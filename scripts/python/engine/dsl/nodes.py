"""Socle DSL GÉNÉRIQUE — moteur de NŒUDS (mirror 1:1 du DSL lazy du jeu, `DSLFactory`/`TargetsSelector`).

Le jeu définit chaque formule d'ability (`GetHits`, `GetSurroundingUnits`, `GetOtherTargets`, …) comme un
**arbre d'expression lazy** : `Sum(a, b)` est un NŒUD dont les opérandes `a`, `b` sont des sous-arbres
(ex. `Multiply(ConfigConst(extraHit), TotalTimesAttacked())`), évalué contre l'état de bataille au bon
instant. On mirroir cette structure 1:1 (règle projet « le Python reflète la structure du jeu ») : un
`Node` par primitive, un évaluateur unique `Node.evaluate(ctx)`. Chaque ability = l'arbre EXACT du
décompilé, vérifiable nœud-par-nœud (cf. active_ability.py, VA citées).

⚠ **Ghidra MISLABEL les ctors de nœuds gshared** (le ctor de `DSLFactory.Sum @180dfc200` s'affiche
`HasUsedActiveAbilityThisTurnTrigger$$.ctor`) → sémantique lue via la STRUCTURE (pointeur de classe, args
enfants, arithmétique), JAMAIS via les noms. cf. [[feedback_re_ghidra_not_experiment]].

Types de valeur (comme le DSL natif, typé) : les nœuds NUMÉRIQUES → int ; CONDITION → bool ; POSITION →
(col,row) ; CIBLAGE → list[unit]. Unité = dict `{id, team, hp, alive, pos:{col,row}, visualId}` (step_context).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import hexgeo


@dataclass
class DslContext:
    """Contexte d'évaluation d'un arbre DSL (l'« état de bataille » que le nœud interroge).

    `config`/`ability_level` → `ConfigConst` ; `caster`/`target`/`units` → ciblage + positions ;
    `times_attacked` = compteur runtime du caster (`TotalTimesAttackedFormula @180f26620`, composant @+0x34)
    NON capté offline → défaut 0 ; `flags` = ensemble de flags actifs (`HasFlag`). `units`/`caster`/`target`
    ne sont requis que par les nœuds de CIBLAGE (AoE) — un arbre purement numérique (hits) les ignore."""
    units: list = field(default_factory=list)
    caster: dict | None = None
    target: dict | None = None
    config: object | None = None            # AbilityConfiguration
    ability_level: int = 0
    times_attacked: int = 0
    flags: frozenset = field(default_factory=frozenset)


class Node:
    """Nœud DSL. `evaluate(ctx)` = valeur résolue contre l'état (int/bool/pos/list selon le nœud)."""
    def evaluate(self, ctx: DslContext):
        raise NotImplementedError


# ── Feuilles numériques ───────────────────────────────────────────────────────────────────────
class Const(Node):
    """`DSLFactory.Direct(value)` : constante littérale."""
    def __init__(self, value: int):
        self.value = value

    def evaluate(self, ctx):
        return self.value


class ConfigConst(Node):
    """`DSLFactory.ConfigConst(key)` / `AbilityConfiguration.GetNumberConstant` : constante de config
    d'ability au niveau courant (ids natifs : 0x2f=nrOfHits, 0x2b=extraHit, 0x48=maxNrOfHits, 0x16=radius)."""
    def __init__(self, key: str, default: int = 0):
        self.key, self.default = key, default

    def evaluate(self, ctx):
        if ctx.config is None:
            return self.default
        return ctx.config.get_variable_for_level(self.key, ctx.ability_level, self.default)


# ── Opérateurs numériques (ctors @180dfc200/180df6930/180dedfe0 — arithmétique confirmée) ───────
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


# ── Feuilles runtime / condition ─────────────────────────────────────────────────────────────
class TotalTimesAttacked(Node):
    """`TotalTimesAttackedFormula.Calculate @180f26620` : compteur runtime d'attaques du caster
    (composant @+0x34). NON capté offline → `ctx.times_attacked` (défaut 0 = pré-snowball)."""
    def evaluate(self, ctx):
        return ctx.times_attacked or 0


class HasFlag(Node):
    """`DSLFactory.HasFlag(flag)` : `flag ∈ ctx.flags`. Le sens exact du flag (ex. HarvesterOfSouls @+0x160)
    reste à RE ; défaut = absent (branche `flag=false`), confirmé par l'agrément."""
    def __init__(self, flag):
        self.flag = flag

    def evaluate(self, ctx):
        return self.flag in ctx.flags


# ── Positions (centres de ciblage) ─────────────────────────────────────────────────────────────
def _pos(u):
    p = u.get("pos") if u else None
    return (p["col"], p["row"]) if p else None


class CasterTile(Node):
    """Tuile du caster (`UnitPosition.MainTile` du caster) — centre d'`AdjacentEnemies`."""
    def evaluate(self, ctx):
        return _pos(ctx.caster)


class TargetTile(Node):
    """Tuile de la cible principale (`MainTile` de la cible) — centre de `SurroundingUnits`."""
    def evaluate(self, ctx):
        return _pos(ctx.target)


# ── Ciblage (évaluent → list[unit]) — géométrie hex `hexgeo.distance` fidèle à la grille ─────────
def _within(units, center, radius, include_center=False):
    out = []
    for u in units:
        p = _pos(u)
        if p is None:
            continue
        d = hexgeo.distance(p, center)
        if d <= radius and (include_center or d > 0):
            out.append(u)
    return out


class SurroundingUnits(Node):
    """`DSLFactory.SurroundingUnits(center, radius) @180dfcb70` = `Units(SurroundingTiles(center, radius))`
    = unités à distance hex <= radius du centre, centre exclu."""
    def __init__(self, center: Node, radius: Node):
        self.center, self.radius = center, radius

    def evaluate(self, ctx):
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))


class AdjacentEnemies(Node):
    """`DSLFactory.AdjacentEnemies(caster) @180de80c0` = `Enemies(Units(AdjacentTiles(caster)) - {caster})`
    = ennemis (team != caster) à dist <= radius du caster, self exclu."""
    def __init__(self, center: Node, radius: Node | None = None):
        self.center, self.radius = center, radius or Const(1)

    def evaluate(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") != ct]


class Enemies(Node):
    """`DSLFactory.Enemies` : filtre → équipe != celle du caster."""
    def __init__(self, inner: Node):
        self.inner = inner

    def evaluate(self, ctx):
        ct = (ctx.caster or {}).get("team")
        return [u for u in self.inner.evaluate(ctx) if u.get("team") != ct]


class Damageable(Node):
    """`DSLFactory.Damageable` : filtre → unités vivantes ciblables (PV > 0)."""
    def __init__(self, inner: Node):
        self.inner = inner

    def evaluate(self, ctx):
        return [u for u in self.inner.evaluate(ctx)
                if bool(u.get("alive", True)) and (u.get("hp") or 0) > 0]


class And(Node):
    """`TargetsSelector.op_BitwiseAnd` : intersection par id."""
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        bset = {u.get("id") for u in self.b.evaluate(ctx)}
        return [u for u in self.a.evaluate(ctx) if u.get("id") in bset]


class Sub(Node):
    """`TargetsSelector.op_Subtraction` : a \\ b par id."""
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        bset = {u.get("id") for u in self.b.evaluate(ctx)}
        return [u for u in self.a.evaluate(ctx) if u.get("id") not in bset]


class UnitSet(Node):
    """Feuille = un ensemble d'unités explicite (ex. `{mainTarget}` pour la soustraction AoE)."""
    def __init__(self, units: list):
        self.units = units

    def evaluate(self, ctx):
        return list(self.units)
