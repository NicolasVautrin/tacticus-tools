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
                          porteur != source -> scaling resolu contre la SOURCE)."""
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
                               VexillaMagnificaDmgReductionEffect, MarkerlightEffect,
                               ExemplarOfHateTargetEffect, SuperchargeExtraPiercingEffect)
from .hits import (SquigHoundAdditionalHitsEffect, CordClawAdditionalHitsEffect,
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
                   AstartesBannerExtraHitEffect, PowerTripFullHealthEffect, PowerTripIgnoreArmorEffect,
                   KanOpenerEffect, LIGHT_COVER_TILE_ID)
from .status import (HypersensoryMinimalHealthEffect, ContaminatedEffect, ContaminatedUnitEffect,
                     StandVigilExtraArmorEffect,
                     BlessingsOfKhorneModifiersEffect, StunnedEffect, StunnedDamageModifierEffect,
                     ActOfFaithBuffEffect, ThrillSeekersEffect, TauntedEffect, PinnedEffect,
                     MV71InitialDmgEffect, MV71ResetInitialDmgEffect, MasterOfTheTutelariesEffect,
                     BlackRageExtraMoveEffect, BlackRageExtraDamageEffect, BlackRageAutomaticUnitEffect,
                     WaaaghExtraMovementEffect, WaaaghExtraDamageEffect, WaaaghExtraHitsEffect)
from .imperative import ProtectorImperativeEffect, ConquerorImperativeEffect
from .ability_modifications import ListenUpMaggotsEffect
from .votann import (AugmentedAssaultReduceArmorEffect, AncestralFortuneExtraCritChanceEffect,
                     AncestralFortuneExtraBlockChanceEffect, GravitonRifleExtraPierceEffect)
from .darkangels import HailstrikeExtraPierceEffect

__all__ = [
    # extra_damage (volet DIRECT)
    "RapidAssaultExtraDamageEffect", "PrioritisedEfficiencyExtraDmgEffect",
    "SmashaEadExtraDamageEffect", "FeederTendrilsExtraDamageEffect",
    "AvalancheOfMuscleExtraDamageEffect",
    "DecoysAndMisdirectionExtraDamageEffect", "LordOfTempestsExtraDamageEffect",
    "CrushingStrikeEffect", "HeavyWeaponExtraDmgEffect", "RangedSpecialistEffect",
    "BeastSlayerExtraDmgEffect", "MartialKatahDmgBonusEffect", "CondemnorStakeExtraDmgEffect",
    "BeaconOfRageExtraDamageEffect", "TerrifyingCrescendoExtraDmgEffect",
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
    "VexillaMagnificaDmgReductionEffect",
    "MarkerlightEffect", "ExemplarOfHateTargetEffect", "SuperchargeExtraPiercingEffect",
    # hits
    "SquigHoundAdditionalHitsEffect", "CordClawAdditionalHitsEffect",
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
    "PowerTripFullHealthEffect", "PowerTripIgnoreArmorEffect", "KanOpenerEffect", "LIGHT_COVER_TILE_ID",
    # status
    "HypersensoryMinimalHealthEffect", "ContaminatedEffect", "ContaminatedUnitEffect",
    "StandVigilExtraArmorEffect",
    "BlessingsOfKhorneModifiersEffect", "StunnedEffect", "StunnedDamageModifierEffect",
    "ActOfFaithBuffEffect", "ThrillSeekersEffect", "TauntedEffect", "PinnedEffect",
    "MV71InitialDmgEffect", "MV71ResetInitialDmgEffect", "MasterOfTheTutelariesEffect",
    "BlackRageExtraMoveEffect", "BlackRageExtraDamageEffect", "BlackRageAutomaticUnitEffect",
    "WaaaghExtraMovementEffect", "WaaaghExtraDamageEffect", "WaaaghExtraHitsEffect",
    # imperative
    "ProtectorImperativeEffect", "ConquerorImperativeEffect",
    # ability_modifications (ecriture dans `ActiveAbilityModificationsComponent`)
    "ListenUpMaggotsEffect",
    # votann (#113)
    "AugmentedAssaultReduceArmorEffect", "AncestralFortuneExtraCritChanceEffect",
    "AncestralFortuneExtraBlockChanceEffect", "GravitonRifleExtraPierceEffect",
    # darkangels (case-117 phase 2)
    "HailstrikeExtraPierceEffect",
]
