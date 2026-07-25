"""#111 -- WaaaghAbility (1058) INERTE en runner isole : DECOMPOSITION PAR ETAGE.

Le symptome (session 78) : `applyAction {kind:"ability", casterId=<warboss>, abilityType=1058}`
rend `ok:true, mutated:false`, events = [group 12 <"Waaagh">, finish] et AUCUN des 3 buffs
(1099/1100/1101) n'est pose.

Ce probe MESURE, etage par etage, ou le natif s'arrete :
  E0  eligibilite  : `abilityTargets` (face DECISION) -- l'ability est-elle offerte, et sur quoi ?
  E1  cast         : `applyAction` -- ok / mutated / actionConsumed / spawned / events bruts
  E2  pose         : `decisionView.effects` du caster et de chaque allie (1099/1100/1101)
  E3  spawn        : nb d'unites orksOrkBoys apparues (etage 1 natif = Spawn)

Usage (depuis scripts/python) :
    python probe_111_waaagh_inert.py --state-file <ABSOLU> [--board MC1_67] [--seed 777]
                                     [--target self|tile|enemy] [--keep]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
CASTER = "orksWarboss"
ALLY = "orksNob"                      # faction Orks -> cible du selecteur board-wide
ENEMIES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt"
WAAAGH = 1058


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def dump_events(evts):
    for e in evts or []:
        print("   ev kind=%-6s group=%-5s step=%-5s entity=%-5s source=%s tags=%s"
              % (e.get("kind"), e.get("group"), e.get("step"), e.get("entity"),
                 e.get("source"), (e.get("tags") or "")[:160]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--target", default="self", choices=("self", "tile", "enemy", "legal"))
    ap.add_argument("--turns", type=int, default=25)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    out = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", a.seed,
                          "--board", a.board, "--state-file", a.state_file,
                          "--p-units", f"{CASTER},{ALLY}", "--a-units", ENEMIES],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print("BUILD FAILED rc=%d" % out.returncode)
        print((out.stdout or "")[-2000:])
        print((out.stderr or "")[-2000:])
        return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("runnerId=%s board=%s seed=%s" % (rid, a.board, a.seed))
    s = sid()
    try:
        dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        wb = next((u for u in dec["units"] if u.get("visualId") == CASTER and u.get("alive")), None)
        if wb is None:
            print("warboss absent")
            return 2
        me = wb["owner"]
        print("currentPlayer=%s me=%s" % (dec.get("currentPlayer"), me))
        for u in dec["units"]:
            print("  u%-4s %-22s owner=%s alive=%s pos=%s hasAction=%s"
                  % (u.get("id"), u.get("visualId"), u.get("owner"), u.get("alive"),
                     u.get("pos"), u.get("hasActionLeft")))
        print("warboss abilities: %s" % [(x.get("id"), x.get("kind"), x.get("name"))
                                         for x in (wb.get("abilities") or [])])

        # ---- E0 : face DECISION (eligibilite/ciblage) -------------------------------------- #
        at = rpc(s, "abilityTargets", {"runnerId": rid, "unitId": wb["id"], "allAbilities": True}, 90)
        for unit in (at.get("units") or []):
            if unit.get("unitId") != wb["id"]:
                continue
            for ab in (unit.get("abilities") or []):
                tg = ab.get("fromHere") or []
                print("  E0 ability=%s kind=%s targets=%d sample=%s"
                      % (ab.get("abilityId"), ab.get("kind"), len(tg),
                         [(t.get("kind"), t.get("targetId"), t.get("col"), t.get("row"))
                          for t in tg[:6]]))

        # ---- E0bis : APPROCHE jusqu'a ce que le gate dynamique s'ouvre --------------------- #
        # `WaaaghAbility$$GetDynamicInvalidTargetReason` = Count(GetPossibleMovementTiles(target)) > 0
        # -> il faut une tuile LIBRE adjacente a la cible, atteignable par le caster en
        # (MOVEMENT + extraMovement) pas. On avance donc le Warboss vers l'ennemi.
        if a.target == "legal":
            from engine.entities.pathfinding.board import Board
            bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="evenq")

            def tile_of(u):
                p = u.get("pos") or {}
                return (board.id_at(p.get("col"), p.get("row"))
                        if p.get("col") is not None else None)

            def bfs(src):
                from collections import deque
                dist, q = {src: 0}, deque([src])
                while q:
                    x = q.popleft()
                    for n in board.neighbours(x):
                        if n not in dist and (n == src or board.walkable(n)):
                            dist[n] = dist[x] + 1
                            q.append(n)
                return dist

            legal = None
            for _t in range(a.turns):
                dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1,
                                              "allAbilities": True}, 90)
                if dec.get("currentPlayer") != me:
                    rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                    continue
                wb = next((u for u in dec["units"] if u["id"] == wb["id"] and u.get("alive")), None)
                if wb is None:
                    print("warboss mort")
                    return 3
                at = rpc(s, "abilityTargets", {"runnerId": rid, "unitId": wb["id"],
                                               "allAbilities": True}, 90)
                tg = []
                for unit in (at.get("units") or []):
                    if unit.get("unitId") != wb["id"]:
                        continue
                    for ab in (unit.get("abilities") or []):
                        if ab.get("abilityId") == WAAAGH:
                            tg = ab.get("fromHere") or []
                print("  approche t%d wbPos=%s waaaghTargets=%d" % (_t, wb.get("pos"), len(tg)))
                if tg:
                    legal = tg[0]
                    break
                ens = [u for u in dec["units"] if u.get("owner") != me and u.get("alive")]
                goal = ens[0]
                dgoal = bfs(tile_of(goal))
                mt = rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
                cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == wb["id"]), None)
                reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                         for t in ((cmt or {}).get("tiles") or [])}
                pool = [t for t in reach if t in dgoal]
                if pool:
                    best = min(pool, key=lambda t: dgoal[t])
                    col, row = reach[best]
                    rpc(s, "applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": wb["id"], "to": {"col": col, "row": row}}}, 60)
                rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            if legal is None:
                print("aucune cible legale atteinte")
                return 4
            print("E0bis cible legale = %s" % legal)
            dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            for u in dec["units"]:
                print("  pre-cast u%-4s %-22s alive=%s pos=%s" % (u.get("id"), u.get("visualId"),
                                                                 u.get("alive"), u.get("pos")))
            act = {"kind": "ability", "casterId": wb["id"], "abilityType": WAAAGH}
            if legal.get("kind") == "unit":
                act["targetId"] = legal.get("targetId")
            else:
                act["to"] = {"col": legal.get("col"), "row": legal.get("row")}
        elif a.target == "self":
            act = {"kind": "ability", "casterId": wb["id"], "targetId": wb["id"],
                   "abilityType": WAAAGH}
        elif a.target == "enemy":
            en = next(u for u in dec["units"] if u.get("owner") != me and u.get("alive"))
            act = {"kind": "ability", "casterId": wb["id"], "targetId": en["id"],
                   "abilityType": WAAAGH}
        else:
            p = wb["pos"]
            act = {"kind": "ability", "casterId": wb["id"],
                   "to": {"col": p["col"], "row": p["row"] + 1}, "abilityType": WAAAGH}

        # ---- E1 : CAST ---------------------------------------------------------------------- #
        ids_before = {u["id"] for u in rpc(
            s, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)["units"]}
        res = rpc(s, "applyAction", {"runnerId": rid, "action": act}, 90)
        a0 = (res.get("actions") or [{}])[0]
        print("E1 cast target=%s ok=%s error=%s mutated=%s actionConsumed=%s spawned=%s eventCount=%s"
              % (a.target, a0.get("ok"), a0.get("error"), a0.get("mutated"),
                 a0.get("actionConsumed"), a0.get("spawned"), a0.get("eventCount")))
        print("   changes=%s" % json.dumps(a0.get("changes") or []))
        dump_events(a0.get("events"))

        # ---- E2/E3 : POSE + SPAWN ----------------------------------------------------------- #
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        for u in dv["units"]:
            eff = [(e.get("type"), e.get("name")) for e in (u.get("effects") or [])]
            print("  E2 u%-4s %-22s alive=%s eff=%s"
                  % (u.get("id"), u.get("visualId"), u.get("alive"), eff))
        # ATTENTION : la constante d'ability est `GetStringConstant(0) = "orksOrkBoys"` (unitId) mais
        # le `visualId` du summon est `orksNpc2OrkBoy` -> on compte les entites APPARUES, pas un nom.
        boyz = [u["id"] for u in dv["units"] if u["id"] not in ids_before]
        print("E3 unites apparues=%d %s" % (len(boyz), boyz))
        return 0
    finally:
        if not a.keep:
            try:
                subprocess.run([sys.executable, "rl_duel.py", "dispose",
                                "--state-file", a.state_file], capture_output=True, text=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
