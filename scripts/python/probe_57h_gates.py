#!/usr/bin/env python
"""Probe #57h : 12345 s14 (u87, nat 69->77 vs eng 69->85) + 2468 s16 (u79, nat 69->89 vs eng 69->91).

Famille « le natif prend une paire MOINS bien notee par NOTRE scoreur » (cf.eng > cf.nat, les deux
= NOTRE pairUtility offline). L'etage UTILITE (100 %) ne confronte que la paire NATIVE -> notre
score du choix ENGINE n'a jamais ete confronte au scoreur natif. Discriminant (methode #57g) :

  pour chaque paire (native et engine), aux tuiles ranked de la paire :
    - OFF u_full pleine precision (sweep _best_attack mirror) ;
    - NATIF pairUtility (IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions) a la meme tuile.

  Cas A : natif(eng_pair) == off(eng_pair)  -> l'utilite est bonne DES DEUX COTES mais le natif ne
          JOUE pas cette paire => gate d'ELIGIBILITE (predicat vtable+0x248 de BasePlaybook /
          GetInvalidTargetReason) ou ordre -> RE cible.
  Cas B : natif(eng_pair) <  off(eng_pair)  -> NOTRE modele sur-score la paire engine (terme en trop
          ou magnitude) -> decomposer le delta.

Usage: python probe_57h_gates.py
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
from engine.playbook import get_playbook_or_default  # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_57h_state.json"

#            seed     stop uid  ab  nat_tgt eng_tgt
CASES = {"S14": ("12345", 14, 87, 69, 77, 85),
         "S16": ("2468",  16, 79, 69, 89, 91)}


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


def run_case(sid: int, tag: str, seed: str, stop: int, uid: int, ab: int,
             nat_tgt: int, eng_tgt: int) -> None:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed,
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[57h:{tag}] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[57h:{tag}] seed={seed} runner={rid} -> walk s{stop}")
    try:
        rpc_l = lambda m, b, t: _r(sid, m, b, t)  # noqa: E731
        predictor = _scene.build_predictor(rpc_l, rid)
        for step in range(stop):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57h:{tag}] natif epuise au pas {step}")
                return
            _apply_native(sid, rid, dry)

        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        msgs = (dry.get("action") or {}).get("messages") or []
        nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
        nat_ab = next((m for m in msgs if m.get("cls") == "ActiveAbilityMessage"), None)
        print(f"[57h:{tag}] NATIF: move={nat_move and (nat_move['to']['col'], nat_move['to']['row'])} "
              f"ability={nat_ab and (nat_ab.get('casterId'), nat_ab.get('abilityType'), nat_ab.get('targetId'))}")

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        _scene.refresh_shields(predictor, rpc_l, rid)
        wt = weights.load()
        ctx = _ai_ctx.build(rpc_l, rid, dv, mov_by_unit, uid, wt, predictor)

        for u in (dv.get("units") or []):
            if u.get("id") in (uid, nat_tgt, eng_tgt):
                print(f"[57h:{tag}]   unit {u.get('id')} {u.get('visualId')} pos={u.get('pos')} "
                      f"hp={u.get('health')} team={u.get('team')}")

        plan = ctx.plans.get(uid) or {}
        order = [(e.get("abilityId"), e.get("targetId"), e.get("rankCount"))
                 for e in (plan.get("evals") or [])]
        print(f"[57h:{tag}] evals order u{uid}: {order}")

        pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
        for tgt, side in ((nat_tgt, "NATPAIR"), (eng_tgt, "ENGPAIR")):
            ev = next((e for e in (plan.get("evals") or [])
                       if e.get("abilityId") == ab and e.get("targetId") == tgt
                       and e.get("rankCount")), None)
            if ev is None:
                print(f"[57h:{tag}] pair({ab},{tgt}) [{side}]: ABSENTE des evals")
                continue
            tiles = [(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                     if rk.get("col") is not None]
            for tile in tiles:
                cand = pb.calculate_action_utility(ctx, tile, tgt, ab)
                off = None if cand is None else (repr(cand["u_full"]), repr(cand["u"]))
                pu = _r(sid, "pairUtility", {"runnerId": rid, "unitId": uid, "targetId": tgt,
                                             "abilityType": ab, "col": tile[0], "row": tile[1]}, 60)
                print(f"[57h:{tag}]   ({ab},{tgt})@{tile} [{side}]: OFF(u_full,u)={off} | "
                      f"NATIF={pu.get('utility')!r} ok={pu.get('ok')} err={pu.get('error')}")
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[57h:{tag}] runner {rid} dispose")
        except Exception:
            pass


def main() -> int:
    sid = _resolve_session()
    for tag, (seed, stop, uid, ab, nat_tgt, eng_tgt) in CASES.items():
        run_case(sid, tag, seed, stop, uid, ab, nat_tgt, eng_tgt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
