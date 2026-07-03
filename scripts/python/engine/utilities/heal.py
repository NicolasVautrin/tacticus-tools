"""`HealUtility` — utilite de SOIN (RE ghidra gqfc5mff6c, doc §13 / status.md §3.1). UNE CLASSE (nom NATIF).

`IdunBattle.AI.Utilities.HealUtility` (ctor @1810cfd80 ; `UtilityType.Heal=44`). Corps =
`<EvaluateAttackInSteps>d__.MoveNext` (stub `EvaluateAttackInSteps @1810cfc10`, body iter @1810e16f0) :
    U = (effective / (maxHP + 1)) * W_HEAL * friendSign * bossMod
avec `W_HEAL = 100` (`HealUtility.cctor @1810cfd10` = Fix64.FromInt(100)), `friendSign = +1` si la
cible est un ALLIE du caster (-1 sinon : soigner un ennemi = utilite negative), `bossMod = 2` si la
cible est un BOSS sinon 1 (`GetUnitUtilityModifier @1810cfc80`).

Le calcul du soin EFFECTIF (`HealAbility.HealAmount @180e345b0` -> `DamagePrediction.PredictHeal
@181037180` -> `FillUpStatComponent.MaxFillUp @180f9b790`) N'EST PAS ici : c'est de la PREDICTION
(magnitude), pas de l'utilite -> reste dans `engine.predict` (heal_amount/predict_heal_effective).
"""
from __future__ import annotations

from .base import BaseUtility
from .utility_type import UtilityType

W_HEAL = 100   # HealUtility.cctor @1810cfd10 : Fix64.FromInt(100)


class HealUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.HealUtility` (ctor @1810cfd80 ; UtilityType.Heal=44). Corps dans
    `evaluate` (= `<EvaluateAttackInSteps>d__.MoveNext`, body @1810e16f0)."""
    UTILITY_TYPE = 44   # UtilityType.Heal

    def get_unit_utility_modifier(self, is_boss: bool) -> float:
        """`HealUtility.GetUnitUtilityModifier @1810cfc80` : `bossMod = 2` si la cible est un BOSS,
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
