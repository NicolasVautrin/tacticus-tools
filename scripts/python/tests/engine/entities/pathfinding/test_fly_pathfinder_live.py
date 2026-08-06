"""Agrement FLY pathfinding — `engine.entities.pathfinding.fly_pathfinder`
(FlyPathfinder) CONFRONTE au moteur natif LIVE (`aiMovableTiles`).

Contrairement a test_pathfinding_live (qui EXCLUT les unites non-walk), ici on
monte un roster Flying EXPLICITE sur un board a CLIFF (|Delta elev|>=2) et on exige
que `fly_pathfinder.get_movable_positions` == set natif EXACT pour chaque unite
volante. Le board a cliff garantit un cas DISCRIMINANT (fly != walk) : le fly
traverse par-dessus l'elevation la ou le walk est bloque (|Delta elev|<=1).

Property-based / version-independant : lit le board + unites du runner LIVE, aucune
tuile hardcodee. Skip propre si le build echoue (flyers hors pool / board absent).
"""
from __future__ import annotations

import pytest

import gameconfig as GC
from engine.entities.pathfinding.board import Board
from engine.entities.pathfinding.fly_pathfinder import (
    get_movable_positions as fly_gmp, is_like_flying)
from engine.entities.pathfinding.walk_pathfinder import get_movable_positions as walk_gmp

# Flyers spawnables (rank 17) sans deep-strike + board trench a forte elevation.
FLYERS = "blackHaarken,thousAhriman,tyranWingedPrime"
CLIFF_BOARD = "C3_59"


@pytest.fixture(scope="module")
def fly_live(rpc, build_runner):
    rid = build_runner(seed="777", extra=["--p-units", FLYERS, "--board", CLIFF_BOARD])["rid"]
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
    move_by_id = {}
    for u in (snap.get("units") or []):
        st = u.get("stats") or {}
        if u.get("entityId") is not None and st.get("movement") is not None:
            move_by_id[u["entityId"]] = st["movement"]
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


def _is_flying(visual_id) -> bool:
    return is_like_flying((GC.unit(visual_id) or {}).get("traits") or [])


def test_fly_movable_matches_native(fly_live):
    """Chaque unite Flying/Burrow de la bataille live : `fly_pathfinder` == set natif
    EXACT. Garde de DISCRIMINATION : au moins une unite doit avoir fly != walk (sinon
    le board n'exerce pas la difference de vol -> le test ne prouverait rien)."""
    board = Board(fly_live["tiles"], adjacency="evenq")
    n_fly = 0
    n_discriminating = 0
    failures = []
    for unit in fly_live["units"]:
        uid = unit["unitId"]
        vid = unit.get("visualId")
        if not _is_flying(vid):
            continue
        pos = unit["pos"]
        start = board.id_at(pos["col"], pos["row"])
        mr = fly_live["move_by_id"].get(uid, 0) or 0
        if start is None or mr <= 0:
            continue
        native = set()
        for t in unit.get("tiles", []):
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                native.add(tid)
        occ = dict(fly_live["occupants"]); occ.pop(start, None)
        team = fly_live["team_by_id"].get(uid)
        _, fpred = fly_gmp(board, start, mr, occ, team)
        _, wpred = walk_gmp(board, start, mr, occ, team)
        n_fly += 1
        if fpred != wpred:
            n_discriminating += 1
        missing = sorted(board.coord(t) for t in (native - fpred))
        extra = sorted(board.coord(t) for t in (fpred - native))
        if missing or extra:
            failures.append(
                f"u{uid} ({vid}): missing={missing[:8]} extra={extra[:8]} "
                f"(nat={len(native)} fly={len(fpred)} walk={len(wpred)})")
    if n_fly == 0:
        pytest.skip("aucune unite Flying deployee (pool/board)")
    assert not failures, "divergences FLY vs natif:\n  " + "\n  ".join(failures)
    assert n_discriminating > 0, (
        "scenario NON-discriminant : fly==walk pour tous les flyers "
        "(le board n'a pas exerce le vol -> agrement trivial)")
