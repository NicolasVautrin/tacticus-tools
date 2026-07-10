"""#94 HealUnitOperation (mirror `HealUnitOperation$$Execute @180e733d0`) — validation du mutateur.

Le coeur = `FillUpStatComponent.FillUp @180f9b2e0` : `healed = min(amount, hp_max - hp)` ; `hp += healed` ;
rend `healed`. Gate heal-block `EffectType.Cursed(79)`. On charge un etat LIVE (unites reelles, stats
resolues), puis on teste le MUTATEUR sur l'etat offline (deterministe, la formule FillUp EST la verite RE).
ASCII-only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.heal import HealUnitOperation, CURSED
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.components import HealthComponent


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def test_heal_operation_fillup_cap(live_session, rpc, build_runner):
    """`FillUp` bit-exact : plein -> 0 ; partiel < manquant -> montant plein ; enorme -> cap au manquant ;
    Cursed(79) -> 0 (gate heal-block). Rend le montant REELLEMENT soigne."""
    rid = build_runner("777")["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob)):
        pytest.skip("state RPC KO")
    state = load_state(dv, ob, snap)

    victim = None
    for eid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp_max is not None and int(hc.hp_max) > 200:
            victim = (eid, hc)
            break
    if victim is None:
        pytest.skip("aucune unite avec hp/hp_max exploitable")
    eid, hc = victim
    hmax = int(hc.hp_max)

    # 1. cible PLEINE -> heal cap a 0 (rien a remplir).
    hc.hp = hmax
    assert HealUnitOperation.execute(state, eid, 9999) == 0
    assert hc.hp == hmax

    # 2. blessee de 100, heal 40 (< manquant) -> +40 exact.
    hc.hp = hmax - 100
    assert HealUnitOperation.execute(state, eid, 40) == 40
    assert hc.hp == hmax - 60

    # 3. heal enorme -> cap au manquant (60), hp==hmax.
    assert HealUnitOperation.execute(state, eid, 9999) == 60
    assert hc.hp == hmax

    # 4. montant <= 0 -> no-op.
    hc.hp = hmax - 50
    assert HealUnitOperation.execute(state, eid, 0) == 0
    assert HealUnitOperation.execute(state, eid, -10) == 0
    assert hc.hp == hmax - 50

    # 5. GATE heal-block EffectType.Cursed(79) : HasEffect(target, 0x4f) -> heal annule.
    if state.effects is not None:
        AddEffectOperation.execute(state, source=eid, target=eid, effect_type=CURSED, name="Cursed")
        assert state.effects.has_effect(eid, effect_type=CURSED)
        assert HealUnitOperation.execute(state, eid, 40) == 0
        assert hc.hp == hmax - 50            # inchange (Cursed bloque)

    print(f"\n[HEAL op] FillUp cap OK (hmax={hmax}) + Cursed(79) gate OK")
    HealUnitOperation  # keep import used
