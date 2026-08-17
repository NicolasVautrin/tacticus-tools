"""#149 slice-6 : PlasmaGrenade (1098) MIGRATION replay-diff -- l'arbre DSL == l'imperatif, BIT-EXACT.

`IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaGrenadeAbility$$ExecuteBehaviour` (DECOMPILE) =
    Execute( op_Addition(
        AttackWithAbilityDamage(caster, target, RandomAmount(minDmg/maxDmg), Plasma, nrOfHits=0x2f),
        AttackWithAbilityDamage(caster, Enemies(caster, AdjacentUnits(target,1)), MEME RandomAmount,
                                Plasma, nrOfHits_2=0x32) ) )
Le SPLASH natif = UN SEUL `AttackWithAbilityDamage` avec un SELECTEUR MULTI-cible (PAS un Foreach) :
`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` resout la liste + `OrderBy` (cle par-unite = ordre de lecture) puis
attaque chaque cible. Porte via le mode `multi=True` de la feuille (tri par id = ordre de lecture natif ==
l'ordre `sorted` de l'imperatif).

Le caster natif (eldarSmnGuardian) est SUMMON-only (hors pool runner) -> PAS de cast live direct
(caster-agnostique : la config PlasmaGrenade est GLOBALE, scale par le level du caster). On valide la MIGRATION par
REPLAY-DIFF sur un etat LIVE captured : l'arbre `plasma_grenade_tree()` (via `PlasmaGrenadeAbility.
execute_behaviour`) doit reproduire BIT-EXACT l'ancien imperatif `_splash_ability_behaviour` (meme set splash,
main + splash per-coup) sous le MEME `state.rng` seede. Le selecteur splash `AdjacentEnemies` est deja
CONFRONTE LIVE en slice-4 (CrushingClaws). Lit l'etat LIVE. ASCII-only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, OwnerComponent, UnitComponent
from engine.runner.abilities.loki import (PlasmaGrenadeAbility, _splash_ability_behaviour,
                                          _adjacent_enemies_of)
from engine.entities.pathfinding.board import Board

CASTER_VIS = "eldarFarseer"                 # n'importe quel player unit buildable : la diff compare la
                                            # MECANIQUE (l'arbre vs l'imperatif lisent le MEME config PlasmaGrenade)
BUILD = ["--roster", "1", "--p-units", CASTER_VIS,
         "--a-units", "necroWarden,necroDestroyer,necroSpyder,necroOverlord"]   # ennemis clusterises -> splash


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


def _visual(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.visual_id if uc is not None else None


def _per_hit(atk):
    return (atk or {}).get("per_hit")


def test_plasma_grenade_migration_matches_imperative(live_session, rpc, build_runner):
    """L'arbre DSL PlasmaGrenade reproduit l'ancien impératif `_splash_ability_behaviour` BIT-EXACT :
    même set splash, même main per-coup, même splash per-coup, sous le MÊME RNG seedé."""
    rid = build_runner("777", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    # native_sym = adjacence unite-unite CORRECTE (mirror natif ; PAS le boardGraph brut qui exclut les
    # tuiles occupees, piege #148). Requis par l'imperatif `_adjacent_enemies_of` (board.neighbours).
    board = Board(bg["tiles"], adjacency="native_sym")

    # --- Trouver un couple (caster player, cible ennemie) ou l'imperatif (board) ET le DSL (hexgeo) donnent
    #     le MEME splash NON VIDE (>=1 ennemi-du-caster vivant adjacent a la cible). Board plat -> concordent.
    st0 = load_state(dv, ob, snap, board=board)
    caster_id = next((eid for eid in st0.entities
                      if _visual(st0, eid) == CASTER_VIS and _alive(st0, eid)
                      and st0.get_entity(eid).get_component(StatsComponent) is not None), None)
    if caster_id is None:
        pytest.skip("caster (StatsComponent) introuvable offline")
    cteam = _team(st0, caster_id)
    pair = None
    for tid in st0.entities:
        if _team(st0, tid) == cteam or not _alive(st0, tid):
            continue
        if _adjacent_enemies_of(st0, caster_id, tid):        # >=1 splash (board)
            pair = tid
            break
    if pair is None:
        pytest.skip("aucune cible ennemie avec voisin ennemi (pas de splash a tester)")
    target_id = pair

    # --- DEUX etats INDEPENDANTS depuis la MEME capture, MEME board + seedes IDENTIQUEMENT -> arbre vs imperatif.
    st_dsl = load_state(dv, ob, snap, board=board); st_dsl.rng = _seed_rng(s0)
    st_imp = load_state(dv, ob, snap, board=board); st_imp.rng = _seed_rng(s0)

    # [DSL] l'arbre migre (via la classe d'ability)
    res_dsl = PlasmaGrenadeAbility().execute_behaviour(st_dsl, caster_id, target_id)
    assert res_dsl is not None and res_dsl.get("dsl") is True, f"arbre DSL non execute: {res_dsl}"
    dsl_main = _per_hit(res_dsl.get("main_attack"))
    dsl_splash = {s["target"]: _per_hit(s["attack"]) for s in (res_dsl.get("splash") or [])}

    # [IMPERATIF] la mecanique partagee _splash_ability_behaviour + _adjacent_enemies_of (ancien chemin)
    imp_set = _adjacent_enemies_of(st_imp, caster_id, target_id)
    # rngcrit-1202 : PlasmaGrenade = factory native IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage (XREFS) ->
    # AbilityDamageOperation, 1 tirage/coup SANS resolve gaspille -> l'oracle imperatif doit passer
    # la MEME famille que l'arbre DSL (native_factory="ability").
    res_imp = _splash_ability_behaviour(st_imp, caster_id, target_id, "PlasmaGrenade", "Plasma",
                                        ranged=True, splash_set=imp_set, is_attack_damage_op=False)
    imp_main = _per_hit(res_imp.get("main_attack"))
    imp_splash = {s["target"]: _per_hit(s["attack"]) for s in (res_imp.get("splash") or [])}

    print(f"\n[PLASMA migration] caster={caster_id} target={target_id} "
          f"splash_dsl={sorted(dsl_splash)} splash_imp={sorted(imp_splash)}")
    print(f"[PLASMA migration] main dsl={dsl_main} imp={imp_main}")
    for tid in sorted(set(dsl_splash) | set(imp_splash)):
        print(f"[PLASMA migration] splash {tid}: dsl={dsl_splash.get(tid)} imp={imp_splash.get(tid)}")

    # 1) MEME set splash (le selecteur DSL Alive(AdjacentEnemies(TargetTile())) == l'imperatif _adjacent_enemies_of)
    assert set(dsl_splash) == set(imp_splash), (
        f"set splash DSL {sorted(dsl_splash)} != imperatif {sorted(imp_splash)}")
    # 2) MAIN per-coup BIT-EXACT
    assert dsl_main == imp_main, f"main per-coup DSL {dsl_main} != imperatif {imp_main}"
    # 3) SPLASH per-coup BIT-EXACT par cible
    for tid in sorted(set(dsl_splash) | set(imp_splash)):
        assert dsl_splash.get(tid) == imp_splash.get(tid), (
            f"splash per-coup cible {tid} DSL {dsl_splash.get(tid)} != imperatif {imp_splash.get(tid)}")
