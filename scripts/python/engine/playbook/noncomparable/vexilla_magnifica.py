"""VexillaMagnificaPlaybook — attaque NonComparable (_PlanTarget), utilite = PV cible."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import _PlanTargetPlaybook


class VexillaMagnificaPlaybook(_PlanTargetPlaybook):
    """IdunBattle.AI.Playbook.Loki.VexillaMagnificaPlaybook$$EvaluateNonComparable = FromInt(GetStat(cible,5=Health))
    -> PV courants de la cible. IdunBattle.AI.Playbook.Loki.VexillaMagnificaPlaybook$$.cctor : MIN_UTILITY=1. [filtre HasEffect 0x48a : TODO]."""
    ABILITY_ID = int(ActiveAbilityType.VexillaMagnifica)  # 1183
    MIN_UTILITY = 1.0

    def should_evaluate(self, ctx) -> bool:
        """Slot 4 de la vtable (0x298, résolu LIVE #46) -> corps FOLDÉ IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$ShouldEvaluate (= le
        `HammerOfWrathPlaybook$$ShouldEvaluate`, COMDAT) : `!EnemyWillBeKilledWithNormalAttack` —
        le natif n'évalue pas Vexilla si l'attaque normale du caster sure-kill déjà un ennemi."""
        from .hammer_of_wrath import _enemy_killed_by_normal_attack
        return not _enemy_killed_by_normal_attack(ctx)

    def evaluate_non_comparable(self, tile, target, ctx):
        hp = ctx.hp_cur_by_id.get(target)                          # GetStat(cible, 5=Health)
        return float(hp) if hp and hp > 0 else None
