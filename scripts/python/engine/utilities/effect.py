"""`AddedEffectUtility` — utilite de POSE D'EFFET (RE ghidra gqfc5mff6c, doc §13). Poids PLAT par type
d'effet, 100% pilote par le BattleConfiguration (PAS de magnitude : un DoT/reduction passe par le DEGAT).

`IdunBattle.AI.Utilities.AddedEffectUtility` (ctor @1810ee410 ; `UtilityType.AddedTileEffects=45` = la
categorie de poids BC `Utilities.Default[AddedTileEffects]` lue par cette utilite). Corps =
`<EvaluateAttackInSteps>d__.MoveNext` (stub `EvaluateAttackInSteps @1810ee3a0`, body iter @1810f6e70) :
    si la cible a DEJA l'effet (EntityExtensions.HasEffect)  -> U = 0
    sinon  U = Weight[name] + signe * Weight["Unit_on_" + name]
           name  = Enum.ToString(EffectType)  (ex. "Fire", "SpiderWeb", "Ice")
           signe = -1 si la cible est un ALLIE du caster (UnitExtensions.IsFriend), sinon +1
Weight[...] = `BaseUtility.GetUtilityValue @1810cd3c0` (`get_utility_value` en base ; absent -> 0).
Ex. AddedTileEffects Fire=10 / Unit_on_Fire=15 : Fire sous un ENNEMI = 10+15 = 25 ; sous un ALLIE = 10-15 = -5.

NB `UtilityType.AttackTargetWithEffect=42` est une AUTRE utilite (preference de CIBLAGE : viser une cible
qui a deja un effet), a ne pas confondre avec la POSE d'effet (AddedTileEffects=45) que porte cette classe.
"""
from __future__ import annotations

from .base import BaseUtility
from .utility_type import UtilityType

EFFECT_UTILITY_PREFIX = "Unit_on_"   # AddedEffectUtility String.Concat(prefix, name) @1810f6e70 ;
                                     # confirme par les cles BC AddedTileEffects (Fire / Unit_on_Fire)


class AddedEffectUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.AddedEffectUtility` (ctor @1810ee410 ; UtilityType.AddedTileEffects=45).
    Corps dans `evaluate` (= `<EvaluateAttackInSteps>d__.MoveNext`, body @1810f6e70)."""
    UTILITY_TYPE = 45   # UtilityType.AddedTileEffects (categorie de poids BC lue par cette utilite)

    def evaluate(self, effect_name: str, target_has_effect: bool, is_friend: bool, weights: dict) -> float:
        if target_has_effect:
            return 0.0                                          # EntityExtensions.HasEffect -> U = 0
        base = self.get_utility_value(weights, effect_name)     # Weight[name]
        prefixed = self.get_utility_value(weights, EFFECT_UTILITY_PREFIX + effect_name)
        if is_friend:
            prefixed = -prefixed                                # signe = -1 si cible alliee
        return float(base + prefixed)


ADDED_EFFECT_UTILITY = AddedEffectUtility()   # instance a UtilityType.AddedTileEffects=45
assert ADDED_EFFECT_UTILITY.UTILITY_TYPE == UtilityType.AddedTileEffects
