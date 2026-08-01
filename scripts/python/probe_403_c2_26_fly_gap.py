#!/usr/bin/env python
"""Probe `#403` -- LOCALISER la tuile de l'ecart `#381-r2` residuel (`C2_26`, T+6, natif 13/port 12).

`probe_381r5_verdict_r2.py` a etabli le CHIFFRE ; ce probe rend l'IDENTITE. Il rejoue le meme
montage (`C2_26`, seed 38104, `overrideRange` 2, 6 `endturn`), puis pour chaque unite en ecart
imprime la ou les tuiles (col,row) et TOUT leur substrat : walkable, elevation, tileDefId,
occupant, distance hex au depart, appartenance au `visited` du port, verdict `can_continue`.

Il decompose ensuite l'ecart PAR ETAGE, en re-jouant le port avec UN etage neutralise a la fois
(le gate d'expansion `IsValidContinuePathTile`, la vue d'adjacence) -- pas pour fitter, mais pour
dire QUEL etage porte la difference. La LOI se lit au decompile, pas ici.

ASCII only. Usage (depuis scripts/python) :
    python probe_403_c2_26_fly_gap.py --board C2_26 --seed 38104 --turns 6
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


def _port_with_walk_gate_on_fly(board, state, uid, start, rng, occ, team):
    """CONTRE-EPREUVE : le port de l'arbre d'AVANT `#403`, ou la branche FLY recevait le gate
    d'expansion de la MARCHE (`WalkPathfinder$$IsValidContinuePathTile`). La mutation porte sur
    `fly_pathfinder.get_movable_positions` (que `find_reachable_tiles` re-importe a chaque appel),
    donc elle traverse le foyer complet -- ce n'est pas un calcul parallele."""
    import engine.entities.pathfinding.fly_pathfinder as FP
    from engine.entities.pathfinding.tile_blocking import make_can_continue
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions as _walk
    from engine.runner.components import StatsComponent
    from engine.services.movement_query import get_movable_tiles_for
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    traits = (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None)
              else None) or []
    cc = make_can_continue(getattr(state, "effects", None), traits, board=board)
    saved = FP.get_movable_positions

    def _muted(b, s0, d, o, t):
        return _walk(b, s0, d, o, t, edge=FP.is_valid_path_node, can_continue=cc)
    try:
        FP.get_movable_positions = _muted
        return get_movable_tiles_for(board, state, uid, start, rng, occ, team)
    finally:
        FP.get_movable_positions = saved


def _variants(board, state, uid, start, rng, occ, team, traits):
    """Le port, re-joue avec UN etage neutralise a la fois. Rend `{nom: set(tile_id)}`."""
    from engine.entities.pathfinding.board import Board
    from engine.entities.pathfinding.pathfinders import movable_positions_for_unit
    from engine.entities.pathfinding.tile_blocking import make_can_continue
    from engine.services.movement_query import (synapse_tiles_for, titanhammer_target_tiles_for,
                                                unit_has_effect_fn)
    eff = getattr(state, "effects", None)
    he = unit_has_effect_fn(state, uid)
    tt = titanhammer_target_tiles_for(state, board, team)
    st = synapse_tiles_for(state, board, team)
    cc = make_can_continue(eff, traits, board=board)

    def run(b, can_continue, depth=None):
        s0 = b.id_at(*board.coord(start))
        _v, s = movable_positions_for_unit(
            b, int(s0), int(rng if depth is None else depth), occ, team, traits=traits,
            has_effect=he, can_continue=can_continue, teleport_target_tiles=tt, synapse_tiles=st)
        return s

    tiles = list(board.by_id.values())
    b_nat = Board(tiles, adjacency="native_sym")
    b_raw = Board(tiles, adjacency="native")
    out = {
        "port courant": run(board, cc),
        "gate WALK sur le FLY": _port_with_walk_gate_on_fly(board, state, uid, start, rng,
                                                            occ, team),
        "adjacence native_sym": run(b_nat, cc),
        "adjacence native": run(b_raw, cc),
        "portee +1": run(board, cc, depth=int(rng) + 1),
    }
    return out


def _tile_row(board, state, occ, tid, start):
    import hexgeo
    from engine.entities.pathfinding.tile_blocking import (tile_blocks_entering,
                                                           terrain_blocks_entering)
    c, r = board.coord(tid)
    sc, sr = board.coord(start)
    eff = getattr(state, "effects", None)
    ets = []
    if eff is not None:
        for e in eff.by_unit.get(int(tid), []):
            ets.append("%s%s" % (e.effect_type, "" if not e.consumed else "(c)"))
    return ("(%d,%d) id=%s walk=%s elev=%s terrain=%-10s occ=%s dist=%d "
            "blockDyn=%s blockTerrain=%s eff=%s"
            % (c, r, tid, board.walkable(tid), board.elevation(tid),
               board.tile_def_id(tid), occ.get(tid), hexgeo.distance((c, r), (sc, sr)),
               tile_blocks_entering(eff, tid, None), terrain_blocks_entering(board, tid, None),
               ",".join(ets) or "-"))


def _run_board(a, board_id) -> int:
    state_file = Path.home() / "AppData/Local/Temp" / ("probe-403-%s.json" % board_id)
    state_file.unlink(missing_ok=True)
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", a.seed,
                        "--board", board_id, "--state-file", str(state_file), "--no-ai"],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[403] build KO %s: %s" % (board_id, (p.stderr or p.stdout or "")[-400:]))
        return 2
    rid = json.loads(state_file.read_text())["runnerId"]
    sid = R._resolve_session()
    try:
        print("\n[403] board=%s seed=%s rid=%s range=%d turns=%d"
              % (board_id, a.seed, rid, a.range, a.turns))
        for _ in range(a.turns):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)

        from engine.ai.state_bridge import _occupants
        from engine.entities.pathfinding.board import Board
        from engine.entities.pathfinding.fly_pathfinder import is_like_flying
        from engine.entities.traits.unit_trait import unit_trait_names
        from engine.runner.components import OwnerComponent, PositionComponent, StatsComponent
        from engine.runner.snapshot import load_state
        from engine.services.movement_query import get_movable_tiles_for, has_special_movement

        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        state = load_state(dv, ob, snap, board=board)
        nat = _rpc(sid, "aiMovableTiles",
                   {"runnerId": rid, "side": "all", "overrideRange": a.range}, 120) or {}
        occ = _occupants(state)

        for u in (nat.get("units") or []):
            uid = int(u.get("unitId"))
            want = {board.id_at(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                    if t.get("col") is not None}
            want.discard(None)
            e = state.get_entity(uid)
            pc = e.get_component(PositionComponent) if e is not None else None
            oc = e.get_component(OwnerComponent) if e is not None else None
            sc = e.get_component(StatsComponent) if e is not None else None
            if pc is None or oc is None:
                continue
            start = board.id_at(pc.col, pc.row)
            if start is None:
                continue
            vis = next((x.get("visualId") for x in (dv.get("units") or [])
                        if int(x.get("id")) == uid), None)
            traits = (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None)
                      else None) or []
            got = get_movable_tiles_for(board, state, uid, start, a.range, occ, oc.team)
            extra, miss = got - want, want - got
            fly = is_like_flying(unit_trait_names(vis))
            mute = _port_with_walk_gate_on_fly(board, state, uid, start, a.range, occ, oc.team)
            if not want:
                # `#381` (garde FLAG de `FindAnyOrAllMoveableTiles`) : un set natif VIDE n'est pas
                # un desaccord de pathfinding. Residu NOMME, hors perimetre de `#403`.
                tag = "N/A"
            elif not extra and not miss:
                tag = "OK "
            else:
                tag = "GAP"
            print("[403] %s u%-5s %-22s fly=%-5s special=%-5s natif=%d port=%d extra=%d "
                  "missing=%d gateWALKsurFLY=%d%s"
                  % (tag, uid, vis, fly, has_special_movement(state, uid),
                     len(want), len(got), len(extra), len(miss), len(mute),
                     "  <-- DISCRIMINANT" if (fly and mute != got) else ""))
            if tag != "GAP":
                continue
            print("[403]   depart %s" % _tile_row(board, state, occ, start, start))
            for tid in sorted(miss):
                print("[403]   MANQUE  %s" % _tile_row(board, state, occ, tid, start))
            for tid in sorted(extra):
                print("[403]   EN TROP %s" % _tile_row(board, state, occ, tid, start))
            print("[403]   natif = %s" % sorted(board.coord(t) for t in want))
            print("[403]   port  = %s" % sorted(board.coord(t) for t in got))
            for name, s in _variants(board, state, uid, start, a.range, occ, oc.team,
                                     traits).items():
                print("[403]   variante %-22s n=%-3d extra=%-3d missing=%d %s"
                      % (name, len(s), len(s - want), len(want - s),
                         "MATCH" if s == want else ""))
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        state_file.unlink(missing_ok=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C2_26",
                    help="un board, ou plusieurs separes par des virgules")
    ap.add_argument("--seed", default="38104")
    ap.add_argument("--range", type=int, default=2)
    ap.add_argument("--turns", type=int, default=6)
    a = ap.parse_args()
    rc = 0
    for b in [x.strip() for x in a.board.split(",") if x.strip()]:
        rc = _run_board(a, b) or rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
