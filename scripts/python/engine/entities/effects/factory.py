"""`EffectFactory` — instancie la bonne sous-classe `BaseEffect` depuis un effet capté (registre
nom d'EffectType → classe). Mirror du dispatch natif « EffectType → classe d'effet ».

Effet non porté → `BaseEffect` (no-op) = dégradation fidèle (présent mais sans contribution, cf. §17.4
« présent ≠ appliqué »). Registre extensible (`EffectFactory.register`) au fil du portage du roster.
"""
from __future__ import annotations

from collections.abc import Mapping

from .base import BaseEffect
from .loki import (
    ActOfFaithBuffEffect,
    AnvilShieldAdditionalBlockEffect,
    AstartesBannerExtraHitEffect,
    ContaminatedUnitEffect,
    BigTargetAdjacentEffect,
    CrushingStrikeEffect,
    DecoysAndMisdirectionExtraDamageEffect,
    FightingRetreatDmgReductionEffect,
    FightingRetreatHitReductionEffect,
    GuardianOrganismDamageReductionEffect,
    HeavyWeaponExtraDmgEffect,
    KanOpenerEffect,
    LightCoverEffect,
    MartialKatahDmgReductionEffect,
    BeastSlayerExtraDmgEffect,
    BeastSlayerExtraBlockEffect,
    MasterAnnihilatorAdditionalHitEffect,
    NeuroparasiteEffect,
    NightshroudDmgReductionEffect,
    ParryEffect,
    PathOfCommandExtraDmgEffect,
    RangedSpecialistEffect,
    PinnedEffect,
    PowerTripFullHealthEffect,
    PowerTripIgnoreArmorEffect,
    RapidAssaultExtraDamageEffect,
    RitesOfBattleExtraDmgEffect,
    ShadowInTheWarpLessDmgEffect,
    SmashaEadExtraDamageEffect,
    StandVigilExtraArmorEffect,
    StunnedEffect,
    TauntedEffect,
    TerminatorArmourReduceDmgEffect,
    TerrifyingExtraDefenseEffect,
)

# Registre nom d'EffectType (`decisionView.effects[].name`) → classe d'effet. À ÉTENDRE au roster.
EFFECT_CLASSES: dict[str, type[BaseEffect]] = {
    "RapidAssault_ExtraDamage": RapidAssaultExtraDamageEffect,
    # AURA +dégât (Attack) du SOURCE Calgar (RitesOfBattleAbility @181225340) : 2 effets permanents
    # mutuellement exclusifs par trait Imperial (26). Noms captés EXACTS = ...Basic (1002) / ...Imperial
    # (1003) ; la classe lit le variant via self.name (endswith Imperial). Modélisée SOURCE-side
    # (create_aura_attack_bonus, ré-évaluée par candidat) — cf. #49 prediction.md point 18.
    "RitesOfBattle_ExtraDmgBasic": RitesOfBattleExtraDmgEffect,
    "RitesOfBattle_ExtraDmgImperial": RitesOfBattleExtraDmgEffect,
    # AURA +Attack (rayon 2) du SOURCE Loki (PathOfCommandAbility @181110f10) : friends dist<=2,
    # +extraDmg (+extraDmg_2 si même grande-alliance que Loki). ExtraDmg=1112 ; ExtraCrit (1107,
    # extraCritChance) = axe CRIT, canal aura-crit non porté (TODO). Nom capté = "PathOfCommand_ExtraDmg".
    "PathOfCommand_ExtraDmg": PathOfCommandExtraDmgEffect,
    # Stat-mod +armure (FixedArmor) FLAT, SELF-buff extraArmor[level] (résidu 0 validable ; nom à confirmer).
    "StandVigil_ExtraArmor": StandVigilExtraArmorEffect,
    "RangedSpecialist": RangedSpecialistEffect,  # +33% dégât RANGED (trait, actif si pas parti adjacent)
    "HeavyWeapon_ExtraDmg": HeavyWeaponExtraDmgEffect,   # +25% dégât RANGED (trait HeavyWeapon→Overwatch)
    # CrushingStrike (trait Terminators, effet 0x4a2=1186, nom capté = 'CrushingStrike') : +50% dégât
    # MÊLÉE NORMALE si pas bougé (@180f3ad90 ForPercentIncrease gated OwnerIsCaster & IsNormalAttack &
    # IsMeleeAttack ; ActiveCondition NOT HasMoved @180f3ad50). #98.
    "CrushingStrike": CrushingStrikeEffect,
    # SmashaEad (orksNob "Tanksmasha") : +extraDmg[level]×mult FLAT au dégât des attaques NORMALES
    # (effet posé quand le porteur a traversé ≥2 hexes ce tour ; @180f6bee0 ForAddition). #68.
    "SmashaEad": SmashaEadExtraDamageEffect,
    # BeastSlayer (orksNob/Titus/Farsight/...) : +20% degat MELEE vs BigTarget/Vehicle (trait,
    # target-conditionnel @180f336c0 ForPercentIncrease ; gate is_melee + target_traits). #68.
    "BeastSlayer_ExtraDmg": BeastSlayerExtraDmgEffect,
    # BeastSlayer cote DEFENSE : +10% chance de bloquer 100% du FixedArmor courant en degat (source de
    # block SUPPLEMENTAIRE, AddExtraBlockEffectToOwner @180e18b70 ; absente du scalaire GetStat(7/8)). #72.
    "BeastSlayer_ExtraBlock": BeastSlayerExtraBlockEffect,
    "PowerTrip_FullHealth": PowerTripFullHealthEffect,
    "PowerTrip_IgnoreArmor": PowerTripIgnoreArmorEffect,
    "Stunned": StunnedEffect,           # effet COMPOSITE (parent 1162 → enfants 1165/1166/1167)
    "ActOfFaith_Effect": ActOfFaithBuffEffect,  # buff crit empilable (1017) — stack seedé = cc/cd_delta 0
    # Tyrant Guard (CrushingClaws) :
    "Taunted_OnlySpecificTargets": TauntedEffect,  # COMPOSITE 27 → enfants 25/26/1237 (bond cible↔tauntant)
    "Pinned": PinnedEffect,             # 1065 (UI « Suppressed ») — stat-mod Movement (matérialisé seul)
    "Terrifying_ExtraDefense": TerrifyingExtraDefenseEffect,  # -30% dégât MÊLÉE reçu (defender, gated melee)
    "TerminatorArmour_ReduceDmg": TerminatorArmourReduceDmgEffect,  # -75% dégât reçu SAUF Psychic/DirectDamage (defender, gated profil)
    # GuardianOrganism (tanks Tyranides) : reduit le degat recu de min(dmgReductionPct%(25-33) x dmg,
    # dmgReduction_cap x mult) = PercentSubtractionCapped (dynamique+capee) ; aura self+adjacents. #89.
    "GuardianOrganism_DamageReduction": GuardianOrganismDamageReductionEffect,
    # Nightshroud (Sibyll Devine astraPrimarisPsy) : aura -dmgReduction Damage "from each hit" aux allies
    # ring-1 en debut de tour (defender, ForSubtraction @180f5bff0 ; SANS gate) = additif defenseur @+0x10
    # PRE-percage (config 499 dilue par armure -> ~155 sante). #111.
    "Nightshroud_DmgReduction": NightshroudDmgReductionEffect,
    # MartialKatah (Custodes ex. custoTrajann/custoVexilusPraetor) : -20% degat des ATTAQUES NORMALES
    # recues (defender, gated IsNormalAttack ; @180f58b30 ForPercentDecrease ConfigConst 0x72=
    # martialKatahDmgReductionPct). Le DmgBonus (+100% vs Summons) reste no-op (canal attaquant, hors gap). #105.
    "MartialKatah_DmgReduction": MartialKatahDmgReductionEffect,
    # Neuroparasite (passif Neurothrope ; EffectType CAPTE = 1218 'Neuroparasite', name-route ; ctor 0x49f=1183
    # = AbilityOrEffect, distinct) : ADDITIF +extraDmg[nivSource]xniveau_parasite au degat PSYCHIQUE recu DE CE
    # Neurothrope (defender, ForAddition gated Psychic + AreEqual(source)). Magnitude+gating+PLACEMENT (scale
    # x%-list, avant-%list) VALIDES LIVE BIT-EXACT #86/#88 (2 separateurs RS on/off ; L1 port==natif 4392-5461).
    "Neuroparasite": NeuroparasiteEffect,
    # Debuffs FightingRetreat (Darkstrider) — posés sur les ENNEMIS adjacents, s'appliquent aux
    # ATTAQUES du porteur : -dmgReduction PLAT + -1 coup (plancher 1), 1 round (rem=2 capté).
    "FightingRetreatDmgReduction": FightingRetreatDmgReductionEffect,
    "FightingRetreatHitReduction": FightingRetreatHitReductionEffect,
    "LightCover": LightCoverEffect,     # couverture (tuile) : -2 coups ranged reçus, plancher 1
    "Parry_ReduceHits": ParryEffect,    # trait Parry : -1 coup MÊLÉE reçu, plancher 1
    "MasterAnnihilator_extraHit": MasterAnnihilatorAdditionalHitEffect,  # debuff Vitruvius : +1 coup reçu (non-Psychic)
    "BigTarget_AdjacentEffect": BigTargetAdjacentEffect,  # aura : -1 coup ranged aux alliés ring-1 du porteur
    # AstartesBanner (porte-banniere Astartes ex. templAncient) : AURA +extraHits(=1) coup MELEE aux ALLIES
    # dans le rayon 2 du porteur (l'effet vit sur LE PORTEUR, comme BigTarget ; @180f323b0 ForAddition
    # OwnerIsCaster&IsMeleeAttack ConfigVar 0xd, selector SurroundingFriends range ConfigConst 0x16=2). #107.
    "AstartesBanner_ExtraHit": AstartesBannerExtraHitEffect,
    "ShadowInTheWarp_LessDmg_Effect": ShadowInTheWarpLessDmgEffect,  # aura : -25% degat PSYCHIQUE aux ennemis a portee
    # DecoysAndMisdirection (Genestealer Cults ex. genesPrimus/genesMagus/genesKelermorph) : +extraDmg
    # FLAT additif a TOUTES les attaques de l'ami buffe (pose quand un decoy est spawn a cote / qu'un ami
    # marche sur un decoy). Gate OwnerIsCaster SEUL (@180f3e340 -> applique en prediction+combat, cf.
    # Neuroparasite). extraDmg[L65]=582 rarity-scale x mult. EffectType capte 1379. #134 (spawn+retaliation
    # Blast NON encore portes -- seul l'effet ExtraDamage l'est ici). Nom capte = effect-type-names.ts:502.
    "DecoysAndMisdirection_ExtraDamage": DecoysAndMisdirectionExtraDamageEffect,
    # AnvilShield (Arjac spaceRockfist) : buff BLOCK_DAMAGE self quand il BLOQUE (0x4b2=1202,
    # AddStaticStatModifierEffect stat 8, var blockDmg[L65]=728 rarity-scale ; @180e16340). INCONDITIONNEL.
    # Le 2e effet de la behaviour (0x4b0=1200 BlockChanceBelowHealthCap, stat 7=BLOCK_CHANCE/blockChance) N'EST
    # PAS inscrit (gate sante abs-vs-% non tranche) ; 1201 FrozenAttackerAdvantage (dynamique) non plus. #133.
    "AnvilShield_AdditionalBlock": AnvilShieldAdditionalBlockEffect,
    # Contaminated_Unit (0x4dd=1245) : sous-effet -X% FixedArmor pose sur une unite occupant/entrant une
    # tuile contaminee (0x4dc). Debuff stat FixedArmor (=16) ; magnitude X NON resolue (#132) -> value=None
    # tant que non mesure live (present mais inerte-stat). Pose par le vecteur tile-effect ContaminatedTileEffect
    # (#128, triggers.py). Nom capte = effect-type-names.ts:368.
    "Contaminated_Unit": ContaminatedUnitEffect,
    # KanOpener : nom d'EffectType à confirmer avant inscription.
}


# `StaticBattleRules.Trait.GetEffectToBeAddedToOwnerForTrait` @18157e800 — dict TraitType -> List<EffectType>
# des owner-effects AJOUTÉS au porteur À LA CRÉATION D'UNITÉ (`InitializeActorAbilitiesOperation.Execute`
# @180e74660, boucle TRAITS). Dict peuplé par `Trait..cctor` @18157f650 (static field +0x30). 4 entrées LUES
# du décompilé (ids natifs cités). Clés = NOM de trait gameconfig ; le natif clé par TraitType enum, la
# correspondance nom<->id est TRIANGULÉE (trait gameconfig `units.traits` <-> effet capté live <-> dict) :
#   custoVexilusPraetor trait "MartialKatah" -> effets captés MartialKatah_DmgBonus+DmgReduction == dict 0x41f ;
#   tauDarkstrider trait "RangedSpecialist" -> effet capté "RangedSpecialist" == dict 0x424 ; idem HeavyWeapon.
# Le natif AJOUTE aussi des owner-effects via la boucle ABILITIES (GetEffectToBeAddedToOwnerForAbility, dict
# ActiveAbility +0x50) — chemin SÉPARÉ non porté ici (ex. BigTarget passe par une ability accordée).
TRAIT_OWNER_EFFECTS: dict[str, list[str]] = {
    "HeavyWeapon": ["HeavyWeapon_ExtraDmg"],                                 # trait 0x3e9=1001 -> 0x3f0=1008
    "MartialKatah": ["MartialKatah_DmgBonus", "MartialKatah_DmgReduction"],  # 0x41f=1055 -> 0x56b=1387,0x56a=1386
    "RangedSpecialist": ["RangedSpecialist"],                                # 0x424=1060 -> 0x5eb=1515
    # trait 0x41e=1054 -> Clone (0x53d=1341) : trait de clone/summon, nom gameconfig non requis (aucun
    # summon concerné) -> omis tant que le nom n'est pas confirmé (fidélité-safe : n'affecte aucun porteur ici).
}


def get_effect_to_be_added_to_owner_for_trait(trait_name: str) -> list[str]:
    """`StaticBattleRules.Trait.GetEffectToBeAddedToOwnerForTrait` @18157e800 — pour un trait, la LISTE des
    noms d'EffectType à ajouter à son porteur à la création (dict `Trait..cctor` @18157f650 +0x30). Trait
    sans owner-effect -> [] (le natif renvoie null)."""
    return TRAIT_OWNER_EFFECTS.get(trait_name, [])


# --- Chemin ABILITY-DÉRIVÉE (distinct des 2 dicts owner-effect directs) : un trait DÉRIVE une ability, et
# c'est le `CreateBehaviour` de cette ability qui pose l'owner-effect à SON init. (RE re-expert : BigTarget.)
#
# ⚠ NE PAS confondre avec `GetEffectToBeAddedToOwnerForAbility` (dict `ActiveAbility` +0x50) : celui-ci ne
# contient QUE {PlasmaCannon->PlasmaCannon_Visual, GravitonRifle->GravitonRifle_ExtraPierce} (armes joueur,
# aucun summon concerné) -> non porté. BigTarget passe par LE CHEMIN CI-DESSOUS.
#
# Étape 1 — `AddTraitOperation.AddDerivedAbilities @180e513c0` (appelé par `AddTraitOperation.Execute
# @180e51901`) : à la création, un trait dérive une ability via `Trait.GetTriggeredAbility` (dict Trait +0x0
# @18157ed10) / `GetActiveAbility` (dict Trait +0x8 @18157e720) et l'ajoute à l'unité. Clés = NOM trait
# gameconfig. Seul BigTarget est porté (chaîne complète RE'd + effet modélisé) ; les autres traits summon
# dérivent aussi une ability (Synapse 0x423, ShadowInTheWarp 0x424, InstinctiveBehaviour 0x413, BattleFatigue
# 0x401) MAIS on n'a PAS lu si leur CreateBehaviour pose un owner-effect -> non portées (fidélité-safe).
TRAIT_DERIVED_ABILITIES: dict[str, list[str]] = {
    "BigTarget": ["BigTarget"],     # UnitTrait.BigTarget 0x3f9=1017 -> ability 0x406=1030 (dict Trait +0x0)
    # ShadowInTheWarp 0x3f9+... 2025 -> ability derivee 0x424 = ShadowInTheWarp_AddEffectAbility (pattern
    # generique _AddEffectAbility : base CreateBehaviour pose constants.effectType au porteur).
    "ShadowInTheWarp": ["ShadowInTheWarp"],
}

# Étape 2 — owner-effects posés par `<Ability>.CreateBehaviour` À L'INIT de l'ability (DSL `AddEffect(owner)`).
# Table par NOM d'ability (chaque entrée = VA du CreateBehaviour source).
ABILITY_INIT_OWNER_EFFECTS: dict[str, list[str]] = {
    "BigTarget": ["BigTarget_AdjacentEffect"],   # `BigTargetAbility.CreateBehaviour` @18121a910 : AddEffect(0x402)
    # `ShadowInTheWarp_AddEffectAbility` (base `AddEffectAbility.CreateBehaviour`) : AddEffect(0x41d=1053).
    "ShadowInTheWarp": ["ShadowInTheWarp_LessDmg_Effect"],
    # `PathOfCommandAbility.CreateBehaviour` @181110f10 : AddEffect(0x458=1112 ExtraDmg) + AddEffect(0x453=1107
    # ExtraCrit). AURA +Attack rayon 2 aux allies (cf. loki.PathOfCommandExtraDmgEffect). Ces owner-effects sont
    # poses a l'INIT de l'ability = a l'ATTERRISSAGE pour un deep-strike (deferres pendant TeleportingIn ;
    # ground truth live ds_landing : absents au teleport-in, apparaissent au landing). ExtraCrit (axe crit) non
    # porte -> seul ExtraDmg est materialise.
    "PathOfCommand": ["PathOfCommand_ExtraDmg"],
}


def get_derived_abilities_for_trait(trait_name: str) -> list[str]:
    """`AddTraitOperation.AddDerivedAbilities` @180e513c0 (dicts Trait +0x0 triggered / +0x8 active) — abilities
    dérivées d'un trait à la création de l'unité. Trait sans dérivation portée -> []."""
    return TRAIT_DERIVED_ABILITIES.get(trait_name, [])


def get_owner_effects_added_on_ability_init(ability_name: str) -> list[str]:
    """Owner-effects posés par `<Ability>.CreateBehaviour` à l'INIT de l'ability (DSL AddEffect(owner)).
    Ability sans owner-effect-à-l'init porté -> []."""
    return ABILITY_INIT_OWNER_EFFECTS.get(ability_name, [])


class EffectFactory:
    """Factory d'effets matérialisés. `registry` = attribut de classe (partagé, extensible). `create`
    mappe UN effet capté ({name, effectType, level, remaining, source}) → sa sous-classe BaseEffect."""

    registry: dict[str, type[BaseEffect]] = EFFECT_CLASSES

    @classmethod
    def create(cls, captured: Mapping, ability_variables_multiplier: int = 100,
               ability_level: int | None = None,
               active_ability_level: int | None = None) -> BaseEffect:
        name = captured.get("name")
        klass = cls.registry.get(name, BaseEffect)
        # RemainingTurns capté : 0 = PAS de compte-à-rebours (passif/aura/this-turn ; retrait géré par
        # TRIGGER, pas par timer — cf. tous les effets seed-777 à rem=0). On le mappe → None (permanent)
        # pour que `expired` (remaining_turns<=0) ne frappe QUE les effets réellement chronométrés (rem>0)
        # après décrément. Sans ça, le filtre droppait TOUS les effets captés (régression RapidAssault).
        rem = captured.get("remaining")
        remaining_turns = rem if (isinstance(rem, int) and rem > 0) else None
        # `ability_variables_multiplier`/`ability_level` = de l'unité porteuse (scale + index des vars
        # d'ability §17.21). `level` capté = stack level (≠ ability level).
        return klass(
            name=name, effect_type=captured.get("effectType"), level=captured.get("level"),
            ability_level=ability_level, active_ability_level=active_ability_level,
            remaining_turns=remaining_turns, source=captured.get("source"),
            ability_variables_multiplier=ability_variables_multiplier)

    @classmethod
    def create_many(cls, captured_list, ability_variables_multiplier: int = 100,
                    ability_level: int | None = None,
                    active_ability_level: int | None = None) -> list[BaseEffect]:
        return [cls.create(c, ability_variables_multiplier, ability_level, active_ability_level)
                for c in (captured_list or [])
                if isinstance(c, Mapping) and c.get("name")]

    @classmethod
    def register(cls, name: str, klass: type[BaseEffect]) -> None:
        cls.registry[name] = klass
