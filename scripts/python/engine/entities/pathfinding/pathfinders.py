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
from . import beeline_pathfinder as _bl
from .walk_pathfinder import get_movable_positions as _walk
from . import fly_pathfinder as _fly
from . import fly_pathfinder as _fly_mod


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


def _teleport_predicate(family: str, board, occupants: dict, moving_team,
                        target_tiles: Optional[set],
                        synapse_tiles: Optional[set]) -> Optional[Callable[[int], bool]]:
    """Le slot virtuel `IsValidTeleportTile(unit, tile)` de la SOUS-CLASSE (vslot 11), ferme sur le
    substrat disponible. Les QUATRE sont DISTINCTS -- ce ne sont pas quatre copies :

      * `TeleportStrike` : « aucun ennemi non-Steppable ADJACENT » (`GetAdjacentEnemies`) ;
      * `FearOfTheUnseen` : le meme, plus DEUX echappatoires (`IsTallGrass`, bulle `Synapse_Effect`
        d'un allie au rayon 2) ;
      * `StormboyzStrike` : corps trivial, non nomme -> `True` -- CONFRONTE live le 2026-08-01
        (`#366-r1` 3/3, greffe du passif : natif == port sur 3 montages, cf. le module) ;
      * `TitanhammerSquad` : le seul VRAIMENT restrictif -- la zone `TitanhammerSquad_TargetTile`
        marquee par un allie, elle-meme ou une voisine.

    Substrats absents (`None`) : la branche concernee est INERTE, et l'effet est nomme dans chaque
    predicat -- jamais un pool invente."""
    if family == "TeleportStrike":
        return lambda tid: _tp.is_valid_teleport_tile_teleport_strike(
            tid, board, occupants, moving_team)
    if family == "FearOfTheUnseen":
        return lambda tid: _tp.is_valid_teleport_tile_fear_of_the_unseen(
            tid, board, occupants, moving_team, synapse_tiles)
    if family == "StormboyzStrike":
        return lambda tid: _tp.is_valid_teleport_tile_stormboyz(
            tid, board, occupants, moving_team)
    if family == "TitanhammerSquad":
        return lambda tid: _tp.is_valid_teleport_tile_titanhammer(tid, board, target_tiles)
    return None


def continue_gate_for(pathfinder_type: int, walk_gate):
    """`IsValidContinuePathTile` — le slot que `BasePathfinder$$NodesInNextLevel` interroge avant
    d'etendre la fill (`vslot 10`, lu `(**(code **)(*(longlong *)this + 0x1d8))`). Le gate vit dans
    la BASE, mais **le predicat appartient au PATHFINDER**, pas a l'appelant : c'est un slot
    virtuel, et les deux branches n'y mettent pas la meme chose.

      * base MARCHE -> `WalkPathfinder$$IsValidContinuePathTile` = `GetTileBlockingReasons == 0`,
        le gate #131 (`walk_gate`, construit par `tile_blocking.make_can_continue`) ;
      * base VOL    -> **rien** (`#381-r2`). `WalkPathfinder$$GetTileBlockingReasons` est le SEUL
        producteur du bit block-entering, et ses XREFS sont EXHAUSTIVES et toutes internes a la
        branche marche (`WalkPathfinder$$IsValidContinuePathTile`, `$$GetEffectiveDepth`,
        `$$WeightCost`, `IgnoreDoorPathfinder$$IsValidContinuePathTile`,
        `WaveValidatorPathfinder$$IsValidContinuePathTile`). Or `FlyPathfinder` derive de
        `BasePathfinder`, PAS de `WalkPathfinder` -- detail et mesure : `fly_pathfinder`.

    Les HUIT decorateurs suivent leur base : `ATeleportPathfinder$$IsValidContinuePathTile` est un
    `_base.IsValidContinuePathTile(unit, tile)` (appel du slot sur `this+0x28`), donc 7/9/11/13
    (fly decore) n'ont pas de gate non plus, et 6/8/10/12 (walk decore) gardent celui de la marche.

    Les types 1/2/4/5 ne sont pas atteignables par `GetPathfinderTypeForUnit` et retombent ici sur
    la base marche, comme le port l'a toujours fait (hors perimetre, cf. `find_reachable_tiles`)."""
    return None if base_type_of(int(pathfinder_type)) == int(PathfinderType.Fly) else walk_gate


def find_reachable_tiles(board, pathfinder_type: int, start_id: int, depth: int,
                         occupants: dict, moving_team, can_continue=None,
                         teleport_target_tiles: Optional[set] = None,
                         synapse_tiles: Optional[set] = None) -> tuple[set, set]:
    """`IdunBattle.Entities.Pathfinding.Pathfinders$$FindReachableTiles(type, start, depth, unit)`
    -- `dict[type].FindReachableTiles(...)`, rendu sous la forme `(visited, stop)` du port.

    Types portes : `Walk` (0) et `Fly` (3) par leurs modules homonymes, et les HUIT decorateurs
    6..13 (base + pool de teleport board-wide). Les types 1/2/4/5 ne sont PAS atteignables par
    `GetPathfinderTypeForUnit` (ils ne servent qu'a des appelants qui passent le type EN DUR, ex.
    le `PathfinderType = 1` litteral de `MinDistanceToClosestEnemyUtility`, porte a part dans
    `ignore_terrain_pathfinder`) -> ils retombent ici sur la base marche, comme le port l'a
    toujours fait, et sont hors perimetre de ce foyer."""
    # forme MODULE : get_movable_positions est SUBSTITUE (probe_381r1, probe_403_c2_26 et
    # deux tests _live.py). Hisse en `from ... import`, ce nom serait lie AU CHARGEMENT et
    # les quatre mesures cesseraient de mordre, EN SILENCE (#485-r1-r1).
    t = int(pathfinder_type)
    base = base_type_of(t)
    if base == int(PathfinderType.Fly):
        # `FlyPathfinder` : arete propre, et AUCUN gate d'expansion (`continue_gate_for`).
        visited, stop = _fly_mod.get_movable_positions(board, int(start_id), int(depth),
                                                       occupants, moving_team)
    else:
        visited, stop = _walk(board, int(start_id), int(depth), occupants, moving_team,
                              can_continue=continue_gate_for(t, can_continue))
    if not is_teleport_type(t):
        return visited, stop
    family = TELEPORT_DECORATORS[t][1]
    pred = _teleport_predicate(family, board, occupants, moving_team,
                               teleport_target_tiles, synapse_tiles)
    tele = _tp.find_tiles_reachable_by_teleport(board, occupants, is_valid_teleport_tile=pred)
    return _tp.iterate_reachable_tiles(visited, stop, tele)


def find_path(board, pathfinder_type: int, from_id, to_id,
              occupants: Optional[dict] = None) -> "list[int] | None":
    """`IdunBattle.Entities.Pathfinding.Pathfinders$$GetPath(type, unit, from, to, useTeleporter)`
    = `dict[type].FindPath(...)` -- le pendant CHEMIN de `find_reachable_tiles` ci-dessus, et le
    MEME dispatch : le type SUFFIT a designer le pathfinder.

    Les trois routes que ce foyer sert, et elles ne rendent PAS la meme forme :

      * types DECORES 6..13 -> `ATeleportPathfinder$$FindPath` = **`[from, to]`**, sans aucun
        pathfinding (RE-DERIVE AU RUNTIME sur `TeleportStrikePathfinder` idx 0x07) ;
      * `Fly` (3)           -> `FlyPathfinder$$FindPath` = le chemin A* REDUIT A SES WAYPOINTS ;
      * `Beeline` (2)       -> `BasePathfinder$$FindPath` avec les predicats triviaux.

    `Walk` (0) rend `None` -- **pas parce que le natif le ferait**, mais parce que le port
    materialise la marche par un AUTRE moteur, en domaine POSITION
    (`walk_pathfinder.get_path_node_counts_by_pos`), FOYER PARTAGE avec la face DECISION (#304).
    Les appelants du port ne demandent donc jamais le chemin de marche a ce foyer-ci ; celui qui
    le ferait doit lire cette ligne plutot que d'interpreter le `None` comme la branche degeneree
    du natif. Les types 1/4/5 ne sont atteignables par aucun `GetPathfinderTypeForUnit`."""
    t = int(pathfinder_type)
    if is_teleport_type(t):
        return _tp.find_path(board, from_id, to_id)
    if t == int(PathfinderType.Beeline):
        return _bl.find_path(board, from_id, to_id, occupants)
    if t == int(PathfinderType.Fly):
        return _fly.find_path(board, from_id, to_id)
    return None


def movable_positions_for_unit(board, start_id: int, depth: int, occupants: dict, moving_team,
                               traits, has_effect, can_continue=None,
                               ignore_special_movement: bool = False,
                               teleport_target_tiles: Optional[set] = None,
                               synapse_tiles: Optional[set] = None) -> tuple[set, set]:
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
                                teleport_target_tiles=teleport_target_tiles,
                                synapse_tiles=synapse_tiles)
