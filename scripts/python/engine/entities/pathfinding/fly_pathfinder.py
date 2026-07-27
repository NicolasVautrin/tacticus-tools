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
    """`IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsValidPathNode` — peut-on TRAVERSER vers `to_id` :
    uniquement `walkable(to)` (non-mur/non-unplayable). Ignore l'élévation ET l'occupant
    (le vol passe par-dessus). `from_id`/`occupants`/`moving_team` inutilisés (signature
    homogène avec le prédicat walk pour le BFS partagé)."""
    t = board.by_id.get(to_id)
    return t is not None and bool(t["walkable"])


def get_movable_positions(
    board: Board, start_id: int, depth: int,
    occupants: dict, moving_team: int,
    can_continue=None,
) -> tuple[set, set]:
    """(visited, stop_set) pour une unité volante à portée `depth` — BFS partagé de
    `walk_pathfinder` avec l'arête FLY (traverse par-dessus tout, arrêt sur tuile libre).

    `can_continue` = gate d'EXPANSION #131 (`IdunBattle.Entities.Pathfinding.BasePathfinder
    $$NodesInNextLevel`). Le gate lui-même vit dans `BasePathfinder` ⇒ il vaut pour TOUS les
    pathfinders. Le PRÉDICAT, lui, est le slot virtuel `IsValidContinuePathTile` : celui que le
    FlyPathfinder résout n'est **PAS ÉTABLI** — la table de symboles ne liste pas
    `FlyPathfinder$$IsValidContinuePathTile`, mais IL2CPP déduplique les corps triviaux et
    l'absence d'un symbole ne prouve RIEN (cf. CLAUDE.md « L'ABSENCE d'une méthode dans les tables
    ne prouve RIEN ») ; le trancher demande d'invoquer le slot de vtable sur une instance. Le
    paramètre est donc THREADÉ (l'appelant décide) et `state_bridge._move_tiles` passe aujourd'hui
    le MÊME prédicat qu'en marche — résidu assumé, sans incidence tant qu'aucune unité volante ne
    survole une tuile block-entering dans un scénario mesuré. None = pas de gate."""
    return _get_movable_positions(board, start_id, depth, occupants, moving_team,
                                  edge=is_valid_path_node, can_continue=can_continue)
