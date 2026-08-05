"""`Corner` -- les SIX COINS d'un hexagone (`IdunBattleLogic.Utils.Hex.Corner`).

Mirror 1:1 de l'enum natif, re-derivable de `data/symbols/<build>/frida/enums.tsv`.

CE QU'IL DESIGNE, ET COMMENT ON LE SAIT. C'est le type du parametre `direction` de

    IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape
        (startTile: IdunBattle.Core.IEntity, direction: IdunBattleLogic.Utils.Hex.Corner)

lu dans la table des methodes du build (`frida/methods.tsv`), pas deduit d'un nom. La meme
signature porte sur `RecordedSimulationRequestsBattleQuery$$GetTilesInTriangleShape`. Source
CONCORDANTE et independante : le noeud DSL qui l'alimente nomme son argument `cornerDirection`
(`IdunBattleLogic.Entities.DSLSelectors$$TilesInTriangleShape(start, cornerDirection)`).

TROISIEME source, purement geometrique : chaque coin est encadre par DEUX aretes
(`IdunBattle.Utils.Hex.Edge` -- le type du parametre d'`AxialCoordinate$$NeighbourAt`), et le
couple que le port lit dans le switch natif est exactement celui-la, coin par coin :

    NorthWest -> (North_West, North)     East      -> (North_East, South_East)
    NorthEast -> (North, North_East)     SouthWest -> (South_West, South)
    West      -> (North_West, South_West) SouthEast -> (South_East, South)

Aucun autre appariement des six valeurs ne produirait ces couples : l'attribution ne tient donc
pas au seul type declare.

⚠ LE NOM DESIGNE, IL NE DECRIT PAS L'ECRAN. Les tables de deltas du port travaillent dans le
repere offset odd-q de `hexgeo`, dont l'axe des lignes est INVERSE par rapport au libelle natif :
`Edge` 0 s'y lit `S` (mesure live #90, cf. `entities/selectors/geometry._CUBE_DIRECTIONS`).
`Corner.NorthWest` porte donc des deltas qui pointent vers le BAS de la grille du port. Le membre
reste le bon designateur -- c'est le nom que le build donne a cet ordinal -- mais ne pas le lire
comme une description d'orientation a l'ecran.

`IdunBattle.Utils.Hex.Edge` n'a PAS de mirror : ses seuls porteurs cotes port sont des ELEMENTS
DE CONTENEUR (le tuple `_CUBE_DIRECTIONS`, les couples valeurs de `_TRIANGLE_SHAPE_DIRECTIONS`),
role hors du perimetre des CLES -- residu `#270-r1-r1`.
"""
from __future__ import annotations

from enum import IntEnum


class Corner(IntEnum):
    """`IdunBattleLogic.Utils.Hex.Corner` -- VERBATIM du build (6 valeurs, aucun alias)."""

    NorthWest = 0
    NorthEast = 1
    West = 2
    East = 3
    SouthWest = 4
    SouthEast = 5
