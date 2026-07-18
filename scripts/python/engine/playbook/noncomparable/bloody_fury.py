"""BloodyFuryPlaybook — attaque NonComparable (_PlanTarget)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import _PlanTargetPlaybook


class BloodyFuryPlaybook(_PlanTargetPlaybook):
    """BloodyFuryPlaybook.EvaluateNonComparable @181122be0 = 1 + (#ennemis adjacents a la tuile
    d'attaque) x ADJACENT_ENEMIES_UTILITY. cctor @181123340 : MIN_UTILITY=1, ADJACENT=10."""
    ABILITY_ID = int(ActiveAbilityType.BloodyFury)  # 1129
    MIN_UTILITY = 1.0
    _ADJACENT_ENEMIES_UTILITY = 10   # cctor @181123340

    def evaluate_non_comparable(self, tile, target, ctx):
        if tile is None:
            return None
        adj = bq.count_adjacent(tile, ctx.epos, ctx.elev_by_pos)   # GetAdjacentEnemies @18105af60
        return 1.0 + adj * self._ADJACENT_ENEMIES_UTILITY
