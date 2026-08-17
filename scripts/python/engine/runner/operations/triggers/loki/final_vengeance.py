"""`FinalVengeance_UnitEffect` (effet 0x5ae = 1454) -- l'effet que la relique `RelicOfLostCadia`
(0x5b3 = 1459, Astra Militarum) pose sur les SUMMONS IMPERIAUX allies adjacents, et qui leur PRETE
le passif `FinalJustice` (0x400 = 1024) le temps qu'ils le portent. #1002-r1.

RE : decompile ghidra, build `rnca9r7q6c` (les deux corps ci-dessous sont LUS verbatim).

i2 de la relique : « Friendly surrounding Imperial Summons have Final Vengeance. »

===================================================================================================
LES DEUX ARBRES, LUS VERBATIM
===================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FinalVengeance_UnitEffect$$CreateTargetTrigger` =

      FinalJusticeAbility.Trigger(dsl)
    & op_LogicalNot( HasTrait( Owner@<DSLSelectors+0x30>, 0x3f6 = 1014 UnitTrait.FinalJustice ) )

ou `IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$Trigger(dsl)` -- une
STATIQUE partagee, dont le corps entier est --

      OnPreDeath( ownerNeedsToBeAlive = 1, ignoreOverkill = 0 )  &  get_OwnerIsTarget

`...FinalVengeance_UnitEffect$$CreateTargetTriggerBehaviour` =

      TriggerAbility( targets  = Owner@<DSLSelectors+0x30>,
                      ability  = 0x400 = TriggeredAbilityType.FinalJustice,
                      actor    = null,
                      caster   = Get(abilityEntities + 8),
                      target   = Get(abilityEntities + 0x10),
                      sel4     = null,
                      groupType= 0,
                      ignoreUnitHavingAbility = **true** )

===================================================================================================
LE BIT QUI FAIT TOUT -- `ignoreUnitHavingAbility = true`
===================================================================================================

`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` :

    abilityState = ignoreUnitHavingAbility ? new Nullable<AbilityState>(default)
                                           : UnitExtensions.GetAbilityState(entity);
    if (abilityState.HasValue) { ... }

Le summon imperial ne PORTE pas `FinalJustice` -- c'est justement ce que l'effet lui prete. Sans ce
bit, `GetAbilityState` rendrait un `Nullable` VIDE et **rien** ne s'executerait. Le port codait le
parametre en dur a `false` (ses deux seuls call-sites le passent ainsi) : c'etait l'ETAGE manquant,
ouvert par la meme tranche dans `abilities/behaviours/lifecycle.py::TriggerAbility`.
⚠ La faute qu'il aurait produite est SILENCIEUSE et PERMISSIVE-EN-MOINS : `notCarrying` aurait avale
100 % des declenchements, l'event `TriggerAbility` serait parti avec `dispatched: True`, et aucune
assertion d'etat n'aurait bouge.

===================================================================================================
CE QUE CE MODULE RE-MATERIALISE, ET POURQUOI CE N'EST PAS UNE INVENTION
===================================================================================================

Le gate `AmountIsGreater(Count(sortedTargets), Zero) & NOT TargetIsOverkilled` appartient au
`...FinalJusticeAbility$$CreateBehaviour` (pas a son `CreateTrigger`). Le port l'a collapse dans
`FinalJusticeAbility.matches()`, et CE point d'entree-ci court-circuite `matches` par construction
(`TriggerAbility` est un declenchement DIRECT). Le bras `Count > 0` survit tout seul
(`_finaljustice_attack` rend `target: None` sans cible) ; le bras `NOT TargetIsOverkilled`, lui,
serait PERDU -- il est donc re-applique ICI, ou l'evenement `On(PreUnitDeath)` est disponible.
C'est un DEPLACEMENT du meme gate natif, pas un gate supplementaire.

===================================================================================================
`ApplyInternal` / `RevertInternal` : UN STEP DE STREAM, PAS UNE OPERATION (#1002-r3, TRANCHE)
===================================================================================================

L'enonce d'origine accusait le mauvais champ, et c'est ce qui rendait le dict ininterpretable : il
parlait d'une Operation poussee a « `<processor>+0x70` ». Or `IdunBattle.Entities.Effects.
BaseEffect$$Init` ecrit, verbatim, `*(this+0x68) = operationProcessor` et `*(this+0x70) = events`.
Le champ lu par les deux corps est donc le canal d'EVENEMENTS. Ce qu'ils poussent :

    events.<slot 2>( StepType.ChangeStats = 0xc,
                     <entityId de l'effet>,
                     { TagKey.UnitStats_IsPlayDeathAnimationOnHit = 0x76 : 0 } )   # apply
                                                                          ... : 1 )   # revert

CE QUI IDENTIFIE LE CANAL n'est pas le nom du champ mais le couple (interface, slot) : c'est le
MEME que celui d'une Operation dont ghidra NOMME le recepteur --
`IdunBattle.Operations.AddActiveAbilityOperation$$Execute` fait
`<slot 2>( IdunBattle.Core.AOperation$$get_Events(this), StepType.ChangeAbility = 0xd, entityId,
{ TagKey.UnitStats_ActiveAbility_Id : ..., ... } )`. Meme interface, meme slot, step DIFFERENT.

RIEN A PORTER COTE MOTEUR, et c'est MESURE, pas suppose : les seuls symboles du build qui portent
`PlayDeathAnimationOnHit` sont `idun.Game.Board.AUnitView$$get_/set_/SetPlayDeathAnimationOnHit` --
la couche VUE. AUCUN sous `IdunBattle.` ni `IdunBattleLogic.`. L'effet demande a la vue de ne pas
jouer l'animation de mort sur le coup tant qu'il est applique (`0`), et la lui rend au retrait
(`1`) : exactement ce qu'il faut pour que le summon place sa derniere attaque AVANT de tomber.

⚠ LE SEUL CRAN QUI PUISSE SE PERIMER EST LE DERNIER. Le jour ou un consommateur LOGIQUE de ce tag
apparait, « purement visuel » est a refaire -- c'est pour lui que
`probe_1002r3_final_vengeance_stream_step.py` est versionne (5 crans, tout derive du binaire et des
tables versionnees, aucune VA en dur).

===================================================================================================
RESIDUS NOMMES -- ce que ce module NE porte PAS
===================================================================================================

* **`caster = Get(abilityEntities + 8)` / `target = Get(abilityEntities + 0x10)`.** Ces deux slots
  ne servent qu'a RE-CONSTRUIRE l'`AbilityEntities` passe a l'ability declenchee ; le behaviour de
  `FinalJustice` porte, lui, ne lit que son OWNER (`_finaljustice_attack(state, owner_id)`), donc
  le mapping exact des deux offsets n'a AUCUN observable ici. Le port thread l'acteur et la cible de
  l'evenement de mort, seule source disponible. A relire au prochain dump si un consommateur les
  lit un jour.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.lifecycle import TriggerAbility
from ....components import StatsComponent
from ....state import State
from ..base import EffectTrigger, TriggerEvent

#: L'EFFET porte par le summon (`EffectType`), et l'ABILITY qu'il prete (`TriggeredAbilityType`) --
#: DEUX enums distincts, jamais rapproches par leur ordinal.
FINAL_VENGEANCE_UNIT_EFFECT = int(EffectType.FinalVengeance_UnitEffect)      # 0x5ae = 1454
FINAL_JUSTICE = int(TriggeredAbilityType.FinalJustice)                      # 0x400 = 1024
#: `HasTrait(Owner@<+0x30>, 0x3f6)` -- `UnitTrait.FinalJustice` (1014). Le NOM, pas l'ordinal :
#: c'est ce que publie `StatsComponent.ctx.traits`.
_TRAIT_FINAL_JUSTICE = UnitTrait.FinalJustice.name


def final_vengeance_target_trigger_behaviour_tree():
    """`...FinalVengeance_UnitEffect$$CreateTargetTriggerBehaviour` -- MIRROR 1:1.

    `targets = Owner@<DSLSelectors+0x30>` : l'unite declenchee est le PORTEUR de l'effet, c.-a-d. le
    summon qui meurt. `ignore_unit_having_ability=True` est le 8e argument natif, LU (cf. l'en-tete)
    -- il est ce qui autorise un porteur qui n'a PAS `FinalJustice` a l'executer."""
    return TriggerAbility(Owner(), FINAL_JUSTICE, ignore_unit_having_ability=True)


class FinalVengeanceUnitEffectTrigger(EffectTrigger):
    """`FinalVengeance_UnitEffect` (1454) -- rail TARGET-TRIGGER.

    OBSERVABLE : un summon imperial ami adjacent au porteur de `RelicOfLostCadia` porte l'effet ;
    quand il meurt SANS avoir ete overkille, il place une derniere attaque normale sur la cible la
    plus rentable, exactement comme `worldKharn` avec son trait `FinalJustice`."""
    effect_type = FINAL_VENGEANCE_UNIT_EFFECT                # 0x5ae = 1454
    event_id = int(EventTriggerType.PreUnitDeath)            # `OnPreDeath(alive 1, ignoreOverkill 0)`
    TRIGGERED_ABILITY_ID = FINAL_JUSTICE                     # l'id INSCRIT par l'ability declenchee
    #: `OnPreDeath(ownerNeedsToBeAlive = 1)` : le porteur est l'unite MOURANTE, donc deja
    #: `alive=False` au dispatch -- meme bypass que `FinalJusticeAbility`, pour la meme raison.
    fire_on_death = True

    def _instance(self, state: State):
        """L'instance 1454 portee par `owner_id` -- necessaire pour lire son flag `IsActive`."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return None
        for e in eff.by_unit.get(int(self.owner_id), []):
            if not e.consumed and e.effect_type == FINAL_VENGEANCE_UNIT_EFFECT:
                return e
        return None

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # RAIL `TARGETS` (#229) : `IdunBattle.Operations.EvaluateTriggerOperation$$
        # EvaluateEffectTriggerTargets` lit `EffectComponent.IsActive @+0x5c` AVANT d'evaluer le
        # trigger d'un `$$CreateTargetTrigger` -- le gate est NATIF, le port doit le rendre.
        inst = self._instance(state)
        if inst is None or not inst.active:
            return False
        # `get_OwnerIsTarget` (via `FinalJusticeAbility.Trigger`) : le porteur de l'effet EST le
        # mourant.
        mourant = ev.dying_id if ev.dying_id is not None else ev.target_id
        if mourant is None or int(mourant) != int(self.owner_id):
            return False
        # `NOT HasTrait(Owner@<+0x30>, 0x3f6 = FinalJustice)` -- « celui qui a DEJA Final Vengeance
        # ne le recoit pas deux fois ». Sans lui, `worldKharn` (qui porte le trait) attaquerait
        # DEUX fois en mourant s'il recevait l'effet.
        e = state.get_entity(int(self.owner_id))
        sc = e.get_component(StatsComponent) if e is not None else None
        traits = set(getattr(getattr(sc, "ctx", None), "traits", None) or ())
        if _TRAIT_FINAL_JUSTICE in traits:
            return False
        # `NOT TargetIsOverkilled` -- le bras du `CreateBehaviour` de `FinalJustice` que ce point
        # d'entree perdrait (cf. l'en-tete §CE QUE CE MODULE RE-MATERIALISE). MEME lecture que
        # `FinalJusticeAbility.matches`, meme canal (`ev.overkill`).
        return not ev.overkill

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # `caster`/`target` de l'`AbilityEntities` reconstruit : l'acteur (tueur) et la cible
        # (mourant) de l'evenement de mort -- seule source disponible, sans observable ici.
        tueur = ev.actor_id
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                       actor_id=(None if tueur is None else int(tueur)),
                                       owner_id=int(self.owner_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        final_vengeance_target_trigger_behaviour_tree().execute(entities, ectx)
        trig = next((p for (n, p) in ectx.emitted if n == "TriggerAbility"), None)
        if trig is None:
            return None
        return {"effect": EffectType.FinalVengeance_UnitEffect.name,
                "owner": int(self.owner_id),
                "ability": FINAL_JUSTICE,
                "dispatched": bool(trig.get("dispatched")),
                "notCarrying": list(trig.get("notCarrying") or ()),
                "results": list(trig.get("results") or ())}
