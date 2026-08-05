"""`SpawnSource` -- D'OU vient une unite qui entre en bataille.

Mirror 1:1 de `IdunBattle.Entities.Enum.SpawnSource`, re-derivable de
`data/symbols/<CURRENT>/frida/enums.tsv`.

CE QU'IL DESIGNE, ET COMMENT ON LE SAIT. C'est le parametre `source` de
`IdunBattle.Core.Services.StreamHelper$$GetAddUnitTags`, recopie tel quel dans le tag
`TagKey.Unit_SpawnSource` (ordinal 0x87) de chaque `Action=AddUnit` du flux de replay.

Confirmation sur le flux natif (C1_02, seed 777) : l'unite prededefinie posee par
`IdunBattle.Operations.SetupGameOperation$$AddPredefinedUnits` porte
`Tag=Unit_SpawnSource:1` (`InitialOperations`), et l'unite placee ensuite sous
`Group=User_PlaceUnit` porte `Tag=Unit_SpawnSource:5` (`Deployment`).
"""
from __future__ import annotations

from enum import IntEnum


class SpawnSource(IntEnum):
    """`IdunBattle.Entities.Enum.SpawnSource` -- VERBATIM du build (9 valeurs)."""

    Unknown = 0
    InitialOperations = 1
    Ability = 2
    AfterTurn = 3
    Drafting = 4
    Deployment = 5
    OceanWave = 6
    Replace = 7
    Room = 8
