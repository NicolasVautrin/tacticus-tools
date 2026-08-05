"""`UnitFlag` -- les drapeaux per-unite (`IdunBattle.Entities.Enum.UnitFlag`).

Mirror 1:1 de l'enum natif, re-derivable de `data/symbols/<build>/frida/enums.tsv`.

CE QU'IL DESIGNE, ET COMMENT ON LE SAIT. C'est le type DECLARE du parametre `flag` de

    IdunBattle.Entities.UnitExtensions.HasFlag        (flag : IdunBattle.Entities.Enum.UnitFlag)
    IdunBattleLogic.Entities.DSLBehaviors.AddFlag     (flag : IdunBattle.Entities.Enum.UnitFlag)
    IdunBattleLogic.Entities.DSLSelectors.UnitsWithFlag / UnitsWithoutFlag
    IdunBattleLogic.Entities.DSLTriggers.HasFlag / DoesNotHaveFlag

LU dans la table des methodes du build (`frida/methods.tsv`), pas deduit d'un nom court.

⚠ CE SONT DES INDEX, PAS DES BITS. Les valeurs sont contigues (0..28, avec les trous 7 et 10)
et le natif les indexe dans `UnitFlagsComponent` -- un `IntFlag` ecrirait un masque et donnerait
`Overkilled | Fled == 8|9 == 9`, faux. D'ou `IntEnum`.

⚠ DEUX MEMBRES QUE LE PORT NOMMAIT AUTREMENT, et qui restent en litteral tant que la lecture
n'est pas faite : `AMBUSH_CONSUMED = 14` (natif 14 = `Resurrected`) et
`TURN_FINISHED_FORCED = 27` (natif 27 = `TurnTerminated`, que le port declarait
« hors enum dump »). Les renommer sans relire le decompile ecrirait un nom au jugement --
cf. `docs/rl/case-270r1r1r3-roles-derives.md`.
"""
from __future__ import annotations

from enum import IntEnum


class UnitFlag(IntEnum):
    """`IdunBattle.Entities.Enum.UnitFlag` -- VERBATIM du build (27 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, cle `IdunBattle.Entities.Enum.UnitFlag`.
    Sous garde de `probe_313_enum_mirror_bijection.py` (bijection exigee)."""

    Moved = 0
    ArrivedAtFinalTile = 1
    ActiveAbilityUsed = 2
    TurnFinished = 3
    NoActionAvailable = 4
    Automatic = 5
    Dead = 6
    Overkilled = 8
    Fled = 9
    PreventLoot = 11
    Teleported = 12
    PreventRevive = 13
    Resurrected = 14
    Downed = 15
    DamagedMachine = 16
    Untargetable = 17
    DisableTriggers = 18
    PreventOverkill = 19
    Revived = 20
    ForceRangedAttack = 21
    PreventResurrect = 22
    CanHealFullHealthUnits = 23
    CanRepairFullHealthUnits = 24
    Undisplaceable = 25
    Removed = 26
    TurnTerminated = 27
    IngoreRangedInMelee = 28
