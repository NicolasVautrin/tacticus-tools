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
`MaxDistanceToUnitTileUtility.<d__2>.IdunBattle.AI.Utilities.MaxDistanceToUnitTileUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`) est parkée dans docs/rl/playbook-engine.md §13.3.

cf. docs/rl/playbook-engine.md §1.5 + §7 + §13.
"""
from __future__ import annotations

import os

from .weights import Weights
from .utilities import tile_composite
from .utilities.tile import terrain_tile_effects, apply_tile_attributes
from .utilities.move import MIN_DIST_UTILITY, UNIT_MOVEMENT  # noqa: F401 (UNIT_MOVEMENT = record membership)


def best_move_faithful(tiles: list, elev_by_pos: dict, enemy_positions: list, wt: Weights,
                       steppable_by_pos: dict | None = None,
                       pathdist_by_pos: dict | None = None,
                       is_temporary_by_pos: dict | None = None,
                       effects_by_pos: dict | None = None,
                       terrain_by_pos: dict | None = None,
                       leaf_ctx: dict | None = None,
                       mindist_case=None) -> tuple:
    """Move scoring FIDÈLE — décideur **UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(16)**
    (composition LUE runtime, doc §13.8/13.11). `U(tuile) = tile_composite(Tile(7)) + wMin×d`.
    PAS de `MaxDistanceToEnemies` (dans AUCUN composite) ni `MaxDistanceToUnitTile` (seulement
    UnitMovementFromTemporary).

    ⚠ `d` = distance de CHEMIN (pathfinding), PAS hex (RE `GetMinDistanceToEnemy`, doc §13.12) :
    si `pathdist_by_pos` (RPC `pathDistToEnemies`) est fourni, on l'utilise ; sinon fallback hex
    (approximation). `elev_by_pos` = `{(col,row): elevation}` (RPC tileMeta = BOARD ENTIER) ; max/min
    d'élévation calculés sur TOUT le board (= `IdunBattle.AI.Utilities.ElevationUtility$$LoadRelevantTileElevations`, verdict case-37 :
    board-singleton, PAS le candidate-set). `is_temporary_by_pos` = `{(col,row): bool}`
    (tileMeta.isTemporary) → leaf TemporaryTile(13) (-10000 sur tuile temporaire). `terrain_by_pos` =
    `{(col,row): tileDefId}` (boardGraph) → covers HÉBERGÉS par le terrain sommés par TileEffects(9)
    (DryBush→LightCover, Loop2 ; case-37). `leaf_ctx` = le dict `ctx` PAR-DÉCISION des feuilles Tile(7)
    (`unit_triggered_abilities` + `friend_positions` → feuille TriggeredAbilities(2), case-36).
    `mindist_case` = le `UtilityMovementCase` (engine.utilities.move) que le générateur natif passe à
    la feuille MinDist(16) : porte ses QUATRE gates d'entrée (`case.Unit == null`, `IsNonAttacking`,
    `case.ClosestEnemy == null`, `!UnitCanBeDamaged`) — sans lui la feuille reste non gatée (#236).
    Renvoie ((col,row)|None, util).
    """
    if not enemy_positions:
        return None, None
    coords = [(t["col"], t["row"]) for t in tiles]
    # Elevation(8) : min/max sur le BOARD ENTIER (`elev_by_pos` = toutes les tuiles tileMeta), pas les
    # candidates — sinon LowestElevation(-5)/HighestElevation(+10) s'appliquent à un faux extrême du
    # candidate-set (case-37 : 909 s4 (3,2)@elev2 = min des candidats mais PAS du board (min=1) -> -5 indu).
    board_elevs = [e for e in elev_by_pos.values() if e is not None]
    emax, emin = (max(board_elevs), min(board_elevs)) if board_elevs else (None, None)
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
        # feuille TileEffects(9) : effets DYNAMIQUES (tileMeta = Loop1 : Thorns/Fire/...) + covers HÉBERGÉS
        # par le terrain (Loop2 : DryBush->LightCover). case-37.
        _effs = list(effects_by_pos.get(c) or []) if effects_by_pos else []
        if terrain_by_pos:
            _effs += terrain_tile_effects(terrain_by_pos.get(c), _effs)   # #155 : `_effs` = canal dyn.
        if _effs:
            meta["effects"] = _effs
        # Attributs de TUILE remontés par `tileMeta` (isTerritory / effects[].effectType) —
        # transportés par le `leaf_ctx` sous forme de cartes par-position (cf. `apply_tile_attributes`).
        apply_tile_attributes(meta, c, leaf_ctx)
        # UnitMovement(6) = Tile(7) [canal tile] + MinDistanceToClosestEnemy(16) [canal mouvement].
        # MinDist gère lui-même distance CHEMIN (si dispo) vs hex (fallback) — corps dans la feuille.
        tile_u = 0.0 if tile_off else tile_composite(c, meta, leaf_ctx or {}, wt)
        mindist_u = MIN_DIST_UTILITY.evaluate_movement(c, enemy_positions, wt, pathdist_by_pos,
                                                       case=mindist_case)
        u = tile_u + mindist_u
        if bu is None or u > bu:
            best, bu = c, u
    return best, bu
