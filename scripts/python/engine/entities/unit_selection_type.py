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


def matches_unit_selection_type(selection_type, *, is_unit: bool | None = True,
                                alive: bool | None = None,
                                targetable: bool | None = None) -> bool:
    """FOYER du mirror d'`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`, decompile
    relu en entier sur `rnca9r7q6c` (#419-r1-tr10-r4) :

        if (unit == null)                    return false;
        if (!<IsUnit>(unit))                 return false;
        if (selectionType == OnlyAlive)               return IsAlive(unit, state);
        if (selectionType == OnlyTargetable)          return !HasFlag(unit, UnitFlag.Untargetable);
        if (selectionType == OnlyAliveAndTargetable)  return IsAlive(unit, state)
                                                             && !HasFlag(unit, Untargetable);
        return true;                                  // Any -- et TOUTE autre valeur

    ⚠ La branche par defaut est `true`, pas `false` : une valeur hors des quatre membres passe le
    filtre. C'est ce que fait le `switch` natif (les trois tests sont des comparaisons successives,
    et le chemin qui n'en satisfait aucune saute au `return true`). Ne pas la durcir.

    TRI-ETAT sur les deux predicats -- `None` = **PAS MESURE**, jamais rabattu sur un booleen :
    la clause correspondante DEGRADE EN VRAI. Un `False` invente ecarterait une unite que le natif
    compte (degradation RESTRICTIVE silencieuse), et c'est exactement la faute que la convention
    `turns_started` / `turns_finished` de `playbook/scene.py` nomme. C'est ce qui rend ce foyer
    utilisable AVANT que le canal `Untargetable` existe partout : il se comporte alors comme le port
    d'avant (volet `IsAlive` seul), sans mentir sur ce qu'il n'a pas lu.

    `is_unit` : mirror du `<IsUnit>(unit)` qui precede le switch. Les appelants qui itere DEJA une
    liste d'unites (tout `scene.units`) passent le defaut `True` -- ce n'est pas un raccourci, c'est
    que leur substrat ne contient que des unites."""
    if is_unit is False:
        return False
    st = int(selection_type)
    if st == int(UnitSelectionType.OnlyAlive):
        return alive is not False
    if st == int(UnitSelectionType.OnlyTargetable):
        return targetable is not False
    if st == int(UnitSelectionType.OnlyAliveAndTargetable):
        return alive is not False and targetable is not False
    return True                                       # `Any`, et toute valeur hors enum


__all__ = ["UnitSelectionType", "matches_unit_selection_type"]
