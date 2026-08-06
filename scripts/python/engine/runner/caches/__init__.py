"""Les CACHES du moteur natif (`IdunBattleLogic.Core.Services.Caches.*`).

Feuille : ce paquet n'importe aucun sibling de `engine.runner` -- il porte des structures de
donnees, pas de la logique de bataille. C'est ce qui le rend importable depuis le dispatch de
triggers sans creer de cycle.
"""
from __future__ import annotations

from .ability_and_effect_cache import (AbilityAndEffectCache, SortedEffect, SortedTriggered,
                                       SortedTriggeredAbility, add_sorted)

__all__ = ["AbilityAndEffectCache", "SortedEffect", "SortedTriggered", "SortedTriggeredAbility",
           "add_sorted"]
