"""`IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect` (effet 0x60e = 1550, pose par
`IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour` sur chaque ennemi
du disque rayon 2 de `necroChronomancer`) -- son TRIGGER DE RETRAIT.

## Ce qui manquait (residu transverse R9)

Le lot #116 posait bien l'effet (visible dans `decisionView`) mais AUCUNE de ses deux faces n'etait
cablee : ni la contribution au degat (cf. `entities/effects/loki/damage_reduction.py`), ni son retrait.
Sans ce retrait, cabler la contribution aurait cree une DEUXIEME divergence -- un bonus PERMANENT la ou
le natif donne une charge a usage unique.

## RE native (decompile ghidra, build gqfc5mff6c)

`IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateRemoveEffectTrigger` :

    On(9)                                                   # BaseEffect$$On(this, 9)
      & get_OwnerIsTarget                                   # owner@0x148 == target@0x178
      & IsUnit(caster@0x160)
      & AreFriends(caster@0x160, EffectSource(Effect@0x150))

Comme pour `InspiredToGreatness_OverrideLevel` (#114 residu 2), le trigger n'est PAS enregistre par la
classe d'effet : c'est `IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` qui, quand
le virtuel `CreateRemoveEffectTrigger` rend un trigger non nul, AJOUTE a l'`ArraySet` de l'effet

    Triggered( CreateRemoveEffectTrigger(), DSLFactory.RemoveEffect(df@0x150) )

(== `IdunBattle.Entities.Effects.BaseEffect$$GetRemoveEffectBehaviour`, `df@0x150` = le selecteur
d'ENTITE-EFFET COURANTE -> retire CETTE instance).

`9` = `EventTriggerType.Attack`, event GENERIQUE emis par
`IdunBattle.Operations.FinishAttackOperation$$Execute` a la FIN de TOUTE attaque (normale ET ability) --
verdict RE deja etabli (#151/G6b) et deja cable des DEUX cotes cote port (`after_hit_normal_attack` et
`after_hit_ability_attack`). Le bonus s'applique donc encore au coup qui consomme l'effet : le degat est
resolu pendant l'attaque, `On(9)` ne fire qu'a sa cloture.

## Frontiere DSL/imperatif (#149)

Le behaviour est un noeud `DSLFactory.RemoveEffect` -> porte comme un ARBRE (feuille `RemoveEffect`) ;
le predicat du trigger est COLLAPSE imperativement dans `matches` (doctrine SuppressiveFire #74 /
MasterAnnihilator / InspiredToGreatness).

COLLAPSE ASSUME, identique a celui d'`InspiredToGreatnessOverrideLevelRemove` : le natif retire
**l'instance** (`RemoveEffect(df@0x150)`), le port retire tous les 1550 non consommes du porteur
(`RemoveEffect(effectType, Caster())`, la seule forme portee). Le gate << deja present >> d'
`AddEffectOperation` garantit au plus UNE instance de 1550 par unite -> les deux formes coincident (une
re-pose incremente `times_applied` sur l'instance existante au lieu d'en creer une seconde).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, UnitComponent
from ....abilities.behaviours import RemoveEffect, entities_from_state
from .....entities.effect_type import EffectType
from .....entities.selectors import Caster
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import EffectTrigger, TriggerEvent

CHRONOMETRON_EXTRA_DAMAGE = int(EffectType.Chronometron_ExtraDamage)   # 0x60e = 1550


class ChronometronExtraDamageRemove(EffectTrigger):
    """`Chronometron_ExtraDamageEffect$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget &
    IsUnit(caster@0x160) & AreFriends(caster@0x160, EffectSource(Effect@0x150))` ->
    `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette instance>)`.

    OBSERVABLE : l'ennemi marque par le Chronomancer prend le `+extraDmg[_2]` du PREMIER coup d'un allie
    du Chronomancer, puis 1550 disparait de `decisionView.effects` -- les coups suivants sont nus. Un
    coup porte par un ennemi DU Chronomancer (donc un allie de la victime) ne consomme rien (gate
    `AreFriends(caster, EffectSource)`)."""
    effect_type = CHRONOMETRON_EXTRA_DAMAGE
    event_id = EventTriggerType.Attack                     # 9

    def _source_of_instance(self, state: State) -> Optional[int]:
        """`EffectSource(Effect@0x150)` = `EffectComponent.SourceUnit @+0x10` de l'instance portee."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return None
        for e in eff.by_unit.get(int(self.owner_id), []):
            if not e.consumed and e.effect_type == CHRONOMETRON_EXTRA_DAMAGE:
                return e.source
        return None

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False                                   # get_OwnerIsTarget (owner@0x148 == target@0x178)
        att = state.get_entity(ev.actor_id) if ev.actor_id is not None else None
        if att is None or att.get_component(UnitComponent) is None:
            return False                                   # IsUnit(caster@0x160)
        src = self._source_of_instance(state)
        if src is None:
            return False
        so = state.get_entity(src)
        aoc = att.get_component(OwnerComponent)
        soc = so.get_component(OwnerComponent) if so is not None else None
        if aoc is None or soc is None:
            return False
        return aoc.team == soc.team                        # AreFriends(caster, EffectSource(Effect))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(CHRONOMETRON_EXTRA_DAMAGE, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": "Chronometron_ExtraDamage", "owner": int(self.owner_id),
                "removed": removed, "consumed_by": ev.actor_id}
