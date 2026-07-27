"""HeroicFusilladePlaybook — splash NonComparable (util plate=1, gates Hero + ennemi voisin)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _traits, _turns_started_gate


class HeroicFusilladePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.HeroicFusilladePlaybook$$EvaluateNonComparable` (id 0x49c=1180, Judh genesKelermorph).
    NonComparable (IdunBattle.AI.Playbook.Loki.HeroicFusilladePlaybook$$.ctor = `NonComparablePlaybook(0x49c)`). IdunBattle.AI.Playbook.Loki.HeroicFusilladePlaybook$$.cctor : MIN_UTILITY=1.
    PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170).

    Utilité CONSTANTE = `Fix64.FromInt(1)` par cible éligible qui passe DEUX gates (VA IdunBattle.AI.Playbook.Loki.HeroicFusilladePlaybook$$EvaluateNonComparable) :
      - gate1 `HasTrait(item.entity, 0x10=Hero)` — la cible est un Héros (en arène quasi tous les
        champions le sont -> gate peu discriminant, mais FIDÈLE au décompilé) ;
      - gate2 `∃ ennemi ∈ GetSurroundingUnits(item.pos, r=1)` via `IsEnemy` (slot 0x76 PROUVÉ
        `<GetSurroundingUnits>b__0 IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass145_0$$u003CGetSurroundingUnitsu003Eb__0`) -> la cible a >=1 AUTRE ennemi adjacent (valeur de splash).
        C'est le gate DISCRIMINANT (le natif n'émet pas 1180 si la cible n'a pas de voisin ennemi).
    Éligibilité déléguée à `ability_targets` (superset 0x44 ; le natif évalue PER-POSITION via
    `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` -> slot 0x41 `GetValidTargets(unit, pos, 1180)` -- cf.
    case-31 : `IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$GetDynamicInvalidTargetReason` n'est PAS dans le chemin playbook, contrairement
    a la croyance anterieure). Utilité PLATE -> `Bucket.ChooseAction` = premier candidat énuméré au tie.
    Aucun W, aucune prédiction de dégât. (`to`=None : le natif dash-off vers un free hex adjacent à la
    cible via `SortTilesByUtility(7)` en exec IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour -> non modélisé dans la face décision.)

    **PAS de gate per-joueur (case-31 §A REFERME 2026-07-22, #39 fable-solver)** : l'ancien « gate
    caster ∈ team 1 » était un ARTEFACT expérimental — dans les 4 expériences A/B de 2026-07-19, le
    camp de Judh était CONFONDU avec son numéro de tour (a-units toujours mesuré à turnsStarted=1,
    p-units à turnsStarted>=2). Le mécanisme natif réel est le slot-4 `turnsStarted > 1` ci-dessous
    (IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate), player-blind. Prouvé live (probe_39c_crafted, MC1_67 seed 4242) : le natif ÉMET
    `move+1180->79` pour Judh **team 2** dès ts=2, cibles Hero + gate2 verts. Toute la chaîne de
    décision native (strategy -> tactic -> generateurs -> playbook) est partagée entre joueurs et
    sans branche PlayerType (IdunBattle.Core.Services.AiControl$$GetAi route les PlayerType 0 ET 1 vers la MÊME
    instance +0x20) — cf. case-31 §A.4."""
    ABILITY_ID = int(ActiveAbilityType.HeroicFusillade)  # 1180
    MIN_UTILITY = 1.0
    PRIORITY = 0

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 de la vtable (0x298, resolu live #46) -> corps foldé IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate :
        `turnsStarted > 1` — 1180 n'est jamais évaluée au 1er tour de l'unité.
        NB (#39) : c'est CE gate qui explique tout le pseudo « per-joueur » du case-31 ; le
        compteur (stat 12, `UnitComponent.turnsStarted@+0x58`, ++ par StartTurnOperation
        IdunBattle.Operations.StartTurnOperation$$Execute sur les CurrentlyOwnedUnitIds du joueur courant) est lu LIVE par-pas via
        combatSnapshot -> les cas où le natif saute l'incrément (mesuré : Judh ciblé par 1202
        VigilanceEternal reste à ts=1 à son 2e tour) sont suivis automatiquement."""
        return _turns_started_gate(ctx)

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
