"""Vecteurs d'event de la face ABILITY (init, pre-cast, post-cast, cast actif, evaluation
inline), extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169
-- deplacement VERBATIM, zero changement de comportement).

`On(AbilityInit=0x21)`, `On(PreUnitAbility=0x2b)`, `On(UnitPostAbility)`,
`On(UnitActiveAbility)`, plus `evaluate_abilities_for_event` (noeud DSL `EvaluateAbilities`)."""
from __future__ import annotations

from typing import Optional

from ....state import State
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggerEvent
from ..loki import _fire_of_absolution_after_attack
from .core import evaluate_trigger_operation


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
    """Vecteur `On(PreUnitAbility=0x2b=43)` — emis par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (`FUN_180026490(0x4d, .., 0x2b)`)
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
        muets face a une ability offensive.
    AUCUN autre trigger porte n'ecoute `event_id == 0x2b`."""
    ev = TriggerEvent(EventTriggerType.PreUnitAbility, caster_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def unit_post_ability_triggers(state: State, caster_id: int, target_id: int,
                               ranged: bool, profile: Optional[str] = None,
                               ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(UnitPostAbility=0xe=14)` — DERNIER evenement emis par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (`FUN_180026490(0x4d, .., 0xe)`),
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
    from ....abilities.attack_type import is_active_ability   # lazy : coherent avec les autres vecteurs
    if not is_active_ability(ability_type):
        return []
    ev = TriggerEvent(EventTriggerType.UnitActiveAbility, caster_id,
                      target_id if target_id is not None else caster_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def evaluate_abilities_for_event(state: State, caster_id: int, target_id: int,
                                 event: int, ranged: bool) -> list[dict]:
    """Mirror `IdunBattle.Entities.Behaviours.EvaluateAbilitiesBehaviour$$Execute` (IdunBattle.Entities.Behaviours.EvaluateAbilitiesBehaviour$$.ctor, champ +0x50 = `EventTriggerType`)
    : EVALUE les abilities DÉCLENCHÉES du CASTER pour l'`EventTriggerType` `event`, INLINE dans un behaviour-tree
    (nœud DSL générique `IdunBattleLogic.Entities.DSLFactory$$EvaluateAbilities`). Callers natifs : NormalAttack
    `EvaluateAbilities(0x26)`, ArmoriumCherub `EvaluateAbilities(0x4b=AttackInAtomicGroup)`, ArmouredMight/
    TheQuickening (after-move).

    `AttackInAtomicGroup` (attaque d'ability ATOMIQUE du caster, ex. ArmoriumCherub `ExecuteAtomic`) -> le passif
    ranged `FireOfAbsolution` (SEUL passif de ce chemin PORTÉ ; les autres after-hit de l'attaque primaire fire
    déjà DANS l'Operation d'attaque via `after_hit_ability_attack`). Ranged-only (FireOfAbsolution ne fire que
    sur attaque RANGED). No-op pour tout autre event (rien d'autre porté ici). Extensible : un futur passif
    keyé sur cet event s'ajoute ici."""
    out: list[dict] = []
    if int(event) == int(EventTriggerType.AttackInAtomicGroup):
        out += _fire_of_absolution_after_attack(state, caster_id, target_id, ranged)
    return out
