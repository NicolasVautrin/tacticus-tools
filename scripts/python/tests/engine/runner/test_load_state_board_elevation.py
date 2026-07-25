"""GARDE ANTI-REGRESSION de la CLASSE DE BUG #63/#64 (OFFLINE, pas de session live).

Cause racine #63 : les feuilles POSITIONNELLES du combat (bonus d'ELEVATION
`IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`, trench, LightCover, GetStuckIn) sont des
no-op SILENCIEUX offline quand `state.board` n'est pas peuple. Un `state.board = board`
oublie dans un helper de replay a produit le faux diagnostic "divergence armure 0.58".

#64 : le board est desormais peuple A LA SOURCE via `load_state(..., board=board)` (point
d'injection unique). Ce test verrouille le contrat : `load_state` avec `board=` attache le
board -> la feuille d'ELEVATION FIRE ; sans board -> elle reste un no-op fidele (mods
inchange). Purement offline (synthetique) : aucun runner, aucune RPC, deterministe.
"""
from __future__ import annotations

from engine.runner.snapshot import load_state
from engine.runner.damage_model import apply_elevation_bonus
from engine.services.damage_modifiers import DamageModifiers
from engine.entities.pathfinding.board import Board

# Deux tuiles adjacentes : attaquant EN SURPLOMB (elev 2) sur la cible (elev 0).
_TILES = [
    {"id": 1, "col": 0, "row": 0, "elevation": 2, "walkable": True, "isWall": False, "neighbours": [2]},
    {"id": 2, "col": 1, "row": 0, "elevation": 0, "walkable": True, "isWall": False, "neighbours": [1]},
]
# attaquant (owner 1) sur la tuile haute ; cible (owner 2) sur la tuile basse.
_DECISION = {
    "currentPlayer": 1,
    "units": [
        {"id": 10, "visualId": "necroDestroyer", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 0}, "effects": []},
        {"id": 20, "visualId": "necroOverlord", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 1, "row": 0}, "effects": []},
    ],
}
_OBSERVE = {"units": [{"squadId": 10, "hp": 1000, "hpMax": 1000},
                      {"squadId": 20, "hp": 8000, "hpMax": 8000}]}


def test_load_state_board_arms_elevation_leaf():
    """`load_state(..., board=board)` -> `state.board` pose -> la feuille d'ELEVATION ajoute un
    modificateur %-increase (attaquant en surplomb). C'est la garantie du fix #64."""
    board = Board(_TILES, adjacency="native_sym")
    state = load_state(_DECISION, _OBSERVE, board=board)
    assert state.board is board, "load_state n'a pas attache le board passe en parametre"
    mods = DamageModifiers()
    apply_elevation_bonus(state, mods, attacker_id=10, target_id=20)
    assert mods.pct_list, (
        "feuille d'ELEVATION no-op alors que board+surplomb presents -> le bonus positionnel "
        "n'est PAS arme (regression du contrat load_state board=)")


def test_load_state_without_board_leaf_is_noop():
    """Contre-epreuve : SANS board, `state.board` reste None -> la feuille d'ELEVATION est un
    no-op FIDELE (mods inchange). Prouve que c'est bien le board qui arme la feuille (pas autre
    chose), et documente le comportement quand le board est absent."""
    state = load_state(_DECISION, _OBSERVE)
    assert state.board is None
    mods = DamageModifiers()
    apply_elevation_bonus(state, mods, attacker_id=10, target_id=20)
    assert not mods.pct_list and mods.additive == 0.0, (
        "feuille d'ELEVATION a mute mods sans board -> ne degrade pas en no-op fidele")


def test_load_state_board_none_equivalent_to_omitted():
    """`board=None` explicite == parametre omis (retro-compat) : state.board reste None."""
    assert load_state(_DECISION, _OBSERVE, board=None).board is None
    assert load_state(_DECISION, _OBSERVE, None, None).board is None
