"""#433-r4-r1-r4 -- PERIMETRE MESURE de la porte d'elevation `|dElev| < 2` cote SUBSTRAT DSL RUNNER.

Ce que ce probe est SEUL a etablir, en chiffres re-derives du code et des entrees versionnees :

  * etape `readers`  -- qui LIT `ctx.elev_by_pos` dans le substrat DSL (`engine/entities/**`,
    `engine/dsl/**`), et qui construit un `DslContext` SANS le poser (donc degrade en no-op
    PERMISSIF). Balayage AST, jamais un grep de prose.
  * etape `boards`   -- sur combien de boards VERSIONNES (`data/boards/**`) la porte peut
    MORDRE : nombre d'aretes du graphe d'adjacence NATIF (`boardGraph.neighbours`) dont
    `|dElev| >= 2`. Un board a zero arete de ce type rendrait un test VERT pour la mauvaise
    raison.
  * etape `flips`    -- sur un board donne, combien de verdicts d'adjacence CHANGENT entre
    `elev_by_pos=None` (l'etat d'avant) et la carte reelle du board (l'etat d'apres), pour
    les DEUX primitives (`battle_query.is_adjacent`, `.are_entities_adjacent`).

Sorties ASCII uniquement (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_REPO = os.path.dirname(os.path.dirname(_HERE))
_ENGINE = os.path.join(_HERE, "engine")
_BOARDS = os.path.join(_REPO, "data", "boards")


# ------------------------------------------------------------------------------------------------
# etape 1 -- READERS / BUILDERS de `elev_by_pos` (AST, pas de grep de prose)
# ------------------------------------------------------------------------------------------------
def _py_files(root: str):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(base, f)


def scan_readers(verbose: bool = True) -> dict:
    """Balaye `engine/**` : lectures d'attribut `.elev_by_pos` et constructions `DslContext(...)`."""
    readers, builders = [], []
    for path in _py_files(_ENGINE):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        except SyntaxError:
            continue
        rel = os.path.relpath(path, _REPO).replace("\\", "/")
        for node in ast.walk(tree):
            # lecture `<x>.elev_by_pos`
            if isinstance(node, ast.Attribute) and node.attr == "elev_by_pos":
                readers.append((rel, node.lineno, ast.unparse(node)))
            # lecture `getattr(<x>, "elev_by_pos", ...)`
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr" and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value == "elev_by_pos"):
                readers.append((rel, node.lineno, ast.unparse(node)))
            # construction `DslContext(...)`
            if isinstance(node, ast.Call):
                fname = None
                if isinstance(node.func, ast.Name):
                    fname = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    fname = node.func.attr
                if fname == "DslContext":
                    kws = {k.arg for k in node.keywords if k.arg}
                    builders.append((rel, node.lineno, "elev_by_pos" in kws, "board" in kws))
    if verbose:
        print("--- LECTEURS de elev_by_pos dans engine/ ---")
        for rel, ln, src in sorted(readers):
            print("  %s:%d  %s" % (rel, ln, src[:90]))
        print("--- CONSTRUCTEURS de DslContext ---")
        for rel, ln, has_elev, has_board in sorted(builders):
            print("  %s:%d  elev_by_pos=%s  board=%s" % (rel, ln, has_elev, has_board))
        n_inert = sum(1 for _r, _l, e, b in builders if not e and b)
        print("BILAN: %d lecteurs, %d constructeurs, %d passent le board SANS kwarg elev"
              % (len(readers), len(builders), n_inert))
        # ATTESTATION DYNAMIQUE : un kwarg absent ne veut plus dire « canal inerte » depuis
        # #433-r4-r1-r4 -- `DslContext.__post_init__` le DERIVE du board. On le PROUVE ici plutot
        # que de le deduire du balayage statique, qui ne peut pas le voir.
        from engine.dsl.base import DslContext
        from engine.entities.pathfinding.board import Board
        tiles = [{"id": c * 3 + r + 1, "col": c, "row": r, "elevation": (3 if (c, r) == (1, 1) else 0),
                  "walkable": True, "neighbours": []} for c in range(3) for r in range(3)]
        derived = DslContext(board=Board(tiles, adjacency="evenq")).elev_by_pos
        print("DERIVATION: board fourni -> elev_by_pos %s (%d tuiles) ; sans board -> %s"
              % ("POSE" if derived else "ABSENT", len(derived or ()),
                 DslContext().elev_by_pos))
    return {"readers": readers, "builders": builders}


# ------------------------------------------------------------------------------------------------
# etape 2 -- BOARDS : ou la porte peut-elle MORDRE ?
# ------------------------------------------------------------------------------------------------
def load_board_elevations(path: str) -> dict:
    """`{(col,row): elevation EFFECTIVE}` depuis un board VERSIONNE (`data/boards/<pool>/<id>.json`,
    forme `BC.Board.Tiles[col].Tile[row]`). L'elevation effective passe par
    `board._effective_elevation` (regle Trench = champ BC - 1, #195) -- le MEME calcul que ce que
    le `boardGraph` live baked, donc ce que lira `state.board` cote runner. Les tuiles
    `ForceUnplayable` sont ECARTEES (elles ne portent aucune unite)."""
    from board import _effective_elevation
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    b = (raw.get("board") or raw.get("Board") or {})
    out = {}
    for c, col in enumerate(b.get("Tiles") or []):
        for r, t in enumerate((col or {}).get("Tile") or []):
            if t is None or bool(t.get("ForceUnplayable")):
                continue
            out[(c, r)] = _effective_elevation(t.get("TileId"), t.get("Elevation", 0))
    return out


def board_relief(path: str) -> dict:
    """Sur combien de PAIRES VOISINES (couronne hex even-q, restreinte au board) la porte
    `|dElev| >= 2` mord-elle ? C'est la borne HAUTE du gisement d'un board : `IterateAdjacentTiles`
    part de la liste stockee (`ConnectivityComponent`), qui est incluse dans la geometrie."""
    import hexgeo
    elev = load_board_elevations(path)
    edges = biting = 0
    pairs = []
    for p, a in elev.items():
        for q in hexgeo.neighbors(p[0], p[1]):
            if q not in elev:
                continue
            edges += 1
            b = elev[q]
            if abs(int(a) - int(b)) >= 2:
                biting += 1
                pairs.append((p, q, int(a), int(b)))
    return {"edges": edges, "biting": biting,
            "levels": sorted(set(elev.values())),
            "pairs": pairs, "tiles": len(elev)}


def scan_boards(pool: str | None = None, top: int = 25, verbose: bool = True) -> list:
    pools = [pool] if pool else ["global", "pvp", "syncPvp"]
    rows = []
    for p in pools:
        d = os.path.join(_BOARDS, p)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".json"):
                continue
            info = board_relief(os.path.join(d, name))
            rows.append((p, name[:-5], info["tiles"], info["edges"], info["biting"],
                         info["levels"]))
    rows.sort(key=lambda r: -r[4])
    if verbose:
        n_bite = sum(1 for r in rows if r[4] > 0)
        print("--- BOARDS versionnes : ou la porte |dElev| >= 2 MORD ---")
        print("total=%d  avec au moins 1 arete gatee=%d" % (len(rows), n_bite))
        for r in rows[:top]:
            print("  %-8s %-28s tiles=%-4d aretes=%-4d gatees=%-4d niveaux=%s"
                  % (r[0], r[1], r[2], r[3], r[4], r[5]))
    return rows


# ------------------------------------------------------------------------------------------------
# etape 3 -- FLIPS : combien de verdicts changent, primitive par primitive
# ------------------------------------------------------------------------------------------------
def scan_flips(board_id: str, pool: str = "global", verbose: bool = True) -> dict:
    import hexgeo
    from engine import battle_query as bq
    path = os.path.join(_BOARDS, pool, board_id + ".json")
    elev_by_pos = load_board_elevations(path)
    flips_is_adj = flips_are_adj = tested = 0
    for a in elev_by_pos:
        for b in hexgeo.neighbors(a[0], a[1]):
            if b not in elev_by_pos:
                continue
            tested += 1
            if bq.is_adjacent(a, b, None) != bq.is_adjacent(a, b, elev_by_pos):
                flips_is_adj += 1
            if (bq.are_entities_adjacent(a, b, None)
                    != bq.are_entities_adjacent(a, b, elev_by_pos)):
                flips_are_adj += 1
    out = {"board": board_id, "tested": tested, "is_adjacent": flips_is_adj,
           "are_entities_adjacent": flips_are_adj}
    if verbose:
        print("--- FLIPS sur %s (%s) ---" % (board_id, pool))
        print("  paires voisines testees      : %d" % tested)
        print("  is_adjacent flips            : %d" % flips_is_adj)
        print("  are_entities_adjacent flips  : %d" % flips_are_adj)
    return out


# ------------------------------------------------------------------------------------------------
# etape 4 -- MONTAGE : quel board VERSIONNE admet la confrontation live de `UnitsDirectlyBehind` ?
# ------------------------------------------------------------------------------------------------
def scan_montage(pool: str | None = None, rng: int = 3, top: int = 12,
                 verbose: bool = True) -> list:
    """Cherche, board par board, un quadruplet (caster, target, behindHigh, behindFlat) qui rend le
    gate `TilesOnSameElevationSelector` (maxDiff = 1) OBSERVABLE sur le splash de
    `PlasmaCannonAbility$$ExecuteBehaviour` :

      * `1 <= dist(caster, target) <= rng`             (portee de l'ability, gameconfig `range`)
      * `behindHigh` et `behindFlat` sur l'anneau R1 de `target`, tous DEUX strictement plus loin
        du caster que la cible (`MinDistance(caster, cand) > MinDistance(caster, target)`, STRICT --
        c'est `AmountIsGreater`, la laterale a distance EGALE est exclue, #48)
      * `|elev(behindHigh) - elev(target)| >= 2`       -> le natif l'EXCLUT du pool
      * `|elev(behindFlat) - elev(target)| <= 1`       -> le natif le GARDE

    Le pool de splash passe donc de 2 a 1 unite : discriminant a 1 bit, lisible aux events de degat.
    C'est le montage que le port d'AVANT #433-r4-r1-r4 rendait a 2."""
    import hexgeo
    pools = [pool] if pool else ["global", "pvp", "syncPvp"]
    found = []
    for p in pools:
        d = os.path.join(_BOARDS, p)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".json"):
                continue
            elev = load_board_elevations(os.path.join(d, name))
            hit = None
            for tgt, te in elev.items():
                ring = [q for q in hexgeo.neighbors(tgt[0], tgt[1]) if q in elev]
                high = [q for q in ring if abs(elev[q] - te) >= 2]
                flat = [q for q in ring if abs(elev[q] - te) <= 1]
                if not high or not flat:
                    continue
                for cas, ce in elev.items():
                    dct = hexgeo.distance(cas, tgt)
                    if dct < 1 or dct > rng:
                        continue
                    h = next((q for q in high if hexgeo.distance(cas, q) > dct), None)
                    f = next((q for q in flat if hexgeo.distance(cas, q) > dct), None)
                    if h is not None and f is not None:
                        hit = (cas, tgt, h, f, te, elev[h], elev[f])
                        break
                if hit:
                    break
            if hit:
                found.append((p, name[:-5]) + hit)
    if verbose:
        print("--- MONTAGE live de UnitsDirectlyBehind (splash PlasmaCannon, range=%d) ---" % rng)
        print("boards versionnes qui l'admettent : %d" % len(found))
        for r in found[:top]:
            print("  %-8s %-24s caster=%s target=%s(elev %d) behindHIGH=%s(elev %d) "
                  "behindFLAT=%s(elev %d)"
                  % (r[0], r[1], r[2], r[3], r[6], r[4], r[7], r[5], r[8]))
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", choices=["readers", "boards", "flips", "montage", "all"],
                    default="all")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--pool", default="global")
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args(argv)
    if a.step in ("readers", "all"):
        scan_readers()
    if a.step in ("boards", "all"):
        scan_boards(top=a.top)
    if a.step in ("flips", "all"):
        scan_flips(a.board, a.pool)
    if a.step in ("montage", "all"):
        scan_montage(top=a.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
