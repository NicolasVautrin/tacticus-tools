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
    -> tout occupant ennemi compte.

    ⚠ `neighbours_native`, PAS `neighbours` -- et c'est MESURE, pas suppose. `IterateAdjacentTiles`
    lit la liste d'adjacence **STOCKEE sur la tuile** (`TileQuery$$IterateAdjacentTiles`), la ou le
    `Board` du port est monte en `adjacency="evenq"` (voisinage hexgeo RECALCULE, et symetrise).
    Sur `C1_74`, ou les deux vues du graphe different sur 32 tuiles (`#381-r3`), la version `evenq`
    rendait 34 tuiles contre 37 au natif ; la version native rend 37. Sur `C2_26`, `MC1_67` et
    `PVP_desert_04` les deux coincident."""
    for n in board.neighbours_native(int(tile_id)):
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
    dans Ghidra : un corps trivial (`return true`) est DEDUPLIQUE par IL2CPP et disparait des deux
    tables (cf. CLAUDE.md, « l'ABSENCE d'une methode dans les tables ne prouve RIEN »).

    ⚠ C'ETAIT une HYPOTHESE (`#381-r5`) faute de porteur confrontable. **CONFRONTE le 2026-08-01**
    (`#366-r1` tranche 3/3, `probe_366_r1_stormboyz_strike.py` front 2) : le passif `StormboyzStrike`
    a ete GREFFE sur des unites du pool (`catalog_inject.graft_passive_ability`), ce qui les met hors
    plateau sous l'effet 1140 -> pathfinder `StormboyzStrikeWalk/Fly` (8/9), pool BOARD-WIDE. Le pool
    natif (`aiMovableTiles`) coincide EXACTEMENT avec ce predicat permissif sur les TROIS montages
    ou la famille effective est bien `StormboyzStrike` :

        orksNob      / MC1_67 / 1 ennemi   natif 61 == true 61   (predicat TeleportStrike : 59)
        thousTzaangor/ C3_26  / 1 ennemi   natif 31 == true 31   (predicat TeleportStrike : 28)
        orksNob      / MC1_67 / 3 ennemis  natif 59 == true 59   (predicat TeleportStrike : 55)

    Le predicat concurrent le plus plausible (celui de `TeleportStrike`, « aucun ennemi non-Steppable
    adjacent ») est donc REFUTE dans les trois cas, et `return false` l'etait deja par construction.

    Les trois lignes ont ete RE-MESUREES apres `#403`/`#445` (`FlyPathfinder$$IsValidPathNode` passe
    de `walkable` a `!IsWall`, gate d'expansion #131 retire de la branche vol) : IDENTIQUES, `31/31`
    compris -- c'est justement `thousTzaangor` qui a la base FLY. Structurellement attendu et
    desormais mesure : pour une unite SANS TUILE le natif appelle `GetReachableTiles(start = NULL,
    ...)`, donc la moitie BASE du decorateur ne produit rien et le pool ne vient que d'ici.

    ⚠ PIEGE DE MESURE, vecu : un 4e montage (`bloodIntercessor`) rendait natif 28 / port 31 et se
    lisait comme une refutation. Ce greffon porte le trait `TeleportStrike`, donc l'effet
    `0x40b = 1035`, que `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit` teste
    AVANT `0x474` : son pathfinder n'etait pas celui de Stormboyz. Verifier la FAMILLE effective
    avant d'interpreter un ecart."""
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
    return any(int(n) in tt for n in board.neighbours_native(int(tile_id)))


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


def find_path(board, from_id, to_id) -> "list[int] | None":
    """`IdunBattle.Entities.Pathfinding.ATeleportPathfinder$$FindPath(unit, fromTile, toTile,
    useTeleporter)` -- l'OVERRIDE le plus radical du registre. Le decompile, en entier :

        var set = new OrderedSet<TileEntity>();
        set.Add(fromTile);
        set.Add(toTile);
        return set.ToList();

    Il **n'y a pas de pathfinding** : les HUIT types decores (6..13) rendent litteralement les
    deux extremites, sans jamais consulter le board. Confirme AU RUNTIME (`resolveVtableSlot`,
    build `rnca9r7q6c`) : `TeleportStrikePathfinder` idx 0x07 (`@+0x1a8`, le slot `FindPath`)
    pointe bien ce corps, et non `BasePathfinder$$FindPath`.

    CONSEQUENCE, mesuree (#448-r1-r1-r1-r1) : pour un porteur `TeleportStrike` -- et **3 des 5
    volants du pool en sont** (`bloodDante`, `bloodIntercessor`, `eldarAutarch`) --
    `MovementQuery$$GetConnectedPathTo` recoit `[from, to]` et recoud le saut par une BEELINE.
    Le compte de tuiles parcourues d'un tel porteur vaut donc la DISTANCE, quelle que soit la
    geometrie : ni les pas de marche, ni la longueur du detour de vol.

    L'`OrderedSet` DEDUPLIQUE : `from == to` rend une liste d'UN element (`Count - 1 == 0`)."""
    if from_id is None or to_id is None:
        return None
    src, dst = int(from_id), int(to_id)
    if board is not None and (src not in board.by_id or dst not in board.by_id):
        return None
    return [src] if src == dst else [src, dst]     # `OrderedSet` : pas de doublon
