"""Socle d'EXECUTION des EFFET-NOEUDS (#149) = la BASE de la famille EFFETS (`AbilityBehaviour`, kind E)
+ l'infrastructure du walker (`OperationResult`, `ExecutionContext`). Mirror du namespace natif
`IdunBattle.DSL` — cote LAZY = `dsl/base.py` (3 bases T/S/V) ; les COMBINATEURS/concrets d'effet
(`Seq`/`Maybe`/`Foreach`/`If`/`Emit`) vivent dans `entities/behaviours.py` (= `IdunBattle.Entities.
Behaviours`), et les feuilles runner dans `runner/abilities/behaviours.py`.

Contrat du walker natif (lu sur `CombinedBehaviour.Execute @180ffe730`, `ForeachBehaviour.Execute
@180fc6210`, `MaybeBehaviour.Execute @180fc9dc0`) :
    OperationResult Execute(this, AbilityEntities entities /*0x50, by-value*/, IProcessor* proc)
  - `entities` = le contexte lu par tous les noeuds (caster/owner/actor, target, casterPosition,
    abilityType, level, subject courant) = homologue de `DslContext` ; reconstruit par `Foreach`.
  - `proc` (IProcessor*, classe DAT_1831d3468) = LE COLLECTEUR d'Operations, threade identiquement a
    travers TOUTE la recursion -> cote port = `ExecutionContext` (state + rng + bus).
  - retour `OperationResult` (byte@+0x20 = flag succes/court-circuit), combine en remontant
    (`OperationResult.Combine`). Operations appliquees via `IdunRunner.Apply @180e34bf0` (cascade deja portee).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .base import DslContext


@dataclass
class OperationResult:
    """Retour de tout `*Behaviour.Execute` natif (8 slots ; byte@+0x20 = flag succes/COURT-CIRCUIT) ;
    `Combine` en remontant. Ici on ne modelise que `stop` (le flag de court-circuit exploite par
    `CombinedBehaviour`) : pour des effets PURS (Spawn/AddEffect) `stop` reste False -> les deux
    branches d'un `&`/`+` s'executent. Les Operations emises N'atterrissent PAS dans l'OperationResult
    mais dans le collecteur `proc` (= `ExecutionContext.emitted`), fidele au natif."""
    stop: bool = False

    def combine(self, other: "OperationResult") -> "OperationResult":
        # `OperationResult.Combine` : `stop` propage (OR) ; les Operations vivent dans `proc`.
        return OperationResult(stop=self.stop or other.stop)

    @staticmethod
    def ok() -> "OperationResult":
        return OperationResult(False)


class ExecutionContext:
    """`IProcessor* proc` natif (classe DAT_1831d3468) threade a travers TOUTE la recursion des
    `*Behaviour.Execute` = LE COLLECTEUR d'Operations. Cote port : porte `state` (ECS mute par les
    Operations portees), `rng` (tirages `Maybe`, cf. `prng.next_bool @180e39720`), `bus` (cascade
    LIFO/FIFO deja portee, runner/events.py). `emitted` = journal des Operations emises (etiquette +
    payload) pour le replay-diff DSL<->imperatif<->live ; sans equivalent natif (le `proc` natif
    applique directement)."""
    __slots__ = ("state", "rng", "bus", "emitted")

    def __init__(self, state=None, rng=None, bus=None):
        self.state = state
        self.rng = rng
        if bus is None:
            from ..runner.events import EventBus
            bus = EventBus()
        self.bus = bus
        self.emitted: List = []

    def emit(self, name: str, **payload) -> None:
        """Journalise une Operation emise par une feuille (etiquette natif + payload)."""
        self.emitted.append((name, payload))


class AbilityBehaviour:
    """Noeud a EFFET = base de la famille EFFETS. Mirror `IdunBattle.DSL.AbilityBehaviour.Execute`
    (kind E). `execute(entities, ectx) -> OperationResult` (contrat du walker, cf. en-tete module).
    `entities` = `DslContext` (contexte lu, reconstruit par `Foreach`) ; `ectx` = `ExecutionContext`
    (le collecteur `proc`). A DISTINGUER des familles LAZY (`AbilityTrigger.should_trigger` /
    `TargetsSelector.select` / `AAmountFormula.calculate`, base.py). Chaque sous-classe cite la VA du
    `*Behaviour` qu'elle mirror (concrets dans entities/behaviours.py)."""
    __slots__ = ()

    def execute(self, entities: DslContext, ectx: ExecutionContext) -> OperationResult:  # pragma: no cover
        raise NotImplementedError(
            f"{type(self).__name__}.execute non porte (cf. #149 slice DSL-effet)")
