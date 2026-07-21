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
    BeaconOfRageExtraDamageEffect,
    BeaconOfRageFriendlyExtraDamageEffect,
    BlessingsOfKhorneModifiersEffect,
    ContaminatedUnitEffect,
    OverwhelmingWrathRangeDmgReductionEffect,
    VexillaMagnificaDmgReductionEffect,
    StunnedDamageModifierEffect,
    BigTargetAdjacentEffect,
    CrushingStrikeEffect,
    DaughterOfTheAbyssExtraDamagePctEffect,
    DaughterOfTheAbyssFriendlyDmgReductionPctEffect,
    DaughterOfTheAbyssOwnerDmgReductionEffect,
    DecoysAndMisdirectionExtraDamageEffect,
    FeederTendrilsExtraDamageEffect,
    LordOfTempestsExtraDamageEffect,
    FightingRetreatDmgReductionEffect,
    FightingRetreatHitReductionEffect,
    GuardianOrganismDamageReductionEffect,
    HeavyWeaponExtraDmgEffect,
    HypersensoryMinimalHealthEffect,
    KanOpenerEffect,
    LightCoverEffect,
    MartialKatahDmgReductionEffect,
    BeastSlayerExtraDmgEffect,
    MartialKatahDmgBonusEffect,
    BeastSlayerExtraBlockEffect,
    DaemonExtraBlockEffect,
    MasterAnnihilatorAdditionalHitEffect,
    CamouflageHitReductionEffect,
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
    SquigHoundAdditionalHitsEffect,
    CordClawAdditionalHitsEffect,
    FoulInfusionExtraHitsEffect,
    CyclicIonBlasterAdditionalHitsEffect,
    ExplosiveMaladiesExtraRangedAttackEffect,
    ExplosiveMaladiesExtraMeleeAttackEffect,
    LordOfTheHostExtraDamageEffect,
    DoomExtraDmgEffect,
    StandVigilExtraArmorEffect,
    StunnedEffect,
    TauntedEffect,
    TerminatorArmourReduceDmgEffect,
    TerrifyingExtraDefenseEffect,
    ProtectorImperativeEffect,
    ConquerorImperativeEffect,
)

# Registre nom d'EffectType (`decisionView.effects[].name`) → classe d'effet. À ÉTENDRE au roster.
EFFECT_CLASSES: dict[str, type[BaseEffect]] = {
    "RapidAssault_ExtraDamage": RapidAssaultExtraDamageEffect,
    "SquigHound_AdditionalHits": SquigHoundAdditionalHitsEffect,   # #179 : 2 coups hetero [minDmg,maxDmg] Physical
    # CordClaw (Exitor-Rho, effet 0x4e2=1250) : apres cast 1122, +nrOfHits_2=2 coups [minDmg_2,maxDmg_2]
    # DirectDamage a toutes ses attaques (@180f3a900, canal #179). #57c.
    "CordClaw_AdditionHits": CordClawAdditionalHitsEffect,
    # FoulInfusion (Pestillian, effet 0x432=1074 sur CHAQUE unite Chaos dans l'aura au cast) :
    # +nrOfHits=1 coup Toxic de ConfigVar(dmg)[state du cast] aux attaques normales (@180f4a340,
    # canal #179 GLOBAL : trigger IsMeleeAttack&OwnerIsCaster indecidable en display -> TRUE,
    # s'applique a TOUT attaquant en prediction — mesure 2468 s14). #57c-C.
    "FoulInfusion_ExtraHits": FoulInfusionExtraHitsEffect,
    # CyclicIonBlaster (Tau, triggered 1133, effet 0x47c=1148) : +nrOfHits=3 coups Particle de
    # minDmg[state] (+extraDmg si cible Markerlight/Mechanical) a TOUTES les attaques du porteur
    # (@180e1dd70, canal #179 forme "amount" : display n'evalue que le noeud MIN, spread pipeline).
    # Valide 54321 s19 (#57e).
    "CyclicIonBlaster_AdditionalHits": CyclicIonBlasterAdditionalHitsEffect,
    # ExplosiveMaladies (Pestillian, effets-AURA sur le PORTEUR) : +nrOfHits=1 coup Blast de
    # extraDmg[state] aux attaques normales des amis ADJACENTS (ranged: tous @180f43cc0 ;
    # melee: Chaos @180f43a40) — adjacence re-evaluee a la tuile candidate. #57c-C bit-exact.
    "ExplosiveMaladies_ExtraRangedAttack": ExplosiveMaladiesExtraRangedAttackEffect,
    "ExplosiveMaladies_ExtraMeleeAttack": ExplosiveMaladiesExtraMeleeAttackEffect,
    # LordOfTheHost (Dante, effet 0x562=1378 sur le PORTEUR) : aura +extraDmg[ablvl]xmult additif
    # pre-percage aux attaques MELEE des amis RapidAssault/Flying rayon 2 (@180f56e30 ForAddition,
    # selector @180f56fb0). Re-evaluee par tuile candidate. #57c.
    "LordOfTheHost_ExtraDamage": LordOfTheHostExtraDamageEffect,
    # Doom (Eldryon, effet 0x45a=1114 sur le PORTEUR) : les ennemis a EXACTEMENT 2 hexes du porteur
    # prennent +extraDmg[ablvl]xmult des attaques normales des amis du porteur (extraDmg_2 Aeldari,
    # toutes attaques) (@180f3f780, selector @180f3fa80 ring-exact). #57c.
    "Doom_extraDmg": DoomExtraDmgEffect,
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
    # DoctrinaImperatives (Tan Gi'da) — toggle @1811d4d20 : Protector = stat-mod +extraArmor sur FixedArmor(16)
    # (aura self+Mechanical-adjacents ; port SELF, portee = increment B) ; Conqueror = +extraDmg gate
    # HasNegativeModifier(cible FixedArmor<0) PRESENT-inerte (contribution +dmg = increment C).
    "ProtectorImperative": ProtectorImperativeEffect,   # 1247
    "ConquerorImperative": ConquerorImperativeEffect,   # 1248
    "RangedSpecialist": RangedSpecialistEffect,  # +33% dégât RANGED (trait, actif si pas parti adjacent)
    "HeavyWeapon_ExtraDmg": HeavyWeaponExtraDmgEffect,   # +25% dégât RANGED (trait HeavyWeapon→Overwatch)
    # CrushingStrike (trait Terminators, effet 0x4a2=1186, nom capté = 'CrushingStrike') : +50% dégât
    # MÊLÉE NORMALE si pas bougé (@180f3ad90 ForPercentIncrease gated OwnerIsCaster & IsNormalAttack &
    # IsMeleeAttack ; ActiveCondition NOT HasMoved @180f3ad50). #98.
    "CrushingStrike": CrushingStrikeEffect,
    # SmashaEad (orksNob "Tanksmasha") : +extraDmg[level]×mult FLAT au dégât des attaques NORMALES
    # (effet posé quand le porteur a traversé ≥2 hexes ce tour ; @180f6bee0 ForAddition). #68.
    "SmashaEad": SmashaEadExtraDamageEffect,
    # FeederTendrils (Deathleaper, effet 0x4ad=1197) : jumeau SmashaEad + gate IsCharging (@180f48ea0
    # ForAddition). +extraDmg[level]xmult FLAT PRE-percage sur l'attaque NORMALE de CHARGE melee ;
    # multiplier GLOBAL (pas per-ability #68, car c'est l'attaque normale de l'unite). #176.
    "FeederTendrils_ExtraDamage": FeederTendrilsExtraDamageEffect,
    # BeastSlayer (orksNob/Titus/Farsight/...) : +20% degat MELEE vs BigTarget/Vehicle (trait,
    # target-conditionnel @180f336c0 ForPercentIncrease ; gate is_melee + target_traits). #68.
    "BeastSlayer_ExtraDmg": BeastSlayerExtraDmgEffect,
    # BeastSlayer cote DEFENSE : +10% chance de bloquer 100% du FixedArmor courant en degat (source de
    # block SUPPLEMENTAIRE, AddExtraBlockEffectToOwner @180e18b70 ; absente du scalaire GetStat(7/8)). #72.
    "BeastSlayer_ExtraBlock": BeastSlayerExtraBlockEffect,
    # Daemon (trait, effet 1034) : 25% chance de bloquer 50% de l'Attack COURANTE du defenseur —
    # pilote WillBeKill/WillBeOverkill de la prediction (scenario block list[0]@0x50). #54A.
    "Daemon_ExtraBlock": DaemonExtraBlockEffect,
    "PowerTrip_FullHealth": PowerTripFullHealthEffect,
    "PowerTrip_IgnoreArmor": PowerTripIgnoreArmorEffect,
    "Stunned": StunnedEffect,           # effet COMPOSITE (parent 1162 → enfants 1165/1166/1167)
    # Enfant 1167 du composite Stunned : -StunnedDmgReductionPct% (BC Effect, =50) au dégât SORTANT du
    # porteur stunné (@180f6f770 ForPercentDecrease trigger OwnerIsActor -> boucle ATTAQUANT du port).
    # VALIDÉ BIT-EXACT 777 s15 (×0.8 MK × 0.5 stun × 0.34 vexilla = 219-437 == natif). #29 lead 2.
    "Stunned_DamageModifier": StunnedDamageModifierEffect,
    # VexillaMagnifica (active 1183 custoVexilusPraetor, effet 1383) : -dmgReductionPct% (=66, non
    # rarity-scalé) à TOUT dégât reçu par le porteur (@180f76510 ForPercentDecrease OwnerIsTarget SEUL,
    # aucun gate profil/mêlée). #29 lead 2.
    "VexillaMagnifica_DmgReduction": VexillaMagnificaDmgReductionEffect,
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
    # martialKatahDmgReductionPct). #105.
    "MartialKatah_DmgReduction": MartialKatahDmgReductionEffect,
    # MartialKatah face ATTAQUE (@180f58930) : +100% degat vs SUMMONS (HasTrait(target, Summon=2),
    # aucun gate melee/normal, applique en prediction). Valide bit-exact 1357 s18 (#57d).
    "MartialKatah_DmgBonus": MartialKatahDmgBonusEffect,
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
    # Camouflage (trait 1037, ex. admecRuststalker) : -1 coup RANGED reçu (-2 si dist>2, -3 sur tuile
    # DryBush << Tall Grass >>), plancher 1 (@181107180, jumeau LightCover/Parry ; slot 0x23 OwnerIsTarget
    # & IsRangedAttack ; consts camouflageHitReduction_1/2/3=1/2/3). #59.
    "Camouflage_HitReduction": CamouflageHitReductionEffect,
    "MasterAnnihilator_extraHit": MasterAnnihilatorAdditionalHitEffect,  # debuff Vitruvius : +1 coup reçu (non-Psychic)
    "BigTarget_AdjacentEffect": BigTargetAdjacentEffect,  # aura : -1 coup ranged aux alliés ring-1 du porteur
    # AstartesBanner (porte-banniere Astartes ex. templAncient) : AURA +extraHits(=1) coup MELEE aux ALLIES
    # dans le rayon 2 du porteur (l'effet vit sur LE PORTEUR, comme BigTarget ; @180f323b0 ForAddition
    # OwnerIsCaster&IsMeleeAttack ConfigVar 0xd, selector SurroundingFriends range ConfigConst 0x16=2). #107.
    "AstartesBanner_ExtraHit": AstartesBannerExtraHitEffect,
    "ShadowInTheWarp_LessDmg_Effect": ShadowInTheWarpLessDmgEffect,  # aura : -25% degat PSYCHIQUE aux ennemis a portee
    # DaughterOfTheAbyss (Atlacoya custoAtlacoya, passif range 2) — 3 effets sur le PORTEUR (#184) :
    # Friendly = -dmgReductionPct% (33 @L50) au degat PSYCHIQUE recu par les AMIS rayon 2 (aura-defense,
    # boucle state-wide @181002c30 ; racine du ~1.49x bloodMephiston seed 2024) ; Owner = -dmgReduction
    # plat Psychic sur Atlacoya elle-meme ; ExtraDamagePct = +extraDmgPct% au degat recu par les Psykers
    # ENNEMIS rayon 2.
    "DaughterOfTheAbyss_FriendlyDmgReductionPct": DaughterOfTheAbyssFriendlyDmgReductionPctEffect,
    "DaughterOfTheAbyss_OwnerDmgReduction": DaughterOfTheAbyssOwnerDmgReductionEffect,
    "DaughterOfTheAbyss_ExtraDamagePct": DaughterOfTheAbyssExtraDamagePctEffect,
    # BlessingsOfKhorne (trait 1046, faction World Eaters — Azkor/Kharn/Wrask/Macer + bosses LHE) :
    # -8%xN degat PSYCHIQUE recu par le porteur / +3%xN TOUT degat sortant, N=min(melee-defeats
    # global, 8) seedé par Scene._seed_battle_counters depuis decisionView.units (#185).
    # EffectType 0x4ee=1262, nom capte = effect-type-names.ts:385.
    "BlessingsOfKhorne": BlessingsOfKhorneModifiersEffect,
    # BeaconOfRage (passive 1236 d'Azkor worldEightbound) : +extraDmg[ablvl passif] x rage FLAT
    # additif a TOUTES les attaques du porteur (@180f33130 ForAddition OwnerIsCaster seul) ; rage =
    # decisionView.effects[].level = min(TotalTimesAttacked, nrOfAttacks=8), cappe a l'ecriture par
    # le natif (@180e13230). EffectType 0x512=1298 (#189). La variante 0x513=1299 FriendlyExtraDamage
    # = aura HOSTEE sur Azkor (@180f33370 PercentageOf(Multiply(ConfigVar extraDmg, EffectLevel), 50)) :
    # 50% du bonus rage FLAT aux attaques MELEE des amis Chaos adjacents, si Azkor a >=1 kill. Canal aura
    # cote source create_aura_attack_damage_bonus_for_ally -> mods.additive de l'ami attaquant (#191).
    "BeaconOfRage_ExtraDamage": BeaconOfRageExtraDamageEffect,
    "BeaconOfRage_FriendlyExtraDamage": BeaconOfRageFriendlyExtraDamageEffect,
    # OverwhelmingWrath (active 1141 d'Azkor) : -dmgReductionPct% (64 des L36) au degat RANGED recu
    # par le porteur jusqu'au debut de son tour suivant (transient rem=1 ; @180f5d6e0 ForPercentDecrease
    # OwnerIsTarget & IsRangedAttack, ConfigVar 0x46). EffectType 0x515=1301 (#190). Le jumeau
    # 0x514=1300 PendingAttack (attaque differee 2x Eviscerate) = hors canal modifier, tache dediee.
    "OverwhelmingWrath_RangeDmgReduction": OverwhelmingWrathRangeDmgReductionEffect,
    # DecoysAndMisdirection (Genestealer Cults ex. genesPrimus/genesMagus/genesKelermorph) : +extraDmg
    # FLAT additif a TOUTES les attaques de l'ami buffe (pose quand un decoy est spawn a cote / qu'un ami
    # marche sur un decoy). Gate OwnerIsCaster SEUL (@180f3e340 -> applique en prediction+combat, cf.
    # Neuroparasite). extraDmg[L65]=582 rarity-scale x mult. EffectType capte 1379. #134 (spawn+retaliation
    # Blast NON encore portes -- seul l'effet ExtraDamage l'est ici). Nom capte = effect-type-names.ts:502.
    "DecoysAndMisdirection_ExtraDamage": DecoysAndMisdirectionExtraDamageEffect,
    # LordOfTempests (passif Njal spaceStormcaller, EffectType 0x4d4=1236) : +extraDmg[ablvl]xmult FLAT
    # PAR HEX GLACE du ring-1 de la position d'attaque (@180f569a0 ForAddition(OwnerIsCaster,
    # Multiply(ConfigVar 8=extraDmg, Count(SurroundingTiles(0,1) with Ice)))) — magnitude POSITION-
    # DEPENDANTE re-countee par tuile candidate via att_ctx. VALIDE BIT-EXACT 31337 s18 (#29).
    "LordOfTempests_ExtraDamage": LordOfTempestsExtraDamageEffect,
    # HypersensoryAbilities (passif Judh genesJudh) : HP-floor 50% du HP courant a la 1re attaque du tour
    # ennemi (effet 0x564=1380). Snapshot floor via ApplyInternal @180f445a0 / clear via RevertInternal
    # @180f44820 ; ActiveCondition IsEnemyTurn & Not(attacked>=1). Apply/Revert impératifs = op runner
    # `MinimalHealthEffectOperation` ; le clamp vit dans `HealthComponent.reduce`. Nom capte = 1380 enum. G6a.
    "HypersensoryAbilities_MinimalHealth": HypersensoryMinimalHealthEffect,
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
    # `HypersensoryAbilitiesAbility.CreateBehaviour` @180f87870 : `AddEffect(0x564=1380, owner, owner)` -> le
    # HP-floor est posé sur le PORTEUR à l'init de l'ability passive (owner-effect self, aucun sélecteur). G6a.
    "HypersensoryAbilities": ["HypersensoryAbilities_MinimalHealth"],
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
