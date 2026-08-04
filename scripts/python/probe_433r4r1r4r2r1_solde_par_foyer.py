"""#433-r4-r1-r4-r2-r1 -- le SOLDE du basculement, VENTILE PAR SENS et PAR FOYER.

POURQUOI PAR FOYER, ET PAS EN BLOC
----------------------------------
Les quatre foyers voisins d'`is_adjacent` ne mirrorent PAS le meme natif ; leur solde n'a donc
aucune raison d'etre le meme, ni meme d'avoir le meme SIGNE :

  * `is_charging`         -> `BattleQuery$$IsCharging` -> `MovementUtil$$AreTilesAdjacent`
                             -> `ConnectivityComponent$$IsNeighbour` = `this[+0x10].Contains(id)`
                             = la liste STOCKEE, plus le COURT-CIRCUIT D'IDENTITE (#433-r1).
  * `newly_adjacent_ids`  -> `MoveUnitOperation$$UpdateCharging` -> `BattleQuery$$GetAdjacentUnits`
                             -> `IterateAdjacentTiles` = liste stockee PUIS porte d'elevation. Le
                             port n'avait NI l'un NI l'autre : DEUX etages, donc un solde propre.
  * `in_arc`              -> `BasePlaybook$$GetEligibleTargetsSelectable` -> ... ->
                             `BattleQuery$$GetTilesAtDistance` = `PositionComponent$$Distance` sur
                             le disque de `GetSurroundingTiles`. GEOMETRIQUE PUR : le solde y va
                             dans l'AUTRE sens (le port GATAIT ce que le natif accorde).

CONVENTION DE SENS -- « avant » = le port d'origine, « apres » = le port livre, et le verdict de
reference est le NATIF tel que le decompile le dit :

    PERMISSIF FERME  : avant VRAI, apres FAUX   (le port accordait ce que le natif refuse)
    RESTRICTIF OUVERT: avant FAUX, apres VRAI   (le port refusait ce que le natif accorde)

Un solde n'est LEGITIME que si son sens est celui de la lecture. Pour les deux premiers foyers, la
lecture dit « la liste stockee est PLUS PETITE que la couronne » -> on n'attend que du permissif
ferme. Pour `in_arc`, elle dit « aucune porte d'elevation » -> on n'attend que du restrictif ouvert.

Le comptage porte sur les PAIRES ORDONNEES de tuiles du board (le graphe est statique), pas sur des
unites : c'est le predicat qu'on mesure, pas une bataille.

ASCII only. Usage :
    python probe_433r4r1r4r2r1_solde_par_foyer.py [--board C3_14 ...]
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

import hexgeo                                                                    # noqa: E402

# Les quatre boards de #433-r4-r1-r4-r2, pour que les soldes soient COMPARABLES a la mesure qui a
# justifie le basculement. `C1_74` = 2 `Bridge`, `C3_14` = 15, `MC1_67`/`C6_25` = temoins.
BOARDS = ("C1_74", "C3_14", "MC1_67", "C6_25")


def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=180):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int) -> tuple[int, pathlib.Path]:
    """Le graphe de tuiles est STATIQUE : le roster n'influe sur aucune vue mesuree ici, on le
    DEGRADE donc plutot que d'echouer quand un board a peu de spawns joueur."""
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p433r4r1r4r2r1_solde_%s.json" % board)
    p = None
    for roster in (5, 4, 3, 2, 1):
        state_file.unlink(missing_ok=True)
        cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
               "--board", board, "--no-ai", "--roster", str(roster),
               "--state-file", str(state_file)]
        p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state_file.exists():
            return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), state_file
        if "spawns joueur <" not in ((p.stdout or "") + (p.stderr or "")):
            break
    sys.stdout.write(((p.stdout if p else "") or "")[-1200:])
    sys.stdout.write(((p.stderr if p else "") or "")[-1200:])
    raise SystemExit("build KO (%s)" % board)


def _ventiler(paires, avant, apres) -> tuple[int, int]:
    """`(permissif ferme, restrictif ouvert)` sur l'ensemble de paires donne."""
    ferme = ouvert = 0
    for (a, b) in paires:
        va, vp = avant(a, b), apres(a, b)
        if va and not vp:
            ferme += 1
        elif vp and not va:
            ouvert += 1
    return ferme, ouvert


def mesurer(res: dict) -> dict:
    """Les trois foyers, chacun avec SES deux versions du predicat, sur les memes paires."""
    from engine import battle_query as bq
    from engine.entities.pathfinding.board import Board, adjacent_neigh_by_pos

    tiles = res.get("tiles") or []
    bd = Board(tiles)
    elev = bd.elev_by_pos()
    canal = adjacent_neigh_by_pos(bd)
    pos = [(t["col"], t["row"]) for t in tiles]
    # Seules les paires a distance hex <= 2 peuvent changer de verdict pour l'un des trois foyers
    # (au-dela, les deux versions rendent FAUX partout) -- borner le balayage ne perd rien.
    paires = [(a, b) for a in pos for b in pos if a != b and hexgeo.distance(a, b) <= 2]
    ring1 = [(a, b) for (a, b) in paires if hexgeo.distance(a, b) == 1]

    out = {"tuiles": len(tiles), "paires_r2": len(paires), "paires_r1": len(ring1),
           "canal": None if canal is None else len(canal)}

    # -- FOYER `is_charging` : `AreTilesAdjacent` = identite OU liste stockee, ET porte.
    #    L'identite est hors paires (a != b) ; elle est gardee par le test offline.
    out["is_charging"] = _ventiler(
        ring1,
        lambda a, b: bq.are_entities_adjacent(a, b, elev, None),
        lambda a, b: bq.are_entities_adjacent(a, b, elev, canal))

    # -- FOYER `newly_adjacent_ids` : avant = `hexgeo.distance == 1` NU (ni etage 1 ni etage 2).
    out["newly_adjacent_ids"] = _ventiler(
        ring1,
        lambda a, b: hexgeo.distance(a, b) == 1,
        lambda a, b: bq.is_adjacent(a, b, elev, canal))
    # ventilation FINE des deux etages, pour dire lequel ferme quoi
    out["newly_etage_enumeration"] = _ventiler(
        ring1,
        lambda a, b: bq.is_adjacent(a, b, elev, None),
        lambda a, b: bq.is_adjacent(a, b, elev, canal))
    out["newly_etage_elevation"] = _ventiler(
        ring1,
        lambda a, b: hexgeo.distance(a, b) == 1,
        lambda a, b: bq.is_adjacent(a, b, elev, None))

    # -- FOYER `in_arc` : avant = ring-1 elevation-gate UNION ring-2 ; apres = dist <= 2.
    out["in_arc"] = _ventiler(
        paires,
        lambda a, b: bq.is_adjacent(a, b, elev, None) or hexgeo.distance(a, b) == 2,
        lambda a, b: bq.in_arc(a, b))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", action="append", default=None)
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()
    boards = a.board or list(BOARDS)
    sid, rpc = _rpc_factory()
    print("== #433-r4-r1-r4-r2-r1 -- solde par FOYER et par SENS (session %s)" % sid)
    print("   convention: FERME = permissif ferme (avant VRAI / apres FAUX) ;"
          " OUVERT = restrictif ouvert")
    total = {}
    for board in boards:
        rid, sf = _build(board, a.seed)
        try:
            res = rpc(sid, "boardGraph", {"runnerId": rid}, 120)
            m = mesurer(res)
        finally:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception as e:                       # noqa: BLE001
                print("   (dispose %s: %s)" % (rid, type(e).__name__))
            sf.unlink(missing_ok=True)
        print("-- %-8s tuiles=%d canal=%s paires r1=%d r2=%d"
              % (board, m["tuiles"], m["canal"], m["paires_r1"], m["paires_r2"]))
        for foyer in ("is_charging", "newly_adjacent_ids", "newly_etage_enumeration",
                      "newly_etage_elevation", "in_arc"):
            f, o = m[foyer]
            print("     %-26s FERME=%-4d OUVERT=%-4d" % (foyer, f, o))
            cf, co = total.get(foyer, (0, 0))
            total[foyer] = (cf + f, co + o)
    print("-- TOTAL sur %d boards" % len(boards))
    for foyer, (f, o) in total.items():
        print("     %-26s FERME=%-4d OUVERT=%-4d" % (foyer, f, o))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
