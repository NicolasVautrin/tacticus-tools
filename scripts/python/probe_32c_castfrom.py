#!/usr/bin/env python
"""Probe #32c : eligibilite PAR POSITION native (castFromTiles) pour TheQuickening au s15 31337.

Hypothese : notre filtre hex-dist<=2 accepte (3,6)->tuile 52 alors que le natif (movement range,
GetInvalidTargetReason par tuile) la refuse -> notre tie util=3 a (3,6) est un FAUX eligible.

Usage: python probe_32c_castfrom.py
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
STATE = ROOT / "logs" / "runners" / "_32ct_state.json"
STOP = 15
UID = 81
ABILITY = 1151
TARGETS = [52, 44, 45, 53, 35, 46]   # tuile 52=(4,4) = la cible du tie + voisines vues au sweep


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337",
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[32c] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[32c] runner={rid} -> walk s{STOP}")
    try:
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[32c] natif epuise au pas {step}")
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

        for tgt in TARGETS:
            cf = _r(sid, "castFromTiles", {"runnerId": rid, "casterId": UID,
                                           "targetId": tgt, "abilityType": ABILITY}, 60)
            mv = [(t.get("col"), t.get("row")) for t in (cf.get("moveTiles") or [])]
            print(f"[32c] castFromTiles tgt={tgt}: currentValid={cf.get('currentValid')} "
                  f"moveTiles={mv} ok={cf.get('ok')} err={cf.get('error')}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[32c] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
