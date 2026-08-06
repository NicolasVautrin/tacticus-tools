"""R21 -- POURQUOI les Ork Boyz invoques par Waaagh (1058) ne BOUGENT PAS cote PORT.

Rouge de reference (pre-existant) :
    tests/engine/runner/test_summon_consumers_live.py::test_waaagh_fresh_summons_act_live_and_port
    AssertionError: port : aucun Ork Boy n'a quitte l'anneau (dists=[0, 1])

DECOMPOSITION PAR ETAGE du chemin porte. Le 5e etage de `WaaaghAbility$$ExecuteBehaviour` est
`PerformAIAction(<sel>, asGroup=1, resetTurnFlags=1)` -> `ComputerActionOperation.execute_group`
-> `ai_control_execute_for_group` -> `ai_control_execute_for` -> `decide_and_apply` :
  E1  selecteur        : quelles unites `PerformAIAction` a-t-il selectionnees ?
  E2  boucle de groupe : lesquelles la boucle a-t-elle REELLEMENT jouees (`ai_results`) ?
  E3  bridge           : `build_from_state(state, boy)` -> origin / move_tiles / enemies / plans
  E4  decision         : `DefaultAiUnitTactic().calculate_next_action(ctx)` -> kind / to / ability
  E5  apply            : position AVANT/APRES de chaque Ork Boy

Usage (depuis scripts/python) :
    python probe_r21_waaagh_summon_move.py --state-file <ABSOLU> [--seed 31337] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests
from sibling_script import sibling_script

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tests", "engine", "runner"))

HOST = "http://127.0.0.1:8765"


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def make_rpc(s: int):
    def _call(method: str, args=None, timeout: float = 60):
        r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                          json={"method": method, "args": [args or {}],
                                "timeout": int(timeout) * 1000},
                          timeout=timeout + 30)
        if r.status_code >= 400:
            raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
        body = r.json()
        if body.get("error"):
            raise RuntimeError(str(body["error"])[:400])
        res = body.get("result")
        return res.get("result") if isinstance(res, dict) and "result" in res else res
    return _call


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import _summon_montage as M
    from engine.runner.abilities.orks import WaaaghAbility
    from engine.runner.components import PositionComponent, UnitComponent, UnitFlagsComponent
    from engine.ai.state_bridge import build_from_state
    from engine.ai.tactic import DefaultAiUnitTactic

    out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build", "--seed", a.seed,
                          "--board", a.board, "--state-file", a.state_file,
                          "--p-units", M.WAAAGH_CASTER,
                          "--a-units", f"{M.WAAAGH_ENEMY},{M.WAAAGH_FOIL}"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print("BUILD FAILED rc=%d" % out.returncode)
        print((out.stdout or "")[-2000:])
        print((out.stderr or "")[-2000:])
        return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("runnerId=%s board=%s seed=%s" % (rid, a.board, a.seed))
    rpc = make_rpc(sid())
    try:
        board = M.board_of(rpc, rid)
        c, tid = M.drive_until_castable(rpc, rid, M.WAAAGH_CASTER, M.WAAAGH_ENEMY, M.WAAAGH_ABILITY)
        cpos = M.upos(c)
        print("caster=%s pos=%s target=%s" % (c["id"], cpos, tid))
        d = M.cast_and_replay(rpc, rid, board, c["id"], tid, M.WAAAGH_ABILITY,
                              WaaaghAbility, M.BOY_VIS)
        res = d["res"]
        st = d["state"]

        live_d = [(ch["to"]["col"], ch["to"]["row"]) for ch in d["live_appeared"] if ch.get("to")]
        import hexgeo
        print("LIVE appeared=%d at=%s dists=%s"
              % (len(d["live_appeared"]), live_d, [hexgeo.distance(p, cpos) for p in live_d]))

        # ---- E0-live : la stat Movement NATIVE des Ork Boyz fraichement invoques ------------- #
        snap1 = rpc("combatSnapshot", {"runnerId": rid}, 60)
        ids_before = {u["id"] for u in d["dv0"]["units"]}
        for su in (snap1.get("units") or []):
            if su.get("entityId") in ids_before:
                continue
            stt = su.get("stats") or {}
            mv_keys = [k for k in stt if "ove" in k or "Move" in k]
            print("E0-live newUnit=%s statKeys=%s moveLike=%s"
                  % (su.get("entityId"), sorted(stt.keys()),
                     {k: stt[k] for k in mv_keys}))
            print("E0-live newUnit=%s statDelta=%s"
                  % (su.get("entityId"), su.get("statDelta")))

        # ---- E1 : selecteur PerformAIAction ------------------------------------------------- #
        print("E1 spawned=%s ai_units=%s" % (res.get("spawned"), res.get("ai_units")))

        # ---- E2 : ce que la boucle de groupe a joue ------------------------------------------ #
        for r in (res.get("ai_results") or []):
            print("E2 ai_result=%s" % json.dumps(r, default=str)[:400])

        # ---- E5 : positions PORT ------------------------------------------------------------ #
        for gid in res.get("spawned") or []:
            pc = st.get_entity(gid).get_component(PositionComponent)
            print("E5 port boy=%s pos=%s dist=%s"
                  % (gid, (pc.col, pc.row) if pc else None,
                     hexgeo.distance((pc.col, pc.row), cpos) if pc else None))

        # ---- E3/E4 : re-derive le bridge + la decision sur un etat FRAIS --------------------- #
        # Rejoue les 4 premiers etages puis inspecte CHAQUE Ork Boy AVANT `PerformAIAction`.
        st2 = d["fresh"]()
        from engine.dsl.effects import ExecutionContext
        from engine.runner.abilities.behaviours.context import entities_from_state
        from engine.runner.abilities.orks import (waaagh_spawn_tree, waaagh_buff_tree,
                                                  waaagh_move_range, waaagh_charge_tile,
                                                  waaagh_move_tree, waaagh_attack_tree)
        import gameconfig as GC
        consts = (GC.ability("Waaagh") or {}).get("constants") or {}
        n = int(consts.get("nrOfSummons") or 0)
        em = int(consts.get("extraMovement") or 0)
        ectx = ExecutionContext(state=st2, rng=st2.rng)
        waaagh_spawn_tree(n).execute(entities_from_state(st2, c["id"], tid), ectx)
        waaagh_buff_tree().execute(entities_from_state(st2, c["id"], tid), ectx)
        mr = waaagh_move_range(st2, c["id"], em)
        dest = waaagh_charge_tile(st2, c["id"], tid, mr)
        waaagh_move_tree(dest).execute(entities_from_state(st2, c["id"], tid), ectx)
        waaagh_attack_tree().execute(entities_from_state(st2, c["id"], tid), ectx)
        boys = [p["unit"] for nm, p in ectx.emitted if nm == "SpawnUnit"]
        print("E3 pre-AI boys=%s" % boys)
        for gid in boys:
            e = st2.get_entity(gid)
            pc = e.get_component(PositionComponent)
            uc = e.get_component(UnitComponent)
            fl = e.get_component(UnitFlagsComponent)
            print("E3 boy=%s vid=%s pos=%s alive=%s ai_ctrl=%s flags=%s"
                  % (gid, uc.visual_id if uc else None, (pc.col, pc.row) if pc else None,
                     uc.alive if uc else None, getattr(uc, "ai_controlled", None) if uc else None,
                     sorted(fl.flags) if fl is not None else None))
            try:
                ctx = build_from_state(st2, gid)
            except Exception as ex:
                print("E3 boy=%s BRIDGE ERROR %r" % (gid, ex))
                continue
            from engine.ai.state_bridge import _move_range
            from engine.runner.components import StatsComponent
            from engine.entities.stats import StatType
            _sc = e.get_component(StatsComponent)
            _mvstat = int(_sc.ctx.get_stat(int(StatType.MOVEMENT))) if _sc else None
            _rng = _move_range(_sc.ctx if _sc else None, uc.visual_id if uc else "")
            _far = max((hexgeo.distance((t["col"], t["row"]), ctx.origin)
                        for t in (ctx.move_tiles or [])), default=0)
            print("E3 boy=%s statMOVEMENT=%s move_range=%s farthest_move_tile=%s"
                  % (gid, _mvstat, _rng, _far))
            print("E3 boy=%s origin=%s move_tiles=%d enemies=%d abilities=%s"
                  % (gid, ctx.origin, len(ctx.move_tiles or []), len(ctx.enemies or []),
                     [x.get("id") for x in ((ctx.me or {}).get("abilities") or [])]))
            print("E3 boy=%s move_tiles=%s"
                  % (gid, [(t["col"], t["row"]) for t in (ctx.move_tiles or [])][:20]))
            plan = (ctx.plans or {}).get(gid) or {}
            print("E3 boy=%s plan evals=%d rank>0=%d"
                  % (gid, len(plan.get("evals") or []),
                     len([e2 for e2 in (plan.get("evals") or []) if e2.get("rankCount")])))
            act = DefaultAiUnitTactic().calculate_next_action(ctx)
            print("E4 boy=%s action=%s" % (gid, json.dumps(act, default=str)[:300]))
        return 0
    finally:
        if not a.keep:
            try:
                subprocess.run([sys.executable, sibling_script("rl_duel.py"), "dispose",
                                "--state-file", a.state_file], capture_output=True, text=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
