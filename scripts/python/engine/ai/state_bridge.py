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
 - `plans` = enumeration offline {uid: {evals:[{abilityId,targetId,rankCount,ranked:[{col,row}]}]}} pour
   l'attaque normale ET les abilities ACTIVES d'attaque (SLICE 2). L'ORDRE de rank est INDIFFERENT :
   `_best_attack` fait un argmax STRICT sur le SET de tuiles atteignables -> on n'a pas a porter le heuristique
   `GetBest`, seulement le SET (tuiles de move d'ou l'attaque est legale, portee = `_ability_reach`).
 - `ability_targets` (SLICE 2) = `ability_targets_offline` (heal/repair/summon/Nova) : enumere l'UNION des cibles
   legales sur toutes les tuiles-caster, mirror `GetAllValidTargetsFromAllPossibleMovementTiles @18111e890` /
   `GetEligibleTargetsSelectable @18111f0d0` (kind/portee derives de gameconfig, cf. `_ability_kind`).

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
from engine.entities.pathfinding.fly_pathfinder import (
    is_like_flying, get_movable_positions as fly_get_movable_positions,
    is_valid_path_node as fly_is_valid_path_node)
from engine.entities.effect_type import EffectType
from engine.entities.active_ability_type import ActiveAbilityType

NORMAL_ATTACK_ID = int(ActiveAbilityType.NormalAttack)   # 17 (id synthetique offline ; cf. en-tete) #158
TELEPORT_STRIKE_TELEPORTING_IN = int(EffectType.TeleportStrike_TeleportingIn)  # 1035 — effet deep-strike -> unite NON-CIBLABLE (#158)


def _is_untargetable(state, uid: int) -> bool:
    """`UnitExtensions.IsTargetable @180ed8ff0` = `!HasFlag(Untargetable=0x11)`. Signal OFFLINE du deep-strike :
    une unite en cours de teleportation (effet `TeleportStrike_TeleportingIn` 1035) est non-ciblable jusqu'a son
    atterrissage (ground truth live ds_landing). -> exclue de l'enumeration de cibles (attaque/ability)."""
    return state.effects is not None and state.effects.has_effect(
        uid, effect_type=TELEPORT_STRIKE_TELEPORTING_IN)


@functools.lru_cache(maxsize=1)
def _weights():
    """Poids BC (statiques) charges 1x. `engine.weights.load()`."""
    from engine.weights import load as _load
    return _load()


def _granted_abilities(vid: str) -> list:
    """Abilities ACTIVES accordees au runtime par un `passiveAbilities` de l'unite (absentes de
    `activeAbilities` — le natif les peuple dans l'ActiveAbilityComponent VIA le passive). DERIVEES DU PASSIVE
    (aucune table hardcodee) : le natif nomme la classe accordee `<Passive>_HealAbility` = membre d'enum
    `Heal_<Passive>` (ex. passive `TwistedScience` -> `TwistedScience_HealAbility$$ExecuteBehaviour @181217ad0`
    = enum `Heal_TwistedScience` 1167). Donc pour chaque passive P on resout l'enum `Heal_<P>` s'il existe.
    C'est le PASSIVE (donnee jeu) + la convention de nommage NATIVE (enum) qui donnent l'ability — pas un
    mapping invente. (Couvre les grants HEAL ; d'autres familles de grant = extension a confirmer.)"""
    import enum_maps as EM
    rev = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    out: list = []
    for p in ((GC.unit(vid) or {}).get("passiveAbilities") or []):
        nm = f"Heal_{p}"
        aid = rev.get(nm)
        if aid is not None:
            out.append((int(aid), nm))
    return out


@functools.lru_cache(maxsize=None)
def _abilities_of(vid: str) -> tuple:
    """Abilities de l'unite reconstruites depuis gameconfig : l'attaque normale (id synthetique 17 si l'unite a
    une arme) + `activeAbilities` (nom == membre d'enum -> id via reverse ACTIVE_ABILITY_TYPE) + les abilities
    ACCORDEES par un passive (`_granted_abilities`, DERIVEES du passive, ex. TwistedScience -> Heal 1167). Une
    active dont le nom n'est pas dans l'enum est ignoree."""
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
    for (aid, name) in _granted_abilities(vid):        # actives accordees par passive (derivees du passive)
        if not any(a[0] == aid for a in out):
            out.append((int(aid), name))
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

    NB : la PORTEE (nombre de tuiles) = stat Movement pour TOUS les pathfinders (Walk comme Fly ; le vol
    change la TRAVERSEE, pas la portee). Le FlyPathfinder (Flying/Burrow) est desormais reproduit par
    `fly_pathfinder` (`_move_tiles` choisit l'arete). Reste non porte : le TeleportStrike (deep-strike =
    tranche deploiement) et les tuiles-hazard temporaires."""
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


def _board_topology_maps(board) -> tuple[dict, dict, dict, dict]:
    """Mirror OFFLINE des seams boardGraph du contexte LIVE (`context._board_tile_ids/_board_neighbours/
    _board_walkable/_board_terrain`), construits depuis `State.board` (memes tuiles boardGraph) :
      - `tile_id_by_pos` {(col,row): tileEntityId} : id de tuile (cible d'une self-cast AoE = MainTile) ;
      - `neigh_by_pos`   {(col,row): [voisins (col,row) ORDRE NATIF GetAdjacentTiles]} : depuis le champ BRUT
        `neighbours` du boardGraph (PAS `board.neighbours` evenq/sorted), pour preserver l'ordre natif dont
        depend la cible exacte de Gauntlets (#117, SortReverse sur le ring-1 natif) ;
      - `walkable_by_pos` {(col,row): walkable} : gate STATIQUE de placement (CanAddUnit #116) ;
      - `terrain_by_pos` {(col,row): tileDefId} : covers HÉBERGÉS par le terrain (TileEffects Loop2, case-37).
    Board absent -> 4 dicts vides (consumers gates ; sans board, ni placement ni Gauntlets ni cover)."""
    if board is None:
        return {}, {}, {}, {}
    tiles = list(board.by_id.values())
    id2pos = {t["id"]: (t["col"], t["row"]) for t in tiles}
    tile_id_by_pos = {(t["col"], t["row"]): t["id"] for t in tiles}
    neigh_by_pos = {(t["col"], t["row"]):
                    [id2pos[n] for n in (t.get("neighbours") or []) if n in id2pos]
                    for t in tiles}
    walkable_by_pos = {(t["col"], t["row"]): bool(t.get("walkable")) for t in tiles}
    terrain_by_pos = {(t["col"], t["row"]): t.get("tileDefId") for t in tiles}
    return tile_id_by_pos, neigh_by_pos, walkable_by_pos, terrain_by_pos


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
    # Sélection du pathfinder par trait (mirror dispatch virtuel `MovementQuery.GetReachableTiles`
    # @18109b380) : unité « comme volante » (Flying/Burrow) -> FlyPathfinder (ignore élévation +
    # unités) ; sinon WalkPathfinder. Portée = même stat Movement dans les deux cas.
    traits = (sc.ctx.traits if sc is not None else None) or []
    _mv = fly_get_movable_positions if is_like_flying(traits) else get_movable_positions
    _, stop = _mv(board, otile, depth, _occupants(state), my_team)
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
    # Arête = pathfinder du MOVER (fly s'il vole -> ignore élévation/unités, comme _move_tiles).
    me = state.get_entity(uid)
    sc = me.get_component(StatsComponent) if me is not None else None
    _edge = fly_is_valid_path_node if is_like_flying(
        (sc.ctx.traits if sc is not None else None) or []) else is_valid_path_node
    level = {t: 0 for t in seeds}
    q = deque(seeds)
    while q:
        cur = q.popleft()
        for n in board.neighbours(cur):
            if n in level:
                continue
            if _edge(board, cur, n, occ, my_team):
                level[n] = level[cur] + 1
                q.append(n)
    return {board.coord(t): d for t, d in level.items()}


# --- Classification d'ability (SLICE 2) — mirror TargetingQuery.GetRange @1810bd670 + le TargetsSelector DSL
#     par-ability (kind non-gameconfig -> derive de la SIGNATURE des constants, exact pour attack/heal/repair/
#     summon, heuristique self pour le residuel). Portee = constants.range sinon attackRangeType sinon arme. ----
# Enums d'ability heal/repair dont `GC.ability` = template de base a CONFIG VIDE : le signal generique
# (`hpToHeal`/`hpToRepair`, cf. `_has_heal_magnitude`) ne peut pas les capter -> gate par ID = l'enum
# d'ability natif `ActiveAbilityType` (une distinction REELLE du jeu, doctrine gate-justifie). Tous les
# autres heals/repairs (dont la config PORTE `hpToHeal`/`hpToRepair`) passent par le chemin generique.
HEAL_ABILITY_IDS = frozenset({8, 18, 1167, 1212})    # MassHeal / Heal / Heal_TwistedScience / HealingBalms_Heal
REPAIR_ABILITY_IDS = frozenset({28, 82, 84, 1119})   # Repair / MechRepair / BattleTinkererRepair / Repair_GalvanicField


def _resolve_ability(ability_id: int):
    """(name, cfg) d'une ability : name via l'enum `ACTIVE_ABILITY_TYPE` (id->nom), cfg via gameconfig."""
    import enum_maps as EM
    name = EM.ACTIVE_ABILITY_TYPE.get(int(ability_id))
    return (name or ""), (GC.ability(name) if name else None) or {}


def _has_heal_magnitude(cfg: dict) -> bool:
    """Signal HEAL generique : presence de l'operande `hpToHeal` du `TargetsSelector` natif (magnitude de
    soin lue par la formule de heal). Remplace le substring de nom (doctrine : gate justifie contre le natif)."""
    return any(k.startswith("hpToHeal") for k in (cfg.get("variables") or {}))


def _has_repair_magnitude(cfg: dict) -> bool:
    """Signal REPAIR generique : presence de l'operande `hpToRepair` (magnitude de reparation)."""
    return any(k.startswith("hpToRepair") for k in (cfg.get("variables") or {}))


def _is_attack_ability(ability_id: int, cfg: dict) -> bool:
    """ATTAQUE (produit du degat) ssi `constants.damageProfile` present ET l'ability n'est PAS deja routee
    vers un playbook NonComparable (NovaBoost/NovaShield portent un damageProfile mais sont buff/tile)."""
    if not (cfg.get("constants") or {}).get("damageProfile"):
        return False
    from engine.playbook.noncomparable import is_noncomp
    return not is_noncomp(int(ability_id))


def _ability_reach(vid: str, ability_id: int, cfg: dict) -> int:
    """Portee de l'ability (mirror `TargetingQuery.GetRange` @1810bd670) : `constants.range` si present, sinon
    `attackRangeType` (Melee->1 ; Normal/Ranged->portee arme), sinon portee arme. (Le +GetStat(0x18) ranged-bonus
    et le clamp effet 0x529 = raffinements runtime non portes.)"""
    c = cfg.get("constants") or {}
    if c.get("range") is not None:
        return int(c["range"])
    if cfg.get("attackRangeType") == "Melee":
        return 1
    return _max_attack_range(vid)


def _ability_kind(ability_id: int, name: str, cfg: dict) -> str:
    """KIND de cible derive offline : 'enemy' (attaque) / 'ally' (heal) / 'machine' (repair) / 'tile' (summon)
    / 'self' (residuel). Cf. §2(c) de la RE : exact pour les 4 premieres, defaut self pour le reste."""
    c = cfg.get("constants") or {}
    if _is_attack_ability(ability_id, cfg):
        return "enemy"
    if int(ability_id) in HEAL_ABILITY_IDS or _has_heal_magnitude(cfg):
        return "ally"
    if int(ability_id) in REPAIR_ABILITY_IDS or _has_repair_magnitude(cfg):
        return "machine"
    if c.get("unitId") and not c.get("damageProfile"):
        return "tile"
    return "self"


def _attack_abilities(vid: str) -> list:
    """[(ability_id, reach)] des abilities d'ATTAQUE de l'unite : l'attaque normale (17, portee=max arme) + chaque
    active a `damageProfile` (non-NonComparable), portee = `_ability_reach`."""
    out = [(NORMAL_ATTACK_ID, _max_attack_range(vid))]
    for aid, _name in _abilities_of(vid):
        if aid == NORMAL_ATTACK_ID:
            continue
        _n, cfg = _resolve_ability(aid)
        if _is_attack_ability(aid, cfg):
            out.append((aid, _ability_reach(vid, aid, cfg)))
    return out


def _plans_for_unit(uid: int, vid: str, origin: tuple | None, move_tiles: list,
                    enemies: list) -> dict:
    """Enumere le `plan` d'attaque de `uid` : pour chaque (ability d'ATTAQUE, ennemi), le SET de tuiles-caster
    (origine + tuiles de move) d'ou l'attaque est legale (dist hex <= portee de l'ability). Forme mirroir de
    `decisionView.attackPlans[uid]` REDUITE a ce que le spine lit (`_best_attack` : abilityId/targetId/rankCount/
    ranked[(col,row)] ; les nombres de degat sont debug-only). Ordre de `ranked` indifferent (argmax strict).

    SLICE 2 : attaque normale (portee=max arme) + abilities ACTIVES d'attaque (portee propre `_ability_reach`)."""
    cand_tiles = [(t["col"], t["row"]) for t in move_tiles]
    if origin is not None:
        cand_tiles.append(origin)
    evals: list = []
    for (aid, reach) in _attack_abilities(vid):
        for en in enemies:
            ep = en.get("pos")
            if not ep:
                continue
            epos = (ep["col"], ep["row"]) if isinstance(ep, dict) else (ep[0], ep[1])
            ranked = [{"col": c, "row": r} for (c, r) in cand_tiles
                      if hexgeo.distance((c, r), epos) <= reach]
            if ranked:
                evals.append({"abilityId": aid, "targetId": en.get("id"),
                              "rankCount": len(ranked), "ranked": ranked})
    return {"evals": evals}


def _is_machine(entity) -> bool:
    """Unite MACHINE (cible du repair) — trait `Mechanical` du gameconfig. Fallback True si indeterminable
    (le repair est dormant ; sur-emettre = filtre downstream)."""
    sc = entity.get_component(StatsComponent)
    traits = (sc.ctx.traits if sc is not None else None) or []
    return "Mechanical" in traits


def ability_targets_offline(state, uid: int, ability_id: int) -> dict:
    """`BasePlaybook.GetAllValidTargetsFromAllPossibleMovementTiles @18111e890` / `BattleQuery @18105d700` /
    `GetEligibleTargetsSelectable @18111f0d0` — enumerateur de ciblage OFFLINE (SLICE 2). Renvoie l'UNION des
    cibles legales sur toutes les tuiles-caster (origine + move) au format du RPC `abilityTargets` que le seam
    `AiDecisionContext.ability_targets` consomme :
      {units:[{unitId, abilities:[{abilityId, targets:[{kind:'unit'|'tile', targetId, tile:{col,row}}]}]}]}
    kind emis = 'unit' (enemy/ally/machine/self) ou 'tile' (summon). Portee/kind via la classification gameconfig
    (`_ability_kind`/`_ability_reach`). Reutilise `_move_tiles`/`_occupants`/board/hexgeo (aucun code board neuf)."""
    me = state.get_entity(uid)
    if me is None:
        return {"units": []}
    oc = me.get_component(OwnerComponent)
    pc = me.get_component(PositionComponent)
    uco = me.get_component(UnitComponent)
    my_team = oc.team if oc is not None else None
    vid = uco.visual_id if uco is not None else ""
    origin = (pc.col, pc.row) if pc is not None else None
    name, cfg = _resolve_ability(ability_id)
    kind = _ability_kind(ability_id, name, cfg)
    reach = _ability_reach(vid, ability_id, cfg) if kind in ("enemy", "ally", "machine") else 1
    reach_tiles = [(t["col"], t["row"]) for t in _move_tiles(state, uid, vid, my_team, origin)]
    if origin is not None:
        reach_tiles.append(origin)
    targets: list = []
    board = state.board
    if kind == "self":
        targets.append({"kind": "unit", "targetId": uid,
                        "tile": {"col": origin[0], "row": origin[1]} if origin else None})
    elif kind in ("enemy", "ally", "machine"):
        for eid, e in state.entities.items():
            u = e.get_component(UnitComponent)
            o = e.get_component(OwnerComponent)
            p = e.get_component(PositionComponent)
            if u is None or not u.alive or o is None or p is None:
                continue
            is_ally = (o.team == my_team)
            if kind == "enemy" and is_ally:
                continue
            if kind in ("ally", "machine") and not is_ally:
                continue
            if kind == "machine" and not _is_machine(e):
                continue
            if _is_untargetable(state, eid):             # non-ciblable (deep-strike teleporting-in)
                continue
            tp = (p.col, p.row)
            if eid == uid or any(hexgeo.distance(T, tp) <= reach for T in reach_tiles):
                targets.append({"kind": "unit", "targetId": eid,
                                "tile": {"col": tp[0], "row": tp[1]}})
    elif kind == "tile" and board is not None:
        occupied = {(p.col, p.row) for e in state.entities.values()
                    for p in (e.get_component(PositionComponent),)
                    for u in (e.get_component(UnitComponent),)
                    if p is not None and (u is None or u.alive)}
        seen: set = set()
        for T in reach_tiles:                                    # spawn adjacent (ring-1) a une tuile-caster
            ttile = board.id_at(T[0], T[1])
            if ttile is None:
                continue
            for n in board.neighbours(ttile):
                col, row = board.coord(n)
                if (col, row) in seen or (col, row) in occupied:
                    continue
                if not board.by_id.get(n, {}).get("walkable", True):
                    continue
                seen.add((col, row))
                targets.append({"kind": "tile", "targetId": None, "tile": {"col": col, "row": row}})
    return {"units": [{"unitId": uid, "abilities": [{"abilityId": int(ability_id), "targets": targets}]}]}


def _dv_units(state) -> list:
    """`units` façon decisionView (ctrl attribue plus bas par team) : id/alive/pos/team/hp/visualId/effects.
    MoW EXCLUES : le natif ne met que `EntityType.Unit` dans `decisionView.units` (les Machines vivent
    dans le canal separe `.mows`) -- cf. `_load_machines`."""
    from engine.runner.components import EffectsOwnedComponent, is_machine_of_war
    out: list = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        ec = e.get_component(EffectsOwnedComponent)
        if uc is None or is_machine_of_war(e):
            continue
        out.append({
            "id": eid, "visualId": uc.visual_id, "alive": bool(uc.alive),
            "team": oc.team if oc is not None else None,
            "pos": {"col": pc.col, "row": pc.row} if pc is not None else None,
            "hp": hc.hp if hc is not None else None,
            # `effects` = noms bruts du composant natif `EffectsOwnedComponent.effects` (str). Les gates
            # d'effets de DÉCISION lisent l'état STRUCTURÉ `State.effects` (HasEffect), pas ce champ.
            "effects": list(ec.effects) if ec is not None else [],
        })
    return out


def _obs_units(state) -> list:
    """`observeBattle.units` façon runner : squadId/teamId/visualId/hp/hpMax/isDead/col/row.
    MoW EXCLUES (canal separe `.mows` cote natif, cf. `_dv_units`)."""
    from engine.runner.components import is_machine_of_war
    out: list = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        if uc is None or is_machine_of_war(e):
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
    # #57l — MinDist(16) ne mesure QU'AUX ennemis CIBLABLES (miroir `FindClosestEnemy` -> `!IsTargetable`,
    # @181197f10) : un ennemi en Deep-Strike (TeleportStrike, non-atterri) est NON-ciblable et exclu du
    # ClosestEnemy. Sans ce filtre, un deep-strike plus proche par chemin ecrase le vrai ClosestEnemy et
    # fausse la distance-chemin par tuile (12345 s5 : (1,4)=6 vers Dante vs 7 vers l'ennemi ciblable).
    # `enemies`/`epos` restent complets (occupance/positionnement) ; seul le seed MinDist est filtre.
    tgt_epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies
                if e.get("pos") and not _is_untargetable(state, e.get("id"))]
    pathdist_by_pos = _pathdist_to_enemies(state, uid, my_team, tgt_epos)
    # topologie boardGraph (self-cast MainTile #116, ordre voisins natif Gauntlets #117, gate placement) —
    # mirror OFFLINE des 3 seams boardGraph que le contexte LIVE fournit ; ex-gap du bridge (build_from_state
    # anterieur a l'ajout de ces champs requis) revele par la confrontation du tour du Skitarii (#24).
    tile_id_by_pos, neigh_by_pos, walkable_by_pos, terrain_by_pos = _board_topology_maps(state.board)
    # Plans d'ATTAQUE : ne cibler que les ennemis CIBLABLES (exclut les deep-strike teleporting-in, non-ciblables
    # jusqu'a l'atterrissage). `enemies` reste complet pour le positionnement (ils occupent le board).
    tgt_enemies = [e for e in enemies if not _is_untargetable(state, e.get("id"))]
    plans = {uid: _plans_for_unit(uid, vid or "", origin, move_tiles, tgt_enemies)}

    def _rpc(method, body, timeout=0):
        """Seam RPC offline (SLICE 2) : `abilityTargets` -> enumerateur offline (heal/repair/summon/Nova) ;
        tout autre method -> vide. Capture `state` (closure) pour `AiDecisionContext.ability_targets`."""
        if method == "abilityTargets" and isinstance(body, dict):
            return ability_targets_offline(state, body.get("unitId"), body.get("abilityType"))
        return {"units": []}

    return AiDecisionContext(
        rpc=_rpc, rid=0, wt=_weights(), predictor=None, sctx=None, scene=scene,
        uid=uid, me=me, units=units, cur=getattr(state, "current_player_id", None), plans=plans,
        enemies=enemies, epos=epos, tgt_epos=tgt_epos, fpos=fpos, origin=origin,
        move_tiles=move_tiles, reach_nc=reach_nc,
        hp_cur_by_id=hp_cur_by_id, hpmax_by_id=hpmax_by_id, obs_units=_obs_units(state),
        ab_name_by_id=ab_name_by_id, normal_ids=normal_ids,
        elev_by_pos=elev_by_pos, is_temporary_by_pos={}, effects_by_pos={},
        pathdist_by_pos=pathdist_by_pos,
        tile_id_by_pos=tile_id_by_pos, neigh_by_pos=neigh_by_pos, walkable_by_pos=walkable_by_pos,
        terrain_by_pos=terrain_by_pos, debug=debug)
