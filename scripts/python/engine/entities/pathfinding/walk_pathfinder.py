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

TUILE D'ARRÊT valide = tuile NON occupée (ni allié ni ennemi). On peut TRAVERSER un
allié mais pas s'y arrêter. Le start (tuile courante) est exclu du set.

GATE D'EXPANSION (#131, mesuré le 2026-07-27) — `IdunBattle.Entities.Pathfinding
.BasePathfinder$$NodesInNextLevel` commence par :

    if (currentTile != startTile && !IsValidContinuePathTile(this, unit, currentTile))
        return <liste vide>;          // aucun voisin -> la tuile est un CUL-DE-SAC

`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidContinuePathTile` =
`GetTileBlockingReasons(tile, unit) == 0` ; le bit 0x1 de
`IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons` vient d'un EFFET de
tuile (EffectType 0 = `BlockEnteringUnitsTileEffect`, posé sur les Swamp par
`ThornsBlockMovementAbility`), sauf si l'unité porte un trait de
`StaticBattleRules.Effect$$NotBlockingMovementOfTraits` (Mounted/Vehicle/Unstoppable).

⇒ une tuile block-entering **reste un STOP légal** (mesure live : les Swamp sont dans
`aiMovableTiles`) mais **la flood-fill ne s'étend PAS depuis elle**. C'est le `can_continue`
de `get_reachable_levels`. Sans lui le port sur-atteint : mesure MC1_67, `admecMarshall`
move 3 depuis (3,7) — natif 6/16/25 tuiles à portée 1/2/3, port 6/17/27 (les 2 tuiles en
trop, (0,5) et (6,5), ne pendent QUE d'un Swamp). C'est ce sur-atteint qui faisait choisir
à la passe IA générique une tuile ILLÉGALE (cf. case-r5).

⚠ `GetEffectiveDepth` (`WalkPathfinder$$GetEffectiveDepth` = `Min(1, depth)` quand
`GetTileBlockingReasons & 2`, bit posé par le MÊME effet sous une condition non mesurée)
reste NON porté : c'est le volet « l'hex FINIT le mouvement » de #131, sans datapoint.

API : `occupants` = dict {tile_id -> team_of_occupant}. `moving_team` = team de
l'unité qui bouge. `can_continue` = prédicat {tile_id -> bool} (None = aucun gate, comportement
d'avant #131). Aucun RVA, aucun appel natif — pur calcul depuis le Board capté.
"""
from __future__ import annotations

import heapq

from .board import Board

# `IdunBattle.Entities.Pathfinding.WalkPathfinder$$WeightCost` = `(bloquee ? 10000 : 10) - elevation(tuile)`.
# C'est le cout d'ENTREE sur la tuile d'ARRIVEE de l'arete (le natif appelle `WeightCost(unit, voisin)`
# depuis `BasePathfinder$$GenerateBreadthFirstTree`), et le bit teste est celui de
# `WalkPathfinder$$GetTileBlockingReasons & 1` (effet de tuile BlockEnteringUnits).
WEIGHT_BASE = 10
WEIGHT_BASE_BLOCKED = 10000


def weight_cost(board: Board, tile_id: int, blocked: bool = False) -> int:
    """`IdunBattle.Entities.Pathfinding.WalkPathfinder$$WeightCost` : cout d'ENTREE sur `tile_id`."""
    base = WEIGHT_BASE_BLOCKED if blocked else WEIGHT_BASE
    return base - int(board.elevation(tile_id))


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
    can_continue=None,
) -> dict:
    """BFS niveau-par-niveau → {tile_id -> distance-en-pas depuis start}. Inclut
    le start (niveau 0). `max_depth` borne la profondeur (None = illimité). Le
    start lui-même n'est pas filtré par son propre occupant (on part de là).

    `edge(board, from_id, to_id, occupants, moving_team) -> bool` = prédicat d'arête
    (peut-on TRAVERSER vers `to`). Défaut = `is_valid_path_node` (WalkPathfinder) ;
    le FlyPathfinder passe son propre prédicat (mirror natif `BasePathfinder` = BFS
    générique, chaque pathfinder override `IsValidPathNode`).

    `can_continue(tile_id) -> bool` = `IsValidContinuePathTile` (#131) : peut-on ÉTENDRE
    la fill DEPUIS cette tuile ? Le start en est exempt (`currentTile != startTile` du natif).
    None = pas de gate (le board n'a pas d'effet block-entering, ou l'appelant ne le connaît
    pas) → BFS d'avant #131."""
    level = {start_id: 0}
    frontier = [start_id]
    depth = 0
    while frontier and (max_depth is None or depth < max_depth):
        depth += 1
        nxt = []
        for cur in frontier:
            # `NodesInNextLevel` : depuis une tuile block-entering (hors start), AUCUN voisin.
            if can_continue is not None and cur != start_id and not can_continue(cur):
                continue
            for n in board.neighbours(cur):
                if n in level:
                    continue
                if edge(board, cur, n, occupants, moving_team):
                    level[n] = depth
                    nxt.append(n)
        frontier = nxt
    return level


def get_path_node_counts(
    board: Board, target_id: int,
    occupants: dict, moving_team: int,
    edge=is_valid_path_node,
    blocked=None,
) -> dict:
    """`{tile_id -> Count}` de `IPathfinders.GetPath(type=1, unit, tile_id, target_id, null)` pour
    TOUTES les tuiles d'ou `target_id` est joignable — un compte de **NOEUDS, extremites incluses**
    (`route+0x18` = `List._size`), donc `aretes + 1`. Tuile absente du dict = `GetPath` rend `null`.

    Mirror de `IdunBattle.Entities.Pathfinding.BasePathfinder$$FindPath` :
      * `GenerateBreadthFirstTree` est un **A\\*** dont le cout d'arete est
        `WalkPathfinder$$WeightCost(unit, voisin)` = `(bloquee ? 10000 : 10) - elevation(voisin)`
        et l'heuristique `BasePathfinder$$Heuristic` = `|dcol| + |drow|` (<= 1 par pas, contre ~10
        de cout reel) donc ADMISSIBLE -> le chemin rendu est de **cout minimal**, pas de longueur
        minimale ; `FindPath` reconstruit ensuite la liste `from..to` (extremites incluses).
      * l'expansion passe par `BasePathfinder$$GetValidNeighbours`, **sans** le gate
        `IsValidContinuePathTile` de `NodesInNextLevel` (celui-la ne vaut que pour l'ENUMERATION
        des tuiles atteignables) : une tuile block-entering reste TRAVERSABLE par un chemin, elle
        coute seulement 10000.

    Ce parcours est INVERSE (il part de `target_id`), pour rendre en UNE passe la distance de toutes
    les tuiles vers une meme destination. L'accumulation `dist(v) = dist(u) + w(v)` avec
    `dist(target) = 0` donne `Somme(w) sur c0..c(k-1)` la ou le natif minimise `Somme(w) sur c1..ck` :
    les deux ne different que de `w(c0) - w(ck)`, CONSTANT a tuile de depart fixee, donc le chemin
    argmin est le MEME. L'asymetrie de predicat est du meme ordre : le natif teste la tuile
    d'ARRIVEE de chaque pas (donc `target_id`, occupe par l'ennemi, et jamais la tuile de depart),
    ici on teste `v` (donc la tuile de depart, toujours une tuile de move legale, et jamais
    `target_id`). Le natif rend bien un chemin vers une tuile occupee par sa cible (mesure live
    `pathDistToEnemies`, 14/14 tuiles), c.-a-d. qu'il exempte de fait sa destination.

    ⚠ NON LU au decompile : le departage entre deux chemins de MEME cout et de longueurs
    differentes (il depend de l'ordre interne de la `PriorityQueue` native). Ici : moins de noeuds
    gagne."""
    if board.by_id.get(target_id) is None:
        return {}

    def _w(tid: int) -> int:
        return weight_cost(board, tid, bool(blocked(tid)) if blocked is not None else False)

    best: dict = {target_id: (0, 1)}
    heap = [(0, 1, target_id)]
    while heap:
        cost, nodes, cur = heapq.heappop(heap)
        if (cost, nodes) > best.get(cur, (cost, nodes)):
            continue
        for n in board.neighbours(cur):
            if not edge(board, cur, n, occupants, moving_team):
                continue
            cand = (cost + _w(n), nodes + 1)
            if n not in best or cand < best[n]:
                best[n] = cand
                heapq.heappush(heap, (cand[0], cand[1], n))
    return {tid: nodes for tid, (_c, nodes) in best.items()}


def get_movable_positions(
    board: Board, start_id: int, depth: int,
    occupants: dict, moving_team: int,
    edge=is_valid_path_node,
    can_continue=None,
) -> tuple[set, set]:
    """Renvoie (visited, stop_set) pour une portée `depth` (niveaux).
      - visited : toutes les tuiles atteintes en ≤ depth pas (traversables, start inclus).
      - stop_set: tuiles où l'unité peut S'ARRÊTER = visited \\ occupées \\ {start}
                  (IsValidContinuePathTile : pas d'occupant ; le natif exclut la
                  tuile courante du résultat).
    `edge` = prédicat de TRAVERSÉE (défaut walk ; fly passe le sien). Le stop reste
    identique (tuile libre) : les tuiles visitées sont déjà passables par construction
    (l'arête exige `walkable`), donc « non occupée » suffit pour les deux pathfinders.
    `can_continue` = gate d'EXPANSION #131 (cf. `get_reachable_levels`) ; il ne retire RIEN
    du stop set — une tuile block-entering reste un arrêt légal (mesuré live)."""
    level = get_reachable_levels(board, start_id, occupants, moving_team, max_depth=depth,
                                 edge=edge, can_continue=can_continue)
    visited = set(level)
    stop = set()
    for tid in visited:
        if tid == start_id:
            continue
        if occupants.get(tid) is not None:          # impossible de finir sur une tuile occupée
            continue
        stop.add(tid)
    return visited, stop
