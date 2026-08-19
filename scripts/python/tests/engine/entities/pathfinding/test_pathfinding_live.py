"""Agrément pathfinding — `engine.entities.pathfinding` (WalkPathfinder) CONFRONTÉ
au moteur natif LIVE (`aiMovableTiles` = MovementQuery.GetMovableTilesFor, et
`boardGraph` = adjacence native).

Property-based, indépendant version/seed :
  • on lit le board + les unités du runner LIVE (aucune valeur hardcodée),
  • pour CHAQUE unité WALK on exige `get_movable_positions` == set natif, EXACT,
  • les unités NON-WALK (Fly/Teleport : portée native > stat Movement) sont
    détectées et exclues (exception connue, pas un échec).

Aucun snapshot gelé : l'oracle est le natif en cours d'exécution. Skip si pas de
session (cf. conftest : live_session amorce-si-besoin, live_runner reuse-or-build).
"""
from __future__ import annotations

import pytest

from engine.entities.pathfinding.board import Board
from engine.entities.pathfinding.walk_pathfinder import get_movable_positions, get_reachable_levels

MODES = ["native", "native_sym", "evenq"]


# --- capture LIVE partagée (une bataille, plusieurs assertions) ----------- #

@pytest.fixture(scope="session")
def live_board(rpc, live_runner):
    """Snapshot LIVE des 4 vues nécessaires + index dérivés (occupants/team/portée)."""
    rid = live_runner
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    amt = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (isinstance(bg, dict) and bg.get("ok")):
        pytest.skip(f"boardGraph KO: {str(bg)[:200]}")
    if not (isinstance(amt, dict) and amt.get("ok")):
        pytest.skip(f"aiMovableTiles KO: {str(amt)[:200]}")

    tiles = bg["tiles"]
    team_by_id = {u["id"]: u.get("team") for u in (dv.get("units") or [])}
    # portée RÉELLE = stat Movement (combatSnapshot, keyé par entityId == unitId)
    move_by_id = {}
    for u in (snap.get("units") or []):
        st = u.get("stats") or {}
        if u.get("entityId") is not None and st.get("movement") is not None:
            move_by_id[u["entityId"]] = st["movement"]
    # occupants : tile_id -> team (boardGraph.occupantUnitId via UnitFoot ;
    # fallback positions decisionView si vieux hook sans capture occupancy)
    occupants = {}
    if any("occupantUnitId" in t for t in tiles):
        for t in tiles:
            oid = t.get("occupantUnitId")
            if oid is not None:
                occupants[t["id"]] = team_by_id.get(oid)
    else:
        b0 = Board(tiles, adjacency="native_sym")
        for u in (dv.get("units") or []):
            p = u.get("pos") or {}
            tid = b0.id_at(p.get("col"), p.get("row"))
            if u.get("alive") and tid is not None:
                occupants[tid] = u.get("team")
    return {"tiles": tiles, "units": amt["units"], "occupants": occupants,
            "team_by_id": team_by_id, "move_by_id": move_by_id}


# --- comparaison pure d'une unité ----------------------------------------- #

def _native_set(board, unit):
    out = set()
    for t in unit.get("tiles", []):
        tid = board.id_at(t["col"], t["row"])
        if tid is not None:
            out.add(tid)
    return out


def _is_non_walk(board, start, native, occ, team, move_range):
    """NON-WALK = le natif atteint des tuiles à plus de `move_range` pas de marche
    (Fly/Teleport/bonus de portée) → le modèle Walk ne s'applique pas."""
    levels = get_reachable_levels(board, start, occ, team, max_depth=None)
    return max((levels.get(t, 999) for t in native), default=0) > move_range


def _diff(board, unit, occupants, team, move_range):
    pos = unit["pos"]
    start = board.id_at(pos["col"], pos["row"])
    native = _native_set(board, unit)
    occ = dict(occupants)
    occ.pop(start, None)
    if _is_non_walk(board, start, native, occ, team, move_range):
        return None                                   # non-Walk → exclue
    _, pred = get_movable_positions(board, start, move_range, occ, team)
    return {
        "missing": sorted(board.coord(t) for t in (native - pred)),  # natif a, pas nous
        "extra": sorted(board.coord(t) for t in (pred - native)),    # nous a, pas natif
        "nNative": len(native), "nPred": len(pred), "start": start is not None,
    }


# --- tests d'agrément ----------------------------------------------------- #

def test_walk_movable_matches_native(live_board):
    """Cœur : sur la bataille LIVE, chaque unité WALK reproduite à l'IDENTIQUE
    (adjacence even-q, la fidèle). Indépendant du seed (boucle sur toutes les
    unités) et de la version (lit le board live)."""
    board = Board(live_board["tiles"], adjacency="evenq")
    walk = 0
    failures = []
    for unit in live_board["units"]:
        uid = unit["unitId"]
        team = live_board["team_by_id"].get(uid)
        mr = live_board["move_by_id"].get(uid, 0)
        r = _diff(board, unit, live_board["occupants"], team, mr)
        if r is None:                                 # non-Walk exclue
            continue
        walk += 1
        if r["missing"] or r["extra"]:
            failures.append(
                f"u{uid} ({unit.get('visualId')}): "
                f"missing={r['missing'][:8]} extra={r['extra'][:8]} "
                f"(nat={r['nNative']} pred={r['nPred']})")
    assert walk > 0, "aucune unité WALK à valider dans la bataille live"
    assert not failures, "divergences pathfinding vs natif:\n  " + "\n  ".join(failures)


def test_evenq_is_the_faithful_adjacency(live_board):
    """even-q doit être AU MOINS aussi fidèle que les modes natifs bruts : son
    nombre d'unités WALK exactes >= celui des autres modes. Documente le choix
    d'adjacence en le confrontant au live."""
    score = {}
    for mode in MODES:
        board = Board(live_board["tiles"], adjacency=mode)
        exact = walk = 0
        for unit in live_board["units"]:
            uid = unit["unitId"]
            r = _diff(board, unit, live_board["occupants"],
                      live_board["team_by_id"].get(uid),
                      live_board["move_by_id"].get(uid, 0))
            if r is None:
                continue
            walk += 1
            exact += int(not r["missing"] and not r["extra"])
        score[mode] = (exact, walk)
    ev_exact = score["evenq"][0]
    assert ev_exact >= score["native"][0], f"evenq pas plus fidèle que native: {score}"
    assert ev_exact >= score["native_sym"][0], f"evenq < native_sym: {score}"


def test_evenq_adjacency_matches_native_on_full_tiles(live_board):
    """La convention even-q est DÉRIVÉE des tuiles natives à 6 voisins : on la
    re-confronte au live. Sur toute tuile où le natif donne 6 voisins (complète,
    non-bord), le set even-q doit être IDENTIQUE au set natif."""
    tiles = live_board["tiles"]
    native_adj = {t["id"]: set(n for n in t.get("neighbours", [])) for t in tiles}
    evenq = Board(tiles, adjacency="evenq")
    checked = 0
    for t in tiles:
        nat = native_adj[t["id"]]
        if len(nat) != 6:                             # seulement les tuiles complètes
            continue
        checked += 1
        assert set(evenq.neighbours(t["id"])) == nat, (
            f"tuile {t['col']},{t['row']}: evenq != natif "
            f"(evenq={sorted(evenq.coord(x) for x in evenq.neighbours(t['id']))} "
            f"nat={sorted(evenq.coord(x) for x in nat)})")
    if checked == 0:
        pytest.skip("aucune tuile native à 6 voisins dans cette bataille")
