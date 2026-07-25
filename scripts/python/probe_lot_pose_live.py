#!/usr/bin/env python
"""Confrontation LIVE du lot << la pose manque >> : on fait AGIR les porteurs dans le runner natif et on
lit `decisionView.effects` -- la VERITE que le port doit reproduire.

  A. MasterAnnihilator : Vitruvius attaque (normale) -> le marqueur 1249 apparait sur SA cible
     (nom / level / remaining / source natifs) ; une 2e attaque sur une AUTRE cible le DEPLACE.
  B. TerrifyingCrescendo : Shiron tire (ranged) -> Pinned sur la cible + son stack 1424 MONTE.
  C. FleshmetalGuns : le seed live du runner porte deja l'effet du tour courant (turnsStarted=1 ->
     FocusedMalice) ; on relit apres N `endturn` pour observer la ROTATION native.

ASCII only. Usage : python probe_lot_pose_live.py [--rounds 3]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc      # noqa: E402

STATE = Path(r"C:\Users\nicolasv\tacticus-tools\data\_lot4pose_main_state.json")
MA, FG, TC, AS, EN = ("admecDominus", "blackObliterator", "emperNoiseMarine",
                      "spaceRockfist", "necroWarden")


def _r(sid, m, b, t=120):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 180)


def find(d, vis, alive=True):
    return [u for u in (d.get("units") or []) if u.get("visualId") == vis and (u.get("alive") or not alive)]


def effs(u):
    return [(e.get("name"), e.get("level"), e.get("remaining"), e.get("source"))
            for e in (u.get("effects") or [])]


def normal_id(u):
    for ab in (u.get("abilities") or []):
        if ab.get("kind") == "normal":
            return ab.get("id")
    return None


def act(sid, rid, action):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action, "captureEvents": False}, 180)


def _dist(a, b):
    import hexgeo
    return hexgeo.distance((a["col"], a["row"]), (b["col"], b["row"]))


def close_in(sid, rid, want_vis, want_range, maxrounds=8):
    """DRIVE POSITIONS : rapproche mes heros des ennemis (move vers la tuile legale la plus proche du
    plus proche ennemi) tour apres tour, jusqu'a ce que `want_vis` ait un ennemi a <= `want_range`.
    Entre deux de mes tours, l'IA adverse joue 1 tour (`aiPlayByUnit`)."""
    for rnd in range(maxrounds):
        d, u = advance_to(sid, rid, want_vis)
        if u is None:
            return None, None
        ens = find(d, EN)
        if ens and min(_dist(u["pos"], e["pos"]) for e in ens) <= want_range:
            return d, u
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        by_uid = {m.get("unitId"): (m.get("tiles") or []) for m in (mov.get("units") or [])}
        taken = set()
        for mine in [x for x in (d.get("units") or []) if x.get("ctrl") and x.get("alive")]:
            tiles = [t for t in by_uid.get(mine["id"], [])
                     if (t.get("col"), t.get("row")) not in taken]
            if not tiles or not ens:
                continue
            tgt = min(ens, key=lambda e: _dist(mine["pos"], e["pos"]))["pos"]
            best = min(tiles, key=lambda t: _dist({"col": t["col"], "row": t["row"]}, tgt))
            taken.add((best["col"], best["row"]))
            act(sid, rid, {"kind": "move", "unitId": mine["id"],
                           "to": {"col": best["col"], "row": best["row"]}})
        act(sid, rid, {"kind": "endturn"})
        _r(sid, "aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                                 "maxPump": 40, "captureEvents": False}, 300)
    d, u = advance_to(sid, rid, want_vis)
    return d, u


def advance_to(sid, rid, vis, maxit=16):
    for _ in range(maxit):
        d = dv(sid, rid)
        us = find(d, vis)
        if not us:
            return d, None
        if d.get("currentPlayer") == us[0].get("owner"):
            return d, us[0]
        act(sid, rid, {"kind": "endturn"})
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()
    sid = _resolve_session()
    rid = json.loads(STATE.read_text())["runnerId"]
    print("[live] session=%s runner=%s" % (sid, rid))

    d = dv(sid, rid)
    print("\n--- C. FleshmetalGuns : effet du tour courant (seed natif) ---")
    for u in find(d, FG):
        print("  Volk u%s turn=%s : %s" % (u["id"], d.get("currentPlayer"),
                                           [e for e in effs(u) if str(e[0]).startswith("Fleshmetal")]))

    print("\n--- A. MasterAnnihilator (attaque normale de Vitruvius) ---")
    d, vit = close_in(sid, rid, MA, 2)
    if vit is None:
        print("  SKIP : Vitruvius injoignable");
    else:
        nid = normal_id(vit)
        ens = find(d, EN)
        print("  Vitruvius u%s normal-ability=%s | ennemis=%s" % (vit["id"], nid, [e["id"] for e in ens]))
        done = []
        for tgt in ens[:2]:
            r = act(sid, rid, {"kind": "ability", "casterId": vit["id"],
                               "targetId": tgt["id"], "abilityId": nid})
            d2 = dv(sid, rid)
            marks = {u["id"]: [e for e in effs(u) if str(e[0]).startswith("MasterAnnihilator")]
                     for u in find(d2, EN)}
            print("  attaque -> u%s (ok=%s) | marques par unite : %s" % (tgt["id"], r.get("ok"), marks))
            done.append(marks)
            if not r.get("ok"):
                break

    print("\n--- B. TerrifyingCrescendo (tir ranged de Shiron) ---")
    for k in range(args.rounds):
        d, sh = close_in(sid, rid, TC, 3)
        if sh is None:
            print("  SKIP : Shiron injoignable"); break
        nid = normal_id(sh)
        ens = find(d, EN)
        tgt = ens[0] if ens else None
        if tgt is None:
            break
        r = act(sid, rid, {"kind": "ability", "casterId": sh["id"],
                           "targetId": tgt["id"], "abilityId": nid})
        d2 = dv(sid, rid)
        sh2 = find(d2, TC)
        tg2 = [u for u in find(d2, EN) if u["id"] == tgt["id"]]
        print("  tir #%d ok=%s | Shiron effets=%s | cible effets=%s"
              % (k + 1, r.get("ok"),
                 [e for e in effs(sh2[0])] if sh2 else None,
                 [e for e in effs(tg2[0])] if tg2 else None))
        act(sid, rid, {"kind": "endturn"})

    print("\n--- C2. FleshmetalGuns apres rotation native ---")
    for k in range(args.rounds):
        d, volk = advance_to(sid, rid, FG)
        if volk is None:
            break
        print("  tour Volk #%d : %s" % (k + 1, [e for e in effs(volk) if str(e[0]).startswith("Fleshmetal")]))
        act(sid, rid, {"kind": "endturn"})


if __name__ == "__main__":
    main()
