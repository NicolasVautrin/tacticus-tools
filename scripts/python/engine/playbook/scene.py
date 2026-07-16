"""Scene — l'état de bataille live consommé par la prédiction (la COUTURE oracle/moteur, forme objet).

Consolide en UN objet les deux sacs de dicts de l'ancien PV (`predictor` statique cold + `sctx` par-pas) :
tables par-unité (UnitContext, armure, bouclier, mult de rareté, niveau d'ability, faction) + état courant
(hp, position, équipe, effets matérialisés) + métadonnées de tuile (élévation). Les fonctions de prédiction
lisent la Scene (`scene.hp(id)`, `scene.effects(id)`, …) au lieu de deux dicts non typés — modèle objet propre.

`from_predictor_sctx` BRIDGE les dicts existants (le seam RPC `build_predictor`/`step_context`/`refresh_shields`
reste le fournisseur ; ré-logeable dans Scene.from_live plus tard sans changer le calcul)."""
from __future__ import annotations

from dataclasses import dataclass, field

import gameconfig as GC
from engine.entities import UnitContext, EffectsState


@dataclass
class Scene:
    """État live pour la prédiction. Tables par-id + état courant + élévation. Accès via méthodes."""

    ctx_by_id: dict            # {id: UnitContext} (stats/traits/arme normale, cold)
    armor_by_id: dict          # {id: fixedArmor} — DYNAMIQUE (debuffs), refresh par-pas
    shield_by_id: dict         # {id: totalShield} — DYNAMIQUE (accordé/consommé), refresh par-pas
    mult_by_id: dict           # {id: abilityVariablesMultiplier %} (rareté)
    ablvl_by_id: dict          # {id: passiveAbilityLevel}
    vis_by_id: dict            # {id: visualId}
    units: list                # decisionView.units (courant)
    hp_by_id: dict             # {id: hp courant}
    pos_by_id: dict            # {id: (col,row)}
    team_by_id: dict           # {id: team}
    eff_state: object          # EffectsState (effets matérialisés seed)
    hpmax_by_id: dict = field(default_factory=dict)   # {squadId: hpMax} (observeBattle)
    elev_by_pos: dict | None = None                    # {(col,row): elevation} (tileMeta)
    board: object | None = None                        # Board (voisins natifs, adjacence hex) — cf.
    #                                                    # engine.entities.pathfinding.board ; None → evenq
    # AbilityState PER-ABILITY (#100) : {uid: {abilityId: {"level","multiplier"}}} — capteur
    # combatSnapshot.abilityStates (entrée ActiveAbility._abilityState @0x4c). C'est le couple que
    # le natif passe au playbook et qui indexe les variables config (TryGetVariableArrayForLevel
    # @181577510) ; le canal global (mult_by_id/activeAbilityLevel) est un fallback.
    abstate_by_id: dict = field(default_factory=dict)
    # TotalAttacksMade PER-UNITE (#106) : {uid: totalAttacksMade} — capteur actorStats
    # (ActorStatisticsComponent +0x20). Indexe le buff MartialInspiration (+33%/tour). Defaut {}
    # -> count=0 (debut de bataille / from_state offline) si non capte.
    actorstats_by_id: dict = field(default_factory=dict)
    # Stat DEFENSE PER-UNITE (#194) : {uid: StatComponent(stat 3)} — mirror du DefenseComponent natif
    # (cctor @180f991c0) lu par `CalculateDefenderModifiersForPrediction @181003066` : ses modifications
    # (ex. tuile Thorns −50) deviennent des entrees %-list (negate=1 → +50 → ×1.5). DYNAMIQUE (la
    # modification suit l'occupation de tuile) → capture combatSnapshot (defense + statDelta.defense),
    # refresh par-pas via `refresh_shields`. Defaut {} → axe inerte (defense non modifiee partout).
    defstat_by_id: dict = field(default_factory=dict)

    @classmethod
    def from_state(cls, state) -> "Scene":
        """Construit la Scene DIRECTEMENT depuis un `State` runner (offline, SANS RPC/combatSnapshot).

        C'est la moitié « prédiction » du bridge `State -> AiDecisionContext` (#65) : le `StatsComponent.ctx`
        d'une unité EST le même `UnitContext` que `build_predictor` cache (via `from_snapshot`) ; `State.effects`
        EST l'`EffectsState` seed ; `State.board` fournit élévation + adjacence hex. Donc `predictor`/`sctx`
        deviennent inutiles (le spine de décision ne lit QUE `ctx.scene`). Armure/bouclier = valeurs LIVE des
        composants (plus fidèle que le cold `refresh_shields` par-pas). Inclut les corpses (comme dv.units) ;
        les tables per-unité ne couvrent que les entités à `StatsComponent`."""
        from ..runner.components import (StatsComponent, OwnerComponent, PositionComponent,
                                         HealthComponent, UnitComponent, ShieldComponent,
                                         EffectsOwnedComponent)
        ctx_by_id, armor_by_id, shield_by_id, mult_by_id, ablvl_by_id, vis_by_id = {}, {}, {}, {}, {}, {}
        hp_by_id, hpmax_by_id, pos_by_id, team_by_id = {}, {}, {}, {}
        units: list = []
        for eid, e in state.entities.items():
            uc = e.get_component(UnitComponent)
            sc = e.get_component(StatsComponent)
            oc = e.get_component(OwnerComponent)
            pc = e.get_component(PositionComponent)
            hc = e.get_component(HealthComponent)
            ec = e.get_component(EffectsOwnedComponent)
            shc = e.get_component(ShieldComponent)
            if uc is None:
                continue
            vis = uc.visual_id if uc else None
            pos = (pc.col, pc.row) if pc is not None else None
            if sc is not None:                                    # tables prédiction : entités à ctx
                ctx = sc.ctx
                ctx_by_id[eid] = ctx
                armor_by_id[eid] = int(ctx.fixed_armor)
                mult_by_id[eid] = int(ctx.ability_variables_multiplier or 100)
                ablvl_by_id[eid] = int(ctx.passive_ability_level or 0)
            shield_by_id[eid] = shc.get_total_shield() if shc is not None else 0
            vis_by_id[eid] = vis
            if hc is not None:
                hp_by_id[eid] = hc.hp
                hpmax_by_id[eid] = hc.hp_max
            if pos is not None:
                pos_by_id[eid] = pos
            if oc is not None:
                team_by_id[eid] = oc.team
            units.append({
                "id": eid, "visualId": vis, "alive": bool(uc.alive),
                "team": oc.team if oc is not None else None,
                "pos": {"col": pos[0], "row": pos[1]} if pos is not None else None,
                "hp": hc.hp if hc is not None else None,
                "effects": list(ec.effects) if ec is not None else [],  # noms bruts (EffectsOwnedComponent)
            })
        elev_by_pos = None
        board = state.board
        if board is not None:
            elev_by_pos = {(t.get("col"), t.get("row")): int(t.get("elevation") or 0)
                           for t in board.by_id.values()
                           if t.get("col") is not None and t.get("row") is not None}
        sc = cls(
            ctx_by_id=ctx_by_id, armor_by_id=armor_by_id, shield_by_id=shield_by_id,
            mult_by_id=mult_by_id, ablvl_by_id=ablvl_by_id, vis_by_id=vis_by_id,
            units=units, hp_by_id=hp_by_id, pos_by_id=pos_by_id, team_by_id=team_by_id,
            eff_state=getattr(state, "effects", None), hpmax_by_id=hpmax_by_id,
            elev_by_pos=elev_by_pos, board=board)
        sc._seed_battle_counters()   # #185 (units offline sans defeatedByMelee -> N=0, inerte)
        return sc

    @classmethod
    def from_predictor_sctx(cls, predictor: dict, sctx: dict, elev_by_pos: dict | None = None,
                            board: object | None = None) -> "Scene":
        """Bridge des dicts de l'ancien PV vers l'objet Scene (mêmes données, forme objet)."""
        sc = cls(
            ctx_by_id=predictor.get("ctx_by_id") or {}, armor_by_id=predictor.get("armor_by_id") or {},
            shield_by_id=predictor.get("shield_by_id") or {}, mult_by_id=predictor.get("mult_by_id") or {},
            ablvl_by_id=predictor.get("ablvl_by_id") or {}, vis_by_id=predictor.get("vis_by_id") or {},
            units=sctx.get("units") or [], hp_by_id=sctx.get("hp_by_id") or {},
            pos_by_id=sctx.get("pos_by_id") or {}, team_by_id=sctx.get("team_by_id") or {},
            eff_state=sctx.get("eff_state"), hpmax_by_id=sctx.get("hpmax_by_id") or {},
            elev_by_pos=elev_by_pos if elev_by_pos is not None else predictor.get("elev_by_pos"),
            board=board if board is not None else predictor.get("board"),
            abstate_by_id=predictor.get("abstate_by_id") or {},
            actorstats_by_id=predictor.get("actorstats_by_id") or {},
            defstat_by_id=predictor.get("defstat_by_id") or {})
        sc._seed_battle_counters()   # #185 BlessingsOfKhorne (melee-defeats -> effets N-scalés)
        return sc

    # ── Compteurs de bataille (#185) ───────────────────────────────────────────────────────────────
    def melee_defeats(self) -> int:
        """Compte de base de `GetMultiplierBasedOnDefeatedInMelee @180f34ea0` = `Count(NormalUnits(
        UnitsDefeatedByMeleeAttack(AllUnits)))` : unités NORMALES (kind-1 — `dv.units` = squads hors
        MoW par construction, `DSLFactory.NormalUnits @180df7770` = `Units(set, kind=1)`) MORTES
        tuées par une attaque de MÊLÉE. Flag = `UnitComponent.DefeatedByMeleeAttack @0x178` (écrit
        par `KillUnitOperation @180e76470`, capté #185 dans decisionView.units) ; `isDead` requis en
        mirror du sélecteur `IsValidUnit @180f00b40` (une unité RESSUSCITÉE ne compte plus). GLOBAL
        (les 2 camps, quel que soit le tueur). Units offline (`from_state`) sans le champ -> 0."""
        return sum(1 for u in (self.units or [])
                   if u.get("defeatedByMelee") and not u.get("alive"))

    def _seed_battle_counters(self) -> None:
        """Seed les effets dépendants d'un COMPTEUR DE BATAILLE : pousse `melee_defeats` (compte brut)
        sur chaque instance d'effet qui déclare l'attribut (BlessingsOfKhorneModifiersEffect #185 —
        duck-typing, pas d'import loki ici). Scene est reconstruite à chaque pas -> compte courant."""
        bu = getattr(self.eff_state, "by_unit", None) if self.eff_state is not None else None
        if not bu:
            return
        n = self.melee_defeats()
        for effs in bu.values():
            for e in effs:
                if hasattr(e, "melee_defeats"):
                    e.melee_defeats = n

    # ── Accesseurs (mirror des lectures dict de PV) ────────────────────────────────────────────────
    def ctx(self, uid):
        return self.ctx_by_id.get(uid)

    def hp(self, uid):
        return self.hp_by_id.get(uid)

    def pos(self, uid):
        return self.pos_by_id.get(uid)

    def team(self, uid):
        return self.team_by_id.get(uid)

    def armor(self, uid) -> int:
        return self.armor_by_id.get(uid, 0)

    def shield(self, uid) -> int:
        return self.shield_by_id.get(uid, 0)

    def mult(self, uid) -> int:
        return self.mult_by_id.get(uid, 100)

    def hpmax(self, uid):
        return self.hpmax_by_id.get(uid)

    def effects(self, uid) -> list:
        """Effets ACTIFS de l'unité (matérialisés, gate HP courant) — `EffectsState.active_effects`."""
        return self.eff_state.active_effects(uid, {"hp": self.hp_by_id.get(uid)})

    def faction(self, uid):
        c = self.ctx_by_id.get(uid)
        return c.faction if c is not None else None

    def ability_state(self, uid, ability_id) -> dict | None:
        """AbilityState PER-ABILITY {level, multiplier} (capteur #100) ; None si non capturé
        (offline `from_state`, ou entrée absente) → l'appelant retombe sur le canal global."""
        return (self.abstate_by_id.get(uid) or {}).get(ability_id)

    def defense_stat(self, uid):
        """`StatComponent` DEFENSE (stat 3) de l'unité — mirror du DefenseComponent natif consommé
        par la face défenseur de `CalculateModifiersFromStatModifications @181004380` (#194).
        None si non capturé (from_state offline sans suivi defense, ou unité absente) → axe inerte."""
        return self.defstat_by_id.get(uid)

    def total_attacks_made(self, uid) -> int:
        """`ActorStatisticsComponent.TotalAttacksMade` (+0x20, capteur actorStats) — nb d'attaques
        de l'unité CETTE BATAILLE. Indexe le buff MartialInspiration (+33%/tour, #106). 0 si non
        capté (from_state offline / début de bataille)."""
        return int((self.actorstats_by_id or {}).get(uid, 0) or 0)


# ── SEAM live-feed (RPC) — tables cold + état par-pas. `rpc(method, body, timeout) -> result dict`. ──
def build_predictor(rpc, rid):
    """Tables STATIQUES (cold, 1×/runner) : `combatSnapshot` (dégât d'arme + stats + unitConfig
    mult/level + boucliers) + `decisionView` (visualId). None si combatSnapshot KO. (Ex-`PV.build_predictor`.)"""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not snap.get("ok"):
        return None
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    vis_by_id = {u["id"]: u.get("visualId") for u in (dv0.get("units") or [])}
    ctx_by_id, armor_by_id, mult_by_id, ablvl_by_id, shield_by_id = {}, {}, {}, {}, {}
    abstate_by_id = {}
    for u in (snap.get("units") or []):
        eid = u["entityId"]
        u["visualId"] = vis_by_id.get(eid)
        armor_by_id[eid] = int((u.get("stats") or {}).get("fixedArmor") or 0)
        shield_by_id[eid] = sum(int(s.get("amount") or 0)
                                for s in (u.get("shields") or []) if (s.get("amount") or 0) > 0)
        uc = u.get("unitConfig") or {}
        if isinstance(uc, dict) and uc.get("abilityVariablesMultiplier") is not None:
            mult_by_id[eid] = int(uc["abilityVariablesMultiplier"])
            if uc.get("passiveAbilityLevel"):
                ablvl_by_id[eid] = int(uc["passiveAbilityLevel"])
        # AbilityState PER-ABILITY (#100) — capteur combatSnapshot.abilityStates (entrée
        # ActiveAbility._abilityState @0x4c) : {abilityId: {level, multiplier}}.
        sts = {int(a["id"]): {"level": a.get("level"), "multiplier": a.get("multiplier")}
               for a in (u.get("abilityStates") or []) if a.get("id") is not None}
        if sts:
            abstate_by_id[eid] = sts
        # #87 : NE PAS dropper le ctx sur `normalAttack.error`. `readNormalAttack` (frida rpc-view.ts)
        # renvoie error="aucune cible atteignable au deploiement (base non capturable)" quand aucun
        # ennemi n'est a portee de l'attaque normale DEPUIS LA POSITION COURANTE (il ne teste PAS les
        # move-tiles). Or le natif score les attaques depuis les tuiles de MOUVEMENT -> une unite peut
        # avoir des attaques rankees (attackPlans/decisionView non vide) alors que sa base normale est
        # "non capturable" au deploiement. Dropper le ctx -> scene.ctx()=None -> make_normal_attack_
        # predictions renvoie None -> AUCUNE attaque scoree (normale ET specials via _PREDICT_VIA_
        # NORMAL_ATTACK), d'ou attack_cands=[] malgre NATIVE ranked non-vide. `from_snapshot` degrade
        # deja proprement sur na.error (nh=1, min/max=0) ; la base reelle = get_stat(ATTACK, INITIAL)
        # (position-independante) et l'arme est re-resolue par adjacence (select_weapon_pierce). Le port
        # ne score de toute facon QUE les abilities deja rankees par le natif (_best_attack itere
        # plan.evals) -> aucun risque d'attaque fantome. Build INCONDITIONNEL.
        ctx_by_id[eid] = UnitContext.from_snapshot(u, GC.unit(vis_by_id.get(eid) or ""),
                                                   snap.get("statTypes"))
    # TotalAttacksMade PER-UNITE (#106) — capteur actorStats (ActorStatisticsComponent +0x20). Capture
    # au BUILD (point-in-time) : correct pour une prediction ponctuelle (count=0 au debut de bataille) ;
    # un refresh PAR-PAS (cf. refresh_shields) serait requis pour un compteur qui evolue mid-bataille
    # (count>0) -> suivi #106. Degrade proprement a {} (count=0) si le RPC manque/echoue.
    try:
        _ast = rpc("actorStats", {"runnerId": rid}, 40)
    except Exception:
        _ast = None
    actorstats_by_id = {u["entityId"]: int(u.get("totalAttacksMade") or 0)
                        for u in ((_ast or {}).get("units") or []) if u.get("entityId") is not None}
    # BOARD STATIQUE (#183) : mirror offline des Tile objects natifs. Le natif ne passe PAS de "board" a la
    # prediction -- l'attackerTile (tuile candidate, `local_588` de CalculateAttackerModifiersForPrediction
    # @181000590) PORTE lui-meme son terrain (tileDefId -> IsTrench @180ec6f80 = IsTileWithId) et son graphe
    # de voisins STOCKE (ConnectivityComponent.IsNeighbour, consulte par IsNeighbourOf @180ec6030 ET par
    # MovementUtil.AreTilesAdjacent @18109d740 = (|rowD|<2) & IsNeighbour). Le Board `native_sym` reproduit
    # ce graphe (capture GetAdjacentTiles(false,false,true) = topologie complete #148) + le terrain. Point de
    # couture = build_predictor (tables statiques cold 1x/runner = l'analogue du graphe de tuiles natif bati
    # une fois au battle-init). Threade dans le dict -> from_predictor_sctx le lit en fallback pour les 3
    # call-sites (context live, predict_samples, predict_sweep). ELEVATION derivee du MEME board (source
    # unique, un seul fetch boardGraph), comme Scene.from_state.
    board = build_board(rpc, rid)
    elev_by_pos = ({(t["col"], t["row"]): int(t.get("elevation") or 0) for t in board.by_id.values()}
                   if board is not None else None)
    return {"ctx_by_id": ctx_by_id, "armor_by_id": armor_by_id, "shield_by_id": shield_by_id,
            "mult_by_id": mult_by_id, "ablvl_by_id": ablvl_by_id, "vis_by_id": vis_by_id,
            "abstate_by_id": abstate_by_id, "actorstats_by_id": actorstats_by_id,
            "board": board, "elev_by_pos": elev_by_pos,
            # #194 : vue DefenseComponent (stat 3 + modifications). Capture au BUILD ; DYNAMIQUE
            # (suit l'occupation de tuile) -> re-capturee par-pas via refresh_shields.
            "defstat_by_id": _defense_stats_from_snapshot(snap.get("units"))}


def build_board(rpc, rid):
    """Board STATIQUE (graphe de connectivite + terrain) depuis le RPC `boardGraph` (STATIQUE, 1x/runner).
    Mirror offline des Tile objects natifs : `native_sym` = graphe complet symetrise (capture
    `GetAdjacentTiles(false,false,true)`, #148) = `ConnectivityComponent.IsNeighbour` ; `terrain_at`=tileDefId
    = `IsTrench`/`IsTileWithId`. Alimente les gates POSITIONNELS de la prediction : reduction Trench
    (CalculateTrenchReduction @181004830, sous-branche IsTrench(attackerTile)+IsNeighbourOf) + adjacence
    (select_weapon melee/ranged) + elevation. None si `boardGraph` KO -> gates positionnels no-op (etat
    anterieur, pas de crash)."""
    from engine.entities.pathfinding.board import Board
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
    except Exception:
        return None
    tiles = (bg or {}).get("tiles") if isinstance(bg, dict) else None
    if not tiles:
        return None
    return Board(tiles, adjacency="native_sym")


def _defense_stats_from_snapshot(units) -> dict:
    """{uid: StatComponent(DEFENSE)} depuis un `combatSnapshot` (#194). Reconstruit la vue
    `DefenseComponent` (stat 3) que la face défenseur de `CalculateModifiersFromStatModifications
    @181004380` lit : `initial` = defense résolue − statDelta.defense (base, 100 chez les unités
    mesurées), `modification` = UNE entrée pseudo-source « live » portant le TOTAL des modifications
    (statDelta). ⚠ Limitation documentée : le natif folde CHAQUE source séparément (produit de
    (1±vᵢ/100)) ; le capteur statDelta ne donne que le total → exact à 1 source (le cas tuile
    Thorns/SpiderWeb/DryBush), approximation si ≥2 sources defense simultanées (rare — un
    `statModSources` par unité donnerait le per-source au prix d'un scan entités par pas)."""
    from engine.entities.stats import StatComponent, ValueModification
    out = {}
    for u in (units or []):
        stats = u.get("stats") or {}
        cur = stats.get("defense")
        if cur is None:
            continue
        delta = int((u.get("statDelta") or {}).get("defense") or 0)
        mod = ValueModification(total=delta, per_source={"live": delta} if delta else {})
        out[u["entityId"]] = StatComponent(initial=int(cur) - delta, modification=mod)
    return out


def refresh_shields(predictor, rpc, rid):
    """Rafraîchit l'état DYNAMIQUE (boucliers accordés/consommés + armure débuffée + stat DEFENSE
    modifiée #194) depuis un `combatSnapshot` FRAIS — appeler 1×/pas comparé. (Ex-`PV.refresh_shields`.)"""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not snap.get("ok"):
        return
    predictor["shield_by_id"] = {
        u["entityId"]: sum(int(s.get("amount") or 0)
                           for s in (u.get("shields") or []) if (s.get("amount") or 0) > 0)
        for u in (snap.get("units") or [])}
    predictor["armor_by_id"] = {
        u["entityId"]: int((u.get("stats") or {}).get("fixedArmor") or 0)
        for u in (snap.get("units") or [])}
    predictor["defstat_by_id"] = _defense_stats_from_snapshot(snap.get("units"))


def step_context(predictor, dv):
    """État COURANT du pas (hp/pos/team + effets matérialisés seed) — reconstruit à chaque pas car
    l'état mute. (Ex-`PV.step_context`.)"""
    units = dv.get("units") or []
    return {
        "units": units,
        "hp_by_id": {u["id"]: u.get("hp") for u in units},
        "pos_by_id": {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units if u.get("pos")},
        "team_by_id": {u["id"]: u.get("team") for u in units},
        "eff_state": EffectsState.seed(
            {u["id"]: (u.get("effects") or []) for u in units},
            predictor["mult_by_id"], predictor["ablvl_by_id"]),
    }
