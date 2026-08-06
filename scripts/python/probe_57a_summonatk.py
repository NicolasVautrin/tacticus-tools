#!/usr/bin/env python
"""Probe #57a : prediction attaquant-SUMMON gonflee +22% (1357 s15, u135 ab=69 -> t162, tile (5,4)).

Chiffres batch #52 : off raw 6580/9865 vs natif 5388/8079 (ratio 1.221). Base implicite :
off 2742 (= INITIAL, auras re-eval nulles) vs natif 2245. Hypothese : le natif CONSERVE les
modifications courantes NON-aura (malus type BattleFatigue sur le summon) que notre modele
INITIAL-plus-auras exclut. Verite terrain a chercher :
  1. INITIAL(u135) et CURRENT(u135) au pas 15 (attack_cur_by_id refresh) ;
  2. decomposition per-source de la modification ATTACK (statModSources) + effets decisionView ;
  3. confrontation off/nat de la paire a la MEME tuile (make_damage_predictions vs aiPlaybookPredict).
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
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK  # noqa: E402
from engine.entities.stats import StatType, StatPart  # noqa: E402
from engine_agreement_stages import _fields_from_native_event  # noqa: E402
from engine.playbook.prediction._shared import defender_prediction_block_amount  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_57a_state.json"

SEED, STOP = "1357", 15
UID, AB, TGT, TILE = 135, 69, 162, (5, 4)


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    import gameconfig as GC
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED,
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[57a] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
        predictor = scene_mod.build_predictor(rpc, rid)
        wt = W.load()
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57a] walk stoppe au pas {step}")
                return 1
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
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        scene_mod.refresh_shields(predictor, rpc, rid)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        units = {u.get("id"): u for u in (dv.get("units") or [])}

        # -- 1. identite + stats brutes attaquant/cible --
        for xid in (UID, TGT):
            u = units.get(xid) or {}
            vid = u.get("visualId")
            print(f"[57a] u{xid}: visualId={vid} team={u.get('team')} hp={u.get('hp')} "
                  f"pos=({u.get('col')},{u.get('row')})")
            print(f"[57a]    effects={[e.get('name') or e.get('type') for e in (u.get('effects') or [])]}")

        ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, UID, wt, predictor)
        uc = ctx.scene.ctx(UID)
        ini = uc.get_stat(StatType.ATTACK, StatPart.INITIAL) if uc is not None else None
        cur_part = uc.get_stat(StatType.ATTACK, StatPart.CURRENT) if uc is not None else None
        cur_step = ctx.scene.attack_current(UID)
        print(f"[57a] ATTACK u{UID}: INITIAL={ini} CURRENT(part)={cur_part} "
              f"attack_cur_by_id(step)={cur_step}")

        # -- 2. decomposition per-source (statModSources, ground truth native) --
        sms = _r(sid, "statModSources", {"runnerId": rid, "unitId": UID, "stats": ["attack"]}, 120)
        if sms.get("ok"):
            for u in (sms.get("units") or []):
                print(f"[57a] statModSources u{u.get('entityId')}: {json.dumps(u.get('mods'))}")
        else:
            print(f"[57a] statModSources KO: {sms.get('error')}")

        # -- 3. confrontation paire off/nat a la MEME tuile --
        off_evs = NORMAL_ATTACK_PLAYBOOK.make_damage_predictions(ctx, TILE, TGT, AB) or []
        off_main = next((e for e in off_evs if e.target == TGT), off_evs[0] if off_evs else None)
        if off_main is not None:
            print(f"[57a] OFF fields: {json.dumps(off_main.composite_fields())}")
        else:
            print("[57a] OFF: aucun event")
        resp = _r(sid, "aiPlaybookPredict",
                  {"runnerId": rid, "unitId": UID, "targetId": TGT, "abilityType": AB,
                   "col": int(TILE[0]), "row": int(TILE[1])}, 60)
        if resp.get("ok"):
            blk = defender_prediction_block_amount(ctx.scene, TGT)
            for i, ev in enumerate(resp.get("events") or []):
                f = _fields_from_native_event(ev, block_amount=blk)
                print(f"[57a] NAT ev{i} t{ev.get('targetId')}: fields={json.dumps(f)}")
        else:
            print(f"[57a] aiPlaybookPredict KO: {resp.get('error')}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
        try:
            STATE.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
