#!/usr/bin/env python
"""Probe #53 : les summons n'attaquent jamais offline (batch #52, gate x5).

Hypothese : build_predictor est COLD (pas 0) -> les summons spawnes mid-bataille n'ont
pas d'entree ctx_by_id/vis_by_id -> scene.ctx(summon)=None -> make_normal_attack_
predictions=None -> toutes tuiles refusees ("gated") -> le moteur bouge au lieu d'attaquer.

Repro : seed 1357 MC1_67, walk natif 15 pas, puis inspection de u135 (summon) :
  1. decisionView frais : u135 present ? visualId ?
  2. combatSnapshot frais : u135 present ? unitConfig/abilityStates ?
  3. scene (predictor cold) : scene.ctx(135) is None ? vis_by_id ?
  4. apres refresh_shields : toujours None ? (preuve que le refresh n'hydrate pas)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.playbook import scene as scene_mod  # noqa: E402
from engine import weights as W  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_53_state.json"
STOP = 15
SUMMON = 135


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "1357",
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[53] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
        predictor = scene_mod.build_predictor(rpc, rid)
        print(f"[53] predictor cold: {len(predictor['ctx_by_id'])} ctx, "
              f"ids={sorted(predictor['ctx_by_id'])}")
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[53] walk stoppe au pas {step}")
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

        # 1. decisionView frais
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 8}, 180)
        u = next((x for x in (dv.get("units") or []) if x.get("id") == SUMMON), None)
        print(f"[53] dv u{SUMMON}: present={u is not None} "
              f"visualId={None if u is None else u.get('visualId')} "
              f"team={None if u is None else u.get('team')} "
              f"pos={None if u is None else u.get('pos')}")
        plan = next((p for p in (dv.get("attackPlans") or []) if p.get("unitId") == SUMMON), None)
        if plan:
            evs = [(e.get("abilityId"), e.get("targetId"), e.get("rankCount"))
                   for e in (plan.get("evals") or [])]
            print(f"[53] dv attackPlans u{SUMMON}: {evs[:6]}")
        else:
            print(f"[53] dv attackPlans u{SUMMON}: ABSENT")

        # 2. combatSnapshot frais
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
        su = next((x for x in (snap.get("units") or []) if x.get("entityId") == SUMMON), None)
        if su is None:
            print(f"[53] snap u{SUMMON}: ABSENT du combatSnapshot frais")
        else:
            uc = su.get("unitConfig") or {}
            print(f"[53] snap u{SUMMON}: present, unitConfig(mult={uc.get('abilityVariablesMultiplier')}, "
                  f"passiveLvl={uc.get('passiveAbilityLevel')}), "
                  f"abilityStates={len(su.get('abilityStates') or [])}, "
                  f"normalAttack.err={(su.get('normalAttack') or {}).get('error')}")

        # 3. scene depuis predictor cold
        print(f"[53] cold ctx_by_id has u{SUMMON}: {SUMMON in predictor['ctx_by_id']}")
        print(f"[53] cold vis_by_id has u{SUMMON}: {SUMMON in predictor['vis_by_id']}")

        # 4. apres refresh_shields
        scene_mod.refresh_shields(predictor, rpc, rid)
        print(f"[53] apres refresh: ctx={SUMMON in predictor['ctx_by_id']} "
              f"vis={SUMMON in predictor['vis_by_id']} "
              f"shield_by_id={SUMMON in predictor['shield_by_id']}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
