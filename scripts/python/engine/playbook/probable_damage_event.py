"""Port FIDÈLE de `IdunBattle.AI.Playbook.ProbableDamageEvent` (.ctor RE'd dans
GenerateMultiHitAttackPredictions @181409da0). Le scorer génère une LISTE de ces events
(un par membre/coup probable), chacun pondéré par une probabilité, puis somme
`CalculateUtilityFromDamageEvent(event) × probability`."""
from __future__ import annotations

from dataclasses import dataclass

from ..entities.unit_context import UnitContext
from ..services.damage_prediction import DamagePredictionResult


@dataclass
class ProbableDamageEvent:
    """Événement de dégât probable : cible + prédiction + poids de probabilité (Fix64(1) par
    défaut ; <1 pour membres secondaires Blast / crit, etc. — param_10 natif)."""
    target: UnitContext
    prediction: DamagePredictionResult
    probability: float = 1.0
