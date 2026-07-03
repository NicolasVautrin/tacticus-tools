"""`MinDistanceToClosestEnemyUtility` + composite `UnitMovement` — scoring de MOUVEMENT (RE ghidra
gqfc5mff6c, doc §1.5 / §13.11 / §13.12). UNE CLASSE feuille (nom NATIF) + le composite = INSTANCE.

`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility` (ctor @1810f0810 ; `UtilityType.
MinDistanceToClosestEnemy=16`) :
  - `GetMinDistanceToEnemy @1810f04a0` : itere les ennemis, garde le MIN de la distance de CHEMIN
    (pathfinding, PAS hex) de `pos` a chaque tuile ennemie. Fallback hex si pas de table de chemin.
  - `EvaluateMovementInSteps` (stub @1810f0430 ; body `<...>d__.MoveNext`) : `U = wMin * d`, avec
    `wMin = MinDistanceToClosestEnemy.PerTileDistance` (-100, du BC ; negatif => preferer se
    RAPPROCHER) et `d = GetMinDistanceToEnemy(pos)`.

Le decideur de move PUR est **UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(16)** (composition
LUE runtime via `UtilitiesDatabase.InitializeUtilities._composedUtilityLookup`, doc §13.8/13.11). C'est
un `ComposedUtility` INSTANCE (PAS une classe). Il s'evalue sur le CANAL MOUVEMENT (`ComposedUtility.
EvaluateMovement @1810cdf00` = Σ enfant.EvaluateMovement) : la feuille Tile score la tuile (canal tile)
et MinDist la distance (canal mouvement). Le generateur `MovementSuggestion` (engine.move.best_move_faithful)
pilote les deux canaux par tuile ; on ne somme donc PAS via `UNIT_MOVEMENT.evaluate` (signatures par canal).

NB hors composite : `MaxDistanceToEnemies(18)` n'est dans AUCUN composite ; `MaxDistanceToUnitTile(17)`
n'appartient qu'a `UnitMovementFromTemporary(5)` — non portes (doc §13.3).
"""
from __future__ import annotations

import hexgeo
from .base import BaseUtility, ComposedUtility
from .tile import TILE_UTILITY
from .utility_type import UtilityType


class MinDistanceToClosestEnemyUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility` (ctor @1810f0810 ;
    UtilityType.MinDistanceToClosestEnemy=16). Feuille du composite UnitMovement(6)."""
    UTILITY_TYPE = 16   # UtilityType.MinDistanceToClosestEnemy

    def get_min_distance_to_enemy(self, pos, enemy_positions, pathdist_by_pos=None) -> int:
        """`MinDistanceToClosestEnemyUtility.GetMinDistanceToEnemy @1810f04a0` : MIN sur les ennemis
        de la distance de CHEMIN de `pos` a la tuile ennemie (pattern nullable : `if d < cur: cur=d`).
        Distance de chemin si `pathdist_by_pos[pos]` est fournie (fidele) ; sinon fallback hex (approx)."""
        pd = pathdist_by_pos.get(pos) if pathdist_by_pos else None
        if pd is not None and pd >= 0:
            return int(pd)
        return min(hexgeo.distance(pos, ep) for ep in enemy_positions)

    def evaluate_movement(self, pos, enemy_positions, wt, pathdist_by_pos=None) -> float:
        """`MinDistanceToClosestEnemyUtility.<EvaluateMovementInSteps>d__.MoveNext` (stub @1810f0430) :
        `U = wMin * d`, `wMin = MinDistanceToClosestEnemy.PerTileDistance` (-100 du BC), `d =
        GetMinDistanceToEnemy(pos)`. wMin negatif => plus l'unite est PROCHE d'un ennemi, plus U est haut."""
        wmin = wt.sub("MinDistanceToClosestEnemy", "PerTileDistance")
        d = self.get_min_distance_to_enemy(pos, enemy_positions, pathdist_by_pos)
        return wmin * d


MIN_DIST_UTILITY = MinDistanceToClosestEnemyUtility()   # instance a UtilityType.MinDistanceToClosestEnemy=16
assert MIN_DIST_UTILITY.UTILITY_TYPE == UtilityType.MinDistanceToClosestEnemy

# Composite UnitMovement(6) = INSTANCE ComposedUtility (Tile=7 + MinDistanceToClosestEnemy=16) ; membership
# LUE runtime (doc §13.8/13.11). Evalue sur le CANAL MOUVEMENT par le generateur, PAS via .evaluate (les
# deux enfants ont des canaux differents) ; sert de RECORD de membership + de cle UtilitiesDatabase.
UNIT_MOVEMENT = ComposedUtility([TILE_UTILITY, MIN_DIST_UTILITY], utility_type=UtilityType.UnitMovement)
