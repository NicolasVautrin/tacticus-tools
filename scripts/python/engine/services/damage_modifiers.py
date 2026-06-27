"""Port FIDÈLE de la COUCHE MODIFIER native (gqfc5mff6c) — RE intégrale + tracée live, doc §17.

Classes/fonctions natives portées 1:1 (VA citée) :
  • `IdunBattle.Core.Services.DamageModifiers`           (accumulateur)  Empty@181006370 / Add@181005f10
  • `DamageCalculations.GetMultiplierFromDamageBonus`    @181005210      (1 ± pct/100)
  • `DamageCalculations.ApplyCappedModifiers`            @181000020      (réducteur : v=clamp(round(v×mult),±cap))
  • `DamageCalculations.CalculateAttackerModifiersForPrediction` @181000590  (builder = boucle sur param_5)
  • leaves positionnels : CalculateElevationBonusModifier@181003ea0 /
    CalculateRangedInMeleeReduction@181004700 / CalculateTrenchReduction@181004830

CHAÎNE (RE §17, tracée live §17.7) : dans `PredictAttackRaw`, `CalculateBaseDamageWithAllModifiers`
applique le modifier **par coup, APRÈS perçage/armure** via `ApplyCappedModifiers`. `param_5` (la liste
de sources) = **les EFFETS actifs de l'unité** (interface effets `DAT_1831b7938` slot 9, §17.8) — chacun
fournit sa contribution via `CreateEffect*ForAttack` (→ `EffectBonus`). Donc le builder = « pour chaque
effet actif, ajoute sa contribution à l'accumulateur ».

⚠ Zones d'ombre (generic-sharing / non tranché statiquement, marquées HYPOTHÈSE) : (a) placement exact
de l'`additif` plat (Addition/Subtraction) vs le `%-list` — ici additif appliqué après le %-list ;
(b) arrondi Fix64 mode 1 ≈ `round()` Python (résidu ±1-3 connu).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .effect_bonus import EffectBonus


@dataclass
class DamageModifiers:
    """Accumulateur `DamageModifiers` (struct ~0x40 : additif@+0x10, %-list@+0x18, mult@+0x30=1,
    detail@+0x38). `pct_list` = liste de `(mult, cap)` (mult=1±pct/100 ; cap=None si non plafonné)."""
    additive: float = 0.0
    pct_list: list[tuple[float, int | None]] = field(default_factory=list)
    multiplicative: float = 1.0
    details: list[EffectBonus] = field(default_factory=list)
    # axe ARMURE/PERÇAGE (champs du DamageModifiers natif lus par CalculateBaseDamageWithAllModifiers
    # @18102d3f0 → GetBaseDamageWithFixedPiercedArmor) — distinct du scalaire dégât (additif/%-list) :
    extra_pierce: int = 0          # @0x20 : pierce_eff = clamp(pierce + extra_pierce, 0, 100)
    armor_penetration: int = 0     # @0x28 : armor_eff = max(FixedArmor − armor_penetration, 0)
    ignore_armor: bool = False     # ignore-armure totale → armor_eff = 0 (pénétration ≥ armure)

    @classmethod
    def empty(cls) -> "DamageModifiers":
        """DamageModifiers.Empty @181006370 : additif=0, mult=One, listes vides, pas de pénétration."""
        return cls()


def get_multiplier_from_damage_bonus(bonus_pct: int) -> float:
    """DamageCalculations.GetMultiplierFromDamageBonus @181005210 :
        b ≥ 1  → 1 + b/100      (bonus)
        b < 1  → 1 − |b|/100     (réduction ; b ≤ 0)."""
    if bonus_pct < 1:
        return 1.0 - (-bonus_pct) / 100.0
    return 1.0 + bonus_pct / 100.0


def add_modifier(acc: DamageModifiers, eb: EffectBonus) -> None:
    """DamageModifiers.Add @181005f10 — intègre UNE contribution d'effet dans l'accumulateur.
      • Addition/Subtraction  → additif ±= value (plat)
      • PercentIncrease/Decrease → %-list.Add((GetMultiplierFromDamageBonus(±value), cap))
      • detail-list .Add (bookkeeping)
    (Piercing/Override = axes séparés — non intégrés au scalaire dégât ici.)"""
    if eb.kind == "Addition":
        acc.additive += eb.value
    elif eb.kind == "Subtraction":
        acc.additive -= eb.value
    elif eb.kind in ("PercentIncrease", "PercentDecrease"):
        pct = eb.value if eb.kind == "PercentIncrease" else -eb.value
        acc.pct_list.append((get_multiplier_from_damage_bonus(pct), eb.cap))
    elif eb.kind == "Piercing":
        acc.extra_pierce += eb.value            # axe perçage (@0x20) — pas le scalaire dégât
    elif eb.kind == "ArmorPenetration":
        acc.armor_penetration += eb.value       # axe armure (@0x28)
    elif eb.kind == "IgnoreArmor":
        acc.ignore_armor = True                 # ignore-armure totale → armor_eff = 0
    acc.details.append(eb)


def apply_capped_modifiers(value: int, mods: DamageModifiers) -> int:
    """DamageCalculations.ApplyCappedModifiers @181000020 — réducteur du `%-list` :
        POUR CHAQUE (mult, cap) : value = clamp(round(value × mult), −cap, +cap).
    (Le `%-list` SEUL est appliqué ici, fidèle au natif. L'`additif` plat est appliqué à part —
    cf. apply_all_modifiers.)"""
    v = value
    for mult, cap in mods.pct_list:
        v = round(v * mult)
        if cap is not None:
            v = max(-cap, min(cap, v))
    return v


def apply_all_modifiers(value: int, mods: DamageModifiers) -> int:
    """Combinaison %-list + additif (le terme appliqué par `CalculateBaseDamageWithAllModifiers`
    @18102d3f0 au dégât per-coup post-perçage). HYPOTHÈSE sur l'ordre additif/%-list (non tranché
    statiquement) : %-list capés PUIS additif plat. Plancher ≥ 0."""
    v = apply_capped_modifiers(value, mods)
    if mods.additive:
        v = round(v + mods.additive)
    return max(0, v)


def build_attacker_modifiers(effect_bonuses: list[EffectBonus | None]) -> DamageModifiers:
    """DamageCalculations.CalculateAttackerModifiersForPrediction @181000590 — boucle sur `param_5`
    (= les EFFETS actifs de l'unité, §17.8) et accumule chaque contribution. `effect_bonuses` =
    [effet.CreateEffectDamageBonusForAttack(...) pour chaque effet actif] (None = pas de contribution)."""
    acc = DamageModifiers.empty()
    for eb in effect_bonuses:
        if eb is not None:
            add_modifier(acc, eb)
    return acc


# ─── Leaves positionnels (chacun = un `EffectBonus` selon la position/terrain) ──────────────────────

def calculate_elevation_bonus_modifier(
        attacker_elevation: int, target_elevation: int, elevation_pct: int,
        attacker_or_target_has_no_elev_effect: bool = False) -> EffectBonus | None:
    """CalculateElevationBonusModifier @181003ea0 : +ElevationPercentage (config) si la tuile de
    l'attaquant est PLUS HAUTE que celle de la cible. Sauté si l'attaquant OU la cible a l'effet
    0x423 (`attacker_or_target_has_no_elev_effect`). Renvoie None sinon."""
    if attacker_or_target_has_no_elev_effect:
        return None
    if attacker_elevation > target_elevation:
        return EffectBonus("PercentIncrease", elevation_pct, owner_is_caster=True)
    return None


def calculate_ranged_in_melee_reduction(
        should_apply: bool, ranged_in_melee_reduction_pct: int) -> EffectBonus | None:
    """CalculateRangedInMeleeReduction @181004700 → ShouldApplyRangedInMelee @181005810 :
    si un attaquant RANGED (trait 0xb) est adjacent à un ennemi melee-able → −RangedInMeleeReduction
    (config). `should_apply` = résultat de ShouldApplyRangedInMelee (adjacence résolue en amont)."""
    if should_apply:
        return EffectBonus("PercentDecrease", ranged_in_melee_reduction_pct, owner_is_caster=True)
    return None


def calculate_trench_reduction(
        target_on_trench_adjacent: bool, trench_reduction_pct: int) -> EffectBonus | None:
    """CalculateTrenchReduction @181004830 : cible sur tuile trench + conditions d'adjacence →
    −TrenchReduction (config). `target_on_trench_adjacent` = conditions résolues en amont."""
    if target_on_trench_adjacent:
        return EffectBonus("PercentDecrease", trench_reduction_pct, owner_is_caster=True)
    return None
