#!/usr/bin/env python
"""#126 -- DIRECTION du beam DarkTalonStrike (1092) : le port prenait le PROLONGEMENT, le natif fait
un ARGMAX.

`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine` :

    ring    = AdjacentTiles(target@0x178)
    nearest = First( SortByDistance(AdjacentTiles(caster@0x160), target@0x178), 1 )
    angle   = AngleBetweenLines(caster@0x160, nearest, target@0x178, subject@0x180)
    count   = Count( Units( GetTilesInLine(subject@0x180) ) )
    best    = First( SortByFormula( SortByFormula(ring, angle, ASC), count, DESC ), 1 )
    return    target@0x178  op_Addition  GetTilesInLine(best)

Ce probe MESURE, sur un etat ou la meilleure direction n'est PAS le prolongement `caster -> aim` :
natif (`aiDryRunAllUnits` -> `CalculateNextActionForUnit`) vs moteur ARGMAX (post-#126) vs moteur
PROLONGEMENT (feuille remise a la geometrie pre-#126).

Scenario derive du board (aucune tuile hardcodee) : caster P, chaine d'ennemis E1 = P + d1,
E2 = E1 + d2, E3 = E1 + 2*d2 avec `d2` a 60 deg de `d1` (=> E3 a distance 3 de P, hors de la portee
de cast) et toutes les tuiles a la MEME elevation (le gate #124 reste inerte, on n'exerce que la
direction).
  prolongement -> util(E1) = 1 (la tuile visee seule) < MIN_UTILITY(2) -> AUCUN NonComparable ;
  argmax       -> util(E1) = 1 + 2 = 3 -> cast 1092 sur l'entite-tuile de E1, comme le natif.

Usage : python probe_126_dark_talon_beam_direction.py [--board MC1_67] [--seed 41171]
ASCII only. Test jumeau : tests/engine/test_dark_talon_beam_direction_decision_live.py
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from collections import deque

import hexgeo

HOST = "http://127.0.0.1:8765"
HERE = os.path.dirname(os.path.abspath(__file__))


def _sid() -> int:
    with urllib.request.urlopen(f"{HOST}/api/admin/status", timeout=15) as r:
        return int(json.load(r)["session"]["id"])


def _rpc(sid, method, args=None, timeout=60):
    body = json.dumps({"method": method, "args": args or {}, "timeout": timeout * 1000}).encode()
    req = urllib.request.Request(f"{HOST}/api/scripts/{sid}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 20) as r:
        out = json.load(r)
    if "error" in out and out.get("error"):
        raise RuntimeError(f"{method}: {out['error']}")
    return out.get("result")


# ------------------------------------------------------------------ geometrie (derivee du board)


def _move_ring(p, walk, elev):
    """`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : walkable +
    porte `|Delta elev| < 2` -- le graphe de MOUVEMENT natif (waypoints du driver de placement)."""
    if elev.get(p) is None:
        return []
    return [n for n in hexgeo.neighbors(p[0], p[1])
            if walk.get(n) and elev.get(n) is not None and abs(elev[n] - elev[p]) < 2]


def _gated_path(src, dst, walk, elev):
    if src == dst:
        return [src]
    prev, q = {src: None}, deque([src])
    while q:
        cur = q.popleft()
        for n in _move_ring(cur, walk, elev):
            if n in prev:
                continue
            prev[n] = cur
            if n == dst:
                path, p = [], n
                while p is not None:
                    path.append(p)
                    p = prev[p]
                return list(reversed(path))
            q.append(n)
    return []


def _find_elbow(elev, walk):
    """(P, E1, E2, E3) : `E1 = P + d1`, `E2 = E1 + d2`, `E3 = E1 + 2*d2`, `d2` a 60 deg de `d1`
    (aretes voisines mod 6) -> `dist(P, E3) = 3`. Toutes les tuiles + le PROLONGEMENT `E1 + d1`
    walkables et de MEME elevation : le gate d'elevation reste inerte, seule la direction est
    exercee. Le prolongement doit exister ET rester VIDE (sinon le port pre-#126 compterait aussi)."""
    cube = {p: hexgeo.to_cube(p[0], p[1]) for p in elev}
    dirs = [(0, -1, 1), (1, -1, 0), (1, 0, -1), (0, 1, -1), (-1, 1, 0), (-1, 0, 1)]
    for P in sorted(elev):
        if not walk.get(P) or elev.get(P) is None:
            continue
        px, _py, pz = cube[P]
        for i, d1 in enumerate(dirs):
            for di in (-1, 1):
                d2 = dirs[(i + di) % 6]
                e1 = hexgeo.from_cube(px + d1[0], pz + d1[2])
                ext = hexgeo.from_cube(px + 2 * d1[0], pz + 2 * d1[2])       # prolongement P->E1
                if e1 not in cube or ext not in cube:
                    continue
                ex, _ey, ez = cube[e1]
                chain = [hexgeo.from_cube(ex + d2[0] * k, ez + d2[2] * k) for k in (1, 2)]
                tiles = [P, e1, ext] + chain
                if any(t not in cube or not walk.get(t) for t in tiles):
                    continue
                if len({elev[t] for t in tiles}) != 1:
                    continue                          # meme palier -> gate #124 inerte
                if hexgeo.distance(P, chain[1]) != 3:
                    continue                          # E3 hors portee de cast (portee mesuree = 2)
                return P, e1, chain[0], chain[1], ext
    return None


# ------------------------------------------------------------------ harnais live


def _positions(sid, rid):
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    return dv, {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")}


def _drive_to(sid, rid, walk, elev, wanted, rounds=14):
    for _ in range(rounds):
        _dv, pos = _positions(sid, rid)
        if all(pos.get(u) == dest for u, dest in wanted.items()):
            return True
        occupied = set(pos.values())
        for uid, dest in wanted.items():
            cur = pos.get(uid)
            if cur is None or cur == dest:
                continue
            for p in reversed(_gated_path(cur, dest, walk, elev)[1:]):
                if not walk.get(p) or (p in occupied and p != dest):
                    continue
                r = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
                if isinstance(r, dict) and (r.get("actions") or [{}])[0].get("mutated"):
                    occupied.discard(cur)
                    occupied.add(p)
                    break
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    _dv, pos = _positions(sid, rid)
    return all(pos.get(u) == dest for u, dest in wanted.items())


def _native(sid, rid, cid):
    dry = _rpc(sid, "aiDryRunAllUnits", {"runnerId": rid}, 150)
    nat = next((u for u in (dry.get("units") or []) if u.get("unitId") == cid), None)
    ab = tgt = None
    for m in ((nat or {}).get("proposed") or []):
        if m.get("cls") == "ActiveAbilityMessage" and ab is None:
            ab, tgt = m.get("abilityType"), m.get("targetId")
    return {"ability": ab, "target": tgt}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="41171")
    a = ap.parse_args(argv)

    sid = _sid()
    sf = os.path.join(tempfile.gettempdir(), "probe126_dts_dir.json")
    cmd = [sys.executable, os.path.join(HERE, "rl_duel.py"), "build", "--seed", a.seed,
           "--board", a.board, "--state-file", sf, "--p-units", "darkaAzrael",
           "--a-units", "eldarRanger,eldarRanger,eldarRanger",
           "--hp-target", "90000", "--hp-player", "90000"]
    print("[build]", " ".join(cmd[2:]))
    out = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stdout[-3000:])
        print(out.stderr[-3000:])
        return 2
    rid = json.load(open(sf, encoding="utf-8"))["runnerId"]
    print("[runner]", rid)

    try:
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        tiles = bg.get("tiles") or []
        elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
        walk = {(t["col"], t["row"]): bool(t.get("walkable")) for t in tiles}
        win = _find_elbow(elev, walk)
        if win is None:
            print("[skip] aucune configuration coude sur", a.board)
            return 1
        P, e1, e2, e3, ext = win
        print(f"[scenario] P={P} E1={e1} E2={e2} E3={e3} prolongement={ext} "
              f"elev={elev[P]} dist(P,E3)={hexgeo.distance(P, e3)}")

        dv, _pos = _positions(sid, rid)
        mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
        cid = next((u["id"] for u in mine if u.get("visualId") == "darkaAzrael"), None)
        myplayer = next((u.get("owner") for u in mine), None)
        eids = [u["id"] for u in (dv.get("units") or [])
                if u.get("owner") != myplayer and u.get("alive")]
        if cid is None or len(eids) < 3:
            print("[skip] roster incomplet", cid, eids)
            return 1
        wanted = {cid: P, eids[0]: e1, eids[1]: e2, eids[2]: e3}
        if not _drive_to(sid, rid, walk, elev, wanted):
            _dv, pos = _positions(sid, rid)
            print("[skip] placement incomplet", {u: pos.get(u) for u in wanted}, "!=", wanted)
            return 1
        for _ in range(3):
            dv, _p = _positions(sid, rid)
            if dv.get("currentPlayer") == myplayer:
                break
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        at = _rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": cid, "abilityId": 1092}, 90)
        aims = []
        for u in (at.get("units") or []):
            if u.get("unitId") != cid:
                continue
            for ab in (u.get("abilities") or []):
                if ab.get("abilityId") != 1092:
                    continue
                for t in (ab.get("fromHere") or []):
                    if t.get("kind") == "tile" and t.get("tile"):
                        aims.append((t["tile"]["col"], t["tile"]["row"]))
        print("[aims fromHere]", sorted(aims), "E3 eligible:", e3 in aims)

        sys.path.insert(0, HERE)
        import engine.playbook.noncomparable.dark_talon_strike as DTS
        enemy_set = {e1, e2, e3}
        for aim in sorted(set(aims) | {e1, e2, e3}):
            argmax = DTS._beam_count(P, aim, enemy_set, walk, elev)
            print(f"  aim {aim}: util(argmax)={argmax}")

        from engine import weights as W
        from engine.playbook import scene as _scene
        from engine_validate import engine_decide

        def _engine():
            d = _rpc(sid, "decisionView",
                     {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mv = _rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
            mbu = {u.get("unitId"): u for u in (mv.get("units") or [])}
            e = engine_decide(sid, rid, d, mbu, cid, wt, predictor)
            return {"ability": e.get("ability") if e.get("kind") == "ability" else None,
                    "target": e.get("target"), "kind": e.get("kind")}

        wt = W.load()
        predictor = _scene.build_predictor(_rpc_bound(sid), rid)
        nat = _native(sid, rid, cid)
        post = _engine()
        orig = DTS._best_line_direction

        def _prolongement(origin, aim, enemy_set, walkable_at, elevation_at, tile_exists):
            ox, _oy, oz = hexgeo.to_cube(origin[0], origin[1])
            ax, _ay, az = hexgeo.to_cube(aim[0], aim[1])
            dx, dz = ax - ox, az - oz
            return None if (dx == 0 and dz == 0) else hexgeo.from_cube(ax + dx, az + dz)

        DTS._best_line_direction = _prolongement
        try:
            pre = _engine()
        finally:
            DTS._best_line_direction = orig
        print("[natif]        ", nat)
        print("[argmax #126]  ", post)
        print("[prolongement] ", pre)
        print("[VERDICT] discriminant:",
              (post["ability"], post["target"]) == (nat["ability"], nat["target"])
              and (pre["ability"], pre["target"]) != (nat["ability"], nat["target"]))
        return 0
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            print("[dispose]", rid)
        except Exception as exc:                                   # noqa: BLE001
            print("[dispose] echec:", exc)


def _rpc_bound(sid):
    def f(method, args=None, timeout=60):
        return _rpc(sid, method, args, timeout)
    return f


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
