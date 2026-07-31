"""#345 -- la FORMULE du terme BOUCLIER de la prediction, confrontee au LIVE.

#342 a debloque le levier (faire POSER un bouclier en bataille) et confronte l'ARRONDI du terme,
en laissant sa FORMULE ouverte : `shieldDmgMin` n'etait PAS `min(shield, totalDmgMin)`, et aucun
modele ne remplacait celui qui venait d'etre refute. Cette garde ferme ce residu.

CE QU'ELLE VERROUILLE, et pourquoi elle ne peut pas passer par accident :

A. **Le terme est REELLEMENT exerce** : bouclier pose en bataille (`ArcaneShieldAbility`), et au
   moins un tir dans le regime de CAP (borne haute rabattue au bouclier). Sans cap, toute formule
   « `min(quelque chose`, bouclier) » est vraie par construction.
B. **PLUSIEURS regimes** (`SOUS-CAP` et `CAP-PARTIEL`). Un modele qui reproduit un seul couple ne
   prouve rien : c'est la grille qui separe.
C. **Les modeles CONCURRENTS sont refutes par la MESURE**, pas cites : `min(shield, totalDmg)` (le
   modele evident, celui que #342 avait refute) et `min(shield, sante + bouclier)` doivent
   s'ecarter du natif sur au moins un regime.
D. **Le port egale le natif sur le terme BOUCLIER**, tir par tir.
E. **Le COMPLEMENT aussi** (`AccurateHealthDamage` et `TotalDamage`) -- c'est la moitie qui a
   revele l'erreur : le terme bouclier seul ne pouvait pas la voir (cf. F).
F. **La MUTATION est jouee** : le port d'AVANT #345 (rem UNIQUE = `shield - cumul MAX` pour les
   deux bornes) doit rester **INDISCERNABLE sur le bouclier** -- il l'est algebriquement, le cap
   `CurrentShield` l'y absorbe -- et **CASSER le complement**. Une garde qui ne regarderait que
   `AccurateShieldDamage` serait donc VERTE sur un port faux ; c'est exactement le piege dans
   lequel #42 etait tombe.

La lecture du decompile qui justifie tout ceci vit dans l'en-tete de
`probe_345_shield_prediction_formula.py` et dans `docs/rl/case-345-formule-terme-bouclier.md`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_345_shield_prediction_formula as P             # noqa: E402


@pytest.fixture(scope="module")
def measured():
    out = P.run(seed=34501, verbose=False)
    assert not out.get("error"), "montage KO : %s" % out.get("error")
    rows = [r for r in (out.get("rows") or []) if not r.get("error")]
    assert rows, "aucun tir exploitable : %s" % [r.get("error") for r in (out.get("rows") or [])]
    return out


def _rows(measured):
    return [r for r in measured["rows"] if not r.get("error")]


def test_the_shield_term_is_actually_exercised(measured):
    """A : bouclier POSE et au moins un tir dans le regime de CAP.

    Hors cap, `AccurateShieldDamage` vaut simplement `hits x base` et TOUTE formule plafonnee au
    bouclier y coincide -- la mesure ne dirait rien."""
    rows = _rows(measured)
    for r in rows:
        assert r["native"]["shieldBefore"] > 0, (
            "Damage=%s : aucun bouclier en bataille -- le vecteur ArcaneShield n'a pas fire "
            "(deplacement du porteur refuse, ou aucun allie dans son rayon)" % r["damage"])
    capped = [r for r in rows if r["regime"] in ("CAP-PARTIEL", "SUR-CAP")]
    assert capped, (
        "aucun tir dans le regime de CAP (regimes vus : %s) -- sans cap, toute formule plafonnee "
        "au bouclier est vraie par construction" % sorted({r["regime"] for r in rows}))


def test_several_regimes_are_covered(measured):
    """B : un seul couple ne separe aucun modele -- il en faut au moins deux, de regimes
    DIFFERENTS."""
    assert len(measured["regimes"]) >= 2, (
        "un seul regime couvert (%s) : plusieurs formules y coincident, la grille ne discrimine "
        "rien" % measured["regimes"])


def test_the_obvious_models_are_refuted_by_measurement(measured):
    """C : `min(shield, totalDmg)` et `min(shield, sante + bouclier)` doivent TOMBER."""
    for name, refuted in measured["rivals_refuted"].items():
        assert refuted, (
            "le modele `%s` egale le natif sur TOUS les tirs : la grille ne le separe pas de la "
            "formule portee -- elargir les regimes avant de conclure quoi que ce soit" % name)


def test_port_matches_native_on_the_shield_term(measured):
    """D : le terme BOUCLIER du port == natif, tir par tir."""
    for r in _rows(measured):
        assert r["shield_match"], (
            "Damage=%s (%s, bouclier %d) : shieldDmg port [%d,%d] != natif [%d,%d]"
            % (r["damage"], r["regime"], r["native"]["shieldBefore"],
               r["port"]["shieldDmgMin"], r["port"]["shieldDmgMax"],
               r["native"]["shieldDmgMin"], r["native"]["shieldDmgMax"]))


def test_port_matches_native_on_the_complement(measured):
    """E : sante ET total. `TotalDamage@0x60` n'est PAS `sante + bouclier` du resultat : le natif
    somme le degat sante TEL QU'IL ENTRE dans `CalculateDamagePredictionScenario` (avant le
    `blockDamage` et avant `FillUpStatComponent$$MaxReduceByMinimum`) et le bloque NON cape."""
    for r in _rows(measured):
        assert r["health_match"], (
            "Damage=%s (%s) : healthDmg port [%d,%d] != natif [%d,%d] -- le SPLIT est faux meme "
            "si le terme bouclier coincide"
            % (r["damage"], r["regime"], r["port"]["healthDmgMin"], r["port"]["healthDmgMax"],
               r["native"]["healthDmgMin"], r["native"]["healthDmgMax"]))
        assert r["total_match"], (
            "Damage=%s (%s) : totalDmg port [%d,%d] != natif [%d,%d]"
            % (r["damage"], r["regime"], r["port"]["totalDmgMin"], r["port"]["totalDmgMax"],
               r["native"]["totalDmgMin"], r["native"]["totalDmgMax"]))


def test_the_pre_345_port_is_blind_on_the_shield_term(measured):
    """F1 : la MUTATION doit etre INVISIBLE sur `AccurateShieldDamage`.

    Ce n'est pas une faiblesse de la mutation, c'est le FAIT central du cas : le champ vaut
    `MinMaxDamage(blockedMin, blockedMax, cap = remShieldMax)`, donc sa borne min se reduit a
    `min(base.Min, remShieldMax)` -- identique sous les deux modeles puisque
    `remShieldMax <= remShieldMin`. Si cette assertion tombait, l'argument d'indiscernabilite
    serait faux et toute la lecture du cas serait a refaire."""
    for r in _rows(measured):
        assert r["mutant_shield_same"], (
            "Damage=%s : le rem UNIQUE change le terme bouclier ([%d,%d] vs natif [%d,%d]) -- "
            "l'indiscernabilite algebrique documentee dans case-345 ne tient pas"
            % (r["damage"], r["mutant_rem_unique"]["shieldDmgMin"],
               r["mutant_rem_unique"]["shieldDmgMax"],
               r["native"]["shieldDmgMin"], r["native"]["shieldDmgMax"]))


def test_the_pre_345_port_breaks_the_complement(measured):
    """F2 : ... et doit CASSER le complement sur au moins un tir. Sans ce rouge, la garde ne
    verrouillerait rien (elle passerait aussi sur le port faux)."""
    broken = [r for r in _rows(measured) if r["mutant_health_breaks"]]
    assert broken, (
        "le rem UNIQUE (port d'avant #345) reproduit le natif sur TOUS les tirs, complement "
        "compris : la grille n'atteint pas le regime ou les deux modeles se separent (il faut un "
        "coup dont la piste MIN n'a pas encore epuise le bouclier alors que la piste MAX l'a "
        "epuise -- ex. `Damage` 2286, 6 coups, bouclier 5483)")
    r = broken[0]
    assert r["mutant_rem_unique"]["healthDmgMin"] > r["native"]["healthDmgMin"], (
        "Damage=%s : le rem UNIQUE devrait SUR-estimer le degat sante (il bloque trop peu cote "
        "MIN), or il rend %d pour un natif de %d"
        % (r["damage"], r["mutant_rem_unique"]["healthDmgMin"], r["native"]["healthDmgMin"]))


def test_overall_verdict(measured):
    assert measured.get("ok"), "verdict global du probe #345 : ECHEC"
