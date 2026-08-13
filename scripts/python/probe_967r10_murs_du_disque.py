#!/usr/bin/env python3
"""#967-r10 -- MESURE du gisement `isWall` et de l'effet OBSERVABLE du filtre mur du noeud DSL
`SurroundingTiles`.

La question que le residu ne posait pas, et qui decide s'il est fermable par une mesure :
**existe-t-il des tuiles `isWall` sur les boards reels, et le filtre change-t-il un ensemble que
les call-sites regardent ?** Trois regimes a distinguer, parce qu'ils ne se valent pas :

  (a) `isWall = True, walkable = False` -- le cas ordinaire. Sur les 5 call-sites qui gardent
      `includeNonWalkable = True` (aucun filtre walkable), la tuile entrait dans le disque : le
      filtre mur la retire. C'est un ecart REEL.
  (b) `isWall = True, walkable = True`  -- s'il existe, alors le filtre mur mord AUSSI la ou le
      gate walkable est arme (`ThriceBlessedConflagration`, `includeNonWalkable = False`).
  (c) `isWall = False, walkable = False` -- Block/Water. Le natif les GARDE sous
      `includeNonWalkable = 1` ; c'est ce que le repli `not walkable` de `Board.is_wall()` aurait
      casse, et pourquoi `_is_wall` lit la cle brute.

Sortie ASCII stricte. Ne modifie rien, ne monte qu'un runner a la fois et le dispose.

Usage :
    python probe_967r10_murs_du_disque.py --boards MC1_67,C3_01,C1_74 --state-file <abs>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

ROOT = PYDIR.parents[1]


def _rpc():
    import probe_130_placement_sort_rng as P130
    return P130.Rpc()


def _build(seed, board, state_file):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("  BUILD KO (%s): %s" % (board, (proc.stderr or proc.stdout or "")[-400:]))
        return None
    return json.loads(Path(state_file).read_text())["runnerId"]


def _mesure_board(tiles):
    """Ventilation des 3 regimes + effet du filtre sur tous les disques de rayon 1 et 2."""
    from engine.entities.pathfinding.board import Board
    from engine.entities.selectors.accessors import FixedTileIds, SurroundingTiles
    from engine.dsl.base import Const

    board = Board(tiles, adjacency="native_sym")

    def _w(t):
        return bool(t.get("walkable"))

    def _iw(t):
        return bool(t.get("isWall"))

    n = len(tiles)
    a = sum(1 for t in tiles if _iw(t) and not _w(t))
    b = sum(1 for t in tiles if _iw(t) and _w(t))
    c = sum(1 for t in tiles if not _iw(t) and not _w(t))
    porte_cle = sum(1 for t in tiles if "isWall" in t)

    class _Ctx:
        board = None

    ctx = _Ctx()
    ctx.board = board

    # Effet du filtre, disque par disque : combien de CENTRES voient leur disque change, et de
    # combien de tuiles au total. On compare le disque AVEC filtre (le port courant) au disque
    # PUR (hexgeo.disk borne au plateau), qui est exactement ce que le port rendait AVANT.
    import hexgeo
    effet = {}
    for r in (1, 2):
        centres_touches = 0
        retirees = 0
        for tid, t in board.by_id.items():
            pur = []
            vus = set()
            for (col, row) in hexgeo.disk(t["col"], t["row"], r):
                x = board.id_at(col, row)
                if x is not None and x not in vus:
                    vus.add(x)
                    pur.append(x)
            main = board.id_at(t["col"], t["row"])
            pur = [x for x in pur if x != main]          # include_center=False
            node = SurroundingTiles(FixedTileIds([tid]), Const(r), include_center=False,
                                    include_non_walkable=True)
            got = list(node.select(ctx))
            d = len(pur) - len(got)
            if d:
                centres_touches += 1
                retirees += d
        effet[r] = (centres_touches, retirees)
    return dict(n=n, porte_cle=porte_cle, mur_non_walkable=a, mur_walkable=b,
                nonwalk_non_mur=c, effet=effet)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", default="MC1_67,C3_01,C1_74,C6_02")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--state-file", default=None)
    args = ap.parse_args()

    rpc = _rpc()
    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    sf = args.state_file or str(ROOT / "logs" / "runners" /
                                ("p967r10-%s.json" % uuid.uuid4().hex[:8]))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)

    print("BOARD              tiles  cle_isWall  mur&!walk  mur&walk  !mur&!walk   "
          "r1(centres/retirees)  r2(centres/retirees)")
    total_murs = 0
    for b in boards:
        rid = _build(args.seed, b, sf)
        if rid is None:
            continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
        finally:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 30)
            except Exception:
                pass
            try:
                Path(sf).unlink()
            except OSError:
                pass
        tiles = (bg or {}).get("tiles") or []
        if not tiles:
            print("%-18s AUCUNE TUILE RENDUE -- boardGraph muet (PAS un zero de mesure)" % b)
            continue
        m = _mesure_board(tiles)
        total_murs += m["mur_non_walkable"] + m["mur_walkable"]
        print("%-18s %5d  %10d  %9d  %8d  %10d   %8s              %8s" % (
            b, m["n"], m["porte_cle"], m["mur_non_walkable"], m["mur_walkable"],
            m["nonwalk_non_mur"],
            "%d/%d" % m["effet"][1], "%d/%d" % m["effet"][2]))
    print()
    print("TOTAL murs sur les boards mesures : %d" % total_murs)
    if total_murs == 0:
        print("ATTENTION : temoin NUL. Un filtre qui ne retire rien ne se confronte pas -- "
              "il faut soit un autre board, soit conclure que le gate est INERTE sur ce corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
