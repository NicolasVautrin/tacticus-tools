#!/usr/bin/env python
"""Probe #57a : move-formula 12345 s5 u89 — natif (0,4) [pathdist 7] vs nous (1,4) [pathdist 6].

Identifie u89 (ids par-seed), son kit move-relevant (NC / triggered / unit-specific), et
compare les entrees : pathDistToEnemies, tuiles legales, positions ennemies. But : savoir si
le natif utilise un TERME de move non modelise ou une autre semantique MinDist.
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
STATE = ROOT / "data" / "_57_state.json"
STOP = 5
UID = 89
TILES = [(0, 4), (1, 4)]


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
        print(f"[57] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57] walk stoppe au pas {step}")
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
        units = {u.get("id"): u for u in (dv.get("units") or [])}
        u = units.get(UID) or {}
        vid = u.get("visualId")
        gu = GC.unit(vid) or {}
        print(f"[57] u{UID}: visualId={vid} pos={u.get('pos')} team={u.get('team')} hp={u.get('hp')}")
        print(f"[57] kit: traits={gu.get('traits')} activeAbilities={gu.get('activeAbilities')} "
              f"passiveAbilities={gu.get('passiveAbilities')}")
        print(f"[57] dv abilities: {[(a.get('id'), a.get('kind')) for a in (u.get('abilities') or [])]}")
        epos = [(x.get('id'), x['pos']['col'], x['pos']['row']) for x in (dv.get('units') or [])
                if x.get('team') != u.get('team') and x.get('alive', True) and x.get('pos')]
        print(f"[57] ennemis: {epos}")
        pdr = _r(sid, "pathDistToEnemies", {"runnerId": rid, "unitId": UID}, 90)
        pd = {(t.get("col"), t.get("row")): t.get("pathDist") for t in (pdr.get("tiles") or [])}
        for t in TILES:
            print(f"[57] pathDistToEnemies{t} = {pd.get(t)}")
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == UID), None) or {}
        mt = [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])]
        print(f"[57] movable ({len(mt)}): {mt}")
        print(f"[57] dans movable: (0,4)={ (0,4) in mt } (1,4)={ (1,4) in mt }")
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
