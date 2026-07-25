"""#149 slice-9 : ValkyrieStrike (1018) MIGRATION replay-diff -- l'arbre DSL == l'ancien imperatif.

`IdunBattleLogic.Entities.Abilities.Active.Loki.ValkyrieStrikeAbility$$ExecuteBehaviour` (DECOMPILE) = plain `Execute` d'un SEUL noeud
`AddBondEffect(0x3fe=1022 ValkyrieStrike_Effect, AbilityStateReference, caster@0x160, target@0x178,
caster@0x160, dureeNode=ZERO, 0)` -- AUCUNE attaque immediate (le Blast nrOfHits=1 = PAYLOAD de l'airstrike
DIFFERE porte par l'effet 1022, hors ExecuteBehaviour). Le carrier natif (astraSmnVoxcaster) est SUMMON-only ;
l'effet 1022 est GLOBAL (config par type d'effet, PAS kit-derive) -> le REPLAY-DIFF est CASTER-AGNOSTIQUE : on
prend n'importe quel couple cross-team VIVANT (cible SANS effet 1022 pre-existant) et on confronte l'arbre
`valkyrie_strike_tree()` (via `ValkyrieStrikeAbility.execute_behaviour`) a l'ancien imperatif
`AddEffectOperation.execute(source=caster, target, 1022, SANS duration_override)`, sur DEUX etats INDEPENDANTS
de la MEME capture LIVE. Deterministe (aucun rng consomme) -> BIT-EXACT BY CONSTRUCTION : meme effet 1022 (+
eventuels sous-effets composites), meme source, meme remaining, meme parent. Verifie AUSSI le carve-out
None->DefaultAmountOfRounds de la feuille `AddBondEffect` (le tree passe duration_rounds=None). Lit l'etat LIVE,
aucune RVA/tuile hardcodee. ASCII-only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import OwnerComponent, UnitComponent
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.abilities.loki import ValkyrieStrikeAbility

VALK = 1022     # EffectType.ValkyrieStrike_Effect (0x3fe) -- airstrike differe
CASTER_VIS = "tyranTyrantGuard"     # player unit buildable (caster-agnostique : effet 1022 GLOBAL)
ENEMY_VIS = "necroWarden"
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", ENEMY_VIS]


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


def _eff_snapshot(state, uid):
    """Empreinte diffable des effets portes par `uid` : (effect_type, source, remaining_turns, parent_type)
    triee -> comparable BIT-EXACT entre deux etats."""
    lst = (state.effects.by_unit.get(uid) if state.effects is not None else None) or []
    return sorted((e.effect_type, e.source, e.remaining_turns, e.parent_type) for e in lst)


def test_valkyrie_strike_migration_matches_imperative(live_session, rpc, build_runner):
    """L'arbre DSL ValkyrieStrike (nœud unique AddBondEffect) reproduit l'ancien impératif
    (`AddEffectOperation.execute`) BIT-EXACT : même effet 1022 (+ sous-effets), même source, même remaining."""
    rid = build_runner("777", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not _ok(dv):
        pytest.skip("decisionView KO")

    # --- choisir un couple cross-team VIVANT dont la cible n'a PAS deja l'effet 1022 (sinon le gate
    #     deja-present d'AddEffectOperation no-op des DEUX cotes -> confront non-exerce). ---
    st_probe = load_state(dv, ob, snap)
    if st_probe.effects is None:
        pytest.skip("pas d'EffectsState materialise (combatSnapshot absent)")
    ids = list(st_probe.entities)
    caster_id = target_id = None
    for a in ids:
        if not _alive(st_probe, a):
            continue
        ta = _team(st_probe, a)
        for b in ids:
            if b == a or _team(st_probe, b) == ta or not _alive(st_probe, b):
                continue
            if not st_probe.effects.has_effect(b, effect_type=VALK):
                caster_id, target_id = a, b
                break
        if caster_id is not None:
            break
    if caster_id is None:
        pytest.skip("aucun couple cross-team vivant sans effet 1022 pre-existant")

    # --- DEUX etats INDEPENDANTS depuis la MEME capture, seedes identiquement (aucun rng consomme par
    #     ValkyrieStrike -- seed pour parite stricte) -> arbre DSL vs imperatif. ---
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    st_dsl = load_state(dv, ob, snap)
    st_imp = load_state(dv, ob, snap)
    if _ok(s0):
        st_dsl.rng = _seed_rng(s0); st_imp.rng = _seed_rng(s0)

    # [DSL] l'arbre migre (via la classe d'ability)
    res = ValkyrieStrikeAbility().execute_behaviour(st_dsl, caster_id, target_id)
    assert res is not None and res.get("dsl") is True, f"arbre DSL non execute: {res}"
    assert res.get("immediate_attack") is None, "ValkyrieStrike ne doit PAS attaquer au cast (airstrike differe)"
    assert res.get("deferred_effect") == VALK, f"deferred_effect attendu {VALK}, recu {res.get('deferred_effect')}"

    # [IMPERATIF] l'ancien corps = un SEUL AddEffectOperation.execute (source=caster, cible, 1022, SANS override)
    AddEffectOperation.execute(st_imp, source=caster_id, target=target_id,
                               effect_type=VALK, name="ValkyrieStrike_Effect")

    dsl_eff = _eff_snapshot(st_dsl, target_id)
    imp_eff = _eff_snapshot(st_imp, target_id)
    print(f"\n[VALKYRIE migration] caster={caster_id} target={target_id}")
    print(f"[VALKYRIE migration] dsl={dsl_eff}")
    print(f"[VALKYRIE migration] imp={imp_eff}")

    # 0) l'arbre DSL a REELLEMENT pose l'effet 1022 (feuille cablee + None-duree geree sans crash)
    assert any(e[0] == VALK for e in dsl_eff), f"effet 1022 non pose par l'arbre DSL: {dsl_eff}"
    # 1) DSL == imperatif BIT-EXACT (meme effet 1022 + memes sous-effets, meme source, meme remaining, meme parent)
    assert dsl_eff == imp_eff, f"effets DSL {dsl_eff} != imperatif {imp_eff}"
