"""VALIDATION LIVE des ports d'ability de summon (#65 SLICE 2 c') sur board/stats REELS.

On construit un runner live (board natif + units reels), on charge l'etat offline, puis on applique les
abilities portees via le CHEMIN REEL `summon_ai._apply_active_ability` (handler-vs-generic) et on confronte
la STRUCTURE au natif :

  - ValkyrieStrike (1018) : le port dedie EXCLUT du generique -> AUCUN degat immediat + effet 1022 pose
    (correction du sur-tir). Controle : `_is_active_attack_ability(1018) is True` (le sur-tir etait reel).
  - PlasmaGrenade (1098) : main sur target (hits=nrOfHits=2) + splash sur `_adjacent_enemies_of` (hits=
    nrOfHits_2=1). Le SET splash == voisins boardGraph (NATIF) de la cible INTER ennemis (hors cible).

Geometrie = adjacence NATIVE (boardGraph -> Board evenq). Degat exact (RNG cale) = raffinement non teste ici
(comme test_summon_trigger) ; on valide COUNTS + SET + no-fire, i.e. les priorites 1/2/4 du spec validator.

NON committe (tests confront live, hors depot).
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (OwnerComponent, PositionComponent, HealthComponent,
                                      UnitComponent)

PLASMA_GRENADE = 1098
VALKYRIE_STRIKE = 1018
VALKYRIE_EFFECT = 1022


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _tile_of(board, state, uid):
    pc = state.get_entity(uid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _load(rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777")["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap)
    state.board = board
    if isinstance(s0, dict) and s0.get("mt"):
        state.rng = _seed_rng(s0)
    return state, board, dec


def _teams(state):
    """(_my_unit_id, enemies_by_team) : renvoie un caster de reference + la liste des ennemis d'une team."""
    by_team: dict = {}
    for eid, e in state.entities.items():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or uc is None or pc is None or not uc.alive:
            continue
        by_team.setdefault(oc.team, []).append(eid)
    return by_team


def _pick_target_with_adjacent_enemy(state, board):
    """Cherche (caster_team_unit, target, expected_splash) : une cible d'une team B ayant >=1 autre unite B
    adjacente (boardGraph), et un caster de team A. DRIVE une 2e unite B adjacente si aucune naturelle."""
    by_team = _teams(state)
    if len(by_team) < 2:
        return None
    teams = sorted(by_team.keys())
    team_a, team_b = teams[0], teams[1]
    caster = by_team[team_a][0]
    # cherche une cible team_b ayant un voisin team_b
    for tgt in by_team[team_b]:
        ttile = _tile_of(board, state, tgt)
        if ttile is None:
            continue
        neigh = set(board.neighbours(ttile))
        adj = [u for u in by_team[team_b]
               if u != tgt and _tile_of(board, state, u) in neigh]
        if adj:
            return caster, tgt, sorted(adj)
    # aucune adjacence naturelle -> DRIVE : place une 2e unite team_b sur une tuile libre adjacente a la 1re
    if len(by_team[team_b]) < 2:
        return None
    tgt = by_team[team_b][0]
    victim = by_team[team_b][1]
    ttile = _tile_of(board, state, tgt)
    occupied = {_tile_of(board, state, u) for u in state.entities
                if state.get_entity(u).get_component(PositionComponent) is not None}
    for nb in board.neighbours(ttile):
        info = board.by_id.get(nb)
        if info is not None and nb not in occupied and board.walkable(nb):
            state.get_entity(victim).get_component(PositionComponent).col = info["col"]
            state.get_entity(victim).get_component(PositionComponent).row = info["row"]
            return caster, tgt, [victim]
    return None


def test_valkyrie_strike_no_immediate_damage(rpc, build_runner):
    """1018 = post l'effet 1022, ZERO degat immediat (sur-tir generique corrige)."""
    from engine.runner.operations.summon_ai import _apply_active_ability, _is_active_attack_ability
    state, board, _dec = _load(rpc, build_runner)
    by_team = _teams(state)
    if len(by_team) < 2:
        pytest.skip("pas 2 teams")
    teams = sorted(by_team.keys())
    caster, target = by_team[teams[0]][0], by_team[teams[1]][0]

    # controle : sans le port dedie, 1018 (damageProfile Blast) serait classe attaque -> sur-tir reel.
    assert _is_active_attack_ability(VALKYRIE_STRIKE) is True

    thc = state.get_entity(target).get_component(HealthComponent)
    hp_before = thc.hp
    res = _apply_active_ability(state, caster, target, VALKYRIE_STRIKE)
    hp_after = state.get_entity(target).get_component(HealthComponent).hp
    eff_names = [getattr(ef, "name", None) for ef in state.effects.active_effects(target, {"hp": hp_after})] \
        if state.effects is not None else []
    print(f"\n[VALKYRIE] routed={res.get('routed')} hp {hp_before}->{hp_after} effects={eff_names}")

    assert res.get("routed") == "handler", f"1018 non route au handler (sur-tir NON corrige) : {res}"
    assert hp_after == hp_before, f"1018 a inflige {hp_before - hp_after} degat IMMEDIAT (doit etre 0)"
    assert any((n or "").startswith("ValkyrieStrike") for n in eff_names) \
        or VALKYRIE_EFFECT in [getattr(ef, "effect_type", None) for ef in
                               (state.effects.active_effects(target, {"hp": hp_after}) if state.effects else [])], \
        f"effet 1022 ValkyrieStrike_Effect non pose : {eff_names}"


def test_plasma_grenade_main_plus_splash(rpc, build_runner):
    """1098 = attaque main (2 hits) sur target + splash (1 hit) sur les ennemis adjacents (set == boardGraph)."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    state, board, _dec = _load(rpc, build_runner)
    picked = _pick_target_with_adjacent_enemy(state, board)
    if picked is None:
        pytest.skip("pas de cible avec ennemi adjacent (ni drivable)")
    caster, target, expected_splash = picked

    # SET attendu recalcule apres un eventuel drive de position (verite = voisins boardGraph INTER ennemis).
    ttile = _tile_of(board, state, target)
    neigh = set(board.neighbours(ttile))
    co_team = state.get_entity(caster).get_component(OwnerComponent).team
    enemies_adj = sorted(
        u for u, e in state.entities.items()
        if u not in (caster, target)
        and (e.get_component(OwnerComponent) or OwnerComponent(-1, -1)).team != co_team
        and (e.get_component(UnitComponent) or UnitComponent(None, False)).alive
        and _tile_of(board, state, u) in neigh)

    res = _apply_active_ability(state, caster, target, PLASMA_GRENADE)
    diag = (res or {}).get("diag") or {}
    # #149 slice-6 : PlasmaGrenade est un arbre DSL -> le diag expose `main_attack`/`splash` (chaque `attack`
    # porte un scalaire `hits` = nb de coups, cf. AttackDamageOperation.execute_ability_attack), PLUS de champs
    # scalaires `hits_main`/`hits_splash` (ancien retour imperatif `_splash_ability_behaviour`).
    main = diag.get("main_attack") or {}
    splash = diag.get("splash") or []
    splash_ids = sorted(x["target"] for x in splash)
    splash_hits = sorted({(x.get("attack") or {}).get("hits") for x in splash})
    print(f"\n[PLASMA] routed={res.get('routed')} hits_main={main.get('hits')} "
          f"splash_hits={splash_hits} splash={splash_ids} expected={enemies_adj}")

    assert res.get("routed") == "handler", f"1098 non route au handler : {res}"
    assert diag.get("main_attack") is not None, "attaque main absente"
    assert main.get("hits") == 2, f"hits main {main.get('hits')} != nrOfHits=2"
    for x in splash:                                                    # chaque volet splash = nrOfHits_2 = 1
        h = (x.get("attack") or {}).get("hits")
        assert h == 1, f"hits splash cible {x.get('target')} = {h} != nrOfHits_2=1"
    assert splash_ids == enemies_adj, \
        f"SET splash {splash_ids} != voisins boardGraph INTER ennemis {enemies_adj}"
    assert len(splash_ids) >= 1, "aucune cible splash (condition non remplie)"
