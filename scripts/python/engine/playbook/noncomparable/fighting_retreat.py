"""FightingRetreatPlaybook — retraite NonComparable (self-target)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class FightingRetreatPlaybook(NonComparablePlaybook):
    """IdunBattle.AI.Playbook.Loki.FightingRetreatPlaybook$$EvaluateNonComparable : u = |ennemis adj a la tuile| +
    (si >0) |allies adj a la tuile - self|, balaye sur les tuiles atteignables (origine EN TETE) ;
    cible = SELF. IdunBattle.AI.Playbook.Loki.FightingRetreatPlaybook$$.cctor : MIN_UTILITY=2."""
    ABILITY_ID = int(ActiveAbilityType.FightingRetreat)  # 1081
    MIN_UTILITY = 2.0

    def evaluate_non_comparable(self, tile, ctx):
        # A = GetAdjacentEnemies(tile) [slot 124] ; B = GetAdjacentFriends(tile)-self [slot 128]
        # (self deja exclu de ctx.fpos ; le natif fait B.Remove(self)). u = |A| + (|A|>0 ? |B| : 0).
        a = bq.count_adjacent(tile, ctx.epos, ctx.elev_by_pos)
        if a == 0:
            return 0.0
        return float(a + bq.count_adjacent(tile, ctx.fpos, ctx.elev_by_pos))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        best_t, best_u = None, None
        for T in ctx.reach_nc:
            u_ = self.evaluate_non_comparable(T, ctx)
            if best_u is None or u_ > best_u:   # strict > : premier max garde (ordre reach_nc)
                best_t, best_u = T, u_
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] FR aid={self.ABILITY_ID} reach={len(ctx.reach_nc)} "
                  f"best={best_t} u={best_u} min={self.MIN_UTILITY}", file=sys.stderr)
        if best_u is None or best_u < self.MIN_UTILITY:
            return []
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (best_t if best_t != ctx.origin else None), "pred": best_u}]
