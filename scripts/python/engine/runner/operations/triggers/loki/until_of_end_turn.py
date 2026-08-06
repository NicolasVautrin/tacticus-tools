"""Le TRIGGER DE RETRAIT d'`IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect` -- la seule chose
que cette classe d'effet fasse, et donc tout ce qu'il y a a porter d'elle cote runner.

## D'ou vient ce trigger (il n'est PAS declare par l'ability qui pose l'effet)

Le natif ne cable rien a la pose. C'est `IdunBattle.Entities.Effects.BaseEffect$$
CreateHandleTriggerAbilities` qui, POUR TOUT effet, appelle le virtuel `CreateRemoveEffectTrigger` et,
si celui-ci rend un trigger non nul, ajoute a l'`ArraySet` de l'effet :

    Triggered( <trigger>, BaseEffect$$GetRemoveEffectBehaviour(), allowInAtomicGroup: <virtuel> )
    ou GetRemoveEffectBehaviour() = IdunBattleLogic.Entities.DSLBehaviors$$RemoveEffect(Effect@0x38)

`UntilOfEndTurnEffect` fournit ce trigger, et rien d'autre :

    IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect$$CreateRemoveEffectTrigger
        = DSLTriggers$$On(EventTriggerType.TurnEnd = 0x17, ownerNeedsToBeAlive: false)

AUCUN predicat supplementaire -- ni owner, ni acteur, ni equipe. L'effet part au PREMIER `TurnEnd`
qui suit sa pose, quel que soit le camp dont le tour se termine. C'est bien ce que le port fait ici :
`matches` rend `True` sans condition, et le dispatch generique (`evaluate_trigger_operation`) ne
retient que les entrees dont l'`event_id` correspond et dont le porteur est vivant.

`ownerNeedsToBeAlive: false` -> le natif ne gate PAS sur la vie du porteur. Le port, lui, applique le
gate `CanGet*Trigger` du dispatch (owner unit vivant) : ecart ASSUME et sans effet observable, un
cadavre n'ayant pas d'`EffectsState` a nettoyer qui change quoi que ce soit.

## Cote port : un EFFECT_TRIGGER, pas un timer

`IdunBattle.Operations.AddEffectOperation$$Execute` pose 1175 SANS duree (le poseur passe un
`Nullable<int>` vide et `StaticBattleRules.Effect$$DefaultAmountOfRounds(1175)` rend un Nullable vide
-- re-derive par `probe_1175 --step 4`), donc `remaining = 0` = PERMANENT. Le retrait ne peut venir
QUE d'ici. Si cette entree disparaissait du registre, le marqueur resterait A VIE et
`HatefulAssaultAbility` cesserait definitivement de se declencher sur toute unite deja frappee une
fois -- une regression SILENCIEUSE (aucune erreur, aucun test de dommage rouge).

## Ce qui est MESURE et ce qui ne l'est pas

Le binaire porte DEUX classes soeurs au corps de `.ctor` IDENTIQUE (donc dedupliquable, cf. CLAUDE.md
« un nom de ctor n'est pas une classe ») : `UntilOfEndTurnEffect` (`On(0x17 TurnEnd)`) et
`IdunBattle.Entities.Effects.Loki.UntilOfEndPhaseEffect` (`On(0x3a PhaseEnd)`). Le slot
`Il2CppClass*` de 1175 est UNIQUE (aucun autre `EffectType` ne le partage) mais ne se resout pas
statiquement en un NOM. C'est donc la MESURE LIVE qui tranche `TurnEnd` contre `PhaseEnd` -- le tour
exact ou 1175 quitte `decisionView.effects` -- et elle est figee par
`tests/engine/runner/test_hateful_assault_live.py`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.tiles import Caster
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import RemoveEffect
from ....state import State
from ..base import EffectTrigger, TriggerEvent

HATEFUL_ASSAULT_ALREADY_ATTACKED = int(EffectType.HatefulAssault_AlreadyAttacked)   # 0x497 = 1175


class UntilOfEndTurnRemove(EffectTrigger):
    """`UntilOfEndTurnEffect$$CreateRemoveEffectTrigger` = `On(TurnEnd)` (SANS predicat) ->
    `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette instance>)`.

    Base GENERIQUE : la classe native est partagee, donc le port l'est aussi. Une sous-classe = un
    `EffectType` a inscrire dans `EFFECT_TRIGGERS` (aujourd'hui le seul est 1175).

    COLLAPSE ASSUME, identique a `ChronometronExtraDamageRemove` : le natif retire L'INSTANCE
    (`RemoveEffect(Effect@0x38)`), le port retire tous les stacks non consommes du type sur le porteur
    (`RemoveEffect(effect_type, Caster())`, la seule forme portee). Les deux coincident : le gate
    << deja present >> d'`AddEffectOperation` garantit au plus UNE instance par unite, et une re-pose
    incremente `times_applied` au lieu d'en creer une seconde."""
    event_id = int(EventTriggerType.TurnEnd)                # On(0x17 = 23)
    effect_type = -1                                        # pose par la sous-classe

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`On(TurnEnd, ownerNeedsToBeAlive: false)` -- le trigger natif n'a AUCUN predicat, pas meme
        sur le camp dont le tour se termine. Rien a evaluer."""
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(self.effect_type, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": int(self.effect_type), "owner": int(self.owner_id), "removed": removed}


class HatefulAssaultAlreadyAttackedRemove(UntilOfEndTurnRemove):
    """`1175 HatefulAssault_AlreadyAttacked` -- l'unique `EffectType` que la fabrique native construit
    par `UntilOfEndTurnEffect` (l'autre porteur du meme NOM de ctor, `1407
    HypersensoryAbilities_HasBeenAttacked`, occupe un slot `Il2CppClass*` DIFFERENT et n'est pas
    porte).

    OBSERVABLE : l'ennemi qui s'ecarte d'un hex adjacent a `blackTerminator` prend l'attaque
    d'opportunite ET gagne 1175 ; a la fin du tour, 1175 disparait de `decisionView.effects`, et il
    redevient frappable au tour suivant."""
    effect_type = HATEFUL_ASSAULT_ALREADY_ATTACKED
