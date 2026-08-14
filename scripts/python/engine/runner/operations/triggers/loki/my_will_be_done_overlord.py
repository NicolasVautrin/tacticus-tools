"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MyWillBeDoneOverlordAbility` -- le passif
`MyWillBeDoneOverlord` (`TriggeredAbilityType` 0x614 = 1556) de `necroOverlord` (Necrons, HERO,
DANS LE POOL rank courant). Tache #354-r1, face COMBAT.

Face DECISION (`MyWillBeDoneOverlordPlaybook` / `MyWillBeDoneOverlordNonOwnerPlaybook`) = HORS
PERIMETRE (comptee en #271-r4).

⚠ PIEGE DE RECENSEMENT (mesure de l'orchestrateur, 2026-07-31) : un PASSIF n'apparait PAS dans
`decisionView.abilities` -- le `decisionView` LIVE de `necroOverlord` n'expose que
`['Loki_NormalAttack', 'ResurrectionOrb']`. On observe cette ability par son EFFET (un allie attaque
au tour du porteur), jamais par une liste de kit live.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c` ; les deux fonctions ont ete RE-LUES A L'ASSEMBLEUR pour
lever les fusions de slots de pile de ghidra -- tous les litteraux ci-dessous sortent du desassemblage)
================================================================================================

## 1. `...MyWillBeDoneOverlordAbility$$CreateTrigger` (disjonction `AbilityTrigger.op_BitwiseOr`)

    ( On(0x12 = TurnStart_EffectActivation, ownerNeedsToBeAlive = 1)
      & AmountIsGreaterThanZero( GetPersistentDataListAsEntities(AbilityOrEffect(this.Id),
                                                                 Owner@DSLSelectors+0x30,
                                                                 Get(<champ statique = dataKey>)) ) )
    | ( On(0x29 = UnitFinishedTurnNormally, ownerNeedsToBeAlive = 1) & get_OwnerIsActor )

Les DEUX litteraux d'enum sont RE-DERIVES de `data/symbols/rnca9r7q6c/frida/enums.tsv`
(`IdunBattle.DSL.EventTriggerType`) : `18 = 0x12 = TurnStart_EffectActivation`,
`41 = 0x29 = UnitFinishedTurnNormally`. Ce build a renumerote quatre enums (#252/#283) -- la
transcription heritee de #361 est CONFIRMEE sur ce point, pas recopiee.

## 2. `...MyWillBeDoneOverlordAbility$$CreateBehaviour(abilityState, triggerType)`

    if (triggerType == 0x12)
        return ClearAllPersistentData( AbilityOrEffect(this.Id), Owner@0x30 )

    target = GetTargetFriend()                       # cf. section 3 -- UN SEUL noeud, PARTAGE
    maxDmg = GetVariableForLevel(config, 0x0d = maxDmg, abilityState, 0)
    dmgPct = GetVariableForLevel(config, 0x4a = dmgPct, abilityState, 0)
    dmg    = PercentageOfAttackCappedAtMax( unit = target, statPart = 0 = Current,
                                            maxAmount = Get(maxDmg), percentage = Get(dmgPct),
                                            roundingRule = 0 )
    then   =   AddTemporaryAttackOverrideEffect(target, dmg)
             & PerformAIAttackFromCurrentPosition(target, utilityEntity = 0, customUtility = 0,
                                                  skipAtomicCheck = 0)
             & ResetTemporaryAttackOverrideEffect(target)
             & AddToPersistentDataList( AbilityOrEffect(this.Id), Owner@0x30,
                                        Get(<dataKey>), EntityId(target) )
    els    = AddDynamicStatModifierEffectToOwner( 0x62d = EffectType.MyWillBeDoneOverlord_ExtraDamage,
                                                  statType = 0 = Attack,
                                                  turns = Sum(TurnsFromRounds(1), <DSLFormulas+0x20
                                                              = Direct(1)>),
                                                  isHidden = 0 )
    return If(target, then, els)

  * `AddTemporaryAttackOverrideEffect(targets, amount)` = `AddStatOverrideEffectBehaviour(targets,
    effectType = 0x510 = EffectType.TemporaryStatOverride, statType = 0 = Attack, amount,
    duration = 0, flag = 1)` -- le MEME couple pose/retrait qu'`ExemplarOfHate` et
    `SternguardFocus` encadrent autour de leur attaque libre (NET-ZERO apres le cast).
  * `ResetTemporaryAttackOverrideEffect(targets)` = `RemoveEffect(targets, Nullable(0x510), 0)`.
  * `PercentageOfAttackCappedAtMax` = `Min(maxAmount, PercentageOf(StatAmount(unit, ATTACK,
    statPart), pct))` -- semantique PROUVEE par identite de singleton de classe (cf.
    `entities/formulas.py::percentage_of_attack_capped_at_max`). ⚠ Le `unit` est ici l'ARBRE
    `GetTargetFriend` LUI-MEME, pas `Subject@0x180` (contraste ExemplarOfHate) : le montant est
    calcule sur l'ATTAQUE de l'allie elu.
  * `AddDynamicStatModifierEffectToOwner` = `AddStatModifierEffectBehaviour(isDynamic = 1,
    source = Owner@0x30, targets = Owner@0x30, effectType, statType, amount = null, turns, ...)`
    -> l'Overlord se BUFFE lui-meme quand aucun allie n'est eligible.

## 3. `...MyWillBeDoneOverlordAbility$$GetTargetFriend` -- le selecteur (arbre LU au desassemblage)

    it = ActiveTarget@DSLSelectors+0x68        # l'ELEMENT COURANT lie par le `Filter` englobant

    base =   HasTrait(it, 0x05 = Mechanical)
           & AmountIsGreaterThanZero( ValidNormalAttackTargets(it, Tiles(it), range = 0,
                                                               <regles par defaut>) )
           & NOT IsInPersistentDataList( AbilityOrEffect(this.Id), Owner@0x30, Get(<dataKey>),
                                         EntityId(it) )
           & (   NOT TriggeringAbilityIs(AbilityOrEffect(0x615 = 1557 PhasalSubjugator))
               | IsUnitWithVisualId(it, VisualUnitIdFromUnitId(
                                          ConfigConstString(TriggeredAbilityConfigId(0x615), 0))) )

    pool = Filter( AdjacentFriends(CasterTiles@DSLSelectors+0x58, unique = 1, selType = 3), base )

    A = Filter(pool,      HasFaction(it, 0x7 = Necrons, 3)  &      HasTrait(it, 0x10 = Hero) )
    B = Filter(pool, NOT  HasFaction(it, 0x7, 3)            &      HasTrait(it, 0x10)        )
    C = Filter(pool,      HasFaction(it, 0x7, 3)            & NOT  HasTrait(it, 0x10)        )
    D = Filter(pool, NOT  HasFaction(it, 0x7, 3)            & NOT  HasTrait(it, 0x10)        )

    return First( SortByFormula( A.Otherwise(B).Otherwise(C).Otherwise(D),
                                 StatAmount(it, statType = 0 = Attack, statPart = 0, 0, 0),
                                 ascending = 0 ),          # 0 = DESCENDANT
                  amount = 1, ignoreForcedTargets = 0 )

  * `Otherwise(x, y)` = « si x rend un set VIDE, prendre y ». L'ordre de preference est donc
    **Necron-Hero > Hero non-Necron > Necron non-Hero > le reste**, et A L'INTERIEUR du groupe elu,
    l'allie de plus GROSSE Attaque courante (tri DESCENDANT, `ascending = 0` lu au desassemblage).
  * `HasTrait 0x05 = Mechanical` (le trait NU, PAS le `IsMechanical` a trois traits de
    `ResurrectionOrb`) ; `0x10 = Hero` ; `UnitFaction 0x7 = Necrons` -- les trois re-derives de
    `enums.tsv`.
  * Le terme `!TriggeringAbilityIs(1557) | IsUnitWithVisualId(...)` est le SEUL a n'etre pas
    porte -- il est TAUTOLOGIQUE sur le vecteur porte, cf. section 5.

## 4. VECTEUR `On(0x29 = UnitFinishedTurnNormally)` -- ou le natif l'emet, et pourquoi c'est le bon point d'ancrage

`IdunBattle.Operations.FinishUnitTurnOperation$$Execute(unit, isTerminated)` (relu) :

    if (isTerminated) flags.Add(0x1b)
    if (flags.Add(0x01 = ArrivedAtFinalTile) && !isTerminated)  publish On(0x1c)
    if (flags.Add(0x03 = TurnFinished)) {
        publish On(0x28 = UnitFinishedTurn)
        if (!isTerminated) publish On(0x29 = UnitFinishedTurnNormally)
        <event de vue 0xc>
    }

Donc `On(0x29 = UnitFinishedTurnNormally)` = « cette unite vient de CLORE son activation, et pas par une terminaison forcee ».
Le port l'emet au MEME endroit (`operations/turnflow.py::FinishUnitTurnOperation.execute`, apres le
`On(0x1c)`), sous les MEMES deux gates (`newly_finished` et `not forced`).
`On(0x28 = UnitFinishedTurn)` reste NON EMIS cote port : aucun consommateur porte -- residu nomme, pas un oubli.

## 5. LE TERME `TriggeringAbilityIs(PhasalSubjugator)` -- pourquoi il ne mord PAS ici

`0x615 = 1557 = TriggeredAbilityType.PhasalSubjugator`, dont
`IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant(config, 0)` vaut `"necroSmnWarrior"`
(gameconfig `PhasalSubjugator.constants.unitId`). Le terme dit donc : « si cette triggered-ability a
ete rejouee PAR `PhasalSubjugator`, seul un `necroSmnWarrior` est eligible ».

Ce regime EXISTE cote natif et il est NOMME :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhasalSubjugator_TriggerPassiveAbility$$CreateBehaviour`
contient `TriggerAbility(Owner@0x30, 0x614 = 1556, ..., selectionType = 3,
ignoreUnitHavingAbility = 0)` -- meme chaine que la branche `Custom` de `RelentlessMarch`
(`TriggerTriggeredAbilityOperation$$TriggerAbility` -> `ExecuteBy(..., 0x20 = Custom)`).

Sur le vecteur PORTE (`On(0x29 = UnitFinishedTurnNormally)`), en revanche, le canal `TriggeringAbility` est **VIDE** :
`FinishUnitTurnOperation$$Execute` publie l'evenement avec une structure `Nullable<AbilityOrEffect>`
ENTIEREMENT NULLE (les quatre mots de pile sont mis a zero juste avant le `call` -- controle fait au
desassemblage). `TriggeringAbilityIs(1557)` y est donc TOUJOURS faux, `NOT(...)` TOUJOURS vrai, et la
disjonction TOUJOURS vraie. **Omettre le terme est EXACT sur ce vecteur, pas une approximation.**

⚠ **L'APPELANT `Custom` EXISTE DESORMAIS (#1011-r1), ET LE TERME RESTE OMIS -- la premisse du residu
qui vivait ici est REFUTEE, pas satisfaite.** Elle disait : « le jour ou la branche `Custom` a un
appelant, le terme (et son `IsUnitWithVisualId`) doit etre pose ICI ». Le decompile dit l'inverse.
`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute`, lu en entier :

    <entities+0x60 CurrentAbility>    = Nullable(this.Id)     # AVANT l'execution du behaviour
    <execution du behaviour>
    <entities+0x98 TriggeringAbility> = Nullable(this.Id)     # APRES, juste avant On(0xd)

`TriggeringAbilityIs` lit `<DSLSelectors+0x90>` -> `+0x98`. Pendant le behaviour de 1557, ce champ
porte donc encore la valeur ENTRANTE, et toute la chaine la PRESERVE :
`IdunBattle.Entities.Behaviours.TriggerAbilityBehaviour$$Execute` reconstruit son `AbilityEntities`
par `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor(<copie de l'entrant>, null)` puis n'ecrase
QUE `actor`/`caster`/`target`/`unitFeetTiles` ; `TriggerTriggeredAbilityOperation$$TriggerAbility` et
`BaseTriggeredAbility$$ExecuteBy` ne font que RECOPIER les 0x148 octets. Or 1557 est lui-meme porte
par `On(0x29)`, dont le canal est nul (ci-dessus) -> `TriggeringAbilityIs(1557)` est FAUX **aussi**
sous `Custom`. Le poser aurait RESTREINT le pool aux seuls `necroSmnWarrior` la ou le natif ne
restreint rien : une divergence par EXCES DE ZELE, invisible en test.

## 6. QUIRK PORTE -- l'arbre-cible est RE-EVALUE par chaque feuille

Le natif passe le MEME objet `GetTargetFriend()` aux QUATRE feuilles du `then` et au `If`, **sans
`Cache(...)`** -- alors qu'`ExemplarOfHate`, lui, enveloppe son selecteur d'attaquant dans un
`Cache(..., 1)` explicite. Le selecteur est donc RE-RESOLU apres chaque feuille, contre l'etat MUTE :
si l'allie elu tue sa seule cible pendant `PerformAIAttackFromCurrentPosition`, il sort du pool
(`AmountIsGreaterThanZero(ValidNormalAttackTargets)` devient faux) et les DEUX feuilles suivantes
(`ResetTemporaryAttackOverrideEffect`, `AddToPersistentDataList`) ne le retrouvent plus : l'override
d'Attaque LUI RESTE et il n'entre PAS dans la liste persistante. Le port MIRRORE ce comportement
(meme objet d'arbre, aucun cache) au lieu de le « corriger » -- un cache ajoute ici serait une
divergence silencieuse.

## 7. RESIDUS NOMMES

  * `EffectType.MyWillBeDoneOverlord_ExtraDamage` (1581) est POSE (feuille `AddDynamicStatModifier
    EffectToOwner`) mais AUCUNE classe d'effet ne le porte cote port -> effet PRESENT sans stat-mod
    (degradation fidele §17.4). Sa magnitude native vient de
    `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` (`ConfigVar` sur la config de
    l'ability) ; la variable `extraDmg` du gameconfig `MyWillBeDoneOverlord` en est la source
    evidente, mais elle n'est lue par AUCUNE des deux fonctions ci-dessus -> non porte plutot
    qu'invente.
  * `EffectType.MyWillBeDoneOverlord_FriendlyAttackedMarker` (1582) existe dans l'enum et
    n'apparait dans AUCUNE des deux fonctions -- il n'est ni pose ni lu par le port.
  * La `dataKey` native est un CHAMP STATIQUE de la classe (`DSLFormulas$$Get(<DAT statique>)`),
    illisible offline : le port emploie la constante `"MyWillBeDoneOverlord"`, exactement la
    convention de `LET_THE_GALAXY_BURN_PERSISTENT_KEY`. La cle n'est jamais comparee a une valeur
    native -> aucun observable n'en depend.
  * `GetPersistentDataListAsEntities` n'est pas porte en SELECTEUR (cf.
    `runner/abilities/behaviours/persistent_data.py`) : le gate du trigger de PURGE est collapse en
    « la liste est non vide ».
  * `unique = 1` d'`AdjacentFriends` : sans effet observable (une unite = une position) ; le port
    ancre sur `Caster()` la ou le natif ancre sur `CasterTiles@+0x58` (l'EMPREINTE du caster) --
    identique pour toute unite 1-hex, ce qu'est `necroOverlord`.
  * `selectionType = 3` (`OnlyAliveAndTargetable`) : le port n'honore que le volet ALIVE.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const, TargetsSelector
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.formulas import (Count, EntityId, StatAmount,
                                    percentage_of_attack_capped_at_max)
from .....entities.selectors.accessors import Subject
from .....entities.selectors.geometry import Otherwise
from .....entities.selectors.units import (
    AdjacentFriends, Filter, First, SortByFormula, Tiles, ValidNormalAttackTargets
)
from .....entities.selectors.tiles import Caster
from .....entities.stats import StatPart, StatType
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import (AmountIsGreaterThanZero, HasFaction, HasTrait,
                                    IsInPersistentDataList, Not, TriggerAnd)
from ....components import OwnerComponent, StatsComponent, persistent_data_list
from ....state import State
from ..base import TriggeredAbility, TriggerEvent
from .....entities.unit_faction import UnitFaction   # #270-r1-r1-r3
from .....dsl.base import AbilityTrigger
from .....dsl.effects import OperationResult
from .....entities.behaviours import Seq
from .....entities.effects.magnitude import ability_var
from ....abilities.base import convert_rounds_to_turns
from ....abilities.behaviours.effects import AddDynamicStatModifierEffect, RemoveEffect
from ....abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
from ....abilities.behaviours.persistent_data import AddToPersistentDataList
from ....abilities.behaviours.stats import AddStatOverrideEffect
from ....abilities.behaviours.summon import PerformAIAttack
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.persistent_data import ClearAllPersistentData

ABILITY_ID = "MyWillBeDoneOverlord"
# `AbilityOrEffect(this.Id)` = `BaseTriggeredAbility+0x10` (`get_Count` mislabel de ghidra =
# `mov eax, [rcx+0x10] ; ret`, corps DEDUPLIQUE) -> le `TriggeredAbilityType` de CETTE ability.
MY_WILL_BE_DONE_OVERLORD = int(TriggeredAbilityType.MyWillBeDoneOverlord)      # 0x614 = 1556
# Cle composite du sac persistant : `(AbilityOrEffect, dataKey)`. La dataKey native est un champ
# STATIQUE illisible offline (cf. residus) -> constante, meme convention que LetTheGalaxyBurn.
PERSISTENT_DATA_KEY = (MY_WILL_BE_DONE_OVERLORD, ABILITY_ID)

TEMPORARY_STAT_OVERRIDE = int(EffectType.TemporaryStatOverride)                # 0x510 = 1296
EXTRA_DAMAGE_EFFECT = int(EffectType.MyWillBeDoneOverlord_ExtraDamage)         # 0x62d = 1581
EXTRA_DAMAGE_EFFECT_NAME = "MyWillBeDoneOverlord_ExtraDamage"

MECHANICAL = int(UnitTrait.Mechanical)                                         # 0x05
HERO = int(UnitTrait.Hero)                                                     # 0x10
NECRONS = UnitFaction.Necrons                                                                    # `UnitFaction.Necrons`

MAX_DMG_KEY = "maxDmg"        # `AbilityVariableType` 0x0d
DMG_PCT_KEY = "dmgPct"        # `AbilityVariableType` 0x4a

_ON_TURN_START_EFFECT_ACTIVATION = int(EventTriggerType.TurnStart_EffectActivation)   # 0x12 = 18
_ON_UNIT_FINISHED_TURN_NORMALLY = int(EventTriggerType.UnitFinishedTurnNormally)      # 0x29 = 41

# `Sum(TurnsFromRounds(1), <DSLFormulas+0x20 = Direct(1)>)` : le `+1` est la CONSTANTE PARTAGEE que
# `IdunBattleLogic.Entities.DSLFormulas$$.ctor` met en cache (`+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
# `+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`).
EXTRA_DAMAGE_EXTRA_TURNS = 1


def my_will_be_done_target_friend() -> TargetsSelector:
    """`...MyWillBeDoneOverlordAbility$$GetTargetFriend` -- MIRROR 1:1 (cf. section 3 de l'en-tete).

    `Subject()` = le slot `DSLSelectors+0x68` (`ActiveTarget`, == `DSLFactory+0x180`), c'est-a-dire
    l'ELEMENT COURANT que le `Filter` lie : cote port c'est `ctx.subject`, pose par `Filter.select`.

    Le terme `!TriggeringAbilityIs(1557) | IsUnitWithVisualId(...)` est OMIS -- tautologique sur le
    vecteur porte, demonstration en section 5. Les quatre `Filter` de groupe reprennent le MEME noeud
    `pool`, comme le natif reprend le meme `pvVar4` : l'arbre est donc evalue quatre fois, exactement
    comme lui."""
    it = Subject()
    base = TriggerAnd(
        TriggerAnd(
            HasTrait(it, MECHANICAL),
            # `ValidNormalAttackTargets(it, Tiles(it), range=0, <regles par defaut>)` : « ce candidat
            # a au moins une cible legale a l'attaque NORMALE depuis sa tuile ». Les trois overrides
            # natifs (range / ignoreRule / additionalRule) sont nuls ici comme aux deux autres
            # call-sites du noeud -> non modelises.
            # `Count(...)` = la conversion selecteur -> CARDINAL que le noeud natif
            # `AmountIsGreaterAbilityTrigger(selector, Direct(0))` fait en interne (meme forme que
            # `AmountIsGreaterThanZero(Count(hexes))` de `LordOfTempests_ExtraDamageEffect`).
            AmountIsGreaterThanZero(Count(ValidNormalAttackTargets(it, Tiles(it))))),
        # `NOT IsInPersistentDataList(...)` : « ce candidat n'a pas DEJA agi depuis la derniere purge ».
        Not(IsInPersistentDataList(MY_WILL_BE_DONE_OVERLORD, Caster(), ABILITY_ID, EntityId(it))))
    # `AdjacentFriends(CasterTiles@+0x58, unique=1, selType=3)` = `Friends(ref, Units(AdjacentTiles(
    # ref)) - ref, 3)` : le referent d'equipe EST le centre (l'Owner, == le Caster pour un triggered).
    pool = Filter(AdjacentFriends(Caster()), base)
    necron = HasFaction(it, NECRONS)
    hero = HasTrait(it, HERO)
    group_a = Filter(pool, TriggerAnd(necron, hero))
    group_b = Filter(pool, TriggerAnd(Not(necron), hero))
    group_c = Filter(pool, TriggerAnd(necron, Not(hero)))
    group_d = Filter(pool, TriggerAnd(Not(necron), Not(hero)))
    chain = Otherwise(Otherwise(Otherwise(group_a, group_b), group_c), group_d)
    # `ascending = 0` LU au desassemblage (`xor r9d, r9d` avant le `call SortByFormula`) -> tri
    # DESCENDANT : l'allie de plus grosse ATTAQUE COURANTE du groupe elu.
    return First(SortByFormula(chain, StatAmount(it, int(StatType.ATTACK),
                                                 int(StatPart.CURRENT)), ascending=False))


def my_will_be_done_attack_tree(target: TargetsSelector, cap: int, pct: int, turns: int):
    """La branche THEN de `...$$CreateBehaviour` -- MIRROR 1:1 du `op_BitwiseAnd` des QUATRE feuilles,
    encapsulee dans le `If(target, then, else)` natif.

    ⚠ `target` est passe TEL QUEL aux quatre feuilles ET a la condition du `If` : c'est le MEME objet
    d'arbre, SANS `Cache` -- le natif le re-resout a chaque etage (section 6 de l'en-tete)."""

    amount = percentage_of_attack_capped_at_max(target, Const(int(cap)), Const(int(pct)),
                                                stat_part=int(StatPart.CURRENT))
    override = AddStatOverrideEffect(target, TEMPORARY_STAT_OVERRIDE, int(StatType.ATTACK), amount,
                                     name="TemporaryStatOverride")
    # `PerformAIAttackFromCurrentPosition(unit, 0, 0, 0)` -> `PerformAIAbilityUnitBehaviour(unit,
    # getAbilityType, null, overrideMovement = <DSLFormulas+0x18 = Direct(0)>, ...)` : l'acteur
    # attaque DEPUIS SA POSITION, sans approche (`allow_move_action=False`, `move_amount=0` =
    # les defauts de la feuille portee, qui sont ceux de CE noeud natif).
    free_attack = PerformAIAttack(target)
    clear = RemoveEffect(TEMPORARY_STAT_OVERRIDE, target)
    remember = AddToPersistentDataList(MY_WILL_BE_DONE_OVERLORD, Caster(), ABILITY_ID,
                                       EntityId(target))
    # `op_BitwiseAnd(op_BitwiseAnd(op_BitwiseAnd(b1, b2), b3), b4)` -- l'imbrication GAUCHE du
    # decompile, reproduite telle quelle (l'ordre d'execution est le meme, la FORME aussi).
    then = Seq(Seq(Seq(override, free_attack), clear), remember)
    # `AddDynamicStatModifierEffectToOwner(0x62d, statType=0 Attack, turns, isHidden=0)` = le MEME
    # behaviour avec `Owner@0x30` dans les DEUX slots (source ET cible).
    els = AddDynamicStatModifierEffect(Caster(), Caster(), EXTRA_DAMAGE_EFFECT,
                                       int(StatType.ATTACK), name=EXTRA_DAMAGE_EFFECT_NAME,
                                       duration_turns=int(turns))
    return _IfTargets(target, then, els)


class _IfTargets:
    """`IdunBattleLogic.Entities.DSLBehaviors$$If(condition = <SELECTEUR>, then, else)` : la condition
    du `If` natif de cette ability est un SELECTEUR de cibles (l'arbre `GetTargetFriend`), pas un
    predicat -- `IfBehaviour$$Execute` prend la branche THEN quand le selecteur rend un set NON VIDE.
    Le noeud `If` du port (`entities/behaviours.py`) prend, lui, un `AbilityTrigger` ; on exprime donc
    ici la forme SELECTEUR sans changer le noeud partage."""
    __slots__ = ("condition", "then", "otherwise")

    def __init__(self, condition: TargetsSelector, then, otherwise=None):
        self.condition, self.then, self.otherwise = condition, then, otherwise

    def execute(self, entities, ectx):
        chosen = self.condition.evaluate(entities)
        branch = self.then if chosen else self.otherwise
        if branch is None:
            return OperationResult.ok()
        return branch.execute(entities, ectx)


def _ability_vars(state: State, owner_id: int) -> tuple:
    """`GetVariableForLevel(config, 0x0d = maxDmg, abilityState, 0)` et `(config, 0x4a = dmgPct, ...)`.

    PASSIF -> `passive_ability_level` (meme lecture que `RelentlessMarch`/`FabricatorClawArray`).
    `variablesAffectedByRarityBonus` du gameconfig `MyWillBeDoneOverlord` = `["maxDmg", "extraDmg"]`
    -> le multiplicateur de rarete s'applique a `maxDmg` et PAS a `dmgPct` ; `ability_var` gate
    l'application sur cette liste, on ne la re-implemente pas ici. (0, 0) si le contexte manque ->
    l'override vaut alors 0 et la feuille est inerte."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return (0, 0)
    lvl = getattr(ctx, "passive_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    cap = int(ability_var(ABILITY_ID, MAX_DMG_KEY, lvl, multiplier_pct=mult) or 0)
    pct = int(ability_var(ABILITY_ID, DMG_PCT_KEY, lvl, multiplier_pct=mult) or 0)
    return (cap, pct)


def _used_ids(state: State, owner_id: int) -> list:
    """Collapse imperatif de `AmountIsGreaterThanZero(GetPersistentDataListAsEntities(...))` : les ids
    deja ranges dans la liste persistante du porteur (cf. le RESIDU NOMME sur le selecteur)."""
    return persistent_data_list(state.get_entity(owner_id), PERSISTENT_DATA_KEY)


def _my_will_be_done_custom(state: State, unit_id: int, entities, ectx):
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[MyWillBeDoneOverlord]` (#1011-r1) -- le bout de chaine
    du `TriggerAbility(Owner@+0x30, 0x614, ..., 3, false)` de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhasalSubjugator_TriggerPassiveAbility$$CreateBehaviour`.

    `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` appelle
    `ITriggeredAbility.ExecuteBy(ability, &abilityState, entities, 0x20)` -- le
    `0x20 = EventTriggerType.Custom` est EN DUR dans l'Operation. Le `CreateBehaviour` de cette
    ability se ventile sur son argument `triggerType` : `0x12` -> la PURGE, **tout le reste** -> le
    tour d'attaque offert. `Custom != 0x12`, donc c'est la branche `else` qui joue, la MEME que celle
    du vecteur `On(0x29)`. Patron `AdaptiveStrategy` -> `RelentlessMarch`
    (`runner/abilities/necrons.py::_relentless_march_custom`).

    `unit_id` = l'unite DECLENCHEE (ici l'Overlord lui-meme, seule cible du `TriggerAbility`) : c'est
    elle qui devient l'OWNER, exactement comme `ExecuteBy` prend l'`abilityState` de l'entite iteree.
    On re-materialise donc `entities_from_state(state, unit_id, None)` plutot que de reutiliser
    l'`entities` du cast -- le natif reconstruit lui aussi son `AbilityEntities` depuis les quatre
    selecteurs du `TriggerAbilityBehaviour`, tous NULS au call-site.

    ⚠ Le terme `!TriggeringAbilityIs(1557) | IsUnitWithVisualId(...)` de `GetTargetFriend` reste OMIS
    sous ce vecteur, et c'est LU -- cf. la section 5 de l'en-tete."""
    cap, pct = _ability_vars(state, int(unit_id))
    turns = int(convert_rounds_to_turns(state, 1)) + EXTRA_DAMAGE_EXTRA_TURNS
    ents = entities_from_state(state, int(unit_id), None)
    my_will_be_done_attack_tree(my_will_be_done_target_friend(), cap, pct, turns).execute(ents, ectx)
    return {"passive": ABILITY_ID, "owner": int(unit_id), "cap": int(cap), "pct": int(pct),
            "trigger_type": int(EventTriggerType.Custom)}


TRIGGERED_ABILITY_BEHAVIOURS[MY_WILL_BE_DONE_OVERLORD] = _my_will_be_done_custom


class MyWillBeDoneOverlordAttackAbility(TriggeredAbility):
    """Branche `On(0x29 = UnitFinishedTurnNormally) & get_OwnerIsActor` de
    `...MyWillBeDoneOverlordAbility$$CreateTrigger` : quand `necroOverlord` CLOT son activation (et pas
    par une terminaison forcee), un allie adjacent eligible attaque immediatement depuis sa position,
    avec son Attaque OVERRIDEE a `min(maxDmg[lvl], round(sonAttaque x dmgPct%))` ; l'allie est ensuite
    memorise dans la liste persistante pour ne pas etre rejoue. Aucun allie eligible -> l'Overlord se
    buffe lui-meme (effet 1581). Cf. l'en-tete du module."""
    event_id = _ON_UNIT_FINISHED_TURN_NORMALLY
    TRIGGERED_ABILITY_ID = MY_WILL_BE_DONE_OVERLORD

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`get_OwnerIsActor` = `AreEqual(Owner@DSLSelectors+0x30, Actor@DSLSelectors+0x40)` : l'unite
        qui vient de finir son tour EST le porteur. Le volet `On(0x29 = UnitFinishedTurnNormally)` + « owner vivant » est deja
        porte par le dispatch."""
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        cap, pct = _ability_vars(state, self.owner_id)
        # `turns = Sum(TurnsFromRounds(1), Direct(1))` -- resolu AVANT l'arbre (le natif le resout
        # aussi avant de batir la feuille), via le MEME mirror de `ConvertRoundsToTurns` que
        # `_resolve_duration`.
        turns = int(convert_rounds_to_turns(state, 1)) + EXTRA_DAMAGE_EXTRA_TURNS
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        target = my_will_be_done_target_friend()
        # Le MEME objet d'arbre part dans les quatre feuilles ET dans la condition du `If` (section 6).
        my_will_be_done_attack_tree(target, cap, pct, turns).execute(entities, ectx)
        attacks = [p for (n, p) in ectx.emitted if n == "PerformAIAttack"]
        added = [p for (n, p) in ectx.emitted if n == "AddToPersistentDataList"]
        buffs = [p for (n, p) in ectx.emitted if n == "AddDynamicStatModifierEffect"]
        acted = [a for p in attacks for a in (p.get("attacks") or [])]
        if not acted and not buffs:
            return None
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "cap": int(cap), "pct": int(pct),
                "friend": (acted[0].get("child") if acted else None),
                "target": (acted[0].get("target") if acted else None),
                "attacks": acted,
                "remembered": [u for p in added for u in (p.get("added") or [])],
                "self_buff": bool(buffs), "dsl": True}


class MyWillBeDoneOverlordClearAbility(TriggeredAbility):
    """Branche `On(0x12 = TurnStart_EffectActivation) &
    AmountIsGreaterThanZero(GetPersistentDataListAsEntities(...))` de
    `...MyWillBeDoneOverlordAbility$$CreateTrigger` -> `ClearAllPersistentData(AbilityOrEffect(this.Id),
    Owner@0x30)` : la liste des allies deja rejoues est PURGEE au premier turn-start suivant.

    ⚠ Ce volet n'a AUCUN gate de joueur (pas de `OwnerIsActor` / `IsTurnOf`) : il fire au turn-start de
    N'IMPORTE QUEL joueur -- donc des le tour ADVERSE qui suit. C'est LU, pas deduit : la conjonction
    du decompile ne porte que le gate de liste non vide."""
    event_id = _ON_TURN_START_EFFECT_ACTIVATION
    TRIGGERED_ABILITY_ID = MY_WILL_BE_DONE_OVERLORD

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return len(_used_ids(state, self.owner_id)) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        before = list(_used_ids(state, self.owner_id))
        entities = entities_from_state(state, self.owner_id, None)
        ectx = ExecutionContext(state=state, rng=state.rng)
        ClearAllPersistentData(MY_WILL_BE_DONE_OVERLORD, Caster()).execute(entities, ectx)
        return {"passive": ABILITY_ID, "owner": int(self.owner_id), "cleared": before}
