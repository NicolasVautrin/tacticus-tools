"""`engine.services` — port FIDÈLE des services natifs `IdunBattle.Core.Services.*` +
`StaticBattleRules.Damage`. Structure 1:1 avec le code live (directive : le Python mirror le
natif, classe→module, méthode→fonction homonyme, VA citées, validable méthode par méthode).

Modules :
  • min_max_damage    — MinMaxDamage (ApplyCap, Avg, Add)
  • static_battle_rules — StaticBattleRules.Damage (GetDamageWithPiercing, GetPiercingRatio)
  • damage_prediction — DamagePrediction (scenario, base-damage perçage/armure, hits, pierce-ratio)
                        + DamagePredictionResult.

À FINIR : PredictAttackRaw (IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw) = l'assembleur qui lit la config d'arme, applique le
spread, multiplie par les coups, et appelle scenario — câble les pièces ci-dessus.
"""
from __future__ import annotations


__all__ = []
