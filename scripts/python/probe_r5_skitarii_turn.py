"""R5 -- probe de DECOMPOSITION du rouge `test_skitarii_played_by_generic_ai_pass`.

Rejoue EXACTEMENT le scenario du test (meme build, meme seed, meme drive de positions) mais
sans assertion : imprime, etage par etage, ce que chaque couche voit.

  1. geometrie : position ennemi / spawn Vanguard / tuile choisie, dist hex vs dist BFS ;
  2. DECISION : le plan `_plans_for_unit` (tuiles-caster candidates par (ability,cible)),
     l'action rendue par `DefaultAiUnitTactic.calculate_next_action` ;
  3. APPLY : le dict complet de `AttackDamageOperation.execute` (hits/total/bornes/armure).

Sortie ASCII only (console cp1252). Usage :
    python probe_r5_skitarii_turn.py [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

HOST = os.environ.get("TACTICUS_HOST", "http://127.0.0.1:8765")
PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

SUMMON_VIS = "admecSmnVanguard"
TAN_VIS = "admecMarshall"
SUMMON_ABILITY = "ControlEdict"
ENEMY_VIS = "necroWarden"
BUILD = ["--roster", "1", "--p-units", f"{TAN_VIS},admecRuststalker",
         "--a-units", f"{ENEMY_VIS},{ENEMY_VIS}"]


def _http(path: str, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HOST + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _sid() -> int:
    return int((_http("/api/admin/status").get("session") or {}).get("id"))


def _rpc(sid: int, method: str, body: dict, timeout=120):
    r = _http(f"/api/scripts/{sid}/rpc",
              {"method": method, "args": [body], "timeout": int(timeout * 1000)}, timeout=timeout + 5)
    return r.get("result", r)


def _build(seed: str, state_file: Path):
    cmd = [sys.executable, str(PYDIR / "rl_duel.py"), "build", "--seed", seed,
           "--state-file", str(state_file), "--board", "MC1_67"] + BUILD
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PYDIR))
    if out.returncode != 0:
        print("BUILD FAILED rc=%s" % out.returncode)
        print(out.stdout[-3000:])
        print(out.stderr[-3000:])
        raise SystemExit(1)
    return int(json.loads(state_file.read_text())["runnerId"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()

    sys.path.insert(0, str(PYDIR))
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import (StatsComponent, OwnerComponent, UnitComponent,
                                          HealthComponent, PositionComponent)
    from engine.runner.operations.spawn import _occupied_tiles, _spawn_config_grot
    from engine.services.battle_query import are_tiles_adjacent

    sid = _sid()
    _rpc(sid, "autoBootExtraire", {}, timeout=240)
    sf = ROOT / "logs" / "probe_r5_state.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(a.seed, sf)
    print("runner=%s" % rid)
    try:
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        dec = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        s0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        tiles = _rpc(sid, "tileMeta", {"runnerId": rid}, 90)   # #131 : effets de TUILE (BlockEnteringUnits)
        state = load_state(dec, ob, snap, board=board, tiles=tiles)
        rng = IntBasedMersenneTwister(); rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
        state.rng = rng

        tan = None
        for eid, e in state.entities.items():
            uc = e.get_component(UnitComponent)
            if uc is not None and uc.visual_id == TAN_VIS:
                sc = e.get_component(StatsComponent); oc = e.get_component(OwnerComponent)
                tan = (eid, getattr(sc.ctx, "active_ability_level", None),
                       int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100),
                       oc.team, oc.player)
                break
        tan_id, lvl, mult, team, player = tan
        print("tan=%s lvl=%s mult=%s team=%s player=%s" % tan)

        enemies = []
        for eid, e in state.entities.items():
            oc = e.get_component(OwnerComponent); uc = e.get_component(UnitComponent)
            hc = e.get_component(HealthComponent); pc = e.get_component(PositionComponent)
            if oc is None or uc is None or hc is None or pc is None or not uc.alive:
                continue
            if oc.team == team or hc.hp is None:
                continue
            enemies.append((eid, uc.visual_id, (pc.col, pc.row), hc.hp))
        print("ENEMIES:")
        for x in enemies:
            print("  id=%s vis=%s pos=%s hp=%s" % x)
        enemy_id, _evis, epos, _ehp = enemies[0]
        epc = state.get_entity(enemy_id).get_component(PositionComponent)

        from collections import deque
        etile = board.id_at(epc.col, epc.row)
        seen = {etile: 0}; q = deque([etile])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in seen:
                    seen[n] = seen[x] + 1; q.append(n)
        bfs = seen

        occ = _occupied_tiles(state)
        spot = next((t for t in board.by_id
                     if bfs.get(t) == 3 and t not in occ and board.walkable(t)), None)
        sc_, sr_ = board.coord(spot)
        print("spawn tile=%s pos=(%s,%s) bfs=%s hex=%s"
              % (spot, sc_, sr_, bfs.get(spot), hexgeo.distance((sc_, sr_), (epc.col, epc.row))))
        suid = _spawn_config_grot(state, SUMMON_VIS, spot, SUMMON_ABILITY, lvl, mult, team, player)
        print("summon uid=%s" % suid)

        # ---- 2. DECISION -----------------------------------------------------------------
        from engine.ai.state_bridge import build_from_state, _attack_abilities, _max_attack_range
        from engine.ai.tactic import DefaultAiUnitTactic
        print("attack_abilities(%s) = %s" % (SUMMON_VIS, _attack_abilities(SUMMON_VIS)))
        print("max_attack_range = %s" % _max_attack_range(SUMMON_VIS))
        ctx = build_from_state(state, suid)
        plan = (getattr(ctx, "plans", None) or {}).get(suid) or {}
        for ev in (plan.get("evals") or []):
            tiles = [(t["col"], t["row"]) for t in ev["ranked"]]
            print("  eval ability=%s target=%s n=%s tiles(hex,bfs)=%s"
                  % (ev["abilityId"], ev["targetId"], ev["rankCount"],
                     [(t, hexgeo.distance(t, (epc.col, epc.row)),
                       bfs.get(board.id_at(t[0], t[1]))) for t in tiles]))
        action = DefaultAiUnitTactic().calculate_next_action(ctx)
        print("ACTION = %s" % action)
        to = action.get("to")
        if to:
            print("  to=%s hex=%s bfs=%s" % (tuple(to), hexgeo.distance(tuple(to), (epc.col, epc.row)),
                                             bfs.get(board.id_at(to[0], to[1]))))

        # ---- 3. APPLY --------------------------------------------------------------------
        from engine.runner.operations.summon_ai import apply_action
        hp_before = {eid: state.get_entity(eid).get_component(HealthComponent).hp
                     for eid, *_ in enemies}
        res = apply_action(state, suid, action)
        hp_after = {eid: state.get_entity(eid).get_component(HealthComponent).hp
                    for eid, *_ in enemies}
        sp = state.get_entity(suid).get_component(PositionComponent)
        print("FINAL pos=(%s,%s) hex_to_enemy=%s bfs=%s adjacent=%s"
              % (sp.col, sp.row, hexgeo.distance((sp.col, sp.row), (epc.col, epc.row)),
                 bfs.get(board.id_at(sp.col, sp.row)),
                 are_tiles_adjacent((sp.col, sp.row), (epc.col, epc.row), board)))
        print("HP before=%s after=%s" % (hp_before, hp_after))
        atk = res.get("attack") or {}
        for k in ("hits", "total", "base", "pierce", "armor", "clean_min", "clean_max",
                  "ranged", "profile", "did_block", "did_evade", "per_hit", "target"):
            print("  atk.%s = %s" % (k, atk.get(k)))
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            print("disposed runner %s" % rid)
        except Exception as ex:
            print("dispose failed: %r" % ex)


if __name__ == "__main__":
    main()
