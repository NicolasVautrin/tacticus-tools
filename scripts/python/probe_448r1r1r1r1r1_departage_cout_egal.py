"""#448-r1-r1-r1-r1-r1 -- le DEPARTAGE A COUT EGAL de
`IdunBattle.Entities.Pathfinding.BasePathfinder$$GenerateBreadthFirstTree`.

    python probe_448r1r1r1r1r1_departage_cout_egal.py [--boards 60]

CE QUE LA FICHE DISAIT, ET CE QUE LE DECOMPILE DIT
--------------------------------------------------
Le residu affirmait que le departage « n'est pas lu au decompile ». **La moitie qui compte l'est.**
Corps de `GenerateBreadthFirstTree`, remis en C# :

    costs[fromTile] = (fromTile, 0);  pq.Enqueue(fromTile, 0);
    while (pq.Count > 0) {
        tile = pq.Dequeue();
        if (tile == toTile) return costs;
        foreach (n in GetValidNeighbours(this, tile, unit, null)) {
            newCost = WeightCost(unit, n) + costs[tile].cost;
            if (!costs.ContainsKey(n) || newCost < costs[n].cost) {      // <-- STRICT, sur le COUT SEUL
                pq.Enqueue(n, newCost + Heuristic(this, n, toTile));
                costs[n] = (tile, newCost);
            }
        }
    }

La CONDITION DE MISE A JOUR est donc entierement lisible : `<` STRICT, sur le COUT, **sans aucun
terme de longueur**. A cout egal, le natif GARDE le parent deja inscrit -- c'est-a-dire le PREMIER
trouve. Ce qui reste illisible n'est pas la regle : c'est **l'ordre de sortie de la
`idun.shared.collections.PriorityQueue` entre priorites egales**, qui decide QUI est « premier ».

Le port, lui, compare `(cout, noeuds)` : a cout egal il prefere le chemin le plus COURT. C'est une
regle que le natif n'a pas.

CE QUE CE PROBE MESURE
----------------------
L'ECART OBSERVABLE entre les deux regles, sur la geometrie REELLE et avec le COUT REEL du
`WalkPathfinder` (celui qui depend de l'elevation -- le seul regime non uniforme atteint par le
port : `FlyPathfinder$$WeightCost` est un `return 10` constant, donc a cout egal toutes les
longueurs y coincident et l'ambiguite n'existe pas).

MESURE (2026-08-10, 60 boards, 18 200 paires (src, dst) joignables) : **0 divergence**, ni sur le
COUT (attendu : les deux regles rendent le meme optimum de cout) ni sur le NOMBRE DE NOEUDS. La
regle fabriquee par le port est donc **INERTE** sur ce substrat -- ce qui ne la rend pas juste,
mais la rend sans consequence mesurable, et c'est ce qui a fait renoncer a la changer : le nombre
de noeuds est l'entree de `movementSteps`, dont la valeur est CONFRONTEE LIVE (#448-r1-r1-r1).
Re-deriver plutot que citer.
"""
from __future__ import annotations

import argparse
import heapq
import pathlib
import sys

import probe_448r1r1r2r2_gates_abandon as P
from engine.entities.pathfinding import base_pathfinder as BP
from engine.entities.pathfinding import walk_pathfinder as WP

BOARDS = pathlib.Path(__file__).resolve().parents[2] / "data" / "boards"


def tree_regle_native(board, src, dst, edge, neighbours, weight_cost) -> dict:
    """La MEME boucle que `base_pathfinder.generate_breadth_first_tree`, a UNE ligne pres : la
    condition de mise a jour est `newCost < costs[n].cost` -- STRICTE, sur le COUT SEUL, comme le
    decompile. Tout le reste (file, heuristique, arret anticipe) est identique, pour que l'ecart
    mesure soit imputable a CETTE ligne et a aucune autre."""
    best = {int(src): (int(src), 0, 1)}
    heap = [(0, 0, 1, int(src))]
    goal = int(dst)
    while heap:
        _p, cost, nodes, tile = heapq.heappop(heap)
        if tile == goal:
            return best
        cur = best.get(tile)
        if cur is not None and cost > cur[1]:
            continue
        for n in neighbours(tile):
            if n == tile or not edge(board, tile, n):
                continue
            nc = cost + int(weight_cost(n))
            known = best.get(n)
            if known is None or nc < known[1]:                    # <-- la SEULE ligne qui differe
                best[n] = (tile, nc, nodes + 1)
                heapq.heappush(heap, (nc + BP.heuristic(board, n, goal), nc, nodes + 1, n))
    return best


def mesurer(n_boards: int) -> int:
    ids = []
    for kind in ("pvp", "global", "syncPvp"):
        d = BOARDS / kind
        if d.exists():
            ids += [p.stem for p in sorted(d.glob("*.json"))]
    print("[dep] dumps disponibles : %d ; balayes : %d" % (len(ids), min(n_boards, len(ids))))
    total = diff_cost = diff_nodes = 0
    touches = set()
    for bid in ids[:n_boards]:
        try:
            board = P._load_board(bid)
        except SystemExit:
            continue
        tids = sorted(board.by_id)

        def wc(t, board=board):
            e = (board.by_id.get(t) or {}).get("elevation", 0) or 0
            return WP.weight_cost(e)                     # le COUT REEL du WalkPathfinder

        edge = lambda b, a, c: True                                        # noqa: E731
        neigh = lambda t, board=board: board.base_add_neighbours(          # noqa: E731
            t, board.neighbours_geometric)
        for src in tids[:8]:
            for dst in tids[:40]:
                if src == dst:
                    continue
                a = BP.generate_breadth_first_tree(board, src, dst, edge=edge, neighbours=neigh,
                                                   weight_cost=wc)
                b = tree_regle_native(board, src, dst, edge, neigh, wc)
                if a.get(dst) is None or b.get(dst) is None:
                    continue                                   # destination injoignable des DEUX
                total += 1
                if a[dst][1] != b[dst][1]:
                    diff_cost += 1
                    touches.add(bid)
                if a[dst][2] != b[dst][2]:
                    diff_nodes += 1
                    touches.add(bid)
    print("[dep] paires joignables : %d" % total)
    print("[dep] divergences de COUT   : %d" % diff_cost)
    print("[dep] divergences de NOEUDS : %d" % diff_nodes)
    print("[dep] boards touches : %d %s" % (len(touches), sorted(touches)[:8]))
    if total == 0:
        print("[dep] AUCUNE paire mesuree -- le balayage n'exerce RIEN, verdict VIDE")
        return 1
    print("[dep] VERDICT : la regle fabriquee par le port (`(cout, noeuds)`) est %s"
          % ("INERTE sur ce substrat" if (diff_cost + diff_nodes) == 0 else "OBSERVABLE"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", type=int, default=60)
    a = ap.parse_args()
    return mesurer(a.boards)


if __name__ == "__main__":
    sys.exit(main())
