"""#1015-r1 -- `InstinctiveBehaviour_UpdateTargetAbility`, le volet CIBLAGE du trait
`InstinctiveBehaviour` (`UnitTrait` 0x7e5 = 2021, **23 porteurs** : 18 npc + 5 summons Tyranides).

i2 (`Traits/InstinctiveBehaviour_Description`) : « If there are targets in range, this unit does
not move and attacks the closest target. » Le « does not move » vit dans l'effet 1235
(`entities/effects/loki/instinctive_behaviour.py`) ; le « attacks the closest target », ici.

L'ability est `TriggeredAbilityType.InstinctiveBehaviour` = 0x413 = **1043**, DERIVEE du trait par
`IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` (dict `Trait +0x0`). Elle ne fait
qu'UNE chose : maintenir le `ForcedAttackTargetsComponent` du porteur EGAL a
`GetUpdatedForcedTarget()`. C'est un mainteneur de cache, pas un effet ponctuel -- d'ou ses DIX
vecteurs et son gate terminal `HasTargetChanged`.

================================================================================================
1. `$$GetUpdatedForcedTarget` -- le SELECTEUR, mirror 1:1
================================================================================================
    tiles = DSLSelectors$$Tiles( Owner@<DSLSelectors+0x30> )
    rng   = DSLFormulas$$NormalAttackRange( unit = Owner@+0x30, unitTile = tiles )
    mv    = DSLFormulas$$StatAmount( unit = Owner@+0x30, statType = 0x1 = Movement,
                                     statPart = 0 = Current, modificationEntity = null,
                                     selectionType = 0 )
    maxd  = DSLFormulas$$Sum( rng, mv )
    enemies = DSLSelectors$$NearestAttackableEnemies( unit = Owner@+0x30,
                                                      distanceType = 0 = Simple,
                                                      maxDistance = maxd )
    gate  =   DSLTriggers$$AmountIsEqualOrGreater( DSLFormulas$$Count(DSLSelectors$$Tiles(Owner)),
                                                  <DSLFormulas+0x20> = Direct(1) )
            op_BitwiseAnd op_LogicalNot(
                DSLTriggers$$IsEffectTarget( Owner@+0x30, 0x41c = EffectType.Synapse_Effect ) )
    return DSLSelectors$$If( gate, enemies, DSLSelectors$$None() )

En clair : **l'ennemi le plus proche a portee (portee d'attaque normale + mouvement)**, sauf si
l'unite est dans une bulle SYNAPSE -- litteralement le « Friendly units within 2 hexes ignore the
effects of Instinctive Behaviour » de `Traits/Synapse_Description`. Le premier conjoint
(`Count(Tiles(Owner)) >= 1`) est le « l'unite est SUR le plateau » ; il tombe pour une unite en
deep-strike / hors plateau.

⚠ `StatType 0x1` = **Movement** (`enums.tsv`), pas `Range` : la portee du selecteur est donc
`portee d'arme + mouvement`, c.-a-d. « ce que l'unite peut atteindre CE TOUR ». C'est ce qui rend
les deux volets coherents -- l'ability DESIGNE une cible qu'il faudra peut-etre approcher, et
l'effet 1235 ne BLOQUE le mouvement que si cette cible est DEJA a portee (`IsInAttackOrAbilityRange`).

================================================================================================
2. `$$CreateTrigger` -- QUAND, et le gate qui evite le travail inutile
================================================================================================
    return IsValidTrigger()
           op_BitwiseAnd op_LogicalNot( DSLTriggers$$IsEffectTarget(
                              Owner@+0x30, 0x1b = 27 EffectType.Taunted_OnlySpecificTargets ) )
           op_BitwiseAnd op_LogicalNot( DSLTriggers$$AreEquivalent(
                              DSLSelectors$$ForcedAttackTargets(Owner@+0x30),
                              GetUpdatedForcedTarget() ) )

Les deux derniers conjoints ont leur methode NOMMEE dans la classe (`$$IsNotTaunted`,
`$$HasTargetChanged`), corps identiques -- on les cite sous leur nom.

⚠ **LE TAUNT GAGNE.** Une unite TAUNTEE (cible de l'effet 27) ne voit PAS sa liste de cibles
forcees reecrite par son instinct : le trigger est mort. C'est ce qui fait coexister les voies 1
(`TauntedEffect$$ApplyInternal`, REMPLACE la liste) et 3 (`AddForcedAttackTargetBehaviour`,
INCREMENTE) sans qu'elles se battent -- la docstring de `ForcedAttackTargetsComponent` notait leur
non-coexistence comme un fait du PORT ; c'est en realite le natif qui l'organise.

`$$IsValidTrigger`, op par op (`C` = le predicat commun) :

    C =   DSLTriggers$$AreEnemies( Owner@<DSLSelectors+0x30>, Other@<DSLSelectors+0x60>,
                                   selectionType = 0 = ByCurrentTeam )
        op_BitwiseOr DSLTriggers$$IsOwnerOfEffect( Other@+0x60, 0x41c = Synapse_Effect,
                                                   onlyActive = false )

      On(0x12 = TurnStart_EffectActivation)
    | ( On(0x32 = UnitAdded)            op_BitwiseAnd C )
    | OnDeath( triggerOnOverkill = true, triggerOnSteppable = false )
    | ( On(0x2e = UnitResurrected)      op_BitwiseAnd C )
    | ( On(0x2d = UnitRevived)          op_BitwiseAnd C )
    | ( On(0x34 = UnitFled)             op_BitwiseAnd C )
    | ( On(0x1d = UnitPositionChanged_2) op_BitwiseAnd C )
    | ( On(0x1d = UnitPositionChanged_2) op_BitwiseAnd get_OwnerIsTarget )
    | ( On(0x3b = UnitBecameTargetable) op_BitwiseAnd C )
    | ( On(0x2b = UnitHealed)           op_BitwiseAnd get_OwnerIsTarget )

Tous les `On` portent `ownerNeedsToBeAlive = true`. Les ordinaux sont ceux du build `rnca9r7q6c`
(`engine/dsl/event_trigger_type.py` ; le retrait d'`ArmorChanged` a decale les 36 derniers).

================================================================================================
3. `$$CreateBehaviour` -- le NET, mirror 1:1
================================================================================================
    current = DSLSelectors$$ForcedAttackTargets( Owner@<DSLSelectors+0x30> )
    updated = GetUpdatedForcedTarget()
    toRemove = current op_Subtraction updated
    toAdd    = updated op_Subtraction current
    refresh  = DSLBehaviors$$RefreshEffects( RefreshEffectTrigger.UnitStateChanged = 3 )
    return   ( DSLBehaviors$$RemoveForcedAttackTarget( Owner@+0x30, toRemove )
               op_BitwiseAnd DSLBehaviors$$AddForcedAttackTarget( Owner@+0x30, toAdd ) )
             op_BitwiseAnd refresh

C'est un DIFF, pas un remplacement : seul le DELTA est ecrit, et le `RefreshEffects` qui suit
re-evalue les `CreateActiveCondition` -- au premier chef celle de 1235, qui vient peut-etre de
basculer.

================================================================================================
RESIDUS NOMMES
================================================================================================
* **`On(0x2b = 43 UnitHealed)` n'a AUCUN emetteur porte.** `runner/operations/heal.py` le nomme
  explicitement dans ses non-portes (`processor.<slot 0x51>(caster, caster, healed, 0x2b,
  abilityOrEffect)`), et #1037 n'a cable que son voisin `0x2c UnitHealedWithRemoveEffects`. Le bras
  est donc INERTE cote port. Cout MESURE nul sur cette ability : `NearestAttackableEnemies` ne lit
  ni PV ni bouclier -- son filtre est `Enemies / !Steppable / Unobscured / distance`, qu'un soin ne
  change pas. Le bras n'existe pour le natif que parce qu'un soin peut RANIMER (et la voie
  RANIMATION, elle, EST couverte par `On(0x2d)` / `On(0x2e)`, tous deux emis).
* **`Nearest` en `distanceType = Simple`** : le port ne fait donc AUCUN pathfinding ici, exactement
  comme le natif (le litteral `0` est LU au call-site).
* Le `$$GetCurrentForcedTarget` natif (= `ForcedAttackTargets(Owner)` nu) n'a pas de call-site dans
  cette classe -- il est cite pour memoire, pas porte.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import op_and
from .....entities.distance_type import DistanceType
from .....entities.effect_type import EffectType
from .....entities.formulas import Count, NormalAttackRange, StatAmount, Sum
from .....entities.selectors.accessors import Owner
from .....entities.selectors.geometry import Nothing, SelectIf
from .....entities.selectors.units import (ForcedAttackTargets, Sub, Tiles,
                                           nearest_attackable_enemies)
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsEqualOrGreater, IsEffectTarget, Not, TriggerAnd
from .....entities.unit_team_selection_type import UnitTeamSelectionType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.forced_targets import (AddForcedAttackTarget, RefreshEffects,
                                                     RemoveForcedAttackTarget)
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ...refresh_effects import RefreshEffectTrigger
from ..base import TriggeredAbility, TriggerEvent
from .... import components as _RC   # FORME B (liaison de MODULE). Arete GRATUITE (#485) :
#     `import engine.runner.components` en process frais ne charge pas ce module.

ABILITY_ID = "InstinctiveBehaviour"
INSTINCTIVE_BEHAVIOUR = int(TriggeredAbilityType.InstinctiveBehaviour)          # 0x413 = 1043
SYNAPSE_EFFECT = int(EffectType.Synapse_Effect)                                # 0x41c = 1052
TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)                          # 0x1b  = 27

#: `<DSLFormulas+0x20>` = `Direct(1)` (`DSLFormulas$$.ctor` : `+0x18 Zero, +0x20 One, +0x28 Two`).
_ONE = 1
#: `selectionType` d'`AreEnemies` (litteral `0` du site). Type DECLARE lu dans `frida/methods.tsv`.
_TEAM_SELECTION = int(UnitTeamSelectionType.ByCurrentTeam)                     # 0

_ON_TURN_START_EFFECTS = int(EventTriggerType.TurnStart_EffectActivation)      # 0x12 = 18
_ON_UNIT_ADDED = int(EventTriggerType.UnitAdded)                               # 0x32 = 50
_ON_PRE_UNIT_DEATH = int(EventTriggerType.PreUnitDeath)                        # `OnDeath(...)`
_ON_UNIT_RESURRECTED = int(EventTriggerType.UnitResurrected)                   # 0x2e = 46
_ON_UNIT_REVIVED = int(EventTriggerType.UnitRevived)                           # 0x2d = 45
_ON_UNIT_FLED = int(EventTriggerType.UnitFled)                                 # 0x34 = 52
_ON_POSITION_CHANGED = int(EventTriggerType.UnitPositionChanged_2)             # 0x1d = 29
_ON_BECAME_TARGETABLE = int(EventTriggerType.UnitBecameTargetable)             # 0x3b = 59
_ON_UNIT_HEALED = int(EventTriggerType.UnitHealed)                             # 0x2b = 43 (INERTE)

#: Les vecteurs ou le predicat commun `C` s'applique (cf. `$$IsValidTrigger` dans l'en-tete).
_VECTORS_WITH_C = (_ON_UNIT_ADDED, _ON_UNIT_RESURRECTED, _ON_UNIT_REVIVED, _ON_UNIT_FLED,
                   _ON_POSITION_CHANGED, _ON_BECAME_TARGETABLE)
#: Les vecteurs ou c'est `get_OwnerIsTarget` qui garde (et non `C`).
_VECTORS_WITH_OWNER_IS_TARGET = (_ON_POSITION_CHANGED, _ON_UNIT_HEALED)
#: Les vecteurs INCONDITIONNELS.
_VECTORS_BARE = (_ON_TURN_START_EFFECTS, _ON_PRE_UNIT_DEATH)


def updated_forced_target():
    """`InstinctiveBehaviour_UpdateTargetAbility$$GetUpdatedForcedTarget` -- ARBRE 1:1 (cf. §1 de
    l'en-tete).

    `unknown_is_target=True` sur l'`IsEffectTarget` : le noeud est sous un `NOT`, donc un canal
    muet (`None`) doit valoir « DANS la bulle Synapse » -> aucune cible forcee -> l'unite reste
    libre. La direction PERMISSIVE ; l'autre inventerait un verrou (cf. la docstring du noeud)."""
    tiles = Tiles(Owner())                                # `Tiles(Owner@+0x30)`
    rng = NormalAttackRange(Owner(), tiles)
    mv = StatAmount(Owner(), int(StatType.MOVEMENT))      # statPart 0 = Current, modEntity null
    enemies = nearest_attackable_enemies(Owner(), int(DistanceType.Simple), Sum(rng, mv))
    on_board = AmountIsEqualOrGreater(Count(Tiles(Owner())), Const(_ONE))
    in_synapse = IsEffectTarget(Owner(), SYNAPSE_EFFECT, unknown_is_target=True)
    return SelectIf(TriggerAnd(on_board, Not(in_synapse)), enemies, Nothing())


def update_forced_target_behaviour_tree():
    """`InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour` -- ARBRE 1:1 (cf. §3).

    `op_and` = `AbilityBehaviour$$op_BitwiseAnd` (la MEME classe `CombinedBehaviour` que
    `op_Addition`, cf. `entities/behaviours.py::Seq`). Les trois feuilles sont PURES -> aucun
    court-circuit, les trois s'executent."""
    current = ForcedAttackTargets(Owner())
    updated = updated_forced_target()
    to_remove = Sub(current, updated)                     # `current op_Subtraction updated`
    to_add = Sub(updated, ForcedAttackTargets(Owner()))   # `updated op_Subtraction current`
    net = op_and(RemoveForcedAttackTarget(Owner(), to_remove),
                 AddForcedAttackTarget(Owner(), to_add))
    return op_and(net, RefreshEffects(int(RefreshEffectTrigger.UnitStateChanged)))


class InstinctiveBehaviourUpdateTargetAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.InstinctiveBehaviour_UpdateTargetAbility` --
    maintient `ForcedAttackTargetsComponent(porteur)` = « l'ennemi le plus proche a portee
    d'attaque + mouvement », sauf sous SYNAPSE et sauf si le porteur est TAUNTE.

    FORME DU PORT (doctrine #149) : le `CreateTrigger` COLLAPSE imperativement dans `matches`
    (c'est une disjonction de vecteurs, plus deux gates), le `CreateBehaviour` est un ARBRE DSL.

    ⚠ `HasTargetChanged` EST DANS `matches`, et il y est LOAD-BEARING : sans lui, le behaviour
    tournerait a chaque vecteur, et son `RefreshEffects` avec -- le natif, lui, ne l'execute que
    quand le set change VRAIMENT (`op_LogicalNot(AreEquivalent(current, updated))`)."""
    __slots__ = ()

    event_id = _ON_TURN_START_EFFECTS
    event_ids = (_ON_TURN_START_EFFECTS, _ON_UNIT_ADDED, _ON_PRE_UNIT_DEATH,
                 _ON_UNIT_RESURRECTED, _ON_UNIT_REVIVED, _ON_UNIT_FLED,
                 _ON_POSITION_CHANGED, _ON_BECAME_TARGETABLE, _ON_UNIT_HEALED)
    TRIGGERED_ABILITY_ID = INSTINCTIVE_BEHAVIOUR

    # -- `$$IsValidTrigger` ---------------------------------------------------------------------

    def _common_predicate(self, state: State, ev: TriggerEvent) -> bool:
        """`C` = `AreEnemies(Owner@+0x30, Other@<DSLSelectors+0x60>, ByCurrentTeam)
        op_BitwiseOr IsOwnerOfEffect(Other@+0x60, 0x41c = Synapse_Effect, onlyActive: false)`.

        `Other@+0x60` est le slot **Target** de l'`AbilityEntities` ; sur les six vecteurs
        concernes, le port y pose l'unite du vecteur (`on_unit_added` : l'unite ajoutee ;
        `unit_position_changed` : celle qui a bouge ; etc.).

        `IsOwnerOfEffect(..., onlyActive: false)` = « l'entite POSSEDE une instance de ce type »
        (`EffectsState.has_effect`, filtre `consumed` seul), pas « elle en est la cible » -- c'est
        le pendant exact de la distinction que porte `entities/effect_targets.py`. Ce disjoint est
        ce qui fait re-evaluer l'instinct quand un EMETTEUR Synapse entre en jeu ou se deplace."""
        other = ev.target_id if ev.target_id is not None else ev.actor_id
        if other is None:
            return False
        o, t = state.get_entity(int(self.owner_id)), state.get_entity(int(other))
        if o is None or t is None:
            return False
        ooc, toc = o.get_component(OwnerComponent), t.get_component(OwnerComponent)
        if ooc is not None and toc is not None and ooc.team != toc.team:
            return True                                   # `AreEnemies(Owner, Other, 0)`
        eff = getattr(state, "effects", None)
        if eff is None:
            return False
        return bool(eff.has_effect(int(other), effect_type=SYNAPSE_EFFECT))

    def _is_valid_trigger(self, state: State, ev: TriggerEvent) -> bool:
        """La disjonction de `$$IsValidTrigger`, vecteur par vecteur (cf. l'en-tete). Un `On` que
        le port n'emet pas ne peut simplement jamais arriver ici -- il n'est pas ECARTE, il est
        INERTE, et c'est nomme dans les residus."""
        eid = int(ev.event_id)
        if eid in _VECTORS_BARE:
            return True                                   # `On(0x12)` et `OnDeath(...)`, nus
        owner_is_target = (ev.target_id is not None and int(ev.target_id) == int(self.owner_id))
        if eid in _VECTORS_WITH_OWNER_IS_TARGET and owner_is_target:
            return True                                   # `On(0x1d)|On(0x2b) & get_OwnerIsTarget`
        return eid in _VECTORS_WITH_C and self._common_predicate(state, ev)

    # -- `$$CreateTrigger` ----------------------------------------------------------------------

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(int(self.owner_id))
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:
            return False                                  # `ownerNeedsToBeAlive = true` (tous les On)
        if not self._is_valid_trigger(state, ev):
            return False
        # `$$IsNotTaunted` = `op_LogicalNot(IsEffectTarget(Owner@+0x30, 0x1b))`. Canal muet
        # (`None`) -> on NE conclut PAS au taunt : le port continuerait a maintenir la liste, ce
        # qu'il faisait deja avant cette tranche. `is_effect_target` n'a pas de geometrie portee
        # pour 27 -> ce gate est INERTE aujourd'hui, et c'est dit ici plutot que tu.
        if _RC.is_effect_target(state, int(self.owner_id), TAUNTED) is True:
            return False
        # `$$HasTargetChanged` = `op_LogicalNot(AreEquivalent(ForcedAttackTargets(Owner),
        # GetUpdatedForcedTarget()))` -- `DSLTriggers$$AreEquivalent` compare deux SELECTIONS ;
        # le port compare les ENSEMBLES d'ids (le natif compare des references d'entite).
        cur, upd = self._current_and_updated(state)
        return cur != upd

    def _current_and_updated(self, state: State) -> tuple:
        """`(ForcedAttackTargets(Owner), GetUpdatedForcedTarget())` en ENSEMBLES d'ids -- les deux
        operandes d'`AreEquivalent`, et les deux du `op_Subtraction` du behaviour."""
        ents = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                   owner_id=int(self.owner_id))
        cur = {int(u["id"]) for u in (ForcedAttackTargets(Owner()).select(ents) or [])
               if isinstance(u, dict) and u.get("id") is not None}
        upd = {int(u["id"]) for u in (updated_forced_target().select(ents) or [])
               if isinstance(u, dict) and u.get("id") is not None}
        return cur, upd

    # -- `$$CreateBehaviour` --------------------------------------------------------------------

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ents = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                   owner_id=int(self.owner_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        update_forced_target_behaviour_tree().execute(ents, ectx)
        added = [i for n, p in ectx.emitted if n == "AddForcedAttackTarget"
                 for i in (p.get("added") or ())]
        removed = [i for n, p in ectx.emitted if n == "RemoveForcedAttackTarget"
                   for i in (p.get("removed") or ())]
        if not added and not removed:
            return None
        return {"trait": ABILITY_ID, "owner": int(self.owner_id), "event": int(ev.event_id),
                "forced_added": added, "forced_removed": removed, "dsl": True}
