"""Socle DSL générique = moteur de NŒUDS (mirror 1:1 du DSL lazy `DSLFactory`/`TargetsSelector` du jeu).

Chaque ability compose un arbre `Node` (numérique + runtime + ciblage), évalué par `Node.evaluate(ctx)`
contre un `DslContext` (état de bataille). cf. nodes.py.
"""
from .nodes import (  # noqa: F401
    Node, DslContext,
    Const, ConfigConst, Sum, Min, Multiply, Difference, If,
    TotalTimesAttacked, TimesRepaired, HasFlag,
    CasterTile, TargetTile,
    SurroundingUnits, AdjacentEnemies, Enemies, Damageable, And, Sub, UnitSet,
    UnitsDirectlyBehind,
)
