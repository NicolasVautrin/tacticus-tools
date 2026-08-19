"""R5 -- decomposition PAR ETAGE de la divergence de tuile mesuree sur le Skitarii Vanguard.

Le summon ne peut pas etre interroge avec son action disponible (il joue TOUT SEUL au turn-start).
On decompose donc les deux etages amont sur un porteur EQUIVALENT et INTERROGEABLE : `admecMarshall`
(meme move=3, meme jeu d'armes melee Physical + Toxic r2), place a la MEME tuile d'origine, sur le
MEME board, face aux MEMES ennemis.

  etage 1 -- `aiMovableTiles` (natif `IdunBattle.Core.Services.BattleQuery$$GetMovableTilesFor`)
             vs `engine.ai.state_bridge._move_tiles` ;
  etage 2 -- `aiPredict(col,row)` (preview natif depuis une tuile donnee) vs
             `engine.playbook.prediction.make_normal_attack_predictions` -- en particulier le
             BONUS D'ELEVATION (le port rend x1.5 sur les tuiles elev=2 du board MC1_67).

Sortie ASCII only. Usage : python probe_r5c_tile_stage.py [--seed 777] [--board MC1_67]
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

MARSHALL = "admecMarshall"
ENEMY = "necroWarden"
POS_ORIGIN = (3, 7)     # tuile d'origine du Vanguard dans le scenario mesure
POS_FOE_A = (6, 8)
POS_FOE_B = (6, 7)


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


def _build(seed: str, board: str, state_file: Path) -> int:
    cmd = [sys.executable, str(PYDIR / "rl_duel.py"), "build", "--seed", seed,
           "--state-file", str(state_file), "--board", board, "--roster", "1",
           "--p-units", f"{MARSHALL},admecRuststalker", "--a-units", f"{ENEMY},{ENEMY}"]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PYDIR),
                         encoding="utf-8", errors="replace")
    if not state_file.exists():
        print((out.stderr or out.stdout or "")[-2500:])
        raise SystemExit("build KO")
    return int(json.loads(state_file.read_text())["runnerId"])


def _dec(sid, rid):
    return _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dec):
    return {int(u["id"]): u for u in (dec.get("units") or [])}


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _move(sid, rid, uid, pos):
    r = _rpc(sid, "applyAction",
             {"runnerId": rid, "action": {"kind": "move", "unitId": int(uid),
                                          "to": {"col": int(pos[0]), "row": int(pos[1])}}}, 90)
    return bool(r.get("ok"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--origin", default=None, help="col,row de la tuile d'origine du porteur")
    a = ap.parse_args()
    global POS_ORIGIN
    if a.origin:
        POS_ORIGIN = tuple(int(x) for x in a.origin.split(","))
    sys.path.insert(0, str(PYDIR))
    import hexgeo

    sid = _sid()
    print("amorce ok=%s" % (_rpc(sid, "autoBootExtraire", {}, timeout=240) or {}).get("ok"))
    sf = ROOT / "logs" / "probe_r5c_state.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(a.seed, a.board, sf)
    print("runner=%s" % rid)
    try:
        us = _units(_dec(sid, rid))
        mar = next(u for u in us.values() if u.get("visualId") == MARSHALL)
        mine = mar.get("team")
        foes = [u for u in us.values() if u.get("team") != mine and u.get("alive")]
        mid, aid, bid = int(mar["id"]), int(foes[0]["id"]), int(foes[1]["id"])
        print("moves=%s" % [_move(sid, rid, mid, POS_ORIGIN), _move(sid, rid, aid, POS_FOE_A),
                            _move(sid, rid, bid, POS_FOE_B)])
        for _ in range(2):                    # reset des flags de tour -> le Marshall a son move
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        dec = _dec(sid, rid)
        us = _units(dec)
        print("currentPlayer=%s ; marshall pos=%s hasAction=%s"
              % (dec.get("currentPlayer"), _pos(us[mid]), us[mid].get("hasAction")))

        tm = _rpc(sid, "tileMeta", {"runnerId": rid}, 90)
        elev = {(t.get("col"), t.get("row")): t.get("elevation") for t in (tm.get("tiles") or [])}
        print("elev origin=%s foeA=%s foeB=%s (6,5)=%s (6,6)=%s (4,7)=%s"
              % (elev.get(POS_ORIGIN), elev.get(POS_FOE_A), elev.get(POS_FOE_B),
                 elev.get((6, 5)), elev.get((6, 6)), elev.get((4, 7))))

        # --- ETAGE 1 : tuiles de deplacement --------------------------------------------
        mv = _rpc(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        nat = None
        for e in (mv.get("units") or []):
            if int(e.get("unitId", -1)) == mid:
                nat = sorted((t["col"], t["row"]) for t in (e.get("tiles") or []))
        from engine.entities.pathfinding.board import Board
        from engine.runner.snapshot import load_state
        from engine.runner.prng import IntBasedMersenneTwister
        from engine.ai.state_bridge import _move_tiles, build_from_state
        from engine.runner.components import UnitComponent, OwnerComponent, PositionComponent
        from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
        from engine.playbook.base import tile_utility
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        s0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        state = load_state(dec, ob, snap, board=board)
        rng = IntBasedMersenneTwister(); rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
        state.rng = rng
        ent = state.get_entity(mid)
        uc = ent.get_component(UnitComponent); oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        port = sorted((t["col"], t["row"]) for t in
                      _move_tiles(state, mid, uc.visual_id, oc.team, (pc.col, pc.row)))
        print("NATIF movable n=%s : %s" % (len(nat or []), nat))
        print("PORT  movable n=%s : %s" % (len(port), port))
        print("DIFF port-only=%s natif-only=%s"
              % (sorted(set(port) - set(nat or [])), sorted(set(nat or []) - set(port))))

        # etage 1bis : d'ou vient la divergence ? (portee / occupants / elevation / BFS)
        from engine.ai.state_bridge import _move_range, _occupants
        from engine.entities.pathfinding.walk_pathfinder import get_reachable_levels
        depth = _move_range(ent.get_component(__import__(
            "engine.runner.components", fromlist=["StatsComponent"]).StatsComponent).ctx, uc.visual_id)
        occ = _occupants(state)
        otile = board.id_at(*POS_ORIGIN)
        lev = get_reachable_levels(board, otile, occ, oc.team, max_depth=None)
        print("depth(stat Movement)=%s occupants=%s"
              % (depth, sorted((board.coord(t), v) for t, v in occ.items())))
        for t in sorted(set(port) - set(nat or [])) + [(6, 6), (4, 7)]:
            tid = board.id_at(*t)
            print("  tile %s: bfs_level=%s elev_boardGraph=%s elev_tileMeta=%s walkable=%s"
                  % (t, lev.get(tid), board.elevation(tid), elev.get(t), board.walkable(tid)))
        # chemins possibles : voisins et leur elevation
        for t in sorted(set(port) - set(nat or [])):
            tid = board.id_at(*t)
            print("  voisins de %s : %s" % (t, [(board.coord(n), board.elevation(n),
                                                 lev.get(n)) for n in board.neighbours(tid)]))
        bad = [(t.get("col"), t.get("row")) for t in (bg.get("tiles") or [])
               if t.get("elevation") != elev.get((t.get("col"), t.get("row")))]
        print("tuiles ou boardGraph.elevation != tileMeta.elevation : %s" % bad)
        meta = {(t.get("col"), t.get("row")): t for t in (tm.get("tiles") or [])}
        natset = set(nat or [])
        print("GRILLE (col,row): elev/lvl/nat  [terrain, effets]")
        rows = sorted({r for (_c, r) in meta}, reverse=True)
        cols = sorted({c for (c, _r) in meta})
        for r in rows:
            line = []
            for c in cols:
                tid = board.id_at(c, r)
                if tid is None:
                    line.append("  ---  "); continue
                line.append("%s/%s/%s" % (board.elevation(tid),
                                          lev.get(tid, "-"), "N" if (c, r) in natset else "."))
            print("  r%-2s %s" % (r, "  ".join("%-7s" % x for x in line)))
        print("META des tuiles port-only + temoin :")
        bgt = {(t.get("col"), t.get("row")): t for t in (bg.get("tiles") or [])}
        for t in sorted(set(port) - natset) + [(4, 6), (1, 6), (5, 6), (5, 7), (2, 7), (6, 6)]:
            print("   %s -> meta=%s" % (t, meta.get(t)))
            print("       bg=%s" % {k: v for k, v in (bgt.get(t) or {}).items() if k != "neighbours"})
        # HYPOTHESE #131 : la tuile portant `BlockEnteringUnits` (EffectType 0) est un CUL-DE-SAC de
        # la flood-fill (`BasePathfinder$$NodesInNextLevel` gate l'expansion sur
        # `WalkPathfinder$$IsValidContinuePathTile`), mais reste un STOP legal.
        state_fx = load_state(dec, ob, snap, board=board, tiles=tm)
        blocked = set()
        for tid in board.by_id:
            for ef in (state_fx.effects.by_unit.get(int(tid), []) if state_fx.effects else []):
                if not ef.consumed and int(getattr(ef, "effect_type", -1) or 0) == 0:
                    blocked.add(tid)
        print("tuiles BlockEnteringUnits (state.effects, tiles=tileMeta) : %s"
              % sorted(board.coord(t) for t in blocked))

        def _levels_gated(max_depth):
            lv = {otile: 0}
            frontier = [otile]
            d = 0
            while frontier and d < max_depth:
                d += 1
                nxt = []
                for cur in frontier:
                    if cur != otile and cur in blocked:      # IsValidContinuePathTile == false
                        continue
                    for n in board.neighbours(cur):
                        if n in lv:
                            continue
                        from engine.entities.pathfinding.walk_pathfinder import is_valid_path_node
                        if is_valid_path_node(board, cur, n, occ, oc.team):
                            lv[n] = d; nxt.append(n)
                frontier = nxt
            return lv

        # NIVEAUX natifs : aiMovableTiles a portee forcee 1/2/3 -> level natif par tuile
        for rng_ in (1, 2, 3):
            m2 = _rpc(sid, "aiMovableTiles", {"runnerId": rid, "overrideRange": rng_}, 90)
            s2 = None
            for e in (m2.get("units") or []):
                if int(e.get("unitId", -1)) == mid:
                    s2 = sorted((t["col"], t["row"]) for t in (e.get("tiles") or []))
            pl = sorted(board.coord(t) for t, l in lev.items()
                        if l is not None and l <= rng_ and t != otile
                        and occ.get(t) is None)
            print("  range=%s NATIF n=%s | PORT n=%s | port-only=%s natif-only=%s"
                  % (rng_, len(s2 or []), len(pl), sorted(set(pl) - set(s2 or [])),
                     sorted(set(s2 or []) - set(pl))))
            lg = _levels_gated(rng_)
            pg = sorted(board.coord(t) for t in lg if t != otile and occ.get(t) is None)
            print("     GATE #131 : n=%s | port-only=%s natif-only=%s"
                  % (len(pg), sorted(set(pg) - set(s2 or [])), sorted(set(s2 or []) - set(pg))))
        # ADJACENCE : boardGraph NATIF vs synthese evenq du port, tuile par tuile
        nat_adj = {t["id"]: sorted(t.get("neighbours") or []) for t in (bg.get("tiles") or [])}
        id2cr = {t["id"]: (t["col"], t["row"]) for t in (bg.get("tiles") or [])}
        print("ADJACENCE natif vs evenq :")
        mism = []
        for tid, ns in nat_adj.items():
            pn = sorted(board.neighbours(tid))
            if pn != ns:
                mism.append((id2cr[tid], len(ns), sorted(id2cr[n] for n in ns),
                             sorted(id2cr[n] for n in pn if n in id2cr)))
        print("  tuiles divergentes: %s/%s" % (len(mism), len(nat_adj)))
        for m in mism[:20]:
            print("   %s natif(n=%s)=%s | evenq=%s" % (m[0], m[1], m[2], m[3]))

        # --- ETAGE 2 : degat predit par tuile (bonus d'elevation) ------------------------
        ctx = build_from_state(state, mid)
        probe_tiles = [POS_ORIGIN, (4, 7), (4, 8), (5, 7), (6, 6), (6, 5), (5, 6), (4, 6)]
        print("tuile | elev | NATIF aiPredict | PORT pred | PORT tile_utility")
        for t in probe_tiles:
            nat_p = _rpc(sid, "aiPredict", {"runnerId": rid, "unitId": mid, "targetId": aid,
                                            "col": int(t[0]), "row": int(t[1]), "fresh": True}, 60)
            cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, t, aid, 17)
            p = (cand or {}).get("pred") or {}
            print("  %s | elev=%s | NATIF=%s" % (t, elev.get(t), nat_p))
            print("     PORT dmin=%s dmax=%s tile_util=%.3f hex(t,foeA)=%s"
                  % (p.get("healthDmgMin"), p.get("healthDmgMax"), tile_utility(ctx, t),
                     hexgeo.distance(t, POS_FOE_A)))
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            print("disposed runner %s" % rid)
        except Exception as ex:
            print("dispose failed: %r" % ex)


if __name__ == "__main__":
    main()
