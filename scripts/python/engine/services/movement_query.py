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

from ..entities.effect_type import EffectType
# Les VALEURS de `SPECIAL_MOVEMENT_PATHFINDER_TYPES` sont des `PathfinderType` (#270-r1-r1).
# Sens de l'import : `pathfinders` ne remonte vers ce module que par un import LOCAL (dans
# `movable_positions_for_unit`), donc aucun cycle a l'import.
from ..entities.pathfinding.pathfinders import PathfinderType
from ..entities.pathfinding import beeline_pathfinder as _beeline
from ..entities.pathfinding.fly_pathfinder import is_like_flying
from ..entities.pathfinding.pathfinders import movable_positions_for_unit
from ..entities.pathfinding.tile_blocking import make_can_continue
from ..entities.traits.unit_trait import UnitTrait, has_trait
from ..runner.components import OwnerComponent
from ..runner.components import OwnerComponent, PositionComponent, UnitComponent
from ..runner.components import StatsComponent
from ..runner.components import get_feet_count, get_unit_feet, StatsComponent
from ..runner.components import get_unit_feet
# HISSES de `get_range_bonus_for_unit` (#485-r5), ou ils etaient DIFFERES au motif ecrit
# << CYCLE >>. La mesure dit le contraire, dans un process FRAIS et pour les TROIS :
# `import engine.entities.effects.base` (174 modules `engine.*`), `import engine.runner.components`
# (178) et `import engine.services.range_bonus` (3) ne mettent PAS `engine.services.movement_query`
# dans `sys.modules`. `..runner.components` etait de surcroit DEJA au preambule ci-dessus, donc ce
# differe-la ne protegeait rien et rougissait `test_270r4r2r2::etage1`.
# FORME B (liaison de MODULE, pas de symbole) : c'est la seule des trois formes qui garde la
# morsure d'un `monkeypatch.setattr`, l'attribut etant resolu a l'APPEL.
from ..entities.effects import base as _effects_base
from ..runner import components as _components
from ..services import range_bonus as _range_bonus

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


def get_min_distance(tiles_a: Optional[Sequence[Pos]], tiles_b: Optional[Sequence[Pos]]) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetMinDistance(IList<TileEntity>, IList<TileEntity>)`
    -- le slot 0x6f d'`IBattleQuery` (identifie par son proxy
    `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass138_0$$u003CGetMinDistanceu003Eb__0`,
    dont tout le corps est cet appel-la). Mirror du decompile :

        int best = int.MaxValue;
        foreach (a in tilesA) foreach (b in tilesB)
            best = Math.Min(best, GetDistance(a, b));       // la surcharge TUILE/TUILE
        return best == int.MaxValue ? -1 : best;

    C'est la MEME double boucle que `get_distance` ci-dessus (meme seed `int.MaxValue`, meme
    primitive de distance hex) -- la SEULE difference lue est le SENTINEL DE SORTIE : quand aucune
    paire n'a ete evaluee, `MovementQuery$$GetDistance` rend `int.MaxValue` alors que celle-ci rend
    **-1**. La distinction n'est pas cosmetique : son unique consommateur DSL,
    `IdunBattle.Entities.Triggers.IsInRangeAbilityTrigger$$ShouldTrigger`, conclut par
    `return GetMinDistance(...) <= range` -- donc un selecteur qui rend VIDE fait rendre VRAI au
    predicat (`-1 <= range`), la ou `int.MaxValue` aurait rendu faux. Ne jamais substituer l'une a
    l'autre."""
    d = get_distance(tiles_a, tiles_b)
    return -1 if d == INT_MAX else d


def get_entity_distance(state, entity_a, entity_b) -> int:
    """`IdunBattle.Core.Services.MovementQuery$$GetDistance(IEntity, IEntity)` — mirror :

        if (a == null || b == null) return int.MaxValue;
        return GetDistance(EntityExtensions.GetTiles(a, state), EntityExtensions.GetTiles(b, state));

    `GetTiles` = l'empreinte COMPLETE (cf. `components.get_unit_feet`)."""
    if entity_a is None or entity_b is None:
        return INT_MAX
    return get_distance(get_unit_feet(state, entity_a), get_unit_feet(state, entity_b))


def adjacent_tile_ids(board, tile: Optional[Pos]) -> List[int]:
    """`IBattleQuery` slot `0x4f` = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(tile,
    onlyEmptyOrSteppable: false, onlyWalkableTiles: true, allowTemporary: true)` -- FOYER UNIQUE des
    DEUX appels de ce module (#457-r1), qui sont le MEME appel a l'octet pres : meme slot, meme
    receveur (`MovementQuery+0x30`), memes flags `(0, 1, 1)`.

    LA VUE, tranchee au decompile. `GetAdjacentTiles` delegue a
    `IdunBattle.Core.Services.BattleQuery$$IterateAdjacentTiles` -> `TileQuery$$IterateAdjacentTiles`,
    dont le `MoveNext` (`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`)
    enumere la liste d'adjacence **STOCKEE** sur la tuile (`ConnectivityComponent`), pas une couronne
    geometrique :

        elev0 = tile.TileComponent.Elevation;
        foreach (nid in tile.ConnectivityComponent.Neighbours) {
            t = state.GetTileEntity(nid);                 if (t == null) continue;
            if (!allowTemporary       && IsTemporary(t))  continue;
            if (onlyWalkableTiles     && !IsWalkable(t, true))          continue;
            if (onlyEmptyOrSteppable  && !IsEmptyOrSteppable(t, state)) continue;
            if (Math.Abs(elev0 - t.Elevation) < 2) yield return t;      // porte INCONDITIONNELLE
        }

    ⇒ **`Board.neighbours_native`** (le champ BRUT `boardGraph.neighbours`), et surtout PAS
    `Board.neighbours()`, qui trie les ids ET symetrise les aretes. Le capteur du `boardGraph` passe
    par ce meme `IterateAdjacentTiles` avec `(0, 0, 1)`, donc la porte d'elevation est deja appliquee
    dans le champ capte ; l'asymetrie residuelle du graphe stocke est une PROPRIETE du natif, pas un
    artefact a corriger. Avant #459 `is_adjacent` lisait la vue symetrisee et la branche `feetCount
    == 7` la vue brute -- deux mirrors du meme appel sur deux graphes differents.

    ⚠ RESIDU `#457-r2`, toujours ouvert : `onlyWalkableTiles = 1` n'est PAS reapplique ici. Le
    `boardGraph` est capte avec `requireWalkable = 0` (murs inclus, a dessein) et le port ne refiltre
    pas. Inerte sur les DEUX consommateurs mesures -- leurs tuiles viennent toutes de
    `GetMovableTilesFor` (pathfinding) ou de l'empreinte courante de l'unite, donc marchables par
    construction -- mais mordant des qu'un appelant y ferait entrer un mur."""
    if board is None or tile is None:
        return []
    tid = board.id_at(tile[0], tile[1])
    return [] if tid is None else list(board.neighbours_native(tid))


def is_adjacent(board, tile_a: Optional[Pos], tile_b: Optional[Pos]) -> bool:
    """`IdunBattle.Core.Services.MovementQuery$$IsAdjacent(a, b)` =
    `GetAdjacentTiles(a, false, true, true).Contains(b)` -- mirror 1:1, via le foyer
    `adjacent_tile_ids` ci-dessus (c'est la MEME instruction d'appel que la branche `feetCount == 7`
    de `GetPossibleTileListsFromMovableTiles`, #457-r1).

    Sans board on ne sait pas decider -> False (aucun voisinage invente ; le seul appelant est
    `is_valid_unit_feet_list`, qui degrade alors en « empreinte non validable », jamais en « valide
    par defaut »)."""
    if board is None or tile_a is None or tile_b is None:
        return False
    tid_b = board.id_at(tile_b[0], tile_b[1])
    if tid_b is None:
        return False
    return tid_b in adjacent_tile_ids(board, tile_a)


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
    des voisins (`adjacent_tile_ids` -> `Board.neighbours_native`) -> `feet[0]` = le centre = la main
    tile. `feetCount` hors {1,3,7} -> `None` (et non une liste vide : le natif rend bien null).

    Le `GetAdjacentTiles(t, false, true, true)` de cette branche et celui d'`is_adjacent` sont le
    MEME appel (meme slot d'interface, memes flags, meme receveur) : ils partagent donc le foyer
    `adjacent_tile_ids` depuis #459 (residu `#457-r1` ferme)."""
    n = int(feet_count)
    tiles = list(tiles)
    if n in (1, 3):
        return [list(c) for c in combinations(tiles, n)]      # GetKCombs<T>(tiles, n)
    if n == 7:
        pool = set(tiles)
        out: List[List[Pos]] = []
        for t in tiles:
            nb = [board.coord(x) for x in adjacent_tile_ids(board, t)]
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
#: #270-r1-r1 : membres nommes. L'ORDRE est celui du decompile et il est OBSERVABLE (cf. ci-dessus)
#: -- le tuple reste donc un tuple, jamais un set.
SPECIAL_MOVEMENT_EFFECT_TYPES = (EffectType.TeleportStrike_TeleportingIn,        # 0x40b = 1035
                                 EffectType.StormboyzStrike_TeleportingIn,      # 0x474 = 1140
                                 EffectType.FearOfTheUnseen_TeleportingIn,      # 0x4d6 = 1238
                                 EffectType.TitanhammerSquad_TeleportingIn)     # 0x625 = 1573

#: `<effet> -> (type WALK, type FLY)` -- les huit valeurs que la branche MOUVEMENT SPECIAL rend,
#: dans l'ordre des tests. Les VALEURS sont des `PathfinderType` (#270-r1-r1) : le commentaire les
#: nommait deja, l'ordinal ne les designait pas. Mirror sous cliquet (`probe_313`, 14 valeurs).
SPECIAL_MOVEMENT_PATHFINDER_TYPES = {
    EffectType.TeleportStrike_TeleportingIn:      # 1035 = 0x40b
        (PathfinderType.TeleportStrikeWalk, PathfinderType.TeleportStrikeFly),       # 6, 7
    EffectType.StormboyzStrike_TeleportingIn:     # 1140 = 0x474
        (PathfinderType.StormboyzStrikeWalk, PathfinderType.StormboyzStrikeFly),     # 8, 9
    EffectType.FearOfTheUnseen_TeleportingIn:     # 1238 = 0x4d6
        (PathfinderType.FearOfTheUnseenWalk, PathfinderType.FearOfTheUnseenFly),     # 10, 11
    EffectType.TitanhammerSquad_TeleportingIn:    # 1573 = 0x625
        (PathfinderType.TitanHammerSquadWalk, PathfinderType.TitanHammerSquadFly),   # 12, 13
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


def get_range_bonus_for_unit(state, board, unit_id: int, occupants: dict = None,
                             moving_team=None) -> list:
    """`IdunBattle.Core.Services.MovementQuery$$GetRangeBonusForUnit(unit, isDangerZone)` --
    mirror de la branche `isDangerZone = false` :

        result = new List<RangeBonus>();
        foreach (var effectEntity in <effets de l'unite>)
            var b = Get(effectEntity).RangeBonusForMovement(entities);   // slot d'interface 0x1f
            if (b.HasValue) result.Add(b.Value);
        return result;

    La branche `isDangerZone` (slot 0x20, `RangeBonusForDangerZone`) n'est PAS portee : son unique
    appelant natif est l'affichage de la ZONE DE DANGER, hors du perimetre du moteur.

    RAYON DE SOUFFLE NUL PAR CONSTRUCTION : `BaseEffect.create_range_bonus_for_movement` rend
    `None` par defaut, donc toute unite sans `AdrenalGlands_Effect` rend `[]` et le consommateur
    (`get_movable_tiles_for`) est alors STRICTEMENT inchange. C'est aussi le regime natif quand
    `rangeBonuses` est vide."""
    # Les trois imports que ce corps portait sont HISSES au preambule (#485-r5) : les trois etaient
    # GRATUITS, mesure en process frais. Les acces restent ATTRIBUTAIRES (forme B).
    eff_state = getattr(state, "effects", None) if state is not None else None
    if eff_state is None:
        return []                       # aucun canal d'effets -> aucun bonus (NON MESURE, pas 0)
    # ── PRE-FILTRE, et il est EXACT (il ne change AUCUN resultat, seulement le cout) ────────────
    # Ce foyer est appele a chaque calcul de mouvement du moteur, et `active_effects` EVALUE les
    # `CreateActiveCondition` -- dont certaines montent un arbre DSL complet. MESURE sur un state
    # reel (session 89, MC1_67, 6 unites) : sur le Hormagaunt, qui porte
    # `InstinctiveBehaviour_BlockMovement` (condition PORTEE), `active_effects` a lui seul coute
    # **0,358 ms** contre 0,005 ms sur une vue deja construite. Or un effet dont la classe ne
    # SURCHARGE PAS `create_range_bonus_for_movement` rend `None` par construction : il ne peut
    # jamais contribuer. On teste donc d'abord la SURCHARGE sur la liste BRUTE (aucune condition
    # evaluee), et on ne paie la vue et les conditions que s'il existe un porteur potentiel.
    # Effet MESURE, ventile (ce foyer, ms/appel) : NON-porteurs 0,010 -> 0,007 ; porteur inchange
    # (le pre-filtre ne l'ecarte pas, par construction). Le cout total de `get_movable_tiles_for`
    # reste 0,08-0,16 ms sur les non-porteurs (identique a `master`) et passe a 2,4 ms sur le
    # PORTEUR SEUL -- dont ~1,9 ms de `get_extra_reachable_tiles` (un sous-pathfinding par tuile
    # atteignable). C'est le prix de la mecanique, paye par la seule unite qui la porte.
    base_hook = _effects_base.BaseEffect.create_range_bonus_for_movement
    raw = getattr(eff_state, "by_unit", None) or {}
    if not any(getattr(type(e), "create_range_bonus_for_movement", base_hook) is not base_hook
               for e in (raw.get(int(unit_id)) or ())):
        return []
    # `active_effects` = flag `EffectComponent.IsActive @+0x5c` ET `CreateActiveCondition`, la
    # MEME conjonction que le natif (`GetEffects(unit)` ne rend que les effets actifs).
    effs = eff_state.active_effects(int(unit_id),
                                    _components.unit_state_for_effects(state, int(unit_id)))
    if not effs:
        return []
    mctx = _range_bonus.MovementBonusContext(state=state, board=board, unit_id=int(unit_id),
                                             occupants=occupants, moving_team=moving_team)
    out = []
    for e in effs:
        b = e.range_bonus_for_movement(mctx)
        if b is not None:
            out.append(b)
    return out


def movement_range_with_applied_bonus(base_range: int, range_bonuses) -> int:
    """`IdunBattle.Core.Services.MovementQuery$$MovementRangeWithAppliedBonus(unit, baseRange,
    rangeBonuses)` -- la BOUCLE, verbatim :

        foreach (var b in rangeBonuses)
            if (b.ReduceRange.HasValue) range = Math.Max(0, range - b.ReduceRange.Value);

    ⚠ **SEUL `ReduceRange` est lu** : un `ExtraRange` n'augmente JAMAIS la portee brute du
    pathfinding. C'est ce qui fait d'`AdrenalGlands` un ajout de TUILES CONDITIONNELLES
    (`GetExtraReachableTiles`) et non un `+1 Mouvement`.

    RESIDU NOMME : la queue native `if (HasTriggeredAbility(unit, 0x4b8) || HasTrait(unit, 0x418
    Stationary)) return 0;` n'est PAS reproduite ICI. Le volet `Stationary` l'est deja EN AVAL
    (`get_movable_positions_for`, #91) ; le volet `HasTriggeredAbility(0x4b8)` n'a aucun porteur
    confronte. Le porter ici changerait le resultat de `get_movable_tiles_for` pour des unites qui
    n'ont AUCUN range bonus -- un rayon de souffle que cette tranche ne mesure pas."""
    rng = int(base_range)
    for b in (range_bonuses or []):
        rr = getattr(b, "reduce_range", None)
        if rr is not None:
            rng = max(0, rng - int(rr))
    return rng


def get_extra_reachable_tiles(board, default_reachable, unit_id: int, bonus, occupants: dict,
                              moving_team, traits, has_effect, can_continue=None) -> set:
    """`IdunBattle.Core.Services.MovementQuery$$GetExtraReachableTiles(defaultReachableTiles,
    pathfinderType, unit, rangeBonus)` -- mirror 1:1 (slots `IPathfinders` LUS dans
    `data/symbols/<build>/metadata/interface_slots.tsv` : 5 = `IsValidContinuePathTile`,
    2 = `IterateReachableTiles`) :

        result = new OrderedSet<ITile>();
        foreach (var t in defaultReachableTiles) {
            if (!pathfinders.IsValidContinuePathTile(type, unit, t)) continue;
            foreach (var t2 in pathfinders.IterateReachableTiles(type, t, bonus.ExtraRange, unit)) {
                if (defaultReachableTiles.Contains(t2)) continue;
                if (bonus.ExtraRangeCondition != null && !bonus.ExtraRangeCondition(t2)) continue;
                result.Add(t2);
            }
        }
        return result;

    `default_reachable` est en IDS DE TUILE (comme tout ce foyer) ; la CONDITION, elle, recoit une
    POSITION `(col, row)` -- le port n'a pas d'objet tuile, et les deux helpers d'`AdrenalGlands`
    raisonnent en positions.

    ECART ASSUME ET MESURE : le natif alimente `defaultReachableTiles` avec le retour BRUT de
    `GetReachableTiles`, AVANT le `RemoveAll(!IsMovableTile)` ; le port collapse les deux etages
    (`walk_pathfinder.get_movable_positions` retire deja ce qu'`IsMovableTile` retirerait). Pour la
    MARCHE l'ecart est NUL (l'arete exige deja `IsWalkable`, donc aucune tuile non-walkable n'est
    jamais atteinte) ; pour le VOL il ne l'est pas -- aucun porteur volant de `RangeBonus`
    n'existe dans le build."""
    extra_range = int(getattr(bonus, "extra_range", 0) or 0)
    cond = getattr(bonus, "extra_range_condition", None)
    if extra_range <= 0:
        return set()
    out = set()
    for tid in sorted(default_reachable):
        # `IsValidContinuePathTile(type, unit, t)` : le gate #131 (`can_continue`), qui est
        # exactement celui que `movable_positions_for_unit` passe deja au pathfinder.
        if can_continue is not None and not can_continue(int(tid)):
            continue
        visited, stop = movable_positions_for_unit(
            board, int(tid), extra_range, occupants, moving_team,
            traits=traits, has_effect=has_effect, can_continue=can_continue)
        for t2 in stop:                       # `RemoveAll(!IsMovableTile)` cote port = le stop-set
            if t2 in default_reachable or t2 in out:
                continue
            if cond is not None and not cond(board.coord(int(t2))):
                continue
            out.add(int(t2))
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
    e = state.get_entity(int(unit_id)) if state is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    traits = (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None)
              else None) or []
    cc = make_can_continue(getattr(state, "effects", None), traits, board=board)
    hef = unit_has_effect_fn(state, unit_id)
    # ── ETAGE `RangeBonus` (#1048) ──────────────────────────────────────────────────────────────
    # `AnyOrFillMoveableTiles` applique les bonus de portee en DEUX temps, et le port suit le meme
    # ordre : (1) `MovementRangeWithAppliedBonus` AVANT le pathfinding (ReduceRange seul),
    # (2) `GetExtraReachableTiles` APRES, une passe par bonus. Sans bonus (`[]`, le cas de TOUTE
    # unite sans `AdrenalGlands_Effect`), les deux etages sont des no-op EXACTS.
    bonuses = get_range_bonus_for_unit(state, board, int(unit_id), occupants, moving_team)
    rng = movement_range_with_applied_bonus(int(override_range), bonuses)
    visited, stop = movable_positions_for_unit(
        board, int(from_tile), rng, occupants, moving_team,
        traits=traits, has_effect=hef, can_continue=cc,
        teleport_target_tiles=titanhammer_target_tiles_for(state, board, moving_team),
        synapse_tiles=synapse_tiles_for(state, board, moving_team))
    if not bonuses:
        return stop
    stop = set(stop)
    # `defaultReachableTiles` du natif = le retour BRUT de `GetReachableTiles` (cf.
    # `get_extra_reachable_tiles`) ; cote port c'est `visited`, et il ACCUMULE d'un bonus au
    # suivant -- le natif fait `defaultReachableTiles.AddRange(extra)` a chaque tour.
    reachable = set(visited)
    for b in bonuses:
        extra = get_extra_reachable_tiles(board, reachable, int(unit_id), b, occupants,
                                          moving_team, traits, hef, can_continue=cc)
        reachable |= extra
        stop |= extra
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
    e = state.get_entity(int(unit_id)) if state is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is not None and has_trait(getattr(sc.ctx, "traits", None), UnitTrait.Stationary):
        return []                       # `if (HasTrait(unit, 0x418)) return new OrderedSet<>()`
    tiles = list(movable_tiles)
    for t in get_unit_feet(state, unit_id):
        if t not in tiles:
            tiles.append(t)
    return get_movable_positions_from_tiles(board, tiles, get_feet_count(state, unit_id))


# ------------------------------------------------------------------------------------------------
# LIGNE DE VUE (#444) -- `MovementQuery$$GetTilesObscuringTerrain` et ses trois fonctions locales.
#
# LE CORPS A DEMENAGE dans `engine/services/line_of_sight.py` (#433-r4-r1-r1-r2) : il etait le SEUL
# foyer complet du natif, et `engine/battle_query.py` -- qui en portait un fork v1 degrade -- ne
# pouvait pas l'importer d'ici (ce module tire 178 modules `engine.*`, dont
# `entities.selectors.units`, qui importe `battle_query` : le cycle que garde #477-r35). Le module
# feuille n'importe que `hexgeo`.
#
# LE RE-EXPORT EST DELIBERE, ET SA FORME AUSSI : `MQ.PositionBoard`, `MQ.get_tiles_obscuring_terrain`
# et `MQ.draw_line_between_coordinates` sont ecrits tels quels dans `services/ability_range.py`, dans
# quatre probes et dans deux fichiers de test. Aucun patcheur ne SUBSTITUE l'un de ces noms
# (verifie : `git grep "setattr(.*movement_query"` ne rend qu'un COMMENTAIRE, sur `get_distance`),
# donc la liaison A ne desarme rien ici -- c'est la mesure qu'exige la doctrine « HISSER EN FORME B »
# avant d'accepter une liaison de NOM plutot que de MODULE.
from .line_of_sight import (            # noqa: F401  (re-export : les call-sites disent `MQ.<nom>`)
    _LINE_NUDGE,
    _determine_blocking_tiles,
    _determine_blocking_walls,
    _first_or_fallback_if_outside_playable_area,
    _tile_elevation_or_none,
    PositionBoard,
    board_is_position_inside,
    draw_line_between_coordinates,
    get_lines_between_tiles,
    get_tiles_obscuring_terrain,
    get_tiles_obscuring_terrain_from_tiles,
)


# ═══ CHEMIN CONNECTE — `GetConnectedPathTo` / `GetNumTilesMoved` (#448-r1-r1-r1-r1) ═══════════

def get_connected_path_to(board, from_id, to_id, path) -> List[int]:
    """`IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo(unit, from, to)`, ETAGE 2 :
    la DENSIFICATION du chemin que le pathfinder de l'unite vient de rendre.

    Le decompile, remis en C# (l'etage 1 -- le choix du pathfinder -- est l'argument `path`) :

        maxRange = new Nullable<UseTeleporter>(UnitExtensions.GetStat(unit, 1));
        var path = pathfinders.GetPath(unit, from, to, maxRange);     // slot itf 3
        if (path == null) return new List { from, to };               // branche DEGENEREE
        var q = new Queue(path);  var res = new List();
        var cur = q.Dequeue();
        while (true) {
            res.Add(cur);
            if (q.Count < 1) return res;
            var last = res.Last();  var next = q.Dequeue();
            if (last != null && next != null
                && GetDistance(GetTiles(last), GetTiles(next)) > 1) {
                var sub = pathfinders.GetPath(PathfinderType.Beeline, unit, last, next, null);
                for (int i = 1; i < sub.Count - 1; i++) res.Add(sub[i]);   // extremites EXCLUES
            }
            cur = next;
        }

    ⚠ CE N'EST PAS UN NO-OP. Pour un MARCHEUR ca en est un (deux noeuds consecutifs d'un chemin
    de `BasePathfinder$$FindPath` sont adjacents, donc `GetDistance <= 1` partout) -- mais le
    `FlyPathfinder` OVERRIDE `FindPath` et rend des **WAYPOINTS**, pas le chemin
    (`fly_pathfinder.find_path`). C'est ici que les sauts sont recousus, et le pathfinder qui les
    recoud est le `Beeline`, qui **traverse tout, murs compris** (`beeline_pathfinder`).

    ⚠ `maxRange` N'EN EST PAS UN : sa signature est `Nullable<UseTeleporter>` et ni
    `BasePathfinder$$FindPath` ni `FlyPathfinder$$FindPath` ne le LISENT. Argument mort sur les
    deux routes -- cf. `base_pathfinder`.

    `path` = la sortie du pathfinder (liste de tile-ids, extremites incluses) ou `None` : le port
    rend alors `[from_id, to_id]`, la branche degeneree du natif."""
    src, dst = int(from_id), int(to_id)
    if path is None:
        return [src, dst]
    q = list(int(t) for t in path)
    if not q:
        return []
    out: List[int] = []
    cur = q.pop(0)
    while True:
        out.append(cur)
        if not q:
            return out
        last = out[-1]
        nxt = q.pop(0)
        if get_distance([board.coord(last)], [board.coord(nxt)]) > 1:
            sub = _beeline.find_path(board, last, nxt)
            for mid in (sub or [])[1:-1]:
                out.append(int(mid))
        cur = nxt


def get_num_tiles_moved(path) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(path)` -- verbatim :

        return CollectionExtensions.IsNullOrEmpty(path) ? 0 : path.Count - 1;

    `Count` = NOEUDS, extremites incluses -> le nombre d'ARETES."""
    if not path:
        return 0
    return len(path) - 1
