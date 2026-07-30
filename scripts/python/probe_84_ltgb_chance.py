#!/usr/bin/env python
"""Probe #84b -- frequence du `Maybe(ConfigConst 0x2a)` de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` : combien d'attaques d'un porteur (cible sur tuile SANS status-effect) gagnent le coup
additionnel ? Accumule les tirages sur PLUSIEURS runners (le round-cap borne un runner a ~12 attaques).

ASCII only. Usage: python probe_84_ltgb_chance.py --builds 5 --rounds 12
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
# SORTIE de run -> `logs/` RELATIF au checkout (#314) : un chemin absolu ferait
# ecrire ce probe dans l'arbre principal depuis un worktree d'agent.
STATE = PYDIR.parents[1] / "logs" / "runners" / "_probe84_ltgb_chance_state.json"
SID = None


def rpc(rid_method, body, timeout=90):
    r = _rpc(SID, rid_method, body, timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def one_build(seed: int, rounds: int, attacker: str):
    out = subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "build",
                          "--seed", str(seed), "--state-file", str(STATE),
                          "--p-units", attacker, "--a-units", "bloodSanguinary",
                          "--board", "MC1_67", "--hp-target", "900000",
                          "--hp-player", "900000"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    rid = None
    for ln in (out.stdout or "").splitlines():
        if "runnerId=" in ln:
            rid = int(ln.split("runnerId=")[1].split()[0])
            break
    if rid is None:
        print("[build KO]", (out.stdout or "")[-300:], (out.stderr or "")[-300:])
        return []

    def dview():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})

    def tile_fx():
        tm = rpc("tileMeta", {"runnerId": rid}, 60)
        return {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                for t in (tm.get("tiles") or [])}

    dv = dview()
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("ctrl")), None)
    en = next((u for u in units if not u.get("ctrl")), None)
    if me is None or en is None:
        return []
    myp, aid, tid = me.get("owner"), me["id"], en["id"]
    norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    walk = [(t.get("col"), t.get("row")) for t in (bg.get("tiles") or []) if t.get("walkable")]

    rows = []
    for _ in range(rounds):
        for _ in range(6):
            dv = dview()
            if dv.get("currentPlayer") == myp:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        else:
            break
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        me = next((u for u in units if u.get("id") == aid), None)
        en = next((u for u in units if u.get("id") == tid), None)
        if me is None or en is None:
            break
        T = upos(en)
        nb = [c for c in walk if hexgeo.distance(c, T) == 1]
        if not T or not nb:
            break
        if upos(me) not in nb:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": aid, "to": {"col": nb[0][0], "row": nb[0][1]}}}, 40)
        fx_before = tile_fx().get(T) or []
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid, "abilityType": norm["id"]}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        n = 0
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == norm["id"]:
                n += 1
        if n:
            rows.append((tuple(fx_before), n))
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "dispose",
                    "--runner", str(rid), "--state-file", str(STATE)],
                   capture_output=True, text=True)
    return rows


def main():
    global SID
    ap = argparse.ArgumentParser()
    ap.add_argument("--builds", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--seed0", type=int, default=84100)
    ap.add_argument("--attacker", default="blackTerminator")
    args = ap.parse_args()
    SID = _resolve_session()
    allrows = []
    for i in range(args.builds):
        r = one_build(args.seed0 + i, args.rounds, args.attacker)
        allrows += r
        a = [n for fx, n in allrows if not fx]
        b = [n for fx, n in allrows if fx]
        base = min(a) if a else 0
        print(f"[build {i}] +{len(r)} tirages | A n={len(a)} base={base} "
              f"succes={sum(1 for n in a if n > base)} ({100.0*sum(1 for n in a if n > base)/max(1,len(a)):.1f}%) "
              f"| B n={len(b)} all_base_plus_1={all(n == base + 1 for n in b) if b else None}")
    a = [n for fx, n in allrows if not fx]
    b = [n for fx, n in allrows if fx]
    base = min(a) if a else 0
    k = sum(1 for n in a if n > base)
    print("\n=== TOTAL ===")
    print(f"BRANCHE A (tuile cible SANS status-effect) : n={len(a)} base={base} "
          f"succes(base+1)={k} -> {100.0*k/max(1,len(a)):.1f}%")
    print(f"BRANCHE B (tuile cible AVEC status-effect) : n={len(b)} hits={b}")


if __name__ == "__main__":
    main()
