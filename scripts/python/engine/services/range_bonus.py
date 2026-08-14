"""Le canal RANGE BONUS du mouvement -- les deux structs natives et le contexte que le port passe
a `<Effect>.CreateRangeBonusForMovement`.

Ce module est une FEUILLE (aucun import du paquet) : il est le point de rencontre entre
`engine/entities/effects/base.py` (qui PRODUIT le bonus) et `engine/services/movement_query.py`
(qui le CONSOMME), sans arete entre les deux.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================

DEUX structs, pas une -- et leurs offsets sont LUS, pas devines :

  `EffectRangeBonus` (retour de `<Effect>$$CreateRangeBonusForMovement`, 0x20 octets)
      +0x00  Trigger              (IAbilityTrigger, null = pas de gate)
      +0x08  ExtraRange           (int, + padding)
      +0x10  ExtraRangeCondition  (Func<ITile, bool>, null = aucune condition)
      +0x18  ReduceRange          (Nullable<int>)

  `IdunBattle.Core.Services.RangeBonus` (ce que le mouvement consomme, 0x18 octets)
      +0x00  ExtraRange           (int, + padding)
      +0x08  ExtraRangeCondition  (Func<ITile, bool>)
      +0x10  ReduceRange          (Nullable<int>)

`IdunBattle.Entities.Effects.BaseEffect$$RangeBonusForMovement(entities)` est le convertisseur :
il appelle le slot virtuel `CreateRangeBonusForMovement(owner)`, rend `null` si le resultat est
vide, EVALUE le `Trigger` s'il est non nul et rend `null` s'il ne passe pas, puis recopie les
trois champs restants dans un `RangeBonus`.

QUI LIT QUOI (et c'est asymetrique)
------------------------------------
  * `IdunBattle.Core.Services.MovementQuery$$MovementRangeWithAppliedBonus(unit, baseRange,
    rangeBonuses)` ne lit QUE `ReduceRange` -- un `ExtraRange` n'augmente donc JAMAIS la portee
    brute du pathfinding ;
  * `IdunBattle.Core.Services.MovementQuery$$GetExtraReachableTiles(defaultReachableTiles,
    pathfinderType, unit, rangeBonus)` lit `ExtraRange` et `ExtraRangeCondition` -- il ajoute des
    tuiles SUPPLEMENTAIRES, une par une, chacune devant satisfaire la condition.

Le seul implementeur du hook dans tout le build est
`IdunBattle.Entities.Effects.Loki.AdrenalGlandsEffect$$CreateRangeBonusForMovement`
(`Trigger = null`, `ExtraRange = GetNumberConstant(0xe = extraMovement)`, `ReduceRange = null`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class RangeBonus:
    """`IdunBattle.Core.Services.RangeBonus` -- ce que `MovementQuery` consomme.

    `extra_range_condition(pos) -> bool` est le `Func<ITile, bool>` natif, en domaine POSITION
    `(col, row)` (le port n'a pas d'objet tuile) ; `None` = aucune condition, TOUTE tuile extra
    est retenue."""
    extra_range: int = 0
    extra_range_condition: Optional[Callable[[Any], bool]] = None
    reduce_range: Optional[int] = None


@dataclass(frozen=True)
class EffectRangeBonus:
    """`EffectRangeBonus` -- ce que le slot `CreateRangeBonusForMovement` d'un effet rend.
    `trigger` est le gate que `BaseEffect$$RangeBonusForMovement` evalue avant conversion."""
    trigger: Optional[Callable[[Any], bool]] = None
    extra_range: int = 0
    extra_range_condition: Optional[Callable[[Any], bool]] = None
    reduce_range: Optional[int] = None


@dataclass(frozen=True)
class MovementBonusContext:
    """Ce que le port doit passer a `CreateRangeBonusForMovement`, la ou le natif passe le seul
    `owner` (l'effet natif, lui, porte deja `IBattleQuery` en `+0x50` et l'etat en `+0x58` --
    champs que le port n'a pas sur ses instances d'effet).

    `board` peut etre `None` : la condition de mouvement est alors INEVALUABLE et l'effet rend
    `None` (aucun bonus), jamais un bonus sans condition -- qui serait PERMISSIF."""
    state: Any = None
    board: Any = None
    unit_id: Optional[int] = None
    occupants: Optional[dict] = None
    moving_team: Any = None
