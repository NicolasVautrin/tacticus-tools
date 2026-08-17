"""PROBE case-205 -- QUEL SUJET le call-site SUMMON de `SortTilesByUtility` met-il dans le
`UtilityMovementCase` ?

`IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtilityForSummon` fixe le selecteur d'unites a un
`IdunBattle.Entities.Selectors.AllAliveMachinesSelector`. Le residu case-165b en deduisait « un
ENSEMBLE d'unites » et laissait les feuilles gatees sur l'unite muettes. Le decompile dit autre
chose : `dc.unit` est un IEntity SINGULIER et il vaut **null** (le selecteur est construit avec un
provider NUL ; `IdunBattle.AI.Utilities.UtilityMovementCase` porte `get_IsSpawning` =
`unit == null && parent != null` et `get_UnitOrParent` = `unit ?? parent`).

Trois hypotheses concurrentes, et une seule est observable-discriminante LIVE :

  H_NULL   `case.unit = null`                 -> la feuille `TriggeredAbilities(2)` rend 0
                                                 (`if (case.unit != null) { ... }` du natif).
  H_PARENT `case.unit = le summoner`          -> feuille 2 = les playbooks du SUMMONER.
  H_FIRST  `case.unit = 1re machine vivante`  -> feuille 2 = les playbooks de CETTE unite.

H_PARENT est deja REFUTE au decompile : `CapturePointTileUtility.<d__3>` et
`PowerUpTileUtility.<d__2>` testent `case.unit == null` PUIS `case.parent != null` -- un test mort
si `unit` valait le parent. Reste a REFUTER H_FIRST live, et c'est ce que ce probe fait.

MONTAGE (le sujet doit CHANGER le classement, sinon la mesure est tautologique) :
  * summoner  = `admecMarshall` (Tan Gi'da). Son passif (1200) n'est dans AUCUN playbook de
    mouvement porte -> sous H_PARENT la feuille 2 rend 0, donc H_PARENT et H_NULL COINCIDENT ici ;
  * temoin    = `templAncient`, porteur d'`AstartesBanner` (1106) = `5 x |amis dans le disque r=2
    autour de la tuile candidate, self inclus|`. Sous H_FIRST ce terme s'applique et RENVERSE le
    classement d'`ElevationUtility` (10/niveau) des que la geometrie s'y prete ;
  * on cherche OFFLINE une geometrie ou `H_NULL != H_FIRST`, on la DRIVE live, on declenche
    l'attaque normale de Tan (le passif `ControlEdict` spawne 1 `admecSmnVanguard` par
    `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(caster)), 7, caster), 1)`), et on
    lit la tuile ou le natif POSE le Vanguard.

Le probe exige EN PLUS que le terme de TUILE VARIE dans le pool (elevations et/ou terrains
distincts) : sur plateau plat le composite est constant et TOUT collapse a l'air juste.

Usage :  python probe_205_summon_tile_subject.py [--seed 777] [--board MC1_67] [--cases 2]
                                                 [--scan-only]
Depuis scripts/python. ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

CASTER_VIS = "admecMarshall"      # summoner : ControlEdict -> admecSmnVanguard
BANNER_VIS = "templAncient"       # temoin : AstartesBanner (1106), playbook de mouvement PORTE
FILLER_VIS = "ultraTitus"         # amis supplementaires -> le compte du banner VARIE selon la tuile
ENEMY_VIS = "necroDestroyer"


class Rpc:
    """Meme voie que la conftest : `rl_collect_batch._rpc(sid, method, [body], timeout_s)`."""

    def __init__(self):
        import rl_collect_batch as R
        self.R = R
        self.sid = R._resolve_session()

    def __call__(self, method, args=None, timeout=60):
        out = self.R._rpc(self.sid, method, [args] if args is not None else [], timeout=timeout)
        return out.get("result") if isinstance(out, dict) and "result" in out else out


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def build(seed, board, state_file):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--roster", "1",
           "--p-units", ",".join((CASTER_VIS, BANNER_VIS, FILLER_VIS)),
           "--a-units", ENEMY_VIS, "--no-ai",
           "--hp-target", "90000", "--hp-player", "90000"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-800:])
        return None
    return json.loads(state_file.read_text())["runnerId"]


# ------------------------------------------------------------------ classements concurrents

def _rank(state, pool, **kw):
    from engine.utilities.tile import sort_tiles_by_utility
    return sort_tiles_by_utility(state, list(pool), **kw)


def _pool(state, caster_id):
    """`CanAddUnit(AdjacentTiles(caster@0x148))` dans l'ORDRE NATIF -- le pool exact du noeud."""
    from engine.runner.operations.spawn import _free_tiles_adjacent
    return _free_tiles_adjacent(state, caster_id, set(), native_order=True)


def _tile_term_varies(board, pool) -> bool:
    """Le terme de TUILE discrimine-t-il ? (elevations OU terrains distincts sur le pool)."""
    elevs = {(board.by_id.get(t) or {}).get("elevation") for t in pool}
    terrs = {board.tile_def_id(t) for t in pool}
    return len(elevs) > 1 or len(terrs) > 1


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is None:
        return False
    pc.col, pc.row = col, row
    return True


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _strict_head(state, pool, **kw) -> bool:
    """La TETE du classement est-elle STRICTEMENT meilleure ? Sinon c'est l'ordre du selecteur source
    (tri stable) qui tranche, et le montage ne teste plus le TERME DE TUILE."""
    from engine.utilities.tile import (TILE_UTILITY, runner_tile_leaf_ctx, terrain_tile_effects)
    from engine.weights import load as load_w
    wt = load_w()
    board = state.board
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    fx = getattr(state, "effects", None)
    ctx = runner_tile_leaf_ctx(state, kw.get("unit_id"), kw.get("parent_id"))
    vals = []
    for t in pool:
        info = board.by_id.get(t) or {}
        effs = [e.name for e in (fx.by_unit.get(int(t), []) if fx else []) if not e.consumed and e.name]
        effs += terrain_tile_effects(board.tile_def_id(t), effs)
        vals.append(TILE_UTILITY.evaluate(board.coord(t), {
            "elevation": info.get("elevation"), "elevation_max": emax, "elevation_min": emin,
            "effects": effs}, ctx, wt))
    top = max(vals)
    return sum(1 for v in vals if v == top) == 1


def scan(state, board, cid, banner_uid, enemy_uid, others, limit, strict=False):
    """Geometries (tuile Tan, tuile temoin, tuile CIBLE) ou H_NULL et H_FIRST DIVERGENT et ou le
    terme de tuile varie. `strict` exige EN PLUS que la tete H_NULL soit STRICTEMENT meilleure --
    sinon le montage ne teste que l'ordre du selecteur source.

    ⚠ La CIBLE fait PARTIE de la geometrie : elle doit etre ADJACENTE au caster (pour que l'attaque
    normale porte), donc elle OCCUPE une tuile du pool `CanAddUnit(AdjacentTiles(caster))` et
    l'ampute. Une premiere version scannait sans elle et perdait la discrimination au drive (mesure :
    2 montages sur 2 rendus tautologiques). Le pool evalue ici est donc le pool RESIDUEL.

    Simulation OFFLINE des positions (aucune ecriture runner)."""
    import hexgeo
    keep = {u: _pos(state, u) for u in [cid, banner_uid, enemy_uid] + list(others)}
    found = []
    tiles = [t for t in sorted(board.by_id) if board.walkable(t)]
    for C in tiles:
        cpos = board.coord(C)
        if not _set_pos(state, cid, *cpos):
            continue
        ring = [t for t in board.neighbours_native(C) if board.walkable(t)]
        if len(ring) < 4:                    # cible + >= 3 candidates residuelles
            continue
        for T in tiles:
            tpos = board.coord(T)
            if tpos == cpos or hexgeo.distance(tpos, cpos) > 3:
                continue
            if not _set_pos(state, banner_uid, *tpos):
                continue
            for E in ring:
                epos = board.coord(E)
                if epos in (cpos, tpos):
                    continue
                if not _set_pos(state, enemy_uid, *epos):
                    continue
                pool = _pool(state, cid)          # pool RESIDUEL (cible + temoin exclus)
                if len(pool) < 2 or not _tile_term_varies(board, pool):
                    continue
                h_null = _rank(state, pool, parent_id=cid)
                h_first = _rank(state, pool, unit_id=banner_uid)
                if h_null[0] == h_first[0]:
                    continue
                if strict and not _strict_head(state, pool, parent_id=cid):
                    continue
                found.append({"caster": cpos, "banner": tpos, "enemy": epos,
                              "pool": list(pool), "h_null": h_null[0], "h_first": h_first[0]})
                break
            if found and found[-1]["caster"] == cpos:
                break
        if len(found) >= limit:
            break
    for u, p in keep.items():                       # restaure l'etat offline
        if p:
            _set_pos(state, u, *p)
    return found


def decompose(state, board, cid, banner_uid, pool):
    """Utilite par tuile sous chaque hypothese + terme de tuile (elevation/terrain) -- pour dire
    QUEL etage tranche, jamais un scalaire global."""
    from engine.utilities.tile import (TILE_UTILITY, runner_tile_leaf_ctx, terrain_tile_effects)
    from engine.weights import load as load_w
    wt = load_w()
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    fx = getattr(state, "effects", None)
    ctx_null = runner_tile_leaf_ctx(state, None, cid)
    ctx_first = runner_tile_leaf_ctx(state, banner_uid)
    rows = []
    for t in pool:
        info = board.by_id.get(t) or {}
        terr = board.tile_def_id(t)
        effs = [e.name for e in (fx.by_unit.get(int(t), []) if fx else []) if not e.consumed and e.name]
        effs += terrain_tile_effects(terr, effs)
        meta = {"elevation": info.get("elevation"), "elevation_max": emax, "elevation_min": emin,
                "effects": effs}
        p = board.coord(t)
        rows.append((t, p, info.get("elevation"), terr,
                     TILE_UTILITY.evaluate(p, meta, ctx_null, wt),
                     TILE_UTILITY.evaluate(p, meta, ctx_first, wt)))
    return rows


# ------------------------------------------------------------------ scenario live

def run_case(rpc, rid, board, geom, verbose=True):
    """Drive la geometrie live, declenche l'attaque de Tan, rend la tuile de spawn NATIVE."""
    def dview():
        return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

    def uid_of(dv, vis, mine=True):
        me = dv.get("currentPlayer")
        for u in (dv.get("units") or []):
            if u.get("visualId") == vis and u.get("alive"):
                if mine and u.get("owner") == me:
                    return u["id"]
                if not mine and u.get("owner") != me:
                    return u["id"]
        return None

    dv = dview()
    cid = uid_of(dv, CASTER_VIS)
    bid = uid_of(dv, BANNER_VIS)
    eid = uid_of(dv, ENEMY_VIS, mine=False)
    if cid is None or bid is None or eid is None:
        print("unites introuvables (cid=%s bid=%s eid=%s)" % (cid, bid, eid))
        return None

    # Les TROIS positions viennent du scan : la cible fait partie de la geometrie (elle ampute le
    # pool, cf. `scan`). Ordre : temoin, cible, caster -- le caster en dernier pour ne pas se faire
    # deloger, et la cible avant lui pour liberer sa tuile d'origine si besoin.
    for uid, p in ((bid, geom["banner"]), (eid, geom["enemy"]), (cid, geom["caster"])):
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
        if not _ok(r):
            print("move KO u%s -> %s : %s" % (uid, p, str(r)[:200]))
            return None

    dv = dview()
    me = next((u for u in (dv.get("units") or []) if u["id"] == cid), None)
    ab = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    if ab is None:
        print("attaque normale introuvable")
        return None
    before = {u["id"] for u in (dv.get("units") or [])}
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ab.get("id")},
        "captureEvents": True}, 150)
    if not _ok(cast):
        print("cast KO : %s" % str(cast)[:300])
        return None
    dv2 = dview()
    new = [u for u in (dv2.get("units") or []) if u["id"] not in before and u.get("pos")]
    if not new:
        print("aucun spawn observe")
        return None
    sp = new[0]
    tile = board.id_at(sp["pos"]["col"], sp["pos"]["row"])
    if verbose:
        print("  LIVE : spawn %s en %s (t%s)"
              % (sp.get("visualId"), (sp["pos"]["col"], sp["pos"]["row"]), tile))
    return {"tile": tile, "cid": cid, "bid": bid, "eid": eid, "dv": dv, "ob": ob, "snap": snap}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--boards", default="MC1_67",
                    help="liste de boards separes par des virgules -- UN montage par board")
    ap.add_argument("--geom", type=int, default=0, help="index de la geometrie retenue par le scan")
    ap.add_argument("--strict", action="store_true",
                    help="exiger une tete H_NULL STRICTEMENT meilleure (le terme de tuile tranche)")
    ap.add_argument("--scan-only", action="store_true")
    a = ap.parse_args()

    rpc = Rpc()
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state

    boards = [b.strip() for b in a.boards.split(",") if b.strip()]
    results = []
    for i, bname in enumerate(boards):
        sf = ROOT / "logs" / "runners" / ("probe205-%d-%s.json" % (i, uuid.uuid4().hex[:8]))
        sf.parent.mkdir(parents=True, exist_ok=True)
        rid = build(a.seed + i, bname, sf)
        if rid is None:
            return 1
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="native_sym")
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            st = load_state(dv, ob, snap, board=board)
            mine = dv.get("currentPlayer")
            ids = {u.get("visualId"): u["id"] for u in (dv.get("units") or [])
                   if u.get("alive") and u.get("owner") == mine}
            cid, bid = ids.get(CASTER_VIS), ids.get(BANNER_VIS)
            eid = next((u["id"] for u in (dv.get("units") or [])
                        if u.get("alive") and u.get("owner") != mine
                        and u.get("visualId") == ENEMY_VIS), None)
            others = [v for k, v in ids.items() if v not in (cid, bid)]
            if cid is None or bid is None or eid is None:
                print("roster incomplet : %s / enemy=%s" % (sorted(ids), eid))
                return 1
            geoms = scan(st, board, cid, bid, eid, others, limit=a.geom + 1, strict=a.strict)
            if len(geoms) <= a.geom:
                print("[case %d] aucune geometrie discriminante sur %s/%d (strict=%s)"
                      % (i, bname, a.seed + i, a.strict))
                continue
            g = geoms[a.geom]
            print("\n=== CASE %d (board=%s seed=%d) ===" % (i, bname, a.seed + i))
            print("  Tan -> %s ; templAncient -> %s ; cible -> %s"
                  % (g["caster"], g["banner"], g["enemy"]))
            print("  H_NULL (port livre, case.unit=null) -> t%s %s"
                  % (g["h_null"], board.coord(g["h_null"])))
            print("  H_FIRST (case.unit=templAncient)    -> t%s %s"
                  % (g["h_first"], board.coord(g["h_first"])))
            if a.scan_only:
                results.append({"case": i, "geom": g, "live": None})
                continue
            live = run_case(rpc, rid, board, g)
            if live is None:
                continue
            # Le pool REEL post-drive (la cible occupe une voisine) : on recalcule les deux
            # classements sur l'etat live d'AVANT le cast, jamais sur une valeur gelee.
            st2 = load_state(live["dv"], live["ob"], live["snap"], board=board)
            pool2 = _pool(st2, live["cid"])
            h_null = _rank(st2, pool2, parent_id=live["cid"])[0]
            h_first = _rank(st2, pool2, unit_id=live["bid"])[0]
            h_parent = _rank(st2, pool2, unit_id=live["cid"])[0]
            print("  pool reel (ordre natif) : %s" % [(t, board.coord(t)) for t in pool2])
            for row in decompose(st2, board, live["cid"], live["bid"], pool2):
                print("    t%-4s %-7s elev=%-3s %-10s u_NULL=%7.1f  u_FIRST=%7.1f"
                      % (row[0], row[1], row[2], row[3], row[4], row[5]))
            print("  H_NULL=t%s  H_PARENT=t%s  H_FIRST=t%s  ||  NATIF=t%s"
                  % (h_null, h_parent, h_first, live["tile"]))
            verdict = ("H_NULL OK" if h_null == live["tile"] else "H_NULL KO")
            if h_first == h_null:
                verdict += " (montage NON discriminant apres drive)"
            else:
                verdict += (" / H_FIRST REFUTE" if h_first != live["tile"] else " / H_FIRST CONFIRME")
            print("  VERDICT : %s" % verdict)
            results.append({"case": i, "h_null": h_null, "h_first": h_first,
                            "h_parent": h_parent, "native": live["tile"]})
        finally:
            rpc("disposeRunner", {"runnerId": rid}, 60)
    print("\n--- SYNTHESE ---")
    for r in results:
        if r.get("native") is None:
            continue
        print("  case %d : natif=t%-4s H_NULL=t%-4s %s ; H_FIRST=t%-4s %s"
              % (r["case"], r["native"], r["h_null"],
                 "OK" if r["h_null"] == r["native"] else "MISMATCH",
                 r["h_first"], "refute" if r["h_first"] != r["native"] else "CONFIRME"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
