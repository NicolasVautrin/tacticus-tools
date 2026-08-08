"""Mirror de `IdunBattle.Entities.Enum.UnitSelectionType` + le predicat qui le LIT.

Le 3e argument de la resolution d'entites du DSL : `IdunBattle.DSL.TargetsSelector$$
SelectUniqueUnits(entities, selectionType)` (et son jumeau `$$SelectAllUnits`) appelle
`IdunBattle.DSL.TargetsSelector$$SelectUnit(entity, selectionType)` PAR ELEMENT, qui termine par

    return UnitExtensions.MatchesUnitSelectionType(entity, selectionType, this.<+0x10 = state>)
             ? entity : null;

C'est donc un FILTRE de la resolution, applique a CHAQUE entite qu'un selecteur enumere -- pas un
parametre decoratif. `IdunBattleLogic.Entities.DSLSelectors` le passe explicitement a la plupart de
ses factories (`Friends(this, of, entities, 3)`, `UnitsWithoutTrait(this, source, trait, 3)`,
`Units(tiles, unique, 3)`, ...).

`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` -- MIRROR 1:1 du decompile :

    if (unit == null)                       return false;
    if (GetEntityType(unit) != Unit)        return false;      // slot 1 de l'entite
    switch (selectionType) {
      case 1: return IsAlive(unit, state);                                       // OnlyAlive
      case 2: return !HasFlag(unit, 0x11);                                       // OnlyTargetable
      case 3: return IsAlive(unit, state) && !HasFlag(unit, 0x11);   // OnlyAliveAndTargetable
      default: return true;                                                      // Any (0)
    }

Le `0x11` est `UnitFlag.Untargetable` = 17 (QUALIFIE : 17 nomme autre chose dans les autres enums).

⚠ **CE FILTRE MORD, ET IL A ETE MESURE** (#585). Une unite en DEEP STRIKE
(`TeleportStrike_TeleportingIn`) porte `UnitFlag.Untargetable` : sur `MC1_67 / 777`,
`spaceRockfist` est un ami MELEE non-Summon, donc RETENU par tous les autres filtres de
`WarHowlAbility$$OtherBuffTargets` -- et le natif ne le buffe PAS au tour 1, puis LE BUFFE apres
son atterrissage. C'est ce `selectionType = 3` qui fait la difference, rien d'autre. Un port sans
lui sur-buffe en silence.

Ordinaux LUS dans `data/symbols/<build>/frida/enums.tsv` :
`IdunBattle.Entities.Enum.UnitSelectionType  0=Any,1=OnlyAlive,2=OnlyTargetable,3=OnlyAliveAndTargetable`.
"""
from __future__ import annotations

from enum import IntEnum

from .unit_flag import UnitFlag


class UnitSelectionType(IntEnum):
    Any = 0
    OnlyAlive = 1
    OnlyTargetable = 2
    OnlyAliveAndTargetable = 3


def matches_unit_selection_type(unit, selection_type, has_unit_flag=None) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType(unit, selectionType, state)`.

    `unit` = le dict d'unite du contexte DSL (`alive` / `hp` portent l'`IsAlive` du port ;
    la branche `GetEntityType != Unit` n'a pas de contrepartie -- une entite-TUILE n'entre jamais
    dans un selecteur unit-domain cote port, et `SelectUnit` l'aurait deja convertie).

    `has_unit_flag` = l'accesseur `ctx.has_unit_flag(unit, flag)` (mirror
    `IdunBattle.Entities.Components.UnitFlagsComponent$$Has`). **ABSENT -> le volet TARGETABLE ne
    se prononce PAS et laisse passer** : une non-mesure ne fabrique pas un refus (meme regle que
    `ctx.has_trait` absent -> trait absent). Le volet ALIVE, lui, est toujours evaluable.

    `selection_type` None ou hors {1, 2, 3} -> `True` (la branche `default` du natif, qui couvre
    `Any = 0` ET toute valeur inconnue : le `switch` decompile ne teste que 1, 2 et 3)."""
    if not isinstance(unit, dict):
        return False                                    # `unit == null` / entite non resolue
    try:
        st = int(selection_type)
    except (TypeError, ValueError):
        return True                                     # branche `default`
    if st not in (int(UnitSelectionType.OnlyAlive), int(UnitSelectionType.OnlyTargetable),
                  int(UnitSelectionType.OnlyAliveAndTargetable)):
        return True                                     # `Any` et toute valeur inconnue
    if st in (int(UnitSelectionType.OnlyAlive), int(UnitSelectionType.OnlyAliveAndTargetable)):
        # `IdunBattle.Entities.UnitExtensions$$IsAlive` cote port : le meme predicat que
        # `AllAliveUnits` (flag `Dead` + PV), c.-a-d. « cette unite est SUR LE BOARD ».
        if not (bool(unit.get("alive", True)) and (unit.get("hp") or 0) > 0):
            return False
    if st in (int(UnitSelectionType.OnlyTargetable),
              int(UnitSelectionType.OnlyAliveAndTargetable)):
        if has_unit_flag is None:
            return True                                 # accesseur non cable -> aucun refus invente
        return not bool(has_unit_flag(unit, int(UnitFlag.Untargetable)))     # !HasFlag(0x11)
    return True
