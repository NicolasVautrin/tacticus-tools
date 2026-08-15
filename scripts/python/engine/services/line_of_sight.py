"""LIGNE DE VUE -- `IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain` et ses trois
fonctions locales, plus le trace `MovementUtil$$DrawLineBetweenCoordinates`.

TERRAIN UNIQUEMENT : aucune unite ne bloque. Le natif rend l'ENSEMBLE des tuiles qui obscurcissent
le trajet ; l'appelant conclut « obscurci » sur `Count > 0`.

⚠ POURQUOI CE MODULE EXISTE, ET POURQUOI IL EST UNE FEUILLE (#433-r4-r1-r1-r2). Ce corps vivait
dans `engine/services/movement_query.py`, qui tire **178** modules `engine.*` a l'import (tout
`engine.entities`, `pathfinding`, `runner.components`). Or `engine/battle_query.py` porte
l'invariant #477-r35 : il ne doit importer NI `engine.entities` NI rien qui l'execute -- et
`engine.entities.selectors.units` fait `from ...battle_query import is_target_tile_obscured`, donc
un import statique `battle_query -> movement_query` FERMERAIT le cycle. Le remede applique est le
(1) de la doctrine (« DEPLACER le code partage vers un module que la cascade ne re-entre pas »),
pas le (3) (« DIFFERER ») : ce module n'importe que `hexgeo` et `typing`, sa cascade `engine.*` est
`{engine, engine.services, engine.services.line_of_sight}`. `movement_query` le RE-EXPORTE, donc
aucun call-site `MQ.<nom>` ne bouge.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import hexgeo

Pos = Tuple[int, int]

# `IdunBattle.Core.Services.MovementUtil$$.cctor` : le NUDGE est un `FloatCubeCoordinate` constant
#     (1 * 10^-6, 2 * 10^-6, -3 * 10^-6)
# construit en Fix64 (`Fix64.Pow(10, -6)` x {1, 2, -3}). C'est la valeur canonique « Red Blob » : elle
# ne sert qu'a DEPARTAGER un point de lerp tombant exactement sur une arete -- la ligne 1 l'AJOUTE,
# la ligne 2 la SOUSTRAIT, d'ou les deux candidates du trajet « diagonal ». La marge (1e-6) est
# quatre ordres de grandeur au-dessus de l'erreur Fix64 (2^-32), donc le port en float64 rend les
# memes tuiles.
_LINE_NUDGE = (1e-6, 2e-6, -3e-6)


def draw_line_between_coordinates(start: Pos, end: Pos, nudge_direction: int) -> List[Pos]:
    """`IdunBattle.Core.Services.MovementUtil$$DrawLineBetweenCoordinates(result, start, end,
    nudgeDirection)` -- la surcharge AXIALE convertit en cube, appelle la surcharge CUBE, puis
    reconvertit ; ce mirror fait les deux d'un coup. VERBATIM de la surcharge CUBE :

        if (start == end) { result.Add(start); return; }        // UNE seule tuile, sans nudge
        n = CubeCoordinate.Distance(start, end);
        a = FloatCubeCoordinate(start); b = FloatCubeCoordinate(end);
        for (i = 0; i <= n; i++) {
            t = Fix64(1) / Fix64(n) * Fix64(i);
            p = a.Lerp(b, t);                                   // FloatLerp(a,b,t) = a + (b-a)*t
            p = (nudgeDirection == 1) ? p - NUDGE : p + NUDGE;
            result.Add(MovementUtil.RoundFloatCubeCoordinates(p));
        }

    `nudgeDirection` est le 4e argument, LITTERAL au call-site : `GetLinesBetweenTiles` passe `0`
    pour la ligne 1 et `1` pour la ligne 2. Les ENDPOINTS sont inclus (n+1 tuiles) -- et eux aussi
    sont nudges, ce qui est sans effet (un sommet entier reste le plus proche de lui-meme).

    ⚠ Le natif ne DEDUPLIQUE pas et n'ordonne pas autrement : la liste est le trajet de `start` vers
    `end`, dans cet ordre, ce que `DetermineBlockingTiles` consomme PAR INDICE."""
    if start == end:
        return [(start[0], start[1])]
    ax, ay, az = hexgeo.to_cube(start[0], start[1])
    bx, by, bz = hexgeo.to_cube(end[0], end[1])
    n = hexgeo.distance(start, end)
    sign = -1.0 if int(nudge_direction) == 1 else 1.0
    out: List[Pos] = []
    for i in range(n + 1):
        t = (1.0 / n) * i
        px = ax + (bx - ax) * t + sign * _LINE_NUDGE[0]
        py = ay + (by - ay) * t + sign * _LINE_NUDGE[1]
        pz = az + (bz - az) * t + sign * _LINE_NUDGE[2]
        rx, _ry, rz = hexgeo.cube_round(px, py, pz)
        out.append(hexgeo.from_cube(rx, rz))
    return out


def get_lines_between_tiles(from_tile: Pos, to_tile: Pos) -> Tuple[List[Pos], List[Pos]]:
    """`IdunBattle.Core.Services.MovementQuery$$GetLinesBetweenTiles(line1, line2, fromTile, toTile)` :

        from = TileExtensions.GetCoordinates(fromTile); to = TileExtensions.GetCoordinates(toTile);
        MovementUtil.DrawLineBetweenCoordinates(line1, from, to, 0);
        MovementUtil.DrawLineBetweenCoordinates(line2, from, to, 1);

    Les DEUX lignes vont de `from` vers `to` -- ce n'est PAS un aller-retour : seul le SIGNE du
    nudge change."""
    return (draw_line_between_coordinates(from_tile, to_tile, 0),
            draw_line_between_coordinates(from_tile, to_tile, 1))


def board_is_position_inside(board, pos: Pos) -> bool:
    """`IdunBattle.Entities.Components.BoardComponent$$IsPositionInside(column, row)` :

        return row >= 0 && column >= 0 && row < this.Height (+0x10) && column < this.Width (+0x14);

    Le `Board` du port n'a ni `Width` ni `Height` -- il porte les TUILES captees. Le rectangle est
    donc le rectangle ENGLOBANT (`max+1` sur chaque axe), memoise. C'est exact tant que le
    `boardGraph` publie tout le rectangle ; s'il en publiait moins, ce prédicat serait plus STRICT
    que le natif, et l'effet resterait borne au choix de ligne (cf.
    `_first_or_fallback_if_outside_playable_area`), jamais au verdict d'obstruction lui-meme."""
    if board is None:
        return False
    dims = getattr(board, "_playable_dims", None)
    if dims is None:
        cols = [c for (c, _r) in board.by_coord]
        rows = [r for (_c, r) in board.by_coord]
        dims = ((max(cols) + 1) if cols else 0, (max(rows) + 1) if rows else 0)
        try:
            board._playable_dims = dims
        except AttributeError:
            pass
        except Exception:
            pass
    width, height = dims
    col, row = int(pos[0]), int(pos[1])
    return 0 <= row < height and 0 <= col < width


def _first_or_fallback_if_outside_playable_area(board, first: List[Pos],
                                                fallback: List[Pos]) -> List[Pos]:
    """`MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__FirstOrFallbackIfOutsidePlayableArea` :

        board = StateExtensions.GetMatchBoard(state);
        foreach (coord in first) if (!board.IsPositionInside(coord)) return fallback;
        return first;

    Une ligne qui sort du plateau est REMPLACEE par l'autre. Appele DEUX fois, en cascade :
    `lineA = f(line1, line2)` puis `lineB = f(line2, lineA)` -- si les deux sortent, les deux
    valent `line2` puis `lineA`, donc la meme."""
    for c in (first or ()):
        if not board_is_position_inside(board, c):
            return fallback
    return first


def _tile_elevation_or_none(board, pos: Pos) -> Optional[int]:
    """`StateExtensions.GetTileAt(state, coord)` puis `TileExtensions.GetTileElevation(tile)` --
    `None` quand `GetTileAt` rend null (coordonnee hors plateau), ce que le natif traite comme
    « pas de tuile » donc NON BLOQUANTE."""
    if board is None:
        return None
    tid = board.id_at(int(pos[0]), int(pos[1]))
    return None if tid is None else board.elevation(tid)


def _determine_blocking_tiles(board, line_a: List[Pos], line_b: List[Pos], index: int,
                              elevation_to_compare: int, threshold: int, out: set) -> None:
    """`MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingTiles(index,
    elevationToCompare, ctx)` -- VERBATIM :

        cA = ctx.lineA[index];  cB = ctx.lineB[index];
        tA = GetTileAt(cA);     tB = GetTileAt(cB);
        blkA = tA != null && (GetTileElevation(tA) - elevationToCompare) >= ctx.threshold;
        blkB = tB != null && (GetTileElevation(tB) - elevationToCompare) >= ctx.threshold;
        if (tA == tB) { if (!blkA) return; out.Add(tA); }             // ligne DROITE : 1 candidate
        else          { if (!(blkA && blkB)) return; out.Add(tA); out.Add(tB); }   // FAT-LINE : ET

    Le seuil est le 4e argument de `MovementQuery$$GetTilesObscuringTerrain`, et le call-site de la
    cascade de ciblage passe `2`. La comparaison est SIGNEE et a SENS UNIQUE (`elev(mid) - ref >= 2`)
    : une tuile PLUS BASSE que la reference n'obscurcit jamais."""
    if index < 0 or index >= len(line_a) or index >= len(line_b):
        return
    ca, cb = line_a[index], line_b[index]
    ea = _tile_elevation_or_none(board, ca)
    eb = _tile_elevation_or_none(board, cb)
    blk_a = ea is not None and (ea - elevation_to_compare) >= threshold
    blk_b = eb is not None and (eb - elevation_to_compare) >= threshold
    if ca == cb:
        if not blk_a:
            return
        out.add((int(ca[0]), int(ca[1])))
        return
    if not (blk_a and blk_b):
        return
    out.add((int(ca[0]), int(ca[1])))
    out.add((int(cb[0]), int(cb[1])))


def _determine_blocking_walls(board, line_a: List[Pos], line_b: List[Pos], out: set) -> None:
    """`MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingWalls(ctx)` -- VERBATIM :

        for (i = 0; i < ctx.lineA.Count; i++) {
            tA = GetTileAt(ctx.lineA[i]);            if (tA == null) continue;
            if (!TileComponent(tA).IsWall (+0x41))   continue;
            tB = GetTileAt(ctx.lineB[i]);            if (tB == null) continue;
            if (!TileComponent(tB).IsWall)           continue;
            out.Add(tA); if (tB != tA) out.Add(tB);
        }

    TOUTE la ligne, ENDPOINTS COMPRIS (contraste avec l'elevation, qui ne teste que les deux tuiles
    adjacentes aux extremites). Meme regle de FAT-LINE : il faut que les DEUX candidates soient des
    murs."""
    for i in range(len(line_a)):
        ca = line_a[i]
        ta = board.id_at(int(ca[0]), int(ca[1])) if board is not None else None
        if ta is None or not board.is_wall(ta):
            continue
        if i >= len(line_b):
            continue
        cb = line_b[i]
        tb = board.id_at(int(cb[0]), int(cb[1]))
        if tb is None or not board.is_wall(tb):
            continue
        out.add((int(ca[0]), int(ca[1])))
        if tb != ta:
            out.add((int(cb[0]), int(cb[1])))


def get_tiles_obscuring_terrain(board, from_tile: Optional[Pos], to_tile: Optional[Pos],
                                obscuring_type: int, blocking_elevation_difference: int) -> set:
    """`IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain(from, to, obscuringType,
    blockingElevationDifference)` -- la surcharge ENTITE (une seule tuile source). VERBATIM :

        if (obscuringType == None(0)) { log(...); return empty; }
        fromTile = GetMainTile(from); toTile = GetMainTile(to);
        result = new DisposableHashSet();
        if (fromTile != null && toTile != null) {
            elevFrom = GetTileElevation(fromTile); elevTo = GetTileElevation(toTile);
            GetLinesBetweenTiles(line1, line2, fromTile, toTile);
            lineA = FirstOrFallbackIfOutsidePlayableArea(line1, line2);
            lineB = FirstOrFallbackIfOutsidePlayableArea(line2, lineA);
            if (2 < lineA.Count) {                                  // <=> distance >= 2
                if ((obscuringType & Elevation(2)) != 0) {
                    DetermineBlockingTiles(1,                elevFrom);   // voisine du FROM
                    DetermineBlockingTiles(lineA.Count - 2,  elevTo);     // voisine du TO
                }
                if ((obscuringType & Wall(4)) != 0) DetermineBlockingWalls();
            }
        }
        return result;

    `idun.meta.ObscuringType` : `None=0, Elevation=2, Wall=4, All=6`.

    **DISTANCE 1 : JAMAIS OBSCURCI** -- la ligne fait 2 tuiles, `2 < Count` est faux, et AUCUN des
    deux volets ne tourne (pas meme les murs). C'est structurel, pas un gate d'adjacence ajoute.

    ⚠ **SEULS DEUX INDEX SONT TESTES POUR L'ELEVATION, quelle que soit la longueur** : `1` (la
    voisine du FROM) et `Count - 2` (la voisine du TO). A distance 2 (`Count == 3`) les deux
    designent la MEME tuile, testee contre les deux references ; a distance 4 (`Count == 5`) la
    tuile du MILIEU n'est JAMAIS regardee. Un port qui balaierait toute la ligne serait donc PLUS
    bloquant que le natif. Le volet MURS, lui, balaie bien tous les index.

    Le port rend un SET DE POSITIONS (le natif un set d'entites-tuile) : seul son cardinal est lu
    par la cascade de ciblage, et les positions servent au diagnostic."""
    if int(obscuring_type) == 0 or from_tile is None or to_tile is None or board is None:
        return set()
    if board.id_at(int(from_tile[0]), int(from_tile[1])) is None:
        return set()
    if board.id_at(int(to_tile[0]), int(to_tile[1])) is None:
        return set()
    elev_from = _tile_elevation_or_none(board, from_tile)
    elev_to = _tile_elevation_or_none(board, to_tile)
    line1, line2 = get_lines_between_tiles((int(from_tile[0]), int(from_tile[1])),
                                           (int(to_tile[0]), int(to_tile[1])))
    line_a = _first_or_fallback_if_outside_playable_area(board, line1, line2)
    line_b = _first_or_fallback_if_outside_playable_area(board, line2, line_a)
    out: set = set()
    if len(line_a) > 2:
        if int(obscuring_type) & 2 and elev_from is not None and elev_to is not None:
            _determine_blocking_tiles(board, line_a, line_b, 1, elev_from,
                                      blocking_elevation_difference, out)
            _determine_blocking_tiles(board, line_a, line_b, len(line_a) - 2, elev_to,
                                      blocking_elevation_difference, out)
        if int(obscuring_type) & 4:
            _determine_blocking_walls(board, line_a, line_b, out)
    return out


class PositionBoard:
    """Le substrat que `get_tiles_obscuring_terrain` attend, construit depuis les CARTES PAR
    POSITION de la face DECISION (`ctx.elev_by_pos`, `ctx.is_wall_by_pos`) au lieu du `Board` de
    pathfinding, qui n'existe que cote COMBAT.

    Les trois seuls accesseurs que la cascade de ligne de vue consomme sont `by_coord` (le
    rectangle englobant de `BoardComponent$$IsPositionInside`), `id_at` et `elevation` /
    `is_wall`. L'IDENTITE de tuile y est la POSITION elle-meme : le natif compare des entites
    (`tA == tB` dans `DetermineBlockingTiles`), et deux coordonnees egales designent la meme
    entite-tuile -- la substitution est donc exacte.

    ⚠ `is_wall_by_pos` ABSENT n'est PAS « aucun mur » : c'est « le canal ne le dit pas ». Le port
    rend alors `False` partout, ce qui ne peut qu'ELARGIR la zone (un mur non vu n'obscurcit pas),
    jamais la retrecir. L'appelant qui veut distinguer les deux doit le faire avant."""

    def __init__(self, elev_by_pos, is_wall_by_pos=None):
        self._elev = {(int(p[0]), int(p[1])): v for p, v in (elev_by_pos or {}).items()
                      if p is not None and p[0] is not None and p[1] is not None}
        self._wall = {(int(p[0]), int(p[1])): bool(v)
                      for p, v in (is_wall_by_pos or {}).items()
                      if p is not None and p[0] is not None and p[1] is not None}
        self.by_coord = self._elev

    def id_at(self, col, row):
        """`IdunBattle.Entities.StateExtensions$$GetTileAt(state, column, row)` -- `None` quand
        aucune tuile n'existe a cette coordonnee, ce que le natif traite comme NON bloquant."""
        p = (int(col), int(row))
        return p if p in self._elev else None

    def elevation(self, tid):
        """`IdunBattle.Entities.TileExtensions$$GetTileElevation` (`TileComponent+0x18`)."""
        return self._elev.get(tid)

    def is_wall(self, tid) -> bool:
        """`TileComponent+0x41` (`IsWall`), publie par le `boardGraph` sous la cle `isWall`."""
        return bool(self._wall.get(tid, False))


def get_tiles_obscuring_terrain_from_tiles(board, from_tiles: Optional[Sequence[Pos]],
                                           to_tile: Optional[Pos], obscuring_type: int,
                                           blocking_elevation_difference: int) -> set:
    """`IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain(IList<IEntity> from, to,
    obscuringType, blockingElevationDifference)` -- la surcharge LISTE, celle qu'appelle la cascade
    de ciblage (le caster est passe par son EMPREINTE). VERBATIM :

        if (from == null || from.Count == 0) return new DisposableHashSet();
        if (from.Count == 1)                 return GetTilesObscuringTerrain(from[0], to, ...);
        results = [];  foreach (f in from) results.Add(GetTilesObscuringTerrain(f, to, ...));
        r = results[0];  for (i = 1; i < results.Count; i++) r.<ISPSet slot 0>(results[i]);
        return r;

    ⚠ **LE SLOT 0 D'`idun.shared.collections.ISPSet<T>` N'EST PAS RESOLU PAR SON NOM** : l'interface
    est un generique pleinement partage, absent du dump Frida, et l'index de `search_code` ne rend
    pas ses call-sites. Le port l'implemente en INTERSECTION, et c'est une lecture SEMANTIQUE, pas un
    nom lu : une union rendrait une unite multi-pieds STRICTEMENT plus aveugle qu'une unite a un
    pied (chaque pied ajouterait ses bloqueurs), ce qui contredit la doctrine du meme fichier cote
    CIBLE (`TargetingQuery$$IsTargetUnitObscured` : une unite est obscurcie ssi TOUTES ses tuiles le
    sont). INERTE pour tout caster a UN pied -- la branche `from.Count == 1` du natif court-circuite
    avant toute combinaison, et c'est le cas de la quasi-totalite du registre."""
    tiles = [t for t in (from_tiles or ()) if t is not None]
    if not tiles:
        return set()
    if len(tiles) == 1:
        return get_tiles_obscuring_terrain(board, tiles[0], to_tile, obscuring_type,
                                           blocking_elevation_difference)
    results = [get_tiles_obscuring_terrain(board, f, to_tile, obscuring_type,
                                           blocking_elevation_difference) for f in tiles]
    out = set(results[0])
    for r in results[1:]:
        out &= r
    return out
