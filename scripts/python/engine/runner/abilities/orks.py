"""Abilities actives ORKS (namespace natif `IdunBattleLogic.Entities.Abilities.Active.Loki.*`).

Waaagh (1058, `orksWarboss` « Snotflogga ») — 2e consommateur porte du debloqueur `PerformAIAction`
(`abilities/behaviours/ai_control.py` + `operations/summon_ai.py::ComputerActionOperation`), avec les
MEMES booleans que SupremeCommander (`asGroup=1, resetTurnFlags=1`) mais un selecteur BOARD-WIDE
(`UnitsWithVisualId`, aucun rayon) au lieu du `UnitsWithIds(SurroundingFriends(range))` de Creed.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC
import hexgeo

from .base import ActiveAbility, convert_rounds_to_turns
from .targeting import (RANGE_FROM_CONFIG, RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
                        TargetingOptions)
from .targeting_rule import TargetingRule as TR
from ..components import PositionComponent, StatsComponent
from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import If, SetCache, op_add, op_and
from ...entities.effect_type import EffectType
from ...entities.formulas import Count, Get, VisualUnitIdFromUnitId
from ...entities.selectors import (ActiveTarget, AdjacentFriends, AdjacentTiles, AdjacentUnits,
                                   AllUnits, Cache, CanAddUnit, Caster, CasterTile, Damageable,
                                   EntitiesWithoutEffects, FixedTileIds, FixedTiles, Friends,
                                   MovableTilesInRange, Owner, SurroundingEnemies, SurroundingTiles,
                                   Target, TargetTile, TileIntersect, Union, Unique, UnitSet,
                                   UnitsFromFaction, UnitsWithVisualId, Unobscured,
                                   non_steppable_or_object_units,
                                   tiles_unit_can_move_to_charge_target)
from ...entities.stats import StatType
from ...entities.triggers import (AmountIsEqualOrGreater, CacheTrigger, IsAdjacent, Not,
                                  OwnerIsAlive, TriggerOr)
from ...utilities.decider import UtilityBucket, UtilityDefinition, WeightedUtility
from ...utilities.tile import first_tile_by_utility
from ...utilities.utility_type import UtilityType
from .behaviours import (AddEffect, AttackWithAttackDamage, KillDeadUnits, MoveUnit, PerformAIAction,
                         Spawn, UseActiveAbility, entities_from_state)

if TYPE_CHECKING:
    from ..state import State

# Index des constantes lues par `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` et ses helpers
# (`AbilityConfiguration.Get*Constant(config, <index>)`) -> cle gameconfig correspondante.
CONST_UNIT_ID = 0x00            # GetStringConstant(0)     -> "unitId"        = orksOrkBoys
CONST_EXTRA_MOVEMENT = 0x0e     # GetNumberConstant(0xe)   -> "extraMovement" = 1
CONST_NR_OF_SUMMONS = 0x10      # GetNumberConstant(0x10)  -> "nrOfSummons"   = 2

WAAAGH_FACTION = "Orks"         # `UnitsFromFaction(..., 5, 3)` — UnitFaction.Orks = 5 (il2cpp_enums)


# ------------------------------------------------------------------------------------------------ #
# Les 5 arbres top-level de `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour`, dans l'ORDRE D'EXECUTION
# natif (5 appels `AActiveAbility.Execute` successifs, chacun enveloppe dans un `Group(<b>, caster@0x160,
# <groupId>)` = ordonnancement de VUE, no-op observable ici) :
#     Group(spawnB,  0x22) · Group(buffB, 0x25) · Group(moveB, 0x23) · Group(atkB, 0x20) · Group(aiB, 0x28)
# ------------------------------------------------------------------------------------------------ #

def waaagh_spawn_tree(count: int) -> Spawn:
    """1er noeud natif IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour (corps INLINE, identique a `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetSummonBehaviour`) :
        `Spawn( caster@0x160,
                PickRandomly(CanAddUnit(AdjacentTiles(casterTile@0x168)), GetNumberConstant(0x10)),
                GetStringConstant(0)=orksOrkBoys,
                SpawnUnitOptions.WithStatsFromConfig(config, level) )`
    AUCUN sous-behaviour on-appearance (`opts+0x18` jamais assigne) -- contraste avec SendInTheNextWave /
    Incursion / Poxwalkers : ici les Ork Boyz agissent via l'etage `PerformAIAction` final. Le
    `PickRandomly` est FOLDE dans la feuille `Spawn` (`pick_n`), qui seule voit `ectx.state.rng`.

    Le centre natif est `casterTile@0x168` (domaine TILE) ; le noeud porte `AdjacentTiles` prend un
    selecteur UNIT-domain et derive la tuile de la position de l'unite -> `Caster()` designe la MEME
    tuile (meme reduction que `supreme_commander_spawn_tree`, `AdjacentTiles(caster@0x160)`)."""
    return Spawn(CanAddUnit(AdjacentTiles(Caster())), "Waaagh", pick_n=count)


def waaagh_buffed_units_selector():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffedUnitsSelector` (== le selecteur INLINE de `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour`) :
        `Unique( caster@0x160
                 + AdjacentFriends(caster@0x160, 1, 3)
                 + UnitsFromFaction(Friends(caster@0x160, @0x80, 3), 5=Orks, 3) )`
    (`TargetsSelector.op_Addition` = union, puis `Unique` = dedup par entite). `@0x80` = le slot PARTAGE
    « toutes les unites (vivantes) » pose par `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` -> porte `AllUnits()`.
    Portee : le caster, ses allies ADJACENTS (quelle que soit leur faction) et TOUS ses allies de faction
    **Orks** (board-wide, aucun rayon).

    `AdjacentFriends` porte prend un CENTRE-POSITION (convention des selecteurs d'anneau du port) ->
    `CasterTile()` designe la MEME ancre que le `caster@0x160` natif (self exclu par `_within`, puis
    reinjecte par l'union `Caster()` — exactement l'`op_Addition(caster, adjacentFriends)` natif)."""
    return Unique(Union(Union(Caster(), AdjacentFriends(CasterTile(), Const(1))),
                        UnitsFromFaction(Friends(AllUnits()), WAAAGH_FACTION)))


def waaagh_buff_tree():
    """2e noeud natif IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour = `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` :
        `op_BitwiseAnd( op_BitwiseAnd(
              AddStaticStatModifierEffect(sel, 1099=Waaagh_ExtraMovement, stat=MOVEMENT(1),
                                          Direct(GetNumberConstant(0xe)=extraMovement), duree@dsl+0xc0=1),
              AddEffect(0x44c=1100 Waaagh_ExtraDamage, AbilityStateReference, caster@0x160, sel, duree@0xc0) ),
              AddEffect(0x44d=1101 Waaagh_ExtraHits,   AbilityStateReference, caster@0x160, sel, duree@0xc0) )`

    Les TROIS effets partagent le MEME selecteur (`waaagh_buffed_units_selector`) et la MEME duree
    (`dsl+0xc0` = `Direct(1)` pose par `DSLFactory..IdunBattleLogic.Entities.DSLFactory$$.ctor` -> 1 round).

    `AddStaticStatModifierEffect` (IdunBattleLogic.Entities.DSLFactory$$AddStaticStatModifierEffect) n'a PAS de feuille dediee dans le port : le mapping etabli
    du projet (valide live sur `BlackRage_ExtraMove` 1342) est `AddEffect(<type>)` + une classe d'effet
    portant `applied_stat_mods` (canal EAGER `AddEffectOperation._apply_stat_mods`) -> ici
    `WaaaghExtraMovementEffect` (+MOVEMENT = extraMovement).

    #95 : les contributions de 1100 (+extraDmg[level], canal
    `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`) et de 1101
    (+extraHit, canal `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`)
    sont DESORMAIS BRANCHEES (classes d'effet `WaaaghExtraDamageEffect`/`WaaaghExtraHitsEffect`)."""
    # #98 : la duree des TROIS effets est `dsl+0xc0` = un noeud `Direct(1)` (alloue par
    # `DSLFactory..IdunBattleLogic.Entities.DSLFactory$$.ctor`), PAS un `TurnsFromRounds(1)` -> elle arrive telle quelle dans le
    # `param_6` d'`IdunBattle.Operations.AddEffectOperation$$Execute`, qui ne la convertit PAS : 1 TOUR, pas 1 round.
    # -> `duration_turns=1` (comportement INCHANGE ; c'est exactement le call-site qu'une conversion
    # aveugle aurait double).
    # #95 `scale_from_source=True` = le PORT de l'`AbilityStateReference` que les TROIS noeuds natifs
    # passent en 2e argument : l'effet materialise resout son `ConfigVar` contre l'AbilityState de sa
    # SOURCE (`ConfigAmount.GetAbilityState` -> selecteur AbilityStateFromEffect -> Owner du reference),
    # pas contre celle du buffe. Requis par `ConfigVar(8=extraDmg)` de 1100, qui n'en consomme que le
    # NIVEAU (multiplier de rarete resolu = 100, MESURE) ; no-op sur 1099/1101 (magnitudes CONSTANTES).
    sel = waaagh_buffed_units_selector()
    return op_and(op_and(AddEffect(int(EffectType.Waaagh_ExtraMovement), "Waaagh_ExtraMovement", sel,
                                   duration_turns=1, scale_from_source=True),
                         AddEffect(int(EffectType.Waaagh_ExtraDamage), "Waaagh_ExtraDamage", sel,
                                   duration_turns=1, scale_from_source=True)),
                  AddEffect(int(EffectType.Waaagh_ExtraHits), "Waaagh_ExtraHits", sel,
                            duration_turns=1, scale_from_source=True))


def waaagh_move_range(state: "State", caster_id: int, extra_movement: int) -> int:
    """`IdunBattleLogic.Entities.DSLFactory$$UnitMovementRangeWithBonus(caster@0x160, 1099, Direct(extraMovement))`
    (lu par `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetPossibleMovementTiles`) = MIRROR 1:1 :
        `If( HasEffect(caster, 1099), StatAmount(caster, MOVEMENT(1), Current), Sum(<idem>, bonus) )`
    -> ANTI-DOUBLE-COMPTE : si l'effet 1099 est DEJA pose (c'est le cas ici, le Group buff @0x25 s'execute
    AVANT le Group move @0x23), la portee = la stat MOVEMENT *deja bonifiee* par l'effet ; sinon
    MOVEMENT + bonus. Le port de `WaaaghExtraMovementEffect.applied_stat_mods` rend les deux branches
    equivalentes -- et sa fidelite est donc DIRECTEMENT observable sur la portee de charge."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    stats = getattr(sc.ctx, "stats", None) if sc is not None else None
    mv = int(stats.get_stat(int(StatType.MOVEMENT), 0)) if stats is not None else 0
    has_eff = (state.effects is not None
               and state.effects.has_effect(caster_id, effect_type=int(EffectType.Waaagh_ExtraMovement)))
    return mv if has_eff else mv + int(extra_movement)


def waaagh_possible_movement_tiles_selector(move_range: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetPossibleMovementTiles` —
    MIRROR du decompile, ARBRE DSL (aucune logique recablee a la main) :

        TilesUnitCanMoveToChargeTarget( caster@0x160, casterTile@0x168, target,
                                        UnitMovementRangeWithBonus(caster, 1099,
                                                                   Direct(GetNumberConstant(0xe))),
                                        ignoreFlags = 0 )
        = CanAddUnit(AdjacentTiles(target)) op_BitwiseAnd MovableTilesInRange(caster, casterTile,
                                                                              range, ignoreFlags=0,
                                                                              ignoreUnitsOnTiles=0)

    `ignoreFlags=0` (CONTRASTE avec VigilanceEternal, qui passe 1). ⚠ #381-r1 : ce 5e argument du
    helper natif N'EST PAS un `canReachOnly` — il ne touche que la garde d'entree de
    `MovementQuery$$FindAnyOrAllMoveableTiles` et ne change PAS l'ensemble rendu. L'ensemble
    « movable » est TOUJOURS le `stop_set` (tuiles LIBRES), parce que
    `MovementQuery$$AnyOrFillMoveableTiles` termine par
    `RemoveAll(t => !IsMovableTile(unit, t, ignoreUnitsOnTiles=0))`.

    `move_range` arrive DEJA CALCULE (`waaagh_move_range`, collapse documente du noeud
    `UnitMovementRangeWithBonus` — il lit l'effet 1099 deja pose, cf. sa docstring) et est presente
    au noeud par un `Direct` : c'est LA valeur du 4e argument natif.

    DEUX consommateurs, exactement comme le natif :
      * l'etage MOVE de `WaaaghAbility$$ExecuteBehaviour` (`waaagh_charge_tile`, qui trie et prend
        la 1re tuile) ;
      * le gate de ciblage `WaaaghAbility$$GetDynamicInvalidTargetReason` (qui n'en prend que le
        `Count`). Les deux voient donc TOUJOURS le meme ensemble."""
    return tiles_unit_can_move_to_charge_target(Caster(), CasterTile(), Target(),
                                                Const(int(move_range)), ignore_flags=False)


def waaagh_charge_tile(state: "State", caster_id: int, target_id: int, move_range: int):
    """Selecteur de destination de l'etage MOVE de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` :

        `First( SortTilesByUtility( WaaaghAbility.GetPossibleMovementTiles(target@0x178),
                                    caster@0x160, 0x20 ), 1 )`

    L'operande `GetPossibleMovementTiles` est l'ARBRE DSL `waaagh_possible_movement_tiles_selector`
    (mirror 1:1). Le litteral d'utilite est **0x20 = 32 = `UtilityType.MovementSuggestion`** (relu au
    decompile : `SortTilesByUtility(factory, pool, caster@0x160, 0x20)` -- la surcharge int de
    `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtility`, qui construit
    `UtilityDefinition..ctor(0x20)` et delegue a la surcharge objet avec `ownerSel` NUL), PAS le
    `7 = Tile` des ports freres. `UtilitiesDatabase$$InitializeUtilities` compose la cle `0x20` en
    `[Tile(7), TileDistance(34)]` -- les DEUX enfants sont portes (#201, `engine/utilities/tile.py`).

    #206 -- le COLLAPSE « la tuile la plus PROCHE du caster (tie-break tile id) » est SUPPRIME : il ne
    reproduisait le natif que dans le regime ou `Tile(7)` est PLAT (alors `TileDistance = -d/10`, seul
    terme non nul, ordonne bien par distance croissante) et il INVERSAIT le natif des que `Tile(7)`
    departageait -- `Tile(7)` est a valeurs entieres (Elevation 10/niveau, TileEffects +-9/-25) et
    domine toujours `|TileDistance| <= 0.2` sur un pool de charge. Le tie-break `, t` (id de tuile)
    etait en prime INVENTE : le natif laisse le tri STABLE rendre l'ordre du selecteur source.
    Meme correction, meme call-site que `_vigilance_move_dest_tile` (cf.
    `docs/rl/case-201-movement-suggestion-tiledistance.md`). Renvoie une (col,row) ou None."""
    board = state.board
    ce = state.get_entity(caster_id)
    cpc = ce.get_component(PositionComponent) if ce is not None else None
    if board is None or cpc is None or state.get_entity(target_id) is None:
        return None
    cands = waaagh_possible_movement_tiles_selector(move_range).evaluate(
        entities_from_state(state, caster_id, target_id))
    if not cands:
        return None
    # `caster@0x160` = `dc.units` du selecteur -> `case.units`, l'unite dont `TileDistanceUtility`
    # mesure l'eloignement (et que lisent les feuilles gatees sur l'unite, case-165b).
    best = first_tile_by_utility(state, cands, unit_id=caster_id,
                                 utility_type=int(UtilityType.MovementSuggestion))
    return board.coord(best) if best is not None else None


def waaagh_move_tree(dest):
    """3e noeud natif IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour : `MoveUnit(caster@0x160, <destination>, <options NULLES>)` — le
    decompile met a zero les 5 selecteurs d'options (`local_1a8..uStack_178 = 0`, seul `local_198` =
    `factory+0xf8` est lu) -> aucun flag after-move (meme configuration que HeroicFusillade, cf.
    `behaviours/movement.py`). Destination = `waaagh_charge_tile` (collapse S)."""
    return MoveUnit(Caster(), FixedTiles([dest] if dest is not None else []))


def waaagh_attack_tree():
    """4e noeud natif IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour = `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetAttackBehaviour` :
        `op_BitwiseAnd(
            If( IsAdjacent(caster@0x160, target@0x178, 3),
                UseActiveAbility(caster@0x160, target@0x178,
                                 UnitNormalAttackType(caster@0x160), <options>) ),
            KillDeadUnits( Killer(activeTarget@0x180), AllUnits() ) )`

    - GATE `IsAdjacent(caster, target, 3)` : le `3` (champ +0x18) ne va PAS au predicat par-paire (slot
      iface 0x5f = `AreNeighbours`) -- MEME lecture que VigilanceEternal IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$ExecuteBehaviour (cf. genestealer.py)
      -> seuil dist == 1 STRICT. L'attaque n'a donc lieu que si la CHARGE a bien amene le Warboss au
      contact (ou s'il y etait deja).
    - `UnitNormalAttackType(caster)` -> attaque NORMALE (la feuille portee `UseActiveAbility` specialise
      deja le dispatch a l'attaque normale, `AttackDamageOperation.execute`).
    - `KillDeadUnits(Killer(@0x180), AllUnits())` : finalisation des cadavres. Le port MIRROR la structure
      SANS re-muter (la mort est finalisee INLINE par l'attaque, cf. `behaviours/lifecycle.py`) et
      n'exploite PAS `subject_sel` -> le noeud `Killer(...)` (non porte) est represente par son operande
      `ActiveTarget@0x180`."""
    return op_and(If(IsAdjacent(Caster(), Target()), UseActiveAbility(Caster(), Target())),
                  KillDeadUnits(ActiveTarget(), AllUnits()))


# ------------------------------------------------------------------------------------------------ #
# RammingSpeed (1059) — l'etage de CHARGE. `#353-r1`, volet (a).
#
# CE N'EST PAS le meme assemblage que Waaagh, et la difference est OBSERVABLE :
# `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo` n'appelle PAS
# `IdunBattleLogic.Entities.DSLSelectors$$TilesUnitCanMoveToChargeTarget` — il assemble les memes deux
# noeuds A LA MAIN, dans l'ORDRE INVERSE, et trie avec une definition d'utilite a DEUX termes.
# ------------------------------------------------------------------------------------------------ #

RAMMING_SPEED_CONST_RANGE = 0x16   # GetNumberConstant(0x16) -> "range" = 5 (AbilityConstantType.range)

# `UtilityDefinition( UtilityBucket([ WeightedUtility(7 = Tile, null),
#                                     WeightedUtility(0x36 = 54 RammingSpeed_MostAdjacentEnemies,
#                                                     null) ], null) )`
# — BATI A LA MAIN par `GetTileToMoveTo` (allocation d'un `WeightedUtility[2]`, deux
# `WeightedUtility$$.ctor` avec un `Nullable<Fix64>` VIDE, un `UtilityBucket$$.ctor`, un
# `TExtensions$$ToArray` puis `UtilityDefinition$$.ctor(bucket)`), et non par la surcharge INT de
# `SortTilesByUtility` que prennent tous les autres call-sites portes. Poids effectifs = 1 et 1
# (le `?? Fix64.FromInt(1)` du ctor), difference minimale = 0 : la composition est la SOMME NUE des
# deux utilites (lecture du decompile, cf. `engine/utilities/decider.py`).
RAMMING_SPEED_TILE_UTILITY = UtilityDefinition(UtilityBucket([
    WeightedUtility(utility_type=int(UtilityType.Tile)),
    WeightedUtility(utility_type=int(UtilityType.RammingSpeed_MostAdjacentEnemies)),
]))


def ramming_speed_charge_tiles_selector(move_range: int) -> TileIntersect:
    """Operande de tri de `RammingSpeedAbility$$GetTileToMoveTo` — ARBRE DSL, mirror 1:1 :

        MovableTilesInRange( caster@0x48, casterTile@0x50, Direct(GetNumberConstant(0x16 = range)),
                             ignoreFlags = 0, ignoreUnitsOnTiles = 0 )
        op_BitwiseAnd
        CanAddUnit( AdjacentTiles( target@0x60 ) )

    ⚠ **L'ORDRE DES OPERANDES EST INVERSE** par rapport a
    `DSLSelectors$$TilesUnitCanMoveToChargeTarget` (= `CanAddUnit(AdjacentTiles(target))` A GAUCHE,
    ce que porte `tiles_unit_can_move_to_charge_target` et qu'utilise Waaagh). Ici c'est
    `MovableTilesInRange` qui est a GAUCHE.

    Ce n'est PAS cosmetique : `IdunBattle.DSL.TargetsSelector$$op_BitwiseAnd(left, right)` construit
    un `CombinedSelector{ +0x18 = left, +0x20 = right }` dont la sortie suit l'operande GAUCHE, et
    `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` termine par un `OrderBy` LINQ
    **STABLE** — a utilite EGALE, c'est le premier de l'ordre SOURCE que `First(..., 1)` emet. Donc
    reutiliser le helper aurait change la tuile rendue sur toute egalite d'utilite.

    RESIDU NOMME, herite du port de `MovableTilesInRange` : ce noeud rend `sorted(...)` (id de tuile
    croissant) la ou le natif rend l'ordre de visite du BFS de
    `IdunBattle.Entities.Pathfinding.BasePathfinder$$GetMovablePositions`. Tant que
    `MovableTilesInRange` etait a DROITE de toutes les intersections portees, cet ordre etait
    inobservable ; ici il devient l'ordre source du tri. Il ne departage que des utilites
    STRICTEMENT egales."""
    return TileIntersect(MovableTilesInRange(Caster(), CasterTile(), Const(int(move_range)),
                                             ignore_flags=False, ignore_units_on_tiles=False),
                         CanAddUnit(AdjacentTiles(Target())))


def ramming_speed_tile_to_move_to(state: "State", caster_id: int, target_id: int,
                                  move_range: Optional[int] = None):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo` —
    MIRROR du decompile :

        First( SortTilesByUtility( <ramming_speed_charge_tiles_selector>,
                                   caster@0x48,
                                   UtilityDefinition( UtilityBucket([ WeightedUtility(7),
                                                                      WeightedUtility(0x36) ], null) ),
                                   parent = null ),
               1 )

    DEUX consommateurs natifs, exactement comme pour Waaagh :
      * l'etage MOVE de `RammingSpeedAbility$$ExecuteBehaviour` —
        `If( !IsAdjacent(caster@0x48, target@0x60, 3), MoveUnit(caster@0x48, <cette tuile>, …) )` ;
      * le gate de ciblage `RammingSpeedAbility$$GetDynamicInvalidTargetReason`, qui appelle
        `SelectTile` sur CE selecteur et rend `0x8000000` quand il ne rend rien.
    Les deux voient donc TOUJOURS la meme tuile.

    `move_range` absent -> lu au gameconfig (`abilities.RammingSpeed.constants.range` = 5), qui est
    la source de `GetNumberConstant(0x16)`. Rend une `(col, row)`, ou None si l'intersection est
    vide (le `MoveUnit` en aval est alors no-op, et le gate de ciblage refuse le cast).

    TROIS consommateurs portes : les deux ci-dessus (face COMBAT, `ramming_speed_tree` et
    `RammingSpeedAbility.get_dynamic_invalid_target_reason`) et le batch EXPLOSION de
    `IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` (face DECISION,
    `playbook/prediction/ramming_speed.tile_to_move_to`, MEME arbre sur substrat `Scene`)."""
    board = getattr(state, "board", None)
    ce = state.get_entity(caster_id)
    if board is None or ce is None or state.get_entity(target_id) is None:
        return None
    if move_range is None:
        consts = (GC.ability("RammingSpeed") or {}).get("constants") or {}
        move_range = int(consts.get("range") or 0)               # GetNumberConstant(0x16 = range)
    cands = ramming_speed_charge_tiles_selector(int(move_range)).evaluate(
        entities_from_state(state, caster_id, target_id))
    if not cands:
        return None
    # `caster@0x48` = le `unit` du selecteur -> `case.unit`, celui dont
    # `RammingSpeed_MostAdjacentEnemies` resout le camp (`GetAdjacentEnemies(tile, case.unit, false)`).
    best = first_tile_by_utility(state, cands, unit_id=caster_id,
                                 utility_definition=RAMMING_SPEED_TILE_UTILITY)
    return board.coord(best) if best is not None else None


RAMMING_SPEED_ID = "RammingSpeed"
RS_CONST_NR_OF_HITS = 0x2f       # GetNumberConstant(0x2f)     -> "nrOfHits"   = 4
RS_CONST_NR_OF_HITS_2 = 0x32     # GetNumberConstant(0x32)     -> "nrOfHits_2" = 2
RS_VAR_MIN_DMG = 0x0c            # GetVariableForLevel(0xc)    -> "minDmg"
RS_VAR_MAX_DMG = 0x0d            # GetVariableForLevel(0xd)    -> "maxDmg"
RS_EXTRA_EXPLODE = int(EffectType.RammingSpeed_ExtraExplode)   # 0x44a = 1098
# `TargetingRule` rendue par `GetDynamicInvalidTargetReason` quand AUCUNE tuile de charge n'est
# atteignable : le litteral natif est `0x8000000` = `TargetIsInRange` (bit 27).
RS_NO_REACHABLE_CHARGE_TILE = int(TR.TargetIsInRange)


def ramming_speed_tree(dest, profile: str):
    """MIRROR 1:1 de `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$
    ExecuteBehaviour` (id 1059). Decompile, dans l'ordre de CONSTRUCTION :

        amount = RandomAmount( GetVariableForLevel(0xc = minDmg), GetVariableForLevel(0xd = maxDmg) )
        prof   = GetDamageProfile(config@0x60)                            # constants.damageProfile
        ifMove = If( op_LogicalNot(IsAdjacent(Caster@0x48, Target@0x60, 3)),
                     MoveUnit(Caster@0x48, GetTileToMoveTo(), <options ZERO>) )
        atk1   = AttackWithAttackDamage( Owner@0x30, Target@0x60, amount, prof,
                                         hits = GetNumberConstant(0x2f = nrOfHits),
                                         AbilityOrEffect(this+0x10), <options ZERO>, 2 )
        atk2   = AttackWithAttackDamage( Owner@0x30, Owner@0x30,  amount, prof,
                                         hits = GetNumberConstant(0x32 = nrOfHits_2), ... )
        addEff = AddEffect( 0x44a = 1098 RammingSpeed_ExtraExplode, AbilityStateReference,
                            source = Owner@0x30, targets = Owner@0x30, <options ZERO> )
        AActiveAbility.Execute( op_Addition( op_Addition(ifMove, addEff),
                                             If(<DSLTriggers+0x20>, op_Addition(atk1, atk2)) ) )

    C'est-a-dire : CHARGE (sautee si deja au contact) -> pose de l'effet 1098 sur SOI -> si le
    porteur a SURVECU au deplacement, `nrOfHits` coups sur la cible PUIS `nrOfHits_2` coups sur
    SOI-MEME (le contrecoup). `Execute` PLAIN, aucun `ExecuteAtomic`, aucun `Group`.

    `<DSLTriggers+0x20>` = **`OwnerIsAlive`** (`IdunBattle.Entities.Triggers.
    OwnerIsAliveAbilityTrigger`) -- nommage et preuve dans le docstring du noeud
    (`entities/triggers.py::OwnerIsAlive`). Il ne porte AUCUN operande : le port ne doit donc PAS y
    conjoindre un `IsAlive(Target())` (le natif ne teste pas la cible ; sur ce chemin elle ne peut
    pas mourir entre le move et l'attaque, mais un conjoint invente est un mirror FAUX).

    SURCHARGE natives resolues PAR L'ADRESSE DU CALL, pas par le nom :
      * `AttackWithAttackDamage` -> l'overload dont le parametre `hits` est un **INT** (les deux
        autres candidats de meme arite prennent un NOEUD ; le natif passe ici le retour d'un
        `GetNumberConstant`, donc un int, et les deux surcharges restantes n'ont pas
        `RammingSpeedAbility$$ExecuteBehaviour` dans leurs xrefs). Elle construit un
        `IdunBattle.Entities.Behaviours.AttackDamageBehaviour` + un `...AttackBehaviour` => famille
        **ATTACK** -> `native_factory="attack"`.
      * `AddEffect` -> l'overload a SIX parametres dont le dernier est une **struct d'options de
        0x20 octets copiee par valeur** (l'autre 6-args prend un NOEUD de duree ; le natif zeroifie
        4 qwords et passe leur adresse). Options ZERO => AUCUN override de duree -> duree DEFAUT de
        l'effet (`duration_rounds=None`), et une SOURCE explicite = `Owner`.

    `dest` = collapse imperatif de `GetTileToMoveTo()` (selecteur S), comme SkyStrike/HammerOfWrath.
    `dest is None` -> `FixedTiles([])` = `MoveUnit` no-op (le natif passe alors un selecteur qui ne
    designe rien, et `MoveUnitBehaviour` ne bouge personne) -- mais le gate de ciblage refuse deja
    le cast dans ce regime (`RS_NO_REACHABLE_CHARGE_TILE`).

    Le degat est en mode BORNES : `RandomAmount(minDmg[level], maxDmg[level])` == exactement ce que
    `ability_attack_params` lit (`min_key`/`max_key` par defaut), et les DEUX attaques partagent le
    MEME noeud `amount` (donc les MEMES bornes) -- seul le nombre de coups differe."""
    if_move = If(Not(IsAdjacent(Caster(), Target())),
                 MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])))
    add_eff = AddEffect(RS_EXTRA_EXPLODE, "RammingSpeed_ExtraExplode", Owner(),
                        duration_rounds=None, source_ref=Owner())
    atk_target = AttackWithAttackDamage(Target(), RAMMING_SPEED_ID, profile, is_melee=True,
                                        native_factory="attack",
                                        ability_type=int(ActiveAbilityType.RammingSpeed))
    atk_self = AttackWithAttackDamage(Owner(), RAMMING_SPEED_ID, profile, is_melee=True,
                                      hits_key="nrOfHits_2", native_factory="attack",
                                      ability_type=int(ActiveAbilityType.RammingSpeed))
    return op_add(op_add(if_move, add_eff),
                  If(OwnerIsAlive(), op_add(atk_target, atk_self)))


class RammingSpeedAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$ExecuteBehaviour`
    (id 1059) -- cf. `ramming_speed_tree()`.

    ZERO porteur au gameconfig (mesure #353 : les 4 citations de `RammingSpeed` sont des
    DEFINITIONS). Confrontee par GREFFE sur `orksKillaKan` (case-92 sec.5bis + injection EXPLICITE
    de la config d'ability, `probe_353_ramming_speed_prediction.build_grafted_seed_bc`).

    Turn-flags = defauts base (1059 ABSENT des overrides `NO_END_TURN`/`NO_ABILITY_USED_FLAG`).

    Renvoie {ability, caster, target, tile, move, add_effect, attack_target, attack_self, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.RammingSpeed)   # 1059
    ABILITY_ID = RAMMING_SPEED_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$.ctor`
    # -- forme « FLAGS DIRECTS » (7 arguments, le `range` est une struct `TargetingRange` de 0x18
    # octets copiee depuis les statiques ; ce n'est NI la surcharge `(this, template)` NI
    # `(this, template, additionalRules)`, dont les xrefs entrantes ne contiennent pas ce ctor) :
    #     TargetingOptions..ctor(&opts, isSelfCasting = 0,
    #                            range = &<TargetingRange statics>+0x18,
    #                            forceMeleeTarget = 1, rules = 0x4002, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0)          <- 0 = AbilityAttackType.DirectTargetAttack
    # Le litteral EST donc le masque effectif. Decomposition :
    #     0x2      TargetMatchesDynamicRule -> PORTE ci-dessous (l'override VIRTUEL
    #              `RammingSpeedAbility$$GetDynamicInvalidTargetReason` ; le delegue `options+0x38`
    #              est passe NUL, la regle passe par le slot de vtable)
    #     0x4000   TargetIsEnemy            -> PORTE (generique)
    # PORTEE : `TargetingRange` statics `+0x18` = `useRangeFromConfig` ->
    # `AActiveAbility$$SetConfigValuesInTargetingOptions` pose `overrideRange =
    # GetNumberConstant(0x16 = range)` = `abilities.RammingSpeed.constants.range` = 5.
    # `forceMeleeTarget = 1` = `RangedBool.False`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$
        GetDynamicInvalidTargetReason` -- MIRROR du decompile :

            casterTile = casterTiles[0]
            movedOrOffTile = UnitExtensions.DidMove(caster)
                             || EntityExtensions.GetMainTile(caster) != casterTile
            isAdjacent = battleQuery.<slot 0x61>(casterTiles, target)      # AreEntitiesAdjacent
            if (movedOrOffTile && !isAdjacent)          return 0x10;       # CasterHasNotMoved
            if (!isAdjacent) {
                if (battleQuery.<slot 0x4f>(target, 1, 1, 1).Count < 1) return 0x20;  # TargetHasFree-
                tile = GetTileToMoveTo().SelectTile(<ctx: caster, target, casterTile>);  # AdjacentTile
                if (tile != null) {
                    path = battleQuery.<slot 0x14>(caster, tile, 0)
                    if (path != null && path.Count != 0) return 0;
                }
                return 0x8000000;                                          # TargetIsInRange
            }
            return 0;                                   # DEJA au contact -> toujours valide

        La 2e clause de `movedOrOffTile` (`MainTile != casterTiles[0]`) se reduit a `DidMove` sur le
        chemin `ExecuteInternal`, qui passe les tuiles REELLES du caster -- meme lecture que
        `targeting.get_invalid_caster_reason`.

        Le test de CHEMIN (`slot 0x14`) est SUBSUME cote port : `ramming_speed_tile_to_move_to`
        n'emet que des tuiles issues de `MovableTilesInRange`, donc deja atteignables au sens du
        port. RESIDU NOMME `#381-r1` : ce pool est le `visited` d'un BFS qui TRAVERSE, la ou le
        natif fait un PATHFINDING -- sur un ring SATURE le port peut donc accepter une cible que le
        natif refuse par `0x8000000`. Ecart d'ACCEPTATION, jamais de refus invente.

        Caster/cible non resolvables -> 0 (permissif, jamais de refus invente)."""
        if target_id is None:
            return 0
        from ..components import unit_has_moved
        cp = self._rs_pos(state, caster_id)
        tp = self._rs_pos(state, target_id)
        if cp is None or tp is None:
            return 0
        is_adjacent = hexgeo.distance(cp, tp) == 1
        if is_adjacent:
            return 0                                     # deja au contact : aucun move, aucun gate
        if unit_has_moved(state, int(caster_id)):
            return int(TR.CasterHasNotMoved)             # 0x10
        board = getattr(state, "board", None)
        if board is None:
            return 0
        ttile = board.id_at(tp[0], tp[1])
        occupied = {self._rs_pos(state, uid) for uid in state.entities}
        free = [n for n in (board.neighbours_native(ttile) if ttile is not None else [])
                if board.walkable(n) and board.coord(n) not in occupied]
        if not free:                                     # `GetFreeAdjacentTiles(target).Count < 1`
            return int(TR.TargetHasFreeAdjacentTile)     # 0x20
        if ramming_speed_tile_to_move_to(state, int(caster_id), int(target_id)) is None:
            return RS_NO_REACHABLE_CHARGE_TILE           # 0x8000000
        return 0

    @staticmethod
    def _rs_pos(state: "State", unit_id):
        e = state.get_entity(unit_id)
        pc = e.get_component(PositionComponent) if e is not None else None
        return (pc.col, pc.row) if pc is not None else None

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        profile = ((GC.ability(RAMMING_SPEED_ID) or {}).get("constants")
                   or {}).get("damageProfile") or "Physical"     # GetDamageProfile(config@0x60)
        dest = ramming_speed_tile_to_move_to(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        ramming_speed_tree(dest, str(profile)).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
        eff = next((p for n, p in ectx.emitted if n == "AddEffect"), None)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": RAMMING_SPEED_ID, "caster": caster_id, "target": target_id,
                "tile": list(dest) if dest else None, "move": moved, "add_effect": eff,
                "attack_target": atks[0] if len(atks) > 0 else None,
                "attack_self": atks[1] if len(atks) > 1 else None, "dsl": True}


def waaagh_ai_tree(unit_id: str) -> PerformAIAction:
    """5e noeud natif IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour (corps INLINE, IDENTIQUE a `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetTriggerSummonsBehaviour`, site IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetTriggerSummonsBehaviour+0xb0) :
        `PerformAIAction( Friends(caster@0x160,
                                  UnitsWithVisualId(VisualUnitIdFromUnitId(Get(GetStringConstant(0))), 1),
                                  3),
                          asGroup=1, resetTurnFlags=1 )`
    MEMES booleans que `SupremeCommanderAbility IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour` -> le socle `PerformAIAction` /
    `ComputerActionOperation.execute_group` s'applique tel quel (reset des flags de tour de TOUTES les
    cibles d'abord, `IdunBattle.Core.Services.AiControl$$ExecuteFor(group) ensuite, restauration enfin).

    ⚠ SELECTEUR **BOARD-WIDE** (`UnitsWithVisualId` est ancre sur le slot partage `@0x80` = toutes les
    unites, AUCUN rayon) -- a ne pas confondre avec le `UnitsWithIds(SurroundingFriends(caster, range))`
    de SupremeCommander. Consequence mecanique : le Waaagh fait rejouer **TOUS** les Ork Boyz allies du
    plateau (y compris ceux d'un cast precedent), pas seulement ceux qui viennent d'etre invoques."""
    return PerformAIAction(Friends(UnitsWithVisualId(VisualUnitIdFromUnitId(Get(unit_id)), 1)),
                           as_group=True, reset_turn_flags=True)


class WaaaghAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` (id 1058, `orksWarboss` « Snotflogga », Orks) —
    MIRROR du DECOMPILE.

    Corps natif (ordre de lecture ; 5 executions top-level SUCCESSIVES, chacune un
    `AActiveAbility.Execute(Group(<b>, caster@0x160, <groupId>), entities)`) :
        opts   = SpawnUnitOptions.WithStatsFromConfig(config, level)
        spawnB = Spawn(caster, PickRandomly(CanAddUnit(AdjacentTiles(casterTile)), GetNumberConstant(0x10)),
                       GetStringConstant(0), opts)                                   # IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour+0xcd..
        buffB  = GetBuffBehaviour(level)                                             # IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour
        moveB  = MoveUnit(caster, First(SortTilesByUtility(GetPossibleMovementTiles(target),
                                                           caster, 0x20), 1), <options nulles>)
        atkB   = GetAttackBehaviour(level)                                           # IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetAttackBehaviour
        aiB    = PerformAIAction(Friends(caster, UnitsWithVisualId(VisualUnitIdFromUnitId(
                                 Get(GetStringConstant(0))), 1), 3), 1, 1)           # IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour+0x2f6+
        Execute(Group(spawnB, caster, 0x22)) ; Execute(Group(buffB, caster, 0x25)) ;
        Execute(Group(moveB,  caster, 0x23)) ; Execute(Group(atkB,  caster, 0x20)) ;
        Execute(Group(aiB,    caster, 0x28))

    Waaagh **n'utilise PAS** `GetAbilityStatModification` (xrefs exhaustives : ses 2 seuls sites sont dans
    SupremeCommander IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour) : `nrOfSummons` et `extraMovement` sont lus BRUTS de la config.

    CINQ executions top-level -> le contexte `entities` est RE-MATERIALISE entre chacune : l'`AbilityEntities`
    natif porte une REF d'etat (les selecteurs de l'etage N voient les mutations des etages < N), alors que
    le `DslContext` du port fige sa liste d'unites a la construction. Sans cette re-materialisation, le
    5e etage (`UnitsWithVisualId`) ne verrait AUCUN des Ork Boyz du 1er etage = **no-op silencieux**.
    (La feuille `Spawn` pousse aussi ses enfants dans `entities.units`, ce qui couvre le cas d'un arbre
    a UNE seule execution -- ici les deux garanties se cumulent.)

    Retour : {spawned, buffed, moved, attack, ai_units, ai_results, count, move_range, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Waaagh)   # 1058
    ABILITY_ID = "Waaagh"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x106004012, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # -> masque LITTERAL (overload « flags directs », pas l'overload preset : le litteral EST le
    # masque effectif). Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2         TargetMatchesDynamicRule        -> consulte GetDynamicInvalidTargetReason
    #     0x10        CasterHasNotMoved               -> PORTE (volet CASTER : le Warboss ne peut pas
    #                                                    caster Waaagh apres s'etre deplace ; MESURE,
    #                                                    cf. probe_115_ability_reason.py)
    #     0x4000      TargetIsEnemy                   -> PORTE (refus sur soi-meme / un allie)
    #     0x6000000   AllowObscuredTarget             -> permissif (aucune contrainte de ligne de vue)
    #     0x100000000 TargetIsNotAdjacent             -> PORTE (#243 ; battleQuery slot 0x61) : une
    #                                                    cible DEJA au contact du Warboss est
    #                                                    refusee AVANT la regle dynamique
    # PORTEE (#241) : `range = TargetingRange` statique `+0x48` = `useWholeBoard` -> le volet
    # generique de portee NE TESTE RIEN. C'est ce qui evite le FORK : la contrainte de
    # distance de Waaagh vit ENTIEREMENT dans `get_dynamic_invalid_target_reason` ci-dessous
    # (qui rend le meme code `TargetIsInRange`). `Waaagh.constants.range` (3) n'est PAS lue
    # par le gate.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.CasterHasNotMoved
        | TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
        | TR.TargetIsNotAdjacent
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetDynamicInvalidTargetReason`
        — MIRROR du decompile :

            tiles = WaaaghAbility.GetPossibleMovementTiles( Get(target) )
            ents  = AbilityEntities(caster, caster, target, ..., casterTiles, ...)
            return Count( tiles.Evaluate(ents) ) > 0 ? 0 : 0x8000000

        `0x8000000` = `TargetingRule.TargetIsInRange` : Waaagh exprime sa contrainte de DISTANCE
        ici (et pas par le volet portee generique du filtre statique). Le predicat : il existe au
        moins une tuile LIBRE et marchable hex-adjacente a la cible, atteignable par le caster en
        `MOVEMENT + extraMovement` pas — autrement dit **la cible doit etre chargeable ce tour-ci,
        sans bouger d'abord**.

        La portee est lue par `waaagh_move_range` (= `UnitMovementRangeWithBonus(caster, 1099,
        Direct(extraMovement))`) : au moment du GATE l'effet 1099 n'est PAS encore pose (les 5
        etages de la behaviour n'ont pas commence) -> la branche `MOVEMENT + bonus` du `If` natif,
        exactement comme le natif qui evalue la meme formule avant toute execution."""
        if target_id is None or state.get_entity(int(target_id)) is None:
            return int(TR.TargetIsInRange)
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        extra_movement = int(consts.get("extraMovement") or 0)   # GetNumberConstant(0xe)
        move_range = waaagh_move_range(state, caster_id, extra_movement)
        tiles = waaagh_possible_movement_tiles_selector(move_range).evaluate(
            entities_from_state(state, caster_id, target_id))
        return 0 if len(tiles) > 0 else int(TR.TargetIsInRange)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        if state.get_entity(caster_id) is None:
            return None
        n_summons = int(consts.get("nrOfSummons") or 0)          # GetNumberConstant(0x10)
        extra_movement = int(consts.get("extraMovement") or 0)   # GetNumberConstant(0xe)
        unit_id = consts.get("unitId")                           # GetStringConstant(0)

        ectx = ExecutionContext(state=state, rng=state.rng)
        # 1) Execute(Group(spawnB, 0x22))
        waaagh_spawn_tree(n_summons).execute(entities_from_state(state, caster_id, target_id), ectx)
        # 2) Execute(Group(buffB, 0x25))
        waaagh_buff_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        # 3) Execute(Group(moveB, 0x23)) — portee et destination LUES APRES le buff (cf. waaagh_move_range).
        move_range = waaagh_move_range(state, caster_id, extra_movement)
        dest = (waaagh_charge_tile(state, caster_id, target_id, move_range)
                if target_id is not None else None)
        waaagh_move_tree(dest).execute(entities_from_state(state, caster_id, target_id), ectx)
        # 4) Execute(Group(atkB, 0x20))
        if target_id is not None:
            waaagh_attack_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        # 5) Execute(Group(aiB, 0x28)) — entities RE-MATERIALISE (les Ork Boyz du 1er etage sont visibles).
        waaagh_ai_tree(unit_id).execute(entities_from_state(state, caster_id, target_id), ectx)

        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        buffed = sorted({p["target"] for n, p in ectx.emitted if n == "AddEffect"})
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        ai = next((p for n, p in ectx.emitted if n == "PerformAIAction"), {})
        return {"spawned": spawned, "buffed": buffed, "moved": moved, "attack": atk,
                "ai_units": ai.get("units") or [], "ai_results": ai.get("results") or [],
                "count": n_summons, "move_range": move_range, "dsl": True}


# ===================== SquigLaunchas (orksRukkatrukk, MACHINE OF WAR, actif 1200) =====================
#
# Porteur : `orksRukkatrukk` « Rukkatrukk » = MACHINE OF WAR (pool `--list-pool`, 8 MoW) -> entite ECS
# hors-plateau (ni Position ni Health), chargee par `_load_machines` (case-mow-offboard-cast).
#
# Index des constantes lues par `SquigLaunchasAbility` (`AbilityConfiguration.Get*Constant(config, i)`) :
CONST_SL_UNIT_ID = 0x00           # GetStringConstant(0)     -> "unitId"      = orksSmnSquig
CONST_SL_ORKS_TARGET = 0x78       # GetNumberConstant(0x78)  -> "nrOfUnits"   = 1  (CIBLAGE, Orks)
CONST_SL_FRIENDS_TARGET = 0x79    # GetNumberConstant(0x79)  -> "nrOfUnits_2" = 2  (CIBLAGE, amis)
CONST_SL_ORKS_SUMMON = 0x81       # GetNumberConstant(0x81)  -> "nrOfUnits_3" = 2  (SUMMON, Orks)
CONST_SL_FRIENDS_SUMMON = 0x82    # GetNumberConstant(0x82)  -> "nrOfUnits_4" = 4  (SUMMON, amis)

SQUIG_LAUNCHAS_ID = "SquigLaunchas"
SQUIG_FACTION = "Orks"            # `UnitsFromFaction(..., 5, 3)` — UnitFaction.Orks = 5 (il2cpp_enums)


def squig_launchas_has_minimum_adjacent_friendly_units(amount: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$HasMinimumAdjacentFriendlyUnits` — MIRROR du DECOMPILE :

        AmountIsEqualOrGreater(
            Friends( Owner@0x148,
                     NonSteppableOrObjectUnits( AdjacentUnits(target@0x178, 1, 3) ) ),
            amount )

    = « au moins `amount` unites ALLIEES DU CASTER (Owner), ni Steppable ni Object, adjacentes (hex 1)
    a la CIBLE ». Le referent de `Friends` est l'OWNER (le caster MoW) : « friendly » = de MON camp,
    pas du camp de la cible (confirme live case-mow §5 : deplacer 2 de MES unites au contact de
    l'ennemi ouvre le ciblage). `AmountIsEqualOrGreater(selecteur, n)` = `Count(sel) >= n`
    (`IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` : slot +0x10 = selecteur COMPTE, +0x20 = seuil, `return seuil <= gauche`)."""
    return AmountIsEqualOrGreater(
        Count(Friends(non_steppable_or_object_units(AdjacentUnits(TargetTile(), Const(1))))),
        Const(int(amount)))


def squig_launchas_has_minimum_adjacent_orks(amount: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$HasMinimumAdjacentOrks` — MIRROR du DECOMPILE : IDENTIQUE a
    `HasMinimumAdjacentFriendlyUnits` avec UN etage de plus, `UnitsFromFaction(..., 5=Orks, 3)` :

        AmountIsEqualOrGreater(
            UnitsFromFaction( Friends(Owner@0x148,
                                      NonSteppableOrObjectUnits(AdjacentUnits(target@0x178, 1, 3))),
                              5 = Orks ),
            amount )

    `IdunBattleLogic.Entities.DSLFactory$$UnitsFromFaction` compare `System.Enum.ToString(UnitFaction)` = le NOM de faction
    (« Orks ») au `FactionId` gameconfig de l'unite -> `ctx.faction_of` cote port."""
    return AmountIsEqualOrGreater(
        Count(UnitsFromFaction(
            Friends(non_steppable_or_object_units(AdjacentUnits(TargetTile(), Const(1)))),
            SQUIG_FACTION)),
        Const(int(amount)))


def squig_launchas_fulfills_summon_criteria(orks_min: int, friends_min: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$FulfillsSummonCriteria` — MIRROR du DECOMPILE :

        op_BitwiseOr( HasMinimumAdjacentOrks(         Direct(GetNumberConstant(0x81)=nrOfUnits_3=2) ),
                      HasMinimumAdjacentFriendlyUnits(Direct(GetNumberConstant(0x82)=nrOfUnits_4=4) ) )

    i2 : « if the target has 2 friendly Orks OR 4 friendly units adjacent to it, summons a Large Squig ».
    ⚠ CONSTANTES DIFFERENTES du predicat de CIBLAGE (`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$GetDynamicInvalidTargetReason` : 0x78=1
    Ork / 0x79=2 amis) — meme paire de predicats, seuils PLUS HAUTS pour le summon."""
    return TriggerOr(squig_launchas_has_minimum_adjacent_orks(orks_min),
                     squig_launchas_has_minimum_adjacent_friendly_units(friends_min))


def squig_launchas_tree(orks_min: int, friends_min: int):
    """Arbre de `SquigLaunchasAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$ExecuteBehaviour` — MIRROR du DECOMPILE :

        attack = AttackWithAbilityDamage( Owner@0x148, target@0x178,
                                          MinMaxDamage, GetDamageProfile(config)=Physical,
                                          GetHits()=ConfigConst(0x2f)=nrOfHits=3,
                                          AbilityOrEffect(0x4b0 = 1200) )
        opts   = SpawnUnitOptions.WithStatsFromConfig(config, abilityState)
        spawn  = Spawn( caster@0x160,
                        PickRandomly( CanAddUnit(AdjacentTiles(Cache(TargetTiles@0x190, 1))), 1,
                                      ..., 0x7fffffff ),
                        GetStringConstant(config, 0) = "orksSmnSquig", opts )
        cond   = Cache( FulfillsSummonCriteria )                              # IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$FulfillsSummonCriteria
        Execute( op_Addition( op_Addition( SetCache(cond), attack ), If(cond, spawn) ) )

    - **ORDRE / TIMING (le point non trivial)** : `SetCache(cond)` s'execute AVANT l'attaque
      (`IdunBattle.Entities.Behaviours.SetCacheBehaviour$$Execute` = evalue le noeud cache, aucune mutation) -> le critere de
      summon est FIGE sur l'etat **PRE-attaque**, puis `If(cond, spawn)` relit le CACHE. Consequence
      mecanique : meme si les 3 coups TUENT la cible, le Squig est invoque des lors que le critere etait
      rempli avant l'attaque.
    - **native_factory = "ability"** : le decompile appelle `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` (PAS `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`) -> `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` : 1 tirage/coup, AUCUN crit, AUCUNE feuille positionnelle. Profil `Physical`
      (PiercingRatio 1), `nrOfHits`=3, `attackRangeType=Ranged` -> `is_melee=False`.
    - **SPAWN** : `AdjacentTiles(Cache(TargetTiles@0x190))` = tuiles hex-adjacentes a la tuile de la
      CIBLE ; `CanAddUnit` = libres+marchables ; `PickRandomly(..., 1)` FOLDE dans la feuille `Spawn`
      (`pick_n=1`, le tirage vit la ou l'on voit `state.rng` — meme convention que Waaagh/SupremeCommander).
      Le port ancre `AdjacentTiles(Target())` (selecteur unit-domain -> tuile de l'unite = MEME tuile que
      `TargetTiles@0x190` ; meme reduction que `waaagh_spawn_tree`). Stats du Squig =
      `WithStatsFromConfig` = `summonHp`/`summonDmg`/`summonArmor`[level] x mult de l'ABILITY (canal
      `AbilityState` de la MoW). AUCUN sous-behaviour on-appearance (`opts+0x18` jamais assigne au
      decompile) : le Squig (trait `Summon`) joue au debut de SON tour, pas a l'apparition."""
    cond = CacheTrigger(squig_launchas_fulfills_summon_criteria(orks_min, friends_min))
    attack = AttackWithAttackDamage(Target(), SQUIG_LAUNCHAS_ID, "Physical", is_melee=False,
                                    native_factory="ability",     # IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage (XREF), 1 tirage/coup
                                    ability_type=int(ActiveAbilityType.SquigLaunchas))
    spawn = Spawn(CanAddUnit(AdjacentTiles(Target())), SQUIG_LAUNCHAS_ID, pick_n=1)
    return op_add(op_add(SetCache(cond), attack), If(cond, spawn))


class SquigLaunchasAbility(ActiveAbility):
    """`SquigLaunchasAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$ExecuteBehaviour` (id 1200, `orksRukkatrukk` « Rukkatrukk »,
    MACHINE OF WAR Orks). Arbre DSL `squig_launchas_tree()` (mirror 1:1) : 3 coups Physical sur la cible
    (famille ABILITY), PUIS — si le critere de summon evalue AVANT l'attaque est rempli — invocation d'un
    `orksSmnSquig` sur un hex libre aleatoire adjacent a la cible.

    PREDICAT DE CIBLAGE (face DECISION/eligibilite, HORS `ExecuteBehaviour`) —
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$GetDynamicInvalidTargetReason`, MIRROR du decompile :
        if !EntityExtensions.IsUnit(target) -> 0
        a = HasMinimumAdjacentOrks(         Direct(GetNumberConstant(0x78)=nrOfUnits=1) )
        b = HasMinimumAdjacentFriendlyUnits(Direct(GetNumberConstant(0x79)=nrOfUnits_2=2) )
        return (b || a) ? 0 : 2
    => cible legale ssi >= 1 Ork allie-du-caster OU >= 2 unites alliees-du-caster adjacentes a elle.
    C'est CE predicat qui rend « 0 cible au spawn » (sweep case-mow §5) : on le MONTE en amenant 1 Ork
    (ou 2 unites quelconques) de MON camp au contact de l'ennemi. Le port n'a PAS de face DECISION pour
    les MoW (case-mow §4) -> le predicat est RE + exerce LIVE (`abilityTargets`), et ses DEUX helpers
    natifs sont neanmoins portes ici : ils sont REUTILISES par `FulfillsSummonCriteria` (seuils 0x81/0x82),
    lui DANS l'ExecuteBehaviour -> confrontables offline.

    Turn-flags = defauts base (1200 absent des overrides). Diag :
    {attacks, summon_criteria, spawned}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SquigLaunchas)   # 1200
    ABILITY_ID = SQUIG_LAUNCHAS_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x40004002, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # Overload « flags DIRECTS » (5e argument -> `options+0x28`) : le litteral EST le masque effectif.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2          TargetMatchesDynamicRule -> `SquigLaunchasAbility$$GetDynamicInvalidTargetReason`
    #                  (>= 1 Ork allie OU >= 2 allies adjacents a la cible ; cf. la docstring de la classe).
    #                  NON surcharge cote port -> defaut 0 = pas de refus dynamique (PERMISSIF assume :
    #                  le port n'a pas de face DECISION pour les MoW, cf. case-mow §4).
    #     0x4000       TargetIsEnemy      -> PORTE (refus sur un allie)
    #     0x40000000   AllowNullCasterTile -> permissif : le caster est une MACHINE OF WAR HORS PLATEAU
    #                  (ni Position ni Health), donc SANS tuile — sans ce bit le volet CASTER refuserait
    #                  tout cast de MoW (`GetInvalidCasterReason` : `casterTiles` vide -> 0x40000000).
    # PORTEE (#241) : `range = TargetingRange` statique `+0x48` = `useWholeBoard` -> aucun
    # test de portee. Indispensable ici : le caster est une MACHINE OF WAR (hors plateau,
    # sans arme gameconfig) -- une portee basee sur l'arme n'aurait aucun sens pour elle.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsEnemy
        | TR.AllowNullCasterTile
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        orks_min = int(consts.get("nrOfUnits_3") or 0)         # GetNumberConstant(0x81)
        friends_min = int(consts.get("nrOfUnits_4") or 0)      # GetNumberConstant(0x82)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        # Verdict du critere de summon (PRE-attaque, == le `SetCache` de l'arbre) pour le diagnostic.
        criteria = bool(squig_launchas_fulfills_summon_criteria(orks_min, friends_min).evaluate(entities))
        squig_launchas_tree(orks_min, friends_min).execute(entities, ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "attacks": attacks, "summon_criteria": criteria, "spawned": spawned,
                "orks_min": orks_min, "friends_min": friends_min, "dsl": True}


# =================================================================================================== #
# SquigMine (1201, `orksRukkatrukk` -- Rukkatrukk Squigbuggy, MachineOfWar) -- lot #90-B
# Patron « pose d'effet(s) seule » : le CAST ne fait que MINER des tuiles (aucune attaque immediate).
# =================================================================================================== #

SQUIG_MINE_ID = "SquigMine"
SQUIG_MINE_TILE = int(EffectType.SquigMine_Tile)     # 0x5a1 = 1441
# Index des variables/constantes lues par `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour`
# (`AbilityConfiguration.Get*`) -> cle gameconfig (croisee avec la config 1201 : nrOfRounds=1, range=2,
# nrOfTiles[level]).
SQUIG_CONST_NR_OF_ROUNDS = 0x45     # GetNumberConstant(0x45)     -> "nrOfRounds" = 1
SQUIG_CONST_RANGE = 0x16            # GetNumberConstant(0x16)     -> "range"      = 2
SQUIG_VAR_NR_OF_TILES = 0x66        # GetVariableForLevel(0x66)   -> "nrOfTiles"[level]


def squig_mine_pool_tree(target_tile_id: int, rng_range: int):
    """POOL de tuiles minables de `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour` -- MIRROR 1:1 :

        EntitiesWithoutEffects(
            CanAddUnit( SurroundingTiles(target@0x178, includeCenter=0, GetNumberConstant(0x16)=range),
                        dsl+0xf8 ),
            [0x5a1=1441 SquigMine_Tile] )

    -> les tuiles a `range` hex de la tuile ciblee (centre EXCLU), LIBRES et walkable (`CanAddUnit`),
    qui ne portent PAS deja une mine. C'est le pool que `PickRandomly` echantillonne."""
    tgt = FixedTileIds([target_tile_id])
    return EntitiesWithoutEffects(
        CanAddUnit(SurroundingTiles(tgt, Const(int(rng_range)), include_center=False)),
        [SQUIG_MINE_TILE])


def squig_mine_tree(target_tile_id: int, picked_tile_ids, duration_turns: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE :

        turns  = TurnsFromRounds( GetNumberConstant(0x45)=nrOfRounds )
        pool   = EntitiesWithoutEffects(CanAddUnit(SurroundingTiles(target, 0, range)), [1441])
        picked = PickRandomly(pool, GetVariableForLevel(0x66)=nrOfTiles[level], 0, 0x7fffffff, false)
        Execute( AddEffect(0x5a1=1441 SquigMine_Tile, absRef, source=owner@0x148,
                           targets=Cache(target@0x178 + picked, 1), turns) )

    UN SEUL noeud `AddEffect` (plain `AActiveAbility.Execute`) -> la tuile CIBLEE est TOUJOURS minee,
    plus `nrOfTiles[level]` tuiles tirees au hasard dans le pool.

    COLLAPSE du `PickRandomly` (doctrine slice-18/19, == BringerOfDespair/Poxwalkers/SendInTheNextWave) :
    le tirage doit voir `state.rng`, que le domaine DSL n'expose pas -> la classe d'ability evalue le pool
    (arbre DSL, cf. `squig_mine_pool_tree`), applique `_pick_randomly_n`, et injecte le resultat par le
    vehicule `FixedTileIds`. Le COUT du tirage est cale depuis #130 (`min(len(pool), nrOfTiles)` tirages,
    bornes decroissantes, MEME quand le pool tient -- cf. `_pick_randomly_n`). ⚠ RESIDU #215 : l'ordre
    d'ENUMERATION natif du pool (non trie) -> quand `len(pool) > nrOfTiles`, l'ENSEMBLE tire peut differer
    du live (le CARDINAL et le POOL, eux, sont exacts)."""
    picked = FixedTileIds(list(picked_tile_ids))
    targets = Cache(Union(FixedTileIds([target_tile_id]), picked))
    return AddEffect(SQUIG_MINE_TILE, EffectType.SquigMine_Tile.name, targets,
                     duration_rounds=None, duration_turns=duration_turns)


class SquigMineAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour` (id 1201, `orksRukkatrukk` -- Rukkatrukk Squigbuggy,
    Orks, MachineOfWar). Cast TILE-TARGET (`abilityTargets` kind="tile", 29 tuiles sur C1_02).

    RE (ghidra gqfc5mff6c) :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour` : cf. `squig_mine_tree` (UN `AddEffect`, zero attaque).
    - `.IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$.ctor` ; `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$AdditionalMarkedTiles` = le MEME pool (preview/playbook) ;
      `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$GetDynamicInvalidTargetReason` = gate de legalite du ciblage (live/RPC, hors behaviour).
    - PHASE 2 (NON PORTEE) : `IdunBattle.Entities.Effects.Loki.SquigMine_TileEffect` (`.IdunBattle.Entities.Effects.Loki.SquigMine_TileEffect$$.ctor`,
      `IdunBattle.Entities.Effects.Loki.SquigMine_TileEffect$$CreateTargetTrigger`, `IdunBattle.Entities.Effects.Loki.SquigMine_TileEffect$$CreateTargetTriggerBehaviour`, `IdunBattle.Entities.Effects.Loki.SquigMine_TileEffect$$GetAttackBehaviour`) -- la mine detone quand une unite entre sur la tuile (minDmg/maxDmg, `damageProfile=
      Blast`, `nrOfHits=3`).

    OBSERVABLE DU CAST (mesure live, runner MoW C1_02, caster 53, cible = tuile (0,1), niveau 50 ->
    `nrOfTiles[49] = 4`) : 5 tuiles portent `SquigMine_Tile` (1441, source 53, remaining 2) = la ciblee
    (0,1) + 4 tirees dans le disque de rayon 2 : (0,3) (1,3) (2,1) (2,2).

    `target_id` = id de TUILE. Flags de tour : defauts base -> termine le tour + ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SquigMine)   # 1201
    ABILITY_ID = SQUIG_MINE_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x46001042, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # Overload « flags DIRECTS » (5e argument -> `options+0x28`) : le litteral EST le masque effectif.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2          TargetMatchesDynamicRule -> `SquigMineAbility$$GetDynamicInvalidTargetReason`
    #                  (non porte -> defaut 0, PERMISSIF assume)
    #     0x40         TargetIsTile        -> cast TILE-TARGET (le domaine TILE n'est pas porte)
    #     0x1000       TargetTileIsFree    -> la tuile doit accepter une unite (`CanAddUnit`), NON PORTE
    #     0x6000000    AllowObscuredTarget -> permissif
    #     0x40000000   AllowNullCasterTile -> permissif (caster = MoW hors plateau, cf. SquigLaunchas)
    # AUCUNE regle du domaine UNITE n'est armee ici : sur une cible-TUILE `_unit_of` rend None et la
    # cascade portee se tait — le masque est donc pose pour la FIDELITE (et pour que le jour ou le
    # domaine TILE sera porte, il morde tout seul), pas pour un refus mesurable aujourd'hui.
    # PORTEE (#241) : `range = TargetingRange` statique `+0x48` = `useWholeBoard` -> aucun
    # test de portee (meme MoW que SquigLaunchas ; `SquigMine.constants.range` = 2 n'est PAS
    # celle du gate).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsTile
        | TR.TargetTileIsFree
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
        | TR.AllowNullCasterTile
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        from ...entities.effects.magnitude import ability_var
        from .loki.splash import _pick_randomly_n
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        if tile_id is None:
            return {"tile": None, "posed": [], "dsl": True}
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        level = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
        mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100) if sc is not None else 100
        rng_range = int(ability_var(SQUIG_MINE_ID, "range", is_constant=True) or 0)
        rounds = int(ability_var(SQUIG_MINE_ID, "nrOfRounds", is_constant=True) or 0)
        n_tiles = int(ability_var(SQUIG_MINE_ID, "nrOfTiles", level, multiplier_pct=mult) or 0)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id)
        pool = squig_mine_pool_tree(tile_id, rng_range).evaluate(entities)   # arbre DSL
        picked = _pick_randomly_n(state, pool, n_tiles)                     # PickRandomly (collapse)
        turns = convert_rounds_to_turns(state, rounds)                      # TurnsFromRounds(nrOfRounds)
        squig_mine_tree(tile_id, picked, turns).execute(entities, ectx)
        posed = [p["target"] for n, p in ectx.emitted if n == "AddEffect"]
        return {"tile": tile_id, "pool": list(pool), "picked": list(picked), "turns": turns,
                "nrOfTiles": n_tiles, "range": rng_range, "posed": posed, "dsl": True}


# ================================================================================================ #
# DakkaDakkaDakka (1171, `orksKillaKan` « Snappawrecka ») — case-decision-noop.
#
# Gisement `[-D]` : la face DECISION etait portee (`DakkaDakkaDakkaAbility` de
# `entities/abilities/active_ability.py`, registre `_SPECIAL_ABILITY_CLASSES` — l'IA PREDIT donc
# `nrOfHits`=6 coups et choisit l'ability), la face COMBAT etait un NO-OP complet.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$ExecuteBehaviour` (MIRROR
# du DECOMPILE, arbre lu noeud par noeud) :
#
#     profile   = GetDamageProfile(config, 0)                         # "Projectile" (pierce 15)
#     numHits   = GetNumHits(this)                                    # cf. `dakka_num_hits`
#     damage    = AActiveAbility.MinMaxDamage(minDmg/maxDmg[level])
#     possible  = Damageable( Unobscured( caster@0x160,               # == $$PossibleLeftoverHitsTargets
#                                         SurroundingEnemies(caster@0x148,
#                                                            GetNumberConstant(0x44 = range_2)) ) )
#     main      = AttackWithAttackDamage( caster@0x148, target@0x178, damage, profile, numHits,
#                                         AbilityOrEffect(this+0x10) )
#     numLeft   = Cache( NumLeftOverHits(target@0x178, AbilityOrEffect(this+0x10)) )
#     picked    = Cache( PickRandomly( possible,
#                                      RandomAmount( One@dsl+0xc0,
#                                                    Min(numLeft, Count(possible)) ),
#                                      allowRepeat=0, maxRepeats=0x7fffffff ) )
#     cnt       = Cache( Count(picked) )
#     q         = Cache( Divide(numLeft, cnt, mode 2 = Floor) )        # \
#     rem       = Difference(numLeft, Multiply(cnt, q))                #  > $$GetLeftoverHitsPerTargetFormula
#     hitsPer   = If( AreEqual(Cache(First(picked, 1)), It@0x180),     # /   (corps INLINE ici)
#                     Sum(q, rem), q )
#     leftAtk   = AttackWithAttackDamage( caster@0x148, picked, damage, profile, hitsPer,
#                                         AbilityOrEffect(this+0x10) )
#     selfLoss  = ChangeStat( caster@0x148, Position(Health=5), mode 3 = Subtract,
#                             GetHealthToLose(this) )
#     Execute( op_and( op_and(main, If(numLeft, leftAtk, null)),
#                      If(IsAlive(caster@0x160), selfLoss, null) ) )
#
# i2 : « Deals 6x [dmg] Projectile Damage to an enemy within range 3. Adds +2 hits for each time
# Snappawrecka was repaired this battle, but cannot exceed 16 hits in total. If the target is
# defeated, leftover hits are allocated to random enemies within 3 hexes. Snappawrecka also loses
# 15% of his maximum Health. »
#
# TROIS COLLAPSES IMPERATIFS, tous du meme genre que ceux deja au depot (BasiliskBarrage collapse
# ses TROIS `PickRandomly`, Waaagh/SquigMine collapsent le leur) — le TIRAGE ne peut pas vivre dans
# un noeud V pur (`AAmountFormula.calculate(ctx)` n'a pas le `state.rng`) :
#   * `NumLeftOverHits` -> `ChainLeftOverHitsAttackDamage._left_over_hits(main_atk, extra=0)` ;
#   * `RandomAmount(1, cnt)` -> `state.rng.next_internal(1, cnt + 1)` (UN tirage) ;
#   * `PickRandomly(possible, n)` -> `_pick_randomly_n(state, pool, n)` (n tirages, bornes
#     decroissantes -- #130/#215).
# L'ORDRE des tirages est celui du natif : attaque MAIN, puis RandomAmount, puis PickRandomly, puis
# attaque LEFTOVER, puis self-loss (deterministe).
# ================================================================================================ #

DDD_ID = "DakkaDakkaDakka"
DDD_CONST_NR_OF_HITS = 0x2f      # GetNumberConstant(0x2f)  -> "nrOfHits"     = 6
DDD_CONST_EXTRA_HITS = 0x64      # GetNumberConstant(100)   -> "extraHits"    = 2
DDD_CONST_MAX_HITS = 0x48        # ConfigConst(0x48)        -> "maxNrOfHits"  = 16
DDD_CONST_RANGE_2 = 0x44         # GetNumberConstant(0x44)  -> "range_2"      = 3
DDD_CONST_HEALTH_PCT = 0x4f      # ConfigConst(0x4f)        -> "healthPct"    = 15
# ^ 0x44 : index NON derivable de la valeur (1171 a `range` == `range_2` == 3). Il est etabli par
#   ELIMINATION sur DEUX configs independantes : 0x16 = `range` est deja ancre (dump.cs
#   AbilityConstantType.range = 22), et le SEUL autre index numerique commun a 1171 et a
#   `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$PossibleTilesForDecoys`
#   (l'autre call-site de 0x44 au depot, cf. `playbook/bespoke.py`) est `range_2`.


def dakka_possible_leftover_targets_tree(range_2: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$PossibleLeftoverHitsTargets`
    — MIRROR 1:1 (le corps est aussi INLINE dans `$$ExecuteBehaviour`) :

        Damageable( Unobscured( caster@0x160,
                                SurroundingEnemies(caster@0x148, GetNumberConstant(0x44), 1, 3) ) )

    = « ennemis du caster dans le disque `range_2` autour de SA tuile (caster exclu), non obscurcis
    depuis le caster, vivants ». `SurroundingEnemies` est ici la surcharge 6-args (reference et
    centre separes, tous deux le caster) -> `reference=None` cote port. `@0x148` (Owner) et `@0x160`
    (Caster) designent la MEME unite pour un cast d'active (owner == caster)."""
    return Damageable(Unobscured(SurroundingEnemies(Caster(), Const(int(range_2))), Caster()))


def dakka_num_hits(times_repaired: int, n_hits: int, extra_hits: int, max_hits: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetNumHits` — MIRROR :

        Min( Sum( Direct(GetNumberConstant(0x2f) = nrOfHits),
                  Multiply( TimesRepaired(caster@0x160),
                            Direct(GetNumberConstant(100) = extraHits) ) ),
             ConfigConst(0x48 = maxNrOfHits) )

    `TimesRepaired` = compteur runtime du caster (`IdunBattle.Entities.Formulas.TimesRepairedFormula`)
    NON capte offline (meme regime documente que `TotalTimesAttacked`, cf. `entities/formulas.py`)
    -> `times_repaired = 0` au cast, donc `hits = nrOfHits` (6). Le snowball reste EXACT des que le
    compteur sera seede : c'est l'arbre entier qui est porte, pas sa valeur au repos."""
    return min(int(n_hits) + int(times_repaired) * int(extra_hits), int(max_hits))


def dakka_main_attack_tree(hits: int) -> AttackWithAttackDamage:
    """1er volet de `$$ExecuteBehaviour` : `AttackWithAttackDamage(caster@0x148, target@0x178,
    MinMaxDamage(minDmg/maxDmg[level]), Nullable(GetDamageProfile), numHits, AbilityOrEffect(+0x10))`.
    `attackRangeType = Ranged` (gameconfig 1171) -> `is_melee=False`. La factory native est
    `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (XREF de l'`ExecuteBehaviour`) ->
    famille **ATTACK** (`native_factory="attack"`, 2 tirages/coup a cc=0)."""
    return AttackWithAttackDamage(Target(), DDD_ID, "Projectile", is_melee=False,
                                  native_factory="attack", hits=None, hits_override=int(hits),
                                  ability_type=int(ActiveAbilityType.DakkaDakkaDakka))


def dakka_leftover_attack_tree(targets: list, hits: int) -> AttackWithAttackDamage:
    """2e volet : `AttackWithAttackDamage(caster@0x148, <picked>, MEME damage/profil, hitsPer,
    AbilityOrEffect(+0x10))`. Les cibles sont deja TIREES (collapse du `PickRandomly`) -> le
    selecteur est un `FixedUnits` sur leurs ids et `multi=True` folde l'`OrderBy` de
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (`if Count > 1 : OrderBy(b__5_0)`)."""
    return AttackWithAttackDamage(UnitSet(list(targets)), DDD_ID, "Projectile", is_melee=False,
                                  multi=True, native_factory="attack",
                                  hits=None, hits_override=int(hits),
                                  ability_type=int(ActiveAbilityType.DakkaDakkaDakka))


class DakkaDakkaDakkaAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$ExecuteBehaviour`
    (id 1171, `orksKillaKan` « Snappawrecka », Orks) — cf. l'en-tete de section pour l'arbre LU.

    Trois volets, dans l'ORDRE natif : (1) `numHits` coups Projectile (pierce 15) sur la cible ;
    (2) si la cible est morte, les coups GASPILLES sont repartis sur des ennemis TIRES au hasard
    dans le disque `range_2` du caster ; (3) le caster perd `healthPct`% de son PV **MAXIMUM**
    (`StatAmount(Self, Health, StatPart.MAXIMUM=2)` — LU, cf. `SubtractHealthPercent.stat_part`),
    sous le gate `IsAlive(caster)`.

    RESIDU NOMME (le seul) — la distribution du RESTE. Le nœud natif est
    `If(AreEqual(Cache(First(picked,1)), It@0x180), Sum(q, rem), q)` : la 1re cible du pick recoit
    `q + rem`, les autres `q`. `It@0x180` = `ActiveTarget` = le **slot 4** de l'`AbilityEntities`
    (`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` : `param_1[4] = param_3`). Or NI
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (qui n'ecrit que les slots 1 = actor
    et 2 = target de sa copie) NI `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget`
    (qui evalue le noeud de coups `+0x90` contre l'`entities` RECU tel quel) ne lient ce slot 4 :
    LU au decompile, pas suppose. Sa valeur au cast top-level n'a pas ete RE. Le port evalue donc le
    predicat contre `entities.active_target`, qui vaut `None` sur ce chemin -> **toutes** les cibles
    piquees recoivent `q`, et `rem` (0..cnt-1 coups) n'est pas distribue. Ecart BORNE par
    `cnt - 1` coups, et NUL des que `numLeft` est divisible par `cnt` (dont tout le cas `cnt == 1`,
    le plus frequent). Fermer ce residu = RE du slot 4 de l'`AbilityEntities` d'un cast top-level.

    Renvoie {ability, caster, target, hits, main_attack, num_left, picked, hits_per, leftover,
    self_loss, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DakkaDakkaDakka)   # 1171
    ABILITY_ID = DDD_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$.ctor`
    # est de la forme PRESET COPIE : il n'ecrit AUCUN flag, il recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` a l'offset **+0x140** du bloc `<class>+0xb8`, puis
    # `TargetingOptions..ctor(&opts, &preset, 0)` (copie) et `AActiveAbility..ctor(this, &opts, 0, 0)`.
    # C'est EXACTEMENT le meme preset que
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$.ctor` (1006,
    # necrons.py) et `...GravitonRifleAbility$$.ctor` (1206, votann.py) : masque effectif =
    # `preset+0x28` = statics `+0x168` = `0x4002`, valeur CONSTANTE ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` (deja lue pour ces deux ports).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2      TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`, que 1171 ne
    #              surcharge PAS (aucun symbole ; le slot vtable reste le defaut 0) -> aucun refus
    #              dynamique, degradation PERMISSIVE assumee et identique au natif.
    #     0x4000   TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie).
    # PORTEE : meme preset -> `TargetingRange` statique `+0x18` = `useRangeFromConfig`
    # (`DakkaDakkaDakka.constants.range` = 3) + `forceMeleeTarget = True`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def _params(self, state: "State", caster_id: int) -> tuple:
        from ...entities.effects.magnitude import ability_var
        n_hits = int(ability_var(DDD_ID, "nrOfHits", is_constant=True) or 1)
        extra_hits = int(ability_var(DDD_ID, "extraHits", is_constant=True) or 0)
        max_hits = int(ability_var(DDD_ID, "maxNrOfHits", is_constant=True) or n_hits)
        range_2 = int(ability_var(DDD_ID, "range_2", is_constant=True) or 1)
        return n_hits, extra_hits, max_hits, range_2

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        from .loki.splash import _pick_randomly_n
        from .behaviours.combat import ChainLeftOverHitsAttackDamage
        from .behaviours import SubtractHealthPercent
        from ...entities.stats import StatPart
        from ...dsl.base import _is_alive

        n_hits, extra_hits, max_hits, range_2 = self._params(state, caster_id)
        # `TimesRepaired(caster@0x160)` : compteur runtime non capte offline -> 0 (cf. `dakka_num_hits`).
        hits = dakka_num_hits(0, n_hits, extra_hits, max_hits)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)

        # (1) MAIN — `AttackWithAttackDamage(caster, target, damage, profile, numHits)`.
        dakka_main_attack_tree(hits).execute(entities, ectx)
        main = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)

        # (2) `numLeft = Cache(NumLeftOverHits(target@0x178, AbilityOrEffect(+0x10)))`.
        # `IdunBattle.Entities.Formulas.NumLeftOverHitsFormula$$Calculate` = nb d'entrees
        # `LeftOverDamages` de la CIBLE dont le FLAG est vrai ET dont la source est CETTE ability.
        # C'est le `count` de `ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits` **sans** son
        # terme `+ extraHits` (ce noeud-ci ne fait que compter) -> `_left_over_hits(atk, extra=0)`,
        # la loi deja mesuree sur 4 regimes (#125).
        num_left = ChainLeftOverHitsAttackDamage._left_over_hits(main or {}, 0) if main else 0
        picked: list = []
        hits_per = 0
        leftover: list = []
        if num_left > 0:                                   # `If(numLeft, leftAtk, null)`
            pool = [u for u in dakka_possible_leftover_targets_tree(range_2).evaluate(entities)
                    if (u or {}).get("id") is not None]    # ordre SOURCE (aucun tri avant le tirage)
            cnt_max = min(int(num_left), len(pool))        # `Min(numLeft, Count(possible))`
            # `RandomAmount(One@dsl+0xc0, cnt_max)` -> `rng.NextInternal(min, max + 1)` (borne haute
            # INCLUSIVE, cf. `IdunBattle.Entities.Formulas.RandomAmount$$Calculate` : `(min, max+1)`).
            n = state.rng.next_internal(1, cnt_max + 1) if state.rng is not None else min(1, cnt_max)
            picked = _pick_randomly_n(state, pool, int(n))  # `PickRandomly(possible, n, 0, 0x7fffffff)`
            cnt = len(picked)
            if cnt > 0:
                # `$$GetLeftoverHitsPerTargetFormula` : `q = Divide(numLeft, cnt, Floor)`,
                # `rem = numLeft - cnt*q`, `hitsPer = If(AreEqual(First(picked), ActiveTarget), q+rem, q)`.
                # Le predicat porte tel quel (cf. RESIDU NOMME dans la docstring de classe) :
                # `active_target` non lie sur ce chemin -> branche `q`.
                q = int(num_left) // cnt
                rem = int(num_left) - cnt * q
                first_is_active = (entities.active_target is not None
                                   and (entities.active_target or {}).get("id") == picked[0].get("id"))
                hits_per = q + rem if first_is_active else q
                if hits_per > 0:
                    before = len(ectx.emitted)
                    dakka_leftover_attack_tree(picked, hits_per).execute(entities, ectx)
                    leftover = [{"target": p["target"], "total": p["total"]}
                                for n2, p in ectx.emitted[before:] if n2 == "AttackWithAttackDamage"]

        # (3) `If(IsAlive(caster@0x160), ChangeStat(caster, Health, Subtract,
        #        PercentageOf(StatAmount(caster, Health, MAXIMUM), ConfigConst(healthPct))), null)`.
        self_loss = None
        if _is_alive(entities.caster):
            before = len(ectx.emitted)
            SubtractHealthPercent(Caster(), DDD_ID, "healthPct",
                                  stat_part=int(StatPart.MAXIMUM)).execute(entities, ectx)
            self_loss = next((p for n2, p in ectx.emitted[before:] if n2 == "ChangeStat"), None)
        return {"ability": DDD_ID, "caster": caster_id, "target": target_id, "hits": hits,
                "main_attack": main, "num_left": num_left,
                "picked": [u.get("id") for u in picked], "hits_per": hits_per,
                "leftover": leftover, "self_loss": self_loss, "range_2": range_2, "dsl": True}
