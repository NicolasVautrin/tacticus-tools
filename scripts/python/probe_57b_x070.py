#!/usr/bin/env python
"""Probe #57b : famille x0.70 defenseur (batch 57a_gen, 4 cas nat = off x 0.700 exact).

Cas sonde : 54321 s16, u81 ab=69 -> t89, tile (2,4) [off 3132/4698 vs nat 2192/3288].
Verite terrain a capturer :
  1. identites (visualId/team/traits) attaquant + defenseur ;
  2. effets decisionView des DEUX unites (la source -30% est-elle nommee et presente ?) ;
  3. nature du coup (melee/ranged a la tuile) — gate IsMeleeAttack de Terrifying ;
  4. statModSources DEFENSE + ATTACK du defenseur (stat-mod cache ?) ;
  5. confrontation off/nat des champs a la meme tuile.
Second cas (meme walk impossible: autre seed) : 1357 s13 u91 ab=1165 -> t153 tile (1,6) — a
sonder ensuite si le premier ne suffit pas.
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
from engine_agreement_stages import _fields_from_native_event  # noqa: E402
from engine.playbook.prediction import defender_prediction_block_amount  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_57b_state.json"

SEED, STOP = "54321", 16
UID, AB, TGT, TILE = 81, 69, 89, (2, 4)


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
        print(f"[57b] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
        predictor = scene_mod.build_predictor(rpc, rid)
        wt = W.load()
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57b] walk stoppe au pas {step}")
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

        for xid in (UID, TGT):
            u = units.get(xid) or {}
            vid = u.get("visualId")
            gu = GC.unit(vid) or {}
            print(f"[57b] u{xid}: visualId={vid} team={u.get('team')} hp={u.get('hp')} "
                  f"pos=({u.get('col')},{u.get('row')}) traits={gu.get('traits')}")
            print(f"[57b]    effects={[e.get('name') or e.get('type') for e in (u.get('effects') or [])]}")

        ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, UID, wt, predictor)
        # nature du coup a la tuile candidate (adjacence hex tuile->cible)
        import hexgeo
        t_u = units.get(TGT) or {}
        t_pos = (t_u.get("col"), t_u.get("row"))
        print(f"[57b] dist(tile {TILE} -> tgt {t_pos}) = "
              f"{hexgeo.distance(TILE, t_pos) if t_pos[0] is not None else '?'}")

        sms = _r(sid, "statModSources",
                 {"runnerId": rid, "unitId": TGT, "stats": ["attack", "defense"]}, 120)
        if sms.get("ok"):
            for u in (sms.get("units") or []):
                print(f"[57b] statModSources t{u.get('entityId')}: {json.dumps(u.get('mods'))}")
        else:
            print(f"[57b] statModSources KO: {sms.get('error')}")

        off_evs = NORMAL_ATTACK_PLAYBOOK.make_damage_predictions(ctx, TILE, TGT, AB) or []
        off_main = next((e for e in off_evs if e.target == TGT), off_evs[0] if off_evs else None)
        if off_main is not None:
            print(f"[57b] OFF fields: {json.dumps(off_main.composite_fields())}")
        resp = _r(sid, "aiPlaybookPredict",
                  {"runnerId": rid, "unitId": UID, "targetId": TGT, "abilityType": AB,
                   "col": int(TILE[0]), "row": int(TILE[1])}, 60)
        if resp.get("ok"):
            blk = defender_prediction_block_amount(ctx.scene, TGT)
            for i, ev in enumerate(resp.get("events") or []):
                f = _fields_from_native_event(ev, block_amount=blk)
                print(f"[57b] NAT ev{i} t{ev.get('targetId')}: fields={json.dumps(f)}")
        else:
            print(f"[57b] aiPlaybookPredict KO: {resp.get('error')}")
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
