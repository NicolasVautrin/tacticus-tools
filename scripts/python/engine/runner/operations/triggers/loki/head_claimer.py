"""`IdunBattleLogic.Entities.Abilities.Active.Loki.HeadClaimerAbility` (`TriggeredAbilityType
0x407 = 1031`, passiveAbility `HeadClaimer` de `blackHaarken` << Haarken Worldclaimer >>) --
l'ACCUMULATION des DEUX compteurs de tetes (#947).

⚠ Le namespace `...Abilities.Active...` MENT : la classe appelle
`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$get_AbilityStateReference` et declare
`CreateTrigger` -- c'est une `passiveAbilities` du kit, comme `InescapableDeathAbility` /
`FirstAmongTraitorsAbility` avant elle.

Les EFFETS sont portes par `entities/effects/loki/head_claimer.py` (`1028 HeadClaimer_ExtraDmg`,
`1029 HeadClaimer_ExtraHit`) ; ce module ne porte que le compteur, exactement comme
`terrifying_crescendo.py` / `fuelled_by_fury.py` le font pour leurs effets a `EffectLevel`.

i2 : << For each enemy unit that Haarken has defeated, his attacks deal +{[extraDmg]} Damage for the
rest of the battle. For each enemy Character that he has defeated, his attacks also score
+{[extraHit]} hit for the rest of the battle. >>

===================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
===================================================================================================

Slots `AbilityEntities` / `DSLSelectors` : `+0x30 Owner · +0x60 Target`.

## `...HeadClaimerAbility$$CreateTrigger` -- une DISJONCTION, puis TROIS conjoints

    branche1 = OnPreDeath2( triggerOnOverkill: true, triggerOnSteppable: false )
    branche2 = On( 0x34 = EventTriggerType.UnitFled, ownerNeedsToBeAlive: true )
    trigger  = (branche1 | branche2)
               & get_OwnerIsActor
               & NOT AreFriends( Owner@+0x30, Target@+0x60, comparisonType: 0, anyEntity: false )
               & NOT TriggeringAbilityIs( AbilityOrEffect(TriggeredAbilityType.ItsGonnaBlow = 1080) )

`IdunBattleLogic.Entities.DSLTriggers$$OnPreDeath2(a, b)` = `OnDeathEvent(2, a, b)`, et le corps
d'`OnDeathEvent` a ete relu :

    overkillGate  = a ? <DSLTriggers+0x70 = Yes> : NOT TargetIsOverkilled()
    steppableGate = b ? <DSLTriggers+0x70 = Yes> : NOT HasTrait(Target@+0x60, 0x1b = Steppable)
    return On(triggerType) & <Yes> & overkillGate & steppableGate

Avec `a = true, b = false` -> `On(2 = PreUnitDeath_2) & NOT TargetHasTrait(Steppable)` : le
compteur monte MEME sur un overkill, et JAMAIS sur une entite `Steppable`.

⚠ Les DEUX litteraux ont ete decodes aux OCTETS (`mov dl, 1` / `xor r8d, r8d` juste avant le
`call`), pas lus dans le pseudo-C -- et le `0x438` du `TriggeringAbilityIs` est qualifie par
l'ADRESSE REELLE de son `AbilityOrEffect$$op_Implicit` (`+0x130`, `E8 rel32` -> l'overload qui pose
`set_TriggeredAbility`, PAS `set_ActiveAbility` ni `set_Effect`). C'est le MEME gate, avec le MEME
id, que `BarbedOvipositorAbility$$CreateTrigger` (cf. `loki/barbed_ovipositor.py`).

## `...HeadClaimerAbility$$CreateBehaviour`

    b1 = AddEffectOrIncreaseLevel( 0x404 = 1028, AbilityStateReference,
                                   source = Owner@+0x30, selector = Owner@+0x30,
                                   amount = <DSLFormulas+0x20 = Const(1)>, max = NULL )
    b2 = AddEffectOrIncreaseLevel( 0x405 = 1029, AbilityStateReference,
                                   source = Owner@+0x30, selector = Owner@+0x30,
                                   amount = <DSLFormulas+0x20 = Const(1)>, max = NULL )
    return AbilityBehaviour.op_BitwiseAnd( b1, If( IsHero(Target@+0x60), b2 ) )

  * `<DSLFormulas+0x20>` est le MEME champ que `TerrifyingCrescendoAbility$$CreateBehaviour` passe
    en `level` (relu cote a cote) = le noeud constant **1** -> increment de +1 par declenchement ;
  * `max = NULL` -> **AUCUN cap** (contraste TerrifyingCrescendo, qui passe
    `Direct(GetNumberConstant(0x62 = buffMaxLevel)) = 6`). C'est le << for the rest of the battle >>
    de l'i2, sans borne ;
  * `IdunBattleLogic.Entities.DSLTriggers$$IsHero(unit)` a pour corps ENTIER
    `HasTraitAbilityTrigger(unit, 0x10, 0)` = `HasTrait(unit, UnitTrait.Hero = 16)`. C'est le
    << Character >> de l'i2 ;
  * la face DEGAT (1028) est INCONDITIONNELLE, seule la face COUPS (1029) passe par le `If`.

## Frontiere DSL/imperatif (#149)

`AddEffectOrIncreaseLevel` est une FACTORY native (elle alloue `Foreach(selector, If(HasEffect,
IncreaseEffectLevel, AddEffect))`) -> portee comme un ARBRE (`add_effect_or_increase_level`), pas
comme un helper imperatif fusionne. Les predicats du `CreateTrigger` sont collapses dans `matches`
(doctrine des triggers). Le `If(IsHero(Target), ...)` du `CreateBehaviour` reste, lui, un NOEUD :
il appartient au behaviour, pas au trigger.

===================================================================================================
RESIDUS EXPLICITES
===================================================================================================

* **`On(0x34 = UnitFled)` : VECTEUR AJOUTE, la branche est VIVANTE (#947-r1 FERME par #981).**
  Elle a longtemps ete portee comme une classe de registre INERTE : le port n'emettait aucun
  `unit_fled_triggers`. `IdunBattle.Operations.FleeOperation$$Execute` publie en fait DEUX events
  apres le `UnitFlag 9` -- `On(0x34 = UnitFled)` puis `On(0x36 = UnitDefeated)` -- tous deux avec
  `actor = caster = triggeringUnit` et `target = la fuyarde` (asymetrie LUE : `On(0x33 =
  PreUnitFled)`, lui, passe la fuyarde TROIS FOIS). Le `triggeringUnit` vient de
  `Caster@<DSLSelectors+0x48>`, que `BattleFatigueAbility$$CreateBehaviour` passe en 2e argument de
  `IdunBattleLogic.Entities.DSLBehaviors$$Flee` -- c'est-a-dire le TUEUR de l'allie dont la mort
  declenche la fatigue. D'ou le scenario complet : Haarken abat un membre d'escouade, un ennemi
  adjacent porteur de `BattleFatigue` fuit, et la tete est creditee a Haarken par `get_OwnerIsActor`.
  Garde d'execution (pas d'inspection de source) :
  `tests/engine/runner/test_981_vecteurs_de_fuite_offline.py`.
* **`NOT TriggeringAbilityIs(TriggeredAbilityType.ItsGonnaBlow = 1080)` : gate INERTE**, meme
  constat que `barbed_ovipositor.py` -- aucun poseur d'`ItsGonnaBlow` n'est porte (passif npc de la
  caisse de munitions), et le canal `triggering_ability` du vecteur `On(2)` reste vide. Le port
  l'omet plutot que de le simuler avec un champ qui ne porte pas la meme information.
* **`ownerNeedsToBeAlive`** : `On(0x34)` le passe a `true` (donc `& <DSLTriggers+0x20>`) tandis que
  le `On(2)` d'`OnDeathEvent` passe par `<DSLTriggers+0x70 = Yes>`. Cote port, le dispatch
  n'interroge que les porteurs presents dans l'etat ; la distinction n'a pas de substrat separe.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import add_effect_or_increase_level
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggers import HasTrait
from ..base import TriggeredAbility, TriggerEvent

HEAD_CLAIMER_ABILITY = "HeadClaimer"
#: `EffectType 0x404 = 1028` / `0x405 = 1029` -- les DEUX effets que `CreateBehaviour` empile.
EXTRA_DMG_EFFECT = int(EffectType.HeadClaimer_ExtraDmg)
EXTRA_DMG_EFFECT_NAME = "HeadClaimer_ExtraDmg"
EXTRA_HIT_EFFECT = int(EffectType.HeadClaimer_ExtraHit)
EXTRA_HIT_EFFECT_NAME = "HeadClaimer_ExtraHit"
#: `OnPreDeath2(...)` -> `OnDeathEvent(2, ...)`, et `On(0x34)`.
_ON_PRE_UNIT_DEATH_2 = int(EventTriggerType.PreUnitDeath_2)      # 2
_ON_UNIT_FLED = int(EventTriggerType.UnitFled)                   # 0x34 = 52
#: `IdunBattleLogic.Entities.DSLTriggers$$IsHero(unit)` = `HasTrait(unit, UnitTrait.Hero = 0x10)` --
#: corps ENTIER de la fonction native, relu. Noeud DSL du foyer `entities/triggers.py`, jamais une
#: recopie du nom de trait au site.
_IS_HERO_TARGET = HasTrait(Target(), int(UnitTrait.Hero))
#: `steppableGate` de `OnDeathEvent(2, a, b=false)` = `NOT HasTrait(Target@+0x60, 0x1b)`.
_IS_STEPPABLE_TARGET = HasTrait(Target(), int(UnitTrait.Steppable))


def head_claimer_extra_dmg_tree():
    """`AddEffectOrIncreaseLevel(0x404, AbilityStateReference, Owner@+0x30, Owner@+0x30,
    amount = Const(1), max = NULL)` -- la face DEGAT, INCONDITIONNELLE dans le `CreateBehaviour`.
    `Caster()` = `Owner@+0x30` (une triggered a `Owner == Caster`). `max_level=None` = le `max`
    NULL natif : aucun clamp dans `IncreaseEffectLevelOperation$$Execute`."""
    return add_effect_or_increase_level(
        EXTRA_DMG_EFFECT, EXTRA_DMG_EFFECT_NAME, Caster(),
        amount=Const(1), max_level=None)


def head_claimer_extra_hit_tree():
    """`AddEffectOrIncreaseLevel(0x405, ...)` -- la face COUPS, jouee SEULEMENT sous
    `If(IsHero(Target@+0x60), ...)`. Meme `amount`/`max` que la face DEGAT."""
    return add_effect_or_increase_level(
        EXTRA_HIT_EFFECT, EXTRA_HIT_EFFECT_NAME, Caster(),
        amount=Const(1), max_level=None)


class _HeadClaimerAccumulateBase(TriggeredAbility):
    """Socle commun aux DEUX branches de la disjonction `op_BitwiseOr` de
    `...HeadClaimerAbility$$CreateTrigger` (portee comme deux entrees de registre, comme
    TerrifyingCrescendo overkill/suppress) : MEMES conjoints, MEME behaviour."""

    def _victim(self, ev: TriggerEvent):
        return ev.dying_id if ev.dying_id is not None else ev.target_id

    def _common_gates(self, state: State, ev: TriggerEvent) -> bool:
        """`get_OwnerIsActor & NOT AreFriends(Owner@+0x30, Target@+0x60, 0, false)`.

        `get_OwnerIsActor` : le porteur est l'ACTEUR de l'evenement = le TUEUR (les vecteurs de mort
        construisent l'event avec `actor = killer`, `target = dying`).

        `NOT AreFriends` (et NON `AreEnemies`, qui est un AUTRE noeud natif) : le conjoint tombe des
        que les deux entites partagent l'equipe. Equipe INCONNUE des deux cotes -> on REFUSE
        (degradation RESTRICTIVE : sans substrat, on ne compte pas une tete qu'on ne peut pas
        qualifier)."""
        if ev.actor_id != self.owner_id:                 # get_OwnerIsActor
            return False
        victim = self._victim(ev)
        if victim is None or victim == self.owner_id:
            return False
        owner_e, victim_e = state.get_entity(self.owner_id), state.get_entity(victim)
        if owner_e is None or victim_e is None:
            return False
        ooc = owner_e.get_component(OwnerComponent)
        voc = victim_e.get_component(OwnerComponent)
        if ooc is None or voc is None or ooc.team is None or voc.team is None:
            return False
        if ooc.team == voc.team:                         # NOT AreFriends(Owner, Target)
            return False
        # `NOT TriggeringAbilityIs(TriggeredAbilityType.ItsGonnaBlow = 1080)` : gate INERTE offline
        # (aucun poseur porte, canal non threade sur ce vecteur) -- cf. residus de l'en-tete.
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`op_BitwiseAnd( AddEffectOrIncreaseLevel(1028), If(IsHero(Target), AddEffectOrIncrease
        Level(1029)) )` -- la face DEGAT toujours, la face COUPS seulement contre un `Hero`."""
        if state.effects is None:
            return None
        victim = self._victim(ev)
        entities = entities_from_state(state, self.owner_id, victim)
        ectx = ExecutionContext(state=state, rng=state.rng)
        head_claimer_extra_dmg_tree().execute(entities, ectx)
        hero = bool(_IS_HERO_TARGET.should_trigger(entities))     # If(IsHero(Target@+0x60), ...)
        if hero:
            head_claimer_extra_hit_tree().execute(entities, ectx)
        levels: dict = {}
        for n, p in ectx.emitted:
            if n in ("IncreaseEffectLevel", "AddEffect"):
                levels[p.get("effect_type", p.get("name"))] = p.get("level")
        return {"ability": HEAD_CLAIMER_ABILITY, "unit": int(self.owner_id),
                "victim": victim, "victim_is_hero": hero, "levels": levels,
                "on_event": int(ev.event_id)}


class HeadClaimerOnDeathAbility(_HeadClaimerAccumulateBase):
    """Branche 1 : `OnPreDeath2(triggerOnOverkill: true, triggerOnSteppable: false)` =
    `On(2 = PreUnitDeath_2) & NOT TargetHasTrait(Steppable)`. Haarken TUE un non-ami.

    Le gate d'OVERKILL est DESARME (`triggerOnOverkill = true` -> `<DSLTriggers+0x70 = Yes>`) : la
    tete compte meme quand la victime est overkillee -- exactement l'inverse du role de ce parametre
    chez `TerrifyingCrescendo`, dont la branche 1 EXIGE l'overkill via un noeud SEPARE."""
    event_id = _ON_PRE_UNIT_DEATH_2

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if not self._common_gates(state, ev):
            return False
        # `steppableGate` : `NOT HasTrait(Target@+0x60, 0x1b = Steppable)`. Noeud DSL du foyer
        # (substrat `entity_trait_names`, repli gameconfig #226) -- un CADAVRE charge sans
        # `StatsComponent` y reste VOYANT, ce qu'une lecture brute de `ctx.traits` ne serait pas.
        entities = entities_from_state(state, self.owner_id, self._victim(ev))
        return not _IS_STEPPABLE_TARGET.should_trigger(entities)


class HeadClaimerOnFledAbility(_HeadClaimerAccumulateBase):
    """Branche 2 : `On(0x34 = UnitFled, ownerNeedsToBeAlive: true)`. Un non-ami FUIT le champ de
    bataille -- le natif compte cela comme une tete (l'i2 dit << defeated >>, pas << killed >>).

    VIVANTE depuis #981 : `FleeOperation.execute` emet le vecteur avec `actor = triggeringUnit`
    (le `Caster@<DSLSelectors+0x48>` du call-site natif), ce qui est exactement ce que
    `get_OwnerIsActor` reconnait. Cf. le bloc RESIDUS de l'en-tete pour la chaine complete."""
    event_id = _ON_UNIT_FLED

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # AUCUN gate `Steppable` sur cette branche : il appartient a `OnDeathEvent`, pas a `On(...)`.
        return self._common_gates(state, ev)
