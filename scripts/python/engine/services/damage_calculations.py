"""Port FIDÈLE de `IdunBattle.Core.Services.DamageCalculations` (gqfc5mff6c)."""
from __future__ import annotations

from . import fix64 as _fx
from .min_max_damage import MinMaxDamage


def calculate_damage_spread(base: int, spread_pct: int = 20) -> int:
    """DamageCalculations.CalculateDamageSpread (IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread) — ARITHMÉTIQUE Fix64 EXACTE (#30a) :
        frac  = Fix64Div(FromInt(spread_pct), FromInt(100))   # div ARRONDI (0.2 → raw 858993459),
                                                              # caché Nullable this+0x38 côté natif
        delta = Round(base × frac, AwayFromZero)              # mul TRONQUANT puis Round mode 1
    Renvoie le DELTA (demi-amplitude). min = base − delta ; max = base + delta.
    Mesuré (u92) : base 2530, delta 506 = 2530×0.20 → 2024..3036. ✓ (pct=20 : identique au
    `round(base×0.2)` float historique pour tout base entier — l'exactitude compte pour les pct
    où base×pct/100 tombe pile sur .5, ex. pct=50 base impair : natif AwayFromZero, round() ToEven.)"""
    # `base` peut arriver en float legacy (avg(minDmg,maxDmg) scalé rareté, prediction.py) →
    # from_number (int = exact ; float = nearest, même approximation que le round() historique).
    frac = _fx.div(_fx.from_int(spread_pct), _fx.from_int(100))
    return _fx.to_int(_fx.round_raw(_fx.mul(_fx.from_number(base), frac), 1))


def spread_to_min_max(base: int, spread_pct: int = 20,
                      cap: int | None = None) -> MinMaxDamage:
    """Construit MinMaxDamage(base−delta, base+delta) via CalculateDamageSpread."""
    delta = calculate_damage_spread(base, spread_pct)
    return MinMaxDamage(min=base - delta, max=base + delta, cap=cap)
