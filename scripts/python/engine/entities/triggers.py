"""Noeuds PREDICAT du DSL = famille `AbilityTrigger.ShouldTrigger` (kind T).

Mirror du namespace natif `IdunBattle.Entities.Triggers` (+ `.Conditions`) : les concrets vivent ici,
a cote de leurs freres `entities/{abilities,selectors,formulas,behaviours,effects}` ; la base
`AbilityTrigger` (= `IdunBattle.DSL`) reste dans `dsl/base.py`. Construits via la facade `DSLFactory`
(`dsl/nodes.py`)."""
from __future__ import annotations

import hexgeo

from ..dsl.base import AbilityTrigger, _pos, _units_of, _is_alive, _same_entity, _c_mod


class TriggerAnd(AbilityTrigger):
    """`AbilityTrigger.op_BitwiseAnd(a, b)` : ET LOGIQUE (court-circuit) de deux prédicats booléens
    `ShouldTrigger`. ≠ `selectors.And` (intersection de LISTES d'unités, domaine ciblage). Utilisé par
    `TauntWithNewChildrenWhoDidDamage @1811e27a0` : `(TotalAttacksMade>0 & turnsEq) & IsAlive(lastAttacked)`.
    `bool(a) and bool(b)` — `b` non évalué si `a` faux (court-circuit natif)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return bool(self.a.evaluate(ctx)) and bool(self.b.evaluate(ctx))


class Not(AbilityTrigger):
    """`AbilityTrigger.op_LogicalNot(a)` : NÉGATION LOGIQUE d'un prédicat (`not a.evaluate`). TheBetrayer
    (`@1811a4f70`) réutilise le MÊME nœud `IsAdjacent` sous `op_LogicalNot` (gate du move) ET en direct
    (gate de l'attaque) — deux évals, verdicts DIVERGENTS à travers le move (re-éval LIVE : le move mute
    la position, cf. docs/rl/dsl-live-context-substrate.md). Le nœud enveloppé est réutilisé, pas dupliqué."""
    def __init__(self, a: AbilityTrigger):
        self.a = a

    def should_trigger(self, ctx):
        return not self.a.evaluate(ctx)


class HasFlag(AbilityTrigger):
    """`DSLFactory.HasFlag(flag)` : `flag ∈ ctx.flags`. Le sens exact du flag (ex. HarvesterOfSouls @+0x160)
    reste à RE ; défaut = absent (branche `flag=false`), confirmé par l'agrément."""
    def __init__(self, flag):
        self.flag = flag

    def should_trigger(self, ctx):
        return self.flag in ctx.flags


class AreEqual(AbilityTrigger):
    """`DSLFactory.AreEqual(a,b) @180de9000` : `a == b` (ctor générique 2-arg, singleton DAT_183200238 ;
    sémantique DÉDUITE du nom — eval résiduelle non décompilée. À confirmer si branché sur des enums/
    objets non-int)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) == self.b.evaluate(ctx)


class AmountIsEqual(AbilityTrigger):
    """`DSLFactory.AmountIsEqual(a,b) @180de8820` → `ShouldTrigger @180ee0bd0` : `a == b`."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) == self.b.evaluate(ctx)


class AmountIsGreater(AbilityTrigger):
    """`DSLFactory.AmountIsGreater(a,b) @180de8a40` → `ShouldTrigger @180ee11f0` : `a > b` STRICT
    (classe DAT_1832482b0, DISTINCTE de AmountIsEqualOrGreater malgré le même nom de ctor mislabel)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) > self.b.evaluate(ctx)


class AmountIsEqualOrGreater(AbilityTrigger):
    """`DSLFactory.AmountIsEqualOrGreater(a,b) @180de8660` → `ShouldTrigger @180ee0e00` : `a >= b`
    (classe DAT_183248030, distincte de AmountIsGreater)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) >= self.b.evaluate(ctx)


class AmountIsGreaterThanZero(AbilityTrigger):
    """`DSLFactory.AmountIsGreaterThanZero(a) @180de88f0` = `AmountIsGreater(a, 0)` : `a > 0`."""
    def __init__(self, a: AbilityTrigger):
        self.a = a

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) > 0


class AmountIsZero(AbilityTrigger):
    """`DSLFactory.AmountIsZero(a) @180de8b10` = `NOT(AmountIsEqualOrGreater(a, 1))` : `a <= 0`
    (== 0 pour un cardinal). ⚠ `a <= 0`, PAS `a == 0` (mirror exact du natif `NOT(a >= 1)`)."""
    def __init__(self, a: AbilityTrigger):
        self.a = a

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) <= 0


class AmountIsOdd(AbilityTrigger):
    """`DSLFactory.AmountIsOdd(a) @180de8ab0` = `NOT(AmountIsEven)` → `(a & 1) == 1` (bit0 de l'int)."""
    def __init__(self, a: AbilityTrigger):
        self.a = a

    def should_trigger(self, ctx):
        return (self.a.evaluate(ctx) & 1) == 1


class Modulo(AbilityTrigger):
    """`DSLFactory.Modulo(a,b,c) @180df69a0` → `ModuloAbilityTrigger.ShouldTrigger @180eeda30` :
    `(a mod b) == c` — ⚠ c'est un PRÉDICAT bool, PAS une valeur `a mod b`. Modulo entier signé C.
    (Pour une valeur modulo pure il faudrait un autre nœud, absent du batch.)"""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger, c: AbilityTrigger):
        self.a, self.b, self.c = a, b, c

    def should_trigger(self, ctx):
        return _c_mod(self.a.evaluate(ctx), self.b.evaluate(ctx)) == self.c.evaluate(ctx)


class HasTrait(AbilityTrigger):
    """`DSLFactory.HasTrait(unit, traitId) @180df14c0` : `UnitExtensions.HasFlag(unit, traitId)` (même
    primitive que HasFlag/UnitsWithTrait). Sujet = l'opérande (passer `Subject()` sous un Filter).
    `ctx.has_trait` défaut None → trait absent → False. [ctor mislabelé, sémantique DÉDUITE ; single-vs-
    any sur une liste = à confirmer à l'agreement]."""
    def __init__(self, unit: AbilityTrigger, trait):
        self.unit, self.trait = unit, trait

    def should_trigger(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        return any(ht(u, self.trait) for u in _units_of(self.unit, ctx))


class AreFriends(AbilityTrigger):
    """`DSLFactory.AreFriends(a, b) @...` : les deux entités sont-elles ALLIÉES (MÊME équipe) ? Mirror du
    test `_friendly_imperial` impératif du `matches` ActOfFaith (`oc.team == oown.team`, live-validé) —
    utilisé par le behaviour accumulate @181219a70 (`AreFriends(killer@0x158, owner@0x148)`). Compare
    l'équipe des unités résolues par les deux sélecteurs (any paire même-équipe) ; None d'un côté → False.
    [⚠ flags natifs résiduels (args `0`/bool/`0` de la factory : includeSelf/aliveOnly ?) non modélisés —
    à confirmer à l'agreement ; le NET même-équipe est prouvé par le matches déjà live-validé.]"""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        ta = [u.get("team") for u in _units_of(self.a, ctx) if isinstance(u, dict)]
        tb = [u.get("team") for u in _units_of(self.b, ctx) if isinstance(u, dict)]
        return any(x is not None and x == y for x in ta for y in tb)


class HasGrandAlliance(AbilityTrigger):
    """Mirror de `HasTrait(unit, grandAllianceTrait)` où le pseudo-trait de GRANDE-ALLIANCE (`GrandAlliance.
    GetTrait @1815647a0` — Imperial=0x1a=26, Chaos, Xenos…) n'est PAS un trait gameconfig mais DÉRIVÉ de la
    FACTION. Le port le résout via `ctx.faction_of(unit) ∈ factions` (MÊME dérivation que le `matches`
    ActOfFaith impératif, live-validé : IMPERIAL_FACTIONS = les 10 factions impériales). `factions` = frozenset
    de FactionId de la grande-alliance. Utilisé par le behaviour ActOfFaith accumulate @181219a70
    (`HasTrait(killer@0x158, 0x1a=26=Imperial)`). None d'un côté → False."""
    def __init__(self, unit: AbilityTrigger, factions):
        self.unit, self.factions = unit, factions

    def should_trigger(self, ctx):
        fo = ctx.faction_of or (lambda u: None)
        return any(fo(u) in self.factions for u in _units_of(self.unit, ctx))


class HasEffect(AbilityTrigger):
    """`DSLFactory.HasEffect(unit, effectType[, minLevel]) @180df0fb0` → `HasEffectTrigger @180f9d830` :
    l'unité a un effet du type (>= minLevel, source-flag mode 6 = owned|incoming). `ctx.has_effect`
    (nouveau) défaut None → False. NON captable offline standard (partiel live via decisionView.effects)."""
    def __init__(self, unit: AbilityTrigger, effect_type, min_level: int = 0):
        self.unit, self.effect_type, self.min_level = unit, effect_type, min_level

    def should_trigger(self, ctx):
        he = ctx.has_effect or (lambda u, et, sf=6, ml=0: False)
        return any(he(u, self.effect_type, 6, self.min_level) for u in _units_of(self.unit, ctx))


class HasAnyEffect(AbilityTrigger):
    """`DSLFactory.HasAnyEffect(unit, effectTypes) @180df0b70` → `@180f9d0c0` : au moins un effet parmi
    la liste (mode 6). `ctx.has_effect` défaut None → False."""
    def __init__(self, unit: AbilityTrigger, effect_types):
        self.unit, self.effect_types = unit, effect_types

    def should_trigger(self, ctx):
        he = ctx.has_effect or (lambda u, et, sf=6, ml=0: False)
        us = _units_of(self.unit, ctx)
        return any(he(u, et, 6, 0) for u in us for et in self.effect_types)


class IsAlive(AbilityTrigger):
    """`DSLFactory.IsAlive(unit) @180df2fa0` → `@180eec930` : `UnitExtensions.IsAlive` = vivant & hp>0.
    (`Damageable`/`Alive` filtrent un ENSEMBLE sur le même critère.)"""
    def __init__(self, unit: AbilityTrigger):
        self.unit = unit

    def should_trigger(self, ctx):
        return any(_is_alive(u) for u in _units_of(self.unit, ctx))


class IsDead(AbilityTrigger):
    """`DSLFactory.IsDead(unit) @180df3370` = `NOT(IsAlive)`."""
    def __init__(self, unit: AbilityTrigger):
        self.unit = unit

    def should_trigger(self, ctx):
        return not any(_is_alive(u) for u in _units_of(self.unit, ctx))


class IsMeleeAttack(AbilityTrigger):
    """`DSLFactory.IsMeleeAttack @180df43f0` → `@180fa1e00` : l'ABILITY COURANTE est-elle une attaque de
    mêlée ? (type de timeline de l'ability, donnée statique gameconfig). `ctx.attack_kind == 'melee'`
    (nouveau slot câblé par la couche ability ; défaut None → False)."""
    def should_trigger(self, ctx):
        return ctx.attack_kind == "melee"


class IsRangedAttack(AbilityTrigger):
    """`DSLFactory.IsRangedAttack @180df4d90` : l'ability courante est-elle une attaque à distance ?
    `ctx.attack_kind == 'ranged'` (même classe qu'IsMeleeAttack, timeline-type distinct)."""
    def should_trigger(self, ctx):
        return ctx.attack_kind == "ranged"


class IsNormalAttack(AbilityTrigger):
    """`DSLFactory.IsNormalAttack @180df47c0` → `@180df4690` : l'ability courante == ActiveAbilityType
    normal (0x3f5 = 1013, `op_Implicit` lu). `ctx.attack_ability_type == 1013` (nouveau slot ; défaut
    None → False). ⚠ le "OR ..." résiduel + la valeur 1013-vs-id-concret = à confirmer à l'agreement."""
    def should_trigger(self, ctx):
        return ctx.attack_ability_type == 1013


class IsAdjacent(AbilityTrigger):
    """`DSLFactory.IsAdjacent(a, b) @180df2f00` → `@180f9f7b0` : une unité de `a` est-elle hex-adjacente
    (dist == 1) à une de `b` ? DEUX sélecteurs explicites (PAS `subject`). [seuil dist==1 DÉDUIT du
    helper d'adjacence 0x5f]."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        pa = [_pos(u) for u in _units_of(self.a, ctx)]
        pb = [_pos(u) for u in _units_of(self.b, ctx)]
        return any(x is not None and y is not None and hexgeo.distance(x, y) == 1 for x in pa for y in pb)


class IsInRange(AbilityTrigger):
    """`DSLFactory.IsInRange(a, b, range) @180df3d80` → `@180fa1720` : `dist(a, b) <= range`. ⚠ ordre
    exact des args factory (slots +0x28/+0x18/+0x20) = structure prouvée, mapping à confirmer au câblage."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger, rng: AbilityTrigger):
        self.a, self.b, self.rng = a, b, rng

    def should_trigger(self, ctx):
        r = self.rng.evaluate(ctx)
        pa = [_pos(u) for u in _units_of(self.a, ctx)]
        pb = [_pos(u) for u in _units_of(self.b, ctx)]
        return any(x is not None and y is not None and hexgeo.distance(x, y) <= r for x in pa for y in pb)


class OwnerIsTarget(AbilityTrigger):
    """`DSLFactory.get_OwnerIsTarget @180e026f0` = `AreEqual(Owner, Target)` : l'entité OWNER est-elle la
    même que la cible ? (`ctx.owner` défaut → `ctx.caster`, hypothèse Owner==Caster documentée)."""
    def should_trigger(self, ctx):
        return _same_entity(ctx.owner or ctx.caster, ctx.target)


class OwnerIsCaster(AbilityTrigger):
    """`DSLFactory.get_OwnerIsCaster @180e02610` = `AreEqual(Owner, Caster)` : OWNER == qui lance ?"""
    def should_trigger(self, ctx):
        return _same_entity(ctx.owner or ctx.caster, ctx.caster)


class OwnerIsActor(AbilityTrigger):
    """`DSLFactory.get_OwnerIsActor @180e02530` = `AreEqual(Owner, Actor)` : OWNER == acteur du contexte ?
    (`ctx.actor` défaut → `ctx.caster`)."""
    def should_trigger(self, ctx):
        return _same_entity(ctx.owner or ctx.caster, ctx.actor or ctx.caster)
