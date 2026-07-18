"""NovaShieldPlaybook — marquage AoE tile-target NonComparable."""
from __future__ import annotations

import hexgeo
from engine.ai.utilities import get_movement_utility
from engine.utilities.utility_type import UtilityType
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class NovaShieldPlaybook(NonComparablePlaybook):
    """`NovaShieldPlaybook.EvaluateNonComparable @18114f9d0` (tier get_Priority=**0** — #115 : aucun
    override get_Priority, defaut base NonComparable ; l'ancien -1000 = @1807D66A0 stale ; id 0x4aa=1194).
    cctor @1811502c0 : MIN_UTILITY=1. Marque un hex CENTRE + son ring-1 (hors trench), dégât AoE différé.
    Par (casterPos ∈ reach, center ∈ cibles-éligibles) :
        marked(center) = {center} ∪ neighbors(center) \\ trench          # GetMarkedTiles @1811f83c0
        util = 100*CountEnemiesOnTiles(marked) + Count(marked)            # @1814aae40 (non-alliés) + get_Count
               + Tile(7)@casterPos + DislikeStartingTiles(27)@casterPos   # GetMovementUtility @1814ab490
    Les 2 termes mouvement dépendent de `casterPos` SEUL (constants sur la boucle center). `ChooseAction`
    = argmax STRICT `>`, gate util >= 1. Cible native = le CENTRE marqué (kind=tile).
    HYPOTHÈSE(trench) : flag isTrench non capturé -> ring géométrique complet (biais <=6 sur Count,
    écrasé par 100*enemies).
    STATUT : DECOMPILE-PROVEN, ARENE-INAGREABLE (Riptide non spawnable). R1 (#80) : NovaShield est
    TILE-target (marque un CENTRE hex, cible kind=tile) -> classe DIFFERENTE des self-cast heals/NovaBoost.
    Le generateur `<GenerateActions>d__7 @18119a3f0` gate les tuiles de move par `HasValidTargets(0x3f)` :
    pour une TILE-target les hex a marquer existent depuis la plupart des positions -> les tuiles de move NE
    sont PAS gatees comme un self-cast -> au tie keep-first la 1re tuile de move gagne (le natif BOUGE). De
    plus l'utilite DEPEND de la position (100*ennemis marques) -> argmax non-trivial, le tie-break n'est que
    secondaire. => on GARDE le sweep origine-LAST (`ctx.reach_nc`). [UNVERIFIED : arene-inagreable +
    `HasValidTargets` derriere dispatch d'interface ; la classe TILE-target n'a PAS de confirmation live comme
    la classe self-target #76 -> ne PAS asserter fermement.] R2 : `DislikeStartingTilesUtility` no-op (poids
    BC non confirmé, arene-inagreable)."""
    ABILITY_ID = int(ActiveAbilityType.NovaShield)  # 1194
    MIN_UTILITY = 1.0
    PRIORITY = 0          # #115 : get_Priority de base (aucun override) = 0, PAS -1000 (source @1807D66A0 stale)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        centers = self._eligible_mark_centers(ctx)
        if not centers:
            return []
        epos = set(ctx.epos or [])
        board = ctx.elev_by_pos or {}
        best = None  # (caster_pos, util)
        for caster_pos in ctx.reach_nc:
            # GetMovementUtility(Tile) + GetMovementUtility(DislikeStartingTiles) @1814ab490 (2 appels natifs).
            move_term = (get_movement_utility(ctx, caster_pos, UtilityType.Tile)
                         + get_movement_utility(ctx, caster_pos, UtilityType.DislikeStartingTilesUtility))
            for center in centers:
                marked = [center] + [n for n in hexgeo.neighbors(*center)
                                     if (not board) or (n in board)]        # GetMarkedTiles \ trench
                n_enemy = sum(1 for t in marked if t in epos)               # CountEnemiesOnTiles @1814aae40
                u = 100.0 * n_enemy + len(marked) + move_term              # 100*enemies + get_Count(marked)
                if best is None or u > best[1]:   # strict > : 1er max garde
                    best = (caster_pos, u)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        caster_pos, u = best
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] NovaShield centers={len(centers)} best_to={caster_pos} "
                  f"u={u} min={self.MIN_UTILITY}", file=sys.stderr)
        return [{"target": None, "ability": self.ABILITY_ID,
                 "to": (caster_pos if caster_pos != ctx.origin else None), "pred": u}]

    def _eligible_mark_centers(self, ctx: NCContext) -> list[tuple]:
        """Mirror `BasePlaybook.GetEligibleTargetsSelectable @18111f0d0` : hex candidats du marquage
        (kind="tile") via l'RPC abilityTargets (union sur toutes les tuiles de move)."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        out: list[tuple] = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID:
                    out = [(t["tile"].get("col"), t["tile"].get("row"))
                           for t in (a.get("targets") or [])
                           if t.get("kind") == "tile" and t.get("tile")
                           and t["tile"].get("col") is not None]
        return out
