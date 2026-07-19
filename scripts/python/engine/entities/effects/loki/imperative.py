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
from ....services.effect_bonus import EffectBonus, for_addition

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
    DEUX faces du meme stat-mod natif (le DynamicStatModifierEffect ecrit la ValueModification a TOUTES ses
    cibles-selecteur = self + amis Mechanical adjacents) :
      - SELF : `applied_stat_mods` (eager ChangeStat cuit dans GetStat, mirror StandVigil/ActOfFaith) = incr. A.
      - ALLIES Mechanical ADJACENTS : `create_aura_fixed_armor_bonus_for_defense` (canal aura +FixedArmor neuf,
        re-evalue par adjacence au site de resolution armure defenseur, self auto-exclu) = incr. B (ci-dessous).
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

    def create_aura_fixed_armor_bonus_for_defense(self, ctx=None) -> "int | None":
        """AURA (increment B) — `ProtectorImperative` @180f39890 : +extraArmor à `GetStat(FixedArmor)` des amis
        **Mechanical(5) ADJACENTS** (ring-1) du porteur. `CreateTargetSelector` = self + `AdjacentFriends(1)` ∩
        `UnitsWithTrait(5)`. Le SELF (porteur) est déjà buffé par `applied_stat_mods` (stat-mod EAGER cuit dans
        `GetStat`) → on s'AUTO-EXCLUT quand def==owner (pas de double-compte : l'aura n'ajoute QUE pour un allié
        distinct). Magnitude = `extraArmor[niveau SOURCE] × mult SOURCE` (identique au self), lue du porteur
        (owner_level/owner_mult). Ré-évaluée PAR ADJACENCE au site de résolution armure (mirror natif : la
        ValueModification du DynamicStatModifierEffect atteint l'allié à portée). GROUND-TRUTH live
        (test_doctrina_protector_aura_live) : allié Mechanical adjacent = +886 FixedArmor, même source-effet."""
        c = ctx or {}
        if c.get("owner_id") == c.get("def_id"):
            return None                                   # self = stat-mod EAGER (increment A) -> pas ici
        ot = c.get("owner_team")
        if ot is None or ot != c.get("def_team"):
            return None                                   # AdjacentFriends = même équipe que le porteur
        if "Mechanical" not in (c.get("def_traits") or ()):
            return None                                   # UnitsWithTrait(5=Mechanical) sur le bénéficiaire
        op, dp = c.get("owner_pos"), c.get("def_pos")
        if not op or not dp:
            return None
        import hexgeo
        if hexgeo.distance(op, dp) != 1:                  # AdjacentFriends(range 1) — adjacence hex ring-1
            return None
        lvl = int(c.get("owner_level") or 0)
        mult = int(c.get("owner_mult") or 100)
        amt = ability_var(_ABILITY, "extraArmor", lvl, multiplier_pct=mult)
        return int(amt) or None


class ConquerorImperativeEffect(BaseEffect):
    """`ConquerorImperativeEffect` (0x4e0=1248, ctor @180f39910 = `DamageModifierAbilityEffect(0x45e=1118)`) —
    +extraDmg FLAT au degat du porteur contre une cible a ARMURE REDUITE.

    DEUX faces du meme DamageModifierAbilityEffect natif (le selecteur @180f39890 = self + amis Mechanical
    adjacents, IDENTIQUE a Protector) :
      - SELF (increment C, `create_effect_damage_bonus_for_attack` ci-dessous) : quand le PORTEUR attaque.
      - ALLIES Mechanical ADJACENTS (increment C2, `create_aura_attack_damage_bonus_for_ally` ci-dessous) :
        canal aura-attaque-degat cote SOURCE, quand un ami Mechanical ring-1 attaque une cible a armure reduite.
        Cable en COMBAT (`damage_model.attacker_modifiers`) ET en PREDICTION (normale + speciale).

    `CreateDamageModifier @180f39650` : `EffectBonus.ForAddition(get_OwnerIsCaster & HasNegativeModifier(
    cible, {ARMOR=4, FIXED_ARMOR=16}), ConfigVar(8=extraDmg, GetAbilityState(effet)))`. Increment A avait
    l'effet PRESENT-INERTE (BaseEffect = None) ; increment C materialise la contribution SELF (le toggle
    Protector<->Conqueror etait deja fonctionnel des A)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> "EffectBonus | None":
        """SELF face (increment C) — `ConquerorImperative.CreateDamageModifier @180f39650` :
        `ForAddition(OwnerIsCaster & HasNegativeModifier(cible, {ARMOR=4, FIXED_ARMOR=16}), ConfigVar(8=
        extraDmg))` = +`extraDmg[niveau actif] x mult` FLAT au degat de TOUTES les attaques du porteur
        (normale ET speciale : AUCUN noeud IsNormalAttack dans le trigger), UNIQUEMENT contre une cible a
        ARMURE REDUITE (>=1 modification per-source <0 sur ARMOR/FIXED_ARMOR). Meme canal additif que
        SmashaEad (`DamageModifiers.Add @181005f10`, applique POST-percage).

        `target_armor_reduced` = evaluation du gate `HasNegativeModifier @180f9db90` faite au SITE de
        resolution (`damage_model.defender_armor_reduced` en combat, `UnitStats.has_negative_modifier` en
        prediction) et threadee dans le canal ; None/False -> cible saine -> pas de bonus (degradation fidele
        "present != applique" hors condition). `OwnerIsCaster` est TRUE quand le porteur attaque (ce chemin)
        et en PREDICTION (cf. DecoysAndMisdirection #71 : OwnerIsCaster-seul applique en display, contrairement
        a SmashaEad dont IsNormalAttack evalue FALSE) -> contribue aux DEUX faces (pas de `if is_prediction`).

        Magnitude = `ability_var("DoctrinaImperatives", "extraDmg", niveau ACTIF, mult)` (ConfigVar var 8,
        in variablesAffectedByRarityBonus -> x multiplier). Niveau/mult seedes sur l'effet a la pose par la
        feuille de toggle (`runner/abilities/loki/imperative.py`) depuis le ctx du caster (AddEffectOperation
        ne les propage pas) ; niveau inconnu -> inerte (comme BeaconOfRage sans ability_level)."""
        if not target_armor_reduced:
            return None                                   # HasNegativeModifier(cible armure) FALSE -> pas de bonus
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var(_ABILITY, "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        # ForAddition -> canal `additive @+0x10` applique POST-percage (DamageModifiers.Add @181005f10).
        return for_addition(True, amt) if amt else None

    def create_aura_attack_damage_bonus_for_ally(self, ctx=None) -> "EffectBonus | None":
        """AURA face (increment C2) — le MEME `CreateDamageModifier @180f39650` projete sur un ALLIE
        **Mechanical(5) ADJACENT** (ring-1) du porteur quand C'EST LUI qui attaque une cible a ARMURE REDUITE.
        `CreateTargetSelector @180f39890` = self + `AdjacentFriends(1)` ∩ `UnitsWithTrait(5=Mechanical)`
        (IDENTIQUE a Protector). Le SELF (porteur) est deja couvert par la self-face
        (`create_effect_damage_bonus_for_attack`) -> AUTO-EXCLUSION att==owner (pas de double-compte ;
        `AdjacentFriends` exclut le porteur). Le gate `HasNegativeModifier(cible armure)` est le MEME que la
        self-face (trigger UNIQUE `OwnerIsCaster & HasNegativeModifier` : `OwnerIsCaster` = l'ami projete est le
        caster-attaquant du coup) -> threade via `target_armor_reduced` dans le ctx aura. Magnitude = `extraDmg
        [niveau actif] x mult` lue du MEME effet-entite (niveau seede a la pose par la feuille de toggle, cf.
        self-face) -- pas de owner_level en ctx. `ctx` = {owner_id/pos/team, att_id/att_pos/att_team, att_traits,
        target_armor_reduced} fourni par l'agregateur `aura_attack_damage_bonus_from_allies` (COMBAT
        `damage_model.attacker_modifiers` / PREDICTION normale+speciale). SYMETRIQUE ALLIE de la self-face, meme
        canal additif que SmashaEad/BeaconOfRage (`DamageModifiers.Add`, POST-percage)."""
        c = ctx or {}
        if not c.get("target_armor_reduced"):
            return None                                   # HasNegativeModifier(cible armure) FALSE -> pas de bonus
        if c.get("att_id") == c.get("owner_id"):
            return None                                   # self = self-face (incr. C) -> AdjacentFriends exclut le porteur
        ot = c.get("owner_team")
        if ot is None or ot != c.get("att_team"):
            return None                                   # AdjacentFriends = meme equipe que le porteur
        if "Mechanical" not in (c.get("att_traits") or ()):
            return None                                   # UnitsWithTrait(5=Mechanical) sur le beneficiaire (l'attaquant)
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        if hexgeo.distance(op, ap) != 1:                  # AdjacentFriends(range 1) = hex-adjacent ring-1
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var(_ABILITY, "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None
