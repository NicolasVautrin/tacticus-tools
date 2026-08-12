"""`Skullsmasher` (`TriggeredAbilityType 0x4c1 = 1217`, passif de kit de `worldJakhal` << Macer >>)
-- les DEUX volets STUN. Le volet DEGAT (owner-effect `1263 Skullsmasher_ExtraDamage`) vit dans
`entities/effects/loki/skullsmasher.py` : il n'a AUCUN trigger propre.

i2 : << [...] In addition, if Macer has defeated an enemy this battle, all enemies he attacks become
Stunned. >>

===================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- recense par le bloc `methodPointers`
===================================================================================================

Le passif derive TROIS abilities natives ; leurs BASES sont LUES dans `frida/classes.tsv` :

    Skullsmasher_DamageEffectAbility  : AOwnerEffectTriggeredAbility   -> owner-effect, PAS ce module
    Skullsmasher_ActivateStunAbility  : BaseTriggeredAbility           -> CE module (le MARQUEUR)
    Skullsmasher_TriggerStunAbility   : BaseTriggeredAbility           -> CE module (le STUN)

Slots `DSLSelectors` : `+0x30 Owner` · `+0x60 Target`.

## `...Skullsmasher_ActivateStunAbility$$CreateTrigger` -- << a deja tue cette bataille >>

    OnDeath( triggerOnOverkill: true, triggerOnSteppable: false )
        & NOT HasTrait( Target@+0x60, UnitTrait.Object = 0xd )
        & get_OwnerIsActor

`IdunBattleLogic.Entities.DSLTriggers$$OnDeath(a, b)` = `OnDeathEvent(0, a, b)`, et le corps
d'`OnDeathEvent` a ete RELU verbatim :

    return On(triggerType) & <DSLTriggers+0x70 = Yes>
           & (a ? <Yes> : NOT TargetIsOverkilled())
           & (b ? <Yes> : NOT HasTrait(Target@+0x60, 0x1b = Steppable))

Avec `a = true, b = false` -> `On(0 = EventTriggerType.UnitDeath) & NOT HasTrait(Target, Steppable)` :
le marqueur se pose MEME sur un overkill, JAMAIS sur une entite `Steppable`.

⚠ Les deux litteraux sont decodes aux OCTETS (`mov dl, 1` / `xor r8d, r8d` juste avant le `call`),
pas lus dans le pseudo-C ; et le `0xd` du second `HasTrait` l'est aussi (`mov r8d, 0xd`).

⚠ **`EventTriggerType.UnitDeath = 0`, PAS `PreUnitDeath_2 = 2`** : c'est le 3e event de
`KillUnitOperation$$Execute`, pas le 2e -- l'ecart avec `HeadClaimer` (#947), qui appelle
`OnPreDeath2`. Le port emet bien les DEUX (`dispatch/move_death.py`).

⚠ **Deux gates de trait, PAS un** : `Steppable` (0x1b) vient d'`OnDeathEvent`, `Object` (0xd) est
propre a cette ability. Les collapser en un seul les rendrait interchangeables ; ils ne le sont pas
(`BarbedOvipositor` porte, lui, un `IsObjectOrSteppable` UNIQUE -- un autre noeud natif).

## `...Skullsmasher_ActivateStunAbility$$CreateBehaviour`

    AddEffect( 0x4f0 = EffectType.Skullsmasher_StunEffect,
               AbilityStateReference, source = Owner@+0x30, targets = Owner@+0x30,
               options = <Nullable<AddEffectBehaviourOptions> VIDE> )

La SURCHARGE est tranchee par l'ADRESSE de la cible du `call` : `0xe9e8b0` =
`AddEffect(effectType, abilityState, source, targets, options: Nullable<AddEffectBehaviourOptions>)`,
et non `0xe9e9b0` (`turns: IAmountFormula`, celle qu'emprunte `ObsessiveAnnunciation_OverkillAbility`
du meme lot). Les 32 octets d'options sont mis a ZERO juste avant l'appel -> **aucune duree**, donc
`DefaultAmountOfRounds(0x4f0)` -> ABSENT de la table -> **PERMANENT** (`remaining = 0`). C'est le
<< this battle >> de l'i2.

## `...Skullsmasher_TriggerStunAbility$$CreateTrigger` / `$$CreateBehaviour`

    On( 0x9 = EventTriggerType.Attack, ownerNeedsToBeAlive: true )
        & get_OwnerIsActor
        & HasEffect( Owner@+0x30, 0x4f0, onlyActive: false, EffectTargetType.Both = 6 )

    AddEffect( 0x48a = EffectType.Stunned, AbilityStateReference,
               source = Owner@+0x30, targets = Target@+0x60, options = <VIDE> )

  * `On` est la surcharge `(triggerType, ownerNeedsToBeAlive: bool)` = `0xedaf60` (les deux autres
    prennent un `IAbilityTrigger` ou un TABLEAU) ;
  * `HasEffect` : `onlyActive = false` -> une instance INACTIVE compte (le marqueur n'a de toute
    facon aucune condition d'activite), `targetType = Both` -> ni << seulement source >> ni
    << seulement cible >> ;
  * les options de l'`AddEffect` sont VIDES ici aussi -> `DefaultAmountOfRounds(0x48a = Stunned)`
    = **1 round**, converti en TOURS par `ConvertRoundsToTurns` DANS l'operation. Le port passe donc
    `duration_rounds=None` (et non `1`), pour que la conversion reste celle du natif.

## Ce que le port NE recable PAS

`get_OwnerIsActor` : sur `On(0 = UnitDeath)` l'acteur est le TUEUR, sur `On(9 = Attack)` c'est
l'ATTAQUANT -- les deux vecteurs construisent leur `TriggerEvent` avec `actor = <celui qui agit>`
(`dispatch/move_death.py`, `dispatch/attack.py`). Un seul predicat, deux vecteurs.

⚠ **AUCUN gate d'equipe sur la mort** : le trigger natif ne porte NI `AreEnemies` NI
`NOT AreFriends` (contraste `HeadClaimer`, qui porte le second). Un allie tue par Macer arme donc le
marqueur -- l'i2 dit << defeated an enemy >>, le decompile dit << a tue >>, et c'est le decompile qui
fait foi. Le regime est de toute facon inatteignable en jeu normal (on n'attaque pas ses allies).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.effects.loki.skullsmasher import ABILITY_ID
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggers import HasTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ..base import TriggeredAbility, TriggerEvent

#: `TriggeredAbilityType.Skullsmasher` = `0x4c1` = 1217 -- l'`AbilityOrEffect` que le `.ctor` de
#: l'effet 1263 passe a `BaseEffect`, donc la config qu'indexent ses `ConfigVar`/`ConfigConst`.
SKULLSMASHER_ABILITY = TriggeredAbilityType.Skullsmasher
#: `EffectType 0x4f0 = 1264` -- le MARQUEUR pose sur Macer au premier kill (PERMANENT).
#: ⚠ `TriggeredAbilityType` 1264 nomme `VisionsOfHeresy` : une confusion d'enum ne leverait pas.
STUN_MARKER = int(EffectType.Skullsmasher_StunEffect)
STUN_MARKER_NAME = EffectType.Skullsmasher_StunEffect.name
#: `EffectType 0x48a = 1162` -- le `Stunned` COMPOSITE (parent -> enfants 1165/1166/1167), pose sur
#: la CIBLE. ⚠ `ActiveAbilityType` 1162 nomme `AncientFury_NormalAttack`.
STUNNED = int(EffectType.Stunned)
STUNNED_NAME = EffectType.Stunned.name

#: `steppableGate` d'`OnDeathEvent(0, a, b = false)` = `NOT HasTrait(Target@+0x60, 0x1b)`.
_TARGET_IS_STEPPABLE = HasTrait(Target(), int(UnitTrait.Steppable))
#: le conjoint PROPRE a `...Skullsmasher_ActivateStunAbility$$CreateTrigger` (`mov r8d, 0xd`).
_TARGET_IS_OBJECT = HasTrait(Target(), int(UnitTrait.Object))


def skullsmasher_marker_tree():
    """`AddEffect(0x4f0, AbilityStateReference, source = Owner@+0x30, targets = Owner@+0x30,
    options = <VIDE>)`.

    `Caster()` = `Owner@DSLSelectors+0x30` (sur une triggered, `Owner == Caster`). Options VIDES ->
    `duration_rounds=None` ET `duration_turns=None` : la cascade de duree de
    `AddEffectOperation$$Execute` tombe alors sur `DefaultAmountOfRounds(0x4f0)`, ABSENTE de la
    table -> **PERMANENT**. `scale_from_source=True` porte l'`AbilityStateReference` du natif."""
    return AddEffect(STUN_MARKER, STUN_MARKER_NAME, Caster(),
                     duration_rounds=None, scale_from_source=True)


def skullsmasher_stun_tree():
    """`AddEffect(0x48a = Stunned, AbilityStateReference, source = Owner@+0x30,
    targets = Target@+0x60, options = <VIDE>)`.

    La CIBLE est `Target()` (`DSLSelectors+0x60`), pas `Caster()` -- c'est le seul endroit du kit ou
    les deux selecteurs different. Options VIDES -> `DefaultAmountOfRounds(0x48a) = 1 round`,
    converti en tours DANS l'operation (d'ou `duration_rounds=None`, jamais un `1` en dur qui
    court-circuiterait `ConvertRoundsToTurns`)."""
    return AddEffect(STUNNED, STUNNED_NAME, Target(),
                     duration_rounds=None, scale_from_source=True)


class SkullsmasherActivateStunAbility(TriggeredAbility):
    """`...Skullsmasher_ActivateStunAbility` : `OnDeath(overkill: true, steppable: false) &
    NOT HasTrait(Target, Object) & get_OwnerIsActor` -> `AddEffect(1264, Owner, Owner)`.

    Le marqueur est PERMANENT et le gate `HasEffect` du volet suivant le lit `onlyActive = false` :
    une seule pose suffit pour toute la bataille (`AddEffectOperation` refuse la re-pose)."""

    event_id = int(EventTriggerType.UnitDeath)                  # On(0)
    TRIGGERED_ABILITY_ID = SKULLSMASHER_ABILITY                 # 1217

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : sur un event de mort, l'ACTEUR est le TUEUR.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        if victim is None or int(victim) == int(self.owner_id):
            return False
        # Les DEUX gates de trait, evalues par des NOEUDS DSL (substrat `entity_trait_names`, repli
        # gameconfig #226) -- un CADAVRE charge sans `StatsComponent` y reste VOYANT, ce qu'une
        # lecture brute de `ctx.traits` ne serait pas.
        entities = entities_from_state(state, self.owner_id, victim)
        if _TARGET_IS_STEPPABLE.should_trigger(entities):       # `steppableGate` d'`OnDeathEvent`
            return False
        return not _TARGET_IS_OBJECT.should_trigger(entities)   # conjoint PROPRE

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        skullsmasher_marker_tree().execute(entities, ectx)
        placed = any(n == "AddEffect" and p.get("placed") for n, p in ectx.emitted)
        return {"ability": ABILITY_ID, "unit": int(self.owner_id),
                "victim": ev.dying_id if ev.dying_id is not None else ev.target_id,
                "marker_placed": bool(placed), "on_event": int(ev.event_id)}


class SkullsmasherTriggerStunAbility(TriggeredAbility):
    """`...Skullsmasher_TriggerStunAbility` : `On(9 = Attack, ownerNeedsToBeAlive: true) &
    get_OwnerIsActor & HasEffect(Owner, 1264, onlyActive: false, Both)` ->
    `AddEffect(1162 = Stunned, source = Owner, targets = Target)`.

    Le gate `HasEffect` est evalue sur l'etat REEL (`state.effects.has_effect`), le MEME store que
    celui qu'alimente `SkullsmasherActivateStunAbility` -- les deux volets ne peuvent donc pas
    diverger sur la presence du marqueur."""

    event_id = int(EventTriggerType.Attack)                     # On(9)
    TRIGGERED_ABILITY_ID = SKULLSMASHER_ABILITY                 # 1217

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : sur `On(Attack)`, l'ACTEUR est l'ATTAQUANT.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        if ev.target_id is None or int(ev.target_id) == int(self.owner_id):
            return False
        if state.effects is None:
            return False
        # `HasEffect(Owner@+0x30, 0x4f0, onlyActive: false, Both)` -- `has_effect` mirroire bien le
        # `onlyActive = 0` natif (il balaie `by_unit`, pas `active_effects`).
        return bool(state.effects.has_effect(int(self.owner_id), STUN_MARKER))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id)
        skullsmasher_stun_tree().execute(entities, ectx)
        placed = any(n == "AddEffect" and p.get("placed") for n, p in ectx.emitted)
        return {"ability": ABILITY_ID, "unit": int(self.owner_id), "target": ev.target_id,
                "stunned": bool(placed), "on_event": int(ev.event_id)}
