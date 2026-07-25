#!/usr/bin/env python
"""Confrontation LIVE #2 -- DRIVE TOTAL des DEUX camps (aucune RNG de positionnement, aucune IA native).

`applyAction` ne verifie PAS la propriete du `unitId`/`casterId` (runner.md §4) : on place donc
NOUS-MEMES les unites adverses. Deux mesures :

  A. TerrifyingCrescendo : Shiron (emperNoiseMarine) tire en RANGED (non-adjacent) sur un ennemi ->
     son trait SuppressiveFire pose Pinned -> le stack 1424 doit MONTER d'un cran par tir.
     On imprime `decisionView.effects` de Shiron a chaque tour (compteur natif).
  B. MasterAnnihilator : Vitruvius attaque la cible A puis (tour suivant) la cible B ->
     le marqueur 1249 doit se DEPLACER (remove-by-source) et ne jamais exister en double.

ASCII only. Usage : python probe_lot_pose_live2.py [--turns 8]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc      # noqa: E402

STATE = Path(r"C:\Users\nicolasv\tacticus-tools\data\_lot4pose_main_state.json")
MA, TC, EN = "admecDominus", "emperNoiseMarine", "necroWarden"
MY_PLAYER = 3


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True})


def act(sid, rid, a):
    return _r(sid, "applyAction", {"runnerId": rid, "action": a, "captureEvents": False})


def U(d, vis):
    return [u for u in (d.get("units") or []) if u.get("visualId") == vis and u.get("alive")]


def P(u):
    return (u["pos"]["col"], u["pos"]["row"])


def eff(u, prefix):
    return [(e["name"], e["level"], e["remaining"], e["source"])
            for e in (u.get("effects") or []) if str(e["name"]).startswith(prefix)]


def my_turn(sid, rid, maxit=6):
    for _ in range(maxit):
        d = dv(sid, rid)
        if d.get("currentPlayer") == MY_PLAYER:
            return d
        act(sid, rid, {"kind": "endturn"})
    return dv(sid, rid)


def movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def drive_enemy_to_distance(sid, rid, enemy_id, anchor_pos, want):
    """DRIVE de l'ADVERSAIRE : place `enemy_id` a la distance hex `want` de `anchor_pos` (tuile legale
    la plus proche de l'objectif). Se joue PENDANT LE TOUR ADVERSE (le movable set est calcule pour le
    joueur courant). Renvoie la distance obtenue."""
    tiles = movable(sid, rid, enemy_id)
    if not tiles:
        return None
    best = min(tiles, key=lambda t: abs(hexgeo.distance(t, anchor_pos) - want))
    act(sid, rid, {"kind": "move", "unitId": enemy_id, "to": {"col": best[0], "row": best[1]}})
    return hexgeo.distance(best, anchor_pos)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=8)
    args = ap.parse_args()
    sid = _resolve_session()
    rid = json.loads(STATE.read_text())["runnerId"]
    print("[live2] session=%s runner=%s" % (sid, rid))

    print("\n--- A. TerrifyingCrescendo : le stack MONTE tir apres tir (suppress) ---")
    seq = []
    for k in range(args.turns):
        d = dv(sid, rid)
        sh = U(d, TC)
        ens = U(d, EN)
        if not sh or not ens:
            print("  fin : roster incomplet"); break
        shiron, sp = sh[0], P(sh[0])
        # tour ADVERSE : on place NOUS-MEMES une cible a distance 2-3 de Shiron (ranged garanti).
        if d.get("currentPlayer") != MY_PLAYER:
            tgt = ens[0]
            got = drive_enemy_to_distance(sid, rid, tgt["id"], sp, 2)
            act(sid, rid, {"kind": "endturn"})
            d = dv(sid, rid)
            sh, ens = U(d, TC), U(d, EN)
            if not sh or not ens:
                break
            shiron, sp = sh[0], P(sh[0])
        cand = [e for e in ens if hexgeo.distance(P(e), sp) >= 2]
        if not cand:
            print("  tour %d : aucune cible NON-adjacente (ranged) -> endturn" % (k + 1))
            act(sid, rid, {"kind": "endturn"}); continue
        tgt = min(cand, key=lambda e: hexgeo.distance(P(e), sp))
        r = act(sid, rid, {"kind": "ability", "casterId": shiron["id"],
                           "targetId": tgt["id"], "abilityType": 69})
        d2 = dv(sid, rid)
        sh2 = U(d2, TC)[0]
        tg2 = [u for u in U(d2, EN) if u["id"] == tgt["id"]]
        lvl = next((e[1] for e in eff(sh2, "TerrifyingCrescendo")), 0)
        seq.append(lvl)
        print("  tir #%d ok=%s dist=%d -> crescendo=%s | cible Pinned=%s"
              % (k + 1, r.get("ok"), hexgeo.distance(P(tgt), sp), eff(sh2, "TerrifyingCrescendo"),
                 eff(tg2[0], "Pinned") if tg2 else None))
        act(sid, rid, {"kind": "endturn"})
    print("  SEQUENCE NATIVE du stack : %s" % seq)

    print("\n--- B. MasterAnnihilator : le marqueur SE DEPLACE (remove-by-source) ---")
    for k in range(3):
        d = my_turn(sid, rid)
        vit = U(d, MA)
        ens = U(d, EN)
        if not vit or len(ens) < 2:
            break
        v, vp = vit[0], P(vit[0])
        tgt = sorted(ens, key=lambda e: hexgeo.distance(P(e), vp))[k % 2]
        r = act(sid, rid, {"kind": "ability", "casterId": v["id"],
                           "targetId": tgt["id"], "abilityType": 69})
        d2 = dv(sid, rid)
        marks = {u["id"]: eff(u, "MasterAnnihilator") for u in U(d2, EN)}
        print("  attaque #%d -> u%s (dist=%d, ok=%s) | marques : %s"
              % (k + 1, tgt["id"], hexgeo.distance(P(tgt), vp), r.get("ok"),
                 {i: m for i, m in marks.items() if m}))
        act(sid, rid, {"kind": "endturn"})


if __name__ == "__main__":
    main()
