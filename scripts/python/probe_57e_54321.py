#!/usr/bin/env python
"""Probe #57d : 2 miss prediction seed 1357 (batch stages_57d_gen).

Signatures (rawHealthDmg, off vs nat) :
  S18 54321 s18 u85 ab1089 GreatFrostAxe -> t93 tile (2,5) : off [4020,6032] vs nat [3576,5364]
      (x0.889 uniforme ; per-hit off [1005,1508] vs nat [894,1341], centres 1256.4 vs 1117.5,
       les 2 en +-20pct -> base differente. i2 : "Crit Damage bonus of the Ice already applied")
  S19 54321 s19 u77 ab69 -> t93 tile (3,6) : off [630,942] vs nat [1098,1644] (x1.743, kill flip)

Usage : python probe_57e_54321.py S18|S19
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
STATE = ROOT / "data" / "_57e_state.json"

CASES = {
    "S18": ("54321", 18, 85, 1089, 93, (2, 5)),
    "S19": ("54321", 19, 77, 69, 93, (3, 6)),
}


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    import gameconfig as GC
    case = (sys.argv[1] if len(sys.argv) > 1 else "S19").upper()
    seed, stop, uid, ab, tgt, tile = CASES[case]
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed,
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[57e] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
        predictor = scene_mod.build_predictor(rpc, rid)
        wt = W.load()
        for step in range(stop):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57e] walk stoppe au pas {step}")
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

        for xid in (uid, tgt):
            u = units.get(xid) or {}
            vid = u.get("visualId")
            gu = GC.unit(vid) or {}
            st = u.get("stats") or {}
            p = u.get("pos") or {}
            print(f"[57e] u{xid}: visualId={vid} team={u.get('team')} hp={u.get('hp')} "
                  f"pos=({p.get('col')},{p.get('row')})")
            print(f"[57e]    stats: attack={st.get('attack')} extraHits={st.get('extraHits')} "
                  f"crit={st.get('critChance')}/{st.get('critDamage')}")
            print(f"[57e]    traits={gu.get('traits')} abilities={[a.get('id') for a in (gu.get('abilities') or [])]}")
            print(f"[57e]    effects(dv)={[e.get('name') or e.get('type') for e in (u.get('effects') or [])]}")

        # roster complet (chasse aux auras/triggered d'allies)
        for u in (dv.get("units") or []):
            p = u.get("pos") or {}
            print(f"[57e] roster: u{u.get('id')} {u.get('visualId')} team={u.get('team')} "
                  f"hp={u.get('hp')} pos=({p.get('col')},{p.get('row')})")

        watch = {uid, tgt}
        eff = _r(sid, "effectAbilityStates", {"runnerId": rid}, 120)
        if eff.get("ok"):
            mine = [e for e in (eff.get("effects") or [])
                    if e.get("source") in watch or e.get("owner") in watch]
            for e in mine:
                print(f"[57e] effect: {json.dumps(e)}")
        else:
            print(f"[57e] effectAbilityStates KO: {eff.get('error')}")

        sms = _r(sid, "statModSources",
                 {"runnerId": rid, "unitId": uid, "stats": ["attack", "extraHits"]}, 120)
        if sms.get("ok"):
            for u in (sms.get("units") or []):
                print(f"[57e] statModSources u{u.get('entityId')}: {json.dumps(u.get('mods'))}")
        else:
            print(f"[57e] statModSources KO: {sms.get('error')}")

        ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, uid, wt, predictor)

        # decomposition NOTRE pipeline : arme choisie a la tuile, adjacence, stats scene
        from engine.services.battle_query import select_weapon_pierce, are_tiles_adjacent
        t_u2 = units.get(tgt) or {}
        tp = t_u2.get("pos") or {}
        t_pos = (tp.get("col"), tp.get("row"))
        scn = ctx.scene
        elev = getattr(scn, "elev_by_pos", None) or {}
        adj = are_tiles_adjacent(tile, t_pos) if t_pos[0] is not None else None
        print(f"[57e] tile={tile} elev={elev.get(tuple(tile))} tgt_pos={t_pos} "
              f"elev_tgt={elev.get(t_pos)} are_tiles_adjacent={adj}")
        try:
            wp = select_weapon_pierce(scn.ctx(uid), adj, None)
            print(f"[57e] select_weapon_pierce(adj={adj}) -> pierce/is_ranged/hits/profile = {wp}")
        except Exception as exc:
            print(f"[57e] select_weapon_pierce KO: {exc!r}")
        try:
            print(f"[57e] scene: attack_current(att)={scn.attack_current(uid)} "
                  f"extra_hits_current(att)={scn.extra_hits_current(uid)} "
                  f"attack_current(tgt)={scn.attack_current(tgt)} hp(tgt)={scn.hp(tgt)}")
        except Exception as exc:
            print(f"[57e] scene stats KO: {exc!r}")

        # decomposition OFF complete (meta=True) : base/pierce/armor/hits/pct-mods/effets
        from engine.playbook.prediction import make_normal_attack_predictions
        _m = make_normal_attack_predictions(ctx.scene, uid, tgt, tile, meta=True)
        if _m is not None:
            _ev, _meta = _m
            print(f"[57e] OFF META: {json.dumps(_meta)}")

        off_evs = NORMAL_ATTACK_PLAYBOOK.make_damage_predictions(ctx, tile, tgt, ab) or []
        for i, e in enumerate(off_evs):
            print(f"[57e] OFF ev{i} t{e.target}: {json.dumps(e.composite_fields())}")
        # natif : depuis la tuile candidate ET depuis la position reelle (gate mouvement ?)
        me_u = units.get(uid) or {}
        mp = me_u.get("pos") or {}
        real_pos = (mp.get("col"), mp.get("row"))
        for lbl, (pc, pr) in (("cand", tile), ("real", real_pos)):
            if pc is None:
                continue
            resp = _r(sid, "aiPlaybookPredict",
                      {"runnerId": rid, "unitId": uid, "targetId": tgt, "abilityType": ab,
                       "col": int(pc), "row": int(pr)}, 60)
            if resp.get("ok"):
                blk = defender_prediction_block_amount(ctx.scene, tgt)
                for i, ev in enumerate(resp.get("events") or []):
                    f = _fields_from_native_event(ev, block_amount=blk)
                    print(f"[57e] NAT[{lbl}] ev{i} t{ev.get('targetId')}: fields={json.dumps(f)}")
                    print(f"[57e] NAT[{lbl}] ev{i} RAW: {json.dumps(ev)}")
            else:
                print(f"[57e] aiPlaybookPredict[{lbl}] KO: {resp.get('error')}")
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
