"""Bus de cascade — discipline LIFO (immédiat, inline) + FIFO (différé).

Modèle natif (RE, cf. docs/rl/runner-engine.md §1.5) :
  • IMMÉDIAT : `EvaluateTriggerOperation.ExecuteImmediately` @180e6ec90 → traité
    INLINE, profondeur d'abord = pile d'appels = **LIFO**.
  • DIFFÉRÉ : `EvaluateTriggerOperation.Execute` @180e6fac0 → enfile un `BattleEvent`
    sur le bus `Events` (`get_Events` @180ffa4a0), drainé plus tard = **FIFO**.
  • L'arbre résultant (groupes) est capté côté live par `apply-stack.ts`
    (stream_group/stream_event) → vérité de validation de la cascade.

⚠ STUB structurel : la sémantique exacte du drain différé (quand/où, phases
System_*) sera plombée à la tranche TRIGGERS (#6) contre l'arbre live.
"""
from __future__ import annotations

from collections import deque
from typing import Callable, Deque, List


class BattleEvent:
    """Base d'un évènement de bataille (UnitMoved, UnitDamaged, UnitKilled, …).
    Chaque type concret porté avec ses champs RE'd au fil des tranches."""
    __slots__ = ()


class EventBus:
    """Deux canaux distincts (cf. modèle natif) :
      - `dispatch_immediate(ev)` : exécution INLINE (LIFO via la pile d'appels Python).
      - `enqueue_deferred(ev)` / `drain_deferred()` : file FIFO traitée à un point de
        synchronisation (post-handlers System_*)."""
    __slots__ = ("_deferred", "_listeners")

    def __init__(self):
        self._deferred: Deque[BattleEvent] = deque()
        # event_type -> listeners TRIÉS (mirror AbilityAndEffectCache, AddSorted
        # @18128ab10). Rempli à la tranche TRIGGERS.
        self._listeners: dict[type, List[Callable[[BattleEvent], None]]] = {}

    # --- différé (FIFO) ---
    def enqueue_deferred(self, ev: BattleEvent) -> None:
        self._deferred.append(ev)

    def drain_deferred(self, handle: Callable[[BattleEvent], None]) -> None:
        while self._deferred:
            handle(self._deferred.popleft())

    # --- immédiat (LIFO inline) ---
    def dispatch_immediate(self, ev: BattleEvent) -> None:
        for fn in self._listeners.get(type(ev), ()):   # ordre trié = ordre natif
            fn(ev)
