"""case-207 -- GENERALISATION : l'echelle `k = |pool|` du `PickRandomly(., 2)` de
`HazeOfCorruption_TargetFinderAbility`.

QUESTION (binaire) : le nombre de `genrand_int32` consommes a l'entree d'une attaque de
`deathBlightlord` vaut-il `min(k, 2)` de plus que les coups d'arme, ou `k` est le CARDINAL de
`Damageable( AdjacentEnemies(Self@0x148, 1, 3) & AdjacentFriends(Target@0x178, 1, 3) )` ?

Le montage principal de case-207 (`probe_207_haze_target_finder.py`, cible `astraCreed`) ne teste
QUE le regime `k = 1`, paye DEUX FOIS (deux emissions de `On(0x2a = PreUnitAbility)` via la re-entree
`ExecuteForReplacedTarget` de SwornProtector). Il ne separe donc PAS

    (a) « `min(k, 2)` tirages par emission »              [le decompile]
    (b) « 2 tirages forfaitaires par attaque du porteur » [un modele constant]

Ce probe CRAFTE la geometrie pour balayer `k = 0, 1, 2` sur UNE SEULE emission (cible SANS
`SwornProtector`, donc aucune re-resolution) :

    C = deathBlightlord, T = la cible (adjacente a C), et les DEUX voisins COMMUNS de C et T
    (sur une grille hex, deux hexes adjacents ont exactement 2 voisins communs) occupes par 0, 1
    ou 2 ennemis supplementaires.

Predictions, avec une arme a 3 coups :
    modele                      k=0   k=1   k=2
    (a) min(k,2)  [decompile]     3     4     5
    (b) forfait 2                 5     5     5
    (c) « pas de tirage si le pool tient » (port d'avant #130)  3   3   3

Les positions sont PILOTEES (`applyAction move` ignore portee/propriete) : on ne subit pas la
geometrie de spawn. Le caster n'est JAMAIS deplace (`moved = 0`).

CLI (depuis scripts/python) :
  python probe_207_haze_pool_ladder.py --seeds 777
  python probe_207_haze_pool_ladder.py --seeds 777,88 --k 0,1,2

Discipline runner : state-file ABSOLU sous logs/, board explicite, dispose en fin. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo

from probe_r6_round_materialize import _mkrpc, PYDIR, ROOT, BOARD
from probe_159_ah_bounds import _board, _genrand_steps, _pos, _unit
from probe_dpw_weapon_cell import _replay_recording, _raw_stream
from probe_207_haze_target_finder import replay_without_haze

CARRIER = "deathBlightlord"
TARGET = "astraBullgryn"                       # aucun trigger `On(PreUnitAbility)`, aucun summon
EXTRAS = ["astraDreir", "astraOrdnance"]       # idem -- occupants des voisins COMMUNS


def _build(seed, extra=None):
    sf = ROOT / "logs" / "runners" / f"p207lad-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
            "--board", BOARD, "--roster", "1", "--p-units", CARRIER,
            "--a-units", ",".join([TARGET] + EXTRAS), *(extra or [])]
    proc = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-500:])
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _move(rpc, rid, uid, coord):
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 60)


def _drive_pool(rpc, rid, board, k, max_turns=20):
    """Place la CIBLE sur un voisin du caster et `k` ennemis sur les voisins COMMUNS caster/cible.
    Les autres ennemis sont exiles a >5 hexes. Le caster ne bouge PAS."""
    my = None
    for _ in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        cst = _unit(dv, CARRIER)
        if cst is None:
            return None, None, None, "caster absent"
        if my is None:
            my = cst.get("owner")
        if dv.get("currentPlayer") == my:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    else:
        return None, None, None, "tour du joueur non atteint"

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    cst = _unit(dv, CARRIER)
    cpos = _pos(cst)
    ctile = board.id_at(*cpos)
    enemies = [u for u in (dv.get("units") or []) if u.get("owner") != my and u.get("alive")]
    tgt = _unit(dv, TARGET)
    if tgt is None or ctile is None:
        return None, None, None, "cible/tuile absente"
    # 1) tout le monde loin (sauf la cible) -- on repart d'une geometrie NEUTRE
    far = [t for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), cpos) > 5]
    it = iter(far)
    exiled = []
    for e in enemies:
        if e["id"] == tgt["id"]:
            continue
        ft = next(it, None)
        if ft is None:
            break
        _move(rpc, rid, e["id"], board.coord(ft))
        exiled.append(e)
    # 2) la cible sur un voisin du caster qui a >= 2 voisins communs LIBRES
    for nt in [n for n in board.neighbours(ctile) if board.walkable(n)]:
        common = [t for t in board.neighbours(nt)
                  if t != ctile and t in set(board.neighbours(ctile)) and board.walkable(t)]
        if len(common) >= max(1, k):
            _move(rpc, rid, tgt["id"], board.coord(nt))
            break
    else:
        return None, None, None, "aucun voisin du caster avec assez de voisins communs"
    # 3) k ennemis sur les voisins COMMUNS
    for i in range(k):
        if i >= len(exiled) or i >= len(common):
            return None, None, None, "pas assez d'ennemis/tuiles pour k=%d" % k
        _move(rpc, rid, exiled[i]["id"], board.coord(common[i]))

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    cst, tgt = _unit(dv, CARRIER), _unit(dv, TARGET)
    nrm = next((a for a in (cst.get("abilities") or []) if a.get("kind") == "normal"), None)
    if nrm is None:
        return None, None, None, "attaque normale introuvable"
    if hexgeo.distance(_pos(cst), _pos(tgt)) != 1:
        return None, None, None, "cible non adjacente apres placement"
    return cst["id"], tgt["id"], nrm["id"], None


def _run(rpc, seed, k, args):
    rid, sf = _build(seed, extra=["--crit", "0,0", "--block-target", "0,0",
                                  "--hp-target", str(args.hp), "--armor-target", str(args.armor)])
    if rid is None:
        return None
    try:
        board = _board(rpc, rid)
        cid, tid, aid, err = _drive_pool(rpc, rid, board, k)
        if cid is None:
            print("[lad] seed %s k=%d : drive KO -- %s" % (seed, k, err))
            return None
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": aid},
            "captureEvents": True}, 120)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        n_native = _genrand_steps(rng0, rng1)
        rows, bonds = [], 0
        for act in (res.get("actions") or []):
            for ev in (act.get("events") or []):
                td = ev.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                if "Amount" in td:
                    rows.append(td)
                if td.get("Effect_SourceTriggeredAbility") == 1076:
                    bonds += 1
        live = [int(td["Amount"]) for td in rows]
        off = _replay_recording(dv, ob, snap, board, rng0, cid, tid, 0)
        off_cf = replay_without_haze(dv, ob, snap, board, rng0, cid, tid, 0)
        geom = {"caster": _pos(_unit(dv, CARRIER)), "target": _pos(_unit(dv, TARGET)),
                "extras": [(_unit(dv, v) or {}).get("id") for v in EXTRAS]}
        return {"seed": seed, "k": k, "n_native": n_native, "n_off": off["n_genrand"],
                "live": live, "off": list(off["per_hit"]), "cell": off["cell"],
                "n_off_cf": off_cf["n_genrand"], "cf": list(off_cf["per_hit"]),
                "rolls": off["rolls"], "raw": _raw_stream(rng0, 8), "bonds": bonds,
                "geom": geom}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777")
    ap.add_argument("--k", default="0,1,2")
    ap.add_argument("--hp", type=int, default=90000)
    ap.add_argument("--armor", type=int, default=6000)
    args = ap.parse_args()
    rpc = _mkrpc()
    rows = []
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        for k in [int(x) for x in args.k.split(",") if x.strip()]:
            r = _run(rpc, seed, k, args)
            if r is None:
                continue
            rows.append(r)
            print("[lad] seed %s k=%d : natif=%s port=%s (contref %s) bonds=%d  live=%s port=%s "
                  "contref=%s"
                  % (seed, k, r["n_native"], r["n_off"], r["n_off_cf"], r["bonds"], r["live"],
                     r["off"], r["cf"]))
            print("      geom=%s cellule=%s" % (json.dumps(r["geom"]), r["cell"]))
            print("      rolls=%s" % (r["rolls"],))
    if not rows:
        print("[lad] aucun montage exploitable")
        return 1
    ok_cnt = sum(1 for r in rows if r["n_native"] == r["n_off"])
    ok_hit = sum(1 for r in rows if r["live"] == r["off"])
    print()
    print("[lad] BILAN %d montages : comptage port==natif %d/%d | per-coup port==live %d/%d"
          % (len(rows), ok_cnt, len(rows), ok_hit, len(rows)))
    base = {r["k"]: r["n_native"] for r in rows}
    print("[lad] natif par k : %s  (attendu (a) min(k,2) : k+3 pour k<=2)" % json.dumps(base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
