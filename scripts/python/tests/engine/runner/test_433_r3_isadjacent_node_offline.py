"""GARDE #433-r3 (OFFLINE PURE) -- le noeud DSL `IsAdjacent` est un UNIVERSEL, et il porte la
porte d'ELEVATION.

`IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger`, lu au decompile :

    A = <sel a>.Select(entities, selectionType)      // slot 3 ; ctor : a@+0x20, b@+0x28,
    B = <sel b>.Select(entities, selectionType)      //          selectionType@+0x18, query@+0x10
    if (A == null || B == null) throw;
    if (!A.Any() || !B.Any()) return false;
    foreach (x in A) foreach (y in B)
        if (!query.AreEntitiesAdjacent(x, y)) return false;      // slot 0x60
    return true;

CE QUE CE FICHIER PROTEGE, et pourquoi chaque point regresse EN SILENCE :

  1. **Le QUANTIFICATEUR.** Le natif rend FAUX des qu'UNE paire ne l'est pas -- un `forall`. Un
     `any` declenche des triggers que le natif REFUSE : degradation PERMISSIVE, sans erreur ni
     crash. La classe SOEUR `IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger`
     est, elle, un `exists` : les deux ne se deduisent pas l'une de l'autre, elles se LISENT.
  2. **Le VIDE.** Le natif teste `Any()` AVANT la boucle et rend FAUX. Un `all(...)` nu rendrait
     VRAI sur une liste vide -- exactement l'inverse.
  3. **La porte d'ELEVATION et le court-circuit d'IDENTITE**, foldes dans
     `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` = `(|dElev| < 2) & (t1 == t2 ||
     IsNeighbour(t1, t2))`. Le noeud delegue au foyer `services/battle_query.py::are_tiles_adjacent`
     (#433-r1) : aucun 5e mirror d'adjacence.
  4. **Le 3e argument de la factory reste INERTE pour le predicat.** `selectionType`
     (`UnitSelectionType`) part au SELECTEUR (2e argument de son `Select`, slot 3) ; le cabler dans
     la comparaison par paire est la faute que la fiche #433-r1 anticipait.

Confrontation LIVE (mesuree) : `python scripts/python/probe_433_r3_isadjacent_node.py` -- etage MOVE
de `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour`
(`If(Not(IsAdjacent(caster, target)), MoveUnit(caster, dest))`). MC1_67 : caster (1,2) elev 2,
cible (1,3) elev 4 -- le natif CHARGE en (2,3), le port en accord ; sous `--mutate` (retour a
`any(hexgeo.distance == 1)`) le port ne bouge pas -> `DESACCORD port=(1,2) natif=(2,3)`.
RE : `docs/rl/case-433-r3-isadjacent-noeud-dsl.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.dsl.base import DslContext                                   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.entities.selectors.accessors import Target
from engine.entities.selectors.tiles import AllAliveUnits, Caster  # noqa: E402
from engine.entities.triggers import IsAdjacent                          # noqa: E402

COLS, ROWS = 7, 7
CENTER = (3, 3)
NEIGH = (3, 4)          # voisine hex de CENTER dans cette geometrie (assertion de montage)
FAR = (0, 0)


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board(elev_by_pos=None) -> Board:
    """Board au format `boardGraph`, adjacence GEOMETRIQUE (`evenq`) : c'est le mode qui laisse la
    porte d'elevation OBSERVABLE. En `native_sym` elle est deja bakee dans le champ `neighbours`
    capte (cf. `runner/abilities/ultramarines.py`), donc un board `native_sym` ne pourrait pas
    distinguer un port qui porte la porte d'un port qui l'ignore."""
    elev_by_pos = elev_by_pos or {}
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row,
                          "elevation": int(elev_by_pos.get((col, row), 0)),
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _unit(uid: int, pos, team: int = 1) -> dict:
    return {"id": uid, "team": team, "player": team, "alive": True, "hp": 1000,
            "pos": ({"col": pos[0], "row": pos[1]} if pos else None), "visualId": "u%d" % uid}


def _ctx(units, caster=None, target=None, board=None) -> DslContext:
    return DslContext(units=list(units), caster=caster, target=target, board=board)


@pytest.fixture
def flat():
    return _board()


def test_montage_neighbours():
    """MONTAGE, pas une mesure : sans cette adjacence geometrique, tout le fichier ne dirait rien."""
    b = _board()
    assert b.id_at(*NEIGH) in set(b.neighbours(b.id_at(*CENTER)))
    assert hexgeo.distance(CENTER, NEIGH) == 1
    assert hexgeo.distance(CENTER, FAR) > 1


# ------------------------------------------------------------------ (Q) le quantificateur

def test_forall_faux_des_qu_une_paire_ne_l_est_pas(flat):
    """`foreach x foreach y : if (!adj) return false` -- une paire NON adjacente suffit a fermer,
    meme si une autre l'est. C'est la divergence PERMISSIVE du `any` d'avant."""
    near, far = _unit(1, CENTER), _unit(2, FAR)
    tgt = _unit(3, NEIGH, team=2)
    ctx = _ctx([near, far, tgt], caster=near, target=tgt, board=flat)
    assert IsAdjacent(AllAliveUnits(), Target()).evaluate(ctx) is False


def test_forall_vrai_quand_toutes_les_paires_le_sont(flat):
    near = _unit(1, CENTER)
    tgt = _unit(3, NEIGH, team=2)
    ctx = _ctx([near, tgt], caster=near, target=tgt, board=flat)
    assert IsAdjacent(AllAliveUnits(), Target()).evaluate(ctx) is True


# ------------------------------------------------------------------ le VIDE

def test_liste_vide_rend_faux_pas_vrai(flat):
    """`if (!A.Any() || !B.Any()) return false` -- un `all(...)` nu rendrait VRAI sur le vide."""
    cst = _unit(1, CENTER)
    assert IsAdjacent(Caster(), Target()).evaluate(_ctx([cst], cst, None, flat)) is False
    assert IsAdjacent(Target(), Caster()).evaluate(_ctx([cst], cst, None, flat)) is False


def test_entite_sans_tuile_ferme_le_forall(flat):
    """`GetTiles` rend une liste VIDE -> la double boucle d'`AreTilesAdjacent(IList, IList)` ne
    tourne pas -> la paire n'est PAS adjacente -> le `forall` rend FAUX."""
    cst, orphan = _unit(1, CENTER), _unit(4, None, team=2)
    assert IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, orphan], cst, orphan, flat)) is False


# ------------------------------------------------------------------ (E) la porte d'elevation

@pytest.mark.parametrize("delta,attendu", [(0, True), (1, True), (2, False), (3, False)])
def test_porte_d_elevation(delta, attendu):
    """`(dElev < 2) & b` : la comparaison est `< 2`, pas `<= 2` ni `< 1`. Les deux bornes sont
    testees -- un port qui gaterait a `|dElev| >= 1` passerait un test qui n'exercerait que 0 et 2."""
    board = _board(elev_by_pos={NEIGH: delta})
    cst, tgt = _unit(1, CENTER), _unit(2, NEIGH, team=2)
    got = IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, tgt], cst, tgt, board))
    assert got is attendu


def test_elevation_ne_recree_pas_l_adjacence_a_distance():
    """Deux tuiles a MEME elevation mais NON voisines restent non adjacentes (la porte est un
    conjoint, pas le predicat)."""
    board = _board()
    cst, tgt = _unit(1, CENTER), _unit(2, FAR, team=2)
    assert IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, tgt], cst, tgt, board)) is False


# ------------------------------------------------------------------ (I) l'identite

def test_court_circuit_d_identite(flat):
    """`tile1 == tile2` rend VRAI sans consulter la connectivite, et `|dElev| = 0 < 2` ne peut pas
    le contredire (#433-r1). Herite du foyer, exerce ICI depuis le noeud."""
    cst = _unit(1, CENTER)
    assert IsAdjacent(Caster(), Caster()).evaluate(_ctx([cst], cst, None, flat)) is True


def test_identite_vaut_aussi_sur_une_tuile_surelevee():
    """Sur une MEME tuile `dElev = 0` quelle que soit son elevation absolue -- la porte ne peut
    donc jamais fermer le court-circuit."""
    board = _board(elev_by_pos={CENTER: 5})
    cst = _unit(1, CENTER)
    assert IsAdjacent(Caster(), Caster()).evaluate(_ctx([cst], cst, None, board)) is True


# ------------------------------------------------------------------ le 3e argument

@pytest.mark.parametrize("target_pos", [NEIGH, (3, 2)])
def test_le_3e_argument_est_inerte_pour_le_predicat(target_pos):
    """`selectionType` part au SELECTEUR (2e argument de son `Select`, slot 3). Le verdict ne doit
    pas VARIER avec lui -- le cabler en seuil de distance est la faute anticipee par #433-r1."""
    board = _board(elev_by_pos={NEIGH: 2})
    cst, tgt = _unit(1, CENTER), _unit(2, target_pos, team=2)
    verdicts = {sel: IsAdjacent(Caster(), Target(), sel).evaluate(
        _ctx([cst, tgt], cst, tgt, board)) for sel in (None, 0, 1, 2, 3)}
    assert len(set(verdicts.values())) == 1, verdicts


# ------------------------------------------------------------------ degradation SANS board

def test_sans_board_adjacence_hex_pure():
    """`ctx.board = None` -> convention du depot : adjacence hex pure (sure sur un board PLAT, ou
    `|dElev| = 0 < 2` partout). Le court-circuit d'identite, lui, vaut DANS LES DEUX branches."""
    cst = _unit(1, CENTER)
    near, far = _unit(2, NEIGH, team=2), _unit(3, FAR, team=2)
    assert IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, near], cst, near, None)) is True
    assert IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, far], cst, far, None)) is False
    assert IsAdjacent(Caster(), Caster()).evaluate(_ctx([cst], cst, None, None)) is True
