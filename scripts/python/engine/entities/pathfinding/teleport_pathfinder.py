"""`IdunBattle.Entities.Pathfinding.ATeleportPathfinder` et ses QUATRE sous-classes -- le
pathfinder d'une unite « qui descend du ciel » (residu `#381-r5`).

CE N'EST PAS UN PATHFINDER DE PLUS : c'est un **DECORATEUR**. `Pathfinders$$.ctor` le construit
avec un pathfinder de BASE en argument (`<X>Pathfinder..ctor(basePathfinder:IPathfinder)`), et
`ATeleportPathfinder$$IterateReachableTiles` -- lu au decompile, iterateur
`<IterateReachableTiles>d__11$$MoveNext` -- vaut EXACTEMENT :

    foreach (t in _base.IterateReachableTiles(startTile, depth, unit))  yield return t;   // slot 2
    if (unit != null)
        foreach (t in FindTilesReachableByTeleport(unit))               yield return t;

⇒ le pool rendu est l'UNION « ce que la marche/le vol atteint en `depth` pas » **ET** un pool
BOARD-WIDE qui ne depend NI du start NI de la portee. C'est pour ca que le natif rend 35 tuiles
la ou le port en rendait 9 (`C2_26`, seed 38104, `overrideRange` 2, `tyranDeathleaper` /
`bloodIntercessor` sous `TeleportStrike_TeleportingIn`).

Les deux autres slots de l'interface sont DELEGUES ou triviaux :
  * `ATeleportPathfinder$$IsValidContinuePathTile` = `_base.IsValidContinuePathTile(unit, tile)`
    (appel du slot 4 sur `this+0x28`) -- le gate d'expansion #131 reste donc celui de la BASE ;
  * `ATeleportPathfinder$$FindPath` = `OrderedSet{fromTile, toTile}.ToList()` : la teleportation
    n'a pas de chemin, juste un depart et une arrivee. NON porte ici (le port n'a pas de
    consommateur de chemin sous mouvement special).

`FindTilesReachableByTeleport(unit)`, mirror du decompile
---------------------------------------------------------
    var tiles = _tileQuery.<slot 0>();                       // toutes les tuiles du plateau
    tiles.RemoveAll(t => !TileExtensions.IsEmptyOrSteppable(t, state));     // b__0
    tiles.RemoveAll(t => !TileExtensions.IsWalkable(t, checkFog: true));    // b__14_1
    tiles.RemoveAll(t =>  TileExtensions.IsTemporary(t));                   // b__14_2
    if (!<vslot 10>) tiles.RemoveAll(t => UnitExtensions.GetUnit(t, state)?.IsPowerUp() == true);
    tiles.RemoveAll(t => !IsValidTeleportTile(unit, t));                    // b__4, vslot 11
    if (!<vslot  9>) tiles.RemoveAll(t => <composant de tuile>+0x2e);       // b__14_5
    return tiles.ToList();

`RemoveAll` (et non `Where`) est la lecture qui rend le SENS des predicats coherent -- ils sont
tous ecrits en NEGATIF (`!IsEmptyOrSteppable`, `!IsWalkable`, `IsTemporary`) -- et c'est la seule
compatible avec la mesure (35 tuiles = les tuiles LIBRES du plateau, pas les 5 occupees).

RESIDUS NOMMES (tous PERMISSIFS : le port peut sur-atteindre, jamais l'inverse)
  * `IsTemporary` : aucun canal offline (meme residu que `MovableTilesInRange` / `CanAddUnit`) ;
  * le trait `Steppable` (0x1b) d'`IsEmptyOrSteppable` : meme CONVENTION que partout ailleurs
    dans le port (`walk_pathfinder`, `CanAddUnit`) -- une tuile occupee est retiree ;
  * `checkFog` d'`IsWalkable` (`tile+0x20 [+0x40] == 0`) : le `boardGraph` capte ne porte pas le
    brouillard -> `board.walkable` seul ;
  * les DEUX gardes virtuelles (`vslot 9` et `vslot 10` de la vtable de `ATeleportPathfinder`,
    lues `(**(code**)(*(longlong*)this + 0x1c8))` et `+0x1d8`) : leurs corps sont TRIVIAUX donc
    DEDUPLIQUES par IL2CPP -- ni la table de symboles ni Ghidra ne les nomment (cf. CLAUDE.md,
    « l'ABSENCE d'une methode dans les tables ne prouve RIEN »). Les deux filtres qu'elles gardent
    (power-up, et un booleen `+0x2e` d'un composant de tuile non identifie) ne sont donc PAS
    portes : on ne recopie pas un nom invente.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional


def is_valid_teleport_tile_teleport_strike(tile_id: int, occupants: dict) -> bool:
    """`IdunBattle.Entities.Pathfinding.TeleportStrikePathfinder$$IsValidTeleportTile(unit, tile)`,
    lu au decompile :

        return _battleQuery.<slot 0x7f>(tile, unit, false)
                           .Count(e => !UnitExtensions.IsSteppable(e)) == 0;

    (le lambda `TeleportStrikePathfinder.<>c.<IsValidTeleportTile>b__1_0` = `!IsSteppable(e)`)

    = « aucune entite NON-Steppable ne se trouve sur la tuile ». Cote port, `occupants` est la
    seule lecture d'occupation disponible et le trait `Steppable` n'est modelise nulle part : le
    predicat se rabat donc sur « tuile libre », soit exactement le meme verdict que le filtre
    `IsEmptyOrSteppable` deja applique en amont. Il est ecrit tel quel pour que la structure du
    natif reste lisible -- et pour qu'un futur substrat `Steppable` n'ait qu'un seul point a
    changer."""
    return occupants.get(int(tile_id)) is None


def is_valid_teleport_tile_stormboyz(tile_id: int, occupants: dict) -> bool:
    """`IdunBattle.Entities.Pathfinding.StormboyzStrikePathfinder` -- la classe EXISTE
    (`data/symbols/<build>/frida/classes.tsv` : `StormboyzStrikePathfinder`, base
    `ATeleportPathfinder`, 48 octets, exactement comme ses trois soeurs) mais **AUCUNE de ses
    methodes n'est nommee** dans les tables ni dans Ghidra.

    ⚠ HYPOTHESE, ecrite comme telle : `IsValidTeleportTile` est un slot virtuel APPELE
    (`FindTilesReachableByTeleport` l'invoque sans garde), donc la classe le fournit forcement ;
    un corps trivial (`return true`) est DEDUPLIQUE par IL2CPP et disparait des deux tables. Le
    seul autre corps trivial possible (`return false`) rendrait le pool de teleport TOUJOURS vide,
    c'est-a-dire ferait de `StormboyzStrikeWalk/Fly` un synonyme exact de `Walk`/`Fly` -- ce que la
    presence meme des types 8/9 dans l'enum contredit.

    NON CONFRONTE : le seul porteur de `StormboyzStrike` est `orksNpc6Stormboy` (npc), hors pool."""
    return True


def find_tiles_reachable_by_teleport(
    board, occupants: dict,
    is_valid_teleport_tile: Optional[Callable[[int], bool]] = None,
) -> set:
    """`IdunBattle.Entities.Pathfinding.ATeleportPathfinder$$FindTilesReachableByTeleport(unit)` --
    mirror des filtres alimentables offline (cf. l'en-tete du module pour les residus).

    `is_valid_teleport_tile(tile_id) -> bool` = le slot virtuel de la SOUS-CLASSE, ferme par
    l'appelant sur l'unite. `None` -> filtre absent (dégradation PERMISSIVE nommee, cf.
    `pathfinders.reachable_tiles`). Rend un `set` d'ids de tuile ; l'ordre du natif (celui du
    `tileQuery`) n'est pas observable en aval -- `AnyOrFillMoveableTiles` verse dans un
    `OrderedSet` que le port modelise en `set`, et les consommateurs trient (`MovableTilesInRange`)
    ou lisent par appartenance."""
    if board is None:
        return set()
    out = set()
    for tid in board.by_id:
        tid = int(tid)
        if occupants.get(tid) is not None:          # `!IsEmptyOrSteppable(tile, state)`
            continue
        if not board.walkable(tid):                 # `!IsWalkable(tile, checkFog: true)`
            continue
        if is_valid_teleport_tile is not None and not is_valid_teleport_tile(tid):
            continue                                # `!IsValidTeleportTile(unit, tile)` (vslot 11)
        out.add(tid)
    return out


def iterate_reachable_tiles(base_visited: Iterable[int], base_stop: Iterable[int],
                            teleport_tiles: Iterable[int]) -> tuple[set, set]:
    """`ATeleportPathfinder$$IterateReachableTiles` = `base` PUIS `FindTilesReachableByTeleport`.

    Le port rend le couple `(visited, stop)` de `walk_pathfinder.get_movable_positions` (le
    `visited` sert au seul cas `ignoreUnitsOnTiles`). Les tuiles de teleport entrent dans les DEUX :
    elles sont deja LIBRES par construction (filtre `IsEmptyOrSteppable`), donc le
    `RemoveAll(t => !IsMovableTile(...))` que `MovementQuery$$AnyOrFillMoveableTiles` applique
    ensuite ne les retire pas -- pas plus que la tuile de depart, qui porte l'unite et n'est donc
    jamais dans le pool de teleport."""
    visited = set(base_visited) | set(teleport_tiles)
    stop = set(base_stop) | set(teleport_tiles)
    return visited, stop
