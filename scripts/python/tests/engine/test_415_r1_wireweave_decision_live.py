"""#415-r1 -- la face DECISION de `1111 WireweaveNet_CounterAttack` (-30), CONFRONTEE au NATIF.

`IdunBattle.AI.Utilities.WireweaveNet_FirstAttack` (`UtilityType` 55, litteral `0x37` lu dans
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`)
verse le poids BC `Utilities.Default.WireweaveNet_FirstAttack.WIREWEAVENET_AdjacentActiveEffect`
(= -30) quand la CIBLE porte un effet `0x457` (1111) dont le flag `EffectComponent.IsActive @+0x5c`
est pose. Le terme est somme DANS `CalculateActionUtility`, APRES
`...$$CalculateUtilityFromPredictions` -- donc l'oracle `pairUtility` (qui invoque directement ce
dernier) lui est STRUCTURELLEMENT AVEUGLE. Le seul oracle qui le VOIT est la DECISION
(`aiDryRunAllUnits` -> `IdunBattle.AI.Tactics.DefaultAiUnitTactic$$CalculateNextActionForUnit`).

CE QUE CE TEST GARDE, sur les DEUX regimes que le montage separe :

  1. **CONFORMITE** -- dans CHAQUE bras, la decision du port (ability, cible, tuile) egale celle du
     NATIF. Le bras ARME doit retenir la cible SANS filet ; le bras DESARME doit retenir la cible
     PREMIERE ENUMEREE (rang cube), c'est-a-dire celle qui portait le filet.
  2. **DISCRIMINANCE** -- terme RETIRE (`utilities.wireweave_net.wireweave_net_first_attack_utility`
     neutralise), l'ecart d'utilite d'ACTION doit valoir EXACTEMENT le poids BC sur la porteuse du
     filet ARME, et rester NUL partout ailleurs -- y compris dans le bras DESARME, le regime ou le
     terme ne s'applique PAS. Et la decision du port mute doit BASCULER sur la porteuse du filet
     dans le bras arme : sans cette assertion le test serait incapable d'echouer sur un port qui
     ignore le terme.

Le montage EXIGE ses deux regimes et EXIGE que rien d'autre ne puisse les separer : egalite EXACTE
de `pairUtility` NATIF entre les deux cibles (meme `utilRaw` Fix64), caster EPINGLE
(`--unit-stat Movement=0` -> une seule tuile d'action), les deux cibles LEGALES depuis cette tuile,
et cibles a distance >= 2 (le regime qui FALSIFIE la lecture « gate d'adjacence » du conjoint
degenere). S'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268).

Montage et mesure : `scripts/python/probe_415_r1_wireweave_decision.py`. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_415_r1_wireweave_decision as P


@pytest.fixture(scope="module")
def wwn_decision_case(live_session):
    """Les DEUX bras du probe (ARME / DESARME). Chaque bras monte SON runner et le DISPOSE en sortie
    de `run()` -- rien a liberer au teardown. Portee MODULE : les deux tests se partagent la mesure."""
    out = {}
    for bras, disarm in (("arme", False), ("desarme", True)):
        r = P.run(disarm=disarm, verbose=True)
        if "error" in r:
            pytest.fail(f"montage #415-r1 NON INSTALLE (bras {bras}) : {r['error']}", pytrace=False)
        out[bras] = r
    if (out["arme"]["P"], out["arme"]["TA"], out["arme"]["TB"]) != \
       (out["desarme"]["P"], out["desarme"]["TA"], out["desarme"]["TB"]):
        pytest.fail(f"les deux bras n'ont pas la MEME geometrie : "
                    f"{(out['arme']['P'], out['arme']['TA'], out['arme']['TB'])} vs "
                    f"{(out['desarme']['P'], out['desarme']['TA'], out['desarme']['TB'])} -- "
                    f"l'A/B ne serait plus attribuable au seul filet", pytrace=False)
    return out


def test_wireweave_decision_matches_native(wwn_decision_case):
    """(1) CONFORMITE + les prealables SANS lesquels l'ecart ne serait attribuable a rien :
    egalite EXACTE de `pairUtility` NATIF, port deja conforme a CET etage, legalite des deux cibles
    depuis la tuile epinglee, et regime DISTANT."""
    fails = [f for f in P.verdict(wwn_decision_case["arme"], wwn_decision_case["desarme"])
             if "NEUTRALISE" not in f and "le terme pese" not in f]
    assert not fails, "conformite #415-r1 :\n  - " + "\n  - ".join(fails)
    arme, desarme = wwn_decision_case["arme"], wwn_decision_case["desarme"]
    assert arme["native"]["target"] == arme["other_id"], (
        f"[arme] le natif doit EVITER la porteuse du filet : cible={arme['native']['target']} "
        f"filet={arme['net_id']} sans_filet={arme['other_id']}")
    assert desarme["native"]["target"] == desarme["net_id"], (
        f"[desarme] sans filet, le tie revient a la cible PREMIERE ENUMEREE "
        f"({desarme['net_id']}) : natif={desarme['native']['target']}")
    assert arme["native"]["target"] != desarme["native"]["target"], (
        "le natif retient la MEME cible dans les deux bras : le montage ne discrimine rien")


def test_wireweave_decision_term_is_load_bearing(wwn_decision_case):
    """(2) DISCRIMINANCE : terme NEUTRALISE, l'ecart vaut EXACTEMENT le poids BC sur la porteuse du
    filet ARME et ZERO ailleurs, et la decision du port BASCULE dans le bras arme."""
    fails = [f for f in P.verdict(wwn_decision_case["arme"], wwn_decision_case["desarme"])
             if "NEUTRALISE" in f or "le terme pese" in f]
    assert not fails, "discriminance #415-r1 :\n  - " + "\n  - ".join(fails)
    arme, desarme = wwn_decision_case["arme"], wwn_decision_case["desarme"]
    assert arme["port_without_wwn"]["target"] == arme["net_id"], (
        f"[arme] terme NEUTRALISE, le port doit retomber sur la porteuse du filet "
        f"({arme['net_id']}) : {arme['port_without_wwn']['target']}")
    assert desarme["port_without_wwn"]["target"] == desarme["port"]["target"], (
        "[desarme] neutraliser le terme CHANGE la decision dans le regime ou il ne s'applique "
        "PAS : il n'y est donc pas inerte")
