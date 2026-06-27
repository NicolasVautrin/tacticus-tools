"""`engine.entities.abilities` — port `IdunBattle.Entities.Abilities.*` + `AbilityConfiguration`."""
from __future__ import annotations

from .ability_configuration import AbilityConfiguration
from .active_ability import AActiveAbility, NormalAttackAbility

__all__ = ["AbilityConfiguration", "AActiveAbility", "NormalAttackAbility"]
