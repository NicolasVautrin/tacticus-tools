"""#381-r1 -- le pool de `MovableTilesInRange` est le STOP-SET GATE, jamais un disque.

Ce que le port faisait, et pourquoi personne ne le voyait
--------------------------------------------------------
Le 4e argument de `IdunBattleLogic.Entities.DSLSelectors$$MovableTilesInRange` etait lu comme un
`canReachOnly` choisissant entre le `visited` et le `stop_set` du BFS. **Cet axe n'existe pas** : le
4e argument est `ignoreFlags` (garde d'entree de `MovementQuery$$FindAnyOrAllMoveableTiles`) et le
5e, `ignoreUnitsOnTiles`, vaut `0` sur tous les call-sites lus. `MovementQuery$$AnyOrFillMoveableTiles`
termine par `RemoveAll(t => !IsMovableTile(unit, t, ignoreUnitsOnTiles))` : le pool est TOUJOURS
filtre. Et le pathfinding qu'il appelle est le MEME que celui d'`aiMovableTiles`
(`MovementQuery$$GetMovableTilesFor`), gate d'expansion #131 COMPRIS -- que ce noeud ne posait pas.

Les trois proprietes verrouillees ici sont donc, dans l'ordre du natif :
  1. le depart et les tuiles OCCUPEES sortent du pool (`IsFreeTile`) ;
  2. une tuile qui ne pend que d'une tuile block-entering (Swamp) n'y entre PAS
     (`BasePathfinder$$NodesInNextLevel` -> `IsValidContinuePathTile`), alors que la tuile
     block-entering elle-meme y RESTE (c'est un STOP legal) ;
  3. le pool est EXACTEMENT le `stop_set` que rend le foyer unique
     `walk_pathfinder.get_movable_positions` avec ce gate -- pas une re-implementation.

Chaque test est AUTO-DISCRIMINANT : il exige que la variante NON gatee differe, sinon la geometrie
ne prouve rien et le test ECHOUE (jamais un vert vide).

100 % OFFLINE : board hex synthetique, aucun runner, aucune session. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo  # noqa: E402

COLS, ROWS = 7, 7
CASTER_POS = (0, 3)
CASTER_VIS = "orksKillaKan"       # WALK (ni Flying ni Burrow) -- le dispatch pathfinder compte
ALLY_VIS = "astraBullgryn"
ENEMY_VIS = "necroWarden"
CASTER_ID, ALLY_ID, ENEMY_ID = 10, 40, 20
MOVE_RANGE = 3


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles(swamps=()) -> list:
    """Board 7x7 PLAT, tout marchable ; `swamps` = les (col,row) dont le tile-def est `Swamp`.

    `Swamp` est le terrain qui heberge `ThornsBlockMovementAbility` (elle pose
    `BlockEnteringUnitsTileEffect` AU SETUP) -- c'est la source du repli TERRAIN de
    `pathfinding/tile_blocking.terrain_blocks_entering`, seul canal disponible sur un etat monte
    sans `tiles=tileMeta`."""
    sw = {tuple(s) for s in swamps}
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb,
                        "tileDefId": "Swamp" if (col, row) in sw else "Grass"})
    return out


def _build(swamps=(), occupants=()):
    """Etat + board. `occupants` = [(unit_id, visualId, team, (col,row))] hors caster."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(_tiles(swamps), adjacency="evenq")
    units = [{"id": CASTER_ID, "visualId": CASTER_VIS, "alive": True, "team": 1, "owner": 1,
              "pos": {"col": CASTER_POS[0], "row": CASTER_POS[1]}, "effects": []}]
    for uid, vis, team, pos in occupants:
        units.append({"id": uid, "visualId": vis, "alive": True, "team": team, "owner": team,
                      "pos": {"col": pos[0], "row": pos[1]}, "effects": []})
    decision = {"currentPlayer": 1, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": 100000, "hpMax": 100000} for u in units]}
    return load_state(decision, observe, board=board), board


def _pool(state, board, swamps=(), occupants=(), move_range=MOVE_RANGE) -> set:
    """Le pool NU du noeud DSL, en (col,row)."""
    from engine.dsl.base import Const
    from engine.entities.selectors.accessors import CasterTile
    from engine.entities.selectors.tiles import Caster, MovableTilesInRange
    from engine.runner.abilities.behaviours.context import entities_from_state
    ents = entities_from_state(state, CASTER_ID, CASTER_ID)
    sel = MovableTilesInRange(Caster(), CasterTile(), Const(int(move_range)),
                              ignore_flags=False, ignore_units_on_tiles=False)
    return {board.coord(t) for t in sel.evaluate(ents)}


def _bfs(board, state, gated: bool, move_range=MOVE_RANGE):
    """(visited, stop) du foyer unique, en (col,row) -- l'oracle interne du noeud."""
    from engine.ai.state_bridge import _occupants
    from engine.entities.pathfinding.tile_blocking import terrain_blocks_entering
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions
    blocked = {t for t in board.by_id if terrain_blocks_entering(board, t, ())}
    cc = (lambda tid: int(tid) not in blocked) if gated else None
    start = board.id_at(*CASTER_POS)
    vis, stop = get_movable_positions(board, start, move_range, _occupants(state), 1,
                                      can_continue=cc)
    return {board.coord(t) for t in vis}, {board.coord(t) for t in stop}


# --------------------------------------------------------------------------------------------- #
# 1. le pool est un STOP-SET : ni le depart, ni une tuile occupee
# --------------------------------------------------------------------------------------------- #
def test_le_depart_et_les_tuiles_occupees_sortent_du_pool():
    """`IsFreeTile(tile, state, allowSteppable: 1, allowTemporaryTile: 0, allowAnyUnit: 0)` retire
    toute tuile portant une unite -- la tuile du CASTER comprise. Le port rendait le `visited`, qui
    les contient toutes."""
    ally = (ALLY_ID, ALLY_VIS, 1, (1, 3))          # ALLIE : traversable, mais pas un arret legal
    state, board = _build(occupants=[ally])
    pool = _pool(state, board, occupants=[ally])
    visited, stop = _bfs(board, state, gated=True)

    assert CASTER_POS not in pool, "la tuile de depart est dans le pool -> c'est le visited"
    assert (1, 3) not in pool, "la tuile de l'allie traverse est dans le pool -> c'est le visited"
    # AUTO-DISCRIMINANT : le visited, lui, les porte -- sinon ce test ne separe rien.
    assert CASTER_POS in visited and (1, 3) in visited
    assert pool == stop


def test_un_ennemi_bloque_la_traversee_et_ampute_le_pool():
    """`WalkPathfinder$$UnitIsBlockedByEnemyUnit` : un ENNEMI non-Steppable interdit d'ENTRER sur sa
    tuile, donc ampute tout ce qui ne pend que d'elle. Un ALLIE, lui, se traverse."""
    enemy = (ENEMY_ID, ENEMY_VIS, 2, (1, 3))
    ally = (ALLY_ID, ALLY_VIS, 1, (1, 3))
    st_e, board_e = _build(occupants=[enemy])
    st_a, board_a = _build(occupants=[ally])
    pool_e = _pool(st_e, board_e, occupants=[enemy], move_range=1)
    pool_a = _pool(st_a, board_a, occupants=[ally], move_range=1)

    assert (1, 3) not in pool_e and (1, 3) not in pool_a, "occupee -> jamais un arret"
    assert pool_e == pool_a, (
        "a portee 1 les deux pools coincident (rien ne pend de la tuile bloquee) -- si ce n'est "
        "pas le cas, le montage ne mesure pas ce qu'il annonce")
    # ... et a portee 2 la difference apparait : l'ennemi coupe le passage, l'allie non.
    assert _pool(st_e, board_e, move_range=2) < _pool(st_a, board_a, move_range=2)


# --------------------------------------------------------------------------------------------- #
# 2. gate d'EXPANSION #131 : une tuile block-entering est un CUL-DE-SAC, pas un mur
# --------------------------------------------------------------------------------------------- #
def test_une_tuile_qui_ne_pend_que_d_un_swamp_n_entre_pas_dans_le_pool():
    """`BasePathfinder$$NodesInNextLevel` : depuis une tuile block-entering, AUCUN voisin. Le noeud
    DSL ne posait pas ce gate (alors que `ai/state_bridge._move_tiles`, le mirror confronte
    d'`aiMovableTiles`, le pose) -> il sur-atteignait.

    Geometrie : un COULOIR de Swamps qui coupe la colonne 1 sur toute la hauteur atteignable. Tout
    ce qui est au-dela (colonnes >= 2) ne peut etre atteint QU'EN TRAVERSANT un Swamp."""
    swamps = [(1, r) for r in range(ROWS)]
    state, board = _build(swamps=swamps)
    pool = _pool(state, board, swamps=swamps)
    _v_gate, stop_gate = _bfs(board, state, gated=True)
    _v_raw, stop_raw = _bfs(board, state, gated=False)

    assert pool == stop_gate
    # Le Swamp reste un STOP legal (mesure live #131 : les Swamp sont dans `aiMovableTiles`) ...
    assert (1, 3) in pool
    # ... mais rien au-dela n'est atteignable.
    assert not any(c >= 2 for (c, _r) in pool), sorted(pool)
    # AUTO-DISCRIMINANT : sans le gate, le port atteignait bien la colonne 2 et au-dela.
    assert any(c >= 2 for (c, _r) in stop_raw)
    assert stop_gate < stop_raw


def test_sans_swamp_le_gate_est_un_no_op_exact():
    """Non-regression : sur un board sans tuile block-entering, le pool est INCHANGE par ce
    correctif (le gate ne retire rien) -- c'est le regime de tous les montages synthetiques
    existants."""
    state, board = _build()
    pool = _pool(state, board)
    _v_gate, stop_gate = _bfs(board, state, gated=True)
    _v_raw, stop_raw = _bfs(board, state, gated=False)
    assert stop_gate == stop_raw
    assert pool == stop_raw


# --------------------------------------------------------------------------------------------- #
# 3. le pool ne CHANGE PAS derriere l'intersection quand rien ne bloque (l'ordre de #353-r1)
# --------------------------------------------------------------------------------------------- #
def test_l_intersection_de_charge_est_inchangee_sur_un_board_sans_blocage():
    """`ramming_speed_charge_tiles_selector` intersecte `MovableTilesInRange` (GAUCHE) avec
    `CanAddUnit(AdjacentTiles(target))` (DROITE). `CanAddUnit` retirant deja les tuiles occupees,
    le passage `visited -> stop_set` est INOBSERVABLE derriere cette intersection : c'est le gate
    #131 qui mord, pas le filtre d'occupation. Ce test le VERIFIE au lieu de le supposer -- et
    c'est ce qui garantit que le datapoint d'ORDRE de `case-353` sec.5bis n'a pas bouge."""
    from ._ramming_speed_charge_montage import build_charge_montage
    from engine.dsl.base import Const
    from engine.entities.selectors.accessors import CasterTile, Target
    from engine.entities.selectors.tiles import (
        AdjacentTiles, CanAddUnit, Caster, MovableTilesInRange, TileIntersect
    )
    from engine.runner.abilities.behaviours.context import entities_from_state

    m = build_charge_montage((2, 3), move_range=5)
    ents = entities_from_state(m.state, m.caster_id, m.target_id)
    # La variante `ignore_units_on_tiles=True` rend le `visited` -- exactement l'ancien port.
    ancien = TileIntersect(
        MovableTilesInRange(Caster(), CasterTile(), Const(5),
                            ignore_flags=False, ignore_units_on_tiles=True),
        CanAddUnit(AdjacentTiles(Target()))).evaluate(ents)
    assert list(m.candidates) == list(ancien), (
        "l'intersection a change alors que le board ne porte aucun blocage -- l'ORDRE du tri de "
        "case-353 sec.5bis serait affecte")


def test_le_pool_nu_lui_a_bien_change():
    """Pendant du test precedent : l'egalite APRES intersection ne doit pas se lire « le correctif
    ne fait rien ». Le pool NU, lui, perd les OCCUPANTS.

    ⚠ CE QUI DISCRIMINE A CHANGE, et c'est un changement DELIBERE (#287-r5-r1, `d696530f`).
    Ce test opposait les deux pools par la tuile de DEPART : elle etait dans le `visited`
    (`ignore_units_on_tiles=True`) et hors du `stop_set`. Depuis, elle est hors des DEUX --
    `BasePathfinder.u003CIterateReachableTilesu003Ed__12$$MoveNext` ne l'EMET PAS, ce qui a ete
    confronte live sur `MC1_67` (`probe_287r5r1_charge_tiles_live.py`) : le natif refuse la tuile
    du caster par `TargetIsInRange` la ou le port l'acceptait.

    Le discriminant devient donc le seul axe que `ignoreUnitsOnTiles` gouverne ENCORE -- les
    tuiles OCCUPEES -- et l'assertion le NOMME au lieu de se contenter d'une inclusion stricte :
    un `nu < disque` seul redeviendrait vrai pour n'importe quelle raison."""
    from ._ramming_speed_charge_montage import (CASTER_ID as MC_CASTER, CASTER_POS as MC_POS,
                                                TARGET_ID as MC_TARGET, build_charge_montage)
    from engine.dsl.base import Const
    from engine.entities.selectors.accessors import CasterTile
    from engine.entities.selectors.tiles import Caster, MovableTilesInRange
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.components import PositionComponent, UnitComponent

    m = build_charge_montage((2, 3), move_range=5)
    ents = entities_from_state(m.state, MC_CASTER, MC_TARGET)
    nu = {m.board.coord(t) for t in MovableTilesInRange(
        Caster(), CasterTile(), Const(5), ignore_flags=False,
        ignore_units_on_tiles=False).evaluate(ents)}
    disque = {m.board.coord(t) for t in MovableTilesInRange(
        Caster(), CasterTile(), Const(5), ignore_flags=False,
        ignore_units_on_tiles=True).evaluate(ents)}

    # 1. Le DEPART sort des deux -- c'est l'etage PATHFINDING qui l'exclut, pas le filtre
    #    d'occupation (#287-r5-r1).
    assert MC_POS not in nu and MC_POS not in disque

    # 2. Ce qui les separe est EXACTEMENT de l'occupation, et il y en a (sinon rien n'est prouve).
    occupees = set()
    for uid, e in m.state.entities.items():
        pc, uc = e.get_component(PositionComponent), e.get_component(UnitComponent)
        if uid != MC_CASTER and pc is not None and uc is not None and uc.alive:
            occupees.add((pc.col, pc.row))
    ecart = disque - nu
    assert ecart, "montage non discriminant : aucune tuile occupee dans le disque"
    assert ecart <= occupees, sorted(ecart)
    assert nu < disque


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
