"""Abilities actives du namespace natif `...Abilities.Active.Loki.*` — 1 classe par ability (VA citée).

Chaque `execute_behaviour` reproduit la behaviour-seq de `<Ability>.ExecuteBehaviour` native : on appelle
les operations portées dans le MÊME ORDRE que le DSL (attaque → AddEffect → déplacements). Au scope de la
tranche EFFETS, l'étape **AddEffect** est portée+validée ; les étapes attaque/push/move (qui mutent PV /
positions) délèguent à leurs tranches (DAMAGE param-ability, déplacement) et sont marquées TODO avec leur
VA pour rester fidèle à la SÉQUENCE.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .base import ActiveAbility, turns_from_rounds, ability_attack_params
from ..operations.effects import AddEffectOperation
from ..operations.damage import AttackDamageOperation

if TYPE_CHECKING:
    from ..state import State

STUNNED = 0x48a          # 1162 EffectType.Stunned (effet COMPOSITE → enfants 1165/1166/1167)


class ThunderousAssaultAbility(ActiveAbility):
    """`ThunderousAssaultAbility.ExecuteBehaviour` @1812158b0 (id 1043, templSwordBrother).

    Séquence native (`&` = op_BitwiseAnd) :
        AttackWithAttackDamage(Nearest enemy, 1x Power)        # [DAMAGE param-ability — TODO]
      & AddEffect(0x48a Stunned, source=casterStateRef, TurnsFromRounds(1))   # ← PORTÉ ici (vecteur attaque)
      & PushUnit(target, 1 hex)                                # [déplacement — TODO ; no-op si BigTarget]
      & KillDeadUnits & MoveUnit(caster -> hex libéré)         # [déplacement — TODO]
    VALIDÉ live : pose Stunned(1162, rem=1) + enfants 1165/1166/1167 sur la cible (cf. test_effect_stun_live)."""
    __slots__ = ()
    ABILITY_TYPE = 1043

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        atk = None
        if target_id is not None:
            # [attaque] AttackWithAttackDamage — dégât d'ABILITY (minDmg/maxDmg config[level], profile
            # Power adjacent, nrOfHits=1). Mute les PV cible (skip si rng non calé : replay effet-seul).
            bmin, bmax, pierce, hits = ability_attack_params(
                state, caster_id, "ThunderousAssault", "Power", ranged=False)
            atk = AttackDamageOperation.execute_ability_attack(
                state, caster_id, target_id, bmin, bmax, pierce, hits)
            # [AddEffect] Stunned 1162, durée = TurnsFromRounds(1 round) :
            AddEffectOperation.execute(state, source=caster_id, target=target_id,
                                       effect_type=STUNNED, name="Stunned",
                                       duration_override=turns_from_rounds(1))
        # [push/kill/move] PushUnit(target) & KillDeadUnits & MoveUnit(caster) : déplacements/positions.
        # TODO (tranche déplacement). BigTarget cible => push no-op (cf. RE tyranTyrantGuard).
        return {"attack": atk}


class GravitonRifleAbility(ActiveAbility):
    """`GravitonRifleAbility.ExecuteBehaviour` @1811e31a0 (id 1206, votanIronmaster).

    Séquence native (`+` = op_Addition) :
        AttackWithAttackDamage(target, 3x Physical, +extraPierce vs Gravis/Terminator/Mechanical)  # [TODO]
      + AddEffect(0x48a Stunned, source=casterStateRef, TurnsFromRounds(GetNumberConstant 0x45 = nrOfRounds=1))
    MÊME pattern AddEffect que ThunderousAssault. ⚠ votanIronmaster N'EST PAS dans le pool du runner
    (non spawnable) → cette ability n'est PAS validée live ; portée pour documenter le pattern partagé."""
    __slots__ = ()
    ABILITY_TYPE = 1206

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        atk = None
        if target_id is not None:
            # [attaque] 3x Physical (range 2). ⚠ extraPierceRatio CONDITIONNEL (+40% vs Gravis/Terminator/
            # Mechanical) NON modélisé ici (TODO : gate sur le type de cible) ; pierce de base sinon.
            bmin, bmax, pierce, hits = ability_attack_params(
                state, caster_id, "GravitonRifle", "Physical", ranged=True)
            atk = AttackDamageOperation.execute_ability_attack(
                state, caster_id, target_id, bmin, bmax, pierce, hits)
            # [AddEffect] Stunned 1162, durée = TurnsFromRounds(nrOfRounds=1) :
            AddEffectOperation.execute(state, source=caster_id, target=target_id,
                                       effect_type=STUNNED, name="Stunned",
                                       duration_override=turns_from_rounds(1))
        return {"attack": atk}
