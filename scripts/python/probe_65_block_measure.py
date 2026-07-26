#!/usr/bin/env python
"""Probe #65 MESURE (a) vs (c) — replay OFFLINE du cas capture + re-capture LIVE ndraw.

Charge logs/runners/p65-repro-123-95-79.json (etat + rng fige) et mesure OFFLINE :
  - execute() AVEC block : total / per_hit / rolls / did_block / tirages consommes ;
  - execute() SANS block (block_sources=None) : total / tirages ;
Puis re-build seed 123, re-drive u95->u79, capture dumpRng AVANT et APRES l'attaque LIVE :
  - live ndraw (tirages consommes par le natif).

Discriminant :
  (a) block spurious : offline draws = live draws + 1  ET  offline-no-block == live ;
  (c) rng shift      : offline draws = live draws       ET  block outcome differe.

ASCII only. Usage: python probe_65_block_measure.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import predict_samples as PV  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "p65measure.json"
JSON = ROOT / "logs" / "runners" / "p65-repro-123-95-79.json"


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _draws(mti0, mti1):
    return mti1 - mti0 + (624 if mti1 < mti0 else 0)


def replay_offline():
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation
    d = json.loads(JSON.read_text())
    dv2, ob2, snap = d["dv2"], d["ob2"], d["snap"]
    s = d["rng_s1"]
    att, tgt = d["att"], d["tgt"]
    print(f"=== OFFLINE replay {JSON.name} : u{att}->u{tgt} ({d.get('tgtVis')}) ===")
    print(f"  live_dmg={d['live_dmg']} block_sources={d['block_sources']} armor={d['armor']} "
          f"target_effects={d['target_effects']}")

    def mk_state():
        st = load_state(dv2, ob2, snap)
        rng = IntBasedMersenneTwister(); rng.mt = list(s["mt"]); rng.mti = s["mti"]
        st.rng = rng
        return st

    st = mk_state()
    r = AttackDamageOperation.execute(st, att, tgt)
    dr = _draws(s["mti"], st.rng.mti)
    print(f"  AVEC block   : total={r['total']} per_hit={r['per_hit']} rolls={r['rolls']} "
          f"did_block={r['did_block']} tirages={dr}")

    st2 = mk_state()
    _orig = AttackDamageOperation._block_sources
    AttackDamageOperation._block_sources = staticmethod(lambda *a, **k: None)
    try:
        r2 = AttackDamageOperation.execute(st2, att, tgt)
    finally:
        AttackDamageOperation._block_sources = _orig
    dr2 = _draws(s["mti"], st2.rng.mti)
    print(f"  SANS block   : total={r2['total']} per_hit={r2['per_hit']} tirages={dr2}")
    return d, r, r2, dr, dr2


def build(seed, board="MC1_67"):
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", board],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return -1, None
    dd = json.loads(STATE.read_text())
    return dd["runnerId"], dd.get("myTeam", 1)


def live_ndraw(off_d):
    sid = _resolve_session()

    def rpc(method, body, t=90):
        return _r(sid, method, body, t)

    rid, my_team = build(123)
    if rid < 0:
        return
    try:
        if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
            print("dumpRng indispo"); return
        rows = PV.build_samples(sid, rid, my_team, 6)
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 3, "allAbilities": True}, 90)
        cur = dec.get("currentPlayer")
        u_by_id = {u["id"]: u for u in (dec.get("units") or [])}
        tile_by = {}
        for ap2 in (dec.get("attackPlans") or []):
            for ev in (ap2.get("evals") or []):
                rk = (ev.get("ranked") or [{}])[0]
                tile_by[(ap2.get("unitId"), ev.get("targetId"))] = (rk.get("col"), rk.get("row"))
        att, tgt = off_d["att"], off_d["tgt"]
        a = u_by_id.get(att)
        norm = next((ab for ab in (a.get("abilities") or []) if ab.get("kind") == "normal"), None) if a else None
        if not norm:
            print("live: attaque normale introuvable (ids shift ?)"); return
        col, row = tile_by.get((att, tgt), (None, None))
        if col is not None:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": att, "to": {"col": col, "row": row}}}, 40)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": att, "targetId": tgt, "abilityType": norm["id"]}}, 40)
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        ok_atk = _ok(res) and (res.get("actions") or [{}])[0].get("ok")
        live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tgt), None)
        nd = _draws(s0["mti"], s1["mti"]) if (_ok(s0) and _ok(s1)) else None
        print(f"\n=== LIVE re-capture u{att}->u{tgt} : ok={ok_atk} after={live_after} tirages={nd} ===")
        print(f"\n=== DISCRIMINANT ===")
        print(f"  offline tirages AVEC block = {off_d['dr_with']}  SANS block = {off_d['dr_without']}  "
              f"live tirages = {nd}")
        if nd is not None:
            if off_d['dr_without'] == nd:
                print("  -> (a) BLOCK SPURIOUS : le natif ne tire PAS le block (draws == offline-sans-block)")
            elif off_d['dr_with'] == nd:
                print("  -> (c) le natif TIRE le block mais resultat differe (rng shift)")
            else:
                print("  -> AUTRE : divergence de draws non expliquee par le seul block")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def main():
    d, r, r2, dr, dr2 = replay_offline()
    d["dr_with"] = dr
    d["dr_without"] = dr2
    live_ndraw(d)


if __name__ == "__main__":
    main()
