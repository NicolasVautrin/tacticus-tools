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

from ...dsl.base import resolve_unit, Const
from ...dsl.effects import AbilityBehaviour, OperationResult, ExecutionContext
from ...entities.behaviours import op_add, op_and, If
from ...entities.selectors import (Target, Caster, TargetTile, FixedTiles, Alive, SurroundingEnemies,
                                   Union)
from ...entities.triggers import Not, IsAlive, IsSurrounding, IsAdjacent, TriggerAnd
from ...entities.traits.unit_trait import UnitTrait, has_trait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.stats import StatType
from ...entities.effects.magnitude import ability_var
from ...entities.pathfinding.walk_pathfinder import get_movable_positions
from ..components import OwnerComponent, PositionComponent, UnitComponent, StatsComponent
from ..operations.spawn import spawn_decoy, _spawn_config_grot
from ..operations.summon_ai import decide_and_apply
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage, MoveUnit, ChangeStat

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


# ============================ HeroicFusillade (Judh genesKelermorph, actif 1180) ============================
#
# "Surrounding radius" = le champ DslContext @+0xc0 (rayon d'ADJACENCE = 1, i2 « surrounding hex »),
# DISTINCT du `range` config (=2, `GetNumberConstant(0x16)`, = portee de MOUVEMENT `MovableTilesInRange`).
# Le natif @1811e8de0 lit @0xc0 (PAS `GetNumberConstant` -- contraste CultDemagogue @1811cdc30 qui passe
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


def _move_dest_tile(state: "State", caster_id: int, target_id: int, surround_radius: int, move_range: int):
    """COLLAPSE (doctrine slice-18/19/22) du selecteur de destination LOURD (kind S) de HeroicFusillade
    @1811e8de0 : `First(SortTilesByUtility( CanAddUnit(SurroundingTiles(target, radius))
    op_And MovableTilesInRange(caster, Direct(range), reachOnly), 7))`. Renvoie la (col,row) de la MEILLEURE
    tuile LIBRE `surround_radius`-adjacente a la cible que le caster peut ATTEINDRE en <= `move_range` pas
    de marche, ou None. `MovableTilesInRange` -> `walk_pathfinder.get_movable_positions` (BFS niveaux fidele,
    reachOnly = stop_set). `SortTilesByUtility` (selecteur AI lourd) COLLAPSE en : la plus PROCHE du caster
    (dist hex, tie-break tile id) -- proxy raisonnable de l'utilite (gap-closer landing adjacent). Pre-move
    (aucune mutation avant le MoveUnit dans l'arbre)."""
    board = state.board
    cpos = _pos_of(state, caster_id)
    tpos = _pos_of(state, target_id)
    if board is None or cpos is None or tpos is None:
        return None
    ctile = board.id_at(cpos[0], cpos[1])
    if ctile is None:
        return None
    _visited, stop = get_movable_positions(board, ctile, int(move_range),
                                           _living_occupants_map(state), _team_of(state, caster_id))
    adj_free = set(_surrounding_free_tiles(state, tpos, surround_radius))    # CanAddUnit(SurroundingTiles(target))
    cands = [t for t in adj_free if t in stop]                              # op_And MovableTilesInRange (reachOnly)
    if not cands:
        return None
    cands.sort(key=lambda t: (hexgeo.distance(cpos, board.coord(t)), t))    # SortTilesByUtility collapse
    return board.coord(cands[0])


def _hf_crit_mag(state: "State", caster_id: int, target_id: int, surround_radius: int) -> int:
    """`Multiply(Direct(GetVariableForLevel(0x42)=extraCritDmg), Count(Unobscured(CanAddUnit(
    SurroundingTiles(target, radius)))))` @1811e8de0 = `extraCritDmg[level] x nbFree`. `nbFree` = nb de
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
    """Mirror 1:1 de `HeroicFusilladeAbility$$ExecuteBehaviour @1811e8de0` :
        op_Addition(
          If( Not(IsSurrounding(caster@0x148, target@0x178, radius)), MoveUnit(caster, destTile) ),   # MOVE
          If( IsAlive(target),
              op_Addition( op_Addition(
                  ChangeStat(caster, CRIT_DAMAGE=10, mode=2=Add, mag),                                 # buff crit (pose)
                  AttackWithAttackDamage(caster, splash, MinMaxDamage, Projectile, GetHits=nrOfHits=6) ), # 6x splash
                  ChangeStat(caster, CRIT_DAMAGE=10, mode=3=Sub, mag) ) ) )                            # buff crit (retire)
    - MOVE : `Not(IsSurrounding(caster, target, radius=1))` = move SEULEMENT si la cible n'entoure pas deja
      le caster. dest = selecteur S lourd COLLAPSE (`_move_dest_tile`). MoveUnit options NULL (decompile
      `local_1b8..local_188 = 0`) -> AUCUN after-move crush/overwatch (feuille `MoveUnit` fidele, cf. tache
      #4 + ThunderousAssault ; le verdict re-expert « declenche crush/overwatch » etait imprecis, corrige au
      decompile).
    - SPLASH : natif `Unobscured(Enemies(SurroundingUnits(target, radius, includeCenter=1)))`. Le
      `includeCenter=1` (SurroundingUnits @180dfcb70 -> `SurroundingTiles(target, includeCenter=1, radius)`
      @180dfca70 = disk INCLUANT la tuile cible -- contraste MOVE `includeCenter=0` = ring exclu-centre) ->
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
    dest = _move_dest_tile(state, caster_id, target_id, surround_radius, move_range)
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
    """`HeroicFusilladeAbility$$ExecuteBehaviour @1811e8de0` (id 1180, Judh genesKelermorph, namespace natif
    `Abilities.Active.Loki`). Arbre DSL `heroic_fusillade_tree()` : (1) Judh MOVE sur une tuile libre
    adjacente a la cible atteignable en <= `range`=2 (sauf si deja adjacente) ; (2) 6x Projectile a la CIBLE
    + tous les ennemis l'entourant (splash cible-centre) ; (3) crit +extraCritDmg x nb de hex libres
    entourant la cible (buff CRIT_DAMAGE net-nul encadrant l'attaque). Selecteurs S (dest move, nbFree)
    collapses ; structure DSL. Renvoie {move, main_attack, splash, crit_bonus, dsl}.

    RE-ARME post-resurrection (`HeroicFusillade_ResurrectAbility$$CreateTrigger @180f86590` = On(0x2f=
    UnitResurrected) & OwnerIsTarget -> reset flag ability-used) = trigger SEPARE (tranche G3-Ambush /
    triggers), PAS dans l'ability active."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HeroicFusillade)  # 1180
    ABILITY_ID = "HeroicFusillade"

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


# ===================== VigilanceEternal (Tyrith custoKyrus, actif 1202) =====================
#
# `VigilanceEternalAbility$$ExecuteBehaviour @18122a580` (namespace natif `Abilities.Active.Loki`,
# Custodes -- HORS gen-stealer, mais REUTILISE le template de charge `_move_dest_tile` de HeroicFusillade
# defini ci-dessus, d'ou le voisinage). L'arbre est `HeroicFusillade @1811e8de0` EXACT, MOINS splash/crit :
#     op_BitwiseAnd(
#       If( Not(IsAdjacent(caster@0x160, target@0x178, 3)),                                  # MOVE gate
#           MoveUnit(caster, First(SortTilesByUtility(GetPossibleMovementTiles, 0x20))) ),   # charge-tile
#       If( IsAlive(caster@0x160) op_BitwiseAnd IsAlive(target@0x178),                       # ATTACK gate (2)
#           AttackWithAttackDamage(caster, target, MinMaxDamage, GetDamageProfile,           # mono-cible
#                                  GetNumberConstant(0x2f)=nrOfHits) ) )
# Differences avec HeroicFusillade (@1811e8de0), lues au decompile :
#  - MOVE gate = `Not(IsAdjacent(caster, target, 3))` (`IsAdjacent @180df2f00` -> `@180f9f7b0`) au lieu de
#    `Not(IsSurrounding(caster, target, radius=1))`. `IsAdjacent.ShouldTrigger` @180f9f7b0 : le predicat
#    par-paire = slot iface `0x5f` (bool `AreNeighbours(pos_a,pos_b)`, PAS `0x6e`=GetDistance d'`IsInRange`
#    @180fa1720) -> seuil dist==1 STRICT ; le `3` (champ +0x18) n'est PAS passe a `0x5f` -- il ne va qu'a
#    l'eval du selecteur (`FUN_180025220` param_5), INERTE pour les selecteurs d'unite Caster/Target. Donc
#    la gate = "bouge SAUF si deja adjacent (dist 1) a la cible", SEMANTIQUEMENT IDENTIQUE au move-gate
#    HeroicFusillade. Corrobore : (a) wiki Tyrith (« melee mobile ... cible un ennemi DEJA adjacent OU
#    ayant un hex libre adjacent dans la move range 2, gap-close sur cet hex ») ; (b) le node `IsAdjacent`
#    porte (dist==1, sans radius) ; (c) le precedent TheBetrayer @1811a4f70 (meme node IsAdjacent sous
#    op_LogicalNot pour gater un move). Le port reutilise le node dist==1 tel quel. [VALIDE LIVE : dist 2/3
#    -> gap-close ; dist 1 -> skip move.]
#  - ATTACK gate = `IsAlive(caster) op_BitwiseAnd IsAlive(target)` (les DEUX vivants) au lieu du seul
#    `IsAlive(target)` -- le caster peut mourir a un overwatch/counter pendant la charge (Tyrith melee).
#  - Attaque MONO-cible (`AttackWithAttackDamage(caster, target, ...)`, PAS de Union/SurroundingEnemies) ;
#    AUCUN buff crit (pas de ChangeStat encadrant). Profil = `GetDamageProfile` = "Power" (melee, pierce
#    40%) ; nrOfHits = `GetNumberConstant(0x2f)` = 3 ; bornes = `MinMaxDamage` = minDmg/maxDmg[level].
#  - Composition top-level = `op_BitwiseAnd` (CombinedBehaviour, == `op_add` : Seq court-circuit ; les deux
#    branches sont pures -> les deux s'executent).
# `GetPossibleMovementTiles @18122ae10` = `TilesUnitCanMoveToChargeTarget(caster@0x160, tile@0x168,
# target@0x190, Direct(GetNumberConstant(0x16)=range=2), canReachOnly=1)` @180dfda00
#   = `CanAddUnit(AdjacentTiles(target)) op_And MovableTilesInRange(caster, tile, Direct(range), reachOnly=1)`
#   == EXACTEMENT le collapse `_move_dest_tile` de HeroicFusillade avec surround_radius=1 (AdjacentTiles =
#   ring-1 = SurroundingTiles radius 1) + move_range=range=2. `SortTilesByUtility(0x20)` collapse -> tuile
#   la plus PROCHE du caster (meme proxy que HeroicFusillade ; gap-closer landing adjacent).
VIGIL_SURROUND_RADIUS = 1     # AdjacentTiles(target) = ring-1 (== SurroundingTiles radius 1)


def vigilance_eternal_tree(state: "State", caster_id: int, target_id: int, move_range: int):
    """Mirror 1:1 de `VigilanceEternalAbility$$ExecuteBehaviour @18122a580` (HeroicFusillade moins
    splash/crit) : `op_and(If(Not(IsAdjacent(caster,target)), MoveUnit(caster, destTile)),
    If(IsAlive(caster) & IsAlive(target), AttackWithAttackDamage(caster->target, Power, 3 hits)))`.
    dest = selecteur S lourd COLLAPSE (`_move_dest_tile`, surround_radius=1, move_range=`range`=2) PRE-move
    ; gate move = `Not(IsAdjacent)` (dist==1 : bouge sauf si deja adjacent) ; gate attaque = les deux
    vivants (re-eval LIVE apres le move -- Voie A, `LiveUnit`)."""
    dest = _move_dest_tile(state, caster_id, target_id, VIGIL_SURROUND_RADIUS, move_range)
    move = If(Not(IsAdjacent(Caster(), Target())),
              MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])))
    attack = AttackWithAttackDamage(Target(), "VigilanceEternal", "Power", is_melee=True)   # mono-cible
    attack_branch = If(TriggerAnd(IsAlive(Caster()), IsAlive(Target())), attack)
    return op_and(move, attack_branch)


class VigilanceEternalAbility(ActiveAbility):
    """`VigilanceEternalAbility$$ExecuteBehaviour @18122a580` (id 1202, Tyrith custoKyrus, namespace natif
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
        cc=0 (refute decompile : `DamagePrediction.RollCritical @1810387a0` gate `cc<1 -> false SANS tirage`,
        unique chemin crit d'`ExecuteHit @180e5eff0` ; la note damage.py "cc=0 => 0 tirage" reste VRAIE pour
        les DEUX vecteurs). Le 2e tirage/coup natif = le VECTEUR : AttackWithAttackDamage passe par le MEME
        `ExecuteHit` que l'attaque normale mais avec un struct NON degenere -> `HitDamage.GetDamage @181007bf0`
        tire la VALEUR BRUTE (1 tirage) PUIS `RandomlyResolveMinMaxDamage @181038600` (slot 8, SANS gate
        min==max) consomme 1 tirage GASPILLE sur la cellule degeneree. Fix : `_run_hits`/`_one_hit` branche
        post_roll (damage.py) ; valide bit-exact per-hit + consommation (6 tirages/3 coups) sur 5 seeds x 2
        cibles via probe_rngcrit_1202.py. L'ecart residuel +1/coup constate a ARMURE>0 (les deux vecteurs,
        p.ex. [918,903,1112] vs live [919,904,1113]) = gap de ROUNDING pierce/armure SEPARE, pre-existant."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.VigilanceEternal)  # 1202
    ABILITY_ID = "VigilanceEternal"

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
