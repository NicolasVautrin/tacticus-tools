"""IncursionPlaybook — summon NonComparable ; cible = ennemi eligible de plus haut PV courant avec
>= 2 tuiles adjacentes libres, gate MIN dynamique = plus haut PV courant de TOUS les ennemis vivants."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class IncursionPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.IncursionPlaybook$$EvaluateNonComparable` (id 0x3fd=1021, black/Loki). Summon :
    `IncursionAbility` fait apparaitre un Bloodletter (blackSmnBloodletter) sur une tuile ADJACENTE a une
    cible ennemie (rayon 2), qui l'attaque immediatement, et continue a en invoquer (max 6) tant que la
    cible est vivante/a portee/a une tuile libre adjacente. La cible de DECISION = l'ENNEMI eligible de
    plus haut PV COURANT ayant >= 2 tuiles adjacentes libres, mais SEULEMENT si c'est l'ennemi de plus
    haut PV de tout le plateau.

    Structure native (mirror EvaluateNonComparable) : Bucket ctor min = `IdunBattle.AI.Playbook.Loki.IncursionPlaybook$$GetHighestUtility` =
    `Max(1, max_E GetStat(E, Health=5, Current))` sur `IdunBattle.AI.Playbook.BasePlaybook$$GetAllEnemies` (= PV COURANT de TOUS les
    ennemis vivants du caster) -> MIN_UTILITY DYNAMIQUE. Par position balayee, enumere
    `GetEligibleTargetsSelectable(MainTile=position)` (ennemis rayon 2) ; pour CHAQUE cible :
      GATE = `GetAdjacentTiles(cible, 1, 1, 1).Count > 1` (slot 0x4e, DAT_18327ff80 = MEME primitive que
             ScarabHive #56-t1 : tuiles adjacentes LIBRES placables ; `IdunBattle.AI.Playbook.Loki.IncursionPlaybook$$IsValidTarget` = `1 <
             count`) -> il faut >= 2 tuiles libres adjacentes a la cible.
      si passe -> `util = Fix64.FromInt(GetStat(cible, 5=Health, Current))` (= PV courant, `IdunBattle.AI.Playbook.Loki.IncursionPlaybook$$GetUtility` = GetStat(cible, 5)) ; `GenerateAction(position, cible, util)` +
                  `Bucket.AddAction` (admission util >= min, remplacement STRICT `>`).

    CONSEQUENCE du MIN = max-PV-de-TOUS-les-ennemis : util(cible) = PV(cible) <= min TOUJOURS (cible
    eligible sous-ensemble des ennemis) -> une cible ne passe l'admission Bucket que si PV(cible) ==
    max-PV GLOBAL. Donc Incursion ne FIRE que si l'ennemi de plus haut PV du plateau est ELIGIBLE (rayon 2)
    ET a >= 2 tuiles adjacentes libres, et la cible = cet ennemi. Sinon bucket vide -> fallback Comparable.

    RECONCILIATION LIVE (ncEvaluate, seed 1357 s11 u93 blackPossession, board MC1_67) : eligibles = 6
    ennemis {153(PV 3989), 83(7530), 81(9537), 139(6282), 135(6282), 85(9035)}, fromHere = {81, 139, 135}.
    util=9537 = PV(81 custoBladeChampion) aux positions (1,4)cur/(1,5)/(2,4)/(2,5), bucket VIDE ailleurs.
    81 = ennemi de plus haut PV du plateau (9537 >= MIN 9537) ET a >= 2 tuiles libres adjacentes -> admis.
    Le natif caste EN PLACE a l'origine (1,4) (81 castable fromHere, cur=True keep-first). Le moteur ratait
    car 1021 absent du registre -> retombait sur l'attaque normale 69 (mauvaise cible 153).

    - util(cible) = `scene.hp(cible)` = `GetStat(cible, Health=5, Current)` = PV COURANT.
    - MIN_UTILITY DYNAMIQUE = `max(1, max_E scene.hp(E))` sur `ctx.enemies` (= GetAllEnemies).
    - gate par cible = `adjacent_addable_count(pos-cible) >= 2` (primitive ScarabHive : GetAdjacentTiles ∩
      CanAddUnit, occupation = epos U fpos U origine). cibles sans >= 2 tuiles libres SAUTEES.
    - cible = argmax PV parmi les eligibles passant le gate, keep-first ; emise SSI PV >= MIN (== max global).
    - position = `_first_cast_pos` (origine-preference #76). PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170). IdunBattle.AI.Playbook.Loki.IncursionPlaybook$$.ctor =
      `NonComparablePlaybook(0x3fd)`. ShouldEvaluate = base IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate (GetUseProbability=1 -> True)."""
    ABILITY_ID = int(ActiveAbilityType.Incursion)  # 1021
    MIN_UTILITY = 0.0     # DYNAMIQUE (GetHighestUtility) -> calcule dans generate_candidates
    PRIORITY = 0
    _MIN_FREE_ADJ = 2     # gate `GetAdjacentTiles(cible,1,1,1).Count > 1` (IdunBattle.AI.Playbook.Loki.IncursionPlaybook$$IsValidTarget)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None or ctx.scene is None:
            return []
        # MIN dynamique = Max(1, max PV COURANT sur TOUS les ennemis vivants) (GetHighestUtility).
        min_util = 1.0
        for e in (ctx.enemies or []):
            eid = e.get("id")
            if eid is None:
                continue
            hp = ctx.scene.hp(eid)
            if hp is not None and float(hp) > min_util:
                min_util = float(hp)
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
        occupied = bq.occupied_positions(ctx)     # #969-r3 : PAR PIED (`TileContentComponent`)
        best = None  # (eid, hp)
        for eid in elig:
            tp = self._pos_of(ctx, eid)
            if tp is None:
                continue
            # gate : >= 2 tuiles adjacentes LIBRES a la cible (GetAdjacentTiles(cible,1,1,1).Count > 1).
            free = bq.adjacent_addable_count(tp, ctx.neigh_by_pos, ctx.walkable_by_pos,
                                             occupied, ctx.elev_by_pos)
            if free < self._MIN_FREE_ADJ:
                continue
            hp = float(ctx.scene.hp(eid) or 0)
            if best is None or hp > best[1]:        # argmax STRICT (keep-first au tie)
                best = (eid, hp)
        if best is None:
            return []
        eid, hp = best
        if hp < min_util:                            # admission Bucket : util >= min (== max-PV global)
            return []
        to = self._first_cast_pos(ctx, eid)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] Incursion elig={elig} tgt={eid} hp={hp} min={min_util} to={to}",
                  file=sys.stderr)
        return [{"target": eid, "ability": self.ABILITY_ID, "to": to, "pred": hp}]

    @staticmethod
    def _pos_of(ctx: NCContext, uid: int):
        u = next((x for x in (ctx.units or []) if x.get("id") == uid), None)
        p = (u or {}).get("pos") if u else None
        if p and p.get("col") is not None:
            return (p["col"], p["row"])
        return None

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
