"""#996-r1 -- reconnaissance de GEOMETRIE : les tuiles candidates de `templNpc1Initiate` sur son
spawn de `MC1_67`, telles que le port les enumere.

Sert a CALER les `--a-place` de `probe_996r1_devout_push.py` : le mouvement de 1053 n'est
DISCRIMINANT que si au moins deux candidates different par le nombre (et l'ARMEMENT) des ennemis
qui leur sont adjacents. Un montage ou toutes les candidates scorent pareil rend un accord
natif/port parfaitement lisible et entierement VIDE (regime degenere, cf. runner.md).

Usage : python probe_996r1_geometry_scout.py --state-file <ABSOLU propre>
ASCII only.
"""
from __future__ import annotations

import argparse
import sys

import probe_996r1_devout_push as P


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--place", default=None, help="col,row du CASTER")
    a = ap.parse_args()
    sid = P._sid()
    pp = None
    if a.place:
        c, r = (int(x) for x in a.place.split(","))
        pp = {P.PORTEUR_VIS: (c, r)}
    rid = P._build(sid, a.state_file, None, p_places=pp)
    try:
        cap = P._capture(sid, rid)
        caster = P._by_vis(cap, P.PORTEUR_VIS)
        st = P._state(cap)
        board = st.board
        p0 = P._pos(caster)
        tid = board.id_at(p0[0], p0[1])
        print("[scout] caster %s pos=%s tile=%s" % (caster["id"], p0, tid))
        vois = [board.coord(n) for n in board.neighbours_native(tid)]
        print("[scout] voisins natifs de %s : %s" % (p0, vois))
        occ = {P._pos(u): u.get("visualId") for u in P._units(cap)}
        for v in vois:
            t2 = board.id_at(v[0], v[1])
            if t2 is None:
                print("[scout]   %s : HORS BOARD" % (v,))
                continue
            n2 = [board.coord(n) for n in board.neighbours_native(t2)]
            print("[scout]   %s occ=%r voisins=%s" % (v, occ.get(v), n2))
    finally:
        if not a.keep:
            P._dispose(sid, rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
