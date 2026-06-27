"""Port FIDÈLE de `IdunBattle.Entities.Abilities.AActiveAbility` (+ NormalAttackAbility).

Mirror live : l'ability expose `GetDamage / GetHits / GetDamageProfile` que le scorer
(`Playbook.MakeDamagePredictions`) consomme avant d'appeler la prédiction. Les valeurs viennent
de la config (gameconfig = registre `BattleQuery@0x48`, RE @18105a530) au niveau de l'unité,
SAUF l'attaque normale dont le dégât d'arme n'est PAS dans gameconfig (id générique 69) → fourni
par la capture `combatSnapshot.normalAttack` (= dégât de base d'arme résolu).

⚠ Modèle de dégât (mesuré) :
  • attaque NORMALE : `GetDamage` rend UNE base (pré-spread) ; le spread ±20% est appliqué par la
    prédiction (`CalculateDamageSpread`). base = avg(min,max) capté.
  • ability SPÉCIALE : gameconfig fournit `minDmg/maxDmg` par niveau EXPLICITES (pas de spread
    symétrique). Le `GetDamage` par-ability exact se porte incrémentalement ; défaut = min/max config.
"""
from __future__ import annotations

from ..unit_context import UnitContext
from .ability_configuration import AbilityConfiguration
from ...services.damage_prediction import get_default_attack_hits
from ...services.min_max_damage import MinMaxDamage

# DamageProfileType index → nom (dump.cs @863303)
_PROFILE_BY_INDEX = {
    -1: "None", 0: "Physical", 1: "Projectile", 3: "Flame", 4: "Bolter", 5: "Particle",
    6: "Acid", 7: "Plasma", 8: "Melta", 10: "Gauss", 11: "Enmitic", 13: "Psychic",
    14: "Power", 15: "DirectDamage", 16: "Energy", 17: "Chain", 18: "Blast", 19: "HeavyRound",
    20: "Piercing", 21: "Las", 22: "Bio", 23: "Pulse", 24: "Toxic", 25: "Eviscerate",
}


class AActiveAbility:
    """Base ability active. `ability_type` = ActiveAbilityType ; `config` = AbilityConfiguration
    (None pour l'attaque normale générique) ; `caster` = UnitContext de l'attaquant."""

    def __init__(self, ability_type: int, caster: UnitContext,
                 config: AbilityConfiguration | None = None):
        self.ability_type = ability_type
        self.caster = caster
        self.config = config

    # AActiveAbility.GetDamageProfile (@180fb11e0) : profil de dégât de l'ability.
    def get_damage_profile(self) -> str:
        if self.config is not None:
            prof = (self.config.constants or {}).get("damageProfile")
            if prof:
                return prof
        return _PROFILE_BY_INDEX.get(self.caster.damage_type, "Physical")

    # GetHits : nombre de coups (base config + ExtraHits / ExtraHitsMelee).
    def get_hits(self) -> int:
        base = self.config.get_variable_for_level(
            "nrOfHits", self.caster.active_ability_level, 1) if self.config else 1
        return get_default_attack_hits(base, self.caster.extra_hits,
                                       self.caster.extra_hits_melee, self.caster.is_melee)

    # GetDamage : base de dégât (single, pré-spread) — défaut générique (special : min/max config).
    def get_damage(self) -> int:
        if self.config is not None:
            lvl = self.caster.active_ability_level
            mn = self.config.get_variable_for_level("minDmg", lvl, 0)
            mx = self.config.get_variable_for_level("maxDmg", lvl, 0)
            if mn or mx:
                return (mn + mx) // 2
            return self.config.get_variable_for_level("dmg", lvl, 0) \
                or self.config.get_variable_for_level("baseDmg", lvl, 0)
        return 0

    def get_pierce(self) -> int:
        """pierceRatio (0..100). Défaut 100 = perçage neutre (pas de réduction armure) ; l'attaque
        normale surcharge avec le profil d'arme. (Abilities spéciales : profil config = TODO.)"""
        return 100

    def get_damage_min_max_raw(self) -> MinMaxDamage:
        """min/max EXPLICITES de la config (special) — avant scenario. Pour les abilities dont
        gameconfig donne directement min/max (pas de spread symétrique)."""
        lvl = self.caster.active_ability_level
        if self.config is not None:
            return MinMaxDamage(min=self.config.get_variable_for_level("minDmg", lvl, 0),
                                max=self.config.get_variable_for_level("maxDmg", lvl, 0))
        return MinMaxDamage()


class NormalAttackAbility(AActiveAbility):
    """Attaque normale (id concret, ex. 69). Dégât d'arme NON dans gameconfig → capté
    (`UnitContext.normal_*`). `GetDamage` rend la base (avg) ; `GetHits` = hits captés ;
    profil = `unit.damageType`."""

    def get_damage(self) -> int:
        """Base PAR COUP = stat Attack (RE : `DSLFactory.NormalAttackDamage`=`StatAmountFormula(Attack)`).
        VALIDÉ live (8/11 exact) : la chaîne `base par-coup × hits-arme + pierce + armure` reproduit
        l'oracle pour les unités sans buff dégât (u88/u92/u96). `get_attack_prediction` applique le ×hits
        (la boucle proba somme un event par coup ; crit=0 → Σ = hits × per-coup)."""
        return self.caster.attack

    def get_hits(self) -> int:
        """hits de l'ARME (gameconfig) + ExtraHits — GetDefaultAttackHits. (≠ `normal_hits` capté
        parfois : u96 capté=2 mais arme Power=3.)"""
        return get_default_attack_hits(self.caster.normal_weapon_hits, self.caster.extra_hits,
                                       self.caster.extra_hits_melee, not self.caster.normal_ranged)

    def get_pierce(self) -> int:
        """pierceRatio de l'attaque normale — GetAttackPiercingDamageRatio (@181030a20) : profil
        d'arme `PiercingRatio` (gameconfig) + ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}, clamp 0..100."""
        from ...services.damage_prediction import get_attack_piercing_damage_ratio
        dir_pierce = (self.caster.extra_pierce_ranged if self.caster.normal_ranged
                      else self.caster.extra_pierce_melee)
        return get_attack_piercing_damage_ratio(
            self.caster.normal_profile_pierce, profile_has_trait3=False,
            attacker_extra_pierce=self.caster.extra_pierce, attacker_extra_pierce_dir=dir_pierce,
            attacker_has_trait_1001_or_1016=False)

    def get_damage_min_max_raw(self) -> MinMaxDamage:
        """min/max captés directement (prédiction native vs allié-déploiement — référence de capture)."""
        return MinMaxDamage(min=self.caster.normal_min, max=self.caster.normal_max)
