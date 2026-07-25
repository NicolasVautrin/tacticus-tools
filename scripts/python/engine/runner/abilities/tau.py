"""Abilities actives TAU (namespace natif `IdunBattleLogic.Entities.Abilities.Active.Loki.*`).

Contenu :
- `HeavyRailRifle` (1160, `tauBroadside` -- Tson'ji, MachineOfWar) : ability MoW **2-PHASES** dont le
  behaviour de CAST est une PURE POSE D'EFFETS (aucune attaque, aucun spawn, aucune stat touchee) --
  patron « pose d'effet(s) seule » du lot #90-B (cf. `docs/rl/case-90-mow-effect-posers.md`). Le cast
  ARME la phase 1 ; le degat vient de la phase 2 (`Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility`,
  porte par l'effet `HeavyRailRifle_PendingAttack`) -- HORS de ce port (cf. residus du case doc).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .base import ActiveAbility
from .behaviours import AddEffect, entities_from_state
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import op_and
from ...entities.effect_type import EffectType
from ...entities.selectors import Caster, Target

if TYPE_CHECKING:
    from ..state import State

HEAVY_RAIL_RIFLE_PENDING_ATTACK = int(EffectType.HeavyRailRifle_PendingAttack)   # 0x535 = 1333
HEAVY_RAIL_RIFLE_PENDING_TARGET = int(EffectType.HeavyRailRifle_PendingTarget)   # 0x536 = 1334


def heavy_rail_rifle_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE :

        Execute(   AddEffect(0x536=1334 HeavyRailRifle_PendingTarget, AbilityStateReference,
                             source=caster@0x160, targets=target@0x178, options=ZERO)
                 & AddEffect(0x535=1333 HeavyRailRifle_PendingAttack, AbilityStateReference,
                             source=caster@0x160, targets=caster@0x160,  options=ZERO) )

    DEUX `DSLFactory.AddEffect` combines par `AbilityBehaviour.op_BitwiseAnd`, passes a
    `AActiveAbility.Execute` (PAS `ExecuteAtomic`). AUCUN autre noeud : ni attaque, ni `ChangeStat`,
    ni `Spawn` -- le cast ne fait que MARQUER (la cible) et ARMER (la MoW).

    Les DEUX options-structs sont ZERO-initialisees (`local_178..uStack_160 = 0`) : pas de
    `TurnsFromRounds` -> duree = `DefaultAmountOfRounds` de l'effet. 1333/1334 sont ABSENTS de la table
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds` -> Nullable null -> `remaining = 0` = PERMANENT (l'effet est consomme par la phase 2,
    pas expire par un timer). CONFIRME LIVE : les deux effets sortent a `remaining 0, level 1`."""
    return op_and(
        AddEffect(HEAVY_RAIL_RIFLE_PENDING_TARGET, EffectType.HeavyRailRifle_PendingTarget.name,
                  Target(), duration_rounds=None),
        AddEffect(HEAVY_RAIL_RIFLE_PENDING_ATTACK, EffectType.HeavyRailRifle_PendingAttack.name,
                  Caster(), duration_rounds=None))


class HeavyRailRifleAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour` (id 1160, `tauBroadside` Broadside -- Tau,
    MachineOfWar). Cast UNIT-TARGET (`abilityTargets` kind="unit").

    RE (ghidra gqfc5mff6c) :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour` : `Execute( AddEffect(0x536, absRef, caster@0x160, target@0x178,
      opts=0) & AddEffect(0x535, absRef, caster@0x160, caster@0x160, opts=0) )` -- cf.
      `heavy_rail_rifle_tree`.
    - `.IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$.ctor` : `AActiveAbility.ctor(..., TargetingOptions unit-target)`.
    - PHASE 2 (NON PORTEE) : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility`
      (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility$$GetFinalUnitDamageAmount`) -- l'attaque differee portee par `HeavyRailRifle_PendingAttack`
      sur la MoW, qui frappe l'unite marquee `HeavyRailRifle_PendingTarget`. Le degat (minDmg/maxDmg,
      profil Piercing, nrOfHits=2, `dmgPctReduction`/`extraDmgPct`) appartient a CETTE phase, pas au cast.

    OBSERVABLE DU CAST (mesure live, runner MoW C1_02, caster 53, cible 49) :
        49    : + HeavyRailRifle_PendingTarget (1334, remaining 0, level 1)
        mow53 : + HeavyRailRifle_PendingAttack (1333, remaining 0, level 1)

    Flags de tour : defauts base (1160 absent des tables d'override `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> l'ability termine le tour + pose ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HeavyRailRifle)   # 1160
    ABILITY_ID = "HeavyRailRifle"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        heavy_rail_rifle_tree().execute(entities, ectx)
        posed = [{"target": p["target"], "effect": p["effect_type"]}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"posed": posed, "dsl": True}
