"""VigilanceEternalPlaybook — frappe NonComparable (utilite = degat de l'ability depuis la tuile libre)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, _turns_started_gate
# FORME B, differes CLASSES GRATUITS depuis le degraissage du baril `engine.playbook`
# (#485-r1-r4). `generate_multi_hit_attack_prediction` est SUBSTITUE par cinq patcheurs.
from engine.playbook.prediction import abilities as _pred_ab
from engine.playbook import probable_damage_event as _pde

_ABILITY_NAME = "VigilanceEternal"


class VigilanceEternalPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.VigilanceEternalPlaybook$$EvaluateNonComparable` (id 0x4b2=1202, Tyrith).

    NonComparable (aucun `Make*Predictions` — reframe #34) a utilite de DEGAT, comme BlackRage : le natif
    calcule les entrees de degat PROPRES de l'ability puis score chaque cible eligible par
    `CalculateUtilityFromDamageEvent` (surcharge IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent : (damage, profile, hits) -> `PredictAttack`
    slot 0x27 -> `ProbableDamageEvent` -> composite Damage case 0x22).

    - entrees : `GetDamageFormula(position)` (nommee `BlightGrenadesAbility.GetDamageFormula` = helper
      PARTAGE), `AActiveAbility.GetDamageProfile` (Power, pierce 40%), `GetHits`
      (`IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` = `nrOfHits` = 3). C'est EXACTEMENT le chemin generique
      d'une special (base minmax config + hits + profil) -> `generate_multi_hit_attack_prediction`,
      appele DIRECTEMENT (pas `make_damage_predictions`, dont le gate d'AFFICHAGE #109 rend `[]` pour
      toute NonComparable : 1202 n'emet AUCUN ProbableDamageEvent affiche — l'oracle live le confirme).
      Meme bypass que HammerOfWrath (`make_hammer_wrath_events`), ici sans override d'entrees.
    - cibles = `BasePlaybook.GetEligibleTargetsSelectable(ctx, position)` (ennemi avec un hex libre
      adjacent, a portee de mouvement 2 — gameconfig `range:2`).
    - `MIN_UTILITY` = IdunBattle.AI.Playbook.Loki.VigilanceEternalPlaybook$$.cctor = `Fix64.FromInt(1)` ; `PRIORITY`=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170).
    - `GenerateAction(position, targetTile, util)` : Tyrith se deplace sur l'hex libre (la tuile rankee
      du plan) puis frappe ; l'ability NE TERMINE PAS son tour (non modelise cote decision, le harnais
      compare une action a la fois).

    Enumeration cible + tuile = plan natif rank (`_PlanTargetPlaybook`) : 1202 a une config de degat,
    donc ses paires sont dans `attackPlans`."""
    ABILITY_ID = int(ActiveAbilityType.VigilanceEternal)  # 1202
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.VigilanceEternalPlaybook$$.cctor = Fix64(1)
    PRIORITY = 0

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 de la vtable (0x298, resolu live #46) -> corps foldé IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate :
        `turnsStarted > 1` — 1202 n'est jamais évaluée au 1er tour de l'unité."""
        return _turns_started_gate(ctx)

    def _ability_prediction(self, tile, target, ctx: NCContext):
        """`GetDamageFormula(position)` + `GetDamageProfile` + `GetHits` -> le `DamagePredictionResult`
        que `CalculateUtilityFromDamageEvent` score. Foyer UNIQUE, partage par `damage_predictions`
        (trace de construction) et `evaluate_non_comparable` (utilite) -- pas de derive possible."""
        return _pred_ab.generate_multi_hit_attack_prediction(
            ctx.scene, ctx.uid, target, self.ABILITY_ID, _ABILITY_NAME, attack_pos=tile)

    def damage_predictions(self, tile, target, ctx: NCContext) -> list:
        """UN SEUL `ProbableDamageEvent` par cible : `VigilanceEternalPlaybook$$EvaluateNonComparable`
        n'a AUCUN gate predictif avant `CalculateUtilityFromDamageEvent` (contraste avec
        `KillMaimBurnPlaybook`, dont `WillNormalAttackKill` en construit un premier)."""
        if tile is None or ctx.scene is None or target is None:
            return []
        dp = self._ability_prediction(tile, target, ctx)
        return [] if dp is None else [("ability", dp)]

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        if tile is None or ctx.scene is None or target is None:
            return None
        dp = self._ability_prediction(tile, target, ctx)
        if dp is None:
            return None
        ev = _pde.ProbableDamageEvent(target=target, prediction=dp)
        u = _pde.calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(target))
        if ctx.debug:
            import sys
            print(f"    [dbg VigilanceEternal u{ctx.uid}] tgt={target} tile={tile} u={u:.1f}",
                  file=sys.stderr)
        return u
