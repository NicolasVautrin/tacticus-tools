"""`ObsessiveAnnunciation` (`TriggeredAbilityType 0x5a3 = 1443`, passif de kit d'`emperKakophonist`
<< Adamatar >>) -- le volet OVERKILL, qui ARME l'aura de crit pour UN TOUR.

Les DEUX effets (`1432 ObsessiveAnnunciation_ExtraDmg`, aura permanente, et `1433
ObsessiveAnnunciation_ExtraCritDmg`, l'aura d'un tour posee ici) vivent dans
`entities/effects/loki/obsessive_annunciation.py` ; ce module ne porte que la POSE.

i2 : << [...] If an enemy was Overkilled this turn, enemies adjacent to Adamatar take
+{[extraCritDmg]} Crit Damage from all attacks by friendly Chaos units. >>

===================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- recense par le bloc `methodPointers`
===================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ObsessiveAnnunciation_OverkillAbility` :
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` (LU dans `frida/classes.tsv`, jamais dans le
nom du `.ctor`). Bloc : `[ CreateTrigger, CreateBehaviour, .ctor = <0x2ea440> ]`.
Slots `DSLSelectors` : `+0x30 Owner` · `+0x60 Target`.

## `$$CreateTrigger`

    OnDeath( triggerOnOverkill: true, triggerOnSteppable: false )
        & TargetIsOverkilled()
        & NOT HasEffect( Owner@+0x30, 0x599 = EffectType.ObsessiveAnnunciation_ExtraCritDmg,
                         onlyActive: false, EffectTargetType.Both = 6 )

`IdunBattleLogic.Entities.DSLTriggers$$OnDeath(a, b)` = `OnDeathEvent(0, a, b)`, dont le corps a
ete RELU verbatim :

    return On(triggerType) & <DSLTriggers+0x70 = Yes>
           & (a ? <Yes> : NOT TargetIsOverkilled())
           & (b ? <Yes> : NOT HasTrait(Target@+0x60, 0x1b = Steppable))

⚠ **Le gate d'overkill apparait DEUX FOIS, et les deux occurrences ne disent PAS la meme chose.**
`a = true` **DESARME** celui d'`OnDeathEvent` (il devient la constante VRAIE) ; c'est le
`TargetIsOverkilled()` **SEPARE** du `CreateTrigger` qui l'EXIGE. Lire `a = true` comme
<< overkill requis >> serait une confusion de sens (c'est l'inverse), et l'omettre parce qu'il est
<< deja la >> supprimerait la seule occurrence qui MORD. Les deux litteraux sont decodes aux OCTETS
(`mov dl, 1` / `xor r8d, r8d`), pas lus dans le pseudo-C.

Avec `a = true, b = false` -> `On(0 = EventTriggerType.UnitDeath) & NOT HasTrait(Target, Steppable)
& TargetIsOverkilled()`.

⚠ **AUCUN `get_OwnerIsActor`, AUCUN gate d'equipe.** Ce trigger ne demande PAS qu'Adamatar soit le
tueur : n'importe quel overkill sur le board arme son aura, y compris celui d'un adversaire. C'est
l'ecart le plus net avec ses deux voisins de forme (`TerrifyingCrescendoOverkillAbility` et
`HeadClaimerOnDeathAbility`, qui portent TOUS DEUX `get_OwnerIsActor`) -- le recopier bornerait
l'aura aux kills d'Adamatar, ce que ni le decompile ni l'i2 (<< If an enemy was Overkilled >>) ne
disent. Le seul filtre est `NOT HasEffect(Owner, 1433)` : ne pas RE-poser une aura deja la.

## `$$CreateBehaviour`

    AddEffect( 0x599, AbilityStateReference, source = Owner@+0x30, targets = Owner@+0x30,
               turns = <DSLFormulas+0x20> = Direct(1) )

⚠ **La SURCHARGE est l'autre** que celle de `Skullsmasher` (meme lot) : `0xe9e9b0` =
`AddEffect(effectType, abilityState, source, targets, turns: IAmountFormula)`, et non `0xe9e8b0`
(`options: Nullable<AddEffectBehaviourOptions>`). C'est l'ADRESSE de la cible du `call` qui tranche
-- le pseudo-C affiche le meme nom et la meme arite dans les deux cas. Consequence portee : la
duree est **1 TOUR** (`duration_turns=1`, jamais converti par `ConvertRoundsToTurns`), la ou la
surcharge d'a-cote laisse l'effet PERMANENT.

`<DSLFormulas+0x20>` = `Direct(1)` : le `.ctor` de `DSLFormulas` y ecrit `Direct(1)` (voisins :
`+0x18 = 0`, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`). C'est le MEME champ que
`HeadClaimerAbility$$CreateBehaviour` passe en `amount` -- meme constante, tout autre role.

## `AbilityStateReference` -> `scale_from_source=True`

Sans lui l'instance materialisee n'a pas d'`ability_level` et son `ConfigVar(extraCritDmg)` reste
INERTE : l'aura serait posee et muette.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.effects.loki.obsessive_annunciation import ABILITY_ID
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggers import HasTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ..base import TriggeredAbility, TriggerEvent

#: `TriggeredAbilityType.ObsessiveAnnunciation` = `0x5a3` = 1443 -- le litteral du `.ctor` du
#: playbook et l'`AbilityOrEffect` que le `.ctor` des deux effets passe a `BaseEffect`.
OBSESSIVE_ANNUNCIATION_ABILITY = TriggeredAbilityType.ObsessiveAnnunciation
#: `EffectType 0x599 = 1433` -- l'aura de CRIT, posee pour UN TOUR.
CRIT_AURA_EFFECT = int(EffectType.ObsessiveAnnunciation_ExtraCritDmg)
CRIT_AURA_EFFECT_NAME = EffectType.ObsessiveAnnunciation_ExtraCritDmg.name
#: `turns = <DSLFormulas+0x20> = Direct(1)` -- une duree DEJA EN TOURS (pas un `TurnsFromRounds`).
CRIT_AURA_DURATION_TURNS = 1

#: `steppableGate` d'`OnDeathEvent(0, a, b = false)` = `NOT HasTrait(Target@+0x60, 0x1b)`.
_TARGET_IS_STEPPABLE = HasTrait(Target(), int(UnitTrait.Steppable))


def obsessive_annunciation_crit_aura_tree():
    """`AddEffect(0x599, AbilityStateReference, source = Owner@+0x30, targets = Owner@+0x30,
    turns = Direct(1))` -- surcharge `turns: IAmountFormula` (`0xe9e9b0`).

    `Caster()` = `Owner@DSLSelectors+0x30` : l'aura vit sur ADAMATAR, ce sont ses ennemis adjacents
    qui la SUBISSENT (`CreateTargetSelector` de l'effet, cf. le module d'effets). `duration_turns=1`
    (et non `duration_rounds`) parce que le natif passe un `Direct(1)` dans `param_6.NullableA`, que
    `AddEffectOperation$$Execute` prend TEL QUEL sans `ConvertRoundsToTurns`."""
    return AddEffect(CRIT_AURA_EFFECT, CRIT_AURA_EFFECT_NAME, Caster(),
                     duration_rounds=None, duration_turns=CRIT_AURA_DURATION_TURNS,
                     scale_from_source=True)


class ObsessiveAnnunciationOverkillAbility(TriggeredAbility):
    """`...ObsessiveAnnunciation_OverkillAbility` : `OnDeath(overkill: true, steppable: false) &
    TargetIsOverkilled() & NOT HasEffect(Owner, 1433, onlyActive: false, Both)` ->
    `AddEffect(1433, source = Owner, targets = Owner, turns = Direct(1))`.

    ⚠ SANS `get_OwnerIsActor` : n'IMPORTE QUEL overkill du board arme l'aura (cf. l'en-tete)."""

    event_id = int(EventTriggerType.UnitDeath)                  # On(0)
    TRIGGERED_ABILITY_ID = OBSESSIVE_ANNUNCIATION_ABILITY       # 1443

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `TargetIsOverkilled()` -- le conjoint SEPARE du `CreateTrigger` (celui d'`OnDeathEvent`
        # est desarme par `triggerOnOverkill = true`). Canal `TriggerEvent.overkill`, threade par
        # `dispatch/move_death.unit_death_triggers`. Non threade -> FAUX : on ne fabrique pas un
        # overkill (meme convention que `was_block` chez `Deathwing`).
        if not ev.overkill:
            return False
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        if victim is None:
            return False
        # `steppableGate` : `NOT HasTrait(Target@+0x60, 0x1b = Steppable)`. Noeud DSL du foyer
        # (substrat `entity_trait_names`, repli gameconfig #226) -- un CADAVRE charge sans
        # `StatsComponent` y reste VOYANT.
        entities = entities_from_state(state, self.owner_id, victim)
        if _TARGET_IS_STEPPABLE.should_trigger(entities):
            return False
        if state.effects is None:
            return False
        # `NOT HasEffect(Owner@+0x30, 0x599, onlyActive: false, Both)` -- `has_effect` mirroire bien
        # le `onlyActive = 0` natif (il balaie `by_unit`, pas `active_effects`), donc une instance
        # INACTIVE compte : on ne re-pose pas une aura deja la, et on ne re-arme pas sa duree.
        return not state.effects.has_effect(int(self.owner_id), CRIT_AURA_EFFECT)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        obsessive_annunciation_crit_aura_tree().execute(entities, ectx)
        placed = any(n == "AddEffect" and p.get("placed") for n, p in ectx.emitted)
        return {"ability": ABILITY_ID, "unit": int(self.owner_id),
                "victim": ev.dying_id if ev.dying_id is not None else ev.target_id,
                "aura_placed": bool(placed), "on_event": int(ev.event_id)}
