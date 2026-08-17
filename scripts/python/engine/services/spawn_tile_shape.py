"""`IdunBattle.Entities.Selectors.ThreeUnitSpawnTileShapeSelector` — le PRODUCTEUR d'empreintes a
3 pieds, et la seule source de multi-hex dans le build `gqfc5mff6c`.

Chaine natif -> port :

    IdunBattleLogic.Entities.DSLSelectors$$ThreeTileUnitSpawnShape(inner)
        -> new ThreeUnitSpawnTileShapeSelector(inner, <IBattleQuery>, <state>)
    ThreeUnitSpawnTileShapeSelector$$Select(ctx)
        -> tile = inner.Select(ctx)            // = la TUILE CIBLE de l'ability = l'ANCRE
        -> tile == null ? new List<TileEntity>() : GetArea(tile)

XREFS EXHAUSTIVES de `ThreeTileUnitSpawnShape` (build gqfc5mff6c) : `AetherStrideAbility`
(`ExecuteBehaviour`, `GetDynamicInvalidTargetReason`, `GetTargetAreaTiles`) et `DutyEternalAbility`
(`ExecuteBehaviour`, `GetDynamicInvalidTargetReason`) — RIEN d'autre. Il n'existe AUCUN producteur
d'empreinte a 7 pieds dans ce build : les branches `7` de `MovementQuery` et de
`DislikeStartingTilesUtility` sont du code MORT ici (portees, non exercables).

ORDRE : `GetTilesInTriangleShape` construit un `HashSet{ancre, t1, t2}` puis `new List<>(hashSet)`
-> ordre d'INSERTION = **[ancre, t1, t2]**. `AddUnitOperation` fait ensuite un `AddFoot` par tuile
DANS CET ORDRE -> `feet[0] == ancre == la main tile` de l'unite spawnee. VALIDE LIVE (cast
`DutyEternal` sur MC1_67 en (2,1) -> `Unit_Foot_Tile_Id_1/2/3` = tuiles 31/32/41 = (2,1)/(2,2)/(3,2),
exactement la direction 1 predite par ce module).
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from ..battle_query import get_tiles_in_triangle_shape
from ..hex_corner import Corner   # type DECLARE du parametre `direction` (#270-r1-r1)

Pos = Tuple[int, int]

# `ThreeUnitSpawnTileShapeSelector$$GetArea` : la liste de directions ESSAYEES, dans cet ordre
# exact (litteral du decompile : Add(1), Add(0), Add(5), Add(4), Add(3), Add(2)). La PREMIERE
# direction dont l'aire passe `CorrectArea` gagne ; aucune -> liste VIDE.
# #270-r1-r1 : `Corner`, pas `Edge` -- ces directions sont passees a `get_tiles_in_triangle_shape`,
# mirror de `BattleQuery$$GetTilesInTriangleShape`, dont le parametre `direction` est DECLARE
# `IdunBattleLogic.Utils.Hex.Corner` (lu dans `frida/methods.tsv`). L'ORDRE est celui du decompile
# et il est OBSERVABLE (premiere aire valide gagne) -> le tuple reste un tuple.
DIRECTION_ORDER: Tuple[Corner, ...] = (Corner.NorthEast,   # 1
                                       Corner.NorthWest,   # 0
                                       Corner.SouthEast,   # 5
                                       Corner.SouthWest,   # 4
                                       Corner.East,        # 3
                                       Corner.West)        # 2


def correct_relationship_in_area(board, area: Sequence[Pos], tile: Pos) -> bool:
    """`ThreeUnitSpawnTileShapeSelector$$CorrectRelationshipInArea(area, tile)` — mirror :

        foreach (other in area) {
            if (other == tile) continue;
            if (!TileExtensions.IsNeighbourOf(other, tile)) return false;
            if (TileExtensions.GetElevationDifference(other, tile) != 0) return false;
        }
        return true;

    Note : le natif rend `false` des la PREMIERE non-voisine (break hors boucle) — donc « toutes
    les autres tuiles de l'aire sont voisines de `tile` ET a la MEME elevation »."""
    if board is None:
        return False
    tid = board.id_at(tile[0], tile[1])
    if tid is None:
        return False
    for other in area:
        if other == tile:
            continue
        oid = board.id_at(other[0], other[1])
        if oid is None or tid not in board.neighbours(oid):
            return False
        if board.elevation(oid) != board.elevation(tid):
            return False
    return True


def correct_area(board, occupied, area: Sequence[Pos]) -> bool:
    """`ThreeUnitSpawnTileShapeSelector$$CorrectArea(area)` — mirror :

        if (area.Count != 3) return false;
        foreach (tile in area) {
            if (TileExtensions.HasPowerup(tile, state)) return false;
            if (!TileExtensions.CanAddUnit(tile, state, true, false, false)) return false;
            if (!CorrectRelationshipInArea(area, tile)) return false;
        }
        return true;

    `CanAddUnit(tile, state, 1, 0, 0)` (`IdunBattle.Entities.TileExtensions$$CanAddUnit`) =
    tuile existante ET non bloquee ET non-mur (`TileComponent+0x40`) ET **vide** (le flag
    `allowSteppable=1` n'autorise un occupant que s'il porte le trait `Steppable`) ET **non
    temporaire** (`TileComponent+0x2c`, car `ignoreTemporary=0`).

    Offline : `occupied` = l'ensemble des positions OCCUPEES (TOUS les pieds de TOUTES les unites
    vivantes — cf. `State.occupied_positions`). `HasPowerup` n'a pas de source offline (le port ne
    modelise pas les power-ups de tuile) -> non teste, et c'est un ECART DOCUMENTE : il ne peut que
    rendre le port PLUS permissif sur un plateau qui porte des power-ups.
    La derogation `Steppable` n'est pas reproduite non plus (meme borne conservatrice que
    `engine.battle_query.can_add_unit`, qui la documente deja)."""
    area = list(area)
    if len(area) != 3 or board is None:
        return False
    occ = occupied or frozenset()
    for tile in area:
        t = board.tile_at(tile[0], tile[1])
        if t is None:
            return False
        if not t.get("walkable") or t.get("isWall") or t.get("isTemporary"):
            return False
        if (tile[0], tile[1]) in occ:
            return False
        if not correct_relationship_in_area(board, area, tile):
            return False
    return True


def get_area(board, occupied, anchor: Optional[Pos]) -> List[Pos]:
    """`ThreeUnitSpawnTileShapeSelector$$GetArea(tile)` — mirror :

        foreach (direction in [1, 0, 5, 4, 3, 2]) {
            area = battleQuery.GetTilesInTriangleShape(tile, direction);
            if (CorrectArea(area)) return area;
        }
        return new List<TileEntity>();       // aucune direction ne convient

    Renvoie l'empreinte a 3 pieds, ORDRE COMPRIS (`[ancre, t1, t2]`), ou `[]` si l'ancre ne porte
    aucune aire valide — auquel cas `DutyEternalAbility$$GetDynamicInvalidTargetReason` refuse la
    cible."""
    if anchor is None:
        return []
    for direction in DIRECTION_ORDER:
        area = get_tiles_in_triangle_shape(anchor, direction)
        if correct_area(board, occupied, area):
            return area
    return []


def get_area_direction(board, occupied, anchor: Optional[Pos]) -> Optional[int]:
    """La DIRECTION retenue par `get_area` (diagnostic / tests) — `None` si aucune ne convient."""
    if anchor is None:
        return None
    for direction in DIRECTION_ORDER:
        if correct_area(board, occupied, get_tiles_in_triangle_shape(anchor, direction)):
            return direction
    return None
