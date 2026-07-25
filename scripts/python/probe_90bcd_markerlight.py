"""Probe #90 groupe B -- DUREE DE VIE du marquage `Markerlight` (1122) pose par
`IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$ExecuteBehaviour` (1161).

But : savoir si le scenario DISCRIMINANT du patron « attaque filtree par un ETAT » (2e cast -> l'ennemi
DEJA marque est frappe) est atteignable dans un runner, c'est-a-dire si le marquage SURVIT jusqu'au tour
ou l'ability redevient castable. Rend, tour par tour : `remaining` du Markerlight sur chaque unite +
si 1161 est re-castable.

Usage (depuis scripts/python) :  python probe_90bcd_markerlight.py [--board C1_02] [--seed 4242]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc   # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_probe90bcd_markerlight.json"
MARKERLIGHT = 1122
ABILITY = 1161


def rpc(sid, m, b, t=90):
    r = _rpc(sid, m, [b], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def marks(sid, rid):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}) or {}
    out = {}
    for u in (dv.get("units") or []):
        for e in (u.get("effects") or []):
            if int(e.get("effectType") or -1) == MARKERLIGHT:
                out[u.get("id")] = e.get("remaining")
    alive = {u.get("id"): u.get("hp") for u in (dv.get("units") or [])}
    return out, alive


def castable(sid, rid, caster):
    at = rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ABILITY}) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    tg = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
    return tg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--turns", type=int, default=6)
    a = ap.parse_args()
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--board", a.board,
         "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden",
         "--p-mow", "tauBroadside", "--state-file", str(STATE)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("build KO:", (proc.stderr or proc.stdout or "")[-400:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}) or {}
        mow = next((m for m in (dv.get("mows") or []) if m.get("visualId") == "tauBroadside"), None)
        if mow is None:
            print("MoW non deployee")
            return 1
        caster = mow["casterId"]
        tg = castable(sid, rid, caster)
        if not tg:
            print("1161 non castable au tour 1")
            return 1
        t0 = tg[0]
        action = {"kind": "ability", "casterId": caster, "abilityType": ABILITY}
        if t0.get("kind") == "unit":
            action["targetId"] = t0["targetId"]
        else:
            action["to"] = {"col": t0["tile"]["col"], "row": t0["tile"]["row"]}
        r = rpc(sid, "applyAction", {"runnerId": rid, "action": action}) or {}
        print("cast1:", json.dumps((r.get("actions") or [{}])[0])[:200])
        m, alive = marks(sid, rid)
        print(f"T0 apres cast : marks={m} hp={alive}")
        for k in range(a.turns):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            m, alive = marks(sid, rid)
            tg = castable(sid, rid, caster)
            print(f"T{k+1} : marks={m} castable={len(tg)} hp={alive}")
            if not m:
                break
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
