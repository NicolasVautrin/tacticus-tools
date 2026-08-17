"""Abilities Genestealer Cults (Isaak `genesPrimus` / Judh `genesKelermorph`) — chantier gen-stealer.

Module DÉDIÉ : `behaviours.py` et `loki.py` (abilities) sont déjà > 1000 lignes (seuil de split), et le
chantier gen-stealer regroupe plusieurs slices partageant les feuilles de decoy (G4 CultDemagogue ici ; G6
HypersensoryAbilities réutilisera `SpawnDecoys`). Org native = 1 classe par ability (`Abilities.Active.*`) ;
les arbres SPÉCIFIQUES vivent avec leur ability. RE ghidra gqfc5mff6c (VA citées). Doc : docs/rl/genestealer-cults.md.

Arbre CultDemagogue (`CultDemagogueAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour`, mirror op_Addition 3 étages) :
    op_add( op_add( SpawnDecoys , SpawnNeophytesOnDecoys ) , PerformAIAction(UnitsWithId(...), 0, 1) )
Sélecteurs de TUILE lourds (S) COLLAPSÉS (doctrine slice-18/19/22/23/24) : résolus impérativement dans
chaque feuille au moment de l'exécution (data-dep : les neophytes lisent les decoys fraîchement posés).
Le 3e étage a été RETROFITÉ (#94) sur le socle `PerformAIAction` (`behaviours/ai_control.py` +
`operations/summon_ai.py::ComputerActionOperation`) : la feuille bespoke `PerformAINeophyteTurn`
fusionnait sélecteur + action et n'implémentait PAS le cycle de flags de tour (`resetTurnFlags=1`).
"""
from __future__ import annotations

import math
from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ...dsl.base import resolve_unit, Const
from ...dsl.effects import AbilityBehaviour, OperationResult, ExecutionContext
from ...entities.behaviours import op_add, op_and, If
from ...entities.selectors.accessors import FixedTiles, Owner, Target, TargetTile
from ...entities.selectors.geometry import UnitsWithId
from ...entities.selectors.tiles import Caster
from ...entities.selectors.units import Alive, SurroundingEnemies, Union
from ...entities.triggers import (Not, IsAlive, IsSurrounding, IsAdjacent, TriggerAnd,
                                  HasEffect, HasFaction, OwnerIsTarget)
from ...entities.traits.unit_trait import UnitTrait, has_trait
from ...entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3
from ...entities.ability_variable_type import AbilityVariableType   # #931
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.unit_faction import UnitFaction
from ...entities.stats import StatType
from ...entities.effects.magnitude import ability_var
from ...services.movement_query import get_movable_tiles_for, get_min_distance
from ... import battle_query                       # `BattleQuery$$GetSurroundingTiles` (#287-r11-r1)
from ...utilities.tile import first_tile_by_utility
from ...utilities.utility_type import UtilityType
from ..components import (OwnerComponent, PositionComponent, UnitComponent, StatsComponent,
                          get_unit_feet)   # `EntityExtensions$$GetTiles` (#287-r11-r1)
from ..components import has_effect_of_type                          # #931
from ..operations.spawn import spawn_decoy, _spawn_config_grot
from ...predict import heal_amount_weapon                            # #931 (`HealAbility$$HealAmount`)
from .base import ActiveAbility
from .attack_query import entity_can_be_healed, is_affected_by_heal_type   # #931
from .targeting import (RANGE_ADJACENT_IF_MELEE_CASTER, RANGE_FROM_CONFIG, RANGE_WHOLE_BOARD,
                        RANGED_BOOL_FALSE, RANGED_BOOL_IF_RANGED_CASTER, TargetingOptions,
                        are_entities_adjacent, charge_tiles_count, entity_tiles,
                        units_are_enemies)
from .targeting_rule import TargetingRule as TR
from .behaviours.ai_control import PerformAIAction
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import LiveUnit, entities_from_state
from .behaviours.effects import AddDynamicStatModifierEffect, AddEffect   # #931
from .behaviours.movement import MoveUnit
from .behaviours.stats import ChangeStat, Heal

from .loki import _pick_randomly_n

import hexgeo

if TYPE_CHECKING:
    from ..state import State


# ----- collapse des sélecteurs S (SurroundingTiles / CanAddUnit / FriendlyDecoysAroundTarget) -----

def _pos_of(state: "State", uid: int):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _occupied_positions(state: "State") -> set:
    occ: set = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None:
            continue
        if uc is not None and not uc.alive:
            continue
        occ.add((pc.col, pc.row))
    return occ


def _surrounding_free_tiles(state: "State", center, radius: int) -> list:
    """`CanAddUnit(SurroundingTiles(center, radius))` collapse : ids de tuiles LIBRES+marchables dans le disk
    hex de rayon `radius` autour de `center` (col,row). Le centre (tuile de la cible) est occupé -> exclu."""
    board = state.board
    if board is None or center is None:
        return []
    occ = _occupied_positions(state)
    out = []
    for (c, r) in hexgeo.disk(center[0], center[1], int(radius)):
        if (c, r) in occ:
            continue
        t = board.id_at(c, r)
        if t is None or not board.walkable(t):
            continue
        out.append(t)
    return sorted(out)


def _friendly_units_around(state: "State", center, radius: int, team, visual_id: str) -> list:
    """`UnitsWithId(SurroundingEnemies(target, radius, filter=ALLY), visual_id)` collapse : ids des unités
    VIVANTES `visual_id` de la team `team` dont la position est dans le disk hex `radius` autour de `center`."""
    if center is None:
        return []
    out = []
    within = set(hexgeo.disk(center[0], center[1], int(radius)))
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if uc is None or oc is None or pc is None or not uc.alive:
            continue
        if oc.team != team or uc.visual_id != visual_id:
            continue
        if (pc.col, pc.row) in within:
            out.append(uid)
    return sorted(out)


def _caster_level_mult(state: "State", caster_id: int):
    c = state.get_entity(caster_id)
    csc = c.get_component(StatsComponent) if c is not None else None
    ctx = csc.ctx if csc is not None else None
    level = getattr(ctx, "active_ability_level", None) if ctx is not None else None
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return level, mult


# ----- feuilles DSL (étages de l'arbre CultDemagogue) -----

class SpawnDecoys(AbilityBehaviour):
    """1er étage : `Spawn( PickRandomly(CanAddUnit(SurroundingTiles(target@0x178, range)), n=nrOfSummons),
    genesSmnDecoy, ForSteppable )` IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour. Pose `n` decoys inertes sur des tuiles libres aléatoires ≤`range`
    hex de la CIBLE. `n = GetVariableForLevel(0x4f)` = var `nrOfSummons` (config-scalé par niveau, ~8 au max, NON
    rarity-scaled) ; `range = NumberConstant(0x44)` = `constants.range` (=2). Feuille DSL -> `spawn_decoy` (G1).
    Sélecteur de tuile COLLAPSÉ (doctrine slice-18/19). Effet PUR (stop=False)."""
    __slots__ = ("target_ref", "ability_id")

    def __init__(self, target_ref, ability_id: str = "CultDemagogue"):
        self.target_ref, self.ability_id = target_ref, ability_id

    def execute(self, entities, ectx):
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        tu = resolve_unit(self.target_ref, entities)
        target_id = tu.get("id") if tu else None
        if state is None or caster_id is None or target_id is None:
            return OperationResult.ok()
        level, _mult = _caster_level_mult(state, caster_id)
        radius = int(ability_var(self.ability_id, "range", is_constant=True) or 2)
        n = int(ability_var(self.ability_id, "nrOfSummons", level) or 0)
        tiles = _surrounding_free_tiles(state, _pos_of(state, target_id), radius)
        for t in _pick_randomly_n(state, tiles, n):
            did = spawn_decoy(state, t, caster_id)
            if did is not None:
                # REF D'ETAT native : les etages AVAL du MEME arbre voient les decoys (cf. la note de
                # `SpawnNeophytesOnDecoys`). `SpawnNeophytesOnDecoys` lit le `state` directement (collapse
                # imperatif), mais la poussee garde le contexte COHERENT (occupation de tuile notamment).
                entities.units.append(LiveUnit(state, did))
                ectx.emit("SpawnDecoy", unit=did, tile=t)
        return OperationResult.ok()


class SpawnNeophytesOnDecoys(AbilityBehaviour):
    """2e étage : `Spawn( Tiles(PickRandomly(Half(Count(FriendlyDecoysAroundTarget)))), genesSmnNeophyte,
    WithStatsFromConfig )` IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour. Sur la MOITIÉ (ceil — `DivideAmount mode1=Ceiling IdunBattle.Entities.Formulas.DivideAmount$$Calculate`) des decoys
    ALLIÉS dans le disk `range` autour de la cible, summon un Neophyte (stats config-scalées `summon*_2`,
    2183/1746/437 au max). Owner = caster ; `ai_controlled=False` (le Neophyte a Ambush+BattleFatigue, PAS
    Summon -> joué au tour normal de sa team, pas auto turn-start). Sélecteur+Half COLLAPSÉS.

    ⚠ HYPOTHÈSE Q3c (re-expert) : l'arbre CultDemagogue décompilé ne montre AUCUN nœud kill-decoy -> le decoy
    sous-jacent n'est PAS retiré (cohabitation decoy+neophyte sur la tuile). À confirmer live (comptage
    d'entités après cast : remplacement vs cohabitation). Effet PUR."""
    __slots__ = ("target_ref", "ability_id")

    def __init__(self, target_ref, ability_id: str = "CultDemagogue"):
        self.target_ref, self.ability_id = target_ref, ability_id

    def execute(self, entities, ectx):
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        tu = resolve_unit(self.target_ref, entities)
        target_id = tu.get("id") if tu else None
        if state is None or caster_id is None or target_id is None:
            return OperationResult.ok()
        c = state.get_entity(caster_id)
        coc = c.get_component(OwnerComponent) if c is not None else None
        if coc is None:
            return OperationResult.ok()
        level, mult = _caster_level_mult(state, caster_id)
        radius = int(ability_var(self.ability_id, "range", is_constant=True) or 2)
        decoy_vid = _const(self.ability_id, "unitId")
        neophyte_vid = _const(self.ability_id, "unitId_2")
        tpos = _pos_of(state, target_id)
        decoys = _friendly_units_around(state, tpos, radius, coc.team, decoy_vid)
        n_neo = math.ceil(len(decoys) / 2)                    # `Half` = DivideAmount mode1 = Ceiling
        board = state.board
        for did in _pick_randomly_n(state, decoys, n_neo):
            dpos = _pos_of(state, did)
            tile = board.id_at(dpos[0], dpos[1]) if (board is not None and dpos is not None) else None
            nid = _spawn_config_grot(state, neophyte_vid, tile, self.ability_id, level, mult,
                                     coc.team, coc.player, ai_controlled=False, key_suffix="_2")
            if nid is not None:
                # REF D'ETAT (mirror de l'`AbilityEntities` natif) : le 3e etage du MEME arbre
                # (`cult_demagogue_ai_tree`, un UNIQUE `Execute` top-level) selectionne les Neophytes via
                # un selecteur DSL sur `ctx.units` -- fige a la construction du `DslContext`. Sans cette
                # poussee, il ne verrait AUCUN Neophyte => NO-OP SILENCIEUX. `LiveUnit` = pos/hp/alive
                # re-lus du state (comme la feuille `Spawn`).
                child = LiveUnit(state, nid)
                entities.children.append(child)
                entities.units.append(child)
                ectx.emit("SpawnNeophyte", unit=nid, tile=tile, on_decoy=did)
        return OperationResult.ok()


def _const(ability_id: str, key: str):
    # #484 : le `import gameconfig as GC` qui vivait ici OMBRAGEAIT son homonyme module-level
    # (ligne 21), ce qui rend `GC` local a TOUTE la fonction. Retrait SUR ici -- contrairement aux
    # differes multi-noms, c'est bien le MEME nom qui est deja lie en tete.
    return ((GC.ability(ability_id) or {}).get("constants") or {}).get(key)


def cult_demagogue_ai_tree(ability_id: str = "CultDemagogue") -> PerformAIAction:
    """3e etage de `CultDemagogueAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour` — MIRROR 1:1 du decompile
    (RETROFIT #94 : remplace l'ancienne feuille bespoke `PerformAINeophyteTurn`, qui FUSIONNAIT selecteur
    et action et n'implementait PAS le cycle de flags de tour) :

        `PerformAIAction( UnitsWithId( SurroundingEnemies(target@0x178, GetNumberConstant(0x44)=range,
                                                          1, 3),
                                       GetStringConstant(config, 4)=unitId_2, 3 ),
                          asGroup=0, resetTurnFlags=1 )`

    - `SurroundingEnemies` en surcharge **4-args** (`IdunBattleLogic.Entities.DSLSelectors$$SurroundingEnemies` : `Enemies(param_2 = X, Units(...))` ou
      `X` est A LA FOIS le centre ET la reference) -> « unites entourant la CIBLE et ennemies DE LA CIBLE »
      = les ALLIES du caster ; d'ou `reference=Target()` (cf. `selectors.SurroundingEnemies`).
    - `UnitsWithId(..., unitId_2)` (`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithId`) restreint aux Neophytes.
    - `asGroup=0` -> `ComputerActionOperation.execute` (mono) = `IdunBattle.Core.Services.AiControl$$ExecuteFor(unit)`
      UNE passe de decision PAR unite, sequentielle et independante (PAS le group operator a boucle).
    - `resetTurnFlags=1` -> les flags de tour de chaque Neophyte sont SAUVEGARDES, EFFACES puis RESTAURES
      autour de l'action (`IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags` / `IdunBattle.Operations.ComputerActionOperation$$SetUnitTurnsFlags`) : il agit meme
      s'il avait deja fini son tour, ET **son action supplementaire ne consomme pas son tour**. C'est ce
      cycle que l'ancienne feuille bespoke n'avait PAS (elle appelait `decide_and_apply` a nu).

    Le socle (`behaviours/ai_control.py::PerformAIAction` + `operations/summon_ai.py::
    ComputerActionOperation`) est utilise TEL QUEL -- la frontiere DSL/imperatif est le `.execute` de la
    feuille : au-dessus l'arbre de selecteurs, en-dessous l'Operation."""
    radius = int(ability_var(ability_id, "range", is_constant=True) or 2)
    neophytes = UnitsWithId(SurroundingEnemies(TargetTile(), Const(radius), reference=Target()),
                            _const(ability_id, "unitId_2"))
    return PerformAIAction(neophytes, as_group=False, reset_turn_flags=True)


def cult_demagogue_tree(target_ref=None):
    """Mirror `CultDemagogueAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour` :
        `op_Addition( op_Addition( Group(spawnDecoys, Null, 100), Group(spawnNeophytes, Null, 0x65) ),
                      PerformAIAction(...) )`
    (les `Group(id=100/101)` natifs = ordonnancement de VUE, no-op observable ici ; l'ASSOCIATION
    `((a+b)+c)` est celle du decompile). UN SEUL `AActiveAbility.Execute` top-level -> le contexte
    `entities` N'EST PAS re-materialise entre les etages : c'est la feuille `Spawn`/`SpawnNeophytesOnDecoys`
    qui pousse ses enfants dans `entities.units` (mirror de la ref d'etat native) pour que le selecteur
    DSL du 3e etage VOIE les Neophytes tout juste poses -- sans quoi : no-op silencieux.
    Cible ennemie = `Target()@0x178` collapsé (doctrine slice-24)."""
    tr = target_ref if target_ref is not None else Target()
    return op_add(op_add(SpawnDecoys(tr), SpawnNeophytesOnDecoys(tr)), cult_demagogue_ai_tree())


# ---- CultDemagogue (1179) : les DEUX constantes lues par `GetDynamicInvalidTargetReason` --------
CULT_DEMAGOGUE_ID = "CultDemagogue"
# `GetNumberConstant(0x44)`. ⚠ L'ORDINAL EST `range_2`, PAS `range` -- et la confusion serait
# SILENCIEUSE ici : le gameconfig de 1179 porte LES DEUX (`range = 2` ET `range_2 = 2`), donc lire
# la mauvaise cle rendrait aujourd'hui la meme valeur et divergerait au premier reequilibrage.
# (`SpawnDecoys`, dans l'`ExecuteBehaviour`, lit un AUTRE site avec son propre ordinal.)
CULT_DEMAGOGUE_CONST_RANGE = AbilityConstantType.range_2      # GetNumberConstant(0x44) -> "range_2"
CULT_DEMAGOGUE_CONST_UNIT_ID = "unitId"                       # GetStringConstant(0x0)  -> "unitId"


def cult_demagogue_free_spawn_tiles(state: "State", caster_id: int) -> list:
    """1er terme de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$GetDynamicInvalidTargetReason` :

        battleQuery.GetFreeSurroundingTiles( EntityExtensions.GetMainTile(caster, state),
                                             GetNumberConstant(0x44 range_2),
                                             includeCenter: 0, onlyMovable: 1 )      # IBattleQuery 104

    LE TERME `onlyMovable` DOMINE LES DEUX AUTRES, et c'est ce qui rend le port court -- pas une
    approximation. Corps natif de `BattleQuery$$GetFreeSurroundingTiles` :

        GetSurroundingTiles(center, distance, onlyEmptyOrSteppable: 1, onlyWalkable: 1,
                            onlyMovable, includeCenter)
          -> IterateSurroundingTiles  (disque hex, `TileQuery.<IterateSurroundingTiles>d__6`)
        FilterInPlace(t => TileExtensions.IsFreeTile(t, state, allowSteppable: 1,
                                                     allowTemporary: 0, allowAnyUnit: 0))

    et le filtre `onlyMovable` de l'iterateur (champ `+0x30`) est litteralement

        unit = UnitExtensions.GetUnit(srcTile, state)                 # l'unite SUR la tuile centre
        if (unit != null) reachable = movementQuery.GetMovableTilesFor(unit, ignoreUnitFlags: 1,
                                                                       options{ overrideRange = distance })
        ... if (!reachable.Contains(tile)) continue

    Or `reachable` est un BFS a `distance` pas depuis la tuile du caster : toute tuile atteignable
    est a distance hex <= `distance`, donc `movable(d)` est INCLUS dans le disque `SurroundingTiles(d)`
    -- l'intersection VAUT `movable(d)`. Et `IsFreeTile` (le `FilterInPlace` de queue) est PLUS
    strict que `onlyEmptyOrSteppable` comme que `onlyWalkable` (il exige vide-ou-Steppable, walkable
    et non-Blocker : meme corps que `TileExtensions$$CanAddUnit`, etabli en #287-r8). Les trois
    termes de disque sont donc DOMINES ; ce qui reste est exactement le `stop_set` du foyer
    `services/movement_query.get_movable_tiles_for`, celui que `MovableTilesInRange` rend deja.

    `includeCenter = 0` coincide : le natif `GetReachableTiles` n'EMET PAS la tuile de depart
    (`BasePathfinder.<IterateReachableTiles>d__12$$MoveNext`, cf. #287-r5-r1), et le port non plus.

    `ignoreUnitFlags = 1` desarme la garde d'entree `UnitFlagsComponent$$Has(unitFlags, 1)` de
    `MovementQuery$$FindAnyOrAllMoveableTiles` : un caster qui a DEJA bouge ce tour garde son pool.
    Cote port cette garde n'a pas de substrat (residu nomme de `MovableTilesInRange`), donc le
    booleen est INERTE ici -- ecrit pour la fidelite de lecture, pas pour un effet."""
    board = state.board
    cpos = _pos_of(state, caster_id)
    if board is None or cpos is None:
        return []
    ctile = board.id_at(cpos[0], cpos[1])
    if ctile is None:
        return []
    rng = int(((GC.ability(CULT_DEMAGOGUE_ID) or {}).get("constants") or {}).get(
        CULT_DEMAGOGUE_CONST_RANGE.name) or 0)
    if rng <= 0:
        return []
    return sorted(get_movable_tiles_for(board, state, caster_id, ctile, rng,
                                        _living_occupants_map(state),
                                        _team_of(state, caster_id)))


def cult_demagogue_has_living_decoy(state: "State", caster_id: int) -> bool:
    """2e terme de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$GetDynamicInvalidTargetReason` :

        allAlive = battleQuery.GetAllAliveUnits( Nullable<int>(
                       EntityExtensions.GetCurrentOwnerEntityId(caster)) )            # IBattleQuery 137
        return allAlive.Where(u => UnitExtensions.GetUnitId(u) == GetStringConstant(0x0 unitId)).Any()

    `BattleQuery$$GetAllAliveUnits(playerEntityId)` itere les entites vivantes et ne garde que
    celles dont `GetCurrentOwnerEntityId(entity) == playerEntityId.Value` quand le `Nullable` a une
    valeur -- donc les unites de MON JOUEUR, pas de mon equipe : le port compare
    `OwnerComponent.player` (11/12), pas `team`. Le lambda est
    `CultDemagogueAbility.<>c__DisplayClass6_0$$<GetDynamicInvalidTargetReason>b__0`, dont le corps
    entier est `String.op_Equality(GetUnitId(u), this.<name>)` -- `GetUnitId` = le `visualId`.

    `player` NON CAPTE (`None`) -> on retombe sur l'equipe, qui est la meilleure approximation
    disponible : un summon herite team ET player de son caster (`SpawnUnitOptions.CopyOwner`), donc
    les deux partitions coincident sur tous les substrats a deux joueurs. Degradation NOMMEE."""
    caster = state.get_entity(caster_id)
    coc = caster.get_component(OwnerComponent) if caster is not None else None
    if coc is None:
        return False
    name = ((GC.ability(CULT_DEMAGOGUE_ID) or {}).get("constants")
            or {}).get(CULT_DEMAGOGUE_CONST_UNIT_ID)
    if not name:
        return False
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive:
            continue
        mien = (oc.player == coc.player) if (coc.player is not None and oc.player is not None) \
            else (oc.team == coc.team)
        if mien and uc.visual_id == name:
            return True
    return False


class CultDemagogueAbility(ActiveAbility):
    """`CultDemagogueAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour` (id 1179, Isaak genesPrimus). Arbre DSL
    `cult_demagogue_tree()` : (1) pose N=`nrOfSummons` decoys ≤range de la cible ; (2) summon des Neophytes sur
    ceil(moitié) des decoys alliés de la zone (stats config `summon*_2`) ; (3) chaque Neophyte joue un tour AI
    complet immédiat. Sélecteurs de TUILE collapsés. Renvoie {decoys, neophytes, ai_units, ai_results, dsl}.

    `ai_units` = les unités RÉELLEMENT sélectionnées par le 3e étage (`PerformAIAction`) : c'est la garde
    ANTI-NO-OP-SILENCIEUX du retrofit #94 — un `ai_units` vide alors que `neophytes` ne l'est pas signale
    que le sélecteur DSL ne voit pas les summons du même arbre (cf. la note « ref d'état » de
    `SpawnNeophytesOnDecoys`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CultDemagogue)  # 1179

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$.ctor`
    # COPIE le PRESET STATIQUE `IdunBattle.Core.Services.TargetingOptions` statics `+0x180` (pose par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor`), puis `AActiveAbility..ctor(this, &opts, 2, 0)`.
    # Masque effectif = `preset+0x28` = statics `+0x1a8` -> `0x4002`.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2      TargetMatchesDynamicRule -> PORTE depuis #287-r11 (surcharge ci-dessous)
    #     0x4000   TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie)
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x180` -> `TargetingRange`
    # statique `+0x18` (`useRangeFromConfig` -> `CultDemagogue.constants.range` = 2) +
    # `forceMeleeTarget = False` (PAS de clamp melee ; contraste avec le preset `+0x140`).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        cult_demagogue_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        decoys = [p["unit"] for n, p in ectx.emitted if n == "SpawnDecoy"]
        neophytes = [p["unit"] for n, p in ectx.emitted if n == "SpawnNeophyte"]
        ai = next((p for n, p in ectx.emitted if n == "PerformAIAction"), {})
        return {"decoys": decoys, "neophytes": neophytes,
                "ai_units": ai.get("units") or [], "ai_results": ai.get("results") or [],
                "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile, ligne a ligne (#287-r11) :

            range     = GetNumberConstant(0x44 range_2);           // = 2 au gameconfig
            name      = GetStringConstant(0x0 unitId);             // = "genesSmnDecoy"
            freeTiles = battleQuery.GetFreeSurroundingTiles(GetMainTile(caster, state), range, 0, 1);
            allAlive  = battleQuery.GetAllAliveUnits(Nullable<int>(GetCurrentOwnerEntityId(caster)));
            battleQuery.GetSurroundingEnemies(target, allAlive, range, 0);       // RESULTAT JETE
            if (freeTiles.Count() != 0) return 0;                  // ICollection<ITile>.get_Count
            return allAlive.Where(u => GetUnitId(u) == name).Any() ? 0 : 2;

        ⚠ L'APPEL A `GetSurroundingEnemies` EST MORT, ET C'EST LU DANS L'ASSEMBLEUR, PAS DEDUIT.
        C'etait l'ambiguite laissee ouverte par #287-r8 §11 : Ghidra n'assigne pas le retour du slot
        120, et le `Where` qui suit recoit un `uVar7` qu'on pouvait lire soit comme le resultat
        perdu, soit comme `allAlive`. Les octets tranchent -- apres le `call r10` du slot vient
        immediatement `mov rcx, [rip+...]` puis un `call`, sans aucun `mov <reg>, rax` : RAX est
        ECRASE sans avoir ete sauve. Et le 1er argument de `Enumerable.Where` est `mov rcx, rbp`,
        or `rbp` est ce que le meme site a passe en 3e argument du slot 120 (`mov r8, rbp`),
        c'est-a-dire `allAlive`. L'appel n'a par ailleurs AUCUN effet de bord : `GetSurroundingEnemies`
        construit un `OrderedSet` NEUF (via `GetSurroundingUnits`) et n'applique son `FilterInPlace`
        qu'a celui-la, jamais a `from`.

        CONSEQUENCE DE PORTAGE, et elle est structurante : **la regle ne lit PAS la cible**. Les deux
        termes ne dependent que du CASTER (ses tuiles de pose, et l'existence d'un decoy vivant dans
        son camp). Le verdict est donc le MEME pour toutes les cibles d'un etat donne -- la bascule
        ne s'exerce pas cible par cible mais entre deux MONTAGES (caster libre / caster encercle).

        SEMANTIQUE : « je peux caster tant que j'ai ou poser un decoy ; si je n'ai plus une seule
        tuile libre atteignable dans mon rayon 2, il faut qu'un decoy soit deja en jeu ».

        Cible non resolue -> `0` : le natif n'evalue jamais cette regle sur une cible non enumeree,
        et aucun de ses deux termes ne la lit. Convention permissive du module."""
        if target_id is None:
            return 0
        if cult_demagogue_free_spawn_tiles(state, int(caster_id)):
            return 0                                   # freeTiles.Count() != 0
        return 0 if cult_demagogue_has_living_decoy(state, int(caster_id)) \
            else int(TR.TargetMatchesDynamicRule)


# ============================ HeroicFusillade (Judh genesKelermorph, actif 1180) ============================
#
# "Surrounding radius" = le champ DslContext @+0xc0 (rayon d'ADJACENCE = 1, i2 « surrounding hex »),
# DISTINCT du `range` config (=2, `GetNumberConstant(0x16)`, = portee de MOUVEMENT `MovableTilesInRange`).
# Le natif IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour lit @0xc0 (PAS `GetNumberConstant` -- contraste CultDemagogue IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour qui passe
# `GetNumberConstant(0x44)=range` a `SurroundingTiles`) -> valeur d'adjacence par defaut du contexte, non
# exposee en config. i2 (« a free surrounding hex within movement range 2 ») confirme : surrounding=adjacent(1),
# movement=2. VALIDATOR : confirmer live (drive positions).
SURROUND_RADIUS = 1


def _team_of(state: "State", uid: int):
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _living_occupants_map(state: "State") -> dict:
    """`{tile_id -> team}` des unites VIVANTES (occupation lue par le pathfinder `MovableTilesInRange`).
    board None -> {}."""
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


def _charge_candidate_tiles(state: "State", caster_id: int, target_id: int,
                            surround_radius: int, move_range: int) -> list:
    """Le POOL de tuiles de charge, DANS L'ORDRE DU SELECTEUR (avant tout tri) :

        CanAddUnit(SurroundingTiles(target@0x190, radius@0xc0))
          op_And MovableTilesInRange(caster@0x160, tile@0x168, Direct(range),
                                     ignoreFlags = 1, ignoreUnitsOnTiles = 0)

    Partage par `HeroicFusilladeAbility$$ExecuteBehaviour` et par
    `VigilanceEternalAbility$$GetPossibleMovementTiles`
    (= `IdunBattleLogic.Entities.DSLSelectors$$TilesUnitCanMoveToChargeTarget(caster, tile, target,
    Direct(GetNumberConstant(0x16)=range), ignoreFlags = 1)`, meme ensemble avec radius 1) — SEUL le
    TRI en aval differe entre les deux (cf. `_hf_move_dest_tile` / `_vigilance_move_dest_tile`).

    ⚠ #381-r1 : le 4e argument n'est PAS un `canReachOnly`, c'est `ignoreFlags` (il ne touche que la
    garde d'entree de `MovementQuery$$FindAnyOrAllMoveableTiles`). L'ensemble rendu est TOUJOURS le
    stop_set, quel que soit ce booleen — ce que ce collapse fait deja (le foyer rend le STOP-SET),
    et par chance : la lecture ecrite ici etait fausse, le resultat juste.

    `MovableTilesInRange` -> `services/movement_query.get_movable_tiles_for`, le FOYER partage qui
    porte les DEUX etages que ce collapse oubliait (`#381-r4`, ferme) : le dispatch
    `MovementQuery$$GetPathfinderTypeForUnit` -> `UnitExtensions$$IsLikeFlying` et le gate
    d'expansion `BasePathfinder$$NodesInNextLevel` -> `IsValidContinuePathTile` (#131), qui fait
    d'une tuile block-entering un CUL-DE-SAC (elle reste un STOP legal).
    `IdunBattle.DSL.TargetsSelector$$op_BitwiseAnd` = INTERSECTION : l'ordre conserve est
    celui de l'operande GAUCHE (`SurroundingTiles`). Pre-move (aucune mutation avant le MoveUnit).

    MESURE de ce que le gate manquant coutait (`probe_381r4_imperative_collapses.py`, boards reels,
    caster `genesKelermorph`, range 2, couples (caster, cible) a distance 2..4) : `C2_26` 151
    configurations ou le pool differe, dont 92 ou la destination `HeroicFusillade` change et 83 ou
    celle de `VigilanceEternal` change ; `EMC2_02` 232 / 143 / 141. La tuile en trop etait ILLEGALE
    cote natif (elle ne pend que d'un Swamp), donc le port chargeait ou le jeu ne peut pas aller.

    RESIDU : l'occupation reste lue par MAIN TILE (`_living_occupants_map`), pas par EMPREINTE --
    meme ecart que `ai/state_bridge._move_tiles`, hors perimetre de `#381-r4`."""
    board = state.board
    cpos = _pos_of(state, caster_id)
    tpos = _pos_of(state, target_id)
    if board is None or cpos is None or tpos is None:
        return []
    ctile = board.id_at(cpos[0], cpos[1])
    if ctile is None:
        return []
    reach = get_movable_tiles_for(board, state, caster_id, ctile, int(move_range),
                                  _living_occupants_map(state), _team_of(state, caster_id))
    adj_free = _surrounding_free_tiles(state, tpos, surround_radius)   # CanAddUnit(SurroundingTiles(target))
    return [t for t in adj_free if t in reach]                        # op_And MovableTilesInRange (reachOnly)


def _hf_move_dest_tile(state: "State", caster_id: int, target_id: int,
                       surround_radius: int, move_range: int):
    """Selecteur de destination de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour`, MIRROR :

        First( SortTilesByUtility( <pool de charge>, self@0x148, 7 ), 1 )

    Le `7` litteral part dans la surcharge int de
    `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility`, qui construit
    `IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor(7 = Tile)` et delegue a la surcharge objet
    -> MEME composite `Tile(7)` que `HammerOfWrathAbility$$ExecuteBehaviour` / `SkyStrikeAbility`.

    #165 — le collapse « la plus PROCHE du caster » est REFUTE (mesure case-226 : a ring-1 le natif
    charge sur la tuile la plus ELEVEE, pas la plus proche). On appelle le FOYER UNIQUE
    `engine/utilities/tile.py::first_tile_by_utility` (tri DECROISSANT stable, ZERO tirage).

    ⚠ RESIDU : le tri etant STABLE, les egalites (carte plate) sont tranchees par l'ordre du
    SELECTEUR SOURCE. Cet ordre est celui d'`IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select`
    (`OrderedSet.AddRange` du slot d'iface `battleQuery+0x65`), qui n'est PAS le meme artefact que
    l'`AdjacentTilesSelector` des ports freres : le port garde ici son parcours `hexgeo.disk`
    (`_surrounding_free_tiles`), NON prouve identique au natif. Renvoie (col,row) ou None."""
    board = state.board
    cands = _charge_candidate_tiles(state, caster_id, target_id, surround_radius, move_range)
    # `caster@0x160` = `dc.units` du selecteur (case-165b) : les feuilles gatees sur l'unite le voient.
    best = first_tile_by_utility(state, cands, unit_id=caster_id)   # First(SortTilesByUtility(..., 7), 1)
    return board.coord(best) if best is not None else None


def _hf_crit_mag(state: "State", caster_id: int, target_id: int, surround_radius: int) -> int:
    """`Multiply(Direct(GetVariableForLevel(0x42)=extraCritDmg), Count(Unobscured(CanAddUnit(
    SurroundingTiles(target, radius)))))` IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour = `extraCritDmg[level] x nbFree`. `nbFree` = nb de
    tuiles LIBRES `surround_radius`-adjacentes a la cible, comptees POST-move (le natif `Cache` la 1re eval
    = au ChangeStat(Add), APRES le move -> la tuile ou le caster vient de se poser n'est PLUS libre).
    `extraCritDmg` est rarity-scaled (`variablesAffectedByRarityBonus`) -> multiplier_pct. `Unobscured` =
    no-op board degage (cover non modelise)."""
    level, mult = _caster_level_mult(state, caster_id)
    extra = int(ability_var("HeroicFusillade", "extraCritDmg", level, multiplier_pct=mult) or 0)
    nb_free = len(_surrounding_free_tiles(state, _pos_of(state, target_id), surround_radius))
    return extra * nb_free


def heroic_fusillade_tree(state: "State", caster_id: int, target_id: int,
                          surround_radius: int, move_range: int):
    """Mirror 1:1 de `HeroicFusilladeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour` :
        op_Addition(
          If( Not(IsSurrounding(caster@0x148, target@0x178, radius)), MoveUnit(caster, destTile) ),   # MOVE
          If( IsAlive(target),
              op_Addition( op_Addition(
                  ChangeStat(caster, CRIT_DAMAGE=10, mode=2=Add, mag),                                 # buff crit (pose)
                  AttackWithAttackDamage(caster, splash, MinMaxDamage, Projectile, GetHits=nrOfHits=6) ), # 6x splash
                  ChangeStat(caster, CRIT_DAMAGE=10, mode=3=Sub, mag) ) ) )                            # buff crit (retire)
    - MOVE : `Not(IsSurrounding(caster, target, radius=1))` = move SEULEMENT si la cible n'entoure pas deja
      le caster. dest = `_hf_move_dest_tile` (pool `_charge_candidate_tiles` + tri `Tile(7)` du foyer
      `first_tile_by_utility`, #165 -- le collapse « plus proche » a ete REFUTE).
      ⚠ MoveUnit options NULL n'eteint PAS l'after-move, et la phrase qui vivait ici (« -> AUCUN after-move
      crush/overwatch ») etait PERIMEE : elle a ete refutee par #448-r1-r1-r2-r1, qui a porte la coupure
      exacte lue au decompile d'`IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` --
      `publish On(0x24) ; if (isInterimStep) return ; publish On(4 = UnitAfterMove) ; publish On(0x1d)`.
      L'octet `MoveUnitOptions+0x14` vaut `MoveUnitBehaviour+0x80`, dont le DEFAUT est 0 : une feuille DSL a
      options nulles laisse donc partir `On(4)`, donc **l'OVERWATCH**. Seul `MoveUnitOptions+0x10` est
      inverse par `MoveUnitBehaviour$$Execute` (`^ 0x101`) -> pas de flag `ArrivedAtFinalTile`, pas de
      `On(0x1c)` (c'est le `arrive_at_final_tile=False` du port). MESURE (#933-r2, seed 777,
      `necroWarden,necroDestroyer`) : le move de Judh en (0,1) declenche l'overwatch adverse, dont le
      `finish_attack` joue `HypersensoryAbilities_MoveAndSpawnDecoy` et RELOCALISE Judh en (1,2).
    - SPLASH : natif `Unobscured(Enemies(SurroundingUnits(target, radius, includeCenter=1)))`. Le
      `includeCenter=1` (IdunBattleLogic.Entities.DSLSelectors$$SurroundingUnits -> `IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles(target, includeCenter=1, radius) = disk INCLUANT la tuile cible -- contraste MOVE `includeCenter=0` = ring exclu-centre) ->
      la CIBLE est dans l'ensemble (i2 « 6x ... to the target AND all other enemies surrounding it »). Porte
      = `Union(Target(), Alive(SurroundingEnemies(TargetTile(), radius)))` (cible + ennemis-du-caster VIVANTS
      `radius`-adjacents ; `SurroundingEnemies` exclut le centre -> `Union(Target())` reinjecte la cible ;
      `Alive`/`Unobscured` = corpses/cover no-op board degage). `multi=True` (tri par id = `OrderBy` natif).
      Profil Projectile (P15), nrOfHits=6.
    - CRIT-PER-FREE-HEX : `mag = extraCritDmg[level] x nbFree` (nbFree compte POST-move). 2x `ChangeStat` sur
      CRIT_DAMAGE (Add avant l'attaque, Sub apres, source PARTAGEE) = buff crit temporaire net-nul
      scope-attaque. Le combat relit `ctx.stat(CRIT_DAMAGE)` au roll (`damage._crit_params`) -> +218 x nbFree
      par coup CRITIQUE, retire apres.
    Selecteurs S (dest, nbFree) COLLAPSES imperativement (LIVE) ; structure If/&/Not/IsAlive/IsSurrounding =
    DSL. `state`/ids requis pour le collapse (dest PRE-move ; mag callable evalue au ChangeStat(Add) POST-move)."""
    src = ("HeroicFusillade_CritDamage", caster_id)                         # source PARTAGEE add<->revert
    dest = _hf_move_dest_tile(state, caster_id, target_id, surround_radius, move_range)
    move = If(Not(IsSurrounding(Caster(), Target(), Const(surround_radius))),
              MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])))
    crit_add = ChangeStat(Caster(), int(StatType.CRIT_DAMAGE), "add", src,
                          amount=lambda entities, ectx: _hf_crit_mag(state, caster_id, target_id, surround_radius))
    crit_revert = ChangeStat(Caster(), int(StatType.CRIT_DAMAGE), "revert", src)
    splash = Union(Target(), Alive(SurroundingEnemies(TargetTile(), Const(surround_radius))))
    attack = AttackWithAttackDamage(splash, "HeroicFusillade", "Projectile", is_melee=False, multi=True)
    attack_branch = If(IsAlive(Target()), op_add(op_add(crit_add, attack), crit_revert))
    return op_add(move, attack_branch)


class HeroicFusilladeAbility(ActiveAbility):
    """`HeroicFusilladeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour` (id 1180, Judh genesKelermorph, namespace natif
    `Abilities.Active.Loki`). Arbre DSL `heroic_fusillade_tree()` : (1) Judh MOVE sur une tuile libre
    adjacente a la cible atteignable en <= `range`=2 (sauf si deja adjacente) ; (2) 6x Projectile a la CIBLE
    + tous les ennemis l'entourant (splash cible-centre) ; (3) crit +extraCritDmg x nb de hex libres
    entourant la cible (buff CRIT_DAMAGE net-nul encadrant l'attaque). Selecteurs S (dest move, nbFree)
    collapses ; structure DSL. Renvoie {move, main_attack, splash, crit_bonus, dsl}.

    RE-ARME post-resurrection (`HeroicFusillade_ResurrectAbility$$IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeroicFusillade_ResurrectAbility$$CreateTrigger` = On(0x2f=
    UnitResurrected) & OwnerIsTarget -> reset flag ability-used) = trigger SEPARE (tranche G3-Ambush /
    triggers), PAS dans l'ability active."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HeroicFusillade)  # 1180
    ABILITY_ID = "HeroicFusillade"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$.ctor`
    # utilise l'overload PRESET + flags — LE PIEGE. Sequence LUE au decompile :
    #     TargetingOptions..ctor(&tmp, 0, &statsFromClass, 1, 0x6004002, 0, 0, 0)  # 7 params : flags DIRECTS
    #     <copie integrale de tmp dans un 2e emplacement de pile `preset`>
    #     TargetingOptions..ctor(&opts, &preset, 0)                                # 3 params : PRESET + flags
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # L'overload 3 params (`IdunBattle.Core.Services.TargetingOptions$$.ctor`) fait
    # `*(this+0x28) = param_3 | *(preset+0x28)` -> Rules = `0 | 0x6004002` = `0x6004002`. Le litteral
    # visible EST donc ici le masque effectif, mais UNIQUEMENT parce que les flags OR-es valent 0 : c'est
    # le OR qui a ete lu, pas le litteral recopie a l'aveugle.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2         TargetMatchesDynamicRule -> non surcharge cote port -> defaut 0 (PERMISSIF assume)
    #     0x4000      TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie)
    #     0x6000000   AllowObscuredTarget      -> permissif
    # PORTEE (#241) : `range = TargetingRange` statique `+0x48` = `useWholeBoard` -> aucun
    # test de portee (l'overload PRESET+flags applique ENSUITE ne touche que `Rules`).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        move_range = int(ability_var(self.ABILITY_ID, "range", is_constant=True) or 2)
        ectx = ExecutionContext(state=state, rng=state.rng)
        heroic_fusillade_tree(state, caster_id, target_id, SURROUND_RADIUS, move_range).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]            # cibles splash != cible principale
        crit_bonus = next((p.get("amount") for n, p in ectx.emitted
                           if n == "ChangeStat" and p.get("mode") == "add"), 0)
        return {"ability": "HeroicFusillade", "caster": caster_id, "target": target_id,
                "move": moved, "main_attack": main, "splash": splash,
                "crit_bonus": crit_bonus, "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile, avec son lambda
        (`...HeroicFusilladeAbility.u003Cu003Ec__DisplayClass2_0$$u003CGetDynamicInvalidTargetReasonu003Eb__0`)
        (#287-r11-r1) :

            dc.ability = this ; dc.caster = caster ;
            dc.range   = GetNumberConstant(0x16 range);                          // = 2
            tiles = battleQuery.GetSurroundingTiles(targetTiles, 1,          // slot 103
                                                    onlyEmptyOrSteppable: 0, onlyWalkable: 1,
                                                    onlyMovable: 0, includeCenter: 1);
            list  = tiles.Where(t => movementQuery.IsInMovementRange(dc.caster, t,
                                                                     ignoreUnitFlags: 1,
                                                                     { overrideRange = dc.range }))
                         .ToList();                                              // IMovementQuery slot 13
            if (battleQuery.GetMinDistance(targetTiles, casterTiles) < 2) return 0;       // slot 111
            return list.Count == 0 ? 2 : 0;                                      // TargetMatchesDynamicRule

        SEMANTIQUE : c'est la CHARGEABILITE, et elle a un COURT-CIRCUIT. Judh tire apres s'etre
        colle a la cible ; si elle est DEJA au contact (`GetMinDistance < 2`) il n'a rien a
        parcourir et la cible est valide sans autre test. Sinon il faut qu'une tuile du ring-1 de
        la cible soit dans son stop-set de mouvement a `range` pas.

        ⚠ TROIS LECTURES QUI SE RATENT SI ON RECOPIE LE POOL DE CHARGE DE L'`ExecuteBehaviour`.
        `_charge_candidate_tiles` (ci-dessus) est un ensemble DIFFERENT, et le substituer ici
        fabriquerait des refus :
          * le gate de ciblage passe `onlyEmptyOrSteppable = 0` -- les tuiles OCCUPEES ENTRENT dans
            le disque, seul `IsInMovementRange` les elimine ; le pool de charge, lui, applique
            `CanAddUnit`, strictement plus severe (blocker / `NotWalkable` / tuile RESERVEE) ;
          * le gate passe `includeCenter = 1` (la tuile de la CIBLE reste candidate ; elle ne survit
            au filtre que si elle est dans le stop-set, ce qu'une tuile occupee n'est pas) alors que
            `CanAddUnit(SurroundingTiles(...))` exclut le centre ;
          * l'ORDRE des deux termes est inverse au decompile : le `Where`/`ToList` est calcule AVANT
            le court-circuit de distance, qui ne le lit pas. Aucune consequence sur le VERDICT (le
            natif jette la liste), mais le port ne doit pas en tirer que la distance est un filtre
            du pool.

        ⚠ `GetMinDistance` (slot **111**, LU dans
        `data/symbols/<build>/metadata/interface_slots.tsv`) N'EST PAS `GetDistance` (slots 108-110,
        homonymes) : il prend le MIN sur toutes les paires des deux EMPREINTES, et rend **-1** quand
        aucune paire n'est mesurable. `-1 < 2` -> `return 0`, donc un substrat vide DESARME la
        regle -- la degradation permissive du module, ici obtenue par le mirror lui-meme
        (`services/movement_query.get_min_distance`), pas par une garde ajoutee.

        ⚠ `IsInMovementRange(unit, tile, ignoreUnitFlags, options)` =
        `GetMovableTilesFor(unit, ignoreUnitFlags, options).Contains(tile)` -- c'est le FOYER
        `services/movement_query.get_movable_tiles_for`, DEJA porte (dispatch de pathfinder + gate
        d'expansion `IsValidContinuePathTile`), et c'est celui que `_charge_candidate_tiles` emploie
        deja. `options.overrideRange = range` est le seul champ pose (la struct de 0x30 octets est
        remise a zero au site) ; `ignoreUnitFlags = 1` ne touche que la garde d'entree
        `UnitFlagsComponent$$Has`, sans substrat cote port (residu deja nomme par le foyer).

        Cible non resolue / board absent -> `0` : convention permissive du module."""
        if target_id is None:
            return 0
        board = state.board
        cpos = _pos_of(state, int(caster_id))
        tpos = _pos_of(state, int(target_id))
        if board is None or cpos is None or tpos is None:
            return 0
        # `GetMinDistance(targetTiles, casterTiles) < 2` -- EMPREINTES des deux entites (#433-r3-r1).
        if get_min_distance(get_unit_feet(state, int(target_id)),
                            get_unit_feet(state, int(caster_id))) < 2:
            return 0
        # `GetNumberConstant(0x16 range)` -- ILLISIBLE => `0`, la convention permissive du module
        # (surtout pas un `or 2` de repli : un defaut invente ferait REFUSER sur un substrat non
        # mesure, exactement la degradation inverse de celle qu'on assume partout ailleurs).
        raw = ability_var(self.ABILITY_ID, AbilityConstantType.range.name, is_constant=True)
        ctile = board.id_at(cpos[0], cpos[1])
        if raw is None or ctile is None:
            return 0
        move_range = int(raw)
        # `GetSurroundingTiles(targetTiles, 1, oEoS=0, oW=1, oM=0, incC=1)` : disque ring-1 + centre,
        # tuiles OCCUPEES comprises (aucun filtre de contenu ici).
        disque = battle_query.get_surrounding_tiles(
            tpos, radius=SURROUND_RADIUS, include_center=True, check_walkable=True,
            walkable_at=lambda p: board.walkable(board.id_at(p[0], p[1])),
            elevation_at=lambda p: board.elevation(board.id_at(p[0], p[1])),
            tile_exists=lambda p: board.id_at(p[0], p[1]) is not None)
        # `.Where(t => IsInMovementRange(caster, t, 1, {overrideRange = range}))`
        reach = get_movable_tiles_for(board, state, int(caster_id), ctile, move_range,
                                      _living_occupants_map(state), _team_of(state, int(caster_id)))
        for p in disque:
            if board.id_at(p[0], p[1]) in reach:
                return 0                                    # `list.Count != 0`
        return int(TR.TargetMatchesDynamicRule)


# ===================== VigilanceEternal (Tyrith custoKyrus, actif 1202) =====================
#
# `VigilanceEternalAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$ExecuteBehaviour` (namespace natif `Abilities.Active.Loki`,
# Custodes -- HORS gen-stealer, mais REUTILISE le pool de charge `_charge_candidate_tiles` de HeroicFusillade
# defini ci-dessus, d'ou le voisinage). L'arbre est `HeroicFusillade IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour` EXACT, MOINS splash/crit :
#     op_BitwiseAnd(
#       If( Not(IsAdjacent(caster@0x160, target@0x178, 3)),                                  # MOVE gate
#           MoveUnit(caster, First(SortTilesByUtility(GetPossibleMovementTiles, 0x20))) ),   # charge-tile
#       If( IsAlive(caster@0x160) op_BitwiseAnd IsAlive(target@0x178),                       # ATTACK gate (2)
#           AttackWithAttackDamage(caster, target, MinMaxDamage, GetDamageProfile,           # mono-cible
#                                  GetNumberConstant(0x2f)=nrOfHits) ) )
# Differences avec HeroicFusillade (IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour), lues au decompile :
#  - MOVE gate = `Not(IsAdjacent(caster, target, 3))` (`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent` -> `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger`) au lieu de
#    `Not(IsSurrounding(caster, target, radius=1))`. `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger : le predicat
#    par-paire = slot iface `0x5f` (bool `AreNeighbours(pos_a,pos_b)`, PAS `0x6e`=GetDistance d'`IsInRange`
#    IdunBattle.Entities.Triggers.IsInRangeAbilityTrigger$$ShouldTrigger) -> seuil dist==1 STRICT ; le `3` (champ +0x18) n'est PAS passe a `0x5f` -- il ne va qu'a
#    l'eval du selecteur (`FUN_180025220` param_5), INERTE pour les selecteurs d'unite Caster/Target. Donc
#    la gate = "bouge SAUF si deja adjacent (dist 1) a la cible", SEMANTIQUEMENT IDENTIQUE au move-gate
#    HeroicFusillade. Corrobore : (a) wiki Tyrith (« melee mobile ... cible un ennemi DEJA adjacent OU
#    ayant un hex libre adjacent dans la move range 2, gap-close sur cet hex ») ; (b) le node `IsAdjacent`
#    porte (dist==1, sans radius) ; (c) le precedent TheBetrayer IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour (meme node IsAdjacent sous
#    op_LogicalNot pour gater un move). Le port reutilise le node dist==1 tel quel. [VALIDE LIVE : dist 2/3
#    -> gap-close ; dist 1 -> skip move.]
#  - ATTACK gate = `IsAlive(caster) op_BitwiseAnd IsAlive(target)` (les DEUX vivants) au lieu du seul
#    `IsAlive(target)` -- le caster peut mourir a un overwatch/counter pendant la charge (Tyrith melee).
#  - Attaque MONO-cible (`AttackWithAttackDamage(caster, target, ...)`, PAS de Union/SurroundingEnemies) ;
#    AUCUN buff crit (pas de ChangeStat encadrant). Profil = `GetDamageProfile` = "Power" (melee, pierce
#    40%) ; nrOfHits = `GetNumberConstant(0x2f)` = 3 ; bornes = `MinMaxDamage` = minDmg/maxDmg[level].
#  - Composition top-level = `op_BitwiseAnd` (CombinedBehaviour, == `op_add` : Seq court-circuit ; les deux
#    branches sont pures -> les deux s'executent).
# `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetPossibleMovementTiles` = `IdunBattleLogic.Entities.DSLSelectors$$TilesUnitCanMoveToChargeTarget(caster@0x160, tile@0x168,
# target@0x190, Direct(GetNumberConstant(0x16)=range=2), canReachOnly=1)
#   = `CanAddUnit(AdjacentTiles(target)) op_And MovableTilesInRange(caster, tile, Direct(range), reachOnly=1)`
#   == EXACTEMENT le pool `_charge_candidate_tiles` de HeroicFusillade avec surround_radius=1
#   (AdjacentTiles = ring-1 = SurroundingTiles radius 1) + move_range=range=2.
VIGIL_SURROUND_RADIUS = 1     # AdjacentTiles(target) = ring-1 (== SurroundingTiles radius 1)


def _vigilance_move_dest_tile(state: "State", caster_id: int, target_id: int, move_range: int):
    """Selecteur de destination de `VigilanceEternalAbility$$ExecuteBehaviour` :

        First( SortTilesByUtility( GetPossibleMovementTiles, caster@0x160, 0x20 ), 1 )

    Le litteral d'utilite est **0x21 = 33 = `UtilityType.MovementSuggestion`**, PAS le `7 = Tile` des
    ports freres (SkyStrike / HeroicFusillade / ForwardSpotter / HammerOfWrath). Relu au decompile
    (#201, re-relu #420 sur `rnca9r7q6c`) : `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities`
    ecrit, pour la cle `0x21`, un tableau de DEUX `UtilityType` -> `[0] = 7` (Tile) puis `[1] = 0x22` (TileDistance), et
    `UtilitiesDatabase$$GetUtility` en fait un `ComposedUtility` de ces deux enfants.

    Les DEUX enfants sont desormais portes (`engine/utilities/tile.py`), donc ce call-site passe par le
    FOYER `first_tile_by_utility(..., utility_type=MovementSuggestion)` comme ses freres. Le collapse
    « la tuile la plus PROCHE du caster » qui vivait ici est SUPPRIME : il ne reproduisait le natif que
    dans le regime ou `Tile(7)` est PLAT (alors `TileDistance` -- seul terme non nul, `-d/10` --
    ordonne effectivement par distance croissante) et il INVERSAIT le natif des que `Tile(7)`
    departageait, puisque `Tile(7)` est a valeurs entieres et domine toujours `|TileDistance| <= 0.2`
    sur un pool de charge. Il portait en prime un tie-break INVENTE (`, t` = id de tuile) la ou le natif
    laisse le tri STABLE rendre l'ordre du selecteur source. Cf.
    `docs/rl/case-201-movement-suggestion-tiledistance.md`. Renvoie (col,row) ou None."""
    board = state.board
    cands = _charge_candidate_tiles(state, caster_id, target_id, VIGIL_SURROUND_RADIUS, move_range)
    if board is None or not cands:
        return None
    # `caster@0x160` = `dc.units` du selecteur -> `case.units`, l'unite dont `TileDistanceUtility`
    # mesure l'eloignement (et que lisent les feuilles gatees sur l'unite, case-165b).
    best = first_tile_by_utility(state, cands, unit_id=caster_id,
                                 utility_type=int(UtilityType.MovementSuggestion))
    return board.coord(best) if best is not None else None


def vigilance_eternal_tree(state: "State", caster_id: int, target_id: int, move_range: int):
    """Mirror 1:1 de `VigilanceEternalAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$ExecuteBehaviour` (HeroicFusillade moins
    splash/crit) : `op_and(If(Not(IsAdjacent(caster,target)), MoveUnit(caster, destTile)),
    If(IsAlive(caster) & IsAlive(target), AttackWithAttackDamage(caster->target, Power, 3 hits)))`.
    dest = `_vigilance_move_dest_tile` (pool `_charge_candidate_tiles` avec surround_radius=1,
    move_range=`range`=2, puis collapse du tri `MovementSuggestion(33)`) PRE-move ; gate move =
    `Not(IsAdjacent)` (dist==1 : bouge sauf si deja adjacent) ; gate attaque = les deux vivants
    (re-eval LIVE apres le move -- Voie A, `LiveUnit`)."""
    dest = _vigilance_move_dest_tile(state, caster_id, target_id, move_range)
    move = If(Not(IsAdjacent(Caster(), Target())),
              MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])))
    attack = AttackWithAttackDamage(Target(), "VigilanceEternal", "Power", is_melee=True)   # mono-cible
    attack_branch = If(TriggerAnd(IsAlive(Caster()), IsAlive(Target())), attack)
    return op_and(move, attack_branch)


class VigilanceEternalAbility(ActiveAbility):
    """`VigilanceEternalAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$ExecuteBehaviour` (id 1202, Tyrith custoKyrus, namespace natif
    `Abilities.Active.Loki`). Arbre DSL `vigilance_eternal_tree()` = HeroicFusillade EXACT moins splash/crit :
    (1) Tyrith MOVE sur une tuile libre adjacente a la cible atteignable en <= `range`=2 (sauf si deja
    adjacente, gate `Not(IsAdjacent)`) ; (2) attaque MONO-cible melee (profil Power, 3 hits) gatee par les
    DEUX vivants. Selecteur S (dest move) collapse ; structure DSL. Renvoie {move, attack, dsl}.
    Ne termine PAS le tour (`SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag` overrides = base.py, 1202 dans les
    deux frozensets) -> flags NON poses (reutilisable plusieurs fois/tour, cf. wiki Tyrith).

    VALIDE LIVE (#220, confront cast 1202 vs port, board MC1_67, custoKyrus vs necroWarden) :
      - GATE dist==1 CONFIRME : cible a dist 3 -> le JEU charge Tyrith (live_moved=True) == port. Prouve que le
        `3` d'`IsAdjacent` n'est PAS un seuil dist<=3 (sinon aucun move a dist 3).
      - LANDING TILE EXACT : port pose Tyrith en (0,1) == live (0,1) (collapse closest-tile de
        `SortTilesByUtility(0x20)` fidele).
      - MONO-CIBLE : un ennemi voisin de la cible n'est PAS touche (pas de splash).
      - RESIDU DEGAT ~1% : RESOLU (cas fable rngcrit-1202, 2026-07-23). La cause N'ETAIT PAS un crit-roll a
        cc=0 (refute decompile : `IdunBattle.Core.Services.DamagePrediction$$RollCritical` gate `cc<1 -> false SANS tirage`,
        unique chemin crit d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` ; la note damage.py "cc=0 => 0 tirage" reste VRAIE pour
        les DEUX vecteurs). Le 2e tirage/coup natif = le VECTEUR : AttackWithAttackDamage passe par le MEME
        `ExecuteHit` que l'attaque normale mais avec un struct NON degenere -> `IdunBattle.Core.HitDamage$$GetDamage`
        tire la VALEUR BRUTE (1 tirage) PUIS `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` (slot 8, SANS gate
        min==max) consomme 1 tirage GASPILLE sur la cellule degeneree. Fix : `_run_hits`/`_one_hit` branche
        post_roll (damage.py) ; valide bit-exact per-hit + consommation (6 tirages/3 coups) sur 5 seeds x 2
        cibles via probe_rngcrit_1202.py.
      - ECART RESIDUEL +1/coup A ARMURE>0 (« [918,903,1112] vs live [919,904,1113] ») : **PERIME**,
        RE-MESURE le 2026-07-28 (`docs/rl/case-38-offbyone-armor-materialization.md`). Ce n'etait pas un
        gap de percage mais la MATERIALISATION finale, qui TRONQUAIT au lieu d'ARRONDIR
        (`FixMath.NET.Fix64$$Round(., AwayFromZero)`, dernier etage de
        `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`) ; ferme par #131
        (vecteur normal) et par la campagne HeavyGravCannon (vecteur ability bounds-mode). Re-mesure sur
        le montage d'origine (custoKyrus vs necroWarden, `--armor-target`) : port livre bit-exact
        **24/24 coups**, les deux vecteurs, a cc=0 ET a cc>=1 (9 tirages live == 9 port). La troncature
        REPRODUIT le symptome de la fiche (`port = live - 1` des que frac >= .5) -> les chiffres cites
        etaient ceux du port de l'epoque. Garde : `tests/engine/runner/test_offbyone_armor_38_live.py`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.VigilanceEternal)  # 1202
    ABILITY_ID = "VigilanceEternal"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$.ctor`
    # utilise le MEME schema PRESET + flags que HeroicFusillade (ctors jumeaux) :
    #     TargetingOptions..ctor(&tmp, 0, &statsFromClass, 1, 0x206004002, 0, 0, 0)  # flags DIRECTS
    #     TargetingOptions..ctor(&opts, &preset=tmp, 0)                              # PRESET + flags (OR 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # -> Rules = `0 | 0x206004002` = `0x206004002` (le OR a ete LU, cf. HeroicFusillade).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2           TargetMatchesDynamicRule -> non surcharge cote port -> defaut 0 (PERMISSIF)
    #     0x4000        TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie)
    #     0x6000000     AllowObscuredTarget      -> permissif
    #     0x200000000   TargetIsNotAnObject -> `UnitExtensions$$HasTrait(target, 0xd)` INTERDIT (la cible
    #                   ne doit pas porter ce trait). NON PORTE (aucun predicat de trait dans la cascade) ->
    #                   degradation PERMISSIVE : le port accepte une cible que le natif refuserait.
    # PORTEE (#241) : `range = TargetingRange` statique `+0x48` = `useWholeBoard` -> aucun
    # test de portee (meme forme PRESET+flags a 0 que HeroicFusillade).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
        | TR.TargetIsNotAnObject
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetDynamicInvalidTargetReason`
        (#287-r5-r1) -- MIRROR du decompile :

            if (battleQuery.<slot 0x62 AreEntitiesAdjacent/2>(casterTiles, targetTiles)) return 0;
            sel = VigilanceEternalAbility$$GetPossibleMovementTiles();
            return sel.<slot 10 SelectTiles/1>(ents).Count < 1 ? 0x8000000 : 0;

        `0x8000000` = `TargetingRule.TargetIsInRange` ; `battleQuery` = `AActiveAbility+0x20` ; les
        deux slots sont LUS dans `data/symbols/<build>/metadata/interface_slots.tsv`
        (`IBattleQuery 98 AreEntitiesAdjacent 2`, `ITargetsSelector 10 SelectTiles 1`).

        SEMANTIQUE : Tyrith accepte une cible DEJA au contact (le `Not(IsAdjacent)` de la behaviour
        saute alors le MOVE) ; sinon il faut qu'elle soit CHARGEABLE ce tour-ci, c'est-a-dire qu'une
        tuile libre adjacente a la cible soit atteignable en <= `range` = 2 pas.

        LE COURT-CIRCUIT D'ADJACENCE EST PROPRE A 1202 -- `LeadingTheChargeAbility` (1204) partage le
        MEME etage sans lui, et son masque porte en prime `TargetIsNotAdjacent`. Les deux regles ne
        sont donc pas interchangeables.

        `GetPossibleMovementTiles` passe `ignoreFlags = 1` (`CONCAT71(..., 1)` au call-site), la ou
        1204 passe `0`. ⚠ TERME NON EXERCE, cause MESUREE : `ignore_flags` ne touche que la garde
        d'entree `UnitFlagsComponent$$Has(unitFlags, 1)` de
        `MovementQuery$$FindAnyOrAllMoveableTiles`, et `unitFlags` n'a AUCUN substrat cote port
        (residu #381, deja nomme dans `MovableTilesInRange`) -- les deux valeurs rendent donc le meme
        ensemble ici. Le parametre est PROPAGE quand meme : le jour ou le substrat existe, les deux
        call-sites divergeront comme le natif.

        `are_entities_adjacent` prend les DEUX EMPREINTES (`AreEntitiesAdjacent(IList, IList)`), pas
        deux MainTiles -- meme foyer que `_dynamic_rule_blood_chalice`. Cible non resolue -> `0`
        (convention permissive du module)."""
        if target_id is None or state.get_entity(int(target_id)) is None:
            return 0
        if are_entities_adjacent(state.board, entity_tiles(state, int(caster_id)),
                                 entity_tiles(state, int(target_id))):
            return 0
        n = charge_tiles_count(state, caster_id, target_id, self.ABILITY_ID, ignore_flags=True)
        if n is None:
            return 0
        return int(TR.TargetIsInRange) if n < 1 else 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        move_range = int(ability_var(self.ABILITY_ID, "range", is_constant=True) or 2)
        ectx = ExecutionContext(state=state, rng=state.rng)
        vigilance_eternal_tree(state, caster_id, target_id, move_range).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        return {"ability": "VigilanceEternal", "caster": caster_id, "target": target_id,
                "move": moved, "attack": atk, "dsl": True}


# ===================================================================================================
# genesBiophagus "Hollan" -- le passif `TwistedScience` (1278) et l'active qu'il SUBSTITUE      #931 #
# ===================================================================================================
#
# CINQ FACES natives, etablies au decompile (jamais deduites d'une colonne d'audit) :
#
#  [F1] `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TwistedScienceAbility` -- le PASSIF
#       (`TriggeredAbilityType.TwistedScience` = 0x4fe = 1278) :
#         `$$CreateTrigger`   = corps PARTAGE (ICF), voir plus bas -- `DSLTriggers@+0x30` =
#                               `On(0x21 = AbilityInit) & <trigger @DSLTriggers+0x70> & OwnerIsActor` ;
#         `$$CreateBehaviour` = `RemoveActiveAbility(Owner@DSLSelectors+0x30, 0x12 = ActiveAbilityType.Heal)
#                                op_BitwiseAnd
#                                AddActiveAbility(Owner@+0x30, 0x48f = ActiveAbilityType.Heal_TwistedScience,
#                                                 abilityState)`
#       -> a l'init, le soin GENERIQUE que le trait `Healer` accorde est REMPLACE par 1167, et
#       l'`AbilityState` transmis est celui du PASSIF (c'est ce qui fait que 1167 s'indexe sur le
#       niveau de `TwistedScience`, jamais sur une entree gameconfig `Heal_TwistedScience` -- il n'y
#       en a AUCUNE). NON PORTE, et le verdict est mesure : cf. `docs/rl/case-931-twisted-science.md`
#       -- le runner ne rejoue pas `AbilityInit`, il charge un etat ou le natif a DEJA fait le swap.
#
#  [F2] `IdunBattleLogic.Entities.Abilities.Active.Loki.TwistedScience_HealAbility` (1167) --
#       PORTEE ICI (`$$.ctor`, `$$GetDynamicInvalidTargetReason`, `$$ExecuteBehaviour`).
#
#  [F3] `IdunBattle.Entities.Effects.Loki.TwistedScience_ExtraDmgEffect` (1356) -- PORTEE dans
#       `entities/effects/loki/extra_damage.py` (`TwistedScienceExtraDmgEffect`).
#
#  [F4] `EffectType.TwistedScience_ExtraHp` (1355) -- AUCUNE classe native dediee : c'est le
#       `DynamicStatModifierEffect` GENERIQUE qu'`AddDynamicStatModifierEffect` materialise sur
#       `StatType.Health`. Sa POSE est portee (elle est le gate de non-repose, cf. [F2] et la face
#       DECISION) ; son +maxHP ne l'est pas -- residu #572-r1, meme arbitrage que 1546 de #902.
#
#  [F5] `IdunBattle.AI.Playbook.Loki.TwistedScience_HealPlaybook` -- face DECISION, DEJA PORTEE
#       (`engine/playbook/common.py::TwistedScience_HealPlaybook` ; utilite +100 / +100 Genestealers,
#       `ShouldExecute = utility > 0` sans la clause boss du 18 generique).
#
# AUCUNE face DEAD dans le moteur. La seule morte du kit est le VISUEL du passif
# (`IdunBattle.View.AbilityConfigs.Loki.TwistedScienceVisuals$$ExecuteInternal` alloue son itérateur
# `<ExecuteInternal>d__3` et le rend ; le `MoveNext` de cet itérateur n'a AUCUNE entree propre dans
# les deux tables = corps fondu par l'ICF avec un `MoveNext` trivial -> aucune etape visuelle), et
# elle vit cote VIEW, hors moteur.
#
# ⚠ COMMENT `$$CreateTrigger` A ETE LU, alors qu'il n'apparait dans AUCUNE table. Les deux tables
# (`frida/methods.tsv`, `ghidra/functions.tsv`) sont DEDUPLIQUEES par adresse : elles n'attribuent un
# corps partage qu'a UN proprietaire. La table `methodPointers` du PE, elle, porte UNE ENTREE PAR
# PROPRIETAIRE et les range par classe : les xrefs DATA de `TwistedScienceAbility$$CreateBehaviour`
# donnent sa position, et ses voisins immediats sont les autres methodes de la MEME classe --
# `[.., SummaryExecutionAddBaseEffectAbility$$CreateTrigger, TwistedScienceAbility$$CreateBehaviour,
# RequiredByNativeCodeAttribute$$.ctor, UnbridledCarnageReworkedAbility$$CreateTrigger, ..]`. Le
# premier voisin EST le `CreateTrigger` de `TwistedScienceAbility` (corps ICF, **58 xrefs DATA**,
# donc 58 abilities sans rapport partagent cet accesseur), le troisieme son `.ctor` trivial. Son
# corps : `return this@+0x28 /* dsl */ -> +0x88 /* DSLTriggers */ -> +0x30`, et
# `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` ECRIT ce champ `+0x30` =
# `On(0x21) & <+0x70> & get_OwnerIsActor`. Conclure "pas de CreateTrigger" de l'absence en table
# aurait ete un faux negatif.

#: Cle gameconfig du PASSIF, et le SEUL endroit ou vivent `hp` et `extraDmg` de cette mecanique.
#: `Heal_TwistedScience` (1167) n'a AUCUNE entree dans `units.abilities` -> `ABILITY_ID = None` sur
#: la classe (cf. `RepairAbility`, meme situation d'ability DERIVEE).
TWISTED_SCIENCE_ID = "TwistedScience"
#: `EffectType.TwistedScience_ExtraHp` -- le stat-mod HEALTH pose sur la cible, et le MARQUEUR que
#: `$$ExecuteBehaviour` et `$$GetDynamicInvalidTargetReason` testent tous deux ("Affected units
#: cannot gain the effects of Twisted Science again").
TWISTED_SCIENCE_EXTRA_HP = int(EffectType.TwistedScience_ExtraHp)      # 0x54b = 1355
#: `EffectType.TwistedScience_ExtraDmg` -- le +extraDmg additif, pose seulement si la cible est de
#: faction `Genestealers`.
TWISTED_SCIENCE_EXTRA_DMG = int(EffectType.TwistedScience_ExtraDmg)    # 0x54c = 1356
#: Cle de source du `ChangeStat` de PV COURANTS. La branche HEALTH de la feuille mute
#: `HealthComponent.hp` directement (stat FILL-UP) et ne la relit pas ; elle reste NOMMEE pour la
#: tracabilite -- meme convention que `_NRP_HEAL_SOURCE` (#902, MEME patron statmod + ChangeStat).
_TS_HEAL_SOURCE = "TwistedScience:hpFill"


def twisted_science_extra_hp(state: "State", caster_id: int) -> int:
    """`DSLFormulas.ConfigVar(0x4fe = TriggeredAbilityType.TwistedScience, Owner@DSLSelectors+0x30,
    0x1d = AbilityVariableType.hp)` -- la surcharge TROIS arguments
    `ConfigVar(abilityType:TriggeredAbilityType, unit:ITargetsSelector, variableType)`, qui construit
    un `IdunBattle.Entities.Formulas.ConfigAmount(abilityType, abilitiesDatabase, unit, variableType)`.

    ⚠ LA SURCHARGE EST CE QUI TRANCHE LA SOURCE DU NIVEAU. Celle-ci resout la config du PASSIF
    (`TriggeredAbilityType` 1278) sur l'UNITE designee -> niveau PASSIF du porteur, pas l'`AbilityState`
    de l'active castee. Les deux autres surcharges de `ConfigVar` prennent un `AbilityState` ou un
    `IAbilityStateSelector` et donneraient le niveau de l'ACTIVE -- ici 1167, qui n'a aucune config.
    D'ou `ctx.passive_ability_level`, exactement comme `galvanic_override_amount`
    (`abilities/repair.py`) le fait pour `GalvanicField`.

    COLLAPSE V assume : le noeud est resolu en scalaire ici, la feuille l'accepte tel quel.
    `hp` est dans `variablesAffectedByRarityBonus` -> le multiplicateur s'applique. Pas de `ctx` /
    config illisible -> `0` (aucune valeur inventee)."""
    e = state.get_entity(int(caster_id)) if caster_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0
    lvl = getattr(ctx, "passive_ability_level", None)
    if lvl is None:
        lvl = getattr(ctx, "active_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    return int(ability_var(TWISTED_SCIENCE_ID, AbilityVariableType.hp.name, lvl,
                           multiplier_pct=mult) or 0)


def twisted_science_heal_amount(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount(dsl)` =

        Multiply( StatAmount(Caster@DSLSelectors+0x48, 0 = ATTACK, 0 = Current),
                  Max( WeaponHighestHits(Caster@+0x48), Get(1) ) )

    -- l'arbre IDENTIQUE, feuille pour feuille, a `RepairAbility$$RepairAmount` (`abilities/repair.py`).
    `TwistedScience_HealAbility$$ExecuteBehaviour` l'appelle en PREMIER et passe son resultat au
    `DSLBehaviors$$Heal` final : le soin de 1167 est donc le soin GENERIQUE, l'ability n'ajoutant
    que le bloc de buffs.

    COLLAPSE V assume (doctrine slice-23) : les trois feuilles se resolvent en deux lectures du
    `UnitContext` du caster, et le produit vit deja dans `engine.predict.heal_amount_weapon` -- LA
    seule lecture de cette formule dans le moteur, deja confrontee live cote DECISION (#45c). On
    l'appelle, on ne la duplique pas. Sans `ctx` -> `0`."""
    e = state.get_entity(int(caster_id)) if caster_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0
    return int(heal_amount_weapon(int(ctx.stat(StatType.ATTACK)),
                                  int(getattr(ctx, "normal_weapon_hits", 1) or 1)))


def twisted_science_heal_tree(state: "State", caster_id: int) -> AbilityBehaviour:
    """L'arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.TwistedScience_HealAbility$$ExecuteBehaviour`
    -- MIRROR du decompile, feuille par feuille et dans SON ordre :

        healAmount = HealAbility.HealAmount(dsl)
        hasExtraHp = DSLTriggers.HasEffect(Target@+0x60, 0x54b = TwistedScience_ExtraHp,
                                           onlyActive = false, targetType = 6 = Both)
        hpVar      = DSLFormulas.ConfigVar(0x4fe = TwistedScience, Owner@+0x30, 0x1d = hp)
        statMod    = DSLBehaviors.AddDynamicStatModifierEffect(targets = Target@+0x60,
                        source = Owner@+0x30, effectType = 0x54b, statType = 5 = Health,
                        abilityStateSelector = AActiveAbility.AbilityStateReference,
                        turns = null, isHidden = false)
        addDmg     = DSLBehaviors.AddEffect(0x54c = TwistedScience_ExtraDmg,
                        abilityState = AbilityStateReference, source = Owner@+0x30,
                        targets = Target@+0x60, options = default(0) -> PERMANENT)
        isGS       = DSLTriggers.HasFaction(Target@+0x60, 0xf = UnitFaction.Genestealers,
                                            selectionType = 3 = OnlyAliveAndTargetable)
        addHp      = DSLBehaviors.ChangeStat(targets = Target@+0x60, stat = Stat(5 = Health),
                        mode = 2 = Add, amount = hpVar, modificationEntity = null,
                        selectionType = 3, isModifiable / isHiddenModification = false)
        cond       = NOT(hasExtraHp) op_BitwiseAnd NOT(DSLTriggers.get_OwnerIsTarget)
        heal       = DSLBehaviors.Heal(healer = Caster@+0x48, selector = Target@+0x60, healAmount,
                        HealBehaviourOptions.ForHeal())
        Execute( If(cond, (statMod op_Addition addHp) op_Addition If(isGS, addDmg)) op_Addition heal )

    ## Ce que la STRUCTURE dit, et que l'i2 seul ne dirait pas

    * le SOIN est INCONDITIONNEL -- il est le second terme du `op_Addition` FINAL, hors du `If`.
      Une cible deja marquee, ou le caster lui-meme, est soignee sans recevoir aucun buff ;
    * le bloc de buffs est gate par DEUX termes, tous deux nies : `!HasEffect(1355)` ("Affected
      units cannot gain the effects of Twisted Science again") et `!OwnerIsTarget` ("Units healed
      by Hollan, **other than himself**") ;
    * `AddDynamicStatModifierEffect` (max HP) precede `ChangeStat` (PV courants) : le natif releve
      le plafond AVANT de remplir, ce qui rend son clamp inerte. Cote port `HealthComponent.hp_max`
      est un champ FIGE que les stat-mods HEALTH ne relevent pas (#572-r1) -> la branche HEALTH de
      `ChangeStat` ne clampe pas non plus, meme arbitrage qu'`UnbreakableDuty` (#572) et
      `NanoscarabRepairProtocols` (#902), qui portent le MEME couple [statmod] + [ChangeStat] ;
    * seul `AddEffect(1356)` est sous le gate de FACTION -- pas le +hp, qui va a n'importe quel
      allie ("If they are a Genestealer Cults unit, they **also** deal +extraDmg").

    ## Ecarts de forme ASSUMES (nommes, pas subis)

    * `HasEffect` natif porte `targetType = 6 = Both` ; le trigger porte du port passe deja
      `EffectTargetType.Both` en dur a `ctx.has_effect` -- meme valeur, non parametrable ;
    * `onlyActive = false` est THREADE (`active_only=False`) : c'est ce qui fait que le gate voit
      aussi une instance INACTIVE, comme le natif ;
    * le `selectionType = 3` de `HasFaction` et de `ChangeStat` n'a pas de substrat cote port (le
      trigger `HasFaction` prend la PREMIERE entite du selecteur, mirror de `SelectSingle`) ; sur un
      cast MONO-CIBLE dont la cible est vivante et ciblable par construction (le gate de cible l'a
      deja tranchee), les trois valeurs 0/1/3 coincident ;
    * `isHidden` / `isModifiable` / `isHiddenModification` sont tous FAUX au natif -> rien a porter."""
    extra_hp = twisted_science_extra_hp(state, caster_id)
    heal_amt = twisted_science_heal_amount(state, caster_id)
    # `turns = null` -> `duration_rounds=None` = aucun override de duree (`DefaultAmountOfRounds`).
    stat_mod = AddDynamicStatModifierEffect(Target(), Owner(), TWISTED_SCIENCE_EXTRA_HP,
                                            int(StatType.HEALTH),
                                            name=EffectType.TwistedScience_ExtraHp.name,
                                            duration_rounds=None)
    add_hp = ChangeStat(Target(), int(StatType.HEALTH), "add", _TS_HEAL_SOURCE, extra_hp)
    # `options = default(0)` -> aucun override de duree : l'effet de degat est PERMANENT ("until they
    # are defeated"). `scale_from_source=True` = l'`AbilityStateReference` natif : la magnitude se lit
    # au niveau/multiplicateur du CASTER, pas du buffe.
    add_dmg = AddEffect(TWISTED_SCIENCE_EXTRA_DMG, EffectType.TwistedScience_ExtraDmg.name,
                        Target(), duration_rounds=None, scale_from_source=True)
    is_gs = HasFaction(Target(), int(UnitFaction.Genestealers))
    cond = TriggerAnd(Not(HasEffect(Target(), TWISTED_SCIENCE_EXTRA_HP, active_only=False)),
                      Not(OwnerIsTarget()))
    buffs = op_add(op_add(stat_mod, add_hp), If(is_gs, add_dmg))
    heal = Heal(Target(), heal_amt, guard=None, scope=0, remove_effects=True)   # `ForHeal()`
    return op_add(If(cond, buffs), heal)


class TwistedScience_HealAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TwistedScience_HealAbility`
    (`ActiveAbilityType.Heal_TwistedScience` = 0x48f = 1167) -- le soin de `genesBiophagus` "Hollan".

    ⚠ LE NOM DE L'ENUM ET CELUI DE LA CLASSE SONT INVERSES dans le build (`Heal_TwistedScience` vs
    `TwistedScience_HealAbility`) : chercher `TwistedScience_Heal` dans `ActiveAbilityType` ne rend
    rien. Meme piege deja documente pour le playbook (`case-419-r1-tr14-r5-r2-r1-r1-r1-r3`).

    Cette ability n'est PAS dans le kit gameconfig de l'unite : le passif `TwistedScience` la
    SUBSTITUE au `18 Heal` que le trait `Healer` accorde ([F1] ci-dessus). Elle n'a donc AUCUNE
    entree `units.abilities` -> `ABILITY_ID = None`, comme `RepairAbility` (28) et pour la meme
    raison ; ses deux variables (`hp`, `extraDmg`) vivent dans la config du PASSIF.

    ⚠ CE QUE CETTE ENTREE AU REGISTRE NE FAIT PAS : porter le `18 Heal` GENERIQUE. Il reste absent
    d'`ABILITY_CLASSES` (comme `1212 HealingBalms_Heal`), donc un cast de 18 reste un no-op --
    residu #931-r1. Le couple est l'exact symetrique de `28 Repair` / `1119 Repair_GalvanicField`
    (#299), a ceci pres que la voie de specialisation est un SWAP DSL et non un heritage de classe :
    `TwistedScience_HealAbility` derive de `AActiveAbility`, pas de `Common.HealAbility`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Heal_TwistedScience)   # 0x48f = 1167
    ABILITY_ID = None

    # `...TwistedScience_HealAbility$$.ctor` -- FORME 1 "FLAGS DIRECTS" (surcharge SEPT arguments
    # `TargetingOptions..ctor(this, isSelfCasting, range, forceMeleeTarget, rules,
    # getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)`, celle qui ECRIT `rules` TEL
    # QUEL a `options+0x28` -- ni preset combine, ni copie statique) :
    #
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x00, 2, 0x8402, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x00 = RANGE_ADJACENT_IF_MELEE_CASTER
    #                        (`onlyAdjacent = 3 = IfNotRangedCaster`, rien d'autre) -- LU dans
    #                        `IdunBattle.Core.Services.TargetingRange$$.cctor`, ou le premier
    #                        `TargetingRange` statique s'ecrit `*puVar1 = 3` puis deux qwords nuls.
    #                        ⚠ CE N'EST PAS `RANGE_ADJACENT` (statics+0x30), celui de `RepairAbility` :
    #                        Hollan porte une arme de melee, donc les deux coincident SUR LUI, mais
    #                        les deux constantes sont distinctes et se lisent, pas se recopient.
    #     forceMeleeTarget = 2 = RangedBool.IfRangedCaster
    #     rules            = 0x8402
    #   puis `AActiveAbility..ctor(this, &opts, 2)` -> `AbilityAttackType.Others`.
    #
    # Decomposition du masque (`IdunBattle.Core.Services.TargetingRule`, bit a bit, RESTE = 0) :
    #     0x0002  TargetMatchesDynamicRule  -> tout le refus reel vit dans la regle DYNAMIQUE
    #     0x0400  TargetIsFriendly          -> une cible ENNEMIE est refusee
    #     0x8000  CasterIsPossibleTarget    -> Hollan PEUT se cibler lui-meme (et le natif le soigne
    #                                          alors sans le buffer : c'est le `!OwnerIsTarget` de
    #                                          l'arbre, pas un refus de ciblage)
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsFriendly | TR.CasterIsPossibleTarget),
        self_cast=False, range=RANGE_ADJACENT_IF_MELEE_CASTER,
        force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ents = entities_from_state(state, caster_id, int(target_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        twisted_science_heal_tree(state, caster_id).execute(ents, ectx)
        posed = [{"target": p["target"], "effect_type": p["effect_type"], "placed": p["placed"]}
                 for n, p in ectx.emitted if n in ("AddEffect", "AddDynamicStatModifierEffect")]
        filled = next((p for n, p in ectx.emitted if n == "ChangeStat"), None)
        healed = next((p for n, p in ectx.emitted if n == "Heal"), None)
        return {"ability": "Heal_TwistedScience", "caster": caster_id, "target": target_id,
                "extra_hp": twisted_science_extra_hp(state, caster_id),
                "effects": posed, "hp_fill": filled, "heal": healed, "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...TwistedScience_HealAbility$$GetDynamicInvalidTargetReason` -- MIRROR verbatim :

            if (!UnitExtensions.IsAffectedByHealType(target, 0 = NonMechanical))  return 0x100;
            if (caster == target) {
                ok = attackQuery.<slot 0x11>(caster, target, 0, true);
            } else {
                if (UnitExtensions.IsEnemy(target, caster, state))                return 0x400;
                if (!EntityExtensions.HasEffect(target, state, 0x54b, onlyActive: null)) return 0;
                ok = attackQuery.<slot 0x11>(caster, target, 0, true);
            }
            return ok ? 0 : 0x100;

        Le slot `0x11` est `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed(caster, target,
        scope, removeEffects)` -- LU dans `metadata/interface_slots.tsv` (`IAttackQuery` 17, 4
        arguments), et non deduit de son voisin `0x12 EntityCanBeRepaired` qu'utilise
        `RepairAbility`. `0x100` = `TargetingRule.TargetIsHealable`, `0x400` = `TargetIsFriendly`.

        ## LA CLAUSE QUI FAIT TOUT L'INTERET DE CE GATE

        `if (!HasEffect(target, 1355)) return 0;` -- une cible ALLIEE **non encore marquee** est
        VALIDE sans passer par `EntityCanBeHealed`, donc **meme a PV pleins**. C'est exactement
        l'i2 : "Hollan can heal other unaffected units even if they are at full Health". Une cible
        deja marquee, elle, retombe sur le gate de soin ordinaire (il faut qu'elle soit blessee, ou
        qu'elle porte un effet negatif que `removeEffects = true` justifierait de purger).

        Le premier test (`IsAffectedByHealType(target, 0)`) precede TOUT, y compris le test de camp :
        un ennemi MECANIQUE est refuse en `0x100`, pas en `0x400`. L'ordre est conserve.

        `onlyActive = null` -> le natif ne consulte PAS `EffectComponent.IsActive @+0x5c` : le
        mirror est `components.has_effect_of_type` (qui ne filtre que `consumed`), surtout PAS
        `ctx.has_effect`, dont le defaut `active_only=True` appellerait `BaseEffect.is_active`.
        Meme arbitrage que `NanoscarabRepairProtocolsAbility` (#902).

        `target == null` -> le natif deref `target` des la premiere ligne ; le port rend `0`
        (le gate generique a deja ecarte ce cas)."""
        if target_id is None:
            return 0
        tid, cid = int(target_id), int(caster_id)
        if not is_affected_by_heal_type(state, tid, 0):        # HealType.NonMechanical
            return int(TR.TargetIsHealable)
        if tid != cid:
            if units_are_enemies(state, tid, cid):
                return int(TR.TargetIsFriendly)
            if not has_effect_of_type(state, tid, TWISTED_SCIENCE_EXTRA_HP):
                return 0                                       # non marquee -> valide MEME a PV pleins
        ok = entity_can_be_healed(state, cid, tid, scope=0, remove_effects=True)
        return 0 if ok else int(TR.TargetIsHealable)
