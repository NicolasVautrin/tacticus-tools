"""Effets du namespace natif `IdunBattle.Entities.Effects.Loki` — 1 classe par effet (VA citée).

Chaque classe override UNIQUEMENT ce qu'elle implémente dans le natif (lu en ghidra). Les magnitudes
non encore confirmées par nom gameconfig renvoient None (pas de contribution) = on N'INVENTE PAS de
valeur non prouvée (cf. doc §17.4 « présent ≠ appliqué »). RapidAssault = seul cas magnitude validé.
"""
from __future__ import annotations

from collections.abc import Mapping

from ...services.effect_bonus import (EffectBonus, for_addition,
                                      for_percent_decrease, for_percent_increase,
                                      for_percent_subtraction_capped)
from .base import BaseEffect, SubEffectSpec, SAME_TURNS
from .magnitude import ability_var, global_value, trait_var
from ...services.damage_combat import BlockSource


class RapidAssaultExtraDamageEffect(BaseEffect):
    """`RapidAssault_ExtraDamageEffect` (effet 0x4cd=1229).
    - dégât @180f67940 : `ForPercentIncrease(ConfigConst key 0xf)` = trait var `rapidAssaultExtraDmgPct` (=25, scalaire).
    - cycle de vie : posé à l'init d'ability (`RapidAssaultAbility.CreateBehaviour` @181224950 `AddEffect(0x4cd)`),
      RETIRÉ en fin de tour si l'unité a attaqué (`RemoveExtraDamageEffectAbility.CreateTrigger` @181224af0 =
      `On(0x17) & UnitsAttackedThisTurn>0 & HasEffect(0x4cd)`).
    VALIDÉ live : +25% → u94→u84 3012-4524 EXACT."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        pct = trait_var("RapidAssault", "rapidAssaultExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None

    @property
    def removed_after_attack(self) -> bool:
        return True


class SmashaEadExtraDamageEffect(BaseEffect):
    """`SmashaEadEffect.CreateEffectDamageBonusForAttack @180f6bee0` (orksNob "Tanksmasha", ability
    SmashaEad, EffectType "SmashaEad") : `EffectBonus.ForAddition(OwnerIsCaster & IsNormalAttack,
    ConfigVar(8=extraDmg, EffectSource))` = +`extraDmg[level]` x multiplier au degat des attaques
    NORMALES du porteur — FLAT additif (PAS %, contrairement a RapidAssault).

    Placement (#69, natif LU) : `ForAddition` ecrit le champ DamageBonus (+5) de l'EffectBonus ->
    `DamageModifiers.Add @181005f10` fait `additif @+0x10 += FromInt(v)`, applique APRES percage/armure
    par `CalculateBaseDamageWithAllModifiers @18102d3f0` (meme canal `additive` que tout ForAddition).
    Il n'existe PAS de canal additif "de base" pre-percage dans le natif -> le kind "BaseAddition"
    invente a ete retire ; le `+66` observe post-percage etait confondu par l'aura #49 + BeastSlayer.

    Effet pose par `SmashaEadAbility.CreateTrigger @1811a0610` quand le porteur a traverse >=2 hexes
    ce tour (condition d'EFFECT-CREATION, deja bakee dans l'effet materialise ; le bonus s'applique
    tant que l'effet est actif -> pas de re-gate ici). `extraDmg` in variablesAffectedByRarityBonus ->
    scale par le multiplier de l'unite. i2 : "+437 Damage" (au niveau/mult affiche). ability ACTIVE ->
    indexe activeAbilityLevel. (L'effet porte AUSSI -dmgReductionPct au degat RECU via
    `CreateEffectDamageMalusForDefense @180f6c060` = cote DEFENSE, PORTE #119 ci-dessous.)"""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        # #71 : trigger natif = OwnerIsCaster & IsNormalAttack (@180f6bee0). Le noeud DSL IsNormalAttack
        # (= `IsRegularAttack(ability DECLENCHANTE)` @180f8d260/@181555b40, FALSE si pas d'ability dans le
        # contexte) evalue FALSE dans le contexte PREDICTION DISPLAY (verdict re-expert : additif absent de
        # decisionView ; off_sans ~= oracle) -> l'additif ne doit PAS entrer dans la DamageModifiers de
        # PREDICTION. En COMBAT (is_prediction=False) l'additif est applique.
        # ⚠ #68 (BUG MAGNITUDE = MULTIPLIER, RE close bit-exact) : le COMBAT live applique +300/coup exact
        # (round(extraDmg[L50]=333 x 90/100)) alors que ce port applique +599 (round(333 x 180/100)) -> SUR-
        # applique ~2x. Le niveau (50), la variable (extraDmg) et l'index (level-1) sont CORRECTS ; SEUL le
        # multiplier est faux : `self.ability_variables_multiplier=180` est le multiplier GLOBAL/primaire de
        # l'unite (UnitConfig+0x74), or la TRIGGERED SmashaEad a son PROPRE multiplier par-ability = 90
        # (`GetAbilityVariablesMultiplierPercentage(abilityId)@181696230` est PAR-ABILITY). Ce multiplier
        # par-ability des triggered n'est capte par AUCUN champ actuel -> fix FIDELE = nouveau capteur (tache
        # #75) ; presence CORRECTE. Test xfail test_getstuckin_combat_absolute_bit_exact -> xpass apres fix.
        if is_prediction:
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("SmashaEad", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        # ForAddition -> canal `additive @+0x10` applique POST-percage (DamageModifiers.Add @181005f10).
        return for_addition(True, amt) if amt is not None else None

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        """`SmashaEadEffect.CreateEffectDamageMalusForDefense @180f6c060` (cote DEFENSE, #119) :
        `EffectBonus.ForPercentDecrease(OwnerIsTarget, ConfigVar 0x46=dmgReductionPct)` — l'effet REDUIT le
        degat RECU par son porteur de `dmgReductionPct`% (i2 « takes -33% Damage » tant que l'effet actif =
        le porteur a traverse >=2 hexes ; la CONDITION est deja bakee dans la materialisation de l'effet ->
        pas de re-gate ici). Gate natif = `OwnerIsTarget` SEUL (decompile @180f6c060) -> AUCUN gate
        melee/normal : s'applique a TOUTE attaque recue. `dmgReductionPct` NON rarity-affected (BC
        `VariablesAffectedByUnitRarityMultiplier=[extraDmg]`) -> multiplier no-op (pas de bug #68 cote defense).
        #119 : reconstruit BIT-EXACT offline (Kariyan->orksNob : RapidAssault x1.25 + DEF -33% = oracle
        [1002,1745] EXACT ; sans ce malus le port sur-predisait x1.49). Meme ConfigVar 0x46 que GuardianOrganism
        (#89), mais ici un ForPercentDecrease PLAT (pas un PercentSubtractionCapped)."""
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        red = ability_var("SmashaEad", "dmgReductionPct", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner=defenseur (l'effet est sur la cible)


class RitesOfBattleExtraDmgEffect(BaseEffect):
    """`RitesOfBattleExtraDmgEffect` (Effects.Loki) — AURA stat-mod +dégât de Calgar (2 EffectTypes
    permanents sur le porteur : Basic `...ExtraDmgBasic` 1002 / Imperial `...ExtraDmgImperial` 1003).
    `RitesOfBattleAbility.CreateBehaviour @181225340` → 2 `DynamicStatModifierEffect` sur le SOURCE ;
    `CreateTargetSelector` = `AdjacentUnits(1) @180de8320` (source EXCLUE) → `Friends @180df0040` →
    `With/WithoutTrait(0x1a=26)` (26 = grande-alliance Imperial, `GrandAlliance.GetTrait @1815647a0`).
    Montant `GetDynamicStatModificationAmount` = `GetVariableForLevel(idx8→extraDmg | idx9→extraDmg_2,
    niveau SOURCE)` × multiplier SOURCE (les 2 vars dans `variablesAffectedByRarityBonus`) ; ajouté à la
    **modification** du stat **Attack**. RE-validé : `extraDmg_2[L50]×1.8 = 1298` (Imperial, u92 adjacent
    à Calgar) ; `extraDmg[L50]×1.8 = 898` (basic).

    ⚠ Modélisée UNIQUEMENT côté SOURCE via `create_aura_attack_bonus` (l'effet-entité vit sur le PORTEUR,
    pas sur le buffé → PAS de `get_stat_modification_*` target-side : le porteur ne se self-buff pas,
    AdjacentUnits l'exclut). La sélection Basic/Imperial + le montant sont ré-évalués PAR CANDIDAT."""

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> int | None:
        """AURA `RitesOfBattleAbility` @181225340 (2 effets permanents sur Calgar : Basic 1002 / Imperial
        1003) : +extraDmg/_2 au DÉGÂT DE BASE des ALLIÉS ring-1 du porteur, gate grande-alliance Imperial.
        `AdjacentUnits(1) @180de8320` (source EXCLUE) → `Friends @180df0040` (même équipe) →
        `With/WithoutTrait(0x1a=26)`. Montant = `GetVariableForLevel(var, niveau SOURCE) × multiplier SOURCE`
        (RE-validé : `extraDmg_2[L50]×1.8 = 1298`, `extraDmg[L50]×1.8 = 898`). Modélisé CÔTÉ SOURCE
        (l'effet-entité vit sur Calgar, pas sur le buffé) et ré-évalué PAR CANDIDAT (adjacence à `att_pos`)."""
        c = ctx or {}
        if c.get("owner_id") == c.get("att_id"):
            return None                                  # AdjacentUnits exclut la source (op_Subtraction self)
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                  # Friends = même équipe que le porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        if hexgeo.distance(op, ap) != 1:                 # AdjacentUnits(range 1) — pure adjacence HEX
            return None
        # Gate trait 0x1a=26 = grande-alliance Imperial (GrandAlliance.GetTrait @1815647a0 : Imperial→26).
        # ABSENT de gameconfig.traits → dérivé de GrandAllianceId. Les 2 effets sont MUTUELLEMENT EXCLUSIFS
        # ("instead") : Basic→WithoutTrait(26) (non-Imperial), Imperial→WithTrait(26).
        target_imperial = (c.get("att_grand_alliance") == "Imperial")
        effect_imperial = bool(self.name and self.name.endswith("Imperial"))
        if effect_imperial != target_imperial:
            return None
        var = "extraDmg_2" if effect_imperial else "extraDmg"
        return ability_var("RitesOfBattle", var, c.get("owner_level"),
                           multiplier_pct=c.get("owner_mult") or 100)


class PathOfCommandExtraDmgEffect(BaseEffect):
    """`PathOfCommandExtraDmgEffect` (Effects.Triggered.Loki) — AURA stat-mod +Attack de Loki
    (`PathOfCommand_ExtraDmg` 1112). `PathOfCommandAbility.CreateBehaviour @181110f10` pose 2 effets
    DynamicStatModifier sur le SOURCE (Loki) : ExtraDmg (0x458=1112) + ExtraCrit (0x453=1107).
    `CreateTargetSelector @180f4bf30` = `SurroundingFriends(owner, range=GetNumberConstant(0x16)=2)` =
    `SurroundingTiles(range) - Tiles(self)` → `Friends` → alliés (même équipe) à distance hex <=2, SOURCE
    EXCLUE (comme RitesOfBattle mais range 2 au lieu de 1).

    Montant `GetDynamicStatModificationAmount @18119c7b0` = `If(IsSameFaction(owner, target), v8+v9, v8)`
    avec `v8 = GetVariableForLevel(8=extraDmg, niveau SOURCE)`, `v9 = (9=extraDmg_2, niveau SOURCE)` (mêmes
    enum-keys 8/9 = extraDmg/extraDmg_2 que RitesOfBattle) × multiplier SOURCE (les 2 dans
    `variablesAffectedByRarityBonus`). `IsSameFaction` = **même FACTION** (FactionId, ex. Aeldari), PAS la
    grande-alliance : `IsSameFaction` s'appuie sur `UnitExtensions.HasFaction @180ed6450` (compare le champ
    FactionId string). CONFIRMÉ RE + LIVE (discriminateur : allié Aeldari adjacent = extraDmg+extraDmg_2=+699 ;
    allié Ork = Xenos MAIS pas Aeldari = extraDmg SEUL=+400). → allié même faction → extraDmg+extraDmg_2 ; autre
    faction (même Xenos) → extraDmg seul. (⚠ DIFFÉRENT de RitesOfBattle dont le gate extraDmg_2 = grande-alliance
    Imperial via trait 26.) Ajouté à la **modification** du stat **Attack**.

    ⚠ Modélisée CÔTÉ SOURCE via `create_aura_attack_bonus` (l'effet-entité vit sur Loki, pas sur le buffé) et
    ré-évaluée PAR CANDIDAT (distance <=2 à `att_pos`). PAS de `get_stat_modification_*` target-side (Loki ne
    se self-buff pas : SurroundingFriends l'exclut). L'axe CRIT (ExtraCrit 1107 = extraCritChance) = effet
    SÉPARÉ non porté ici (nécessite un canal aura-crit dédié — TODO)."""

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> int | None:
        c = ctx or {}
        if c.get("owner_id") == c.get("att_id"):
            return None                                  # SurroundingFriends exclut la source (- Tiles(self))
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                  # Friends = même équipe que le porteur (Loki)
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = ability_var("PathOfCommand", "range", is_constant=True) or 2   # GetNumberConstant(0x16)=range=2
        if hexgeo.distance(op, ap) > rng:                # SurroundingFriends(range) — portée hex du porteur
            return None
        lvl, mult = c.get("owner_level"), (c.get("owner_mult") or 100)
        base = ability_var("PathOfCommand", "extraDmg", lvl, multiplier_pct=mult) or 0
        # If(IsSameFaction(owner, target), extraDmg + extraDmg_2, extraDmg) — IsSameFaction = même FACTION
        # (FactionId, cf. HasFaction @180ed6450), PAS grande-alliance. Confirmé live (Ork Xenos = extraDmg seul).
        ofac, afac = c.get("owner_faction"), c.get("att_faction")
        if ofac is not None and ofac == afac:
            base += ability_var("PathOfCommand", "extraDmg_2", lvl, multiplier_pct=mult) or 0
        return base or None


class StandVigilExtraArmorEffect(BaseEffect):
    """`StandVigil_ExtraArmorEffect` (Effects.Loki) — buff **StatModification** +armure, **SELF-buff**
    (l'unité se buffe elle-même en « stand vigil » = sans se déplacer). `GetDynamicStatModificationAmount
    @180f6d910` = `ConfigVar(key 0x51c=1308, EffectSource, 0x1b)` = ability var
    `StandVigil.extraArmor[level]` (FLAT), ajouté à la **modification** du stat **FixedArmor** (=16) via
    `ChangeStat` (part 5/9 ; revert part 6).

    **Self-buff** ⇒ la source EST l'unité porteuse → `level` = niveau de l'ability StandVigil de l'unité
    elle-même (`self.ability_level` capté depuis unitConfig, sinon `self.level`) → magnitude EXACTE
    offline ⇒ **résidu 0 validable live** (contrairement à RitesOfBattle, buff cross-unité)."""

    def get_stat_modification_stat(self) -> int | None:
        return 16                                   # StatType.FIXED_ARMOR

    def get_stat_modification_amount(self) -> int | None:
        # StandVigil = ability ACTIVE → indexer sur activeAbilityLevel (fallback passif, puis stack level).
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        return ability_var("StandVigil", "extraArmor", lvl)


class CrushingStrikeEffect(BaseEffect):
    """`CrushingStrikeEffect` (Effects.Loki, effet 0x4a2=1186 ; ctor @180f3af20, base
    `ADamageDefenseModifierAbilityEffect`).
    - dégât `CreateDamageModifier` @180f3ad90 : `ForPercentIncrease(OwnerIsCaster & IsNormalAttack &
      IsMeleeAttack, ConfigConst key 0xf)` = trait var `crushingStrikeExtraDmgPct` (=50, constante
      plate via `AbilityConfiguration.GetNumberConstant` — cf. `ConfigAmount.Calculate @180f171c0` —
      NON rarity-scalée).
    - condition d'activité `CreateActiveCondition` @180f3ad50 : NOT HasFlag(HasMoved) (« if it has
      not moved this turn ») — en PRÉDICTION la tuile candidate fixe le flag (`has_moved`), en COMBAT
      `state.moved_this_turn` (#60).
    VALIDÉ live #98 (darkaTerminator u80→u78 seed777 roster1) : préd depuis (6,6) not-moved elev2>1
    = ×2.25 = CrushingStrike(×1.5) × ÉlévationBonus(×1.5) [composition %-list multiplicative] ;
    depuis les tuiles déplacées (elev égale) = ×1.0 EXACT (5307,7959)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        if is_ranged:                            # gated IsMeleeAttack (@180f3ad90)
            return None
        if is_normal_attack is False:            # gated IsNormalAttack (spéciale mêlée → pas de bonus)
            return None
        if has_moved:                            # ActiveCondition NOT HasFlag(HasMoved) (@180f3ad50)
            return None
        pct = trait_var("CrushingStrike", "crushingStrikeExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


class HeavyWeaponExtraDmgEffect(BaseEffect):
    """`HeavyWeapon_ExtraDmgEffect` (effet 1008 ; ctor `DamageModifierAbilityEffect(0x3e9)`).
    - dégât `CreateDamageModifier` @180f4f030 : `EffectBonus.ForPercentIncrease(cond, amount)` où
      `amount = ConditionalAmount(TriggeringAbilityIs(0x3ec) ? amount×2 : amount)`, `amount = ConfigConst
      key 0xf` = trait var `heavyWeaponExtraDmg` (=25, scalaire) ; condition = `OwnerIsCaster &
      IsRangedAttack & flags`. ⇒ **+25% de dégât sur les attaques RANGED** (le ×2 si l'ability
      déclenchante est 0x3ec = raffinement non porté ; l'attaque normale/overwatch n'est pas 0x3ec).
    Porté par le trait HeavyWeapon (qui accorde aussi l'Overwatch) → s'applique au tir d'overwatch."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        if not is_ranged:                        # gated IsRangedAttack (no-op sur mêlée / contexte inconnu)
            return None
        # Gate NO-MOVE (`!HasFlag(HasMoved=0)` @180f4f030 ; i2 : « When this unit has not moved this
        # turn »). En PRÉDICTION la tuile candidate fixe le flag : has_moved=True (candidat avec
        # déplacement) → pas de bonus (GROUND TRUTH step-23 : rangées ranged u78 SANS ×1.25 depuis les
        # tuiles déplacées ; step-11 : « ×1.25 selon tuile »). En COMBAT (#60) l'état est DÉSORMAIS tracé
        # (`state.moved_this_turn` -> `attacker_modifiers` passe un bool défini) : le bonus s'annule si
        # l'unité a bougé ce tour. None (contexte hors combat/prédiction) → bonus appliqué (fallback).
        if has_moved:
            return None
        pct = trait_var("HeavyWeapon", "heavyWeaponExtraDmg")
        return for_percent_increase(True, pct) if pct is not None else None


class RangedSpecialistEffect(BaseEffect):
    """`RangedSpecialistEffect` (trait RangedSpecialist — i2 : « If this unit did not start its turn
    adjacent to an enemy unit, it deals +33% Damage with ranged attacks »).
    - dégât @180f67520 : `EffectBonus.ForPercentIncrease((OwnerIsCaster & IsRangedAttack &
      !TriggeringAbilityIs(0x434)) | (branche 0x434 overwatch), Get(ConfigConst 0xf))` =
      **+rangedSpecialistDmgPct% sur les attaques RANGED** (toutes tuiles — la condition « pas parti
      adjacent » est l'état ACTIF de l'effet, reflété par la capture isActive, PAS un gate de tuile).
    MAGNITUDE : `traitVariables.rangedSpecialistDmgPct` = 33. GROUND TRUTH step-8 seed777 :
    u80→u94 ranged natif = moteur ×1.33 exact (per-coup 534 = round(401×1.33)), mêlée intacte."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        if not is_ranged:                        # gated IsRangedAttack (@180f67520)
            return None
        pct = trait_var("RangedSpecialist", "rangedSpecialistDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


# Traits cible gatant BeastSlayer_ExtraDmg (natif `HasTrait(target, X)`) : BigTarget=0x405=1029,
# Vehicle=0x3f9=1017. Noms gameconfig confirmes (unit_map find --trait BigTarget/Vehicle).
_BEAST_SLAYER_TARGET_TRAITS = frozenset({"BigTarget", "Vehicle"})


class BeastSlayerExtraDmgEffect(BaseEffect):
    """`BeastSlayer_ExtraDmgEffect.CreateDamageModifier @180f336c0` (trait BeastSlayer, effet
    `BeastSlayer_ExtraDmg`) : `ForPercentIncrease(ConfigConst 0xf = beastSlayerExtraDmgPct=20)` gate
    `OwnerIsCaster & IsMeleeAttack & (HasTrait(target, 0x405=BigTarget) | HasTrait(target, 0x3f9=Vehicle))`.
    => +20% de degat MELEE vs Big Targets / Vehicles (i2). Variable de TRAIT -> globale, NON scalee.
    `target_traits` = noms de traits de la CIBLE ; None (contexte sans cible : prediction generique,
    trigger, ability/splash melee) -> pas de bonus (cible inconnue -> "present != applique").
    Cf. docs/rl/case-68-orksnob-attacker-effects.md."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        if is_ranged:                                  # IsMeleeAttack -> melee uniquement
            return None
        if not target_traits or _BEAST_SLAYER_TARGET_TRAITS.isdisjoint(target_traits):
            return None                                # cible ni BigTarget ni Vehicle -> 0
        pct = trait_var("BeastSlayer", "beastSlayerExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


class BeastSlayerExtraBlockEffect(BaseEffect):
    """`BeastSlayerAbility.CreateAddBlockEffectBehaviour @180e18b70` (trait BeastSlayer, effet
    `BeastSlayer_ExtraBlock`, cote DEFENSE) : `AddExtraBlockEffectToOwner(chance, amount)` avec
    chance=`GetBlockChance @180e19120`=`GetNumberConstant(0x2d=beastSlayerBlockChance)` (=10) et
    amount=`GetBlockDamage @180e19160`=`PercentageOf(StatAmount(0x10=FixedArmor),
    GetNumberConstant(0x36=beastSlayerBlockAsMaxArmorPct))` (=100% du FixedArmor COURANT).
    => source de BLOCK SUPPLEMENTAIRE (roll separe : +10% chance de bloquer 100% de l'armure courante
    en degat), ABSENTE du scalaire GetStat(7/8) (verifie LIVE 2026-07-09 : orksNob blockChance=0). Le
    natif la tient dans `GetMultiValueStat(7)`. Variables de TRAIT -> globales, NON scalees par le mult.
    Cf. docs/rl/case-68-orksnob-attacker-effects.md (#72)."""

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0):
        chance = trait_var("BeastSlayer", "beastSlayerBlockChance")
        pct = trait_var("BeastSlayer", "beastSlayerBlockAsMaxArmorPct")
        if not chance or pct is None:
            return None
        amount = int(int(defender_fixed_armor) * int(pct) / 100)   # PercentageOf(FixedArmor, blockDmgPct)
        if amount <= 0:
            return None
        # block_id = la chance (id natif dans failedList @181002350) : une source EXCLUE apres son 1er
        # echec sur un coup (exclusion inter-coups, cf. AttackDamageOperation._run_hits #72).
        return BlockSource(chance=int(chance), amount=amount, block_id=int(chance))


class TerrifyingExtraDefenseEffect(BaseEffect):
    """`Terrifying_ExtraDefense_Effect.CreateDamageModifier` @180f47ba0 : réduit le dégât MÊLÉE reçu par
    son PORTEUR (l'effet est sur la CIBLE). Trigger natif = `OwnerIsTarget & IsMeleeAttack` (AbilityOrEffect
    0x62) ; valeur = `ConfigConst(0x28)`. La valeur n'est PAS exposée par gameconfig (trait/effet Terrifying
    = variables vides) ; magnitude **30 confirmée LIVE** (scorer ×0.70 sur eldarMauganRa, seed777 step22).
    ⇒ malus défenseur `PercentDecrease(30)` gated `IsMeleeAttack` (no-op sur attaque ranged / contexte inconnu)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if not is_melee:                         # gated IsMeleeAttack
            return None
        return for_percent_decrease(False, 30)   # owner_is_caster=False (l'effet est sur le défenseur)


class MartialKatahDmgReductionEffect(BaseEffect):
    """`MartialKatah_DmgReductionEffect.CreateDamageModifier @180f58b30` (trait MartialKatah, Custodes
    ex. custoTrajann / custoVexilusPraetor) : réduit le dégât des ATTAQUES NORMALES reçues par son PORTEUR.
    Trigger natif = `OwnerIsTarget & IsNormalAttack` (DSLFactory.get_OwnerIsTarget & IsNormalAttack, op&) ;
    valeur = `ConfigConst(0x72)` = `martialKatahDmgReductionPct` (=20) ; kind `EffectBonus.ForPercentDecrease`.
    ⇒ malus défenseur `PercentDecrease(20)` GATÉ `IsNormalAttack` (no-op sur les spéciales config-based).
    i2 : « Normal attacks against this unit deal -{dmgReductionPct}% Damage. » (le +extraDmgPct% vs Summons
    est l'effet SÉPARÉ MartialKatah_DmgBonus, canal attaquant.)

    Gate `IsNormalAttack` : lu via `attacker_ctx["is_normal_attack"]` (threadé par la PRÉDICTION —
    make_normal_attack_predictions=True, generate_multi_hit_attack_prediction=False). Absent (combat runner,
    att_ctx sans le flag) → None = INERTE (port PRÉDICTION-first, cf. GuardianOrganism #89/#91). L'effet est
    sur le DÉFENSEUR → `owner_is_caster=False`."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if not (attacker_ctx and attacker_ctx.get("is_normal_attack")):   # gated IsNormalAttack
            return None
        red = trait_var("MartialKatah", "martialKatahDmgReductionPct")     # ConfigConst 0x72 (=20)
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner=défenseur (l'effet est sur la cible)


_TERMINATOR_EXCLUDED: "frozenset[str] | None" = None


def _terminator_excluded_profiles() -> "frozenset[str]":
    """Profils de dégât PERÇANT le TerminatorArmour (`terminatorArmourExcludedDmgProfiles` du trait,
    = "Psychic,DirectDamage") → set de noms. Lu une fois en gameconfig, mis en cache."""
    global _TERMINATOR_EXCLUDED
    if _TERMINATOR_EXCLUDED is None:
        raw = ""
        try:
            import gameconfig as _GC
            raw = ((_GC.trait("TerminatorArmour") or {}).get("variables") or {}).get(
                "terminatorArmourExcludedDmgProfiles") or ""
        except Exception:
            raw = ""
        _TERMINATOR_EXCLUDED = frozenset(p.strip() for p in raw.split(",") if p.strip())
    return _TERMINATOR_EXCLUDED


class TerminatorArmourReduceDmgEffect(BaseEffect):
    """`TerminatorArmour_ReduceDmg_Effect.CreateEffectDamageMalusForDefense` @180f70f80 : réduit de
    `terminatorArmourDmgReduction`% (=-75) le dégât reçu par son PORTEUR, SAUF si le profil de dégât de
    l'attaque figure dans `terminatorArmourExcludedDmgProfiles` (=Psychic,DirectDamage). Trigger natif =
    `OwnerIsTarget & NOT DamageProfileIs(excludedArray)` (ConfigConst 0x4c=reduction, 0x52=array via
    `EffectBonus.ForPercentIncrease`) — NON gated mêlée (≠ Terrifying, s'applique mêlée ET ranged).
    Valeurs LUES en gameconfig (trait TerminatorArmour), -75% confirmé LIVE (u96 encaisse 904 vs u94 3616,
    même attaquant → ratio 0.25 = -75%)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        red = trait_var("TerminatorArmour", "terminatorArmourDmgReduction")   # -75 (magnitude 75)
        if not red:
            return None
        if damage_profile and damage_profile in _terminator_excluded_profiles():
            return None                                     # profil perçant (Psychic/DirectDamage) → pas de réduction
        return for_percent_decrease(False, abs(int(red)))   # owner=défenseur (l'effet est sur la cible)


class GuardianOrganismDamageReductionEffect(BaseEffect):
    """`GuardianOrganism_DamageReductionEffect.CreateEffectDamageMalusForDefense @180f4c630` (trait
    GuardianOrganism, tanks Tyranides ex. tyranTyrantGuard) : réduit le dégât REÇU par son porteur de
    `min(dmgReductionPct% × CurrentDamage, dmgReduction[cap] × mult)` — `EffectBonus.ForSubtraction(
    OwnerIsTarget, Min(PercentageOf(CurrentDamage, ConfigVar(0x46)), ConfigVar(0x12)))`. Réduction
    DYNAMIQUE (fraction du dégât courant) + CAPÉE absolue -> kind `PercentSubtractionCapped` (≠ un simple
    PercentDecrease : le cap plafonne le MONTANT soustrait, pas le %).
      - pct = ConfigVar(0x46) = `dmgReductionPct` [25..33 par niveau, NON rarity-scaled].
      - cap = ConfigVar(0x12) = `dmgReduction` [20..1455, rarity-scaled × mult].
    AURA (`CreateTargetSelector @180f4c890` = Self + `AdjacentFriends(range 1)`) : l'effet se MATÉRIALISE
    sur chaque bénéficiaire (self + amis ring-1) -> capté dans SA liste (source = le porteur GuardianOrganism).
    Côté port l'effet est DÉJÀ sur le défenseur (comme Terrifying/Terminator) : `self.ability_level`/
    `self.ability_variables_multiplier` = ceux du porteur = le DÉFENSEUR (EffectsState.seed les propage) ->
    niveau/mult CORRECTS sans threading. Aucun gate profil/mêlée/attaquant (OwnerIsTarget seul).
    Symptôme non-porté (probe #86a) : port sur-prédit dégât->TyrantGuard (off 3205 vs natif 2324)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        pct = ability_var("GuardianOrganism", "dmgReductionPct", lvl)   # ConfigVar 0x46 (non scalé)
        if not pct:
            return None
        cap = ability_var("GuardianOrganism", "dmgReduction", lvl,      # ConfigVar 0x12 (rarity-scalé)
                          multiplier_pct=self.ability_variables_multiplier)
        return for_percent_subtraction_capped(False, int(pct), int(cap) if cap else None)


class NeuroparasiteEffect(BaseEffect):
    """`NeuroparasiteEffect.CreateEffectDamageMalusForDefense @180f5b840` (passif du Neurothrope
    `Neuroparasite`, EffectType 0x49f=1183, base `ABondEffect` = lien cible<->Neurothrope infecteur).
    Malgré le nom « MalusForDefense », c'est un ADDITIF **POSITIF** au dégât PSYCHIQUE reçu (le porteur =
    une faiblesse infligée) :
      `EffectBonus.ForAddition(OwnerIsTarget & AreEqual(BondedEntity, damageSource) & DamageProfileIs(0xd),
                               Multiply(ConfigVar(8=extraDmg, sourceAbilityState), EffectLevel))`
    = **+extraDmg[niveauSource] × niveau_de_parasite** au dégât psychique de LE Neurothrope qui a infecté la
    cible. i2 : « Psychic Damage dealt by the Neurothrope is increased by +1237 Damage for each level of a
    Neuroparasite on the target » (`extraDmg[L65]=1237` ; max 15 niveaux via `GetMaximumLevel @180f5bdc0`).

    Gates natifs (@180f5b840) :
      - `DamageProfileIs(0xd=Psychic)` -> uniquement le dégât PSYCHIQUE (`damage_profile == "Psychic"`).
      - `AreEqual(BondedEntity, damageSource)` -> uniquement les attaques de CE Neurothrope (l'effet `source`
        = le Neurothrope infecteur). `attacker_ctx["id"]` threadé par le builder : si connu et != source ->
        pas de bonus (un AUTRE psyker n'en profite pas).
      - `EffectLevel` = niveau de STACK du parasite sur la cible (`self.level`, capté decisionView.effects[].level).

    Magnitude `ConfigVar(8=extraDmg)` = INDEXÉE par le niveau de l'ability Neuroparasite du Neurothrope SOURCE
    (`GetAbilityState(effect)`), × SON multiplier (`extraDmg` in `variablesAffectedByRarityBonus`). L'attaquant
    ÉTANT le source (gate AreEqual), le builder passe `attacker_ctx["ability_level"]/["multiplier"]` = ceux du
    Neurothrope (`scene.ablvl_by_id`/`scene.mult`). Source inconnu (`ability_level` None : chemin combat runner
    qui ne matérialise pas encore le parasite) -> pas de bonus (dégradation fidèle, PAS un extraDmg[0] mal-indexé).

    VALIDÉ LIVE (#86, Neurothrope vs orksRuntherd VANILLA, parasite lvl0->1, aiPredict oracle) :
      - L'effet est bien MATÉRIALISÉ côté cible (EffectType capté = **1218** `Neuroparasite` ; le ctor 0x49f=1183
        est l'`AbilityOrEffect`, distinct — le routage factory se fait par NOM, ok).
      - MAGNITUDE `extraDmg[50]=942 × mult(1.8) = 1696` EXACTE = per-level natif AVANT le %-list attaquant
        (confirme le MULTIPLIER = mult UNITÉ, comme PowerTrip ; lève l'incertitude #75 pour ce passif).
      - PLACEMENT = AVANT le %-list attaquant (scalé ×%-mods), TRANCHÉ par 2 SÉPARATEURS (#88, RÉSOLU) :
        RangedSpecialist ON (M=1.33) -> Δ per-level=2256 ; OFF (Neuro démarre adjacent, M=1) -> Δ=1696
        (L1'=(3302,4106) EXACT, réfute l'hypothèse "flat 2256"). `(base+1696)×M` EXACT sur les 2 régimes.
    Le placement est câblé dans `prediction.py _add_positional_and_defender_mods` : l'additif défenseur est
    PRE-SCALÉ par le produit des %-mods avant merge dans `mods.additive` (= équivalent algébrique de avant-%list,
    `(base+A)×M = base×M + A×M`, l'`apply_all_modifiers` porté appliquant l'additif après le %-list §17.7).
    Sémantique : "damage DEALT by the Neurothrope is increased" = dégât ATTAQUANT -> scalé par ses %-mults.
    VALIDÉ port==natif BIT-EXACT (L0 (2136,3205), L1 (4392,5461)). ⚠ ISOLÉ au def additive (Neuroparasite = seul
    consommateur) ; le placement de l'additif ATTAQUANT (SmashaEad) reste après-%list (#70/#75, séparateur att
    non mesuré). Combat : parasite non matérialisé par le runner -> def additive=0 -> inerte."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if (damage_profile or "") != "Psychic":       # DamageProfileIs(0xd=Psychic)
            return None
        ac = attacker_ctx or {}
        aid = ac.get("id")
        if aid is not None and self.source is not None and aid != self.source:
            return None                               # AreEqual(BondedEntity, damageSource) : autre attaquant
        lvl = int(self.level or 0)                    # EffectLevel = niveau de parasite sur la cible
        if lvl <= 0:
            return None
        src_lvl = ac.get("ability_level")             # niveau de l'ability Neuroparasite du Neurothrope SOURCE
        if src_lvl is None:
            return None                               # source non résolu -> pas d'indexation extraDmg fidèle
        per = ability_var("Neuroparasite", "extraDmg", src_lvl,
                          multiplier_pct=ac.get("multiplier") or 100)
        if not per:
            return None
        return for_addition(False, int(per) * lvl)    # owner=cible (défenseur) ; additif POSITIF au dégât reçu


class FightingRetreatDmgReductionEffect(BaseEffect):
    """`FightingRetreat_DamageReductionEffect` (effet 1157 `FightingRetreatDmgReduction`) — debuff posé
    par FightingRetreat (Darkstrider) sur les ennemis adjacents (« deal -582 Damage for one round »).
    - dégât @180f493a0 : `EffectBonus.ForAddition(OwnerIsCaster, Multiply(ConfigVar(0x12=dmgReduction),
      MinusOne))` = **-dmgReduction PLAT** sur les attaques du PORTEUR (additif, PAS un pct).
      `dmgReduction` = variable par niveau (lvl65=582), flaggée `variablesAffectedByRarityBonus`.
    ⚠ Niveau/multiplier fidèles = ceux du CASTER SOURCE (Darkstrider, abilityState de l'effet), non
      captés pour un debuff d'origine ennemie → fallback niveau/multiplier du PORTEUR (approximation
      documentée ; identique en pratique sur rosters au même palier)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var("FightingRetreat", "dmgReduction", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, -int(v)) if v else None


class FightingRetreatHitReductionEffect(BaseEffect):
    """`FightingRetreat_HitReductionEffect` (effet 1158 `FightingRetreatHitReduction`) — même debuff,
    axe COUPS (« They also have 1 fewer hits, to a minimum of one »).
    - hits @180f495d0 : `EffectBonus.ForAdditionWithMinimum(OwnerIsCaster, Multiply(MinusOne,
      ConfigConst(0x2c=hitsReduction=1)), min=Direct(1))` = **-1 coup, PLANCHER 1**. Le plancher est
      appliqué chez les consommateurs de hits (`max(1, …)`, cf. predict_validate)."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        # trigger natif = OwnerIsCaster SEUL (@180f495d0, pas de IsNormalAttack) -> TOUTES les attaques.
        n = ability_var("FightingRetreat", "hitsReduction", is_constant=True)   # ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


class LightCoverEffect(BaseEffect):
    """`LightCoverEffect` — couverture légère (effet de TUILE posé par `LightCoverAbility`
    Abilities.Tiles.Loki, `UnitsThatNeedEffect` @1811c1830 = unités SUR les tuiles de couverture).
    - hits @180f556b0 : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget(tuiles égales) &
      !IsMeleeAttack, -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-hitsReduction coups
      sur les attaques NON-mêlée reçues par le porteur, plancher 1**.
    MAGNITUDE : `globalValues.lightCoverHitReduction` = 2 (LightCoverAbility = ability de TUILE,
    absente de `units.abilities` — sa config vit dans les valeurs globales).
    GROUND TRUTH step-13 seed777 (trace AllMods, u90→u84 porteur LightCover) : ranged 4→2 coups
    partout, mêlée dist 1 → 4 coups (gate !IsMeleeAttack) — natif dMin/dMax reproduits exacts."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None) -> EffectBonus | None:
        if is_melee:                        # trigger natif = !IsMeleeAttack (@180f556b0)
            return None
        n = global_value("lightCoverHitReduction")   # miroir du ConfigConst 0x2c (=2)
        return for_addition(True, -int(n)) if n else None


class ParryEffect(BaseEffect):
    """`ParryEffect` (effet `Parry_ReduceHits`, trait Parry — i2 : « reduces incoming melee multi-hit
    attacks by 1 hit, to a minimum of 1 »).
    - hits @180f5d860 : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget & IsMeleeAttack,
      -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-1 coup MÊLÉE reçu, plancher 1**
      (jumeau mêlée de LightCover). MAGNITUDE : `traitVariables.parryHitReduction` = 1.
    GROUND TRUTH step-6 seed777 (trace AllMods, u86→u94 porteur Parry) : mêlée dist 1 = 4 coups
    vs ranged = 5 (base 3 + PowerTrip 1 + MasterAnnihilator 1) — natif reproduit exact."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None) -> EffectBonus | None:
        if not is_melee:                    # trigger natif = IsMeleeAttack (@180f5d860)
            return None
        n = trait_var("Parry", "parryHitReduction")  # miroir du ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


class MasterAnnihilatorAdditionalHitEffect(BaseEffect):
    """`MasterAnnihilator_AdditionalHitEffect` (effet `MasterAnnihilator_extraHit` — DEBUFF posé par
    Vitruvius sur SA cible d'attaque normale ; i2 : « Attacks by any friendly unit against the
    affected enemy score an additional hit, except attacks that deal Psychic Damage »).
    - hits @180f58d50 : `EffectAdditionalHits.Create(OwnerIsTarget & !AreEqual(
      CurrentAttackDamageProfile, 0xd=Psychic), count=ConfigConst(0x2f nrOfHits=1),
      dmg=FirstHitInCurrentAttackDamageRange capé ConfigVar(0xd maxDmg))` = **+1 coup reçu par le
      porteur (attaques non-Psychic)**. Les attaquants = ennemis du porteur = alliés du poseur (le
      gate « friendly unit » de l'i2 est structurel, pas dans le trigger).
    ⚠ CAP du coup bonus (dmg <= maxDmg[lvl] ex. 5456) non modélisé (per-coup observé << cap) — TODO.
    GROUND TRUTH step-6 seed777 : u86→u94 ranged = 5 coups (3 arme + 1 PowerTrip + 1 MA) vs 4 sur
    les cibles non marquées (88/96)."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None) -> EffectBonus | None:
        if damage_profile == "Psychic":     # !AreEqual(profil, 0xd=Psychic) (@180f58d50)
            return None
        n = ability_var("MasterAnnihilator", "nrOfHits", is_constant=True)   # ConfigConst 0x2f (=1)
        return for_addition(True, int(n)) if n else None


class BigTargetAdjacentEffect(BaseEffect):
    """`BigTargetAdjacentEffect` — AURA du trait BigTarget (i2 : « Adjacent friendly units receive
    -1 hit from ranged attacks, to a minimum of 1 »). L'effet est POSSÉDÉ par le porteur BigTarget
    (capté dans SA liste d'effets) ; ses bénéficiaires = les ALLIÉS ring-1 HEX désignés dynamiquement
    (TargetSelector @180f33c70, refresh @180f33ce0) — PAS le porteur lui-même (GROUND TRUTH step-13
    seed777 : u86 porteur = 4 coups pleins ; u80 allié adjacent = 3 coups).
    - hits @180f33ac0 : `ForAdditionWithMinimum(OwnerIsTarget & IsRangedAttack, Direct(-1),
      min=Direct(1))` — valeur -1 codée dans le natif (pas de config).
    Canal AURA (le porteur n'est pas la cible de l'attaque) : ctx fourni par l'agrégateur
    `aura_hits_malus_for_defense` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, is_melee}."""

    def create_aura_hits_malus_for_defense(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if c.get("is_melee") or c.get("owner_id") == c.get("tgt_id"):
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None                     # bénéficiaires = alliés du porteur uniquement
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo                       # ring-1 HEX (parité validée vs boardGraph)
        if hexgeo.distance(op, tp) != 1:
            return None
        return for_addition(True, -1)       # Direct(-1) @180f33ac0


class AstartesBannerExtraHitEffect(BaseEffect):
    """`AstartesBanner_AdditionalHitsEffect` (effet capté "AstartesBanner_ExtraHit", passif AstartesBanner
    ex. templAncient) — AURA +coups : les ALLIÉS dans le rayon 2 du porteur marquent +extraHits coups avec
    leurs attaques MÊLÉE (i2 : « Other friendly units within 2 hexes score an additional hit with their melee
    attacks. This additional hit can deal a maximum of 5456 Damage »). L'effet est POSSÉDÉ par le PORTEUR
    (capté dans SA liste d'effets, comme BigTarget) ; bénéficiaires = SurroundingFriends (exclut self).
    - hits `CreateAdditionalHits @180f323b0` : `ForAddition(OwnerIsCaster & IsMeleeAttack, ConfigVar(0xd=
      extraHits, sourceAbilityState))` + cap dégât 5456 sur le coup ajouté (FirstHitInCurrentAttackDamageRange
      + max). ⚠ CAP 5456 du coup ajouté NON porté (refine : ne mord que si dégât/coup > 5456 ; le +1 coup
      COUNT est l'effet principal, GROUND TRUTH ultraApothecary 1->2 @seed999 via AstartesBanner de templAncient).
    - cible `CreateTargetSelector @180f325f0` : `SurroundingFriends(range=ConfigConst 0x16=2, exclut self)`.
    Canal AURA côté SOURCE (`create_aura_hits_bonus_for_attack`, agrégé par `aura_hits_bonus_for_attack`),
    SYMÉTRIQUE de BigTarget (défenseur). Magnitude `extraHits` indexée sur le niveau d'ability du PORTEUR
    (`GetAbilityState` -> `self.ability_level`). Ctx aura = {owner_id/pos/team, att_id/att_pos/att_team, is_melee}."""

    def create_aura_hits_bonus_for_attack(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not c.get("is_melee"):                          # IsMeleeAttack
            return None
        if c.get("att_id") == c.get("owner_id"):           # SurroundingFriends exclut le porteur (self)
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                    # bénéficiaires = ALLIÉS du porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = ability_var("AstartesBanner", "range", is_constant=True)   # ConfigConst 0x16 (=2)
        if hexgeo.distance(op, ap) > int(rng if rng else 2):             # SurroundingFriends(range)
            return None
        n = ability_var("AstartesBanner", "extraHits", is_constant=True)  # constante extraHits (=1)
        return for_addition(True, int(n)) if n else None


class ShadowInTheWarpLessDmgEffect(BaseEffect):
    """`ShadowInTheWarp_LessDmg_Effect` (effet 1053=0x41d) — AURA de RÉDUCTION du dégât PSYCHIQUE. L'effet
    vit sur le PORTEUR (trait ShadowInTheWarp, ex. tyranSmnWarrior) et se PROJETTE sur les ENNEMIS
    environnants (psykers) : quand un tel ennemi attaque en PSYCHIQUE, son dégât est réduit.
    - dégât `CreateEffectDamageBonusForAttack` @180f6b420 : `ForPercentIncrease(OwnerIsActor &
      DamageProfileIs(0xd=Psychic), ConfigConst(0x3b))` = `shadowInTheWarpDmgModifier`% (=-25, négatif).
    - cible `CreateTargetSelector` @180f6b5f0 : `SurroundingEnemies(range=ConfigConst 0x16) &
      UnitsWithTrait(0x3ea) & UnitsNotFromFaction(0xc)`.
    MAGNITUDE + PORTÉE LUES du trait (`traitVariables.shadowInTheWarpDmgModifier=-25`, `shadowInTheWarpRange=2`).
    ⚠ Filtre `UnitsWithTrait(0x3ea)` (psyker) NON décodable offline (pas de map TRAIT) → SUR-APPROXIMÉ au
    seul gate PSYCHIQUE (tout ennemi attaquant en Psychic dans la portée subit le malus) ; raffinement quand
    le trait 0x3ea sera mappé. Canal AURA côté SOURCE (`create_aura_attack_damage_malus_for_enemy`), agrégé
    par `aura_attack_damage_malus_from_enemies` et ajouté aux modifiers de l'ATTAQUANT en prédiction."""

    def create_aura_attack_damage_malus_for_enemy(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if (c.get("damage_profile") or "") != "Psychic":    # DamageProfileIs(0xd) @180f6b420
            return None
        if c.get("owner_team") is None or c.get("owner_team") == c.get("att_team"):
            return None                                       # SurroundingEnemies : l'attaquant est ENNEMI du porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = trait_var("ShadowInTheWarp", "shadowInTheWarpRange")
        if hexgeo.distance(op, ap) > int(rng if rng else 2):  # SurroundingEnemies(range ConfigConst 0x16)
            return None
        red = trait_var("ShadowInTheWarp", "shadowInTheWarpDmgModifier")   # -25 (ConfigConst 0x3b)
        if not red:
            return None
        return for_percent_decrease(True, abs(int(red)))      # OwnerIsActor : malus sur l'attaque de l'ennemi


class PowerTripFullHealthEffect(BaseEffect):
    """`PowerTrip_FullHealthEffect` — axe COUPS (hits), actif SSI PV pleins.
    - hits @180f64cf0 : `ForAddition(ConfigConst key 0x2b)` = constante `extraHit` de l'ability PowerTrip (=1).
    - condition @180f64cb0 : `!IsDamaged` (hp == max).
    MAGNITUDE résolue : `gameconfig.ability('PowerTrip').constants['extraHit']` = 1 → +1 coup quand PV pleins."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        # trigger natif @180f64cf0 = `IsNormalAttack & OwnerIsCaster` -> ATTAQUE NORMALE SEULEMENT
        # (l'appliquer aux spéciales sur-prédisait DakkaDakkaDakka -> régression steps 6/13).
        if not is_normal_attack:
            return None
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

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # Gate ATTAQUE NORMALE (i2 : « Normal attacks ignore X Armour ») — GROUND TRUTH step-13 :
        # DakkaDakkaDakka (spéciale, même porteur u90) per-coup natif 404/728 vs 78 = armure PLEINE
        # (2208), la pénétration 499 ne s'applique qu'au normal (per-coup 416/1598).
        if not is_normal_attack:
            return None
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


class ActOfFaithBuffEffect(BaseEffect):
    """`ActOfFaithBuffEffect` (effet 0x3f9=1017, namespace `Effects.Loki`) — buff de crit empilable du
    trait ActOfFaith (Adepta Sororitas).

    C'est un effet **StatModification** (mute GetStat), PAS un modifier calc-time :
      - `ApplyModification` @180f302f0 : deux `ChangeStat` sur le porteur —
          crit-chance (`Position(9,5)`)  += `actOfFaithExtraCritChance` (=10) **FLAT** (la valeur
            observable get_CurrentValue plafonne à 100 via GetClampedValue) ;
          crit-damage (`Position(10,5)`) += `Ceiling(GetStat(10=critDmg, part=3) × actOfFaithExtraCritDmgPct%
            =25%)` où `part=3` = la stat de **BASE** (StatComponent.GetStatPart@180fa8bb0 → offset 0x48, SANS
            modifications) ⇒ boost **FLAT** sur la crit-dmg hors-ActOfFaith (PAS compound). Confirmé live :
            3 stacks base 250 → +63 plat à chaque fois (250->313->376->439).
      - `RevertInternal` @180f306e0 : annule les deux ChangeStat (delta natif stocké @+0xb8).

    Posé par `ActOfFaithAbility` (trigger mort/kill d'allié Imperial), retiré — TOUS les stacks — par
    `ActOfFaith_RemoveEffectAbility` au crit du porteur. La mutation de stat est faite par le TRIGGER
    (`operations.triggers`), PAS ici : ctx.crit_chance/crit_damage sont déjà effet-inclusifs (GetStat) →
    ne PAS contribuer aux hooks calc-time crit (sinon double-compte). Cette classe ne porte que les DELTAS
    appliqués par CE stack (`cc_delta`/`cd_delta`), pour un revert exact (l'addition compound est
    ordre-dépendante à l'aller, mais le revert = simple soustraction des deltas stockés, donc exact).

    ⚠ Un stack SEEDÉ depuis un snapshot live (déjà fondu dans ctx) ne connaît pas ses deltas (0 par
    défaut) : un reset de stacks seedés ne re-baisse pas la stat. Le chemin VALIDÉ accumule depuis 0
    (deltas exacts) ; le seeding mid-accumulation est un edge case documenté."""
    cc_delta: int = 0   # delta crit-chance OBSERVÉ par CE stack (info/report)
    cd_delta: int = 0   # delta crit-damage OBSERVÉ par CE stack (info/report)
    stat_mod_source = None   # clé de source ChangeStat (revert par-source via UnitStats.revert_stat)


class KanOpenerEffect(BaseEffect):
    """`KanOpenerEffect` (triggered) — `IgnoreArmor` @180f65100 = `ConfigVar(key 0x40)` = pénétration
    d'armure per-niveau (axe armure, contrairement à PowerTrip dont la réduction est stateful on-attack).
    ⚠ KillaKan n'a PAS KanOpener (kit = PowerTrip) ; clé 0x40 → nom var gameconfig non résolu pour les
    unités qui l'ont → pénétration None tant qu'inconnue (à mapper quand on porte une unité KanOpener)."""

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # TODO: mapper la clé 0x40 → var gameconfig (per-niveau) puis return ability_var(..., self.level).
        return None


class TauntedEffect(BaseEffect):
    """`TauntedEffect.ApplyInternal` @180f47510 (effet COMPOSITE 27 = `Taunted_OnlySpecificTargets`,
    base `ABondEffect` — lien cible↔tauntant). À l'application, spawne 3 SOUS-effets via
    `AddSubEffectWithSameTurns` (⇒ MÊME durée que le parent) :
      - 0x19=25  `Taunted_BlockMovement`        (la cible ne peut plus se déplacer)
      - 0x1a=26  `Taunted_CantUseAbility`        (la cible ne peut plus utiliser d'ability active)
      - 0x4d5=1237 `Taunted_RefreshUnitTurnFinished`
    Le natif enregistre aussi le `BondedEntityId` (la cible est forcée d'attaquer le tauntant) — c'est un
    effet de CIBLAGE IA (concern playbook, non porté ici : on matérialise l'effet + ses enfants ; le
    `source` de l'effet = le tauntant capture la direction du bond). VALIDÉ live attendu : la cible porte
    27 + 25/26/1237 (parent 1 round, enfants same-turns) après CrushingClaws."""

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            SubEffectSpec(0x19, "Taunted_BlockMovement", turns=SAME_TURNS),      # AddSubEffectWithSameTurns
            SubEffectSpec(0x1a, "Taunted_CantUseAbility", turns=SAME_TURNS),     # AddSubEffectWithSameTurns
            SubEffectSpec(0x4d5, "Taunted_RefreshUnitTurnFinished", turns=SAME_TURNS),
        ]


class PinnedEffect(BaseEffect):
    """`PinnedEffect.ApplyInternal` @180f5e6d0 (effet 1065 `Pinned` ; UI = « Suppressed »). Effet
    stat-mod SIMPLE (pas de sous-effet nommé) : un `ChangeStat(Position(1,5), statType=4 = Movement,
    valeur = Negative(EffectConfig(1)))` sur la cible ⇒ réduit le MOUVEMENT (la cible « pinned » ne peut
    pas avancer le tour suivant).

    ⚠ Contributions NON encore portées (présent ≠ appliqué, §17.4) : (1) la réduction de Movement (le
    mouvement n'est pas dans le chemin de combat/dégât porté) ; (2) `PinnedEffect.CreateEffectDamageBonusForAttack`
    @180f5e8e0 (malus de dégât quand l'unité Pinned attaque) — à RE + porter si on modélise le débuff
    offensif. Ici on MATÉRIALISE l'effet (nom 1065 sur la cible) — c'est le scope de la tranche EFFETS."""
