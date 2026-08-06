"""#381-r1 -- le pool du NOEUD DSL `MovableTilesInRange` CONFRONTE a `aiMovableTiles`.

Pourquoi cet oracle est une egalite EXACTE, pas une approximation
----------------------------------------------------------------
Le RPC `aiMovableTiles` appelle **litteralement** `IdunBattle.Core.Services.MovementQuery$$
GetMovableTilesFor(unit, ignoreUnitFlags: false, options)`, et
`MovableTilesInRangeSelector$$Select` appelle `BattleQuery$$GetMovableTilesFor(entity, fromTile,
ignoreFlags, options)`, qui `ToList(fromTile)` puis delegue au MEME slot d'`IMovementQuery`. Les
deux traversent donc `FindAnyOrAllMoveableTiles` -> `AnyOrFillMoveableTiles`, avec le meme
`ignoreUnitsOnTiles = 0`. Toute difference est un ecart de PORT.

Ce que ce test garde, et que rien ne gardait
-------------------------------------------
`test_block_entering_tiles_live.py` (#131) confronte `ai/state_bridge._move_tiles` au meme RPC ;
le NOEUD DSL, lui, appelait le pathfinder SANS aucun des trois etages (filtre d'occupation, gate
d'expansion, dispatch fly) et rendait le `visited` -- un DISQUE. Sur les call-sites du port
(Waaagh, RammingSpeed, BlackRage) l'intersection avec `CanAddUnit(...)` masquait le filtre
d'occupation, mais PAS le gate d'expansion : c'est ainsi que `RammingSpeed` designait sur `C1_74`
une tuile que le natif n'atteint pas (`case-383` sec.5).

Le test est AUTO-DISCRIMINANT : il exige que l'ancien comportement (`ignore_units_on_tiles=True`,
c.-a-d. le `visited`) soit STRICTEMENT plus large sur au moins une unite -- sinon la geometrie ne
prouve rien et le test ECHOUE (jamais un vert vide).

Les unites VOLANTES sont ECARTEES et comptees : leur ecart releve d'un residu DISTINCT et
PREEXISTANT (`#381-r2` -- `FlyPathfinder$$AddNeighbours` itere `GetSurroundingTiles(tile, 1)`,
voisinage GEOMETRIQUE, la ou `BasePathfinder$$AddNeighbours` itere la liste d'adjacence STOCKEE sur
la tuile). Idem pour toute unite dont le pool natif est VIDE (garde FLAG #381, non portee).

ASCII only.
"""
from __future__ import annotations

import pytest

BOARDS = ["MC1_67", "C2_26", "PVP_desert_04"]


def _load(rpc, rid):
    """Etat offline du runner LIVE, AVEC `tiles=tileMeta` : sans ce canal les effets de TUILE ne
    sont pas seedes et le gate #131 retomberait sur le seul repli TERRAIN."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    return load_state(dec, ob, snap, board=board, tiles=tm), board


def _native(rpc, rid, override_range: int) -> dict:
    """`{unitId: set((col,row))}` -- `side='all'` (le noeud DSL n'est pas restreint au joueur
    courant), `overrideRange` = le `Direct(...)` que tous les call-sites lui passent."""
    res = rpc("aiMovableTiles",
              {"runnerId": rid, "side": "all", "overrideRange": int(override_range)}, 120)
    if not isinstance(res, dict) or res.get("ok") is False:
        pytest.skip("aiMovableTiles indisponible")
    return {int(u["unitId"]): {(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                               if t.get("col") is not None}
            for u in (res.get("units") or []) if u.get("unitId") is not None}


def _pool(state, board, uid: int, rng: int, ignore_units_on_tiles: bool = False) -> set:
    from engine.dsl.base import Const
    from engine.entities.selectors.accessors import CasterTile
    from engine.entities.selectors.tiles import Caster, MovableTilesInRange
    from engine.runner.abilities.behaviours.context import entities_from_state
    sel = MovableTilesInRange(Caster(), CasterTile(), Const(int(rng)), ignore_flags=False,
                              ignore_units_on_tiles=ignore_units_on_tiles)
    return {board.coord(t) for t in sel.evaluate(entities_from_state(state, int(uid), int(uid)))}


@pytest.mark.parametrize("board_id", BOARDS)
def test_le_pool_du_noeud_dsl_egale_aiMovableTiles_live(live_session, rpc, build_runner, board_id):
    """Sur CHAQUE unite WALK dont le natif rend un pool non vide : egalite EXACTE."""
    from engine.entities.pathfinding.fly_pathfinder import is_like_flying
    from engine.entities.traits.unit_trait import unit_trait_names
    from engine.runner.abilities.behaviours.context import entities_from_state

    rng = 5
    rid = build_runner("3811", board=board_id)["rid"]
    state, board = _load(rpc, rid)
    nat = _native(rpc, rid, rng)

    walk, flying, empty, bad = [], [], [], []
    wider = 0
    for uid in sorted(nat):
        n = nat[uid]
        if not n:
            empty.append(uid)                    # garde FLAG #381, non portee -> ECARTEE
            continue
        vis = (entities_from_state(state, uid, uid).caster or {}).get("visualId")
        if is_like_flying(unit_trait_names(vis)):
            flying.append(uid)                   # residu #381-r2 -> ECARTEE
            continue
        p = _pool(state, board, uid, rng)
        walk.append(uid)
        if p != n:
            bad.append((uid, vis, sorted(p - n), sorted(n - p)))
        if _pool(state, board, uid, rng, ignore_units_on_tiles=True) > p:
            wider += 1

    print("[381-r1] %s : WALK=%d volantes=%d pool-natif-vide=%d desaccords=%d"
          % (board_id, len(walk), len(flying), len(empty), len(bad)))
    assert walk, ("aucune unite WALK confrontable sur %s -- le bras ne prouve rien" % board_id)
    # AUTO-DISCRIMINANT : l'ancien comportement (`visited`) doit etre STRICTEMENT plus large.
    assert wider, ("l'ancien pool (`visited`) coincide avec le nouveau sur les %d unites de %s -- "
                   "la geometrie ne discrimine pas le correctif" % (len(walk), board_id))
    assert not bad, ("pool DSL != aiMovableTiles : %s"
                     % [(u, v, "en trop=%s" % x, "manque=%s" % m) for u, v, x, m in bad])


def test_le_gate_d_expansion_mord_sur_le_noeud_dsl_live(live_session, rpc, build_runner):
    """Pendant DSL de `test_block_entering_tiles_live` : sur un board a tuiles block-entering, la
    variante SANS le gate #131 sur-atteint STRICTEMENT, et c'est bien le gate qui referme l'ecart.

    On ne DRIVE pas ici : la geometrie de spawn de `MC1_67` suffit (mesure -- 3 unites sur 9 y
    sur-atteignent sans le gate). Si ce n'etait plus le cas, le test ECHOUE au lieu de passer vide."""
    import engine.entities.selectors.tiles as T
    from engine.entities.pathfinding.fly_pathfinder import is_like_flying
    from engine.entities.pathfinding.tile_blocking import tile_blocks_entering
    from engine.entities.traits.unit_trait import unit_trait_names
    from engine.runner.abilities.behaviours.context import entities_from_state

    rng = 5
    rid = build_runner("3811", board="MC1_67")["rid"]
    state, board = _load(rpc, rid)
    blocked = sorted(board.coord(t) for t in board.by_id
                     if tile_blocks_entering(state.effects, t, []))
    assert blocked, "MC1_67 sans tuile block-entering -> ce bras ne peut rien prouver"
    nat = _native(rpc, rid, rng)

    saved = T._movement_can_continue
    over, mismatch = [], []
    try:
        for uid in sorted(nat):
            n = nat[uid]
            if not n:
                continue
            vis = (entities_from_state(state, uid, uid).caster or {}).get("visualId")
            if is_like_flying(unit_trait_names(vis)):
                continue
            gated = _pool(state, board, uid, rng)
            T._movement_can_continue = lambda ctx, brd, traits: None       # gate DESARME
            raw = _pool(state, board, uid, rng)
            T._movement_can_continue = saved
            if raw > gated:
                over.append((uid, sorted(raw - gated)))
            if gated != n:
                mismatch.append(uid)
    finally:
        T._movement_can_continue = saved

    print("[381-r1/gate] block-entering=%s ; unites sur-atteintes sans le gate=%s"
          % (blocked, [u for u, _ in over]))
    assert over, ("le gate #131 ne retire RIEN sur MC1_67 -> il ne serait pas confronte "
                  "(geometrie non discriminante)")
    assert not mismatch, "pool DSL != aiMovableTiles avec le gate arme : %s" % mismatch
