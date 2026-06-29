"""Effets du namespace natif `IdunBattle.Entities.Effects.Loki` — 1 classe par effet (VA citée).

Chaque classe override UNIQUEMENT ce qu'elle implémente dans le natif (lu en ghidra). Les magnitudes
non encore confirmées par nom gameconfig renvoient None (pas de contribution) = on N'INVENTE PAS de
valeur non prouvée (cf. doc §17.4 « présent ≠ appliqué »). RapidAssault = seul cas magnitude validé.
"""
from __future__ import annotations

from collections.abc import Mapping

from ...services.effect_bonus import EffectBonus, for_addition, for_percent_increase
from .base import BaseEffect, SubEffectSpec, SAME_TURNS
from .magnitude import ability_var, trait_var


class RapidAssaultExtraDamageEffect(BaseEffect):
    """`RapidAssault_ExtraDamageEffect` (effet 0x4cd=1229).
    - dégât @180f67940 : `ForPercentIncrease(ConfigConst key 0xf)` = trait var `rapidAssaultExtraDmgPct` (=25, scalaire).
    - cycle de vie : posé à l'init d'ability (`RapidAssaultAbility.CreateBehaviour` @181224950 `AddEffect(0x4cd)`),
      RETIRÉ en fin de tour si l'unité a attaqué (`RemoveExtraDamageEffectAbility.CreateTrigger` @181224af0 =
      `On(0x17) & UnitsAttackedThisTurn>0 & HasEffect(0x4cd)`).
    VALIDÉ live : +25% → u94→u84 3012-4524 EXACT."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None) -> EffectBonus | None:
        pct = trait_var("RapidAssault", "rapidAssaultExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None

    @property
    def removed_after_attack(self) -> bool:
        return True


class HeavyWeaponExtraDmgEffect(BaseEffect):
    """`HeavyWeapon_ExtraDmgEffect` (effet 1008 ; ctor `DamageModifierAbilityEffect(0x3e9)`).
    - dégât `CreateDamageModifier` @180f4f030 : `EffectBonus.ForPercentIncrease(cond, amount)` où
      `amount = ConditionalAmount(TriggeringAbilityIs(0x3ec) ? amount×2 : amount)`, `amount = ConfigConst
      key 0xf` = trait var `heavyWeaponExtraDmg` (=25, scalaire) ; condition = `OwnerIsCaster &
      IsRangedAttack & flags`. ⇒ **+25% de dégât sur les attaques RANGED** (le ×2 si l'ability
      déclenchante est 0x3ec = raffinement non porté ; l'attaque normale/overwatch n'est pas 0x3ec).
    Porté par le trait HeavyWeapon (qui accorde aussi l'Overwatch) → s'applique au tir d'overwatch."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None) -> EffectBonus | None:
        if not is_ranged:                        # gated IsRangedAttack (no-op sur mêlée / contexte inconnu)
            return None
        pct = trait_var("HeavyWeapon", "heavyWeaponExtraDmg")
        return for_percent_increase(True, pct) if pct is not None else None


class PowerTripFullHealthEffect(BaseEffect):
    """`PowerTrip_FullHealthEffect` — axe COUPS (hits), actif SSI PV pleins.
    - hits @180f64cf0 : `ForAddition(ConfigConst key 0x2b)` = constante `extraHit` de l'ability PowerTrip (=1).
    - condition @180f64cb0 : `!IsDamaged` (hp == max).
    MAGNITUDE résolue : `gameconfig.ability('PowerTrip').constants['extraHit']` = 1 → +1 coup quand PV pleins."""

    def create_effect_hits_bonus_for_attack(self) -> EffectBonus | None:
        n = ability_var("PowerTrip", "extraHit", is_constant=True)   # key 0x2b → constante extraHit (=1)
        return for_addition(True, n) if n else None

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        s = unit_state or {}
        hp, mx = s.get("hp"), s.get("max_hp")
        if hp is None or mx is None:        # max_hp non capté → ne pas masquer l'effet à tort
            return True
        return hp >= mx


class PowerTripIgnoreArmorEffect(BaseEffect):
    """`PowerTrip_IgnoreArmorEffect` — « Normal attacks ignore X Armour » = axe PÉNÉTRATION.
    ⚠ Le natif `PowerTrip_IgnoreArmorEffect.CreateEffectDamageBonusForAttack` @180f64fa0 = NO-OP
    (EffectBonus condition-seule, valeur 0) ; la pénétration est en fait bâtie DIRECTEMENT dans
    `CalculateAttackerModifiersForPrediction` @181000590 (lit la config PowerTrip de l'attaquant), pas
    portée par l'effet — pattern d'exploitation directe (cf. §17.17). On l'attribue ICI (l'effet
    représente la présence de PowerTrip ⇒ sa présence GATE correctement la pénétration : normal attack,
    owner=caster). Magnitude = `armorIgnored[level] × AbilityVariablesMultiplierPercentage/100` arrondi
    (§17.21, var flaggée `variablesAffectedByRarityBonus`). VÉRIFIÉ live u90 : 277 × 1.8 = round(498.6)
    = 499 = pénétration @0x28 attaquant ⇒ per-bout u90→u86 [341,1265], ×6 = oracle [2048,7592].
    `armorReduction` (full-health) = axe SÉPARÉ (debuff stateful de la stat FixedArmor cible, hors
    prédiction — la prédiction lit l'armure courante) → non porté ici (cf. PowerTrip_OnAttackAbility)."""

    def get_armor_penetration(self) -> int | None:
        # armorIgnored indexé par le niveau de l'ABILITY (passive, =50), PAS le stack level (=1), scalé par
        # le multiplier de l'unité. `ability_level` seedé depuis l'unité ; fallback `level` si absent.
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var("PowerTrip", "armorIgnored", lvl,
                           multiplier_pct=self.ability_variables_multiplier)


class StunnedEffect(BaseEffect):
    """`StunnedEffect` (effet COMPOSITE 0x48a=1162) — `ApplyInternal` @180f6eb30 spawne 3 SOUS-effets
    quand Stunned est appliqué (confirmé live : parent rem=1 + enfants 1165 rem=1, 1166/1167 rem=0) :
      - `AddBlockAbilitiesSubEffect` @180f6e870 → 0x48d=1165 Stunned_CantUseAbility, via
        `AddSubEffectWithSameTurns` ⇒ MÊME durée que le parent.
      - `ApplyMovementModifier` @180f6ef30 → 0x48e=1166 Stunned_MovementOverride, via
        `AddStatOverrideEffect` (durée 0 = permanent/lié au parent) ; gardé par `StatAmount(movement)>0`
        côté natif (simplification ici : toujours spawné — la quasi-totalité des units ont movement>0 ;
        reverté par `ResetMovementModifier`).
      - `ApplyDamageModifier` @180f6e9b0 → 0x48f=1167 Stunned_DamageModifier, via `AddEffect(turns=0)`
        (permanent/lié au parent ; reverté par `ResetDamageModifier`).
    Les enfants portent `parent_type=1162` (lien `ParentEffect@+0x70`) ; ils n'ont pas eux-mêmes de
    sous-effets. VALIDÉ live (templSwordBrother/ThunderousAssault → tyranTyrantGuard)."""

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            SubEffectSpec(0x48d, "Stunned_CantUseAbility", turns=SAME_TURNS),  # AddSubEffectWithSameTurns
            SubEffectSpec(0x48e, "Stunned_MovementOverride", turns=0),         # AddStatOverrideEffect (cond. mvt>0)
            SubEffectSpec(0x48f, "Stunned_DamageModifier", turns=0),           # AddEffect turns=0
        ]


class KanOpenerEffect(BaseEffect):
    """`KanOpenerEffect` (triggered) — `IgnoreArmor` @180f65100 = `ConfigVar(key 0x40)` = pénétration
    d'armure per-niveau (axe armure, contrairement à PowerTrip dont la réduction est stateful on-attack).
    ⚠ KillaKan n'a PAS KanOpener (kit = PowerTrip) ; clé 0x40 → nom var gameconfig non résolu pour les
    unités qui l'ont → pénétration None tant qu'inconnue (à mapper quand on porte une unité KanOpener)."""

    def get_armor_penetration(self) -> int | None:
        # TODO: mapper la clé 0x40 → var gameconfig (per-niveau) puis return ability_var(..., self.level).
        return None
