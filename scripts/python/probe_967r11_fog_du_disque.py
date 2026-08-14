#!/usr/bin/env python3
"""#967-r11 -- MESURE du gisement `isInFog` et de l'effet OBSERVABLE du filtre FOG du noeud DSL
`SurroundingTiles`. Jumeau exact de `probe_967r10_murs_du_disque.py`, sur le TROISIEME axe.

Les deux questions que le residu ne posait pas, et qui decident s'il est fermable par une mesure :

  (1) **Le substrat est-il la ?** Le residu portait `BLOCAGE: seeding` au motif que la cle
      `isInFog` << n'est pas confrontee ici >>. Or `boardGraph` la publie PAR TUILE, au meme rang
      qu'`isWall` (`frida/hooks/features/ai-step/rpc-board.ts` : `isWall: t.isWall,
      isInFog: t.isInFog ?? false`). Cet etage le VERIFIE sur des boards reels au lieu de le
      supposer -- et `porte_cle` distingue << 0 tuile en fog >> de << cle absente >>.

  (2) **Le filtre change-t-il un ensemble que les call-sites regardent ?** TROIS regimes, qui ne
      se valent pas :
        (a) `isInFog = True, walkable = False` -- deja coupe par le gate walkable LA OU IL EST
            ARME (1 call-site sur 7). Ailleurs, le fog est le SEUL a couper.
        (b) `isInFog = True, walkable = True`  -- le regime DISCRIMINANT, celui qui prouve que le
            fog n'est pas rabattable sur la marchabilite. Mesure #433-r4 : 31 tuiles sur 63 du
            board `C6_02`.
        (c) `isInFog = False, walkable = False` -- Block/Water : le natif les GARDE sous
            `includeNonWalkable = 1`, et le filtre fog ne doit PAS y toucher.

  (3) **VALUE-PRESERVING** : la colonne `sans_fog` compte les boards a ZERO tuile en brouillard.
      Sur ceux-la le correctif est un NO-OP EXACT, et c'est ce qui borne le rayon de souffle.

Sortie ASCII stricte. Ne modifie rien, ne monte qu'un runner a la fois et le dispose.

Usage :
    python probe_967r11_fog_du_disque.py --boards MC1_67,C6_02,C6_09,C3_01 --state-file <abs>
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


def _build(seed, board, state_file, p_units=None, a_units=None):
    """⚠ Le nombre d'unites n'est PAS libre : un board dont le `SpawnPointSet` porte moins de
    points que d'unites fait echouer le build (`spawns joueur < N units`). Les boards `C6_*` --
    les SEULS du corpus a porter du brouillard -- en ont 3 ou 4, la ou le defaut en monte 5.
    Sans `--p-units`, ils sortiraient en `BUILD KO` et le probe conclurait << 0 tuile en fog >>
    sur un board qu'il n'a jamais mesure : une NON-MESURE lue comme un zero."""
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board]
    if p_units:
        cmd += ["--p-units", p_units]
    if a_units:
        cmd += ["--a-units", a_units]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("  BUILD KO (%s): %s" % (board, (proc.stderr or proc.stdout or "")[-400:]))
        return None
    return json.loads(Path(state_file).read_text())["runnerId"]


def _mesure_board(tiles):
    """Ventilation des 3 regimes + effet du filtre FOG sur tous les disques de rayon 1 et 2.

    L'effet est mesure PAR DIFFERENCE : disque AVEC le gate fog (le port courant) contre le meme
    disque en NEUTRALISANT ce seul gate (`_is_in_fog` force a `False`). On isole donc le fog des
    deux autres axes -- comparer au disque `hexgeo.disk` PUR melangerait mur, fog et walkable."""
    from engine.entities.pathfinding.board import Board
    from engine.entities.selectors.accessors import FixedTileIds, SurroundingTiles
    from engine.dsl.base import Const

    board = Board(tiles, adjacency="native_sym")

    def _w(t):
        return bool(t.get("walkable"))

    def _if(t):
        return bool(t.get("isInFog"))

    n = len(tiles)
    porte_cle = sum(1 for t in tiles if "isInFog" in t)
    a = sum(1 for t in tiles if _if(t) and not _w(t))
    b = sum(1 for t in tiles if _if(t) and _w(t))
    c = sum(1 for t in tiles if not _if(t) and not _w(t))

    class _Ctx:
        board = None

    ctx = _Ctx()
    ctx.board = board

    class _SansFog(SurroundingTiles):
        """Le MEME noeud, gate fog NEUTRALISE -- l'etat d'AVANT #967-r11, et lui seul."""
        def _is_in_fog(self, board, tid):
            return False

    effet = {}
    for r in (1, 2):
        centres_touches = 0
        retirees = 0
        for tid in board.by_id:
            avec = list(SurroundingTiles(FixedTileIds([tid]), Const(r), include_center=False,
                                         include_non_walkable=True).select(ctx))
            sans = list(_SansFog(FixedTileIds([tid]), Const(r), include_center=False,
                                 include_non_walkable=True).select(ctx))
            d = len(sans) - len(avec)
            if d:
                centres_touches += 1
                retirees += d
        effet[r] = (centres_touches, retirees)
    return dict(n=n, porte_cle=porte_cle, fog_non_walkable=a, fog_walkable=b,
                nonwalk_non_fog=c, effet=effet)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", default="MC1_67,C6_02,C6_09,C3_01")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--p-units", default=None,
                    help="obligatoire sur les boards a peu de spawns (C6_*) -- cf. `_build`")
    ap.add_argument("--a-units", default=None)
    args = ap.parse_args()

    rpc = _rpc()
    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    sf = args.state_file or str(ROOT / "logs" / "runners" /
                                ("p967r11-%s.json" % uuid.uuid4().hex[:8]))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)

    print("BOARD              tiles  cle_isInFog  fog&!walk  fog&walk  !fog&!walk   "
          "r1(centres/retirees)  r2(centres/retirees)")
    total_fog = 0
    sans_fog = []
    non_mesures = []
    for b in boards:
        rid = _build(args.seed, b, sf, args.p_units, args.a_units)
        if rid is None:
            non_mesures.append(b)
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
            non_mesures.append(b)
            continue
        m = _mesure_board(tiles)
        f = m["fog_non_walkable"] + m["fog_walkable"]
        total_fog += f
        if f == 0:
            sans_fog.append(b)
        print("%-18s %5d  %11d  %9d  %8d  %10d   %8s              %8s" % (
            b, m["n"], m["porte_cle"], m["fog_non_walkable"], m["fog_walkable"],
            m["nonwalk_non_fog"],
            "%d/%d" % m["effet"][1], "%d/%d" % m["effet"][2]))
    print()
    mesures = len(boards) - len(non_mesures)
    print("PORTEE : %d board(s) MESURE(S) sur %d demande(s)." % (mesures, len(boards)))
    if non_mesures:
        # Un board qui n'a pas pu etre monte n'est PAS un board a zero tuile en fog. Le confondre
        # ferait lire une NON-MESURE comme un value-preserving.
        print("   NON MESURE(S) -- BUILD KO ou boardGraph muet, ce n'est PAS un zero : %s"
              % non_mesures)
    print("TOTAL tuiles en BROUILLARD sur les boards MESURES : %d" % total_fog)
    print("VALUE-PRESERVING : %d board(s) MESURE(S) a ZERO tuile en fog -> le correctif y est un "
          "NO-OP EXACT : %s" % (len(sans_fog), sans_fog or "(aucun)"))
    if mesures == 0:
        print("ATTENTION : AUCUN board mesure -- ce run ne dit RIEN, ni dans un sens ni dans "
              "l'autre.")
        return 2
    if total_fog == 0:
        print("ATTENTION : temoin NUL. Un filtre qui ne retire rien ne se confronte pas -- "
              "il faut soit un autre board, soit conclure que le gate est INERTE sur ce corpus.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
