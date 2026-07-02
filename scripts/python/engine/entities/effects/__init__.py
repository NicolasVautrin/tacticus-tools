"""`engine.entities.effects` — port des effets de combat `IdunBattle.Entities.Effects.*` en hiérarchie
de classes (BaseEffect + sous-classes 1:1 + factory + registre), remplaçant l'ancien registre de données
(`effects_damage_bonus.EffectDef`). Mirror fidèle du modèle natif « 1 classe par effet ».

API :
  • `BaseEffect` / sous-classes (loki.py …) — 1 classe par effet, override des méthodes implémentées.
  • `EffectFactory` / `EFFECT_CLASSES` — instancie la bonne classe depuis un effet capté.
  • `build_attacker_modifiers_from_effects(effects)` → `DamageModifiers` (builder
    `CalculateAttackerModifiersForPrediction` : itère les effets ACTIFS, agrège damage-bonus + pénétration).
  • `hits_bonus_from_effects(effects)` → int (axe COUPS, `CreateEffectHitsBonusForAttack`).
`effects` accepte des instances `BaseEffect` (déjà matérialisées/filtrées par EffectsState) OU des dicts
captés (matérialisés à la volée via la factory).
"""
from __future__ import annotations

from collections.abc import Mapping

from ...services.damage_modifiers import (
    DamageModifiers, build_attacker_modifiers, build_defender_modifiers,
)
from ...services.effect_bonus import for_armor_penetration
from .base import BaseEffect, SubEffectSpec, SAME_TURNS
from .factory import EFFECT_CLASSES, EffectFactory
from .loki import (
    KanOpenerEffect,
    PowerTripFullHealthEffect,
    PowerTripIgnoreArmorEffect,
    RapidAssaultExtraDamageEffect,
    StunnedEffect,
)

__all__ = [
    "BaseEffect", "SubEffectSpec", "SAME_TURNS", "EffectFactory", "EFFECT_CLASSES",
    "RapidAssaultExtraDamageEffect", "PowerTripFullHealthEffect",
    "PowerTripIgnoreArmorEffect", "KanOpenerEffect", "StunnedEffect",
    "build_attacker_modifiers_from_effects", "build_defender_modifiers_from_effects",
    "hits_bonus_from_effects", "hits_malus_from_defender_effects", "aura_hits_malus_for_defense",
    "crit_chance_bonus_from_effects", "crit_damage_bonus_from_effects",
]


def _as_effects(effects) -> list[BaseEffect]:
    """Normalise une liste hétérogène (instances BaseEffect ou dicts captés) → instances BaseEffect."""
    out: list[BaseEffect] = []
    for e in (effects or []):
        if isinstance(e, BaseEffect):
            out.append(e)
        elif isinstance(e, Mapping) and e.get("name"):
            out.append(EffectFactory.create(e))
    return out


def build_attacker_modifiers_from_effects(effects, is_ranged: bool | None = None,
                                          is_normal_attack: bool = True,
                                          has_moved: bool | None = None) -> DamageModifiers:
    """`CalculateAttackerModifiersForPrediction` @181000590 — DamageModifiers depuis les effets ACTIFS de
    l'attaquant (§17.8). Agrège : damage-bonus (additif/percent, `create_effect_damage_bonus_for_attack`)
    + pénétration d'armure (`get_armor_penetration` → axe armure). Les effets doivent être déjà filtrés
    actifs (EffectsState.active_effects) ; si on passe des dicts, AUCUN filtre is_active n'est appliqué.
    `is_ranged` = nature du coup → bonus gated `IsRangedAttack` (HeavyWeapon, RangedSpecialist).
    `is_normal_attack` → pénétrations gated normal-only (PowerTrip_IgnoreArmor, step-13 ground truth).
    `has_moved` = candidat avec déplacement → bonus gated no-move (HeavyWeapon @180f4f030)."""
    bonuses = []
    for e in _as_effects(effects):
        db = e.create_effect_damage_bonus_for_attack(is_ranged, has_moved)
        if db is not None:
            bonuses.append(db)
        pen = e.get_armor_penetration(is_normal_attack)
        if pen is not None:
            bonuses.append(for_armor_penetration(True, pen))
    return build_attacker_modifiers(bonuses)


def build_defender_modifiers_from_effects(effects, is_melee: bool | None = None,
                                          damage_profile: str | None = None) -> DamageModifiers:
    """`CalculateDefenderModifiersForPrediction` @181002c30 — DamageModifiers depuis les effets de la CIBLE
    (réductions de dégât reçu). Agrège `create_effect_damage_malus_for_defense` (slot 0x1a). Symétrique de
    `build_attacker_modifiers_from_effects`. Effets déjà filtrés actifs (EffectsState.active_effects).
    `is_melee` = nature du coup (propagée aux malus gated `IsMeleeAttack`, ex. Terrifying_ExtraDefense) ;
    `damage_profile` = NOM du profil de dégât de l'attaque (propagé aux malus gated `DamageProfileIs`, ex.
    TerminatorArmour -75% SAUF Psychic/DirectDamage).
    ⚠ Couvre la famille `ADamageDefenseModifierAbilityEffect` (EffectBonus PercentDecrease ConfigVar gated) +
    Terrifying_ExtraDefense + TerminatorArmour_ReduceDmg (CreateDamageModifier trigger-based) ; les réductions
    par STAT (Defense), par COUPS (Parry_ReduceHits) ou par TRIGGER (predOptimistic) sont des axes SÉPARÉS
    (cf. docs/rl/runner-engine.md §1.8)."""
    maluses = []
    for e in _as_effects(effects):
        mb = e.create_effect_damage_malus_for_defense(is_melee, damage_profile)
        if mb is not None:
            maluses.append(mb)
    return build_defender_modifiers(maluses)


def hits_bonus_from_effects(effects, is_normal_attack: bool = True) -> int:
    """Σ des bonus de COUPS (`CreateEffectHitsBonusForAttack`) des effets actifs (axe hits, ex.
    PowerTrip_FullHealth). Addition = +value, Subtraction = −value."""
    total = 0
    for e in _as_effects(effects):
        hb = e.create_effect_hits_bonus_for_attack(is_normal_attack)
        if hb is None:
            continue
        if hb.kind == "Addition":
            total += hb.value
        elif hb.kind == "Subtraction":
            total -= hb.value
    return total


def hits_malus_from_defender_effects(effects, is_melee: bool | None = None,
                                     damage_profile: str | None = None) -> int:
    """Σ des modifications de COUPS des effets actifs de la CIBLE (`create_effect_hits_malus_for_defense`,
    ex. LightCover @180f556b0 : -2 ranged ; Parry @180f5d860 : -1 mêlée ; MasterAnnihilator
    @180f58d50 : +1 non-Psychic). Natif = même canal `CreateEffectHitsBonusForAttack` trigger
    `OwnerIsTarget` ; plancher min=1 appliqué chez le consommateur (`max(1, …)`).
    Retour signé (à ADDITIONNER aux hits)."""
    total = 0
    for e in _as_effects(effects):
        hb = e.create_effect_hits_malus_for_defense(is_melee, damage_profile)
        if hb is None:
            continue
        if hb.kind == "Addition":
            total += hb.value
        elif hb.kind == "Subtraction":
            total -= hb.value
    return total


def aura_hits_malus_for_defense(units_effects, ctx) -> int:
    """Σ des malus de COUPS projetés sur la CIBLE par des effets AURA possédés par d'AUTRES unités
    (`create_aura_hits_malus_for_defense`, ex. BigTargetAdjacentEffect @180f33ac0 : -1 ranged pour
    les alliés ring-1 du porteur). `units_effects` = itérable de (owner_id, owner_pos, owner_team,
    effets du porteur) ; `ctx` = {tgt_id, t_pos, tgt_team, is_melee}. Plancher min=1 chez le
    consommateur. Retour ≤ 0 (à ADDITIONNER aux hits)."""
    total = 0
    for owner_id, owner_pos, owner_team, effects in (units_effects or []):
        octx = {**(ctx or {}), "owner_id": owner_id, "owner_pos": owner_pos,
                "owner_team": owner_team}
        for e in _as_effects(effects):
            hb = e.create_aura_hits_malus_for_defense(octx)
            if hb is None:
                continue
            if hb.kind == "Addition":
                total += hb.value
            elif hb.kind == "Subtraction":
                total -= hb.value
    return total


def crit_chance_bonus_from_effects(effects) -> int:
    """Σ des bonus de CHANCE de crit des effets ACTIFS de l'attaquant
    (`DamagePrediction.GetCritChanceBonusFromEffects`@181031180) — couche calc-time ajoutée à
    `GetStat(9)` dans RollCritical (PAS dans GetStat ⇒ pas dans le combatSnapshot ⇒ à sommer ici).
    No-op (0) tant qu'aucun effet n'override `create_effect_crit_chance_bonus_for_attack`."""
    total = 0
    for e in _as_effects(effects):
        b = e.create_effect_crit_chance_bonus_for_attack()
        if b is not None:
            total += b
    return total


def crit_damage_bonus_from_effects(effects) -> int:
    """Σ des bonus de DÉGÂT de crit des effets ACTIFS de l'attaquant
    (`DamagePrediction.GetCritDamageBonusFromEffects`@181031bb0) — couche calc-time ajoutée à
    `GetStat(10)` dans CalculateCriticalDamage. No-op (0) tant qu'aucun effet n'override
    `create_effect_crit_damage_bonus_for_attack`."""
    total = 0
    for e in _as_effects(effects):
        b = e.create_effect_crit_damage_bonus_for_attack()
        if b is not None:
            total += b
    return total
