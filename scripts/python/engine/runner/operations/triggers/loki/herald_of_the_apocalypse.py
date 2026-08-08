"""`IdunBattle.Entities.Effects.Loki.HeraldOfTheApocalypse_ExtraDamageEffect` (effet 0x403 = 1027, pose
par `IdunBattleLogic.Entities.Abilities.Active.Loki.HeraldOfTheApocalypseAbility$$ExecuteBehaviour` sur
la cible ET l'ennemi DIRECTEMENT DERRIERE elle) -- son TRIGGER DE RETRAIT. #BL-1020r.

## RE native (decompile ghidra, build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.Loki.HeraldOfTheApocalypse_ExtraDamageEffect$$CreateRemoveEffectTrigger` :

    On(9, ownerNeedsToBeAlive = 1)                          # DSLTriggers$$On(triggers@dsl+0x88, 9, 1)
      & get_OwnerIsTarget                                   # owner@+0x30 == target
      & IsUnit(caster@DSLSelectors+0x48)

Le jumeau `...$$GetRemoveTrigger` a un corps STRICTEMENT identique (meme trois noeuds, meme ordre) :
la classe expose les deux, ce qui ne change rien au trigger effectif.

Comme pour `Chronometron_ExtraDamage` (residu R9) et `InspiredToGreatness_OverrideLevel` (#114), le
trigger n'est PAS enregistre par la classe d'effet : c'est
`IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` qui, quand le virtuel
`CreateRemoveEffectTrigger` rend un trigger non nul, AJOUTE a l'`ArraySet` de l'effet

    Triggered( CreateRemoveEffectTrigger(), DSLFactory.RemoveEffect(df@0x150) )

(== `IdunBattle.Entities.Effects.BaseEffect$$GetRemoveEffectBehaviour`, `df@0x150` = le selecteur
d'ENTITE-EFFET COURANTE -> retire CETTE instance).

`9` = `EventTriggerType.Attack`, event GENERIQUE emis par
`IdunBattle.Operations.FinishAttackOperation$$Execute` a la FIN de TOUTE attaque (normale ET ability) --
verdict RE deja etabli (#151/G6b) et cable des DEUX cotes cote port (`after_hit_normal_attack` et
`after_hit_ability_attack`). Le bonus s'applique donc encore au coup qui consomme l'effet : le degat
est resolu pendant l'attaque, `On(9)` ne fire qu'a sa cloture. C'est exactement le << next attack >>
de l'i2.

## Ce que ce trigger N'A PAS, et son jumeau si

`ChronometronExtraDamageRemove` porte un 4e conjoint `AreFriends(caster, EffectSource(Effect))` : chez
lui, seul un allie du poseur consomme la charge. Ici ce conjoint est ABSENT du decompile -> **toute**
unite qui attaque le porteur consomme l'effet, y compris un allie de la victime. Ne pas recopier le
gate du voisin serait la faute inverse de celle que la doctrine proscrit.

## Frontiere DSL/imperatif (#149)

Le behaviour est un noeud `DSLFactory.RemoveEffect` -> porte comme un ARBRE (feuille `RemoveEffect`) ;
le predicat du trigger est COLLAPSE imperativement dans `matches` (doctrine SuppressiveFire #74 /
Chronometron / InspiredToGreatness).

COLLAPSE ASSUME, identique a celui de `ChronometronExtraDamageRemove` : le natif retire **l'instance**
(`RemoveEffect(df@0x150)`), le port retire tous les 1027 non consommes du porteur
(`RemoveEffect(effectType, Caster())`, la seule forme portee). Le gate << deja present >>
d'`AddEffectOperation` garantit au plus UNE instance de 1027 par unite -> les deux formes coincident.
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

HERALD_OF_THE_APOCALYPSE_EFFECT = int(EffectType.HeraldOfTheApocalypse)   # 0x403 = 1027


class HeraldOfTheApocalypseExtraDamageRemove(EffectTrigger):
    """`HeraldOfTheApocalypse_ExtraDamageEffect$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget &
    IsUnit(caster@DSLSelectors+0x48)` -> `BaseEffect$$GetRemoveEffectBehaviour` =
    `RemoveEffect(<cette instance>)`.

    OBSERVABLE : l'ennemi marque par Haarken prend le `+extraDmg` du PREMIER coup porte contre lui,
    puis 1027 disparait de `decisionView.effects` -- les coups suivants sont nus."""
    effect_type = HERALD_OF_THE_APOCALYPSE_EFFECT
    event_id = EventTriggerType.Attack                     # 9

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False                                   # get_OwnerIsTarget (owner@+0x30 == target)
        att = state.get_entity(ev.actor_id) if ev.actor_id is not None else None
        if att is None or att.get_component(UnitComponent) is None:
            return False                                   # IsUnit(caster@DSLSelectors+0x48)
        return True                                        # PAS d'AreFriends ici (cf. docstring)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(HERALD_OF_THE_APOCALYPSE_EFFECT, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": "HeraldOfTheApocalypse", "owner": int(self.owner_id),
                "removed": removed, "consumed_by": ev.actor_id}
