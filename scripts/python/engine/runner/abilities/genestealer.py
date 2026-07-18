"""Abilities Genestealer Cults (Isaak `genesPrimus` / Judh `genesKelermorph`) — chantier gen-stealer.

Module DÉDIÉ : `behaviours.py` et `loki.py` (abilities) sont déjà > 1000 lignes (seuil de split), et le
chantier gen-stealer regroupe plusieurs slices partageant les feuilles de decoy (G4 CultDemagogue ici ; G6
HypersensoryAbilities réutilisera `SpawnDecoys`). Org native = 1 classe par ability (`Abilities.Active.*`) ;
les arbres SPÉCIFIQUES vivent avec leur ability. RE ghidra gqfc5mff6c (VA citées). Doc : docs/rl/genestealer-cults.md.

Arbre CultDemagogue (`CultDemagogueAbility$$ExecuteBehaviour @1811cdc30`, mirror op_Addition 3 étages) :
    op_add( SpawnDecoys , op_add( SpawnNeophytesOnDecoys , PerformAINeophyteTurn ) )
Sélecteurs AI/tuile LOURDS (S) COLLAPSÉS (doctrine slice-18/19/22/23/24) : résolus impérativement dans
chaque feuille au moment de l'exécution (data-dep : les neophytes lisent les decoys fraîchement posés).
"""
from __future__ import annotations

import math
from typing import Optional, TYPE_CHECKING

from ...dsl.base import resolve_unit
from ...dsl.effects import AbilityBehaviour, OperationResult, ExecutionContext
from ...entities.behaviours import op_add
from ...entities.selectors import Target
from ...entities.traits.unit_trait import UnitTrait, has_trait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import OwnerComponent, PositionComponent, UnitComponent, StatsComponent
from ..operations.spawn import spawn_decoy, _spawn_config_grot
from ..operations.summon_ai import decide_and_apply
from .base import ActiveAbility
from .behaviours import entities_from_state
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
    genesSmnDecoy, ForSteppable )` @1811cdc30. Pose `n` decoys inertes sur des tuiles libres aléatoires ≤`range`
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
                ectx.emit("SpawnDecoy", unit=did, tile=t)
        return OperationResult.ok()


class SpawnNeophytesOnDecoys(AbilityBehaviour):
    """2e étage : `Spawn( Tiles(PickRandomly(Half(Count(FriendlyDecoysAroundTarget)))), genesSmnNeophyte,
    WithStatsFromConfig )` @1811cdc30. Sur la MOITIÉ (ceil — `DivideAmount mode1=Ceiling @180f19800`) des decoys
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
                ectx.emit("SpawnNeophyte", unit=nid, tile=tile, on_decoy=did)
        return OperationResult.ok()


class PerformAINeophyteTurn(AbilityBehaviour):
    """3e étage : `PerformAIAction(FriendlyNeophytesAroundTarget, 0, 1)` @1811cdc30 -> `PerformAIActionBehaviour
    .Execute @180fcba10`. Chaque Neophyte fraîchement summon dans le disk `range` autour de la cible joue un
    TOUR AI COMPLET (move + attaque via playbook), PAS une simple attaque (re-expert Q4 : le Neophyte a move=3
    + Ambush -> il DOIT bouger). -> `decide_and_apply` par neophyte. Effet PUR."""
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
        radius = int(ability_var(self.ability_id, "range", is_constant=True) or 2)
        neophyte_vid = _const(self.ability_id, "unitId_2")
        tpos = _pos_of(state, target_id)
        for nid in _friendly_units_around(state, tpos, radius, coc.team, neophyte_vid):
            e = state.get_entity(nid)
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is None or not uc.alive:              # un tour précédent (overwatch) a pu le tuer
                continue
            res = decide_and_apply(state, nid)
            ectx.emit("NeophyteTurn", unit=nid, result=res)
        return OperationResult.ok()


def _const(ability_id: str, key: str):
    import gameconfig as GC
    return ((GC.ability(ability_id) or {}).get("constants") or {}).get(key)


def cult_demagogue_tree(target_ref=None):
    """Mirror `CultDemagogueAbility$$ExecuteBehaviour @1811cdc30` : `op_add(SpawnDecoys, op_add(
    SpawnNeophytesOnDecoys, PerformAINeophyteTurn))` (les `Group(id=100/101)` natifs = ordonnancement, no-op
    observable ici). Cible ennemie = `Target()@0x178` collapsé (doctrine slice-24)."""
    tr = target_ref if target_ref is not None else Target()
    return op_add(SpawnDecoys(tr), op_add(SpawnNeophytesOnDecoys(tr), PerformAINeophyteTurn(tr)))


class CultDemagogueAbility(ActiveAbility):
    """`CultDemagogueAbility$$ExecuteBehaviour @1811cdc30` (id 1179, Isaak genesPrimus). Arbre DSL
    `cult_demagogue_tree()` : (1) pose N=`nrOfSummons` decoys ≤range de la cible ; (2) summon des Neophytes sur
    ceil(moitié) des decoys alliés de la zone (stats config `summon*_2`) ; (3) chaque Neophyte joue un tour AI
    complet immédiat. Sélecteurs S collapsés. Renvoie {decoys, neophytes, turns, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CultDemagogue)  # 1179

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        cult_demagogue_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        decoys = [p["unit"] for n, p in ectx.emitted if n == "SpawnDecoy"]
        neophytes = [p["unit"] for n, p in ectx.emitted if n == "SpawnNeophyte"]
        turns = [p for n, p in ectx.emitted if n == "NeophyteTurn"]
        return {"decoys": decoys, "neophytes": neophytes, "turns": turns, "dsl": True}
