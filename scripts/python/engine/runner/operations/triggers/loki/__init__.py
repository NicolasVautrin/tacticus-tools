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

from .psyker import PsykerExtraAttackAbility
from .fire import (
    FireTileDoT, env_fire_tile_tree, OnFireDamageAbility, _fire_of_absolution_after_attack,
    FIRE_TILE, FIRE_DMG_PCT_KEY, FIRE_PROFILE, fire_of_absolution_ignite_chance
)
from .act_of_faith import (
    ActOfFaithAccumulateAbility, ActOfFaithResetAbility, ActOfFaithCustomRemoveEffectAbility,
    _reset_act_of_faith, ACTOFFAITH_EFFECT, ACT_OF_FAITH_ABILITY, IMPERIAL_FACTIONS
)
from .betrayer import (
    TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility, _add_betrayer_effect,
    _betrayer_target, _betrayer_stop_tile, _betrayer_take_turn, THEBETRAYER_EFFECT
)
from .arcane_shield import ArcaneShieldAbility, _arcaneshield_target, _arcaneshield_grant
from .final_justice import (
    FinalJusticeAbility, _finaljustice_target, _normal_attack_damage_node, _damage_utility_weights
)
from .control_edict import ControlEdictAbility
from .rad_saturation import RadSaturationAbility
from .on_toxic_damage import OnToxicDamageAbility
from .lord_of_tempests import LordOfTempestsAddIceAbility

__all__ = [
    "PsykerExtraAttackAbility", "FireTileDoT", "env_fire_tile_tree", "OnFireDamageAbility",
    "_fire_of_absolution_after_attack", "FIRE_TILE", "FIRE_DMG_PCT_KEY", "FIRE_PROFILE",
    "fire_of_absolution_ignite_chance", "ActOfFaithAccumulateAbility", "ActOfFaithResetAbility",
    "ActOfFaithCustomRemoveEffectAbility", "_reset_act_of_faith", "ACTOFFAITH_EFFECT",
    "ACT_OF_FAITH_ABILITY", "IMPERIAL_FACTIONS", "TheBetrayerAddEffectAbility",
    "TheBetrayerTakeTurnAbility", "_add_betrayer_effect", "_betrayer_target",
    "_betrayer_stop_tile", "_betrayer_take_turn", "THEBETRAYER_EFFECT", "ArcaneShieldAbility",
    "_arcaneshield_target", "_arcaneshield_grant", "FinalJusticeAbility", "_finaljustice_target",
    "_normal_attack_damage_node", "_damage_utility_weights", "ControlEdictAbility",
    "RadSaturationAbility", "OnToxicDamageAbility", "LordOfTempestsAddIceAbility",
]
