"""`MinDistanceToClosestEnemyUtility` + composite `UnitMovement` — scoring de MOUVEMENT (RE ghidra
gqfc5mff6c, doc §1.5 / §13.11 / §13.12). UNE CLASSE feuille (nom NATIF) + le composite = INSTANCE.

`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility` (IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$.ctor ; `UtilityType.
MinDistanceToClosestEnemy=17`) :
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

Le decideur de move PUR est **UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(17)** (composition
LUE runtime via `UtilitiesDatabase.InitializeUtilities._composedUtilityLookup`, doc §13.8/13.11). C'est
un `ComposedUtility` INSTANCE (PAS une classe). Il s'evalue sur le CANAL MOUVEMENT (`ComposedUtility.
IdunBattle.AI.Utilities.ComposedUtility$$EvaluateMovement` = Σ enfant.EvaluateMovement) : la feuille Tile score la tuile (canal tile)
et MinDist la distance (canal mouvement). Le generateur `MovementSuggestion` (engine.move.best_move_faithful)
pilote les deux canaux par tuile ; on ne somme donc PAS via `UNIT_MOVEMENT.evaluate` (signatures par canal).

NB hors composite : `MaxDistanceToEnemies(19)` n'est dans AUCUN composite ; `MaxDistanceToUnitTile(18)`
n'appartient qu'a `UnitMovementFromTemporary(5)` — non portes (doc §13.3).
"""
from __future__ import annotations

from dataclasses import dataclass

import hexgeo
from ..entities.stats import StatType
from ..entities.traits.unit_trait import UnitTrait, has_trait
from .base import BaseUtility, ComposedUtility
from .tile import TILE_UTILITY, UTILITY_BY_TYPE
from .utility_type import UtilityType


# `IdunBattle.AI.Utilities.BaseUtility$$.cctor` ecrit a `statics+0x20` une COPIE de
# `FixMath.NET.Fix64.MinValue` (`Fix64` statics+0x18 = raw `0x8000000000000000`, soit -2^31 une fois
# le Q32.32 divise par 2^32). C'est la valeur que
# `MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` rend quand
# `GetMinDistanceToEnemy` n'a PAS de valeur -- une tuile d'ou le ClosestEnemy n'est joignable par
# AUCUN chemin est donc REDHIBITOIRE, jamais « penalisee proportionnellement ».
NO_PATH_UTILITY = -2147483648.0


@dataclass(frozen=True)
class UtilityMovementCase:
    """`IdunBattle.AI.Utilities.UtilityMovementCase` — le contexte que le generateur
    `<GenerateActions>IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext`
    passe a chaque feuille du composite UnitMovement(6). La feuille MinDist en lit DEUX champs :
    `case+0x10` = `Unit` (le mover) et `case+0x20` = `ClosestEnemy` (l'ennemi FIGE par
    `FindClosestEnemy`) — cf. `<EvaluateMovementInSteps>IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`.

    Le port ne materialise que ce que les gates LISENT (pas l'entite entiere) :
      - `unit` : identite du mover. `None` == `case.Unit == null` (gate 1).
      - `unit_traits` : substrat `HasTrait` du mover (`entity_trait_names`) -> gate 2 `IsNonAttacking`.
      - `unit_crit_chance` : `IdunBattle.Entities.UnitExtensions$$GetStat(unit, StatType.CriticalChance)`
        -> branche `crit != 0` de `UnitCanBeDamaged` (gate 4). `None` = stat NON RESOLUE par le port
        (contexte live sans `Scene`) -> gate 4 SUSPENDU, comme pour `closest_enemy_traits`.
        **Le defaut est `None`, pas `0`** : `0` est precisement la valeur qui FAIT MORDRE le gate,
        donc un defaut a `0` le ferait mordre sur une stat que personne n'a lue. Un appelant qui
        renseigne `closest_enemy_traits=(Impervious,)` sans fournir la stat obtient un gate
        SUSPENDU (permissif), jamais un gate arme sur une donnee absente.
      - `closest_enemy` : identite du ClosestEnemy. `None` == `case.ClosestEnemy == null` (gate 3).
      - `closest_enemy_traits` : substrat `HasTrait` du ClosestEnemy -> branche `Impervious` du gate 4.
        **`None` = substrat NON RESOLU par le port** (identite du ClosestEnemy ambigue cote LIVE, cf.
        `engine.ai.context`) : le gate 4 est alors SUSPENDU (permissif), jamais devine.

    `evaluate_movement(case=None)` = aucun case fourni -> AUCUN gate (comportement d'avant #236) :
    un appelant qui n'a pas construit le case ne doit pas se voir imposer un gate invente."""
    unit: object = None
    unit_traits: tuple = ()
    unit_crit_chance: "int | None" = None
    closest_enemy: object = None
    closest_enemy_traits: "tuple | None" = ()


def is_non_attacking(trait_names) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsNonAttacking(unit)` : `GetBaseUnitComponent(unit)` puis
    `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait(comp, 0x409)` — le trait `0x409` = 1033
    = `UnitTrait.NonAttacking`. Composant absent -> false (le natif retombe sur le `return` nu).
    Cote port le substrat `HasTrait` est `entity_trait_names` (kit + traits ACCORDES en bataille)."""
    return has_trait(trait_names, UnitTrait.NonAttacking)


def unit_can_be_damaged(unit_crit_chance, target_trait_names) -> bool:
    """`IdunBattle.AI.Utilities.UnitCanBeDamagedUtility$$UnitCanBeDamaged(unit, target)`, in extenso :

        if (!UnitExtensions.HasTrait(target, 0x1c)) return true;      // 0x1c = 28 = Impervious
        return UnitExtensions.GetStat(unit, 9) != 0;                  // 9 = StatType.CriticalChance

    Autrement dit : une cible `Impervious` n'est « endommageable » que par une unite dont la
    CriticalChance est NON NULLE (le trait ne cede qu'aux coups critiques). L'appel est
    ASYMETRIQUE — `unit` (le mover) fournit la stat, `target` (le ClosestEnemy) le trait.

    `target_trait_names is None` (identite du ClosestEnemy non etablie) ou `unit_crit_chance is None`
    (stat non resolue) -> `True` (permissif) : le port ne fabrique pas un gate sur une donnee qu'il
    n'a pas lue. Ces deux `None` sont les SEULS trous du mirror, et ils sont nommes dans
    `UtilityMovementCase`."""
    if target_trait_names is None or unit_crit_chance is None:
        return True
    if not has_trait(target_trait_names, UnitTrait.Impervious):
        return True
    return int(unit_crit_chance or 0) != 0


assert int(UnitTrait.NonAttacking) == 0x409 and int(UnitTrait.Impervious) == 0x1c
assert int(StatType.CRIT_CHANCE) == 9      # `GetStat(unit, 9)` de `UnitCanBeDamaged`


class MinDistanceToClosestEnemyUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility` (IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$.ctor ;
    UtilityType.MinDistanceToClosestEnemy=17). Feuille du composite UnitMovement(6)."""
    UTILITY_TYPE = int(UtilityType.MinDistanceToClosestEnemy)  # 17

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

    def evaluate(self, tile, meta, ctx, wt) -> float:
        """CANAL TUILE -- la signature qu'emploie `sort_tiles_by_utility` (le foyer du selecteur
        `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector`), et qui est celle de tous les
        enfants du composite `Tile(7)`.

        Elle rend **0.0 INCONDITIONNELLEMENT**, et ce n'est pas une degradation : c'est le GATE 3 du
        natif, lu VERBATIM (#448-r1). La lambda `IdunBattle.Entities.Selectors.
        SortTilesByUtilitySelector.u003Cu003Ec__DisplayClass8_0$$u003CSelectu003Eb__1` construit

            new UtilityMovementCase(dc.unit, _tile, closestEnemy: NULL, abilityType: NULL,
                                    dc.parent, target: NULL)

        (le 3e argument est litteralement `0` dans le decompile, et le ctor nomme range ce parametre
        en `case+0x20`), et `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility.
        u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` fait, avant tout calcul :

            if (case.<+0x10> == null)                                   yield Fix64.FromInt(0);
            if (UnitExtensions.IsNonAttacking(case.<+0x10>))            yield Fix64.FromInt(0);
            if (case.<+0x20> == null || !UnitCanBeDamaged(...))         yield Fix64.FromInt(0);

        `case.<+0x20>` EST le `ClosestEnemy`. Par CE chemin il est donc toujours nul et la feuille est
        MUETTE -- pas redhibitoire (`NO_PATH_UTILITY`), juste zero.

        ⇒ **Le composite `UnitMovement(6)` se reduit EXACTEMENT a `Tile(7)` quand il est evalue par
        `SortTilesByUtility`.** Le terme de distance n'existe que sur le canal MOUVEMENT, ou le
        generateur `MovementActionGenerator` fournit un vrai `ClosestEnemy` (methode
        `evaluate_movement` ci-dessous, signature differente et appelants differents).

        Consommateur : `...StormboyzStrike_FallbackAbility$$CreateBehaviour`, seul call-site porte
        qui demande `UtilityDefinition(6)`."""
        return 0.0

    def evaluate_movement(self, pos, enemy_positions, wt, pathdist_by_pos=None,
                          case: "UtilityMovementCase | None" = None) -> float:
        """`MinDistanceToClosestEnemyUtility.<EvaluateMovementInSteps>d__.MoveNext` (stub IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$EvaluateMovementInSteps) :
        `U = wMin * d` quand `d` a une valeur, `wMin = MinDistanceToClosestEnemy.PerTileDistance`
        (-100 du BC) ; wMin negatif => plus l'unite est PROCHE d'un ennemi, plus U est haut. Quand `d`
        n'a PAS de valeur, le natif rend la constante statique `BaseUtility` `statics+0x20` =
        `Fix64.MinValue` (cf. `NO_PATH_UTILITY`), pas un repli proportionnel.

        QUATRE GATES D'ENTREE precedent tout calcul (#236) — chacun rend `Fix64.FromInt(0)`, soit
        **0.0**, PAS `NO_PATH_UTILITY` : la tuile n'est pas redhibitoire, la feuille est MUETTE.
        Ils sont dans l'ordre EXACT du natif (le premier qui mord court-circuite) :

          1. `case.Unit == null`                                        (`case+0x10`)
          2. `IdunBattle.Entities.UnitExtensions$$IsNonAttacking(case.Unit)`
          3. `case.ClosestEnemy == null`                                (`case+0x20`)
          4. `!IdunBattle.AI.Utilities.UnitCanBeDamagedUtility$$UnitCanBeDamaged(case.Unit, case.ClosestEnemy)`

        Sans eux le port attribue un terme de distance la ou le natif rend zero -> il PREFERE des
        tuiles que le natif n'evalue pas. La degradation est PERMISSIVE (ni erreur ni crash) et
        STRUCTURELLEMENT INVISIBLE en agrement : `MovementActionGenerator.generate` est un argmax pur,
        donc un ecart UNIFORME sur toutes les tuiles ne deplace AUCUN choix. Ce terme ne se valide
        que TUILE PAR TUILE (cf. `tests/engine/test_min_distance_move_leaf_live.py`)."""
        if case is not None:
            if case.unit is None:                                   # gate 1
                return 0.0
            if is_non_attacking(case.unit_traits):                  # gate 2
                return 0.0
            if case.closest_enemy is None:                          # gate 3
                return 0.0
            if not unit_can_be_damaged(case.unit_crit_chance,       # gate 4
                                       case.closest_enemy_traits):
                return 0.0
        d = self.get_min_distance_to_enemy(pos, enemy_positions, pathdist_by_pos)
        if d is None:
            return NO_PATH_UTILITY
        return wt.sub("MinDistanceToClosestEnemy", "PerTileDistance") * d


MIN_DIST_UTILITY = MinDistanceToClosestEnemyUtility()   # instance a UtilityType.MinDistanceToClosestEnemy=17
assert MIN_DIST_UTILITY.UTILITY_TYPE == UtilityType.MinDistanceToClosestEnemy

# Composite UnitMovement(6) = INSTANCE ComposedUtility (Tile=7 + MinDistanceToClosestEnemy=17) ; membership
# LUE runtime (doc §13.8/13.11). Evalue sur le CANAL MOUVEMENT par le generateur, PAS via .evaluate (les
# deux enfants ont des canaux differents) ; sert de RECORD de membership + de cle UtilitiesDatabase.
UNIT_MOVEMENT = ComposedUtility([TILE_UTILITY, MIN_DIST_UTILITY], utility_type=UtilityType.UnitMovement)

# Inscription au mirror de `IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` (#448-r1).
# Elle vit ICI et non dans `tile.py` parce que `UNIT_MOVEMENT` a besoin de `TILE_UTILITY` : c'est
# `move` qui depend de `tile`, jamais l'inverse. `engine/utilities/__init__.py` importe les deux dans
# cet ordre, donc la cle est posee des que le package est charge -- et le chemin qui la consomme
# (`sort_tiles_by_utility`) passe forcement par ce package.
# Demandeur : `...StormboyzStrike_FallbackAbility$$CreateBehaviour` -> `UtilityDefinition(6)`.
# Sur ce chemin le composite VAUT `Tile(7)` : la feuille MinDist y est court-circuitee par son gate
# `ClosestEnemy == null` (cf. `MinDistanceToClosestEnemyUtility.evaluate`).
UTILITY_BY_TYPE[int(UtilityType.UnitMovement)] = UNIT_MOVEMENT
