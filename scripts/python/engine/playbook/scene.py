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
    tile_effects_by_pos: dict | None = None            # {(col,row): [noms d'effets de tuile]} — DYNAMIQUE
    #                                                    # (la glace LordOfTempests s'ACCUMULE en bataille) ->
    #                                                    # fourni FRAIS par décision (tileMeta, cf. context.py) ;
    #                                                    # None = inconnu (bonus position-dépendants inertes)
    board: object | None = None                        # Board (voisins natifs, adjacence hex) — cf.
    #                                                    # engine.entities.pathfinding.board ; None → evenq
    # AbilityState PER-ABILITY (#100) : {uid: {abilityId: {"level","multiplier"}}} — capteur
    # combatSnapshot.abilityStates (entrée ActiveAbility._abilityState @0x4c). C'est le couple que
    # le natif passe au playbook et qui indexe les variables config (TryGetVariableArrayForLevel
    # IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel) ; le canal global (mult_by_id/activeAbilityLevel) est un fallback.
    abstate_by_id: dict = field(default_factory=dict)
    # TotalAttacksMade PER-UNITE (#106) : {uid: totalAttacksMade} — capteur actorStats
    # (ActorStatisticsComponent +0x20). Indexe le buff MartialInspiration (+33%/tour). Defaut {}
    # -> count=0 (debut de bataille / from_state offline) si non capte.
    actorstats_by_id: dict = field(default_factory=dict)
    # Stat DEFENSE PER-UNITE (#194) : {uid: StatComponent(stat 3)} — mirror du DefenseComponent natif
    # (IdunBattle.Entities.Components.DefenseComponent$$.cctor) lu par `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction+0x436` : ses modifications
    # (ex. tuile Thorns −50) deviennent des entrees %-list (negate=1 → +50 → ×1.5). DYNAMIQUE (la
    # modification suit l'occupation de tuile) → capture combatSnapshot (defense + statDelta.defense),
    # refresh par-pas via `refresh_shields`. Defaut {} → axe inerte (defense non modifiee partout).
    defstat_by_id: dict = field(default_factory=dict)
    # TurnsStarted PER-UNITE (#46) : {uid: turnsStarted} — stat 12 (`UnitComponent.turnsStarted@+0x58`,
    # incr. StartTurn ; `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` = GetStat(unit,0xc)). Indexe le
    # gate `ShouldEvaluate(unit)` slot-4 des playbooks « pas au 1er tour » (corps folde IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate :
    # TheQuickening/HeroicFusillade/VigilanceEternal = `GetStat(unit,12) > 1`). DYNAMIQUE (incremente
    # a CHAQUE tour demarre) → capture combatSnapshot, refresh par-pas via `refresh_shields`.
    # Defaut {} → uid absent = non capte (l'accesseur rend None, le gate ne mord pas a l'aveugle).
    turns_started_by_id: dict = field(default_factory=dict)
    # Stat ATTACK COURANT PER-UNITE (#45-s18) : {uid: GetStat(Attack, Current)} — la lecture EXACTE des
    # noeuds DSL `StatAmount(Self, Attack, Current)` (ex. splash Psyker `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$GetAttackDamage`).
    # DYNAMIQUE : les ValueModifications vont et viennent (aura RitesOfBattle +1298 par ADJACENCE a
    # Calgar — vecu 31337 : 2101 au deploiement, 803 au s18 une fois Njal eloigne) → le cold
    # `ctx_by_id[uid].attack` (fige au build) SURESTIME/SOUS-ESTIME des qu'une aura bouge. Capture
    # combatSnapshot (stats.attack), refresh par-pas via `refresh_shields`. Defaut {} → fallback
    # `ctx.attack` (from_state offline : le UnitContext du State est deja live).
    attack_cur_by_id: dict = field(default_factory=dict)
    # Stat EXTRA_HITS COURANT PER-UNITE (#57a) : {uid: GetStat(ExtraHits=17, Current)} — les effets
    # stat-mod DYNAMIQUES sur les hits (Swarm_HitReduction 1021 : `SwarmAbility.CreateBehaviour
    # IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour` poste EXTRA_HITS = -min(membresInitiaux-?, membresManquants) a chaque membre perdu ;
    # vecu 1357 s15 u135 ripperSwarm : extraHits -2, hits natifs 3 vs 5 offline). Le cold
    # `ctx.stat(EXTRA_HITS)` (fige a l'hydratation — au SPAWN pour un summon #53) devient stale des
    # que des membres meurent. Capture combatSnapshot (stats.extraHits), refresh par-pas.
    extra_hits_cur_by_id: dict = field(default_factory=dict)
    # ChargedUnitIds PER-UNITE (case-r32) : {uid: set(ids charges CE TOUR)} — mirror de
    # `UnitComponent.ChargedUnitIds@+0x190`, le 2e terme de `IdunBattle.Core.Services.BattleQuery$$IsCharging`.
    # Alimente par `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging`, vide par
    # `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`. `from_state` le lit de l'ECS (donc une
    # prediction faite sur un etat que le runner offline a fait EVOLUER voit les charges deja acquises,
    # comme le natif). ⚠ `from_predictor_sctx` / etat rechargé par `load_state` : AUCUN RPC n'expose ce
    # champ -> table VIDE, degradation RESTRICTIVE (le bonus de charge est omis, jamais invente). Gap
    # d'outillage nomme : le point d'ancrage a hooker est `UnitComponent+0x190` cote `combatSnapshot`.
    charged_by_id: dict = field(default_factory=dict)
    # PreventOverkill PER-UNITE (#195) : {uid: `UnitExtensions.HasFlag(u, 0x13)`} — le 5e argument
    # `isPreventOverkill` que le natif passe à `IsOverkill` DEUX FOIS sur la face décision (dans
    # `ApplyTraitDamageLimitsToDamage`, où il lit `HasFlag(defender, 0x13)` juste avant l'appel ; et
    # via `DamagePredictionResult.PreventOverkill@+0xb3` que lisent `WillBeOverkill`/`MightBeOverkill`).
    # Rempli par `from_state` depuis l'ECS (`unit_prevents_overkill` : composant de flags d'abord,
    # effet 1354 ensuite). VIDE côté `from_predictor_sctx` — AUCUN RPC n'expose `UnitFlagsComponent`
    # (gap d'outillage nommé, tâche O5) : l'accesseur retombe alors sur la DÉRIVATION PAR L'EFFET,
    # qui est le même invariant (cf. `effects_prevent_overkill`), pas une approximation.
    prevent_overkill_by_id: dict = field(default_factory=dict)

    def charged(self, uid) -> set:
        """Ids que `uid` a CHARGES ce tour (vide si non capte)."""
        return self.charged_by_id.get(uid) or set()

    def prevents_overkill(self, uid) -> bool:
        """`UnitExtensions.HasFlag(uid, 0x13)` = `UnitFlag.PreventOverkill` (=19) — la cible ne peut
        PAS être overkillée (#195). Table renseignée (`from_state`) → lecture ECS ; sinon dérivation
        depuis les effets ACTIFS de l'unité, seule source disponible côté live."""
        v = self.prevent_overkill_by_id.get(uid)
        if v is not None:
            return bool(v)
        if self.eff_state is None:
            return False
        from ..runner.components import effects_prevent_overkill
        return effects_prevent_overkill(self.effects(uid))

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
                                         EffectsOwnedComponent, is_machine_of_war,
                                         unit_prevents_overkill)
        ctx_by_id, armor_by_id, shield_by_id, mult_by_id, ablvl_by_id, vis_by_id = {}, {}, {}, {}, {}, {}
        hp_by_id, hpmax_by_id, pos_by_id, team_by_id = {}, {}, {}, {}
        defstat_by_id, charged_by_id, prevent_overkill_by_id = {}, {}, {}
        from engine.entities.stats import StatType as _ST     # #197 : DEFENSE (stat 3) du ctx ECS
        turns_started_by_id = {}
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
            # MACHINES OF WAR exclues : la Scene mirroir `decisionView.units`, qui est
            # `EntityType.Unit`-only (le natif expose les MoW dans un canal SÉPARÉ `.mows`, et
            # `aiPlaybookPredict` a son propre chemin de résolution de caster Machine, case-172).
            # Depuis que `load_state` matérialise les MoW (débloqueur cast MoW), les faire entrer
            # ici les traiterait comme des unités sans position -> face DÉCISION inchangée.
            if is_machine_of_war(e):
                continue
            vis = uc.visual_id if uc else None
            pos = (pc.col, pc.row) if pc is not None else None
            if sc is not None:                                    # tables prédiction : entités à ctx
                ctx = sc.ctx
                ctx_by_id[eid] = ctx
                armor_by_id[eid] = int(ctx.fixed_armor)
                mult_by_id[eid] = int(ctx.ability_variables_multiplier or 100)
                ablvl_by_id[eid] = int(ctx.passive_ability_level or 0)
                # #197 : StatComponent DEFENSE (stat 3) de l'ECS live -> la prédiction OFFLINE (from_state)
                # folde le stat-mod defense (Thorns ×1.5) comme le COMBAT runner, MEME source (ctx.stats)
                # -> décision offline et combat cohérents. None si le stat n'est pas seedé (axe inerte).
                _ds = ctx.stats.components.get(int(_ST.DEFENSE)) if ctx.stats is not None else None
                if _ds is not None:
                    defstat_by_id[eid] = _ds
                # #46 : TurnsStarted (stat 12) du ctx ECS — le runner offline l'incremente au
                # StartTurn (mirror `StartTurnOperation IdunBattle.Operations.StartTurnOperation$$Execute`, `increment_base`).
                if ctx.stats is not None and int(_ST.TURNS_STARTED) in ctx.stats.components:
                    turns_started_by_id[eid] = ctx.stats.get_stat(int(_ST.TURNS_STARTED))
            shield_by_id[eid] = shc.get_total_shield() if shc is not None else 0
            # case-r32 : `UnitComponent.ChargedUnitIds@+0x190` tel que l'ECS le porte MAINTENANT.
            if getattr(uc, "charged_unit_ids", None):
                charged_by_id[eid] = {int(i) for i in uc.charged_unit_ids}
            # #195 : `HasFlag(u, 0x13)` LU de l'ECS (composant de flags d'abord, effet 1354 ensuite).
            prevent_overkill_by_id[eid] = unit_prevents_overkill(state, eid)
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
            elev_by_pos=elev_by_pos, board=board, defstat_by_id=defstat_by_id,
            turns_started_by_id=turns_started_by_id, charged_by_id=charged_by_id,
            prevent_overkill_by_id=prevent_overkill_by_id)
        sc._seed_battle_counters()   # #185 (units offline sans defeatedByMelee -> N=0, inerte)
        return sc

    @classmethod
    def from_predictor_sctx(cls, predictor: dict, sctx: dict, elev_by_pos: dict | None = None,
                            board: object | None = None,
                            tile_effects_by_pos: dict | None = None) -> "Scene":
        """Bridge des dicts de l'ancien PV vers l'objet Scene (mêmes données, forme objet).
        `tile_effects_by_pos` = effets de tuile FRAIS du pas (tileMeta ; dynamique — la glace
        LordOfTempests s'accumule) ; None -> bonus position-dépendants inertes."""
        sc = cls(
            ctx_by_id=predictor.get("ctx_by_id") or {}, armor_by_id=predictor.get("armor_by_id") or {},
            shield_by_id=predictor.get("shield_by_id") or {}, mult_by_id=predictor.get("mult_by_id") or {},
            ablvl_by_id=predictor.get("ablvl_by_id") or {}, vis_by_id=predictor.get("vis_by_id") or {},
            units=sctx.get("units") or [], hp_by_id=sctx.get("hp_by_id") or {},
            pos_by_id=sctx.get("pos_by_id") or {}, team_by_id=sctx.get("team_by_id") or {},
            eff_state=sctx.get("eff_state"), hpmax_by_id=sctx.get("hpmax_by_id") or {},
            elev_by_pos=elev_by_pos if elev_by_pos is not None else predictor.get("elev_by_pos"),
            tile_effects_by_pos=tile_effects_by_pos,
            board=board if board is not None else predictor.get("board"),
            abstate_by_id=predictor.get("abstate_by_id") or {},
            actorstats_by_id=predictor.get("actorstats_by_id") or {},
            defstat_by_id=predictor.get("defstat_by_id") or {},
            turns_started_by_id=predictor.get("turns_started_by_id") or {},
            attack_cur_by_id=predictor.get("attack_cur_by_id") or {},
            extra_hits_cur_by_id=predictor.get("extra_hits_cur_by_id") or {})
        sc._seed_battle_counters()   # #185 BlessingsOfKhorne (melee-defeats -> effets N-scalés)
        return sc

    # ── Compteurs de bataille (#185) ───────────────────────────────────────────────────────────────
    def melee_defeats(self) -> int:
        """Compte de base de `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee` = `Count(NormalUnits(
        UnitsDefeatedByMeleeAttack(AllUnits)))` : unités NORMALES (kind-1 — `dv.units` = squads hors
        MoW par construction, `IdunBattleLogic.Entities.DSLFactory$$NormalUnits` = `Units(set, kind=1)`) MORTES
        tuées par une attaque de MÊLÉE. Flag = `UnitComponent.DefeatedByMeleeAttack @0x178` (écrit
        par `KillUnitOperation IdunBattle.Operations.KillUnitOperation$$Execute`, capté #185 dans decisionView.units) ; `isDead` requis en
        mirror du sélecteur `IdunBattle.Entities.Selectors.UnitsDefeatedByMeleeAttackSelector$$IsValidUnit` (une unité RESSUSCITÉE ne compte plus). GLOBAL
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
        par la face défenseur de `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` (#194).
        None si non capturé (from_state offline sans suivi defense, ou unité absente) → axe inerte."""
        return self.defstat_by_id.get(uid)

    def total_attacks_made(self, uid) -> int:
        """`ActorStatisticsComponent.TotalAttacksMade` (+0x20, capteur actorStats) — nb d'attaques
        de l'unité CETTE BATAILLE. Indexe le buff MartialInspiration (+33%/tour, #106). 0 si non
        capté (from_state offline / début de bataille)."""
        return int((self.actorstats_by_id or {}).get(uid, 0) or 0)

    def attack_current(self, uid) -> int:
        """`GetStat(unit, Attack=0, Current)` DU PAS — la lecture des noeuds `StatAmount(Attack)`
        (#45-s18). Fallback `ctx.attack` (cold snapshot / from_state live) si non capturé."""
        v = (self.attack_cur_by_id or {}).get(uid)
        if v is not None:
            return int(v)
        c = self.ctx_by_id.get(uid)
        return int(c.attack) if c is not None else 0

    def extra_hits_current(self, uid) -> int | None:
        """`GetStat(unit, ExtraHits=17, Current)` DU PAS (#57a) — inclut les stat-mods dynamiques
        (Swarm_HitReduction). Fallback `ctx.stat(EXTRA_HITS)` (cold snapshot / from_state live) ;
        None si l'unité est absente des deux tables."""
        v = (self.extra_hits_cur_by_id or {}).get(uid)
        if v is not None:
            return int(v)
        c = self.ctx_by_id.get(uid)
        from engine.entities.stats import StatType as _ST
        return int(c.stat(_ST.EXTRA_HITS)) if c is not None else None

    def turns_started(self, uid) -> int | None:
        """`GetStat(unit, 0xc=TurnsStarted)` (`IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`) — nb
        de tours DEMARRES par l'unité cette bataille (incr. StartTurn). Indexe le gate slot-4
        `ShouldEvaluate(unit) = GetStat(unit,12) > 1` (#46, corps foldé IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate). None si non
        capturé (uid absent des tables) → l'appelant ne gate pas à l'aveugle."""
        v = (self.turns_started_by_id or {}).get(uid)
        return None if v is None else int(v)


# ── SEAM live-feed (RPC) — tables cold + état par-pas. `rpc(method, body, timeout) -> result dict`. ──
def _hydrate_static_unit(ctx_by_id, vis_by_id, mult_by_id, ablvl_by_id, abstate_by_id,
                         u, vis_id, stat_types):
    """Entrée STATIQUE d'une unité dans les tables du predictor (bloc per-unit de
    `build_predictor`, partagé avec l'hydratation mid-bataille de `refresh_shields` #53).

    #87 : NE PAS dropper le ctx sur `normalAttack.error`. `readNormalAttack` (frida rpc-view.ts)
    renvoie error="aucune cible atteignable au deploiement (base non capturable)" quand aucun
    ennemi n'est a portee de l'attaque normale DEPUIS LA POSITION COURANTE (il ne teste PAS les
    move-tiles). Or le natif score les attaques depuis les tuiles de MOUVEMENT -> une unite peut
    avoir des attaques rankees (attackPlans/decisionView non vide) alors que sa base normale est
    "non capturable" au deploiement. Dropper le ctx -> scene.ctx()=None -> make_normal_attack_
    predictions renvoie None -> AUCUNE attaque scoree (normale ET specials via _PREDICT_VIA_
    NORMAL_ATTACK), d'ou attack_cands=[] malgre NATIVE ranked non-vide. `from_snapshot` degrade
    deja proprement sur na.error (nh=1, min/max=0) ; la base reelle = get_stat(ATTACK, INITIAL)
    (position-independante) et l'arme est re-resolue par adjacence (select_weapon_pierce). Le port
    ne score de toute facon QUE les abilities deja rankees par le natif (_best_attack itere
    plan.evals) -> aucun risque d'attaque fantome. Build INCONDITIONNEL."""
    eid = u["entityId"]
    u["visualId"] = vis_id
    vis_by_id[eid] = vis_id
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
    ctx_by_id[eid] = UnitContext.from_snapshot(u, GC.unit(vis_id or ""), stat_types)


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
        armor_by_id[eid] = int((u.get("stats") or {}).get("fixedArmor") or 0)
        shield_by_id[eid] = sum(int(s.get("amount") or 0)
                                for s in (u.get("shields") or []) if (s.get("amount") or 0) > 0)
        _hydrate_static_unit(ctx_by_id, vis_by_id, mult_by_id, ablvl_by_id, abstate_by_id,
                             u, vis_by_id.get(eid), snap.get("statTypes"))
    # TotalAttacksMade PER-UNITE (#106) — capteur actorStats (ActorStatisticsComponent +0x20). Capture
    # au BUILD (point-in-time = count au pas 0). DYNAMIQUE (incremente a chaque attaque) -> RE-CAPTUREE
    # PAR-PAS par `refresh_shields` (#33 : sans ce refresh, une prediction mid-bataille indexee par ce
    # compteur SOUS-ESTIME -- MartialInspiration ; staleness prouvee 31337 s16). Degrade proprement a
    # {} (count=0) si le RPC manque/echoue.
    try:
        _ast = rpc("actorStats", {"runnerId": rid}, 40)
    except Exception:
        _ast = None
    actorstats_by_id = {u["entityId"]: int(u.get("totalAttacksMade") or 0)
                        for u in ((_ast or {}).get("units") or []) if u.get("entityId") is not None}
    # BOARD STATIQUE (#183) : mirror offline des Tile objects natifs. Le natif ne passe PAS de "board" a la
    # prediction -- l'attackerTile (tuile candidate, `local_588` de CalculateAttackerModifiersForPrediction
    # IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction) PORTE lui-meme son terrain (tileDefId -> IdunBattle.Entities.TileExtensions$$IsTrench = IsTileWithId) et son graphe
    # de voisins STOCKE (ConnectivityComponent.IsNeighbour, consulte par IdunBattle.Entities.TileExtensions$$IsNeighbourOf ET par
    # IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent = (|rowD|<2) & IsNeighbour). Le Board `native_sym` reproduit
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
            # #46 : TurnsStarted (stat 12) — gate slot-4 « pas au 1er tour ». DYNAMIQUE ->
            # re-capturé par-pas via `refresh_shields` (le cold seul serait figé au pas 0).
            "turns_started_by_id": {
                u["entityId"]: int((u.get("stats") or {}).get("turnsStarted") or 0)
                for u in (snap.get("units") or [])
                if (u.get("stats") or {}).get("turnsStarted") is not None},
            "board": board, "elev_by_pos": elev_by_pos,
            # #194 : vue DefenseComponent (stat 3 + modifications). Capture au BUILD ; DYNAMIQUE
            # (suit l'occupation de tuile) -> re-capturee par-pas via refresh_shields.
            "defstat_by_id": _defense_stats_from_snapshot(snap.get("units")),
            # #45b' : MaxHealth EFFECTIF (capteur combatSnapshot.healthMax = GetStat(e,5,part=2),
            # la lecture EXACTE de DamageUtility IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext pour combinedMax — base+modifs,
            # clamp cape). DYNAMIQUE (bump TwistedScience mid-bataille) -> refresh par-pas.
            # Vieux hooks sans le champ -> {} (fallback obs.hpMax base, etat anterieur).
            "hpmax_eff_by_id": _hpmax_eff_from_snapshot(snap.get("units")),
            # #45-s18 : Attack COURANT (GetStat(0, Current)) — lecture des noeuds StatAmount(Attack)
            # (splash Psyker). DYNAMIQUE (aura RitesOfBattle par adjacence) -> refresh par-pas.
            "attack_cur_by_id": {
                u["entityId"]: int((u.get("stats") or {}).get("attack") or 0)
                for u in (snap.get("units") or [])
                if (u.get("stats") or {}).get("attack") is not None},
            # #57a : ExtraHits COURANT (GetStat(17, Current)) — stat-mods hits dynamiques
            # (Swarm_HitReduction IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour). DYNAMIQUE -> refresh par-pas.
            "extra_hits_cur_by_id": {
                u["entityId"]: int((u.get("stats") or {}).get("extraHits") or 0)
                for u in (snap.get("units") or [])
                if (u.get("stats") or {}).get("extraHits") is not None}}


def build_board(rpc, rid):
    """Board STATIQUE (graphe de connectivite + terrain) depuis le RPC `boardGraph` (STATIQUE, 1x/runner).
    Mirror offline des Tile objects natifs : `native_sym` = graphe complet symetrise (capture
    `GetAdjacentTiles(false,false,true)`, #148) = `ConnectivityComponent.IsNeighbour` ; `terrain_at`=tileDefId
    = `IsTrench`/`IsTileWithId`. Alimente les gates POSITIONNELS de la prediction : reduction Trench
    (IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction, sous-branche IsTrench(attackerTile)+IsNeighbourOf) + adjacence
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


def _hpmax_eff_from_snapshot(units) -> dict:
    """{uid: MaxHealth EFFECTIF} depuis `combatSnapshot.healthMax` (#45b') = GetStat(e, Health=5,
    StatPart=2) — l'agrégat base+modifications (clamp cape inclus) que `DamageUtility
    IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` lit pour combinedMax. {} si le capteur manque (vieux hooks)."""
    return {u["entityId"]: int(u["healthMax"]) for u in (units or [])
            if u.get("healthMax") is not None}


def _defense_stats_from_snapshot(units) -> dict:
    """{uid: StatComponent(DEFENSE)} depuis un `combatSnapshot` (#194). Reconstruit la vue
    `DefenseComponent` (stat 3) que la face défenseur de `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` lit : `initial` = defense résolue − statDelta.defense (base, 100 chez les unités
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
    """Rafraîchit l'état DYNAMIQUE par pas comparé (appeler 1×/pas) — deux sources FRAÎCHES :
    - `combatSnapshot` : boucliers accordés/consommés + armure débuffée + stat DEFENSE modifiée (#194) ;
    - `actorStats` : `TotalAttacksMade` par unité (#33/#106) — DYNAMIQUE (incrémente à CHAQUE attaque)
      donc le cold de `build_predictor` (capté au pas 0 = 0) SOUS-ESTIME toute prédiction mid-bataille
      indexée par ce compteur (MartialInspiration +33 %/attaque). Staleness FEED prouvée 31337 s16 :
      l'attaquant u79 avait fait 2 attaques → cold 598-898 vs natif 994-1976 == fresh (2 stacks).
    (Ex-`PV.refresh_shields`.)"""
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
    # #45b' : re-capture MaxHealth EFFECTIF (part 2) — DYNAMIQUE (bump TwistedScience
    # mid-bataille : u87 777 s15 base 11044 -> 14036 apres le cast 1167 du pas 1).
    predictor["hpmax_eff_by_id"] = _hpmax_eff_from_snapshot(snap.get("units"))
    # #45-s18 : re-capture Attack COURANT (StatAmount(Attack) du pas) — DYNAMIQUE (aura
    # RitesOfBattle +1298 par ADJACENCE : 2101 au deploiement vs 803 au s18, 31337 u89).
    predictor["attack_cur_by_id"] = {
        u["entityId"]: int((u.get("stats") or {}).get("attack") or 0)
        for u in (snap.get("units") or [])
        if (u.get("stats") or {}).get("attack") is not None}
    # #57a : re-capture ExtraHits COURANT — stat-mods hits dynamiques (Swarm_HitReduction :
    # -1 hit par membre de swarm perdu, maintenu par le behaviour DSL IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour). Le cold
    # (hydratation au build/spawn) SURESTIME les hits des qu'un membre meurt (1357 s15 u135 :
    # extraHits -2, natif 3 hits vs 5 offline).
    predictor["extra_hits_cur_by_id"] = {
        u["entityId"]: int((u.get("stats") or {}).get("extraHits") or 0)
        for u in (snap.get("units") or [])
        if (u.get("stats") or {}).get("extraHits") is not None}
    # #46 : re-capture TurnsStarted (stat 12, incrémente à chaque tour démarré) — même raison
    # que TotalAttacksMade (#33) : le cold du build (pas 0) sous-estime tout gate mid-bataille.
    predictor["turns_started_by_id"] = {
        u["entityId"]: int((u.get("stats") or {}).get("turnsStarted") or 0)
        for u in (snap.get("units") or [])
        if (u.get("stats") or {}).get("turnsStarted") is not None}
    # #33 : re-capture TotalAttacksMade (mirror du refresh de build_predictor). On n'écrase QUE si
    # le RPC a répondu (units présent) — sinon on garde le cold en fallback (RPC KO -> _r renvoie {},
    # .get("units") is None). Un `actorStats` valide sans attaque = {units:[…, totalAttacksMade:0]}.
    _ast = rpc("actorStats", {"runnerId": rid}, 40)
    if _ast.get("units") is not None:
        predictor["actorstats_by_id"] = {
            u["entityId"]: int(u.get("totalAttacksMade") or 0)
            for u in _ast["units"] if u.get("entityId") is not None}
    # #53 : hydrate les unités APPARUES mid-bataille (summons) dans les tables STATIQUES —
    # `build_predictor` est cold (pas 0), donc un summon spawné ensuite n'a NI ctx NI visualId :
    # scene.ctx(summon)=None -> make_normal_attack_predictions=None -> toutes tuiles refusées
    # ("gated") -> le moteur bouge au lieu d'attaquer (batch #52 : 5 misses, probe_53_summon).
    # Le natif lit l'ECS live par décision — l'hydratation par-pas retire la staleness de NOTRE
    # seam, elle n'invente rien. decisionView LAZY (1 RPC uniquement quand un entityId inconnu
    # apparaît dans le snapshot frais — rare).
    new_units = [u for u in (snap.get("units") or [])
                 if u.get("entityId") is not None and u["entityId"] not in predictor["ctx_by_id"]]
    if new_units:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        vis = {x["id"]: x.get("visualId") for x in (dv0.get("units") or [])}
        for u in new_units:
            _hydrate_static_unit(predictor["ctx_by_id"], predictor["vis_by_id"],
                                 predictor["mult_by_id"], predictor["ablvl_by_id"],
                                 predictor["abstate_by_id"], u, vis.get(u["entityId"]),
                                 snap.get("statTypes"))


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
