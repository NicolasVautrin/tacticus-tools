#!/usr/bin/env python
"""Probe #65 repro DETERMINISTE — replique le fixture test_offline_attack_reproduces_live_damage
epingle sur seed 123, capture CHAQUE cas mono-coup (clean + block-divergent) et sauve un JSON
rejouable OFFLINE-only du cas ou offline != live.

Pour chaque cas : mesure block_sources offline, port execute() (per-hit/rolls/did_block), LIVE,
et discriminant offline-SANS-block. Sauve data/rl-state/p65-repro-<seed>-<att>-<tgt>.json.

ASCII only. Usage: python probe_65_block_repro.py [--seed 123]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import predict_samples as PV  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "rl-state" / "p65repro.json"


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def build(seed, board="MC1_67"):
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", board],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[p65] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        return -1, None
    d = json.loads(STATE.read_text())
    return d["runnerId"], d.get("myTeam", 1)


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=123)
    args = ap.parse_args()
    sid = _resolve_session()

    def rpc(method, body, t=90):
        return _r(sid, method, body, t)

    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.damage_model import defender_modifiers, defender_fixed_armor

    rid, my_team = build(args.seed)
    if rid < 0:
        return
    try:
        if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
            print("dumpRng indispo")
            return
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        rows = PV.build_samples(sid, rid, my_team, 6)
        print(f"seed {args.seed} rid {rid}: {len(rows)} rows")
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 3, "allAbilities": True}, 90)
        cur = dec.get("currentPlayer")
        u_by_id = {u["id"]: u for u in (dec.get("units") or [])}
        tile_by = {}
        for ap2 in (dec.get("attackPlans") or []):
            for ev in (ap2.get("evals") or []):
                rk = (ev.get("ranked") or [{}])[0]
                tile_by[(ap2.get("unitId"), ev.get("targetId"))] = (rk.get("col"), rk.get("row"))

        found = []
        for r in rows:
            if r["hits"] != 1 or not PV.sample_is_clean(r):
                continue
            att, tgt = r["att"], r["tgt"]
            a = u_by_id.get(att)
            if not a or a.get("owner") != cur:
                continue
            norm = next((ab for ab in (a.get("abilities") or []) if ab.get("kind") == "normal"), None)
            if not norm:
                continue
            col, row = tile_by.get((att, tgt), (None, None))
            if col is not None:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": att, "to": {"col": col, "row": row}}}, 40)
            dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
            state = load_state(dv2, ob2, snap)
            te = state.get_entity(tgt)
            hc = te.get_component(HealthComponent) if te is not None else None
            if hc is None or hc.hp is None:
                continue
            hp_before = hc.hp
            s1 = rpc("dumpRng", {"runnerId": rid}, 30)
            if not _ok(s1):
                continue
            state.rng = _seed_rng(s1)
            # mesure block avant l'attaque
            tsc = te.get_component(StatsComponent)
            thc = te.get_component(HealthComponent)
            armor = defender_fixed_armor(state, tgt)
            def_mods, _da = defender_modifiers(state, tgt, thc.hp, is_melee=True,
                                               damage_profile=None, attacker_id=att,
                                               is_normal_attack=True)
            blk = AttackDamageOperation._block_sources(tsc, _da, armor)
            runner = Runner(state).install_default_handlers(20)
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": att, "targetId": tgt,
                "abilityType": norm["id"]}}, 40)
            s2 = rpc("dumpRng", {"runnerId": rid}, 30)     # RNG APRES l'attaque live
            live_ndraw = (s2["mti"] - s1["mti"] + (624 if s2["mti"] < s1["mti"] else 0)) \
                if (_ok(s1) and _ok(s2)) else None
            if not (_ok(res) and (res.get("actions") or [{}])[0].get("ok")):
                continue
            live_after = next((u.get("hp") for u in (res.get("units") or [])
                               if u.get("squadId") == tgt), None)
            if live_after is None:
                continue
            runner.apply(AttackUnitMessage(att, tgt))
            off_ndraw = state.rng.mti - s1["mti"] + (624 if state.rng.mti < s1["mti"] else 0)
            rr = runner.damage_handler.last
            off_after = state.get_entity(tgt).get_component(HealthComponent).hp
            live_dmg = hp_before - int(live_after)
            tgt_dv = next((u for u in (dv2.get("units") or []) if u.get("id") == tgt), {})
            eff = [e.get("type") or e.get("name") for e in (tgt_dv.get("effects") or [])]
            div = off_after != live_after
            tag = "  <<< DIVERGENT" if div else ""
            print(f"u{att}->u{tgt} ({r.get('tgtVis')}): live_dmg={live_dmg} off_total={rr['total']} "
                  f"did_block={rr['did_block']} blk={blk} live_ndraw={live_ndraw} off_ndraw={off_ndraw} "
                  f"eff={eff}{tag}")
            if div:
                out = ROOT / "data" / "rl-state" / f"p65-repro-{args.seed}-{att}-{tgt}.json"
                out.write_text(json.dumps({
                    "seed": args.seed, "att": att, "tgt": tgt, "tgtVis": r.get("tgtVis"),
                    "norm_id": norm["id"], "hp_before": hp_before, "live_after": int(live_after),
                    "live_dmg": live_dmg, "off_total": rr["total"], "off_after": off_after,
                    "block_sources": [vars(b) for b in (blk or [])], "armor": armor,
                    "target_effects": eff, "rng_s1": s1,
                    "dv2": dv2, "ob2": ob2, "snap": snap,
                }))
                found.append(str(out))
                print(f"    JSON: {out}")
        print(f"\n=== {len(found)} cas divergents captures ===")
        for f in found:
            print("  " + f)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


if __name__ == "__main__":
    main()
