#!/usr/bin/env python
"""Probe #57a-2 : 1357 s15 — (1) stats DYNAMIQUES u135 (extraHits/numberOfMembers, staleness
du ctx hydrate au spawn) ; (2) identite de l'entite-effet 116 (+400 attack) via
effectAbilityStates {Owner, AbilityType} ; (3) +400 present ailleurs ? (statModSources attack
toutes unites)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_57a2_state.json"

SEED, STOP, UID = "1357", 15, 135


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED,
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[57a2] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57a2] walk stoppe au pas {step}")
                return 1
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

        # -- 1. combatSnapshot u135 : stats CURRENT au pas (extraHits, numberOfMembers, attack) --
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        for u in (snap.get("units") or []):
            if u.get("entityId") == UID:
                st = u.get("stats") or {}
                sd = u.get("statDelta") or {}
                keep = {k: st.get(k) for k in ("attack", "extraHits", "extraHitsMelee",
                                               "numberOfMembers", "health")}
                dkeep = {k: sd.get(k) for k in ("attack", "extraHits", "numberOfMembers")
                         if sd.get(k)}
                print(f"[57a2] snap u{UID}: stats={json.dumps(keep)} statDelta={json.dumps(dkeep)}")

        # -- 2. entite-effet 116 : owner + abilityType --
        eas = _r(sid, "effectAbilityStates", {"runnerId": rid}, 120)
        if eas.get("ok"):
            found = False
            for e in (eas.get("effects") or []):
                if e.get("effectId") == 116 or e.get("source") == UID:
                    print(f"[57a2] effect: {json.dumps(e)}")
                    found = True
            if not found:
                print("[57a2] entite 116 absente de effectAbilityStates -> dump brut (20 1ers):")
                for e in (eas.get("effects") or [])[:20]:
                    print(f"[57a2]   {json.dumps(e)}")
        else:
            print(f"[57a2] effectAbilityStates KO: {eas.get('error')}")

        # -- 3. +400 attack ailleurs ? statModSources attack (toutes unites) --
        sms = _r(sid, "statModSources", {"runnerId": rid, "stats": ["attack"]}, 180)
        if sms.get("ok"):
            for u in (sms.get("units") or []):
                mods = (u.get("mods") or {}).get("attack")
                if mods:
                    print(f"[57a2] attackMods u{u.get('entityId')}: {json.dumps(mods)}")
        else:
            print(f"[57a2] statModSources KO: {sms.get('error')}")
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
