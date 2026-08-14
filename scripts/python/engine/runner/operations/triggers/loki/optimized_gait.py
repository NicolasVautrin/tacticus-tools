"""`OptimizedGait` (`TriggeredAbilityType` 0x4b5 = 1205, passif de kit d'`admecRuststalker`
<< Exitor-Rho >>, lineup Adeptus Mechanicus) -- les DEUX abilities TRIGGERED du passif.

i2 (`Abilities/OptimizedGait_CurrentLevelDescription`) : << Whenever an enemy adjacent to Exitor-Rho
is attacked by another friendly Mechanical unit, Exitor-Rho deals nrOfHits x minDmg-maxDmg Energy
Damage to that enemy. If an enemy adjacent to Exitor-Rho is defeated by a friendly Mechanical unit
or an attack triggered from this ability, Exitor-Rho moves onto its hex. >>

===================================================================================================
CE QUE LE PASSIF DERIVE -- TROIS classes natives, et une seule etait portee
===================================================================================================

    IdunBattleLogic.Entities.Abilities.Active.Loki.OptimizedGait_NormalAttackAbility     -> DEJA porte
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.OptimizedGait_TriggerAttackAbility -> CE module
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.OptimizedGaitAbility               -> CE module

La PREMIERE est l'attaque normale CONCRETE que la cascade
`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` substitue au porteur
(`CUSTOM_NORMAL_ATTACK_BY_PASSIVE["OptimizedGait"] == "OptimizedGait_NormalAttack"`, 1205 -> 1123),
et son gate `useSpecial` d'`InformWeapon` est porte depuis #419-r1-tr14-r4-r2-r1-r2. C'est le SEUL
canal par lequel le nom `OptimizedGait` apparaissait cote port -- une table de DISPATCH d'attaque
normale, pas un cablage de la MECANIQUE du passif. Les deux abilities TRIGGERED, qui SONT cette
mecanique, n'avaient aucun porteur (#1050).

⚠ Les deux classes triggered partagent le MEME `TriggeredAbilityType` (1205) : `TriggeredAbilityType`
ne contient qu'un `OptimizedGait`, et il n'existe aucun `OptimizedGait_TriggerAttack` dans l'enum.
Meme forme que `StormboyzStrike` (trois classes sous 1141) -- le registre les inscrit toutes deux
sous la meme cle. C'est CE fait qui rend la branche B ci-dessous non triviale : l'attaque reactive
s'execute avec `CurrentAbility = 1205`, donc le kill qu'elle cause porte `killTrigger = 1205`, ce
que `TriggeringAbilityIs(1205)` reconnait.

===================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
===================================================================================================

Slots `DSLSelectors` : `+0x30 Owner` · `+0x40 Actor` · `+0x48 Caster` · `+0x60 Target`.
Slots `DSLTriggers` : `+0x40`/`+0x70` = le trigger TOUJOURS-VRAI (meme classe, `$$.ctor` LU),
`+0x48 = op_LogicalNot(<la meme classe>)` = le trigger TOUJOURS-FAUX.

## `...OptimizedGait_TriggerAttackAbility$$CreateTrigger`

    On( 0x9 = EventTriggerType.Attack, ownerNeedsToBeAlive: true )
  & op_LogicalNot( get_OwnerIsCaster )
  & AreEnemies ( Owner@+0x30, Target@+0x60, 0 )
  & IsAdjacent ( Owner@+0x30, Target@+0x60, 0 )
  & IsMechanical( Actor@+0x40, 0 )
  & AreFriends ( Owner@+0x30, Actor@+0x40, 0, anyEntity: false )

⚠ Les trois litteraux `On(9, true)`, `IsMechanical(..., 0)` et `AreFriends(..., false, 0)` sont
DECODES AUX OCTETS (`mov edx,9` / `mov r8b,1` puis `xor r9d,r9d` ; `xor r8d,r8d` + `xor r9d,r9d` ;
`mov byte [rsp+20],0` + `mov qword [rsp+28],0`), pas lus dans le pseudo-C -- ghidra perd les
registres au trampoline.

## `...OptimizedGait_TriggerAttackAbility$$CreateBehaviour`

    b1 = AttackDamage( Owner@+0x30, Target@+0x60,
                       amount  = RandomAmount( GetVariableForLevel(0xc), GetVariableForLevel(0xd) ),
                       profile = Direct( Nullable(GetDamageProfileOrDefault(0x10)) ),
                       hits    = Direct( BaseTriggeredAbility$$GetHits() ),
                       source  = AbilityOrEffect(this), options = <struct ZEROEE> )
    b2 = ExecuteAdditionalHitsWithDamageProfileType( Owner@+0x30, Target@+0x60, source,
                                                    profile, Nullable(0x4e2), true )
    b  = b1 op_Addition b2
    bw = InformWeapon( Nullable(profile),
                       isMelee    = IBattleQuery.<slot 7> AreUnitsInMelee( entities+0x18, entities+0x10 ),
                       useSpecial = EntityExtensions.HasEffect( entities+0x18, state, 0x4e2, null ) )
    return bw op_Addition Attack( Owner@+0x30, Target@+0x60, b, <options ZEROEE> )

`BaseTriggeredAbility$$GetHits` = `config.GetNumberConstant(0x2f)` = `nrOfHits` ;
`BaseTriggeredAbility$$GetDamageProfileOrDefault(0x10)` = `config.GetDamageProfile()` avec repli.
Au gameconfig, `OptimizedGait.constants == {nrOfHits: '2', damageProfile: 'Energy'}` et ses
variables sont `minDmg`/`maxDmg` -- exactement les trois cles que ces trois lectures designent, et
mot pour mot le << nrOfHits x minDmg-maxDmg Energy Damage >> de l'i2.

⚠ **L'ANCRE des deux lectures d'entite est `entities+0x18`, c'est-a-dire l'OWNER** -- pas la cible.
Calcul d'offset, pas lecture a l'oeil : ghidra declare `undefined8 local_298[3]; void *pvStack_280;`,
donc `pvStack_280 == local_298 + 0x18`, et `local_298` est la copie de l'`AbilityEntities`
(`+0x00 actor · +0x08 caster · +0x10 target · +0x18 owner`, appariement etabli par #419-r1-tr14-r4-r2-r1).
Le second operande d'`AreUnitsInMelee` est `local_158 == local_168 + 0x10` = la CIBLE.
La fiche `case-419-r1-tr14-r4-r2-inform-weapon-tags.md` §7ter ecrivait << ancre sur la CIBLE >> pour
ce `HasEffect`-ci : la lecture est RECTIFIEE ici. L'ecart est INERTE sur ce porteur (pour une
triggered, `owner == caster == le porteur`, et c'est ce meme porteur que la mesure a 3 bras de
#419-r1-tr14-r4-r2-r1-r2 a designe pour l'attaque NORMALE) -- mais il changerait tout si un jour un
montage separait owner et cible.

## `...OptimizedGaitAbility$$CreateTrigger` -- le DEPLACEMENT

    C = OnDeath( triggerOnOverkill: true, triggerOnSteppable: false )
      & IsAdjacent( Owner@+0x30, Target@+0x60, 0 )
      & AreEnemies( Owner@+0x30, Target@+0x60, 0 )
      & CanMove   ( Owner@+0x30 )
      & IsWalkable( Tiles(Target@+0x60) )

    A = op_LogicalNot( get_OwnerIsActor )
      & IsMechanical( Actor@+0x40, 0 )
      & AreFriends ( Owner@+0x30, Actor@+0x40, 0, anyEntity: false )

    B = get_OwnerIsActor
      & TriggeringAbilityIs( AbilityOrEffect(0x4b5 = 1205 OptimizedGait) )

    return C op_BitwiseAnd ( A op_BitwiseOr B )

`IdunBattleLogic.Entities.DSLTriggers$$OnDeath(a, b)` = `OnDeathEvent(0, a, b)`, corps relu :
`On(triggerType) & <+0x70 = Yes> & (a ? <Yes> : NOT TargetIsOverkilled()) &
(b ? <Yes> : NOT HasTrait(Target@+0x60, 0x1b = Steppable))`. Avec `a = true, b = false` ->
`On(0 = EventTriggerType.UnitDeath) & NOT HasTrait(Target, Steppable)` -- **exactement** la meme
forme que `Skullsmasher_ActivateStunAbility` (litteraux `mov dl,1` / `xor r8d,r8d`).

⚠ `EventTriggerType.UnitDeath = 0`, PAS `PreUnitDeath_2 = 2` : le 3e event de
`IdunBattle.Operations.KillUnitOperation$$Execute`.

`0x4b5` du `TriggeringAbilityIs` est LU A L'ASSEMBLEUR (`mov edx,0x4b5` juste avant le
`call IdunBattle.Core.AbilityOrEffect$$op_Implicit`) : le pseudo-C ne montre qu'un buffer local.

⚠ **LES DEUX BRANCHES SONT DISJOINTES PAR CONSTRUCTION** (`OwnerIsActor` d'un cote, sa negation de
l'autre) : c'est un OU EXCLUSIF de fait, ce qui autorise le port a les evaluer en cascade sans
double-comptage. Elles sont pourtant portees comme UN SEUL trigger (et non deux entrees de registre
comme `HeadClaimer`), parce qu'elles partagent le conjoint `C` ET le behaviour : les separer
dupliquerait le `MoveUnit`.

## `...OptimizedGaitAbility$$CreateBehaviour`

    MoveUnit( Owner@+0x30, First(Tiles(Target@+0x60), 1),
              options = <0x40 octets a ZERO SAUF +0x10 = <DSLTriggers+0x48> = le trigger TOUJOURS-FAUX> )

**CET OCTET EST LE QUIRK DE LA TRANCHE, et il se lit de bout en bout** :

  * `IdunBattle.Entities.Behaviours.MoveUnitBehaviour$$.ctor` recopie `options+0x10` dans
    `this+0x70` ;
  * `IdunBattle.Entities.Behaviours.MoveUnitBehaviour$$Execute` fait
    `uVar14 = (this+0x70 != null) ? this+0x70.ShouldTrigger(entities) : TRUE` -- **le DEFAUT est
    VRAI**, c'est le seul des sept selecteurs d'options dans ce cas ;
  * puis `MoveUnitOptions+0x11 = uVar14 ^ 1` (l'octet est ECRIT NIE : `CONCAT11(uVar14, uVar13) ^ 0x101`) ;
  * et `IdunBattle.Operations.MoveUnitOperation$$Execute` fait
    `if (options+0x11 == 0) UnitExtensions.SetMovedFlag(unit)`.

Options nulles (tous les autres call-sites de `DSLBehaviors$$MoveUnit`) -> `uVar14 = true` ->
`+0x11 = 0` -> **`UnitFlag.Moved` POSE**. Ici le trigger rend FAUX -> `+0x11 = 1` -> **`Moved` N'EST
PAS POSE** : le pas d'Exitor-Rho sur l'hex du mort **ne consomme pas son deplacement**. Cote port
c'est `MoveUnitOperation(set_moved=False)`, dont le mirror etait deja ecrit (cf. la docstring de
`MoveUnitOperation`) mais que la feuille DSL `MoveUnit` ne savait pas exprimer -- elle le peut
depuis cette tranche (`set_moved=`, defaut `True` = strict no-op pour ses 30 autres call-sites).

`First(source, 1)` = `PickFirstN(source, 1)` (la surcharge `int` de `DSLSelectors$$First` construit
`Direct(amount)` et alloue un `PickFirstNSelector`), et NON un index -- meme lecture que
`stormboyz_strike_fallback_tree`.

===================================================================================================
PORTEUR / CONFRONTABILITE
===================================================================================================

`admecRuststalker` << Exitor-Rho >> est **lineup** et **dans le pool** (`rl_duit build --list-pool`).
Aucune greffe n'est necessaire. Les cinq autres porteurs (`unit_map.py find --ability OptimizedGait`)
sont des npc.

⚠ Les DEUX triggers exigent un ACTEUR `Mechanical` ALLIE du porteur, distinct de lui : le montage
minimal est donc `admecRuststalker` + une seconde unite Mechanical dans SON camp, et un ennemi
ADJACENT a `admecRuststalker` que cette seconde unite attaque.

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : ce sont des `BaseTriggeredAbility` (cf. les appels
a `BaseTriggeredAbility$$GetHits` / `$$GetDamageProfileOrDefault` dans le `CreateBehaviour`), pas des
`AActiveAbility` -- elles n'entrent pas dans `ABILITY_CLASSES` et ne traversent jamais
`IdunBattle.Operations.ActiveAbilityOperation`.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

import gameconfig as GC

from ....state import State
from ....abilities.behaviours.combat import AttackWithAttackDamage, InformWeapon
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.movement import MoveUnit
from ....components import has_effect_of_type
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Seq
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Actor, Target
from .....entities.selectors.geometry import PickFirstN
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import Tiles
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import (
    AreEnemies, AreFriends, CanMove, HasTrait, IsAdjacent, IsWalkable, TriggeringAbilityIs,
    is_mechanical
)
from .....services import battle_query as _svc_bq
from ..base import TriggeredAbility, TriggerEvent

#: La cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig du passif.
OPTIMIZED_GAIT = "OptimizedGait"
#: `TriggeredAbilityType.OptimizedGait` = `0x4b5` = 1205. ⚠ `ActiveAbilityType` 1205 nomme
#: `TalonOfHorus_NormalAttack` et `EffectType` 1205 `Fealty_ExtraHits` : trois enums, meme entier.
OPTIMIZED_GAIT_ID = TriggeredAbilityType.OptimizedGait
#: `0x4e2` = 1250 = `EffectType.CordClaw_AdditionHits` -- le MEME littéral que le gate `useSpecial`
#: de l'attaque normale substituee (`services/custom_normal_attack.py`), et le MEME que le filtre
#: d'effet du `ExecuteAdditionalHitsWithDamageProfileType` de ce behaviour.
CORD_CLAW_ADDITION_HITS = int(EffectType.CordClaw_AdditionHits)

# --- les conjoints, en NOEUDS DSL (substrat `entity_trait_names` / `board` / equipes) -------------
#: `steppableGate` d'`OnDeathEvent(0, a, b = false)` = `NOT HasTrait(Target@+0x60, 0x1b)`.
_TARGET_IS_STEPPABLE = HasTrait(Target(), int(UnitTrait.Steppable))
#: `IsMechanical(Actor@+0x40, 0)` -- le `selectionType` LITTERAL du call-site (`xor r8d,r8d`).
_ACTOR_IS_MECHANICAL = is_mechanical(Actor(), 0)
#: `AreFriends(Owner@+0x30, Actor@+0x40, 0 = ByCurrentTeam, anyEntity: false)`. `Caster()` = le slot
#: `Owner@+0x30` (sur une triggered, `Owner == Caster` -- meme convention que `skullsmasher`).
_OWNER_AND_ACTOR_ARE_FRIENDS = AreFriends(Caster(), Actor())
#: `AreEnemies(Owner@+0x30, Target@+0x60, 0 = ByCurrentTeam)`.
_OWNER_AND_TARGET_ARE_ENEMIES = AreEnemies(Caster(), Target())
#: `IsAdjacent(Owner@+0x30, Target@+0x60, 0)`. Le 3e littéral part au SELECTEUR (cf. la docstring du
#: noeud) ; `0` = `UnitSelectionType.Any`, donc AUCUN filtre -- on le passe explicitement plutot que
#: de laisser le `None` << non releve >>, parce qu'il EST relu (`xor r9d,r9d`).
_OWNER_ADJACENT_TARGET = IsAdjacent(Caster(), Target(), 0)
#: `CanMove(Owner@+0x30)`.
_OWNER_CAN_MOVE = CanMove(Caster())
#: `IsWalkable(Tiles(Target@+0x60))`. ⚠ `as_ids=True` : le foyer `Walkable` prend un ID d'entite-tuile,
#: et un `Tiles(...)` nu rend des POSITIONS -- le piege deja documente sur `Vitarus`.
_TARGET_TILE_IS_WALKABLE = IsWalkable(Tiles(Target(), as_ids=True))
#: `TriggeringAbilityIs(AbilityOrEffect(0x4b5))` -- l'ability est QUALIFIEE (`TriggeredAbilityType`),
#: jamais un entier nu : la surcharge d'`op_Implicit` du site decide de l'enum.
_TRIGGERED_BY_OPTIMIZED_GAIT = TriggeringAbilityIs(OPTIMIZED_GAIT_ID)


def _damage_profile() -> str:
    """`BaseTriggeredAbility$$GetDamageProfileOrDefault(0x10)` = `config.GetDamageProfile()` =
    `constants.damageProfile` de la config du PASSIF (`Energy` au gameconfig courant).

    Le `defaultValue = 0x10` du natif n'est consomme que si le `Nullable` de la config est VIDE ; il
    ne l'est pas ici (la cle existe), donc le port lit la config et ne modelise pas le repli --
    ecart NOMME plutot que devine."""
    return ((GC.ability(OPTIMIZED_GAIT) or {}).get("constants") or {}).get("damageProfile") or ""


def optimized_gait_attack_tree(is_melee: bool, use_special: bool) -> Seq:
    """`$$CreateBehaviour` du TriggerAttack -- MIRROR de l'`op_Addition` de tete :

        InformWeapon( Nullable(profile), isMelee, useSpecial )
      + Attack( Owner@+0x30, Target@+0x60,
                AttackDamage(...) + ExecuteAdditionalHitsWithDamageProfileType(...) )

    Cote port, le couple `Attack(AttackDamage(...))` EST `AttackWithAttackDamage` (meme paire
    `AttackBehaviour` + `AttackDamageBehaviour`), et le volet
    `ExecuteAdditionalHitsWithDamageProfileType` est joue PAR L'OPERATION
    (`damage_ops/ability.py`, sous `is_attack_damage_op and leaf_executes_additional_hits(
    is_outside_attack)`) -- donc `is_outside_attack=True` (le defaut) est ce qui le rend, et il ne
    faut surtout pas l'appeler une seconde fois a la main.

    `level_slot="passive"` : l'ability est montee avec le `passiveAbilityState` (c'est un passif de
    KIT), donc `GetVariableForLevel(0xc/0xd)` indexe le niveau des PASSIFS du porteur.

    `ability_type = 1205` = l'`AbilityOrEffect(this)` que le natif thread comme SOURCE du coup --
    c'est LUI qui, en devenant le `killTrigger` de la mort qu'il cause, arme la branche B du
    deplacement ci-dessous.

    `multi=False` + aucun `attack_state0` : le natif enveloppe la feuille dans son PROPRE
    `IdunBattleLogic.Entities.DSLBehaviors$$Attack`, donc un `OngoingAttack` NEUF, et il n'y a
    qu'UNE cible (`Target@+0x60`) -- aucun `OrderBy` a folder.

    `options` est une struct ZEROEE au call-site -> ni `alwaysOverkilled` (+4) ni `alwaysCrit` (+5)."""
    return Seq(InformWeapon(_damage_profile(), is_melee=is_melee, use_special=use_special),
               AttackWithAttackDamage(Target(), OPTIMIZED_GAIT, _damage_profile(),
                                      is_melee=is_melee, level_slot="passive",
                                      ability_type=int(OPTIMIZED_GAIT_ID), multi=False,
                                      force_overkill=False, force_crit=False))


def optimized_gait_move_tree() -> MoveUnit:
    """`...OptimizedGaitAbility$$CreateBehaviour` = `MoveUnit(Owner@+0x30, First(Tiles(Target),1),
    options{+0x10 = <DSLTriggers+0x48> = TOUJOURS-FAUX})`.

    `set_moved=False` est le mirror de cet octet, et c'est le SEUL call-site du port qui le pose :
    la chaine `behaviourOptions+0x10` -> `MoveUnitBehaviour+0x70` -> `MoveUnitOptions+0x11` (ECRIT
    NIE) -> `if (options+0x11 == 0) SetMovedFlag(unit)` est lue dans l'en-tete du module. Le pas
    d'Exitor-Rho NE CONSOMME PAS son deplacement.

    `Tiles(Target())` rend la MainTile de la victime en POSITION (le domaine par defaut du port) --
    c'est ce que `MoveUnit` consomme ; l'`as_ids=True` n'est requis que pour le gate `IsWalkable`,
    dont le foyer `Walkable` travaille en IDS."""
    return MoveUnit(Caster(), PickFirstN(Tiles(Target()), Const(1)), set_moved=False)


class OptimizedGaitTriggerAttackAbility(TriggeredAbility):
    """`...OptimizedGait_TriggerAttackAbility` (1205) : quand un allie MECHANICAL du porteur attaque
    un ennemi ADJACENT au porteur, le porteur frappe cet ennemi.

    `On(9 = Attack, ownerNeedsToBeAlive: true)` -> `fire_on_death` reste FAUX (le defaut), ce qui EST
    le gate de vivacite d'`EvaluateTriggerOperation$$CanGetAbilityTrigger`."""

    event_id = int(EventTriggerType.Attack)                   # On(9)
    TRIGGERED_ABILITY_ID = int(OPTIMIZED_GAIT_ID)             # 0x4b5 = 1205

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `op_LogicalNot(get_OwnerIsCaster)` : le porteur n'est PAS l'auteur de l'attaque. Sur
        # `On(9)` le vecteur du port construit son event avec `actor = l'attaquant`, et le natif
        # ecrit la MEME entite en `+0x00` (actor) et `+0x08` (caster) pour une attaque -- les deux
        # slots ne se separent pas sur ce vecteur.
        if ev.actor_id is None or int(ev.actor_id) == int(self.owner_id):
            return False
        if ev.target_id is None or int(ev.target_id) == int(self.owner_id):
            return False
        # `actor_id` : le slot `Actor@DSLSelectors+0x40`, que les DEUX `IsMechanical`/`AreFriends`
        # de ce trigger lisent. `entities_from_state` sait le threader -- ne pas le faire laisserait
        # `Actor()` VIDE, donc `is_mechanical` VRAI (un `all` sur l'ensemble vide) et `AreFriends`
        # FAUX : deux degradations OPPOSEES, dont la premiere est PERMISSIVE.
        entities = entities_from_state(state, self.owner_id, ev.target_id,
                                       actor_id=int(ev.actor_id))
        # `AreEnemies(Owner, Target)` puis `IsAdjacent(Owner, Target)` -- l'ORDRE est celui des
        # `op_BitwiseAnd` natifs ; il n'a pas d'effet observable (aucun n'a d'effet de bord), mais
        # le mirror se lit ligne a ligne contre le decompile.
        if not _OWNER_AND_TARGET_ARE_ENEMIES.should_trigger(entities):
            return False
        if not _OWNER_ADJACENT_TARGET.should_trigger(entities):
            return False
        if not _ACTOR_IS_MECHANICAL.should_trigger(entities):
            return False
        return bool(_OWNER_AND_ACTOR_ARE_FRIENDS.should_trigger(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # `isMelee = IBattleQuery.<slot 7> AreUnitsInMelee(owner, target)` -- le foyer porte est
        # `services.battle_query.are_tiles_adjacent` (adjacence HEX + porte d'elevation), le MEME
        # que celui d'`additional_targets.is_melee_position`. On ne le re-derive pas d'un
        # `ev.ranged` : le natif ne lit PAS la nature de l'arme de l'attaque DECLENCHANTE, il
        # mesure la GEOMETRIE entre le PORTEUR et la cible.
        is_melee = _owner_is_in_melee(state, int(self.owner_id), ev.target_id)
        # `useSpecial = EntityExtensions.HasEffect(owner, state, 0x4e2, null)` -- le 4e argument NUL
        # -> aucun filtre `onlyActive`, ce qui EST `has_effect_of_type`.
        use_special = has_effect_of_type(state, int(self.owner_id), CORD_CLAW_ADDITION_HITS)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id)
        optimized_gait_attack_tree(is_melee, use_special).execute(entities, ectx)
        hits = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        if not hits:
            return None
        return {"ability": OPTIMIZED_GAIT, "class": "TriggerAttack", "unit": int(self.owner_id),
                "actor": (None if ev.actor_id is None else int(ev.actor_id)),
                "target": int(ev.target_id), "is_melee": bool(is_melee),
                "use_special": bool(use_special),
                "attack": hits[-1].get("attack"), "on_event": int(ev.event_id)}


class OptimizedGaitMoveAbility(TriggeredAbility):
    """`...OptimizedGaitAbility` (1205) : quand un ennemi ADJACENT au porteur MEURT -- tue par un
    allie Mechanical (branche A) ou par une attaque declenchee par CE passif (branche B) -- le
    porteur avance sur son hex, SANS consommer son deplacement.

    `OnDeath(overkill: true, steppable: false)` -> `On(0 = UnitDeath)` et le seul gate de trait est
    `NOT HasTrait(Target, Steppable)` : le pas a lieu MEME sur un overkill."""

    event_id = int(EventTriggerType.UnitDeath)                # On(0)
    TRIGGERED_ABILITY_ID = int(OPTIMIZED_GAIT_ID)             # 0x4b5 = 1205

    def _victim(self, ev: TriggerEvent):
        return ev.dying_id if ev.dying_id is not None else ev.target_id

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        victim = self._victim(ev)
        if victim is None or int(victim) == int(self.owner_id):
            return False
        entities = entities_from_state(state, self.owner_id, victim)
        # --- le conjoint `C`, commun aux deux branches ------------------------------------------
        if _TARGET_IS_STEPPABLE.should_trigger(entities):        # `steppableGate` d'`OnDeathEvent`
            return False
        if not _OWNER_ADJACENT_TARGET.should_trigger(entities):
            return False
        if not _OWNER_AND_TARGET_ARE_ENEMIES.should_trigger(entities):
            return False
        if not _OWNER_CAN_MOVE.should_trigger(entities):
            return False
        if not _TARGET_TILE_IS_WALKABLE.should_trigger(entities):
            return False
        # --- `A op_BitwiseOr B` ------------------------------------------------------------------
        owner_is_actor = (ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id))
        if owner_is_actor:
            # B = `get_OwnerIsActor & TriggeringAbilityIs(1205)`. Le canal natif est
            # `AbilityEntities+0x98`, que `KillUnitOperation` remplit avec le `killTrigger` de la
            # file de morts (#301) -- cote port `state.trigger_ability_type`, pose par
            # `AttackDamageOperation._verify_deaths` le temps du drain. C'est ce canal-la, et pas
            # `ev.triggering_ability` (`+0x60`), que le natif publie VIDE sur tout le vecteur MORT.
            ents = replace(entities, attack_ability_type=getattr(state, "trigger_ability_type", None))
            return bool(_TRIGGERED_BY_OPTIMIZED_GAIT.should_trigger(ents))
        # A = `NOT get_OwnerIsActor & IsMechanical(Actor) & AreFriends(Owner, Actor)`.
        if ev.actor_id is None:
            return False
        ents = entities_from_state(state, self.owner_id, victim, actor_id=int(ev.actor_id))
        if not _ACTOR_IS_MECHANICAL.should_trigger(ents):
            return False
        return bool(_OWNER_AND_ACTOR_ARE_FRIENDS.should_trigger(ents))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        victim = self._victim(ev)
        if victim is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, victim)
        optimized_gait_move_tree().execute(entities, ectx)
        moved = [p for n, p in ectx.emitted if n == "MoveUnit"]
        if not moved:
            return None
        return {"ability": OPTIMIZED_GAIT, "class": "Move", "unit": int(self.owner_id),
                "victim": int(victim), "moved": bool(moved[-1].get("moved")),
                "to": moved[-1].get("to"), "on_event": int(ev.event_id)}


def _owner_is_in_melee(state: State, owner_id: int, target_id) -> bool:
    """`IBattleQuery.<slot 7> AreUnitsInMelee(entities+0x18 = owner, entities+0x10 = target)` --
    foyer porte `services.battle_query.are_tiles_adjacent` (adjacence HEX + porte d'elevation).

    Position d'un des deux inconnue -> `False` : le natif deref sans garde, on ne mirroir pas une
    levee et l'absence de position ne peut pas valoir << au contact >>. Meme convention que
    `additional_targets.is_melee_position`."""
    from ....components import PositionComponent
    if target_id is None:
        return False
    oe = state.get_entity(int(owner_id))
    te = state.get_entity(int(target_id))
    op = oe.get_component(PositionComponent) if oe is not None else None
    tp = te.get_component(PositionComponent) if te is not None else None
    if op is None or tp is None:
        return False
    return bool(_svc_bq.are_tiles_adjacent((op.col, op.row), (tp.col, tp.row), state.board))


__all__ = ["OPTIMIZED_GAIT", "OPTIMIZED_GAIT_ID", "CORD_CLAW_ADDITION_HITS",
           "optimized_gait_attack_tree", "optimized_gait_move_tree",
           "OptimizedGaitTriggerAttackAbility", "OptimizedGaitMoveAbility"]
