"""probe #206 -- les DEUX derniers call-sites `SortTilesByUtility(..., 0x20)` restes COLLAPSES apres
#201 : `BlackRage` (1163, bloodDeathCompany) et `Waaagh` (1058, orksWarboss).

Les deux appellent, au decompile :

    First( SortTilesByUtility( <Ability>.GetPossibleMovementTiles(...), caster@0x160, 0x20 ), 1 )

soit EXACTEMENT la forme de `VigilanceEternalAbility$$ExecuteBehaviour` (#201) : composite
`MovementSuggestion(32) = [Tile(7), TileDistance(33)]`.

Ce que le probe ETABLIT (jamais un scalaire fitte -- on separe les etages) :

  1. `--scan-only` : balaie OFFLINE les geometries (caster, cible) jouables et retient celles ou
     l'ANCIEN collapse et le NOUVEAU tri DESIGNENT DES TUILES DIFFERENTES. Sans une telle
     geometrie le port est invalidable : sur carte plate `Tile(7)` est constant, `TileDistance`
     ordonne seul par distance croissante, et TOUT collapse « la plus proche » a l'air juste.
  2. `--decompose` (implicite a chaque cas joue) : le pool score TERME PAR TERME -- les feuilles de
     `Tile(7)` une a une, `TileDistance(33)` a part -- pour NOMMER le terme qui tranche.
  3. le cast LIVE : la tuile ou le natif POSE le caster tranche entre ANCIEN et NOUVEAU.

Les deux ANCIENS collapses ne sont PAS identiques et sont reproduits ici tels qu'ils etaient
(jamais reintroduits dans `engine/`) :
  * Waaagh    : `sorted(pool, key=(hexdist(caster, tuile), tileId))[0]` -- MEME pool que le natif.
  * BlackRage : pool COLLAPSE lui aussi (`board.neighbours(tuile de la cible)`, ring-1 NU, sans
                `MovableTilesInRange`), trie par `hexdist(caster, tuile)` (tri STABLE python ->
                tie-break = ordre de `board.neighbours`), puis la feuille `MoveUnit` prenait la 1re
                libre+walkable de la liste.

ASCII only (cp1252). Usage :
    python probe_206_charge_tile_movement_suggestion.py --ability waaagh --scan-only
    python probe_206_charge_tile_movement_suggestion.py --ability blackrage --cases 5
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

# --------------------------------------------------------------- les deux call-sites du lot
ABILITIES = {
    "blackrage": {"id": 1163, "vis": "bloodDeathCompany", "cfg": "BlackRage"},
    "waaagh":    {"id": 1058, "vis": "orksWarboss",       "cfg": "Waaagh"},
}


# ---------------------------------------------------------------- RPC / build

def rpc(method, body, timeout=90):
    r = R._rpc(R._resolve_session(), method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def inject_bc(units: str) -> Path:
    out = ROOT / "logs" / "runners" / ("p206-%s.json" % uuid.uuid4().hex[:8])
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", units, "--out", str(out)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not out.exists():
        raise SystemExit("catalog_inject KO: %s" % ((p.stderr or p.stdout or "")[-400:]))
    return out


def build(seed, board, extra):
    state = ROOT / "logs" / "runners" / ("p206-state-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise SystemExit("build KO: %s" % ((p.stderr or p.stdout or "")[-600:]))
    return int(json.loads(state.read_text())["runnerId"]), state


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
    """Amene chaque unite sur SA position voulue (pas-a-pas via `aiMovableTiles`), puis `endturn`
    -- ce qui RESET le flag `Moved` du caster (indispensable : `CasterHasNotMoved` gate Waaagh)."""
    for _ in range(max_turns):
        if all(live_pos(rid, u) == p for u, p in wanted.items()):
            endturn(rid)                      # reset du flag Moved avant le cast
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


# ---------------------------------------------------------------- decomposition par etage

def decompose(state, board, tiles, unit_id):
    """Score PAR TERME des `tiles`, avec les MEMES `meta`/`ctx` que
    `engine.utilities.tile.sort_tiles_by_utility` : les feuilles de `Tile(7)` d'un cote,
    `TileDistance(33)` de l'autre. C'est cette separation qui rend l'ecart ATTRIBUABLE."""
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
        out[t] = {"coord": pos, "terrain": terr, "elev": info.get("elevation"), "terms": terms,
                  "tile7": tile7, "tiledistance": tdist, "total32": tile7 + tdist}
    return out


# ---------------------------------------------------------------- pools / tris (par ability)

def move_range_of(kind, state, caster):
    if kind == "waaagh":
        from engine.runner.abilities.orks import waaagh_move_range
        import gameconfig as GC
        extra = int(((GC.ability("Waaagh") or {}).get("constants") or {}).get("extraMovement") or 0)
        return waaagh_move_range(state, caster, extra)
    from engine.runner.abilities.loki.strike import _black_rage_move_range
    return _black_rage_move_range(state, caster)


def pool_of(kind, state, caster, target, move_range):
    from engine.runner.abilities.behaviours import entities_from_state
    if kind == "waaagh":
        from engine.runner.abilities.orks import waaagh_possible_movement_tiles_selector as sel
    else:
        from engine.runner.abilities.loki.strike import (
            black_rage_possible_movement_tiles_selector as sel)
    return sel(move_range).evaluate(entities_from_state(state, caster, target))


def new_sort(state, cands, caster):
    """Ce que le PORT #206 rend : `First(SortTilesByUtility(pool, caster, 0x20), 1)`."""
    from engine.utilities.tile import first_tile_by_utility
    from engine.utilities.utility_type import UtilityType
    best = first_tile_by_utility(state, cands, unit_id=caster,
                                 utility_type=int(UtilityType.MovementSuggestion))
    return state.board.coord(best) if best is not None else None


def tile7_only_sort(state, cands, caster):
    """CONTRE-EPREUVE : le composite `Tile(7)` SEUL (le litteral des ports freres). La ou ce tri
    differe de `new_sort`, c'est `TileDistance(33)` SEUL qui tranche."""
    from engine.utilities.tile import first_tile_by_utility
    from engine.utilities.utility_type import UtilityType
    best = first_tile_by_utility(state, cands, unit_id=caster, utility_type=int(UtilityType.Tile))
    return state.board.coord(best) if best is not None else None


def legacy_waaagh(board, cands, cpos):
    """Port d'AVANT #206 : `sorted(pool, key=(hexdist(caster, tuile), tileId))[0]`."""
    if not cands:
        return None
    return board.coord(sorted(cands, key=lambda t: (hexgeo.distance(cpos, board.coord(t)), t))[0])


def legacy_black_rage(state, board, caster, target, cpos):
    """Port d'AVANT #206 (`_black_rage_charge_positions` + feuille `MoveUnit`) : ring-1 NU de la
    tuile de la cible (`board.neighbours`), trie STABLE par `hexdist(caster, tuile)`, puis la 1re
    tuile walkable ET libre (ce que faisait `MoveUnit` en aval)."""
    from engine.runner.components import PositionComponent
    from engine.runner.operations.displace import _occupied
    te = state.get_entity(target)
    tpc = te.get_component(PositionComponent) if te is not None else None
    if tpc is None:
        return None
    ttid = board.id_at(tpc.col, tpc.row)
    if ttid is None:
        return None
    positions = []
    for tid in board.neighbours(ttid):
        t = board.by_id.get(tid)
        if t is not None:
            positions.append((t["col"], t["row"]))
    positions.sort(key=lambda p: hexgeo.distance(tuple(cpos), p))    # tri STABLE (pas de tie-break)
    occ = _occupied(state, caster)
    for pos in positions:
        tid = board.id_at(pos[0], pos[1])
        if tid is None or not board.walkable(tid) or pos in occ:
            continue
        return pos
    return None


def legacy_of(kind, state, board, cands, caster, target, cpos):
    return (legacy_waaagh(board, cands, cpos) if kind == "waaagh"
            else legacy_black_rage(state, board, caster, target, cpos))


# ---------------------------------------------------------------- scan offline

def _kind_of_divergence(dec, board, legacy, new):
    """QUEL etage produit la divergence -- c'est la seule facon de ne pas se mentir sur ce que la
    pose live valide :

      * `TILE7`    : `Tile(7)` DIFFERE entre la tuile de l'ANCIEN et celle du NOUVEAU. C'est le
                     regime demande : un terme ENTIER (Elevation 10/niveau, TileEffects +-9/-25)
                     renverse l'ordre. Le collapse « la plus proche » y est FRANCHEMENT faux.
      * `TILEDIST` : `Tile(7)` egal, `total32` different -> seul `TileDistance(33)` tranche.
      * `TIEBREAK` : `total32` egal -> c'est l'ordre du SELECTEUR SOURCE (tri stable) qui tranche,
                     contre le tie-break `tileId` INVENTE de l'ancien collapse.
    """
    inv = {d["coord"]: d for d in dec.values()}
    a, b = inv.get(tuple(legacy)), inv.get(tuple(new))
    if a is None or b is None:
        return "HORS-POOL"          # l'ancien pool BlackRage sortait du pool natif -> divergence de POOL
    if abs(a["tile7"] - b["tile7"]) > 1e-9:
        return "TILE7"
    if abs(a["total32"] - b["total32"]) > 1e-9:
        return "TILEDIST"
    return "TIEBREAK"


def scan_geometries(kind, state, board, caster, target, max_keep=400):
    """Mute OFFLINE les positions des deux unites et retient les couples ou ANCIEN != NOUVEAU.
    Rend [(cpos, tpos, legacy, new, only7, pool_dbg, categorie)] ; positions restaurees a la sortie."""
    from engine.runner.components import PositionComponent
    cpc = state.get_entity(caster).get_component(PositionComponent)
    tpc = state.get_entity(target).get_component(PositionComponent)
    keep_c, keep_t = (cpc.col, cpc.row), (tpc.col, tpc.row)
    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    found, seen = [], 0
    try:
        for ttile in walk:
            tp = board.coord(ttile)
            tpc.col, tpc.row = tp
            for ctile in walk:
                cp = board.coord(ctile)
                if ctile == ttile:
                    continue
                d = hexgeo.distance(cp, tp)
                # `TargetIsNotAdjacent` -> dist >= 2 ; pool non vide -> dist <= move_range + 1
                cpc.col, cpc.row = cp
                mr = move_range_of(kind, state, caster)
                if not 2 <= d <= mr + 1:
                    continue
                cands = pool_of(kind, state, caster, target, mr)
                if len(cands) < 2:
                    continue
                seen += 1
                legacy = legacy_of(kind, state, board, cands, caster, target, cp)
                new = new_sort(state, cands, caster)
                if legacy == new or new is None or legacy is None:
                    continue
                dec = decompose(state, board, cands, caster)
                found.append((cp, tp, legacy, new, tile7_only_sort(state, cands, caster),
                              [(dec[t]["coord"], round(dec[t]["tile7"], 2),
                                round(dec[t]["tiledistance"], 2)) for t in cands],
                              _kind_of_divergence(dec, board, legacy, new)))
                if len(found) >= max_keep:
                    return found, seen
    finally:
        cpc.col, cpc.row = keep_c
        tpc.col, tpc.row = keep_t
    return found, seen


# ---------------------------------------------------------------- cast live

def cast(rid, kind, caster, target, tries=8):
    """Caste l'ability et rend (action, position du caster APRES). `mutated == False` sans `error`
    = ce n'est pas le tour du camp du caster (ou le gate refuse) -> `endturn` et on retente.

    La position d'apres est lue dans le retour d'`applyAction` (`units[].squadId/pos`), PAS via
    `decisionView` : quand l'action termine la bataille, la vue de decision ne liste plus rien et
    `live_pos` rendrait `None` -- faux negatif qui ferait passer un port juste pour faux."""
    aid = ABILITIES[kind]["id"]
    act0, res = {}, {}
    for _ in range(tries):
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": aid}}, 120) or {}
        act0 = (res.get("actions") or [{}])[0]
        if not act0.get("error") and act0.get("mutated"):
            break
        endturn(rid)
    after = None
    for u in (res.get("units") or []):
        if int(u.get("squadId", -1)) == int(caster):
            p = u.get("pos") or {}
            after = (p.get("col"), p.get("row"))
            break
    return act0, after


def spawn_tiles_from_events(act0) -> set:
    """Tuiles ou les summons du cast ont ATTERRI, lues dans les events de l'action : l'event
    `step 10` d'une entite portant `Unit_IsSummoned:1` expose ses pieds (`Unit_Foot_Tile_Id_*`).
    C'est la seule lecture fiable -- `decisionView` post-cast rend leur position APRES le
    `PerformAIAction` final, qui les a deja fait jouer."""
    out = set()
    for ev in (act0.get("events") or []):
        tags = ev.get("tags")
        if not tags:
            continue
        try:
            d = json.loads(tags) if isinstance(tags, str) else dict(tags)
        except Exception:
            continue
        if not d.get("Unit_IsSummoned"):
            continue
        for k, v in d.items():
            if k.startswith("Unit_Foot_Tile_Id"):
                out.add(int(v))
    return out


def print_pool(dec, cands, cpos):
    print("  %-6s %-9s %-10s %5s %5s %9s %9s %9s  %s"
          % ("tile", "coord", "terrain", "elev", "dist", "Tile(7)", "TileDist", "TOTAL32",
             "termes Tile(7)"))
    for t in cands:
        d = dec[t]
        print("  %-6d %-9s %-10s %5s %5d %9.2f %9.2f %9.2f  %s"
              % (t, str(d["coord"]), str(d["terrain"]), str(d["elev"]),
                 hexgeo.distance(tuple(cpos), d["coord"]), d["tile7"], d["tiledistance"],
                 d["total32"], json.dumps(d["terms"], sort_keys=True)))


def play_case(rid, kind, cp, tp, a_unit):
    """Drive la geometrie puis CASTE. Rend le verdict de CE cas."""
    st, board, dv = load(rid)
    caster, target = uid_by_vis(dv, ABILITIES[kind]["vis"]), uid_by_vis(dv, a_unit)
    if caster is None or target is None:
        return {"error": "roster absent"}
    if not drive_to(rid, {caster: tuple(cp), target: tuple(tp)}):
        return {"error": "drive KO", "c": live_pos(rid, caster), "t": live_pos(rid, target)}
    st, board, dv = load(rid)                       # etat POST-drive : c'est celui du cast
    mr = move_range_of(kind, st, caster)
    cands = pool_of(kind, st, caster, target, mr)
    if not cands:
        return {"error": "pool vide"}
    dec = decompose(st, board, cands, caster)
    legacy = legacy_of(kind, st, board, cands, caster, target, cp)
    new = new_sort(st, cands, caster)
    only7 = tile7_only_sort(st, cands, caster)
    print("\n[206/%s] pool GetPossibleMovementTiles caster@%s cible@%s (move_range=%d) :"
          % (kind, tuple(cp), tuple(tp), mr))
    print_pool(dec, cands, cp)
    print("[206/%s] ANCIEN collapse                        -> %s" % (kind, legacy))
    print("[206/%s] Tile(7) SEUL (sans TileDistance)        -> %s" % (kind, only7))
    print("[206/%s] NOUVEAU tri MovementSuggestion(32)      -> %s" % (kind, new))
    act0, after = cast(rid, kind, caster, target)
    if act0.get("error") or not act0.get("mutated"):
        return {"error": "cast KO: %s (mutated=%s)" % (act0.get("error"), act0.get("mutated")),
                "legacy": legacy, "new": new}
    # WAAAGH : l'etage MOVE s'execute APRES l'etage SPAWN (`Group(spawnB,0x22)` puis
    # `Group(moveB,0x23)`), et les 2 Ork Boyz atterrissent sur des tuiles ADJACENTES AU CASTER
    # (`PickRandomly(CanAddUnit(AdjacentTiles(casterTile)), 2)`) -- qui recouvrent souvent le pool
    # de charge. Le pool que le natif TRIE est donc le pool POST-SPAWN. Prevoir depuis l'etat
    # PRE-cast mesurerait un AUTRE etage (le tirage) et fabriquerait de faux contre-exemples : on
    # relit les tuiles de spawn dans les events (`Unit_IsSummoned` / `Unit_Foot_Tile_Id_1`) et on
    # RE-TRIE le pool ampute -- ce qui isole bien l'etage TRI, seul objet de ce port.
    spawned_tiles = spawn_tiles_from_events(act0)
    if kind == "waaagh" and spawned_tiles:
        cands2 = [t for t in cands if t not in spawned_tiles]
        if cands2 != cands:
            legacy = legacy_of(kind, st, board, cands2, caster, target, cp)
            new = new_sort(st, cands2, caster) if cands2 else None
            print("[206/%s] spawns Ork Boyz sur %s -> pool POST-SPAWN %s ; ANCIEN=%s NOUVEAU=%s"
                  % (kind, sorted(spawned_tiles), [board.coord(t) for t in cands2], legacy, new))
    verdict = "NEW" if after == new else ("LEGACY" if after == legacy else "AUTRE")
    print("[206/%s] NATIF atterrit %s  => %s" % (kind, after, verdict))
    return {"legacy": legacy, "new": new, "tile7": only7, "native": after, "verdict": verdict}


# ---------------------------------------------------------------- scenario complet

def run(kind, seed, board_id, a_unit, cases, scan_only, limit, keep, only_cat=None):
    vis = ABILITIES[kind]["vis"]
    bc = inject_bc(vis)
    try:
        rid, _sf = build(seed, board_id, ["--seed-bc", str(bc), "--p-units", vis,
                                          "--a-units", a_unit, "--no-ai"])
    finally:
        bc.unlink(missing_ok=True)
    geoms = []
    try:
        st, board, dv = load(rid)
        caster, target = uid_by_vis(dv, vis), uid_by_vis(dv, a_unit)
        print("[206/%s] runner=%d caster=u%s target=u%s board=%s spawn c=%s t=%s"
              % (kind, rid, caster, target, board_id, live_pos(rid, caster),
                 live_pos(rid, target)))
        if caster is None or target is None:
            return {"error": "roster absent"}
        keep_c = live_pos(rid, caster)
        geoms, seen = scan_geometries(kind, st, board, caster, target)
        cats = {}
        for g in geoms:
            cats[g[6]] = cats.get(g[6], 0) + 1
        print("[206/%s] couples testes=%d  DISCRIMINANTS (ancien != nouveau)=%d  par etage: %s"
              % (kind, seen, len(geoms), json.dumps(cats, sort_keys=True)))
        # PRIORITE aux cas ou `Tile(7)` tranche (le regime demande), puis proximite aux spawns
        # (moins de tours de drive = moins de derive d'etat).
        rank = {"TILE7": 0, "HORS-POOL": 1, "TILEDIST": 2, "TIEBREAK": 3}
        if only_cat:
            geoms = [g for g in geoms if g[6] == only_cat]
        geoms.sort(key=lambda g: (rank.get(g[6], 9),
                                  hexgeo.distance(keep_c, g[0]) + hexgeo.distance(keep_c, g[1])))
        # DIVERSITE : au plus une geometrie par tuile-cible, sinon les 5 cas joues sont 5 variantes
        # du meme voisinage et ne generalisent rien.
        seen_t, uniq = set(), []
        for g in geoms:
            if tuple(g[1]) in seen_t:
                continue
            seen_t.add(tuple(g[1]))
            uniq.append(g)
        geoms = uniq
        for g in geoms[:limit]:
            print("[206/%s] [%s] caster@%s cible@%s  ANCIEN=%s  NOUVEAU=%s  Tile7seul=%s"
                  % (kind, g[6], g[0], g[1], g[2], g[3], g[4]))
            print("            pool(coord, Tile7, TileDist) = %s" % (g[5],))
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass
    if scan_only or not geoms:
        return {"found": len(geoms)}

    results = []
    for i, g in enumerate(geoms[:cases]):
        cp, tp, cat = g[0], g[1], g[6]
        bc = inject_bc(vis)
        try:
            rid, _sf = build(int(seed) + i, board_id, ["--seed-bc", str(bc), "--p-units", vis,
                                                       "--a-units", a_unit, "--no-ai"])
        finally:
            bc.unlink(missing_ok=True)
        try:
            print("\n=== [206/%s] cas %d/%d [%s] runner=%d ===" % (kind, i + 1, cases, cat, rid))
            r = play_case(rid, kind, cp, tp, a_unit)
            r["cat"] = cat
            r["geom"] = {"caster": cp, "target": tp}
            results.append(r)
        finally:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass
    ok = sum(1 for r in results if r.get("verdict") == "NEW")
    bad = [r for r in results if r.get("verdict") in ("LEGACY", "AUTRE")]
    err = [r for r in results if r.get("error")]
    print("\n[206/%s] BILAN : %d/%d NEW  |  %d contre-exemples  |  %d cas non joues"
          % (kind, ok, len(results), len(bad), len(err)))
    for r in bad + err:
        print("   %s" % json.dumps(r, default=str)[:300])
    return {"ok": ok, "n": len(results), "results": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", choices=tuple(ABILITIES) + ("both",), default="both")
    ap.add_argument("--seed", default="206206")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--a-unit", default="necroWarden")
    ap.add_argument("--cases", type=int, default=5)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--scan-only", action="store_true")
    ap.add_argument("--cat", choices=("TILE7", "TILEDIST", "TIEBREAK", "HORS-POOL"), default=None,
                    help="ne joue QUE les geometries dont la divergence vient de cet etage")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    kinds = tuple(ABILITIES) if a.ability == "both" else (a.ability,)
    for k in kinds:
        run(k, a.seed, a.board, a.a_unit, a.cases, a.scan_only, a.limit, a.keep, a.cat)


if __name__ == "__main__":
    main()
