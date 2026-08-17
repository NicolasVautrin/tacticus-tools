"""`1111 WireweaveNet_CounterAttack` — la RIPOSTE de `eldarRanger` (Calandis), portee par un EFFET.

i2 : « The first time Calandis is targeted by a normal melee attack during the enemy's turn, the
attacker immediately takes 2x 873-1310 Piercing Damage. If the attacker is eliminated, their melee
attack is not executed. »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) — decompile = verite
================================================================================================
Chaine COMPLETE, de l'ability a la riposte (chaque maillon LU, aucun deduit du nom) :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.WireweaveNetAbility
        : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility   (classes.tsv)
    IdunBattle.Entities.Effects.Loki.WireweaveNet_CounterAttackEffect
        : IdunBattle.Entities.Effects.CounterAttackEffect
        : IdunBattle.Entities.Effects.PlayerTurnEffect
        : IdunBattle.Entities.Effects.BaseEffect                       (classes.tsv)

## 1. La POSE — `AOwnerEffectTriggeredAbility$$CreateTrigger` + `WireweaveNetAbility$$CreateBehaviour`

    CreateTrigger   = OnOwnerSpecificAbilityInit(this.Id@+0x10)          # a l'INIT de l'ability
    CreateBehaviour = AddEffect(GetEffectType()=0x457, <AbilityStateReference>,
                                source = Owner@<DSLSelectors+0x30>,
                                targets = Owner@<DSLSelectors+0x30>, <duree ZEROEE>)
                    + If( NOT <DSLTriggers+0x28>,                        # NOT IsTurnOf(Owner)
                          ActivateEffect(Owner, 0x457) )

`WireweaveNetAbility$$GetEffectType` = `return 0x457` (= 1111 en **EffectType**) — a ne pas confondre
avec le `0x457` que le `.ctor` de l'effet passe en **TriggeredAbilityType** (cf. la docstring de
`WireweaveNetCounterAttackEffect`). Le corps de `CreateBehaviour` est celui de la BASE
(`AOwnerEffectTriggeredAbility$$CreateBehaviour` = `If(CreateCondition, AddEffect(...))`) auquel
`WireweaveNetAbility` substitue son propre `If(NOT IsTurnOf(Owner), ActivateEffect)` — c'est
litteralement le corps de `WireweaveNetAbility$$ActivateEffectIfOwnerTurn`, inline.

Port : `factory.ABILITY_INIT_OWNER_EFFECTS["WireweaveNet"] = ["WireweaveNet_CounterAttack"]` (meme
mecanisme qu'`AnvilShield`/`HammerOfWrath`/`ModifiedExoarmour`/`VisionsOfHeresy`). Il FAUT ce seed :
l'effet est INACTIF pendant le tour de son porteur, donc absent du canal `decisionView` par DEFAUT
(actifs seuls) — un runner capture pendant le tour de Calandis n'aurait AUCUNE instance a armer.

## 2. La FENETRE D'ARMEMENT — `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal`, branche freq 2

    On(0x12 = TurnStart_EffectActivation) & <DSLTriggers+0x28>  -> DeactivateEffect(<Sel+0x38>)
    On(0x17 = TurnEnd)                    & <DSLTriggers+0x28>  -> ActivateEffect(<Sel+0x38>)

(`<DSLTriggers+0x28>` = `IsTurnOf(Owner)`, cf. case-366-r1 §2 ; `<DSLSelectors+0x38>` = le slot
EFFET, celui que prennent `Activate/Deactivate/RemoveEffect` — l'ordre des slots `+0x30 Owner ·
+0x38 Effect · +0x40 Actor · +0x48 Caster` mirrore celui du `DSLFactory` `0x148 Owner · 0x150 Effect ·
0x158 Actor · 0x160 Caster` deja etabli dans `entities/selectors/accessors.py`.)

=> l'effet est ARME de la fin du tour de Calandis jusqu'au debut de son tour suivant = le tour ENNEMI.

Le TROISIEME `Triggered()` de la meme methode (`On(0x2e = UnitResurrected) & OwnerIsTarget ->
ActivateEffect`) est gate par un virtuel booleen (`vtable +0x728`) dont l'implementation sur cette
chaine est un stub `return 0` (le groupe de methodes de `PlayerTurnEffect` dans la table
`methodPointers` contient exactement un `xor eax,eax ; ret`) -> **non bati**. Sans consequence
observable de toute facon : il ne concerne que la resurrection du porteur.

## 3. LA RIPOSTE — `CounterAttackEffect$$CreateTargetTrigger` / `$$CreateTargetTriggerBehaviour`

    CreateTargetTrigger =
          GetCounterAttackTrigger()              # vtable +0x778
        & <DSLTriggers+0x20>                     # conjoint SINGLETON non qualifie (cf. RESIDUS)
        & GetCounterAttackCondition()            # vtable +0x788
        & AreEnemies(Caster@<Sel+0x48>, Owner@<Sel+0x30>, 0)
        & IsAlive(Caster@<Sel+0x48>)

    WireweaveNet_CounterAttackEffect$$GetCounterAttackTrigger   = On(0x2a = PreUnitAbility, true)
    WireweaveNet_CounterAttackEffect$$GetCounterAttackCondition =
          get_OwnerOrOwnerTileIsTarget & IsMeleeAttack & IsNormalAttack

    CreateTargetTriggerBehaviour =
          GetCounterAttackBehaviour(effect)      # vtable +0x748
        & DeactivateEffect(effect)               # gate vtable +0x738 = stub `return 1` -> TOUJOURS

`0x2a = 42 = PreUnitAbility` (VERIFIE contre `frida/enums.tsv`, pas deduit : 43 = `UnitHealed`) —
la riposte part **AVANT** que l'attaque adverse ne s'execute, exactement comme `MartialSuperiority`
(#133). C'est ce qui rend observable le « If the attacker is eliminated, their melee attack is not
executed » : le gate ACTEUR-MORT post-`On(PreUnitAbility)` d'`ActiveAbilityOperation$$ExecuteInternal`
est DEJA porte (cf. l'en-tete de `martial_superiority.py`), sur les deux voies.

`DeactivateEffect(effect)` est ce qui porte le « **the FIRST time** » : le gate de son `if` est le
virtuel `vtable +0x738`, dont l'implementation sur cette chaine est le stub `return 1` — le PREMIER
membre du groupe `CounterAttackEffect` de la table `methodPointers` (adresse `0x1802b4590`, corps
`mov eax,1 ; ret`, partage avec `UnityEngine.U2D.IK.Solver2D$$DoValidate`). L'`ArraySet` de
`PlayerTurnEffect` le re-arme a la fin du tour du porteur (§2).

## 4. LE DEGAT — `CounterAttackEffect$$AttackDamage`

    WireweaveNet_CounterAttackEffect$$GetCounterAttackBehaviour =
        CounterAttackEffect$$AttackDamage( effect,
                                           damageProfile = GetDamageProfile(config@+0x60),
                                           hits          = GetNumberConstant(config@+0x60, 0x2f) )

    CounterAttackEffect$$AttackDamage =
        DSLBehaviors.AttackWithAttackDamage( caster  = Owner@<Sel+0x30>,
                                             targets = GetCounterAttackTargets()  # vtable +0x768
                                             amount  = GetDamage(effect),         # vtable +0x758
                                             damageProfile, hits,
                                             source  = <this.SourceAbility ?? AbilityOrEffect()> )

    WireweaveNet_CounterAttackEffect$$GetCounterAttackTargets = <DSLSelectors+0x48>   # Caster
    WireweaveNet_CounterAttackEffect$$GetDamage               = BaseEffect$$GetMinMaxDamage(0)

gameconfig `WireweaveNet` : `attackRangeType = Melee`, `constants = {damageProfile: "Piercing",
nrOfHits: "2"}`, `variables = {minDmg[65], maxDmg[65]}` avec
`variablesAffectedByRarityBonus = ["minDmg","maxDmg"]` (niveau 50 : 665-997 AVANT multiplicateur de
rarete ; niveau 65 : 873-1310). `WireweaveNet` est le PASSIF d'`eldarRanger` (`unit_map kit`) ->
`level_slot="passive"`.

================================================================================================
RESIDUS EXPLICITES
================================================================================================
 * `<DSLTriggers+0x20>` : noeud-trigger SINGLETON du factory (classe `DAT_183343468` instanciee
   UNIQUEMENT par `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`, et LUE nulle part ailleurs
   que dans `CounterAttackEffect$$CreateTargetTrigger` — `list_xrefs` rend DEUX references, toutes
   deux dans `InitializeShared`). Elle ne recoit que `factory@+0x10` (le service DSL) : aucun
   selecteur d'owner/cible ne lui est passe, donc elle ne peut porter qu'une condition GLOBALE.
   MEME traitement que le conjoint `ctx@0x90` de `MartialSuperiorityAbility$$CreateTrigger` et que
   le `ctx@0x98` des `Triggered()` d'overwatch (case-127 §8.3) : non qualifie, NON porte, la mesure
   live tranche (elle confirme que la riposte part).
 * Le natif lit la cible de la riposte dans le slot **`Caster`** (`<DSLSelectors+0x48>`), pas
   `Actor` ; sur le vecteur `On(PreUnitAbility)` publie par `ActiveAbilityOperation` les deux slots
   designent la MEME entite (l'attaquant), et c'est elle que `TriggerEvent.actor_id` porte. Le port
   n'a pas de canal caster-de-l'evenement distinct d'`actor` -> `Actor()`, comme
   `MartialSuperiorityAbility$$GetInitialTarget` (qui, lui, lit bien `Actor@0x158`).
 * `AttackWithAttackDamage` recoit `source = AbilityOrEffect{TriggeredAbility = 1111}`. Le canal
   `ability_type` du port est keye sur l'espace `ActiveAbilityType` des gates
   `IsNormalAttack`/`AbilityHasAttackType` -> non threade (MEME choix que `MartialSuperiority` et
   `MartialApotheosis`, qui recoivent aussi leur propre id).
 * `get_OwnerOrOwnerTileIsTarget` = `AreEqual(Target, Owner) | AreEqual(Target, Tiles(Owner))` : le
   port n'a qu'UNE cible d'evenement (une entite) -> la 2e branche (cible = la TUILE du porteur) est
   structurellement couverte par la 1re (aucun vecteur porte ne cible la tuile d'une unite occupee).
   MEME residu que `martial_superiority.py`.
 * Quatre SOEURS non portees, faute de porteur confrontable dans ce cas :
   `GrimRetribution_CounterAttackEffect` (1213), `SmashaSquigJaws_CounterAttackEffect` (1104),
   `UnwaveringSentinel_CounterAttackEffect` (1439), `WarConstruct_CounterAttackEffect` (1286).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Actor
from ....state import State
from ....components import OwnerComponent, UnitComponent
from ....abilities.attack_type import is_normal_attack
from ..base import EffectTrigger, TriggerEvent, _is_adjacent_units
from .....dsl.effects import ExecutionContext
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from . import counter_attack as _ca     # forme B (cf. la note au-dessus des quatre delegations)

WIREWEAVE_NET_COUNTER_ATTACK = int(EffectType.WireweaveNet_CounterAttack)   # 0x457 = 1111
WIREWEAVE_NET = "WireweaveNet"          # nom gameconfig de l'ability SOURCE (passif d'`eldarRanger`)
_PROFILE = "Piercing"                   # `GetDamageProfile(cfg)` -> constants.damageProfile


#: Les QUATRE lectures/ecritures de la BASE `PlayerTurnEffect` vivent depuis #946 dans le foyer
#: PARTAGE `loki/counter_attack.py` (elles sont identiques pour les trois membres portes de la
#: famille, parce qu'elles n'appartiennent a AUCUN d'eux). Liaison en forme B (`import <module>` puis
#: acces attributaire) et non `from <module> import <nom>` : un binding de module n'est jamais gele,
#: donc un `monkeypatch.setattr("...counter_attack.set_active", ...)` MORD ici -- ce qu'une liaison
#: par nom desarmerait silencieusement.
def _instances(state: State, owner_id: int) -> list:
    return _ca.instances(state, owner_id, WIREWEAVE_NET_COUNTER_ATTACK)


def _flag_is_set(state: State, owner_id: int) -> bool:
    return _ca.flag_is_set(state, owner_id, WIREWEAVE_NET_COUNTER_ATTACK)


def _set_active(state: State, owner_id: int, value: bool) -> bool:
    return _ca.set_active(state, owner_id, WIREWEAVE_NET_COUNTER_ATTACK, value)


def _is_turn_of_owner(state: State, owner_id: int, ev: Optional[TriggerEvent] = None) -> Optional[bool]:
    return _ca.is_turn_of_owner(state, owner_id, ev)


def wireweave_net_tree():
    """UNE feuille `AttackWithAttackDamage` sur l'ATTAQUANT — mirror de
    `CounterAttackEffect$$AttackDamage` : `caster = Owner@<Sel+0x30>` (Calandis),
    `targets = GetCounterAttackTargets() = <Sel+0x48>` (le Caster de l'ability declenchante, porte
    ici par `Actor()` — cf. RESIDUS), `amount = GetDamage() = GetMinMaxDamage(minDmg/maxDmg[level])`,
    `damageProfile = GetDamageProfile(cfg) = "Piercing"`, `hits = GetNumberConstant(cfg, 0x2f)
    = nrOfHits = 2`. `attackRangeType = Melee` -> `is_melee=True`. La config est celle de l'ability
    SOURCE de l'effet, montee en PASSIF sur `eldarRanger` -> `level_slot="passive"`.
    `multi=False` = collapse MONO-CIBLE (le slot `Caster` ne porte qu'UNE entite).
    Import paresseux (evite le cycle triggers <-> abilities.behaviours, == martial_superiority)."""
    return AttackWithAttackDamage(Actor(), WIREWEAVE_NET, _PROFILE,
                                  is_melee=True, level_slot="passive")


class WireweaveNetCounterAttack(EffectTrigger):
    """`CounterAttackEffect$$CreateTargetTrigger` + `$$CreateTargetTriggerBehaviour` pour
    `WireweaveNet_CounterAttackEffect` — la RIPOSTE elle-meme (cf. §3/§4 de l'en-tete)."""
    event_id = EventTriggerType.PreUnitAbility          # `GetCounterAttackTrigger` = On(0x2a = PreUnitAbility, true)
    effect_type = WIREWEAVE_NET_COUNTER_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # (a) gate `EffectComponent.IsActive @+0x5c` — premier test d'`EvaluateEffectTriggerTargets`,
        #     AVANT toute evaluation du trigger de cible. C'est LUI qui porte le « first time » : le
        #     behaviour a desactive l'instance a la riposte precedente.
        if not _flag_is_set(state, self.owner_id):
            return False
        # (b) REPLI de la fenetre d'armement (`NOT IsTurnOf(Owner)`), exactement comme #127 replie
        #     `_ranged_auto_attack_is_active` dans le `matches` du tir d'overwatch. Le trigger de
        #     cible natif ne porte PAS ce conjoint : cote natif la fenetre est portee UNIQUEMENT par
        #     le flag, que les deux `Triggered()` du §2 ecrivent aux boundaries de tour. L'invariant
        #     natif est donc « actif => pas le tour du porteur » -- le repli est EXACT, et il est
        #     indispensable sur un etat SEEDE mi-tour (le seed materialise l'instance ACTIVE sans
        #     jamais avoir vu de `On(0x12)`), qui est le regime de tous les tests.
        if _is_turn_of_owner(state, self.owner_id, ev) is not False:
            return False
        # (c) `get_OwnerOrOwnerTileIsTarget` = AreEqual(Target@0x178, Owner) | AreEqual(Target, Tiles(Owner)).
        if ev.target_id != self.owner_id:
            return False
        attacker = ev.actor_id
        if attacker is None or int(attacker) == int(self.owner_id):
            return False
        # (d) `IsNormalAttack` (`IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack(df)` = `IsNormalAttack(df, df@0x130)`,
        #     l'ability EN COURS) : une ACTIVE de melee ne reveille PAS la riposte, seule l'attaque
        #     NORMALE le fait. C'est ce qui distingue ce gate de celui de `MartialSuperiority`
        #     (`IsDirectTargetAttack` = `AbilityHasAttackType(DirectTargetAttack) | IsNormalAttack`,
        #     donc STRICTEMENT plus large) -- deux abilities voisines, deux predicats DIFFERENTS.
        if not is_normal_attack(ev.ability_type):
            return False
        # (e) `IsMeleeAttack` -- predicat POSITIONNEL natif (`IsMeleeAttackAbilityTrigger` -> le
        #     caster est ADJACENT a la cible), PAS la nature de l'arme. On exige une PREUVE POSITIVE
        #     d'adjacence (`_is_adjacent_units`) et non `_is_ranged_position` : le repli sans board
        #     de ce dernier rend False = « melee », sens PERMISSIF pour un trigger de riposte (meme
        #     raisonnement que `martial_superiority.py`).
        if not _is_adjacent_units(state, attacker, self.owner_id):
            return False
        att = state.get_entity(attacker)
        ow = state.get_entity(self.owner_id)
        if att is None or ow is None:
            return False
        # (f) `AreEnemies(Caster@<Sel+0x48>, Owner@<Sel+0x30>, 0)`.
        ac = att.get_component(OwnerComponent)
        oc = ow.get_component(OwnerComponent)
        if ac is None or oc is None or ac.team == oc.team:
            return False
        # (g) `IsAlive(Caster@<Sel+0x48>)` -- ET leg de re-validation du drain (`RunPhase`/`VerifyDeaths`
        #     re-evaluent chaque item contre l'etat courant : un attaquant tue entre l'enfilement et
        #     le drain ne matche plus).
        auc = att.get_component(UnitComponent)
        return not (auc is not None and not auc.alive)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`CreateTargetTriggerBehaviour` = `GetCounterAttackBehaviour(effect) & DeactivateEffect(effect)`,
        dans CET ordre (`AbilityBehaviour$$op_BitwiseAnd`, gauche puis droite)."""
        if state.rng is None:                          # l'attaque consomme le RNG (rolls/crit/block)
            return None
        entities = entities_from_state(state, self.owner_id, actor_id=int(ev.actor_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        wireweave_net_tree().execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        atk = atks[0] if atks else None
        deactivated = _set_active(state, self.owner_id, False)   # `& DeactivateEffect(effect@<Sel+0x38>)`
        return {"effect": "WireweaveNet_CounterAttack", "caster": int(self.owner_id),
                "target": (atk.get("target") if atk else None),
                "attack": (atk.get("attack") if atk else None),
                "deactivated": deactivated, "dsl": True}


class WireweaveNetDeactivateOnOwnerTurnStart(EffectTrigger):
    """1er `Triggered()` de la branche `ActivationFrequency == 2` de
    `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal` :

        On(0x12 = TurnStart_EffectActivation) & <DSLTriggers+0x28> -> DeactivateEffect(<Sel+0x38>)

    DESARME la riposte au debut du tour de son porteur. Observationnellement redondant avec le repli
    `NOT IsTurnOf(Owner)` du `matches` de la riposte, mais porte quand meme : 1 `Triggered()` natif
    = 1 artefact offline, et c'est LUI qui explique pourquoi 1111 est absent du canal `decisionView`
    par DEFAUT pendant le tour de Calandis."""
    event_id = EventTriggerType.TurnStart_EffectActivation
    effect_type = WIREWEAVE_NET_COUNTER_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return _is_turn_of_owner(state, self.owner_id, ev) is True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _set_active(state, self.owner_id, False):
            return None                                # gate natif « deja inactif -> no-op »
        return {"effect": "WireweaveNet_CounterAttack", "owner": int(self.owner_id),
                "deactivated": "turn_of_owner"}


class WireweaveNetActivateOnOwnerTurnEnd(EffectTrigger):
    """2e `Triggered()` de la meme branche :

        On(0x17 = TurnEnd) & <DSLTriggers+0x28> -> ActivateEffect(<Sel+0x38>)

    RE-ARME la riposte a la fin du tour de son porteur. C'est le CONTREPOIDS du `DeactivateEffect`
    que le behaviour de riposte applique : sans lui, la premiere riposte de la bataille serait aussi
    la derniere. `EvaluateEffectTriggerEffectAbilities` (la voie de ces `Triggered()`) n'applique
    AUCUN gate `IsActive`, contrairement a `EvaluateEffectTriggerTargets` — c'est ce qui permet de
    RE-activer une instance desactivee ; le port fait pareil (`collect_effect_triggers` ne filtre pas
    sur `e.active`)."""
    event_id = EventTriggerType.TurnEnd
    effect_type = WIREWEAVE_NET_COUNTER_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return _is_turn_of_owner(state, self.owner_id, ev) is True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _set_active(state, self.owner_id, True):
            return None                                # deja actif -> aucune ecriture (no-op)
        return {"effect": "WireweaveNet_CounterAttack", "owner": int(self.owner_id),
                "activated": "turn_end_of_owner"}
