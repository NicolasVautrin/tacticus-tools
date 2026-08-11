"""`EffectFactory` — instancie la bonne sous-classe `BaseEffect` depuis un effet capté (registre
nom d'EffectType → classe). Mirror du dispatch natif « EffectType → classe d'effet ».

Effet non porté → `BaseEffect` (no-op) = dégradation fidèle (présent mais sans contribution, cf. §17.4
« présent ≠ appliqué »). Registre extensible (`EffectFactory.register`) au fil du portage du roster.
"""
from __future__ import annotations

from collections.abc import Mapping

from .base import BaseEffect
from .loki.ability_modifications import ListenUpMaggotsEffect
from .loki.amulet_of_the_voidwyrm import AmuletOfTheVoidwyrmCritDamageReductionEffect
from .loki.ramshackle import RamshackleDmgReductionEffect
from .loki.supa_cybork_body import SupaCyborkBodyCritDmgReductionEffect
from .loki.blood_chalice import BloodChaliceExtraPiercingEffect, BloodChaliceHealOnAttackEffect
from .loki.champion_of_the_feast import ChampionOfTheFeastReduceArmorEffect
from .loki.counter_attack import WireweaveNetCounterAttackEffect
from .loki.crit_aura import PathOfCommandExtraCritEffect
from .loki.cursed_plague_bell import CursedPlagueBellExtraMoveEffect
from .loki.custodes import MomentShackleExtraBlockChanceEffect, MomentShackleExtraBlockDamageEffect
from .loki.damage_reduction import (
    CamoCloakDmgReductionEffect, ChronometronExtraDamageEffect,
    DaughterOfTheAbyssFriendlyDmgReductionPctEffect, DaughterOfTheAbyssOwnerDmgReductionEffect,
    ExemplarOfHateTargetEffect, FightingRetreatDmgReductionEffect,
    FireAndRepositionReduceDmgEffect, GuardianOrganismDamageReductionEffect,
    HeraldOfTheApocalypseExtraDamageEffect,
    LightOfSanguiniusDmgReductionEffect, MarkerlightEffect,
    MartialKatahDmgReductionEffect, NeuroparasiteEffect, NightshroudDmgReductionEffect,
    OverwhelmingWrathRangeDmgReductionEffect, PrioritisedEfficiencyDmgReductionEffect,
    PsychicFortressDmgReductionEffect, SereneUnifierSenseOfStoneEffect,
    ShadowInTheWarpLessDmgEffect, SuperchargeExtraPiercingEffect, TerminatorArmourReduceDmgEffect,
    TerrifyingExtraDefenseEffect, VexillaMagnificaDmgReductionEffect
)
from .loki.daemonic_patrons import (
    DaemonicPatronsDmgReductionEffect, DaemonicPatronsExtraDamageEffect
)
from .loki.dark_angels_passives import (
    FearedInterrogatorOwnerEffect, FearedInterrogatorTargetEffect, LionHelmExtraBlockChanceEffect,
    LionHelmExtraBlockDamageEffect, LionHelmExtraDmgEffect
)
from .loki.darkangels import HailstrikeExtraPierceEffect
from .loki.lions_wrath import TheLionsWrathExtraCritChanceEffect
from .loki.martial_exemplar import MartialExemplarExtraCritChanceEffect
from .loki.destroy_the_witch import (
    DestroyTheWitchExtraDamageEffect, DestroyTheWitchExtraMoveEffect
)
from .loki.empyric_ambush import EmpyricAmbushEffect
from .loki.euphoric_strikes import EuphoricStrikesExtraCritEffect
from .loki.extra_damage import (
    AvalancheOfMuscleExtraDamageEffect, BeaconOfRageExtraDamageEffect, BeastSlayerExtraDmgEffect,
    CondemnorStakeExtraDmgEffect, CrushingStrikeEffect, DecoysAndMisdirectionExtraDamageEffect,
    FeederTendrilsExtraDamageEffect, FuelledByFuryExtraDamageEffect, HeavyGravCannonEffect,
    HeavyWeaponExtraDmgEffect, LordOfTempestsExtraDamageEffect, MartialKatahDmgBonusEffect,
    MeltaExtraDmgEffect,
    ModifiedExoarmourExtraDmgEffect, PrimarchOfTheFirstLegionExtraDamageEffect,
    PrioritisedEfficiencyExtraDmgEffect, RangedSpecialistEffect, RapidAssaultExtraDamageEffect,
    SmashaEadExtraDamageEffect, SpecialIssueCombiMeltaExtraDmgEffect,
    TerrifyingCrescendoExtraDmgEffect
)
from .loki.extra_damage_aura import (
    BeaconOfRageFriendlyExtraDamageEffect, DaughterOfTheAbyssExtraDamagePctEffect,
    DefenderOfTheGreaterGoodExtraDmgDroneEffect, DefenderOfTheGreaterGoodExtraDmgEffect,
    DoomExtraDmgEffect, LordOfTheHostExtraDamageEffect, PathOfCommandExtraDmgEffect,
    PsychicStalkExtraAttackDamageEffect, PsychicStalkFriendlyChaosExtraDamageEffect,
    PsychicStalkVisualEffect, RitesOfBattleExtraDmgEffect, SpotterReworkedExtraDamageEffect,
    SpotterReworkedHeavyWeaponEffect
)
from .loki.hits import (
    AnvilShieldAdditionalBlockEffect, AnvilShieldBlockChanceBelowHealthCapEffect,
    AnvilShieldFrozenAttackerAdvantageEffect, AstartesBannerExtraHitEffect,
    BeastSlayerExtraBlockEffect, BigTargetAdjacentEffect, CamouflageHitReductionEffect,
    CordClawAdditionalHitsEffect, CyclicIonBlasterAdditionalHitsEffect, DaemonExtraBlockEffect,
    DefenderOfTheGreaterGoodExtraHitsDroneEffect, DefenderOfTheGreaterGoodExtraHitsEffect,
    DiminutiveHitReductionEffect, ExemplarOfTheKauyonAdditionalHitsEffect,
    ExplosiveMaladiesExtraMeleeAttackEffect, ExplosiveMaladiesExtraRangedAttackEffect,
    FearOfTheUnseenExtraDamageEffect, FightingRetreatHitReductionEffect,
    FleshmetalGunsFocusedMaliceEffect, FleshmetalGunsRuinousSalvoEffect,
    FleshmetalGunsWarpHailEffect, FoulInfusionExtraHitsEffect, InfernalPactsAdditionalHitsEffect,
    KanOpenerEffect, LegendaryCommanderExtraHitsEffect, LetTheGalaxyBurnEffect, LightCoverEffect,
    MasterAnnihilatorAdditionalHitEffect, ParryEffect, PowerTripFullHealthEffect,
    PowerTripIgnoreArmorEffect, PsychicFortressExtraBlockEffect, SagaOfTheWarriorBornOwnerEffect,
    ShroudPsalmEffect, SorcerousFacadeAdditionalHitsEffect,
    SpecialIssueCombiMeltaAdditionalHitsEffect, SquigHoundAdditionalHitsEffect,
    Swarm_HitReductionEffect, UnstoppableFerocityOwnerEffect, VoltagheistFieldExtraHitEffect
)
from .loki.imperative import ConquerorImperativeEffect, ProtectorImperativeEffect
from .loki.inescapable_accuracy import (
    InescapableAccuracyExtraCritChanceEffect, InescapableAccuracyExtraCritDamageEffect,
    InescapableAccuracyOverrideHitsEffect
)
from .loki.holy_duel import (
    HolyDuelDmgReductionEffect, HolyDuelExtraDmgEffect, HolyDuelTauntEffect
)
from .loki.martial_inspiration import MartialInspirationExtraDamageEffect
from .loki.martial_superiority import MartialSuperiorityVisualEffect
from .loki.mind_control import (
    MindControlIncomingDamageBonusEffect, MindControlOutgoingDamageReductionEffect,
    MindControlTaunterEffect
)
from .loki.my_will_be_done_overlord import MyWillBeDoneOverlordExtraDamageEffect
from .loki.titanhammer_squad import TitanhammerSquadExtraBlockDamageEffect
from .loki.possession import AttemptedPossessionPossessedEffect
from .loki.reality_unbound import (
    RealityUnboundExtraMaxDamageEffect, RealityUnboundMovementEffect, RealityUnboundRangeEffect
)
from .loki.reinforced_hive_node import (
    ReinforcedHiveNodeExtraArmorEffect, ReinforcedHiveNodeExtraBlockEffect
)
from .loki.relentless_march import RelentlessMarchExtraMoveEffect
from .loki.relic_bolt_pistol import (
    RelicBoltPistolExtraCritDamageEffect, RelicBoltPistolExtraPierceEffect
)
from .loki.rites_of_morkai import RitesOfMorkaiExtraDamageEffect
from .loki.serene_unifier import SereneUnifierStormOfFireEffect
from .loki.shock_assault import ShockAssaultBuffEffect
from .loki.status import (
    ActOfFaithBuffEffect, BlackRageAutomaticUnitEffect, BlackRageExtraDamageEffect,
    BlackRageExtraMoveEffect, BlessingsOfKhorneModifiersEffect,
    ContagionsOfNurgleArmorReductionEffect, ContaminatedEffect, ContaminatedUnitEffect,
    DespoiledGroundEffect, DespoiledGroundExtraDamagePctEffect,
    HammerOfWrathConditionalDamageEffect, HypersensoryMinimalHealthEffect, MV71InitialDmgEffect,
    MV71ResetInitialDmgEffect, MasterOfTheTutelariesEffect, PinnedEffect,
    StandVigilExtraArmorEffect, StunnedDamageModifierEffect, StunnedEffect, TauntedEffect,
    ThrillSeekersEffect, TunnelingHorrorPendingSummonEffect, WaaaghExtraDamageEffect,
    WaaaghExtraHitsEffect, WaaaghExtraMovementEffect
)
from .loki.structural_analyser import StructuralAnalyserVisualEffect
from .loki.unbreakable_duty import (
    UnbreakableDutyDamageEffect, UnbreakableDutyDamageReductionEffect, UnbreakableDutyHealthEffect
)
from .loki.until_of_end_turn import UntilOfEndTurnEffect
from .loki.visions_of_heresy import (
    VisionsOfHeresyExtraPierceMeleeEffect, VisionsOfHeresyExtraPierceRangedEffect
)
from .loki.votann import (
    AncestralFortuneExtraBlockChanceEffect, AncestralFortuneExtraCritChanceEffect,
    AugmentedAssaultReduceArmorEffect, GravitonRifleExtraPierceEffect, PurgeResponseEffect
)
from .loki.wall_of_mirrors import WallOfMirrorsEffect
from .loki.war_howl import WarHowlExtraDamageUnstoppableEffect

# Registre nom d'EffectType (`decisionView.effects[].name`) → classe d'effet. À ÉTENDRE au roster.
EFFECT_CLASSES: dict[str, type[BaseEffect]] = {
    # LionHelm (passif darkaAzrael, TriggeredAbilityType 1163) — 3 effets AURA poses sur AZRAEL.
    # 1193 = +extraDmg aux attaques d'OVERWATCH des allies a <=2 hexes (canal aura-degat) ;
    # 1214/1232 = stat-mods PROJETES BlockDamage/BlockChance (canal aura-statmod, cf.
    # `runner/operations/aura_stat_mods.py`), 1232 restreint aux allies de FACTION DarkAngels.
    "LionHelm_ExtraDmg": LionHelmExtraDmgEffect,
    "LionHelm_ExtraBlockDamage": LionHelmExtraBlockDamageEffect,
    "LionHelm_ExtraBlockChance": LionHelmExtraBlockChanceEffect,
    # FearedInterrogator (passif darkaAsmodai, TriggeredAbilityType 1235) — 2 effets sur ASMODAI.
    # 1295 = MARQUEUR (selecteur des ennemis eligibles, jamais materialise sur eux) ; 1294 = les deux
    # bonus (+extraDmg, +extraHits si la cible est de grande-alliance Chaos).
    "FearedInterrogator_Owner": FearedInterrogatorOwnerEffect,
    "FearedInterrogator_Target": FearedInterrogatorTargetEffect,
    # Melta_ExtraDmg (0x511=1297) -- le +50 % vs `Vehicle` du profil de degat `Melta`, pose au
    # `MatchInit` par l'ability GLOBALE `OnMeltaDamageAbility` (1211) sur UNE TUILE arbitraire.
    # Inscrit ICI parce que le canal live le remonte comme n'importe quel effet de tuile
    # (`readEffectsByTile` -> `load_state(tiles=)`), ET dans `MATCH_WIDE_EFFECTS`
    # (`effects/__init__.py`) parce que ce canal-la est OPT-IN : sans la seconde inscription le
    # bonus serait inerte dans tous les chemins qui ne passent pas `tiles=` (#488-r1).
    "Melta_ExtraDmg": MeltaExtraDmgEffect,
    "RapidAssault_ExtraDamage": RapidAssaultExtraDamageEffect,
    "SquigHound_AdditionalHits": SquigHoundAdditionalHitsEffect,   # #179 : 2 coups hetero [minDmg,maxDmg] Physical
    # SpecialIssueCombiMelta (`darkaSternguard` « Ramus », npc `darkaBossSternguardLHE` ; ability
    # TriggeredAbilityType 1545) -- FACE COMBAT, #419-r1-tr11-r3. Les DEUX effets sont poses ensemble
    # par `SpecialIssueCombiMelta_InitAbility$$CreateBehaviour` (`AddEffect(0x61b) & AddEffect(0x61c)`
    # sur `Owner@DSLSelectors+0x30`) et se distinguent par leur PORTEE EXACTE, lue au `.ctor` de
    # `DSLFormulas` (`+0x20 = Const(1)`, `+0x28 = Const(2)`) et non au call-site :
    #   1563 = un GROUPE du canal #179 (`nrOfHits` coups [minDmg,maxDmg] Bolter) a d == **2** ;
    #   1564 = un ForAddition `extraDmg` sur les attaques NORMALES a d == **1**.
    # `IsAtRange` compare par EGALITE (cf. `effects/base.py::is_at_range`) : ce ne sont PAS des
    # portees « jusqu'a ». La 3e portee du kit (`Pinned` a d == 3) vit sur l'ability
    # `SpecialIssueCombiMelta_AddEffectAbility`, pas sur un effet -- residu `#419-r1-tr11-r4`.
    "SpecialIssueCombiMelta_AdditionalHits": SpecialIssueCombiMeltaAdditionalHitsEffect,
    "SpecialIssueCombiMelta_ExtraDmg": SpecialIssueCombiMeltaExtraDmgEffect,
    # SorcerousFacade (Yazaghor thousTzaangor, effet 0x4b4=1204 pose par le cast de 1100 sur le CASTER
    # ET l'allie Psyker vise, TurnsFromRounds(1)) : +nrOfHits=1 coup hetero [minDmg,maxDmg] Psychic a
    # TOUTES leurs attaques (trigger = `get_OwnerIsCaster` SEUL). Corps natif IDENTIQUE instruction
    # pour instruction a `IdunBattle.Entities.Effects.Loki.SquigHound_AdditionalHitsEffect$$
    # CreateAdditionalHits` -> meme canal #179, forme PREDEFINED [min,max]. #287 (face COMBAT de 1100).
    "SorcerousFacade_AdditionalHits": SorcerousFacadeAdditionalHitsEffect,
    # CordClaw (Exitor-Rho, effet 0x4e2=1250) : apres cast 1122, +nrOfHits_2=2 coups [minDmg_2,maxDmg_2]
    # DirectDamage a toutes ses attaques (IdunBattle.Entities.Effects.Loki.CordClaw_AdditionalHitsEffect$$CreateAdditionalHits, canal #179). #57c.
    "CordClaw_AdditionHits": CordClawAdditionalHitsEffect,
    # FearOfTheUnseen (Deathleaper `tyranDeathleaper`, effet 0x4d7=1239 pose sur LUI-MEME par le cast de
    # 1115) : +nrOfHits=3 coups PREDEFINED [minDmg,maxDmg] DirectDamage a ses attaques MELEE
    # (`IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_ExtraDamageEffect$$CreateAdditionalHits`, trigger
    # OwnerIsCaster & IsMeleeAttack, canal #179). Le nom capte est le membre d'enum `EffectType`.
    "FearOfTheUnseen_ExtraDamage": FearOfTheUnseenExtraDamageEffect,
    # FoulInfusion (Pestillian, effet 0x432=1074 sur CHAQUE unite Chaos dans l'aura au cast) :
    # +nrOfHits=1 coup Toxic de ConfigVar(dmg)[state du cast] aux attaques normales (IdunBattle.Entities.Effects.Loki.FoulInfusion_ExtraHitsEffect$$CreateAdditionalHits,
    # canal #179 GLOBAL : trigger IsMeleeAttack&OwnerIsCaster indecidable en display -> TRUE,
    # s'applique a TOUT attaquant en prediction — mesure 2468 s14). #57c-C.
    "FoulInfusion_ExtraHits": FoulInfusionExtraHitsEffect,
    # CyclicIonBlaster (Tau, triggered 1133, effet 0x47c=1148) : +nrOfHits=3 coups Particle de
    # minDmg[state] (+extraDmg si cible Markerlight/Mechanical) a TOUTES les attaques du porteur
    # (IdunBattleLogic.Entities.Abilities.Triggered.Loki.CyclicIonBlaster_AdditionalHitsEffect$$CreateAdditionalHits, canal #179 forme "amount" : display n'evalue que le noeud MIN, spread pipeline).
    # Valide 54321 s19 (#57e).
    "CyclicIonBlaster_AdditionalHits": CyclicIonBlasterAdditionalHitsEffect,
    # ExemplarOfTheKauyon (`tauShadowsun`, effet 0x49d=1181 pose sur ELLE-MEME par le cast de 1087,
    # le temps de l'attaque normale que l'ability declenche puis RETIRE) : +nrOfHits=2 coups Blast de
    # `ConfigVar(0xb = dmg)` (`...ExemplarOfTheKauyon_AdditionalHitsEffectEffect$$CreateAdditionalHits`
    # -> `EffectAdditionalHits$$Create`, canal #179, trigger `get_OwnerIsCaster` SEUL, param_8 = 0 donc
    # cellule DEGENEREE). ⚠ CANAL DIFFERENT de `1183 DefenderOfTheGreaterGood_ExtraHits` (#372), qui
    # partage le porteur mais passe par `CreateEffectHitsBonusForAttack` (coups d'ARME). #366-r1 G3.
    "ExemplarOfTheKauyon_AdditionalHits": ExemplarOfTheKauyonAdditionalHitsEffect,
    # FleshmetalGuns (Volk blackObliterator, passif 0x429=1065) : effet CYCLIQUE au debut de son tour
    # (behaviour IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour, UnitTurnsStarted % 3) -> +nrOfHits{,_2,_3}=2 coups PREDEFINED
    # [minDmg,maxDmg]{,_2,_3} Melta/Flame/HeavyRound aux attaques RANGED du porteur
    # (IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits, trigger OwnerIsCaster & IsRangedAttack, canal #179). #65 (decouvert probe #62).
    "FleshmetalGunsFocusedMalice": FleshmetalGunsFocusedMaliceEffect,
    "FleshmetalGunsRuinousSalvo": FleshmetalGunsRuinousSalvoEffect,
    "FleshmetalGunsWarpHail": FleshmetalGunsWarpHailEffect,
    # Swarm (trait, effet 0x3fd=1021 self) : EXTRA_HITS = -min(nrOfMembers-1, membres morts) —
    # AddOrUpdate par SwarmAbility IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour a chaque evenement PV du porteur. Amount dependant de
    # l'etat PV -> lie post-materialisation (bind_group_state, cf. unit_context.from_snapshot). #60.
    "Swarm_HitReduction": Swarm_HitReductionEffect,
    # ExplosiveMaladies (Pestillian, effets-AURA sur le PORTEUR) : +nrOfHits=1 coup Blast de
    # extraDmg[state] aux attaques normales des amis ADJACENTS (ranged: tous IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateAdditionalHits ;
    # melee: Chaos IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraMeleeAttackEffect$$CreateAdditionalHits) — adjacence re-evaluee a la tuile candidate. #57c-C bit-exact.
    "ExplosiveMaladies_ExtraRangedAttack": ExplosiveMaladiesExtraRangedAttackEffect,
    "ExplosiveMaladies_ExtraMeleeAttack": ExplosiveMaladiesExtraMeleeAttackEffect,
    # InfernalPacts (Abraxas thousInfernalMaster, effet-AURA 0x4ae=1198 sur le PORTEUR ; #202-B) :
    # +nrOfHits=1 coup PREDEFINED [minDmg,maxDmg] Psychic aux attaques des amis CHAOS adjacents
    # (ranged tous @ trigger IsRangedAttack ; melee AUSSI pour les Daemons, disjunct HasTrait(0x3fb)).
    # IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$CreateAdditionalHits/IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$CreateTargetSelector/IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$GetRefreshTriggers — adjacence re-evaluee a la tuile candidate (refresh PreAttack).
    "InfernalPacts_AdditionalHits": InfernalPactsAdditionalHitsEffect,
    # LordOfTheHost (Dante, effet 0x562=1378 sur le PORTEUR) : aura +extraDmg[ablvl]xmult additif
    # pre-percage aux attaques MELEE des amis RapidAssault/Flying rayon 2 (IdunBattle.Entities.Effects.Loki.LordOfTheHost_ExtraDamageEffect$$CreateEffectDamageBonusForAttack ForAddition,
    # selector IdunBattle.Entities.Effects.Loki.LordOfTheHost_ExtraDamageEffect$$CreateTargetSelector). Re-evaluee par tuile candidate. #57c.
    "LordOfTheHost_ExtraDamage": LordOfTheHostExtraDamageEffect,
    # Doom (Eldryon, effet 0x45a=1114 sur le PORTEUR) : les ennemis a EXACTEMENT 2 hexes du porteur
    # prennent +extraDmg[ablvl]xmult des attaques normales des amis du porteur (extraDmg_2 Aeldari,
    # toutes attaques) (IdunBattle.Entities.Effects.Loki.Doom_extraDmgEffect$$CreateEffectDamageBonusForAttack, selector IdunBattle.Entities.Effects.Loki.Doom_extraDmgEffect$$CreateTargetSelector ring-exact). #57c.
    "Doom_extraDmg": DoomExtraDmgEffect,
    # DestroyTheWitch (Helbrecht templHelbrecht, passif TriggeredAbilityType 0x443=1091 ; les DEUX
    # owner-effects de `DestroyTheWitchAbility$$CreateBehaviour`) :
    #  - 0x440=1088 ExtraMove   : StaticStatModifierEffect +extraMovement(=1) sur MOVEMENT ;
    #  - 0x441=1089 ExtraDamage : aura +extraDmg[ablvl]xmult additif sur les attaques MELEE de
    #    Helbrecht ET de ses allies HEX-ADJACENTS contre une cible **Psyker**
    #    (IdunBattle.Entities.Effects.Loki.DestroyTheWitch_ExtraDamageEffect$$CreateEffectDamageBonusForAttack
    #    + $$CreateTargetSelector = Unique(SurroundingFriends(Owner,1) + Owner)).
    # Les DEUX partagent la MEME `CreateActiveCondition` (corps natif FONDU par IL2CPP -- les deux
    # tables de symboles en nomment chacune un representant DIFFERENT ; ground truth live : les deux
    # effets apparaissent/disparaissent ENSEMBLE avec la presence d'un Psyker ENNEMI). Cf.
    # `loki/destroy_the_witch.py`.
    "DestroyTheWitch_ExtraMove": DestroyTheWitchExtraMoveEffect,
    "DestroyTheWitch_ExtraDamage": DestroyTheWitchExtraDamageEffect,
    # ReinforcedHiveNode (passif du SUMMON `tyranSmnWarrior`, invoque par `tyranWingedPrime` via
    # l'active `AlphaWarrior` 1112 ; TriggeredAbilityType 0x459 = 1113). `CreateBehaviour` pose DEUX
    # owner-effects PERMANENTS, en DEUX classes natives DISTINCTES (parents differents) :
    #  - 0x454=1108 ExtraArmor  : `StaticStatModifierEffect` — FixedArmor(16) += PercentageOf(
    #    StatAmount(Owner, FixedArmor, 3=Initial), Direct(extraArmorPct=100)) = +100 % de l'armure
    #    de BASE du porteur -> PORTE ici (`loki/reinforced_hive_node.py`) ;
    #  - 0x455=1109 ExtraBlock  : `StatOverrideEffect` — BlockChance(7) FORCEE a blockChance=100
    #    (`ApplyInternal` = `ChangeStat(Position(7, part 7 = OVERRIDE), Direct(<comp+0x14>))` ->
    #    `ValueOverride.SetOverride`, avec `isModifiable = 0` : ce n'est PAS un additif, et aucune
    #    modification par-source ne s'y ajoute). Canal `applied_stat_overrides`, pilote par le MEME
    #    driver `refresh_stat_modifier_effects` que l'additif (le refresh natif appelle les slots
    #    `IEffect+0xe`/`+0xf` sans connaitre la famille de l'effet).
    # Les DEUX partagent la MEME `CreateActiveCondition` (corps FONDU par IL2CPP, tranche sur la
    # table `g_MethodPointers` ordonnee par classe, PAS sur les noms de `functions.tsv`) :
    # `AmountIsOdd(Sum(RoundsStarted(Owner), Direct(1)))` = actif un round sur deux.
    "ReinforcedHiveNode_ExtraArmor": ReinforcedHiveNodeExtraArmorEffect,
    "ReinforcedHiveNode_ExtraBlock": ReinforcedHiveNodeExtraBlockEffect,
    # CursedPlagueBell (deathBlightbringer "Corrodius", active 1071) : effet 0x431=1073 pose pour UN
    # tour sur les amis CHAOS non-Stationary de l'aura ContagionsOfNurgle (vecteur
    # `CursedPlagueBellMovementAbility$$CreateBehaviour` = `AddEffect(0x431, ..., turns=1)`).
    # Classe d'effet NATIVE bespoke (contrairement a BlackRage/Waaagh, qui passent par la feuille
    # generique) : `CursedPlagueBell_ExtraMoveEffect$$ApplyInternal` emet lui-meme
    # `ChangeStat(Entity(target), Stat(1=Movement, 5=Modification), Modify, Direct(
    # GetNumberConstant(0xe = extraMovement)), Entity(effect), OnlyAlive)` -> canal eager
    # `applied_stat_mods` + `reverted_stats` (part 6 = ResetModification au revert). Cf.
    # `loki/cursed_plague_bell.py`.
    "CursedPlagueBell_ExtraMove": CursedPlagueBellExtraMoveEffect,
    # RelentlessMarch (necroWarden "Makhotep", passif `TriggeredAbilityType` 1004) : effet
    # 0x3f3=1011 pose pour UN tour sur les allies ADJACENTS non-`Stationary` (vecteur
    # `RelentlessMarchAbility$$CreateBehaviour` = `AddEffect(0x3f3, ..., UnitsWithoutTrait(
    # Friends(AdjacentUnits(Owner)), 0x418), turns = Nullable<int>(1))`, #328).
    # MEME forme OVERRIDE que CursedPlagueBell, mais le montant est le LITTERAL `Direct(1)` du
    # decompile -- l'ability n'a AUCUNE constante au gameconfig, donc transposer le
    # `GetNumberConstant(0xe = extraMovement)` du voisin aurait rendu 0 (effet inerte).
    # Cf. `loki/relentless_march.py` et `docs/rl/case-328-relentless-march.md`.
    "RelentlessMarch_Effect": RelentlessMarchExtraMoveEffect,
    # MyWillBeDoneOverlord (necroOverlord "Imotekh", passif `TriggeredAbilityType` 1556) : effet
    # 0x62d=1581 pose sur LUI-MEME par la branche ELSE de `MyWillBeDoneOverlordAbility$$CreateBehaviour`
    # (`AddDynamicStatModifierEffectToOwner(0x62d, stat = 0 Attack, Sum(TurnsFromRounds(1), Direct(1)))`)
    # quand aucun allie adjacent n'est eligible a l'attaque libre. AUCUNE classe d'effet native dediee :
    # instance GENERIQUE `DynamicStatModifierEffect(AbilityType(1556), 8 = extraDmg, isNegative = 0, 0)`
    # construite par la lambda `EffectsDatabase.<>c$$<InitializeEffects>b__14_574` -> magnitude lue par
    # `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` (meme mold que le lot Votann).
    # Residu nomme de #354-r1, ferme par #358 -- cf. `loki/my_will_be_done_overlord.py`.
    "MyWillBeDoneOverlord_ExtraDamage": MyWillBeDoneOverlordExtraDamageEffect,
    # TitanhammerSquad (astarLysander "Lysander", active 1231) : effet 0x624=1572 pose sur chaque
    # membre du groupe (Lysander + allies `TerminatorArmour` a portee `range`) dont la BlockChance
    # COURANTE est > 0, par le 3e volet de
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$ExecuteBehaviour`
    # (`AddDynamicStatModifierEffect(..., 0x624, stat 8 = BlockDamage, ...)`). AUCUNE classe d'effet
    # native dediee : instance GENERIQUE `DynamicStatModifierEffect(AbilityType(1231), 0x14 =
    # blockDmg, isNegative = 0, 0)` construite par la lambda
    # `EffectsDatabase.<>c$$<InitializeEffects>b__14_565` (l'`AbilityType` 0x4cf est LU AU
    # DESASSEMBLEUR) -> magnitude lue par `DynamicStatModifierEffect$$GetDynamicStatModificationAmount`,
    # meme mold que `MyWillBeDoneOverlord` ci-dessus. Cf. `loki/titanhammer_squad.py`.
    "TitanhammerSquad_ExtraBlockDamage": TitanhammerSquadExtraBlockDamageEffect,
    # SpotterReworked (Thaddeus astraOrdnance, 2 effets sur le PORTEUR IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpotterReworkedAbility$$CreateBehaviour) : aura
    # +extraDmg[ablvl]xmult additif pre-percage aux attaques RANGED des amis SANS HeavyWeapon
    # rayon 2 (IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateEffectDamageBonusForAttack) ; +extraDmg_2 aux amis AVEC HeavyWeapon, toutes attaques (IdunBattle.Entities.Effects.Loki.SpotterReworked_HeavyWeaponEffect$$CreateEffectDamageBonusForAttack).
    # Selectors IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateTargetSelector/IdunBattle.Entities.Effects.Loki.SpotterReworked_HeavyWeaponEffect$$CreateTargetSelector (UnitsWithRangedAttacks + fork trait 1001). #66.
    "SpotterReworked_ExtraDamage": SpotterReworkedExtraDamageEffect,
    "SpotterReworked_HeavyWeapon": SpotterReworkedHeavyWeaponEffect,
    # DefenderOfTheGreaterGood (tauShadowsun passif, TriggeredAbilityType 1155 ; effet 0x49e=1182 sur le
    # PORTEUR IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$CreateBehaviour branche NON-Summon) : aura +extraDmg[ablvl]xmult additif pre-percage aux attaques
    # RANGED non-Psychic des amis SOIT adjacents (toute faction) SOIT T'au dans range 2 (IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier, selector
    # IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector = (AdjacentFriends(1)-owner) + UnitsFromFaction(SurroundingFriends(2), Tau=9)). extraDmg[L65]=364.
    "DefenderOfTheGreaterGood_ExtraDmg": DefenderOfTheGreaterGoodExtraDmgEffect,
    # #372 — l'axe COUPS de la MEME ability (1183) et les TROIS jumeaux drone. UNE SEULE classe
    # native par axe, parametree : `..._Extra{Dmg,Hits}Effect$$.ctor(this, isDrone)` ecrit `isDrone`
    # a `this+0x480` ; la branche `isDrone` du selecteur ajoute `EntitiesIsNotTargetOfEffect(sel,
    # <effectType non-drone>)` = anti-double-comptage quand les deux auras se recouvrent.
    # COUPS = `..._ExtraHitsEffect$$CreateEffectHitsBonusForAttack` = `EffectBonus.ForAddition(
    # get_OwnerIsCaster & IsRangedAttack & !DamageProfileIs(0xd) & Maybe(chance), ConfigConst(0x2b =
    # extraHit))` avec `chance = Min(Direct(100), Multiply(ConfigConst(0x2a = chance),
    # UnitTurnsStarted(parent-ou-source)))` -> TERME de la formule de coups (canal
    # `aura_hits_bonus_for_attack`), PAS un groupe #179. RE : `docs/rl/case-372-dotgg-extra-hits.md`.
    "DefenderOfTheGreaterGood_ExtraHits": DefenderOfTheGreaterGoodExtraHitsEffect,
    "DefenderOfTheGreaterGood_ExtraDmgDrone": DefenderOfTheGreaterGoodExtraDmgDroneEffect,
    "DefenderOfTheGreaterGood_ExtraHitsDrone": DefenderOfTheGreaterGoodExtraHitsDroneEffect,
    # AURA +dégât (Attack) du SOURCE Calgar (RitesOfBattleAbility IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfBattleAbility$$CreateBehaviour) : 2 effets permanents
    # mutuellement exclusifs par trait Imperial (26). Noms captés EXACTS = ...Basic (1002) / ...Imperial
    # (1003) ; la classe lit le variant via self.name (endswith Imperial). Modélisée SOURCE-side
    # (create_aura_attack_bonus, ré-évaluée par candidat) — cf. #49 prediction.md point 18.
    "RitesOfBattle_ExtraDmgBasic": RitesOfBattleExtraDmgEffect,
    "RitesOfBattle_ExtraDmgImperial": RitesOfBattleExtraDmgEffect,
    # AURA +Attack (rayon 2) du SOURCE Loki (PathOfCommandAbility IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandAbility$$CreateBehaviour) : friends dist<=2,
    # +extraDmg (+extraDmg_2 si même grande-alliance que Loki). Nom capté = "PathOfCommand_ExtraDmg".
    "PathOfCommand_ExtraDmg": PathOfCommandExtraDmgEffect,
    # Volet CRIT du MEME behaviour (#373) : `AddDynamicStatModifierEffectToOwner(0x453 = 1107,
    # statType 0x9 = CritChance)`. Selecteur = SurroundingFriends(range 2) INTERSECTE
    # `UnitsWithStatBiggerThan(CritChance, Current, > 0, excludingEffect)` -> un allie a portee dont
    # la chance de crit est NULLE n'est PAS cible. Magnitude = extraCritChance[niveau SOURCE].
    # Canal = l'aura stat-mod PROJETEE (`runner/operations/aura_stat_mods.py`), comme LionHelm.
    "PathOfCommand_ExtraCrit": PathOfCommandExtraCritEffect,
    # Stat-mod +armure (FixedArmor) FLAT, SELF-buff extraArmor[level] (résidu 0 validable ; nom à confirmer).
    "StandVigil_ExtraArmor": StandVigilExtraArmorEffect,
    # Marqueur until-EoT 1197 (#202-C, Abraxas) : arme la triggered 1173 (Screamer sur attaque Psychic
    # vs ennemi) tant qu'il est actif — cf. EFFECT_TRIGGERS[1197] (triggers/dispatch.py).
    "MasterOfTheTutelaries": MasterOfTheTutelariesEffect,   # 1197 (0x4ad)
    # DoctrinaImperatives (Tan Gi'da) — toggle IdunBattleLogic.Entities.Abilities.Active.Loki.DoctrinaImperativesAbility$$ExecuteBehaviour : Protector = stat-mod +extraArmor sur FixedArmor(16)
    # (aura self+Mechanical-adjacents ; port SELF, portee = increment B) ; Conqueror = +extraDmg gate
    # HasNegativeModifier(cible FixedArmor<0) PRESENT-inerte (contribution +dmg = increment C).
    "ProtectorImperative": ProtectorImperativeEffect,   # 1247
    "ConquerorImperative": ConquerorImperativeEffect,   # 1248
    # BlackRage (bloodDeathCompany "Lucien", active 1163 IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour) — 3 self-buffs posés au cast (#217) :
    # ExtraMove (1342) = stat-mod +MOVEMENT (constante extraMovement=1, canal eager applied_stat_mods) ;
    # ExtraDamage (1343) = marqueur (+extraDmg-on-charge NON modelise, residu) ; AutomaticUnit (1344) =
    # marqueur (arme le triggered act-again BlackRage_ActivationAbility, NON modelise, residu). Tous remaining=0.
    "BlackRage_ExtraMove": BlackRageExtraMoveEffect,
    "BlackRage_ExtraDamage": BlackRageExtraDamageEffect,
    "BlackRage_AutomaticUnit": BlackRageAutomaticUnitEffect,
    # Waaagh (orksWarboss, active 1058 IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour) — 3 buffs poses par `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour`
    # sur caster + allies adjacents + TOUS les allies de faction Orks, duree 1 round (@dsl+0xc0) :
    # ExtraMovement (1099) = stat-mod +MOVEMENT (constante extraMovement=1, canal eager applied_stat_mods,
    # REQUIS par UnitMovementRangeWithBonus de l'etage MOVE) ; ExtraDamage (1100) = +extraDmg[L] PLAT par coup
    # (IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack, ForAddition
    # IsNormalAttack & IsMeleeAttack & OwnerIsCaster, ConfigVar 8) ; ExtraHits (1101) = +extraHit coup
    # (IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack, MEME condition,
    # ConfigConst 0x2b). NIVEAU = celui du POSEUR (AbilityStateReference -> scale_from_source) ;
    # multiplier de rarete RESOLU = 100 (mesure live +443 = extraDmg[L50] brut). #95.
    "Waaagh_ExtraMovement": WaaaghExtraMovementEffect,
    "Waaagh_ExtraDamage": WaaaghExtraDamageEffect,
    "Waaagh_ExtraHits": WaaaghExtraHitsEffect,
    # --- #112 DarkAngels lot 1 : les DEUX effets poses par les actives portees dans
    # `runner/abilities/darkangels.py`, tous deux a trigger `OwnerIsTarget` (ils vivent sur la VICTIME) :
    # ExemplarOfHate_Target (1293, pose par 1140) = additif `OwnerIsTarget & (IsMeleeAttack |
    # IsOverwatchAttack)` x `ConfigVar(8=extraDmg)` -> +degat PLAT recu en melee (moitie overwatch = residu).
    "ExemplarOfHate_Target": ExemplarOfHateTargetEffect,
    # Chronometron_ExtraDamage (1550, pose par l'active 1226 de `necroChronomancer` sur CHAQUE ennemi du
    # disque rayon 2) — MEME mold `OwnerIsTarget` : additif PLAT au degat RECU, gate sur l'ATTAQUANT
    # (`IsUnit` & `AreFriends(caster, EffectSource)`), magnitude
    # `If(IsMechanical(caster), extraDmg_2, extraDmg) x TimesEffectApplied` ; CONSOMME au 1er coup allie
    # (`CreateRemoveEffectTrigger` = `On(9) & …`, cf. `EFFECT_TRIGGERS[1550]`). Residu transverse R9.
    "Chronometron_ExtraDamage": ChronometronExtraDamageEffect,
    # HeraldOfTheApocalypse (1027, pose par l'active 1020 de `blackHaarken` sur la cible ET l'ennemi
    # DIRECTEMENT DERRIERE elle) — TROISIEME du meme mold `OwnerIsTarget` : `ForAddition(OwnerIsTarget &
    # IsUnit(caster), ConfigVar(8 = extraDmg))` -> +degat PLAT recu, SANS gate de nature de coup ni
    # d'equipe (contraste avec ses deux jumeaux ci-dessus) ; CONSOMME au 1er coup recu
    # (`CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget & IsUnit(caster)`, cf. `EFFECT_TRIGGERS[1027]`).
    # ⚠ Le NOM d'`EffectType` 1027 est `HeraldOfTheApocalypse` TOUT COURT (pas `..._ExtraDamage`) alors
    # que la classe native s'appelle `HeraldOfTheApocalypse_ExtraDamageEffect` -- le routage se fait par
    # le nom CAPTE, donc c'est celui-la qui est la cle. #BL-1020r.
    "HeraldOfTheApocalypse": HeraldOfTheApocalypseExtraDamageEffect,
    # Supercharge_ExtraPiercing (1208, pose par 1103) = `ForPiercing(DamageProfileIs(Plasma) &
    # OwnerIsTarget, ConfigVar(0x3f=extraPierceRatio))` -> +percage Plasma contre la victime (axe @0x20).
    "Supercharge_ExtraPiercing": SuperchargeExtraPiercingEffect,
    # BloodChalice_HealOnAttack (1368, pose par 1175) = `ForPiercing(get_OwnerIsCaster &
    # IsMeleeAttack, ConfigVar(0x3f=extraPierceRatio))` -> +percage sur les coups de MELEE du
    # PORTEUR (face INVERSE de Supercharge, qui gate sur OwnerIsTarget). Son SECOND volet, le soin
    # sur attaque melee, est un `EffectTrigger` (`operations/triggers/effect_triggers.py`). #576
    "BloodChalice_HealOnAttack": BloodChaliceHealOnAttackEffect,
    # BloodChalice_ExtraPiercing (1369, pose par 1175) = `AStatModifierEffect` sur
    # `StatType.ExtraPierceMelee` ; magnitude et stat viennent de la FEUILLE de pose, pas de la
    # classe. `CreateActiveCondition = IsCharging(Owner, Target)` NON portee (residu #576-r1). #576
    "BloodChalice_ExtraPiercing": BloodChaliceExtraPiercingEffect,
    "RangedSpecialist": RangedSpecialistEffect,  # +33% dégât RANGED (trait, actif si pas parti adjacent)
    # Markerlight (1122, posé sur la CIBLE par MV71SniperDroneSquadAttack IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour (e) /
    # StructuralAnalyser IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddMarkerlightAbility$$CreateBehaviour) : +MarkerlightDmgBonusPct% (=15, règle BC Effect) au dégât reçu des
    # attaques RANGED d'un attaquant T'AU (IdunBattle.Entities.Effects.Loki.MarkerlightEffect$$CreateDamageModifier ForPercentIncrease, gates OwnerIsTarget &
    # HasFaction(T'au) & IsRangedAttack). Retrait au heal/repair NON porté (flag). #61bis.
    "Markerlight": MarkerlightEffect,
    # MV71SniperDroneSquad (Sho'syl, #61bis) — paire posée sur le DRONE par l'ability 1076 :
    # InitialDmg (1132) = OVERRIDE des 4 stats du drone (ATTACK/CRIT_CHANCE/CRIT_DAMAGE/EXTRA_HITS) aux
    # valeurs CURRENT du PARENT (IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyInternal, part 7 SetOverride modifiable) ; ResetInitialDmg (1133) =
    # compagnon. Les DEUX retirés dès que le drone attaque (TargetTrigger On(10,1)&OwnerIsCaster).
    "MV71SniperDroneSquad_InitialDmg": MV71InitialDmgEffect,       # 1132
    "MV71SniperDroneSquad_ResetInitialDmg": MV71ResetInitialDmgEffect,   # 1133
    "HeavyWeapon_ExtraDmg": HeavyWeaponExtraDmgEffect,   # +25% dégât RANGED (trait HeavyWeapon→Overwatch)
    # CrushingStrike (trait Terminators, effet 0x4a2=1186, nom capté = 'CrushingStrike') : +50% dégât
    # MÊLÉE NORMALE si pas bougé (IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateDamageModifier ForPercentIncrease gated OwnerIsCaster & IsNormalAttack &
    # IsMeleeAttack ; ActiveCondition NOT HasMoved IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition). #98.
    "CrushingStrike": CrushingStrikeEffect,
    # SmashaEad (orksNob "Tanksmasha") : +extraDmg[level]×mult FLAT au dégât des attaques NORMALES
    # (effet posé quand le porteur a traversé ≥2 hexes ce tour ; IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageBonusForAttack ForAddition). #68.
    "SmashaEad": SmashaEadExtraDamageEffect,
    # FeederTendrils (Deathleaper, effet 0x4ad=1197) : jumeau SmashaEad + gate IsCharging (IdunBattle.Entities.Effects.Loki.FeederTendrils_ExtraDamageEffect$$CreateEffectDamageBonusForAttack
    # ForAddition). +extraDmg[level]xmult FLAT PRE-percage sur l'attaque NORMALE de CHARGE melee ;
    # multiplier GLOBAL (pas per-ability #68, car c'est l'attaque normale de l'unite). #176.
    "FeederTendrils_ExtraDamage": FeederTendrilsExtraDamageEffect,
    # PrimarchOfTheFirstLegion_ExtraDamage (effet 0x5f3 = 1523, #418) : pose sur l'allie Dark Angels
    # qui vient d'encaisser un coup a la place de `darkaBossLion`. `ForAddition(get_OwnerIsCaster,
    # ConfigVar(8 = extraDmg))` -- gate SEUL (pas d'`IsNormalAttack`, contraste SmashaEad /
    # FeederTendrils), donc actif AUSSI en prediction. Duree `TurnsFromRounds(nrOfRounds = 1)`.
    "PrimarchOfTheFirstLegion_ExtraDamage": PrimarchOfTheFirstLegionExtraDamageEffect,
    # AvalancheOfMuscle (astraBullgryn passif, EffectType 1025) : JUMEAU de FeederTendrils (IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack
    # ForAddition, IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$.ctor ABondEffect 0x404=1028) SAUF le noeud IsNormalAttack ABSENT ->
    # +extraDmg[level passif]xmult FLAT PRE-percage sur TOUTE attaque en CHARGE (OwnerIsCaster & IsCharging).
    # astraBullgryn melee-only ; multiplier GLOBAL a valider live (#68/#75). #220.
    "AvalancheOfMuscle_ExtraDamage": AvalancheOfMuscleExtraDamageEffect,
    # BeastSlayer (orksNob/Titus/Farsight/...) : +20% degat MELEE vs BigTarget/Vehicle (trait,
    # target-conditionnel IdunBattle.Entities.Effects.Loki.BeastSlayer_ExtraDmgEffect$$CreateDamageModifier ForPercentIncrease ; gate is_melee + target_traits). #68.
    "BeastSlayer_ExtraDmg": BeastSlayerExtraDmgEffect,
    # BeastSlayer cote DEFENSE : +10% chance de bloquer 100% du FixedArmor courant en degat (source de
    # block SUPPLEMENTAIRE, AddExtraBlockEffectToOwner IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour ; absente du scalaire GetStat(7/8)). #72.
    "BeastSlayer_ExtraBlock": BeastSlayerExtraBlockEffect,
    # Daemon (trait, effet 1034) : 25% chance de bloquer 50% de l'Attack COURANTE du defenseur —
    # pilote WillBeKill/WillBeOverkill de la prediction (scenario block list[0]@0x50). #54A.
    "Daemon_ExtraBlock": DaemonExtraBlockEffect,
    # SagaOfTheWarriorBorn (spaceBlackmane <<Ragnar>>, passif ; effet 0x4c7=1223) : +extraHits[level
    # passif] coups a TOUTE attaque du porteur EN CHARGE (IdunBattle.Entities.Effects.Loki.
    # SagaOfTheWarriorBorn_OwnerEffect$$CreateEffectHitsBonusForAttack = ForAddition(OwnerIsCaster &
    # IsCharging, ConfigVar(0x13 = extraHits)) -- DEUX noeuds, ni IsNormalAttack ni IsMeleeAttack).
    # Gate = foyer partage `is_charging_attack(att_ctx)`. MESURE live : 10 coups en charge vs 7 en
    # decalage adjacent. La face CRIT du meme effet reste NON portee (residu N14, case-ischarging-hits §7).
    "SagaOfTheWarriorBorn_Owner": SagaOfTheWarriorBornOwnerEffect,
    # SagaOfTheWarriorBorn_OtherSpaceWolves (0x4c8=1224) -- MEME CLASSE NATIVE que 1223, pas un calque :
    # les deux fabriques `<>c$$<InitializeEffects>b__14_{241,242}` d'`IdunBattle.Core.Services.
    # EffectsDatabase$$InitializeEffects` sont BIT-IDENTIQUES (meme slot `Il2CppClass*`, meme
    # `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$.ctor`, aucun argument
    # variable). Sur les 607 enregistrements, ce slot ne couvre QUE 1223 et 1224 -- identite tranchee
    # par le slot, jamais par le nom du ctor (51 noms couvrent plusieurs classes). Le port doit donc
    # pointer la MEME classe, sinon il duplique une classe que le natif n'a pas.
    # Le ctor est une CONSTANTE partagee : `AbilityOrEffect(TriggeredAbilityType.SagaOfTheWarriorBorn
    # = 0x49e = 1182)` -> les deux effets lisent la MEME config d'ability, donc les MEMES
    # `extraHits` (0x13) / `extraCritDmg` (0x42). Seul le PORTEUR change.
    # POSE (face separee, non portee ici -- cf. la docstring de la classe) :
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SagaOfTheWarriorBorn_KillAbility` pose 1224
    # sur les Space Wolves AMIS (hors Ragnar) quand Ragnar TUE un ennemi ayant le trait `Hero`.
    "SagaOfTheWarriorBorn_OtherSpaceWolves": SagaOfTheWarriorBornOwnerEffect,
    # UnstoppableFerocity (`blackSmnBloodletter`, summon d'Archimatos `blackPossession` ; passif du
    # summon, effet 0x408=1032) : +extraHit (constante = 1) coup a TOUTE attaque du porteur EN CHARGE
    # (`IdunBattle.Entities.Effects.Loki.UnstoppableFerocityOwnerEffect$$CreateEffectHitsBonusForAttack`
    # = ForAddition(get_OwnerIsCaster & IsCharging(caster@0x160, target@0x178),
    #   Direct(GetNumberConstant(config@+0x60, 0x2b = extraHit))) -- DEUX noeuds, ni IsNormalAttack ni
    # IsMeleeAttack : meme forme que 1223). Gate = foyer partage `is_charging_attack(att_ctx)`.
    # Le nom capte est le membre d'enum `EffectType` (`effect-type-names.ts:157`), suffixe `Effect`
    # COMPRIS -- il differe de la classe native seulement par le `_` (cf. 1192 juste au-dessus).
    # La 2e clause i2 (« +1 hit vs Psyker ») est l'effet SEPARE 0x4a8=1192, non porte.
    "UnstoppableFerocity_OwnerEffect": UnstoppableFerocityOwnerEffect,
    "PowerTrip_FullHealth": PowerTripFullHealthEffect,
    "PowerTrip_IgnoreArmor": PowerTripIgnoreArmorEffect,
    "Stunned": StunnedEffect,           # effet COMPOSITE (parent 1162 → enfants 1165/1166/1167)
    # Enfant 1167 du composite Stunned : -StunnedDmgReductionPct% (BC Effect, =50) au dégât SORTANT du
    # porteur stunné (IdunBattle.Entities.Effects.Loki.Stunned_DamageModifierEffect$$CreateEffectDamageMalusForDefense ForPercentDecrease trigger OwnerIsActor -> boucle ATTAQUANT du port).
    # VALIDÉ BIT-EXACT 777 s15 (×0.8 MK × 0.5 stun × 0.34 vexilla = 219-437 == natif). #29 lead 2.
    "Stunned_DamageModifier": StunnedDamageModifierEffect,
    # VexillaMagnifica (active 1183 custoVexilusPraetor, effet 1383) : -dmgReductionPct% (=66, non
    # rarity-scalé) à TOUT dégât reçu par le porteur (IdunBattle.Entities.Effects.Loki.VexillaMagnifica_DmgReductionEffect$$CreateDamageDefenseModifier ForPercentDecrease OwnerIsTarget SEUL,
    # aucun gate profil/mêlée). #29 lead 2.
    "VexillaMagnifica_DmgReduction": VexillaMagnificaDmgReductionEffect,
    # SereneUnifierSenseOfStone (0x491=1169, phase 1 du cycle du passif SereneUnifier 0x479=1145 de
    # `tauAunShi`) : -dmgReductionPct% (=50 des L50, non rarity-scale) a TOUT degat recu par le porteur
    # (`IdunBattle.Entities.Effects.Loki.SereneUnifierSenseOfStoneEffect$$CreateEffectDamageMalusForDefense`
    # ForPercentDecrease OwnerIsTarget SEUL, ConfigVar 0x46 -- jumeau structurel de VexillaMagnifica).
    # L'effet est MATERIALISE sur chaque beneficiaire par l'`AddEffect` du behaviour turn-start
    # (self + amis adjacents + amis T'au a <=2), donc capte dans SA liste `decisionView.effects` : canal
    # DEFENSEUR standard, PAS un canal aura. Sans cette entree l'effet retombait sur `BaseEffect` nu ->
    # tout banc embarquant Aun'Shi sur-predisait le degat d'un facteur 2,000 EXACT (#192).
    "SereneUnifierSenseOfStone": SereneUnifierSenseOfStoneEffect,
    # SereneUnifierStormOfFire (0x493=1171) — phase k=0 du MEME cycle `Modulo(PlayerTurnsStarted, 3)`,
    # mais par l'AUTRE canal : instance GENERIQUE `StaticStatModifierEffect` posee par la feuille
    # `AddStaticStatModifierEffect(units, 0x493, stat = 0 ATTACK, ConfigVar(8 = extraDmg),
    # TurnsFromRounds(1))`. Le declarer = l'attribution du seed pose sa `ValueModification` par-source,
    # donc son EXPIRATION (1 round) la RETIRE (#118) au lieu de coller le +extraDmg d'ATTACK a vie.
    # Cf. `entities/effects/loki/serene_unifier.py` et `docs/rl/case-371-g1-static-stat-modifier.md`.
    "SereneUnifierStormOfFire": SereneUnifierStormOfFireEffect,
    # UnbreakableDuty (active `templAncient`) — les DEUX self-buffs de
    # `UnbreakableDutyAbility$$ExecuteBehaviour`, poses par `AddStaticStatModifierEffectToOwner` avec
    # `turns = NULL` donc **PERMANENTS** : 0x4e3=1251 (stat 5 HEALTH, ConfigVar(0x1e = extraHp)) et
    # 0x4e8=1256 (stat 0 ATTACK, ConfigVar(8 = extraDmg)). Aucune expiration a fermer ici — ce que
    # l'inscription ferme est l'ATTRIBUTION du seed (residu opaque -> cle par-source, donc
    # confrontation « somme des magnitudes config == statDelta natif » et revert exact si un chemin de
    # retrait apparait). Cf. `entities/effects/loki/unbreakable_duty.py`.
    "UnbreakableDuty_Health": UnbreakableDutyHealthEffect,
    "UnbreakableDuty_Damage": UnbreakableDutyDamageEffect,
    # UnbreakableDuty (suite) -- l'AURA de reduction, posee INCONDITIONNELLEMENT par le cast
    # (`AddEffect(0x449 = 1097, AbilityStateReference, Owner@+0x30, TurnsFromRounds(1))`). Elle vit
    # sur le CASTER et se PROJETTE sur `Owner + SurroundingFriends(Owner, ConfigConst(range) = 2)`
    # via `UnbreakableDuty_DamageReductionEffect$$CreateTargetSelector` -> DEUX canaux
    # (`create_effect_damage_malus_for_defense` pour la patte SELF,
    # `create_aura_defense_damage_malus_for_ally` pour la patte projetee). Sans cette ligne, 1097
    # se materialisait en `BaseEffect` NU : present dans `decisionView.effects`, contribuant ZERO.
    "UnbreakableDuty_DamageReduction": UnbreakableDutyDamageReductionEffect,
    # ShockAssault_Buff (0x3e8 = 1000, #366-r1) -- le « +Damage for this attack » que le PASSIF
    # `ShockAssault` d'`ultraInceptorSgt` pose sur ses Inceptors avant de les faire attaquer
    # (`ShockAssaultAbility$$CreateBehaviour` = `AddStaticStatModifierEffect(<Inceptors amis
    # adjacents>, 0x3e8, stat = 0 ATTACK, Get(ConfigVar(8 = extraDmg)), turns = NULL, hidden)`).
    # Classe native DEDIEE (`...Loki.ShockAssaultBuffEffect : StaticStatModifierEffect`) -- identite
    # tranchee au slot `Il2CppClass*` de la fabrique `<>c$$<InitializeEffects>b__14_26`, dont c'est
    # l'UNIQUE xref : le ctor FONDU (Ghidra le nomme `SwarmHitReductionEffect$$.ctor`) ne fait donc
    # PAS une classe commune. Son seul membre propre est `$$CreateRemoveEffectTrigger` = `On(0xa =
    # AttackDamageAttack) & OwnerIsCaster`, porte cote runner
    # (`runner/operations/triggers/loki/shock_assault.py`) : sans lui le buff serait PERMANENT
    # (`turns = NULL`) la ou le natif le borne a l'attaque en cours.
    # Cf. `entities/effects/loki/shock_assault.py` et `docs/rl/case-366-r1-shock-assault-buff.md`.
    "ShockAssault_Buff": ShockAssaultBuffEffect,
    "ActOfFaith_Effect": ActOfFaithBuffEffect,  # buff crit empilable (1017) — stack seedé = cc/cd_delta 0
    # « Thrilled » (1434, trait ThrillSeekers) : StaticStatModifierEffect CRIT_CHANCE +extraCritChance,
    # a TIMER (TurnsFromRounds(nrOfRounds)). Le declarer ici = l'attribution du seed pose sa
    # `ValueModification` par-source, donc son expiration la RETIRE (#118) au lieu de la garder a vie.
    # Le nom capte est le membre d'enum `EffectType` (cf. `EFFECT_TYPE_NAMES[1434] = "ThrillSeekers"`),
    # identique a celui que passe la feuille `AddStaticStatModifierEffect` a la pose en combat.
    "ThrillSeekers": ThrillSeekersEffect,
    # RealityUnbound (passif `thousTzaangor`) — les TROIS `StaticStatModifierEffect` generiques du
    # passif, declares pour que l'attribution du seed pose leur `ValueModification` par-source (donc
    # que l'expiration la retire, #118) ; 1207 porte en plus `stacks_stat_mod_on_add` (cumul « for
    # each different enemy unit »). Cf. `entities/effects/loki/reality_unbound.py`.
    "RealityUnbound_Movement": RealityUnboundMovementEffect,          # 1205 : +1 MOVEMENT, 1 tour
    "RealityUnbound_Range": RealityUnboundRangeEffect,                # 1206 : +1 EXTRA_RANGE, 1 tour
    "RealityUnbound_ExtraMaxDamage": RealityUnboundExtraMaxDamageEffect,  # 1207 : +extraMaxDmg, EMPILABLE
    # Tyrant Guard (CrushingClaws) :
    "Taunted_OnlySpecificTargets": TauntedEffect,  # COMPOSITE 27 → enfants 25/26/1237 (bond cible↔tauntant)
    # HolyDuel (1050, templChampion « Brother Jaeger ») — `entities/effects/loki/holy_duel.py`.
    # 1091 est un COMPOSITE dont trois des quatre enfants vivent sur l'entité BONDÉE (le champion) :
    # les DEUX `Taunted` du duel sont symétriques.
    "HolyDuel_Taunt": HolyDuelTauntEffect,               # 0x443 = 1091 (composite + bond)
    "HolyDuel_ExtraDmg": HolyDuelExtraDmgEffect,         # 0x444 = 1092 (+extraDmg vs le duelliste)
    "HolyDuel_DmgReduction": HolyDuelDmgReductionEffect,  # 0x445 = 1093 (−dmgReduction du duelliste)
    "Pinned": PinnedEffect,             # 1065 (UI « Suppressed ») — stat-mod Movement (matérialisé seul)
    # ListenUpMaggots (0x426=1062, passif d'`astraSmnKell`) : SEULE source native de modification de
    # CONSTANTE d'ability (`AddUnitActiveAbilityModification` sur `Parent(Self)` = Creed). #95-RESTE2.
    "ListenUpMaggotsEffect": ListenUpMaggotsEffect,
    "Terrifying_ExtraDefense": TerrifyingExtraDefenseEffect,  # -30% dégât MÊLÉE reçu (defender, gated melee)
    "TerminatorArmour_ReduceDmg": TerminatorArmourReduceDmgEffect,  # -75% dégât reçu SAUF Psychic/DirectDamage (defender, gated profil)
    # GuardianOrganism (tanks Tyranides) : reduit le degat recu de min(dmgReductionPct%(25-33) x dmg,
    # dmgReduction_cap x mult) = PercentSubtractionCapped (dynamique+capee) ; aura self+adjacents. #89.
    "GuardianOrganism_DamageReduction": GuardianOrganismDamageReductionEffect,
    # Nightshroud (Sibyll Devine astraPrimarisPsy) : aura -dmgReduction Damage "from each hit" aux allies
    # ring-1 en debut de tour (defender, ForSubtraction IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier ; SANS gate) = additif defenseur @+0x10
    # PRE-percage (config 499 dilue par armure -> ~155 sante). #111.
    "Nightshroud_DmgReduction": NightshroudDmgReductionEffect,
    # MartialKatah (Custodes ex. custoTrajann/custoVexilusPraetor) : -20% degat des ATTAQUES NORMALES
    # recues (defender, gated IsNormalAttack ; IdunBattle.Entities.Effects.Loki.MartialKatah_DmgReductionEffect$$CreateDamageModifier ForPercentDecrease ConfigConst 0x72=
    # martialKatahDmgReductionPct). #105.
    "MartialKatah_DmgReduction": MartialKatahDmgReductionEffect,
    # MartialKatah face ATTAQUE (IdunBattle.Entities.Effects.Loki.MartialKatah_DmgBonusEffect$$CreateEffectDamageBonusForAttack) : +100% degat vs SUMMONS (HasTrait(target, Summon=2),
    # aucun gate melee/normal, applique en prediction). Valide bit-exact 1357 s18 (#57d).
    "MartialKatah_DmgBonus": MartialKatahDmgBonusEffect,
    # CondemnorStake (adeptCanoness passif, effet 1076) : JUMEAU de AvalancheOfMuscle (IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack ForAddition,
    # IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$.ctor source 0x42e=1070) SAUF gate IsCharging -> HasTrait(target, Psyker=0x3ea=1002). +extraDmg
    # [ablvl passif]xmult FLAT additif PRE-percage a TOUTE attaque du porteur (aucun gate melee/normal) vs cible
    # Psyker. i2 "+2183 Damage" = extraDmg[L65] (lu gameconfig, jamais hardcode). Precedent gate target-trait
    # BeastSlayer/MartialKatah/DaughterOfTheAbyss. #220.
    "CondemnorStake_ExtraDmg": CondemnorStakeExtraDmgEffect,
    # Neuroparasite (passif Neurothrope ; EffectType CAPTE = 1218 'Neuroparasite', name-route ; ctor 0x49f=1183
    # = AbilityOrEffect, distinct) : ADDITIF +extraDmg[nivSource]xniveau_parasite au degat PSYCHIQUE recu DE CE
    # Neurothrope (defender, ForAddition gated Psychic + AreEqual(source)). Magnitude+gating+PLACEMENT (scale
    # x%-list, avant-%list) VALIDES LIVE BIT-EXACT #86/#88 (2 separateurs RS on/off ; L1 port==natif 4392-5461).
    "Neuroparasite": NeuroparasiteEffect,
    # Debuffs FightingRetreat (Darkstrider) — posés sur les ENNEMIS adjacents, s'appliquent aux
    # ATTAQUES du porteur : -dmgReduction PLAT + -1 coup (plancher 1), 1 round (rem=2 capté).
    "FightingRetreatDmgReduction": FightingRetreatDmgReductionEffect,
    "FightingRetreatHitReduction": FightingRetreatHitReductionEffect,
    # MindControl (active 1164, `genesMagus`) -- les TROIS effets de son arbre, cf.
    # `entities/effects/loki/mind_control.py`. L'appariement id <-> classe est INVERSE de l'ordre
    # des ctors dans le binaire : il vient de l'enum `EffectType`, jamais de l'ordre des symboles.
    # 1349 : `ForAddition(get_OwnerIsCaster, Negative(ConfigVar 0x12 = dmgReduction))` = -582 PLAT
    #        sur les attaques du porteur (face ATTAQUANT, aucun gate).
    # 1350 : `ForPercentIncrease(get_OwnerIsTarget, ConfigVar 0xa = extraDmgPct)` = +20 % sur le
    #        degat RECU (canal defenseur, face NATIVE attaquant -- `DEFENSE_MALUS_NATIVE_FACE`).
    # 1367 : MARQUEUR de bond sur l'allie taunteur (`get_Range` = 1) -- aucune contribution.
    "MindControl_OutoingDamageReduction": MindControlOutgoingDamageReductionEffect,
    "MindControl_IncomingDamageBonus": MindControlIncomingDamageBonusEffect,
    "MindControl_Taunter": MindControlTaunterEffect,
    # AttemptedPossession (active 1101 thousSorcerer, effet 1209) -- l'OWNER-SWAP : son
    # `ApplyInternal` est litteralement `ChangeUnitOwner(target, bondedEntity)` et son
    # `RevertInternal` `ResetUnitOwner(target)` (IdunBattle.Entities.Effects.Loki.
    # AttemptedPossession_PossessedEffect$$ApplyInternal / $$RevertInternal). Le SECOND effet de
    # l'ability (1210 AttemptedPossession_DmgOverride) n'a AUCUNE classe native propre : c'est le
    # `StatOverrideEffect` generique, deja porte par le canal `AddStatOverrideEffect`. (#590)
    "AttemptedPossession_Possessed": AttemptedPossessionPossessedEffect,
    # LightOfSanguinius (active 1177 bloodDante, effet 1376) -- pose sur la CIBLE + les ennemis qui
    # l'entourent : -dmgReductionPct% sur le degat que le PORTEUR inflige, DOUBLE quand le defenseur
    # du coup est a healthPct% de PV ou moins (IdunBattle.Entities.Effects.Loki.LightOfSanguinius_
    # DamageReductionEffect$$CreateDamageModifier : ForPercentDecrease(get_OwnerIsCaster,
    # If(NOT(HealthPctIsBelowOrEqual(Target, ConfigConst 0x4f)), ConfigVar 0x46, x2)) ; #510).
    "LightOfSanguinius": LightOfSanguiniusDmgReductionEffect,
    "LightCover": LightCoverEffect,     # couverture (tuile) : -2 coups ranged reçus, plancher 1
    "Parry_ReduceHits": ParryEffect,    # trait Parry : -1 coup MÊLÉE reçu, plancher 1
    # Camouflage (trait 1037, ex. admecRuststalker) : -1 coup RANGED reçu (-2 si dist>2, -3 sur tuile
    # DryBush << Tall Grass >>), plancher 1 (IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack, jumeau LightCover/Parry ; slot 0x23 OwnerIsTarget
    # & IsRangedAttack ; consts camouflageHitReduction_1/2/3=1/2/3). #59.
    "Camouflage_HitReduction": CamouflageHitReductionEffect,
    # Diminutive (trait 0x408=1032, summon `orksGrot` + 3 npc) : -diminutiveHitReduction(=1) coup sur
    # TOUTE attaque recue, plancher 1 (IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack = jumeau BigTarget IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack SANS le noeud
    # IsRangedAttack ; trigger OwnerIsTarget seul -> melee ET ranged). #75.
    "Diminutive_HitReduction": DiminutiveHitReductionEffect,
    # ShroudPsalm (effet 0x556=1366, pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.
    # ShroudPsalmAbility$$ExecuteBehaviour` sur jusqu'a 2 ALLIES du caster, caster EXCLU, pour
    # TurnsFromRounds(1)) : -hitsReduction(=2) coups sur les attaques NORMALES recues, plancher 1
    # (`IdunBattle.Entities.Effects.Loki.ShroudPsalmEffect$$CreateEffectHitsBonusForAttack` =
    # `ForAdditionWithMinimum(get_OwnerIsTarget & IsNormalAttack, Negative(Get(ConfigConst 0x2c)),
    # min=Get(1))`). SEUL porteur du noeud `IsNormalAttack` cote DEFENSE. #419-r1-tr9-r4-r1-r2.
    "ShroudPsalm": ShroudPsalmEffect,
    # VoltagheistField_ExtraHit (effet 0x565=1381, pose par `IdunBattleLogic.Entities.Abilities.
    # Triggered.Loki.VoltagheistField_OnRepairAbility` sur `On(0x30 = UnitRepaired) & OwnerIsTarget`,
    # duree UntilEndOfTurn) : +extraHit(=1) coup sur les attaques NORMALES du porteur
    # (`...VoltagheistField_ExtraHitEffect$$CreateEffectHitsBonusForAttack` =
    # `ForAddition(get_OwnerIsCaster & IsNormalAttack, Get(ConfigConst 0x2b))`) -- jumeau structurel
    # de `PowerTrip_FullHealth`. #419-r1-tr9-r4-r1-r2.
    "VoltagheistField_ExtraHit": VoltagheistFieldExtraHitEffect,
    # LegendaryCommander_ExtraHits (effet 0x573=1395, pose SUR custoTrajann par
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegendaryCommanderAbility$$CreateBehaviour`
    # = `AddEffect(0x572, .., Owner, Owner) & AddEffect(0x573, .., Owner, Owner)`) : AURA source-side
    # (+ConfigVar(0x2f = nrOfHits) coups) dont le trigger est le SEUL du canal COUPS pose en NEGATION
    # (`!IsNormalAttack`), avec un etat persistant (<< first attack >>) et
    # `IsFirstHitGroupInAttack`. #419-r1-tr9-r4-r1-r2-r1.
    "LegendaryCommander_ExtraHits": LegendaryCommanderExtraHitsEffect,
    "MasterAnnihilator_extraHit": MasterAnnihilatorAdditionalHitEffect,  # debuff Vitruvius : +1 coup reçu (non-Psychic)
    # LetTheGalaxyBurn (effet 0x5c5=1477, owner-effect auto-porte par les 5 heros Black Legion qui ont le
    # TRAIT 0x422=1058) : +1 coup d'ARME a l'attaque du porteur, gate `OwnerIsCaster &
    # (TargetHasTileEffect | IsPersistentData(0x5ca))` (IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits, count node NULL -> 1 coup). #84.
    "LetTheGalaxyBurn": LetTheGalaxyBurnEffect,
    "BigTarget_AdjacentEffect": BigTargetAdjacentEffect,  # aura : -1 coup ranged aux alliés ring-1 du porteur
    # AstartesBanner (porte-banniere Astartes ex. templAncient) : AURA +extraHits(=1) coup MELEE aux ALLIES
    # dans le rayon 2 du porteur (l'effet vit sur LE PORTEUR, comme BigTarget ; IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits ForAddition
    # OwnerIsCaster&IsMeleeAttack ConfigVar 0xd, selector SurroundingFriends range ConfigConst 0x16=2). #107.
    "AstartesBanner_ExtraHit": AstartesBannerExtraHitEffect,
    "ShadowInTheWarp_LessDmg_Effect": ShadowInTheWarpLessDmgEffect,  # aura : -25% degat PSYCHIQUE aux ennemis a portee
    # DaughterOfTheAbyss (Atlacoya custoAtlacoya, passif range 2) — 3 effets sur le PORTEUR (#184) :
    # Friendly = -dmgReductionPct% (33 @L50) au degat PSYCHIQUE recu par les AMIS rayon 2 (aura-defense,
    # boucle state-wide IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction ; racine du ~1.49x bloodMephiston seed 2024) ; Owner = -dmgReduction
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
    # additif a TOUTES les attaques du porteur (IdunBattle.Entities.Effects.Loki.BeaconOfRage_ExtraDamageEffect$$CreateEffectDamageBonusForAttack ForAddition OwnerIsCaster seul) ; rage =
    # decisionView.effects[].level = min(TotalTimesAttacked, nrOfAttacks=8), cappe a l'ecriture par
    # le natif (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ABeaconOfRageAbility$$GetUpdateSelfEffectBehaviour). EffectType 0x512=1298 (#189). La variante 0x513=1299 FriendlyExtraDamage
    # = aura HOSTEE sur Azkor (IdunBattle.Entities.Effects.Loki.BeaconOfRage_FriendlyExtraDamageEffect$$CreateEffectDamageBonusForAttack PercentageOf(Multiply(ConfigVar extraDmg, EffectLevel), 50)) :
    # 50% du bonus rage FLAT aux attaques MELEE des amis Chaos adjacents, si Azkor a >=1 kill. Canal aura
    # cote source create_aura_attack_damage_bonus_for_ally -> mods.additive de l'ami attaquant (#191).
    "BeaconOfRage_ExtraDamage": BeaconOfRageExtraDamageEffect,
    "BeaconOfRage_FriendlyExtraDamage": BeaconOfRageFriendlyExtraDamageEffect,
    # TerrifyingCrescendo (passif triggered 1435 d'emperNoiseMarine "Shiron") : +extraDmg[ablvl passif]
    # x mult x crescendo FLAT additif aux attaques RANGED du porteur (IdunBattle.Entities.Effects.Loki.TerrifyingCrescendo_ExtraDmgEffect$$CreateEffectDamageBonusForAttack ForAddition(IsRangedAttack
    # & OwnerIsCaster, Multiply(ConfigVar 8=extraDmg, EffectLevel))) ; crescendo = decisionView.effects[].level
    # = min(nb overkill/suppress, buffMaxLevel=6), cappe a l'ecriture par IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour. Jumeau
    # de BeaconOfRage + gate IsRangedAttack. EffectType 0x590=1424 (#204). Accumulation = CreateTrigger
    # IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger (On overkill | On suppress-effect-pose 0x429=1065). extraDmg[L65]=218 (i2), rarity-scale.
    "TerrifyingCrescendo_ExtraDmg": TerrifyingCrescendoExtraDmgEffect,
    # FuelledByFury (passif triggered 1251 d'ultraTitus << Titus >>) : +extraDmg[ablvl passif] x mult
    # x fury FLAT additif a TOUTES les attaques du porteur (IdunBattle.Entities.Effects.Loki.
    # FuelledByFury_ExtraDamageEffect$$CreateEffectDamageBonusForAttack = ForAddition(get_OwnerIsCaster
    # SEUL, GetCurrentExtraDamage() = Multiply(ConfigVar 8=extraDmg, EffectLevel))). C'est le corps
    # PARTAGE dont TerrifyingCrescendo herite (`...FuelledByFury_ExtraDamageEffect$$GetCurrentExtraDamage`,
    # refcount 10). fury = compteur d'abilities ACTIVES castees par des Characters ALLIES, accumule
    # par IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateTrigger
    # (`On(0xe=UnitPostAbility) & AreFriends & HasTrait(Hero) & !HasTrait(MachineOfWar) &
    # IsActiveAbilityCountedAsUsed`) -> `If(HasEffect, IncreaseEffectLevel(+1, SANS cap), AddEffect)`.
    # EffectType 0x52b=1323 (#1323). extraDmg[L65]=153 (i2), rarity-scale.
    "FuelledByFury_ExtraDamage": FuelledByFuryExtraDamageEffect,
    # ModifiedExoarmour (passif triggered 0x5f9=1529 de votanChampion << Kimm >>) : +extraDmg[ablvl
    # passif] x mult x TILES-PARCOURUES-CE-TOUR, additif PRE-percage, sur les attaques de MELEE du
    # porteur (`IdunBattle.Entities.Effects.Loki.ModifiedExoarmour_ExtraDmgEffect$$
    # CreateEffectDamageBonusForAttack` = ForAddition(get_OwnerIsCaster & IsMeleeAttack,
    # GetCurrentDamageBonus() = Multiply(ConfigVar 8=extraDmg, TilesMovedThisTurn(Self)))).
    # EffectType 0x608=1544 (case-322 ; l'ecart mesure par #312 valait 44.395 vs 17.8 en utilite).
    # MEME forme que FuelledByFury (Multiply(ConfigVar, <compteur>)), le compteur en moins.
    "ModifiedExoarmour_ExtraDmg": ModifiedExoarmourExtraDmgEffect,
    # OverwhelmingWrath (active 1141 d'Azkor) : -dmgReductionPct% (64 des L36) au degat RANGED recu
    # par le porteur jusqu'au debut de son tour suivant (transient rem=1 ; IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_RangeDmgReductionEffect$$CreateDamageDefenseModifier ForPercentDecrease
    # OwnerIsTarget & IsRangedAttack, ConfigVar 0x46). EffectType 0x515=1301 (#190). Le jumeau
    # 0x514=1300 PendingAttack (attaque differee 2x Eviscerate) = hors canal modifier, tache dediee.
    "OverwhelmingWrath_RangeDmgReduction": OverwhelmingWrathRangeDmgReductionEffect,
    # FireAndReposition (active 1063 de Calandis eldarRanger) : -dmgReduction[active_lvl] x mult PLAT
    # du degat RANGED recu par le porteur, MAIS seulement HORS de son propre tour
    # (`...FireAndReposition_ReduceDmgEffect$$CreateEffectDamageMalusForDefense` = ForSubtraction(
    # OwnerIsTarget & IsRangedAttack & NOT IsTurnOf(Owner), ConfigVar 0x12=dmgReduction)). Le 3e gate
    # est ce qui EXCLUT l'overwatch ennemi declenche pendant le tour de Calandis -- il n'est PAS
    # redondant avec la duree TurnsFromRounds(1) de la pose. Canal = flat_reductions (additif
    # DEFENSEUR pre-percage, meme slot @+0x10 que Nightshroud). EffectType 0x456=1110 (#366-r1).
    "FireAndReposition_ReduceDmg": FireAndRepositionReduceDmgEffect,
    # PsychicStalk (passif triggered 1179 d'Ahriman thousAhriman) : +extraDmgPct % (33 @L50/L65) au
    # degat RECU par tout ENNEMI d'Ahriman qui se tient sur un hex EN FEU, quand le coup a un profil
    # Flame ou Psychic. `IdunBattle.Entities.Effects.Loki.PsychicStalk_ExtraAttackDamageEffect$$
    # CreateEffectDamageMalusForDefense` = ForPercentIncrease( (IsUnit|IsMachine|CasterIsCasterTile)
    # & AreEnemies(Target@0x60, Owner@0x30) & GetTargetIsOnFireTileCondition() &
    # GetAttackHasValidDamageProfileCondition(), ConfigVar(0xa = extraDmgPct) ). L'effet vit sur
    # AHRIMAN (`...ExtraAttackDamageAbility$$CreateBehaviour` : `AddEffect(0x4bf, targets=Owner@0x30)`)
    # -> canal AURA state-wide `create_aura_defense_damage_malus_for_ally`, %-list DEFENSEUR (PAS
    # `flat_reductions` : la fabrique est ForPercentIncrease, pas ForSubtraction). AUCUN gate sur
    # l'attaquant hors le OU structurel -- c'est ce qui le separe de son voisin 0x59b=1435
    # FriendlyChaosExtraDamage (ForAddition, gate `AreFriends & HasTrait(Chaos)`, ci-dessous).
    # EffectType 0x4bf=1215 (#366-r1).
    "PsychicStalk_ExtraAttackDamage": PsychicStalkExtraAttackDamageEffect,
    # 3e effet du MEME kit PsychicStalk, canal ATTAQUANT ADDITIF (et non %-list defenseur) :
    # `IdunBattle.Entities.Effects.Loki.PsychicStalk_FriendlyChaosExtraDamageEffect$$
    # CreateEffectDamageBonusForAttack` = ForAddition( AreFriends(Owner@0x30, Caster@0x48)
    # & HasTrait(Caster@0x48, 0x7ea = Chaos) & GetTargetIsOnFireTileCondition()
    # & GetAttackHasValidDamageProfileCondition(), ConfigVar(8 = extraDmg) ). Le slot 0x16 est
    # invoque STATE-WIDE par `IdunBattle.Core.Services.DamageCalculations$$
    # CalculateAttackerModifiersForPrediction`, sans exclure le porteur (`UnitExtensions$$IsFriend`
    # n'ecarte pas l'egalite) -> DEUX pattes port disjointes : `create_effect_damage_bonus_for_attack`
    # (Ahriman attaque) + `create_aura_attack_damage_bonus_for_ally` (un allie Chaos attaque).
    # ⚠ `extraDmg` est dans `variablesAffectedByRarityBonus` -> SCALE par le multiplier de rarete
    # (499 @{L50, 180 %}), contrairement a l'`extraDmgPct` de 1215. EffectType 0x59b=1435 (#366-r1).
    "PsychicStalk_FriendlyChaosExtraDamage": PsychicStalkFriendlyChaosExtraDamageEffect,
    # 3e et DERNIER effet du kit PsychicStalk -- AUCUN canal de degat, aucun stat-mod, aucun trigger :
    # la classe native `IdunBattle.Entities.Effects.Loki.PsychicStalk_VisualEffectEffect` ne surcharge
    # QUE `CreateActiveCondition` (= `NOT IsDead(Owner@0x30)`, portee -> `is_active`),
    # `CreateTargetSelector` (= `Units(EntitiesWithAnyEffect(Tiles(Enemies(Owner, AllUnits, alive)),
    # Fire = 5, effectTarget = 6), unique, 3)`, portee -> `target_selector_covers`) et
    # `GetRefreshTriggers` (non portable : le port n'a pas de `RefreshEffectTrigger`). Sa sortie est
    # 100 % PRESENTATION, et les DEUX consommateurs sont NOMMES : le VFX/SFX
    # `IdunBattle.View.AbilityConfigs.Loki.PsychicStalkEffectVisual` et l'ICONE de statut
    # (`StaticBattleRules.Effect$$.cctor` inscrit 0x4c0 -> 2 dans le dict d'affichage <statics>+0x10,
    # que `IsUnitEffectShownAsGenericDebuff` teste `== 2`). Inscrit ici pour NOMMER la classe native
    # au lieu de router sur `BaseEffect` -- meme motif que `WireweaveNet_CounterAttack`.
    # EffectType 0x4c0=1216 (#366-r1).
    "PsychicStalk_VisualEffect": PsychicStalkVisualEffect,
    # WireweaveNet (PASSIF 1111 de Calandis `eldarRanger`) : effet-RIPOSTE (`CounterAttackEffect` ->
    # `PlayerTurnEffect`). AUCUN canal de bonus -- tout son observable vit dans les TROIS `Triggered()`
    # de `EFFECT_TRIGGERS[1111]` (`runner/operations/triggers/loki/wireweave_net.py`). Inscrit ici pour
    # nommer la classe NATIVE au lieu de router sur `BaseEffect`, et porter les litteraux du `.ctor`
    # (`turnsEnabled=1` -> tour ENNEMI, `activationFrequency=2`, `hasAutomaticActivation=False`).
    "WireweaveNet_CounterAttack": WireweaveNetCounterAttackEffect,
    # 1255 MartialSuperiority_Visual (case-366-r1) : MARQUEUR « riposte armee » du passif
    # `MartialSuperiority` (1092) de `templChampion`, pose a l'init par
    # `MartialSuperiorityAddEffectAbility` (`AOwnerEffectTriggeredAbility`, corps de BASE). Sa SEULE
    # semantique native est `CreateActiveCondition = op_LogicalNot(<DSLTriggers+0x28>)` =
    # `NOT IsTurnOf(Owner)` -- aucun `CreateEffect*`, aucun stat-mod, `hasAutomaticActivation=TRUE`.
    # AUCUN consommateur logique de l'id 1255 dans tout le binaire (balayage exhaustif de l'immediat
    # 0x4e7 : que des sites d'ENREGISTREMENT), et aucun poids `MartialSuperiority*` dans
    # `BC.Utilities` -> contribution de FIDELITE seule (le flag `IsActive` de l'instance suit la
    # condition native au lieu de rester `True` inconditionnellement). Detail :
    # `loki/martial_superiority.py`.
    "MartialSuperiority_Visual": MartialSuperiorityVisualEffect,
    # PsychicFortress (passif Tigurius ultraTigurius, ability enum 0x3e8=1000) -- 2 effets posEs par
    # IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicFortressAbility$$CreateBehaviour :
    #  - DmgReduction (0x3f2=1010) : AURA -dmgReduction[ablvl]xmult PLAT du degat PSYCHIQUE recu par les AMIS
    #    ring-1 (aura-defense, gate DamageProfileIs Psychic ; IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateDamageModifier ForAddition(Multiply(ConfigVar 0x12,
    #    Direct(-1))) ; selector IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateTargetSelector Friends(SurroundingUnits range 1, exclut porteur)). Jumeau structurel
    #    de DaughterOfTheAbyss_Owner/Nightshroud -> flat_reductions pre-percage.
    #  - ExtraBlock (0x3ef=1007) : source de BLOCK +blockChance(=50)% de blockDmg[ablvl]xmult Damage
    #    (IdunBattleLogic.Entities.DSLFactory$$AddExtraBlockEffectToOwner, MultiValueStat 7/8 hors GetStat, comme BeastSlayer).
    "PsychicFortress_DmgReduction": PsychicFortressDmgReductionEffect,
    "PsychicFortress_ExtraBlock": PsychicFortressExtraBlockEffect,
    # CamoCloak_DmgReduction (0x3f6=1014, passif CamoCloak 0x3eb=1003 de `ultraEliminatorSgt` et du
    # summon `ultraSmnEliminator`) -- owner-effect PERMANENT (`CamoCloakAbility$$CreateBehaviour` =
    # `AddEffect(0x3f6, stateRef, Owner@0x148, duree 0)`). Reduction PLATE du degat RANGED recu,
    # GATEE par le COUVERT : `HasEffect(sel, 1013 LightCover, onlyActive=0, 6) | IsEffectTarget(sel,
    # 1026 BigTarget_Adjacent)` -- le meme predicat sert de `CreateActiveCondition` (sur Owner) ET de
    # membre du trigger de degat (sur Target). Canal = `ForAddition(Multiply(ConfigVar 0x12,
    # Direct(-1)))` slot +0x10 == jumeau STRUCTUREL de PsychicFortress -> `flat_reductions`
    # pre-percage. Magnitude indexee par le niveau PASSIF (`set_TriggeredAbility`). (#366-r1)
    "CamoCloak_DmgReduction": CamoCloakDmgReductionEffect,
    # DecoysAndMisdirection (Genestealer Cults ex. genesPrimus/genesMagus/genesKelermorph) : +extraDmg
    # FLAT additif a TOUTES les attaques de l'ami buffe (pose quand un decoy est spawn a cote / qu'un ami
    # marche sur un decoy). Gate OwnerIsCaster SEUL (IdunBattle.Entities.Effects.Loki.DecoysAndMisdirection_ExtraDamageEffect$$CreateEffectDamageBonusForAttack -> applique en prediction+combat, cf.
    # Neuroparasite). extraDmg[L65]=582 rarity-scale x mult. EffectType capte 1379. #134 (spawn+retaliation
    # Blast NON encore portes -- seul l'effet ExtraDamage l'est ici). Nom capte = effect-type-names.ts:502.
    "DecoysAndMisdirection_ExtraDamage": DecoysAndMisdirectionExtraDamageEffect,
    # LordOfTempests (passif Njal spaceStormcaller, EffectType 0x4d4=1236) : +extraDmg[ablvl]xmult FLAT
    # PAR HEX GLACE du ring-1 de la position d'attaque (IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$CreateEffectDamageBonusForAttack ForAddition(OwnerIsCaster,
    # Multiply(ConfigVar 8=extraDmg, Count(SurroundingTiles(0,1) with Ice)))) — magnitude POSITION-
    # DEPENDANTE re-countee par tuile candidate via att_ctx. VALIDE BIT-EXACT 31337 s18 (#29).
    "LordOfTempests_ExtraDamage": LordOfTempestsExtraDamageEffect,
    # HypersensoryAbilities (passif Judh genesJudh) : HP-floor 50% du HP courant a la 1re attaque du tour
    # ennemi (effet 0x564=1380). Snapshot floor via IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal / clear via RevertInternal
    # IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$RevertInternal ; ActiveCondition IsEnemyTurn & Not(attacked>=1). Apply/Revert impératifs = op runner
    # `MinimalHealthEffectOperation` ; le clamp vit dans `HealthComponent.reduce`. Nom capte = 1380 enum. G6a.
    "HypersensoryAbilities_MinimalHealth": HypersensoryMinimalHealthEffect,
    # AnvilShield (Arjac spaceRockfist) — les TROIS effets de la passive (tous ability-init, ability
    # ACTIVE -> index activeAbilityLevel) :
    #  - 0x4b2=1202 AdditionalBlock : stat 8 BLOCK_DAMAGE, var 0x14 blockDmg[L65]=728 RARITY-scale (997
    #    live). INCONDITIONNEL (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour`, 1er volet).
    #  - 0x4b0=1200 BlockChanceBelowHealthCap : stat 7 BLOCK_CHANCE, var 0x15 blockChance (=20, NON
    #    rarity-scale), 2e volet de la MEME behaviour. ActiveCondition (#100, resolue) =
    #    `AmountIsEqualOrGreater(Direct(GetNumberConstant(0x4f=healthPct=35)), StatAmount(Self, HEALTH,
    #    CURRENT_PCT))` -> le gate sante est un **POURCENTAGE** (StatPart 1). Live : absent+blockChance 0
    #    a 100 % PV, present+blockChance 20 a 31.8 %.
    #  - 0x4b1=1201 FrozenAttackerAdvantage : MEME stat 7 / MEME var 0x15, pose TRANSITOIREMENT par
    #    `...AnvilShieldAbility_FrozenAttackerAdvantage$$CreateBehaviour` sur `On(0x2a=PreUnitAbility)`
    #    quand l'attaquant est sur une tuile GLACEE, consomme a `On(0xe=UnitPostAbility)`.
    # Les DEUX derniers etaient les prerequis manquants du volet `ApplyStun` (#100).
    "AnvilShield_AdditionalBlock": AnvilShieldAdditionalBlockEffect,
    "AnvilShield_BlockChanceBelowHealthCap": AnvilShieldBlockChanceBelowHealthCapEffect,
    "AnvilShield_FrozenAttackerAdvantage": AnvilShieldFrozenAttackerAdvantageEffect,
    # HammerOfWrath_ConditionalDamage (0x534=1332) — MEME PATRON qu'`AnvilShield_BlockChanceBelowHealthCap` :
    # owner-effect PERMANENT pose a l'init de l'ability (triggered 1258 `AOwnerEffectTriggeredAbility`),
    # SANS contribution propre, dont l'`ActiveCondition` (`HealthPctIsBelowOrEqual(Self, ConfigConst(
    # 0x4f=healthPct=50))`) est LUE par `HammerOfWrathAbility$$GetDoubleCondition` = `HasEffect(Self,
    # 0x534, activeOnly=1)` pour DOUBLER les bornes de degat. Absent du seed live tant qu'il est inactif.
    "HammerOfWrath_ConditionalDamage": HammerOfWrathConditionalDamageEffect,
    # TunnelingHorror_PendingSummon (0x459=1113, `necroSmnDestroyer`) -- MARQUEUR de bond pose sur la
    # TUILE de destination par `TunnelingHorrorAbility$$ExecuteBehaviour` (active 1011), retire par
    # `TunnelingHorror_AppearAbility$$ExecuteBehaviour` (active 1060). ZERO contribution. Sa classe
    # native derive d'`ABondEffect` (le `.ctor` que Ghidra attribue a `BaseEffect` est un corps
    # DEDUPLIQUE -- parent lu dans `frida/classes.tsv`) et surcharge les TROIS getters qui pilotent
    # `ABondEffect$$CreateHandleTriggerAbilitiesInternal` a false/null/false => l'`ArraySet` de
    # triggers de retrait automatique est VIDE, donc AUCUNE entree `EFFECT_TRIGGERS[1113]` (mesure,
    # pas oubli). Arrive offline par `_load_tile_effects` uniquement : l'ability 1011 n'est pas
    # portee (primitive `RemoveUnitFromTilesOperation` manquante, residu #366-r1).
    "TunnelingHorror_PendingSummon": TunnelingHorrorPendingSummonEffect,
    # Contaminated_Unit (0x4dd=1245) : sous-effet -X% FixedArmor pose sur une unite occupant/entrant une
    # tuile contaminee (0x4dc). Debuff stat FixedArmor (=16) ; magnitude X NON resolue (#132) -> value=None
    # tant que non mesure live (present mais inerte-stat). Pose par le vecteur tile-effect ContaminatedTileEffect
    # (#128, triggers.py). Nom capte = effect-type-names.ts:368.
    "Contaminated_Unit": ContaminatedUnitEffect,
    # ContagionsOfNurgle_ArmorReduction1/2 (0x42f=1071 / 0x430=1072) : les DEUX instances de
    # `ContagionsOfNurgle_ArmorReduction_Effect` (une aura / deux-ou-plus). Debuff FixedArmor (=16),
    # magnitude = variable de trait (-20 / -40 %), materialisee en DELTA PLAT par le vecteur poseur
    # `operations/triggers/loki/contagions_of_nurgle.py` (case-dpw). Noms captes = effect-type-names.
    "ContagionsOfNurgle_ArmorReduction1": ContagionsOfNurgleArmorReductionEffect,
    "ContagionsOfNurgle_ArmorReduction2": ContagionsOfNurgleArmorReductionEffect,
    # Contaminated (0x4dc=1244) : l'effet de TUILE lui-meme. Porte pour son point d'extension
    # IMMUNITE (`ContaminatedEffect$$EntityIsImmuneToEffect` : ContagionsOfNurgle | Mechanical |
    # base) — canal unique consulte par le gate de `AddEffectOperation` ET par le vecteur
    # tile-effect. Nom capte = effect-type-names.ts (`EffectType.Contaminated`). #224.
    "Contaminated": ContaminatedEffect,
    # DespoiledGround (0x5c4=1476) : l'effet de TUILE lui-meme (#85). MEME patron que `Contaminated` /
    # `Fire` : marqueur sans contribution propre, tout l'observable vit dans l'ability d'environnement
    # qui le lit (`EnvDespoiledGroundTileAbility` -> `DespoiledGroundTileDoT`). Porte pour que le
    # tile-effect pose par `FleshMetalGuns_TileEffectAbility` soit une VRAIE instance (nom capte, duree
    # `DefaultAmountOfRounds(0x5c4)=2` rounds -> tours, expiration par `on_turn_end`).
    "DespoiledGround": DespoiledGroundEffect,
    # DespoiledGround_ExtraDamagePct (0x5c6=1478) : le buff +15 % degat (BC `DespoiledGroundExtraDmgPct`)
    # pose sur l'unite CHAOS qui demarre son tour sur une tuile DespoiledGround, actif contre les cibles
    # Xenos (1006) ou Imperial (26). Nom capte = effect-type-names.ts.
    "DespoiledGround_ExtraDamagePct": DespoiledGroundExtraDamagePctEffect,
    # Leagues of Votann (#113) — les TROIS stat-mods sont des `DynamicStatModifierEffect` GENERIQUES
    # (aucune classe native dediee) instancies par des lambdas de `EffectsDatabase$$InitializeEffects` :
    # magnitude = `ConfigVar(<abilityId>, EffectSource, <varKey>)`, signe = le champ `isNegative` (+0x4a4)
    # lu par `DynamicStatModifierEffect$$GetDynamicStatModificationAmount`. Detail + lambdas citees :
    # entities/effects/loki/votann.py.
    #  - 0x605=1541 : ability 1221 AugmentedAssault, var 0x30=48 armorReduction, isNegative=1 -> stat 16
    #    FixedArmor NEGATIF sur la CIBLE de l'attaque (permanent : 0x605 absent du switch
    #    `StaticBattleRules.Effect$$DefaultAmountOfRounds`).
    #  - 0x5cd=1485 / 0x5ce=1486 : ability 1207 AncestralFortune, vars 0x41=65 extraCritChance /
    #    0x3e=62 extraBlockChance, isNegative=0 -> stats 9 CritChance / 7 BlockChance sur le CASTER, 1 round.
    # 0x43b=1083 (#419-r6-r2) : le JUMEAU **STATIC** du 0x605 ci-dessous -- meme observable
    # (FixedArmor NEGATIF permanent sur la cible), mecanique native DIFFERENTE. Classe DEDIEE
    # `IdunBattle.Entities.Effects.Loki.ChampionOfTheFeast_ReduceArmorEffect` derivant de
    # `StaticStatModifierEffect`, posee par `ChampionOfTheFeastAbility$$CreateBehaviour` via
    # `AddStaticStatModifierEffect(target, 0x43b, 0x10 FixedArmor, Direct(-armorReduction), turns=NULL)`.
    # Le signe vient de la FORMULE (`Direct(-v)`), pas d'un flag `isNegative`. Detail :
    # entities/effects/loki/champion_of_the_feast.py.
    "ChampionOfTheFeast_ReduceArmor": ChampionOfTheFeastReduceArmorEffect,
    "AugmentedAssault_ReduceArmor": AugmentedAssaultReduceArmorEffect,
    "AncestralFortune_ExtraCritChance": AncestralFortuneExtraCritChanceEffect,
    "AncestralFortune_ExtraBlockChance": AncestralFortuneExtraBlockChanceEffect,
    # 0x56f=1391 \ 0x570=1392 (case-231) : MEME patron GENERIQUE que le trio ci-dessus. Lambdas
    # `EffectsDatabase...b__14_400` / `...b__14_401` -> ability 1184 MomentShackle, vars 0x15=21
    # blockChance / 0x14=20 blockDmg, isNegative=0 -> stats 7 BlockChance / 8 BlockDamage sur le
    # CASTER (le call-site passe `owner@0x148` en source ET en cible), TurnsFromRounds(1).
    "MomentShackle_ExtraBlockChance": MomentShackleExtraBlockChanceEffect,
    "MomentShackle_ExtraBlockDamage": MomentShackleExtraBlockDamageEffect,
    # 0x5cc=1484 GravitonRifle_ExtraPierce : OWNER-effect de Vynn (dict natif
    # `GetEffectToBeAddedToOwnerForAbility`), classe DEDIEE
    # `IdunBattle.Entities.Effects.Loki.GravitonRifle_ExtraPierceEffect` — canal PERCAGE (pas stat-mod) :
    # `CreatePiercingBonusForAttack` = ForAddition((OwnerIsCaster & CurrentAbilityIs(1206)) &
    # (HasTrait(target,1039)|HasTrait(target,1013)|HasTrait(target,5)), ConfigVar(0x3f=63 extraPierceRatio)).
    "GravitonRifle_ExtraPierce": GravitonRifleExtraPierceEffect,
    # 0x576=1398 WallOfMirrors (#433-r4-r1-r1) : effet pose par le cast de 1186 sur SON PROPRE caster
    # juste avant le `UseNormalAttack`, et retire juste apres -- canal PERCAGE, UN SEUL gate.
    # `IdunBattle.Entities.Effects.Loki.WallOfMirrorsEffect$$CreatePiercingBonusForAttack` =
    # ForAddition(get_OwnerIsCaster, ConfigConst(0x40 = extraPierce)).
    "WallOfMirrors": WallOfMirrorsEffect,
    # 0x602=1538 PurgeResponse (case-366-r1-blockhits-purgeresponse) : owner-effect du passif
    # `PurgeResponse` (TriggeredAbilityType 0x5f6 = 1526) de l'Ironkin Steeljack
    # (`votanSmnSteeljack`, summon de `votanMemnyr` via `IronkinSteeljack` 1219 ; jumeau npc
    # `votanNpc2Steeljack`). SECOND et DERNIER implementeur natif de `BlockHitsReduction` :
    #   `IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$CreateBlockHitReductionTrigger`
    #       = TriggeringAbilityIs( AbilityOrEffect(EffectType 0x3f1 = 1009 Overwatch_AutoAttack) )
    # UN SEUL noeud -- pas de `get_OwnerIsCaster`, pas d'`op_BitwiseAnd` (lu a l'assembleur). Le
    # trigger ne lit RIEN du porteur : une seule instance ACTIVE sur le board, dans N'IMPORTE quel
    # camp, suffit a eteindre les reductions de coups de TOUTE attaque d'overwatch. C'est ce qui a
    # impose le balayage BOARD-WIDE de `block_hits_reduction_from_effects` (l'ancien balayage
    # attaquant-seul RENDAIT le `get_OwnerIsCaster` de 1117, qui a migre dans sa classe).
    "PurgeResponse": PurgeResponseEffect,
    # Trait PrioritisedEfficiency (0x423=1059, LES TROIS Votann : votanBeserk/votanIronmaster/votanUthar)
    # -- systeme de STANCES a 5 effets (#121). Les DEUX effets porteurs de degat sont portes ici ; les
    # deux MARQUEURS de stance (1479 HostileAcquisition / 1480 FortifyTakeover) n'ont AUCUNE methode
    # native (ils ne servent qu'aux `HasEffect` des behaviours de stance et de GrimEfficiency) -> BaseEffect
    # nu = fidele ; `PrioritisedEfficiency_ExtraMovement` (1482) = stat-mod MOVEMENT non porte (residu).
    #  - 0x5c9=1481 ExtraDmg (stance « Hostile Acquisition ») :
    #    `IdunBattle.Entities.Effects.Loki.PrioritisedEfficiency_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
    #    = `ForPercentIncrease(get_OwnerIsCaster, ConfigConst(0xf))` -> +25 % (%-list ATTAQUANT, POST
    #    percage/armure) sur TOUTES les attaques du porteur (normales ET abilities, melee ET distance).
    #  - 0x5cb=1483 DmgReduction (stance « Fortify Takeover ») :
    #    `...PrioritisedEfficiency_DmgReductionEffect$$CreateEffectDamageMalusForDefense`
    #    = `ForPercentDecrease(get_OwnerIsTarget, ConfigConst(0x72))` -> -33 % sur TOUT degat recu.
    "PrioritisedEfficiency_ExtraDmg": PrioritisedEfficiencyExtraDmgEffect,
    "PrioritisedEfficiency_DmgReduction": PrioritisedEfficiencyDmgReductionEffect,
    # 0x580=1408 MartialInspiration_ExtraDamage (#509) : l'active `1191 MartialInspiration` de
    # `custoBladeChampion` << Kariyan >> le pose SUR SON PROPRE CASTER (1 tour) AVANT de frapper.
    # `...MartialInspiration_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` =
    # `ForPercentIncrease( OwnerIsCaster & (CurrentAbilityIs(ActiveAbilityType 0x4a7 = 1191)
    #                                       | CurrentAbilityIs(TriggeredAbilityType 0x527 = 1319
    #                                                          LegacyOfCombat)),
    #                      ConfigVar(0xa extraDmgPct) x TotalTurnsWithAttacksMade(Owner) )`.
    # Les TROIS constantes du corps passent par TROIS surcharges DIFFERENTES d'`op_Implicit`
    # (`set_ActiveAbility` / `set_TriggeredAbility` / `set_Effect`) -- cf. l'en-tete du module.
    "MartialInspiration_ExtraDamage": MartialInspirationExtraDamageEffect,
    # 0x5e5=1509 Hailstrike (case-117 phase 2) : buff pose sur un ALLIE par l'ability 1214 de la MoW
    # `darkaStormSpeeder`. Classe DEDIEE `IdunBattle.Entities.Effects.Loki.Hailstrike_ExtraPierceEffect`
    # — canal PERCAGE : `CreatePiercingBonusForAttack` = `ForPiercing(OwnerIsCaster & (IsRangedAttack |
    # IsOverwatchAttack), ConfigVar(0x3f=63 extraPierceRatio, GetAbilityState(this)))`. AUCUN gate
    # `CurrentAbilityIs` -> s'applique aussi a l'attaque NORMALE ranged du porteur. Le nom d'EffectType
    # capte live est « Hailstrike » (== `EffectType.Hailstrike`, verifie par test_storm_speeder_live).
    "Hailstrike": HailstrikeExtraPierceEffect,
    # 0x541=1345 / 0x542=1346 VisionsOfHeresy_ExtraPierce{Melee,Ranged} (case-366-r1) — les DEUX
    # owner-effects du passif `VisionsOfHeresy` (0x4f0=1264) de `bloodDeathCompany` <<Lucien>>.
    # UNE SEULE classe native (`VisionsOfHeresy_ExtraPierceEffect` : les deux ids partagent le MEME slot
    # `Il2CppClass*`, tranche par le SLOT et non par le nom du ctor) ; le discriminant melee/ranged est le
    # `statType` que passe le poseur `...VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour` =
    # `AddStaticStatModifierEffect(Owner, 0x541, 0x15=21 EXTRA_PIERCE_MELEE, ConfigVar(0x3f=extraPierceRatio),
    #  turns=NULL) & AddStaticStatModifierEffect(Owner, 0x542, 0x16=22 EXTRA_PIERCE_RANGED, <le MEME>, NULL)`.
    # CANAL = le STAT (21/22), lu par `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`
    # (`GetStat(attacker, isMelee ? 0x15 : 0x16)`) — PAS un `EffectBonus.ForPiercing` (canal de Hailstrike
    # ci-dessus). ActiveCondition = `HealthPctIsBelowOrEqual(Owner, ConfigConst(0x4f=healthPct)=50)`, donc
    # les deux effets sont ABSENTS du seed live tant que Lucien est au-dessus de 50 % PV : ils sont poses
    # par `ABILITY_INIT_OWNER_EFFECTS["VisionsOfHeresy"]` et actives/desactivees par le driver
    # `refresh_stat_modifier_effects`. Cf. `entities/effects/loki/visions_of_heresy.py`.
    "VisionsOfHeresy_ExtraPierceMelee": VisionsOfHeresyExtraPierceMeleeEffect,
    "VisionsOfHeresy_ExtraPierceRanged": VisionsOfHeresyExtraPierceRangedEffect,
    # 1222 WarHowl_ExtraDamage_Unstoppable (case-366-r1) : buff a DUREE 1 TOUR pose par l'ACTIVE
    # `WarHowl` (0x452 = 1106) de `spaceBlackmane` <<Ragnar>> sur LUI-MEME + tout ami MELEE non-Summon
    # (`WarHowlAbility$$ExecuteBehaviour` : `AddEffect(0x4c6, CreateSnapshot(abilityState),
    #  source = Caster, targets = Caster + UnitsWithoutTrait(UnitsWithoutRangedWeapons(Friends(...)),
    #  0x2 = Summon), turns = Get(1))` -- ni faction ni rayon). Classe DEDIEE : le slot `Il2CppClass*`
    # `0x1833908e8` n'est partage par aucun autre id, et le `$$.ctor` n'a qu'UN appelant parmi les 607
    # fabriques (`...EffectsDatabase.<>c$$<InitializeEffects>b__14_240`).
    # DEUX canaux de LECTURE portes, tous deux gates `get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack` :
    #   `...WarHowl_ExtraDamage_UnstoppableEffect$$CreateEffectDamageBonusForAttack`
    #       = ForAddition(<3 noeuds>, ConfigVar(0x08 = extraDmg))          -> additif per-coup ;
    #   `...WarHowl_ExtraDamage_UnstoppableEffect$$CreateCritChanceBonus`
    #       = ForAddition(<3 noeuds> & AmountIsGreaterThanZero(StatAmount(Caster, 0x9 CriticalChance,
    #                     StatPart.Current)), ConfigVar(0x41 = extraCritChance)).
    # Le 3e artefact (`ApplyInternal`/`RevertInternal` = AddTrait/RemoveTrait `0x412 = 1042
    # Unstoppable`, isTemporary) est LU par le substrat d'entite (`combatSnapshot.units[].traits`,
    # MESURE : u81 gagne 1042 au cast) ; sa POSE offline attend le port de l'ability 1106.
    "WarHowl_ExtraDamage_Unstoppable": WarHowlExtraDamageUnstoppableEffect,
    # 1529 RitesOfMorkai_ExtraDamage (#906) : SECOND effet de l'ACTIVE `RitesOfMorkai` (0x4bb = 1211)
    # de `spaceWolfPriest` <<Baldr>>, pose sur le sous-ensemble de sa zone qui porte deja une forme de
    # Final Vengeance (`RitesOfMorkaiAbility$$ExecuteBehaviour` : `AddEffect(0x5f9,
    #  AbilityStateReference, Filter(<la zone cachee>, HasTrait(ActiveTarget, 0x3f6 FinalJustice)
    #  op_BitwiseOr HasEffect(ActiveTarget, 0x5ae FinalVengeance_UnitEffect, onlyActive: 0, Both)),
    #  TurnsFromRounds(ConfigConst(0x45 nrOfRounds)))`). Le PREMIER effet du meme cast est 1502
    # `RitesOfMorkai` (le revive, `runner/operations/triggers/loki/rites_of_morkai.py`, #79/#229).
    # UN canal de LECTURE porte, a UN SEUL noeud de trigger -- et c'est le contraste avec 1222 :
    #   `...RitesOfMorkai_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`
    #       = ForAddition(get_OwnerIsCaster, ConfigVar(0x08 = extraDmg))     -> additif per-coup,
    #     SANS `IsMeleeAttack` ni `IsNormalAttack` (i2 : « with all attacks »).
    # `CreateActiveCondition` = `$$HasAnyKindOfFinalVengeance` (corps FONDU par IL2CPP, la MEME
    # adresse occupe DEUX slots du bloc `methodPointers`) -> `is_active` la mirrore, mais
    # `active_condition_ported` reste FALSE (les deux membres du OR n'ont pas la meme surete de
    # mesure -- cf. l'en-tete du module).
    "RitesOfMorkai_ExtraDamage": RitesOfMorkaiExtraDamageEffect,
    # 1115 InescapableAccuracy_extraCritChance (case-366-r1) : volet CHANCE DE CRIT du passif
    # `InescapableAccuracy` (TriggeredAbilityType 0x45b = 1115) d'`eldarMauganRa`.
    # `InescapableAccuracyAbility$$CreateBehaviour` pose les TROIS effets d'un bloc sur l'Owner
    # (`AddEffect(0x45b) + AddEffect(0x45c) + AddEffect(0x45d)`, `turns = NULL` -> PERMANENTS).
    # TROIS classes natives et non une, tranche par le SLOT `Il2CppClass*` : les fabriques
    # `EffectsDatabase.<>c$$<InitializeEffects>b__14_141/142/143` allouent depuis TROIS slots
    # DIFFERENTS puis appellent le MEME corps de `$$.ctor` (dedup IL2CPP d'un corps bit-identique --
    # le nom du ctor ne dit donc RIEN de l'identite de classe). DEUX chemins portes ici :
    #   `...InescapableAccuracy_ExtraCritChanceEffect$$CreateCritChanceBonus`
    #       = ForAddition(get_OwnerIsCaster & IsRangedAttack, ConfigVar(0x41 = extraCritChance))
    #   `...InescapableAccuracy_ExtraCritDamageEffect$$CreateCritDamageBonus`
    #       = ForAddition(get_OwnerIsCaster & IsRangedAttack, ConfigVar(0x42 = extraCritDmg))
    #   + `CreateActiveCondition` (corps PARTAGE par les trois) = NOT HasFlag(Owner, 0 = UnitFlag.Moved).
    # N'HERITENT RIEN de leur voisin 1222 : pas de `IsNormalAttack`, pas d'`AmountIsGreaterThanZero`,
    # et le gate d'attaque est l'INVERSE (RANGED). Les DEUX canaux sont distincts (1115 ->
    # `RollCritical` = SI le coup crite ; 1116 -> `CalculateCriticalDamage` = de COMBIEN).
    # ⚠ Asymetrie de config, relue : `variablesAffectedByRarityBonus == ["extraCritDmg"]` -- seul
    # 1116 est scale par le multiplicateur de rarete du porteur.
    # 1117 InescapableAccuracy_overrideHits -- le TROISIEME volet, porte depuis case-366-r1/1117 :
    #   `...InescapableAccuracy_OverridHitsEffect$$CreateBlockHitReductionTrigger`
    #       = get_OwnerIsCaster & IsRangedAttack        (trigger NU : aucun `EffectBonus`, donc
    #                                                    AUCUNE variable de config, donc rien a
    #                                                    scaler par la rarete)
    # Consommateur : `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction` ->
    # `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`, qui SAUTE la liste des bonus de
    # coups a `addition < 0` quand le flag est arme. Ce n'est donc PAS un terme de somme mais un
    # INTERRUPTEUR de l'axe COUPS -- cable dans `services.attack_hits_formula` (foyer PARTAGE
    # combat/prediction : `AttackDamageOperation$$GetAttackHits` delegue au slot 0xb6 de
    # `BattleQuery`, qui delegue a `DamagePrediction$$GetAttackHits`).
    "InescapableAccuracy_extraCritChance": InescapableAccuracyExtraCritChanceEffect,
    "InescapableAccuracy_extraCritDmg": InescapableAccuracyExtraCritDamageEffect,
    "InescapableAccuracy_overrideHits": InescapableAccuracyOverrideHitsEffect,
    # 1578 EmpyricAmbush (#589-r1-r1) : la MARQUE que `EmpyricAmbushAbility$$ExecuteBehaviour` pose
    # sur la CIBLE de l'ability active d'`eldarLhykhis` -- `AddEffect(0x62a, <abilityStateRef>,
    # source = Owner@DSLSelectors+0x30, targets = Target@+0x60, turns = <DSLFormulas+0x20> =
    # Direct(1))`, donc UN tour. La classe porte DEUX canaux, meme trigger a la variable pres :
    #   `EmpyricAmbushEffect$$CreateCritChanceBonus`
    #       = ForAddition(get_OwnerIsTarget & IsValidAttackForBuff(), ConfigVar(0x41 = extraCritChance))
    #   `EmpyricAmbushEffect$$CreateCritDamageBonus`
    #       = ForAddition(get_OwnerIsTarget & IsValidAttackForBuff(), ConfigVar(0x42 = extraCritDmg))
    # `get_OwnerIsTarget` = le PORTEUR est le DEFENSEUR -- c'est le premier implementeur des canaux
    # CRIT qui ne vive pas sur l'attaquant, et c'est ce qui a impose l'elargissement du balayage a
    # `board_effect_carriers` (cf. `entities/effects/__init__.py`).
    # `IsValidAttackForBuff` porte SEPT noeuds dont le sujet est `Caster@DSLSelectors+0x48` (le
    # caster de l'ATTAQUE, pas le porteur) : AreEnemies(Caster, Target) & (HasFaction(Caster,
    # Aeldari) | TilesMovedThisTurn(Caster) >= GetNumberConstant(0x51 = movement)) &
    # (AreFriends(Caster, EffectSource) & NOT AreEqual(Caster, EffectSource) & HasTrait(Caster, Hero)).
    # Le seuil `movement` = 4 est RELU du gameconfig, jamais code en dur -- c'est le seul des six
    # consommateurs de `DSLFormulas$$TilesMovedThisTurn` qui echappe a la borne saturante de #589.
    # ⚠ Config lue = l'ability ACTIVE 1232 (`mov edx, 0x4d0` + surcharge `set_ActiveAbility` de
    # `AbilityOrEffect$$op_Implicit`, relue byte a byte), PAS l'EffectType 1578.
    "EmpyricAmbush": EmpyricAmbushEffect,
    # 1429 EuphoricStrikes_ExtraCrit (#522) : la MARQUE que `EuphoricStrikesAbility$$ExecuteBehaviour`
    # pose sur la CIBLE de l'ability active d'`emperExultant` (« Laviscus ») -- `AddEffect(0x595,
    # <abilityStateRef>, source = Caster@DSLSelectors+0x48, targets = Target@+0x60,
    # turns = <DSLFormulas+0x20> = Direct(1))`, donc UN tour. UN SEUL canal (le build ne porte que
    # `$$CreateCritChanceBonus`, `$$CreateRemoveEffectTrigger` et `$$.ctor` pour cette classe) :
    #   `EuphoricStrikes_ExtraCritEffect$$CreateCritChanceBonus`
    #       = ForAddition(get_OwnerIsTarget
    #                       & AmountIsGreaterThanZero(StatAmount(Caster@+0x48, 0x9 = CritChance,
    #                                                            0 = Current, null, 0)),
    #                     ConfigVar(0x41 = extraCritChance))
    # `get_OwnerIsTarget` = le PORTEUR est le DEFENSEUR (comme 1578), donc le balayage board-wide de
    # `board_effect_carriers` est ce qui le rend atteignable ; le SUJET du second noeud est en revanche
    # l'ATTAQUANT (`Caster@+0x48`) -- un attaquant a crit-chance nulle ne gagne RIEN.
    # ⚠ Config lue = l'ability ACTIVE 1198 (`mov edx, 0x4ae` du `$$.ctor`, relu octet a octet), PAS
    # l'EffectType 1429. `extraCritChance` est HORS `variablesAffectedByRarityBonus` -> pas de scaling.
    # Le RETRAIT (`CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget | On(0) & Target ==
    # EffectSource`) vit dans `EFFECT_TRIGGERS[1429]` : sans lui le +crit ne serait pas une CHARGE A
    # USAGE UNIQUE mais un buff de tout le tour -- regression PERMISSIVE (forme de 1550/1000).
    "EuphoricStrikes_ExtraCrit": EuphoricStrikesExtraCritEffect,
    # 1464 / 1465 DaemonicPatrons_* (#911) : les DEUX buffs que `DaemonicPatronsAbility$$
    # ExecuteBehaviour` pose sur le CASTER (`emperFlawlessBlade` « Hascule »), pour
    # `Sum(TurnsFromRounds(nrOfRounds), Const(1))` tours. Leur BASE native commune
    # `ADaemonicPatronsEffect` porte le seul etage qui les rend dynamiques :
    #     n = Count(Filter(AdjacentEnemies(Owner@0x30, unique: 1, selectionType: 3),
    #                      HasEffect(It@0x68, 27 Taunted_OnlySpecificTargets, onlyActive: 0, 6)))
    # -- les ennemis adjacents TAUNTES, pas les ennemis adjacents. La meme grandeur sert la
    # `CreateActiveCondition` (`AmountIsGreaterThanZero(n)`) et les deux magnitudes, donc elles ne
    # peuvent pas diverger ; foyer unique `runner/components.py::adjacent_taunted_enemies_count`,
    # publie sous la cle `adjacent_taunted_enemies` du `unit_state` ET des ctx de degat.
    # 1464 = `ForAddition(+extraDmg x n)` face ATTAQUANT (`get_OwnerIsCaster`, slot +0x10) ;
    # 1465 = `ForPercentIncrease(-Min(100, dmgReductionPct x n))` face DEFENSEUR
    # (`get_OwnerIsTarget`, slot +0x08 a montant NEGATIF -- le natif n'appelle PAS ForPercentDecrease).
    "DaemonicPatrons_ExtraDamage": DaemonicPatronsExtraDamageEffect,      # 1464, #911
    "DaemonicPatrons_DmgReduction": DaemonicPatronsDmgReductionEffect,    # 1465, #911
    # 1522 TheLionsWrath_ExtraCritChance (#889) : le buff que `darkaBossLion` pose sur LUI-MEME au
    # cast de son active 1217 -- `AddEffect(0x5f2, <abilityStateRef>, targets = Owner@DSLSelectors
    # +0x30, turns = null)`, surcharge a CINQ arguments (pas de `source`). UN SEUL canal (le build ne
    # porte que `$$CreateCritChanceBonus` et `$$.ctor` pour cette classe -- ni CritDamage, ni
    # `CreateRemoveEffectTrigger`) :
    #   `TheLionsWrath_ExtraCritChanceEffect$$CreateCritChanceBonus`
    #       = ForAddition(get_OwnerIsCaster
    #                       & AmountIsEqual(CurrentHitIndex(), <DSLFormulas+0x20> = Direct(1)),
    #                     ConfigVar(0x3a = chance))
    # `get_OwnerIsCaster` = le porteur est l'ATTAQUANT (symetrique de 1429, porte par le DEFENSEUR).
    # ⚠ La variable est `chance` (0x3a = 58), **PAS** `extraCritChance` (0x41 = 65) : c'est celle-ci
    # que lit `1216 MartialExemplar`, l'AUTRE active du meme boss. L'ordinal seul ne l'aurait pas dit.
    # `chance` = 100 a tous les niveaux et `nrOfHits = 2` -> le SECOND coup crite par construction.
    # Le RETRAIT n'est pas un `EFFECT_TRIGGERS` : la PHASE 2 (`TheLionsWrath_PendingAttackAbility$$
    # CreateBehaviour`) finit par `RemoveEffect(Owner@+0x30, Nullable(0x5f2))`, HORS de son `If`.
    "TheLionsWrath_ExtraCritChance": TheLionsWrathExtraCritChanceEffect,
    # 1520 MartialExemplar_ExtraCritChance (#889-r5) : le buff que `darkaBossLion` pose sur LUI-MEME
    # au cast de son AUTRE active, 1216 -- `AddEffect(0x5f0, <abilityStateRef>, targets =
    # Owner@DSLSelectors+0x30, turns = <DSLFormulas+0x20> = Direct(1))`, meme surcharge a CINQ
    # arguments que 1522 ci-dessus mais duree **1 TOUR** au lieu de `null`. UN SEUL canal (le build
    # ne porte que `$$CreateCritChanceBonus` et `$$.ctor` -- ni CritDamage, ni RemoveEffectTrigger) :
    #   `MartialExemplar_ExtraCritChanceEffect$$CreateCritChanceBonus`
    #       = ForAddition(get_OwnerIsCaster & HasTrait(Target@DSLSelectors+0x60, 0x2 = Summon),
    #                     ConfigVar(0x41 = extraCritChance))
    # ⚠ DEUX pieges d'ordinal sur cette seule ligne : (a) `0x41 = extraCritChance` et NON `0x3a =
    # chance`, la variable de 1217 -- deux actives du MEME boss, deux variables voisines, et
    # l'ordinal seul ne les separe pas ; (b) `1520` est AUSSI `TriggeredAbilityType.
    # TheLionsWrath_PendingAttack` -- c'est l'`AddEffect` (2e argument = `EffectType`) qui fixe
    # l'enum ici. Le predicat porte sur le trait du DEFENSEUR (`tgt_traits`), unique dans le depot.
    "MartialExemplar_ExtraCritChance": MartialExemplarExtraCritChanceEffect,
    # 1460 AmuletOfTheVoidwyrm_CritDamageReduction (#589-r1-r1-r2-r1) : owner-effect PERMANENT de la
    # RELIQUE `AmuletOfTheVoidwyrm`, pose a l'init par la base `IdunBattle.Entities.Abilities.
    # AOwnerEffectTriggeredAbility$$CreateBehaviour` (`If(<trig>, AddEffect(GetEffectType() = 0x5b4,
    # AbilityState(Owner, <cette ability>), source = Owner, targets = Owner, turns = <zeroe>))`) sur
    # le trigger `OnOwnerSpecificAbilityInit`. UN seul canal, et c'est le premier `ForSubtraction` de
    # l'axe crit-DEGAT :
    #   `...AmuletOfTheVoidwyrm_CritDamageReductionEffect$$CreateCritDamageBonus`
    #       = ForSubtraction(get_OwnerIsTarget,            <- trigger NU, aucun op_BitwiseAnd
    #                        Multiply(ConfigVar(0x97 = critDmgReduction),
    #                                 GetAdjacentFriendlySummonsAndDecoysCount()))
    #   + `CreateActiveCondition` = AmountIsGreaterThanZero(<le MEME compteur>)
    # ⚠ TROIS enums, deux a 1460 : `EffectType` 0x5b4 = 1460 est CET effet, mais sa CONFIG est la
    # TRIGGERED 0x5b8 = **1464** `AmuletOfTheVoidwyrm` (`.ctor` relu octet a octet : `mov edx, 0x5b8`
    # + la surcharge d'`AbilityOrEffect$$op_Implicit` qui appelle `set_TriggeredAbility`) -- tandis
    # que `TriggeredAbilityType` 1460 est `TalismanOfRage`, une AUTRE relique.
    # ⚠ Le niveau lu est celui de l'`AbilityState` TERTIAIRE du porteur (relique EQUIPEE), via le
    # foyer `triggered_ability_state` de #357 : `ability_level` (le passif, 50 en runner normalise)
    # rendrait TOUJOURS le dernier palier.
    "AmuletOfTheVoidwyrm_CritDamageReduction": AmuletOfTheVoidwyrmCritDamageReductionEffect,
    # 1468 SupaCyborkBody_CritDmgReduction (#503-r4) : owner-effect du passif `SupaCyborkBody`, JUMEAU
    # DE FORME de 1460 juste au-dessus -- meme canal `CreateCritDamageBonus`, meme `ForSubtraction`,
    # meme trigger `get_OwnerIsTarget` NU, meme cle `ConfigVar(0x97 = critDmgReduction)` :
    #   `...SupaCyborkBody_CritDmgReductionEffect$$CreateCritDamageBonus`
    #       = ForSubtraction(get_OwnerIsTarget,
    #                        Multiply(ConfigVar(0x97), EffectLevel(Effect@+0x38)))
    #   + `CreateActiveCondition` = HasAdjacentEnemies(Owner, Tiles(Owner))
    #   + `GetCalculateLevel`     = Count(AdjacentEnemies(Owner, 1, 3))   <- CE niveau-la
    # La SEULE difference de structure : le 2e facteur du `Multiply` est une LECTURE du niveau
    # STOCKE (`EffectComponent+0x68`), que `RefreshEffectsOperation$$UpdateLevel` tient egal a
    # `GetCalculateLevel` -- d'ou le compteur porte, cf. `adjacent_enemies_count`.
    # ⚠ CONFIG = la TRIGGERED `0x5c3 = 1475 SupaCyborkBody`, litteral du `.ctor` relu A
    # L'ASSEMBLEUR (`ba c3 05 00 00`), PAS l'`EffectType` 1468 -- meme piege que 1460/1464.
    # SON ABSENCE ETAIT PERMISSIVE ET SILENCIEUSE : mesuree sur le tir differe `1237` (#503-r4),
    # elle valait 1736 PV de trop sur une cible a 12049 PV (le port la TUAIT, le natif non).
    "SupaCyborkBody_CritDmgReduction": SupaCyborkBodyCritDmgReductionEffect,
    # 1457/1458 RelicBoltPistol_{ExtraPierce,ExtraCritDamage} (#910) : les DEUX owner-effects
    # PERMANENTS de la relique `RelicBoltPistol` (`R_Crit_RelicBoltPistol`, 7 porteurs `lineup`),
    # poses d'un bloc et INCONDITIONNELLEMENT par `IdunBattleLogic.Entities.Abilities.Triggered.
    # Loki.RelicBoltPistolAbility$$CreateBehaviour` = `AddEffect(0x5b1, .., source = targets =
    # Owner@+0x30, options = <zeroe>) & AddEffect(0x5b2, .., idem)`.
    #   `...RelicBoltPistol_ExtraPierceEffect$$CreatePiercingBonusForAttack`
    #       = ForAddition(get_OwnerIsCaster & IsMeleeAttack,
    #                     If(HasTrait(Target@+0x60, 0x3ee = 1006 Xenos)
    #                        | HasTrait(Target@+0x60, 0x7ea = 2026 Chaos),
    #                        Multiply(ConfigVar(0x3f = extraPierceRatio), <DSLFormulas+0x28>),
    #                        ConfigVar(0x3f = extraPierceRatio)))
    #   `...RelicBoltPistol_ExtraCritDamageEffect$$CreateCritDamageBonus`
    #       = le MEME corps avec `IsRangedAttack` et `ConfigVar(0x42 = extraCritDmg)`
    # ⚠ TROIS enums, DEUX collisions : `TriggeredAbilityType` 1457 = `KardiocoreGalvanus` et
    # 1458 = `PhoenixGem` (deux AUTRES reliques), `EffectType` 1467 = `SelfRepairMechanism`. La
    # CONFIG des deux effets est la TRIGGERED `0x5bb = 1467 RelicBoltPistol`, litteral du `.ctor`
    # PARTAGE relu a l'assembleur (`ba bb 05 00 00`) -- meme piege que 1460/1464 et 1468/1475.
    # ⚠ `<DSLFormulas+0x28>` = `Direct(2)` est une MAGNITUDE (branche d'un `If`), PAS un gate :
    # sans le trait d'alliance le bonus vaut `cv`, il ne disparait pas.
    "RelicBoltPistol_ExtraPierce": RelicBoltPistolExtraPierceEffect,
    "RelicBoltPistol_ExtraCritDamage": RelicBoltPistolExtraCritDamageEffect,
    # 1090 Ramshackle_DmgReduction (#570-r1) : owner-effect PERMANENT du passif `Ramshackle`, seul
    # passif du summon `orksGrotTank`. #570 avait NOMME ce trou -- le tank arrivait avec ses stats,
    # ses traits et ses armes, et SANS sa reduction de degat : ecart PERMISSIF (il encaisse plus
    # qu'il ne devrait) et SILENCIEUX (aucun test ne peut distinguer « le tank meurt » de « le tank
    # meurt trop vite »).
    #   `...Ramshackle_DmgReductionEffect$$CreateDamageModifier`
    #       = ForAddition(get_OwnerIsTarget
    #                       & AmountIsEqualOrGreater(ConfigConst(0x49 = pierceRatio),
    #                                                AttackPiercingRatio()),
    #                     Multiply(ConfigVar(0x12 = dmgReduction), Direct(-1)@DSLFormulas+0x38))
    # SENS DU GATE, LU dans `AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` (`return <+0x20>
    # <= <+0x18>`) : `pierceRatio >= percage du profil` = « les profils a percage FAIBLE ».
    # ⚠ CONFIG = la TRIGGERED `0x445 = 1093 Ramshackle`, litteral du `.ctor` relu A L'ASSEMBLEUR
    # (`ba 45 04 00 00`) -- et `EffectType` 1093 est `HolyDuel_DmgReduction`, une AUTRE chose.
    "Ramshackle_DmgReduction": RamshackleDmgReductionEffect,
    # 1175 HatefulAssault_AlreadyAttacked (case-366-r1) : MARQUEUR pose par
    # `...HatefulAssaultAbility$$CreateBehaviour` sur l'ennemi qu'il vient de frapper, et LU par le
    # `CreateTrigger` de cette meme ability (`NOT HasEffect(Actor, 0x497, onlyActive=0, Both)`) -- ce
    # qui borne l'attaque d'opportunite a UNE fois par ennemi et par tour. La classe native est la
    # GENERIQUE `UntilOfEndTurnEffect` (slot `Il2CppClass*`, cf. `probe_1175 --step 1`), zero
    # contribution : toute sa semantique est sa DUREE, portee par `EFFECT_TRIGGERS[1175]`.
    # ⚠ Cette entree ne change RIEN au comportement par elle-meme (`BaseEffect` no-op est identique) --
    # elle documente l'identite de classe et fait passer 1175 du cote « porte » de l'inventaire #366.
    "HatefulAssault_AlreadyAttacked": UntilOfEndTurnEffect,
    # 1174 StructuralAnalyser_Visual (case-366-r1) : volet PORTEUR du passif de `tauDarkstrider`,
    # pose d'un bloc avec `1156 StructuralAnalyserDmgBoost` par
    # `...StructuralAnalyser_AddDamageBuffAbility$$CreateBehaviour` (`AddEffect(0x484)+AddEffect(0x496)`).
    # SOEUR de 1156 sous `AStructuralAnalyserEffect`, PAS sa fille (classes.tsv) : elle cible `Owner`
    # (MESURE : `ReceiveEffect e=<porteur>` contre `e=<allie>` pour 1156) et ne porte AUCUN canal --
    # prediction native IDENTIQUE actif/inactif sur cible Markerlightee ([18428-27640] des deux cotes).
    # Toute sa semantique est sa `CreateActiveCondition` = `AmountIsGreaterThanZero(AdjacentFriends
    # + UnitsFromFaction(SurroundingFriends(2), Tau))`, portee par `is_active`.
    # ⚠ Cette entree ne change RIEN au comportement par elle-meme (`BaseEffect` no-op est identique) --
    # elle fixe l'identite de classe (interdire d'heriter le +extraDmg de 1156 au porteur) et fait
    # passer 1174 du cote « porte » de l'inventaire #366. `1156` reste NON porte (cas [opus] du kit Tau).
    "StructuralAnalyser_Visual": StructuralAnalyserVisualEffect,
    # 1291 HeavyGravCannon : owner-effect du PASSIF homonyme d'admecDestroyer <<Sy-Gex>>. Classe DEDIEE
    # `IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect` a DEUX canaux partageant UNE condition
    # (`...$$DamageCondition` = OwnerIsActor & IsRangedAttack & (HasTrait(target,5=Mechanical) |
    # HasTrait(target,0x3f5=1013 MkXGravis) | HasTrait(target,0x40f=1039 TerminatorArmour))) :
    #   `...$$CreateEffectDamageBonusForAttack`  = ForAddition(cond, ConfigVar(8=extraDmg))     -> flat
    #   `...$$CreatePiercingBonusForAttack`      = ForPiercing(cond, ConfigVar(0x3f=extraPierceRatio))
    # ⚠ Le nom est un HOMONYME a TROIS faces : EffectType 1291 = HeavyGravCannon (CETTE cle, le nom capte
    # live), TriggeredAbilityType 1233 = HeavyGravCannon (la config lue via l'AbilityOrEffect 0x4d1 du
    # ctor), TriggeredAbilityType 1291 = SelfRepairMechanism (aucun rapport).
    "HeavyGravCannon": HeavyGravCannonEffect,
    # KanOpener -- les DEUX noms d'EffectType sont TRANCHES depuis #366/#371, et l'inscription reste
    # VOLONTAIREMENT non faite : `1102 KanOpener_IgnoreArmor` (classe propre, celle qu'ecrit
    # `KanOpenerEffect` ci-dessus) et `1103 KanOpener_ReduceArmor` (instance generique
    # `StaticStatModifierEffect`, `IdunBattleLogic.Entities.Abilities.Triggered.Loki.KanOpenerEffect$$
    # CreateTargetTriggerBehaviour` = `AddStaticStatModifierEffect(<cible>, 0x44f, stat = 0x10
    # FIXED_ARMOR, -ConfigVar(0x30 = armorReduction), turns = NULL)` -> PERMANENT et NEGATIF).
    # L'ability existe au gameconfig mais a **0 porteur** sur les 5 voies (`unit_map find --ability
    # KanOpener` = 0 unites) : aucun effet ne peut donc apparaitre dans `decisionView.effects`, et une
    # inscription serait un port qu'aucun montage n'exerce. Cf. `docs/rl/case-371-g1-static-stat-modifier.md`.
}


# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait — dict TraitType -> List<EffectType>
# des owner-effects AJOUTÉS au porteur À LA CRÉATION D'UNITÉ (`InitializeActorAbilitiesOperation.Execute`
# IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute, boucle TRAITS). Dict peuplé par `Trait..idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor (static field +0x30). 4 entrées LUES
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
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait — pour un trait, la LISTE des
    noms d'EffectType à ajouter à son porteur à la création (dict `Trait..idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor +0x30). Trait
    sans owner-effect -> [] (le natif renvoie null)."""
    return TRAIT_OWNER_EFFECTS.get(trait_name, [])


# --- Chemin ABILITY-DÉRIVÉE (distinct des 2 dicts owner-effect directs) : un trait DÉRIVE une ability, et
# c'est le `CreateBehaviour` de cette ability qui pose l'owner-effect à SON init. (RE re-expert : BigTarget.)
#
# ⚠ NE PAS confondre avec `GetEffectToBeAddedToOwnerForAbility` (dict `ActiveAbility` +0x50) : celui-ci ne
# contient QUE {PlasmaCannon->PlasmaCannon_Visual, GravitonRifle->GravitonRifle_ExtraPierce} (armes joueur,
# aucun summon concerné) -> non porté. BigTarget passe par LE CHEMIN CI-DESSOUS.
#
# Étape 1 — `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` (appelé par `AddTraitOperation.Execute
# IdunBattle.Operations.AddTraitOperation$$Execute+0xd1`) : à la création, un trait dérive une ability via `Trait.GetTriggeredAbility` (dict Trait +0x0
# idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility) / `GetActiveAbility` (dict Trait +0x8 idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetActiveAbility) et l'ajoute à l'unité. Clés = NOM trait
# gameconfig. Seul BigTarget est porté (chaîne complète RE'd + effet modélisé) ; les autres traits summon
# dérivent aussi une ability (Synapse 0x423, ShadowInTheWarp 0x424, InstinctiveBehaviour 0x413, BattleFatigue
# 0x401) MAIS on n'a PAS lu si leur CreateBehaviour pose un owner-effect -> non portées (fidélité-safe).
TRAIT_DERIVED_ABILITIES: dict[str, list[str]] = {
    "BigTarget": ["BigTarget"],     # UnitTrait.BigTarget 0x3f9=1017 -> ability 0x406=1030 (dict Trait +0x0)
    # ShadowInTheWarp 0x3f9+... 2025 -> ability derivee 0x424 = ShadowInTheWarp_AddEffectAbility (pattern
    # generique _AddEffectAbility : base CreateBehaviour pose constants.effectType au porteur).
    "ShadowInTheWarp": ["ShadowInTheWarp"],
    # Daemon (trait 0x3fb=1019) -> ability derivee "Daemon" dont l'init pose Daemon_ExtraBlock (MESURE
    # live #202-C, cascade spawn Pink Horror/Screamer runner 183 : groupe 21 src=Daemon -> groupe 22
    # Daemon_ExtraBlock, BlockChance +25 / BlockDamage +449 = 50% Attack). Sans ce seed, un summon
    # Daemon spawne offline n'a AUCUN block (gap corrige).
    "Daemon": ["Daemon"],
    # Terrifying (trait 0x22=34, x39 carriers dont 11 lineup) -> triggered ability derivee 0x62 (dict
    # GetTriggeredAbility +0x0 idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor, lu par idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility). Chaine RE'd #73 :
    # IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities ajoute `TerrifyingAbilityAbility` IdunBattleLogic.Entities.Abilities.Active.TerrifyingAbilityAbility$$.ctor (= AOwnerEffectSpecific-
    # TriggeredAbility(0x62)) ; son IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger = OnOwnerSpecificAbilityInit(0x62) pose l'effet
    # Terrifying_ExtraDefense (0x62) sur le porteur a l'init. Les 11 lineup captent l'effet live (decisionView)
    # -> seed idempotent (no-op sur eux) ; AUCUN carrier SUMMON (28 npc + 0 summons) -> spawn path sans porteur
    # spawnable a ce jour (validation function-level, cf. tests/.../test_summon_trait_effects_live).
    "Terrifying": ["TerrifyingAbility"],
    # Diminutive (trait 0x408=1032) -> triggered ability derivee 0x43f=1087 (dict Trait +0x0, lu par
    # `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility`). `DiminutiveAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.DiminutiveAbility$$.ctor =
    # `AOwnerEffectSpecificTriggeredAbility(0x43f)` IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$.ctor ; `IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger` =
    # `OnOwnerSpecificAbilityInit(0x43f)` -> pose l'owner-effect a l'init. MEME patron que Terrifying
    # (#73). Carrier SUMMON `orksGrot` (summone par `orksRuntherd` SquigHound/GetEmRuntz, tous deux
    # dans le pool) -> chaine CONFRONTABLE live, contrairement a Terrifying. #75.
    "Diminutive": ["DiminutiveAbility"],
}

# Étape 2 — owner-effects posés par `<Ability>.CreateBehaviour` À L'INIT de l'ability (DSL `AddEffect(owner)`).
# Table par NOM d'ability (chaque entrée = VA du CreateBehaviour source).
ABILITY_INIT_OWNER_EFFECTS: dict[str, list[str]] = {
    # `RamshackleAbility` (TriggeredAbilityType 0x445 = 1093, parent `IdunBattle.Entities.Abilities.
    # AOwnerEffectTriggeredAbility` d'apres `classes.tsv`) : la base pose l'owner-effect a l'init du
    # porteur, `turns = <zeroe>` -> PERMANENT. `$$GetEffectType` a pour corps ENTIER `return 0x442`
    # (= 1090), donc l'appariement ability -> effet est LU, pas devine. Seul porteur du kit : le
    # summon `orksGrotTank` / npc `orksNpc3GrotTank` (#570-r1).
    "Ramshackle": ["Ramshackle_DmgReduction"],
    "BigTarget": ["BigTarget_AdjacentEffect"],   # `IdunBattleLogic.Entities.Abilities.Active.Loki.BigTargetAbility$$CreateBehaviour : AddEffect(0x402)
    # `ShadowInTheWarp_AddEffectAbility` (base `AddEffectAbility.CreateBehaviour`) : AddEffect(0x41d=1053).
    "ShadowInTheWarp": ["ShadowInTheWarp_LessDmg_Effect"],
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandAbility$$CreateBehaviour : AddEffect(0x458=1112 ExtraDmg) + AddEffect(0x453=1107
    # ExtraCrit). AURA rayon 2 aux allies : +Attack (cf. loki.PathOfCommandExtraDmgEffect) et +CritChance
    # (cf. loki.crit_aura.PathOfCommandExtraCritEffect, #373). Ces owner-effects sont
    # poses a l'INIT de l'ability = a l'ATTERRISSAGE pour un deep-strike (deferres pendant TeleportingIn ;
    # ground truth live ds_landing : absents au teleport-in, apparaissent au landing -- l'event stream de
    # l'atterrissage porte les DEUX `Effect_Refresh`, dans cet ordre : 1107 puis 1112).
    "PathOfCommand": ["PathOfCommand_ExtraCrit", "PathOfCommand_ExtraDmg"],
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility$$CreateBehaviour : `AddEffect(0x564=1380, owner, owner)` -> le
    # HP-floor est posé sur le PORTEUR à l'init de l'ability passive (owner-effect self, aucun sélecteur). G6a.
    "HypersensoryAbilities": ["HypersensoryAbilities_MinimalHealth"],
    # Ability derivee du trait Daemon : pose Daemon_ExtraBlock (1034) sur le porteur a l'init (#202-C,
    # mesure live — block 25% / 50% Attack, deja porte via DaemonExtraBlockEffect).
    "Daemon": ["Daemon_ExtraBlock"],
    # TerrifyingAbility (triggered 0x62 derivee du trait Terrifying) : `AOwnerEffectSpecificTriggeredAbility`
    # (0x62) CreateBehaviour = AddEffect(owner, Terrifying_ExtraDefense 0x62) a l'init du porteur -> -30%
    # (globalValues.terrifyingBonus) degat MELEE recu (defender, gate IsMeleeAttack). Chaine RE'd #73.
    "TerrifyingAbility": ["Terrifying_ExtraDefense"],
    # DiminutiveAbility (triggered 0x43f=1087 derivee du trait Diminutive) :
    # `AOwnerEffectSpecificTriggeredAbility(0x43f)` — CreateBehaviour = AddEffect(owner,
    # Diminutive_HitReduction) a l'init du porteur -> -1 coup sur TOUTE attaque recue, plancher 1
    # (`Diminutive_HitReductionEffect..IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$.ctor / hits IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack). Chaine RE'd #75.
    "DiminutiveAbility": ["Diminutive_HitReduction"],
    # InfernalPacts (passif Abraxas, #202-B) : effet-AURA 0x4ae=1198 AUTO-PORTEUR (enregistré par
    # `EffectsDatabase.<InitializeEffects>b__14_225`, AUCUNE classe Ability — pas de CreateBehaviour à citer).
    # Seed = filet pour les états non captés (Abraxas lineup est normalement couvert par decisionView).
    "InfernalPacts": ["InfernalPacts_AdditionalHits"],
    # AnvilShield (passif d'Arjac spaceRockfist) — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    # AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour` pose DEUX owner-effects a
    # l'init (`AbilityBehaviour.op_Addition` des deux `AddStaticStatModifierEffect`). Seul 0x4b0=1200 est
    # inscrit ici : il est INACTIF au-dessus de 35 % PV, donc ABSENT du seed live (`decisionView.effects`
    # n'expose que les ACTIFS — GROUND TRUTH #100) alors que 1202 y est TOUJOURS (inconditionnel, deja
    # capte). Sans ce seed, le gate `HasEffect(Arjac, 1200)` d'`ApplyStun` serait mort dans tout runner
    # demarrant Arjac a pleins PV. Idempotent : si Arjac demarre sous 35 %, l'effet est deja capte -> skip.
    "AnvilShield": ["AnvilShield_BlockChanceBelowHealthCap"],
    # LionHelm (passif d'Azrael darkaAzrael, TriggeredAbilityType 1163) —
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LionHelmAbility$$CreateBehaviour` pose TROIS
    # effets sur le PORTEUR (`AddEffect(1193, targets=Owner)` + 2 `AddDynamicStatModifierEffect(
    # targets=Owner, ...)`), tous INCONDITIONNELS -> tous CAPTES par `decisionView.effects` sur un
    # runner frais (verifie live). Le seed reste un filet (idempotent).
    "LionHelm": ["LionHelm_ExtraDmg", "LionHelm_ExtraBlockChance", "LionHelm_ExtraBlockDamage"],
    # FearedInterrogator (passif d'Asmodai darkaAsmodai, TriggeredAbilityType 1235) —
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FearedInterrogatorAbility$$CreateBehaviour`
    # pose les DEUX effets sur le PORTEUR (`AddEffect(1294, source=Owner, targets=Owner)` &
    # `AddEffect(1295, source=Owner, targets=Owner)`) ; verifie live chez Asmodai, RIEN chez les cibles.
    "FearedInterrogator": ["FearedInterrogator_Owner", "FearedInterrogator_Target"],
    # HammerOfWrath (actif de Mataneo `bloodIntercessor`) — la triggered DERIVEE 1258
    # `HammerOfWrath_ConditionalDamage` est un `AOwnerEffectTriggeredAbility` : son `CreateBehaviour`
    # (corps de BASE, `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour`) =
    # `If(<cond>, AddEffect(0x534, AbilityState(owner), owner, owner, <duree ZEROE>))` sur le trigger
    # `OnOwnerSpecificAbilityInit` -> owner-effect PERMANENT du porteur. Comme `AnvilShield_
    # BlockChanceBelowHealthCap`, il est INACTIF au-dessus de healthPct (=50 %) donc ABSENT du seed
    # live (`decisionView.effects` n'expose que les ACTIFS) : sans ce seed, le gate `HasEffect(Mataneo,
    # 1332)` du node de degat serait mort dans tout runner ou Mataneo tombe sous 50 % APRES la capture.
    # Idempotent (skip si deja capte). Cle = le NOM d'ability gameconfig du porteur.
    "HammerOfWrath": ["HammerOfWrath_ConditionalDamage"],
    # ModifiedExoarmour (passif de `votanChampion` << Kimm >>, TriggeredAbilityType 0x5f9=1529) —
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ModifiedExoarmourAbility$$CreateBehaviour`
    # = `AddEffect(0x607) & AddEffect(0x608)` : les DEUX effets sont poses sur le porteur a l'init.
    # Seul 0x608=1544 est inscrit ici : son `CreateActiveCondition`
    # (`AmountIsGreaterThanZero(TilesMovedThisTurn)`) le laisse INACTIF tant que l'unite n'a pas
    # bouge, donc ABSENT du canal `decisionView` par DEFAUT — MESURE live sur la fixture #312 :
    # `1543 ModifiedExoarmour_PierceReduction` est publie des le deploiement, `1544` seulement avec
    # `includeInactive`. 1543 est inconditionnel et toujours capte -> pas besoin de le seeder.
    # MEME motif exact qu'`AnvilShield_BlockChanceBelowHealthCap` et
    # `HammerOfWrath_ConditionalDamage` ci-dessus. Idempotent (skip si deja capte). case-322.
    "ModifiedExoarmour": ["ModifiedExoarmour_ExtraDmg"],
    # VisionsOfHeresy (passif de `bloodDeathCompany` <<Lucien>>, TriggeredAbilityType 0x4f0=1264) —
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour`
    # pose les DEUX owner-effects a l'init (`AbilityBehaviour.op_BitwiseAnd` de deux
    # `AddStaticStatModifierEffect(Owner, ...)`, `turns = NULL` donc PERMANENTS). Les DEUX portent la MEME
    # `CreateActiveCondition` (`HealthPctIsBelowOrEqual(Owner, ConfigConst(0x4f=healthPct)=50)`) : aucun des
    # deux n'est publie par `decisionView.effects` tant que Lucien est au-dessus du seuil (canal ACTIF-ONLY,
    # GROUND TRUTH #100). Sans ce seed, le +extraPierceRatio n'apparaitrait JAMAIS dans un runner qui
    # demarre Lucien a pleins PV et le fait descendre en cours de bataille. MEME motif exact
    # qu'`AnvilShield_BlockChanceBelowHealthCap` / `HammerOfWrath_ConditionalDamage` ci-dessus.
    # Idempotent (skip si deja capte). case-366-r1.
    "VisionsOfHeresy": ["VisionsOfHeresy_ExtraPierceMelee", "VisionsOfHeresy_ExtraPierceRanged"],
    # CamoCloak (passif d'`ultraEliminatorSgt` <<Certus>> et du summon `ultraSmnEliminator`,
    # TriggeredAbilityType 0x3eb=1003) -- `IdunBattleLogic.Entities.Abilities.Active.Loki.
    # CamoCloakAbility$$CreateBehaviour` est un `AddEffect(0x3f6, AbilityStateReference, Owner, 0)`
    # NU : aucun `If(...)`, la pose est INCONDITIONNELLE et permanente (duree 0). La
    # `CreateActiveCondition` de `1014` (`HasEffect(Owner, 0x3f5 LightCover) | IsEffectTarget(
    # Owner, 0x402 BigTarget_Adjacent)`) le laisse INERTE hors couvert, donc ABSENT du canal
    # `decisionView` par DEFAUT -- MESURE live (`probe_366_r1_camo_seed.py`, `C4_09`/4242, Certus
    # capte hors couvert) : canal DEFAUT = pas de `1014`, canal `includeInactive` = `1014` avec
    # `active: false`. INERTE, jamais ABSENT.
    # Sans ce seed, un etat charge depuis le canal par DEFAUT n'a AUCUNE instance a rallumer quand
    # la sim fait ENTRER le porteur en couvert : le port reste muet la ou le natif retire
    # `dmgReduction x mult` par coup (mesure : live 31907 contre port 32655). MEME motif exact
    # qu'`AnvilShield_BlockChanceBelowHealthCap` / `HammerOfWrath_ConditionalDamage` /
    # `ModifiedExoarmour_ExtraDmg` / `VisionsOfHeresy_*` ci-dessus. Idempotent (skip si deja
    # capte, quel que soit le canal -- `has_effect` ne filtre pas sur le flag).
    # ⚠ `active_condition_ported` reste FALSE, et c'est DELIBERE : l'instance seedee ici nait
    # `active = True` et c'est `is_active` (la condition PORTEE) qui la ferme ; le flag capte,
    # quand il existe, garde son mot a dire. Le rallumage en cours de sim est assure par le
    # SECOND `RefreshEffects(UnitPositionChanged)` du natif
    # (`operations/movement.py::refresh_effects_after_move_triggers`), pas par ce drapeau.
    # case-366-r1-camo-seed.
    "CamoCloak": ["CamoCloak_DmgReduction"],
    # PAS d'entree `"WireweaveNet"` ici, et c'est une DECISION MESUREE (case-366-r1b §7bis).
    # `1111 WireweaveNet_CounterAttack` est pourtant bien un owner-effect pose a l'init
    # (`WireweaveNetAbility$$CreateBehaviour` = `AddEffect(0x457, .., source=Owner, targets=Owner)`
    # sur `OnOwnerSpecificAbilityInit`) et INACTIF pendant le tour de son porteur -- le profil exact
    # des quatre entrees ci-dessus. DEUX raisons de ne PAS l'inscrire :
    #   1. INUTILE sur le canal COMBAT : la riposte ne peut partir que si l'instance est ARMEE, et le
    #      canal `decisionView.effects` par DEFAUT publie EXACTEMENT les effets armes. « Arme » =>
    #      « capte ». Contrairement a `AnvilShield`/`HammerOfWrath`, dont le gate `HasEffect` doit
    #      voir l'instance meme INACTIVE, ici l'instance inactive ne sert a rien.
    #   2. NUISIBLE : `spawn._seed_ability_owner_effects` lit les passives du **KIT gameconfig**
    #      (`GC.unit(vid).passiveAbilities`), pas de la MESURE -- et `UnitContext.passive_abilities`
    #      (le canal `unitAbilityStates`, tri-etat) n'est seede qu'APRES, par `_load_passive_abilities`.
    #      Un montage `--unit-stat "eldarRanger:PassiveAbilities=[]"` (le levier anti-bruit de
    #      case-366-r1) voyait donc le port materialiser 1111 sur une Calandis qui N'A PAS le passif
    #      en bataille -> riposte FANTOME, flux MT decale, et les DEUX gardes MELEE de
    #      `test_fire_and_reposition_reduce_dmg_live` au ROUGE (live 23633 vs port 21840). MEME piege
    #      que #264 (traits) et que le `seed_witness_effect` du pendant DECISION
    #      (`playbook/scene.py::_seed_condition_gated_owner_effects`).
    # RESIDU NOMME : une continuation offline qui CAPTURE pendant le tour de Calandis puis franchit
    # la frontiere de tour n'a aucune instance a armer -> pas de riposte.
    # ⚠ #570-r5 A DEPLACE UNE AUTRE CHOSE, ET CE BLOCAGE-CI EST INTACT. Ce que la tranche a hisse
    # avant la materialisation, c'est l'`AbilityState` (niveau/multiplicateur) du canal, pas la
    # LISTE des passives : `_seed_ability_owner_effects` lit toujours `GC.unit(vid).passiveAbilities`
    # et `ctx.passive_abilities` (la MESURE) est toujours seede en aval. Rouvrir ce residu demande
    # donc encore de faire lire au seed le substrat MESURE -- une modification de sa SOURCE, pas de
    # sa PLACE.
    # PAS d'entree `"StructuralAnalyser"` non plus, MEME arbitrage (case-366-r1, 1174) :
    # `...StructuralAnalyser_AddDamageBuffAbility$$CreateBehaviour` pose bien DEUX owner-effects d'un
    # bloc sur son porteur (`AddEffect(0x484 = 1156) + AddEffect(0x496 = 1174)`, `turns` VIDE donc
    # PERMANENTS), et `1174 StructuralAnalyser_Visual` est bien ETEINT par sa `CreateActiveCondition`
    # geometrique -- donc absent du canal ACTIF-ONLY. Mais son instance inactive ne sert a RIEN :
    # 1174 n'a AUCUN canal de contribution (MESURE : prediction native identique des deux cotes de la
    # bascule) et AUCUN `HasEffect(0x496)` ne le lit. L'inscrire n'apporterait donc que le risque du
    # point 2 ci-dessus (materialisation sur une unite privee du passif par `--unit-stat`).
    #
    # PAS d'entree `"MartialSuperiority"` non plus, MEME raisonnement en plus fort (case-366-r1) :
    # `1255 MartialSuperiority_Visual` est bien un owner-effect pose a l'init
    # (`MartialSuperiorityAddEffectAbility`, corps de BASE `AOwnerEffectTriggeredAbility$$
    # CreateBehaviour` = `If(Yes, AddEffect(0x4e7, .., targets=Owner, source=Owner))`) et INACTIF
    # pendant le tour de son porteur. Mais AUCUN consommateur logique ne lit 1255 (balayage
    # exhaustif de l'immediat, cf. `loki/martial_superiority.py`) : materialiser l'instance quand le
    # canal de capture ne l'a pas vue n'apporte AUCUN observable, et exposerait au piege #312
    # (le seed lit les passives du KIT gameconfig, pas de la MESURE).
}


def get_derived_abilities_for_trait(trait_name: str) -> list[str]:
    """`IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities (dicts Trait +0x0 triggered / +0x8 active) — abilities
    dérivées d'un trait à la création de l'unité. Trait sans dérivation portée -> []."""
    return TRAIT_DERIVED_ABILITIES.get(trait_name, [])


def get_owner_effects_added_on_ability_init(ability_name: str) -> list[str]:
    """Owner-effects posés par `<Ability>.CreateBehaviour` à l'INIT de l'ability (DSL AddEffect(owner)).
    Ability sans owner-effect-à-l'init porté -> []."""
    return ABILITY_INIT_OWNER_EFFECTS.get(ability_name, [])


# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility`
# — dict `ActiveAbility` +0x50 (peuplé par le `.cctor` de la même classe), lu par la boucle ABILITIES
# d'`IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` : owner-effects ajoutés au PORTEUR à
# la création parce qu'il possède l'ability (chemin DIRECT, DISTINCT du `CreateBehaviour` ci-dessus).
# CONTENU COMPLET du dict natif = 2 entrées (armes joueur) ; seule la 2ᵉ a une contribution modélisée :
#   PlasmaCannon   -> PlasmaCannon_Visual        (effet purement VISUEL -> non inscrit, aucun hook)
#   GravitonRifle  -> GravitonRifle_ExtraPierce  (0x5cc=1484, canal perçage conditionnel, #113)
ABILITY_OWNER_EFFECTS: dict[str, list[str]] = {
    "GravitonRifle": ["GravitonRifle_ExtraPierce"],   # ability 0x4b6=1206 -> effet 0x5cc=1484
}


def get_effect_to_be_added_to_owner_for_ability(ability_name: str) -> list[str]:
    """`StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility` — owner-effects qu'une ability
    ajoute à son porteur à la création de l'unité. Ability hors dict -> [] (le natif renvoie null)."""
    return ABILITY_OWNER_EFFECTS.get(ability_name, [])


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
        # FLAG `EffectComponent.IsActive @+0x5c` — LU du capté quand la source le publie.
        # Le canal live `readEffectsByUnit`/`readEffectsByTile` (frida/hooks/game/effects.ts) rend
        # `active` sur CHAQUE entrée, mais ne publie les entrées à `IsActive == 0` que sous
        # `includeInactive`. D'où la règle : clé ABSENTE -> `True` (canal par défaut = actifs seuls,
        # « présent == actif » ; c'est aussi le cas de la pose OFFLINE d'`AddEffectOperation`, dont le
        # `captured` n'a pas de clé `active` — le natif crée l'entité-effet ACTIVE et délègue l'inertie
        # à `<Effect>.CreateActiveCondition`). Clé PRÉSENTE -> on la respecte : c'est ce qui rend le
        # canal `includeInactive` EXPLOITABLE au seed. Sans cette lecture, un effet capté INERTE
        # atterrirait `active=True` et `EffectsState.active_effects` le laisserait contribuer —
        # exactement le ×0.70 fantôme que #208 a fermé.
        active = captured.get("active")
        # `StatModifierComponent` de l'entite-effet, publie champ par champ sous ses NOMS NATIFS
        # (`{StatType, Amount, ApplyCounter, IsDynamic, IsHidden}`) : c'est la magnitude que le natif
        # RELIT (`StaticStatModifierEffect$$GetStatModificationAmount` = `+0x14`), donc la seule
        # exacte pour un buff CROSS-UNITE dont `source` designe le porteur. Cf. `BaseEffect.stat_mod`
        # / `captured_stat_mod_amount`. Absent -> None, la classe retombe sur sa derivation.
        sm = captured.get("statMod")
        eff = klass(
            name=name, effect_type=captured.get("effectType"), level=captured.get("level"),
            ability_level=ability_level, active_ability_level=active_ability_level,
            remaining_turns=remaining_turns, source=captured.get("source"),
            active=(True if active is None else bool(active)),
            stat_mod=(sm if isinstance(sm, Mapping) else None),
            ability_variables_multiplier=ability_variables_multiplier)
        # `BondComponent.BondedEntityId` de l'entite-effet (#436-r1) -- le champ `+0x10` qu'ecrit
        # `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultBondEffectBuilder` et que relit
        # `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`. Pour l'effet 27
        # `Taunted_OnlySpecificTargets`, c'est l'unite QUI TAUNTE : la seule que le tauntee aura le
        # droit d'attaquer (`TargetIsAllowedForCaster`, #436).
        #
        # POSE EN ATTRIBUT D'INSTANCE, pas en champ de ctor : `BaseEffect.bonded` est un attribut de
        # CLASSE simple (sans annotation -- sinon dataclass field ecrase par l'`__init__`), et le
        # vecteur de pose OFFLINE (`AddEffectOperation.execute`) l'ecrit de la meme facon.
        #
        # TRI-ETAT, et il est LOAD-BEARING. Le capteur rend DEUX champs : `bondMeasured` (la mesure
        # a-t-elle eu lieu ?) et `bondedEntityId` (son resultat). On n'ecrit QUE si `bondMeasured is
        # True` ET que l'id est non nul :
        #   * capteur MUET (hook anterieur a #436-r1, classe `BondComponent` irresolue) -> on ne
        #     TOUCHE A RIEN, donc l'attribut de classe `None` = comportement STRICTEMENT anterieur ;
        #   * mesure faite, pas de lien (l'immense majorite des effets, qui ne sont pas des bond
        #     effects) -> `None` aussi, et c'est la MEME valeur : les deux collapsent ici sur le
        #     defaut du port, mais les distinguer reste la seule lecture correcte du canal -- un
        #     consommateur qui voudrait ECRIRE (et donc effacer) doit pouvoir les separer.
        if captured.get("bondMeasured") is True:
            bonded = captured.get("bondedEntityId")
            if bonded is not None:
                eff.bonded = int(bonded)
        # `EffectComponent+0x48` -- les CIBLES materialisees sur l'entite-effet
        # (`EffectComponent$$AddTargetId`, ecrit par `RefreshEffectsOperation$$AddTargetsToEffect`).
        # C'est la SORTIE native de tout `CreateTargetSelector` d'effet, celle que lit
        # `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffectOfType` (#366-r1-effect-targets).
        #
        # TRI-ETAT, et il est porte par le CAPTEUR lui-meme : `readEffectTargetIds` rend `null`
        # quand le champ n'a pas pu etre resolu et `[]` quand il est mesure vide. On ne recopie donc
        # QUE ce qui est une LISTE -- un `None` laisse l'attribut de classe intact (`None` = pas
        # mesure), sans jamais fabriquer un `[]` qui se lirait << aucune cible >>.
        tids = captured.get("targetIds")
        if isinstance(tids, (list, tuple)):
            eff.target_ids = [int(t) for t in tids]
        return eff

    @classmethod
    def create_many(cls, captured_list, ability_variables_multiplier: int = 100,
                    ability_level: int | None = None,
                    active_ability_level: int | None = None) -> list[BaseEffect]:
        return [cls.create(c, ability_variables_multiplier, ability_level, active_ability_level)
                for c in (captured_list or [])
                if isinstance(c, Mapping) and c.get("name")]

    @classmethod
    def effect_def(cls, effect_type: int | None = None, name: str | None = None) -> BaseEffect:
        """`IdunBattle.Core.Services.EffectsDatabase` slot 0 = `Get(EffectType)` — l'instance-DEF que le
        jeu tient PAR EffectType et qu'interrogent `IdunBattle.Core.Services.BattleQuery$$IsUnitImmuneTo`
        et le gate d'immunité d'`IdunBattle.Operations.AddEffectOperation$$Execute`.

        Le registre du port est keyé par NOM d'EffectType (c'est ce que threadent les vecteurs de pose),
        d'où le paramètre `name` ; `effect_type` n'est porté que pour l'identité de l'instance. Nom absent
        ou non porté → `BaseEffect` = def NEUTRE (`can_be_immune_to = False` ⇒ jamais immune), la
        dégradation fidèle : un effet dont la classe n'est pas portée n'invente aucune immunité."""
        klass = cls.registry.get(name, BaseEffect) if name else BaseEffect
        return klass(name=name or "", effect_type=effect_type)

    @classmethod
    def register(cls, name: str, klass: type[BaseEffect]) -> None:
        cls.registry[name] = klass
