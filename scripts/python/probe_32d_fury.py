#!/usr/bin/env python
"""Probe #32d : matrice de reconciliation de la prediction Fury (31337 s5, tuile (3,5)).

Cibles EXACTES (L3 natif, spec re-expert) :
  composite(Fury->91) = 9.660285501740873   (bloodDeathCompany hp9035)
  composite(Fury->95) = 10.866318154148757  (thousAhriman hp8032)
  feuille (3,5)       = 20.52660365588963

Variantes testees : hits {1,2} x canal {range [min,max] spread0, predefined avg spread0,
predefined avg spread20}.
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
STATE = ROOT / "logs" / "runners" / "_32ct_state.json"
STOP = 5
UID = 81
TILE = (3, 5)
TARGETS = {91: 9.660285501740873, 95: 10.866318154148757}


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _predict(scene, uid, tgt, tile, hits, channel):
    import gameconfig as GC
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.stats import ARMOR_STAT_TYPES
    from engine.entities.traits import target_hit_multiplier, TraitFactory
    from engine.entities.effects import calculate_attacker_modifiers_for_prediction
    from engine.services.damage_prediction import get_attack_prediction
    from engine.playbook.prediction import (_add_positional_and_defender_mods,
                                            _apply_ally_attack_dmg_bonus,
                                            _target_damage_limits, _PROFILE_INDEX)
    lvl = (scene.ablvl_by_id or {}).get(uid)
    mult = int((scene.mult_by_id or {}).get(uid) or 100)
    dmin = ability_var("FuryOfTheAncients", "minDmg", lvl, multiplier_pct=mult)
    dmax = ability_var("FuryOfTheAncients", "maxDmg", lvl, multiplier_pct=mult)
    prof = GC.damage_profile("Psychic") or {}
    actx = scene.ctx(uid)
    pierce = max(0, min(100, int(prof.get("PiercingRatio") or 0)
                        + actx.extra_pierce + actx.extra_pierce_melee))
    _hm = tile != scene.pos(uid)
    _tctx = scene.ctx(tgt)
    _tar = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
            if _tctx is not None and _tctx.stats is not None else None)
    mods = calculate_attacker_modifiers_for_prediction(
        scene.effects(uid), is_ranged=False, has_moved=_hm, is_normal_attack=False,
        target_armor_reduced=_tar,
        att_ctx={"att_pos": tile, "tile_effects_by_pos": scene.tile_effects_by_pos})
    _add_positional_and_defender_mods(mods, scene, uid, tgt, True, tile, scene.pos(tgt),
                                      damage_profile="Psychic", is_normal_attack=False)
    _apply_ally_attack_dmg_bonus(mods, scene, uid, tile, True, _tar)
    hit_mult = target_hit_multiplier(TraitFactory.create_many(
        (GC.unit(scene.vis_by_id.get(tgt)) or {}).get("traits")))
    kw = dict(target_current_health=scene.hp(tgt) or 0, hits=hits,
              profile_type=_PROFILE_INDEX.get("Psychic", 0), pierce_pct=pierce,
              armor=scene.armor(tgt), mods=mods, hit_mult=hit_mult,
              target_shield=scene.shield(tgt), target_limits=_target_damage_limits(scene, tgt))
    if channel == "range":
        return dict(kw, initial_damage=int(dmin), extra_max=int(dmax) - int(dmin), spread_pct=0), \
            get_attack_prediction(initial_damage=int(dmin), extra_max=int(dmax) - int(dmin),
                                  spread_pct=0, **kw)
    avg = (int(dmin) + int(dmax)) // 2
    sp = 0 if channel == "avg0" else 20
    return dict(kw, initial_damage=avg, spread_pct=sp), \
        get_attack_prediction(initial_damage=avg, extra_max=0, spread_pct=sp, **kw)


def main() -> int:
    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337",
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[32d] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
        predictor = scene_mod.build_predictor(rpc, rid)
        wt = W.load()
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
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

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        if predictor is not None:
            scene_mod.refresh_shields(predictor, rpc, rid)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        from engine.ai import context as _ai_ctx
        ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, UID, wt, predictor, debug=False)
        scene = ctx.scene
        from engine.playbook.probable_damage_event import (ProbableDamageEvent,
                                                           calculate_utility_from_damage_event)
        lvl = (scene.ablvl_by_id or {}).get(UID)
        mult = (scene.mult_by_id or {}).get(UID)
        print(f"[32d] u{UID} passive lvl={lvl} mult={mult}")
        for tgt, want in TARGETS.items():
            print(f"[32d] tgt={tgt} hp={scene.hp(tgt)} armor={scene.armor(tgt)} "
                  f"shield={scene.shield(tgt)} hpmax={ctx.hpmax_by_id.get(tgt)} want={want}")
            for hits in (1, 2):
                for ch in ("range", "avg0", "avg20"):
                    try:
                        kw, pred = _predict(scene, UID, tgt, TILE, hits, ch)
                    except Exception as e:
                        print(f"[32d]   hits={hits} ch={ch}: ERR {e}")
                        continue
                    ev = ProbableDamageEvent(target=tgt, prediction=pred)
                    u = calculate_utility_from_damage_event(ev, wt, ctx.hpmax_by_id.get(tgt))
                    d = u - want
                    tagexact = " <== EXACT" if abs(d) < 1e-9 else (" (close)" if abs(d) < 0.02 else "")
                    print(f"[32d]   hits={hits} ch={ch}: u={u!r} delta={d:+.9f}{tagexact} "
                          f"(base={kw.get('initial_damage')}+x{kw.get('extra_max', 0)})")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
