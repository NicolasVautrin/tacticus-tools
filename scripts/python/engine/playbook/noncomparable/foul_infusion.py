"""FoulInfusionPlaybook — buff self-cast NonComparable ; util = #amis-eligibles adjacents + bonus ennemi."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first


class FoulInfusionPlaybook(NonComparablePlaybook):
    """`FoulInfusionPlaybook.EvaluateNonComparable @18113c670` (id 0x40e=1038, deathPutrifier).
    Buff SELF-CAST : `FoulInfusionAbility.ExecuteBehaviour @1811dffb0` applique l'effet 0x432
    (FoulInfusion_ExtraHits) a SOI + amis Nurgle voisins (`SurroundingFriends -> UnitsWithTrait(0x7ea)
    + self`) puis attaque un ennemi adjacent aleatoire. La cible de DECISION = le CASTER (param_2).

    Structure native (mirror EvaluateNonComparable) : Bucket min = `Fix64.FromInt(2)` (cctor @18113c8f0).
    Par position balayee :
      iVar2 = Count(`GetEligibleTargetsEntities(MainTile=position)` @18111ead0)   # amis eligibles, SELF EXCLU
      if iVar2 >= 2:
          iVar3 = Count(`GetAdjacentEnemies(position)` slot 0x7e @18105af60)
          iVar2 += (iVar3 > 0)                                                    # +1 si un ennemi adjacent
      util = iVar2 ; GenerateAction(position, param_2=CASTER, Fix64(iVar2)) + AddAction
    `GetEligibleTargetsEntities` = `GetValidTargets` slot 0x41 (ability targeting = amis Nurgle, range 1)
    MOINS un predicat (retire le CASTER). MIN_UTILITY=2 -> le Bucket rejette util<2 : gate effectif =
    `#amis-eligibles-adjacents(pos) >= 2`.

    RECONCILIATION LIVE (ncEvaluate, seed 2468 s12 u91 deathPutrifier, board MC1_67) : amis eligibles
    (`abilityTargets` moins self) = {162@(3,4), 166@(3,2), 87@(1,2)} (Nurgle : les 2 Poxwalkers + le
    Blightbringer). util=2 EXACT a (3,3)=cur[162,166 adj], (2,2)[166,87 adj], (2,1)[166,87 adj] ; VIDE
    partout ailleurs (<2 amis adjacents). 7/7 positions matchent `#amis-adjacents(self exclu)` avec
    range=1 (dist hex 1). Bonus ennemi-adjacent = 0 aux 3 positions (util reste 2). Natif caste EN PLACE
    a (3,3)=origine (keep-first au tie util=2), cible = self (91).

    - util(pos) = `#{ami f in abilityTargets, f != self : is_adjacent(pos, pos(f))}` + `(count>=2 &&
      count_adjacent(pos, epos) > 0)`. Range = 1 (adjacent) : HYPOTHESE durcie par 7/7 positions live +
      ability "surrounding friends" (FLAG validateur : range non decodee du constant CustomRange). Le set
      d'amis (filtre trait Nurgle 0x7ea) vient de `abilityTargets` (natif) -> pas de trait code en dur.
    - cible = SOI (`ctx.uid`) = param_2 du GenerateAction (le caster). VALIDE LIVE (miss tgt=91=self).
    - MIN_UTILITY=2 ; sweep `_sweep_origin_first` (origine d'abord, argmax STRICT `>`) -> reste en place au
      tie (comme les heals #76). ctor @18113c960 = `NonComparablePlaybook(0x40e)` ; PRIORITY=0 (#115)."""
    ABILITY_ID = int(ActiveAbilityType.FoulInfusion)  # 1038
    MIN_UTILITY = 2.0     # cctor @18113c8f0 = Fix64.FromInt(2) -> gate effectif #amis-adj(self exclu) >= 2
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        # amis eligibles (natif : SurroundingFriends filtre trait Nurgle 0x7ea + self) MOINS le caster.
        friend_ids: list[int] = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    tid = t.get("targetId")
                    if t.get("kind") == "unit" and tid is not None and tid != ctx.uid:
                        friend_ids.append(tid)     # SELF EXCLU (predicat de GetEligibleTargetsEntities)
        if not friend_ids:
            return []
        pos_by_id = {u.get("id"): u.get("pos") for u in (ctx.units or [])}
        friend_pos = [(p["col"], p["row"]) for fid in friend_ids
                      for p in [pos_by_id.get(fid)] if p and p.get("col") is not None]
        best = None  # (T, util)
        for T in _sweep_origin_first(ctx):
            count = sum(1 for fp in friend_pos if bq.is_adjacent(T, fp, ctx.elev_by_pos))  # range 1
            if count < 2:
                continue                                  # MIN_UTILITY=2 : gate #amis-adjacents >= 2
            util = float(count)
            if bq.count_adjacent(T, ctx.epos, ctx.elev_by_pos) > 0:   # slot 0x7e GetAdjacentEnemies
                util += 1.0                               # +1 (count>=2 deja garanti)
            if best is None or util > best[1]:            # strict > : origine gagne le tie (keep-first)
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] FoulInfusion friends={friend_pos} best={best}", file=sys.stderr)
        if best is None:
            return []
        T, util = best
        # cible = SOI (param_2 = caster) ; to = origine (in-place) ou meilleure tuile de move.
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": util}]
