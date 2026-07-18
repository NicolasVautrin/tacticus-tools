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
- `status.py`           — stat-mods, composites (Stunned/Taunted), HP-floor, modificateurs multi-axes."""
from __future__ import annotations

from .extra_damage import (RapidAssaultExtraDamageEffect, SmashaEadExtraDamageEffect,
                           FeederTendrilsExtraDamageEffect, DecoysAndMisdirectionExtraDamageEffect,
                           RitesOfBattleExtraDmgEffect, PathOfCommandExtraDmgEffect,
                           CrushingStrikeEffect, HeavyWeaponExtraDmgEffect, RangedSpecialistEffect,
                           BeastSlayerExtraDmgEffect, DaughterOfTheAbyssExtraDamagePctEffect,
                           BeaconOfRageExtraDamageEffect, BeaconOfRageFriendlyExtraDamageEffect)
from .damage_reduction import (TerrifyingExtraDefenseEffect, MartialKatahDmgReductionEffect,
                               TerminatorArmourReduceDmgEffect, GuardianOrganismDamageReductionEffect,
                               NightshroudDmgReductionEffect, NeuroparasiteEffect,
                               FightingRetreatDmgReductionEffect, ShadowInTheWarpLessDmgEffect,
                               DaughterOfTheAbyssFriendlyDmgReductionPctEffect,
                               DaughterOfTheAbyssOwnerDmgReductionEffect,
                               OverwhelmingWrathRangeDmgReductionEffect)
from .hits import (SquigHoundAdditionalHitsEffect, AnvilShieldAdditionalBlockEffect,
                   BeastSlayerExtraBlockEffect, FightingRetreatHitReductionEffect, LightCoverEffect,
                   ParryEffect, MasterAnnihilatorAdditionalHitEffect, BigTargetAdjacentEffect,
                   AstartesBannerExtraHitEffect, PowerTripFullHealthEffect, PowerTripIgnoreArmorEffect,
                   KanOpenerEffect, LIGHT_COVER_TILE_ID)
from .status import (HypersensoryMinimalHealthEffect, ContaminatedUnitEffect, StandVigilExtraArmorEffect,
                     BlessingsOfKhorneModifiersEffect, StunnedEffect, ActOfFaithBuffEffect,
                     TauntedEffect, PinnedEffect)

__all__ = [
    # extra_damage
    "RapidAssaultExtraDamageEffect", "SmashaEadExtraDamageEffect", "FeederTendrilsExtraDamageEffect",
    "DecoysAndMisdirectionExtraDamageEffect", "RitesOfBattleExtraDmgEffect", "PathOfCommandExtraDmgEffect",
    "CrushingStrikeEffect", "HeavyWeaponExtraDmgEffect", "RangedSpecialistEffect",
    "BeastSlayerExtraDmgEffect", "DaughterOfTheAbyssExtraDamagePctEffect",
    "BeaconOfRageExtraDamageEffect", "BeaconOfRageFriendlyExtraDamageEffect",
    # damage_reduction
    "TerrifyingExtraDefenseEffect", "MartialKatahDmgReductionEffect", "TerminatorArmourReduceDmgEffect",
    "GuardianOrganismDamageReductionEffect", "NightshroudDmgReductionEffect", "NeuroparasiteEffect",
    "FightingRetreatDmgReductionEffect", "ShadowInTheWarpLessDmgEffect",
    "DaughterOfTheAbyssFriendlyDmgReductionPctEffect", "DaughterOfTheAbyssOwnerDmgReductionEffect",
    "OverwhelmingWrathRangeDmgReductionEffect",
    # hits
    "SquigHoundAdditionalHitsEffect", "AnvilShieldAdditionalBlockEffect", "BeastSlayerExtraBlockEffect",
    "FightingRetreatHitReductionEffect", "LightCoverEffect", "ParryEffect",
    "MasterAnnihilatorAdditionalHitEffect", "BigTargetAdjacentEffect", "AstartesBannerExtraHitEffect",
    "PowerTripFullHealthEffect", "PowerTripIgnoreArmorEffect", "KanOpenerEffect", "LIGHT_COVER_TILE_ID",
    # status
    "HypersensoryMinimalHealthEffect", "ContaminatedUnitEffect", "StandVigilExtraArmorEffect",
    "BlessingsOfKhorneModifiersEffect", "StunnedEffect", "ActOfFaithBuffEffect",
    "TauntedEffect", "PinnedEffect",
]
