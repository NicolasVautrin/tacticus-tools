"""`engine.entities.pathfinding` — port FIDÈLE du pathfinding natif
`IdunBattle.Entities.Pathfinding.*` (decompile = vérité, structure 1:1).

Deux moteurs natifs distincts (RE ghidra gqfc5mff6c, cf. docs/rl/playbook-engine.md §18) :

  • ÉNUMÉRATION des tuiles atteignables (= ce que l'IA consomme : aiMovableTiles /
    GetAllValidTargetsFromAllPossibleMovementTiles) = FLOOD-FILL PAR NIVEAUX,
    NON pondéré. 1 pas = 1 niveau ; `range` niveaux de profondeur.
    Chaîne : MovementQuery.GetMovableTilesFor @18109a330 →
    BasePathfinder.GetMovablePositions @180ee25d0 (itérateur @180f27840) +
    WalkPathfinder.IsValidPathNode @180f2ee50.

  • CHEMIN EXACT pondéré (A*) — GenerateBreadthFirstTree @180ee21a0 + WeightCost
    @180f2f120 — sert UNIQUEMENT à GetPathTo (tracer la route). PAS à
    l'énumération IA → non porté ici pour l'instant.

Le graphe de board (adjacence + élévation + walkable) est capté LIVE via le RPC
`boardGraph` (approche A) — cf. board.py.
"""
from __future__ import annotations

from .board import Board
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
]
