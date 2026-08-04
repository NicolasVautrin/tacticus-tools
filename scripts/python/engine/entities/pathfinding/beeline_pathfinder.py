"""`IdunBattle.Entities.Pathfinding.IgnoreEverythingPathfinder` -- le **`PathfinderType = 2`
(`Beeline`)**, celui qui ne sert qu'a une chose dans tout le moteur : RE-DENSIFIER le chemin
simplifie d'un volant, dans `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo`.

Il n'est atteignable par AUCUN `GetPathfinderTypeForUnit` -- son unique call-site passe le type
`2` EN DUR (`GetConnectedPathTo`, cf. `services/movement_query.get_connected_path_to`).

SES QUATRE SLOTS, RE-DERIVES AU RUNTIME (`resolveVtableSlot`, build `rnca9r7q6c`, vtable propre
depuis `+0x138` par pas de `0x10`) -- l'absence de ces methodes des tables de symboles ne prouvait
rien, IL2CPP DEDUPLIQUE les corps triviaux et c'est exactement ce qui se passe ici :

    idx 0x0b (@+0x1e8)  IsValidPathNode          -> corps TRIVIAL `return true`
    idx 0x09 (@+0x1c8)  IsValidFinalTile         -> corps TRIVIAL `return true`
    idx 0x0a (@+0x1d8)  IsValidContinuePathTile  -> corps TRIVIAL `return true`
    idx 0x0c (@+0x1f8)  WeightCost               -> `IgnoreEverythingPathfinder$$WeightCost`
    idx 0x07 (@+0x1a8)  FindPath                 -> `BasePathfinder$$FindPath` (aucun override)
    idx 0x10 (@+0x238)  AddNeighbours            -> `BasePathfinder$$AddNeighbours`

⇒ **il TRAVERSE TOUT, murs compris**, et accepte n'importe quelle destination. C'est ce qui fait
que la re-densification d'un chemin de vol COUPE a travers les obstacles au lieu de les longer :
entre deux waypoints, la longueur du sous-chemin est la distance dans le graphe d'adjacence, pas
la longueur du detour.

SON VOISINAGE EST, AU NATIF, LA LISTE **STOCKEE** (`BasePathfinder$$AddNeighbours` = le
`ConnectivityComponent`) -- contrairement au `FlyPathfinder` qui, lui, OVERRIDE ce slot.

SON SUBSTRAT EST LE CANAL BRUT DEPUIS `#448-r1-r1-r1-r1-r2-r1` -- et c'est LE site du port ou
ce rebranchement MORD, parce que son predicat d'arete est le corps trivial `return true` : il ne
re-filtre RIEN, donc toute arete de trop dans le voisinage devient un raccourci reel.

L'HISTORIQUE, en deux temps, parce qu'il explique les deux replis :

  1. Le port lisait le champ herite `neighbours`. Il est AMPUTE : le capteur passe par
     `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`, dont la porte `|delta elev| < 2`
     est INCONDITIONNELLE -- **18 aretes dirigees** de `MC1_67`, toutes des marches `2 <-> 4`.
     Le natif prouve qu'elles existent chez lui : sur `(1,1) -> (1,3)` d'un volant (`d = 2`) il
     enregistre **2** tuiles, ce qui exige l'arete `(1,2)-(1,3)`. Avec le champ, le port rendait
     **3**.
  2. Le port est passe a la GEOMETRIE, proxy MESURE du `ConnectivityComponent`. Elle en est un
     SUR-ensemble strict : le `ConnectivityComponent` ne relie pas deux tuiles geometriquement
     voisines quand `TileComponent$$HasEdge` refuse d'un cote -- les deux `Bridge` de `C1_74`,
     **16 aretes dirigees** (chaque `Bridge` a 6 voisins geometriques pour 2 aretes de
     connectivite : ses deux voisins dans l'axe du pont). La beeline geometrique y COUPE par le
     pont la ou le natif fait le tour. C'etait le residu nomme `#448-r1-r1-r1-r1-r2`.

⇒ le canal brut est le seul substrat juste des DEUX cotes, et l'ordre d'inclusion mesure sur trois
boards est `neighbours <= connectivity <= geometrie`. Le repli quand le canal n'est pas capte
reste la GEOMETRIE (le comportement du temps 2), jamais le champ herite : ce serait revenir au
temps 1, c'est-a-dire deguiser en correctif le bug que la mesure de SS9 avait ferme.

`IdunBattle.Entities.Pathfinding.IgnoreEverythingPathfinder$$WeightCost`, verbatim :

    return 10 + (tile.GetComponent<TileContentComponent>().IsFilled() ? 1 : 0);

et `IdunBattle.Entities.Components.TileContentComponent$$IsFilled` = `comp[+0x10] != 0`, c'est-a-
dire « une unite occupe la tuile ». Le +1 ne peut pas rallonger le chemin (une arete de plus coute
10) : il ne fait que DEPARTAGER deux chemins de meme longueur en faveur du moins encombre.
"""
from __future__ import annotations

from . import base_pathfinder as _base
from .board import Board

WEIGHT_BASE = 10          # `IgnoreEverythingPathfinder$$WeightCost` : cout nominal d'entree
WEIGHT_FILLED = 1         # ... + 1 quand `TileContentComponent$$IsFilled` (tuile occupee)


def weight_cost(is_filled: bool) -> int:
    """`IgnoreEverythingPathfinder$$WeightCost(unit, tile)` = `10 + IsFilled(tile)`."""
    return WEIGHT_BASE + (WEIGHT_FILLED if is_filled else 0)


def is_valid_path_node(board: Board, from_id: int, to_id: int) -> bool:
    """Le vslot `IsValidPathNode` (@+0x1e8), RE-DERIVE AU RUNTIME : corps TRIVIAL `return true`.
    Aucun test de mur, d'elevation, d'occupant ni de fog -- c'est le sens du nom de la classe."""
    return True


def is_valid_final_tile(board: Board, tile_id: int) -> bool:
    """Le vslot `IsValidFinalTile` (@+0x1c8), meme corps trivial `return true`."""
    return True


def find_path(board: Board, from_id, to_id, occupants=None) -> "list[int] | None":
    """`IPathfinders.GetPath(PathfinderType.Beeline, unit, from, to, null)` -- les tuiles du
    chemin, extremites INCLUSES, ou `None` si une extremite est hors board.

    `occupants` = `{tile_id -> team}` (le substrat de `IsFilled`) ; `None` -> aucune tuile
    occupee, ce qui ne change QUE le departage a longueur egale.

    Le voisinage est le `ConnectivityComponent` BRUT (`Board.base_add_neighbours`), avec repli sur
    la GEOMETRIE quand le canal n'est pas capte -- cf. l'en-tete du module pour les deux mesures
    qui imposent ce couple."""
    occ = occupants or {}
    return _base.find_path(
        board, from_id, to_id,
        edge=is_valid_path_node,
        neighbours=lambda tid: board.base_add_neighbours(tid, board.neighbours_geometric),
        weight_cost=lambda tid: weight_cost(tid in occ),
        is_valid_final_tile=lambda tid: is_valid_final_tile(board, tid))
