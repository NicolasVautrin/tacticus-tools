"""Package `loki` — effets du namespace natif `IdunBattle.Entities.Effects.Loki` (+ `Effects.Idun`,
`Effects.Triggered.Loki`), **regroupés par FAMILLE DE HOOK de pipeline** (une classe va dans le fichier de
son hook primaire ; ses hooks secondaires voyagent avec elle). Découpé depuis l'ancien monolithe `loki.py`
(1447 l, 44 classes). Chaque classe override UNIQUEMENT ce qu'elle implémente dans le natif (lu en ghidra).

Ce `__init__` re-exporte la SURFACE PUBLIQUE COMPLETE (les 44 effets + `LIGHT_COVER_TILE_ID`) → tous les
imports externes (`from .loki import X` dans `factory.py`/`effects/__init__.py`, `from ...entities.effects.loki
import LIGHT_COVER_TILE_ID` dans `operations/damage.py`) restent INCHANGES.

- `extra_damage.py`     — bonus de dégât ATTAQUANT (`create_effect_damage_bonus_for_attack` / aura attack).
- `damage_reduction.py` — malus de dégât DÉFENSEUR (`create_effect_damage_malus_for_defense` + auras réduc).
- `hits.py`             — coups / blocs / pénétration-armure (hits/block/armor-pen).
- `status.py`           — stat-mods, composites (Stunned/Taunted), HP-floor, modificateurs multi-axes.
- `imperative.py`       — DoctrinaImperatives (Tan Gi'da) : Protector (+FixedArmor) / Conqueror (+dmg gate)."""
from __future__ import annotations

from .extra_damage import (RapidAssaultExtraDamageEffect, SmashaEadExtraDamageEffect,
                           FeederTendrilsExtraDamageEffect, AvalancheOfMuscleExtraDamageEffect,
                           DecoysAndMisdirectionExtraDamageEffect,
                           LordOfTempestsExtraDamageEffect,
                           RitesOfBattleExtraDmgEffect, PathOfCommandExtraDmgEffect,
                           CrushingStrikeEffect, HeavyWeaponExtraDmgEffect, RangedSpecialistEffect,
                           BeastSlayerExtraDmgEffect, MartialKatahDmgBonusEffect,
                           CondemnorStakeExtraDmgEffect,
                           DaughterOfTheAbyssExtraDamagePctEffect,
                           BeaconOfRageExtraDamageEffect, BeaconOfRageFriendlyExtraDamageEffect,
                           TerrifyingCrescendoExtraDmgEffect,
                           LordOfTheHostExtraDamageEffect, DoomExtraDmgEffect,
                           SpotterReworkedExtraDamageEffect, SpotterReworkedHeavyWeaponEffect,
                           DefenderOfTheGreaterGoodExtraDmgEffect)
from .damage_reduction import (TerrifyingExtraDefenseEffect, MartialKatahDmgReductionEffect,
                               TerminatorArmourReduceDmgEffect, GuardianOrganismDamageReductionEffect,
                               NightshroudDmgReductionEffect, NeuroparasiteEffect,
                               FightingRetreatDmgReductionEffect, ShadowInTheWarpLessDmgEffect,
                               DaughterOfTheAbyssFriendlyDmgReductionPctEffect,
                               DaughterOfTheAbyssOwnerDmgReductionEffect,
                               OverwhelmingWrathRangeDmgReductionEffect,
                               PsychicFortressDmgReductionEffect,
                               VexillaMagnificaDmgReductionEffect, MarkerlightEffect)
from .hits import (SquigHoundAdditionalHitsEffect, CordClawAdditionalHitsEffect,
                   FoulInfusionExtraHitsEffect, CyclicIonBlasterAdditionalHitsEffect,
                   FleshmetalGunsFocusedMaliceEffect, FleshmetalGunsRuinousSalvoEffect,
                   FleshmetalGunsWarpHailEffect,
                   Swarm_HitReductionEffect,
                   ExplosiveMaladiesExtraRangedAttackEffect,
                   ExplosiveMaladiesExtraMeleeAttackEffect,
                   InfernalPactsAdditionalHitsEffect,
                   AnvilShieldAdditionalBlockEffect,
                   BeastSlayerExtraBlockEffect, DaemonExtraBlockEffect,
                   PsychicFortressExtraBlockEffect,
                   FightingRetreatHitReductionEffect, LightCoverEffect,
                   ParryEffect, DiminutiveHitReductionEffect, CamouflageHitReductionEffect,
                   MasterAnnihilatorAdditionalHitEffect,
                   LetTheGalaxyBurnEffect, LET_THE_GALAXY_BURN_PERSISTENT_KEY,
                   BigTargetAdjacentEffect,
                   AstartesBannerExtraHitEffect, PowerTripFullHealthEffect, PowerTripIgnoreArmorEffect,
                   KanOpenerEffect, LIGHT_COVER_TILE_ID)
from .status import (HypersensoryMinimalHealthEffect, ContaminatedUnitEffect, StandVigilExtraArmorEffect,
                     BlessingsOfKhorneModifiersEffect, StunnedEffect, StunnedDamageModifierEffect,
                     ActOfFaithBuffEffect, TauntedEffect, PinnedEffect,
                     MV71InitialDmgEffect, MV71ResetInitialDmgEffect, MasterOfTheTutelariesEffect,
                     BlackRageExtraMoveEffect, BlackRageExtraDamageEffect, BlackRageAutomaticUnitEffect)
from .imperative import ProtectorImperativeEffect, ConquerorImperativeEffect

__all__ = [
    # extra_damage
    "RapidAssaultExtraDamageEffect", "SmashaEadExtraDamageEffect", "FeederTendrilsExtraDamageEffect",
    "AvalancheOfMuscleExtraDamageEffect",
    "DecoysAndMisdirectionExtraDamageEffect", "LordOfTempestsExtraDamageEffect",
    "RitesOfBattleExtraDmgEffect", "PathOfCommandExtraDmgEffect",
    "CrushingStrikeEffect", "HeavyWeaponExtraDmgEffect", "RangedSpecialistEffect",
    "BeastSlayerExtraDmgEffect", "MartialKatahDmgBonusEffect", "CondemnorStakeExtraDmgEffect",
    "DaughterOfTheAbyssExtraDamagePctEffect",
    "BeaconOfRageExtraDamageEffect", "BeaconOfRageFriendlyExtraDamageEffect",
    "TerrifyingCrescendoExtraDmgEffect",
    "LordOfTheHostExtraDamageEffect", "DoomExtraDmgEffect",
    "SpotterReworkedExtraDamageEffect", "SpotterReworkedHeavyWeaponEffect",
    "DefenderOfTheGreaterGoodExtraDmgEffect",
    # damage_reduction
    "TerrifyingExtraDefenseEffect", "MartialKatahDmgReductionEffect", "TerminatorArmourReduceDmgEffect",
    "GuardianOrganismDamageReductionEffect", "NightshroudDmgReductionEffect", "NeuroparasiteEffect",
    "FightingRetreatDmgReductionEffect", "ShadowInTheWarpLessDmgEffect",
    "DaughterOfTheAbyssFriendlyDmgReductionPctEffect", "DaughterOfTheAbyssOwnerDmgReductionEffect",
    "OverwhelmingWrathRangeDmgReductionEffect", "PsychicFortressDmgReductionEffect",
    "VexillaMagnificaDmgReductionEffect",
    "MarkerlightEffect",
    # hits
    "SquigHoundAdditionalHitsEffect", "CordClawAdditionalHitsEffect",
    "FoulInfusionExtraHitsEffect", "CyclicIonBlasterAdditionalHitsEffect",
    "FleshmetalGunsFocusedMaliceEffect", "FleshmetalGunsRuinousSalvoEffect",
    "FleshmetalGunsWarpHailEffect",
    "Swarm_HitReductionEffect",
    "ExplosiveMaladiesExtraRangedAttackEffect", "ExplosiveMaladiesExtraMeleeAttackEffect",
    "InfernalPactsAdditionalHitsEffect",
    "AnvilShieldAdditionalBlockEffect", "BeastSlayerExtraBlockEffect",
    "DaemonExtraBlockEffect", "PsychicFortressExtraBlockEffect",
    "FightingRetreatHitReductionEffect", "LightCoverEffect", "ParryEffect",
    "CamouflageHitReductionEffect", "DiminutiveHitReductionEffect",
    "MasterAnnihilatorAdditionalHitEffect", "LetTheGalaxyBurnEffect",
    "LET_THE_GALAXY_BURN_PERSISTENT_KEY",
    "BigTargetAdjacentEffect", "AstartesBannerExtraHitEffect",
    "PowerTripFullHealthEffect", "PowerTripIgnoreArmorEffect", "KanOpenerEffect", "LIGHT_COVER_TILE_ID",
    # status
    "HypersensoryMinimalHealthEffect", "ContaminatedUnitEffect", "StandVigilExtraArmorEffect",
    "BlessingsOfKhorneModifiersEffect", "StunnedEffect", "StunnedDamageModifierEffect",
    "ActOfFaithBuffEffect", "TauntedEffect", "PinnedEffect",
    "MV71InitialDmgEffect", "MV71ResetInitialDmgEffect", "MasterOfTheTutelariesEffect",
    "BlackRageExtraMoveEffect", "BlackRageExtraDamageEffect", "BlackRageAutomaticUnitEffect",
    # imperative
    "ProtectorImperativeEffect", "ConquerorImperativeEffect",
]
