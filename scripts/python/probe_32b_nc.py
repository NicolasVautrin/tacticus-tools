#!/usr/bin/env python
"""Probe #32b : compare le Bucket NC NATIF (ncEvaluate par position) a notre
EvaluateNonComparable par tuile, pour une ability NC au pas d'un miss cast-tile.

Usage: python probe_32b_nc.py --seed 909 --stop 17 --uid 95 --ability 1202 --tiles "3,4;4,2"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import engine_validate as EV  # noqa: E402
from engine.playbook import scene as scene_mod  # noqa: E402
from engine import weights as W  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_32ct_state.json"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", required=True)
    ap.add_argument("--stop", type=int, required=True)
    ap.add_argument("--uid", type=int, required=True)
    ap.add_argument("--ability", type=int, required=True)
    ap.add_argument("--tiles", default="")
    ap.add_argument("--board", default="MC1_67")
    args = ap.parse_args()
    tiles = set()
    for part in (args.tiles.split(";") if args.tiles else []):
        c, r = part.split(",")
        tiles.add((int(c), int(r)))

    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", args.seed,
         "--state-file", str(STATE), "--board", args.board],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[32b] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[32b] runner={rid} seed={args.seed} -> walk s{args.stop}")
    try:
        rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
        predictor = scene_mod.build_predictor(rpc, rid)
        wt = W.load()
        for step in range(args.stop):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[32b] natif epuise au pas {step}")
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

        # positions/identites
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        u0 = (dv.get("units") or [{}])[0]
        print(f"[32b] dv unit keys: {sorted(u0.keys())}")
        for u in (dv.get("units") or []):
            p = u.get("pos") or {}
            print(f"[32b]   unit id={u.get('id')} vis={u.get('visualId')} team={u.get('team')} "
                  f"pos=({p.get('col')},{p.get('row')}) hp={u.get('hp')}")

        # NATIF : bucket NC par position
        nc = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": args.uid,
                                    "abilityType": args.ability, "sweep": True}, 120)
        print(f"[32b] NATIF ncEvaluate ok={nc.get('ok')} playbook={nc.get('playbookClass')}")
        for row in (nc.get("positions") or []):
            pos = row.get("pos")
            t = tuple(pos) if isinstance(pos, list) else pos
            bk = row.get("bucket")
            mark = " <== INTERET" if (isinstance(t, tuple) and tuple(t) in tiles) else ""
            print(f"[32b]   pos={t} cur={row.get('cur')} hvt={row.get('hvt')} "
                  f"bucket={json.dumps(bk, default=str)[:160]}{mark}")

        # MOTEUR : notre EvaluateNonComparable par tuile rankee
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        if predictor is not None:
            scene_mod.refresh_shields(predictor, rpc, rid)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        from engine.ai import context as _ai_ctx
        from engine.playbook import noncomparable as playbooks
        ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, args.uid, wt, predictor, debug=False)
        nc_ctx = playbooks.NCContext(
            uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
            enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos,
            walkable_by_pos=ctx.walkable_by_pos,
            plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
            elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets,
            wt=ctx.wt, is_temporary_by_pos=ctx.is_temporary_by_pos,
            effects_by_pos=ctx.effects_by_pos, obs_units=ctx.obs_units,
            tile_id_by_pos=ctx.tile_id_by_pos, active_levels=ctx.active_ability_levels,
            units=ctx.units, cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene, debug=True)
        pb = playbooks.playbook_for(args.ability)
        if pb is None:
            print(f"[32b] playbook NC {args.ability} introuvable dans le registre python")
        else:
            try:
                cands = pb.generate_candidates(nc_ctx)
                print(f"[32b] ENG generate_candidates -> {json.dumps(cands, default=str)}")
            except Exception as e:
                print(f"[32b] ENG generate_candidates ERR {e}")
            plan = nc_ctx.plan
            for ev in (plan.get("evals") or []):
                if ev.get("abilityId") != args.ability or not ev.get("rankCount"):
                    continue
                tgt = ev.get("targetId")
                for rk in (ev.get("ranked") or []):
                    tile = (rk.get("col"), rk.get("row"))
                    if tile[0] is None:
                        continue
                    try:
                        nu = pb.evaluate_non_comparable(tile, tgt, nc_ctx)
                    except Exception as e:
                        nu = f"ERR {e}"
                    mark = " <== INTERET" if tile in tiles else ""
                    print(f"[32b] ENG ab={args.ability} tgt={tgt} tile={tile} u={nu}{mark}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[32b] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
