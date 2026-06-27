"""Port FIDÈLE de `IdunBattle.Core.Services.DamagePrediction` (gqfc5mff6c).

Chaque méthode = sa jumelle native (même nom, même logique), VA citée. Les ENTRÉES (stats
résolues, traits, config d'arme) viennent de `combatSnapshot` (one-shot) + gameconfig — pas de
black-box. La struct résultat mirror `DamagePredictionResult`.

⚠ Découverte mesurée (predict_validate.py) : la PRÉDICTION IA (`GetAllPredictions`/
`GetNormalAttackPrediction`/`GetAttackPrediction`, même cœur `PredictAttackRaw`) est PRÉ-ARMURE
pour l'attaque normale (dmg indépendant de l'armure cible ; `armorBefore=0`).

`PredictAttackRaw` @181032fb0 a été **RE LECTURE INTÉGRALE** (3037 lignes + 3 helpers scalaires
décompilés) — algorithme complet dans playbook-engine.md §16. Confirmé : l'armure est soustraite EN
AMONT (postArmor) ; `CalculateDamagePredictionScenario` ne soustrait PAS l'armure mais le
`previousHitsPrediction` (param_7, longtemps mal nommé `armor`). Restent à CALIBRER vs aiPredict (live
= confirmation) : le multiplicateur crit (§16.3 slots 0x10/0x11) et la source `perHitList`
(crit-chance par coup) — exposés comme hooks paramétrés ci-dessous.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .min_max_damage import MinMaxDamage
from .damage_calculations import spread_to_min_max
from .static_battle_rules import get_damage_with_piercing, get_piercing_ratio
from .damage_modifiers import DamageModifiers, apply_all_modifiers

# StatType (dump.cs @863349)
STAT_FIXED_ARMOR = 0x10        # 16
STAT_EXTRA_HITS = 0x11         # 17
STAT_EXTRA_PIERCE_MELEE = 0x15  # 21
STAT_EXTRA_PIERCE_RANGED = 0x16  # 22
STAT_EXTRA_HITS_MELEE = 0x17   # 23
STAT_EXTRA_PIERCE = 0x1a       # 26

# Traits référencés par la chaîne perçage/dégât (à confirmer noms exacts) :
TRAIT_HIT_TWICE = 0x3f5        # 1013 — cible : applique GetDamageWithPiercing 2× (cf. @181030d10)
TRAIT_PIERCE_1001 = 0x3e9      # 1001 — attaquant : bonus perçage LasCannon
TRAIT_PIERCE_1016 = 0x3f8      # 1016 — attaquant : bonus perçage LasCannon


@dataclass
class DamagePredictionResult:
    """struct DamagePredictionResult (offsets natifs lus via aiPredict) :
      CurrentHealth@0 · Armor@4 · Shield@8 · AccurateHealthDamage(MinMax)@0x58(Min0x60,Max0x64)
      · TotalDamage(MinMax)@0x88(Min0x90,Max0x94) · MightCrit@0xB1 · ForceOverkill@0xB2 ·
      AppliedHits@0xBC."""
    current_health: int = 0
    armor: int = 0
    shield: int = 0
    accurate_health_damage: MinMaxDamage = field(default_factory=MinMaxDamage)
    total_damage: MinMaxDamage = field(default_factory=MinMaxDamage)
    might_crit: bool = False
    applied_hits: int = 0


def get_default_attack_hits(base_hits: int, extra_hits: int,
                           extra_hits_melee: int, is_melee: bool) -> int:
    """DamagePrediction.GetDefaultAttackHits (@181032520) :
        hits = base + ExtraHits(17) + (melee ? ExtraHitsMelee(23) : 0) ; max(hits, 0)."""
    h = base_hits + extra_hits
    if is_melee:
        h += extra_hits_melee
    return max(h, 0)


def get_attack_piercing_damage_ratio(profile_piercing_ratio: int, profile_has_trait3: bool,
                                     attacker_extra_pierce: int, attacker_extra_pierce_dir: int,
                                     attacker_has_trait_1001_or_1016: bool,
                                     extra_pierce_min: int = 0, extra_pierce_max: int = 0,
                                     lascannon_bonus: int = 0) -> int:
    """DamagePrediction.GetAttackPiercingDamageRatio (@181030a20) :
        base = GetPiercingRatio(profile, attackerTraits)
        total = clamp(0,100, base + ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}
                              + extra_pierce_min + extra_pierce_max)
    (`extra_pierce_min/max` = bonus de perçage d'EFFET, params Fix64→int ; 0 en baseline.)"""
    base = get_piercing_ratio(profile_piercing_ratio, profile_has_trait3,
                              attacker_has_trait_1001_or_1016, lascannon_bonus)
    total = (base + attacker_extra_pierce + attacker_extra_pierce_dir
             + extra_pierce_min + extra_pierce_max)
    return max(0, min(100, total))


def get_base_damage_with_fixed_pierced_armor(
        damage: int, pierce_pct: int, target_fixed_armor: int,
        armor_penetration: int = 0, hit_multiplier: int = 1) -> int:
    """DamagePrediction.GetBaseDamageWithFixedPiercedArmor (@181030d10).

        armor_eff = max(target.FixedArmor(16) − armor_penetration, 0)
        d = damage
        repeat hit_multiplier fois : d = GetDamageWithPiercing(d, pierce_pct, armor_eff)
        return d
    hit_multiplier : 1 normalement ; 2 si la cible a le trait 1013 (TRAIT_HIT_TWICE) (et flag off) ;
    3 dans un cas d'ability triggered spéciale (0x4b6 + GetVariableForLevel 0x51) — non porté ici.
    (RÉSOLUTION armure/perçage. La prédiction IA pré-armure → l'orchestrateur passe armor=0.)"""
    armor_eff = max(target_fixed_armor - armor_penetration, 0)
    d = damage
    for _ in range(max(1, hit_multiplier)):
        d = get_damage_with_piercing(d, pierce_pct, armor_eff)
    return d


def calculate_damage_prediction_scenario(
        raw: MinMaxDamage, prev_hits: int = 0, profile_type: int = 0,
        shield_absorb_min: int = 0, shield_absorb_max: int = 0,
        reduction_min: int = 0, reduction_max: int = 0,
        remaining_health: int | None = None,
        trait_min_cap: int | None = None, result_cap: int | None = None,
        *, armor: int = 0) -> MinMaxDamage:
    """DamagePrediction.CalculateDamagePredictionScenario (@18102ed00) — UN outcome (1 coup × 1 état).
    Corps RE LECTURE INTÉGRALE (playbook-engine.md §16.2) :

        eff = max(0, raw − prev_hits)              # param_7 = previousHitsPrediction (PAS l'armure !)
        shieldAbs = absorbShield(eff)              # interface slot 0xb (FUN_1800068b0)
        health    = max(0, eff − shieldAbs)
        if cible.FillUpStatComponent : health = MaxReduceByMinimum(health, remaining_health)  # overkill
        MinMaxDamage.ApplyCap

    ⚠ CORRECTION RE : `param_7` natif = **previousHitsPrediction** (dégât cumulé des coups précédents),
    PAS l'armure (l'ancien code le nommait `armor` à tort — sans effet car la prédiction IA pré-armure
    passait 0). L'armure est soustraite EN AMONT (postArmor, §16.1.3), pas ici ; `armor` reste un knob
    optionnel kw-only (0 par défaut = prédiction IA pré-armure). `reduction_*` = réduction trigger cible
    (decisionView.effects ; 0 baseline). `remaining_health` (FillUpStat) = plafond overkill (None=off)."""
    eff_min = max(0, raw.min - prev_hits - armor)
    eff_max = max(0, raw.max - prev_hits - armor)
    m = max(0, eff_min - shield_absorb_min - reduction_min)
    big = max(0, eff_max - shield_absorb_max - reduction_max)
    if remaining_health is not None:
        # FillUpStatComponent.MaxReduceByMinimum : borne le dégât santé à la santé restante (overkill).
        m = min(m, remaining_health)
        big = min(big, remaining_health)
    if trait_min_cap is not None:
        # MaxReduceByMinimum (cap trait) : planche le dégât à trait_min_cap.
        m = max(m, trait_min_cap)
        big = max(big, trait_min_cap)
    out = MinMaxDamage(min=m, max=big, cap=result_cap)
    out.apply_cap()
    return out


def get_base_damage_fix64(base: int, extra_max: int = 0, spread_pct: int = 20,
                          is_max_out: bool = False) -> MinMaxDamage:
    """DamagePrediction.GetBaseDamageFix64 (@181030ba0) — la MinMax de base AVANT armure (local_938).
    RE (playbook-engine.md §16) :
        min = CalculateMinDamage(base) = base − CalculateDamageSpread(base)   # slot 8
        max = CalculateMaxDamage(base) + ExtraMaxDamage(stat 0x19=25)         # slot 9 + extraMax
    ⚠ ASYMÉTRIE : `ExtraMaxDamage` gonfle le BOUT HAUT seulement (stat attaquant). `is_max_out` (rare,
    trait force-max) → min = max = CalculateMaxDamage(base)+extraMax."""
    mm = spread_to_min_max(base, spread_pct)            # {base−spread, base+spread}
    hi = mm.max + extra_max
    lo = hi if is_max_out else mm.min
    return MinMaxDamage(min=lo, max=hi)


def get_attack_prediction(
        target_current_health: int, initial_damage: int, hits: int, profile_type: int,
        armor: int = 0, pierce_pct: int = 100, extra_max: int = 0,
        mods: DamageModifiers | None = None,
        hit_mult: int = 1, reduction_min: int = 0, reduction_max: int = 0,
        spread_pct: int = 20, might_crit: bool = False) -> DamagePredictionResult:
    """DamagePredictionQuery.GetAttackPrediction (slot 14) → `PredictAttackRaw` @181032fb0
    (RE LECTURE INTÉGRALE §16 + couche modifier tracée live §17). Prédiction d'UNE attaque (scorer).

    CHAÎNE FIDÈLE (RE + VALIDÉE live ; `DSLFactory.NormalAttackDamage`=`StatAmountFormula(Attack)`) :
      1. base = initial_damage  PAR COUP (= stat Attack de l'attaque normale). **PAS de modifier ici.**
      2. mm = GetBaseDamageFix64(base, extra_max)               # {base−spread, base+spread+ExtraMaxDamage}
      3. par BOUT : GetDamageWithPiercing(bout, pierce%, armor) répété `hit_mult`×  (GetBaseDamageWith-
         FixedPiercedArmor : max(max(0,bout−armure), bout×pierce%/100))
      3b. **MODIFIER post-perçage PAR BOUT** : apply_all_modifiers(bout, mods)       # ApplyCappedModifiers
         (RE §17.7 : dans `CalculateBaseDamageWithAllModifiers`@18102d3f0, le ×bonus est appliqué APRÈS
          le perçage/armure ; `mods`=DamageModifiers bâti depuis les EFFETS actifs de l'attaquant §17.8 ;
          None = aucun bonus → rétro-compat exacte). Preuve numérique : u94 +25% reproduit u94→u84 4524
          ET u94→u86 4518 à l'unité (placement-sur-base donnerait 5877/5880, faux).
      4. scenario (bouclier/réduction/overkill) PAR COUP, puis **× hits** (la boucle proba @2390 ajoute
         un event par coup ; crit=0 → coups identiques → Σ = hits × per-coup). `hits` = hits de l'ARME.

    VALIDÉ : 1-coup (u88 pierce1+armure, u92 pierce70) EXACT ; multi-coup u96 (3 hits) = base×3 ;
    buff u94 (RapidAssault +25%, mods) = oracle EXACT."""
    hits = max(1, hits)
    base = initial_damage                                       # 1. base PAR COUP (PAS de modifier ici)
    mm = get_base_damage_fix64(base, extra_max, spread_pct)     # 2. spread + extraMax (asymétrie haut)
    lo, hi = mm.min, mm.max                                     # 3. armure/perçage PAR BOUT (hit_mult×)
    pierce_eff, armor_eff = pierce_pct, armor                   # 3a. AXE ARMURE depuis mods (pré-perçage)
    if mods is not None:
        # CalculateBaseDamageWithAllModifiers @18102d3f0 : pierce-extra (@0x20) + pénétration (@0x28)
        # passés à GetBaseDamageWithFixedPiercedArmor → pierce_eff = clamp(pierce+extra,0,100) ;
        # armor_eff = max(FixedArmor−pénétration, 0) ; ignore-armure totale → armor_eff = 0.
        pierce_eff = max(0, min(100, pierce_pct + mods.extra_pierce))
        armor_eff = 0 if mods.ignore_armor else max(0, armor - mods.armor_penetration)
    for _ in range(max(1, hit_mult)):
        lo = get_damage_with_piercing(lo, pierce_eff, armor_eff)
        hi = get_damage_with_piercing(hi, pierce_eff, armor_eff)
    if mods is not None:                                        # 3b. MODIFIER scalaire post-perçage PAR BOUT
        lo = apply_all_modifiers(lo, mods)                      #     (ApplyCappedModifiers : %-list + additif)
        hi = apply_all_modifiers(hi, mods)
    per_hit = calculate_damage_prediction_scenario(            # 4. scenario PAR COUP
        MinMaxDamage(min=lo, max=hi), prev_hits=0, profile_type=profile_type,
        reduction_min=reduction_min, reduction_max=reduction_max)
    total = MinMaxDamage(min=per_hit.min * hits, max=per_hit.max * hits)   # Σ des `hits` events
    return DamagePredictionResult(
        current_health=target_current_health, armor=armor,
        accurate_health_damage=total, total_damage=total,
        applied_hits=hits, might_crit=might_crit)
