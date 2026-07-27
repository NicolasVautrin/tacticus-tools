"""CordClawPlaybook — attaque NonComparable ; util = #ennemis adjacents a la tuile d'attaque, cible = 1er
ennemi eligible en ordre voisins natif de la tuile gagnante."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class CordClawPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.CordClawPlaybook$$EvaluateNonComparable` (id 0x462=1122, admecRuststalker/Exitor-Rho).
    Attaque melee NonComparable (`IdunBattleLogic.Entities.Abilities.Active.Loki.CordClawAbility$$ExecuteBehaviour` = AttackWithAttackDamage 4x
    + effet 0x4e2 AdditionalHits 2x jusqu'a la fin du prochain tour). L'utilite de DECISION = le nombre
    d'ennemis ADJACENTS a la TUILE D'ATTAQUE du caster (PAS a la cible) -> le caster attaque depuis la
    position la plus entouree d'ennemis (valeur max pour ses attaques bonus futures).

    Structure native (mirror EvaluateNonComparable) : pour chaque cible eligible
    (`GetEligibleTargetsSelectable(MainTile=position)`), `count = query.slot0x7e(casterMainTile).Count`
    puis `GenerateAction(position, cible, Fix64.FromInt(count))` + `Bucket.AddAction`. slot 0x7e (IBattleQuery
    DAT_18327ff80) = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies` (`IterateAdjacentTiles`+`GetUnitsOnTiles`, porte
    d'elevation |dElev|<2) sur la MainTile de la POSITION balayee -> compte POSITION-dependant (identique
    pour toutes les cibles d'une meme position). Utilite = FromInt(count) BRUT (aucun +1/echelle, cf.
    BloodyFury IdunBattle.AI.Playbook.Loki.BloodyFuryPlaybook$$EvaluateNonComparable qui fait `1+adj*10`).

    RECONCILIATION LIVE (board MC1_67, ncEvaluate) :
    - seed 2468 s7 u83 : util(6,5)=2 (u93+u95 adj), util(5,6)=util(4,5)=util(4,4)=1 -> pos(6,5) cible u95.
    - seed 54321 s10 u89 : util(2,5)=util(3,5)=util(4,5)=util(4,6)=3 ; le natif prend (2,5) = 1re position
      ordre movable atteignant le max (Bucket.AddAction keep-first sur strict `>`) ; cible u83.

    - POSITION : sweep `ctx.reach_nc` (ordre movable natif) ; argmax STRICT `>` -> 1re position du max gagne
      (mirror #32/#76 Bucket.AddAction keep-first, NullPosition/origine incluse). Confirme live (position
      EXACTE sur les 2 misses).
    - CIBLE au sein de la position gagnante (tie sur le count position-based) = 1er ennemi ELIGIBLE adjacent
      a la tuile en ordre voisins NATIF FORWARD (`neigh_by_pos`, = ordre `GetValidTargets` slot 0x41 ->
      `IdunBattle.Core.Services.AttackQuery$$GetValidTargets` qui scanne les tuiles d'attaque). Le `count` (util) compte TOUS
      les ennemis adjacents (summons inclus, ex. u140 decoy -> util 3), mais la cible filtre l'ensemble
      ELIGIBLE (`GetEligibleTargetsSelectable` = abilityTargets ; u140 non-eligible ecarte). VALIDE LIVE
      BIT-EXACT sur les 2 misses (u95 = (6,4) 2e voisin de (6,5) ; u83 = (2,6) 1er voisin de (2,5)).
      NB : ordre FORWARD (PAS inverse comme Gauntlets/SortReverseSelector -- chemin selecteur different).
    - MIN_UTILITY=1 : IdunBattle.AI.Playbook.Loki.CordClawPlaybook$$.cctor pose `Fix64.FromInt(1)` -> min-utilite du Bucket ctor (IdunBattle.AI.Playbook.Loki.CordClawPlaybook$$EvaluateNonComparable)
      -> admission `count >= 1` (positions sans ennemi adjacent ecartees).
    - IdunBattle.AI.Playbook.Loki.CordClawPlaybook$$.ctor = `NonComparablePlaybook(0x462)` -> 1er arg=ability_id ; PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170)."""
    ABILITY_ID = int(ActiveAbilityType.CordClaw)  # 1122
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.CordClawPlaybook$$.cctor = Fix64(1) -> admission Bucket count>=1
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        # POSITION : util(P) = #ennemis adjacents a P (GetAdjacentEnemies) ; 1re position du max (movable order).
        best_p, best_u = None, None
        for P in (ctx.reach_nc or []):
            u = float(bq.count_adjacent(P, ctx.epos, ctx.elev_by_pos))   # slot 0x7e = GetAdjacentEnemies
            if u < self.MIN_UTILITY:
                continue                     # admission Bucket count>=1
            if best_u is None or u > best_u:  # strict > : 1re position du max gagne (keep-first)
                best_p, best_u = P, u
        if best_p is None:
            return []
        tgt = self._first_eligible_adjacent(best_p, ctx)
        if tgt is None:
            return []
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] CordClaw pos={best_p} count={best_u} tgt={tgt}",
                  file=sys.stderr)
        return [{"target": tgt, "ability": self.ABILITY_ID,
                 "to": (best_p if best_p != ctx.origin else None), "pred": best_u}]

    def _first_eligible_adjacent(self, P: tuple, ctx: NCContext):
        """1er ennemi ELIGIBLE adjacent a `P` en ordre voisins natif FORWARD (mirror
        `GetEligibleTargetsSelectable(P)` = slot 0x41 GetValidTargets, ordre du scan des tuiles d'attaque).
        Ennemi = position dans `ctx.epos` ; ELIGIBLE = ensemble global `abilityTargets(uid, 1122)` (ecarte
        les ennemis non-ciblables : decoys/deep-strike). Sans neigh_by_pos -> fallback hexgeo (compte
        identique, ordre non natif)."""
        eid_by_pos = {}
        for e in (ctx.enemies or []):
            p = e.get("pos")
            if p and p.get("col") is not None:
                eid_by_pos[(p["col"], p["row"])] = e.get("id")
        eligible = self._eligible_ids(ctx)
        neigh = (ctx.neigh_by_pos or {}).get(P)
        if neigh is None:
            neigh = list(hexgeo.neighbors(P[0], P[1]))   # fallback (ordre non natif)
        for n in neigh:
            if not bq.is_adjacent(P, n, ctx.elev_by_pos):   # porte |dElev|<2 (comme count_adjacent)
                continue
            tid = eid_by_pos.get(n)
            if tid is None:
                continue                                    # pas d'ennemi sur ce voisin
            if eligible is not None and tid not in eligible:
                continue                                    # ennemi non-ciblable (decoy/deep-strike)
            return tid
        return None

    def _eligible_ids(self, ctx: NCContext):
        """Ensemble des cibles ELIGIBLES globales (abilityTargets kind unit). None si la seam est absente
        (-> pas de filtre : 1er ennemi adjacent)."""
        if ctx.ability_targets is None:
            return None
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        out = set()
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        out.add(t["targetId"])
        return out
