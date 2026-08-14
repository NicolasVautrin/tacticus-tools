"""Les QUATRE registres de triggers (trait / passiveAbility / activeAbility / effectType),
extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169 --
deplacement VERBATIM, zero changement de comportement).

Ce module porte AUSSI le gros bloc d'imports d'abilities concretes que ces registres
entrainent : ce sont leurs VALEURS, ils n'ont pas d'autre consommateur.

Les quatre dicts sont re-exportes TELS QUELS par le `__init__` du package (meme objet) :
un consommateur externe qui les MUTE (`ACTIVE_ABILITY_TRIGGERS.pop(...)` d'un test) agit
bien sur le dict que lit `core.collect_*`. Un REBIND, lui, ne porterait pas -- aucun site
connu n'en fait."""
from __future__ import annotations

from ..base import TriggeredAbility, EffectTrigger
from ..loki import (PsykerExtraAttackAbility, ActOfFaithAccumulateAbility, ActOfFaithResetAbility,
                   FinalJusticeAbility, TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility,
                   ArcaneShieldAbility, ControlEdictAbility, RadSaturationAbility,
                   LordOfTempestsAddIceAbility, FireTileDoT, FIRE_TILE,
                   OnFireDamageAbility, OnToxicDamageAbility)
from ..bond_removal import bond_removal_registry_entries
from ..pending_attack import pending_attack_registry_entries       # #513 : les attaques DIFFEREES
from ..effect_triggers import (OverwatchAutoAttack, ContaminatedTileEffect,
                              RangedAutoAttackActivateOnTurnStart,
                              RangedAutoAttackDeactivateOnTurnStart,
                              RangedAutoAttackDeactivateOnAttack,
                              BloodChaliceHealOnMeleeAttack,
                              OVERWATCH_AUTO_ATTACK, CONTAMINATED_TILE,
                              BLOOD_CHALICE_HEAL_ON_ATTACK)
from ..genestealer import (DecoysAndMisdirectionDamageEnemiesAbility,
                          DecoysAndMisdirectionBuffFriendsAbility,
                          AmbushSummonAbility, EnvAmbushResurrectAbility,
                          HypersensoryMoveAndSpawnDecoyAbility)
from ..loki.weaver_of_fate import WeaverOfFateAbility                 # #202-A (trait WeaverOfFate)
from ..loki.reality_unbound import (RealityUnboundAbility,            # passif thousTzaangor (2 volets)
                                   RealityUnboundExtraMaxDamageAbility)
from ..loki.prophetic_sentinel import PropheticSentinelOverwatchAbility  # passif thousSekhetar (volet overwatch)
from ..loki.time_flux import TimeFluxRegenAbility                     # passif thousTerminator (volet regen)
from ..loki.tough_to_kill import ToughToKillHealAbility               # passif astraDreir (volet regen)
from ..loki.healing_balms import (HealingBalmsDelayedHeal,            # #966 (effet 1508, spaceWolfPriest)
                                  HEALING_BALMS_EFFECT)
from ..loki.ghost_revive import (                                     # #213 + #366-r1
    TimeFluxReviveAbility, EchoesFromTheWarpAbility,                  # les 2 poses (`GhostReviveAbility`)
    TimeFluxGhostEffectRevive, EchoesFromTheWarpGhostEffectRevive,    # les 2 resurrections (`GhostEffect`)
    TimeFluxGhostRemoveOnSourceMoves, TimeFluxGhostRemoveOnUnitAdded,
    TimeFluxGhostRemoveOnUnitEnters, TimeFluxGhostRemoveOnSourceDeathInactive,
    TimeFluxGhostRemoveOnSourceRemoved,
    EchoesGhostRemoveOnSourceMoves, EchoesGhostRemoveOnUnitAdded,
    EchoesGhostRemoveOnUnitEnters, EchoesGhostRemoveOnSourceDeathInactive,
    EchoesGhostRemoveOnSourceRemoved,
    TIME_FLUX_GHOST_EFFECT, ECHOES_GHOST_EFFECT)
from ..loki.living_metal import LivingMetalRepairAbility             # #203 (trait LivingMetal, Necron)
from ..loki.close_combat_weakness import (                          # #1015-r1 (trait T'AU, 16 npc)
    CloseCombatWeaknessMarkStartedTurnAdjacent, CLOSE_COMBAT_WEAKNESS_REDUCE_DMG)
from ..loki.destroyer_hive import DestroyerHiveAbility               # case-220 DG (passiveAbility deathTyphus)
from ..loki.cursed_plague_bell import (CursedPlagueBellMovementAbility,   # #224 DG (passif deathBlightbringer)
                                      CursedPlagueBellAttackAbility)     # #224 item 5 (volet ATTAQUE)
from ..loki.martial_apotheosis import MartialApotheosisAttackAbility  # case-220 (passif necroOverlord, Necron)
from ..loki.light_im_up import LightImUpAbility                       # #419-r1-tr5-r7 (passif orksWarboss, face COMBAT)
from ..loki.martial_superiority import MartialSuperiorityRiposteAbility  # #133 (passif templChampion)
from ..loki.refusal_to_be_outdone import (RefusalToBeOutdoneRecordHitAbility,          # #965
                                          RefusalToBeOutdoneResetOnNormalAttackAbility,
                                          RefusalToBeOutdoneResetOnTurnEndAbility)
from ..loki.whispering_web import WhisperingWebAbility                # #965 (passif eldarLhykhis)
from ..loki.wireweave_net import (WireweaveNetCounterAttack,          # #366-r1b (passif eldarRanger)
                                  WireweaveNetActivateOnOwnerTurnEnd,
                                  WireweaveNetDeactivateOnOwnerTurnStart,
                                  WIREWEAVE_NET_COUNTER_ATTACK)
from ..loki.grim_retribution import (GrimRetributionCounterAttack,    # #946 (passif darkaHellblaster)
                                     GrimRetributionActivateOnEnemyTurnStart,
                                     GrimRetributionDeactivateOnEnemyTurnEnd,
                                     GRIM_RETRIBUTION_COUNTER_ATTACK)
from ..loki.unwavering_sentinel import (UnwaveringSentinelCounterAttack,   # #946 (passif custoKyrus)
                                        UnwaveringSentinelCustomAbility,
                                        UnwaveringSentinelActivateOnEnemyTurnStart,
                                        UnwaveringSentinelDeactivateOnEnemyTurnEnd,
                                        UNWAVERING_SENTINEL_COUNTER_ATTACK,
                                        UNWAVERING_SENTINEL_ABILITY)
from ..loki.shield_of_faith import (ShieldOfFaithAbility,             # #1024-r1 (mythique adeptExorcist)
                                    ShieldOfFaithCustomAbility,
                                    SHIELD_OF_FAITH as SHIELD_OF_FAITH_ABILITY)
from ..loki.master_of_the_tutelaries import (MasterOfTheTutelariesSummonAbility,   # #202-C (triggered 1173)
                                            MASTER_EFFECT as MASTEROFTUTELARIES_EFFECT)
from ..loki.tainted_narthecium import TaintedNartheciumReviveAbility  # case-66 (passif deathRotbone, revive)
from ..loki.narthecium import NartheciumReviveAbility                 # #79 (passif ultraApothecary, revive)
from ..loki.rites_of_morkai import (RitesOfMorkaiReviveTrigger,       # #79 (effet 1502 pose par Baldr)
                                   RITES_OF_MORKAI_EFFECT)
from ..loki.attempted_possession import (AttemptedPossessionPropagate,   # #590-r3 (effet 1209, thousSorcerer)
                                         POSSESSED as POSSESSED_EFFECT)
from ..loki.reanimation_beam import (ReanimationBeamReviveTrigger,    # #79 (effet 1547, MoW necroReanimator)
                                    REANIMATION_BEAM_EFFECT)
from ..loki.phoenix_gem import (PhoenixGemReviveAbility,              # #79 (relic, marqueur 1451)
                               PhoenixGemRemoveMarkerOnRevive,       # #89-B3 (On(0x2d = UnitRevived) -> RemoveEffect)
                               PhoenixGemRemoveMarkerOnResurrect,    # #89-B3 (On(0x2e = UnitResurrected) -> RemoveEffect)
                               PHOENIX_GEM_CAN_REVIVE)
from ..loki.legendary_commander import (                             # #419-r1-tr9-r4-r1-r2-r1
    LegendaryCommanderExtraHitsMarkCaster, LEGENDARY_COMMANDER_EXTRA_HITS)
from ..loki.suppressive_fire import SuppressiveFireAddEffectAbility  # #74 (trait SuppressiveFire 1010)
from ..loki.special_issue_combi_melta import (                       # #419-r1-tr11-r4 (passif 1545)
    SpecialIssueCombiMeltaAddEffectAbility, SPECIAL_ISSUE_COMBI_MELTA)
from ..loki.death_nova import ExplodesAbility, PutridExplosionAbility  # death-nova (traits 1008 / 2028)
from ..loki.master_annihilator import MasterAnnihilatorMarkAbility   # lot POSE (passif admecDominus)
from ..loki.fleshmetal_guns import (FleshmetalGunsRotationAbility,   # lot POSE (passif blackObliterator)
                                   FleshmetalGunsTileEffectAbility)  # #85 volet DespoiledGround
from ..loki.despoiled_ground import (DespoiledGroundTileDoT,         # #85 (EnvDespoiledGroundTileAbility)
                                    DESPOILED_GROUND_TILE)
from ..loki.head_claimer import (HeadClaimerOnDeathAbility,          # lot POSE (passif blackHaarken,
                                 HeadClaimerOnFledAbility)           # #947)
from ..loki.trophy_taker import TrophyTakerOnUnitDefeatedAbility     # #951 (passif worldExecutions)
from ..loki.headwoppas_killchoppa import (                           # #1012-r1 (relique 1549 d'orksWarboss :
    HEADWOPPAS_KILLCHOPPA_EXTRA_DMG,                                 #  le compteur de kills de l'effet
    HeadwoppasKillchoppaIncreaseLevelOnKill)                         #  1568, sans cap)
from ..loki.skullsmasher import (SkullsmasherActivateStunAbility,    # #953 (passif worldJakhal :
                                 SkullsmasherTriggerStunAbility)     # marqueur de kill + pose du Stun)
from ..loki.obsessive_annunciation import (                          # #954 (passif emperKakophonist :
    ObsessiveAnnunciationOverkillAbility)                            # armement de l'aura de crit)
from ..loki.ecstatic_slaughter import (                              # passif emperFlawlessBlade :
    EcstaticSlaughterOnThrilledAbility, EcstaticSlaughterOnOverkillAbility)   # riposte + taunt
from ..loki.armour_of_shrieking_souls import (                       # passif emperLucius : le tueur
    ARMOUR_OF_SHRIEKING_SOULS_EFFECT,                                # devient Elated, saigne, et sa
    ArmourOfShriekingSoulsOnDeathAbility,                            # disparition ramene Lucius
    ArmourOfShriekingSoulsDrainOnTurnStart,
    ArmourOfShriekingSoulsResurrectOnRemoved,
    ArmourOfShriekingSoulsRemoveOnSourceResurrected)
from ..loki.terrifying_crescendo import (TerrifyingCrescendoOverkillAbility,   # lot POSE (passif
                                        TerrifyingCrescendoSuppressAbility)   # emperNoiseMarine, #204)
from ..loki.deathwing import DeathwingAbility                          # #932 (passif darkaTerminator)
from ..loki.fuelled_by_fury import (FuelledByFuryExtraDamageAbility,  # compteur 1323 (passif ultraTitus)
                                    FuelledByFuryReviveAbility,       # #88 A1 : self-revive On(3)
                                    FuelledByFuryCanReviveActivateOnAbilityInit,
                                    FuelledByFuryCanReviveActivateOnTurnStart,
                                    FuelledByFuryCanReviveDeactivateOnRevive,
                                    FUELLED_BY_FURY_CAN_REVIVE)       # marqueur 1324
from ..loki.talons_of_the_emperor import (                            # #521-r1 : compteur 1420
    TalonsOfTheEmperorUsedAbilitiesAbility,                           # (helper PASSIF de l'actif 1195)
    TALONS_OF_THE_EMPEROR_ID as TOTE_ACTIVE_ID)
from ..loki.anvil_shield import (AnvilShieldApplyIceAbility,          # lot POSE (passif spaceRockfist)
                                AnvilShieldApplyStunAbility,          # #100 volet Stun on-block
                                AnvilShieldFrozenAttackerAdvantageAbility,   # #100 volet +block glace
                                AnvilShieldFrozenAdvantageExpire,     # #100 conso On(UnitPostAbility)
                                FROZEN_ADVANTAGE as ANVIL_FROZEN_ADVANTAGE)
from ..loki.let_the_galaxy_burn import (LetTheGalaxyBurnArmAbility,   # #84 (trait LetTheGalaxyBurn 1058)
                                       LetTheGalaxyBurnResetAbility)
from ..loki.sworn_protector import (SwornProtectorSummonKellAbility,  # #95-RESTE2 (passif astraCreed)
                                   SwornProtectorProtectSwitchAbility)
from ..loki.haze_of_corruption import (HazeOfCorruptionTargetFinderAbility,   # case-207 (deathBlightlord)
                                      HazeCorruptionBonusHitAbility,         # case-209 (coup Toxic bonus)
                                      HazeOfCorruptionDamageTransferTrigger,  # case-209 (effet 1077)
                                      HAZE_DAMAGE_TRANSFER)
from ..loki.listen_up_maggots import ListenUpMaggotsAddEffectAbility  # #95-RESTE2 (passif astraSmnKell)
from ..loki.stormboyz_strike import (StormboyzStrikeTeleportAbility,   # #366-r1 3/3 (passif orksNpc6Stormboy)
                                     StormboyzStrikeFallbackAbility,   # #448-r1 -- On(0x28)
                                     StormboyzStrikeMissAbility)       # #448-r1 -- On(0x1f)
# Imports pour EFFET DE BORD : ces modules inscrivent leur entree de `TRIGGERED_ABILITY_BEHAVIOURS`
# A L'IMPORT. Sans eux, le noeud `TriggerAbility` qui les vise rend `dispatched: False` -- un gap
# VISIBLE, mais un gap, et sur les deux phases 2 d'`APendingAttackEffect` il est PIRE que ca :
# le `RemoveEffect` du MEME `Triggered()` consomme le marqueur quand meme, donc l'effet disparait
# sans que rien ne frappe (`triggers/pending_attack.py` Sec.2).
#   1134 FullThrottle              -- #448-r1 (`TriggerAbility(Caster, 0x46e)` du Miss)
#   1127 SeekerMissile_Attack      -- #513, phase 2 de l'active 1069, DEPLACEE ici par #503-r3
#   1237 OverwhelmingWrath_Attack  -- #503-r1, phase 2 de l'active 1141, DEPLACEE ici par #503-r3
# ⚠ Les deux dernieres vivaient dans `abilities/tau.py` et `abilities/worldeaters.py`, donc hors de
# portee de ce module : mesure du 2026-08-10 en process FRAIS, le registre n'avait qu'UNE entree
# ici contre QUATRE via `abilities/handler.py`. Les hisser d'ou elles etaient n'etait pas possible
# (`registry -> abilities.tau` est une arete PORTEUSE, mesuree) -- c'est le DEPLACEMENT qui a
# supprime l'arete. Cliquet : `tests/engine/runner/test_503r3_registre_trigger_peuple_offline.py`.
from ..loki import full_throttle as _full_throttle                  # noqa: F401
from ..loki import seeker_missile_attack as _seeker_missile_attack  # noqa: F401
from ..loki import overwhelming_wrath_attack as _overwhelming_wrath_attack  # noqa: F401
from ..loki import lions_wrath_attack as _lions_wrath_attack        # noqa: F401  (#889, phase 2 de 1217)
from ..loki import the_lantern_attack as _the_lantern_attack        # noqa: F401  (#1030, phase 2 de 1094)
from ..loki.thrill_seekers import (ThrillSeekersFullHealthTargetAbility,   # trait ThrillSeekers 1056
                                  ThrillSeekersDamageTakenAbility)        # (x5 Emperor's Children)
from ..loki.hailstrike import HailstrikeAttackAbility                 # case-117 ph.2 (1214 -> 1507)
from ..loki.drachnyen import (DrachnyenExtraAttackAbility,            # #BL-1029r (1029 -> 1485)
                              DRACHNYEN_ABILITY)
from ..loki.doctrina_imperatives import (DoctrinaImperativesSetStartAbility,   # #521-r4
                                         DOCTRINA_IMPERATIVES_ACTIVE)          # (1118 -> 1201)
from ..loki.calibanite_greatsword import (                                     # #521-r4 / #521-r7
    CalibaniteGreatswordNormalAttackAdditionalDamageAbility,                   # (1189 -> 1316)
    CALIBANITE_GREATSWORD_ACTIVE)
from ..loki.empyric_ambush import EmpyricAmbushResetAbility           # #589-r1-r1-r1-r1 (1232 -> 1555)
from ..loki.heavy_warp_flamer import (HeavyWarpFlamerAttackTrackingAbility,       # #523-r1
                                      HeavyWarpFlamerAttackTrackingResetAbility)  # (1227 -> 1546)
from ..loki.inspired_to_greatness import (InspiredToGreatnessOverrideLevelRemove,   # #114 residu 2
                                         ITG_OVERRIDE_LEVEL)
from ..loki.chronometron import (ChronometronExtraDamageRemove,                    # residu R9
                                CHRONOMETRON_EXTRA_DAMAGE)
from ..loki.timesplinter_mantle import (                       # #961 (1534 + effet 1551)
    TimesplinterMantleAbility, TimesplinterMantleDamageReductionRemoveOnAttack,
    TimesplinterMantleDamageReductionRemoveOnTurnEnd, MANTLE_EFFECT, TIMESPLINTER_MANTLE)
from ..loki.living_lightning import (                          # #961 (1007 + 1020 + effet 1020)
    LivingLightningAttackAbility, LivingLightningMoveEffectAbility,
    LivingLightningMovingRemoveOnArrived, LIVING_LIGHTNING, LIVING_LIGHTNING_MOVE_EFFECT)
from ..loki.fury_from_the_delve import (                       # #964 (passif 1528, votanBeserk)
    FuryFromTheDelveCheckTargetHealthAbility, FuryFromTheDelveAttackOrPinAbility,
    FURY_FROM_THE_DELVE)
from ..loki.ecog_support import ECogSupportAbility, ECOG_SUPPORT   # #964-r1 (passif 1487, votanIronmaster)
from ..loki.omnissiahs_blessing import (                    # #1023 (passif 1299, admecSmnTechpriest)
    OmnissiahsBlessingAbility, OMNISSIAHS_BLESSING)
from ..loki.herald_of_the_apocalypse import (HeraldOfTheApocalypseExtraDamageRemove,  # #BL-1020r
                                             HERALD_OF_THE_APOCALYPSE_EFFECT)
from ..loki.euphoric_strikes import (EuphoricStrikesExtraCritRemove,               # #522 (1198 -> 1429)
                                     EUPHORIC_STRIKES_EXTRA_CRIT)
from ..loki.shock_assault import (ShockAssaultBuffRemove,                          # case-366-r1 (1000)
                                  SHOCK_ASSAULT_BUFF)
from ..loki.hateful_assault import HatefulAssaultAttackAbility            # case-366-r1 (1038 + 1175)
from ..loki.legacy_of_combat import LegacyOfCombatAdditionalAttackAbility  # #928 (1319, custoBladeChampion)
from ..loki.savage_killer import SavageKillerAbility                      # #929 (1159, passif spaceWulfen)
from ..loki.wrathful_devotion import WrathfulDevotionAbility              # #936 (1214, passif worldTerminator)
from ..loki.full_throttle import FullThrottlePassiveAbility               # #448-r1-r1 (1134, gate)
from ..loki.harlequins_panoply import (HarlequinsPanoplyIgnoreHitsRemove,  # case-366-r1 (1227)
                                       HarlequinsPanoplyCustomAbility,     # case-366-r1 move (#406)
                                       HARLEQUINS_PANOPLY_ABILITY,
                                       HARLEQUINS_PANOPLY_IGNORE_HITS)
from ..loki.until_of_end_turn import (HatefulAssaultAlreadyAttackedRemove,
                                      HATEFUL_ASSAULT_ALREADY_ATTACKED)
from ..loki.teleporting_in import (                                       # #448-r2 tranche 1/4
    TeleportStrikeTeleportingInRemoveOnAfterMove,          # T1 On(4)
    TeleportStrikeTeleportingInRemoveOnPreUnitAbility,     # T2 On(0x2a = PreUnitAbility)
    TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn,   # T3 On(0x28 = UnitFinishedTurn) & HasTile
    TeleportStrikeTeleportingInAddMovingOnPreMove,         # T4 On(0x1f) -> AddEffect(1036)
    TeleportStrikeMovingRemoveOnAfterMove,                 # TeleportMovingEffect : On(4)
    TELEPORT_STRIKE_TELEPORTING_IN, TELEPORT_STRIKE_MOVING,
    FearOfTheUnseenTeleportingInRemoveOnAfterMove,         # #448-r2c tranche 2/4 -- T1 On(4)
    FearOfTheUnseenTeleportingInRemoveOnPreUnitAbility,    # T2 On(0x2a = PreUnitAbility)
    FearOfTheUnseenTeleportingInRemoveOnUnitFinishedTurn,  # T3 On(0x28 = UnitFinishedTurn) & HasTile
    FearOfTheUnseenTeleportingInAddMovingOnPreMove,        # T4 On(0x1f) -> AddEffect(1241)
    FearOfTheUnseenMovingRemoveOnAfterMove,                # TeleportMovingEffect : On(4)
    FEAR_OF_THE_UNSEEN_TELEPORTING_IN, FEAR_OF_THE_UNSEEN_MOVING,
    StormboyzStrikeTeleportingInRemoveOnAfterMove,         # #448-r2b -- T1 On(4)
    StormboyzStrikeTeleportingInRemoveOnPreUnitAbility,    # T2 On(0x2a)
    StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn,  # T3 On(0x28) & HasTile -> FAUX hors plateau
    StormboyzStrikeTeleportingInAddMovingOnPreMove,        # T4 On(0x1f = PreUnitMove) -> Nothing() (Nullable VIDE)
    STORMBOYZ_STRIKE_TELEPORTING_IN,
    TitanhammerSquadTeleportingInRemoveOnAfterMove,        # #448-r2d tranche 4/4 -- T1 On(4 = UnitAfterMove)
    TitanhammerSquadTeleportingInRemoveOnPreUnitAbility,   # T2 On(0x2a = PreUnitAbility)
    TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn, # T3 On(0x28 = UnitFinishedTurn) & HasTile
    TitanhammerSquadTeleportingInAddMovingOnPreMove,       # T4 On(0x1f = PreUnitMove) & <vslot 0x748> -> 1574
    TitanhammerSquadMovingRemoveOnAfterMove,               # TeleportMovingEffect : On(4 = UnitAfterMove)
    TITANHAMMER_SQUAD_TELEPORTING_IN, TITANHAMMER_SQUAD_MOVING)
from ..loki.ramming_speed import (RammingSpeedExtraExplodeRemove,          # case-389-r1 (1098)
                                  RAMMING_SPEED_EXTRA_EXPLODE)
from ..loki.terminator_armour import (TerminatorArmourDeactivateOnAttack,   # #432 (trait, 44 porteurs)
                                      TerminatorArmourActivateOnTurnStart,
                                      TerminatorArmourDeactivateOnTurnEnd,
                                      TerminatorArmourActivateOnEffectAdded,
                                      TERMINATOR_ARMOUR_REDUCE_DMG)
from ..loki.reactivate_overwatch import (EarlyWarningOverrideReactivateOverwatch,   # #114 residu 3
                                        EarlyWarningOverrideHitReductionPurge,
                                        EWO_REACTIVATE_OVERWATCH,
                                        InescapableDeathReactivateOverwatch,        # #924 (necroDestroyer)
                                        InescapableDeathHitReductionPurge,
                                        INESCAPABLE_DEATH_EFFECT)
from ..loki.cosmic_horror import (CosmicHorrorOnKillAbility,           # passif genesPatriarch (GS Cults)
                                 CosmicHorrorOnMoveAbility)
from ..loki.possession import PossessionSummonOnKillAbility            # #955 (passif blackPossession)
from ..loki.summary_execution import SummaryExecutionAbility           # #955 (passif astraYarrick)
from ..loki.spiritual_leader import SpiritualLeaderAbility             # passif genesMagus (GS Cults)
from ..loki.barbed_ovipositor import BarbedOvipositorSummonAbility     # passif tyranParasite (Tyranids)
from ..loki.synaptic_linchpin import SynapticLinchpinAbility           # passif tyranWingedPrime (Tyranids)
from ..loki.fabricator_claw_array import FabricatorClawArrayAbility    # #303 (passif necroSpyder, N20)
from ..loki.reanimation_protocols import ReanimationProtocolsAbility  # #1016 (passif necron 1008)
from ..loki.champion_of_the_feast import ChampionOfTheFeastAbility    # #419-r6-r2 (passif templSwordBrother)
from ..loki.fury_of_the_ancients import FuryOfTheAncientsAbility      # #927 (passif bloodMephiston)
from ..loki.sanguinary_priest import SanguinaryPriestAbility          # #921 (passif bloodSanguinary)
from ..loki.medicus_ministorum import MedicusMinistorumAbility        # #958 (passif adeptHospitaller)
from ..loki.aggressive_onslaught import (AggressiveOnslaughtPrepareAbility,   # #958 (passif
                                         AggressiveOnslaughtSummonAbility,    #  bloodIntercessor,
                                         AggressiveOnslaughtUnsummonAbility)  #  3 classes natives)
from ..loki.red_rampage import (RedRampageAttackAbility,              # #963 (passif bloodTerminator,
                                RedRampageBuffAbility)                #  2 classes natives)
from ..loki.geminae_superia import GeminaeSuperiaAbility              # #963 (passif adeptCelestine)
from ..loki.dawn_blade import DawnBladeHealAbility                     # #317 (relique tauFarsight)
from ..loki.wyrdmakers_helm import WyrdmakersHelmAbility               # #1037 (relique spaceWolfPriest)
from ..loki.daemonflesh_plate import (DaemonfleshPlateAbility,        # #916 (relique 1493)
                                      DaemonfleshPlateResetActiveAbility)
from ..loki.orbs_of_decay import OrbsOfDecayAbility                    # #1003 (relique 1465, DG)
from ..loki.lakrimae import LakrimaeAddContaminationAbility            # #1003 (relique 1541, DG)
from ..loki.chalice_of_baal import (ChaliceOfBaalAbility,             # #1005 (relique 1550,
                                    ChaliceOfBaalResetAbility)        #  bloodSanguinary)
from ..loki.vitarus import VitarusAbility                              # #1005 (relique 1470,
                                                                       #  bloodMephiston)
from ..loki.blade_of_the_ancestors import (                           # #1001 (relique 1491, votanUthar)
    BladeOfTheAncestorsAbility, BladeOfTheAncestorsRemoveEffectAbility,
    BladeOfTheAncestorsCustomRemoveEffectAbility, BLADE_OF_THE_ANCESTORS)
from ..loki.volumms_master_artifice import (                          # #1001 (relique 1488, votanIronmaster)
    VolummsMasterArtificeAbility)
from ..loki.maugetar import (MaugetarAddEffectAbility,                # #1006 (relique 1498)
                             MaugetarResetMovementAbility,
                             MaugetarHasNotMovedRemoveOnMove,
                             MAUGETAR_HAS_NOT_MOVED)
from ..loki.sabre_of_sacrifice import SabreOfSacrificeAbility          # #1002 (relique 1478)
from ..loki.relic_of_lost_cadia import (RelicOfLostCadiaAbility,       # #1002 (relique 1459)
                                        RelicOfLostCadiaSummonUnitAbility)
from ..loki.book_of_fate import BookOfFateAbility                     # #1008 (relique 1461, BL)
from ..loki.helspear import (HelspearBuffActiveAbility,               # #1008 (relique 1558,
                             HelspearResetActiveAbility)              #  blackHaarken)
from ..loki.dw02_advanced_burst_cannon import (                       # #1012 (relique 1476, tauCrisis)
    Dw02AdvancedBurstCannonAbility)
from ..loki.relic_power_fist import RelicPowerFistAbility             # #1009 (relique 1466, 3 factions)
from ..loki.paragon_spear import ParagonSpearAbility                   # #1013 (relique 1494, custoKyrus)
from ..loki.the_ardent_blade import TheArdentBladeTriggerAbility       # #1013-r2 (relique 1468)
from ..loki.phasal_subjugator import (PhasalSubjugatorSummonAbility,   # #1011-r1 (relique 1557,
                                      PhasalSubjugatorTriggerPassiveAbility)   # necroOverlord)
from ..loki.electrochaff_backups import (                             # #1025 (MYTHIQUE 1454, MoW
    ElectrochaffBackupsOnMarkerlightAbility,                          #  tauBroadside : voie
    ElectrochaffBackupsOnRangedDamageAbility)                         #  TERTIAIRE, cf. le registre)
from ..loki.hyper_corrosive_acid import HyperCorrosiveAcidAbility      # #1035 (MYTHIQUE 1455, MoW
                                                                      #  tyranBiovore, voie TERTIAIRE)
from ..loki.relentless_march import RelentlessMarchAbility             # #328 (passif necroWarden)
from ..loki.my_will_be_done_overlord import (MyWillBeDoneOverlordAttackAbility,   # #354 (necroOverlord)
                                             MyWillBeDoneOverlordClearAbility)
from ..loki.icon_of_obstinacy import IconOfObstinacyAddArmourBuffAbility   # #919 (astarLysander)
from ..loki.serene_unifier import SereneUnifierRotationAbility        # #462-r4e-o-r2-r1-r1 (tauAunShi)
from ..loki.neuroparasite import (NeuroparasiteAddBondEffectAbility,     # #462-r4b-r1-r1-r1
                                  NeuroparasiteIncreaseLevelOnPsychicHit,
                                  NeuroparasiteIncreaseLevelOnPinned,
                                  NEUROPARASITE_EFFECT)
from ..loki.haywire_mine import (HaywireMineSteppableAbility,          # #462-...-c-r3-r1-r3
                                 HaywireMineCustomAbility,             # #462-...-c-r3-r1-r5
                                 HaywireMinePlaceOnMoveAbility,
                                 HaywireMinePlaceOnTurnEndAbility,
                                 HaywireMineResetAbility,
                                 HAYWIRE_MINE_ID)
from ..loki.savior_protocols import SaviorProtocolsAbility            # #1020 (passif drones T'au)
from ..loki.instinctive_behaviour import InstinctiveBehaviourUpdateTargetAbility   # #1015-r1


# --- Registre : trait → ability-trigger(s) accordée(s) --------------------------------------------
TRAIT_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    "Psyker": [PsykerExtraAttackAbility],
    # InstinctiveBehaviour (trait 0x7e5 = 2021, 23 porteurs : 18 npc + 5 summons Tyranides ; #1015-r1)
    # -> triggered DERIVEE `TriggeredAbilityType.InstinctiveBehaviour` = 0x413 = 1043 (dict `Trait +0x0`,
    # `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities`). Elle MAINTIENT le
    # `ForcedAttackTargetsComponent` du porteur egal a « l'ennemi le plus proche a portee d'attaque
    # + mouvement », sauf sous SYNAPSE (0x41c) et sauf si le porteur est TAUNTE (27). Le volet
    # MOUVEMENT du trait est l'owner-effet 1235 (`TRAIT_DERIVED_ABILITIES` + `ABILITY_INIT_OWNER_
    # EFFECTS`, `entities/effects/factory.py`). Cf. loki/instinctive_behaviour.py.
    "InstinctiveBehaviour": [InstinctiveBehaviourUpdateTargetAbility],
    # ActOfFaith accorde DEUX ability-triggers (accumulation sur mort/kill + reset au crit).
    "ActOfFaith": [ActOfFaithAccumulateAbility, ActOfFaithResetAbility],
    # FinalJustice (worldKharn) = attaque normale à la mort (fire-on-death, gate overkill).
    "FinalJustice": [FinalJusticeAbility],
    # Ambush (Isaak/Judh/Neophyte, G3) = mort -> decoy (On UnitDefeated=54) + resurrection sur decoy allie
    # au debut du tour suivant (On TurnStart=22). Les DEUX sont fire-on-death (owner mort au moment du fire).
    "Ambush": [AmbushSummonAbility, EnvAmbushResurrectAbility],
    # WeaverOfFate (trait Abraxas thousInfernalMaster, #202-A) = `On(9=Attack)` : >=3 ennemis ayant recu
    # du degat PSYCHIC ce tour -> pose l'effet-marqueur 1185 WeaverOfFate_MaxOutDamage sur soi (1 tour,
    # degats max sans tirage). Cf. loki/weaver_of_fate.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateBehaviour).
    "WeaverOfFate": [WeaverOfFateAbility],
    # LivingMetal (trait 1000, TOUT le roster Necron : 41 npc + 6 lineup + 4 summons, #203) = regen % PV
    # au debut du tour du proprietaire : `On(TurnStart_Other=19) & OwnerIsActor & IsDamaged(self)` ->
    # Repair(self, round(10% maxHP)). Cf. loki/living_metal.py (IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateBehaviour).
    "LivingMetal": [LivingMetalRepairAbility],
    # SuppressiveFire (trait 1010, x49 unites dont 8 lineup, #74) = pose Pinned/« Suppressed » (1065) sur
    # la cible d'une attaque RANGED du porteur : `On(PreAttack=5) & IsRangedAttack & OwnerIsActor &
    # AreEnemies & AmountIsGreaterThanZero(Units(target))` -> `AddEffect(Pinned, Target())`. Route sur
    # `On(NormalAttack=38)` (cf. loki/suppressive_fire.py IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateBehaviour).
    "SuppressiveFire": [SuppressiveFireAddEffectAbility],
    # DEATH-NOVA (`loki/death_nova.py`) : les deux traits qui font exploser le porteur a sa MORT, sur
    # l'event `PreUnitDeath_2 = 2` (PAS 1 : `IdunBattleLogic.Entities.DSLTriggers$$OnPreDeath2` -> `OnDeathEvent(2,...)`).
    # Explodes (1008 -> triggered 1021, IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$CreateBehaviour) : maxPV x 25% en DirectDamage a TOUS les
    # adjacents (friendly-fire), fire MEME EN OVERKILL (`OnPreDeath2(1,1)` = aucun gate).
    "Explodes": [ExplodesAbility],
    # PutridExplosion (2028 -> triggered 1074, IdunBattleLogic.Entities.Abilities.Active.Loki.PutridExplosion_Ability$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.PutridExplosion_Ability$$CreateBehaviour) : maxPV x 25% en Toxic aux adjacents
    # SAUF faction DeathGuard ; `OnPreDeath2(1,0)` = pas de gate overkill, mais NOT HasTrait(Steppable).
    "PutridExplosion": [PutridExplosionAbility],
    # LetTheGalaxyBurn (trait 1058, x5 heros Black Legion, #84 volet 1) = arme/desarme le FLAG persistant
    # 1482 qui alimente le +1 coup de `LetTheGalaxyBurnEffect` (effet 1477) :
    #   - `LetTheGalaxyBurnAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour : `On(PreAttack=5) & OwnerIsCaster &
    #     Maybe(33%) & !HasTileStatusEffect(Targets)` -> `SetPersistentData` ;
    #   - `LetTheGalaxyBurn_ResetAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour : `ClearPersistentData` en fin d'attaque (`On(9)`).
    # Cf. loki/let_the_galaxy_burn.py (2 branches du gate, ground truth live 34.2% / 100%).
    "LetTheGalaxyBurn": [LetTheGalaxyBurnArmAbility, LetTheGalaxyBurnResetAbility],
    # ThrillSeekers (trait 1056 -> triggered 1444 ; les 5 kits Emperor's Children, tous lineup/HERO) =
    # DISJONCTION `op_BitwiseOr` de deux `On()` -> DEUX classes (patron TerrifyingCrescendo/ActOfFaith) :
    #   `On(PreAttackHit=6) & IsFirstHitInSeries & OwnerIsCaster & Not(IsWounded(target))`
    #      = « le porteur commence une attaque sur un ennemi a PLEINE VIE »
    #   `On(DamageTaken=0xf) & OwnerIsTarget`   = « le porteur SUBIT du degat »
    # -> pose (ou REFRESH via `ChangeEffectTurns(Set)` si deja porte) l'effet *Thrilled* 1434 =
    # `AddStaticStatModifierEffect(Owner, 1434, CRIT_CHANCE, extraCritChance=15, TurnsFromRounds(1))`.
    # Cf. loki/thrill_seekers.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateTrigger /
    # IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateBehaviour).
    "ThrillSeekers": [ThrillSeekersFullHealthTargetAbility, ThrillSeekersDamageTakenAbility],
}

# --- Registre : passiveAbility → ability-trigger(s) accordée(s) ------------------------------------
# Certains triggers viennent d'une PASSIVE ABILITY (≠ trait), ex. worldKharn.passiveAbilities=['TheBetrayer'].
ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # SpecialIssueCombiMelta (passif de `darkaSternguard` << Ramus >> HERO + du npc
    # `darkaBossSternguardLHE`) = la 3e portee du kit, la seule qui vive sur une ABILITY :
    # `On(0x26 = NormalAttack) & OwnerIsCaster & IsAtRange(Caster@+0x48, Target@+0x60, Get(3))`
    # -> `AddEffect(0x429 = 1065 Pinned, targets = Target@+0x60, source NULLE = la cible)`.
    # ⚠ CE N'EST PAS un montage `GetDerivedTriggeredAbilities` : les DEUX dicts natifs ont ete lus
    # (`StaticBattleRules.ActiveAbility$$.cctor` est indexe par `ActiveAbilityType` -- l'active du
    # porteur est `SternguardFocus` ; `StaticBattleRules.TriggeredAbility$$.cctor` ne peuple son
    # `<statics>+0x88` que de `0x3ef -> [0x3fc]` et `0x48e -> [0x491]`, jamais `0x609`). C'est le
    # chemin ORDINAIRE d'une passiveAbility, forme `LetTheGalaxyBurn` : DEUX classes natives pour UN
    # nom de kit. La soeur `SpecialIssueCombiMelta_InitAbility` n'est pas portee (le port ne rejoue
    # aucun spawn ; ses effets 1563/1564 arrivent poses par `load_state`). Cf.
    # loki/special_issue_combi_melta.py. #419-r1-tr11-r4.
    SPECIAL_ISSUE_COMBI_MELTA: [SpecialIssueCombiMeltaAddEffectAbility],
    # TimesplinterMantle (passif 0x5fe = 1534 de `necroChronomancer` << Thothmek >>, HERO) :
    # `On(0x12 = TurnStart_EffectActivation, ownerNeedsToBeAlive: 1)` -- UN SEUL noeud, PAS
    # d'`IsTurnOf(Owner)` (contraste `RelentlessMarch`, l'autre passif Necron turn-start) -> l'effet
    # est REARME au debut de CHAQUE tour, les deux camps compris.
    # `Foreach(NonSteppableUnits(MechanicalUnits(Friends(AdjacentUnits(Owner)))) + Owner,
    #          AddEffect(0x60f = 1551, source = Owner@+0x30, targets = ActiveTarget@+0x68))`.
    # Cf. loki/timesplinter_mantle.py. #961.
    TIMESPLINTER_MANTLE: [TimesplinterMantleAbility],
    # LivingLightning (passif 0x3ef = 1007 de `necroPlasmancer` << Thutmose >>, HERO) -- DEUX classes
    # natives pour UN nom de kit, forme `LetTheGalaxyBurn` :
    #   * `LivingLightningAbility` : `On(0x1c = ArrivedAtFinalTile) & OwnerIsActor &
    #     !AmountIsZero(GetPossibleTargets(1))` -> `AttackWithAttackDamage(1x DirectDamage)` sur UN
    #     ennemi tire au hasard, rayon `If(<ennemi adjacent>, 1, constants.range = 2)` ;
    #   * `LivingLightningMoveEffectAbility` (0x3fc = 1020) : `On(0x1f = PreUnitMove) & OwnerIsActor
    #     & <la DESTINATION a >= 1 ennemi adjacent>` -> `AddEffect(0x3fc)` (marqueur VISUEL).
    # ⚠ 1020 est monte par `StaticBattleRules.**TriggeredAbility**$$GetDerivedTriggeredAbilities`
    # (`<statics>+0x88`, DEUX entrees : `0x3ef -> [0x3fc]` et `0x48e -> [0x491]`), un dict DISTINCT
    # de celui d'`ACTIVE_ABILITY_TRIGGERS` (`<statics>+0x30`, indexe par `ActiveAbilityType`).
    # Les deux chemins convergent ici sur la MEME cle -- le nom `units.passiveAbilities` --, donc
    # ecrire les deux classes sous cette entree monte EXACTEMENT l'ensemble natif ; l'ecrire dans
    # `ACTIVE_ABILITY_TRIGGERS` serait faux (l'active de `necroPlasmancer` est
    # `HarbingerOfDestruction`). Cf. loki/living_lightning.py. #961.
    LIVING_LIGHTNING: [LivingLightningAttackAbility, LivingLightningMoveEffectAbility],
    # FuryFromTheDelve (passif 0x5f8 = 1528 de `votanBeserk` << Grimnyr Berserker >>, HERO Leagues of
    # Votann) -- DEUX classes pour UN nom de kit, forme `LetTheGalaxyBurn` : le `CreateTrigger` natif
    # est une DISJONCTION `op_BitwiseOr` et le `CreateBehaviour` se ventile sur son `triggerType`.
    #   * `FuryFromTheDelveCheckTargetHealthAbility` : `On(0x2a = PreUnitAbility) & IsNormalAttack &
    #     OwnerIsActor` -> `SetPersistentData(1528, Owner, "TARGET_HEALTH_ABOVE_HALF",
    #     AmountIsGreater(Health.Current(Target), PercentageOf(Health.Maximum(Target), hpPct = 50)))` ;
    #   * `FuryFromTheDelveAttackOrPinAbility` : `On(0x26 = NormalAttack) & OwnerIsActor &
    #     IsAlive(Target)` -> `If(<le flag> > 0, AddEffect(0x429 = 1065 Pinned, nrOfRounds = 1),
    #     AttackWithAttackDamage(nrOfHits = 2, Eviscerate, minDmg/maxDmg))`.
    # ⚠ Les DEUX classes sont necessaires : sans la premiere, la cle reste absente,
    # `GetPersistentDataFormula$$Calculate` rend `default(T)` = 0, et la seconde partirait TOUJOURS
    # en attaque supplementaire. Cf. loki/fury_from_the_delve.py. #964.
    FURY_FROM_THE_DELVE: [FuryFromTheDelveCheckTargetHealthAbility,
                          FuryFromTheDelveAttackOrPinAbility],
    # EcogSupport (passif 0x5cf = 1487 de `votanIronmaster` << Vynn >>, HERO Leagues of Votann) --
    # DEUX classes natives pour UN nom de kit, mais elles NE SE VENTILENT PAS sur un `triggerType` :
    # ce sont deux `BaseTriggeredAbility` a `CreateTrigger` DIFFERENTS.
    #   * `ECogSupportAbility` (ICI) : `On(0x30 = 48 UnitRepaired, ownerNeedsToBeAlive: 1) &
    #     get_OwnerIsCaster` -> `If(AmountIsGreater(ConfigConst(maxSummons = 3),
    #     Count(UnitsWithId(Children(Owner), "votanSmnEcog", 3))),
    #     Spawn(Owner, PickRandomly(CanAddUnit(AdjacentTiles(Owner)), 1), "votanSmnEcog", opts),
    #     PerformAIAbility(PickRandomly(<E-Cogs adjacents ayant une cible de REPARATION>, 1),
    #                      getAbilityType = GetRepairType, overrideMovement = Direct(0)))` ;
    #   * `ECogSupport_InitAbility` : `OnOwnerSpecificAbilityInit(0x5cf)` -> `AddFlag(Owner, 0x18 =
    #     UnitFlag.CanRepairFullHealthUnits)`. PAS d'entree ici -- c'est un etat pose a l'INIT, il
    #     vit sur `entities/effects/factory.ABILITY_INIT_OWNER_FLAGS` (meme boucle native
    #     `InitializeActorAbilitiesOperation$$Execute` que les owner-effects).
    # ⚠ Le vecteur `On(0x30)` n'existait PAS avant cette tranche (`operations/repair.py` le nommait
    # parmi ses non-portes) : sans `triggers/dispatch/repair.py`, cette entree serait un
    # registered-but-dead. Cf. loki/ecog_support.py. #964-r1.
    ECOG_SUPPORT: [ECogSupportAbility],
    # OmnissiahsBlessing (passif 0x513 = 1299 d'`admecSmnTechpriest` << Tech-Priest Enginseer >>,
    # SUMMON d'`InvocationOfMachineVengeance` ; aussi `admecNpc2Techpriest`). UNE classe :
    #   `On(0x30 = 48 UnitRepaired, ownerNeedsToBeAlive: 1) & get_OwnerIsCaster
    #    & HasEffect(Owner@+0x30, 0x555 = 1365 MachineVengeance, onlyActive: 0, targetType: 6)
    #    & NOT get_OwnerIsTarget`
    #   -> `AddEffectOrIncreaseLevel(0x555, stateRef, source = Owner@+0x30, targets = Target@+0x60,
    #       level = EffectLevel(EffectFromOwner(Owner@+0x30, 0x555)), maxLevel = NULL)
    #      op_BitwiseAnd RemoveEffect(Owner@+0x30, Nullable(0x555), NULL)`
    # -- le TRANSFERT integral de la pile au repare, puis son retrait chez le porteur. L'ORDRE des
    # deux behaviours est load-bearing (inverse, le transfert lirait 0). Le vecteur `On(0x30)`
    # existe depuis #964-r1 (`dispatch/repair.py`), donc l'inscription n'est PAS registered-but-dead.
    # Cf. loki/omnissiahs_blessing.py. #1023.
    OMNISSIAHS_BLESSING: [OmnissiahsBlessingAbility],
    # TheBetrayer = gain-rage-au-kill (mort) + auto-tour (début de tour). Cf. les 2 classes dans loki.py.
    "TheBetrayer": [TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility],
    # ArcaneShield (Thaumachus) = bouclier à la FIN DE L'ACTIVATION du porteur : `On(0x1c=
    # ArrivedAtFinalTile) & OwnerIsActor & OwnerIsCaster` -> vecteur `arrived_at_final_tile_triggers`
    # (après son 1er move, OU à la clôture de son tour s'il n'a pas bougé). Cible = `First(SortByFormula(
    # pool, Sum(3*distance, faction, chaos, owner), ASC), 1)` — score ADDITIF où la distance domine.
    "ArcaneShield": [ArcaneShieldAbility],
    # DecoysAndMisdirection (Isaak genesPrimus, G2) = 2 abilities-triggers step-on-decoy : DamageEnemies
    # (ennemi qui marche sur un decoy allié -> Blast) + BuffFriends (allié -> +582 dmg fin-de-tour + decoy).
    "DecoysAndMisdirection": [DecoysAndMisdirectionDamageEnemiesAbility,
                              DecoysAndMisdirectionBuffFriendsAbility],
    # HatefulAssault (passif Angrax blackTerminator, case-366-r1) = attaque d'opportunite :
    # `On(0x1f=PreUnitMove) & AreEnemies & IsAdjacent & !HasEffect(Actor, 0x497) &
    # !AreEqual(Tiles(Actor), <destination>)` -> `AttackWithAttackDamage(2x Power) & AddEffect(0x497)`.
    # Le marqueur 1175 est ce qui borne l'attaque a UNE fois par ennemi et par tour ; son retrait vit
    # dans `EFFECT_TRIGGERS[1175]` (`On(TurnEnd)`). Cf. loki/hateful_assault.py.
    "HatefulAssault": [HatefulAssaultAttackAbility],
    # LegacyOfCombat (passif Kariyan `custoBladeChampion`, #928) = l'attaque SUPPLEMENTAIRE qui suit
    # la PREMIERE attaque du tour : `On(0xb = UnitAbility) & OwnerIsActor & !CurrentAbilityIs(1319)
    # & AmountIsEqual(TimesAttackMadeThisTurn(Owner, null), Direct(1))` ->
    # `If(AmountIsGreaterThanZero(First(SortByDamagePrediction(Randomize(BigTargets adjacents)))),
    #     1x Piercing sur ce Big Target, 3x Power sur CHAQUE ennemi adjacent)`.
    # `On(0xb)` n'avait AUCUN consommateur porte et n'etait donc pas emis : #928 l'ajoute sur les
    # DEUX voies (`dispatch/ability.py::unit_ability_triggers`). Cf. loki/legacy_of_combat.py.
    "LegacyOfCombat": [LegacyOfCombatAdditionalAttackAbility],
    # FullThrottle (passif orksNpc6Stormboy, #448-r1-r1) = le jetpack qui lache quand on pousse les
    # gaz : `On(0x24=UnitPositionChanged_1) & OwnerIsActor & AmountIsEqualOrGreater(MovementSteps(),
    # movement=3)` -> `If(Maybe(chance=30), Kill(Caster, Caster, ForDirectKill))`.
    # C'est la face AUTONOME ; la face DIRECTE (declenchee par `...StormboyzStrike_MissAbility` via
    # le nœud `TriggerAbility`) passe par `TRIGGERED_ABILITY_BEHAVIOURS[1134]` et court-circuite ce
    # `ShouldTrigger`. Les deux partagent le meme behaviour. Cf. loki/full_throttle.py.
    # ⚠ `MovementSteps()` = `AbilityEntities+0x11c` = `path.Count`, donc **pas + 1** : le seuil
    # effectif est 2 PAS parcourus, pas 3 (mesure : case-448-r1-r1).
    "FullThrottle": [FullThrottlePassiveAbility],
    # HypersensoryAbilities (passif Judh genesKelermorph, G6b) = MoveAndSpawnDecoy : `On(9=Attack)` sur la 1re
    # attaque du tour ennemi -> move + decoy sur la tuile quittee + contre-attaque 3x Projectile. G6a (HP-floor,
    # effet 1380) est un OWNER-EFFECT auto-pose (pas un ability-trigger) ; ici = le volet triggered.
    "HypersensoryAbilities": [HypersensoryMoveAndSpawnDecoyAbility],
    # ControlEdict (passif Tan Gi'da admecMarshall, S4b) = after-normal-attack `On(0x26)` Imperative-gate :
    # Protector -> summon Skitarii Vanguard adjacent a Tan (cap maxSummons[level]) ; Conqueror -> les Summons
    # Mechanical amis adjacents attaquent la cible de Tan a portee. Cf. loki/control_edict.py.
    "ControlEdict": [ControlEdictAbility],
    # RadSaturation (passif Skitarii Vanguard admecSmnVanguard, S4b GAP) = pose l'effet de TUILE Contaminated
    # (1244) sur SA PROPRE tuile apres qu'il bouge (`On(4)&OwnerIsActor`, vecteur after_move) ou en fin de tour
    # s'il n'a pas bouge (`On(0x17=TurnEnd)`, vecteur end_turn ci-dessous). Cf. loki/rad_saturation.py.
    "RadSaturation": [RadSaturationAbility],
    # LordOfTempests (passif Njal spaceStormcaller, #35) = AddIce : glace la tuile de CHAQUE ennemi touche
    # par une attaque normale de Njal (`On(38)` cible principale + `On(9)&kind==0x3f5` victime du smite
    # Psyker), `OwnerIsCaster`. Cf. loki/lord_of_tempests.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateBehaviour).
    "LordOfTempests": [LordOfTempestsAddIceAbility],
    # DestroyerHive (passif deathTyphus, case-220 DG) = au debut du tour de Typhus, sa nuee attaque 1x un
    # ennemi adjacent aleatoire (`On(0x16) & OwnerIsActor & AmountIsGreaterThanZero(GetValidTargets)` ->
    # AttackWithAttackDamage(caster, PickRandomly(ennemis adjacents,1), MinMax[passive lvl], DirectDamage,
    # nrOfHits=1)). Cf. loki/destroyer_hive.py (IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets/IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateBehaviour).
    "DestroyerHive": [DestroyerHiveAbility],
    # CursedPlagueBell (passif deathBlightbringer/Corrodius, Death Guard) -- DEUX des trois classes
    # natives du passif ; la DANGER ZONE (`CursedPlagueBellDangerZoneAbility` +
    # `CursedPlagueBell_DangerZoneEffect` 1084) n'est PAS portee.
    #  * MOUVEMENT (`CursedPlagueBellMovementAbility`) : `On(TurnStart_Other=0x13) & OwnerIsActor` ->
    #    `AddEffect(CursedPlagueBell_ExtraMove 1073, turns=Nullable(1))` sur
    #    `UnitsWithoutTrait(UnitsWithTrait(SurroundingFriends(Owner, ContagionsOfNurgleRange(Owner)),
    #    Chaos), Stationary)` = les allies Chaos non-Stationary du disque d'aura Contagion (centre
    #    exclu).
    #  * ATTAQUE (`CursedPlagueBellAttackAbility`, case-224 item 5) : `On(9=Attack) &
    #    (OwnerIsTarget|OwnerIsAlive) & !CasterIsTarget & CurrentAttackDamageProfilesContain(Psychic)
    #    & AreEnemies(Actor,Owner) & HasTrait(Actor,Psyker) & IsInContagionsOfNurgleRange &
    #    !CurrentAbilityIs(this)` -> `AttackWithAttackDamage(Actor -> Actor, Direct(dmg[lvl porteur]),
    #    Psychic, nrOfHits)` : le psyker ennemi qui porte une attaque Psychic DANS l'aura se blesse
    #    lui-meme. Cf. loki/cursed_plague_bell.py.
    "CursedPlagueBell": [CursedPlagueBellMovementAbility, CursedPlagueBellAttackAbility],
    # MartialApotheosis (passif necroOverlord, case-220 Necrons) = `On(TurnStart_Actions=0x16) & OwnerIsActor
    # & AmountIsGreaterThanZero(GetValidTargets)` : au debut de son tour, attaque 1 ennemi adjacent damageable
    # ALEATOIRE (PickRandomly count=1) avec 2 coups Energy (pierce 30). Classe native ETEND DestroyerHive
    # (CreateTrigger/GetValidTargets herites). Cf. loki/martial_apotheosis.py (IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour/IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets).
    # ⚠ VIVANTE, et le kit gameconfig ne le dit PAS (#392). Le build `rnca9r7q6c` l'a retiree du KIT
    # de `necroOverlord` (au profit de `MyWillBeDoneOverlord`) -- mais le natif ne monte pas le kit :
    # il enumere `UnitConfiguration.PassiveAbilities`, et `data/seed-bc.json` porte
    # `necroOverlord.PassiveAbilities = [1045]`. Mesure : le `TriggeredAbilityComponent` reel du
    # porteur rend `['1045=MartialApotheosis']` en hierarchie 2, et LIVE l'ennemi anneau-1 encaisse
    # 3702 au turn-start (0 a d=2). #354 avait conclu « orpheline » depuis le seul gameconfig : c'est
    # ce referentiel qui etait faux. Mesure + verdict : case-392, probe_392.
    "MartialApotheosis": [MartialApotheosisAttackAbility],
    # LightImUp (passif de kit d'`orksWarboss` << Boss Gulgortz >>, triggered 1103), face COMBAT --
    # #419-r1-tr5-r7. `On(0x26 = NormalAttack, ownerNeedsToBeAlive: 0) & get_OwnerIsActor` ->
    # `If(IsInAttackRange(Caster, Target), Attack(nrOfHits x Projectile [minDmg,maxDmg] sur la
    # cible)) & If(IsDead(Target), Attack(NumLeftOverHits sur 1 ennemi PickRandomly du disque
    # r = range, non obscurci, cible principale exclue))`.
    # ⚠ AUCUNE gate de MELEE cote combat : c'est le PLAYBOOK (face DECISION, #419-r1-tr5) qui porte
    # `IsMeleeAttack(case)`. Les deux faces divergent, et c'est natif.
    # Cf. loki/light_im_up.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$CreateBehaviour).
    "LightImUp": [LightImUpAbility],
    # TaintedNarthecium (passif deathRotbone, Death Guard/Chaos, case-66) = base ReviveEffect : `OnPreDeath &
    # CanBeRevived & AreFriends & HasTrait(Chaos) & IsAdjacent(2)` -> Maybe(75%){ Revive-EN-PLACE a
    # min(reviveHP,maxPV), even-if-Overkilled ; DeactivateEffect once-per-turn }. Debloqueur du sous-systeme
    # REVIVE (base ReviveEffect + ReviveUnitOperation). Cf. loki/tainted_narthecium.py (IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$.ctor/IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter/
    # IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger/IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour) + operations/revive.py (IdunBattle.Operations.ReviveUnitOperation$$Execute).
    "TaintedNarthecium": [TaintedNartheciumReviveAbility],
    # Narthecium (passif ultraApothecary, Ultramarines/Imperial, #79 retrofit case-66) = MEME base
    # ReviveEffect : `OnPreDeath(unless-Overkilled) & CanBeRevived & AreFriends & IsAdjacent(2)` ->
    # Maybe(100%){ Revive-EN-PLACE a min(reviveHP,maxPV) ; DeactivateEffect once-per-turn }. Le filtre
    # IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter n'a PAS de HasTrait (contraste Chaos de TaintedNarthecium) et get_ReviveOnOverkill
    # GameCamera$$ShouldBlurBackground = 0 -> gate `NOT overkill`. Cf. loki/narthecium.py + triggers/revive_effect.py.
    "Narthecium": [NartheciumReviveAbility],
    # MasterAnnihilator (passif admecDominus << Vitruvius >>) = POSE du marqueur 1249 avec REMOVE-BY-SOURCE :
    # `On(0x26=NormalAttack) & OwnerIsCaster & AreEnemies` -> `RemoveEffect(OwnerOfEffect(EffectsFromUnitSource(
    # Self, 1249)), 1249) + AddEffect(1249, Target())`. L'effet (+1 coup recu non-Psychic) etait deja porte
    # (hits.py) mais JAMAIS pose. Cf. loki/master_annihilator.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour).
    "MasterAnnihilator": [MasterAnnihilatorMarkAbility],
    # FleshmetalGuns (passif blackObliterator << Volk >>) = ROTATION turn-start des 3 effets d'arme :
    # `On(0x16=TurnStart_Actions) & IsTurnOf(Self)` -> `RemoveEffect x3 + If(Modulo(UnitTurnsStarted(Self),
    # 3, k), AddEffect(1067|1212|1221))`. Les 3 effets (+2 coups Melta/Flame/HeavyRound) etaient deja portes
    # (hits.py) mais SEUL celui du seed vivait. Cf. loki/fleshmetal_guns.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArchContaminatorAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour).
    # `FleshmetalGuns` porte DEUX abilities natives distinctes (deux slots voisins de la table de
    # pointeurs de methodes) : la ROTATION turn-start (`FleshMetalGunsAbility`) et le volet TILE-EFFECT
    # (`FleshMetalGuns_TileEffectAbility`, `On(0x10=DamageDealt)` -> DespoiledGround sur la tuile de la
    # victime pendant le round WarpHail, #85). Le gate `HasEffect(Self, 0x4c5)` du second rend
    # l'inscription inconditionnelle INERTE hors round WarpHail.
    "FleshmetalGuns": [FleshmetalGunsRotationAbility, FleshmetalGunsTileEffectAbility],
    # TerrifyingCrescendo (passif emperNoiseMarine << Shiron >>) = ACCUMULATION du stack de l'effet 1424
    # (deja porte #204, magnitude x level) : disjonction `On(0=UnitDeath) & OwnerIsActor & TargetIsOverkilled`
    # | `On(0x3d=PreEffectAdded) & OwnerIsActor & TriggeringEffectIs(1065=Pinned)` -> `AddEffectOrIncreaseLevel(
    # 1424, +1, max=buffMaxLevel=6)`. Cf. loki/terrifying_crescendo.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour).
    "TerrifyingCrescendo": [TerrifyingCrescendoOverkillAbility, TerrifyingCrescendoSuppressAbility],
    # HeadClaimer (passif `blackHaarken` << Haarken >>, TriggeredAbilityType 0x407 = 1031, #947) =
    # ACCUMULATION des DEUX compteurs de tetes (effets 1028/1029, portes par
    # `entities/effects/loki/head_claimer.py`, magnitude x level) : disjonction
    # `OnPreDeath2(overkill: true, steppable: false)` = `On(2 = PreUnitDeath_2) &
    # NOT TargetHasTrait(Steppable)` | `On(0x34 = UnitFled)`, puis `& get_OwnerIsActor &
    # NOT AreFriends(Owner, Target) & NOT TriggeringAbilityIs(1080 = ItsGonnaBlow)` ->
    # `AddEffectOrIncreaseLevel(1028, +1, SANS cap) & If(IsHero(Target),
    # AddEffectOrIncreaseLevel(1029, +1, SANS cap))`. DEUX classes pour la disjonction, MEME patron
    # que TerrifyingCrescendo juste au-dessus. ⚠ La branche `UnitFled` est INERTE offline (aucun
    # vecteur de fuite n'est emis) -- residu #947-r1, declare dans loki/head_claimer.py.
    "HeadClaimer": [HeadClaimerOnDeathAbility, HeadClaimerOnFledAbility],
    # TrophyTaker (passif `worldExecutions` << Tarvakh >>, #951) -- SEUL le bras `On(UnitDefeated)`
    # de la disjonction du `CreateTrigger` entre ici. L'autre bras (`<DSLTriggers+0x30>` =
    # `On(AbilityInit) & OwnerIsActor`) pose l'effet 1289 sur le porteur, et ce canal-la est deja
    # servi par `decisionView.effects` (l'effet n'a AUCUNE `CreateActiveCondition`, donc il y est
    # ACTIF) -> pas d'entree `ABILITY_INIT_OWNER_EFFECTS`, cf. `entities/effects/loki/trophy_taker.py`.
    "TrophyTaker": [TrophyTakerOnUnitDefeatedAbility],
    # FuelledByFury (passif ultraTitus << Titus >>) = ACCUMULATION du stack de l'effet 1323 (magnitude
    # x level portee en meme temps, `entities/effects/loki/extra_damage.py`) : `On(0xe=UnitPostAbility)
    # & AreFriends(Owner, caster) & HasTrait(caster, 0x10=Hero) & !HasTrait(caster, 0x419=MachineOfWar)
    # & IsActiveAbilityCountedAsUsed(false)` -> `If(HasEffect, IncreaseEffectLevel(+1, SANS cap),
    # AddEffect(1323))`. Cf. loki/fuelled_by_fury.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateBehaviour).
    # + volet REVIVE (#88 residu A1) : `FuelledByFury_ReviveAbility` = `On(3=PendingDeathAdded) &
    # HasEffect(self, 1324 actif) & AreEqual(caster, self) & TriggeringAbilityIs(1024=FinalJustice)` ->
    # `Revive(self, self, ConfigVar('hp'), healType=0, sourceId=1251)`. Le passif porte les DEUX
    # triggered-abilities (l'`ArraySet` du marqueur 1324 n'enregistre, lui, que ses 3 triggers d'etat).
    "FuelledByFury": [FuelledByFuryExtraDamageAbility, FuelledByFuryReviveAbility],
    # Deathwing (passif `darkaTerminator` << Baraqiel >>, TriggeredAbilityType 0x4dd=1245) :
    # `On(9 = Attack, ownerNeedsToBeAlive: true) & get_OwnerIsTarget & WasBlock()` ->
    # `If(HasEffect(Owner, 0x526=1318), IncreaseEffectLevel(+1, SANS cap),
    #    AddEffect(1318, AbilityStateReference, Owner, Owner, turns = TurnsFromRounds(1)))`.
    # TROIS termes au trigger, et c'est tout -- aucun gate de profil, de bouclier ni de degat aux PV
    # (contraste `TerminatorArmour_ReduceDmg`, que le MEME porteur transporte via son trait).
    # Cf. loki/deathwing.py ; la MAGNITUDE vit dans `entities/effects/loki/deathwing.py`.
    "Deathwing": [DeathwingAbility],
    # AnvilShield (passif spaceRockfist << Arjac >>) = volet ON-BLOCK `ApplyIce` : `On(UnitBlocked=0x3c) &
    # OwnerIsTarget & IsUnit(caster)` -> `AddEffect(Ice=0x11, source=Self, cible=CasterTile)` (la tuile de
    # l'attaquant BLOQUE gele). L'effet de tuile Ice etait deja porte ; c'est le DISPATCH `On(0x3c = UnitBlocked)` qui
    # manquait. Volets Stun / FrozenAttackerAdvantage / init-effects = residus documentes.
    # Cf. loki/anvil_shield.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour ; emetteur IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers).
    # #100 : les DEUX autres volets on-block sont desormais portes (ils etaient du dead-code faute de
    # leurs prerequis) — `ApplyStun` (`On(0x3c = UnitBlocked) & IsMeleeAttack & (HasEffect(1200)|HasEffect(1201))` ->
    # Stunned sur l'attaquant) et `FrozenAttackerAdvantage` (`On(0x2a=PreUnitAbility) & IsNormalAttack &
    # IsUnitOnTileWithEffect(caster, Ice)` -> +20 % block chance transitoire).
    "AnvilShield": [AnvilShieldApplyIceAbility, AnvilShieldApplyStunAbility,
                    AnvilShieldFrozenAttackerAdvantageAbility],
    # --- #95-RESTE2 : chaine SwornProtector -> Kell -> ListenUpMaggots ---------------------------
    # SwornProtector (passif `astraCreed`, triggered 1050) = `On(PreUnitAbility=0x2a)` : a la PREMIERE
    # attaque ennemie visant Creed, Kell (`astraSmnKell`) apparait sur un hex libre adjacent et prend
    # sa place (TriggerAbility -> SwornProtector_Protect). Cf. loki/sworn_protector.py.
    "SwornProtector": [SwornProtectorSummonKellAbility],
    # SwornProtector_Protect (passif `astraSmnKell`, triggered 1075) = MEME event : a chaque attaque
    # suivante visant Creed, Kell re-echange sa position avec lui et encaisse.
    "SwornProtector_Protect": [SwornProtectorProtectSwitchAbility],
    # HazeOfCorruption (passif `deathBlightlord` << Maladus >>, triggered 1076) = MEME event
    # `On(PreUnitAbility=0x2a)`, gate `get_OwnerIsCaster` SEUL : a l'entree de CHAQUE ability du
    # porteur, `HazeOfCorruption_TargetFinderAbility$$CreateBehaviour` resout
    # `PickRandomly(Damageable(AdjacentEnemies(Self) & AdjacentFriends(Target)), 2)` -- donc
    # `min(len(pool), 2)` `genrand_int32` AVANT tout coup -- et bonde les relais (effet 1077).
    # C'etait la source des 2 tirages manquants de case-207. Cf. loki/haze_of_corruption.py.
    # case-209 : le passif porte un SECOND volet, `HazeCorruption_BonusHitAbility` (orthographe
    # native SANS le « Of ») -- `On(PreUnitDeath=1) & OwnerIsActor & IsDead(Target) & !IsDead(Owner)
    # & !TriggeringEffectIs(0x435)` -> 1 coup `extraDmg` profil Toxic sur la cible qui vient de
    # tomber, dont le degat DEBORDE integralement vers le relais bonde (l'effet 1077 ci-dessous).
    "HazeOfCorruption": [HazeOfCorruptionTargetFinderAbility, HazeCorruptionBonusHitAbility],
    # MartialSuperiority (passif `templChampion` << Brother Jaeger >>, triggered 0x444=1092) = MEME
    # event `On(PreUnitAbility=0x2a)` : quand Jaeger est CIBLE d'une attaque de MELEE pendant le tour
    # ADVERSE, il frappe l'attaquant 2x profil Power AVANT que l'attaque ne s'execute
    # (`MartialSuperiorityAbility$$CreateTrigger`/`$$CreateBehaviour`, cible = `Actor@0x158` ==
    # `$$GetInitialTarget`). Si la riposte TUE l'attaquant, le gate acteur-mort POST-`On(0x2a = PreUnitAbility)` de
    # `ActiveAbilityOperation$$ExecuteInternal` annule l'attaque entrante. Cf. loki/martial_superiority.py.
    "MartialSuperiority": [MartialSuperiorityRiposteAbility],
    # RefusalToBeOutdone (passif `emperExultant` « Laviscus », triggered 0x5a1 = 1441) -- l'OUTRAGE
    # (#965). TROIS entrees pour DEUX classes natives : le port est indexe par `event_id`, or
    # `...RefusalToBeOutdoneAbility$$CreateTrigger` et celui de sa sous-ability de reset sont chacun
    # une DISJONCTION (patron `HeavyWarpFlamer`). `...RefusalToBeOutdone_ResetStatsAbility` n'a
    # AUCUN ordinal `TriggeredAbilityType` propre (l'enum natif ne porte que 1441 et 1554 pour ces
    # familles) et `emperExultant` n'a qu'UN passif au gameconfig : c'est une sous-ability montee
    # par la principale, d'ou la MEME cle de registre et le MEME `AbilityOrEffect` de sac.
    # La branche `On(0x4b = UnitTransformed) & OwnerIsTarget` n'est PAS cablee : cet event n'a aucun
    # emetteur cote port (mesure #965) -- residu #965-r1.
    "RefusalToBeOutdone": [RefusalToBeOutdoneRecordHitAbility,
                           RefusalToBeOutdoneResetOnTurnEndAbility,
                           RefusalToBeOutdoneResetOnNormalAttackAbility],
    # WhisperingWeb (passif `eldarLhykhis`, triggered 0x62a = 1554) -- la TOILE MONO-CIBLE (#965) :
    # `On(0x26 = NormalAttack) & IsRangedAttack & OwnerIsCaster & AreEnemies(Target, Caster)` ->
    # `RemoveEffect(<toiles deja posees PAR Lhykhis>) + AddBondEffect(0x62b = 1579, Target)`.
    # ⚠ Seule l'ABILITY (la pose) est portee. La MAGNITUDE de l'effet 1579
    # (`ConfigVar(extraDmg) * CurrentHitIndex()`) est un residu #965-r2 : son canal d'accueil
    # (`create_effect_damage_malus_for_defense`) n'a pas `hit_index` dans son `attacker_ctx`, et
    # `defender_modifiers` est appele UNE FOIS PAR ATTAQUE, avant la boucle de coups.
    "WhisperingWeb": [WhisperingWebAbility],
    # ListenUpMaggots (passif `astraSmnKell`, triggered 1063) = `On(AbilityInit=0x21)` : pose l'effet
    # 0x426 sur Kell, qui ecrit `+1 nrOfSummons` / `+3 range` sur son PARENT (Creed) via
    # `AddUnitActiveAbilityModification` -- SEULE source non nulle de `GetAbilityStatModification`.
    "ListenUpMaggots": [ListenUpMaggotsAddEffectAbility],
    # StormboyzStrike (passif `orksNpc6Stormboy`, triggered 0x475=1141) = MEME event
    # `On(AbilityInit=0x21)`, avec DEUX gates en plus (`UnitTurnsStarted(Owner) == 0` et
    # `NOT HasFlag(Owner, Moved)`) : a l'init, l'unite QUITTE le plateau
    # (`RemoveUnitFromItsTiles(Owner, true)`) et prend 1140 `StormboyzStrike_TeleportingIn` pour
    # 2 TOURS -- l'etat qui detourne son pathfinder vers `StormboyzStrikePathfinder` (pool
    # BOARD-WIDE). Cf. loki/stormboyz_strike.py -- tranche 3/3 de `#366-r1-tunnel-family`.
    # #448-r1 : les DEUX AUTRES classes du meme `TriggeredAbilityType` 1141 entrent ici. Le builder
    # `AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_134` en construit
    # TROIS (contre UNE pour `FullThrottle`/`b__28_137`) -> le passif les monte TOUTES :
    #   * `_FallbackAbility` -- `On(0x28 = UnitFinishedTurn) & OwnerIsActor & HasEffect(Owner, 0x474,
    #     onlyActive: false, 6)` -> `(MoveUnit(Caster, <sel>) & AddEffect(0x49b = 1179, <sel>,
    #     turns: 1)) & If(Count(Tiles(Caster)) == 0, RemoveEffect(Owner, 0x474) & Kill(Caster))`,
    #     `<sel> = PickFirstN(SortTilesByUtility(CanAddUnit(AllTiles), Caster, 6 = UnitMovement), 1)`
    #     -- le MEME objet-noeud pour le move ET la marque, d'ou le quirk #425 (la tuile marquee
    #     n'est PAS celle d'atterrissage). SEULE poseuse de 1179.
    #   * `_MissAbility` -- `On(0x1f = PreUnitMove) & OwnerIsActor & HasEffect(...)` ->
    #     `Inform{0x79} & If(Maybe(chance = 20), OverrideUnitMovementTarget(Owner, PickRandomly(
    #     CanAddUnit(AdjacentTiles(<TargetTiles>)), 1))) & RemoveEffect(Caster, 0x474) &
    #     TriggerAbility(Caster, 0x46e = 1134 FullThrottle)`.
    # ⚠ Le 3e terme du Fallback est un `IfBehaviour`, PAS un `PerformAIMovementBehaviour` : le ctor
    # nomme ainsi dans les tables est un corps DEDUPLIQUE (cf. l'en-tete de loki/stormboyz_strike.py).
    "StormboyzStrike": [StormboyzStrikeTeleportAbility, StormboyzStrikeFallbackAbility,
                        StormboyzStrikeMissAbility],
    # --- Genestealer Cults : les 2 passifs HERO restants du parc GS ------------------------------
    # CosmicHorror (passif `genesPatriarch` << The Patermine >>) = DEUX abilities natives distinctes :
    #   * `On(0x36=UnitDefeated) & OwnerIsActor & AreEnemies & NOT HasTrait(Steppable)` -> decoy sur la
    #     tuile du mort + `Foreach(ennemis de l'anneau, Maybe(chance){ TriggerAbility(BattleFatigue)
    #     & If(IsAlive, AddEffect(Pinned 1065)) })` -- UN SEUL Maybe pour les DEUX volets (le << 60 %
    #     et 60 % >> de l'i2 est de la prose : le decompile n'a qu'un tirage par victime) ;
    #   * `On(0x35=PostUnitKill) & OwnerIsActor & AreFriends & HasTrait(Decoy)` -> `Heal(self, hp)`
    #     (le << marcher sur un decoy >> est en realite le CRUSH du decoy, qui passe par
    #     `KillUnitOperation$$Execute` -> `On(0x35 = PostUnitKill)`).
    # Cf. loki/cosmic_horror.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateTrigger /
    # ...$$CreateBehaviour / IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnMoveAbility$$CreateTrigger).
    "CosmicHorror": [CosmicHorrorOnKillAbility, CosmicHorrorOnMoveAbility],
    # Possession (passif `blackPossession` << Archimatos >>, `TriggeredAbilityType` 0x40a = 1034),
    # #955 : `On(0x35 = PostUnitKill, ownerAlive) & OwnerIsActor & AreEnemies(Owner, Target)
    # & NOT IsObjectOrSteppable(Target) & NOT TriggeringAbilityIs(0x438 = ItsGonnaBlow)` ->
    # `If(NOT IsDefeatedByMeleeAttack(Target), Spawn(unitId_2, ordinal 2), Spawn(unitId, ordinal 1))`
    # sur `PickRandomly(FreeTilesOrAdjacentFreeTiles(Tiles(Target)), 1)`. Le passif n'a NI effet NI
    # playbook -- les classes `AttemptedPossession*` sont celles de l'ACTIVE 1101 de `thousSorcerer`.
    # Cf. loki/possession.py + docs/rl/case-955-summary-execution-et-possession.md.
    "Possession": [PossessionSummonOnKillAbility],
    # SummaryExecution (passif `astraYarrick` << Yarrick >>, `TriggeredAbilityType` 0x409 = 1033),
    # #955 : `NOT HasEffect(Owner, 0x407 = SummaryExecution_Effect, false, 6) & On(0x33 =
    # PreUnitFled, ownerAlive) & AreFriends(Owner, Actor) & TriggeringAbilityIs(0x401 =
    # BattleFatigue)` -> `AddDynamicStatModifierEffectToOwner(0x407, Attack) & Kill(Owner, Actor,
    # ForDirectKill)`. Le verrou << the FIRST time >> EST la presence de l'effet 1031.
    # ⚠ La face AURA du kit (1043, posee au chargement) n'est PAS ici : elle a le trigger d'INIT
    # partage, donc elle vit dans `effects.factory.ABILITY_INIT_OWNER_EFFECTS`.
    # Cf. loki/summary_execution.py + docs/rl/case-955-summary-execution-et-possession.md.
    "SummaryExecution": [SummaryExecutionAbility],
    # HaywireMineSteppable (passif du SUMMON `astarSmnHaywireMine` d'`astarCyrus`, et du npc
    # `astarNpc1HaywireMine`) = la MINE QUI EXPLOSE quand on marche dessus, #462-...-c-r3-r1-r3 :
    # `OnPreDeath(ignoreOverkill=1) & OwnerIsTarget & HasDeathReason(Owner, DamageReason.Steppable)
    # & NOT HasTrait(Actor, Steppable) & IsAlive(Actor) & AreEnemies(Owner, Actor)` ->
    # `If(HasTrait(Actor, Mechanical), atk1 + atk2, atk1)`, `atk*` =
    # `AttackWithAbilityDamage(Owner, Actor, RandomAmount(minDmg, maxDmg), <profil>, <coups>)`.
    # C'est le SEUL consommateur du canal `HasDeathReason(..., Steppable)`, donc la preuve directe
    # que le crush publie `On(1)` avec sa raison (mesure live : Amount=1403 profil Blast).
    # Cf. loki/haywire_mine.py.
    "HaywireMineSteppable": [HaywireMineSteppableAbility],
    # HaywireMine (passif `astarCyrus` << Haywire Mine >>, `TriggeredAbilityType` 0x5fb = 1531,
    # #462-r4b-r1-r1-r1-r1-c-r3-r1-r5) = la POSE de la mine que l'entree ci-dessus fait exploser.
    # TROIS entrees pour DEUX classes natives de MEME id (le patron `DawnBlade_Heal`/`_Init`) :
    #   * `HaywireMineAbility$$CreateTrigger` est un `op_BitwiseOr` -> ses DEUX disjonctions sont
    #     des entrees SEPAREES ici (meme patron qu'ActOfFaith / MyWillBeDoneOverlord) :
    #       - `On(4 = UnitAfterMove) & OwnerIsActor & TriggeringAbilityIsNone` -> pose sur la tuile
    #         QUITTEE (`PreviousTile`) ;
    #       - `On(0x29 = UnitFinishedTurnNormally) & OwnerIsActor & AmountIsZero(GetPersistentData)`
    #         -> pose de fin d'activation (tuile adjacente de meilleure utilite si l'unite n'a pas
    #         bouge) ;
    #   * `HaywireMine_ResetAbility` (`On(0x28 = UnitFinishedTurn) & OwnerIsActor` ->
    #     `ClearPersistentData`) RE-ARME le gate d'un tour a l'autre. Elle n'a PAS d'entree propre
    #     dans `TriggeredAbilityType` : c'est la 2e classe du meme id, d'ou l'inscription sous le
    #     MEME nom de kit.
    # L'ordre `On(0x28)` PUIS `On(0x29)` de `FinishUnitTurnOperation$$Execute` est ce qui rend le
    # gate persistant toujours ouvert a la fin d'une activation normale -- mesure live, cf.
    # `docs/rl/case-462-r4b-r1-r1-r1-r1-c-r3-r1-r5-pose-mine-haywire.md`. Cf. loki/haywire_mine.py.
    "HaywireMine": [HaywireMinePlaceOnMoveAbility, HaywireMinePlaceOnTurnEndAbility,
                    HaywireMineResetAbility],
    # Neuroparasite (passif `tyranNeurothrope` << Neurothrope >> + 6 npc, #462-r4b-r1-r1-r1) = la POSE
    # du parasite : `On(9 = Attack) & OwnerIsCaster & !HasEffect(Target, 0x4c2) & IsUnit(Target) &
    # CurrentAttackDamageProfilesContain(0xd = Psychic) & !(OwnerIsActor & OwnerIsTarget)` ->
    # `AddBondEffect(0x4c2 = 1218, abilityState, source: Owner, targets: Target, bondedEntity: Owner,
    # options: <vide> = PERMANENT)`. L'effet 1218 portait deja son additif de degat defenseur
    # (`entities/effects/loki/damage_reduction.py::NeuroparasiteEffect`, magnitude fermee par #553)
    # mais AUCUN vecteur offline ne le POSAIT : en self-play 100 % porte le parasite n'apparaissait
    # jamais. Sa MONTEE EN NIVEAU vit dans `EFFECT_TRIGGERS[1218]`. Cf. loki/neuroparasite.py.
    "Neuroparasite": [NeuroparasiteAddBondEffectAbility],
    # PropheticSentinel (passif de kit `thousSekhetar` << Sekhetar Robot >>, TriggeredAbilityType
    # 0x607 = 1543) = DEUX classes natives sous le MEME id, et une SEULE entre ici :
    #   * `PropheticSentinel_AddBuffAbility` : trigger HERITE `<DSLTriggers+0x30>` =
    #     `On(0x21 = AbilityInit) & get_OwnerIsActor` -> trois `AddStaticStatModifierEffectToOwner`
    #     PERMANENTS. C'est un owner-effect posé au spawn : son canal est
    #     `factory.ABILITY_INIT_OWNER_EFFECTS["PropheticSentinel"]`, PAS ce registre.
    #   * `PropheticSentinel_OverwatchAbility` (ici) : `On(0x17 = TurnEnd) & IsTurnOf(Owner) &
    #     AmountIsEqualOrGreater(Count(UnitsWithTrait(AdjacentFriends(Caster, CasterTile, 1),
    #     0x3ea = Psyker, 3)), Direct(1))` -> `ActivateEffect(Owner, 0x3f1 = Overwatch_AutoAttack)`
    #     = RE-ARMEMENT de l'overwatch en fin de son tour s'il a >= 1 ami Psyker adjacent.
    # ⚠ Les deux `CreateTrigger` sont DIFFERENTS -- l'hypothese « un trigger partage » est refutee
    # par la table des pointeurs de methodes (le corps du `CreateTrigger` d'`_AddBuffAbility` est un
    # fold ICF vers `SummaryExecutionAddBaseEffectAbility$$CreateTrigger` = `return <+0x30>`).
    # Cf. loki/prophetic_sentinel.py + entities/effects/loki/prophetic_sentinel.py.
    "PropheticSentinel": [PropheticSentinelOverwatchAbility],
    # SpiritualLeader (passif `genesMagus` << Xybia >>) = `On(0x1c=ArrivedAtFinalTile) & OwnerIsActor`
    # (fin d'activation : apres son 1er move, OU cloture de tour si elle n'a pas bouge -- les DEUX
    # emetteurs natifs de 0x1c) -> decoy sur la meilleure tuile adjacente libre, puis si >=2 decoys
    # adjacents (le neuf COMPTE, DSL lazy) summon d'un Neophyte sur l'un d'eux tire au hasard.
    # Cf. loki/spiritual_leader.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$GetAdjacentDecoys).
    "SpiritualLeader": [SpiritualLeaderAbility],
    # RealityUnbound (passif `thousTzaangor` << Yazaghor >>) = DEUX volets, DEUX classes natives,
    # DEUX events -- le passif accorde les deux :
    #   * `RealityUnboundAbility` : `On(9=Attack)` & >=3 ennemis DISTINCTS ayant recu du Psychic ce
    #     tour & `Not(HasEffect(self, 1205))` -> +extraMovement MOVEMENT (1205) et +extraRange
    #     EXTRA_RANGE (1206), 1 tour. Son `CreateTrigger` est un fold ICF vers
    #     `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$GetTrigger` (parametre
    #     par l'effectType 0x4b5) -- MEME corps que WeaverOfFate, aucune parente.
    #   * `RealityUnboundExtraMaxDamageAbility` : `On(0x42=FinalDamage)` &
    #     `HasTakenDamageOfDamageProfileThisTurnAmountOfTimes(target, Psychic, times=1)` (EGALITE
    #     STRICTE = 1re instance seulement = « each DIFFERENT enemy ») & `AreEnemies` ->
    #     +extraMaxDmg EXTRA_MAX_DAMAGE (1207, EMPILABLE), 1 tour.
    # Cf. loki/reality_unbound.py + entities/effects/loki/reality_unbound.py.
    "RealityUnbound": [RealityUnboundAbility, RealityUnboundExtraMaxDamageAbility],
    # TimeFlux (passif `thousTerminator` << Toth >>) -- le natif derive DEUX triggered-abilities du
    # MEME passiveAbility, et ce registre en est le mirror :
    #   * `TimeFluxAbility` (REGEN) : `OwnerIsActor & On(0x13=TurnStart_Other)` -> `Heal(self,
    #     Min(Sum(hpToHeal, LastHitDamageTakenLastTurn(self)), maxHpToHeal))` -- loki/time_flux.py ;
    #   * `TimeFluxReviveAbility` = `GhostReviveAbility(effectType=1186)` (POSE DU GHOST, #213) :
    #     `OwnerIsActor & On(0x1f=PreUnitMove) & OwnerIsCaster` -> `If(<4 gates>, Nothing(),
    #     AddEffect(1186, source=self, targets=CurrentTurnStartTile(self)))` -- loki/ghost_revive.py.
    "TimeFlux": [TimeFluxRegenAbility, TimeFluxReviveAbility],
    # ToughToKill (passif de kit d'`astraDreir` << Dreir >>) -- MEME forme que `TimeFlux` : le natif
    # derive DEUX triggered-abilities du MEME passiveAbility, et leurs BASES different (lues dans
    # `frida/classes.tsv`, jamais dans le nom du `.ctor`) :
    #   * `ToughToKill_HealAbility` (: `BaseTriggeredAbility`) : `On(0x13 = TurnStart_Other,
    #     ownerNeedsToBeAlive: 1) & <DSLTriggers+0x28 = IsTurnOf(Owner)>` -> `Heal(Owner,
    #     Get(GetVariableForLevel(0x20 = hpToHeal)), options = ForRegenerate)` -- SEULE inscrite ici
    #     (loki/tough_to_kill.py) ;
    #   * `ToughToKill_CritAbility` (: `AOwnerEffectTriggeredAbility`, n'override QUE
    #     `GetEffectType` = `return 0x5c0`) : owner-effect PERMANENT pose a l'init -> ce n'est PAS un
    #     vecteur de combat, donc il passe par `ABILITY_INIT_OWNER_EFFECTS` + `EFFECT_CLASSES`
    #     (`entities/effects/loki/tough_to_kill.py`), jamais par ce registre.
    "ToughToKill": [ToughToKillHealAbility],
    # Skullsmasher (passif de kit de `worldJakhal` << Macer >>, `TriggeredAbilityType 0x4c1 = 1217`,
    # #953) -- MEME forme que `ToughToKill` / `TimeFlux` : le natif derive TROIS triggered-abilities
    # du MEME passiveAbility, et leurs BASES different (lues dans `frida/classes.tsv`) :
    #   * `Skullsmasher_ActivateStunAbility` (: `BaseTriggeredAbility`) : `OnDeath(overkill: true,
    #     steppable: false) & NOT HasTrait(Target@+0x60, 0xd = Object) & get_OwnerIsActor` ->
    #     `AddEffect(0x4f0 = Skullsmasher_StunEffect, source = Owner, targets = Owner,
    #     options = <VIDE>)` = un MARQUEUR PERMANENT (aucune duree, type absent de
    #     `DefaultAmountOfRounds`) ;
    #   * `Skullsmasher_TriggerStunAbility` (: `BaseTriggeredAbility`) : `On(9 = Attack,
    #     ownerNeedsToBeAlive: true) & get_OwnerIsActor & HasEffect(Owner, 0x4f0, onlyActive: false,
    #     Both)` -> `AddEffect(0x48a = Stunned, source = Owner, targets = Target@+0x60,
    #     options = <VIDE>)` = duree `DefaultAmountOfRounds(Stunned) = 1 round` ;
    #   * `Skullsmasher_DamageEffectAbility` (: `AOwnerEffectTriggeredAbility`, n'override QUE
    #     `GetEffectType` = `return 0x4ef`) : owner-effect PERMANENT pose a l'INIT -> ce n'est PAS un
    #     vecteur de combat, donc il passe par `ABILITY_INIT_OWNER_EFFECTS` + `EFFECT_CLASSES`
    #     (`entities/effects/loki/skullsmasher.py`), jamais par ce registre.
    # ⚠ `OnDeath(a, b)` = `OnDeathEvent(0, a, b)` -> l'event est `UnitDeath = 0`, PAS
    # `PreUnitDeath_2 = 2` (l'ecart avec `HeadClaimer`, qui appelle `OnPreDeath2`). Cf.
    # loki/skullsmasher.py.
    "Skullsmasher": [SkullsmasherActivateStunAbility, SkullsmasherTriggerStunAbility],
    # ObsessiveAnnunciation (passif de kit d'`emperKakophonist` << Adamatar >>,
    # `TriggeredAbilityType 0x5a3 = 1443`, #954) : `OnDeath(overkill: true, steppable: false) &
    # TargetIsOverkilled() & NOT HasEffect(Owner@+0x30, 0x599, onlyActive: false, Both)` ->
    # `AddEffect(0x599 = ObsessiveAnnunciation_ExtraCritDmg, source = Owner, targets = Owner,
    # turns = <DSLFormulas+0x20> = Direct(1))` -> l'aura de crit est armee pour UN TOUR.
    # ⚠ Le gate d'overkill apparait DEUX FOIS et les deux ne disent PAS la meme chose : `a = true`
    # DESARME celui d'`OnDeathEvent`, c'est le `TargetIsOverkilled()` SEPARE qui l'exige.
    # ⚠ **AUCUN `get_OwnerIsActor`** : n'importe quel overkill du board arme l'aura, y compris celui
    # d'un adversaire -- l'ecart avec `TerrifyingCrescendoOverkillAbility` et
    # `HeadClaimerOnDeathAbility`, qui le portent tous deux. Cf. loki/obsessive_annunciation.py.
    # L'AUTRE effet du passif (1432, l'aura de degat) est un owner-effect d'INIT ->
    # `ABILITY_INIT_OWNER_EFFECTS`, pas ce registre.
    "ObsessiveAnnunciation": [ObsessiveAnnunciationOverkillAbility],
    # EcstaticSlaughter (passif de kit d'`emperFlawlessBlade` << Hascule >>,
    # `TriggeredAbilityType 0x5c0 = 1472`) : les DEUX branches de l'`op_BitwiseOr` de son
    # `CreateTrigger`, qui partagent le MEME `CreateBehaviour` (3 coups Eviscerate sur un ennemi
    # adjacent choisi par `Cache(First(SortUnitsByDamageUtility(Randomize(AdjacentEnemies))))`,
    # puis `AddBondEffect(0x1b = Taunted_OnlySpecificTargets, bonded = Owner, 1 round)`) :
    #   * `On(0x3e = EffectAdded) & CurrentAbilityIs(AbilityOrEffect(0x59a = EffectType.
    #     ThrillSeekers)) & get_OwnerIsTarget` -- Hascule devient *Thrilled* ;
    #   * `OnDeath(overkill: true, steppable: false) & TargetIsOverkilled() & IsNormalUnit(Target) &
    #     AreEnemies(Owner, Target, 0) & IsAdjacent(Owner, Target, 0)` -- un ennemi ADJACENT est
    #     overkill, PAR N'IMPORTE QUI (aucun `get_OwnerIsActor`, comme `ObsessiveAnnunciation`).
    # Le gate `AmountIsGreaterThanZero(AdjacentEnemies(Owner, unique, sel 3))` est COMMUN aux deux
    # (l'`op_BitwiseAnd` porte sur le OU, lu aux registres). Cf. loki/ecstatic_slaughter.py.
    # ⚠ La 1re branche exigeait le vecteur `On(0x3e)`, qui N'EXISTAIT PAS cote port -- ajoute par la
    # meme tranche (`dispatch/move_death.effect_added_triggers`, emis en fin d'`AddEffectOperation`).
    "EcstaticSlaughter": [EcstaticSlaughterOnThrilledAbility, EcstaticSlaughterOnOverkillAbility],
    # ArmourOfShriekingSouls (passif de kit d'`emperLucius`, `TriggeredAbilityType 0x598 = 1432`) :
    # `OnDeathEvent(0, overKill: true, steppable: false) & get_OwnerIsTarget & IsUnit(Actor@+0x40) &
    # AreEnemies(Actor, Owner, 0)` -> `If(NOT IsAlive(Actor), Resurrect(Owner sur Tiles(Actor)),
    # AddEffect(0x58f = ArmourOfShriekingSouls, source = Owner, targets = Actor))`.
    # ⚠ `IsUnit` est un MISLABEL ICF du pseudo-C (`RequiredByNativeCodeAttribute$$.ctor`) : son
    # pointeur de classe n'est partage qu'avec `DSLTriggers$$IsUnit`. Les TROIS autres faces vivent
    # dans `EFFECT_TRIGGERS[0x58f]`. Cf. loki/armour_of_shrieking_souls.py.
    "ArmourOfShriekingSouls": [ArmourOfShriekingSoulsOnDeathAbility],
    # EchoesFromTheWarp (passif UNIQUE de `thousNpc4Terminator`, npc) = la SECONDE instanciation de
    # `GhostReviveAbility`, parametree `effectType = 1284` -- MEME arbre, seule la branche d'amount
    # du behaviour de l'effet change (`StatAmount(src, Health, Initial)` = « Full Health »).
    # `EchoesFromTheWarpAbility` ne declare que son `.ctor` (bloc `methodPointers` lu). #366-r1.
    "EchoesFromTheWarp": [EchoesFromTheWarpAbility],
    # BarbedOvipositor (passif `tyranParasite` << Parasite of Mortrex >>) = `On(0=UnitDeath) &
    # OwnerIsActor & AreEnemies & Not(IsObjectOrSteppable(target)) & Not(TriggeringAbilityIs(
    # TriggeredAbilityType.ItsGonnaBlow=1080)) & Not(HasTrait(target, 5=Mechanical))` -> `Spawn(owner,
    # PickRandomly(CanAddUnit(Tiles(target)),1).Otherwise(PickRandomly(CanAddUnit(AdjacentTiles(
    # target)),1)), "tyranSmnRipperSwarm", WithStatsFromConfig)` : chaque kill QUALIFIANT du Parasite
    # pose un Ripper Swarm sur l'hex du mort. Aucun cap de summons dans l'arbre natif, AUCUNE
    # on-appearance (le Ripper n'attaque PAS a l'apparition -- contraste l'actif `ItItches`).
    # Cf. loki/barbed_ovipositor.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger /
    # ...$$CreateBehaviour).
    "BarbedOvipositor": [BarbedOvipositorSummonAbility],
    # SynapticLinchpin (passif `tyranWingedPrime` << Winged Prime >>, triggered 1192) =
    # `On(38=NormalAttack, ownerNeedsToBeAlive: NOT(OwnerIsActor & TriggeringAbilityIs(
    # TriggeredAbilityType.FinalJustice=1024))) & HasTrait(actor@+0x40, UnitTrait.Synapse=2024)
    # & AreFriends(owner@+0x30, actor@+0x40) & IsAlive(target@+0x60)` ->
    # `Repeat(If(NOT AmountIsEqualOrGreater(UnitsWithId(Children(owner), "tyranSmnHormagaunt",
    # OnlyAliveAndTargetable), Direct(maxSummons)), Spawn(owner, First(SortTilesByUtilityForSummon(
    # CanAddUnit(AdjacentTiles(target)), UtilityType.Tile=7, parent: caster@+0x48), 1), unitId,
    # opts{+0x18 = UseNormalAttackIfAble(activeTarget@+0x68, target@+0x60)})), Direct(nrOfSummons))` :
    # toute attaque NORMALE d'un AMI porteur de `Synapse` (le Winged Prime compris) sur un ennemi qui
    # SURVIT pose un Hormagaunt adjacent a la cible, lequel l'attaque immediatement -- sous un cap de
    # summons VIVANTS. Le 2e argument d'`On` n'est PAS une condition d'evenement : `DSLTriggers$$On`
    # rend `Event(t) & (OwnerIsAlive | !X)`, donc le passif survit a la mort de son porteur quand
    # c'est LUI qui frappe via `FinalJustice`. Cf. loki/synaptic_linchpin.py
    # (IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility$$CreateTrigger /
    # ...$$CreateBehaviour).
    "SynapticLinchpin": [SynapticLinchpinAbility],
    # FabricatorClawArray (passif `necroSpyder` << Canoptek Spyder >>, triggered 0x3ee = 1006) =
    # `On(0x1c=ArrivedAtFinalTile) & OwnerIsActor & !AmountIsZero(GetTargetSelector())` ->
    # `Repair(Owner, GetTargetSelector(), Direct(ConfigVar(0x24 = hpToRepair)), ForRepair)`, ou
    # `GetTargetSelector` = `PickRandomly(Repairable(UnitsAffectedByHealType(AdjacentFriends(Owner,1,3),
    # 1), 0,1,3), 1).Otherwise(PickRandomly(UnitsWithNegativeEffects(<le meme filtre heal-type>), 1))`.
    # RESIDU N20 de #299 : le Spyder qui bouge PUIS repare restaurait, cote port, la SEULE reparation
    # active -- mesure natif 10457 vs port 6025, ecart 4432 = hpToRepair[50] 2216 x mult 200 %.
    # Cf. loki/fabricator_claw_array.py (IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$GetTargetSelector).
    "FabricatorClawArray": [FabricatorClawArrayAbility],
    # ChampionOfTheFeast (passif `templSwordBrother` << Sword Brother Godswyl >>, `TriggeredAbilityType`
    # 0x43e = 1086 -- #419-r6-r2) = MEME event `On(0x1c = ArrivedAtFinalTile)` que FabricatorClawArray
    # ci-dessus, MEME forme de gate :
    #   `On(0x1c) & get_OwnerIsActor & !AmountIsZero(Damageable(AdjacentEnemies(Caster@+0x48,1,3)))`
    #   -> `AttackWithAttackDamage(Owner@+0x30, <cible>, MinMaxDamage(abilityState),
    #        GetDamageProfileOrDefault(DamageProfileType.Power = 0xe), GetHits(), ..., selectionType 2)
    #      op_Addition
    #      IfAlive(<cible>, AddStaticStatModifierEffect(<cible>, 0x43b = 1083, 0x10 = FixedArmor,
    #                                                   Direct(-armorReduction[lvl]), turns = NULL))`
    # ou `<cible>` = `Cache(Otherwise(PickRandomly(UnitsWithoutTrait(pool, 0x19 = Immune), 1),
    #                                 PickRandomly(pool, 1)))` -- une PREFERENCE non-Immune, pas un
    # filtre dur, et un `Cache` qui garantit UNE cible et UN tirage pour l'attaque ET le malus.
    # `On(0x1c)` porte a lui seul les DEUX branches de l'i2 (« After moving » / « if he does not
    # move, at the end of his turn ») : ce sont les deux emetteurs du MEME flag.
    # Cf. loki/champion_of_the_feast.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ChampionOfTheFeastAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$GetTarget / ...$$GetPossibleTargets).
    "ChampionOfTheFeast": [ChampionOfTheFeastAbility],
    # FuryOfTheAncients (passif `bloodMephiston` << Mephiston >>, `TriggeredAbilityType` 0x4df = 1247
    # -- #927) = QUATRIEME consommateur d'`On(0x1c = ArrivedAtFinalTile)`, MEME gate que
    # `ChampionOfTheFeast` ci-dessus :
    #   `On(0x1c) & get_OwnerIsActor & !AmountIsZero(Damageable(AdjacentEnemies(Caster@+0x48,1,3)))`
    #   -> `ChainAttackDamage(preselected = GetTarget(), jump = GetSecondTargetSelector,
    #        maxTargets = <DSLFormulas+0x20 = Direct(1)>, MinMaxDamage, profil Psychic,
    #        hits = ConfigConst(0x2f nrOfHits), extraBehaviour = AddEffect(0x528 = 1320
    #        FuryOfTheAncients -> ActiveTarget, source Owner@+0x30,
    #        TurnsFromRounds(ConfigConst(0x69 effectTurns))), chainOptions +0x12 = 1)`
    # ⚠ ET LA RESSEMBLANCE S'ARRETE LA. `ChampionOfTheFeast` pique sa cible par `PickRandomly` (avec
    # preference non-Immune) ; celui-ci la choisit par `First(SortByFormula(pool, Sum(
    # DamagePredictionFormula(ActiveTarget), DamagePredictionFormula(GetSecondTargetSelector(
    # ActiveTarget))), DESC), 1)` -- un TRI sur l'esperance de degat des DEUX maillons, `prioritizeKills
    # = false`, AUCUN tirage de cible. Et le tri, lui, consomme 2 tirages PAR CANDIDAT (son
    # `MinMaxDamage` est evalue par le slot 1 = `RandomAmount$$Calculate`), y compris quand la seconde
    # cible n'existe pas. Ne pas recopier le voisin de forme.
    # L'effet 1320 est un `IdunBattle.Entities.Effects.HealBlockingEffect` (hierarchie lue dans
    # `frida/classes.tsv`, PAS dans le pseudo-C qui designe `DeathwingEffect` par ICF) : il inscrit sa
    # cible au registre `HealthComponent+0x78` que lit `UnitExtensions$$HasHealBlockers` -> gates SOIN
    # / REPARATION / RESURRECTION. `has_heal_blockers` (attack_query.py) le lit desormais pour de vrai.
    # Cf. loki/fury_of_the_ancients.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryOfTheAncientsAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$GetTarget / ...$$GetSecondTargetSelector /
    # ...$$GetDamagePredictionFormula / ...$$GetPossibleTargets).
    "FuryOfTheAncients": [FuryOfTheAncientsAbility],
    # SanguinaryPriest (passif de kit `bloodSanguinary` << Nicodemus >>, `TriggeredAbilityType`
    # 0x510 = 1296 -- #921) = TROISIEME consommateur d'`On(0x1c = ArrivedAtFinalTile)`, mais son
    # `CreateTrigger` porte UN TERME DE PLUS que celui de `SpiritualLeader` :
    #   `On(0x1c, ownerNeedsToBeAlive = 1) & <DSLTriggers+0x28 = IsTurnOf(Owner)> & get_OwnerIsActor`
    # -> `Heal(Owner@+0x30, AdjacentFriends(Owner, unique, 3) op_Subtraction MechanicalUnits(., 3),
    #          RandomAmount(GetVariableForLevel(0x20 hpToHeal), GetVariableForLevel(0x47 maxHpToHeal)),
    #          HealBehaviourOptions.ForRegenerate)`.
    # ⚠ AUCUN filtre `UnitTrait.Immune` ici -- c'est l'ACTIF `BloodChalice` du MEME porteur qui en
    # porte un (`UnitsWithoutTrait(adj - mech, 0x19, 3)`). Ne pas recopier le voisin de forme.
    # Le `RandomAmount` est tire PAR CIBLE (`HealBehaviour$$Execute` appelle `Calculate` dans la
    # boucle d'enumeration) -- la feuille `abilities/behaviours/stats.py::Heal` a ete corrigee en
    # consequence dans le meme commit.
    # Cf. loki/sanguinary_priest.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$GetTargets).
    "SanguinaryPriest": [SanguinaryPriestAbility],
    # MedicusMinistorum (passif de kit `adeptHospitaller` << Isabella >>, `TriggeredAbilityType`
    # 0x42d = 1069) -- soin REACTIF a l'allie adjacent qui vient d'encaisser :
    #   `On(0x9 = Attack, ownerNeedsToBeAlive = 1)
    #    & AmountIsGreaterThanZero(<DSLFormulas+0x50> = CurrentDamage)
    #    & AreFriends(Target@+0x60, Owner@+0x30, 0, false)
    #    & IsAdjacent(Target@+0x60, Owner@+0x30, 3)
    #    & !get_OwnerOrOwnerTileIsTarget`
    # -> `Heal(Owner@+0x30, Target@+0x60, Get(GetVariableForLevel(0x20 = hpToHeal)),
    #          HealBehaviourOptions.ForRegenerate)`.
    # ⚠ Le sujet du soin est la CIBLE de l'attaque, PAS l'attaquant : le passif recompense l'allie
    # QUI ENCAISSE. Et le namespace natif dit `Abilities.**Active**.Loki` alors que la base lue dans
    # `classes.tsv` est `BaseTriggeredAbility` -- c'est bien une passiveAbility.
    # ⚠ « non-mechanical » et « unless it is defeated » du tooltip ne sont PAS des noeuds de l'arbre
    # (le selecteur est `Target` NU) : ils vivent sous la feuille, dans
    # `AttackQuery$$EntityCanBeHealed` (`IsMachine` / `IsDamagedUnit` / `IsAffectedByHealType(., 0)`)
    # que `HealUnitOperation` appelle deja. NE PAS recopier la soustraction `MechanicalUnits` de son
    # voisin de forme `SanguinaryPriestAbility$$GetTargets` : elle serait plus STRICTE que le natif.
    # Cf. loki/medicus_ministorum.py.
    "MedicusMinistorum": [MedicusMinistorumAbility],
    # AggressiveOnslaught (passif de kit `bloodIntercessor` << Mataneo >>, `TriggeredAbilityType`
    # 0x4e0 = 1248) -- TROIS classes natives pour UN id de kit (forme `LetTheGalaxyBurn`), toutes
    # base `BaseTriggeredAbility` (lue dans `classes.tsv`) :
    #   * `_PrepareAbility`  : `On(0x5 = PreAttack) & OwnerIsAlive & OwnerIsCaster`
    #                          -> `SetPersistentData(Owner, Get("IsCharging"), IsCharging(Caster, Target))` ;
    #   * `_SummonAbility`   : `(On(0xb = UnitAbility) & OwnerIsAlive & OwnerIsCaster)
    #                           & (AmountIsGreaterThanZero(GetPersistentData(Owner, "IsCharging"))
    #                              | IsCharging(Caster, Target))`
    #                          -> `Spawn(Caster, Cache(First(SortByDistance(CanAddUnit(AdjacentTiles(
    #                             TargetTiles@+0x78)), Caster@+0x48), nrOfSummons)), "bloodSmnIntercessor",
    #                             options{OnSpawn = UseNormalAttackIfAble(ActiveTarget@+0x68, Target@+0x60)})` ;
    #   * `_UnsummonAbility` : `On(0x12 = TurnStart_EffectActivation) & OwnerIsAlive & IsTurnOf(Owner)
    #                          & AmountIsGreaterThanZero(Children(Owner))` -> `RemoveUnit(Children(Owner))`.
    # ⚠ Le `Prepare` n'est PAS redondant : `On(0xb)` est emis par `ActiveAbilityOperation$$
    # ExecuteInternal` APRES le behaviour d'attaque, donc le drapeau capture au `PreAttack` est la
    # voie NOMINALE ; le `IsCharging` en direct est le SECOND bras du `op_BitwiseOr`.
    # ⚠ Le spawn est adjacent a la CIBLE (`AdjacentTiles(TargetTiles@+0x78)`) mais TRIE par distance
    # au CASTER (`SortByDistance(., Caster@+0x48)`) -- deux selecteurs differents, lus tels quels.
    # ⚠ `First` est la surcharge `PickFirstN` (les N premiers), tranchee par la SIGNATURE que rend
    # `probe_951_call_targets.py` : `PickAtIndex` aurait spawn 1 summon au lieu de 2.
    # ⚠ Le desinvoque passe par `ChildrenOf` (les enfants PERSISTANTS lus dans l'etat), JAMAIS par
    # `Children` (l'accumulateur `ctx.children` du cast courant) : l'Unsummon court a un TOUR
    # ULTERIEUR du spawn, ou cet accumulateur est vide -- no-op silencieux.
    # Cf. loki/aggressive_onslaught.py.
    "AggressiveOnslaught": [AggressiveOnslaughtPrepareAbility,
                            AggressiveOnslaughtSummonAbility,
                            AggressiveOnslaughtUnsummonAbility],
    # RedRampage (passif de kit `bloodTerminator` << Cezare >>, `TriggeredAbilityType` 0x60f = 1551
    # -- #963) -- DEUX classes natives pour UN id de kit, toutes deux base `BaseTriggeredAbility`
    # (lue dans `classes.tsv`) :
    #   * `RedRampage_AttackAbility` : `On(0x1c = ArrivedAtFinalTile) & get_OwnerIsActor
    #     & !AmountIsZero(AdjacentEnemies(Owner@+0x30, 1, 3))`
    #     -> `AttackWithAttackDamage(Owner@+0x30, <le MEME selecteur NU>, MinMaxDamage(abilityState),
    #        GetDamageProfile(), GetHits(), ..., selectionType 2 OnlyTargetable)` ;
    #   * `RedRampage_BuffAbility`   : `On(0x36 = UnitDefeated) & <DSLTriggers+0x28 = IsTurnOf(Owner)>
    #     & AreEnemies(Owner@+0x30, Target@+0x60, 1 ByOriginalTeam) & get_OwnerIsActor
    #     & !AmountIsEqual(EffectRemainingTurns(EffectFromOwner(Owner, 0x622)), <turns>)`
    #     -> `If(HasEffect(Owner, 0x622, 0, 6 Both), ChangeEffectTurns(Owner, 0x622, <turns>, 1 Set),
    #        AddStaticStatModifierEffect(Owner, 0x622 RedRampage_ExtraMovement, 1 Movement,
    #        Get(GetNumberConstant(0xe extraMovement)), <turns>, isHidden 0))`,
    #     ou `<turns>` = `RedRampage_BuffAbility$$GetEffectTurnsAfterDefeatedEnemy` =
    #     `Sum(<DSLFormulas+0x20> = Direct(1), TurnsFromRounds(1))`.
    # ⚠ CINQUIEME consommateur d'`On(0x1c)`, MEME gate que `ChampionOfTheFeast` / `FuryOfTheAncients`
    # -- ET LA RESSEMBLANCE S'ARRETE LA : les deux autres enveloppent leur pool dans un
    # `Cache`/`PickRandomly` et ne frappent QU'UNE cible ; celui-ci passe le selecteur NU et frappe
    # TOUS les ennemis adjacents, sans consommer le moindre tirage PRNG. Ne pas recopier le voisin.
    # ⚠ Le buff n'est PAS cumulatif : la branche `if` RE-TIME (`ChangeType.Set`), elle ne re-pose
    # rien -- et `NeedsEffectUpdateAfterDefeatedEnemy` coupe deja le fire quand la duree est atteinte.
    # Cf. loki/red_rampage.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.RedRampage_AttackAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$GetTargets ; ...RedRampage_BuffAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$NeedsEffectUpdateAfterDefeatedEnemy /
    # ...$$GetEffectTurnsAfterDefeatedEnemy).
    "RedRampage": [RedRampageAttackAbility, RedRampageBuffAbility],
    # GeminaeSuperia (passif de kit `adeptCelestine` << Celestine >>, `TriggeredAbilityType`
    # 0x418 = 1048 -- #963). Le namespace natif dit `Abilities.**Active**.Loki` alors que la base LUE
    # dans `classes.tsv` est `BaseTriggeredAbility` : c'est bien une passiveAbility (meme piege que
    # `MedicusMinistorum`).
    #   `On(0x39 = PreDamageTaken, ownerNeedsToBeAlive = 0) & IsFirstDamagingHitInSeries
    #    & get_OwnerIsTarget & AmountIsGreaterThanZero(GetPossibleSpawnTiles()) & SummonLimit()`
    #   -> `Spawn(Owner@+0x30, PickRandomly(GetPossibleSpawnTiles(), 1, 0, 0x7fffffff, false),
    #            GetStringConstant(0 unitId), SpawnUnitOptions.WithStatsFromConfig(config,
    #            abilityState){ +0x10 = AddEffect(0x425 GeminaeSuperia_JustSummonedEffect,
    #            AbilityStateReference, Target@+0x60, turns = null) })
    #      op_BitwiseAnd
    #      TriggerAbility(Last(Children(Owner@+0x30), 1, true), 0x419 = Lifewards,
    #                     actor = Actor@+0x40, caster = Caster@+0x48, target = Owner@+0x30,
    #                     unitFeetTiles = null, selectionType 1 OnlyAlive, ignoreUnitHavingAbility 0)`
    # avec `GetPossibleSpawnTiles` = `CanAddUnit(AdjacentTiles(Owner) op_Subtraction
    # PendingMovingTile(Owner))` et `SummonLimit` = `!AmountIsEqualOrGreater(UnitsWithId(
    # Children(Owner), GetStringConstant(0), 0 Any), Get(2))`. ⚠ Le `0` du `UnitsWithId` est
    # `UnitSelectionType.Any` et `DSLSelectors$$Children` n'a AUCUN filtre `alive` : le cap compte
    # donc les Geminae POSEES, MORTES COMPRISES -- c'est bien le « twice per battle » de l'i2, pas
    # « deux vivantes a la fois ». Et `Get(2)` est le LITTERAL 2, ecrit dans l'ability native, pas
    # une variable de config.
    # ⚠ La face DECISION (`IdunBattle.AI.Playbook.Loki.GeminaeSuperiaPlaybook`) etait DEJA portee
    # depuis case-165b (`engine/playbook/geminae_superia.py`) ; seule la face COMBAT manquait, et
    # DEUX lecteurs de l'effet 1061 l'attendaient (`operations/spawn.py`, `abilities/loki/momentum.py`,
    # tous deux annotes « NO-OP offline tant qu'aucun poseur de 1061 n'est porte »).
    # Cf. loki/geminae_superia.py (IdunBattleLogic.Entities.Abilities.Active.Loki.GeminaeSuperiaAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$GetPossibleSpawnTiles / ...$$SummonLimit).
    "GeminaeSuperia": [GeminaeSuperiaAbility],
    # SaviorProtocols (passif des SIX drones T'au -- 3 npc `tauNpc*Drone*` + 3 SUMMONS
    # `tauSmn*Drone*` --, `TriggeredAbilityType` 0x460 = 1120 ; #1020) :
    #   `On(0x39 = PreDamageTaken, ownerNeedsToBeAlive = 0) & TargetIsValidTrigger()
    #    & IsAdjacent(Owner@+0x30, Target@+0x60, 0) & !TriggeringAbilityIs(A)
    #    & !TriggeringAbilityIs(B)`
    #   -> `If(Maybe(ConfigConst(0x2a = chance, abilityState)),
    #          TransferDamage(caster = Caster@+0x48, originalTarget = Target@+0x60,
    #                         transferTarget = Owner@+0x30, <+0x88>, <+0x90>), null)`
    # avec `TargetIsValidTrigger` = `AreFriends(Target, Owner) & HasFaction(Target, 9 = Tau, 3)
    # & !ActorHasTriggeredAbility(Target, 0x460) & !AreEqual(Target, Owner)`.
    # ⚠ Le `Maybe` est la surcharge **PREDICAT** (`DSLTriggers$$Maybe` -> `MaybeTrigger`), pas le
    # noeud EFFET homonyme : c'est la CONDITION de l'`If`, pas un enveloppeur de behaviour.
    # ⚠ `TransferDamage` **CONSOMME** le `Nullable<DamageAppliedResult>` de `FillUpStatComponent
    # +0x64` (`TransferDamageOperation$$GetDamage` y ecrit le zero) : le degat est DEPLACE, pas
    # duplique. C'est l'etage #1020 (`damage.py::_pre_damage_taken_per_hit`) qui rend ce canal
    # existant -- avant lui le retour du dispatch etait jete et rien ne pouvait annuler le degat.
    # ⚠ La face DECISION (`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook`, volets ATTACK et
    # MOVE) etait deja portee (#443 / #443-r1, `engine/playbook/savior_protocols.py`).
    # Cf. loki/savior_protocols.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$TargetIsValidTrigger).
    "SaviorProtocols": [SaviorProtocolsAbility],
    # RelentlessMarch (passif `necroWarden` << Makhotep >>, `TriggeredAbilityType` 0x3ec = 1004 --
    # HOMONYME d'id avec `ActiveAbilityType` 1004 `MortisRound`, #328) :
    # `On(TurnStart_Other=0x13) & <DSLTriggers+0x28 = IsTurnOf(Owner)>` ->
    #   `AddEffect(0x3f3 RelentlessMarch_Effect, turns = Nullable<int>(1))` sur
    #   `UnitsWithoutTrait(Friends(AdjacentUnits(Owner)), 0x418 Stationary)`
    # + `Repair(Owner, Friends(AdjacentUnits(Owner)), Direct(hpToRepair[lvl]), ForRepair)`.
    # ⚠ Le filtre `Stationary` ne porte QUE sur la cible de l'`AddEffect` -- le `Repair` recoit
    # l'arbre NON filtre (la fiche #317 disait l'inverse ; lu au desassemblage des deux call-sites).
    # Les allies NON mecaniques sont ecartes de la reparation par le gate `EntityCanBeRepaired` de
    # l'Operation, pas par un selecteur. Branche `triggerType == Custom` (exclusion des HEROS) portee
    # mais SANS appelant cote port tant qu'`AdaptiveStrategy` (1005) n'est pas dans `ABILITY_CLASSES`.
    # Cf. loki/relentless_march.py + `docs/rl/case-328-relentless-march.md`.
    "RelentlessMarch": [RelentlessMarchAbility],
    # MyWillBeDoneOverlord (passif `necroOverlord`, `TriggeredAbilityType` 0x614 = 1556 -- #354) :
    # UNE classe native, DEUX branches disjointes de son `CreateTrigger` (`op_BitwiseOr`), donc DEUX
    # entrees ici (meme patron qu'ActOfFaith / TerrifyingCrescendo / ThrillSeekers) :
    #   * `On(0x29 = UnitFinishedTurnNormally) & OwnerIsActor` -> quand l'Overlord CLOT son activation,
    #     l'allie adjacent elu (Mechanical, avec une cible a portee, pas deja rejoue ; preference
    #     Necron-Hero > Hero > Necron > reste, puis plus grosse Attaque) attaque DEPUIS SA POSITION
    #     avec son Attaque overridee a `min(maxDmg[lvl], round(Attaque x dmgPct%))`, puis est memorise
    #     dans la liste persistante. Aucun allie eligible -> l'Overlord se buffe (effet 1581).
    #   * `On(0x12 = TurnStart_EffectActivation) & AmountIsGreaterThanZero(<liste persistante>)` ->
    #     `ClearAllPersistentData` : la liste est PURGEE au premier turn-start suivant, SANS gate de
    #     joueur (donc des le tour adverse).
    # ⚠ `necroOverlord` porte AUSSI `LivingMetal` (`On(0x13)`) -- evenement DISTINCT, aucune
    # interference. ⚠ RESIDU MESURE (#392) : c'est l'INVERSE de `MartialApotheosis` -- le kit
    # gameconfig nomme `MyWillBeDoneOverlord`, mais `data/seed-bc.json` ne la monte PAS
    # (`necroOverlord.PassiveAbilities = [1045]`). Ces deux entrees sont donc INERTES dans tout
    # runner bati sur ce seed, et le port ne peut pas les confronter par cette voie ; il faudrait
    # une seed BC ou l'Overlord la porte (greffe `catalog_inject`). Balayage : probe_392 etage 0 --
    # ce sont les SEULS ecarts kit/BC du seed (avec `Bounce` sur `orksNpc7Squig`, non portee).
    # Cf. loki/my_will_be_done_overlord.py (`...MyWillBeDoneOverlordAbility$$CreateTrigger` /
    # `$$CreateBehaviour` / `$$GetTargetFriend`).
    "MyWillBeDoneOverlord": [MyWillBeDoneOverlordAttackAbility, MyWillBeDoneOverlordClearAbility],
    # IconOfObstinacy (passif `astarLysander`, `TriggeredAbilityType` 0x610 = 1552 -- #919). Le
    # gameconfig n'a QU'UNE entree, mais le natif porte DEUX classes d'ability derivees d'une meme
    # base `AIconOfObstinacyAbility` : seule celle-ci est un TRIGGER.
    #   `...IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger` =
    #     On(0x28 = UnitFinishedTurn, ownerNeedsToBeAlive = 1)
    #     & Contains( Owner + UnitsWithTrait(AdjacentFriends(Owner), 0x40f = TerminatorArmour),
    #                 Actor@DSLSelectors+0x40 )
    #     & AmountIsZero( TimesAttackMadeThisTurn(Actor@0x40, rangeType = null) )
    #   `$$CreateBehaviour` = AddDynamicStatModifierEffect(targets = Actor, source = Owner,
    #     0x628 = IconOfObstinacy_ExtraArmor, statType 0x10 = FixedArmor, AbilityStateReference,
    #     TurnsFromRounds(1)).
    # ⚠ AUCUN `get_OwnerIsActor` : l'ability ecoute la fin de tour de TOUTE unite et filtre par le
    # `Contains`. ⚠ `On(0x28)` et non `On(0x29)` -> une terminaison FORCEE declenche aussi le buff.
    # L'AUTRE volet (`IconOfObstinacy_AddDamageBuffAbility`) n'est PAS ici : son `CreateTrigger` est
    # `OnOwnerSpecificAbilityInit` -> owner-effect, registre `effects.factory.
    # ABILITY_INIT_OWNER_EFFECTS`. Cf. loki/icon_of_obstinacy.py.
    "IconOfObstinacy": [IconOfObstinacyAddArmourBuffAbility],
    # SereneUnifier (passif `tauAunShi`, `TriggeredAbilityType` 0x479 = 1145 -- #462-r4e-o-r2-r1-r1) :
    # `On(TurnStart_Other=0x13, ownerNeedsToBeAlive=1) & <DSLTriggers+0x28 = IsTurnOf(Owner)> &
    #  get_OwnerIsCaster` -> les SIX `If(Modulo(PlayerTurnsStarted(Self), 3, k))` qui posent, sur
    # self + amis adjacents + amis T'au a <= `range`, l'effet de la phase courante :
    #   k = 0 -> 0x493 = 1171 StormOfFire  (stat 0 ATTACK, ConfigVar(8 = extraDmg))
    #   k = 1 -> 0x491 = 1169 SenseOfStone (classe bespoke : reduction de degat)
    #   k = 2 -> 0x492 = 1170 ZephyrsGrace (stat 1 MOVEMENT, ConfigConst(0xe = extraMovement))
    #   + les trois `*_Visual` (0x49a / 0x498 / 0x499), `NoneEffect` inertes.
    # ⚠ Le compteur est `PlayerTurnsStarted` (`TurnComponent+0x38` = `State.turn_counts`), PAS
    # `UnitTurnsStarted` (`UnitComponent+0x58`) qu'indexe le cycle jumeau de `FleshmetalGuns` --
    # deux compteurs natifs distincts, et les confondre decale la phase.
    # Les EFFETS etaient portes depuis longtemps, la ROTATION ne l'etait pas : un rejeu offline
    # multi-tours gardait donc a vie l'effet SEEDE au chargement. Cf. loki/serene_unifier.py et
    # `docs/rl/case-462-r4e-o-amount-borne-aux-pv.md` SS 9.
    "SereneUnifier": [SereneUnifierRotationAbility],
    # SavageKiller (passif `spaceWulfen` << Ulf >>, `TriggeredAbilityType` 0x487 = 1159 -- #929) :
    # UNE seule classe native, donc UNE seule entree ici -- et c'est LOAD-BEARING, pas cosmetique :
    # le cap de phase d'`EvaluateTriggerOperation$$EvaluateAbilityTrigger` est indexe par
    # ability-type cote natif et par `type(entry).__name__` cote port ; deux classes Python
    # donneraient DEUX compteurs pour UN compteur natif.
    #   `$$CreateTrigger` = `CreateSummonMoveTrigger() | CreateCharacterActiveAbilityTrigger()`
    #     FACE A : `On(4 = UnitAfterMove | 0x23 = UnitDisplaced | 0x32 = UnitAdded)`
    #              & HasTrait(Target@DSLSelectors+0x60, 2 = Summon)
    #              & IsAdjacent(Owner@+0x30, Target@+0x60, 3) & AreEnemies(Owner, Target, 0)
    #              [+ `NOT IsReplacedUnit` sur la seule branche UnitAdded -- residu #929-r2]
    #     FACE B : `On(0x2a = PreUnitAbility)` & IsActiveAbilityCountedAsUsed(**true**)
    #              & NOT TriggeringAbilityIs((ActiveAbilityType)0x467 = ArmouredMight_Move)
    #              & NOT IsOverwatchAttack()
    #              & IsAdjacent(Owner@+0x30, Caster@+0x48, 3) & AreEnemies(Owner, Caster, 0)
    #   `$$CreateBehaviour(abilityState, triggerType)` -> AttackWithAttackDamage(Owner -> cible,
    #     5 coups Power [minDmg,maxDmg]), la cible etant `Caster@+0x48` sur `0x2a` et `Target@+0x60`
    #     sinon (le MEME choix que `$$GetInitialTarget` exprime en `ConditionalSelector`).
    # ⚠ La 4e disjonction native (`On(0x3b = UnitBecameTargetable)`) n'est PAS abonnee : le port
    # n'emet nulle part cet evenement -> residu #929-r1, port speculatif refuse.
    # ⚠ `$$CreateValidActiveAbilityTrigger` est du DEAD CODE (0 `UNCONDITIONAL_CALL`, aucun homonyme
    # dans le binaire) -- verdict grave par `test_929_savage_killer_offline.py`.
    # Cf. loki/savage_killer.py + `docs/rl/case-929-savage-killer.md`.
    "SavageKiller": [SavageKillerAbility],
    # WrathfulDevotion (passif `worldTerminator` << Wrask >>, triggered 0x4be = 1214, #936) = UNE
    # ability native, DEUX faces, un seul `CreateShield` :
    #   * `On(0x36 = UnitDefeated) & OwnerIsActor & IsDefeatedByMeleeAttack(Target@+0x60, 0, 1)`
    #     -> vecteur EXISTANT `unit_defeated_triggers` ;
    #   * `On(0x3b = UnitBecameTargetable) & OwnerIsTarget
    #     & CurrentAbilityIs(AbilityOrEffect((**EffectType**)0x40b = TeleportStrike_TeleportingIn))`
    #     -> vecteur `unit_became_targetable_triggers`, **AJOUTE par cette tranche** dans
    #     `remove_effects.py` (le port ne l'emettait nulle part -- cf. le residu #929-r1 ci-dessus,
    #     qui en etait la victime).
    # Behaviour : `CreateShield(Owner + UnitsWithTrait(AdjacentFriends(Owner, 1, 3), Chaos, 3),
    # Direct(shieldHp), AbilityOrEffect((TriggeredAbilityType)1214), TurnsFromRounds(1), null, true)`,
    # plus -- sur la SEULE face B -- le marqueur `0x518 WrathfulDevotionTeleported_Visual`.
    # ⚠ La 3e branche du `switch (triggerType)` natif (`UnitDeath` -> `0x517 ...Killed_Visual`) est
    # du DEAD CODE : `CreateTrigger` n'abonne QUE {0x36, 0x3b}, et c'est `GetEventTriggers` qui
    # decide de l'abonnement. Verdict grave par `test_936_wrathful_devotion_offline.py`.
    # Cf. loki/wrathful_devotion.py + `docs/rl/case-936-wrathful-devotion.md`.
    "WrathfulDevotion": [WrathfulDevotionAbility],
    # #1016 -- `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationProtocolsAbility`
    # (: `IdunBattle.Entities.Abilities.BaseTriggeredAbility` d'apres `frida/classes.tsv` -- le
    # NAMESPACE `Abilities.Active.Loki` ment, c'est une TRIGGERED, `TriggeredAbilityType` 0x3f0 =
    # **1008**, et `unit_map` la classe `voie: passive`). LE passif de faction Necron, et l'item le
    # plus porte de la dette de kit : 9 porteurs (6 npc + les summons `necroSmnSwarm` /
    # `necroSmnWarrior` / `necroSmnDeathmark`).
    #   CreateTrigger   = OnPreDeath(overkill: 0, steppable: 0) & get_OwnerIsTarget
    #                   & AmountIsEqualOrGreater(Friends(Target, UnitsWithSameVisualId(Target, 1), 3),
    #                                            Direct(1))
    #   CreateBehaviour = Maybe(() => Revive(Owner, Target,
    #                                        PercentageOf(StatAmount(Owner, Health, Initial),
    #                                                     Direct(hpPct)),
    #                                        healType: 1 = Mechanical, AbilityOrEffect(1008),
    #                                        targetsTile: null, priority: 0),
    #                           Owner, chance)
    # ⚠ `AmountIsEqualOrGreater` est MAL NOMME : `AmountIsGreaterAbilityTrigger$$ShouldTrigger` rend
    # `evaluate(minAmount@+0x20) < amount` et AUCUN des deux `.ctor` ne decremente -> `>` STRICT,
    # donc << au moins UNE AUTRE >> unite du meme visualId, ce que l'i2 dit mot pour mot.
    # ⚠ AUCUN gate once-per-turn / once-per-battle dans l'arbre : la resurrection est REPETABLE.
    # Cf. loki/reanimation_protocols.py pour la RE complete.
    "ReanimationProtocols": [ReanimationProtocolsAbility],
}

# --- Registre : ability ACTIVE → triggered-ability(s) DERIVEE(s) ----------------------------------
# Mirror de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetDerived
# TriggeredAbilities` (dict statique `ActiveAbilityType -> List<TriggeredAbilityType>`, peuple par
# `...StaticBattleRules.ActiveAbility$$.cctor`) : posseder l'ability ACTIVE fait porter la (les)
# triggered-ability(s) derivee(s) DES L'INIT de l'unite, sans aucun cast prealable. C'est un TROISIEME
# chemin de registration, distinct des deux deja portes (`TRAIT_TRIGGERS` = par trait ;
# `ABILITY_TRIGGERS` = par passiveAbility) -- et le SEUL qui puisse porter une triggered-ability greffee
# sur une ability ACTIVE (cas des MoW, qui n'ont ni trait ni passif dedie).
# Cle = NOM gameconfig de l'ability active (`units.activeAbilities`), comme ABILITY_TRIGGERS l'est pour
# `units.passiveAbilities`. 39 entrees existent cote natif ; seules celles dont la triggered-ability est
# PORTEE sont inscrites ici (le reste = registered-but-unported, no-op fidele).
ACTIVE_ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # 0x4be (1214 Hailstrike, `darkaStormSpeeder` MoW) -> 0x5e3 (1507 Hailstrike_Attack) : quand un ALLIE
    # porteur du buff 1509 finit une attaque RANGED/OVERWATCH sur un ennemi VIVANT, la MoW attaque la
    # MEME cible (`nrOfHits` coups du profil de la config 1214, factory AttackWithAbilityDamage).
    # Le gate `HasEffect(attaquant, 1509)` du trigger rend l'entree INERTE tant qu'aucun Hailstrike
    # n'est pose -> l'inscription inconditionnelle est fidele. Cf. loki/hailstrike.py.
    "Hailstrike": [HailstrikeAttackAbility],
    # 0x4d0 (1232 EmpyricAmbush, `eldarLhykhis` HERO) -> 0x613 (1555 EmpyricAmbush_Reset) : quand la
    # PORTEUSE de l'actif ACHEVE un ennemi d'une attaque NORMALE au CONTACT, son actif est re-arme
    # (`ResetActiveAbility(Owner, allowUseless: 1)`). L'entree du cctor est un `ToList` a UN element.
    # Le trigger porte ses propres gates (OwnerIsActor + AreEnemies + IsNormalAttack + IsMeleeAttack),
    # donc l'inscription inconditionnelle est fidele. Cf. loki/empyric_ambush.py.
    "EmpyricAmbush": [EmpyricAmbushResetAbility],
    # 0x4cb (1227 HeavyWarpFlamer, `thousSekhetar` HERO) -> 0x60a (1546 HeavyWarpFlamer_AttackTracking)
    # -- le COMPTEUR de coups psychiques allies que lit `HeavyWarpFlamerAbility$$GetNumExtraHits`.
    # DEUX classes de port pour UNE classe native : son `CreateTrigger` est une DISJONCTION
    # (`On(9 = Attack) & ... | On(0x17 = TurnEnd)`) et son `CreateBehaviour` branche sur le
    # `triggerType` ; le registre du port etant indexe par `event_id`, il faut une entree par
    # disjoint (patron `HaywireMinePlaceOnMove` / `HaywireMinePlaceOnTurnEnd`).
    # Le couple est LU dans le motif d'insertion de `StaticBattleRules.ActiveAbility$$.cctor`
    # (valeur en `[rbp+0x18]`, cle en `[rbp+0x20]`), entre `0x5e3 -> 0x4be` (Hailstrike) et
    # `0x613 -> 0x4d0` (EmpyricAmbush) -- les deux entrees ci-dessus. Cf. loki/heavy_warp_flamer.py.
    "HeavyWarpFlamer": [HeavyWarpFlamerAttackTrackingAbility,
                        HeavyWarpFlamerAttackTrackingResetAbility],
    # 0x405 (1029 Drachnyen, `blackAbaddon` HERO) -> 0x5cd (1485 Drachnyen_ExtraAttack) : apres une
    # attaque NORMALE au CONTACT du porteur, si l'effet 1471 est actif sur lui, il porte
    # `nrOfHits` coups supplementaires (config 1029) sur l'ennemi adjacent le plus RENTABLE
    # (`First(SortUnitsByDamageUtility(...), 1)`). L'entree du cctor est un `ToList` a UN element,
    # LU verbatim : `GetDerivedTriggeredAbilities[0x405] = [0x5cd]` -- l'unique occurrence de
    # chacun des deux ordinaux dans tout `StaticBattleRules.ActiveAbility$$.cctor`.
    # Le gate `HasEffect(Owner, 0x5bf = 1471)` du trigger rend l'entree INERTE tant que l'active
    # 1029 n'a pas ete castee -> l'inscription inconditionnelle est fidele (patron Hailstrike).
    # Cf. loki/drachnyen.py. #BL-1029r.
    DRACHNYEN_ABILITY: [DrachnyenExtraAttackAbility],
}

# --- Registre : ability ACTIVE → triggered-ability HELPER (« passive helper ») ---------------------
# Mirror de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$Get
# PassiveHelperAbility` (#521-r1) -- un `Dictionary<ActiveAbilityType, TriggeredAbilityType>` range
# dans `<StaticBattleRules.ActiveAbility statics>+0x78`, peuple par le `.cctor` de la meme classe.
#
# ⚠ CE N'EST PAS le dict d'`ACTIVE_ABILITY_TRIGGERS` ci-dessus. Deux dicts natifs DISTINCTS, deux
# slots statiques distincts, et deux chemins de montage distincts :
#   * `...$$GetDerivedTriggeredAbilities` (statics+0x30, valeur = une **List**) -> monte par
#     `UnitFactory$$AddDerivedAbilities` ;
#   * `...$$GetPassiveHelperAbility`      (statics+0x78, valeur = un **scalaire** Nullable) -> monte
#     par `IdunBattle.Entities.Factories.UnitFactory$$AddActiveAbility`, lui-meme appele en boucle
#     sur `config@+0xa0` = `UnitConfiguration.ActiveAbilities` depuis
#     `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` (et son jumeau
#     `IdunBattle.Entities.Factories.MachineFactory$$AddConfiguredAbilities` pour les MoW) :
#         helper = GetPassiveHelperAbility(activeAbility)
#         if (helper.HasValue) TriggeredAbilityComponent.TryAdd(helper.Value, passiveAbilityState, 0)
#     -- l'etat d'ability inscrit est le **PASSIF**, et la hierarchie vaut 0.
# Ecrire une entree de l'un dans l'autre ferait porter une triggered-ability par un chemin que le
# natif n'emprunte pas ; c'est pourquoi le registre est SEPARE, comme `RELIC_ABILITY_TRIGGERS` l'est
# d'`ABILITY_TRIGGERS`.
#
# Cle = NOM gameconfig de l'ability active. Le dict natif compte SIX entrees, transcrites ici en
# COMMENTAIRE (nom + ordinal), pour que le lecteur voie ce qui est porte et ce qui ne l'est pas :
#   1032 Catalyst              -> 1062 GuildBossRunAway                            (non porte)
#   1070 BreathOfSilence       -> 1128 BreathOfSilence_SetStart                    (non porte)
#   1118 DoctrinaImperatives   -> 1201 DoctrinaImperatives_SetStart                (non porte)
#   1148 DaemonicOrdnance      -> 1244 DaemonicOrdnance_Crit                       (non porte)
#   1189 CalibaniteGreatsword  -> 1316 CalibaniteGreatsword_NormalAttackAdditionalDamage <- PORTE (#521-r4)
#   1195 TalonsOfTheEmperor    -> 1330 TalonsOfTheEmperor_UsedAbilities            <- PORTE (#521-r1)
# Les trois non portees restent registered-but-unported cote natif : no-op fidele, elles n'ont RIEN a
# faire ici tant que leur classe n'existe pas (une entree vide serait un mensonge de couverture).
PASSIVE_HELPER_ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # 0x4ab (1195 TalonsOfTheEmperor, `custoAtlacoya` HERO) -> 0x532 (1330 TalonsOfTheEmperor_Used
    # Abilities) : a la FERMETURE de toute active d'un allie `Hero` non-`MachineOfWar` qui COMPTE
    # (`IsActiveAbilityCountedAsUsed`, donc PAS l'attaque normale), le porteur incremente de +1, SANS
    # cap, le niveau de l'effet 1420 -- le compteur que lit
    # `...TalonsOfTheEmperorAbility$$GetExtraDamage`. Le trigger porte tous ses gates, donc
    # l'inscription inconditionnelle est fidele. Cf. loki/talons_of_the_emperor.py.
    TOTE_ACTIVE_ID: [TalonsOfTheEmperorUsedAbilitiesAbility],
    # 0x466 (1118 DoctrinaImperatives, `admecMarshall` HERO) -> 0x4b9 (1201
    # DoctrinaImperatives_SetStart) : a l'INIT des abilities du porteur, self-buff
    # `AddDynamicStatModifierEffectToOwner(1247 ProtectorImperative, 16 FixedArmor, turns = null)`.
    # Le trigger PARTAGE (`<DSLTriggers+0x30>`) se reduit a `On(0x21 = AbilityInit) & OwnerIsActor` :
    # son 2e conjoint `<DSLTriggers+0x70>` est le `YesTrigger` CONSTANT (element neutre), ce qui
    # LEVE le dernier verrou de lecture note par case-521r1 Sec.5bis.
    # ⚠ INERTE sur le regime courant : le port n'emet `On(AbilityInit)` qu'au SPAWN, et aucune unite
    # portant 1118 n'est spawnee -- celles du roster arrivent par `load_state` avec l'effet DEJA
    # pose. Inscription FIDELE au registre natif, gain de comportement NUL, et c'est dit.
    # Cf. loki/doctrina_imperatives.py. #521-r4.
    DOCTRINA_IMPERATIVES_ACTIVE: [DoctrinaImperativesSetStartAbility],
    # 0x4a5 (1189 CalibaniteGreatsword, `darkaCompanion` << Forcas >> HERO) -> 0x524 (1316
    # CalibaniteGreatsword_NormalAttackAdditionalDamage) : quand Forcas est en posture SWEEP
    # (effet 1405, pose par le TOGGLE 1189) et porte une attaque NORMALE de MELEE, il frappe EN PLUS
    # les ennemis adjacents A LA FOIS a son empreinte et a sa cible --
    # `Foreach(AdjacentEnemies(Caster, CasterTile, 1) & AdjacentUnits(Target, 1, 3), Attack(...))`,
    # bornes `minDmg`/`maxDmg` de 1189 au niveau du caster, `nrOfHits_2 = 3`, profil `Power`.
    # ⚠ L'ETAGE qui le rendait inerte est LEVE (#521-r7) : `ALoki_NormalAttackAbility$$
    # ExecuteNormalAttack` emet `EvaluateAbilities(0x4a = AttackInAtomicGroup, immediately: true)`
    # sur TOUTE attaque normale -- ce n'est pas `...$$ExecuteTriggerAbilities` (qui emet 0x26) qui
    # le porte, et c'est cette lecture partielle qui avait fait conclure a l'absence d'emetteur.
    # Cf. loki/calibanite_greatsword.py. #521-r4.
    CALIBANITE_GREATSWORD_ACTIVE: [CalibaniteGreatswordNormalAttackAdditionalDamageAbility],
}

# --- Registre : relicAbility → triggered-ability(s) accordée(s) ------------------------------------
# QUATRIEME chemin de registration (#317), et il est DISTINCT des trois autres : une RELIQUE accorde
# une triggered-ability sans passer ni par `traits`, ni par `passiveAbilities`, ni par
# `activeAbilities`. Deux formes cote natif :
#   * `gameconfig.units.<kind>.<id>.relicAbilities` -- la relique EN DUR sur l'unite. 25 abilities
#     du build sont dans ce cas, TOUTES sur des npc (mesure : `probe_317_repair_callers_inventory.py`) ;
#   * l'item relique EQUIPE par le joueur (`items[*].abilityId` + `allowedUnits`), materialise dans
#     `BattleConfiguration.Units[].TertiaryAbility` -- 4 unites sur 175 du seed BC en portent une,
#     et 52 autres peuvent en recevoir une par le montage #237.
# **LES DEUX formes sont lues depuis #357** : la premiere par le gameconfig (`relicAbilities`), la
# seconde par `UnitContext.tertiary_ability`, seede depuis le RPC `unitAbilityStates`
# (`snapshot._load_tertiary_abilities`) -- la branche TERTIAIRE d'`IdunBattle.Entities.Factories.
# UnitFactory$$AddConfiguredAbilities`. Le registre ci-dessous est INDEXE PAR NOM d'ability, donc il
# sert aux deux formes sans duplication ; c'est `collect_triggered_abilities` qui DEDUPLIQUE (mirror
# du `TryAdd` sur `KeyedCollection`) quand une unite porte la meme relique par les deux voies.
# ⚠ Le canal est ON PAR DEFAUT depuis #363 (transport ambiant `snapshot.bind_live_rpc`, lie par le
# harnais de test). Hors harnais live -- `State` nu, capture rejouee sans transport, ou refus
# explicite `ability_states=False` -- le rail ne voit QUE la forme gameconfig, exactement comme
# avant #357.
#
# Registre SEPARE de `ABILITY_TRIGGERS` a dessein : aucune des 25 relicAbilities n'y figure, donc un
# registre distinct rend la double-inscription STRUCTURELLEMENT impossible.
RELIC_ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # DawnBlade (relique `R_Crit_DawnBlade` de `tauFarsight` ; en dur sur les 5 npc `*Farsight`),
    # `TriggeredAbilityType` 0x5dd = 1501. `DawnBlade_HealAbility` : `On(0=UnitDeath) & OwnerIsActor
    # & IsDefeatedByMeleeAttack(Targets@0x60)` -> `Repair(self, self, Get(hpToHeal[lvl]), ForRepair)`.
    # ⚠ LE NOM MENT : l'artefact est un `DSLBehaviors$$Repair`, pas un `$$Heal` -- et la variable lue
    # s'appelle `hpToHeal` (`AbilityVariableType` 0x20). Cf. loki/dawn_blade.py.
    # La 2e classe native du meme id (`DawnBlade_InitAbility`, qui pose l'effet 1501
    # `DawnBlade_ExtraDmg`) n'est PAS portee : elle ne construit aucun `Repair` (#317, hors perimetre).
    "DawnBlade": [DawnBladeHealAbility],
    # DaemonfleshPlate (relique `R_Block_DaemonfleshPlate`, `TriggeredAbilityType` 0x5d5 = 1493 ;
    # 4 porteurs `lineup` : blackTerminator / deathBlightlord / thousTerminator / worldTerminator).
    # DEUX classes natives pour UNE cle (patron `LetTheGalaxyBurn` / `HaywireMine`) :
    #   * `DaemonfleshPlateAbility` -- `On(9 = Attack) & OwnerIsCaster` (⚠ ce `CreateTrigger` est
    #     INVISIBLE des tables : son corps est DEDUPLIQUE avec celui de
    #     `LetTheGalaxyBurn_ResetAbility$$CreateTrigger` ; appartenance etablie slot a slot dans le
    #     bloc `methodPointers` du PE) -> `If(counter >= nrOfAttacks - 1, retire les piles + arme
    #     1491 + vide le compteur, +1 pile d'armure 1490 + counter += 1)` ;
    #   * `DaemonfleshPlate_ResetActiveAbility` -- `On(0x3a = PhaseEnd) & HasEffect(Owner, 1491)`
    #     -> `ResetActiveAbility(Owner, true) + RemoveEffect(1491)`.
    # Cf. loki/daemonflesh_plate.py.
    "DaemonfleshPlate": [DaemonfleshPlateAbility, DaemonfleshPlateResetActiveAbility],
    # OrbsOfDecay (relique Death Guard, `TriggeredAbilityType` 0x5b9 = 1465 ; 3 porteurs `lineup`
    # TOUS dans le pool : deathBlightbringer / deathPutrifier / deathRotbone). #1003.
    # `On(0x4a = AttackInAtomicGroup) & get_OwnerIsCaster & IsMeleeAttack` -- SANS `IsNormalAttack`,
    # contrairement a 1316 sur le meme evenement -> `AttackWithAttackDamage(Toxic, nrOfHits)` contre
    # les ennemis ADJACENTS a la tuile de la cible dont l'armure est reduite de PLUS de
    # `armorReductionPct` % de sa BASE, plus `AddEffect(1244 Contaminated)` sur la tuile de la cible.
    # La CIBLE elle-meme n'est PAS dans ce selecteur (`AdjacentTiles` exclut ses origines) : le
    # « on the target's hex » de l'i2 vit dans la 2e classe native du meme id
    # (`OrbsOfDecay_AdditionalHitsAbility` -> effet 1463, canal `additional_hit_groups`), NON portee
    # -- residu `#1003-r1`, qui rejoint `#884-r2`. Cf. loki/orbs_of_decay.py.
    "OrbsOfDecay": [OrbsOfDecayAbility],
    # Lakrimae (relique Death Guard, `TriggeredAbilityType` 0x605 = 1541 ; porteur `deathTyphus`,
    # dans le pool). #1003. DEUX classes natives pour UNE cle, comme `DaemonfleshPlate` :
    #   * `Lakrimae_AddContamination_Ability` -- `On(0x26 = NormalAttack) & get_OwnerIsActor &
    #     IsMeleeAttack & IsNormalAttack` -> `AddEffect(1244 Contaminated, source = Owner@+0x30,
    #     targets = TargetTiles@+0x78)`   <- PORTEE ;
    #   * `Lakrimae_SummonPoxwalker_Ability` -- `On(0x35 = PostUnitKill)` + 8 conjoints ->
    #     `Spawn(deathPoxwalker)` : NON portee, residu `#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1` (etages
    #     `ContagionsOfNurgleRange(.., 1, ..)` / `IsUnitWithVisualId` / `FreeTilesOrAdjacentFreeTiles`
    #     non portes). L'inscrire vide serait un mensonge de couverture.
    # Cf. loki/lakrimae.py.
    "Lakrimae": [LakrimaeAddContaminationAbility],
    # ChaliceOfBaal (relique `R_Health_ChaliceOfBaal`, `TriggeredAbilityType` 0x60e = 1550 ;
    # porteur `bloodSanguinary` << Nicodemus >>, HERO du pool). DEUX classes natives pour UNE cle
    # -- et c'est LU, pas suppose : `IdunBattle.Core.Services.AbilitiesDatabase.u003Cu003Ec$$
    # u003CInitializeTriggeredAbilitiesu003Eb__28_426` construit `ChaliceOfBaalAbility` PUIS
    # `ChaliceOfBaal_ResetAbility` et les range dans LA MEME liste (patron `LetTheGalaxyBurn` /
    # `HaywireMine` / `DaemonfleshPlate`) :
    #   * `ChaliceOfBaalAbility` -- `On(0 = UnitDeath, alive) & NOT HasTrait(Target, Steppable)
    #     & IsAdjacent(Owner, Target, Any) & NOT HasTriggeredThisTurn()` -> `Heal(Owner, Owner +
    #     AdjacentFriends filtres NonMechanical, Get(hp)) & AddEffect(0x621 = 1569
    #     ChaliceOfBaal_ExtraDmg, turns = Direct(1)) & SetPersistentData("ChaliceOfBaalTriggered")`.
    #     ⚠ AUCUN `get_OwnerIsActor` : le porteur n'a pas a etre le TUEUR (contraste `DawnBlade`).
    #   * `ChaliceOfBaal_ResetAbility` -- `On(0x17 = TurnEnd, alive) & HasTriggeredThisTurn()` ->
    #     `ClearAllPersistentData(1550, Owner)`. Son `CreateBehaviour` est un corps FONDU par l'ICF,
    #     partage avec `NoHidingFromTheWatchers_EndPhaseAbility$$CreateBehaviour`.
    # Cf. loki/chalice_of_baal.py. #1005.
    "ChaliceOfBaal": [ChaliceOfBaalAbility, ChaliceOfBaalResetAbility],
    # Vitarus (relique `R_Crit_Vitarus`, `TriggeredAbilityType` 0x5be = 1470 ; porteur
    # `bloodMephiston`, HERO du pool). DEUX classes natives, dont UNE SEULE est un vecteur de
    # combat :
    #   * `VitarusAbility` (ici) -- `On(9 = Attack, alive) & get_OwnerIsCaster & IsMeleeAttack
    #     & (IsNormalAttack | CurrentAbilityIs(0x4df = 1247 FuryOfTheAncients))` ->
    #     `If(la tuile de la cible est en Feu, Inform(Is_Modified) + RemoveEffect(Fire),
    #         AddEffect(Fire))` ;
    #   * `Vitarus_InitAbility` -- `AOwnerEffectTriggeredAbility` dont le SEUL override est
    #     `$$GetEffectType` (`return 0x5ba` = 1466) : owner-effect PERMANENT pose a l'init, donc
    #     `ABILITY_INIT_OWNER_EFFECTS["Vitarus"]`, PAS une entree ici (patron `ToughToKill`).
    # Cf. loki/vitarus.py. #1005.
    "Vitarus": [VitarusAbility],
    # BladeOfTheAncestors (relique `R_Crit_BladeOfTheAncestors`, `TriggeredAbilityType` 0x5d3 =
    # 1491 ; UN porteur autorise : `votanUthar` << Uthar >>, HERO hors pool -> injection catalogue).
    # DEUX classes natives pour UNE cle (patron `DaemonfleshPlate`), toutes deux sous le namespace
    # `...Abilities.**Active**.Loki` alors que la base LUE est `BaseTriggeredAbility` :
    #   * `BladeOfTheAncestorsAbility` -- `On(0 = UnitDeath) & AreFriends(Targets@+0x60, Owner) &
    #     HasTrait(Targets@+0x60, Hero)` | `... & AreFriends(Actor@+0x40, Owner) &
    #     HasTrait(Actor@+0x40, Hero) & IsNormalUnit(Targets@+0x60)` -> `AddEffect(0x5d1 = 1489)` ;
    #   * `BladeOfTheAncestors_RemoveEffectAbility` -- `On(9 = Attack) & OwnerIsCaster & WasCrit &
    #     HasEffect(Owner, 0x5d1)` -> `TriggerAbilityDelayed(Owner, 0x5d3, 3)` (le retrait tombe au
    #     DRAIN, branche `Custom` : cf. `CUSTOM_TRIGGERED_ABILITIES[1491]`).
    # L'EFFET 1489 est inscrit dans le MEME commit (`EFFECT_CLASSES`, #1004) : l'ability seule
    # poserait un `BaseEffect` nu, qui ne change aucune stat. Cf. loki/blade_of_the_ancestors.py.
    "BladeOfTheAncestors": [BladeOfTheAncestorsAbility, BladeOfTheAncestorsRemoveEffectAbility],
    # VolummsMasterArtifice (relique `R_Crit_VolummsMasterArtifice`, `TriggeredAbilityType` 0x5d0 =
    # 1488 ; UN porteur autorise : `votanIronmaster` << Vynn >>, HERO hors pool). UNE classe :
    # `On(0x30 = 48 UnitRepaired) & (AreEqual(Parent(Caster@+0x48), Owner@+0x30) | OwnerIsCaster)`
    # -> `AddPersistentData(+1) & If(compteur >= nrOfRepairs, Heal(hpToHeal) & ResetActiveAbility &
    # SetPersistentData(0))`. Le vecteur `UnitRepaired` existe depuis #964-r1
    # (`dispatch/repair.py`), donc l'inscription n'est PAS registered-but-dead.
    # Cf. loki/volumms_master_artifice.py.
    "VolummsMasterArtifice": [VolummsMasterArtificeAbility],
    # Maugetar (relique `R_Crit_Maugetar` d'`eldarMauganRa`, `TriggeredAbilityType` 0x5da = 1498 --
    # `Maugetar` figure aussi dans les `activeAbilities` d'un npc : c'est une INVERSION DE VOIE
    # mesuree, pas une active). DEUX classes natives pour UNE cle, meme patron que `DaemonfleshPlate`
    # ci-dessus :
    #   * `Maugetar_AddEffectAbility` -- `On(0x12 = TurnStart_EffectActivation) & IsTurnOf(Owner)`
    #     -> `AddEffect(1497 Maugetar_HasNotMoved, stateRef, Owner, turns = null)` ;
    #   * `Maugetar_ResetMovementAbility` -- `On(0xe = UnitPostAbility) & get_OwnerIsCaster`
    #     -> `If(HasEffect(Owner, 1497, onlyActive: false, 6), ResetMovement(Owner))`.
    #     ⚠ Son `CreateTrigger` est INVISIBLE des tables (corps fondu par l'ICF avec
    #     `...DaemonicOrdnance_RemoveCritChance$$CreateTrigger`) : appartenance etablie slot a slot
    #     dans le bloc `methodPointers` du PE.
    # Le RETRAIT de l'effet (`On(0x1f = PreUnitMove) & get_OwnerIsActor`) est un trigger PROPRE de
    # l'effet -> `EFFECT_TRIGGERS[1497]`, pas ici. Cf. loki/maugetar.py.
    "Maugetar": [MaugetarAddEffectAbility, MaugetarResetMovementAbility],
    # WyrdmakersHelm (relique `R_Booster_Crit_WyrdmakersHelm`, `TriggeredAbilityType` 0x5e0 = 1504 ;
    # UN porteur, `spaceWolfPriest`, HORS du seed BC -> injection catalogue PUIS `--equip-relic`).
    # UNE SEULE classe native pour cet id -- verifie dans `frida/classes.tsv`, qui ne porte qu'un
    # `Wyrdmaker*` : contraste `TheArdentBlade`/`PhasalSubjugator`/`Maugetar`. Il n'y a NI classe
    # d'effet ; `EffectType.WyrdmakersHelm` (1505, un AUTRE enum que l'ability 1504) n'est que
    # l'etiquette du stat-mod pose puis retire DANS l'arbre.
    # `On(0x2c = UnitHealedWithRemoveEffects) & (OwnerIsTarget | (IsAdjacent(Owner, Target, 3) &
    #  AreFriends(Owner, Target, 0))) & AmountIsEqual(TimesHealedThisTurn(Target), Const(1)) &
    #  IsTurnOf(Owner)` -> `AddStaticStatModifierEffectToOwner(1505, Attack, ConfigVar(extraDmg)) +
    #  SetCache(Cache(Tiles(First(SortUnitsByDamageUtility(...))))) + UseNormalAttack(Owner, cible) +
    #  RemoveEffect(Owner, 1505) + If(NOT IsDead(Owner), AddEffect(17 Ice, cache))`.
    # ⚠ Le vecteur `On(0x2c)` N'EXISTAIT PAS : il est pose par la MEME tranche
    # (`triggers/dispatch/heal.py`) -- sans lui cette entree serait inscrite et jamais declenchee.
    # Cf. loki/wyrdmakers_helm.py. #1037.
    "WyrdmakersHelm": [WyrdmakersHelmAbility],
    # SabreOfSacrifice (`TriggeredAbilityType` 0x5c6 = 1478 ; UN porteur `lineup`, `astraDreir`,
    # DANS le pool rank 17 -> montage `--equip-relic` seul). UNE classe native, UN seul `On()` :
    # `On(9 = Attack) & IsCharging(Caster, Target) & (OwnerIsCaster | (Parent(Caster) == Owner &
    # IsUnitWithVisualId(Caster, "astraNpc5DeathRider") & IsAdjacent(Owner, Caster, 3)))` ->
    # `AddEffect(1065 Pinned, source = Owner, targets = Target, duree PAR DEFAUT) &
    #  AddStaticStatModifierEffect(Caster, 1473 SabreOfSacrifice_ExtraArmor, 16 FixedArmor,
    #  Multiply(Count(allies normaux vaincus), Get(extraArmor)), TurnsFromRounds(1))`.
    # ⚠ La disjonction est INTERNE a la conjonction (elle porte sur le PORTEUR du coup, pas sur
    # l'evenement) -> UNE seule classe, pas la ventilation `FuryFromTheDelve`.
    # ⚠ SEUL call-site porte du depot ou OWNER != CASTER (branche Death Rider summon) : le slot
    # `Owner` est threade explicitement. Cf. loki/sabre_of_sacrifice.py. #1002.
    "SabreOfSacrifice": [SabreOfSacrificeAbility],
    # RelicOfLostCadia (`TriggeredAbilityType` 0x5b3 = 1459 ; TROIS porteurs `lineup` Astra, tous
    # dans le pool rank 17 : astraBullgryn / astraOrdnance / astraPrimarisPsy). DEUX classes
    # natives pour UNE cle (patron `LetTheGalaxyBurn` / `DaemonfleshPlate`) :
    #   * `RelicOfLostCadiaAbility` -- CINQ vecteurs (`On(4 UnitAfterMove) | (On(0x32 UnitAdded) &
    #     IsAlive(Actor)) | On(0x3b UnitBecameTargetable) | On(0x2d UnitRevived) |
    #     OnOwnerSpecificAbilityInit(1459)`) -> pose 1454 `FinalVengeance_UnitEffect` sur les
    #     summons IMPERIAUX allies adjacents. La disjonction d'`On()` se ventile en `event_ids` ;
    #     le vecteur `OnOwnerSpecificAbilityInit` n'est PAS un trigger -> il ne peut PAS passer par
    #     `ABILITY_INIT_OWNER_EFFECTS` (qui pose sur l'OWNER, or la cible est le VOISINAGE) et
    #     reste couvert par `On(0x32 UnitAdded)`, qui refait le meme balayage au spawn.
    #   * `RelicOfLostCadiaAbility_SummonUnit` -- `On(0 = UnitDeath, alive: 0) & OwnerIsTarget` ->
    #     `Spawn(astraSmnGuardsman)` dans l'hex du porteur mort.
    # Cf. loki/relic_of_lost_cadia.py. #1002.
    "RelicOfLostCadia": [RelicOfLostCadiaAbility, RelicOfLostCadiaSummonUnitAbility],
    # BookOfFate (relique `R_Booster_Crit_BookOfFate`, `TriggeredAbilityType` 0x5b5 = 1461 ; TROIS
    # porteurs autorises LUS dans `items/.../allowedUnits` : `blackPossession` (Black Legion, pool
    # rank 17), `thousInfernalMaster` et `thousSorcerer` (Thousand Sons)). UNE classe native. #1008.
    # `On(0x26 = NormalAttack) & get_OwnerIsCaster & IsAlive(Owner) & AmountIsGreaterThanZero(
    #  <summons amis adjacents>)` -> un summon adjacent AYANT une cible attaque depuis sa position,
    # choisi par une cascade `Otherwise` a TROIS etages (le `thousSmnDaemonPrince` nomme par
    # `AbilityConstantType.affectedUnitId` > un Daemon quelconque > un non-Daemon), et s'il est
    # `Daemon` il porte `+extraDmg` d'Attack LE TEMPS DE CE COUP (l'ordre `(buff & attaque) & retrait`
    # est LU au dernier `op_BitwiseAnd`). L'effet 1452 n'a AUCUNE classe native dediee : c'est le
    # `StaticStatModifierEffect` generique que monte `AddStaticStatModifierEffect` -- rien a inscrire
    # dans `EFFECT_CLASSES`. Cf. loki/book_of_fate.py.
    "BookOfFate": [BookOfFateAbility],
    # Helspear (relique `R_Crit_Helspear`, `TriggeredAbilityType` 0x616 = 1558 ; UN porteur autorise :
    # `blackHaarken` << Haarken Worldclaimer >>, HERO du pool rank 17). DEUX classes natives pour UNE
    # cle (patron `DaemonfleshPlate` / `ChaliceOfBaal`). #1008. ⚠ AUCUNE description i2 n'existe pour
    # cette relique -- le decompile est la seule source.
    #   * `Helspear_BuffActiveAbility` -- `On(9 = Attack, alive) & get_OwnerIsCaster &
    #     CurrentAbilityIs(ActiveAbilityType.HeraldOfTheApocalypse = 0x3fc)` ->
    #     `AddEffect(0x62f = 1583 Helspear_IgnoreArmor, targets = Target@+0x60)
    #      + AddEffect(0x5c4 = 1476 DespoiledGround, targets = Tiles(Target@+0x60))` (`op_Addition`) ;
    #   * `Helspear_ResetActiveAbility` -- `On(0x36 = UnitDefeated, alive) & get_OwnerIsActor &
    #     NOT IsSteppableUnit(Target) & NOT AreFriends(Owner, Target, ByCurrentTeam, false) &
    #     NOT TriggeringAbilityIs(0x3fc) & <DSLTriggers+0x58>` ->
    #     `AddPersistentData(+1) + If(compteur >= nrOfUnits, ResetActiveAbility(allowUseless) +
    #      ClearPersistentData)`. L'INCREMENT est a GAUCHE -> seuil sur le compteur DEJA incremente.
    # ⚠ Le SIXIEME conjoint du reset (`<DSLTriggers+0x58>`) n'est PAS identifie et n'est PAS porte :
    # residu `#1008-r3`, BLOCAGE `capteur`. L'EFFET 1583 entre dans `EFFECT_CLASSES` DANS CE MEME
    # COMMIT, mais sa magnitude n'atteint pas le calcul (residu `#1008-r2`, BLOCAGE `etage`).
    # Cf. loki/helspear.py.
    "Helspear": [HelspearBuffActiveAbility, HelspearResetActiveAbility],
    # Dw02AdvancedBurstCannon (relique `R_Crit_Dw02AdvancedBurstCannon`, `TriggeredAbilityType`
    # 0x5c4 = 1476 ; UN porteur autorise : `tauCrisis` << Re'vas >>, HERO du pool rank 17). #1012.
    # UNE classe native, dont les DEUX corps sont dans les tables :
    # `On(9 = Attack, alive) & get_OwnerIsCaster & NOT IsSpecialActiveAbility` ->
    # `If(compteur >= nrOfAttacks - 1,
    #     (RemoveEffect(0x5be) & ResetActiveAbility(allowUseless)) & ClearPersistentData,
    #     AddStaticStatModifierEffect(Caster, 0x5be, 0x1a = ExtraPierce, ConfigVar(extraPierceRatio))
    #       & AddPersistentData(+1))`.
    # ⚠ Le `If` est la RACINE du corps (patron `DaemonfleshPlate`), donc le seuil porte sur le
    # compteur AVANT increment -- l'INVERSE de `VolummsMasterArtifice` ci-dessus.
    # Le re-armement de l'active est IMMEDIAT (pas de marqueur + `PhaseEnd`), d'ou l'absence de
    # seconde classe. L'EFFET 1470 est inscrit dans le MEME commit (`EFFECT_CLASSES`) : sans lui la
    # pile serait un `BaseEffect` nu, qui ne modifie aucune stat.
    # Cf. loki/dw02_advanced_burst_cannon.py.
    "Dw02AdvancedBurstCannon": [Dw02AdvancedBurstCannonAbility],
    # RelicPowerFist (relique `R_Crit_RelicPowerFist`, `TriggeredAbilityType` 0x5ba = 1466 ; #1009).
    # ⚠ TROIS porteurs autorises, sur TROIS factions : `templAggressor` (Black Templars),
    # `bloodIntercessor` (Blood Angels), `darkaTerminator` (Dark Angels, celui que #1009 confronte).
    # UNE classe native :
    #   `On(9 = Attack, alive) & get_OwnerIsCaster
    #    & CurrentAttackDamageProfilesContain(0xe = Power, includeNotApplied = true)`
    #   -> `Maybe(AddEffect(0x429 = 1065 Pinned,  source = Owner@+0x30, targets = Target@+0x60),
    #             ConditionalAmount(IsSpecialActiveAbility, Double(chance),   chance))
    #    &  Maybe(AddEffect(0x48a = 1162 Stunned, source = Owner@+0x30, targets = Target@+0x60),
    #             ConditionalAmount(IsSpecialActiveAbility, Double(chance_2), chance_2))`
    # ⚠ DEUX tirages `next_bool` INDEPENDANTS, Pinned PUIS Stunned (`MaybeBehaviour` tire AVANT son
    # enfant, `CombinedBehaviour` execute gauche puis droite) : les fusionner decalerait la sequence
    # PRNG de toute la bataille. Cf. loki/relic_power_fist.py.
    "RelicPowerFist": [RelicPowerFistAbility],
    # ParagonSpear (relique `R_Crit_ParagonSpear`, `TriggeredAbilityType` 0x5d6 = 1494 ; UN porteur,
    # `custoKyrus`, DANS le pool rank 17 -> `--equip-relic` suffit, aucune injection). UNE classe
    # native, UN vecteur : `On(0x16 = TurnStart_Actions, ownerNeedsToBeAlive: 1) &
    # <DSLTriggers+0x28 = IsTurnOf(Owner@+0x30)> & AmountIsGreaterThanZero(GetPossibleTargets())`
    # -> `AttackWithAttackDamage(First(SortByDistance(Randomize(GetPossibleTargets()), Owner), 1),
    # nrOfHits = 2 coups profil Bolter, bornes minDmg/maxDmg au niveau TERTIAIRE)`.
    # `GetPossibleTargets` = `If(AmountIsGreaterThanZero(adjacents), adjacents, distants)` : les
    # ennemis damageable ADJACENTS s'il y en a, sinon ceux du rayon `range` en vue DEGAGEE.
    # ⚠ `level_slot="tertiary"` : lire le niveau des PASSIFS clamperait au dernier palier (50 dans
    # tout runner normalise), SILENCIEUSEMENT. Cf. loki/paragon_spear.py. #1013.
    "ParagonSpear": [ParagonSpearAbility],
    # TheArdentBlade (relique `R_*_TheArdentBlade`, `TriggeredAbilityType` 0x5bc = 1468 ; UN porteur,
    # `adeptCelestine`, HORS pool rank 17 -> etat 3 : injection catalogue PUIS `--equip-relic`).
    # #1013-r2. DEUX classes natives pour UNE cle, et elles ne vont PAS au meme endroit :
    #   * `TheArdentBlade_InitAbility` -- pas de `CreateTrigger` propre (patron
    #     `OnOwnerSpecificAbilityInit`), `CreateBehaviour = AddEffect(0x5b6 = 1462, stateRef,
    #     source = targets = Owner@+0x30, options <32 octets a ZERO>) & ActivateEffect(Owner, 0x5b6)`
    #     -> `ABILITY_INIT_OWNER_EFFECTS["TheArdentBlade"]`, PAS une entree ici (patron `Vitarus`) ;
    #   * `TheArdentBlade_TriggerAbility` (ICI) -- `On(0x36 = UnitDefeated, alive) & OwnerIsActor &
    #     IsNormalUnit(Target@+0x60) & AreEnemies(Owner, Target, 1 = ByOriginalTeam) &
    #     HasEffect(Owner, 0x5b6, onlyActive: 1, 6 = Both)` -> `If(<une Geminae morte ET une tuile
    #     libre adjacente>, Group(Resurrect(<la 1re morte>, <meilleure tuile>, Get(hp),
    #     healType = 2 = Any), Owner, 0x28), Group(PerformAIAttack(<une Geminae VIVANTE a portee
    #     `range`, tiree au hasard>, allowOnlyMove: 1), <la meme>, 0x20)) & DeactivateEffect(Owner,
    #     0x5b6)`.
    # ⚠ L'EFFET 1462 n'a AUCUNE classe native (11 symboles `ArdentBlade` au build, aucun sous
    # `Entities.Effects.*`) : c'est un JETON A UN COUP, pas un modificateur -- rien a inscrire dans
    # `EFFECT_CLASSES`. Et `DeactivateEffect` l'ETEINT sans le RETIRER (`RemoveEffect` = slot
    # distinct, jamais emprunte) : supprimer l'instance romprait le cycle en silence.
    # Cf. loki/the_ardent_blade.py.
    "TheArdentBlade": [TheArdentBladeTriggerAbility],
    # PhasalSubjugator (relique `R_*_PhasalSubjugator`, `TriggeredAbilityType` 0x615 = 1557 ; porteur
    # `necroOverlord`, HERO du pool rank 17 -> `--equip-relic` suffit). #1011-r1. DEUX classes
    # natives pour UNE cle -- et c'est LU : `AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggered
    # Abilitiesu003Eb__28_433` construit UNE `List` et y `Add` DEUX elements (controle : `b__28_432`,
    # la cle voisine 0x614, n'en construit qu'UN).
    #   * `PhasalSubjugator_SummonAbility` -- `On(0x1c = ArrivedAtFinalTile, alive) & OwnerIsActor &
    #     NOT AmountIsGreaterThanZero(Friends(Owner, UnitsWithVisualId(VisualUnitIdFromUnitId(
    #     GetStringConstant(0) = "necroSmnWarrior"), 1 = OnlyAlive), 1 = OnlyAlive))`
    #     -> `Spawn(Owner, First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(Owner)),
    #        7 = Tile, Owner), 1), unitId, WithStatsFromConfig(config, abilityState))` ;
    #   * `PhasalSubjugator_TriggerPassiveAbility` -- `On(0x29 = UnitFinishedTurnNormally, alive) &
    #     OwnerIsActor` -> `If(NOT HasFriendlyWarrior(), <le meme Spawn>) & IfAlive(Owner,
    #     TriggerAbility(Owner, 0x614 = MyWillBeDoneOverlord, selectionType: 3,
    #     ignoreUnitHavingAbility: false))`.
    # ⚠ SON `CreateTrigger` EST INVISIBLE DES DEUX TABLES (corps DEDUPLIQUE) : l'appartenance est
    # etablie par la STRUCTURE de `frida/methods.tsv` (ordre `methodPointers` PAR CLASSE VISITEE --
    # la ligne `efad70 CallInReinforcementsAbility.CreateTrigger` s'intercale entre les deux methodes
    # de `PhasalSubjugator_TriggerPassiveAbility`, et MANQUE de son propre groupe naturel), et le
    # corps partage est GENERIQUE (`On(0x29, alive) & get_OwnerIsActor`, aucun litteral propre).
    # ⚠ Le gate `HasFriendlyWarrior` est un CONJOINT DU TRIGGER pour la classe 1 et un `If` DU
    # BEHAVIOUR pour la classe 2 : le re-declenchement de 1556 se produit MEME quand un Guerrier vit.
    # Le re-declenchement passe par `TRIGGERED_ABILITY_BEHAVIOURS[MyWillBeDoneOverlord]`, pose dans
    # `loki/my_will_be_done_overlord.py` (branche `Custom`, patron `AdaptiveStrategy`).
    # Cf. loki/phasal_subjugator.py.
    "PhasalSubjugator": [PhasalSubjugatorSummonAbility, PhasalSubjugatorTriggerPassiveAbility],
    # ElectrochaffBackups (#1025) -- ability **MYTHIQUE** de MACHINE OF WAR, pas une relique, et
    # pourtant elle entre ICI : la voie de registration COTE COMBAT est la MEME, et c'est LU, pas
    # suppose. `IdunMetaLogic.UserProgress.TertiaryAbilities$$GetTertiaryAbility` (le foyer META qui
    # REMPLIT `BC.Units[].TertiaryAbility`) branche sur item-relique OU mythique et ecrit le MEME
    # champ ; `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` fait ensuite
    # l'UNIQUE `TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)`. Le natif de combat
    # ne distingue donc PAS les deux, et un registre `MYTHIC_*` separe serait un artefact du port.
    # Substrat cote port : `UnitContext.tertiary_ability` (montage `rl_duel build --equip-mythic`,
    # ou `catalog_inject.equip_mythic`). Le gameconfig, lui, la range sous `mythicAbilities` --
    # cle META que `collect_triggered_abilities` ne lit PAS, exactement comme le natif.
    # `TriggeredAbilityType` 0x5ae = 1454 ; DEUX porteurs : `tauBroadside` (lineup) et
    # `tauNpcMoWBroadside` (npc). UNE classe native, un `CreateTrigger` DISJONCTIF (`op_BitwiseOr`)
    # -> DEUX classes portees, une par `On()` (patron `FuryFromTheDelve`) :
    #   * `On(0x3e = EffectAdded) & <commun> & TriggeringEffectIs(0x462 = Markerlight)` ;
    #   * `On(0x0f = DamageTaken) & <commun> & IsRangedAttack()` ;
    # avec `<commun> = AreEnemies(Owner@+0x30, Target@+0x60) & IsNormalUnit(Target@+0x60)`.
    # Behaviour UNIQUE : `If(HasEffect(Target, 0x5a6, onlyActive: 0, 6),
    #                       ChangeEffectTurns(Target, 0x5a6, turns, ChangeType.Set),
    #                       AddEffect(0x5a6, stateRef, Owner, Target, turns))`.
    # ⚠ L'EFFET 0x5a6 = 1446 n'entre PAS dans `EFFECT_CLASSES`, et c'est DELIBERE : son
    # `CreateDamageModifier` ouvre sur `HasRarity(Target, 5 = Mythic)`, qui lit
    # `GetBaseUnitComponent(e)+0x74` -- canal ABSENT du port (residu `#1025-r1`, BLOCAGE capteur).
    # L'inscrire sans ce gate serait un terme PERMISSIF. Cf. loki/electrochaff_backups.py.
    "ElectrochaffBackups": [ElectrochaffBackupsOnMarkerlightAbility,
                            ElectrochaffBackupsOnRangedDamageAbility],
    # HyperCorrosiveAcid (#1035) -- ability **MYTHIQUE** de MACHINE OF WAR, meme voie de
    # registration que la relique (cf. le commentaire d'`ElectrochaffBackups` juste au-dessus :
    # `BC.Units[].TertiaryAbility` -> `TriggeredAbilityComponent$$TryAdd(id, tertiaryState, 3)`).
    # `TriggeredAbilityType` 0x5af = 1455 ; DEUX porteurs : `tyranBiovore` (lineup, AU SEED) et
    # `tyranNpcMowBiovore` (npc). `frida/classes.tsv` : parent `IdunBattle.Entities.Abilities.
    # BaseTriggeredAbility`, et la classe DECLARE ses deux methodes (rien d'herite).
    #   `$$CreateTrigger`   = On(0x0f = DamageTaken, ownerNeedsToBeAlive: 1)
    #                         & AreEnemies(Owner@+0x30, Target@+0x60, 0) & IsAlive(Target@+0x60)
    #                         & AreFriends(Owner@+0x30, Actor@+0x40, 0, false)
    #                         & IsUnitWithVisualId(Actor@+0x40, VisualUnitIdFromUnitId(
    #                               GetStringConstant(0x0 = unitId) = "tyranSmnSporeMine"))
    #   `$$CreateBehaviour` = If( HasEffect(Target@+0x60, 0x5a8, onlyActive: 0, effectTarget: 6),
    #                             ChangeEffectTurns(Target@+0x60, 0x5a8, turns, ChangeType.Set),
    #                             AddEffect(0x5a8, stateRef, Owner@+0x30, Target@+0x60, turns) )
    # avec `turns = TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds))`.
    # ⚠ LE GATE PORTE SUR L'ACTEUR, PAS SUR LE PORTEUR : c'est la SPORE MINE amie qui doit frapper
    # (`Actor@+0x40`), et l'effet se pose sur SA victime (`Target@+0x60`). Aucun `get_OwnerIsActor`
    # -- le Biovore n'a pas a etre l'attaquant, et ne le sera jamais sur ce vecteur.
    # ⚠ L'EFFET 0x5a8 = 1448 n'entre PAS dans `EFFECT_CLASSES`, et c'est DELIBERE : son
    # `$$CreateEffectDamageBonusForAttack` ouvre sur `HasRarity(Caster@+0x48, 5 = Mythic)` (plus
    # `HasTrait(Caster, 0x10 = Hero)`), qui lit `GetBaseUnitComponent(e)+0x74` -- canal ABSENT du
    # port (residu `#1035-r1`, BLOCAGE capteur, meme verrou que `#1025-r1`). L'inscrire sans ce gate
    # serait un terme PERMISSIF. Cf. loki/hyper_corrosive_acid.py.
    "HyperCorrosiveAcid": [HyperCorrosiveAcidAbility],
    # ShieldOfFaith (#1024-r1) -- MYTHIQUE d'`adeptExorcist` (MoW Sisterhood), `TriggeredAbilityType`
    # 0x5ad = 1453. ELLE ENTRE ICI PARCE QUE LE NATIF N'A QU'UNE VOIE TERTIAIRE, et c'est LU :
    # `catalog_inject.equip_mythic` ecrit le MEME `BC.Units[].TertiaryAbility` et declenche le MEME
    # `TriggeredAbilityComponent$$TryAdd(id, tertiaryState, 3)` d'`IdunBattle.Entities.Factories.
    # UnitFactory$$AddConfiguredAbilities` qu'une relique equipee -- seule la GARDE d'attribution
    # differe (`units.<kind>.<id>.mythicAbilities` au lieu d'`items[*].allowedUnits`). Un registre
    # `MYTHIC_*` separe inventerait une distinction que le natif n'a pas ; c'est aussi ce registre
    # qui donne a `triggered_ability_state` le couple TERTIAIRE (niveau 1..4, mult 100), et non le
    # couple PASSIF (50/180) qui lirait le dernier palier en silence.
    #   `$$CreateTrigger` = ( On(5 = PreAttack, true) & IsUnitOnTileWithEffect(Target@+0x60,
    #                             EffectType[]{ 5 = Fire }) )
    #                     | ( On(9 = Attack, true) & WasCrit() )
    #                     & IsUnit(Attacker) & AreFriends(Owner@+0x30, Attacker, 0, false)
    #                     & HasRarity(Attacker, idun.meta.Rarity.Mythic = 5)
    #   `$$CreateBehaviour(.., triggerType != Custom)` = TriggerAbilityDelayed(Owner@+0x30, 1453, 3)
    # La disjonction d'`On()` se ventile en `event_ids` (patron `RelicOfLostCadia`) ; la POSE du
    # bouclier vit dans la branche `Custom`, donc dans `CUSTOM_TRIGGERED_ABILITIES[1453]`.
    # ⚠ Contrairement a `HyperCorrosiveAcid` ci-dessus, le gate `HasRarity` N'EST PLUS un verrou :
    # le canal existe depuis #1039 (`combatSnapshot.units[].rarity`) et est consomme depuis #999-r3
    # par `UnitContext.rarity` -- c'est le noeud `HasRarity` qui le lit, avec son tri-etat.
    # Cf. loki/shield_of_faith.py.
    "ShieldOfFaith": [ShieldOfFaithAbility],
}

# --- Registre : abilities GLOBALES (aucun owner) ---------------------------------------------------
# Les abilities `IdunBattleLogic.Entities.Abilities.Damage.Loki.*` ne sont portees par AUCUNE unite :
# leur `CreateTrigger` ne teste que le PROFIL DU COUP, jamais un owner (`get_OwnerIs*` absent). Elles
# sont donc inscrites UNE SEULE FOIS pour la bataille -- une inscription par entite les ferait firer N
# fois par evenement, ce que la mesure live REFUTE (exactement UN `NextBool` par serie de coups pour le
# canal 1203, oracle = etat MT). Cf. `core.collect_global_triggers`.
#
#   OnFireDamageAbility  (1016) : On(0x10) & DamageProfileHasTrait(1 = OnFire)  & !TriggeringEffectIs(5)
#                                 -> AddEffect(5 = Fire, Tiles(Target()))            [INCONDITIONNEL]
#   OnToxicDamageAbility (1203) : On(0x10) & DamageProfileHasTrait(4 = OnToxic) & !TriggeringEffectIs(0x4dc)
#                                 -> If(IsFirstHitInSeries & Maybe(chance=25), AddEffect(0x4dc))
#
# Le 3e membre de la famille, `OnMeltaDamageAbility` (1211), est absent de ce registre pour une
# raison DIFFERENTE des deux autres -- et surtout PAS parce qu'il serait mort (#488-r1).
# Son `CreateTrigger` EXISTE sur `rnca9r7q6c` (slot de vtable a la profondeur 0, RPC
# `resolveMethodPtr` ; le corps est DEDUPLIQUE, donc la table seule ne tranchait pas), mais son
# vecteur n'est pas `On(0x10 = DamageDealt)` : c'est `On(0x19 = MatchInit, true)`. Il ne pose donc
# RIEN on-hit -- il pose, UNE FOIS au debut du match, l'effet 1297 `Melta_ExtraDmg` sur une TUILE
# arbitraire (`AddEffect(1297, AbilityStateReference, First(AllTiles(), 1))`). Cet effet n'a aucun
# gate de porteur : il bonifie +50 % TOUT coup de profil `Melta` porte contre une cible `Vehicle`.
# Il est PORTE, mais par le canal du DEGAT (`MATCH_WIDE_EFFECTS`, `entities/effects/__init__.py`),
# pas par le bus d'events -- d'ou son absence ici. Cf. `docs/rl/case-488-r1-onmelta-vivant-ou-mort.md`.
GLOBAL_TRIGGERS: list[type[TriggeredAbility]] = [
    OnFireDamageAbility,
    OnToxicDamageAbility,
]


# ---------------------------------------------------------------------------------------------
# TRIGGERED-ABILITIES DIFFEREES (#406) : `TriggeredAbilityType (int) -> classes portant la branche
# `triggerType == 0x20 = Custom` de leur `CreateBehaviour`.
#
# Ce registre est le mirror de l'etape (2) de `IdunBattle.Operations.
# TriggerTriggeredAbilityOperation$$TriggerAbility` -- « quelles triggered-abilities de CE type
# l'entite porte-t-elle » (slot 1 du cache d'abilities). Il n'est JAMAIS consulte par le bus
# d'events : ses entrees n'ont pas de `CreateTrigger` et ne sont atteintes que par le drain de
# `state.pending_triggered_abilities` (`dispatch/pending.py`), arme par le noeud DSL
# `TriggerAbilityDelayed`.
#
# ⚠ Une entree ici CHANGE le chemin du noeud `TriggerAbilityDelayed` pour cette ability : elle la
# fait passer du collapse INLINE herite a la vraie file. Ne l'ajouter qu'apres avoir lu la branche
# `Custom` du `CreateBehaviour` correspondant.
CUSTOM_TRIGGERED_ABILITIES: dict[int, list[type[TriggeredAbility]]] = {
    # 1187 HarlequinsPanoply : `Inform(0xb6) + If(NOT IsAdjacent(Owner, Caster, 3), MoveUnit(...))`
    # = le deplacement d'UN hex vers l'attaquant, arme par le `TriggerAbilityDelayed(Owner, 1187, 3)`
    # de la branche `On(0x3c = UnitBlocked)` de la MEME ability. cf. loki/harlequins_panoply.py.
    HARLEQUINS_PANOPLY_ABILITY: [HarlequinsPanoplyCustomAbility],
    # 1531 HaywireMine : `if (triggerType == 0x20 = Custom) return Spawn & AddPersistentData;` --
    # la branche NUE, SANS le `If(Count(tiles) > 0, ..., TriggerAbilityDelayed)` qui l'enveloppe sur
    # les deux vecteurs reels. Elle est armee par le `TriggerAbilityDelayed(Owner, 0x5fb, 3)` de
    # cette MEME ability, c'est-a-dire quand le selecteur de tuiles rend VIDE (typiquement : la
    # tuile precedente est occupee par la mine que le deplacement vient d'y poser). Le
    # re-declenchement re-evalue le selecteur a l'etat COURANT ; si la tuile est toujours prise, le
    # `Spawn` est un no-op et seul l'`AddPersistentData` mord. Cf. loki/haywire_mine.py.
    HAYWIRE_MINE_ID: [HaywireMineCustomAbility],
    # 1449 UnwaveringSentinel (#946) : la branche `triggerType == 0x20 = Custom` de
    # `UnwaveringSentinelAbility$$CreateBehaviour` = `IfAlive(Caster, AttackWithAttackDamage(Owner ->
    # Caster, MinMaxDamage(abilityState), GetDamageProfile(), GetHits()))`. Elle est armee par le
    # `TriggerAbilityDelayed(Owner, 0x5a9, OnlyAliveAndTargetable)` que le `GetCounterAttackBehaviour`
    # de l'EFFET 1439 pose sur `On(0x9 = Attack)`. Le litteral `0x20` du re-declenchement est LU
    # (dernier argument de l'appel au slot 4 dans
    # `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility`), pas deduit.
    # cf. loki/unwavering_sentinel.py.
    UNWAVERING_SENTINEL_ABILITY: [UnwaveringSentinelCustomAbility],
    # 1491 BladeOfTheAncestors (#1001) : la branche `triggerType == 0x20 = Custom` de
    # `BladeOfTheAncestors_RemoveEffectAbility$$CreateBehaviour` = `RemoveEffect(Owner@+0x30,
    # Nullable(0x5d1 = 1489))` -- LE RESET du buff crit. Armee par le `TriggerAbilityDelayed(Owner,
    # 0x5d3, 3)` de la branche `!= Custom` de la MEME classe, sur `On(9) & OwnerIsCaster & WasCrit`.
    # ⚠ L'AUTRE classe de 1491, `BladeOfTheAncestorsAbility`, a elle aussi une branche `Custom` --
    # et elle vaut `DSLBehaviors$$Nothing()`. Le natif l'appelle au drain et elle ne fait RIEN :
    # l'inscrire ici serait un mensonge de couverture (une classe de no-op), pas une fidelite.
    BLADE_OF_THE_ANCESTORS: [BladeOfTheAncestorsCustomRemoveEffectAbility],
    # 1453 ShieldOfFaith (#1024-r1) : la branche `triggerType == 0x20 = Custom` de
    # `ShieldOfFaithAbility$$CreateBehaviour` = `If( IsAlive(Attacker) & AmountIsZero(
    # CurrentShieldAmount(Attacker, 3)), CreateShield(Attacker, PercentageOf(StatAmount(Attacker,
    # Health, Maximum), ConfigVar(0x96 = shieldPct)), <AbilityOrEffect>, TurnsFromRounds(1)) )`.
    # Armee par le `TriggerAbilityDelayed(Owner@+0x30, 0x5ad, 3)` de la branche `!= Custom` de la
    # MEME classe, sur les DEUX vecteurs (`On(5) & tuile en feu` | `On(9) & WasCrit`).
    # ⚠ SANS CETTE ENTREE le noeud retomberait sur le collapse INLINE, qui poserait le bouclier
    # AVANT la resolution des degats : le bon observable et le mauvais ORDRE.
    SHIELD_OF_FAITH_ABILITY: [ShieldOfFaithCustomAbility],
}

# --- Registre : effectType → effet-trigger(s) ------------------------------------------------------
# ⚠ La valeur est une LISTE : cote natif, `BaseEffect.CreateHandleTriggerAbilitiesInternal` renvoie un
# **`ArraySet`** (N `Triggered(trigger, behaviour)` par effet) — ex. `PhoenixGem_CanReviveEffect
# IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` en enregistre DEUX. Un dict 1->1 ne pouvait pas les porter.
EFFECT_TRIGGERS: dict[int, list[type[EffectTrigger]]] = {
    # 1009 : le trigger de TIR (`CreateTargetTrigger`, On(4)) + les TROIS `Triggered()` de
    # `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` qui
    # pilotent `EffectComponent.IsActive @+0x5c` de l'instance (activation au tour adverse, desactivation
    # au tour du porteur, desactivation des que le porteur attaque = « un seul tir par activation »).
    OVERWATCH_AUTO_ATTACK: [OverwatchAutoAttack,                      # On(4)    -> le TIR
                            RangedAutoAttackActivateOnTurnStart,      # On(0x12) -> ActivateEffect
                            RangedAutoAttackDeactivateOnTurnStart,    # On(0x12) -> DeactivateEffect
                            RangedAutoAttackDeactivateOnAttack],      # On(10)   -> DeactivateEffect
    # BloodChalice_HealOnAttack 0x558=1368 (pose par 1175, #576) : `...BloodChalice_HealOnAttackEffect
    # $$CreateTargetTrigger` = `On(0x9 Attack, 1) & get_OwnerIsCaster & IsMeleeAttack` ->
    # `$$CreateTargetTriggerBehaviour` = `Heal(EffectSource, Owner@0x30, ConfigVar(0x20 hpToHeal),
    # HealBehaviourOptions.ForHeal)`. Le SECOND volet de l'effet (le +percage de
    # `$$CreatePiercingBonusForAttack`) n'est PAS un trigger : il vit dans
    # `entities/effects/loki/blood_chalice.py`.
    BLOOD_CHALICE_HEAL_ON_ATTACK: [BloodChaliceHealOnMeleeAttack],    # On(9) -> Heal
    # HealingBalms 0x5e4=1508 (pose par l'active substituee `1212 HealingBalms_Heal`, #966) : le
    # SOIN RETARDE. `...HealingBalmsEffect$$CreateTargetTrigger` = `On(0x13 = TurnStart_Other, 1) &
    # <DSLTriggers+0x28 = IsTurnOf(Owner)>` -> `$$CreateTargetTriggerBehaviour` =
    # `Heal(EffectSource, Owner@0x30, ConfigVar(0x20 hpToHeal), ForHeal) op_Addition
    # GetRemoveEffectBehaviour(this)`. Le second terme est ce qui rend le soin ONE-SHOT ; sans lui
    # l'effet soignerait a CHAQUE debut de tour du porteur jusqu'a expiration -- degradation
    # PERMISSIVE, aucune erreur. Les DEUX autres effets du kit (1503/1504) sont des stat-mods sans
    # trigger -> `EFFECT_CLASSES`, pas ici.
    HEALING_BALMS_EFFECT: [HealingBalmsDelayedHeal],                  # On(0x13) -> Heal + Remove
    # 1130 CloseCombatWeakness_ReduceDmg (trait T'AU 1035, 16 porteurs npc, #1015-r1) :
    # `...CloseCombatWeakness_ReduceDmg_Effect$$CreateTargetTrigger` = `On(0x12 =
    # TurnStart_EffectActivation, 1) & HasAdjacentEnemies(Owner@+0x30, Tiles(Owner@+0x30), false,
    # false)` -> `$$CreateTargetTriggerBehaviour` = `AddEffect(0x469 = 1129
    # CloseCombatWeakness_StartedTurnAdjacentToEnemy, Owner, turns = <DSLFormulas+0x20> = Direct(1))`.
    # Le VOLET DEGAT de l'effet (le -50 %/-25 %) n'est PAS un trigger : il vit dans
    # `entities/effects/loki/close_combat_weakness.py`, canal `CreateEffectDamageBonusForAttack`.
    CLOSE_COMBAT_WEAKNESS_REDUCE_DMG: [CloseCombatWeaknessMarkStartedTurnAdjacent],   # On(0x12)
    # HazeOfCorruption_DamageTransfer 0x435=1077 (case-209, bond pose par le target-finder de #207) :
    # `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger` =
    # `(OnDeath & (TriggeringAbilityIs(0x435) | AreEqual(Actor, bonded)) | On(0x2d = UnitRevived) | On(0x34 = UnitFled))
    # & IsAlive(bonded) & AreEqual(Target, EffectSource)` -> le RELAIS encaisse, de la part du
    # porteur, chaque `LeftOverDamage` que la cible initiale a gaspillee.
    # 1111 WireweaveNet_CounterAttack (passif `eldarRanger` <<Calandis>>) : le trigger de RIPOSTE
    # (`CounterAttackEffect$$CreateTargetTrigger`, `On(0x2a = PreUnitAbility)`) + les DEUX
    # `Triggered()` de la branche `ActivationFrequency == 2` de
    # `IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal` qui
    # pilotent `EffectComponent.IsActive @+0x5c` (desarmement au debut du tour du porteur,
    # re-armement a sa fin -> la fenetre est le tour ENNEMI). Le « the FIRST time » d'i2 vient du
    # `& DeactivateEffect(effect)` que `$$CreateTargetTriggerBehaviour` ajoute a la riposte.
    WIREWEAVE_NET_COUNTER_ATTACK: [WireweaveNetCounterAttack,                  # On(0x2a = PreUnitAbility) -> la RIPOSTE
                                   WireweaveNetDeactivateOnOwnerTurnStart,     # On(0x12) -> DeactivateEffect
                                   WireweaveNetActivateOnOwnerTurnEnd],        # On(0x17) -> ActivateEffect
    # 1213 GrimRetribution_CounterAttack (passif `darkaHellblaster` <<Sarquael>>, #946) : MEME famille
    # que 1111 ci-dessus, mais `activationFrequency = 1` -- donc la paire de `Triggered()` est
    # l'INVERSE (armement au DEBUT de chaque tour ENNEMI, desarmement a sa FIN => une riposte PAR TOUR
    # ennemi, non une par cycle), et le trigger de riposte est `On(0x9 = Attack)`, pas
    # `On(0x2a = PreUnitAbility)` : le coup adverse a deja porte quand Sarquael riposte.
    # cf. loki/grim_retribution.py.
    GRIM_RETRIBUTION_COUNTER_ATTACK: [GrimRetributionCounterAttack,             # On(0x9)  -> la RIPOSTE
                                      GrimRetributionActivateOnEnemyTurnStart,  # On(0x12) -> ActivateEffect
                                      GrimRetributionDeactivateOnEnemyTurnEnd], # On(0x17) -> DeactivateEffect
    # 1439 UnwaveringSentinel_CounterAttack (passif `custoKyrus` <<Tyrith>>, #946) : MEME fenetre
    # d'armement que 1213, mais le behaviour de riposte n'attaque PAS -- il ENFILE un
    # `TriggerAbilityDelayed(Owner, 1449, OnlyAliveAndTargetable)`. Le degat tombe au drain, dans
    # `CUSTOM_TRIGGERED_ABILITIES[1449]`. cf. loki/unwavering_sentinel.py.
    UNWAVERING_SENTINEL_COUNTER_ATTACK: [UnwaveringSentinelCounterAttack,             # On(0x9)  -> ENFILE
                                         UnwaveringSentinelActivateOnEnemyTurnStart,  # On(0x12) -> ActivateEffect
                                         UnwaveringSentinelDeactivateOnEnemyTurnEnd], # On(0x17) -> DeactivateEffect
    # 1147 TerminatorArmour_ReduceDmg (trait `TerminatorArmour`, **44 porteurs**) : la REDUCTION
    # (-75 %, gate profil) vivait deja dans `entities/effects/loki/damage_reduction.py`, mais SANS
    # son cycle -- donc armee en permanence, alors que l'i2 dit « the FIRST attack each turn ». Les
    # QUATRE `Triggered()` natifs ecrivent `EffectComponent.IsActive @+0x5c` : consommation a la
    # cloture de la 1re attaque qualifiante (`CreateTargetTrigger` -> `DeactivateEffect`), re-armement
    # au turn-start et desarmement au turn-end (branche `ActivationFrequency == 1 (PerTurn)` de
    # `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal`, `TurnsEnabled == 2 (Both)`), plus la
    # re-activation `On(EffectAdded)` (structurellement inerte : le poseur est un
    # `OnOwnerSpecificAbilityInit` one-shot). Cf. loki/terminator_armour.py.
    # ⚠ Le jumeau `TerminatorArmour_Visual` (1375) n'a PAS d'entree ici, et c'est LU :
    # `TerminatorArmour_Visual_Effect$$CreateEffectDamageMalusForDefense` retourne un
    # `Nullable<EffectBonus>` VIDE (zeroe, aucun ctor) -- il ne reduit rien, son etat n'a aucun
    # observable de degat.
    # 1423 ArmourOfShriekingSouls (l'effet << Elated >> pose sur le TUEUR d'`emperLucius`) : les
    # TROIS `Triggered()` de son `CreateHandleTriggerAbilitiesInternal` + son couple
    # `CreateTargetTrigger`/`CreateTargetTriggerBehaviour` :
    #   * `On(0x16 = TurnStart_Actions) & <DSLTriggers+0x28 = IsTurnOf(Owner)>` -> `DirectDamage(
    #     EffectSource, Owner, RandomAmount(ConfigVar(minHp), ConfigVar(maxHp)))` -- le saignement ;
    #   * `On(0x25 = UnitRemoved) & get_OwnerIsTarget & IsDead(Owner)` -> `Resurrect(EffectSource
    #     sur Tiles(Owner))` -- Lucius revient sur l'hex de sa victime ;
    #   * `On(0x2e = UnitResurrected) & AreEqual(EffectSource, Target)` -> `RemoveEffect`.
    # ⚠ `<DSLTriggers+0x28>` est un CHAMP (pose par `DSLTriggers$$InitializeShared`), pas un appel :
    # son pointeur de classe n'est partage qu'avec `DSLTriggers$$IsTurnOf`.
    ARMOUR_OF_SHRIEKING_SOULS_EFFECT: [ArmourOfShriekingSoulsDrainOnTurnStart,        # On(0x16)
                                       ArmourOfShriekingSoulsResurrectOnRemoved,      # On(0x25)
                                       ArmourOfShriekingSoulsRemoveOnSourceResurrected],  # On(0x2e)
    TERMINATOR_ARMOUR_REDUCE_DMG: [TerminatorArmourDeactivateOnAttack,      # On(9)    -> DeactivateEffect
                                   TerminatorArmourActivateOnTurnStart,     # On(0x12) -> ActivateEffect
                                   TerminatorArmourDeactivateOnTurnEnd,     # On(0x17) -> DeactivateEffect
                                   TerminatorArmourActivateOnEffectAdded],  # On(0x3e) -> ActivateEffect
    # 1218 Neuroparasite (#462-r4b-r1-r1-r1) : les DEUX `Triggered()` que
    # `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal`
    # ajoute a l'`ArraySet`, tous deux vers `$$GetIncreaseLevelBehaviour` =
    # `IncreaseEffectLevel(Effect, Direct(1), max = $$GetMaximumLevel())` avec
    # `max = buffMaxLevel[lvl du passif du Neurothrope] + (effectLevel=1 si le bonde porte NornCrown)` :
    #   * `On(9) & OwnerIsTarget & CurrentAttackDamageProfilesContain(0xd)` -- toute attaque PSYCHIQUE
    #     subie par la victime (AUCUN gate sur l'auteur du coup : c'est le decompile) ;
    #   * `On(0x3d = PreEffectAdded) & OwnerIsTarget & TriggeringEffectIs(0x429 = 1065 Pinned)`.
    # Sans eux, tout parasite restait au NIVEAU 1 -- or l'additif de degat est `x EffectLevel`.
    # Le trigger de RETRAIT (a) herite d'`ABondEffect` s'AJOUTE a ces deux-la, par la derivation en
    # bas de fichier (`get_RemoveOnBondedEntityDeath` VRAI pour `NeuroparasiteEffect`) ; (b) et (c)
    # restent NON CONFRONTES. Cf. loki/neuroparasite.py et bond_removal.py.
    NEUROPARASITE_EFFECT: [NeuroparasiteIncreaseLevelOnPsychicHit,   # On(9)    -> +1 niveau
                           NeuroparasiteIncreaseLevelOnPinned],     # On(0x3d) -> +1 niveau
    # #1012-r1 -- `HeadwoppasKillchoppa_ExtraDmg` (0x620 = 1568), owner-effet de la relique
    # `HeadwoppasKillchoppa` d'`orksWarboss` << Gulgortz >>. UN SEUL `Triggered()` dans
    # `...HeadwoppasKillchoppaEffect$$CreateHandleTriggerAbilitiesInternal` :
    # `On(0x36 = UnitDefeated) & NOT IsSteppableUnit(Targets@+0x60) & AreEqual(Attacker(),
    # Owner@+0x30)` -> `IncreaseEffectLevel(Owner@+0x30, 1568, amount = null, max = null)`.
    # `amount` nul retombe sur `<DSLFormulas+0x20> = Direct(1)` ; `max` nul desactive le clamp
    # d'`IncreaseEffectLevelOperation$$Execute` -- AUCUN cap (contraste `Neuroparasite`, qui ecrit
    # `$$GetMaximumLevel`). MEME famille que les deux entrees `NEUROPARASITE_EFFECT` ci-dessus :
    # sans ce trigger l'effet resterait au niveau 0, donc INACTIF et sans magnitude, pour toujours.
    # Cf. loki/headwoppas_killchoppa.py (les deux, effet et trigger).
    HEADWOPPAS_KILLCHOPPA_EXTRA_DMG: [HeadwoppasKillchoppaIncreaseLevelOnKill],   # On(0x36) -> +1 niveau
    HAZE_DAMAGE_TRANSFER: [HazeOfCorruptionDamageTransferTrigger],
    CONTAMINATED_TILE: [ContaminatedTileEffect],  # tile-effect : enter(4)+tick(0x12) -> pose Contaminated_Unit
    FIRE_TILE: [FireTileDoT],                     # tile-effect : tick(0x14) -> DoT 20% PV initiale a l'occupant
    # DespoiledGround 0x5c4=1476 (#85) : MEME patron que le feu — `EnvDespoiledGroundTileAbility`
    # (`On(0x14) & Count(EntitiesWithAnyEffect(0x5c4))>0`) inflige a l'occupant non-immune un degat
    # tire dans [DespoiledGroundMinDmgPct, DespoiledGroundMaxDmgPct] % de sa PV MAX (profil
    # DirectDamage), puis pose 1478 (+%degat vs Xenos/Imperial) si l'occupant est Chaos a SON tour.
    DESPOILED_GROUND_TILE: [DespoiledGroundTileDoT],
    # MasterOfTheTutelaries (#202-C, effet 1197 pose par l'active 1096 d'Abraxas) : la collecte
    # par-effet-actif EST le Add/RemoveTriggeredAbility natif (IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal /
    # IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$RevertInternal) -> Screamer sur attaque Psychic vs ennemi (On(9), triggered 1173).
    MASTEROFTUTELARIES_EFFECT: [MasterOfTheTutelariesSummonAbility],   # 1197 -> 1173
    # RitesOfMorkai (#79, effet « Inspired » 1502 pose par l'active 1211 de spaceWolfPriest) = MEME base
    # `ReviveEffect` que Narthecium, mais rail EFFET (pose par une ACTIVE, pas par un passif) : filtre
    # IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$CreateTargetFilter = `OwnerIsTarget` (self-revive) et IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$.ctor `removeEffect=TRUE` -> le 2e volet du
    # behaviour est `RemoveEffect` (one-shot DEFINITIF) et non `DeactivateEffect` (once-per-turn).
    RITES_OF_MORKAI_EFFECT: [RitesOfMorkaiReviveTrigger],            # 1502 (self-revive one-shot)
    # ReanimationBeam (#79, effet 1547 pose par l'active 1223 de la MoW necroReanimator) = base
    # ReviveEffect, filtre IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter = AreFriends & HasTrait(Mechanical=5) & HasEffect(1545
    # NanoscarabRepairProtocols) ; IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$.ctor removeEffect=TRUE -> one-shot.
    REANIMATION_BEAM_EFFECT: [ReanimationBeamReviveTrigger],         # 1547 (allie Mechanical nanoscarabe)
    # AttemptedPossession_Possessed (#590-r3, effet 1209 pose par l'active 1101 de `thousSorcerer`) --
    # le trigger de PROPAGATION greffe par
    # `IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect$$CreateHandleTriggerAbilitiesInternal` :
    # `On(0x32 UnitAdded) & AmountIsZero(Count(Parent(Owner))) & AreEqual(Parent(Actor), Owner)` ->
    # `AddBondEffect(0x4b9, targets = Actor, bondedEntity = BondedEntityFromEffect(Effect), turns = 1)`.
    # Tout summon qui apparait sous la coupe de l'unite possedee est possede a son tour, 1 tour, bonde
    # au MEME caster. Rail `ArraySet` -> AUCUN gate `IsActive` (case-229).
    # Les TROIS retraits HERITES d'`ABondEffect` sont, eux, DERIVES de `BOND_REMOVAL_GATES` par la
    # boucle `bond_removal_registry_entries()` plus bas -- 1209 y arme le seul gate (a).
    POSSESSED_EFFECT: [AttemptedPossessionPropagate],                 # 1209 (propagation aux summons)
    # PhoenixGem (#79, relic d'eldarAutarch) : PAS un ReviveEffect -- `PhoenixGem_ReviveAbility`
    # (IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour) enregistree par l'effet-marqueur `PhoenixGem_CanReviveEffect` 1451
    # (IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal). Self-revive INCONDITIONNEL (pas de Maybe), **even if Overkilled**, one-shot par
    # bataille. Le `IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` de l'effet enregistre en plus les
    # DEUX triggers de RETRAIT du marqueur (case-89 volet B3) : `On(0x2d=UnitRevived) & OwnerIsTarget &
    # CurrentAbilityIs(PhoenixGem=0x5b2)` et `On(0x2e=UnitResurrected) & OwnerIsTarget`.
    # #1006 -- `Maugetar_HasNotMovedEffect$$CreateRemoveEffectTrigger` = `On(0x1f = PreUnitMove,
    # ownerNeedsToBeAlive: true) & get_OwnerIsActor` -> `RemoveEffect(EffectSelf)`. C'est le SEUL
    # trigger propre de l'effet 1497 ; son autre canal (`$$CreateAdditionalHits`) est un descripteur
    # du canal #179, pas un trigger d'evenement -> `EFFECT_CLASSES["Maugetar_HasNotMoved"]`.
    # ⚠ L'ABILITY seule laisserait un `BaseEffect` NU qui ne se retire jamais ; l'EFFET seul ne
    # serait jamais (re)pose. Les DEUX registres, dans le MEME commit.
    MAUGETAR_HAS_NOT_MOVED: [MaugetarHasNotMovedRemoveOnMove],       # 1497 -> retrait au PRE-move
    PHOENIX_GEM_CAN_REVIVE: [PhoenixGemReviveAbility,                # 1451 (self-revive, even-if-overkill)
                             PhoenixGemRemoveMarkerOnRevive,         # On(0x2d = UnitRevived) -> RemoveEffect(1451)
                             PhoenixGemRemoveMarkerOnResurrect],     # On(0x2e = UnitResurrected) -> RemoveEffect(1451)
    # FuelledByFury_CanRevive 1324 (#88 A1, marqueur POSE PAR LE JEU a l'init d'ultraTitus -- donc capte
    # tel quel par le snapshot live) : l'`ArraySet` d'`IdunBattle.Entities.Effects.Loki.
    # FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` n'enregistre QUE les 3
    # triggers qui pilotent son etat ACTIF (`EffectComponent.IsActive @+0x5c`) -- l'ability de revive,
    # elle, est portee par le PASSIF (`ABILITY_TRIGGERS["FuelledByFury"]`). Contraste PhoenixGem : ici
    # c'est une DESACTIVATION (once-per-TURN, re-armee au tick 0x12), pas un retrait definitif.
    FUELLED_BY_FURY_CAN_REVIVE: [FuelledByFuryCanReviveActivateOnAbilityInit,    # On(0x21) -> Activate
                                 FuelledByFuryCanReviveActivateOnTurnStart,     # On(0x12) -> Activate
                                 FuelledByFuryCanReviveDeactivateOnRevive],     # On(0x2d = UnitRevived) -> Deactivate
    # AnvilShield_FrozenAttackerAdvantage (#100, effet 0x4b1=1201 pose par le volet `On(0x2a = PreUnitAbility)`) : son
    # SEUL trigger propre est `IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect
    # $$CreateTargetTrigger` = `On(0xe=UnitPostAbility) & AreEqual(target@0x178, EffectSource(this))` ->
    # le bonus +20 % block ne vit QUE le temps de l'ability qui l'a declenche (ground truth live).
    ANVIL_FROZEN_ADVANTAGE: [AnvilShieldFrozenAdvantageExpire],      # 1201 -> conso a UnitPostAbility
    # InspiredToGreatness_OverrideLevel (#114 residu 2, effet 1180 pose par l'active 1082 de tauAunShi
    # sur l'allie `canReset`) : son SEUL trigger est celui que `BaseEffect$$CreateHandleTriggerAbilities`
    # greffe quand `CreateRemoveEffectTrigger` est non nul --
    # `InspiredToGreatness_OverrideLevelEffect$$CreateRemoveEffectTrigger` = `On(0xc) & OwnerIsCaster`
    # -> `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette instance>)`. Borne l'override de
    # `ACTIVE_ABILITY_LEVEL` au PROCHAIN CAST D'ACTIF du porteur.
    ITG_OVERRIDE_LEVEL: [InspiredToGreatnessOverrideLevelRemove],    # 1180 -> retrait On(0xc)
    # Chronometron_ExtraDamage (residu R9, effet 1550 pose par l'active 1226 de `necroChronomancer` sur
    # chaque ennemi du disque rayon 2) : meme greffe generique que 1180 --
    # `Chronometron_ExtraDamageEffect$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget &
    # IsUnit(caster) & AreFriends(caster, EffectSource)` -> `RemoveEffect(<cette instance>)`. C'est ce
    # qui fait du +degat une CHARGE A USAGE UNIQUE (consommee au 1er coup d'un allie du Chronomancer),
    # et non un buff persistant. Cf. loki/chronometron.py.
    CHRONOMETRON_EXTRA_DAMAGE: [ChronometronExtraDamageRemove],      # 1550 -> retrait On(9)
    # TimesplinterMantle_DamageReduction (0x60f = 1551, pose CHAQUE debut de tour par le passif 1534
    # de `necroChronomancer` sur lui-meme + ses allies Mechanical non-Steppable adjacents).
    # `...TimesplinterMantle_DamageReductionEffect$$CreateRemoveEffectTrigger` est une DISJONCTION --
    # `(On(9 = Attack) & OwnerIsTarget & IsUnit(Caster)) | On(0x17 = TurnEnd)` -- et le registre du
    # port etant indexe par `event_id`, il faut UNE entree par disjoint (patron `HeavyWarpFlamer` /
    # `HaywireMine`). C'est ce couple qui fait de la reduction plate une CHARGE A USAGE UNIQUE
    # rearmee a chaque tour, et non un buff permanent. Cf. loki/timesplinter_mantle.py. #961.
    MANTLE_EFFECT: [TimesplinterMantleDamageReductionRemoveOnAttack,     # 1551 -> retrait On(9)
                    TimesplinterMantleDamageReductionRemoveOnTurnEnd],   # 1551 -> retrait On(0x17)
    # LivingLightning_MoveEffect (0x3fc = 1020, marqueur pose au PRE-MOVE de `necroPlasmancer` quand
    # sa destination a un ennemi adjacent). `...LivingLightning_MovingEffect$$
    # CreateRemoveEffectTrigger` = `On(0x1c = ArrivedAtFinalTile) & OwnerIsActor`. Sans cette entree
    # le marqueur serait PERMANENT (aucune duree posee, absent de `DefaultAmountOfRounds`).
    # Cf. loki/living_lightning.py. #961.
    LIVING_LIGHTNING_MOVE_EFFECT: [LivingLightningMovingRemoveOnArrived],   # 1020 -> retrait On(0x1c)
    # HeraldOfTheApocalypse 1027 (#BL-1020r, effet pose par `HeraldOfTheApocalypseAbility$$Execute
    # Behaviour` de `blackHaarken` sur la cible ET l'ennemi derriere elle). Meme greffe generique --
    # `HeraldOfTheApocalypse_ExtraDamageEffect$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget &
    # IsUnit(caster)` -> `RemoveEffect(<cette instance>)`. ⚠ SANS l'`AreFriends(caster, EffectSource)`
    # de 1550 : ici N'IMPORTE QUELLE unite qui attaque le porteur consomme la charge. i2 : « the NEXT
    # attack made by a unit against them ». Cf. loki/herald_of_the_apocalypse.py.
    HERALD_OF_THE_APOCALYPSE_EFFECT: [HeraldOfTheApocalypseExtraDamageRemove],   # 1027 -> retrait On(9)
    # EuphoricStrikes_ExtraCrit 1429 (#522, effet pose par `EuphoricStrikesAbility$$ExecuteBehaviour`
    # sur la cible d'`emperExultant` « Laviscus »). Meme greffe generique que 1180/1550 --
    # `EuphoricStrikes_ExtraCritEffect$$CreateRemoveEffectTrigger` = `On(9 = Attack, alive) &
    # OwnerIsTarget | On(0 = UnitDeath, alive) & AreEqual(Target, EffectSource(Effect))` ->
    # `RemoveEffect(<cette instance>)`. C'est ce qui fait du +crit-chance une CHARGE A USAGE UNIQUE
    # (i2 : « The **next** attack against that enemy this turn ») et non un buff de tout le tour ;
    # le 2e disjoint fait sauter la marque si Laviscus meurt avant qu'elle serve. Sans cette entree :
    # regression PERMISSIVE et SILENCIEUSE, forme exacte de 1550/1000. Cf. loki/euphoric_strikes.py.
    EUPHORIC_STRIKES_EXTRA_CRIT: [EuphoricStrikesExtraCritRemove],    # 1429 -> retrait On(9) | On(0)
    # ShockAssault_Buff 1000 (case-366-r1, effet pose par `ShockAssaultAbility$$CreateBehaviour` sur
    # les Inceptors amis adjacents a `ultraInceptorSgt`). Meme greffe generique que 1180/1550 --
    # `ShockAssaultBuffEffect$$CreateRemoveEffectTrigger` = `On(0xa = AttackDamageAttack) &
    # OwnerIsCaster` -> `RemoveEffect(<cette instance>)`. Sans cette entree le `+extraDmg` d'ATTACK
    # serait PERMANENT (la pose a `turns = NULL`) la ou l'i2 dit « for this attack » : regression
    # PERMISSIVE et SILENCIEUSE. Le MEME event porte la POSE (`ShockAssaultAbility$$CreateTrigger`),
    # mais sur un `OwnerIsCaster` qui designe le BELLATOR -- ici c'est l'INCEPTOR.
    # Cf. loki/shock_assault.py.
    SHOCK_ASSAULT_BUFF: [ShockAssaultBuffRemove],                    # 1000 -> retrait On(0xa)
    # LegendaryCommander_ExtraHits 1395 (#419-r1-tr9-r4-r1-r2-r1, effet pose SUR `custoTrajann` par
    # son passif) : le TARGET-TRIGGER de l'effet, `LegendaryCommander_ExtraHitsEffect$$
    # CreateTargetTrigger` = `On(0xa = AttackDamageAttack) & IsValidAttack(Effect@0x38)` ->
    # `$$CreateTargetTriggerBehaviour` = `AddToPersistentDataList(<AbilityOrEffect>,
    # EffectSource(Get(effect)), EntityId(Owner@0x30), EntityId(Caster@0x48))`. C'est l'ECRIVAIN du
    # << first attack >> : sans lui la liste reste vide et le bonus de coups s'applique a CHAQUE
    # attaque d'ability -- regression PERMISSIVE et SILENCIEUSE (forme de #436).
    # Cf. loki/legendary_commander.py.
    LEGENDARY_COMMANDER_EXTRA_HITS: [LegendaryCommanderExtraHitsMarkCaster],
    # HatefulAssault_AlreadyAttacked (case-366-r1, effet 1175 pose par `HatefulAssaultAbility$$
    # CreateBehaviour` sur l'ennemi qu'Angrax vient de frapper). Fabrique native = la GENERIQUE
    # `UntilOfEndTurnEffect`, dont le SEUL contenu est
    # `CreateRemoveEffectTrigger = On(0x17 = TurnEnd, ownerNeedsToBeAlive: false)` -- aucun predicat.
    # SANS cette entree le marqueur serait PERMANENT (`DefaultAmountOfRounds(1175)` = Nullable vide,
    # `AddEffect` avec `turns` vide) et HatefulAssault cesserait a jamais de frapper une unite deja
    # touchee une fois : regression PERMISSIVE-INVERSE et SILENCIEUSE. Cf. loki/until_of_end_turn.py.
    HATEFUL_ASSAULT_ALREADY_ATTACKED: [HatefulAssaultAlreadyAttackedRemove],   # 1175 -> retrait On(0x17)
    # 1035 TeleportStrike_TeleportingIn (#448-r2 tranche 1/4) : les QUATRE `Triggered()` d'
    # `IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal`,
    # partages par les trois soeurs (1140 Stormboyz, 1238 FearOfTheUnseen, 1573 TitanhammerSquad ;
    # 1238 est inscrite plus bas par #448-r2c). Les TROIS retraits font l'ATTERRISSAGE deep-strike (l'unite
    # redevient ciblable, reprend un pathfinder normal et initialise ses passives deferrees) ; le
    # QUATRIEME pose le marqueur transitoire `1036 TeleportStrike_Moving` pendant le pas.
    # Avant #448-r2 le port faisait atterrir toutes les unites du joueur finissant dans
    # `EndTurnOperation` : le natif, LUI, retire l'effet des le `On(4 = UnitAfterMove)` du
    # deplacement ou le `On(0x2a = PreUnitAbility)` du cast (mesure live). Cf. loki/teleporting_in.py.
    TELEPORT_STRIKE_TELEPORTING_IN: [TeleportStrikeTeleportingInRemoveOnAfterMove,          # On(4 = UnitAfterMove)
                                     TeleportStrikeTeleportingInRemoveOnPreUnitAbility,     # On(0x2a = PreUnitAbility)
                                     TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn,   # On(0x28 = UnitFinishedTurn)
                                     TeleportStrikeTeleportingInAddMovingOnPreMove],        # On(0x1f)
    # 1036 TeleportStrike_Moving : `IdunBattleLogic.Effects.TeleportMovingEffect$$
    # CreateHandleTriggerAbilitiesInternal` = UN SEUL `Triggered(On(4) & OwnerIsActor,
    # RemoveEffect(EffectSelf))`. Sans cette entree le marqueur pose par T4 survivrait au pas et
    # `set_moved_flag` poserait `UnitFlag.Teleported` sur un deplacement ordinaire.
    TELEPORT_STRIKE_MOVING: [TeleportStrikeMovingRemoveOnAfterMove],           # 1036 -> retrait On(4)
    # 1238 FearOfTheUnseen_TeleportingIn (#448-r2c, tranche 2/4) -- MEME `ArraySet` natif que 1035,
    # mais la SEULE des quatre soeurs a surcharger le vslot 0x738, et la surcharge n'est PAS le
    # conjonct neutre : `IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_TeleportingInEffect$$
    # GetAdditionalRemoveTriggers` = `AmountIsEqual(EffectRemainingTurns(EffectSelf), Direct(1))`.
    # Ce vslot conditionne les QUATRE `Triggered()` (T4 compris), donc rien ne fire tant qu'il reste
    # plus d'un tour a l'effet -- pose a 3 par `FearOfTheUnseenAbility$$ExecuteBehaviour`
    # (`Sum(TurnsFromRounds(1), Direct(1))`, 2 joueurs), il SURVIT au `FinishUnitTurn` qui suit son
    # propre cast puis a tout le tour adverse. Collapser le vslot a `True` ferait disparaitre le
    # Deep Strike du Deathleaper immediatement apres son cast. Cf. loki/teleporting_in.py.
    FEAR_OF_THE_UNSEEN_TELEPORTING_IN: [
        FearOfTheUnseenTeleportingInRemoveOnAfterMove,          # T1 On(4)
        FearOfTheUnseenTeleportingInRemoveOnPreUnitAbility,     # T2 On(0x2a = PreUnitAbility)
        FearOfTheUnseenTeleportingInRemoveOnUnitFinishedTurn,   # T3 On(0x28 = UnitFinishedTurn) & HasTile
        FearOfTheUnseenTeleportingInAddMovingOnPreMove],        # T4 On(0x1f) -> AddEffect(1241)
    # 1241 FearOfTheUnseen_Moving : DEUXIEME des trois `EffectType` que la fabrique native construit
    # par `IdunBattleLogic.Effects.TeleportMovingEffect` -- meme `Triggered` unique que 1036.
    FEAR_OF_THE_UNSEEN_MOVING: [FearOfTheUnseenMovingRemoveOnAfterMove],       # 1241 -> retrait On(4)
    # 1140 StormboyzStrike_TeleportingIn (#448-r2b) : les MEMES quatre `Triggered()` de
    # la base `ATeleportingEffect`, avec DEUX particularites, toutes deux MESUREES :
    #   * `GetMovingEffectType` (vslot 0x758) est bien SURCHARGE (`resolveMethodPtr` le trouve a la
    #     profondeur 0) mais son corps est `xor eax, eax ; ret` -> `Nullable` VIDE -> T4 prend la
    #     branche `Nothing()`. C'est le SEUL des quatre sans `*_Moving` -- et il n'y a AUCUN
    #     `StormboyzStrike_Moving` dans l'`EffectType` du build. AUCUNE entree `*_Moving` ici, donc.
    #   * le porteur est HORS PLATEAU sous 1140 (`StormboyzStrike_TeleportAbility$$CreateBehaviour`
    #     appelle `RemoveUnitFromItsTiles`) : `HasTile(Owner)` est FAUX, T3 NE FIRE PAS et l'effet
    #     SURVIT a la fin du tour. Un port qui oublierait le gate le retirerait -- c'est le seul
    #     regime de la famille qui l'exerce. Cf. loki/teleporting_in.py et
    #     docs/rl/case-448-r2b-stormboyz-teleporting-in.md.
    STORMBOYZ_STRIKE_TELEPORTING_IN: [StormboyzStrikeTeleportingInRemoveOnAfterMove,          # On(4)
                                      StormboyzStrikeTeleportingInRemoveOnPreUnitAbility,     # On(0x2a)
                                      StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn,   # On(0x28 = UnitFinishedTurn)
                                      StormboyzStrikeTeleportingInAddMovingOnPreMove],        # On(0x1f = PreUnitMove)
    # 1573 TitanhammerSquad_TeleportingIn (#448-r2d, tranche 4/4) : MEMES quatre `Triggered()`, mais
    # c'est le SEUL des quatre effets de la famille a surcharger le vslot 0x748
    # (`GetCustomMovingEffectCondition`) -- `Contains(<TargetTiles>, tgt) | IsAdjacentTiles(
    # <TargetTiles>, tgt)` ou `tgt = EffectTarget(EffectsFromUnitSource(EffectSource(EffectSelf),
    # 0x623 = 1571 TitanhammerSquad_TargetTile))`. Le marqueur `1574 *_Moving` n'est donc pose que si
    # la DESTINATION du pas EST une tuile marquee 1571 ou lui est adjacente.
    # ⚠ `1571` est pose par l'ACTIVE `1231`, **NON PORTEE** : sur un etat que le port a construit
    # seul, ce conjoint est FAUX partout (entree vide). Il n'est exerce que sur un etat re-seede
    # depuis le natif apres un cast reel (`probe_448_r2d_titanhammer_squad.py`).
    TITANHAMMER_SQUAD_TELEPORTING_IN: [
        TitanhammerSquadTeleportingInRemoveOnAfterMove,          # On(4 = UnitAfterMove)
        TitanhammerSquadTeleportingInRemoveOnPreUnitAbility,     # On(0x2a = PreUnitAbility)
        TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn,   # On(0x28 = UnitFinishedTurn)
        TitanhammerSquadTeleportingInAddMovingOnPreMove],        # On(0x1f = PreUnitMove)
    # 1574 TitanhammerSquad_Moving : meme `TeleportMovingEffect` que 1036 -- UN SEUL `Triggered(
    # On(4 = UnitAfterMove) & OwnerIsActor, RemoveEffect(EffectSelf))`.
    TITANHAMMER_SQUAD_MOVING: [TitanhammerSquadMovingRemoveOnAfterMove],       # 1574 -> retrait On(4 = UnitAfterMove)
    # 1098 RammingSpeed_ExtraExplode (case-389-r1, pose sur le CASTER par `RammingSpeedAbility$$
    # ExecuteBehaviour`). Le natif le POSE et le RETIRE dans le MEME `applyAction` : son
    # `CreateTargetTrigger` est `On(0x3a = PhaseEnd, ownerNeedsToBeAlive: false)` -- un `On(...)` NU --
    # et son `CreateTargetTriggerBehaviour` est `BaseEffect$$GetRemoveEffectBehaviour` =
    # `RemoveEffect(Effect@0x38)`. La borne `PhaseEnd` est la cloture du message top-level
    # (`InputMessageProcessor$$RunPhase(..., isInternalPhase: false)` -> `OperationProcessor$$EndPhase`
    # -> `EndPhaseOperation$$Execute`), portee par `dispatch/phase.py` en sortie de `Runner.apply`.
    # SANS cette entree l'effet est PERMANENT (options `AddEffect` ZERO -> `remaining = 0`) et le
    # porteur garderait A VIE le `+extraDmgPct` de sa nova `Explodes` -- regression SILENCIEUSE, et
    # INERTE sur tout scenario ou 1098 n'est lu que PENDANT le cast. Cf. loki/ramming_speed.py.
    RAMMING_SPEED_EXTRA_EXPLODE: [RammingSpeedExtraExplodeRemove],             # 1098 -> retrait On(0x3a = PhaseEnd)
    # 1227 HarlequinsPanoply_IgnoreHits (#366-r1) : la classe d'effet ne surcharge QUE
    # `$$CreateTargetTrigger` -- pour un `BaseEffect` c'est le trigger de RETRAIT
    # (`CreateHandleTriggerAbilities` -> `Triggered(<trigger>, RemoveEffect(Effect@0x38))`), ici
    # `On(9 = Attack) & get_OwnerIsTarget` = la CLOTURE de l'attaque qui visait le porteur. Les deux
    # AUTRES faces du cluster (pose on-block, discard per-coup) ne peuvent PAS passer par ce registre :
    # elles sont per-COUP alors que le bus du port emet `On(6)`/`On(0x3c = UnitBlocked)` une fois par attaque ->
    # elles sont appelees par l'intercepteur de `_run_hits` (cf. loki/harlequins_panoply.py).
    HARLEQUINS_PANOPLY_IGNORE_HITS: [HarlequinsPanoplyIgnoreHitsRemove],       # 1227 -> retrait On(9)
    # EarlyWarningOverride_ReactivateOverwatch (#114 residu 3, effet 1145 pose par l'active 1077 de
    # tauCrisis) : `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal` rend un ArraySet
    # de DEUX `Triggered()` -> DEUX classes. (1) `On(1=PreUnitDeath) & OwnerIsActor & NOT IsTurnOf(owner)
    # & AmountIsGreater(Max(Ranged,Melee AttackHits), hitsReduction) & LegitDeathReasons` ->
    # `ActivateEffect(1009) & AddStaticStatModifierEffect(1146, EXTRA_HITS, -hitsReduction,
    # TurnsUntilUnitOwnerTurn)` ; (2) `(On(0)|On(0x11)) & NOT HasEffect(owner,1009,onlyActive)` ->
    # `RemoveEffect(1146)`. Cf. loki/reactivate_overwatch.py.
    EWO_REACTIVATE_OVERWATCH: [EarlyWarningOverrideReactivateOverwatch,   # 1145 -> re-entree + -1 coup
                               EarlyWarningOverrideHitReductionPurge],   # 1145 -> purge du 1146
    # #924 -- `InescapableDeathEffect` (1018), passif `InescapableDeath` de `necroDestroyer`. MEME
    # base native `AReactivateOverwatchEffect`, donc les MEMES deux `Triggered()`. Les deux points
    # de variation sont lus au decompile, pas recopies du voisin : `GetHitReductionEffectType` =
    # 0x3fb (1019, pas 1146), et `LegitDeathReasons` n'est PAS surcharge ici (la classe n'a que 4
    # entrees `methodPointers`, aucune sur ce slot) -> UN seul terme la ou 1145 en a deux.
    INESCAPABLE_DEATH_EFFECT: [InescapableDeathReactivateOverwatch,       # 1018 -> re-entree + -1 coup
                               InescapableDeathHitReductionPurge],       # 1018 -> purge du 1019
    # `GhostEffect` -- le time-ghost, effet dont le PORTEUR est une TUILE. UNE SEULE classe native
    # (0 sous-classe, `classes.tsv` re-derive) mais DEUX effectTypes, donc deux entrees ICI :
    # 1186 `TimeFlux_Revive` (`thousTerminator`, #213) et 1284 `EchoesFromTheWarp_Revive`
    # (`thousNpc4Terminator`, #366-r1). SIX entrees chacune : le `CreateTargetTrigger` /
    # `CreateTargetTriggerBehaviour` (la resurrection NON in-place,
    # `OnPreDeath(ignoreOverkill=1) & AreEqual(EffectSource, target)`) + les CINQ `Triggered()` de
    # son `CreateHandleTriggerAbilitiesInternal` = la « condition de disparition » de l'i2.
    # Le FORK d'amount (`Direct(ConfigVar('hp'))` vs `StatAmount(src, Health, Initial)`) est resolu
    # ICI, a l'enregistrement -- mirror du natif, qui le resout A LA CONSTRUCTION de l'arbre en
    # comparant le `TriggeredAbilityType` poseur a `0x485 = 1157 TimeFlux`.
    # Cf. loki/ghost_revive.py pour les arbres in extenso.
    TIME_FLUX_GHOST_EFFECT: [TimeFluxGhostEffectRevive,          # On(1)    -> Revive(tiles=Owner) + RemoveEffect
                             TimeFluxGhostRemoveOnSourceMoves,   # On(0x1f) -> le poseur rebouge
                             TimeFluxGhostRemoveOnUnitAdded,     # On(0x32 = UnitAdded) -> une autre unite APPARAIT dessus
                             TimeFluxGhostRemoveOnUnitEnters,    # On(0x24) -> une autre unite ARRIVE dessus
                             TimeFluxGhostRemoveOnSourceDeathInactive,  # On(0)    -> poseur mort, effet INACTIF
                             TimeFluxGhostRemoveOnSourceRemoved],       # On(0x25) -> poseur retire du plateau
    ECHOES_GHOST_EFFECT: [EchoesFromTheWarpGhostEffectRevive,    # On(1)    -> Revive(Full Health, tiles=Owner)
                          EchoesGhostRemoveOnSourceMoves,        # On(0x1f)
                          EchoesGhostRemoveOnUnitAdded,          # On(0x32 = UnitAdded)
                          EchoesGhostRemoveOnUnitEnters,         # On(0x24)
                          EchoesGhostRemoveOnSourceDeathInactive,  # On(0)
                          EchoesGhostRemoveOnSourceRemoved],       # On(0x25)
}

# ------------------------------------------------------------------------------------------------
# Le RETRAIT herite d'`IdunBattle.Entities.Effects.ABondEffect` (#462-r4b-r1-r1-r1-r1).
#
# Ces entrees ne sont PAS ecrites a la main : elles se DERIVENT de `BOND_REMOVAL_GATES`, la table
# des trois virtuels de la classe d'effet NATIVE, mesuree au runtime
# (`probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared`). C'est le mirror du natif, ou le
# `Triggered()` est construit par la BASE `ABondEffect$$CreateHandleTriggerAbilitiesInternal` pour
# TOUTES ses derivees -- une seule classe de trigger, N effect_type -- et n'entre dans l'`ArraySet`
# que si son virtuel est arme.
#
# Un `setdefault(...).append(...)` plutot qu'une entree litterale : `EFFECT_TRIGGERS` est MUTE
# in-place et non rebinde (cf. l'en-tete du module), et un effet de bond peut deja porter ses
# propres triggers -- `NEUROPARASITE_EFFECT` en a deux (la montee en niveau de #556), auxquels
# celui-ci s'AJOUTE, exactement comme le natif AJOUTE les siens a l'`ArraySet` herite.
# Un MEME effect_type peut aussi entrer DEUX fois : `Taunted_OnlySpecificTargets` arme (a) ET (b),
# et le natif ajoute alors bien DEUX `Triggered()` distincts a l'`ArraySet` (#462-r4b-r1-r1-r1-r1-b).
#
# Le trigger (c) `<+0x738> get_Adjacent` est PORTE depuis que le port pose 1091 `HolyDuel_Taunt` --
# le SEUL effet de toute la famille a l'armer, et l'ability 1050 qui le pose est desormais dans
# `ABILITY_CLASSES`. 1091 entre donc lui aussi DEUX fois (gates (a) et (c)). Cf. `bond_removal.py` §5.
for _bond_et, _bond_cls in bond_removal_registry_entries():
    EFFECT_TRIGGERS.setdefault(_bond_et, []).append(_bond_cls)


# #513 -- l'ATTAQUE DIFFEREE d'`IdunBattle.Entities.Effects.APendingAttackEffect`, un QUATRIEME
# `Triggered()` qui s'AJOUTE aux trois retraits de bond ci-dessus, exactement comme le natif ajoute
# le sien a l'`ArraySet` que lui rend `ABondEffect$$CreateHandleTriggerAbilitiesInternal`.
# `SeekerMissileFrequencyLock_Target` (1123) porte donc DEUX entrees ici : ce retrait-la (le gate (a)
# n'est PAS arme sur la famille -- `get_RemoveOnBondedEntityDeath` y vaut `NOT IsExecutedIfOwnerDies`)
# et cette attaque. Cf. `pending_attack.py` pour la table et son critere d'inscription.
for _pend_et, _pend_cls in pending_attack_registry_entries():
    EFFECT_TRIGGERS.setdefault(_pend_et, []).append(_pend_cls)


# #889 -- le SECOND `Triggered()` de `TheLionsWrath_PendingAttackEffect` (1521), celui de la
# DERIVEE et non de la base : `On(0x25 = UnitRemoved) & get_OwnerIsTarget -> GetAttackBehaviour`.
# 1521 porte donc DEUX entrees ici (celle de la base, derivee ci-dessus, et celle-ci), exactement
# comme le natif ajoute son `Triggered()` a l'`ArraySet` que lui rend
# `APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal`. Cf. `loki/lions_wrath_attack.py`.
EFFECT_TRIGGERS.setdefault(_lions_wrath_attack.LW_PENDING_ATTACK, []).append(
    _lions_wrath_attack.LionsWrathPendingAttackOnUnitRemoved)
