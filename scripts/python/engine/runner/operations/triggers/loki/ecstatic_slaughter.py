"""`EcstaticSlaughter` (`TriggeredAbilityType 0x5c0 = 1472`, passif de kit d'`emperFlawlessBlade`
<< Hascule >>) -- la riposte extatique : 3 coups Eviscerate sur UN ennemi adjacent, puis un TAUNT
d'un round si la cible survit.

i2 : << When Hascule becomes Thrilled or every time an enemy unit adjacent to him is Overkilled,
Hascule deals 3x {minDmg}-{maxDmg} Eviscerating Damage to an adjacent enemy unit. If the enemy
survives, it is Taunted for 1 round. >>

===================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- recense par le bloc `methodPointers`
===================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.EcstaticSlaughterAbility` :
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` (base LUE dans `frida/classes.tsv`, jamais
dans le nom du `.ctor`). Bloc `methodPointers` : **4 slots**, **3 corps PROPRES** --
`[CreateTrigger, CreateBehaviour, GetAttackTarget, .ctor]`, le `.ctor` etant FONDU par l'ICF (il
n'a pas de ligne a lui dans `frida/methods.tsv`, et le slot voisin porte le nom d'un autre
proprietaire). Slots `DSLSelectors` : `+0x30 Owner` · `+0x60 Target`.

## `$$CreateTrigger`

      (   On( 0x3e = EventTriggerType.EffectAdded, ownerNeedsToBeAlive: true )
        & CurrentAbilityIs( AbilityOrEffect(0x59a = EffectType.ThrillSeekers) )
        & get_OwnerIsTarget )
    | (   OnDeath( triggerOnOverkill: true, triggerOnSteppable: false )
        & TargetIsOverkilled()
        & IsNormalUnit( Target@+0x60 )
        & AreEnemies( Owner@+0x30, Target@+0x60, UnitTeamSelectionType 0 )
        & IsAdjacent( Owner@+0x30, Target@+0x60, UnitSelectionType 0 ) )
    & AmountIsGreaterThanZero(
          AdjacentEnemies( Owner@+0x30, unique: true, selectionType: 3 ) )

L'ORDRE des combinateurs est lu aux registres, pas au pseudo-C : `op_BitwiseOr(rbp = branche
EffectAdded, rsi = branche OnDeath)` PUIS `op_BitwiseAnd(<ce OU>, rbx = le gate d'adjacence)`. Le
gate d'adjacence est donc COMMUN aux deux branches -- ce n'est pas un conjoint de la seule branche
mort.

⚠ Le litteral `0x59a` du `CurrentAbilityIs` est un **`EffectType`**, pas un `TriggeredAbilityType` :
la surcharge appelee est `IdunBattle.Core.AbilityOrEffect$$op_Implicit(effect:
IdunBattle.Entities.Enum.EffectType)` -- le probe de desassemblage rend sa SIGNATURE, et
`EffectType.ThrillSeekers = 1434` alors que `TriggeredAbilityType.ThrillSeekers = 1444`. Prendre
l'ordinal pour l'autre enum aurait cable le trigger sur un id qui n'est jamais publie.

⚠ `IdunBattleLogic.Entities.DSLTriggers$$OnDeath(a, b)` = `OnDeathEvent(0, a, b)`, dont le corps a
ete relu verbatim :

    return On(triggerType) & <DSLTriggers+0x70 = Yes>
           & (a ? <Yes> : NOT TargetIsOverkilled())
           & (b ? <Yes> : NOT HasTrait(Target@+0x60, 0x1b = Steppable))

`a = true` **DESARME** le gate d'overkill d'`OnDeathEvent` ; c'est le `TargetIsOverkilled()`
SEPARE du `CreateTrigger` qui l'EXIGE (meme piege que `ObsessiveAnnunciation`, meme lot). Les deux
litteraux sont decodes aux octets (`mov dl, 1` / `xor r8d, r8d`).

⚠ **AUCUN `get_OwnerIsActor` sur la branche mort** : Hascule n'a pas besoin d'etre le tueur. Un
overkill inflige par n'importe qui sur un ennemi adjacent a lui declenche la riposte -- l'i2 le dit
(<< every time an enemy unit adjacent to him is Overkilled >>), et le recopier depuis
`HeadClaimerOnDeathAbility` / `TerrifyingCrescendo` (qui, eux, le portent) aurait borne le passif.

## `$$CreateBehaviour`

    cible = Cache( First( SortUnitsByDamageUtility( Randomize( AdjacentEnemies(Owner@+0x30,
                                                                unique: true, sel: 3) ),
                                                    caster = Owner@+0x30,
                                                    damage = MinMaxDamage(abilityState),
                                                    unitSelectionType = 3, hits = null ),
                          amount: 1, ignoreForcedTargets: false ),
                   matchAbilityEntities: true )

    AttackWithAttackDamage( caster: Owner@+0x30, target: cible,
                            amount: MinMaxDamage(abilityState),
                            damageProfile: AbilityConfiguration$$GetDamageProfile()   # Eviscerate
                            hits: GetNumberConstant(0x2f = nrOfHits)                   # 3
                            abilityOrEffect: AbilityOrEffect(<this.AbilityType> = 1472),
                            options: null, selectionType: UnitSelectionType 2 )
  & AddBondEffect( 0x1b = EffectType.Taunted_OnlySpecificTargets,
                   abilityState: get_AbilityStateReference(),
                   source: Owner@+0x30, targets: cible, bondedEntity: Owner@+0x30,
                   turns: TurnsFromRounds( GetNumberConstant(0x45 = nrOfRounds) ) )   # 1

Les deux `GetNumberConstant` sont qualifies par `data/symbols/<build>/frida/enums.tsv`
(`AbilityConstantType 0x2f = nrOfHits`, `0x45 = nrOfRounds`) et le gameconfig d'`EcstaticSlaughter`
porte bien `nrOfHits: 3`, `nrOfRounds: 1`, `damageProfile: Eviscerate`.

⚠ **Le TAUNT n'est PAS conditionne par un `If`** : le decompile ne porte AUCUN test de survie. Le
<< If the enemy survives >> de l'i2 est un fait d'EXECUTION -- `AddEffectOperation$$Execute` ne pose
rien sur un cadavre --, pas un noeud de l'arbre. Ecrire un `If(IsAlive(cible), ...)` aurait ete une
logique INVENTEE ; le port pose l'`AddBondEffect` inconditionnellement, comme le natif, et laisse
l'Operation trancher.

## `$$GetAttackTarget`

La MEME chaine de selection, **sans le `Cache`** -- c'est l'accesseur que consomme la face DECISION
(`IdunBattle.AI.Playbook.Loki.EcstaticSlaughterPlaybook`, de la famille
`AdjacentUnitPreferenceTriggeredAbilityPlaybook<EcstaticSlaughterAbility>`). Face NON portee par
cette tranche (residu nomme en fin de fichier).

===================================================================================================
FORME DU PORT (doctrine #149) ET RESIDUS
===================================================================================================
* `CreateTrigger` COLLAPSE imperativement dans `matches` -- idiome de tous les trigger-ports. Les
  deux branches de l'`op_BitwiseOr` deviennent DEUX classes (patron `ThrillSeekers` /
  `TerrifyingCrescendo`), parce que le dispatch du port est indexe par `event_id` ; le
  `CreateBehaviour` natif etant UNIQUE, les deux classes partagent le meme corps.
* `CreateBehaviour` = un VRAI ARBRE DSL : la chaine de selection est MATERIALISEE (elle n'a rien a
  collapser -- l'ability RE-DERIVE sa cible, il n'y a pas de cible de message a reprendre), et les
  deux feuilles (`AttackWithAttackDamage`, `AddBondEffect`) appellent leurs Operations.

RESIDUS NOMMES :
* face DECISION (`EcstaticSlaughterPlaybook` + `GetAttackTarget`) non portee.
* `ignoreForcedTargets: false` du `First` et `matchAbilityEntities: true` du `Cache` sont
  transcrits ici, non portes (le `Cache` du port memoise par instance de noeud, ce qui suffit : les
  DEUX feuilles lisent le meme sous-arbre dans le meme cast).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import op_add
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Target
from .....entities.selectors.geometry import Cache, Randomize
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import (AdjacentEnemies, First, SortUnitsByDamageUtility)
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import HasTrait
from ....abilities.base import ability_attack_params
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddBondEffect
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, _is_adjacent_units

#: cle gameconfig (minDmg/maxDmg/nrOfHits/nrOfRounds/damageProfile) ET nom d'`EffectType`/d'ability.
ABILITY_ID = "EcstaticSlaughter"
#: `TriggeredAbilityType.EcstaticSlaughter` = `0x5c0` = 1472 -- l'`AbilityOrEffect` que le natif
#: passe en 6e argument de son `AttackWithAttackDamage`.
ECSTATIC_SLAUGHTER = int(TriggeredAbilityType.EcstaticSlaughter)
#: `EffectType.ThrillSeekers` = `0x59a` = 1434 -- l'effet << Thrilled >>, litteral du
#: `CurrentAbilityIs`. ⚠ PAS `TriggeredAbilityType.ThrillSeekers` (1444) : la surcharge d'
#: `AbilityOrEffect$$op_Implicit` appelee prend un `EffectType` (cf. l'en-tete de module).
THRILLED = int(EffectType.ThrillSeekers)
#: `EffectType.Taunted_OnlySpecificTargets` = `0x1b` = 27 -- le bond pose sur la cible.
TAUNT_EFFECT = int(EffectType.Taunted_OnlySpecificTargets)
TAUNT_EFFECT_NAME = EffectType.Taunted_OnlySpecificTargets.name
#: `UnitSelectionType 3` = `OnlyAliveAndTargetable` -- le litteral des DEUX `AdjacentEnemies` et du
#: `SortUnitsByDamageUtility`.
SEL_ALIVE_TARGETABLE = 3
#: `steppableGate` d'`OnDeathEvent(0, a, b = false)` = `NOT HasTrait(Target@+0x60, 0x1b)`.
_TARGET_IS_STEPPABLE = HasTrait(Target(), int(UnitTrait.Steppable))


def ecstatic_slaughter_rounds(state: State, owner_id: int) -> int:
    """`AbilityConfiguration$$GetNumberConstant(cfg, 0x45 = nrOfRounds)` = la duree du taunt, LUE au
    gameconfig d'`EcstaticSlaughter` (= 1). Constante absente -> 1 : le natif rend 0 pour un index
    manquant, mais `TurnsFromRounds(0)` donnerait un taunt qui expire au tick suivant sa pose, ce
    qui n'est pas plus fidele qu'un round -- on prend le defaut du gameconfig et on le DIT."""
    import gameconfig as GC
    consts = (GC.ability(ABILITY_ID) or {}).get("constants") or {}
    v = consts.get(AbilityConstantType.nrOfRounds.name)
    return 1 if v is None else int(v)


class _MinMaxDamage:
    """`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage(abilityState)` -- le noeud
    VALEUR que le natif passe DEUX fois : au `SortUnitsByDamageUtility` (borne de prediction) et a
    l'`AttackWithAttackDamage` (le degat reel).

    C'est une PLAGE, pas un scalaire : le port la rend en couple `(base_min, base_max)` via
    `ability_attack_params` -- le MEME foyer que la feuille d'attaque, donc les deux consommateurs
    lisent la meme source (pas de seconde implementation des bornes). `level_slot="passive"` :
    `EcstaticSlaughter` est un PASSIF, ses `minDmg`/`maxDmg` s'indexent au niveau d'ability PASSIVE.

    `state`/`owner_id` absents -> `(0, 0)` : sans ECS il n'y a pas de niveau d'ability, et
    fabriquer une borne serait pire qu'un zero qui laisse le tri inerte."""
    __slots__ = ("state", "owner_id", "profile")

    def __init__(self, state: State, owner_id: int, profile: Optional[str]):
        self.state, self.owner_id, self.profile = state, int(owner_id), profile

    def evaluate(self, entities):
        if self.state is None:
            return (0, 0)
        bmin, bmax, _pierce, _hits = ability_attack_params(
            self.state, self.owner_id, ABILITY_ID, self.profile, level_slot="passive")
        return (int(bmin), int(bmax))


def ecstatic_slaughter_target_selector(state: State, owner_id: int, profile: Optional[str]):
    """La chaine de ciblage de `$$CreateBehaviour`, noeud pour noeud :

        Cache( First( SortUnitsByDamageUtility( Randomize( AdjacentEnemies(Owner, unique, sel 3) ),
                                                Owner, MinMaxDamage, sel 3, hits: null ), 1 ), true )

    `Caster()` = `Owner@DSLSelectors+0x30` (pour une triggered-ability, Owner == Caster == le
    porteur). Le `Randomize` consomme `state.rng` DANS le selecteur (comme `PickRandomly`), donc
    l'ordre de depart est aleatoire AVANT le tri d'utilite -- c'est ce qui departage deux cibles a
    utilite egale, et c'est mesurable.

    `$$GetAttackTarget` est LA MEME chaine sans le `Cache` : le `Cache` n'existe que parce que le
    `CreateBehaviour` a DEUX consommateurs (l'attaque et le taunt) qui doivent viser la MEME unite."""
    ring = AdjacentEnemies(Caster(), selection_type=SEL_ALIVE_TARGETABLE)
    ordered = SortUnitsByDamageUtility(Randomize(ring), Caster(),
                                       _MinMaxDamage(state, owner_id, profile),
                                       selection_type=SEL_ALIVE_TARGETABLE)
    # `...EcstaticSlaughterAbility$$CreateBehaviour` pousse `matchAbilityEntities = 1` (mode
    # DICT), qui est le defaut du noeud.
    return Cache(First(ordered))


def ecstatic_slaughter_tree(state: State, owner_id: int, rounds: int):
    """Arbre de `EcstaticSlaughterAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete) :

        AttackWithAttackDamage(Owner, cible, MinMaxDamage, Eviscerate, nrOfHits, this, null, 2)
      & AddBondEffect(0x1b, AbilityStateReference, Owner, cible, bonded = Owner,
                      TurnsFromRounds(nrOfRounds))

    `op_add` (= `Seq`) est la MEME classe native `CombinedBehaviour` que l'`op_BitwiseAnd` du
    decompile. Le profil de degat vient de `GetDamageProfile()` = `constants.damageProfile` du
    gameconfig (`Eviscerate`), jamais deduit du nom de l'ability.

    `bonded_ref = Caster()` porte le 5e argument natif `bondedEntity = Owner@+0x30` : le taunt de
    `Taunted_OnlySpecificTargets` ne force la cible a attaquer QUE Hascule -- sans lui l'instance
    n'aurait pas d'entite bondee et le taunt ne designerait personne.
    `scale_from_source=True` porte l'`AbilityStateReference` (3e argument), sans quoi l'instance
    materialisee n'a pas d'`ability_level`."""
    import gameconfig as GC
    profile = ((GC.ability(ABILITY_ID) or {}).get("constants") or {}).get("damageProfile")
    cible = ecstatic_slaughter_target_selector(state, owner_id, profile)
    return op_add(
        AttackWithAttackDamage(cible, ABILITY_ID, profile, is_melee=True, multi=True,
                               ability_type=ECSTATIC_SLAUGHTER, level_slot="passive"),
        AddBondEffect(TAUNT_EFFECT, TAUNT_EFFECT_NAME, Caster(), cible,
                      duration_rounds=rounds, bonded_ref=Caster(), scale_from_source=True))


class _EcstaticSlaughterBase(TriggeredAbility):
    """Corps PARTAGE des deux branches de l'`op_BitwiseOr` du `CreateTrigger` : le natif n'a qu'UN
    `CreateBehaviour`, les deux branches l'executent a l'identique (patron `ThrillSeekers`)."""
    TRIGGERED_ABILITY_ID = ECSTATIC_SLAUGHTER              # 1472

    def _has_adjacent_enemy(self, state: State) -> bool:
        """Le gate COMMUN aux deux branches : `AmountIsGreaterThanZero(AdjacentEnemies(Owner@+0x30,
        unique: true, selectionType: 3))`. Evalue par le NOEUD, pas par une re-implementation --
        c'est le meme sous-arbre que celui du behaviour."""
        ring = AdjacentEnemies(Caster(), selection_type=SEL_ALIVE_TARGETABLE)
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        return bool(ring.evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        rounds = ecstatic_slaughter_rounds(state, self.owner_id)
        # `AbilityEntities` du behaviour : le natif ancre TOUT sur `Owner@+0x30` (la chaine de
        # ciblage RE-DERIVE la cible, elle ne lit pas `Target@+0x60`), donc caster == target ==
        # le porteur -- ce que construit la ligne ci-dessous.
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        ecstatic_slaughter_tree(state, self.owner_id, rounds).execute(entities, ectx)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        taunts = [p for n, p in ectx.emitted if n == "AddBondEffect"]
        return {"ability": ABILITY_ID, "caster": int(self.owner_id),
                "attack": (atk or {}).get("attack"),
                "taunted": bool(taunts and taunts[0].get("placed")),
                "rounds": rounds, "on_event": int(ev.event_id)}


class EcstaticSlaughterOnThrilledAbility(_EcstaticSlaughterBase):
    """Branche 1 : `On(0x3e = EffectAdded) & CurrentAbilityIs(AbilityOrEffect(0x59a =
    EffectType.ThrillSeekers)) & get_OwnerIsTarget` & <gate d'adjacence>.

    Hascule vient de devenir *Thrilled* (son propre trait `ThrillSeekers` le lui pose a sa premiere
    attaque sur une cible a pleine vie, ou quand il encaisse du degat) -> il frappe.

    ⚠ Cette branche exigeait un EMETTEUR qui n'existait PAS : le port n'avait que `On(0x3d =
    PreEffectAdded)`. `dispatch/move_death.effect_added_triggers`, ajoute par cette tranche, est
    emis a la FIN d'`AddEffectOperation.execute` -- la place du natif (`AddEffectOperation$$Execute
    +0xd0b`, apres `AddNewEffect`)."""
    event_id = int(EventTriggerType.EffectAdded)           # On(0x3e = 62)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `CurrentAbilityIs(AbilityOrEffect(ThrillSeekers))` -- sur le vecteur de POSE, les DEUX
        # canaux d'ability portent la meme valeur (#306) ; on lit `triggering_ability`, le mirror
        # de `AbilityEntities+0x60` que `CurrentAbilitySelector$$Select` lit.
        if ev.triggering_ability is None or int(ev.triggering_ability) != THRILLED:
            return False
        # `get_OwnerIsTarget` : l'effet est pose SUR le porteur (`AddEffectOperation` construit son
        # `AbilityEntities` avec `target = owner = la cible de la pose`).
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False
        return self._has_adjacent_enemy(state)


class EcstaticSlaughterOnOverkillAbility(_EcstaticSlaughterBase):
    """Branche 2 : `OnDeath(overkill: true, steppable: false) & TargetIsOverkilled() &
    IsNormalUnit(Target) & AreEnemies(Owner, Target, 0) & IsAdjacent(Owner, Target, 0)` & <gate
    d'adjacence>.

    Un ennemi ADJACENT vient d'etre OVERKILL -- par n'importe qui, y compris un adversaire : il n'y
    a **aucun** `get_OwnerIsActor` (cf. l'en-tete)."""
    event_id = int(EventTriggerType.UnitDeath)             # OnDeath(...) = OnDeathEvent(0, ...)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `TargetIsOverkilled()` -- le conjoint SEPARE (celui d'`OnDeathEvent` est DESARME par
        # `triggerOnOverkill = true`). Canal `TriggerEvent.overkill`, threade par
        # `dispatch/move_death.unit_death_triggers`. Non threade -> FAUX : on ne fabrique pas un
        # overkill (meme convention qu'`ObsessiveAnnunciation`).
        if not ev.overkill:
            return False
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        if victim is None or int(victim) == int(self.owner_id):
            return False
        owner, target = state.get_entity(self.owner_id), state.get_entity(victim)
        if owner is None or target is None:
            return False
        entities = entities_from_state(state, self.owner_id, victim)
        # `steppableGate` d'`OnDeathEvent(0, a, b = false)` : `NOT HasTrait(Target, Steppable)`.
        if _TARGET_IS_STEPPABLE.should_trigger(entities):
            return False
        # `IsNormalUnit(Target@+0x60)` -- `IdunBattle.Entities.Triggers.IsNormalUnitTrigger` ecarte
        # les entites non-unites et les tokens ; le port le porte par le composant d'unite (une
        # tuile / une entite-effet n'en a pas) -- meme granularite que le gate `Steppable` juste
        # au-dessus, dont il est le voisin natif.
        if target.get_component(UnitComponent) is None:
            return False
        # `AreEnemies(Owner@+0x30, Target@+0x60, UnitTeamSelectionType 0 = ByCurrentTeam)`.
        oo, to = owner.get_component(OwnerComponent), target.get_component(OwnerComponent)
        if oo is None or to is None or oo.team == to.team:
            return False
        # `IsAdjacent(Owner@+0x30, Target@+0x60, UnitSelectionType 0)` -- le `0` ne filtre NI sur la
        # vivacite NI sur la ciblabilite (contraste avec le `3` des `AdjacentEnemies`), et c'est
        # LOAD-BEARING ici : la victime est un CADAVRE au moment ou `On(UnitDeath)` est publie, donc
        # un `3` ferait disparaitre l'adjacence et le passif ne firerait JAMAIS.
        if not _is_adjacent_units(state, int(self.owner_id), int(victim)):
            return False
        return self._has_adjacent_enemy(state)
