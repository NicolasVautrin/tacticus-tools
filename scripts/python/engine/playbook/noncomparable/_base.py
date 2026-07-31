"""Fondations partagees des playbooks NonComparable (namespace `engine.playbook.noncomparable`).

Bases de hierarchie (`NonComparablePlaybook`, `_PlanTargetPlaybook`), contexte live `NCContext`, et
helpers transverses (config gameconfig, traits, sweep origine-d'abord, HasValidTargets). Chaque
playbook natif vit dans son propre module (bloody_fury.py, heals.py, ...) et importe d'ici ; le
registre + le driver `choose_action` sont dans le package `__init__.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import gameconfig as _gc


# ---------------------------------------------------------------------------------------------
# TIERS `get_Priority` NATIFS (`IdunBattle.Entities.Abilities.AbilityPriority` :
# 1000=First, 100=Early, 0=Normal, -100=Late, -1000=Last)
#
# `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` range chaque ActiveAbilityType
# NonComparable dans `dict[playbook.get_Priority()]` (slot 0 de l'interface IPlaybook, dispatch
# `FUN_180002560(0, DAT_1831d4f88, playbook)`) ; `GetDefaultActiveAbilityActionGenerators` cree UN
# generateur par tier, dans l'ordre [1000, 100, 0, -100, -1000], evalues PREMIER-NON-NULL avant le
# fallback Comparable. Le tier n'ordonne QUE les NonComparable : slot 1 `get_IsComparable` vrai
# renvoie l'ability dans l'OrderedSet `special`, qui ignore la priorite.
#
# Cette table est le RESULTAT D'UN SWEEP EXHAUSTIF des 258 valeurs de l'enum ActiveAbilityType,
# mesure par invocation du slot 0 de la vtable d'interface (`probe_170_playbook_priority.py`,
# RPC `pbGate`), confirme par la voie independante `abilityPreferences` (0 divergence / 258) et,
# pour trois d'entre elles, par les OCTETS du corps natif :
#     TzeentchsFirestormPlaybook.get_Priority  b8 e8 03 00 00 c3  mov eax,0x3E8      ->  1000
#     SquigMinePlaybook.get_Priority           b8 9c ff ff ff c3  mov eax,0xFFFFFF9C ->  -100
#     ReanimationBeamPlaybook.get_Priority     b8 18 fc ff ff c3  mov eax,0xFFFFFC18 -> -1000
#
# TOUTE ability ABSENTE de cette table vaut 0 (`AbilityPriority.Normal`) -- c'est le cas de 236
# des 258 ; l'absence est donc l'ecrasante majorite, mais elle n'est PAS une regle generale.
#
# ATTENTION -- ne JAMAIS re-deriver ces valeurs d'une recherche de symboles. Les corps
# `mov eax,imm32 ; ret` sont dedupliques par IL2CPP : Ghidra n'en nomme AUCUN, et
# `data/symbols/<build>/frida/methods.tsv` (indexe par RVA, sans doublon) n'expose qu'UN
# proprietaire par corps -- d'ou les 3 seuls hits pour 22 surcharges reelles. C'est exactement
# le faux negatif qui avait produit la conclusion erronee « aucun playbook n'override
# get_Priority » (#115), corrigee par #170.
NATIVE_PRIORITY: dict[int, int] = {
    # 1000 = First
    1070: 1000,   # BreathOfSilencePlaybook
    1085: 1000,   # EreWeGoPlaybook
    1109: 1000,   # DeathScreamPlaybook
    1127: 1000,   # ArmouredMight_MovePlaybook
    1155: 1000,   # TzeentchsFirestormPlaybook
    1173: 1000,   # ArcScourgePlaybook
    1192: 1000,   # NovaBoostPlaybook            (PORTE)
    1200: 1000,   # SquigLaunchasPlaybook
    1213: 1000,   # DeathOnTheWindPlaybook
    # 100 = Early
    1032: 100,    # CatalystPlaybook
    1125: 100,    # GunnersKillOnSightPlaybook
    1174: 100,    # SolarAtomizerPlaybook
    1187: 100,    # ThriceBlessedConflagrationPlaybook   (PORTE)
    # -100 = Late
    1159: -100,   # MacroPlasmaIncineratorPlaybook
    1201: -100,   # SquigMinePlaybook
    1209: -100,   # InfernalCannonPlaybook
    # -1000 = Last
    1072: -1000,  # MyWillBeDonePlaybook
    1084: -1000,  # DaGreatWaaaghPlaybook
    1111: -1000,  # LivingBatteringRamPlaybook
    1172: -1000,  # InvocationOfMachineVengeancePlaybook
    1194: -1000,  # NovaShieldPlaybook           (PORTE)
    1223: -1000,  # ReanimationBeamPlaybook
}


def native_priority(ability_id: int) -> int:
    """Tier `get_Priority` natif d'une ability (0 = `AbilityPriority.Normal` par defaut).

    POINT D'EXTENSION : tout nouveau playbook NonComparable pose `PRIORITY = native_priority(<id>)`
    -- ou, si son ability est absente de `NATIVE_PRIORITY`, laisse le defaut 0. Le garde-fou
    `probe_170_playbook_priority.py` echoue si une classe portee diverge de la mesure live."""
    return NATIVE_PRIORITY.get(ability_id, 0)


_CFG_CACHE: dict = {}


def _unit_cfg(visual_id) -> dict:
    """Config gameconfig d'une unite par visualId (resolue + cachee ; `resolve_unit_id` d'abord, comme
    `_faction`). Le dict porte `traits` / `GrandAllianceId` / `kind`. Vide si introuvable."""
    if not visual_id:
        return {}
    c = _CFG_CACHE.get(visual_id)
    if c is None:
        try:
            uid = _gc.resolve_unit_id(visual_id)
            c = (_gc.unit(uid) if uid else _gc.unit(visual_id)) or {}
        except Exception:
            c = {}
        _CFG_CACHE[visual_id] = c
    return c


def _traits(visual_id) -> list:
    """Traits gameconfig (Hero/Mechanical). heal = Healable = non-Mecanique ; resurrect hero = Hero(16)."""
    return _unit_cfg(visual_id).get("traits") or []


_KIT_SPAWN_CACHE: dict = {}
_ALL_UNIT_IDS: set | None = None


def _all_unit_ids() -> set:
    """Tous les ids d'unite connus de gameconfig (lineup + npc + summons), caches."""
    global _ALL_UNIT_IDS
    if _ALL_UNIT_IDS is None:
        try:
            _ALL_UNIT_IDS = set(sum(_gc.all_unit_ids().values(), []))
        except Exception:
            _ALL_UNIT_IDS = set()
    return _ALL_UNIT_IDS


def _kit_spawn_visual_ids(visual_id) -> set:
    """Ids d'unite que le KIT de `visual_id` peut faire APPARAITRE (ses summons).

    MIRROR OFFLINE du lien natif enfant -> parent. Le natif le lit sur l'ECS :
    `IdunBattle.Entities.Components.ChildComponent` porte `ParentId` (BEntityId @+0x10 -- offset
    CONFIRME live par `dumpEntityComponents`), pose au spawn par
    `IdunBattle.Operations.SpawnUnitOperation$$Execute`. C'est ce champ que lit
    `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$IsFriendlyKell` (`*(int *)(comp + 0x10)
    == EntityId(caster)`).

    AUCUN RPC ne publie ce champ : ni `projectUnitsFull` (decisionView : id/visualId/pos/hp/owner/
    team/alive/ctrl/hasAction/ranged/defeatedByMelee/killerId/abilities/effects), ni `observeBattle`
    (entityId/squadId/visualId/teamId/playerId/col/row/hp/hpMax/armor/rank/isDead), ni
    `combatSnapshot`. Le lien se RECONSTRUIT donc depuis la config : toute constante d'une ability
    du kit dont la valeur NOMME une unite connue de gameconfig designe une unite que ce kit fait
    apparaitre. Le scan des 669 unites rend un vocabulaire de cles etroit et exclusivement
    spawn-related : `unitId`(48), `unitToSpawn`(5), `unitId_2`(5), `summonId`(3), `heroId`(3),
    `unitIds`(2), `affectedUnitIds`(1).

    `affectedUnitIds` apporte en prime le visualId **LIVE** d'un summon dont l'id de CONFIG differe :
    `SupremeCommander` spawne `astraSmnGuardsman` (kind=summons) mais le live projette
    `astraNpc1Guardsman` (kind=npc, meme nom « Cadian Guardsman ») -- les deux sont dans
    `affectedUnitIds`, donc les deux formes sont couvertes.

    DOMAINE D'EXACTITUDE (a lire avec le consommateur `IsFriendlyKell`) : le couple
    (visualId de summon, equipe du summoner) identifie le parent des lors qu'une equipe ne porte pas
    DEUX summoners du meme summon. Sinon le predicat « j'ai un enfant » peut passer pour le
    summoner A alors que l'enfant est celui de B. RESIDU pour lever l'approximation : publier
    `ChildComponent.ParentId` dans `projectUnitsFull` (le champ dict `parentId` existe deja cote
    port -- `engine/entities/selectors.py::Parent` -- et serait alors lu directement)."""
    if not visual_id:
        return set()
    s = _KIT_SPAWN_CACHE.get(visual_id)
    if s is None:
        known = _all_unit_ids()
        cfg = _unit_cfg(visual_id)
        s = set()
        for ab in ((cfg.get("activeAbilities") or []) + (cfg.get("passiveAbilities") or [])):
            try:
                consts = (_gc.ability(ab) or {}).get("constants") or {}
            except Exception:
                continue
            for v in consts.values():
                for tok in str(v).split(","):
                    tok = tok.strip()
                    if tok in known:
                        s.add(tok)
        _KIT_SPAWN_CACHE[visual_id] = s
    return s


def _has_valid_targets(ctx: "NCContext", unit_id: int) -> bool:
    """`IBattleQuery.HasValidTargets(unit, GetUnitPosition(unit), GetNormalAttackType(unit))` (slot 0x3f
    -> `IdunBattle.Core.Services.BattleQuery$$HasValidTargets` -> `IdunBattle.Core.Services.AttackQuery$$HasValidTargets`) résolu OFFLINE :
    l'unité peut-elle attaquer >= 1 ennemi avec son attaque NORMALE DEPUIS SA POSITION ACTUELLE (SANS bouger) ?
    = `abilityTargets(unit, GetNormalAttackType(unit))` -> `usable` (CanCurrentlyBeUsed = cooldown/munitions)
    ET `fromHereCount > 0` (`fromHere` = `AttackQuery.GetValidTargets(unit, pos, ability)` = légalité du cast
    immédiat : portée + LoS + filtre ennemi). POSITION-INDÉPENDANT du sweep du caster (dépend de la tuile
    FIXE de `unit`) -> à calculer 1x par cible. `ability_targets`/`units` absent, unité/attaque introuvable,
    RPC vide -> False (fallback = borne inf, = comportement pré-#77)."""
    if ctx.ability_targets is None:
        return False
    u = next((x for x in (ctx.units or []) if x.get("id") == unit_id), None)
    if u is None:
        return False
    # GetNormalAttackType = l'attaque normale CONCRETE de l'unité (id per-unit, pas l'abstrait 17).
    na = next((a for a in (u.get("abilities") or [])
               if a.get("kind") == "normal" and a.get("id") is not None), None)
    if na is None:
        return False
    at = ctx.ability_targets(unit_id, na["id"]) or {}
    for uu in (at.get("units") or []):
        if uu.get("unitId") != unit_id:
            continue
        for a in (uu.get("abilities") or []):
            if a.get("abilityId") == na["id"]:
                return (a.get("usable") is not False) and int(a.get("fromHereCount") or 0) > 0
    return False


def _normal_attack_ids(ctx: "NCContext", unit_id: int) -> set:
    """Ids de l'attaque NORMALE CONCRETE d'une unite (`GetNormalAttackType` ; per-unit, PAS l'abstrait
    17 — cf. project_ability_normal_attack_concrete). Vide si l'unite est absente de `ctx.units`."""
    u = next((x for x in (ctx.units or []) if x.get("id") == unit_id), None)
    return {a.get("id") for a in ((u or {}).get("abilities") or [])
            if a.get("kind") == "normal" and a.get("id") is not None}


def _will_normal_attack_kill(ctx: "NCContext", target_id, position: tuple | None) -> bool:
    """`IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill` : `PredictAttack` (slot 0x20 = attaque NORMALE du
    caster DEPUIS `position`) -> `ProbableDamageEvent` -> `DamagePredictionResult.get_WillBeKill` =
    SURE-kill (borne MIN >= PV courants, = `killSure` du composite). `target == null` -> false (branche
    `param_3 == 0` du natif). Predicteur (`ctx.scene`) absent -> false (borne inf, pas de gate a l'aveugle).

    A NE PAS confondre avec `EnemyCouldBeKilledWithNormalAttack` (`_enemy_killed_by_normal_attack`,
    hammer_of_wrath) qui teste s'il EXISTE un ennemi sure-kill ; ici c'est CETTE cible-la."""
    if target_id is None or position is None or ctx.scene is None:
        return False
    from engine.playbook.prediction import make_normal_attack_predictions
    ev = make_normal_attack_predictions(ctx.scene, ctx.uid, target_id, position)
    if ev is None:
        return False
    return bool(ev.composite_fields().get("killSure"))


def _get_num_attack_targets_in_position(ctx: "NCContext", unit_id: int, tile: tuple | None) -> int:
    """`IdunBattle.AI.Playbook.Loki.TheQuickeningPlaybook$$GetNumAttackTargetsInPosition` = `IBattleQuery` slot 0x7f
    (cibles d'attaque NORMALE de `unit_id` DEPUIS `tile`, POSITION HYPOTHETIQUE — la requete prend
    la tuile en argument, elle n'est PAS contrainte par le mouvement/l'occupation) suivi de `.Count`.

    Mirror OFFLINE via le plan natif (`decisionView.attackPlans`) : nombre de cibles DISTINCTES dont
    l'eval d'attaque NORMALE de `unit_id` liste `tile` parmi ses tuiles rankees — les tuiles rankees
    d'une paire (ability, cible) sont exactement les positions d'ou l'attaque est legale. Plan absent
    (le bridge offline `state_bridge` ne peuple que l'unite ACTIVE) -> 0 (borne inf assumee).

    FALLBACK GEOMETRIQUE (#46) : le plan est AVEUGLE hors de l'univers MOVABLE de `unit_id` — ses
    tuiles rankees sortent de `GetPossibleMovementTiles`, donc une tuile OCCUPEE (l'echange
    TheQuickening : caster sur la tuile d'un allie de meme empreinte) ou la position P d'un ALLIE
    echange n'y figure JAMAIS (mesure 31337 pas 15 : la cible native 52=(4,4), occupee par u79,
    etait jetee ici -> le port ratait la paire). Pour ces tuiles hors-plan on mirrore la partie
    MELEE du slot 0x7f : #ennemis ADJACENTS a `tile` (porte |dElev|<2, `is_adjacent`), si l'unite a
    une arme de melee (gameconfig `weapons` sans `Range`). Borne INF : l'arme RANGED (portee+LoS non
    portees) n'est pas comptee ; pour une tuile DU plan du caster le verdict plan reste autoritaire
    (pas de sur-comptage des tuiles movables sans attaque legale)."""
    if tile is None:
        return 0
    plan = (ctx.plans or {}).get(unit_id) or {}
    nids = _normal_attack_ids(ctx, unit_id)
    if not nids:
        return 0
    tgts = set()
    for ev in (plan.get("evals") or []):
        if ev.get("abilityId") not in nids or not ev.get("rankCount"):
            continue
        for rk in (ev.get("ranked") or []):
            if (rk.get("col"), rk.get("row")) == tile:
                tgts.add(ev.get("targetId"))
                break
    if tgts:
        return len(tgts)
    if unit_id == ctx.uid and tile in (ctx.reach_nc or []):
        return 0     # tuile DANS l'univers movable du plan du caster -> plan autoritaire
    u = next((x for x in (ctx.units or []) if x.get("id") == unit_id), None)
    if u is None:
        return 0
    weapons = _unit_cfg(u.get("visualId")).get("weapons") or []
    if not any("Range" not in w for w in weapons):
        return 0     # pas d'arme de melee -> le mirror geometrique ne sait pas compter (borne inf)
    from engine.battle_query import count_adjacent
    return count_adjacent(tile, ctx.epos or [], ctx.elev_by_pos)


def eligible_target_tiles(ctx: "NCContext", ability_id: int) -> tuple[list, list]:
    """Mirror de `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` pour un domaine
    TUILE -> `(from_here, union)`, deux listes de `(col, row)` DANS L'ORDRE DU NATIF.

    Le selector natif est `GetEligibleTargetsEntities(caster, possibleCasterPosition)` =
    IBattleQuery `GetValidTargets(caster, position, abilityType)` suivi d'un
    `idun.shared.extensions.ListExtensions$$Remove` (filtre d'ineligibilite) : la liste est donc
    calculee **PAR POSITION du caster**, et son ORDRE compte -- `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction`
    ne remplace que si STRICTEMENT superieur, donc a utilite egale c'est la PREMIERE cible enumeree
    qui gagne.

    L'RPC `abilityTargets` publie les deux vues, et elles ne sont PAS interchangeables :
      * `fromHere` = `GetValidTargets(unit, position COURANTE, ability)` -> l'ordre EXACT du selector
        natif a la position d'origine ;
      * `targets`  = `GetAllValidTargetsFromAllPossibleMovementTiles` -> l'UNION sur toutes les tuiles
        de move, dans un ordre qui n'est celui d'AUCUNE position en particulier.

    MESURE #343 (1166, runner MC1_67/909, caster genesBiophagus en (1,0), 1 ennemi en (0,1)) : les
    deux vues portent les MEMES 3 tuiles de spawn mais dans des ordres differents --
    `fromHere = [(1,1), (2,0), (0,0)]` contre `targets`-filtre `= [(2,0), (0,0), (1,1)]`. Deux
    d'entre elles valent l'utilite 1 ; le natif emet `(1,1)`, la 1re de `fromHere`. Balayer l'union
    faisait donc emettre `(0,0)` -- meme utilite, MAUVAISE tuile.

    Le residu qui reste : pour une position de move (T != origine) aucune vue par-position n'existe
    cote RPC ; l'appelant retombe sur l'union filtree, dont l'ordre est une APPROXIMATION. Le natif
    balayant l'origine EN PREMIER et ne remplacant que sur amelioration STRICTE, ce residu n'est
    atteignable que si une tuile de move ameliore strictement l'utilite."""
    if ctx.ability_targets is None:
        return [], []
    at = ctx.ability_targets(ctx.uid, ability_id) or {}
    from_here, union = [], []
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != ability_id:
                continue
            for key, out in (("fromHere", from_here), ("targets", union)):
                for t in (a.get(key) or []):
                    tile = t.get("tile")
                    if t.get("kind") == "tile" and tile and tile.get("col") is not None:
                        out.append((tile.get("col"), tile.get("row")))
    return from_here, union


def _turns_started_gate(ctx: "NCContext") -> bool:
    """Corps FOLDÉ (COMDAT) du slot-4 `ShouldEvaluate(unit)` « pas au 1er tour » — code UNIQUE
    IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate (symbole `AlphaWarriorPlaybook$$ShouldEvaluate`, refcount 7) pointé par la vtable de
    PLUSIEURS playbooks : `return GetStat(unit, 0xc=TurnsStarted) > 1`.

    Vtables résolues LIVE (`resolveVtableSlot` @0x298, gqfc5mff6c) : TheQuickening(1151),
    HeroicFusillade(1180), VigilanceEternal(1202), AlphaWarrior (non porté) -> IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate.
    `turnsStarted` (stat 12) = compteur PER-UNIT incrémenté au StartTurn -> vaut 1 pendant le
    PREMIER tour de l'unité : l'ability n'est JAMAIS évaluée au 1er tour (mesure #46 seed 31337 :
    slot4=0 au pas 5 (1er tour u81, 8/8 déterministe), =1 au pas 15 (2e tour) — la corrélation
    RapidAssault n=2 était un PROXY du 1er tour, pas le mécanisme). Compteur non capturé (scene
    absente / uid hors tables) -> True : ne PAS gater à l'aveugle (mirror du précédent
    `_is_player_side`)."""
    if ctx.scene is None:
        return True
    ts = ctx.scene.turns_started(ctx.uid)
    if ts is None:
        return True
    return ts > 1


def _sweep_origin_first(ctx: "NCContext") -> list:
    """Ordre de balayage des positions candidates : ORIGINE D'ABORD, puis les tuiles de move.

    Le generateur natif `ActiveAbilityActionGenerator.<GenerateActions>d__7 IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` evalue chaque
    position dans un Bucket ; `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` SEED le 1er ajoute puis ne remplace QUE si
    STRICTEMENT superieur (`System.TimeSpan.op_GreaterThan`) -> keep-first au tie. CONFIRME LIVE
    (#76, deathRotbone RevitalizingMalignancy) : a utilite CONSTANTE le natif RESTE EN PLACE, il ne
    bouge QUE si une tuile de move AMELIORE STRICTEMENT.

    MECANISME CORRIGE (R1, decompile) : ce n'est PAS une specificite self-cast, et ce n'est PAS la
    branche `NullPosition` (elle ne tire que si `tiles.Count == 0`). La liste `tiles` elle-meme
    COMMENCE par la position courante : `ABaseAiUnitTactic$$GenerateActionTiles` -> `IBattleQuery`+0xe
    = `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`, dont l'`OrderedSet`
    est SEEDE avec `GetUnitPosition(unit)` avant `UnionWith(movable)`. => `ctx.reach_nc` EST
    desormais construit dans cet ordre (cf. `engine.ai.context.action_tiles_for`) et cette fonction
    est l'IDENTITE. Conservee comme point d'ancrage documentaire + filet si `reach_nc` etait
    reconstruit autrement par un appelant."""
    if ctx.origin is None:
        return list(ctx.reach_nc)
    return [ctx.origin] + [t for t in ctx.reach_nc if t != ctx.origin]


@dataclass
class NCContext:
    """Etat live consomme par les generators de playbook (bundle du scope engine_decide)."""
    uid: int
    origin: tuple | None
    reach_nc: list                 # origine + tuiles de MOVE = positions candidates du caster
    epos: list                     # positions ennemies (GetAdjacentEnemies, slot 124/126)
    fpos: list                     # positions alliees, self exclu (GetAdjacentFriends, slot 128)
    plan: dict                     # plan natif (evals rankes) — abilities d'ATTAQUE
    hp_cur_by_id: dict             # PV courants par id cible (GetStat 5 = Health ; Vexilla)
    ability_targets: object = None # callable(uid, ability_id) -> dict RPC abilityTargets (summon)
    enemies: list = field(default_factory=list)    # unités ennemies {id, pos} (MÊME ordre que `epos`) :
    #                                emettre la CIBLE de l'arc pour Gauntlets (#117)
    neigh_by_pos: dict = field(default_factory=dict)  # {(col,row): [voisins ordre natif]} (boardGraph) :
    #                                cible EXACTE Gauntlets = 1er ennemi ring-1 en ordre voisins inversé (#117)
    walkable_by_pos: dict = field(default_factory=dict)  # {(col,row): walkable} (boardGraph, statique) :
    #                                gate STATIQUE de placement CanAddUnit (HammerOfWrath +5 displacement #116)
    obs_units: list = field(default_factory=list)  # observeBattle.units (isDead/teamId/visualId/pos) :
    #                                SOURCE DES MORTS pour RitesOfRestoration (decisionView garde les
    #                                depouilles -> observeBattle.isDead, cf. project_decisionview_keeps_dead)
    elev_by_pos: dict = None       # {(col,row): elevation} (tileMeta) — porte d'adjacence |Δelev|<2
    wt: object = None              # Weights BC (NovaShield : terme Tile(7) = tile_utility)
    is_temporary_by_pos: dict = field(default_factory=dict)  # Tile(7) (feuille is_temporary)
    effects_by_pos: dict = field(default_factory=dict)       # Tile(7) (feuille TileEffects)
    tile_id_by_pos: dict = field(default_factory=dict)       # {(col,row): tileEntityId} (boardGraph) :
    #                            cible d'une self-cast AoE (heal) = MainTile-id du caster, PAS son unit-id
    active_levels: object = None   # callable() -> {unitId: activeAbilityLevel} (lazy combatSnapshot) :
    #                            niveau d'ability des allies pour InspiredToGreatness (util = level)
    ability_config: object = None  # callable(uid) -> {"active","passive","multiplier"} (combatSnapshot) :
    #                            niveau PASSIF du caster pour ReachedSummonCap (#38 : ControlEdict est
    #                            le passif de Tan Gi'da -> maxSummons[level passif])
    units: list = field(default_factory=list)   # dv.units (par-unite abilities + usable/cooldown) :
    #                            etat cooldown des allies pour InspiredToGreatness (GetActive usable)
    cast_from_tiles: object = None   # callable(uid, target_id, ability_id) -> {currentValid, moveTiles} :
    #                            positionnement move-to-reach des NC ally-targeted (#81)
    plans: dict = field(default_factory=dict)   # {unitId: plan attackPlans} de TOUTES les unites (#44) :
    #                            `GetNumAttackTargetsInPosition(unit, tile)` de TheQuickening interroge
    #                            aussi le plan d'un ALLIE (terme +1 de l'ami echange), pas seulement `plan`
    scene: object = None           # engine.playbook.Scene (predictor+sctx) — HammerOfWrath (#114) score
    #                            son utilité de décision via Σ CalculateUtilityFromDamageEvent (prédiction
    #                            dégât INTERNE, bypass du gate d'affichage #109) sur cible + adjacents.
    debug: bool = False


class NonComparablePlaybook:
    """`NonComparablePlaybook<T>` — playbook à heuristique ENTIÈRE écrite dans la feuille (summons,
    buffs, retraite), par opposition à `ComparablePlaybook<T>` (attaques/soins = somme pondérée sur
    prédictions). Sous-classe = un playbook natif homonyme (selector + leaf `EvaluateNonComparable`
    + MIN_UTILITY du cctor)."""
    ABILITY_ID: int = -1
    MIN_UTILITY: float = 0.0       # cctor du playbook -> gate Bucket.AddAction (util >= min)
    PRIORITY: int = 0              # get_Priority (slot0) -> tier NonComparable (dict[prio], IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists)
    #                                DEFAUT 0 = `AbilityPriority.Normal` (236 abilities / 258).
    #                                22 playbooks SURCHARGENT le getter : poser alors
    #                                `PRIORITY = native_priority(<ABILITY_ID>)` (table ci-dessus).

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`IPlaybook` slot 4 `ShouldEvaluate(unit)` — gate AMONT du générateur
        `ActiveAbilityActionGenerator.<GenerateActions>d__7 IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` (`FUN_180003bd0(4, …)`),
        évalué AVANT tout sweep de position : False -> l'ability est SAUTÉE entièrement (le
        fallback Comparable prend la main).

        Impl de base = `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` : `prob := vtable[0x1f8]
        GetUseProbability(unit)` puis `prob >= 1 -> True` ; `prob <= 0 -> False` ; sinon tirage
        RNG autobot. Les DEUX surcharges de base `GetUseProbability` (IdunBattle.AI.Playbook.BasePlaybook$$GetUseProbability / IdunBattle.AI.Playbook.BasePlaybook$$GetUseProbability,
        slots 0x208/0x1f8) rendent `Fix64(1)` -> True constant ici. Les playbooks à
        `GetUseProbability` conditionnelle (BlackRage IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$GetUseProbability = 0.4, ItItches IdunBattle.AI.Playbook.Loki.ItItchesPlaybook$$GetUseProbability)
        restent True = écart assumé « porte ALÉATOIRE non modélisée » (moteur déterministe,
        cf. §5 case-44). Un playbook qui OVERRIDE le slot 4 lui-même (vtable ≠ IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate)
        surcharge cette méthode (ex. corps foldé IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate `GetStat(unit,12) > 1`)."""
        return True

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Mirror <GenerateActions>d__7 pour CETTE ability : balaie positions/cibles (selector
        propre), score (evaluate_non_comparable), gate par MIN_UTILITY. Rend 0 ou 1 candidat
        {target, ability, to, pred} = le meilleur de l'ability (Bucket local deja argmax-e)."""
        raise NotImplementedError


class _PlanTargetPlaybook(NonComparablePlaybook):
    """Base des abilities d'ATTAQUE NonComparable (BloodyFury, VexillaMagnifica, HammerOfWrath,
    BlackRage, VigilanceEternal, Stormcaller). Le generator natif `<GenerateActions>d__7 IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`
    balaie les POSITIONS candidates dans l'ordre de `ctx.reach_nc` = la liste `tiles` du tactic
    (`ABaseAiUnitTactic$$GenerateActionTiles` -> `IBattleQuery`+0xe =
    `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` : **position COURANTE en
    tete**, puis les tuiles de move dans l'ordre du movable set natif) et, PAR position, les cibles
    eligibles ; `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` SEED le 1er ajoute puis ne remplace QUE si STRICTEMENT superieur
    -> au tie d'utilite, la PREMIERE position de cet ordre gagne, c'est-a-dire l'ORIGINE : une
    utilite position-INDEPENDANTE (BloodyFury, Stormcaller) fait donc caster SANS BOUGER.
    L'eligibilite par position pour la paire (ability, cible) = les tuiles rankees du plan natif
    (`GetAllValidTargetsFromAllPossibleMovementTiles`) -> gate `P in ranked(tgt)`.

    Miss vecu (#32, 909 s17 VigilanceEternal) : l'ancien balayage en ordre RANKED du plan cassait
    le tie 43.867 vers (4,2) (1re rankee) quand le natif prend (3,4) (1re du movable set) — l'origine
    n'y etait pas legale pour la paire, d'ou la 1re tuile de move.
    Miss vecu (R1, 31337/C3_01 s11 Stormcaller) : `reach_nc` etait construit origine-LAST -> le port
    prenait la 1re tuile de MOVE (2,4) la ou le natif restait en (2,3)."""

    def evaluate_non_comparable(self, tile: tuple, target, ctx: NCContext) -> float | None:
        raise NotImplementedError

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        pairs = []   # (tgt, tuiles rankees de la paire) — ordre cibles = ordre du plan natif
        for ev in (ctx.plan.get("evals") or []):
            if ev.get("abilityId") != self.ABILITY_ID or not ev.get("rankCount"):
                continue
            rset = {(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                    if rk.get("col") is not None}
            if rset:
                pairs.append((ev.get("targetId"), rset))
        if not pairs:
            return []
        best = None  # (target, tile, util)
        for P in ctx.reach_nc:                      # ORIGINE en tete puis moves (ordre natif)
            for tgt, rset in pairs:
                if P not in rset:
                    continue                        # pas de cast (ability,tgt) depuis cette position
                nu = self.evaluate_non_comparable(P, tgt, ctx)
                if nu is None:
                    continue
                if best is None or nu > best[2]:   # strict > : premiere position du max gagne
                    best = (tgt, P, nu)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        return [{"target": best[0], "ability": self.ABILITY_ID,
                 "to": (best[1] if best[1] != ctx.origin else None), "pred": best[2]}]
