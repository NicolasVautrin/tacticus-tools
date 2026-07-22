#!/usr/bin/env python
"""Probe #57h2 : decomposition PAR FEUILLE de NOTRE terme Tile(7) aux tuiles suspectes de
12345 s14 (u87 : nat (3,5)->t77 +20 vs eng (4,3)->t85 +30) et 2468 s16 (u79 : nat (3,4)->t89
+30 vs eng (4,2)->t91 +50).

#57h a etabli (pairUtility natif == notre u, bit-pres, 4 paires) que TOUTE la divergence de ces
2 misses est dans le terme de tuile u_full-u. Ce probe identifie QUELLE(S) feuille(s) portent
nos +20/+30/+50 -> candidates au diff L3 par-feuille (a lancer en session CALME, L3 global).

Usage: python probe_57h2_tileterm.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine import weights  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.playbook import scene as _scene  # noqa: E402
from engine.playbook.base import tile_utility  # noqa: E402
from engine.utilities.tile import (TILE_LEAVES, TILE_LEAF_IDS,  # noqa: E402
                                   terrain_tile_effects, tile_leaf_ctx)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_57h_state.json"

#            seed     stop uid  tuiles a decomposer
CASES = {"S14": ("12345", 14, 87, [(3, 5), (4, 3), (3, 4), (3, 2)]),
         "S16": ("2468",  16, 79, [(3, 4), (4, 2), (4, 3)])}


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _apply_native(sid: int, rid: int, dry: dict) -> None:
    acts = []
    for m in (dry["action"]["messages"] or []):
        if m.get("cls") == "MoveUnitMessage":
            acts.append({"kind": "move", "unitId": m["unitId"],
                         "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
        elif m.get("cls") == "ActiveAbilityMessage":
            acts.append({"kind": "ability", "casterId": m["casterId"],
                         "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
        elif m.get("cls") == "FinishUnitTurnMessage":
            acts.append({"kind": "finish", "unitId": m["unitId"]})
    if acts:
        _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)


def run_case(sid: int, tag: str, seed: str, stop: int, uid: int, tiles: list) -> None:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed,
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[57h2:{tag}] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[57h2:{tag}] seed={seed} runner={rid} -> walk s{stop}")
    try:
        rpc_l = lambda m, b, t: _r(sid, m, b, t)  # noqa: E731
        predictor = _scene.build_predictor(rpc_l, rid)
        for step in range(stop):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57h2:{tag}] natif epuise au pas {step}")
                return
            _apply_native(sid, rid, dry)

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        _scene.refresh_shields(predictor, rpc_l, rid)
        wt = weights.load()
        ctx = _ai_ctx.build(rpc_l, rid, dv, mov_by_unit, uid, wt, predictor)
        lctx = tile_leaf_ctx(ctx)

        for pos in tiles:
            meta: dict = {}
            e = ctx.elev_by_pos.get(pos)
            if e is not None:
                _elevs = [x for x in ctx.elev_by_pos.values() if x is not None]
                meta = {"elevation": e, "elevation_max": max(_elevs),
                        "elevation_min": min(_elevs)}
            if pos in ctx.is_temporary_by_pos:
                meta["is_temporary"] = ctx.is_temporary_by_pos[pos]
            _effs = list(ctx.effects_by_pos.get(pos) or [])
            _effs += terrain_tile_effects((getattr(ctx, "terrain_by_pos", None) or {}).get(pos))
            if _effs:
                meta["effects"] = _effs
            total = tile_utility(ctx, pos)
            parts = []
            for i in TILE_LEAF_IDS:
                name, leaf = TILE_LEAVES.get(i, (None, None))
                if leaf is None:
                    continue
                v = leaf.evaluate(pos, meta, lctx, wt)
                if v:
                    parts.append(f"{name}({i})={v:+.3f}")
            print(f"[57h2:{tag}] tuile {pos}: total={total:+.3f} meta={meta} | " + " ".join(parts))
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[57h2:{tag}] runner {rid} dispose")
        except Exception:
            pass


def main() -> int:
    sid = _resolve_session()
    for tag, (seed, stop, uid, tiles) in CASES.items():
        run_case(sid, tag, seed, stop, uid, tiles)
    return 0


if __name__ == "__main__":
    sys.exit(main())
