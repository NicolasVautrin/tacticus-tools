"""`Runner` — pipeline `Apply` (RE CONFIRMÉ, cf. docs/rl/runner-engine.md §1.1).

`IdunBattle.Runner.IdunRunner$$Apply` @180e34bf0 :
    Apply(msg):
      cur = GetCurrentPlayerId(state)
      if ShouldBlockMessage(msg,cur) or ShouldRejectMessage(msg): return  # no-op
      for h in preHandlers@0x80:  h.handle(msg, state, cur)               # PRE
      record(msg)  @0xb8                                                   # journal (Replay)
      for h in postHandlers@0x88: h.handle(msg, state, cur)               # POST

Les handlers sont des visiteurs (`msg.accept(handler)`). L'ossature du pipeline est
fidèle ; les gates (`ShouldBlock`/`ShouldReject`) et les handlers concrets sont
remplis au fil des tranches (RE + validation live).
"""
from __future__ import annotations

from typing import Callable, List, Optional

from .state import State
from .events import EventBus
from .messages import Message


class Runner:
    """Runner de bataille. `state` = ECS ; `pre_handlers`/`post_handlers` = visiteurs ;
    `recorder` journalise chaque message appliqué (base d'un Replay/diff)."""

    def __init__(self, state: Optional[State] = None):
        self.state: State = state if state is not None else State()
        self.bus = EventBus()
        self.pre_handlers: List[object] = []      # visiteurs (visit_<Msg>)
        self.post_handlers: List[object] = []
        self.recorder: List[Message] = []         # @0xb8 — journal des messages

    def install_default_handlers(self, spread_pct: int = 20) -> "Runner":
        """Installe les handlers portés (tranche par tranche) : mouvement + dégât + abilities actives.
        `spread_pct` = BattleConfiguration.Damage.DamageSpreadPercentage (défaut 20)."""
        from .operations.movement import MovementHandler
        from .operations.damage import DamageHandler
        from .abilities import AbilityHandler
        self.movement_handler = MovementHandler(self.state, self.bus)  # after_move (overwatch…)
        self.post_handlers.append(self.movement_handler)
        self.damage_handler = DamageHandler(self.state, spread_pct)
        self.post_handlers.append(self.damage_handler)
        self.ability_handler = AbilityHandler(self.state)     # ActiveAbilityMessage → ExecuteBehaviour
        self.post_handlers.append(self.ability_handler)
        return self

    # --- gates (mirror IdunRunner$$ShouldBlockMessage / ShouldRejectMessage) ---
    def should_block(self, msg: Message, current_player: Optional[int]) -> bool:
        return False   # TODO RE @ IdunRunner$$ShouldBlockMessage

    def should_reject(self, msg: Message) -> bool:
        return False   # TODO RE @ IdunRunner$$ShouldRejectMessage

    # --- pipeline Apply @180e34bf0 ---
    def apply(self, msg: Message) -> None:
        cur = self.state.current_player_id           # GetCurrentPlayerId(state)
        if self.should_block(msg, cur) or self.should_reject(msg):
            return                                   # message bloqué/rejeté = no-op
        for h in self.pre_handlers:                  # PRE @0x80
            msg.accept(h)
        self.recorder.append(msg)                    # record @0xb8
        for h in self.post_handlers:                 # POST @0x88
            msg.accept(h)
