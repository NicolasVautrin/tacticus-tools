#!/usr/bin/env python
"""Probe #49b : FALSIFICATION du mecanisme « ring-2 occupancy-gated » (verdict re-expert).

Verdict decompile : admission bucket = util >= Min(3,total) (@18004cc80, op_GreaterThanOrEqual) ;
util NON cappee ; ring-2 = portee board-graph slot 0x65 GATEE PAR L'OCCUPATION (pas la distance
geometrique). A s14 : l'unique chemin 2-pas (5,4)->(3,5) passe par (4,4) OCCUPEE par u79 ->
u81 exclu -> arc natif = 2 < 3 -> bucket vide (mesure). Notre in_arc dist==2 passe-tout -> 3.

Prediction falsifiable executee ici :
  1. s14 baseline : ncEvaluate(u87, 1000, sweep) -> bucket VIDE partout (controle).
  2. MOVE u79 (4,4) -> tuile adjacente libre de (5,4) [(5,5) ou (6,4)] via applyAction.
  3. re-ncEvaluate : le bucket doit devenir NON-VIDE (u81 rejoignable via (4,4) libre,
     u79 reste ring-1 de (5,4) -> arc=3 >= seed 3).
Si 3. reste vide -> le mecanisme est autre chose (ne PAS porter le BFS occupation).

Usage: python probe_49b_occupancy.py [--seed 31337] [--stop-step 14]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_49gnt_state.json"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[49b] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def nc_summary(res: dict) -> str:
    """Resume compact d'un retour ncEvaluate : positions avec bucket non-vide (shape-tolerant)."""
    outs = []
    for p in (res.get("positions") or res.get("results") or []):
        if not isinstance(p, dict):
            continue
        best = p.get("best") or p.get("bucket") or None
        if best:
            if isinstance(best, dict):
                act = best.get("action") if isinstance(best.get("action"), dict) else {}
                outs.append(f"({p.get('col')},{p.get('row')}) util={best.get('util')} "
                            f"tgt={act.get('target')}")
            else:
                outs.append(f"({p.get('col')},{p.get('row')}) best={best!r}")
    return ("NON-VIDE: " + "; ".join(outs)) if outs else "VIDE partout"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--stop-step", type=int, default=14)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    print(f"[49b] seed={args.seed} runner={rid} -> walk jusqu'au pas {args.stop_step}")

    try:
        for step in range(args.stop_step):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[49b] natif epuise au pas {step} ({dry.get('error')})")
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

        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
               for u in (dv.get("units") or []) if u.get("pos")}
        occ = set(pos.values())
        print(f"[49b] positions s14: u87={pos.get(87)} u77={pos.get(77)} "
              f"u79={pos.get(79)} u81={pos.get(81)}")

        base = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": 87, "abilityType": 1000,
                                      "sweep": True}, 90)
        print(f"[49b] BASELINE keys={list(base.keys())}")
        print(f"[49b] BASELINE (brut, 700c): {json.dumps(base, default=str)[:700]}")
        print(f"[49b] BASELINE ncEvaluate: ok={base.get('ok')} -> {nc_summary(base)}")

        # destination : tuile adjacente de (5,4) LIBRE parmi (5,5)/(6,4) (gardent u79 ring-1)
        dest = next((d for d in [(5, 5), (6, 4)] if d not in occ), None)
        if dest is None:
            print("[49b] aucune destination libre parmi (5,5)/(6,4) -- abandon")
            return 4
        mv = _r(sid, "applyAction", {"runnerId": rid, "actions": [
            {"kind": "move", "unitId": 79, "to": {"col": dest[0], "row": dest[1]}}]}, 60)
        dv2 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        pos2 = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv2.get("units") or []) if u.get("pos")}
        print(f"[49b] move u79 -> {dest}: ok={mv.get('ok')} err={mv.get('error')} "
              f"pos(u79)={pos2.get(79)}")
        if pos2.get(79) != dest:
            print("[49b] u79 n'a PAS bouge -- test non concluant (applyAction refuse ?)")
            return 5

        after = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": 87, "abilityType": 1000,
                                       "sweep": True}, 90)
        print(f"[49b] APRES move ncEvaluate: ok={after.get('ok')} -> {nc_summary(after)}")
        raw = json.dumps(after, default=str)
        print(f"[49b] APRES (brut, 900c): {raw[:900]}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[49b] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
