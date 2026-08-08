"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.CalibaniteGreatsword_NormalAttackAdditional
DamageAbility` (triggered `0x524` = **1316**) -- le helper PASSIF de l'active `0x4a5` = 1189
`CalibaniteGreatsword` (`darkaCompanion` << Forcas >>, HERO Dark Angels). #521-r4 / #521-r7,
case-521r1 Sec.5bis et Sec.5ter.

## Chemin de montage : `GetPassiveHelperAbility`, le SIXIEME chemin

`idun...StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility` (dict `<statics>+0x78`) porte
`1189 -> 1316`. Cote port : `PASSIVE_HELPER_ABILITY_TRIGGERS`, cle = le NOM gameconfig de l'ACTIVE.

## L'ETAGE `On(0x4a)` -- ce qui bloquait, et ce qui le leve (#521-r7)

Le `CreateTrigger` exige `On(0x4a = AttackInAtomicGroup)`. #521-r4 avait conclu qu'AUCUN emetteur
n'existait sur la voie de l'attaque NORMALE, en lisant
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteTriggerAbilities`
(qui emet `EvaluateAbilities(0x26)`). La lecture etait INCOMPLETE : l'emetteur est le SIBLING,
`...ALoki_NormalAttackAbility$$ExecuteNormalAttack`, dont le corps est

    custom = this.vslot(0x4a8)()                       # GetCustomNormalAttackBehaviour
    b      = ALoki_NormalAttackAbility$$GetAttackDamageBehaviour(this, abilityState, entities,
                                                                 attackWeapon, custom)
    b      = b op_BitwiseAnd DSLBehaviors$$EvaluateAbilities(dsl, 0x4a, null, null, null,
                                                             immediately: true)
    return AActiveAbility$$ExecuteAtomic(this, b, entities, 0x3d)

-- donc **TOUTE attaque normale** (la classe de base de toutes les `<X>_NormalAttackAbility`, y
compris la generique `Loki_NormalAttackAbility`) emet `EvaluateAbilities(AttackInAtomicGroup)`,
INCONDITIONNELLEMENT, juste apres les coups d'arme et le fold primaire, et DANS
`ExecuteAtomic(0x3d)` -- ce qui est exactement le sens du nom de l'evenement. Contraste LU :
`IdunBattleLogic.Entities.Abilities.Active.NormalAttackAbility$$CreateBehaviour` (l'autre classe
d'attaque normale, hors namespace `Loki`) emet `EvaluateAbilities(0x26, immediately: false)`.

Le port l'emet depuis `DamageHandler.visit_AttackUnitMessage`
(`operations/damage.py`), au meme rang.

## `$$CreateTrigger` (MIRROR du decompile, build `rnca9r7q6c`)

    On(0x4a = AttackInAtomicGroup, ownerNeedsToBeAlive = 0)
    & <DSLTriggers+0x20 = OwnerIsAlive>
    & get_OwnerIsActor
    & IsNormalAttack(CurrentAbility)
    & IsMeleeAttack
    & HasEffect(Owner@DSLSelectors+0x30, 0x57d = 1405 CalibaniteGreatswordSweep, onlyActive: 0)

`ownerNeedsToBeAlive = 0` n'ouvre RIEN ici : le conjoint explicite `<+0x20> = OwnerIsAlive` remet
le gate. Le port laisse donc `fire_on_death` a FAUX (defaut), ce qui est exactement le gate de
vivacite d'`EvaluateTriggerOperation$$CanGetAbilityTrigger` -- meme resultat, un seul cran.

⚠ `1405 CalibaniteGreatswordSweep` est la POSTURE : `CalibaniteGreatswordAbility$$ExecuteBehaviour`
(porte, `runner/abilities/darkangels.py`) est un TOGGLE -- Forcas demarre en posture STRIKE (1404),
et le cast bascule en SWEEP (1405). Sans cast prealable, ce trigger ne fire donc JAMAIS.

## `$$CreateBehaviour` (MIRROR du decompile)

    Foreach( CalibaniteGreatswordAbility$$GetSweepAdditionalTargets(dsl), <CreateBehaviour>b__3_0 )

    b__3_0(target) = ...CalibaniteGreatsword_NormalAttackAdditionalDamageAbility$$
                     GetAdditionalTargetsAttackBehavior(this, target)
        = DSLBehaviors$$Attack( caster = Caster@DSLSelectors+0x48, target,
            DSLBehaviors$$AttackWithAttackDamage(
                caster  = Caster@+0x48, targets = target,
                amount  = CalibaniteGreatswordAbility$$GetAdditionalTargetsDamage(dsl, false),
                profile = DSLSelectors$$Direct(Nullable(this.config.GetDamageProfile())),
                hits    = DSLFormulas$$Direct(this.config.GetNumberConstant(0x32 = nrOfHits_2)),
                source  = AbilityOrEffect(this), options = <struct ZEROEE>, selectionType = 2),
            source = AbilityOrEffect(this) )

    CalibaniteGreatswordAbility$$GetAdditionalTargetsDamage(dsl, isPrediction: false)
        = DSLFormulas$$RandomAmount( ConfigVar(0x4a5 = 1189, Caster@+0x48, 0xc = minDmg),
                                     ConfigVar(0x4a5 = 1189, Caster@+0x48, 0xd = maxDmg) )
      (la branche `isPrediction != 0` rend `Average(min, max)` -- face DECISION, hors de ce port)

    CalibaniteGreatswordAbility$$GetSweepAdditionalTargets(dsl)
        = AdjacentEnemies(Caster@+0x48, CasterTile@+0x50, unique: 1)
        & AdjacentUnits (Target@+0x60, unique: 1, selectionType: 3)

## D'OU VIENT LA CONFIG, ET POURQUOI CE N'EST PAS UNE DEDUCTION DE CONFORT

Le natif lit les DEUX constantes (`nrOfHits_2`, `damageProfile`) sur `this@+0x20`, l'
`AbilityConfiguration` de l'instance d'ability, et les DEUX bornes sur le litteral `0x4a5` = 1189.
Or **1316 n'a AUCUNE configuration propre** : ni entree gameconfig (`GC.ability(...)` -> None), ni
entree `BattleConfiguration.Abilities.{Active,Passive}Abilities`. MESURE du 2026-08-08 sur
`data/seed-bc.json` : les TROIS helpers de `GetPassiveHelperAbility` deja identifies sont dans ce
cas (`TalonsOfTheEmperor_UsedAbilities`, `DoctrinaImperatives_SetStart`,
`CalibaniteGreatsword_NormalAttackAdditionalDamage` -- 0/3 present), alors que leurs trois ACTIVES
porteuses le sont (3/3). La seule configuration atteignable est donc celle de l'ACTIVE 1189, et
c'est corrobore par le gameconfig lui-meme : `CalibaniteGreatsword.constants` porte EXACTEMENT
`{damageProfile: "Power", nrOfHits_2: "3"}` -- deux constantes que l'ability ACTIVE 1189 relit
elle-meme pour SA propre passe de balayage
(`CalibaniteGreatswordAbility$$GetAdditionalTargetsHits` = `ConfigConst(0x4a5, Caster, 0x32)`,
`...$$GetAdditionalTargetsDamageProfileType` = `config.GetDamageProfile()`).

## RANG et CONSOMMATION RNG

Le `CreateBehaviour` natif est PLAIN (pas d'`ExecuteAtomic`) : chaque cible est enveloppee dans son
PROPRE `DSLBehaviors$$Attack`, donc `StartAttackOperation$$Execute` pousse un `OngoingAttack` NEUF
par cible -> `attack_state0=None`, `multi=False` (surtout pas `multi=True`, qui trierait par id).
L'ordre est celui du SELECTEUR, comme pour le CLEAVE de #478.
"""
from __future__ import annotations

from typing import Optional

import gameconfig as GC

from ....state import State
from ....components import has_effect_of_type
from ....abilities.attack_type import is_normal_attack
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.behaviours import Foreach
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import CasterTile, Subject, Target
from .....entities.selectors.units import AdjacentEnemies, AdjacentUnits, And
from .....entities.triggered_ability_type import TriggeredAbilityType
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `PASSIVE_HELPER_ABILITY_TRIGGERS` = le NOM gameconfig de l'ACTIVE 0x4a5 = 1189.
CALIBANITE_GREATSWORD_ACTIVE = ActiveAbilityType.CalibaniteGreatsword.name
#: `HasEffect(Owner@+0x30, 0x57d, onlyActive: 0)` -- la POSTURE balayage, posee par le TOGGLE 1189.
CALIBANITE_GREATSWORD_SWEEP = int(EffectType.CalibaniteGreatswordSweep)            # 0x57d = 1405


def sweep_additional_targets():
    """`CalibaniteGreatswordAbility$$GetSweepAdditionalTargets(dsl)` -- MIRROR 1:1 :

        AdjacentEnemies(Caster@+0x48, CasterTile@+0x50, unique: 1)
      & AdjacentUnits (Target@+0x60, unique: 1, selectionType: 3)

    = les ennemis adjacents a l'EMPREINTE du caster ET adjacents a la CIBLE. La surcharge appelee
    est `AdjacentEnemies(this, unit, unitTile, unique)` (3e argument = un SELECTEUR DE TUILES) --
    tranchee par XREF entrante, pas par arite ; c'est la MEME que celle de `TalonOfHorus`
    (`abilities/loki/additional_targets.py`), d'ou le meme `AdjacentEnemies(CasterTile(), ...)`."""
    return And(AdjacentEnemies(CasterTile(), Const(1)),
               AdjacentUnits(Target(), Const(1)))


def _sweep_damage_profile() -> str:
    """`this.config.GetDamageProfile()` = `constants.damageProfile` de la config LUE, c'est-a-dire
    celle de l'ACTIVE 1189 (cf. l'en-tete : 1316 n'a AUCUNE configuration propre)."""
    return ((GC.ability(CALIBANITE_GREATSWORD_ACTIVE) or {}).get("constants") or {}
            ).get("damageProfile") or ""


def sweep_attack_leaf(target_sel):
    """`...$$GetAdditionalTargetsAttackBehavior(this, target)` -- la feuille, MIRROR 1:1.

    * `ability_id = "CalibaniteGreatsword"` + `level_slot="active"` = `ConfigVar(0x4a5, Caster,
      0xc/0xd)` : les bornes sont celles de l'ACTIVE 1189, au niveau que le CASTER a pour elle ;
    * `hits_key = "nrOfHits_2"` = `GetNumberConstant(0x32)` ;
    * `profile` = `GetDamageProfile()` ;
    * `ability_type = 1316` = l'`AbilityOrEffect(this)` que le natif thread comme SOURCE du coup
      (c'est la TRIGGERED, pas l'active qui la registre) ;
    * `is_melee=True` : le trigger porte `IsMeleeAttack`, donc ce coup n'existe que sur une attaque
      de melee -- on ne re-derive pas la nature d'une adjacence ;
    * `multi=False` + aucun `attack_state0` : le natif enveloppe CHAQUE cible dans son propre
      `DSLBehaviors$$Attack`, donc un `OngoingAttack` NEUF par cible et AUCUN tri par id ;
    * `options` est une struct ZEROEE au call-site -> ni `alwaysOverkilled` (+4) ni `alwaysCrit`
      (+5)."""
    return AttackWithAttackDamage(
        target_sel, CALIBANITE_GREATSWORD_ACTIVE, _sweep_damage_profile(), is_melee=True,
        hits_key="nrOfHits_2", level_slot="active", multi=False,
        ability_type=int(TriggeredAbilityType.CalibaniteGreatsword_NormalAttackAdditionalDamage))


def calibanite_greatsword_sweep_tree():
    """`$$CreateBehaviour` = `Foreach(GetSweepAdditionalTargets(dsl), b__3_0)`. PLAIN : aucun
    `ExecuteAtomic` (contraste avec le CLEAVE de #478, qui en porte un)."""
    return Foreach(sweep_additional_targets(), sweep_attack_leaf(Subject()))


class CalibaniteGreatswordNormalAttackAdditionalDamageAbility(TriggeredAbility):
    """`CalibaniteGreatsword_NormalAttackAdditionalDamage` (triggered 1316) -- cf. l'en-tete.
    `owner_id` = l'unite qui POSSEDE l'active 1189, instanciee par le registre
    `PASSIVE_HELPER_ABILITY_TRIGGERS` (mirror de `GetPassiveHelperAbility`)."""
    event_id = EventTriggerType.AttackInAtomicGroup      # On(0x4a, ownerNeedsToBeAlive = 0)
    TRIGGERED_ABILITY_ID = TriggeredAbilityType.CalibaniteGreatsword_NormalAttackAdditionalDamage

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : l'attaque doit etre CELLE du porteur.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        if ev.target_id is None:
            return False
        # `IsNormalAttack(CurrentAbility@DSLSelectors+0x88)` -- meme foyer de gate que
        # `AnvilShieldFrozenAttackerAdvantageAbility` : c'est le marqueur de kind `0x3f5` que la
        # voie NORMALE thread qui le satisfait ; un cast d'ability thread son propre
        # `ActiveAbilityType` et ne passe pas (c'est ce qui empeche 1316 de fire sur le
        # `EvaluateAbilities(0x4a)` d'`ArmoriumCherub`).
        if not is_normal_attack(ev.ability_type):
            return False
        # `IsMeleeAttack` -- la nature de l'ARME choisie par `ALoki_NormalAttackAbility$$
        # FindAttackWeapon`, threadee telle quelle par l'emetteur (`ev.ranged`).
        if ev.ranged:
            return False
        # `HasEffect(Owner@DSLSelectors+0x30, 0x57d, onlyActive: 0)` : `onlyActive` NUL au
        # call-site -> aucun filtre `IsActive`, exactement ce que fait `has_effect_of_type`.
        return has_effect_of_type(state, int(self.owner_id), CALIBANITE_GREATSWORD_SWEEP)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id)
        calibanite_greatsword_sweep_tree().execute(entities, ectx)
        hits = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        if not hits:
            return None
        return {"ability": "CalibaniteGreatsword_NormalAttackAdditionalDamage",
                "owner": int(self.owner_id), "target": int(ev.target_id),
                "sweep": [{"target": p.get("target"), "attack": p.get("attack")} for p in hits]}
