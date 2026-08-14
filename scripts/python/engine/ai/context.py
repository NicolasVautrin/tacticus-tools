"""AiDecisionContext — l'état d'une décision, alimenté par RPC (la COUTURE oracle/moteur explicite).

Le décideur natif lit l'état live (ECS) ; notre port le lit via RPC (`decisionView`, `observeBattle`,
`tileMeta`, `pathDistToEnemies`, `abilityTargets`). Ce module CONCENTRE toute cette lecture en UN objet
`AiDecisionContext` que les générateurs/playbooks consomment — au lieu d'un câblage RPC diffus dans le
spine. C'est la divergence ASSUMÉE (le natif n'a pas besoin de RPC) rendue en une frontière nette et
unique (`build(...)`), pas une infidélité cachée.

`rpc(method, body, timeout) -> dict` est INJECTÉ par le harnais -> `engine/` reste agnostique du
transport (host/session). `predictor`/`sctx` = le prédicteur OFFLINE de `predict_validate` (le port
fidèle de `GenerateMultiHitAttackPredictions`), déjà construit 1×/runner.

Mirroir de la tête de l'ancien `engine_decide` (mêmes RPC, mêmes champs dérivés) — extraction pure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from engine import battle_query  # gate IdunBattle.Core.Services.AttackQuery$$CanUseAbility (stun/taunt)
from engine.entities.active_ability_type import ActiveAbilityType  # repli de nom (cf. _ability_name)
from engine.playbook.scene import Scene, step_context as _step_context  # état objet + seam live-feed
# #443-r2-b1 : projection ACTIF-ONLY de la liste BRUTE d'effets — le pendant de la porte
# `decision_view_seed_body` (canal `includeInactive`), UN SEUL foyer pour les deux faces.
from engine.runner.snapshot import active_only_rows
from ..services.machine_of_war_position import machine_of_war_position_for_player
from ..services import current_player as _cp   # forme B (#359-r6) : foyer `current_player_team`
from engine.entities.traits.unit_trait import UnitTrait, entity_trait_names, has_trait
from engine.utilities.move import UtilityMovementCase


@dataclass
class AiDecisionContext:
    """Bundle immuable-par-décision de l'état requis pour scorer/choisir l'action de `uid`.

    Construit par `build(...)` (une passe RPC). Les générateurs/playbooks n'en lisent que des champs
    — aucun n'ouvre lui-même le transport (sauf lazy `ability_targets`, exposé ici)."""

    # --- Transport (seam) ---
    rpc: Callable[..., dict]          # rpc(method, body, timeout) -> result dict (injecté)
    rid: int                          # runnerId (pour construire les bodies des appels lazy)
    wt: Any                           # poids BC chargés (weights.load())
    predictor: dict | None            # prédicteur OFFLINE (combatSnapshot cold, 1×/runner)
    sctx: dict | None                 # step_context du prédicteur (état courant du pas)
    scene: Any                        # Scene objet (predictor+sctx consolidés) -> engine.playbook.prediction

    # --- Unité active + vue globale ---
    uid: int
    me: dict | None
    units: list                       # dv.units (toutes, vivantes ou non)
    cur: int | None                   # dv.currentPlayer
    plans: dict                       # {unitId: plan attackPlans} (abilities d'ATTAQUE rankées)

    # --- Positions / adversaires / alliés ---
    enemies: list                     # unités adverses vivantes positionnées
    epos: list                        # positions ennemies (GetAdjacentEnemies) — COMPLET (occupance)
    tgt_epos: list                    # positions ennemies CIBLABLES (post-filtres `FindClosestEnemy`
    #                                   IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext #26 : Environment/IsTargetable/IsIrrelevantObject/
    #                                   IsDead/GetOnlyTargets) — seed du fallback HEX de MinDist(16)
    fpos: list                        # positions alliées, self exclu (GetAdjacentFriends)
    origin: tuple | None              # (col,row) de l'unité active
    move_tiles: list                  # tuiles de mouvement atteignables (aiMovableTiles[uid])
    reach_nc: list                    # ALIAS de `action_tiles` (nom historique côté NonComparable) :
    #                                   la MÊME liste native `tiles`, origine EN TÊTE
    action_tiles: list                # `tiles` de `DefaultAiUnitTactic.<CalculateNextActionForUnit>d__5`
    #                                   = `ABaseAiUnitTactic$$GenerateActionTiles` -> `IBattleQuery`+0xe
    #                                   = `BattleQuery$$GetCurrentAndMovablePositionsFor` : position
    #                                   COURANTE EN TÊTE puis les tuiles de move. L'ORDRE porte le
    #                                   tie-break natif (Bucket keep-first) -> cf. `action_tiles_for`.

    # --- Santé / identités ---
    hp_cur_by_id: dict                # {id: hp courant} (GetStat 5 = Health)
    hpmax_by_id: dict                 # {squadId: hpMax} (observeBattle) — coût PV / composite Damage
    obs_units: list                   # observeBattle.units bruts (réutilisés par le heal : hpMax+hp)
    ab_name_by_id: dict               # {abilityId: name} des abilities de l'unité active
    normal_ids: set                   # ids d'attaque NORMALE de l'unité (champ decisionView `kind == "normal"`)

    # --- Métadonnées de tuile (Tile(7) + porte d'adjacence + MinDist chemin) ---
    elev_by_pos: dict                 # {(col,row): elevation}
    is_temporary_by_pos: dict         # {(col,row): bool}
    effects_by_pos: dict              # {(col,row): [effectName…]} (feuille TileEffects)
    pathdist_by_pos: dict             # {(col,row): pathDist} (MinDist fidèle, distance de CHEMIN)
    tile_id_by_pos: dict              # {(col,row): tileEntityId} (boardGraph) — cible d'une self-cast
    #                                   AoE = MainTile-id du caster (GenerateAction(this,pos,MainTile,util))
    neigh_by_pos: dict                # {(col,row): [voisins ordre natif GetAdjacentTiles]} (boardGraph) —
    #                                   cible EXACTE de Gauntlets = 1er ennemi ring-1 en ordre inversé (#117)
    walkable_by_pos: dict             # {(col,row): walkable} (boardGraph, statique) — gate STATIQUE de
    #                                   placement (TileExtensions.CanAddUnit) ; l'occupation DYNAMIQUE se
    #                                   lit via epos/fpos/origine (frais), PAS le occupantUnitId caché (#116)
    terrain_by_pos: dict              # {(col,row): tileDefId} (boardGraph, statique) — covers HÉBERGÉS par
    #                                   le terrain sommés par TileEffects(10) Loop2 (DryBush->LightCover, case-37)
    is_wall_by_pos: dict = field(default_factory=dict)
    #     {(col,row): bool} <- boardGraph.isWall = `TileComponent+0x41`, le drapeau que lit
    #     `MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingWalls` — le volet MURS
    #     de la LIGNE DE VUE (#433-r4-r2-r1-r2). VIDE = canal muet -> aucun mur vu (PERMISSIF).
    is_in_fog_by_pos: dict = field(default_factory=dict)
    #     {(col,row): bool} <- boardGraph.isInFog = `TileComponent+0x40`, le SECOND volet de
    #     `TileExtensions$$IsWalkable(t, checkFog: true)` — celui que `walkable_by_pos`
    #     (= `BattleQuery$$IsWalkableTile`) ne porte PAS. Consommé avec lui par l'étage AMONT
    #     `TargetingQuery$$GetTilesInRange` (#433-r4-r2-r1-r2-r2-r1). VIDE = canal muet -> volet
    #     inerte (PERMISSIF). Mesuré : 31 tuiles `walkable && isInFog` sur `C6_02`.
    # Deux attributs de TUILE que `tileMeta` remonte DÉJÀ et que le port jetait (#175) : sans eux les
    # feuilles Tile(7) qui les gatent restent muettes même quand `ctx.unit_traits` est peuplé.
    is_territory_by_pos: dict = field(default_factory=dict)
    #     {(col,row): bool} <- tileMeta.isTerritory = `TileComponent+0x2e`, l'octet que lit
    #     `IdunBattle.Entities.TileExtensions$$IsTerritoryTile` -> feuille CapturePoint(25) (+/-300)
    tile_effect_type_ids_by_pos: dict = field(default_factory=dict)
    #     {(col,row): [EffectType]} <- tileMeta.effects[].effectType = `EffectComponent+0x58` ->
    #     feuilles DespoiledGround(28, 0x5c4), Contaminated(25, 0x4dc), MoltenForm(23, 5/10)
    # --- `MachineOfWarPosition` du joueur COURANT (predicat `IsPositionMachineForCurrentPlayer`) ---
    # Consomme par les arbres dont la GEOMETRIE depend du cote du plateau : 1148 DaemonicOrdnance
    # (face DECISION), 1142 MacroPlasmaIncinerator et DevastatingRefrain (face COMBAT).
    # TROIS canaux, dans l'ordre de fidelite -- cf. `machine_of_war_position`.
    mow_position_by_player: Any = None
    #     {playerId: `MachineOfWarPosition`} <- `boardGraph.mowPositions` (#311), c.-a-d.
    #     `IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer(player)` INVOQUE sur le
    #     runner, joueur par joueur. C'est la valeur EFFECTIVE que compare le predicat -- le natif
    #     lui-meme, pas une reconstitution. TRI-ETAT : `None` = pas mesure (canal absent : chemin
    #     OFFLINE, ou methode irresolue cote hooks), `{}` = mesure et aucun joueur.
    spawn_groups: Any = None
    #     `SpawnPointGroups` du SpawnPointSet ACTIF de la BC du runner (`BattleQuery+0x78`).
    #     MIRROR de la cascade native (`machine_of_war_position_for_player`), donc un cran EN DESSOUS
    #     du canal ci-dessus : il DEVINE `playerNr = 0` la ou le natif le LIT de
    #     `StateExtensions$$GetTeam(state)` (`local_res10 >> 0x20` au decompile). Reste indispensable
    #     au chemin OFFLINE (`build_from_state`), qui n'a aucun RPC. `None` = non lu.
    mow_slot_by_player: dict = field(default_factory=dict)
    #     {playerId: `MachineComponent.Position @0x78`} <- `decisionView.mows[].owner`/`.slot`.
    #     REPLI, exact quand il repond : le slot ou la MoW du joueur A ETE deployee EST la
    #     `MachineOfWarPosition` de son groupe de spawn. C'est le regime REEL de 1148 (son porteur
    #     `blackForgefiend` EST une MoW) ; il ne manque que dans les montages qui GREFFENT l'ability
    #     sur un hero. Table vide = aucune MoW.
    current_player_team: Any = None
    #     `TeamComponent.<+0x24>` du joueur courant, derive de `decisionView` (l'equipe des unites
    #     `ctrl`). Entree de `GroupForPlayer(teamIndex, playerNr)`.
    mindist_case: Any = None
    #     `UtilityMovementCase` (engine.utilities.move) — les DEUX champs que la feuille
    #     MinDistanceToClosestEnemy(17) LIT sur son case : `+0x10` Unit et `+0x20` ClosestEnemy,
    #     plus les deux valeurs que ses gates en derivent (traits du mover, CriticalChance du mover,
    #     traits du ClosestEnemy). `None` = le port n'a pas pu etablir le case -> aucun gate (#236).
    offline_triggered_kits: dict | None = None
    #     {unitId: [TriggeredAbilityType]} du chemin OFFLINE (#983-r1) — le MEME substrat d'ENTITE
    #     que le RPC `unitAbilityStates` seede cote runner (`UnitContext.triggered_abilities`,
    #     `snapshot._load_triggered_abilities`), lu ici depuis le `State` par `state_bridge`.
    #     C'est ce que `live_triggered_kits()` sert quand `rid` est faux : sans lui, le chemin
    #     offline rendait `{}` et tout consommateur retombait sur le kit gameconfig SEUL.
    #     TRI-ETAT, PAR UNITE : `None` = canal absent (contexte LIVE, ou bridge anterieur) ;
    #     une table ne porte QUE les unites dont le canal a parle -- une unite absente de la table
    #     n'est PAS « sans passif », elle est NON MESUREE, et son lecteur retombe sur le gameconfig.
    victory_conditions: dict | None = None
    #     `BC.Victory.VictoryConditions` -- le `<victoryConfig @+0x18>` que lit
    #     `IdunBattle.Core.Services.BattleQuery$$GetMaxRounds`, donc l'entree 1 de
    #     `BattleQuery$$HasMinimumRemainingTurns` (#1027-r5). TRI-ETAT : `None` = canal non fourni
    #     (chemin LIVE -- aucun RPC ne publie `BC.Victory`) -> le foyer applique sa cascade et
    #     retombe sur le defaut DERIVE de `data/seed-bc.json` ; un dict fourni SANS
    #     `MainPlayerRoundLimitation` est une MESURE (« cette BC ne pose aucun plafond »).
    turns_ended_by_first_player: int | None = None
    #     `matchTurn.GetAmountOfTurnsEndedByPlayer(GetPlayerTurnOrder()[0])` = le
    #     `TurnComponent.<Dictionary @+0x40>`, entree 2 du bras 2 du meme gate. `None` = non mesure.
    #     ⚠ SURTOUT PAS `decisionView.turnsEnded`, qui publie la SOMME sur tous les joueurs.

    debug: bool = False

    def machine_of_war_position(self):
        """`IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer(currentPlayer)` —
        la valeur que compare `IsPositionMachineForPlayerTrigger$$ShouldTrigger`.

        Cascade, de la source NATIVE au repli, puis a l'ignorance ASSUMEE :

        0. `mow_position_by_player` -- le natif INVOQUE (`boardGraph.mowPositions`, #311). Rien a
           reconstituer : c'est la valeur que le predicat compare, repli natif compris ;
        1. sinon `spawn_groups` lus -> mirror de la cascade (`GroupForPlayer` + le fallback natif
           quand le groupe manque REELLEMENT dans la config). Seule voie du chemin OFFLINE ;
        2. sinon, le slot de la MoW du joueur courant (`decisionView.mows`) : le slot ou elle a ete
           deployee EST la `MachineOfWarPosition` de son groupe. ATTENTION -- ce repli est
           structurellement MUET la ou le natif diverge du fallback : un groupe qui declare
           `MachineOfWarPosition = 0` (502 des 675 boards) ne deploie AUCUNE MoW, donc
           `decisionView.mows` y est VIDE (mesure #302 tranche 5, board `C1_01`) ;
        3. sinon `None` = **non mesure**. Le port ne devine PAS : sur les 675 boards du depot, 502
           declarent `MachineOfWarPosition = 0` et 173 declarent (2, 1) -- appliquer le fallback
           natif a l'aveugle serait faux sur ~74 % des plateaux (cf.
           `engine.services.machine_of_war_position`). Le predicat rend alors False."""
        return _machine_of_war_position(self.spawn_groups, self.current_player_team,
                                        self.mow_slot_by_player, self.cur,
                                        self.mow_position_by_player)

    def ability_targets(self, unit_id: int, ability_id: int) -> dict:
        """Lazy `abilityTargets` (union des cibles/tuiles légales) — `GetEligibleTargetsSelectable`.
        Appelé à la demande (summon, heal) : coûteux, donc PAS pré-fetché pour toutes les abilities."""
        return self.rpc("abilityTargets",
                         {"runnerId": self.rid, "unitId": unit_id, "abilityType": ability_id}, 40)

    def cast_from_tiles(self, unit_id: int, target_id: int, ability_id: int) -> dict:
        """Lazy `castFromTiles` : tuiles (courante + move) d'ou `unit_id` peut caster `ability_id` sur
        `target_id` (GetInvalidTargetReason valide par tuile). `{currentValid, moveTiles:[{col,row}]}`.
        Résout le positionnement move-to-reach des NC ally-targeted (#81 : InspiredToGreatness)."""
        return self.rpc("castFromTiles", {"runnerId": self.rid, "casterId": unit_id,
                                          "targetId": target_id, "abilityType": ability_id}, 40)

    def _unit_ability_config(self) -> dict:
        """`{unitId: {"active", "passive", "multiplier"}}` via `combatSnapshot.unitConfig` (statique/
        bataille -> cache par rid, 1 fetch lazy). Niveau ACTIF `activeAbilityLevel` (cfg+0xB8), niveau
        PASSIF `passiveAbilityLevel` (cfg+0xBC), `AbilityVariablesMultiplierPercentage` (cfg+0x74, defaut
        100). Clef = `entityId` (= dv.id/squadId). `stats`/GetStat(18) renvoie null ici -> unitConfig."""
        m = _ACTIVE_LEVEL_CACHE.get(self.rid)
        if m is None:
            snap = self.rpc("combatSnapshot", {"runnerId": self.rid}, 40) or {}
            m = {}
            for u in (snap.get("units") or []):
                k = u.get("entityId")
                if k is not None:
                    cfg = u.get("unitConfig") or {}
                    m[k] = {"active": int(cfg.get("activeAbilityLevel") or 0),
                            "passive": int(cfg.get("passiveAbilityLevel") or 0),
                            "multiplier": int(cfg.get("abilityVariablesMultiplier") or 100)}
            _ACTIVE_LEVEL_CACHE[self.rid] = m
        return m

    def live_triggered_ability_ids(self, unit_id: int) -> list:
        """Ids de `TriggeredAbilityType` REELLEMENT portes par `unit_id` en bataille — lecture du
        `TriggeredAbilityComponent` via le RPC `unitAbilityStates`.

        C'est la SOURCE du dispatcher natif : `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.
        u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` itere l'AbilitiesComponent ECS, pas le
        gameconfig. La difference porte : `passiveAbilities` du gameconfig IGNORE les abilities
        accordees par TRAIT et par RELIQUE. Cas mesure (N13, `C4_09`/31337 pas 22) : admecMarshall
        porte la relique `KardiocoreGalvanus` (1457), absente de son kit gameconfig, dont le
        playbook vaut +5 par ami adjacent a la tuile candidate.

        LECTURE DU CHAMP : le RPC ne nomme PAS le type ; il dumpe `raw` = 12 int32 lus a partir de
        `TriggeredAbility+0x10`, et l'id est `raw[0]` (= le champ `AbilityName`). Verifie par
        recoupement sur la MEME structure : `level`/`mult`, exposes separement par le RPC depuis
        `+0x20`/`+0x24`, retombent exactement sur `raw[4]`/`raw[5]` -> la base est bien `+0x10`.
        Mesure de controle (C4_09/31337) : u84 admecMarshall = [1200 ControlEdict, **1457
        KardiocoreGalvanus** (relique), 1201] ; u94 ultraCalgar = [1014 RitesOfBattle, 1186, 1024] ;
        u96 spaceStormcaller = [1194 LordOfTempests, ...] -- chaque `raw[0]` retombe sur le passif
        gameconfig connu, plus les ids que le gameconfig ignore.

        Cache par (rid, unit_id) : le kit declenche est pose au spawn (AbilityFactory) et ne bouge
        qu'au grain d'un `AddTraitOperation` en cours de bataille — meme niveau de fraicheur que
        `_unit_ability_config`. RPC indisponible / unite absente -> `[]`, et l'appelant retombe sur
        le gameconfig (degradation = comportement d'avant ce cablage)."""
        if not self.rid:
            # Contexte OFFLINE (`state_bridge`, rid=0) : son seam RPC ne sert qu'`abilityTargets`
            # et rend `{"units": []}` pour tout le reste -- on ne l'appelle donc pas. Mais le
            # substrat d'ENTITE, lui, est LA (#983-r1) : `UnitContext.triggered_abilities` publie
            # par `state_bridge` dans `offline_triggered_kits`. C'etait le residu N13-b (kit
            # declenche offline sans traits/reliques) ; sans pont, l'appelant retombait sur le
            # gameconfig ALORS QUE la mesure existait. Table absente / unite non mesuree -> `[]`,
            # et l'appelant retombe sur le gameconfig, comme avant.
            return list((self.offline_triggered_kits or {}).get(int(unit_id)) or [])
        key = (self.rid, int(unit_id))
        got = _TRIGGERED_KIT_CACHE.get(key)
        if got is None:
            got = []
            try:
                r = self.rpc("unitAbilityStates",
                             {"runnerId": self.rid, "unitId": int(unit_id)}, 40) or {}
                for u in (r.get("units") or []):
                    for t in (u.get("triggered") or []):
                        raw = (t or {}).get("raw") or []
                        v = raw[0] if raw else None      # TriggeredAbility.AbilityName @+0x10
                        if isinstance(v, int) and v > 0 and v not in got:
                            got.append(v)
            except Exception:
                got = []
            _TRIGGERED_KIT_CACHE[key] = got
        return got

    def live_triggered_kits(self) -> dict:
        """`{unitId: [TriggeredAbilityType]}` pour TOUTES les unites de la bataille, en UN SEUL RPC.

        Meme lecture que `live_triggered_ability_ids` (le `TriggeredAbilityComponent`, `raw[0]` =
        `TriggeredAbility.AbilityName`) : `unitAbilityStates` SANS `unitId` enumere toutes les
        entites `Unit`/`Machine` d'un coup. Necessaire des qu'un consommateur a besoin du kit
        DECLENCHE de plusieurs unites -- ex. `AttractToDecoysUtility` (64), dont le compte natif
        boucle sur `GetAllAliveUnits` (slot 0x88 de l'interface de query, le meme que
        `IdunBattle.Entities.Selectors.AllAliveUnitsSelector$$Select` et
        `IdunBattle.AI.Playbook.BasePlaybook$$GetAllEnemies`) : appeler la version par-unite N fois
        couterait N walks complets du state pour la meme information.

        Alimente le MEME cache `(rid, unitId)` que la version par-unite -- les deux voies sont donc
        coherentes et se servent mutuellement -- plus un cache PAR RID de la table complete, car
        l'appelant (`_adjacent_units` via `tile_leaf_ctx`) est reevalue PAR TUILE CANDIDATE. RPC
        indisponible -> `{}`, et l'appelant retombe sur le kit gameconfig (degradation deja en
        vigueur).

        CHEMIN OFFLINE (`rid` faux, #983-r1) : ce n'est plus `{}` d'office. Le MEME substrat
        d'ENTITE existe cote `State` -- `UnitContext.triggered_abilities`, que
        `snapshot._load_triggered_abilities` seede depuis ce meme RPC -- et `state_bridge` le
        publie dans `offline_triggered_kits`. Sans ce pont, le canal restait muet HORS LIVE alors
        que la donnee etait deja en memoire : une degradation PERMISSIVE gratuite. Champ `None`
        (aucun pont) -> `{}`, comportement d'avant."""
        if not self.rid:
            return self.offline_triggered_kits or {}
        cached = _TRIGGERED_KITS_ALL_CACHE.get(self.rid)
        if cached is not None:
            return cached
        out: dict = {}
        try:
            r = self.rpc("unitAbilityStates", {"runnerId": self.rid}, 60) or {}
        except Exception:
            _TRIGGERED_KITS_ALL_CACHE[self.rid] = out
            return out
        for u in (r.get("units") or []):
            uid = u.get("entityId")             # cle du RPC (= dv.id / squadId), cf. rpc-snapshot.ts
            if uid is None:
                continue
            ids: list = []
            for t in (u.get("triggered") or []):
                raw = (t or {}).get("raw") or []
                v = raw[0] if raw else None          # TriggeredAbility.AbilityName @+0x10
                if isinstance(v, int) and v > 0 and v not in ids:
                    ids.append(v)
            out[int(uid)] = ids
            _TRIGGERED_KIT_CACHE[(self.rid, int(uid))] = ids
        _TRIGGERED_KITS_ALL_CACHE[self.rid] = out
        return out

    def active_ability_levels(self) -> dict:
        """`{unitId: activeAbilityLevel}` (stat 18 / unitConfig+0xB8). Source du NIVEAU d'ability ACTIVE
        pour `InspiredToGreatnessPlaybook` (util = level zero-based)."""
        return {k: v["active"] for k, v in self._unit_ability_config().items()}

    def heal_config(self, unit_id: int) -> dict:
        """`{"active","passive","multiplier"}` de `unit_id` (unitConfig) : niveaux d'ability actif/passif
        + AbilityVariablesMultiplierPercentage. Source OFFLINE de la magnitude de soin
        `ability_var(hpToHeal, level, multiplier_pct)` (#79) : un soin ACCORDE par un passive
        (`Heal_<P>`/`<P>_Heal`) s'indexe au niveau PASSIF ; un soin natif au niveau ACTIF."""
        return self._unit_ability_config().get(
            unit_id, {"active": 0, "passive": 0, "multiplier": 100})


_BOARD_GRAPH_CACHE: dict = {}      # {rid: réponse boardGraph BRUTE} — 1 fetch/rid (partagé)
_BOARD_TILE_IDS_CACHE: dict = {}   # {rid: {(col,row): tileEntityId}} — board statique, dérivé
_BOARD_NEIGH_CACHE: dict = {}      # {rid: {(col,row): [voisins ordre natif]}} — dérivé
_BOARD_WALKABLE_CACHE: dict = {}   # {rid: {(col,row): walkable}} — board statique, dérivé (#116)
_BOARD_TERRAIN_CACHE: dict = {}    # {rid: {(col,row): tileDefId}} — terrain statique, dérivé (case-37)
_BOARD_IS_WALL_CACHE: dict = {}    # {rid: {(col,row): isWall}} — TileComponent+0x41, dérivé (#433-r4-r2-r1-r2)
_BOARD_IS_IN_FOG_CACHE: dict = {}  # {rid: {(col,row): isInFog}} — TileComponent+0x40, dérivé (#433-r4-r2-r1-r2-r2-r1)
_ACTIVE_LEVEL_CACHE: dict = {}     # {rid: {unitId: {active,passive,multiplier}}} — combatSnapshot, 1 fetch/rid
_TRIGGERED_KIT_CACHE: dict = {}    # {(rid, unitId): [TriggeredAbilityType]} — unitAbilityStates, 1 fetch/unite
#                                    (kit DECLENCHE reel : passifs + trait-granted + RELIQUES, cf. N13)
_TRIGGERED_KITS_ALL_CACHE: dict = {}   # {rid: {unitId: [TriggeredAbilityType]}} — unitAbilityStates SANS
#                                        unitId, 1 fetch/rid (#241 : `_adjacent_units` est reevalue par tuile)


def _board_graph(rpc: Callable[..., dict], rid: int) -> dict:
    """Réponse BRUTE de `boardGraph` (board STATIQUE -> cachée par rid ; 1 fetch partagé par tous
    les dérivés `_board_*`).

    #302 tranche 5 — c'est la RÉPONSE qui est cachée, plus ses seules `tiles`. Le champ
    `mowPositions` (#311) voyageait déjà dans cet objet et était jeté à la ligne suivante : le
    brancher ne coûte donc AUCUN RPC supplémentaire."""
    r = _BOARD_GRAPH_CACHE.get(rid)
    if r is None:
        r = rpc("boardGraph", {"runnerId": rid}, 60) or {}
        _BOARD_GRAPH_CACHE[rid] = r
    return r


def _board_graph_tiles(rpc: Callable[..., dict], rid: int) -> list:
    """Liste brute des tuiles `boardGraph` (board STATIQUE -> caché par rid ; 1 fetch partagé entre
    `_board_tile_ids` et `_board_neighbours`)."""
    return _board_graph(rpc, rid).get("tiles") or []


def _board_mow_positions(rpc: Callable[..., dict], rid: int):
    """`{playerId: MachineOfWarPosition}` — `boardGraph.mowPositions` (#311), c.-à-d.
    `IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer(player)` INVOQUÉ joueur par
    joueur sur le runner. C'est la valeur EFFECTIVE que compare
    `IdunBattle.Entities.Triggers.IsPositionMachineForPlayerTrigger$$ShouldTrigger`.

    TRI-ÉTAT préservé depuis le hook, qui le porte déjà (`mowPositions: null` = méthode irrésolue) :
    `None` = **pas mesuré**, `{}` = mesuré et aucun joueur. Les confondre ferait passer un capteur
    MORT pour un plateau sans joueurs. Une entrée dont le `machineOfWarPosition` est `null` (le hook
    a capturé une erreur d'invocation) est ÉCARTÉE — jamais rabattue sur `0`, qui est une valeur
    LÉGITIME (`MachineOfWarPosition.None_`) portée par 502 des 675 boards."""
    mp = _board_graph(rpc, rid).get("mowPositions")
    if not isinstance(mp, list):
        return None
    out = {}
    for e in mp:
        pid, pos = (e or {}).get("playerId"), (e or {}).get("machineOfWarPosition")
        if pid is not None and pos is not None:
            out[pid] = int(pos)
    return out


def _board_tile_ids(rpc: Callable[..., dict], rid: int) -> dict:
    """{(col,row): tileEntityId} depuis `boardGraph` (board STATIQUE -> caché par rid). Le tile-id
    = l'entity-id de tuile qu'`applyOneAction` attend comme cible (findTileEntityId) ET que le natif
    encode comme cible d'une self-cast AoE (MainTile). `tileMeta` ne porte pas l'id -> boardGraph."""
    m = _BOARD_TILE_IDS_CACHE.get(rid)
    if m is None:
        m = {(t.get("col"), t.get("row")): t.get("id") for t in _board_graph_tiles(rpc, rid)}
        _BOARD_TILE_IDS_CACHE[rid] = m
    return m


def _board_neighbours(rpc: Callable[..., dict], rid: int) -> dict:
    """{(col,row): [voisins (col,row) dans l'ORDRE natif `GetAdjacentTiles`]} depuis `boardGraph`
    (`neighbours` = liste d'IDs de tuile -> résolus en positions). L'ordre natif est PRÉSERVÉ (le
    consommateur `gauntlets_target` gère l'inversion `SortReverseSelector`). Board statique -> caché.
    Sert à la CIBLE exacte de Gauntlets (#117 : 1er ennemi ring-1 en ordre voisins inversé)."""
    m = _BOARD_NEIGH_CACHE.get(rid)
    if m is None:
        tiles = _board_graph_tiles(rpc, rid)
        id2pos = {t.get("id"): (t.get("col"), t.get("row")) for t in tiles}
        m = {(t.get("col"), t.get("row")):
             [id2pos[n] for n in (t.get("neighbours") or []) if n in id2pos]
             for t in tiles}
        _BOARD_NEIGH_CACHE[rid] = m
    return m


def _board_terrain(rpc: Callable[..., dict], rid: int) -> dict:
    """{(col,row): tileDefId} depuis `boardGraph` (terrain STATIQUE `TileId` de la BC : Grass/DryBush/
    Trench/... — board caché par rid). Alimente les covers HÉBERGÉS par le terrain sommés par la feuille
    TileEffects(10) via son Loop2 (DryBush->LightCover ; case-37). `tileMeta` ne porte pas le terrain."""
    m = _BOARD_TERRAIN_CACHE.get(rid)
    if m is None:
        m = {(t.get("col"), t.get("row")): t.get("tileDefId") for t in _board_graph_tiles(rpc, rid)}
        _BOARD_TERRAIN_CACHE[rid] = m
    return m


def _board_walkable(rpc: Callable[..., dict], rid: int) -> dict:
    """{(col,row): bool walkable} depuis `boardGraph` (`BattleQuery.IsWalkableTile` = `TileExtensions
    .IsWalkable`, cf. rpc-board.ts) — board STATIQUE (murs / terrain infranchissable), caché par rid.
    Gate STATIQUE de placement (`TileExtensions.CanAddUnit`) : une tuile non-walkable ne peut jamais
    accueillir d'unité. L'OCCUPATION dynamique se lit séparément (epos/fpos/origine frais), PAS via le
    `occupantUnitId` du boardGraph caché (il serait périmé — le board est caché, l'occupation change)."""
    m = _BOARD_WALKABLE_CACHE.get(rid)
    if m is None:
        m = {(t.get("col"), t.get("row")): bool(t.get("walkable"))
             for t in _board_graph_tiles(rpc, rid)}
        _BOARD_WALKABLE_CACHE[rid] = m
    return m


def _board_is_wall(rpc: Callable[..., dict], rid: int) -> dict:
    """{(col,row): bool isWall} depuis `boardGraph` (`TileComponent+0x41`, cf. `match-state.ts`) —
    board STATIQUE, caché par rid. C'est le second volet de la LIGNE DE VUE
    (`IdunBattle.Core.Services.MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingWalls`,
    #433-r4-r2-r1-r2) ; l'élévation (`tileMeta`) en est le premier.

    DISTINCT de `walkable` : `TileExtensions.IsWalkable` agrège le mur ET le terrain infranchissable,
    là où le prédicat de ligne de vue lit le SEUL drapeau `IsWall`. Les rabattre l'un sur l'autre
    ferait bloquer la vue par de l'eau ou un fossé, que le natif traverse."""
    m = _BOARD_IS_WALL_CACHE.get(rid)
    if m is None:
        m = {(t.get("col"), t.get("row")): bool(t.get("isWall"))
             for t in _board_graph_tiles(rpc, rid)}
        _BOARD_IS_WALL_CACHE[rid] = m
    return m


def _board_is_in_fog(rpc: Callable[..., dict], rid: int) -> dict:
    """{(col,row): bool isInFog} depuis `boardGraph` (`TileComponent+0x40`, publié par #403) —
    caché par rid. C'est le SECOND volet de `IdunBattle.Entities.TileExtensions$$IsWalkable(t,
    checkFog: true)`, la lambda que `TargetingQuery$$GetTilesInRange` applique en `RemoveAll`
    (#433-r4-r2-r1-r2-r2-r1).

    DISTINCT de `walkable` : celui-ci est `BattleQuery$$IsWalkableTile`, qui n'a PAS de paramètre
    `checkFog` et ne rend donc que le premier volet. MESURÉ (2026-08-04) : sur `C6_02`, 31 tuiles
    sur 63 sont `walkable == True` ET `isInFog == True` — les rabattre l'un sur l'autre laisserait
    31 tuiles attribuées à tort.

    CACHÉ comme `walkable`/`isWall` : mesuré STABLE sur ce montage (`C6_02`, 32 tuiles en fog
    inchangées après deux `endturn`). ÉCART NOMMÉ si un mode révélait le fog en cours de bataille."""
    m = _BOARD_IS_IN_FOG_CACHE.get(rid)
    if m is None:
        m = {(t.get("col"), t.get("row")): bool(t.get("isInFog"))
             for t in _board_graph_tiles(rpc, rid)}
        _BOARD_IS_IN_FOG_CACHE[rid] = m
    return m


def _tile_attribute_maps(tiles: list) -> tuple:
    """`(is_territory_by_pos, tile_effect_type_ids_by_pos)` depuis les tuiles `tileMeta` (#175).

    `isTerritory` = `TileComponent+0x2e` (lu par `IdunBattle.Entities.TileExtensions$$IsTerritoryTile`)
    et `effects[].effectType` = `EffectComponent+0x58` (comparé à `0x5c4` par
    `IdunBattle.AI.Utilities.DespoiledGroundUtility.u003CEvaluateMovementInStepsu003Ed__5$$MoveNext`)
    étaient tous deux déjà remontés par le RPC et jetés par le port : `effects_by_pos` ne gardait que
    le NOM (clé de poids BC de la feuille TileEffects(10)), jamais le type."""
    terr, tids = {}, {}
    for t in tiles:
        p = (t.get("col"), t.get("row"))
        terr[p] = bool(t.get("isTerritory"))
        ids = [int(e["effectType"]) for e in (t.get("effects") or [])
               if e.get("effectType") is not None]
        if ids:
            tids[p] = ids
    return terr, tids


def _enemies(units: list) -> list:
    """Unités adverses vivantes positionnées (ctrl=False => adverse)."""
    return [u for u in units if not u.get("ctrl") and u.get("alive") and u.get("pos")]


def action_tiles_for(origin: tuple | None, move_tiles: list) -> list:
    """Positions candidates du caster — mirror EXACT, **ORDRE COMPRIS**, de la liste `tiles` que
    `IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`
    construit puis passe à CHAQUE générateur (`GenerateActions(unit, position, tiles)`).

    Chaîne native, lue au décompilé (gqfc5mff6c) :

    - `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` appelle `IBattleQuery` **slot
      +0xe** avec `(unit, false, 0)`, puis, par ability de l'unité, `PlaybookDatabase.LoadPlaybook`
      -> slot 1 du playbook = `FilterMovementTiles`. Ce hook ne peut que RESTREINDRE : le seul corps
      existant, `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$FilterMovementTilesForMaxMovement`
      (RunsAround / RunsAway / SaviorProtocols), re-remplit un OrderedSet depuis les positions DÉJÀ
      présentes (argmax de longueur de chemin). Aucun playbook n'AJOUTE de position.
    - **Le slot +0xe est `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`**,
      pas `$$GetMovableTilesFor` (le 3e argument du call site vaut `0` : les deux `GetMovableTilesFor`
      /`GetMovablePositionsFor` DÉRÉFÉRENCENT ce `MovementOptions*` — seul
      `GetCurrentAndMovablePositionsFor` le copie par valeur et tolère 0 ; et c'est le seul à rendre
      des `UnitPosition`, le type qu'énumère `FilterMovementTilesForMaxMovement`). Son corps :

          var set = new OrderedSet<UnitPosition>(EntityExtensions.GetUnitPosition(unit));   // COURANTE
          set.UnionWith(_movementQuery.GetMovablePositionsFor(unit, flag, default));
          return set;

      => la position COURANTE est dans l'ensemble, **et elle y est la PREMIÈRE** (graine de
      l'`OrderedSet`, qui préserve l'ordre d'insertion) ; les tuiles de mouvement viennent après,
      dans l'ordre de `GetMovableTilesFor` (qui, lui, exclut bien la tuile courante — d'où l'union).

    L'ORDRE est ce qui compte : `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction`
    seede le 1er ajouté et ne remplace que sur `>` STRICT (keep-first au tie). La position courante
    étant énumérée en tête, **à utilité ÉGALE le natif reste sur place** ; il ne bouge que sur un
    gain STRICT. C'est ce que `noncomparable._base._sweep_origin_first` observait live (#76,
    deathRotbone RevitalizingMalignancy) — ce n'était pas une exception self-cast, c'est l'ordre
    d'énumération natif.

    Machine of War -> `[]` : `DefaultMachineTactic` passe `NullPosition()` + `new OrderedSet()`
    littéralement, sans jamais appeler `GenerateActionTiles` (cf. `build_machine`)."""
    tiles = [] if origin is None else [origin]
    tiles += [t for t in ((x["col"], x["row"]) for x in move_tiles) if t != origin]
    return tiles


def _ability_name(a: dict) -> str | None:
    """Nom d'ability tel que le consomme le PREDICTEUR offline (cle de l'entree gameconfig).

    `decisionView` nomme les abilities via `frida/hooks/data/ability-names.ts` — une map GENEREE,
    figee dans le bundle injecte : un id absent de cette map sort en placeholder `"id:<n>"`
    (`abilityName()` : `ACTIVE_ABILITY_NAMES[id] ?? \\`id:${id}\\``). Le predicteur cle sa recherche
    gameconfig sur ce NOM -> `make_damage_predictions` rend `[]`, l'ability n'est JAMAIS candidate,
    et le silence est total (ni erreur ni desaccord de degat).

    Repli sur l'enum du moteur (`ActiveAbilityType`, source independante) : elle porte le MEME nom
    que la cle gameconfig. Portee MESUREE (`probe_27_3_ability_names.py`, build gqfc5mff6c) : 8 ids
    sur 331 sont absents de la map des hooks (1215/1216/1217 npc-only, 1223/1224 MoW, 1220 sans
    entree gameconfig, 1228 et 1230 = heros hors catalogue de la seed BC) -> le repli est inerte
    partout ailleurs. Il rend confrontables les porteurs amenes par `catalog_inject.py`."""
    name = a.get("name")
    aid = a.get("id")
    if aid is None or (name and not str(name).startswith("id:")):
        return name
    try:
        return ActiveAbilityType(int(aid)).name
    except ValueError:
        return name


def _mow_slot_by_player(dv: dict) -> dict:
    """`{playerId: MachineComponent.Position}` depuis `decisionView.mows` — le REPLI du canal
    `MachineOfWarPosition` (cf. `AiDecisionContext.machine_of_war_position`).

    `projectMowsFull` emet `owner` = `ownerId` (un playerId, celui qui indexe `playerTeams`) et
    `slot` = `MachineComponent.Position @0x78` (`MachineOfWarPosition` : 1=Top, 2=Bottom). Ligne sans
    l'un des deux -> ECARTEE (jamais un slot invente) ; `mows` absent -> table VIDE."""
    return {m.get("owner"): m.get("slot") for m in (dv.get("mows") or [])
            if m.get("owner") is not None and m.get("slot") is not None}


def _machine_of_war_position(spawn_groups, current_player_team, mow_slot_by_player, cur,
                             mow_position_by_player=None):
    """La cascade de `AiDecisionContext.machine_of_war_position`, en fonction MODULE.

    Elle vit ici (et non seulement en methode) parce que la `Scene` la porte desormais aussi : la
    face PREDICTION (`make_damage_predictions`) ne recoit que la `Scene`, jamais l'
    `AiDecisionContext`, et l'arbre de zone de 1148 lit ce canal. Un seul foyer -> les deux
    consommateurs ne peuvent pas diverger.

    #302 tranche 5 -- le NATIF INVOQUE passe DEVANT le mirror. `mow_position_by_player` est le
    retour de `GetPositionMachineForPlayer(player)` lui-meme ; `spawn_groups` n'en est qu'une
    transcription, qui DEVINE en plus `playerNr = 0`. Un `cur` absent de la table mesuree ne
    court-circuite PAS la suite de la cascade : la table peut etre non vide et ne pas porter le
    joueur courant (elle n'enumere que les entites `EntityType.Player` du runner)."""
    if mow_position_by_player:
        pos = mow_position_by_player.get(cur)
        if pos is not None:
            return pos
    if spawn_groups is not None and current_player_team is not None:
        return machine_of_war_position_for_player(spawn_groups, int(current_player_team))
    return (mow_slot_by_player or {}).get(cur)


def _current_player_team(dv: dict):
    """`TeamComponent.<+0x24>` du joueur COURANT — l'entree de `GroupForPlayer(teamIndex, ...)`.

    `decisionView.units[].ctrl` est `IsControlledByCurrentPlayer` (invoque natif, cf.
    `projectUnitsFull`) : l'equipe d'une unite controlee EST celle du joueur courant. On prend la
    premiere ; `None` si aucune unite controlee n'est projetee (le predicat retombe alors sur
    l'ignorance assumee, jamais sur une equipe devinee).

    #359-r6 -- ADAPTATEUR DE SUBSTRAT, plus une re-ecriture de la regle : celle-ci vit desormais
    dans `engine/services/current_player.py`, que `engine/playbook/prediction/abilities.py` partage.
    Ce site ne garde que ce qui lui est propre : l'ORDRE de balayage (`units` puis `mows`) et le nom
    sous lequel trois probes l'importent."""
    return _cp.current_player_team(dv.get("units"), dv.get("mows"))


def build(rpc: Callable[..., dict], rid: int, dv: dict, mov_by_unit: dict, uid: int,
          wt: Any, predictor: dict | None, debug: bool = False,
          spawn_groups=None) -> AiDecisionContext:
    """Une passe RPC -> `AiDecisionContext`. Reproduit exactement la tête de l'ancien `engine_decide`
    (mêmes appels `observeBattle`/`tileMeta`/`pathDistToEnemies`, mêmes dérivations).

    #443-r2-b1 — `dv` accepte les DEUX canaux de `readEffectsByUnit`, et l'appelant DOIT le capter
    par `runner/snapshot.py::decision_view_seed_body` (canal `includeInactive`) : c'est le seul qui
    publie les effets POSÉS mais INERTES, que les mirrors d'un `HasEffect(..., onlyActive = 0)`
    DOIVENT voir. Ce que le canal ajoute n'atteint QUE le canal STRUCTURÉ (`sctx["eff_state"]`,
    porteur du flag par instance) : `ctx.units` / `ctx.me` sont projetés ACTIF-ONLY ci-dessous, donc
    les lecteurs de la liste BRUTE gardent EXACTEMENT leur verdict d'avant la bascule."""
    units = active_only_rows(dv.get("units"))
    cur = dv.get("currentPlayer")
    plans = {p.get("unitId"): p for p in (dv.get("attackPlans") or [])}
    enemies = _enemies(units)
    epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies]
    me = next((u for u in units if u.get("id") == uid), None)
    hp_cur_by_id = {u.get("id"): u.get("hp") for u in units}
    ab_name_by_id = {x.get("id"): _ability_name(x)
                     for x in ((me or {}).get("abilities") or [])}
    normal_ids = {a.get("id") for a in ((me or {}).get("abilities") or [])
                  if a.get("kind") == "normal"}
    # Gate d'usabilite `IdunBattle.Core.Services.AttackQuery$$CanUseAbility` (stun/taunt -> effets
    # `*_CantUseAbility`) : les actives/granted bloquees ne doivent JAMAIS atteindre les
    # generateurs (le natif ne genere pas d'action pour elles ; l'attaque normale passe).
    # Filtre au POINT DE COUTURE unique (tous les generateurs lisent ctx.me["abilities"]).
    # Vecu #45 777 s15 : u83 stunne (1165) -> le natif joue 69->87 (2.88) faute de mieux,
    # nous emettions Repair 28 self (30.06) -> miss "utility-logic" fantome.
    if me is not None:
        kept = [a for a in (me.get("abilities") or [])
                if battle_query.can_use_ability(me, a)
                and battle_query.can_currently_be_used(a)]
        if len(kept) != len(me.get("abilities") or []):
            me = {**me, "abilities": kept}

    # maxHP par cible (combinedMax du composite Damage) — observeBattle 1×/décision (réutilisé heal).
    obs = rpc("observeBattle", {"runnerId": rid}, 40)
    obs_units = obs.get("units") or []
    hpmax_by_id = {u.get("squadId"): (u.get("hpMax") or 0) for u in obs_units}
    # #45b' : overlay MaxHealth EFFECTIF (combatSnapshot.healthMax = GetStat(e,5,part=2), la
    # lecture EXACTE de DamageUtility IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext) — obs.hpMax est la BASE (struct @0x14) et
    # rate les bumps mid-bataille (TwistedScience +2992 sur u87, 777 s15 : natif 2.8836
    # reconstruit exact avec 14036, faux 2.3755 avec 11044). Vieux hooks -> overlay vide.
    if predictor is not None:
        hpmax_by_id.update(predictor.get("hpmax_eff_by_id") or {})

    # État courant du pas pour le prédicteur OFFLINE (hp/pos/team/effets seed).
    sctx = _step_context(predictor, dv) if predictor is not None else None
    if sctx is not None:
        sctx["hpmax_by_id"] = hpmax_by_id   # coût PV des abilities (GetHealthToLose)

    # Métadonnées de tuile (Tile(7)) + distance-CHEMIN (MinDist fidèle).
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    tiles = tm.get("tiles") or []
    elev_by_pos = {(t.get("col"), t.get("row")): t.get("elevation") for t in tiles}
    is_temporary_by_pos = {(t.get("col"), t.get("row")): bool(t.get("isTemporary")) for t in tiles}
    effects_by_pos = {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                      for t in tiles}
    is_territory_by_pos, tile_effect_type_ids_by_pos = _tile_attribute_maps(tiles)
    pdr = rpc("pathDistToEnemies", {"runnerId": rid, "unitId": uid}, 90)
    pathdist_by_pos = {(t.get("col"), t.get("row")): t.get("pathDist") for t in (pdr.get("tiles") or [])}
    # #26 — ennemis CIBLABLES retenus par le RPC (miroir natif COMPLET des filtres `FindClosestEnemy`
    # IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext : Environment / IsTargetable / IsIrrelevantObject / IsDead / GetOnlyTargets) : seed
    # du fallback HEX de MinDist(16) quand pathDist=-1. Fallback epos (complet) si RPC KO.
    _pdr_enemies = pdr.get("enemies")
    tgt_epos = ([(e.get("col"), e.get("row")) for e in _pdr_enemies]
                if _pdr_enemies else epos)
    # {(col,row): tileEntityId} — board STATIQUE (caché par rid). Cible native d'une self-cast AoE
    # = MainTile-id du caster (mesuré CombatRestoratives : tgt=22 = id de la tuile du caster).
    tile_id_by_pos = _board_tile_ids(rpc, rid)
    neigh_by_pos = _board_neighbours(rpc, rid)   # voisins ordre natif -> cible exacte Gauntlets (#117)
    walkable_by_pos = _board_walkable(rpc, rid)  # gate statique de placement CanAddUnit (#116)
    terrain_by_pos = _board_terrain(rpc, rid)    # terrain statique -> covers TileEffects (DryBush->LightCover, case-37)
    is_wall_by_pos = _board_is_wall(rpc, rid)    # TileComponent+0x41 -> volet MURS de la ligne de vue (#433-r4-r2-r1-r2)
    is_in_fog_by_pos = _board_is_in_fog(rpc, rid)  # TileComponent+0x40 -> 2e volet d'IsWalkable (#433-r4-r2-r1-r2-r2-r1)

    origin = (me["pos"]["col"], me["pos"]["row"]) if me and me.get("pos") else None
    move_tiles = (mov_by_unit.get(uid) or {}).get("tiles") or []
    fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("ctrl") and u.get("alive") and u.get("pos") and u.get("id") != uid]
    # `tiles` du tactic natif — ORIGINE EN TÊTE puis les tuiles de move
    # (`ABaseAiUnitTactic$$GenerateActionTiles` -> `IBattleQuery`+0xe =
    # `BattleQuery$$GetCurrentAndMovablePositionsFor`, cf. `action_tiles_for`). C'est cet ORDRE que
    # TOUS les sweeps de position consomment : `Bucket$$AddAction` est keep-first (`>` strict), donc
    # à utilité ÉGALE le natif reste sur place.
    action_tiles = action_tiles_for(origin, move_tiles)
    # `reach_nc` = LE MÊME objet natif (`tiles`), sous son nom historique côté NonComparable. Il était
    # construit origine-LAST au motif que « l'ordre brut du générateur » plaçait la `NullPosition` en
    # dernier — motif RÉFUTÉ par le décompilé (le slot +0xe est `GetCurrentAndMovablePositionsFor`,
    # dont l'`OrderedSet` est SEEDÉ avec la position courante) et par la mesure (31337/C3_01 step 11 :
    # Stormcaller, utilité position-INDÉPENDANTE, natif sur place en (2,3), port -> (2,4) = 1re tuile
    # de move). `_sweep_origin_first` (#76) devient l'IDENTITÉ : ce n'était pas une exception self-cast,
    # c'était déjà l'ordre natif.
    reach_nc = action_tiles

    mow_slot_by_player = _mow_slot_by_player(dv)
    current_player_team = _current_player_team(dv)
    mow_position_by_player = _board_mow_positions(rpc, rid)   # #302-5 — gratuit (boardGraph déjà fetché)

    # Scene objet = predictor + sctx consolidés (+ élévation + effets de tuile FRAIS du pas — la glace
    # LordOfTempests s'accumule en bataille) — consommée par engine.playbook.prediction.
    # `machine_of_war_position` : MEME cascade que `AiDecisionContext.machine_of_war_position` (foyer
    # unique `_machine_of_war_position`) — la face PREDICTION ne voit que la Scene.
    scene = (Scene.from_predictor_sctx(
        predictor, sctx, elev_by_pos, tile_effects_by_pos=effects_by_pos,
        machine_of_war_position=_machine_of_war_position(spawn_groups, current_player_team,
                                                         mow_slot_by_player, cur,
                                                         mow_position_by_player))
             if (predictor is not None and sctx is not None) else None)

    # #236 — `UtilityMovementCase` de la feuille MinDist(16), face LIVE (cf. `_mindist_case`).
    mindist_case = _mindist_case(uid, me, units, scene, pdr)

    return AiDecisionContext(
        rpc=rpc, rid=rid, wt=wt, predictor=predictor, sctx=sctx, scene=scene,
        uid=uid, me=me, units=units, cur=cur, plans=plans,
        enemies=enemies, epos=epos, tgt_epos=tgt_epos, fpos=fpos, origin=origin,
        move_tiles=move_tiles, reach_nc=reach_nc, action_tiles=action_tiles,
        hp_cur_by_id=hp_cur_by_id, hpmax_by_id=hpmax_by_id, obs_units=obs_units,
        ab_name_by_id=ab_name_by_id, normal_ids=normal_ids,
        elev_by_pos=elev_by_pos, is_temporary_by_pos=is_temporary_by_pos,
        effects_by_pos=effects_by_pos, pathdist_by_pos=pathdist_by_pos,
        mindist_case=mindist_case,
        tile_id_by_pos=tile_id_by_pos, neigh_by_pos=neigh_by_pos,
        walkable_by_pos=walkable_by_pos, terrain_by_pos=terrain_by_pos,
        is_wall_by_pos=is_wall_by_pos, is_in_fog_by_pos=is_in_fog_by_pos,
        is_territory_by_pos=is_territory_by_pos,
        tile_effect_type_ids_by_pos=tile_effect_type_ids_by_pos,
        mow_slot_by_player=mow_slot_by_player, current_player_team=current_player_team,
        mow_position_by_player=mow_position_by_player,
        spawn_groups=spawn_groups, debug=debug)


def _mindist_case(uid, me, units, scene, pdr: dict):
    """`UtilityMovementCase` de la feuille MinDistanceToClosestEnemy(17) — face LIVE (#236).

    Le generateur natif `<GenerateActions>IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext`
    construit ce case avec `ClosestEnemy = FindClosestEnemy(unit, posCourante)`. Le RPC
    `pathDistToEnemies` REJOUE ce meme `FindClosestEnemy` (memes predicats natifs, meme
    `GetPath(type=1)`) mais n'expose que `closestResolved` + la LISTE `enemies` des candidats
    retenus, pas l'ID retenu -> l'identite du ClosestEnemy n'est pas toujours decidable ici.

    Ce qui EST decidable, et suffit :
      * `noTargetableEnemies` vrai -> le set de candidats du RPC est VIDE apres les predicats
        natifs, c'est EXACTEMENT `ClosestEnemy == null`, donc le GATE 3 (mesure : roster adverse
        100 % `TeleportStrike`, les cinq portent `TeleportStrike_TeleportingIn` donc `IsTargetable`
        faux, cf. `probe_236_mindist_gates.py`). Toute AUTRE erreur (`Pathfinders` non resolu,
        runner/state nul, unite introuvable) est une indisponibilite du PORT : aucun case, les
        gates restent hors-jeu ;
      * `closestResolved` faux (0 candidat, ou aucun joignable depuis la tuile courante) ->
        `ClosestEnemy == null`, c'est le GATE 3, exact ;
      * `closestEnemyId` servi -> l'identite EST connue, gate 4 exact quelle que soit la
        composition du set ;
      * a defaut, un seul candidat -> son identite EST le ClosestEnemy, gate 4 exact ;
      * a defaut, plusieurs candidats -> le gate 4 ne lit du ClosestEnemy QUE `HasTrait(Impervious)` :
        si les candidats sont UNANIMES sur ce trait, le verdict est le meme quel que soit l'argmin,
        donc exact sans connaitre l'argmin. Sinon (candidats PANACHES) le substrat est laisse a
        `None` et le gate 4 est SUSPENDU — jamais devine."""
    if not pdr:
        return None
    # GATE 3 -- voie STRUCTUREE et UNIQUE : le champ `noTargetableEnemies` pose par le hook dans sa
    # sortie `if (!cands.length)` (`frida/hooks/features/ai-step/rpc-board.ts`). Le littéral
    # d'erreur du meme `return` n'est PLUS une donnee : un message est un canal fragile, et le lire
    # comme une mesure est exactement le patron « un echec rendu se lit comme une mesure ». Il ne
    # sert plus qu'a DETECTER un bundle Frida anterieur au champ -- cas ou le port ne peut pas
    # savoir si le gate mord, et ou le silence serait une regression PERMISSIVE invisible
    # (terme de distance attribue la ou le natif rend 0). On LEVE donc, on ne devine pas.
    _no_targetable = False
    if not pdr.get("ok"):
        if pdr.get("noTargetableEnemies") is True:
            _no_targetable = True
        elif pdr.get("error") == "aucun ennemi vivant":
            raise RuntimeError(
                "pathDistToEnemies rend le litteral 'aucun ennemi vivant' SANS le champ "
                "`noTargetableEnemies` : le bundle Frida injecte est anterieur a ce champ. Le "
                "gate 3 de MinDist(16) serait silencieusement inactif -> rebuild + reinject "
                "requis (#236). Aucun UtilityMovementCase n'est devine.")
        else:
            return None
    vis_by_id = {u.get("id"): u.get("visualId") for u in (units or [])}
    _ctx_of = (lambda i: scene.ctx(i)) if scene is not None else (lambda i: None)
    _traits = lambda i: entity_trait_names(_ctx_of(i), vis_by_id.get(i))   # noqa: E731
    me_ctx = _ctx_of(uid)
    # `GetStat(unit, 9)` du gate 4. Sans `Scene`, la stat n'est PAS lisible -> None = gate suspendu
    # (et non 0, qui FERAIT mordre le gate sur une donnee jamais lue).
    crit = getattr(me_ctx, "crit_chance", None) if me_ctx is not None else None
    unit_traits = entity_trait_names(me_ctx, (me or {}).get("visualId"))

    cands = [] if _no_targetable else [e.get("id") for e in (pdr.get("enemies") or [])]
    if not pdr.get("closestResolved") or not cands:
        return UtilityMovementCase(unit=uid, unit_traits=unit_traits, unit_crit_chance=crit,
                                   closest_enemy=None, closest_enemy_traits=None)
    # `closestEnemyId` = l'argmin que le RPC a REELLEMENT retenu (meme selection que
    # `MovementActionGenerator.<FindClosestEnemy>d__8$$MoveNext`, keep-first a egalite). Servi ->
    # l'identite du ClosestEnemy est connue, plus aucune ambiguite a lever.
    ce_id = pdr.get("closestEnemyId")
    if ce_id is not None:
        return UtilityMovementCase(unit=uid, unit_traits=unit_traits, unit_crit_chance=crit,
                                   closest_enemy=ce_id, closest_enemy_traits=_traits(ce_id))
    if len(cands) == 1:
        ce_traits = _traits(cands[0])
    else:
        _imp = [has_trait(_traits(i), UnitTrait.Impervious) for i in cands]
        ce_traits = ((UnitTrait.Impervious.name,) if all(_imp)
                     else (() if not any(_imp) else None))
    return UtilityMovementCase(unit=uid, unit_traits=unit_traits, unit_crit_chance=crit,
                               closest_enemy=cands[0] if len(cands) == 1 else True,
                               closest_enemy_traits=ce_traits)


def machine_row(dv: dict, uid: int) -> dict | None:
    """La ligne `decisionView.mows` du caster `uid` (`casterId` == `machineId`, l'entité
    `EntityType.Machine`). None si `uid` n'est pas une MACHINE OF WAR — c'est le DISCRIMINANT de
    routage vers `DefaultMachineTactic` (mirror `IdunBattle.Entities.EntityExtensions$$IsMachine`,
    testé par `IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit`). Le canal `.mows` est
    SÉPARÉ de `.units` côté natif : une Machine n'est jamais dans `decisionView.units`."""
    return next((m for m in (dv.get("mows") or []) if m.get("casterId") == uid), None)


def build_machine(rpc: Callable[..., dict], rid: int, dv: dict, uid: int,
                  wt: Any, predictor: dict | None, debug: bool = False,
                  spawn_groups=None) -> AiDecisionContext:
    """`AiDecisionContext` d'un caster MACHINE OF WAR — mirror de
    `IdunBattle.AI.Tactics.DefaultMachineTactic.<CalculateNextActionForUnit>d__5$$MoveNext`.

    Ce qu'il fait DE MOINS que `build`, et pourquoi (tout est lu au décompilé) :

    - **`origin = None`, `move_tiles = []`, `reach_nc = []`** — le tactic Machine appelle
      `gen.GenerateActions(machine, UnitPosition.NullPosition(), new OrderedSet())` : la position du
      caster est la position NULLE et l'ensemble des tuiles candidates est VIDE (là où le tactic unité
      passe `GetUnitPosition(unit)` et `ABaseAiUnitTactic$$GenerateActionTiles`). On n'INVENTE donc
      aucune tuile pour la MoW : elle n'a pas de `PositionComponent` (mesuré `dumpEntityComponents`).
    - **`plans = {}`** — `decisionView.attackPlans` est une projection des plans d'attaque
      POSITIONNELS ; sans tuile candidate il n'y a rien à ranker. Côté natif, la branche
      `positions.Count == 0` de `ActiveAbilityActionGenerator.<GenerateActions>d__7` fait UNE
      évaluation depuis `NullPosition()` — c'est aux playbooks (feuilles NonComparable) de produire la
      cible, pas au sweep de tuiles.
    - **pas d'appel `pathDistToEnemies`** — ce champ ne sert qu'au `MovementActionGenerator`, que
      `DefaultMachineTactic$$.ctor` n'ajoute PAS (et `<CalculateMovementForUnit>d__8$$MoveNext` rend
      une liste vide, toujours). `pathdist_by_pos = {}`.
    - **`normal_ids = set()`** — une MACHINE n'a JAMAIS d'attaque normale, et c'est structurel :
      `IdunBattle.Entities.Factories.MachineFactory$$Build` n'appelle **jamais**
      `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` (il appelle
      `UnitFactory$$InitBaseComponent`, `MachineFactory$$AddConfiguredAbilities` et
      `UnitFactory$$AddDerivedAbilities`, et c'est tout). Mécanique : `AddNormalAttackAbility` n'a
      qu'UN SEUL xref de code, `UnitFactory$$Build`. Aucune configuration ne peut donc en donner une
      à une Machine.
      ⚠ La raison écrite ici jusqu'à #419-r1-tr14-r5-r2 était « les 8 MoW du pool ont `weapons=[]`
      en gameconfig » — une dérivation du KIT, c.-à-d. exactement le critère que #551 a réfuté sur
      la voie passive. Elle donnait la bonne valeur pour la mauvaise raison, et se serait lue comme
      périmée le jour où une MoW recevrait une arme au catalogue. CONFRONTÉ, contre-bras compris :
      écrire `BC.Units[<MoW>].ActiveAbilities = [PoundThemToDust]` — la clé de la voie active du
      dispatch — ne lui donne toujours AUCUNE ability `kind == "normal"`
      (`probe_419r1tr14r5r2_active_normal_attack.py --volet mow`).

    Le reste (observeBattle / tileMeta / boardGraph / Scene) est la MÊME couture que `build` : ce sont
    des lectures d'ENVIRONNEMENT, indépendantes du caster."""
    # `.units` ne contient JAMAIS de Machine (canal séparé). Projection ACTIF-ONLY : cf. `build`
    # (#443-r2-b1) — la liste BRUTE reste indépendante du canal de capture, seul `sctx["eff_state"]`
    # (structuré, porteur du flag) voit ce que `includeInactive` ajoute.
    units = active_only_rows(dv.get("units"))
    cur = dv.get("currentPlayer")
    me = machine_row(dv, uid)
    if me is None:
        raise ValueError(f"build_machine: {uid} absent de decisionView.mows")
    me = active_only_rows([me])[0]          # la MoW aussi : `can_use_ability` lit `me["effects"]`
    # `ctrl` recalculé PAR RAPPORT AU CAMP DE LA MACHINE (et non au joueur courant) : c'est le camp
    # de l'acteur qui définit ami/ennemi pour ses sélecteurs (`Owner@0x148`).
    my_team = me.get("team")
    units = [{**u, "ctrl": (u.get("team") == my_team)} for u in units]
    enemies = _enemies(units)
    epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies]
    hp_cur_by_id = {u.get("id"): u.get("hp") for u in units}
    # Gate par ability du générateur natif : `CanUseAbility` (stun/taunt) ET la composite
    # `ActiveAbility$$get_CanCurrentlyBeUsed` (cooldown + MUNITIONS). Sans le terme munitions, le
    # port proposerait une ability que le natif refuse (mesuré : `1187 hasAmmo:false`).
    kept = [a for a in (me.get("abilities") or [])
            if battle_query.can_use_ability(me, a) and battle_query.can_currently_be_used(a)]
    me = {**me, "abilities": kept}
    ab_name_by_id = {x.get("id"): _ability_name(x) for x in kept}

    obs = rpc("observeBattle", {"runnerId": rid}, 40)
    obs_units = obs.get("units") or []
    hpmax_by_id = {u.get("squadId"): (u.get("hpMax") or 0) for u in obs_units}
    if predictor is not None:
        hpmax_by_id.update(predictor.get("hpmax_eff_by_id") or {})

    sctx = _step_context(predictor, dv) if predictor is not None else None
    if sctx is not None:
        sctx["hpmax_by_id"] = hpmax_by_id

    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    tiles = tm.get("tiles") or []
    elev_by_pos = {(t.get("col"), t.get("row")): t.get("elevation") for t in tiles}
    is_temporary_by_pos = {(t.get("col"), t.get("row")): bool(t.get("isTemporary")) for t in tiles}
    effects_by_pos = {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                      for t in tiles}
    is_territory_by_pos, tile_effect_type_ids_by_pos = _tile_attribute_maps(tiles)
    tile_id_by_pos = _board_tile_ids(rpc, rid)
    neigh_by_pos = _board_neighbours(rpc, rid)
    walkable_by_pos = _board_walkable(rpc, rid)
    terrain_by_pos = _board_terrain(rpc, rid)
    is_wall_by_pos = _board_is_wall(rpc, rid)
    is_in_fog_by_pos = _board_is_in_fog(rpc, rid)

    fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("ctrl") and u.get("alive") and u.get("pos") and u.get("id") != uid]
    mow_slot_by_player = _mow_slot_by_player(dv)
    current_player_team = _current_player_team(dv)
    mow_position_by_player = _board_mow_positions(rpc, rid)   # #302-5 — gratuit (boardGraph déjà fetché)
    scene = (Scene.from_predictor_sctx(
        predictor, sctx, elev_by_pos, tile_effects_by_pos=effects_by_pos,
        machine_of_war_position=_machine_of_war_position(spawn_groups, current_player_team,
                                                         mow_slot_by_player, cur,
                                                         mow_position_by_player))
             if (predictor is not None and sctx is not None) else None)

    return AiDecisionContext(
        rpc=rpc, rid=rid, wt=wt, predictor=predictor, sctx=sctx, scene=scene,
        uid=uid, me=me, units=units, cur=cur, plans={},
        enemies=enemies, epos=epos, tgt_epos=epos, fpos=fpos, origin=None,
        move_tiles=[], reach_nc=[], action_tiles=[],   # `NullPosition` + `new OrderedSet()` (cf. docstring)
        hp_cur_by_id=hp_cur_by_id, hpmax_by_id=hpmax_by_id, obs_units=obs_units,
        ab_name_by_id=ab_name_by_id, normal_ids=set(),
        elev_by_pos=elev_by_pos, is_temporary_by_pos=is_temporary_by_pos,
        effects_by_pos=effects_by_pos, pathdist_by_pos={},
        tile_id_by_pos=tile_id_by_pos, neigh_by_pos=neigh_by_pos,
        walkable_by_pos=walkable_by_pos, terrain_by_pos=terrain_by_pos,
        is_wall_by_pos=is_wall_by_pos, is_in_fog_by_pos=is_in_fog_by_pos,
        is_territory_by_pos=is_territory_by_pos,
        tile_effect_type_ids_by_pos=tile_effect_type_ids_by_pos,
        mow_slot_by_player=mow_slot_by_player,
        current_player_team=current_player_team,
        mow_position_by_player=mow_position_by_player,
        spawn_groups=spawn_groups, debug=debug)
