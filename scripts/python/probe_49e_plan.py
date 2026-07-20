#!/usr/bin/env python
"""Probe #49e : dump du plan d'attaque u87 au s14 31337 — la paire (69,81) et la tuile (3,4)
sont-elles ENUMEREES (attackPlans maxRank=32) ? Miss residuel : natif 69->81@(3,4) u=28.86,
moteur 69->79@(4,3) u=12.51 ; formule et prediction OK sur la paire native -> le sweep n'a
probablement jamais evalue (81,(3,4)).

Usage: python probe_49e_plan.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_49gnt_state.json"
STOP = 14


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337",
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[49e] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[49e] runner={rid} -> walk s{STOP}")
    try:
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[49e] natif epuise au pas {step}")
                return 3
            acts = []
            for m in (dry["action"]["messages"] or []):
                if m.get("cls") == "MoveUnitMessage":
                    acts.append({"kind": "move", "unitId": m["unitId"],
                                 "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
                elif m.get("cls") == "ActiveAbilityMessage":
                    acts.append({"kind": "ability", "casterId": m["casterId"],
                                 "targetId": m.get("targetId"),
                                 "abilityType": m["abilityType"]})
                elif m.get("cls") == "FinishUnitTurnMessage":
                    acts.append({"kind": "finish", "unitId": m["unitId"]})
            if acts:
                _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        plans = dv.get("attackPlans") or []
        p87 = next((p for p in plans if p.get("unitId") == 87), None)
        if p87 is None:
            print("[49e] pas de plan u87 ; unitIds plans:", [p.get("unitId") for p in plans][:12])
            return 4
        for ev in (p87.get("evals") or []):
            if ev.get("abilityId") != 69:
                continue
            ranked = ev.get("ranked") or []
            tiles = [(rk.get("col"), rk.get("row")) for rk in ranked]
            print(f"[49e] eval 69->tgt{ev.get('targetId')}: rankCount={ev.get('rankCount')} "
                  f"nTiles={len(tiles)} has(3,4)={(3, 4) in tiles} has(4,3)={(4, 3) in tiles}")
            print(f"       tiles: {tiles[:20]}{' ...' if len(tiles) > 20 else ''}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[49e] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
