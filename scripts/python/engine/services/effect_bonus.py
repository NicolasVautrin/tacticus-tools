"""Port FIDÈLE de `IdunBattle.Entities.Effects.EffectBonus` (gqfc5mff6c).

Chaque effet construit sa contribution de dégât/coups via ces fabriques (RE : ce sont les seules
sources de bonus que le builder modifier consomme — cf. playbook-engine.md §17). Le `CreateEffect*
ForAttack` d'un effet appelle l'une d'elles avec une **constante de config** (`DSLFactory.ConfigConst`)
comme magnitude, puis renvoie un `EffectBonus` (Nullable). Ex. confirmé :
  RapidAssault_ExtraDamageEffect.CreateEffectDamageBonusForAttack @180f67940 :
      = EffectBonus.ForPercentIncrease(ownerIsCaster, ConfigConst(effect, 0xf=extraDmgPct))

`EffectBonus.ForPercentIncrease` @180f40850 = pur emballage `{ownerIsCaster, value}` (AUCUNE condition ;
les conditions sont (a) la présence de l'effet — cycle de vie triggers — et (b) la logique propre du
`CreateEffect*ForAttack` de chaque effet, portée par-effet). Famille des fabriques (toutes @180f40xxx) :
ForPercentIncrease/ForPercentDecrease/ForAddition/ForSubtraction/ForPiercing/ForOverride/ForReset
+ CappedEffectBonus.Create (variante avec plafond).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EffectBonus:
    """Mirror de `EffectBonus` (struct valeur). On garde le strict nécessaire au calcul du modifier.

    `kind` = la fabrique d'origine ; `value` = sa magnitude (pct pour Percent*, montant pour
    Addition/Subtraction, ratio pour Piercing, valeur pour Override) ; `owner_is_caster` = à qui le
    bonus s'applique (l'attaquant pour un buff offensif) ; `cap` = plafond (CappedEffectBonus, None=∞)."""
    kind: str
    value: int = 0
    owner_is_caster: bool = True
    cap: int | None = None


# EffectBonus.ForPercentIncrease @180f40850 — +value % (multiplicatif 1+value/100)
def for_percent_increase(owner_is_caster: bool, value: int,
                         cap: int | None = None) -> EffectBonus:
    return EffectBonus("PercentIncrease", value, owner_is_caster, cap)


# EffectBonus.ForPercentDecrease @180f40760 — −value % (multiplicatif 1−value/100)
def for_percent_decrease(owner_is_caster: bool, value: int,
                         cap: int | None = None) -> EffectBonus:
    return EffectBonus("PercentDecrease", value, owner_is_caster, cap)


# EffectBonus.ForAddition @180f406e0 — +value plat (additif). Écrit le champ DamageBonus (+5) de
# l'EffectBonus → `DamageModifiers.Add @181005f10` fait `additif @+0x10 += FromInt(v)`, appliqué
# APRÈS perçage/armure (`CalculateBaseDamageWithAllModifiers @18102d3f0`). Il n'existe PAS de canal
# additif « de base » pré-perçage dans le natif (cf. #69 : kind « BaseAddition » inventé retiré).
def for_addition(owner_is_caster: bool, value: int) -> EffectBonus:
    return EffectBonus("Addition", value, owner_is_caster)


# EffectBonus.ForSubtraction @180f409b0 — −value plat (additif)
def for_subtraction(owner_is_caster: bool, value: int) -> EffectBonus:
    return EffectBonus("Subtraction", value, owner_is_caster)


# Réduction DYNAMIQUE CAPÉE : `ForSubtraction(Min(PercentageOf(CurrentDamage, pct), cap))` — soustrait
# `min(pct% × dégât_courant, cap)` du dégât REÇU. `value` = pct, `cap` = plafond ABSOLU de la réduction
# (≠ la sémantique `cap` de CappedEffectBonus qui plafonne le RÉSULTAT). Ex. GuardianOrganism_DamageReduction
# @180f4c630 : pct=ConfigVar(0x46=dmgReductionPct), cap=ConfigVar(0x12=dmgReduction). Appliqué APRÈS le
# %-list + additif (CurrentDamage = dégât post-mods), cf. `apply_all_modifiers`. `cap=None` = non plafonné.
def for_percent_subtraction_capped(owner_is_caster: bool, pct: int,
                                   cap: int | None = None) -> EffectBonus:
    return EffectBonus("PercentSubtractionCapped", pct, owner_is_caster, cap)


# EffectBonus.ForPiercing @180f40890 — bonus de PERÇAGE (axe armure, pas le scalaire dégât).
# Alimente le champ pierce-extra du DamageModifiers (struct @0x20) sommé dans
# CalculateBaseDamageWithAllModifiers @18102d3f0 → pierce_eff = clamp(pierce + extra, 0, 100).
def for_piercing(owner_is_caster: bool, value: int) -> EffectBonus:
    return EffectBonus("Piercing", value, owner_is_caster)


# Axe ARMOR-PENETRATION (struct DamageModifiers @0x28) — `armor_eff = max(FixedArmor − pénétration, 0)`
# (CalculateBaseDamageWithAllModifiers @18102d3f0 ; sommé attaquant+défenseur). Source par-effet =
# méthode d'interface dédiée (ex. KanOpenerEffect.IgnoreArmor @180f65100 = ConfigVar key 0x40), PAS
# CreateEffectDamageBonusForAttack (qui n'alimente que additif/percent via DamageModifiers.Add).
def for_armor_penetration(owner_is_caster: bool, value: int) -> EffectBonus:
    return EffectBonus("ArmorPenetration", value, owner_is_caster)


# Ignore-armure TOTALE (pénétration ≥ armure) — `armor_eff = 0`. Variante booléenne pour les effets
# « ignore l'armure » sans valeur numérique de pénétration.
def for_ignore_armor(owner_is_caster: bool = True) -> EffectBonus:
    return EffectBonus("IgnoreArmor", 0, owner_is_caster)
