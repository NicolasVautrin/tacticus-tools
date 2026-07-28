"""Noeuds PREDICAT du DSL = famille `AbilityTrigger.ShouldTrigger` (kind T).

Mirror du namespace natif `IdunBattle.Entities.Triggers` (+ `.Conditions`) : les concrets vivent ici,
a cote de leurs freres `entities/{abilities,selectors,formulas,behaviours,effects}` ; la base
`AbilityTrigger` (= `IdunBattle.DSL`) reste dans `dsl/base.py`. Construits via la facade `DSLFactory`
(`dsl/nodes.py`)."""
from __future__ import annotations

import hexgeo

from ..dsl.base import (AbilityTrigger, AAmountFormula, _pos, _units_of, _is_alive, _same_entity,
                        _c_mod)


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


class MaybeTrigger(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$Maybe(chance)` (surcharge a UN argument) ->
    `IdunBattle.Entities.Triggers.MaybeTrigger$$.ctor` / `$$ShouldTrigger` : PREDICAT NON DETERMINISTE
    (kind T) qui tire `NextBool(chance)`.

    A NE PAS CONFONDRE avec le noeud EFFET homonyme `entities.behaviours.Maybe`
    (`IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute`, surcharges a 3/4 args de la meme factory) :
    celui-la ENVELOPPE un behaviour, celui-ci est un PREDICAT compose par `op_BitwiseAnd`/`If`.

    Mirror 1:1 de `MaybeTrigger$$ShouldTrigger` :
        chance = <formule V>.Calculate(entities)                 # ici `ConfigConst(...)` @+0x20
        if (!ANonDeterministicAbilityTrigger.CanUseRandom(this)) return 99 < chance;
        return DisallowablePseudoRNG.NextBool(this.rng@+0x18, chance);
    Le RNG est un CHAMP de l'instance (`+0x18`, pose par la factory depuis `DSLFactory+0x18`), PAS une
    entree du contexte -> le port le prend AU CONSTRUCTEUR, comme le natif.

    ## `CanUseRandom` (RE `IdunBattle.DSL.ANonDeterministicAbilityTrigger$$CanUseRandom`, O4a)
        return state@+0x10.IsRandomAllowed && rng@+0x18.IsAllowed@+0x20;
    Les DEUX facteurs sont lus :
      - `IdunBattle.Core.IMatchState$$get_IsRandomAllowed` = `!<slot 0xb>` (le state en SIMULATION rend
        false) ;
      - `DisallowablePseudoRNG+0x20` = le flag `IsAllowed`, pose a 1 par
        `IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$.ctor`, mis a 0 par
        `IdunBattleLogic.Entities.DSLFactory$$SetDisallowRandom` et remis a 1 par
        `IdunBattleLogic.Entities.DSLFactory$$SetAllowRandom` -- dont l'UNIQUE call-site (xrefs) est
        `IdunBattle.AI.Playbook.BasePlaybook$$Evaluate`, c.-a-d. l'IA qui EVALUE ses options.
    Autrement dit `CanUseRandom == false` == **on est du cote DECISION/PREDICTION**, et le natif y
    substitue au tirage le predicat DETERMINISTE `99 < chance` (donc vrai SSI `chance >= 100`) -- la
    meme regle que celle deja ground-truthee cote formule de coups (`traits/combat.py` : « Maybe(chance)
    en PREDICTION : compte SSI chance == 100 »). Cote port, l'absence de PRNG (`rng is None`) EST cette
    situation : aucun flux de tirages n'est cale, on est hors execution de bataille -> on rend `99 < ch`
    (mirror), et non plus `False` (l'ancienne degradation, qui divergeait des `chance >= 100`).

    `chance` = noeud VALEUR (`AAmountFormula`) ou int litteral. UN SEUL `next_bool` par evaluation,
    et AUCUN tirage sur la branche `!CanUseRandom`."""
    def __init__(self, rng, chance):
        self.rng, self.chance = rng, chance

    def should_trigger(self, ctx):
        ch = self.chance.evaluate(ctx) if isinstance(self.chance, AAmountFormula) else int(self.chance)
        if self.rng is None:                         # !CanUseRandom -> `return 99 < chance` (0 tirage)
            return 99 < int(ch)
        # `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextBool` (1 tirage genrand, cf. prng.py).
        return bool(self.rng.next_bool(int(ch)))


class IsFirstHitInSeries(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsFirstHitInSeries()` ->
    `IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger` (MIRROR 1:1) :

        var v = entities.IsFirstHit;          // Nullable<bool>
        return v.HasValue ? v.Value : false;

    ou `IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHit` lit le `DamageAppliedResult` du
    coup courant (champ +0x110) et rend `IdunBattle.Core.Services.DamageAppliedResult$$get_IsFirstHit`
    = `hitIndex == 0`. Autrement dit : « le coup courant est le PREMIER de la serie de coups ».

    Cote port, `ctx.is_first_hit` est pose par le vecteur qui evalue l'arbre (defaut None -> False,
    mirror du `!HasValue`). Frere de `IsFirstHitGroupInAttack`
    (`IdunBattleLogic.Entities.DSLFactory$$IsFirstHitGroupInAttack`, champ +0x118), NON porte."""
    def should_trigger(self, ctx):
        v = ctx.is_first_hit
        return bool(v) if v is not None else False   # Nullable<bool> : `HasValue ? Value : false`


class HasFlag(AbilityTrigger):
    """`DSLFactory.HasFlag(flag)` : `flag ∈ ctx.flags`. Le sens exact du flag (ex. HarvesterOfSouls @+0x160)
    reste à RE ; défaut = absent (branche `flag=false`), confirmé par l'agrément."""
    def __init__(self, flag):
        self.flag = flag

    def should_trigger(self, ctx):
        return self.flag in ctx.flags


class HasUnitFlag(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$HasFlag(unit, flag)` ->
    `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$.ctor(unit, flag, want=1)` : l'UNITE selectionnee
    porte-t-elle le drapeau `IdunBattle.Entities.Enum.UnitFlag` ? C'est le jumeau UNIT-DOMAIN du noeud
    `HasFlag` ci-dessus (qui, lui, teste un flag SCALAIRE du contexte de decision, `ctx.flags` -- ex. le
    `HasFlag(@+0x160)` d'`HarvesterOfSouls`, sans operande-unite).

    Port : `ctx.has_unit_flag(unit, flag)` (le MEME accesseur que `AllDeadOrResurrectedUnits`, branche par
    `entities_from_state` sur le `UnitFlagsComponent` de l'ECS runner). Selecteur normalise par `_units_of`
    (`Any` sur les unites resolues, comme `IsAlive`/`IsDead`) ; accesseur absent -> False (degradation
    fidele : flag absent).

    Consommateurs portes : `DoomSirenAbility` (`HasFlag(It@0x180, 8 = Overkilled)`) et
    `FearOfTheUnseenAbility` (`NOT HasFlag(Self@0x148, 0 = Moved)`)."""
    def __init__(self, unit: AbilityTrigger, flag):
        self.unit, self.flag = unit, int(flag)

    def should_trigger(self, ctx):
        fn = ctx.has_unit_flag
        if fn is None:
            return False
        return any(bool(fn(u, self.flag)) for u in _units_of(self.unit, ctx))


class AreEqual(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$AreEqual(a,b)` : `a == b` (ctor générique 2-arg, singleton DAT_183200238 ;
    sémantique DÉDUITE du nom — eval résiduelle non décompilée. À confirmer si branché sur des enums/
    objets non-int).

    Domaine ENTITÉ (#117) : le natif compare des RÉFÉRENCES d'entité, et un opérande peut être un
    sélecteur qui rend une LISTE (`AreEqual(<cible courante>, Cache(Units(target@0x178)))` de
    `DarkTalonStrikeAbility$$DamageUnit` : `Subject()` rend un dict, `Cache(Units(...))` une liste d'un
    élément). On normalise les deux côtés par `_units_of` et on compare les ids DÈS QU'UN côté résout en
    entité(s) ; sinon égalité brute (domaine scalaire/enum inchangé)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        va, vb = self.a.evaluate(ctx), self.b.evaluate(ctx)

        def _ids(v):
            if isinstance(v, dict):
                items = [v]
            elif isinstance(v, (list, tuple)) and not (
                    len(v) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in v)):
                items = list(v)
            else:
                return None
            if not all(isinstance(x, dict) and x.get("id") is not None for x in items):
                return None
            return [x["id"] for x in items]
        ia, ib = _ids(va), _ids(vb)
        if ia is not None or ib is not None:
            return ia is not None and ib is not None and ia == ib
        return va == vb


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
    """`IdunBattleLogic.Entities.DSLFactory$$HasEffect(unit, effectType, activeOnly, sourceFlags)` →
    `IdunBattle.Entities.Triggers.HasEffectTrigger$$ShouldTrigger` → `IdunBattle.Entities.
    EntityExtensions$$HasOneOfEffects(entity, query, [effectType], activeOnly, sourceFlags)`.

    ⚠ RECTIFICATION (#100) : le 4e argument natif n'est PAS un `minLevel` — c'est un **flag ACTIVE-ONLY**.
    Preuve par le decompile de `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` (chemin de
    `HasOneOfEffects`) : `if (param_4 != 0) { if (EffectComponent+0x5c == '\\0') continue; }` avant le
    test `EffectComponent+0x58 == effectType` — et `+0x5c` est le flag **IsActive** (mis a 0 par
    `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect`, qui court-circuite s'il vaut deja
    0). Le `sourceFlags` (5e arg, = 6 = 2|4) selectionne les DEUX branches de `HasOneOfEffects`
    (owned | incoming). Tous les call-sites lus du cluster AnvilShield passent `activeOnly = 1`.

    `min_level` (conserve, defaut 0) reste le filtre de NIVEAU du port pour les call-sites qui en ont
    besoin ; `active_only` (defaut True = ce que passent les call-sites natifs lus) fait respecter
    l'`ActiveCondition` de l'effet (`BaseEffect.is_active`). `ctx.has_effect` defaut None → False.
    NON captable offline standard (partiel live via decisionView.effects).

    DOMAINE MIXTE (#90 — mirror du natif, qui teste une `IEntity` INDIFFERENCIEE via
    `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects`) : une entite-UNITE (dict) passe par
    `ctx.has_effect`, une entite-TUILE (id int, ex. le sujet d'un `Filter` tile-domain --
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$ExecuteBehaviour` filtre sa zone
    par `HasEffect(Tiles(Subject@0x180), 5=Fire)`) par `ctx.tile_has_effect`. Accesseur absent -> False.

    LIMITE ASSUMEE (fusion #100 x #90) : `active_only` n'est threade QUE sur la branche UNITE. Le natif
    l'applique a n'importe quelle `IEntity`, mais l'accesseur tuile du port (`ctx.tile_has_effect`,
    #217) n'expose aucune notion d'effet actif/inactif -- le lui passer serait inventer un parametre
    qu'il ne sait pas honorer. Sans consequence tant qu'aucun effet de TUILE ne porte d'ActiveCondition
    (aucun a ce jour) ; a rouvrir avec l'infra effets-de-tuile mutables (tache #85)."""
    def __init__(self, unit: AbilityTrigger, effect_type, min_level: int = 0,
                 active_only: bool = True):
        self.unit, self.effect_type, self.min_level = unit, effect_type, min_level
        self.active_only = bool(active_only)

    def should_trigger(self, ctx):
        he = ctx.has_effect or (lambda u, et, sf=6, ml=0, ao=True: False)
        the = getattr(ctx, "tile_has_effect", None)
        # Meme normalisation que `_units_of` (dict -> [dict], None -> [], liste telle quelle),
        # ETENDUE au domaine TUILE : l'iteration de #90 la subsume, on y injecte `active_only`.
        raw = self.unit.evaluate(ctx)
        items = [] if raw is None else ([raw] if isinstance(raw, (dict, int, tuple)) else list(raw))
        for it in items:
            if isinstance(it, dict):
                if he(it, self.effect_type, 6, self.min_level, self.active_only):
                    return True
            elif isinstance(it, int) and not isinstance(it, bool):
                if the is not None and the(int(it), int(self.effect_type)):
                    return True
        return False


class HasAnyEffect(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$HasAnyEffect(unit, effectTypes)` → `IdunBattle.Entities.Triggers.HasAnyEffectTrigger$$ShouldTrigger` : au moins un effet parmi
    la liste (mode 6). `ctx.has_effect` défaut None → False."""
    def __init__(self, unit: AbilityTrigger, effect_types):
        self.unit, self.effect_types = unit, effect_types

    def should_trigger(self, ctx):
        he = ctx.has_effect or (lambda u, et, sf=6, ml=0: False)
        us = _units_of(self.unit, ctx)
        return any(he(u, et, 6, 0) for u in us for et in self.effect_types)


class HasFaction(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$HasFaction(unit, faction, mode)` -> `IdunBattle.Entities.Triggers.HasFactionTrigger$$ShouldTrigger` :
    resout `unit` en UNE entite (slot 7 = select-single) puis `IdunBattle.Entities.UnitExtensions$$HasFaction(entity, faction@+0x10)`.
    `faction` = valeur de l'enum `IdunBattle.Entities.Enum.UnitFaction` (0=Ultramarines, 1=Sisterhood,
    2=AstraMilitarum, ...). Entite absente -> False (le natif retourne sans valeur = 0).

    Port : la faction offline vient de `ctx.faction_of` (FactionId gameconfig, une CHAINE) -- on compare donc
    au NOM de l'enum (`UNIT_FACTION_NAMES[value]`), meme reduction que `UnitsFromFaction` (qui, lui, recoit
    deja le nom via `System.Enum.ToString`). Accesseur absent -> False.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$ExecuteBehaviour`
    (`If(HasFaction(target, 1=Sisterhood), AddEffect(1401), AddEffect(1436))`)."""
    def __init__(self, unit: AbilityTrigger, faction):
        self.unit, self.faction = unit, faction

    def should_trigger(self, ctx):
        fo = ctx.faction_of
        if fo is None:
            return False
        name = UNIT_FACTION_NAMES.get(int(self.faction)) if not isinstance(self.faction, str) \
            else self.faction
        if name is None:
            return False
        return any(fo(u) == name for u in _units_of(self.unit, ctx))


# `IdunBattle.Entities.Enum.UnitFaction` (dump enums du build) — la table est PARTIELLE : seules les valeurs
# effectivement referencees par un arbre porte y figurent (ajouter au fil des call-sites, jamais deviner).
UNIT_FACTION_NAMES = {
    0: "Ultramarines", 1: "Sisterhood", 2: "AstraMilitarum", 3: "BlackLegion", 4: "DeathGuard",
    5: "Orks", 6: "BlackTemplars", 7: "Necrons",
}


class HasUnit(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$HasUnit(tiles, mode)` : la/les TUILE(s) du selecteur portent-elles
    une unite (`GetUnitOrMachine(tile) != null`) ? Predicat TILE-domain -- consomme sous un `Filter`/
    `FilterContinuous` ou le sujet est un id de tuile (`IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInLine`).
    Lit `ctx.board.coord(tile)` + l'occupation VIVANTE de `ctx.units` (meme modele que `CanAddUnit`/`Units`).
    board absent -> False."""
    def __init__(self, tiles: AbilityTrigger):
        self.tiles = tiles

    def should_trigger(self, ctx):
        return bool(_units_on(self.tiles, ctx))


def _units_on(tiles: AbilityTrigger, ctx) -> list:
    """Occupants VIVANTS des tuiles rendues par `tiles` (mirror `IdunBattle.Entities.UnitExtensions$$GetUnitOrMachine`
    applique a une entite-TUILE). Accepte le domaine id-de-tuile (int), position (col,row) ou dict d'unite
    (passthrough). Helper partage `HasUnit`/`AreEnemies` (tile-domain)."""
    board = getattr(ctx, "board", None)
    raw = tiles.evaluate(ctx)
    items = [] if raw is None else ([raw] if isinstance(raw, (dict, int, tuple)) else list(raw))
    out = []
    for it in items:
        if isinstance(it, dict):
            out.append(it)
            continue
        if isinstance(it, bool) or board is None:
            continue
        p = None
        if isinstance(it, int):
            p = board.coord(it) if it in board.by_id else None
        elif isinstance(it, (tuple, list)) and len(it) == 2:
            p = (it[0], it[1])
        if p is None:
            continue
        for u in ctx.units:
            if _is_alive(u) and _pos(u) == (int(p[0]), int(p[1])):
                out.append(u)
    return out


class AreEnemies(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$AreEnemies(a, b, mode)` : symetrique exact d'`AreFriends` (equipes
    DIFFERENTES). `IdunBattle.Entities.UnitExtensions$$IsFriend` == false pour au moins une paire resolue.
    Les deux operandes sont normalises par `_units_of` (un ref-unite seul compte pour 1). None d'un cote ->
    False. Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInLine`
    (`HasUnit(subject) & AreEnemies(Owner@0x148, Units(subject))`)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        ta = [u.get("team") for u in _units_of(self.a, ctx) if isinstance(u, dict)]
        tb = [u.get("team") for u in _units_of(self.b, ctx) if isinstance(u, dict)]
        return any(x is not None and y is not None and x != y for x in ta for y in tb)


class HasNegativeModifier(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$HasNegativeModifier(unit, statType)` ->
    `IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger` : l'entite porte-t-elle AU MOINS UNE
    modification PER-SOURCE strictement NEGATIVE sur l'un des StatTypes du filtre (`@+0x18` = array inline) ?
    Le natif itere le `Dictionary<source, ValueModification>` du `StatComponent` et rend true au 1er
    `value(@+0x14) < 0` dont le `stat(@+0x10)` est dans le filtre.

    Port : `UnitStats.has_negative_modifier(stat_types)` (mirror deja en place, foyer du gate
    ConquerorImperative) via l'accesseur `ctx.get_stat`-adjacent `ctx.has_negative_modifier` ; accesseur
    absent -> False (degradation fidele). Consommateur porte :
    `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger`
    (`HasNegativeModifier(subject@0x180, 0x10=FixedArmor)`)."""
    def __init__(self, unit: AbilityTrigger, stat_types):
        self.unit = unit
        self.stat_types = tuple(int(s) for s in
                                (stat_types if isinstance(stat_types, (list, tuple, set, frozenset))
                                 else (stat_types,)))

    def should_trigger(self, ctx):
        fn = getattr(ctx, "has_negative_modifier", None)
        if fn is None:
            return False
        return any(fn(u, self.stat_types) for u in _units_of(self.unit, ctx))


class IsInTeamAura(AbilityTrigger):
    """`IdunBattle.Entities.Triggers.IsInAuraRangeTrigger$$ShouldTrigger` (construit par
    `IdunBattleLogic.Entities.DSLFactory$$IsInTeamContagionsOfNurgleAura(unit, teamReference)` = le meme trigger
    fige sur `effectType = 0x42f = 1071 ContagionsOfNurgle_ArmorReduction1`) :

        unit = <selecteur @+0x10>.SelectSingle(entities)      ; null -> false
        ref  = <selecteur @+0x18>.SelectSingle(entities)      ; null -> false
        team = EntityExtensions.GetCurrentTeamId(ref)
        return battleQuery.<slot 0x92>(effectType@+0x20, team, unit)

    -> « `unit` est-elle dans la PORTEE d'une aura `effectType` d'un porteur de l'equipe de `ref` ? ».

    RESIDU ASSUME : le canal d'AURA n'est PAS materialise offline (aucun `GetInRangeAuraAmount` porte ;
    cf. la meme limitation cote `EffectFromOwner`). Le noeud lit `ctx.is_in_team_aura(unit, effectType,
    teamRef)` ; accesseur ABSENT (cas courant) -> **False** = degradation fidele « present != applique ».
    L'autre branche du predicat consommateur (`HasNegativeModifier` FixedArmor) est, elle, PLEINEMENT
    portee -- c'est celle qui est exercable/validable live."""
    def __init__(self, unit: AbilityTrigger, effect_type: int, team_reference: AbilityTrigger):
        self.unit, self.effect_type, self.team_reference = unit, int(effect_type), team_reference

    def should_trigger(self, ctx):
        fn = getattr(ctx, "is_in_team_aura", None)
        if fn is None:
            return False
        us = _units_of(self.unit, ctx)
        refs = _units_of(self.team_reference, ctx)
        if not us or not refs:
            return False
        return any(fn(u, self.effect_type, r) for u in us for r in refs)


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


class IsRepairable(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsRepairable(unit, flag)` -- le predicat qui aiguille le
    `If(IsRepairable, Repair, Heal)` de `IdunBattleLogic.Entities.Abilities.Active.Loki.
    InspiredToGreatnessAbility$$RepairOrHeal` (i2 : « heals **or repairs** it »).

    SEMANTIQUE DEDUITE (le ctor du trigger est MISLABELE par ghidra -- on lit la STRUCTURE : un
    trigger a UN operande-unite + un flag) = `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType
    (unit, 1 = Repair)` = `HasTrait(AffectedByHealAndRepair = 0x421)` OU `IsMechanical(unit)`
    (Mechanical 5 | LivingMetal 1000 | Vehicle 1029) -- le COMPLEMENTAIRE exact du type 0 deja porte
    (`healable_heal_type_0` : `HasTrait(0x421) OU NON-IsMechanical`), et le seul aiguillage qui rend
    l'i2 (« Cannot be healed, but can be repaired instead » du trait Mechanical).

    DISCRIMINANT LIVE : si la lecture etait fausse, une cible MECANIQUE prendrait la branche `Heal`,
    dont la garde `healable_heal_type_0` la REJETTE -> 0 PV rendus. Un gain de PV mesure sur une cible
    mecanique PROUVE la branche `Repair`. `ctx.has_trait` absent -> False (branche `Heal`)."""
    def __init__(self, unit: AbilityTrigger):
        self.unit = unit

    def should_trigger(self, ctx):
        from .traits.unit_trait import UnitTrait
        ht = ctx.has_trait
        if ht is None:
            return False
        mech = (UnitTrait.Mechanical, UnitTrait.LivingMetal, UnitTrait.Vehicle)
        return any(ht(u, int(UnitTrait.AffectedByHealAndRepair)) or any(ht(u, int(t)) for t in mech)
                   for u in _units_of(self.unit, ctx))


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


class IsCharging(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsCharging(a, b)` -> predicat dont l'`Evaluate` appelle le
    slot `IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)`. MIRROR du decompile de
    CETTE methode (2 termes, `&`) :

        return AreEntitiesAdjacent(caster, target)
               && GetComponent<UnitComponent>(caster).ChargedUnitIds@+0x190.Contains(target.Id)

    Le 2e terme est ecrit par `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` (toute unite
    devenue NOUVELLEMENT adjacente pendant un pas de deplacement) et vide par
    `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` -> « a charge cette unite CE TOUR ».

    ⚠ « a charge » n'est donc PAS « a bouge » : une unite qui bouge SANS arriver au contact de la
    cible, ou qui etait DEJA adjacente avant son pas, n'est pas en charge.

    Les CONSOMMATEURS de ce noeud passent tous par le foyer `engine/battle_query.py::is_charging`
    (jamais par une re-derivation locale) : canal DEGAT `AvalancheOfMuscle` 1025 / `FeederTendrils`
    (case-r32, gate `effects/base.py::is_not_charging`) et canal COUPS `SagaOfTheWarriorBorn_Owner`
    1223 (case-r33, gate `effects/base.py::is_charging_attack`). L'ancienne approximation par
    `has_moved` du canal modifier a ete RETIREE le 2026-07-28 — ne pas la reintroduire : elle
    sur-accordait (mesure `+599`/coup sur `astraBullgryn`). L'inventaire complet des 16 xrefs du
    noeud, avec ce qui reste non porte, vit dans `docs/rl/case-r33-ischarging-xrefs.md`.

    `ctx.charged_units` absent -> ensemble vide -> False (degradation fidele)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        us_a = [u for u in _units_of(self.a, ctx) if isinstance(u, dict)]
        us_b = [u for u in _units_of(self.b, ctx) if isinstance(u, dict)]
        acc = getattr(ctx, "charged_units", None)
        for ua in us_a:
            charged = set(acc(ua)) if acc is not None else set()
            pa = _pos(ua)
            for ub in us_b:
                pb = _pos(ub)
                if pa is None or pb is None or hexgeo.distance(pa, pb) != 1:
                    continue                          # AreEntitiesAdjacent
                if ub.get("id") in charged:           # ChargedUnitIds.Contains(target.Id)
                    return True
        return False


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
