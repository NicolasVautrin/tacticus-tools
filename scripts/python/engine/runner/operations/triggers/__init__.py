"""Package trigger du runner — re-export de l'API publique (les imports `from .triggers import X`
des autres modules restent INCHANGÉS : le package s'importe comme l'ancien module `triggers.py`).

Découpage fidèle au namespace natif :
- `base.py`             — FRAMEWORK (`AbilityTrigger`/`EffectTrigger` + abstraction TUILE) + sélecteurs DSL.
- `dispatch.py`         — `IdunBattle.Operations.EvaluateTriggerOperation` (registres + collect + vecteurs).
- `loki.py`             — `Abilities.{Active,Triggered,Damage}.Loki.*` (Psyker, ActOfFaith, TheBetrayer,
                          FinalJustice, ArcaneShield, EnvFireTile, FireOfAbsolution, OnFireDamage).
- `tiles.py`            — `Abilities.Tiles.*` (DryBushFireSpread, FirstAidHeal).
- `effect_triggers.py`  — `Entities.Effects.*` (Contaminated, Overwatch).
"""
from .base import (TriggerEvent, TriggeredAbility, EffectTrigger, TileEffectTrigger,
                   PHASE_TRIGGER_CAP, triggered_ability_state,
                   _unit_tile, _hex_dist, _adjacent_enemies, _is_adjacent_units)
from .dispatch.ability import (pre_unit_ability_triggers, unit_ability_triggers,
                               unit_post_ability_triggers)
from .dispatch.attack import (
    after_hit_ability_attack, after_hit_normal_attack, attack_damage_attack_triggers,
    finish_attack_triggers, pre_attack_triggers,
    pre_damage_taken_triggers          # #963 -- `On(0x39 = PreDamageTaken)`, sans emetteur avant
)
from .dispatch.core import (
    collect_effect_triggers, collect_triggered_abilities, evaluate_trigger_operation
)
from .dispatch.move_death import (
    after_death_triggers, after_move_triggers, arrived_at_final_tile_triggers, displace_triggers,
    effect_added_triggers, effect_removed_triggers, pending_death_added_triggers,
    post_unit_kill_triggers,
    pre_effect_added_triggers, pre_effect_removed_triggers, pre_move_triggers,
    pre_unit_death_2_triggers, unit_death_triggers, unit_defeated_triggers,
    unit_position_changed_1_triggers, unit_position_changed_2_triggers, unit_removed_triggers,
    unit_resurrected_triggers, unit_revived_triggers
)
from .dispatch.phase import phase_end_triggers
from .dispatch.registry import (
    ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS, EFFECT_TRIGGERS, TRAIT_TRIGGERS,
    PASSIVE_HELPER_ABILITY_TRIGGERS          # #521-r1 -- `...ActiveAbility$$GetPassiveHelperAbility`
)
from .dispatch.turn import (
    delayed_attack_triggers, end_turn_summon_triggers, start_turn_triggers, tile_tick_triggers,
    turn_start_other_triggers, unit_finished_turn_normally_triggers, unit_finished_turn_triggers
)
from engine.services.damage_prediction import is_overkill, unit_is_overkill
from .loki import (
    _fire_of_absolution_after_attack, OnFireDamageAbility, OnToxicDamageAbility,
    THEBETRAYER_EFFECT, ACTOFFAITH_EFFECT,
    _add_betrayer_effect, _reset_act_of_faith,
    _finaljustice_target, _normal_attack_damage_node, _damage_utility_weights,
    _arcaneshield_grant, _arcaneshield_target,
    _betrayer_take_turn, _betrayer_target, _betrayer_stop_tile,
)
from .tiles import first_aid_heal, dry_bush_fire_spread

__all__ = [
    "TriggerEvent", "TriggeredAbility", "EffectTrigger", "TileEffectTrigger", "PHASE_TRIGGER_CAP",
    "triggered_ability_state",
    "_unit_tile", "_hex_dist", "_adjacent_enemies", "_is_adjacent_units",
    "TRAIT_TRIGGERS", "ABILITY_TRIGGERS", "ACTIVE_ABILITY_TRIGGERS", "EFFECT_TRIGGERS",
    "PASSIVE_HELPER_ABILITY_TRIGGERS",
    "collect_triggered_abilities", "collect_effect_triggers", "evaluate_trigger_operation",
    "after_death_triggers", "is_overkill", "unit_is_overkill", "start_turn_triggers",
    "turn_start_other_triggers", "tile_tick_triggers", "delayed_attack_triggers",
    "unit_finished_turn_triggers", "unit_finished_turn_normally_triggers",
    "pre_attack_triggers", "pre_unit_ability_triggers", "unit_ability_triggers",
    "unit_post_ability_triggers",
    "after_hit_normal_attack", "after_hit_ability_attack", "after_move_triggers", "displace_triggers",
    "attack_damage_attack_triggers", "finish_attack_triggers",
    "end_turn_summon_triggers", "unit_defeated_triggers", "unit_death_triggers",
    "unit_resurrected_triggers", "pre_unit_death_2_triggers", "pre_effect_added_triggers",
    "effect_added_triggers", "pre_effect_removed_triggers", "effect_removed_triggers",
    "unit_revived_triggers", "pending_death_added_triggers",
    "post_unit_kill_triggers", "arrived_at_final_tile_triggers", "pre_damage_taken_triggers",
    "pre_move_triggers", "unit_position_changed_1_triggers", "unit_position_changed_2_triggers",
    "unit_removed_triggers", "phase_end_triggers",
    "_fire_of_absolution_after_attack", "OnFireDamageAbility", "OnToxicDamageAbility",
    "THEBETRAYER_EFFECT", "ACTOFFAITH_EFFECT",
    "_add_betrayer_effect", "_reset_act_of_faith",
    "_finaljustice_target", "_normal_attack_damage_node", "_damage_utility_weights",
    "_arcaneshield_grant", "_arcaneshield_target",
    "_betrayer_take_turn", "_betrayer_target", "_betrayer_stop_tile",
]
