"""Scoring de MOUVEMENT — repositionnement pur (le profil natif « MovementSuggestion », §1.5).

Le décideur de move PUR est **UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(16)**
(composition LUE runtime via `UtilitiesDatabase.InitializeUtilities._composedUtilityLookup`,
RE ghidra gqfc5mff6c, doc §13.8/13.11) : `U(tuile) = tile_composite(Tile(7)) + wMin × d`, avec
wMin = `MinDistanceToClosestEnemy.PerTileDistance` (-100) et `d` = distance de CHEMIN (pathfinding,
`GetMinDistanceToEnemy`, doc §13.12), PAS hex.

On compare l'ARGMAX (la tuile choisie), pas la valeur d'utilité exacte → l'arithmétique Fix64
n'a pas à être répliquée (cf. doc §6). NB : `MaxDistanceToEnemies` n'est dans AUCUN composite et
`MaxDistanceToUnitTile` n'appartient qu'à `UnitMovementFromTemporary(5)` (move « depuis une tuile
temporaire ») — non porté ; sa formule RE'd `A-(A-B)/d` (A=FarthestTile 700, B=ClosestTile 400,
`MaxDistanceToUnitTileUtility.<d__2>.MoveNext @1810fdeb0`) est parkée dans docs/rl/playbook-engine.md §13.3.

cf. docs/rl/playbook-engine.md §1.5 + §7 + §13.
"""
from __future__ import annotations

import os

from .weights import Weights
from .utilities import tile_composite
from .utilities.move import MIN_DIST_UTILITY, UNIT_MOVEMENT  # noqa: F401 (UNIT_MOVEMENT = record membership)


def best_move_faithful(tiles: list, elev_by_pos: dict, enemy_positions: list, wt: Weights,
                       steppable_by_pos: dict | None = None,
                       pathdist_by_pos: dict | None = None,
                       is_temporary_by_pos: dict | None = None,
                       effects_by_pos: dict | None = None,
                       leaf_ctx: dict | None = None) -> tuple:
    """Move scoring FIDÈLE — décideur **UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(16)**
    (composition LUE runtime, doc §13.8/13.11). `U(tuile) = tile_composite(Tile(7)) + wMin×d`.
    PAS de `MaxDistanceToEnemies` (dans AUCUN composite) ni `MaxDistanceToUnitTile` (seulement
    UnitMovementFromTemporary).

    ⚠ `d` = distance de CHEMIN (pathfinding), PAS hex (RE `GetMinDistanceToEnemy`, doc §13.12) :
    si `pathdist_by_pos` (RPC `pathDistToEnemies`) est fourni, on l'utilise ; sinon fallback hex
    (approximation). `elev_by_pos` = `{(col,row): elevation}` (RPC tileMeta) ; max/min sur les
    tuiles candidates (= `LoadRelevantTileElevations`). `is_temporary_by_pos` = `{(col,row): bool}`
    (tileMeta.isTemporary) → leaf TemporaryTile(13) (-10000 sur tuile temporaire). `leaf_ctx` = le dict
    `ctx` PAR-DÉCISION des feuilles Tile(7) (`unit_triggered_abilities` + `friend_positions` → feuille
    TriggeredAbilities(2), case-36). Renvoie ((col,row)|None, util).
    """
    if not enemy_positions:
        return None, None
    coords = [(t["col"], t["row"]) for t in tiles]
    elevs = [elev_by_pos.get(c) for c in coords]
    elevs = [e for e in elevs if e is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    tile_off = os.environ.get("ENGINE_TILE_OFF") == "1"   # diagnostic : MinDist seul (Tile=0)
    best = None
    bu = None
    for c in coords:
        e = elev_by_pos.get(c)
        meta: dict = {"elevation": e, "elevation_max": emax, "elevation_min": emin} \
            if e is not None else {}
        if steppable_by_pos and c in steppable_by_pos:
            meta["steppable"] = steppable_by_pos[c]
        if is_temporary_by_pos and c in is_temporary_by_pos:
            meta["is_temporary"] = is_temporary_by_pos[c]
        if effects_by_pos and c in effects_by_pos:
            meta["effects"] = effects_by_pos[c]   # feuille TileEffects (Thorns/Fire/... via tileMeta)
        # UnitMovement(6) = Tile(7) [canal tile] + MinDistanceToClosestEnemy(16) [canal mouvement].
        # MinDist gère lui-même distance CHEMIN (si dispo) vs hex (fallback) — corps dans la feuille.
        tile_u = 0.0 if tile_off else tile_composite(c, meta, leaf_ctx or {}, wt)
        mindist_u = MIN_DIST_UTILITY.evaluate_movement(c, enemy_positions, wt, pathdist_by_pos)
        u = tile_u + mindist_u
        if bu is None or u > bu:
            best, bu = c, u
    return best, bu
