"""Noeuds VALEUR du DSL = famille `AAmountFormula.Calculate` (kind V) : arithmetique/combinateurs
numeriques + accesseurs config/stat/compteurs runtime.

Mirror du namespace natif `IdunBattle.Entities.Formulas` : les concrets vivent ici, a cote de leurs
freres `entities/{abilities,selectors,triggers,behaviours,effects}` ; la base `AAmountFormula`
(= `IdunBattle.DSL`) reste dans `dsl/base.py`. Construits via la facade `DSLFactory` (`dsl/nodes.py`)."""
from __future__ import annotations

from fractions import Fraction

from ..dsl.base import (AAmountFormula, TargetsSelector, Const, _round_fix64, _effect_field,
                        _default_get_stat, resolve_unit)


class Sum(AAmountFormula):
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return self.a.evaluate(ctx) + self.b.evaluate(ctx)


class Min(AAmountFormula):
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return min(self.a.evaluate(ctx), self.b.evaluate(ctx))


class Multiply(AAmountFormula):
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return self.a.evaluate(ctx) * self.b.evaluate(ctx)


class Difference(AAmountFormula):
    """`DSLFactory.Difference(a,b) @180dedfe0` = `Sum(a, Multiply(b, -1))` = a - b."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return self.a.evaluate(ctx) - self.b.evaluate(ctx)


class If(AAmountFormula):
    """`DSLFactory.If(cond, a, b)` : `a` si `cond` (bool) sinon `b`. Évalue paresseusement la branche prise."""
    def __init__(self, cond: AAmountFormula, a: AAmountFormula, b: AAmountFormula):
        self.cond, self.a, self.b = cond, a, b

    def calculate(self, ctx):
        return (self.a if self.cond.evaluate(ctx) else self.b).evaluate(ctx)


class Max(AAmountFormula):
    """`DSLFactory.Max(a,b) @180df62e0` : `max(a,b)` (singleton DAT_1832457c8, usage prouvé via
    `NonLethalDamage = Min(Max(HP-1, 0), dmg)`)."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return max(self.a.evaluate(ctx), self.b.evaluate(ctx))


class Divide(AAmountFormula):
    """`DSLFactory.Divide(a,b,mode) @180dee5a0` → `DivideAmount.Calculate @180f19800` :
    `Fix64(a) / Fix64(b)` PUIS `RoundFix64Result(_, mode)` — PAS une division entière. `mode` =
    Ceiling(1)/Floor(2)/Round-half-to-even(0). `b==0` → un arbre valide ne divise jamais par 0
    (laisse remonter l'erreur)."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula, mode: int = 0):
        self.a, self.b, self.mode = a, b, mode

    def calculate(self, ctx):
        return _round_fix64(Fraction(self.a.evaluate(ctx), self.b.evaluate(ctx)), self.mode)


class Half(AAmountFormula):
    """`DSLFactory.Half(a,mode) @180df0840` = `Divide(a, 2, mode)` — MÊME arrondi Fix64 (pas `a//2`)."""
    def __init__(self, a: AAmountFormula, mode: int = 0):
        self.a, self.mode = a, mode

    def calculate(self, ctx):
        return _round_fix64(Fraction(self.a.evaluate(ctx), 2), self.mode)


class Double(AAmountFormula):
    """`DSLFactory.Double(a) @180dee6f0` = `Multiply(a, 2)` = `a * 2` (entier exact, sans arrondi)."""
    def __init__(self, a: AAmountFormula):
        self.a = a

    def calculate(self, ctx):
        return self.a.evaluate(ctx) * 2


class Negative(AAmountFormula):
    """`DSLFactory.Negative(a) @180df7090` = `Multiply(a, -1)` = `-a`."""
    def __init__(self, a: AAmountFormula):
        self.a = a

    def calculate(self, ctx):
        return -self.a.evaluate(ctx)


class PercentageOf(AAmountFormula):
    """`DSLFactory.PercentageOf(pct, base, mode) @180df8720` → `PercentageOf.Calculate @180f20fc0`
    (Fix64) : `round_mode(pct% * base)` avec arrondis intermédiaires half-to-even à 2 décimales — PAS
    `pct*base//100`. `pct` = pourcentage entier (50 = 50 %). Les arrondis à 2 décimales sont INERTES
    pour des opérandes entières (nos cas) → `round_mode(Fraction(pct*base, 100))` fidèle."""
    def __init__(self, pct: AAmountFormula, base: AAmountFormula, mode: int = 0):
        self.pct, self.base, self.mode = pct, base, mode

    def calculate(self, ctx):
        return _round_fix64(Fraction(self.pct.evaluate(ctx) * self.base.evaluate(ctx), 100), self.mode)


class Count(AAmountFormula):
    """`DSLFactory.Count(selector) @180decfa0` → `CountFormula.Calculate @180f18040` : cardinal du
    sélecteur (nb d'éléments). Retour int >= 0."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        return len(self.selector.evaluate(ctx))


# --- Accesseurs VALEUR (mirror `DSLFactory.X` -> formules natives : config / stat / compteurs). ---

class ConfigConst(AAmountFormula):
    """`DSLFactory.ConfigConst(key)` / `AbilityConfiguration.GetNumberConstant` : constante de config
    d'ability au niveau courant. Ids natifs = enum `AbilityConstantType` (dump.cs TypeDefIndex 24411) :
    0x2f=nrOfHits(47), 0x2b=extraHit(43), 0x48=maxNrOfHits(72), 0x16=range(22). ⚠ `GetNumberConstant
    @181576af0`->`GetStringConstant @181576bb0` LÈVE une exception si la clé est ABSENTE (TryGetValue
    échoue -> throw) : une clé référencée par un arbre EST toujours présente dans la config (jamais de
    défaut natif). ⚠ DIVERGENCE assumée : le `default` Python retourne une valeur là où le natif
    THROW — garde-fou offline inerte tant que la clé existe, mais il MASQUERAIT silencieusement une
    clé manquante (verdict validator 2026-07-02 : réserve non bloquante)."""
    def __init__(self, key: str, default: int = 0):
        self.key, self.default = key, default

    def calculate(self, ctx):
        if ctx.config is None:
            return self.default
        return ctx.config.get_variable_for_level(self.key, ctx.ability_level, self.default)


class TotalTimesAttacked(AAmountFormula):
    """`TotalTimesAttackedFormula.Calculate @180f26620` : compteur runtime d'attaques du caster
    (composant @+0x34). NON capté offline → `ctx.times_attacked` (défaut 0 = pré-snowball)."""
    def calculate(self, ctx):
        return ctx.times_attacked or 0


class TimesRepaired(AAmountFormula):
    """`DSLFactory.TimesRepaired` : compteur runtime de réparations du caster (Mechanical — ex.
    DakkaDakkaDakka `GetNumHits @1811d0eb0` : +extraHits coups par réparation). NON capté offline →
    `ctx.times_repaired` (défaut 0 = pré-snowball)."""
    def calculate(self, ctx):
        return getattr(ctx, "times_repaired", 0) or 0


class TotalAttacksMade(AAmountFormula):
    """`DSLFactory.TotalAttacksMade @180dfe090` = `Entities.Formulas.TotalAttacksMadeFormula` (@180f25b90) :
    nb d'attaques faites par `unit` (compteur runtime). Port on-appearance : la feuille `PerformAIAttack`
    (`runner/abilities/behaviours.py`) pose `_attacks_made` sur le dict de l'enfant (0 si pas d'attaque).
    Unité hors-cast → 0 (compteur général non capté offline, même régime que `TotalTimesAttacked`)."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = resolve_unit(self.unit, ctx)
        return int((u or {}).get("_attacks_made", 0) or 0)


class UnitTurnsStarted(AAmountFormula):
    """`DSLFactory.UnitTurnsStarted @180dff280` = `Entities.Formulas.UnitTurnsStartedFormula` (@180f2d6c0) :
    nb de tours entamés par `unit` (compteur runtime). Le natif compare (via `AmountIsEqual`) le `turnsStarted`
    de l'owner CAPTURÉ au cast (`factory+0xb8`) au `UnitTurnsStarted(child)` → ne retient que les enfants NEUFS
    de CE cast. Offline le compteur n'est pas capté → `_turns_started` de l'enfant (SpawnUnit pose 0) ; couplé
    à `Const(0)` (owner fraîchement dans nos runners) l'égalité tient EXACTEMENT comme le natif la satisfait
    pour les enfants neufs. Unité hors-cast → 0. ⚠ Mid-bataille (owner turnsStarted>0) ce couple dégradé
    demanderait les vrais compteurs runtime (gap offline documenté, même régime que `times_attacked`)."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = resolve_unit(self.unit, ctx)
        return int((u or {}).get("_turns_started", 0) or 0)


class TurnsFromRounds(AAmountFormula):
    """`DSLFactory.TurnsFromRounds(rounds) @180dfec50` → `TurnsFromRoundsFormula.Calculate @180f26a50`
    = `BattleQuery.ConvertRoundsToTurns @181058af0` (interface slot 0x1b) = `count(joueurs du turnOrder,
    PlayerType != 2) * rounds` (RE #174 : PlayerType@+0x20 = config statique, Environment=2 exclu ;
    count = CONSTANTE de bataille). `rounds * ctx.turns_per_round` avec `turns_per_round = count(non-Env)`.
    Defaut 1 = CORRECT pour nos runners 1v1 (count=1 PROUVE par test_effect_stun_live : convert(1)=1) ;
    ne divergerait que dans une bataille count>=2 (non simulee), a capter alors du turnOrder runtime."""
    def __init__(self, rounds: AAmountFormula):
        self.rounds = rounds

    def calculate(self, ctx):
        return self.rounds.evaluate(ctx) * getattr(ctx, "turns_per_round", 1)


class Get(Const):
    """`DSLFactory.Get(value) @180df05d0` = `Const`/`Direct` : enveloppe une valeur littérale int/enum en
    nœud (MÊME singleton DAT_183202d40 + ctor `(value,0)` que `Direct`). Le nom de ctor mislabelé
    `IceTileEffect...d__5` est un trampoline gshared — la classe réelle est le nœud constante, PAS un
    accesseur. (Les overloads Get @180df0690/@180df0630 sur arg objet = sélecteurs distincts, hors batch.)"""


class ConfigVar(AAmountFormula):
    """`DSLFactory.ConfigVar(key) @180decac0` → `Formulas.ConfigAmount.Calculate @180f171c0` :
    `AbilityConfiguration.GetVariableForLevel(key, level)` = valeur du tableau de config SCALÉE par le
    niveau de l'ability. ≠ `ConfigConst` natif (`GetNumberConstant`, valeur fixe hors niveau). Cas
    standard = caster au niveau courant → `ctx.ability_level` ; niveau d'une unité tierce = NON offline.
    ⚠ RÉSERVE (validator) : le `ConfigConst` Python actuel appelle DÉJÀ `get_variable_for_level` — donc
    fait le boulot de ConfigVar, pas de ConfigConst (qui devrait être number-constant fixe). À trancher :
    le wrapper AbilityConfiguration distingue-t-il number-constant (fixe) vs variable-array (par niveau) ?"""
    def __init__(self, key: str, default: int = 0):
        self.key, self.default = key, default

    def calculate(self, ctx):
        if ctx.config is None:
            return self.default
        return ctx.config.get_variable_for_level(self.key, ctx.ability_level, self.default)


class StatAmount(AAmountFormula):
    """`DSLFactory.StatAmount(selector, statType, variant, level) @180dfbf60` →
    `StatAmountFormula.Calculate @180f22d40` : SOMME de `UnitExtensions.GetStat(unit, statType, variant,
    level)` sur toutes les unités du sélecteur (singleton → 1 unité ; multi → somme). `ctx.get_stat`
    fournit les stats réelles ; défaut dégradé = Health via hp (cf. `_default_get_stat`)."""
    def __init__(self, selector: TargetsSelector, stat_type: int, variant: int = 0,
                 level: AAmountFormula | None = None):
        self.selector, self.stat_type, self.variant, self.level = selector, stat_type, variant, level

    def calculate(self, ctx):
        gs = ctx.get_stat or _default_get_stat
        lvl = self.level.evaluate(ctx) if self.level is not None else None
        return sum(gs(u, self.stat_type, self.variant, lvl) for u in self.selector.evaluate(ctx))


class EntityId(AAmountFormula):
    """`DSLFactory.EntityId(ref) @180def470` : id de l'entité résolue (ou None)."""
    def __init__(self, ref):
        self.ref = ref

    def calculate(self, ctx):
        e = self.ref.evaluate(ctx)
        return e.get("id") if isinstance(e, dict) else None


class EffectLevel(AAmountFormula):
    """`DSLFactory.EffectLevel @180deead0` : niveau de l'effet COURANT (`ctx.effect`). 0 si absent."""
    def calculate(self, ctx):
        return _effect_field(ctx.effect, "level", 0)
