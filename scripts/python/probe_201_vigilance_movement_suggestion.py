"""probe #201 -- `VigilanceEternal` (1202) trie ses tuiles de charge par `MovementSuggestion(32)`,
composite `[Tile(7), TileDistance(34)]` -- et non par un collapse « la plus proche du caster ».

Ce que le probe ETABLIT, en trois etages separes (on ne fitte aucun scalaire) :

  1. `--decompose` : pour une geometrie donnee, le score du pool de charge TERME PAR TERME
     (les feuilles de `Tile(7)` une a une, puis `TileDistance(34)` a part), en regard des
     metadonnees LIVE (`tileMeta`). C'est ce qui permet de nommer LE terme qui tranche.
  2. `--scan` : balaie les geometries jouables et retient celles ou l'ANCIEN collapse
     (`min` sur `(hexdist(caster, tuile), tileId)`) et le NOUVEAU tri (`first_tile_by_utility`
     avec `utility_type=MovementSuggestion`) DESIGNENT DES TUILES DIFFERENTES. C'est la
     geometrie discriminante -- sans elle, le port est invalidable.
  3. le cast LIVE de 1202 sur cette geometrie : la tuile ou le natif POSE Tyrith tranche.

`--repro` rejoue la geometrie de reference #220 (custoKyrus vs necroWarden sur MC1_67), ou le
port d'AVANT etait deja d'accord avec le natif : c'est le temoin de NON-REGRESSION.

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

VIGIL_ABILITY = 1202
VIGIL_VIS = "custoKyrus"


# ---------------------------------------------------------------- RPC / build

def rpc(method, body, timeout=90):
    r = R._rpc(R._resolve_session(), method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def inject_bc(units: str) -> Path:
    out = ROOT / "logs" / "runners" / ("vig201-%s.json" % uuid.uuid4().hex[:8])
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", units, "--out", str(out)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not out.exists():
        raise SystemExit("catalog_inject KO: %s" % ((p.stderr or p.stdout or "")[-400:]))
    return out


def build(seed: str, board: str, extra: list):
    state = ROOT / "logs" / "runners" / ("vig201-state-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise SystemExit("build KO: %s" % ((p.stderr or p.stdout or "")[-600:]))
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


def drive_to(rid, wanted: dict, max_turns: int = 18) -> bool:
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

def decompose(state, board, tiles, unit_id):
    """Score PAR TERME des `tiles`, avec les MEMES `meta`/`ctx` que
    `engine.utilities.tile.sort_tiles_by_utility` -- les 29 feuilles de `Tile(7)` d'un cote,
    `TileDistance(34)` de l'autre (c'est la separation qui rend l'ecart attribuable)."""
    from engine.utilities.tile import (TILE_LEAVES, TILE_LEAF_IDS, terrain_tile_effects,
                                       runner_tile_leaf_ctx, TileDistanceUtility)
    from engine.weights import load as load_weights
    wt = load_weights()
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    fx = getattr(state, "effects", None)
    leaf_ctx = runner_tile_leaf_ctx(state, unit_id)
    dist_leaf = TileDistanceUtility()
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
        pos = board.coord(t)
        terms = {}
        for lid in TILE_LEAF_IDS:
            name, leaf = TILE_LEAVES.get(int(lid), (None, None))
            if leaf is None:
                continue
            v = leaf.evaluate(pos, meta, leaf_ctx, wt)
            if v:
                terms[name] = v
        tile7 = float(sum(terms.values()))
        tdist = dist_leaf.evaluate(pos, meta, leaf_ctx, wt)
        out[t] = {"coord": pos, "terrain": terr, "elev": info.get("elevation"), "effects": effs,
                  "terms": terms, "tile7": tile7, "tiledistance": tdist,
                  "total32": tile7 + tdist}
    return out


def tile_meta_by_pos(rid):
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    return {(t.get("col"), t.get("row")): t for t in (tm.get("tiles") or [])}


# ---------------------------------------------------------------- les deux selecteurs

def pool_of(state, board, caster, target, move_range):
    from engine.runner.abilities.genestealer import (_charge_candidate_tiles,
                                                     VIGIL_SURROUND_RADIUS)
    return _charge_candidate_tiles(state, caster, target, VIGIL_SURROUND_RADIUS, move_range)


def legacy_collapse(board, cands, cpos):
    """Le port d'AVANT #201 : `sorted(cands, key=(hexdist(caster, tuile), tileId))[0]`.
    Reproduit ICI pour que le scan puisse le confronter au nouveau tri sans le reintroduire
    dans `engine/`."""
    if not cands:
        return None
    return board.coord(sorted(cands, key=lambda t: (hexgeo.distance(cpos, board.coord(t)), t))[0])


def new_sort(state, cands, caster):
    from engine.utilities.tile import first_tile_by_utility
    from engine.utilities.utility_type import UtilityType
    best = first_tile_by_utility(state, cands, unit_id=caster,
                                 utility_type=int(UtilityType.MovementSuggestion))
    return state.board.coord(best) if best is not None else None


def tile7_only_sort(state, cands, caster):
    """L'AUTRE moitie du composite, seule : `UtilityDefinition(7)` -- ce que rendrait le foyer si
    on branchait ce call-site sur le litteral des ports freres. Sert de CONTRE-EPREUVE isolant
    `TileDistance(34)` : la ou ce tri differe de `new_sort`, c'est `TileDistance` SEUL qui
    tranche (et non `Tile(7)` qui domine)."""
    from engine.utilities.tile import first_tile_by_utility
    from engine.utilities.utility_type import UtilityType
    best = first_tile_by_utility(state, cands, unit_id=caster, utility_type=int(UtilityType.Tile))
    return state.board.coord(best) if best is not None else None


# ---------------------------------------------------------------- cast

def cast_vigil(rid, caster, target, tries=10):
    act0 = {}
    for _ in range(tries):
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": VIGIL_ABILITY}}, 120)
        act0 = ((res or {}).get("actions") or [{}])[0]
        if not act0.get("error") and act0.get("mutated"):
            return act0
        endturn(rid)
    return act0


# ---------------------------------------------------------------- scenarios

def _print_pool(dec, cands, cpos, board):
    print("  %-6s %-9s %-9s %6s %5s %9s %9s %9s  %s"
          % ("tile", "coord", "terrain", "elev", "dist", "Tile(7)", "TileDist", "TOTAL32",
             "termes Tile(7)"))
    for t in cands:
        d = dec[t]
        print("  %-6d %-9s %-9s %6s %5d %9.2f %9.2f %9.2f  %s"
              % (t, str(d["coord"]), str(d["terrain"]), str(d["elev"]),
                 hexgeo.distance(tuple(cpos), d["coord"]), d["tile7"], d["tiledistance"],
                 d["total32"], json.dumps(d["terms"], sort_keys=True)))


def run_geom(rid, board_arg, caster, target, cpos, tpos, move_range, do_cast=True):
    st, board, _dv = load(rid)
    cands = pool_of(st, board, caster, target, move_range)
    if not cands:
        print("[201] pool VIDE (aucune tuile de charge) -- geometrie inutilisable")
        return {"error": "pool vide"}
    dec = decompose(st, board, cands, caster)
    legacy = legacy_collapse(board, cands, cpos)
    new = new_sort(st, cands, caster)
    only7 = tile7_only_sort(st, cands, caster)
    print("\n[201] pool `CanAddUnit(AdjacentTiles(target)) & MovableTilesInRange(caster,2)` "
          "(ordre selecteur) caster@%s cible@%s :" % (tuple(cpos), tuple(tpos)))
    _print_pool(dec, cands, cpos, board)
    tm = tile_meta_by_pos(rid)
    for t in cands:
        live = tm.get(dec[t]["coord"]) or {}
        print("      liveTileMeta%s: %s" % (dec[t]["coord"], json.dumps(
            {k: v for k, v in live.items() if k not in ("col", "row")}, sort_keys=True)[:300]))
    print("[201] ANCIEN collapse (plus proche, tie-break id) -> %s" % (legacy,))
    print("[201] Tile(7) SEUL (sans TileDistance)            -> %s" % (only7,))
    print("[201] NOUVEAU tri MovementSuggestion(32)          -> %s" % (new,))
    res = {"pool": [board.coord(t) for t in cands], "legacy": legacy, "new": new, "tile7": only7,
           "dec": {str(board.coord(t)): dec[t] for t in cands}}
    if do_cast:
        act0 = cast_vigil(rid, caster, target)
        if act0.get("error") or not act0.get("mutated"):
            print("[201] cast KO: err=%s mutated=%s" % (act0.get("error"), act0.get("mutated")))
            res["error"] = "cast KO"
            return res
        after = live_pos(rid, caster)
        res["native"] = after
        tags = []
        if after == new:
            tags.append("== MovementSuggestion(32)")
        if after == legacy:
            tags.append("== ancien collapse")
        if after == only7:
            tags.append("== Tile(7) seul")
        verdict = ("NEW" if after == new else "PORT FAUX")
        print("[201] NATIF atterrit %s  => %s   [%s]" % (after, verdict, " ; ".join(tags) or "-"))
        res["verdict"] = verdict
    return res


def scenario(seed, board_id, cpos, tpos, dispose=True, do_cast=True, a_unit="necroWarden"):
    bc = inject_bc(VIGIL_VIS)
    try:
        rid, _sf = build(seed, board_id, ["--seed-bc", str(bc), "--p-units", VIGIL_VIS,
                                          "--a-units", a_unit, "--no-ai"])
    finally:
        bc.unlink(missing_ok=True)
    try:
        st, board, dv = load(rid)
        caster, target = uid_by_vis(dv, VIGIL_VIS), uid_by_vis(dv, a_unit)
        print("[201] runner=%d caster=u%s target=u%s spawn c=%s t=%s"
              % (rid, caster, target, live_pos(rid, caster), live_pos(rid, target)))
        if caster is None or target is None:
            return {"error": "roster absent"}
        ok = drive_to(rid, {caster: tuple(cpos), target: tuple(tpos)})
        print("[201] drive ok=%s c=%s t=%s" % (ok, live_pos(rid, caster), live_pos(rid, target)))
        if not ok:
            return {"error": "drive KO"}
        mr = move_range()
        return run_geom(rid, board_id, caster, target, cpos, tpos, mr, do_cast=do_cast)
    finally:
        if dispose:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass


def move_range():
    from engine.entities.effects.magnitude import ability_var
    return int(ability_var("VigilanceEternal", "range", is_constant=True) or 2)


def scan(seed, board_id, a_unit, limit, dispose=True, play=True, max_pairs=0, against="legacy"):
    """Balaie les couples (caster, cible) jouables et retient ceux ou le NOUVEAU tri diverge du
    tri de reference `against`, puis joue LIVE le moins couteux a atteindre depuis les spawns.

      * `against="legacy"` : contre l'ANCIEN collapse « la plus proche, tie-break id ». Isole ce
        que le fix CHANGE.
      * `against="tile7"`  : contre `Tile(7)` SEUL. Isole ce que `TileDistance(34)` APPORTE --
        c'est la contre-epreuve de la feuille portee, celle qui interdit de conclure « le fix
        marche parce que Tile(7) domine »."""
    bc = inject_bc(VIGIL_VIS)
    try:
        rid, _sf = build(seed, board_id, ["--seed-bc", str(bc), "--p-units", VIGIL_VIS,
                                          "--a-units", a_unit, "--no-ai"])
    finally:
        bc.unlink(missing_ok=True)
    try:
        st, board, dv = load(rid)
        caster, target = uid_by_vis(dv, VIGIL_VIS), uid_by_vis(dv, a_unit)
        from engine.runner.components import PositionComponent
        cpc = st.get_entity(caster).get_component(PositionComponent)
        tpc = st.get_entity(target).get_component(PositionComponent)
        keep_c, keep_t = (cpc.col, cpc.row), (tpc.col, tpc.row)
        mr = move_range()
        walk = [t for t in sorted(board.by_id) if board.walkable(t)]
        found, seen = [], 0
        for ttile in walk:
            tp = board.coord(ttile)
            tpc.col, tpc.row = tp
            for ctile in walk:
                cp = board.coord(ctile)
                # gate move = `Not(IsAdjacent)` -> dist >= 2 ; pool non vide -> dist <= mr + 1
                if ctile == ttile or not 2 <= hexgeo.distance(cp, tp) <= mr + 1:
                    continue
                cpc.col, cpc.row = cp
                cands = pool_of(st, board, caster, target, mr)
                if len(cands) < 2:
                    continue
                seen += 1
                ref = (legacy_collapse(board, cands, cp) if against == "legacy"
                       else tile7_only_sort(st, cands, caster))
                new = new_sort(st, cands, caster)
                if ref == new:
                    continue
                dec = decompose(st, board, cands, caster)
                found.append((cp, tp, ref, new,
                              [(dec[t]["coord"], dec[t]["tile7"], dec[t]["tiledistance"])
                               for t in cands]))
                if max_pairs and len(found) >= max_pairs:
                    break
            if max_pairs and len(found) >= max_pairs:
                break
        cpc.col, cpc.row = keep_c
        tpc.col, tpc.row = keep_t
        print("[201-scan/%s] board=%s couples testes=%d  divergents=%d"
              % (against, board_id, seen, len(found)))
        found.sort(key=lambda g: hexgeo.distance(keep_c, g[0]) + hexgeo.distance(keep_t, g[1]))
        for g in found[:limit]:
            print("[201-scan/%s] caster@%s cible@%s  REF=%s  NOUVEAU=%s  pool(Tile7,TileDist)=%s"
                  % ((against,) + g))
        if not found:
            print("[201-scan] AUCUNE geometrie discriminante sur ce board")
            return {"rid": rid, "found": []}
        if not play:
            return {"rid": rid, "found": found}
        cp, tp, legacy, new, _pool = found[0]
        ok = drive_to(rid, {caster: cp, target: tp})
        print("[201-scan] drive ok=%s c=%s t=%s" % (ok, live_pos(rid, caster),
                                                    live_pos(rid, target)))
        if not ok:
            return {"rid": rid, "error": "drive KO", "found": found}
        out = run_geom(rid, board_id, caster, target, cp, tp, mr, do_cast=True)
        out["found"] = len(found)
        return out
    finally:
        if dispose:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true",
                    help="cherche + joue une geometrie ou ANCIEN collapse != NOUVEAU tri")
    ap.add_argument("--scan-only", action="store_true", help="scan sans jouer (inventaire)")
    ap.add_argument("--repro", action="store_true",
                    help="rejoue la geometrie de reference #220 (temoin de non-regression)")
    ap.add_argument("--seed", default="201201")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--caster-pos", default="2,1")
    ap.add_argument("--target-pos", default="0,2")
    ap.add_argument("--a-unit", default="necroWarden")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--max-pairs", type=int, default=0)
    ap.add_argument("--against", choices=("legacy", "tile7"), default="legacy",
                    help="tri de reference du scan : `legacy` = l'ancien collapse ; "
                         "`tile7` = Tile(7) seul (isole l'apport de TileDistance)")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--no-cast", action="store_true")
    a = ap.parse_args()
    if a.scan or a.scan_only:
        scan(a.seed, a.board, a.a_unit, a.limit, dispose=not a.keep, play=not a.scan_only,
             max_pairs=a.max_pairs, against=a.against)
        return
    cpos = tuple(int(x) for x in a.caster_pos.split(","))
    tpos = tuple(int(x) for x in a.target_pos.split(","))
    scenario(a.seed, a.board, cpos, tpos, dispose=not a.keep, do_cast=not a.no_cast,
             a_unit=a.a_unit)


if __name__ == "__main__":
    main()
