#!/usr/bin/env python
"""Diag #65 — varTrace des resolutions GetVariableForLevel pendant le decisionView du round
WarpHail (miss +-22 : natif per-hit [570,866] vs offline minDmg_3/maxDmg_3 x mult [559,877],
MEME somme). Rejoue le scenario probe_65 (Volk vs sang, MC1_67) jusqu'a la branche WarpHail,
arme varTraceInstall, declenche le decisionView maxRank 99, dump les entries {varType, level,
value, backtrace} groupees. ASCII only. Usage: python probe_65_vartrace.py [--seed 65001]"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_65_vartrace_state.json"
W, H = 7, 9
MV_VOLK = 2


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _units_by_vis(dv):
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=65001)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", "blackObliterator", "--a-units", "bloodSanguinary",
         "--hp-player", "30000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[65vt] build KO: {(proc.stderr or proc.stdout or '')[-400:]}"); return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[65vt] runner={rid}")
    try:
        for rnd in range(6):
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            byvis = _units_by_vis(dv)
            if "blackObliterator" not in byvis:
                print("[65vt] volk perdu"); return 2
            volk = byvis["blackObliterator"]["id"]
            eff = [e.get("name") for e in (byvis["blackObliterator"].get("effects") or [])]
            branch = next((n for n in eff if n and n.startswith("FleshmetalGuns")), "<none>")
            print(f"[65vt] round {rnd}: branch={branch}")
            if branch == "FleshmetalGunsWarpHail":
                r = rpc("varTraceInstall", {}, 30)
                print(f"[65vt] varTraceInstall: {r}")
                rpc("varTraceRead", {"reset": True}, 30)          # purge
                rpc("decisionView", {"runnerId": rid, "maxRank": 99,
                                     "allAbilities": True}, 120)
                out = rpc("varTraceRead", {}, 30)
                rpc("varTraceRemove", {}, 30)
                entries = out.get("entries") or []
                print(f"[65vt] entries={out.get('count')} (cap 500)")
                groups = Counter()
                sample = {}
                for e in entries:
                    k = (e.get("varType"), e.get("level"), e.get("value"))
                    groups[k] += 1
                    if k not in sample:
                        sample[k] = e.get("backtrace") or []
                for k, n in sorted(groups.items(), key=lambda kv: -kv[1]):
                    vt, lvl, val = k
                    bt = ",".join(str(x) for x in sample[k][:4])
                    print(f"  varType={vt} level={lvl} value={val} x{n} bt=[{bt}]")
                return 0
            # avancer d'un round : park ring-3 + finish + aiturn
            sp = _pos(byvis.get("bloodSanguinary") or {})
            cur = _pos(byvis["blackObliterator"])
            if sp[0] is not None:
                ring = [t for t in hexgeo.ring(sp[0], sp[1], 3)
                        if 0 <= t[0] < W and 0 <= t[1] < H]
                goal = min(ring, key=lambda t: hexgeo.distance(t, cur)) if ring else cur
                cands = [t for t in hexgeo.disk(cur[0], cur[1], MV_VOLK)
                         if 0 <= t[0] < W and 0 <= t[1] < H and t != cur and t != sp]
                cands.sort(key=lambda t: (hexgeo.distance(t, goal), hexgeo.distance(t, cur)))
                for t in cands[:12]:
                    try:
                        rr = rpc("applyAction", {"runnerId": rid, "actions": [
                            {"kind": "move", "unitId": volk,
                             "to": {"col": t[0], "row": t[1]}}]}, 60)
                    except Exception:
                        continue
                    if isinstance(rr, dict) and rr.get("ok", True) and not rr.get("error"):
                        break
            try:
                rpc("applyAction", {"runnerId": rid,
                                    "actions": [{"kind": "finish", "unitId": volk}]}, 60)
            except Exception:
                pass
            subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                            "--state-file", str(STATE)], cwd=str(PYDIR),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("[65vt] WarpHail jamais atteint"); return 3
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[65vt] runner {rid} dispose")
        except Exception as e:
            print(f"[65vt] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
