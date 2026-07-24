"""#149 slice-13 : Fragstorm (1078, templSmnAggressor) MIGRATION vers l'arbre DSL.

`FragstormAbility.ExecuteBehaviour @1811e0a00` (DECOMPILE) = `ExecuteAtomic(op_BitwiseAnd(main, splash))` :
    main   = AttackWithAttackDamage(caster, target, RandomAmount, Blast, nrOfHits=4)
    splash = AttackWithAttackDamage(caster,
                 PickRandomly(AdjacentTiles(target) - Tiles(Friends(caster)), nrOfTargets=4),
                 RandomAmount, Blast, nrOfHits_2=2)
Le splash SOUSTRAIT explicitement les tuiles a AMI-DU-CASTER (i2 « ... to up to 4 random hexes adjacent to the
target, excluding hexes with friendly units ») -> ENEMIES-ONLY, a la DIFFERENCE de Stikkbomb (`AdjacentUnits`
BRUT = friendly-fire). Porte = `Alive(Sub(AdjacentUnits(TargetTile()), AdjacentFriends(TargetTile())))` +
`pick_n=4` folde le PickRandomly dans la feuille.

On exerce l'ability avec un caster PROXY buildable (le vrai carrier Fragstorm = templSmnAggressor summon,
non-buildable en lineup ; l'exclusion des amis ne depend que de l'ability + geometrie). On DRIVE un ALLIE du
caster ET un ENNEMI adjacents a la cible, on caste, et on verifie que le splash touche l'ENNEMI mais JAMAIS
l'allie (== enemies-only, l'INVERSE de Stikkbomb). Robuste au RNG du pick (subset + cap 4). Lit l'etat LIVE.
ASCII-only. NON committe (tests confront live, hors depot).
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent, OwnerComponent, UnitComponent
from engine.runner.abilities.loki import FragstormAbility

# caster PROXY + unites = lineup buildables (le carrier Fragstorm reel = summon non buildable ; l'exclusion
# des amis du splash ne depend PAS du kit du caster, seulement de l'ability + geometrie).
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


def _alive(state, uid):
    uc = state.get_entity(uid).get_component(UnitComponent)
    return uc.alive if uc is not None else True


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


def test_fragstorm_migration_enemies_only(live_session, rpc, build_runner):
    """`FragstormAbility.execute_behaviour` prend le chemin DSL (`fragstorm_tree`) et le splash EXCLUT les
    amis du caster : l'ENNEMI adjacent a la cible est touche, l'ALLIE adjacent ne l'est JAMAIS (== enemies-only,
    l'INVERSE du friendly-fire Stikkbomb)."""
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
    if ally is None or target is None or enemy2 is None:
        pytest.skip("besoin d'un allie du caster + une cible ennemie + un 2e ennemi")

    occupied = {_pos(state, i) for i in live_ids if _pos(state, i) is not None}
    occupied.discard(_pos(state, ally))
    assert _drive_adjacent(state, board, ally, target, occupied), "impossible de DRIVE l'allie adjacent a la cible"
    occupied.discard(_pos(state, enemy2))
    assert _drive_adjacent(state, board, enemy2, target, occupied), "impossible de DRIVE l'ennemi adjacent a la cible"

    # candidats ATTENDUS = ennemis-du-caster (team != caster) VIVANTS adjacents (hex 1) a la cible, hors cible/caster
    tp = _pos(state, target)
    enemy_cands = sorted(
        i for i in live_ids if i not in (target, caster_id) and _team(state, i) != ctm
        and _pos(state, i) is not None and hexgeo.distance(_pos(state, i), tp) == 1 and _alive(state, i))
    assert enemy2 in enemy_cands, "l'ennemi drive n'est pas dans les candidats adjacents (setup)"
    assert ally not in enemy_cands, "setup incoherent : l'allie ne doit pas etre un candidat ennemi"

    # restaure les PV a plein sur cible + candidats (evite l'overkill qui masque un coup)
    for i in [target] + enemy_cands + [ally]:
        hc = state.get_entity(i).get_component(HealthComponent)
        if hc is not None:
            hc.hp = hc.hp_max
    ally_hp0 = state.get_entity(ally).get_component(HealthComponent).hp

    # === chemin DSL migre ===
    res = FragstormAbility().execute_behaviour(state, caster_id, target)
    splash_ids = sorted((x.get("target") for x in (res.get("splash") or [])))
    print(f"\n[FRAGSTORM migration] dsl={res.get('dsl')} main_hits={(res.get('main_attack') or {}).get('hits')} "
          f"splash={splash_ids} enemy_cands={enemy_cands} ally={ally}(team{ctm})")

    assert res.get("dsl") is True, f"arbre DSL non pris: {res}"
    assert (res.get("main_attack") or {}).get("hits") == 4, \
        f"main hits {(res.get('main_attack') or {}).get('hits')} != nrOfHits=4"
    # ENEMIES-ONLY : chaque cible splash est un ennemi-du-caster adjacent (JAMAIS un ami)
    assert set(splash_ids).issubset(set(enemy_cands)), \
        f"splash {splash_ids} deborde des ennemis adjacents {enemy_cands} (friendly-fire indu ?)"
    assert ally not in splash_ids, "FIDELITE : l'allie du caster (ami) est dans le splash -> friendly-fire indu"
    # cap PickRandomly(4) : exactement min(#candidats, 4) cibles
    assert len(splash_ids) == min(len(enemy_cands), 4), \
        f"splash {len(splash_ids)} != min(#cands {len(enemy_cands)}, 4)"
    for x in (res.get("splash") or []):
        h = (x.get("attack") or {}).get("hits")
        assert h == 2, f"splash cible {x.get('target')} hits {h} != nrOfHits_2=2"
    # l'allie n'a PERDU AUCUN PV (enemies-only effectif)
    ally_hp1 = state.get_entity(ally).get_component(HealthComponent).hp
    assert ally_hp1 == ally_hp0, f"l'allie a subi du degat ({ally_hp0}->{ally_hp1}) -> friendly-fire indu"
