"""Modele de RESERVATION de tuile -- mirror des cinq `IdunBattle.Entities.TileExtensions$$*` qui
lisent et ecrivent le `Nullable<int>` `TileContentComponent+0x34` (#550-r1).

C'est l'etat que le port n'avait pas, et son absence rendait NO-OP quatre noeuds DSL
(`IdunBattleLogic.Entities.DSLBehaviors$$Reserve` / `$$RemoveReservation`) et INJOUABLE le gate
amont `IdunBattle.Operations.MoveUnitOperation$$IsPositionReservedForOtherUnit`
(#448-r1-r1-r2-r2-r1).

LE SUBSTRAT
-----------
Le natif porte la reservation SUR LA TUILE : `TileContentComponent.<+0x34> : Nullable<int>` (l'id de
l'unite qui a reserve). Le port n'a pas d'entite-tuile -- son plateau est un graphe
(`engine.entities.pathfinding.board.Board`) et l'occupation est DERIVEE des positions des unites.
La reservation, elle, N'EST PAS derivable : c'est un etat propre. Elle vit donc dans
`State.tile_reservations`, un `dict[(col,row) -> unit_id]` -- l'absence de cle EST le `Nullable`
vide. Le dict est cree paresseusement pour qu'un `State` charge par un vieux chemin n'ait rien a
declarer.

LES CINQ MIRRORS, LUS VERBATIM
------------------------------
    ReserveForUnit(tile, unit)              tile.content.<+0x34> = Nullable(unit.Id)
    RemoveReserveForUnit(tile, unit)        if (r.HasValue && r.Value == unit.Id) r = null
    IsTileReserved(tile)                    return r.HasValue
    IsTileReservedForUnit(tile, unit)       return unit != null && r.HasValue && r.Value == unit.Id
    IsTileReservedForOtherUnit(tile, allowedUnit)
                                            allowedUnit == null : return r.HasValue
                                            sinon                : return !(r.HasValue && r.Value == allowedUnit.Id)

et l'agregateur du `BattleQuery`, surcharge LISTE (celle que prend le gate de mouvement) :

    BattleQuery.IsTileReservedForAnotherUnit(tiles, unit)
        foreach (tile in tiles)
            if (IsTileReserved(tile) && !IsTileReservedForUnit(tile, unit)) return true
        return false

⚠ **`IsTileReservedForOtherUnit` N'EST PAS `IsTileReservedForAnotherUnit`, et l'ecart n'est PAS un
detail de nommage.** Sur une tuile NON reservee et un `allowedUnit` NON nul, la premiere rend
**VRAI** (le decompile calcule litteralement `!(HasValue && Value == allowedUnit.Id)`, avec un
raccourci `if (!HasValue) return true` qui CONFIRME la formule au lieu de la contredire), la seconde
rend FAUX. Les deux polarites sont donc opposees sur le cas le plus courant. C'est LU, pas deduit,
et ca a une consequence structurelle enorme cote `CanAddUnit` -- voir le bloc suivant.

⚠ **CONSEQUENCE : `TileExtensions$$CanAddUnitFromAbility` EXIGE la reservation quand son `parent`
est non nul.** Le decompile :

    CanAddUnitFromAbility(tile, state, parent, allowSteppable) {
        if (!IsFreeTile(tile, state, allowSteppable, allowTemporaryTile: false, allowAnyUnit: false))
            return false;
        if (IsTileReservedForOtherUnit(tile, parent))   return false;
        if (IsTilePendingDrafting(tile, state, null))   return false;
        return true;
    }

et `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` resout `parent` par un SELECTEUR
(`this.<+0x20>.SelectUnit(entities, 3)`), donc non nul des que l'arbre en passe un. Avec un `parent`
non nul et AUCUNE reservation, `IsTileReservedForOtherUnit` rend vrai -> **`CanAddUnit` rend un set
VIDE**. C'est exactement pourquoi l'arbre de `1121 ItItches` place un `Reserve(Owner, targetTiles)`
AVANT son `Foreach(CanAddUnit(targetTiles, Owner, ...))` : le `Reserve` est ce qui fait PASSER le
`CanAddUnit` qui suit. Le noeud n'est pas decoratif -- il est load-bearing.

⇒ le port de `CanAddUnit` (`engine/entities/selectors/tiles.py`) ne peut PAS ajouter
`IsTileReservedForOtherUnit` sans consommer ce modele-ci, et reciproquement il ne doit pas l'ajouter
sans lui : les deux omissions se compensent aujourd'hui. Residu explicite, cf. la case-doc.

CE QUI N'EST PAS ICI
--------------------
`IdunBattle.Entities.TileExtensions$$IsTilePendingDrafting` : la reservation de DRAFTING est un
autre etat (le `DraftingComponent` des joueurs, `comp.<+0x28>.<+0x2c>` = la tuile en attente), et le
runner n'a pas de phase de drafting. Non porte, et sa direction est dite dans
`operations/movement.py::_is_position_reserved_for_drafting`.
"""
from __future__ import annotations

from typing import Iterable, Optional

from ..state import State


def _table(state: State) -> dict:
    """Le `dict[(col,row) -> unit_id]` de l'etat, cree paresseusement.

    L'ABSENCE d'une cle est le `Nullable<int>` VIDE de `TileContentComponent+0x34` -- on ne stocke
    jamais `None` comme valeur, exactement comme le natif ne laisse jamais un `Nullable` « pose mais
    sans valeur »."""
    t = getattr(state, "tile_reservations", None)
    if t is None:
        t = {}
        state.tile_reservations = t
    return t


def _pos(tile) -> Optional[tuple]:
    """Normalise une tuile en `(col,row)`. `None` = pas de tuile (le `tile == null` natif, sur lequel
    les cinq extensions LEVENT ; le port refuse en rendant `None` plutot que d'exploser un tour)."""
    if tile is None:
        return None
    try:
        return (int(tile[0]), int(tile[1]))
    except (TypeError, IndexError, ValueError):
        return None


def reserve_for_unit(state: State, tile, unit_id) -> bool:
    """`IdunBattle.Entities.TileExtensions$$ReserveForUnit(tile, unit)` :

        tile.GetComponent<TileContentComponent>().<+0x34> = new Nullable<int>(unit.Id);

    ECRASE une reservation existante, quel qu'en soit le titulaire -- le natif n'a AUCUN gate ici.
    Rend « l'ecriture a eu lieu »."""
    p = _pos(tile)
    if p is None or unit_id is None:
        return False
    _table(state)[p] = int(unit_id)
    return True


def remove_reserve_for_unit(state: State, tile, unit_id) -> bool:
    """`IdunBattle.Entities.TileExtensions$$RemoveReserveForUnit(tile, unit)` :

        r = content.<+0x34>;
        if (r.HasValue && r.Value == unit.Id) content.<+0x34> = null;

    Le gate d'IDENTITE est LU : une unite ne peut pas liberer la reservation d'une AUTRE. Rend « la
    reservation a ete retiree »."""
    p = _pos(tile)
    if p is None or unit_id is None:
        return False
    t = _table(state)
    if t.get(p) != int(unit_id):
        return False
    del t[p]
    return True


def is_tile_reserved(state: State, tile) -> bool:
    """`IdunBattle.Entities.TileExtensions$$IsTileReserved(tile)` = `content.<+0x34>.HasValue`."""
    p = _pos(tile)
    return p is not None and p in _table(state)


def is_tile_reserved_for_unit(state: State, tile, unit_id) -> bool:
    """`IdunBattle.Entities.TileExtensions$$IsTileReservedForUnit(tile, unit)` :

        if (unit == null) return false;                      // le tout premier gate du decompile
        return r.HasValue && r.Value == unit.Id;
    """
    if unit_id is None:
        return False
    p = _pos(tile)
    return p is not None and _table(state).get(p) == int(unit_id)


def is_tile_reserved_for_other_unit(state: State, tile, allowed_unit_id) -> bool:
    """`IdunBattle.Entities.TileExtensions$$IsTileReservedForOtherUnit(tile, allowedUnit)` --
    MIRROR VERBATIM, polarite comprise (cf. l'avertissement en tete de module) :

        if (allowedUnit == null) return content.<+0x34>.HasValue;
        if (!content.<+0x34>.HasValue) return true;                      // raccourci du decompile
        return !(content.<+0x34>.HasValue && content.<+0x34>.Value == allowedUnit.Id);

    Les deux dernieres lignes disent la MEME chose : le raccourci n'est pas une exception, c'est la
    formule evaluee a `HasValue == false`. Un lecteur qui « corrigerait » ce retour en `false`
    casserait le seul consommateur natif, `$$CanAddUnitFromAbility`, dont le `Reserve` amont d'
    `ItItches` depend.

    AUCUN consommateur PORTE a ce jour -- c'est `CanAddUnit` (`entities/selectors/tiles.py`) qui
    l'appellerait, et il ne le fait pas encore. Presente ici pour que le couple
    reservation/`CanAddUnit` se porte d'un bloc le jour venu, et pour que le test de cette tranche
    puisse figer la polarite."""
    p = _pos(tile)
    if p is None:
        return False
    t = _table(state)
    if allowed_unit_id is None:
        return p in t                                     # branche `allowedUnit == null`
    return not (p in t and t[p] == int(allowed_unit_id))   # `!(HasValue && Value == allowedUnit.Id)`


def is_tile_reserved_for_another_unit(state: State, tiles: Iterable, unit_id) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsTileReservedForAnotherUnit(tiles, unit)` -- la
    surcharge LISTE (slot d'interface `0xa5`), celle que
    `IdunBattle.Operations.MoveUnitOperation$$IsPositionReservedForOtherUnit` appelle avec la
    `UnitPosition` de destination :

        foreach (var tile in tiles)
            if (TileExtensions.IsTileReserved(tile) &&
                !TileExtensions.IsTileReservedForUnit(tile, unit))
                return true;
        return false;

    Polarite SAINE (une tuile non reservee ne bloque personne), a la difference de son homonyme
    `TileExtensions$$IsTileReservedForOtherUnit`. La surcharge TUILE UNIQUE (`(tile, unit)`) calcule
    exactement le meme predicat sur un seul element : `IsTileReserved(tile) &&
    !IsTileReservedForUnit(tile, unit)`."""
    t = _table(state)
    if not t:
        return False                                       # aucune reservation posee : rien a lire
    uid = None if unit_id is None else int(unit_id)
    for tile in (tiles or ()):
        p = _pos(tile)
        if p is None or p not in t:
            continue                                       # `!IsTileReserved(tile)`
        if t[p] != uid:                                    # `!IsTileReservedForUnit(tile, unit)`
            return True
    return False


def clear_reservations(state: State) -> None:
    """Vide la table. AUCUN mirror natif -- outil de montage pour les tests, qui doivent pouvoir
    repartir d'un etat sans reservation sans reconstruire le `State`."""
    _table(state).clear()
