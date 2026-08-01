"""Vecteur d'event de la face PHASE -- `On(0x3a = EventTriggerType.PhaseEnd)`.

## Ce qu'est une PHASE cote natif

`IdunBattle.Messages.InputMessageProcessor$$RunPhase(type, action, isInternalPhase, isManualTurnEnd)`
encadre l'execution d'UN message. Chaque `InputMessageProcessor$$Visit` (un par type de message
d'entree) l'appelle avec `isInternalPhase = 0` -- verifie sur le `Visit` d'AddUnit,
`RunPhase(this, 0x4, action, 0, 0)` -- alors que la cascade interne
`$$ProcessPendingTriggeredAbilities` l'appelle avec `RunPhase(this, 0xf, action, 1, 0)`.
**Une phase = un message TOP-LEVEL**, pas une triggered-ability.

Dans sa branche `isInternalPhase == false`, `$$RunPhase` appelle par slot
`Core.Services.OperationProcessor$$EndPhase` (qui n'a AUCUN appelant direct dans le binaire) ->
`IdunBattle.Operations.EndPhaseOperation$$Execute`, qui fait TROIS gestes, dans cet ordre :

    1. publie l'evenement `EventTriggerType.PhaseEnd` (0x3a)
    2. `$$ResetTileReservation`
    3. `$$ResetEntityPhase`

Le port portait deja (3) -- c'est le `state.reset_trigger_phases()` de `Runner.apply` (#140), place en
ENTREE d'`apply` plutot qu'en sortie (decalage assume : le reset de fin de phase N == le reset de debut
de phase N+1). (1) manquait entierement, et (2) n'est pas porte (pas de reservation de tuile cote port).

## Consommateurs

`EFFECT_TRIGGERS[1098 RammingSpeed_ExtraExplode]` (cf. `triggers/loki/ramming_speed.py`) -- le premier,
et le seul aujourd'hui. Le natif a d'autres ecouteurs de `PhaseEnd` (au moins
`IdunBattle.Entities.Effects.Loki.UntilOfEndPhaseEffect$$CreateRemoveEffectTrigger` et la premiere
branche d'`IdunBattle.Entities.Effects.TemporaryEffect$$CreateRemoveEffectTrigger` =
`On(0x3a) | (On(9, true) & OwnerIsActor)`) ; ils entreront par ce meme vecteur quand leurs effets seront
portes.

L'evenement n'a NI acteur NI cible (le natif publie sans entite -- `EndPhaseOperation$$Execute` ne passe
que le type), d'ou `actor_id = target_id = -1`, comme le vecteur `TurnEnd`.
"""
from __future__ import annotations

from ....state import State
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggerEvent
from .core import evaluate_trigger_operation


def phase_end_triggers(state: State) -> list[dict]:
    """Vecteur FIN DE PHASE (mirror de la publication `0x3a` d'`IdunBattle.Operations.EndPhaseOperation$$Execute`).

    Appele en SORTIE de `Runner.apply`, c.-a-d. a la cloture du message top-level -- la borne exacte de
    `RunPhase(..., isInternalPhase: false)`. No-op si personne n'ecoute."""
    ev = TriggerEvent(EventTriggerType.PhaseEnd, -1, -1, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)
