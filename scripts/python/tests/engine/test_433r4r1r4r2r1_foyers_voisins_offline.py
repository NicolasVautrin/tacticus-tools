"""#433-r4-r1-r4-r2-r1 -- les QUATRE foyers voisins d'adjacence, chacun sur SON substrat natif.

#433-r4-r1-r4-r2 a bascule `is_adjacent` de la couronne hex vers la liste STOCKEE du
`ConnectivityComponent`. Quatre foyers voisins faisaient encore de la geometrie ; ils ne
partagent PAS le meme verdict, parce qu'ils ne mirrorent PAS le meme natif.

    foyer                          natif                                       verdict
    ---------------------------    ----------------------------------------    -------------
    battle_query.is_charging       BattleQuery$$IsCharging                      BRANCHE
                                   -> MovementUtil$$AreTilesAdjacent
                                   -> ConnectivityComponent$$IsNeighbour        (liste stockee)
    battle_query.newly_adjacent_   MoveUnitOperation$$UpdateCharging            BRANCHE
      ids (+ son jumeau ECS        -> BattleQuery$$GetAdjacentUnits             (2 etages
      runner.components.           -> TileQuery.<IterateAdjacentTiles>d__8       manquants)
      update_charging)                $$MoveNext
    battle_query.in_arc            BasePlaybook$$GetEligibleTargetsSelectable   GEOMETRIQUE
    battle_query.count_enemies_    -> AttackQuery$$GetValidTargetsWithCache       PUR : rien a
      in_arc                       -> TargetingQuery$$GetUnitsInRange             brancher, et
                                   -> BattleQuery$$GetUnitsAtDistance             la porte
                                   -> BattleQuery$$GetTilesAtDistance             d'elevation
                                   -> BattleQuery$$GetSurroundingTiles            etait EN TROP

LES DEUX LECTURES QUI TRANCHENT

* `IdunBattle.Entities.Components.ConnectivityComponent$$IsNeighbour` vaut
  `this[+0x10].Contains(<entity id de tile2>)` -- la MEME `List<int>` qu'enumere
  `IterateAdjacentTiles`. `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` la joint a la
  porte par un ET (`iVar7 < 2 & bVar3`). Donc `IsCharging` lit bien la liste stockee.
* `IdunBattle.Core.Services.BattleQuery$$GetTilesAtDistance` filtre le disque de
  `GetSurroundingTiles` par `PositionComponent$$Distance(t, centre) == distance` : une distance
  hexagonale sur un disque cube. **Aucun `ConnectivityComponent`, aucun `|dElev| < 2`** sur la
  chaine d'ELIGIBILITE -- y brancher le canal FABRIQUERAIT une divergence. La mesure live le
  disait deja (case-49x, probe_49x_realanchor phase B, `C1_25` : ennemi adjacent a `|dElev| = 2`,
  le natif GENERE quand meme une action) ; `eligible_targets_count` le portait, `in_arc` non.

100 % OFFLINE.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine import battle_query as bq                                            # noqa: E402
from engine.entities.pathfinding.board import (Board,                            # noqa: E402
                                               adjacent_neigh_by_pos)
from engine.playbook.prediction._shared import _prediction_is_charging           # noqa: E402
from engine.playbook.scene import Scene                                          # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent,         # noqa: E402
                                      UnitComponent, charged_unit_ids,
                                      update_charging)
from engine.runner.damage_model import battle_query_is_charging                  # noqa: E402
from engine.runner.state import State                                            # noqa: E402

COLS, ROWS = 5, 5


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board(elev=None, coupe=(), with_neighbours: bool = True) -> Board:
    """Board 5x5 plein. `coupe` = aretes NON DIRIGEES retirees du champ `neighbours` des DEUX
    cotes -- le patron `Bridge` mesure live. `with_neighbours=False` retire le CHAMP (canal
    absent), a ne PAS confondre avec une liste vide."""
    elev = elev or {}
    coupees = set()
    for (a, b) in coupe:
        coupees.add((a, b))
        coupees.add((b, a))
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            t = {"id": _tid(col, row), "col": col, "row": row, "walkable": True,
                 "isWall": False, "elevation": int(elev.get((col, row), 0))}
            if with_neighbours:
                t["neighbours"] = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                                   if 0 <= c < COLS and 0 <= r < ROWS
                                   and ((col, row), (c, r)) not in coupees]
            tiles.append(t)
    return Board(tiles)


# Le patron mesure : `FANTOME` est dans la couronne de `A` mais PAS dans sa liste stockee ;
# `TEMOIN` y est des deux cotes. Le temoin est ce qui interdit de lire un refus comme une inertie.
A = (2, 2)
FANTOME = hexgeo.neighbors(2, 2)[0]
TEMOIN = hexgeo.neighbors(2, 2)[1]
LOIN = (0, 0)


def test_le_montage_est_discriminant():
    """Sans ce cran, tous les autres pourraient etre verts pour la mauvaise raison."""
    assert hexgeo.distance(A, FANTOME) == 1 and hexgeo.distance(A, TEMOIN) == 1
    assert FANTOME != TEMOIN
    assert hexgeo.distance(A, LOIN) > 2
    bd = _board(coupe=[(A, FANTOME)])
    neigh = adjacent_neigh_by_pos(bd)
    assert FANTOME not in neigh[A] and TEMOIN in neigh[A]


# --------------------------------------------------------------- FOYER 1 : `is_charging`
def test_is_charging_lit_la_liste_stockee():
    """`MovementUtil$$AreTilesAdjacent` -> `ConnectivityComponent$$IsNeighbour` = la liste stockee.
    Le 2e terme (`ChargedUnitIds.Contains`) est VRAI dans les deux cas : seul le substrat bouge."""
    bd = _board(coupe=[(A, FANTOME)])
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    assert bq.is_charging(A, FANTOME, 7, [7], elev, None) is True      # avant : la couronne
    assert bq.is_charging(A, FANTOME, 7, [7], elev, neigh) is False    # apres : la liste stockee
    assert bq.is_charging(A, TEMOIN, 7, [7], elev, neigh) is True      # TEMOIN : toujours accorde


def test_is_charging_garde_son_second_terme():
    """Le canal ne remplace pas `ChargedUnitIds` : adjacent sans avoir charge reste FAUX."""
    bd = _board()
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    assert bq.is_charging(A, TEMOIN, 7, [], elev, neigh) is False
    assert bq.is_charging(A, TEMOIN, 7, [9], elev, neigh) is False


def test_is_charging_tri_etat_PAR_CLE():
    """Une tuile ABSENTE du canal retombe sur la geometrie POUR ELLE SEULE. Un tri-etat pose sur
    le dict entier (`{} -> tout faux`) isolerait toutes les tuiles d'un coup : le vice `#381-r3`."""
    bd = _board(coupe=[(A, FANTOME)])
    elev = bd.elev_by_pos()
    partiel = {A: [TEMOIN]}                       # LOIN et TEMOIN n'ont PAS d'entree
    assert bq.is_charging(A, FANTOME, 7, [7], elev, partiel) is False    # A est dans le canal
    assert bq.is_charging(TEMOIN, A, 7, [7], elev, partiel) is True      # TEMOIN ne l'est pas
    assert bq.is_charging(A, FANTOME, 7, [7], elev, {}) is True          # dict VIDE != isolement


# ------------------------------------- FOYER 2 : `newly_adjacent_ids` et son jumeau ECS
def _positions(**kw):
    return {int(k[1:]): v for k, v in kw.items()}


def test_newly_adjacent_ids_etage_ENUMERATION():
    """`UpdateCharging` -> `GetAdjacentUnits` -> `IterateAdjacentTiles` : la liste STOCKEE."""
    bd = _board(coupe=[(A, FANTOME)])
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    others = _positions(u7=FANTOME, u8=TEMOIN)
    assert bq.newly_adjacent_ids(LOIN, A, others) == {7, 8}                   # avant : la couronne
    assert bq.newly_adjacent_ids(LOIN, A, others, elev, neigh) == {8}         # apres : la liste


def test_newly_adjacent_ids_etage_PORTE_ELEVATION():
    """Le second etage de l'iterateur, que le port ne portait pas davantage."""
    bd = _board(elev={FANTOME: 2})
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    others = _positions(u7=FANTOME, u8=TEMOIN)
    assert bq.newly_adjacent_ids(LOIN, A, others) == {7, 8}
    assert bq.newly_adjacent_ids(LOIN, A, others, elev, neigh) == {8}


def test_newly_adjacent_ids_reste_un_DELTA():
    """« Nouvellement adjacent » : deja au contact avant le pas -> pas de charge."""
    bd = _board()
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    others = _positions(u8=TEMOIN)
    assert bq.newly_adjacent_ids(A, A, others, elev, neigh) == set()
    assert bq.newly_adjacent_ids(None, A, others, elev, neigh) == {8}   # `MainTile == null`


def test_newly_adjacent_ids_sans_canaux_est_le_comportement_ANTERIEUR():
    bd = _board(coupe=[(A, FANTOME)])
    others = _positions(u7=FANTOME, u8=TEMOIN)
    assert bq.newly_adjacent_ids(LOIN, A, others, None, None) == {7, 8}


def _state(units, board=None) -> State:
    st = State()
    for uid, pos, team in units:
        e = st.add_entity(uid)
        e.add_component(PositionComponent(pos[0], pos[1]))
        e.add_component(UnitComponent("u%d" % uid, True))
        e.add_component(OwnerComponent(team))
    st.board = board
    return st


def test_update_charging_ECS_lit_le_MEME_substrat():
    """Le pendant ECS derive ses canaux de `state.board` -- une seule des deux faces branchee
    ferait diverger un natif UNIQUE (`MoveUnitOperation$$UpdateCharging`)."""
    bd = _board(coupe=[(A, FANTOME)])
    st = _state([(1, LOIN, 0), (7, FANTOME, 1), (8, TEMOIN, 1)], board=bd)
    update_charging(st, 1, LOIN, A)
    assert charged_unit_ids(st, 1) == {8}                     # 7 est hors liste stockee


def test_update_charging_sans_board_est_le_comportement_ANTERIEUR():
    st = _state([(1, LOIN, 0), (7, FANTOME, 1), (8, TEMOIN, 1)], board=None)
    update_charging(st, 1, LOIN, A)
    assert charged_unit_ids(st, 1) == {7, 8}


def test_les_DEUX_faces_saccordent():
    """Face COMBAT (ECS) et face PREDICTION (Scene) doivent rendre le MEME ensemble."""
    bd = _board(coupe=[(A, FANTOME)])
    st = _state([(1, LOIN, 0), (7, FANTOME, 1), (8, TEMOIN, 1)], board=bd)
    update_charging(st, 1, LOIN, A)
    combat = charged_unit_ids(st, 1)
    others = _positions(u7=FANTOME, u8=TEMOIN)
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    prediction = bq.newly_adjacent_ids(LOIN, A, others, elev, neigh)
    assert combat == prediction == {8}


def test_battle_query_is_charging_COMBAT_derive_du_board():
    """Le pont ECS ne passait NI l'elevation NI le voisinage."""
    bd = _board(coupe=[(A, FANTOME)])
    st = _state([(1, A, 0), (7, FANTOME, 1), (8, TEMOIN, 1)], board=bd)
    st.get_entity(1).get_component(UnitComponent).charged_unit_ids = [7, 8]
    assert battle_query_is_charging(st, 1, 7) is False        # arete hors liste stockee
    assert battle_query_is_charging(st, 1, 8) is True         # TEMOIN
    st_nu = _state([(1, A, 0), (7, FANTOME, 1)], board=None)
    st_nu.get_entity(1).get_component(UnitComponent).charged_unit_ids = [7]
    assert battle_query_is_charging(st_nu, 1, 7) is True      # sans board : comportement anterieur


def _scene(board, pos_by_id, charged):
    return Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                 vis_by_id={}, units=[], hp_by_id={}, pos_by_id=pos_by_id, team_by_id={},
                 eff_state=None, board=board, charged_by_id=charged)


def test_prediction_is_charging_derive_de_la_scene():
    """Face PREDICTION : le canal vient de `Scene.neigh_by_pos`, jamais d'un call-site."""
    bd = _board(coupe=[(A, FANTOME)])
    sc = _scene(bd, {1: LOIN, 7: FANTOME, 8: TEMOIN}, {})
    assert _prediction_is_charging(sc, 1, A, 7) is False      # le pas ne charge PAS le fantome
    assert _prediction_is_charging(sc, 1, A, 8) is True
    sc_nu = _scene(None, {1: LOIN, 7: FANTOME, 8: TEMOIN}, {})
    assert _prediction_is_charging(sc_nu, 1, A, 7) is True    # sans board : comportement anterieur


def test_prediction_is_charging_terme_REEL_passe_aussi_par_le_canal():
    """Charge DEJA acquise, aucun pas : le predicat re-verifie l'adjacence, donc le canal mord."""
    bd = _board(coupe=[(A, FANTOME)])
    sc = _scene(bd, {1: A, 7: FANTOME, 8: TEMOIN}, {1: {7, 8}})
    assert _prediction_is_charging(sc, 1, None, 7) is False
    assert _prediction_is_charging(sc, 1, None, 8) is True


# ------------------------------------- FOYERS 3 et 4 : `in_arc` / `count_enemies_in_arc`
def test_in_arc_est_GEOMETRIQUE_PUR():
    """La chaine d'ELIGIBILITE passe par `GetTilesAtDistance` (distance hex sur le disque de
    `GetSurroundingTiles`), pas par `IterateAdjacentTiles` : une arete absente de la liste
    stockee reste dans l'arc, et le natif genere bien une action depuis la."""
    assert bq.in_arc(A, FANTOME) is True
    assert bq.in_arc(A, TEMOIN) is True


def test_in_arc_na_PLUS_de_porte_delevation():
    """Mesure live case-49x : ennemi adjacent a `|dElev| = 2`, le natif GENERE une action. La
    porte etait un fork de port contre `eligible_targets_count`, qui ne l'a jamais eue."""
    haut, bas = (2, 2), (2, 3)
    assert hexgeo.distance(haut, bas) == 1
    assert bq.in_arc(haut, bas) is True
    assert bq.eligible_targets_count(haut, [bas]) == 1        # le jumeau, inchange
    assert bq.count_enemies_in_arc(haut, [bas]) == 1          # d'accord avec lui


def test_in_arc_garde_ring2_et_sarrete_la():
    a = (2, 2)
    assert bq.in_arc(a, (2, 0)) is True                       # dist 2
    assert bq.in_arc(a, (2, 5)) is False                      # dist 3


def test_in_arc_et_eligible_targets_count_saccordent_partout():
    """Les deux mirrorent le MEME natif ; le fork est ferme, donc l'accord doit etre TOTAL."""
    cibles = [(c, r) for c in range(COLS) for r in range(ROWS)]
    for t in cibles:
        n = bq.count_enemies_in_arc(t, cibles)
        assert n == bq.eligible_targets_count(t, cibles), t


def test_enemies_in_arc_preserve_lordre_denumeration():
    ennemis = [{"id": 3, "pos": {"col": TEMOIN[0], "row": TEMOIN[1]}},
               {"id": 4, "pos": {"col": FANTOME[0], "row": FANTOME[1]}},
               {"id": 5, "pos": {"col": LOIN[0], "row": LOIN[1]}}]
    assert [e["id"] for e in bq.enemies_in_arc(A, ennemis)] == [3, 4]


# ------------------------------------------------------- le CANAL : memoisation et robustesse
def test_adjacent_neigh_by_pos_est_MEMOISE():
    """Chemins CHAUDS cote combat (un appel par pas, un par coup) : une reconstruction en
    O(tuiles) y serait payee des milliers de fois. Le board est STATIQUE (lu au decompile)."""
    bd = _board()
    a = adjacent_neigh_by_pos(bd)
    assert adjacent_neigh_by_pos(bd) is a


def test_adjacent_neigh_by_pos_tolere_un_board_FIGE():
    """Un porteur duck-type peut refuser l'attribut de cache : on recalcule, on n'echoue pas."""
    class _Fige:
        __slots__ = ("by_id",)

        def __init__(self, by_id):
            self.by_id = by_id

    bd = _board()
    fige = _Fige(bd.by_id)
    assert adjacent_neigh_by_pos(fige) == adjacent_neigh_by_pos(fige)


def test_adjacent_neigh_by_pos_garde_son_TRI_ETAT():
    assert adjacent_neigh_by_pos(None) is None
    assert adjacent_neigh_by_pos(_board(with_neighbours=False)) is None


def test_adjacent_addable_count_le_branchement_est_un_NO_OP():
    """Le canal propage au filtre ne change RIEN, dans les DEUX branches -- c'est pourquoi il est
    sur : branche NATIVE, `p` sort deja du canal ; branche FALLBACK, `neigh` est la couronne."""
    bd = _board(coupe=[(A, FANTOME)])
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    walk = {(c, r): True for c in range(COLS) for r in range(ROWS)}
    avec = bq.adjacent_addable_count(A, neigh, walk, set(), elev)
    sans = bq.adjacent_addable_count(A, None, walk, set(), elev)
    assert avec == len(neigh[A])              # branche native : tous les voisins stockes
    assert sans == len(hexgeo.neighbors(*A))  # branche fallback : la couronne entiere
