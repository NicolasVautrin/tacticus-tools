"""`engine.runner` — port Python FIDÈLE du runner de bataille natif
(`IdunBattle.Runner.IdunRunner` + Operations + ECS + cascade events/triggers).

Carte/plan : docs/rl/runner-engine.md. Méthodo : RE ghidra (decompile=vérité,
structure 1:1, VA citées), validation par agrément vs LIVE brique par brique
(replay-diff). Build de référence gqfc5mff6c.

⚠ OSSATURE CONFIRMÉE (pipeline Apply, primitives ECS, bus de cascade). Les corps
d'Operations sont des STUBS remplis tranche par tranche (move → damage → death →
effects → triggers → turn-flow), chacun validé contre le live avant d'être affirmé.
"""
from __future__ import annotations

from .state import State, Entity, Component
from .events import EventBus, BattleEvent
from .messages import Message
from .operations.base import Operation
from .runner import Runner

__all__ = [
    "Runner", "State", "Entity", "Component",
    "EventBus", "BattleEvent", "Message", "Operation",
]
