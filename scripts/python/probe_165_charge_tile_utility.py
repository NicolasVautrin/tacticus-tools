"""probe #165 -- le collapse « tuile la plus PROCHE » vs le tri natif par utilite `Tile(7)`.

Trois ports freres de `HammerOfWrathAbility$$ExecuteBehaviour` collapsaient
`SortTilesByUtility(..., UtilityDefinition(7 = Tile))` en « la tuile la plus proche du caster » :
`SkyStrikeAbility$$ExecuteBehaviour`, `HeroicFusilladeAbility$$ExecuteBehaviour` et
`ForwardSpotterAbility$$PickTiles`. Ce probe sert a (a) TROUVER une geometrie ou les deux regles
DIVERGENT (sinon la validation live ne prouve rien), (b) confronter le port au live.

Modes :
  --scan-boards          : liste les boards dont un ring-1 porte des elevations HETEROGENES
                           (candidats a un scenario discriminant), 100 % offline.
  --plan <board>         : pour un board, liste les tuiles-cibles dont le ring-1 libre DIVERGE
                           entre « plus proche du caster » et « meilleure utilite Tile(7) »,
                           pour chaque position de caster plausible. 100 % offline.

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import board as B
import hexgeo
import rl_collect_batch as R
from engine.entities.pathfinding.board import Board as EngineBoard
from engine.utilities.tile import sort_tiles_by_utility


_STRICT = False        # --strict : ne garder que les divergences ou l'UTILITE departage


def _load_board(board_id: str):
    """Rend (dump, EngineBoard) pour un id de board dumpe (cherche dans les 3 pools)."""
    for kind in ("pvp", "syncPvp", "global"):
        p = R.BOARDS_DIR / kind / ("%s.json" % board_id)
        if p.exists():
            dump = json.loads(p.read_text(encoding="utf-8"))
            return dump, _engine_board(dump)
    raise SystemExit("board introuvable: %s" % board_id)


def _engine_board(dump) -> EngineBoard:
    """`EngineBoard` depuis un dump de board (`board.Tiles` = liste de COLONNES, chacune `{Tile:[...]}`).

    ⚠ Le dump BC ne porte NI ids de tuile NI liste d'adjacence : on synthetise des ids (col*H+row) et
    on derive l'adjacence en `evenq`. C'est suffisant pour REPERER une geometrie discriminante par
    l'ELEVATION ; le tie-break a utilite egale (ordre `neighbours_native`) n'est PAS representatif ici
    -- la confrontation exacte se fait LIVE via le RPC `boardGraph`."""
    cols = dump["board"].get("Tiles") or []
    height = dump["board"].get("Height") or max((len((c or {}).get("Tile") or []) for c in cols),
                                                default=0)
    tiles = []
    for c, col in enumerate(cols):
        for r, t in enumerate((col or {}).get("Tile") or []):
            if t is None:
                continue
            tiles.append({
                "id": c * height + r, "col": c, "row": r,
                "elevation": B._effective_elevation(t.get("TileId"), t.get("Elevation", 0)),
                "walkable": not bool(t.get("ForceUnplayable", False)),
                "tileDefId": t.get("TileId"),
            })
    return EngineBoard(tiles, adjacency="evenq")


def _ring1(board: EngineBoard, tid: int) -> list:
    return list(board.neighbours(tid))       # dump BC : pas de champ `neighbours` -> evenq derive


def scan_boards(limit: int) -> None:
    """Boards dont AU MOINS un ring-1 (marchable) porte >= 2 elevations distinctes."""
    rows = []
    for kind in ("pvp", "syncPvp", "global"):
        d = R.BOARDS_DIR / kind
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            dump = json.loads(p.read_text(encoding="utf-8"))
            try:
                bd = _engine_board(dump)
            except Exception:
                continue
            n_het = 0
            for tid in bd.by_id:
                elevs = {bd.elevation(t) for t in _ring1(bd, tid) if bd.walkable(t)}
                if len(elevs) >= 2:
                    n_het += 1
            if n_het:
                rows.append((dump["id"], kind, n_het, len(bd.by_id)))
    rows.sort(key=lambda r: -r[2])
    for r in rows[:limit]:
        print("id=%-18s kind=%-8s ring1_heterogenes=%-4d tiles=%d" % r)


def plan(board_id: str, max_rows: int) -> None:
    """Couples (caster, cible) ou « plus proche » != « meilleure utilite Tile(7) » sur le ring-1
    LIBRE de la cible. Board vide d'unites : l'occupation reelle ne fera que retirer des candidats,
    donc c'est une borne SUPERIEURE des scenarios discriminants -- a re-verifier en bataille."""
    dump, bd = _load_board(board_id)
    print("board=%s kind=%s tiles=%d" % (dump["id"], dump.get("kind"), len(bd.by_id)))
    found = 0
    for ttile in sorted(bd.by_id):
        ring = [t for t in _ring1(bd, ttile) if bd.walkable(t)]
        if len(ring) < 2:
            continue
        ranked = sort_tiles_by_utility(bd, ring)
        best_util = ranked[0]
        # STRICT : on ne garde que les geometries ou l'utilite DEPARTAGE (elevations distinctes).
        # A utilite EGALE le choix vient de l'ordre du selecteur, non representatif dans ce dump.
        if bd.elevation(best_util) == min(bd.elevation(t) for t in ring):
            continue
        for ctile in sorted(bd.by_id):
            if ctile == ttile or not bd.walkable(ctile):
                continue
            cpos = bd.coord(ctile)
            d = hexgeo.distance(cpos, bd.coord(ttile))
            if d < 2 or d > 4:            # caster non adjacent (sinon pas de move) et pas trop loin
                continue
            near = sorted(ring, key=lambda t: (hexgeo.distance(cpos, bd.coord(t)), t))[0]
            if near == best_util or bd.elevation(near) == bd.elevation(best_util):
                continue
            print("caster@%-8s cible@%-8s d=%d  ring1=%s  PLUS_PROCHE=%s(e%d) UTILITE=%s(e%d)" % (
                cpos, bd.coord(ttile), d,
                [(t, bd.coord(t), bd.elevation(t)) for t in ring],
                bd.coord(near), bd.elevation(near),
                bd.coord(best_util), bd.elevation(best_util)))
            found += 1
            if found >= max_rows:
                return
    if not found:
        print("aucune divergence sur ce board")


def _live_state(rid: int):
    """`State` du runner + le `boardGraph` brut (ids/voisins/elevations NATIFS)."""
    import rl_collect_batch as _R
    from engine.runner.snapshot import load_state
    sid = _R._resolve_session()

    def rpc(method, body, timeout=90):
        r = _R._rpc(sid, method, [body], timeout=timeout)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = EngineBoard(bg["tiles"], adjacency="evenq")
    return load_state(dec, ob, snap, board=board), board


def live_scan(rid: int, caster_id: int, target_id: int, move_range: int, limit: int) -> None:
    """Balaye les positions (caster, cible) du board REEL et liste celles ou le choix de tuile de
    charge DIVERGE entre l'ancien collapse « la plus proche » et le tri natif `Tile(7)`.

    N'ecrit RIEN dans le runner : la position des deux unites est simulee en modifiant le
    `PositionComponent` du `State` charge (copie locale), puis restauree."""
    from engine.runner.abilities.genestealer import (_charge_candidate_tiles, _hf_move_dest_tile,
                                                     SURROUND_RADIUS)
    from engine.runner.components import PositionComponent
    state, board = _live_state(rid)
    ce = state.get_entity(caster_id)
    te = state.get_entity(target_id)
    cpc = ce.get_component(PositionComponent)
    tpc = te.get_component(PositionComponent)
    print("[live] runner=%d caster=u%d@%s target=u%d@%s move_range=%d"
          % (rid, caster_id, (cpc.col, cpc.row), target_id, (tpc.col, tpc.row), move_range))
    found = 0
    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    for ttile in walk:
        tpc.col, tpc.row = board.coord(ttile)
        for ctile in walk:
            if ctile == ttile:
                continue
            cpc.col, cpc.row = board.coord(ctile)
            d = hexgeo.distance((cpc.col, cpc.row), (tpc.col, tpc.row))
            if d < 2 or d > 3:                     # non adjacent (sinon pas de move), reste proche
                continue
            pool = _charge_candidate_tiles(state, caster_id, target_id, SURROUND_RADIUS, move_range)
            if len(pool) < 2:
                continue
            near = sorted(pool, key=lambda t: (hexgeo.distance((cpc.col, cpc.row), board.coord(t)), t))[0]
            best = _hf_move_dest_tile(state, caster_id, target_id, SURROUND_RADIUS, move_range)
            if best is None or board.coord(near) == best:
                continue
            print("caster@%-7s cible@%-7s d=%d pool=%s COLLAPSE=%s(e%d) PORT=%s(e%d)"
                  % ((cpc.col, cpc.row), (tpc.col, tpc.row), d,
                     [(board.coord(t), board.elevation(t)) for t in pool],
                     board.coord(near), board.elevation(near),
                     best, board.elevation(board.id_at(*best))))
            found += 1
            if found >= limit:
                return
    if not found:
        print("aucune divergence atteignable sur ce board avec ce move_range")


def live_show(rid: int, caster_id: int, target_id: int, move_range: int) -> None:
    """Pour les positions COURANTES : pool, choix de l'ancien collapse, choix du port."""
    from engine.runner.abilities.genestealer import (_charge_candidate_tiles, _hf_move_dest_tile,
                                                     SURROUND_RADIUS)
    from engine.runner.components import PositionComponent
    state, board = _live_state(rid)
    cpc = state.get_entity(caster_id).get_component(PositionComponent)
    pool = _charge_candidate_tiles(state, caster_id, target_id, SURROUND_RADIUS, move_range)
    best = _hf_move_dest_tile(state, caster_id, target_id, SURROUND_RADIUS, move_range)
    near = (sorted(pool, key=lambda t: (hexgeo.distance((cpc.col, cpc.row), board.coord(t)), t))[0]
            if pool else None)
    print("caster@%s pool=%s" % ((cpc.col, cpc.row),
                                 [(board.coord(t), board.elevation(t)) for t in pool]))
    print("COLLAPSE(plus proche)=%s   PORT(Tile(7))=%s"
          % (board.coord(near) if near is not None else None, best))


def live_scan_spawn(rid: int, target_id: int, limit: int) -> None:
    """`ForwardSpotterAbility$$PickTiles` : positions de la CIBLE ou l'ancien collapse (1re tuile libre
    dans l'ordre `board.neighbours` = ids TRIES) et le port #165 (`neighbours_native` + tri `Tile(7)`)
    DIVERGENT. Simule la position de la cible sur le `State` charge (aucune ecriture runner)."""
    from engine.runner.abilities.astramilitarum import forward_spotter_pick_tiles
    from engine.runner.components import PositionComponent, UnitComponent
    state, board = _live_state(rid)
    tpc = state.get_entity(target_id).get_component(PositionComponent)
    occ_ids = set()
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ_ids.add(t)
    found = 0
    for ttile in sorted(board.by_id):
        if not board.walkable(ttile):
            continue
        tpc.col, tpc.row = board.coord(ttile)
        occ = (occ_ids - {board.id_at(tpc.col, tpc.row)}) | {ttile}
        old = [t for t in board.neighbours(ttile) if t not in occ and board.walkable(t)]
        new = forward_spotter_pick_tiles(state, target_id, 1)
        if not old or not new or old[0] == new[0]:
            continue
        print("cible@%-7s ring1_libre=%s  COLLAPSE=%s(e%d) PORT=%s(e%d)"
              % (board.coord(ttile),
                 [(board.coord(t), board.elevation(t)) for t in old],
                 board.coord(old[0]), board.elevation(old[0]),
                 board.coord(new[0]), board.elevation(new[0])))
        found += 1
        if found >= limit:
            return
    if not found:
        print("aucune divergence de tuile de spawn sur ce board")


def live_scan_sky(rid: int, caster_id: int, target_id: int, limit: int) -> None:
    """`SkyStrikeAbility$$ExecuteBehaviour` : couples (caster, cible) ou l'ancien collapse (ring-1
    libre `hexgeo.disk`, trie par distance au caster puis id) et le port #165 (`neighbours_native` +
    tri `Tile(7)`) DIVERGENT. Aucune contrainte de reach (Celestine VOLE)."""
    from engine.runner.abilities.sisterhood import _sky_strike_dest_tile
    from engine.runner.components import PositionComponent, UnitComponent
    state, board = _live_state(rid)
    cpc = state.get_entity(caster_id).get_component(PositionComponent)
    tpc = state.get_entity(target_id).get_component(PositionComponent)
    found = 0
    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    for ttile in walk:
        tpc.col, tpc.row = board.coord(ttile)
        for ctile in walk:
            if ctile == ttile:
                continue
            cpc.col, cpc.row = board.coord(ctile)
            occ = {(cpc.col, cpc.row), (tpc.col, tpc.row)}
            old = []
            for (c, r) in hexgeo.disk(tpc.col, tpc.row, 1):
                if (c, r) in occ:
                    continue
                t = board.id_at(c, r)
                if t is None or not board.walkable(t):
                    continue
                old.append(t)
            if len(old) < 2:
                continue
            old.sort(key=lambda t: (hexgeo.distance((cpc.col, cpc.row), board.coord(t)), t))
            new = _sky_strike_dest_tile(state, caster_id, target_id)
            if new is None or board.coord(old[0]) == new:
                continue
            if _STRICT and board.elevation(old[0]) == board.elevation(board.id_at(*new)):
                continue      # egalite d'utilite -> departagee par l'ordre source, pas par le tri
            print("caster@%-7s cible@%-7s ring1=%s COLLAPSE=%s(e%d) PORT=%s(e%d)"
                  % ((cpc.col, cpc.row), (tpc.col, tpc.row),
                     [(board.coord(t), board.elevation(t)) for t in old],
                     board.coord(old[0]), board.elevation(old[0]),
                     new, board.elevation(board.id_at(*new))))
            found += 1
            if found >= limit:
                return
    if not found:
        print("aucune divergence de tuile d'atterrissage sur ce board")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-boards", action="store_true")
    ap.add_argument("--plan", metavar="BOARD_ID")
    ap.add_argument("--live-scan", action="store_true")
    ap.add_argument("--live-scan-spawn", action="store_true")
    ap.add_argument("--live-scan-sky", action="store_true")
    ap.add_argument("--live-show", action="store_true")
    ap.add_argument("--runner", type=int)
    ap.add_argument("--caster", type=int)
    ap.add_argument("--target", type=int)
    ap.add_argument("--move-range", type=int, default=2)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--strict", action="store_true",
                    help="ne garder que les divergences ou l'UTILITE departage (elevations distinctes)")
    a = ap.parse_args()
    global _STRICT
    _STRICT = bool(a.strict)
    if a.scan_boards:
        scan_boards(a.limit)
    elif a.plan:
        plan(a.plan, a.limit)
    elif a.live_scan:
        live_scan(a.runner, a.caster, a.target, a.move_range, a.limit)
    elif a.live_scan_spawn:
        live_scan_spawn(a.runner, a.target, a.limit)
    elif a.live_scan_sky:
        live_scan_sky(a.runner, a.caster, a.target, a.limit)
    elif a.live_show:
        live_show(a.runner, a.caster, a.target, a.move_range)
    else:
        ap.error("--scan-boards | --plan <board> | --live-scan | --live-show")


if __name__ == "__main__":
    main()
