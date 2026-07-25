"""`MinDistanceToClosestEnemyUtility` + composite `UnitMovement` — scoring de MOUVEMENT (RE ghidra
gqfc5mff6c, doc §1.5 / §13.11 / §13.12). UNE CLASSE feuille (nom NATIF) + le composite = INSTANCE.

`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility` (IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$.ctor ; `UtilityType.
MinDistanceToClosestEnemy=16`) :
  - `<EvaluateMovementInSteps>IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` (stub IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$EvaluateMovementInSteps) : `U = wMin * d`, avec
    `wMin = MinDistanceToClosestEnemy.PerTileDistance` (-100, du BC ; negatif => preferer se
    RAPPROCHER) et `d = GetMinDistanceToEnemy(unit, tuile_candidate, ClosestEnemy)`. Le contexte du
    leaf = `UtilityMovementCase(unit, tuile, ClosestEnemy)`, construit par le generateur
    `<GenerateActions>IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext` avec `ClosestEnemy = FindClosestEnemy(unit, posCourante)`.
  - `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` : MIN sur les tuiles de FOOTPRINT du **ClosestEnemy** (UN seul
    ennemi fige) de la distance de CHEMIN (`IPathfinders.GetPath(type=1, unit, tuile, tuileEnnemie,
    null).Count`, PAS hex ; Count INCLUT la tuile de depart) de `tuile` a chaque tuile ennemie.
  - **ClosestEnemy = `MovementActionGenerator.<FindClosestEnemy>IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext`** : argmin
    (depuis la position COURANTE) SUR LES ENNEMIS CIBLABLES uniquement -- filtres COMPLETS (#26, ordre
    natif) : `!CurrentOwnerIsEnvironment` (`IdunBattle.Entities.EntityExtensions$$CurrentOwnerIsEnvironment` = Owner.Type==2, joueur Environment/neutre),
    **`IsTargetable`** (`IdunBattle.Entities.UnitExtensions$$IsTargetable` = `!HasFlag(0x11)`), `!IsIrrelevantObject` (`IdunBattle.Entities.UnitExtensions$$IsIrrelevantObject` = trait 27,
    ou trait 13 avec stat0<=0), `!IsDead`, puis restriction `GetOnlyTargets` (`IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` = List<int>
    d'ids de cibles FORCEES, taunt ; liste vide si pas de composant ou OwnerComponent.IsOverridden).
    Le RPC `pathDistToEnemies` (rpc-board.ts) invoque ces predicats NATIFS et renvoie aussi `enemies`
    (les cibles retenues) -> `ctx.tgt_epos`, seed du fallback HEX quand pathDist=-1 ; le bridge offline
    filtre son seed via `state_bridge._is_untargetable` (deep-strike ; Environment/irrelevant/taunt sans
    porteur offline connu a ce jour). CRITIQUE : une unite en Deep-Strike (TeleportStrike, flag 0x11
    non-atterri) est NON-CIBLABLE -> exclue du ClosestEnemy. 12345 s5 (case-52 §#57l) : sans le filtre,
    un Dante deep-strike (plus proche par chemin) ecrasait le ClosestEnemy -> (1,4) valait d=6 vers
    Dante au lieu de d=7 vers l'ennemi ciblable -> move (1,4) au lieu de (0,4).

Le decideur de move PUR est **UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(16)** (composition
LUE runtime via `UtilitiesDatabase.InitializeUtilities._composedUtilityLookup`, doc §13.8/13.11). C'est
un `ComposedUtility` INSTANCE (PAS une classe). Il s'evalue sur le CANAL MOUVEMENT (`ComposedUtility.
IdunBattle.AI.Utilities.ComposedUtility$$EvaluateMovement` = Σ enfant.EvaluateMovement) : la feuille Tile score la tuile (canal tile)
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
    """`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility` (IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$.ctor ;
    UtilityType.MinDistanceToClosestEnemy=16). Feuille du composite UnitMovement(6)."""
    UTILITY_TYPE = int(UtilityType.MinDistanceToClosestEnemy)  # 16

    def get_min_distance_to_enemy(self, pos, enemy_positions, pathdist_by_pos=None) -> int:
        """`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` : distance de CHEMIN de
        `pos` au **ClosestEnemy CIBLABLE** (min sur son footprint ; le ClosestEnemy est fige par
        `FindClosestEnemy`, cf. en-tete). `pathdist_by_pos[pos]` porte cette distance-chemin filtree
        (RPC `pathDistToEnemies` ou `state_bridge`, tous deux post-filtres natifs) ; sinon fallback
        hex (approx : min sur `enemy_positions` = `ctx.tgt_epos`, les ennemis CIBLABLES post-filtres
        #26 -- hex reste une approximation de la distance de CHEMIN, mais le SET est fidele)."""
        pd = pathdist_by_pos.get(pos) if pathdist_by_pos else None
        if pd is not None and pd >= 0:
            return int(pd)
        return min(hexgeo.distance(pos, ep) for ep in enemy_positions)

    def evaluate_movement(self, pos, enemy_positions, wt, pathdist_by_pos=None) -> float:
        """`MinDistanceToClosestEnemyUtility.<EvaluateMovementInSteps>d__.MoveNext` (stub IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$EvaluateMovementInSteps) :
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
