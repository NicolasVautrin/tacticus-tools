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
from .abilities.handler import AbilityHandler
from .operations.damage import DamageHandler
from .operations.movement import MovementHandler
from .operations.triggers.dispatch.pending import process_pending_triggered_abilities
from .operations.triggers.dispatch.damage_events import process_damage_events   # #443-r2-b2
#: FORME B (import de MODULE), et pas `from ...phase import phase_end_triggers` : le differe
#: est mesure GRATUIT une fois les barils vides, mais hisse en forme A il rendrait INERTE le
#: `monkeypatch.setattr(phase_mod, "phase_end_triggers", ...)` de
#: `test_389_ramming_speed_combat_offline::test_runner_apply_closes_the_phase` -- mesure du
#: 2026-08-06, ce test est TOMBE ainsi. Un import de module relit l'attribut A L'APPEL.
from .operations.triggers.dispatch import phase as phase_dispatch
from .operations.turnflow import TurnFlowHandler
from .operations.turnflow import verify_units_turn_finished


class Runner:
    """Runner de bataille. `state` = ECS ; `pre_handlers`/`post_handlers` = visiteurs ;
    `recorder` journalise chaque message appliqué (base d'un Replay/diff)."""

    def __init__(self, state: Optional[State] = None):
        self.state: State = state if state is not None else State()
        self.bus = EventBus()
        self.pre_handlers: List[object] = []      # visiteurs (visit_<Msg>)
        self.post_handlers: List[object] = []
        self.recorder: List[Message] = []         # @0xb8 — journal des messages
        # #287-r1-r1 : dernier bilan de `VerifyUnitsTurnFinishedOperation$$Execute` (poses, retraits,
        # ABSTENTIONS). Diagnostic seulement — c'est ce qui rend l'amplitude du residu lisible.
        self.last_verify_turn_finished: Optional[dict] = None

    def install_default_handlers(self, spread_pct: Optional[int] = None) -> "Runner":
        """Installe les handlers portés (tranche par tranche) : mouvement + dégât + abilities actives.

        `spread_pct` = `BattleConfiguration.Damage.DamageSpreadPercentage`. `None` (le cas normal)
        = LU de la BC de cette bataille, via `State.damage_spread_percentage` que
        `load_state(damage_config=...)` a posé ; à défaut, le défaut DÉRIVÉ de la seed versionnée.
        Le foyer est `engine.services.damage_config.resolve_spread_pct` — aucun `20` en dur ici
        (c'était le résidu `#449-r2-r4` : le natif le lit dans la BC, cf.
        `IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64`)."""
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
        # #443-r2-b2 : DRAIN DE LA FILE DES DAMAGE-EVENTS, **AVANT** celui des triggered-abilities
        # differees. Le rang est LU verbatim dans
        # `IdunBattle.Messages.InputMessageProcessor$$RunPhase` :
        #     action() ; VerifyDeaths() ; **ProcessDamageEvents()** ; <slot 0x1e> ;
        #     ProcessPendingTriggeredAbilities() ; <slot 0x14> ; ...
        # Les inverser ferait voir aux consommateurs d'`On(0x11)` un etat que le natif leur cache
        # (une ability differee jouee avant la purge). Le SECOND couple `ProcessDamageEvents` /
        # `ProcessPendingTriggeredAbilities` du bloc de fin de tour n'est pas porte -- MEME residu,
        # deja nomme, que le second drain des differees.
        process_damage_events(self.state)
        process_pending_triggered_abilities(self.state)
        # #287-r1-r1 : ARBITRAGE DE `UnitFlag.NoActionAvailable`. Toujours dans la branche
        # `isInternalPhase == false` de `IdunBattle.Messages.InputMessageProcessor$$RunPhase`, et
        # APRES le DRAIN #1 ci-dessus, le natif invoque le slot `IOperationProcessor` **0x21** =
        # `Core.Services.OperationProcessor$$VerifyUnitsTurnFinished` (AUCUN argument — c'est ce qui
        # l'identifie parmi `0x22` a un argument et `0x23` a deux) ->
        # `IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$Execute`. C'est la SEULE voie
        # native qui RETIRE le flag (slot 0x77), et le retrait est load-bearing : le flag SURVIT au
        # changement de tour (`UnitFlagsComponent$$RemoveTurnFlags(includeNoAction: 0)`), donc sans
        # lui toute unite marquee une fois le resterait pour toujours.
        # Le natif appelle `0x21` DEUX fois ; le port n'en pose qu'un — les gestes que le natif
        # intercale entre les deux ne sont pas joues ici, l'operation est idempotente, et le second
        # appel couterait un second pathfinding par unite (residu nomme dans
        # `operations/turnflow.verify_units_turn_finished`).
        self.last_verify_turn_finished = verify_units_turn_finished(self.state)
        phase_dispatch.phase_end_triggers(self.state)
