"""`IdunBattle.AI.Playbook.Loki.PsykerPlaybook` — face ATTACK des triggered (splash Psyker, #45-s18).

Consommé par la feuille `TriggeredAbilitiesUtility(2)` du composite Damage(34) (dispatcher face attack
`<EvaluateAttackInSteps>d__2 IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext` : itère les triggered de l'ATTAQUANT, `PlaybookDatabase.
LoadPlaybook`, Σ `ITriggeredAbilityPlaybook.CalculateAttackUtilityInSteps` vslot 3). Pendant ATTACK de
`adjacent_unit_preference.py` (face MOVE, case-36) — même protocole, autre vslot.

Corps `PsykerPlaybook.<CalculateAttackUtilityInStepsInternal>IdunBattle.AI.Playbook.Loki.PsykerPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` (RE intégral,
case-34 §MAJ #45quater) :

  1. GATES : `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$IsRegularAttack(case)` = l'ability du case est dans le set statique des
     attaques régulières (`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`) — mirror
     `ability_id in ctx.normal_ids` ; arme du case (slot 0xae = sélection d'arme vs cible) NON mêlée
     (`WeaponProfile.get_IsMelee` -> 0) et profil Psychic (`profile+0x10 == 0xd`) ; non supprimé
     (`IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$IsPsykerAttackSuppressed` = IsEffectTarget(CASTER, 1191) || IsEffectTarget(CIBLE
     du case, 1533)).
  2. AMOUNT : `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$GetAttackDamage` = `PercentageOf(StatAmount(Self,
     Attack, Current), Direct(GetNumberConstant(0xf)))` évalué vs le CASTER = `round_fix64(
     psykerExtraDmg% x GetStat(Attack))` — MÊME formule que la face runner (`triggers/loki/psyker.py`,
     validée bit-exact ; pct = `GC.trait("Psyker").variables.psykerExtraDmg` = 50).
  3. TARGETS : `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$PossibleTargets` = `Damageable(Enemies(caster, AdjacentUnits(CIBLE, 1)))`
     -> ennemis VIVANTS hex-adjacents à la cible du case (self/cible exclus) ; vide -> 0.
  4. PAR TARGET U : prédiction du montant vs U via l'interface query slot 0x23 =
     `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (amount, Nullable<profil 13>) -> hits FORCÉS 1,
     profil résolu, montant PRÉDÉFINI (`IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` boxe
     l'amount en Nullable<int> : canal predefined SANS spread ±20%, même famille que les
     additional-hits `RandomAmount`) -> le pipeline standard applique la COUCHE MODIFIERS complète.
     PROUVÉ 31337 s18 (u89 Njal -> u81, splash sur {u77, u79}) : base 402 (50% x attack 803)
     + LordOfTempests_ExtraDamage ADDITIF 1200 (= 400/hex x 3 hexes glacés ring-1 de la TUILE DU CASE
     (2,4)) = 1602 ; u79 custoBladeChampion -20% MartialKatah_DmgReduction -> 1282 (== splash EXÉCUTÉ
     sur u79, hp-diff exact) ; u77 admecMarshall sans réduction -> 1602. Les deux effets sont gatés
     `IsNormalAttack` côté port -> le splash EST traité normal-attack par la couche modifiers
     (`is_normal_attack=True`), mesure à l'appui.
  5. `ProbableDamageEvent(U, prediction)` -> `TriggeredAbilityPlaybook.CalculateUtilityFromDamageEvent`
     (composite Damage standard, hpmax EFFECTIF part-2) ; **u = Σ / Count(targets) (MOYENNE)** —
     `Fix64.op_Division` de sortie du SM. Validé : mean(u77(1602)=21.3896, u79(1282)=14.3181)
     = 17.85385 == L3 natif 17.85381752299145 (delta < 4e-5).
"""
from __future__ import annotations

from fractions import Fraction

import hexgeo
import gameconfig as GC

from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.formulas import _round_fix64
from ..entities.stats import ARMOR_STAT_TYPES
from ..entities.traits import target_hit_multiplier, TraitFactory
from ..entities.effects import calculate_attacker_modifiers_for_prediction
from ..services.battle_query import select_weapon_pierce
from ..services.damage_prediction import get_attack_prediction
from .probable_damage_event import ProbableDamageEvent, calculate_utility_from_damage_event

# Effets de suppression du splash (`IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$IsPsykerAttackSuppressed`) — noms captés (EffectType
# 1191 / 1533), lus sur les units decisionView (capture brute, indépendante de la factory d'effets).
_OWNER_SUPPRESS = "HuntersBeyondDeathPsykerSuppression"    # EffectType 1191, sur le CASTER
_TARGET_SUPPRESS = "WatchedOver_PsykerSuppression"         # EffectType 1533, sur la CIBLE du case


def _unit_has_effect(scene, uid: int, name: str) -> bool:
    u = next((x for x in (scene.units or []) if x.get("id") == uid), None)
    return any((e.get("name") == name) for e in ((u or {}).get("effects") or []))


class PsykerPlaybook:
    """`PsykerPlaybook` (`IdunBattle.AI.Playbook.Loki`) — playbook triggered de PsykerExtraAttack(1013).
    Seule la face ATTACK est portée (la face MOVE hérite du 0 de base `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateMovementUtilityInSteps`)."""

    ability_id: int = int(TriggeredAbilityType.PsykerExtraAttack)   # 1013

    # ---- mirror slot 0x23 : prédiction d'un MONTANT prédéfini vs U (pipeline modifiers complet) ----
    def _predict_amount_vs_target(self, scene, att_id: int, tgt_id: int, amount: int, attack_pos):
        """`IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (slot 0x23) -> `DamagePredictionQuery.
        IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` (amount en Nullable<int> = predefined, hits=1, profil Psychic
        résolu via `GetDamageProfile`). Pipeline = LE MÊME chemin amount que `generate_multi_hit_attack_
        prediction` : mods attaquant (builder IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction, additifs positionnels LordOfTempests inclus
        via `att_ctx.att_pos` = tuile du case) + mods défenseur par-cible + hit_mult MkXGravis + caps
        cibles ; spread 0 (canal predefined). `is_normal_attack=True` : mesuré (cf. docstring module)."""
        prof = GC.damage_profile("Psychic") or {}
        actx = scene.ctx(att_id)
        pierce = max(0, min(100, int(prof.get("PiercingRatio") or 0)
                            + actx.extra_pierce + actx.extra_pierce_ranged))
        from .prediction import prediction_has_moved, prediction_has_teleported
        _hm = prediction_has_moved(scene, att_id, attack_pos)
        _tctx = scene.ctx(tgt_id)
        _tar = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                if _tctx is not None and _tctx.stats is not None else None)
        mods = calculate_attacker_modifiers_for_prediction(
            scene.effects(att_id), is_ranged=True, has_moved=_hm, is_normal_attack=True,
            target_armor_reduced=_tar,
            att_ctx={"att_pos": attack_pos,
                     "tile_effects_by_pos": scene.tile_effects_by_pos,
                     "has_teleported": prediction_has_teleported(scene, att_id, attack_pos)})
        from .prediction import (_add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
                                 _target_damage_limits, _PROFILE_INDEX, _entity_traits)
        _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, False, attack_pos,
                                          scene.pos(tgt_id), damage_profile="Psychic",
                                          is_normal_attack=True)
        _apply_ally_attack_dmg_bonus(mods, scene, att_id, attack_pos, False, _tar, damage_profile="Psychic")
        # #267-r1 : MkXGravis lu sur l'ENTITE (`GetBaseDamageWithFixedPiercedArmor` ->
        # HasTrait(defender, 0x3f5)), MEME foyer que `_target_damage_limits` deux lignes plus bas.
        hit_mult = target_hit_multiplier(TraitFactory.create_many(_entity_traits(scene, tgt_id)))
        return get_attack_prediction(
            target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount), hits=1,
            profile_type=_PROFILE_INDEX.get("Psychic", 0), pierce_pct=pierce,
            armor=scene.armor(tgt_id), mods=mods, hit_mult=hit_mult, spread_pct=0,
            target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id),
            target_prevents_overkill=scene.prevents_overkill(tgt_id),   # #195 : HasFlag(cible, 0x13)
            attacker_effects=scene.effects(att_id),   # #202 : max-out evalue DANS predict_attack_raw
            attacker_ctx=actx)                        # #R34 : MightCrit = CouldCrit(attaquant)

    def possible_targets(self, scene, att_id: int, case_tgt_id: int) -> list[int]:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$PossibleTargets` = `Damageable(Enemies(caster, AdjacentUnits(CIBLE, 1)))` —
        ennemis du caster VIVANTS hex-adjacents à la cible du case (mirror du pool runner
        `_adjacent_damageable_enemies`, ici sur Scene). Adjacence GÉOMÉTRIQUE hex (evenq)."""
        my_team = scene.team(att_id)
        tpos = scene.pos(case_tgt_id)
        if tpos is None:
            return []
        out = []
        for u in (scene.units or []):
            u_id = u.get("id")
            if u_id in (att_id, case_tgt_id) or not u.get("alive"):
                continue
            if u.get("team") == my_team:
                continue
            p = scene.pos(u_id)
            if p is not None and hexgeo.distance(tpos, p) == 1:
                out.append(u_id)
        return out

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile) -> float:
        """Mirror `<CalculateAttackUtilityInStepsInternal>IdunBattle.AI.Playbook.Loki.PsykerPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` (cf. docstring
        module : gates -> amount -> targets -> prédiction/utilité par target -> MOYENNE)."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0
        # 1. IsRegularAttack(case) : l'ability évaluée est l'attaque NORMALE de l'unité.
        if int(ability_id) not in (ctx.normal_ids or ()):
            return 0.0
        actx = sc.ctx(attacker_uid)
        tpos = sc.pos(case_tgt_id)
        if actx is None or tpos is None:
            return 0.0
        # 2. arme du case : mêlée -> 0 ; profil != Psychic -> 0.
        d = hexgeo.distance(attack_tile, tpos)
        _p, is_ranged, _h, prof_name = select_weapon_pierce(actx, d <= 1, d)
        if not is_ranged or prof_name != "Psychic":
            return 0.0
        # 3. IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$IsPsykerAttackSuppressed (caster 1191 || cible du case 1533).
        if (_unit_has_effect(sc, attacker_uid, _OWNER_SUPPRESS)
                or _unit_has_effect(sc, case_tgt_id, _TARGET_SUPPRESS)):
            return 0.0
        # 4. amount = IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$GetAttackDamage (PercentageOf Fix64, mirror runner psyker_smite_tree).
        #    StatAmount(Attack, Current) = le stat DU PAS (`scene.attack_current`, refresh par-pas) —
        #    PAS le cold ctx.attack : l'aura RitesOfBattle (+1298 par adjacence Calgar) va et vient
        #    (vécu 31337 : cold 2101 vs 803 au s18 -> feuille 24.37 au lieu de 17.85).
        pct = int((GC.trait("Psyker") or {}).get("variables", {}).get("psykerExtraDmg") or 0)
        amount = int(_round_fix64(Fraction(pct * int(sc.attack_current(attacker_uid)), 100), 0))
        if amount <= 0:
            return 0.0
        # 5. targets adjacents damageables ; vide -> 0.
        targets = self.possible_targets(sc, attacker_uid, case_tgt_id)
        if not targets:
            return 0.0
        # 6. Σ CalculateUtilityFromDamageEvent / Count (MOYENNE, Fix64.op_Division de sortie).
        total = 0.0
        for u_id in targets:
            pred = self._predict_amount_vs_target(sc, attacker_uid, u_id, amount, attack_tile)
            ev = ProbableDamageEvent(target=u_id, prediction=pred)
            total += calculate_utility_from_damage_event(ev, ctx.wt,
                                                         (ctx.hpmax_by_id or {}).get(u_id))
        return total / len(targets)


# `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` (singleton par type) — face ATTACK. Seuls les types dont
# le playbook a un corps attack NON-trivial sont enregistrés (base `TriggeredAbilityPlaybook.
# CalculateAttackUtilityInSteps` yield 0) : absence == 0, même dégradation que le natif. ~60 playbooks
# triggered ont un corps attack non-trivial (case-34 §MAJ #45quater) — port à la demande (agreement).
from .aggressive_onslaught import AggressiveOnslaughtPlaybook   # #58 (registre, cf. module dedie)

TRIGGERED_ATTACK_PLAYBOOKS: dict[int, object] = {
    int(TriggeredAbilityType.PsykerExtraAttack): PsykerPlaybook(),
    # #58 : AggressiveOnslaught (1248) — summon d'attaque, valeur = min(free_adj(target), nrOfSummons-1)
    # x weight (AggressiveOnslaught_PerFreeTileAfterCharge=40). Corps IdunBattle.AI.Playbook.Loki.AggressiveOnslaughtPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext.
    int(TriggeredAbilityType.AggressiveOnslaught): AggressiveOnslaughtPlaybook(),
}


def load_attack_playbook(ability_id: int) -> PsykerPlaybook | None:
    """Mirror `PlaybookDatabase.LoadPlaybook` (attack-relevant uniquement). None -> le dispatcher skip
    (même chemin que le `if playbook == null: continue` natif)."""
    return TRIGGERED_ATTACK_PLAYBOOKS.get(int(ability_id))
