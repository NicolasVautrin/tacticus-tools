"""IgnoreTerrainPathfinder — le pathfinder **`PathfinderType = 1`**, celui que la face DECISION
utilise pour mesurer une distance de CHEMIN. Port fidele (#17-off, RE ghidra `gqfc5mff6c`).

Qui l'appelle, et pourquoi ce module existe separement de `walk_pathfinder` :

  `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` appelle
  `IPathfinders.GetPath(1, unit, tuile, tuileEnnemie, null)` avec **`1` en LITTERAL** — meme pour une
  unite VOLANTE. `IdunBattle.Entities.Pathfinding.Pathfinders$$.ctor` construit le dictionnaire
  `PathfinderType -> pathfinder` ; l'entree `1` n'est PAS le `WalkPathfinder` (celui-la sert a
  l'ENUMERATION des tuiles atteignables, via `MovementQuery.GetReachableTiles`). Les deux different
  sur les DEUX faces qui comptent :

  ⚠ **Base de preuve de l'identification** (le `.ctor` mappe le type 1 sur un `TypeInfo` que le
  binaire ne resout qu'au runtime, donc le NOM n'est pas lu directement) : (a) la hierarchie
  (`classes.tsv`) partage les pathfinders en deux familles — `IgnoreDoor`/`WaveValidator` derivent de
  `WalkPathfinder`, `IgnoreTerrain`/`IgnoreEverything` de `BasePathfinder` ; (b) la MESURE tranche
  entre ces deux familles (cf. tableau et chiffres ci-dessous). **NON DEPARTAGE** : `IgnoreTerrain`
  (qui teste l'elevation) contre un pathfinder qui l'ignorerait — les deux ont le meme `WeightCost`
  et la meme absence de test d'occupant, et aucun montage n'a exerce ce gate (`probe_17_off_occupant
  _gate.py` colonne `d_flat` : 0 tuile discriminante sur `MC1_67` comme sur le board a cliff
  `C3_59`). Ce module porte la variante qui TESTE l'elevation.

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

    VOISINAGE = la liste STOCKEE (`#381-r3`). `IgnoreTerrainPathfinder` derive de `BasePathfinder`
    (`data/symbols/<build>/frida/classes.tsv`) et n'OVERRIDE PAS `AddNeighbours` : il herite donc du
    corps qui enumere le `ConnectivityComponent` de la tuile -- `board.base_add_neighbours`, et non
    `board.neighbours()`, qui depend du `adjacency=` choisi par l'appelant.

    ⚠ Le canal BRUT depuis `#448-r1-r1-r1-r1-r2-r1` (avant : le champ herite `neighbours`, ampute
    par la porte `|dElev| < 2` du capteur). Sur CETTE route le changement est un NO-OP **prouve**,
    pas constate : les aretes que le canal ajoute sont exactement celles de `|dElev| >= 2`, et
    `IgnoreTerrainPathfinder$$IsValidPathNode` exige `|dElev| <= 1` -- il les refuse toutes. Le
    rebranchement ne deplace donc AUCUNE distance ; il enleve la dependance a une porte qui
    appartient au CAPTEUR et non au natif mirrore. Repli sur le champ herite si le canal n'est pas
    capte : meme graphe effectif, par le meme argument.

    MESURE (`C1_74`/3811, oracle `pathDistToEnemies`, qui appelle litteralement
    `IPathfinders.GetPath(1, unit, from, to, null)`) : sur 180 distances confrontees, la GEOMETRIE
    en rate **11** (4 unites sur 10), la liste STOCKEE **0**. L'ecart etait invisible en production
    (`playbook/scene.py` monte le `Board` en `native_sym`) et vivant dans tout probe monte en
    `evenq` -- exactement la dependance au montage que `#381-r3` supprime.

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
        for n in board.base_add_neighbours(cur):   # `BasePathfinder$$AddNeighbours` (non override)
            if not is_valid_path_node(board, cur, n):
                continue
            cand = (cost + weight_cost(n, occupants), nodes + 1)
            if n not in best or cand < best[n]:
                best[n] = cand
                heapq.heappush(heap, (cand[0], cand[1], n))
    return {tid: nodes for tid, (_cost, nodes) in best.items()}


def get_path_node_counts_by_pos(target, neigh_by_pos=None, walkable_by_pos=None,
                                elev_by_pos=None, occupied_positions=()) -> dict:
    """`{(col,row) -> Count}` de `IPathfinders.GetPath(PathfinderType.IgnoreTerrain, unit, <pos>,
    target, null)` -- le JUMEAU EN DOMAINE POSITION de `get_path_node_counts` ci-dessus, exactement
    comme `walk_pathfinder.get_path_node_counts_by_pos` est le jumeau du moteur `Board` de la marche.

    Il existe parce que les TROIS constructeurs de `leaf_ctx` (`tile.py`) ne publient pas un
    `Board` : ils publient les cartes par-position (`neigh_by_pos` = `board.neighbours_native`,
    `walkable_by_pos`, `elev_by_pos`). Le consommateur est
    `IdunBattle.AI.Utilities.MoveTowardsUnitUtility$$GetMinDistanceToTarget`, qui appelle ce
    pathfinder avec le litteral `1` (`PathfinderType.IgnoreTerrain`) et lit `route+0x18`
    (`List._size`) -- un compte de NOEUDS, extremites INCLUSES.

    ⚠ **LE VOISINAGE PUBLIE EST `neighbours_native`, PAS `connectivity`** -- et ici c'est un
    NO-OP PROUVE, pas une approximation : `board.base_add_neighbours` documente l'identite
    `neighbours == connectivity INTERSECTE {aretes de |dElev| < 2}`, et `is_valid_path_node`
    ci-dessus exige `|dElev| <= 1` -- il refuse donc exactement les aretes que le champ omet.
    C'est le MEME argument que celui ecrit dans `get_path_node_counts` pour son propre repli.

    Parcours INVERSE (il part de `target`), comme le jumeau `Board` et pour la meme raison : une
    passe rend la distance de TOUTES les tuiles candidates vers la meme destination. L'argument de
    symetrie est celui de `get_path_node_counts` (predicat symetrique, ecart de cout constant a
    tuile de depart fixee).

    `occupied_positions` = `TileContentComponent.IsFilled(to)` du `WeightCost` (`10 + IsFilled`) --
    un COUT, jamais un gate de passage : ce pathfinder n'a AUCUN test d'occupant.
    `neigh_by_pos` absent -> repli sur le voisinage `hexgeo` restreint aux positions connues (meme
    degradation que `walk_pathfinder.get_path_node_counts_by_pos`)."""
    import hexgeo
    tk = (target[0], target[1])
    occ = {(p[0], p[1]) for p in (occupied_positions or ())}
    domain = None
    if neigh_by_pos is None:
        domain = set(walkable_by_pos or ()) | set(elev_by_pos or ())

    def _neighbours(p):
        if neigh_by_pos is not None:
            return [(q[0], q[1]) for q in (neigh_by_pos.get(p) or ())]
        ns = hexgeo.neighbors(p[0], p[1])
        return [q for q in ns if not domain or q in domain]

    def _elev(p):
        return None if elev_by_pos is None else elev_by_pos.get(p)

    best: dict = {tk: (0, 1)}                      # pos -> (cout cumule, nb de noeuds)
    heap = [(0, 1, tk)]
    while heap:
        cost, nodes, cur = heapq.heappop(heap)
        if (cost, nodes) > best.get(cur, (cost, nodes)):
            continue                               # entree perimee de la file
        ce = _elev(cur)
        for n in _neighbours(cur):
            # `IgnoreTerrainPathfinder$$IsValidPathNode(from, to)` : `IsWalkable(to)` ET
            # `|elev(to) - elev(from)| <= 1`. AUCUN test d'occupant (la signature native n'a meme
            # pas de parametre `unit`).
            if walkable_by_pos is not None and not walkable_by_pos.get(n, False):
                continue
            ne = _elev(n)
            if ce is not None and ne is not None and abs(ne - ce) > 1:
                continue
            cand = (cost + WEIGHT_BASE + (1 if n in occ else 0), nodes + 1)
            if n not in best or cand < best[n]:
                best[n] = cand
                heapq.heappush(heap, (cand[0], cand[1], n))
    return {p: nodes for p, (_cost, nodes) in best.items()}
