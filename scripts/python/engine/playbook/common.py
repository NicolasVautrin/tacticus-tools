"""Playbooks Comparable COMMUNS — Normal / Default / Heal / Repair (namespace `IdunBattle.AI.Playbook`).

Sous-classes MINCES de `ComparablePlaybook<T>` (base.py) : elles n'overrident QUE le fournisseur de
prédiction (`MakeDamagePredictions`, vtable +0x358) et éventuellement le gate/custom. Le calcul
prédiction->utilité (Σ damage_composite + Tile(7)) est mutualisé dans la base.

- `NormalAttackPlaybook` (ALoki_NormalAttackPlaybook & co, un par unité côté natif) : prédiction =
  `prediction.make_normal_attack_predictions` (sélection d'arme + hits + perçage + armure + modifiers effets).
- `DefaultActiveAbilityPlaybook` : fallback pour toute ability spéciale sans playbook bespoke ->
  `prediction.make_damage_predictions` (cible principale + AoE ; None/[] pour summon/buff/heal = NON-attaque).
- `HealPlaybook` (tag 18) : soin = `HealUtility IdunBattle.AI.Utilities.HealUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext` (heal_utility) + CustomUtility (TwistedScience).
  Gate `IdunBattle.AI.Playbook.Common.HealPlaybook$$ShouldExecute` : pred > 0.
- `RepairPlaybook` (tag 28) : réparation générique du trait `Mechanic` — prédiction NON-dégât
  (`MakeRepairPredictions` + `RepairedAmountUtility`), candidats montés par `_repair_candidates`.

PRÉDICTEUR = `engine.playbook.prediction` (modèle objet : Scene + ability + services + ProbableDamageEvent).
"""
from __future__ import annotations

from . import prediction
from .base import ComparablePlaybook, register
from ..predict import heal_utility
from ..entities.active_ability_type import ActiveAbilityType


class NormalAttackPlaybook(ComparablePlaybook):
    """Attaque normale (par-unité côté natif ; ici une classe, PV gère la sélection d'arme).
    Porte le bonus d'action +1 (`calculate_custom_utility`) : la normale bat tout actif Comparable
    tant que Δ(pair+tile) < 1 — l'ancien « tie-break à utilité égale » en était l'ombre (#64)."""
    is_normal_attack = True

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        if ctx.scene is None:
            return None
        ev = prediction.make_normal_attack_predictions(ctx.scene, ctx.uid, target, caster_tile)
        return None if ev is None else [ev]

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        """`ALoki_NormalAttackPlaybook<T>.IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility` (générique partagé de
        tous les `*_NormalAttackPlaybook` par-unité) ; idem `Idun.NormalAttackPlaybook<T> IdunBattle.AI.Playbook.Idun.NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility`
        et `Loki_NormalBossAttackPlaybook IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$CalculateCustomUtility` : `Fix64.FromInt(1)` constant. Preuve L3 #64
        (2468 s18 u77) : action 69 = 20.981 pair + 40 tile + 1 = 61.981 > 61.728 = 21.728 + 40 + 0
        (MartialInspiration 1191) -> natif joue 69 ; 31337 s16 Δpair=4.97 > 1 -> 1191 émis.
        (Exception native NON portée : ProperKilly_NormalAttackPlaybook IdunBattle.AI.Playbook.Loki.ProperKilly_NormalAttackPlaybook$$CalculateCustomUtility, logique melee.)"""
        return 1.0


class DefaultActiveAbilityPlaybook(ComparablePlaybook):
    """Fallback générique pour toute ability spéciale d'attaque (non enregistrée sous un id bespoke).
    Prédiction = `PV.make_damage_predictions` : liste cible principale + AoE. None/[] = NON-attaque
    (summon/buff/heal) -> aucune action émise (gate). ability_id -1 (non enregistré ; défaut)."""
    ability_id = -1
    is_normal_attack = False

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        if ctx.scene is None:
            return None
        return prediction.make_damage_predictions(ctx.scene, ctx.uid, target, ability_id,
                                                  ctx.ab_name_by_id.get(ability_id), attack_pos=caster_tile)


class HealPlaybook(ComparablePlaybook):
    """Soin (tag 18). Utilité = CustomUtility (TwistedScience : +100, +100 si cible Genestealers) +
    `HealUtility` (heal_utility = (missing/(maxHP+1))×100×friendSign×bossMod). Gate `IdunBattle.AI.Playbook.Common.HealPlaybook$$ShouldExecute` : pred > 0 (self-heal permis). L'énumération cibles/tuiles reste au générateur ;
    `score` = le terme d'utilité par cible."""
    ability_id = int(ActiveAbilityType.Heal)  # 18 (#158)

    def score(self, effective_heal, hp_max, is_friend, is_twisted, target_faction):
        """Utilité de soin d'une cible, ou None si `pred <= 0` (gate `ShouldExecute`). `effective_heal` =
        soin EFFECTIF `min(HealAmount, missing)` (le générateur le cape via `predict_heal_effective`, #79 ;
        auparavant saturé à `missing`). Le skip « cible déjà buffée TwistedScience » est un gate
        d'ÉNUMÉRATION (fait par le générateur, inconditionnel), pas ce CustomUtility."""
        heal_term = heal_utility(effective_heal, hp_max, is_friend=is_friend, is_boss=False)
        custom = (100 + (100 if target_faction == "Genestealers" else 0)) if is_twisted else 0
        pred = custom + heal_term
        return pred if pred > 0 else None


class HealingBalms_HealPlaybook(ComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook` (ability 1212, `AddActiveAbility(0x4bc)`
    posee par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HealingBalmsAbility$$CreateBehaviour`,
    qui RETIRE en meme temps le `Heal` generique 18 du porteur). Son `.ctor` derive DIRECTEMENT de
    `ComparablePlaybook<T>` (`ComparablePlaybook<T>..ctor(this, 0x4bc, klass)`), pas de `HealPlaybook`.

    DEUX overrides, et un seul porte du comportement :

    * `IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$MakeHealPredictions` : corps IDENTIQUE a
      `IdunBattle.AI.Playbook.Common.HealPlaybook$$MakeHealPredictions` et a
      `IdunBattle.AI.Playbook.Loki.TwistedScience_HealPlaybook$$MakeHealPredictions` (memes appels,
      memes arguments : `HealAbility$$HealAmount(ability)`, selecteur de cibles `ability.<+0x90>+0x60`,
      `Nullable<Fix64>` de proba VIDE, `ComparablePlaybook<T>$$GenerateHealPredictions(..., scope=0)`) —
      seul le type gshared differe. C'est la recopie imposee par la hierarchie, PAS une chaine propre :
      la prediction de soin est la chaine STANDARD, deja portee (`engine.predict` PARTIE 3).
    * `IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$CalculateCustomUtility` — le seul delta :

          if (EntityExtensions$$HasEffect(target, state, 0x5df, 0)) x = Fix64(0)
          else x = SUM over MakeHealPredictions(caster, casterPosition.MainTile, target, abilityState)
                       of Playbook<T>$$CalculateUtilityFromHealEvent(ev)
          return Fix64.FastMul(x, Fix64.<statics+0x30>)

      `Fix64.<statics+0x30>` = `op_Division(One, Fix64(2))` ecrit par `FixMath.NET.Fix64$$.cctor`
      = **Half**. `0x5df` = `EffectType.HealingBalms_ExtraCritDamage`, l'un des deux stat-modifiers que
      `HealingBalms_HealAbility$$ExecuteBehaviour` pose sur les memes cibles (avec 0x5e0
      `HealingBalms_ExtraCritChance`) — le gate est donc « cette cible porte deja mon buff ».

      La somme sommee par le custom est LA MEME que celle de la 2e boucle de
      `ComparablePlaybook<T>$$CalculateUtilityFromPredictions` (slot +0x368, `CalculateUtilityFromHealEvent`).
      Comme `CalculateActionUtility` fait `u = custom + CalculateUtilityFromPredictions`, l'utilite
      d'action vaut **1.5 x U_heal** sur une cible non buffee et **1.0 x U_heal** sur une cible buffee.

    * `IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$ShouldExecute` = `utility > Fix64(0)` SEUL
      — sans la clause `!IsBoss(caster) || caster != target` de
      `IdunBattle.AI.Playbook.Common.HealPlaybook$$ShouldExecute`. Meme effet ici : `u = 1.5 x U` a le
      signe de `U`, donc le gate reste `U > 0` (cible a PV pleins -> `MaxFillUp` = 0 -> aucune action,
      malgre un ciblage qui l'autorise — `HealingBalms_HealAbility$$GetDynamicInvalidTargetReason` ne
      teste que `UnitExtensions$$IsAffectedByHealType`, ce que l'i2 dit mot pour mot : « Baldr can heal
      friendly units even if they are at full Health »)."""
    ability_id = int(ActiveAbilityType.HealingBalms_Heal)  # 1212

    def calculate_custom_utility_from_heal(self, heal_term: float, target_has_balms: bool) -> float:
        """`...HealingBalms_HealPlaybook$$CalculateCustomUtility` : `Half * Sum(CalculateUtilityFromHealEvent)`
        gate par `!HasEffect(target, EffectType.HealingBalms_ExtraCritDamage)`. `heal_term` EST cette
        somme (le selecteur de cibles de l'ability est mono-cible : `abilityTargets` enumere une cible
        par candidat, et le generateur score cible par cible — un seul `ProbableHealEvent`)."""
        return 0.0 if target_has_balms else 0.5 * heal_term

    def score(self, effective_heal, hp_max, is_friend, target_has_balms: bool):
        """Utilite d'ACTION de la paire (caster, cible), ou None si `ShouldExecute` refuse.
        `heal_term` = `Sum(Probability x HealUtility.Evaluate)` (proba = 1, `ProbableHealEvent$$.ctor`
        sur un `Nullable` vide) ; `custom` = le terme ci-dessus ; gate `u > 0`."""
        heal_term = heal_utility(effective_heal, hp_max, is_friend=is_friend, is_boss=False)
        pred = self.calculate_custom_utility_from_heal(heal_term, target_has_balms) + heal_term
        return pred if pred > 0 else None


class RepairPlaybook(ComparablePlaybook):
    """`IdunBattle.AI.Playbook.Common.RepairPlaybook` (tag 28, granted par le trait `Mechanic`).
    `MakeDamagePredictions` -> None : la réparation n'est PAS une attaque. Sa prédiction passe par
    `MakeRepairPredictions` (dict {cible: RepairPredictionResult}) et son utilité par
    `RepairedAmountUtility` — les DEUX sont portées, et la génération de candidats vit dans
    `engine.ai.action_generators.ActionGenerators._repair_candidates` (magnitude
    `repair_amount_weapon`, remplissage `predict_repair_effective`, utilité `repair_utility` ;
    confronté live #45d au scoreur natif `pairUtility`)."""
    ability_id = int(ActiveAbilityType.Repair)  # 28 (#158)

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        return None


# Instance unique du fallback (spéciales sans bespoke) + du soin (dispatch par le générateur).
DEFAULT_PLAYBOOK = DefaultActiveAbilityPlaybook()
NORMAL_ATTACK_PLAYBOOK = NormalAttackPlaybook()
HEAL_PLAYBOOK = HealPlaybook()
HEALING_BALMS_HEAL_PLAYBOOK = HealingBalms_HealPlaybook()

# Registre des playbooks de SOIN dispatches par `_heal_candidates` (id d'ability -> instance). Un id
# absent retombe sur `HEAL_PLAYBOOK` (le generique 18, dont `TwistedScience_HealPlaybook` 1167 ne
# differe que par son CustomUtility deja porte dans `HealPlaybook.score`).
HEAL_PLAYBOOKS: dict[int, ComparablePlaybook] = {
    HEALING_BALMS_HEAL_PLAYBOOK.ability_id: HEALING_BALMS_HEAL_PLAYBOOK,
}

register(RepairPlaybook())
