"""#448-r1-r1-r1-r1-r2 OFFLINE -- le CONTRAT du canal brut `ConnectivityComponent`.

Le capteur qui alimente ce canal (`connectivity` / `teleportTwinTileId` du RPC `boardGraph`)
exige une fenetre de reinjection pour tirer. Ces crans-la, eux, ne l'exigent PAS : ils
verrouillent le contrat du LECTEUR (`Board.neighbours_connectivity` / `Board.teleport_twin`),
c'est-a-dire tout ce qui peut se casser sans qu'aucun capteur ne soit en cause.

Le cran central est le TRI-ETAT. `#381-r3` a deja paye, sur le champ `neighbours`, la confusion
« absent == vide » : le repli inventait six voisins la ou le natif n'en a aucun. Ici la meme
faute serait PIRE -- un repli silencieux sur `neighbours_native()` rendrait precisement le champ
AMPUTE que ce canal existe pour contourner, donc le bug se deguiserait en correctif.

ASCII only (cp1252).
"""
from __future__ import annotations

from engine.entities.pathfinding.board import Board

# Bande 4x1. `neighbours` (le champ AMPUTE, capte via `TileQuery$$IterateAdjacentTiles` et sa
# porte `|dElev| < 2`) omet l'arete 2<->3 ; `connectivity` (le canal BRUT, la liste stockee du
# `ConnectivityComponent`) la porte. C'est exactement la forme mesuree sur `MC1_67` : 18 aretes
# dirigees presentes cote natif et absentes du champ herite.
_ROW = [
    {"id": 1, "col": 0, "row": 0, "elevation": 0, "walkable": True, "isWall": False,
     "neighbours": [2], "connectivity": [2], "teleportTwinTileId": 0},
    {"id": 2, "col": 1, "row": 0, "elevation": 0, "walkable": True, "isWall": False,
     "neighbours": [1], "connectivity": [1, 3], "teleportTwinTileId": 0},
    {"id": 3, "col": 2, "row": 0, "elevation": 2, "walkable": True, "isWall": False,
     "neighbours": [4], "connectivity": [2, 4], "teleportTwinTileId": 0},
    {"id": 4, "col": 3, "row": 0, "elevation": 2, "walkable": True, "isWall": False,
     "neighbours": [3], "connectivity": [3], "teleportTwinTileId": 0},
]


def _rows():
    return [dict(t) for t in _ROW]


def test_le_canal_brut_porte_l_arete_que_le_champ_ampute_omet():
    """La raison d'etre du canal : la marche 2->3 (delta d'elevation 2) EXISTE cote natif."""
    b = Board(_rows(), adjacency="evenq")
    assert b.neighbours_native(2) == [1]              # champ herite, ampute par la porte
    assert b.neighbours_connectivity(2) == [1, 3]     # canal brut, la liste stockee


def test_canal_ABSENT_rend_None_et_NE_retombe_PAS_sur_le_champ_ampute():
    """Le point qui compte. Un repli sur `neighbours_native()` rendrait le graphe AMPUTE en se
    faisant passer pour le graphe natif -- un bug deguise en correctif, invisible."""
    tiles = [{k: v for k, v in t.items() if k != "connectivity"} for t in _ROW]
    b = Board(tiles, adjacency="evenq")
    assert b.neighbours_connectivity(2) is None
    assert b.neighbours_native(2) == [1]              # l'autre canal, lui, repond toujours


def test_canal_VIDE_rend_une_liste_vide_pas_None():
    """Legitime cote natif : une tuile dont le `ConnectivityComponent` ne relie rien. `[]` et
    `None` ne veulent pas dire la meme chose et ne doivent jamais se confondre."""
    tiles = _rows()
    tiles[1]["connectivity"] = []
    b = Board(tiles, adjacency="evenq")
    assert b.neighbours_connectivity(2) == []
    assert b.neighbours_connectivity(2) is not None


def test_le_canal_filtre_les_ids_hors_board():
    """Meme discipline que `neighbours_native` : un id absent du board est ecarte, pas propage."""
    tiles = _rows()
    tiles[0]["connectivity"] = [2, 999]
    b = Board(tiles, adjacency="evenq")
    assert b.neighbours_connectivity(1) == [2]


def test_teleport_twin_tri_etat():
    """`0` cote natif = « pas une tuile de teleport » (la valeur exacte que testent les quatre
    surcharges de `TileExtensions$$IsTeleportationTile`) -> `None`, jamais un id `0`."""
    b0 = Board(_rows(), adjacency="evenq")
    assert b0.teleport_twin(1) is None                # champ present, valeur 0

    tiles = _rows()
    tiles[0]["teleportTwinTileId"] = 4
    tiles[3]["teleportTwinTileId"] = 1
    b1 = Board(tiles, adjacency="evenq")
    assert b1.teleport_twin(1) == 4
    assert b1.teleport_twin(4) == 1                   # les deux se pointent mutuellement
    assert b1.teleport_twin(2) is None

    absent = Board([{k: v for k, v in t.items() if k != "teleportTwinTileId"} for t in _ROW],
                   adjacency="evenq")
    assert absent.teleport_twin(1) is None


def test_aucun_pathfinder_n_est_rebranche_sur_le_canal():
    """Garde de PERIMETRE. Rebrancher un pathfinder sur ce canal change des resultats
    observables et doit etre MESURE live -- le faire avant la fenetre serait speculatif. Ce cran
    rougit si quelqu'un le fait sans passer par la mesure : il verifie que la marche voit
    toujours le champ herite, arete 2->3 comprise (absente)."""
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions

    b = Board(_rows(), adjacency="evenq")
    _vis, stop = get_movable_positions(b, 1, 5, {}, 1)
    assert stop == {2}, stop
