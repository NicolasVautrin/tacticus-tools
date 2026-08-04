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

VENTILATION A TROIS VUES -- deux points que le plan sous-entend sans les ecrire :

  * un delta SCALAIRE de `+18` est compatible avec `+20 / -2`. On compte donc SEPAREMENT chaque
    sens, jamais la seule difference des cardinaux ;
  * le cran 6 (« les 4 aretes `Bridge` sont dans la geometrie et PAS dans le canal brut ») ne se
    mesure PAS contre le champ `neighbours` : celui-ci porte deja la porte d'elevation. Il se
    mesure contre `Board.neighbours_geometric` -- la couronne hex recalculee, substrat de
    `IdunBattle.Entities.Pathfinding.FlyPathfinder$$AddNeighbours`. Les TROIS vues sont donc
    confrontees deux a deux :

      G = `neighbours_geometric`  (couronne hex, aucune porte)
      N = `neighbours`            (`BattleQuery$$GetAdjacentTiles` -> porte `|delev| < 2`)
      C = `connectivity`          (`ConnectivityComponent`, critere `TileComponent$$HasEdge`)

    `C \\ N` mesure ce que la porte amputait ; `G \\ C` mesure ce que `HasEdge` refuse et que la
    geometrie invente. Sans la troisieme vue, les deux causes sont INDISCERNABLES -- c'est
    exactement ce qui faisait sous-compter le residu a 4 aretes.

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
    """Le nombre de SPAWNS JOUEUR varie par board (les `C6_*` en ont 3 a 5) et le build refuse
    `N spawns joueur < M units`. On DEGRADE le roster plutot que d'echouer : le graphe de tuiles
    est STATIQUE, donc le compte d'unites n'influe sur AUCUNE des trois vues mesurees ici."""
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p448r1r1r1r1r2_state_%s.json" % board)
    p = None
    for roster in (5, 4, 3, 2, 1):
        state_file.unlink(missing_ok=True)
        cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
               "--board", board, "--no-ai", "--roster", str(roster),
               "--state-file", str(state_file)]
        p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state_file.exists():
            if roster != 5:
                print("     [build] %s : roster degrade a %d (spawns joueur)" % (board, roster))
            return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), state_file
        if "spawns joueur <" not in ((p.stdout or "") + (p.stderr or "")):
            break
    sys.stdout.write(((p.stdout if p else "") or "")[-1200:])
    sys.stdout.write(((p.stderr if p else "") or "")[-1200:])
    raise SystemExit("build KO (%s)" % board)


def _ventiler(res: dict) -> dict:
    """Ecart ARETE PAR ARETE entre les TROIS vues (cf. l'en-tete du module).

    Tri-etat respecte : une tuile dont `connectivity` est `None` (composant absent) n'entre dans
    AUCUN compte -- elle est comptee a part (`sans_composant`). La confondre avec `[]` est la
    faute exacte de `#381-r3`."""
    from engine.entities.pathfinding.board import Board

    tiles = res.get("tiles") or []
    by_id = {t["id"]: t for t in tiles}
    bd = Board(tiles)
    manquantes = []
    ecarts = {"C_moins_N": [], "N_moins_C": [], "G_moins_C": [], "C_moins_G": [],
              "G_moins_N": [], "N_moins_G": []}
    for t in tiles:
        conn = t.get("connectivity")
        neigh = set(t.get("neighbours") or [])
        geo = set(bd.neighbours_geometric(t["id"]))
        for nid in sorted(geo - neigh):
            ecarts["G_moins_N"].append((t, by_id.get(nid)))
        for nid in sorted(neigh - geo):
            ecarts["N_moins_G"].append((t, by_id.get(nid)))
        if conn is None:
            manquantes.append(t["id"])
            continue
        cset = set(conn)
        for nid in sorted(cset - neigh):
            ecarts["C_moins_N"].append((t, by_id.get(nid)))
        for nid in sorted(neigh - cset):
            ecarts["N_moins_C"].append((t, by_id.get(nid)))
        for nid in sorted(geo - cset):
            ecarts["G_moins_C"].append((t, by_id.get(nid)))
        for nid in sorted(cset - geo):
            ecarts["C_moins_G"].append((t, by_id.get(nid)))
    ecarts["sans_composant"] = manquantes
    return ecarts


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

        # --- cran 4/5/6 : la VENTILATION a trois vues.
        ce, ne = res.get("connectivityEdges"), res.get("neighbourEdges")
        delta = None if (ce is None or ne is None) else ce - ne
        v = _ventiler(res)
        n_cn, n_nc = len(v["C_moins_N"]), len(v["N_moins_C"])
        n_gc, n_cg = len(v["G_moins_C"]), len(v["C_moins_G"])
        n_gn, n_ng = len(v["G_moins_N"]), len(v["N_moins_G"])
        print("  [4] connectivityEdges=%s neighbourEdges=%s  DELTA=%s" % (ce, ne, delta))
        print("      C\\N=%d  N\\C=%d  |  G\\C=%d  C\\G=%d  |  G\\N=%d  N\\G=%d"
              % (n_cn, n_nc, n_gc, n_cg, n_gn, n_ng))
        if delta is not None and delta != n_cn - n_nc:
            print("      ECART: le delta scalaire ne se ventile pas -- compteurs incoherents")
            bad += 1
        # Identite structurelle : `N` etant `G` PRIVE de la porte, et `C` etant `G` PRIVE de
        # `HasEdge`, les aretes que `G` a en trop sur `N` se partagent EXACTEMENT entre les deux
        # causes. Elle rougit si une TROISIEME cause s'est glissee dans une des vues.
        if n_gn != n_cn + n_gc:
            print("      ECART: G\\N (%d) != C\\N (%d) + G\\C (%d) -- une 3e cause coexiste"
                  % (n_gn, n_cn, n_gc))
            bad += 1

        # cran 5 : les aretes que la porte d'elevation AMPUTAIT. Toutes doivent avoir
        # |delev| >= 2 (c'est exactement ce que `TileQuery$$IterateAdjacentTiles` filtre).
        mauvaises = [(a, b) for (a, b) in v["C_moins_N"]
                     if a is not None and b is not None
                     and abs(int(a.get("elevation") or 0) - int(b.get("elevation") or 0)) < 2]
        print("  [5] aretes C\\N avec |delev| < 2 : %d (attendu 0)" % len(mauvaises))
        bad += 0 if not mauvaises else 1
        if verbose or mauvaises:
            for (a, b) in (mauvaises or v["C_moins_N"])[:24]:
                print("        %s" % _fmt(a, b))

        # cran 6 : `G \ C` -- ce que `HasEdge` refuse et que la couronne hex invente. C'est le
        # residu « dans l'autre sens » : la beeline sur geometrie couperait la ou le natif fait
        # le tour. `C \ G` doit etre NUL (le canal ne peut pas inventer un voisin hors couronne).
        print("  [6] aretes G\\C (geometrie sans le canal brut) : %d ; C\\G : %d (attendu 0)"
              % (n_gc, n_cg))
        bad += 0 if n_cg == 0 else 1
        for (a, b) in v["G_moins_C"][:24]:
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
        return bad, {"delta": delta, "C_moins_N": n_cn, "G_moins_C": n_gc,
                     "C_moins_G": n_cg, "teleport": tel}
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
        print("   %-8s delta=%s C\\N=%s G\\C=%s C\\G=%s teleport=%s"
              % (b, r.get("delta"), r.get("C_moins_N"), r.get("G_moins_C"),
                 r.get("C_moins_G"), r.get("teleport")))
    # Le canal ne PROUVE qu'il transporte que si au moins un board rend un ecart NON NUL. Un
    # `C\N == 0` partout serait un accord DEGENERE : le canal lirait la meme chose que le champ
    # herite, donc il ne mordrait pas -- et le lire comme une confirmation serait la faute.
    non_degenere = any((r.get("C_moins_N") or 0) > 0 for r in resume.values())
    print("   regime non degenere (au moins un ecart C\\N > 0) : %s"
          % ("OUI" if non_degenere else "NON -- accord DEGENERE, le canal ne mord pas"))
    if not non_degenere:
        bad += 1
    print("VERDICT: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
