#!/usr/bin/env python
"""Probe #57j : 54321 s8 u81 HammerOfWrath (1153) — natif t91, offline t93 (nc-pair).

Decompose NOTRE utilite NC pour chaque (position, cible) legale : Sigma events (primaire+
secondaires), bonus Overwatch (+100), displacement (+5 x CanAddUnit voisins cible). Ordres
imprimes : reach_nc (positions, ordre natif movable) + evals (cibles) + tuiles rankees par paire.

Objectif : discriminer (a) u(93) > u(91) strict offline -> terme divergent (borne INF CanAddUnit ?
Overwatch ? adjacents secondaires ?) vs (b) tie inter-positions -> ordre de sweep.

Usage: python probe_57j_hammer.py
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
from engine.playbook import noncomparable as playbooks  # noqa: E402
from engine.playbook.noncomparable.hammer_of_wrath import HammerOfWrathPlaybook  # noqa: E402
from engine.playbook.prediction import make_hammer_wrath_events  # noqa: E402
from engine.playbook.probable_damage_event import calculate_utility_from_damage_event  # noqa: E402
from engine.playbook.noncomparable._base import _traits  # noqa: E402
from engine import battle_query as bq  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_57j_state.json"
SEED, STOP, UID, AB = "54321", 8, 81, 1153
TGTS = (91, 93)


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def main() -> int:
    sid = _resolve_session()
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", SEED,
                    "--state-file", str(STATE), "--board", "MC1_67"],
                   cwd=str(PYDIR), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[57j] build KO", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[57j] runner={rid} -> walk s{STOP}")
    try:
        rpc_l = lambda m, b, t: _r(sid, m, b, t)  # noqa: E731
        predictor = _scene.build_predictor(rpc_l, rid)
        for step in range(STOP):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57j] natif epuise au pas {step}")
                return 3
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

        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        msgs = (dry.get("action") or {}).get("messages") or []
        nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
        nat_ab = next((m for m in msgs if m.get("cls") == "ActiveAbilityMessage"), None)
        print(f"[57j] NATIF: move={nat_move and (nat_move['to']['col'], nat_move['to']['row'])} "
              f"ability={nat_ab and (nat_ab.get('casterId'), nat_ab.get('abilityType'), nat_ab.get('targetId'))}")

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        _scene.refresh_shields(predictor, rpc_l, rid)
        wt = weights.load()
        ctx = _ai_ctx.build(rpc_l, rid, dv, mov_by_unit, UID, wt, predictor)
        for u in (dv.get("units") or []):
            if u.get("id") in (UID,) + TGTS:
                print(f"[57j]   unit {u.get('id')} {u.get('visualId')} pos={u.get('pos')}")

        nc = playbooks.NCContext(
            uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
            enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos, walkable_by_pos=ctx.walkable_by_pos,
            plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
            elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets,
            wt=ctx.wt, is_temporary_by_pos=ctx.is_temporary_by_pos,
            effects_by_pos=ctx.effects_by_pos, obs_units=ctx.obs_units,
            tile_id_by_pos=ctx.tile_id_by_pos, active_levels=ctx.active_ability_levels,
            units=ctx.units, cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene, debug=False)

        print(f"[57j] reach_nc (ordre positions): {nc.reach_nc}")
        plan = nc.plan
        print(f"[57j] evals order: "
              f"{[(e.get('abilityId'), e.get('targetId'), e.get('rankCount')) for e in (plan.get('evals') or [])]}")

        pb = HammerOfWrathPlaybook()
        print(f"[57j] should_evaluate={pb.should_evaluate(nc)}")
        for ev in (plan.get("evals") or []):
            if ev.get("abilityId") != AB or not ev.get("rankCount"):
                continue
            tgt = ev.get("targetId")
            tiles = [(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                     if rk.get("col") is not None]
            print(f"[57j] pair({AB},{tgt}) tuiles rankees: {tiles}")
            tu = next((x for x in (nc.units or []) if x.get("id") == tgt), None)
            tpos = ((tu or {}).get("pos") or {})
            vis = next((x.get("visualId") for x in (nc.obs_units or [])
                        if x.get("squadId") == tgt), None)
            ow = "Overwatch" in _traits(vis)
            disp = HammerOfWrathPlaybook._displacement_bonus(tgt, nc)
            # Diagnostic secondaires : TOUTES les unites hex-adjacentes a la cible (team + isDead),
            # pour voir laquelle le natif exclut (2 events natifs a t93 vs nos 3).
            import hexgeo  # noqa: PLC0415
            sc = nc.scene
            tp = sc.pos(tgt)
            dead_by_id = {x.get("squadId"): x.get("isDead") for x in (nc.obs_units or [])}
            adjs = [(u, sc.pos(u), sc.team(u), dead_by_id.get(u))
                    for u in sc.pos_by_id
                    if u != tgt and sc.pos(u) is not None and tp is not None
                    and hexgeo.distance(sc.pos(u), tp) == 1]
            print(f"[57j]   adj(all) de {tgt}@{tp} (id,pos,team,isDead): {adjs} "
                  f"caster_team={sc.team(UID)}")
            for P in nc.reach_nc:
                if P not in set(tiles):
                    continue
                events = make_hammer_wrath_events(nc.scene, UID, tgt, P)
                eu = sum(calculate_utility_from_damage_event(x, nc.wt, nc.scene.hpmax(x.target))
                         for x in (events or []))
                total = pb.evaluate_non_comparable(P, tgt, nc)
                print(f"[57j]   ({AB},{tgt})@{P}: total={total!r} events(n={len(events or [])})"
                      f"={eu:.4f} overwatch={ow} disp={disp:.0f} tgt_pos=({tpos.get('col')},{tpos.get('row')})")
                for x in (events or []):
                    cf = x.composite_fields()
                    u1 = calculate_utility_from_damage_event(x, nc.wt, nc.scene.hpmax(x.target))
                    print(f"[57j]     ev tgt={x.target} u={u1:+.4f} hp={cf['hpBefore']}"
                          f"/{sc.hpmax(x.target)} shield={cf['shieldBefore']} "
                          f"dmg=[{cf['healthDmgMin']},{cf['healthDmgMax']}] "
                          f"raw=[{cf['rawHealthDmgMin']},{cf['rawHealthDmgMax']}] "
                          f"hits={cf['appliedHits']} kill={cf['kill']} killSure={cf['killSure']}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[57j] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
