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

from .board import Board
from .walk_pathfinder import get_movable_positions as _get_movable_positions

# Traits (enum UnitTrait) rendant une unité « comme volante ». Le port lit les NOMS de
# trait gameconfig (str), l'enum donne le nom : 4=Flying, 19=Burrow.
LIKE_FLYING_TRAITS = ("Flying", "Burrow")


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
