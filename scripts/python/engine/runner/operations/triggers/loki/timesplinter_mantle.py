"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimesplinterMantleAbility` -- le passif
`TimesplinterMantle` (`TriggeredAbilityType` 0x5fe = 1534) de `necroChronomancer` << Thothmek >>
(Necrons, HERO), et le TRIGGER DE RETRAIT de l'effet qu'il pose.

C'est le DERNIER item manquant du kit de Thothmek (son active `Chronometron` 1226 est portee).

⚠ PAS d'i2 : `data/i2_en.json` est un dump ANTERIEUR a l'arrivee de cette unite (`Timesplinter`,
`Chronometron` et `Thothmek` y rendent tous `-1`). Il n'y a donc AUCUN texte de tooltip pour ce
passif -- le decompile est la seule source, ce qui est de toute facon la doctrine.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`). Les surcharges sont tranchees par l'ADRESSE du `call`
(`probe_951_call_targets.py`), jamais a l'oeil.
================================================================================================

## 1. `...TimesplinterMantleAbility$$CreateTrigger`

    DSLTriggers.On(EventTriggerType.TurnStart_EffectActivation = 0x12, ownerNeedsToBeAlive: true)

**UN SEUL noeud** : le corps est un `jmp` vers `On`, il n'y a AUCUN `op_BitwiseAnd`. En
particulier PAS d'`IsTurnOf(Owner)` -- contraste `RelentlessMarchAbility$$CreateTrigger`, l'autre
passif Necron turn-start, qui lui porte `& <DSLTriggers+0x28> = IsTurnOf(Owner)`. Recopier le
voisin de forme aurait restreint la pose au seul tour du porteur.

CONSEQUENCE OBSERVABLE : l'effet est (re)pose au debut de CHAQUE tour, les deux camps compris.
Combine au retrait `On(TurnEnd)` ci-dessous, cela fait une reduction plate REARMEE a chaque tour et
consommee par la premiere attaque recue.

`0x12` = `TurnStart_EffectActivation` (19 = `TurnStart_Other`, 0x16 = `TurnStart_Actions` : les
trois sont des events DISTINCTS de la sequence `StartTurnOperation$$Execute` 0x12/0x13/0x14/0x15/
0x16). Le vecteur porte est `dispatch/turn.py::tile_tick_triggers`, qui emet 0x12 puis 0x14 -- il
publie `actor = target = -1` et `player_id = None`, ce qui suffit puisque le trigger natif ne lit
NI acteur NI joueur.

## 2. `...TimesplinterMantleAbility$$CreateBehaviour(abilityState, triggerType)`

    targets = DSLSelectors.AdjacentUnits(Owner@DSLSelectors+0x30, unique: 1, selectionType: 3)
              |> DSLSelectors.Friends(of: Owner@+0x30, _, selectionType: 3)
              |> DSLSelectors.MechanicalUnits(_, selectionType: 3)
              |> DSLSelectors.NonSteppableUnits(_, selectionType: 3)
              op_Addition  Owner@+0x30

    return DSLBehaviors.Foreach(
        targets,
        DSLBehaviors.AddEffect( effectType   = 0x60f = EffectType.TimesplinterMantle_DamageReduction,
                                abilityState = BaseTriggeredAbility.get_AbilityStateReference(this),
                                source       = Owner@+0x30,
                                targets      = ActiveTarget@+0x68,
                                options      = Nullable<AddEffectBehaviourOptions> VIDE ) )

Les deux methodes `$$GetTargets` et `$$GetAddOrActivateEffect` portent EXACTEMENT ces deux
morceaux : ce sont les helpers C# que le compilateur a INLINES dans `CreateBehaviour` (aucune xref
CODE vers elles, seulement les entrees de la table de methodes).

  * `NonSteppableUnits(entities, sel)` = `op_BitwiseAnd(entities, UnitsWithoutTrait(entities,
    0x1b = UnitTrait.Steppable, sel))` -- factory mirroree telle quelle
    (`entities/selectors/units.py::non_steppable_units`), pas une classe inventee ;
  * la surcharge d'`AddEffect` retenue est celle a 5 parametres `(effectType, abilityState, source,
    targets, options: Nullable<AddEffectBehaviourOptions>)` -- donc la source est EXPLICITE
    (`Owner@+0x30`), contrairement a la surcharge 4-args qui retombe sur la cible. Les 32 octets du
    `Nullable` sont mis a ZERO avant l'appel => AUCUNE duree ; et `1551` est absent de
    `StaticBattleRules.Effect$$DefaultAmountOfRounds` => l'effet est PERMANENT jusqu'a son trigger.
  * `ActiveTarget@+0x68` = l'element courant du `Foreach` (le natif ecrit `entities[slot 4] = elem`
    avant d'executer un corps STATIQUE, cf. `entities/behaviours.py::Foreach`).

⚠ La carte des slots `DSLSelectors` de ce build, ETABLIE et non interpolee : les getters NOMMES de
`DSLTriggers` sont chacun un `AreEqual` de deux slots -- `get_OwnerIsActor = (+0x30, +0x40)`,
`get_OwnerIsCaster = (+0x30, +0x48)`, `get_OwnerIsTarget = (+0x30, +0x60)` -- d'ou
`Owner 0x30 · Actor 0x40 · Caster 0x48 · CasterTile 0x50 · Target 0x60 · ActiveTarget 0x68 ·
TargetTiles 0x78`.

## 3. L'EFFET 1551 et son RETRAIT

`...TimesplinterMantle_DamageReductionEffect$$.ctor` = `DamageModifierAbilityEffect..ctor(this,
0x5fe, 0)` (l'`AbilityOrEffect` est le `TriggeredAbilityType` 1534, pas un `EffectType`).

    ...$$CreateDamageDefenseModifier  = EffectBonus.ForSubtraction(
            get_OwnerIsTarget & IsUnit(Caster@+0x48),
            ConfigVar(0x12 = dmgReduction, GetAbilityState(effect), config),
            AbilityOrEffect(TriggeredAbilityType 1534) )

    ...$$CreateRemoveEffectTrigger    = ( BaseEffect.On(9 = Attack)
                                          & get_OwnerIsTarget
                                          & IsUnit(Caster@+0x48) )
                                        op_BitwiseOr  BaseEffect.On(0x17 = TurnEnd)

La face DEGAT vit dans `entities/effects/loki/damage_reduction.py::
TimesplinterMantleDamageReductionEffect` (bac `flat_reductions`, jumeau de Nightshroud). Le RETRAIT
est ici, et il faut DEUX classes cote port parce que le registre est indexe par `event_id` alors
que le natif exprime une DISJONCTION (meme patron que `HeavyWarpFlamer` / `HaywireMine`).

Sans ces deux entrees, la reduction serait PERMANENTE la ou le natif donne une charge a usage
unique, rearmee chaque tour : degradation silencieuse (aucune erreur, aucun test rouge).

## 4. FORME DU PORT (doctrine #149)

`CreateBehaviour` -> ARBRE DSL (`Foreach` + feuille `AddEffect`), construit de noeuds EXISTANTS
(`AdjacentUnits`, `Friends`, `MechanicalUnits`, `non_steppable_units`, `Union`, `ActiveTarget`) --
aucun ciblage recable a la main. `CreateTrigger` et les deux `CreateRemoveEffectTrigger` sont
COLLAPSES imperativement dans `matches` (idiome de tous les trigger-ports).

## 5. RESIDUS NOMMES

  * `IsUnit(Caster@+0x48)` de la face DEGAT : TAUTOLOGIQUE sur le canal
    `create_effect_damage_malus_for_defense` du port (seul le pipeline d'attaque le parcourt) --
    NON CONFRONTE. Il EST porte, lui, sur le trigger de retrait ci-dessous, ou l'acteur est connu.
  * `unitSelectionType = 3` (`OnlyAliveAndTargetable`) : le port l'honore par `selection_type=3` sur
    `AdjacentUnits`/`Friends`, mais `MechanicalUnits` cote port ignore ce parametre (foyer partage,
    hors tranche).
  * `unique = 1` d'`AdjacentUnits` : sans effet observable (une unite = une position).
  * `IdunBattle.AI.Playbook.Loki.TimesplinterMantlePlaybook` (face DECISION, 3 corps propres) : hors
    perimetre. La face NON-OWNER, elle, est DEJA portee
    (`engine/playbook/non_owner.py::TimesplinterMantleNonOwnerPlaybook`).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import TargetsSelector
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Foreach
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import ActiveTarget
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import (
    AdjacentUnits, Friends, MechanicalUnits, Union, non_steppable_units
)
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType
from ....components import UnitComponent
from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from ..base import EffectTrigger, TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig de la passiveAbility porteuse.
TIMESPLINTER_MANTLE = "TimesplinterMantle"
#: `AddEffect(effectType = 0x60f, ...)` -- un `EffectType`, PAS un `TriggeredAbilityType` (l'ordinal
#: 1551 vaut `RedRampage` dans l'autre enum : la qualification n'est pas decorative).
MANTLE_EFFECT = int(EffectType.TimesplinterMantle_DamageReduction)     # 0x60f = 1551
MANTLE_EFFECT_NAME = EffectType(MANTLE_EFFECT).name
#: `selectionType: 3` des quatre selecteurs du `CreateBehaviour`.
_SEL_ALIVE_TARGETABLE = int(UnitSelectionType.OnlyAliveAndTargetable)  # 3


def timesplinter_mantle_targets() -> TargetsSelector:
    """`...TimesplinterMantleAbility$$GetTargets` -- MIRROR 1:1 :

        NonSteppableUnits( MechanicalUnits( Friends( of = Owner@0x30,
                                                     AdjacentUnits(Owner@0x30, unique: 1, sel: 3),
                                                     sel: 3 ),
                                            sel: 3 ),
                           sel: 3 )
          op_Addition  Owner@0x30

    `Caster()` = le slot `DSLSelectors+0x30` (Owner) : pour un triggered,
    `entities_from_state(state, owner_id, ...)` pose `caster == owner` (meme convention que
    `relentless_march.py`). `AdjacentUnits` exclut deja l'origine (le natif fait
    `Units(AdjacentTiles(origin)) - origin`) et ne filtre AUCUNE equipe ; le camp vient du `Friends`
    au-dessus, dont le REFERENT est l'Owner (2e argument natif), pas une constante.

    L'`op_Addition` remet l'Owner DANS l'ensemble : Thothmek se couvre LUI-MEME, et il n'a besoin
    d'etre ni Mechanical ni adjacent a lui-meme pour cela (il l'est de fait -- `LivingMetal` -- mais
    ce n'est pas ce qui l'y met)."""
    owner = Caster()
    chain = AdjacentUnits(owner, selection_type=_SEL_ALIVE_TARGETABLE)
    chain = Friends(chain, owner, selection_type=_SEL_ALIVE_TARGETABLE)
    chain = MechanicalUnits(chain, selection_type=_SEL_ALIVE_TARGETABLE)
    chain = non_steppable_units(chain, _SEL_ALIVE_TARGETABLE)
    return Union(chain, owner)


def timesplinter_mantle_behaviour_tree() -> Foreach:
    """`...TimesplinterMantleAbility$$CreateBehaviour` -- MIRROR 1:1 :

        Foreach( GetTargets(), GetAddOrActivateEffect() )
        ou GetAddOrActivateEffect() = AddEffect(0x60f, AbilityStateReference, source = Owner@0x30,
                                                targets = ActiveTarget@0x68, options VIDES)

    `duration_rounds=None` = les options natives ZEROEES -> pas d'override -> `DefaultAmountOfRounds
    (1551)` est un Nullable VIDE -> `remaining = 0` = PERMANENT, retire par les DEUX effect-triggers
    de ce module.
    `scale_from_source=True` = l'`abilityState` que le natif BAKE dans l'entite-effet
    (`BaseEffect$$GetAbilityState`), et que `CreateDamageDefenseModifier` relit pour indexer son
    `ConfigVar(dmgReduction)` : la magnitude suit le niveau/multiplier de THOTHMEK, pas ceux de
    l'allie couvert.
    `source_ref` reste au DEFAUT (= `entities.caster`) : le contexte est construit par
    `entities_from_state(state, owner_id)`, donc `caster == owner == Owner@0x30`, exactement le
    3e argument natif. Meme collapse que `relentless_march.py`."""
    return Foreach(timesplinter_mantle_targets(),
                   AddEffect(MANTLE_EFFECT, MANTLE_EFFECT_NAME, ActiveTarget(),
                             duration_rounds=None, scale_from_source=True))


class TimesplinterMantleAbility(TriggeredAbility):
    """`TimesplinterMantleAbility` (1534, passif de `necroChronomancer` << Thothmek >>).

    Au debut de CHAQUE tour (les deux camps) : pose 1551 sur Thothmek ET sur ses allies MECANIQUES
    non-`Steppable` adjacents. Cf. l'en-tete du module."""
    event_id = int(EventTriggerType.TurnStart_EffectActivation)   # On(0x12 = 18)
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.TimesplinterMantle)     # 0x5fe = 1534

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` = `On(0x12, ownerNeedsToBeAlive: true)` et RIEN d'autre. Le volet
        << owner vivant >> est deja le gate `CanGetAbilityTrigger` du dispatch, il ne reste donc
        AUCUN predicat a evaluer ici. En particulier PAS de test sur `ev.player_id` : le natif
        n'a pas d'`IsTurnOf(Owner)` (contraste `RelentlessMarchAbility`)."""
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `On(TurnStart_EffectActivation)` ne porte aucune cible : l'arbre est entierement
        # caster-ancre (`Owner@0x30` pour l'origine de l'adjacence, le referent du `Friends` et la
        # source de l'`AddEffect`).
        entities = entities_from_state(state, self.owner_id, None)
        timesplinter_mantle_behaviour_tree().execute(entities, ectx)
        placed = [p for (n, p) in ectx.emitted if n == "AddEffect"]
        if not placed:
            return None
        return {"passive": TIMESPLINTER_MANTLE, "owner": int(self.owner_id),
                "effect": MANTLE_EFFECT,
                "covered": [p.get("target") for p in placed],
                "newly_placed": [p.get("target") for p in placed if p.get("placed")]}


class _TimesplinterMantleDamageReductionRemove(EffectTrigger):
    """Base des DEUX disjoints de `...TimesplinterMantle_DamageReductionEffect$$
    CreateRemoveEffectTrigger`, dont le behaviour est le meme :
    `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(Effect@0x38)` = CETTE instance.

    COLLAPSE ASSUME, identique a `ChronometronExtraDamageRemove` : le natif retire L'INSTANCE, le
    port retire tous les stacks non consommes du type sur le porteur (`RemoveEffect(effect_type,
    Caster())`, la seule forme portee). Les deux coincident -- le gate << deja present >>
    d'`AddEffectOperation` garantit au plus UNE instance par unite."""
    effect_type = MANTLE_EFFECT

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(MANTLE_EFFECT, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": MANTLE_EFFECT_NAME, "owner": int(self.owner_id), "removed": removed,
                "event": int(self.event_id)}


class TimesplinterMantleDamageReductionRemoveOnAttack(_TimesplinterMantleDamageReductionRemove):
    """PREMIER disjoint : `On(9 = Attack) & get_OwnerIsTarget & IsUnit(Caster@+0x48)`.

    `On(9)` est l'event GENERIQUE emis par `IdunBattle.Operations.FinishAttackOperation$$Execute` a
    la FIN de TOUTE attaque (normale ET ability) : la reduction s'applique donc encore au coup qui
    la consomme -- le degat est resolu pendant l'attaque, `On(9)` ne fire qu'a sa cloture. Meme
    lecture que `Chronometron_ExtraDamage` et `HeraldOfTheApocalypse`.

    ⚠ SANS l'`AreFriends(caster, EffectSource)` de 1550 : n'importe quelle unite qui attaque le
    porteur consomme la charge."""
    event_id = int(EventTriggerType.Attack)                       # 9

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False                                          # get_OwnerIsTarget
        att = state.get_entity(ev.actor_id) if ev.actor_id is not None else None
        # `IsUnit(Caster@+0x48)` -- l'attaquant est une UNITE (et non une tuile / l'environnement).
        return att is not None and att.get_component(UnitComponent) is not None


class TimesplinterMantleDamageReductionRemoveOnTurnEnd(_TimesplinterMantleDamageReductionRemove):
    """SECOND disjoint : `BaseEffect.On(0x17 = TurnEnd)` -- SEUL, sans aucun predicat (ni owner, ni
    camp). L'effet part donc au premier `TurnEnd` qui suit sa pose, quel que soit le camp dont le
    tour se termine, exactement comme `UntilOfEndTurnEffect`.

    C'est ce disjoint qui, combine au `On(TurnStart_EffectActivation)` de l'ability, fait de 1551
    une couverture REARMEE A CHAQUE TOUR plutot qu'un buff permanent."""
    event_id = int(EventTriggerType.TurnEnd)                      # 0x17 = 23

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True
