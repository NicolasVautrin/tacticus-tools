"""Noeuds ARITHMETIQUES / combinateurs numeriques du DSL (cf. base.py)."""
from __future__ import annotations

from fractions import Fraction

from .base import Node, _round_fix64


class Sum(Node):
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        return self.a.evaluate(ctx) + self.b.evaluate(ctx)


class Min(Node):
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        return min(self.a.evaluate(ctx), self.b.evaluate(ctx))


class Multiply(Node):
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        return self.a.evaluate(ctx) * self.b.evaluate(ctx)


class Difference(Node):
    """`DSLFactory.Difference(a,b) @180dedfe0` = `Sum(a, Multiply(b, -1))` = a - b."""
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        return self.a.evaluate(ctx) - self.b.evaluate(ctx)


class If(Node):
    """`DSLFactory.If(cond, a, b)` : `a` si `cond` (bool) sinon `b`. Évalue paresseusement la branche prise."""
    def __init__(self, cond: Node, a: Node, b: Node):
        self.cond, self.a, self.b = cond, a, b

    def evaluate(self, ctx):
        return (self.a if self.cond.evaluate(ctx) else self.b).evaluate(ctx)


class Max(Node):
    """`DSLFactory.Max(a,b) @180df62e0` : `max(a,b)` (singleton DAT_1832457c8, usage prouvé via
    `NonLethalDamage = Min(Max(HP-1, 0), dmg)`)."""
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        return max(self.a.evaluate(ctx), self.b.evaluate(ctx))


class Divide(Node):
    """`DSLFactory.Divide(a,b,mode) @180dee5a0` → `DivideAmount.Calculate @180f19800` :
    `Fix64(a) / Fix64(b)` PUIS `RoundFix64Result(_, mode)` — PAS une division entière. `mode` =
    Ceiling(1)/Floor(2)/Round-half-to-even(0). `b==0` → un arbre valide ne divise jamais par 0
    (laisse remonter l'erreur)."""
    def __init__(self, a: Node, b: Node, mode: int = 0):
        self.a, self.b, self.mode = a, b, mode

    def evaluate(self, ctx):
        return _round_fix64(Fraction(self.a.evaluate(ctx), self.b.evaluate(ctx)), self.mode)


class Half(Node):
    """`DSLFactory.Half(a,mode) @180df0840` = `Divide(a, 2, mode)` — MÊME arrondi Fix64 (pas `a//2`)."""
    def __init__(self, a: Node, mode: int = 0):
        self.a, self.mode = a, mode

    def evaluate(self, ctx):
        return _round_fix64(Fraction(self.a.evaluate(ctx), 2), self.mode)


class Double(Node):
    """`DSLFactory.Double(a) @180dee6f0` = `Multiply(a, 2)` = `a * 2` (entier exact, sans arrondi)."""
    def __init__(self, a: Node):
        self.a = a

    def evaluate(self, ctx):
        return self.a.evaluate(ctx) * 2


class Negative(Node):
    """`DSLFactory.Negative(a) @180df7090` = `Multiply(a, -1)` = `-a`."""
    def __init__(self, a: Node):
        self.a = a

    def evaluate(self, ctx):
        return -self.a.evaluate(ctx)


class PercentageOf(Node):
    """`DSLFactory.PercentageOf(pct, base, mode) @180df8720` → `PercentageOf.Calculate @180f20fc0`
    (Fix64) : `round_mode(pct% * base)` avec arrondis intermédiaires half-to-even à 2 décimales — PAS
    `pct*base//100`. `pct` = pourcentage entier (50 = 50 %). Les arrondis à 2 décimales sont INERTES
    pour des opérandes entières (nos cas) → `round_mode(Fraction(pct*base, 100))` fidèle."""
    def __init__(self, pct: Node, base: Node, mode: int = 0):
        self.pct, self.base, self.mode = pct, base, mode

    def evaluate(self, ctx):
        return _round_fix64(Fraction(self.pct.evaluate(ctx) * self.base.evaluate(ctx), 100), self.mode)


class Count(Node):
    """`DSLFactory.Count(selector) @180decfa0` → `CountFormula.Calculate @180f18040` : cardinal du
    sélecteur (nb d'éléments). Retour int >= 0."""
    def __init__(self, selector: Node):
        self.selector = selector

    def evaluate(self, ctx):
        return len(self.selector.evaluate(ctx))
