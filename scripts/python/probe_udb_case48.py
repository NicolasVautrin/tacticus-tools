"""Probe #48 : cartographie l'inclusion native de `UnitsDirectlyBehind` par POSITION frontiere
(front delta -1 / lateral delta 0 / away delta +1) pour PlasmaCannon (darkaTerminator), et confronte
a l'offline. Mesure les distances hex LIVE reelles (rule out placement error). Self-contained runner.
ASCII only. Usage: python probe_udb_case48.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.entities.selectors.units import UnitsDirectlyBehind

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
CASTER_VIS = "darkaTerminator"
ABILITY = 1150
A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"

import rl_collect_batch as R
SID = R._resolve_session()


def rpc(method, body=None, timeout=90):
    r = R._rpc(SID, method, [body] if body is not None else [], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _caster(dv):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_VIS and u.get("alive")), None)


def main():
    R._rpc(SID, "autoBootExtraire", [{}], timeout=180)
    sf = ROOT / "logs" / "runners" / f"udb-probe-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
         "--hp-target", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-300:]); return
    rid = json.loads(sf.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = bg["tiles"]
        elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
        board = Board(tiles, adjacency="native_sym")

        def mv(uid, tid):
            c = board.coord(tid)
            return rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        myplayer = _caster(dv).get("owner")
        for _ in range(6):
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            c = _caster(dv)
            if c is None:
                break
            tin = any("TeleportingIn" in (e.get("name") or "") for e in (c.get("effects") or []))
            if not tin and dv.get("currentPlayer") == myplayer:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        caster = _caster(dv)
        cid = caster["id"]
        cpos = (caster["pos"]["col"], caster["pos"]["row"])
        ctile = board.id_at(*cpos)
        eC = elev.get(cpos)
        enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
        print("caster", cid, "at", cpos, "elev", eC, "| enemies", [e["id"] for e in enemies])

        far = [t for t in sorted(board.by_id) if board.walkable(t)
               and hexgeo.distance(board.coord(t), cpos) > 6]
        for e, ft in zip(enemies, far):
            mv(e["id"], ft)

        # cherche T a d=2 avec front/lateral/away walkable, cast legal
        cand = None
        for T in sorted(board.by_id):
            ct = board.coord(T)
            if not board.walkable(T) or T == ctile or hexgeo.distance(ct, cpos) != 2:
                continue
            if elev.get(ct) is None or eC is None or abs(elev.get(ct) - eC) > 1:
                continue
            slots = {"front": None, "lateral": None, "away": None}
            for n in board.neighbours(T):
                if not board.walkable(n) or n == ctile:
                    continue
                cn = board.coord(n)
                if elev.get(cn) is None or abs(elev.get(cn) - elev.get(ct)) > 1:
                    continue
                d = hexgeo.distance(cn, cpos) - 2
                key = {-1: "front", 0: "lateral", 1: "away"}.get(d)
                if key and slots[key] is None:
                    slots[key] = n
            if slots["lateral"] and slots["away"]:
                mv(enemies[0]["id"], T)
                at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
                fh = [x.get("targetId") for x in
                      next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                            if a.get("abilityId") == ABILITY), {}).get("fromHere") or []]
                if enemies[0]["id"] in fh:
                    cand = (T, slots)
                    break
                mv(enemies[0]["id"], far[0])
        if cand is None:
            print("NO GEOMETRY"); return
        T, slots = cand
        print("target tile", T, "coord", board.coord(T), "| slots", {k: (board.coord(v) if v else None) for k, v in slots.items()})

        # place lateral + away (2 enemies), garde le 4e loin ; front reste vide (pas d'ennemi)
        target = enemies[0]
        u_lat, u_away = enemies[1], enemies[2]
        mv(u_lat["id"], slots["lateral"])
        mv(u_away["id"], slots["away"])

        # mesure distances hex LIVE reelles
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in dv2["units"] if u.get("pos")}
        tp = pos[target["id"]]
        print("LIVE dist: d_ct=", hexgeo.distance(cpos, tp),
              "| lateral", u_lat["id"], "at", pos.get(u_lat["id"]),
              "d(caster)=", hexgeo.distance(cpos, pos[u_lat["id"]]),
              "d(target)=", hexgeo.distance(tp, pos[u_lat["id"]]),
              "| away", u_away["id"], "at", pos.get(u_away["id"]),
              "d(caster)=", hexgeo.distance(cpos, pos[u_away["id"]]),
              "d(target)=", hexgeo.distance(tp, pos[u_away["id"]]))

        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv2, ob2, snap2); st.board = board
        ent = entities_from_state(st, cid, target["id"])
        udb = sorted(x.get("id") for x in UnitsDirectlyBehind().select(ent))
        print("OFFLINE UnitsDirectlyBehind:", udb, "(lateral", u_lat["id"], "away", u_away["id"], ")")

        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": target["id"], "abilityType": ABILITY},
            "captureEvents": True}, 120)
        live = set()
        for act in (cast.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                    live.add(td.get("Target_Id"))
        print("LIVE splash targets:", sorted(live), "| main", target["id"],
              "lateral", u_lat["id"], "(in?", u_lat["id"] in live, ") away", u_away["id"], "(in?", u_away["id"] in live, ")")
        print("VERDICT: lateral", "INCLUDED (>= )" if u_lat["id"] in live else "EXCLUDED (> strict)")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
