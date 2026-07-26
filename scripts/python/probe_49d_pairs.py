#!/usr/bin/env python
"""Probe #49d : confrontation des paires 69->81 vs 69->79 au s14 31337 (miss residuel post-fix).

Post-fix Gauntlets (ring-1 only) : moteur emet 69->79 @(4,3), natif 69->81 @(3,4). Notre paire
scoree par le scorer natif = 28.8605 (match formule). Question : la paire NATIVE (69,81,(3,4))
score-t-elle PLUS (gap de formule sur cette paire) ou PAREIL (tie-break/terme tuile) ?

Usage: python probe_49d_pairs.py
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
STATE = ROOT / "logs" / "runners" / "_49gnt_state.json"
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
        print(f"[49d] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[49d] runner={rid} -> walk s{STOP}")
    try:
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[49d] natif epuise au pas {step}")
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

        for (tgt, tile, tag) in [(81, (3, 4), "NATIF"), (79, (4, 3), "MOTEUR"),
                                 (81, (4, 3), "croise 81@(4,3)"), (79, (3, 4), "croise 79@(3,4)")]:
            r = _r(sid, "pairUtility", {"runnerId": rid, "unitId": 87, "targetId": tgt,
                                        "abilityType": 69, "col": tile[0], "row": tile[1]}, 60)
            print(f"[49d] pair(69,{tgt})@{tile} [{tag}]: ok={r.get('ok')} "
                  f"util={r.get('utility')} err={r.get('error')}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[49d] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
