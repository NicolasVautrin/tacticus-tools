"""`build_from_state` — bridge `State`(runner) -> `AiDecisionContext` (100% offline, SANS RPC). #65.

Le decideur `DefaultAiUnitTactic.calculate_next_action` ne consomme QU'un `AiDecisionContext` ; ce module
le construit ENTIEREMENT depuis un `State` runner (composants + board + gameconfig), en remplacement de la
couture RPC de `context.build` (decisionView/observeBattle/tileMeta/pathDistToEnemies/aiMovableTiles/
combatSnapshot). C'est ce qui permet a `StartTurnOperation` de jouer les summons (unites `ai_controlled`)
via le PLAYBOOK COMPLET offline (cf. docs/rl/runner-engine.md #65).

Faits cles (map de la passe RE / agent) :
 - Le spine ne lit QUE `ctx.scene` pour la prediction (jamais `predictor`/`sctx`) et `ctx.cur` est mort.
 - `scene = Scene.from_state(state)` : le `StatsComponent.ctx` d'une unite EST le meme `UnitContext` que le
   predicteur cache ; `State.effects` EST l'`EffectsState` ; `State.board` = elevation + adjacence hex.
 - `plans` = enumeration offline {uid: {evals:[{abilityId,targetId,rankCount,ranked:[{col,row}]}]}}.
   L'ORDRE de rank est INDIFFERENT : `_best_attack` fait un argmax STRICT sur le SET de tuiles atteignables
   -> on n'a pas a porter le heuristique `GetBest`, seulement le SET (tuiles de move d'ou l'attaque est legale).
 - `ability_targets` = fermeture no-op (retourne vide) : SEULS heal/repair/summon/Nova l'utilisent ; un summon
   a attaque-normale (Cadien) n'en a pas besoin (SLICE 1). SLICE 2 = enumerateur de cibles offline.

Attaque normale : son ActiveAbilityType CONCRET per-unite (Loki_NormalAttack=69, ...) est un etat RUNTIME
(`ActiveAbilityComponent.NormalAttackType`) NON derivable de gameconfig -> on utilise l'id SYNTHETIQUE 17
(`NormalAttack` generique). C'est SANS impact : la prediction lit l'arme du `ctx` (pas l'id), et l'apply de
l'attaque normale passe par `AttackUnitMessage` (sans id). Les abilities ACTIVES, elles, ont un nom == leur
membre d'enum -> id resolu par reverse-lookup `ACTIVE_ABILITY_TYPE`.

Gaps no-op documentes : `is_temporary_by_pos`/`effects_by_pos` = {} (tuiles temporaires/hazard non portees,
~0 sur board plat) ; `pathdist_by_pos` = BFS multi-source approx (fallback hex present dans best_move).
"""
from __future__ import annotations

import functools
from collections import deque
from typing import Any

import gameconfig as GC
import hexgeo

from engine.playbook.scene import Scene
from engine.runner.components import (StatsComponent, OwnerComponent, PositionComponent,
                                      HealthComponent, UnitComponent)
from engine.entities.pathfinding.walk_pathfinder import get_movable_positions, is_valid_path_node

NORMAL_ATTACK_ID = 17    # ActiveAbilityType.NormalAttack (id synthetique offline ; cf. en-tete)


@functools.lru_cache(maxsize=1)
def _weights():
    """Poids BC (statiques) charges 1x. `engine.weights.load()`."""
    from engine.weights import load as _load
    return _load()


@functools.lru_cache(maxsize=None)
def _abilities_of(vid: str) -> tuple:
    """Abilities de l'unite (offline) sous forme `((id, name), ...)` : l'attaque normale (id synthetique 17
    si l'unite a une arme) + chaque `activeAbilities` (nom == membre d'enum -> id via reverse ACTIVE_ABILITY_TYPE).
    Une active dont le nom n'est pas dans l'enum du build est ignoree (documente)."""
    import enum_maps as EM
    rev = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    gu = GC.unit(vid) or {}
    out: list = []
    if gu.get("weapons"):
        out.append((NORMAL_ATTACK_ID, "NormalAttack"))
    for key in (gu.get("activeAbilities") or []):
        aid = rev.get(key)
        if aid is not None:
            out.append((int(aid), key))
    return tuple(out)


def _max_attack_range(vid: str) -> int:
    """Portee d'attaque MAX = max(Range des armes) ; melee (Range absent) -> 1. Sert de rayon d'enumeration
    des tuiles de tir legales (identique a triggers._max_attack_range)."""
    gu = GC.unit(vid) or {}
    ranges = [int(w.get("Range") or 0) for w in (gu.get("weapons") or [])]
    mx = max(ranges) if ranges else 0
    return mx if mx > 0 else 1


def _move_range(ctx, vid: str) -> int:
    """Portee de deplacement (tuiles). Priorite au STAT movement LIVE (effet-inclusif, `StatType.MOVEMENT=1`)
    quand il est seede (State charge d'un combatSnapshot — c'est la source que `test_pathfinding_live` confronte
    a `aiMovableTiles`) ; sinon fallback gameconfig `Movement` (cas du summon spawne offline sans combatSnapshot,
    ou la base sans bonus = la bonne portee). 0 -> unite immobile.

    NB : les unites NON-WALK (Fly/Teleport : portee native > stat Movement) ne sont PAS reproductibles par le
    flood Walk (limitation partagee avec le port pathfinding, cf. `_is_non_walk`) ; les summons sont Walk."""
    from engine.entities.stats import StatType
    mv = ctx.get_stat(int(StatType.MOVEMENT)) if ctx is not None else 0
    if mv and mv > 0:
        return int(mv)
    return int((GC.unit(vid) or {}).get("Movement") or 0)


def _occupants(state) -> dict:
    """{tile_id -> team} des unites VIVANTES positionnees (bloque le pathfinding : ennemi bloque, allie passe)."""
    board = state.board
    occ: dict = {}
    if board is None:
        return occ
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if uc is None or not uc.alive or oc is None or pc is None:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ[t] = oc.team
    return occ


def _move_tiles(state, uid: int, vid: str, my_team: int, origin: tuple | None) -> list:
    """Tuiles d'ARRET atteignables de `uid` (mirror `aiMovableTiles`) = `WalkPathfinder.get_movable_positions`
    a portee `Movement`. [] si pas de board / origine / Movement=0. Forme `[{col,row}]` (comme le RPC)."""
    board = state.board
    if board is None or origin is None:
        return []
    otile = board.id_at(origin[0], origin[1])
    me = state.get_entity(uid)
    sc = me.get_component(StatsComponent) if me is not None else None
    depth = _move_range(sc.ctx if sc is not None else None, vid)
    if otile is None or depth <= 0:
        return []
    _, stop = get_movable_positions(board, otile, depth, _occupants(state), my_team)
    out = []
    for t in stop:
        c, r = board.coord(t)
        out.append({"col": c, "row": r})
    return out


def _pathdist_to_enemies(state, uid: int, my_team: int, enemy_positions: list) -> dict:
    """`{(col,row): pathDist}` = distance de MARCHE (BFS multi-source depuis les tuiles ennemies) vers
    l'ennemi le plus proche. Approximation du RPC `pathDistToEnemies` (le natif `GetMinDistanceToClosestEnemy`
    exact = raffinement) ; `best_move` a de toute facon un fallback distance hex. Predicat d'arete =
    `is_valid_path_node` (marchable + |Delta elev|<=1 + non bloque par un ennemi)."""
    board = state.board
    if board is None or not enemy_positions:
        return {}
    seeds = [board.id_at(c, r) for (c, r) in enemy_positions]
    seeds = [t for t in seeds if t is not None]
    occ = _occupants(state)
    level = {t: 0 for t in seeds}
    q = deque(seeds)
    while q:
        cur = q.popleft()
        for n in board.neighbours(cur):
            if n in level:
                continue
            if is_valid_path_node(board, cur, n, occ, my_team):
                level[n] = level[cur] + 1
                q.append(n)
    return {board.coord(t): d for t, d in level.items()}


def _plans_for_unit(uid: int, vid: str, origin: tuple | None, move_tiles: list,
                    enemies: list) -> dict:
    """Enumere le `plan` d'attaque de `uid` : pour chaque (ability d'attaque, ennemi), le SET de tuiles-caster
    (origine + tuiles de move) d'ou l'attaque est legale (dist hex <= portee de l'ability). Forme mirroir de
    `decisionView.attackPlans[uid]` REDUITE a ce que le spine lit (`_best_attack` : abilityId/targetId/rankCount/
    ranked[(col,row)] ; les nombres de degat sont debug-only). Ordre de `ranked` indifferent (argmax strict).

    SLICE 1 : seule l'ATTAQUE NORMALE est enumeree (portee = max Range d'arme). Les abilities actives d'attaque
    (DefaultActiveAbilityPlaybook) = SLICE 2 (necessite leur portee/ciblage propre)."""
    reach = _max_attack_range(vid)
    cand_tiles = [(t["col"], t["row"]) for t in move_tiles]
    if origin is not None:
        cand_tiles.append(origin)
    evals: list = []
    for en in enemies:
        ep = en.get("pos")
        if not ep:
            continue
        epos = (ep["col"], ep["row"]) if isinstance(ep, dict) else (ep[0], ep[1])
        ranked = [{"col": c, "row": r} for (c, r) in cand_tiles
                  if hexgeo.distance((c, r), epos) <= reach]
        if ranked:
            evals.append({"abilityId": NORMAL_ATTACK_ID, "targetId": en.get("id"),
                          "rankCount": len(ranked), "ranked": ranked})
    return {"evals": evals}


def _dv_units(state) -> list:
    """`units` façon decisionView (ctrl attribue plus bas par team) : id/alive/pos/team/hp/visualId/effects."""
    from engine.runner.components import EffectsOwnedComponent
    out: list = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        ec = e.get_component(EffectsOwnedComponent)
        if uc is None:
            continue
        out.append({
            "id": eid, "visualId": uc.visual_id, "alive": bool(uc.alive),
            "team": oc.team if oc is not None else None,
            "pos": {"col": pc.col, "row": pc.row} if pc is not None else None,
            "hp": hc.hp if hc is not None else None,
            "effects": list(ec.effects) if ec is not None else [],
        })
    return out


def _obs_units(state) -> list:
    """`observeBattle.units` façon runner : squadId/teamId/visualId/hp/hpMax/isDead/col/row."""
    out: list = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        if uc is None:
            continue
        out.append({
            "squadId": eid, "teamId": oc.team if oc is not None else None,
            "visualId": uc.visual_id, "hp": hc.hp if hc is not None else None,
            "hpMax": hc.hp_max if hc is not None else None, "isDead": not bool(uc.alive),
            "col": pc.col if pc is not None else None, "row": pc.row if pc is not None else None,
        })
    return out


def _no_rpc(method: str, body: dict, timeout: int = 0) -> dict:
    """Fermeture RPC no-op du bridge offline. `ability_targets` (heal/repair/summon/Nova) -> vide.
    SLICE 2 = enumerateur de cibles offline (from State) branche ici."""
    return {"units": []}


def build_from_state(state, uid: int, debug: bool = False):
    """`State`(runner) -> `AiDecisionContext` pour l'unite `uid` (offline). Tous les champs derives des
    composants/board/gameconfig ; `predictor`/`sctx`=None (le spine lit `ctx.scene`). Voir en-tete pour les
    gaps documentes."""
    from engine.ai.context import AiDecisionContext, _enemies

    me_ent = state.get_entity(uid)
    if me_ent is None:
        raise ValueError(f"build_from_state: unite {uid} absente du State")
    m_oc = me_ent.get_component(OwnerComponent)
    m_uc = me_ent.get_component(UnitComponent)
    m_pc = me_ent.get_component(PositionComponent)
    my_team = m_oc.team if m_oc is not None else None
    vid = m_uc.visual_id if m_uc is not None else None
    origin = (m_pc.col, m_pc.row) if m_pc is not None else None

    units = _dv_units(state)
    for u in units:                                   # ctrl = meme camp que l'unite qui decide
        u["ctrl"] = (u.get("team") == my_team)
    enemies = _enemies(units)
    epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies]
    fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("ctrl") and u.get("alive") and u.get("pos") and u.get("id") != uid]

    abilities = [{"id": aid, "name": nm, "usable": True} for (aid, nm) in _abilities_of(vid or "")]
    ab_name_by_id = {aid: nm for (aid, nm) in _abilities_of(vid or "")}
    normal_ids = {NORMAL_ATTACK_ID} if any(a[0] == NORMAL_ATTACK_ID for a in _abilities_of(vid or "")) else set()

    me = next((u for u in units if u.get("id") == uid), None)
    if me is not None:
        me["abilities"] = abilities

    move_tiles = _move_tiles(state, uid, vid or "", my_team, origin)
    reach_nc = [(t["col"], t["row"]) for t in move_tiles] + ([origin] if origin is not None else [])

    scene = Scene.from_state(state)
    hp_cur_by_id = dict(scene.hp_by_id)
    hpmax_by_id = dict(scene.hpmax_by_id)
    elev_by_pos = scene.elev_by_pos or {}
    pathdist_by_pos = _pathdist_to_enemies(state, uid, my_team, epos)
    plans = {uid: _plans_for_unit(uid, vid or "", origin, move_tiles, enemies)}

    return AiDecisionContext(
        rpc=_no_rpc, rid=0, wt=_weights(), predictor=None, sctx=None, scene=scene,
        uid=uid, me=me, units=units, cur=getattr(state, "current_player_id", None), plans=plans,
        enemies=enemies, epos=epos, fpos=fpos, origin=origin,
        move_tiles=move_tiles, reach_nc=reach_nc,
        hp_cur_by_id=hp_cur_by_id, hpmax_by_id=hpmax_by_id, obs_units=_obs_units(state),
        ab_name_by_id=ab_name_by_id, normal_ids=normal_ids,
        elev_by_pos=elev_by_pos, is_temporary_by_pos={}, effects_by_pos={},
        pathdist_by_pos=pathdist_by_pos, debug=debug)
