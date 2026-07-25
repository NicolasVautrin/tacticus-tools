"""WalkPathfinder — port FIDÈLE du pathfinder de marche natif
(`IdunBattle.Entities.Pathfinding.WalkPathfinder` + `BasePathfinder
.GetMovablePositions`). RE ghidra gqfc5mff6c (cf. docs/rl/playbook-engine.md §18).

ÉNUMÉRATION des tuiles atteignables = flood-fill PAR NIVEAUX (1 pas = 1 niveau,
`range` niveaux), SANS coût accumulé (le IdunBattle.Entities.Pathfinding.WalkPathfinder$$WeightCost ne sert qu'à
GetPath A*, pas à l'énumération). `IdunBattle.Entities.Pathfinding.BasePathfinder$$GetMovablePositions
(itérateur IdunBattle.Entities.Pathfinding.BasePathfinder.u003CGetMovablePositionsu003Ed__23$$MoveNext) fait un BFS niveau-par-niveau via `NodesInNextLevel`,
profondeur décrémentée de 1 par niveau.

PRÉDICAT D'ARÊTE (`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidPathNode) — peut-on entrer
sur `to` depuis `from` :
  1. IsWalkable(to)                                 (IdunBattle.Entities.TileExtensions$$IsWalkable)
  2. |elev(to) - elev(from)| <= 1                   (IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsReachableElevationDifference)
     (exception téléporteurs : non modélisée ici — board basique sans téléporteur)
  3. !UnitIsBlockedByEnemyUnit(to, unit)            (IdunBattle.Entities.Pathfinding.WalkPathfinder$$UnitIsBlockedByEnemyUnit : un ENNEMI sur la
     tuile bloque le passage ; un ALLIÉ laisse passer — sauf trait 0x1b non modélisé)

TUILE D'ARRÊT valide (`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidContinuePathTile :
`GetTileBlockingReasons == 0`) = tuile NON occupée (ni allié ni ennemi). On peut
TRAVERSER un allié mais pas s'y arrêter. Le start (tuile courante) est exclu du set.

⚠ `GetEffectiveDepth` (hazard tile → `Min(1, depth)`, IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetEffectiveDepth) non encore
plombé (pas de tuile-hazard sur board basique) — TODO si une feuille hazard apparaît.

API : `occupants` = dict {tile_id -> team_of_occupant}. `moving_team` = team de
l'unité qui bouge. Aucun RVA, aucun appel natif — pur calcul depuis le Board capté.
"""
from __future__ import annotations

from .board import Board


def is_valid_path_node(
    board: Board, from_id: int, to_id: int,
    occupants: dict, moving_team: int,
) -> bool:
    """Peut-on TRAVERSER vers `to_id` depuis `from_id` (IsValidPathNode/Walk)."""
    t = board.by_id.get(to_id)
    if t is None or not t["walkable"]:
        return False
    if abs(board.elevation(to_id) - board.elevation(from_id)) > 1:
        return False
    occ = occupants.get(to_id)
    if occ is not None and occ != moving_team:      # ENNEMI sur la tuile → bloque
        return False
    return True


def get_reachable_levels(
    board: Board, start_id: int,
    occupants: dict, moving_team: int,
    max_depth: int | None = None,
    edge=is_valid_path_node,
) -> dict:
    """BFS niveau-par-niveau → {tile_id -> distance-en-pas depuis start}. Inclut
    le start (niveau 0). `max_depth` borne la profondeur (None = illimité). Le
    start lui-même n'est pas filtré par son propre occupant (on part de là).

    `edge(board, from_id, to_id, occupants, moving_team) -> bool` = prédicat d'arête
    (peut-on TRAVERSER vers `to`). Défaut = `is_valid_path_node` (WalkPathfinder) ;
    le FlyPathfinder passe son propre prédicat (mirror natif `BasePathfinder` = BFS
    générique, chaque pathfinder override `IsValidPathNode`)."""
    level = {start_id: 0}
    frontier = [start_id]
    depth = 0
    while frontier and (max_depth is None or depth < max_depth):
        depth += 1
        nxt = []
        for cur in frontier:
            for n in board.neighbours(cur):
                if n in level:
                    continue
                if edge(board, cur, n, occupants, moving_team):
                    level[n] = depth
                    nxt.append(n)
        frontier = nxt
    return level


def get_movable_positions(
    board: Board, start_id: int, depth: int,
    occupants: dict, moving_team: int,
    edge=is_valid_path_node,
) -> tuple[set, set]:
    """Renvoie (visited, stop_set) pour une portée `depth` (niveaux).
      - visited : toutes les tuiles atteintes en ≤ depth pas (traversables, start inclus).
      - stop_set: tuiles où l'unité peut S'ARRÊTER = visited \\ occupées \\ {start}
                  (IsValidContinuePathTile : pas d'occupant ; le natif exclut la
                  tuile courante du résultat).
    `edge` = prédicat de TRAVERSÉE (défaut walk ; fly passe le sien). Le stop reste
    identique (tuile libre) : les tuiles visitées sont déjà passables par construction
    (l'arête exige `walkable`), donc « non occupée » suffit pour les deux pathfinders."""
    level = get_reachable_levels(board, start_id, occupants, moving_team, max_depth=depth, edge=edge)
    visited = set(level)
    stop = set()
    for tid in visited:
        if tid == start_id:
            continue
        if occupants.get(tid) is not None:          # impossible de finir sur une tuile occupée
            continue
        stop.add(tid)
    return visited, stop
