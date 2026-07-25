"""`HealUtility` — utilite de SOIN (RE ghidra gqfc5mff6c, doc §13 / status.md §3.1). UNE CLASSE (nom NATIF).

`IdunBattle.AI.Utilities.HealUtility` (IdunBattle.AI.Utilities.HealUtility$$.ctor ; `UtilityType.Heal=44`). Corps =
`<EvaluateAttackInSteps>d__.MoveNext` (stub `IdunBattle.AI.Utilities.HealUtility$$EvaluateAttackInSteps`, body iter IdunBattle.AI.Utilities.HealUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext) :
    U = (effective / (maxHP + 1)) * W_HEAL * friendSign * bossMod
avec `W_HEAL = 100` (`IdunBattle.AI.Utilities.HealUtility$$.cctor` = Fix64.FromInt(100)), `friendSign = +1` si la
cible est un ALLIE du caster (-1 sinon : soigner un ennemi = utilite negative), `bossMod = 2` si la
cible est un BOSS sinon 1 (`IdunBattle.AI.Utilities.HealUtility$$GetUnitUtilityModifier`).

Le calcul du soin EFFECTIF (`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount` -> `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` -> `IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp`) N'EST PAS ici : c'est de la PREDICTION
(magnitude), pas de l'utilite -> reste dans `engine.predict` (heal_amount/predict_heal_effective).
"""
from __future__ import annotations

from .base import BaseUtility
from .utility_type import UtilityType

W_HEAL = 100   # IdunBattle.AI.Utilities.HealUtility$$.cctor : Fix64.FromInt(100)


class HealUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.HealUtility` (IdunBattle.AI.Utilities.HealUtility$$.ctor ; UtilityType.Heal=44). Corps dans
    `evaluate` (= `<EvaluateAttackInSteps>d__.MoveNext`, body IdunBattle.AI.Utilities.HealUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext)."""
    UTILITY_TYPE = int(UtilityType.Heal)  # 44

    def get_unit_utility_modifier(self, is_boss: bool) -> float:
        """`IdunBattle.AI.Utilities.HealUtility$$GetUnitUtilityModifier` : `bossMod = 2` si la cible est un BOSS,
        sinon 1 (le soin d'un boss compte double)."""
        return 2.0 if is_boss else 1.0

    def evaluate(self, effective_heal, target_max_hp, is_friend: bool, is_boss: bool) -> float:
        # ratio = HealRatio = effective / (maxHP + 1) (le +1 evite la division par zero)
        ratio = effective_heal / (int(target_max_hp) + 1)
        u = ratio * W_HEAL
        if not is_friend:
            u = -u                      # friendSign : soigner un ennemi = utilite negative
        return u * self.get_unit_utility_modifier(is_boss)


HEAL_UTILITY = HealUtility()   # instance enregistree a UtilityType.Heal=44
assert HEAL_UTILITY.UTILITY_TYPE == UtilityType.Heal
