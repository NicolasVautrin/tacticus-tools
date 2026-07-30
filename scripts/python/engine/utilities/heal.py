"""`HealUtility` — utilite de SOIN. UNE CLASSE (nom NATIF). RE re-lue sur le build `rnca9r7q6c` (#27-1212).

`IdunBattle.AI.Utilities.HealUtility` (IdunBattle.AI.Utilities.HealUtility$$.ctor ; `UtilityType.Heal=45`). Corps =
`<EvaluateAttackInSteps>d__.MoveNext` (stub `IdunBattle.AI.Utilities.HealUtility$$EvaluateAttackInSteps`, body iter IdunBattle.AI.Utilities.HealUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext) :
    U = (effective / (maxHP + 1)) * W_HEAL * friendSign * bossMod
avec `W_HEAL = 100` (`IdunBattle.AI.Utilities.HealUtility$$.cctor` = Fix64.FromInt(100)), `friendSign = +1` si la
cible est un ALLIE du caster (-1 sinon : soigner un ennemi = utilite negative), `bossMod = 2` si le
CASTER est un BOSS sinon 1 (`IdunBattle.AI.Utilities.HealUtility$$GetUnitUtilityModifier` — cf. la
docstring de la methode : la fiche disait « la cible », c'est REFUTE au decompile courant).
`effective` = le champ HAUT (`>> 32`) de la struct de 8 octets rendue par
`IdunBattle.Core.Services.DamagePrediction$$PredictHeal` (`CONCAT44(fill, currentHealth)`) — MEME FORME
que le retour de `PredictRepair`. Cote hooks les deux familles ont des decodeurs DISTINCTS, et un seul
est fautif : `readHealEvent` lit la struct INLINE sur ses 8 octets (`+0x08`/`+0x0c` d'un
`ProbableHealEvent` de stride `0x18`) et est SAIN ; `decodeRepairDict` suppose 16 octets / 4 ints et
DEBORDE (backlog #276-r1). Canal de reference malgre tout : le SCALAIRE `pairUtility`, qui ne decode
aucun champ.
⚠ `UtilityType.Heal` vaut **45** sur ce build (`0x2d`, litteral lu dans
`IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromHealEvent`) ;
l'ancienne redaction « Heal=44 » venait d'un build anterieur — l'enum est re-derive, jamais recopie.

Le calcul du soin EFFECTIF (`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount` -> `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` -> `IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp`) N'EST PAS ici : c'est de la PREDICTION
(magnitude), pas de l'utilite -> reste dans `engine.predict` (heal_amount/predict_heal_effective).
"""
from __future__ import annotations

from .base import BaseUtility
from .utility_type import UtilityType

W_HEAL = 100   # IdunBattle.AI.Utilities.HealUtility$$.cctor : Fix64.FromInt(100)


class HealUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.HealUtility` (IdunBattle.AI.Utilities.HealUtility$$.ctor ; UtilityType.Heal=45). Corps dans
    `evaluate` (= `<EvaluateAttackInSteps>d__.MoveNext`, body IdunBattle.AI.Utilities.HealUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext)."""
    UTILITY_TYPE = int(UtilityType.Heal)  # 45 = 0x2d (litteral de CalculateUtilityFromHealEvent)

    def get_unit_utility_modifier(self, is_boss: bool) -> float:
        """`IdunBattle.AI.Utilities.HealUtility$$GetUnitUtilityModifier` : `bossMod = 2` si le **CASTER**
        est un BOSS, sinon `Fix64.One`.

        RE-LU sur le build `rnca9r7q6c` (`...HealUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext`) :
        l'iterateur appelle `UnitExtensions$$IsBoss(case+0x10)`, et `UtilityAttackCase$$ForHealPrediction`
        ecrit `caster` en `+0x10` / `target` en `+0x20` (c'est bien `+0x20` que lit le `GetStat(Health,
        Maximum)` du denominateur). Ghidra nomme d'ailleurs le parametre `caster` dans
        `GetUnitUtilityModifier`. **La fiche `docs/rl/playbook/prediction.md` §9 disait « la cible » —
        REFUTE.** Sans effet numerique sur les mesures faites : en arene `BossUnit` est nul, donc les
        appelants passent `is_boss=False` et le terme est inerte."""
        return 2.0 if is_boss else 1.0

    def evaluate(self, effective_heal, target_max_hp, is_friend: bool, is_boss: bool) -> float:
        # ratio = HealRatio = effective / (maxHP + 1) (le +1 evite la division par zero)
        ratio = effective_heal / (int(target_max_hp) + 1)
        u = ratio * W_HEAL
        if not is_friend:
            u = -u                      # friendSign : soigner un ennemi = utilite negative
        return u * self.get_unit_utility_modifier(is_boss)


HEAL_UTILITY = HealUtility()   # instance enregistree a UtilityType.Heal=45
assert HEAL_UTILITY.UTILITY_TYPE == UtilityType.Heal
