#!/usr/bin/env python
"""Diag #65 (suite) — AllMods trace des coups de prediction aux rounds WarpHail (miss +-22)
et FocusedMalice (controle OK). Attendu : inputs per-coup du groupe = bornes predefined
(WarpHail [698,1096] = [388,609]x1.8 si le noeud est brut ; autre valeur = transformation
dans l'eval du noeud). ASCII only. Usage: python probe_65_allmods.py [--seed 65001]"""
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
STATE = ROOT / "logs" / "runners" / "_65_allmods_state.json"
W, H = 7, 9
MV_VOLK = 2


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _units_by_vis(dv):
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _dump_round(rpc, rid, label):
    rpc("scorerDamageTraceClear", {"runnerId": rid}, 30)
    rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 120)
    out = rpc("scorerAllModsTraceDump", {"runnerId": rid, "max": 500}, 30)
    entries = out.get("entries") or []
    print(f"[65am] {label}: entries={len(entries)} (buf={out.get('bufferSize')})")
    groups = Counter()
    outs = {}
    for e in entries:
        k = (e.get("input"), e.get("isMelee"), e.get("site"))
        groups[k] += 1
        outs.setdefault(k, []).append(round(e.get("out") or 0, 1))
    for k, n in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        inp, mel, site = k
        o = outs[k]
        print(f"  input={inp} isMelee={mel} site={site} x{n} out[0..2]={o[:3]}")


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
        print(f"[65am] build KO: {(proc.stderr or proc.stdout or '')[-400:]}"); return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[65am] runner={rid}")
    armed = False
    try:
        r = rpc("scorerDamageTraceOn", {"runnerId": rid}, 30)
        armed = bool(r.get("ok"))
        print(f"[65am] traceOn: {r}")
        if not armed:
            return 2
        dumped = set()
        for rnd in range(7):
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            byvis = _units_by_vis(dv)
            if "blackObliterator" not in byvis:
                print("[65am] volk perdu"); return 2
            volk = byvis["blackObliterator"]["id"]
            eff = [e.get("name") for e in (byvis["blackObliterator"].get("effects") or [])]
            branch = next((n for n in eff if n and n.startswith("FleshmetalGuns")), "<none>")
            print(f"[65am] round {rnd}: branch={branch}")
            if branch == "FleshmetalGunsWarpHail" and "wh" not in dumped:
                _dump_round(rpc, rid, f"round {rnd} WARPHAIL")
                dumped.add("wh")
            elif branch == "FleshmetalGunsFocusedMalice" and rnd > 0 and "fm" not in dumped:
                _dump_round(rpc, rid, f"round {rnd} FOCUSEDMALICE")
                dumped.add("fm")
            if {"wh", "fm"} <= dumped:
                return 0
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
        print("[65am] branches non atteintes:", dumped); return 3
    finally:
        try:
            if armed:
                _r(sid, "scorerDamageTraceOff", {"runnerId": rid}, 15)
        except Exception:
            pass
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[65am] runner {rid} dispose")
        except Exception as e:
            print(f"[65am] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
