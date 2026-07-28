"""`IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook` — face MOVE du passif Fury (bloodMephiston).

Consommé par la feuille `TriggeredAbilitiesUtility(2)` du composite Tile(7) (dispatcher move
`<EvaluateMovementInSteps>d__2 IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` → `PlaybookDatabase.LoadPlaybook(1247)`). Case #32
(31337 s5) : ce terme manquant (20.5266 à (3,5)) flippait le cast-tile de l'attaque de Mephiston.

Corps `<CalculateMovementUtilityInStepsInternal>IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` (IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$.ctor,
TriggeredAbilityType 0x4df=1247) — RE re-expert #32, réconcilié EXACT :

    enemies = ennemis ADJACENTS à la tuile candidate (query playerId du case.unit ; gate
              élévation |Δelev|<2 d'`IterateAdjacentTiles` — `bq.is_adjacent`)
    vide -> yield 0
    N = count ; prob = Fix64(1/N)
    total = Σ_E [ GDU(E, 1/N) + (second(E) ? GDU(second(E), 1/N) : 0) ]     # MÊME prob 1/N

- `IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagedEnemyUtility` (GDU) : `ProbableDamageEvent(target, GetDamagePrediction,
  probability1=prob)` → `TriggeredAbilityPlaybook<T>.IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent`
  = prob1 × prob2(=1) × composite Damage — primitive portée `calculate_utility_from_damage_event`.
- second(E) : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryOfTheAncientsAbility$$GetSecondTargetSelector` = `Friends(AdjacentUnits(E, r=1))` (alliés de E
  = les AUTRES ennemis du caster, self-exclu) → `IdunBattle.DSL.TargetsSelector$$SelectUnit(…, 3)` = PREMIER vivant
  ciblable (`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType(u,3)`) en ordre d'énumération des tuiles
  adjacentes de E → itération `neigh_by_pos[E]` (ordre voisins natif), fallback ordre `enemies`.
- `IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction` : niveau PASSIF du caster (`GetAbilityState`) → `GetDamage`
  (`MinMaxDamage` = minDmg/maxDmg[lvl] × mult rareté) évalué en MOYENNE, routé par le slot 0x23
  (`IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction`, cf. `psyker.py`) = **montant PRÉDÉFINI
  avg(min,max), hits FORCÉS 1, spread 0** — PROUVÉ probe_32d (matrice hits×canal) : delta ~1e-8
  vs les composites natifs pour les DEUX cibles ; hits=2/canal plage → ×2/off. Le const
  `nrOfHits`=2 (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryOfTheAncientsAbility$$GetAttackHits`) concerne l'EXÉCUTION du trigger, pas cette prédiction.
  Profil `GetDamageProfileOrDefault(0xd)` = Psychic (pierce 100) ; pipeline modifiers/armure/
  bouclier/caps COMPLET vs cible, tuile caster du case (mods positionnels).

Réconciliation (31337 s5, u81 bloodMephiston lvl passif 50 mult 180 → per-hit [599,797] avg 698 ;
tuile (3,5) elev2 ; ennemis adjacents {91,95} mutuellement adjacents → le ×2 du second-target
annule le 1/N) : `composite(Fury→91)=9.660285501740873 + composite(Fury→95)=10.866318154148757
= 20.52660365588963` = la feuille L3 native EXACTE ; 0 à (3,6)/(4,5)/(5,5) (aucun ennemi
adjacent).
"""
from __future__ import annotations

import gameconfig as GC

from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.stats import ARMOR_STAT_TYPES
from ..entities.traits import target_hit_multiplier, TraitFactory
from ..entities.effects import calculate_attacker_modifiers_for_prediction
from ..entities.effects.magnitude import ability_var
from ..services.damage_prediction import get_attack_prediction
from .. import battle_query as bq
from .probable_damage_event import ProbableDamageEvent, calculate_utility_from_damage_event

_ABILITY_NAME = "FuryOfTheAncients"


class FuryOfTheAncientsPlaybook:
    """Playbook triggered 1247 — face MOVE seule (la face ATTACK, observée L3 en mode attack,
    est un chemin distinct non porté : cf. case-32 « gap connexe »)."""

    ability_id: int = int(TriggeredAbilityType.FuryOfTheAncients)   # 0x4df = 1247

    # ---- mirror `IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction` ----------------------------------------------
    def _get_damage_prediction(self, scene, uid: int, tgt_id: int, attack_pos):
        """Prédiction du dégât Fury vs `tgt_id` depuis `attack_pos` (tuile du case) : montant
        PRÉDÉFINI = avg(minDmg,maxDmg)[niveau PASSIF × mult rareté], hits FORCÉS 1, spread 0
        (slot 0x23 `BattleQuery.GetAttackPrediction`, mirror `psyker.py`) — routé par le MÊME
        pipeline modifiers/armure/bouclier que les prédictions d'attaque. PROUVÉ probe_32d :
        delta ~1e-8 vs composites natifs ; les variantes hits=2 / canal plage sont OFF."""
        lvl = (scene.ablvl_by_id or {}).get(uid)
        mult = int((scene.mult_by_id or {}).get(uid) or 100)
        dmin = ability_var(_ABILITY_NAME, "minDmg", lvl, multiplier_pct=mult)
        dmax = ability_var(_ABILITY_NAME, "maxDmg", lvl, multiplier_pct=mult)
        if not dmin or not dmax:
            return None
        a = GC.ability(_ABILITY_NAME) or {}
        consts = a.get("constants") or {}
        prof_name = consts.get("damageProfile") or "Psychic"         # GetDamageProfileOrDefault(0xd)
        prof = GC.damage_profile(prof_name) or {}
        is_melee = (a.get("attackRangeType") or "").lower() == "melee"
        actx = scene.ctx(uid)
        if actx is None:
            return None
        dir_pierce = actx.extra_pierce_melee if is_melee else actx.extra_pierce_ranged
        pierce = max(0, min(100, int(prof.get("PiercingRatio") or 0)
                            + actx.extra_pierce + dir_pierce))
        _hm = attack_pos != scene.pos(uid)
        _tctx = scene.ctx(tgt_id)
        _tar = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                if _tctx is not None and _tctx.stats is not None else None)
        mods = calculate_attacker_modifiers_for_prediction(
            scene.effects(uid), is_ranged=not is_melee, has_moved=_hm, is_normal_attack=False,
            target_armor_reduced=_tar,
            att_ctx={"att_pos": attack_pos, "tile_effects_by_pos": scene.tile_effects_by_pos})
        from .prediction import (_add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
                                 _target_damage_limits, _PROFILE_INDEX)
        _add_positional_and_defender_mods(mods, scene, uid, tgt_id, is_melee, attack_pos,
                                          scene.pos(tgt_id), damage_profile=prof_name,
                                          is_normal_attack=False)
        _apply_ally_attack_dmg_bonus(mods, scene, uid, attack_pos, is_melee, _tar, damage_profile=prof_name)
        hit_mult = target_hit_multiplier(TraitFactory.create_many(
            (GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits")))
        avg = (int(dmin) + int(dmax)) // 2       # MinMaxDamage avgFlag (somme paire ici : 599+797)
        return get_attack_prediction(
            target_current_health=scene.hp(tgt_id) or 0, initial_damage=avg,
            hits=1,                              # slot 0x23 : hits forcés 1 (probe_32d)
            profile_type=_PROFILE_INDEX.get(prof_name, 0), pierce_pct=pierce,
            armor=scene.armor(tgt_id), mods=mods, hit_mult=hit_mult, spread_pct=0,
            target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id),
            attacker_effects=scene.effects(uid),   # #202 : max-out evalue DANS predict_attack_raw
            attacker_ctx=actx)                     # #R34 : MightCrit = CouldCrit(attaquant)

    # ---- mirror `IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagedEnemyUtility` -------------------------------------------
    def _damaged_enemy_utility(self, scene, uid: int, tgt_id: int, tile, prob: float,
                               hpmax_by_id: dict, wt) -> float:
        pred = self._get_damage_prediction(scene, uid, tgt_id, tile)
        if pred is None:
            return 0.0
        ev = ProbableDamageEvent(target=tgt_id, prediction=pred, probability1=prob)
        return calculate_utility_from_damage_event(ev, wt, (hpmax_by_id or {}).get(tgt_id))

    # ---- mirror second(E) : `Friends(AdjacentUnits(E))` + `SelectUnit(…, 3)` ------------------
    def _second_target(self, e_pos, e_id: int, enemies: list, elev_by_pos, neigh_by_pos) -> int | None:
        """PREMIER autre ennemi (du caster) VIVANT adjacent à E — ordre = voisins natifs de la
        tuile de E (`neigh_by_pos`), fallback ordre de la liste `enemies` (liant seulement si E a
        >= 2 ennemis adjacents — flag spec re-expert, à trancher sur un cas multi-adjacent)."""
        epos_by_id = {}
        for u in enemies:
            p = u.get("pos") or {}
            if p.get("col") is not None:
                epos_by_id[u.get("id")] = (p["col"], p["row"])
        neigh = (neigh_by_pos or {}).get(tuple(e_pos)) or ()
        if neigh:
            unit_at = {pos: uid_ for uid_, pos in epos_by_id.items()}
            for npos in neigh:
                cand = unit_at.get(tuple(npos))
                if cand is not None and cand != e_id:
                    return cand
        for u in enemies:                                        # fallback : ordre liste
            uid_ = u.get("id")
            if uid_ == e_id:
                continue
            p = epos_by_id.get(uid_)
            if p is not None and bq.is_adjacent(tuple(e_pos), p, elev_by_pos):
                return uid_
        return None

    # ---- mirror `<CalculateMovementUtilityInStepsInternal>IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` -----------
    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        scene = (ctx or {}).get("scene")
        uid = (ctx or {}).get("uid")
        enemies = (ctx or {}).get("enemies") or []
        elev = (ctx or {}).get("elev_by_pos")
        hpmax = (ctx or {}).get("hpmax_by_id") or {}
        neigh = (ctx or {}).get("neigh_by_pos")
        if scene is None or uid is None or not enemies:
            return 0.0
        adj = []
        for u in enemies:
            p = u.get("pos") or {}
            if p.get("col") is None:
                continue
            if bq.is_adjacent(tuple(tile), (p["col"], p["row"]), elev):
                adj.append((u.get("id"), (p["col"], p["row"])))
        if not adj:
            return 0.0                                           # collection vide -> yield Fix64(0)
        prob = 1.0 / len(adj)
        total = 0.0
        for e_id, e_pos in adj:
            total += self._damaged_enemy_utility(scene, uid, e_id, tile, prob, hpmax, wt)
            second = self._second_target(e_pos, e_id, enemies, elev, neigh)
            if second is not None:
                total += self._damaged_enemy_utility(scene, uid, second, tile, prob, hpmax, wt)
        return total
