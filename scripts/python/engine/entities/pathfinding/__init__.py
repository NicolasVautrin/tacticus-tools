"""`engine.entities.pathfinding` — port FIDÈLE du pathfinding natif
`IdunBattle.Entities.Pathfinding.*` (decompile = vérité, structure 1:1).

Deux moteurs natifs distincts (RE ghidra gqfc5mff6c, cf. docs/rl/playbook-engine.md §18) :

  • ÉNUMÉRATION des tuiles atteignables (= ce que l'IA consomme : aiMovableTiles /
    GetAllValidTargetsFromAllPossibleMovementTiles) = FLOOD-FILL PAR NIVEAUX,
    NON pondéré. 1 pas = 1 niveau ; `range` niveaux de profondeur.
    Chaîne : IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor →
    IdunBattle.Entities.Pathfinding.BasePathfinder$$GetMovablePositions (itérateur IdunBattle.Entities.Pathfinding.BasePathfinder.u003CGetMovablePositionsu003Ed__23$$MoveNext) +
    IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidPathNode.

  • CHEMIN EXACT pondéré (A*) — IdunBattle.Entities.Pathfinding.BasePathfinder$$GenerateBreadthFirstTree + IdunBattle.Entities.Pathfinding.WalkPathfinder$$WeightCost — sert UNIQUEMENT à GetPathTo (tracer la route). PAS à
    l'énumération IA → non porté ici pour l'instant.

Le graphe de board (adjacence + élévation + walkable) est capté LIVE via le RPC
`boardGraph` (approche A) — cf. board.py.
"""
from __future__ import annotations

from .board import Board
from .tile_blocking import make_can_continue, tile_blocks_entering
from .walk_pathfinder import (
    get_movable_positions,
    get_reachable_levels,
    is_valid_path_node,
)

__all__ = [
    "Board",
    "get_movable_positions",
    "get_reachable_levels",
    "is_valid_path_node",
    "make_can_continue",
    "tile_blocks_entering",
]
