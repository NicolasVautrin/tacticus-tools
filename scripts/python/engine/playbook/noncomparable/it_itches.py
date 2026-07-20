"""ItItchesPlaybook — poussee NonComparable (utilite = #ennemis affectes par la poussee)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait, has_any_trait
from engine.runner.operations.displace import _dir_index, _step   # geometrie FindTileToPush partagee

from ._base import NCContext, NonComparablePlaybook, _traits, _sweep_origin_first

# `IsDisplaceable @180ed8140` : traits BLOQUANTS lisibles en gameconfig.
_NOT_DISPLACEABLE = (UnitTrait.Immovable,   # 0x11 = 17
                     UnitTrait.Hulking,     # 3
                     UnitTrait.BigTarget)   # 0x3f9 = 1017


class ItItchesPlaybook(NonComparablePlaybook):
    """`ItItchesPlaybook.EvaluateNonComparable @181146c50` (id 0x461=1121, tyranParasiteOfMortrex).

    NonComparable a utilite ENTIERE (aucun `Make*Predictions` — reframe #34) : la Parasite pousse un
    ennemi adjacent ET les ennemis adjacents A LA FOIS a la cible et a elle-meme, puis fait apparaitre un
    Ripper Swarm dans chaque hex libere. L'utilite = COMBIEN d'ennemis la poussee affecte.

    - cibles = `GetEligibleTargetsSelectable(ctx, position)` (ennemis adjacents).
    - GATE 1 : `UnitExtensions.IsDisplaceable(target) == false -> continue` (@180ed8140 : unite vivante,
      SANS `Immovable(17)` ni `Hulking(3)` ni `BigTarget(0x3f9=1017)`, et sans le FLAG runtime 0x19).
    - GATE 2 (`CanBePushed` inline, cf. @181146aa0) : `IBattleQuery` slot 0x4d `(casterTile, target)` ->
      liste de tuiles, `FilterInPlace(<predicat du playbook>)`, `Count > 0` = il existe une destination de
      poussee. Porte par la GEOMETRIE REELLEMENT EXECUTEE (`DisplaceUnitOperation` /
      `FindTileToPush @180e695e0` : 1 pas dans la direction caster->cible, tuile walkable et libre) —
      c'est le mirror defendable ; l'identite exacte du slot 0x4d n'est PAS tranchee (ce n'est ni
      `GetAdjacentTiles`=0x4e ni `GetTilesBehind`=0x53, qui prennent d'autres arites) -> FLAG.
    - utilite = `Fix64.FromInt(Count(GetTargetUnits(cible)))` ou
      `ItItchesAbility.GetTargetUnits @1811ec5e0` = `Enemies(Target + AdjacentTilesIntersection(caster,
      target))` = la cible ELLE-MEME + les ennemis adjacents A LA FOIS a la cible et au caster.
    - `MIN_UTILITY` = cctor @181147830 = `Fix64.FromInt(1)` (toujours passe des que la cible est
      poussable : elle compte pour 1) ; `PRIORITY`=0 (#115). `GenerateAction(position, cible, util)`.

    Ecarts assumes : (1) le FLAG runtime `HasFlag(unit, 0x19)` d'`IsDisplaceable` n'est pas lisible
    offline (enum de flags d'entite, distinct des traits gameconfig) -> non teste ; (2) l'eligibilite
    par-position est reconstituee en filtrant l'union `abilityTargets` par adjacence a la position
    balayee ; (3) `GetUseProbability @1811477b0` = `Fix64.FromIntFraction(GetMaxNumUnitsAffected, 3)`
    (porte ALEATOIRE : ~n/3 de chances d'utiliser l'ability) — non modelisee (moteur deterministe),
    meme statut que ScarabSummon/BlackRage."""
    ABILITY_ID = int(ActiveAbilityType.ItItches)  # 1121
    MIN_UTILITY = 1.0     # cctor @181147830 = Fix64(1)
    PRIORITY = 0

    def _eligible_targets(self, ctx: NCContext) -> list[int]:
        """`GetEligibleTargetsSelectable` (unites) : union `abilityTargets`, ordre preserve."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        out: list[int] = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        out.append(t["targetId"])
        return list(dict.fromkeys(out))

    @staticmethod
    def _is_displaceable(ctx: NCContext, unit: dict) -> bool:
        """`UnitExtensions.IsDisplaceable @180ed8140` (part lisible offline : vivante + traits)."""
        if unit is None or unit.get("alive") is False:
            return False
        return not has_any_trait(_traits(unit.get("visualId")), _NOT_DISPLACEABLE)

    @staticmethod
    def _can_be_pushed(ctx: NCContext, pusher_pos: tuple, tpos: tuple) -> bool:
        """`CanBePushed @181146aa0` : existe-t-il une destination de poussee ? Mirror de la geometrie
        EXECUTEE (`FindTileToPush`) : 1 pas dans la direction `pusher_pos -> tpos`, tuile connue du
        board, walkable et LIBRE. `walkable_by_pos` absent -> on se rabat sur les tuiles connues
        (`elev_by_pos`) pour ne pas gater a l'aveugle."""
        d = _dir_index(pusher_pos[0], pusher_pos[1], tpos[0], tpos[1])
        if d is None:
            return False           # pousseur non adjacent -> pas de direction unitaire
        dest = _step(tpos[0], tpos[1], d)
        if ctx.walkable_by_pos:
            if not ctx.walkable_by_pos.get(dest):
                return False
        elif ctx.elev_by_pos is not None and dest not in ctx.elev_by_pos:
            return False           # hors board
        occupied = set(ctx.epos or []) | set(ctx.fpos or []) | {pusher_pos}
        return dest not in occupied

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        tgt_ids = self._eligible_targets(ctx)
        if not tgt_ids:
            return []
        by_id = {u.get("id"): u for u in (ctx.units or [])}
        best = None      # (util, position, target)
        for P in _sweep_origin_first(ctx):
            for tid in tgt_ids:
                tu = by_id.get(tid)
                p = (tu or {}).get("pos") if tu else None
                if not p or p.get("col") is None:
                    continue
                tpos = (p["col"], p["row"])
                if not bq.is_adjacent(P, tpos, ctx.elev_by_pos):
                    continue                        # cible non adjacente DEPUIS cette position
                if not self._is_displaceable(ctx, tu):
                    continue                        # GATE 1
                if not self._can_be_pushed(ctx, P, tpos):
                    continue                        # GATE 2
                # GetTargetUnits : la cible + les ennemis adjacents A LA FOIS a la cible et au caster.
                util = 1.0 + sum(1.0 for e in (ctx.epos or [])
                                 if e != tpos
                                 and bq.is_adjacent(tpos, e, ctx.elev_by_pos)
                                 and bq.is_adjacent(P, e, ctx.elev_by_pos))
                if best is None or util > best[0]:  # Bucket.AddAction : remplacement STRICT `>`
                    best = (util, P, tid)
        if best is None or best[0] < self.MIN_UTILITY:
            return []
        util, P, tid = best
        if ctx.debug:
            import sys
            print(f"    [dbg ItItches u{ctx.uid}] pos={P} tgt={tid} util={util}", file=sys.stderr)
        return [{"target": tid, "ability": self.ABILITY_ID,
                 "to": (P if P != ctx.origin else None), "pred": util}]
