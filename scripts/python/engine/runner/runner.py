"""`Runner` — pipeline `Apply` (RE CONFIRMÉ, cf. docs/rl/runner-engine.md §1.1).

`IdunBattle.Runner.IdunRunner$$IdunBattle.Runner.IdunRunner$$Apply :
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
        from .operations.turnflow import TurnFlowHandler
        from .abilities import AbilityHandler
        self.movement_handler = MovementHandler(self.state, self.bus)  # after_move (overwatch…)
        self.post_handlers.append(self.movement_handler)
        self.damage_handler = DamageHandler(self.state, spread_pct)
        self.post_handlers.append(self.damage_handler)
        self.ability_handler = AbilityHandler(self.state)     # ActiveAbilityMessage → ExecuteBehaviour
        self.post_handlers.append(self.ability_handler)
        self.turnflow_handler = TurnFlowHandler(self.state)   # EndTurnMessage → EndTurn/ChangeTurn/StartTurn
        self.post_handlers.append(self.turnflow_handler)
        return self

    # --- gates (mirror IdunRunner$$ShouldBlockMessage / ShouldRejectMessage) ---
    def should_block(self, msg: Message, current_player: Optional[int]) -> bool:
        return False   # TODO RE @ IdunRunner$$ShouldBlockMessage

    def should_reject(self, msg: Message) -> bool:
        return False   # TODO RE @ IdunRunner$$ShouldRejectMessage

    # --- pipeline IdunBattle.Runner.IdunRunner$$Apply ---
    def apply(self, msg: Message) -> None:
        cur = self.state.current_player_id           # GetCurrentPlayerId(state)
        if self.should_block(msg, cur) or self.should_reject(msg):
            return                                   # message bloqué/rejeté = no-op
        # #140 : boundary de phase-triggers (mirror EndPhaseOperation.ResetEntityPhase). Le natif reset les
        # compteurs par ACTIVATION ; offline (pas d'OperationProcessor) on le mappe sur chaque ACTION
        # top-level. `apply` n'est PAS ré-entrant dans le port (la cascade = appels directs, pas des re-apply)
        # → le reset ici est TOUJOURS avant la cascade, jamais dedans (ne casse pas la borne de récursion).
        self.state.reset_trigger_phases()
        for h in self.pre_handlers:                  # PRE @0x80
            msg.accept(h)
        self.recorder.append(msg)                    # record @0xb8
        for h in self.post_handlers:                 # POST @0x88
            msg.accept(h)
        # #389-r1 : CLOTURE DE PHASE. `IdunBattle.Messages.InputMessageProcessor$$RunPhase`, dans sa
        # branche `isInternalPhase == false` (celle de TOUT message top-level : les `Visit` passent 0,
        # seul `$$ProcessPendingTriggeredAbilities` passe 1), appelle
        # `Core.Services.OperationProcessor$$EndPhase` -> `IdunBattle.Operations.EndPhaseOperation$$
        # Execute`, qui publie `EventTriggerType.PhaseEnd` (0x3a) AVANT ses deux resets. `apply` EST la
        # borne du message top-level cote port -> l'emission va ICI, en sortie. Le `reset_trigger_phases`
        # ci-dessus est l'AUTRE geste de la meme operation native (`$$ResetEntityPhase`), place en entree
        # (decalage assume #140 : le reset de fin de phase N == celui du debut de phase N+1) -- ce qui
        # laisse l'emission s'executer avec les compteurs de LA phase qui se termine, comme le natif.
        # #406 : DRAIN DE LA FILE DES TRIGGERED-ABILITIES DIFFEREES, AVANT la cloture de phase.
        # `IdunBattle.Messages.InputMessageProcessor$$RunPhase` appelle
        # `$$ProcessPendingTriggeredAbilities` juste apres le retour de `action()` (et apres
        # `VerifyDeaths` / `ProcessDamageEvents`), donc APRES la totalite de l'arbre d'operations du
        # message -- `IdunBattle.Operations.FinishAttackOperation$$Execute` et ses `On(9)`/`On(10)`
        # inclus -- et AVANT `EndPhase`. `apply` etant la borne du message top-level cote port, la
        # position exacte est ICI, entre les post-handlers et `phase_end_triggers`.
        # RE + residus (2e drain natif du bloc de fin de tour, `VerifyTurnEnd`) :
        # `operations/triggers/dispatch/pending.py`.
        from .operations.triggers.dispatch.pending import process_pending_triggered_abilities
        process_pending_triggered_abilities(self.state)
        from .operations.triggers.dispatch.phase import phase_end_triggers   # lazy : circular import
        phase_end_triggers(self.state)
