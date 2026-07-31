"""#360 -- une ability de MACHINE OF WAR confrontee avec SON PORTEUR, pas avec une greffe.

`#350-r3` avait laisse `1147 HadesAutocannons` et `1148 DaemonicOrdnance` confrontees sur une unite
GREFFEE, faute d'oracle acceptant une MoW pour caster. Deux verrous etaient nommes : (a) le capteur
`aiPlaybookPredict`, (b) le contexte `engine.ai.context`. #360 les a mesures :

  (a) EST le verrou, et sa cause est une SUBSTITUTION du harnais -- `rpc-predict.ts` passait la
      `UnitPosition` de la CIBLE pour un caster off-board. Le natif passe
      `IdunBattle.Core.UnitPosition$$NullPosition()` (lu dans
      `IdunBattle.AI.Tactics.DefaultMachineTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`),
      c.-a-d. une liste de tuiles VIDE. Avec la position du CASTER, le MEME
      `<X>Playbook$$MakeDamagePredictions` REND ses events.
  (b) N'EST PAS un verrou : `engine.ai.context.build_machine` existe et `engine_validate.py` route
      deja dessus (`machine_row`). `build` rend `me = None` sur une Machine parce que c'est la
      fonction des UNITES -- `decisionView.units` ne contient jamais de Machine.

Ce que la garde tient :

1. l'oracle par la position du CASTER repond pour une MoW, et le port lui construit un contexte ;
2. la CONFRONTATION avec le porteur reel donne le MEME verdict d'arrondi que la voie greffee, et
   les MEMES couples (min, max, hits) -- ce qui valide RETROSPECTIVEMENT la greffe de `#350-r3` ;
3. le bras A DISCRIMINE (les quatre variantes ne coincident pas) et le code LIVRE egale le natif.

Deux runners (etape A + deux bras de l'etape B, disposes par le probe). ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_360_mow_caster_oracle as P                     # noqa: E402


@pytest.fixture(scope="module")
def discriminant():
    return P.step_a(seed=36210, verbose=False)


@pytest.fixture(scope="module")
def confronted():
    return P.step_b(seed=36240, verbose=False)


def test_the_caster_position_is_what_opens_the_mow_oracle(discriminant):
    """1 : le MEME `MakeDamagePredictions`, deux positions, deux issues. C'est la mesure qui
    designe `rpc-predict.ts` comme le verrou -- et elle ne depend d'aucune fenetre de reinject,
    puisque `ncPlaybookPredict` passe DEJA la position du caster."""
    r = discriminant
    nc = r["ncPlaybookPredict"]
    assert not nc.get("error"), (
        "l'oracle par la position du CASTER leve desormais : %s -- relire "
        "`UnitPosition$$NullPosition` et `GetEntitiesFromSelector`" % nc.get("error"))
    assert (nc.get("returnedCount") or 0) >= 1, (
        "l'oracle par la position du CASTER ne rend plus d'event pour une MoW (returned=%s) : le "
        "montage summon ou le selecteur de 1147 a change" % nc.get("returnedCount"))
    ai = r["aiPlaybookPredict"]
    if str(ai.get("posSrc") or "").startswith("machine:"):
        # Bundle POSTERIEUR au correctif : les deux oracles partent de la meme position, ils
        # doivent donc rendre la MEME chose. C'est le verrou de non-regression du correctif.
        got = [(e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))
               for e in (ai.get("events") or [])]
        want = [(e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))
                for e in (nc.get("returned") or [])]
        assert got == want, (
            "les deux oracles partent de la MEME `UnitPosition` (posSrc=%s) et divergent : "
            "aiPlaybookPredict %s != ncPlaybookPredict %s" % (ai.get("posSrc"), got, want))
    else:
        # Bundle ANTERIEUR : on VERIFIE que le symptome est bien celui qu'on corrige, au lieu de
        # sauter le test. Un `count >= 0` ici voudrait dire que le diagnostic ne tient plus.
        assert ai.get("listNull") is True or (ai.get("count") or 0) < 0, (
            "le bundle injecte ne porte pas le correctif (posSrc=%s) mais `aiPlaybookPredict` "
            "rend pourtant une liste (count=%s) : le diagnostic de #360 est a re-mesurer"
            % (ai.get("posSrc"), ai.get("count")))


def test_the_port_has_a_context_for_a_machine_caster(discriminant):
    """2 : `build_machine` rend le contexte REEL de la MoW. `build` rendant None n'est pas un trou
    du port -- c'est le canal `.units`, qui ne contient aucune Machine."""
    r = discriminant
    assert r["port_build_machine_me"] == P.MOW, (
        "`build_machine` ne construit plus le contexte de la MoW : %s" % r["port_build_machine_me"])
    assert r["port_scene_ctx"] is True, (
        "`scene.ctx(<MoW>)` est vide : le predicteur (combatSnapshot) n'hydrate plus les Machine, "
        "et toute prediction offline avec une MoW pour caster serait muette")
    assert r["port_origin"] is None, (
        "`build_machine` donne desormais une origine a la MoW : le mirror de `DefaultMachineTactic` "
        "(`NullPosition()` + `new OrderedSet()`) ne tient plus")
    assert r["port_build_me"] is None, (
        "`build` (fonction des UNITES) rend un contexte pour une Machine : `decisionView.units` "
        "contiendrait desormais les MoW, ce qui change le routage de tactic")


def test_1147_with_its_real_mow_carrier_matches_the_graft(confronted):
    """3 : la confrontation elle-meme. Meme verdict d'arrondi ET memes couples que la greffe."""
    r = confronted
    for k in ("a", "b"):
        arm = r["arms"][k]
        assert not arm.get("error"), "bras %s KO : %s" % (k, arm.get("error"))
        assert arm["shipped_ok"], (
            "bras %s : le code LIVRE %s != natif %s (caster = la MoW REELLE)"
            % (k, arm["shipped"], arm["native"]))
        assert arm["agrees_with_graft"], (
            "bras %s : le porteur MoW REEL rend %s la ou la GREFFE rendait %s -- la greffe ne "
            "serait plus une mesure equivalente, et les verdicts pris par greffe seraient a "
            "reprendre" % (k, arm["native"], arm["graft_native"]))
    assert r["arms"]["a"]["discriminates"], (
        "le bras A ne discrimine plus (les quatre variantes coincident) : il ne prouve rien")
    assert r["regimes_ok"], "la parite pilotee n'est pas celle annoncee (3 mod 4 puis 1 mod 4)"
    assert r["nul_on_both_arms"] == ["to_even"], (
        "variantes nulles sur les DEUX bras : %s -- attendu ['to_even'] (voie a2, "
        "`StaffOfStarsAbility$$GetDamage` avec isPrediction = 1)" % r["nul_on_both_arms"])
