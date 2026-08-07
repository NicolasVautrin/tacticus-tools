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
                              OVERWATCH_AUTO_ATTACK, CONTAMINATED_TILE)
from ..genestealer import (DecoysAndMisdirectionDamageEnemiesAbility,
                          DecoysAndMisdirectionBuffFriendsAbility,
                          AmbushSummonAbility, EnvAmbushResurrectAbility,
                          HypersensoryMoveAndSpawnDecoyAbility)
from ..loki.weaver_of_fate import WeaverOfFateAbility                 # #202-A (trait WeaverOfFate)
from ..loki.reality_unbound import (RealityUnboundAbility,            # passif thousTzaangor (2 volets)
                                   RealityUnboundExtraMaxDamageAbility)
from ..loki.time_flux import TimeFluxRegenAbility                     # passif thousTerminator (volet regen)
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
from ..loki.destroyer_hive import DestroyerHiveAbility               # case-220 DG (passiveAbility deathTyphus)
from ..loki.cursed_plague_bell import (CursedPlagueBellMovementAbility,   # #224 DG (passif deathBlightbringer)
                                      CursedPlagueBellAttackAbility)     # #224 item 5 (volet ATTAQUE)
from ..loki.martial_apotheosis import MartialApotheosisAttackAbility  # case-220 (passif necroOverlord, Necron)
from ..loki.martial_superiority import MartialSuperiorityRiposteAbility  # #133 (passif templChampion)
from ..loki.wireweave_net import (WireweaveNetCounterAttack,          # #366-r1b (passif eldarRanger)
                                  WireweaveNetActivateOnOwnerTurnEnd,
                                  WireweaveNetDeactivateOnOwnerTurnStart,
                                  WIREWEAVE_NET_COUNTER_ATTACK)
from ..loki.master_of_the_tutelaries import (MasterOfTheTutelariesSummonAbility,   # #202-C (triggered 1173)
                                            MASTER_EFFECT as MASTEROFTUTELARIES_EFFECT)
from ..loki.tainted_narthecium import TaintedNartheciumReviveAbility  # case-66 (passif deathRotbone, revive)
from ..loki.narthecium import NartheciumReviveAbility                 # #79 (passif ultraApothecary, revive)
from ..loki.rites_of_morkai import (RitesOfMorkaiReviveTrigger,       # #79 (effet 1502 pose par Baldr)
                                   RITES_OF_MORKAI_EFFECT)
from ..loki.reanimation_beam import (ReanimationBeamReviveTrigger,    # #79 (effet 1547, MoW necroReanimator)
                                    REANIMATION_BEAM_EFFECT)
from ..loki.phoenix_gem import (PhoenixGemReviveAbility,              # #79 (relic, marqueur 1451)
                               PhoenixGemRemoveMarkerOnRevive,       # #89-B3 (On(0x2d = UnitRevived) -> RemoveEffect)
                               PhoenixGemRemoveMarkerOnResurrect,    # #89-B3 (On(0x2e = UnitResurrected) -> RemoveEffect)
                               PHOENIX_GEM_CAN_REVIVE)
from ..loki.legendary_commander import (                             # #419-r1-tr9-r4-r1-r2-r1
    LegendaryCommanderExtraHitsMarkCaster, LEGENDARY_COMMANDER_EXTRA_HITS)
from ..loki.suppressive_fire import SuppressiveFireAddEffectAbility  # #74 (trait SuppressiveFire 1010)
from ..loki.death_nova import ExplodesAbility, PutridExplosionAbility  # death-nova (traits 1008 / 2028)
from ..loki.master_annihilator import MasterAnnihilatorMarkAbility   # lot POSE (passif admecDominus)
from ..loki.fleshmetal_guns import (FleshmetalGunsRotationAbility,   # lot POSE (passif blackObliterator)
                                   FleshmetalGunsTileEffectAbility)  # #85 volet DespoiledGround
from ..loki.despoiled_ground import (DespoiledGroundTileDoT,         # #85 (EnvDespoiledGroundTileAbility)
                                    DESPOILED_GROUND_TILE)
from ..loki.terrifying_crescendo import (TerrifyingCrescendoOverkillAbility,   # lot POSE (passif
                                        TerrifyingCrescendoSuppressAbility)   # emperNoiseMarine, #204)
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
# Import pour EFFET DE BORD : `loki/full_throttle.py` inscrit `TRIGGERED_ABILITY_BEHAVIOURS[1134]`
# a l'import (#448-r1). Sans lui, le `TriggerAbility(Caster, 0x46e)` du Miss rendrait
# `dispatched: False` -- un gap VISIBLE, mais un gap.
from ..loki import full_throttle as _full_throttle    # noqa: F401
from ..loki.thrill_seekers import (ThrillSeekersFullHealthTargetAbility,   # trait ThrillSeekers 1056
                                  ThrillSeekersDamageTakenAbility)        # (x5 Emperor's Children)
from ..loki.hailstrike import HailstrikeAttackAbility                 # case-117 ph.2 (1214 -> 1507)
from ..loki.empyric_ambush import EmpyricAmbushResetAbility           # #589-r1-r1-r1-r1 (1232 -> 1555)
from ..loki.heavy_warp_flamer import (HeavyWarpFlamerAttackTrackingAbility,       # #523-r1
                                      HeavyWarpFlamerAttackTrackingResetAbility)  # (1227 -> 1546)
from ..loki.inspired_to_greatness import (InspiredToGreatnessOverrideLevelRemove,   # #114 residu 2
                                         ITG_OVERRIDE_LEVEL)
from ..loki.chronometron import (ChronometronExtraDamageRemove,                    # residu R9
                                CHRONOMETRON_EXTRA_DAMAGE)
from ..loki.euphoric_strikes import (EuphoricStrikesExtraCritRemove,               # #522 (1198 -> 1429)
                                     EUPHORIC_STRIKES_EXTRA_CRIT)
from ..loki.shock_assault import (ShockAssaultBuffRemove,                          # case-366-r1 (1000)
                                  SHOCK_ASSAULT_BUFF)
from ..loki.hateful_assault import HatefulAssaultAttackAbility            # case-366-r1 (1038 + 1175)
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
                                        EWO_REACTIVATE_OVERWATCH)
from ..loki.cosmic_horror import (CosmicHorrorOnKillAbility,           # passif genesPatriarch (GS Cults)
                                 CosmicHorrorOnMoveAbility)
from ..loki.spiritual_leader import SpiritualLeaderAbility             # passif genesMagus (GS Cults)
from ..loki.barbed_ovipositor import BarbedOvipositorSummonAbility     # passif tyranParasite (Tyranids)
from ..loki.fabricator_claw_array import FabricatorClawArrayAbility    # #303 (passif necroSpyder, N20)
from ..loki.champion_of_the_feast import ChampionOfTheFeastAbility    # #419-r6-r2 (passif templSwordBrother)
from ..loki.dawn_blade import DawnBladeHealAbility                     # #317 (relique tauFarsight)
from ..loki.relentless_march import RelentlessMarchAbility             # #328 (passif necroWarden)
from ..loki.my_will_be_done_overlord import (MyWillBeDoneOverlordAttackAbility,   # #354 (necroOverlord)
                                             MyWillBeDoneOverlordClearAbility)
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


# --- Registre : trait → ability-trigger(s) accordée(s) --------------------------------------------
TRAIT_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    "Psyker": [PsykerExtraAttackAbility],
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
    # l'event `PreUnitDeath_2 = 2` (PAS 1 : `IdunBattleLogic.Entities.DSLFactory$$OnPreDeath2` -> `OnDeathEvent(2,...)`).
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
#   1189 CalibaniteGreatsword  -> 1316 CalibaniteGreatsword_NormalAttackAdditionalDamage (non porte)
#   1195 TalonsOfTheEmperor    -> 1330 TalonsOfTheEmperor_UsedAbilities            <- PORTE (#521-r1)
# Les cinq non portees restent registered-but-unported cote natif : no-op fidele, elles n'ont RIEN a
# faire ici tant que leur classe n'existe pas (une entree vide serait un mensonge de couverture).
PASSIVE_HELPER_ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # 0x4ab (1195 TalonsOfTheEmperor, `custoAtlacoya` HERO) -> 0x532 (1330 TalonsOfTheEmperor_Used
    # Abilities) : a la FERMETURE de toute active d'un allie `Hero` non-`MachineOfWar` qui COMPTE
    # (`IsActiveAbilityCountedAsUsed`, donc PAS l'attaque normale), le porteur incremente de +1, SANS
    # cap, le niveau de l'effet 1420 -- le compteur que lit
    # `...TalonsOfTheEmperorAbility$$GetExtraDamage`. Le trigger porte tous ses gates, donc
    # l'inscription inconditionnelle est fidele. Cf. loki/talons_of_the_emperor.py.
    TOTE_ACTIVE_ID: [TalonsOfTheEmperorUsedAbilitiesAbility],
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
    # PhoenixGem (#79, relic d'eldarAutarch) : PAS un ReviveEffect -- `PhoenixGem_ReviveAbility`
    # (IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour) enregistree par l'effet-marqueur `PhoenixGem_CanReviveEffect` 1451
    # (IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal). Self-revive INCONDITIONNEL (pas de Maybe), **even if Overkilled**, one-shot par
    # bataille. Le `IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` de l'effet enregistre en plus les
    # DEUX triggers de RETRAIT du marqueur (case-89 volet B3) : `On(0x2d=UnitRevived) & OwnerIsTarget &
    # CurrentAbilityIs(PhoenixGem=0x5b2)` et `On(0x2e=UnitResurrected) & OwnerIsTarget`.
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
# Le trigger (c) `<+0x738> get_Adjacent` n'est PAS porte : le seul effet qui l'arme est 1091
# `HolyDuel_Taunt`, que le port ne POSE jamais (l'ability 1050 n'est pas dans `ABILITY_CLASSES`).
# Sa face NATIVE est mesuree malgre tout -- cf. `bond_removal.py` §5.
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
