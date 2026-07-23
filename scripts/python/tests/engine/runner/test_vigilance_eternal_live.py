"""#220 : VigilanceEternal (actif 1202, Tyrith custoKyrus) PORT -> arbre DSL, valide LIVE.

`VigilanceEternalAbility$$ExecuteBehaviour @18122a580` (DECOMPILE, mirror 1:1) = HeroicFusillade
@1811e8de0 EXACT, MOINS splash/crit :
    op_BitwiseAnd(
      If( Not(IsAdjacent(caster@0x160, target@0x178, 3)), MoveUnit(caster, destTile) ),   # MOVE (charge)
      If( IsAlive(caster) op_BitwiseAnd IsAlive(target),
          AttackWithAttackDamage(caster, target, MinMaxDamage, GetDamageProfile=Power,
                                 GetNumberConstant(0x2f)=nrOfHits=3) ) )                   # attaque mono-cible
FINDINGS DECOMPILE :
  - MOVE gate `Not(IsAdjacent(caster,target,3))` : `IsAdjacent.ShouldTrigger @180f9f7b0` par-paire = slot
    iface 0x5f (bool AreNeighbours, PAS 0x6e=GetDistance d'IsInRange @180fa1720) -> dist==1 STRICT ; le `3`
    (champ +0x18) ne va qu'a l'eval du selecteur (INERTE pour Caster/Target). Gate = "bouge SAUF si deja
    adjacent" == move-gate HeroicFusillade `Not(IsSurrounding(...,1))`. Corrobore wiki Tyrith + node porte
    dist==1 + precedent TheBetrayer @1811a4f70.
  - `GetPossibleMovementTiles @18122ae10` = `TilesUnitCanMoveToChargeTarget(caster, tile, target,
    Direct(GetNumberConstant(0x16)=range=2), reachOnly=1) @180dfda00` = `CanAddUnit(AdjacentTiles(target))
    op_And MovableTilesInRange(caster, tile, Direct(range), reachOnly=1)` == collapse `_move_dest_tile`
    HeroicFusillade (surround_radius=1, move_range=2). `SortTilesByUtility(0x20)` -> tuile la plus proche.
  - ATTAQUE mono-cible melee (profil Power, pierce 40%, 3 hits) ; gate = les DEUX vivants ; PAS de splash/crit.

VALIDATION : deterministe-sur-etat-live (comme HeroicFusillade). BUILD un runner (Tyrith + 2 ennemis),
capture l'etat LIVE (units/teams/board/stats/rng), DRIVE les positions sur l'etat charge, execute le PORT
et asserte le WIRING : (1) charge dist 2 -> Tyrith MOVE sur un hex libre adjacent a la cible + degat ;
(2) gate deja-adjacent -> AUCUN move + degat ; (3) charge dist 3 -> MOVE (confirme le gate dist==1, PAS
dist<=3) ; (4) attaque MONO-cible (aucun autre ennemi voisin touche). ASCII-only. Skip si pas de session /
Tyrith non buildable / geometrie infaisable.
"""
from __future__ import annotations

import pytest

import hexgeo

BUILD = ["--p-units", "custoKyrus", "--a-units", "necroWarden,necroDestroyer"]
TYRITH_VIS = "custoKyrus"
MOVE_RANGE = 2
SURROUND_RADIUS = 1


# ------------------------------------------------------------------ helpers etat

def _find_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _team(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _enemies_of(state, uid):
    from engine.runner.components import UnitComponent, OwnerComponent
    mine = _team(state, uid)
    out = []
    for oid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team == mine:
            continue
        out.append(oid)
    return out


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _walk_nbrs(board, tid):
    return [n for n in board.neighbours(tid) if board.walkable(n)]


def _park_others(state, board, keep_ids, center_coord):
    """Deplace toute unite VIVANTE hors `keep_ids` sur une tuile marchable LOIN (dist hex > 4) du centre."""
    from engine.runner.components import UnitComponent
    used = set()
    far = [t for t in board.by_id
           if board.walkable(t) and hexgeo.distance(board.coord(t), center_coord) > 4]
    far.sort()
    it = iter(far)
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uid in keep_ids or uc is None or not uc.alive:
            continue
        for t in it:
            if t not in used:
                used.add(t)
                _set_pos(state, uid, *board.coord(t))
                break


def _find_charge(board, start_dist):
    """Trouve (T, tyrith_start, n_walk_nbrs) : T marchable avec >=2 voisins marchables ; tyrith_start a dist
    HEX `start_dist` de T ET a un voisin LIBRE de T atteignable en <= MOVE_RANGE pas de marche (charge). On
    prend le tyrith_start le PLUS PROCHE d'un voisin de T (garantit reachOnly). Renvoie None si aucun."""
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions
    for T in sorted(board.by_id):
        if not board.walkable(T):
            continue
        nbrs = _walk_nbrs(board, T)
        if len(nbrs) < 2:
            continue
        for js in sorted(board.by_id):
            if not board.walkable(js) or js == T or js in nbrs:
                continue
            if hexgeo.distance(board.coord(js), board.coord(T)) != start_dist:
                continue
            # un voisin LIBRE de T (autre que js) doit etre atteignable depuis js en <= MOVE_RANGE
            _vis, stop = get_movable_positions(board, js, MOVE_RANGE, {}, None)
            reach = [n for n in nbrs if n in stop and n != js]
            if reach:
                return board.coord(T), board.coord(js), len(nbrs)
    return None


def _find_adjacent_pair(board):
    """Trouve (T, tyrith_adj, n) : T marchable, tyrith_adj = un voisin marchable (DEJA adjacent)."""
    for T in sorted(board.by_id):
        if not board.walkable(T):
            continue
        nbrs = _walk_nbrs(board, T)
        if len(nbrs) < 2:
            continue
        return board.coord(T), board.coord(nbrs[0]), len(nbrs)
    return None


# ------------------------------------------------------------------ fixture

@pytest.fixture(scope="session")
def vig_state(rpc, build_runner):
    """Etat LIVE reel (Tyrith custoKyrus + necrons) charge offline, rejouable a volonte."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap)
        st.board = board
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"]); r.mti = rng0["mti"]
            st.rng = r
        return st

    if _find_by_vis(build_state(), TYRITH_VIS) is None:
        pytest.skip("Tyrith (custoKyrus) absent du build (non spawnable rank 17 ?)")
    return {"build_state": build_state, "board": board}


# ------------------------------------------------------------------ tests

def test_vig_charge_dist2_move_then_attack(vig_state):
    """(1) Tyrith a dist 2 d'une cible NON adjacente -> MOVE sur un hex libre adjacent a la cible
    (gap-close), termine ADJACENTE ; (2) l'attaque mono-cible endommage la cible."""
    from engine.runner.abilities.genestealer import VigilanceEternalAbility
    state = vig_state["build_state"]()
    board = vig_state["board"]
    tyrith = _find_by_vis(state, TYRITH_VIS)
    enemies = _enemies_of(state, tyrith)
    if tyrith is None or not enemies:
        pytest.skip("Tyrith + 1 ennemi requis")
    clus = _find_charge(board, start_dist=2)
    if clus is None:
        pytest.skip("aucune geometrie de charge dist2")
    t_coord, ty_coord, _n = clus
    target = enemies[0]
    _park_others(state, board, {tyrith, target}, t_coord)
    _set_pos(state, target, *t_coord)
    _set_pos(state, tyrith, *ty_coord)
    assert hexgeo.distance(ty_coord, t_coord) == 2, "setup: Tyrith doit etre a dist 2"

    hp_t0 = _hp(state, target)
    res = VigilanceEternalAbility().execute_behaviour(state, tyrith, target)
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
    # (1) MOVE : Tyrith a bouge et est desormais adjacente a la cible
    assert res["move"] is not None and res["move"].get("moved") is True, \
        f"Tyrith n'a pas charge: {res['move']}"
    assert hexgeo.distance(_pos(state, tyrith), t_coord) == 1, \
        f"Tyrith pas adjacente post-charge: {_pos(state, tyrith)} vs {t_coord}"
    # (2) ATTAQUE mono-cible : la cible subit des degats
    assert res["attack"] is not None and res["attack"].get("target") == target, \
        f"pas d'attaque sur la cible: {res['attack']}"
    assert _hp(state, target) < hp_t0, f"cible pas endommagee (hp {hp_t0} -> {_hp(state, target)})"


def test_vig_gate_already_adjacent_no_move(vig_state):
    """GATE `Not(IsAdjacent(caster, target))` : Tyrith DEJA adjacente -> AUCUN move (dist==1). L'attaque
    a toujours lieu (branche If(IsAlive&IsAlive) independante du move)."""
    from engine.runner.abilities.genestealer import VigilanceEternalAbility
    state = vig_state["build_state"]()
    board = vig_state["board"]
    tyrith = _find_by_vis(state, TYRITH_VIS)
    enemies = _enemies_of(state, tyrith)
    if tyrith is None or not enemies:
        pytest.skip("Tyrith + 1 ennemi requis")
    pair = _find_adjacent_pair(board)
    if pair is None:
        pytest.skip("aucune paire adjacente geometrique")
    t_coord, ty_coord, _n = pair
    target = enemies[0]
    _park_others(state, board, {tyrith, target}, t_coord)
    _set_pos(state, target, *t_coord)
    _set_pos(state, tyrith, *ty_coord)
    assert hexgeo.distance(ty_coord, t_coord) == 1, "setup: Tyrith adjacente"

    hp_t0 = _hp(state, target)
    res = VigilanceEternalAbility().execute_behaviour(state, tyrith, target)
    assert res is not None
    # gate FALSE -> MoveUnit jamais execute (aucun move) ; Tyrith reste sur place
    assert res["move"] is None, f"un move a fire alors que Tyrith etait deja adjacente: {res['move']}"
    assert _pos(state, tyrith) == ty_coord, "Tyrith a bouge malgre le gate deja-adjacent"
    # l'attaque a bien eu lieu
    assert res["attack"] is not None and _hp(state, target) < hp_t0, \
        "l'attaque devrait avoir lieu meme sans move"


def test_vig_charge_dist3_still_moves(vig_state):
    """DISCRIMINANT du gate : Tyrith a dist 3 -> le port MOVE (charge). Confirme `IsAdjacent`=dist==1
    (si le `3` etait un seuil dist<=3, IsAdjacent serait VRAI a dist 3 -> Not(..)=FALSE -> AUCUN move).
    Le port bouge -> semantique dist==1 (verifiee live par ailleurs)."""
    from engine.runner.abilities.genestealer import VigilanceEternalAbility
    state = vig_state["build_state"]()
    board = vig_state["board"]
    tyrith = _find_by_vis(state, TYRITH_VIS)
    enemies = _enemies_of(state, tyrith)
    if tyrith is None or not enemies:
        pytest.skip("Tyrith + 1 ennemi requis")
    clus = _find_charge(board, start_dist=3)
    if clus is None:
        pytest.skip("aucune geometrie de charge dist3")
    t_coord, ty_coord, _n = clus
    target = enemies[0]
    _park_others(state, board, {tyrith, target}, t_coord)
    _set_pos(state, target, *t_coord)
    _set_pos(state, tyrith, *ty_coord)
    assert hexgeo.distance(ty_coord, t_coord) == 3, "setup: Tyrith a dist 3"

    res = VigilanceEternalAbility().execute_behaviour(state, tyrith, target)
    assert res is not None
    assert res["move"] is not None and res["move"].get("moved") is True, \
        f"Tyrith devrait charger depuis dist 3 (gate dist==1): {res['move']}"
    assert hexgeo.distance(_pos(state, tyrith), t_coord) == 1, \
        f"Tyrith pas adjacente post-charge dist3: {_pos(state, tyrith)}"


def test_vig_single_target_no_splash(vig_state):
    """MONO-cible : un 2e ennemi ADJACENT a la cible n'est PAS touche (pas de Union/SurroundingEnemies,
    contraste HeroicFusillade)."""
    from engine.runner.abilities.genestealer import VigilanceEternalAbility
    state = vig_state["build_state"]()
    board = vig_state["board"]
    tyrith = _find_by_vis(state, TYRITH_VIS)
    enemies = _enemies_of(state, tyrith)
    if tyrith is None or len(enemies) < 2:
        pytest.skip("Tyrith + 2 ennemis requis")
    clus = _find_charge(board, start_dist=2)
    if clus is None:
        pytest.skip("aucune geometrie de charge dist2")
    t_coord, ty_coord, n_nbrs = clus
    if n_nbrs < 3:
        pytest.skip("cible sans voisin libre pour poser le 2e ennemi")
    target, e2 = enemies[0], enemies[1]
    # e2 sur un voisin marchable de T DIFFERENT de la tuile de depart/atterrissage de Tyrith
    ttile = board.id_at(*t_coord)
    e2_tile = next((n for n in _walk_nbrs(board, ttile)
                    if board.coord(n) != ty_coord and hexgeo.distance(board.coord(n), ty_coord) > 1), None)
    if e2_tile is None:
        pytest.skip("pas de voisin libre distinct pour e2")
    _park_others(state, board, {tyrith, target, e2}, t_coord)
    _set_pos(state, target, *t_coord)
    _set_pos(state, e2, *board.coord(e2_tile))
    _set_pos(state, tyrith, *ty_coord)

    hp_e0 = _hp(state, e2)
    res = VigilanceEternalAbility().execute_behaviour(state, tyrith, target)
    assert res is not None and res["attack"] is not None
    # e2 (ennemi voisin de la cible) NON touche : attaque mono-cible
    assert _hp(state, e2) == hp_e0, f"e2 voisin endommage alors que l'attaque est mono-cible (hp {hp_e0} -> {_hp(state, e2)})"
