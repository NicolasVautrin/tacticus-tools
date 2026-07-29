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
    Precisions RE (#17, 2026-07-29) : la valeur lue est `route+0x18` = `List._size`, donc un compte
    de **NOEUDS** (extremites incluses) = `aretes + 1` -- une flood-fill qui compte des ARETES rend
    UN DE MOINS ; `PathfinderType = 1` est un **litteral**, meme pour une unite VOLANTE ; et le
    `Nullable<int>` rendu est NUL quand aucune tuile de l'ennemi n'est joignable.
  - Gates de la feuille, avant tout calcul (`<EvaluateMovementInSteps>` in extenso) : `case.Unit ==
    null` -> 0 ; `IdunBattle.Entities.UnitExtensions$$IsNonAttacking(case.Unit)` -> 0 ;
    `case.ClosestEnemy == null` ou `IdunBattle.AI.Utilities.UnitCanBeDamagedUtility$$UnitCanBeDamaged(case.Unit, case.ClosestEnemy)`
    faux -> 0. Et si `d` n'a PAS de valeur, le natif rend la **constante statique** `statics+0x20` de
    `IdunBattle.AI.Utilities.BaseUtility` (#17-off, 2026-07-29) : son `.cctor` y recopie
    `FixMath.NET.Fix64.MinValue` (`Fix64` statics+0x18 = raw `0x8000000000000000`), donc
    `NO_PATH_UTILITY` ci-dessous -- **PAS** une distance hex.
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
    Structure confirmee (#17) : `bestDist` part de `int.MinValue`, le candidat exige `d > 0`, et la
    comparaison `d < bestDist` est STRICTE -> **premier-gagne** dans l'ordre de
    `IdunBattle.Entities.StateExtensions$$GetAllEnemyUnitsOfUnit`.
  - ⚠ **Les deux sources de `pathdist_by_pos` sont desormais equivalentes** (`#17-off`, 2026-07-29).
    Source LIVE (RPC `pathDistToEnemies`) : bit-exacte au natif -- 14/14 tuiles au pas s5 de la seed
    12345, tie -700/-700 sur (0,4)/(1,4) inclus. Source OFFLINE
    (`state_bridge._pathdist_to_enemies`) : rendait **UN DE MOINS sur chaque tuile** (BFS d'ARETES vs
    Count de NOEUDS) et prenait le min sur TOUS les ennemis ciblables au lieu du seul ClosestEnemy
    fige -- elle porte maintenant `FindClosestEnemy` + `GetMinDistanceToEnemy`. Garde commune :
    `tests/engine/test_min_distance_move_leaf_live.py` (les deux faces y sont confrontees tuile par
    tuile ; un offset UNIFORME ne deplace AUCUN argmax, donc aucune statistique d'agrement ne peut
    voir ce trou -- ne jamais valider ce terme par un taux d'accord).

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


# `IdunBattle.AI.Utilities.BaseUtility$$.cctor` ecrit a `statics+0x20` une COPIE de
# `FixMath.NET.Fix64.MinValue` (`Fix64` statics+0x18 = raw `0x8000000000000000`, soit -2^31 une fois
# le Q32.32 divise par 2^32). C'est la valeur que
# `MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` rend quand
# `GetMinDistanceToEnemy` n'a PAS de valeur -- une tuile d'ou le ClosestEnemy n'est joignable par
# AUCUN chemin est donc REDHIBITOIRE, jamais « penalisee proportionnellement ».
NO_PATH_UTILITY = -2147483648.0


class MinDistanceToClosestEnemyUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility` (IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$.ctor ;
    UtilityType.MinDistanceToClosestEnemy=16). Feuille du composite UnitMovement(6)."""
    UTILITY_TYPE = int(UtilityType.MinDistanceToClosestEnemy)  # 16

    def get_min_distance_to_enemy(self, pos, enemy_positions=None, pathdist_by_pos=None):
        """`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` : distance de CHEMIN de
        `pos` au **ClosestEnemy CIBLABLE** (min sur son footprint ; le ClosestEnemy est fige par
        `FindClosestEnemy`, cf. en-tete), en **NOEUDS** (`GetPath(...).Count`, extremites incluses).
        `pathdist_by_pos[pos]` porte cette distance (RPC `pathDistToEnemies` ou `state_bridge`, tous
        deux post-filtres natifs et tous deux en NOEUDS).

        Rend **None** = le `Nullable<int>` NUL du natif : aucun chemin de `pos` vers le ClosestEnemy
        (RPC `pathDist = -1`, ou tuile absente du dict offline). L'appelant doit alors rendre
        `NO_PATH_UTILITY`, PAS une distance de repli.

        `enemy_positions` ne sert QUE de repli DEGRADE quand `pathdist_by_pos` est vide/absent : c'est
        le cas « le port n'a aucune source de distance-chemin » (ex. `State.board is None`), qui
        n'existe PAS cote natif -- pas le cas `d == null`. Le repli hex est alors une approximation
        de PORT, explicitement hors mirror."""
        if pathdist_by_pos:
            pd = pathdist_by_pos.get(pos)
            return int(pd) if (pd is not None and pd >= 0) else None
        if not enemy_positions:
            return None
        return min(hexgeo.distance(pos, ep) for ep in enemy_positions)

    def evaluate_movement(self, pos, enemy_positions, wt, pathdist_by_pos=None) -> float:
        """`MinDistanceToClosestEnemyUtility.<EvaluateMovementInSteps>d__.MoveNext` (stub IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$EvaluateMovementInSteps) :
        `U = wMin * d` quand `d` a une valeur, `wMin = MinDistanceToClosestEnemy.PerTileDistance`
        (-100 du BC) ; wMin negatif => plus l'unite est PROCHE d'un ennemi, plus U est haut. Quand `d`
        n'a PAS de valeur, le natif rend la constante statique `BaseUtility` `statics+0x20` =
        `Fix64.MinValue` (cf. `NO_PATH_UTILITY`), pas un repli proportionnel."""
        d = self.get_min_distance_to_enemy(pos, enemy_positions, pathdist_by_pos)
        if d is None:
            return NO_PATH_UTILITY
        return wt.sub("MinDistanceToClosestEnemy", "PerTileDistance") * d


MIN_DIST_UTILITY = MinDistanceToClosestEnemyUtility()   # instance a UtilityType.MinDistanceToClosestEnemy=16
assert MIN_DIST_UTILITY.UTILITY_TYPE == UtilityType.MinDistanceToClosestEnemy

# Composite UnitMovement(6) = INSTANCE ComposedUtility (Tile=7 + MinDistanceToClosestEnemy=16) ; membership
# LUE runtime (doc §13.8/13.11). Evalue sur le CANAL MOUVEMENT par le generateur, PAS via .evaluate (les
# deux enfants ont des canaux differents) ; sert de RECORD de membership + de cle UtilitiesDatabase.
UNIT_MOVEMENT = ComposedUtility([TILE_UTILITY, MIN_DIST_UTILITY], utility_type=UtilityType.UnitMovement)
