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
from engine.playbook.scene import Scene, step_context as _step_context  # état objet + seam live-feed


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
    #                                   le terrain sommés par TileEffects(9) Loop2 (DryBush->LightCover, case-37)
    # Deux attributs de TUILE que `tileMeta` remonte DÉJÀ et que le port jetait (#175) : sans eux les
    # feuilles Tile(7) qui les gatent restent muettes même quand `ctx.unit_traits` est peuplé.
    is_territory_by_pos: dict = field(default_factory=dict)
    #     {(col,row): bool} <- tileMeta.isTerritory = `TileComponent+0x2e`, l'octet que lit
    #     `IdunBattle.Entities.TileExtensions$$IsTerritoryTile` -> feuille CapturePoint(24) (+/-300)
    tile_effect_type_ids_by_pos: dict = field(default_factory=dict)
    #     {(col,row): [EffectType]} <- tileMeta.effects[].effectType = `EffectComponent+0x58` ->
    #     feuilles DespoiledGround(28, 0x5c4), Contaminated(25, 0x4dc), MoltenForm(23, 5/10)

    debug: bool = False

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
            # et rend `{"units": []}` pour tout le reste. On ne l'appelle pas -> l'appelant retombe
            # sur le gameconfig. C'est le residu N13-b (kit declenche offline sans traits/reliques).
            return []
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


_BOARD_GRAPH_CACHE: dict = {}      # {rid: tiles list} — boardGraph brut, 1 fetch/rid (partagé)
_BOARD_TILE_IDS_CACHE: dict = {}   # {rid: {(col,row): tileEntityId}} — board statique, dérivé
_BOARD_NEIGH_CACHE: dict = {}      # {rid: {(col,row): [voisins ordre natif]}} — dérivé
_BOARD_WALKABLE_CACHE: dict = {}   # {rid: {(col,row): walkable}} — board statique, dérivé (#116)
_BOARD_TERRAIN_CACHE: dict = {}    # {rid: {(col,row): tileDefId}} — terrain statique, dérivé (case-37)
_ACTIVE_LEVEL_CACHE: dict = {}     # {rid: {unitId: {active,passive,multiplier}}} — combatSnapshot, 1 fetch/rid
_TRIGGERED_KIT_CACHE: dict = {}    # {(rid, unitId): [TriggeredAbilityType]} — unitAbilityStates, 1 fetch/unite
#                                    (kit DECLENCHE reel : passifs + trait-granted + RELIQUES, cf. N13)


def _board_graph_tiles(rpc: Callable[..., dict], rid: int) -> list:
    """Liste brute des tuiles `boardGraph` (board STATIQUE -> caché par rid ; 1 fetch partagé entre
    `_board_tile_ids` et `_board_neighbours`)."""
    t = _BOARD_GRAPH_CACHE.get(rid)
    if t is None:
        bg = rpc("boardGraph", {"runnerId": rid}, 60) or {}
        t = bg.get("tiles") or []
        _BOARD_GRAPH_CACHE[rid] = t
    return t


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
    TileEffects(9) via son Loop2 (DryBush->LightCover ; case-37). `tileMeta` ne porte pas le terrain."""
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


def _tile_attribute_maps(tiles: list) -> tuple:
    """`(is_territory_by_pos, tile_effect_type_ids_by_pos)` depuis les tuiles `tileMeta` (#175).

    `isTerritory` = `TileComponent+0x2e` (lu par `IdunBattle.Entities.TileExtensions$$IsTerritoryTile`)
    et `effects[].effectType` = `EffectComponent+0x58` (comparé à `0x5c4` par
    `IdunBattle.AI.Utilities.DespoiledGroundUtility.u003CEvaluateMovementInStepsu003Ed__5$$MoveNext`)
    étaient tous deux déjà remontés par le RPC et jetés par le port : `effects_by_pos` ne gardait que
    le NOM (clé de poids BC de la feuille TileEffects(9)), jamais le type."""
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


def build(rpc: Callable[..., dict], rid: int, dv: dict, mov_by_unit: dict, uid: int,
          wt: Any, predictor: dict | None, debug: bool = False) -> AiDecisionContext:
    """Une passe RPC -> `AiDecisionContext`. Reproduit exactement la tête de l'ancien `engine_decide`
    (mêmes appels `observeBattle`/`tileMeta`/`pathDistToEnemies`, mêmes dérivations)."""
    units = dv.get("units") or []
    cur = dv.get("currentPlayer")
    plans = {p.get("unitId"): p for p in (dv.get("attackPlans") or [])}
    enemies = _enemies(units)
    epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies]
    me = next((u for u in units if u.get("id") == uid), None)
    hp_cur_by_id = {u.get("id"): u.get("hp") for u in units}
    ab_name_by_id = {x.get("id"): x.get("name") for x in ((me or {}).get("abilities") or [])}
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

    # Scene objet = predictor + sctx consolidés (+ élévation + effets de tuile FRAIS du pas — la glace
    # LordOfTempests s'accumule en bataille) — consommée par engine.playbook.prediction.
    scene = (Scene.from_predictor_sctx(predictor, sctx, elev_by_pos,
                                       tile_effects_by_pos=effects_by_pos)
             if (predictor is not None and sctx is not None) else None)

    return AiDecisionContext(
        rpc=rpc, rid=rid, wt=wt, predictor=predictor, sctx=sctx, scene=scene,
        uid=uid, me=me, units=units, cur=cur, plans=plans,
        enemies=enemies, epos=epos, tgt_epos=tgt_epos, fpos=fpos, origin=origin,
        move_tiles=move_tiles, reach_nc=reach_nc, action_tiles=action_tiles,
        hp_cur_by_id=hp_cur_by_id, hpmax_by_id=hpmax_by_id, obs_units=obs_units,
        ab_name_by_id=ab_name_by_id, normal_ids=normal_ids,
        elev_by_pos=elev_by_pos, is_temporary_by_pos=is_temporary_by_pos,
        effects_by_pos=effects_by_pos, pathdist_by_pos=pathdist_by_pos,
        tile_id_by_pos=tile_id_by_pos, neigh_by_pos=neigh_by_pos,
        walkable_by_pos=walkable_by_pos, terrain_by_pos=terrain_by_pos,
        is_territory_by_pos=is_territory_by_pos,
        tile_effect_type_ids_by_pos=tile_effect_type_ids_by_pos, debug=debug)


def machine_row(dv: dict, uid: int) -> dict | None:
    """La ligne `decisionView.mows` du caster `uid` (`casterId` == `machineId`, l'entité
    `EntityType.Machine`). None si `uid` n'est pas une MACHINE OF WAR — c'est le DISCRIMINANT de
    routage vers `DefaultMachineTactic` (mirror `IdunBattle.Entities.EntityExtensions$$IsMachine`,
    testé par `IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit`). Le canal `.mows` est
    SÉPARÉ de `.units` côté natif : une Machine n'est jamais dans `decisionView.units`."""
    return next((m for m in (dv.get("mows") or []) if m.get("casterId") == uid), None)


def build_machine(rpc: Callable[..., dict], rid: int, dv: dict, uid: int,
                  wt: Any, predictor: dict | None, debug: bool = False) -> AiDecisionContext:
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
    - **`normal_ids = set()`** — les 8 MoW du pool ont `weapons=[]` en gameconfig : aucune attaque
      normale, donc aucune entrée `kind == "normal"`.

    Le reste (observeBattle / tileMeta / boardGraph / Scene) est la MÊME couture que `build` : ce sont
    des lectures d'ENVIRONNEMENT, indépendantes du caster."""
    units = dv.get("units") or []          # `.units` ne contient JAMAIS de Machine (canal séparé)
    cur = dv.get("currentPlayer")
    me = machine_row(dv, uid)
    if me is None:
        raise ValueError(f"build_machine: {uid} absent de decisionView.mows")
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
    ab_name_by_id = {x.get("id"): x.get("name") for x in kept}

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

    fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("ctrl") and u.get("alive") and u.get("pos") and u.get("id") != uid]
    scene = (Scene.from_predictor_sctx(predictor, sctx, elev_by_pos,
                                       tile_effects_by_pos=effects_by_pos)
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
        is_territory_by_pos=is_territory_by_pos,
        tile_effect_type_ids_by_pos=tile_effect_type_ids_by_pos, debug=debug)
