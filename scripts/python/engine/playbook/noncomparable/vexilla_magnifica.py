"""VexillaMagnificaPlaybook — attaque NonComparable (_PlanTarget), utilite = PV cible."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import _PlanTargetPlaybook


class VexillaMagnificaPlaybook(_PlanTargetPlaybook):
    """VexillaMagnificaPlaybook.EvaluateNonComparable @18117f6f0 = FromInt(GetStat(cible,5=Health))
    -> PV courants de la cible. cctor @18117fa30 : MIN_UTILITY=1. [filtre HasEffect 0x48a : TODO]."""
    ABILITY_ID = int(ActiveAbilityType.VexillaMagnifica)  # 1183
    MIN_UTILITY = 1.0

    def evaluate_non_comparable(self, tile, target, ctx):
        hp = ctx.hp_cur_by_id.get(target)                          # GetStat(cible, 5=Health)
        return float(hp) if hp and hp > 0 else None
