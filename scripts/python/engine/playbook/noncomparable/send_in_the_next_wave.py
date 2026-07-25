"""SendInTheNextWavePlaybook — summon NonComparable ; cible = ennemi eligible de plus haute Attack,
gate MIN dynamique = plus haute Attack de TOUS les ennemis vivants (ne fire que si le plus dangereux
est ciblable)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class SendInTheNextWavePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.SendInTheNextWavePlaybook$$EvaluateNonComparable` (id 0x3f8=1016, astra/Loki). Summon :
    `SendInTheNextWaveAbility` fait apparaitre 2+ Cadian Guardsmen (astraSmnGuardsman) dans un rayon 2
    d'une cible ennemie, qui FONT FEU sur elle immediatement. La cible de DECISION = l'ENNEMI eligible de
    plus HAUTE Attack, mais SEULEMENT si c'est l'ennemi de plus haute Attack de TOUT le plateau.

    Structure native (mirror EvaluateNonComparable) : Bucket ctor min = `IdunBattle.AI.Playbook.Loki.SendInTheNextWavePlaybook$$GetHighestEnemyAttackStat` = `Max(1, max_E GetStat(E, Attack=0, Current))` sur `IdunBattle.AI.Playbook.BasePlaybook$$GetAllEnemies` (slot 0x88
    GetAllAliveUnits + filtre IsEnemy = TOUS les ennemis vivants du caster) -> MIN_UTILITY DYNAMIQUE. Par
    position balayee, enumere `GetEligibleTargetsSelectable(MainTile=position)` (= ennemis ciblables,
    rayon 2) ; pour CHAQUE cible -> `util = Fix64.FromInt(GetStat(cible, 0=Attack, Current))` ;
    `GenerateAction(position, cible, util)` + `Bucket.AddAction` (admission util >= min, remplacement
    STRICT `>`).

    CONSEQUENCE du MIN = max-Attack-de-TOUS-les-ennemis : util(cible) = Attack(cible) <= min TOUJOURS
    (cible eligible sous-ensemble des ennemis) -> une cible ne passe l'admission Bucket que si
    Attack(cible) == max-Attack GLOBAL. Donc SendInTheNextWave ne FIRE que si l'ennemi de plus haute
    Attack de tout le plateau est ELIGIBLE (rayon 2), et la cible = cet ennemi. Sinon bucket vide ->
    fallback Comparable (attaque normale).

    RECONCILIATION LIVE (ncEvaluate, seed 1357 s9 u83 astraYarrick, board MC1_67) : eligible = {95
    custoAtlacoya (Attack 3011)}, unique cible. util=3011 aux positions (3,6)/(2,6) (95 castable rayon 2),
    bucket VIDE partout ailleurs. 95 = ennemi de plus haute Attack du plateau (util 3011 >= MIN 3011 ->
    admis). Le natif MOVE->(3,6) (1re position du tie util 3011 en ordre movable) puis caste 1016 sur 95.
    Le moteur ratait car 1016 absent du registre -> retombait sur l'attaque normale 69 (meme cible 95).

    - util(cible) = `scene.attack_current(cible)` = `GetStat(cible, Attack=0, Current)`.
    - MIN_UTILITY DYNAMIQUE = `max(1, max_E scene.attack_current(E))` sur `ctx.enemies` (= GetAllEnemies).
    - cible = argmax Attack parmi les ennemis eligibles (`abilityTargets`), keep-first au tie ; emise SSI
      son Attack >= MIN (== max global). Sinon aucun candidat.
    - position = `_first_cast_pos` (origine-preference #76 : cast en place si castable, sinon 1re tuile de
      move d'ou la cible est castable). PRIORITY=0 (#115). IdunBattle.AI.Playbook.Loki.SendInTheNextWavePlaybook$$.ctor = `NonComparablePlaybook(0x3f8)`.
    - ShouldEvaluate = base IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate (GetUseProbability=Fix64(1) -> True constant ; pas d'override)."""
    ABILITY_ID = int(ActiveAbilityType.SendInTheNextWave)  # 1016
    MIN_UTILITY = 0.0     # DYNAMIQUE (GetHighestEnemyAttackStat) -> calcule dans generate_candidates
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None or ctx.scene is None:
            return []
        # MIN dynamique = Max(1, max Attack COURANTE sur TOUS les ennemis vivants) (GetHighestEnemyAttackStat).
        min_util = 1.0
        for e in (ctx.enemies or []):
            eid = e.get("id")
            if eid is None:
                continue
            atk = float(ctx.scene.attack_current(eid))
            if atk > min_util:
                min_util = atk
        # cibles ENNEMIES eligibles (GetEligibleTargetsSelectable) — ordre natif, dedup keep-first.
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        elig: list[int] = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        elig.append(t["targetId"])
        elig = list(dict.fromkeys(elig))
        if not elig:
            return []
        best = None  # (eid, attack)
        for eid in elig:
            atk = float(ctx.scene.attack_current(eid))
            if best is None or atk > best[1]:      # argmax STRICT (keep-first au tie)
                best = (eid, atk)
        eid, atk = best
        if atk < min_util:                          # admission Bucket : util >= min (== max-Attack global)
            return []
        to = self._first_cast_pos(ctx, eid)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] SendInTheNextWave elig={elig} tgt={eid} atk={atk} "
                  f"min={min_util} to={to}", file=sys.stderr)
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
