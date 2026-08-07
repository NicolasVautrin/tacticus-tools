"""`IdunBattle.Entities.Effects.Loki.EuphoricStrikes_ExtraCritEffect` (effet 0x595 = 1429, pose par
`IdunBattleLogic.Entities.Abilities.Active.Loki.EuphoricStrikesAbility$$ExecuteBehaviour` sur la
cible d'`emperExultant` « Laviscus ») -- son TRIGGER DE RETRAIT. #522.

## Ce que ce module tient

Le +`extraCritChance` de 1429 est une CHARGE A USAGE UNIQUE : l'i2 dit « The **next** attack against
that enemy this turn has +{[extraCritChance]}% Crit Chance ». Sans ce retrait, le port bufferait
**toutes** les attaques portees contre la cible pendant le tour -- regression PERMISSIVE et
SILENCIEUSE, exactement la forme de `Chronometron_ExtraDamage` (1550) et de `ShockAssault_Buff`
(1000). La contribution elle-meme vit dans `entities/effects/loki/euphoric_strikes.py`.

## RE native (decompile ghidra, build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.Loki.EuphoricStrikes_ExtraCritEffect$$CreateRemoveEffectTrigger`, dans
l'ordre exact des `op_BitwiseAnd` / `op_BitwiseOr` :

      On( 9 = EventTriggerType.Attack,    ownerNeedsToBeAlive: true ) & get_OwnerIsTarget
    | On( 0 = EventTriggerType.UnitDeath, ownerNeedsToBeAlive: true )
        & AreEqual( Target@DSLSelectors+0x60, EffectSource(Effect@DSLSelectors+0x38) )

`IdunBattleLogic.Entities.DSLTriggers$$On(this, triggerType, ownerNeedsToBeAlive)` -- signature
relue : le second litteral est le DRAPEAU, pas un second event. Le drapeau VRAI fait choisir a `On`
le conjoint `<DSLTriggers+0x20>` = `IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`
(`IsUnit(owner) ? UnitExtensions.IsAlive(owner, state) : true`), nomme par case-224 item 5 -- il est
donc porte ici, sur les DEUX disjoints.

Comme pour 1550 / 1180, le trigger n'est PAS enregistre par la classe d'effet : c'est
`IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` qui, quand le virtuel
`CreateRemoveEffectTrigger` rend un trigger non nul, AJOUTE a l'`ArraySet` de l'effet

    Triggered( CreateRemoveEffectTrigger(), DSLFactory.RemoveEffect(df@0x150) )

(== `IdunBattle.Entities.Effects.BaseEffect$$GetRemoveEffectBehaviour`, `df@0x150` = le selecteur
d'ENTITE-EFFET COURANTE -> retire CETTE instance).

## Les deux disjoints, et ce qu'ils designent

* **`On(9) & get_OwnerIsTarget`** -- `9` = `EventTriggerType.Attack`, event GENERIQUE emis par
  `IdunBattle.Operations.FinishAttackOperation$$Execute` a la FIN de TOUTE attaque (normale ET
  ability), deja cable des deux cotes cote port (`after_hit_normal_attack` /
  `after_hit_ability_attack`). `get_OwnerIsTarget` = `AreEqual(Owner@+0x30, Target@+0x60)` : le
  PORTEUR est le DEFENSEUR du coup. Le bonus s'applique donc encore a l'attaque qui consomme la
  marque -- le degat est resolu PENDANT l'attaque, `On(9)` ne fire qu'a sa cloture. C'est le meme
  ordonnancement que 1550.
* **`On(0) & AreEqual(Target, EffectSource(Effect))`** -- `0` = `EventTriggerType.UnitDeath`, le 3e
  des events de mort emis par `IdunBattle.Operations.KillUnitOperation$$Execute`. Le vecteur du port
  (`dispatch/move_death.py`) pose `actor = le TUEUR`, `target = la victime` : le noeud demande donc
  « la victime est-elle la SOURCE de cet effet ? », c'est-a-dire **la marque saute si Laviscus
  meurt**. `EffectSource(<DSLSelectors+0x38>)` = `IdunBattleLogic.Entities.DSLSelectors$$EffectSource`
  applique au slot `Effect` : la SOURCE de l'effet (`EffectComponent.SourceUnit @+0x10`), donc
  `BaseEffect.source`, pas son porteur.

## Frontiere DSL/imperatif (#149)

Le behaviour est un noeud `DSLFactory.RemoveEffect` -> porte comme un ARBRE (feuille `RemoveEffect`) ;
le predicat du trigger est COLLAPSE imperativement dans `matches` (doctrine SuppressiveFire #74 /
`ChronometronExtraDamageRemove` / `InspiredToGreatnessOverrideLevelRemove`).

COLLAPSE ASSUME, identique a celui de `ChronometronExtraDamageRemove` : le natif retire
**l'instance** (`RemoveEffect(df@0x150)`), le port retire tous les 1429 non consommes du porteur
(`RemoveEffect(effectType, Caster())`, la seule forme portee). Le gate << deja present >> d'
`AddEffectOperation` garantit au plus UNE instance de 1429 par unite -> les deux formes coincident
(une re-pose incremente `times_applied` sur l'instance existante au lieu d'en creer une seconde).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import RemoveEffect
from .....entities.effect_type import EffectType
from .....entities.selectors.tiles import Caster
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import EffectTrigger, TriggerEvent

EUPHORIC_STRIKES_EXTRA_CRIT = int(EffectType.EuphoricStrikes_ExtraCrit)   # 0x595 = 1429


class EuphoricStrikesExtraCritRemove(EffectTrigger):
    """`EuphoricStrikes_ExtraCritEffect$$CreateRemoveEffectTrigger` = `On(9, alive) & OwnerIsTarget
    | On(0, alive) & AreEqual(Target, EffectSource(Effect))` ->
    `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette instance>)`.

    OBSERVABLE : l'ennemi marque par Laviscus donne +`extraCritChance` de chance de crit a la
    PREMIERE attaque portee contre lui, puis 1429 disparait de `decisionView.effects` -- les
    attaques suivantes sont nues. Et si Laviscus meurt avant, la marque saute immediatement."""
    effect_type = EUPHORIC_STRIKES_EXTRA_CRIT
    event_id = int(EventTriggerType.Attack)                       # On(9) -- 1er disjoint
    # 2e disjoint : `On(0 = UnitDeath)`. Meme entree, deux events -- le dispatch accepte `event_ids`
    # sur toute entree (`dispatch/core.py`), pas seulement sur les tile-effects (precedent :
    # `ReactivateOverwatchHitReductionRemove`).
    event_ids = (int(EventTriggerType.Attack), int(EventTriggerType.UnitDeath))

    def _source_of_instance(self, state: State) -> Optional[int]:
        """`EffectSource(Effect@0x150)` = `EffectComponent.SourceUnit @+0x10` de l'instance portee."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return None
        for e in eff.by_unit.get(int(self.owner_id), []):
            if not e.consumed and e.effect_type == EUPHORIC_STRIKES_EXTRA_CRIT:
                return e.source
        return None

    def _owner_is_alive(self, state: State) -> bool:
        """Conjoint `<DSLTriggers+0x20>` = `OwnerIsAliveAbilityTrigger$$ShouldTrigger` que
        `DSLTriggers$$On` place quand `ownerNeedsToBeAlive` est VRAI (le cas des DEUX disjoints
        ici) : `IsUnit(owner) ? UnitExtensions.IsAlive(owner, state) : true`. Une entite-tuile (pas
        d'`UnitComponent`) passe donc, comme le natif."""
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        uc = e.get_component(UnitComponent)
        return True if uc is None else bool(uc.alive)      # IsUnit(owner) ? IsAlive(owner) : true

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if not self._owner_is_alive(state):                # On(..., ownerNeedsToBeAlive: true)
            return False
        if ev.target_id is None:
            return False
        if int(ev.event_id) == int(EventTriggerType.Attack):
            # get_OwnerIsTarget = AreEqual(Owner@+0x30, Target@+0x60) -- le porteur est le DEFENSEUR.
            return int(ev.target_id) == int(self.owner_id)
        # On(0 = UnitDeath) : `target` = la victime (`dispatch/move_death.py`) ->
        # AreEqual(Target@+0x60, EffectSource(Effect@+0x38)) = « la SOURCE de la marque meurt ».
        src = self._source_of_instance(state)
        return src is not None and int(ev.target_id) == int(src)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(EUPHORIC_STRIKES_EXTRA_CRIT, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": EffectType.EuphoricStrikes_ExtraCrit.name, "owner": int(self.owner_id),
                "removed": removed, "on_event": int(ev.event_id), "actor": ev.actor_id}
