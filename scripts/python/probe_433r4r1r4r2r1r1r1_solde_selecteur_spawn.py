"""#433-r4-r1-r4-r2-r1-r1-r1 -- le SOLDE du branchement des DEUX selecteurs de spawn NC.

Les sites : `AberrantHypermorphPlaybook` (1166) et `MasterOfTheTutelariesPlaybook` (1096)
re-projetaient l'union `abilityTargets` sur la position candidate T par
`hexgeo.distance(T, ST) == 1` NU. Le selecteur natif, lui, passe par
`TargetingQuery$$GetTilesInRange` -> slot 0x51 `BattleQuery$$GetAdjacentTiles` ->
`IterateAdjacentTiles` (`onlyAdjacent = RangedBool.True` dans le `TargetingRange` statique +0x30
recopie par les deux `.ctor` d'ability) : liste STOCKEE du `ConnectivityComponent` PUIS porte
`|dElev| < 2`. Les deux sites partagent DONC le meme predicat -- ce qui se mesure une fois.

CONVENTION DE SENS (identique a `probe_433r4r1r4r2r1_solde_par_foyer.py`, pour comparabilite) :

    PERMISSIF FERME   : avant VRAI, apres FAUX   (le port accordait ce que le natif refuse)
    RESTRICTIF OUVERT : avant FAUX, apres VRAI   (le port refusait ce que le natif accorde)

La lecture dit « liste stockee ⊆ couronne hex, plus une porte » -> on n'attend QUE du permissif
ferme. Un seul OUVERT invaliderait la lecture.

DEUX GRAINS, parce que le premier ne dit pas l'impact :
  * PAIRES  -- le predicat lui-meme, sur toutes les paires ring-1 du board. Comparable au
    solde d'`in_arc`/`newly_adjacent_ids` de #614.
  * SITES   -- combien de positions candidates T voient leur ENSEMBLE de tuiles de spawn
    changer. C'est ce grain qui peut deplacer l'argmax du bucket, donc la DECISION.
    On y distingue les T qui perdent TOUTE tuile de spawn (le playbook n'emet plus rien
    depuis cette position) de ceux qui en perdent seulement une partie.

Le graphe de tuiles est STATIQUE : le roster n'influe sur rien de ce qui est mesure ici.

ASCII only. Usage :
    python probe_433r4r1r4r2r1r1r1_solde_selecteur_spawn.py [--board C3_14 ...] [--seed 777]
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

# `C1_74` = 2 `Bridge`, `C3_14` = 15, `MC1_67` = temoin sans arete coupee : trois STRUCTURES
# differentes, et c'est la structure qui gouverne l'ecart (pas la taille).
BOARDS = ("C1_74", "C3_14", "MC1_67")


def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=180):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int) -> tuple[int, pathlib.Path]:
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p433r4r1r4r2r1r1r1_spawn_%s.json" % board)
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


def mesurer(res: dict) -> dict:
    from engine import battle_query as bq
    from engine.entities.pathfinding.board import Board, adjacent_neigh_by_pos

    tiles = res.get("tiles") or []
    bd = Board(tiles)
    elev = bd.elev_by_pos()
    canal = adjacent_neigh_by_pos(bd)
    pos = [(t["col"], t["row"]) for t in tiles]

    ferme = ouvert = 0
    sites_reduits = sites_vides = sites_total = 0
    for tpos in pos:
        # AVANT : le filtre `hexgeo.distance(T, ST) == 1`, sur l'union des tuiles du board.
        avant = {q for q in pos if hexgeo.distance(tpos, q) == 1}
        apres = {q for q in pos if bq.is_adjacent(tpos, q, elev, canal)}
        ferme += len(avant - apres)
        ouvert += len(apres - avant)
        if avant:
            sites_total += 1
            if apres != avant:
                sites_reduits += 1
            if not apres:
                sites_vides += 1
    return {"tuiles": len(tiles), "canal": None if canal is None else len(canal),
            "paires_fermees": ferme, "paires_ouvertes": ouvert,
            "sites_total": sites_total, "sites_changes": sites_reduits,
            "sites_vides": sites_vides}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", action="append", default=None)
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()
    boards = a.board or list(BOARDS)
    sid, rpc = _rpc_factory()
    print("== #433-r4-r1-r4-r2-r1-r1-r1 -- solde des selecteurs de spawn NC (session %s)" % sid)
    print("   FERME = permissif ferme (avant VRAI / apres FAUX) ; OUVERT = restrictif ouvert")
    tot_f = tot_o = tot_s = tot_c = tot_v = 0
    for board in boards:
        rid, sf = _build(board, a.seed)
        try:
            m = mesurer(rpc(sid, "boardGraph", {"runnerId": rid}, 120))
        finally:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception as e:                       # noqa: BLE001
                print("   (dispose %s: %s)" % (rid, type(e).__name__))
            sf.unlink(missing_ok=True)
        print("-- %-8s tuiles=%-4d canal=%-4s paires FERME=%-4d OUVERT=%-4d |"
              " positions T changees=%d/%d dont VIDEES=%d"
              % (board, m["tuiles"], m["canal"], m["paires_fermees"], m["paires_ouvertes"],
                 m["sites_changes"], m["sites_total"], m["sites_vides"]))
        tot_f += m["paires_fermees"]
        tot_o += m["paires_ouvertes"]
        tot_s += m["sites_total"]
        tot_c += m["sites_changes"]
        tot_v += m["sites_vides"]
    print("-- TOTAL sur %d boards : paires FERME=%d OUVERT=%d | positions T changees=%d/%d"
          " dont VIDEES=%d" % (len(boards), tot_f, tot_o, tot_c, tot_s, tot_v))
    if tot_o:
        print("VERDICT: FAIL -- %d paires RESTRICTIF OUVERT, la lecture n'en prevoit AUCUNE" % tot_o)
        return 1
    print("VERDICT: PASS -- solde strictement PERMISSIF FERME, conforme a la lecture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
