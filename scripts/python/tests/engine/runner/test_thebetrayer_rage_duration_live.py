"""#149 slice-17 : TheBetrayer_AddEffect (rage 0x4f3 de worldKharn) MIGRATION vers l'arbre DSL
`betrayer_add_effect_tree()` (mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_AddEffectAbility$$CreateBehaviour`).

Valide la CORRECTION DE DUREE (RE IdunBattle.Operations.AddEffectOperation$$Execute). Arbre natif = `AddEffect(0x4f3, source=AbilityStateReference,
target=Self@0x148)`. La feuille `AddEffect` route vers `AddEffectOperation.execute` -> durée =
`DefaultAmountOfRounds(0x4f3)`=null (switch idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds sans 0x4f3) -> FALLBACK 1 (RE IdunBattle.Operations.AddEffectOperation$$Execute :
`EffectComponent.Duration@+0x68 = local_588[0]`, et `local_588[0] = 1` quand l'override Nullable est null).
=> la rage native dure **1 TOUR**, re-accordée à chaque kill -- PAS permanente. L'ancien port posait un
`BaseEffect` PERMANENT (remaining_turns=None) : DIVERGENCE LATENTE que ce mirror corrige.

Ce test confirme, sur un état LIVE, que le nouveau `_add_betrayer_effect` crée la rage avec
`remaining_turns == 1` (et source/target = le porteur), i.e. la duree native RE-confirmee -- PAS le marqueur
permanent d'avant. ASCII-only. NON committe (tests confront live, hors depot)."""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.components import UnitComponent, StatsComponent
from engine.runner.operations.triggers import THEBETRAYER_EFFECT, _add_betrayer_effect

KHARN = "worldKharn"
BUILD = ["--roster", "1", "--p-units", "worldKharn",
         "--a-units", "necroWarden,necroOverlord,necroWarden"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _visual(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.visual_id if uc is not None else None


def test_thebetrayer_rage_duration_is_one_turn(live_session, rpc, build_runner):
    """Le nouveau `_add_betrayer_effect` (arbre DSL AddEffect(0x4f3, Caster())) crée la rage avec
    `remaining_turns == 1` (RE IdunBattle.Operations.AddEffectOperation$$Execute : fallback 1), source/target = le porteur -- PAS le marqueur
    PERMANENT (remaining_turns=None) de l'ancien port."""
    rid = build_runner("777", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    state = load_state(dv, ob, snap)
    if state.effects is None:
        pytest.skip("EffectsState non charge (combatSnapshot absent)")
    kid = next((eid for eid in state.entities
                if _visual(state, eid) == KHARN
                and state.get_entity(eid).get_component(StatsComponent) is not None), None)
    if kid is None:
        pytest.skip("worldKharn (StatsComponent) introuvable offline")
    if state.effects.has_effect(kid, effect_type=THEBETRAYER_EFFECT):
        pytest.skip("Kharn a deja la rage 0x4f3 dans la capture -> pose non exercable proprement")

    res = _add_betrayer_effect(state, kid)
    rage = [e for e in state.effects.by_unit.get(int(kid), [])
            if e.effect_type == THEBETRAYER_EFFECT and not e.consumed]
    print(f"\n[BETRAYER dur] res={res} rage={[(e.name, e.remaining_turns, e.source, e.target) for e in rage]}")

    # 1. la rage a bien ete posee.
    assert rage, f"rage 0x4f3 non posee (res={res})"
    # 2. DUREE = 1 tour (RE IdunBattle.Operations.AddEffectOperation$$Execute : DefaultAmountOfRounds(0x4f3)=null -> fallback 1), PAS permanent (None).
    assert rage[0].remaining_turns == 1, \
        f"duree rage {rage[0].remaining_turns} != 1 (RE IdunBattle.Operations.AddEffectOperation$$Execute fallback 1 ; ancien port = permanent None)"
    # 3. source ET target = le porteur (AbilityStateReference source + Self@0x148 target).
    assert rage[0].source == kid, f"source rage {rage[0].source} != porteur {kid}"
    assert rage[0].target == kid, f"target rage {rage[0].target} != porteur {kid}"
