"""BlackRagePlaybook — charge NonComparable (utilite = degat de l'attaque NORMALE depuis la charge)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook
# FORME B (liaison de MODULE), et differes CLASSES GRATUITS depuis le degraissage du baril
# `engine.playbook` (#485-r1-r4) : charger l'un ou l'autre dans un process FRAIS ne fait plus
# atterrir ce module dans `sys.modules`, donc il n'y a plus de cycle a fermer -> HISSE.
# `make_normal_attack_predictions` est SUBSTITUE par un patcheur
# (`test_974_custodes_emperors_children_decision_offline.py`) : une liaison `from X import f` au
# niveau module le GELERAIT et rendrait le patch inerte.
from engine.playbook.prediction import normal_attack as _pred_na
from engine.playbook import probable_damage_event as _pde


class BlackRagePlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$EvaluateNonComparable` (id 0x48b=1163, bloodDeathCompany/Lucien).

    NonComparable (aucun `Make*Predictions` — reframe #34) MAIS l'utilite EST une utilite de DEGAT :
    le natif predit l'attaque NORMALE du caster sur la cible DEPUIS la tuile de charge, en fait un
    `ProbableDamageEvent`, et le score par `CalculateUtilityFromDamageEvent`. Meme forme que
    HammerOfWrath (#114) : degat consomme EN INTERNE par la decision, jamais emis en prediction affichee.

    - cibles = `BasePlaybook.GetEligibleTargetsSelectable(ctx, position)` (ennemis a portee de charge).
    - par cible : `IBattleQuery` slot 0x21 `PredictAttack(caster, target, position)` -> `DamagePredictionResult`
      -> `ProbableDamageEvent(target, prediction, prob1=null, prob2=null)` ->
      `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent` (= `prob x ForDamagePrediction`, composite
      Damage case 0x22). Porte via `make_normal_attack_predictions` (meme chemin PredictAttack normal
      que `WillNormalAttackKill`) + `calculate_utility_from_damage_event`.
    - `MIN_UTILITY` = IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$.cctor = `Fix64.FromInt(1)` ; `PRIORITY`=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170).
    - Le COUT de l'ability (Lucien tombe a 50% PV, `GetSetHealthBehaviour`) N'ENTRE PAS dans l'utilite :
      le natif n'emet AUCUN event self-negatif ici (contrairement au chemin Comparable `GetHealthToLose`).

    POSITION DE PREDICTION = la TUILE DE CHARGE (adjacente a la cible), PAS la tuile de cast (#47).
    La charge ferme au contact avant l'attaque : `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` fait
    `MoveUnit(First(SortTilesByUtility(GetPossibleMovementTiles)))` ou `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetPossibleMovementTiles` = `TilesUnitCanMoveToChargeTarget(range=UnitMovementRangeWithBonus(0x53e,
    ConfigConst 0xe))` — des tuiles ADJACENTES a la cible — PUIS `UseActiveAbility(attaque NORMALE)`.
    La prediction de la decision reflete donc l'attaque AU CONTACT (arme de MELEE), quelle que soit la
    position d'evaluation du generateur. MESURE (31337 s12, u91) : le natif emet (1163, cible 85) SANS
    pre-move alors que la prediction ranged DEPUIS l'origine donnerait 77 (50.2 vs 40.3) ; au contact,
    85 = melee 4 hits 3008-3788 kill -> u=132.8 >> 77 (jamais kill, hp 8533) — l'argmax natif est
    reproduit. Le port evalue chaque tuile ADJACENTE a la cible libre+walkable (mirror du sweep du
    generateur RESTREINT aux tuiles de charge) et garde le max ; la tuile de cast rankee ne sert que
    d'ancre `to` (ranked[0]=origine -> to=None, cast en place comme le natif).

    GAP assume — `IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$GetUseProbability` : le natif tire `0.4` si les PV apres usage
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetHealthPercentageAfterUse`, ConfigVar 0x26 = 50%) sont INFERIEURS aux
    PV COURANTS (`GetStat(Health, part=1)`), sinon `1.0` (Fix64.One). C'est une porte ALEATOIRE consommee
    hors du Bucket ; le moteur offline est deterministe -> non modelise (meme statut que ScarabSummon /
    `IdunBattle.AI.Playbook.Loki.ScarabSummonPlaybook$$GetUseProbability`). Consequence : offline emet 1163 la ou le natif peut le sauter 60% du
    temps quand Lucien est au-dessus de 50% PV."""
    ABILITY_ID = int(ActiveAbilityType.BlackRage)  # 1163
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$.cctor = Fix64(1)
    PRIORITY = 0
    # Prediction independante de la position balayee (charge au contact) : le sweep position-outer
    # de _PlanTargetPlaybook duplique la meme evaluation -> le tie retombe sur la 1re position
    # legale de l'ordre movable natif (mirror Bucket keep-first IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction).

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` (slot 4 IPlaybook, gate AMONT du generateur
        `ActiveAbilityActionGenerator.<GenerateActions>d__7 IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`) nourri de
        `IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$GetUseProbability` : prob = `0.4`
        (`Fix64.FromIntFraction(4,10)`) si HP_apres_usage < PV COURANTS, sinon `1.0`
        (`Fix64.One`, statics+0x20 -- lu au FixMath.NET.Fix64$$.cctor). ShouldEvaluate : prob>=1 -> True ;
        prob<=0 -> False ; sinon RNG (jamais 0 ici). HP_apres = MaxHealth * ConfigVar(0x26) =
        50% MaxHealth (`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetHealthPercentageAfterUse` = ConfigVar(0x26) ;
        `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetSetHealthBehaviour` = ChangeStat(Health, PercentageOf(MaxHealth, 0x26)) ;
        i2 "set to 50% Health").

        -> prob 1.0 = OFFERT DETERMINISTE ssi PV_courant <= 50% MaxHealth (Lucien deja blesse :
        berserk garanti, HP_apres le remonte a 50%). Sinon prob 0.4 = porte ALEATOIRE per-appel
        que le moteur DETERMINISTE ne reproduit pas -> on ne l'offre PAS (conservateur : matche
        la MAJORITE ~60% des non-offres natives ET la reference capturee). CONFIRME LIVE (#57f) :
        31337 s12 u91 hp=1/9537 (<50%) -> natif 6/6 offert (deterministe) ; 54321 s12 u93 hp=6040
        (>50%) -> flicker 1/5 (RNG 0.4). scene/hp absents -> True (pas de gate a l'aveugle =
        comportement pre-#57f ; evaluate_non_comparable rend None sans scene de toute facon)."""
        if ctx.scene is None:
            return True
        hp = ctx.scene.hp(ctx.uid)
        hpmax = ctx.scene.hpmax(ctx.uid)
        if hp is None or hpmax is None:
            return True
        # ConfigVar 0x26 = 50% (i2 "set to 50% Health" ; IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetHealthPercentageAfterUse) -- Lucien-only
        return hp <= hpmax * 0.5

    def _charge_tiles(self, target, ctx: NCContext) -> list[tuple]:
        """Tuiles de charge candidates pour la PREDICTION : hex ADJACENTS a la cible, walkable et
        LIBRES (mirror `TilesUnitCanMoveToChargeTarget` — l'occupation/walkability y gate les
        destinations reelles). Fallback : tous les voisins si le filtre vide tout (la legalite de la
        cible est deja garantie par le plan natif / `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetDynamicInvalidTargetReason`)."""
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
        best = None
        for cpos in self._charge_tiles(target, ctx):
            ev = _pred_na.make_normal_attack_predictions(ctx.scene, ctx.uid, target, cpos)
            if ev is None:
                continue
            u = _pde.calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(target))
            if best is None or u > best:
                best = u
        if ctx.debug and best is not None:
            import sys
            print(f"    [dbg BlackRage u{ctx.uid}] tgt={target} charge-max u={best:.1f}", file=sys.stderr)
        return best
