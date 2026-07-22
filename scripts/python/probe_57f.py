#!/usr/bin/env python
"""Probe #57f : discriminant legalite-vs-offre + determinisme (BlackRage 1163 / MartialInspiration 1191).

MISS A : 54321 s12 u93 -> offline offre BlackRage(1163), natif joue 69. (board MC1_67)
MISS B : 2468  s18 u77 -> offline offre MartialInspiration(1191), natif joue 69. (board MC1_67)
REG  C : 31337 s12 u91 -> natif emet BlackRage(1163)->85 (ref HIT) : check HP<=50%? (board defaut)

Usage : python probe_57f.py A|B|C
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
STATE = ROOT / "data" / "_57f_state.json"

# case -> (seed, stop, uid, ability, board_or_None)
CASES = {
    "A": ("54321", 12, 93, 1163, "MC1_67"),
    "B": ("2468", 18, 77, 1191, "MC1_67"),
    "C": ("31337", 12, 91, 1163, "MC1_67"),
    "D": ("31337", 16, 79, 1191, "MC1_67"),
}


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _native_decision(sid, rid):
    dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
    msgs = (dry.get("action") or {}).get("messages") or []
    out = []
    for m in msgs:
        cls = m.get("cls")
        if cls == "MoveUnitMessage":
            out.append(("move", m.get("unitId"), (m["to"]["col"], m["to"]["row"])))
        elif cls == "ActiveAbilityMessage":
            out.append(("ability", m.get("casterId"), m.get("abilityType"), m.get("targetId")))
        elif cls == "FinishUnitTurnMessage":
            out.append(("finish", m.get("unitId")))
    return dry.get("ok"), dry.get("hasNext"), out


def main():
    case = (sys.argv[1] if len(sys.argv) > 1 else "A").upper()
    seed, stop, uid, ab, board = CASES[case]
    sid = _resolve_session()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", str(STATE)]
    if board:
        cmd += ["--board", board]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[57f] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        for step in range(stop):
            ok, hasnext, acts = _native_decision(sid, rid)
            if not ok or not hasnext:
                print(f"[57f] walk stoppe au pas {step} ok={ok} hasnext={hasnext}")
                return 1
            apply = []
            for a in acts:
                if a[0] == "move":
                    apply.append({"kind": "move", "unitId": a[1], "to": {"col": a[2][0], "row": a[2][1]}})
                elif a[0] == "ability":
                    apply.append({"kind": "ability", "casterId": a[1], "targetId": a[3], "abilityType": a[2]})
                elif a[0] == "finish":
                    apply.append({"kind": "finish", "unitId": a[1]})
            if apply:
                _r(sid, "applyAction", {"runnerId": rid, "actions": apply}, 60)

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        units = {u.get("id"): u for u in (dv.get("units") or [])}
        u = units.get(uid) or {}
        print(f"[57f] case {case} seed {seed} step {stop} uid {uid} ability {ab} board {board}")
        print(f"[57f] u{uid}: vid={u.get('visualId')} hp={u.get('hp')} pos={u.get('pos')} team={u.get('team')} owner={u.get('owner')}")
        for a in (u.get("abilities") or []):
            if a.get("id") == ab:
                print(f"[57f] ability {ab} state = {json.dumps(a)}")

        cs = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
        for su in (cs.get("units") or []):
            if su.get("entityId") == uid:
                cur = (su.get("stats") or {}).get("health")
                mx = su.get("healthMax")
                pct = (100.0 * cur / mx) if (cur and mx) else None
                print(f"[57f] combatSnapshot u{uid}: health={cur} healthMax={mx} pct={pct}")

        at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": uid, "abilityType": ab}, 120)
        aunits = at.get("units") or []
        for au in aunits:
            for aa in (au.get("abilities") or []):
                if aa.get("abilityId") == ab:
                    print(f"[57f] abilityTargets: targetCount={aa.get('targetCount')} fromHereCount={aa.get('fromHereCount')}")

        seen = []
        for i in range(6):
            ok, hn, acts = _native_decision(sid, rid)
            mine = [a for a in acts if (len(a) > 1 and a[1] == uid)]
            has_ab = any(a[0] == "ability" and a[1] == uid and a[2] == ab for a in acts)
            seen.append(has_ab)
            print(f"[57f] dryRun#{i}: uid-actions={mine[:3]} offers_{ab}={has_ab}")
        print(f"[57f] DETERMINISM offers_{ab} across 6 dryRuns = {seen}  (all-True=deterministic prob1.0 ; flicker=RNG prob0.4)")
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
