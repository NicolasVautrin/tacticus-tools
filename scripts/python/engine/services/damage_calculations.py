"""Port FIDÈLE de `IdunBattle.Core.Services.DamageCalculations` (gqfc5mff6c)."""
from __future__ import annotations

from .min_max_damage import MinMaxDamage


def calculate_damage_spread(base: int, spread_pct: int = 20) -> int:
    """DamageCalculations.CalculateDamageSpread (@1810028e0) :
        delta = Round(base × DamageSpreadPercentage/100)   # DamageSpreadPercentage (BC.Damage) = 20
    Renvoie le DELTA (demi-amplitude). min = base − delta ; max = base + delta.
    Mesuré (u92) : base 2530, delta 506 = 2530×0.20 → 2024..3036. ✓"""
    return round(base * spread_pct / 100.0)


def spread_to_min_max(base: int, spread_pct: int = 20,
                      cap: int | None = None) -> MinMaxDamage:
    """Construit MinMaxDamage(base−delta, base+delta) via CalculateDamageSpread."""
    delta = calculate_damage_spread(base, spread_pct)
    return MinMaxDamage(min=base - delta, max=base + delta, cap=cap)
