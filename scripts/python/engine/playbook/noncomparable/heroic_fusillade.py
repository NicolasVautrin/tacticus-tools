"""HeroicFusilladePlaybook — splash NonComparable (util plate=1, gates Hero + ennemi voisin)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _traits, _turns_started_gate


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
    Éligibilité déléguée à `ability_targets` (superset 0x44 ; le natif évalue PER-POSITION via
    `GetEligibleTargetsSelectable @18111ed80` -> slot 0x41 `GetValidTargets(unit, pos, 1180)` -- cf.
    case-31 : `GetDynamicInvalidTargetReason @1811e9430` n'est PAS dans le chemin playbook, contrairement
    a la croyance anterieure). Utilité PLATE -> `Bucket.ChooseAction` = premier candidat énuméré au tie.
    Aucun W, aucune prédiction de dégât. (`to`=None : le natif dash-off vers un free hex adjacent à la
    cible via `SortTilesByUtility(7)` en exec @1811e8de0 -> non modélisé dans la face décision.)

    **GATE PER-JOUEUR (case-31 demi-partie A, prouvé A/B live 2026-07-19)** : le natif n'émet JAMAIS 1180
    pour une unité du camp a-units (player « enemy_1 », PlayerType 1, team 2) -- même état optimal forcé
    (1180 fraîche/usable/hasAmmo, cibles légales depuis 9 tuiles au pipeline complet, caster adjacent à un
    Héros accompagné -> le dryRun attaque quand même) -- alors qu'il l'émet spontanément pour le MÊME Judh,
    MÊME seed/board/rosters, côté p-units (team 1). L'asymétrie est spécifique à 1180 (le camp a-units
    émet d'autres NC : 1117/1122/1123 mesurés) ; le maillon natif interne n'est pas localisé (candidats +
    instruments : case-31 §A.4). Port = comportement observé : émettre SSI caster team 1."""
    ABILITY_ID = int(ActiveAbilityType.HeroicFusillade)  # 1180
    MIN_UTILITY = 1.0
    PRIORITY = 0

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 de la vtable (0x298, resolu live #46) -> corps foldé @18111af90 :
        `turnsStarted > 1` — 1180 n'est jamais évaluée au 1er tour de l'unité."""
        return _turns_started_gate(ctx)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if not self._is_player_side(ctx):      # gate per-joueur (case-31 §A) : a-units ne tire JAMAIS
            return []
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

    def _is_player_side(self, ctx: NCContext) -> bool:
        """Caster ∈ camp « player » (BC `Player.Players` : PlayerType 0 -> TeamId 1 ; a-units =
        « enemy_1 » PlayerType 1 -> TeamId 2). Comportement A/B case-31 §A.1 : 4 expériences live,
        suppress systématique côté team 2, émission spontanée côté team 1. team absent -> permissif
        (comportement pré-fix) pour ne pas gater à l'aveugle un contexte sans decisionView complet."""
        me = next((u for u in (ctx.units or []) if u.get("id") == ctx.uid), None)
        team = (me or {}).get("team")
        if team is None:
            return True
        return int(team) == 1
