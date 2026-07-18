"""HeroicFusilladePlaybook — splash NonComparable (util plate=1, gates Hero + ennemi voisin)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _traits


class HeroicFusilladePlaybook(NonComparablePlaybook):
    """`HeroicFusilladePlaybook.EvaluateNonComparable @181144510` (id 0x49c=1180, Judh genesKelermorph).
    NonComparable (ctor @181144ac0 = `NonComparablePlaybook(0x49c)`). cctor @181144a50 : MIN_UTILITY=1.
    PRIORITY=0 (aucun override get_Priority, #115).

    Utilité CONSTANTE = `Fix64.FromInt(1)` par cible éligible qui passe DEUX gates (VA @181144510) :
      - gate1 `HasTrait(item.entity, 0x10=Hero)` — la cible est un Héros (en arène quasi tous les
        champions le sont -> gate peu discriminant, mais FIDÈLE au décompilé) ;
      - gate2 `∃ ennemi ∈ GetSurroundingUnits(item.pos, r=1)` via `IsEnemy` (slot 0x76 PROUVÉ
        `<GetSurroundingUnits>b__0 @1810b01e0`) -> la cible a >=1 AUTRE ennemi adjacent (valeur de splash).
        C'est le gate DISCRIMINANT (le natif n'émet pas 1180 si la cible n'a pas de voisin ennemi).
    Éligibilité (ennemi à portée avec free hex atteignable) déléguée à `ability_targets` (le RPC applique
    `HeroicFusilladeAbility.GetDynamicInvalidTargetReason @1811e9430`). Utilité PLATE -> `Bucket.ChooseAction`
    = premier candidat énuméré au tie. Aucun W, aucune prédiction de dégât. (`to`=None : le natif dash-off
    vers un free hex adjacent à la cible via `SortTilesByUtility(7)` en exec @1811e8de0 -> non modélisé
    dans la face décision ; à surveiller pour l'agreement de position.)"""
    ABILITY_ID = int(ActiveAbilityType.HeroicFusillade)  # 1180
    MIN_UTILITY = 1.0
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        tgt_ids = []                      # ordre préservé (mirror enumeration GetEligibleTargetsSelectable)
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        tgt_ids.append(t["targetId"])
        tgt_ids = list(dict.fromkeys(tgt_ids))
        if not tgt_ids:
            return []
        by_id = {u.get("id"): u for u in (ctx.units or [])}
        for tid in tgt_ids:               # keep-first : 1er candidat qui passe les 2 gates (util plate=1)
            tu = by_id.get(tid)
            p = (tu or {}).get("pos") if tu else None
            if not p or p.get("col") is None:
                continue
            tpos = (p["col"], p["row"])
            if "Hero" not in _traits((tu or {}).get("visualId")):   # gate1 : HasTrait(cible, Hero=0x10)
                continue
            others = [e for e in (ctx.epos or []) if e != tpos]     # gate2 : >=1 ennemi ring-1 (splash)
            if bq.count_adjacent(tpos, others) < 1:                 # GetSurroundingUnits(r=1) & IsEnemy
                continue
            if ctx.debug:
                import sys
                print(f"    [dbg HeroicFusillade u{ctx.uid}] tgt={tid} pos={tpos} -> util=1", file=sys.stderr)
            return [{"target": tid, "ability": self.ABILITY_ID, "to": None, "pred": 1.0}]
        return []
