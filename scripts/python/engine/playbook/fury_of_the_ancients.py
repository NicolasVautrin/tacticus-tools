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
  (= `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage` = `DSLFormulas.RandomAmount(minDmg 0xc, maxDmg 0xd)`,
  ×mult rareté) évalué en MOYENNE par le slot 4 d'`IAmountFormula` = `IdunBattle.DSL.AAmountFormula$$CalculateAverage`
  — qui TRONQUE (#339, cf. `engine.dsl.base.calculate_average`), routé par le slot 0x23
  (`IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction`, cf. `psyker.py`) = **montant DONNÉ
  avg(min,max), hits FORCÉS 1, spread ±20 %** — probe_32d (matrice hits×canal) rendait delta ~1e-8
  vs les composites natifs pour les DEUX cibles ; hits=2/canal plage → ×2/off.
  ⚠ #449 — cette matrice ne discriminait PAS l'axe spread : re-jouée, elle rend le MÊME chiffre
  pour `avg0` et `avg20` (9.660285492973332 / 10.866318147871546, à 1e-15 près), parce que le
  composite Damage consomme `MinMaxDamage$$Avg` = la MOYENNE des deux bornes, et
  `avg(0,8·d, 1,2·d) == d`. Ce qu'elle a discriminé (canal plage vs moyenne, hits 1 vs 2) reste
  acquis ; le « spread 0 » n'y était PAS mesuré. La valeur juste est établie au décompilé
  (`DamagePredictionQuery$$GetAttackPrediction` écrit le littéral `1` à
  `DamagePredictionRequest+0x6a`, que `DamagePrediction$$PredictAttackRaw` teste pour router vers
  `DamagePrediction$$GetBaseDamageFix64`) et MESURÉE sur les deux autres lecteurs du même foyer
  (`psyker.py`, `avalanche_of_muscle.py` — probe_449). Le const
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
from ..entities.traits import target_hit_multiplier
from ..entities.traits.factory import TraitFactory
from ..entities.effects import calculate_attacker_modifiers_for_prediction
from ..entities.effects.magnitude import ability_var
from ..services.damage_prediction import get_attack_prediction
# #350-r3b : foyer UNIQUE des deux formes de moyenne de la couche TRIGGERED — la forme n'est plus
# choisie ici, elle est LUE dans `TRIGGERED_PREDICTION_AVERAGE_FORM` au symbole du call-site natif.
from ..entities.abilities.triggered_ability import triggered_prediction_damage
from .. import battle_query as bq
from .probable_damage_event import ProbableDamageEvent, calculate_utility_from_damage_event
from .prediction._shared import (
    _PROFILE_INDEX, _add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
    _entity_traits, _target_damage_limits
)
from .prediction._shared import prediction_has_moved, prediction_has_teleported
from .prediction._shared import _entity_rarity   # #1025-r1 (rarete de la CIBLE)

_ABILITY_NAME = "FuryOfTheAncients"


class FuryOfTheAncientsPlaybook:
    """Playbook triggered 1247 — face MOVE seule (la face ATTACK, observée L3 en mode attack,
    est un chemin distinct non porté : cf. case-32 « gap connexe »)."""

    ability_id: int = int(TriggeredAbilityType.FuryOfTheAncients)   # 0x4df = 1247

    # ---- mirror `IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction` ----------------------------------------------
    def _get_damage_prediction(self, scene, uid: int, tgt_id: int, attack_pos):
        """Prédiction du dégât Fury vs `tgt_id` depuis `attack_pos` (tuile du case) : montant
        DONNÉ = avg(minDmg,maxDmg)[niveau PASSIF × mult rareté], hits FORCÉS 1, spread ±20 %
        (slot 0x23 `BattleQuery.GetAttackPrediction`, mirror `psyker.py`) — routé par le MÊME
        pipeline modifiers/armure/bouclier que les prédictions d'attaque. probe_32d :
        delta ~1e-8 vs composites natifs ; les variantes hits=2 / canal plage sont OFF.
        Le spread est celui de #449 (cf. en-tête) : son axe n'était pas mesuré par probe_32d."""
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
        _hm = prediction_has_moved(scene, uid, attack_pos)
        _tctx = scene.ctx(tgt_id)
        _tar = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                if _tctx is not None and _tctx.stats is not None else None)
        mods = calculate_attacker_modifiers_for_prediction(
            scene.effects(uid), is_ranged=not is_melee, has_moved=_hm, is_normal_attack=False,
            target_armor_reduced=_tar,
            att_ctx={"att_pos": attack_pos, "tile_effects_by_pos": scene.tile_effects_by_pos,
                     "has_teleported": prediction_has_teleported(scene, uid, attack_pos),
                     # `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1, 1435) : aucun gate
                     # `IsNormalAttack` dans son trigger -> il entre AUSSI sur ce vecteur.
                     # MEMES CLES que la normale / les abilities / la face COMBAT.
                     "att_grand_alliance": (GC.unit(scene.vis_by_id.get(uid))
                                            or {}).get("GrandAllianceId"),
                     "damage_profile": prof_name,
                     "t_pos": scene.pos(tgt_id),
                     "tgt_team": scene.team(tgt_id),
                     # #1025-r1 -- `HasRarity(Target@<DSLSelectors+0x60>, idun.meta.Rarity
                     # .Mythic = 5)` + `AreFriends(Target@<DSLSelectors+0x60>, EffectSource(
                     # Effect@<DSLSelectors+0x38>))`, les deux conjoints utiles d'`Electrochaff
                     # Backups_DamageReductionPct` (1446). Son `$$CreateDamageModifier` ne porte
                     # NI `IsNormalAttack` NI `IsMeleeAttack` -> il entre AUSSI sur ce vecteur.
                     # MEMES cles que la normale et que la face COMBAT -- pas de fork. TRI-ETAT
                     # sur la rarete (`None` = non mesure -> gate FERME), cf. `_entity_rarity`.
                     "tgt_rarity": _entity_rarity(scene, tgt_id),
                     "team_by_id": scene.team_by_id})
        _add_positional_and_defender_mods(mods, scene, uid, tgt_id, is_melee, attack_pos,
                                          scene.pos(tgt_id), damage_profile=prof_name,
                                          is_normal_attack=False)
        _apply_ally_attack_dmg_bonus(mods, scene, uid, attack_pos, is_melee, _tar, damage_profile=prof_name)
        # #267-r1 : MkXGravis lu sur l'ENTITE (`GetBaseDamageWithFixedPiercedArmor` ->
        # HasTrait(defender, 0x3f5)), MEME foyer que `_target_damage_limits` deux lignes plus bas.
        hit_mult = target_hit_multiplier(TraitFactory.create_many(_entity_traits(scene, tgt_id)))
        # #339/#350-r3b -- `GetDamage` rend un noeud VALEUR a PLAGE, et la moyenne qu'on en prend
        # TRONQUE : `<Ability>$$GetDamage` (corps dedupe = `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage`)
        # = `IdunBattleLogic.Entities.DSLFormulas$$RandomAmount(minDmg 0xc, maxDmg 0xd)`, puis le
        # slot 4 d'`IAmountFormula` = `IdunBattle.DSL.AAmountFormula$$CalculateAverage`.
        # Ni `MinMaxDamage$$Avg` (#333) ni `BaseTriggeredAbility$$MinMaxDamageAverage` (l'AUTRE forme
        # de cette meme couche, demi-vers-le-pair) : les trois divergent des que `min + max` vaut
        # 3 mod 4. Le SLOT n'est plus code ici : il est lu au symbole du call-site natif.
        avg = triggered_prediction_damage(
            _ABILITY_NAME, lvl, mult,
            "IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction")
        if avg is None:
            return None
        return get_attack_prediction(
            target_current_health=scene.hp(tgt_id) or 0, initial_damage=avg,
            hits=1,                              # slot 0x23 : hits forcés 1 (probe_32d)
            profile_type=_PROFILE_INDEX.get(prof_name, 0), pierce_pct=pierce,
            # spread_pct : le DEFAUT (+/-20 %). #449 -- TROISIEME lecteur du MEME foyer
            # (`BattleQuery$$GetAttackPrediction` a montant -> `DamagePredictionQuery$$
            # GetAttackPrediction` -> `request+0x6a = 1` -> `GetBaseDamageFix64`). Corrige PAR
            # STRUCTURE : sa face est MOVE, et `ncPlaybookPredict` n'expose aucune voie MOVE --
            # ses bornes propres restent NON CONFRONTEES (residu `#449-r1`). Ce que la mesure
            # etablit, c'est que le canal qui l'avait << valide >> (composite, probe_32d
            # `avg0` vs `avg20`) rend le MEME chiffre a 1e-15 pres : il ne separait rien.
            armor=scene.armor(tgt_id), mods=mods, hit_mult=hit_mult,
            target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id),
            target_prevents_overkill=scene.prevents_overkill(tgt_id),   # #195 : HasFlag(cible, 0x13)
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
            if p is not None and bq.is_adjacent(tuple(e_pos), p, elev_by_pos, neigh_by_pos):
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
            if bq.is_adjacent(tuple(tile), (p["col"], p["row"]), elev, neigh):
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
