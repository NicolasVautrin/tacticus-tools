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
    tant que Δ(pair+tile) < 1 — l'ancien « tie-break à utilité égale » en était l'ombre (#64).

    ⚠ Cette UNIQUE classe porte les **SEIZE** identités d'attaque normale que distribue la cascade
    d'`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` (14 par la voie passive,
    `1126 RogalDorn_NormalAttack` par l'active, `69 Loki_NormalAttack` en repli), et c'est FIDÈLE :
    les seize `<X>_NormalAttack*Playbook` natifs dérivent tous d'`ALoki_NormalAttackPlaybook<T>` et
    **aucun** ne redéclare `ShouldExecute`. Mesuré NIVEAU PAR NIVEAU sur les 16 classes
    (`class_get_methods` de la chaîne de parents, RPC `resolveMethodPtr`) : le `MethodInfo` de
    `ShouldExecute` apparaît à `depth 1` (= `ALoki_NormalAttackPlaybook`1`) pour les seize, à
    `depth 0` pour la seule `Loki_NormalBossAttackPlaybook`. La table des symboles NOMMÉS ne
    suffisait pas à le conclure (corps dédupliqués : `MortisRoundPlaybook` partage le corps que la
    table attribue à `SpiritLeechPlaybook$$ShouldExecute`)."""
    is_normal_attack = True

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        if ctx.scene is None:
            return None
        ev = prediction.make_normal_attack_predictions(ctx.scene, ctx.uid, target, caster_tile)
        return None if ev is None else [ev]

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        """`IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$ShouldExecute`,
        lu verbatim :

            if (UnitExtensions.HasTriggeredAbility(target, 0x48)) return false;
            return attackHealUtility > Fix64(0);

        `0x48` = 72 = **`Explosive`** dans `IdunBattle.Entities.Enum.TriggeredAbilityType` (qualifié
        sur `data/symbols/<build>/frida/enums.tsv` ; ⚠ 72 n'est PAS le même membre dans un autre
        enum, et le nom ne se devine pas). La lecture porte sur la **CIBLE** : le 4e argument de
        `ShouldExecute(this, caster, casterTile, target, attackHealUtility)`, soit `R9` dans le corps
        gshared — sémantiquement « l'IA refuse d'attaquer au corps une cible qui EXPLOSE ».

        `IdunBattle.AI.Playbook.Idun.NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$ShouldExecute`
        (la base de `17 NormalAttack`) a le corps IDENTIQUE — même gate, même littéral.

        SUBSTRAT : `HasTriggeredAbility` fait `TriggeredAbilityComponent$$TryGetAbility`, donc
        l'**ENTITÉ** (le composant monté), jamais le kit gameconfig — d'où le foyer unique
        `entity_triggered_ability_ids`, tri-état (canal muet -> repli kit, comportement d'avant).

        DEUX clauses, donc deux régressions fermées : le gate `Explosive` **et** le seuil
        `utility > 0`, que le port n'appliquait pas davantage. `utility` arrive déjà sommé du custom
        (+1 pour l'attaque normale), exactement comme le natif."""
        from ..entities.triggered_ability_type import TriggeredAbilityType, entity_triggered_ability_ids
        scene = getattr(ctx, "scene", None)
        if scene is not None and target is not None:
            tctx = scene.ctx(target)
            vis = (getattr(scene, "vis_by_id", None) or {}).get(target)
            if int(TriggeredAbilityType.Explosive) in entity_triggered_ability_ids(tctx, vis):
                return False
        return utility > 0.0

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        """`ALoki_NormalAttackPlaybook<T>.IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility` (générique partagé de
        tous les `*_NormalAttackPlaybook` par-unité) ; idem `Idun.NormalAttackPlaybook<T> IdunBattle.AI.Playbook.Idun.NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility`
        et `Loki_NormalBossAttackPlaybook IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$CalculateCustomUtility` : `Fix64.FromInt(1)` constant. Preuve L3 #64
        (2468 s18 u77) : action 69 = 20.981 pair + 40 tile + 1 = 61.981 > 61.728 = 21.728 + 40 + 0
        (MartialInspiration 1191) -> natif joue 69 ; 31337 s16 Δpair=4.97 > 1 -> 1191 émis.
        (Exception native NON portée : ProperKilly_NormalAttackPlaybook IdunBattle.AI.Playbook.Loki.ProperKilly_NormalAttackPlaybook$$CalculateCustomUtility, logique melee.)"""
        return 1.0


class NormalBossAttackPlaybook(NormalAttackPlaybook):
    """`IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook` — l'attaque normale de la
    **17e** identité, celle que la branche TRAIT de la cascade pose sur un porteur de `Boss`
    (`UnitTrait` 2023 -> `ActiveAbilityType` 1030, cf. `engine.services.custom_normal_attack`).

    UN SEUL différentiel avec les seize autres, et c'est `ShouldExecute`. Le reste est identique,
    lu et non supposé : `Loki_NormalBossAttackPlaybook$$CalculateCustomUtility` rend
    `Fix64.FromInt(1)` comme `ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility`,
    et `Loki_NormalBossAttackPlaybook$$MakeDamagePredictions` a la MÊME forme (slot `0x22` du
    service, un unique `ProbableDamageEvent`). D'où l'héritage de `NormalAttackPlaybook` : seule la
    méthode qui diffère est redéfinie.

    ⚠ La HIÉRARCHIE native est différente de celle du port, et c'est sans conséquence ici :
    `Loki_NormalBossAttackPlaybook$$.ctor` appelle `ComparablePlaybook<T>..ctor(this, 0x406, …)`
    DIRECTEMENT — elle ne dérive PAS d'`ALoki_NormalAttackPlaybook<T>`. Hériter côté port est ce qui
    fait porter `is_normal_attack`, le custom `+1` et la prédiction d'attaque normale, tous trois
    identiques par mesure ; ce que l'héritage natif ne donne PAS — le gate `Explosive` — est
    précisément ce que cette classe reprend."""
    ability_id = int(ActiveAbilityType.Loki_NormalBossAttack)   # 1030

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        """`IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$ShouldExecute`, lu verbatim :

            return attackHealUtility > Fix64(0);

        La clause `HasTriggeredAbility(target, 0x48)` de la générique est **ABSENTE** — un boss
        attaque une cible `Explosive` que toute autre unité refuserait. C'est le SEUL différentiel
        de décision entre `69` et `1030` (#419-r1-tr14-r5-r2-r1 §3.2), donc la seule chose qui donne
        un effet observable à la branche TRAIT de la cascade."""
        return utility > 0.0


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
NORMAL_BOSS_ATTACK_PLAYBOOK = NormalBossAttackPlaybook()


def normal_attack_playbook(ability_id) -> NormalAttackPlaybook:
    """FOYER du dispatch `PlaybookDatabase$$LoadPlaybook` pour une attaque NORMALE : rend le playbook
    de l'identité `ability_id` que la fabrique a posée sur l'entité.

    DEUX playbooks seulement, parce que le natif n'en distingue que deux sur cet axe : les SEIZE
    identités de la cascade partagent `ALoki_NormalAttackPlaybook<T>` (aucune ne redéclare
    `ShouldExecute` — mesuré niveau par niveau, cf. `NormalAttackPlaybook`), et `1030
    Loki_NormalBossAttack` a le sien. Un `ability_id` inconnu retombe sur la générique, ce qui est
    le comportement d'avant ce foyer.

    ⚠ Le dispatch se fait par l'ID CONCRET de l'attaque normale (`ctx.normal_ids`, alimenté par
    `decisionView` `kind == "normal"` = `ActiveAbilityComponent.NormalAttackType@0x28`), jamais par
    le trait du caster : c'est la fabrique qui a déjà tranché, une fois pour toutes, au spawn."""
    return (NORMAL_BOSS_ATTACK_PLAYBOOK
            if ability_id is not None
            and int(ability_id) == NORMAL_BOSS_ATTACK_PLAYBOOK.ability_id
            else NORMAL_ATTACK_PLAYBOOK)
HEAL_PLAYBOOK = HealPlaybook()
HEALING_BALMS_HEAL_PLAYBOOK = HealingBalms_HealPlaybook()

# Registre des playbooks de SOIN dispatches par `_heal_candidates` (id d'ability -> instance). Un id
# absent retombe sur `HEAL_PLAYBOOK` (le generique 18, dont `TwistedScience_HealPlaybook` 1167 ne
# differe que par son CustomUtility deja porte dans `HealPlaybook.score`).
HEAL_PLAYBOOKS: dict[int, ComparablePlaybook] = {
    HEALING_BALMS_HEAL_PLAYBOOK.ability_id: HEALING_BALMS_HEAL_PLAYBOOK,
}

register(RepairPlaybook())
