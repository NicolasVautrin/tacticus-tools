"""probe #165b -- le RESIDU `SkyStrike` sur une cible au BORD, caster tres eloigne.

`docs/rl/case-165-collapse-tuile-plus-proche.md` §4 : Celestine @(1,0), necroWarden @(6,7) sur
`MC1_67`, le natif atterrit sur (5,7) e1 la ou le port `Tile(7)` rend (6,6) e2.

Ce probe REPRODUIT la mesure et DECOMPOSE le score PAR TERME (feuille par feuille) des tuiles
candidates, cote port, en regard des metadonnees LIVE (`tileMeta`) -- c'est ce qui permet de dire
QUEL terme manque plutot que « le port se trompe ».

Modes :
  --repro   : build + drive + decomposition + cast LIVE (la mesure de reference).
  --geom    : meme chose mais avec des positions/roster surchargeables (generalisation).

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

SKY_ABILITY = 1025
SKY_VIS = "adeptCelestine"


# ---------------------------------------------------------------- RPC / build

def _sid():
    return R._resolve_session()


def rpc(method, body, timeout=90):
    r = R._rpc(_sid(), method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def inject_bc(units: str) -> Path:
    out = ROOT / "logs" / "runners" / ("sky165b-%s.json" % uuid.uuid4().hex[:8])
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", units, "--out", str(out)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not out.exists():
        raise SystemExit("catalog_inject KO: %s" % ((p.stderr or p.stdout or "")[-400:]))
    return out


def build(seed: str, board: str, extra: list) -> int:
    state = ROOT / "logs" / "runners" / ("sky165b-state-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise SystemExit("build KO: %s" % ((p.stderr or p.stdout or "")[-500:]))
    st = json.loads(state.read_text())
    return int(st["runnerId"]), state


# ---------------------------------------------------------------- state / drive

def load(rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dv, ob, snap, board=board), board, dv


def uid_by_vis(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return int(u["id"])
    return None


def live_pos(rid, uid):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120) or {}
    for u in (dv.get("units") or []):
        if int(u.get("id")) == int(uid):
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row"))
    return None


def move(rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def endturn(rid):
    return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def drive_to(rid, wanted: dict, max_turns: int = 16) -> bool:
    """Amene chaque `uid -> (col,row)` a destination, pas-a-pas (mirror du helper du test #165)."""
    for _ in range(max_turns):
        if all(live_pos(rid, u) == p for u, p in wanted.items()):
            return True
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
        for mu in (mov.get("units") or []):
            uid = int(mu.get("unitId") or -1)
            if uid not in wanted:
                continue
            dest = tuple(wanted[uid])
            cur = ((mu.get("pos") or {}).get("col"), (mu.get("pos") or {}).get("row"))
            if cur == dest:
                continue
            reach = [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None]
            if not reach:
                continue
            step = min(reach, key=lambda p: (hexgeo.distance(p, dest), p))
            if step != cur:
                move(rid, uid, *step)
        endturn(rid)
    return all(live_pos(rid, u) == p for u, p in wanted.items())


# ---------------------------------------------------------------- decomposition

def decompose(state, board, tiles, unit_id=None, wt=None):
    """Score PAR FEUILLE de `Tile(7)` pour chaque tuile, exactement comme le fait
    `engine.utilities.tile.sort_tiles_by_utility` (memes `meta`, meme `ctx`).

    `unit_id` = le selecteur `dc.units` du natif -> `runner_tile_leaf_ctx` (case-165b). Sans lui les
    feuilles gatees sur l'unite rendent 0 et le tri se reduit a `Elevation` + `TileEffects`."""
    from engine.utilities.tile import (TILE_LEAVES, TILE_LEAF_IDS, terrain_tile_effects,
                                       runner_tile_leaf_ctx)
    from engine.weights import load as load_weights
    wt = wt or load_weights()
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    fx = getattr(state, "effects", None)
    leaf_ctx = runner_tile_leaf_ctx(state, unit_id)
    out = {}
    for t in tiles:
        info = board.by_id.get(t) or {}
        terr = board.tile_def_id(t)
        effs = []
        if fx is not None:
            effs += [e.name for e in fx.by_unit.get(int(t), []) if not e.consumed and e.name]
        effs += terrain_tile_effects(terr, effs)
        meta = {"elevation": info.get("elevation"), "elevation_max": emax,
                "elevation_min": emin, "effects": effs}
        terms = {}
        for lid in TILE_LEAF_IDS:
            name, leaf = TILE_LEAVES.get(int(lid), (None, None))
            if leaf is None:
                continue
            v = leaf.evaluate(board.coord(t), meta, leaf_ctx, wt)
            if v:
                terms[name] = v
        out[t] = {"coord": board.coord(t), "terrain": terr, "elev": info.get("elevation"),
                  "effects": effs, "terms": terms, "total": float(sum(terms.values()))}
    return out


def tile_meta_by_pos(rid):
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    out = {}
    for t in (tm.get("tiles") or []):
        out[(t.get("col"), t.get("row"))] = t
    return out, tm


# ---------------------------------------------------------------- cast

def cast_sky(rid, caster, target, tries=10):
    act0 = {}
    for _ in range(tries):
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": SKY_ABILITY}}, 120)
        act0 = ((res or {}).get("actions") or [{}])[0]
        if not act0.get("error") and act0.get("mutated"):
            return act0
        endturn(rid)
    return act0


def foot_tiles(act0):
    """Les `Unit_Foot_Tile_Id_1` des steps d'action (avec `Is_Last_Tile`), dans l'ordre."""
    out = []
    for ev in (act0.get("events") or []):
        if ev.get("kind") != "action":
            continue
        try:
            tags = json.loads(ev.get("tags") or "{}")
        except ValueError:
            continue
        if tags.get("Unit_Foot_Tile_Id_1") is not None:
            out.append((int(ev.get("step") or -1), int(tags["Unit_Foot_Tile_Id_1"]),
                        tags.get("Is_Last_Tile")))
    return out


# ---------------------------------------------------------------- scenario

def run(seed: str, board_id: str, cpos, tpos, a_unit: str, dispose: bool = True,
        do_cast: bool = True, blockers=()):
    """`blockers` = [(visualId, (col,row)), ...] — unites SUPPLEMENTAIRES du camp adverse garees
    sur des tuiles du pool. Sert a RETIRER un candidat du `CanAddUnit(AdjacentTiles(target))` et
    a voir sur quoi le natif se rabat (discriminant tri-par-utilite vs ordre-source)."""
    extra_vis = [v for v, _ in blockers]
    bc = inject_bc(SKY_VIS)
    try:
        rid, state_file = build(seed, board_id,
                                ["--seed-bc", str(bc), "--p-units", SKY_VIS,
                                 "--a-units", ",".join([a_unit] + extra_vis), "--no-ai"])
    finally:
        bc.unlink(missing_ok=True)
    try:
        st, board, dv = load(rid)
        caster = uid_by_vis(dv, SKY_VIS)
        target = uid_by_vis(dv, a_unit)
        print("[165b] runner=%d caster=u%s target=u%s spawn c=%s t=%s"
              % (rid, caster, target, live_pos(rid, caster), live_pos(rid, target)))
        if caster is None or target is None:
            return {"error": "roster absent"}
        wanted = {caster: tuple(cpos), target: tuple(tpos)}
        for vis, bpos in blockers:
            buid = uid_by_vis(dv, vis)
            if buid is None:
                return {"error": "blocker %s absent" % vis}
            wanted[buid] = tuple(bpos)
        ok = drive_to(rid, wanted)
        print("[165b] drive ok=%s %s" % (ok, {u: live_pos(rid, u) for u in wanted}))
        if not ok:
            return {"error": "drive KO"}

        st2, board2, dv2 = load(rid)
        from engine.runner.abilities.sisterhood import (_sky_strike_dest_tile,
                                                        _sk_occupied_positions)
        ttile = board2.id_at(*tpos)
        occ = _sk_occupied_positions(st2)
        cands = [t for t in board2.neighbours_native(ttile)
                 if board2.coord(t) not in occ and board2.walkable(t)]
        port = _sky_strike_dest_tile(st2, caster, target)
        dec = decompose(st2, board2, cands, unit_id=caster)
        tm, tm_raw = tile_meta_by_pos(rid)
        print("\n[165b] pool `CanAddUnit(AdjacentTiles(target))` (ordre selecteur natif) :")
        for t in cands:
            d = dec[t]
            live = tm.get(d["coord"]) or {}
            print("  tile=%-4d %-7s terrain=%-10s elev=%s  dist_caster=%d  total=%8.2f  %s"
                  % (t, d["coord"], d["terrain"], d["elev"],
                     hexgeo.distance(tuple(cpos), d["coord"]), d["total"],
                     json.dumps(d["terms"], sort_keys=True)))
            print("      liveTileMeta: %s" % json.dumps(
                {k: v for k, v in live.items() if k not in ("col", "row")}, sort_keys=True)[:400])
        print("[165b] PORT choisit %s" % (port,))

        res = {"rid": rid, "cands": [board2.coord(t) for t in cands], "dec": dec,
               "port": port, "tile_meta": {str(k): v for k, v in tm.items()}}
        if do_cast:
            # `movement-trace` (auto-arme, attach-only) enregistre CHAQUE appel des 42 factories
            # `*Utility$$EvaluateMovementInSteps`. On vide juste avant le cast : ce qui reste
            # ensuite est la LISTE EXACTE des feuilles que le natif evalue pour ce tri.
            rpc("clearMovementTrace", {}, 20)
            act0 = cast_sky(rid, caster, target)
            res["trace"] = rpc("movementTraceStats", {}, 30)
            print("[165b] movementTraceStats: %s" % json.dumps(
                (res["trace"] or {}).get("byUtility"), sort_keys=False))
            if act0.get("error") or not act0.get("mutated"):
                print("[165b] cast KO: err=%s mutated=%s" % (act0.get("error"),
                                                             act0.get("mutated")))
                res["error"] = "cast KO"
                return res
            ft = foot_tiles(act0)
            after = live_pos(rid, caster)
            print("[165b] foot_tiles=%s" % ft)
            print("[165b] NATIF atterrit %s  (port=%s)" % (after, port))
            res["native"] = after
            res["foot_tiles"] = ft
        return res
    finally:
        if dispose:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass


def _score_pool(st, board, caster, target, tpos, variant: str):
    """Scores `Tile(7)` du pool de SkyStrike pour la geometrie COURANTE du `State`.

    `variant` : `full` = le port livre ; `no-owner` = sans le +10 `OwnerInAdjacentTile` ;
    `no-unit` = sans `dc.units` du tout (= le port d'AVANT case-165b). Rend (pool ordonne selecteur,
    {tile: score}) ; le monkey-patch est LOCAL et restaure."""
    from engine.playbook.geminae_superia import GeminaeSuperiaPlaybook
    from engine.runner.abilities.sisterhood import _sk_occupied_positions
    ttile = board.id_at(*tpos)
    occ = _sk_occupied_positions(st)
    pool = [t for t in board.neighbours_native(ttile)
            if board.coord(t) not in occ and board.walkable(t)]
    orig = GeminaeSuperiaPlaybook.owner_in_adjacent_tile
    if variant == "no-owner":
        GeminaeSuperiaPlaybook.owner_in_adjacent_tile = lambda self, tile, ctx: False
    try:
        dec = decompose(st, board, pool, unit_id=(None if variant == "no-unit" else caster))
    finally:
        GeminaeSuperiaPlaybook.owner_in_adjacent_tile = orig
    return pool, {t: dec[t]["total"] for t in pool}


def scan_owner_term(seed: str, board_id: str, a_unit: str, limit: int, dispose: bool = True,
                    variant: str = "no-owner"):
    """Cherche une geometrie ou le terme retire par `variant` RENVERSE l'argmax du tri, puis la joue
    LIVE. `no-owner` isole le +10 `OwnerInAdjacentTile` ; `no-unit` isole le passage de `dc.units`
    dans son ENTIER (c'est la contre-epreuve du fix, rejouable sur n'importe quel board)."""
    bc = inject_bc(SKY_VIS)
    try:
        rid, _sf = build(seed, board_id,
                         ["--seed-bc", str(bc), "--p-units", SKY_VIS,
                          "--a-units", a_unit, "--no-ai"])
    finally:
        bc.unlink(missing_ok=True)
    try:
        st, board, dv = load(rid)
        caster = uid_by_vis(dv, SKY_VIS)
        target = uid_by_vis(dv, a_unit)
        from engine.runner.components import PositionComponent
        cpc = st.get_entity(caster).get_component(PositionComponent)
        tpc = st.get_entity(target).get_component(PositionComponent)
        keep_c, keep_t = (cpc.col, cpc.row), (tpc.col, tpc.row)
        walk = [t for t in sorted(board.by_id) if board.walkable(t)]
        found = []
        for ttile in walk:
            tpos = board.coord(ttile)
            tpc.col, tpc.row = tpos
            for ctile in walk:
                cpos = board.coord(ctile)
                if ctile == ttile or not 2 <= hexgeo.distance(cpos, tpos) <= 3:
                    continue
                cpc.col, cpc.row = cpos
                pool, s_on = _score_pool(st, board, caster, target, tpos, "full")
                if len(pool) < 2:
                    continue
                _p, s_off = _score_pool(st, board, caster, target, tpos, variant)
                best_on = max(pool, key=lambda t: (s_on[t], -pool.index(t)))
                best_off = max(pool, key=lambda t: (s_off[t], -pool.index(t)))
                if best_on == best_off:
                    continue
                found.append((cpos, tpos, board.coord(best_on), board.coord(best_off),
                              [(board.coord(t), s_on[t], s_off[t]) for t in pool]))
        cpc.col, cpc.row = keep_c
        tpc.col, tpc.row = keep_t
        # la geometrie la MOINS chere a atteindre depuis les spawns (chaque saut = un tour de jeu)
        found.sort(key=lambda g: hexgeo.distance(keep_c, g[0]) + hexgeo.distance(keep_t, g[1]))
        for g in found[:limit]:
            print("[owner] caster@%s cible@%s  AVEC=%s  SANS=%s  pool=%s" % g)
        if not found:
            print("[owner] aucune geometrie ou le terme OwnerInAdjacentTile renverse l'argmax")
            return {"rid": rid, "found": []}
        cpos, tpos, best_on, best_off, pool = found[0]
        ok = drive_to(rid, {caster: cpos, target: tpos})
        print("[owner] drive ok=%s c=%s t=%s" % (ok, live_pos(rid, caster), live_pos(rid, target)))
        if not ok:
            return {"rid": rid, "error": "drive KO", "found": found}
        st2, board2, _dv2 = load(rid)
        from engine.runner.abilities.sisterhood import _sky_strike_dest_tile
        port = _sky_strike_dest_tile(st2, caster, target)
        act0 = cast_sky(rid, caster, target)
        after = live_pos(rid, caster)
        print("[owner] PORT=%s  AVEC_terme=%s  SANS_terme=%s  NATIF=%s"
              % (port, best_on, best_off, after))
        return {"rid": rid, "port": port, "with": best_on, "without": best_off, "native": after}
    finally:
        if dispose:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-owner", action="store_true",
                    help="cherche + joue une geometrie ou `OwnerInAdjacentTile` renverse l'argmax")
    ap.add_argument("--scan-unit", action="store_true",
                    help="idem mais en retirant `dc.units` en ENTIER (contre-epreuve du fix)")
    ap.add_argument("--seed", default="165165")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--caster-pos", default="1,0")
    ap.add_argument("--target-pos", default="6,7")
    ap.add_argument("--a-unit", default="necroWarden")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--no-cast", action="store_true")
    ap.add_argument("--block", action="append", default=[],
                    help="visualId:col,row -- gare une unite adverse SUPPLEMENTAIRE sur cette "
                         "tuile (la retire du pool CanAddUnit). Repetable.")
    a = ap.parse_args()
    if a.scan_owner or a.scan_unit:
        scan_owner_term(a.seed, a.board, a.a_unit, 5, dispose=not a.keep,
                        variant="no-unit" if a.scan_unit else "no-owner")
        return
    cpos = tuple(int(x) for x in a.caster_pos.split(","))
    tpos = tuple(int(x) for x in a.target_pos.split(","))
    blockers = []
    for b in a.block:
        vis, pos = b.split(":")
        blockers.append((vis, tuple(int(x) for x in pos.split(","))))
    run(a.seed, a.board, cpos, tpos, a.a_unit, dispose=not a.keep, do_cast=not a.no_cast,
        blockers=blockers)


if __name__ == "__main__":
    main()
