"""HolyDuelPlaybook — defi NonComparable (cible ennemi de plus haute Attack), gate !MightBeKill."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


def _enemy_might_be_killed_by_normal_attack(ctx: NCContext) -> bool:
    """`IdunBattle.AI.Playbook.BasePlaybook$$EnemyMightBeKilledWithNormalAttack` = `IdunBattle.AI.Playbook.BasePlaybook$$EnemyCouldBeKilledWithNormalAttack(
    killSure=0)` : l'attaque NORMALE du caster POURRAIT-elle tuer (`get_MightBeKill` =
    rawMax >= PV, kill POSSIBLE) un ennemi atteignable ? DISTINCT de Hammer/Stormcaller qui utilisent
    `WillBeKill` (killSure=1, dmgMin >= PV). Porte via le plan : evals de l'attaque NORMALE, une tuile
    rankee avec `kill` (= natif `hp <= mightKillDmg`, projection.ts) ; fallback `dmgMax >= hp_cur` si le
    flag `kill` est absent. Sert le gate IdunBattle.AI.Playbook.Loki.HolyDuelPlaybook$$ShouldEvaluate de HolyDuel (`!EnemyMightBeKilled...`)."""
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
        for rk in (ev.get("ranked") or []):
            if rk.get("kill"):                    # MightBeKill natif (hp <= mightKillDmg)
                return True
            dmax = rk.get("dmgMax")               # fallback : rawMax >= PV (flag kill absent)
            if dmax is not None and hp is not None and dmax >= hp:
                return True
    return False


class HolyDuelPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.HolyDuelPlaybook$$EvaluateNonComparable` (id 0x41a=1050, templChampion). Defi
    NonComparable : `IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` pose un bond (AddBondEffect 0x443)
    entre caster et cible + effets Taunt/DmgReduction/ExtraDmg, puis `UseActiveAbility` (attaque). La
    cible = l'ENNEMI eligible de plus HAUTE Attack.

    Structure native (mirror EvaluateNonComparable) : Bucket ctor 2-arg (min defaut, PAS de cctor -> 0).
    Par position balayee, enumere `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable(MainTile=position) (= ennemis
    valides slot 0x41) ; pour CHAQUE cible -> util = `Fix64.FromInt(GetStat(cible, 0=Attack))` ;
    `GenerateAction(position, cible, util)` + `Bucket.AddAction` (argmax STRICT, keep-first au tie). Le
    Bucket garde l'ennemi de plus haute Attack (utilite POSITION-INDEPENDANTE : depend de la cible seule).

    IdunBattle.AI.Playbook.Loki.HolyDuelPlaybook$$ShouldEvaluate = `!EnemyMightBeKilledWithNormalAttack` : le natif N'EVALUE PAS HolyDuel si
    l'attaque normale du caster POURRAIT tuer un ennemi (prefere le kill au defi). PORTE ci-dessous
    (MightBeKill = kill possible, distinct du WillBeKill de Hammer).

    RECONCILIATION LIVE (ncEvaluate, seed 1357 s12 u87 templChampion, board MC1_67) : eligibles =
    {85 tyranParasite (Attack 4518), 135 tyranNpc2RipperSwarm}. util=4518 IDENTIQUE a toute position
    non-vide, cible CONSTANTE = 85 (max Attack) ; ShouldEvaluate True (aucun MightBeKill au normal).
    Natif caste EN PLACE a (2,2)=origine (85 eligible in-place, keep-first).

    - util(cible) = `scene.attack_current(cible)` = `GetStat(cible, Attack=0, Current)`. Cible = argmax
      Attack parmi les ennemis eligibles (`abilityTargets`), keep-first au tie.
    - MIN_UTILITY=0 (IdunBattle.AI.Playbook.Loki.HolyDuelPlaybook$$.ctor = `NonComparablePlaybook(0x41a)` SANS min ; Attack > 0 toujours admise).
    - position : util POSITION-INDEPENDANTE -> 1re tuile d'ou la cible est castable (origine-preference
      #76 via `cast_from_tiles`). VALIDE LIVE (cast in-place a origine). PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170)."""
    ABILITY_ID = int(ActiveAbilityType.HolyDuel)  # 1050
    MIN_UTILITY = 0.0     # ctor NonComparablePlaybook(0x41a) sans min -> 0 ; util = Attack (toujours > 0)
    PRIORITY = 0

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 vtable -> `IdunBattle.AI.Playbook.Loki.HolyDuelPlaybook$$ShouldEvaluate` = `!EnemyMightBeKilledWithNormalAttack` : HolyDuel
        SAUTE si l'attaque normale POURRAIT tuer un ennemi (le fallback Comparable prend le kill)."""
        if _enemy_might_be_killed_by_normal_attack(ctx):
            if ctx.debug:
                import sys
                print(f"    [dbg NC u{ctx.uid}] HolyDuel SKIP (normal might-kill)", file=sys.stderr)
            return False
        return True

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        enemy_ids: list[int] = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        enemy_ids.append(t["targetId"])
        # dedup en gardant l'ordre (keep-first au tie).
        enemy_ids = list(dict.fromkeys(enemy_ids))
        if not enemy_ids:
            return []
        best = None  # (enemy_id, attack)
        for eid in enemy_ids:
            atk = float(ctx.scene.attack_current(eid)) if ctx.scene is not None else 0.0
            if best is None or atk > best[1]:      # argmax STRICT (keep-first au tie)
                best = (eid, atk)
        eid, atk = best
        to = self._first_cast_pos(ctx, eid)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] HolyDuel eligible={enemy_ids} tgt={eid} atk={atk} to={to}",
                  file=sys.stderr)
        return [{"target": eid, "ability": self.ABILITY_ID, "to": to, "pred": atk}]

    def _first_cast_pos(self, ctx: NCContext, target: int):
        """Origine-preference #76 : cast EN PLACE si la cible est castable a l'origine (`currentValid`),
        sinon 1re tuile de move legale (`cast_from_tiles`, ordre movable). Seam absente -> None."""
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
