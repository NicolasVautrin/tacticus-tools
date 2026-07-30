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
    # ⚠ RECTIFICATIF (mesure 2026-07-30, `probe_pathfinding_overreach --audit`) : ce controle negatif
    # tient, mais PAS pour la raison ecrite ici jusqu'a present (<< les Swamp de PVP_desert_04 ne
    # portent AUCUN BlockEnteringUnits, la pose est CONDITIONNELLE >>). Le board DEPLOYE par
    # `--board PVP_desert_04` n'a **aucune** tuile Swamp : son `boardGraph.tileDefId` rend
    # `Unplayable 24 / Grass 21 / Block 14 / DryBush 4`. Les << 10 Swamp >> venaient du DUMP BC
    # (`data/boards/**/PVP_desert_04.json`), pas du live. Le board reste un excellent controle
    # negatif -- zero tuile bloquante -- mais il ne dit RIEN sur une pose conditionnelle.
    # Correlation Swamp(live) <-> BlockEnteringUnits mesuree sur 13 boards : 75/75, zero exception
    # (`probe_pathfinding_overreach.py --audit "MC1_67,C4_09,EMC2_02,PVP_desert_04,C2_26,C2_19,
    # MC1_15,EC2_10,LE2_12,MC1_64,C3_10,Infested_SyncPvp_Arctic_01,C1_02"`), ce qui FONDE le repli
    # terrain de `tile_blocking.TERRAIN_BLOCK_ENTERING`.
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


@pytest.mark.parametrize("board_id", ["MC1_67", "C4_09"])
def test_block_entering_gate_armed_without_tile_channel_live(live_session, rpc, build_runner,
                                                             board_id):
    """Le gate #131 doit mordre AUSSI sur un etat charge SANS `tiles=tileMeta` (residu case-224 SS4).

    Le test ci-dessus hydrate l'etat (`_load` passe `tiles=`), donc il ne pouvait PAS voir le trou :
    `load_state(tiles=...)` est OPT-IN et la quasi-totalite des call-sites ne le passe pas. Sur un
    etat non hydrate, `State.effects` ne porte AUCUN effet de tuile, `make_can_continue` rendait
    `None`, et `_move_tiles` s'etendait DEPUIS une Swamp : UNE tuile de trop, celle qui ne pend que
    d'un Swamp (MC1_67/777 `worldJakhal` (2,3) via la Swamp (1,3), `necroWarden` (3,6) via (4,6) ;
    C4_09/31337 `blackAbaddon` (4,4) via (4,3)).

    La garde : sur un etat NON hydrate, `_move_tiles` == `aiMovableTiles` pour toute unite que le
    natif juge encore mobile. AUTO-DISCRIMINANTE : avec `TERRAIN_BLOCK_ENTERING` vide (l'arbre
    d'AVANT le fix) le meme etat doit sur-atteindre STRICTEMENT -- sinon la geometrie ne prouve rien.
    """
    import engine.entities.pathfinding.tile_blocking as TB
    from engine.ai.state_bridge import _move_tiles
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.snapshot import load_state

    rid = build_runner("777" if board_id == "MC1_67" else "31337",
                       extra=["--p-units", "deathBlightbringer,worldJakhal,blackAbaddon,astraBullgryn",
                              "--a-units", "necroWarden,necroWarden",
                              "--hp-target", "300000", "--hp-player", "300000"],
                       board=board_id)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    mv = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 120)

    # etat NON hydrate : PAS de `tiles=` -- c'est tout l'objet du test.
    state = load_state(dec, ob, snap, board=board)
    assert not any(state.effects.by_unit.get(t) for t in board.by_id), \
        "l'etat ne devait porter AUCUN effet de tuile -> le test ne mesure pas le bon regime"

    def _port(uid):
        e = state.get_entity(uid)
        pc, oc, uc = (e.get_component(PositionComponent), e.get_component(OwnerComponent),
                      e.get_component(UnitComponent))
        return {(t["col"], t["row"])
                for t in _move_tiles(state, int(uid), uc.visual_id, int(oc.team), (pc.col, pc.row))}

    natives = {int(u["unitId"]): {(t["col"], t["row"]) for t in (u.get("tiles") or [])}
               for u in (mv.get("units") or [])}
    natives = {k: v for k, v in natives.items() if v}      # unites encore mobiles seulement
    assert natives, "aiMovableTiles ne rend rien -> rien a confronter"

    saved, over_before = TB.TERRAIN_BLOCK_ENTERING, 0
    try:
        TB.TERRAIN_BLOCK_ENTERING = frozenset()            # l'arbre d'AVANT le fix
        for uid, nat in natives.items():
            over_before += len(_port(uid) - nat)
    finally:
        TB.TERRAIN_BLOCK_ENTERING = saved
    assert over_before > 0, (f"{board_id} : sans le repli terrain le port est deja d'accord avec le "
                             "natif -> scenario NON discriminant, le test ne prouve rien")

    bad = {}
    for uid, nat in natives.items():
        p = _port(uid)
        if p != nat:
            bad[uid] = (sorted(p - nat), sorted(nat - p))
    print(f"[224-SS4] {board_id} etat NON hydrate : {len(natives)} unites, "
          f"sur-atteinte AVANT={over_before} APRES={sum(len(v[0]) for v in bad.values())}")
    assert not bad, f"{board_id} : desaccord sur un etat non hydrate -> {bad}"
