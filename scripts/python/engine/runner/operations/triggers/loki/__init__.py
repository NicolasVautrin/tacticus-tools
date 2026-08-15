"""Package `loki` — ability-triggers des namespaces natifs
`IdunBattleLogic.Entities.Abilities.{Active,Triggered,Damage}.Loki.*`, **1 module par ability native**
(VA citée dans chaque). Découpé depuis l'ancien monolithe `loki.py` (>1000 l) ; regroupé « Loki » comme
le reste du repo (`abilities/loki.py`, `effects/loki.py`).

Ce `__init__` re-exporte la SURFACE PUBLIQUE COMPLETE → tous les imports externes (`from .loki import X`
dans `dispatch.py`/`triggers/__init__.py`, `from ...triggers.loki import X` dans les tests) restent
INCHANGÉS : le package s'importe exactement comme l'ancien module `loki.py`.

- `psyker.py`        — `Active.Loki`  : PsykerExtraAttackAbility (splash « Smite »).
- `fire.py`          — cluster FEU (effet 5 partagé) : EnvFireTile DoT (`Active`), OnFireDamage (`Damage`),
                       FireOfAbsolution (`Active`) + `_is_immune_to_fire` + constantes `FIRE_*`.
- `act_of_faith.py`  — `Active.Loki`  : ActOfFaith accumulate + reset (buff crit Adepta Sororitas).
- `betrayer.py`      — `Triggered.Loki`: TheBetrayer add-effect (rage) + take-turn (auto-tour).
- `arcane_shield.py` — `Triggered.Loki`: ArcaneShield (bouclier ThousandSons).
- `final_justice.py` — `Active.Loki`  : FinalJustice (attaque de mort de worldKharn).

FRAMEWORK (bases + sélecteurs DSL) = `../base.py` ; DISPATCH (registres + vecteurs +
`EvaluateTriggerOperation`) = `../dispatch.py`."""
from __future__ import annotations

from .psyker import (PsykerExtraAttackAbility, psyker_smite_tree,
                     PSYKER_OWNER_SUPPRESS, PSYKER_TARGET_SUPPRESS, PSYCHIC_PROFILE)
from .fire import (FireTileDoT, env_fire_tile_tree, on_fire_damage_tree, fire_of_absolution_tree,
                   _is_immune_to_fire, OnFireDamageAbility, _fire_of_absolution_after_attack,
                   FIRE_TILE, FIRE_DMG_PCT_KEY, FIRE_IMMUNE_TRAITS, FIRE_PROFILE,
                   fire_of_absolution_ignite_chance)
from .act_of_faith import (ActOfFaithAccumulateAbility, ActOfFaithResetAbility,
                           ActOfFaithCustomRemoveEffectAbility,
                           act_of_faith_accumulate_tree, act_of_faith_reset_tree,
                           act_of_faith_delayed_tree, _reset_act_of_faith,
                           ACTOFFAITH_EFFECT, ACT_OF_FAITH_ABILITY, IMPERIAL_FACTIONS,
                           CRIT_CHANCE_MAX)
from .betrayer import (TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility,
                       betrayer_add_effect_tree, _add_betrayer_effect, _betrayer_target,
                       _betrayer_stop_tile, _betrayer_take_turn,
                       THEBETRAYER_EFFECT, THEBETRAYER_RANGE, THEBETRAYER_PROFILE)
from .arcane_shield import (ArcaneShieldAbility, _arcaneshield_target, _arcaneshield_grant,
                            _arcaneshield_candidates, _arcaneshield_score, _arcaneshield_range,
                            ARCANESHIELD_RANGE, ARCANESHIELD_TRAIT_EXCLUDE,
                            ARCANESHIELD_DISTANCE_WEIGHT, ARCANESHIELD_OWNER_PENALTY_OFFSET)
from .final_justice import (FinalJusticeAbility, _finaljustice_target, _finaljustice_attack,
                            _normal_attack_damage_node, _damage_utility_weights)
from .control_edict import (ControlEdictAbility, _adjacent_mechanical_summons,
                            PROTECTOR as CONTROLEDICT_PROTECTOR, CONQUEROR as CONTROLEDICT_CONQUEROR)
from .rad_saturation import RadSaturationAbility, rad_saturation_tree, CONTAMINATED_TILE as RADSAT_CONTAMINATED_TILE
from .on_toxic_damage import (on_toxic_damage_tree, OnToxicDamageAbility,
                              CONTAMINATED_TILE as TOXIC_CONTAMINATED_TILE, TOXIC_CHANCE_KEY)
from .lord_of_tempests import (LordOfTempestsAddIceAbility, lord_of_tempests_add_ice_tree,
                               ICE_TILE, SMITE_KIND)
from .suppressive_fire import (SuppressiveFireAddEffectAbility, suppressive_fire_tree,
                               PINNED as SUPPRESSIVEFIRE_PINNED)
from .death_nova import (ExplodesAbility, PutridExplosionAbility,
                         explodes_tree, putrid_explosion_tree,
                         EXPLODES_ABILITY, PUTRID_ABILITY, EXPLODES_PROFILE,
                         RAMMING_SPEED_EXTRA_EXPLODE)

__all__ = [
    # psyker
    "PsykerExtraAttackAbility", "psyker_smite_tree",
    "PSYKER_OWNER_SUPPRESS", "PSYKER_TARGET_SUPPRESS", "PSYCHIC_PROFILE",
    # fire
    "FireTileDoT", "env_fire_tile_tree", "on_fire_damage_tree", "fire_of_absolution_tree",
    "_is_immune_to_fire", "OnFireDamageAbility", "_fire_of_absolution_after_attack",
    "FIRE_TILE", "FIRE_DMG_PCT_KEY", "FIRE_IMMUNE_TRAITS", "FIRE_PROFILE",
    "fire_of_absolution_ignite_chance",
    # act_of_faith
    "ActOfFaithAccumulateAbility", "ActOfFaithResetAbility",
    "ActOfFaithCustomRemoveEffectAbility",
    "act_of_faith_accumulate_tree", "act_of_faith_reset_tree", "act_of_faith_delayed_tree",
    "_reset_act_of_faith",
    "ACTOFFAITH_EFFECT", "ACT_OF_FAITH_ABILITY", "IMPERIAL_FACTIONS", "CRIT_CHANCE_MAX",
    # betrayer
    "TheBetrayerAddEffectAbility", "TheBetrayerTakeTurnAbility",
    "betrayer_add_effect_tree", "_add_betrayer_effect", "_betrayer_target",
    "_betrayer_stop_tile", "_betrayer_take_turn",
    "THEBETRAYER_EFFECT", "THEBETRAYER_RANGE", "THEBETRAYER_PROFILE",
    # arcane_shield
    "ArcaneShieldAbility", "_arcaneshield_target", "_arcaneshield_grant",
    "_arcaneshield_candidates", "_arcaneshield_score", "_arcaneshield_range",
    "ARCANESHIELD_RANGE", "ARCANESHIELD_TRAIT_EXCLUDE",
    "ARCANESHIELD_DISTANCE_WEIGHT", "ARCANESHIELD_OWNER_PENALTY_OFFSET",
    # final_justice
    "FinalJusticeAbility", "_finaljustice_target", "_finaljustice_attack",
    "_normal_attack_damage_node", "_damage_utility_weights",
    # control_edict (S4b)
    "ControlEdictAbility", "_adjacent_mechanical_summons",
    "CONTROLEDICT_PROTECTOR", "CONTROLEDICT_CONQUEROR",
    # rad_saturation (S4b GAP — passif du Skitarii Vanguard)
    "RadSaturationAbility", "rad_saturation_tree", "RADSAT_CONTAMINATED_TILE",
    # on_toxic_damage (1203 — jumeau d'OnFireDamage : pose Contaminated 1244 on-hit, gate
    # `IsFirstHitInSeries & Maybe(chance=25)`, 1 tirage par serie de coups)
    "on_toxic_damage_tree", "OnToxicDamageAbility", "TOXIC_CONTAMINATED_TILE", "TOXIC_CHANCE_KEY",
    # lord_of_tempests (#35 — passif AddIce de Njal)
    "LordOfTempestsAddIceAbility", "lord_of_tempests_add_ice_tree", "ICE_TILE", "SMITE_KIND",
    # suppressive_fire (#74 — trait SuppressiveFire 1010 -> triggered 1044 pose Pinned 1065)
    "SuppressiveFireAddEffectAbility", "suppressive_fire_tree", "SUPPRESSIVEFIRE_PINNED",
    # death_nova — traits Explodes (1008 -> 1021) et PutridExplosion (2028 -> 1074), event PreUnitDeath_2
    "ExplodesAbility", "PutridExplosionAbility", "explodes_tree", "putrid_explosion_tree",
    "EXPLODES_ABILITY", "PUTRID_ABILITY", "EXPLODES_PROFILE", "RAMMING_SPEED_EXTRA_EXPLODE",
]
