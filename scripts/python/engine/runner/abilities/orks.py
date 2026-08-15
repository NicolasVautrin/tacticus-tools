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
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE,
                        RANGED_BOOL_IF_RANGED_CASTER, RANGED_BOOL_TRUE, TargetingOptions,
                        entity_tiles, has_steppable_unit, units_are_friendly)
from .targeting_rule import TargetingRule as TR
from ..components import (HealthComponent, PositionComponent, StatsComponent, UnitComponent,
                          has_effect_of_type)   # #484 : hisse
from ...services.battle_query import are_entities_adjacent
from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import AtomicGroup, If, SetCache, op_add, op_and
from ...entities.effect_type import EffectType
from ...entities.formulas import Count, Get, Multiply, RoundsStarted, Sum, VisualUnitIdFromUnitId
from ...entities.selectors.accessors import (
    ActiveTarget, CasterTile, FixedTileIds, FixedTiles, Owner, SelectTile, SurroundingTiles,
    Target, TargetTile
)
from ...entities.selectors.geometry import Cache, EntitiesWithoutEffects, UnitsWithVisualId
from ...entities.selectors.tiles import (
    AdjacentTiles, AllAliveUnits, AllUnits, CanAddUnit, Caster, MovableTilesInRange, TileIntersect,
    tiles_unit_can_move_to_charge_target
)
from ...entities.selectors.units import (
    AdjacentFriends, AdjacentUnits, Damageable, Friends, Sub, SurroundingEnemies, Union, Unique,
    UnitSet, UnitsFromFaction, Unobscured, non_steppable_or_object_units
)
from ...entities.stats import StatType
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve #585-r1,
#: build `rnca9r7q6c`, littéral par littéral (jamais par symetrie).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3
from ...entities.triggers import (AmountIsEqualOrGreater, CacheTrigger, IsAdjacent, Not,
                                  OwnerIsAlive, TriggerOr)
from ...utilities.decider import UtilityBucket, UtilityDefinition, WeightedUtility
from ...utilities.tile import first_tile_by_utility
from ...utilities.utility_type import UtilityType
from .behaviours.ai_control import PerformAIAction
from .behaviours.combat import (AttackWithAttackDamage, ChainLeftOverHitsAttackDamage,
                                UseActiveAbility)
from .behaviours.context import entities_from_state
from .behaviours.effects import AddEffect
from .behaviours.lifecycle import KillDeadUnits
from .behaviours.movement import MoveUnit
from .behaviours.summon import PerformAIAttack, Spawn, StatModifierFormula
from ...entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3
from ...entities.ability_variable_type import AbilityVariableType   # #270-r1-r1-r3
from ...dsl.base import _is_alive
from ...entities.effects.magnitude import ability_var
from ...entities.stats import StatPart
from ..components import unit_has_moved
from .behaviours.stats import SubtractHealthPercent
from .loki.splash import _pick_randomly_n

if TYPE_CHECKING:
    from ..state import State

# Index des constantes lues par `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` et ses helpers
# (`AbilityConfiguration.Get*Constant(config, <index>)`) -> cle gameconfig correspondante.
CONST_UNIT_ID = 0x00            # GetStringConstant(0)     -> "unitId"        = orksOrkBoys
CONST_EXTRA_MOVEMENT = AbilityConstantType.extraMovement     # GetNumberConstant(0xe)   -> "extraMovement" = 1
CONST_NR_OF_SUMMONS = AbilityConstantType.nrOfSummons      # GetNumberConstant(0x10)  -> "nrOfSummons"   = 2

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
        `Unique( <dsl>+0x48 = Caster
                 + AdjacentFriends(<dsl>+0x48, 1, 3)
                 + UnitsFromFaction(Friends(<dsl>+0x48, <dsl>+0x20, 3), 5=Orks, 3) )`
    (`TargetsSelector.op_Addition` = union, puis `Unique` = dedup par entite). `<dsl>+0x20` = le slot
    PARTAGE `IdunBattle.Entities.Selectors.AllAliveUnitsSelector` (pool `EntityPool.AliveUnits`) pose
    par `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` -> porte `AllAliveUnits()`. Ce n'est
    PAS `DSLSelectors$$AllUnits`, que la MEME ability appelle deux noeuds plus loin, dans
    `GetAttackBehaviour` (#514).
    Portee : le caster, ses allies ADJACENTS (quelle que soit leur faction) et TOUS ses allies de faction
    **Orks** (board-wide, aucun rayon).

    `AdjacentFriends` porte prend un CENTRE-POSITION (convention des selecteurs d'anneau du port) ->
    `CasterTile()` designe la MEME ancre que le `caster@0x160` natif (self exclu par `_within`, puis
    reinjecte par l'union `Caster()` — exactement l'`op_Addition(caster, adjacentFriends)` natif)."""
    # #585-r1 -- littéraux LUS dans `...WaaaghAbility$$GetBuffedUnitsSelector` :
    #   AdjacentFriends(gs, gs@0x48, unique: 1, 3)   <- surcharge `(this, unit, unique, selectionType)`
    #   Friends(gs, gs@0x48, gs@0x20, 3) ; UnitsFromFaction(gs, ., 5, 3)
    # L'ETAGE EXISTE depuis #585-r3 : `AdjacentFriends` et `UnitsFromFaction` portent le parametre.
    # La surcharge d'`AdjacentFriends` est la VARIANTE A (`(this, unit, unique, selectionType)`) --
    # tranche par XREF ENTRANTE : `WaaaghAbility$$GetBuffedUnitsSelector` n'appelle pas la variante B
    # (celle qui code `3` en dur et prend une ancre geometrique en 3e argument).
    return Unique(Union(Union(Caster(), AdjacentFriends(CasterTile(), Const(1),
                                                        selection_type=SELECTION)),
                        UnitsFromFaction(Friends(AllAliveUnits(), selection_type=SELECTION),
                                         WAAAGH_FACTION, selection_type=SELECTION)))


def waaagh_buff_tree():
    """2e noeud natif IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour = `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` :
        `op_BitwiseAnd( op_BitwiseAnd(
              AddStaticStatModifierEffect(sel, 1099=Waaagh_ExtraMovement, stat=MOVEMENT(1),
                                          Direct(GetNumberConstant(0xe)=extraMovement), duree@dsl+0xc0=1),
              AddEffect(0x44c=1100 Waaagh_ExtraDamage, AbilityStateReference, caster@0x160, sel, duree@0xc0) ),
              AddEffect(0x44d=1101 Waaagh_ExtraHits,   AbilityStateReference, caster@0x160, sel, duree@0xc0) )`

    Les TROIS effets partagent le MEME selecteur (`waaagh_buffed_units_selector`) et la MEME duree
    (`dsl+0xc0` = `Direct(1)` pose par `DSLFactory..IdunBattleLogic.Entities.DSLFactory$$.ctor` -> 1 round).

    `AddStaticStatModifierEffect` (IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect) n'a PAS de feuille dediee dans le port : le mapping etabli
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
    """`IdunBattleLogic.Entities.DSLFormulas$$UnitMovementRangeWithBonus(caster@0x160, 1099, Direct(extraMovement))`
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
        `Count`). Les deux voient donc TOUJOURS le meme ensemble.

    `SelectTile` = mirror du `TargetsSelector$$SelectTile` (vslot 0xc) par lequel
    `MovableTilesInRangeSelector$$Select` -- le selecteur que construit
    `DSLSelectors$$TilesUnitCanMoveToChargeTarget` -- resout son `casterTiles` (#459)."""
    return tiles_unit_can_move_to_charge_target(Caster(), SelectTile(CasterTile()), Target(),
                                                Const(int(move_range)), ignore_flags=False)


def waaagh_charge_tile(state: "State", caster_id: int, target_id: int, move_range: int):
    """Selecteur de destination de l'etage MOVE de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` :

        `First( SortTilesByUtility( WaaaghAbility.GetPossibleMovementTiles(target@0x178),
                                    caster@0x160, 0x20 ), 1 )`

    L'operande `GetPossibleMovementTiles` est l'ARBRE DSL `waaagh_possible_movement_tiles_selector`
    (mirror 1:1). Le litteral d'utilite est **0x20 = 32 = `UtilityType.MovementSuggestion`** (relu au
    decompile : `SortTilesByUtility(factory, pool, caster@0x160, 0x20)` -- la surcharge int de
    `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility`, qui construit
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
    - `KillDeadUnits(Killer(<dsl>+0x68 = ActiveTarget), AllUnits())` : finalisation des cadavres. Le
      port MIRROR la structure SANS re-muter (la mort est finalisee INLINE par l'attaque, cf.
      `behaviours/lifecycle.py`) et n'exploite PAS `subject_sel` -> le noeud `Killer(...)` (non porte)
      est represente par son operande `ActiveTarget`.
      ⚠ **ICI, et ICI SEULEMENT dans cette ability, le natif appelle `DSLSelectors$$AllUnits`** --
      la primitive pool `EntityPool.AllUnits`, MORTS INCLUS (verifie au decompile de
      `WaaaghAbility$$GetAttackBehaviour`, `rnca9r7q6c`). C'est exigé par le sens du noeud : un
      selecteur d'unites VIVANTES ne peut, par construction, rendre aucun cadavre a finaliser --
      le volet `downed` serait TOUJOURS vide. Le buff, deux noeuds plus haut, passe lui `+0x20`
      (`AllAliveUnits`). #514."""
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

RAMMING_SPEED_CONST_RANGE = AbilityConstantType.range   # GetNumberConstant(0x16) -> "range" = 5 (AbilityConstantType.range)

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
    # `MovableTilesInRangeSelector$$Select` resout son `unitTileSelector` (+0x28) par
    # `TargetsSelector$$SelectTile` -- UNE tuile de depart, pas l'empreinte (#459).
    return TileIntersect(MovableTilesInRange(Caster(), SelectTile(CasterTile()),
                                             Const(int(move_range)),
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
RS_CONST_NR_OF_HITS = AbilityConstantType.nrOfHits       # GetNumberConstant(0x2f)     -> "nrOfHits"   = 4
RS_CONST_NR_OF_HITS_2 = AbilityConstantType.nrOfHits_2     # GetNumberConstant(0x32)     -> "nrOfHits_2" = 2
RS_VAR_MIN_DMG = AbilityVariableType.minDmg            # GetVariableForLevel(0xc)    -> "minDmg"
RS_VAR_MAX_DMG = AbilityVariableType.maxDmg            # GetVariableForLevel(0xd)    -> "maxDmg"
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

        LE SLOT 0x61 N'EST PAS `hexgeo.distance == 1` (#433-r4-r1-r4-r2-r1-r1-r1). C'est
        `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`, surcharge
        `(IList tiles, IEntity unit)` -- celle dont la signature colle au call-site (le meme `target`
        part ensuite au slot 0x4f, qui prend une ENTITE) :

            AreEntitiesAdjacent(casterTiles, target)
              -> MovementUtil.AreTilesAdjacent(casterTiles, EntityExtensions.GetTiles(target))
                 -> foreach t1 in casterTiles: foreach t2 in targetTiles:
                        AreTilesAdjacent(t1, t2)   // vrai des qu'UNE paire l'est
                    AreTilesAdjacent(t1, t2) = (|dElev| < 2)
                                             & (t1 == t2 || ConnectivityComponent(t1).IsNeighbour(t2))

        soit TROIS etages qu'une distance hexagonale rate, tous PERMISSIFS : la liste STOCKEE
        (`ConnectivityComponent+0x10`, pas la couronne hex), la porte d'ELEVATION, et les
        EMPREINTES (deux `IList`, pas deux tuiles principales -- une unite multi-hex est adjacente
        par n'importe lequel de ses pieds). D'ou l'appel au foyer partage
        `services.battle_query.are_entities_adjacent`, qui porte les trois et DELEGUE a
        `targeting.are_entities_adjacent` des qu'un board est la : le verdict de ciblage de
        RammingSpeed et celui de la cascade generique sortent litteralement de la meme fonction.
        `board` absent (scene de test) -> sa degradation NOMMEE (adjacence hex pure + court-circuit
        d'identite, sans porte d'elevation), jamais une geometrie nue de plus.

        Le test de CHEMIN (`slot 0x14`) est SUBSUME cote port : `ramming_speed_tile_to_move_to`
        n'emet que des tuiles issues de `MovableTilesInRange`, donc deja atteignables au sens du
        port. RESIDU NOMME `#381-r1` : ce pool est le `visited` d'un BFS qui TRAVERSE, la ou le
        natif fait un PATHFINDING -- sur un ring SATURE le port peut donc accepter une cible que le
        natif refuse par `0x8000000`. Ecart d'ACCEPTATION, jamais de refus invente.

        Caster/cible non resolvables -> 0 (permissif, jamais de refus invente)."""
        if target_id is None:
            return 0
        cp = self._rs_pos(state, caster_id)
        tp = self._rs_pos(state, target_id)
        if cp is None or tp is None:
            return 0
        board = getattr(state, "board", None)
        is_adjacent = are_entities_adjacent(entity_tiles(state, caster_id),
                                            entity_tiles(state, target_id), board)
        if is_adjacent:
            return 0                                     # deja au contact : aucun move, aucun gate
        if unit_has_moved(state, int(caster_id)):
            return int(TR.CasterHasNotMoved)             # 0x10
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
CONST_SL_ORKS_TARGET = AbilityConstantType.nrOfUnits       # GetNumberConstant(0x78)  -> "nrOfUnits"   = 1  (CIBLAGE, Orks)
CONST_SL_FRIENDS_TARGET = AbilityConstantType.nrOfUnits_2    # GetNumberConstant(0x79)  -> "nrOfUnits_2" = 2  (CIBLAGE, amis)
CONST_SL_ORKS_SUMMON = AbilityConstantType.nrOfUnits_3       # GetNumberConstant(0x81)  -> "nrOfUnits_3" = 2  (SUMMON, Orks)
CONST_SL_FRIENDS_SUMMON = AbilityConstantType.nrOfUnits_4    # GetNumberConstant(0x82)  -> "nrOfUnits_4" = 4  (SUMMON, amis)

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
    # #585-r1 -- les TROIS litteraux LUS dans `...SquigLaunchasAbility$$HasMinimumAdjacentFriendlyUnits` :
    #   AdjacentUnits(gs, gs@0x60, unique: 1, 3) ; NonSteppableOrObjectUnits(gs, ., 3) ; Friends(gs, gs@0x30, ., 3)
    return AmountIsEqualOrGreater(
        Count(Friends(non_steppable_or_object_units(AdjacentUnits(TargetTile(), Const(1),
                                                                  selection_type=SELECTION),
                                                    selection_type=SELECTION),
                      selection_type=SELECTION)),
        Const(int(amount)))


def squig_launchas_has_minimum_adjacent_orks(amount: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$HasMinimumAdjacentOrks` — MIRROR du DECOMPILE : IDENTIQUE a
    `HasMinimumAdjacentFriendlyUnits` avec UN etage de plus, `UnitsFromFaction(..., 5=Orks, 3)` :

        AmountIsEqualOrGreater(
            UnitsFromFaction( Friends(Owner@0x148,
                                      NonSteppableOrObjectUnits(AdjacentUnits(target@0x178, 1, 3))),
                              5 = Orks ),
            amount )

    `IdunBattleLogic.Entities.DSLSelectors$$UnitsFromFaction` compare `System.Enum.ToString(UnitFaction)` = le NOM de faction
    (« Orks ») au `FactionId` gameconfig de l'unite -> `ctx.faction_of` cote port."""
    # #585-r1 -- les QUATRE litteraux LUS dans `...SquigLaunchasAbility$$HasMinimumAdjacentOrks` :
    #   AdjacentUnits(gs, gs@0x60, unique: 1, 3) ; NonSteppableOrObjectUnits(gs, ., 3) ;
    #   Friends(gs, gs@0x30, ., 3) ; UnitsFromFaction(gs, ., 5, 3)
    return AmountIsEqualOrGreater(
        Count(UnitsFromFaction(
            Friends(non_steppable_or_object_units(AdjacentUnits(TargetTile(), Const(1),
                                                                selection_type=SELECTION),
                                                  selection_type=SELECTION),
                    selection_type=SELECTION),
            SQUIG_FACTION, selection_type=SELECTION)),
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
    - **native_factory = "ability"** : le decompile appelle `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (PAS `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`) -> `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` : 1 tirage/coup, AUCUN crit, AUCUNE feuille positionnelle. Profil `Physical`
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
                                    native_factory="ability",     # IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage (XREF), 1 tirage/coup
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
    #                  PORTE depuis #287-r11 -- cf. la surcharge ci-dessous.
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

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile, ligne a ligne (#287-r11) :

            if (!EntityExtensions.IsUnit(target)) return 0;
            entities = new AbilityEntities(caster, caster, target, caster, ...);
            a = HasMinimumAdjacentOrks(         Direct(GetNumberConstant(0x78 nrOfUnits)) )
                    .ShouldTrigger(entities, 0x20);
            b = HasMinimumAdjacentFriendlyUnits(Direct(GetNumberConstant(0x79 nrOfUnits_2)) )
                    .ShouldTrigger(entities, 0x20);
            return (b || a) ? 0 : 2;                    // 2 = TargetingRule.TargetMatchesDynamicRule

        LES DEUX PREDICATS ETAIENT DEJA PORTES, et c'est ce qu'il fallait verifier avant d'ecrire
        quoi que ce soit : `squig_launchas_has_minimum_adjacent_orks` /
        `..._has_minimum_adjacent_friendly_units` servent deja `FulfillsSummonCriteria` dans
        l'`ExecuteBehaviour`. SEULS LES SEUILS CHANGENT -- et c'est le piege de cette surcharge :
        le CIBLAGE lit `0x78`/`0x79` (`nrOfUnits` = 1 Ork, `nrOfUnits_2` = 2 amis), le SUMMON lit
        `0x81`/`0x82` (`nrOfUnits_3` = 2 Orks, `nrOfUnits_4` = 4 amis). Reutiliser
        `squig_launchas_fulfills_summon_criteria` ici poserait les seuils DU SUMMON sur le ciblage
        -- un SUR-refus systematique (plus strict que le natif), l'inverse exact de la degradation
        que cette tranche vient corriger.

        `AbilityEntities(caster, actor: caster, target, owner: caster, ...)` (signature LUE dans
        `frida/methods.tsv` : `caster, actor, target, owner, casterTile, activePlayer, ...`) -> le
        referent `Owner` de `Friends` EST le caster, exactement comme dans l'`ExecuteBehaviour`.
        `entities_from_state(state, caster_id, target_id)` produit le meme contexte.

        `IsUnit(target)` : cote port `state.entities` ne contient que des unites/MoW, donc un
        `target_id` qui n'y resout pas N'EST PAS une unite (tuile du board, id inconnu) -> `0`,
        mirror exact du garde d'entree natif (permissif, pas un refus)."""
        if target_id is None:
            return 0
        ents = entities_from_state(state, int(caster_id), int(target_id))
        if ents.target is None:
            return 0                                   # !EntityExtensions.IsUnit(target) -> 0
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        orks_min = int(consts.get(CONST_SL_ORKS_TARGET.name) or 0)        # GetNumberConstant(0x78)
        friends_min = int(consts.get(CONST_SL_FRIENDS_TARGET.name) or 0)  # GetNumberConstant(0x79)
        a = bool(squig_launchas_has_minimum_adjacent_orks(orks_min).should_trigger(ents))
        b = bool(squig_launchas_has_minimum_adjacent_friendly_units(friends_min).should_trigger(ents))
        return 0 if (b or a) else int(TR.TargetMatchesDynamicRule)


# =================================================================================================== #
# SquigMine (1201, `orksRukkatrukk` -- Rukkatrukk Squigbuggy, MachineOfWar) -- lot #90-B
# Patron « pose d'effet(s) seule » : le CAST ne fait que MINER des tuiles (aucune attaque immediate).
# =================================================================================================== #

SQUIG_MINE_ID = "SquigMine"
SQUIG_MINE_TILE = int(EffectType.SquigMine_Tile)     # 0x5a1 = 1441
# Index des variables/constantes lues par `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour`
# (`AbilityConfiguration.Get*`) -> cle gameconfig (croisee avec la config 1201 : nrOfRounds=1, range=2,
# nrOfTiles[level]).
SQUIG_CONST_NR_OF_ROUNDS = AbilityConstantType.nrOfRounds     # GetNumberConstant(0x45)     -> "nrOfRounds" = 1
SQUIG_CONST_RANGE = AbilityConstantType.range            # GetNumberConstant(0x16)     -> "range"      = 2
SQUIG_VAR_NR_OF_TILES = AbilityVariableType.nrOfTiles        # GetVariableForLevel(0x66)   -> "nrOfTiles"[level]


def squig_mine_pool_tree(target_tile_id: int, rng_range: int):
    """POOL de tuiles minables de `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour` -- MIRROR 1:1 :

        EntitiesWithoutEffects(
            CanAddUnit( SurroundingTiles(target@0x178, includeCenter=0, GetNumberConstant(0x16)=range),
                        dsl+0xf8 ),
            [0x5a1=1441 SquigMine_Tile] )

    -> les tuiles a `range` hex de la tuile ciblee (centre EXCLU), LIBRES et walkable (`CanAddUnit`),
    qui ne portent PAS deja une mine. C'est le pool que `PickRandomly` echantillonne."""
    tgt = FixedTileIds([target_tile_id])
    # `allow_steppable=False` EXPLICITE (#462-...-r5-r3) : ce call-site prend la surcharge a DEUX
    # arguments de `DSLSelectors$$CanAddUnit` et lui passe `<DSLTriggers+0x40>` -- releve a l'octet
    # (`mov r8,[r8+0x40]` juste avant le call), donc `ShouldTrigger` VRAI et `allowSteppable` FAUX.
    # C'est l'un des 14 call-sites natifs sur 147 a valoir FALSE ; le defaut du noeud est `True`.
    return EntitiesWithoutEffects(
        CanAddUnit(SurroundingTiles(tgt, Const(int(rng_range)), include_center=False),
                   allow_steppable=False),
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
    #                  PORTE depuis #287-r4-r1 -- cf. la surcharge ci-dessous
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

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile, ligne a ligne (#287-r4-r1) :

            if (target == null) return 0;
            if (EntityExtensions.HasEffect(target, state, 0x5a1, onlyActive: false)) return 2;
            if (TileExtensions.HasSteppableUnit(target, state))                      return 2;
            return 0;                       // 0x5a1 = EffectType.SquigMine_Tile
                                            // 2     = TargetingRule.TargetMatchesDynamicRule

        SEMANTIQUE : une mine ne se pose ni sur une tuile qui en porte DEJA une, ni sur une tuile
        occupee par une unite `Steppable`. C'est le SEUL terme du gate qui morde sur ce cast : le
        reste du masque (`TargetIsTile`, `TargetTileIsFree`) releve du domaine TILE, non porte.

        `EntityExtensions$$HasEffect(entity, state, type, onlyActive)` =
        `IsOwnerOfEffect(...) || IsTargetOfEffect(...)`, et `onlyActive` est passe a `false` par ce
        call-site -> `has_effect_of_type`, dont la docstring etablit la meme non-consultation
        d'`EffectComponent.IsActive` et la coincidence owned/targeted sur l'`EffectsState` du port.

        `has_steppable_unit` resout la tuile en son OCCUPANT (`GetUnit`), ce qui est exactement ce
        que fait `TileExtensions$$HasSteppableUnit` -- son argument natif y transite deja."""
        if target_id is None:
            return 0
        if has_effect_of_type(state, int(target_id), int(EffectType.SquigMine_Tile)):
            return int(TR.TargetMatchesDynamicRule)
        if has_steppable_unit(state, int(target_id)):
            return int(TR.TargetMatchesDynamicRule)
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
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
DDD_CONST_NR_OF_HITS = AbilityConstantType.nrOfHits      # GetNumberConstant(0x2f)  -> "nrOfHits"     = 6
DDD_CONST_EXTRA_HITS = AbilityConstantType.extraHits      # GetNumberConstant(100)   -> "extraHits"    = 2
DDD_CONST_MAX_HITS = AbilityConstantType.maxNrOfHits        # ConfigConst(0x48)        -> "maxNrOfHits"  = 16
DDD_CONST_RANGE_2 = AbilityConstantType.range_2         # GetNumberConstant(0x44)  -> "range_2"      = 3
DDD_CONST_HEALTH_PCT = AbilityConstantType.healthPct      # ConfigConst(0x4f)        -> "healthPct"    = 15
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
        n_hits = int(ability_var(DDD_ID, "nrOfHits", is_constant=True) or 1)
        extra_hits = int(ability_var(DDD_ID, "extraHits", is_constant=True) or 0)
        max_hits = int(ability_var(DDD_ID, "maxNrOfHits", is_constant=True) or n_hits)
        range_2 = int(ability_var(DDD_ID, "range_2", is_constant=True) or 1)
        return n_hits, extra_hits, max_hits, range_2

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None

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


# ================================================================================================ #
# 1057 GrotTank (`orksBigMek`, #570) -- SUMMON tile-target. UN SEUL `AActiveAbility.Execute`, mais CINQ
# mecaniques composees dans les options de spawn :
#   (1) `Spawn(Caster@0x48, Target@0x60, GetStringConstant(unitId), opts)` = la pose sur la tuile
#       ADJACENTE LIBRE ciblee ;
#   (2) `opts = SpawnUnitOptions.WithStatsFromConfig(config, abilityState, <abilitiesLevel>, null)`
#       = les stats du summon lues du gameconfig (`summonHp` / `summonDmg` / `summonArmor`) ;
#   (3) `abilitiesLevel = DSLFormulas.AbilityLevelAmount(Owner@0x30, <ce type d'ability>)`
#       = le niveau sous lequel l'unite posee monte SES abilities ;
#   (4) `opts.<+0x28> = [ StatModifierFormula(Health, Initial, TankHealth(), null) ]`
#       = OVERRIDE des PV par une FORMULE, par-dessus le `summonHp` du (2) ;
#   (5) `opts.<+0x18> = DSLBehaviors.PerformAIAttackFromCurrentPosition(ActiveTarget@0x68, ...)`
#       = le sous-behaviour ON-APPEARANCE : le tank tire des qu'il apparait, SANS bouger.
# Le tooltip i2 s'apparie noeud par noeud : « Calls in a Grot Tank in an adjacent free hex » = (1) +
# le masque `TargetIsTile|TargetTileIsFree` ; « cannot move in its first turn, but can immediately
# attack an enemy in range » = (5) puis le `FinishUnitTurn(spawned, isTerminated: true)` de
# `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` (#291, deja porte) ; « 84 Health +12 for each
# round that has started 30 Damage 24 Armour » = (4) + (2) au niveau 2.
# ================================================================================================ #

GROT_TANK_ID = "GrotTank"
GROT_TANK_CONST_UNIT_ID = AbilityConstantType.unitId          # GetStringConstant(0) -> "orksGrotTank"


def grot_tank_health_formula(level: Optional[int], mult: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GrotTankAbility$$TankHealth(abilityState)` --
    MIRROR du decompile, dans l'ORDRE DE CONSTRUCTION natif :

        extraHp   = config.GetVariableForLevel(AbilityVariableType.extraHp,  abilityState)   // 0x1e
        rounds    = DSLFormulas.RoundsStarted(Caster@0x48)
        perRound  = DSLFormulas.Multiply(rounds, DSLFormulas.Direct(extraHp))
        summonHp  = config.GetVariableForLevel(AbilityVariableType.summonHp, abilityState)   // 0x29
        return      DSLFormulas.Sum(DSLFormulas.Direct(summonHp), perRound)

    Les DEUX variables sont lues au moment de la CONSTRUCTION de l'arbre (le natif appelle
    `GetVariableForLevel` avant d'emballer le resultat dans un `Direct`), sous l'`AbilityState` du
    CASTER -> ici `ability_var(GrotTank, <cle>, level, multiplier_pct=mult)`. Seul le terme
    `RoundsStarted` est evalue au moment du spawn.

    `RoundsStarted(<sel>)` = **SOMME** de `TurnsStarted` sur les unites du selecteur
    (`IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate`), sans plancher ; le selecteur
    natif est `DSLSelectors+0x48` = **Caster**, donc la somme porte sur UNE unite = le compteur de
    tours du Big Mek. Au tour ou il caste, ce compteur vaut deja >= 1 (il est incremente au
    StartTurn), ce qui est exactement ce que dit le tooltip (« +12 for each round that has
    started »).

    ⚠ La grandeur est bien le compteur du CASTER, pas un compteur global de manche : le natif ne
    passe pas `AllAliveUnits` -- c'est le meme slot `+0x48` que celui du `Spawn` juste apres."""
    summon_hp = int(ability_var(GROT_TANK_ID, AbilityVariableType.summonHp.name,
                                level, multiplier_pct=mult) or 0)
    extra_hp = int(ability_var(GROT_TANK_ID, AbilityVariableType.extraHp.name,
                               level, multiplier_pct=mult) or 0)
    return Sum(Get(summon_hp), Multiply(RoundsStarted(Caster()), Get(extra_hp)))


def grot_tank_tree(level: Optional[int], mult: int) -> Spawn:
    """L'UNIQUE noeud top-level de `...GrotTankAbility$$ExecuteBehaviour` :

        `AActiveAbility.Execute( DSLBehaviors.Spawn(Caster@0x48, Target@0x60, unitId, opts) )`

    ou `opts` porte le `StatModifierFormula` (Health/Initial/TankHealth) en `+0x28` et le
    sous-behaviour on-appearance `PerformAIAttackFromCurrentPosition(ActiveTarget@0x68)` en `+0x18`.

    Pas de `Group`, pas d'`ExecuteAtomic` : le natif n'en construit AUCUN ici (contraste GetEmRuntz,
    qui enchaine `ExecuteAtomic(Spawn)` puis `Execute(PerformAIAttack + Foreach)`, et ItItches, qui
    enveloppe son spawn dans un `Group(Ability_Summon)`). On ne rajoute pas d'enveloppe que le
    decompile ne porte pas.

    Le tile-selecteur est `Target@0x60` BRUT -- aucun `CanAddUnit`, aucun `AdjacentTiles` : la
    contrainte « hex adjacent LIBRE » est portee INTEGRALEMENT par le masque de ciblage
    (`TargetIsTile | TargetTileIsFree`, `range = TargetingRange statics+0x30` = adjacent), donc
    elle emerge du gate, pas de l'arbre. La feuille `Spawn` normalise l'element du selecteur par
    `GetMainTile(...).Id`, comme `SpawnUnitBehaviour$$Execute`.

    `PerformAIAttack(ActiveTarget())` = les DEUX defauts de `...FromCurrentPosition` (`+0x70 = 0`
    allowMoveAction, `+0x78 = Direct(0)` moveAmount) : le tank tire depuis SA tuile, il n'approche
    pas. Le 5e argument natif (`false`) est ce meme `allowMoveAction`."""
    return Spawn(Target(), GROT_TANK_ID,
                 on_appearance=PerformAIAttack(ActiveTarget()),      # `SpawnUnitOptions+0x18`
                 stat_modifier_formulas=[                            # `SpawnUnitOptions+0x28`
                     StatModifierFormula(int(StatType.HEALTH), int(StatPart.INITIAL),
                                         grot_tank_health_formula(level, mult), None)])


class GrotTankAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GrotTankAbility$$ExecuteBehaviour` (id 1057,
    `orksBigMek` -- Orks). Cast TILE-TARGET : invoque `orksGrotTank` sur une tuile adjacente LIBRE,
    avec des PV qui CROISSENT avec le nombre de tours deja commences par le caster, et une attaque
    immediate depuis la tuile de spawn.

    Cinq mecaniques, un seul `Execute` -- cf. le bandeau du module juste au-dessus.

    CE QUE LE SUMMON APPORTE (recon gameconfig `orksGrotTank`, kind `summons`) : Movement 2, deux
    armes (`Physical` 1 coup en melee ; `Blast` 3 coups, Range 3), traits `Summon` / `Mechanical` /
    `BattleFatigue` / `Vehicle`, et UNE passive `Ramshackle` (`TriggeredAbilityType.Ramshackle` =
    1093, effet `EffectType.Ramshackle_DmgReduction` = 1090). Cette passive N'EST PAS PORTEE (aucun
    mirror de `IdunBattle.Entities.Effects.Loki.Ramshackle_DmgReductionEffect$$CreateDamageModifier`
    dans `entities/effects/`) : le Grot Tank porte donc, offline, la reduction de degat en MOINS.
    C'est un ecart NOMME, dans le sens PERMISSIF pour l'adversaire (le tank encaisse plus qu'il ne
    devrait), pas un oubli.

    `abilitiesLevel` (`SpawnUnitOptions+0x30`) : le natif y passe
    `AbilityLevelAmount(Owner@0x30, <ce type>)`, c'est-a-dire le niveau de CETTE ability sur son
    porteur -- la MEME grandeur que le `abilityState.level` que la feuille `Spawn` lit deja dans
    l'`active_ability_level` du caster. On ne pose donc PAS `ability_state` : ce serait la meme
    valeur ecrite deux fois, et le champ du port sert a exprimer un `AbilityState` ETRANGER (la
    mine Haywire posee par un PASSIF).

    Flags de tour : defauts base -> termine le tour + ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GrotTank)   # 1057
    ABILITY_ID = GROT_TANK_ID

    # GATE DE CIBLE. `IdunBattleLogic.Entities.Abilities.Active.Loki.GrotTankAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x30>, 1, 0x1040, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)
    # Overload « FLAGS DIRECTS » a 7 arguments (5e argument -> `options+0x28`) : le litteral EST le
    # masque effectif -- ce n'est ni l'overload PRESET+flags, ni une recopie de champ statique.
    # Decomposition EXHAUSTIVE de 0x1040 (0x40 + 0x1000, aucun bit residuel) :
    #     0x40    (bit 6)  TargetIsTile     -> la cible EST une entite-tuile
    #     0x1000  (bit 12) TargetTileIsFree -> cette tuile doit etre LIBRE
    # PORTEE : `TargetingRange` statique `+0x30` = adjacent (`RANGE_ADJACENT`), et
    # `forceMeleeTarget = 1` = `RangedBool.False` (l'enum natif est INVERSE).
    # Valeurs MIGREES depuis `targeting.py::TARGETING_OPTIONS_UNPORTED` (contrat de disjonction :
    # une ability a UNE source de masque) et RE-LUES au decompile a l'occasion -- bit-identiques.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetIsTile | TR.TargetTileIsFree, self_cast=False,
        range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE (`TargetingQuery$$GetActualTarget`, slot 16) : sous
        # `TargetIsTile` le role `target` natif est TOUJOURS l'entite-TUILE. IDEMPOTENT.
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        if tile_id is None:
            return {"ability": GROT_TANK_ID, "caster": caster_id, "target": target_id,
                    "tile": None, "spawned": [], "attacks": [], "dsl": True}
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        level = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
        mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100) if sc is not None else 100
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, tile_id)
        grot_tank_tree(level, mult).execute(entities, ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [a for n, p in ectx.emitted if n == "PerformAIAttack"
                   for a in (p.get("attacks") or [])]
        summon_vid = ((GC.ability(GROT_TANK_ID) or {}).get("constants") or {}).get("unitId")
        # PV effectifs du (des) tank(s) pose(s) -- l'observable de l'etage `StatModifierFormula`.
        tank_hp = []
        for gid in spawned:
            ge = state.get_entity(int(gid))
            hc = ge.get_component(HealthComponent) if ge is not None else None
            tank_hp.append(None if hc is None else hc.hp_max)
        return {"ability": GROT_TANK_ID, "caster": caster_id, "target": target_id, "tile": tile_id,
                "summon": summon_vid, "spawned": spawned, "tank_hp": tank_hp,
                "attacks": attacks, "dsl": True}


# =================================================================================================== #
# ExplosivePresents (1170, `orksRedGobbo` -- Da Red Gobbo, npc) -- #997.
#
# L'audit de couverture l'annoncait `DAMAGE(Blast)` en derivant la categorie du `damageProfile` de
# l'ARME du porteur (residu #491-r2). Ici la categorie annoncee est **CONFIRMEE** par le decompile :
# le cast frappe pour de vrai (contraste les quatre autres de la meme tranche, qui posent des effets
# `*_Pending*` et dont le degat appartient a une TRIGGERED -- cf.
# `docs/rl/case-997-six-noop-la-categorie-annoncee-ment-4-fois-sur-6.md`).
# =================================================================================================== #

EXPLOSIVE_PRESENTS_ID = "ExplosivePresents"
EP_CONST_UNIT_ID = AbilityConstantType.unitId       # GetStringConstant(0) -> "unitId" = orksGrot


def explosive_presents_tree() -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ExplosivePresentsAbility$$ExecuteBehaviour`
    (id 1170, `orksRedGobbo`) -- MIRROR du DECOMPILE :

        targets = op_Subtraction( op_Addition( target@0x60,
                                               AdjacentUnits(target@0x60, unique:1, 3) ),
                                  caster@0x48 )
        ExecuteAtomic(
            AttackWithAbilityDamage(caster@0x48, targets, MinMaxDamage(abilityState),
                                    GetDamageProfile(), GetHits(), this, 2)
          , 0x2a )

    UN SEUL volet d'attaque (contraste tout le patron splash main+secondaire de `loki/splash.py`) :
    le natif passe un selecteur MULTI directement a UN `AttackWithAbilityDamage`, donc la CIBLE et
    ses adjacents partagent la MEME plage (`minDmg`/`maxDmg`) et le MEME nombre de coups
    (`nrOfHits`) -- il n'y a ni `minDmg_2` ni `nrOfHits_2` dans la config 1170.
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` resout la liste, l'`OrderBy` par id,
    puis attaque chaque cible -> porte via `multi=True`.

    FRIENDLY-FIRE, et c'est le decompile qui le dit : le selecteur est `AdjacentUnits` BRUT, SANS
    wrapper `Enemies(...)` -- meme forme que `StikkbombAbility$$ExecuteBehaviour` (#213). Les ALLIES
    du caster adjacents a la cible sont donc touches. Le SEUL retrait est le CASTER lui-meme, par un
    `op_Subtraction(., caster@0x48)` explicite.

    `selectionType = 3` (`OnlyAliveAndTargetable`) est LU au 4e argument du `DSLSelectors$$AdjacentUnits`
    natif -- la surcharge unique `(this, origin, unique, selectionType)`. Sans wrapper de camp c'est
    le SEUL filtre de l'ensemble, d'ou son poids ici.

    FACTORY NATIVE = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (le symbole est
    resolu tel quel dans le corps decompile) -> `native_factory="ability"` = `AbilityDamageOperation`
    = **1 tirage/coup**, PAS les 2 tirages/coup de `DSLFactory$$AttackWithAttackDamage` (piege
    rngcrit-1202). RANGED : la config 1170 n'a AUCUN `attackRangeType`, donc `AttackRangeType.None`
    (0) != `Melee` -> `is_melee=False` (convention du port, cf. `fury_of_the_ancients`).

    `ExecuteAtomic(., 0x2a)` -> `AtomicGroup` (inline #201 ; `0x2a` = id du groupe atomique, aucun
    `EvaluateAbilities` implicite, cf. #209)."""
    # `op_Addition(target, AdjacentUnits(target))` puis `op_Subtraction(., caster)`. Le premier
    # operande est la CIBLE dans le domaine UNITE (`Target()`) ; le centre geometrique du second est
    # sa tuile (`TargetTile()`, convention Stikkbomb/PlasmaGrenade : le natif passe un selecteur
    # d'unite et `AdjacentTiles` en resout les pieds).
    targets = Sub(Union(Target(), AdjacentUnits(TargetTile(), selection_type=SELECTION)),
                  Caster())
    return AtomicGroup(AttackWithAttackDamage(targets, EXPLOSIVE_PRESENTS_ID, "Blast",
                                              is_melee=False, multi=True,
                                              native_factory="ability"))


class ExplosivePresentsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExplosivePresentsAbility$$ExecuteBehaviour`
    (id 1170, `orksRedGobbo` -- Da Red Gobbo, npc ; faction Orks).

    UN volet d'attaque AoE : la cible ET ses unites adjacentes (friendly-fire, cf.
    `explosive_presents_tree`), moins le caster. Plage et coups PARTAGES par toutes les cibles.

    CONFRONTABILITE : porteur `orksRedGobbo`, npc -- montable par `--explicit-stats` (toute entree
    `units.npc` porte une table `stats[]`). « npc-only » n'implique pas « non confrontable »."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ExplosivePresents)   # 1170
    ABILITY_ID = EXPLOSIVE_PRESENTS_ID

    # GATE DE CIBLE (#115) -- forme (A) FLAGS DIRECTS, la seule ou la lecture naive du litteral est
    # juste. `IdunBattleLogic.Entities.Abilities.Active.Loki.ExplosivePresentsAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x18>, 2, 0x200000000002, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0)
    # UN SEUL appel de ctor, aucune copie de preset statique, aucune surcharge PRESET+FLAGS
    # derriere -- le 5e argument EST le masque.
    # Decomposition EXHAUSTIVE de 0x200000000002 (aucun bit residuel) :
    #     0x2               (bit 1)  TargetMatchesDynamicRule -> consulte
    #                                `get_dynamic_invalid_target_reason` ci-dessous (PORTEE)
    #     0x200000000000    (bit 45) TargetIsUnit             -> la cible est une UNITE
    # ⚠ AUCUN `TargetIsEnemy` : le masque n'exclut PAS les allies. C'est la REGLE DYNAMIQUE qui les
    # refuse, et elle a une exception (l'unite de quete) -- rabattre le gate sur `TargetIsEnemy`
    # serait plus restrictif que le natif.
    # PORTEE : `TargetingRange` statique `+0x18` = `useRangeFromConfig` -> `constants.range` = 2 ;
    # `forceMeleeTarget = 2` = `RangedBool.IfRangedCaster` (l'enum natif est INVERSE).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsUnit, self_cast=False,
        range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int, target_id) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExplosivePresentsAbility$$GetDynamicInvalidTargetReason`
        -- la regle-delegue posee a `options+0x38`, consultee parce que le masque porte
        `TargetMatchesDynamicRule`. Corps natif, LU (5 parametres `caster, casterTiles, target,
        targetTiles`) :

            questUnitId = <gameconfig>.GetUnit( GetStringConstant(config, 0 = unitId) ).Id
            if (target != null && UnitExtensions.GetQuestUnitId(target) == questUnitId) return 0
            return UnitExtensions.IsFriend(target, caster, state) ? 2 : 0

        Autrement dit : **l'unite designee par `constants.unitId` reste TOUJOURS une cible valide,
        meme amie** (config 1170 : `orksGrot` -- Da Red Gobbo offre ses cadeaux a ses propres
        Grots), et **hors elle les amis sont refuses** (raison 2). C'est ce qui explique l'absence
        de `TargetIsEnemy` dans le masque : le filtrage de camp vit ICI, avec son exception.

        `GetQuestUnitId(unit)` = `BaseUnitComponent+0x18` s'il est non vide, SINON
        `UnitExtensions$$GetVisualUnitId(unit)`. Le port n'a pas de champ `questUnitId` distinct :
        il lit `UnitComponent.visual_id`, c'est-a-dire la BRANCHE DE REPLI du natif -- exacte pour
        toute unite dont le `questUnitId` est vide, ce qui est le cas de tout ce qui entre dans un
        runner (aucun montage n'ecrit ce champ). ECART NOMME, pas un oubli.

        `IsFriend(target, caster, state)` compare `GetCurrentPlayer` des deux ; offline l'equivalent
        est `units_are_friendly` (meme `OwnerComponent.team`, la convention d'equipe du port).
        Un caster ou une cible introuvable -> `IsFriend` faux -> 0 (permissif, == le natif dont les
        deux `GetCurrentPlayer` se rabattent alors sur 0... et deviennent EGAUX ; le port refuse ici
        de fabriquer un refus sur une entite absente)."""
        quest_unit_id = ((GC.ability(EXPLOSIVE_PRESENTS_ID) or {}).get("constants")
                         or {}).get(EP_CONST_UNIT_ID.name)
        te = state.get_entity(int(target_id)) if target_id is not None else None
        uc = te.get_component(UnitComponent) if te is not None else None
        if uc is not None and quest_unit_id and uc.visual_id == quest_unit_id:
            return 0                                  # l'unite de quete est TOUJOURS ciblable
        return 2 if units_are_friendly(state, target_id, caster_id) else 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        explosive_presents_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]
        return {"ability": EXPLOSIVE_PRESENTS_ID, "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}
