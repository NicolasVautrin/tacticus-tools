#!/usr/bin/env python
"""Probe #57g : tie exact 12345 s15 u89 — MurderousSwing (1137) t83 (natif) vs t81 (offline).

Le dump stages (data/stages_57e_gen.json) donne cf.nat == cf.eng == 167.86 (les DEUX = NOTRE
scoreur, arrondi). Question discriminante AVANT de mirrorer un ordre d'enumeration :
  A. le scorer NATIF (pairUtility = IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions) donne-t-il
     VRAIMENT la meme utilite aux deux paires (tie reel -> probleme d'ORDRE au argmax) ?
  B. ou score-t-il t83 > t81 (terme d'utilite manquant offline, le "tie" est un artefact) ?

Sortie :
  1. ordre d'enumeration des evals natifs (attackPlans) de u89 : position de (1137,83) vs (1137,81) ;
  2. sweep OFFLINE pleine precision (repr) des deux paires sur toutes leurs tuiles ranked ;
  3. sweep NATIF pairUtility des deux paires sur les memes tuiles ;
  4. action native s15 (dry-run non applique) : tuile de move + (ability, target).

Usage: python probe_57g_tie.py
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
STATE = ROOT / "data" / "_57g_state.json"
SEED = "12345"
STOP = 15          # etat de decision du step 15 (0-based, comme les records stages)
UID = 89
AB = 1137          # MurderousSwing
TGT_NAT, TGT_ENG = 83, 81


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


def main() -> int:
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED,
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[57g] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[57g] runner={rid} seed={SEED} -> walk s{STOP}")
    try:
        rpc_l = lambda m, b, t: _r(sid, m, b, t)  # noqa: E731
        predictor = _scene.build_predictor(rpc_l, rid)
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57g] natif epuise au pas {step}")
                return 3
            _apply_native(sid, rid, dry)

        # --- s15 : dry-run SANS apply (etat de decision intact) ---
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        msgs = (dry.get("action") or {}).get("messages") or []
        nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
        nat_ab = next((m for m in msgs if m.get("cls") == "ActiveAbilityMessage"), None)
        print(f"[57g] s{STOP} NATIF: move={nat_move and (nat_move['to']['col'], nat_move['to']['row'])} "
              f"ability={nat_ab and (nat_ab.get('casterId'), nat_ab.get('abilityType'), nat_ab.get('targetId'))}")
        uid = (nat_ab or {}).get("casterId") or (nat_move or {}).get("unitId")
        if uid != UID:
            print(f"[57g] ATTENTION uid natif s{STOP} = {uid} != attendu {UID}")

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        _scene.refresh_shields(predictor, rpc_l, rid)
        wt = weights.load()
        ctx = _ai_ctx.build(rpc_l, rid, dv, mov_by_unit, UID, wt, predictor)

        # 1. ordre d'enumeration des evals (attackPlans natifs) pour u89
        plan = ctx.plans.get(UID) or {}
        order = [(e.get("abilityId"), e.get("targetId"), e.get("rankCount"))
                 for e in (plan.get("evals") or [])]
        print(f"[57g] evals order u{UID} (ab,tgt,rankCount): {order}")

        # 2+3. sweep OFFLINE pleine precision + NATIF pairUtility, pour les 2 paires
        pb = NORMAL_ATTACK_PLAYBOOK if AB in ctx.normal_ids else get_playbook_or_default(AB)
        for tgt in (TGT_NAT, TGT_ENG):
            ev = next((e for e in (plan.get("evals") or [])
                       if e.get("abilityId") == AB and e.get("targetId") == tgt
                       and e.get("rankCount")), None)
            if ev is None:
                print(f"[57g] pair({AB},{tgt}): ABSENTE des evals")
                continue
            tiles = [(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                     if rk.get("col") is not None]
            print(f"[57g] pair({AB},{tgt}) tuiles ranked: {tiles}")
            for tile in tiles:
                cand = pb.calculate_action_utility(ctx, tile, tgt, AB)
                off = None if cand is None else (repr(cand["u_full"]), repr(cand["u"]))
                pu = _r(sid, "pairUtility", {"runnerId": rid, "unitId": UID, "targetId": tgt,
                                             "abilityType": AB, "col": tile[0], "row": tile[1]}, 60)
                print(f"[57g]   ({AB},{tgt})@{tile}: OFF u_full={off} | "
                      f"NATIF util={pu.get('utility')!r} ok={pu.get('ok')} err={pu.get('error')}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[57g] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
