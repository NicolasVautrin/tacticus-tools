#!/usr/bin/env python
"""Probe #56-t3b : ground-truth des 3 misses ability seed 1357 (board MC1_67).

  step 7  u79 -> 1197 ExcruciatingFrequencies (Comparable, ligne AoE ciblant une TILE)
  step 9  u83 -> 1016 SendInTheNextWave      (NC, util=Attack cible, MIN=max Attack ennemis)
  step 11 u93 -> 1021 Incursion              (NC, util=HP cible, MIN=max HP, gate adj>=2)

Usage : python probe_56t3b.py
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
STATE = ROOT / "data" / "_t3b_probe.json"

STOPS = {7: (79, 1197, 44, False), 9: (83, 1016, 95, True), 11: (93, 1021, 81, True)}


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main():
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "1357",
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[t3b] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        for step in range(20):
            if step in STOPS:
                uid, ab, tgt, is_nc = STOPS[step]
                dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
                units = {u.get("id"): u for u in (dv.get("units") or [])}
                print(f"\n===== STEP {step} u{uid} ability {ab} (nativeTgt={tgt}) =====")
                for u in (dv.get("units") or []):
                    p = u.get("pos") or {}
                    st = u.get("stats") or {}
                    print(f"  u{u.get('id')} team={u.get('team')} ctrl={u.get('ctrl')} "
                          f"alive={u.get('alive')} pos=({p.get('col')},{p.get('row')}) "
                          f"hp={u.get('hp')} attack={st.get('attack')} vis={u.get('visualId')}")
                at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": uid, "abilityType": ab}, 60)
                print(f"  abilityTargets: {json.dumps(at)[:1800]}")
                if is_nc:
                    nc = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": uid,
                                                "abilityType": ab, "sweep": True}, 120)
                    print(f"  ncEvaluate ok={nc.get('ok')} pb={nc.get('playbookClass')} "
                          f"evalName={nc.get('evalName')} err={nc.get('error')}")
                    for row in (nc.get("positions") or []):
                        act = row.get("action") or {}
                        print(f"    ncpos {row.get('pos')} cur={row.get('cur')} hvt={row.get('hvt')} "
                              f"util={row.get('util')} tgt={act.get('targetLow')} ab={act.get('ability')} "
                              f"bucket={row.get('bucket')} err={row.get('error')}")
                me = units.get(uid) or {}
                mp = me.get("pos") or {}
                pr = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": uid, "targetId": tgt,
                        "abilityType": ab, "col": mp.get("col"), "row": mp.get("row")}, 60)
                print(f"  aiPlaybookPredict u{uid}->tgt{tgt} ok={pr.get('ok')} err={pr.get('error')}")
                for ev in (pr.get("events") or []):
                    print(f"    NAT ev tgt={ev.get('targetId')}: {json.dumps(ev)[:400]}")
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[t3b] walk stop at step {step} ok={dry.get('ok')} hasNext={dry.get('hasNext')}")
                break
            if step in STOPS:
                msgs = [(m.get("cls"), m.get("unitId") or m.get("casterId"),
                         m.get("abilityType"), m.get("targetId"),
                         (m.get("to") or {}).get("col"), (m.get("to") or {}).get("row"))
                        for m in (dry["action"]["messages"] or [])]
                print(f"  NATIVE action step {step}: {msgs}")
            acts = []
            for m in (dry["action"]["messages"] or []):
                if m.get("cls") == "MoveUnitMessage":
                    acts.append({"kind": "move", "unitId": m["unitId"],
                                 "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
                elif m.get("cls") == "ActiveAbilityMessage":
                    acts.append({"kind": "ability", "casterId": m["casterId"],
                                 "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
                elif m.get("cls") == "FinishUnitTurnMessage":
                    acts.append({"kind": "finish", "unitId": m["unitId"]})
            if acts:
                _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)
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
