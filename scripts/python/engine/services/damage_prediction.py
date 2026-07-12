"""Port FIDÈLE de `IdunBattle.Core.Services.DamagePrediction` (gqfc5mff6c).

Chaque méthode = sa jumelle native (même nom, même logique), VA citée. Les ENTRÉES (stats
résolues, traits, config d'arme) viennent de `combatSnapshot` (one-shot) + gameconfig — pas de
black-box. La struct résultat mirror `DamagePredictionResult`.

⚠ Découverte mesurée (predict_validate.py) : la PRÉDICTION IA (`GetAllPredictions`/
`GetNormalAttackPrediction`/`GetAttackPrediction`, même cœur `PredictAttackRaw`) est PRÉ-ARMURE
pour l'attaque normale (dmg indépendant de l'armure cible ; `armorBefore=0`).

STRUCTURE (calquée 1:1 sur le natif — le `×hits` N'est PAS dans PredictAttackRaw) :
  - `predict_attack_raw`            = `DamagePrediction.PredictAttackRaw @181032fb0`  (UN COUP, prev-aware)
  - `get_multi_hit_attack_prediction` = `BattleQuery.GetMultiHitAttackPrediction @181066080`  (LA boucle)
  - `DamagePredictionResult.add`     = `DamagePredictionResult.Add @18102a710`  (Σ des coups)
  - `.default_block_scenario`        = `get_DefaultBlockScenario @18102bcd0`  (prev cumulé threadé)
  - `get_attack_prediction`          = entrée attaque NORMALE (whole-attack) → route par la boucle.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .min_max_damage import MinMaxDamage
from .damage_calculations import spread_to_min_max
from .static_battle_rules import get_damage_with_piercing, get_piercing_ratio
from .damage_modifiers import (
    DamageModifiers, apply_all_modifiers, apply_capped_modifiers, capped_reduction_flat,
)
from .trait_damage_limits import apply_trait_damage_limits_to_damage, compute_prediction_overkill

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
    """struct DamagePredictionResult (dump.cs TypeDefIndex 11757, offsets STRUCT) :
      CurrentHealth@0 · CurrentArmor@4 · CurrentShield@8 · healthDmg(RAW min@0x24/max@0x28,
      NON capé par HP — utilisé par get_WillBeKill @18102bef0 / WillBeOverkill @18102ba40) ·
      AccurateHealthDamage(MinMax)@0x58 (Min@+8=0x60, Max@+0xc=0x64, CAPÉ par HP santé restante)
      · AccurateArmorDamage@0x68 · AccurateShieldDamage@0x78 · TotalDamage@0x88 · LimitedByMinHp@0xB0
      · MightCrit@0xB1 · ForceOverkill@0xB2 · AppliedHits@0xBC.
    SPLIT santé/bouclier (PredictAttackRaw, call-sites VA 0x181034caa/0x181034ce7) :
      shieldDmg = CalculateDamageBlockedByShield @181002850 = Min(dmg, shieldRestant) PAR BORNE ;
      healthDmg = dmg − shieldDmg. Le bouclier absorbe le dégât FINAL (post-armure/modifiers).
    ⚠ DEUX représentations du dégât santé (le natif les DISTINGUE) : `raw_health_damage` (@0x24/@0x28,
      NON capé par la santé restante) sert le test de KILL/OVERKILL (l'écrasement `min(dmg,HP)` détruirait
      l'info d'over-shoot) ; `accurate_health_damage` (@0x58, CAPÉ) sert `DamageDealt` (satu à HP). Le port
      historique les confondait (une seule valeur capée) -> `OverkillUnit` INERTE (#84)."""
    current_health: int = 0
    armor: int = 0
    shield: int = 0
    accurate_health_damage: MinMaxDamage = field(default_factory=MinMaxDamage)
    raw_health_damage: MinMaxDamage = field(default_factory=MinMaxDamage)   # @0x24/@0x28 NON capé HP (kill/overkill)
    accurate_shield_damage: MinMaxDamage = field(default_factory=MinMaxDamage)
    total_damage: MinMaxDamage = field(default_factory=MinMaxDamage)
    limited_by_min_hp: bool = False
    might_crit: bool = False
    force_overkill: bool = False   # ForceOverkill @0xB2 (trait force-overkill ; défaut False, non porté baseline)
    applied_hits: int = 0

    def default_block_scenario(self) -> "BlockScenario":
        """`DamagePredictionResult.get_DefaultBlockScenario` @18102bcd0 — le scénario cumulé (dégât santé/
        bouclier déjà infligé) threadé comme `prev` au coup suivant → ressources RESTANTES de la cible."""
        return BlockScenario(
            health_min=self.accurate_health_damage.min, health_max=self.accurate_health_damage.max,
            shield_min=self.accurate_shield_damage.min, shield_max=self.accurate_shield_damage.max)

    def add(self, other: "DamagePredictionResult") -> None:
        """`DamagePredictionResult.Add` @18102a710 — somme ENTIÈRE champ-par-champ (Accurate* santé/bouclier
        + Total + AppliedHits) avec ApplyCap. MUTE self (agrège le coup `other` de la boucle multi-coups)."""
        h = MinMaxDamage(min=self.accurate_health_damage.min + other.accurate_health_damage.min,
                         max=self.accurate_health_damage.max + other.accurate_health_damage.max,
                         cap=self.accurate_health_damage.cap)
        h.apply_cap()
        self.accurate_health_damage = h
        # raw @0x24/@0x28 : somme NON capée par HP (l'over-shoot cumulé des coups = base du flag overkill)
        rh = MinMaxDamage(min=self.raw_health_damage.min + other.raw_health_damage.min,
                          max=self.raw_health_damage.max + other.raw_health_damage.max,
                          cap=self.raw_health_damage.cap)
        rh.apply_cap()
        self.raw_health_damage = rh
        s = MinMaxDamage(min=self.accurate_shield_damage.min + other.accurate_shield_damage.min,
                         max=self.accurate_shield_damage.max + other.accurate_shield_damage.max,
                         cap=self.accurate_shield_damage.cap)
        s.apply_cap()
        self.accurate_shield_damage = s
        t = MinMaxDamage(min=self.total_damage.min + other.total_damage.min,
                         max=self.total_damage.max + other.total_damage.max, cap=self.total_damage.cap)
        t.apply_cap()
        self.total_damage = t
        self.applied_hits += other.applied_hits
        self.might_crit = self.might_crit or other.might_crit


@dataclass
class BlockScenario:
    """Scénario cumulé threadé comme `prev` entre coups — `get_DefaultBlockScenario` @18102bcd0. Porte le
    dégât CUMULÉ (santé/bouclier) des coups précédents → RESSOURCES RESTANTES de la cible au coup suivant
    (`rem = pleine − cumul`). Champs natifs consommés par `PredictAttackRaw` (prev = Nullable@param_3+0x84) :
    healthDmg@+0x08 (rem_HP @181034087), shieldAbs min@+0x28 / max@+0x2c (rem_shield @1810341d5/427a).
    (armorDmg@+0x18 non threadé ici — armure=0 en prédiction IA.) Vide (tout 0) = 1er coup = pleines."""
    health_min: int = 0
    health_max: int = 0
    shield_min: int = 0
    shield_max: int = 0


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

        eff = max(0, raw − prev_hits)              # param_7 = BONUS CRIT du scénario courant (intra-coup)
        shieldAbs = absorbShield(eff)              # interface slot 0xb (FUN_1800068b0)
        health    = max(0, eff − shieldAbs)
        if cible.FillUpStatComponent : health = MaxReduceByMinimum(health, remaining_health)  # overkill
        MinMaxDamage.ApplyCap

    ⚠ CORRECTION RE (verdict prev-threading @181035dce) : `param_7` natif = le **bonus du scénario de crit
    COURANT** (répartition crit/non-crit d'UN hit), PAS un cumul inter-coups. La déplétion inter-coups
    (bouclier/HP restant) se fait EN AMONT dans `predict_attack_raw` sur les ressources restantes, PAS via
    `prev_hits` ici. `armor` = knob kw-only (0 = prédiction IA pré-armure). `reduction_*` = réduction
    trigger cible (decisionView.effects ; 0 baseline). `remaining_health` (FillUpStat) = plafond overkill."""
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


def apply_pierce_and_modifiers(value: int, pierce_pct: int = 100, armor: int = 0,
                               mods: DamageModifiers | None = None, hit_mult: int = 1,
                               attacker_additive_pre: bool = False) -> int:
    """BASE COMMUNE prédiction↔combat — réduction d'UNE valeur de dégât (= étape 3+3b de
    `predict_attack_raw`, cf. `CalculateBaseDamageWithAllModifiers` @18102d3f0) :
        pierce_eff = clamp(0,100, pierce + mods.extra_pierce)
        armor_eff  = 0 si mods.ignore_armor sinon max(0, armor − mods.armor_penetration)
        d = GetDamageWithPiercing(value, pierce_eff, armor_eff) répété hit_mult×
        d = ApplyAllModifiers(d, mods)        # ×bonus post-perçage §17.7
    La PRÉDICTION l'applique à ses 2 bornes (min,max) ; le COMBAT à la valeur TIRÉE → mêmes
    dégâts par construction. (Le scénario bouclier/réduction/overkill reste au niveau range,
    cf. calculate_damage_prediction_scenario.)

    `attacker_additive_pre` (#75/#68, case-68 MAJ 13) : en COMBAT l'additif ForAddition ATTAQUANT
    (mods.additive) s'ajoute au dégât AVANT perçage/armure — le caller combat de
    `CalculateAbilityDamage @18102cb50` passe un dégât DÉJÀ additivé, et
    `CalculateBaseDamageWithAllModifiers @18102d3f0` NE consomme PAS `DamageModifiers.Addition@+0x10`
    (LU : seuls Piercing@+0x20 et IgnoreArmor@+0x28 y entrent, puis %-list slot 0x11 / Multiplier
    slot 0x10 / Override@+0x0). Reconstruit BIT-EXACT 3/3 (orksNob SmashaEad additif 599, pierce 50,
    armure cible 2208 : bornes (base±spread)+599 → GDWP → live [1540,1738,1526] à l'unité).
      True  = placement natif COMBAT (#75) ET PRÉDICTION (#70/Q3) : pré-perçage ; l'additif traverse
              perçage PUIS %-list -> scalé ×%-mod (cohérent #88) ; PAS de re-add post ;
      False = chemin legacy post-perçage (additif après %-list, NON scalé) — plus utilisé par le port
              (prédiction basculée True au #70/Q3 : verdict RE PredictAttackRaw @181032fb0, prediction.md §10)."""
    pierce_eff, armor_eff = pierce_pct, armor
    if mods is not None:
        pierce_eff = max(0, min(100, pierce_pct + mods.extra_pierce))
        armor_eff = 0 if mods.ignore_armor else max(0, armor - mods.armor_penetration)
    d = value
    if mods is not None and attacker_additive_pre and mods.additive:
        d = round(d + mods.additive)       # additif au dégât AVANT perçage (COMBAT, MAJ 13)
    for _ in range(max(1, hit_mult)):
        d = get_damage_with_piercing(d, pierce_eff, armor_eff)
    if mods is not None:
        if attacker_additive_pre:
            # additif déjà dans la base → %-list SEUL (ApplyCappedModifiers @181000020) + plancher 0
            d = max(0, apply_capped_modifiers(d, mods))
        else:
            d = apply_all_modifiers(d, mods)   # %-list PUIS additif (@+0x10) — APRES percage (§17.7)
    return d


def predict_attack_raw(
        prev: "BlockScenario", initial_damage: int, profile_type: int = 0,
        armor: int = 0, pierce_pct: int = 100, extra_max: int = 0,
        mods: DamageModifiers | None = None, hit_mult: int = 1,
        reduction_min: int = 0, reduction_max: int = 0, spread_pct: int = 20,
        target_current_health: int = 0, target_shield: int = 0,
        target_limits: dict | None = None,
        predefined: MinMaxDamage | None = None, might_crit: bool = False) -> DamagePredictionResult:
    """`DamagePrediction.PredictAttackRaw` @181032fb0 — prédiction d'UN COUP contre les RESSOURCES RESTANTES
    de la cible (déplétées par `prev`, scénario cumulé des coups précédents ; `prev` vide = ressources
    pleines = 1er coup). NE fait PAS le ×hits (→ `get_multi_hit_attack_prediction`) ; l'additif plat EST
    appliqué ICI PAR COUP (via `mods` non strippé, #70).

    Recurrence RE (verdict prev-threading, VA/offsets) :
      rem_shld = max(0, target_shield − prev.shieldAbs)         # bouclier restant (prev@+0x28/+0x2c) @1810341d5/427a
      rem_HP   = max(0, target_current_health − prev.healthDmg) # HP restant (prev@+0x08)             @181034087
      base = predefined | GetBaseDamageFix64(initial_damage)    # {base−spread, base+spread+extraMax}
      blocked = Min(base, rem_shld)                             # split bouclier PER-COUP (slot 0xc @181034caa/ce7)
      health  = ApplyPierce/Armure/%-mods(base − blocked)       # CalculateBaseDamageWithAllModifiers @18102d3f0
      health  = min(health, rem_HP)                             # overkill PER-COUP (FillUpStat.MaxReduceByMinimum)
    ⚠ `prev` déplète les RESSOURCES EN AMONT (bouclier/HP restant) — ce N'EST PAS `param_7`
    (previousHitsPrediction) de CDS, qui est le bonus crit INTRA-coup (verdict RE @181035dce)."""
    mm = predefined if predefined is not None \
        else get_base_damage_fix64(initial_damage, extra_max, spread_pct)
    # #70/Q3 : additif plat NON strippé -> appliqué PAR COUP en PRÉ-perçage (attacker_additive_pre=True aux
    # call-sites lo/hi ci-dessous). Verdict RE (PredictAttackRaw @181032fb0, prediction.md §10) : le natif
    # ajoute l'additif @+0x10 à la base int AVANT `CalculateBaseDamageWithAllModifiers @18102d3f0` (L1940/L2062) ;
    # CBDWAM NE consomme PAS Addition (acquis #75) -> l'additif traverse perçage PUIS %-list (scalé ×%-mod #88).
    # `GetMultiHitAttackPrediction @181066080` appelle `PredictAttackRaw` PAR COUP + `Add`, SANS additif
    # post-boucle. L'ancien strip + application UNE FOIS sur l'agrégat = artefact pré-refactor #51.
    # GuardianOrganism (PercentSubtractionCapped, défenseur) : la réduction = un `ForSubtraction` dont le
    # montant `Min(PercentageOf(CurrentDamage, pct), cap)` est PRÉ-ÉVALUÉ EN SCALAIRE (natif : `Calculate
    # BaseDamageWithAllModifiers @18102d3f0` reçoit le défender-mod DÉJÀ évalué -> MÊME valeur pour min ET max
    # = FLAT, PAS re-évalué per-borne). `CurrentDamage` = la BASE (centre) du dégât post-perçage/mods, donc
    # D=(lo+hi)/2 ; CONFIRMÉ LIVE 2 cas (Kharn->TyrantGuard D6280 -> flat min(33%*D,cap2619)=2072 => 2952/5464 ;
    # #86a D2670 -> flat min(33%*D,cap)=881 => .../2324). On STRIPPE donc capped_reductions du chemin PER-BORNE
    # (apply_all_modifiers = per-VALEUR, correct pour le COMBAT) et on soustrait le scalaire FLAT après (bornes).
    mods_pct = mods
    _capped = list(mods.capped_reductions) if mods else []
    if _capped:
        mods_pct = replace(mods, capped_reductions=[])
    if target_shield > 0:
        # split bouclier PER-COUP sur le bouclier RESTANT (déplété par prev) : Min(base, rem_shield)
        blk_lo = min(mm.min, max(0, target_shield - prev.shield_min))
        blk_hi = min(mm.max, max(0, target_shield - prev.shield_max))
        rem_lo, rem_hi = mm.min - blk_lo, mm.max - blk_hi
    else:
        blk_lo = blk_hi = 0
        rem_lo, rem_hi = mm.min, mm.max
    # PRÉDICTION : conversion int finale = **Round** (le natif matérialise la borne prédite via Round ;
    # ≠ COMBAT op_Explicit=troncature). apply_pierce_and_modifiers/apply_capped_modifiers renvoient le
    # Fix64 fractionnaire (perçage non tronqué #111) -> on arrondit ICI, une seule fois par borne.
    lo = round(apply_pierce_and_modifiers(rem_lo, pierce_pct, armor, mods_pct, hit_mult,
                                          attacker_additive_pre=True)) if rem_lo else 0
    hi = round(apply_pierce_and_modifiers(rem_hi, pierce_pct, armor, mods_pct, hit_mult,
                                          attacker_additive_pre=True)) if rem_hi else 0
    # Réduction DÉFENSEUR capée FLAT (GuardianOrganism) : scalaire = min(trunc(pct% × D), cap) avec D=(lo+hi)/2 =
    # CurrentDamage (base/centre du dégât, pré-GO), soustrait des DEUX bornes (mirror pré-évalué natif @18102d3f0 ;
    # HELPER PARTAGÉ avec le COMBAT `capped_reduction_flat` = MÊME formule + troncature Fix64, confirmée bit-exact
    # #91). AVANT target_limits (ordre natif : CalculateBaseDamageWithAllModifiers -> ApplyTraitDamageLimitsToDamage).
    if _capped and (lo or hi):
        _flat = capped_reduction_flat((lo + hi) / 2.0, _capped)
        lo = max(0, lo - _flat)
        hi = max(0, hi - _flat)
    if target_limits:
        # ApplyTraitDamageLimitsToDamage @18102c650 — cape le dégât per-bout APRÈS modifiers, AVANT le
        # scénario (ordre natif). Appliqué aux 2 bornes (le natif appelle chaque Apply 2× : min puis max).
        # `current_health` = HP RESTANT de la cible avant CE coup (déplété par `prev`). `target_limits` =
        # champs STATIQUES cible (traits/member/max_health) montés par l'appelant ; les caps non dérivables
        # offline (Impervious charge, member-count stat 20, boss 0x5d4) y sont des no-op documentés.
        _rem_lo = max(0, target_current_health - prev.health_min)
        _rem_hi = max(0, target_current_health - prev.health_max)
        # Porte IsOverkill (@181032db0) : le natif calcule le flag UNE fois depuis la borne MIN (accum =
        # (maxHP - curHP) + dmgMin) et l'applique aux 2 bornes (ApplyResilient(min,ovk)+ApplyResilient(max,
        # ovk)). overkill=True => cap Resilient BYPASSE (l'unite meurt) => pas de HP-1. Fidele au live :
        # over-kill massif -> skip (HP), modere -> cape (HP-1). max_health peuple par le vrai moteur
        # (engine/ai/context.py observeBattle) ; None dans le harnais de sonde -> flag inerte (cap deja off).
        _maxhp = int(target_limits.get("max_health") or 0)
        _ovk = compute_prediction_overkill(_rem_lo, _maxhp, lo) if (lo and _maxhp > 0) else False
        if lo:
            lo = apply_trait_damage_limits_to_damage(lo, current_health=_rem_lo, overkill=_ovk,
                                                     **target_limits)
        if hi:
            hi = apply_trait_damage_limits_to_damage(hi, current_health=_rem_hi, overkill=_ovk,
                                                     **target_limits)
    health = calculate_damage_prediction_scenario(
        MinMaxDamage(min=lo, max=hi), prev_hits=0, profile_type=profile_type,
        reduction_min=reduction_min, reduction_max=reduction_max)
    # RAW @0x24/@0x28 : dégât santé AVANT le cap de santé-restante (over-shoot préservé pour kill/overkill).
    raw_health = MinMaxDamage(min=health.min, max=health.max, cap=health.cap)
    if target_current_health > 0:
        # overkill PER-COUP : la santé de CE coup <= HP RESTANT (HP courant − cumul prev). La somme sur les
        # coups = min(Σ, HP) — équivalent à l'ancien cap-sur-agrégat, mais fidèle à la déplétion native.
        health = MinMaxDamage(min=min(health.min, max(0, target_current_health - prev.health_min)),
                              max=min(health.max, max(0, target_current_health - prev.health_max)),
                              cap=health.cap)
    return DamagePredictionResult(
        current_health=target_current_health, armor=armor, shield=target_shield,
        accurate_health_damage=health, raw_health_damage=raw_health,
        accurate_shield_damage=MinMaxDamage(min=blk_lo, max=blk_hi),
        total_damage=MinMaxDamage(min=blk_lo + health.min, max=blk_hi + health.max),
        applied_hits=1, might_crit=might_crit)


def get_multi_hit_attack_prediction(
        target_current_health: int, initial_damage: int | None = None, hits: int = 1,
        profile_type: int = 0, armor: int = 0, pierce_pct: int = 100, extra_max: int = 0,
        mods: DamageModifiers | None = None, hit_mult: int = 1,
        reduction_min: int = 0, reduction_max: int = 0, spread_pct: int = 20,
        target_shield: int = 0, might_crit: bool = False,
        target_limits: dict | None = None) -> DamagePredictionResult:
    """`BattleQuery.GetMultiHitAttackPrediction` @181066080 — LA boucle multi-coups (le `×hits` est ICI, PAS
    dans PredictAttackRaw) :
        result = predict_attack_raw(coup 1, prev=vide)
        for i in 2..hits: prev = result.default_block_scenario(); result.add(predict_attack_raw(coup i, prev))
    `prev` (`get_DefaultBlockScenario @18102bcd0`) porte le cumul santé/bouclier → chaque coup opère sur les
    ressources RESTANTES (déplétion PER-COUP fidèle : bouclier/HP décroissent d'un coup à l'autre). `Add`
    @18102a710 somme les Accurate*. L'ADDITIF plat (ForAddition, ex. −582) s'applique PAR COUP dans
    `predict_attack_raw` (mirror natif ; PAS une fois sur l'agrégat — #70).

    Base par coup = `GetBaseDamageFix64(initial_damage)` = `{0.8·base, 1.2·base+extraMax}` (±20%, RE
    @181030ba0 slots 8/9 = 0.8/1.2). `initial_damage` = stat Attack (NORMALE) OU `GetDamage` avg(minDmg,maxDmg)
    scalé rareté (SPÉCIALE générique). ⚠ L'ancien chemin `damage=`/plage empirique `(0.8·d/hits, 2.2·d/hits)`
    est SUPPRIMÉ : RE PredictAttackRaw @181032fb0 = base 1 SEUL int -> GetBaseDamageFix64 ±20% (OU flat via
    byte @param_3+0x6a), aucun facteur 2.2, aucune paire {minDmg,maxDmg}. Les specials Attack-based
    (PlasmaCannon/SpiritLeech) ne passent PAS ici (routés via _PREDICT_VIA_NORMAL_ATTACK)."""
    hits = max(1, hits)

    def _hit(prev: "BlockScenario") -> DamagePredictionResult:
        return predict_attack_raw(
            prev, initial_damage or 0, profile_type=profile_type, armor=armor, pierce_pct=pierce_pct,
            extra_max=extra_max, mods=mods, hit_mult=hit_mult, reduction_min=reduction_min,
            reduction_max=reduction_max, spread_pct=spread_pct,
            target_current_health=target_current_health, target_shield=target_shield,
            target_limits=target_limits, might_crit=might_crit)

    result = _hit(BlockScenario())                          # coup 1 : prev vide → ressources pleines
    for _i in range(1, hits):
        result.add(_hit(result.default_block_scenario()))   # coup i : prev = cumul → ressources restantes
    # #70 : l'additif plat (ForAddition) est appliqué PAR COUP dans `predict_attack_raw` (via `mods` non
    # strippé) -> mirror natif (Σ des events per-coup, chacun avec l'additif). PLUS d'application UNE FOIS
    # sur l'agrégat (ancien bloc = artefact pré-refactor #51 ; SANS contrepartie native, cf. prediction.md §4).
    return result


def get_attack_prediction(
        target_current_health: int, initial_damage: int, hits: int, profile_type: int,
        armor: int = 0, pierce_pct: int = 100, extra_max: int = 0,
        mods: DamageModifiers | None = None, hit_mult: int = 1,
        reduction_min: int = 0, reduction_max: int = 0, spread_pct: int = 20,
        might_crit: bool = False, target_shield: int = 0, target_limits: dict | None = None,
        shield_raw: MinMaxDamage | None = None) -> DamagePredictionResult:
    """`BattleQuery.GetNormalAttackPrediction` / `GetAttackPrediction` (slot 14) — entrée attaque NORMALE
    (whole-attack). Le natif route TOUTE attaque multi-coups par `GetMultiHitAttackPrediction` (boucle
    `PredictAttackRaw` par coup + `prev` déplété + `Add`) : on DÉLÈGUE donc à `get_multi_hit_attack_prediction`.
    Le `×hits`, le split bouclier et l'overkill sont désormais PER-COUP là-dedans (plus d'agrégat).

    ⚠ `shield_raw` (ancien override de la base bouclier AGRÉGÉE pour les spéciales) est OBSOLÈTE — le
    bouclier est déplété PAR COUP via `prev` ; accepté pour compat des appelants mais IGNORÉ.

    VALIDÉ (à préserver) : 1-coup (u88 pierce1+armure, u92 pierce70) ; multi-coup u96 = base×3 ;
    buff u94 (RapidAssault +25%) = oracle EXACT ; seed777 step-11 ; #47 GetStuckIn 11/11 ; bouclier
    worldTerminator (sh 3989)."""
    return get_multi_hit_attack_prediction(
        target_current_health=target_current_health, initial_damage=initial_damage, hits=hits,
        profile_type=profile_type, armor=armor, pierce_pct=pierce_pct, extra_max=extra_max,
        mods=mods, hit_mult=hit_mult, reduction_min=reduction_min, reduction_max=reduction_max,
        spread_pct=spread_pct, target_shield=target_shield, might_crit=might_crit,
        target_limits=target_limits)
