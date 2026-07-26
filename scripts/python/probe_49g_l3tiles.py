#!/usr/bin/env python
"""Probe #49g : par-feuille NATIF (L3 utility_score) des tuiles (3,4) et (4,3) au s14 31337.

Post RitesOfBattle : nos Tile7 restent (3,4)=5.0 / (4,3)=30.0 (aucun allie adjacent a ces
tuiles) et l'argmax attaque flippe encore vers 79@(4,3). L'ecart natif Tile7 doit etre
< 16.35 -> une AUTRE feuille diverge. Capture L3 pendant le dry-run du pas (le sweep natif
emet utility_score par feuille par caseTile) puis diff.

Usage: python probe_49g_l3tiles.py
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
TRACES = ROOT / "frida" / "data" / "ai-traces"   # host cwd = frida/ (cf. ai-trace-store.ts)
STOP = 14
TILES = {(3, 4), (4, 3)}


def _r(sid: int, method: str, body, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337",
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[49g] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[49g] runner={rid} -> walk s{STOP}")
    try:
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[49g] natif epuise au pas {step}")
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

        _rpc(sid, "aiTraceEnable", ["L3"], timeout=20)
        st = (_rpc(sid, "aiTraceStatus", [], timeout=20).get("result") or {})
        lo = st.get("seq")
        _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)   # le sweep natif emet les utility_score
        st2 = (_rpc(sid, "aiTraceStatus", [], timeout=20).get("result") or {})
        hi = st2.get("seq")
        _rpc(sid, "aiTraceDisable", ["L3"], timeout=20)
        print(f"[49g] fenetre seq: ({lo}, {hi}]")

        files = sorted(TRACES.glob(f"{sid}-*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not files:
            print(f"[49g] pas de trace {sid}-*.jsonl dans {TRACES}")
            return 4
        out: dict = {}
        with open(files[-1], encoding="utf-8") as f:
            for line in f:
                if '"utility_score"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("evt") != "utility_score":
                    continue
                sq = e.get("seq")
                if sq is None or (hi is not None and sq > hi) or (lo is not None and sq <= lo):
                    continue
                eu = e.get("unit")
                eun = eu.get("name") if isinstance(eu, dict) else eu
                if eun and eun != "ultraCalgar":
                    continue
                ct = e.get("caseTile") or {}
                t = (ct.get("col"), ct.get("row")) if isinstance(ct, dict) else tuple(ct or ())
                if t not in TILES:
                    continue
                extra = {k: v for k, v in e.items()
                         if k not in ("evt", "seq", "unit", "caseTile", "utility", "score")}
                out.setdefault(t, []).append((e.get("seq"), str(e.get("utility") or ""),
                                              e.get("score"), extra))
        for t in sorted(TILES):
            evs = out.get(t) or []
            nz = [x for x in evs if x[2]]
            print(f"[49g] NATIF tile {t}: {len(evs)} events, {len(nz)} non-zero:")
            for sq, leaf, score, extra in nz:
                print(f"    seq={sq} {leaf} = {score} extra={json.dumps(extra, default=str)[:120]}")
        print("[49g] OFFLINE (rappel probe 49f) : Tile7 (3,4)=5.0 / (4,3)=30.0")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[49g] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
