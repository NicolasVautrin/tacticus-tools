"""`Maugetar` (#1006) -- relique unique `R_Crit_Maugetar` d'`eldarMauganRa`, `TriggeredAbilityType`
0x5da = 1498. TROIS artefacts natifs pour UNE cle : deux `*Ability` (patron `DaemonfleshPlate`) plus
l'effet 1497, dont le RETRAIT est un trigger propre.

i2 : « During his turn, if Maugan Ra has not moved, he can move after attacking and his attacks that
contain a Crit deal an additional 1x 2622-3492 Direct Damage. When Overwatching, Crits deal this
additional hit if he has not moved in his last turn. »

================================================================================================
L'ENUM : 1498 EST UN `TriggeredAbilityType`, ET LA VOIE MENT
================================================================================================
`Maugetar` apparait dans les `activeAbilities` du npc `eldarBossMauganRaUltra` -- c'est l'une des
DEUX inversions de voie mesurees (#270-c). Le nom, lui, ne ment pas :
`IdunBattle.Entities.Enum.TriggeredAbilityType` porte `1498 = Maugetar`, et l'ordinal 1498 nomme
`ExemplarOfTheMontka` dans `EffectType`. Les trois classes natives vivent sous
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.*` et derivent de
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` (`frida/classes.tsv`) : aucune classe
`...Abilities.Active.Loki.Maugetar*` n'existe. Ce port n'entre donc PAS dans `ABILITY_CLASSES` et ne
pose ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE`.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Maugetar_AddEffectAbility$$CreateTrigger` :

    IdunBattleLogic.Entities.DSLTriggers$$On(0x12 = TurnStart_EffectActivation,
                                             ownerNeedsToBeAlive: true)
  & <DSLTriggers+0x28>                                     # `IsTurnOf(Owner)`

`...Maugetar_AddEffectAbility$$CreateBehaviour` :

    IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(
        0x5d9 = 1497 Maugetar_HasNotMoved,
        IdunBattle.Entities.Abilities.BaseTriggeredAbility$$get_AbilityStateReference,
        <DSLSelectors+0x30> = Owner,
        turns = null)                                      # -> effet PERMANENT

`...Maugetar_ResetMovementAbility$$CreateTrigger` :

    DSLTriggers$$On(0xe = UnitPostAbility, ownerNeedsToBeAlive: true)
  & IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster

⚠ Ce `CreateTrigger` est **INVISIBLE des tables** : son corps est fondu par l'ICF avec celui de
`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnance_RemoveCritChance$$CreateTrigger`.
Appartenance etablie slot a slot dans le bloc `methodPointers` du PE
(`probe_8889_methodptr_vtable.py --window 6 <VA du CreateBehaviour>`), dont le motif est
`[CreateTrigger, CreateBehaviour, <corps trivial>]` par classe -- verifie sur les quatre voisins
NOMMES du meme bloc (`MastersOfManoeuvre`, `MischiefMakers`, `ModifiedExoarmour`,
`Maugetar_AddEffect`). C'est exactement la forme de l'avertissement « l'ABSENCE d'une methode dans
les tables ne prouve RIEN ».

`...Maugetar_ResetMovementAbility$$CreateBehaviour` :

    DSLBehaviors$$If(
        DSLTriggers$$HasEffect(Owner, 0x5d9, onlyActive: false,
                               targetType: 6 = EffectTargetType.Both),
        IdunBattleLogic.Entities.DSLBehaviors$$ResetMovement(Owner),
        null)

`IdunBattle.Entities.Effects.Loki.Maugetar_HasNotMovedEffect$$CreateRemoveEffectTrigger` :

    DSLTriggers$$On(0x1f = PreUnitMove, ownerNeedsToBeAlive: true)
  & IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsActor

Le volet DEGAT de l'effet (`$$CreateAdditionalHits`) vit dans
`engine/entities/effects/loki/hits.py::MaugetarHasNotMovedEffect` -- canal #179, gate
`AttackDamageIsCritical`, bi-canal ROLL/DISPLAY.

================================================================================================
CE QUE LA MECANIQUE FAIT, ETAGE PAR ETAGE
================================================================================================
1. au debut du tour de SON joueur, le porteur (re)pose l'effet 1497 sur lui-meme -- PERMANENT ;
2. tant que 1497 est la, toute attaque du porteur qui CONTIENT un crit porte `nrOfHits` coup(s)
   additionnel(s) [minDmg, maxDmg] `DirectDamage` (`hits.py`) ;
3. des que le porteur AMORCE un deplacement (`On(PreUnitMove)`, emis AVANT l'ecriture de la
   position), 1497 est retire : plus de coup additionnel ;
4. a la CLOTURE de chaque ability du porteur (`On(UnitPostAbility)` -- emis par les DEUX voies :
   cast et attaque normale), si 1497 est encore la, le porteur REOUVRE son deplacement
   (`ResetMovement` retire `Moved`, `ArrivedAtFinalTile`, `TurnTerminated`, `TurnFinished`, mais
   PAS `ActiveAbilityUsed` -- il ne peut donc pas re-caster).

L'ordre (3) avant (4) est ce qui rend la mecanique non circulaire : bouger APRES avoir attaque
retire l'effet, donc la deuxieme attaque de la meme unite n'a plus le bonus.

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
* les trois `CreateTrigger` COLLAPSENT imperativement dans `matches` (patron `DawnBlade` /
  `DaemonfleshPlate`) ;
* les deux `CreateBehaviour` sont des ARBRES DSL dont les feuilles APPELLENT les Operations deja
  portees (`AddEffect` -> `AddEffectOperation`, `ResetMovement` -> `ResetMovementBehavior`,
  `RemoveEffect` -> `RemoveEffectOperation`) -- aucune n'est re-ecrite.

RESIDUS NOMMES
  * **`ownerNeedsToBeAlive = true`** des trois `On(...)` : le port n'inscrit de triggers que pour des
    entites vivantes sur ces vecteurs, donc le gate est structurellement satisfait ; il n'est pas
    re-teste.
  * **le tir d'OVERWATCH** : l'i2 promet le coup additionnel « when Overwatching ... if he has not
    moved in his last turn ». Aucun etage supplementaire cote natif -- c'est le MEME effet 1497 qui
    survit au tour adverse (il n'est retire que par un deplacement du PORTEUR) et le meme descripteur
    #179 que traverse l'attaque d'overwatch. Rien de specifique n'est donc porte ici, et c'est LU,
    pas suppose.
  * **la publication de stream** de `ResetMovementBehavior` (`Publish(<0xc>, e, {<0x70>: 0})`) : deja
    documentee comme non portee sur la feuille (`abilities/behaviours/movement.py`).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner
from .....entities.selectors.tiles import Caster
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import HasEffect
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from ....abilities.behaviours.movement import ResetMovement
from ....components import OwnerComponent
from ....state import State
from ..base import EffectTrigger, TriggeredAbility, TriggerEvent

ABILITY_ID = "Maugetar"
MAUGETAR_ABILITY = int(TriggeredAbilityType.Maugetar)                 # 0x5da = 1498
MAUGETAR_HAS_NOT_MOVED = int(EffectType.Maugetar_HasNotMoved)         # 0x5d9 = 1497

#: `onlyActive` = 3e argument du `HasEffect` natif, LU a `0` dans
#: `...Maugetar_ResetMovementAbility$$CreateBehaviour` (l'effet compte meme s'il est INACTIF).
_HAS_EFFECT_ONLY_ACTIVE = False


def maugetar_add_effect_tree() -> AddEffect:
    """`...Maugetar_AddEffectAbility$$CreateBehaviour` = `AddEffect(1497, AbilityStateReference,
    Owner@DSLSelectors+0x30, turns = null)`.

    `turns = null` -> `duration_rounds=None` : l'effet est PERMANENT, et c'est le `On(PreUnitMove)`
    de `MaugetarHasNotMovedRemoveOnMove` qui le retire -- jamais une expiration."""
    return AddEffect(MAUGETAR_HAS_NOT_MOVED, EffectType.Maugetar_HasNotMoved.name, Owner(),
                     duration_rounds=None)


def maugetar_reset_movement_tree() -> If:
    """`...Maugetar_ResetMovementAbility$$CreateBehaviour` = `If(HasEffect(Owner, 1497,
    onlyActive: false, targetType: 6 = Both), ResetMovement(Owner), null)` -- MIRROR 1:1.

    Le `HasEffect` reste un NOEUD (il n'est pas collapse dans `matches`) parce que c'est la
    STRUCTURE du `CreateBehaviour` natif : le gate vit dans l'arbre, pas dans le trigger."""
    return If(HasEffect(Owner(), MAUGETAR_HAS_NOT_MOVED, active_only=_HAS_EFFECT_ONLY_ACTIVE),
              ResetMovement(Owner()))


class MaugetarAddEffectAbility(TriggeredAbility):
    """`Maugetar_AddEffectAbility` -- au debut du tour de SON joueur, le porteur se pose l'effet
    1497 `Maugetar_HasNotMoved`.

    `On(0x12 = TurnStart_EffectActivation)` est un vecteur SANS acteur (`tile_tick_triggers` construit
    l'evenement avec `actor = target = -1`, mirror de `StartTurnOperation$$Execute` qui l'emet pour
    le TOUR, pas pour une unite) : le second conjoint `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` est
    donc le SEUL discriminant, et il se lit `OwnerComponent.player == State.current_player_id`
    (mirror `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`, meme egalite que le
    foyer `entities/effects/base.py::is_turn_of_owner`)."""
    event_id = EventTriggerType.TurnStart_EffectActivation            # 0x12 = 18
    TRIGGERED_ABILITY_ID = MAUGETAR_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `IsTurnOf(Owner)`. Tri-etat : proprietaire ou joueur courant NON MESURE -> FAUX, jamais
        # permissif (un effet pose au tour de l'adversaire donnerait le bonus hors de sa fenetre).
        ent = state.get_entity(int(self.owner_id))
        oc = ent.get_component(OwnerComponent) if ent is not None else None
        cur = getattr(state, "current_player_id", None)
        if oc is None or getattr(oc, "player", None) is None or cur is None:
            return False
        return int(oc.player) == int(cur)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        maugetar_add_effect_tree().execute(entities, ectx)
        placed = [p for (n, p) in ectx.emitted if n == "AddEffect"]
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "effect": MAUGETAR_HAS_NOT_MOVED, "adds": placed}


class MaugetarResetMovementAbility(TriggeredAbility):
    """`Maugetar_ResetMovementAbility` -- a la CLOTURE d'une ability du porteur, s'il n'a pas bouge
    (l'effet 1497 est encore la), il RECUPERE son deplacement.

    `On(0xe = UnitPostAbility)` est emis par les DEUX voies (`AbilityHandler` pour un cast,
    `after_hit_normal_attack` pour l'attaque normale) -- c'est ce qui realise le « he can move AFTER
    ATTACKING » de l'i2. `get_OwnerIsCaster` = le porteur est le CASTER de l'evenement."""
    event_id = EventTriggerType.UnitPostAbility                       # 0xe = 14
    TRIGGERED_ABILITY_ID = MAUGETAR_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` : `unit_post_ability_triggers` construit l'event avec
        # `actor = caster = caster_id`. Le gate `HasEffect` n'est PAS ici -- il est dans l'ARBRE
        # (`maugetar_reset_movement_tree`), comme le natif.
        return ev.actor_id == self.owner_id

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        maugetar_reset_movement_tree().execute(entities, ectx)
        resets = [p for (n, p) in ectx.emitted if n == "ResetMovement"]
        if not resets:
            return None            # branche `else` NULLE du `If` natif : rien a rapporter
        return {"relic": ABILITY_ID, "owner": int(self.owner_id), "resets": resets}


class MaugetarHasNotMovedRemoveOnMove(EffectTrigger):
    """`Maugetar_HasNotMovedEffect$$CreateRemoveEffectTrigger` = `On(0x1f = PreUnitMove,
    ownerNeedsToBeAlive: true) & get_OwnerIsActor` -> retrait de l'effet.

    `CreateRemoveEffectTrigger` est le canal natif dont le BEHAVIOUR est implicite : la base
    `IdunBattle.Entities.Effects.BaseEffect` en fabrique un `RemoveEffect(EffectSelf)`. D'ou la
    feuille `RemoveEffect(1497, Caster())` ici -- le porteur du marqueur EST le mover.

    ⚠ Le vecteur est PRE-move (`MoveUnitOperation$$EvaluatePreMoveTriggers` part AVANT l'ecriture de
    la position) : l'effet tombe des que le deplacement est AMORCE, pas une fois arrive."""
    effect_type = MAUGETAR_HAS_NOT_MOVED
    event_id = EventTriggerType.PreUnitMove                           # 0x1f = 31

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : `pre_move_triggers` pose `actor = target = mover_id`.
        return ev.actor_id == self.owner_id

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(MAUGETAR_HAS_NOT_MOVED, Caster()).execute(entities, ectx)
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "removed": MAUGETAR_HAS_NOT_MOVED, "on_event": int(ev.event_id)}
