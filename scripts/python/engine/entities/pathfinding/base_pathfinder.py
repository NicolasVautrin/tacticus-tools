"""`IdunBattle.Entities.Pathfinding.BasePathfinder` -- la route **CHEMIN EXACT** en domaine
TILE-ID, celle que tous les pathfinders heritent et que seul `FlyPathfinder` surcharge.

DEUX ROUTES, DEUX MODULES. `BasePathfinder` porte deux faces distinctes :

  * l'ENUMERATION (`GetMovablePositions` -> `NodesInNextLevel`), une flood-fill PAR NIVEAUX,
    portee par `walk_pathfinder.get_reachable_levels` ;
  * le CHEMIN (`FindPath` -> `GenerateBreadthFirstTree`), un A* pondere, porte ICI.

`walk_pathfinder.get_path_node_counts_by_pos` porte deja la seconde face en domaine POSITION,
pour la face DECISION (qui n'a pas de `Board`). Ce module-ci est son pendant en domaine TILE-ID :
c'est celui dont la chaine `MovementQuery$$GetConnectedPathTo` a besoin, parce qu'elle consomme le
CHEMIN lui-meme (elle le simplifie puis le densifie), pas seulement sa longueur.

LE DECOMPILE, remis en C#
-------------------------
`IdunBattle.Entities.Pathfinding.BasePathfinder$$FindPath(unit, fromTile, toTile, useTeleporter)` :

    if (fromTile == null || toTile == null)        return null;
    if (!IsValidFinalTile(unit, toTile))           return null;      // vslot @+0x1c8
    cameFrom = GenerateBreadthFirstTree(unit, fromTile, toTile);
    path = [toTile]; cur = toTile;
    while (cur != fromTile) {
        if (!cameFrom.TryGetValue(cur, out cur))   return null;      // destination injoignable
        path.Add(cur);
    }
    path.Reverse();                                                  // extremites INCLUSES
    return path;

`IdunBattle.Entities.Pathfinding.BasePathfinder$$GenerateBreadthFirstTree(unit, fromTile, toTile)` :

    costs[fromTile] = (fromTile, 0);  pq.Enqueue(fromTile, 0);
    while (pq.Count > 0) {
        tile = pq.Dequeue();
        if (tile == toTile) return costs;                            // arret ANTICIPE (A*)
        foreach (n in GetValidNeighbours(this, tile, unit, null)) {
            newCost = WeightCost(unit, n) + costs[tile].cost;        // vslot @+0x1f8
            if (!costs.ContainsKey(n) || newCost < costs[n].cost) {
                pq.Enqueue(n, newCost + Heuristic(this, n, toTile));
                costs[n] = (tile, newCost);
            }
        }
    }
    return costs;

`GetValidNeighbours` = `AddNeighbours` (vslot @+0x238) filtre par
`BasePathfinder$$CheckNeighbour` = `neighbour != tile && !excluded(neighbour)
&& IsValidPathNode(tile, neighbour, unit)` (vslot @+0x1e8), et `BasePathfinder$$Heuristic` =
`|dcol| + |drow|`.

⚠ LE 5e PARAMETRE N'EST PAS UN `maxRange` (`#448-r1-r1-r1-r1`). Sa signature, lue dans
`data/symbols/<build>/frida/methods.tsv`, est
`useTeleporter:System.Nullable<IdunBattle.Entities.Pathfinding.UseTeleporter>` -- et ni
`BasePathfinder$$FindPath` ni `FlyPathfinder$$FindPath` ne le LISENT (il traverse leur corps sans
etre deference). `MovementQuery$$GetConnectedPathTo` y passe pourtant
`Nullable(GetStat(unit, 1))` : c'est un argument MORT sur ces deux routes, et le port n'a donc
rien a en faire. La case-doc de `#448-r1-r1-r1` le nommait « maxRange a porter » -- REFUTE.

RESIDUS, tous nommes
--------------------
  * DEPARTAGE entre deux chemins de MEME cout et de longueurs differentes (#448-r1-r1-r1-r1-r1).
    ⚠ **LA REGLE, ELLE, EST LUE** -- la fiche disait le contraire : la mise a jour native est
    `if (!costs.ContainsKey(n) || newCost < costs[n].cost)`, un `<` **STRICT** sur le **COUT
    SEUL**, sans aucun terme de longueur ; a cout egal le natif GARDE le parent deja inscrit,
    c'est-a-dire le PREMIER trouve. Ce qui reste illisible n'est PAS la regle mais l'ordre de
    sortie de la `idun.shared.collections.PriorityQueue` entre priorites egales, qui decide QUI
    est « premier » -- et qu'aucun port ne peut reproduire sans la file elle-meme.
    Ici, a cout egal, MOINS DE NOEUDS gagne : une regle que le natif n'a pas, et qui est donc une
    FABRICATION assumee -- meme arbitrage que `walk_pathfinder._dijkstra_by_pos`.
    **MESUREE INERTE** (`probe_448r1r1r1r1r1_departage_cout_egal.py`, 2026-08-10) : sur 60 boards
    et 18 200 paires (src, dst) joignables, avec le COUT REEL du `WalkPathfinder` (le seul regime
    non uniforme que le port atteigne), les deux regles rendent **0 divergence**, ni de cout ni de
    nombre de noeuds. Elle n'est donc pas corrigee : la corriger ne changerait rien de mesurable
    et ferait reposer `movementSteps` -- valeur CONFRONTEE LIVE (#448-r1-r1-r1) -- sur un etage
    neuf. Sans relief (cout uniforme, EXACTEMENT le cas du vol), l'ambiguite n'existe meme pas.
    Re-deriver le chiffre, ne pas citer cette ligne.
  * `AddTeleportationTiles` / `AddShadewalkerTiles` : les deux autres sources de voisins de
    `GetValidNeighbours`. Le `boardGraph` ne publie ni la jumelle de teleportation
    (`ConnectivityComponent+0x18`) ni l'effet `0x3a`. Degradation RESTRICTIVE, identique a celle
    deja nommee dans `walk_pathfinder.get_reachable_levels`.
  * `excluded` (le `Predicate<TileEntity>` de `CheckNeighbour`) : `null` a tous les call-sites
    portes -- `GenerateBreadthFirstTree` passe litteralement `null`.
"""
from __future__ import annotations

import heapq

from .board import Board


def heuristic(board: Board, from_id: int, to_id: int) -> int:
    """`IdunBattle.Entities.Pathfinding.BasePathfinder$$Heuristic(from, to)` = la somme des
    ecarts absolus des DEUX composantes de la position (`|dcol| + |drow|`).

    Elle est ADMISSIBLE (<= 2 par pas, contre un cout reel >= 6 sur les elevations du jeu), donc
    l'arret anticipe de `GenerateBreadthFirstTree` rend bien un chemin de cout MINIMAL."""
    fc, fr = board.coord(int(from_id))
    tc, tr = board.coord(int(to_id))
    return abs(fc - tc) + abs(fr - tr)


def generate_breadth_first_tree(board: Board, from_id: int, to_id: int, *,
                                edge, neighbours, weight_cost) -> dict:
    """`BasePathfinder$$GenerateBreadthFirstTree` -- `{tile_id -> (parent_id, cout_cumule)}`.

    `edge(board, from_id, to_id) -> bool`   = le vslot `IsValidPathNode` du pathfinder ;
    `neighbours(tile_id) -> [tile_id]`      = le vslot `AddNeighbours` (liste STOCKEE pour la
                                              base, GEOMETRIE pour `FlyPathfinder`) ;
    `weight_cost(tile_id) -> int`           = le vslot `WeightCost`, applique a la tuile
                                              d'ARRIVEE de l'arete.

    Le port ajoute au tuple natif `(parent, cout)` un TROISIEME terme, le nombre de noeuds, qui
    ne sert qu'au departage a cout egal (cf. l'en-tete) ; il n'entre pas dans la comparaison de
    cout du natif."""
    best: dict = {int(from_id): (int(from_id), 0, 1)}
    heap = [(0, 0, 1, int(from_id))]              # (priorite = cout + heuristique, cout, noeuds, tuile)
    goal = int(to_id)
    while heap:
        _prio, cost, nodes, tile = heapq.heappop(heap)
        if tile == goal:
            return best                            # `if (tile == toTile) return costs;`
        cur = best.get(tile)
        if cur is not None and (cost, nodes) > (cur[1], cur[2]):
            continue                               # entree perimee de la file
        for n in neighbours(tile):
            if n == tile or not edge(board, tile, n):
                continue                           # `CheckNeighbour`
            cand = (cost + int(weight_cost(n)), nodes + 1)
            known = best.get(n)
            if known is None or cand < (known[1], known[2]):
                best[n] = (tile, cand[0], cand[1])
                heapq.heappush(heap, (cand[0] + heuristic(board, n, goal), cand[0], cand[1], n))
    return best


def find_path(board: Board, from_id, to_id, *, edge, neighbours, weight_cost,
              is_valid_final_tile) -> "list[int] | None":
    """`BasePathfinder$$FindPath` -- la liste des tuiles du chemin, **extremites INCLUSES**
    (`path[0]` = depart, `path[-1]` = destination), ou `None`.

    `None` couvre les TROIS sorties nulles du natif : une extremite absente, un
    `IsValidFinalTile(to)` faux, et une destination que l'arbre ne relie pas au depart.
    `from == to` rend `[to]` (Count 1), comme le natif dont la boucle de remontee ne s'execute
    alors pas -- et `GetNumTilesMoved` y vaut donc 0."""
    if from_id is None or to_id is None:
        return None
    src, dst = int(from_id), int(to_id)
    if src not in board.by_id or dst not in board.by_id:
        return None
    if not is_valid_final_tile(dst):
        return None
    came = generate_breadth_first_tree(board, src, dst, edge=edge, neighbours=neighbours,
                                       weight_cost=weight_cost)
    path = [dst]
    cur = dst
    while cur != src:
        nxt = came.get(cur)
        if nxt is None:
            return None                            # `TryGetValue` faux -> destination injoignable
        cur = nxt[0]
        path.append(cur)
    path.reverse()
    return path
