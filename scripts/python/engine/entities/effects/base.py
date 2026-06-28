"""`BaseEffect` — mirror de `IdunBattle.Entities.Effects.BaseEffect` + l'interface effet que les builders
de modifier/prédiction consomment (gqfc5mff6c).

Chaque effet du jeu = **UNE sous-classe** (1:1, le namespace natif = le module Python : `Loki` → loki.py).
Une sous-classe N'OVERRIDE QUE les méthodes qu'elle implémente réellement (lues dans ghidra, VA citée) ;
tout le reste = no-op par défaut (l'effet ne contribue rien / est actif tant que présent). C'est la
réplique fidèle du modèle natif « 1 classe par effet, interface uniforme » (doc §17.3/§17.13).

Méthodes d'interface (chacune = sa jumelle native) :
  • create_effect_damage_bonus_for_attack → `EffectBonus | None`  (CreateEffectDamageBonusForAttack)
  • create_effect_hits_bonus_for_attack   → `EffectBonus | None`  (CreateEffectHitsBonusForAttack)
  • get_armor_penetration                 → `int | None`          (IgnoreArmor, ex. KanOpener ConfigVar 0x40)
  • is_active(unit_state)                  → bool                  (CreateActiveCondition)
Cycle de vie (porté depuis les `*Ability.CreateTrigger` de pose/retrait) : `removed_after_attack`,
`one_shot`, `expired`.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ...services.effect_bonus import EffectBonus


@dataclass
class BaseEffect:
    """Effet matérialisé : identité (seedée depuis la capture one-shot) + état de cycle de vie mutable."""
    name: str
    effect_type: int | None = None
    level: int | None = None                 # niveau de STACK capté (decisionView.effects[].level) — pour
                                             # les effets à empilement (ex. Contagions) ; ≠ niveau d'ability
    # Niveau de l'ABILITY source sur l'unité (active/passive/tertiary), qui indexe les `variables[level]`
    # d'ability (≠ stack `level`). Ex. PowerTrip.armorIgnored indexé par PassiveAbilityLevel (=50), PAS
    # par le stack level (=1). Seedé depuis l'unité ; None → fallback sur `level`. §17.21.
    ability_level: int | None = None
    remaining_turns: int | None = None      # None = permanent/aura ; sinon décrémenté en fin de tour
    source: int | None = None
    consumed: bool = False                   # retiré par le cycle de vie (one-shot / fin-de-tour)
    # `AbilityVariablesMultiplierPercentage` de l'unité porteuse (BC, défaut 100). Le natif bake le
    # scaling dans la config par-unité ; ici l'effet le porte pour scaler ses variables d'ability
    # affectées (`variablesAffectedByRarityBonus`) via `magnitude.ability_var(multiplier_pct=…)`. §17.21.
    ability_variables_multiplier: int = 100

    # ── contributions aux modifiers (None = pas de contribution) ────────────────────────────────────
    def create_effect_damage_bonus_for_attack(self) -> EffectBonus | None:
        """`<Effect>.CreateEffectDamageBonusForAttack` — contribution au scalaire dégât (additif/percent)."""
        return None

    def create_effect_hits_bonus_for_attack(self) -> EffectBonus | None:
        """`<Effect>.CreateEffectHitsBonusForAttack` — contribution à l'axe COUPS (Addition/Subtraction)."""
        return None

    def create_effect_damage_malus_for_defense(self) -> EffectBonus | None:
        """`<Effect>.CreateEffectDamageMalusForDefense` — contribution DÉFENSEUR (l'effet est sur la CIBLE,
        réduit le dégât reçu). Symétrique de `create_effect_damage_bonus_for_attack`. Renvoie un `EffectBonus`
        (typiquement `PercentDecrease` de valeur `ConfigVar(key)`, gated par une condition d'effet) ou None.

        RE : `CalculateDefenderModifiersForPrediction` @181002c30 itère les effets de la cible et appelle
        cette méthode (interface effet, slot 0x1a) sur chacun → accumule un `DamageModifiers` (%-list).
        La famille `ADamageDefenseModifierAbilityEffect` (CloudOfFlies/ContemptuousDisregard/ForwardObservers/
        HuntersInstincts/… @180f08e60→BaseEffect.DamageMalusForDefense @180f10120) = `EffectBonus(PercentDecrease,
        ConfigVar(key))` gated (ex. ContemptuousDisregard @180f3a5b0 : OwnerIsTarget & HasUsedActiveAbilityThisTurn
        → ConfigVar 0x46). Défaut None = effet sans réduction défensive (dégradation fidèle)."""
        return None

    def get_armor_penetration(self) -> int | None:
        """`<Effect>.IgnoreArmor` — pénétration d'armure (axe armure : armor_eff = max(armure − pén, 0))."""
        return None

    # ── cycle de vie ────────────────────────────────────────────────────────────────────────────────
    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """`<Effect>.CreateActiveCondition` — l'effet contribue-t-il dans l'état courant ? (défaut : oui)."""
        return True

    @property
    def removed_after_attack(self) -> bool:
        """Retiré en fin de tour si l'unité a attaqué ce tour (cas RapidAssault)."""
        return False

    @property
    def one_shot(self) -> bool:
        """Consommé dès la 1re attaque de l'unité (effets « 1re attaque » stricts)."""
        return False

    @property
    def expired(self) -> bool:
        return self.remaining_turns is not None and self.remaining_turns <= 0
