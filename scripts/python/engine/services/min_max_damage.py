"""Port FIDÈLE de `IdunBattle.Core.Services.MinMaxDamage` (struct + méthodes).

1:1 avec le natif (build gqfc5mff6c). Chaque méthode = sa jumelle live, même nom, même logique ;
VA citée pour re-vérification. cf. directive « la structure Python colle à la structure live ».
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MinMaxDamage:
    """struct MinMaxDamage. Champs (offsets natifs entre parenthèses) :
      Cap (Nullable<int>) @0x0 (HasValue + value) · Min @0x8 · Max @0xc.
    `cap=None` ⇔ Nullable.HasValue=false."""
    min: int = 0
    max: int = 0
    cap: int | None = None

    def apply_cap(self) -> None:
        """MinMaxDamage.ApplyCap (@181052380) : si Cap.HasValue, Min=Min(Min,Cap), Max=Min(Max,Cap)."""
        if self.cap is None:
            return
        if self.min > self.cap:
            self.min = self.cap
        if self.max > self.cap:
            self.max = self.cap

    def avg(self) -> int:
        """MinMaxDamage.Avg (@181052470) : (Min+Max)/2 (division entière Fix64→int)."""
        return (self.min + self.max) // 2

    def add(self, other: "MinMaxDamage") -> "MinMaxDamage":
        """MinMaxDamage.Add (@1810522c0) : somme composante par composante."""
        return MinMaxDamage(min=self.min + other.min, max=self.max + other.max, cap=self.cap)
