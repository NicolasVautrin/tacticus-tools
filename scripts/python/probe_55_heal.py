#!/usr/bin/env python
"""Probe #55 : heal x3 (12345 s13, u91 Heal(18) self, off 2008 vs nat 6024).

Identifie le caster reel (ids par-seed !), son arme (hits), son attack stat, et confronte
la formule `HealAmount = StatAmount(weapon) x Max(WeaponHighestHits(weapon),1)` aux
healEvents natifs (aiPlaybookPredict).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.playbook import scene as scene_mod  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_55_state.json"
STOP = 13
UID = 91


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    import gameconfig as GC
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "12345",
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[55] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[55] walk stoppe au pas {step}")
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

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 8}, 180)
        u = next((x for x in (dv.get("units") or []) if x.get("id") == UID), None) or {}
        vid = u.get("visualId")
        print(f"[55] u{UID}: visualId={vid} hp={u.get('hp')} team={u.get('team')}")
        gu = GC.unit(vid) or {}
        print(f"[55] gameconfig weapons: {json.dumps(gu.get('weapons'))[:300]}")
        print(f"[55] abilities dv: {[ (a.get('id'), a.get('kind')) for a in (u.get('abilities') or []) ]}")

        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
        su = next((x for x in (snap.get("units") or []) if x.get("entityId") == UID), None) or {}
        na = su.get("normalAttack") or {}
        st = su.get("stats") or {}
        print(f"[55] snap: attack={st.get('attack')} normalAttack={na}")

        resp = _r(sid, "aiPlaybookPredict",
                  {"runnerId": rid, "unitId": UID, "targetId": UID, "abilityType": 18,
                   "col": 4, "row": 2}, 60)
        print(f"[55] aiPlaybookPredict(18,self)@ (4,2): ok={resp.get('ok')}")
        for ev in (resp.get("healEvents") or []):
            print(f"[55]   healEvent: {ev}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
        try:
            STATE.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
