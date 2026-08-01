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
compatible avec la mesure (`C2_26` : 41 tuiles LIBRES du plateau, pas les 5 occupees).

RESIDUS NOMMES (tous PERMISSIFS : le port peut sur-atteindre, jamais l'inverse)
  * `IsTemporary` : aucun canal offline (meme residu que `MovableTilesInRange` / `CanAddUnit`) ;
  * le trait `Steppable` (0x1b) d'`IsEmptyOrSteppable` ET du `Count(e => !IsSteppable(e))` des
    predicats ci-dessous : meme CONVENTION que partout ailleurs dans le port -- une tuile occupee
    est retiree, un occupant ennemi compte ;
  * `checkFog` d'`IsWalkable` (`tile+0x20 [+0x40] == 0`) : le `boardGraph` capte ne porte pas le
    brouillard -> `board.walkable` seul ;
  * les DEUX gardes virtuelles (`vslot 9` et `vslot 10` de la vtable de `ATeleportPathfinder`,
    lues `(**(code**)(*(longlong*)this + 0x1c8))` et `+0x1d8`) : leurs corps sont TRIVIAUX donc
    DEDUPLIQUES par IL2CPP -- ni la table de symboles ni Ghidra ne les nomment (cf. CLAUDE.md,
    « l'ABSENCE d'une methode dans les tables ne prouve RIEN »). Les deux filtres qu'elles gardent
    (power-up, et un booleen `+0x2e` d'un composant de tuile non identifie) ne sont donc PAS
    portes : on ne recopie pas un nom invente. MESURE : sur `C2_26`/38104 et `MC1_67`/38104, une
    fois les trois filtres portes appliques, le port rend EXACTEMENT le pool natif -- ces deux
    gardes n'ont retire aucune tuile sur les configurations confrontees.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional


def _has_adjacent_enemy(tile_id: int, board, occupants: dict, moving_team) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(from, unit, ignoreSteppables)`,
    lu au decompile :

        var player = unit.GetComponent<OwnerComponent>().CurrentPlayerEntityId -> <entite joueur>;
        var tiles  = IterateAdjacentTiles(from, onlyEmptyOrSteppable: false,
                                          onlyWalkableTiles: true, allowTemporary: true);
        return GetUnitsOnTiles(tiles, friendsOf: null, enemiesOf: player, ignoreSteppables);

    Les DEUX appelants (`TeleportStrikePathfinder` et `FearOfTheUnseenPathfinder`) en prennent le
    `Count(e => !UnitExtensions.IsSteppable(e))` et exigent `== 0` : « aucun ennemi NON-Steppable
    sur une tuile adjacente ». Le port compare des TEAM la ou le natif compare des joueurs (meme
    convention que `WalkPathfinder$$UnitIsBlockedByEnemyUnit`), et n'a pas de substrat `Steppable`
    -> tout occupant ennemi compte."""
    for n in board.neighbours(int(tile_id)):
        occ = occupants.get(int(n))
        if occ is not None and moving_team is not None and occ != moving_team:
            return True
    return False


def is_valid_teleport_tile_teleport_strike(tile_id: int, board, occupants: dict,
                                           moving_team) -> bool:
    """`IdunBattle.Entities.Pathfinding.TeleportStrikePathfinder$$IsValidTeleportTile(unit, tile)`,
    lu au decompile :

        return _battleQuery.GetAdjacentEnemies(tile, unit, ignoreSteppables: false)
                           .Count(e => !UnitExtensions.IsSteppable(e)) == 0;

    (le lambda est `TeleportStrikePathfinder.<>c.<IsValidTeleportTile>b__1_0` = `!IsSteppable(e)`)

    ⇒ **on ne se pose PAS a cote d'un ennemi**. C'est ce predicat, et lui seul, qui explique
    l'ecart mesure entre les 41 tuiles libres de `C2_26` et les 35 du pool natif : les six
    manquantes sont EXACTEMENT celles a distance 1 d'une unite adverse."""
    return not _has_adjacent_enemy(tile_id, board, occupants, moving_team)


def is_valid_teleport_tile_fear_of_the_unseen(tile_id: int, board, occupants: dict, moving_team,
                                              synapse_tiles: Optional[set] = None) -> bool:
    """`IdunBattle.Entities.Pathfinding.FearOfTheUnseenPathfinder$$IsValidTeleportTile(unit, tile)`
    -- meme coeur que `TeleportStrike`, avec DEUX echappatoires en plus :

        if (TileExtensions.IsTallGrass(tile))                                    return true;
        if (GetAdjacentEnemies(tile, unit, false).Count(e => !IsSteppable(e)) == 0) return true;
        var player = EntityExtensions.GetOriginalPlayer(unit, state);
        return <unites du player>.Any(e => EntityExtensions.HasEffect(e, state, 0x41c, 0)
                   && GetSurroundingTiles(e, 2, onlyEmptyOrSteppable: true, onlyWalkable: true,
                                          onlyMovable: false, includeCenter: true).Contains(tile));

    `0x41c` = `Synapse_Effect` (1052) : un Tyranide peut se poser au contact d'un ennemi tant qu'il
    reste dans la BULLE SYNAPSE d'un allie (rayon 2, centre inclus). `synapse_tiles` = cette union,
    calculee par l'appelant ; `None` = NON MESURE -> troisieme branche inerte (degradation
    RESTRICTIVE et nommee, cf. `pathfinders._teleport_predicate`).

    `IsTallGrass` = `TileExtensions$$IsTileWithId(tile, <TallGrass>)` : lisible sur le
    `tileDefId` du `boardGraph` -- et INERTE sur les 779 boards dumpes, qui n'en portent aucune."""
    if board.tile_def_id(int(tile_id)) == "TallGrass":
        return True
    if not _has_adjacent_enemy(tile_id, board, occupants, moving_team):
        return True
    return synapse_tiles is not None and int(tile_id) in synapse_tiles


def is_valid_teleport_tile_stormboyz(tile_id: int, board, occupants: dict, moving_team) -> bool:
    """`IdunBattle.Entities.Pathfinding.StormboyzStrikePathfinder` -- la classe EXISTE
    (`data/symbols/<build>/frida/classes.tsv` : base `ATeleportPathfinder`, 48 octets, exactement
    comme ses trois soeurs) mais **AUCUNE de ses methodes n'est nommee**, ni dans les tables ni
    dans Ghidra.

    ⚠ HYPOTHESE, ecrite comme telle : `IsValidTeleportTile` est un slot virtuel APPELE
    (`FindTilesReachableByTeleport` l'invoque sans garde), donc la classe le fournit forcement ;
    un corps trivial (`return true`) est DEDUPLIQUE par IL2CPP et disparait des deux tables. Le
    seul autre corps trivial possible (`return false`) rendrait le pool de teleport TOUJOURS vide,
    c'est-a-dire ferait de `StormboyzStrikeWalk/Fly` un synonyme exact de `Walk`/`Fly` -- ce que la
    presence meme des types 8/9 dans l'enum contredit.

    NON CONFRONTE : le seul porteur de `StormboyzStrike` est `orksNpc6Stormboy` (npc, hors pool)."""
    return True


def is_valid_teleport_tile_titanhammer(tile_id: int, board, target_tiles: Optional[set]) -> bool:
    """`IdunBattle.Entities.Pathfinding.TitanhammerSquadPathfinder$$IsValidTeleportTile(unit,
    tile)`, lu au decompile :

        if (IsValidTitanhammerSquadTargetTile(unit, tile))  return true;
        foreach (t in _battleQuery.GetAdjacentTiles(tile, onlyEmptyOrSteppable: false,
                                                    onlyWalkableTiles: true,
                                                    allowTemporary: false))
            if (IsValidTitanhammerSquadTargetTile(unit, t)) return true;
        return false;

    et `TitanhammerSquadPathfinder$$IsValidTitanhammerSquadTargetTile(unit, tile)` :

        var eff = EntityExtensions.GetOwnedEffect(tile, state, 0x623);   // TitanhammerSquad_TargetTile
        return eff != null
            && EntityExtensions.GetEffectSourceUnit(eff, state) is u
            && UnitExtensions.IsFriend(u, unit, state);

    ⇒ SEUL des quatre a etre RESTRICTIF : on ne se pose que sur la zone MARQUEE par un allie (ou
    a cote). `target_tiles` = les tuiles marquees ; `None` = NON MESURE -> predicat toujours FAUX,
    donc pool de teleport VIDE (degradation RESTRICTIVE et nommee, jamais un pool invente).

    NON CONFRONTE : le seul porteur de `TitanhammerSquad` est `astarLysander` (lineup, HORS pool
    du seed BC courant -- injectable par `catalog_inject`, cf. `case-92` §6)."""
    if target_tiles is None:
        return False
    tt = {int(t) for t in target_tiles}
    if int(tile_id) in tt:
        return True
    return any(int(n) in tt for n in board.neighbours(int(tile_id)))


def find_tiles_reachable_by_teleport(
    board, occupants: dict,
    is_valid_teleport_tile: Optional[Callable[[int], bool]] = None,
) -> set:
    """`IdunBattle.Entities.Pathfinding.ATeleportPathfinder$$FindTilesReachableByTeleport(unit)` --
    mirror des filtres alimentables offline (cf. l'en-tete du module pour les residus).

    `is_valid_teleport_tile(tile_id) -> bool` = le slot virtuel de la SOUS-CLASSE (vslot 11), ferme
    par l'appelant sur l'unite. `None` -> filtre absent. Rend un `set` d'ids de tuile ; l'ordre du
    natif (celui du `tileQuery`) n'est pas observable en aval -- `AnyOrFillMoveableTiles` verse
    dans un `OrderedSet` que le port modelise en `set`, et les consommateurs trient
    (`MovableTilesInRange`) ou lisent par appartenance."""
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
