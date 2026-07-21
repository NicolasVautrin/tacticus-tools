#!/usr/bin/env python
"""Probe #54 : deltas PLATS pairUtility (+50 / -40) du batch #52 — decomposition terme a terme.

Cas A (+50, nous AU-DESSUS)  : 1357 s15, u135 (summon) ab=69 -> t162, tile (5,4)
                               off=214.9486 nat=164.9486. Suspect : gate STEPPABLE du
                               KillUnitUtility natif (@1810e1a90 : IsUnit(target) &&
                               IsSteppable(target)=HasTrait(0x1b) -> yield 0) non porte.
Cas B (-40, nous EN-DESSOUS) : 54321 s16, u81 (Mephiston) ab=69 -> t89, tile (2,4)
                               off=161.1402 nat=201.1402. Suspect : DefinitelyOverkill(40)
                               natif rate offline (hpBefore/forceOverkill/raw dans is_overkill).

Pour chaque cas : events natifs bruts (aiPlaybookPredict a la tuile) + identite de la cible
(visualId/traits) + decomposition offline (Damage/Kill/Overkill/psyker par event) + pairUtility.
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
from engine_agreement_stages import _fields_from_native_event  # noqa: E402
from engine.utilities.damage import DamageUtility, KillUnitUtility, OverkillUnitUtility  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_54_state.json"

CASES = [
    {"seed": "1357", "stop": 15, "uid": 135, "ab": 69, "tgt": 162, "tile": (5, 4)},
    {"seed": "54321", "stop": 16, "uid": 81, "ab": 69, "tgt": 89, "tile": (2, 4)},
]


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def run_case(sid: int, case: dict) -> None:
    import gameconfig as GC
    seed, stop = case["seed"], case["stop"]
    uid, ab, tgt, tile = case["uid"], case["ab"], case["tgt"], case["tile"]
    print(f"\n===== cas seed={seed} s{stop} u{uid} ab={ab} tgt={tgt} tile={tile} =====")
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed,
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[54] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
        predictor = scene_mod.build_predictor(rpc, rid)
        wt = W.load()
        for step in range(stop):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[54] walk stoppe au pas {step}")
                return
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

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        scene_mod.refresh_shields(predictor, rpc, rid)
        units = {u.get("id"): u for u in (dv.get("units") or [])}
        for xid in (uid, tgt):
            u = units.get(xid) or {}
            vid = u.get("visualId")
            traits = (GC.unit(vid) or {}).get("traits")
            print(f"[54] u{xid}: visualId={vid} team={u.get('team')} hp={u.get('hp')} "
                  f"traits={traits}")

        # hpmax : mirror ctx.hpmax_by_id (predictor hpmax_eff + fallback obs)
        hpmax = (predictor.get("hpmax_eff_by_id") or {}).get(tgt)
        print(f"[54] hpmax_eff(t{tgt})={hpmax}")

        resp = _r(sid, "aiPlaybookPredict",
                  {"runnerId": rid, "unitId": uid, "targetId": tgt, "abilityType": ab,
                   "col": int(tile[0]), "row": int(tile[1])}, 60)
        if not resp.get("ok"):
            print(f"[54] aiPlaybookPredict KO: {resp.get('error')}")
            return
        me_team = (units.get(uid) or {}).get("team")
        total = 0.0
        for i, ev in enumerate(resp.get("events") or []):
            t_id = ev.get("targetId")
            f = _fields_from_native_event(ev)
            hm = (predictor.get("hpmax_eff_by_id") or {}).get(t_id)
            du = DamageUtility().evaluate(f, hm, wt)
            ku = KillUnitUtility().evaluate(f, hm, wt)
            ou = OverkillUnitUtility().evaluate(f, hm, wt)
            sign = -1.0 if (units.get(t_id) or {}).get("team") == me_team else 1.0
            prob = (ev.get("probability") or 1.0) * (ev.get("probMult") or 1.0)
            total += sign * prob * (du + ku + ou)
            print(f"[54] ev{i} t{t_id} prob={prob} sign={sign} raw={ev}")
            print(f"[54]    fields={f}")
            print(f"[54]    Damage={du:.4f} Kill={ku:.4f} Overkill={ou:.4f} "
                  f"(hpmax={hm})")
        pu = _r(sid, "pairUtility",
                {"runnerId": rid, "unitId": uid, "targetId": tgt, "abilityType": ab,
                 "col": int(tile[0]), "row": int(tile[1])}, 60)
        print(f"[54] offline 3-feuilles total={total:.4f} | pairUtility natif="
              f"{pu.get('utility')!r} (ok={pu.get('ok')})")
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
        try:
            STATE.unlink()
        except Exception:
            pass


def main() -> int:
    sid = _resolve_session()
    for case in CASES:
        run_case(sid, case)
    return 0


if __name__ == "__main__":
    sys.exit(main())
