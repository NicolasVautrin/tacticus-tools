"""`IdunBattle.Core.Services.MovementQuery` — les slots qui raisonnent sur l'EMPREINTE d'une unite
(la liste de ses tuiles), et non sur une tuile unique.

C'est la moitie « geometrie » du substrat MULTI-HEX (R30). L'autre moitie — le STOCKAGE de
l'empreinte — vit dans `engine.runner.components` (`UnitComponent.feet` + `get_unit_feet` /
`get_feet_count` / `get_main_tile`), mirror de `UnitComponent._feet`.

MODELE NATIF, lu au decompile (build gqfc5mff6c) :

  * une unite a N PIEDS. Chaque pied est une ENTITE a part (`Blueprints.UnitFoot`) portant un
    `UnitFootComponent {UnitId@0x10, TileId@0x14}` ; `UnitComponent._feet` @+0x78 est l'
    `OrderedSet<int>` des ids de ces entites-pieds, rempli par
    `IdunBattle.Operations.AddUnitOperation$$Execute` (`UnitComponent$$ClearFeet` puis un
    `UnitComponent$$AddFoot` par tuile, DANS L'ORDRE de la liste de tuiles recue).
  * `IdunBattle.Entities.EntityExtensions$$GetTiles` = `IterateTiles(...).ToList()` = les tuiles
    des pieds, dans l'ordre des pieds.
  * `IdunBattle.Entities.EntityExtensions$$GetMainTileId` : sur un `UnitComponent`, prend
    `_feet[0]` puis recurse sur le `UnitFootComponent.TileId` de CE pied -> **la MAIN TILE est
    la tuile du PREMIER pied**.
  * TAILLES SUPPORTEES = 1, 3, 7 — declarees par l'enum `IdunBattle.Core.Services.TargetingRule`
    (`CasterHas1/3/7Tiles`, `TargetHas1/3/7Tiles`) et imposees par `IsValidUnitFeetList` ci-dessous.

Le port n'a ni entite-tuile ni entite-pied : il collapse « pied -> tuile » en un `(col,row)`
(meme collapse que `PositionComponent`, deja en place). L'ORDRE, lui, est conserve tel quel :
c'est lui qui designe la main tile.
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable, List, Optional, Sequence, Tuple

import hexgeo

Pos = Tuple[int, int]

# `IsValidUnitFeetList` / `GetPossibleTileListsFromMovableTiles` : seuls 1, 3 et 7 sont supportes ;
# toute autre valeur fait logger « Unsupported feet count: <n> » et rend false / null.
SUPPORTED_FEET_COUNTS = (1, 3, 7)

# `MovementQuery$$GetDistance` seed sa recherche de MINIMUM a `int.MaxValue` et rend cette valeur
# telle quelle quand une des deux listes est vide (et l'overload entite rend 0x7fffffff sur null).
INT_MAX = 0x7FFFFFFF


def get_distance(tiles_a: Optional[Sequence[Pos]], tiles_b: Optional[Sequence[Pos]]) -> int:
    """`IdunBattle.Core.Services.MovementQuery$$GetDistance(IList<TileEntity>, IList<TileEntity>)`
    — mirror 1:1 :

        int best = int.MaxValue;
        foreach (a in tilesA) foreach (b in tilesB)
            best = Min(best, CubeCoordinate.Distance(a.Position.GetCubeCoordinate(),
                                                     b.Position.GetCubeCoordinate()));
        return best;

    C'est LE point ou le multi-hex change tout : la distance entre deux entites est le **MINIMUM
    sur toutes les paires de pieds**, pas la distance entre leurs deux main tiles. Une unite a 3
    pieds « touche » donc a distance 1 tout ce qui est adjacent a N'IMPORTE LEQUEL de ses pieds.

    Liste vide (ou None) -> `int.MaxValue` : aucune paire n'a ete evaluee, le seed ressort tel
    quel (fidele — le natif ne rend PAS 0)."""
    best = INT_MAX
    for a in (tiles_a or ()):
        for b in (tiles_b or ()):
            d = hexgeo.distance(a, b)
            if d < best:
                best = d
    return best


def get_entity_distance(state, entity_a, entity_b) -> int:
    """`IdunBattle.Core.Services.MovementQuery$$GetDistance(IEntity, IEntity)` — mirror :

        if (a == null || b == null) return int.MaxValue;
        return GetDistance(EntityExtensions.GetTiles(a, state), EntityExtensions.GetTiles(b, state));

    `GetTiles` = l'empreinte COMPLETE (cf. `components.get_unit_feet`)."""
    from ..runner.components import get_unit_feet
    if entity_a is None or entity_b is None:
        return INT_MAX
    return get_distance(get_unit_feet(state, entity_a), get_unit_feet(state, entity_b))


def is_adjacent(board, tile_a: Optional[Pos], tile_b: Optional[Pos]) -> bool:
    """`IdunBattle.Core.Services.MovementQuery$$IsAdjacent(a, b)` =
    `GetAdjacentTiles(a, false, true, true).Contains(b)` (slot 0x4e, flags `(0,1,1)`).

    Offline : le graphe d'adjacence NATIF du `boardGraph` (`Board.neighbours`), la meme adjacence
    que partout ailleurs dans le port. Sans board on ne sait pas decider -> False (aucun voisinage
    invente ; le seul appelant est `is_valid_unit_feet_list`, qui degrade alors en « empreinte non
    validable », jamais en « valide par defaut »)."""
    if board is None or tile_a is None or tile_b is None:
        return False
    tid_a = board.id_at(tile_a[0], tile_a[1])
    tid_b = board.id_at(tile_b[0], tile_b[1])
    if tid_a is None or tid_b is None:
        return False
    return tid_b in board.neighbours(tid_a)


def _elevation(board, tile: Pos) -> Optional[int]:
    tid = board.id_at(tile[0], tile[1]) if board is not None else None
    return None if tid is None else board.elevation(tid)


def _center_of_seven(board, tiles: Sequence[Pos]) -> Optional[Pos]:
    """La tuile CENTRE d'une empreinte a 7 pieds.

    ⚠ SYMBOLE NON RESOLU : `IsValidUnitFeetList` obtient le centre par un slot d'interface
    (`<IBattleQuery slot 0x5d>(tiles)`) que la table de symboles ne nomme pas. On ne recopie donc
    PAS un nom invente : on applique la definition GEOMETRIQUE que la branche impose juste apres
    (« toute tuile de la liste differente du centre lui est adjacente ») — c'est-a-dire l'unique
    tuile adjacente aux 6 autres. Elle coincide avec le PRODUCTEUR de ces listes
    (`get_possible_tile_lists_from_movable_tiles`, branche 7 : `OrderedSet{t} + neighbours(t)`,
    centre en tete). Aucun centre -> None -> empreinte invalide."""
    for cand in tiles:
        others = [t for t in tiles if t != cand]
        if len(others) == len(tiles) - 1 and all(is_adjacent(board, cand, o) for o in others):
            return cand
    return None


def is_valid_unit_feet_list(board, feet_count: int, tiles: Optional[Sequence[Optional[Pos]]]) -> bool:
    """`IdunBattle.Core.Services.MovementQuery$$IsValidUnitFeetList(feetCount, tiles)` — mirror
    1:1 du decompile, dans l'ordre :

        if (tiles == null) return false;
        if (tiles.Count != feetCount) return false;
        nullCount = tiles.Count(t => t == null);
        if (nullCount == feetCount) return true;          // liste ENTIEREMENT nulle = acceptee
        if (nullCount > 0) return false;
        elev = TileExtensions.GetElevation(tiles[0]);
        for (i = 1; i < tiles.Count; i++)
            if (TileExtensions.GetElevation(tiles[i]) != elev) return false;   // meme ELEVATION
        if (feetCount == 1) return true;
        if (feetCount == 3)
            return GetDistance(0,1)==1 && GetDistance(0,2)==1 && GetDistance(1,2)==1
                && IsAdjacent(0,1) && IsAdjacent(0,2) && IsAdjacent(1,2);      // TRIANGLE
        if (feetCount == 7) {
            center = <slot 0x5d>(tiles);
            foreach (t in tiles) if (t != center && !IsAdjacent(t, center)) return false;
            return true;                                                       // CENTRE + ANNEAU
        }
        Log("Unsupported feet count: " + feetCount); return false;

    Les DEUX tests du cas 3 (distance cube == 1 ET adjacence de graphe) sont conserves : ils ne sont
    redondants que sur un plateau sans trou — le graphe natif porte des aretes manquantes aux bords."""
    if tiles is None:
        return False
    tiles = list(tiles)
    if len(tiles) != int(feet_count):
        return False
    null_count = sum(1 for t in tiles if t is None)
    if null_count == int(feet_count):
        return True                                   # liste toute nulle : acceptee par le natif
    if null_count > 0:
        return False
    elev0 = _elevation(board, tiles[0])
    for t in tiles[1:]:
        if _elevation(board, t) != elev0:
            return False
    n = int(feet_count)
    if n == 1:
        return True
    if n == 3:
        for i, j in ((0, 1), (0, 2), (1, 2)):
            if hexgeo.distance(tiles[i], tiles[j]) != 1:
                return False
        return all(is_adjacent(board, tiles[i], tiles[j]) for i, j in ((0, 1), (0, 2), (1, 2)))
    if n == 7:
        center = _center_of_seven(board, tiles)
        if center is None:
            return False
        return all(t == center or is_adjacent(board, t, center) for t in tiles)
    return False                                      # « Unsupported feet count: <n> »


def get_possible_tile_lists_from_movable_tiles(
        board, tiles: Sequence[Pos], feet_count: int) -> Optional[List[List[Pos]]]:
    """`IdunBattle.Core.Services.MovementQuery$$GetPossibleTileListsFromMovableTiles(tiles,
    feetCount)` — mirror 1:1 :

        if (feetCount == 1) return TExtensions.GetKCombs(tiles, 1);
        if (feetCount == 3) return TExtensions.GetKCombs(tiles, 3);
        if (feetCount == 7) {
            var res = new OrderedSet<...>();
            foreach (t in tiles) {
                var nb = GetAdjacentTiles(t, false, true, true);       // slot 0x4e, flags (0,1,1)
                if (tiles.ContainsAll(nb)) { var s = new OrderedSet(); s.Add(t); s.AddRange(nb);
                                             res.Add(s); }
            }
            return res;
        }
        return null;

    Branche 7 : le CENTRE est ajoute EN PREMIER, l'anneau ensuite dans l'ordre d'enumeration natif
    des voisins (`Board.neighbours_native`) -> `feet[0]` = le centre = la main tile.
    `feetCount` hors {1,3,7} -> `None` (et non une liste vide : le natif rend bien null)."""
    n = int(feet_count)
    tiles = list(tiles)
    if n in (1, 3):
        return [list(c) for c in combinations(tiles, n)]      # GetKCombs<T>(tiles, n)
    if n == 7:
        pool = set(tiles)
        out: List[List[Pos]] = []
        for t in tiles:
            tid = board.id_at(t[0], t[1]) if board is not None else None
            if tid is None:
                continue
            nb = [board.coord(x) for x in board.neighbours_native(tid)]
            if nb and all(x in pool for x in nb):
                out.append([t] + nb)
        return out
    return None


def get_movable_positions_from_tiles(board, tiles: Sequence[Pos],
                                     feet_count: int) -> List[List[Pos]]:
    """`IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles(tiles, feetCount)` —
    mirror 1:1 :

        if (tiles.Count == 0) return new OrderedSet<UnitPosition>();
        if (feetCount == 1)  return UnitPositionExtensions.ToUnitPositionList(tiles);
        var res = new OrderedSet<UnitPosition>();
        foreach (combo in GetPossibleTileListsFromMovableTiles(tiles, feetCount))
            if (IsValidUnitFeetList(feetCount, combo)) res.Add(new UnitPosition(combo));
        return res;

    ⚠ Le cas `feetCount == 1` est un CHEMIN A PART (`ToUnitPositionList`, aucun filtre) — c'est
    pour ca qu'une unite a 1 pied ne change strictement PAS de comportement quand ce module entre
    en jeu. Une `UnitPosition` = ici la liste ordonnee des tuiles de l'empreinte (son `MainTile`
    natif, `UnitPosition$$get_MainTile`, est l'element 0)."""
    tiles = list(tiles)
    if not tiles:
        return []
    if int(feet_count) == 1:
        return [[t] for t in tiles]                            # ToUnitPositionList
    combos = get_possible_tile_lists_from_movable_tiles(board, tiles, feet_count) or []
    return [c for c in combos if is_valid_unit_feet_list(board, feet_count, c)]


#: `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit, ignoreSpecialMovement)`,
#: LU AU DECOMPILE :
#:
#:     if (!ignoreSpecialMovement) {
#:         if (HasEffect(unit, 0x40b)) return IsLikeFlying(unit) ? 7  : 6;
#:         if (HasEffect(unit, 0x474)) return IsLikeFlying(unit) ? 9  : 8;
#:         if (HasEffect(unit, 0x4d6)) return IsLikeFlying(unit) ? 11 : 10;
#:         if (HasEffect(unit, 0x625)) return IsLikeFlying(unit) ? 13 : 12;
#:     }
#:     return IsLikeFlying(unit) ? 3 : 0;
#:
#: Les quatre effets sont les etats « je descends du ciel » (`EffectType` du port) :
#:     0x40b = 1035 TeleportStrike_TeleportingIn      0x474 = 1140 StormboyzStrike_TeleportingIn
#:     0x4d6 = 1238 FearOfTheUnseen_TeleportingIn     0x625 = 1573 TitanhammerSquad_TeleportingIn
#:
#: L'ordre des quatre tests est CELUI DU DECOMPILE et il est observable : une unite qui porterait
#: deux de ces effets prendrait le pathfinder du PREMIER de cette liste.
SPECIAL_MOVEMENT_EFFECT_TYPES = (0x40b, 0x474, 0x4d6, 0x625)

#: `<effet> -> (type WALK, type FLY)` -- les huit valeurs que la branche MOUVEMENT SPECIAL rend,
#: dans l'ordre des tests. Les types sont ceux de `entities.pathfinding.pathfinders.PathfinderType`.
SPECIAL_MOVEMENT_PATHFINDER_TYPES = {
    0x40b: (6, 7),        # 1035 TeleportStrike_TeleportingIn    -> TeleportStrikeWalk / Fly
    0x474: (8, 9),        # 1140 StormboyzStrike_TeleportingIn   -> StormboyzStrikeWalk / Fly
    0x4d6: (10, 11),      # 1238 FearOfTheUnseen_TeleportingIn   -> FearOfTheUnseenWalk / Fly
    0x625: (12, 13),      # 1573 TitanhammerSquad_TeleportingIn  -> TitanHammerSquadWalk / Fly
}


def get_pathfinder_type_for_unit(has_effect, traits, ignore_special_movement: bool = False) -> int:
    """`IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit,
    ignoreSpecialMovement)` -- MIRROR 1:1 du decompile, et le FOYER UNIQUE du dispatch :

        if (!ignoreSpecialMovement) {
            if (HasEffect(unit, state, 0x40b, 0)) return IsLikeFlying(unit) ? 7  : 6;
            if (HasEffect(unit, state, 0x474, 0)) return IsLikeFlying(unit) ? 9  : 8;
            if (HasEffect(unit, state, 0x4d6, 0)) return IsLikeFlying(unit) ? 11 : 10;
            if (HasEffect(unit, state, 0x625, 0)) return IsLikeFlying(unit) ? 13 : 12;
        }
        return IsLikeFlying(unit) ? 3 : 0;

    (la surcharge a DEUX arguments, `GetPathfinderTypeForUnit(this, unit)`, est un simple
    `GetPathfinderTypeForUnit(this, unit, false)` -- elle n'a donc pas de mirror propre.)

    ⇒ **le type de pathfinder ne depend PAS que d'`IsLikeFlying`** : quatre effets « je descends
    du ciel » le detournent vers un `ATeleportPathfinder`, dont le pool est BOARD-WIDE. C'est le
    residu `#381-r5`, ferme ici. MESURE avant/apres (`C2_26`, seed 38104, `overrideRange` 2, tout
    debut de bataille) : `tyranDeathleaper` et `bloodIntercessor` portent
    `TeleportStrike_TeleportingIn` et le natif leur rend **35** tuiles la ou le port en rendait
    **9** -- un pool board-wide, pas un disque de rayon 2.

    `has_effect(effect_type:int) -> bool` ferme sur l'unite (chaque consommateur a son propre
    canal : `state.effects.has_effect` cote runner, `ctx.has_effect` cote DSL) ; `None` = pas de
    canal -> aucun effet special, la branche finale. `traits` = les NOMS de trait (gameconfig),
    lus par `UnitExtensions$$IsLikeFlying`."""
    from ..entities.pathfinding.fly_pathfinder import is_like_flying
    fly = 1 if is_like_flying(traits) else 0
    if not ignore_special_movement and has_effect is not None:
        for et in SPECIAL_MOVEMENT_EFFECT_TYPES:
            if has_effect(int(et)):
                return SPECIAL_MOVEMENT_PATHFINDER_TYPES[et][fly]
    return 3 if fly else 0                      # `IsLikeFlying(unit) ? Fly : Walk`


def has_special_movement(state, unit_id: int) -> bool:
    """L'unite est-elle dans un etat de MOUVEMENT SPECIAL (`GetPathfinderTypeForUnit`, branche
    `!ignoreSpecialMovement`) ? Un mesureur s'en sert pour NOMMER le regime plutot que de compter
    un desaccord ; depuis `#381-r5` le port SUIT ce regime au lieu de le subir."""
    eff = getattr(state, "effects", None) if state is not None else None
    if eff is None:
        return False
    return any(eff.has_effect(int(unit_id), effect_type=int(t))
               for t in SPECIAL_MOVEMENT_EFFECT_TYPES)


def unit_has_effect_fn(state, unit_id: int):
    """`EntityExtensions$$HasEffect(unit, state, <type>, 0)` ferme sur l'unite -- le canal que les
    consommateurs RUNNER passent a `get_pathfinder_type_for_unit`. `state.effects` absent -> None
    (pas de canal), et le dispatch retombe alors explicitement sur `Walk`/`Fly`."""
    eff = getattr(state, "effects", None) if state is not None else None
    if eff is None:
        return None
    uid = int(unit_id)
    return lambda et: eff.has_effect(uid, effect_type=int(et))


def synapse_tiles_for(state, board, moving_team) -> set | None:
    """La BULLE SYNAPSE de l'equipe du mover -- la troisieme branche de
    `FearOfTheUnseenPathfinder$$IsValidTeleportTile` :

        <unites du player>.Any(e => HasEffect(e, state, 0x41c, 0)
            && BattleQuery$$GetSurroundingTiles(e, 2, onlyEmptyOrSteppable: true,
                   onlyWalkable: true, onlyMovable: false, includeCenter: true).Contains(tile))

    `0x41c` = `Synapse_Effect` (1052). Le rayon est une distance HEX (`GetSurroundingTiles`), pas
    un nombre de pas. Les deux gates `onlyEmptyOrSteppable`/`onlyWalkable` sont deja appliques en
    amont par `FindTilesReachableByTeleport` -- on ne les rejoue pas. Aucun canal -> `None` (NON
    MESURE), et la branche reste inerte."""
    eff = getattr(state, "effects", None) if state is not None else None
    if eff is None or board is None:
        return None
    from ..entities.effect_type import EffectType
    from ..runner.components import OwnerComponent, PositionComponent, UnitComponent
    want = int(EffectType.Synapse_Effect)
    out = set()
    for eid, e in (getattr(state, "entities", None) or {}).items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if uc is None or not uc.alive or oc is None or pc is None:
            continue
        if moving_team is None or oc.team != moving_team:
            continue
        if not eff.has_effect(int(eid), effect_type=want):
            continue
        for tid in board.by_id:
            c, r = board.coord(int(tid))
            if hexgeo.distance((c, r), (pc.col, pc.row)) <= 2:
                out.add(int(tid))
    return out


def titanhammer_target_tiles_for(state, board, moving_team) -> set | None:
    """Les tuiles portant `TitanhammerSquad_TargetTile` (1571) posees par un ALLIE du mover --
    le seul substrat que reclame `TitanhammerSquadPathfinder$$IsValidTeleportTile` (cf.
    `pathfinders.titanhammer_target_tiles`). `state.effects` keye les effets de tuile par tile-id
    (case-35) ; l'appartenance de la SOURCE a l'equipe du mover se lit sur l'entite source.
    Aucun canal -> `None` (NON MESURE), et le pool de teleport Titanhammer reste vide."""
    eff = getattr(state, "effects", None) if state is not None else None
    if eff is None or board is None:
        return None
    from ..entities.effect_type import EffectType
    from ..runner.components import OwnerComponent
    want = int(EffectType.TitanhammerSquad_TargetTile)
    out = set()
    for tid in board.by_id:
        for e in eff.by_unit.get(int(tid), []):
            if e.consumed or int(getattr(e, "effect_type", -1)) != want:
                continue
            src = state.get_entity(int(getattr(e, "source", 0) or 0))
            oc = src.get_component(OwnerComponent) if src is not None else None
            if oc is not None and moving_team is not None and oc.team == moving_team:
                out.add(int(tid))
                break
    return out


def get_movable_tiles_for(board, state, unit_id: int, from_tile: int, override_range: int,
                          occupants: dict, moving_team) -> set:
    """`IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor(unit, tiles, ignoreUnitFlags,
    options)` -- le FOYER que tout collapse imperatif du noeud `MovableTilesInRange` doit appeler.
    Rend le STOP-SET (ids de tuile), comme le natif.

        MovementQuery$$GetMovableTilesFor -> $$FindAnyOrAllMoveableTiles :
            type  = GetPathfinderTypeForUnit(unit, options.pathfinderTypeOverride)
            range = options.overrideRange ?? StatComponent(Movement).CurrentValue
          -> $$AnyOrFillMoveableTiles(tiles, type, unit, range, bonus, ignoreUnitsOnTiles, out) :
                 r = GetReachableTiles(start, type, range, unit)      // le PATHFINDING
                 r.RemoveAll(t => !IsMovableTile(this, unit, t, ignoreUnitsOnTiles))

    DEUX etages que les collapses impératifs oubliaient (residu `#381-r4`, ferme ici), et que le
    noeud DSL homonyme (`entities/selectors/tiles.MovableTilesInRange`) porte depuis `#381-r1` :

      1. `MovementQuery$$GetPathfinderTypeForUnit` : un volant prend le `FlyPathfinder` (traverse
         tout, ignore l'elevation) -- et, depuis `#381-r5`, sa branche MOUVEMENT SPECIAL est
         portee elle aussi (quatre effets -> un `ATeleportPathfinder` au pool board-wide). Le
         dispatch ENTIER vit dans `entities.pathfinding.pathfinders.movable_positions_for_unit`,
         partage par les trois consommateurs ;
      2. le gate d'EXPANSION `BasePathfinder$$NodesInNextLevel` -> `IsValidContinuePathTile`
         (#131) : une tuile block-entering (Swamp/Fire/Ice/...) reste un STOP legal mais devient
         un CUL-DE-SAC. `board=` est OBLIGATOIRE (repli TERRAIN de `make_can_continue`) : la
         plupart des etats du runner sont charges SANS le canal opt-in `load_state(tiles=tileMeta)`,
         et le gate serait alors INERTE **en silence** -- residu ferme par case-224 sec.4.

    `occupants` reste construit par l'APPELANT (les collapses n'ont pas tous la meme convention
    d'occupation) ; `moving_team` est la valeur a laquelle `WalkPathfinder$$UnitIsBlockedByEnemyUnit`
    compare l'occupant. Traits lus a la source unique du port (`StatsComponent.ctx.traits`).

    RESIDUS (identiques a ceux du noeud DSL, cf. `MovableTilesInRange`) : la garde d'entree
    `UnitFlagsComponent$$Has(unitFlags, 1)` (#381, aucun substrat), `IsTileReserved` /
    `IsTilePendingDrafting` / `IsTemporary`, le trait `Steppable` d'`IsFreeTile`, et l'occupation
    par EMPREINTE (les appelants passent une occupation par MAIN TILE, comme `_move_tiles`)."""
    from ..entities.pathfinding.pathfinders import movable_positions_for_unit
    from ..entities.pathfinding.tile_blocking import make_can_continue
    from ..runner.components import StatsComponent
    e = state.get_entity(int(unit_id)) if state is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    traits = (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None)
              else None) or []
    cc = make_can_continue(getattr(state, "effects", None), traits, board=board)
    _visited, stop = movable_positions_for_unit(
        board, int(from_tile), int(override_range), occupants, moving_team,
        traits=traits, has_effect=unit_has_effect_fn(state, unit_id), can_continue=cc,
        teleport_target_tiles=titanhammer_target_tiles_for(state, board, moving_team),
        synapse_tiles=synapse_tiles_for(state, board, moving_team))
    return stop


def get_movable_positions_for(board, state, unit_id: int, movable_tiles: Iterable[Pos]
                              ) -> List[List[Pos]]:
    """`IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor(unit, ..., options)` —
    l'assemblage que le natif fait au-dessus des deux fonctions ci-dessus :

        if (UnitExtensions.HasTrait(unit, 0x418)) return new OrderedSet<UnitPosition>();  // immobile
        feetCount   = UnitExtensions.GetFeetCount(unit, state);
        movable     = GetMovableTilesFor(unit, ..., options);
        movable.AddRange(EntityExtensions.IterateTiles(unit, state));   // ses tuiles ACTUELLES
        return GetMovablePositionsFromTiles(movable, feetCount);

    `movable_tiles` = le resultat de `GetMovableTilesFor` (le pathfinding, deja porte ailleurs) ;
    on n'ajoute ici que les deux etapes propres a l'empreinte : l'union avec les tuiles courantes
    et le regroupement en positions a N pieds.

    LE GATE `HasTrait(0x418)` EST DESORMAIS REPRODUIT (#91, il etait le residu R30 §6.3). Il ne
    l'etait pas parce qu'aucun porteur du trait n'existait dans l'etat du port ; c'est
    `AddTrait(ActiveTarget, 0x418)` -- le sous-behaviour on-appearance de `DutyEternalAbility$$
    ExecuteBehaviour` -- qui en cree un. Les traits sont lus a la SOURCE UNIQUE du port
    (`StatsComponent.ctx.traits`, cf. `entities/traits/unit_trait.py`) ; une entite sans
    `StatsComponent` n'est pas gatee (meme convention permissive qu'ailleurs)."""
    from ..runner.components import get_feet_count, get_unit_feet, StatsComponent
    from ..entities.traits.unit_trait import UnitTrait, has_trait
    e = state.get_entity(int(unit_id)) if state is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is not None and has_trait(getattr(sc.ctx, "traits", None), UnitTrait.Stationary):
        return []                       # `if (HasTrait(unit, 0x418)) return new OrderedSet<>()`
    tiles = list(movable_tiles)
    for t in get_unit_feet(state, unit_id):
        if t not in tiles:
            tiles.append(t)
    return get_movable_positions_from_tiles(board, tiles, get_feet_count(state, unit_id))
