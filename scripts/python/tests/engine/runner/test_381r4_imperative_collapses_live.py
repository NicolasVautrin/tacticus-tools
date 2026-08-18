"""#381-r4 LIVE -- le foyer des collapses imperatifs confronte au JEU.

DEUX FACES, et la seconde est celle qui compte pour une ability
---------------------------------------------------------------
1. LE FOYER, NU. `services/movement_query.get_movable_tiles_for` (que
   `abilities/genestealer._charge_candidate_tiles` et
   `operations/triggers/loki/betrayer._betrayer_stop_tile` appellent depuis `#381-r4`) est le
   mirror de `IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor`. Le RPC `aiMovableTiles`
   appelle LITTERALEMENT cette fonction native : l'egalite attendue est donc EXACTE, unite par
   unite, pas une approximation.

2. L'ATTERRISSAGE. `VigilanceEternalAbility$$ExecuteBehaviour` pose Tyrith sur
   `First(SortTilesByUtility(GetPossibleMovementTiles, 0x20))`. Sur une geometrie ou le gate
   d'expansion #131 CHANGE le pool, le port GATE et le port NON GATE designent deux tuiles
   differentes -- et c'est le jeu qui tranche.

Les deux tests sont AUTO-DISCRIMINANTS : ils exigent que la variante NON gatee (l'etat d'AVANT
`#381-r4`) DIVERGE, sinon la geometrie ne prouve rien et le test ECHOUE.

Board : `C2_26` -- 6 tuiles `Swamp` (block-entering), deja utilise par la confrontation `#381-r1`.
ASCII only.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

import hexgeo

BOARD = "C2_26"
TYRITH_VIS = "custoKyrus"
FOE_VIS = "necroWarden"
VIG_ABILITY = 1202
MOVE_RANGE = 2
BUILD = ["--p-units", TYRITH_VIS, "--a-units", FOE_VIS, "--no-ai"]
BUILD_POOL = ["--no-ai"]             # roster COMPLET du seed : autant d'unites confrontees
PROBE_RANGE = 2                      # meme portee que la charge -- c'est la ou le gate mord


@contextmanager
def _no_gate():
    """L'etat d'AVANT `#381-r4` : gate d'expansion #131 desarme.

    ⚠ CE CONTRE-TEMOIN A ETE MUET 13 JOURS (#10031), et le fichier a rougi sur un message qui
    accusait la GEOMETRIE. La redaction d'origine disait « le foyer resout `make_can_continue` a
    CHAQUE appel (import fonction-local) -> patcher le module suffit » : vrai jusqu'a `492c722f`
    (« hisser 624 imports differes d'engine/ au niveau module »), qui a passe ce nom en FORME A dans
    `engine/services/movement_query.py`. Des lors le patch n'atteignait plus le foyer, `raw` valait
    toujours `gate`, `_pick_geometry` ne trouvait plus AUCUN couple discriminant, et le test
    echouait sur « aucune geometrie ou le gate #131 change l'atterrissage sur C2_26 -- le test ne
    prouverait rien ». L'auto-controle disait donc VRAI ; ce qu'il ne pouvait pas dire, c'est que la
    cause etait l'INSTRUMENT et non le board. Le foyer est repasse en FORME B, et la morsure est
    desormais VERIFIEE ici meme -- une contre-epreuve muette est pire qu'absente.

    La verification est BORNEE au foyer que ce fichier exerce : `engine.ai.state_bridge` fige lui
    aussi `make_can_continue` en forme A, mais aucun des deux tests d'ici ne traverse ce chemin
    (residu #10031-r1). La vue large est le role de
    `tests/engine/services/test_10031_morsure_des_mutations_offline.py`."""
    from engine.entities.pathfinding import tile_blocking as TB
    from morsure_substitution import liaisons_figees
    saved = TB.make_can_continue
    TB.make_can_continue = lambda *a, **k: None
    try:
        figees = liaisons_figees("engine.entities.pathfinding.tile_blocking", "make_can_continue",
                                 saved, consommateurs_seuls=True,
                                 prefixe="engine.services.movement_query")
        assert not figees, ("le desarmement du gate ne mord pas : %s a(ont) fige `make_can_continue` "
                            "en forme A -- ce fichier mesurerait `raw == gate` partout et "
                            "accuserait la geometrie (#10031)" % sorted(figees))
        yield
    finally:
        TB.make_can_continue = saved


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dv, ob, snap, board=board), board, dv


def _uid(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return int(u["id"])
    return None


def _live_pos(rpc, rid, uid):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120) or {}
    for u in (dv.get("units") or []):
        if int(u.get("id")) == int(uid):
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row"))
    return None


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def _drive(rpc, rid, wanted, max_turns=18):
    """Amene chaque unite sur sa tuile voulue en jouant des moves legaux (le natif refuse tout
    placement illegal -- c'est le harnais de `test_vigilance_eternal_live`)."""
    for _ in range(max_turns):
        if all(_live_pos(rpc, rid, u) == p for u, p in wanted.items()):
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
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid,
                    "to": {"col": int(step[0]), "row": int(step[1])}}}, 90)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    return all(_live_pos(rpc, rid, u) == p for u, p in wanted.items())


# --------------------------------------------------------------------------------------------- #
# 1. LE FOYER, NU : `get_movable_tiles_for` == `aiMovableTiles`
# --------------------------------------------------------------------------------------------- #
def test_le_foyer_des_collapses_est_le_pool_natif(rpc, build_runner):
    """`MovementQuery$$GetMovableTilesFor`, unite par unite, a `overrideRange = 2` (la portee des
    trois collapses). Ecartees, et COMPTEES -- deux residus NOMMES, aucun n'est un desaccord :
      * pool natif VIDE : garde d'entree `UnitFlagsComponent$$Has(unitFlags, 1)` (`#381`) ;
      * VOLANTES : `#381-r2` (`FlyPathfinder$$AddNeighbours` n'itere pas le meme voisinage).

    Les unites en MOUVEMENT SPECIAL ne sont PLUS ecartees : `#381-r5` est ferme (la branche
    `!ignoreSpecialMovement` de `GetPathfinderTypeForUnit` est portee, cf.
    `tests/engine/entities/pathfinding/test_381r5_special_movement_live.py`), elles sont donc
    CONFRONTEES comme les autres -- et elles sont justement celles dont le pool est le plus large
    (35 tuiles au lieu de 9 sur ce board)."""
    from engine.ai.state_bridge import _occupants
    from engine.entities.pathfinding.fly_pathfinder import is_like_flying
    from engine.entities.pathfinding.tile_blocking import terrain_blocks_entering
    from engine.entities.traits.unit_trait import unit_trait_names
    from engine.runner.components import OwnerComponent, PositionComponent
    from engine.services.movement_query import get_movable_tiles_for, has_special_movement

    rid = build_runner("38104", extra=BUILD_POOL, board=BOARD)["rid"]
    state, board, dv = _load(rpc, rid)
    blocking = [board.coord(t) for t in board.by_id if terrain_blocks_entering(board, t, ())]
    assert blocking, "%s ne porte aucune tuile block-entering -- le gate est inerte" % BOARD

    nat = rpc("aiMovableTiles", {"runnerId": rid, "side": "all",
                                 "overrideRange": PROBE_RANGE}, 120) or {}
    listed = {int(u.get("unitId")): {(int(t["col"]), int(t["row"]))
                                     for t in (u.get("tiles") or []) if t.get("col") is not None}
              for u in (nat.get("units") or [])}
    assert listed, "aiMovableTiles n'a liste aucune unite"

    occ = _occupants(state)
    compared, equal, empty, flying, special, gate_bit = 0, 0, 0, 0, 0, 0
    detail = []
    for uid, want in sorted(listed.items()):
        e = state.get_entity(uid)
        pc = e.get_component(PositionComponent) if e is not None else None
        oc = e.get_component(OwnerComponent) if e is not None else None
        if pc is None or oc is None:
            continue
        vis = next((u.get("visualId") for u in (dv.get("units") or [])
                    if int(u.get("id")) == uid), None)
        special += int(has_special_movement(state, uid))    # `#381-r5` : PORTE, plus ecarte
        if not has_special_movement(state, uid) and is_like_flying(unit_trait_names(vis)):
            flying += 1
            continue
        if not want:
            empty += 1                          # garde FLAG non portee : pas un desaccord
            continue
        start = board.id_at(pc.col, pc.row)
        if start is None:
            continue
        got = {board.coord(t) for t in get_movable_tiles_for(
            board, state, uid, start, PROBE_RANGE, occ, oc.team)}
        with _no_gate():
            raw = {board.coord(t) for t in get_movable_tiles_for(
                board, state, uid, start, PROBE_RANGE, occ, oc.team)}
        compared += 1
        if got == want:
            equal += 1
        else:
            detail.append((uid, vis, sorted(got - want), sorted(want - got)))
        if raw != got:
            gate_bit += 1

    print("\n[381-r4] %s : %d/%d == natif (dont %d en MOUVEMENT SPECIAL, #381-r5 ferme) ; "
          "ecartees : %d pool vide (#381), %d volantes (#381-r2) ; %d unite(s) dont le gate #131 "
          "change le pool ; %d tuile(s) block-entering"
          % (BOARD, equal, compared, special, empty, flying, gate_bit, len(blocking)))
    assert compared, ("aucune unite confrontable (%d pool natif vide, %d volantes) -- "
                      "NON CONCLUANT" % (empty, flying))
    assert gate_bit, ("le gate #131 ne change le pool d'AUCUNE des %d unites confrontees : la "
                      "geometrie ne prouve rien" % compared)
    assert equal == compared, ("foyer != natif sur %d/%d unites : %s"
                               % (compared - equal, compared, detail[:4]))


# --------------------------------------------------------------------------------------------- #
# 2. L'ATTERRISSAGE : le jeu pose Tyrith sur la tuile du port GATE
# --------------------------------------------------------------------------------------------- #
def _pick_geometry(state, board, caster, target):
    """(cpos, tpos, gate_dest, raw_dest) ou le port LIVRE et le port NON GATE divergent, avec une
    distance caster<->cible dans [2, MOVE_RANGE+1] (gate `Not(IsAdjacent)` + pool non vide)."""
    from engine.runner.abilities.genestealer import _vigilance_move_dest_tile
    from engine.runner.components import PositionComponent
    e_c = state.get_entity(caster).get_component(PositionComponent)
    e_t = state.get_entity(target).get_component(PositionComponent)
    keep_c, keep_t = (e_c.col, e_c.row), (e_t.col, e_t.row)
    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    found = []
    try:
        for ttile in walk:
            tpos = board.coord(ttile)
            _set_pos(state, target, *tpos)
            for ctile in walk:
                if ctile == ttile:
                    continue
                cpos = board.coord(ctile)
                if not 2 <= hexgeo.distance(cpos, tpos) <= MOVE_RANGE + 1:
                    continue
                _set_pos(state, caster, *cpos)
                gate = _vigilance_move_dest_tile(state, caster, target, MOVE_RANGE)
                with _no_gate():
                    raw = _vigilance_move_dest_tile(state, caster, target, MOVE_RANGE)
                if gate is None or raw is None or gate == raw:
                    continue
                found.append((cpos, tpos, gate, raw))
    finally:
        _set_pos(state, caster, *keep_c)
        _set_pos(state, target, *keep_t)
    if not found:
        return None
    found.sort(key=lambda g: hexgeo.distance(keep_c, g[0]) + hexgeo.distance(keep_t, g[1]))
    return found[0]


def test_l_atterrissage_de_vigilance_eternal_suit_le_gate(rpc, build_runner):
    """DISCRIMINANT de bout en bout : sur une geometrie ou le pool GATE et le pool NON GATE
    designent deux tuiles differentes, le jeu pose Tyrith sur celle du port GATE. Sans le gate, le
    port l'envoyait sur une tuile que le natif n'atteint PAS (elle ne pend que d'un Swamp)."""
    from engine.runner.abilities.genestealer import _vigilance_move_dest_tile

    rid = build_runner("38105", extra=BUILD, board=BOARD)["rid"]
    state, board, dv = _load(rpc, rid)
    caster, target = _uid(dv, TYRITH_VIS), _uid(dv, FOE_VIS)
    assert caster is not None and target is not None, "roster attendu absent du runner"

    geo = _pick_geometry(state, board, caster, target)
    assert geo is not None, ("aucune geometrie ou le gate #131 change l'atterrissage sur %s -- le "
                             "test ne prouverait rien" % BOARD)
    cpos, tpos, _g0, _r0 = geo
    if not _drive(rpc, rid, {caster: cpos, target: tpos}):
        pytest.skip("geometrie non atteignable (vise %s/%s, obtenu %s/%s)"
                    % (cpos, tpos, _live_pos(rpc, rid, caster), _live_pos(rpc, rid, target)))

    # tout re-derive sur l'etat LIVE effectif -- aucune valeur gelee
    state2, _b2, _dv2 = _load(rpc, rid)
    gate = _vigilance_move_dest_tile(state2, caster, target, MOVE_RANGE)
    with _no_gate():
        raw = _vigilance_move_dest_tile(state2, caster, target, MOVE_RANGE)
    assert gate is not None and raw is not None and gate != raw, \
        "geometrie live non discriminante (gate=%s raw=%s)" % (gate, raw)

    act = {}
    for _ in range(8):
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": VIG_ABILITY}}, 120)
        act = ((res or {}).get("actions") or [{}])[0]
        if not act.get("error") and act.get("mutated"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    assert not act.get("error") and act.get("mutated"), \
        "cast 1202 sans effet: err=%s mutated=%s" % (act.get("error"), act.get("mutated"))

    live = _live_pos(rpc, rid, caster)
    print("\n[381-r4] c=%s t=%s gate=%s no-gate=%s live=%s" % (cpos, tpos, gate, raw, live))
    assert live == gate, "atterrissage live %s != port gate %s (no-gate aurait donne %s)" \
                         % (live, gate, raw)
    assert live != raw, "le natif atterrit sur la tuile NON gatee -- le gate #131 serait REFUTE"


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
