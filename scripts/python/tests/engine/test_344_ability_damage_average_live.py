"""#344 -- les DEUX moyennes de la prediction d'ability, confrontees au LIVE.

CE QUE CETTE GARDE VERROUILLE, et pourquoi elle ne peut pas passer par accident :

A. **Les DEUX cotes de la parite sont EXERCES, et ils sont PILOTES.** Les deux moyennes natives ne
   divergent que si `minDmg + maxDmg` vaut 3 mod 4 ; sur une somme paire, ou sur `1 mod 4`, elles
   coincident et une mesure qui n'y verrait que ca ne dirait RIEN. Le montage ne SUBIT donc pas la
   parite : `rl_duel build --unit-stat '<vis>:ActiveAbilityLevel=<L>'` choisit le niveau, donc le
   couple (minDmg, maxDmg) de la config. Le regime obtenu est RE-DERIVE du live.
B. **Les DEUX FAMILLES sont exercees, et elles rendent des reponses OPPOSEES.** Le natif MONTE pour
   `FlailSwing` (playbook -> `<X>Ability$$GetDamageAmountMain` -> `AActiveAbility$$MinMaxDamageAverage`
   = `Half(Sum(...), 0)`) et TRONQUE pour `PlasmaCannon` (playbook -> `<X>Ability$$GetDamage` ->
   `AActiveAbility$$MinMaxDamage(isPrediction: FALSE)` = `RandomAmount`, pris au slot 4 =
   `AAmountFormula$$CalculateAverage`). C'est CE test qui interdit de remettre tout le monde sur un
   seul arrondi -- l'erreur que #344 a d'abord commise avant de la mesurer.
C. **Le code LIVRE est confronte**, pas seulement la formule : le probe appelle
   `engine.playbook.prediction.abilities.make_damage_predictions` SANS aucun patch et exige
   l'egalite bit-exacte avec `aiPlaybookPredict` sur les deux bras des deux familles.
D. **Le MODE est discrimine, pas suppose** : quatre variantes d'arrondi tournent sur le MEME etat,
   et une SEULE egale le natif sur les deux bras -- celle que le registre du port prevoit.
E. **Le regime n'est pas degenere** : sur chaque bras, les quatre variantes doivent rendre des
   bornes DISTINCTES. Un arrondi aval (armure, `Ceiling`) peut ABSORBER l'ecart d'une unite (piege
   herite de #339 sec.4, re-observe ici : BringerOfDespair niveau 2 sur cible blindee) ; un bras
   muet fait ECHOUER le probe au lieu de le verdir.

Toute la lecture du decompile vit dans l'en-tete de `probe_344_ability_damage_average.py`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_344_ability_damage_average as P                 # noqa: E402
from engine.entities.abilities.active_ability import (_PREDICTION_MINMAX_AVERAGE,   # noqa: E402
                                                      _PREDICTION_MINMAX_RANDOM_READ)

# Deux montages, un par FAMILLE. Niveaux choisis pour poser `3 mod 4` (bras a) et `1 mod 4` (bras b).
MONTAGES = {
    "average": dict(caster="deathBlightlord", ability=1042, ability_name="FlailSwing",
                    board="MC1_67", center=(3, 4), lvl_a=2, lvl_b=5, seed=34401),
    "random": dict(caster="darkaTerminator", ability=1150, ability_name="PlasmaCannon",
                   board="C1_03", center=(3, 6), lvl_a=3, lvl_b=2, seed=34411),
}


@pytest.fixture(scope="module")
def measured():
    out = {}
    for key, m in MONTAGES.items():
        sf = PYDIR.parents[1] / "logs" / ("t344_%s.json" % key)
        r = P.run(state_file=str(sf), verbose=False, **m)
        assert not r.get("error"), "%s : montage KO (%s)" % (key, r.get("error"))
        for k, arm in (r.get("arms") or {}).items():
            assert not arm.get("error"), "%s bras %s KO : %s" % (key, k, arm["error"])
        out[key] = r
    return out


def test_the_two_montages_are_of_opposite_families():
    """B (pre-condition) : sans une ability de CHAQUE famille, le test ne peut pas montrer que la
    reponse native depend du playbook."""
    assert MONTAGES["average"]["ability"] in _PREDICTION_MINMAX_AVERAGE
    assert MONTAGES["random"]["ability"] in _PREDICTION_MINMAX_RANDOM_READ


def test_both_parities_are_driven(measured):
    """A : `3 mod 4` d'un cote, `1 mod 4` de l'autre, sur les DEUX montages -- et le niveau
    EFFECTIF (relu du live) est bien celui demande."""
    for key, out in measured.items():
        a, b = out["arms"]["a"], out["arms"]["b"]
        assert a["sum_mod4"] == 3, (
            "%s bras a : somme %d n'est pas 3 mod 4 -- les deux moyennes y coincident, le montage "
            "ne discrimine rien" % (key, a["sum"]))
        assert b["sum_mod4"] == 1, (
            "%s bras b : somme %d n'est pas 1 mod 4" % (key, b["sum"]))
        for k, arm in (("a", a), ("b", b)):
            assert arm["level_eff"] == arm["level_asked"], (
                "%s bras %s : le niveau pilote n'a pas pris (demande %d, effectif %d) -- la mesure "
                "porterait sur un autre couple que celui annonce"
                % (key, k, arm["level_asked"], arm["level_eff"]))


def test_every_arm_discriminates(measured):
    """E : sur chaque bras, les quatre variantes doivent rendre des bornes DISTINCTES."""
    for key, out in measured.items():
        for k in ("a", "b"):
            assert out["arms"][k]["discriminates"], (
                "%s bras %s : les quatre variantes d'arrondi rendent la MEME prediction -- l'ecart "
                "d'une unite a ete absorbe en aval, ce bras ne prouve rien" % (key, k))


def test_shipped_code_matches_native_on_both_arms(measured):
    """C : le code LIVRE (aucun patch) egale le natif, bras par bras, sur les deux familles."""
    for key, out in measured.items():
        for k in ("a", "b"):
            arm = out["arms"][k]
            assert arm["shipped_ok"], (
                "%s bras %s : le port LIVRE rend %s la ou le natif rend %s (minDmg=%d maxDmg=%d, "
                "somme %d = %d mod 4)" % (key, k, arm["shipped"], arm["native"], arm["minDmg"],
                                          arm["maxDmg"], arm["sum"], arm["sum_mod4"]))


def test_the_native_answer_depends_on_the_family(measured):
    """B + D : une seule variante egale le natif sur les deux bras, et ce n'est PAS la meme pour les
    deux familles. C'est la mutation « un seul arrondi pour tout le monde » qui meurt ici."""
    avg, rnd = measured["average"], measured["random"]
    assert avg["nul_on_both_arms"] == ["to_even"], (
        "famille `MinMaxDamageAverage` : variantes nulles sur les deux bras = %s, attendu "
        "['to_even']" % avg["nul_on_both_arms"])
    assert rnd["nul_on_both_arms"] == ["trunc"], (
        "famille `RandomAmount` + `CalculateAverage` : variantes nulles sur les deux bras = %s, "
        "attendu ['trunc']" % rnd["nul_on_both_arms"])
    assert avg["nul_on_both_arms"] != rnd["nul_on_both_arms"], (
        "les deux familles rendent le MEME arrondi : un port a moyenne unique passerait -- le test "
        "ne verrouille plus rien")


def test_truncation_is_wrong_for_the_average_family(measured):
    """D (mutation ciblee) : sur le bras `3 mod 4` de la famille (a), la TRONCATURE -- le port
    d'avant #344 -- s'ecarte du natif. Sans ca, la correction ne serait pas load-bearing."""
    a = measured["average"]["arms"]["a"]
    assert a["match"]["to_even"] and not a["match"]["trunc"], (
        "bras a de la famille (a) : trunc=%s to_even=%s (natif %s) -- la troncature devrait etre "
        "REFUSEE ici" % (a["ports"]["trunc"], a["ports"]["to_even"], a["native"]))
    assert a["ports"]["trunc"] != a["ports"]["to_even"]


def test_to_even_is_wrong_for_the_random_family(measured):
    """B (mutation symetrique) : sur le bras `3 mod 4` de la famille (b), le demi-vers-le-pair --
    le premier fix de #344, avant la mesure -- s'ecarte du natif."""
    a = measured["random"]["arms"]["a"]
    assert a["match"]["trunc"] and not a["match"]["to_even"], (
        "bras a de la famille (b) : to_even=%s trunc=%s (natif %s) -- aligner cette famille sur le "
        "demi-vers-le-pair serait une REGRESSION"
        % (a["ports"]["to_even"], a["ports"]["trunc"], a["native"]))
