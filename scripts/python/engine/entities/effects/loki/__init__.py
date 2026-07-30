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
                          cible + bonus degat/coups)."""
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
                           HeavyGravCannonEffect)
from .extra_damage_aura import (RitesOfBattleExtraDmgEffect, PathOfCommandExtraDmgEffect,
                                DaughterOfTheAbyssExtraDamagePctEffect,
                                BeaconOfRageFriendlyExtraDamageEffect,
                                LordOfTheHostExtraDamageEffect, DoomExtraDmgEffect,
                                SpotterReworkedExtraDamageEffect, SpotterReworkedHeavyWeaponEffect,
                                DefenderOfTheGreaterGoodExtraDmgEffect)
from .damage_reduction import (TerrifyingExtraDefenseEffect, MartialKatahDmgReductionEffect,
                               PrioritisedEfficiencyDmgReductionEffect,
                               TerminatorArmourReduceDmgEffect, GuardianOrganismDamageReductionEffect,
                               NightshroudDmgReductionEffect, NeuroparasiteEffect,
                               FightingRetreatDmgReductionEffect, ShadowInTheWarpLessDmgEffect,
                               DaughterOfTheAbyssFriendlyDmgReductionPctEffect,
                               DaughterOfTheAbyssOwnerDmgReductionEffect,
                               OverwhelmingWrathRangeDmgReductionEffect,
                               PsychicFortressDmgReductionEffect,
                               SereneUnifierSenseOfStoneEffect,
                               VexillaMagnificaDmgReductionEffect, MarkerlightEffect,
                               ExemplarOfHateTargetEffect, ChronometronExtraDamageEffect,
                               SuperchargeExtraPiercingEffect)
from .hits import (SquigHoundAdditionalHitsEffect, CordClawAdditionalHitsEffect,
                   SorcerousFacadeAdditionalHitsEffect,
                   FearOfTheUnseenExtraDamageEffect,
                   FoulInfusionExtraHitsEffect, CyclicIonBlasterAdditionalHitsEffect,
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
from .reality_unbound import (RealityUnboundMovementEffect, RealityUnboundRangeEffect,
                              RealityUnboundExtraMaxDamageEffect)
from .imperative import ProtectorImperativeEffect, ConquerorImperativeEffect
from .ability_modifications import ListenUpMaggotsEffect
from .votann import (AugmentedAssaultReduceArmorEffect, AncestralFortuneExtraCritChanceEffect,
                     AncestralFortuneExtraBlockChanceEffect, GravitonRifleExtraPierceEffect)
from .custodes import (MomentShackleExtraBlockChanceEffect, MomentShackleExtraBlockDamageEffect)
from .darkangels import HailstrikeExtraPierceEffect
from .dark_angels_passives import (LionHelmExtraDmgEffect, LionHelmExtraBlockDamageEffect,
                                   LionHelmExtraBlockChanceEffect,
                                   FearedInterrogatorOwnerEffect, FearedInterrogatorTargetEffect)

__all__ = [
    # dark_angels_passives (passifs LionHelm 1163 / FearedInterrogator 1235)
    "LionHelmExtraDmgEffect", "LionHelmExtraBlockDamageEffect", "LionHelmExtraBlockChanceEffect",
    "FearedInterrogatorOwnerEffect", "FearedInterrogatorTargetEffect",
    # extra_damage (volet DIRECT)
    "RapidAssaultExtraDamageEffect", "PrioritisedEfficiencyExtraDmgEffect",
    "SmashaEadExtraDamageEffect", "FeederTendrilsExtraDamageEffect",
    "AvalancheOfMuscleExtraDamageEffect",
    "DecoysAndMisdirectionExtraDamageEffect", "LordOfTempestsExtraDamageEffect",
    "CrushingStrikeEffect", "HeavyWeaponExtraDmgEffect", "RangedSpecialistEffect",
    "BeastSlayerExtraDmgEffect", "MartialKatahDmgBonusEffect", "CondemnorStakeExtraDmgEffect",
    "BeaconOfRageExtraDamageEffect", "TerrifyingCrescendoExtraDmgEffect",
    "FuelledByFuryExtraDamageEffect",
    "HeavyGravCannonEffect",
    # extra_damage_aura (volet AURA)
    "RitesOfBattleExtraDmgEffect", "PathOfCommandExtraDmgEffect",
    "DaughterOfTheAbyssExtraDamagePctEffect", "BeaconOfRageFriendlyExtraDamageEffect",
    "LordOfTheHostExtraDamageEffect", "DoomExtraDmgEffect",
    "SpotterReworkedExtraDamageEffect", "SpotterReworkedHeavyWeaponEffect",
    "DefenderOfTheGreaterGoodExtraDmgEffect",
    # damage_reduction
    "TerrifyingExtraDefenseEffect", "MartialKatahDmgReductionEffect",
    "PrioritisedEfficiencyDmgReductionEffect", "TerminatorArmourReduceDmgEffect",
    "GuardianOrganismDamageReductionEffect", "NightshroudDmgReductionEffect", "NeuroparasiteEffect",
    "FightingRetreatDmgReductionEffect", "ShadowInTheWarpLessDmgEffect",
    "DaughterOfTheAbyssFriendlyDmgReductionPctEffect", "DaughterOfTheAbyssOwnerDmgReductionEffect",
    "OverwhelmingWrathRangeDmgReductionEffect", "PsychicFortressDmgReductionEffect",
    "SereneUnifierSenseOfStoneEffect",
    "VexillaMagnificaDmgReductionEffect",
    "MarkerlightEffect", "ExemplarOfHateTargetEffect", "ChronometronExtraDamageEffect",
    "SuperchargeExtraPiercingEffect",
    # hits
    "SquigHoundAdditionalHitsEffect", "CordClawAdditionalHitsEffect",
    "SorcerousFacadeAdditionalHitsEffect",
    "FearOfTheUnseenExtraDamageEffect",
    "FoulInfusionExtraHitsEffect", "CyclicIonBlasterAdditionalHitsEffect",
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
    "PowerTripFullHealthEffect", "PowerTripIgnoreArmorEffect", "KanOpenerEffect", "LIGHT_COVER_TILE_ID",
    # status
    "HypersensoryMinimalHealthEffect", "ContaminatedEffect", "ContaminatedUnitEffect",
    "ContagionsOfNurgleArmorReductionEffect",
    "DespoiledGroundEffect", "DespoiledGroundExtraDamagePctEffect",
    "StandVigilExtraArmorEffect",
    "BlessingsOfKhorneModifiersEffect", "StunnedEffect", "StunnedDamageModifierEffect",
    "ActOfFaithBuffEffect", "ThrillSeekersEffect", "TauntedEffect", "PinnedEffect",
    "RealityUnboundMovementEffect", "RealityUnboundRangeEffect", "RealityUnboundExtraMaxDamageEffect",
    "MV71InitialDmgEffect", "MV71ResetInitialDmgEffect", "MasterOfTheTutelariesEffect",
    "BlackRageExtraMoveEffect", "BlackRageExtraDamageEffect", "BlackRageAutomaticUnitEffect",
    "WaaaghExtraMovementEffect", "WaaaghExtraDamageEffect", "WaaaghExtraHitsEffect",
    "HammerOfWrathConditionalDamageEffect",
    # destroy_the_witch (passif templHelbrecht 1091 : +1 MOVEMENT gate Psyker ennemi + aura melee)
    "DestroyTheWitchExtraMoveEffect", "DestroyTheWitchExtraDamageEffect",
    # cursed_plague_bell (aura deathBlightbringer 1071 : +1 MOVEMENT aux amis Chaos, 1 tour)
    "CursedPlagueBellExtraMoveEffect",
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
]
