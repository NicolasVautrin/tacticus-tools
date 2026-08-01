#!/usr/bin/env python
"""Probe `#403-r1` -- l'ARETE du FlyPathfinder : `board.walkable` est-il le bon predicat ?

Le port monte l'arete FLY sur `board.walkable` (= `BattleQuery.IsWalkableTile` =
`IdunBattle.Entities.TileExtensions$$IsWalkable`). Le natif, lui, lit DEUX flags du
`TileComponent` (`IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsValidPathNode` :
`tc+0x40 == 0 && tc+0x41 == 0`), et `IsWalkable` teste `movementComponent+0x10 == 0` -- un
troisieme champ que l'arete du vol NE lit PAS.

Ce probe recense le board LIVE par `(tileDefId, walkable, isWall)` et imprime les tuiles ou les
deux predicats divergeraient, puis re-joue le pool d'une volante avec l'arete `not isWall`.

ASCII only. Usage (depuis scripts/python) :
    python probe_403r1_fly_edge_predicate.py --board C2_26 --seed 38104 --turns 6 --range 4
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                              # noqa: E402


def _rpc(sid, method, body, timeout=120):
    r = R._rpc(sid, method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C2_26")
    ap.add_argument("--seed", default="38104")
    ap.add_argument("--range", type=int, default=4)
    ap.add_argument("--turns", type=int, default=6)
    a = ap.parse_args()

    state_file = Path.home() / "AppData/Local/Temp" / ("probe-403r1-%s.json" % a.board)
    state_file.unlink(missing_ok=True)
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", a.seed,
                        "--board", a.board, "--state-file", str(state_file), "--no-ai"],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("build KO: %s" % ((p.stderr or p.stdout or "")[-400:]))
        return 2
    rid = json.loads(state_file.read_text())["runnerId"]
    sid = R._resolve_session()
    try:
        for _ in range(a.turns):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)

        from engine.ai.state_bridge import _occupants
        from engine.entities.pathfinding import fly_pathfinder as FP
        from engine.entities.pathfinding.board import Board
        from engine.entities.pathfinding.fly_pathfinder import is_like_flying
        from engine.entities.traits.unit_trait import unit_trait_names
        from engine.runner.components import OwnerComponent, PositionComponent
        from engine.runner.snapshot import load_state
        from engine.services.movement_query import get_movable_tiles_for, has_special_movement

        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        print("[403r1] board=%s rid=%s tiles=%d" % (a.board, rid, len(bg["tiles"])))
        cen = Counter((t.get("tileDefId"), bool(t.get("walkable")), bool(t.get("isWall")))
                      for t in bg["tiles"])
        for k in sorted(cen, key=lambda x: str(x)):
            print("[403r1]   terrain=%-12s walkable=%-5s isWall=%-5s n=%d" % (k[0], k[1], k[2],
                                                                              cen[k]))
        diverge = [t for t in bg["tiles"] if bool(t.get("walkable")) == bool(t.get("isWall"))]
        print("[403r1] tuiles ou walkable != (not isWall) : %d -> %s"
              % (len(diverge), sorted((t["col"], t["row"], t.get("tileDefId"))
                                      for t in diverge)[:24]))

        dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        state = load_state(dv, ob, snap, board=board)
        nat = _rpc(sid, "aiMovableTiles",
                   {"runnerId": rid, "side": "all", "overrideRange": a.range}, 120) or {}
        occ = _occupants(state)

        saved = FP.is_valid_path_node

        def _edge_not_wall(b, from_id, to_id, occupants, moving_team):
            t = b.by_id.get(to_id)
            return t is not None and not bool(t.get("isWall"))

        for u in (nat.get("units") or []):
            uid = int(u.get("unitId"))
            want = {board.id_at(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                    if t.get("col") is not None}
            want.discard(None)
            if not want:
                continue
            e = state.get_entity(uid)
            pc = e.get_component(PositionComponent) if e is not None else None
            oc = e.get_component(OwnerComponent) if e is not None else None
            if pc is None or oc is None:
                continue
            vis = next((x.get("visualId") for x in (dv.get("units") or [])
                        if int(x.get("id")) == uid), None)
            if not is_like_flying(unit_trait_names(vis)) or has_special_movement(state, uid):
                continue
            start = board.id_at(pc.col, pc.row)
            got = get_movable_tiles_for(board, state, uid, start, a.range, occ, oc.team)
            try:
                FP.is_valid_path_node = _edge_not_wall
                alt = get_movable_tiles_for(board, state, uid, start, a.range, occ, oc.team)
            finally:
                FP.is_valid_path_node = saved
            print("[403r1] u%-5s %-22s natif=%-3d port(walkable)=%-3d port(not isWall)=%-3d "
                  "| walkable manque=%s | notWall extra=%s manque=%s"
                  % (uid, vis, len(want), len(got), len(alt),
                     sorted(board.coord(t) for t in (want - got)),
                     sorted(board.coord(t) for t in (alt - want)),
                     sorted(board.coord(t) for t in (want - alt))))
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        state_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
