"""`UnitSelectionType` -- le filtre que TOUT selecteur d'unite applique a sa sortie
(`IdunBattle.Entities.Enum.UnitSelectionType`).

C'est le 2e argument d'`IdunBattle.DSL.TargetsSelector$$SelectUnit` / `$$Select`, et le 3e de
`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent` / `DSLSelectors$$Enemies` / ... Le foyer qui le
consomme est `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType(unit, selectionType,
state)`, MIRROR de son decompile (build `rnca9r7q6c`) :

    if (unit == null)                       return false;
    if (!EntityExtensions.IsUnit(unit))     return false;
    if (selectionType == 1)                 return UnitExtensions.IsAlive(unit, state);
    if (selectionType == 2)                 return !UnitExtensions.HasFlag(unit, 0x11);
    if (selectionType == 3)                 return UnitExtensions.IsAlive(unit, state)
                                                   && !UnitExtensions.HasFlag(unit, 0x11);
    return true;                            // 0 = Any

`0x11` = `UnitFlag.Untargetable` (17) -- cf. `engine/entities/unit_flag.py`.

⚠ NE PAS LE CONFONDRE avec les autres << selection types >> du build : c'est CE type-la qui est
declare au 3e parametre d'`IsAdjacent` et au 2e de `SelectUnit`, et il n'a que QUATRE membres.

Le mirror entre au registre de `probe_313_enum_mirror_bijection.py` DANS LE COMMIT QUI LE CREE
(#524) -- cle LUE dans `data/symbols/<CURRENT>/frida/enums.tsv`.
"""
from __future__ import annotations

from enum import IntEnum


class UnitSelectionType(IntEnum):
    """`IdunBattle.Entities.Enum.UnitSelectionType` -- VERBATIM du build (4 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, cle
    `IdunBattle.Entities.Enum.UnitSelectionType`."""

    Any = 0
    OnlyAlive = 1
    OnlyTargetable = 2
    OnlyAliveAndTargetable = 3
