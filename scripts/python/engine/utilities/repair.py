"""`RepairedAmountUtility` — utilite de REPARATION des unites MECANIQUES (RE ghidra rnca9r7q6c, #45d).

`IdunBattle.AI.Utilities.RepairedAmountUtility` (IdunBattle.AI.Utilities.RepairedAmountUtility$$.ctor ; `UtilityType.RepairedAmount=47`).
Corps = `<EvaluateRepairInSteps>d__.MoveNext` (stub `IdunBattle.AI.Utilities.RepairedAmountUtility$$EvaluateRepairInSteps`, body iter
IdunBattle.AI.Utilities.RepairedAmountUtility.u003CEvaluateRepairInStepsu003Ed__2$$MoveNext) — UN SEUL yield, UN SEUL terme :
    U = fill_hp / (maxHP + 1) * W_HP * bossMod
`fill_hp` = le champ `fillUp` de la `RepairPredictionResult` (`Nullable` a case+0xdc, moitie HAUTE
du qword). Denominateur `+1` = `IdunBattle.AI.Utilities.RepairedAmountUtility$$GetMaxHealth`
(`GetStat(target, Health=5, Maximum=2) + 1` — evite /0 ; branche BOSS = constante de config, cf.
RESIDU). `bossMod = 2` si BOSS sinon `Fix64.One`
(`IdunBattle.AI.Utilities.RepairedAmountUtility$$GetUnitUtilityModifier`). PAS de friendSign
(contrairement au soin) : on ne repare QUE ses machines.

RESIDU -- W_ARMOR est de la DONNEE MORTE sur ce build. `IdunBattle.AI.Utilities.RepairedAmountUtility$$.cctor`
ecrit bien deux poids (`W[0] = Fix64.FromInt(100)` a statics+0, `W[1] = Fix64.FromInt(0x32=50)` a
statics+8), mais les xrefs du bloc statique sont EXHAUSTIFS : le `.cctor` (2 ecritures), le
`MoveNext` (2 lectures : le check cctor-done, puis `**(statics+0xb8)` = W[0] SEUL) et
`UtilitiesDatabase.<InitializeUtilities>b__18_24`. Aucun lecteur de `W[1]`. Symetriquement,
`IdunBattle.Core.Services.DamagePrediction$$PredictRepair` n'appelle `MaxFillUp` qu'UNE fois, sur
le composant Health (meme triplet que `GetFillUpStatComponent(unit, 5)`), et rend une struct de
8 octets. Un port a deux termes surevaluerait la reparation des que la cible aurait de l'Armor
manquante. (Inerte dans tout montage runner mesure : `observeBattle` rend armor = armorMax = 0.)

La PREDICTION du remplissage (`PredictRepair` -> `MaxFillUp`) = magnitude, PAS utilite -> reste dans
`engine.predict` (repair_amount / repair_amount_weapon / predict_repair_effective).
"""
from __future__ import annotations

from .base import BaseUtility
from .utility_type import UtilityType

W_HP = 100      # IdunBattle.AI.Utilities.RepairedAmountUtility$$.cctor : W[0] = Fix64.FromInt(100)
# W[1] = Fix64.FromInt(0x32) est ECRIT par le cctor mais AUCUN lecteur ne l'atteint (xrefs
# exhaustifs, cf. docstring). Conserve en commentaire pour que le prochain lecteur du cctor
# n'en re-deduise pas un second terme.


class RepairedAmountUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.RepairedAmountUtility` (IdunBattle.AI.Utilities.RepairedAmountUtility$$.ctor ; UtilityType.RepairedAmount=47).
    Corps dans `evaluate` (= `<EvaluateRepairInSteps>d__.MoveNext`, body IdunBattle.AI.Utilities.RepairedAmountUtility.u003CEvaluateRepairInStepsu003Ed__2$$MoveNext)."""
    UTILITY_TYPE = int(UtilityType.RepairedAmount)  # 48

    def get_unit_utility_modifier(self, is_boss: bool) -> float:
        """`IdunBattle.AI.Utilities.RepairedAmountUtility$$GetUnitUtilityModifier` : `bossMod = 2` si BOSS sinon 1."""
        return 2.0 if is_boss else 1.0

    def evaluate(self, fill_hp, target_max_hp, is_boss: bool) -> float:
        # IdunBattle.AI.Utilities.RepairedAmountUtility$$GetMaxHealth : denom = GetStat(Maximum)+1 (le +1 evite la division par zero)
        return fill_hp / (int(target_max_hp) + 1) * W_HP * self.get_unit_utility_modifier(is_boss)


REPAIR_UTILITY = RepairedAmountUtility()   # instance enregistree a UtilityType.RepairedAmount=47
assert REPAIR_UTILITY.UTILITY_TYPE == UtilityType.RepairedAmount
