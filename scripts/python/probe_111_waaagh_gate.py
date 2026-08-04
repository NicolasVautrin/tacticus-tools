"""#111 -- Waaagh (1058) : DECOMPOSITION du gate de CIBLAGE (face DECISION + face EXECUTION).

Amene le Warboss a portee de CHARGE d'un ennemi, puis caste QUATRE fois le meme sort avec des
cibles differentes, en mesurant a chaque fois `ok / mutated / actionConsumed / eventCount` :

  A. cible = LE CASTER lui-meme      -> attendu NO-OP (filtre statique TargetingOptions)
  B. cible = un ALLIE                -> attendu NO-OP (idem)
  C. cible = un ENNEMI HORS portee de charge  -> attendu NO-OP (gate DYNAMIQUE
     `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetDynamicInvalidTargetReason` : Count(GetPossibleMovementTiles(target)) > 0)
  D. cible = un ENNEMI offert par `abilityTargets` -> attendu EXECUTION COMPLETE

Un NO-OP consomme l'action ? Non : `actionConsumed=False` est la signature du rejet moteur
(cf. `ActionResult.actionConsumed`, TF12). L'ordre A,B,C,D est important : seul D consomme
l'activation, donc D est teste EN DERNIER.

Usage (depuis scripts/python) :
    python probe_111_waaagh_gate.py --state-file <ABSOLU> [--board MC1_67] [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import requests
from sibling_script import sibling_script

HOST = "http://127.0.0.1:8765"
CASTER = "orksWarboss"
ALLY = "orksNob"
ENEMIES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt"
WAAAGH = 1058


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def cast(s, rid, caster_id, target_id, label):
    res = rpc(s, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "targetId": target_id,
        "abilityType": WAAAGH}}, 120)
    a0 = (res.get("actions") or [{}])[0]
    groups = sorted({e.get("group") for e in (a0.get("events") or []) if e.get("kind") == "group"})
    print("  %-38s ok=%-5s mutated=%-5s actionConsumed=%-5s spawned=%-4s events=%-4s groups=%s"
          % (label, a0.get("ok"), a0.get("mutated"), a0.get("actionConsumed"),
             a0.get("spawned"), a0.get("eventCount"), groups))
    return a0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--turns", type=int, default=25)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build", "--seed", a.seed,
                          "--board", a.board, "--state-file", a.state_file,
                          "--p-units", f"{CASTER},{ALLY}", "--a-units", ENEMIES],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print("BUILD FAILED rc=%d" % out.returncode)
        print((out.stdout or "")[-2000:] + (out.stderr or "")[-2000:])
        return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("runnerId=%s board=%s seed=%s" % (rid, a.board, a.seed))
    s = sid()
    try:
        from engine.entities.pathfinding.board import Board
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")

        def tile_of(u):
            p = u.get("pos") or {}
            return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

        def bfs(src):
            dist, q = {src: 0}, deque([src])
            while q:
                x = q.popleft()
                for n in board.neighbours(x):
                    if n not in dist and (n == src or board.walkable(n)):
                        dist[n] = dist[x] + 1
                        q.append(n)
            return dist

        dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        wb0 = next(u for u in dec["units"] if u.get("visualId") == CASTER and u.get("alive"))
        ally0 = next(u for u in dec["units"] if u.get("visualId") == ALLY and u.get("alive"))
        me = wb0["owner"]

        offered = []
        for _t in range(a.turns):
            dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
            if dec.get("currentPlayer") != me:
                rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            wb = next((u for u in dec["units"] if u["id"] == wb0["id"] and u.get("alive")), None)
            if wb is None:
                print("warboss mort")
                return 3
            at = rpc(s, "abilityTargets", {"runnerId": rid, "unitId": wb["id"],
                                           "allAbilities": True})
            offered, superset = [], []
            for unit in (at.get("units") or []):
                if unit.get("unitId") != wb["id"]:
                    continue
                for ab in (unit.get("abilities") or []):
                    if ab.get("abilityId") == WAAAGH:
                        offered = ab.get("fromHere") or []      # legalite EXACTE du cast immediat
                        superset = ab.get("targets") or []      # ce tour, MOVE inclus (superset)
            print("approche t%-2d wbPos=%-22s E0 fromHere=%d %s | targets(superset)=%d %s"
                  % (_t, wb.get("pos"), len(offered),
                     [t.get("targetId") for t in offered],
                     len(superset), [t.get("targetId") for t in superset]))
            if offered:
                break
            ens = [u for u in dec["units"] if u.get("owner") != me and u.get("alive")]
            dgoal = bfs(tile_of(ens[0]))
            mt = rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == wb["id"]), None)
            reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                     for t in ((cmt or {}).get("tiles") or [])}
            pool = [t for t in reach if t in dgoal]
            if pool:
                col, row = reach[min(pool, key=lambda t: dgoal[t])]
                rpc(s, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": wb["id"], "to": {"col": col, "row": row}}}, 60)
            rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if not offered:
            print("aucune cible legale atteinte")
            return 4

        dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        wb = next(u for u in dec["units"] if u["id"] == wb0["id"])
        ens = [u for u in dec["units"] if u.get("owner") != me and u.get("alive")]
        legal_ids = {t.get("targetId") for t in offered if t.get("kind") == "unit"}
        far = next((e for e in ens if e["id"] not in legal_ids), None)
        near = next(e for e in ens if e["id"] in legal_ids)
        print("caster=u%s pos=%s | ennemis offerts=%s | ennemi HORS gate=%s"
              % (wb["id"], wb.get("pos"), sorted(legal_ids),
                 (far or {}).get("id")))

        print("DECOMPOSITION (meme caster, meme etat, seule la CIBLE change) :")
        cast(s, rid, wb["id"], wb["id"], "A cible=CASTER (self)")
        cast(s, rid, wb["id"], ally0["id"], "B cible=ALLIE (orksNob)")
        if far is not None:
            cast(s, rid, wb["id"], far["id"], "C cible=ENNEMI hors portee charge")
        else:
            print("  C non testable (tous les ennemis sont dans le gate)")
        d = cast(s, rid, wb["id"], near["id"], "D cible=ENNEMI offert par E0")

        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        print("POSE apres D :")
        for u in dv["units"]:
            w = [e.get("name") for e in (u.get("effects") or [])
                 if (e.get("name") or "").startswith("Waaagh_")]
            if w or (u.get("visualId") or "").startswith("orksNpc"):
                print("  u%-4s %-22s alive=%-5s waaagh=%s"
                      % (u.get("id"), u.get("visualId"), u.get("alive"), w))
        return 0 if d.get("mutated") else 5
    finally:
        if not a.keep:
            subprocess.run([sys.executable, sibling_script("rl_duel.py"), "dispose",
                            "--state-file", a.state_file], capture_output=True, text=True)


if __name__ == "__main__":
    raise SystemExit(main())
