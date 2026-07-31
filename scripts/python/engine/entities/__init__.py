"""`engine.entities` — port des entités/composants natifs `IdunBattle.Entities.*`.
Pour l'instant : UnitContext (état résolu d'unité) + abilities/."""
from __future__ import annotations

from .unit_context import UnitContext
from .effects_state import EffectsState, baked_ability_state
from .effects import BaseEffect, EffectFactory
from .traits_state import TraitsState
from .traits import BaseTrait, TraitFactory
from .stats import (
    StatType, StatPart, StatComponent, FillUpStatComponent,
    ValueModification, ValueOverride, UnitStats, seed_unit_stats,
    native_stat_parts, compare_unit_stats,
)

__all__ = [
    "UnitContext", "EffectsState", "baked_ability_state", "BaseEffect", "EffectFactory",
    "TraitsState", "BaseTrait", "TraitFactory",
    "StatType", "StatPart", "StatComponent", "FillUpStatComponent",
    "ValueModification", "ValueOverride", "UnitStats", "seed_unit_stats",
    "native_stat_parts", "compare_unit_stats",
]
