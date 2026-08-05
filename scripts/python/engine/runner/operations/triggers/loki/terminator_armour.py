"""`1147 TerminatorArmour_ReduceDmg` — le CYCLE d'armement de l'armure Terminator (44 porteurs).

i2 (`Traits/TerminatorArmour_Description`) : « **The first attack each turn** against this unit deals
{[dmgPctReduction]}% Damage. Hits dealing Psychic or Direct Damage are excluded. This unit cannot be
Suppressed. »

Le port portait la REDUCTION (`entities/effects/loki/damage_reduction.py::TerminatorArmourReduceDmgEffect`,
-75 % gate profil) mais AUCUN cycle : l'effet restait arme en permanence, donc **TOUTES** les attaques
recues etaient reduites, pas seulement la premiere de chaque tour. Ce module porte le cycle
ACTIVATE / DEACTIVATE qui manquait.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) — decompile = verite
================================================================================================

    IdunBattle.Entities.Effects.Loki.TerminatorArmour_ReduceDmg_Effect
        : IdunBattle.Entities.Effects.PlayerTurnEffect
        : IdunBattle.Entities.Effects.BaseEffect                        (classes.tsv)

## 1. Le CTOR — quelle fenetre, quelle frequence

    TerminatorArmour_ReduceDmg_Effect$$.ctor =
        PlayerTurnEffect..ctor(this,
                               turnsEnabled        = 2,
                               activationFrequency = 1,
                               sourceAbility       = Nullable(AbilityOrEffect(0x476 = 1142)))

Les deux litteraux sont LUS a l'assembleur (`mov edx, 0x476` avant `AbilityOrEffect$$op_Implicit`),
et les deux enums sont dans le dump du build :

    IdunBattle.Entities.Effects.PlayerTurnEffect.TurnsEnabled          0=Player, 1=Enemy, **2=Both**
    IdunBattle.Entities.Effects.PlayerTurnEffect.ActivationFrequency   0=Automatic, **1=PerTurn**, 2=PerRound
    IdunBattle.Entities.Enum.TriggeredAbilityType                      **1142=TerminatorArmour**

## 2. La FENETRE — `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal`, branche freq **1**

    On(0x12 = TurnStart_EffectActivation) & IsEnabledTurnType()  -> ActivateEffect(<Sel+0x38>)
    On(0x17 = TurnEnd)                    & IsEnabledTurnType()  -> DeactivateEffect(<Sel+0x38>)

(⚠ la branche freq **2**, celle de `WireweaveNet_CounterAttack`, est l'INVERSE : deactivate au
turn-start, activate au turn-end. Ne pas transposer l'une sur l'autre.)

    PlayerTurnEffect$$IsEnabledTurnType =
        turnsEnabled == 2 -> <DSLTriggers+0x70>
        turnsEnabled == 0 -> <DSLTriggers+0x28>          # IsTurnOf(Owner)
        sinon             -> NOT <DSLTriggers+0x28>

`<DSLTriggers+0x28>` est construit par `DSLTriggers$$InitializeShared` sur `<DSLSelectors+0x30>`
(= Owner) : c'est `IsTurnOf(Owner)`, deja etabli par case-366-r1 §2 et par `wireweave_net.py`.
`<DSLTriggers+0x70>` est le TROISIEME singleton du `.ctor` de `DSLTriggers` (meme classe et meme
argument `0` que `+0x40`, dont `+0x48` est la NEGATION) -> cf. RESIDUS.

=> `TurnsEnabled.Both` : l'armure est **ARMEE au debut de CHAQUE tour** (le sien comme celui de
l'adversaire) et DESARMEE a la fin de chaque tour.

Le TROISIEME `Triggered()` de la meme methode (`On(0x2e = UnitResurrected) & OwnerIsTarget ->
ActivateEffect`) est gate par un virtuel booleen (`vtable +0x728`) dont l'implementation sur la
chaine `PlayerTurnEffect` est un stub `return 0` (meme constat que `wireweave_net.py` §2) -> NON
BATI, donc non porte.

## 3. LA CONSOMMATION — `$$CreateTargetTrigger` / `$$CreateTargetTriggerBehaviour`

    TerminatorArmour_ReduceDmg_Effect$$CreateTargetTrigger =
          On(9 = Attack, true)
        & AreEqual( Units(<Sel+0x60 = Target>, true, 3), <Sel+0x30 = Owner> )
        & CurrentAttackDamageProfilesContainOtherThan(
              GetEnumArrayConstant(config@+0x60, 0x52), includeNotApplied = true)
        & AmountIsZero( CurrentShieldAmount(<Sel+0x60 = Target>, 3) )
        & (   AmountIsGreaterThanZero( HealthDamageFromEvent() )
            | WasBlock() )

    TerminatorArmour_ReduceDmg_Effect$$CreateTargetTriggerBehaviour =
          DeactivateEffect(effect)

Le mapping des slots `DSLSelectors` est LU, pas suppose : `DSLTriggers$$get_OwnerIsTarget` =
`AreEqual(<+0x30>, <+0x60>)`, `$$get_OwnerIsActor` = `AreEqual(<+0x30>, <+0x40>)`,
`$$get_OwnerIsCaster` = `AreEqual(<+0x30>, <+0x48>)` -> **+0x30 Owner · +0x38 Effect · +0x40 Actor ·
+0x48 Caster · +0x60 Target** (l'ordre etabli par `wireweave_net.py`, ici re-derive et etendu au
slot Target).

**GRANULARITE — c'est le coeur du cas.** `On(9 = Attack)` est emis par
`IdunBattle.Operations.FinishAttackOperation$$Execute`, **UNE SEULE FOIS PAR ATTAQUE**, a sa
CLOTURE (`FUN_1800280e0(0x50, .., 9, entities)` inconditionnel, suivi du `On(10)` gate
`currentAttack@+0x2c`). La desactivation tombe donc APRES le dernier coup : **tous les coups de la
premiere attaque sont reduits**, et c'est la DEUXIEME attaque du meme tour qui ne l'est plus.
Le regime « premier COUP seulement » n'existe pas (il exigerait `On(8 = AttackHit)`), et le regime
mono-coup est DEGENERE (les deux lectures y coincident) : le discriminant est **deux attaques dans
le meme tour**, pas le nombre de coups.

## 4. LE JUMEAU `_Visual` (1375) — il ne reduit RIEN

    IdunBattle.Entities.Effects.Loki.TerminatorArmour_Visual_Effect
        : IdunBattle.Entities.Effects.Loki.TerminatorArmour_ReduceDmg_Effect     (classes.tsv)

    TerminatorArmour_Visual_Effect$$CreateEffectDamageMalusForDefense =
        { zeroe les 0x58 octets du `Nullable<EffectBonus>` de retour ; AUCUN ctor }

C'est un `return null` : la sous-classe NEUTRALISE la reduction de sa base. `_Visual` est un pur
marqueur d'affichage (`TerminatorArmour_AddVisualEffectAbility$$GetEffectType = 0x55f = 1375`, pose
par le meme `AOwnerEffectTriggeredAbility` que `_AddEffectAbility$$GetEffectType = 0x47b = 1147`).
Cote port il n'a AUCUNE classe dans `EffectFactory` -> il est deja inerte, et il ne doit surtout pas
en recevoir une. Aucun trigger n'est enregistre pour 1375 ici : son etat actif/inactif n'a aucun
observable de degat.

================================================================================================
RESIDUS EXPLICITES
================================================================================================
 * `<DSLTriggers+0x70>` (le conjoint de `TurnsEnabled.Both`) est un SINGLETON non qualifie : sa
   classe est celle de `<+0x40>`, construite avec le MEME argument (`0`), et `<+0x48>` en est la
   negation logique. Le port le lit **TRIVIALEMENT VRAI**, ce qui est la seule lecture compatible
   (a) avec le nom de la valeur d'enum (`Both` = l'union de `Player` et `Enemy`, dont les deux
   autres branches d'`IsEnabledTurnType` sont exactement le trigger et sa negation), (b) avec
   `DSLTriggers$$InitializeShared`, qui l'utilise comme conjoint de `On(0x21) & OwnerIsActor` et de
   `On(0x41) & OwnerIsActor` (un conjoint FAUX y rendrait ces deux singletons morts), et (c) avec
   l'i2 (« each turn »). Confronte LIVE par le re-armement au tour suivant.
 * `includeNotApplied = true` (2e argument de `CurrentAttackDamageProfilesContainOtherThan`) n'est
   pas modelise : le port ne connait que le SET des profils de l'attaque (`ev.profiles`), sans
   distinguer les coups appliques des coups annules.
 * `Units(<Target>, true, 3)` est collapse en « la cible de l'evenement EST le porteur » : le port
   n'a qu'UNE cible d'evenement (une entite), pas un ensemble.
 * `On(9)` du port vit au niveau MESSAGE (attaque normale) / SORTIE D'OPERATION (attaque d'ability)
   -- une attaque declenchee par un TRIGGER (le tir d'overwatch) ne le traverse pas (divergence
   STRUCTURELLE preexistante, documentee dans `dispatch/attack.py::attack_damage_attack_triggers`).
   Consequence pour ce cas : un tir d'overwatch sur un porteur d'armure ne consomme pas son armure
   cote port, alors qu'il la consomme cote natif. RESIDU NOMME, non elargi ici.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from ....state import State
from ....components import ShieldComponent
from ..base import EffectTrigger, TriggerEvent
from .....entities.effects.loki.damage_reduction import _terminator_excluded_profiles

TERMINATOR_ARMOUR_REDUCE_DMG = int(EffectType.TerminatorArmour_ReduceDmg)   # 0x47b = 1147


def _instances(state: State, owner_id: int) -> list:
    """Les instances 1147 NON consommees portees par `owner_id` — les entites-effet dont les
    `Triggered()` ci-dessous ecrivent `EffectComponent.IsActive @+0x5c` (`e.active`). Liste et non
    instance unique parce que le natif raisonne PAR ENTITE-EFFET ; en pratique `AddEffectOperation`
    no-ope sur un meme-type deja present, donc il y en a 0 ou 1. (Meme helper que
    `wireweave_net.py::_instances` / `effect_triggers.py::_ranged_auto_attack_instances`.)"""
    if state.effects is None:
        return []
    return [e for e in state.effects.by_unit.get(int(owner_id), [])
            if not e.consumed and e.effect_type == TERMINATOR_ARMOUR_REDUCE_DMG]


def _set_active(state: State, owner_id: int, value: bool) -> bool:
    """Ecrit `EffectComponent.IsActive @+0x5c` — mirror de
    `IdunBattle.Operations.RefreshEffectsOperation$$ActivateEffect` (`+0x5c = 1`) /
    `$$DeactivateEffect` (`+0x5c = 0`, precede du gate « deja inactif -> no-op »). Renvoie True si un
    flag a CHANGE (permet de ne rien emettre quand l'ecriture est un no-op, comme le natif)."""
    changed = False
    for e in _instances(state, owner_id):
        if bool(e.active) != bool(value):
            e.active = bool(value)
            changed = True
    return changed


def _flag_is_set(state: State, owner_id: int) -> bool:
    """Le flag `EffectComponent.IsActive @+0x5c` de l'instance — mirror EXACT du gate que
    `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` applique AVANT
    d'evaluer le trigger de CIBLE (`if (*(char *)(effectEntity + 0x5c) == 0) -> pas d'evaluation`).
    C'est le rail TARGETS : il DOIT lire le flag, contrairement au rail ARRAYSET des trois autres
    `Triggered()` (cf. `probe_229_effect_triggers_active`). Aucune instance -> True (degradation
    PERMISSIVE : on ne fabrique pas un refus ; si l'effet est reellement absent,
    `collect_effect_triggers` n'aura instancie aucun trigger). MEME convention que
    `wireweave_net._flag_is_set` et `effect_triggers._ranged_auto_attack_flag_is_set`."""
    insts = _instances(state, owner_id)
    return (not insts) or any(e.active for e in insts)


def _total_shield(state: State, owner_id: int) -> int:
    """`CurrentShieldAmount(<Sel+0x60 = Target>, 3)` -> `ShieldComponent.GetTotalShield` du porteur.
    LU AU MOMENT DE L'EVENEMENT, donc APRES la deplétion du bouclier par l'attaque qui vient de se
    resoudre (`On(9)` est emis a la CLOTURE) — un bouclier qui vient d'etre casse rend bien 0 ici, et
    l'armure EST consommee. Composant absent -> 0 (aucun bouclier)."""
    e = state.get_entity(int(owner_id))
    sc = e.get_component(ShieldComponent) if e is not None else None
    return int(sc.get_total_shield()) if sc is not None else 0


def _attack_profiles(ev: TriggerEvent) -> set:
    """Le SET des profils de degat de l'attaque courante (mirror du `CurrentAttack` que lit
    `CurrentAttackDamageProfilesContainOtherThan`). `ev.profiles` est le canal complet (arme + coups
    bonus heterogenes #179) quand l'emetteur le threade ; a defaut on retombe sur le profil primaire
    seul — MEME repli que les autres consommateurs de ce canal (cf. `TriggerEvent.profiles`)."""
    if ev.profiles:
        return set(ev.profiles)
    return {ev.profile} - {None}


class TerminatorArmourDeactivateOnAttack(EffectTrigger):
    """`TerminatorArmour_ReduceDmg_Effect$$CreateTargetTrigger` +
    `$$CreateTargetTriggerBehaviour` — la CONSOMMATION de l'armure (cf. §3 de l'en-tete).

    C'est LUI qui porte le « **the first attack each turn** » d'i2 : l'armure se desactive a la
    cloture de la premiere attaque QUALIFIANTE du tour, et le contrepoids `On(0x12)` la re-arme au
    tour suivant."""
    event_id = EventTriggerType.Attack                      # On(9), emis par FinishAttackOperation
    effect_type = TERMINATOR_ARMOUR_REDUCE_DMG

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # (0) gate `EffectComponent.IsActive @+0x5c` — premier test d'`EvaluateEffectTriggerTargets`,
        #     AVANT toute evaluation du trigger de cible. Une armure DEJA consommee ne se re-consomme
        #     pas : c'est le rail TARGETS (cf. `_flag_is_set`).
        if not _flag_is_set(state, self.owner_id):
            return False
        # (a) `AreEqual(Units(Target), Owner)` = le porteur EST la cible de l'attaque.
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False
        # (b) `CurrentAttackDamageProfilesContainOtherThan(<terminatorArmourExcludedDmgProfiles>)` :
        #     une attaque PUREMENT Psychic/DirectDamage ne consomme pas l'armure (et ne beneficie pas
        #     non plus de la reduction — meme tableau, cf. `CreateEffectDamageMalusForDefense`).
        #     Profils inconnus (aucun canal threade) -> FAUX : on ne fabrique pas une consommation.
        excluded = _terminator_excluded_profiles()
        profs = _attack_profiles(ev)
        if not profs or not any(p not in excluded for p in profs):
            return False
        # (c) `AmountIsZero(CurrentShieldAmount(Target))` : tant qu'il reste du bouclier, l'armure
        #     n'est PAS consommee.
        if _total_shield(state, self.owner_id) != 0:
            return False
        # (d) `AmountIsGreaterThanZero(HealthDamageFromEvent()) | WasBlock()` : l'attaque doit avoir
        #     entame les PV, OU avoir ete bloquee. Une attaque entierement esquivee/annulee ne
        #     consomme rien. Canaux non threades -> FAUX (cf. `TriggerEvent.health_damage`).
        hd = ev.health_damage
        if (hd is not None and int(hd) > 0) or bool(ev.was_block):
            return True
        return False

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _set_active(state, self.owner_id, False):
            return None                                     # gate natif « deja inactif -> no-op »
        return {"effect": "TerminatorArmour_ReduceDmg", "owner": int(self.owner_id),
                "deactivated": "attack_absorbed"}


class TerminatorArmourActivateOnTurnStart(EffectTrigger):
    """1er `Triggered()` de la branche `ActivationFrequency == 1 (PerTurn)` de
    `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal` :

        On(0x12 = TurnStart_EffectActivation) & IsEnabledTurnType() -> ActivateEffect(<Sel+0x38>)

    `IsEnabledTurnType()` vaut `<DSLTriggers+0x70>` pour `TurnsEnabled.Both` (le litteral du ctor)
    -> trivialement vrai, donc l'armure se RE-ARME au debut de CHAQUE tour, sans gate de joueur.
    C'est le CONTREPOIDS de `TerminatorArmourDeactivateOnAttack` : sans lui la premiere attaque
    encaissee de la bataille serait aussi la derniere a etre reduite.

    `EvaluateEffectTriggerEffectAbilities` (la voie de ces `Triggered()`) n'applique AUCUN gate
    `IsActive`, contrairement a `EvaluateEffectTriggerTargets` — c'est ce qui permet de RE-activer
    une instance desactivee ; le port fait pareil (`collect_effect_triggers` ne filtre pas sur
    `e.active`)."""
    event_id = EventTriggerType.TurnStart_EffectActivation   # On(0x12)
    effect_type = TERMINATOR_ARMOUR_REDUCE_DMG

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True                                          # TurnsEnabled.Both -> aucun gate de tour

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _set_active(state, self.owner_id, True):
            return None                                      # deja actif -> aucune ecriture (no-op)
        return {"effect": "TerminatorArmour_ReduceDmg", "owner": int(self.owner_id),
                "activated": "turn_start"}


class TerminatorArmourDeactivateOnTurnEnd(EffectTrigger):
    """2e `Triggered()` de la meme branche :

        On(0x17 = TurnEnd) & IsEnabledTurnType() -> DeactivateEffect(<Sel+0x38>)

    DESARME l'armure a la fin de chaque tour. Observationnellement redondant avec le re-armement de
    `On(0x12)` qui suit immediatement (rien ne frappe entre les deux vecteurs), mais porte quand
    meme : 1 `Triggered()` natif = 1 artefact offline, et c'est LUI qui explique qu'une capture prise
    au boundary de tour puisse ne PAS voir 1147 dans `decisionView` (canal actifs-seuls)."""
    event_id = EventTriggerType.TurnEnd                      # On(0x17)
    effect_type = TERMINATOR_ARMOUR_REDUCE_DMG

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True                                          # TurnsEnabled.Both -> aucun gate de tour

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _set_active(state, self.owner_id, False):
            return None                                      # gate natif « deja inactif -> no-op »
        return {"effect": "TerminatorArmour_ReduceDmg", "owner": int(self.owner_id),
                "deactivated": "turn_end"}


class TerminatorArmourActivateOnEffectAdded(EffectTrigger):
    """Le `Triggered()` PROPRE a `TerminatorArmour_ReduceDmg_Effect$$CreateHandleTriggerAbilitiesInternal`
    (ajoute a l'`ArraySet` rendu par la base) :

        On(0x3e = 62 EffectAdded)
          & AreEqual( <Sel+0x90 = TriggeringAbilityOrEffect>,
                      Direct(AbilityOrEffect(this@+0x10)) )      # = TriggeringEffectIs(1147)
          & AreEqual( <Sel+0x48 = Caster>, OwnerOfEffect(<Sel+0x38 = Effect>) )
        -> ActivateEffect(<Sel+0x38>)

    Le litteral de `Direct(...)` est LU a l'assembleur : `mov edx, [rdi+0x10]` juste avant
    `AbilityOrEffect$$op_Implicit`, ou `rdi` est l'effet — `BaseEffect+0x10` est son propre id
    (le `.ctor` de `BaseEffect` ecrit +0x14..+0x3c et JAMAIS +0x10). C'est donc « une instance de
    CE type d'effet vient d'etre posee ». `<Sel+0x90>` est le slot que prennent
    `DSLTriggers$$TriggeringEffectIs` / `$$TriggeringAbilityIs` / `$$TriggeringAbilityIsNone`
    (etabli par `TriggerEvent.triggering_effect`), et `AddEffectOperation$$Execute` y ecrit bien
    `AbilityOrEffect(effectType)` (#306).

    STRUCTURELLEMENT INERTE aujourd'hui, et c'est une lecture, pas une supposition : le SEUL poseur
    de 1147 est `TerminatorArmour_AddEffectAbility` (`GetEffectType = 0x47b`), dont le
    `CreateTrigger` herite d'`AOwnerEffectTriggeredAbility` = `OnOwnerSpecificAbilityInit(this.Id)`
    et dont le `CreateBehaviour` pose l'effet avec une duree ZEROEE (permanent) — il n'y a donc
    aucun chemin de RE-pose en cours de bataille. Porte quand meme (1 `Triggered()` natif = 1
    classe) ; son cout est nul pour toute unite qui ne recoit pas un 1147 neuf."""
    event_id = EventTriggerType.EffectAdded                   # On(0x3e = 62)
    effect_type = TERMINATOR_ARMOUR_REDUCE_DMG

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.triggering_effect is None or int(ev.triggering_effect) != TERMINATOR_ARMOUR_REDUCE_DMG:
            return False
        # `AreEqual(Caster, OwnerOfEffect(Effect))` : sur le vecteur d'AJOUT, `caster == actor ==
        # la SOURCE` de l'effet pose (#306) ; `OwnerOfEffect(<mon effet>)` est mon porteur.
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _set_active(state, self.owner_id, True):
            return None                                       # deja actif -> aucune ecriture (no-op)
        return {"effect": "TerminatorArmour_ReduceDmg", "owner": int(self.owner_id),
                "activated": "effect_added"}
