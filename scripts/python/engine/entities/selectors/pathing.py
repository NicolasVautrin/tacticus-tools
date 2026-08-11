"""Selecteurs dont le corps natif interroge le PATHFINDING -- `Nearest` (`NearestSelector`) et
`ClosestPositionToTarget` (`Selectors.ClosestPositionToTarget`). Tranche 5 du decoupage de
`selectors.py` (cf. `__init__.py`).

POURQUOI UNE TRANCHE A PART : ces deux noeuds sont les SEULS selecteurs dont le `$$Select` appelle
`IBattleQuery.GetMinPathLength` / `GetMovablePositionsFor`, c.-a-d. le moteur de deplacement --
`units`/`tiles`/`geometry` ne lisent que la geometrie hex et l'occupation. Ils dependent donc de
`entities/pathfinding` (comme `tiles.MovableTilesInRange`), et de rien d'autre.

Demandeur (#889-r5) : `IdunBattleLogic.Entities.Abilities.Active.Loki.MartialExemplarAbility$$
ExecuteBehaviour` (`1216`), qui empile les deux dans sa branche << aucun ennemi attaquable
adjacent >> : `MoveUnit(Owner, ClosestPositionToTarget(Owner, Tiles(<cible tiree>), nrOfTiles,
false))` ou `<cible tiree>` passe par `Nearest(..., CasterTiles, Owner, PathLength, null)`.
"""
from __future__ import annotations

from ...dsl.base import TargetsSelector, _feet, _is_alive, _pos, _units_of, resolve_unit
from ._shared import _entity_pos, _tile_positions
from ..pathfinding.walk_pathfinder import get_path_node_counts_by_pos
from ..traits.unit_trait import UnitTrait
# FORME B (`import <module>` + acces attributaire) : `BattleQuery$$AreEntitiesAdjacent` (slot 96)
# est le mirror natif appele par `NearestSelector$$GetDistance`, et la forme B garde la MORSURE
# d'un `monkeypatch.setattr` dessus. Differe CLASSE **GRATUIT** (mesure du 2026-08-11 : charger
# `engine.services.battle_query` seul en process FRAIS ne met PAS `engine.entities.selectors.pathing`
# dans `sys.modules`) -> HISSE au niveau module, comme la doctrine l'exige.
from ...services import battle_query as _svc_battle_query


def _mq():
    """`engine.services.movement_query`, DIFFERE -- classe **PORTEUR**, et la mesure est celle que
    la doctrine demande, pas le constat qu'un cycle existe : charger
    `engine.services.movement_query` seul dans un process FRAIS met
    `engine.entities.selectors.pathing` dans `sys.modules` (mesure du 2026-08-11), donc le hisser
    FERMERAIT le cycle -- il le fermait, litteralement : la cascade
    `movement_query -> runner.components -> ... -> entities.selectors -> pathing -> movement_query`
    faisait echouer `from ..runner.components import OwnerComponent` sur un module partiellement
    initialise, et rendait ROUGES les cinq dicts consommateurs de `probe_313` etape 5.

    Les DEUX parades en amont ont ete essayees et ECARTEES, pas negligees :
      * (1) DEPLACER -- `MovementQuery$$GetDistance` est le foyer natif partage par les faces
        COMBAT et DECISION ; en extraire une copie ici creerait une SECONDE implementation du meme
        natif, exactement ce que ce module existe pour eviter ;
      * (2) ALLEGER l'`__init__` -- `entities/selectors/__init__.py` RE-EXPORTE toutes ses tranches
        par contrat ecrit (145 sites d'import en dependent) ; en sortir `pathing` reglerait le
        cycle en cassant l'uniformite du paquet.

    FORME B (`from ... import <module>` + acces attributaire) : elle garde la morsure d'un
    `monkeypatch.setattr("engine.services.movement_query.get_distance", ...)`, ce qu'une liaison
    `from X import get_distance` perdrait."""
    from ...services import movement_query
    return movement_query

#: `System.Int32.MaxValue` -- la sentinelle que rendent `NearestSelector$$GetDistance` (via
#: `BattleQuery$$GetMinPathLength` sur un chemin vide) et le `maxDistance` ABSENT des deux noeuds.
#: ⚠ CE N'EST PAS `-1` : `BattleQuery$$GetMinDistance` porte l'autre sentinelle, et les confondre
#: inverserait les comparaisons `d <= maxDistance` ci-dessous.
INT_MAX = 0x7FFFFFFF


def _walk_blocking_positions(ctx, mover) -> set:
    """`IdunBattle.Entities.Pathfinding.WalkPathfinder$$UnitIsBlockedByEnemyUnit` cote DSL : les
    positions portant un occupant ENNEMI VIVANT non `Steppable`.

    MEME predicat que le foyer runner `runner/operations/movement.py::_blocking_positions` -- il est
    RE-EXPRIME ici sur le substrat du DSL (`ctx.units` + `ctx.has_trait`), qui n'a ni `State` ni
    composants ECS ; les deux lisent le meme natif. `ctx.has_trait` absent -> aucun `Steppable`
    detecte -> tout occupant ennemi bloque (polarite CONSERVATRICE : on ne fabrique pas un passage).
    """
    team = (mover or {}).get("team")
    ht = getattr(ctx, "has_trait", None) or (lambda u, t: False)
    out = set()
    for u in (ctx.units or []):
        if not isinstance(u, dict) or u is mover or not _is_alive(u):
            continue
        if team is not None and u.get("team") == team:
            continue
        if ht(u, int(UnitTrait.Steppable)):
            continue
        for f in _feet(u):
            out.add((int(f[0]), int(f[1])))
    return out


def _path_node_counts(ctx, mover, origin):
    """`{(col,row) -> Count}` de `IPathfinders.GetPath(unit, origin, <pos>, null)` -- le FOYER
    PARTAGE `walk_pathfinder.get_path_node_counts_by_pos` (celui de `MoveUnitOperation` et de la
    face DECISION), jamais une seconde implementation.

    `Count` = nombre de NOEUDS extremites incluses, ce qui est EXACTEMENT ce que rend
    `IdunBattle.Core.Services.BattleQuery$$GetMinPathLength` (`route.Count`, avec `int.MaxValue`
    quand le chemin est vide). Rend `{}` si le board n'est pas cale."""
    board = getattr(ctx, "board", None)
    if board is None or origin is None:
        return {}
    neigh, walk, elev = board.walk_maps_by_pos()
    return get_path_node_counts_by_pos((int(origin[0]), int(origin[1])),
                                       neigh_by_pos=neigh, walkable_by_pos=walk, elev_by_pos=elev,
                                       blocking_positions=_walk_blocking_positions(ctx, mover))


def _free_adjacent_positions(ctx, entity) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles(from)` (slot 82) -- corps LU :

        GetAdjacentTiles(from, includeSelf: 1, onlyWalkable: 1).FilterInPlace(<tuile LIBRE>)

    L'etage ADJACENCE passe par le FOYER UNIQUE deja porte
    (`services/movement_query.adjacent_tile_ids`, mirror de `BattleQuery$$GetAdjacentTiles(tile, 0,
    1, 1)`, qui lit le voisinage STOCKE du board) -- pas par la geometrie hex pure, qui ignorerait
    la connectivite et l'elevation. Le port materialise ensuite << libre >> par l'absence
    d'occupant VIVANT (meme critere d'occupation que `tiles.MovableTilesInRange` : par EMPREINTE,
    jamais par main tile). Rend une liste de positions `(col,row)`, `[]` si le board n'est pas
    cale."""
    board = getattr(ctx, "board", None)
    if board is None or entity is None:
        return []
    occupied = set()
    for u in (ctx.units or []):
        if isinstance(u, dict) and _is_alive(u):
            for f in _feet(u):
                occupied.add((int(f[0]), int(f[1])))
    out, seen = [], set()
    for p in _feet(entity):
        for tid in _mq().adjacent_tile_ids(board, (int(p[0]), int(p[1]))):
            c = board.coord(int(tid))
            n = (int(c[0]), int(c[1]))
            if n in seen or n in occupied or not board.walkable(int(tid)):
                continue
            seen.add(n)
            out.append(n)
    return out


class Nearest(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$Nearest(entities, target, pathfindingUnit,
    distanceType, maxDistance)` -> `IdunBattle.Entities.Selectors.NearestSelector$$Select`.

    UNE SEULE implementation dans le build (`refcount` 9, aucune surcharge homonyme) -- etabli par
    les XREFS ENTRANTES, pas par le nom : ses appelants sont `CosmicHorror_OnKillAbility$$
    CreateBehaviour`, `ThunderousAssaultAbility$$ExecuteBehaviour`, `TheBetrayer_TakeTurnAbility$$
    GetNearestValidAttackTargets`, et les DEUX de `MartialExemplarAbility` (`$$ExecuteBehaviour` et
    `$$GetNearestValidAttackTargets`). Les voisins `NearestFreeTilesAmount` et
    `NearestAttackableEnemies` sont des noms DISTINCTS, pas des surcharges.

    MIRROR de `$$Select`, lu de bout en bout :

        candidates = (+0x28 entities).Select(entities)
        targets    = (+0x30 target).Select(entities)
        maxDist    = (+0x48 maxDistance)?.Calculate(entities) ?? int.MaxValue
        pathUnit   = (+0x38 pathfindingUnit)?.SelectUnit(entities, OnlyAliveAndTargetable)
        if (pathUnit == null && (+0x40 distanceType) == PathLength) {
            logger.Log(0x17, 4, 0) ; return candidates ;      // <- INTACTS, aucun tri
        }
        best = int.MaxValue ; result = new OrderedSet()
        foreach (c in candidates) foreach (t in targets) {
            d = GetDistance(c, t, pathUnit)
            if (d <= best && d <= maxDist) { if (d < best) result.Clear() ; result.Add(c) ; best = d }
        }
        return result

    DEUX points de structure que le port ne lisse pas :
      * la branche `pathUnit == null` en `PathLength` rend les CANDIDATS TELS QUELS -- ni vide, ni
        filtres. C'est la degradation du NATIF, pas la notre ;
      * `best` est mis a jour DANS la boucle interne, et `Add` a lieu aussi a EGALITE (`d <= best`)
        -> les ex-aequo s'accumulent, dedupliques par l'`OrderedSet`. Un `min`-argmax classique
        rendrait UN element la ou le natif peut en rendre plusieurs.

    `distance_type` = `IdunBattle.Entities.Enum.DistanceType` (`0 = Simple`, `1 = PathLength`)."""

    def __init__(self, entities: TargetsSelector, target: TargetsSelector,
                 pathfinding_unit: TargetsSelector = None,
                 distance_type: int = 0, max_distance=None):
        self.entities, self.target = entities, target
        self.pathfinding_unit = pathfinding_unit
        self.distance_type = int(distance_type)
        self.max_distance = max_distance

    # `IdunBattle.Entities.Selectors.NearestSelector$$GetDistance(candidate, target,
    # pathfindingUnit)` -- MIRROR, les deux bras :
    #
    #     if (distanceType == Simple) return battleQuery.GetDistance(candidate, target);   // slot 108
    #     if (battleQuery.AreEntitiesAdjacent(candidate, target)) return 1;                // slot 96
    #     tiles  = candidate.ToList();
    #     isUnit = EntityExtensions.IsUnit(candidate);
    #     if (isUnit) tiles = battleQuery.GetFreeAdjacentTiles(candidate);                 // slot 82
    #     d = battleQuery.GetMinPathLength(pathfindingUnit, target, tiles);                // slot 22
    #     return isUnit ? d : d - 1;
    #
    # ⚠ Le `- 1` ne porte QUE sur un candidat qui n'est PAS une unite (une tuile) : le chemin y
    # arrive SUR la tuile, alors que pour une unite il s'arrete sur une tuile ADJACENTE (d'ou le
    # `GetFreeAdjacentTiles`). Le rabattre sur les deux bras decalerait tout le classement d'un pas.
    def _distance(self, ctx, candidate, target, path_unit, counts) -> int:
        board = getattr(ctx, "board", None)
        cp = _entity_pos(candidate, board)
        tp = _entity_pos(target, board)
        if cp is None or tp is None:
            return INT_MAX
        if self.distance_type == 0:                            # DistanceType.Simple
            # `MovementQuery$$GetDistance(IList, IList)` = MIN sur les paires de pieds, sentinelle
            # `int.MaxValue` sur liste vide. ⚠ PAS `get_min_distance` (sentinelle `-1`).
            return _mq().get_distance(
                _feet(candidate) if isinstance(candidate, dict) else [cp],
                _feet(target) if isinstance(target, dict) else [tp])
        # DistanceType.PathLength
        if _svc_battle_query.are_entities_adjacent(
                _feet(candidate) if isinstance(candidate, dict) else [cp],
                _feet(target) if isinstance(target, dict) else [tp], board=board):
            return 1
        is_unit = isinstance(candidate, dict)
        tiles = _free_adjacent_positions(ctx, candidate) if is_unit else [cp]
        # `GetMinPathLength(unit, from, to:IList)` = MIN sur `to`, avec court-circuit des que le
        # minimum atteint 1 (`while (best != 1)`), et `int.MaxValue` quand aucun chemin n'existe.
        best = INT_MAX
        for t in tiles:
            n = counts.get((int(t[0]), int(t[1])))
            if n and int(n) < best:
                best = int(n)
            if best == 1:
                break
        if best == INT_MAX:
            return INT_MAX
        return best if is_unit else best - 1

    def select(self, ctx):
        candidates = _units_of(self.entities, ctx)
        board = getattr(ctx, "board", None)
        raw_t = self.target.evaluate(ctx)
        targets = ([] if raw_t is None
                   else ([raw_t] if isinstance(raw_t, (dict, int)) else list(raw_t)))
        max_d = INT_MAX
        if self.max_distance is not None:
            v = (self.max_distance.evaluate(ctx) if hasattr(self.max_distance, "evaluate")
                 else self.max_distance)
            max_d = INT_MAX if v is None else int(v)
        path_unit = None
        if self.pathfinding_unit is not None:
            path_unit = resolve_unit(self.pathfinding_unit, ctx)
            # `SelectUnit(entities, OnlyAliveAndTargetable)` -- le 2e argument du slot 7, LU au
            # call-site (`CONCAT44(x, 3)`). Le port materialise le filtre par la liveness, seul
            # canal disponible sans `State` (meme degradation que `_selection_ok` ailleurs).
            if path_unit is not None and not _is_alive(path_unit):
                path_unit = None
        if path_unit is None and self.distance_type == 1:      # DistanceType.PathLength
            return candidates                                  # branche NATIVE (log + passthrough)
        counts = ({} if self.distance_type == 0
                  else _path_node_counts(ctx, path_unit, _pos(path_unit)))
        best, result, seen = INT_MAX, [], set()
        for c in candidates:
            for t in targets:
                d = self._distance(ctx, c, t, path_unit, counts)
                if d <= best and d <= max_d:
                    if d < best:                               # `result.Clear()` du natif
                        result, seen = [], set()
                    key = c.get("id") if isinstance(c, dict) else _entity_pos(c, board)
                    if key not in seen:                        # `OrderedSet.Add` (dedup, ordre gardé)
                        seen.add(key)
                        result.append(c)
                    best = d
        return result


class ClosestPositionToTarget(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$ClosestPositionToTarget(unit, targetTiles,
    maxDistance, ignoreFlags)` -> `IdunBattle.Entities.Selectors.ClosestPositionToTarget$$Select`.

    UNE SEULE implementation, et son unique appelant du build est
    `MartialExemplarAbility$$ExecuteBehaviour` (xrefs entrantes).

    ⚠ **LE CTOR EST MISLABELE ET LE PIEGE EST REEL.** Ghidra nomme le ctor alloue par ce noeud
    `IdunBattle.Entities.Selectors.TilesUnitCanAttackFromSelector$$.ctor` -- un corps DEDUPLIQUE,
    partage avec `DSLSelectors$$TilesUnitCanAttackFrom`, dont les parametres sont
    `(tiles, enemyOf, unitId:System.String, withMovement:bool)`. Lire ces noms-la aurait fait
    ranger un `IAmountFormula` dans un slot `System.String` et brancher le `$$Select` de l'AUTRE
    classe (celui qui appelle `GetUnitConfig`/`GetUnitMaxRange`). La signature RETENUE est celle de
    `frida/methods.tsv` (`unit:ITargetsSelector, targetTiles:ITargetsSelector,
    maxDistance:IAmountFormula, ignoreFlags:System.Boolean`), et la classe reellement allouee est
    `IdunBattle.Entities.Selectors.ClosestPositionToTarget` (`classes.tsv`, taille 64, base
    `TargetSelector`), dont le `$$Select` est le corps mirrore ci-dessous.

    MIRROR de `$$Select` :

        targets   = (+0x28 targetTiles).Select(entities)
        maxDist   = (+0x30 maxDistance)?.Calculate(entities) ?? int.MaxValue
        unit      = (+0x20 unit)?.SelectUnit(entities, OnlyAliveAndTargetable)
        positions = battleQuery.GetMovablePositionsFor(unit, (+0x38 ignoreFlags),
                                                       Nullable<int>(maxDist))      // slot 13
        best = null ; bestD = int.MaxValue
        foreach (p in positions) {
            tile = p.<Tile>
            d = battleQuery.GetDistance(tile, targets)                              // slot 110
            if (d < bestD) { best = tile ; bestD = d }
        }
        return best

    Le comparateur est `<` STRICT : a egalite, la PREMIERE position dans l'ordre du pathfinder
    gagne. `maxDistance` n'est pas un filtre a posteriori -- c'est l'`overrideRange` passe au
    moteur de deplacement, donc le RAYON du BFS.

    Rend une liste de POSITIONS `(col,row)` (domaine tuile du port), vide si rien n'est joignable.
    """

    def __init__(self, unit: TargetsSelector, target_tiles: TargetsSelector,
                 max_distance=None, ignore_flags: bool = False):
        self.unit, self.target_tiles = unit, target_tiles
        self.max_distance = max_distance
        self.ignore_flags = bool(ignore_flags)

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        targets = _tile_positions(self.target_tiles, ctx, board)
        unit = resolve_unit(self.unit, ctx)
        if unit is None or not targets:
            return []
        max_d = INT_MAX
        if self.max_distance is not None:
            v = (self.max_distance.evaluate(ctx) if hasattr(self.max_distance, "evaluate")
                 else self.max_distance)
            max_d = INT_MAX if v is None else int(v)
        # `GetMovablePositionsFor(unit, ignoreFlags, overrideRange)` : le port reutilise le FOYER
        # deja porte -- le BFS de marche borne a `overrideRange`, occupation par empreinte. Les
        # positions rendues sont le `stop_set` (cf. `tiles.MovableTilesInRange` : le natif filtre
        # les tuiles occupees, la tuile de depart comprise).
        origin = _pos(unit)
        if origin is None:
            return []
        counts = _path_node_counts(ctx, unit, origin)
        occupied = set()
        for u in (ctx.units or []):
            if isinstance(u, dict) and _is_alive(u):
                for f in _feet(u):
                    occupied.add((int(f[0]), int(f[1])))
        best, best_d = None, INT_MAX
        for p, n in counts.items():
            if int(n) - 1 > max_d or p in occupied:
                continue
            d = _mq().get_distance([p], targets)
            if d < best_d:                                   # `<` STRICT : 1er arrive, 1er servi
                best, best_d = p, d
        return [] if best is None else [best]
