"""MV71SniperDroneSquadAttack (1076) — l'attaque NORMALE de Sho'syl (`tauMarksman`) : invoque un
MV71 Sniper Drone qui attaque la cible à sa place (#61bis).

Namespace natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility`
(`.IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$.ctor` = `ALoki_NormalAttackAbility..ctor(this, CustomLokiNormalAttackOptions(2), 1, 0)` —
c'est l'attaque normale PER-UNIT de Sho'syl, confirmé live : `decisionView` la liste kind="normal").
Config = l'entrée gameconfig **`MV71SniperDroneSquad`** (le passif 1119) : constants
`{unitId: tauSmnDroneSniper, maxSummons: 3}`, variables `summonHp/summonDmg/summonArmor`
(GT lvl50 mult180 → 1996/2093/499, EXACT — case-61bis §2).

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` (mirror 1:1, décompilé re-lu 2026-07-22) :
    if IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$IsMeleeAttack -> ALoki_NormalAttackAbility.ExecuteBehaviour ; RETURN
    tile = PickTile(IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PickTile, firstOnly=0) ; null -> RETURN (no-op)
    (a) if HasUnitId(tile, unitId) : Execute( RemoveUnit(Units(Get(tile),1,3)) )
    (b) if IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$HasToManySummons : Execute( RemoveUnit(First(AlreadySpawnedSummonsSorted,1,0)) )
    (c) spawned = Execute( Spawn(caster@0x160, Get(tile), Get(unitId),
                                 SpawnUnitOptions.WithStatsFromConfig(cfg@0x60, msg, 0,0,0)) )
    (d) foreach drone in spawned :
            AddEffect(0x46c=1132 InitialDmg, stateRef, Get(drone))       # OVERRIDE 4 stats du parent
            AddEffect(0x46d=1133 ResetInitialDmg, stateRef, Get(drone))
            UseActiveAbility(Alive(Get(drone)), target@0x178, GetNormalAttackType(drone),
                             Nullable<AbilityOrEffect>(this+0x10=1076) x2)   # attribution 1076
    (e) AddEffect(0x462=1122 Markerlight, stateRef, caster@0x160, target@0x178,
                  Sum(TurnsFromRounds(1), Direct(1)))   # fin du prochain tour du caster

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PickTile` : candidates = tuiles autour des TUILES DE LA CIBLE selon la config du drone
(service slot 0x66 x slot 0xaa(unitId) — portée d'attaque du drone), filtrées `CanAddUnit` &
`!IsTilePendingDrafting` & « peut attaquer les tuiles de la cible depuis » (slot 0xc3) ; puis
`SortTilesByUtility(list, [UtilityBucket[WeightedUtility(7=Tile), WeightedUtility(0x37=
MV71SniperDroneSquad_ClosestToParent)]], Self@0x148)` -> First. `firstOnly` -> 1er candidat brut
(le gate de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason` : la SEULE condition dynamique — H53 infirmée,
aucune portée minimale). FALLBACK (seulement au cap) : la tuile du drone le plus faible si à portée
de la cible, non obscurcie, tir possible — d'où l'éviction (a).

COLLAPSES documentés (doctrine FinalJustice, tri d'utilité impératif) :
  - tri = `ClosestToParent` (distance hex au caster ; natif = MovementInSteps IdunBattle.AI.Utilities.MV71SniperDroneSquad_SpawnTileUtility$$EvaluateMovementInSteps, == dist hex
    sur board ouvert) ; `WeightedUtility(7=Tile)` traité CONSTANT sur terrain uniforme (flag) ;
    tie-break = (dist hex à la cible, id de tuile) — À CONFRONTER live (GT (3,4)/(4,3)/(5,4)).
  - « peut attaquer depuis » = distance <= portée max d'arme du drone ; LoS (`UnobscuredTiles`) NON
    portée (flag — board MC1_67 ouvert).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC
import hexgeo

from ..base import ActiveAbility, convert_rounds_to_turns
from ..targeting import (RANGE_ADJACENT_IF_MELEE_CASTER, RANGED_BOOL_IF_RANGED_CASTER,
                         TargetingOptions)
from ..targeting_rule import TargetingRule as TR
from ...components import (StatsComponent, OwnerComponent, PositionComponent, UnitComponent,
                           HealthComponent)
from ...operations.damage import AttackDamageOperation
from ...operations.effects import AddEffectOperation
from ...operations.spawn import _spawn_config_grot, _occupied_tiles
from ...operations.remove_unit import RemoveUnitOperation
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


def is_mv71_normal_attacker(visual_id) -> bool:
    """L'attaque NORMALE de cette unité est-elle `MV71SniperDroneSquadAttack` (1076) ? Mirror du
    dispatch natif par `ActiveAbilityComponent.NormalAttackType@0x28` (per-unit, vtable de l'instance),
    résolu OFFLINE depuis le KIT gameconfig : porteur du passif `MV71SniperDroneSquad` (Sho'syl /
    `tauMarksman`) — même doctrine de résolution kit que `UnitNormalAttackType` (formulas.py)."""
    if not visual_id:
        return False
    v = _MV71_KIT_CACHE.get(visual_id)
    if v is None:
        names = []
        for _slot, x in (GC.unit_abilities(visual_id) or {}).items():
            if isinstance(x, str):
                names.append(x)
            elif isinstance(x, dict):
                names.append(x.get("name") or x.get("id"))
            elif isinstance(x, list):
                names += [(y.get("name") if isinstance(y, dict) else y) for y in x]
        v = CONFIG in names
        _MV71_KIT_CACHE[visual_id] = v
    return v


_MV71_KIT_CACHE: dict = {}


def _friendly_drones(state: "State", team, unit_id: str) -> list:
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$AlreadySpawnedSummonsSortedSelector` = `SortByFormula(UnitsWithId(Friends(Self),
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


def _spawn_tile_utility_0x37(pos, parent_pos, adj, caster_team) -> float:
    """`MV71SniperDroneSquad_SpawnTileUtility.EvaluateMovementInSteps` (`<d__5>.IdunBattle.AI.Utilities.MV71SniperDroneSquad_SpawnTileUtility.u003CEvaluateMovementInStepsu003Ed__5$$MoveNext`,
    poids BC catégorie `MV71SniperDroneSquad_ClosestToParent`) :
        u  = Fix64(-steps(candidate, tuile du PARENT)) x W[AdjacentToParent]            (=50/pas)
        si AUCUN ennemi adjacent au candidat : u += W[NoAdjacentEnemy]                  (=40)
        pour chaque AMI adjacent :
            (gate « aucun ennemi adjacent ») ami a StructuralAnalyser(0x477)  -> +W[InRangeOfStructuralAnalyser] (=3)
            (gate idem)                     ami a DefenderOfTheGreaterGood(0x483) -> +W[InRangeOf...GreaterGood] (=25)
            `IdunBattle.AI.Utilities.SaviorProtocolsUtility$$CanBeProtector` (= HasFaction(9=T'au) ET PAS SaviorProtocols 0x460) -> +W[AdjacentToTau] (=20)
    `steps` = slot service 0x6b(parentTile, candidate) — port : distance hex (== pas sur board ouvert
    sans mur ; flag si un board a des obstacles). FONCTION PURE (tranche 3) : `adj` = occupants VIVANTS
    adjacents [(team, visual_id)] — hydraté runner-state (`_adjacent_occupants`) OU scene (prédiction)."""
    from ....entities.triggered_ability_type import triggered_ability_ids
    from ....ai.action_generators import _faction
    wt = _wt()
    u = -hexgeo.distance(pos, parent_pos) * wt.sub(_W_CAT, "MV71SniperDroneSquad_AdjacentToParent")
    enemies_adj = [x for x in adj if x[0] != caster_team]
    friends_adj = [x for x in adj if x[0] == caster_team]
    if not enemies_adj:
        u += wt.sub(_W_CAT, "MV71SniperDroneSquad_NoAdjacentEnemy")
    for _team, vis in friends_adj:
        trig = set(triggered_ability_ids(vis) or ())
        if not enemies_adj:
            if STRUCTURAL_ANALYSER in trig:
                u += wt.sub(_W_CAT, "MV71SniperDDroneSquad_InRangeOfStructuralAnalyser")
            if DEFENDER_OF_THE_GREATER_GOOD in trig:
                u += wt.sub(_W_CAT, "MV71SniperDDroneSquad_InRangeOfDefenderOfTheGreaterGood")
        if _faction(vis) == "Tau" and SAVIOR_PROTOCOLS not in trig:   # IdunBattle.AI.Utilities.SaviorProtocolsUtility$$CanBeProtector
            u += wt.sub(_W_CAT, "MV71SniperDroneSquad_AdjacentToTau")
    return float(u)


def _tile7_utility(pos, elev, elev_minmax, eff_names, adj, caster_team, unit_id: str) -> float:
    """Terme `WeightedUtility(7 = Tile)` du bucket — le composite Tile(7) PORTÉ (`utilities/tile.py`,
    29 feuilles), évalué pour le DRONE-TEST (`TestUnitProvider` natif : l'unité évaluée = le drone qui
    serait posé). FONCTION PURE (tranche 3) : `elev`/`elev_minmax` = élévation tuile + min/max BOARD
    ENTIER ; `eff_names` = effets DYNAMIQUES de la tuile + covers hébergés par le TERRAIN ; `adj` =
    occupants VIVANTS adjacents [(team, visual_id)] (counts d'amis par triggered-ability, leaves
    20/21/22). leaf_ctx du drone : kit déclenché (SaviorProtocols 1120 — LoadPlaybook(1120) natif =
    null -> dispatcher(2) à 0), faction T'au (9), arme ranged."""
    from ....utilities.tile import tile_composite
    from ....entities.triggered_ability_type import triggered_ability_ids
    meta: dict = {}
    if elev is not None:
        meta = {"elevation": elev, "elevation_max": elev_minmax[1], "elevation_min": elev_minmax[0]}
    if eff_names:
        meta["effects"] = list(eff_names)
    counts: dict = {}
    for _team, vis in adj:
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
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PickTile` : renvoie l'id de TUILE choisie, ou None (aucune tuile -> cast no-op,
    le gate de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason`).

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
        from ....utilities.tile import terrain_tile_effects
        best_tid, best_u = None, None
        for tid, pos in cands:                              # max stable (ordre des candidats au tie)
            adj = [(t, v) for _e, t, v in _adjacent_occupants(state, board, tid)]
            effs = []
            if state.effects is not None:                   # effets dynamiques poses SUR la tuile (Fire/Ice…)
                effs += [e.name for e in state.effects.by_unit.get(int(tid), [])
                         if not e.consumed and e.name]
            effs += terrain_tile_effects(board.terrain_at(pos[0], pos[1]), effs)  # covers heberges (#155)
            elev = (board.by_id.get(tid) or {}).get("elevation")
            u = (_tile7_utility(pos, elev, emm, effs, adj, coc.team, unit_id)
                 + _spawn_tile_utility_0x37(pos, cpos, adj, coc.team))
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


def pick_tile_scene(scene, att_id: int, tgt_id: int, unit_id: str, max_summons: int,
                    parent_pos=None, first_only: bool = False):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PickTile` côté PRÉDICTION (#61bis tranche 3) — MÊME port que `_pick_tile` (runner),
    hydraté depuis la `Scene` du playbook : la prédiction native passe le délégué b__0 IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility.u003Cu003Ec__DisplayClass7_0$$u003CPredictAttacku003Eb__0 =
    `() => PickTile(entities, firstOnly=0)`, soit LE MÊME PickTile que l'exécution. Le SCORING
    (Tile(7) + utilité 0x37) est la MÊME fonction pure que le runner (pas de fork) ; seule
    l'hydratation diffère (pos_by_id/vis_by_id/hp vs entities/components).

    `parent_pos` = position du CASTER pour le terme ClosestToParent — la chaîne display threade la
    POSITION CANDIDATE de bout en bout (#153 : entities.CasterPosition = tuile de sélection), donc
    l'appelant passe `attack_pos` ; défaut = position réelle. **Le caster est VIRTUELLEMENT SUR
    `parent_pos`** (arbitré live, probe_61bis_pred seed 61011) : (a) la tuile candidate est EXCLUE
    des tuiles de drone (mirror du filtre `!Contains(unitPosition.Tile)` — indiscernable de
    l'occupation en EXÉCUTION où la tuile du caster est réellement occupée, discriminé en prédiction
    par les rows (5,7)/(4,6) x1.5) ; (b) sa tuile RÉELLE devient LIBRE ; (c) l'adjacence
    (AdjacentToTau/NoAdjacentEnemy/leaves 20-22) le voit à la position HYPOTHÉTIQUE (parent (5,7) :
    (6,6) ne gagne que si le caster T'au adjacent est vu en (5,7)). Occupation/adjacence = unités
    VIVANTES (hp>0 — decisionView garde les cadavres). Renvoie la POSITION (col,row), ou None
    (aucune tuile -> prédiction VIDE)."""
    board = scene.board
    t_pos = scene.pos(tgt_id)
    if board is None or t_pos is None:
        return None
    if parent_pos is None:
        parent_pos = scene.pos(att_id)
    caster_team = scene.team(att_id)
    if parent_pos is None or caster_team is None:
        return None
    parent_pos = tuple(parent_pos)
    rng = _drone_attack_range(unit_id)
    alive = [u for u in scene.pos_by_id
             if (scene.hp(u) or 0) > 0 and scene.pos(u) is not None]
    # remap : caster deplace de sa tuile reelle vers parent_pos (position hypothetique #153)
    _pos_of = {u: (parent_pos if u == att_id else tuple(scene.pos(u))) for u in alive}
    occupied = set(_pos_of.values())
    by_pos = {p: u for u, p in _pos_of.items()}
    tpos = tuple(t_pos)

    def _adj(tid):
        out = []
        for n in board.neighbours(tid):
            info = board.by_id.get(n)
            if info is None:
                continue
            u = by_pos.get((info["col"], info["row"]))
            if u is not None:
                out.append((scene.team(u), scene.vis_by_id.get(u)))
        return out

    cands = []
    for tid in sorted(board.by_id.keys()):
        info = board.by_id[tid]
        pos = (info["col"], info["row"])
        if not board.walkable(tid) or pos in occupied:      # CanAddUnit (libre + marchable)
            continue
        d_t = hexgeo.distance(pos, tpos)
        if d_t < 1 or d_t > rng:                            # « peut attaquer la cible depuis » (portée)
            continue
        cands.append((tid, pos))
    if cands:
        if first_only:
            return cands[0][1]
        elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
        emm = (min(elevs), max(elevs)) if elevs else (None, None)
        from ....utilities.tile import terrain_tile_effects
        best_pos, best_u = None, None
        for tid, pos in cands:
            adj = _adj(tid)
            effs = list((scene.tile_effects_by_pos or {}).get(pos) or ())   # dynamiques (tileMeta du pas)
            effs += terrain_tile_effects(board.terrain_at(pos[0], pos[1]), effs)   # #155 : canal dyn.
            elev = (board.by_id.get(tid) or {}).get("elevation")
            u = (_tile7_utility(pos, elev, emm, effs, adj, caster_team, unit_id)
                 + _spawn_tile_utility_0x37(pos, tuple(parent_pos), adj, caster_team))
            if best_u is None or u > best_u:
                best_pos, best_u = pos, u
        return best_pos
    # FALLBACK natif : uniquement au cap — tuile du drone le plus FAIBLE, si à portée de la cible.
    drones = sorted((int(scene.hp(u) or 0), u) for u in alive
                    if scene.vis_by_id.get(u) == unit_id and scene.team(u) == caster_team)
    if len(drones) < max_summons or not drones:
        return None
    wpos = scene.pos(drones[0][1])
    if wpos is None:
        return None
    d_t = hexgeo.distance(tuple(wpos), tpos)
    if d_t < 1 or d_t > rng:
        return None
    return tuple(wpos)


class MV71SniperDroneSquadAttackAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` (id **1076**) — cf. docstring
    module pour la chaîne native complète et les collapses. GROUND TRUTH live : case-61bis §2 (runner
    88, seed 61001 : dégât −9391, drone (3,4) adjacent caster, stats 1996/499/2093, Markerlight posé,
    1132/1133 absents post-cast)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MV71SniperDroneSquadAttack)   # 1076

    # GATE DE CIBLE (#115) -- FORME 4, **FACTORY NOMMEE** (la forme decouverte par #248) :
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$.ctor`
    # n'ecrit AUCUN champ et ne recopie AUCUN preset -- il appelle
    #   `IdunBattle.Core.Services.TargetingOptions$$CustomLokiNormalAttackOptions(&opts, 2)`
    # puis `ALoki_NormalAttackAbility..ctor(this, &opts, 1, 0)`.
    #
    # La factory recopie le preset `<TargetingOptions statics>+0x00` CHAMP PAR CHAMP, et ne COMBINE
    # que `Rules` -- mirror verbatim de son decompile :
    #     *param_1              = *puVar2                          # +0x00 isSelfCasting
    #     *(param_1+0x08/0x10/0x18) = *(puVar2+0x08/0x10/0x18)     # TargetingRange (0x18 octets)
    #     *(param_1+0x20)       = *(puVar2+0x20)                   # forceMeleeTarget
    #     *(param_1+0x28)       = *(puVar2+0x28) | param_2         # <- LE OU, comme la surcharge 2
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit ce preset +0x00 :
    #     +0x00 isSelfCasting    = 0
    #     +0x08 range           <- `TargetingRange` statics+0x00 = RANGE_ADJACENT_IF_MELEE_CASTER
    #     +0x20 forceMeleeTarget = 2 = RangedBool.IfRangedCaster
    #     +0x28 rules            = 0x4002
    # => masque EFFECTIF = `0x4002 | 2` = **0x4002**, l'argument `2` de la factory etant DEJA pose
    #    par le preset (le OU ne change rien ici -- c'est le calcul qui le dit, pas une supposition).
    # Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`), somme = 0x4002 :
    #     0x2    TargetMatchesDynamicRule -> `MV71SniperDroneSquadAttackAbility$$GetDynamicInvalid
    #            TargetReason` ; non surcharge cote port -> defaut 0 (PERMISSIF assume, cf. la
    #            docstring de module : la SEULE condition dynamique est « une tuile de spawn existe »)
    #     0x4000 TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie)
    # PORTEE (#241) : `TargetingRange` statics+0x00 = `onlyAdjacent = IfNotRangedCaster` -- le drone
    # est RANGED, donc `onlyAdjacent` retombe sur la portee d'ARME ; `forceMeleeTarget =
    # IfRangedCaster` re-clampe a 1 quand `ShouldApplyRangedInMelee`. C'est le profil exact du tir
    # normal (meme preset que 1004 MortisRound a `Rules` pres).
    # ⚠ LE PORTEUR NE SE LIT PAS DANS LE GAMECONFIG : le balayage des 669 kits par ID d'ability ne
    # rend RIEN pour 1076 (`tauMarksman` n'y porte que le PASSIF `MV71SniperDroneSquad`). C'est le
    # LIVE qui tranche -- `decisionView(allAbilities=true)` expose 1076 sur `tauMarksman`, et
    # `abilityReason` traverse la cascade pour lui MALGRE un `abilityState` null (ability
    # `...Abilities.Triggered.`, donc pas d'`ActiveAbilityComponent`). Ce cas RESSEMBLE au piege MoW
    # de #249 mais en DIFFERE : `AttackQuery$$GetInvalidTargetReason` ne court-circuite pas sur
    # `0x1`, il rend les vraies regles rompues. CONFRONTEE LIVE, cf.
    # `docs/rl/case-254-loki-solo-targeting.md`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT_IF_MELEE_CASTER,
                                         force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)

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
        # --- dispatch mêlée : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$IsMeleeAttack` (cible adjacente) -> délégation TOTALE à
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
                                                is_crit=bool(atk.get("did_crit")),
                                                did_block=bool(atk.get("did_block")))
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
            # IdunBattle.Entities.Behaviours.RemoveUnitBehaviour$$Execute : despawn SANS vecteur
            # on-death. Le sélecteur est déjà résolu ici, mais la MUTATION passe par l'Operation
            # native (`IdunBattle.Operations.RemoveUnitOperation$$Execute`, `removeEffects=1` — le
            # littéral du behaviour) : c'est elle qui porte le gate `Removed`, la pose du flag 0x1a,
            # la publication d'`On(0x25 = UnitRemoved)` PUIS la consommation des effets portés.
            if RemoveUnitOperation.execute(state, int(uid), remove_effects=True) is not None:
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
        # TargetTrigger `On(AttackDamageAttack=10,1) & OwnerIsCaster` (IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$CreateTargetTrigger) : le drone vient
        # d'attaquer -> 1132 (IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$RevertInternal = REMOVE_OVERRIDE x4) et 1133 sont retirés
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
        # tour du caster (identique StructuralAnalyser IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddMarkerlightAbility$$CreateBehaviour).
        # #98 : `Sum(TurnsFromRounds(1), Direct(1))` -> SEUL le terme `TurnsFromRounds` passe par
        # `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` ; le `Direct(1)` est deja en TOURS.
        ml = AddEffectOperation.execute(state, source=caster_id, target=target_id,
                                        effect_type=MARKERLIGHT, name="Markerlight",
                                        duration_override=convert_rounds_to_turns(state, 1) + 1)
        return {"melee": False, "tile": (tinfo.get("col"), tinfo.get("row")), "spawned": [drone_id],
                "evicted": evicted, "attack": atk, "markerlight": ml is not None,
                "overrides_applied": bool(eff_1132), "drone_flags": drone_flags}
