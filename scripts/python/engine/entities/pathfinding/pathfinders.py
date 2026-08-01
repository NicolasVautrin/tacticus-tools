"""`IdunBattle.Entities.Pathfinding.Pathfinders` -- le REGISTRE des pathfinders, et le FOYER
UNIQUE du port pour « quel pathfinder cette unite obtient-elle, et que rend-il ».

Trois consommateurs partagent ce foyer et n'en dupliquent plus le dispatch :
`entities/selectors/tiles.MovableTilesInRange`, `ai/state_bridge._move_tiles`, et
`services/movement_query.get_movable_tiles_for`.

L'enum, lu VERBATIM dans `data/symbols/<build>/frida/enums.tsv`
(`IdunBattle.Entities.Pathfinding.PathfinderType`) -- QUATORZE valeurs, pas deux :

    0=Walk  1=IgnoreTerrain  2=Beeline  3=Fly  4=IgnoreDoor  5=WaveValidator
    6=TeleportStrikeWalk     7=TeleportStrikeFly
    8=StormboyzStrikeWalk    9=StormboyzStrikeFly
    10=FearOfTheUnseenWalk   11=FearOfTheUnseenFly
    12=TitanHammerSquadWalk  13=TitanHammerSquadFly

`IdunBattle.Entities.Pathfinding.Pathfinders$$.ctor` remplit un `Dictionary<PathfinderType,
IPathfinder>` de QUATORZE entrees, et sa STRUCTURE est ce qui compte (les noms de classe que
Ghidra pose sur les ctors gshared ne le sont pas) :

    0 -> walk        1 -> ignoreTerrain   2 -> ignoreEverything (Beeline)
    3 -> fly         4 -> ignoreDoor      5 -> waveValidator
    6 -> A(walk)     7 -> A(fly)          // A = TeleportStrikePathfinder
    8 -> B(walk)     9 -> B(fly)          // B = StormboyzStrikePathfinder
   10 -> C(walk)    11 -> C(fly)          // C = FearOfTheUnseenPathfinder
   12 -> D(walk)    13 -> D(fly)          // D = TitanhammerSquadPathfinder

Les huit derniers sont donc des **DECORATEURS** d'un pathfinder de base (les instances `walk` et
`fly` sont litteralement REUTILISEES : le meme objet est passe aux quatre ctors). Ce que le
decorateur ajoute : cf. `teleport_pathfinder`.

`MovementQuery$$GetReachableTiles(start, type, depth, unit)` = `IPathfinders.FindReachableTiles`
(slot 1) = `Pathfinders$$FindReachableTiles` = `dict[type].FindReachableTiles(start, depth, unit)`.
Aucune autre indirection : le type SUFFIT a designer le pathfinder.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Callable, Optional

from . import teleport_pathfinder as _tp


class PathfinderType(IntEnum):
    """`IdunBattle.Entities.Pathfinding.PathfinderType` -- mirror VERBATIM (orthographe du dump
    comprise : `TitanHammerSquad*` porte un H majuscule que le nom de classe
    `TitanhammerSquadPathfinder` n'a pas)."""
    Walk = 0
    IgnoreTerrain = 1
    Beeline = 2
    Fly = 3
    IgnoreDoor = 4
    WaveValidator = 5
    TeleportStrikeWalk = 6
    TeleportStrikeFly = 7
    StormboyzStrikeWalk = 8
    StormboyzStrikeFly = 9
    FearOfTheUnseenWalk = 10
    FearOfTheUnseenFly = 11
    TitanHammerSquadWalk = 12
    TitanHammerSquadFly = 13


#: Les huit types DECORES -> `(type de base, famille de teleport)`, tels que `Pathfinders$$.ctor`
#: les construit. La famille designe la sous-classe qui fournit `IsValidTeleportTile` (vslot 11).
TELEPORT_DECORATORS: dict[int, tuple[int, str]] = {
    int(PathfinderType.TeleportStrikeWalk):    (int(PathfinderType.Walk), "TeleportStrike"),
    int(PathfinderType.TeleportStrikeFly):     (int(PathfinderType.Fly),  "TeleportStrike"),
    int(PathfinderType.StormboyzStrikeWalk):   (int(PathfinderType.Walk), "StormboyzStrike"),
    int(PathfinderType.StormboyzStrikeFly):    (int(PathfinderType.Fly),  "StormboyzStrike"),
    int(PathfinderType.FearOfTheUnseenWalk):   (int(PathfinderType.Walk), "FearOfTheUnseen"),
    int(PathfinderType.FearOfTheUnseenFly):    (int(PathfinderType.Fly),  "FearOfTheUnseen"),
    int(PathfinderType.TitanHammerSquadWalk):  (int(PathfinderType.Walk), "TitanhammerSquad"),
    int(PathfinderType.TitanHammerSquadFly):   (int(PathfinderType.Fly),  "TitanhammerSquad"),
}


def is_teleport_type(pathfinder_type: int) -> bool:
    """Le type designe-t-il un `ATeleportPathfinder` (6..13) ?"""
    return int(pathfinder_type) in TELEPORT_DECORATORS


def base_type_of(pathfinder_type: int) -> int:
    """Le pathfinder DECORE (`Walk` ou `Fly`) -- l'argument `basePathfinder` du ctor."""
    t = int(pathfinder_type)
    return TELEPORT_DECORATORS.get(t, (t, ""))[0]


def titanhammer_target_tiles(tile_has_effect_with_source, board) -> set:
    """Les tuiles qui rendent VRAI `TitanhammerSquadPathfinder$$IsValidTitanhammerSquadTargetTile`
    -- mirror du decompile :

        var eff = EntityExtensions.GetOwnedEffect(tile, state, 0x623);   // TitanhammerSquad_TargetTile
        return eff != null
            && EntityExtensions.GetEffectSourceUnit(eff, state) is u
            && UnitExtensions.IsFriend(u, unit, state);

    `tile_has_effect_with_source(tile_id) -> bool` = « cette tuile porte l'effet 1571 pose par un
    ALLIE du mover », le seul predicat que l'appelant sait construire (le port keye les effets de
    tuile par tile-id dans `EffectsState`, cf. case-35). `None` -> `set()` NON MESURE."""
    if tile_has_effect_with_source is None or board is None:
        return set()
    return {int(t) for t in board.by_id if tile_has_effect_with_source(int(t))}


def _teleport_predicate(family: str, board, occupants: dict,
                        target_tiles: Optional[set]) -> Optional[Callable[[int], bool]]:
    """Le slot virtuel `IsValidTeleportTile(unit, tile)` de la SOUS-CLASSE (vslot 11), ferme sur le
    substrat disponible. `None` = filtre absent.

    ⚠ RESULTAT DE RE, et il compte : sur le pool que `FindTilesReachableByTeleport` a DEJA filtre
    (`IsEmptyOrSteppable` retire toute tuile occupee), TROIS des quatre predicats sont
    IDENTIQUEMENT VRAIS -- ce ne sont donc pas « quatre variantes du meme pathfinder » par hasard,
    c'est que trois d'entre eux ne restreignent rien de plus :

      * `TeleportStrike` : `Count(entites sur la tuile, e => !IsSteppable(e)) == 0` ;
      * `FearOfTheUnseen` : `IsTallGrass(tile) || <ce meme compte> == 0 || <zone d'un allie qui
        porte l'effet 0x41c>` -- la 2e branche suffit et court-circuite les deux autres ;
      * `StormboyzStrike` : aucune methode nommee, corps trivial (cf. `teleport_pathfinder`).

    Le QUATRIEME, `TitanhammerSquad`, est le seul RESTRICTIF : la tuile n'est valide que si
    ELLE-MEME ou une de ses VOISINES porte `TitanhammerSquad_TargetTile` (1571) pose par un allie
    -- `IsValidTitanhammerSquadTargetTile(unit, tile) || GetAdjacentTiles(tile, ...)
    .Any(t => IsValidTitanhammerSquadTargetTile(unit, t))`. Sans substrat (`target_tiles is None`)
    on ne peut pas trancher : on rend un predicat TOUJOURS FAUX, donc un pool de teleport VIDE.
    Degradation RESTRICTIVE et NOMMEE -- exactement le comportement d'avant `#381-r5`, jamais un
    pool board-wide invente."""
    if family in ("TeleportStrike", "FearOfTheUnseen"):
        return lambda tid: _tp.is_valid_teleport_tile_teleport_strike(tid, occupants)
    if family == "StormboyzStrike":
        return lambda tid: _tp.is_valid_teleport_tile_stormboyz(tid, occupants)
    if family == "TitanhammerSquad":
        if target_tiles is None:
            return lambda tid: False
        tt = {int(t) for t in target_tiles}
        return lambda tid: (int(tid) in tt
                            or any(int(n) in tt for n in board.neighbours(int(tid))))
    return None


def find_reachable_tiles(board, pathfinder_type: int, start_id: int, depth: int,
                         occupants: dict, moving_team, can_continue=None,
                         teleport_target_tiles: Optional[set] = None) -> tuple[set, set]:
    """`IdunBattle.Entities.Pathfinding.Pathfinders$$FindReachableTiles(type, start, depth, unit)`
    -- `dict[type].FindReachableTiles(...)`, rendu sous la forme `(visited, stop)` du port.

    Types portes : `Walk` (0) et `Fly` (3) par leurs modules homonymes, et les HUIT decorateurs
    6..13 (base + pool de teleport board-wide). Les types 1/2/4/5 ne sont PAS atteignables par
    `GetPathfinderTypeForUnit` (ils ne servent qu'a des appelants qui passent le type EN DUR, ex.
    le `PathfinderType = 1` litteral de `MinDistanceToClosestEnemyUtility`, porte a part dans
    `ignore_terrain_pathfinder`) -> ils retombent ici sur la base marche, comme le port l'a
    toujours fait, et sont hors perimetre de ce foyer."""
    from .fly_pathfinder import get_movable_positions as _fly
    from .walk_pathfinder import get_movable_positions as _walk
    t = int(pathfinder_type)
    base = base_type_of(t)
    mv = _fly if base == int(PathfinderType.Fly) else _walk
    visited, stop = mv(board, int(start_id), int(depth), occupants, moving_team,
                       can_continue=can_continue)
    if not is_teleport_type(t):
        return visited, stop
    family = TELEPORT_DECORATORS[t][1]
    pred = _teleport_predicate(family, board, occupants, teleport_target_tiles)
    tele = _tp.find_tiles_reachable_by_teleport(board, occupants, is_valid_teleport_tile=pred)
    return _tp.iterate_reachable_tiles(visited, stop, tele)


def movable_positions_for_unit(board, start_id: int, depth: int, occupants: dict, moving_team,
                               traits, has_effect, can_continue=None,
                               ignore_special_movement: bool = False,
                               teleport_target_tiles: Optional[set] = None
                               ) -> tuple[set, set]:
    """LES DEUX ETAGES, dans l'ordre du natif : `MovementQuery$$GetPathfinderTypeForUnit` puis
    `MovementQuery$$GetReachableTiles`. C'est ce que les TROIS consommateurs appellent -- ils ne
    choisissent plus le pathfinder eux-memes.

    `has_effect(effect_type:int) -> bool` = `EntityExtensions$$HasEffect(unit, state, <type>, 0)`
    ferme sur l'unite par l'appelant ; `None` -> aucun effet (le dispatch retombe alors sur
    `Walk`/`Fly`, soit le comportement d'avant `#381-r5`, mais par une valeur EXPLICITE)."""
    from ...services.movement_query import get_pathfinder_type_for_unit
    ptype = get_pathfinder_type_for_unit(has_effect, traits,
                                         ignore_special_movement=ignore_special_movement)
    return find_reachable_tiles(board, ptype, start_id, depth, occupants, moving_team,
                                can_continue=can_continue,
                                teleport_target_tiles=teleport_target_tiles)
