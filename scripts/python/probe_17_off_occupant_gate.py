#!/usr/bin/env python
"""#17-off -- le pathfinder de `MinDist(16)` TRAVERSE-t-il les unites ? (montage CRAFTE)

`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` appelle
`IPathfinders.GetPath(1, ...)` : le pathfinder `PathfinderType = 1`. La RE dit que ce n'est PAS le
`WalkPathfinder` de l'enumeration des tuiles (`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidPathNode`
teste `UnitIsBlockedByEnemyUnit`) mais `IdunBattle.Entities.Pathfinding.IgnoreTerrainPathfinder`, dont
l'`IsValidPathNode` n'a meme PAS de parametre `unit` -> **aucun test d'occupant**.

Ce probe le rend DISCRIMINANT : il RAPPROCHE l'unite qui decide du paquet ennemi (pilotage
`applyAction move` des deux camps), de sorte que des unites se retrouvent SUR les chemins courts.
Puis, pour chaque tuile candidate, il compare :

  * `d_natif`     -- RPC `pathDistToEnemies` (invoque le pathfinder NATIF) ;
  * `d_ignore`    -- le port livre (`ignore_terrain_pathfinder`, traverse les unites) ;
  * `d_walk`      -- la MEME recherche avec le predicat du WalkPathfinder (un ennemi bloque).

Un montage n'est CONCLUANT que si `d_ignore != d_walk` sur au moins une tuile : sinon le gate
d'occupant n'est pas exerce et le vert ne prouve rien.

Usage (depuis scripts/python, session Frida warmee) :
  python probe_17_off_occupant_gate.py --state-file <ABSOLU>.json [--seed 777] [--board C4_09]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                              # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402
from engine.ai.state_bridge import _occupants, _is_untargetable           # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.pathfinding.ignore_terrain_pathfinder import (        # noqa: E402
    get_path_node_counts, weight_cost)
from engine.entities.pathfinding.walk_pathfinder import is_valid_path_node # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

PYDIR = Path(__file__).resolve().parent


def _walk_path_node_counts(board, target_id, occupants, moving_team) -> dict:
    """CONTRE-VARIANTE (pas le port livre) : meme A* de `BasePathfinder$$FindPath`, mais avec le
    predicat d'arete du `WalkPathfinder` -- un occupant ENNEMI bloque. Sert UNIQUEMENT a prouver que
    le montage exerce le gate d'occupant."""
    import heapq
    if board.by_id.get(target_id) is None:
        return {}
    best = {target_id: (0, 1)}
    heap = [(0, 1, target_id)]
    while heap:
        cost, nodes, cur = heapq.heappop(heap)
        if (cost, nodes) > best.get(cur, (cost, nodes)):
            continue
        for n in board.neighbours(cur):
            if not is_valid_path_node(board, cur, n, occupants, moving_team):
                continue
            cand = (cost + weight_cost(n, occupants), nodes + 1)
            if n not in best or cand < best[n]:
                best[n] = cand
                heapq.heappush(heap, (cand[0], cand[1], n))
    return {t: n for t, (_c, n) in best.items()}


def _flat_path_node_counts(board, target_id, occupants) -> dict:
    """CONTRE-VARIANTE #2 (pas le port livre) : meme A*, mais SANS la porte d'elevation
    (`|delta elevation| <= 1`). Sert a departager `IgnoreTerrainPathfinder` (qui teste l'elevation)
    d'un pathfinder qui l'ignorerait -- les deux ont le MEME `WeightCost` (`10 + IsFilled`) et la
    meme absence de test d'occupant, donc seul ce gate les distingue."""
    import heapq
    if board.by_id.get(target_id) is None:
        return {}
    best = {target_id: (0, 1)}
    heap = [(0, 1, target_id)]
    while heap:
        cost, nodes, cur = heapq.heappop(heap)
        if (cost, nodes) > best.get(cur, (cost, nodes)):
            continue
        for n in board.neighbours(cur):
            t = board.by_id.get(n)
            if t is None or not t["walkable"]:
                continue
            cand = (cost + weight_cost(n, occupants), nodes + 1)
            if n not in best or cand < best[n]:
                best[n] = cand
                heapq.heappush(heap, (cand[0], cand[1], n))
    return {t: n for t, (_c, n) in best.items()}


def _closest(board, counts_by_enemy, otile):
    """`FindClosestEnemy` : premier ennemi d'ou l'origine est la plus proche (`<` STRICT)."""
    best = None
    for eid, counts in counts_by_enemy.items():
        d = counts.get(otile)
        if d is None or d <= 0:
            continue
        if best is None or d < best[1]:
            best = (eid, d)
    return best


def main(argv: list) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="C4_09")
    ap.add_argument("--state-file", required=True)
    args, extra = ap.parse_known_args(argv)
    sid = _resolve_session()

    state_file = Path(args.state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed), "--board", args.board,
         "--state-file", str(state_file), "--no-ai", *extra],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[probe17off] build KO: %s" % ((proc.stderr or proc.stdout or "")[-400:]))
        return 2
    rid = json.loads(state_file.read_text(encoding="utf-8")).get("runnerId")
    print("[probe17off] session=%s runner=%s seed=%s board=%s" % (sid, rid, args.seed, args.board))

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return (r.get("result") or {}) if isinstance(r, dict) else {}

    try:
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        bg = rpc("boardGraph", {"runnerId": rid})
        board = Board(bg["tiles"], adjacency="native_sym")
        units = dv.get("units") or []
        mine = [u for u in units if u.get("ctrl") and u.get("alive") and u.get("pos")]
        foes = [u for u in units if not u.get("ctrl") and u.get("alive") and u.get("pos")]
        if not (mine and foes):
            print("[probe17off] montage vide")
            return 3

        # --- DRIVE : AMENER LES ENNEMIS sur mon unite (jamais l'inverse -- bouger `me` consommerait
        #     son activation et viderait son movable set, donc l'oracle `pathDistToEnemies`). On
        #     pilote le camp adverse (`side="enemy"`), ce qui pose des unites SUR les chemins courts
        #     -- sans quoi le gate d'occupant n'est jamais exerce.
        anchor = (foes[0]["pos"]["col"], foes[0]["pos"]["row"])
        me = min(mine, key=lambda u: hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), anchor))
        my_pos = (me["pos"]["col"], me["pos"]["row"])
        for f in foes:
            mv = rpc("aiMovableTiles", {"runnerId": rid, "side": "enemy"}) or {}
            row = next((r for r in (mv.get("units") or []) if r.get("unitId") == f["id"]), None)
            tiles = [(t["col"], t["row"]) for t in ((row or {}).get("tiles") or [])]
            if not tiles:
                continue
            to = min(tiles, key=lambda t: hexgeo.distance(t, my_pos))
            rpc("applyAction", {"runnerId": rid,
                                "action": {"kind": "move", "unitId": f["id"],
                                           "to": {"col": to[0], "row": to[1]}}}, 60)
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})

        obs = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        tm = rpc("tileMeta", {"runnerId": rid}, 60)
        state = load_state(dv, obs, snap, board=board, tiles=tm)
        occ = _occupants(state)
        me_u = next(u for u in (dv.get("units") or []) if u["id"] == me["id"])
        origin = (me_u["pos"]["col"], me_u["pos"]["row"])
        otile = board.id_at(*origin)
        my_team = me_u.get("team")

        pd = rpc("pathDistToEnemies", {"runnerId": rid, "unitId": me["id"]})
        if not pd.get("ok"):
            print("[probe17off] pathDistToEnemies KO: %s" % str(pd)[:200])
            return 4
        nat_pd = {(t["col"], t["row"]): t["pathDist"] for t in (pd.get("tiles") or [])}
        kept = pd.get("enemies") or []
        print("[probe17off] origine=%s team=%s ennemis retenus=%s"
              % (origin, my_team, [(e["id"], e["col"], e["row"]) for e in kept]))
        print("[probe17off] occupants du board: %d tuiles" % len(occ))

        tgt = [(e["pos"]["col"], e["pos"]["row"]) for e in (dv.get("units") or [])
               if not e.get("ctrl") and e.get("alive") and e.get("pos")
               and not _is_untargetable(state, e.get("id"))]
        ig_by_e, wk_by_e, fl_by_e = {}, {}, {}
        for i, (c, r) in enumerate(tgt):
            et = board.id_at(c, r)
            if et is None:
                continue
            ig_by_e[i] = get_path_node_counts(board, et, occ)
            wk_by_e[i] = _walk_path_node_counts(board, et, occ, my_team)
            fl_by_e[i] = _flat_path_node_counts(board, et, occ)
        ci, cw = _closest(board, ig_by_e, otile), _closest(board, wk_by_e, otile)
        cf = _closest(board, fl_by_e, otile)
        ig = ig_by_e.get(ci[0], {}) if ci else {}
        wk = wk_by_e.get(cw[0], {}) if cw else {}
        fl = fl_by_e.get(cf[0], {}) if cf else {}

        rows, diff_gate, diff_elev, bad = [], 0, 0, 0
        for t, dn in sorted(nat_pd.items()):
            if dn is None or dn < 0:
                continue
            tid = board.id_at(t[0], t[1])
            d_ig, d_wk, d_fl = ig.get(tid), wk.get(tid), fl.get(tid)
            if d_ig != d_wk:
                diff_gate += 1
            if d_ig != d_fl:
                diff_elev += 1
            if d_ig != dn:
                bad += 1
            rows.append((t, dn, d_ig, d_wk, d_fl))
        print("  %-9s %-9s %-11s %-11s %-11s" % ("tile", "d_natif", "d_ignore", "d_walk", "d_flat"))
        for (t, dn, d_ig, d_wk, d_fl) in rows:
            flag = "" if d_ig == dn else "   <-- PORT DIVERGE"
            gate = " *occ*" if d_ig != d_wk else ""
            gate += " *elev*" if d_ig != d_fl else ""
            print("  %-9s %-9s %-11s %-11s %-11s%s%s" % (str(t), dn, d_ig, d_wk, d_fl, gate, flag))
        # Branche `d == null` de la feuille (-> `NO_PATH_UTILITY`) : combien de tuiles candidates
        # n'ont AUCUN chemin vers le ClosestEnemy ? Le pathfinder du type 1 ne bloquant sur aucune
        # unite, elle n'est atteignable que par une coupure de terrain / d'elevation.
        unreach_nat = [t for t, d in nat_pd.items() if d is not None and d < 0]
        unreach_off = [t for t in nat_pd if board.id_at(t[0], t[1]) not in ig]
        print("")
        print("  branche d == null (NO_PATH_UTILITY) : natif pathDist<0 sur %d tuile(s), "
              "offline sans chemin sur %d" % (len(unreach_nat), len(unreach_off)))
        print("=== BILAN === tuiles=%d  gate OCCUPANT exerce sur %d  gate ELEVATION exerce sur %d  "
              "port(ignore) != natif sur %d" % (len(rows), diff_gate, diff_elev, bad))
        if not diff_gate:
            print("  montage NON CONCLUANT : le gate d'occupant ne mord sur aucune tuile.")
        if not diff_elev:
            print("  gate d'elevation non exerce : ce board ne departage pas "
                  "IgnoreTerrainPathfinder (teste l'elevation) d'un pathfinder qui l'ignorerait.")
        return 0
    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        print("[probe17off] runner %s dispose" % rid)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
