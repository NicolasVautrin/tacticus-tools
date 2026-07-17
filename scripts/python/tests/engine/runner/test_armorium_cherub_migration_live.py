"""#149 slice-7 : ArmoriumCherub (1014) MIGRATION replay-diff -- l'arbre DSL == l'ancien imperatif, BIT-EXACT.

`ArmoriumCherubAbility.ExecuteBehaviour @1811b4000` (DECOMPILE) =
    ExecuteAtomic( op_and(
        AttackWithAttackDamage(caster, target, MinMaxDamage(minDmg 0xc/maxDmg 0xd), Flame, nrOfHits=0x2f=4),
        EvaluateAbilities(0x4b=AttackInAtomicGroup) ) )
Le 2e nœud `EvaluateAbilities(AttackInAtomicGroup)` = `EvaluateAbilitiesBehaviour @180fc48a0` : EVALUE les
passifs declenches du caster pour cet event -> `FireOfAbsolution` (splash 3x Flame + Maybe ignite). Porte via
la feuille `EvaluateAbilities` + le dispatch `evaluate_abilities_for_event` (AttackInAtomicGroup ->
`_fire_of_absolution_after_attack`).

Caster = adeptRetributor «Vindicta» (BUILDABLE, porte le passif FireOfAbsolution + l'actif ArmoriumCherub) :
on exerce REELLEMENT le splash. On valide la MIGRATION par REPLAY-DIFF -- l'arbre `armorium_cherub_tree()`
(via `ArmoriumCherubAbility.execute_behaviour`) reproduit BIT-EXACT l'ANCIEN corps imperatif (main attack via
`execute_ability_attack` + passif via `_fire_of_absolution_after_attack`) sous le MEME `state.rng` seede, sur
DEUX etats INDEPENDANTS issus de la MEME capture LIVE. Lit l'etat LIVE. ASCII-only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, OwnerComponent, UnitComponent
from engine.runner.abilities.loki import ArmoriumCherubAbility, _adjacent_enemies_of
from engine.runner.abilities.base import ability_attack_params
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.triggers import _fire_of_absolution_after_attack
from engine.entities.pathfinding.board import Board

CASTER_VIS = "adeptRetributor"              # «Vindicta» : porte FireOfAbsolution (passif) + ArmoriumCherub (actif)
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


def _splash_map(passive):
    """{splash_target -> per_hit} depuis la liste retournee par _fire_of_absolution_after_attack."""
    out = {}
    for p in (passive or []):
        for s in (p.get("splash") or []):
            out[s["target"]] = _per_hit(s["attack"])
    return out


def _ignited(passive):
    out = set()
    for p in (passive or []):
        out |= set(p.get("ignited_tiles") or [])
    return out


def _imperative(state, caster_id, target_id):
    """Corps EXACT de l'ANCIEN `ArmoriumCherubAbility.execute_behaviour` (avant migration) : attaque d'ability
    4x Flame + passif FireOfAbsolution inline, ranged=True."""
    bmin, bmax, pierce, hits = ability_attack_params(state, caster_id, "ArmoriumCherub", "Flame", ranged=True)
    main = AttackDamageOperation.execute_ability_attack(
        state, caster_id, target_id, bmin, bmax, pierce, hits, damage_profile="Flame", is_melee=False)
    passive = _fire_of_absolution_after_attack(state, caster_id, target_id, ranged=True)
    return {"main_attack": main, "fire_of_absolution": passive}


def test_armorium_cherub_migration_matches_imperative(live_session, rpc, build_runner):
    """L'arbre DSL ArmoriumCherub reproduit l'ancien impératif (main 4x Flame + passif FireOfAbsolution)
    BIT-EXACT : même main per-coup, même set/per-coup de splash, mêmes tuiles ignitées, sous le MÊME RNG seedé."""
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
    # tuiles occupees, piege #148). Requis par `_adjacent_enemies_of` (state.board.neighbours).
    board = Board(bg["tiles"], adjacency="native_sym")

    st0 = load_state(dv, ob, snap); st0.board = board
    if st0.effects is None:
        pytest.skip("EffectsState non charge (combatSnapshot absent) -> gate FireOfAbsolution KO")
    caster_id = next((eid for eid in st0.entities
                      if _visual(st0, eid) == CASTER_VIS and _alive(st0, eid)
                      and st0.get_entity(eid).get_component(StatsComponent) is not None), None)
    if caster_id is None:
        pytest.skip("caster adeptRetributor (StatsComponent) introuvable offline")
    cteam = _team(st0, caster_id)
    # cible ENNEMIE avec >=1 ennemi-du-caster adjacent (splash FireOfAbsolution NON VIDE = chemin exerce).
    pair = None
    for tid in st0.entities:
        if _team(st0, tid) == cteam or not _alive(st0, tid):
            continue
        if _adjacent_enemies_of(st0, caster_id, tid):
            pair = tid
            break
    if pair is None:
        pytest.skip("aucune cible ennemie avec voisin ennemi (splash FireOfAbsolution non exercable)")
    target_id = pair

    # DEUX etats INDEPENDANTS depuis la MEME capture, MEME board, seedes IDENTIQUEMENT -> arbre vs imperatif.
    st_dsl = load_state(dv, ob, snap); st_dsl.board = board; st_dsl.rng = _seed_rng(s0)
    st_imp = load_state(dv, ob, snap); st_imp.board = board; st_imp.rng = _seed_rng(s0)

    # [DSL] l'arbre migre (via la classe d'ability)
    res_dsl = ArmoriumCherubAbility().execute_behaviour(st_dsl, caster_id, target_id)
    assert res_dsl is not None and res_dsl.get("dsl") is True, f"arbre DSL non execute: {res_dsl}"
    dsl_main = _per_hit(res_dsl.get("main_attack"))
    dsl_splash = _splash_map(res_dsl.get("fire_of_absolution"))
    dsl_ign = _ignited(res_dsl.get("fire_of_absolution"))

    # [IMPERATIF] l'ancien corps (attaque d'ability + passif inline)
    res_imp = _imperative(st_imp, caster_id, target_id)
    imp_main = _per_hit(res_imp.get("main_attack"))
    imp_splash = _splash_map(res_imp.get("fire_of_absolution"))
    imp_ign = _ignited(res_imp.get("fire_of_absolution"))

    print(f"\n[ARMORIUM migration] caster={caster_id} target={target_id}")
    print(f"[ARMORIUM migration] main dsl={dsl_main} imp={imp_main}")
    print(f"[ARMORIUM migration] splash dsl={ {k: dsl_splash[k] for k in sorted(dsl_splash)} } "
          f"imp={ {k: imp_splash[k] for k in sorted(imp_splash)} }")
    print(f"[ARMORIUM migration] ignited dsl={sorted(dsl_ign)} imp={sorted(imp_ign)}")

    # 0) le passif FireOfAbsolution a REELLEMENT fire (splash non vide) -> chemin EvaluateAbilities exerce
    assert imp_splash, "splash FireOfAbsolution vide cote imperatif -> chemin EvaluateAbilities non exerce"
    # 1) MAIN per-coup BIT-EXACT (feuille AttackWithAbilityDamage == execute_ability_attack imperatif)
    assert dsl_main == imp_main, f"main per-coup DSL {dsl_main} != imperatif {imp_main}"
    # 2) MEME set + per-coup de splash (EvaluateAbilities(AttackInAtomicGroup) == _fire_of_absolution inline)
    assert dsl_splash == imp_splash, f"splash DSL {dsl_splash} != imperatif {imp_splash}"
    # 3) MEMES tuiles ignitees (meme conso RNG Maybe -> bit-exact)
    assert dsl_ign == imp_ign, f"ignited DSL {sorted(dsl_ign)} != imperatif {sorted(imp_ign)}"
