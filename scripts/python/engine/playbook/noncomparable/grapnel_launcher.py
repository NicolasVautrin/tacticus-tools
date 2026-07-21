"""GrapnelLauncherPlaybook — reposition NonComparable (utilite plate 1 par cible eligible)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class GrapnelLauncherPlaybook(NonComparablePlaybook):
    """`GrapnelLauncherPlaybook.EvaluateNonComparable @18113f300` (id 0x442=1090, Loki/tauCrisis
    family). Ability de reposition/grapin (`GrapnelLauncherAbility.ExecuteBehaviour @1811e29c0`).
    Le playbook de DECISION est le PLUS SIMPLE : utilite CONSTANTE 1 par cible eligible, AUCUN gate
    de formule (aucun ShouldEvaluate override -> base True).

    Structure native (mirror EvaluateNonComparable) : Bucket ctor 3-arg avec min = Nullable(Fix64(1))
    (cctor @18113f600 pose `**(DAT_183257d10+0xb8)=Fix64(1)`, relu dans la leaf -> MIN_UTILITY=1). Par
    position balayee, enumere `GetEligibleTargetsSelectable(MainTile=position)` @18111f0d0 ; pour CHAQUE
    cible eligible -> `util = Fix64.FromInt(1)` CONSTANTE, `GenerateAction(position, cible, util)` +
    `Bucket.AddAction` (argmax STRICT `>`, keep-first au tie). Aucune arithmetique : util=1 partout.

    RECONCILIATION LIVE (ncEvaluate, seed 54321 s13 u87... en fait CASTER = spaceHound, board MC1_67) :
    TOUTES les positions -> util=1 ; la cible varie par position (GetEligibleTargetsSelectable depend de
    la position). Le natif caste EN PLACE a l'ORIGINE (3,2)=cur sur u81 (bloodIntercessor) : l'ORIGINE
    est evaluee la PREMIERE dans le sweep du generateur et gagne le tie (keep-first, util const). Confirme
    par les 3 castes en place de cette tranche (Grapnel/DarkTalon origine=util max) : le sweep NC est
    ORIGINE-FIRST + remplacement strict `>` -> l'origine ne perd que sur util STRICTEMENT superieure.
    Le moteur ratait car 1090 absent du registre -> retombait sur l'attaque normale 69 (meme cible u81).

    - utilite = 1.0 CONSTANTE par cible eligible (Fix64.FromInt(1) @18113f300). MIN_UTILITY=1 (cctor) ->
      toute cible admise. Aucun terme position-dependant.
    - cible = 1er ENNEMI eligible castable DEPUIS L'ORIGINE (`fromHere` d'abro`abilityTargets`) ; util
      const + origine-first -> keep-first garde la 1re cible de l'origine (u81 live). Origine-preference
      (cast en place, to=None) via `_first_cast_pos` : si aucune cible fromHere, 1re tuile de move.
    - ctor @18113f670 = `NonComparablePlaybook(0x442)` -> 1er arg=ability_id ; PRIORITY=0 (defaut #115).
    - ShouldEvaluate = base @18111fb70 (GetUseProbability=Fix64(1) -> True constant ; pas d'override)."""
    ABILITY_ID = int(ActiveAbilityType.GrapnelLauncher)  # 1090
    MIN_UTILITY = 1.0     # cctor @18113f600 = Fix64(1) ; util 1 constante toujours admise
    PRIORITY = 0
    _UTIL = 1.0           # Fix64.FromInt(1) @18113f300 = utilite constante par cible eligible

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        # cibles ENNEMIES eligibles DEPUIS L'ORIGINE d'abord (fromHere) : origine-first + util const
        # -> keep-first garde la 1re cible fromHere (cast en place). Fallback : cibles avec move.
        fromhere: list[int] = []
        allelig: list[int] = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        fromhere.append(t["targetId"])
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        allelig.append(t["targetId"])
        # dedup en gardant l'ordre (keep-first au tie d'util constante)
        fromhere = list(dict.fromkeys(fromhere))
        allelig = list(dict.fromkeys(allelig))
        if fromhere:
            tgt, to = fromhere[0], None     # cast EN PLACE a l'origine (keep-first, origine-first)
        elif allelig:
            tgt = allelig[0]
            to = self._first_cast_pos(ctx, tgt)
        else:
            return []
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] GrapnelLauncher tgt={tgt} to={to} "
                  f"(fromHere={fromhere[:3]})", file=sys.stderr)
        return [{"target": tgt, "ability": self.ABILITY_ID, "to": to, "pred": self._UTIL}]

    def _first_cast_pos(self, ctx: NCContext, target: int):
        """Origine-preference (#76) : cast EN PLACE si castable a l'origine, sinon 1re tuile de move
        legale (`cast_from_tiles`, ordre movable). Seam absente -> None (cast en place)."""
        if ctx.cast_from_tiles is None:
            return None
        try:
            cf = ctx.cast_from_tiles(ctx.uid, target, self.ABILITY_ID) or {}
        except Exception:
            return None
        if cf.get("currentValid"):
            return None
        posset = {(t.get("col"), t.get("row")) for t in (cf.get("moveTiles") or [])
                  if t.get("col") is not None}
        for P in (ctx.reach_nc or []):
            if P in posset:
                return None if P == ctx.origin else P
        return None
