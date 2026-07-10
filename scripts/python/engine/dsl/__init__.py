"""Socle DSL générique = moteur de NŒUDS (mirror 1:1 du DSL lazy `DSLFactory`/`TargetsSelector` du jeu).

Chaque ability compose un arbre `Node` (numérique + runtime + ciblage), évalué par `Node.evaluate(ctx)`
contre un `DslContext` (état de bataille). cf. nodes.py.
"""
from .nodes import (  # noqa: F401
    Node, DslContext,
    Const, ConfigConst, Sum, Min, Multiply, Difference, If,
    Max, Divide, Half, Double, Negative, PercentageOf,
    TotalTimesAttacked, TimesRepaired, TurnsFromRounds, HasFlag,
    AreEqual, AmountIsEqual, AmountIsGreater, AmountIsEqualOrGreater,
    AmountIsGreaterThanZero, AmountIsZero, AmountIsOdd, Modulo,
    CasterTile, TargetTile, OwnerTile,
    SurroundingUnits, AdjacentEnemies, Enemies, Damageable, And, Sub, UnitSet,
    Subject, Count, Filter,
    UnitsDirectlyBehind,
    Get, ConfigVar, Cache, StatAmount,
    OwnerIsTarget, OwnerIsCaster, OwnerIsActor,
    Friends, Units, Tiles, First, Unique, UnitsWithTrait, UnitsWithoutTrait,
    AdjacentFriends, SurroundingEnemies, SurroundingFriends,
    SortByFormula, SortByDistance,
    HasTrait, HasEffect, HasAnyEffect, IsAlive, IsDead, Alive,
    IsMeleeAttack, IsRangedAttack, IsNormalAttack, IsAdjacent, IsInRange,
    Entity, EntityId, Nothing, Null, EffectSource, EffectLevel, EffectFromOwner,
)
