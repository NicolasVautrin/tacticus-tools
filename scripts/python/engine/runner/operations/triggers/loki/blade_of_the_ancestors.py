"""`BladeOfTheAncestors` -- relique `R_Crit_BladeOfTheAncestors`, `TriggeredAbilityType` 0x5d3 =
1491, porteur `votanUthar` << Uthar >> (HERO Leagues of Votann, HORS du pool rank 17). #1001.

i2 : << Uthar gains +extraCritChance% Crit Chance and deals +extraCritDmg Crit Damage each time a
friendly character dies or kills an enemy unit. Once Uthar crits, this bonus resets. >>

================================================================================================
DEUX classes natives pour UNE cle de registre (patron `DaemonfleshPlate` / `LetTheGalaxyBurn`)
================================================================================================
Les deux vivent sous `IdunBattleLogic.Entities.Abilities.**Active**.Loki` -- le NAMESPACE MENT
(l'ability est un `TriggeredAbilityType`, sa base est `IdunBattle.Entities.Abilities.
BaseTriggeredAbility`, LUE dans `frida/classes.tsv`). Meme piege que `ActOfFaith`, meme namespace.

## `IdunBattleLogic.Entities.Abilities.Active.Loki.BladeOfTheAncestorsAbility$$CreateTrigger`

    ( On(0 = UnitDeath, ownerNeedsToBeAlive = 1)
      & AreFriends( Targets@DSLSelectors+0x60, Owner@DSLSelectors+0x30, 0, 0 )
      & HasTrait(   Targets@+0x60, 0x10 = UnitTrait.Hero ) )
  | ( On(0 = UnitDeath, ownerNeedsToBeAlive = 1)
      & AreFriends( Actor@DSLSelectors+0x40, Owner@+0x30, 0, 0 )
      & HasTrait(   Actor@+0x40, 0x10 = Hero )
      & IsNormalUnit( Targets@+0x60 ) )

Branche 1 = << a friendly character **dies** >> (le MOURANT est un Hero allie) ; branche 2 =
<< a friendly character **kills an enemy unit** >> (le TUEUR est un Hero allie, et la victime est
une unite NORMALE). `+0x30 = Owner`, `+0x40 = Actor`, `+0x60 = Targets` -- identification LUE
(`DSLTriggers$$get_OwnerIsActor` = `AreEqual(+0x30, +0x40)`), pas deduite.

## `...BladeOfTheAncestorsAbility$$CreateBehaviour(abilityState, triggerType)`

    if (triggerType == 0x20 = Custom) return Nothing();
    return AddEffect( 0x5d1 = 1489 BladeOfTheAncestors_Effect,
                      BaseTriggeredAbility$$get_AbilityStateReference(this),
                      targets = Owner@+0x30, turns = null )

⚠ La surcharge appelee est celle a QUATRE parametres (`effectType, abilityState, targets, turns`)
-- il n'y a AUCUN selecteur `source`. Le natif retombe alors sur << la source EST la cible >>
(`AddEffectBehaviour$$Execute` : `lVar14 = <cible courante>; if (<selecteur source> != 0) lVar14 =
<son resultat>;`), ce que le port ecrit `source_from_target=True`. Ici cible = `Owner` = caster,
donc les deux voies coincident -- la forme est citee, pas exploitee.

## `...BladeOfTheAncestors_RemoveEffectAbility$$CreateTrigger`

    On(9 = Attack, ownerNeedsToBeAlive = 1)
  & get_OwnerIsCaster
  & WasCrit
  & HasEffect( Owner@+0x30, 0x5d1 = 1489, onlyActive = false, targetType = 6 = Both )

## `...BladeOfTheAncestors_RemoveEffectAbility$$CreateBehaviour(abilityState, triggerType)`

    if (triggerType != 0x20 = Custom)
        return TriggerAbilityDelayed( Owner@+0x30, 0x5d3 = 1491, unitSelectionType = 3 );
    return RemoveEffect( Owner@+0x30, Nullable(0x5d1 = 1489), replaceableEffectType = null );

================================================================================================
LE RESET EST DIFFERE, ET C'EST LA LECTURE PORTEUSE DE CETTE TRANCHE
================================================================================================
Le crit n'efface PAS le buff sur place : il ENFILE un re-declenchement de l'ability 1491, que
`IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities` draine APRES la
cloture complete du message top-level (RE de la file : `dispatch/pending.py`). Au drain, le natif
rappelle le slot 4 de CHAQUE classe de 1491 portee par l'entite, avec `triggerType = 0x20` :

    BladeOfTheAncestorsAbility            (Custom) -> `Nothing()`        = no-op
    BladeOfTheAncestors_RemoveEffectAbility (Custom) -> `RemoveEffect(Owner, 1489)`

Consequence OBSERVABLE : les coups SUIVANTS de l'attaque qui a crite beneficient encore du buff --
il ne tombe qu'une fois l'attaque terminee. Un collapse INLINE du `TriggerAbilityDelayed` retirerait
le buff au milieu de la salve.
⚠ `ActOfFaith_RemoveEffectAbility`, le jumeau de forme, a exactement la meme fourche, et son port
(`loki/act_of_faith.py`) ECARTE la branche `!= 0x20` en la disant << cross-instantiation gshared >>.
Cette lecture-la n'est PAS re-jugee ici (hors perimetre), mais elle est CONTREDITE par ce corps-ci,
qui n'est pas gshared du tout : residu `#1001-r1`.

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
* les DEUX `CreateTrigger` COLLAPSENT imperativement dans `matches` (patron `DawnBlade` pour le
  vecteur `On(UnitDeath)`, patron `ActOfFaithResetAbility` pour `On(9) & OwnerIsCaster & WasCrit`) ;
* les TROIS `CreateBehaviour` sont des feuilles DSL deja portees (`AddEffect`,
  `TriggerAbilityDelayed`, `RemoveEffect`) -- aucune Operation n'est re-ecrite ;
* la MAGNITUDE n'est PAS ici : elle vit dans la classe d'effet
  (`entities/effects/loki/votann.py::BladeOfTheAncestorsBuffEffect`), qui est le mirror de
  `...BladeOfTheAncestorsBuffEffect$$ApplyModification`. Mesure #1004 : les DEUX inscriptions sont
  necessaires -- l'ability seule poserait un `BaseEffect` NU qui ne change aucune stat.

RESIDUS NOMMES
  * `AreFriends(a, b, comparisonType = 0, anyEntity = 0)` -- les deux derniers arguments
    (`UnitTeamSelectionType` / `anyEntity`) ne sont pas modelises : le port compare les `team` des
    `OwnerComponent`, comme tous les autres collapses d'`AreFriends` du depot.
  * `HasEffect(..., onlyActive = false, targetType = 6 = Both)` -- `EffectsState.has_effect` ne
    filtre ni sur `IsActive` ni sur le `EffectTargetType`, donc le gate porte est le MEME que le
    natif sur ce couple d'arguments (`onlyActive = false` = ce que fait deja le port).
  * `unitSelectionType = 3` de `TriggerAbilityDelayed` : conserve pour la tracabilite, jamais lu
    (le selecteur est `Owner`, deja resolu).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from ....abilities.behaviours.lifecycle import TriggerAbilityDelayed
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `RELIC_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability de relique.
ABILITY_ID = "BladeOfTheAncestors"
#: `TriggerAbilityDelayed(Owner, 0x5d3, 3)` et `AbilityOrEffect(0x5d3)` du `.ctor` de l'effet.
BLADE_OF_THE_ANCESTORS = int(TriggeredAbilityType.BladeOfTheAncestors)      # 0x5d3 = 1491
#: `AddEffect(0x5d1, ...)` / `RemoveEffect(Owner, Nullable(0x5d1))` / `HasEffect(Owner, 0x5d1, ...)`.
BUFF_EFFECT = int(EffectType.BladeOfTheAncestors_Effect)                    # 0x5d1 = 1489

#: `HasTrait(<slot>, 0x10)` -- le << character >> de l'i2.
HERO_TRAIT = UnitTrait.Hero                                                 # 0x10 = 16
#: `IsNormalUnit(unit)` = `IdunBattle.Entities.UnitExtensions$$IsNormalUnit` (LU) :
#: `NOT HasTrait(unit, 0xd = Object) AND NOT HasTrait(unit, 0x1b = Steppable)`.
NON_NORMAL_TRAITS = (UnitTrait.Object, UnitTrait.Steppable)                 # 0xd = 13, 0x1b = 27

#: `unitSelectionType` (4e argument natif) du `TriggerAbilityDelayed` -- trace, jamais lu.
DELAYED_UNIT_SELECTION_TYPE = 3


def _traits_of(state: State, uid) -> list:
    e = state.get_entity(uid) if uid is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    return list(getattr(sc.ctx, "traits", None) or []) if sc is not None else []


def _team_of(state: State, uid) -> Optional[int]:
    e = state.get_entity(uid) if uid is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _is_normal_unit(state: State, uid) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsNormalUnit(unit)`, MIRROR 1:1 du decompile :

        comp = GetBaseUnitComponent(unit)
        if (comp != null && comp.HasTrait(0xd  = Object))    return false;
        comp = GetBaseUnitComponent(unit)
        if (comp != null)  return !comp.HasTrait(0x1b = Steppable);
        return true;

    Ce N'EST PAS un no-op offline : `state.entities` porte des summons `Steppable` (les mines
    `HaywireMine`, les `powup*`), qui sont exactement ce que ce gate exclut."""
    tr = _traits_of(state, uid)
    return not any(has_trait(tr, t) for t in NON_NORMAL_TRAITS)


def _friendly_hero(state: State, uid, owner_team: Optional[int]) -> bool:
    """`AreFriends(<slot>, Owner@+0x30) & HasTrait(<slot>, 0x10 = Hero)` -- le conjoint commun aux
    DEUX branches du `CreateTrigger`, sur des slots differents.

    `AreFriends` = meme `team` (collapse standard du depot) ; equipe inconnue -> FAUX (degradation
    RESTRICTIVE, jamais un declenchement invente)."""
    if uid is None or owner_team is None:
        return False
    if _team_of(state, uid) != owner_team:
        return False
    return has_trait(_traits_of(state, uid), HERO_TRAIT)


def blade_of_the_ancestors_add_tree():
    """`...BladeOfTheAncestorsAbility$$CreateBehaviour`, branche `triggerType != Custom` =
    `AddEffect(0x5d1, AbilityStateReference, Owner@+0x30, turns = null)`.

    `duration_rounds=None` : le natif passe `turns = null`, donc la duree vient de
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds`,
    dont le switch ne connait PAS `0x5d1` -> **PERMANENT** (le buff n'est retire que par le crit).
    Meme lecture que le `0x3f9` d'`ActOfFaith`.

    `scale_from_source` reste FAUX, et c'est DELIBERE : il seederait `ability_level =
    passive_ability_level` (50 sur tout runner normalise), alors que l'`AbilityStateReference` d'une
    relique est le couple TERTIAIRE. C'est `BladeOfTheAncestorsBuffEffect.applied_stat_mods` qui
    resout le bon couple, sur le ctx du porteur -- qui EST celui de la source, la pose etant
    `Owner -> Owner`."""
    return AddEffect(BUFF_EFFECT, EffectType.BladeOfTheAncestors_Effect.name, Owner(),
                     duration_rounds=None, source_from_target=True)


def blade_of_the_ancestors_delayed_tree():
    """`...BladeOfTheAncestors_RemoveEffectAbility$$CreateBehaviour`, branche `triggerType != Custom`
    = `TriggerAbilityDelayed(Owner@+0x30, 0x5d3 = 1491, 3)` -- l'ENFILEMENT, aucun retrait ici."""
    return TriggerAbilityDelayed(Owner(), BLADE_OF_THE_ANCESTORS,
                                 unit_selection_type=DELAYED_UNIT_SELECTION_TYPE)


def blade_of_the_ancestors_remove_tree():
    """`...BladeOfTheAncestors_RemoveEffectAbility$$CreateBehaviour`, branche
    `triggerType == 0x20 = Custom` = `RemoveEffect(Owner@+0x30, Nullable(0x5d1))`.

    La feuille itere les instances du porteur et revert le `ChangeStat` de chacune par-source
    (`reverted_stats()` de la classe d'effet) : TOUTES les piles tombent d'un coup, comme le
    `RemoveEffect` natif, qui ne porte aucun compteur."""
    return RemoveEffect(BUFF_EFFECT, Owner())


class BladeOfTheAncestorsAbility(TriggeredAbility):
    """`BladeOfTheAncestorsAbility` -- ACCUMULATION : une pile de buff crit de plus a chaque fois
    qu'un HERO allie MEURT, ou qu'un HERO allie TUE une unite normale.

    `On(0 = UnitDeath)` est le 3e des cinq events de mort de
    `IdunBattle.Operations.KillUnitOperation$$Execute` (`dispatch/move_death.unit_death_triggers`) ;
    son `actor` est le TUEUR et son `dying`/`target` la victime."""

    event_id = int(EventTriggerType.UnitDeath)                              # 0
    TRIGGERED_ABILITY_ID = BLADE_OF_THE_ANCESTORS                           # 1491

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:              # `On(..., ownerNeedsToBeAlive = 1)`
            return False
        owner_team = _team_of(state, self.owner_id)
        dying = ev.dying_id if ev.dying_id is not None else ev.target_id
        # BRANCHE 1 -- `AreFriends(Targets@+0x60, Owner) & HasTrait(Targets@+0x60, Hero)`
        if _friendly_hero(state, dying, owner_team):
            return True
        # BRANCHE 2 -- `AreFriends(Actor@+0x40, Owner) & HasTrait(Actor@+0x40, Hero)
        #               & IsNormalUnit(Targets@+0x60)`
        if not _friendly_hero(state, ev.actor_id, owner_team):
            return False
        return dying is not None and _is_normal_unit(state, dying)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), ev.dying_id,
                                       actor_id=ev.actor_id)
        blade_of_the_ancestors_add_tree().execute(entities, ectx)
        placed = [p for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        if not placed:
            return None
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "dying": None if ev.dying_id is None else int(ev.dying_id),
                "killer": None if ev.actor_id is None else int(ev.actor_id),
                "stacks_added": len(placed), "dsl": True}


class BladeOfTheAncestorsRemoveEffectAbility(TriggeredAbility):
    """`BladeOfTheAncestors_RemoveEffectAbility`, vecteur `On(9 = Attack)` -- le CRIT du porteur
    ENFILE le reset. Aucun retrait ici (cf. l'en-tete : le reset tombe au drain).

    `On(9)` est l'evenement GENERIQUE de fin d'attaque (`FinishAttackOperation`, emis pour l'attaque
    NORMALE comme pour une ability) : le reset n'a aucun gate normal/ability, `WasCrit` est le seul
    filtre de type -- meme lecture que `ActOfFaithResetAbility` (verdict G6b)."""

    event_id = int(EventTriggerType.Attack)                                 # 9
    TRIGGERED_ABILITY_ID = BLADE_OF_THE_ANCESTORS                           # 1491

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):   # get_OwnerIsCaster
            return False
        if not ev.is_crit:                                                  # WasCrit
            return False
        if state.effects is None:                                           # HasEffect(Owner, 0x5d1)
            return False
        return bool(state.effects.has_effect(int(self.owner_id), effect_type=BUFF_EFFECT))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), None, actor_id=ev.actor_id)
        blade_of_the_ancestors_delayed_tree().execute(entities, ectx)
        delayed = [p for n, p in ectx.emitted if n == "TriggerAbilityDelayed"]
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "queued": bool(delayed and delayed[0].get("queued")),
                "dispatched": bool(delayed and delayed[0].get("dispatched")), "dsl": True}


class BladeOfTheAncestorsCustomRemoveEffectAbility(TriggeredAbility):
    """`BladeOfTheAncestors_RemoveEffectAbility$$CreateBehaviour`, branche
    `triggerType == 0x20 = Custom` -- LE RESET. Jamais atteinte par le bus d'events : inscrite dans
    `CUSTOM_TRIGGERED_ABILITIES[1491]`, elle n'est joignable que par le drain de
    `state.pending_triggered_abilities`.

    `matches` rend `True` : sur ce chemin le natif ne RE-EVALUE aucun trigger
    (`TriggerTriggeredAbilityOperation$$TriggerAbility` n'appelle que le slot 4). Le seul gate qui
    reste est celui du drain lui-meme (`IsUnit(entity) => IsAlive(entity)`), porte par
    `dispatch/pending.trigger_triggered_ability`.

    ⚠ Le jumeau `BladeOfTheAncestorsAbility` a LUI AUSSI une branche `Custom`, et elle vaut
    `DSLBehaviors$$Nothing()` : le natif l'appelle au drain et elle ne fait RIEN. Elle n'est donc
    pas inscrite au registre -- une classe de no-op y serait un mensonge de couverture, pas une
    fidelite."""

    event_id = int(EventTriggerType.Custom)          # 0x20 -- jamais emis par le bus du port
    TRIGGERED_ABILITY_ID = BLADE_OF_THE_ANCESTORS    # 1491

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), None)
        blade_of_the_ancestors_remove_tree().execute(entities, ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        return {"relic": ABILITY_ID, "owner": int(self.owner_id), "removed": removed, "dsl": True}
