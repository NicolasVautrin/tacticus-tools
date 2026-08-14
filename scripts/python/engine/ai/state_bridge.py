"""`build_from_state` — bridge `State`(runner) -> `AiDecisionContext` (100% offline, SANS RPC). #65.

Le decideur `DefaultAiUnitTactic.calculate_next_action` ne consomme QU'un `AiDecisionContext` ; ce module
le construit ENTIEREMENT depuis un `State` runner (composants + board + gameconfig), en remplacement de la
couture RPC de `context.build` (decisionView/observeBattle/tileMeta/pathDistToEnemies/aiMovableTiles/
combatSnapshot). C'est ce qui permet a `StartTurnOperation` de jouer les summons (unites `ai_controlled`)
via le PLAYBOOK COMPLET offline (cf. docs/rl/runner-engine.md #65).

Faits cles (map de la passe RE / agent) :
 - Le spine ne lit QUE `ctx.scene` pour la prediction (jamais `predictor`/`sctx`) et `ctx.cur` est mort.
 - `scene = Scene.from_state(state)` : le `StatsComponent.ctx` d'une unite EST le meme `UnitContext` que le
   predicteur cache ; `State.effects` EST l'`EffectsState` ; `State.board` = elevation + adjacence hex.
 - `plans` = enumeration offline {uid: {evals:[{abilityId,targetId,rankCount,ranked:[{col,row}]}]}} pour
   l'attaque normale ET les abilities ACTIVES d'attaque (SLICE 2). On n'a pas a porter le heuristique
   `GetBest`, seulement le SET (origine + tuiles de move d'ou l'attaque est legale, portee =
   `_ability_reach`) : `_best_attack` fait un argmax STRICT et impose LUI-MEME le rang de l'ORIGINE
   (seul rang qui porte un tie-break natif, cf. R1). L'ordre relatif des autres tuiles est indifferent.
 - `ability_targets` (SLICE 2) = `ability_targets_offline` (heal/repair/summon/Nova) : enumere l'UNION des cibles
   legales sur toutes les tuiles-caster, mirror `IdunBattle.AI.Playbook.BasePlaybook$$GetAllValidTargetsFromAllPossibleMovementTiles` /
   `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` (kind/portee derives de gameconfig, cf. `_ability_kind`).

Attaque normale : son ActiveAbilityType CONCRET per-unite (Loki_NormalAttack=69, ...) est un etat RUNTIME
(`ActiveAbilityComponent.NormalAttackType`) NON derivable de gameconfig -> on utilise l'id SYNTHETIQUE 17
(`NormalAttack` generique). C'est SANS impact : la prediction lit l'arme du `ctx` (pas l'id), et l'apply de
l'attaque normale passe par `AttackUnitMessage` (sans id). Les abilities ACTIVES, elles, ont un nom == leur
membre d'enum -> id resolu par reverse-lookup `ACTIVE_ABILITY_TYPE`.

Gaps no-op documentes : `is_temporary_by_pos`/`effects_by_pos` = {} (tuiles temporaires/hazard non portees,
~0 sur board plat). `pathdist_by_pos` n'en est PLUS un depuis `#17-off` : c'est le mirror offline de
`FindClosestEnemy` + `GetMinDistanceToEnemy` (ClosestEnemy FIGE, `GetPath(type=1)` compte des NOEUDS),
cf. `_pathdist_to_enemies`.
"""
from __future__ import annotations

import functools
from typing import Any

import gameconfig as GC
import hexgeo

from engine.playbook.scene import Scene
from engine.runner.components import (StatsComponent, OwnerComponent, PositionComponent,
                                      HealthComponent, UnitComponent)
from engine.entities.pathfinding.ignore_terrain_pathfinder import get_path_node_counts
from engine.entities.pathfinding.tile_blocking import make_can_continue
from engine.entities.pathfinding.pathfinders import movable_positions_for_unit
from engine.services.movement_query import (synapse_tiles_for, titanhammer_target_tiles_for,
                                            unit_has_effect_fn)
from engine.entities.effect_type import EffectType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import entity_trait_names
from engine.services.custom_normal_attack import has_normal_attack
from engine.utilities.move import UtilityMovementCase

NORMAL_ATTACK_ID = int(ActiveAbilityType.NormalAttack)   # 17 (id synthetique offline ; cf. en-tete) #158
TELEPORT_STRIKE_TELEPORTING_IN = int(EffectType.TeleportStrike_TeleportingIn)  # 1035 — effet deep-strike -> unite NON-CIBLABLE (#158)
STORMBOYZ_STRIKE_TELEPORTING_IN = int(EffectType.StormboyzStrike_TeleportingIn)  # 1140 (#448-r2b)
#: Domaine de `UntargetableEffect` (foyer unique : `engine.entities.effects.aura_selectors`).
#: Le flag ne vient PAS de l'effet feuille -- `UntargetableEffect$$ApplyInternal` fait
#: `IdunBattle.Entities.Components.UnitFlagsComponent$$Add(0x11)` sur la CIBLE pour TOUTE
#: sous-classe. Contenu, fermeture native et residus : cf. le commentaire du foyer.
from engine.entities.effects.aura_selectors import UNTARGETABLE_EFFECT_TYPES  # noqa: E402
from engine.ai.context import AiDecisionContext, _enemies, action_tiles_for
from engine.entities.stats import StatType
from engine.playbook.noncomparable import is_noncomp
from engine.runner.abilities.targeting import refuses_all_enemy_targets, targeting_options_for
from engine.runner.components import EffectsOwnedComponent, is_machine_of_war
from engine.runner.components import is_machine_of_war
from engine.weights import load as _load
from engine.runner.abilities.targeting_rule import TargetingRule as _TR


def _is_untargetable(state, uid: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsTargetable` = `!HasFlag(Untargetable=0x11)`. Signal OFFLINE du deep-strike :
    une unite en cours de teleportation est non-ciblable jusqu'a son atterrissage (ground truth live
    ds_landing pour 1035 ; pour 1140 le porteur est en plus HORS PLATEAU). -> exclue de
    l'enumeration de cibles (attaque/ability). Domaine : `UNTARGETABLE_EFFECT_TYPES` ci-dessus."""
    if state.effects is None:
        return False
    return any(state.effects.has_effect(uid, effect_type=t) for t in UNTARGETABLE_EFFECT_TYPES)


@functools.lru_cache(maxsize=1)
def _weights():
    """Poids BC (statiques) charges 1x. `engine.weights.load()`."""
    return _load()


@functools.lru_cache(maxsize=None)
def _granted_abilities(vid: str, passive_abilities: tuple | None = None) -> tuple:
    """Abilities ACTIVES accordees au runtime par un `passiveAbilities` de l'unite (absentes de
    `activeAbilities` — le natif les peuple dans l'ActiveAbilityComponent VIA le passive). DERIVEES DU PASSIVE
    (aucune table hardcodee) : le natif nomme la classe accordee `<Passive>_HealAbility` = membre d'enum
    `Heal_<Passive>` (ex. passive `TwistedScience` -> `TwistedScience_HealAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.TwistedScience_HealAbility$$ExecuteBehaviour`
    = enum `Heal_TwistedScience` 1167). Donc pour chaque passive P on resout l'enum `Heal_<P>` s'il existe.
    C'est le PASSIVE (donnee jeu) + la convention de nommage NATIVE (enum) qui donnent l'ability — pas un
    mapping invente. (Couvre les grants HEAL ; d'autres familles de grant = extension a confirmer.)

    SUBSTRAT — TRI-ETAT (#931-r2), meme discipline que `services.custom_normal_attack` :
      * `passive_abilities` = un TUPLE (fut-il VIDE) -> c'est la MESURE de l'entite
        (`UnitContext.passive_abilities`, hierarchie 2 du `TriggeredAbilityComponent`, cf.
        `runner.snapshot.PASSIVE_HIERARCHY`) : elle prime, sans exception ;
      * `None` -> canal MUET, repli sur le KIT gameconfig (`GC.unit(vid).passiveAbilities`).

    POURQUOI. Le natif fait le swap depuis `UnitConfiguration.PassiveAbilities`
    (`...TwistedScienceAbility$$CreateBehaviour`, `On(AbilityInit) & OwnerIsActor`), c'est-a-dire un
    fait d'ENTITE — `BC.Units[].PassiveAbilities`. Le KIT gameconfig coincide tant que personne ne
    touche a la liste, et DIVERGE des qu'un montage la modifie : tout bras
    `catalog_inject.write_grafted_seed_bc(..., replace=True)` REMPLACE la liste, donc une unite
    greffee de `TwistedScience` recevrait `1167` cote natif et pas cote face DECISION (et
    symetriquement pour une unite dont le passif est retire). Meme vice de substrat que
    #264 / #366-r1 / #419-r1-tr14-r5.

    Le tuple est exige (et non une liste) parce que ce foyer est `lru_cache` : une entree non
    hashable leverait, et une entree MUABLE ferait servir un cache pour une valeur qui a change."""
    import enum_maps as EM
    rev = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    source = (passive_abilities if passive_abilities is not None
              else ((GC.unit(vid) or {}).get("passiveAbilities") or []))
    out: list = []
    for p in source:
        nm = f"Heal_{p}"
        aid = rev.get(nm)
        if aid is not None:
            out.append((int(aid), nm))
    return tuple(out)


@functools.lru_cache(maxsize=None)
def _abilities_of(vid: str, passive_abilities: tuple | None = None,
                  traits: tuple | None = None) -> tuple:
    """Abilities de l'unite reconstruites depuis gameconfig : l'attaque normale (id synthetique 17 si l'unite a
    une arme) + `activeAbilities` (nom == membre d'enum -> id via reverse ACTIVE_ABILITY_TYPE) + les abilities
    ACCORDEES par un passive (`_granted_abilities`, DERIVEES du passive, ex. TwistedScience -> Heal 1167) + les
    abilities DERIVEES D'UN TRAIT (`entities.active_abilities.derived_active_ability_ids`). Une active dont le
    nom n'est pas dans l'enum est ignoree.

    `passive_abilities` : le TRI-ETAT de `_granted_abilities` (mesure d'entite / `None` = repli kit).

    `traits` (#1015-r1) : les NOMS de traits de l'ENTITE (`entity_trait_names(ctx, vid)`, rendus hashables),
    `None` = canal muet -> repli sur le KIT gameconfig. C'est le pendant EXACT, sur la troisieme liste de la
    `UnitConfiguration`, de ce que `passive_abilities` fait sur la deuxieme -- meme forme de substrat (#264),
    meme tri-etat. Le natif lit `config@+0xd0 = UnitConfiguration.Traits` dans
    `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities`, PAS le kit.

    ⚠ CE QUE CETTE 4e SOURCE REPARE (mesure #1015-r1) : `18 Heal` est accordee par le seul TRAIT `Healer`
    (18 porteurs, dont 6 en lineup) et n'apparait dans AUCUN `activeAbilities` gameconfig. Sans elle, un
    `adeptHospitaller` / `bloodSanguinary` / `deathRotbone` / `ultraApothecary` n'avait AUCUNE ability de soin
    cote decideur offline : `_heal_candidates` filtre `me["abilities"]` sur `"Heal" in name`, donc il rendait
    `[]` -- degradation MUETTE (ni erreur, ni cast refuse : simplement une action que le natif propose et que
    le port ne voyait pas). Meme forme pour `28 Repair` / trait `Mechanic`.

    L'attaque normale et les `activeAbilities`, eux, restent du kit : borne NOMMEE, pas un oubli."""
    import enum_maps as EM
    from ..entities.active_abilities import derived_active_ability_ids
    rev = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    gu = GC.unit(vid) or {}
    out: list = []
    if gu.get("weapons"):
        out.append((NORMAL_ATTACK_ID, "NormalAttack"))
    for key in (gu.get("activeAbilities") or []):
        aid = rev.get(key)
        if aid is not None:
            out.append((int(aid), key))
    for (aid, name) in _granted_abilities(vid, passive_abilities):   # accordees par passive
        if not any(a[0] == aid for a in out):
            out.append((int(aid), name))
    # DERIVEES D'UN TRAIT -- `UnitFactory$$AddDerivedAbilities` 3e boucle, moins le
    # `RemoveActiveAbility` du passif substitutif (`TwistedScience`/`HealingBalms`/`GalvanicField`).
    # Les DEUX substrats sont pris au meme tri-etat : mesure d'entite quand elle existe, kit sinon.
    _traits = traits if traits is not None else tuple(gu.get("traits") or ())
    _passives = (passive_abilities if passive_abilities is not None
                 else tuple(gu.get("passiveAbilities") or ()))
    for aid in derived_active_ability_ids(_traits, _passives):
        if not any(a[0] == aid for a in out):
            # ⚠ Le NOM vient de `EM.ACTIVE_ABILITY_TYPE` (sens `{id: nom}`), pas de `rev` (`{nom: id}`) :
            # ces derivees N'ONT AUCUNE entree gameconfig, donc aucun nom de kit ne les designe. Et il
            # n'est pas decoratif -- `ActionGenerators._heal_candidates` selectionne les abilities de
            # soin par `"Heal" in ab["name"]`, donc un `str(aid)` de repli les rendrait invisibles au
            # decideur, exactement le trou qu'on repare.
            out.append((int(aid), EM.ACTIVE_ABILITY_TYPE.get(int(aid)) or str(aid)))
    return tuple(out)


def measured_passive_abilities(ctx) -> tuple | None:
    """Le TRI-ETAT `UnitContext.passive_abilities`, rendu HASHABLE pour les foyers `lru_cache`.

    `None` = canal MUET (pas de `UnitContext`, ou l'attribut jamais seede) -> les appelants
    retombent sur le KIT. Un tuple VIDE est une MESURE (« cette entite ne porte aucun passif »),
    et surtout PAS un `or ()` de repli : les deux se lisent differemment."""
    pas = getattr(ctx, "passive_abilities", None) if ctx is not None else None
    return None if pas is None else tuple(pas)


def _max_attack_range(vid: str) -> int:
    """Portee d'attaque MAX = max(Range des armes) ; melee (Range absent) -> 1. Sert de rayon d'enumeration
    des tuiles de tir legales (identique a triggers._max_attack_range)."""
    gu = GC.unit(vid) or {}
    ranges = [int(w.get("Range") or 0) for w in (gu.get("weapons") or [])]
    mx = max(ranges) if ranges else 0
    return mx if mx > 0 else 1


def _move_range(ctx, vid: str) -> int:
    """Portee de deplacement (tuiles). Priorite au STAT movement LIVE (effet-inclusif, `StatType.MOVEMENT=1`)
    quand il est seede (State charge d'un combatSnapshot — c'est la source que `test_pathfinding_live` confronte
    a `aiMovableTiles`) ; sinon fallback gameconfig `Movement` (cas du summon spawne offline sans combatSnapshot,
    ou la base sans bonus = la bonne portee). 0 -> unite immobile.

    NB : la PORTEE (nombre de tuiles) = stat Movement pour TOUS les pathfinders (Walk comme Fly ; le vol
    change la TRAVERSEE, pas la portee). Le FlyPathfinder (Flying/Burrow) est desormais reproduit par
    `fly_pathfinder` (`_move_tiles` choisit l'arete). Reste non porte : le TeleportStrike (deep-strike =
    tranche deploiement) et les tuiles-hazard temporaires."""
    mv = ctx.get_stat(int(StatType.MOVEMENT)) if ctx is not None else 0
    if mv and mv > 0:
        return int(mv)
    return int((GC.unit(vid) or {}).get("Movement") or 0)


def _occupants(state) -> dict:
    """{tile_id -> team} des unites VIVANTES positionnees (bloque le pathfinding : ennemi bloque, allie passe)."""
    board = state.board
    occ: dict = {}
    if board is None:
        return occ
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if uc is None or not uc.alive or oc is None or pc is None:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ[t] = oc.team
    return occ


def _board_topology_maps(board) -> tuple[dict, dict, dict, dict, dict]:
    """Mirror OFFLINE des seams boardGraph du contexte LIVE (`context._board_tile_ids/_board_neighbours/
    _board_walkable/_board_terrain`), construits depuis `State.board` (memes tuiles boardGraph) :
      - `tile_id_by_pos` {(col,row): tileEntityId} : id de tuile (cible d'une self-cast AoE = MainTile) ;
      - `neigh_by_pos`   {(col,row): [voisins (col,row) ORDRE NATIF GetAdjacentTiles]} : depuis le champ BRUT
        `neighbours` du boardGraph (PAS `board.neighbours` evenq/sorted), pour preserver l'ordre natif dont
        depend la cible exacte de Gauntlets (#117, SortReverse sur le ring-1 natif) ;
      - `walkable_by_pos` {(col,row): walkable} : gate STATIQUE de placement (CanAddUnit #116) ;
      - `terrain_by_pos` {(col,row): tileDefId} : covers HÉBERGÉS par le terrain (TileEffects Loop2, case-37).
      - `is_wall_by_pos`  {(col,row): isWall} : `TileComponent+0x41`, volet MURS de la LIGNE DE VUE
        (#433-r4-r2-r1-r2). Il vient du MEME boardGraph que `walkable`, mais ne s'en deduit pas :
        `IsWalkable` agrege le mur ET le terrain infranchissable.
    Board absent -> 5 dicts vides (consumers gates ; sans board, ni placement ni Gauntlets ni cover)."""
    if board is None:
        return {}, {}, {}, {}, {}
    tiles = list(board.by_id.values())
    id2pos = {t["id"]: (t["col"], t["row"]) for t in tiles}
    tile_id_by_pos = {(t["col"], t["row"]): t["id"] for t in tiles}
    neigh_by_pos = {(t["col"], t["row"]):
                    [id2pos[n] for n in (t.get("neighbours") or []) if n in id2pos]
                    for t in tiles}
    walkable_by_pos = {(t["col"], t["row"]): bool(t.get("walkable")) for t in tiles}
    terrain_by_pos = {(t["col"], t["row"]): t.get("tileDefId") for t in tiles}
    is_wall_by_pos = {(t["col"], t["row"]): bool(t.get("isWall")) for t in tiles}
    return tile_id_by_pos, neigh_by_pos, walkable_by_pos, terrain_by_pos, is_wall_by_pos


def _board_fog_map(board) -> dict:
    """`{(col,row): isInFog}` -- mirror OFFLINE de `context._board_is_in_fog` (boardGraph `isInFog`
    = `TileComponent+0x40`). Avec `walkable_by_pos`, c'est le substrat de l'etage AMONT
    `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` (#433-r4-r2-r1-r2-r2-r1) :
    `TileExtensions$$IsWalkable(t, checkFog: true)` agrege les DEUX volets, et `IsWalkableTile`
    (donc `walkable`) n'en rend que le premier.

    FONCTION SEPAREE, et non un 6e element de `_board_topology_maps` : ce tuple positionnel est
    deballe par deux appelants, et l'allonger casserait celui qui n'en a pas besoin.

    TRI-ETAT STRICT, et c'est ce qui la distingue de ses voisines : un board dont AUCUNE tuile ne
    PORTE la cle rend `{}` (canal muet), jamais un dict de `False` -- ce dernier se lirait
    << mesure : aucune tuile en fog >>, alors que c'est << non mesure >>. L'erreur serait du bon
    cote (permissif), mais elle MENTIRAIT, et c'est ce qui la rend inacceptable.
    Board absent -> `{}` aussi."""
    if board is None:
        return {}
    tiles = list(board.by_id.values())
    if not any("isInFog" in t for t in tiles):
        return {}
    return {(t["col"], t["row"]): bool(t.get("isInFog")) for t in tiles}


def _move_tiles(state, uid: int, vid: str, my_team: int, origin: tuple | None,
                override_range: int | None = None) -> list:
    """Tuiles d'ARRET atteignables de `uid` (mirror `aiMovableTiles`) = `WalkPathfinder.get_movable_positions`
    a portee `Movement`. [] si pas de board / origine / Movement=0. Forme `[{col,row}]` (comme le RPC).

    `override_range` (#996-r1) = le `MovementOptions.overrideRange` (`Nullable<int>` a `options+0x04`)
    que `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` remplit depuis le 3e
    argument de `ABaseAiUnitTactic$$GenerateActionTiles`. VERBATIM du decompile
    (`IdunBattle.Core.Services.MovementQuery$$FindAnyOrAllMoveableTiles`) :

        range = options.overrideRange.HasValue ? options.overrideRange.Value
                                               : StatComponent.get_CurrentValue(<stat Movement>);

    -- l'override REMPLACE la portee, il ne l'annule pas. `0` reduit donc l'ensemble a la seule
    graine de l'`OrderedSet` (la tuile courante), et c'est un CAS PARTICULIER de la meme formule,
    pas une regle a part."""
    board = state.board
    if board is None or origin is None:
        return []
    otile = board.id_at(origin[0], origin[1])
    me = state.get_entity(uid)
    sc = me.get_component(StatsComponent) if me is not None else None
    depth = (_move_range(sc.ctx if sc is not None else None, vid) if override_range is None
             else int(override_range))
    if otile is None or depth <= 0:
        return []
    # Selection du pathfinder = `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit`,
    # porte ENTIER dans `entities.pathfinding.pathfinders.movable_positions_for_unit` (le foyer que
    # partagent les trois consommateurs). DEUX axes, pas un : `UnitExtensions$$IsLikeFlying`
    # (Flying/Burrow -> FlyPathfinder, ignore elevation + unites) ET la branche MOUVEMENT SPECIAL
    # (#381-r5 : quatre effets « je descends du ciel » -> un `ATeleportPathfinder`, pool
    # board-wide). Portee = meme stat Movement dans tous les cas.
    traits = (sc.ctx.traits if sc is not None else None) or []
    # #131 : gate d'EXPANSION `BasePathfinder$$NodesInNextLevel` -> `IsValidContinuePathTile`. Une
    # tuile portant `BlockEnteringUnits` (Swamp) est un CUL-DE-SAC de la flood-fill (elle reste un
    # stop legal). Sans lui le port sur-atteint et la passe IA choisit une tuile ILLEGALE (case-r5).
    # `board=` est OBLIGATOIRE ici (residu case-224 SS4, ferme) : la plupart des etats qui arrivent
    # dans `_move_tiles` sont charges SANS le canal OPT-IN `load_state(tiles=tileMeta)`, donc
    # `state.effects` ne porte AUCUN effet de tuile et le gate serait INERTE **en silence**. Le board
    # fournit alors le repli TERRAIN (`terrain_blocks_entering` : le tile-def Swamp heberge
    # `ThornsBlockMovementAbility`, qui pose `BlockEnteringUnits` au setup). MESURE avant/apres
    # (`probe_pathfinding_overreach`) : sans lui MC1_67/777 sur-atteint (2,3) depuis la Swamp (1,3).
    _cc = make_can_continue(state.effects, traits, board=board)
    _, stop = movable_positions_for_unit(
        board, otile, depth, _occupants(state), my_team, traits=traits,
        has_effect=unit_has_effect_fn(state, uid), can_continue=_cc,
        teleport_target_tiles=titanhammer_target_tiles_for(state, board, my_team),
        synapse_tiles=synapse_tiles_for(state, board, my_team))
    out = []
    for t in stop:
        c, r = board.coord(t)
        out.append({"col": c, "row": r})
    return out


def _pathdist_to_enemies(state, uid: int, my_team: int, enemy_positions: list,
                         origin=None, enemy_ids: list | None = None) -> tuple:
    """`{(col,row): pathDist}` OFFLINE, mirror 1:1 du couple natif qui alimente la feuille de
    mouvement `MinDistanceToClosestEnemy(17)` — et pendant offline EXACT du RPC `pathDistToEnemies` :

      1. `IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext`
         fige **UN** `ClosestEnemy` = argmin de la distance depuis la tuile COURANTE sur les ennemis
         deja filtres par l'appelant (`!CurrentOwnerIsEnvironment` / `IsTargetable` /
         `!IsIrrelevantObject` / vivant / `GetOnlyTargets` -> `tgt_epos`), avec le filtre `d > 0` et une
         comparaison `d < bestDist` **STRICTE** (`bestDist` = `int.MinValue`) : a egalite, le PREMIER
         de l'enumeration gagne.
      2. `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` mesure
         ensuite chaque tuile candidate vers CE seul ennemi (MIN sur son footprint), par
         `IPathfinders.GetPath(type=1, unit, tuile, tuileEnnemie, null)` dont il lit `route+0x18` =
         `List._size` : un compte de **NOEUDS**, extremites incluses (`aretes + 1`).

    ⚠ `PathfinderType = 1` est un **LITTERAL** : le natif mesure cette distance avec le MEME
    pathfinder pour tout le monde, y compris une unite VOLANTE (seul
    `MovementActionGenerator$$GetDistanceToEnemy`, qui choisit le ClosestEnemy, derive son type de
    l'unite : `(movementType == 3) + 1`). D'ou l'absence de `fly_is_valid_path_node` ici, alors que
    `_move_tiles` l'utilise bien. Et le type 1 n'est PAS le `WalkPathfinder` de `_move_tiles` : c'est
    `ignore_terrain_pathfinder` (aucun blocage par occupant, cout `10 + IsFilled`) — cf. son en-tete,
    la difference est MESUREE, pas supposee.

    Ecarts de port ASSUMES, faute de source offline : le footprint de l'ennemi est reduit a sa tuile
    principale (`PositionComponent`, comme le RPC live qui lit `GetMainTile`) — exact pour toute
    unite mono-tuile ; et l'ordre d'enumeration est celui de `State.entities`, pas de
    `IdunBattle.Entities.StateExtensions$$GetAllEnemyUnitsOfUnit` — il ne mord que sur un tie de
    distance entre deux ennemis.

    Rend `(pathdist_by_pos, closest_enemy_id)`. `closest_enemy_id is None` == `ClosestEnemy == null`
    cote natif — c'est le GATE 3 de la feuille MinDist (#236), a ne pas confondre avec « le port n'a
    aucune source de distance » : quand `board`/`origin` manquent on rend `(None, None)`, ou le
    PREMIER `None` signale precisement cette indisponibilite (le case n'est alors pas construit).
    `enemy_ids` (facultatif, aligne sur `enemy_positions`) porte l'identite retenue."""
    board = state.board
    if board is None or origin is None:
        return None, None
    otile = board.id_at(origin[0], origin[1])
    if otile is None:
        return None, None
    if not enemy_positions:                   # aucun candidat -> `ClosestEnemy == null` (gate 3)
        return {}, None
    occ = _occupants(state)                   # `IsFilled` du `WeightCost` (PAS un gate de passage)

    best_counts = None
    best_dist = None
    best_id = None
    ids = list(enemy_ids or ())
    for i, (c, r) in enumerate(enemy_positions):
        etile = board.id_at(c, r)
        if etile is None:
            continue
        counts = get_path_node_counts(board, etile, occ)
        d = counts.get(otile)
        if d is None or d <= 0:               # `d.HasValue && d.Value > 0`
            continue
        if best_dist is None or d < best_dist:   # `<` STRICT -> premier-gagne
            best_dist, best_counts = d, counts
            best_id = ids[i] if i < len(ids) else None
    if best_counts is None:
        return {}, None                       # aucun ennemi joignable -> `ClosestEnemy == null`
    return {board.coord(t): n for t, n in best_counts.items()}, best_id


# --- Classification d'ability (SLICE 2) — mirror IdunBattle.Core.Services.TargetingQuery$$GetRange + le TargetsSelector DSL
#     par-ability (kind non-gameconfig -> derive de la SIGNATURE des constants, exact pour attack/heal/repair/
#     summon, heuristique self pour le residuel). Portee = constants.range sinon attackRangeType sinon arme. ----
# Enums d'ability heal/repair dont `GC.ability` = template de base a CONFIG VIDE : le signal generique
# (`hpToHeal`/`hpToRepair`, cf. `_has_heal_magnitude`) ne peut pas les capter -> gate par ID = l'enum
# d'ability natif `ActiveAbilityType` (une distinction REELLE du jeu, doctrine gate-justifie). Tous les
# autres heals/repairs (dont la config PORTE `hpToHeal`/`hpToRepair`) passent par le chemin generique.
# #270-r1-r1 : membres nommes -- le NOM etait deja au site, l'ordinal ne designait rien (`8` vaut
# aussi `UnitTrait.Drunk`, et c'est bien `ActiveAbilityType` que la prose ci-dessus nomme).
HEAL_ABILITY_IDS = frozenset({ActiveAbilityType.MassHeal,              # 8
                              ActiveAbilityType.Heal,                  # 18
                              ActiveAbilityType.Heal_TwistedScience,   # 1167
                              ActiveAbilityType.HealingBalms_Heal})    # 1212
# 82 `MechRepair` et 84 `BattleTinkererRepair` RETIRES (#270) : le build `rnca9r7q6c` ne porte plus
# ces membres d'`ActiveAbilityType` (confirme par `dumpEnum` au runtime, par `classes.tsv` -- aucune
# classe `<Nom>Ability` -- et par le gameconfig, qui ne configure aucune ability de ces noms). Ils
# etaient INERTES : le jeu ne peut pas les emettre. Garde : `probe_270_active_ability_type_drift.py`.
REPAIR_ABILITY_IDS = frozenset({ActiveAbilityType.Repair,                  # 28
                                ActiveAbilityType.Repair_GalvanicField})   # 1119


def _resolve_ability(ability_id: int):
    """(name, cfg) d'une ability : name via l'enum `ACTIVE_ABILITY_TYPE` (id->nom), cfg via gameconfig."""
    import enum_maps as EM
    name = EM.ACTIVE_ABILITY_TYPE.get(int(ability_id))
    return (name or ""), (GC.ability(name) if name else None) or {}


def _has_heal_magnitude(cfg: dict) -> bool:
    """Signal HEAL generique : presence de l'operande `hpToHeal` du `TargetsSelector` natif (magnitude de
    soin lue par la formule de heal). Remplace le substring de nom (doctrine : gate justifie contre le natif)."""
    return any(k.startswith("hpToHeal") for k in (cfg.get("variables") or {}))


def _has_repair_magnitude(cfg: dict) -> bool:
    """Signal REPAIR generique : presence de l'operande `hpToRepair` (magnitude de reparation)."""
    return any(k.startswith("hpToRepair") for k in (cfg.get("variables") or {}))


def _refuses_all_enemy_targets(ability_id: int) -> bool:
    """VETO NATIF de la route ENNEMIE : le masque `TargetingOptions` RE-LU de l'ability refuse-t-il
    TOUTE cible ennemie (`TargetIsFriendly` / `TargetIsCaster`) ? Masque non lu -> False (aucun veto,
    la classification gameconfig garde la main -- meme convention permissive que
    `engine.runner.abilities.targeting`).

    POURQUOI CE VETO EXISTE : le generateur d'action offline construit ses tuiles legales par la
    SEULE distance hex, la ou son homologue natif
    `IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom` filtre CHAQUE tuile candidate par
    `AttackQuery.GetInvalidTargetReason(unit, new UnitPosition(tile), target, ability)` et n'en garde
    aucune quand la cascade rompt. Une ability `TargetIsFriendly` (ex. 1100 SorcerousFacade) rompt
    sur TOUS les ennemis : le natif ne rend AUCUNE tuile, donc AUCUNE paire (ability, ennemi). Sans
    ce veto le moteur en fabrique une par ennemi -- des actions que le natif REFUSE.

    Strictement SOUSTRACTIF, et c'est voulu : jamais de PROMOTION vers la route ennemie (un masque
    qui porte `TargetIsEnemy` sans `damageProfile` reste hors de `_best_attack`, cf. le residu
    « masque enemy mais non routee » de `probe_217_phantom_action_routing.py`)."""
    opts = targeting_options_for(ability_id)
    return opts is not None and refuses_all_enemy_targets(opts)


def _is_attack_ability(ability_id: int, cfg: dict) -> bool:
    """ROUTE d'ATTAQUE : cette ability entre-t-elle dans `attackPlans` / `_best_attack` ? ssi le
    masque natif ne l'interdit pas ET `constants.damageProfile` present ET l'ability n'est PAS deja
    routee vers un playbook NonComparable (NovaBoost/NovaShield portent un damageProfile mais sont
    buff/tile).

    Le masque natif passe AVANT la signature gameconfig : `damageProfile` dit « cette ability produit
    du degat », il ne dit RIEN du camp de la cible. 1100 SorcerousFacade porte un `damageProfile`
    (Psychic) et cible pourtant un ALLIE Psyker (`SorcerousFacadeAbility$$.ctor`, rules=0x402).

    ⚠ C'est un predicat de ROUTE, PAS de DOMAINE, et les confondre a coute 29 abilities (#977-r5) :
    la clause `not is_noncomp` repond a « quel GENERATEUR sert cette ability »
    (`IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` range par `get_IsComparable` du
    playbook), pas a « quelles cibles le natif enumere ». Le domaine, lui, est
    `_enumerates_both_camps` ci-dessous. Ne PAS reintroduire cet appel dans `_ability_kind`."""
    if not _enumerates_enemy_units(ability_id, cfg):
        return False
    return not is_noncomp(int(ability_id))


def _enumerates_enemy_units(ability_id: int, cfg: dict) -> bool:
    """DOMAINE : l'enumeration native peut-elle rendre des unites ENNEMIES ? (independant de la ROUTE)

    Les deux termes sont ceux de `_is_attack_ability` MOINS la clause de route : le VETO de camp
    RE-lu du masque, et la presence d'un `constants.damageProfile` (le seul signal gameconfig qui
    dise « cette ability vise une UNITE et lui fait du degat »)."""
    if _refuses_all_enemy_targets(ability_id):
        return False
    return bool((cfg.get("constants") or {}).get("damageProfile"))


def _enumerates_both_camps(ability_id: int, cfg: dict) -> bool:
    """`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` n'applique AUCUN
    filtre de CAMP -- LU sur le corps (`rnca9r7q6c`), et c'est ce qui fonde le kind `any`.

    Le corps enchaine : `GetUnitsInRange` (ou `GetTilesInRange` si le bit `TargetIsTile` est pose,
    ou si l'appelant force `onlyTiles`), l'ajout du caster sous `CasterIsPossibleTarget` (bit 15) ou
    le bit 57, puis TROIS `RemoveWhere` -- `<GetPossibleTargetsForOptions>b__0` (retire les entites
    mortes / `HasSteppableUnit`), `b__1` (retire les NON-amis que du terrain obscurcit :
    `IsFriend(target, caster) -> false`, donc un ami n'est JAMAIS retire par ce prédicat), et
    `b__2` sous le bit 1 (la regle dynamique de l'ability). AUCUN de ces trois ne lit le camp pour
    l'exclure. Le camp n'est tranche qu'ENSUITE, par la cascade
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` -- exactement les deux regles
    que `refuses_all_enemy_targets` reconnait.

    ⇒ un masque LU qui ne porte NI `TargetIsFriendly` NI `TargetIsCaster` laisse survivre les DEUX
    camps. Le port rendait `self` (le caster SEUL) pour 29 abilities dans ce cas -- une degradation
    RESTRICTIVE et silencieuse (`CordClawPlaybook._eligible_ids` filtrait alors TOUS les ennemis).

    `TargetIsTile` est EXCLU ici : sous ce bit le natif rend des TUILES (`GetTilesInRange`), pas des
    unites -- et l'enumerateur de tuiles offline est le patron SUMMON (ring-1 des tuiles-caster),
    pas le patron AIM a portee. Ces 10 abilities restent donc hors de cette branche (residu #977-r7).
    Masque NON LU -> `False` : on ne fabrique pas un domaine depuis une non-mesure."""
    if not _enumerates_enemy_units(ability_id, cfg):
        return False
    opts = targeting_options_for(ability_id)
    return opts is not None and not opts.has(_TR.TargetIsTile)


def _ability_reach(vid: str, ability_id: int, cfg: dict) -> int:
    """Portee de l'ability (mirror `IdunBattle.Core.Services.TargetingQuery$$GetRange) : `constants.range` si present, sinon
    `attackRangeType` (Melee->1 ; Normal/Ranged->portee arme), sinon portee arme. (Le +GetStat(0x18) ranged-bonus
    et le clamp effet 0x529 = raffinements runtime non portes.)"""
    c = cfg.get("constants") or {}
    if c.get("range") is not None:
        return int(c["range"])
    if cfg.get("attackRangeType") == "Melee":
        return 1
    return _max_attack_range(vid)


def _ability_kind(ability_id: int, name: str, cfg: dict) -> str:
    """KIND de cible derive offline : 'enemy' (attaque) / 'ally' (heal) / 'machine' (repair) / 'tile' (summon)
    / 'any' (les DEUX camps) / 'self' (residuel). Cf. §2(c) de la RE : exact pour les 4 premieres,
    defaut self pour le reste.

    ⚠ C'est le DOMAINE de cible, PAS la ROUTE de decision (#977-r5). La branche 'enemy' teste
    `_is_attack_ability`, qui porte en plus la clause de route `not is_noncomp` -- une ability
    NonComparable ne peut donc pas y entrer, et tombait AUTREFOIS sur le 'self' residuel : mesure,
    29 abilities a `damageProfile` et SANS aucun veto de camp y etaient rabattues, si bien que
    `ability_targets_offline` n'emettait plus que le CASTER. La branche 'any' (`_enumerates_both_camps`)
    les rattrape SANS toucher a la route -- et l'ensemble emis est strictement ELARGI, jamais reduit.

    Le masque natif RE-lu PRIME quand il porte `TargetIsFriendly` : c'est le camp que la cascade
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` impose (tout non-allie rompt),
    et donc le seul domaine que `GetPossibleTargetsForOptions` laisse survivre. Sans ca, une ability
    ALLIEE a `damageProfile` (1100 SorcerousFacade) retombait sur 'enemy'. La restriction FINE
    eventuelle (regle dynamique de l'ability) n'est pas appliquee ici quand la classe d'ability n'est
    pas portee -> l'ensemble rendu est un SUR-ENSEMBLE des allies, degradation permissive assumee."""
    c = cfg.get("constants") or {}
    if _refuses_all_enemy_targets(ability_id):
        _opts = targeting_options_for(ability_id)
        if _opts is not None and _opts.has(_TR.TargetIsFriendly):
            return "ally"
        return "self"                                  # `TargetIsCaster` : la cible DOIT etre le caster
    if _is_attack_ability(ability_id, cfg):
        return "enemy"
    if int(ability_id) in HEAL_ABILITY_IDS or _has_heal_magnitude(cfg):
        return "ally"
    if int(ability_id) in REPAIR_ABILITY_IDS or _has_repair_magnitude(cfg):
        return "machine"
    if c.get("unitId") and not c.get("damageProfile"):
        return "tile"
    if _enumerates_both_camps(ability_id, cfg):
        return "any"
    return "self"


def _attack_abilities(vid: str, has_normal: bool = True,
                      passive_abilities: tuple | None = None,
                      traits: tuple | None = None) -> list:
    """[(ability_id, reach)] des abilities d'ATTAQUE de l'unite : l'attaque normale (17, portee=max arme) + chaque
    active a `damageProfile` (non-NonComparable), portee = `_ability_reach`.

    `has_normal=False` (#419-r1-tr14-r5-r4) : l'unite porte `Erratic`/`Harmless`, donc la fabrique
    ne lui a POSE aucune attaque normale -- il ne faut pas en planifier une. Cf. le call-site.

    `passive_abilities` : le TRI-ETAT d'entite de `_granted_abilities` (#931-r2), propage tel quel.
    `traits` : le TRI-ETAT d'entite des abilities DERIVEES D'UN TRAIT (#1015-r1), propage tel quel --
    le MEME substrat doit alimenter les deux appels a `_abilities_of` d'un meme tour, sinon deux vues
    du kit divergeraient. Aucune des deux derivees connues (`18 Heal`, `28 Repair`) n'a de
    `damageProfile`, donc `_is_attack_ability` les rejette : la propagation ne CHANGE rien aujourd'hui,
    elle empeche une divergence de substrat demain."""
    out = [(NORMAL_ATTACK_ID, _max_attack_range(vid))] if has_normal else []
    for aid, _name in _abilities_of(vid, passive_abilities, traits):
        if aid == NORMAL_ATTACK_ID:
            continue
        _n, cfg = _resolve_ability(aid)
        if _is_attack_ability(aid, cfg):
            out.append((aid, _ability_reach(vid, aid, cfg)))
    return out


def _plans_for_unit(uid: int, vid: str, origin: tuple | None, move_tiles: list,
                    enemies: list, has_normal: bool = True,
                    passive_abilities: tuple | None = None,
                    traits: tuple | None = None) -> dict:
    """Enumere le `plan` d'attaque de `uid` : pour chaque (ability d'ATTAQUE, ennemi), le SET de tuiles-caster
    (origine + tuiles de move) d'ou l'attaque est legale (dist hex <= portee de l'ability). Forme mirroir de
    `decisionView.attackPlans[uid]` REDUITE a ce que le spine lit (`_best_attack` : abilityId/targetId/rankCount/
    ranked[(col,row)] ; les nombres de degat sont debug-only). Ordre de `ranked` indifferent (argmax strict).

    SLICE 2 : attaque normale (portee=max arme) + abilities ACTIVES d'attaque (portee propre `_ability_reach`).

    ORIGINE INCLUSE ET EN TETE (R1). Ce n'est pas un ajout d'outillage : le natif LUI-MEME met la
    position courante dans les candidats, en premier -- `ABaseAiUnitTactic$$GenerateActionTiles` ->
    `IBattleQuery`+0xe = `BattleQuery$$GetCurrentAndMovablePositionsFor` (OrderedSet SEEDE avec
    `GetUnitPosition(unit)`, puis `UnionWith(GetMovablePositionsFor(...))`). La couture LIVE fait
    pareil (`projection.ts::computeAttackPlans` ajoute la `mainTile` au set avant de ranker) : garder
    l'origine ICI maintient la PARITE offline/live. `plans` sert AUSSI d'oracle geometrique (« depuis
    quelles tuiles l'attaque est-elle legale ») a `noncomparable._base._get_num_attack_targets_in_position`
    et a `hammer_of_wrath`/`holy_duel` -- l'en retirer les casserait.

    ORDRE : seul le rang de l'ORIGINE compte, et `ComparableAbilityGenerator._best_attack` le RE-IMPOSE
    de toute facon (il balaie l'origine d'abord, puis les `ranked` dans leur ordre) -- le tie-break
    keep-first du `Bucket` ne depend donc pas de cette liste. On met quand meme l'origine en tete ici
    pour que la forme offline soit le mirror exact de l'ensemble natif. L'ordre RELATIF des tuiles de
    move reste, lui, indifferent (cf. residu R1-b : l'ordre natif exact n'est pas etabli)."""
    cand_tiles = [] if origin is None else [origin]
    cand_tiles += [t for t in ((x["col"], x["row"]) for x in move_tiles) if t != origin]
    evals: list = []
    for (aid, reach) in _attack_abilities(vid, has_normal, passive_abilities, traits):
        for en in enemies:
            ep = en.get("pos")
            if not ep:
                continue
            epos = (ep["col"], ep["row"]) if isinstance(ep, dict) else (ep[0], ep[1])
            ranked = [{"col": c, "row": r} for (c, r) in cand_tiles
                      if hexgeo.distance((c, r), epos) <= reach]
            if ranked:
                # `rankComplete` (#350-r3a-r4) : cette enumeration parcourt TOUTES les tuiles
                # candidates -- il n'y a aucun plafond ici, contrairement a `computeAttackPlans`
                # (`for (let r = 0; r < maxRank; r++)`), qui perd 21 positions sur 33 a `maxRank=6`.
                # Le DECLARER est ce qui permet aux lecteurs de `ranked` de ne PAS payer un
                # `castFromTiles` sur cette face -- et de ne pas non plus SUPPOSER que le plan est
                # complet sur l'autre. Tri-etat : cf. `engine.ai.cast_positions`.
                evals.append({"abilityId": aid, "targetId": en.get("id"),
                              "rankCount": len(ranked), "ranked": ranked,
                              "rankComplete": True})
    return {"evals": evals}


def _is_machine(entity) -> bool:
    """Unite MACHINE (cible du repair) — trait `Mechanical` du gameconfig. Fallback True si indeterminable
    (le repair est dormant ; sur-emettre = filtre downstream)."""
    sc = entity.get_component(StatsComponent)
    traits = (sc.ctx.traits if sc is not None else None) or []
    return "Mechanical" in traits


def ability_targets_offline(state, uid: int, ability_id: int) -> dict:
    """`IdunBattle.AI.Playbook.BasePlaybook$$GetAllValidTargetsFromAllPossibleMovementTiles` / `BattleQuery IdunBattle.Core.Services.BattleQuery$$GetAllValidTargetsFromAllPossibleMovementTiles` /
    `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` — enumerateur de ciblage OFFLINE (SLICE 2). Renvoie l'UNION des
    cibles legales sur toutes les tuiles-caster (origine + move) au format du RPC `abilityTargets` que le seam
    `AiDecisionContext.ability_targets` consomme :
      {units:[{unitId, abilities:[{abilityId, targets:[{kind:'unit'|'tile', targetId, tile:{col,row}}]}]}]}
    kind emis = 'unit' (enemy/ally/machine/self) ou 'tile' (summon). Portee/kind via la classification gameconfig
    (`_ability_kind`/`_ability_reach`). Reutilise `_move_tiles`/`_occupants`/board/hexgeo (aucun code board neuf)."""
    me = state.get_entity(uid)
    if me is None:
        return {"units": []}
    oc = me.get_component(OwnerComponent)
    pc = me.get_component(PositionComponent)
    uco = me.get_component(UnitComponent)
    my_team = oc.team if oc is not None else None
    vid = uco.visual_id if uco is not None else ""
    origin = (pc.col, pc.row) if pc is not None else None
    name, cfg = _resolve_ability(ability_id)
    kind = _ability_kind(ability_id, name, cfg)
    reach = (_ability_reach(vid, ability_id, cfg)
             if kind in ("enemy", "ally", "machine", "any") else 1)
    reach_tiles = [(t["col"], t["row"]) for t in _move_tiles(state, uid, vid, my_team, origin)]
    if origin is not None:
        reach_tiles.append(origin)
    targets: list = []
    board = state.board
    if kind == "self":
        targets.append({"kind": "unit", "targetId": uid,
                        "tile": {"col": origin[0], "row": origin[1]} if origin else None})
    elif kind in ("enemy", "ally", "machine", "any"):
        for eid, e in state.entities.items():
            u = e.get_component(UnitComponent)
            o = e.get_component(OwnerComponent)
            p = e.get_component(PositionComponent)
            if u is None or not u.alive or o is None or p is None:
                continue
            is_ally = (o.team == my_team)
            # `any` = AUCUN filtre de camp -- `GetPossibleTargetsForOptions` n'en pose aucun, et le
            # masque de ces abilities ne porte ni `TargetIsFriendly` ni `TargetIsCaster` (#977-r5).
            if kind == "enemy" and is_ally:
                continue
            if kind in ("ally", "machine") and not is_ally:
                continue
            if kind == "machine" and not _is_machine(e):
                continue
            if _is_untargetable(state, eid):             # non-ciblable (deep-strike teleporting-in)
                continue
            tp = (p.col, p.row)
            if eid == uid or any(hexgeo.distance(T, tp) <= reach for T in reach_tiles):
                targets.append({"kind": "unit", "targetId": eid,
                                "tile": {"col": tp[0], "row": tp[1]}})
    elif kind == "tile" and board is not None:
        occupied = {(p.col, p.row) for e in state.entities.values()
                    for p in (e.get_component(PositionComponent),)
                    for u in (e.get_component(UnitComponent),)
                    if p is not None and (u is None or u.alive)}
        seen: set = set()
        for T in reach_tiles:                                    # spawn adjacent (ring-1) a une tuile-caster
            ttile = board.id_at(T[0], T[1])
            if ttile is None:
                continue
            for n in board.neighbours(ttile):
                col, row = board.coord(n)
                if (col, row) in seen or (col, row) in occupied:
                    continue
                if not board.by_id.get(n, {}).get("walkable", True):
                    continue
                seen.add((col, row))
                targets.append({"kind": "tile", "targetId": None, "tile": {"col": col, "row": row}})
    return {"units": [{"unitId": uid, "abilities": [{"abilityId": int(ability_id), "targets": targets}]}]}


def _dv_units(state) -> list:
    """`units` façon decisionView (ctrl attribue plus bas par team) : id/alive/pos/team/hp/visualId/effects.

    MoW EXCLUES, et c'est FIDELE (pas le residu R14) : le natif ne met que `EntityType.Unit` dans
    `decisionView.units` -- les Machines vivent dans le canal SEPARE `.mows` (cf. `_load_machines`) et
    ont leur PROPRE chemin de decision, `IdunBattle.AI.Tactics.DefaultMachineTactic`, sur lequel
    `IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit` route des `IsMachine(actor)`. Le port de
    ce chemin est `engine.ai.context.build_machine` + `engine.ai.tactic.DefaultMachineTactic` (routage
    dans `engine_validate.engine_decide`) : position du caster = `UnitPosition.NullPosition`, tuiles
    candidates VIDES, aucun `MovementActionGenerator`. Glisser une MoW ICI lui inventerait une origine
    et contaminerait le raisonnement positionnel de toutes les vraies unites.

    RESIDU (voie 100% OFFLINE) : `build_from_state` n'a pas de jumeau Machine parce que le seam de
    ciblage offline `ability_targets_offline` mirrore
    `IdunBattle.AI.Playbook.BasePlaybook$$GetAllValidTargetsFromAllPossibleMovementTiles` -- il ancre
    les cibles aux tuiles-caster (origine + move), donc il rend VIDE pour un caster sans position.
    L'eligibilite d'une ability de MoW vient de ses `TargetingOptions` + `GetAllTargets` (filtre
    STATIQUE non porte, tache #115) ; tant qu'il manque, la face DECISION MoW se confronte par la voie
    LIVE (RPC `abilityTargets`), comme le fait `context.build` pour les unites."""
    out: list = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        ec = e.get_component(EffectsOwnedComponent)
        if uc is None or is_machine_of_war(e):
            continue
        out.append({
            "id": eid, "visualId": uc.visual_id, "alive": bool(uc.alive),
            "team": oc.team if oc is not None else None,
            "pos": {"col": pc.col, "row": pc.row} if pc is not None else None,
            "hp": hc.hp if hc is not None else None,
            # `effects` = noms bruts du composant natif `EffectsOwnedComponent.effects` (str). Les gates
            # d'effets de DÉCISION lisent l'état STRUCTURÉ `State.effects` (HasEffect), pas ce champ.
            "effects": list(ec.effects) if ec is not None else [],
        })
    return out


def _obs_units(state) -> list:
    """`observeBattle.units` façon runner : squadId/teamId/visualId/hp/hpMax/isDead/col/row.
    MoW EXCLUES (canal separe `.mows` cote natif + chemin de decision dedie, cf. `_dv_units`)."""
    out: list = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        if uc is None or is_machine_of_war(e):
            continue
        out.append({
            "squadId": eid, "teamId": oc.team if oc is not None else None,
            "visualId": uc.visual_id, "hp": hc.hp if hc is not None else None,
            "hpMax": hc.hp_max if hc is not None else None, "isDead": not bool(uc.alive),
            "col": pc.col if pc is not None else None, "row": pc.row if pc is not None else None,
        })
    return out


def _triggered_kits_from_state(scene) -> dict:
    """`{unitId: [TriggeredAbilityType]}` du chemin OFFLINE (#983-r1) -- le pont qui manquait entre
    le substrat d'ENTITE deja seede et `AiDecisionContext.live_triggered_kits`.

    MEME substrat que le RPC `unitAbilityStates` cote LIVE : le `TriggeredAbilityComponent`, image
    `UnitContext.triggered_abilities` posee par `snapshot._load_triggered_abilities`. C'est ce que
    `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
    enumere reellement, et ce qu'interroge `IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility`
    -- pas le kit gameconfig, qui ignore les abilities accordees par TRAIT, par RELIQUE et par
    greffe (mesure #456-r1 : divergence sur 3 des 4 unites, DANS LES DEUX SENS).

    ⚠ ON N'INSCRIT QUE CE QUI A ETE MESURE. Une entite dont `triggered_abilities is None` (canal
    muet : snapshot sans `unitAbilityStates`, entite sans `StatsComponent`) reste ABSENTE de la
    table -- surtout pas une liste vide, qui se lirait « cette unite ne porte aucun passif » et
    ferait RETIRER un id que le kit gameconfig connait. C'est le tri-etat d'
    `entity_triggered_ability_ids`, transpose au grain de la TABLE : ici on ne rabat pas sur le
    gameconfig nous-memes, on laisse le consommateur le faire -- il est le seul a savoir s'il
    remplace (regle #456-r1) ou s'il unit (regle N13, `_adjacent_units` /
    `CalibaniteGreatswordPlaybook`).

    `scene is None` -> `{}` (pas de substrat du tout)."""
    if scene is None:
        return {}
    out: dict = {}
    for eid, uctx in (getattr(scene, "ctx_by_id", None) or {}).items():
        ids = getattr(uctx, "triggered_abilities", None)
        if ids is None:
            continue                      # canal MUET pour cette entite -> pas d'entree (tri-etat)
        out[int(eid)] = [int(x) for x in ids]
    return out


def _no_rpc(method: str, body: dict, timeout: int = 0) -> dict:
    """Fermeture RPC no-op du bridge offline. `ability_targets` (heal/repair/summon/Nova) -> vide.
    SLICE 2 = enumerateur de cibles offline (from State) branche ici."""
    return {"units": []}


def build_from_state(state, uid: int, debug: bool = False, max_distance: int | None = None):
    """`State`(runner) -> `AiDecisionContext` pour l'unite `uid` (offline). Tous les champs derives des
    composants/board/gameconfig ; `predictor`/`sctx`=None (le spine lit `ctx.scene`). Voir en-tete pour les
    gaps documentes.

    `max_distance` = le 3e argument d'`IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles(unit,
    ignoreFlags, overrideRange)`, propage jusqu'au slot `IBattleQuery+0xe` =
    `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor(unit, ignoreUnitFlags, options)`
    -> `MovementQuery$$GetMovablePositionsFor` -> `MovementQuery$$FindAnyOrAllMoveableTiles`, dont le
    corps LU tranche : `range = options.overrideRange.HasValue ? options.overrideRange.Value :
    StatComponent.get_CurrentValue(<stat Movement>)`. L'override est donc une PROFONDEUR DE
    FLOOD-FILL, pas un interrupteur.

    `None` (defaut) = plage de deplacement NORMALE de l'unite (le regime de
    `CalculateNextActionForUnit`). **`0` = portee de deplacement NULLE** : l'ensemble se reduit a la
    graine de l'`OrderedSet`, c.-a-d. la tuile COURANTE seule -- c'est litteralement le
    « FromCurrentPosition » du noeud `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttackFromCurrentPosition`
    (`behaviour+0x78 = Direct(0)`). **`N > 0` = flood-fill a `N` tuiles** : le regime de
    `DSLBehaviors$$PerformAIMovement`, dont les DEUX call-sites portes passent `DSLFormulas$$Direct(1)`
    (`1144 BioMinefield`, `1053 DevoutPush`). ⚠ Ce dernier regime etait rabattu sur `0` jusqu'a
    #996-r1, sous la premisse « aucun appelant » -- premisse deja fausse a l'ecriture."""

    me_ent = state.get_entity(uid)
    if me_ent is None:
        raise ValueError(f"build_from_state: unite {uid} absente du State")
    m_oc = me_ent.get_component(OwnerComponent)
    m_uc = me_ent.get_component(UnitComponent)
    m_pc = me_ent.get_component(PositionComponent)
    my_team = m_oc.team if m_oc is not None else None
    vid = m_uc.visual_id if m_uc is not None else None
    origin = (m_pc.col, m_pc.row) if m_pc is not None else None

    units = _dv_units(state)
    for u in units:                                   # ctrl = meme camp que l'unite qui decide
        u["ctrl"] = (u.get("team") == my_team)
    enemies = _enemies(units)
    epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies]
    fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("ctrl") and u.get("alive") and u.get("pos") and u.get("id") != uid]

    # #419-r1-tr14-r5-r4 -- `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` REND
    # SANS RIEN AJOUTER quand `config.Traits` contient `Erratic` (0x0e) ou `Harmless` (0x15) : la
    # fabrique n'appelle alors NI `GetCustomNormalAttackTypeFromPassive`, NI la voie active, NI
    # `ActiveAbilityComponent$$Add`. L'unite n'a AUCUNE attaque normale, son
    # `ActiveAbilityComponent.NormalAttackType@0x28` reste a 0, et le natif ne publie donc aucune
    # ability `kind == "normal"` pour elle. Le port, lui, en posait une des que le KIT gameconfig
    # portait une arme -- une divergence PERMISSIVE (ni erreur ni crash) : le decideur offline
    # generait, scorait et pouvait CHOISIR une attaque que le natif ne propose pas.
    # SUBSTRAT D'ENTITE : le natif lit `UnitConfiguration.Traits`, c.-a-d. `BC.Units[].Traits`, que
    # le kit gameconfig ne reproduit PAS (#264). `entity_trait_names` est le foyer qui lit ce
    # substrat -- et son repli kit, quand l'entite n'a pas de `UnitContext`, reste une BORNE.
    _me_sc = me_ent.get_component(StatsComponent)
    _me_traits = entity_trait_names(getattr(_me_sc, "ctx", None), vid)
    has_normal = has_normal_attack(_me_traits)
    # #931-r2 -- MEME forme de substrat, sur l'autre liste de la `UnitConfiguration` : les abilities
    # ACCORDEES par un passif viennent de `BC.Units[].PassiveAbilities` (fait d'ENTITE), pas du KIT.
    # `measured_passive_abilities` rend le TRI-ETAT ; `None` = canal muet -> repli kit, BORNE nommee.
    _me_passives = measured_passive_abilities(getattr(_me_sc, "ctx", None))
    # #1015-r1 -- TROISIEME liste de la meme `UnitConfiguration` : `Traits` (`config@+0xd0`), lue par
    # `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities` pour poser `18 Heal` (trait
    # `Healer`) / `28 Repair` (trait `Mechanic`). MEME substrat d'entite que `has_normal` juste
    # au-dessus -- c'est le meme `entity_trait_names`, lu UNE fois et partage.
    _me_abilities = [(aid, nm) for (aid, nm) in _abilities_of(
                         vid or "", _me_passives, tuple(sorted(_me_traits)))
                     if has_normal or aid != NORMAL_ATTACK_ID]
    abilities = [{"id": aid, "name": nm, "usable": True} for (aid, nm) in _me_abilities]
    ab_name_by_id = {aid: nm for (aid, nm) in _me_abilities}
    normal_ids = {NORMAL_ATTACK_ID} if any(a[0] == NORMAL_ATTACK_ID for a in _me_abilities) else set()

    me = next((u for u in units if u.get("id") == uid), None)
    if me is not None:
        me["abilities"] = abilities

    # `GenerateActionTiles(unit, true, overrideRange)` -> `GetCurrentAndMovablePositionsFor` ->
    # `MovementQuery$$FindAnyOrAllMoveableTiles`, ou l'override REMPLACE la stat `Movement` comme
    # profondeur de flood-fill (`range = overrideRange.HasValue ? .Value : Movement.CurrentValue`).
    # ⚠ CE SITE RENDAIT `[]` POUR **TOUTE** VALEUR NON NULLE (#996-r1) -- la premisse ecrite ici
    # (« seules `None` et `0` ont un call-site natif ») etait FAUSSE AU MOMENT MEME OU ELLE A ETE
    # ECRITE : `1144 BioMinefield` passe deja `Direct(1)` (`PerformAIMovement`), et `1053 DevoutPush`
    # aussi. Le `1` etait donc traite comme `0` -> une seule candidate (la tuile courante) ->
    # keep-first -> AUCUN mouvement, sans erreur.
    move_tiles = _move_tiles(state, uid, vid or "", my_team, origin, override_range=max_distance)
    # `tiles` du tactic natif (`ABaseAiUnitTactic$$GenerateActionTiles` -> `IBattleQuery`+0xe =
    # `BattleQuery$$GetCurrentAndMovablePositionsFor`) : ORIGINE EN TETE puis les tuiles de move.
    # MEME helper que la couture LIVE `context.build` -> meme ensemble ET meme ORDRE de sweep.
    # `reach_nc` est l'ALIAS historique de cette meme liste (cf. `context.build`).
    action_tiles = action_tiles_for(origin, move_tiles)
    reach_nc = action_tiles

    scene = Scene.from_state(state)
    hp_cur_by_id = dict(scene.hp_by_id)
    hpmax_by_id = dict(scene.hpmax_by_id)
    elev_by_pos = scene.elev_by_pos or {}
    # #57l — MinDist(16) ne mesure QU'AUX ennemis CIBLABLES (miroir `FindClosestEnemy` -> `!IsTargetable`,
    # IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext) : un ennemi en Deep-Strike (TeleportStrike, non-atterri) est NON-ciblable et exclu du
    # ClosestEnemy. Sans ce filtre, un deep-strike plus proche par chemin ecrase le vrai ClosestEnemy et
    # fausse la distance-chemin par tuile (12345 s5 : (1,4)=6 vers Dante vs 7 vers l'ennemi ciblable).
    # `enemies`/`epos` restent complets (occupance/positionnement) ; seul le seed MinDist est filtre.
    _tgt = [e for e in enemies if e.get("pos") and not _is_untargetable(state, e.get("id"))]
    tgt_epos = [(e["pos"]["col"], e["pos"]["row"]) for e in _tgt]
    pathdist_by_pos, closest_enemy_id = _pathdist_to_enemies(
        state, uid, my_team, tgt_epos, origin=origin, enemy_ids=[e.get("id") for e in _tgt])
    # #236 — le `UtilityMovementCase` que le generateur natif passe a la feuille MinDist(16). Face
    # OFFLINE : le ClosestEnemy est FIGE par le meme `FindClosestEnemy` qui produit `pathdist_by_pos`
    # (une seule passe), donc son IDENTITE est connue -> les 4 gates y sont exacts, gate 4 compris.
    # `pathdist_by_pos is None` = le port n'a AUCUNE source de distance (board/origine absents) :
    # aucun case n'est construit, la feuille garde son comportement degrade documente.
    mindist_case = None
    if pathdist_by_pos is not None:
        # `GetStat(unit, 9)` du gate 4 : la valeur LUE, ou `None` si l'unite n'a pas de
        # `UnitContext` dans la Scene -- donc pas de stat lisible. Surtout PAS un `or 0` de repli :
        # `0` est la valeur qui FAIT MORDRE le gate (`UnitCanBeDamaged` renvoie faux sur un
        # ClosestEnemy `Impervious`), donc un defaut le ferait mordre sur une donnee jamais lue.
        _me_ctx = scene.ctx(uid)
        mindist_case = UtilityMovementCase(
            unit=uid,
            unit_traits=entity_trait_names(_me_ctx, vid),
            unit_crit_chance=(getattr(_me_ctx, "crit_chance", None)
                              if _me_ctx is not None else None),
            closest_enemy=closest_enemy_id,
            closest_enemy_traits=(None if closest_enemy_id is None else entity_trait_names(
                scene.ctx(closest_enemy_id),
                next((e.get("visualId") for e in _tgt if e.get("id") == closest_enemy_id), None))))
    else:
        pathdist_by_pos = {}
    # topologie boardGraph (self-cast MainTile #116, ordre voisins natif Gauntlets #117, gate placement) —
    # mirror OFFLINE des 3 seams boardGraph que le contexte LIVE fournit ; ex-gap du bridge (build_from_state
    # anterieur a l'ajout de ces champs requis) revele par la confrontation du tour du Skitarii (#24).
    (tile_id_by_pos, neigh_by_pos, walkable_by_pos, terrain_by_pos,
     is_wall_by_pos) = _board_topology_maps(state.board)
    is_in_fog_by_pos = _board_fog_map(state.board)
    # Plans d'ATTAQUE : ne cibler que les ennemis CIBLABLES (exclut les deep-strike teleporting-in, non-ciblables
    # jusqu'a l'atterrissage). `enemies` reste complet pour le positionnement (ils occupent le board).
    tgt_enemies = [e for e in enemies if not _is_untargetable(state, e.get("id"))]
    plans = {uid: _plans_for_unit(uid, vid or "", origin, move_tiles, tgt_enemies, has_normal,
                                  _me_passives, tuple(sorted(_me_traits)))}

    def _rpc(method, body, timeout=0):
        """Seam RPC offline (SLICE 2) : `abilityTargets` -> enumerateur offline (heal/repair/summon/Nova) ;
        tout autre method -> vide. Capture `state` (closure) pour `AiDecisionContext.ability_targets`."""
        if method == "abilityTargets" and isinstance(body, dict):
            return ability_targets_offline(state, body.get("unitId"), body.get("abilityType"))
        return {"units": []}

    return AiDecisionContext(
        rpc=_rpc, rid=0, wt=_weights(), predictor=None, sctx=None, scene=scene,
        uid=uid, me=me, units=units, cur=getattr(state, "current_player_id", None), plans=plans,
        enemies=enemies, epos=epos, tgt_epos=tgt_epos, fpos=fpos, origin=origin,
        move_tiles=move_tiles, reach_nc=reach_nc, action_tiles=action_tiles,
        hp_cur_by_id=hp_cur_by_id, hpmax_by_id=hpmax_by_id, obs_units=_obs_units(state),
        ab_name_by_id=ab_name_by_id, normal_ids=normal_ids,
        elev_by_pos=elev_by_pos, is_temporary_by_pos={}, effects_by_pos={},
        pathdist_by_pos=pathdist_by_pos, mindist_case=mindist_case,
        tile_id_by_pos=tile_id_by_pos, neigh_by_pos=neigh_by_pos, walkable_by_pos=walkable_by_pos,
        terrain_by_pos=terrain_by_pos, is_wall_by_pos=is_wall_by_pos,
        is_in_fog_by_pos=is_in_fog_by_pos,
        offline_triggered_kits=_triggered_kits_from_state(scene),   # #983-r1
        debug=debug)
