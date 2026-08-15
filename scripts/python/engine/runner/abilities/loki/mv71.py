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
            AddFlag(Get(drone), 0x1c = UnitFlag.IngoreRangedInMelee)      # cf. l'encadre ci-dessous
            UseActiveAbility(Alive(Get(drone)), target@0x178, GetNormalAttackType(drone),
                             Nullable<AbilityOrEffect>(this+0x10=1076) x2)   # attribution 1076
            RemoveFlag(Get(drone), 0x1c)
    (e) AddEffect(0x462=1122 Markerlight, stateRef, caster@0x160, target@0x178,
                  Sum(TurnsFromRounds(1), Direct(1)))   # fin du prochain tour du caster

⚠ LE COUPLE `AddFlag`/`RemoveFlag` DE (d) MANQUAIT A CETTE CITATION (#287-r11-r2-r1-r2), et il
n'est pas decoratif : `MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` est le **SEUL** poseur
de `UnitFlag.IngoreRangedInMelee` (28 = `0x1c`) de tout le binaire -- balayage EXHAUSTIF des deux
seules voies d'ecriture d'un flag (25 appelants de `UnitFlagsComponent$$Add`, 10 appelants de
`IdunBattleLogic.Entities.DSLBehaviors$$AddFlag`, plus les xrefs de `UnitFlagsComponent$$Remove` ;
la classe n'expose ni `AddRange` ni setter de masque). La chaine est
`AddEffect & AddEffect & AddFlag(sel, 0x1c) & UseActiveAbility(...) & RemoveFlag(sel, 0x1c)`,
composee par `AbilityBehaviour$$op_BitwiseAnd`, et le porteur du flag est **le DRONE** (selecteur
`+0x68`, celui-la meme qui recoit les deux `AddEffect` et le `Alive()`), jamais le heros.
SEMANTIQUE : l'attaque d'OUVERTURE du drone fraichement invoque est DISPENSEE de la penalite
ranged-in-melee -- le flag est TRANSITOIRE, il n'existe jamais entre deux actions.
CONSEQUENCE SUR LE MIRROR DU GATE : sur le chemin `BattleQuery$$IsTargetInAttackRangeForSummon`,
`ShouldApplyRangedInMelee` recoit le **`parent`**, qui ne porte JAMAIS ce flag -> le gate y est
INERTE PAR CONSTRUCTION, et c'est une mesure, pas un manque de canal. Il MORD sur l'autre chemin,
`AttackQuery$$ShouldApplyRangedInMelee(caster = LE DRONE)` (-> `targeting.get_range`).

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PickTile` : candidates = tuiles autour des TUILES DE LA CIBLE selon la config du drone
(service slot 0x66 x slot 0xaa(unitId) — portée d'attaque du drone), filtrées `CanAddUnit` &
`!IsTilePendingDrafting` & « peut attaquer les tuiles de la cible depuis » (slot 0xc3) ; puis
`SortTilesByUtility(list, [UtilityBucket[WeightedUtility(7=Tile), WeightedUtility(0x38=
MV71SniperDroneSquad_ClosestToParent)]], Self@0x148)` -> First. `firstOnly` -> 1er candidat brut
(le gate de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason` : la SEULE condition dynamique — H53 infirmée,
aucune portée minimale). FALLBACK (seulement au cap) : la tuile du drone le plus faible si à portée
de la cible, non obscurcie, tir possible — d'où l'éviction (a).

COLLAPSES documentés (doctrine FinalJustice, tri d'utilité impératif) :
  - tri = `ClosestToParent` (distance hex au caster ; natif = MovementInSteps IdunBattle.AI.Utilities.MV71SniperDroneSquad_SpawnTileUtility$$EvaluateMovementInSteps, == dist hex
    sur board ouvert) ; `WeightedUtility(7=Tile)` traité CONSTANT sur terrain uniforme (flag) ;
    tie-break = (dist hex à la cible, id de tuile) — À CONFRONTER live (GT (3,4)/(4,3)/(5,4)).
  - « peut attaquer depuis » (slot 0xc3 = `IBattleQuery` 196) N'EST PLUS un collapse de distance :
    `IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon` est MIRRORÉ depuis
    `#287-r11-r2-r1` (`_is_target_in_attack_range_for_summon`) — `IsTargetable`, clamp mêlée
    `ShouldApplyRangedInMelee` DEPUIS LA TUILE CANDIDATE, portée, LIGNE DE VUE
    (`MovementQuery$$GetTilesObscuringTerrain`, `IMovementQuery` slot 16, littéraux `6, 2`) et
    `CanMeleeAttackOverElevationDifference`. Le collapse coûtait une tuile de spawn parfois
    différente tant que `PickTile` ne servait qu'à l'EXÉCUTION ; depuis `#287-r11-r2` il décide de
    la LÉGALITÉ d'un cast, donc chaque étage manquant ACCEPTAIT une cible que le natif REFUSE.
  - le REPLI se termine nativement par
    `IdunBattleLogic.Entities.DSLSelectors$$FilterTilesIfCanAttackTargetTileFrom(Caster@0x48,
    Target@0x60, <la tuile>)`, PORTÉ depuis `#433-r4-r1` (nœud DSL
    `entities/selectors/tiles.py::FilterTilesIfCanAttackTargetTileFrom`) : la tuile du drone le plus
    faible est REFUSÉE si un ennemi du caster lui est adjacent ET qu'elle n'est pas adjacente à la
    tuile de la cible → `PickTile` rend null → cast NO-OP. Son maillon `UnobscuredTiles` est porté
    depuis `#287-r11-r2-r1` et il est un **NŒUD DSL** depuis `#287-r11-r2-r1-r3`
    (`entities/selectors/tiles.py::UnobscuredTiles`, mirror d'`UnobscuredTilesSelector$$Select` ET
    de son `$$IsObscured`) — la DÉCISION n'est plus collapsée, elle émerge de l'arbre (doctrine
    #149), comme pour son voisin de chaîne `FilterTilesIfCanAttackTargetTileFrom` depuis #433-r4-r1.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC
import hexgeo

from ..base import ActiveAbility, convert_rounds_to_turns
from ..behaviours.context import entities_from_state
from ..targeting import (RANGE_ADJACENT_IF_MELEE_CASTER, RANGED_BOOL_IF_RANGED_CASTER,
                         TargetingOptions, has_steppable_unit, is_targetable)
from ..targeting_rule import TargetingRule as TR
from ...components import (StatsComponent, OwnerComponent, PositionComponent, UnitComponent,
                           HealthComponent, UnitFlagsComponent, get_unit_feet)
from ....entities.unit_flag import UnitFlag   # `IngoreRangedInMelee` (#287-r11-r2-r1-r2)
from ....dsl.base import DslContext
from ....entities.selectors.accessors import FixedTileIds, FixedTiles, Target
from ....entities.selectors.tiles import Caster, FilterTilesIfCanAttackTargetTileFrom
from ....entities.selectors.tiles import UnobscuredTiles      # #287-r11-r2-r1-r3
from ...operations.damage import AttackDamageOperation
from ...operations.effects import AddEffectOperation
from ...operations.spawn import _spawn_config_grot, _occupied_tiles
from ...operations.remove_unit import RemoveUnitOperation
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effect_type import EffectType
from ....entities.traits.unit_trait import UnitTrait, entity_trait_names
from ....entities.triggered_ability_type import TriggeredAbilityType   # #270-r1-r1
from ....services.battle_query import are_tiles_adjacent
# #287-r11-r2-r1-r1 -- FORME B (module, pas symbole) : `_drone_attack_range` DELEGUE a son foyer
# natif `BattleQuery$$GetUnitMaxRange`. Un `from ... import get_unit_max_range` gelerait la liaison
# et NE MORDRAIT PAS sous `monkeypatch.setattr("engine.services.battle_query.get_unit_max_range")`.
# Aucun cycle : `services.battle_query` est DEJA dans la cascade de ce module (l'import ci-dessus).
from ....services import battle_query as _sbq
from ....services.custom_normal_attack import substitutes_normal_attack
from ....services.movement_query import get_tiles_obscuring_terrain
from ....services.targeting_query import BLOCKING_ELEVATION_DIFFERENCE, OBSCURING_TYPE_ALL
from ....entities.triggered_ability_type import triggered_ability_ids
from ....utilities.tile import tile_composite
from ....utilities.tile import terrain_tile_effects
from ....weights import load

if TYPE_CHECKING:
    from ...state import State

INITIAL_DMG = int(EffectType.MV71SniperDroneSquad_InitialDmg)          # 1132 = 0x46c
RESET_INITIAL_DMG = int(EffectType.MV71SniperDroneSquad_ResetInitialDmg)   # 1133 = 0x46d
MARKERLIGHT = int(EffectType.Markerlight)                              # 1122 = 0x462
CONFIG = "MV71SniperDroneSquad"    # l'entrée gameconfig qui porte constants/variables (le passif 1119)


def _drone_attack_range(unit_id: str) -> int:
    """Portee d'attaque max du drone = `IdunBattle.Core.Services.BattleQuery$$GetUnitMaxRange(unitId)`
    (slot **171** d'`IBattleQuery`), DELEGUE a son foyer
    `engine.services.battle_query.get_unit_max_range` (#287-r11-r2-r1-r1).

    C'est la MEME fonction que la boucle INLINE de `BattleQuery$$IsTargetInAttackRangeForSummon`
    (slot 196) -- corps confronte au decompile, identique aux deux endroits :

        config = GetUnitConfig(unitId);
        if (config == null || config.Weapons == null) return 0;
        max = 0;
        foreach (w in config.Weapons) max = Math.Max(max, w.Range.HasValue ? w.Range.Value : 1);
        return max;

    ⚠ CE QUI A CHANGE, ET LES DEUX REGIMES OU CA MORD (#287-r11-r2-r1-r1). Le corps LOCAL d'avant
    ecrivait `int(w.get("Range") or 0)` puis `return mx if mx > 0 else 1` : il MAPPAIT le `0` natif
    sur `1`, et lisait `0` (au lieu de `1`) pour une arme sans portee. Deux divergences :

      * **config nulle, absente ou liste d'armes VIDE** -> natif `0`, port d'avant `1`. Regime reel :
        les unites du gameconfig sans aucune arme (MoW et decor). Portee 1 ⇒ l'anneau de `_pick_tile`
        (`1 <= d <= rng`) garde les tuiles ADJACENTES a la cible, la ou le natif n'en garde AUCUNE
        (`1 <= d <= 0` est vide) -> une cible que le natif REFUSE etait acceptee. MEME direction
        PERMISSIVE que l'ecart que #287-r11-r2-r1 a ferme ;
      * **arme a `Range` explicitement `0`** (`HasValue` vrai, valeur 0) -> natif `0`, port d'avant
        `1` (le `mx > 0 else 1` la rabattait). Distinct du precedent : ici la config EXISTE.

    Le cas « toutes les armes sans `Range` » (melee pure) rendait deja `1` des deux cotes -- par
    accident de compensation, pas par fidelite : `or 0` mettait 0, et `mx > 0 else 1` le remontait."""
    return _sbq.get_unit_max_range(unit_id)


def is_mv71_normal_attacker(visual_id, passive_abilities=None, active_abilities=None,
                            traits=None, config_active_abilities=None) -> bool:
    """L'attaque NORMALE de cette unité est-elle `MV71SniperDroneSquadAttack` (1076) ? Mirror du
    dispatch natif par `ActiveAbilityComponent.NormalAttackType@0x28`, écrit UNE fois par
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` depuis
    `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive`.

    ⚠ La clé de dispatch native est `UnitConfiguration.PassiveAbilities` — un fait d'ENTITÉ, pas le
    kit gameconfig. `passive_abilities` (la liste MESURÉE, `UnitContext.passive_abilities`) fait donc
    autorité quand elle existe ; `None` = canal muet -> repli KIT, le comportement d'avant.
    Résoudre par le kit SEUL était le fork mesuré par #419-r1-tr14-r5 : sur un bras
    `write_grafted_seed_bc(..., replace=True)` le natif ramène l'attaque normale à `69` et le port
    continuait de prendre le chemin drone. RE et mesure : `engine.services.custom_normal_attack`.

    `active_abilities` (#419-r1-tr14-r5-r2) = la SECONDE voie de la meme cascade. Elle n'est
    consultee par le natif que lorsque la voie passive rend `null`, et elle ne peut rendre que
    `RogalDorn_NormalAttack` -- jamais `MV71SniperDroneSquadAttack`. La passer ne change donc pas
    la reponse de CE predicat ; elle est threadee pour que le foyer decide de la MEME cascade
    partout, plutot que d'avoir un poste d'appel qui en connaisse une moitie.

    `traits` (#419-r1-tr14-r5-r2-r1) = la TROISIEME branche, threadee pour la MEME raison et avec la
    MEME portee : elle ne peut rendre que `Loki_NormalBossAttack`, donc jamais
    `MV71SniperDroneSquadAttack`. `None` = canal muet -> repli kit."""
    return substitutes_normal_attack(CONFIG, passive_abilities=passive_abilities,
                                     visual_id=visual_id, active_abilities=active_abilities,
                                     traits=traits,
                                     config_active_abilities=config_active_abilities)


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
        _WT = load()
    return _WT


# Catégorie BC de l'utilité 0x37 (⚠ deux sous-clés portent le TYPO NATIF « DDrone » — copie exacte).
_W_CAT = "MV71SniperDroneSquad_ClosestToParent"
STRUCTURAL_ANALYSER = TriggeredAbilityType.StructuralAnalyser       # 1143 (triggered) — bonus InRangeOfStructuralAnalyser
DEFENDER_OF_THE_GREATER_GOOD = TriggeredAbilityType.DefenderOfTheGreaterGood   # 1155 (triggered) — bonus InRangeOfDefenderOfTheGreaterGood
SAVIOR_PROTOCOLS = TriggeredAbilityType.SaviorProtocols          # 1120 (triggered) — gate CanBeProtector (= T'au ET PAS 1120)


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
            # #270-r1-r1 : les trois ids sont des `TriggeredAbilityType` -- ce sont EXACTEMENT les
            # trois que les feuilles 21/22/23 du composite Tile lisent dans `ability_friend_counts`
            # (`utilities/tile.py` : KustomForceFieldUtility 1102, DefenderOfTheGreaterGood 1155,
            # SaviorProtocols 1120). Le nom est donc deja au site, cote consommateur.
            if ab in (TriggeredAbilityType.KustomForceField,             # 1102
                      TriggeredAbilityType.DefenderOfTheGreaterGood,     # 1155
                      TriggeredAbilityType.SaviorProtocols):             # 1120
                counts[ab] = counts.get(ab, 0) + 1
    if counts:
        meta["ability_friend_counts"] = counts
    ctx = {"unit_triggered_abilities": list(triggered_ability_ids(unit_id) or ()),
           "unit_faction": 9,                          # UnitFaction.Tau (le drone-test)
           "unit_has_ranged_weapon": True,
           "friend_positions": []}
    return float(tile_composite(pos, meta, ctx, _wt()))


def _filter_tiles_if_can_attack_target_tile_from(dctx, tile_id: int):
    """DERNIER maillon de la chaine de REPLI native de `PickTile`, non porte jusqu'a `#433-r4-r1` :

        sel = SurroundingTiles(Tiles(Target@0x60), includeCenter: 0, radius: <portee du drone>)
              op_BitwiseAnd Tiles(First(AlreadySpawnedSummonsSortedForRemoval, 1, 0))
        sel = UnobscuredTiles(Tiles(Target@0x60), sel)                    # LoS -- `_unobscured_tiles`
        sel = FilterTilesIfCanAttackTargetTileFrom(Caster@0x48, Target@0x60, sel)   # <- ICI
        return sel.SelectTile(entities)

    Les deux premiers etages sont deja collapses imperativement par l'appelant (l'anneau = la garde
    `1 <= dist(drone, cible) <= portee`, l'intersection = « la tuile DU drone le plus faible ») ;
    le troisieme, lui, EST un noeud DSL depuis `#287-r11-r2-r1-r3` (`_unobscured_tiles`, qui monte
    `UnobscuredTiles`) ; ce dernier etage-la l'est aussi -- la structure emerge de l'arbre
    (doctrine #149), le collapse ne fournit que le vehicule `FixedTileIds`. Rend l'id survivant, ou None
    (le natif rend alors `null`, donc un cast NO-OP : ni eviction, ni spawn, ni Markerlight)."""
    kept = FilterTilesIfCanAttackTargetTileFrom(
        Caster(), Target(), FixedTileIds([int(tile_id)])).select(dctx)
    return int(kept[0]) if kept else None


def _filter_can_attack_target_tile_from(state: "State", caster_id: int, target_id: int,
                                        tile_id: int):
    """Face RUNNER de `_filter_tiles_if_can_attack_target_tile_from` : contexte DSL depuis le `State`.

    La porte d'elevation `|dElev| < 2` des DEUX adjacences est ACTIVE depuis #433-r4-r1-r4 :
    `DslContext.__post_init__` derive `elev_by_pos` du `board` (ici `state.board`, le `boardGraph`
    capte). Elle ne degrade en no-op que si le board n'expose aucune elevation."""
    return _filter_tiles_if_can_attack_target_tile_from(
        entities_from_state(state, caster_id, target_id), tile_id)


# ------------------------------------------------------------------------------------------------
# `IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon` (#287-r11-r2-r1)
#
# Le TROISIEME filtre de `PickTile` (`IBattleQuery` slot 196, `metadata/interface_slots.tsv`). Il
# etait COLLAPSE en `1 <= distance(tuile, cible) <= portee` ; depuis #287-r11-r2 ce collapse decide
# de la LEGALITE d'un cast (le gate `GetDynamicInvalidTargetReason` teste la NULLITE de `PickTile`),
# donc chaque condition non portee ACCEPTE une cible que le natif REFUSE (SOUS-refus).
#
# La substitution est un DICT `{id de tuile: (team, steppable, targetable)}` des unites VIVANTES :
# c'est tout ce que les deux etages a substrat (`ShouldApplyRangedInMelee` et `IsTargetable`) lisent,
# et les deux faces du port (runner / prediction) savent le construire depuis LEUR hydratation.
# ------------------------------------------------------------------------------------------------

def _should_apply_ranged_in_melee_from_tile(board, tile_id, attacker_team,
                                            occupant_by_tile,
                                            attacker_ignores_ranged_in_melee=None) -> bool:
    """`IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee(attacker,
    attackerTiles, state, ignoreTrait)` -- VERBATIM du decompile :

        if (attackerTiles == null || attackerTiles.Count == 0)        return false;
        if (!UnitExtensions.HasTrait(attacker, 0xb) && !ignoreTrait)  return false;
        if (UnitExtensions.HasFlag(attacker, 0x1c))                   return false;
        foreach (attackerTile in attackerTiles)
          foreach (adj in TileComponent(attackerTile).Neighbours)
            u = UnitExtensions.GetUnit(adj, state);
            if (u != null && EntityExtensions.IsUnit(u)
                && !UnitExtensions.IsFriend(attacker, u, state)
                && !TileExtensions.HasSteppableUnit(adj, state)
                && DamageCalculations.CanMeleeAttackOverElevationDifference(attackerTile, adj)
                && UnitExtensions.IsTargetable(u) && UnitExtensions.IsAlive(u, state))
              return true;
        return false;

    ⚠ CE N'EST PAS `targeting.should_apply_ranged_in_melee`, ET LA DIFFERENCE EST LE POINT :
    `IsTargetInAttackRangeForSummon` l'appelle avec `attackerTiles = [<la tuile CANDIDATE>]`
    (`TExtensions.ToList(tile)`), PAS avec les tuiles du caster. C'est donc « un ennemi du caster
    est-il au contact de la tuile ou le DRONE serait pose », et c'est ce qui rabat la portee a 1 --
    donc ce qui ARME `CanMeleeAttackOverElevationDifference` en aval. `ignoreTrait = 1` est le
    litteral du call-site : le gate `HasTrait(0xb Ranged)` est court-circuite.

    `attacker` n'entre ici QUE par son equipe (`IsFriend`) : la fonction ne lit aucune tuile du
    caster. `IsAlive` est mirroir par CONSTRUCTION -- `occupant_by_tile` ne porte que des unites
    vivantes.

    LE GATE `!HasFlag(attacker, 0x1c)` EST PORTE DEPUIS #287-r11-r2-r1-r2 (il manquait aux DEUX
    mirrors). `0x1c` se lit dans SON espace de nommage : `UnitFlag.IngoreRangedInMelee` (**typo
    native**, `enums.tsv` : `28=IngoreRangedInMelee`) -- l'ordinal 28 nomme AUTRE CHOSE dans
    `UnitTrait` et dans `TargetingRule`, donc l'appariement se fait par le NOM, jamais par le
    nombre. `attacker` = le **`parent`** du call-site (`BattleQuery$$IsTargetInAttackRangeForSummon`
    passe `parent`, pas le drone) : c'est le drapeau du CASTER qui dispense du clamp melee.

    `attacker_ignores_ranged_in_melee` est en TRI-ETAT, et la DIRECTION est celle de #287-r11-r1-r1-r2 :
      * `True` MESURE  -> le natif rend `false` AVANT la boucle -> pas de clamp ;
      * `False` MESURE -> la boucle s'evalue ;
      * `None` = PAS MESURE -> la boucle s'evalue aussi. Sauter sur une non-mesure ELARGIRAIT la
        portee du drone (le clamp a 1 disparaitrait), c'est-a-dire fabriquerait des candidates que
        le natif refuse.

    ⚠ **SUR CE CHEMIN-CI LE GATE EST INERTE PAR CONSTRUCTION, ET C'EST UNE MESURE.** Le SEUL
    poseur du flag dans tout le binaire est `MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour`
    (balayage exhaustif des deux voies d'ecriture, cf. l'encadre en tete de module), et il le pose
    sur le **DRONE**. Or `IsTargetInAttackRangeForSummon` passe le **`parent`** : aucun regime ne
    peut donc rendre `True` ici. Le mirror est ecrit parce que le natif l'ecrit -- pas parce qu'un
    gisement l'exige. C'est aussi ce qui rend le `None` de la face PREDICTION sans consequence :
    la `Scene` n'a pas de table pour ce flag, mais la valeur MESUREE serait `False` de toute
    facon. Point d'ancrage si un jour un second poseur apparait : une entree de plus dans la
    `Scene`, alimentee du MEME canal (`combatSnapshot.units[].unitFlags` publie DEJA toutes les
    valeurs de l'enum) -- aucun capteur neuf n'est requis."""
    if board is None or tile_id is None or attacker_team is None:
        return False
    # `if (UnitExtensions.HasFlag(attacker, 0x1c)) return false;` -- AVANT la boucle, comme le natif.
    if attacker_ignores_ranged_in_melee is True:
        return False
    elev = board.elevation(tile_id)
    for n in board.neighbours(tile_id):
        occ = (occupant_by_tile or {}).get(int(n))
        if occ is None:
            continue                                    # `GetUnit(adj, state) == null`
        team, steppable, targetable = occ
        if team is None or int(team) == int(attacker_team):
            continue                                    # `!IsFriend(attacker, u, state)`
        if steppable:
            continue                                    # `!TileExtensions.HasSteppableUnit(adj)`
        ne = board.elevation(n)
        if elev is not None and ne is not None and abs(int(elev) - int(ne)) >= 2:
            continue                                    # `CanMeleeAttackOverElevationDifference`
        if not targetable:
            continue                                    # `UnitExtensions.IsTargetable(u)`
        return True
    return False


def _is_target_in_attack_range_for_summon(board, tile_id, target_tiles, unit_max_range: int,
                                          attacker_team, occupant_by_tile,
                                          target_is_targetable: bool = True,
                                          attacker_ignores_ranged_in_melee=None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon(parent, unitId, tile,
    target)` -- MIRROR 1:1 du decompile (`IBattleQuery` slot 196) :

        if (target == null || !UnitExtensions.IsTargetable(target)) return false;
        range = 0; foreach (w in GetUnitConfig(unitId).Weapons)
                       range = Math.Max(range, w.Range.HasValue ? w.Range.Value : 1);
        if (DamageCalculations.ShouldApplyRangedInMelee(parent, [tile], state, true)) {
            range = 1;
            if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target)))          return false;
        } else if (range == 1
                   && !TileExtensions.IsAdjacentTo(tile, GetTiles(target)))    return false;
        if (BattleQuery.GetDistance(tile, target) > range)                     return false;
        foreach (t in GetTiles(target))
            if (!<IMovementQuery slot 16>(tile, t, 6, 2).IsNullOrEmpty())      return false;
        if (range == 1)
            return DamageCalculations.CanMeleeAttackOverElevationDifference(
                       tile, EntityExtensions.GetMainTile(target));
        return true;

    LE SLOT 0x10 EST CELUI D'`IMovementQuery`, PAS D'`IBattleQuery` -- et c'est la mesure qui le
    dit, pas le contexte : le service interroge est `this+0x10`, et
    `IdunBattle.Core.Services.BattleQuery$$GetDistance(tileA, tileB)` appelle le slot `9` du MEME
    champ, que `data/symbols/<build>/metadata/interface_slots.tsv` nomme `IMovementQuery 9
    GetDistance/2`. Slot `16` y est `IMovementQuery GetTilesObscuringTerrain/4` -- la surcharge
    ENTITE (la surcharge LISTE est le slot `15`, celui que `TargetingQuery$$GetTilesObscuringTerrain`
    appelle avec `casterTiles`). CONFRONTEE au corps deja porte pour `TargetIsUnobscured` :
    c'est LA MEME fonction native, `IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain`
    -- `TargetingQuery$$IsTargetTileObscured` appelle ce meme slot `16`.

    ⚠ MAIS PAS LE MEME CHEMIN D'ENTREE, ET L'ECART COMPTE : la cascade de ciblage passe par
    `TargetingQuery$$GetTilesObscuringTerrain`, qui GATE sur `TargetingConfiguration.
    EnableObscuringTerrain (+0x10)`, sur `IsFriendOrHasFriendlyUnitOnIt` et sur les bits 25/26 du
    masque, et qui COMPOSE son `ObscuringType`. Ici, RIEN de tout cela : l'appel est DIRECT sur
    `IMovementQuery`, avec les litteraux `(6 = ObscuringType.All, 2)`. Le port appelle donc
    `services.movement_query.get_tiles_obscuring_terrain` (la geometrie) et surtout PAS
    `services.targeting_query.target_is_obscured` (les gardes de la cascade), qui rendrait
    faussement « non obscurci » des que `EnableObscuringTerrain` est faux.

    `target_tiles` = `EntityExtensions$$GetTiles(target)` (la liste des pieds, DANS L'ORDRE : sa
    premiere entree est la main tile de `GetMainTile`). `unit_max_range` = `GetUnitMaxRange(unitId)`
    (mirror `_drone_attack_range`) : le decompile de `BattleQuery$$GetUnitMaxRange` porte LE MEME
    corps que la boucle inline de ce slot -- meme `HasValue ? Value : 1`, meme `Math.Max`.

    `board is None` -> `False` cote appelant (il ne construit alors aucune candidate) ; ici on
    suppose le board present. Un canal d'elevation ou de mur MUET ne peut qu'ELARGIR la zone (cf.
    `movement_query.PositionBoard`), jamais la retrecir : la degradation reste PERMISSIVE et
    NOMMEE."""
    if not target_is_targetable or not target_tiles or board is None:
        return False
    tile_pos = board.coord(tile_id)
    if tile_pos is None:
        return False
    rng = int(unit_max_range)
    # `TileExtensions$$IsAdjacentTo(tile, otherTiles)` = `any(MovementUtil.AreTilesAdjacent(tile, t))`
    # (decompile LU) -- et `are_tiles_adjacent` est justement le mirror d'`AreTilesAdjacent`, porte
    # d'elevation `|dElev| < 2` comprise.
    adjacent = any(bool(are_tiles_adjacent(tile_pos, t, board)) for t in target_tiles)
    if _should_apply_ranged_in_melee_from_tile(board, tile_id, attacker_team, occupant_by_tile,
                                               attacker_ignores_ranged_in_melee):
        rng = 1                                          # le clamp melee, DEPUIS LA TUILE CANDIDATE
        if not adjacent:
            return False
    elif rng == 1 and not adjacent:
        return False
    if min(hexgeo.distance(tile_pos, t) for t in target_tiles) > rng:
        return False                                     # `BattleQuery$$GetDistance` = min sur les pieds
    for t in target_tiles:                               # LIGNE DE VUE, par tuile de la CIBLE
        if get_tiles_obscuring_terrain(board, tile_pos, t, OBSCURING_TYPE_ALL,
                                       BLOCKING_ELEVATION_DIFFERENCE):
            return False
    if rng == 1:
        # `CanMeleeAttackOverElevationDifference(tile, GetMainTile(target))` = `|dElev| < 2`
        # (litteral `iVar1 < 2` du decompile). `GetMainTile` = la tuile du PREMIER pied.
        main = target_tiles[0]
        mtid = board.id_at(int(main[0]), int(main[1]))
        me = board.elevation(mtid) if mtid is not None else None
        ae = board.elevation(tile_id)
        if ae is not None and me is not None and abs(int(ae) - int(me)) >= 2:
            return False
    return True


def _tiles_obscuring_terrain_for(board):
    """L'accesseur `ctx.tiles_obscuring_terrain` pour un `DslContext` bati A LA MAIN (face DECISION).

    Cote RUNNER, `entities_from_state` le fournit lui-meme. Ici la scene n'a pas de `State`, mais la
    geometrie ne depend QUE du board -- et les deux litteraux (`obscuringType = 6 = All`,
    `blockingElevationDifference = 2`) sont ceux du call-site natif, importes de leur foyer."""
    return lambda a, b: get_tiles_obscuring_terrain(board, a, b, OBSCURING_TYPE_ALL,
                                                    BLOCKING_ELEVATION_DIFFERENCE)


def _unobscured_tiles(dctx, from_tiles, tile_id: int) -> bool:
    """LE MAILLON `UnobscuredTiles` DU REPLI DE `MV71SniperDroneSquadAttackAbility$$PickTile`, monte
    en NOEUD DSL depuis #287-r11-r2-r1-r3 :

        sel = SurroundingTiles(...) op_BitwiseAnd Tiles(First(AlreadySpawnedSummons..., 1, 0))
        sel = UnobscuredTiles(Tiles(Target@0x60), sel)                    # <- ICI
        sel = FilterTilesIfCanAttackTargetTileFrom(Caster@0x48, Target@0x60, sel)

    L'artefact natif est un `IdunBattleLogic.Entities.DSLSelectors$$UnobscuredTiles`, donc un ARBRE
    (doctrine #149) -- exactement comme son VOISIN de chaine `FilterTilesIfCanAttackTargetTileFrom`,
    noeud depuis #433-r4-r1. Le collapse imperatif qui vivait ici (`_is_obscured_from_tiles`, une
    boucle sur `get_tiles_obscuring_terrain`) est remplace par
    `entities/selectors/tiles.py::UnobscuredTiles`, qui porte la formule ENTIERE -- y compris le bras
    `caster.Count == 0 -> liste VIDE` que le collapse rendait par `True` (obscurci), c'est-a-dire le
    MEME observable mais par un chemin different.

    Le vehicule est `FixedTileIds`, comme pour le maillon voisin : le collapse ne fournit que
    l'ENTREE (la candidate deja choisie imperativement), la DECISION emerge du noeud.

    Rend VRAI si la tuile est OBSCURCIE (donc a retirer) -- meme polarite que le predicat qu'il
    remplace, pour que les deux call-sites restent lisibles."""
    kept = UnobscuredTiles(FixedTiles([(int(p[0]), int(p[1])) for p in (from_tiles or ())]),
                           FixedTileIds([int(tile_id)])).select(dctx)
    return not kept


def _occupants_by_tile(state: "State", board) -> dict:
    """Le substrat d'`_is_target_in_attack_range_for_summon`, hydrate depuis l'ECS du RUNNER :
    `{id de tuile: (team, steppable, targetable)}` des unites VIVANTES seulement (le natif teste
    `IsAlive` en dernier, donc les cadavres ne comptent pas)."""
    out: dict = {}
    if board is None:
        return out
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if uc is None or oc is None or pc is None or not uc.alive:
            continue
        tid = board.id_at(pc.col, pc.row)
        if tid is None:
            continue
        out[int(tid)] = (oc.team, has_steppable_unit(state, int(eid)),
                         is_targetable(state, int(eid)))
    return out


def _pick_tile(state: "State", caster_id: int, target_id: int, unit_id: str,
               max_summons: int, first_only: bool = False):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PickTile` : renvoie l'id de TUILE choisie, ou None (aucune tuile -> cast no-op,
    le gate de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason`).

    Candidates = tuiles MARCHABLES et LIBRES à distance <= portée du drone de LA CIBLE (slot 0x66 x
    config drone), d'où le drone peut attaquer — ce dernier filtre est
    `IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon` (`IBattleQuery` slot 196),
    PORTE depuis #287-r11-r2-r1 : ligne de vue comprise. Tri = `SortTilesByUtility(list,
    [UtilityBucket[WeightedUtility(7=Tile),
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
    # Le substrat des DEUX etages a substrat d'`IsTargetInAttackRangeForSummon`, monte UNE fois pour
    # toute l'enumeration (il ne depend pas de la candidate).
    occupant_by_tile = _occupants_by_tile(state, board)
    target_tiles = get_unit_feet(state, int(target_id)) or [tpos]   # `EntityExtensions$$GetTiles`
    target_ok = is_targetable(state, int(target_id))                # `UnitExtensions$$IsTargetable`
    # `HasFlag(parent, 0x1c = UnitFlag.IngoreRangedInMelee)` (#287-r11-r2-r1-r2) : le natif lit le
    # drapeau du **parent**, pas du drone. MESURE cote runner (le `UnitFlagsComponent` est dans
    # l'ECS et `load_state` le seede depuis `combatSnapshot.units[].unitFlags`) -> jamais `None`
    # ici, contrairement a la face prediction.
    c_flags = ce.get_component(UnitFlagsComponent)
    caster_ignores_melee = bool(c_flags is not None
                               and c_flags.has(UnitFlag.IngoreRangedInMelee))
    cands = []
    for tid in sorted(board.by_id.keys()):
        if not board.walkable(tid) or tid in occupied:      # CanAddUnit (libre + marchable)
            continue
        info = board.by_id[tid]
        pos = (info["col"], info["row"])
        d_t = hexgeo.distance(pos, tpos)
        if d_t < 1 or d_t > rng:                            # l'ANNEAU (`GetSurroundingTiles`, radius)
            continue
        # « peut attaquer la cible depuis » : le slot 196, PORTE (#287-r11-r2-r1). Il ne se reduit
        # PAS a la distance -- ligne de vue, clamp melee depuis la candidate, elevation.
        if not _is_target_in_attack_range_for_summon(board, tid, target_tiles, rng, coc.team,
                                                     occupant_by_tile, target_ok,
                                                     caster_ignores_melee):
            continue
        cands.append((tid, pos))
    if cands:
        if first_only:
            return cands[0][0]                              # gate GetDynamicInvalidTargetReason (1er candidat)
        elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
        emm = (min(elevs), max(elevs)) if elevs else (None, None)
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
    tid = board.id_at(wp.col, wp.row)
    if tid is None:
        return None
    # `sel = UnobscuredTiles(Tiles(Target@0x60), sel)` -- LIGNE DE VUE du repli, NOEUD DSL depuis
    # #287-r11-r2-r1-r3. Ce maillon-la n'est PAS `IsTargetInAttackRangeForSummon` (le repli ne le
    # rappelle pas) : c'est le selecteur `UnobscuredTilesSelector`, meme geometrie mais sens
    # CIBLE -> candidate. Le `dctx` est celui que le maillon SUIVANT construit deja.
    if _unobscured_tiles(entities_from_state(state, caster_id, target_id),
                         target_tiles, int(tid)):
        return None
    return _filter_can_attack_target_tile_from(state, caster_id, target_id, int(tid))


def _is_melee_attack(state: "State", caster_id: int, target_id: Optional[int]) -> bool:
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$IsMeleeAttack(entities)`
    (mirror), FOYER UNIQUE des DEUX consommateurs natifs — le dispatch de `ExecuteBehaviour` et le
    gate de `GetDynamicInvalidTargetReason`, qui appellent tous deux CETTE methode-la.

    Corps natif, LU :

        trigger = DSLTriggers.IsMeleeAttack(Direct(AbilityOrEffect(this)), Caster@0x48,
                                            <dsl+0x58>, Target@0x60)      # surcharge 4 arguments
        return trigger.<slot +0x188>(entities, 0x20, ...)

    `IdunBattleLogic.Entities.DSLTriggers$$IsMeleeAttack` (surcharge 4 arguments) construit un
    `IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger` — le nom porte l'axe INVERSE, et
    c'est le natif qui l'ecrit : la surcharge « melee » et sa negation
    (`MV71SniperDroneSquadAttackAbility$$HasAttackType`, `type == 1` ->
    `AbilityTrigger$$op_LogicalNot(IsMeleeAttack(...))`) partagent le meme trigger.

    COLLAPSE (celui que `execute_behaviour` applique depuis #61bis, confronte live —
    `docs/rl/case-254-loki-solo-targeting.md`) : « la cible est ADJACENTE au caster ». Il est ecrit
    ICI et pas deux fois : le natif appelle la MEME methode aux deux endroits, donc le port ne doit
    pas pouvoir les faire diverger.

    Positions non resolues -> `False` : le port ne fabrique pas un dispatch melee faute de mesure
    (c'est la branche PERMISSIVE du gate, cf. `mv71_dynamic_invalid_target_reason`)."""
    if target_id is None:
        return False
    ce = state.get_entity(caster_id)
    te = state.get_entity(target_id)
    cp = ce.get_component(PositionComponent) if ce is not None else None
    tp = te.get_component(PositionComponent) if te is not None else None
    if cp is None or tp is None:
        return False
    return are_tiles_adjacent((cp.col, cp.row), (tp.col, tp.row), state.board)


def mv71_dynamic_invalid_target_reason(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason`
    (MIRROR 1:1 du decompile, 4 parametres `caster, casterTiles, target, targetTiles`) :

        entities = default(AbilityEntities);          // memset 0x128
        entities.<+0x08> = caster; entities.<+0x10> = target;
        entities.<+0x18> = caster; entities.<+0x48> = casterTiles;
        if (!IsMeleeAttack(entities) && target != null
            && PickTile(entities, pickFirst: true) == null)
            return 1;                                 // = TargetingRule.ValidRequest
        return 0;

    DEUX lectures que la conversion oblige a faire :

    * le code rendu est le litteral **`1` = `TargetingRule.ValidRequest`**, PAS `2
      TargetMatchesDynamicRule` : c'est le meme emploi « code de refus » que la tete de domaine
      TUILE du filtre statique (cf. `targeting_rule_inventory`, role `REASON`). Recopier `2` par
      analogie avec les autres regles dynamiques aurait ecrit un code FAUX ;
    * `PickTile(pickFirst: true)` n'est PAS « la premiere tuile de l'anneau » : c'est le MEME corps
      que l'execution, REPLI COMPRIS. Quand aucune tuile candidate ne passe le filtre, le natif
      poursuit sur le bloc `HasTooManySummons` (tuile du drone le plus faible, filtree par
      `FilterTilesIfCanAttackTargetTileFrom`) — ce que `_pick_tile` fait deja pour les deux modes.
      Un port qui aurait court-circuite a « anneau vide -> refus » aurait SUR-refuse au cap.

    L'ORDRE d'enumeration de `GetSurroundingTiles` n'a aucune incidence ici : le gate ne teste que
    la NULLITE du retour, jamais QUELLE tuile est rendue.

    Substrat non mesure (`unitId` absent du gameconfig) -> `0` : convention permissive du module,
    jamais un refus invente."""
    if _is_melee_attack(state, caster_id, target_id):
        return 0
    if target_id is None:
        return 0
    consts = (GC.ability(CONFIG) or {}).get("constants") or {}
    unit_id = consts.get("unitId")                       # GetStringConstant(cfg, 0)
    if unit_id is None:
        return 0
    max_summons = int(consts.get("maxSummons") or 3)     # GetNumberConstant(cfg, 0x3c)
    tile = _pick_tile(state, caster_id, target_id, unit_id, max_summons, first_only=True)
    if tile is not None:
        return 0
    return int(TR.ValidRequest)                          # le litteral `1` du decompile


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

    # MEME substrat que la face runner (`_occupants_by_tile`), hydrate depuis la `Scene` : c'est ce
    # qui empeche les deux faces de forker sur `IsTargetInAttackRangeForSummon` (#287-r11-r2-r1).
    #   * `targetable` est CONSTANT a `True` -- ni la `Scene` ni le runner ne posent
    #     `UnitFlag.Untargetable` (`targeting.is_targetable` est constamment vrai) : meme canal muet
    #     des deux cotes, donc pas un fork ;
    #   * `Steppable` passe DEPUIS #287-r11-r2-r1-r2 par le `UnitContext` de la `Scene`
    #     (`scene.ctx(uid)`), et non plus par la borne STATIQUE `entity_trait_names(None, visualId)`.
    #     LE CANAL PRECEDENT ETAIT LE MAUVAIS : `entity_trait_names` documente lui-meme que
    #     `Scene.ctx(uid)` est LE MEME OBJET que le `StatsComponent.ctx` que lit la face runner
    #     (`targeting._unit_traits`), donc passer `None` REDUISAIT volontairement le substrat au kit
    #     gameconfig -- aveugle a tout trait ACCORDE EN BATAILLE (`AddTraitOperation`) ET a la MESURE
    #     live `combatSnapshot.units[].traits`, qui differe du kit DANS LES DEUX SENS (#264 : 5 unites
    #     du seed ont MOINS de traits que leur kit, 48 en ont PLUS). C'etait un fork entre les deux
    #     faces, pas une borne assumee. `ctx` absent -> `entity_trait_names` retombe de lui-meme sur
    #     la borne statique, donc la degradation reste celle d'avant pour une unite hors tables.
    occupant_by_tile = {}
    for u, p in _pos_of.items():
        t = board.id_at(int(p[0]), int(p[1]))
        if t is None:
            continue
        traits = entity_trait_names(scene.ctx(u), scene.vis_by_id.get(u))
        occupant_by_tile[int(t)] = (scene.team(u), UnitTrait.Steppable.name in traits, True)
    cands = []
    for tid in sorted(board.by_id.keys()):
        info = board.by_id[tid]
        pos = (info["col"], info["row"])
        if not board.walkable(tid) or pos in occupied:      # CanAddUnit (libre + marchable)
            continue
        d_t = hexgeo.distance(pos, tpos)
        if d_t < 1 or d_t > rng:                            # l'ANNEAU (`GetSurroundingTiles`, radius)
            continue
        # `attacker_ignores_ranged_in_melee` reste a son defaut `None` = **PAS MESURE** : la `Scene`
        # porte une table par flag (`moved_by_id`, `teleported_by_id`, `active_ability_used_by_id`,
        # `prevent_overkill_by_id`) et aucune pour `UnitFlag.IngoreRangedInMelee`. La degradation est
        # celle du foyer : le clamp melee reste applique, jamais leve sur une non-mesure.
        if not _is_target_in_attack_range_for_summon(board, tid, [tpos], rng, caster_team,
                                                     occupant_by_tile, True, None):
            continue                                        # `IsTargetInAttackRangeForSummon`
        cands.append((tid, pos))
    if cands:
        if first_only:
            return cands[0][1]
        elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
        emm = (min(elevs), max(elevs)) if elevs else (None, None)
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
    tid = board.id_at(wpos[0], wpos[1])
    if tid is None:
        return None
    # MEME dernier maillon que la face runner (`_filter_tiles_if_can_attack_target_tile_from`), la
    # SEULE difference etant l'hydratation : les unites viennent de `_pos_of` (donc le caster est
    # VIRTUELLEMENT sur `parent_pos`, #153), pas de l'ECS. Aucun fork de predicat.
    # ⚠ Le `dctx` est desormais construit AVANT le maillon `UnobscuredTiles` -- qui est un NOEUD DSL
    # depuis #287-r11-r2-r1-r3 et le consomme, comme le maillon suivant. `tiles_obscuring_terrain`
    # est pose ICI parce que ce contexte-la est bati a la main (face DECISION) : `entities_from_state`
    # le fournit tout seul cote runner.
    units = [{"id": u, "team": scene.team(u), "alive": True, "hp": int(scene.hp(u) or 0),
              "pos": {"col": int(p[0]), "row": int(p[1])}} for u, p in _pos_of.items()]
    by_id = {d["id"]: d for d in units}
    dctx = DslContext(units=units, caster=by_id.get(att_id), target=by_id.get(tgt_id), board=board,
                      tiles_obscuring_terrain=_tiles_obscuring_terrain_for(board))
    # MEME maillon `UnobscuredTiles` que la face runner (#287-r11-r2-r1, noeud depuis -r3).
    if _unobscured_tiles(dctx, [tpos], int(tid)):
        return None
    if _filter_tiles_if_can_attack_target_tile_from(dctx, int(tid)) is None:
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

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """La regle-delegue du bit `TargetMatchesDynamicRule` pose ci-dessus (#287-r11-r2) —
        `MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason`, mirror dans
        `mv71_dynamic_invalid_target_reason`.

        ⚠ Elle REMPLACE celle de l'attaque normale generique : le corps natif ne rappelle JAMAIS
        `ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason` (le test d'arme). 1076 EST
        l'attaque normale de `tauMarksman`, donc le porteur consulte est
        `targeting._NormalAttackTargeting`, qui aiguille desormais vers CETTE surcharge — mirror du
        fait que le delegue `options+0x38` est lie au slot vtable `+0x480` de l'INSTANCE."""
        return mv71_dynamic_invalid_target_reason(state, caster_id, target_id)

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
        # Le prédicat vit dans `_is_melee_attack` (#287-r11-r2) : le natif appelle la MÊME méthode
        # ici et dans son gate de ciblage, le port ne doit donc pas pouvoir les faire diverger.
        if _is_melee_attack(state, caster_id, target_id):
            atk = AttackDamageOperation.execute(state, caster_id, target_id)
            after = []
            if atk is not None:
                from ...operations.triggers.dispatch.attack import after_hit_normal_attack
                # `finish_attack` (#437) = le vecteur `On(9)`, desormais emis DANS l'operation ;
                # remis EN TETE (ordre natif) pour garder le canal observable.
                after = (atk.get("finish_attack") or []) + after_hit_normal_attack(
                    state, caster_id, target_id,
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
        # `AddFlag(Get(drone), 0x1c = UnitFlag.IngoreRangedInMelee)` (#287-r11-r2-r1-r2) -- ce
        # behaviour est le SEUL poseur du flag dans tout le binaire, et son porteur est le DRONE.
        # TRANSITOIRE : pose ici, retire juste apres l'attaque, exactement comme la chaine DSL
        # `AddFlag & UseActiveAbility & RemoveFlag`. L'etat final est donc INCHANGE.
        # ⚠ INERTE PAR CE CHEMIN, et la cause est NOMMEE : le seul consommateur porte du gate est
        # `targeting.get_range` (sous `options.force_melee_target`), que ce raccourci ne traverse
        # pas -- le port appelle `AttackDamageOperation` DIRECTEMENT la ou le natif passe par la
        # cascade `ActiveAbilityOperation`. Le mirror est ecrit parce que le natif l'ecrit, et il
        # arme le gate le jour ou l'execution du drone passera par la cascade.
        d_ent = state.get_entity(int(drone_id))
        d_flags = (d_ent.get_component(UnitFlagsComponent)
                   or d_ent.add_component(UnitFlagsComponent())) if d_ent is not None else None
        if d_flags is not None:
            d_flags.add(UnitFlag.IngoreRangedInMelee)
        # l'attaque COMMANDÉE : l'attaque normale DU DRONE (arme choisie par distance — r4 Piercing à
        # distance, Physical au contact), stats lues via GetStat -> les OVERRIDES s'appliquent.
        atk = AttackDamageOperation.execute(state, drone_id, target_id)
        if d_flags is not None:
            d_flags.remove(UnitFlag.IngoreRangedInMelee)     # `RemoveFlag(Get(drone), 0x1c)`
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
