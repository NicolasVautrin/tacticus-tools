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
                   _is_immune_to_fire, _on_fire_damage_ability, _fire_of_absolution_after_attack,
                   FIRE_TILE, FIRE_DMG_PCT_KEY, FIRE_IMMUNE_TRAITS, FIRE_PROFILE,
                   FIRE_OF_ABSOLUTION_IGNITE_CHANCE)
from .act_of_faith import (ActOfFaithAccumulateAbility, ActOfFaithResetAbility,
                           act_of_faith_accumulate_tree, act_of_faith_reset_tree, _reset_act_of_faith,
                           ACTOFFAITH_EFFECT, IMPERIAL_FACTIONS, CRIT_CHANCE_MAX)
from .betrayer import (TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility,
                       betrayer_add_effect_tree, _add_betrayer_effect, _betrayer_target,
                       _betrayer_stop_tile, _betrayer_take_turn,
                       THEBETRAYER_EFFECT, THEBETRAYER_RANGE, THEBETRAYER_PROFILE)
from .arcane_shield import (ArcaneShieldAbility, _arcaneshield_target, _arcaneshield_grant,
                            CHAOS_FACTIONS, ARCANESHIELD_RANGE, ARCANESHIELD_TRAIT_EXCLUDE)
from .final_justice import (FinalJusticeAbility, _finaljustice_target, _finaljustice_attack,
                            _normal_attack_health_range, _damage_utility_weights)
from .control_edict import (ControlEdictAbility, _adjacent_mechanical_summons,
                            PROTECTOR as CONTROLEDICT_PROTECTOR, CONQUEROR as CONTROLEDICT_CONQUEROR)

__all__ = [
    # psyker
    "PsykerExtraAttackAbility", "psyker_smite_tree",
    "PSYKER_OWNER_SUPPRESS", "PSYKER_TARGET_SUPPRESS", "PSYCHIC_PROFILE",
    # fire
    "FireTileDoT", "env_fire_tile_tree", "on_fire_damage_tree", "fire_of_absolution_tree",
    "_is_immune_to_fire", "_on_fire_damage_ability", "_fire_of_absolution_after_attack",
    "FIRE_TILE", "FIRE_DMG_PCT_KEY", "FIRE_IMMUNE_TRAITS", "FIRE_PROFILE",
    "FIRE_OF_ABSOLUTION_IGNITE_CHANCE",
    # act_of_faith
    "ActOfFaithAccumulateAbility", "ActOfFaithResetAbility",
    "act_of_faith_accumulate_tree", "act_of_faith_reset_tree", "_reset_act_of_faith",
    "ACTOFFAITH_EFFECT", "IMPERIAL_FACTIONS", "CRIT_CHANCE_MAX",
    # betrayer
    "TheBetrayerAddEffectAbility", "TheBetrayerTakeTurnAbility",
    "betrayer_add_effect_tree", "_add_betrayer_effect", "_betrayer_target",
    "_betrayer_stop_tile", "_betrayer_take_turn",
    "THEBETRAYER_EFFECT", "THEBETRAYER_RANGE", "THEBETRAYER_PROFILE",
    # arcane_shield
    "ArcaneShieldAbility", "_arcaneshield_target", "_arcaneshield_grant",
    "CHAOS_FACTIONS", "ARCANESHIELD_RANGE", "ARCANESHIELD_TRAIT_EXCLUDE",
    # final_justice
    "FinalJusticeAbility", "_finaljustice_target", "_finaljustice_attack",
    "_normal_attack_health_range", "_damage_utility_weights",
    # control_edict (S4b)
    "ControlEdictAbility", "_adjacent_mechanical_summons",
    "CONTROLEDICT_PROTECTOR", "CONTROLEDICT_CONQUEROR",
]
