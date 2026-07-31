"""#339 -- le terme LIFESTEAL de SpiritLeech, confronte au LIVE.

CE QUE CETTE GARDE VERROUILLE, et pourquoi elle ne peut pas passer par accident :

A. **Les DEUX axes du gap sont EXERCES.**
   - l'axe BORNES : le montage cape `AccurateHealthDamage` bien EN DESSOUS des bornes brutes
     (`--hp-target`), donc `healthDmg* != rawHealthDmg*`. Sans ca, lire les brutes ou les capees
     donnerait le meme chiffre et la garde ne dirait rien du champ effectivement moyenne ;
   - l'axe ARRONDI : la parite est PILOTEE (deux bras, floor IMPAIR / floor PAIR), et le `H` est
     choisi pour que le `Ceiling` de `PercentageOf` n'ECRASE PAS l'ecart d'une unite (a 60 %,
     `ceil(2759 x .6) == ceil(2760 x .6)` -- un bras mal choisi serait vert sans discriminer).
B. **Le code LIVRE est confronte, pas seulement la formule du probe** :
   `ComparableAbilityGenerator._spiritleech_lifesteal_util` est appele sur le contexte IA REEL
   (`engine.ai.context.build`) et nourri de la prediction NATIVE -- feed identique des deux cotes,
   donc tout ecart est un gap de LOGIQUE.
C. **L'oracle est isole** : `pairUtility`
   (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`)
   moins le terme DEGAT recalcule depuis les MEMES events natifs. Le residu vaut exactement le
   terme de soin -- ce qui prouve au passage que le terme d'EFFET (1065) pese 0.
D. **La MUTATION est jouee** : la variante `port_avant` REPRODUIT le port d'avant #339 (bornes
   brutes + bouclier, `.5` conserve) et doit s'ecarter sur les DEUX bras, de bien plus qu'un
   arrondi -- c'est la preuve que le bug principal etait le CHAMP lu, pas la virgule.
E. **`to_even` est le SEUL mode nul sur les deux bras** : troncature et demi-vers-le-haut tombent
   chacun sur un bras.

La lecture du decompile qui justifie tout ca vit dans l'en-tete de
`probe_339_spiritleech_lifesteal.py`. Le pendant OFFLINE (les trois moyennes natives et leur
regime de divergence) est `test_339_moyennes_residuelles_offline.py`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_339_spiritleech_lifesteal as P                  # noqa: E402

TOL = 1e-6


@pytest.fixture(scope="module")
def measured():
    out = P.run(seed=33910, verbose=False)
    assert not out.get("error"), "montage KO : %s" % out.get("error")
    for key, arm in (out.get("arms") or {}).items():
        assert not arm.get("error"), "bras %s KO : %s" % (key, arm["error"])
    return out


def test_the_capped_bounds_really_differ_from_the_raw_ones(measured):
    """A (axe BORNES) : si la cape ne mord pas, lire `healthDmg*` ou `rawHealthDmg*` revient au
    meme et la garde ne temoigne plus du champ moyenne."""
    for key, arm in measured["arms"].items():
        assert (arm["healthDmgMax"], arm["healthDmgMin"]) != (arm["rawHealthDmgMax"],
                                                              arm["rawHealthDmgMin"]), (
            "bras %s : bornes capees == bornes brutes (%s) -- l'axe BORNES n'est pas exerce"
            % (key, (arm["healthDmgMin"], arm["healthDmgMax"])))
        assert arm["healthDmgMax"] < arm["rawHealthDmgMax"], (
            "bras %s : la cape aux PV ne mord pas sur la borne HAUTE (%d >= %d)"
            % (key, arm["healthDmgMax"], arm["rawHealthDmgMax"]))


def test_the_two_arms_exercise_both_sides_of_the_parity(measured):
    """A (axe ARRONDI) : un `.5` a floor PAIR **et** un a floor IMPAIR, sinon aucun mode n'est
    separe. Le regime ne doit pas non plus etre degenere (`LimitedByMinHp` court-circuiterait)."""
    arms = measured["arms"]
    for key, arm in arms.items():
        assert arm["sum_odd"], (
            "bras %s : somme %d PAIRE -- aucun `.5` exact, l'arrondi n'est pas exerce"
            % (key, arm["sum"]))
        assert not arm["limitedByMinHp"], "bras %s : `LimitedByMinHp` VRAI" % key
        assert arm["pct"], "bras %s : hpToHealPct nul, le terme mesure n'existe pas" % key
    assert arms["up"]["floor_odd"] is True, (
        "bras UP : floor %d n'est pas IMPAIR -- le natif n'y monte pas" % arms["up"]["floor"])
    assert arms["down"]["floor_odd"] is False, (
        "bras DOWN : floor %d n'est pas PAIR -- le natif n'y descend pas" % arms["down"]["floor"])


def test_the_ceiling_does_not_swallow_the_one_unit_gap(measured):
    """A (piege propre a #339) : `PercentageOf(..., roundUp=1)` peut ABSORBER un ecart d'une unite
    sur la moyenne. Si les montants de soin des variantes coincidaient, le bras serait vert sans
    rien discriminer."""
    for key, arm in measured["arms"].items():
        amounts = {n: arm["terms"][n]["amount"] for n in ("to_even", "trunc", "half_up")}
        assert len(set(amounts.values())) >= 2, (
            "bras %s : `Ceiling` ecrase les variantes sur le meme montant de soin %s -- ce bras "
            "ne discrimine rien" % (key, amounts))


def test_the_shipped_port_matches_the_native_on_both_arms(measured):
    """B : `_spiritleech_lifesteal_util` (le code livre) == residu natif, sur les DEUX bras."""
    for key, arm in measured["arms"].items():
        assert arm["real_delta"] is not None and abs(arm["real_delta"]) < TOL, (
            "bras %s : port livre %s != residu natif %s (ecart %s)"
            % (key, arm["real_port"], arm["residual"], arm["real_delta"]))


def test_the_residual_is_exactly_the_heal_term(measured):
    """C : le residu `natif - degat` vaut le terme de soin SEUL. Corollaire mesure : l'effet
    natif observe (`1065`) pese 0 dans `CalculateUtilityFromPredictions`."""
    for key, arm in measured["arms"].items():
        assert arm["effectEvents"], (
            "bras %s : aucun event d'effet -- l'affirmation « l'effet pese 0 » n'est plus TESTEE"
            % key)
        assert abs(arm["deltas"]["to_even"]) < TOL, (
            "bras %s : residu %s != terme de soin %s -- une 4e famille de prediction pese, la "
            "soustraction n'isole plus le lifesteal"
            % (key, arm["residual"], arm["terms"]["to_even"]["utility"]))


def test_round_to_even_is_the_only_mode_null_on_both_arms(measured):
    """E : chaque autre mode DOIT tomber sur au moins un bras."""
    arms = measured["arms"]
    for name in ("trunc", "half_up", "kept_half", "port_avant"):
        fails = [k for k, arm in arms.items() if not arm["measured_null"][name]]
        assert fails, (
            "la variante `%s` egale le natif sur les DEUX bras : le montage ne la separe pas de "
            "`to_even`" % name)
    assert measured.get("nul_on_both_arms") == ["to_even"], (
        "variantes nulles sur les deux bras : %s -- il devrait n'y avoir QUE `to_even`"
        % (measured.get("nul_on_both_arms"),))


def test_the_pre_339_port_turns_this_guard_red_by_far_more_than_a_rounding(measured):
    """D : la MUTATION. `port_avant` = bornes BRUTES + bouclier, `.5` conserve. Son ecart doit etre
    d'un ordre de grandeur AU-DESSUS de celui des variantes qui ne different que par l'arrondi --
    sinon on aurait corrige une virgule en croyant corriger le champ lu."""
    for key, arm in measured["arms"].items():
        gros = abs(arm["deltas"]["port_avant"])
        petit = max(abs(arm["deltas"]["trunc"]), abs(arm["deltas"]["half_up"]))
        assert gros > TOL, "bras %s : le port d'avant #339 n'est pas rouge" % key
        assert gros > 10 * petit, (
            "bras %s : l'ecart du port d'avant #339 (%s) n'excede pas 10x l'ecart d'un simple "
            "arrondi (%s) -- la garde ne temoigne plus que le CHAMP lu etait faux"
            % (key, gros, petit))


def test_overall_verdict(measured):
    assert measured.get("ok"), "verdict global du probe #339 : ECHEC"
