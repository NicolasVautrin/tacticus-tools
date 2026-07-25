"""AberrantHypermorphPlaybook — action composee move+summon (NonComparable)."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class AberrantHypermorphPlaybook(NonComparablePlaybook):
    """IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$EvaluateNonComparable (action COMPOSEE move+summon).
    Le generator balaie les tuiles de MOVE du caster ; par tuile T, le selector
    `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` rend les tuiles de SPAWN eligibles (ring-1 libre,
    portee=1 — gameconfig 1166 « free adjacent hex ») ; utilite d'un spawn ST = #ennemis adjacents
    (`IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$GetUtility`, slot 126 GetAdjacentEnemies -> Fix64.FromInt). Le caster BOUGE vers la
    tuile T qui maximise ce count. IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$.cctor : MIN_UTILITY=1.

    NB abilityTargets.targets = UNION des spawns sur TOUTES les tuiles de move
    (GetAllValidTargetsFromAllPossibleMovementTiles, dist 0-4 de l'origine) — le filtre
    distance(T,ST)==1 reconstitue le per-tuile."""
    ABILITY_ID = int(ActiveAbilityType.AberrantHypermorph)  # 1166
    MIN_UTILITY = 1.0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        spawn_tiles = self._eligible_spawn_tiles(ctx)
        best_t, best_u = None, None
        for T in ctx.reach_nc:   # positions candidates du caster (origine + tuiles de move)
            # IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$GetUtility (slot 126 GetAdjacentEnemies) = #ennemis adjacents au spawn ST.
            cnt = [float(bq.count_adjacent(ST, ctx.epos, ctx.elev_by_pos))
                   for ST in spawn_tiles if hexgeo.distance(T, ST) == 1]
            u_ = max(cnt) if cnt else 0.0
            if best_u is None or u_ > best_u:   # strict > : premier max garde (ordre reach_nc)
                best_t, best_u = T, u_
        if best_t is None or best_u < self.MIN_UTILITY:
            return []
        return [{"target": None, "ability": self.ABILITY_ID,
                 "to": (best_t if best_t != ctx.origin else None), "pred": best_u}]

    def _eligible_spawn_tiles(self, ctx: NCContext) -> list[tuple]:
        """Mirror IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable : union des tuiles de spawn
        (kind="tile") via l'RPC abilityTargets."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        tiles: list[tuple] = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID:
                    tiles = [(t["tile"].get("col"), t["tile"].get("row"))
                             for t in (a.get("targets") or [])
                             if t.get("kind") == "tile" and t.get("tile")
                             and t["tile"].get("col") is not None]
        return tiles
