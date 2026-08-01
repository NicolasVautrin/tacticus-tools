#!/usr/bin/env python
"""Probe `#381-r5` -- VERDICT CHIFFRE sur la premisse de `#381-r2`.

`#381-r2` (« `FlyPathfinder$$AddNeighbours` n'itere pas le bon voisinage ») s'appuie sur un
datapoint `bloodIntercessor` : natif 47 / port 27 sur `MC1_67`. Ce datapoint est pris au TOUT
DEBUT de la bataille -- donc SOUS `TeleportStrike_TeleportingIn`, l'effet qui detourne l'unite
vers un `ATeleportPathfinder` (`#381-r5`). Ce probe tranche en DEUX temps :

  T0   au debut de bataille : qui porte un effet de mouvement special, qui est `IsLikeFlying`,
       et l'ecart port/natif de chacun ;
  T+n  apres N `endturn` (l'effet expire), les MEMES unites re-mesurees.

Si l'ecart d'une unite disparait avec l'effet, il etait imputable a `#381-r5`, pas au
`FlyPathfinder`. Si un ecart PERSISTE sur une unite VOLANTE sans effet special, la premisse de
`#381-r2` tient, et le probe le chiffre.

ASCII only. Usage (depuis scripts/python) :
    python probe_381r5_verdict_r2.py --board MC1_67 --seed 38104 --turns 6
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                              # noqa: E402


def _rpc(sid, method, body, timeout=120):
    r = R._rpc(sid, method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _measure(sid, rid, probe_range):
    """Rend `{uid: row}` ou row = (visualId, flying, special, n_natif, n_port, extra, missing)."""
    from engine.ai.state_bridge import _occupants
    from engine.entities.pathfinding.board import Board
    from engine.entities.pathfinding.fly_pathfinder import is_like_flying
    from engine.entities.traits.unit_trait import unit_trait_names
    from engine.runner.components import OwnerComponent, PositionComponent
    from engine.runner.snapshot import load_state
    from engine.services.movement_query import get_movable_tiles_for, has_special_movement

    bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, snap, board=board)
    nat = _rpc(sid, "aiMovableTiles",
               {"runnerId": rid, "side": "all", "overrideRange": probe_range}, 120) or {}
    occ = _occupants(state)
    out = {}
    for u in (nat.get("units") or []):
        uid = int(u.get("unitId"))
        want = {board.id_at(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                if t.get("col") is not None}
        want.discard(None)
        e = state.get_entity(uid)
        pc = e.get_component(PositionComponent) if e is not None else None
        oc = e.get_component(OwnerComponent) if e is not None else None
        if pc is None or oc is None:
            continue
        start = board.id_at(pc.col, pc.row)
        if start is None:
            continue
        vis = next((x.get("visualId") for x in (dv.get("units") or [])
                    if int(x.get("id")) == uid), None)
        got = get_movable_tiles_for(board, state, uid, start, probe_range, occ, oc.team)
        out[uid] = (vis, bool(is_like_flying(unit_trait_names(vis))),
                    bool(has_special_movement(state, uid)), len(want), len(got),
                    len(got - want), len(want - got))
    return out


def _print(tag, rows):
    print("[%s] %-6s %-22s %-6s %-8s %-6s %-6s %-6s %s"
          % ("r2", "uid", "visualId", "flying", "special", "natif", "port", "extra", "missing"))
    for uid, (vis, fly, sp, n_nat, n_got, extra, miss) in sorted(rows.items()):
        print("[%s] %-6s %-22s %-6s %-8s %-6d %-6d %-6d %d"
              % (tag, uid, vis, fly, sp, n_nat, n_got, extra, miss))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="38104")
    ap.add_argument("--range", type=int, default=2)
    ap.add_argument("--turns", type=int, default=6)
    a = ap.parse_args()

    state_file = Path.home() / "AppData/Local/Temp" / ("probe-381r5-r2-%s.json" % a.board)
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
        print("[r2] board=%s seed=%s rid=%s range=%d" % (a.board, a.seed, rid, a.range))
        t0 = _measure(sid, rid, a.range)
        print("\n[r2] === T0 (debut de bataille) ===")
        _print("T0", t0)
        for i in range(a.turns):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        tn = _measure(sid, rid, a.range)
        print("\n[r2] === T+%d endturn ===" % a.turns)
        _print("Tn", tn)
        print("\n[r2] === VERDICT ===")
        for uid in sorted(set(t0) & set(tn)):
            v0, f0, s0, n0, g0, e0, m0 = t0[uid]
            v1, f1, s1, n1, g1, e1, m1 = tn[uid]
            if not s0 and not s1 and not f0:
                continue
            print("[r2] u%-5s %-22s special %s->%s flying=%s | ecart T0 (+%d/-%d) -> Tn (+%d/-%d)"
                  % (uid, v0, s0, s1, f0, e0, m0, e1, m1))
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        state_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
