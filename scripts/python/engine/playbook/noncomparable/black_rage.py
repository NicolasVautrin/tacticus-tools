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

    POSITION DE PREDICTION = la TUILE DE CHARGE (adjacente a la cible), PAS la tuile de cast (#47).
    La charge ferme au contact avant l'attaque : `ExecuteBehaviour @1811b9c20` fait
    `MoveUnit(First(SortTilesByUtility(GetPossibleMovementTiles)))` ou `GetPossibleMovementTiles
    @1811ba5f0` = `TilesUnitCanMoveToChargeTarget(range=UnitMovementRangeWithBonus(0x53e,
    ConfigConst 0xe))` — des tuiles ADJACENTES a la cible — PUIS `UseActiveAbility(attaque NORMALE)`.
    La prediction de la decision reflete donc l'attaque AU CONTACT (arme de MELEE), quelle que soit la
    position d'evaluation du generateur. MESURE (31337 s12, u91) : le natif emet (1163, cible 85) SANS
    pre-move alors que la prediction ranged DEPUIS l'origine donnerait 77 (50.2 vs 40.3) ; au contact,
    85 = melee 4 hits 3008-3788 kill -> u=132.8 >> 77 (jamais kill, hp 8533) — l'argmax natif est
    reproduit. Le port evalue chaque tuile ADJACENTE a la cible libre+walkable (mirror du sweep du
    generateur RESTREINT aux tuiles de charge) et garde le max ; la tuile de cast rankee ne sert que
    d'ancre `to` (ranked[0]=origine -> to=None, cast en place comme le natif).

    GAP assume — `GetUseProbability @181121740` : le natif tire `0.4` si les PV apres usage
    (`BlackRageAbility.GetHealthPercentageAfterUse @1811ba570`, ConfigVar 0x26 = 50%) sont INFERIEURS aux
    PV COURANTS (`GetStat(Health, part=1)`), sinon `1.0` (Fix64.One). C'est une porte ALEATOIRE consommee
    hors du Bucket ; le moteur offline est deterministe -> non modelise (meme statut que ScarabSummon /
    `GetUseProbability @181159220`). Consequence : offline emet 1163 la ou le natif peut le sauter 60% du
    temps quand Lucien est au-dessus de 50% PV."""
    ABILITY_ID = int(ActiveAbilityType.BlackRage)  # 1163
    MIN_UTILITY = 1.0     # cctor @181121960 = Fix64(1)
    PRIORITY = 0
    # PAS de SWEEP_ALL_RANKED : la prediction est independante de la tuile de cast (charge au contact),
    # balayer les tuiles rankees ne ferait que dupliquer la meme evaluation.

    def _charge_tiles(self, target, ctx: NCContext) -> list[tuple]:
        """Tuiles de charge candidates pour la PREDICTION : hex ADJACENTS a la cible, walkable et
        LIBRES (mirror `TilesUnitCanMoveToChargeTarget` — l'occupation/walkability y gate les
        destinations reelles). Fallback : tous les voisins si le filtre vide tout (la legalite de la
        cible est deja garantie par le plan natif / `GetDynamicInvalidTargetReason @1811ba280`)."""
        tpos = None
        occupied = set()
        for u in (ctx.units or []):
            p = u.get("pos") or {}
            pos = (p.get("col"), p.get("row"))
            if u.get("id") == target:
                tpos = pos
            if u.get("alive") and pos[0] is not None and u.get("id") != ctx.uid:
                occupied.add(pos)
        if tpos is None or tpos[0] is None:
            return []
        neigh = list(ctx.neigh_by_pos.get(tpos) or [])
        free = [n for n in neigh
                if ctx.walkable_by_pos.get(n, True) and n not in occupied]
        return free or neigh

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        if ctx.scene is None or target is None:
            return None
        from engine.playbook.prediction import make_normal_attack_predictions
        from engine.playbook.probable_damage_event import calculate_utility_from_damage_event
        best = None
        for cpos in self._charge_tiles(target, ctx):
            ev = make_normal_attack_predictions(ctx.scene, ctx.uid, target, cpos)
            if ev is None:
                continue
            u = calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(target))
            if best is None or u > best:
                best = u
        if ctx.debug and best is not None:
            import sys
            print(f"    [dbg BlackRage u{ctx.uid}] tgt={target} charge-max u={best:.1f}", file=sys.stderr)
        return best
