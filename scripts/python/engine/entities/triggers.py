"""Noeuds PREDICAT du DSL = famille `AbilityTrigger.ShouldTrigger` (kind T).

Mirror du namespace natif `IdunBattle.Entities.Triggers` (+ `.Conditions`) : les concrets vivent ici,
a cote de leurs freres `entities/{abilities,selectors,formulas,behaviours,effects}` ; la base
`AbilityTrigger` (= `IdunBattle.DSL`) reste dans `dsl/base.py`. Construits via la facade `DSLFactory`
(`dsl/nodes.py`)."""
from __future__ import annotations

import hexgeo

from ..dsl.base import (AbilityTrigger, AAmountFormula, TargetsSelector, Const, _pos, _feet,
                        _units_of, _is_alive, _same_entity, _c_mod)
# `IdunBattle.Entities.Enum.UnitFaction` — FOYER UNIQUE (#241) : mirror 1:1 des 21 membres transcrits
# de `data/symbols/<build>/frida/enums.tsv`. La table locale etait PARTIELLE (8 valeurs, « ajouter au
# fil des call-sites ») ; elle en derive maintenant, ce qui la rend complete sans changer aucune des
# 8 valeurs qu'elle portait deja. Re-export : l'API `triggers.UNIT_FACTION_NAMES` est inchangee.
# ⚠ NON CONFRONTE LIVE -- differe par la MAJ gqfc5mff6c -> rnca9r7q6c. Le seul consommateur est
# `HasFaction.should_trigger` ci-dessous (arbre `ThriceBlessedConflagration`), dont la garde
# `tests/engine/test_thrice_blessed_decision_live.py` n'a PAS pu etre re-jouee : son run est tombe
# dans la fenetre d'arret du jeu. Le changement est value-preserving par construction (memes 8
# valeurs, meme lecture `UNIT_FACTION_NAMES[value]`) -- a re-jouer tel quel apres migration de build.
from .unit_faction import UNIT_FACTION_NAMES        # noqa: F401 (re-export)


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


class IsCanAddUnit(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLTriggers$$IsCanAddUnit(selector)` -- MIRROR du decompile :

        return <trigger DAT_1833d73e0>( DSLSelectors.CanAddUnit(selector), DSLFormulas+0x20 )

    DEUX pieges tenus ensemble, et c'est leur conjonction qui donne le sens :

    1. **La CLASSE du trigger n'est PAS celle que ghidra nomme.** Le ctor affiche
       `AmountIsGreaterAbilityTrigger..ctor` -- corps DEDUPLIQUE (`base() ; +0x10 = selector ;
       +0x20 = minAmount`), donc UN seul proprietaire dans la table pour les deux classes soeurs. Le
       `Il2CppClass*` reellement alloue (`DAT_1833d73e0`) est celui qu'alloue AUSSI
       `IdunBattleLogic.Entities.DSLTriggers$$AmountIsZero`, dont la semantique (`NOT(...)` = « la
       selection est VIDE ») ne tient QUE si la comparaison est `>=`. C'est donc
       `AmountIsEqualOrGreaterAbilityTrigger`. (`AmountIsGreaterThanZero`, lui, alloue une classe
       DIFFERENTE -- `DAT_1833d7670` -- et lit `DSLFormulas+0x18`.)
    2. **`DSLFormulas+0x20` = `Direct(1)`**, pas `Direct(0)` : `IdunBattleLogic.Entities.DSLFormulas
       $$.ctor` pose `+0x18 = Direct(0)`, `+0x20 = Direct(1)`, `+0x28 = Direct(2)`,
       `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`.

    => `IsCanAddUnit(sel)` = `Count(CanAddUnit(sel)) >= 1` = « AU MOINS UNE tuile de `sel` peut
    accueillir une unite ». Lire la paire a l'envers (`> 1` avec la classe affichee) rendrait le
    predicat TOUJOURS FAUX sur un `First(...)`, et tuerait silencieusement une branche.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.GrapnelLauncherAbility$$
    ExecuteBehaviour` = `IsCanAddUnit(First(Cache(Tiles(Target))))` -- « la tuile d'origine de la
    cible est-elle libre ». Le `CanAddUnit` est celui du port (`selectors.tiles.CanAddUnit` :
    walkable ET aucun pied d'unite VIVANTE), evalue sur l'etat LIVE."""
    def __init__(self, selector):
        self.selector = selector

    def should_trigger(self, ctx):
        from .selectors.tiles import CanAddUnit
        return len(CanAddUnit(self.selector).evaluate(ctx) or []) >= 1


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


def is_mechanical(unit: TargetsSelector, selection_type: int = 0) -> AbilityTrigger:
    """`IdunBattleLogic.Entities.DSLTriggers$$IsMechanical(unit, selectionType)` — MIRROR de la FACTORY :
    le natif N'ALLOUE PAS de predicat dedie, il compose

        AmountIsEqualOrGreaterAbilityTrigger( MechanicalUnits(unit, selectionType),
                                              formulas+0x20 = Direct(1) )

    (`DSLFormulas$$.ctor` alloue les constantes partagees `+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
    `+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)` -- d'ou le `>= 1`). La classe
    allouee (`DAT_1833d73e0`) est DISTINCTE de celle d'`AmountIsGreaterThanZero` (`DAT_1833d7670`,
    qui prend `+0x18 = Direct(0)`) : `>= 1` et `> 0` coincident sur un cardinal, mais ce sont bien
    deux noeuds natifs differents -- on mirror celui qui est appele.

    Le sujet est un SELECTEUR : sous un `Filter`, passer `Subject()` (le natif passe `selectors+0x68`,
    le selecteur-sujet partage). Consommateurs portes :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetPossibleResurrectTargets`
    (`HasTrait(It, 0x10 = Hero) & IsMechanical(It)`) et `$$GetMaxSummonsFormula` (`IsMechanical` seul)."""
    from .formulas import Count
    from .selectors import MechanicalUnits
    return AmountIsEqualOrGreater(Count(MechanicalUnits(unit, selection_type)), Const(1))


class IsTurnOf(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)` = `new <DAT_1833ab568>(selector,
    matchState@+0x10)` — ctor gshared 2-champs MISLABELE par ghidra
    (`System.Linq.Expressions.Interpreter.QuoteInstruction$$.ctor` : STRUCTURE lue, jamais le nom,
    cf. l'en-tete de `dsl/base.py`). La classe allouee est
    `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger`.

    MIRROR de `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger` (#366-r1-turnof) :

        if (ctx.CurrentPlayer == null) return false;               # garde de tete, ctx@+0x50
        first = selector.SelectFirst(ctx);                         # slot 1 de l'interface selecteur
        if (first != null && EntityExtensions.IsPlayer(first))     # EntityType == 4 (PLAYER)
            return first.Id == ctx.CurrentPlayer.Id;               # chemin PLAYER (voir plus bas)
        foreach (e in selector.<slot 6>(ctx, selectionType = 0))   # variante ACTEURS
            if (e.GetComponent<OwnerComponent>().CurrentPlayerEntityId != ctx.CurrentPlayer.Id)
                return false;                                      # sort FAUX des qu'UNE diverge
        return true;                                               # enumeration epuisee -> VRAI

    => l'agregation est **`all`**, et le **set VIDE rend VRAI** (le `MoveNext()` faux sort sur
    `return 1`). Le port agregeait par `any(...)` jusqu'a #366-r1-turnof : ecart INERTE sur les
    call-sites natifs (aucun ne soumet 2 entites-unites, mesure dans
    `docs/rl/case-366-r1-turnof-all.md`), mais faux des qu'un selecteur multi-entites est passe.

    Trois lectures qui ferment la semantique de la boucle :
      * le composant lu est `IdunBattle.Entities.Components.OwnerComponent`, champ
        `get_CurrentPlayerEntityId` (+0x10) — le MEME couple de champs que
        `IdunBattle.View.FSM.VisualBattleQuery$$IsControlledByCurrentPlayer`, qui l'appelle par son
        nom ; donc bien le proprietaire COURANT (mind-control inclus), pas l'original ;
      * l'enumeration mappe chaque entite par `IdunBattle.DSL.TargetsSelector$$SelectUnit(e, 0)`, et
        `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` rend VRAI INCONDITIONNELLEMENT
        pour `selectionType = 0` (seuls 1/2/3 filtrent vie et flag 0x11) => **aucun filtre de vie**,
        un porteur MORT reste dans le set ;
      * une TUILE (ou un `UnitFoot`) est resolue en son occupant par le meme `SelectUnit` — une tuile
        VIDE disparait donc du set, et c'est la seule facon d'atteindre le cas « set vide ».

    **Chemin PLAYER non expose par le port** : quand le selecteur rend une entite de type PLAYER
    (`IdunBattleLogic.Entities.DSLSelectors$$Player(team)` ->
    `IdunBattle.Entities.Selectors.PlayersByTeamSelector`), le natif court-circuite la boucle et
    compare l'Id du PREMIER selectionne au joueur courant. Trois call-sites natifs l'empruntent
    (`EnvAngelsOfDeathAbility` / `EnvValkyrieStrikeAbility` / `EnvValkyrieStrike_AttackAbility`,
    tous `$$CreateTrigger`), aucun n'est porte : le port n'a pas d'entite-JOUEUR, donc ce chemin
    n'est pas mirrote (l'ecrire serait inventer une representation).

    Deux call-sites natifs deja portes (imperativement) confirment la lecture de fond :
      * `FleshMetalGunsAbility$$CreateTrigger` = `On(0x16=TurnStart_Actions) & IsTurnOf(Self@0x148)` —
        la rotation d'armes ne fire qu'au debut du tour de SON porteur (ground truth live case-222 §B) ;
      * `IdunBattle.Entities.Effects.FirstAidHealEffect$$CreateTargetTrigger` =
        `On(0x13) & IsTurnOf(Units(tile))` — l'ennemi debout sur une tuile FirstAid n'est PAS soigne a
        MON tour.

    `ctx.current_player_id is None` (contexte sans tour courant : prediction, arbre purement numerique)
    -> **False** : c'est la garde de tete du natif (`ctx@+0x50 == 0 -> return false`), pas une
    degradation inventee.

    LIMITE ASSUMEE : le natif LEVE (`FUN_1801f51f0`) quand le selecteur rend une collection NULLE, la
    ou une collection VIDE rend VRAI. `_units_of` confond les deux (`None -> []`), donc le port rend
    VRAI dans les deux cas. Le port n'a pas de canal d'exception ; et cote port un accesseur singleton
    qui rend `None` signifie « le contexte n'a pas cette entite », ce qui est exactement le cas
    « `SelectUnit` filtre l'entite -> set vide -> VRAI » du natif."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def should_trigger(self, ctx):
        cur = ctx.current_player_id
        if cur is None:                       # `if (ctx@+0x50 == 0) return false;`
            return False
        # `foreach (...) if (owner != current) return false; return true;` -- `all`, set vide -> VRAI.
        return all((u or {}).get("player") == cur for u in _units_of(self.unit, ctx))


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




class IsUnitWithVisualId(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLTriggers$$IsUnitWithVisualId(unit, visualIdFormula)` : l'unite
    resolue par `unit` porte-t-elle le `visualId` rendu par la formule ? Le call-site porte
    (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MyWillBeDoneOverlordAbility$$GetTargetFriend`)
    nourrit la formule par `VisualUnitIdFromUnitId(ConfigConstString(<config>, 0))`, donc une CHAINE.
    Entite absente / formule nulle -> False (degradation fidele)."""
    def __init__(self, unit: AbilityTrigger, visual_id):
        self.unit, self.visual_id = unit, visual_id

    def should_trigger(self, ctx):
        vid = self.visual_id.evaluate(ctx) if hasattr(self.visual_id, "evaluate") else self.visual_id
        if vid is None:
            return False
        return any((u or {}).get("visualId") == vid for u in _units_of(self.unit, ctx))


class IsInPersistentDataList(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLTriggers$$IsInPersistentDataList(abilityOrEffect, unit, dataKey,
    value)` -> `Idun.Source.IdunBattle.Logic.Entities.Triggers.IsInPersistentDataListTrigger$$ShouldTrigger`
    — MIRROR du decompile, dont le corps utile tient en trois gestes :

        entity = <selecteur @+0x28>.SelectSingle(entities)          # null -> pas de verdict
        key    = <formule @+0x38 (ou @+0x30)>.Calculate(entities)   # la dataKey (string)
        v      = <formule @+0x40>.Calculate(entities)               # la VALEUR cherchee
        list   = entity.GetComponent<PersistentDataComponent>()
                       .TryGetPersistDataList(GetPersistentDataId(abilityOrEffect@+0x10), key)
                 ?? new List<T>()
        return list.Contains(v)

    Le port range la liste sous la MEME cle composite que le scalaire (`(abilityOrEffect, dataKey)`,
    cf. `PersistentDataComponent`) et lit via l'accesseur `ctx.persistent_data_list` — absent (contexte
    hors runner) -> liste VIDE -> False, ce qui est la reponse du natif quand la cle n'existe pas."""
    def __init__(self, ability_or_effect: int, unit: AbilityTrigger, data_key, value):
        self.ability_or_effect = int(ability_or_effect)
        self.unit, self.data_key, self.value = unit, data_key, value

    def should_trigger(self, ctx):
        fn = ctx.persistent_data_list
        if fn is None:
            return False
        key = self.data_key.evaluate(ctx) if hasattr(self.data_key, "evaluate") else self.data_key
        val = self.value.evaluate(ctx) if hasattr(self.value, "evaluate") else self.value
        if val is None:
            return False
        ck = (self.ability_or_effect, key)
        return any(val in (fn(u, ck) or ()) for u in _units_of(self.unit, ctx))


class Contains(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLTriggers$$Contains(list, elements)` ->
    `IdunBattle.Entities.Triggers.XContainsYTrigger$$ShouldTrigger` -- MIRROR du decompile :

        y = <selecteur @+0x18 `elements`>.SelectSingle(entities)   # null -> FALSE
        xs = <selecteur @+0x10 `list`>.Select(entities)
        foreach (x in xs) if (x.Id == y.Id) return true
        return false

    Trois traits LUS qui ne se devinent pas :
      * `elements` passe par **SelectSingle**, pas `Select` : le second operande est un element
        UNIQUE, et un selecteur qui rend 0 ou >1 entite ne « contient » rien -> FALSE ;
      * la comparaison est sur l'**Id** (`get_Id`), pas sur l'identite d'objet ;
      * l'ordre des arguments est `Contains(CONTENANT, CONTENU)` -- le champ `+0x10` est la liste.

    11 proprietaires natifs (`docs/rl/dsl-usage/dsl-usage-primitives.tsv`). Premier consommateur
    porte : la formule de tri de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PrimarchOfTheFirstLegionAbility$$CreateBehaviour`
    (`Contains(GetPersistentDataListAsEntities(...), It@DSLSelectors+0x68)`)."""
    def __init__(self, list_sel: TargetsSelector, elements: TargetsSelector):
        self.list_sel, self.elements = list_sel, elements

    def should_trigger(self, ctx):
        ys = _units_of(self.elements, ctx)
        if len(ys) != 1:                      # `SelectSingle` : 0 ou plusieurs -> pas de verdict
            return False
        yid = (ys[0] or {}).get("id")
        if yid is None:
            return False
        return any((x or {}).get("id") == yid for x in _units_of(self.list_sel, ctx))


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

    Le slot 0x92 EST `IdunBattle.Core.Services.BattleQuery$$IsInTeamAuraRange` =
    `GetInRangeAuraAmount(effectType, team, target, returnFirst: true) > 0`, entierement lisible au
    decompile -> PORTE (case-224) dans `battle_query.get_in_range_aura_amount`, avec son etage de
    portee dans `entities/effects/aura.py`. Le noeud lit `ctx.is_in_team_aura(unit, effectType,
    teamRef)`, fourni par `runner/abilities/behaviours/context.entities_from_state`.

    ⚠ Comparateur INCLUSIF (`d <= GetCurrentRange(porteur)`) : la boucle native `continue` seulement
    quand `range < dist`. Mesure live (case-224, `abilityTargets` sur `EntropyCannons`) : a
    `TurnsStarted(porteur)` = 1 / 3 / 5 le seuil natif vaut 1 / 2 / 3, et une mutation du `<=` en `<`
    rougit exactement les tuiles a `d == range`. Le predicat par UNITE (`IsInUnitAura` ci-dessous)
    est INCLUSIF lui aussi : les deux versions ont le MEME rayon effectif (#293).

    Accesseur ABSENT (contexte hors runner, ex. prediction) -> **False** = degradation fidele."""
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


class IsInUnitAura(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLTriggers$$IsInUnitContagionsOfNurgleAura(target, unit)` -- MIRROR
    du decompile, qui n'est PAS un trigger dedie mais un COMPOSE de deux formules :

        range = DSLFormulas.ContagionsOfNurgleRange(unit, unitSelectionType=0, isNextTurn=false)
        dist  = DSLFormulas.MinDistance(target, unit)
        return new AmountIsEqualOrGreaterAbilityTrigger(amount: range, minAmount: dist)

    `IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` evalue
    `+0x18` (amount) dans `iVar13`, `+0x20` (minAmount) dans `uVar15`, et finit par
    `return uVar15 <= iVar13` -> **`dist <= range`, INCLUSIF**, exactement comme la version
    d'EQUIPE (`IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount`). Les deux versions ont
    donc le MEME rayon effectif -- ce qui renverse `case-224-is-in-contagions-of-nurgle-range.md`
    §2.1 (« UNITE == EQUIPE - 1 »), verrouille a l'epoque par un test qui ne comparait le port
    QU'A LUI-MEME, faute de consommateur porte.

    ⚠ **LE PIEGE, et c'est LUI qui a fait ecrire « STRICT » (#224 -> #299, tranche par #293).**
    Le ctor visible au decompile porte le nom `IdunBattle.Entities.Conditions.
    AmountIsGreaterAbilityTrigger$$.ctor`, et le `ShouldTrigger` de CETTE classe-la finit bien par
    `return uVar15 < iVar13`, STRICT. **Ce nom ne designe PAS la classe instanciee.** Ce ctor est un
    corps TRIVIAL (`base..ctor` + `[this+0x18] = amount` + `[this+0x20] = minAmount`) que IL2CPP
    DEDUPLIQUE entre toutes les conditions de meme layout ; la table des symboles ne lui donne qu'UN
    proprietaire, et c'est `AmountIsGreater...`. La classe REELLEMENT allouee est celle dont le
    pointeur est charge juste avant `il2cpp_object_new` -- et c'est le MEME global que celui de
    `IdunBattleLogic.Entities.DSLTriggers$$AmountIsEqualOrGreater`, pas celui de
    `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreater`.
    **Ne jamais re-deriver un comparateur du NOM de son `.ctor`.** Re-derivation mecanique (pointeur
    de classe lu dans les octets + encodage `setg` vs `setge`, et l'inventaire des 22 sites
    d'instanciation) : `python scripts/python/probe_293_aura_predicate_comparator.py --inventory`.

    Les deux autres modeles qui expliquaient l'ecart d'une unite sont REFUTES, chacun par lecture
    de son ETAGE (pas par un fit) :

    * `MinDistance` natif = `hexdist - 1` ? NON. `IdunBattle.Entities.Formulas.MinDistanceFormula$$
      Calculate` accumule `Math.Min(min, PositionComponent.Distance(b, a))` ;
      `IdunBattle.Entities.Components.PositionComponent$$Distance` =
      `IdunBattle.Utils.Hex.CubeCoordinate$$Distance(this.ToCube(), other.ToCube())` =
      `Max(|dx|, |dy|, |dz|)`. Aucun offset sur tout le chemin.
    * `GetCurrentRange` natif = table + 1 ? NON. `IdunBattle.Entities.Effects.Loki.
      ContagionsOfNurgle_ArmorReduction_Effect$$GetRangeOnOwnerTurn(numRounds)` est un arbre
      `ConditionalAmount` lu en entier -- `Not(AmountIsGreater(numRounds, Direct(2))) ? Direct(1)
      : (Not(AmountIsGreater(numRounds, Direct(4))) ? Direct(2) : Direct(3))`, soit `<=2 -> 1`,
      `<=4 -> 2`, sinon `3` : exactement `effects/aura.aura_range_on_owner_turn`.

    Confirmation live (`probe_224_cursed_plague_bell_attack.py`, deux paliers, attribution par le
    tag natif `Passive_Ability_Type = 1071`) : `TurnsStarted = 3` (range 2) -> la cloche part a d=1
    et d=2, PAS a d=3 ; `TurnsStarted = 5` (range 3) -> a d=2 et d=3, PAS a d=4.

    Consommateur : `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$
    IsInContagionsOfNurgleRange` (cf. `runner/abilities/deathguard.is_in_contagions_of_nurgle_range`).
    `effect_type` reste un PARAMETRE (le natif le fige a 1071 dans le seul helper `...Contagions...`,
    mais `AuraEffectRangeFormula` est generique sur `IAuraEffect`)."""
    def __init__(self, target: TargetsSelector, effect_type: int, unit: TargetsSelector,
                 is_next_turn: bool = False):
        from .formulas import AuraEffectRange, MinDistance
        self.target, self.unit, self.effect_type = target, unit, int(effect_type)
        self.range_formula = AuraEffectRange(unit, int(effect_type), is_next_turn=is_next_turn)
        self.distance_formula = MinDistance(target, unit)

    def should_trigger(self, ctx):
        # INCLUSIF -- mirror de `AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger`
        # (`return minAmount <= amount`), la classe REELLEMENT instanciee par
        # `IdunBattleLogic.Entities.DSLTriggers$$IsInUnitContagionsOfNurgleAura` ; le nom du `.ctor`
        # (deduplique sur `AmountIsGreater...`) ne dit rien de la classe -- cf. le docstring.
        return int(self.distance_formula.calculate(ctx)) <= int(self.range_formula.calculate(ctx))


class IsAlive(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsAlive(unit)` → `IdunBattle.Entities.Conditions.IsAliveAbilityTrigger$$ShouldTrigger` : `UnitExtensions.IsAlive` = vivant & hp>0.
    (`Damageable`/`Alive` filtrent un ENSEMBLE sur le même critère.)"""
    def __init__(self, unit: AbilityTrigger):
        self.unit = unit

    def should_trigger(self, ctx):
        return any(_is_alive(u) for u in _units_of(self.unit, ctx))


class OwnerIsAlive(AbilityTrigger):
    """`IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger$$ShouldTrigger` -- le SINGLETON
    PARTAGE `<DSLTriggers+0x20>`, sans operande (ni selecteur, ni formule).

    MIRROR du decompile :

        if (!EntityExtensions.IsUnit(entities.Owner@+0x18))  return true;   // pas une unite -> VRAI
        return UnitExtensions.IsAlive(entities.Owner@+0x18, this._state@+0x10);

    ###### POURQUOI IL A FALLU LE NOMMER, ET COMMENT ######
    Ce noeud n'est NOMME NULLE PART : `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`
    l'alloue par `new <DAT_183343468>(dsl.state@+0x10)` et l'assigne a `<DSLTriggers+0x20>`, et ce
    slot de metadata-usage n'a QUE cette xref dans tout le binaire (donc la classe n'est instanciee
    nulle part ailleurs, donc aucun `DSLTriggers$$X` ne la nomme). Identification, TROIS sources :

      1. **FORME** -- le ctor pose UN champ (`+0x10`), donc `taille = 24`, parent
         `IdunBattle.DSL.AbilityTrigger` (taille 16). Il y a **23** classes de ce gabarit dans
         `data/symbols/<build>/frida/classes.tsv`.
      2. **TYPE DU CHAMP** -- l'argument est `dsl.state` (un `MatchState`), pas un selecteur.
         Sur les 23, 21 sont allouees par un `IdunBattleLogic.Entities.DSLTriggers$$<X>` NOMME qui
         leur passe un SELECTEUR (`CanMove`/`HasTile`/`IsMoving`/`IsWounded`/`IsEffectActive`/
         `IsEffectCreatedThisTurn`/`TriggeringAbilityIsNone`/`IsAbilityCountedOnlyOnce`/
         `IsPartialAttackAbility`/`CanBeDisplaced`/`IsSpecialActiveAbility`/... ) -- donc leur slot
         de classe n'est PAS `DAT_183343468`. Restent DEUX classes sans allocateur nomme, et ce sont
         exactement les DEUX que `InitializeShared` alloue :
         `IdunBattle.Entities.Triggers.IsMeleePositionAbilityTrigger` (son `ShouldTrigger` invoque
         le slot d'interface 9 d'`IBattleQuery` SUR `this+0x10` -> son champ est un **BattleQuery**,
         = `dsl+0x28`, donc `<DSLTriggers+0x18>`) et `OwnerIsAliveAbilityTrigger` (son champ part en
         2e argument d'`IdunBattle.Entities.UnitExtensions$$IsAlive(unit, state)` -> un
         **MatchState**, = `dsl+0x10`, donc `<DSLTriggers+0x20>`). L'appariement est FORCE.
      3. **CORPS TRIVIAL DONT LE SLOT EST L'UNIQUE OPERANDE** -- `IdunBattleLogic.Entities.
         DSLTriggers$$IsRangedPosition` est litteralement
         `IdunBattle.DSL.AbilityTrigger$$op_LogicalNot(this+0x18)`. Cela NOMME `<+0x18>` =
         « IsMeleePosition » de facon independante, et confirme la moitie battleQuery de
         l'appariement ci-dessus. (Meme voie que celle qui a nomme `<+0x28>` = `IsTurnOf(Owner)` :
         `DSLTriggers$$IsTurnOf` alloue le MEME `DAT_1833ab568` avec les MEMES arguments.)

    Les trois porteurs LUS de `<+0x20>` (xrefs du motif `<dsl+0x88>+0x20`) le placent tous au meme
    endroit -- APRES un deplacement, AVANT l'attaque :
    `RammingSpeedAbility$$ExecuteBehaviour`, `SkyStrikeAbility$$ExecuteBehaviour`,
    `ExemplarOfTheKauyonAbility$$ExecuteBehaviour`. C'est le gate « le porteur a-t-il SURVECU au
    deplacement ? » (overwatch/piege/DoT declenches par la charge).

    `ctx.owner` (repli `ctx.caster`) ; owner non resolvable -> **True**, mirror de la branche
    `!IsUnit(Owner)` (le natif ne refuse pas, il laisse passer)."""
    def should_trigger(self, ctx):
        u = ctx.owner or ctx.caster
        if u is None:
            return True                       # `!EntityExtensions.IsUnit(Owner)` -> return true
        return _is_alive(u)


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
        return battleQuery.GetPositionMachineForPlayer(player) == this.Position (@+0x20)

    ⚠ **`GetPositionMachineForPlayer` n'interroge AUCUNE machine deployee** (RE #302 tranche 3, la
    ligne precedente de cette docstring disait le contraire) :

        teamIndex = player.GetComponent<TeamComponent>().<+0x24>
        grp = spawnPointSet@BattleQuery+0x78.GroupForPlayer(teamIndex, playerNr)
        if (grp != null) return grp.MachineOfWarPosition@+0x14        // propriete du PLATEAU
        return teamIndex == 1 ? 2 : (teamIndex == 2 ? 1 : 0)          // fallback SANS groupe

    -> « le GROUPE DE SPAWN du joueur COURANT porte-t-il le slot `position` ? ». C'est le joueur
    COURANT du tour, PAS le caster (`TurnComponent.CurrentPlayerId`). Le port de la cascade vit dans
    `engine.services.machine_of_war_position` ; la face DECISION la cable
    (`AiDecisionContext.machine_of_war_position`). Consomme par les abilities dont la GEOMETRIE
    depend du cote du plateau : `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetTargetAreaTiles`
    et `IdunBattleLogic.Entities.Abilities.Active.Loki.MacroPlasmaIncineratorAbility$$ExecuteBehaviour`
    (`If(this, Direct(1), Direct(4))` = coin du triangle), `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour` / `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$GetShape` (choix du triplet de directions).

    `ctx.current_player_machine_position` ; None = **non mesure** -> False. ⚠ RESIDU (#302) : cote
    COMBAT, `entities_from_state` alimente encore ce champ par le slot de la `MachineComponent` du
    joueur courant -- un PROXY exact quand une MoW est deployee, et « inconnu » sinon, alors que le
    natif repond toujours. Le cablage de la vraie source (les `SpawnPointGroups` de la BC) est fait
    cote DECISION ; la face COMBAT attend son `State.spawn_groups`."""
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
    """`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(a, b, selectionType)` ->
    `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger` -- MIRROR 1:1 du
    decompile, et il ne dit NI << une paire suffit >> NI << dist == 1 >> (#433-r3) :

        A = <sel a>.Select(entities, selectionType)      // slot 3 ; `.ctor` : a@+0x20, b@+0x28,
        B = <sel b>.Select(entities, selectionType)      //          selectionType@+0x18, query@+0x10
        if (A == null || B == null) throw;
        if (!A.Any() || !B.Any()) return false;
        foreach (x in A) foreach (y in B)
            if (!query.AreEntitiesAdjacent(x, y)) return false;      // slot 0x60
        return true;

    TROIS lectures, chacune contre le port d'avant :

    * **QUANTIFICATEUR UNIVERSEL.** Le natif rend FAUX des qu'UNE paire n'est pas adjacente et VRAI
      quand l'enumeration de `A` s'epuise sans echec -- un `forall`, pas un `exists`. Le port faisait
      `any(...)`, donc il declenchait des que N'IMPORTE QUELLE paire l'etait : divergence
      PERMISSIVE. La classe SOEUR `IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger`
      (resolue par le slot 10, cf. `runner/operations/triggers/loki/teleporting_in.py`) est, elle,
      un `exists` -- les deux ne se deduisent pas l'une de l'autre, elles se LISENT.
      Listes VIDES : le natif teste `Any()` AVANT la boucle et rend FAUX (un `All` nu rendrait vrai
      sur le vide) -> `not pa or not pb` -> False.
    * **La comparaison par paire est `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`**
      (surcharge `(entity1, entity2)` -- slot 0x60 de `IBattleQuery` sur ce build ; les deux
      arguments sont des elements d'enumeration, et c'est la seule des trois surcharges qui prenne
      deux entites nues ; recoupe par `IdunBattle.View.FSM.VisualBattleQuery$$AreAdjacent`, qui
      resout deux entites avant d'appeler ce meme slot). Elle delegue a
      `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`, dont la surcharge SCALAIRE vaut
      `(|dElev| < 2) & (tile1 == tile2 || ConnectivityComponent$$IsNeighbour(tile1, tile2))` : donc
      **PORTE D'ELEVATION** et **court-circuit d'IDENTITE**, tous deux absents du port d'avant.
      Le foyer est `services/battle_query.py::are_tiles_adjacent` (#433-r1) -- pas un 5e mirror.
    * **Le 3e argument va au SELECTEUR, PAS au predicat.** `selectionType` (`UnitSelectionType`,
      champ `+0x18`) n'est lu QUE comme 2e argument du `Select` des deux selecteurs ; il n'entre pas
      dans la comparaison par paire. Le port le prend au constructeur pour mirrorer la signature
      native et le garder INERTE ici ; la couche selecteur du port ne consomme pas encore le
      `UnitSelectionType` (residu `#433-r3-r2`).

    `ctx.board` = le graphe de tuiles (`state.board` cote COMBAT, `scene.board` cote DECISION) :
    fourni -> voisinage natif + porte d'elevation ; ABSENT -> degradation documentee du depot =
    adjacence hex pure (sure sur un board PLAT, ou `|dElev| = 0 < 2` partout). Une unite sans
    position -> empreinte VIDE -> la paire n'est PAS adjacente, donc le `forall` rend FAUX --
    exactement le natif, dont `GetTiles` rend alors une liste vide et dont la double boucle
    d'`AreTilesAdjacent(IList, IList)` ne tourne pas.

    EMPREINTES (#433-r3-r1, FERME). La surcharge appelee est
    `AreTilesAdjacent(GetTiles(entity1), GetTiles(entity2))` -- l'empreinte COMPLETE de chaque
    entite, LUE au decompile (`tiles1 = EntityExtensions.GetTiles(entity1, this@+0x38)`, idem pour
    `entity2`), et la surcharge LISTE de `MovementUtil$$AreTilesAdjacent` est un OU sur les paires
    de tuiles (elle rend FAUX sur une liste vide). Le port lit donc `_feet` (mirror `GetTiles`) et
    delegue chaque paire d'ENTITES au foyer UNIQUE `services/battle_query.py::are_entities_adjacent`,
    qui redescend sur le foyer d'empreintes de `runner/abilities/targeting.py` (#R30) des qu'un
    board est la. Une unite mono-tuile a `feet == [main tile]` -> resultat bit-a-bit inchange."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger, selection_type: int | None = None):
        # `selection_type` = `UnitSelectionType` du 3e argument de la factory : il part au SELECTEUR
        # (slot 3), jamais dans la comparaison par paire. Garde-le INERTE (cf. docstring).
        self.a, self.b, self.selection_type = a, b, selection_type

    def should_trigger(self, ctx):
        from ..services.battle_query import are_entities_adjacent   # lazy : garde anti-circulaire
        ua = _units_of(self.a, ctx)
        ub = _units_of(self.b, ctx)
        if not ua or not ub:                          # `!A.Any() || !B.Any()` -> false
            return False
        board = getattr(ctx, "board", None)
        for x in ua:
            for y in ub:                              # `foreach x foreach y : if (!adj) return false`
                if not are_entities_adjacent(_feet(x), _feet(y), board):
                    return False
        return True                                   # enumeration epuisee sans echec -> true


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
    1223 (case-ischarging-hits, gate `effects/base.py::is_charging_attack`). L'ancienne approximation par
    `has_moved` du canal modifier a ete RETIREE le 2026-07-28 — ne pas la reintroduire : elle
    sur-accordait (mesure `+599`/coup sur `astraBullgryn`). L'inventaire complet des 16 xrefs du
    noeud, avec ce qui reste non porte, vit dans `docs/rl/case-ischarging-hits-channel.md`.

    `ctx.charged_units` absent -> ensemble vide -> False (degradation fidele).

    EMPREINTES + PORTE D'ELEVATION (#433-r3-r1). Le terme geometrique de `BattleQuery$$IsCharging`
    est litteralement `AreEntitiesAdjacent(caster, target)`, donc
    `AreTilesAdjacent(GetTiles(caster), GetTiles(target))` : empreintes COMPLETES, gate
    `|dElev| < 2` et court-circuit d'identite compris. Le port ecrivait ici
    `hexgeo.distance(pa, pb) != 1` sur les MAIN TILES -- un TROISIEME ecart au meme foyer (ni
    empreinte, ni elevation, ni identite : la correction #433-r1 n'avait jamais atteint ce noeud).
    Il passe desormais par `services/battle_query.py::are_entities_adjacent`, comme `IsAdjacent`.

    RESIDU (quantificateur, NON traite ici) : le natif prend UNE unite de chaque cote --
    `IsChargingTrigger$$ShouldTrigger` appelle `TargetsSelector$$SelectUnit(entities, 3)` puis
    `SelectUnit(entities, 0)`, un `FirstOrDefault` filtre par `UnitExtensions$$MatchesUnitSelectionType`,
    et ne fait qu'UN appel a `IsCharging`. Le port boucle sur les deux listes (`any`). Identique sur
    des singletons (`Caster`/`Target`, tous les call-sites lus) ; le porter demanderait d'abord le
    filtre `UnitSelectionType`, qui est le residu `#433-r3-r2`."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger):
        self.a, self.b = a, b

    def should_trigger(self, ctx):
        from ..services.battle_query import are_entities_adjacent   # lazy : garde anti-circulaire
        us_a = [u for u in _units_of(self.a, ctx) if isinstance(u, dict)]
        us_b = [u for u in _units_of(self.b, ctx) if isinstance(u, dict)]
        acc = getattr(ctx, "charged_units", None)
        board = getattr(ctx, "board", None)
        for ua in us_a:
            charged = set(acc(ua)) if acc is not None else set()
            fa = _feet(ua)
            for ub in us_b:
                if not are_entities_adjacent(fa, _feet(ub), board):
                    continue                          # AreEntitiesAdjacent(caster, target)
                if ub.get("id") in charged:           # ChargedUnitIds.Contains(target.Id)
                    return True
        return False


class IsInRange(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLFactory$$IsInRange(a, b, range)` ->
    `IdunBattle.Entities.Triggers.IsInRangeAbilityTrigger$$ShouldTrigger` -- MIRROR du decompile,
    et il n'est NI `dist(mainTile, mainTile)` NI un `any` sur les entites :

        range = <formule @+0x28>.Calculate(entities);             // slot 1 d'IAmountFormula
        A     = <selecteur @+0x18>.SelectTiles(entities);         // slot 10 -> EMPREINTES
        B     = <selecteur @+0x20>.SelectTiles(entities);         // slot 10 -> EMPREINTES
        return query@+0x10.GetMinDistance(A, B) <= range;         // slot 0x6f d'IBattleQuery

    TROIS lectures :

    * **EMPREINTES** (#433-r3-r1). `IdunBattle.DSL.TargetsSelector$$SelectTiles` materialise
      `EntityExtensions$$IterateTiles` de CHAQUE entite selectionnee dans UNE liste plate -- donc
      toutes les tuiles de tous les pieds. `IdunBattle.Core.Services.BattleQuery$$GetMinDistance`
      prend ensuite le MIN sur toutes les paires de cette liste. Le port lisait la seule MAIN TILE.
    * **LE VIDE REND VRAI.** `GetMinDistance` seed a `int.MaxValue` et, si aucune paire n'a ete
      evaluee, rend **-1** (`if (best == int.MaxValue) best = -1`) -- donc `-1 <= range` = VRAI.
      Le port rendait FAUX (un `any` sur un produit vide). C'est le SEUL des trois ecarts qui
      change le verdict sur une unite MONO-tuile : il suffit qu'un selecteur ne rende rien.
      Mirror dans `services/movement_query.py::get_min_distance`, qui NOMME l'ecart au sentinel
      d'`IdunBattle.Core.Services.MovementQuery$$GetDistance` (`int.MaxValue`).
    * la comparaison est `<=` sur le MINIMUM, ce qui EST un `exists` sur les paires -- le `any`
      du port etait juste sur ce point-la (mais applique aux mauvaises tuiles).

    Ordre des args factory : `a@+0x18`, `b@+0x20`, `range@+0x28`, `query@+0x10` (lu au `.ctor`)."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger, rng: AbilityTrigger):
        self.a, self.b, self.rng = a, b, rng

    def should_trigger(self, ctx):
        from ..services.movement_query import get_min_distance   # lazy : garde anti-circulaire
        r = self.rng.evaluate(ctx)
        ta = [f for u in _units_of(self.a, ctx) for f in _feet(u)]   # `SelectTiles` = liste PLATE
        tb = [f for u in _units_of(self.b, ctx) for f in _feet(u)]
        return get_min_distance(ta, tb) <= r


class IsSurrounding(IsInRange):
    """`IdunBattleLogic.Entities.DSLFactory$$IsSurrounding(a, b, radius)` -- et c'est **LA MEME
    CLASSE NATIVE QUE `IsInRange`**, pas un noeud frere.

    MESURE (#433-r3-r1) : `IdunBattleLogic.Entities.DSLTriggers$$IsSurrounding` et
    `IdunBattleLogic.Entities.DSLTriggers$$IsInRange` allouent le MEME pointeur de classe
    (`DAT_1833a9d10` sur le build `rnca9r7q6c`) et appellent le MEME `.ctor` avec les arguments
    dans le MEME ordre (`query`, `selector1`, `selector2`, `range`). Les deux factories ne
    different que par leur nom : il n'existe pas de `IsSurroundingAbilityTrigger` dans le binaire.
    L'ancienne docstring disait « semantique DEDUITE de l'usage + i2 » -- la deduction tombait
    juste, la voila LUE.

    ⚠ Ghidra mislabel le `.ctor` partage en `IdunBattle.Entities.Triggers.IsUnitOnTileEffectTrigger$$.ctor`
    (corps gshared dedupliqué) : c'est le pointeur de classe qui tranche, jamais le nom.

    Le port herite donc de `IsInRange` -- aucun corps propre, aucune chance de divergence entre les
    deux. Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour`,
    qui gate son move par `Not(IsSurrounding(caster@0x148, target@0x178, radius=1))`."""
    def __init__(self, a: AbilityTrigger, b: AbilityTrigger, radius: AbilityTrigger):
        super().__init__(a, b, radius)
        self.radius = radius            # alias historique du 3e argument (meme objet que `rng`)


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
