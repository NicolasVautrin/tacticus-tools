"""#149 slice-8 : ScythingTalons (1065) MIGRATION replay-diff -- l'arbre DSL == l'ancien imperatif, BIT-EXACT.

`ScythingTalonsAbility.ExecuteBehaviour @1812059f0` (DECOMPILE) =
    ExecuteAtomic( op_BitwiseAnd(
        AttackWithAttackDamage(caster, target, MinMaxDamage, Bio, condHits1=0x2f=3),
        AttackWithAttackDamage(caster, Unique(Enemies(caster, AdjacentUnits(casterTile,1) &
                               AdjacentUnits(targetTile,1), 3)), MEME MinMaxDamage, Bio, condHits2=0x32=2) ) )
Le SPLASH natif = UN SEUL `AttackWithAttackDamage` avec un SELECTEUR MULTI-cible (PAS un Foreach) : porte via
le mode `multi=True` de la feuille (tri par id = ordre de lecture natif). Selecteur splash =
`Alive(And(AdjacentEnemies(CasterTile()), AdjacentEnemies(TargetTile())))` = ennemis du caster adjacents aux
DEUX tuiles (== l'imperatif `_adjacent_to_both`).

Le caster natif (tyranSmnWarrior) est SUMMON-only ; le REPLAY-DIFF est CASTER-AGNOSTIQUE (l'arbre ET
l'imperatif lisent le MEME config ScythingTalons scale par le level du caster) -> on utilise un player unit
MELEE buildable qu'on DRIVE dans le cluster ennemi pour exercer un SPLASH `_adjacent_to_both` NON VIDE (>=1
ennemi adjacent aux DEUX). L'arbre `scything_talons_tree()` (via `ScythingTalonsAbility.execute_behaviour`)
doit reproduire BIT-EXACT l'ancien imperatif `_splash_ability_behaviour`+`_adjacent_to_both` (meme set splash,
main + splash per-coup) sous le MEME `state.rng` seede, sur DEUX etats INDEPENDANTS de la MEME capture LIVE.
C'est le PREMIER confront LIVE non-vide du selecteur `_adjacent_to_both` DSL (empty en 1v1 slice-4). Lit
l'etat LIVE, aucune tuile/RVA hardcodee, drive les positions. ASCII-only.
"""
from __future__ import annotations

from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, OwnerComponent, UnitComponent
from engine.runner.abilities.loki import (ScythingTalonsAbility, _splash_ability_behaviour,
                                          _adjacent_to_both)
from engine.entities.pathfinding.board import Board

CASTER_VIS = "tyranTyrantGuard"     # player unit MELEE buildable, drive-to-contact eprouve (slice-4)
ENEMIES = "necroWarden,necroDestroyer,necroSpyder,necroOverlord"   # cluster spawn -> adjacent-to-both exercable
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", ENEMIES]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _team(state, eid):
    e = state.get_entity(eid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _alive(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.alive if uc is not None else True


def _has_stats(state, eid):
    e = state.get_entity(eid)
    return e is not None and e.get_component(StatsComponent) is not None


def _visual(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.visual_id if uc is not None else None


def _per_hit(atk):
    return (atk or {}).get("per_hit")


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def _find_adj_both_pair(state):
    """Scan tous les couples cross-team (caster, target) VIVANTS+StatsComponent pour un `_adjacent_to_both`
    NON VIDE (>=1 ennemi-du-caster adjacent aux DEUX). Renvoie (caster_id, target_id) ou (None, None)."""
    ids = list(state.entities)
    for a in ids:
        if not (_alive(state, a) and _has_stats(state, a)):
            continue
        ta = _team(state, a)
        for b in ids:
            if b == a or _team(state, b) == ta or not _alive(state, b):
                continue
            if _adjacent_to_both(state, a, b):
                return a, b
    return None, None


def test_scything_talons_migration_matches_imperative(live_session, rpc, build_runner):
    """L'arbre DSL ScythingTalons reproduit l'ancien impératif (`_splash_ability_behaviour`+`_adjacent_to_both`)
    BIT-EXACT : même set splash, même main per-coup, même splash per-coup, sous le MÊME RNG seedé."""
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    # native_sym = adjacence unite-unite CORRECTE (mirror natif ; PAS le boardGraph brut qui exclut les
    # tuiles occupees, piege #148). Requis par `_adjacent_to_both` (state.board.neighbours).
    board = Board(bg["tiles"], adjacency="native_sym")

    def tile_of(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    # --- DRIVE : wade le caster DANS le cluster ennemi (maximise le nb d'ennemis vivants adjacents) jusqu'a
    #     ce qu'un couple cross-team ait un `_adjacent_to_both` NON VIDE. ---
    my_player = None
    pair_caster = pair_target = None
    dv = ob = snap = None
    for _turn in range(25):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        if not _ok(dv):
            pytest.skip("decisionView KO")
        st = load_state(dv, ob, snap); st.board = board
        pc, pt = _find_adj_both_pair(st)
        if pc is not None:
            pair_caster, pair_target = pc, pt
            break
        units = dv.get("units") or []
        caster = next((u for u in units if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        if caster is None:
            pytest.skip("caster (tyranTyrantGuard) mort/absent avant contact")
        if my_player is None:
            my_player = caster.get("owner")
        if dv.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        enemies = [u for u in units if u.get("alive") and u.get("owner") != my_player]
        enemy_tiles = {tile_of(u) for u in enemies if tile_of(u) is not None}
        if not enemy_tiles:
            pytest.skip("aucun ennemi vivant")
        # tuiles atteignables du caster ; choisir celle qui maximise (#ennemis adjacents, -dist au plus proche)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in ((mt or {}).get("units") or []) if x.get("unitId") == caster["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        cur = tile_of(caster)
        if cur is not None:
            reach.setdefault(cur, (caster["pos"]["col"], caster["pos"]["row"]))
        if not reach:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        dist = _bfs(board, cur) if cur is not None else {}
        mind = {et: min((dist.get(t, 1 << 20) for t in reach), default=1 << 20) for et in enemy_tiles}

        def _score(t):
            adj = set(board.neighbours(t))
            n_adj = sum(1 for et in enemy_tiles if et in adj)          # ennemis adjacents a cette tuile
            near = min((_dist_between(board, t, et) for et in enemy_tiles), default=1 << 20)
            return (n_adj, -near)

        best = max(reach, key=_score)
        col, row = reach[best]
        if best != cur:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": caster["id"], "to": {"col": col, "row": row}}}, 40)
        else:
            # deja au meilleur poste mais pas encore de splash -> laisser la main (l'IA ennemie se rapproche)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    if pair_caster is None:
        pytest.skip("aucun couple avec `_adjacent_to_both` non vide en 25 tours (geometrie non atteinte)")

    caster_id, target_id = pair_caster, pair_target

    # --- capture stable + rng ---
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")

    # --- DEUX etats INDEPENDANTS depuis la MEME capture, MEME board + seedes IDENTIQUEMENT -> arbre vs imperatif.
    st_dsl = load_state(dv, ob, snap); st_dsl.board = board; st_dsl.rng = _seed_rng(s0)
    st_imp = load_state(dv, ob, snap); st_imp.board = board; st_imp.rng = _seed_rng(s0)

    # [DSL] l'arbre migre (via la classe d'ability)
    res_dsl = ScythingTalonsAbility().execute_behaviour(st_dsl, caster_id, target_id)
    assert res_dsl is not None and res_dsl.get("dsl") is True, f"arbre DSL non execute: {res_dsl}"
    dsl_main = _per_hit(res_dsl.get("main_attack"))
    dsl_splash = {s["target"]: _per_hit(s["attack"]) for s in (res_dsl.get("splash") or [])}

    # [IMPERATIF] la mecanique partagee _splash_ability_behaviour + _adjacent_to_both (ancien chemin)
    imp_set = _adjacent_to_both(st_imp, caster_id, target_id)
    res_imp = _splash_ability_behaviour(st_imp, caster_id, target_id, "ScythingTalons", "Bio",
                                        ranged=False, splash_set=imp_set)
    imp_main = _per_hit(res_imp.get("main_attack"))
    imp_splash = {s["target"]: _per_hit(s["attack"]) for s in (res_imp.get("splash") or [])}

    print(f"\n[SCYTHING migration] caster={caster_id} target={target_id} "
          f"splash_dsl={sorted(dsl_splash)} splash_imp={sorted(imp_splash)}")
    print(f"[SCYTHING migration] main dsl={dsl_main} imp={imp_main}")
    for tid in sorted(set(dsl_splash) | set(imp_splash)):
        print(f"[SCYTHING migration] splash {tid}: dsl={dsl_splash.get(tid)} imp={imp_splash.get(tid)}")

    # 0) le splash a REELLEMENT fire (non vide) -> selecteur `_adjacent_to_both` DSL exerce non-vide
    assert imp_splash, "splash `_adjacent_to_both` vide cote imperatif -> chemin multi-cible non exerce"
    # 1) MEME set splash (Alive(And(AdjacentEnemies(CasterTile()),AdjacentEnemies(TargetTile()))) == _adjacent_to_both)
    assert set(dsl_splash) == set(imp_splash), (
        f"set splash DSL {sorted(dsl_splash)} != imperatif {sorted(imp_splash)}")
    # 2) MAIN per-coup BIT-EXACT
    assert dsl_main == imp_main, f"main per-coup DSL {dsl_main} != imperatif {imp_main}"
    # 3) SPLASH per-coup BIT-EXACT par cible
    for tid in sorted(set(dsl_splash) | set(imp_splash)):
        assert dsl_splash.get(tid) == imp_splash.get(tid), (
            f"splash per-coup cible {tid} DSL {dsl_splash.get(tid)} != imperatif {imp_splash.get(tid)}")


def _dist_between(board, a, b):
    """Distance BFS walkable a->b (approx pour scorer la proximite au cluster). 1<<20 si injoignable."""
    if a == b:
        return 0
    dist = {a: 0}; q = deque([a])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == b or board.walkable(n)):
                dist[n] = dist[x] + 1
                if n == b:
                    return dist[n]
                q.append(n)
    return 1 << 20
