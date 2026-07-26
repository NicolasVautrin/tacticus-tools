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
                   PHASE_TRIGGER_CAP, _unit_tile, _hex_dist, _adjacent_enemies, _is_adjacent_units)
from .dispatch import (
    TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS, EFFECT_TRIGGERS,
    collect_triggered_abilities, collect_effect_triggers, evaluate_trigger_operation,
    after_death_triggers, is_overkill, start_turn_triggers, turn_start_other_triggers,
    tile_tick_triggers,
    pre_attack_triggers, pre_unit_ability_triggers, unit_post_ability_triggers,
    after_hit_normal_attack, after_hit_ability_attack, after_move_triggers, displace_triggers,
    end_turn_summon_triggers, unit_defeated_triggers, unit_death_triggers,
    unit_resurrected_triggers, pre_unit_death_2_triggers, pre_effect_added_triggers,
    unit_revived_triggers,
)
from .loki import (
    _fire_of_absolution_after_attack, _on_fire_damage_ability,
    THEBETRAYER_EFFECT, ACTOFFAITH_EFFECT,
    _add_betrayer_effect, _reset_act_of_faith,
    _finaljustice_target, _normal_attack_health_range, _damage_utility_weights,
    _arcaneshield_grant, _arcaneshield_target,
    _betrayer_take_turn, _betrayer_target, _betrayer_stop_tile,
)
from .tiles import first_aid_heal, dry_bush_fire_spread

__all__ = [
    "TriggerEvent", "TriggeredAbility", "EffectTrigger", "TileEffectTrigger", "PHASE_TRIGGER_CAP",
    "_unit_tile", "_hex_dist", "_adjacent_enemies", "_is_adjacent_units",
    "TRAIT_TRIGGERS", "ABILITY_TRIGGERS", "ACTIVE_ABILITY_TRIGGERS", "EFFECT_TRIGGERS",
    "collect_triggered_abilities", "collect_effect_triggers", "evaluate_trigger_operation",
    "after_death_triggers", "is_overkill", "start_turn_triggers", "turn_start_other_triggers",
    "tile_tick_triggers",
    "pre_attack_triggers", "pre_unit_ability_triggers", "unit_post_ability_triggers",
    "after_hit_normal_attack", "after_hit_ability_attack", "after_move_triggers", "displace_triggers",
    "end_turn_summon_triggers", "unit_defeated_triggers", "unit_death_triggers",
    "unit_resurrected_triggers", "pre_unit_death_2_triggers", "pre_effect_added_triggers",
    "unit_revived_triggers",
    "_fire_of_absolution_after_attack", "_on_fire_damage_ability",
    "THEBETRAYER_EFFECT", "ACTOFFAITH_EFFECT",
    "_add_betrayer_effect", "_reset_act_of_faith",
    "_finaljustice_target", "_normal_attack_health_range", "_damage_utility_weights",
    "_arcaneshield_grant", "_arcaneshield_target",
    "_betrayer_take_turn", "_betrayer_target", "_betrayer_stop_tile",
]
