"""Effets Imperative de DoctrinaImperatives (Tan Gi'da / admecMarshall, namespace natif `Effects.Loki`).

RE (build gqfc5mff6c) : `DoctrinaImperativesAbility.ExecuteBehaviour @1811d4d20` bascule (toggle) entre
DEUX effets mutuellement exclusifs poses sur le caster (via `AddDynamicStatModifierEffectToOwner` /
`AddEffect`, cf. `runner/abilities/loki/imperative.py`) :

  - **ProtectorImperativeEffect** (0x4df=1247) : `DynamicStatModifierEffect` +extraArmor sur la stat
    **FixedArmor(16)** (arg `stat=0x10` du helper @180de6560 = 16 ; GROUND-TRUTH live statModSources :
    +886 FixedArmor, residual 0). Aura self + Mechanical ADJACENTS dans le natif (selecteur de l'effet) ;
    ce port (increment A) materialise le stat-mod SELF (sur le caster) via `applied_stat_mods` — la PORTEE
    aux allies Mechanical adjacents (canal aura +FixedArmor neuf, re-evalue par adjacence) = increment B.

  - **ConquerorImperativeEffect** (0x4e0=1248) : `DamageModifierAbilityEffect` +extraDmg gate
    `HasNegativeModifier(cible, FixedArmor<0)` (@180f39650 = "vs armure reduite"), aura self + Mechanical
    adjacents. Increment A : effet PRESENT (le toggle fonctionne) mais contribution +dmg DIFFEREE
    (increment C : canal `create_effect_damage_bonus_for_attack` + gate HasNegativeModifier + portee aura) —
    degradation fidele "present != applique" (BaseEffect = contribution None).

Magnitudes = `ability_var("DoctrinaImperatives", "extraArmor"/"extraDmg", activeAbilityLevel, mult)` (les deux
in `variablesAffectedByRarityBonus` -> multiplier applique ; max 582 @lvl65). Le stat-mod SELF est mirror du
pattern eager canonique `ActOfFaithBuffEffect.applied_stat_mods` (materialise par `AddEffectOperation.
_apply_stat_mods` via `apply_change_stat`, revert par-source via la feuille `RemoveEffect` + `reverted_stats`).
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var

_ABILITY = "DoctrinaImperatives"


def _active_level_mult(stats_ctx):
    """(activeAbilityLevel, multiplier%) du porteur — DoctrinaImperatives est une ability ACTIVE, ses vars
    s'indexent sur `active_ability_level` et sont rarity-scaled (`ability_variables_multiplier`)."""
    lvl = getattr(stats_ctx, "active_ability_level", None)
    if lvl is None:
        lvl = getattr(stats_ctx, "ability_level", None)
    lvl = int(lvl) if lvl is not None else 0
    mult = int(getattr(stats_ctx, "ability_variables_multiplier", 100) or 100)
    return lvl, mult


class ProtectorImperativeEffect(BaseEffect):
    """`ProtectorImperativeEffect` (0x4df=1247) — stat-mod **FixedArmor(16)** += `extraArmor[level]` x mult.

    Pose sur le caster par la branche ELSE du toggle (`AddDynamicStatModifierEffectToOwner(0x4df, stat=0x10)`
    @1811d4d20) ; l'observable live = +886 FixedArmor keye par l'entite-effet (statModSources, residual 0).
    Le natif projette AUSSI ce stat-mod aux allies Mechanical ADJACENTS (aura) — non couvert ici (increment B :
    canal aura +FixedArmor re-evalue par adjacence). Ce que ce port materialise = le buff SELF (part du buff
    natif ou le caster = self ∈ selector) via `applied_stat_mods` (eager ChangeStat, mirror StandVigil/ActOfFaith).
    """
    stat_mod_source = None   # cle de source ChangeStat (revert par-source via la feuille RemoveEffect)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """DATA du `ChangeStat` (part 5/9) pose a l'application : FixedArmor += extraArmor[level] x mult.
        Symetrique de `reverted_stats()`. `stats_ctx` = `StatsComponent.ctx` du porteur (self-cast : porteur ==
        caster == la source du niveau)."""
        from ...stats import StatType
        lvl, mult = _active_level_mult(stats_ctx)
        amt = ability_var(_ABILITY, "extraArmor", lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.FIXED_ARMOR), int(amt))]

    def reverted_stats(self) -> "list":
        """`RevertInternal` — annule le ChangeStat FixedArmor (lu par la feuille `RemoveEffect` pour
        `revert_change_stat(..., stat_mod_source)` par-source, au toggle vers Conqueror)."""
        from ...stats import StatType
        return [StatType.FIXED_ARMOR]


class ConquerorImperativeEffect(BaseEffect):
    """`ConquerorImperativeEffect` (0x4e0=1248) — `DamageModifierAbilityEffect` +extraDmg gate
    `HasNegativeModifier(cible, FixedArmor<0)` (@180f39650), aura self + Mechanical adjacents (@180f39890).

    Increment A : effet PRESENT (materialise sur le caster par la branche THEN du toggle -> le toggle Protector
    <-> Conqueror fonctionne) mais SANS contribution +dmg (BaseEffect = None). La contribution
    (`create_effect_damage_bonus_for_attack` = +`extraDmg[level]` x mult FLAT, gate cible-a-armure-reduite,
    + portee aura aux allies Mechanical adjacents) = increment C. Degradation fidele "present != applique".
    """
    # increment C : create_effect_damage_bonus_for_attack (ForAddition, gate HasNegativeModifier(target
    # FixedArmor<0)) + portee aura self+Mechanical-adjacents. Volontairement non implemente ici.
