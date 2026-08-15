#!/usr/bin/env python
"""#433-r4-r1-r1-r2 -- LE FORK DE LIGNE DE VUE, MESURE AVANT TOUTE EDITION.

Deux mirrors du MEME natif `IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain`
coexistent dans le port :

  * COMPLET  -- `engine/services/movement_query.py::get_tiles_obscuring_terrain` (+ `PositionBoard`),
    livre par #433-r4-r2-r1-r2 : trace les DEUX lignes nudgees
    (`MovementUtil$$DrawLineBetweenCoordinates`, nudge `(1e-6, 2e-6, -3e-6)` du
    `MovementUtil$$.cctor`), applique `DetermineBlockingTiles` aux index `1` et `Count - 2`, et
    `DetermineBlockingWalls` sur TOUTE la ligne.
  * v1       -- `engine/battle_query.py::is_target_tile_obscured` : reconstruit les candidates par
    VOISINS COMMUNS, refuse tout ce qui n'est pas a distance EXACTEMENT 2, et n'a aucun volet MURS.

Ce probe MESURE l'ecart des deux, exhaustivement, sur des plateaux synthetiques. Il ne conclut
rien : il imprime les trois regimes separement (dist 1 / dist 2 / dist >= 3) et le volet MURS.

Usage : python probe_433r4r1r1r2_los_fork.py [--cols N] [--rows N] [--seed S]
"""
from __future__ import annotations

import argparse
import itertools
import random
import sys

sys.path.insert(0, ".")

import hexgeo                                    # noqa: E402
from engine import battle_query as BQ            # noqa: E402
from engine.services import movement_query as MQ  # noqa: E402

MASK_ALL = 6          # `idun.meta.ObscuringType.All` = Elevation(2) | Wall(4)
SEUIL = 2             # `blockingElevationDifference` du call-site de ciblage


def complet(elev, walls, a, b, mask=MASK_ALL):
    """Le foyer COMPLET, via le substrat `PositionBoard` de la face DECISION."""
    board = MQ.PositionBoard(elev, walls)
    return bool(MQ.get_tiles_obscuring_terrain(board, a, b, mask, SEUIL))


def v1(elev, a, b):
    """Le fork v1 de `battle_query`."""
    return bool(BQ.is_target_tile_obscured(a, b, elev))


def plateau(cols, rows, rnd, elev_max=4, wall_p=0.0):
    elev = {(c, r): rnd.randint(0, elev_max) for c in range(cols) for r in range(rows)}
    walls = {p: (rnd.random() < wall_p) for p in elev}
    return elev, walls


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cols", type=int, default=9)
    ap.add_argument("--rows", type=int, default=9)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--plateaux", type=int, default=12)
    args = ap.parse_args()

    rnd = random.Random(args.seed)
    par_dist = {}          # dist -> [n_paires, n_desaccords, n_v1_bloque, n_complet_bloque]
    exemples = {}
    for _k in range(args.plateaux):
        elev, _w = plateau(args.cols, args.rows, rnd)
        sans_mur = {p: False for p in elev}
        cells = list(elev)
        for a, b in itertools.permutations(cells, 2):
            d = hexgeo.distance(a, b)
            if d > 6:
                continue
            rc = complet(elev, sans_mur, a, b, MASK_ALL)
            rv = v1(elev, a, b)
            e = par_dist.setdefault(d, [0, 0, 0, 0])
            e[0] += 1
            e[2] += int(rv)
            e[3] += int(rc)
            if rc != rv:
                e[1] += 1
                if d not in exemples:
                    exemples[d] = (a, b, elev.get(a), elev.get(b), rv, rc)

    print("ECART v1 <-> COMPLET, volet ELEVATION seul (aucun mur), mask=6 seuil=2")
    print("%-6s %10s %12s %10s %12s" % ("dist", "paires", "desaccords", "v1 bloque", "complet bl."))
    for d in sorted(par_dist):
        n, k, bv, bc = par_dist[d]
        print("%-6d %10d %12d %10d %12d" % (d, n, k, bv, bc))
    print()
    for d in sorted(exemples):
        a, b, ea, eb, rv, rc = exemples[d]
        print("  1er desaccord dist=%d : %s(elev %s) -> %s(elev %s)  v1=%s complet=%s"
              % (d, a, ea, b, eb, rv, rc))

    # --- volet MURS : le v1 n'en a AUCUN, donc tout mur bloquant est un desaccord par
    #     construction. On mesure COMBIEN, pour dire si le volet est inerte ou non.
    rnd2 = random.Random(args.seed + 1)
    elev, walls = plateau(args.cols, args.rows, rnd2, elev_max=0, wall_p=0.25)
    cells = list(elev)
    n_mur = sum(1 for a, b in itertools.permutations(cells, 2)
                if hexgeo.distance(a, b) <= 6 and complet(elev, walls, a, b, 4))
    n_tot = sum(1 for a, b in itertools.permutations(cells, 2) if hexgeo.distance(a, b) <= 6)
    print("\nVOLET MURS SEUL (mask=4, plateau PLAT, 25%% de murs) : %d paires bloquees sur %d"
          % (n_mur, n_tot))
    print("  (le v1 en bloque 0 par construction -- il n'a aucun canal de murs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
