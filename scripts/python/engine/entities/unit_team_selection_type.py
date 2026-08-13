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
from typing import Optional


class UnitTeamSelectionType(IntEnum):
    ByCurrentTeam = 0
    ByOriginalTeam = 1


def team_for_selection(unit, selection_type) -> Optional[int]:
    """FOYER du << quelle equipe lit-on ? >> -- mirror de la BIFURCATION d'
    `IdunBattle.Entities.UnitExtensions$$IsFriend(unit, other, selectionType, state)` (#963-r1) :

        if (selectionType == 0)  p = EntityExtensions.GetCurrentPlayer(unit, state);   // ByCurrentTeam
        else if (== 1)           p = EntityExtensions.GetOriginalPlayer(unit, state);  // ByOriginalTeam
        else                     return false;
        teamId = (p == null || p.<+0x20> == null) ? 0 : p.<+0x20>.<+0x24>;

    Cote port, l'ECS ne porte pas d'entite-PLAYER : `OwnerComponent` (cf. `runner/components.py`)
    tient `team`/`player` = le COURANT et `overridden_from` = le couple `(team, player)`
    D'ORIGINE, `None` quand aucun override n'est actif. L'equipe D'ORIGINE est donc
    `overridden_from[0]` s'il existe, sinon `team` -- ce que le substrat publie sous
    `originalTeam` (`runner/abilities/behaviours/context.py::_unit_dict`).

    ⚠ **`originalTeam` ABSENT n'est PAS `None` : c'est << ce substrat ne modelise pas la
    possession >>**, et la seule reponse qui n'invente rien est alors l'equipe COURANTE -- qui EST
    l'equipe d'origine tant qu'aucun `ChangeUnitOwnerOperation` n'a couru. C'est exactement le
    comportement d'avant #963-r1 pour ces substrats (decision/prediction), donc une degradation
    value-preserving et non une regression silencieuse.

    ⚠ **Une valeur HORS des deux membres rend `None`**, ce que les deux noeuds consommateurs
    (`AreFriends` / `AreEnemies`) traduisent en predicat FAUX -- le `return false` natif. Mesure du
    recensement de #963-r1 : aucun call-site natif ne passe autre chose que `0` ou `1`, donc cette
    branche est inerte ; elle est mirroree parce qu'elle EXISTE au decompile, pas parce qu'elle est
    atteinte.

    ⚠ Ce qui N'EST PAS mirrore ici, et qui est nomme plutot que devine : le natif rabat un joueur
    ABSENT sur `teamId = 0`, si bien que deux unites sans joueur y sont AMIES. Le port rend `None`,
    que les deux noeuds traduisent en FAUX des deux cotes. Aucun dict d'unite du port ne sort sans
    `team` (le substrat le pose depuis l'`OwnerComponent`), donc l'ecart n'a pas de regime -- il est
    ecrit pour ne pas se relire comme un mirror complet."""
    if not isinstance(unit, dict):
        return None
    st = int(selection_type)
    if st == int(UnitTeamSelectionType.ByCurrentTeam):
        return unit.get("team")
    if st == int(UnitTeamSelectionType.ByOriginalTeam):
        orig = unit.get("originalTeam")
        return unit.get("team") if orig is None else orig
    return None


__all__ = ["UnitTeamSelectionType", "team_for_selection"]
