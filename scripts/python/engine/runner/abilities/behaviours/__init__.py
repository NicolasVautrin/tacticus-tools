"""FEUILLES d'effet a EFFET du namespace natif `IdunBattle.Entities.Behaviours.*`, RUNNER-COUPLEES, +
builder de contexte `entities_from_state` (#149).

Contenu = les `*Behaviour` CONCRETS qui MUTENT l'etat en emettant une runner Operation deja portee :
`Spawn` (`SpawnUnitBehaviour` @180fd5ab0 -> `_spawn_config_grot`), `AttackWithAttackDamage`
(`DSLFactory.AttackWithAttackDamage` @180de9fb0 -> `AttackDamageOperation.execute_ability_attack`/
`execute_normal_like` : attaque d'ability crit/block), `AttackWithAbilityDamage`
(`DSLFactory.AttackWithAbilityDamage` @180de9c90 -> `AttackDamageOperation.execute_direct` : degat DIRECT
sans crit/block — DoT feu `EnvFireTile`), `AddEffect` (`AddEffectBehaviour` @180f947e0 ->
`AddEffectOperation`), `AddBondEffect`
(`AddBondEffectBehaviour` -> idem), `PerformAIAttack` (`PerformAIAbilityUnitBehaviour` @180fcb940). Couche
MINCE d'orchestration au-dessus des mutateurs ECS.

Ils vivent ICI (et non dans `entities/behaviours.py` avec les COMBINATEURS purs `Seq`/`Maybe`/`Foreach`/
`If`/`AtomicGroup`, MEME namespace natif `Entities.Behaviours`) parce qu'ils sont RUNNER-COUPLES (appellent
des Operations de `runner/`, que `entities/` ne peut importer sans inverser le layering). Le split
entities/runner = layering, PAS le namespace natif.

Ce package ne contient QUE des `Entities.Behaviours` :
- Les COMBINATEURS purs -> `engine/entities/behaviours.py`.
- Les SELECTEURS/FORMULES (`Children`=`AllAliveMachinesSelector`, `LastUnitAttackedBy`=`LastUnitAttackedBy
  Selector`, `TotalAttacksMade`/`UnitTurnsStarted`=`*Formula`) -> `entities/selectors.py` + `entities/formulas.py`
  (leur vrai namespace `Entities.Selectors`/`Formulas`).
- Les ARBRES d'ability SPECIFIQUES (`thunderous_assault_tree`/`getemruntz_tree`…) -> `abilities/loki.py`
  (namespace natif `Abilities.Active.Loki`, avec leur classe d'ability).

`entities_from_state` construit le `DslContext` (= l'`entities` natif lu par les selecteurs) depuis le
`State` runner. cf. docs/rl/dsl-effect-nodes.md.

DECOUPAGE EN PACKAGE (module >1000 lignes scinde par FAMILLE de feuille, ré-export ci-dessous pour que les
call-sites `from ..behaviours import X` restent inchanges) :
- `context`   : `entities_from_state`, `LiveUnit`, `_unit_dict` (socle du contexte DSL).
- `summon`    : `Spawn`, `PerformAIAttack`, `SpawnSummon`, `SpawnReplica`.
- `combat`    : `AttackWithAttackDamage`, `AttackWithAbilityDamage`, `EvaluateAbilities`, `UseActiveAbility`.
- `effects`   : `AddBondEffect`, `AddEffect`, `RemoveEffect`, `SetOnFire`, `CreateShield`.
- `stats`     : `Heal`, `ChangeStat`, `SetHealth` (+ futur `AddStaticStatModifierEffect`).
- `movement`  : `PushUnit`, `MoveUnit` (+ futur `ResetMovement`).
- `lifecycle` : `KillDeadUnits`, `RemoveUnit` (+ futur REVIVE / `TriggerAbility`).
"""
from __future__ import annotations

from .context import entities_from_state, LiveUnit, _unit_dict
from .summon import Spawn, PerformAIAttack, SpawnSummon, SpawnReplica
from .combat import AttackWithAttackDamage, AttackWithAbilityDamage, EvaluateAbilities, UseActiveAbility
from .effects import (AddBondEffect, AddEffect, RemoveEffect, SetOnFire, CreateShield,
                      _add_effect_targets, _add_effect_target_id)
from .stats import Heal, ChangeStat, SetHealth, is_mechanical, healable_heal_type_0
from .movement import PushUnit, MoveUnit
from .lifecycle import KillDeadUnits, RemoveUnit

__all__ = [
    "entities_from_state", "LiveUnit",
    "Spawn", "PerformAIAttack", "SpawnSummon", "SpawnReplica",
    "AttackWithAttackDamage", "AttackWithAbilityDamage", "EvaluateAbilities", "UseActiveAbility",
    "AddBondEffect", "AddEffect", "RemoveEffect", "SetOnFire", "CreateShield",
    "Heal", "ChangeStat", "SetHealth", "is_mechanical", "healable_heal_type_0",
    "PushUnit", "MoveUnit",
    "KillDeadUnits", "RemoveUnit",
]
