"""Facade `DSLFactory` (mirror `IdunBattleLogic.Entities.DSLFactory`) = POINT DE CONSTRUCTION UNIQUE de
tous les noeuds DSL. Les abilities/prediction l'importent `as dsl` et construisent via `dsl.Sum(...)`,
`dsl.AdjacentEnemies(...)`, `dsl.Foreach(...)` = exactement les `DSLFactory.X` natifs.

Les CLASSES concretes vivent dans leur home de namespace natif `IdunBattle.Entities.{Formulas,Triggers,
Selectors,Behaviours}` -> `entities/{formulas,triggers,selectors,behaviours}.py` ; les 4 BASES
(`IdunBattle.DSL`) dans `dsl/base.py` (T/S/V) + `dsl/effects.py` (E). Ce module ne fait que RE-EXPORTER
(il est importe APRES l'init du package, jamais pendant l'import d'un module `entities/*` -> pas de cycle).
"""
from .base import *  # noqa: F401,F403
from .base import (  # noqa: F401
    AAmountFormula, AbilityTrigger, TargetsSelector, DslContext, Const, _pos, _feet, _within,
    _round_fix64, _c_mod, _same_entity, _units_of, _effect_field, _is_alive, _default_get_stat,
)
from .effects import AbilityBehaviour, OperationResult, ExecutionContext  # noqa: F401
# ORDRE VOULU : formulas EN DERNIER. `If` existe en 2 familles -- `behaviours.If` (conditionnel a EFFET,
# 2 args) et `formulas.If` (ternaire VALEUR, 3 args, utilise par active_ability `dsl.If(cond,a,b)`). On
# laisse la VALEUR gagner la facade (le `If` a EFFET reste importe en direct par runner/abilities/behaviours).
from ..entities.behaviours import *  # noqa: F401,F403
from ..entities.selectors import *   # noqa: F401,F403
from ..entities.triggers import *    # noqa: F401,F403
from ..entities.formulas import *    # noqa: F401,F403  (value `If` shadows behaviours.If -- voulu)
