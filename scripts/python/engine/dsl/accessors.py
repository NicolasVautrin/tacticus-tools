"""Noeuds ACCESSEURS d'etat / contexte du DSL (cf. base.py)."""
from __future__ import annotations

from .base import Node, Const, _pos, _effect_field, _default_get_stat


class ConfigConst(Node):
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

    def evaluate(self, ctx):
        if ctx.config is None:
            return self.default
        return ctx.config.get_variable_for_level(self.key, ctx.ability_level, self.default)


class TotalTimesAttacked(Node):
    """`TotalTimesAttackedFormula.Calculate @180f26620` : compteur runtime d'attaques du caster
    (composant @+0x34). NON capté offline → `ctx.times_attacked` (défaut 0 = pré-snowball)."""
    def evaluate(self, ctx):
        return ctx.times_attacked or 0


class TimesRepaired(Node):
    """`DSLFactory.TimesRepaired` : compteur runtime de réparations du caster (Mechanical — ex.
    DakkaDakkaDakka `GetNumHits @1811d0eb0` : +extraHits coups par réparation). NON capté offline →
    `ctx.times_repaired` (défaut 0 = pré-snowball)."""
    def evaluate(self, ctx):
        return getattr(ctx, "times_repaired", 0) or 0


class TurnsFromRounds(Node):
    """`DSLFactory.TurnsFromRounds(rounds) @180dfec50` → `TurnsFromRoundsFormula.Calculate @180f26a50`
    = `BattleQuery.ConvertRoundsToTurns @181058af0` (interface slot 0x1b) = `count(joueurs du turnOrder,
    PlayerType != 2) * rounds` (RE #174 : PlayerType@+0x20 = config statique, Environment=2 exclu ;
    count = CONSTANTE de bataille). `rounds * ctx.turns_per_round` avec `turns_per_round = count(non-Env)`.
    Defaut 1 = CORRECT pour nos runners 1v1 (count=1 PROUVE par test_effect_stun_live : convert(1)=1) ;
    ne divergerait que dans une bataille count>=2 (non simulee), a capter alors du turnOrder runtime."""
    def __init__(self, rounds: Node):
        self.rounds = rounds

    def evaluate(self, ctx):
        return self.rounds.evaluate(ctx) * getattr(ctx, "turns_per_round", 1)


class CasterTile(Node):
    """Tuile du caster (`UnitPosition.MainTile` du casterPosition passé par le generator) — pour une
    décision balayée c'est la TUILE D'ATTAQUE candidate (`ctx.caster_pos`), pas la position courante."""
    def evaluate(self, ctx):
        return ctx.caster_pos or _pos(ctx.caster)


class TargetTile(Node):
    """Tuile de la cible principale (`MainTile` de la cible) — centre de `SurroundingUnits`."""
    def evaluate(self, ctx):
        return _pos(ctx.target)


class OwnerTile(Node):
    """Tuile COURANTE (réelle) de l'owner/caster — position du composant entité, PAS la tuile d'attaque
    balayée. `HarvesterOfSoulsAbility.GetSurroundingUnits @1811e76a0` ancre son `SurroundingUnits(sel@0x160,
    range)` sur ce sélecteur (sel@0x160 = OWNER : cf. `StatAmount(@0x160,Health)`=maxHP caster dans
    `DakkaDakkaDakka.GetHealthToLose @1811d09a0`, `HasFlag(@0x160)` du caster dans `Harvester.GetHits`).
    La fonction native ne reçoit AUCUN `casterPosition` (elle ne prend que l'ability) -> sel@0x160 résout
    la position LIVE de l'owner (non déplacé pendant la prédiction), != `CasterTile` (= `ctx.caster_pos`,
    la tuile d'attaque post-move). Preuve ground-truth seed777 step-17 : AoE ancré sur (5,6)=owner-réel
    (et non (4,3)=tuile d'attaque) reproduit les 4 sets natifs (cf. active_ability.HarvesterOfSoulsAbility)."""
    def evaluate(self, ctx):
        return _pos(ctx.caster)


class Subject(Node):
    """Élément COURANT lié par un `Filter` (mirror du sélecteur-sujet natif `ability+0x180` =
    OriginalTarget). Les prédicats sous un `Filter` lisent leur sujet ici ; hors Filter → `ctx.subject`
    (None par défaut)."""
    def evaluate(self, ctx):
        return ctx.subject


class Get(Const):
    """`DSLFactory.Get(value) @180df05d0` = `Const`/`Direct` : enveloppe une valeur littérale int/enum en
    nœud (MÊME singleton DAT_183202d40 + ctor `(value,0)` que `Direct`). Le nom de ctor mislabelé
    `IceTileEffect...d__5` est un trampoline gshared — la classe réelle est le nœud constante, PAS un
    accesseur. (Les overloads Get @180df0690/@180df0630 sur arg objet = sélecteurs distincts, hors batch.)"""


class ConfigVar(Node):
    """`DSLFactory.ConfigVar(key) @180decac0` → `Formulas.ConfigAmount.Calculate @180f171c0` :
    `AbilityConfiguration.GetVariableForLevel(key, level)` = valeur du tableau de config SCALÉE par le
    niveau de l'ability. ≠ `ConfigConst` natif (`GetNumberConstant`, valeur fixe hors niveau). Cas
    standard = caster au niveau courant → `ctx.ability_level` ; niveau d'une unité tierce = NON offline.
    ⚠ RÉSERVE (validator) : le `ConfigConst` Python actuel appelle DÉJÀ `get_variable_for_level` — donc
    fait le boulot de ConfigVar, pas de ConfigConst (qui devrait être number-constant fixe). À trancher :
    le wrapper AbilityConfiguration distingue-t-il number-constant (fixe) vs variable-array (par niveau) ?"""
    def __init__(self, key: str, default: int = 0):
        self.key, self.default = key, default

    def evaluate(self, ctx):
        if ctx.config is None:
            return self.default
        return ctx.config.get_variable_for_level(self.key, ctx.ability_level, self.default)


class Cache(Node):
    """`DSLFactory.Cache(source) @180deb0d0` → `CacheSelector.Select @180ee35f0` : mémoïse le résultat du
    sous-arbre (clé = contexte d'éval complet, portée = instance du nœud, sans invalidation).
    Sémantiquement TRANSPARENT → pass-through fidèle en VALEUR (on recalcule ; divergence perf assumée,
    non observable sur les valeurs)."""
    def __init__(self, source: Node):
        self.source = source

    def evaluate(self, ctx):
        return self.source.evaluate(ctx)


class StatAmount(Node):
    """`DSLFactory.StatAmount(selector, statType, variant, level) @180dfbf60` →
    `StatAmountFormula.Calculate @180f22d40` : SOMME de `UnitExtensions.GetStat(unit, statType, variant,
    level)` sur toutes les unités du sélecteur (singleton → 1 unité ; multi → somme). `ctx.get_stat`
    fournit les stats réelles ; défaut dégradé = Health via hp (cf. `_default_get_stat`)."""
    def __init__(self, selector: Node, stat_type: int, variant: int = 0, level: Node | None = None):
        self.selector, self.stat_type, self.variant, self.level = selector, stat_type, variant, level

    def evaluate(self, ctx):
        gs = ctx.get_stat or _default_get_stat
        lvl = self.level.evaluate(ctx) if self.level is not None else None
        return sum(gs(u, self.stat_type, self.variant, lvl) for u in self.selector.evaluate(ctx))


class Entity(Node):
    """`DSLFactory.Entity(ref) @180def540` : résout la RÉFÉRENCE passée en argument (rôle
    caster/target/subject) en ENTITÉ. Wrapper fin — l'opérande (souvent un nœud rôle, ex. `Subject`)
    évalue déjà l'entité."""
    def __init__(self, ref: Node):
        self.ref = ref

    def evaluate(self, ctx):
        return self.ref.evaluate(ctx)


class EntityId(Node):
    """`DSLFactory.EntityId(ref) @180def470` : id de l'entité résolue (ou None)."""
    def __init__(self, ref: Node):
        self.ref = ref

    def evaluate(self, ctx):
        e = self.ref.evaluate(ctx)
        return e.get("id") if isinstance(e, dict) else None


class Nothing(Node):
    """`DSLFactory.Nothing @180df7870` : sélecteur VIDE (retourne `[]`). Classe DISTINCTE de `Null`."""
    def evaluate(self, ctx):
        return []


class Null(Node):
    """`DSLFactory.Null @180df74f0` : entité/valeur NULLE (retourne `None`). Même classe qu'`Entity` avec
    arg null ; distinct de `Nothing` (ensemble vide)."""
    def evaluate(self, ctx):
        return None


class EffectSource(Node):
    """`DSLFactory.EffectSource @180deeb90` : entité SOURCE de l'effet COURANT (`ctx.effect`). NON captable
    hors application d'effet → None si `ctx.effect` absent."""
    def evaluate(self, ctx):
        return _effect_field(ctx.effect, "source", None)


class EffectLevel(Node):
    """`DSLFactory.EffectLevel @180deead0` : niveau de l'effet COURANT (`ctx.effect`). 0 si absent."""
    def evaluate(self, ctx):
        return _effect_field(ctx.effect, "level", 0)


class EffectFromOwner(Node):
    """`DSLFactory.EffectFromOwner(effectType) @180deea50` → `EffectWithTypeSelector @180ee7f30` : effets
    du type possédés par l'owner. NON captable offline (effets par unité absents du state) → `[]` défaut."""
    def __init__(self, effect_type):
        self.effect_type = effect_type

    def evaluate(self, ctx):
        return []
