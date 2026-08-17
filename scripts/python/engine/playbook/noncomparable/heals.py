"""Playbooks de SOIN / REPAIR / refresh NonComparable — famille partageant HealTargets / _wound_fraction.

Rites (resurrection), CombatRestoratives (heal AoE), DefendTheDivineWork (repair AoE), Revitalizing-
Malignancy (heal Chaos filtre), InspiredToGreatness (refresh d'ability d'un allie). DefendTheDivineWork
et RevitalizingMalignancy REUTILISENT `CombatRestorativesPlaybook._wound_fraction` (couplage natif =
meme IdunBattleLogic.Entities.Abilities.Active.Loki.CombatRestorativesAbility$$HealTargets) -> co-localises.
"""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import entity_trait_names, trait_name

from ._base import (NCContext, NonComparablePlaybook, _has_valid_targets,
                    _sweep_origin_first, _traits, _unit_cfg)
from engine.runner.operations.triggers.revive_effect import is_affected_by_heal_type


def _affected_by_heal_type(ctx: NCContext, obs_unit: dict, heal_type: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(unit, healType)` COTE DECISION —
    le MEME mirror 1:1 que consomme la face COMBAT, pas une seconde expression du gate.

        if (GetBaseUnitComponent(unit) != null && HasTrait(unit, 0x421)) return true;
        if (healType == 0 &&  IsMechanical(unit)) return false;     // Heal   : pas les mecaniques
        if (healType == 1 && !IsMechanical(unit)) return false;     // Repair : QUE les mecaniques
        return true;

    ou `IdunBattle.Entities.UnitExtensions$$IsMechanical` = `HasTrait(Mechanical=5)` OU
    `HasTrait(LivingMetal=0x3e8=1000)` OU `HasTrait(Vehicle=0x405=1029)` — les TROIS, alors que ce
    module ne testait que `Mechanical` : necroWarden (LivingMetal, PAS Mechanical) etait compte
    soignable cote DECISION et refuse cote COMBAT (`healable_heal_type_0`), et symetriquement
    invisible au gate repair de DefendTheDivineWork.

    L'implementation DELEGUE a `runner/operations/triggers/revive_effect.py::is_affected_by_heal_type`
    (le mirror deja porte, appele par `BattleQuery$$CanBeRevived`) en lui passant un resolveur de trait
    NAME-BASED : cote decision il n'y a pas de `BaseUnitComponent`, le substrat equivalent est
    `entity_trait_names(unit_ctx, visualId)` (#225) = kit gameconfig + traits ACCORDES EN BATAILLE
    (`AddTrait` -> `BaseUnitComponent+0x40`/`+0x48`) + pseudo-trait de grande-alliance. Un
    `AffectedByHealAndRepair` accorde en cours de bataille (seul vecteur natif :
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SupaCyborkBodyAbility_AddTrait$$CreateBehaviour`,
    trait porte par 0/669 unites au gameconfig) est donc VU des lors que la Scene est branchee.
    `ctx.scene` absente (harnais de sonde) ou unite hors tables -> borne STATIQUE
    `entity_trait_names(None, visualId)`, exactement comme `utilities/tile.py::_adjacent_units`.

    ⚠ Ce gate n'est QU'UN des disjuncts de `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`,
    la fonction que le wrapper `Healable` (`IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select`,
    slot 0x11 de l'IAttackQuery) applique reellement : `NOT IsMachine(EntityType==6)` &
    `(IsDamagedUnit | HasNegativeUnitEffect | HasFlag(source,0x17))` & `NOT HasHealBlockers` &
    `NOT (checkGroupLimit && IsAtGroupUnitHealLimit)` & `NOT HasTrait(0xd=Object)` &
    `IsAffectedByHealType(unit, 0)`. Les cinq premiers restent NON PORTES cote decision (residu nomme,
    cf. backlog) — les porter n'est pas une retouche de ce gate mais un chantier par disjunct."""
    scene = getattr(ctx, "scene", None)
    sid = obs_unit.get("squadId")
    uctx = scene.ctx(sid) if (scene is not None and sid is not None) else None
    names = entity_trait_names(uctx, obs_unit.get("visualId"))
    return bool(is_affected_by_heal_type(lambda _u, tid: trait_name(tid) in names,
                                        obs_unit, int(heal_type)))


class RitesOfRestorationPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.RitesOfRestorationPlaybook$$EvaluateNonComparable` (NonComparable, id 1039). Soin AoE +
    RESURRECTION (adeptHospitaller). Emet l'action en 1039, ciblee sur SOI (confirme live : ATK(1039,78)).

    - `IdunBattle.AI.Playbook.Loki.RitesOfRestorationPlaybook$$ShouldEvaluate` : `Count(GetPossibleResurrectTargets) > 0` -> l'IA n'evalue Rites QUE
      s'il y a un allie DEFAIT. Morts lus via `obs_units.isDead` (decisionView garde les depouilles ->
      observeBattle est la source ; cf. project_decisionview_keeps_dead).
    - Gate (par position T du caster) : `(heroDead>=1 & |resurrectTiles|>=1) | (summonDead>=2 & |tiles|>=2)`.
      hero = allie mort avec trait `Hero` (UnitsWithTrait 0x10 @GetPossibleResurrectHeroTargets 181203d00) ;
      summon = allie mort SANS `Hero` (UnitsWithTrait 2 IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetPossibleResurrectSummonTargets). resurrectTiles = `CanAddUnit(
      AdjacentTiles(T))` IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetResurrectTiles = hex adjacents sur board, libres (unite vivante absente).
    - util = `1 + Count(GetHealTargets)` (cctor Fix64(1) IdunBattle.AI.Playbook.Loki.RitesOfRestorationPlaybook$$.cctor ; IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetHealTargets =
      `Healable(owner + AdjacentFriends(owner,1))` = self (non-Mecanique) + amis adjacents non-Mecaniques).
      MIN_UTILITY=1 (Bucket du cctor). Sweep reach_nc (adjacence -> depend de la position -> le caster va
      la ou il soigne le plus).
    PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170)."""
    ABILITY_ID = int(ActiveAbilityType.RitesOfRestoration)  # 1039
    MIN_UTILITY = 1.0
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        obs = ctx.obs_units or []
        me_obs = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        if me_obs is None:
            return []
        team = me_obs.get("teamId")
        # ShouldEvaluate : Count(GetPossibleResurrectTargets) > 0. IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetPossibleResurrectTargets
        # = AllDeadUnits -> Friends -> UnitsWithTrait(0x1a=Imperial=26) -> UnitsAffectedByHealType(0)
        # (le litteral healType du noeud `UnitsAffectedByHealType` est bien **0**, lu au decompile).
        # Le gate heal-type passe par `_affected_by_heal_type` (mirror complet : disjunct HasTrait(0x421)
        # + les TROIS traits d'IsMechanical) au lieu du seul « Mechanical absent du kit ». Imperial =
        # gameconfig GrandAllianceId. Morts lus via obs_units.isDead.
        def _resurrectable(u):
            cfg = _unit_cfg(u.get("visualId"))
            return (cfg.get("GrandAllianceId") == "Imperial"                 # UnitsWithTrait(0x1a=26)
                    and _affected_by_heal_type(ctx, u, 0))                   # UnitsAffectedByHealType(0)
        dead = [u for u in obs if u.get("teamId") == team and u.get("isDead")
                and u.get("squadId") != ctx.uid and _resurrectable(u)]
        if not dead:
            return []   # Count(GetPossibleResurrectTargets) == 0 -> ability non evaluee
        # hero = ResurrectTargets ∩ UnitsWithTrait(0x10=Hero=16) IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetPossibleResurrectHeroTargets ; summon = ∩ UnitsWithTrait(
        # Summon=2) IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetPossibleResurrectSummonTargets. Le trait "Summon" EST exposé par gameconfig (59 unités ; les summons
        # Imperial sont en section kind="summons", PAS "npc") -> l'ancien proxy kind=="npc" ratait 100%
        # des vrais summons ET comptait des npc non-summon (faux nég + faux pos, validateur) -> trait exact.
        hero_dead = sum(1 for u in dead if "Hero" in _traits(u.get("visualId")))
        summon_dead = sum(1 for u in dead if "Summon" in _traits(u.get("visualId")))
        # Alliees VIVANTES heal-affectables (heal targets adjacents) + occupation (resurrectTiles).
        # `GetHealTargets` = `Healable(caster, self@0x160 + AdjacentFriends(self,1), 0)` : le gate porte
        # ici est `IsAffectedByHealType(u, 0)` (les autres disjuncts d'`EntityCanBeHealed` restent hors
        # portee, cf. `_affected_by_heal_type`).
        ally_healable_pos = [(u.get("col"), u.get("row")) for u in obs
                             if u.get("teamId") == team and not u.get("isDead")
                             and u.get("squadId") != ctx.uid and u.get("col") is not None
                             and _affected_by_heal_type(ctx, u, 0)]
        self_healable = _affected_by_heal_type(ctx, me_obs, 0)
        occupied = {(u.get("col"), u.get("row")) for u in obs
                    if not u.get("isDead") and u.get("squadId") != ctx.uid
                    and u.get("col") is not None}                # le caster (mobile) n'occupe pas
        board = ctx.elev_by_pos or {}
        best = None  # (T, util)
        for T in _sweep_origin_first(ctx):   # ORIGINE d'abord : keep-first au tie -> reste en place (#76)
            res_tiles = [n for n in hexgeo.neighbors(*T)
                         if ((not board) or n in board) and n not in occupied]
            gate = (hero_dead >= 1 and len(res_tiles) >= 1) or (summon_dead >= 2 and len(res_tiles) >= 2)
            if not gate:
                continue
            heal_count = (1 if self_healable else 0) + sum(
                1 for p in ally_healable_pos if bq.is_adjacent(T, p, ctx.elev_by_pos, bq.neigh_map(ctx)))  # AdjacentUnits gate (#45/#76)
            util = 1.0 + heal_count
            if best is None or util > best[1]:   # strict > : 1er max garde (ordre reach_nc)
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] Rites deadHero={hero_dead} deadSum={summon_dead} "
                  f"best={best} min={self.MIN_UTILITY}", file=sys.stderr)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        T, util = best
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,   # cast sur SOI (self-target)
                 "to": (T if T != ctx.origin else None), "pred": util}]


class CombatRestorativesPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.CombatRestorativesPlaybook$$EvaluateNonComparable` (NonComparable, id 1002 ;
    ultraApothecary/Incisus). Soin AoE self + allies adjacents. Emet l'action ciblee sur SOI.

    - Ciblage `IdunBattleLogic.Entities.Abilities.Active.Loki.CombatRestorativesAbility$$HealTargets` = `Friends(AdjacentUnits(caster,r=1))
      + self` -> SOI + unites ALLIEES adjacentes. Pas de wrapper `Healable` (contrairement a Rites
      IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetHealTargets) : inclut les allies MECANIQUES (le natif compte leur fraction de PV manquante).
    - util(T) = `Σ (1 - FillUpStatComponent.RemainingPercentage) IdunBattle.Entities.Components.FillUpStatComponent$$RemainingPercentage` sur {self + allies
      adjacents a T}. `RemainingPercentage = max(0, cur/max)` (Health fillup : cur@+0x18 / CurrentMax)
      -> `1 - RemainingPercentage = missing/maxHP` = FRACTION de PV MANQUANTE. N'utilise PAS le
      montant `hpToHeal` (magnitude != utilite dans ce regime NonComparable). Un allie plein -> 0.
    - MIN_UTILITY = `Fix64.FromIntFraction(9,10) = 0.9` (IdunBattle.AI.Playbook.Loki.CombatRestorativesPlaybook$$.cctor). Sweep reach_nc (le caster
      va la ou la somme des fractions manquantes adjacentes est max), argmax STRICT.
    PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170)."""
    ABILITY_ID = int(ActiveAbilityType.CombatRestoratives)  # 1002
    MIN_UTILITY = 0.9      # IdunBattle.AI.Playbook.Loki.CombatRestorativesPlaybook$$.cctor : Fix64.FromIntFraction(9,10)
    PRIORITY = 0

    @staticmethod
    def _wound_fraction(u: dict) -> float:
        """`1 - FillUpStatComponent.RemainingPercentage` = `(maxHP - curHP)/maxHP` (>= 0). Health fillup
        lu depuis obs_units (hp/hpMax). maxHP <= 0 -> 0 (evite /0, comme le +1 defensif natif absent ici)."""
        mx = int(u.get("hpMax") or 0)
        if mx <= 0:
            return 0.0
        cur = int(u.get("hp") or 0)
        return max(0.0, 1.0 - cur / mx)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        obs = ctx.obs_units or []
        me_obs = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        if me_obs is None:
            return []
        team = me_obs.get("teamId")
        self_wound = self._wound_fraction(me_obs)      # self TOUJOURS dans HealTargets (0 si plein)
        # Allies VIVANTS (self exclu) avec position -> candidats "adjacents a T" (Friends(AdjacentUnits)).
        allies = [(u.get("col"), u.get("row"), self._wound_fraction(u)) for u in obs
                  if u.get("teamId") == team and not u.get("isDead")
                  and u.get("squadId") != ctx.uid and u.get("col") is not None]
        best = None  # (T, util)
        for T in _sweep_origin_first(ctx):   # ORIGINE d'abord : keep-first au tie -> reste en place (#76)
            # IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(caster@T, r=1) = AdjacentTiles + porte d'elevation |dElev|<2
            # d'IterateAdjacentTiles (#45/#76). bq.is_adjacent = MEME adjacence que les comptages
            # GetAdjacent* -> plus de fork raw-hexgeo qui sur-comptait des voisins hors-elevation.
            util = self_wound + sum(w for c, r, w in allies if bq.is_adjacent(T, (c, r), ctx.elev_by_pos, bq.neigh_map(ctx)))
            if best is None or util > best[1]:         # strict > : 1er max garde (ordre reach_nc)
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] CombatRestoratives selfW={self_wound:.2f} "
                  f"best={best} min={self.MIN_UTILITY}", file=sys.stderr)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        T, util = best
        # Cible native = MainTile-id du caster (self-cast AoE : GenerateAction(this, pos, MainTile, util) ;
        # mesure live tgt=22 = id de la tuile (1,0) du caster). Fallback ctx.uid si tile-id absent.
        target = ctx.tile_id_by_pos.get(T, ctx.uid)
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": util}]


class DefendTheDivineWorkPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DefendTheDivineWorkPlaybook$$EvaluateNonComparable` (NonComparable REPAIR, id 1117 ;
    admecManipulus/Actus). Repair AoE self + allies adjacents ; emet l'action ciblee sur SOI (MainTile).

    - Ciblage = `IdunBattleLogic.Entities.Abilities.Active.Loki.CombatRestorativesAbility$$HealTargets` REUTILISE (self + amis adjacents),
      GATE par `GetEligibleTargetsEntities` : l'ability n'est evaluee QUE s'il existe >=1 cible eligible
      (repair -> unite MECANIQUE). Sinon aucune action a cette position.
    - util(T) = `Σ_{cible ∈ HealTargets} [ (1 - FillUpStatComponent.RemainingPercentage_health IdunBattle.Entities.Components.FillUpStatComponent$$RemainingPercentage)
      + 0.5 × HasValidTargets(cible) ]` sur {self + amis adjacents}. Le +0.5 (`Fix64.FromIntFraction(1,2)`)
      par cible SSI `IBattleQuery.HasValidTargets(cible, GetUnitPosition(cible), GetNormalAttackType(cible))`
      (slot 0x3f IdunBattle.Core.Services.BattleQuery$$HasValidTargets -> `IdunBattle.Core.Services.AttackQuery$$HasValidTargets`) = "la cible peut-elle attaquer un
      ennemi avec son attaque NORMALE DEPUIS SA POSITION (sans bouger)" = combat-readiness (+0.5 par allié
      réparé prêt à combattre). PORTÉ (#77) via `_has_valid_targets(ctx, cible)` = `abilityTargets(cible,
      normalAttack).usable ET fromHereCount>0` (`fromHere` = GetValidTargets à position FIXE) — calculé 1x
      par cible (position-indép du sweep). `ability_targets` absent -> +0.5 omis (borne inf, pré-#77).
    - MIN_UTILITY = `Fix64.FromIntFraction(9,10) = 0.9` (IdunBattle.AI.Playbook.Loki.DefendTheDivineWorkPlaybook$$.cctor). Sweep reach_nc, argmax STRICT.
    PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170)."""
    ABILITY_ID = int(ActiveAbilityType.DefendTheDivineWork)  # 1117
    MIN_UTILITY = 0.9      # IdunBattle.AI.Playbook.Loki.DefendTheDivineWorkPlaybook$$.cctor : Fix64.FromIntFraction(9,10)
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        obs = ctx.obs_units or []
        me_obs = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        if me_obs is None:
            return []
        team = me_obs.get("teamId")
        wf = CombatRestorativesPlaybook._wound_fraction
        self_wound = wf(me_obs)                                       # self TOUJOURS dans HealTargets
        # GATE `GetEligibleTargetsEntities` -> IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$GetDynamicInvalidTargetReason :
        # pour une cible AMIE != caster, la seule raison d'invalidite restante est
        # `NOT IsAffectedByHealType(target, **1**)` (litteral lu au decompile). Type 1 = REPAIR =
        # HasTrait(0x421) OU IsMechanical -- donc LivingMetal/Vehicle comptent, pas seulement le trait
        # `Mechanical` que ce module testait.
        self_repairable = _affected_by_heal_type(ctx, me_obs, 1)
        # combat-readiness (#77) : +0.5 par cible qui HasValidTargets DEPUIS SA POSITION FIXE (position-indep
        # du sweep -> resolu 1x par cible). self TOUJOURS dans HealTargets -> son readiness compte aussi.
        self_ready = 0.5 if _has_valid_targets(ctx, ctx.uid) else 0.0
        allies = [(u.get("col"), u.get("row"), wf(u), _affected_by_heal_type(ctx, u, 1),
                   0.5 if _has_valid_targets(ctx, u.get("squadId")) else 0.0)
                  for u in obs if u.get("teamId") == team and not u.get("isDead")
                  and u.get("squadId") != ctx.uid and u.get("col") is not None]
        best = None  # (T, util)
        for T in _sweep_origin_first(ctx):   # ORIGINE d'abord : keep-first au tie -> reste en place (#76)
            adj = [(w, rep, rd) for c, r, w, rep, rd in allies
                   if bq.is_adjacent(T, (c, r), ctx.elev_by_pos, bq.neigh_map(ctx))]   # AdjacentUnits gate (#45/#76)
            # GATE GetEligibleTargetsEntities : >=1 cible REPARABLE (self ou adjacent) sinon ability non evaluee.
            if not (self_repairable or any(rep for _, rep, _ in adj)):
                continue
            # util = Σ [ (1 - healthPct) + 0.5×HasValidTargets ] sur self + adjacents (boucle HealTargets, #77).
            util = self_wound + self_ready + sum(w + rd for w, _, rd in adj)
            if best is None or util > best[1]:                       # strict > : 1er max garde
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] DefendTheDivineWork selfRepairable={self_repairable} "
                  f"selfReady={self_ready} best={best} min={self.MIN_UTILITY}", file=sys.stderr)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        T, util = best
        target = ctx.tile_id_by_pos.get(T, ctx.uid)                  # MainTile-id (self-cast AoE)
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": util}]


class RevitalizingMalignancyPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.RevitalizingMalignancyPlaybook$$EvaluateNonComparable` (NonComparable heal, id 1037 ;
    deathRotbone/Nauseous). Soin AoE self + adjacents, FILTRE non-Imperial ET non-Mecanique.

    - Ciblage `IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$GetAllHealTargets` = `Healable(UnitsWithoutTrait(0x1a=Imperial=26,
      Friends(AdjacentUnits(caster,r=1)) + self))` = self + amis adjacents qui sont NON-Imperial ET
      non-Mecanique (`Healable`). (Chaos ne soigne pas les Imperials ni les machines.)
    - util(T) = `Σ (1 - RemainingPercentage_health IdunBattle.Entities.Components.FillUpStatComponent$$RemainingPercentage)` sur ces cibles (= Σ missing/max). Meme
      formule que CombatRestoratives. MIN_UTILITY = `Fix64.FromIntFraction(9,10) = 0.9` (IdunBattle.AI.Playbook.Loki.RevitalizingMalignancyPlaybook$$.cctor).
      Sweep reach_nc, argmax STRICT ; self-cast (MainTile-id). PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170)."""
    ABILITY_ID = int(ActiveAbilityType.RevitalizingMalignancy)  # 1037
    MIN_UTILITY = 0.9      # IdunBattle.AI.Playbook.Loki.RevitalizingMalignancyPlaybook$$.cctor : Fix64.FromIntFraction(9,10)
    PRIORITY = 0

    @staticmethod
    def _healable(ctx: NCContext, u: dict) -> bool:
        """`Healable ∘ UnitsWithoutTrait(0x1a=Imperial)` (lu au decompile sur
        IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$GetAllHealTargets :
        `Healable(caster@0x160, UnitsWithoutTrait(Friends(AdjacentUnits) + self@0x148, 0x1a), 0)`) :
        non-Imperial (GrandAllianceId) ET `IsAffectedByHealType(u, 0)` — ce dernier via le mirror
        complet `_affected_by_heal_type` (0x421 + les trois traits d'IsMechanical), non plus le seul
        `Mechanical` du kit."""
        cfg = _unit_cfg(u.get("visualId"))
        return (cfg.get("GrandAllianceId") != "Imperial"
                and _affected_by_heal_type(ctx, u, 0))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        obs = ctx.obs_units or []
        me_obs = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        if me_obs is None:
            return []
        team = me_obs.get("teamId")
        wf = CombatRestorativesPlaybook._wound_fraction
        self_wound = wf(me_obs) if self._healable(ctx, me_obs) else 0.0   # self compte SSI Healable
        allies = [(u.get("col"), u.get("row"), wf(u)) for u in obs
                  if u.get("teamId") == team and not u.get("isDead")
                  and u.get("squadId") != ctx.uid and u.get("col") is not None
                  and self._healable(ctx, u)]
        best = None  # (T, util)
        for T in _sweep_origin_first(ctx):   # ORIGINE d'abord : keep-first au tie -> reste en place (#76)
            util = self_wound + sum(w for c, r, w in allies
                                    if bq.is_adjacent(T, (c, r), ctx.elev_by_pos, bq.neigh_map(ctx)))  # AdjacentUnits gate (#45/#76)
            if best is None or util > best[1]:
                best = (T, util)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        T, util = best
        target = ctx.tile_id_by_pos.get(T, ctx.uid)
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": util}]


def _active_ability_levels(ctx: NCContext) -> dict:
    """`{unitId: activeAbilityLevel}` — délègue à `ctx.active_levels()` (bound sur l'AiDecisionContext,
    combatSnapshot cache/rid). `{}` si non branché (harnais de sonde) -> level 0 = argmax trivial a UN
    seul candidat (le niveau ne départage QUE plusieurs allies en cooldown)."""
    f = getattr(ctx, "active_levels", None)
    return f() if callable(f) else {}


class InspiredToGreatnessPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.InspiredToGreatnessPlaybook$$EvaluateNonComparable` (NonComparable, id 0x43a=1082 ;
    tauAunShi/Kroot). Refresh l'ability d'un ALLIE (`IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$RepairOrHeal` = If(IsRepairable, Repair,
    Heal) + `InspiredToGreatness_OverrideLevelEffect`). Cible = l'ALLIE (unit-id), PAS une tuile.

    - Ciblage : `GetEligibleTargetsSelectable` (targeting `AActiveAbility`) filtre par
      `IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason` = cible != caster, PAS trait 0x7e7, ET
      (repairable | healable-blesse | ability-en-cooldown) [slots 0x11/0x12/0x31]. -> on delegue au jeu
      via `ctx.ability_targets(uid, 1082)` (VIDE si aucun allie blesse/reparable/en-cooldown -> pas d'action).
    - util(cible) : le natif prend l'ACTIVE ability de la cible (`ActiveAbilityComponent.GetActive`) ;
      SEULEMENT si `ActiveAbility.CanCurrentlyBeUsed == FALSE` (= EN COOLDOWN) -> util =
      `Fix64.FromInt(Level.ToZeroBasedIndex(AbilityState.Level))` = NIVEAU zero-based de cette ability.
      Les allies dont l'active est PRETE (usable) NE contribuent PAS. `Bucket.AddAction` argmax STRICT ->
      l'IA refresh l'ability EN COOLDOWN de plus HAUT NIVEAU.
    - MIN_UTILITY=0 (ctor `NonComparablePlaybook(0x43a)` IdunBattle.AI.Playbook.Loki.InspiredToGreatnessPlaybook$$.ctor, SANS min explicite). PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170).
    - Data offline : eligibilite = `abilityTargets` (jeu) ; cooldown = entree active de `dv.units[ally]
      .abilities` (`usable`) ; niveau = `combatSnapshot.unitConfig.activeAbilityLevel` (cfg+0xb8 ;
      `GetStat(18)`=null en snapshot -> via unitConfig). Le level ne departage QUE plusieurs allies en
      cooldown -> a UN seul candidat la cible est determinee sans lui. VALIDE LIVE (#78) : util=49 (level 50).
    - Eligibilite = `targets` (superset MOVE-inclus) : le natif BALAIE les tuiles de move et CASTE 1082 AVEC
      un move pour atteindre l'allie en cooldown quand il est hors portee in-place (VALIDE LIVE #78/#81).
    - POSITIONNEMENT move-to-reach (#81, PORTE + VALIDE LIVE via `castFromTiles`) : `to` = origine si l'allie
      est castable in-place (`currentValid`, origine-preference #76), sinon la 1re tuile de move LEGALE
      (`GetInvalidTargetReason(caster, tile, ally, 1082)` valide par tuile, ordre `GetMovableTilesFor`) ->
      MATCH EXACT natif (tauAunShi caste 1082 depuis (1,1) = port to=(1,1)). NB : le cas `currentValid=True`
      (origine castable) emet to=None par origine-preference #76 (self-cast confirme) ; NON separement crafte
      pour l'ally-target (le generateur keep-first-move-first pourrait BOUGER si des tuiles de move sont aussi
      legales -> a confirmer si un craft origine-castable apparait)."""
    ABILITY_ID = int(ActiveAbilityType.InspiredToGreatness)  # 1082
    MIN_UTILITY = 0.0     # ctor NonComparablePlaybook(0x43a) sans min -> 0
    PRIORITY = 0

    @staticmethod
    def _eligible_targets(at: dict) -> list:
        """Cibles alliees eligibles pour 1082 (le jeu a deja applique repairable/healable/on-cooldown).
        `targets` = superset MOVE-inclus (le natif balaie les tuiles de move pour atteindre l'allie ; cf.
        validation #78 ou le natif BOUGE pour caster). On prend ce superset pour l'ELIGIBILITE (ability+
        cible) ; la tuile de move exacte reste un raffinement de positionnement non porte."""
        out: list = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == InspiredToGreatnessPlaybook.ABILITY_ID:
                    src = a.get("targets") or []
                    out = [t.get("targetId") for t in src        # Tgt.targetId (PAS squadId)
                           if t.get("kind") == "unit" and t.get("targetId") is not None]
        return list(dict.fromkeys(out))

    @staticmethod
    def _active_ability(au: dict) -> dict | None:
        """`ActiveAbilityComponent.GetActive` : l'active NON-normale de l'unite (entree `kind` active/
        granted de `dv.units[i].abilities`)."""
        return next((ab for ab in (au.get("abilities") or [])
                     if ab.get("kind") in ("active", "granted")), None)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        eligible = self._eligible_targets(at)
        if not eligible:
            return []                                  # aucun allie eligible en portee -> pas d'action
        levels = _active_ability_levels(ctx)
        best = None  # (ally_id, level_zero_based)
        for ally_id in eligible:
            au = next((u for u in ctx.units if u.get("id") == ally_id), None)
            if au is None:
                continue
            active = self._active_ability(au)          # GetActive
            if active is None or active.get("usable") is not False:
                continue                               # requis : ability EN COOLDOWN (usable == False)
            lvl = max(0, int(levels.get(ally_id, 1)) - 1)   # ToZeroBasedIndex (activeAbilityLevel 1-based)
            if best is None or lvl > best[1]:          # argmax STRICT (keep-first au tie)
                best = (ally_id, lvl)
        if best is None:
            if ctx.debug:
                import sys
                print(f"    [dbg NC u{ctx.uid}] InspiredToGreatness eligible={eligible} best=None",
                      file=sys.stderr)
            return []
        ally_id, lvl = best
        # POSITIONNEMENT (#81) : cast SANS bouger si l'allie est castable in-place (origine-preference #76) ;
        # sinon la 1re tuile de move LEGALE (GetInvalidTargetReason par tuile via castFromTiles) -> le natif
        # BALAIE les tuiles de move et caste depuis la 1re d'ou l'allie est atteignable (keep-first).
        to = None
        cft_fn = getattr(ctx, "cast_from_tiles", None)
        if callable(cft_fn):
            cft = cft_fn(ctx.uid, ally_id, self.ABILITY_ID) or {}
            if not cft.get("currentValid"):
                mt = cft.get("moveTiles") or []
                if mt:
                    to = (mt[0].get("col"), mt[0].get("row"))
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] InspiredToGreatness eligible={eligible} best={best} to={to}",
                  file=sys.stderr)
        # Cible = l'ALLIE (unit-id) ; to = origine (in-place) ou 1re tuile de move legale (#81).
        return [{"target": ally_id, "ability": self.ABILITY_ID, "to": to, "pred": float(lvl)}]
