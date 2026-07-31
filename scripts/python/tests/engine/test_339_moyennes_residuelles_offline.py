"""#339 -- TROIS moyennes natives, TROIS comportements. La garde qui interdit de les confondre.

#333 a etabli que `IdunBattle.Core.Services.MinMaxDamage$$Avg` arrondit demi-vers-le-PAIR. Le
residu qu'il a laisse (« deux autres sites gardent une division entiere ») a ete resolu ici en
lisant l'artefact de CHAQUE site -- et ils ne sont pas les memes :

| moyenne native | corps | comportement |
|---|---|---|
| `IdunBattle.Core.Services.MinMaxDamage$$Avg` | `(int)Fix64.Round(Fix64(Min+Max)/Fix64(2), 0)` | demi-vers-le-PAIR |
| `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamageAverage` (et son jumeau `BaseTriggeredAbility`) | `Half(Sum(Direct(min), Direct(max)), rule=0)` -> `IdunBattle.Entities.Formulas.DivideAmount$$Calculate` -> `IdunBattle.DSL.AAmountFormula$$RoundFix64Result(mode 0)` | demi-vers-le-PAIR |
| `IdunBattle.DSL.AAmountFormula$$CalculateAverage` | `(CalculateMin() + CalculateMax()) / 2`, arithmetique ENTIERE | TRONCATURE |

Le point qui fait tout : **elles divergent exactement quand `min + max` vaut 3 mod 4**. Sur une
somme PAIRE elles coincident ; sur `1 mod 4` aussi (le floor est pair, demi-vers-le-pair descend).
Une mesure qui ne verrait que ces regimes ne dirait RIEN -- c'est ce qui avait laisse passer le
commentaire « somme paire ici : 599+797 » du site Fury.

Ce que la garde verrouille :
A. la table de divergence des trois moyennes (et donc qu'aucune n'est substituable) ;
B. `Half` / `Divide` du DSL passent bien par `RoundFix64Result` -- mode 0 ToEven, 1 Ceiling, 2 Floor ;
C. le site Fury est cable sur `calculate_average` (TRONCATURE), pas sur `min_max_avg` ;
D. la chaine du lifesteal SpiritLeech = `ceil(min_max_avg(bornes CAPEES) x pct / 100)` -- et les
   bornes BRUTES / le bouclier n'y entrent PAS.

ASCII only.
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

from engine.dsl.base import calculate_average, _round_fix64  # noqa: E402
from engine.services.min_max_damage import min_max_avg       # noqa: E402
from engine.entities.formulas import Half, Sum, Divide       # noqa: E402
from engine.dsl.base import Const                            # noqa: E402


def _half_sum(a: int, b: int) -> int:
    """`MinMaxDamageAverage` = `Half(Sum(Direct(a), Direct(b)), rule = 0)`, arbre REEL."""
    return Half(Sum(Const(a), Const(b)), 0).calculate(None)


# (min, max) couvrant les quatre residus de `min+max` mod 4, plus les bords.
TABLE = [
    # min,  max,   somme mod 4, trunc, to_even
    (2758, 2759, 1, 2758, 2758),      # floor PAIR   -> ToEven DESCEND = trunc
    (2761, 2762, 3, 2761, 2762),      # floor IMPAIR -> ToEven MONTE  != trunc
    (599, 797, 0, 698, 698),          # somme PAIRE  -> tout le monde d'accord (le cas du commentaire)
    (4812, 6019, 3, 5415, 5416),
    (4812, 6017, 1, 5414, 5414),
    (0, 1, 1, 0, 0),
    (1, 2, 3, 1, 2),
    (2, 3, 1, 2, 2),
    (3, 4, 3, 3, 4),
]


def test_the_three_native_averages_diverge_exactly_at_3_mod_4():
    """A : la table. `calculate_average` TRONQUE, les deux autres arrondissent demi-vers-le-pair."""
    seen_diverge = 0
    for mn, mx, mod4, want_trunc, want_even in TABLE:
        s = mn + mx
        assert s % 4 == mod4, "table incoherente sur (%d,%d)" % (mn, mx)
        assert calculate_average(mn, mx) == want_trunc, (
            "`AAmountFormula$$CalculateAverage`(%d,%d) = %d, attendu %d (troncature)"
            % (mn, mx, calculate_average(mn, mx), want_trunc))
        assert min_max_avg(mn, mx) == want_even, (
            "`MinMaxDamage$$Avg`(%d,%d) = %d, attendu %d (demi-vers-le-pair)"
            % (mn, mx, min_max_avg(mn, mx), want_even))
        assert _half_sum(mn, mx) == want_even, (
            "`MinMaxDamageAverage`(%d,%d) = %d, attendu %d -- `Half(Sum(...))` doit arrondir "
            "COMME `MinMaxDamage$$Avg`, pas comme `CalculateAverage`"
            % (mn, mx, _half_sum(mn, mx), want_even))
        if want_trunc != want_even:
            seen_diverge += 1
            assert s % 4 == 3, (
                "(%d,%d) diverge hors du regime `3 mod 4` -- la RE de #339 est fausse" % (mn, mx))
    assert seen_diverge >= 3, (
        "la table n'exerce que %d cas de DIVERGENCE : elle ne separerait pas les deux familles"
        % seen_diverge)


def test_every_sum_up_to_400_agrees_outside_3_mod_4():
    """A (exhaustif) : hors `3 mod 4`, les trois moyennes sont EGALES -- c'est precisement ce qui
    rend un montage non pilote incapable de conclure."""
    for s in range(0, 400):
        mn, mx = s // 2, s - s // 2
        t, e = calculate_average(mn, mx), min_max_avg(mn, mx)
        if s % 4 == 3:
            assert e == t + 1, "somme %d : ToEven %d n'est pas trunc %d + 1" % (s, e, t)
        else:
            assert e == t, "somme %d : ToEven %d != trunc %d hors du regime 3 mod 4" % (s, e, t)


def test_round_fix64_modes_are_the_three_rules_of_RoundFix64Result():
    """B : `IdunBattle.DSL.AAmountFormula$$RoundFix64Result` -- `1`=Ceiling, `2`=Floor, sinon
    `Fix64.Round(., 0)` = demi-vers-le-pair. C'est CE dispatch qui donne son arrondi a `Half`."""
    assert _round_fix64(Fraction(5, 2), 0) == 2      # 2.5 -> 2 (pair)
    assert _round_fix64(Fraction(7, 2), 0) == 4      # 3.5 -> 4 (pair)
    assert _round_fix64(Fraction(5, 2), 1) == 3      # Ceiling
    assert _round_fix64(Fraction(5, 2), 2) == 2      # Floor
    assert Divide(Const(7), Const(2), 1).calculate(None) == 4
    assert Divide(Const(7), Const(2), 2).calculate(None) == 3
    assert Divide(Const(7), Const(2), 0).calculate(None) == 4


def test_fury_playbook_is_wired_on_the_truncating_average():
    """C : le site Fury (#32) consomme `calculate_average`, PAS `min_max_avg`. Le cablage est
    verifie sur l'objet importe par le module -- pas sur le texte du fichier."""
    import engine.playbook.fury_of_the_ancients as F
    assert F.calculate_average is calculate_average, (
        "`fury_of_the_ancients` n'importe plus `AAmountFormula$$CalculateAverage` : son montant "
        "predefini repasserait par une AUTRE moyenne que celle du natif")
    assert not hasattr(F, "min_max_avg"), (
        "`fury_of_the_ancients` importe `min_max_avg` : ce n'est PAS son artefact natif (#339)")


def test_spiritleech_lifesteal_chain_reads_the_capped_bounds_only():
    """D : `GetHealAmountForPrediction` = `PercentageOf(DamagePredictionFormula, hpToHealPct, Ceiling)`
    et `DamagePredictionFormula$$Calculate` finit par `MinMaxDamage$$Avg(prediction + 0x40)` =
    `AccurateHealthDamage`. Donc : bornes CAPEES, un SEUL arrondi, aucun bouclier.

    Le regime choisi est celui MESURE live par `probe_339_spiritleech_lifesteal.py` (bras UP) : les
    bornes brutes valent `[2758, 4139]`, les capees `[2758, 2765]`. La formule d'AVANT #339
    (brutes + bouclier, `.5` conserve) rendait `2070` la ou le natif rend `1658`."""
    pct = 60
    capped_min, capped_max = 2758, 2765
    raw_min, raw_max = 2758, 4139
    shield_min, shield_max = 0, 0

    natif = _round_fix64(Fraction(min_max_avg(capped_min, capped_max) * pct, 100), 1)
    assert min_max_avg(capped_min, capped_max) == 2762, "le `.5` a floor IMPAIR doit MONTER"
    assert natif == 1658

    avant_base = Fraction(raw_min + raw_max, 2) + Fraction(shield_min + shield_max, 2)
    avant = _round_fix64(avant_base * pct / 100, 1)
    assert avant == 2070, (
        "la formule d'avant #339 doit rendre 2070 -- sinon la garde ne temoigne plus de l'ecart")
    assert natif != avant

    # Et la troncature (l'autre moyenne native) rendrait ENCORE autre chose sur ce meme regime.
    tronque = _round_fix64(Fraction(calculate_average(capped_min, capped_max) * pct, 100), 1)
    assert tronque == 1657, (
        "sur ce regime `3 mod 4` la troncature doit rendre 1657 : les trois moyennes sont bien "
        "distinguables APRES le `Ceiling` de `PercentageOf` (il ne les ecrase pas)")
