"""`EntityType` -- la nature d'une entite ECS (`IdunBattle.Entities.Enum.EntityType`).

Mirror 1:1 de l'enum natif, re-derivable de `data/symbols/<build>/frida/enums.tsv`.

CE QU'IL DESIGNE, ET COMMENT ON LE SAIT. C'est le type DECLARE du parametre `type` /
`entityType` de

    IdunBattle.Core.Entity..ctor                     (type : IdunBattle.Entities.Enum.EntityType)
    IdunBattle.Core.Services.EntitiesFactory.Build   (entityType : ...)
    IdunBattle.Core.Match.AddFactory                 (entityType : ...)

LU dans la table des methodes du build (`frida/methods.tsv`), pas deduit d'un nom court.
"""
from __future__ import annotations

from enum import IntEnum


class EntityType(IntEnum):
    """`IdunBattle.Entities.Enum.EntityType` -- VERBATIM du build (9 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, cle `IdunBattle.Entities.Enum.EntityType`.
    Sous garde de `probe_313_enum_mirror_bijection.py` (bijection exigee)."""

    Tile = 0
    Unit = 1
    Match = 2
    Effect = 3
    Player = 4
    UnitFoot = 5
    Machine = 6
    MachinePlatform = 7
    EnvironmentAbility = 8
