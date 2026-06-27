"""`engine.entities` — port des entités/composants natifs `IdunBattle.Entities.*`.
Pour l'instant : UnitContext (état résolu d'unité) + abilities/."""
from __future__ import annotations

from .unit_context import UnitContext
from .effects_state import EffectsState
from .effects import BaseEffect, EffectFactory
from .traits_state import TraitsState
from .traits import BaseTrait, TraitFactory

__all__ = [
    "UnitContext", "EffectsState", "BaseEffect", "EffectFactory",
    "TraitsState", "BaseTrait", "TraitFactory",
]
