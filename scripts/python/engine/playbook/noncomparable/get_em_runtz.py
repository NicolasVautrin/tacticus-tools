"""GetEmRuntzPlaybook — summon de grots NonComparable (gate minSummons HP%)."""
from __future__ import annotations

import hexgeo
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class GetEmRuntzPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.GetEmRuntzPlaybook$$EvaluateNonComparable` (id 1045, orksRuntherd). Utilité = NOMBRE de
    tuiles de spawn = |hex LIBRES adjacents au caster ∩ adjacents à un ennemi| (`GetSpawnTileSelector`).
    `MIN_UTILITY` = `minSummons` DYNAMIQUE selon les PV% du caster (`IdunBattle.AI.Playbook.Loki.GetEmRuntzPlaybook$$GetMinSummonsToUse` :
    `GetStat(Health, part1=%)` -> <=49 => 1 ; 49<..<75 => 2 ; >=75 => 3). L'IA caste si `numTiles >= minSummons` ;
    utilité = `numTiles`. IdunBattle.AI.Playbook.Loki.GetEmRuntzPlaybook$$.cctor : base 1. get_Priority = 0 (défaut). NonComparable = évaluée AVANT
    l'attaque. Le caster NE bouge PAS (spawn autour de sa position actuelle)."""
    ABILITY_ID = int(ActiveAbilityType.GetEmRuntz)  # 1045
    MIN_UTILITY = 1.0      # plancher structurel ; le vrai gate = minSummons dynamique (generate_candidates)

    def _min_summons(self, ctx: NCContext) -> int:
        # GetMinSummonsToUse : PV% du caster -> 1/2/3 (défaut prudent 3 si inconnu).
        hp = hpmax = None
        for u in (ctx.obs_units or []):
            if u.get("squadId") == ctx.uid:
                hp, hpmax = u.get("hp"), u.get("hpMax")
                break
        if not hp or not hpmax:
            return 3
        pct = 100 * int(hp) // int(hpmax)
        return 1 if pct <= 49 else (2 if pct < 75 else 3)

    def _spawn_tile_count(self, ctx: NCContext) -> int:
        # GetSpawnTileSelector : hex LIBRES adjacents au caster (dist hex 1) ∩ adjacents à >=1 ennemi.
        valid = set(ctx.elev_by_pos.keys()) if ctx.elev_by_pos else set()
        occ = set(ctx.epos) | set(ctx.fpos) | {ctx.origin}
        n = 0
        for T in valid:
            if T in occ or hexgeo.distance(ctx.origin, T) != 1:
                continue
            if any(hexgeo.distance(e, T) == 1 for e in ctx.epos):    # adjacent à un ennemi
                n += 1
        return n

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        num = self._spawn_tile_count(ctx)
        if num <= 0 or num < self._min_summons(ctx):     # gate minSummons (HP%-dépendant)
            return []
        # utilité = nombre de grots qui apparaîtraient ; caster ne bouge pas (to=None) ; target=None.
        return [{"target": None, "ability": self.ABILITY_ID, "to": None, "pred": float(num)}]
