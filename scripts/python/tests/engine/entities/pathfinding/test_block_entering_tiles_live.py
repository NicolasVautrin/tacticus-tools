"""#131 — une tuile `BlockEnteringUnits` (Swamp) est un CUL-DE-SAC de la flood-fill, CONFRONTE au natif.

`IdunBattle.Entities.Pathfinding.BasePathfinder$$NodesInNextLevel` refuse d'etendre la fill depuis une
tuile ou `IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidContinuePathTile` est faux
(= `GetTileBlockingReasons != 0`, bit 0x1 = effet de tuile `BlockEnteringUnitsTileEffect`, EffectType 0,
pose sur les Swamp par `ThornsBlockMovementAbility$$CreateBehaviour`). La tuile reste un STOP legal.

`test_pathfinding_live` ne l'exerce pas : sur les positions de SPAWN, aucun Swamp n'est un point de
passage OBLIGE, donc le sur-atteint du port reste invisible. Ce test DRIVE une unite jusqu'a une
origine ou le Swamp est un goulot, puis exige l'egalite EXACTE avec `aiMovableTiles`.

Le test est AUTO-DISCRIMINANT : il exige aussi que la variante SANS le gate donne un set STRICTEMENT
plus grand — sinon la geometrie ne prouve rien et le test ECHOUE (jamais un vert vide).

Oracle = `aiMovableTiles` (natif `MovementQuery.GetMovableTilesFor`) sur le runner LIVE. ASCII only.
"""
from __future__ import annotations

import pytest

BUILD = ["--roster", "1", "--p-units", "admecMarshall,admecRuststalker",
         "--a-units", "necroWarden,necroWarden"]


def _units(dec):
    return {int(u["id"]): u for u in (dec.get("units") or [])}


def _load(rpc, rid):
    """Etat offline du runner LIVE, AVEC le canal `tiles=tileMeta` (sans lui les effets de TUILE ne
    sont pas seedes et le gate #131 est un no-op silencieux)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    return load_state(dec, ob, snap, board=board, tiles=tm), board, dec


def _blocked(state, board) -> set:
    from engine.entities.pathfinding.tile_blocking import tile_blocks_entering
    return {t for t in board.by_id if tile_blocks_entering(state.effects, t, [])}


def _sets(state, board, uid, vid, team, origin, depth):
    """(set GATE, set SANS gate) des tuiles d'arret, en (col,row)."""
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions
    from engine.entities.pathfinding.tile_blocking import make_can_continue
    from engine.ai.state_bridge import _occupants
    otile = board.id_at(origin[0], origin[1])
    occ = _occupants(state)
    cc = make_can_continue(state.effects, [])
    _v, gated = get_movable_positions(board, otile, depth, occ, team, can_continue=cc)
    _v, raw = get_movable_positions(board, otile, depth, occ, team)
    return ({board.coord(t) for t in gated}, {board.coord(t) for t in raw})


def _native_tiles(rpc, rid, uid):
    mv = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    for e in (mv.get("units") or []):
        if int(e.get("unitId", -1)) == int(uid):
            return {(t["col"], t["row"]) for t in (e.get("tiles") or [])}
    return None


@pytest.mark.parametrize("board_id", ["MC1_67", "C2_26", "PVP_desert_04"])
def test_block_entering_tile_is_a_dead_end_live(live_session, rpc, build_runner, board_id):
    """Une unite WALK conduite a une origine ou un Swamp est un goulot : `_move_tiles` (offline)
    == `aiMovableTiles` (natif) EXACTEMENT, et la variante sans gate est STRICTEMENT plus large.

    TROIS boards (generalisation, geometries de goulot differentes) :
      - `MC1_67`  : l'arene par defaut du harnais, celle ou le rouge de `test_skitarii_turn_live`
                    a ete mesure (4 tuiles block-entering) ;
      - `C2_26`   : 6 tuiles block-entering, le plus gros ecart mesure (portee 3 : natif 29,
                    port SANS gate 33) ;
      - `PVP_desert_04` : CONTROLE NEGATIF — aucune tuile block-entering live, le gate doit rester
                    INERTE (il ne doit RIEN retirer)."""
    from engine.ai.state_bridge import _move_tiles, _move_range, _occupants
    from engine.runner.components import StatsComponent, OwnerComponent, UnitComponent
    from engine.entities.pathfinding.fly_pathfinder import is_like_flying

    rid = build_runner("777", extra=BUILD, board=board_id)["rid"]
    state, board, dec = _load(rpc, rid)
    blocked = _blocked(state, board)

    # unite WALK controlee, avec un Movement > 0
    me = None
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent); sc = e.get_component(StatsComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or sc is None or oc is None or not uc.alive:
            continue
        u = _units(dec).get(eid) or {}
        if not u.get("ctrl"):
            continue
        traits = sc.ctx.traits or []
        if is_like_flying(traits):
            continue
        d = _move_range(sc.ctx, uc.visual_id)
        if d > 0:
            me = (eid, uc.visual_id, oc.team, d)
            break
    if me is None:
        pytest.skip("aucune unite WALK controlee avec Movement>0")
    uid, vid, team, depth = me

    # --- CONTROLE NEGATIF : aucun effet block-entering sur ce board -> le gate doit etre INERTE.
    # Mesure 2026-07-27 : les Swamp de `PVP_desert_04` (10 tuiles, elevation 4) ne portent AUCUN
    # `BlockEnteringUnits`, la ou ceux de `MC1_67` (elevations 1-2) en portent — la pose est
    # CONDITIONNELLE (`SwampBlockMovement`, condition non RE'd). C'est exactement ce qui interdit de
    # gater sur le TERRAIN (`tileDefId == 'Swamp'`) : ce serait un sur-blocage ici.
    if not blocked:
        from collections import Counter
        census = Counter(board.tile_def_id(t) for t in board.by_id)
        nat0 = _native_tiles(rpc, rid, uid)
        if not nat0:
            pytest.skip("aiMovableTiles vide pour cette unite (pas d'action ?)")
        p0 = _units(dec)[int(uid)]["pos"]
        port0 = {(t["col"], t["row"])
                 for t in _move_tiles(state, uid, vid, team, (p0["col"], p0["row"]))}
        print(f"[131-neg] {board_id} terrain={dict(census)} aucun effet block-entering ; "
              f"natif n={len(nat0)} port n={len(port0)}")
        assert port0 == nat0, (f"gate SUR-BLOQUANT sur {board_id} : port-only={sorted(port0 - nat0)} "
                               f"natif-only={sorted(nat0 - port0)}")
        return

    # ORIGINE DISCRIMINANTE : une tuile libre d'ou le gate CHANGE le set atteignable.
    occ = _occupants(state)
    spot = None
    for tid in sorted(board.by_id):
        if tid in occ or not board.walkable(tid):
            continue
        g, r = _sets(state, board, uid, vid, team, board.coord(tid), depth)
        if g != r:
            spot = board.coord(tid)
            break
    if spot is None:
        pytest.skip("aucune origine ou le gate #131 change quelque chose sur ce board")

    r = rpc("applyAction", {"runnerId": rid,
                            "action": {"kind": "move", "unitId": int(uid),
                                       "to": {"col": int(spot[0]), "row": int(spot[1])}}}, 90)
    assert r.get("ok"), f"drive de u{uid} vers {spot} refuse : {str(r)[:200]}"
    for _ in range(2):                      # rendre son action a l'unite (flags de tour remis a zero)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)

    state, board, dec = _load(rpc, rid)
    u = _units(dec)[int(uid)]
    assert (u["pos"]["col"], u["pos"]["row"]) == spot, "l'unite n'est pas a l'origine voulue"
    assert u.get("hasAction"), "l'unite n'a pas retrouve son action -> aiMovableTiles serait vide"

    nat = _native_tiles(rpc, rid, uid)
    assert nat, "aiMovableTiles ne rend rien pour cette unite"
    port = {(t["col"], t["row"]) for t in _move_tiles(state, uid, vid, team, spot)}
    gated, raw = _sets(state, board, uid, vid, team, spot, depth)

    print(f"[131] u{uid} {vid} @{spot} depth={depth} blocked={sorted(board.coord(t) for t in blocked)}")
    print(f"[131] natif n={len(nat)} port n={len(port)} sans-gate n={len(raw)} "
          f"| port-only={sorted(port - nat)} natif-only={sorted(nat - port)}")

    # 1. le scenario est DISCRIMINANT : sans le gate, le port sur-atteint.
    assert raw - gated, "geometrie NON discriminante (le gate ne retire rien) -> le test ne prouve rien"
    assert raw - nat, "sans le gate le port serait deja d'accord avec le natif -> scenario inutile"
    # 2. avec le gate : EGALITE EXACTE avec le natif.
    assert port == nat, (f"movable set != natif : port-only={sorted(port - nat)} "
                         f"natif-only={sorted(nat - port)}")
