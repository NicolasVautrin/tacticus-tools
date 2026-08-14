"""Noeuds SELECTEUR du DSL = famille `TargetsSelector.Select` (kind S) : selecteurs d'unites, de
tuiles (domaine TILE = ids), et accesseurs de tuile/entite/sujet.

Mirror du namespace natif `IdunBattle.Entities.Selectors` : les concrets vivent ici, a cote de leurs
freres `entities/{abilities,triggers,formulas,behaviours,effects}` ; la base `TargetsSelector`
(= `IdunBattle.DSL`) reste dans `dsl/base.py`. Construits via la facade `DSLFactory` (`dsl/nodes.py`).
Les selecteurs de TUILES lisent `ctx.board` (entities/pathfinding : `neighbours`/`id_at`/`walkable`).

DECOUPAGE (le fichier faisait 1563 lignes ; aucune logique n'a change, seules les
tranches ont bouge) -- graphe de dependances ACYCLIQUE, chaque fleche va vers le bas :

    _shared      helpers de normalisation (`_entity_pos`, `_tile_positions`)
       ^
       |-- units       domaine UNITE + algebre d'ensembles
       |-- tiles       domaine TUILE (ids ; lit `ctx.board`)
       |-- geometry    geometrie hex par direction + noeuds tardifs
           accessors   slots de role du contexte (aucune dependance)
       ^
       |-- composites  les noeuds qui assemblent PLUSIEURS tranches

CE MODULE RE-EXPORTE TOUT : `from ..entities.selectors import X` continue de
fonctionner a l'identique pour les 145 sites d'import du depot. Ajouter un noeud =
le poser dans sa tranche ET l'ajouter au re-export ci-dessous."""

from ._shared import (  # noqa: F401
    _entity_pos, _tile_positions,
)

from .units import (  # noqa: F401
    SurroundingUnits, AdjacentEnemies, AdjacentUnits, Enemies, Damageable, And, Sub, Union,
    UnitsFromFaction, UnitSet, Filter, UnitsDirectlyBehind, Friends, Units,
    UnitsOnTilesWithEffect, Tiles, First, Unique, UnitsWithIds, UnitsWithTrait, UnitsWithRarity,
    UnitsWithoutTrait, UnitsWithoutRangedWeapons, UnitsWithRangedWeapons, hero_units, AllDeadUnits,
    AllDeadOrResurrectedUnits, MechanicalUnits,
    non_steppable_or_object_units, units_with_traits, NormalUnits, UnitsDefeatedBy,
    AdjacentFriends, SurroundingEnemies, SurroundingFriends, SortByFormula, SortByDistance,
    Alive, UnitsThatCanHaveActiveAbilityReset, Unobscured, UnitsDamagedThisPhase,
    ValidNormalAttackTargets, SortUnitsByDamageUtility,
    UnitsAffectedByHealType, Healable, Repairable, UnitsWithEffectsOfType, UnitsWithNegativeEffects,
)

from .tiles import (  # noqa: F401
    Caster, AllUnits, AllAliveUnits, AllTiles, Children, ChildrenOf, Parent, LastUnitAttackedBy, AdjacentTiles,
    TileUnique,
    CanAddUnit, TileIntersect, MovableTilesInRange, tiles_unit_can_move_to_charge_target,
    FilterTilesIfCanAttackTargetTileFrom, SortTilesByUtility, PreviousTile,
    TileBehindTargetFromSourceDirection, TileBehindFilled,
    TilesWithoutPowerUps, SafestTiles, unit_is_power_up,
)

from .accessors import (  # noqa: F401
    CasterTile, TargetTile, FixedTile, FixedTiles, FixedTileIds, OwnerTile, Subject, Actor, Target,
    ActiveTarget, SurroundingTiles, _center_pos, Owner, SelectTile,
)

from .geometry import (  # noqa: F401
    neighbour_at, TilesInTriangleShape, ThreeTileUnitSpawnShape, TileFromVector, Walkable,
    DirectionTo,
    Blocking, SortReverse, SortByRow,
    TilesOnSameElevation,
    EntitiesWithoutEffects, EntitiesWithAnyEffect, PickFirstN, PickRandomly, Randomize, Otherwise,
    TilesBehindInLine, EdgeTilesByDirection, EdgeTiles, CenterTiles,
    FilterContinuous, UnitsWithVisualId, UnitsWithId, Cache, Entity, Nothing, Null, SelectIf,
    AtIndex, ConditionalSelector,
    EffectSource, EffectFromOwner, EffectsFromUnitSource, EffectsOfUnits, OwnerOfEffect,
)

from .pathing import (  # noqa: F401
    Nearest, ClosestPositionToTarget,
)

from .valid_targets import (  # noqa: F401
    UnitsWithAnyValidTarget, HasAnyValidTarget,
)

from .composites import (  # noqa: F401
    get_spawn_tile_selector, adjacent_units, attackable_enemies, random_adjacent_free_tile,
)

__all__ = [
    "_entity_pos", "_tile_positions", "SurroundingUnits", "AdjacentEnemies", "AdjacentUnits",
    "Enemies", "Damageable", "And", "Sub", "Union", "UnitsFromFaction", "UnitSet", "Filter",
    "UnitsDirectlyBehind", "Friends", "Units", "UnitsOnTilesWithEffect", "Tiles", "First",
    "Unique", "UnitsWithIds", "UnitsWithTrait", "UnitsWithRarity", "UnitsWithoutTrait",
    "UnitsWithoutRangedWeapons",
    "UnitsWithRangedWeapons", "hero_units",
    "AllDeadUnits", "AllDeadOrResurrectedUnits", "MechanicalUnits",
    "non_steppable_or_object_units", "NormalUnits", "UnitsDefeatedBy", "AdjacentFriends",
    "SurroundingEnemies", "SurroundingFriends", "SortByFormula", "SortByDistance", "Alive",
    "UnitsThatCanHaveActiveAbilityReset", "Unobscured", "UnitsDamagedThisPhase",
    "ValidNormalAttackTargets", "SortUnitsByDamageUtility",
    "UnitsAffectedByHealType", "Healable", "Repairable", "UnitsWithEffectsOfType",
    "UnitsWithNegativeEffects",
    "Owner", "PickRandomly", "Randomize",
    "Caster", "AllUnits", "AllAliveUnits", "AllTiles", "Children", "ChildrenOf",
    "Parent", "LastUnitAttackedBy", "AdjacentTiles", "TileUnique", "CanAddUnit",
    "TileIntersect", "MovableTilesInRange", "tiles_unit_can_move_to_charge_target",
    "FilterTilesIfCanAttackTargetTileFrom",
    "CasterTile", "TargetTile", "FixedTile", "FixedTiles", "FixedTileIds", "OwnerTile", "Subject",
    "SelectTile", "Actor",
    "Target", "ActiveTarget", "SurroundingTiles", "_center_pos", "neighbour_at",
    "TilesInTriangleShape", "ThreeTileUnitSpawnShape", "TileFromVector", "Walkable", "Blocking",
    "DirectionTo", "SortReverse", "SortByRow",
    "TilesOnSameElevation",
    "EntitiesWithoutEffects", "EntitiesWithAnyEffect", "PickFirstN", "Otherwise",
    "TilesBehindInLine", "FilterContinuous", "UnitsWithVisualId", "UnitsWithId", "Cache",
    "Entity", "Nothing", "Null", "SelectIf", "AtIndex", "ConditionalSelector",
    "TileBehindTargetFromSourceDirection", "TileBehindFilled", "EffectSource", "EffectFromOwner",
    "EdgeTiles", "CenterTiles", "TilesWithoutPowerUps", "SafestTiles", "unit_is_power_up",
    "EffectsFromUnitSource", "EffectsOfUnits",
    "OwnerOfEffect", "get_spawn_tile_selector", "adjacent_units", "attackable_enemies",
    "random_adjacent_free_tile",
    "SortTilesByUtility", "PreviousTile",
    "Nearest", "ClosestPositionToTarget",
    "UnitsWithAnyValidTarget",
]
