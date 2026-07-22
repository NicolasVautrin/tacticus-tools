"""Probe #39b — trace TurnsStarted (stat 12) de TOUTES les unites a CHAQUE pas du walk natif.

Question : le compteur `UnitComponent.turnsStarted@+0x58` (incremente par StartTurnOperation
@180ea3fb0 sur les CurrentlyOwnedUnitIds du joueur COURANT) avance-t-il pour les DEUX camps,
ou reste-t-il fige a 1 pour le camp a-units (ce qui serait LE mecanisme interne du pseudo
« gate per-joueur » de 1180 : slot-4 @18111af90 = GetStat(unit,12)>1 jamais ouvert) ?

Usage : python probe_39b_tscounter.py --runner <rid> --max-steps 16
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def ts_all(sid: int, rid: int) -> dict:
    snap = _r(sid, "combatSnapshot", {"runnerId": rid})
    out = {}
    for u in (snap.get("units") or []):
        st = u.get("stats") or {}
        if st.get("turnsStarted") is not None:
            out[u.get("entityId")] = int(st["turnsStarted"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--max-steps", type=int, default=16)
    args = ap.parse_args()
    sid = _resolve_session()
    rid = args.runner

    for step in range(args.max_steps):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print("step %2d: walk end (%s)" % (step, dry.get("error") or "no action"))
            break
        msgs = (dry.get("action") or {}).get("messages") or []
        uid = dry.get("activatedUnitId")
        if uid is None:
            for m in msgs:
                uid = m.get("unitId") or m.get("casterId")
                if uid is not None:
                    break
        kinds = [(m.get("cls", "?")[:6], m.get("abilityType"), m.get("targetId")) for m in msgs]
        ts = ts_all(sid, rid)
        print("step %2d u%-3s ts=%s act=%s" % (step, uid, sorted(ts.items()), kinds))
        acts = []
        for m in msgs:
            if m.get("cls") == "MoveUnitMessage":
                acts.append({"kind": "move", "unitId": m["unitId"],
                             "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
            elif m.get("cls") == "ActiveAbilityMessage":
                acts.append({"kind": "ability", "casterId": m["casterId"],
                             "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
            elif m.get("cls") == "FinishUnitTurnMessage":
                acts.append({"kind": "finish", "unitId": m["unitId"]})
        if acts:
            _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 40)


if __name__ == "__main__":
    main()
