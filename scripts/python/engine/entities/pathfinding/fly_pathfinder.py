"""FlyPathfinder — port FIDÈLE du pathfinder de vol natif
(`IdunBattle.Entities.Pathfinding.FlyPathfinder`). RE ghidra gqfc5mff6c.

Une unité « comme volante » (`IsLikeFlying`) utilise ce pathfinder au lieu du
WalkPathfinder. Sélection natif = dispatch virtuel de `IdunBattle.Core.Services.MovementQuery$$GetReachableTiles sur le pathfinder de l'unité.

PRÉDICAT « comme volante » (`IdunBattle.Entities.UnitExtensions$$IsLikeFlying`) :
    IsLikeFlying(u) = HasTrait(Flying=4) OR HasTrait(Burrow=19)
(les DEUX traits volent : Flying = vol classique, Burrow = terre/ressort ignorant
le terrain de surface). Les noms viennent de l'enum `UnitTrait` (4=Flying, 19=Burrow).

PRÉDICAT D'ARÊTE (`IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsValidPathNode`) — peut-on TRAVERSER
sur `to` : le natif ne teste QUE deux flags intrinsèques de la tuile
(`tile[+0x40]==0 AND tile[+0x41]==0` = non-unplayable ET non-mur ; `+0x41` confirmé
« mur » via `IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsAnyAdjacentTileWall`). **AUCUN test d'élévation,
AUCUN blocage par unité** (contrairement à Walk `IsWalkable + |Δelev|<=1 + !BlockedByEnemy`).
→ le vol ignore l'élévation ET traverse par-dessus alliés ET ennemis ; il ne peut pas
entrer sur un mur / une tuile injouable. Ces deux flags = `walkable=False` côté board
capté (cf. board.py « les MURS sont walkable=False »), donc l'arête fly = `board.walkable(to)`.

TUILE D'ARRÊT (`IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsValidFinalTile`) = `!IsTemporary(tile) AND
IsWalkable(tile)` = tuile passable, non-temporaire, NON occupée. Même règle d'arrêt que
Walk (les tuiles visitées sont passables par construction → « non occupée » suffit).
`IsTemporary` (tuile-hazard éphémère) non modélisé sur board basique (partagé avec
walk_pathfinder — TODO si une feuille hazard apparaît).
"""
from __future__ import annotations

from . import base_pathfinder as _base
from .board import Board
from .walk_pathfinder import get_movable_positions as _get_movable_positions

# Traits (enum UnitTrait) rendant une unité « comme volante ». Le port lit les NOMS de
# trait gameconfig (str), l'enum donne le nom : 4=Flying, 19=Burrow.
LIKE_FLYING_TRAITS = ("Flying", "Burrow")

#: `FlyPathfinder`'s `WeightCost` (vslot @+0x1f8), RE-DERIVE AU RUNTIME (`resolveVtableSlot`,
#: build `rnca9r7q6c`) : le slot pointe un corps TRIVIAL `return 10` -- ni celui du
#: `WalkPathfinder` (`10 - elevation`) ni celui de l'`IgnoreEverything` (`10 + IsFilled`).
#: Le cout est donc UNIFORME, et le chemin de cout minimal est le chemin de LONGUEUR minimale.
#: C'est ce qui rend le port du chemin de vol non ambigu (cf. `base_pathfinder`, residu de
#: departage : sans relief l'ambiguite n'existe pas).
WEIGHT_COST = 10


def is_like_flying(traits) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsLikeFlying` = HasTrait(Flying=4) OR HasTrait(Burrow=19).
    `traits` = liste des noms de trait (gameconfig)."""
    if not traits:
        return False
    ts = set(traits)
    return any(t in ts for t in LIKE_FLYING_TRAITS)


def is_valid_path_node(
    board: Board, from_id: int, to_id: int,
    occupants: dict, moving_team: int,
) -> bool:
    """`IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsValidPathNode` — peut-on TRAVERSER vers
    `to_id` ? Le décompilé, VERBATIM :

        return nextTile.TileComponent[+0x40] == 0 && nextTile.TileComponent[+0x41] == 0;

    `+0x40` = `IsInFogOfWar`, `+0x41` = `IsWall` (les DEUX offsets sont recoupés :
    `FlyPathfinder$$IsAnyAdjacentTileWall` teste `+0x41`, et `TileExtensions$$IsWalkable(tile,
    checkFog: true)` teste `+0x40` sous le nom `checkFog`). Aucun test d'élévation, aucun blocage
    par unité : le vol ignore le relief et survole alliés comme ennemis.

    ⚠ CE N'EST PAS `IsWalkable` (`#403`, mesuré le 2026-08-01). `TileExtensions$$IsWalkable` =
    `MovementComponent[+0x10] == 0 && TileComponent[+0x40] == 0` — un TROISIÈME champ, celui des
    obstacles de décor. Une tuile `Block`/`Water` porte `walkable = False, isWall = False` : le
    natif la SURVOLE (elle n'est pas un mur) sans pouvoir s'y poser. Tant que le port montait
    l'arête sur `board.walkable`, il refusait de la traverser et SOUS-ATTEIGNAIT — MESURE
    (`probe_403r1_fly_edge_predicate.py`, `C2_26`/38104, `overrideRange` 4, T+6) :
    `tyranNeurothrope` natif **22**, port **21** ; la tuile `(6,6)` ne pend que du `Block` `(6,5)`.

    L'exclusion de `Block`/`Water` de l'ARRIVÉE reste faite, comme dans le natif, par
    `MovementQuery$$IsMovableTile` -> `TileExtensions$$IsFreeTile`, dont les deux premiers tests
    sont EXACTEMENT ceux d'`IsWalkable` (cf. `walk_pathfinder.get_movable_positions`).

    RÉSIDU NOMMÉ : `IsInFogOfWar` n'est pas publié par le `boardGraph` (le capteur le lit —
    `match-state.ts` `tileIsInFog: 0x40` — mais ne l'expose pas), donc l'arête ne porte que
    `!IsWall`. Dégradation PERMISSIVE sur la seule TRAVERSÉE ; l'ARRIVÉE, elle, reste gardée par
    `board.walkable`, qui INCLUT le volet fog. `from_id`/`occupants`/`moving_team` inutilisés
    (signature homogène avec le prédicat walk pour le BFS partagé)."""
    return board.by_id.get(to_id) is not None and not board.is_wall(to_id)


def get_movable_positions(
    board: Board, start_id: int, depth: int,
    occupants: dict, moving_team: int,
) -> tuple[set, set]:
    """(visited, stop_set) pour une unité volante à portée `depth` — BFS partagé de
    `walk_pathfinder` avec l'arête FLY (traverse par-dessus tout, arrêt sur tuile libre).

    **AUCUN gate d'EXPANSION** (`#381-r2`, fermé le 2026-08-01). `IdunBattle.Entities.Pathfinding
    .BasePathfinder$$NodesInNextLevel` interroge bien un slot virtuel (`vslot 10`, lu
    `(**(code **)(*(longlong *)this + 0x1d8))`) avant d'étendre la fill, mais le prédicat #131 —
    « la tuile porte un effet bloqueur » — est produit par le SEUL
    `IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons`, dont les XREFS sont
    EXHAUSTIVES et toutes internes à la branche MARCHE : `WalkPathfinder$$IsValidContinuePathTile`,
    `WalkPathfinder$$GetEffectiveDepth`, `WalkPathfinder$$WeightCost`,
    `IgnoreDoorPathfinder$$IsValidContinuePathTile` et
    `WaveValidatorPathfinder$$IsValidContinuePathTile`. Or `FlyPathfinder` dérive de
    `BasePathfinder`, **pas** de `WalkPathfinder` (`data/symbols/<build>/frida/classes.tsv` :
    `IdunBattle.Entities.Pathfinding.FlyPathfinder  56  IdunBattle.Entities.Pathfinding.BasePathfinder`),
    et `IgnoreDoor`/`WaveValidator` sont les DEUX seules sous-classes de `WalkPathfinder`.
    ⇒ aucun chemin de code ne peut faire d'une tuile block-entering un cul-de-sac pour un volant.

    Le corps EXACT du vslot 10 du `FlyPathfinder` reste non nommable (IL2CPP déduplique les corps
    triviaux — cf. CLAUDE.md « L'ABSENCE d'une méthode dans les tables ne prouve RIEN »), mais les
    deux seules formes compatibles sont **indiscernables ici** : `true`, ou le corps
    d'`IgnoreTerrainPathfinder$$IsValidContinuePathTile` = `TileExtensions$$IsWalkable(tile,
    checkFog: true)` — que l'arête `FlyPathfinder$$IsValidPathNode` a déjà exigé de toute tuile
    visitée (`board.walkable`, capté par `BattleQuery.IsWalkableTile`).

    MESURE (`probe_403_c2_26_fly_gap.py`, `C2_26`/38104, `overrideRange` 2, T+6 `endturn`) :
    `bloodIntercessor` (Flying, sans mouvement spécial) — natif **13**, port **12** tant que le
    gate marche s'appliquait ; la tuile manquante était `(0,2)`, qui ne pend que du Swamp `(1,2)`.
    Sans le gate : **13/13**.

    VOISINAGE = la GÉOMÉTRIE, et c'est un override REEL (#381-r3).
    `IdunBattle.Entities.Pathfinding.FlyPathfinder$$AddNeighbours`
    (`u003CAddNeighboursu003Ed__7$$MoveNext`) occupe le même slot virtuel que
    `IdunBattle.Entities.Pathfinding.BasePathfinder$$AddNeighbours` (leurs seules XREFS sont des
    entrées de vtable) mais interroge la requête de tuiles au rayon 1 au lieu de la liste stockée
    du `ConnectivityComponent`. Le passer EXPLICITEMENT rend le résultat indépendant du `adjacency=`
    de l'instance : jusqu'ici le vol héritait du mode de l'appelant, donc il était juste sous
    `evenq` (les probes) et FAUX sous `native_sym` (`playbook/scene.py`, le montage de PRODUCTION).
    MESURE `C1_74`/3811 `overrideRange` 5 : `bloodIntercessor` natif **46**, port **45** sous
    `native_sym` (la tuile `(3,1)` manque), **46** avec la géométrie."""
    return _get_movable_positions(board, start_id, depth, occupants, moving_team,
                                  edge=is_valid_path_node,
                                  neighbours=board.neighbours_geometric)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# CHEMIN EXACT (`FlyPathfinder$$FindPath`) — l'OVERRIDE, et il ne rend PAS le chemin (#448-r1-r1-r1-r1)
# ─────────────────────────────────────────────────────────────────────────────────────────────
def is_valid_final_tile(board: Board, tile_id: int) -> bool:
    """Le vslot `IsValidFinalTile` (@+0x1c8) du `FlyPathfinder`, RE-DERIVE AU RUNTIME : il pointe
    le MEME corps que celui du marcheur (`IdunBattle.Entities.Pathfinding.WalkPathfinder$$
    IsValidFinalTile`) -- le vol n'a pas le sien. Ce corps, verbatim :

        return !TileExtensions.IsTemporary(tile) && TileExtensions.IsWalkable(tile, true);

    `IsWalkable(tile, checkFog: true)` = `board.walkable`. `IsTemporary` (tuile-hazard ephemere)
    n'a aucune source offline -> RESIDU, deja nomme dans `walk_pathfinder`."""
    return board.walkable(int(tile_id))


def is_any_adjacent_tile_wall(board: Board, tile_id: int) -> bool:
    """`IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsAnyAdjacentTileWall(tile)` -- « une tuile
    de la couronne porte-t-elle `TileComponent+0x41` (`IsWall`) ? ». C'est le SEUL predicat qui
    fasse retenir un point de virage dans `FindPath` ci-dessous.

    Le natif interroge un slot de la requete de tuiles (`this+0x18`, slot 2, args `(tile, 0, 0, 1)`)
    et parcourt le resultat en testant `+0x41` sur chacun. Le port lit la GEOMETRIE au rayon 1,
    meme source que `FlyPathfinder$$AddNeighbours` (slot 1 de la MEME interface, args
    `(tile, 1, ...)`), qui est celle du vol.

    RESIDU NOMME : le slot 2 n'est pas le slot 1, et le natif ne retire PAS le centre du
    resultat (contrairement a `AddNeighbours`, dont l'iterateur fait `while (t == startTile)`).
    Inobservable ici : `FindPath` n'appelle ce predicat que sur des tuiles DEJA traversees, or
    l'arete `IsValidPathNode` interdit d'entrer sur un mur -- une tuile du chemin n'est jamais
    elle-meme un mur."""
    return any(board.is_wall(n) for n in board.neighbours_geometric(int(tile_id)))


def direction_to(board: Board, from_id: int, to_id: int):
    """`IdunBattle.Utils.Hex.AxialCoordinate$$DirectionTo(this, neighbor)` -- la direction hex du
    pas, rendue comme le vecteur CUBE unitaire `(x, y, z)` (`None` = le `Nullable` vide du natif).

    Le natif calcule le delta CUBE `(dq, -(dq+dr), dr)`, le divise par sa norme euclidienne
    (Fix64), met a `0` la composante strictement plus petite que les deux autres (avec un
    tie-break `x *= K + 0.01` quand `|x| == |y|` ou `|x| == |z|`), arrondit chaque composante
    non nulle VERS L'EXTERIEUR (`Ceiling` si > 0, `Floor` sinon), puis passe le tout a
    `IdunBattle.Utils.Hex.CubeDirections$$EdgeToNeighbor`.

    SUR UN PAS UNITAIRE -- le SEUL regime ou `FlyPathfinder$$FindPath` l'appelle, puisqu'il ne le
    fait que sur deux tuiles CONSECUTIVES d'un chemin -- cette machinerie rend exactement le
    delta cube : le vecteur est une permutation de `(1, -1, 0)`, sa norme vaut `sqrt(2)`, et les
    trois branches du tri (composante nulle en z / en y / en x) reduisent toutes au meme vecteur.
    Verifie a la main sur les trois cas.

    RESIDU NOMME : la normalisation GENERALE (deux tuiles NON adjacentes) n'est pas portee --
    aucun call-site porte ne la sollicite. Le port rend `None` dans ce cas, ce qui se comporte
    comme le `Nullable` vide que `EdgeToNeighbor` rendrait sur un vecteur hors des six aretes."""
    import hexgeo
    fc, fr = board.coord(int(from_id))
    tc, tr = board.coord(int(to_id))
    fx, fy, fz = hexgeo.to_cube(fc, fr)
    tx, ty, tz = hexgeo.to_cube(tc, tr)
    d = (tx - fx, ty - fy, tz - fz)
    if sorted(abs(v) for v in d) != [0, 1, 1]:
        return None                                # pas un pas unitaire -> hors regime porte
    return d


def find_path(board: Board, from_id, to_id) -> "list[int] | None":
    """`IdunBattle.Entities.Pathfinding.FlyPathfinder$$FindPath(unit, fromTile, toTile,
    useTeleporter)` -- l'OVERRIDE, et ce qu'il rend N'EST PAS LE CHEMIN : c'est sa reduction en
    **WAYPOINTS**. Le decompile, remis en C# :

        path = base.FindPath(unit, fromTile, toTile, useTeleporter);
        if (path == null || path.Count <= 1) return path;
        out = new List();
        dir = path[0].GetPosition().DirectionTo(path[1].GetPosition());
        for (i = 0; i < path.Count; i++) {
            tile = path[i] as TileEntity;
            if (i < path.Count - 1 && i != 0) {
                bool isTele = TileExtensions.IsTeleportationTile(tile, state, ref _);
                bool turn = false;
                if (IsAnyAdjacentTileWall(this, tile)) {
                    var nd = tile.GetPosition().DirectionTo(path[i + 1].GetPosition());
                    turn = (dir != nd);                       // egalite `Nullable<HexDirection>`
                    if (turn) dir = nd;
                }
                if (isTele || turn) out.Add(tile);
            } else {
                out.Add(tile);                                // extremites TOUJOURS gardees
            }
        }
        return out;

    ⇒ un vol DIRECT se reduit a `[from, to]`. Seuls survivent les virages qui ont un MUR dans
    leur couronne, et les tuiles de teleportation. C'est `MovementQuery$$GetConnectedPathTo` qui
    RE-DENSIFIE ensuite chaque saut par une beeline (`beeline_pathfinder`), laquelle traverse
    tout, murs compris.

    ⚠ `dir` n'est mis a jour QUE quand le virage est RETENU : un changement de direction loin de
    tout mur laisse la direction de reference inchangee, donc le virage SUIVANT est compare a
    l'ancienne. Le port garde ce comportement tel quel -- c'est ce que le decompile fait.

    RESIDU NOMME : `IdunBattle.Entities.TileExtensions$$IsTeleportationTile` (le `!= 0` du
    `ConnectivityComponent+0x18`) n'est pas publie par le `boardGraph` -- meme absence de source
    que le `AddTeleportationTiles` deja nomme dans `walk_pathfinder`. Le port lit donc `False`,
    donc il ne garde PAS un waypoint que le natif garderait sur un board a teleporteur.
    Degradation bornee a ces boards ; aucune arete non geometrique n'apparait dans le
    `boardGraph` de `C1_74`, `MC1_67`, `C2_26`, `C6_25` ni `PVP_desert_04`."""
    path = _base.find_path(board, from_id, to_id,
                           edge=is_valid_path_node_no_ctx,
                           neighbours=board.neighbours_geometric,
                           weight_cost=lambda tid: WEIGHT_COST,
                           is_valid_final_tile=lambda tid: is_valid_final_tile(board, tid))
    if path is None or len(path) <= 1:
        return path
    out = []
    cur_dir = direction_to(board, path[0], path[1])
    last = len(path) - 1
    for i, tid in enumerate(path):
        if 0 < i < last:
            turn = False
            if is_any_adjacent_tile_wall(board, tid):
                nd = direction_to(board, tid, path[i + 1])
                turn = nd != cur_dir
                if turn:
                    cur_dir = nd
            if turn:                               # `isTele` : pas de source -> False (RESIDU)
                out.append(tid)
        else:
            out.append(tid)                        # `i == 0` et `i == Count-1` : TOUJOURS
    return out


def is_valid_path_node_no_ctx(board: Board, from_id: int, to_id: int) -> bool:
    """`is_valid_path_node` sans le contexte d'occupation -- le vol n'en lit aucun (cf. la
    docstring de `is_valid_path_node` : `from_id`/`occupants`/`moving_team` y sont deja
    inutilises). Signature a trois arguments, celle qu'attend `base_pathfinder`."""
    return is_valid_path_node(board, from_id, to_id, {}, None)
