"""#333 -- `IdunBattle.Core.Services.MinMaxDamage$$Avg` ARRONDIT, et il arrondit DEMI-VERS-LE-PAIR.

Pourquoi une garde OFFLINE en plus de la garde live (`test_333_minmax_avg_rounding_live.py`) :
**seul un `.5` EXACT separe les modes d'arrondi**, et un `.5` exact n'arrive que si `Min + Max`
est IMPAIR. Un montage live ne choisit pas la parite de ses bornes -- il l'observe. La garde qui
DISCRIMINE le mode doit donc pouvoir poser les bornes elle-meme, sur les DEUX cotes de la parite
de la partie entiere :

    | Min | Max | somme | floor | ToEven (NATIF) | AwayFromZero/half-up | troncature | port d'avant |
    |-----|-----|-------|-------|----------------|----------------------|------------|--------------|
    |   0 |   1 |     1 |     0 |            *0* |                    1 |          0 |          0.5 |
    |   1 |   2 |     3 |     1 |            *2* |                    2 |          1 |          1.5 |
    |   2 |   3 |     5 |     2 |            *2* |                    3 |          2 |          2.5 |
    |   3 |   4 |     7 |     3 |            *4* |                    4 |          3 |          3.5 |

Les lignes a `floor` PAIR (0 et 2) separent ToEven de half-up ; les lignes a `floor` IMPAIR (1 et 3)
separent ToEven de la troncature. Sans les DEUX, un vert ne dit rien -- c'est exactement ce qui
manquait a la mesure de #329, dont tous les cas IMPAIRS avaient un `floor` impair (ToEven et half-up
y coincident).

LECTURE DU DECOMPILE (`rnca9r7q6c`) qui justifie la colonne NATIF :

    IdunBattle.Core.Services.MinMaxDamage$$Avg =
        (long) Fix64.op_Explicit( Fix64.Round(
                   Fix64.op_Division( Fix64.op_Implicit(Min@+0x8) + Fix64.op_Implicit(Max@+0xc),
                                      Fix64.op_Implicit(2) ),
                   midpointRounding = 0 ) )

    FixMath.NET.Fix64$$Round(value, midpointRounding) :
        frac  = value & 0xffffffff ; integral = value & 0xffffffff00000000     # floor vers -inf
        frac <  0x80000000                      -> integral
        frac == 0x80000000 && midpointRounding == 0 -> ((value >> 0x20) & 1) == 0 ? integral
                                                                                  : integral + One
        frac == 0x80000000 && midpointRounding != 0 -> integral < Zero ? integral : integral + One
        sinon                                   -> integral + One
    (`One` = statics+0x20 = 0x100000000 et `Zero` = statics+0x28 = 0, ecrits par
     `FixMath.NET.Fix64$$.cctor`.)

`midpointRounding = 0` prend donc la branche `((value >> 0x20) & 1) == 0` = **MidpointRounding.ToEven**.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

from engine.services import fix64                            # noqa: E402
from engine.services.min_max_damage import MinMaxDamage, min_max_avg   # noqa: E402
from engine.utilities.damage import DamageUtility            # noqa: E402


# (Min, Max, valeur NATIVE lue au decompile). Les quatre premieres lignes sont le tableau de
# l'en-tete ; les suivantes rallongent la serie et ajoutent la mesure reelle de #329.
NATIVE_TABLE = [
    # somme PAIRE -> pas de .5, aucun mode ne se separe
    (0, 0, 0), (1, 1, 1), (2, 2, 2), (2514, 3768, 3141),
    # somme IMPAIRE, floor PAIR -> le natif DESCEND (c'est ce que half-up ne fait pas)
    (0, 1, 0), (2, 3, 2), (4, 5, 4), (0, 5, 2), (3770, 5652, 4711),
    # somme IMPAIRE, floor IMPAIR -> le natif MONTE (c'est ce que la troncature ne fait pas)
    (1, 2, 2), (3, 4, 4), (5, 6, 6), (0, 3, 2), (3771, 5652, 4712),
]


def _floor_half(dmin, dmax):
    return (dmin + dmax) // 2


def _half_up(dmin, dmax):
    s = dmin + dmax
    return s // 2 + (s & 1)          # AwayFromZero sur des bornes >= 0


def _kept_half(dmin, dmax):
    """L'ancien port : `(min + max) / 2.0`, le `.5` conserve."""
    return (dmin + dmax) / 2.0


@pytest.mark.parametrize("dmin,dmax,expected", NATIVE_TABLE)
def test_avg_mirrors_the_native_round_to_even(dmin, dmax, expected):
    """`min_max_avg` == la valeur lue au decompile, borne par borne."""
    got = min_max_avg(dmin, dmax)
    assert got == expected, (
        "Avg(%d, %d) = %s != %s (natif) -- somme %s, floor %s"
        % (dmin, dmax, got, expected, dmin + dmax, _floor_half(dmin, dmax)))
    assert MinMaxDamage(min=dmin, max=dmax).avg() == expected, (
        "la methode de struct diverge du corps partage")


def test_the_montage_actually_exercises_both_sides_of_the_parity():
    """La garde ne vaut QUE si la table contient les deux regimes discriminants. Sans ce controle,
    un futur elagage de `NATIVE_TABLE` rendrait les tests suivants verts et muets."""
    odd = [(a, b) for a, b, _ in NATIVE_TABLE if (a + b) % 2 == 1]
    down = [(a, b) for a, b in odd if _floor_half(a, b) % 2 == 0]
    up = [(a, b) for a, b in odd if _floor_half(a, b) % 2 == 1]
    assert down, "aucun `.5` a floor PAIR -- ToEven et demi-vers-le-haut ne sont pas separes"
    assert up, "aucun `.5` a floor IMPAIR -- ToEven et la troncature ne sont pas separees"


def test_round_to_even_is_the_only_mode_that_matches_everywhere():
    """Les trois modes concurrents SONT chacun contredits par au moins une ligne de la table.
    C'est la formulation adversariale : on ne montre pas que ToEven passe, on montre que les
    autres TOMBENT."""
    for name, fn in (("troncature `// 2`", _floor_half),
                     ("demi-vers-le-haut", _half_up),
                     ("le `.5` conserve (port d'avant #333)", _kept_half)):
        wrong = [(a, b, fn(a, b), exp) for a, b, exp in NATIVE_TABLE if fn(a, b) != exp]
        assert wrong, (
            "le mode `%s` n'est contredit par AUCUNE ligne : la table ne discrimine pas" % name)


def test_negative_bounds_follow_the_same_floor_semantics():
    """Le natif prend `floor` vers -inf (`& 0xffffffff00000000`), pas une troncature vers zero :
    -1.5 -> -2 (floor -2, PAIR) et -2.5 -> -2 (floor -3, IMPAIR -> +1). Regime non atteint par le
    rail de degat (bornes >= 0), transcrit parce que le natif le fait -- pas confronte live."""
    assert min_max_avg(-2, -1) == -2
    assert min_max_avg(-3, -2) == -2
    assert min_max_avg(-1, 0) == 0
    assert min_max_avg(-4, -3) == -4


def test_avg_is_the_composition_of_the_already_ported_fix64_primitives():
    """Le corps n'invente pas d'arithmetique : c'est `from_int`/`div`/`round_raw(mode=0)`/`to_int`.
    Et la division par 2 est EXACTE -- la fraction vaut 0 ou exactement 0x80000000, jamais autre
    chose (c'est ce qui garantit qu'aucun autre etage ne pourrait absorber le demi)."""
    for dmin, dmax, expected in NATIVE_TABLE:
        raw = fix64.div(fix64.from_int(dmin) + fix64.from_int(dmax), fix64.from_int(2))
        assert (raw & 0xFFFFFFFF) in (0, 0x80000000), (
            "Avg(%d, %d) : fraction %#x -- la division Fix64 par 2 n'est pas exacte"
            % (dmin, dmax, raw & 0xFFFFFFFF))
        assert ((raw & 0xFFFFFFFF) == 0x80000000) == ((dmin + dmax) % 2 == 1)
        assert fix64.to_int(fix64.round_raw(raw, 0)) == expected


# --------------------------------------------------------------------------------------------
# Cablage : les deux methodes de `DamageUtility` (le FOYER du rail de degat)
# --------------------------------------------------------------------------------------------

def test_damage_utility_health_and_shield_both_go_through_the_native_avg():
    """`IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage` / `$$GetShieldDamage` appellent le
    MEME `MinMaxDamage$$Avg`. Les deux doivent donc rendre un ENTIER arrondi, pas un demi."""
    u = DamageUtility()
    for dmin, dmax, expected in NATIVE_TABLE:
        assert u.get_health_damage({"healthDmgMin": dmin, "healthDmgMax": dmax}) == float(expected)
        assert u.get_shield_damage({"shieldDmgMin": dmin, "shieldDmgMax": dmax}) == float(expected)


def test_each_term_is_rounded_separately_not_their_sum():
    """`<EvaluateAttackInSteps>d__2.MoveNext` fait `Avg(health) + Avg(shield)` : DEUX arrondis, puis
    la somme. Arrondir la somme des deux demis donnerait 1 la ou le natif donne 0."""
    u = DamageUtility()
    pred = {"healthDmgMin": 0, "healthDmgMax": 1, "shieldDmgMin": 0, "shieldDmgMax": 1}
    total = u.get_health_damage(pred) + u.get_shield_damage(pred)
    assert total == 0.0, (
        "somme des deux termes = %s : les `.5` ont ete additionnes AVANT d'etre arrondis "
        "(0.5 + 0.5 = 1.0 -> 1), alors que le natif arrondit chaque `Avg` d'abord" % total)


def test_limited_by_min_hp_short_circuits_before_the_average():
    """La branche `LimitedByMinHp@+0x88` rend `Fix64(CurrentHealth@+0x00)` SANS passer par `Avg` --
    elle ne doit donc pas etre affectee par l'arrondi."""
    u = DamageUtility()
    assert u.get_health_damage({"limitedByMinHp": True, "hpBefore": 17,
                                "healthDmgMin": 0, "healthDmgMax": 1}) == 17.0


def test_the_utility_moves_by_exactly_the_rounding_delta():
    """Etage suivant : l'ecart d'un demi se propage dans `u = clamp(D/combinedMax)*80 +
    (1 - clamp((remaining - D)/combinedMax))*20`, soit `100/combinedMax` par unite de D. C'est la
    forme EXACTE de l'ecart mesure par #329 (`+2.500e-03` a `combinedMax = 20002`)."""
    max_hp = 20000
    pred = {"healthDmgMin": 3771, "healthDmgMax": 5652, "hpBefore": max_hp, "shieldBefore": 0}
    # `DamageUtility.evaluate` ne lit PAS les poids BC (ses 80/20 sont les Fix64 en dur du
    # `DamageUtility$$.cctor`) -- seules les feuilles KillUnit/OverkillUnit le font.
    u = DamageUtility().evaluate(pred, max_hp, None)

    combined_max = (max_hp + 1) + (0 + 1)
    d_native = 4712.0                                   # Avg ToEven (floor 4711 IMPAIR -> +1)
    d_old = 4711.5                                      # l'ancien port
    expect = (d_native / combined_max) * 80.0 + (1.0 - (combined_max - d_native) / combined_max) * 20.0
    old = (d_old / combined_max) * 80.0 + (1.0 - (combined_max - d_old) / combined_max) * 20.0
    assert abs(u - expect) < 1e-9, "utilite %r != %r" % (u, expect)
    assert abs((expect - old) - 0.5 * 100.0 / combined_max) < 1e-9, (
        "le pas d'utilite par unite de degat n'est pas 100/combinedMax")
