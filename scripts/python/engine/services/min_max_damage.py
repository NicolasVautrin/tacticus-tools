"""Port FIDÈLE de `IdunBattle.Core.Services.MinMaxDamage` (struct + méthodes).

1:1 avec le natif (relu au décompilé `rnca9r7q6c` pour `Avg`). Chaque méthode = sa jumelle live,
même nom, même logique. cf. directive « la structure Python colle à la structure live ».
"""
from __future__ import annotations

from dataclasses import dataclass

from . import fix64


def min_max_avg(dmg_min: int, dmg_max: int) -> int:
    """Corps de `IdunBattle.Core.Services.MinMaxDamage$$Avg`, exposé hors de la struct parce que le
    rail DÉCISION lit un dict de prédiction APLATI (`engine.utilities.damage.DamageUtility`) et n'a
    pas de `MinMaxDamage` à matérialiser.

    Décompilé `rnca9r7q6c`, lu VERBATIM (aucun étage déduit) :

        Fix64.op_Explicit( Fix64.Round( Fix64.op_Division(
            Fix64.op_Implicit(this.Min@+0x8) + Fix64.op_Implicit(this.Max@+0xc),
            Fix64.op_Implicit(2) ), midpointRounding = 0 ) )

    Les quatre étages, composés ici avec les mirrors DÉJÀ portés de `engine.services.fix64` :

    - `FixMath.NET.Fix64$$op_Implicit` (int → Fix64) = `(long)(int)v << 32` → `fix64.from_int` ;
    - `FixMath.NET.Fix64$$op_Addition` = addition des raw (pas de saturation émulée, cf. en-tête
      de `fix64`) ;
    - `FixMath.NET.Fix64$$op_Division` → `fix64.div`. EXACTE ici : le quotient est accumulé à
      2^-33 puis `(q+1)>>1`, ce qui rend `(Min+Max) << 31` — donc une fraction valant 0 (somme
      PAIRE) ou exactement `0x80000000` (somme IMPAIRE), jamais autre chose ;
    - `FixMath.NET.Fix64$$Round(value, 0)` → `fix64.round_raw(..., mode=0)`. **`midpointRounding = 0`
      est `MidpointRounding.ToEven`** : le corps teste `((value >> 0x20) & 1) == 0` sur la partie
      ENTIÈRE quand la fraction vaut exactement `0x80000000`, et rend le `floor` si elle est PAIRE,
      `floor + One` sinon (`One` = `Fix64` statics+0x20 = `0x100000000`, lu dans
      `FixMath.NET.Fix64$$.cctor`). L'autre branche (`midpointRounding != 0` = `AwayFromZero`)
      compare à `Zero` = statics+0x28 = 0 — ce n'est PAS celle-ci ;
    - `FixMath.NET.Fix64$$op_Explicit` (Fix64 → long) = `raw >> 32` → `fix64.to_int`. Exact après
      `Round`, qui rend déjà un raw intégral.

    ⚠ Somme IMPAIRE = `.5` EXACT, et c'est le SEUL régime où les modes d'arrondi se séparent :
    demi-vers-le-PAIR DESCEND quand la partie entière est déjà paire (`0.5 → 0`, `2.5 → 2`) et
    MONTE sinon (`1.5 → 2`, `3.5 → 4`). Ni troncature (`// 2`), ni demi-vers-le-haut, ni le `.5`
    conservé — les trois coïncident avec le natif sur une moitié des cas seulement.

    `Min`/`Max` sont des `int` natifs (champs 32 bits @+0x8/+0xc lus par `Avg`) : un flottant chez
    un producteur du port serait un bug de ce producteur, la coercion ne le fabrique pas."""
    raw = fix64.div(fix64.from_int(int(dmg_min)) + fix64.from_int(int(dmg_max)),
                    fix64.from_int(2))
    return fix64.to_int(fix64.round_raw(raw, 0))


@dataclass
class MinMaxDamage:
    """struct MinMaxDamage. Champs (offsets natifs entre parenthèses) :
      Cap (Nullable<int>) @0x0 (HasValue + value) · Min @0x8 · Max @0xc.
    `cap=None` ⇔ Nullable.HasValue=false."""
    min: int = 0
    max: int = 0
    cap: int | None = None

    def apply_cap(self) -> None:
        """MinMaxDamage.ApplyCap (IdunBattle.Core.Services.MinMaxDamage$$ApplyCap) : si Cap.HasValue, Min=Min(Min,Cap), Max=Min(Max,Cap)."""
        if self.cap is None:
            return
        if self.min > self.cap:
            self.min = self.cap
        if self.max > self.cap:
            self.max = self.cap

    def avg(self) -> int:
        """MinMaxDamage.Avg (`IdunBattle.Core.Services.MinMaxDamage$$Avg`) : `(long)Fix64.Round(
        (Fix64(Min) + Fix64(Max)) / Fix64(2), midpointRounding = 0)` — arrondi DEMI-VERS-LE-PAIR.
        Corps + lecture du décompilé : `min_max_avg`."""
        return min_max_avg(self.min, self.max)

    def add(self, other: "MinMaxDamage") -> "MinMaxDamage":
        """MinMaxDamage.Add (IdunBattle.Core.Services.MinMaxDamage$$Add) : somme composante par composante."""
        return MinMaxDamage(min=self.min + other.min, max=self.max + other.max, cap=self.cap)
