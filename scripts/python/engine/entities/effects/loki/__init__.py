"""Package `loki` — effets du namespace natif `IdunBattle.Entities.Effects.Loki` (+ `Effects.Idun`,
`Effects.Triggered.Loki`), **regroupés par FAMILLE DE HOOK de pipeline** (une classe va dans le fichier de
son hook primaire ; ses hooks secondaires voyagent avec elle). Découpé depuis l'ancien monolithe `loki.py`
(1447 l, 44 classes). Chaque classe override UNIQUEMENT ce qu'elle implémente dans le natif (lu en ghidra).

Ce `__init__` re-exporte la SURFACE PUBLIQUE COMPLETE (les 44 effets + `LIGHT_COVER_TILE_ID`) → tous les
imports externes (`from .loki import X` dans `factory.py`/`effects/__init__.py`, `from ...entities.effects.loki
import LIGHT_COVER_TILE_ID` dans `operations/damage.py`) restent INCHANGES.

- `extra_damage.py`      — bonus de dégât ATTAQUANT, volet DIRECT (l'effet buffe l'attaque de son porteur).
- `extra_damage_aura.py` — même famille, volet AURA (effet sur le SOURCE + `CreateTargetSelector` natif →
                           hooks `create_aura_*`, réévalués PAR CANDIDAT).
- `damage_reduction.py` — malus de dégât DÉFENSEUR (`create_effect_damage_malus_for_defense` + auras réduc).
- `hits.py`             — coups / blocs / pénétration-armure (hits/block/armor-pen).
- `status.py`           — stat-mods, composites (Stunned/Taunted), HP-floor, modificateurs multi-axes.
- `imperative.py`       — DoctrinaImperatives (Tan Gi'da) : Protector (+FixedArmor) / Conqueror (+dmg gate).
- `votann.py`           — Leagues of Votann (#113) : les 3 `DynamicStatModifierEffect` GÉNÉRIQUES du lot
                          (armure −, crit +, block +) + le canal PERÇAGE `GravitonRifle_ExtraPierce`.
- `darkangels.py`       — Dark Angels (case-117 phase 2) : canal PERÇAGE `Hailstrike_ExtraPierce` (1509,
                          porteur != source -> scaling resolu contre la SOURCE).
- `dark_angels_passives.py` — passifs `LionHelm` (1163, darkaAzrael : aura +dmg overwatch + aura
                          stat-mod block) et `FearedInterrogator` (1235, darkaAsmodai : marqueur de
                          cible + bonus degat/coups).
- `visions_of_heresy.py` — canal PERCAGE par STAT (`EXTRA_PIERCE_MELEE` 21 / `EXTRA_PIERCE_RANGED` 22)
                          conditionne aux PV : `VisionsOfHeresy_ExtraPierce{Melee,Ranged}` (1345/1346,
                          `bloodDeathCompany`). UNE classe native, deux `EffectType` (case-366-r1).
- `war_howl.py`         — buff d'ACTIVE a duree 1 tour de `spaceBlackmane` : `WarHowl_ExtraDamage_
                          Unstoppable` (1222), +extraDmg ET +extraCritChance sur la NORMALE MELEE
                          du porteur, + trait `Unstoppable` (case-366-r1).
- `inescapable_accuracy.py` — passif d'`eldarMauganRa` : `InescapableAccuracy_extraCritChance`
                          (1115) et `InescapableAccuracy_extraCritDmg` (1116), +extraCritChance /
                          +extraCritDmg sur les attaques A DISTANCE tant que le porteur n'a pas
                          bouge (case-366-r1). Canaux DIFFERENTS (RollCritical vs
                          CalculateCriticalDamage), gate PARTAGE.
- `until_of_end_turn.py` — `UntilOfEndTurnEffect` : LE marqueur a duree du natif (aucune contribution ;
                          sa seule semantique est `CreateRemoveEffectTrigger` = `On(TurnEnd)`).
- `structural_analyser.py` — volet PORTEUR du passif de `tauDarkstrider` :
                          `StructuralAnalyser_Visual` (1174), cible Owner, ZERO contribution,
                          ACTIF tant qu'un allie est adjacent (toute faction) ou T'au a <= 2 hexes
                          (case-366-r1). SOEUR de `1156` (non porte), pas sa fille.
- `crit_aura.py`        — auras stat-mod dont le `StatType` ecrit chez la cible est le CRIT
                          (`PathOfCommand_ExtraCrit` 1107, eldarAutarch). Meme interface
                          `aura_stat_modification_*` que le volet block de LionHelm."""
from __future__ import annotations

from .extra_damage import (RapidAssaultExtraDamageEffect, PrioritisedEfficiencyExtraDmgEffect,
                           SmashaEadExtraDamageEffect,
                           FeederTendrilsExtraDamageEffect, AvalancheOfMuscleExtraDamageEffect,
                           DecoysAndMisdirectionExtraDamageEffect,
                           LordOfTempestsExtraDamageEffect,
                           CrushingStrikeEffect, HeavyWeaponExtraDmgEffect, RangedSpecialistEffect,
                           BeastSlayerExtraDmgEffect, MartialKatahDmgBonusEffect,
                           CondemnorStakeExtraDmgEffect,
                           BeaconOfRageExtraDamageEffect,
                           TerrifyingCrescendoExtraDmgEffect,
                           FuelledByFuryExtraDamageEffect,
                           ModifiedExoarmourExtraDmgEffect,
                           HeavyGravCannonEffect)
from .extra_damage_aura import (RitesOfBattleExtraDmgEffect, PathOfCommandExtraDmgEffect,
                                APsychicStalkEffect, PsychicStalkExtraAttackDamageEffect,
                                DaughterOfTheAbyssExtraDamagePctEffect,
                                BeaconOfRageFriendlyExtraDamageEffect,
                                LordOfTheHostExtraDamageEffect, DoomExtraDmgEffect,
                                SpotterReworkedExtraDamageEffect, SpotterReworkedHeavyWeaponEffect,
                                DefenderOfTheGreaterGoodExtraDmgEffect,
                                DefenderOfTheGreaterGoodExtraDmgDroneEffect)
from .counter_attack import WireweaveNetCounterAttackEffect
from .damage_reduction import (TerrifyingExtraDefenseEffect, MartialKatahDmgReductionEffect,
                               PrioritisedEfficiencyDmgReductionEffect,
                               TerminatorArmourReduceDmgEffect, GuardianOrganismDamageReductionEffect,
                               NightshroudDmgReductionEffect, NeuroparasiteEffect,
                               FightingRetreatDmgReductionEffect, ShadowInTheWarpLessDmgEffect,
                               DaughterOfTheAbyssFriendlyDmgReductionPctEffect,
                               DaughterOfTheAbyssOwnerDmgReductionEffect,
                               OverwhelmingWrathRangeDmgReductionEffect,
                               FireAndRepositionReduceDmgEffect,
                               PsychicFortressDmgReductionEffect,
                               CamoCloakDmgReductionEffect,
                               SereneUnifierSenseOfStoneEffect,
                               VexillaMagnificaDmgReductionEffect, MarkerlightEffect,
                               ExemplarOfHateTargetEffect, ChronometronExtraDamageEffect,
                               SuperchargeExtraPiercingEffect)
from .hits import (SquigHoundAdditionalHitsEffect, CordClawAdditionalHitsEffect,
                   SorcerousFacadeAdditionalHitsEffect,
                   FearOfTheUnseenExtraDamageEffect,
                   FoulInfusionExtraHitsEffect, CyclicIonBlasterAdditionalHitsEffect,
                   ExemplarOfTheKauyonAdditionalHitsEffect,
                   FleshmetalGunsFocusedMaliceEffect, FleshmetalGunsRuinousSalvoEffect,
                   FleshmetalGunsWarpHailEffect,
                   Swarm_HitReductionEffect,
                   ExplosiveMaladiesExtraRangedAttackEffect,
                   ExplosiveMaladiesExtraMeleeAttackEffect,
                   InfernalPactsAdditionalHitsEffect,
                   AnvilShieldAdditionalBlockEffect,
                   AnvilShieldBlockChanceBelowHealthCapEffect,
                   AnvilShieldFrozenAttackerAdvantageEffect,
                   BeastSlayerExtraBlockEffect, DaemonExtraBlockEffect,
                   PsychicFortressExtraBlockEffect,
                   FightingRetreatHitReductionEffect, LightCoverEffect,
                   ParryEffect, DiminutiveHitReductionEffect, CamouflageHitReductionEffect,
                   MasterAnnihilatorAdditionalHitEffect,
                   LetTheGalaxyBurnEffect, LET_THE_GALAXY_BURN_PERSISTENT_KEY,
                   BigTargetAdjacentEffect,
                   AstartesBannerExtraHitEffect, SagaOfTheWarriorBornOwnerEffect,
                   UnstoppableFerocityOwnerEffect,
                   DefenderOfTheGreaterGoodExtraHitsEffect,
                   DefenderOfTheGreaterGoodExtraHitsDroneEffect,
                   PowerTripFullHealthEffect, PowerTripIgnoreArmorEffect,
                   KanOpenerEffect, LIGHT_COVER_TILE_ID)
from .status import (HypersensoryMinimalHealthEffect, ContaminatedEffect, ContaminatedUnitEffect,
                     ContagionsOfNurgleArmorReductionEffect,
                     DespoiledGroundEffect, DespoiledGroundExtraDamagePctEffect,
                     StandVigilExtraArmorEffect,
                     BlessingsOfKhorneModifiersEffect, StunnedEffect, StunnedDamageModifierEffect,
                     ActOfFaithBuffEffect, ThrillSeekersEffect, TauntedEffect, PinnedEffect,
                     MV71InitialDmgEffect, MV71ResetInitialDmgEffect, MasterOfTheTutelariesEffect,
                     BlackRageExtraMoveEffect, BlackRageExtraDamageEffect, BlackRageAutomaticUnitEffect,
                     WaaaghExtraMovementEffect, WaaaghExtraDamageEffect, WaaaghExtraHitsEffect,
                     HammerOfWrathConditionalDamageEffect)
from .destroy_the_witch import (DestroyTheWitchExtraMoveEffect,        # passif templHelbrecht (1091)
                                DestroyTheWitchExtraDamageEffect)
from .cursed_plague_bell import CursedPlagueBellExtraMoveEffect        # aura deathBlightbringer (1071)
from .relentless_march import RelentlessMarchExtraMoveEffect           # passif necroWarden (1004)
from .my_will_be_done_overlord import (                                # passif necroOverlord (1556)
    MyWillBeDoneOverlordExtraDamageEffect)
from .reality_unbound import (RealityUnboundMovementEffect, RealityUnboundRangeEffect,
                              RealityUnboundExtraMaxDamageEffect)
from .serene_unifier import SereneUnifierStormOfFireEffect              # passif tauAunShi (1145), 1171
from .unbreakable_duty import (UnbreakableDutyHealthEffect,             # active templAncient, 1251/1256
                               UnbreakableDutyDamageEffect)
from .imperative import ProtectorImperativeEffect, ConquerorImperativeEffect
from .ability_modifications import ListenUpMaggotsEffect
from .votann import (AugmentedAssaultReduceArmorEffect, AncestralFortuneExtraCritChanceEffect,
                     AncestralFortuneExtraBlockChanceEffect, GravitonRifleExtraPierceEffect)
from .custodes import (MomentShackleExtraBlockChanceEffect, MomentShackleExtraBlockDamageEffect)
from .darkangels import HailstrikeExtraPierceEffect
from .dark_angels_passives import (LionHelmExtraDmgEffect, LionHelmExtraBlockDamageEffect,
                                   LionHelmExtraBlockChanceEffect,
                                   FearedInterrogatorOwnerEffect, FearedInterrogatorTargetEffect)
from .crit_aura import PathOfCommandExtraCritEffect
from .visions_of_heresy import (VisionsOfHeresyExtraPierceMeleeEffect,
                                VisionsOfHeresyExtraPierceRangedEffect)
from .war_howl import WarHowlExtraDamageUnstoppableEffect
from .inescapable_accuracy import (InescapableAccuracyExtraCritChanceEffect,
                                   InescapableAccuracyExtraCritDamageEffect)
from .until_of_end_turn import UntilOfEndTurnEffect
from .structural_analyser import StructuralAnalyserVisualEffect

__all__ = [
    # dark_angels_passives (passifs LionHelm 1163 / FearedInterrogator 1235)
    "LionHelmExtraDmgEffect", "LionHelmExtraBlockDamageEffect", "LionHelmExtraBlockChanceEffect",
    "FearedInterrogatorOwnerEffect", "FearedInterrogatorTargetEffect",
    # crit_aura (aura stat-mod CRIT projetee -- volet CRIT de PathOfCommand 1112)
    "PathOfCommandExtraCritEffect",
    # extra_damage (volet DIRECT)
    "RapidAssaultExtraDamageEffect", "PrioritisedEfficiencyExtraDmgEffect",
    "SmashaEadExtraDamageEffect", "FeederTendrilsExtraDamageEffect",
    "AvalancheOfMuscleExtraDamageEffect",
    "DecoysAndMisdirectionExtraDamageEffect", "LordOfTempestsExtraDamageEffect",
    "CrushingStrikeEffect", "HeavyWeaponExtraDmgEffect", "RangedSpecialistEffect",
    "BeastSlayerExtraDmgEffect", "MartialKatahDmgBonusEffect", "CondemnorStakeExtraDmgEffect",
    "BeaconOfRageExtraDamageEffect", "TerrifyingCrescendoExtraDmgEffect",
    "FuelledByFuryExtraDamageEffect", "ModifiedExoarmourExtraDmgEffect",
    "HeavyGravCannonEffect",
    # extra_damage_aura (volet AURA)
    "RitesOfBattleExtraDmgEffect", "PathOfCommandExtraDmgEffect",
    "APsychicStalkEffect", "PsychicStalkExtraAttackDamageEffect",
    "DaughterOfTheAbyssExtraDamagePctEffect", "BeaconOfRageFriendlyExtraDamageEffect",
    "LordOfTheHostExtraDamageEffect", "DoomExtraDmgEffect",
    "SpotterReworkedExtraDamageEffect", "SpotterReworkedHeavyWeaponEffect",
    "DefenderOfTheGreaterGoodExtraDmgEffect", "DefenderOfTheGreaterGoodExtraDmgDroneEffect",
    # damage_reduction
    "TerrifyingExtraDefenseEffect", "MartialKatahDmgReductionEffect",
    "PrioritisedEfficiencyDmgReductionEffect", "TerminatorArmourReduceDmgEffect",
    "GuardianOrganismDamageReductionEffect", "NightshroudDmgReductionEffect", "NeuroparasiteEffect",
    "FightingRetreatDmgReductionEffect", "ShadowInTheWarpLessDmgEffect",
    "DaughterOfTheAbyssFriendlyDmgReductionPctEffect", "DaughterOfTheAbyssOwnerDmgReductionEffect",
    "OverwhelmingWrathRangeDmgReductionEffect", "FireAndRepositionReduceDmgEffect",
    # counter_attack
    "WireweaveNetCounterAttackEffect",
    "PsychicFortressDmgReductionEffect", "CamoCloakDmgReductionEffect",
    "SereneUnifierSenseOfStoneEffect",
    "VexillaMagnificaDmgReductionEffect",
    "MarkerlightEffect", "ExemplarOfHateTargetEffect", "ChronometronExtraDamageEffect",
    "SuperchargeExtraPiercingEffect",
    # hits
    "SquigHoundAdditionalHitsEffect", "CordClawAdditionalHitsEffect",
    "SorcerousFacadeAdditionalHitsEffect",
    "FearOfTheUnseenExtraDamageEffect",
    "FoulInfusionExtraHitsEffect", "CyclicIonBlasterAdditionalHitsEffect",
    "ExemplarOfTheKauyonAdditionalHitsEffect",
    "FleshmetalGunsFocusedMaliceEffect", "FleshmetalGunsRuinousSalvoEffect",
    "FleshmetalGunsWarpHailEffect",
    "Swarm_HitReductionEffect",
    "ExplosiveMaladiesExtraRangedAttackEffect", "ExplosiveMaladiesExtraMeleeAttackEffect",
    "InfernalPactsAdditionalHitsEffect",
    "AnvilShieldAdditionalBlockEffect", "AnvilShieldBlockChanceBelowHealthCapEffect",
    "AnvilShieldFrozenAttackerAdvantageEffect", "BeastSlayerExtraBlockEffect",
    "DaemonExtraBlockEffect", "PsychicFortressExtraBlockEffect",
    "FightingRetreatHitReductionEffect", "LightCoverEffect", "ParryEffect",
    "CamouflageHitReductionEffect", "DiminutiveHitReductionEffect",
    "MasterAnnihilatorAdditionalHitEffect", "LetTheGalaxyBurnEffect",
    "LET_THE_GALAXY_BURN_PERSISTENT_KEY",
    "BigTargetAdjacentEffect", "AstartesBannerExtraHitEffect",
    "SagaOfTheWarriorBornOwnerEffect", "UnstoppableFerocityOwnerEffect",
    "DefenderOfTheGreaterGoodExtraHitsEffect", "DefenderOfTheGreaterGoodExtraHitsDroneEffect",
    "PowerTripFullHealthEffect", "PowerTripIgnoreArmorEffect", "KanOpenerEffect", "LIGHT_COVER_TILE_ID",
    # status
    "HypersensoryMinimalHealthEffect", "ContaminatedEffect", "ContaminatedUnitEffect",
    "ContagionsOfNurgleArmorReductionEffect",
    "DespoiledGroundEffect", "DespoiledGroundExtraDamagePctEffect",
    "StandVigilExtraArmorEffect",
    "BlessingsOfKhorneModifiersEffect", "StunnedEffect", "StunnedDamageModifierEffect",
    "ActOfFaithBuffEffect", "ThrillSeekersEffect", "TauntedEffect", "PinnedEffect",
    "RealityUnboundMovementEffect", "RealityUnboundRangeEffect", "RealityUnboundExtraMaxDamageEffect",
    # G1 case-371 : instances GENERIQUES `StaticStatModifierEffect` (declarees pour l'attribution
    # par-source du seed, donc le revert exact -- cf. #118).
    "SereneUnifierStormOfFireEffect", "UnbreakableDutyHealthEffect", "UnbreakableDutyDamageEffect",
    "MV71InitialDmgEffect", "MV71ResetInitialDmgEffect", "MasterOfTheTutelariesEffect",
    "BlackRageExtraMoveEffect", "BlackRageExtraDamageEffect", "BlackRageAutomaticUnitEffect",
    "WaaaghExtraMovementEffect", "WaaaghExtraDamageEffect", "WaaaghExtraHitsEffect",
    "HammerOfWrathConditionalDamageEffect",
    # destroy_the_witch (passif templHelbrecht 1091 : +1 MOVEMENT gate Psyker ennemi + aura melee)
    "DestroyTheWitchExtraMoveEffect", "DestroyTheWitchExtraDamageEffect",
    # cursed_plague_bell (aura deathBlightbringer 1071 : +1 MOVEMENT aux amis Chaos, 1 tour)
    "CursedPlagueBellExtraMoveEffect",
    # relentless_march (passif necroWarden 1004 : +1 MOVEMENT aux allies adjacents non-Stationary)
    "RelentlessMarchExtraMoveEffect",
    # my_will_be_done_overlord (passif necroOverlord 1556 : +extraDmg ATTACK self, branche ELSE)
    "MyWillBeDoneOverlordExtraDamageEffect",
    # imperative
    "ProtectorImperativeEffect", "ConquerorImperativeEffect",
    # ability_modifications (ecriture dans `ActiveAbilityModificationsComponent`)
    "ListenUpMaggotsEffect",
    # votann (#113)
    "AugmentedAssaultReduceArmorEffect", "AncestralFortuneExtraCritChanceEffect",
    "AncestralFortuneExtraBlockChanceEffect", "GravitonRifleExtraPierceEffect",
    # custodes (case-231) — les 2 `DynamicStatModifierEffect` generiques de MomentShackle (1184)
    "MomentShackleExtraBlockChanceEffect", "MomentShackleExtraBlockDamageEffect",
    # darkangels (case-117 phase 2)
    "HailstrikeExtraPierceEffect",
    # visions_of_heresy (case-366-r1) -- canal PERCAGE par STAT (21/22), conditionne aux PV
    "VisionsOfHeresyExtraPierceMeleeEffect", "VisionsOfHeresyExtraPierceRangedEffect",
    # war_howl (case-366-r1) -- +extraDmg ET +extraCritChance sur la NORMALE MELEE, 1 tour
    "WarHowlExtraDamageUnstoppableEffect",
    # inescapable_accuracy (case-366-r1) -- +extraCritChance / +extraCritDmg RANGED, MEME gate
    # NOT HasFlag(Moved) (un seul corps natif de `CreateActiveCondition` pour les trois volets)
    "InescapableAccuracyExtraCritChanceEffect",
    "InescapableAccuracyExtraCritDamageEffect",
    # until_of_end_turn (case-366-r1) -- LA classe de MARQUEUR a duree : zero contribution, sa seule
    # semantique est son `CreateRemoveEffectTrigger` = `On(TurnEnd)`. Porteur : 1175.
    "UntilOfEndTurnEffect",
    # structural_analyser (case-366-r1) -- 1174, volet PORTEUR : zero contribution, sa seule
    # semantique est sa `CreateActiveCondition` geometrique.
    "StructuralAnalyserVisualEffect",
]
