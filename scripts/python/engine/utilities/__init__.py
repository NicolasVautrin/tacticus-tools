"""engine.utilities — réimplémentation FIDÈLE des leaf-utilities natives `IdunBattle.AI.Utilities`,
UNE CLASSE `*Utility` par `UtilityType` (nom natif), dont `evaluate(...)` porte le corps de son
`*Utility.<Evaluate*InSteps>d__N.MoveNext` (ghidra gqfc5mff6c) + poids `BattleConfiguration.Utilities`.

Le composite à scorer (Damage=35, Tile=7) = INSTANCE `ComposedUtility` (SOMME de ses feuilles ; ce ne
sont PAS des classes dédiées). La MEMBERSHIP exacte est LUE À L'EXÉCUTION (RPC `dumpComposedUtility`,
doc §13.8) — pas devinée. cf. docs/rl/playbook-engine.md §13.7 / §13.8 / §13.9.

Base + enum : `base.py` (BaseUtility/ComposedUtility), `utility_type.py` (enum UtilityType, dump.cs).
Wrappers minces `tile_composite`/`damage_composite` conservés pour les appelants existants.
"""
from __future__ import annotations

from .base import BaseUtility, ComposedUtility  # noqa: F401
from .utility_type import UtilityType  # noqa: F401
from .damage import (  # noqa: F401
    damage_composite, DamageUtility, KillUnitUtility, OverkillUnitUtility, DAMAGE_UTILITY)
from .tile import (  # noqa: F401
    tile_composite, TILE_LEAVES, TILE_LEAF_IDS, TILE_UTILITY,
    sort_tiles_by_utility, first_tile_by_utility)
from .move import MinDistanceToClosestEnemyUtility, MIN_DIST_UTILITY, UNIT_MOVEMENT  # noqa: F401
from .heal import HealUtility, HEAL_UTILITY  # noqa: F401
from .repair import RepairedAmountUtility, REPAIR_UTILITY  # noqa: F401
from .effect import AddedEffectUtility, ADDED_EFFECT_UTILITY, EFFECT_UTILITY_PREFIX  # noqa: F401
