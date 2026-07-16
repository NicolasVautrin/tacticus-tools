"""Socle DSL = les 4 BASES de famille (mirror `IdunBattle.DSL`) : `AAmountFormula`/`AbilityTrigger`/
`TargetsSelector` (LAZY, base.py) + `AbilityBehaviour` + infra walker (`OperationResult`/
`ExecutionContext`, effects.py). Les NOEUDS CONCRETS vivent dans leur namespace natif
`entities/{formulas,triggers,selectors,behaviours}` et se construisent via la FACADE `DSLFactory` =
`dsl/nodes.py` (importee `as dsl` par les abilities/prediction). cf. nodes.py.

NB (cycle) : ce `__init__` n'importe QUE base + effects (feuilles, sans dep `entities/`) -> importer
`engine.dsl.base` depuis `entities/*` ne re-declenche PAS la facade -> pas de cycle d'import.
"""
from .base import (  # noqa: F401
    AAmountFormula, AbilityTrigger, TargetsSelector, DslContext, Const,
)
from .effects import AbilityBehaviour, OperationResult, ExecutionContext  # noqa: F401
