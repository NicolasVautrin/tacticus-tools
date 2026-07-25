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
    `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$TauntWithNewChildrenWhoDidDamage` : `(TotalAttacksMade>0 & turnsEq) & IsAlive(lastAttacked)`.
    `bool(a) and bool(b)` — `b` non évalué si `a` faux (court-circuit natif)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return bool(self.a.evaluate(ctx)) and bool(self.b.evaluate(ctx))


class TriggerOr(AbilityTrigger):
    """`IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr(a, b)` : OU LOGIQUE de deux prédicats booléens. Classe
    NATIVE DISTINCTE de l'ET (`IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd` -> DAT_18325bd38 ; ici DAT_1832782e8), MEME
    layout (`left@+0x10`, `right@+0x18`). 201 call-sites natifs — dont
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$FulfillsSummonCriteria` (`HasMinimumAdjacentOrks(nrOfUnits_3)
    | HasMinimumAdjacentFriendlyUnits(nrOfUnits_4)`), les disjonctions `CreateTrigger` de RadSaturation
    /TerrifyingCrescendo/ActOfFaith (jusqu'ici recablees a la main dans leurs triggers impératifs).
    `bool(a) or bool(b)` — court-circuit (le `ShouldTrigger` natif de la classe n'est pas relu ; sans
    effet observable, les deux operandes etant des predicats PURS)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return bool(self.a.evaluate(ctx)) or bool(self.b.evaluate(ctx))


class Not(AbilityTrigger):
    """`AbilityTrigger.op_LogicalNot(a)` : NÉGATION LOGIQUE d'un prédicat (`not a.evaluate`). TheBetrayer
    (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour`) réutilise le MÊME nœud `IsAdjacent` sous `op_LogicalNot` (gate du move) ET en direct
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
    """`IdunBattleLogic.Entities.DSLFactory$$AreEqual(a,b)` : `a == b` (ctor générique 2-arg, singleton DAT_183200238 ;
    sémantique DÉDUITE du nom — eval résiduelle non décompilée. À confirmer si branché sur des enums/
    objets non-int)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) == self.b.evaluate(ctx)


class AmountIsEqual(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$AmountIsEqual(a,b)` → `IdunBattle.Entities.Conditions.AmountIsEqualAbilityTrigger$$ShouldTrigger` : `a == b`."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) == self.b.evaluate(ctx)


class AmountIsGreater(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$AmountIsGreater(a,b)` → `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` : `a > b` STRICT
    (classe DAT_1832482b0, DISTINCTE de AmountIsEqualOrGreater malgré le même nom de ctor mislabel)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) > self.b.evaluate(ctx)


class AmountIsEqualOrGreater(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$AmountIsEqualOrGreater(a,b)` → `IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` : `a >= b`
    (classe DAT_183248030, distincte de AmountIsGreater)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) >= self.b.evaluate(ctx)


class CacheTrigger(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$Cache(trigger)` (overload PRÉDICAT du `Cache` — le sélecteur est
    `IdunBattleLogic.Entities.DSLFactory$$Cache`, même famille, singleton de classe DISTINCT `DAT_183282208` ; le ctor
    affiché `thor_Menu_WaitForCondition..ctor` est un fold gshared MISLABELÉ, structure lue = 1 champ =
    le nœud caché) : MÉMOÏSE le verdict booléen du sous-arbre. La 1ʳᵉ évaluation calcule et stocke ;
    les suivantes rendent le CACHE — la mémoïsation est OBSERVABLE dès que l'état mute entre deux
    consommateurs.

    Consommateur porté : `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$ExecuteBehaviour` —
    `cond = Cache(FulfillsSummonCriteria)`, puis `Execute( (SetCache(cond) + attack) + If(cond, spawn) )` :
    le `SetCache` force l'éval AVANT l'attaque, donc le critère de summon est figé sur l'état
    **PRÉ-attaque** (une cible tuée par les 3 coups ne peut pas invalider a posteriori le spawn).
    Portée = l'instance du nœud ; l'arbre étant rebâti par cast, le cache est **par-cast**."""
    def __init__(self, inner: AbilityTrigger):
        self.inner = inner
        self._has = False
        self._cached = False

    def should_trigger(self, ctx):
        if not self._has:                            # miss -> calcule + stocke (slot unique)
            self._cached = bool(self.inner.evaluate(ctx))
            self._has = True
        return self._cached                          # hit -> verdict MEMOISE


class AmountIsGreaterThanZero(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$AmountIsGreaterThanZero(a)` = `AmountIsGreater(a, 0)` : `a > 0`."""
    def __init__(self, a: AbilityTrigger):
        self.a = a

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) > 0


class AmountIsZero(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$AmountIsZero(a)` = `NOT(AmountIsEqualOrGreater(a, 1))` : `a <= 0`
    (== 0 pour un cardinal). ⚠ `a <= 0`, PAS `a == 0` (mirror exact du natif `NOT(a >= 1)`)."""
    def __init__(self, a: AbilityTrigger):
        self.a = a

    def should_trigger(self, ctx):
        return self.a.evaluate(ctx) <= 0


class AmountIsOdd(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$AmountIsOdd(a)` = `NOT(AmountIsEven)` → `(a & 1) == 1` (bit0 de l'int)."""
    def __init__(self, a: AbilityTrigger):
        self.a = a

    def should_trigger(self, ctx):
        return (self.a.evaluate(ctx) & 1) == 1


class Modulo(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$Modulo(a,b,c)` → `IdunBattle.Entities.Conditions.ModuloAbilityTrigger$$ShouldTrigger` :
    `(a mod b) == c` — ⚠ c'est un PRÉDICAT bool, PAS une valeur `a mod b`. Modulo entier signé C.
    (Pour une valeur modulo pure il faudrait un autre nœud, absent du batch.)"""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger, c: AbilityTrigger):
        self.a, self.b, self.c = a, b, c

    def should_trigger(self, ctx):
        return _c_mod(self.a.evaluate(ctx), self.b.evaluate(ctx)) == self.c.evaluate(ctx)


class HasTrait(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$HasTrait(unit, traitId)` : `UnitExtensions.HasFlag(unit, traitId)` (même
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
    utilisé par le behaviour accumulate IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour (`AreFriends(killer@0x158, owner@0x148)`). Compare
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
    idun.Idun.Source.Shared.GrandAlliance$$GetTrait` — Imperial=0x1a=26, Chaos, Xenos…) n'est PAS un trait gameconfig mais DÉRIVÉ de la
    FACTION. Le port le résout via `ctx.faction_of(unit) ∈ factions` (MÊME dérivation que le `matches`
    ActOfFaith impératif, live-validé : IMPERIAL_FACTIONS = les 10 factions impériales). `factions` = frozenset
    de FactionId de la grande-alliance. Utilisé par le behaviour ActOfFaith accumulate IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour
    (`HasTrait(killer@0x158, 0x1a=26=Imperial)`). None d'un côté → False."""
    def __init__(self, unit: AbilityTrigger, factions):
        self.unit, self.factions = unit, factions

    def should_trigger(self, ctx):
        fo = ctx.faction_of or (lambda u: None)
        return any(fo(u) in self.factions for u in _units_of(self.unit, ctx))


class HasEffect(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$HasEffect(unit, effectType[, minLevel])` → `HasEffectTrigger IdunBattle.Entities.Triggers.HasEffectTrigger$$ShouldTrigger` :
    l'unité a un effet du type (>= minLevel, source-flag mode 6 = owned|incoming). `ctx.has_effect`
    (nouveau) défaut None → False. NON captable offline standard (partiel live via decisionView.effects)."""
    def __init__(self, unit: AbilityTrigger, effect_type, min_level: int = 0):
        self.unit, self.effect_type, self.min_level = unit, effect_type, min_level

    def should_trigger(self, ctx):
        he = ctx.has_effect or (lambda u, et, sf=6, ml=0: False)
        return any(he(u, self.effect_type, 6, self.min_level) for u in _units_of(self.unit, ctx))


class HasAnyEffect(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$HasAnyEffect(unit, effectTypes)` → `IdunBattle.Entities.Triggers.HasAnyEffectTrigger$$ShouldTrigger` : au moins un effet parmi
    la liste (mode 6). `ctx.has_effect` défaut None → False."""
    def __init__(self, unit: AbilityTrigger, effect_types):
        self.unit, self.effect_types = unit, effect_types

    def should_trigger(self, ctx):
        he = ctx.has_effect or (lambda u, et, sf=6, ml=0: False)
        us = _units_of(self.unit, ctx)
        return any(he(u, et, 6, 0) for u in us for et in self.effect_types)


class IsAlive(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsAlive(unit)` → `IdunBattle.Entities.Conditions.IsAliveAbilityTrigger$$ShouldTrigger` : `UnitExtensions.IsAlive` = vivant & hp>0.
    (`Damageable`/`Alive` filtrent un ENSEMBLE sur le même critère.)"""
    def __init__(self, unit: AbilityTrigger):
        self.unit = unit

    def should_trigger(self, ctx):
        return any(_is_alive(u) for u in _units_of(self.unit, ctx))


class IsDead(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsDead(unit)` = `NOT(IsAlive)`."""
    def __init__(self, unit: AbilityTrigger):
        self.unit = unit

    def should_trigger(self, ctx):
        return not any(_is_alive(u) for u in _units_of(self.unit, ctx))


class IsPositionMachineForCurrentPlayer(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsPositionMachineForCurrentPlayer` -> `IsPositionMachineForPlayerTrigger
    .IdunBattle.Entities.Triggers.IsPositionMachineForPlayerTrigger$$ShouldTrigger` :

        turn   = state.GetMatchTurn() ; player = state.GetPlayer(turn.CurrentPlayerId)
        if (player == null) return false
        return battleQuery.<MachineOfWarPosition>(player) == this.Position (@+0x20)

    -> « le SLOT de deploiement (`MachineOfWarPosition` : 1=Top, 2=Bottom) de la MoW du joueur COURANT
    vaut-il `position` ? ». Note : c'est le joueur COURANT du tour, PAS le caster (le natif lit
    `TurnComponent.CurrentPlayerId`). Consomme par les abilities MoW dont la GEOMETRIE depend du cote du
    plateau : `IdunBattleLogic.Entities.Abilities.Active.Loki.MacroPlasmaIncineratorAbility$$ExecuteBehaviour`
    (`If(this, Direct(1), Direct(4))` = coin du triangle) et `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour` / `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$GetShape` (choix du triplet de directions).

    `ctx.current_player_machine_position` (pose par `entities_from_state` : le slot de la
    `MachineComponent` dont l'`OwnerComponent.player` == `state.current_player_id`) ; None (le joueur
    courant n'a pas de MoW) -> False, mirror du `if (player == null) return false`."""
    def __init__(self, position: int):
        self.position = int(position)

    def should_trigger(self, ctx):
        pos = ctx.current_player_machine_position
        return pos is not None and int(pos) == self.position


class IsMeleeAttack(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsMeleeAttack` → `IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` : l'ABILITY COURANTE est-elle une attaque de
    mêlée ? (type de timeline de l'ability, donnée statique gameconfig). `ctx.attack_kind == 'melee'`
    (nouveau slot câblé par la couche ability ; défaut None → False)."""
    def should_trigger(self, ctx):
        return ctx.attack_kind == "melee"


class IsRangedAttack(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsRangedAttack` : l'ability courante est-elle une attaque à distance ?
    `ctx.attack_kind == 'ranged'` (même classe qu'IsMeleeAttack, timeline-type distinct)."""
    def should_trigger(self, ctx):
        return ctx.attack_kind == "ranged"


class IsNormalAttack(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack` → `IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack` : l'ability courante == ActiveAbilityType
    normal (0x3f5 = 1013, `op_Implicit` lu). `ctx.attack_ability_type == 1013` (nouveau slot ; défaut
    None → False). ⚠ le "OR ..." résiduel + la valeur 1013-vs-id-concret = à confirmer à l'agreement."""
    def should_trigger(self, ctx):
        return ctx.attack_ability_type == 1013


class IsAdjacent(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsAdjacent(a, b)` → `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger` : une unité de `a` est-elle hex-adjacente
    (dist == 1) à une de `b` ? DEUX sélecteurs explicites (PAS `subject`). [seuil dist==1 DÉDUIT du
    helper d'adjacence 0x5f]."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        pa = [_pos(u) for u in _units_of(self.a, ctx)]
        pb = [_pos(u) for u in _units_of(self.b, ctx)]
        return any(x is not None and y is not None and hexgeo.distance(x, y) == 1 for x in pa for y in pb)


class IsInRange(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsInRange(a, b, range)` → `IdunBattle.Entities.Triggers.IsInRangeAbilityTrigger$$ShouldTrigger` : `dist(a, b) <= range`. ⚠ ordre
    exact des args factory (slots +0x28/+0x18/+0x20) = structure prouvée, mapping à confirmer au câblage."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger, rng: AbilityTrigger):
        self.a, self.b, self.rng = a, b, rng

    def should_trigger(self, ctx):
        r = self.rng.evaluate(ctx)
        pa = [_pos(u) for u in _units_of(self.a, ctx)]
        pb = [_pos(u) for u in _units_of(self.b, ctx)]
        return any(x is not None and y is not None and hexgeo.distance(x, y) <= r for x in pa for y in pb)


class IsSurrounding(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsSurrounding(a, b, radius)` : une unite de `b` est-elle a distance hex
    <= `radius` d'une unite de `a` (b "entoure" a) ? Distance SYMETRIQUE -> semantique == `IsInRange`
    (l'ordre a/b est indifferent). ctor IL2CPP mislabele (`AttackHitsWithModifiersFormula.ctor` = corps
    gshared partage) ; sens DEDUIT de l'usage + i2 : HeroicFusillade IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour gate son move par
    `Not(IsSurrounding(caster@0x148, target@0x178, radius=1))` = move SEULEMENT si la cible n'entoure pas
    DEJA le caster (i2 « ... or is already on a hex surrounding Judh. She then moves to the free hex »).
    `radius` = noeud VALEUR (`.evaluate`). None d'un cote -> False."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger, radius: AbilityTrigger):
        self.a, self.b, self.radius = a, b, radius

    def should_trigger(self, ctx):
        r = self.radius.evaluate(ctx)
        pa = [_pos(u) for u in _units_of(self.a, ctx)]
        pb = [_pos(u) for u in _units_of(self.b, ctx)]
        return any(x is not None and y is not None and hexgeo.distance(x, y) <= r for x in pa for y in pb)


class OwnerIsTarget(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$get_OwnerIsTarget` = `AreEqual(Owner, Target)` : l'entité OWNER est-elle la
    même que la cible ? (`ctx.owner` défaut → `ctx.caster`, hypothèse Owner==Caster documentée)."""
    def should_trigger(self, ctx):
        return _same_entity(ctx.owner or ctx.caster, ctx.target)


class OwnerIsCaster(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$get_OwnerIsCaster` = `AreEqual(Owner, Caster)` : OWNER == qui lance ?"""
    def should_trigger(self, ctx):
        return _same_entity(ctx.owner or ctx.caster, ctx.caster)


class OwnerIsActor(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$get_OwnerIsActor` = `AreEqual(Owner, Actor)` : OWNER == acteur du contexte ?
    (`ctx.actor` défaut → `ctx.caster`)."""
    def should_trigger(self, ctx):
        return _same_entity(ctx.owner or ctx.caster, ctx.actor or ctx.caster)
