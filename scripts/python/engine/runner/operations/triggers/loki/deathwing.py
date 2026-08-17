"""Passif `Deathwing` de `darkaTerminator` << Baraqiel >> (Dark Angels) --
`TriggeredAbilityType 0x4dd = 1245`. CE fichier porte l'ACCUMULATION du stack ; la MAGNITUDE vit
dans `entities/effects/loki/deathwing.py::DeathwingEffect` (#932).

i2 `Abilities/Deathwing_CurrentLevelDescription` : << Each time Baraqiel **blocks damage during an
attack**, all further incoming damage is reduced by {dmgReduction} and the damage Baraqiel deals
with melee or *Plasma Cannon* attacks is increased by {extraDmg} **for 1 round**. This effect is
doubled against Chaos enemies or when standing adjacent to another friendly Dark Angel. >>

Porter l'une sans l'autre laisse soit un effet INERTE (niveau fige au seed), soit un compteur MORT --
les deux se degradent en silence (meme couple que `FuelledByFury`).

===================================================================================================
RE native (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
===================================================================================================

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.DeathwingAbility
        : IdunBattle.Entities.Abilities.BaseTriggeredAbility            (frida/classes.tsv)

CE QUE LA CLASSE DECLARE (`global-metadata.dat`) -- 5 entrees, aucune de plus :

    [CreateTrigger (slot 26), CreateBehaviour (slot 28), GetEffectType (slot 35), GetEffect, .ctor]

Pas d'`OnOwnerSpecificAbilityInit`, pas de `CreateHandleTriggerAbilities` : le canal de port est
donc `ABILITY_TRIGGERS`, et NON `ABILITY_INIT_OWNER_EFFECTS` (l'effet n'est PAS pose au deploiement,
il nait du premier blocage).

## `...DeathwingAbility$$CreateTrigger`

    On(EventTriggerType.Attack = 9, ownerNeedsToBeAlive: true)
      & get_OwnerIsTarget
      & WasBlock()

TROIS termes, et c'est TOUT -- a comparer au trigger du voisin `TerminatorArmour_ReduceDmg_Effect`
(`On(9) & AreEqual(Units(Target), Owner) & CurrentAttackDamageProfilesContainOtherThan(...) &
AmountIsZero(CurrentShieldAmount(Target)) & (AmountIsGreaterThanZero(HealthDamageFromEvent()) |
WasBlock())`), que le MEME porteur transporte via son trait `TerminatorArmour`. Ici : **aucun** gate
de profil de degat, **aucun** gate de bouclier, **aucune** exigence de degat aux PV. Un blocage
suffit, meme si l'attaque n'a rien entame.

⚠ `EventTriggerType` 9 = `Attack` dans `IdunBattle.DSL.EventTriggerType` -- l'homonyme
`UnityEngine.EventSystems.EventTriggerType` 9 est `Select`. L'enum est QUALIFIE, jamais lu a
l'ordinal.

`On(9)` est emis par `IdunBattle.Operations.FinishAttackOperation$$Execute`, **UNE SEULE FOIS PAR
ATTAQUE**, a sa cloture -- donc le stack monte de **+1 par ATTAQUE bloquee**, pas de +1 par COUP
bloque. Le regime mono-coup est DEGENERE (les deux lectures y coincident) : le discriminant est une
attaque MULTI-COUPS dont plusieurs coups sont bloques.

## `...DeathwingAbility$$CreateBehaviour`

    If( HasEffect(Owner@DSLSelectors+0x30, GetEffectType(), onlyActive: false,
                  EffectTargetType.Both = 6),
        IncreaseEffectLevel( EffectFromOwner(Owner@+0x30, GetEffectType()),
                             amount: NULL, max: NULL ),
        AddEffect( GetEffectType(), <BaseTriggeredAbility.get_AbilityStateReference>,
                   source = Owner@+0x30, targets = Owner@+0x30,
                   turns = TurnsFromRounds(1) ) )

* `GetEffectType()` est un VIRTUEL (slot 35) : `DeathwingAbility` rend `0x526 = 1318`
  (`EffectType.Deathwing`) et sa fille `DeathwingKnightAbility` rend `0x5e8 = 1512`
  (`EffectType.DeathwingKnight`) -- elle n'override QUE ce slot. `DeathwingKnight` n'est pas portee
  ici (une ability par tranche ; ses porteurs sont un npc et un summon).
* `IncreaseEffectLevel` est la surcharge **3-args** `(effect: ITargetsSelector, amount, max)`
  (`0x180ea3610`, tranchee par ses XREFS ENTRANTES), pas la 4-args `(owner, effectType, amount,
  max)` qu'utilise `FuelledByFury`. Le sélecteur `EffectFromOwner(Owner, T)` designe l'ENTITE-EFFET
  de type `T` portee par l'Owner ; cote port, `IncreaseEffectLevel(<type>, Caster(), ...)` designe
  le MEME ensemble d'instances (meme collapse que `neuroparasite.py`).
* `amount = NULL` -> `IdunBattleLogic.Entities.DSLBehaviors$$IncreaseEffectLevel` substitue
  `df@0xc0 = Const(1)` : increment **+1** par declenchement.
* `max = NULL` -> **AUCUN CAP** (le clamp d'`IdunBattle.Operations.IncreaseEffectLevelOperation$$
  Execute` est desactive) -- contraste `TerrifyingCrescendo` (`buffMaxLevel = 6`). Le gameconfig
  `Deathwing` ne porte d'ailleurs AUCUNE constante (`upgrades: null`, deux variables et rien
  d'autre), donc il n'y a pas de plafond a chercher.
* `turns = TurnsFromRounds(1)` (surcharge `AddEffect(effectType, abilityState, source, targets,
  turns: IAmountFormula)`, `0x180e9e9b0`) -> l'effet dure **1 round**, contraste `FuelledByFury`
  dont l'options-struct ZEROEE donne un effet PERMANENT. C'est le << for 1 round >> de l'i2.
* l'`AddEffect` ne porte PAS de `level` initial (aucune options-struct) : le niveau de la 1re pose
  retombe sur le defaut natif **1** d'`IdunBattle.Operations.AddEffectOperation$$Execute`
  (`local_588[0] = 1`).

## Frontiere DSL/imperatif (#149)

Le behaviour est un ARBRE (`If(HasEffect, IncreaseEffectLevel, AddEffect)`), mirrore noeud par
noeud. Il n'utilise PAS le helper `add_effect_or_increase_level` : celui-ci mirroire la FACTORY
COMPOSITE `IdunBattleLogic.Entities.DSLBehaviors$$AddEffectOrIncreaseLevel`, qui alloue un
`ForeachBehaviour` et passe un `level` explicite -- deux noeuds que ce `CreateBehaviour`-ci n'a pas.
Les feuilles restent imperatives (`IncreaseEffectLevelOperation`, `AddEffectOperation`).

## RESIDUS NOMMES

* `On(9)` du port vit au niveau MESSAGE (attaque normale) / SORTIE D'OPERATION (attaque d'ability) :
  une attaque declenchee par un TRIGGER (le tir d'overwatch) ne le traverse pas -- divergence
  STRUCTURELLE preexistante, documentee dans `dispatch/attack.py::attack_damage_attack_triggers`
  et deja portee au compte de `TerminatorArmour`. Consequence ici : un blocage sur un tir
  d'overwatch ne monte pas le stack cote port alors qu'il le monte cote natif.
* `ownerNeedsToBeAlive: true` (2e argument d'`On`) n'est pas modelise separement : le port n'arme
  pas `fire_on_death`, ce qui est la MEME semantique (le trigger ne joue pas si le porteur est
  mort).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, IncreaseEffectLevel
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If as IfBehaviour
from .....entities.effect_type import EffectType
from .....entities.effects.loki.deathwing import ABILITY_ID, ABILITY_ID_KNIGHT
from .....entities.selectors.tiles import Caster
from .....entities.triggers import HasEffect
from .....entities.triggered_ability_type import TriggeredAbilityType
from ..base import TriggeredAbility, TriggerEvent

#: `EffectType.Deathwing` = `0x526` = 1318 -- le retour du VIRTUEL `DeathwingAbility$$GetEffectType`
#: (la fille `DeathwingKnightAbility` rend `0x5e8` = 1512, non portee ici).
DEATHWING_EFFECT = int(EffectType.Deathwing)
#: nom d'`EffectType` capte live (`decisionView.effects[].name`) -- la cle d'`EFFECT_CLASSES`.
DEATHWING_EFFECT_NAME = EffectType.Deathwing.name
#: `TriggeredAbilityType.Deathwing` = `0x4dd` = 1245 -- le litteral du `.ctor` du playbook et
#: l'`AbilityOrEffect` que le `.ctor` de l'effet passe a `BaseEffect`.
DEATHWING_ABILITY = TriggeredAbilityType.Deathwing
#: `TurnsFromRounds(1)` -- la duree LUE au 5e argument de l'`AddEffect`.
DEATHWING_DURATION_ROUNDS = 1
#: #1073 -- `EffectType.DeathwingKnight` = `0x5e8` = 1512, le retour du MEME virtuel sur la fille
#: `DeathwingKnightAbility`, et `TriggeredAbilityType.DeathwingKnight` = `0x5e6` = 1510.
DEATHWING_KNIGHT_EFFECT = int(EffectType.DeathwingKnight)
DEATHWING_KNIGHT_EFFECT_NAME = EffectType.DeathwingKnight.name
DEATHWING_KNIGHT_ABILITY = TriggeredAbilityType.DeathwingKnight


def deathwing_tree(effect_type: int = DEATHWING_EFFECT, effect_name: str = DEATHWING_EFFECT_NAME):
    """Mirror 1:1 de `...DeathwingAbility$$CreateBehaviour` (cf. l'en-tete du module) :

        If( HasEffect(Owner@+0x30, GetEffectType(), onlyActive: false, Both),
            IncreaseEffectLevel(EffectFromOwner(Owner, GetEffectType()), +1, SANS cap),
            AddEffect(GetEffectType(), AbilityStateReference, Owner, Owner, TurnsFromRounds(1)) )

    `Caster()` = `Owner@DSLSelectors+0x30` : le porteur du trigger est aussi la source ET la cible de
    l'effet. `active_only=False` mirroire le 3e argument `0` du `HasEffect` natif -- une instance
    INACTIVE compte, donc on n'en repose pas une seconde par-dessus.
    `scale_from_source=True` porte l'`AbilityStateReference` : l'instance materialisee resout ses
    `ConfigVar` contre l'etat d'ability de sa SOURCE (le porteur), ce dont la face MAGNITUDE
    (`DeathwingEffect`) a besoin -- sans lui, `ability_level` reste None et l'effet est INERTE.
    `max_level=None` = le `max` NULL natif (aucun clamp).

    #1073 -- l'`EffectType` est un PARAMETRE parce qu'il l'est aussi cote natif : les trois
    occurrences du pseudo-C sont l'appel virtuel `(**(code **)(*this + 0x368))(this, ...)`, c.-a-d.
    le slot 35 `GetEffectType`. `DeathwingAbility` y rend `0x526` (= 1318) et sa fille
    `DeathwingKnightAbility` `0x5e8` (= 1512) -- cette derniere n'override QUE ce slot, ce qui est
    LU : le metadata lui declare exactement `[GetEffectType (slot 35), .ctor]`, et le bloc
    `methodPointers` du PE, ancre sur son `$$GetEffectType` (seul symbole propre de la classe),
    n'expose aucune autre entree. Le trigger, le behaviour et le `GetEffect` viennent donc du
    parent, litteralement -- un seul corps, deux valeurs."""
    return IfBehaviour(
        HasEffect(Caster(), effect_type, active_only=False),
        IncreaseEffectLevel(effect_type, Caster(), Const(1), None),
        AddEffect(effect_type, effect_name, Caster(),
                  duration_rounds=DEATHWING_DURATION_ROUNDS, scale_from_source=True))


class DeathwingAbility(TriggeredAbility):
    """`...DeathwingAbility` -- `On(9 = Attack, ownerNeedsToBeAlive: true) & get_OwnerIsTarget &
    WasBlock()` -> `If(HasEffect(Owner, 1318), IncreaseEffectLevel(+1, SANS cap),
    AddEffect(1318, turns = TurnsFromRounds(1)))`. Cf. l'en-tete de module pour les deux arbres."""

    event_id = int(EventTriggerType.Attack)                     # On(9)
    TRIGGERED_ABILITY_ID = DEATHWING_ABILITY                    # 1245 (l'ability EST le passif)
    #: `GetEffectType()` (slot 35) -- VIRTUEL, d'ou l'attribut de classe (#1073).
    EFFECT_TYPE = DEATHWING_EFFECT                              # 0x526 = 1318
    EFFECT_NAME = DEATHWING_EFFECT_NAME
    #: la cle gameconfig rendue dans le compte-rendu du behaviour -- celle de CETTE ability.
    ABILITY_KEY = ABILITY_ID

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsTarget` = `AreEqual(<Sel+0x30 = Owner>, <Sel+0x60 = Target>)` : le porteur EST
        # la cible de l'attaque qui vient de se clore.
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False
        # `WasBlock()` -- l'attaque a-t-elle ete BLOQUEE ? Canal `TriggerEvent.was_block`, threade
        # par les DEUX voies de cloture (`dispatch/attack.py`). Non threade -> FAUX : on ne fabrique
        # pas un blocage (meme convention que `terminator_armour.py`).
        return bool(ev.was_block)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        deathwing_tree(self.EFFECT_TYPE, self.EFFECT_NAME).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        lvl = None
        for n, p in ectx.emitted:
            if n in ("IncreaseEffectLevel", "AddEffect"):
                lvl = p.get("level")
        return {"ability": self.ABILITY_KEY, "unit": int(self.owner_id),
                "attacker": ev.actor_id, "level": lvl, "on_event": int(ev.event_id)}


class DeathwingKnightAbility(DeathwingAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DeathwingKnightAbility` -- passif du summon
    `darkaSmnTerminator` << Deathwing Knight >> et de son jumeau npc `darkaNpc3Terminator` (#1073).

    `frida/classes.tsv` la donne fille de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DeathwingAbility` (et non de
    `BaseTriggeredAbility`), et le `global-metadata.dat` lui declare exactement DEUX entrees --
    `[GetEffectType (slot 35), .ctor]`. Elle n'override donc RIEN d'autre : `CreateTrigger`,
    `CreateBehaviour` et `GetEffect` sont ceux du parent, au corps pres.

    `...DeathwingKnightAbility$$GetEffectType` a pour corps ENTIER `return 0x5e8` (= 1512
    `EffectType.DeathwingKnight`) la ou `...DeathwingAbility$$GetEffectType` rend `0x526` (= 1318).
    C'est le SEUL delta de la classe, et l'appariement ability -> effet en decoule -- il est LU, pas
    devine.

    ⚠ L'i2 de ce passif (<< the damage he deals is increased >>) omet la restriction
    << melee or *Plasma Cannon* >> que porte celui de `Deathwing`. Le corps natif, lui, est
    LITTERALEMENT LE MEME (`IsMeleeAttack() | NOT IsNormalAttack()` du
    `DeathwingEffect$$CreateEffectDamageBonusForAttack` partage). La prose diverge, le code non."""

    TRIGGERED_ABILITY_ID = DEATHWING_KNIGHT_ABILITY              # 0x5e6 = 1510
    EFFECT_TYPE = DEATHWING_KNIGHT_EFFECT                        # `$$GetEffectType` -> 0x5e8 = 1512
    EFFECT_NAME = DEATHWING_KNIGHT_EFFECT_NAME
    ABILITY_KEY = ABILITY_ID_KNIGHT
