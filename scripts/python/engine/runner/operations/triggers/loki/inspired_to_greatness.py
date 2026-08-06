"""`IdunBattle.Entities.Effects.Loki.InspiredToGreatness_OverrideLevelEffect` (effet 0x49c = 1180,
pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$ExecuteBehaviour`
sur l'allie `canReset` de `tauAunShi`) -- son TRIGGER DE RETRAIT.

## Ce qui manquait (residu #114 §5.2)

Le lot #114 posait bien l'effet (`AddStatOverrideEffect(canReset, 1180, ACTIVE_ABILITY_LEVEL, lvl)`,
magnitude bit-exacte validee live) mais ne branchait AUCUN retrait -> l'override de
`active_ability_level` etait PERMANENT offline, la ou le natif le borne a UNE utilisation.

## RE native (decompile ghidra, build gqfc5mff6c)

`IdunBattle.Entities.Effects.Loki.InspiredToGreatness_OverrideLevelEffect$$CreateRemoveEffectTrigger` :

    On(0xc) & get_OwnerIsCaster                       # `DSLFactory.On(df, 0xc, 1, 0)` puis op_BitwiseAnd

Le trigger n'est PAS enregistre par la classe d'effet elle-meme : c'est
`IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` (le wrapper GENERIQUE au-dessus
de `CreateHandleTriggerAbilitiesInternal`) qui, quand le virtuel `CreateRemoveEffectTrigger` rend un
trigger non nul, AJOUTE a l'`ArraySet` de l'effet :

    Triggered( CreateRemoveEffectTrigger(),
               DSLFactory.RemoveEffect(df@0x150) )     # == `BaseEffect$$GetRemoveEffectBehaviour`

`df@0x150` = le selecteur d'ENTITE-EFFET COURANTE -> le behaviour retire CETTE instance
(`RemoveEffect(effect : ITargetsSelector)`, l'overload a 1 argument).

`0xc` = `EventTriggerType.UnitActiveAbility`. Emis par
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` APRES l'execution de la behaviour et
AVANT `AddFlagsAfterAbilityExecution`, **sous le gate**
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsActiveAbility` :

    On(0xb)  UnitAbility            -- inconditionnel
    if (IsActiveAbility(abilityType)) On(0xc)  UnitActiveAbility
    AddFlagsAfterAbilityExecution(...)
    On(0xe)  UnitPostAbility

=> une ATTAQUE NORMALE (un `IsRegularAttack`) N'EMET PAS `0xc`, bien qu'elle emprunte la meme
operation. La semantique du retrait est donc exactement « au PROCHAIN CAST D'ACTIF du porteur »
(l'utilisation supplementaire que 1082 vient de lui accorder), pas « a sa prochaine action ».

## Frontiere DSL/imperatif (#149)

Le behaviour est un noeud `DSLFactory.RemoveEffect` -> porte comme un ARBRE (feuille `RemoveEffect`),
qui delegue au revert imperatif (`AddEffectOperation.revert_stat_overrides` = `<Effect>.RevertInternal`
part OVERRIDE, `ResetStat` part 8). Le predicat du trigger (`OwnerIsCaster`) est COLLAPSE
imperativement dans `matches`, comme tous les triggers portes (doctrine SuppressiveFire #74 /
MasterAnnihilator).

COLLAPSE ASSUME : le natif retire **l'instance** (`RemoveEffect(df@0x150)`), le port retire tous les
stacks 1180 non consommes du porteur (`RemoveEffect(effectType, Caster())`, la seule forme portee).
1180 est pose par `AddStatOverrideEffect`, dont l'`AddEffectOperation` a un gate << deja present >> ->
au plus UNE instance par unite : les deux formes coincident.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import RemoveEffect
from .....entities.effect_type import EffectType
from .....entities.selectors.tiles import Caster
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import EffectTrigger, TriggerEvent

ITG_OVERRIDE_LEVEL = int(EffectType.InspiredToGreatness_OverrideLevel)   # 0x49c = 1180


class InspiredToGreatnessOverrideLevelRemove(EffectTrigger):
    """`InspiredToGreatness_OverrideLevelEffect$$CreateRemoveEffectTrigger` = `On(0xc) & OwnerIsCaster`
    -> `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette instance>)`.

    OBSERVABLE : l'allie « inspire » garde son `active_ability_level` plafonne (le `Min` de 1082) tant
    qu'il n'a pas re-utilise son actif ; des qu'il le CASTE, l'effet 1180 disparait de
    `decisionView.effects` et le niveau d'ability revient a sa valeur d'origine (`overridden_prev`).
    L'ordre natif garantit que le cast LUI-MEME beneficie encore de l'override (`On(0xc)` est emis
    APRES l'execution de la behaviour)."""
    effect_type = ITG_OVERRIDE_LEVEL
    event_id = EventTriggerType.UnitActiveAbility          # 0xc = 12

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` : le PORTEUR de l'effet est le caster de l'ability qui vient de
        # s'executer (l'`AbilityEntities` de `On(0xc)` a caster/actor = le caster du cast).
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(ITG_OVERRIDE_LEVEL, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": "InspiredToGreatness_OverrideLevel", "owner": int(self.owner_id),
                "removed": removed, "on_ability": ev.ability_type}
