"""Mirror de l'enum natif `IdunBattle.Entities.Enum.DistanceType` (build `rnca9r7q6c`,
`data/symbols/<build>/frida/enums.tsv` : `0=Simple,1=PathLength`).

Consommateur : le 4e argument de `IdunBattleLogic.Entities.DSLSelectors$$Nearest(entities, target,
pathfindingUnit, distanceType, maxDistance)`, que `IdunBattle.Entities.Selectors.NearestSelector$$
GetDistance` lit pour choisir entre DEUX metriques qui n'ont rien a voir :

  * `Simple`     -> `IBattleQuery.GetDistance(candidate, target)` : la distance HEX ;
  * `PathLength` -> `IBattleQuery.GetMinPathLength(pathfindingUnit, target, <tuiles>)` : le nombre
    de NOEUDS du CHEMIN, donc le PATHFINDING -- et, dans ce bras, un `pathfindingUnit` nul fait
    rendre au selecteur ses candidats INTACTS.

Ecrire `1` au site aurait donc choisi le pathfinding sans le dire. #889-r5."""
from enum import IntEnum


class DistanceType(IntEnum):
    Simple = 0
    PathLength = 1
