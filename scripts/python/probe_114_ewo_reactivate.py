"""Probe #114 residu 3 -- monte le scenario << Re'vas TUE en overwatch >> et MESURE, etape par etape,
ce que le natif rend : main a l'adversaire, tuiles atteignables des orks, effet du `applyAction move`
sur une unite ADVERSE, et les effets de Re'vas apres le kill.

Sert a lever la seule inconnue de harnais du volet B : peut-on DRIVER une unite du camp adverse
(`applyAction move` hors de mon camp) une fois la main passee ? Sortie ASCII pure.
"""
from __future__ import annotations

import sys

import rl_collect_batch as R
from sibling_script import sibling_script

BOARD = "MC1_67"
EARLY_WARNING_OVERRIDE = 1077
OVERWATCH = 1009
EWO_REACTIVATE = 1145
EWO_HIT_REDUCTION = 1146


def rpc(sid, m, b, t=90):
    r = R._rpc(sid, m, [b], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def dec(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})


def units(d):
    return {int(u["id"]): u for u in (d.get("units") or [])}


def pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def effs(d, uid):
    u = units(d).get(int(uid))
    return sorted(int(e["effectType"]) for e in ((u or {}).get("effects") or []))


def main():
    sid = R._resolve_session()
    w = R._rpc(sid, "autoBootExtraire", [{}], timeout=180)
    print("amorce:", str(w)[:120])
    import subprocess
    sf = sys.argv[1] if len(sys.argv) > 1 else "logs/probe114b.json"
    cmd = [sys.executable, sibling_script("rl_duel.py"), "build", "--seed", "114900",
           "--p-units", "tauCrisis,tauMarksman", "--a-units", "orksNob,orksNob",
           "--hp-target", "1", "--board", BOARD, "--state-file", sf]
    out = subprocess.run(cmd, capture_output=True, text=True)
    print(out.stdout[-1500:])
    import json
    st = json.load(open(sf, encoding="utf-8"))
    rid = st.get("runnerId") or st.get("rid")
    print("rid=", rid)

    d = dec(sid, rid)
    rv = next(u for u in units(d).values() if u.get("visualId") == "tauCrisis")
    me = rv.get("owner")
    print("revas=", rv["id"], "pos=", pos(rv), "owner=", me, "currentPlayer=", d.get("currentPlayer"))
    at = rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": rv["id"],
                                     "abilityType": EARLY_WARNING_OVERRIDE})
    print("fromHere 1077:", ((at.get("units") or [{}])[0].get("abilities") or [{}])[0].get("fromHere"))
    a = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": rv["id"], "abilityType": EARLY_WARNING_OVERRIDE,
        "targetId": rv["id"]}})
    print("cast 1077:", str(a)[:300])
    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
    d = dec(sid, rid)
    print("apres endturn currentPlayer=", d.get("currentPlayer"), "revas effs=", effs(d, rv["id"]))

    for side in (None, "friendly", "enemy", "hostile"):
        body = {"runnerId": rid}
        if side:
            body["side"] = side
        mv = rpc(sid, "aiMovableTiles", body) or {}
        rows = [(u.get("unitId"), len(u.get("tiles") or [])) for u in (mv.get("units") or [])]
        print("aiMovableTiles side=", side, "->", rows)

    import hexgeo
    for step in range(20):
        d = dec(sid, rid)
        cp = d.get("currentPlayer")
        ob = rpc(sid, "observeBattle", {"runnerId": rid}) or {}
        hp = {u["squadId"]: u["hp"] for u in (ob.get("units") or [])}
        rvl = units(d).get(rv["id"])
        if rvl is None:
            print("   decisionView SANS revas -> keys=", sorted(d.keys())[:12],
                  "ok=", d.get("ok"), "err=", str(d.get("error"))[:200])
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
            continue
        rpos = pos(rvl)
        foes = [u for u in units(d).values()
                if u.get("team") != rv.get("team") and hp.get(u["id"], 0) > 0]
        print(f"-- step {step} cp={cp} revas={rpos} foes="
              f"{[(f['id'], pos(f), hexgeo.distance(pos(f), rpos)) for f in foes]} hp={hp}")
        if not foes:
            print("   plus d'ennemi vivant"); break
        if cp == me:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
            continue
        mv = rpc(sid, "aiMovableTiles", {"runnerId": rid}) or {}
        rows = {u.get("unitId"): [(t["col"], t["row"]) for t in (u.get("tiles") or [])]
                for u in (mv.get("units") or [])}
        progressed = False
        for f in foes:
            tiles = rows.get(f["id"]) or []
            if not tiles:
                continue
            best = min(tiles, key=lambda q: hexgeo.distance(q, rpos))
            r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": f["id"], "to": {"col": best[0], "row": best[1]}}})
            ok = (r.get("actions") or [{}])[0].get("mutated")
            ob2 = rpc(sid, "observeBattle", {"runnerId": rid}) or {}
            hp2 = {u["squadId"]: u["hp"] for u in (ob2.get("units") or [])}
            print(f"   move u{f['id']} -> {best} d={hexgeo.distance(best, rpos)} mutated={ok} "
                  f"hp={hp2.get(f['id'])}")
            progressed = True
            if hp2.get(f["id"], 1) <= 0:
                print("   KILL ! revas effs:", effs(dec(sid, rid), rv["id"]))
                rpc(sid, "disposeRunner", {"runnerId": rid})
                return
        if not progressed:
            r1 = rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
            print("   endturn(enemy) ->", (r1.get("actions") or [{}])[0].get("mutated"),
                  "cp=", dec(sid, rid).get("currentPlayer"))
    print("revas effs:", effs(dec(sid, rid), rv["id"]))
    rpc(sid, "disposeRunner", {"runnerId": rid})


if __name__ == "__main__":
    main()
