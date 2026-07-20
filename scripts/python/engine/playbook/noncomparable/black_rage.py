"""BlackRagePlaybook — charge NonComparable (utilite = degat de l'attaque NORMALE depuis la charge)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook


class BlackRagePlaybook(_PlanTargetPlaybook):
    """`BlackRagePlaybook.EvaluateNonComparable @1811211f0` (id 0x48b=1163, bloodDeathCompany/Lucien).

    NonComparable (aucun `Make*Predictions` — reframe #34) MAIS l'utilite EST une utilite de DEGAT :
    le natif predit l'attaque NORMALE du caster sur la cible DEPUIS la tuile de charge, en fait un
    `ProbableDamageEvent`, et le score par `CalculateUtilityFromDamageEvent`. Meme forme que
    HammerOfWrath (#114) : degat consomme EN INTERNE par la decision, jamais emis en prediction affichee.

    - cibles = `BasePlaybook.GetEligibleTargetsSelectable(ctx, position)` (ennemis a portee de charge).
    - par cible : `IBattleQuery` slot 0x21 `PredictAttack(caster, target, position)` -> `DamagePredictionResult`
      -> `ProbableDamageEvent(target, prediction, prob1=null, prob2=null)` ->
      `Playbook.CalculateUtilityFromDamageEvent @1814a9f90` (= `prob x ForDamagePrediction`, composite
      Damage case 0x22). Porte via `make_normal_attack_predictions` (meme chemin PredictAttack normal
      que `WillNormalAttackKill`) + `calculate_utility_from_damage_event`.
    - `MIN_UTILITY` = cctor @181121960 = `Fix64.FromInt(1)` ; `PRIORITY`=0 (#115).
    - Le COUT de l'ability (Lucien tombe a 50% PV, `GetSetHealthBehaviour`) N'ENTRE PAS dans l'utilite :
      le natif n'emet AUCUN event self-negatif ici (contrairement au chemin Comparable `GetHealthToLose`).

    GAP assume — `GetUseProbability @181121740` : le natif tire `0.4` si les PV apres usage
    (`BlackRageAbility.GetHealthPercentageAfterUse @1811ba570`, ConfigVar 0x26 = 50%) sont INFERIEURS aux
    PV COURANTS (`GetStat(Health, part=1)`), sinon `1.0` (Fix64.One). C'est une porte ALEATOIRE consommee
    hors du Bucket ; le moteur offline est deterministe -> non modelise (meme statut que ScarabSummon /
    `GetUseProbability @181159220`). Consequence : offline emet 1163 la ou le natif peut le sauter 60% du
    temps quand Lucien est au-dessus de 50% PV."""
    ABILITY_ID = int(ActiveAbilityType.BlackRage)  # 1163
    MIN_UTILITY = 1.0     # cctor @181121960 = Fix64(1)
    PRIORITY = 0
    SWEEP_ALL_RANKED = True   # utilite POSITION-dependante (degat depuis la tuile de charge)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        if tile is None or ctx.scene is None or target is None:
            return None
        from engine.playbook.prediction import make_normal_attack_predictions
        from engine.playbook.probable_damage_event import calculate_utility_from_damage_event
        ev = make_normal_attack_predictions(ctx.scene, ctx.uid, target, tile)
        if ev is None:
            return None
        u = calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(target))
        if ctx.debug:
            import sys
            print(f"    [dbg BlackRage u{ctx.uid}] tgt={target} tile={tile} u={u:.1f}", file=sys.stderr)
        return u
