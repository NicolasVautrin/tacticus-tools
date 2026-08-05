"""`Edge` -- les SIX ARETES d'un hexagone (`IdunBattle.Utils.Hex.Edge`).

Mirror 1:1 de l'enum natif, re-derivable de `data/symbols/<build>/frida/enums.tsv`.

CE QU'IL DESIGNE, ET COMMENT ON LE SAIT. C'est le type DECLARE du parametre `direction` de

    IdunBattle.Utils.Hex.AxialCoordinate.NeighbourAt
        (direction : IdunBattle.Utils.Hex.Edge)

LU dans la table des methodes du build (`frida/methods.tsv`), pas deduit d'un nom court. Les
deux autres porteurs de la meme signature le confirment :
`IdunBattle.Utils.Hex.CubeCoordinate.NeighbourAt` (parametre nomme `edge`) et
`IdunBattle.Entities.Components.PositionComponent.NeighbourAt`.

⚠ LA CLE D'APPARIEMENT EST LE NOM PLEIN, jamais le nom court : le build porte un SECOND enum
appele `Edge` (`UnityEngine.RectTransform.Edge`, 4 valeurs Left/Right/Top/Bottom). Le nom court
aurait apparie faux -- c'est exactement le piege deja rencontre sur `Corner` (cinq homonymes).

⚠ LE NOM DESIGNE, IL NE DECRIT PAS L'ECRAN. Les tables de deltas du port travaillent dans le
repere offset odd-q de `hexgeo`, dont l'axe des lignes est INVERSE par rapport au libelle natif :
`Edge.North` (0) y pointe vers le BAS de la grille (mesure live #90). Un commentaire de site qui
ecrit `{N, SE, SW}` pour `(South, North_East, North_West)` decrit donc l'ECRAN du port, pas
l'ordinal -- les deux coexistent et ne se contredisent pas.

CE QU'IL FAUT PORTER, ET CE QU'IL NE FAUT PAS. Les VALEURS de `_TRIANGLE_SHAPE_DIRECTIONS`
(`entities/selectors/geometry.py`) et les deux listes de directions de `DevastatingRefrainAbility`
(`runner/abilities/sisterhood.py`) sont des `Edge` : elles sont passees a `NeighbourAt` /
`TileFromVector`. Le tuple `_CUBE_DIRECTIONS` du meme fichier, lui, ne l'est PAS : ses elements
sont les DELTAS cubiques (-1/0/+1) -- c'est son INDEX qui est un `Edge`.
"""
from __future__ import annotations

from enum import IntEnum


class Edge(IntEnum):
    """`IdunBattle.Utils.Hex.Edge` -- VERBATIM du build (6 valeurs, aucun alias)."""

    North = 0
    North_East = 1
    South_East = 2
    South = 3
    South_West = 4
    North_West = 5
