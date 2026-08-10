"""GARDE des SEPT GATES AMONT d'`IdunBattle.Operations.MoveUnitOperation$$Execute`, de la branche
`allowNullTargetPosition` (#448-r1-r1-r2-r2-r1) et du modele de RESERVATION (#550-r1).

Le montage vit dans le probe (`probe_448r1r1r2r2r1_gates_amont.py`), que ce fichier IMPORTE : pas
de fork.

⚠ **CES SEPT GATES SONT PERMISSIFS QUAND ILS MANQUENT** -- ni erreur, ni crash, l'unite bouge
simplement la ou le natif refuse. C'est invisible en self-play et c'est exactement le trou qu'un
entrainement irait exploiter. Le fichier garde donc DEUX choses : que chaque gate MORD (etage 1),
et que chacun est encore CABLE dans `execute` (etage 3, par AST) -- un refactor qui en decrocherait
un rouvrirait le gisement en silence.

⚠ **L'etage 2 est le seul qui prouve que l'etage 1 mesure quelque chose** : il rejoue le volet
offline sous CINQ neutralisations et exige que les cinq ROUGISSENT. Un bras vert sous sa mutation
serait un montage inerte deguise en preuve.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import probe_448r1r1r2r2r1_gates_amont as P
from engine.runner.operations import tile_reservation as TR
from engine.runner.state import State

#: Ce fichier ne peut pas changer de verdict SANS qu'un de ces chemins bouge.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/movement.py",
        "scripts/python/engine/runner/operations/tile_reservation.py",
        "scripts/python/engine/runner/operations/remove_unit_from_tiles.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/state.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/pathfinding/board.py",
        # HOMONYME, et c'est le piege : `scripts/python/board.py` (le choix de board du
        # runner) n'est PAS `engine/entities/pathfinding/board.py` ci-dessus. Il est bien
        # importe par ce fichier, et son absence rendait le declencheur TROP ETROIT --
        # `probe_486r15_declencheurs_tests.py` le disait, sur `master`, depuis #869.
        "scripts/python/board.py",
        "scripts/python/probe_448r1r1r2r2r1_gates_amont.py",
        "scripts/python/probe_448r1r1r2r2_gates_abandon.py",
        "data/boards/pvp/C4_09.json",
        "data/boards/pvp/C3_23.json",
        # #547-r2 : LU a l'execution (chargement du board), pas importe -- l'empreinte REECRITE
        # en entier l'a montre, l'ancienne le cachait.
        "scripts/python/board.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Les sept gates vivent dans `movement.py`, leurs substrats dans `tile_reservation.py` "
              "(reservation), `turnflow.py` (`_can_move`), `components.py` (`UnitFlagsComponent.FLED`, "
              "`get_unit_feet`), `state.py` (le slot `tile_reservations`) et `board.py` (walkable). "
              "La branche lift-off consomme `remove_unit_from_tiles.py`. Les deux dumps de board sont "
              "les entrees LUES : `C4_09` pour la geometrie, `C3_23` parce qu'il porte des tuiles "
              "`ForceUnplayable` (le bras `walkable == False` de `BattleQuery$$IsWalkableTile`), que "
              "`C4_09` n'a pas. Aucune dependance au build ni au jeu.",
}

_MOVEMENT = (pathlib.Path(__file__).resolve().parents[3]
             / "engine" / "runner" / "operations" / "movement.py")

#: Les sept gates, par le NOM du natif qu'ils mirroitent et par celui du helper porte. La table est
#: figee ICI et non derivee du module : c'est elle qui rougit si un helper DISPARAIT.
GATES = (
    ("IsAllowedToMove", "_is_allowed_to_move"),
    ("UnitIsOnTiles", "_unit_is_on_tiles"),
    ("TilesAreWalkable", "_tiles_are_walkable"),
    ("TilesMatchUnitFeetCount", "_tiles_match_unit_feet_count"),
    ("IsDisallowedEmptyPosition", "_is_disallowed_empty_position"),
    ("IsPositionReservedForOtherUnit", "_is_position_reserved_for_other_unit"),
    ("IsPositionReservedForDrafting", "_is_position_reserved_for_drafting"),
)


# ------------------------------------------------------------------ 1. les gates MORDENT
def test_1_le_volet_offline_du_probe_est_integralement_vert():
    """Onze bras : les trois etages de G1, G2, les deux bras de G3, G5 + le LIFT-OFF, G6 et son
    cycle Set/Remove, les DEUX polarites opposees, et l'extinction par `enforce_native_gates`."""
    assert P.volet_offline(P.BOARD_ID) == 0


# ------------------------------------------------------------------ 2. la CONTRE-EPREUVE
def test_2_les_cinq_mutants_rougissent():
    """Sans ce controle, l'etage 1 pourrait etre vert parce qu'il ne mesure RIEN."""
    verts = P.volet_mutants(P.BOARD_ID)
    assert verts == 0, "mutant(s) reste(s) VERT(s) : le bras correspondant est inerte"


# ------------------------------------------------------------------ 3. CLIQUET de cablage
def test_3_les_sept_gates_sont_APPELES_par_execute():
    """AST : chaque helper de gate est appele au moins une fois DANS
    `MoveUnitOperation.execute`. Un refactor qui en decrocherait un ne casserait rien
    d'observable -- le mouvement passerait simplement la ou le natif refuse."""
    tree = ast.parse(_MOVEMENT.read_text(encoding="utf-8"))
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "MoveUnitOperation")
    ex = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "execute")
    appeles = {n.func.id for n in ast.walk(ex)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    manquants = [h for _, h in GATES if h not in appeles]
    assert not manquants, "gate(s) DECABLE(S) de MoveUnitOperation.execute : %s" % manquants


def test_3b_chaque_gate_CITE_son_symbole_natif():
    """Le mirror doit rester lisible face au decompile : chaque helper nomme le natif qu'il
    mirroite, VERBATIM (`MoveUnitOperation$$<Nom>`)."""
    src = _MOVEMENT.read_text(encoding="utf-8")
    manquants = [n for n, _ in GATES if ("MoveUnitOperation$$%s" % n) not in src]
    assert not manquants, "symbole natif non cite : %s" % manquants


# ------------------------------------------------------------------ 4. le MODELE de reservation
def test_4_les_cinq_mirrors_de_reservation():
    """Mirror par mirror, sur un `State` NU (pas de board, pas d'unite) : le modele ne depend
    d'aucun substrat de plateau."""
    st = State()
    t = (3, 4)
    assert TR.is_tile_reserved(st, t) is False
    assert TR.is_tile_reserved_for_unit(st, t, 1) is False
    # `IsTileReservedForUnit` : le tout premier gate du decompile est `unit == null -> false`.
    assert TR.is_tile_reserved_for_unit(st, t, None) is False
    assert TR.reserve_for_unit(st, t, 1) is True
    assert TR.is_tile_reserved(st, t) is True
    assert TR.is_tile_reserved_for_unit(st, t, 1) is True
    assert TR.is_tile_reserved_for_unit(st, t, 2) is False
    # `RemoveReserveForUnit` : gate d'IDENTITE -- une autre unite ne libere rien.
    assert TR.remove_reserve_for_unit(st, t, 2) is False
    assert TR.is_tile_reserved(st, t) is True
    assert TR.remove_reserve_for_unit(st, t, 1) is True
    assert TR.is_tile_reserved(st, t) is False
    # `ReserveForUnit` ECRASE sans gate.
    TR.reserve_for_unit(st, t, 1)
    TR.reserve_for_unit(st, t, 2)
    assert TR.is_tile_reserved_for_unit(st, t, 2) is True


def test_4b_les_DEUX_polarites_opposees_sont_FIGEES():
    """⚠ LE POINT LE PLUS FACILE A « CORRIGER » PAR ERREUR.
    `TileExtensions$$IsTileReservedForOtherUnit(tile, allowedUnit)` calcule litteralement
    `!(HasValue && Value == allowedUnit.Id)` -- donc **VRAI sur une tuile NON reservee** -- tandis
    que `BattleQuery$$IsTileReservedForAnotherUnit(tiles, unit)` rend FAUX sur la meme tuile.
    Les deux sont LUS. Un lecteur qui alignerait le premier sur le second casserait
    `CanAddUnitFromAbility`, dont le `Reserve` amont d'`ItItches` depend."""
    st = State()
    t = (1, 1)
    assert TR.is_tile_reserved_for_another_unit(st, [t], 1) is False      # BattleQuery
    assert TR.is_tile_reserved_for_other_unit(st, t, 1) is True           # TileExtensions
    assert TR.is_tile_reserved_for_other_unit(st, t, None) is False       # branche allowedUnit null
    TR.reserve_for_unit(st, t, 1)
    assert TR.is_tile_reserved_for_another_unit(st, [t], 1) is False      # reservee pour MOI
    assert TR.is_tile_reserved_for_other_unit(st, t, 1) is False          # idem, les deux d'accord
    assert TR.is_tile_reserved_for_another_unit(st, [t], 2) is True       # reservee pour un AUTRE
    assert TR.is_tile_reserved_for_other_unit(st, t, 2) is True
    assert TR.is_tile_reserved_for_other_unit(st, t, None) is True        # `HasValue`


def test_4c_l_absence_de_cle_EST_le_nullable_vide():
    """Aucun chemin ne stocke `None` comme valeur : le dict ne porte que des reservations REELLES.
    Sans ce cran, `is_tile_reserved` rendrait vrai sur une tuile liberee."""
    st = State()
    TR.reserve_for_unit(st, (2, 2), 7)
    TR.remove_reserve_for_unit(st, (2, 2), 7)
    assert st.tile_reservations == {}, st.tile_reservations
    # `tile is None` -> aucun des cinq ne mute ni ne lit (le natif LEVE ; le port refuse en trace).
    assert TR.reserve_for_unit(st, None, 7) is False
    assert TR.is_tile_reserved(st, None) is False
    assert st.tile_reservations == {}


# ------------------------------------------------------------------ 5. le LIFT-OFF
def test_5_le_lift_off_retire_du_plateau_sans_tuer(tmp_path):
    """Branche `position.Count == 0` : `RemoveUnitFromTiles` + `EvaluateAfterMoveTriggers` avec
    `movementSteps = 0`, et RIEN d'autre -- ni `SetMovedFlag`, ni `RecordTilesMoved`, ni mort."""
    from engine.runner.components import UnitComponent, UnitFlagsComponent, get_unit_feet
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    board = P.P._load_board(P.BOARD_ID)
    a, _b, _c = P._voisines(board)
    st = P.P._state(board, [(1, a, 0, [])])
    op = MoveUnitOperation(1, None, allow_null_target_position=True)
    op.execute(st, EventBus())
    assert get_unit_feet(st, 1) == []                       # RETIREE du plateau
    assert st.get_entity(1).get_component(UnitComponent).alive is True    # PAS morte
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert not fl.has(UnitFlagsComponent.MOVED), "`SetMovedFlag` ne doit PAS etre joue"
    assert op.last_movement_steps == 0 and op.last_path is None
    assert op.last_abandoned == ""


@pytest.mark.parametrize("allow", [False, True])
def test_5b_le_lift_off_est_GARDE_par_son_octet(allow):
    """`MoveUnitOptions+0x15` est le SEUL gardien : sans lui, G5 refuse et l'unite reste."""
    from engine.runner.components import get_unit_feet
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    board = P.P._load_board(P.BOARD_ID)
    a, _b, _c = P._voisines(board)
    st = P.P._state(board, [(1, a, 0, [])])
    op = MoveUnitOperation(1, None, allow_null_target_position=allow)
    op.execute(st, EventBus())
    if allow:
        assert get_unit_feet(st, 1) == []
    else:
        assert get_unit_feet(st, 1) == [a]
        assert op.last_abandoned == "disallowed-empty-position"
