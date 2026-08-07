#!/usr/bin/env python
"""#515 (residu `#497-r1`) -- RAYON DE SOUFFLE de la reparation d'adjacence du RUNNER.

QUESTION BINAIRE : `engine/dsl/base.py::_within` decide l'appartenance par
`hexgeo.distance <= r`. Le natif ne fait pas ca. Combien de sites, et combien de
CONFIGURATIONS, changent de resultat si on branche l'etage `adjacent` sur la
primitive juste ?

CE QUE LE NATIF FAIT, LU (pas suppose) --
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` :

    elev0 = tile[+0x20][+0x18];                                  // d__8+0x48, lu UNE fois
    foreach (nid in tile[+0x30][+0x10])                           // ConnectivityComponent.Neighbours
        t = state.GetTileEntity(nid); if (t == null) continue;
        if (!allowTemporary  && IsTemporary(t))        continue;
        if ( onlyWalkable    && !IsWalkable(t, true))  continue;
        if ( onlyEmptyOrStep && !IsEmptyOrSteppable(t)) continue;
        if (Math.Abs(elev0 - t[+0x20][+0x18]) < 2) yield return t;   // porte INCONDITIONNELLE

Deux etages, dans cet ordre : (1) une ENUMERATION de la liste STOCKEE ; (2) une PORTE
`|dElev| < 2`. La porte prend la VALEUR ABSOLUE -> elle est SYMETRIQUE, donc portee par la
PAIRE, jamais par l'arete. (L'asymetrie possible vient du substrat, pas de la porte :
`InitializeConnectivityOperation$$Execute` exige `HasEdge` des DEUX cotes, donc le substrat
est symetrique par construction lui aussi -- mesure `#433-r4-r1-r4-r2`, 0 arete one-way.)

CE QUE LE NATIF NE FAIT PAS -- et c'est la BORNE de la reparation.
`IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` (le
rayon quelconque) est une TRIPLE BOUCLE CUBE (`dx`,`dy`,`dz` avec `x+y+z == 0`) qui resout
chaque coordonnee par `StateExtensions$$GetTileAt` : **aucune liste stockee, aucune porte
d'elevation**. Donc `order='surrounding'` DOIT rester en distance hex, et une "unification"
des deux primitives serait un BUG, pas une reparation.

ETAGES
  [1] SITES      -- recensement AST des instanciations `Adjacent*`/`Surrounding*` dans
                    `engine/**`, et des call-sites de `_within` par `order`.
  [2] TOPOLOGIE  -- sur les 675 boards de `data/boards/global/`, combien d'aretes de la
                    couronne hex la porte d'elevation REFUSE ? C'est la borne INFERIEURE de
                    la sur-atteinte (le refus `HasEdge` du substrat s'y ajoute, et il n'est
                    pas derivable offline). Donne la variable independante : le DENIVELE.
  [3] MONOTONIE  -- pour chaque tuile de chaque board a denivele, l'ensemble « couronne hex
                    ET porte » est-il TOUJOURS inclus dans « couronne hex » ? La reparation
                    ne peut que RETIRER : c'est ce qui rend le rayon de souffle borne.
  [4] SENSIBLES  -- combien de tuiles voient leur voisinage CHANGER, sur combien de boards.
                    Une unite posee sur une de ces tuiles est un temoin de la divergence.

ASCII only (cp1252). Offline pur : aucun runner, aucun RPC.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from board import _effective_elevation  # noqa: E402

BOARDS = ROOT / "data" / "boards" / "global"
ENGINE = Path(__file__).resolve().parent / "engine"

# Les six selecteurs de voisinage du port, ventiles par l'`order` qu'ils passent a `_within`
# (lu au site, pas devine) -- cf. `engine/entities/selectors/units.py`.
SEL_ADJACENT = ("AdjacentUnits", "AdjacentEnemies", "AdjacentFriends")
SEL_SURROUNDING = ("SurroundingUnits", "SurroundingEnemies", "SurroundingFriends")


# --------------------------------------------------------------------------- etage 1
def etage1_sites() -> dict:
    """Recensement AST des INSTANCIATIONS (pas des mentions en docstring : le grep textuel
    rendait 450 la ou l'AST en compte bien moins)."""
    par_nom: Counter = Counter()
    par_fichier: Counter = Counter()
    fichiers_adj: set[str] = set()
    for f in sorted(ENGINE.rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = f.relative_to(ENGINE.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            nom = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if nom in SEL_ADJACENT or nom in SEL_SURROUNDING:
                par_nom[nom] += 1
                par_fichier[rel] += 1
                if nom in SEL_ADJACENT:
                    fichiers_adj.add(rel)
    adj = sum(par_nom[n] for n in SEL_ADJACENT)
    sur = sum(par_nom[n] for n in SEL_SURROUNDING)
    return {"par_nom": dict(par_nom), "par_fichier": dict(par_fichier),
            "adjacent": adj, "surrounding": sur, "fichiers_adjacent": sorted(fichiers_adj)}


# --------------------------------------------------------------------------- boards
def charger_board(path: Path) -> dict:
    """`{(col,row): elevation_effective}` depuis un board de `data/boards/global/`.

    L'elevation EFFECTIVE (`board._effective_elevation`) est ce que le jeu expose
    (`TileExtensions$$GetElevation`) : `Trench` = champ BC - 1, les autres a l'identique.
    C'est bien cette valeur-la que lit la porte (`tile[+0x20][+0x18]`)."""
    d = json.loads(path.read_text(encoding="utf-8"))
    board = d.get("board") or {}
    elev: dict[tuple[int, int], int] = {}
    for col, colonne in enumerate(board.get("Tiles") or []):
        for row, t in enumerate((colonne or {}).get("Tile") or []):
            if not isinstance(t, dict):
                continue
            if t.get("ForceUnplayable"):
                continue
            elev[(col, row)] = _effective_elevation(t.get("TileId"), t.get("Elevation"))
    return elev


def couronne(elev: dict, pos: tuple) -> list[tuple]:
    """Les voisins de `pos` au sens du PORT ACTUEL : `hexgeo.distance == 1` sur les tuiles
    presentes. C'est exactement ce que `_within(..., radius=1)` retient aujourd'hui."""
    return [p for p in elev if p != pos and hexgeo.distance(pos, p) == 1]


# --------------------------------------------------------------------------- etages 2-4
def etage234(limite: int | None = None) -> dict:
    boards = sorted(BOARDS.glob("*.json"))
    if limite:
        boards = boards[:limite]
    total_aretes = 0
    total_refusees = 0
    par_board: list[tuple[str, int, int, int]] = []   # (id, aretes, refusees, tuiles touchees)
    violations_monotonie = 0
    for path in boards:
        elev = charger_board(path)
        if not elev:
            continue
        aretes = 0
        refusees = 0
        touchees = set()
        for pos, e0 in elev.items():
            voisins = couronne(elev, pos)
            garde = [p for p in voisins if abs(e0 - elev[p]) < 2]
            aretes += len(voisins)
            refus = len(voisins) - len(garde)
            refusees += refus
            # etage 3 : MONOTONIE -- l'ensemble garde est-il inclus dans la couronne ?
            if not set(garde) <= set(voisins):
                violations_monotonie += 1
            if refus:
                touchees.add(pos)
        total_aretes += aretes
        total_refusees += refusees
        par_board.append((path.stem, aretes, refusees, len(touchees)))
    par_board.sort(key=lambda r: -r[2])
    sensibles = [r for r in par_board if r[2] > 0]
    return {"boards": len(par_board), "aretes": total_aretes, "refusees": total_refusees,
            "violations_monotonie": violations_monotonie,
            "boards_sensibles": len(sensibles), "top": par_board[:15],
            "par_board": {r[0]: r for r in par_board}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=None, help="n premiers boards (debug)")
    ap.add_argument("--board", action="append", default=[], help="detailler ce board")
    args = ap.parse_args()

    print("=" * 78)
    print("#515 -- RAYON DE SOUFFLE de la porte d'elevation sur l'adjacence du RUNNER")
    print("=" * 78)

    s = etage1_sites()
    print("\n[1] SITES (AST, instanciations reelles -- pas les mentions en docstring)")
    print("    order='adjacent'    (porte NATIVE : liste stockee + |dElev| < 2) : %d" % s["adjacent"])
    print("    order='surrounding' (balayage CUBE, AUCUNE porte)                : %d" % s["surrounding"])
    for nom in SEL_ADJACENT + SEL_SURROUNDING:
        print("      %-20s %d" % (nom, s["par_nom"].get(nom, 0)))
    print("    fichiers portant au moins un site 'adjacent' : %d" % len(s["fichiers_adjacent"]))
    top = sorted(s["par_fichier"].items(), key=lambda kv: -kv[1])[:12]
    for f, n in top:
        print("      %-64s %d" % (f, n))

    m = etage234(args.limite)
    print("\n[2] TOPOLOGIE -- porte d'elevation sur la couronne hex, %d boards" % m["boards"])
    print("    aretes dirigees de couronne : %d" % m["aretes"])
    print("    REFUSEES par |dElev| >= 2   : %d  (%.2f %%)"
          % (m["refusees"], 100.0 * m["refusees"] / max(1, m["aretes"])))
    print("    boards ou la porte MORD     : %d / %d  (%.1f %%)"
          % (m["boards_sensibles"], m["boards"], 100.0 * m["boards_sensibles"] / max(1, m["boards"])))
    print("    NB : borne INFERIEURE -- le refus `HasEdge` du substrat n'est pas derivable")
    print("         offline (il vit dans le `boardGraph` capte live).")

    print("\n[3] MONOTONIE -- l'ensemble repare est-il toujours INCLUS dans l'actuel ?")
    print("    violations : %d  (attendu 0 : la porte ne peut que RETIRER)" % m["violations_monotonie"])

    print("\n[4] TUILES SENSIBLES -- top 15 boards par aretes refusees")
    print("    %-12s %8s %10s %10s" % ("board", "aretes", "refusees", "tuiles"))
    for bid, ar, rf, tu in m["top"]:
        print("    %-12s %8d %10d %10d" % (bid, ar, rf, tu))

    for b in args.board:
        r = m["par_board"].get(b)
        if r is None:
            print("\n    board %s : ABSENT de la mesure" % b)
            continue
        print("\n    %s : %d aretes, %d refusees, %d tuiles touchees" % (b, r[1], r[2], r[3]))
        elev = charger_board(BOARDS / (b + ".json"))
        for pos in sorted(elev):
            perdus = [p for p in couronne(elev, pos) if abs(elev[pos] - elev[p]) >= 2]
            if perdus:
                print("      (%2d,%2d) elev=%d  perd %s"
                      % (pos[0], pos[1], elev[pos], sorted(perdus)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
