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

⚠ **LE PORT LIT POURTANT LA GEOMETRIE, ET C'EST LA MESURE QUI L'IMPOSE.** Le champ `neighbours`
du `boardGraph` n'est PAS le `ConnectivityComponent` : le capteur passe par
`IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`, dont la porte `|delta elev| < 2` est
INCONDITIONNELLE -- il publie donc une version AMPUTEE des marches d'elevation. Mesure sur
`MC1_67` (`probe_448_r1_r1_r1_r1_flying_tiles_moved.py --diag`) : **18 aretes dirigees**
geometriques absentes du champ, TOUTES des marches `2 <-> 4`.

Le natif prouve que ces aretes existent chez lui : sur le mouvement `(1,1) -> (1,3)` d'un volant
(`d = 2`), il enregistre **2** tuiles -- ce qui exige un chemin de deux aretes, donc l'arete
`(1,2)-(1,3)` que le champ `neighbours` ne porte pas. Avec le champ, le port rendait **3**.
La geometrie est donc le proxy MESURE du `ConnectivityComponent` reel, et le champ capte en est
une sous-approximation. RESIDU NOMME dans l'autre sens : le `ConnectivityComponent` peut
legitimement NE PAS relier deux tuiles geometriquement voisines (mesure `#381-r3` : les deux
`Bridge` de `C1_74`, 4 aretes sur 74) -- la beeline du port y couperait ou le natif ferait le
tour. Aucun board mesure ici n'est dans ce cas.

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

    Le voisinage est la GEOMETRIE et non le champ `neighbours` capte -- cf. l'en-tete du module
    (le champ est une version amputee du `ConnectivityComponent`, et la mesure native tranche)."""
    occ = occupants or {}
    return _base.find_path(
        board, from_id, to_id,
        edge=is_valid_path_node,
        neighbours=board.neighbours_geometric,
        weight_cost=lambda tid: weight_cost(tid in occ),
        is_valid_final_tile=lambda tid: is_valid_final_tile(board, tid))
