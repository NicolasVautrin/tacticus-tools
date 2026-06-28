"""Base des Operations (mutateurs ECS).

Native : chaque `IdunBattle.Operations.*Operation` a un `Execute(state, …)` qui mute
des composants et peut émettre des events (→ cascade). Côté Python, chaque operation
concrète hérite de `Operation` et implémente `execute`, en miroir 1:1 du natif (VA
citée), RE'd puis validée contre le live avant d'être affirmée.

⚠ Aucune operation concrète encore portée — voir le plan de tranches (#24+).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import State
    from ..events import EventBus


class Operation:
    """Base d'un mutateur atomique. Sous-classe = 1 operation native (VA en docstring).
    `execute` mute `state` (composants) et peut pousser des events sur `bus`."""
    __slots__ = ()

    def execute(self, state: "State", bus: "EventBus") -> None:  # pragma: no cover
        raise NotImplementedError(
            f"{type(self).__name__}.execute non porté (cf. plan de tranches)")
