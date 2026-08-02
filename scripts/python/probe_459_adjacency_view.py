"""#457-r1 -- MESURE du rayon de souffle des DEUX vues du voisinage, sur des boards REELS.

LE FAIT, tranche au decompile (`rnca9r7q6c`), c'est que les deux lectures mirrorent UN SEUL appel :

    IdunBattle.Core.Services.MovementQuery$$IsAdjacent(a, b) :
        lVar1 = <IBattleQuery slot 0x4f>(this->battleQuery@+0x30, a, 0, 1, 1);
        return lVar1.Contains(b);

    IdunBattle.Core.Services.MovementQuery$$GetPossibleTileListsFromMovableTiles, branche 7 :
        uVar4 = <IBattleQuery slot 0x4f>(this->battleQuery@+0x30, t, 0, 1, 1);
        if (movableTiles.ContainsAll(uVar4)) { s = {t}; s.AddRange(uVar4); res.Add(s); }

-- MEME slot, MEME receveur, MEMES flags. Le port en avait fait DEUX vues du `Board` :
`board.neighbours()` (triee ET symetrisee) pour la premiere, `board.neighbours_native()` (le champ
brut) pour la seconde. La vue JUSTE est la seconde :
`IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles` -> `$$IterateAdjacentTiles` ->
`IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`, dont le `MoveNext` enumere la liste
d'adjacence STOCKEE (`ConnectivityComponent`), jamais une couronne recalculee.

CE QUE CE PROBE MESURE, et pourquoi il faut du LIVE : l'asymetrie vit dans le
`ConnectivityComponent`, qui n'est PAS derivable des dumps `data/boards/` (ils portent la
`BattleConfiguration` : TileId / Elevation / ForceUnplayable, pas la connectivite). Il faut donc
capter le `boardGraph` d'un runner reel, board par board.

Sorties, par board :
  * aretes dirigees stockees, et celles que la SYMETRISATION ajoute ;
  * paires ordonnees dont le verdict d'`is_adjacent` CHANGE (c'est exactement le compte ci-dessus) ;
  * empreintes a 3 pieds (`IsValidUnitFeetList(3, ...)`, permutations comprises -- l'ordre compte
    des que l'adjacence est asymetrique) dont la VALIDITE change ;
  * centres a 7 pieds dont l'anneau change.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_459_adjacency_view.py
    python probe_459_adjacency_view.py --boards MC1_67,C1_74 --state-file <absolu>.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from itertools import combinations, permutations
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

DEFAULT_BOARDS = ("MC1_67", "C1_74", "C2_02", "C4_09", "C1_25", "C2_19")


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, board: str, seed: int = 777) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO (%s) : %s" % (board, (proc.stderr or proc.stdout or "")[-800:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _measure(bg_tiles) -> dict:
    """Toute la mesure est OFFLINE une fois le `boardGraph` capte : on construit DEUX `Board` sur
    les memes tuiles, l'un lu par sa liste stockee, l'autre par la vue symetrisee, et on compare
    les trois consommateurs."""
    from engine.entities.pathfinding.board import Board
    from engine.services import movement_query as MQ

    board = Board(bg_tiles, adjacency="native_sym")
    ids = list(board.by_id)
    stored = {t: set(board.neighbours_native(t)) for t in ids}
    sym = {t: set(board.neighbours(t)) for t in ids}

    n_stored = sum(len(v) for v in stored.values())
    extra = sorted((a, b) for a in ids for b in (sym[a] - stored[a]))

    # --- consommateur 1 : `IsAdjacent`. Le verdict change EXACTEMENT sur `extra`.
    flips = 0
    for a, b in extra:
        pa, pb = board.coord(a), board.coord(b)
        if MQ.is_adjacent(board, pa, pb) is not (b in sym[a]):
            flips += 1

    # --- consommateur 2 : `IsValidUnitFeetList(3, ...)`, PERMUTATIONS comprises.
    #     Le natif teste `IsAdjacent(0,1)`, `(0,2)`, `(1,2)` -- des paires ORDONNEES.
    def _valid(triple, adj) -> bool:
        import hexgeo
        pos = [board.coord(t) for t in triple]
        if len({board.elevation(t) for t in triple}) != 1:
            return False
        for i, j in ((0, 1), (0, 2), (1, 2)):
            if hexgeo.distance(pos[i], pos[j]) != 1:
                return False
            if triple[j] not in adj[triple[i]]:
                return False
        return True

    tri_seen, tri_flip, tri_total = set(), 0, 0
    for a in ids:
        for b, c in combinations(sorted(sym[a]), 2):
            key = tuple(sorted((a, b, c)))
            if key in tri_seen:
                continue
            tri_seen.add(key)
            for perm in permutations(key):
                v_sym = _valid(perm, sym)
                v_nat = _valid(perm, stored)
                if v_sym or v_nat:
                    tri_total += 1
                if v_sym != v_nat:
                    tri_flip += 1

    # --- consommateur 3 : branche `feetCount == 7`, pool = TOUT le board (borne haute).
    pool = [board.coord(t) for t in ids]
    seven_sym = {c[0]: tuple(c[1:])
                 for c in (_combos(board, pool, sym) or [])}
    seven_nat = {c[0]: tuple(c[1:])
                 for c in (MQ.get_possible_tile_lists_from_movable_tiles(board, pool, 7) or [])}
    # DEUX ecarts a ne pas confondre : l'ENSEMBLE des pieds (la symetrisation en ajoute) et leur
    # ORDRE (la vue symetrisee TRIE les ids). L'ordre n'entre pas dans `IsValidUnitFeetList` mais
    # il fixe l'ordre des pieds de la `UnitPosition` produite -- donc il est observable en aval.
    seven_set = sum(1 for k in set(seven_sym) | set(seven_nat)
                    if set(seven_sym.get(k) or ()) != set(seven_nat.get(k) or ()))
    seven_ord = sum(1 for k in set(seven_sym) & set(seven_nat)
                    if seven_sym[k] != seven_nat[k]
                    and set(seven_sym[k]) == set(seven_nat[k]))

    return {"tiles": len(ids), "edges_stored": n_stored, "edges_added_by_sym": len(extra),
            "is_adjacent_flips": flips, "feet3_candidates": tri_total, "feet3_flips": tri_flip,
            "feet7_centres": len(seven_nat), "feet7_set_flips": seven_set,
            "feet7_order_flips": seven_ord}


def _combos(board, tiles, adj):
    """La branche 7 rejouee sur la vue SYMETRISEE -- le bras temoin (ce que faisait le port avant
    #459 pour `is_adjacent`, applique ici a l'autre consommateur pour rendre les deux comparables)."""
    pool = set(tiles)
    out = []
    for t in tiles:
        tid = board.id_at(t[0], t[1])
        if tid is None:
            continue
        nb = [board.coord(x) for x in sorted(adj[tid])]
        if nb and all(x in pool for x in nb):
            out.append([t] + nb)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", default=",".join(DEFAULT_BOARDS))
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    sf = Path(a.state_file) if a.state_file else \
        Path(tempfile.gettempdir()) / ("rl_459_%s.json" % uuid.uuid4().hex[:8])
    sid = _resolve_session()
    rows, errs = [], []
    for b in [x.strip() for x in a.boards.split(",") if x.strip()]:
        rid = None
        try:
            rid = _build(sf, b)
            bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
            if not (isinstance(bg, dict) and bg.get("tiles")):
                raise RuntimeError("boardGraph indispo")
            row = _measure(bg["tiles"])
            row["board"] = b
            rows.append(row)
        except Exception as exc:                                # noqa: BLE001
            errs.append("%s : %s" % (b, exc))
        finally:
            if rid is not None:
                try:
                    _r(sid, "disposeRunner", {"runnerId": rid}, 30)
                except Exception:                               # noqa: BLE001
                    pass
    sf.unlink(missing_ok=True)

    if a.json:
        print(json.dumps({"rows": rows, "errors": errs}, indent=2))
    else:
        print("=== #457-r1 : les DEUX vues du voisinage, sur board REEL ===")
        print("%-12s %6s %8s %8s %8s %10s %8s %7s %8s %8s" % (
            "board", "tiles", "e_stored", "e_+sym", "isAdj!=", "feet3_cand", "feet3!=",
            "f7_ctr", "f7_set!=", "f7_ord!="))
        for r in rows:
            print("%-12s %6d %8d %8d %8d %10d %8d %7d %8d %8d" % (
                r["board"], r["tiles"], r["edges_stored"], r["edges_added_by_sym"],
                r["is_adjacent_flips"], r["feet3_candidates"], r["feet3_flips"],
                r["feet7_centres"], r["feet7_set_flips"], r["feet7_order_flips"]))
        for e in errs:
            print("  [erreur] %s" % e)
    if not rows:
        print("VERDICT: NON MESURE -- aucun board capte")
        return 1
    tot = sum(r["edges_added_by_sym"] for r in rows)
    print("VERDICT: %d board(s) mesure(s), %d arete(s) dirigee(s) ajoutee(s) par la symetrisation"
          % (len(rows), tot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
