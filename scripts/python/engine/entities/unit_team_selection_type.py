"""Mirror de `IdunBattle.Entities.Enum.UnitTeamSelectionType`.

Le SELECTEUR D'EQUIPE que prennent les surcharges a trois arguments de la primitive d'amitie :

    IdunBattle.Core.Services.BattleQuery$$AreFriends(unit1, unit2, selectionType)
        -> IdunBattle.Entities.UnitExtensions$$IsFriend(unit1, unit2, selectionType, this.State)

`IdunBattle.Entities.UnitExtensions$$IsFriend` (surcharge a 4 arguments) branche sur cette valeur :

    if (selectionType == 0)  p = EntityExtensions.GetCurrentPlayer(...)    // ByCurrentTeam
    else if (== 1)           p = EntityExtensions.GetOriginalPlayer(...)   // ByOriginalTeam
    else                     return false;                                 // AUCUNE autre valeur

⚠ La surcharge a TROIS arguments (`IsFriend(unit, other, state)`) n'est PAS un cas a part : son
corps decompile est mot pour mot celui de la branche `== 0` ci-dessus (`GetCurrentPlayer` des deux
cotes, egalite des `playerId`). Autrement dit `AreFriends(a, b, ByCurrentTeam)` et `IsFriend(a, b)`
sont le MEME predicat -- ce qui rend REDONDANT le gate `AreFriends` du corps de
`MawClawsOfThyraxNonOwnerPlaybook`, deja garanti par le pre-gate d'`IterateAbilities`. Le port
mirrore quand meme le corps ; c'est la redondance qui est notee, pas elle qui est supprimee.

Ordinaux LUS dans `data/symbols/<build>/frida/enums.tsv` :
`IdunBattle.Entities.Enum.UnitTeamSelectionType  0=ByCurrentTeam,1=ByOriginalTeam`.
"""
from __future__ import annotations

from enum import IntEnum


class UnitTeamSelectionType(IntEnum):
    ByCurrentTeam = 0
    ByOriginalTeam = 1
