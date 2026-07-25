"""Port FIDÈLE de `IdunBattle.Core.Services.DamagePrediction` (gqfc5mff6c).

Chaque méthode = sa jumelle native (même nom, même logique), VA citée. Les ENTRÉES (stats
résolues, traits, config d'arme) viennent de `combatSnapshot` (one-shot) + gameconfig — pas de
black-box. La struct résultat mirror `DamagePredictionResult`.

⚠ Découverte mesurée (predict_validate.py) : la PRÉDICTION IA (`GetAllPredictions`/
`GetNormalAttackPrediction`/`GetAttackPrediction`, même cœur `PredictAttackRaw`) est PRÉ-ARMURE
pour l'attaque normale (dmg indépendant de l'armure cible ; `armorBefore=0`).

STRUCTURE (calquée 1:1 sur le natif — le `×hits` N'est PAS dans PredictAttackRaw) :
  - `predict_attack_raw`            = `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`  (UN COUP, prev-aware)
  - `get_multi_hit_attack_prediction` = `IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction`  (LA boucle)
  - `DamagePredictionResult.add`     = `IdunBattle.Core.Services.DamagePredictionResult$$Add`  (Σ des coups)
  - `.default_block_scenario`        = `IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario`  (prev cumulé threadé)
  - `get_attack_prediction`          = entrée attaque NORMALE (whole-attack) → route par la boucle.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from . import fix64 as _fx
from .min_max_damage import MinMaxDamage
from .damage_calculations import spread_to_min_max
from .static_battle_rules import get_damage_with_piercing, get_piercing_ratio, W_LASCANNON_PIERCE_BONUS
from .damage_modifiers import (
    DamageModifiers, apply_all_modifiers, apply_capped_modifiers, capped_reduction_flat,
)
from .trait_damage_limits import apply_trait_damage_limits_to_damage, compute_prediction_overkill

# StatType ids : utiliser l'enum `entities.stats.StatType` (complet #157). Les constantes STAT_* hex
# eparses (mortes) ont ete retirees.
# #157 : constantes de trait id-brut MORTES retirées (TRAIT_HIT_TWICE=1013, TRAIT_PIERCE_1001=1001=HeavyWeapon,
# TRAIT_PIERCE_1016=1016=Emplacement) — la chaîne perçage/dégât gate par bool name-based ; les ids vivent
# désormais dans `entities.traits.UnitTrait` (#146).


@dataclass
class DamagePredictionResult:
    """struct DamagePredictionResult (dump.cs TypeDefIndex 11757, offsets STRUCT) :
      CurrentHealth@0 · CurrentArmor@4 · CurrentShield@8 · healthDmg RAW (MinMax)@0x18
      {cap@0x18, Min@0x20, Max@0x24} — NON capé par HP ; `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` =
      `CurrentHealth@0 <= raw MAX@0x24` (offsets RE-CONFIRMÉS #40 : `IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario` copie result@+0x20 → BS.healthDmg@+0x08 = raw MIN cumulé, layout vérifié
      par le `[0]<=[9]` de WillBeKill + le kill natif=true à rawMax>=HP) ·
      AccurateHealthDamage(MinMax)@0x58 (Min@+8=0x60, Max@+0xc=0x64, CAPÉ par HP santé restante)
      · AccurateArmorDamage@0x68 · AccurateShieldDamage@0x78 · TotalDamage@0x88 · LimitedByMinHp@0xB0
      · MightCrit@0xB1 · ForceOverkill@0xB2 · AppliedHits@0xBC.
    SPLIT santé/bouclier (PredictAttackRaw, call-sites VA IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1cfa/IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1d37) :
      shieldDmg = CalculateDamageBlockedByShield = Min(dmg_borne, rem) avec **rem UNIQUE** =
      shield − cumul MAX absorbé (#42, cf. BlockScenario) ; healthDmg = dmg − shieldDmg.
      Le bouclier absorbe la base RAW pré-perçage (le reste traverse perçage/armure/mods).
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
    # #54A : mirror de `list[0]@0x50` (scénarios de BLOCK, mergés par index dans `IdunBattle.Core.Services.DamagePredictionResult$$Add`) =
    # le scénario « TOUS les coups bloqués » : Σ_coup max(0, rawMin_coup − blockAmount). None = pas de
    # source de block chez le défenseur (liste vide) → `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` retombe sur le
    # scalaire rawMin@0x24. Consommé par will-be-kill/will-be-overkill (killSure/DefinitelyOverkill).
    block_raw_min: int | None = None

    def default_block_scenario(self) -> "BlockScenario":
        """`IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario — le scénario cumulé (dégât santé/
        bouclier déjà infligé) threadé comme `prev` au coup suivant → ressources RESTANTES de la cible.
        ⚠ #40 (RE 2026-07-20, copie champ-à-champ LUE) : la santé threadée est UN SEUL int —
        `BS.healthDmg@+0x08 = result@+0x20` = **raw health MIN cumulé** (PAS un par-borne min/max).
        La borne MAX du coup suivant est donc déplétée par le scénario MIN (le natif suppose le
        minimum garanti déjà infligé) — c'est ce qui laisse le rawMax cumulé dépasser HP−1
        (31337 s8 : 1047+800(cap 801−1)+102 = 1949 > 1498). Bouclier : les DEUX champs sont
        threadés mais le rem effectif ne lit que `shield_max` (cumul MAX, #42 — cf. BlockScenario)."""
        return BlockScenario(
            health=self.raw_health_damage.min,
            shield_min=self.accurate_shield_damage.min, shield_max=self.accurate_shield_damage.max)

    def add(self, other: "DamagePredictionResult") -> None:
        """`IdunBattle.Core.Services.DamagePredictionResult$$Add — somme ENTIÈRE champ-par-champ (Accurate* santé/bouclier
        + Total + AppliedHits) avec ApplyCap. MUTE self (agrège le coup `other` de la boucle multi-coups)."""
        _self_raw_min_before = self.raw_health_damage.min   # #54A : fallback block AVANT la somme raw
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
        # #54A : merge du scénario block (mirror per-index de `IdunBattle.Core.Services.DamagePredictionResult$$Add` : quand UN côté n'a pas
        # de liste, son scalaire rawMin sert d'entrée — c'est exactement le fallback natif).
        if self.block_raw_min is not None or other.block_raw_min is not None:
            a = self.block_raw_min if self.block_raw_min is not None else _self_raw_min_before
            b = other.block_raw_min if other.block_raw_min is not None else other.raw_health_damage.min
            self.block_raw_min = a + b


@dataclass
class BlockScenario:
    """Scénario cumulé threadé comme `prev` entre coups — `IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario. Porte le
    dégât CUMULÉ (santé/bouclier) des coups précédents → RESSOURCES RESTANTES de la cible au coup suivant
    (`rem = pleine − cumul`). Champs natifs consommés par `PredictAttackRaw` (prev = Nullable@param_3+0x84) :
    healthDmg@+0x08 = **UN SEUL int** (rem_HP IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x10d7 : `local_914 = Max(0, HP − BS@+0x08)` — la MÊME
    valeur sert les 2 bornes), shieldAbs min@+0x28 / max@+0x2c (rem_shield IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1225/427a).
    (armorDmg@+0x18 = déplétion armure IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1180 — armure=0 en prédiction IA, non threadé.)
    Vide (tout 0) = 1er coup = pleines. ⚠ #40 : l'ancien port threadait health_min/health_max PER-BORNE
    (rem_hi déplété par le cumul MAX) → rawMax saturait à HP−1 (1498) là où le natif rend 1949.
    ⚠ #42 (mesure discriminante 777 s11, ab1150 3 coups vs bouclier 3989) : côté BOUCLIER le rem
    effectif est AUSSI un scalaire UNIQUE = shield − `shield_max` (cumul MAX absorbé) pour les DEUX
    bornes — `shield_min` (cumul MIN, mirror MM3.min du scénario natif) est conservé dans le struct
    mais ne pilote PAS le rem (l'ancienne lecture per-piste min@+0x28/max@+0x2c donnait un
    shieldDmgMin sur-évalué 3351 vs natif 2873). Layout RE réel (skew +4 lu au repack de
    `IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction`) : le buffer de `get_DefaultBlockScenario` copie
    DPR@0x18..0x4b et le BlockScenario VRAI = buffer@0x04.. → BS@+0x08 = MM1.min (santé raw MIN
    cumulé, #40 ✓) ; MM3 {min@+0x28, max@+0x2c} = paire bouclier bloquée cumulée."""
    health: int = 0
    shield_min: int = 0
    shield_max: int = 0


def get_default_attack_hits(base_hits: int, extra_hits: int,
                           extra_hits_melee: int, is_melee: bool) -> int:
    """DamagePrediction.GetDefaultAttackHits (IdunBattle.Core.Services.DamagePrediction$$GetDefaultAttackHits) :
        hits = base + ExtraHits(17) + (melee ? ExtraHitsMelee(23) : 0) ; max(hits, 0)."""
    h = base_hits + extra_hits
    if is_melee:
        h += extra_hits_melee
    return max(h, 0)


def get_attack_piercing_damage_ratio(profile_piercing_ratio: int, profile_has_lascannon: bool,
                                     attacker_extra_pierce: int, attacker_extra_pierce_dir: int,
                                     attacker_has_heavy_weapon_or_emplacement: bool,
                                     extra_pierce_min: int = 0, extra_pierce_max: int = 0,
                                     lascannon_bonus: int = W_LASCANNON_PIERCE_BONUS) -> int:
    """DamagePrediction.GetAttackPiercingDamageRatio (IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio) :
        base = GetPiercingRatio(profile, attackerTraits)
        total = clamp(0,100, base + ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}
                              + extra_pierce_min + extra_pierce_max)
    (`extra_pierce_min/max` = bonus de perçage d'EFFET, params Fix64→int ; 0 en baseline.
     `profile_has_lascannon` = `DamageProfile.HasTrait(DamageTrait.LasCannon)` ; `attacker_has_heavy_weapon_or_emplacement`
     = `HasTrait(attacker, UnitTrait.HeavyWeapon|Emplacement)` — cf. entities/damage_trait.py + entities/traits/unit_trait.py.)"""
    base = get_piercing_ratio(profile_piercing_ratio, profile_has_lascannon,
                              attacker_has_heavy_weapon_or_emplacement, lascannon_bonus)
    total = (base + attacker_extra_pierce + attacker_extra_pierce_dir
             + extra_pierce_min + extra_pierce_max)
    return max(0, min(100, total))


def get_base_damage_with_fixed_pierced_armor(
        damage: int, pierce_pct: int, target_fixed_armor: int,
        armor_penetration: int = 0, hit_multiplier: int = 1) -> int:
    """DamagePrediction.GetBaseDamageWithFixedPiercedArmor (IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor).

        armor_eff = max(target.FixedArmor(16) − armor_penetration, 0)
        d = damage
        repeat hit_multiplier fois : d = GetDamageWithPiercing(d, pierce_pct, armor_eff)
        return d
    hit_multiplier : 1 normalement ; 2 si la cible a le trait 1013 (UnitTrait, cf. #146) (et flag off) ;
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
    """DamagePrediction.CalculateDamagePredictionScenario (IdunBattle.Core.Services.DamagePrediction$$CalculateDamagePredictionScenario) — UN outcome (1 coup × 1 état).
    Corps RE LECTURE INTÉGRALE (playbook-engine.md §16.2) :

        eff = max(0, raw − prev_hits)              # param_7 = BONUS CRIT du scénario courant (intra-coup)
        shieldAbs = absorbShield(eff)              # interface slot 0xb (FUN_1800068b0)
        health    = max(0, eff − shieldAbs)
        if cible.FillUpStatComponent : health = MaxReduceByMinimum(health, remaining_health)  # overkill
        MinMaxDamage.ApplyCap

    ⚠ CORRECTION RE (verdict prev-threading IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2e1e) : `param_7` natif = le **bonus du scénario de crit
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
    """DamagePrediction.GetBaseDamageFix64 (IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64) — la MinMax de base AVANT armure (local_938).
    RE (playbook-engine.md §16) :
        min = CalculateMinDamage(base) = base − CalculateDamageSpread(base)   # slot 8
        max = CalculateMaxDamage(base) + ExtraMaxDamage(stat 0x19=25)         # slot 9 + extraMax
    ⚠ ASYMÉTRIE : `ExtraMaxDamage` gonfle le BOUT HAUT seulement (stat attaquant). `is_max_out` (rare,
    trait force-max) → min = max = CalculateMaxDamage(base)+extraMax."""
    mm = spread_to_min_max(base, spread_pct)            # {base−spread, base+spread}
    hi = mm.max + extra_max
    lo = hi if is_max_out else mm.min
    # #65 : les bornes sont consommees par `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` dont le
    # param est un **int baseDamage** (op_Explicit Fix64->int = TRONCATURE) -> trunc mirror. No-op pour
    # toute base entiere (bornes entieres) ; ne mord que sur les bases fractionnaires (midpoint x.5 du
    # noeud Average, ex. FleshmetalGuns Melta avg 1246.5 -> bornes 997.5/1495.5 -> 997/1495, ground
    # truth AllMods + oracle (3890,5830) reconstruit exact).
    return MinMaxDamage(min=int(lo), max=int(hi))


def _materialize(v) -> int:
    """Matérialisation int des BORNES de prédiction = `FixMath.NET.Fix64$$Round(·, mode 1 AwayFromZero)` sur la valeur Fix64 EXACTE, puis conversion (intégrale → passthrough).
    ⚠ Verdict EMPIRIQUE #30a (2 mesures A/B live, seeds 777+31337 ×20 steps) : floor(exact)
    = 13 mismatches vs round(float) = 5 vs round(exact) — le natif ARRONDIT les bornes
    prédites (le Round vit en aval de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`,
    qui lui renvoie du fractionnaire sans Round interne — lu intégralement ; les op_Explicit
    de PredictAttackRaw portent sur des Fix64 déjà intégraux). ≠ COMBAT : le dégât TIRÉ se
    matérialise par op_Explicit=floor (`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`, apply_all_modifiers).
    L'exactitude Fix64 reste LA correction : round(float) divergeait aux frontières .5
    fabriquées par le bruit float (777s6 : float 277.5→278 vs exact 277.49999982…→277)."""
    return _fx.to_int(_fx.round_raw(_fx.from_number(v), 1))


def apply_pierce_and_modifiers(value: int, pierce_pct: int = 100, armor: int = 0,
                               mods: DamageModifiers | None = None, hit_mult: int = 1,
                               attacker_additive_pre: bool = False):
    """BASE COMMUNE prédiction↔combat — réduction d'UNE valeur de dégât (= étape 3+3b de
    `predict_attack_raw`, cf. `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers) :
        pierce_eff = clamp(0,100, pierce + mods.extra_pierce)
        armor_eff  = 0 si mods.ignore_armor sinon max(0, armor − mods.armor_penetration)
        d = GetDamageWithPiercing(value, pierce_eff, armor_eff) répété hit_mult×
        d = ApplyAllModifiers(d, mods)        # ×bonus post-perçage §17.7
    La PRÉDICTION l'applique à ses 2 bornes (min,max) ; le COMBAT à la valeur TIRÉE → mêmes
    dégâts par construction. (Le scénario bouclier/réduction/overkill reste au niveau range,
    cf. calculate_damage_prediction_scenario.)

    `attacker_additive_pre` (#75/#68, case-68 MAJ 13) : en COMBAT l'additif ForAddition ATTAQUANT
    (mods.additive) s'ajoute au dégât AVANT perçage/armure — le caller combat de
    `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` passe un dégât DÉJÀ additivé, et
    `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` NE consomme PAS `DamageModifiers.Addition@+0x10`
    (LU : seuls Piercing@+0x20 et IgnoreArmor@+0x28 y entrent, puis %-list slot 0x11 / Multiplier
    slot 0x10 / Override@+0x0). Reconstruit BIT-EXACT 3/3 (orksNob SmashaEad additif 599, pierce 50,
    armure cible 2208 : bornes (base±spread)+599 → GDWP → live [1540,1738,1526] à l'unité).
      True  = placement natif COMBAT (#75) ET PRÉDICTION (#70/Q3) : pré-perçage ; l'additif traverse
              perçage PUIS %-list -> scalé ×%-mod (cohérent #88) ; PAS de re-add post ;
      False = chemin legacy post-perçage (additif après %-list, NON scalé) — plus utilisé par le port
              (prédiction basculée True au #70/Q3 : verdict RE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw, prediction.md §10)."""
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
            # additif déjà dans la base → %-list SEUL (IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers) + plancher 0
            d = max(0, apply_capped_modifiers(d, mods))
        else:
            d = apply_all_modifiers(d, mods)   # %-list PUIS additif (@+0x10) — APRES percage (§17.7)
    return d


def is_attack_max_out_damage(attacker_effects) -> bool:
    """#202 WeaverOfFate — mirror `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` (branche effet) :
    l'attaquant est owner OU target de l'effet 1185 `WeaverOfFate_MaxOutDamage` (self-cast : roles
    confondus offline) -> degats MAX sans tirage. FOYER UNIQUE cote prediction, evalue DANS
    `predict_attack_raw` comme le natif l'evalue DANS `PredictAttackRaw` (wrapper `DamagePrediction.
    IdunBattle.Core.Services.DamagePrediction$$IsAttackMaxOutDamage`, call site IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1b0a) — les appelants passent les EFFETS de
    l'attaquant (scene.effects / active ECS), pas un flag pre-calcule. La branche
    `HasTriggeredAbility(1494 ParagonSpear)` n'est PAS mirroree (porteur hors kit — residu case-202 §6).
    (Le COMBAT runner a son mirror jumeau sur l'EffectsState ECS : `weaver_of_fate.
    is_attack_max_out_damage` — meme fonction native, deux stores.)"""
    return any(getattr(e, "name", None) == "WeaverOfFate_MaxOutDamage"
               for e in (attacker_effects or []))


def predict_attack_raw(
        prev: "BlockScenario", initial_damage: int, profile_type: int = 0,
        armor: int = 0, pierce_pct: int = 100, extra_max: int = 0,
        mods: DamageModifiers | None = None, hit_mult: int = 1,
        reduction_min: int = 0, reduction_max: int = 0, spread_pct: int = 20,
        target_current_health: int = 0, target_shield: int = 0,
        target_limits: dict | None = None,
        predefined: MinMaxDamage | None = None, might_crit: bool = False,
        attacker_effects=None) -> DamagePredictionResult:
    """`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw — prédiction d'UN COUP contre les RESSOURCES RESTANTES
    de la cible (déplétées par `prev`, scénario cumulé des coups précédents ; `prev` vide = ressources
    pleines = 1er coup). NE fait PAS le ×hits (→ `get_multi_hit_attack_prediction`) ; l'additif plat EST
    appliqué ICI PAR COUP (via `mods` non strippé, #70).

    Recurrence RE (verdict prev-threading, VA/offsets) :
      rem_shld = max(0, target_shield − prev.shieldAbs)         # bouclier restant (prev@+0x28/+0x2c) IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1225/427a
      rem_HP   = max(0, target_current_health − prev.healthDmg) # HP restant (prev@+0x08)             IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x10d7
      base = predefined | GetBaseDamageFix64(initial_damage)    # {base−spread, base+spread+extraMax}
      blocked = Min(base, rem_shld)                             # split bouclier PER-COUP (slot 0xc IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1cfa/ce7)
      health  = ApplyPierce/Armure/%-mods(base − blocked)       # IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers
      health  = min(health, rem_HP)                             # overkill PER-COUP (FillUpStat.MaxReduceByMinimum)
    ⚠ `prev` déplète les RESSOURCES EN AMONT (bouclier/HP restant) — ce N'EST PAS `param_7`
    (previousHitsPrediction) de CDS, qui est le bonus crit INTRA-coup (verdict RE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2e1e)."""
    # #202 WeaverOfFate : le flag max-out est evalue ICI, foyer unique (mirror natif : PredictAttackRaw
    # appelle IsAttackMaxOutDamage IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1b0a lui-meme) puis passe a `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64`
    # -> min = max (bornes degenerees). Un `predefined` (bornes d'ability RandomAmount) est degenere pareil.
    is_max_out = is_attack_max_out_damage(attacker_effects)
    mm = predefined if predefined is not None \
        else get_base_damage_fix64(initial_damage, extra_max, spread_pct, is_max_out=is_max_out)
    if is_max_out and predefined is not None:
        mm = MinMaxDamage(min=predefined.max, max=predefined.max)
    # #70/Q3 : additif plat NON strippé -> appliqué PAR COUP en PRÉ-perçage (attacker_additive_pre=True aux
    # call-sites lo/hi ci-dessous). Verdict RE (IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw, prediction.md §10) : le natif
    # ajoute l'additif @+0x10 à la base int AVANT `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` (L1940/L2062) ;
    # CBDWAM NE consomme PAS Addition (acquis #75) -> l'additif traverse perçage PUIS %-list (scalé ×%-mod #88).
    # `IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction` appelle `PredictAttackRaw` PAR COUP + `Add`, SANS additif
    # post-boucle. L'ancien strip + application UNE FOIS sur l'agrégat = artefact pré-refactor #51.
    # GuardianOrganism (PercentSubtractionCapped, défenseur) : la réduction = un `ForSubtraction` dont le
    # montant `Min(PercentageOf(CurrentDamage, pct), cap)` est PRÉ-ÉVALUÉ EN SCALAIRE (natif : `Calculate
    # BaseDamageWithAllModifiers IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` reçoit le défender-mod DÉJÀ évalué -> MÊME valeur pour min ET max
    # = FLAT, PAS re-évalué per-borne). `CurrentDamage` = la BASE (centre) du dégât post-perçage/mods, donc
    # D=(lo+hi)/2 ; CONFIRMÉ LIVE 2 cas (Kharn->TyrantGuard D6280 -> flat min(33%*D,cap2619)=2072 => 2952/5464 ;
    # #86a D2670 -> flat min(33%*D,cap)=881 => .../2324). On STRIPPE donc capped_reductions du chemin PER-BORNE
    # (apply_all_modifiers = per-VALEUR, correct pour le COMBAT) et on soustrait le scalaire FLAT après (bornes).
    mods_pct = mods
    _capped = list(mods.capped_reductions) if mods else []
    if _capped:
        mods_pct = replace(mods, capped_reductions=[])
    if target_shield > 0:
        # split bouclier PER-COUP sur le bouclier RESTANT — #42 : rem UNIQUE = shield − cumul MAX
        # absorbé (prev.shield_max), consommé par LES DEUX bornes (mirror #40 côté santé, où le rem
        # HP unique = cumul MIN). Mesure discriminante 777 s11 u95 ab1150 -> u81 (S=3989, m=1117,
        # M=1675 x3 coups) : natif shieldDmg = [2873, 3989] = m-track {1117,1117,639} / M-track
        # {1675,1675,639} — le coup 3 des DEUX pistes est capé par rem = 3989−(1675+1675) = 639 ;
        # l'ancienne déplétion par-piste donnait min = 1117x3 = 3351 (faux, jamais discriminé avant :
        # les 2 modèles coïncident tant que la piste MAX n'épuise pas le bouclier en cours de rafale).
        # healthDmgMax natif 58 = f(1675−639) confirme le MÊME rem côté borne haute.
        _rem_sh = max(0, target_shield - prev.shield_max)
        blk_lo = min(mm.min, _rem_sh)
        blk_hi = min(mm.max, _rem_sh)
        rem_lo, rem_hi = mm.min - blk_lo, mm.max - blk_hi
    else:
        blk_lo = blk_hi = 0
        rem_lo, rem_hi = mm.min, mm.max
    # PRÉDICTION : conversion int finale = **op_Explicit = FLOOR** (IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1ed7/e98/eaa/ebb — le natif
    # matérialise les bornes prédites par `FixMath.NET.Fix64$$op_Explicit` = raw>>32, PAS un Round ; le
    # commentaire historique « Round » était FAUX, #30a). MÊME conversion que le COMBAT. La chaîne
    # apply_pierce_and_modifiers/apply_capped_modifiers renvoie le Fix64 fractionnaire EXACT (`.raw`,
    # perçage non tronqué #111 + arithmétique Fix64 #30a) -> floor ICI, une seule fois par borne.
    # (`round()` float ne marchait qu'aux points où round(float)==floor(exact) : 777s6 natif
    # 1850×fix(0.15)=277.4999…→277 vs float 277.5→278 ; et floor(float) régressait ailleurs — seule
    # l'exactitude raw rend le floor universellement juste.)
    lo = _materialize(apply_pierce_and_modifiers(rem_lo, pierce_pct, armor, mods_pct, hit_mult,
                                                 attacker_additive_pre=True)) if rem_lo else 0
    hi = _materialize(apply_pierce_and_modifiers(rem_hi, pierce_pct, armor, mods_pct, hit_mult,
                                                 attacker_additive_pre=True)) if rem_hi else 0
    # Réduction DÉFENSEUR capée FLAT (GuardianOrganism) : scalaire = min(trunc(pct% × D), cap) avec D=(lo+hi)/2 =
    # CurrentDamage (base/centre du dégât, pré-GO), soustrait des DEUX bornes (mirror pré-évalué natif IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers ;
    # HELPER PARTAGÉ avec le COMBAT `capped_reduction_flat` = MÊME formule + troncature Fix64, confirmée bit-exact
    # #91). AVANT target_limits (ordre natif : CalculateBaseDamageWithAllModifiers -> ApplyTraitDamageLimitsToDamage).
    if _capped and (lo or hi):
        _flat = capped_reduction_flat((lo + hi) / 2.0, _capped)
        lo = max(0, lo - _flat)
        hi = max(0, hi - _flat)
    # #170 PLANCHER PRÉDICTION 1-dégât-de-santé PAR COUP — `PredictAttackRaw` fait `MinMaxDamageFix64.MathMax(
    # &dmg, Fix64.One) @IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x26d2` (`IdunBattle.Core.Services.MinMaxDamageFix64$$MathMax` remonte min ET max à 1) APRÈS CalculateBaseDamage
    # WithAllModifiers/ApplyCap (perçage+armure+%-mods+défenseur), AVANT ApplyTraitDamageLimitsToDamage. Valeur =
    # littéral 1 (Fix64 static+0x20 ; ≠ le +0x28=Zero que planche get_damage_with_piercing). ⚠ PRÉDICTION SEULE :
    # le COMBAT `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` planche à 0 (`Fix64.Max(base, 0)`) — NE PAS toucher
    # `get_damage_with_piercing` (partagé combat). GATE natif = le coup CONNECTE et le Nullable bouclier du
    # HitDamage est SANS VALEUR (= cible SANS bouclier : le split ne tourne pas, aucun block boxé). #42 RAFFINE
    # l'ancien mapping `rem>0` : mesure 777 s11 u81 (bouclier 3989) coup 3 partiellement absorbé (rem 478 > 0)
    # -> natif healthDmgMin RESTE 0 (pas de plancher) ; dès que la cible a un bouclier le hit porte une valeur
    # de block (même 0) -> plancher JAMAIS appliqué. Sans bouclier : coup absorbé par l'ARMURE (lo=0) → 1 ;
    # dégât > 1 → no-op (n'affecte QUE pierce-0/armure-lourde). Verdict RE #170 + docs/rl/case-166-168-...md.
    if target_shield <= 0:
        if rem_lo:
            lo = max(lo, 1)
        if rem_hi:
            hi = max(hi, 1)
    if target_limits:
        # IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage — cape le dégât per-bout APRÈS modifiers, AVANT le
        # scénario (ordre natif). Appliqué aux 2 bornes (le natif appelle chaque Apply 2× : min puis max).
        # `current_health` = HP RESTANT de la cible avant CE coup (déplété par `prev`). `target_limits` =
        # champs STATIQUES cible (traits/member/max_health) montés par l'appelant ; les caps non dérivables
        # offline (Impervious charge, member-count stat 20, boss 0x5d4) y sont des no-op documentés.
        # #40 : rem UNIQUE (natif IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x10d7 lit BS.healthDmg@+0x08 = raw MIN cumulé) — les DEUX
        # bornes du coup courant sont capées contre le MÊME HP restant (scénario minimum garanti).
        _rem = max(0, target_current_health - prev.health)
        # Porte IsOverkill (IdunBattle.Core.Services.DamagePrediction$$IsOverkill) : le natif calcule le flag UNE fois depuis la borne MIN (accum =
        # (maxHP - curHP) + dmgMin) et l'applique aux 2 bornes (ApplyResilient(min,ovk)+ApplyResilient(max,
        # ovk)). overkill=True => cap Resilient BYPASSE (l'unite meurt) => pas de HP-1. Fidele au live :
        # over-kill massif -> skip (HP), modere -> cape (HP-1). max_health peuple par le vrai moteur
        # (engine/ai/context.py observeBattle) ; None dans le harnais de sonde -> flag inerte (cap deja off).
        _maxhp = int(target_limits.get("max_health") or 0)
        _ovk = compute_prediction_overkill(_rem, _maxhp, lo) if (lo and _maxhp > 0) else False
        if lo:
            lo = apply_trait_damage_limits_to_damage(lo, current_health=_rem, overkill=_ovk,
                                                     **target_limits)
        if hi:
            hi = apply_trait_damage_limits_to_damage(hi, current_health=_rem, overkill=_ovk,
                                                     **target_limits)
    health = calculate_damage_prediction_scenario(
        MinMaxDamage(min=lo, max=hi), prev_hits=0, profile_type=profile_type,
        reduction_min=reduction_min, reduction_max=reduction_max)
    # RAW @0x24/@0x28 : dégât santé AVANT le cap de santé-restante (over-shoot préservé pour kill/overkill).
    raw_health = MinMaxDamage(min=health.min, max=health.max, cap=health.cap)
    if target_current_health > 0:
        # overkill PER-COUP : la santé de CE coup <= HP RESTANT (FillUpStat.MaxReduceByMinimum consomme
        # local_914 = LE rem UNIQUE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x10d7, #40) — les 2 bornes contre le même rem ; la borne max
        # cumulée peut donc dépasser HP (normalisée ensuite par le cap HP de l'accurate dans Add).
        # #43 : le natif BOXE ce rem comme Cap Nullable de l'AccurateHealthDamage — result@0x00 =
        # local_914 (rem), repris `Nullable<int>.ctor(&cap, result@0x00) IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x3354` + `ApplyCap
        # IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x337c` avant l'écriture @0x58. `IdunBattle.Core.Services.DamagePredictionResult$$Add` garde le cap de SELF (= coup 1, rem =
        # HP PLEIN) et re-ApplyCap → l'AGRÉGAT accurate est clampé au HP cible (mesuré : s8 accurate
        # max 1499 = HP ; 31337-drive6 u91→u83 8034 = HP, pas Σ 9532 ni le rem du coup 3). Le port ne
        # posait jamais ce cap (cap=None → apply_cap no-op dans Add) : seul le min() per-coup contre
        # le rem MIN existait — insuffisant quand aucun coup individuel ne dépasse le rem (HP haut,
        # piste MIN basse). Gate hp>0 = port-side (harnais/probes sans cible ; natif toujours boxé).
        _rem_hp = max(0, target_current_health - prev.health)
        health = MinMaxDamage(min=min(health.min, _rem_hp),
                              max=min(health.max, _rem_hp),
                              cap=_rem_hp)
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
        target_limits: dict | None = None,
        extra_groups: "list[dict] | None" = None,
        defender_block_amount: int | None = None,
        attacker_effects=None) -> DamagePredictionResult:
    """`IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction — LA boucle multi-coups (le `×hits` est ICI, PAS
    dans PredictAttackRaw) :
        result = predict_attack_raw(coup 1, prev=vide)
        for i in 2..hits: prev = result.default_block_scenario(); result.add(predict_attack_raw(coup i, prev))
    `prev` (`IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario`) porte le cumul santé/bouclier → chaque coup opère sur les
    ressources RESTANTES (déplétion PER-COUP fidèle : bouclier/HP décroissent d'un coup à l'autre). `IdunBattle.Core.Services.DamagePredictionResult$$Add somme les Accurate*. L'ADDITIF plat (ForAddition, ex. −582) s'applique PAR COUP dans
    `predict_attack_raw` (mirror natif ; PAS une fois sur l'agrégat — #70).

    Base par coup = `GetBaseDamageFix64(initial_damage)` = `{0.8·base, 1.2·base+extraMax}` (±20%, RE
    IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64 slots 8/9 = 0.8/1.2). `initial_damage` = stat Attack (NORMALE) OU `GetDamage` avg(minDmg,maxDmg)
    scalé rareté (SPÉCIALE générique). ⚠ L'ancien chemin `damage=`/plage empirique `(0.8·d/hits, 2.2·d/hits)`
    est SUPPRIMÉ : RE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw = base 1 SEUL int -> GetBaseDamageFix64 ±20% (OU flat via
    byte @param_3+0x6a), aucun facteur 2.2, aucune paire {minDmg,maxDmg}. Les specials Attack-based
    (PlasmaCannon/SpiritLeech) ne passent PAS ici (routés via _PREDICT_VIA_NORMAL_ATTACK)."""
    hits = max(1, hits)

    # #54A : scénario BLOCK per-coup (mirror `IdunBattle.Core.Services.DamagePrediction$$CalculateDamagePredictionScenario` →
    # entrée `list[0]@0x50` « tous les coups bloqués ») : rawMin_coup' = max(0, rawMin_coup − amount).
    # Appliqué au raw min FINAL du coup (armure=0 en prédiction IA, pré-armure ≡ post) — réconcilié
    # 1357 s15 (5388 − 3×1097 = 2097). None/0 = pas de source de block → liste vide (fallback scalaire).
    def _with_block(r: DamagePredictionResult) -> DamagePredictionResult:
        if defender_block_amount and int(defender_block_amount) > 0:
            r.block_raw_min = max(0, r.raw_health_damage.min - int(defender_block_amount))
        return r

    def _hit(prev: "BlockScenario") -> DamagePredictionResult:
        return _with_block(predict_attack_raw(
            prev, initial_damage or 0, profile_type=profile_type, armor=armor, pierce_pct=pierce_pct,
            extra_max=extra_max, mods=mods, hit_mult=hit_mult, reduction_min=reduction_min,
            reduction_max=reduction_max, spread_pct=spread_pct,
            target_current_health=target_current_health, target_shield=target_shield,
            target_limits=target_limits, might_crit=might_crit, attacker_effects=attacker_effects))

    result = _hit(BlockScenario())                          # coup 1 : prev vide → ressources pleines
    for _i in range(1, hits):
        result.add(_hit(result.default_block_scenario()))   # coup i : prev = cumul → ressources restantes
    # #179 : coups ADDITIONNELS HETEROGENES (EffectAdditionalHits, ex. SquigHound_AdditionalHits) — degat
    # [min,max] PROPRE (predefined -> pas de spread ±20%, RandomAmount natif) + pierce/profil PROPRES, mais
    # MEME cible (armure/hp/bouclier/hit_mult). Continuent la MEME chaine `prev` (result.default_block_
    # scenario()) APRES les coups d'arme -> deplete bouclier/HP restant = overkill CONTINU fidele (le natif
    # les ajoute au meme DamagePredictionResult). Mirror IdunBattle.Entities.Effects.EffectAdditionalHits$$Create.
    for _grp in (extra_groups or []):
        # deux formes de degat de groupe : `predefined` [min,max] (RandomAmount natif, pas de spread)
        # OU `amount` seul -> spread ±20% standard du per-coup. L'amount peut etre un ConfigVar entier
        # (FoulInfusion #57c-C) ou le MIDPOINT x.5 du noeud Average natif (FleshmetalGuns #65) ->
        # pas de troncature int (le spread Fix64 from_number est exact sur les .5).
        _pre = _grp.get("predefined")
        _amt = _grp.get("amount") or 0

        # #57d : member-cap Swarm per-COUP — le groupe porte le flag HitsMultipleMembers de SON profil
        # (natif : IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit recoit le DamageProfile du coup courant).
        _ghmm = _grp.get("profile_has_hits_multiple_members")
        _gtl = (target_limits if _ghmm is None or not target_limits
                else {**target_limits, "profile_has_hits_multiple_members": bool(_ghmm)})

        def _ghit(prev: "BlockScenario", _pre=_pre, _amt=_amt, _gp=_grp.get("pierce_pct", pierce_pct),
                  _gpt=_grp.get("profile_type", profile_type), _gm=_grp.get("mods"),
                  _gtl=_gtl) -> DamagePredictionResult:
            return predict_attack_raw(
                prev, _amt, profile_type=_gpt, armor=armor, pierce_pct=_gp, mods=_gm, hit_mult=hit_mult,
                reduction_min=reduction_min, reduction_max=reduction_max, spread_pct=spread_pct,
                target_current_health=target_current_health, target_shield=target_shield,
                target_limits=_gtl, predefined=_pre, might_crit=might_crit,
                attacker_effects=attacker_effects)
        for _j in range(max(0, int(_grp.get("count", 0)))):
            result.add(_with_block(_ghit(result.default_block_scenario())))
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
        shield_raw: MinMaxDamage | None = None,
        extra_groups: "list[dict] | None" = None,
        defender_block_amount: int | None = None,
        attacker_effects=None) -> DamagePredictionResult:
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
        target_limits=target_limits, extra_groups=extra_groups,
        defender_block_amount=defender_block_amount, attacker_effects=attacker_effects)
