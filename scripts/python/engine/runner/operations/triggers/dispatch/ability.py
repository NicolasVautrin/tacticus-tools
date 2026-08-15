"""Vecteurs d'event de la face ABILITY (init, pre-cast, post-cast, cast actif, evaluation
inline), extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169
-- deplacement VERBATIM, zero changement de comportement).

`On(AbilityInit=0x21)`, `On(PreUnitAbility=0x2a)`, `On(UnitAbility=0xb)`, `On(UnitPostAbility)`,
`On(UnitActiveAbility)`, plus `evaluate_abilities_for_event` (noeud DSL `EvaluateAbilities`)."""
from __future__ import annotations

from typing import Optional

from ....state import State
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggerEvent
from ..loki import _fire_of_absolution_after_attack
from .core import evaluate_trigger_operation
from ....abilities.attack_type import is_active_ability, is_normal_attack


#: 5e VOIE DE COUVERTURE d'un passif (#951-r2) — le canal IMPERATIF de ce module, declare ICI parce
#: que c'est ICI qu'il vit. Cle = NOM gameconfig du passif (meme cle que `passiveAbilities`, donc
#: aucune traduction), valeur = le callable REELLEMENT appele par le vecteur.
#:
#: ⚠ POURQUOI IL FAUT UN REGISTRE POUR UN APPEL EN DUR. `audit_kit_coverage.py` etablit la couverture
#: d'un passif en lisant des REGISTRES (`ABILITY_TRIGGERS`, `ABILITY_INIT_OWNER_EFFECTS`,
#: `CUSTOM_NORMAL_ATTACK_BY_PASSIVE`, `EFFECT_CLASSES`). Un passif joue par un appel IMPERATIF n'a,
#: par construction, aucune entree a lire : il etait donc compte MANQUANT alors qu'il est PORTE EN
#: ENTIER — mesure #951 sur `FireOfAbsolution`, et le cout n'est pas cosmetique, c'est un agent
#: dispatche sur du travail deja fait. La declaration est le SEUL moyen de rendre cette voie
#: lisible ; le test `test_951r2_voies_de_couverture_offline.py` la rend VERIFIABLE (le callable
#: doit exister ET etre appele dans ce module — une declaration morte rougit).
#:
#: ⚠ DISJONCTION OBLIGATOIRE avec les autres registres de passif. Y inscrire un nom qui figure DEJA
#: dans `ABILITY_TRIGGERS` ne serait pas une double couverture : ce serait un DOUBLE FIRE — c'est
#: exactement ce que le parametre `fire_of_absolution=False` d'`evaluate_abilities_for_event` existe
#: pour empecher sur la voie normale. Le test garde cette disjonction.
IMPERATIVE_ABILITY_VECTORS: dict[str, object] = {
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateTrigger` =
    # `On(0x4a = AttackInAtomicGroup, ownerNeedsToBeAlive: 1) & get_OwnerIsActor & IsRangedAttack()`.
    # Le `CreateBehaviour` est porte en entier par `fire_of_absolution_tree` ; ce qui manque au
    # registre est l'INSCRIPTION, pas le corps. Cf. `docs/rl/case-951-trophy-taker-et-fire-of-
    # absolution.md` §4. Le gate `ownerNeedsToBeAlive` n'est pas modelise sur ce vecteur (residu
    # `#951-r4`) : inobservable ici, l'attaquant venant de porter son attaque.
    "FireOfAbsolution": _fire_of_absolution_after_attack,
}


def ability_init_triggers(state: State, unit_id: int) -> list[dict]:
    """Vecteur `On(AbilityInit=0x21=33)` — emis par
    `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` quand les abilities d'une unite
    s'INITIALISENT (creation d'unite : roster de depart ET summon pose en cours de bataille).

    C'est le trigger de base pre-cache `df@0xa8` (`IdunBattleLogic.Entities.DSLFactory$$InitializeShared` :
    `On(0x21) & df@0x128 & OwnerIsActor(owner@0x148, actor@0x158)`), consomme tel quel par toute la
    famille des owner-effects poses a l'init (`LifewardsAddEffectAbility$$CreateTrigger` = `return df@0xa8`)
    et, AVEC un gate supplementaire, par `IdunBattleLogic.Entities.Abilities.Active.Loki.ListenUpMaggotsAbility$$CreateTrigger`
    (`df@0xa8 & HasUnit(Parent(caster@0x160), 3)`).

    Le port materialise deja la BRANCHE INCONDITIONNELLE de cette famille par SEEDING au spawn
    (`spawn.py::_seed_*_owner_effects` = la table `factory.ABILITY_INIT_OWNER_EFFECTS`) ; ce vecteur
    couvre la branche GATEE, qu'un seed inconditionnel ne peut pas porter. `actor_id == target_id ==
    l'unite qui s'initialise` (owner == actor : c'est le sens de `get_OwnerIsActor` ici).

    SEUL consommateur porte : `ListenUpMaggotsAddEffectAbility` (#95-RESTE2). Aucun autre trigger du
    registre n'ecoute `event_id == 33` -> zero effet de bord, zero conso RNG pour les autres spawns."""
    ev = TriggerEvent(EventTriggerType.AbilityInit, unit_id, unit_id, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def pre_unit_ability_triggers(state: State, caster_id: int, target_id: int,
                              ranged: bool, profile: Optional[str] = None,
                              ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(PreUnitAbility=0x2a=42)` — emis par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (`FUN_1800280e0(0x4d, .., 0x2a)` = `On(PreUnitAbility)`)
    **TOUT EN HAUT**, avant l'execution de l'ability (donc avant tout degat/block) ; la MEME operation
    emet ensuite, dans l'ordre, `0xb (UnitAbility)`, `0xc (UnitActiveAbility)` et `0xe (UnitPostAbility)`.
    L'`AbilityEntities` de l'evenement est celui de l'ability : caster = l'ACTEUR, target = la cible.

    L'attaque NORMALE emprunte cette operation (l'attaque normale EST une active ability, cf.
    `NormalAttackType` — memoire « normal attack = concrete ability id »).

    #120 — LES DEUX VOIES L'EMETTENT. Le natif n'a qu'UN site d'emission ; le port en a deux parce
    qu'il a deux portes d'operation (`DamageHandler.visit_AttackUnitMessage` pour l'attaque normale,
    `AbilityHandler.visit_ActiveAbilityMessage` pour un cast). Jusqu'a #120 seule la voie NORMALE
    emettait = FORK de port (1 site natif -> 2 sites offline dont 1 muet), et les consommateurs
    s'appuyaient sur un gate STRUCTUREL (« ce vecteur ne peut venir que d'une attaque normale »).
    Les deux voies emettent desormais, au meme rang relatif que le natif (apres les gates
    acteur-mort / cible-invalide, avant l'execution), et les gates des consommateurs sont PORTES
    (`abilities/attack_type.py` : `IsNormalAttack`, `AbilityHasAttackType`).

    `ability_type` = `df@0x130` (l'ability declenchante) : `0x3f5` (marqueur « kind attaque-normale »)
    sur la voie normale, l'`ActiveAbilityType` du cast sur la voie ability. C'est LE discriminant que
    lisent les deux gates ci-dessus — le renseigner n'est pas optionnel.

    Consommateurs portes :
      * `AnvilShieldFrozenAttackerAdvantageAbility` (#100) — gate `IsNormalAttack`, donc actif sur la
        seule voie normale : le bonus +20 % block d'Arjac doit etre POSE avant le calcul du block de
        CETTE attaque (c'est exactement pour ca que le natif emet l'evenement AVANT l'execution) ;
      * `SwornProtectorSummonKellAbility` / `SwornProtectorProtectSwitchAbility` (#95) — gate
        `AbilityHasAttackType(0|1)`, donc actifs sur les DEUX voies : c'est eux que le fork rendait
        muets face a une ability offensive ;
      * `HazeOfCorruptionTargetFinderAbility` (case-207) — gate `get_OwnerIsCaster` SEUL (aucun gate
        d'attaque) : il fire pour N'IMPORTE QUELLE ability de `deathBlightlord` et **consomme du
        RNG** (`min(|pool|, 2)` tirages du `PickRandomly`) AVANT le premier coup. C'est le
        consommateur qui rend ce vecteur NUMERIQUEMENT observable : un rejeu offline qui appelle
        `<Ability>.execute_behaviour(...)` a la main au lieu de passer par
        `AbilityHandler.visit_ActiveAbilityMessage` saute ces tirages et lit la mauvaise fenetre du
        flux -- signature mesuree #277 (port 21680 / live 21023 sur `FlailSwing`, cellule d'arme
        pourtant IDENTIQUE).
    AUCUN autre trigger porte n'ecoute `event_id == 0x2b`."""
    ev = TriggerEvent(EventTriggerType.PreUnitAbility, caster_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def unit_post_ability_triggers(state: State, caster_id: int, target_id: int,
                               ranged: bool, profile: Optional[str] = None,
                               ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(UnitPostAbility=0xe=14)` — DERNIER evenement emis par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (`FUN_1800280e0(0x4d, .., 0xe)` = `On(UnitPostAbility)`),
    apres `0x2b` puis `0xb`/`0xc`. Consommateur porte : le trigger PROPRE de l'effet 1201
    (`AnvilShieldFrozenAdvantageExpire`) qui consomme le +20 % block a la fin de l'ability.
    AUCUN autre trigger porte n'ecoute `event_id == 0xe`.

    #120 — PENDANT EXACT de `pre_unit_ability_triggers` : emis par les DEUX voies (fin de
    `after_hit_normal_attack` pour l'attaque normale, queue de
    `AbilityHandler.visit_ActiveAbilityMessage` pour un cast, apres `AddFlagsAfterAbilityExecution`
    comme le natif). Emettre `0x2b` sans son `0xe` sur la meme voie laisserait un effet
    « le temps de CETTE ability » pose pour toujours."""
    ev = TriggerEvent(EventTriggerType.UnitPostAbility, caster_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def unit_ability_triggers(state: State, caster_id: int, target_id: Optional[int],
                          ranged: bool, profile: Optional[str] = None,
                          ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(UnitAbility = 0xb = 11)` -- emis par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` **APRES l'execution de la
    behaviour** et **AVANT** le gate `IsActiveAbility` qui conditionne `On(0xc)`. Sequence LUE au
    desassemblage du corps (`probe_928_legacy_of_combat.py --step 2` sur le voisin `0x2a`) :

        On(0x2a) -> gates -> execution -> **On(0xb)** -> if (IsActiveAbility) On(0xc)
                 -> AddFlagsAfterAbilityExecution -> On(0xe)

    ⚠ **INCONDITIONNEL**, contrairement a `0xc` : l'attaque NORMALE (qui est une active ability
    natif, `IsRegularAttack`) l'emet aussi. C'est ce qui en fait le vecteur du << after performing
    his first attack each turn >> de `1319 LegacyOfCombat`, dont le gate compte les attaques et
    n'a besoin d'AUCUN discriminant de kind.

    Emis par les DEUX voies du port, comme `0x2a`/`0xe` (#120) : `AbilityHandler.
    visit_ActiveAbilityMessage` pour un cast, `after_hit_normal_attack` pour l'attaque normale.
    N'emettre que d'un cote recreerait le fork que #120 a ferme.

    RANG vis-a-vis du COMPTEUR D'ATTAQUES : l'increment `ActorStatisticsComponent+0x24` est pose
    par `RegisterAttackOperation$$Execute` **pendant** l'execution de la behaviour (port :
    `components.register_attack_made`, appele par `AttackDamageOperation._apply_damage_pipeline`),
    donc AVANT ce vecteur. `TimesAttackMadeThisTurn(Owner)` y vaut deja 1 a la premiere attaque du
    tour -- c'est exactement ce que le trigger de 1319 teste (`AmountIsEqual(..., Direct(1))`).

    `ability_type` = `AbilityEntities.CurrentAbility` (`+0x60`), ce que lit
    `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs` : `0x3f5` (marqueur attaque-normale)
    sur la voie normale, l'`ActiveAbilityType` du cast sur la voie ability. SEUL consommateur
    porte : `LegacyOfCombatAdditionalAttackAbility` (#928)."""
    ev = TriggerEvent(EventTriggerType.UnitAbility, caster_id,
                      target_id if target_id is not None else caster_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def unit_active_ability_triggers(state: State, caster_id: int, target_id: Optional[int],
                                 ranged: bool, profile: Optional[str] = None,
                                 ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(UnitActiveAbility = 0xc = 12)` — emis par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` APRES l'execution de la behaviour
    et AVANT `AddFlagsAfterAbilityExecution`, **sous le gate**
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsActiveAbility`
    (sequence lue au decompile : `On(0xb)` inconditionnel -> `if (IsActiveAbility(t)) On(0xc)` ->
    `AddFlagsAfterAbilityExecution` -> `On(0xe)`).

    Ce gate est LOAD-BEARING : l'attaque NORMALE emprunte la meme operation mais est un
    `IsRegularAttack` -> elle n'emet PAS `0xc`. Le port n'emet donc ce vecteur que depuis la voie
    ABILITY (`AbilityHandler.visit_ActiveAbilityMessage`), et le gate y est re-applique tel quel (une
    ability du registre qui serait, elle, une attaque reguliere -- ex. 1076 MV71 -- reste muette).

    SEUL consommateur porte : `InspiredToGreatnessOverrideLevelRemove` (effet 1180, #114) — le retrait
    de l'override de niveau au PROCHAIN CAST D'ACTIF du porteur. AUCUN autre trigger porte n'ecoute
    `event_id == 12`. `ability_type` = `df@0x130` (l'ability declenchante), threade pour les gates
    kind des futurs consommateurs."""
    if not is_active_ability(ability_type):
        return []
    ev = TriggerEvent(EventTriggerType.UnitActiveAbility, caster_id,
                      target_id if target_id is not None else caster_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def evaluate_abilities_for_event(state: State, caster_id: int, target_id: int,
                                 event: int, ranged: bool,
                                 profile: Optional[str] = None,
                                 ability_type: Optional[int] = None,
                                 fire_of_absolution: bool = True) -> list[dict]:
    """Mirror `IdunBattle.Entities.Behaviours.EvaluateAbilitiesBehaviour$$Execute` (IdunBattle.Entities.Behaviours.EvaluateAbilitiesBehaviour$$.ctor, champ +0x50 = `EventTriggerType`)
    : EVALUE les abilities DÉCLENCHÉES du CASTER pour l'`EventTriggerType` `event`, INLINE dans un behaviour-tree
    (nœud DSL générique `IdunBattleLogic.Entities.DSLFactory$$EvaluateAbilities`). Callers natifs : NormalAttack
    `EvaluateAbilities(0x26)` (`ALoki_NormalAttackAbility$$ExecuteTriggerAbilities`) **et
    `EvaluateAbilities(0x4a, immediately: true)`** (`...$$ExecuteNormalAttack`, #521-r7), ArmoriumCherub
    `EvaluateAbilities(0x4a=AttackInAtomicGroup)`, ArmouredMight/TheQuickening (after-move).

    DEUX canaux, et c'est un fait du PORT, pas du natif (qui n'en a qu'un, `EvaluateTriggerOperation`) :

      * le passif ranged `FireOfAbsolution` est appele IMPERATIVEMENT (il n'est dans aucun registre) ;
      * tout le reste passe par `evaluate_trigger_operation`, donc par les registres. C'est ce second
        canal qui rend `PASSIVE_HELPER_ABILITY_TRIGGERS` atteignable sur cet event -- son seul
        consommateur aujourd'hui est `1316 CalibaniteGreatsword_NormalAttackAdditionalDamage`
        (#521-r4). Le premier canal reste separe pour ne PAS doubler `FireOfAbsolution`.

    `profile` / `ability_type` = les champs d'`AbilityEntities` que les gates des consommateurs lisent
    (`IsNormalAttack(CurrentAbility)` pour 1316). `None` = non threade sur ce site (le noeud DSL
    `EvaluateAbilities` d'une ability ne les renseigne pas) -> les gates de kind se TAISENT, ce qui est
    exactement le comportement natif pour un cast (`ArmoriumCherub` n'est pas une attaque normale).

    ⚠ `fire_of_absolution` -- `#521-r8` EST FERME, ET LE DRAPEAU RESTE, MAIS IL A CHANGE DE ROLE.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateTrigger` est
    `On(0x4a = AttackInAtomicGroup, ownerNeedsToBeAlive: 1) & get_OwnerIsActor & IsRangedAttack` --
    AUCUN gate excluant l'attaque normale. Le natif le fait donc fire sur l'attaque normale RANGED
    de son porteur, et il le fait DEPUIS CE VECTEUR. Le port le jouait IMPERATIVEMENT depuis
    `after_hit_normal_attack` (le vecteur `On(0x26)`) : comportement PRESENT, RANG FAUX -- apres
    `On(9)`/`On(10)`, apres le cleave, apres `On(0x26)`/`On(8)`, au lieu d'avant tout cela. Le RANG
    natif est lu dans `...ALoki_NormalAttackAbility$$ExecuteNormalAttack` :

        b = GetAttackDamageBehaviour(...)                     # coups d'ARME + FOLD primaire
        b = b op_BitwiseAnd EvaluateAbilities(dsl, 0x4a, immediately: true)     # <- ICI
        return ExecuteAtomic(this, b, entities, 0x3d)
        # ... puis, dans `Execute<X>` : le CLEAVE (`ExecuteAtomic(.., 0x2a)`), puis
        #     `ExecuteTriggerAbilities` -> `EvaluateAbilities(0x26)`

    ⚠ **LA FICHE DU RESIDU DISAIT « avant `On(0x26)`/`On(9)`/`On(10)` » -- ET C'EST FAUX POUR DEUX
    DES TROIS.** `On(9)` et `On(10)` sortent de `FinishAttackOperation$$Execute`, que le noeud
    `Attack(...)` de `GetAttackDamageBehaviour` traverse AVANT que `ExecuteNormalAttack` ne compose
    `EvaluateAbilities(0x4a)`. L'ordre natif est donc `On(9)` -> `On(10)` -> **`On(0x4a)`** ->
    cleave -> `On(0x26)`. Seul `On(0x26)` etait correctement decrit.

    Le drapeau n'est donc plus un ANTI-DOUBLE-FIRE (il n'y a plus qu'UN site) : il reste le point de
    MUTATION qui permet a une contre-epreuve de desarmer ce seul canal sans toucher au bus, et le
    defaut est desormais `True` sur les DEUX voies -- la voie NORMALE comme la voie ABILITY
    (`ArmoriumCherub`, noeud DSL)."""
    out: list[dict] = []
    if fire_of_absolution and int(event) == int(EventTriggerType.AttackInAtomicGroup):
        out += _fire_of_absolution_after_attack(state, caster_id, target_id, ranged)
    ev = TriggerEvent(int(event), caster_id, target_id, ranged=ranged, profile=profile,
                      ability_type=ability_type,
                      is_normal_attack=(None if ability_type is None
                                        else is_normal_attack(ability_type)))
    return out + evaluate_trigger_operation(state, ev)
