"""#381-r3 OFFLINE -- les deux sources de voisinage, sur un board SYNTHETIQUE (sans runner).

Verrouille les quatre proprietes que le live ne peut pas isoler proprement :

  1. le BFS de MARCHE enumere la liste STOCKEE (`BasePathfinder$$AddNeighbours`), QUEL QUE SOIT le
     `adjacency=` du `Board` ;
  2. le BFS de VOL interroge la GEOMETRIE (`FlyPathfinder$$AddNeighbours`), idem ;
  3. `neighbours_geometric` ne depend pas du mode ;
  4. champ `neighbours` **ABSENT** != champ **VIDE** -- le premier retombe sur `neighbours()`
     (boards fabriques a la main), le second rend `[]`. Les confondre inventait six voisins la ou
     le natif n'en a aucun, et c'est un cas REEL : la porte `|dElev| < 2` INCONDITIONNELLE de
     `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` vide le champ des tuiles en creux
     (mesure `C1_74` : les deux `Water` d'elevation 1 entourees de 3 et 4).

ASCII only (cp1252).
"""
from __future__ import annotations

from engine.entities.pathfinding.board import Board
from engine.entities.pathfinding.fly_pathfinder import get_movable_positions as fly_positions
from engine.entities.pathfinding.walk_pathfinder import get_movable_positions as walk_positions

# Bande 4x1 a plat. La liste STOCKEE omet volontairement l'arete 2<->3 (le cas des deux `Bridge`
# de `C1_74`, que le `ConnectivityComponent` ne relie pas a leur voisin de meme niveau).
_ROW = [
    {"id": 1, "col": 0, "row": 0, "elevation": 0, "walkable": True, "isWall": False,
     "neighbours": [2]},
    {"id": 2, "col": 1, "row": 0, "elevation": 0, "walkable": True, "isWall": False,
     "neighbours": [1]},
    {"id": 3, "col": 2, "row": 0, "elevation": 0, "walkable": True, "isWall": False,
     "neighbours": [4]},
    {"id": 4, "col": 3, "row": 0, "elevation": 0, "walkable": True, "isWall": False,
     "neighbours": [3]},
]


def _rows():
    return [dict(t) for t in _ROW]


def test_la_geometrie_ne_depend_pas_du_mode():
    for mode in ("evenq", "native", "native_sym"):
        b = Board(_rows(), adjacency=mode)
        assert b.neighbours_geometric(2) == [1, 3], mode
        assert b.neighbours_geometric(1) == [2], mode


def test_la_liste_stockee_ne_depend_pas_du_mode():
    for mode in ("evenq", "native", "native_sym"):
        b = Board(_rows(), adjacency=mode)
        assert b.neighbours_native(2) == [1], mode
        assert b.neighbours_native(3) == [4], mode


def test_la_marche_lit_la_liste_stockee_meme_sous_evenq():
    """Sous `adjacency="evenq"` (le montage de TOUS les probes), le BFS de marche traversait
    l'arete 2->3 que la liste stockee ne porte pas -- c'est la SUR-ATTEINTE de `#381-r3`."""
    b = Board(_rows(), adjacency="evenq")
    _vis, stop = walk_positions(b, 1, 5, {}, 1)
    assert stop == {2}, stop
    # contre-epreuve : monte sur la geometrie, la marche atteint toute la bande
    _vis2, stop2 = walk_positions(b, 1, 5, {}, 1, neighbours=b.neighbours_geometric)
    assert stop2 == {2, 3, 4}, stop2


def test_le_vol_lit_la_geometrie_meme_sous_native_sym():
    """Sous `adjacency="native_sym"` (le montage de PRODUCTION, `playbook/scene.py`), le vol
    heritait de la liste stockee et SOUS-atteignait."""
    b = Board(_rows(), adjacency="native_sym")
    _vis, stop = fly_positions(b, 1, 5, {}, 1)
    assert stop == {2, 3, 4}, stop


def test_champ_ABSENT_retombe_sur_le_mode():
    """Board fabrique a la main (aucun champ `neighbours`) : le repli historique tient."""
    tiles = [{k: v for k, v in t.items() if k != "neighbours"} for t in _ROW]
    b = Board(tiles, adjacency="evenq")
    assert b.neighbours_native(2) == [1, 3]
    _vis, stop = walk_positions(b, 1, 5, {}, 1)
    assert stop == {2, 3, 4}, stop


def test_champ_VIDE_rend_le_vide():
    """Le cas reel des tuiles en creux : le capteur a tout filtre par elevation. Rendre `[]` est
    EXACT -- `IsValidPathNode` refuserait ces memes aretes."""
    tiles = _rows()
    tiles[1]["neighbours"] = []                       # la tuile 2 est un cul-de-sac stocke
    b = Board(tiles, adjacency="evenq")
    assert b.neighbours_native(2) == []
    _vis, stop = walk_positions(b, 1, 5, {}, 1)
    assert stop == {2}, stop                          # on y ENTRE (arete 1->2), on n'en SORT pas


def test_le_vide_n_est_pas_l_absence():
    """La distinction elle-meme, sur le seul accesseur -- sans passer par un BFS."""
    absent = Board([{k: v for k, v in t.items() if k != "neighbours"} for t in _ROW],
                   adjacency="evenq")
    vide = Board([dict(t, neighbours=[]) for t in _ROW], adjacency="evenq")
    assert absent.neighbours_native(2) == [1, 3]
    assert vide.neighbours_native(2) == []
