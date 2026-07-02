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

# Sentinelle de durée d'un sous-effet : MÊME nombre de tours que le parent (mirror natif
# `AddSubEffectWithSameTurns`). Distinct de None (= permanent, lié au cycle de vie du parent).
SAME_TURNS = "same"


@dataclass
class SubEffectSpec:
    """Sous-effet (enfant) qu'un effet COMPOSITE spawne quand il est appliqué (mirror des
    `Add*SubEffect`/`AddEffect` de `<Effect>.ApplyInternal`). `turns` :
      • `SAME_TURNS` → même durée que le parent (`AddSubEffectWithSameTurns`)
      • `0` ou None  → permanent, lié au parent (rem=0 natif ; reverté à l'expiration du parent)
      • `N>0`        → N tours."""
    effect_type: int
    name: str
    turns: "int | str | None" = None


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
    source: int | None = None                # `EffectComponent` SourceUnit @+0x10 (qui a posé l'effet)
    # `EffectComponent` Target @+0x14 — l'unité QUI PORTE l'effet (peuplé à la MATÉRIALISATION,
    # AddEffectOperation/AddNewEffect ; les effets seedés one-shot le laissent None, l'unité porteuse
    # = la clé `EffectsState.by_unit`). Distinct de `source` (qui l'a posé).
    target: int | None = None
    # `EffectComponent` Value @+0x60/+0x64 (flag @+0x5d) — magnitude matérialisée (Nullable<int> natif :
    # None = effet sans valeur portée, la magnitude vient alors de la config d'ability). Peuplé par
    # AddEffectOperation depuis le builder (param_6) quand l'ability source porte une valeur explicite.
    value: int | None = None
    # `EffectComponent` ParentEffect @+0x70 — pour un SOUS-effet (enfant d'un effet composite), le type
    # de l'effet parent qui l'a spawné (ex. Stunned 1162 parent de 1165/1166/1167). None = effet racine.
    # Sert au cycle de vie (les enfants sont reverté quand le parent expire). §matérialisation composite.
    parent_type: int | None = None
    consumed: bool = False                   # retiré par le cycle de vie (one-shot / fin-de-tour)
    # `AbilityVariablesMultiplierPercentage` de l'unité porteuse (BC, défaut 100). Le natif bake le
    # scaling dans la config par-unité ; ici l'effet le porte pour scaler ses variables d'ability
    # affectées (`variablesAffectedByRarityBonus`) via `magnitude.ability_var(multiplier_pct=…)`. §17.21.
    ability_variables_multiplier: int = 100

    # ── contributions aux modifiers (None = pas de contribution) ────────────────────────────────────
    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None) -> EffectBonus | None:
        """`<Effect>.CreateEffectDamageBonusForAttack` — contribution au scalaire dégât (additif/percent).
        `is_ranged` = nature du coup courant (passée par le combat) : permet aux effets gated `IsRangedAttack`
        (ex. HeavyWeapon_ExtraDmg) de ne contribuer qu'aux tirs. None = contexte inconnu (prédiction)."""
        return None

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        """`<Effect>.CreateEffectHitsBonusForAttack` — contribution à l'axe COUPS (Addition/Subtraction)."""
        return None

    def create_effect_crit_chance_bonus_for_attack(self) -> int | None:
        """Bonus de CHANCE de crit (%) — couche calc-time SÉPARÉE de `GetStat(9)`, sommée dans
        `DamagePrediction.GetCritChanceBonusFromEffects`@181031180 puis ajoutée à GetStat(9) dans
        `RollCritical` (cc = clamp(GetStat(9)+Σbonus, 0, 100)). Distinct des effets StatModification
        sur la crit-chance (eux DANS GetStat) → pas de double-compte. Défaut None = pas de bonus."""
        return None

    def create_effect_crit_damage_bonus_for_attack(self) -> int | None:
        """Bonus de DÉGÂT de crit — couche calc-time SÉPARÉE de `GetStat(10)`, sommée dans
        `DamagePrediction.GetCritDamageBonusFromEffects`@181031bb0 puis ajoutée à GetStat(10) dans
        `CalculateCriticalDamage` (critDmgPct = max(0, GetStat(10)+Σbonus)). Défaut None = pas de bonus."""
        return None

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None) -> EffectBonus | None:
        """`<Effect>.CreateEffectDamageMalusForDefense` — contribution DÉFENSEUR (l'effet est sur la CIBLE,
        réduit le dégât reçu). Symétrique de `create_effect_damage_bonus_for_attack`. `is_melee` = nature
        du coup (certains malus sont gated `IsMeleeAttack`, ex. Terrifying_ExtraDefense) ; `damage_profile`
        = NOM du profil de dégât de l'attaque (certains malus sont gated `DamageProfileIs`, ex.
        TerminatorArmour réduit SAUF Psychic/DirectDamage). Renvoie un `EffectBonus`
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

    # ── matérialisation composite ─────────────────────────────────────────────────────────────────
    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        """`<Effect>.ApplyInternal` — sous-effets (enfants) spawnés quand CET effet est appliqué.
        Défaut : aucun (effet simple). Un effet COMPOSITE (ex. Stunned) override pour déclarer ses
        enfants ; `AddEffectOperation` les matérialise après le parent (en propageant le lien parent)."""
        return []

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
