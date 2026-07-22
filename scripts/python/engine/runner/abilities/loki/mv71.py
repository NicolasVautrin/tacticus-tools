"""MV71SniperDroneSquadAttack (1076) — l'attaque NORMALE de Sho'syl (`tauMarksman`) : invoque un
MV71 Sniper Drone qui attaque la cible à sa place (#61bis).

Namespace natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility`
(`.ctor @18110b330` = `ALoki_NormalAttackAbility..ctor(this, CustomLokiNormalAttackOptions(2), 1, 0)` —
c'est l'attaque normale PER-UNIT de Sho'syl, confirmé live : `decisionView` la liste kind="normal").
Config = l'entrée gameconfig **`MV71SniperDroneSquad`** (le passif 1119) : constants
`{unitId: tauSmnDroneSniper, maxSummons: 3}`, variables `summonHp/summonDmg/summonArmor`
(GT lvl50 mult180 → 1996/2093/499, EXACT — case-61bis §2).

`ExecuteBehaviour @181108900` (mirror 1:1, décompilé re-lu 2026-07-22) :
    if IsMeleeAttack(@181109960) -> ALoki_NormalAttackAbility.ExecuteBehaviour ; RETURN
    tile = PickTile(@181109ac0, firstOnly=0) ; null -> RETURN (no-op)
    (a) if HasUnitId(tile, unitId) : Execute( RemoveUnit(Units(Get(tile),1,3)) )
    (b) if HasToManySummons(@181109870) : Execute( RemoveUnit(First(AlreadySpawnedSummonsSorted,1,0)) )
    (c) spawned = Execute( Spawn(caster@0x160, Get(tile), Get(unitId),
                                 SpawnUnitOptions.WithStatsFromConfig(cfg@0x60, msg, 0,0,0)) )
    (d) foreach drone in spawned :
            AddEffect(0x46c=1132 InitialDmg, stateRef, Get(drone))       # OVERRIDE 4 stats du parent
            AddEffect(0x46d=1133 ResetInitialDmg, stateRef, Get(drone))
            UseActiveAbility(Alive(Get(drone)), target@0x178, GetNormalAttackType(drone),
                             Nullable<AbilityOrEffect>(this+0x10=1076) x2)   # attribution 1076
    (e) AddEffect(0x462=1122 Markerlight, stateRef, caster@0x160, target@0x178,
                  Sum(TurnsFromRounds(1), Direct(1)))   # fin du prochain tour du caster

`PickTile @181109ac0` : candidates = tuiles autour des TUILES DE LA CIBLE selon la config du drone
(service slot 0x66 x slot 0xaa(unitId) — portée d'attaque du drone), filtrées `CanAddUnit` &
`!IsTilePendingDrafting` & « peut attaquer les tuiles de la cible depuis » (slot 0xc3) ; puis
`SortTilesByUtility(list, [UtilityBucket[WeightedUtility(7=Tile), WeightedUtility(0x37=
MV71SniperDroneSquad_ClosestToParent)]], Self@0x148)` -> First. `firstOnly` -> 1er candidat brut
(le gate de `GetDynamicInvalidTargetReason @181109630` : la SEULE condition dynamique — H53 infirmée,
aucune portée minimale). FALLBACK (seulement au cap) : la tuile du drone le plus faible si à portée
de la cible, non obscurcie, tir possible — d'où l'éviction (a).

COLLAPSES documentés (doctrine FinalJustice, tri d'utilité impératif) :
  - tri = `ClosestToParent` (distance hex au caster ; natif = MovementInSteps @1810eff90, == dist hex
    sur board ouvert) ; `WeightedUtility(7=Tile)` traité CONSTANT sur terrain uniforme (flag) ;
    tie-break = (dist hex à la cible, id de tuile) — À CONFRONTER live (GT (3,4)/(4,3)/(5,4)).
  - « peut attaquer depuis » = distance <= portée max d'arme du drone ; LoS (`UnobscuredTiles`) NON
    portée (flag — board MC1_67 ouvert).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC
import hexgeo

from ..base import ActiveAbility, turns_from_rounds
from ...components import (StatsComponent, OwnerComponent, PositionComponent, UnitComponent,
                           HealthComponent)
from ...operations.damage import AttackDamageOperation
from ...operations.effects import AddEffectOperation
from ...operations.spawn import _spawn_config_grot, _occupied_tiles
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effect_type import EffectType
from ....services.battle_query import are_tiles_adjacent

if TYPE_CHECKING:
    from ...state import State

INITIAL_DMG = int(EffectType.MV71SniperDroneSquad_InitialDmg)          # 1132 = 0x46c
RESET_INITIAL_DMG = int(EffectType.MV71SniperDroneSquad_ResetInitialDmg)   # 1133 = 0x46d
MARKERLIGHT = int(EffectType.Markerlight)                              # 1122 = 0x462
CONFIG = "MV71SniperDroneSquad"    # l'entrée gameconfig qui porte constants/variables (le passif 1119)


def _drone_attack_range(unit_id: str) -> int:
    """Portée d'attaque max du drone (mirror de la config d'unité résolue par le service slot 0xaa) :
    max(Range des armes) ; armes mêlée seules -> 1."""
    ranges = [int(w.get("Range") or 0) for w in ((GC.unit(unit_id) or {}).get("weapons") or [])]
    mx = max(ranges) if ranges else 0
    return mx if mx > 0 else 1


def _friendly_drones(state: "State", team, unit_id: str) -> list:
    """`AlreadySpawnedSummonsSortedSelector @1811087e0` = `SortByFormula(UnitsWithId(Friends(Self),
    unitId), StatAmount(Subject, 5=HEALTH), dir=1)` : drones amis VIVANTS tries par PV CROISSANTS
    (le plus faible en tete -> `First(sel,1,0)` = l'evince du cap). Tie-break id (ordre de lecture)."""
    out = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        hc = e.get_component(HealthComponent)
        if uc is None or oc is None or not uc.alive or uc.visual_id != unit_id or oc.team != team:
            continue
        out.append((int(hc.hp) if hc is not None and hc.hp is not None else 0, eid))
    return [eid for _, eid in sorted(out)]


_WT = None    # cache module du Weights BC (statique par bataille, comme magnitude._BC_EFFECT_CFG)


def _wt():
    global _WT
    if _WT is None:
        from ....weights import load
        _WT = load()
    return _WT


# Catégorie BC de l'utilité 0x37 (⚠ deux sous-clés portent le TYPO NATIF « DDrone » — copie exacte).
_W_CAT = "MV71SniperDroneSquad_ClosestToParent"
STRUCTURAL_ANALYSER = 0x477       # 1143 (triggered) — bonus InRangeOfStructuralAnalyser
DEFENDER_OF_THE_GREATER_GOOD = 0x483   # 1155 (triggered) — bonus InRangeOfDefenderOfTheGreaterGood
SAVIOR_PROTOCOLS = 0x460          # 1120 (triggered) — gate CanBeProtector (= T'au ET PAS 1120)


def _adjacent_occupants(state: "State", board, tid: int):
    """Unites VIVANTES positionnees sur les tuiles ADJACENTES a `tid` : [(entity, team, visual_id)]."""
    npos = {(board.by_id[n]["col"], board.by_id[n]["row"])
            for n in board.neighbours(tid) if n in board.by_id}
    out = []
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if uc is None or oc is None or pc is None or not uc.alive:
            continue
        if (pc.col, pc.row) in npos:
            out.append((e, oc.team, uc.visual_id))
    return out


def _spawn_tile_utility_0x37(state: "State", board, tid: int, pos, cpos, caster_team) -> float:
    """`MV71SniperDroneSquad_SpawnTileUtility.EvaluateMovementInSteps` (`<d__5>.MoveNext @181100f60`,
    poids BC catégorie `MV71SniperDroneSquad_ClosestToParent`) :
        u  = Fix64(-steps(candidate, tuile du PARENT)) x W[AdjacentToParent]            (=50/pas)
        si AUCUN ennemi adjacent au candidat : u += W[NoAdjacentEnemy]                  (=40)
        pour chaque AMI adjacent :
            (gate « aucun ennemi adjacent ») ami a StructuralAnalyser(0x477)  -> +W[InRangeOfStructuralAnalyser] (=3)
            (gate idem)                     ami a DefenderOfTheGreaterGood(0x483) -> +W[InRangeOf...GreaterGood] (=25)
            `CanBeProtector @1810e0a50` (= HasFaction(9=T'au) ET PAS SaviorProtocols 0x460) -> +W[AdjacentToTau] (=20)
    `steps` = slot service 0x6b(parentTile, candidate) — port : distance hex (== pas sur board ouvert
    sans mur ; flag si un board a des obstacles)."""
    from ....entities.triggered_ability_type import triggered_ability_ids
    from ....ai.action_generators import _faction
    wt = _wt()
    u = -hexgeo.distance(pos, cpos) * wt.sub(_W_CAT, "MV71SniperDroneSquad_AdjacentToParent")
    adj = _adjacent_occupants(state, board, tid)
    enemies_adj = [x for x in adj if x[1] != caster_team]
    friends_adj = [x for x in adj if x[1] == caster_team]
    if not enemies_adj:
        u += wt.sub(_W_CAT, "MV71SniperDroneSquad_NoAdjacentEnemy")
    for _e, _team, vis in friends_adj:
        trig = set(triggered_ability_ids(vis) or ())
        if not enemies_adj:
            if STRUCTURAL_ANALYSER in trig:
                u += wt.sub(_W_CAT, "MV71SniperDDroneSquad_InRangeOfStructuralAnalyser")
            if DEFENDER_OF_THE_GREATER_GOOD in trig:
                u += wt.sub(_W_CAT, "MV71SniperDDroneSquad_InRangeOfDefenderOfTheGreaterGood")
        if _faction(vis) == "Tau" and SAVIOR_PROTOCOLS not in trig:   # CanBeProtector @1810e0a50
            u += wt.sub(_W_CAT, "MV71SniperDroneSquad_AdjacentToTau")
    return float(u)


def _tile7_utility(state: "State", board, tid: int, pos, unit_id: str, caster_team,
                   elev_minmax) -> float:
    """Terme `WeightedUtility(7 = Tile)` du bucket — le composite Tile(7) PORTÉ (`utilities/tile.py`,
    29 feuilles), évalué pour le DRONE-TEST (`TestUnitProvider` natif : l'unité évaluée = le drone qui
    serait posé). Meta runner-side : élévation (min/max BOARD ENTIER), effets DYNAMIQUES de la tuile
    (state.effects, keyés par tile id) + covers hébergés par le TERRAIN, counts d'amis adjacents par
    triggered-ability (leaves 20/21/22). leaf_ctx du drone : kit déclenché (SaviorProtocols 1120 —
    LoadPlaybook(1120) natif = null -> dispatcher(2) à 0), faction T'au (9), arme ranged."""
    from ....utilities.tile import tile_composite, terrain_tile_effects
    from ....entities.triggered_ability_type import triggered_ability_ids
    meta: dict = {}
    info = board.by_id.get(tid) or {}
    elev = info.get("elevation")
    if elev is not None:
        meta = {"elevation": elev, "elevation_max": elev_minmax[1], "elevation_min": elev_minmax[0]}
    effs = []
    if state.effects is not None:                       # effets dynamiques poses SUR la tuile (Fire/Ice…)
        effs += [e.name for e in state.effects.by_unit.get(int(tid), [])
                 if not e.consumed and e.name]
    effs += terrain_tile_effects(board.terrain_at(pos[0], pos[1]))   # covers heberges (DryBush->LightCover)
    if effs:
        meta["effects"] = effs
    counts: dict = {}
    for _e, _team, vis in _adjacent_occupants(state, board, tid):
        if _team != caster_team:
            continue
        for ab in (triggered_ability_ids(vis) or ()):
            if ab in (1102, 1155, 1120):
                counts[ab] = counts.get(ab, 0) + 1
    if counts:
        meta["ability_friend_counts"] = counts
    ctx = {"unit_triggered_abilities": list(triggered_ability_ids(unit_id) or ()),
           "unit_faction": 9,                          # UnitFaction.Tau (le drone-test)
           "unit_has_ranged_weapon": True,
           "friend_positions": []}
    return float(tile_composite(pos, meta, ctx, _wt()))


def _pick_tile(state: "State", caster_id: int, target_id: int, unit_id: str,
               max_summons: int, first_only: bool = False):
    """`PickTile @181109ac0` : renvoie l'id de TUILE choisie, ou None (aucune tuile -> cast no-op,
    le gate de `GetDynamicInvalidTargetReason @181109630`).

    Candidates = tuiles MARCHABLES et LIBRES à distance <= portée du drone de LA CIBLE (slot 0x66 x
    config drone), d'où le drone peut attaquer (collapse distance ; LoS `UnobscuredTiles` non portée,
    flag). Tri = `SortTilesByUtility(list, [UtilityBucket[WeightedUtility(7=Tile),
    WeightedUtility(0x37=ClosestToParent)]])` -> First : score = Tile(7) porté + utilité 0x37
    (`_spawn_tile_utility_0x37`), max premier, tie-break stable = ordre des candidats (id de tuile
    croissant — l'énumération native slot 0x66 n'est pas RE'd, à confronter live). FALLBACK (au cap
    uniquement, mirror du bloc HasToManySummons du natif) : la tuile du drone le plus FAIBLE si elle
    est à portée de la cible (-> éviction (a) au call-site)."""
    board = state.board
    ce = state.get_entity(caster_id)
    te = state.get_entity(target_id)
    cp = ce.get_component(PositionComponent) if ce is not None else None
    tp = te.get_component(PositionComponent) if te is not None else None
    coc = ce.get_component(OwnerComponent) if ce is not None else None
    if board is None or cp is None or tp is None or coc is None:
        return None
    rng = _drone_attack_range(unit_id)
    tpos = (tp.col, tp.row)
    cpos = (cp.col, cp.row)
    occupied = _occupied_tiles(state)
    cands = []
    for tid in sorted(board.by_id.keys()):
        if not board.walkable(tid) or tid in occupied:      # CanAddUnit (libre + marchable)
            continue
        info = board.by_id[tid]
        pos = (info["col"], info["row"])
        d_t = hexgeo.distance(pos, tpos)
        if d_t < 1 or d_t > rng:                            # « peut attaquer la cible depuis » (portée)
            continue
        cands.append((tid, pos))
    if cands:
        if first_only:
            return cands[0][0]                              # gate GetDynamicInvalidTargetReason (1er candidat)
        elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
        emm = (min(elevs), max(elevs)) if elevs else (None, None)
        best_tid, best_u = None, None
        for tid, pos in cands:                              # max stable (ordre des candidats au tie)
            u = (_tile7_utility(state, board, tid, pos, unit_id, coc.team, emm)
                 + _spawn_tile_utility_0x37(state, board, tid, pos, cpos, coc.team))
            if best_u is None or u > best_u:
                best_tid, best_u = tid, u
        return best_tid
    # FALLBACK natif : uniquement si le cap est atteint — tuile du drone le plus faible, si à portée.
    ce_oc = ce.get_component(OwnerComponent)
    drones = _friendly_drones(state, ce_oc.team if ce_oc is not None else None, unit_id)
    if len(drones) < max_summons or not drones:
        return None
    we = state.get_entity(drones[0])
    wp = we.get_component(PositionComponent) if we is not None else None
    if wp is None:
        return None
    d_t = hexgeo.distance((wp.col, wp.row), tpos)
    if d_t < 1 or d_t > rng:
        return None
    return board.id_at(wp.col, wp.row)


class MV71SniperDroneSquadAttackAbility(ActiveAbility):
    """`MV71SniperDroneSquadAttackAbility.ExecuteBehaviour @181108900` (id **1076**) — cf. docstring
    module pour la chaîne native complète et les collapses. GROUND TRUTH live : case-61bis §2 (runner
    88, seed 61001 : dégât −9391, drone (3,4) adjacent caster, stats 1996/499/2093, Markerlight posé,
    1132/1133 absents post-cast)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MV71SniperDroneSquadAttack)   # 1076

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ce = state.get_entity(caster_id)
        te = state.get_entity(target_id)
        cp = ce.get_component(PositionComponent) if ce is not None else None
        tp = te.get_component(PositionComponent) if te is not None else None
        if ce is None or te is None or cp is None or tp is None:
            return None
        # --- dispatch mêlée : `IsMeleeAttack @181109960` (cible adjacente) -> délégation TOTALE à
        # l'attaque normale (`ALoki_NormalAttackAbility.ExecuteBehaviour`) — exécution == le pipeline
        # d'attaque normale du port (AttackDamageOperation + after-hit, mirror DamageHandler). H53
        # infirmée : c'est un dispatch, pas un refus de cible.
        if are_tiles_adjacent((cp.col, cp.row), (tp.col, tp.row), state.board):
            atk = AttackDamageOperation.execute(state, caster_id, target_id)
            after = []
            if atk is not None:
                from ...operations.triggers import after_hit_normal_attack
                after = after_hit_normal_attack(state, caster_id, target_id,
                                                bool(atk.get("ranged")), atk.get("profile"),
                                                is_crit=bool(atk.get("did_crit")))
            return {"melee": True, "attack": atk, "after_hit": after}

        consts = (GC.ability(CONFIG) or {}).get("constants") or {}
        unit_id = consts.get("unitId")                       # GetStringConstant(cfg, 0) = tauSmnDroneSniper
        max_summons = int(consts.get("maxSummons") or 3)     # GetNumberConstant(cfg, 0x3c) = 3
        if unit_id is None:
            return None
        coc = ce.get_component(OwnerComponent)
        csc = ce.get_component(StatsComponent)
        cctx = csc.ctx if csc is not None else None
        if coc is None or cctx is None:
            return None

        # --- PickTile (null -> no-op, seul gate dynamique) ---
        tile = _pick_tile(state, caster_id, target_id, unit_id, max_summons)
        if tile is None:
            return {"melee": False, "tile": None, "spawned": []}
        board = state.board
        tinfo = board.by_id.get(tile) or {}

        evicted: list = []

        def _remove(uid: int) -> None:
            # RemoveUnitBehaviour.Execute @180fce1d0 : despawn SANS vecteur on-death (cf. feuille
            # `RemoveUnit` behaviours.py — même mutation, inline ici car sélecteur déjà résolu).
            e = state.get_entity(uid)
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is not None and uc.alive:
                uc.alive = False
                if state.effects is not None:
                    for eff in state.effects.by_unit.get(int(uid), []):
                        eff.consumed = True
                evicted.append(uid)

        # (a) la tuile choisie porte déjà un drone (fallback) -> RemoveUnit(Units(Get(tile),1,3))
        for eid, e in list(state.entities.items()):
            uc = e.get_component(UnitComponent)
            pc = e.get_component(PositionComponent)
            if (uc is not None and uc.alive and uc.visual_id == unit_id and pc is not None
                    and board.id_at(pc.col, pc.row) == tile):
                _remove(eid)
        # (b) cap maxSummons -> RemoveUnit(First(AlreadySpawnedSummonsSorted,1,0)) = le plus faible
        drones = _friendly_drones(state, coc.team, unit_id)
        if len(drones) >= max_summons:
            _remove(drones[0])

        # (c) Spawn WithStatsFromConfig(cfg) : stats summon* du niveau du caster. L'ability 1076 dérive
        # du PASSIF 1119 (namespace Triggered) -> niveau passif d'abord, fallback actif (GT 50/180).
        level = getattr(cctx, "passive_ability_level", None)
        if level is None:
            level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        drone_id = _spawn_config_grot(state, unit_id, tile, CONFIG, level, mult,
                                      coc.team, coc.player)
        if drone_id is None:
            return {"melee": False, "tile": None, "spawned": [], "evicted": evicted}

        # (d) par drone : AddEffect 1132 (OVERRIDE 4 stats <- CURRENT du parent, snapshot à l'apply)
        # + AddEffect 1133, puis UseActiveAbility(GetNormalAttackType(drone), attribution 1076).
        eff_1132 = AddEffectOperation.execute(state, source=caster_id, target=drone_id,
                                              effect_type=INITIAL_DMG,
                                              name="MV71SniperDroneSquad_InitialDmg")
        AddEffectOperation.execute(state, source=caster_id, target=drone_id,
                                   effect_type=RESET_INITIAL_DMG,
                                   name="MV71SniperDroneSquad_ResetInitialDmg")
        # l'attaque COMMANDÉE : l'attaque normale DU DRONE (arme choisie par distance — r4 Piercing à
        # distance, Physical au contact), stats lues via GetStat -> les OVERRIDES s'appliquent.
        atk = AttackDamageOperation.execute(state, drone_id, target_id)
        # TargetTrigger `On(AttackDamageAttack=10,1) & OwnerIsCaster` (@180f575c0) : le drone vient
        # d'attaquer -> 1132 (RevertInternal @180f577d0 = REMOVE_OVERRIDE x4) et 1133 sont retirés
        # (GT : seuls les owner-effects de traits restent post-cast). Collapse : ce cast contient le
        # SEUL On(10) du porteur atteignable ; un drone qui n'attaque pas garderait l'effet jusqu'à sa
        # prochaine attaque (résidu flaggé : la consommation n'est pas câblée aux attaques AI-turn).
        if state.effects is not None:
            for eff in state.effects.by_unit.get(int(drone_id), []):
                if eff.consumed or eff.effect_type not in (INITIAL_DMG, RESET_INITIAL_DMG):
                    continue
                if eff.effect_type == INITIAL_DMG:
                    AddEffectOperation.revert_stat_overrides(state, drone_id, eff)
                eff.consumed = True
        # le drone finit son tour immédiatement (GT tag UnitStats_TurnFinished=1) — même queue
        # AddFlagsAfterAbilityExecution que toute ability exécutée (ici pour le DRONE).
        from ...operations.turnflow import add_flags_after_ability_execution
        drone_flags = add_flags_after_ability_execution(state, drone_id,
                                                        skip_ability_used=False, skip_end_turn=False)

        # (e) Markerlight sur la CIBLE, durée Sum(TurnsFromRounds(1), Direct(1)) = fin du prochain
        # tour du caster (identique StructuralAnalyser @1811a2a00).
        ml = AddEffectOperation.execute(state, source=caster_id, target=target_id,
                                        effect_type=MARKERLIGHT, name="Markerlight",
                                        duration_override=turns_from_rounds(1) + 1)
        return {"melee": False, "tile": (tinfo.get("col"), tinfo.get("row")), "spawned": [drone_id],
                "evicted": evicted, "attack": atk, "markerlight": ml is not None,
                "overrides_applied": bool(eff_1132), "drone_flags": drone_flags}
