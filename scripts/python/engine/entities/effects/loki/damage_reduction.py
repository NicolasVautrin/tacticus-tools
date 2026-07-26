"""Effets `Effects.Loki` — famille MALUS DE DÉGÂT DÉFENSEUR (`create_effect_damage_malus_for_defense` +
auras de réduction). Réduit le dégât REÇU par le porteur (ou par ses alliés / l'ennemi via aura).
1 classe par effet natif (VA citée). Cf. `loki/__init__.py`."""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import (EffectBonus, for_addition, for_piercing, for_subtraction,
                                       for_percent_decrease, for_percent_increase,
                                       for_percent_subtraction_capped)
from ..base import BaseEffect
from ..magnitude import ability_var, bc_effect_config, global_value, trait_var


class MarkerlightEffect(BaseEffect):
    """`MarkerlightEffect` (effet **1122=0x462**, `Entities.Effects.Loki`) — la cible est « marquée ».
    `.IdunBattle.Entities.Effects.Loki.MarkerlightEffect$$.ctor` = `DamageModifierAbilityEffect..ctor(this, 0x462, Nullable(1))`.
    `IdunBattle.Entities.Effects.Loki.MarkerlightEffect$$CreateDamageModifier` : trigger = `OwnerIsTarget & HasFaction(actor@0x158, 9=T'au, 3)
    & IsRangedAttack` ; bonus = `EffectBonus.ForPercentIncrease(Direct(GetEffectConfig(4)))` —
    slot service 0xbe(4) = la règle GLOBALE `MarkerlightDmgBonusPct` de la section BC `Effect`
    (`unitEffectVariables.markerlightDmgBonusPct` = **15** ; même mécanisme `IdunBattle.Core.Services.BattleQuery$$InitEffectConfig` que Pinned EffectConfig(0/1)).

    ⇒ malus DÉFENSEUR : les attaques **RANGED** d'un attaquant **T'au** contre le porteur font
    **+15 %**. Gates lus du contexte : `is_melee is False` (RANGED prouvé ; None = nature inconnue →
    None, présent ≠ appliqué) + `attacker_ctx["faction"] == "Tau"` (threadé par
    `damage_model.defender_modifiers` ; absent → None).

    Pose (MV71SniperDroneSquadAttack IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour étape (e)) : sur la CIBLE, durée
    `Sum(TurnsFromRounds(1), Direct(1))` = fin du prochain tour du caster — identique à
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddMarkerlightAbility$$CreateBehaviour`.
    ⚠ NON porté (flaggé) : le retrait au HEAL/REPAIR de la cible (i2 « Healing or repairing removes
    the effect ») — cycle de vie durée-seule offline."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if is_melee is not False:                              # gated IsRangedAttack (None = inconnu)
            return None
        if not (attacker_ctx and attacker_ctx.get("faction") == "Tau"):   # HasFaction(actor, 9=T'au)
            return None
        pct = bc_effect_config("MarkerlightDmgBonusPct", 15)   # règle globale (unitEffectVariables)
        if not pct:
            return None
        return for_percent_increase(False, int(pct))           # owner=défenseur (dégât REÇU +15 %)


class ExemplarOfHateTargetEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ExemplarOfHate_TargetEffect` (effet **1293=0x50d**) — pose sur la
    CIBLE par `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfHateAbility$$ExecuteBehaviour`
    (`AddEffect(0x50d, stateRef, source=caster@0x160, target@0x178, TurnsFromRounds(2))`, #112).

    `IdunBattle.Entities.Effects.Loki.ExemplarOfHate_TargetEffect$$CreateEffectDamageBonusForAttack`
    (MIRROR du DECOMPILE) :
        trigger = get_OwnerIsTarget & ( IsMeleeAttack | IsOverwatchAttack )
        montant = ConfigVar(8 = extraDmg, GetAbilityState(effect), config@+0x60)
        -> EffectBonus ADDITIF (le corps est INLINE : la struct construite pose le montant au champ
           +0x10, EXACTEMENT le slot ecrit par `IdunBattle.Entities.Effects.EffectBonus$$ForAddition`
           (`param_1[2] = amount`) et distinct de ForPercentIncrease (+0x08) / ForSubtraction (+0x18) /
           ForOverride (+0x28)).
    i2 : « For this round and the next, all friendly units deal +<extraDmg> Damage against that enemy
    with melee or Overwatch attacks. »

    Malgre le nom natif « ...ForAttack », le trigger est `OwnerIsTarget` : l'effet vit sur la VICTIME et
    MAJORE le degat qu'elle RECOIT -> canal PORT `create_effect_damage_malus_for_defense` (le meme mold
    que `NeuroparasiteEffect`, dont la docstring documente l'additif POSITIF cote defenseur).

    MAGNITUDE : `ConfigVar` resolu contre l'`AbilityState` de la SOURCE (Asmodai) -> l'`AddEffect` du port
    passe `scale_from_source=True` (niveau d'ability + multiplier de rarete du poseur seedes sur
    l'instance). `extraDmg` EST dans `variablesAffectedByRarityBonus` (554 @mult100 -> 997 @mult180).

    RESIDU FLAGGE : la branche `IsOverwatchAttack` du `op_BitwiseOr` n'est PAS threadee (le port ne
    distingue pas un coup d'overwatch d'un coup ranged ordinaire au site de resolution defenseur) ->
    seule la moitie MELEE contribue. Un tir d'overwatch ne recoit donc pas le +extraDmg : c'est un
    MANQUE, jamais un sur-compte."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if is_melee is not True:              # IsMeleeAttack (prouve melee) ; IsOverwatchAttack = residu
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)       # ExemplarOfHate = ability ACTIVE du poseur
        v = ability_var("ExemplarOfHate", "extraDmg", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(False, int(v)) if v else None      # owner=cible -> additif au degat RECU


class SuperchargeExtraPiercingEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.Supercharge_ExtraPiercingEffect` (effet **1208=0x4b8**) — pose sur
    la cible ET les <=2 unites derriere elle par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SuperchargeAbility$$ExecuteBehaviour`
    (`AddEffect(0x4b8, stateRef, caster@0x160, op_Addition(target@0x178, behind), TurnsFromRounds(1))`).

    `IdunBattle.Entities.Effects.Loki.Supercharge_ExtraPiercingEffect$$CreatePiercingBonusForAttack`
    (MIRROR du DECOMPILE) :
        profile = AbilityConfiguration.GetDamageProfile(config@+0x60)          # Plasma
        trigger = DamageProfileIs(profile) & get_OwnerIsTarget
        montant = ConfigVar(0x3f = extraPierceRatio, GetAbilityState(effect), config@+0x60)
        -> EffectBonus.ForPiercing(trigger, montant)      # axe PERCAGE @+0x20, PAS le scalaire degat
    i2 : « ... all with +<extraPierceRatio>% pierce ratio. Until the beginning of Sarquael's next turn,
    any further hits that deal Plasma Damage against these units also have +<extraPierceRatio>% pierce
    ratio. »

    Canal PORT = `create_piercing_bonus_for_attack` (slot d'interface DEDIE, agrege par
    `build_defender_modifiers_from_effects` puis fusionne dans le percage effectif par
    `AttackDamageOperation._apply_defender_flat_reductions` : `pierce_eff = clamp(pierce + extra, 0,100)`).
    Le profil vient de la CONFIG de l'ability source (`Supercharge.constants.damageProfile` = Plasma), pas
    d'un litteral. Magnitude indexee par l'`AbilityState` du poseur -> `scale_from_source=True` a la pose
    (`extraPierceRatio` n'est PAS dans `variablesAffectedByRarityBonus` -> multiplier inerte)."""

    def create_piercing_bonus_for_attack(self, damage_profile: str | None = None,
                                         is_melee: bool | None = None) -> EffectBonus | None:
        import gameconfig as _GC
        prof = ((_GC.ability("Supercharge") or {}).get("constants") or {}).get("damageProfile")
        if not prof or (damage_profile or "") != prof:         # DamageProfileIs(GetDamageProfile(config))
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)                        # Supercharge = ability ACTIVE du poseur
        v = ability_var("Supercharge", "extraPierceRatio", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_piercing(False, int(v)) if v else None      # owner=cible (percage de QUI l'attaque)


class TerrifyingExtraDefenseEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Terrifying_ExtraDefense_Effect$$CreateDamageModifier : réduit le dégât MÊLÉE reçu par
    son PORTEUR (l'effet est sur la CIBLE). Trigger natif = `get_OwnerIsTarget & IsMeleeAttack`
    (AbilityOrEffect 0x62) ; valeur = `ConfigConst(0x28)`.

    ⚠ Le trait `Terrifying` (id 0x22=34) N'EST PAS lu en direct dans le calcul de dégât (≠ MkXGravis
    `HasTrait(cible, 0x3f5)` IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor). Il DÉRIVE une triggered ability qui pose CET effet sur le porteur
    — chaîne RE'd intégralement (#73) : `Trait..idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor` dict `GetTriggeredAbility` (+0x0, lu par
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility`) mappe trait 0x22 -> TriggeredAbilityType 0x62 ;
    `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` ajoute cette ability (`TerrifyingAbilityAbility`
    IdunBattleLogic.Entities.Abilities.Active.TerrifyingAbilityAbility$$.ctor = `AOwnerEffectSpecificTriggeredAbility(0x62)`) ; son `IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger` =
    `OnOwnerSpecificAbilityInit(0x62)` -> à l'init du porteur, sa behaviour `AddEffect(owner,
    Terrifying_ExtraDefense 0x62)`. Effet enregistré `EffectsDatabase.<InitializeEffects>b__14_11`. Côté
    port : matérialisé pour un porteur CAPTÉ live (`decisionView.effects`, ex. eldarMauganRa) et, faute de
    capture (summon spawné), seedé via `TRAIT_DERIVED_ABILITIES["Terrifying"]` (factory.py).

    Magnitude = `ConfigConst(0x28)` = `clientGameConfig.globalValues.terrifyingBonus` (= **-30**, signé comme
    `elevationBonus`=+50 / `trenchBonus`=-50) — LU en gameconfig (PAS un trait var : `trait("Terrifying")`
    est vide). ⇒ malus défenseur `PercentDecrease(|−30|)` = ×0.70 gated `IsMeleeAttack` (no-op sur attaque
    ranged / contexte inconnu). VALIDÉ bit-exact LIVE (#73, eldarMauganRa : per-hit combat offline == live en
    mêlée ×0.70 ET ranged ×1.0)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if not is_melee:                         # gated IsMeleeAttack
            return None
        # ConfigConst(0x28) = globalValues.terrifyingBonus (= -30 signé, mirror elevation/trench @globalValues).
        red = global_value("terrifyingBonus")
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner_is_caster=False (effet sur le défenseur) -> x0.70


class MartialKatahDmgReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.MartialKatah_DmgReductionEffect$$CreateDamageModifier` (trait MartialKatah, Custodes
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


class VexillaMagnificaDmgReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.VexillaMagnifica_DmgReductionEffect$$CreateDamageDefenseModifier` (active
    VexillaMagnifica 1183, custoVexilusPraetor — effet 0x567=1383, nom capté
    "VexillaMagnifica_DmgReduction") : réduit le dégât reçu par son PORTEUR. #29 lead 2 (la pièce
    ×0.34 du miss 777 s15).

    Trigger natif = `get_OwnerIsTarget` SEUL (décompilé IdunBattle.Entities.Effects.Loki.VexillaMagnifica_DmgReductionEffect$$CreateDamageDefenseModifier : AUCUN gate profil/mêlée/normal)
    → s'applique à TOUT dégât reçu, prédiction ET combat. Valeur = `ConfigVar(0x46=dmgReductionPct,
    GetAbilityState(effet))` = `dmgReductionPct[ablvl]` des variables VexillaMagnifica (=66 à tous
    les niveaux utiles, HORS variablesAffectedByRarityBonus → multiplier no-op ; même clé 0x46 que
    SmashaEad/GuardianOrganism/OverwhelmingWrath). `EffectBonus.ForPercentDecrease` → entrée %-list
    multiplicative standard. VALIDÉ BIT-EXACT (777 s15, u83 stunné -> u87 porteur) :
    ×0.8 (MartialKatah) × 0.5 (Stunned) × 0.34 (CE malus) = 219-437 == natif.

    NB : l'effet est posé par le toggle actif VexillaMagnifica (le porteur « plante la bannière ») —
    la POSE runner-face n'est pas portée ; ici on consomme l'effet CAPTÉ (présent = actif)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        red = ability_var("VexillaMagnifica", "dmgReductionPct", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
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
    """`IdunBattle.Entities.Effects.Loki.TerminatorArmour_ReduceDmg_Effect$$CreateEffectDamageMalusForDefense : réduit de
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
    """`IdunBattle.Entities.Effects.Loki.GuardianOrganism_DamageReductionEffect$$CreateEffectDamageMalusForDefense` (trait
    GuardianOrganism, tanks Tyranides ex. tyranTyrantGuard) : réduit le dégât REÇU par son porteur de
    `min(dmgReductionPct% × CurrentDamage, dmgReduction[cap] × mult)` — `EffectBonus.ForSubtraction(
    OwnerIsTarget, Min(PercentageOf(CurrentDamage, ConfigVar(0x46)), ConfigVar(0x12)))`. Réduction
    DYNAMIQUE (fraction du dégât courant) + CAPÉE absolue -> kind `PercentSubtractionCapped` (≠ un simple
    PercentDecrease : le cap plafonne le MONTANT soustrait, pas le %).
      - pct = ConfigVar(0x46) = `dmgReductionPct` [25..33 par niveau, NON rarity-scaled].
      - cap = ConfigVar(0x12) = `dmgReduction` [20..1455, rarity-scaled × mult].
    AURA (`IdunBattle.Entities.Effects.Loki.GuardianOrganism_DamageReductionEffect$$CreateTargetSelector` = Self + `AdjacentFriends(range 1)`) : l'effet se MATÉRIALISE
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


class NightshroudDmgReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier` (ability Nightshroud de
    Sibyll Devine `astraPrimarisPsy`, base `ADamageDefenseModifierAbilityEffect(0x416)` = IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$.ctor) :
    réduit d'un montant PLAT le dégât REÇU par son porteur — `EffectBonus.ForSubtraction(OwnerIsTarget,
    ConfigVar(0x12)=dmgReduction × mult)`. i2 : « All friendly units starting their turn adjacent to Sibyll
    Devine gain Infiltrate for that turn and take -{dmgReduction} Damage from each hit in their and the next
    enemy turn. » (le grant Infiltrate + la durée their+next-enemy-turn = cycle de vie de l'effet ; le
    ForSubtraction est le SEUL terme de dégât).
      - montant = ConfigVar(0x12) = `dmgReduction` [5..364 par niveau, RARITY-SCALÉ : dmgReduction ∈
        variablesAffectedByRarityBonus] × `mult` (= `*(effet+0x60)`) = niveau/mult du porteur = le DÉFENSEUR
        (EffectsState.seed les propage sur chaque allié ring-1 de Sibyll, comme l'AURA GuardianOrganism #89).
    AUCUN gate (OwnerIsTarget SEUL -> s'applique mêlée ET ranged, normale ET spéciale, tout profil de dégât ;
    ≠ le percent-decrease gaté de Terrifying/MartialKatah). PER-COUP : « -X Damage from EACH hit » -> additif
    DÉFENSEUR @+0x10 soustrait de la BASE **PRÉ-perçage** (comme l'additif attaquant #75), donc DILUÉ par
    perçage/armure PUIS scalé ×%-list -> son effet SANTÉ ≪ la valeur config. Canal `flat_reductions` (fusionné
    dans `mods.additive` au merge prediction, SANS le pré-scale ×M de Neuroparasite). MESURÉ LIVE (#111,
    ArmoriumCherub u92->custoTrajann adjacent à Sibyll, varTrace {lvl50,mult180}) : valeur config **499** ;
    dilué par le facteur perçage/armure (~0.31) -> ~155/coup de dégât SANTÉ = oracle [1620,2744] (le "155"
    n'est PAS la config mais 499 traversant l'armure). Port sans NS = [2240,3364] (sur-préd +620 agg)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        red = ability_var("Nightshroud", "dmgReduction", lvl,          # ConfigVar 0x12 (rarity-scalé × mult)
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_subtraction(False, abs(int(red)))   # owner=défenseur (effet sur la cible) ; plat PRÉ-perçage (#120)


class NeuroparasiteEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateEffectDamageMalusForDefense` (passif du Neurothrope
    `Neuroparasite`, EffectType 0x49f=1183, base `ABondEffect` = lien cible<->Neurothrope infecteur).
    Malgré le nom « MalusForDefense », c'est un ADDITIF **POSITIF** au dégât PSYCHIQUE reçu (le porteur =
    une faiblesse infligée) :
      `EffectBonus.ForAddition(OwnerIsTarget & AreEqual(BondedEntity, damageSource) & DamageProfileIs(0xd),
                               Multiply(ConfigVar(8=extraDmg, sourceAbilityState), EffectLevel))`
    = **+extraDmg[niveauSource] × niveau_de_parasite** au dégât psychique de LE Neurothrope qui a infecté la
    cible. i2 : « Psychic Damage dealt by the Neurothrope is increased by +1237 Damage for each level of a
    Neuroparasite on the target » (`extraDmg[L65]=1237` ; max 15 niveaux via `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetMaximumLevel`).

    Gates natifs (IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateEffectDamageMalusForDefense) :
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
    - dégât IdunBattle.Entities.Effects.Loki.FightingRetreat_DamageReductionEffect$$CreateEffectDamageBonusForAttack : `EffectBonus.ForAddition(OwnerIsCaster, Multiply(ConfigVar(0x12=dmgReduction),
      MinusOne))` = **-dmgReduction PLAT** sur les attaques du PORTEUR (additif, PAS un pct).
      `dmgReduction` = variable par niveau (lvl65=582), flaggée `variablesAffectedByRarityBonus`.
    ⚠ Niveau/multiplier fidèles = ceux du CASTER SOURCE (Darkstrider, abilityState de l'effet), non
      captés pour un debuff d'origine ennemie → fallback niveau/multiplier du PORTEUR (approximation
      documentée ; identique en pratique sur rosters au même palier)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var("FightingRetreat", "dmgReduction", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, -int(v)) if v else None


class ShadowInTheWarpLessDmgEffect(BaseEffect):
    """`ShadowInTheWarp_LessDmg_Effect` (effet 1053=0x41d) — AURA de RÉDUCTION du dégât PSYCHIQUE. L'effet
    vit sur le PORTEUR (trait ShadowInTheWarp, ex. tyranSmnWarrior) et se PROJETTE sur les ENNEMIS
    environnants (psykers) : quand un tel ennemi attaque en PSYCHIQUE, son dégât est réduit.
    - dégât `IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateEffectDamageBonusForAttack : `ForPercentIncrease(OwnerIsActor &
      DamageProfileIs(0xd=Psychic), ConfigConst(0x3b))` = `shadowInTheWarpDmgModifier`% (=-25, négatif).
    - cible `IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateTargetSelector : `SurroundingEnemies(range=ConfigConst 0x16) &
      UnitsWithTrait(0x3ea) & UnitsNotFromFaction(0xc)`.
    MAGNITUDE + PORTÉE LUES du trait (`traitVariables.shadowInTheWarpDmgModifier=-25`, `shadowInTheWarpRange=2`).
    ⚠ Filtre `UnitsWithTrait(0x3ea)` (psyker) NON décodable offline (pas de map TRAIT) → SUR-APPROXIMÉ au
    seul gate PSYCHIQUE (tout ennemi attaquant en Psychic dans la portée subit le malus) ; raffinement quand
    le trait 0x3ea sera mappé. Canal AURA côté SOURCE (`create_aura_attack_damage_malus_for_enemy`), agrégé
    par `aura_attack_damage_malus_from_enemies` et ajouté aux modifiers de l'ATTAQUANT en prédiction."""

    def create_aura_attack_damage_malus_for_enemy(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if (c.get("damage_profile") or "") != "Psychic":    # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateEffectDamageBonusForAttack
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


class DaughterOfTheAbyssFriendlyDmgReductionPctEffect(BaseEffect):
    """`DaughterOfTheAbyss_FriendlyDmgReductionPctEffect` (effet 0x58b=1419, passif DaughterOfTheAbyss
    d'Atlacoya custoAtlacoya) — AURA de RÉDUCTION du dégât PSYCHIQUE REÇU par les AMIS du porteur
    (i2 : « Psychic Damage dealt to other friendly units within 2 hexes of Atlacoya is reduced by 33% »).
    L'effet vit sur le PORTEUR (posé par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DaughterOfTheAbyssAbility$$CreateBehaviour :
    AddEffect(0x58b) — capté live source=Atlacoya, JAMAIS matérialisé sur les amis) et se PROJETTE sur
    les cibles à la CALC (boucle state-wide EffectWithTarget × cibles de `CalculateDefenderModifiers-
    ForPrediction` IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction).
    - dégât `IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_FriendlyDmgReductionPctEffect$$CreateEffectDamageMalusForDefense : `(OwnerIsTarget & DamageProfileIs(0xd=
      Psychic)) -> -ConfigVar(0x46=dmgReductionPct, abilityState)` (négation via nœud Direct(-1), mirror
      du jumeau Owner IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_OwnerDmgReductionEffect$$CreateEffectDamageMalusForDefense `Multiply(ConfigVar, factory+0xd8)`).
    - cibles (selector famille, jumeau symétrique IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_ExtraDamagePctEffect$$CreateTargetSelector) : amis du porteur dans le rayon
      `constants.range` (=2), « OTHER » ⇒ exclut le porteur (qui a SON OwnerDmgReduction).
    MAGNITUDE : `dmgReductionPct[ablvl]` (25→33, hors variablesAffectedByRarityBonus ⇒ PAS de scaling
    rareté). GROUND TRUTH #184 (seed 2024 MC1_67) : bloodMephiston (Psychic) → tgts 81/83/85/79 tous à
    ≤2 hexes d'Atlacoya (6,8) = natif ×0.67 EXACT (2016,3024 = 1003×1.25×[0.8,1.2]×3×0.67), cible ALLIÉE
    de Mephiston (hors aura) = ×1.0 (3009,4515) ; u91 worldExecutions (profil Power) = bit-exact sans
    réduction. C'était le ~1.49x du flip-flop #184 (1/0.67), PAS un écart de hit-count."""

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if (c.get("damage_profile") or "") != "Psychic":      # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_FriendlyDmgReductionPctEffect$$CreateEffectDamageMalusForDefense
            return None
        if c.get("tgt_id") == c.get("owner_id"):              # « OTHER friendly units » : exclut le porteur
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None                                       # SurroundingFriends : cible ALLIÉE du porteur
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo
        rng = ability_var("DaughterOfTheAbyss", "range", is_constant=True)   # ConfigConst 0x16 (=2)
        if hexgeo.distance(op, tp) > int(rng if rng else 2):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        pct = ability_var("DaughterOfTheAbyss", "dmgReductionPct", level=lvl)
        if not pct:
            return None
        return for_percent_decrease(True, abs(int(pct)))      # -33% @L50 (négation Direct(-1) native)


class DaughterOfTheAbyssOwnerDmgReductionEffect(BaseEffect):
    """`DaughterOfTheAbyss_OwnerDmgReductionEffect` (effet 0x58a=1418) — réduction PLATE du dégât
    PSYCHIQUE reçu par le PORTEUR lui-même (i2 : « Atlacoya takes -1892 Psychic Damage »). L'effet est
    dans la liste d'effets de la CIBLE quand Atlacoya est visée ⇒ canal défenseur STANDARD.
    - dégât `IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_OwnerDmgReductionEffect$$CreateEffectDamageMalusForDefense : `(OwnerIsTarget & DamageProfileIs(0xd=
      Psychic)) -> Multiply(ConfigVar(0x12=dmgReduction, abilityState), Direct(-1) factory+0xd8)`
      = soustraction plate (slot additif défenseur @+0x10, mirror Nightshroud #111/#120).
    MAGNITUDE : `dmgReduction[ablvl]` ∈ variablesAffectedByRarityBonus ⇒ × multiplier de l'unité.
    ⚠ NON VALIDÉ LIVE (#184) : structure lue du décompilé (jumeau exact de Nightshroud IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier,
    lui validé) mais aucune mesure native vs Atlacoya-cible obtenue (hors plans dans les seeds
    d'audit + rows toujours predOptimistic via son Parry_ReduceHits) — placement per-hit additif
    présumé par la famille."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if (damage_profile or "") != "Psychic":               # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_OwnerDmgReductionEffect$$CreateEffectDamageMalusForDefense
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        amt = ability_var("DaughterOfTheAbyss", "dmgReduction", level=lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not amt:
            return None
        # owner=défenseur (effet sur la cible) → flat_reductions PRÉ-perçage (routage Nightshroud #120)
        return for_subtraction(False, abs(int(amt)))


class OverwhelmingWrathRangeDmgReductionEffect(BaseEffect):
    """`OverwhelmingWrath_RangeDmgReductionEffect` (EffectType 0x515=1301, nom capté
    "OverwhelmingWrath_RangeDmgReduction" ; famille `ADamageDefenseModifierAbilityEffect`, IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_RangeDmgReductionEffect$$.ctor = base(0x475=1141 = OverwhelmingWrath, l'ACTIVE d'Azkor worldEightbound)) — i2 :
    « Until the beginning of his next turn Azkor Taunts all adjacent enemies and takes -64% Damage
    from ranged attacks. » Effet TRANSIENT (rem=1 capté), posé par l'ExecuteBehaviour de l'ability
    (IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour), expire au début du tour suivant du porteur. #190.

    - dégât `IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_RangeDmgReductionEffect$$CreateDamageDefenseModifier` : `EffectBonus.ForPercentDecrease(
      get_OwnerIsTarget & IsRangedAttack, ConfigVar(0x46=dmgReductionPct, GetAbilityState(effet)))`
      → le dégât des attaques RANGED reçues par le porteur est réduit de `dmgReductionPct`%.
      Gate RANGED strict (aucun filtre profil/normal) ; contexte inconnu (is_melee=None) → no-op.
    - MAGNITUDE : `dmgReductionPct[ablvl]` (24→64, plateau à 64 dès L36 ; HORS
      variablesAffectedByRarityBonus=[minDmg,maxDmg] → multiplier no-op). Ability ACTIVE →
      active_ability_level, fallback ability_level (seed = passif ; plateau ⇒ écart no-op) / level.

    GROUND TRUTH #190 (seed 777 MC1_67 iter-4, session 22) : meph (1,4) → Azkor (3,4) dist 2
    (ranged), tout Grass, elev 3=3 — l'hypothèse « positionnelle » de la tâche est RÉFUTÉE par
    mesure (toggles no-elev/no-board strictement inertes) : oracle=(532,798) = engine ×0.360 EXACT
    min ET max = 1−0.64 ; à iter-5 (effet expiré) le MÊME couple matche BIT-EXACT → transient,
    pas positionnel. (L'effet jumeau `OverwhelmingWrath_PendingAttack` 0x514=1300 = l'attaque
    différée 2× Eviscerate au début du tour suivant — hors canal modifier, non porté ici.)"""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if is_melee is not False:                # gated IsRangedAttack IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_RangeDmgReductionEffect$$CreateDamageDefenseModifier
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        pct = ability_var("OverwhelmingWrath", "dmgReductionPct", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        return for_percent_decrease(False, abs(int(pct)))   # owner=défenseur (l'effet est sur la cible)


class PsychicFortressDmgReductionEffect(BaseEffect):
    """`PsychicFortress_DmgReductionEffect` (effet 0x3f2=1010, passif PsychicFortress de Tigurius
    ultraTigurius ; base `ADamageDefenseModifierAbilityEffect(1000=0x3e8=PsychicFortress AbilityOrEffect)`,
    IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$.ctor) — AURA de RÉDUCTION PLATE du dégât PSYCHIQUE REÇU par les AMIS ring-1 du porteur.
    L'effet vit sur le PORTEUR (posé par `IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicFortressAbility$$CreateBehaviour` :
    `AddEffect(0x3f2, AbilityStateRef, context@0x148)` — capté live source=Tigurius, JAMAIS matérialisé
    sur les amis) et se PROJETTE sur les cibles à la CALC (boucle state-wide EffectWithTarget × cibles de
    `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`, canal `aura_defense_damage_malus_from_units`).

    - dégât `IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateDamageModifier` : `EffectBonus.ForAddition(OwnerIsTarget &
      DamageProfileIs(0xd=Psychic), Multiply(ConfigVar(0x12=dmgReduction, GetAbilityState(effet),
      mult@+0x60), Direct(-1)@factory+0xd8))` = SOUSTRACTION plate négative (slot additif défenseur @+0x10,
      jumeau STRUCTUREL EXACT de `DaughterOfTheAbyss_OwnerDmgReduction IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_OwnerDmgReductionEffect$$CreateEffectDamageMalusForDefense` et `Nightshroud IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier`).
    - cibles `IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateTargetSelector` : `Friends(SurroundingUnits(context@0x148, range=1,
      includeCenter=false))` = amis à distance EXACTEMENT 1 (ring-1), EXCLUT le porteur (includeCenter=false).

    MAGNITUDE : `dmgReduction[ablvl]` (12->873, RARITY-SCALÉ : dmgReduction ∈ variablesAffectedByRarityBonus)
    × mult du porteur (Tigurius = le carrier de l'aura -> `self.ability_level`/`self.ability_variables_multiplier`).
    i2 : « ... Also reduces incoming Psychic Damage by 873. » Placement PRÉ-perçage (`for_subtraction(False)`
    -> `flat_reductions`) présumé par la famille Nightshroud (jumeau structurel, validé #120) : additif défenseur
    plat soustrait de la BASE pré-perçage, dilué par perçage/armure PUIS scalé ×%-list. Gate Psychic-only
    (l'aura protège les amis du porteur contre les attaques PSYCHIQUES des psykers ennemis)."""

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if (c.get("damage_profile") or "") != "Psychic":     # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateDamageModifier
            return None
        if c.get("tgt_id") == c.get("owner_id"):              # SurroundingUnits(includeCenter=false) exclut le porteur
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None                                       # Friends : cible ALLIÉE du porteur
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo
        if hexgeo.distance(op, tp) != 1:                      # SurroundingUnits(range=1, includeCenter=false) = ring-1 exact IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateTargetSelector
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        amt = ability_var("PsychicFortress", "dmgReduction", lvl,   # ConfigVar 0x12 (rarity-scalé × mult)
                          multiplier_pct=self.ability_variables_multiplier)
        if not amt:
            return None
        return for_subtraction(False, abs(int(amt)))          # owner=défenseur -> flat_reductions pré-perçage (famille Nightshroud)
