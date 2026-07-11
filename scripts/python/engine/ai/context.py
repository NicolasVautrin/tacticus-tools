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
    epos: list                        # positions ennemies (GetAdjacentEnemies)
    fpos: list                        # positions alliées, self exclu (GetAdjacentFriends)
    origin: tuple | None              # (col,row) de l'unité active
    move_tiles: list                  # tuiles de mouvement atteignables (aiMovableTiles[uid])
    reach_nc: list                    # origine + tuiles de move = positions candidates du caster

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
_ACTIVE_LEVEL_CACHE: dict = {}     # {rid: {unitId: {active,passive,multiplier}}} — combatSnapshot, 1 fetch/rid


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


def _enemies(units: list) -> list:
    """Unités adverses vivantes positionnées (ctrl=False => adverse)."""
    return [u for u in units if not u.get("ctrl") and u.get("alive") and u.get("pos")]


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

    # maxHP par cible (combinedMax du composite Damage) — observeBattle 1×/décision (réutilisé heal).
    obs = rpc("observeBattle", {"runnerId": rid}, 40)
    obs_units = obs.get("units") or []
    hpmax_by_id = {u.get("squadId"): (u.get("hpMax") or 0) for u in obs_units}

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
    pdr = rpc("pathDistToEnemies", {"runnerId": rid, "unitId": uid}, 90)
    pathdist_by_pos = {(t.get("col"), t.get("row")): t.get("pathDist") for t in (pdr.get("tiles") or [])}
    # {(col,row): tileEntityId} — board STATIQUE (caché par rid). Cible native d'une self-cast AoE
    # = MainTile-id du caster (mesuré CombatRestoratives : tgt=22 = id de la tuile du caster).
    tile_id_by_pos = _board_tile_ids(rpc, rid)
    neigh_by_pos = _board_neighbours(rpc, rid)   # voisins ordre natif -> cible exacte Gauntlets (#117)
    walkable_by_pos = _board_walkable(rpc, rid)  # gate statique de placement CanAddUnit (#116)

    origin = (me["pos"]["col"], me["pos"]["row"]) if me and me.get("pos") else None
    move_tiles = (mov_by_unit.get(uid) or {}).get("tiles") or []
    fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("ctrl") and u.get("alive") and u.get("pos") and u.get("id") != uid]
    # reach_nc = tuiles de MOVE puis ORIGINE (`NullPosition`) EN DERNIER : ORDRE BRUT du generateur
    # `<GenerateActions>d__7 @18119a3f0` (`Bucket.AddAction` keep-first `>`). NUANCE #76/#80 : le tie-break
    # depend de `HasValidTargets(0x3f)` PAR tuile de move. SELF-cast (heals, NovaBoost) : self-cible
    # position-independante -> le generateur gate les tuiles de move -> le natif RESTE EN PLACE au tie
    # (CONFIRME LIVE #76) -> ces playbooks balaient `_sweep_origin_first` (origine d'abord), PAS cet ordre brut.
    # TILE/other-target (NovaShield) : tuiles de move non gatees -> le natif BOUGE au tie -> sweep origine-LAST
    # (cet ordre brut). Donc `reach_nc` reste origine-LAST ; les self-cast le reordonnent localement.
    reach_nc = [(t["col"], t["row"]) for t in move_tiles] + ([origin] if origin is not None else [])

    # Scene objet = predictor + sctx consolidés (+ élévation) — consommée par engine.playbook.prediction.
    scene = (Scene.from_predictor_sctx(predictor, sctx, elev_by_pos)
             if (predictor is not None and sctx is not None) else None)

    return AiDecisionContext(
        rpc=rpc, rid=rid, wt=wt, predictor=predictor, sctx=sctx, scene=scene,
        uid=uid, me=me, units=units, cur=cur, plans=plans,
        enemies=enemies, epos=epos, fpos=fpos, origin=origin,
        move_tiles=move_tiles, reach_nc=reach_nc,
        hp_cur_by_id=hp_cur_by_id, hpmax_by_id=hpmax_by_id, obs_units=obs_units,
        ab_name_by_id=ab_name_by_id, normal_ids=normal_ids,
        elev_by_pos=elev_by_pos, is_temporary_by_pos=is_temporary_by_pos,
        effects_by_pos=effects_by_pos, pathdist_by_pos=pathdist_by_pos,
        tile_id_by_pos=tile_id_by_pos, neigh_by_pos=neigh_by_pos,
        walkable_by_pos=walkable_by_pos, debug=debug)
