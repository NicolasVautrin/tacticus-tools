"""`1439 UnwaveringSentinel_CounterAttack` — la RIPOSTE de `custoKyrus` (Tyrith), portee par un EFFET
de la famille `IdunBattle.Entities.Effects.CounterAttackEffect` **et** par une re-entree DIFFEREE
dans l'ability qui l'a pose.

i2 : « During each enemy turn, after Tyrith is attacked and the attacker is within range 2, she deals
2x 1601-2183 Bolter Damage to the attacker. If there is an enemy adjacent to Tyrith, the range of this
ability is reduced to 1. »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) — decompile = verite
================================================================================================
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.UnwaveringSentinelAbility
        : IdunBattle.Entities.Abilities.BaseTriggeredAbility            (classes.tsv)
    IdunBattle.Entities.Effects.Loki.UnwaveringSentinel_CounterAttackEffect
        : IdunBattle.Entities.Effects.CounterAttackEffect
        : IdunBattle.Entities.Effects.PlayerTurnEffect
        : IdunBattle.Entities.Effects.BaseEffect                        (classes.tsv)

⚠ **L'ability est une `BaseTriggeredAbility`, PAS une `AOwnerEffectTriggeredAbility`** — c'est le
premier ecart avec `WireweaveNet` et `GrimRetribution`, et il est LU dans `classes.tsv`, jamais
deduit d'un nom. Consequence directe : elle n'herite d'AUCUN `CreateBehaviour` qui poserait l'effet ;
elle ecrit le sien, et il BIFURQUE.

⚠ **1439 != 1449.** L'`EffectType` de la riposte est 1439, la `TriggeredAbilityType` du passif est
1449 — et chaque ordinal nomme autre chose dans l'enum d'en face (`TriggeredAbilityType 1439` =
`NovaShield_BlockVisual`, `EffectType 1449` = `MoreGitzOverEre_ExtraDamagePct`). Une confusion
d'enum serait ici SILENCIEUSE en ordinal.

## 0. LE RECENSEMENT — par le bloc `methodPointers`

`UnwaveringSentinelAbility` declare **QUATRE** entrees :

    [ CreateTrigger(= WayOfTheShortBlade_InitAbility) · CreateBehaviour(PROPRE)
      · GetCounterAttackBehaviour(PROPRE) · GetAddEffectBehaviour(PROPRE) ]

`UnwaveringSentinel_CounterAttackEffect` declare **SIX** entrees, dont **CINQ corps propres** :

    [ .ctor(PROPRE) · GetCounterAttackTargets(= WireweaveNet) · GetCounterAttackTrigger(PROPRE)
      · GetCounterAttackCondition(PROPRE) · GetCounterAttackBehaviour(PROPRE) · GetDamage(PROPRE) ]

## 1. LA POSE — `CreateTrigger` herite de forme, `CreateBehaviour` PROPRE et BIFURQUANT

    UnwaveringSentinelAbility$$CreateTrigger        # corps PARTAGE avec WayOfTheShortBlade_InitAbility
        = OnOwnerSpecificAbilityInit(this.Id@+0x10) # -> le MEME vecteur que la famille AOwnerEffect*

    UnwaveringSentinelAbility$$CreateBehaviour(abilityState, triggerType) =
        if (triggerType == 0x20 = Custom)   -> <GetCounterAttackBehaviour, inline>   # cf. §4
        else                                -> <GetAddEffectBehaviour,    inline>

    UnwaveringSentinelAbility$$GetAddEffectBehaviour =
        AddEffect( 0x59f = EffectType.UnwaveringSentinel_CounterAttack,
                   get_AbilityStateReference,
                   source  = Owner@<DSLSelectors+0x30>,
                   targets = Owner@<DSLSelectors+0x30>,
                   <duree ZEROEE> )

Port de la pose : `factory.ABILITY_INIT_OWNER_EFFECTS["UnwaveringSentinel"] =
["UnwaveringSentinel_CounterAttack"]`, comme pour ses deux soeurs — la bifurcation ne change pas la
face POSE, la voie `OnOwnerSpecificAbilityInit` ne pouvant produire que `triggerType != Custom`.

## 2. LA FENETRE D'ARMEMENT — branche freq 1, IDENTIQUE a `GrimRetribution`

`.ctor` : `turnsEnabled = 1`, `activationFrequency = 1` (litteraux relus a l'assembleur, cf.
`entities/effects/loki/counter_attack.py`) ->

    On(0x12 = TurnStart_EffectActivation) & NOT IsTurnOf(Owner)  -> ActivateEffect(<Sel+0x38>)
    On(0x17 = TurnEnd)                    & NOT IsTurnOf(Owner)  -> DeactivateEffect(<Sel+0x38>)

=> **une riposte par tour ennemi** (« During each enemy turn »), et non une par cycle.

## 3. LA RIPOSTE — trigger et condition

    UnwaveringSentinel_CounterAttackEffect$$GetCounterAttackTrigger   # PROPRE ; GrimRetribution en
                                                                     # PARTAGE le corps
        = On(0x9 = Attack, true)

    UnwaveringSentinel_CounterAttackEffect$$GetCounterAttackCondition =
          get_OwnerOrOwnerTileIsTarget
        & Contains( list     = ValidNormalAttackTargets(
                                   unit     = Owner@<DSLSelectors+0x30>,
                                   unitTile = Tiles(Owner),
                                   range    = Direct( GetNumberConstant(config@this+0x60,
                                                        AbilityConstantType.range = 0x16) ),
                                   ignoreRule = null, additionalRule = null ),
                    elements = Caster@<DSLSelectors+0x48> )

⚠ **C'est `ValidNormalAttackTargets` qui porte les DEUX phrases de l'i2 a la fois**, et c'est ce qui
rend inutile tout gate d'adjacence ecrit a la main :

  * « the attacker is within **range 2** » = l'override `range = GetNumberConstant(range)`
    (`constants.range = 2` au gameconfig `UnwaveringSentinel`) ;
  * « If there is an enemy adjacent to Tyrith, the range of this ability is **reduced to 1** » =
    le clamp MELEE que `IdunBattle.Core.Services.TargetingQuery$$GetRange` applique a TOUTE attaque
    normale (`IsTrue(ForceMeleeTarget) && ShouldApplyRangedInMelee`), et que l'override de portee ne
    desarme pas. Le port ne le RE-code pas : il passe par le foyer unique
    `runner/abilities/targeting.valid_normal_attack_targets`, qui l'applique deja.

Le bloc `range != null` du selecteur natif fait AUSSI `opts.rules &= ~TargetMatchesDynamicRule` ; les
deux ecritures sont portees ensemble dans ce foyer (#946), qui recoit desormais `range_override`.

    CreateTargetTrigger (base) ajoute, comme pour les deux soeurs :
        & <DSLTriggers+0x20>                                  # SINGLETON non qualifie (RESIDUS)
        & AreEnemies(Caster@<Sel+0x48>, Owner@<Sel+0x30>, 0)
        & IsAlive(Caster@<Sel+0x48>)

## 4. LE DEGAT — DEUX SAUTS, et c'est le deuxieme grand ecart avec la famille

    UnwaveringSentinel_CounterAttackEffect$$GetCounterAttackBehaviour =
        DSLBehaviors.TriggerAbilityDelayed( entity = Owner@<DSLSelectors+0x30>,
                                            triggeredAbilityType = 0x5a9 = 1449,
                                            unitSelectionType    = OnlyAliveAndTargetable )

**Pas d'`AttackDamage`.** L'effet ENFILE un re-declenchement de SA PROPRE ability ; c'est
`UnwaveringSentinelAbility` qui frappe, au drain :

    IdunBattle.Entities.Behaviours.TriggerAbilityDelayedBehaviour$$Execute
        -> IMatchState.AddPendingTriggeredAbility(unit, 1449, abilityEntities)   # slot 6
    IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities
        -> IOperationProcessor.TriggerAbility(...)                               # slot 0x56
    IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility
        -> <ability>.ExecuteBehaviour(abilityState, abilityEntities, 0x20)       # slot 4, litteral LU

Le `0x20` du dernier appel est LU aux octets (`CONCAT44(uVar16, 0x20)`), pas deduit : c'est lui qui
choisit la branche `Custom` de `CreateBehaviour`, donc :

    UnwaveringSentinelAbility$$GetCounterAttackBehaviour(abilityState) =
        IfAlive( Caster@<Sel+0x48>,
                 DSLBehaviors.AttackWithAttackDamage(
                     caster        = Owner@<DSLSelectors+0x30>,
                     target        = Caster@<DSLSelectors+0x48>,
                     amount        = BaseTriggeredAbility$$MinMaxDamage(abilityState),
                     damageProfile = BaseTriggeredAbility$$GetDamageProfile(),
                     hits          = BaseTriggeredAbility$$GetHits(),
                     abilityOrEffect, options = null, selectionType = OnlyTargetable ) )

Le degat vient donc de la CONFIG DE L'ABILITY (`minDmg`/`maxDmg`/`nrOfHits`/`damageProfile` de
`UnwaveringSentinel`), pas de l'effet. gameconfig : `attackRangeType = Ranged`,
`constants = {damageProfile: "Bolter", nrOfHits: "2", range: "2"}` — niveau 65 : 1601-2183.

    CreateTargetTriggerBehaviour (base) =
        GetCounterAttackBehaviour(effect) & DeactivateEffect(effect)   # gate vtable +0x738 = `return 1`

================================================================================================
RESIDUS EXPLICITES
================================================================================================
 * `UnwaveringSentinel_CounterAttackEffect$$GetDamage` et `$$GetCounterAttackTargets` sont des
   **OVERRIDES MORTS** sur cette chaine : leurs slots de vtable (`+0x758` / `+0x768`) n'ont qu'un
   consommateur, `CounterAttackEffect$$AttackDamage`, que ce membre n'emprunte jamais. `GetDamage`
   rend d'ailleurs `<DSLFormulas+0x18>` = la constante 0. C'est un RESULTAT du recensement, pas un
   oubli de port.
 * `<DSLTriggers+0x20>` : MEME residu que `wireweave_net.py` / `grim_retribution.py` — noeud-trigger
   SINGLETON non qualifie, NON porte.
 * `get_OwnerOrOwnerTileIsTarget` : le port n'a qu'UNE cible d'evenement -> la branche « cible = la
   TUILE du porteur » est structurellement couverte. MEME residu que ses deux soeurs.
 * `unitSelectionType = OnlyAliveAndTargetable` du `TriggerAbilityDelayed` : le port le transporte
   sans le lire (`TriggerAbilityDelayed.unit_selection_type`), MEME residu que les trois call-sites
   deja portes.
 * Le natif lit la cible de la riposte dans `Caster@<Sel+0x48>` ; sur le vecteur `On(Attack)` ce slot
   et `Actor` designent la meme entite, et c'est elle que `TriggerEvent.actor_id` porte -- puis, au
   drain, `_aid` de l'evenement enfile. MEME residu que ses deux soeurs.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import If
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.selectors.accessors import Actor, Owner
from .....entities.selectors.units import Tiles, ValidNormalAttackTargets
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import Contains, IsAlive
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.lifecycle import TriggerAbilityDelayed
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ..base import EffectTrigger, TriggeredAbility, TriggerEvent
from . import counter_attack as _ca     # forme B : le socle PARTAGE de la famille (#946)

UNWAVERING_SENTINEL_COUNTER_ATTACK = int(EffectType.UnwaveringSentinel_CounterAttack)   # 0x59f = 1439
UNWAVERING_SENTINEL_ABILITY = int(TriggeredAbilityType.UnwaveringSentinel)              # 0x5a9 = 1449
UNWAVERING_SENTINEL = "UnwaveringSentinel"   # nom gameconfig de l'ability (passif de `custoKyrus`)
_PROFILE = "Bolter"                          # `GetDamageProfile()` -> constants.damageProfile
#: `unitSelectionType` du `TriggerAbilityDelayed` -- transporte, jamais lu (cf. RESIDUS).
_SEL_DELAYED = int(UnitSelectionType.OnlyAliveAndTargetable)


def counter_attack_range() -> Optional[int]:
    """`GetNumberConstant(config@this+0x60, AbilityConstantType.range)` — la portee que le natif
    passe a `ValidNormalAttackTargets`, LUE au gameconfig de l'ability (`constants.range` = 2).

    `AbilityConstantType.range` et non l'ordinal `0x16` : l'accesseur appele au site est
    `GetNumberConstant`, donc la clef vit dans CET enum-la (`GetVariableForLevel` en a un AUTRE, ou
    22 nomme `blockDmg_2`). `None` = constante absente du gameconfig -> l'appelant n'arme AUCUN
    override, ce qui rend au selecteur sa portee d'arme (degradation NOMMEE, jamais un 0 invente qui
    fermerait la riposte en silence)."""
    return ability_var(UNWAVERING_SENTINEL, AbilityConstantType.range.name, is_constant=True)


def attacker_in_normal_attack_range_tree(rng: Optional[int]):
    """Le SECOND conjoint de `GetCounterAttackCondition`, noeud par noeud :

        Contains( list     = ValidNormalAttackTargets(Owner@+0x30, Tiles(Owner), range = Direct(rng)),
                  elements = Caster@<Sel+0x48> )

    `Caster@+0x48` est porte par `Actor()` (cf. RESIDUS de l'en-tete). `Contains(CONTENANT, CONTENU)`
    — l'ordre des arguments est celui du natif (`DSLTriggers$$Contains(list, elements)`), et le port
    compare des `Id`, jamais l'identite d'objet."""
    return Contains(ValidNormalAttackTargets(Owner(), Tiles(Owner()), range=rng), Actor())


def unwavering_sentinel_delayed_tree():
    """`GetCounterAttackBehaviour` de l'EFFET (§4) :

        TriggerAbilityDelayed( entity = Owner@<DSLSelectors+0x30>, 1449, OnlyAliveAndTargetable )

    Le sélecteur d'entite est `Owner` (Tyrith), pas l'attaquant : c'est ELLE qui re-declenche son
    ability. Le port passe par le noeud partage, qui ENFILE (chemin « file ») des lors que 1449 est
    inscrite dans `CUSTOM_TRIGGERED_ABILITIES` -- ce qu'elle est."""
    return TriggerAbilityDelayed(Owner(), UNWAVERING_SENTINEL_ABILITY,
                                 unit_selection_type=_SEL_DELAYED)


def unwavering_sentinel_attack_tree():
    """`UnwaveringSentinelAbility$$GetCounterAttackBehaviour`, la branche `Custom` (§4) :

        IfAlive( Caster@<Sel+0x48>, AttackWithAttackDamage(Owner -> Caster, MinMaxDamage(abilityState),
                                                           GetDamageProfile(), GetHits(), ...) )

    `IfAlive(x, b)` est LITTERALEMENT `If(IsAlive(x), b)` (`DSLBehaviors$$IfAlive` appelle
    `DSLTriggers$$IsAlive` puis `DSLBehaviors$$If`) -> pas de noeud dedie, meme convention que les
    six call-sites deja portes.

    `attackRangeType = Ranged` au gameconfig -> `is_melee=False`. `level_slot="passive"` :
    `UnwaveringSentinel` est le PASSIF de `custoKyrus`, donc `MinMaxDamage(abilityState)` indexe le
    canal PASSIF, pas l'`activeAbilityLevel`. `hits` = `GetHits()` = `constants.nrOfHits` = 2, lu par
    la clef par defaut du noeud."""
    return If(IsAlive(Actor()),
              AttackWithAttackDamage(Actor(), UNWAVERING_SENTINEL, _PROFILE,
                                     is_melee=False, level_slot="passive"))


class UnwaveringSentinelCounterAttack(EffectTrigger):
    """`CounterAttackEffect$$CreateTargetTrigger` + `$$CreateTargetTriggerBehaviour` pour
    `UnwaveringSentinel_CounterAttackEffect` — le trigger de riposte, dont le behaviour ENFILE
    (cf. §3/§4 de l'en-tete). Le degat, lui, tombe dans `UnwaveringSentinelCustomAbility`."""
    event_id = EventTriggerType.Attack          # `GetCounterAttackTrigger` = On(0x9 = Attack, true)
    effect_type = UNWAVERING_SENTINEL_COUNTER_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # (a) gate `EffectComponent.IsActive @+0x5c` (cf. `loki/counter_attack.py`). Ici il porte le
        #     « une riposte par tour ennemi » : le behaviour desactive l'instance, et
        #     `UnwaveringSentinelActivateOnEnemyTurnStart` la re-arme au tour ennemi SUIVANT.
        if not _ca.flag_is_set(state, self.owner_id, UNWAVERING_SENTINEL_COUNTER_ATTACK):
            return False
        # (b) REPLI de la fenetre d'armement (`NOT IsTurnOf(Owner)`) -- MEME raison et MEME forme que
        #     `wireweave_net.py` / `grim_retribution.py` : indispensable sur un etat SEEDE mi-tour.
        if _ca.is_turn_of_owner(state, self.owner_id, ev) is not False:
            return False
        # (c) `get_OwnerOrOwnerTileIsTarget` -- Tyrith (ou sa tuile) EST la cible du coup.
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False
        attacker = ev.actor_id
        if attacker is None or int(attacker) == int(self.owner_id):
            return False
        ow = state.get_entity(self.owner_id)
        att = state.get_entity(attacker)
        if ow is None or att is None:
            return False
        # (d) `AreEnemies(Caster@<Sel+0x48>, Owner@<Sel+0x30>, 0)`.
        ac = att.get_component(OwnerComponent)
        oc = ow.get_component(OwnerComponent)
        if ac is None or oc is None or ac.team == oc.team:
            return False
        # (e) `IsAlive(Caster@<Sel+0x48>)` -- ET leg de re-validation du drain.
        auc = att.get_component(UnitComponent)
        if auc is not None and not auc.alive:
            return False
        # (f) `Contains(ValidNormalAttackTargets(Owner, Tiles(Owner), Direct(range)), Caster)` --
        #     LE gate de portee, qui porte AUSSI le « reduced to 1 » quand un ennemi est adjacent
        #     (cf. §3). `entities_from_state` pose `caster = owner = le porteur` et `actor =
        #     l'attaquant`, donc `Actor()` designe bien le `Caster@+0x48` natif.
        ents = entities_from_state(state, int(self.owner_id), actor_id=int(attacker))
        return attacker_in_normal_attack_range_tree(counter_attack_range()).should_trigger(ents)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`CreateTargetTriggerBehaviour` = `GetCounterAttackBehaviour(effect) & DeactivateEffect(effect)`,
        dans CET ordre. Le premier terme ENFILE le re-declenchement de 1449 ; AUCUN degat ne tombe
        ici — il tombe au drain, dans `UnwaveringSentinelCustomAbility`."""
        entities = entities_from_state(state, self.owner_id, actor_id=int(ev.actor_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        unwavering_sentinel_delayed_tree().execute(entities, ectx)
        delayed = [p for n, p in ectx.emitted if n == "TriggerAbilityDelayed"]
        deactivated = _ca.set_active(state, self.owner_id,
                                     UNWAVERING_SENTINEL_COUNTER_ATTACK, False)
        return {"effect": "UnwaveringSentinel_CounterAttack", "caster": int(self.owner_id),
                "attacker": int(ev.actor_id),
                "queued": bool(delayed and delayed[0].get("queued")),
                "deactivated": deactivated, "dsl": True}


class UnwaveringSentinelCustomAbility(TriggeredAbility):
    """`UnwaveringSentinelAbility$$CreateBehaviour`, branche **`triggerType == 0x20 = Custom`** — LE
    DEGAT (§4 de l'en-tete). Jamais atteinte par le bus d'events : elle n'a pas de `CreateTrigger`
    propre a ce vecteur, elle est inscrite dans `CUSTOM_TRIGGERED_ABILITIES[1449]` et n'est joignable
    que par le drain de `state.pending_triggered_abilities`.

    `matches` rend `True` : sur ce chemin le natif ne RE-EVALUE aucun trigger (le declenchement est
    imperatif, `TriggerTriggeredAbilityOperation$$TriggerAbility` n'appelle que `ExecuteBehaviour`).
    La seule condition restante, `IsAlive(Caster)`, est DANS l'arbre — donc evaluee a l'etat COURANT
    au moment du drain, exactement comme le natif, ce qui est observable : un attaquant mort entre
    l'enfilement et le drain ne prend rien.

    Le mapping des roles au drain : `TriggerAbilityDelayed` a memorise `(actor, target)` du contexte
    d'enfilement, et le trigger de riposte y avait pose `actor = l'attaquant`. Donc `ev.actor_id` =
    l'attaquant = le `Caster@<Sel+0x48>` natif, et `entities_from_state(state, owner_id,
    actor_id=ev.actor_id)` rend `Caster()` = le porteur, `Actor()` = l'attaquant."""
    event_id = int(EventTriggerType.Custom)          # 0x20 -- jamais emis par le bus du port
    TRIGGERED_ABILITY_ID = UNWAVERING_SENTINEL_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.rng is None:                          # l'attaque consomme le RNG (rolls/crit/block)
            return None
        entities = entities_from_state(state, self.owner_id,
                                       actor_id=(int(ev.actor_id) if ev.actor_id is not None
                                                 else None))
        ectx = ExecutionContext(state=state, rng=state.rng)
        unwavering_sentinel_attack_tree().execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        atk = atks[0] if atks else None
        return {"ability": "UnwaveringSentinel_CounterAttack", "caster": int(self.owner_id),
                "target": (atk.get("target") if atk else None),
                "attack": (atk.get("attack") if atk else None), "dsl": True}


class UnwaveringSentinelActivateOnEnemyTurnStart(EffectTrigger):
    """1er `Triggered()` de la branche `ActivationFrequency == 1` (§2) :

        On(0x12 = TurnStart_EffectActivation) & NOT IsTurnOf(Owner) -> ActivateEffect(<Sel+0x38>)

    ARME la riposte au debut de CHAQUE tour ennemi -- le « During **each** enemy turn » de l'i2."""
    event_id = EventTriggerType.TurnStart_EffectActivation
    effect_type = UNWAVERING_SENTINEL_COUNTER_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return _ca.is_turn_of_owner(state, self.owner_id, ev) is False

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _ca.set_active(state, self.owner_id, UNWAVERING_SENTINEL_COUNTER_ATTACK, True):
            return None                                # deja actif -> aucune ecriture (no-op)
        return {"effect": "UnwaveringSentinel_CounterAttack", "owner": int(self.owner_id),
                "activated": "turn_start_of_enemy"}


class UnwaveringSentinelDeactivateOnEnemyTurnEnd(EffectTrigger):
    """2e `Triggered()` de la meme branche :

        On(0x17 = TurnEnd) & NOT IsTurnOf(Owner) -> DeactivateEffect(<Sel+0x38>)

    DESARME la riposte a la fin de chaque tour ennemi. MEME raison de le porter que son homologue
    `GrimRetributionDeactivateOnEnemyTurnEnd` : 1 `Triggered()` natif = 1 artefact offline."""
    event_id = EventTriggerType.TurnEnd
    effect_type = UNWAVERING_SENTINEL_COUNTER_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return _ca.is_turn_of_owner(state, self.owner_id, ev) is False

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _ca.set_active(state, self.owner_id, UNWAVERING_SENTINEL_COUNTER_ATTACK, False):
            return None                                # gate natif « deja inactif -> no-op »
        return {"effect": "UnwaveringSentinel_CounterAttack", "owner": int(self.owner_id),
                "deactivated": "turn_end_of_enemy"}
