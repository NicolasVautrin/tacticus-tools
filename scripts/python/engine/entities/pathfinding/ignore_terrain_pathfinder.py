"""IgnoreTerrainPathfinder — le pathfinder **`PathfinderType = 1`**, celui que la face DECISION
utilise pour mesurer une distance de CHEMIN. Port fidele (#17-off, RE ghidra `gqfc5mff6c`).

Qui l'appelle, et pourquoi ce module existe separement de `walk_pathfinder` :

  `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` appelle
  `IPathfinders.GetPath(1, unit, tuile, tuileEnnemie, null)` avec **`1` en LITTERAL** — meme pour une
  unite VOLANTE. `IdunBattle.Entities.Pathfinding.Pathfinders$$.ctor` construit le dictionnaire
  `PathfinderType -> pathfinder` ; l'entree `1` n'est PAS le `WalkPathfinder` (celui-la sert a
  l'ENUMERATION des tuiles atteignables, via `MovementQuery.GetReachableTiles`). Les deux different
  sur les DEUX faces qui comptent :

    | face                | WalkPathfinder                         | ce pathfinder (type 1)          |
    |---------------------|----------------------------------------|---------------------------------|
    | `IsValidPathNode`   | + `UnitIsBlockedByEnemyUnit(to, unit)` | AUCUN test d'occupant           |
    | `WeightCost`        | `(bloquee ? 10000 : 10) - elevation`   | `10 + IsFilled(to)`             |

  Consequences MESUREES (probe_17_s5_mindist, 2026-07-29, 101 tuiles sur 2 couples seed/board) :
  un chemin peut TRAVERSER une unite — y compris finir sur la tuile occupee par sa cible, ce qui est
  exactement ce que fait `GetMinDistanceToEnemy` — et le cout etant quasi uniforme (10 ou 11), le
  chemin rendu est un chemin de LONGUEUR MINIMALE. Porter ici le `WeightCost` du WalkPathfinder
  (`10 - elevation`) faisait diverger 18 des 87 tuiles du couple `777/C4_09`, toujours d'un pas EN
  TROP : sur un board a relief, le chemin le moins cher au sens Walk est plus long en pas, et ce
  n'est PAS ce que le natif rend.

`IdunBattle.Entities.Pathfinding.IgnoreTerrainPathfinder$$IsValidPathNode(this, from, to)` in extenso :

    ok = |elevation(to) - elevation(from)| <= 1
    if (IsTeleportationTile(from) && IsTeleportationTile(to)) ok = true
    return IsWalkable(to) && ok

⚠ NON porte : l'exception TELEPORTEURS (aucun board de test n'en porte, comme dans `walk_pathfinder`).
"""
from __future__ import annotations

import heapq

from .board import Board

WEIGHT_BASE = 10        # `IgnoreTerrainPathfinder$$WeightCost` = `10 + TileContentComponent.IsFilled(to)`


def is_valid_path_node(board: Board, from_id: int, to_id: int) -> bool:
    """`IdunBattle.Entities.Pathfinding.IgnoreTerrainPathfinder$$IsValidPathNode` — peut-on entrer sur
    `to_id` depuis `from_id`. **Aucun test d'occupant** : la signature native n'a meme pas de
    parametre `unit`, contrairement a `WalkPathfinder$$IsValidPathNode`."""
    t = board.by_id.get(to_id)
    if t is None or not t["walkable"]:
        return False
    return abs(board.elevation(to_id) - board.elevation(from_id)) <= 1


def weight_cost(tile_id: int, occupants: dict) -> int:
    """`IdunBattle.Entities.Pathfinding.IgnoreTerrainPathfinder$$WeightCost` = `IsFilled(to) + 10` :
    le cout d'ENTREE sur la tuile d'ARRIVEE de l'arete (le natif appelle `WeightCost(unit, voisin)`
    depuis `BasePathfinder$$GenerateBreadthFirstTree`). `IsFilled` = la tuile porte une unite —
    l'elevation n'intervient PAS ici (c'est une specificite du `WalkPathfinder`)."""
    return WEIGHT_BASE + (1 if occupants.get(tile_id) is not None else 0)


def get_path_node_counts(board: Board, target_id: int, occupants: dict) -> dict:
    """`{tile_id -> Count}` de `IPathfinders.GetPath(1, unit, tile_id, target_id, null)` pour TOUTES
    les tuiles d'ou `target_id` est joignable — un compte de **NOEUDS, extremites incluses**
    (`route+0x18` = `List._size`), donc `aretes + 1`. Tuile absente du dict = `GetPath` rend `null`.

    Mirror de `IdunBattle.Entities.Pathfinding.BasePathfinder$$FindPath` :
      * `GenerateBreadthFirstTree` est un **A\\*** : cout d'arete = `WeightCost(unit, voisin)`,
        heuristique `BasePathfinder$$Heuristic` = `|dcol| + |drow|` (<= 2 par pas, contre 10 de cout
        reel) donc ADMISSIBLE et coherente -> le chemin rendu est de **cout minimal** ;
      * `FindPath` reconstruit ensuite la liste `from..to`, **extremites incluses** — d'ou le
        `Count` = `aretes + 1` ;
      * l'expansion passe par `BasePathfinder$$GetValidNeighbours`, **sans** le gate
        `IsValidContinuePathTile` de `NodesInNextLevel` (celui-la ne vaut que pour l'ENUMERATION des
        tuiles atteignables) : une tuile block-entering reste TRAVERSABLE par un chemin.

    Ce parcours est INVERSE (il part de `target_id`) pour rendre en UNE passe la distance de toutes
    les tuiles vers une meme destination. L'accumulation `dist(v) = dist(u) + w(v)` avec
    `dist(target) = 0` donne `Somme(w) sur c0..c(k-1)` la ou le natif minimise `Somme(w) sur c1..ck` :
    les deux ne different que de `w(c0) - w(ck)`, CONSTANT a tuile de depart fixee, donc le chemin
    argmin est le MEME. Le predicat, lui, est symetrique (`IsWalkable` de chaque extremite et un
    `|delta elevation|` symetrique, aucun test d'occupant).

    ⚠ NON LU au decompile : le departage entre deux chemins de MEME cout et de longueurs
    differentes (il depend de l'ordre interne de la `PriorityQueue` native). Ici : moins de noeuds
    gagne."""
    if board.by_id.get(target_id) is None:
        return {}
    best: dict = {target_id: (0, 1)}
    heap = [(0, 1, target_id)]
    while heap:
        cost, nodes, cur = heapq.heappop(heap)
        if (cost, nodes) > best.get(cur, (cost, nodes)):
            continue                                  # entree perimee de la file
        for n in board.neighbours(cur):
            if not is_valid_path_node(board, cur, n):
                continue
            cand = (cost + weight_cost(n, occupants), nodes + 1)
            if n not in best or cand < best[n]:
                best[n] = cand
                heapq.heappush(heap, (cand[0], cand[1], n))
    return {tid: nodes for tid, (_cost, nodes) in best.items()}
