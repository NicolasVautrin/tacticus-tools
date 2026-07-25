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

from .base import ActiveAbility
from ..components import PositionComponent, StatsComponent, OwnerComponent, UnitComponent
from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import If, op_add, op_and
from ...entities.effect_type import EffectType
from ...entities.formulas import Get, VisualUnitIdFromUnitId
from ...entities.pathfinding.walk_pathfinder import get_movable_positions
from ...entities.selectors import (ActiveTarget, AdjacentFriends, AdjacentTiles, AllUnits, CanAddUnit,
                                   Caster, CasterTile, FixedTiles, Friends, Target, Union, Unique,
                                   UnitsFromFaction, UnitsWithVisualId)
from ...entities.stats import StatType
from ...entities.triggers import IsAdjacent
from .behaviours import (AddEffect, KillDeadUnits, MoveUnit, PerformAIAction, Spawn, UseActiveAbility,
                         entities_from_state)

if TYPE_CHECKING:
    from ..state import State

# Index des constantes lues par `WaaaghAbility.ExecuteBehaviour @18122b010` et ses helpers
# (`AbilityConfiguration.Get*Constant(config, <index>)`) -> cle gameconfig correspondante.
CONST_UNIT_ID = 0x00            # GetStringConstant(0)     -> "unitId"        = orksOrkBoys
CONST_EXTRA_MOVEMENT = 0x0e     # GetNumberConstant(0xe)   -> "extraMovement" = 1
CONST_NR_OF_SUMMONS = 0x10      # GetNumberConstant(0x10)  -> "nrOfSummons"   = 2

WAAAGH_FACTION = "Orks"         # `UnitsFromFaction(..., 5, 3)` — UnitFaction.Orks = 5 (il2cpp_enums)


# ------------------------------------------------------------------------------------------------ #
# Les 5 arbres top-level de `WaaaghAbility.ExecuteBehaviour @18122b010`, dans l'ORDRE D'EXECUTION
# natif (5 appels `AActiveAbility.Execute` successifs, chacun enveloppe dans un `Group(<b>, caster@0x160,
# <groupId>)` = ordonnancement de VUE, no-op observable ici) :
#     Group(spawnB,  0x22) · Group(buffB, 0x25) · Group(moveB, 0x23) · Group(atkB, 0x20) · Group(aiB, 0x28)
# ------------------------------------------------------------------------------------------------ #

def waaagh_spawn_tree(count: int) -> Spawn:
    """1er noeud natif @18122b010 (corps INLINE, identique a `WaaaghAbility.GetSummonBehaviour @18122c120`) :
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
    """`WaaaghAbility.GetBuffedUnitsSelector @18122bb30` (== le selecteur INLINE de `GetBuffBehaviour
    @18122b900`) :
        `Unique( caster@0x160
                 + AdjacentFriends(caster@0x160, 1, 3)
                 + UnitsFromFaction(Friends(caster@0x160, @0x80, 3), 5=Orks, 3) )`
    (`TargetsSelector.op_Addition` = union, puis `Unique` = dedup par entite). `@0x80` = le slot PARTAGE
    « toutes les unites (vivantes) » pose par `InitializeShared @180df2670` -> porte `AllUnits()`.
    Portee : le caster, ses allies ADJACENTS (quelle que soit leur faction) et TOUS ses allies de faction
    **Orks** (board-wide, aucun rayon).

    `AdjacentFriends` porte prend un CENTRE-POSITION (convention des selecteurs d'anneau du port) ->
    `CasterTile()` designe la MEME ancre que le `caster@0x160` natif (self exclu par `_within`, puis
    reinjecte par l'union `Caster()` — exactement l'`op_Addition(caster, adjacentFriends)` natif)."""
    return Unique(Union(Union(Caster(), AdjacentFriends(CasterTile(), Const(1))),
                        UnitsFromFaction(Friends(AllUnits()), WAAAGH_FACTION)))


def waaagh_buff_tree():
    """2e noeud natif @18122b010 = `WaaaghAbility.GetBuffBehaviour @18122b900` :
        `op_BitwiseAnd( op_BitwiseAnd(
              AddStaticStatModifierEffect(sel, 1099=Waaagh_ExtraMovement, stat=MOVEMENT(1),
                                          Direct(GetNumberConstant(0xe)=extraMovement), duree@dsl+0xc0=1),
              AddEffect(0x44c=1100 Waaagh_ExtraDamage, AbilityStateReference, caster@0x160, sel, duree@0xc0) ),
              AddEffect(0x44d=1101 Waaagh_ExtraHits,   AbilityStateReference, caster@0x160, sel, duree@0xc0) )`

    Les TROIS effets partagent le MEME selecteur (`waaagh_buffed_units_selector`) et la MEME duree
    (`dsl+0xc0` = `Direct(1)` pose par `DSLFactory..ctor @180e020b0` -> 1 round).

    `AddStaticStatModifierEffect` (@180de7b20) n'a PAS de feuille dediee dans le port : le mapping etabli
    du projet (valide live sur `BlackRage_ExtraMove` 1342) est `AddEffect(<type>)` + une classe d'effet
    portant `applied_stat_mods` (canal EAGER `AddEffectOperation._apply_stat_mods`) -> ici
    `WaaaghExtraMovementEffect` (+MOVEMENT = extraMovement). Les contributions de 1100 (+extraDmg[level])
    et 1101 (+extraHit) restent des RESIDUS documentes (marqueurs poses, canaux modifier non branches)."""
    # #98 : la duree des TROIS effets est `dsl+0xc0` = un noeud `Direct(1)` (alloue par
    # `DSLFactory..ctor @180e020b0`), PAS un `TurnsFromRounds(1)` -> elle arrive telle quelle dans le
    # `param_6` d'`AddEffectOperation.Execute @180e48940`, qui ne la convertit PAS : 1 TOUR, pas 1 round.
    # -> `duration_turns=1` (comportement INCHANGE ; c'est exactement le call-site qu'une conversion
    # aveugle aurait double).
    sel = waaagh_buffed_units_selector()
    return op_and(op_and(AddEffect(int(EffectType.Waaagh_ExtraMovement), "Waaagh_ExtraMovement", sel,
                                   duration_turns=1),
                         AddEffect(int(EffectType.Waaagh_ExtraDamage), "Waaagh_ExtraDamage", sel,
                                   duration_turns=1)),
                  AddEffect(int(EffectType.Waaagh_ExtraHits), "Waaagh_ExtraHits", sel,
                            duration_turns=1))


def waaagh_move_range(state: "State", caster_id: int, extra_movement: int) -> int:
    """`DSLFactory.UnitMovementRangeWithBonus(caster@0x160, 1099, Direct(extraMovement)) @180dff050`
    (lu par `WaaaghAbility.GetPossibleMovementTiles @18122c060`) = MIRROR 1:1 :
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


def _living_occupants_map(state: "State") -> dict:
    """`{tile_id -> team}` des unites VIVANTES (occupation lue par le pathfinder `MovableTilesInRange`)."""
    board = state.board
    if board is None:
        return {}
    occ: dict = {}
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if pc is None or oc is None or (uc is not None and not uc.alive):
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ[t] = oc.team
    return occ


def waaagh_charge_tile(state: "State", caster_id: int, target_id: int, move_range: int):
    """COLLAPSE du selecteur de destination LOURD (kind S) de l'etage MOVE @18122b010 :
        `First( SortTilesByUtility( WaaaghAbility.GetPossibleMovementTiles(target@0x178),
                                    caster@0x160, 0x20 ), 1 )`
    ou `GetPossibleMovementTiles @18122c060` =
        `TilesUnitCanMoveToChargeTarget(caster@0x160, casterTile@0x168, target,
                                        UnitMovementRangeWithBonus(caster, 1099, Direct(extraMovement)),
                                        canReachOnly=0) @180dfda00`
        = `CanAddUnit(AdjacentTiles(target)) op_And MovableTilesInRange(caster, tile, range, reachOnly=0)`.

    `canReachOnly=0` (CONTRASTE avec VigilanceEternal/HeroicFusillade qui passent 1) -> l'ensemble
    « movable » est le `visited` du BFS (toutes les tuiles ATTEINTES en <= range pas) et non le `stop_set`
    ; la difference (tuiles traversables mais occupees) est de toute facon eliminee par le
    `CanAddUnit(AdjacentTiles(target))` en amont. `SortTilesByUtility(0x20)` (selecteur AI lourd) COLLAPSE
    en : la tuile la plus PROCHE du caster (tie-break tile id) -- MEME proxy que les autres gap-closers
    portes (HeroicFusillade/VigilanceEternal/SkyStrike). Renvoie une (col,row) ou None."""
    board = state.board
    ce, te = state.get_entity(caster_id), state.get_entity(target_id)
    cpc = ce.get_component(PositionComponent) if ce is not None else None
    tpc = te.get_component(PositionComponent) if te is not None else None
    if board is None or cpc is None or tpc is None:
        return None
    ctile = board.id_at(cpc.col, cpc.row)
    if ctile is None:
        return None
    coc = ce.get_component(OwnerComponent)
    visited, _stop = get_movable_positions(board, ctile, int(move_range),
                                           _living_occupants_map(state),
                                           coc.team if coc is not None else None)
    occ = set(_living_occupants_map(state))
    # CanAddUnit(AdjacentTiles(target)) : tuiles hex-adjacentes a la cible, LIBRES et marchables.
    adj_free = [t for t in board.neighbours(board.id_at(tpc.col, tpc.row))
                if t not in occ and board.walkable(t)]
    cands = [t for t in adj_free if t in visited]        # op_And MovableTilesInRange (canReachOnly=0)
    if not cands:
        return None
    cpos = (cpc.col, cpc.row)
    cands.sort(key=lambda t: (hexgeo.distance(cpos, board.coord(t)), t))   # SortTilesByUtility collapse
    return board.coord(cands[0])


def waaagh_move_tree(dest):
    """3e noeud natif @18122b010 : `MoveUnit(caster@0x160, <destination>, <options NULLES>)` — le
    decompile met a zero les 5 selecteurs d'options (`local_1a8..uStack_178 = 0`, seul `local_198` =
    `factory+0xf8` est lu) -> aucun flag after-move (meme configuration que HeroicFusillade, cf.
    `behaviours/movement.py`). Destination = `waaagh_charge_tile` (collapse S)."""
    return MoveUnit(Caster(), FixedTiles([dest] if dest is not None else []))


def waaagh_attack_tree():
    """4e noeud natif @18122b010 = `WaaaghAbility.GetAttackBehaviour @18122b700` :
        `op_BitwiseAnd(
            If( IsAdjacent(caster@0x160, target@0x178, 3),
                UseActiveAbility(caster@0x160, target@0x178,
                                 UnitNormalAttackType(caster@0x160), <options>) ),
            KillDeadUnits( Killer(activeTarget@0x180), AllUnits() ) )`

    - GATE `IsAdjacent(caster, target, 3)` : le `3` (champ +0x18) ne va PAS au predicat par-paire (slot
      iface 0x5f = `AreNeighbours`) -- MEME lecture que VigilanceEternal @18122a580 (cf. genestealer.py)
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


def waaagh_ai_tree(unit_id: str) -> PerformAIAction:
    """5e noeud natif @18122b010 (corps INLINE, IDENTIQUE a `WaaaghAbility.GetTriggerSummonsBehaviour
    @18122c260`, site @18122c310) :
        `PerformAIAction( Friends(caster@0x160,
                                  UnitsWithVisualId(VisualUnitIdFromUnitId(Get(GetStringConstant(0))), 1),
                                  3),
                          asGroup=1, resetTurnFlags=1 )`
    MEMES booleans que `SupremeCommanderAbility @18120df30` -> le socle `PerformAIAction` /
    `ComputerActionOperation.execute_group` s'applique tel quel (reset des flags de tour de TOUTES les
    cibles d'abord, `AiControl.ExecuteFor(group)` @180ffbeb0 ensuite, restauration enfin).

    ⚠ SELECTEUR **BOARD-WIDE** (`UnitsWithVisualId` est ancre sur le slot partage `@0x80` = toutes les
    unites, AUCUN rayon) -- a ne pas confondre avec le `UnitsWithIds(SurroundingFriends(caster, range))`
    de SupremeCommander. Consequence mecanique : le Waaagh fait rejouer **TOUS** les Ork Boyz allies du
    plateau (y compris ceux d'un cast precedent), pas seulement ceux qui viennent d'etre invoques."""
    return PerformAIAction(Friends(UnitsWithVisualId(VisualUnitIdFromUnitId(Get(unit_id)), 1)),
                           as_group=True, reset_turn_flags=True)


class WaaaghAbility(ActiveAbility):
    """`WaaaghAbility.ExecuteBehaviour @18122b010` (id 1058, `orksWarboss` « Snotflogga », Orks) —
    MIRROR du DECOMPILE.

    Corps natif (ordre de lecture ; 5 executions top-level SUCCESSIVES, chacune un
    `AActiveAbility.Execute(Group(<b>, caster@0x160, <groupId>), entities)`) :
        opts   = SpawnUnitOptions.WithStatsFromConfig(config, level)
        spawnB = Spawn(caster, PickRandomly(CanAddUnit(AdjacentTiles(casterTile)), GetNumberConstant(0x10)),
                       GetStringConstant(0), opts)                                   # @18122b0dd..
        buffB  = GetBuffBehaviour(level)                                             # @18122b900
        moveB  = MoveUnit(caster, First(SortTilesByUtility(GetPossibleMovementTiles(target),
                                                           caster, 0x20), 1), <options nulles>)
        atkB   = GetAttackBehaviour(level)                                           # @18122b700
        aiB    = PerformAIAction(Friends(caster, UnitsWithVisualId(VisualUnitIdFromUnitId(
                                 Get(GetStringConstant(0))), 1), 3), 1, 1)           # @18122b306+
        Execute(Group(spawnB, caster, 0x22)) ; Execute(Group(buffB, caster, 0x25)) ;
        Execute(Group(moveB,  caster, 0x23)) ; Execute(Group(atkB,  caster, 0x20)) ;
        Execute(Group(aiB,    caster, 0x28))

    Waaagh **n'utilise PAS** `GetAbilityStatModification` (xrefs exhaustives : ses 2 seuls sites sont dans
    SupremeCommander @18120df30) : `nrOfSummons` et `extraMovement` sont lus BRUTS de la config.

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
