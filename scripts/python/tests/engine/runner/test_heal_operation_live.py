"""#94 / #520 `HealUnitOperation` (mirror `IdunBattle.Operations.HealUnitOperation$$Execute`).

Le coeur = `IdunBattle.Entities.Components.FillUpStatComponent$$FillUp` : `healed = min(amount,
hp_max - hp)` ; `hp += healed` ; rend `healed`. Gate heal-block `EffectType.Cursed(79)`.

#520 a ajoute les DEUX etages que l'Operation n'avait pas -- le gate
`IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed` (slot 0x11, en TETE de l'Operation) et
`IdunBattle.Core.Services.DamagePrediction$$PredictHeal` (slot 1 de la `DamagePredictionQuery`). Ce
fichier garde les deux, et sa VICTIME est desormais choisie PAR LE GATE au lieu d'etre la premiere
unite venue : une cible MECANIQUE n'est pas soignable, et le test qui la prenait au hasard mesurait
donc un chemin que le natif refuse.

On charge un etat LIVE (unites reelles, stats resolues), puis on teste le MUTATEUR sur l'etat
offline (deterministe, la formule FillUp EST la verite RE). ASCII-only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.heal import HealUnitOperation, predict_heal, CURSED
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.abilities.attack_query import entity_can_be_healed
from engine.runner.components import HealthComponent


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _state(rid, rpc):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob)):
        pytest.skip("state RPC KO")
    return load_state(dv, ob, snap)


def _victimes(state):
    """Ventile les unites du state en SOIGNABLES / NON SOIGNABLES selon le gate natif.

    La cible est blessee artificiellement (hp = hp_max - 1) AVANT d'interroger le gate : sans PV
    manquants, `AttackQuery$$IsDamagedUnit` est faux pour TOUT LE MONDE et la ventilation serait
    degeneree -- un accord en regime degenere ne prouve rien."""
    ok, ko = [], []
    for eid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is None or hc.hp is None or hc.hp_max is None or int(hc.hp_max) <= 200:
            continue
        garde = int(hc.hp)
        hc.hp = int(hc.hp_max) - 1
        (ok if entity_can_be_healed(state, eid, eid, scope=0, remove_effects=True)
         else ko).append(eid)
        hc.hp = garde
    return ok, ko


def test_heal_operation_fillup_cap(live_session, rpc, build_runner):
    """`FillUp` bit-exact sur une cible que le GATE accepte : plein -> 0 ; partiel < manquant ->
    montant plein ; enorme -> cap au manquant ; Cursed(79) -> 0 (gate heal-block)."""
    rid = build_runner("777")["rid"]
    state = _state(rid, rpc)
    soignables, _ = _victimes(state)
    if not soignables:
        pytest.skip("aucune unite SOIGNABLE (gate EntityCanBeHealed) avec hp/hp_max exploitable")
    eid = soignables[0]
    hc = state.get_entity(eid).get_component(HealthComponent)
    hmax = int(hc.hp_max)

    # 1. cible PLEINE -> le gate lui-meme refuse (`IsDamagedUnit` faux, et aucun des trois autres
    #    disjuncts n'est lisible offline) : 0 PV, et surtout AUCUNE mutation.
    hc.hp = hmax
    assert HealUnitOperation.execute(state, eid, eid, 9999) == 0
    assert hc.hp == hmax

    # 2. blessee de 100, heal 40 (< manquant) -> +40 exact.
    hc.hp = hmax - 100
    assert HealUnitOperation.execute(state, eid, eid, 40) == 40
    assert hc.hp == hmax - 60

    # 3. heal enorme -> cap au manquant (60), hp==hmax  (`PredictHeal` -> `MaxFillUp`).
    assert HealUnitOperation.execute(state, eid, eid, 9999) == 60
    assert hc.hp == hmax

    # 4. montant NUL -> aucun PV bouge.
    hc.hp = hmax - 50
    assert HealUnitOperation.execute(state, eid, eid, 0) == 0
    assert hc.hp == hmax - 50

    # 5. GATE heal-block EffectType.Cursed(79) : HasEffect(target, 0x4f) -> heal annule.
    if state.effects is not None:
        AddEffectOperation.execute(state, source=eid, target=eid, effect_type=CURSED, name="Cursed")
        assert state.effects.has_effect(eid, effect_type=CURSED)
        assert HealUnitOperation.execute(state, eid, eid, 40) == 0
        assert hc.hp == hmax - 50            # inchange (Cursed bloque)

    print("\n[HEAL op] FillUp cap OK (hmax=%d) + Cursed(79) gate OK" % hmax)


def test_le_gate_EntityCanBeHealed_est_ARME_et_DISCRIMINE(live_session, rpc, build_runner):
    """#520 -- le cran que l'Operation n'avait PAS, et le seul qui prouve qu'elle l'a maintenant.

    `IdunBattle.Operations.HealUnitOperation$$Execute` ouvre sur
    `if (!attackQuery.<slot 0x11>(caster, target, scope, removeEffects)) return {};`. Avant #520 ce
    gate n'etait appele NULLE PART depuis l'Operation : le port soignait une unite MECANIQUE
    (`IsAffectedByHealType(target, 0)` faux), une MACHINE OF WAR (`IsMachine`) et une cible a trait
    `Object` -- trois refus natifs devenus des mutations de PV silencieuses.

    Le test exige un TEMOIN NON NUL des DEUX cotes : au moins une cible refusee ET au moins une
    acceptee. Un board ou tout le monde est soignable rendrait ce test vert sans rien mesurer."""
    rid = build_runner("777")["rid"]
    state = _state(rid, rpc)
    soignables, refusees = _victimes(state)
    if not refusees:
        pytest.skip("aucune cible REFUSEE par le gate sur ce seed -- temoin negatif absent")
    assert soignables, "temoin POSITIF absent : le gate refuserait tout le monde"

    # Cote REFUSE : blessee de 100, et pourtant PAS UN SEUL PV rendu, PAS UNE mutation.
    for eid in refusees:
        hc = state.get_entity(eid).get_component(HealthComponent)
        hmax = int(hc.hp_max)
        hc.hp = hmax - 100
        rendu = HealUnitOperation.execute(state, eid, eid, 500)
        assert rendu == 0, "gate EntityCanBeHealed : cible %d refusee -> 0" % eid
        assert int(hc.hp) == hmax - 100, "aucune mutation sur un refus (OperationResult vide)"

    # Cote ACCEPTE : la MEME blessure rend bien 100.
    eid = soignables[0]
    hc = state.get_entity(eid).get_component(HealthComponent)
    hmax = int(hc.hp_max)
    hc.hp = hmax - 100
    assert HealUnitOperation.execute(state, eid, eid, 500) == 100

    print("\n[HEAL gate] refusees=%d acceptees=%d" % (len(refusees), len(soignables)))


def test_predict_heal_branche_NEGATIVE_retire_des_PV(live_session, rpc, build_runner):
    """`PredictHeal` : `if (predicted < 0) return -MaxReduce(fillUp, -predicted, false);`.

    Un « soin » NEGATIF retire des PV -- le decompile l'ecrit, et le port le mirrore depuis #520.
    Avant, `HealUnitOperation` sortait sur `if amount <= 0: return 0`, ce qui rendait la branche
    INEXISTANTE cote port.

    ⚠ CE N'EST PAS UN CHEMIN ATTEIGNABLE PAR UN CALL-SITE PORTE, et c'est le test qui l'etablit :
    la feuille `abilities/behaviours/stats.py::Heal` filtre `amount > 0` avant d'appeler l'Operation.
    On mesure donc ici le MIRROR, pas un comportement de jeu."""
    rid = build_runner("777")["rid"]
    state = _state(rid, rpc)
    soignables, _ = _victimes(state)
    if not soignables:
        pytest.skip("aucune unite SOIGNABLE")
    eid = soignables[0]
    hc = state.get_entity(eid).get_component(HealthComponent)
    hmax = int(hc.hp_max)
    hc.hp = hmax - 100

    # `MaxReduce(-(-10)) = Min(10, current)` -> `predicted = -10`.
    assert predict_heal(state, eid, eid, -10) == -10
    # `FillUp(-10)` = `Min(-10, max - cur)` = -10 -> les PV DESCENDENT ; `healed <= 0` -> retour 0.
    assert HealUnitOperation.execute(state, eid, eid, -10) == 0
    assert int(hc.hp) == hmax - 110, "la branche negative RETIRE 10 PV (MaxReduce)"

    # Borne basse : on ne peut pas retirer plus que les PV courants (`Min(amount, Current)`).
    hc.hp = 5
    assert predict_heal(state, eid, eid, -999) == -5

    print("\n[HEAL neg] branche MaxReduce OK (hmax=%d)" % hmax)
