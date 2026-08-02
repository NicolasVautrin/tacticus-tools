"""R30 -- GARDE du substrat MULTI-HEX (empreinte a N pieds), 100 % offline.

Ce fichier ne remplace PAS la confrontation live (`test_multihex_dutyeternal_live.py`) : il
VERROUILLE les invariants que la confrontation a etablis, et surtout la NON-REGRESSION du cas
nominal — une unite a UN pied doit se comporter EXACTEMENT comme avant le substrat.

Chaque assertion cite la fonction native qu'elle garde :
  `IdunBattle.Entities.Components.UnitComponent$$AddFoot` / `$$ClearFeet`
  `IdunBattle.Entities.UnitExtensions$$GetUnitFeet` / `$$GetFeetCount`
  `IdunBattle.Entities.EntityExtensions$$GetMainTileId`
  `IdunBattle.Core.Services.MovementQuery$$GetDistance` / `$$IsValidUnitFeetList`
  `IdunBattle.Core.Services.MovementQuery$$GetPossibleTileListsFromMovableTiles`
  `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles`
  `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape`
  `IdunBattle.Entities.Selectors.ThreeUnitSpawnTileShapeSelector$$GetArea` / `$$CorrectArea`
  `IdunBattle.AI.Utilities.DislikeStartingTilesUtility.<EvaluateMovementInSteps>d__2$$MoveNext`
ASCII only.
"""
from __future__ import annotations

import hexgeo
import pytest

from engine import battle_query as BQ
from engine.ai.utilities import DislikeStartingTilesUtility
from engine.entities.pathfinding.board import Board
from engine.runner.components import (PositionComponent, UnitComponent, get_feet_count,
                                      get_main_tile, get_unit_feet, set_unit_feet)
from engine.runner.state import State
from engine.services import movement_query as MQ
from engine.services import spawn_tile_shape as STS

COLS, ROWS = 8, 9


def _flat_board(elev_overrides=None, unplayable=()) -> Board:
    """Plateau plat COLSxROWS, adjacence `evenq` recalculee (aucun trou), pour isoler la
    geometrie de l'empreinte de toute particularite d'un board dumpe.

    Le champ `neighbours` est REMPLI (voisinage even-q clippe aux bords), comme dans tout autre
    montage offline du depot. Il ne peut PAS rester `[]` : `Board.neighbours_native` distingue le
    champ ABSENT (repli sur `neighbours()`) du champ PRESENT ET VIDE (rend `[]`), et cette seconde
    lecture est EXACTE sur un board reel -- `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`
    applique une porte d'elevation inconditionnelle, donc une tuile dont tous les voisins stockes
    sont a 2 niveaux d'ecart ressort bien sans aucun voisin. Un `[]` litteral declarait donc
    « aucun voisin natif » sur un plateau que cette docstring annonce sans trou.

    Les MURS restent presents dans la liste : le capteur `boardGraph` appelle
    `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(tile, false, false, true)`
    (`requireWalkable = 0`), donc `unplayable` retire la marchabilite, jamais l'arete."""
    tiles, tid = [], 1
    idof = {}
    for c in range(COLS):
        for r in range(ROWS):
            idof[(c, r)] = tid
            tid += 1
    for (c, r), i in idof.items():
        tiles.append({
            "id": i, "col": c, "row": r,
            "elevation": (elev_overrides or {}).get((c, r), 0),
            "tileDefId": "Grass", "isTemporary": False, "isWall": (c, r) in unplayable,
            "walkable": (c, r) not in unplayable, "occupantUnitId": None,
            "neighbours": [idof[n] for n in hexgeo.neighbors(c, r) if n in idof],
        })
    return Board(tiles, adjacency="evenq")


def _unit(state: State, uid: int, pos, feet=None) -> None:
    e = state.add_entity(uid)
    e.add_component(UnitComponent(visual_id=f"u{uid}", alive=True))
    e.add_component(PositionComponent(pos[0], pos[1]))
    if feet:
        set_unit_feet(state, uid, feet)


# ------------------------------------------------------------------------- garde DU MONTAGE

def test_flat_board_publishes_native_neighbours():
    """GARDE DU MONTAGE, pas du port : `_flat_board` doit exposer un voisinage NATIF non vide.

    Sans elle, un montage qui rend `neighbours_native == []` ne se signale pas franchement -- il
    fait passer a VIDE l'anneau des tests a 7 pieds. Trois d'entre eux tombaient alors en
    `IndexError` (`ring[0]`), mais `test_dislike_starting_tiles_footprint_follows_feet_count`
    restait VERT avec zero assertion utile : `set([center]) == {center} | set([])` est vraie.
    C'est un vert vacueux, la forme la plus couteuse -- on la rend impossible ici."""
    board = _flat_board()
    inner = (3, 4)
    ring = board.neighbours_native(board.id_at(*inner))
    assert len(ring) == 6, f"tuile interieure a {len(ring)} voisins natifs au lieu de 6"
    assert set(ring) == set(board.neighbours(board.id_at(*inner))), \
        "vue NATIVE et vue evenq du montage doivent coincider sur un plateau plat sans trou"
    # un coin en a strictement moins (clip aux bords), et jamais zero
    corner = board.neighbours_native(board.id_at(0, 0))
    assert 0 < len(corner) < 6


# ---------------------------------------------------------------- formes natives (les 3 tailles)

def test_triangle_shape_is_three_mutually_adjacent_tiles():
    """`BattleQuery$$GetTilesInTriangleShape(tile, d)` : pour les 6 directions et les DEUX parites
    de colonne, l'aire est [ancre, t1, t2] avec t1/t2 voisins de l'ancre ET voisins entre eux.
    C'est la propriete que `MovementQuery$$IsValidUnitFeetList(3, ...)` exige ensuite."""
    for anchor in [(2, 4), (3, 4), (0, 0), (5, 7), (4, 2), (7, 3)]:
        for d in range(6):
            area = BQ.get_tiles_in_triangle_shape(anchor, d)
            assert area[0] == anchor, f"{anchor} d={d}: ancre pas en tete -> {area}"
            assert len(area) == 3 and len(set(area)) == 3, f"{anchor} d={d}: {area}"
            for i, j in ((0, 1), (0, 2), (1, 2)):
                assert hexgeo.distance(area[i], area[j]) == 1, \
                    f"{anchor} d={d}: {area[i]} et {area[j]} pas voisins ({area})"


def test_triangle_directions_are_six_distinct_areas():
    """Les 6 directions donnent 6 aires DISTINCTES (aucune collision de transcription du switch)."""
    for anchor in [(2, 4), (3, 4)]:
        areas = {tuple(sorted(BQ.get_tiles_in_triangle_shape(anchor, d))) for d in range(6)}
        assert len(areas) == 6, f"{anchor}: {len(areas)} aires distinctes au lieu de 6"


def test_get_area_tries_directions_in_native_order():
    """`ThreeUnitSpawnTileShapeSelector$$GetArea` : ordre d'essai [1, 0, 5, 4, 3, 2], PREMIERE
    direction valide. En bloquant la direction 1, c'est la 0 qui doit sortir."""
    assert STS.DIRECTION_ORDER == (1, 0, 5, 4, 3, 2)
    board = _flat_board()
    anchor = (2, 4)
    d1 = BQ.get_tiles_in_triangle_shape(anchor, 1)
    assert STS.get_area(board, frozenset(), anchor) == d1
    assert STS.get_area_direction(board, frozenset(), anchor) == 1
    # On occupe une tuile PROPRE a la direction 1 (absente de l'aire de la direction 0) ->
    # `CorrectArea` refuse la 1, et c'est la 0 -- la SUIVANTE DE L'ORDRE NATIF, pas la 2 -- qui sort.
    d0 = BQ.get_tiles_in_triangle_shape(anchor, 0)
    only_d1 = [t for t in d1[1:] if t not in d0]
    assert only_d1, "aire de la direction 1 entierement incluse dans celle de la direction 0"
    blocked = frozenset({only_d1[0]})
    assert STS.get_area_direction(board, blocked, anchor) == 0
    assert STS.get_area(board, blocked, anchor) == d0
    # On bloque AUSSI la 0 -> la 5 (3e de l'ordre) prend la main.
    blocked2 = blocked | {t for t in d0[1:] if t not in BQ.get_tiles_in_triangle_shape(anchor, 5)}
    assert STS.get_area_direction(board, blocked2, anchor) == 5


def test_get_area_refuses_elevation_step_and_edges():
    """`CorrectArea` -> `CorrectRelationshipInArea` : meme ELEVATION obligatoire. Et une aire qui
    deborde du plateau n'a pas 3 tuiles -> refus (`area.Count != 3`)."""
    anchor = (2, 4)
    stepped = {t: 1 for d in range(6) for t in BQ.get_tiles_in_triangle_shape(anchor, d)[1:]}
    assert STS.get_area(_flat_board(elev_overrides=stepped), frozenset(), anchor) == []
    corner = (0, 0)                                   # toutes les aires debordent ou sont hors board
    board = _flat_board()
    area = STS.get_area(board, frozenset(), corner)
    assert all(board.tile_at(t[0], t[1]) is not None for t in area)


# ------------------------------------------------------------------- stockage / accesseurs natifs

def test_single_foot_unit_is_strictly_unchanged():
    """NON-REGRESSION du cas NOMINAL : une unite a 1 pied garde `feet = None`, son empreinte est
    `[PositionComponent]`, sa main tile est sa position, son compte est 1."""
    s = State()
    _unit(s, 1, (3, 4))
    uc = s.get_entity(1).get_component(UnitComponent)
    assert uc.feet is None, "une unite mono-tuile ne doit PAS materialiser de liste de pieds"
    assert get_unit_feet(s, 1) == [(3, 4)]
    assert get_feet_count(s, 1) == 1
    assert get_main_tile(s, 1) == (3, 4)
    assert s.occupied_positions() == {(3, 4)}
    assert s.unit_at((3, 4)) is s.get_entity(1)
    assert s.unit_at((3, 5)) is None


def test_entity_without_position_has_no_feet():
    """`GetUnitFeetIds` rend vide pour une entite qui n'est pas une unite sur le plateau (MoW hors
    plateau : ni `PositionComponent`, ni pieds) -> compte 0, main tile None."""
    s = State()
    e = s.add_entity(9)
    e.add_component(UnitComponent(visual_id="mow", alive=True))
    assert get_unit_feet(s, 9) == []
    assert get_feet_count(s, 9) == 0
    assert get_main_tile(s, 9) is None


def test_set_unit_feet_keeps_main_tile_invariant():
    """`set_unit_feet` = la boucle ClearFeet/AddFoot d'`AddUnitOperation$$Execute` : l'ordre est
    conserve, `feet[0]` est la main tile, et la `PositionComponent` est recalee dessus."""
    s = State()
    _unit(s, 1, (0, 0))
    feet = [(2, 1), (2, 2), (3, 2)]
    assert set_unit_feet(s, 1, feet) == feet
    pc = s.get_entity(1).get_component(PositionComponent)
    assert (pc.col, pc.row) == (2, 1) == get_main_tile(s, 1)
    assert get_feet_count(s, 1) == 3
    # AddFoot = OrderedSet.Add -> idempotent (pas de doublon), ordre d'insertion conserve
    uc = s.get_entity(1).get_component(UnitComponent)
    uc.add_foot((2, 2))
    assert uc.feet == feet
    # retomber a un pied REVIENT au cas nominal (aucun etat multi-hex residuel)
    assert set_unit_feet(s, 1, [(5, 5)]) == [(5, 5)]
    assert s.get_entity(1).get_component(UnitComponent).feet is None
    assert get_main_tile(s, 1) == (5, 5)


def test_occupancy_counts_every_foot():
    """VALIDE LIVE : les 3 tuiles d'un Galatian portent le MEME `occupantUnitId`. Cote port,
    `unit_at` et `occupied_positions` doivent voir les 3 pieds, pas la seule main tile."""
    s = State()
    _unit(s, 1, (2, 1), feet=[(2, 1), (2, 2), (3, 2)])
    _unit(s, 2, (6, 7))
    assert s.occupied_positions() == {(2, 1), (2, 2), (3, 2), (6, 7)}
    for f in [(2, 1), (2, 2), (3, 2)]:
        assert s.unit_at(f) is s.get_entity(1), f"tuile {f} non attribuee a l'unite proprietaire"
    s.get_entity(1).get_component(UnitComponent).alive = False
    assert s.occupied_positions() == {(6, 7)}, "une unite morte n'occupe plus aucun de ses pieds"


# --------------------------------------------------------------------- geometrie MovementQuery

def test_get_distance_is_min_over_feet_pairs():
    """`MovementQuery$$GetDistance(IList, IList)` = MIN sur toutes les paires ; listes vides ->
    `int.MaxValue` (le seed ressort tel quel, le natif ne rend PAS 0)."""
    galatian = [(2, 1), (2, 2), (3, 2)]
    assert MQ.get_distance(galatian, [(3, 3)]) == 1        # adjacent au pied (3,2)...
    assert hexgeo.distance((2, 1), (3, 3)) == 2            # ...mais a 2 de la MAIN TILE
    assert MQ.get_distance([(2, 1)], [(3, 3)]) == 2        # 1 pied = comportement d'avant
    assert MQ.get_distance([], [(3, 3)]) == MQ.INT_MAX
    assert MQ.get_distance(galatian, []) == MQ.INT_MAX


def test_get_entity_distance_uses_footprints():
    s = State()
    _unit(s, 1, (2, 1), feet=[(2, 1), (2, 2), (3, 2)])
    _unit(s, 2, (3, 3))
    assert MQ.get_entity_distance(s, s.get_entity(1), s.get_entity(2)) == 1
    assert MQ.get_entity_distance(s, s.get_entity(1), None) == MQ.INT_MAX


@pytest.mark.parametrize("n", [1, 3, 7])
def test_is_valid_unit_feet_list_accepts_native_shapes(n):
    """`IsValidUnitFeetList` accepte 1 (toujours), 3 (triangle) et 7 (centre + anneau)."""
    board = _flat_board()
    center = (3, 4)
    if n == 1:
        feet = [center]
    elif n == 3:
        feet = BQ.get_tiles_in_triangle_shape(center, 1)
    else:
        ring = [board.coord(t) for t in board.neighbours_native(board.id_at(*center))]
        feet = [center] + ring
    assert len(feet) == n
    assert MQ.is_valid_unit_feet_list(board, n, feet) is True


def test_is_valid_unit_feet_list_rejections():
    """Refus mirror : mauvais compte, elevation heterogene, triangle non ferme, taille non
    supportee ; ACCEPTATION de la liste entierement nulle (branche `nullCount == feetCount`)."""
    board = _flat_board(elev_overrides={(3, 5): 1})
    tri = BQ.get_tiles_in_triangle_shape((3, 4), 1)
    assert MQ.is_valid_unit_feet_list(board, 3, tri[:2]) is False        # Count != feetCount
    assert MQ.is_valid_unit_feet_list(board, 3, None) is False
    assert MQ.is_valid_unit_feet_list(board, 3, [None, None, None]) is True
    assert MQ.is_valid_unit_feet_list(board, 3, [tri[0], tri[1], None]) is False
    assert MQ.is_valid_unit_feet_list(board, 3, [(0, 0), (0, 1), (5, 5)]) is False  # non ferme
    assert MQ.is_valid_unit_feet_list(board, 2, [(0, 0), (0, 1)]) is False          # non supporte
    if (3, 5) in tri:                                                   # marche d'elevation
        assert MQ.is_valid_unit_feet_list(board, 3, tri) is False


def test_possible_tile_lists_and_movable_positions():
    """`GetPossibleTileListsFromMovableTiles` : k-combinaisons pour 1 et 3, centre+anneau pour 7,
    `None` hors {1,3,7}. `GetMovablePositionsFromTiles` : chemin A PART pour 1 pied (aucun filtre)
    et filtre `IsValidUnitFeetList` au-dela."""
    board = _flat_board()
    center = (3, 4)
    ring = [board.coord(t) for t in board.neighbours_native(board.id_at(*center))]
    pool = [center] + ring
    assert MQ.get_possible_tile_lists_from_movable_tiles(board, pool, 2) is None
    assert MQ.get_possible_tile_lists_from_movable_tiles(board, pool, 1) == [[t] for t in pool]
    assert len(MQ.get_possible_tile_lists_from_movable_tiles(board, pool, 3)) == 35   # C(7,3)
    seven = MQ.get_possible_tile_lists_from_movable_tiles(board, pool, 7)
    assert seven and seven[0][0] == center, "le CENTRE doit etre en tete (= main tile)"
    # 1 pied : chemin `ToUnitPositionList` -> une position par tuile, sans filtre
    assert MQ.get_movable_positions_from_tiles(board, pool, 1) == [[t] for t in pool]
    assert MQ.get_movable_positions_from_tiles(board, [], 3) == []
    # 3 pieds : seules les combinaisons TRIANGULAIRES survivent (et il y en a strictement moins)
    tri3 = MQ.get_movable_positions_from_tiles(board, pool, 3)
    assert 0 < len(tri3) < 35
    for combo in tri3:
        assert MQ.is_valid_unit_feet_list(board, 3, combo)


def test_get_movable_positions_for_adds_current_tiles():
    """`GetMovablePositionsFor` ajoute les tuiles ACTUELLES de l'unite au pool avant le
    regroupement (le natif : `movable.AddRange(IterateTiles(unit))`)."""
    board = _flat_board()
    s = State()
    _unit(s, 1, (3, 4))
    out = MQ.get_movable_positions_for(board, s, 1, [])
    assert out == [[(3, 4)]], "la tuile courante doit rester une position atteignable"


# --------------------------------------------------------- terme d'utilite feetCount (leaf 27)

class _Ctx:
    def __init__(self, origin=None, feet_count=1, start_feet=None, neigh_by_pos=None, wt=None):
        self.origin = origin
        self.feet_count = feet_count
        self.start_feet = start_feet
        self.neigh_by_pos = neigh_by_pos
        self.wt = wt        # weights BC (None = poids NON LU -> aucune penalite fabriquee)


def test_dislike_starting_tiles_footprint_follows_feet_count():
    """`DislikeStartingTilesUtility` : l'empreinte candidate = [MainTile], etendue de l'anneau
    UNIQUEMENT si `GetFeetCount == 7`. Une unite a 3 pieds n'etend RIEN (quirk natif lu au
    decompile)."""
    u = DislikeStartingTilesUtility()
    board = _flat_board()
    center = (3, 4)
    ring = [board.coord(t) for t in board.neighbours_native(board.id_at(*center))]
    assert len(ring) == 6, "anneau vide -> les assertions ci-dessous seraient VACUEUSES"
    neigh = {center: ring}
    assert u.candidate_footprint(_Ctx(feet_count=1, neigh_by_pos=neigh), center) == [center]
    assert u.candidate_footprint(_Ctx(feet_count=3, neigh_by_pos=neigh), center) == [center]
    seven = u.candidate_footprint(_Ctx(feet_count=7, neigh_by_pos=neigh), center)
    assert seven[0] == center and set(seven) == {center} | set(ring)


def test_dislike_starting_tiles_overlap_semantics():
    """Le test final est un CHEVAUCHEMENT d'ensembles (`ContainsAnyOf`), pas une egalite, et il
    rend le POIDS BC quand il mord.

    ⚠ Le data-gap « poids toujours 0.0 » que cette garde verrouillait est LEVE (#343) : la
    categorie `Default/DislikeStartingTilesUtility` porte `ActiveAbility_DislikesCurrentTiles`, et
    le natif QUITTE sa tuile de depart a utilite autrement egale (mesure `probe_343_*` sur 1194).
    Ce qui reste verrouille ici : la SEMANTIQUE (chevauchement, pas egalite) et le fait qu'un
    contexte SANS weights ne fabrique aucune penalite."""
    u = DislikeStartingTilesUtility()

    class _W:
        def sub(self, cat, key):
            assert (cat, key) == (u.WEIGHT_CATEGORY, u.WEIGHT_KEY)
            return -40

    wt = _W()
    assert u.evaluate(_Ctx(origin=(3, 4), wt=wt), (3, 4)) == -40.0   # chevauchement -> poids
    assert u.evaluate(_Ctx(origin=(3, 4), wt=wt), (5, 5)) == 0.0     # disjoint -> 0
    assert u.evaluate(_Ctx(wt=wt), (3, 4)) == 0.0        # pas d'origine connue -> jamais de penalite
    assert u.evaluate(_Ctx(origin=(3, 4)), (3, 4)) == 0.0  # poids NON LU -> 0, pas d'invention
    # `feet_count == 7` : l'empreinte candidate est l'ANNEAU -> le chevauchement mord depuis un voisin.
    board = _flat_board()
    center = (3, 4)
    ring = [board.coord(t) for t in board.neighbours_native(board.id_at(*center))]
    ctx7 = _Ctx(origin=center, feet_count=7, neigh_by_pos={ring[0]: [center]}, wt=wt)
    assert u.evaluate(ctx7, ring[0]) == -40.0
