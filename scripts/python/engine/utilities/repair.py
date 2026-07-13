"""`RepairedAmountUtility` — utilite de REPARATION des unites MECANIQUES (RE ghidra gqfc5mff6c, doc §13).

`IdunBattle.AI.Utilities.RepairedAmountUtility` (ctor @1810e0940 ; `UtilityType.RepairedAmount=47`).
Corps = `<EvaluateRepairInSteps>d__.MoveNext` (stub `EvaluateRepairInSteps @1810e06f0`, body iter
@1810e45b0) — DEUX termes (Health id 5 + Armor id 4) :
    U = (fill_hp/(maxHP+1) * W_HP + fill_armor/(maxArmor+1) * W_ARMOR) * bossMod
avec `W_HP = 100`, `W_ARMOR = 50` (`RepairedAmountUtility.cctor @1810e08b0` : Fix64.FromInt(100)/(0x32)),
`bossMod = 2` si BOSS sinon 1 (`GetUnitUtilityModifier @1810e0820`). Denominateurs +1 = `GetMaxHealth
@1810e0760` (evite /0). PAS de friendSign (contrairement au soin) : on ne repare QUE ses machines.

La PREDICTION du remplissage (`DamagePrediction.PredictRepair @181038280` -> `MaxFillUp @180f9b790` x2)
= magnitude, PAS utilite -> reste dans `engine.predict` (repair_amount / predict_repair_effective).
"""
from __future__ import annotations

from .base import BaseUtility
from .utility_type import UtilityType

W_HP = 100      # RepairedAmountUtility.cctor @1810e08b0 : W[0] = Fix64.FromInt(100)
W_ARMOR = 50    # RepairedAmountUtility.cctor @1810e08b0 : W[1] = Fix64.FromInt(0x32)


class RepairedAmountUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.RepairedAmountUtility` (ctor @1810e0940 ; UtilityType.RepairedAmount=47).
    Corps dans `evaluate` (= `<EvaluateRepairInSteps>d__.MoveNext`, body @1810e45b0)."""
    UTILITY_TYPE = int(UtilityType.RepairedAmount)  # 47

    def get_unit_utility_modifier(self, is_boss: bool) -> float:
        """`RepairedAmountUtility.GetUnitUtilityModifier @1810e0820` : `bossMod = 2` si BOSS sinon 1."""
        return 2.0 if is_boss else 1.0

    def evaluate(self, fill_hp, target_max_hp, fill_armor, target_max_armor, is_boss: bool) -> float:
        # GetMaxHealth @1810e0760 : denom = GetStat(Maximum)+1 (le +1 evite la division par zero)
        term_hp = fill_hp / (int(target_max_hp) + 1) * W_HP
        term_armor = fill_armor / (int(target_max_armor) + 1) * W_ARMOR
        return (term_hp + term_armor) * self.get_unit_utility_modifier(is_boss)


REPAIR_UTILITY = RepairedAmountUtility()   # instance enregistree a UtilityType.RepairedAmount=47
assert REPAIR_UTILITY.UTILITY_TYPE == UtilityType.RepairedAmount
