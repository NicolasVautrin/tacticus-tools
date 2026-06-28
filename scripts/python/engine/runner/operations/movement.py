"""Operations de mouvement — `IdunBattle.Operations.MoveUnitOperation` @180e79ff0.

Tranche 1, INCRÉMENT 1a (POSITION) : écrit la position finale du mover dans son
`PositionComponent`. C'est le cœur observable du move (le natif fait aussi la
validation, CalculatePaths, AddMoveEvent/pas, KillSteppableUnits, charging…, mais
l'EFFET d'ÉTAT sur le mover = sa position finale).

INCRÉMENT 1b (à venir, validé vs la vérité-terrain probe = Maugan Ra 1174 sur le
mover) : `EvaluateAfterMoveTriggers` @180e79770 → cascade OVERWATCH
(`Overwatch_AutoAttackEffect` → auto-attaque → dégât + consommation de l'effet).
`AddMoveEvent` @180e78d20 émet l'event UnitMoved(step 3) + tuiles du chemin sur le bus.
"""
from __future__ import annotations

from ..state import State
from ..events import EventBus
from ..components import PositionComponent
from .base import Operation


class MoveUnitOperation(Operation):
    """@180e79ff0 (1a) — pose la position finale du mover. `to` = (col,row)."""
    __slots__ = ("unit_id", "to")

    def __init__(self, unit_id: int, to: tuple[int, int]):
        self.unit_id = unit_id
        self.to = to

    def execute(self, state: State, bus: EventBus) -> None:
        e = state.get_entity(self.unit_id)
        if e is None:
            return
        pc = e.get_component(PositionComponent)
        if pc is None:
            e.add_component(PositionComponent(self.to[0], self.to[1]))
        else:
            pc.col, pc.row = self.to
        # INCRÉMENT 1b : AddMoveEvent (bus) + EvaluateAfterMoveTriggers (overwatch) ici.


class MovementHandler:
    """Visiteur des messages de mouvement (mirror du handler natif qui lance
    MoveUnitOperation). Lié à l'état/bus du runner."""
    __slots__ = ("state", "bus")

    def __init__(self, state: State, bus: EventBus):
        self.state = state
        self.bus = bus

    def visit_MoveUnitMessage(self, msg) -> None:
        MoveUnitOperation(msg.unit_id, msg.to).execute(self.state, self.bus)
