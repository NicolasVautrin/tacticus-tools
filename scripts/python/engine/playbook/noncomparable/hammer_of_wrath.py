"""HammerOfWrathPlaybook — charge NonComparable (_PlanTarget), utilite = degat interne + bonus."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, _traits


def _enemy_killed_by_normal_attack(ctx: NCContext) -> bool:
    """`BasePlaybook.EnemyCouldBeKilledWithNormalAttack(killSure=1) @18111dae0` : l'attaque NORMALE du
    caster WillBeKill (dmgMin >= PV) un ennemi atteignable ? (`GetAllNormalAttackTargets` -> PredictAttack
    (0x21) -> get_WillBeKill). Porté via le plan : evals de l'attaque NORMALE, une cible rankée sure-kill
    (`dmgMin >= hp_cur`). Sert le gate ShouldEvaluate @181142320 de Hammer (`!EnemyCouldBeKilled...`)."""
    me = next((u for u in (ctx.units or []) if u.get("id") == ctx.uid), None)
    if me is None:
        return False
    normal_ids = {a.get("id") for a in (me.get("abilities") or []) if a.get("kind") == "normal"}
    if not normal_ids:
        return False
    for ev in (ctx.plan.get("evals") or []):
        if ev.get("abilityId") not in normal_ids:
            continue
        hp = ctx.hp_cur_by_id.get(ev.get("targetId"))
        if hp is None:
            continue
        for rk in (ev.get("ranked") or []):
            dmin = rk.get("dmgMin")
            if dmin is not None and dmin >= hp:      # WillBeKill (sure-kill : dmgMin >= PV courants)
                return True
    return False


class HammerOfWrathPlaybook(_PlanTargetPlaybook):
    """`HammerOfWrathPlaybook.EvaluateNonComparable @181141680` (id 0x481=1153, bloodIntercessor). Charge
    NonComparable : utilité de DÉCISION = Σ dégât INTERNE (cible + adjacents) + bonus trait, SANS émettre de
    ProbableDamageEvent affiché (dégât exclu de la prédiction #109). Le caster CHARGE la cible (move + attaque).

    - utilité(cible) = `+100·HasTrait(cible, 0x3eb=1003=Overwatch)` + `CalcUtilFromDamageEvent(PRIMARY)`
      + `Σ_{adj ∈ SelectUniqueUnits(GetAdjacentTargets,3)} CalcUtilFromDamageEvent(SECONDARY)`
      + `5·Σ_{n ∈ GetAdjacentTiles(cible)} CanAddUnit(n)` (#116, PORTÉ). Chemin dégât =
      `make_hammer_wrath_events` (primary minDmg/nrOfHits/Power ; secondary minDmg_2/nrOfHits_2/Physical sur
      ennemis adjacents à la cible), Σ `calculate_utility_from_damage_event`.
    - +5·CanAddUnit (#116, RE re-expert) : `+5` par voisin ring-1 de la CIBLE où une unité peut être placée.
      Le natif fait `IBattleQuery.slot0x4e(cible)` = `GetAdjacentTiles @18105b660` (prouvé slot 78 via
      `MovementQuery.IsAdjacent @18109c470` + slot-map RecordedSimulationRequestsBattleQuery ; PAS GetTilesBehind
      = slot 0x53) puis `TileExtensions.CanAddUnit @180ec4c60` (tuile walkable/non-wall ET VIDE). Biais du natif
      vers les cibles entourées d'ESPACE LIBRE (place pour le knock-back de la charge). Le terme dépend de la
      CIBLE (pas de la tuile de charge) -> influe l'ARGMAX de cible. Porté via `bq.adjacent_addable_count`
      (voisins boardGraph, porte |Δelev|<2 comme #45, gate `can_add_unit`). FLAG : co-location trait 0x1b +
      tuiles walkable-mais-réservées non modélisées (borne INF, cf. `can_add_unit`).
    - MIN_UTILITY=1 (cctor @181142340) ; ctor @1811423b0 = `NonComparablePlaybook(0x481)` -> 1er arg =
      ability_id, PRIORITY=0 (cf. #115). GenerateAction(position, cible, util) + AddAction (argmax via base).
    - ShouldEvaluate @181142320 = `!EnemyCouldBeKilledWithNormalAttack(killSure)` : le natif N'ÉVALUE PAS
      Hammer si l'attaque normale du caster sure-kill déjà un ennemi (économise la charge). Porté ci-dessous.
    - Trait 1003 = `Overwatch` (enum UnitTrait, dump.cs gqfc5mff6c:863979 ; PAS BigTarget=1017).
    Éligibilité + tuile de charge = plan natif (evals rankées 1153), comme BloodyFury/Vexilla (_PlanTargetPlaybook)."""
    ABILITY_ID = int(ActiveAbilityType.HammerOfWrath)  # 1153
    MIN_UTILITY = 1.0     # cctor @181142340 = Fix64(1)
    PRIORITY = 0
    _OVERWATCH = "Overwatch"   # trait 0x3eb=1003 (enum UnitTrait) -> +100 sur une cible en Overwatch

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 de la vtable -> `ShouldEvaluate @181142320` = `!EnemyWillBeKilledWithNormalAttack`
        (relogé de generate_candidates vers l'étage natif du gate — le générateur le teste AVANT
        tout sweep, #46)."""
        if _enemy_killed_by_normal_attack(ctx):
            if ctx.debug:
                import sys
                print(f"    [dbg NC u{ctx.uid}] Hammer SKIP (normal sure-kill)", file=sys.stderr)
            return False
        return True

    def evaluate_non_comparable(self, tile, target, ctx):
        if tile is None or ctx.scene is None:
            return None
        from engine.playbook.prediction import make_hammer_wrath_events
        from engine.playbook.probable_damage_event import calculate_utility_from_damage_event
        events = make_hammer_wrath_events(ctx.scene, ctx.uid, target, tile)
        if not events:
            return None
        u = sum(calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(ev.target))
                for ev in events)
        # +100 si la CIBLE a le trait Overwatch (HasTrait(target, 0x3eb) @181141680).
        vis = next((x.get("visualId") for x in (ctx.obs_units or []) if x.get("squadId") == target), None)
        if self._OVERWATCH in _traits(vis):
            u += 100.0
        disp = self._displacement_bonus(target, ctx)   # +5 par voisin ring-1 CanAddUnit de la cible (#116)
        u += disp
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] Hammer tgt={target} tile={tile} events={len(events)} "
                  f"disp={disp:.0f} u={u:.1f}", file=sys.stderr)
        return u

    @staticmethod
    def _displacement_bonus(target, ctx: NCContext) -> float:
        """`+5 · Σ_{n ∈ GetAdjacentTiles(cible)} CanAddUnit(n)` (#116). Voisins ring-1 de la CIBLE
        (`IBattleQuery.GetAdjacentTiles` slot 0x4e @18105b660) où une unité peut être placée
        (`TileExtensions.CanAddUnit @180ec4c60`). Occupation LIVE = TOUTES les unités vivantes
        (epos ∪ fpos ∪ origine, FRAÎCHE). Cible introuvable / sans position -> 0."""
        tu = next((u for u in (ctx.units or []) if u.get("id") == target), None)
        p = (tu or {}).get("pos") if tu else None
        if not p or p.get("col") is None:
            return 0.0
        occupied = set(ctx.epos or []) | set(ctx.fpos or [])
        if ctx.origin is not None:
            occupied.add(ctx.origin)
        return 5.0 * bq.adjacent_addable_count((p["col"], p["row"]), ctx.neigh_by_pos,
                                               ctx.walkable_by_pos, occupied, ctx.elev_by_pos)
