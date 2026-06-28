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
from .base import BaseEffect
from .factory import EFFECT_CLASSES, EffectFactory
from .loki import (
    KanOpenerEffect,
    PowerTripFullHealthEffect,
    PowerTripIgnoreArmorEffect,
    RapidAssaultExtraDamageEffect,
)

__all__ = [
    "BaseEffect", "EffectFactory", "EFFECT_CLASSES",
    "RapidAssaultExtraDamageEffect", "PowerTripFullHealthEffect",
    "PowerTripIgnoreArmorEffect", "KanOpenerEffect",
    "build_attacker_modifiers_from_effects", "build_defender_modifiers_from_effects",
    "hits_bonus_from_effects",
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


def build_attacker_modifiers_from_effects(effects) -> DamageModifiers:
    """`CalculateAttackerModifiersForPrediction` @181000590 — DamageModifiers depuis les effets ACTIFS de
    l'attaquant (§17.8). Agrège : damage-bonus (additif/percent, `create_effect_damage_bonus_for_attack`)
    + pénétration d'armure (`get_armor_penetration` → axe armure). Les effets doivent être déjà filtrés
    actifs (EffectsState.active_effects) ; si on passe des dicts, AUCUN filtre is_active n'est appliqué."""
    bonuses = []
    for e in _as_effects(effects):
        db = e.create_effect_damage_bonus_for_attack()
        if db is not None:
            bonuses.append(db)
        pen = e.get_armor_penetration()
        if pen is not None:
            bonuses.append(for_armor_penetration(True, pen))
    return build_attacker_modifiers(bonuses)


def build_defender_modifiers_from_effects(effects) -> DamageModifiers:
    """`CalculateDefenderModifiersForPrediction` @181002c30 — DamageModifiers depuis les effets de la CIBLE
    (réductions de dégât reçu). Agrège `create_effect_damage_malus_for_defense` (slot 0x1a). Symétrique de
    `build_attacker_modifiers_from_effects`. Effets déjà filtrés actifs (EffectsState.active_effects).
    ⚠ Couvre la famille `ADamageDefenseModifierAbilityEffect` (EffectBonus PercentDecrease ConfigVar gated) ;
    les réductions par STAT (Defense), par COUPS (Parry_ReduceHits) ou par TRIGGER (predOptimistic) sont des
    axes SÉPARÉS, non couverts ici (cf. docs/rl/runner-engine.md §1.8)."""
    maluses = []
    for e in _as_effects(effects):
        mb = e.create_effect_damage_malus_for_defense()
        if mb is not None:
            maluses.append(mb)
    return build_defender_modifiers(maluses)


def hits_bonus_from_effects(effects) -> int:
    """Σ des bonus de COUPS (`CreateEffectHitsBonusForAttack`) des effets actifs (axe hits, ex.
    PowerTrip_FullHealth). Addition = +value, Subtraction = −value."""
    total = 0
    for e in _as_effects(effects):
        hb = e.create_effect_hits_bonus_for_attack()
        if hb is None:
            continue
        if hb.kind == "Addition":
            total += hb.value
        elif hb.kind == "Subtraction":
            total -= hb.value
    return total
