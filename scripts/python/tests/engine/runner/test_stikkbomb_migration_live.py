"""#149 slice-12 : Stikkbomb (1051, Ork Boy) MIGRATION vers l'arbre DSL + FIX friendly-fire (#213).

`IdunBattleLogic.Entities.Abilities.Active.Loki.StikkbombAbility$$ExecuteBehaviour` (DECOMPILE) = `Execute(AtomicGroup(op_Addition(main, splash)))` :
    main   = AttackWithAttackDamage(caster, target, RandomAmount, Blast, nrOfHits=2)
    splash = AttackWithAttackDamage(caster, AdjacentUnits(target,1,3), RandomAmount, Blast, nrOfHits_2=1)
Le splash passe `AdjacentUnits(target,1,3)` BRUT -- SANS wrapper `Enemies(...)` (contraste PlasmaGrenade
`Enemies(caster, AdjacentUnits(...))` et Fragstorm `AdjacentTiles - Tiles(Friends(...))`). DECOMPILE + i2
concordants (Stikkbomb = « units in hexes adjacent », les 3 autres = « enemy units »/« excluding friendly
hexes ») => FRIENDLY-FIRE : le splash touche TOUTES les unites adjacentes a la cible, ALLIES DU CASTER INCLUS.

La FRIENDLY-FIRE est une propriete du SELECTEUR de l'ability (config-driven `AdjacentUnits`), PAS du kit du
caster -> le vrai carrier (Ork Boy = orksNpc2OrkBoy NPC / orksOrkBoys summon) n'etant PAS buildable en lineup,
on exerce l'ability behaviour avec un caster PROXY buildable (le splash ne depend que de l'ability + geometrie).
On DRIVE un ALLIE du caster (meme team) ET un ennemi adjacents a la cible, on caste, et on verifie que le splash
touche LES DEUX = exactement l'ensemble des unites a distance hex 1 de la cible (AUCUN filtre team), l'allie du
caster INCLUS. Lit l'etat LIVE. ASCII-only. NON committe (tests confront live, hors depot).
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent, OwnerComponent, UnitComponent
from engine.runner.abilities.loki import StikkbombAbility

# caster PROXY + ennemis = unites lineup buildables (le carrier Stikkbomb reel = Ork Boy NPC/summon, non buildable ;
# le splash friendly-fire ne depend PAS du kit du caster, seulement de l'ability + geometrie).
BUILD = ["--roster", "1", "--p-units", "necroSpyder,necroDestroyer",
         "--a-units", "necroSpyder,necroDestroyer"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _pos(state, uid):
    pc = state.get_entity(uid).get_component(PositionComponent)
    return (pc.col, pc.row) if pc is not None else None


def _team(state, uid):
    oc = state.get_entity(uid).get_component(OwnerComponent)
    return oc.team if oc is not None else None


def _drive_adjacent(state, board, unit_id, target_id, occupied):
    """DRIVE `unit_id` sur une tuile LIBRE a distance hex 1 de `target_id` (hexgeo = adjacence PURE, pas
    board.neighbours qui exclut l'occupe). Renvoie True si place."""
    tp = _pos(state, target_id)
    for tid, info in board.by_id.items():
        cell = (info["col"], info["row"])
        if cell in occupied or not board.walkable(tid):
            continue
        if hexgeo.distance(cell, tp) == 1:
            pc = state.get_entity(unit_id).get_component(PositionComponent)
            pc.col, pc.row = info["col"], info["row"]
            occupied.add(cell)
            return True
    return False


def test_stikkbomb_migration_friendly_fire(live_session, rpc, build_runner):
    """`StikkbombAbility.execute_behaviour` prend le chemin DSL (`stikkbomb_tree`) et le splash FRIENDLY-FIRE :
    allie-du-caster + ennemi adjacents a la cible sont TOUS DEUX touches (== toutes les unites a dist 1)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("rng absent")

    state = load_state(dec, ob, snap, board=board)
    state.rng = _seed_rng(s0)

    live_ids = [u["id"] for u in (dec.get("units") or []) if state.get_entity(u["id"]) is not None]
    if len(live_ids) < 3:
        pytest.skip("besoin d'au moins 3 unites")
    # caster PROXY = 1re unite ; allie = meme team (!= caster) ; cible = autre team ; enemy2 = autre team (!= cible)
    caster_id = live_ids[0]
    ctm = _team(state, caster_id)
    ally = next((i for i in live_ids if i != caster_id and _team(state, i) == ctm), None)
    target = next((i for i in live_ids if _team(state, i) != ctm), None)
    enemy2 = next((i for i in live_ids if i != target and _team(state, i) != ctm), None)
    if ally is None or target is None:
        pytest.skip("besoin d'un allie du caster + une cible ennemie")

    occupied = {_pos(state, i) for i in live_ids if _pos(state, i) is not None}
    occupied.discard(_pos(state, ally))
    assert _drive_adjacent(state, board, ally, target, occupied), "impossible de DRIVE l'allie adjacent a la cible"
    if enemy2 is not None:
        occupied.discard(_pos(state, enemy2))
        _drive_adjacent(state, board, enemy2, target, occupied)   # best-effort (2e ennemi adjacent)

    # ensemble ATTENDU = toutes les unites VIVANTES a distance hex 1 de la cible (AUCUN filtre team), hors cible
    tp = _pos(state, target)
    expected_splash = sorted(
        i for i in live_ids if i != target
        and _pos(state, i) is not None and hexgeo.distance(_pos(state, i), tp) == 1
        and (state.get_entity(i).get_component(UnitComponent) or UnitComponent(None, False)).alive)
    assert ally in expected_splash, "l'allie n'a pas ete drive adjacent (setup)"

    # restaure les PV a plein sur cible + splash (evite l'overkill qui masque un coup)
    for i in [target] + expected_splash:
        hc = state.get_entity(i).get_component(HealthComponent)
        if hc is not None:
            hc.hp = hc.hp_max

    # === chemin DSL migre ===
    res = StikkbombAbility().execute_behaviour(state, caster_id, target)
    splash_ids = sorted((x.get("target") for x in (res.get("splash") or [])))
    print(f"\n[STIKKBOMB migration] dsl={res.get('dsl')} main_hits={(res.get('main_attack') or {}).get('hits')} "
          f"splash={splash_ids} expected={expected_splash} ally={ally}(team{ctm})")

    assert res.get("dsl") is True, f"arbre DSL non pris: {res}"
    assert (res.get("main_attack") or {}).get("hits") == 2, \
        f"main hits {(res.get('main_attack') or {}).get('hits')} != nrOfHits=2"
    # FRIENDLY-FIRE : le splash == TOUTES les unites adjacentes (allie du caster INCLUS), AUCUN filtre team
    assert splash_ids == expected_splash, f"splash {splash_ids} != adjacents-toutes-teams {expected_splash}"
    assert ally in splash_ids, "FRIENDLY-FIRE NON reproduit : l'allie du caster n'est PAS dans le splash"
    for x in (res.get("splash") or []):
        h = (x.get("attack") or {}).get("hits")
        assert h == 1, f"splash cible {x.get('target')} hits {h} != nrOfHits_2=1"
    # l'allie (meme team que le caster) a bien perdu des PV = friendly-fire effectif
    ally_hc = state.get_entity(ally).get_component(HealthComponent)
    assert ally_hc.hp < ally_hc.hp_max, "l'allie n'a pas subi de degat (friendly-fire non effectif)"
