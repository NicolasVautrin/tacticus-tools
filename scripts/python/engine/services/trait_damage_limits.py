"""Port FIDÈLE de `IdunBattle.Core.Services.DamagePrediction.ApplyTraitDamageLimitsToDamage` @18102c650
et de ses 5 sous-limites (gqfc5mff6c). Chaque fonction = sa jumelle native (même nom homonyme, VA citée).

CONTEXTE (RE) : dans `PredictAttackRaw`, le rawMM per-coup (après perçage/armure/modifiers, =
`CalculateBaseDamageWithAllModifiers`) est passé à **`ApplyTraitDamageLimitsToDamage` @0x1810359c7**
qui le MODIFIE IN-PLACE **avant** la boucle multi-coups. Le port historique (`damage_prediction.py`)
SAUTAIT entièrement cette étape → trou. Ces limites sont surtout no-op pour un héros nu, mais comptent
pour : cibles multi-membres (member-cap), trait Resilient (1009), trait Impervious (28), boss
(BossEndFightUndefeated 1492).

⚠ Le dégât est un int (borne min ou max), traité séparément (le natif appelle chaque Apply 2× : une
fois sur *param_3=min, une fois sur *param_4=max). Ici on opère sur UNE borne (int) ; l'appelant boucle.
"""
from __future__ import annotations

import math

# Trait / ability ids (hex natifs)
TRAIT_RESILIENT = 0x3f1           # 1009
TRAIT_IMPERVIOUS = 0x1c           # 28
PROFILE_TRAIT_HITS_MULTIPLE_MEMBERS = 2   # DamageProfile.HasTrait(2) — Blast : skip member-cap
ABILITY_BOSS_END_FIGHT_UNDEFEATED = 0x5d4  # 1492 (triggered) — cap boss "invaincu jusqu'a fin du fight"
BOSS_CAP_CONSTANT_INDEX = 0x12    # 18 — GetNumberConstant de l'ability 1492


def get_group_unit_max_health_with_remaining_members(total_hp: int, member_count: int,
                                                     remaining: int) -> int:
    """DamageCalculations.GetGroupUnitMaxHealthWithRemainingMembers @1810050a0 : somme des PV des
    `remaining` premiers membres, PV repartis (total_hp / member_count, +1 pour les premiers restes)."""
    acc = 0
    if remaining <= 0:
        return 0
    for i in range(remaining):
        if i < member_count:
            per = total_hp // member_count
            if i < total_hp - per * member_count:   # reste de la division reparti sur les 1ers membres
                per += 1
        else:
            per = 0
        acc += per
    return acc


def get_group_unit_remaining_member_count(total_hp: int, member_count: int, damage: int) -> int:
    """DamageCalculations.GetGroupUnitRemainingMemberCount @181005120 : nb de membres SURVIVANTS apres
    `damage` (retire des membres tant que la somme de leurs PV <= damage)."""
    m = member_count
    while m >= 1:
        acc = 0
        for i in range(m - 1):
            if i < member_count:
                per = total_hp // member_count
                if i < total_hp - per * member_count:
                    per += 1
            else:
                per = 0
            acc += per
        if acc < damage:
            break
        m -= 1
    else:
        return 0
    return m


def apply_group_unit_damage_limit(dmg: int, profile_has_hits_multiple_members: bool,
                                  member_count: int, member_total_hp: int,
                                  cumulative_damage: int, flag: bool = False) -> int:
    """DamagePrediction.ApplyGroupUnitDamageLimit @18102bfe0 : cape le degat a la frontiere de membre
    pour une cible MULTI-MEMBRE. Skip si le profil a HitsMultipleMembers (trait 2 = Blast). No-op si
    `member_count <= 1` (heros). `cumulative_damage` = param_5."""
    if member_count <= 1:
        return dmg
    if profile_has_hits_multiple_members:   # HasTrait(profile, 2) -> return (pas de member-cap pour Blast)
        return dmg
    if flag:
        return dmg
    remaining = get_group_unit_remaining_member_count(member_total_hp, member_count, cumulative_damage)
    if remaining > 1:
        cap_health = get_group_unit_max_health_with_remaining_members(
            member_total_hp, member_count, remaining - 1)
        limit = cumulative_damage - cap_health
        if dmg > limit:
            dmg = limit
    return dmg


def apply_resilient_trait_damage_limit(dmg: int, target_has_resilient: bool,
                                       current_health: int, max_health: int,
                                       overkill: bool = False) -> int:
    """DamagePrediction.ApplyResilientTraitDamageLimit @18102c3a0 : trait Resilient (0x3f1=1009). Si la
    cible a Resilient ET max_health(param_5) > 1 ET current_health(param_4) > 0 ET PAS overkill : cape le
    degat a `current_health - 1` (ne peut pas one-shot ; laisse 1 PV). (param_4=param_9=currentHealth,
    param_5=param_11=maxHealth, param_6=flag overkill.)"""
    if not overkill:
        if target_has_resilient and max_health > 1 and current_health > 0:
            cap = current_health - 1
            if dmg > cap:
                return cap
    return dmg


def apply_impervious_trait_damage_limit(dmg: int, target_has_impervious: bool,
                                        impervious_stat_current: int | None,
                                        param_6: int, param_7: int) -> int:
    """DamagePrediction.ApplyImperviousTraitDamageLimit @18102c190 : trait Impervious (0x1c=28). Lit un
    StatComponent (charge Impervious) : si absent -> pas de cible valide ; CurrentValue < 1 OU < 100 ->
    degat = 0 (bloque) ; sinon degat = param_6 + param_7. (`impervious_stat_current` = None -> pas
    d'Impervious sur cette cible -> no-op.)"""
    if not target_has_impervious or impervious_stat_current is None:
        return dmg
    if impervious_stat_current < 1 or impervious_stat_current < 100:
        return 0
    return param_6 + param_7


def is_overkill(current_health: int, damage: int, default_flag: int,
                allow_flag: int, suppress: int, cond: int, threshold_pct: int) -> int:
    """DamagePrediction.IsOverkill @181032db0 : le degat depasse-t-il la sante d'un ratio > seuil ?
    (param_1=currentHealth, param_2=damage, param_7=threshold%). Simplifie : renvoie 1 si overkill
    au-dela du seuil, sinon default/0. (Gate `cond`=param_6 ; `suppress`=param_5.)"""
    if not cond:
        return 0
    if damage >= current_health:
        if allow_flag:
            return 1
    if not suppress and current_health > 0:
        pct = int((damage - current_health) / current_health * 100)
        if damage >= current_health:
            return default_flag if pct < threshold_pct else 1
    return 0


def apply_trait_damage_limits_to_damage(
        dmg: int, *, is_special: int = 1,
        target_has_resilient: bool = False, target_has_impervious: bool = False,
        impervious_stat_current: int | None = None,
        member_count: int = 1, member_total_hp: int = 0,
        profile_has_hits_multiple_members: bool = False,
        current_health: int = 0, max_health: int = 0,
        target_has_boss_cap: bool = False, boss_cap_const: int = 0,
        cumulative_damage: int | None = None, overkill: bool = False) -> int:
    """DamagePrediction.ApplyTraitDamageLimitsToDamage @18102c650 — orchestre les 5 limites sur UNE borne
    de degat (int). Ordre natif :
      1. ApplyGroupUnitDamageLimit (member-cap)         @18102bfe0
      2. ApplyResilientTraitDamageLimit (Resilient)     @18102c3a0
      3. si is_special==1 : ApplyImperviousTraitDamageLimit @18102c190
      4. si HasTriggeredAbility(0x5d4=1492) : cap boss  = Min(dmg, param_9 - maxHealth*const/100)
    `cumulative_damage` (param_5 member-cap / param_9 boss) defaut = current_health si None."""
    cum = current_health if cumulative_damage is None else cumulative_damage
    # 1. member-cap
    dmg = apply_group_unit_damage_limit(
        dmg, profile_has_hits_multiple_members, member_count, member_total_hp, cum, overkill)
    # 2. Resilient
    dmg = apply_resilient_trait_damage_limit(
        dmg, target_has_resilient, current_health, max_health, overkill)
    # 3. Impervious (seulement chemin special is_special==1)
    if is_special == 1:
        dmg = apply_impervious_trait_damage_limit(
            dmg, target_has_impervious, impervious_stat_current, current_health, 0)
    # 4. cap BossEndFightUndefeated (0x5d4=1492)
    if target_has_boss_cap:
        # uVar3 = Max(param_9 - maxHealth * const/100, 0) ; dmg = Min(dmg, uVar3)
        cap = max(cum - int(math.floor(max_health * boss_cap_const / 100.0)), 0)
        if dmg > cap:
            dmg = cap
    return dmg
