#!/usr/bin/env python
"""Probe `#381-r5` -- QUELLES tuiles le pool de teleport natif exclut, et pourquoi.

`ATeleportPathfinder$$FindTilesReachableByTeleport` enchaine six `RemoveAll`. Trois sont
alimentables offline (occupation, walkable, `IsValidTeleportTile`) ; trois ne le sont pas
(`IsTemporary`, un filtre power-up et un booleen `+0x2e` d'un composant de tuile, tous deux gates
par une propriete virtuelle dont le corps est dedupliqué). Ce probe DIT lesquelles des tuiles que
le port garde en trop sont exclues par le natif, et imprime leurs proprietes pour trancher.

ASCII only. Usage (depuis scripts/python) :
    python probe_381r5_teleport_pool.py --board C2_26 --seed 38104
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


def _rpc(sid, method, body, timeout=90):
    r = R._rpc(sid, method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C2_26")
    ap.add_argument("--seed", default="38104")
    ap.add_argument("--range", type=int, default=2)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()

    state_file = Path(a.state_file) if a.state_file else \
        Path.home() / "AppData/Local/Temp" / ("probe-381r5-%s.json" % a.board)
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
        from engine.ai.state_bridge import _occupants
        from engine.entities.pathfinding.board import Board
        from engine.runner.components import PositionComponent
        from engine.runner.snapshot import load_state
        from engine.services.movement_query import has_special_movement

        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        state = load_state(dv, ob, snap, board=board)
        nat = _rpc(sid, "aiMovableTiles",
                   {"runnerId": rid, "side": "all", "overrideRange": a.range}, 120) or {}

        occ = _occupants(state)
        pos_by_uid = {}
        for u in (dv.get("units") or []):
            pp = u.get("pos") or {}
            pos_by_uid[int(u["id"])] = (pp.get("col"), pp.get("row"), u.get("visualId"),
                                        u.get("team"), u.get("alive"))
        print("[probe] board=%s seed=%s rid=%s tiles=%d" % (a.board, a.seed, rid, len(board.by_id)))
        print("[probe] unites:")
        for uid, (c, r, vis, team, alive) in sorted(pos_by_uid.items()):
            print("  u%-5s %-24s team=%s alive=%s pos=(%s,%s) special=%s"
                  % (uid, vis, team, alive, c, r, has_special_movement(state, uid)))

        # tuiles LIBRES et WALKABLE = ce que le port propose comme pool de teleport
        free = {t for t in board.by_id if board.walkable(t) and occ.get(t) is None}
        for u in (nat.get("units") or []):
            uid = int(u.get("unitId"))
            if not has_special_movement(state, uid):
                continue
            want = {board.id_at(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                    if t.get("col") is not None}
            want.discard(None)
            e = state.get_entity(uid)
            pc = e.get_component(PositionComponent) if e is not None else None
            print("\n[probe] u%s %s pos=(%s,%s) natif=%d libres_walkable=%d"
                  % (uid, pos_by_uid.get(uid, ("?",))[2], pc.col, pc.row, len(want), len(free)))
            extra = sorted(free - want)
            miss = sorted(want - free)
            print("  natif MAIS pas libre/walkable (%d): %s"
                  % (len(miss), [board.coord(t) for t in miss][:20]))
            print("  TOUTES les tuiles libres+walkable (IN = dans le pool natif) :")
            import hexgeo
            enemies = [(p[0], p[1]) for uid2, p in pos_by_uid.items()
                       if p[4] and p[3] != pos_by_uid[uid][3]]
            allies = [(p[0], p[1]) for uid2, p in pos_by_uid.items()
                      if p[4] and p[3] == pos_by_uid[uid][3]]
            for t in sorted(free):
                c, r = board.coord(t)
                td = board.by_id[t]
                de = min((hexgeo.distance((c, r), q) for q in enemies), default=99)
                da = min((hexgeo.distance((c, r), q) for q in allies), default=99)
                print("    %-3s (%2d,%2d) elev=%s def=%-8s nbrs=%d dEnemy=%d dAlly=%d keys=%s"
                      % ("IN" if t in want else "OUT", c, r, td.get("elevation"),
                         td.get("tileDefId"), len(board.neighbours(t)), de, da,
                         "" if t in want else sorted(k for k in td)))
            break
        # profil du board : combien de tuiles par (row) pour reperer un motif de bord
        rows = {}
        for t in board.by_id:
            c, r = board.coord(t)
            rows.setdefault(r, []).append(c)
        print("\n[probe] rows: %s" % {k: len(v) for k, v in sorted(rows.items())})
        cols = {}
        for t in board.by_id:
            c, r = board.coord(t)
            cols.setdefault(c, []).append(r)
        print("[probe] cols: %s" % {k: len(v) for k, v in sorted(cols.items())})
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        state_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
