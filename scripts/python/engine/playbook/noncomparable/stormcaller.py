"""StormcallerPlaybook — zone de glace NonComparable (utilite = #unites prises dans la zone)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, _will_normal_attack_kill


class StormcallerPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.StormcallerPlaybook$$EvaluateNonComparable` (id 0x459=1113, spaceStormcaller).

    NonComparable : le DEGAT n'entre PAS dans l'utilite (le playbook n'a AUCUN `Make*Predictions` —
    c'est le reframe #34). Le natif compte les UNITES prises dans la zone de glace :

    - cibles = `BasePlaybook.GetEligibleTargetsSelectable(ctx, position.MainTile)` (ennemis a portee 3).
    - GATE par cible : `WillNormalAttackKill(target, position.MainTile) -> continue` — le natif SAUTE
      une cible que l'attaque normale tue deja a coup sur (il ne gaspille pas Stormcaller dessus).
    - utilite = `IdunBattle.AI.Playbook.Loki.StormcallerPlaybook$$GetTargetUtility` : part de `Fix64.Zero` (champ statique Fix64 +0x28) puis
      `+1` (champ statique [1] du IdunBattle.AI.Playbook.Loki.StormcallerPlaybook$$.cctor = `Fix64.FromInt(1)`) PAR TUILE de la zone qui PORTE
      UNE UNITE (`UnitExtensions.GetUnit(tile, state) != null` — AUCUN filtre d'equipe : les allies ET
      le caster comptent s'ils sont dans la zone).
    - zone = `IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$GetAddIceTiles` = `AdjacentTiles(Target) + Target` = la tuile
      de la cible + son ring-1. `AdjacentTiles` passe par `IterateAdjacentTiles` -> porte d'elevation
      `|delta elev| < 2` (cf. `bq.is_adjacent`).
    - `MIN_UTILITY` = champ statique [0] du cctor = `Fix64.FromInt(1)` ; `PRIORITY`=0 (#115). Le gate
      MIN est structurellement toujours passe (la cible vivante est elle-meme dans la zone) -> le SEUL
      gate discriminant est `WillNormalAttackKill`.

    Enumeration cible + tuile de cast = plan natif rank (`_PlanTargetPlaybook`, comme BloodyFury /
    Vexilla / HammerOfWrath) : Stormcaller a une config de degat, donc ses paires (cible, tuiles) sont
    presentes dans `attackPlans` meme si son utilite de DECISION les ignore."""
    ABILITY_ID = int(ActiveAbilityType.Stormcaller)  # 1113
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.StormcallerPlaybook$$.cctor champ [0] = Fix64(1)
    PRIORITY = 0

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        tu = next((u for u in (ctx.units or []) if u.get("id") == target), None)
        p = (tu or {}).get("pos") if tu else None
        if not p or p.get("col") is None:
            return None
        tpos = (p["col"], p["row"])
        if _will_normal_attack_kill(ctx, target, tile):
            return None      # `continue` natif : l'attaque normale sure-kill deja cette cible
        # GetTargetUtility : +1 par tuile de la zone (cible + ring-1) portant une unite VIVANTE.
        n = 0
        for u in (ctx.units or []):
            if u.get("alive") is False:
                continue
            q = u.get("pos")
            if not q or q.get("col") is None:
                continue
            upos = (q["col"], q["row"])
            if upos == tpos or bq.is_adjacent(tpos, upos, ctx.elev_by_pos):
                n += 1
        if ctx.debug:
            import sys
            print(f"    [dbg Stormcaller u{ctx.uid}] tgt={target}@{tpos} tile={tile} "
                  f"unitsInIce={n}", file=sys.stderr)
        return float(n)
