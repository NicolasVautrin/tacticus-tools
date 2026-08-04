"""#448-r1-r1-r1-r1-r2 -- CONFRONTATION du capteur `ConnectivityComponent` BRUT (#466).

LE CRITERE, pose AVANT la methode
---------------------------------
Prouver qu'un champ EXISTE ne prouve pas qu'il TRANSPORTE. Le capteur ajoute a `boardGraph`
un canal `connectivity` (la liste du `ConnectivityComponent`, sans porte d'elevation) a cote du
champ `neighbours` herite (`BattleQuery$$GetAdjacentTiles`, qui porte la porte). Question
binaire : **le canal transporte-t-il quelque chose que `neighbours` ne transporte pas ?**

Le cran qui discrimine est un ECART NON NUL -- `connectivityEdges - neighbourEdges == +18` sur
`MC1_67`. Un `0` serait un accord DEGENERE (les deux canaux liraient la meme chose, donc le
capteur ne mordrait pas), et non une confirmation.

CE QUE CHAQUE CRAN TRANCHE : cf. `docs/rl/case-448-r1-r1-r1-r1-flying-tiles-moved.md` §13.4.
Les sept crans y sont ecrits AVANT la mesure ; ce probe ne fait que les jouer.

VENTILATION DANS LES DEUX SENS -- le point que le plan sous-entend sans l'ecrire : un delta
scalaire de `+18` est compatible avec `+20 / -2`. Le probe compte donc SEPAREMENT
`connectivity \\ neighbours` (la porte d'elevation amputait) et `neighbours \\ connectivity`
(la geometrie sur-genere -- les `Bridge` de `C1_74`), et n'accepte le cran 4 que si le second
est nul sur `MC1_67`.

Usage (session warmee) :
    python probe_448r1r1r1r1r2_connectivity_channel_live.py                # les 3 boards
    python probe_448r1r1r1r1r2_connectivity_channel_live.py --board MC1_67
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))

# `MC1_67` = le board de la mesure de reference (§9). `C1_74` porte les deux `Bridge` du cran 6.
# `C6_25` porte des murs (temoin : la porte d'elevation n'y est pas le seul relief).
BOARDS = ("MC1_67", "C1_74", "C6_25")


def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=180):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int) -> tuple[int, pathlib.Path]:
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p448r1r1r1r1r2_state_%s.json" % board)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--no-ai", "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        sys.stdout.write((p.stdout or "")[-1200:])
        sys.stdout.write((p.stderr or "")[-1200:])
        raise SystemExit("build KO (%s)" % board)
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), state_file


def _ventiler(res: dict) -> dict:
    """Ecart ARETE PAR ARETE, dans les DEUX sens, avec l'elevation des deux bouts.

    Tri-etat respecte : une tuile dont `connectivity` est `None` (composant absent) n'entre
    dans AUCUN des deux comptes -- elle est comptee a part (`sans_composant`)."""
    tiles = res.get("tiles") or []
    by_id = {t["id"]: t for t in tiles}
    manquantes, conn_only, geom_only = [], [], []
    for t in tiles:
        conn = t.get("connectivity")
        if conn is None:
            manquantes.append(t["id"])
            continue
        neigh = set(t.get("neighbours") or [])
        cset = set(conn)
        for nid in sorted(cset - neigh):
            conn_only.append((t, by_id.get(nid)))
        for nid in sorted(neigh - cset):
            geom_only.append((t, by_id.get(nid)))
    return {"conn_only": conn_only, "geom_only": geom_only, "sans_composant": manquantes}


def _fmt(a: dict | None, b: dict | None) -> str:
    def one(x):
        if x is None:
            return "?"
        return "(%d,%d)e%s%s" % (x["col"], x["row"], x.get("elevation"),
                                 "/W" if x.get("isWall") else "")
    d = "?"
    if a is not None and b is not None:
        d = str(abs(int(a.get("elevation") or 0) - int(b.get("elevation") or 0)))
    return "%s -> %s  |delev|=%s" % (one(a), one(b), d)


def run_board(sid, rpc, board: str, seed: int, verbose: bool) -> tuple[int, dict]:
    rid, state_file = _build(board, seed)
    bad = 0
    try:
        res = rpc(sid, "boardGraph", {"runnerId": rid}, 180)
        if not res.get("ok"):
            print("  boardGraph KO: %s" % res.get("error"))
            return 1, {}
        (LOGSDIR / ("p448r1r1r1r1r2_boardgraph_%s.json" % board)).write_text(
            json.dumps(res), encoding="utf-8")

        # --- cran 1 : la classe est-elle resolue ? Premier a lire : sans elle rien n'est
        #     interpretable (le canal serait `null` partout, indiscernable d'un plateau nu).
        cls_ok = res.get("connectivityClassResolved")
        print("  [1] connectivityClassResolved = %s   (attendu True)" % cls_ok)
        bad += 0 if cls_ok is True else 1

        # --- cran 2 : le LAYOUT. Le capteur publie ce qu'il a OBSERVE, pas ce qu'il suppose.
        lay = res.get("connectivityLayout")
        print("  [2] connectivityLayout.resolved = %s  listOffset=%s teleportOffset=%s"
              % (None if lay is None else lay.get("resolved"),
                 None if lay is None else lay.get("listOffset"),
                 None if lay is None else lay.get("teleportOffset")))
        for f in ((lay or {}).get("fields") or []):
            print("        champ %-14s @0x%02x  type=%s" % (f.get("name"), f.get("offset"),
                                                            f.get("type")))
        if lay and (lay.get("note") or ""):
            print("        note: %s" % lay.get("note"))
        # Le cran porte sur les OFFSETS EFFECTIVEMENT UTILISES, pas sur le drapeau `resolved` :
        # un repli qui tombe sur les bons offsets rend des mesures justes. On CONFRONTE donc les
        # offsets utilises aux champs DECLARES par le runtime -- c'est l'arbitre du plan.
        decl = {f.get("name"): f.get("offset") for f in ((lay or {}).get("fields") or [])}
        want_list = decl.get("NeighbourIds")
        want_tel = decl.get("TeleportTileId")
        if lay is None:
            print("        ECART: layout non publie -> mesures 3-7 non interpretables")
            bad += 1
        else:
            if want_list is not None and lay.get("listOffset") != want_list:
                print("        ECART: listOffset=%s != NeighbourIds@0x%02x DECLARE"
                      % (lay.get("listOffset"), want_list))
                bad += 1
            if want_tel is not None and lay.get("teleportOffset") != want_tel:
                print("        ECART: teleportOffset=%s != TeleportTileId@0x%02x DECLARE"
                      % (lay.get("teleportOffset"), want_tel))
                bad += 1

        # --- cran 3 : des tuiles SANS composant seraient a nommer, jamais a moyenner.
        miss = res.get("connectivityMissing")
        over = res.get("connectivityOversize")
        print("  [3] connectivityMissing = %s (attendu 0) ; connectivityTiles = %s / %s ; "
              "connectivityOversize = %s (attendu 0)"
              % (miss, res.get("connectivityTiles"), res.get("tileCount"), over))
        bad += 0 if miss == 0 else 1
        bad += 0 if over == 0 else 1

        # --- cran 4/5/6 : la VENTILATION, dans les deux sens.
        ce, ne = res.get("connectivityEdges"), res.get("neighbourEdges")
        delta = None if (ce is None or ne is None) else ce - ne
        v = _ventiler(res)
        print("  [4] connectivityEdges=%s neighbourEdges=%s  DELTA=%s" % (ce, ne, delta))
        print("      ventilation : conn_only=%d  geom_only=%d  (delta net = %d)"
              % (len(v["conn_only"]), len(v["geom_only"]),
                 len(v["conn_only"]) - len(v["geom_only"])))
        if delta is not None and delta != len(v["conn_only"]) - len(v["geom_only"]):
            print("      ECART: le delta scalaire ne se ventile pas -- compteurs incoherents")
            bad += 1

        # cran 5 : les aretes que la porte d'elevation AMPUTAIT. Toutes doivent avoir
        # |delev| >= 2 (c'est exactement ce que `TileQuery$$IterateAdjacentTiles` filtre).
        mauvaises = [(a, b) for (a, b) in v["conn_only"]
                     if a is not None and b is not None
                     and abs(int(a.get("elevation") or 0) - int(b.get("elevation") or 0)) < 2]
        print("  [5] aretes conn_only avec |delev| < 2 : %d (attendu 0)" % len(mauvaises))
        bad += 0 if not mauvaises else 1
        if verbose or mauvaises:
            for (a, b) in (mauvaises or v["conn_only"])[:24]:
                print("        %s" % _fmt(a, b))

        # cran 6 : le sens INVERSE -- la geometrie sur-genere. Les `Bridge` en sont la cause
        # attendue sur `C1_74` ; sur `MC1_67` ce compte doit etre NUL.
        print("  [6] aretes geom_only (geometrie sans le canal brut) : %d" % len(v["geom_only"]))
        for (a, b) in v["geom_only"][:24]:
            ta = None if a is None else a.get("tileDefId")
            tb = None if b is None else b.get("tileDefId")
            print("        %s  terrain %s -> %s" % (_fmt(a, b), ta, tb))

        # cran 7 : le champ TELEPORT. Tri-etat : `0` ne conclut RIEN a lui seul.
        tel = res.get("connectivityTeleportTiles")
        paires = [(t["id"], t.get("teleportTwinTileId")) for t in (res.get("tiles") or [])
                  if t.get("teleportTwinTileId")]
        print("  [7] connectivityTeleportTiles = %s ; paires non nulles = %d"
              % (tel, len(paires)))
        for (a, b) in paires[:8]:
            print("        tile %d <-> %d" % (a, b))
        return bad, {"delta": delta, "conn_only": len(v["conn_only"]),
                     "geom_only": len(v["geom_only"]), "teleport": tel}
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", action="append", default=None)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    boards = a.board or list(BOARDS)
    sid, rpc = _rpc_factory()
    print("== #448-r1-r1-r1-r1-r2 -- confrontation du canal `ConnectivityComponent` BRUT")
    print("   session=%s boards=%s seed=%d" % (sid, ",".join(boards), a.seed))
    bad = 0
    resume = {}
    for b in boards:
        print("\n-- board %s" % b)
        n, r = run_board(sid, rpc, b, a.seed, a.verbose)
        bad += n
        resume[b] = r
    print("\n== RESUME")
    for b, r in resume.items():
        print("   %-8s delta=%s conn_only=%s geom_only=%s teleport=%s"
              % (b, r.get("delta"), r.get("conn_only"), r.get("geom_only"), r.get("teleport")))
    # Le canal ne PROUVE qu'il transporte que si au moins un board rend un ecart NON NUL.
    non_degenere = any((r.get("conn_only") or 0) > 0 for r in resume.values())
    print("   regime non degenere (au moins un ecart conn_only > 0) : %s"
          % ("OUI" if non_degenere else "NON -- accord DEGENERE, le canal ne mord pas"))
    if not non_degenere:
        bad += 1
    print("VERDICT: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
