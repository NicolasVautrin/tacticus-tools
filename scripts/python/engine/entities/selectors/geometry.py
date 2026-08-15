"""Geometrie hex par DIRECTION + selecteurs tardifs (effets, memoisation, ids visuels).

`IdunBattle.Utils.Hex` : voisin par direction, triangle, vecteur, meme elevation, ligne derriere.
Plus les noeuds construits au-dessus (`TilesBehindInLine`, `FilterContinuous`, `Cache`,
`EffectSource`...). Tranche 4 du decoupage de `selectors.py` -- cf. `__init__.py`."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ... import battle_query          # mirror UNIQUE de GetTilesBehind/IsTileValidForList (#117/#124)
from ...hex_corner import Corner      # `IdunBattleLogic.Utils.Hex.Corner` (#270-r1 volet 2)
from ...hex_edge import Edge          # `IdunBattle.Utils.Hex.Edge` (#270-r1-r1)
from ...dsl.base import (AAmountFormula, TargetsSelector, Const, _pos, _feet, _within, _is_alive,
                         _units_of, _effect_field, resolve_unit)
from ._shared import _entity_pos, _tile_positions
# Foyer UNIQUE du filtre `UnitSelectionType` (mirror `IdunBattle.Entities.UnitExtensions$$
# MatchesUnitSelectionType`), lu par `UnitsWithId` : surtout pas un 2e port du predicat. Feuille
# legere (l'enum + son derivateur), deja partagee par `selectors/units.py` et `entities/triggers.py`.
from ..unit_selection_type import UnitSelectionType, selection_ok_from_ctx
# Foyer UNIQUE du predicat `IdunBattle.Entities.UnitExtensions$$HasUnitId` (#1078), partage avec le
# volet MULTI-ID `selectors/units.py::UnitsWithIds` : `UnitsWithIdSelector$$Select` est LE MEME
# selecteur pour les deux, donc un 2e port du predicat serait une divergence garantie (#1078-r1).
# Import de niveau MODULE (forme A) et non differe : `selectors/units.py` n'importe PAS `geometry`
# -- mesure, pas presomption (cf. l'etape 0 de `probe_1078r1_units_with_id_mono.py`).
from .units import has_unit_id
# `PickFirstN` / `PickLastN` ONT DEMENAGE dans le module FEUILLE `._pick` (#1032-r2) : ils
# partagent avec `selectors/units.py::First` le foyer
# `IdunBattle.DSL.APickSelector$$AddForcedTargetsAndUpdateCandidates`, et le seul emplacement d'ou
# les DEUX tranches peuvent l'atteindre sans fermer de cycle est un module qui n'importe qu'elles.
# Le DEPLACEMENT est le premier remede de la doctrine d'import, pas un differe. Re-exportes ici
# parce que ~15 call-sites ecrivent deja `from ...selectors.geometry import PickFirstN`.
from ._pick import PickFirstN, PickLastN          # noqa: F401  (re-export, cf. ci-dessus)
from ...services.spawn_tile_shape import get_area


# --- Geometrie de TUILES par DIRECTION HEX (`IdunBattle.Utils.Hex`) -------------------------
#
# `CubeDirections..IdunBattle.Utils.Hex.CubeDirections$$.cctor` alloue SIX `int[3]` (coordonnees CUBE x/y/z aux offsets
# +0x20/+0x24/+0x28) puis les range dans l'array statique indexe par direction :
#     V0=(0,-1,1)  V1=(0,1,-1)  V2=(1,0,-1)  V3=(1,-1,0)  V4=(-1,1,0)  V5=(-1,0,1)
#     array[0..5] = [V0, V3, V2, V1, V4, V5]
# `IdunBattle.Utils.Hex.AxialCoordinate$$NeighbourAt` lit `array[dir][0]` (= dx, ajoute a la COLONNE) et
# `array[dir][2]` (= dz, ajoute au z cube `row - (col + (col&1))/2`) -> la table (dx, dz) ci-dessous.
# En offset (col,row) odd-q-UP (convention `hexgeo`, live-validee vs `boardGraph`) cela donne :
#     0 = S     1 = SE    2 = NE    3 = N     4 = NW    5 = SW
# CONFIRME LIVE (#90) : `DevastatingRefrain` bombarde `Target + dirs {3,1,5}` -> cast sur (2,3) a
# marque (2,2)=N, (3,4)=SE, (1,4)=SW.
# ⚠ #270-r1-r1 -- ce tuple RESTE en litteraux, et c'est un RESULTAT, pas un oubli : ses elements
# sont les DELTAS cubiques (-1/0/+1), qui ne designent aucun enum. C'est son INDEX qui est un
# `Edge` (le parametre `direction` d'`AxialCoordinate$$NeighbourAt`, cf. `neighbour_at` ci-dessous).
# Ecrire `Edge` sur les deltas serait FAUX, et plus faux que l'ordinal, qui lui ne ment pas.
_CUBE_DIRECTIONS = ((0, 1), (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1))


def neighbour_at(col: int, row: int, direction: int) -> tuple:
    """`IdunBattle.Utils.Hex.AxialCoordinate$$NeighbourAt` : position de la tuile voisine dans la DIRECTION HEX
    `direction` (0..5, table `_CUBE_DIRECTIONS`). Le natif passe en cube (x=col, z=row-(col+(col&1))/2),
    ajoute (dx,dz) puis reconvertit — soit exactement `hexgeo.to_cube`/`from_cube` (meme parite
    odd-q-UP : le natif calcule `col + (col & 1)` quand le flag de parite @+0x18 vaut 0)."""
    dx, dz = _CUBE_DIRECTIONS[int(direction) % 6]
    x, _y, z = hexgeo.to_cube(int(col), int(row))
    return hexgeo.from_cube(x + dx, z + dz)


# `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape` : par COIN, le COUPLE de directions
# hex des deux voisines ajoutees a la tuile-centre, dans l'ordre d'insertion du natif (lVar5 puis lVar6).
# Lu case par case sur les DEUX branches de parite du decompile (colonne paire / impaire), qui donnent
# le MEME couple de directions — la parite ne change que l'ecriture en offset.
# CLE = `IdunBattleLogic.Utils.Hex.Corner`, le type DECLARE du parametre `direction` de
# `GetTilesInTriangleShape` (#270-r1 volet 2) ; le noeud DSL amont nomme d'ailleurs son argument
# `cornerDirection`. Chaque couple encadre bien son coin : NorthWest = (North_West, North), etc.
# VALEURS = `IdunBattle.Utils.Hex.Edge`, le type DECLARE du parametre `direction`
# d'`AxialCoordinate$$NeighbourAt` (LU dans `frida/methods.tsv`) -- c'est exactement la fonction que
# `neighbour_at` ci-dessus mirroir, et a qui ces valeurs sont passees. Converti par #270-r1-r1.
# ⚠ Le NOM designe, il ne decrit pas l'ECRAN : dans le repere odd-q de `hexgeo`, `Edge.North` pointe
# vers le BAS de la grille du port (cf. la docstring d'`engine/hex_edge.py`). Chaque couple encadre
# bien son coin -- NorthWest = (North_West, North), etc.
_TRIANGLE_SHAPE_DIRECTIONS = {
    Corner.NorthWest: (Edge.North_West, Edge.North),        # (5, 0)
    Corner.NorthEast: (Edge.North, Edge.North_East),        # (0, 1)
    Corner.West:      (Edge.North_West, Edge.South_West),   # (5, 4)
    Corner.East:      (Edge.North_East, Edge.South_East),   # (1, 2)
    Corner.SouthWest: (Edge.South_West, Edge.South),        # (4, 3)
    Corner.SouthEast: (Edge.South, Edge.South_East),        # (3, 2)
}


class TilesInTriangleShape(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$TilesInTriangleShape` -> `IdunBattle.Entities.Selectors.TilesInTriangleShapeSelector$$Select`
    -> `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape` : la tuile-CENTRE + les DEUX voisines du coin
    `direction` (0..5) = un triangle de 3 hexes. `direction > 5` -> le centre SEUL (garde native
    `if (5 < param_3) goto LAB_18106bd25`). Les voisines hors-plateau sont ignorees (le natif
    n'ajoute au HashSet que les `GetTileAt` non nuls).

    `center` = selecteur (position (col,row), dict d'unite, ou liste) ; `direction` = scalaire ou noeud
    VALEUR (`.evaluate`). Retour list[int] (tile ids), centre d'abord. board None -> []."""
    def __init__(self, center: TargetsSelector, direction):
        self.center, self.direction = center, direction

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        d = self.direction.evaluate(ctx) if hasattr(self.direction, "evaluate") else self.direction
        d = int(d)
        seen, out = set(), []
        for c in _tile_positions(self.center, ctx, board):
            for p in [c] + [neighbour_at(c[0], c[1], k)
                            for k in _TRIANGLE_SHAPE_DIRECTIONS.get(d, ())]:
                t = board.id_at(p[0], p[1])
                if t is not None and t not in seen:
                    seen.add(t)
                    out.append(t)
        return out


class ThreeTileUnitSpawnShape(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$ThreeTileUnitSpawnShape(inner)` ->
    `IdunBattle.Entities.Selectors.ThreeUnitSpawnTileShapeSelector$$Select` — mirror :

        tile = inner.Select(ctx);                       // l'ANCRE (la tuile CIBLEE par le cast)
        return tile == null ? new List<TileEntity>() : GetArea(tile);

    `GetArea` essaie les directions dans l'ordre litteral `[1, 0, 5, 4, 3, 2]` et retient la
    PREMIERE aire qui passe `CorrectArea` (3 tuiles, libres, voisines deux a deux, meme
    elevation) ; aucune -> liste VIDE, et c'est CE vide que
    `...DutyEternalAbility$$GetDynamicInvalidTargetReason` traduit en refus (raison 2).

    Le corps geometrique vit dans `engine.services.spawn_tile_shape` (porte en #R30, tables de
    forme dans `engine.battle_query`) : ce noeud n'est QUE l'enveloppe DSL qui manquait — R30
    avait porte le selecteur comme FONCTION, pas comme noeud d'arbre, si bien qu'aucune ability
    ne pouvait le consommer sans recabler la geometrie a la main.

    XREFS natives EXHAUSTIVES du noeud : `DutyEternalAbility` et `AetherStrideAbility`.

    OCCUPATION : `CorrectArea` appelle `TileExtensions$$CanAddUnit(tile, state, 1, 0, 0)` -> une
    tuile sous N'IMPORTE QUEL pied est occupee ; on lit donc l'empreinte (`unit["feet"]`) de
    chaque unite VIVANTE de `ctx.units`, comme le noeud `CanAddUnit`. Retour list[int] (tile ids),
    **ancre d'abord** — l'ordre est OBSERVABLE : `AddUnitOperation` fait un `AddFoot` par tuile
    dans cet ordre, donc `feet[0] == ancre == main tile`. board None -> []."""
    def __init__(self, inner: TargetsSelector):
        self.inner = inner

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        occ = set()
        for u in ctx.units:
            if not _is_alive(u):
                continue
            for f in _feet(u):                            # `GetTiles` (repli main tile documente)
                occ.add((int(f[0]), int(f[1])))
        anchors = _tile_positions(self.inner, ctx, board)
        if not anchors:                                   # `tile == null` -> liste VIDE
            return []
        out = []
        for t in get_area(board, occ, anchors[0]):        # `Select` du natif = UNE tuile (l'ancre)
            tid = board.id_at(t[0], t[1])
            if tid is not None:
                out.append(tid)
        return out


class TileFromVector(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$TileFromVector` -> `IdunBattle.Entities.Selectors.TileFromVectorSelector$$Select` : pour CHAQUE
    tuile de `tiles`, la VOISINE dans la direction hex `direction` (`IdunBattle.Utils.Hex.AxialCoordinate$$NeighbourAt`). Le natif abandonne si le noeud-vecteur (Nullable @+0x28) n'a pas de valeur, et n'ajoute
    que les tuiles resolues (hors-plateau -> ignorees). Retour list[int] (tile ids)."""
    def __init__(self, tiles: TargetsSelector, direction):
        self.tiles, self.direction = tiles, direction

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        d = self.direction.evaluate(ctx) if hasattr(self.direction, "evaluate") else self.direction
        if d is None:
            return []
        out = []
        for c in _tile_positions(self.tiles, ctx, board):
            p = neighbour_at(c[0], c[1], int(d))
            t = board.id_at(p[0], p[1])
            if t is not None:
                out.append(t)
        return out


class DirectionTo(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$DirectionTo(from, to)` ->
    `IdunBattleLogic.Entities.VectorFormulas.DirectionToFormula$$Calculate` -- MIRROR du decompile :

        a = <from>.Select(entities).<slot 1 = premier>;      // FUN_180025bf0(1, ...)
        b = <to>.Select(entities).<slot 1 = premier>;
        if (a == null || b == null)              return Nullable<Vector>();   // VIDE
        d = AxialCoordinate.DirectionTo(GetPosition(a), GetPosition(b));      // Nullable<Edge>
        if (!d.HasValue)                         return Nullable<Vector>();   // VIDE
        return Nullable<Vector>( new Vector(d.Value, amount: 1) );

    Le natif rend donc un COUPLE `(Edge, amount)` -- c'est ce que consomme
    `IdunBattle.Core.Services.BattleQuery$$GetTileInDirection(startTile, vector)`, qui boucle
    `vector.amount` fois sur `PositionComponent$$NeighbourAt(vector.direction)`. Le port n'exprime
    que la composante `Edge` : le SEUL producteur de ce noeud (`DSLFormulas$$DirectionTo`) fige
    `amount = 1`, et le seul consommateur porte (`TileFromVector`, meme `NeighbourAt`) fait le pas
    unitaire. Retour : `int` membre d'`Edge`, ou `None` (le `Nullable` VIDE du natif) -- surtout
    pas `0`, qui est `Edge.South` et ferait fabriquer une direction la ou le natif abandonne.

    ⚠ Les deux selecteurs sont reduits a LEUR PREMIER element (slot 1), pas a leur union : le
    natif appelle deux fois le meme helper mono-entite. Sur `SolarAtomizerAbility$$GetTargetTiles`
    le `from` est `AdjacentTiles(Target) & Tiles(CasterTiles)`, qui peut porter PLUSIEURS tuiles
    quand le caster est multi-hex (Belisarius) -- la premiere gagne, comme au natif.

    `AxialCoordinate$$DirectionTo` rend un `Nullable` VIDE des que le delta n'est pas une des six
    aretes (deux tuiles non adjacentes en general) : c'est exactement le regime porte par
    `engine.entities.pathfinding.fly_pathfinder.direction_to`, dont ce noeud partage la restriction
    au PAS UNITAIRE. Hors de ce regime -> `None`."""
    def __init__(self, frm: TargetsSelector, to: TargetsSelector):
        self.frm, self.to = frm, to

    def calculate(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return None
        a = _tile_positions(self.frm, ctx, board)
        b = _tile_positions(self.to, ctx, board)
        if not a or not b:                      # `a == null || b == null` -> Nullable VIDE
            return None
        return direction_to(a[0], b[0])


# `IdunBattle.Utils.Hex.CubeDirections$$EdgeToNeighbor(diff)` -- MIRROR LITTERAL du decompile : le
# natif encode le vecteur cube ARRONDI en `code = 100*x + 10*y + z` et le compare a SIX constantes ;
# tout autre code rend un `Nullable` VIDE (branche `return 0`). La table est donc EXHAUSTIVE, et
# c'est elle qui fixe l'ordinal `IdunBattle.Utils.Hex.Edge` de chaque vecteur unitaire.
# ⚠ Recoupement avec `_CUBE_DIRECTIONS` ci-dessus (deux lectures independantes, meme resultat) :
# l'INDEX de ce tuple EST l'ordinal `Edge`. Ex. index 0 = (dx=0, dz=1) = cube (0,-1,1) -> code -9,
# et la table dit bien `Edge` 0. Les six concordent.
_EDGE_BY_CUBE_CODE = {-99: 5, -90: 4, -9: 0, 9: 3, 90: 1, 99: 2}


def direction_to(a: tuple, b: tuple):
    """`IdunBattle.Utils.Hex.AxialCoordinate$$DirectionTo(this, neighbor)` -- MIRROR du decompile,
    et **il ne se restreint PAS aux tuiles ADJACENTES** : il NORMALISE le vecteur cube `b - a` vers
    l'une des six aretes. Le corps natif, terme a terme (arithmetique `FixMath.NET.Fix64`) :

        (dx, dy, dz) = cube(b) - cube(a)
        len = Sqrt(|dx|^2 + |dy|^2 + |dz|^2)
        (nx, ny, nz) = (dx, dy, dz) / len
        if (|nx| == |ny| || |nx| == |nz|)   nx *= (Fix64.One + 1/100)      # tie-break, x FAVORISE
        if      (|nx| < |ny| && |nx| < |nz|)  nx = Fix64.Zero              # goto arrondi
        else if (|ny| < |nx| && |ny| < |nz|)  ny = Fix64.Zero              # goto arrondi
        else if (|nz| < |nx| && |nz| < |ny|)  nz = Fix64.Zero
        chaque composante : 0 -> 0 ; > 0 -> Ceiling ; < 0 -> Floor
        return CubeDirections.EdgeToNeighbor(x, y, z)                      # VIDE hors des six

    `Fix64.One` = `<Fix64 statics>+0x20` et `Fix64.Zero` = `+0x28` -- offsets LUS (le decompile
    n'a que les offsets ; les noms viennent du dump de champs, ordre `MaxValue/MinValue/One/Zero`).

    LE PORT EST EN ENTIERS, ET C'EST EXACT, pas une approximation :
      * la division par `len` est un facteur COMMUN strictement positif -- elle preserve l'ordre ET
        les egalites entre `|dx|, |dy|, |dz|`, donc les cinq comparaisons se font sur les entiers ;
      * l'arrondi vers l'exterieur se reduit a `sign()` : apres normalisation `|n_i| <= 1`, et
        `|n_i| == 1` exigerait les deux autres composantes nulles, impossible avec `dx+dy+dz == 0`
        pour un vecteur non nul. Le facteur de tie-break ne le casse pas non plus -- le maximum de
        `|dx|/len` sous cette contrainte est `sqrt(2/3) ~ 0,8165`, et `x 1,01` reste `< 1` ;
      * le tie-break `x 1,01` se code en comparant `100*|d|` (et `101*|dx|` en cas d'egalite) :
        pour des entiers `<= 100` -- tout board l'est tres largement -- aucun autre entier ne peut
        se glisser entre `|dx|` et `1,01*|dx|`, donc l'ordre STRICT est inchange et seule
        l'EGALITE bascule, ce qui est exactement l'effet voulu par le natif.

    Consequence GEOMETRIQUE, et elle est LOAD-BEARING pour `NovaCharge` : une seule composante est
    annulee, celle qui est STRICTEMENT la plus petite. Quand il n'y en a pas, les trois signes
    survivent, le code n'est aucune des six constantes, et le natif rend VIDE. C'est le cas du
    delta cube `(+-2, -+1, -+1)` -- deux des six « diagonales » du ring 2 -- ou `|dx|` vaut 2 et
    les deux autres 1 : le tie-break ne mord pas (il exige `|nx| == |ny|` ou `|nx| == |nz|`) et
    aucune composante n'est strictement minimale. Les QUATRE autres diagonales, elles, passent
    bien par le tie-break et rendent une arete.
    ⚠ Donc **10 des 12 tuiles du ring 2 normalisent, pas 6** : c'est MESURE
    (`test_1032_novacharge_callripperswarms_offline::test_etage5_...`), et cela REFUTE l'idee
    intuitive que seules les tuiles alignees produiraient une direction. Ce qui reste vrai est une
    INCLUSION : les six tuiles que le gate dynamique de `NovaCharge`
    (`...NovaChargeAbility$$IsValidLineStartTile`) accepte en font partie.

    `a == b` -> `len == 0` -> division par zero cote natif ; le port rend `None` (aucun call-site
    ne l'atteint : les deux selecteurs designent des tuiles distinctes). Retour : `int` membre
    d'`Edge` (== index de `_CUBE_DIRECTIONS`), ou `None`."""
    ax, ay, az = hexgeo.to_cube(int(a[0]), int(a[1]))
    bx, by, bz = hexgeo.to_cube(int(b[0]), int(b[1]))
    dx, dy, dz = bx - ax, by - ay, bz - az
    if dx == 0 and dy == 0 and dz == 0:
        return None                             # `len == 0` : le natif diviserait par zero
    kx, ky, kz = abs(dx) * 100, abs(dy) * 100, abs(dz) * 100
    if kx == ky or kx == kz:                    # `nx *= (One + 1/100)`
        kx = abs(dx) * 101
    if kx < ky and kx < kz:
        dx = 0
    elif ky < kx and ky < kz:
        dy = 0
    elif kz < kx and kz < ky:
        dz = 0
    code = 100 * _sign(dx) + 10 * _sign(dy) + _sign(dz)     # `EdgeToNeighbor` : 100x + 10y + z
    return _EDGE_BY_CUBE_CODE.get(code)         # hors des six -> `Nullable` VIDE


def _sign(v: int) -> int:
    """`Ceiling` (v > 0) / `Floor` (v < 0) / `Zero` (v == 0) sur une composante NORMALISEE, dont la
    valeur absolue est toujours dans `]0, 1[` -- cf. la demonstration dans `direction_to`."""
    return 0 if v == 0 else (1 if v > 0 else -1)


class Walkable(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Walkable` : garde les tuiles WALKABLE (`BattleQuery.IsWalkableTile` =
    `TileExtensions.IsWalkable`, expose par `Board.walkable`). N'exige PAS que la tuile soit LIBRE
    (c'est `CanAddUnit` qui ajoute la contrainte d'occupation). Ordre de `source` preserve."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        return [t for t in self.source.evaluate(ctx) if board.walkable(t)]


class SortReverse(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$SortReverse` -> `IdunBattle.Entities.Selectors.SortReverseSelector$$Select`
    = `System.Linq.Enumerable.Reverse(source).ToList()` — INVERSION pure de l'ordre du selecteur source
    (aucun filtre, aucune cle de tri malgre le nom).

    L'ORDRE est OBSERVABLE des qu'un consommateur itere sans re-trier : `IdunBattle.Entities.Behaviours.
    AbilityDamageBehaviour$$Execute` (famille ABILITY) enumere son selecteur TEL QUEL — contraste
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (famille ATTACK) qui pose un
    `OrderBy(b__5_0)` quand `Count > 1`. Consommateur porte :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetAffectedTiles`
    (la ligne de tir est parcourue de la tuile la PLUS LOINTAINE vers l'aim)."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        v = self.source.evaluate(ctx)
        if v is None:
            return []
        return list(reversed(list(v)))


class SortByRow(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$SortByRow(tiles, sameColumnIsRandom, additionalSorting,
    ascending)` -> `IdunBattle.Entities.Selectors.SortByRowSelector$$Select`.

    Le ctor NOMME la carte des champs, lue verbatim
    (`IdunBattle.Entities.Selectors.SortByRowSelector$$.ctor(this, tiles, state, pseudoRng,
    sameColumnIsRandom, additionalSortingFormula, ascending)`) :

        +0x18 tiles · +0x20 pseudoRng · +0x28 sameColumnIsRandom · +0x30 additionalSortingFormula
        +0x38 ascending

    et `Select` s'y branche exactement (`IdunBattle.Entities.Selectors.SortByRowSelector$$Select`) :

        ordered = (+0x38 /* ascending */ == 0) ? OrderByDescending(src, key) : OrderBy(src, key)
        if (+0x30 /* additionalSortingFormula */ != 0) ordered = ThenBy(ordered, <formule>)
        if (+0x28 /* sameColumnIsRandom      */ != 0) ordered = ThenBy(ordered, <pseudoRng>)
        return ordered.ToList()

    ⚠ `ascending` est le CINQUIEME argument de la factory, et le call-site porte lui passe **false**
    -- donc la branche prise est `OrderByDescending`. La docstring de `HadesAutocannonsAbility`
    nommait ce selecteur `asc`, ce qui etait une erreur de RE : `SortByRow(..., 0, 0, false)` trie
    par row DECROISSANTE. C'est le sens qui compte ici, puisque le meme arbre reutilise le resultat
    sous un `SortReverse` pour l'autre branche du `If`.

    CLE DE TRI. Les deux lambdas de la cle (`...SortByRowSelector.u003Cu003Ec__DisplayClass6_0$$u003CSelectu003Eb__0`
    pour `OrderBy`, `...b__1` pour `OrderByDescending`) ont le MEME corps : elles resolvent
    `IdunBattle.Entities.EntityExtensions$$GetMainTileId(s, state)` puis lisent le champ ROW de la
    tuile. Cote port, `_entity_pos` EST le mirror de `GetMainTile` (domaine MIXTE unite / id de tuile
    / position), d'ou la meme cle des deux cotes.

    ORDRE STABLE : `Enumerable.OrderBy`/`OrderByDescending` sont des tris STABLES, et `sorted` de
    Python aussi -- les ex aequo de row gardent donc l'ordre du selecteur source, des deux cotes.

    Une entite dont la position n'est pas resolvable (`_entity_pos` -> None, ex. id de tuile sans
    board) ne peut pas etre classee : elle est laissee en QUEUE dans l'ordre source, jamais
    silencieusement jetee -- le natif, lui, n'a pas ce cas (il travaille sur des entites-tuiles
    deja resolues).

    `additional_sorting` EST porte depuis #1027 -- son premier call-site est
    `IdunBattleLogic.Entities.Abilities.Active.InvocationOfMachineVengeanceAbility$$ExecuteBehaviour`
    (`SortByRow(CanAddUnit(AllTiles@+0x18), sameColumnIsRandom: 1, additionalSorting: <formule>,
    ascending: 1)`) : deux `sort` STABLES successifs realisent `OrderBy(row).ThenBy(f)` a
    l'identique, et l'element courant est lie au slot `AbilityEntities+0x20` (`Subject`/
    `ActiveTarget`), comme chez `SortByFormula`.

    ⚠ `same_column_is_random` reste un RESIDU NOMME (`#1027-r1`), et le noeud NE LEVE PLUS quand on
    le pose : le natif l'applique en DERNIER (`ThenBy(pseudoRng)`), donc il ne peut departager que
    des elements DEJA ex aequo sur (row, additionalSorting). Ne pas tirer rend alors *un* des ordres
    que le natif peut rendre -- l'ordre source, stable -- et non un ordre INVENTE. Le substrat
    manquant est le `pseudoRng` du match : `ctx.pick_randomly` existe mais mirrore
    `PickRandomAmountSelector` (tirer N elements), pas une CLE de tri par element. Consequence
    observable, bornee : quand plusieurs tuiles partagent row ET cle secondaire, le port prend
    toujours la premiere du selecteur source la ou le natif tire."""
    def __init__(self, source: TargetsSelector, same_column_is_random: bool = False,
                 additional_sorting=None, ascending: bool = False):
        self.source = source
        self.same_column_is_random = bool(same_column_is_random)
        self.additional_sorting = additional_sorting
        self.ascending = bool(ascending)

    def select(self, ctx):
        v = self.source.evaluate(ctx)
        if v is None:
            return []
        items = list(v)
        board = getattr(ctx, "board", None)
        rows = [(_entity_pos(it, board) or (None, None))[1] for it in items]
        # Les non-classables restent en QUEUE, dans l'ordre source (cf. docstring).
        classables = [(r, i) for i, r in enumerate(rows) if r is not None]
        if self.additional_sorting is not None:
            # `ThenBy(ordered, <additionalSortingFormula>)` -- SECOND critere. `sort` de Python est
            # STABLE, donc `OrderBy(row).ThenBy(f)` se realise en triant D'ABORD par la CLE
            # SECONDAIRE puis par la PRIMAIRE : l'ordre inverse (primaire d'abord) rendrait la
            # formule PRIORITAIRE sur la row, ce qui est un autre tri (mesure a l'etage 6 de
            # `test_1027_belisarius_actives_offline` : `[2, 3, 1]` au lieu de `[2, 1, 3]`).
            # L'element courant est lie au
            # slot `AbilityEntities+0x20`, celui-la meme que lisent `Subject()`/`ActiveTarget()`
            # -- meme binding que `SortByFormula` de `selectors/units.py`, et c'est ce que lit le
            # `Units(ActiveTarget@+0x68)` du call-site
            # `IdunBattleLogic.Entities.Abilities.Active.InvocationOfMachineVengeanceAbility$$
            # ExecuteBehaviour`. `ThenBy` est TOUJOURS ascendant (le natif n'expose pas de sens ici).
            def _key(ri):
                it = items[ri[1]]
                w = self.additional_sorting.evaluate(replace(ctx, subject=it, active_target=it))
                return int(w or 0)
            classables.sort(key=_key)
        classables.sort(key=lambda ri: ri[0], reverse=not self.ascending)   # +0x38 ascending
        out = [items[i] for _, i in classables]
        out.extend(items[i] for i, r in enumerate(rows) if r is None)
        return out


class Blocking(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Blocking` : garde les tuiles BLOQUANTES = le COMPLEMENT
    exact de `Walkable` sur le meme predicat de tuile.

    RE (structure, PAS le nom) : `IdunBattleLogic.Entities.DSLFactory$$Blocking` et
    `IdunBattleLogic.Entities.DSLFactory$$Walkable` allouent la MEME classe de selecteur (meme
    singleton de type) et n'appellent qu'UN ctor commun, avec un seul argument different -- le dernier
    litteral : `Walkable` passe **0**, `Blocking` passe **1**. Ghidra mislabelle ce ctor gshared
    `EffectWithTypeSelector$$.ctor` (il est FOLDE : `AtIndex`/`IsMechanical`/`MechanicalUnits`/
    `TilesWithTriggeredAbility`/`UnitsWithTriggeredAbility` l'appellent aussi) -- on lit donc la
    STRUCTURE (`+0x18 = selecteur source`, `+0x20 = le litteral`), jamais le nom.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetAffectedTiles`
    = `SortReverse(TilesBehindInLine(...)) op_Subtraction Blocking(<le meme selecteur>)` -> la ligne de
    tir PRIVEE de ses tuiles bloquantes. Ordre de `source` preserve (comme `Walkable`)."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        return [t for t in self.source.evaluate(ctx) if not board.walkable(t)]


class TilesOnSameElevation(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$TilesOnSameElevation` -> `IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select` :
    garde les tuiles de `tiles` dont l'ECART D'ELEVATION avec la tuile d'ANCRAGE (selecteur @+0x18, une
    seule tuile) est <= `max_diff` (@+0x28) — `TileExtensions.GetElevationDifference(tile, anchor) <=
    maxDiff`. Ancrage introuvable -> [] (le natif abandonne si le selecteur d'ancre ne rend rien)."""
    def __init__(self, anchor: TargetsSelector, tiles: TargetsSelector, max_diff: int = 0):
        self.anchor, self.tiles, self.max_diff = anchor, tiles, int(max_diff)

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        anchors = _tile_positions(self.anchor, ctx, board)
        if not anchors:
            return []
        at = board.id_at(anchors[0][0], anchors[0][1])
        if at is None:
            return []
        ae = board.elevation(at)
        return [t for t in self.tiles.evaluate(ctx)
                if abs(board.elevation(t) - ae) <= self.max_diff]


class EntitiesWithoutEffects(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EntitiesWithoutEffects` -> `IdunBattle.Entities.Selectors.EntitiesWithoutEffectsSelector$$Select` : garde les entites de `source` qui NE portent AUCUN des `effect_types`
    (`EntityExtensions.HasOneOfEffects(entity, types, source-flag 6)` -> exclusion).

    Domaine MIXTE, comme le natif (il itere des `IEntity` indifferenciees) : une entite-UNITE (dict) est
    testee par `ctx.has_effect`, une entite-TUILE (id int) par `ctx.tile_has_effect`. Accesseur absent ->
    « aucun effet » (degradation fidele documentee dans `DslContext`)."""
    def __init__(self, source: TargetsSelector, effect_types):
        self.source = source
        self.effect_types = [int(e) for e in (effect_types or [])]

    def select(self, ctx):
        out = []
        for e in (self.source.evaluate(ctx) or []):
            if isinstance(e, dict):
                has = any(ctx.has_effect(e, et) for et in self.effect_types) \
                    if ctx.has_effect is not None else False
            else:
                has = any(ctx.tile_has_effect(int(e), et) for et in self.effect_types) \
                    if ctx.tile_has_effect is not None else False
            if not has:
                out.append(e)
        return out


class EntitiesWithAnyEffect(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EntitiesWithAnyEffect` -> `IdunBattle.Entities.Selectors.EntitiesWithAnyEffectSelector$$Select` : JUMEAU EXACT (branche opposee) d'`EntitiesWithoutEffects` -- garde les entites de `source`
    qui portent AU MOINS UN des `effect_types` (`EntityExtensions.HasOneOfEffects(entity, types, ...,
    source-flag @+0x30)` -> INCLUSION ; le `Without` fait l'exclusion sur le MEME appel).

    Domaine MIXTE comme le natif (il itere des `IEntity` indifferenciees) : entite-UNITE (dict) testee par
    `ctx.has_effect`, entite-TUILE (id int) par `ctx.tile_has_effect`. Accesseur absent -> « aucun effet »
    -> l'entite est ECARTEE (symetrique fidele de la degradation d'`EntitiesWithoutEffects`, qui garde).

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$GetAttackTargets`
    (`EntitiesWithAnyEffect(Enemies(caster, allUnits), 0x462=1122 Markerlight)`)."""
    def __init__(self, source: TargetsSelector, effect_types):
        self.source = source
        self.effect_types = [int(e) for e in (effect_types or [])]

    def select(self, ctx):
        out = []
        for e in (self.source.evaluate(ctx) or []):
            if isinstance(e, dict):
                has = any(ctx.has_effect(e, et) for et in self.effect_types) \
                    if ctx.has_effect is not None else False
            else:
                has = any(ctx.tile_has_effect(int(e), et) for et in self.effect_types) \
                    if ctx.tile_has_effect is not None else False
            if has:
                out.append(e)
        return out


class AtIndex(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$AtIndex(entities, index)` ->
    `IdunBattle.Entities.Selectors.PickAtIndexSelector$$Select` : l'element a `index` de la source
    (ordre TEL QUEL), `[]` si hors borne. Retour list de 0/1 element (PAS un element nu).

    ⚠ Le `.ctor` alloue par la factory porte dans Ghidra le nom
    `IdunBattle.Entities.Selectors.WalkableTilesSelector$$.ctor` : corps DEDUPLIQUE (meme signature
    `(state, source, int)`), pas l'identite de la classe -- on cite donc la FACTORY.

    ⚠ **CE NOEUD EST LE SEUL PORT DE `PickAtIndexSelector`** (#1032-r2). La docstring d'avant
    affirmait que `selectors.units.First` mirrorait le MEME selecteur « atteint par une AUTRE
    factory `DSLFactory$$First(source[, index])` » : cette factory N'EXISTE PAS dans le build
    (`IdunBattleLogic.Entities.DSLFactory$$` n'y porte que 5 methodes, aucun selecteur), et le
    `First` natif -- `IdunBattleLogic.Entities.DSLSelectors$$First(entities, amount,
    ignoreForcedTargets)`, 2 surcharges -- construit un `PickFirstNSelector`, pas celui-ci.
    `units.First` est donc devenu ce qu'il mirrore vraiment : une sous-classe de `PickFirstN`.
    Le voisin a ne pas confondre reste `PickFirstN` (les `amount` PREMIERS elements), qui vit
    desormais dans `._pick` et est re-exporte en tete de ce module.
    ORDRE DE GRANDEUR (census PE, build `t6dpr4k06g`) : `AtIndex` = **6** call-sites dans tout le
    binaire, `First` = **145**.

    CONSOMMATEUR PORTE : `IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase$$
    ExecuteBehaviour`, qui deroule sa vague sur les 3 tuiles de la ligne par `AtIndex(tiles, i)`
    et `AtIndex(tiles, i + 1)` (le maillon SUIVANT, pour decider du `FinishAttack`)."""
    def __init__(self, source: TargetsSelector, index: int = 0):
        self.source, self.index = source, int(index)

    def select(self, ctx):
        lst = list(self.source.evaluate(ctx))
        return [lst[self.index]] if 0 <= self.index < len(lst) else []


class PickRandomly(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$PickRandomly(entities, amount, allowDuplicates,
    maxDuplicatesAllowed, ignoreForcedTargets)` -> `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select`.

    Le NOEUD ; la BOUCLE native (et sa loi de consommation RNG) vit dans le foyer UNIQUE
    `runner/abilities/loki/splash.py::_pick_randomly_n`, mirror 1:1 deja valide live (#130 / #215) --
    on delegue au lieu de la reecrire. Rappel de la loi qui compte : le natif tire
    `min(len(pool), amount)` fois **meme quand le pool tient deja dans `amount`** (aucun court-circuit),
    et un tirage sur un pool de 1 CONSOMME quand meme un `genrand_int32`. Court-circuiter desaligne
    tout le flux RNG en aval.

    L'ordre de `source` est celui du selecteur natif (`source.Select(entities).ToList()`, aucun tri
    intermediaire) : ce noeud ne le retrie PAS -- c'est ce qui decide QUI est piquee des que
    `len(pool) > amount`.

    `ctx.pick_randomly` absent (contexte hors runner : pas de PRNG de bataille) -> repli DETERMINISTE
    sur les `amount` premiers elements, ZERO tirage. C'est une DEGRADATION assumee et nommee, pas un
    mirror : elle garde le selecteur utilisable en prediction/tests unitaires, ou aucun etat RNG
    n'existe. Le chemin RUNNER, lui, passe toujours par l'accesseur.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$GetTargetSelector`
    (DEUX instances distinctes : la primaire sur `Repairable(...)`, le fallback sur
    `UnitsWithNegativeEffects(...)`)."""
    def __init__(self, source: TargetsSelector, amount=1, allow_duplicates: bool = False,
                 max_duplicates: int = 0x7FFFFFFF, ignore_forced_targets: bool = False):
        self.source, self.amount = source, amount
        self.allow_duplicates = bool(allow_duplicates)
        self.max_duplicates = int(max_duplicates)
        self.ignore_forced_targets = bool(ignore_forced_targets)

    def select(self, ctx):
        n = self.amount.evaluate(ctx) if hasattr(self.amount, "evaluate") else self.amount
        n = int(n or 0)
        pool = _units_of(self.source, ctx)
        if n <= 0 or not pool:
            return []
        f = getattr(ctx, "pick_randomly", None)
        if f is None:
            return list(pool)[:n]                  # repli DETERMINISTE (aucun PRNG) -- cf. docstring
        return f(pool, n, self.allow_duplicates, self.max_duplicates)


class Randomize(PickRandomly):
    """`IdunBattleLogic.Entities.DSLSelectors$$Randomize(source)` -- MIRROR du decompile, qui alloue
    le MEME `IdunBattle.Entities.Selectors.PickRandomAmountSelector` que `PickRandomly` avec des
    arguments FIXES, lus au call-site :

        PickRandomAmountSelector..ctor(this, state, source, 0x7fffffff, random,
                                       allowRepeat = 0, maxRepeats = 0x7fffffff, skipForced = 0)

    (mapping des champs relu dans `PickRandomAmountSelector$$.ctor`, cf.
    `runner/abilities/loki/splash.py::_pick_randomly_n`.) `amount = 0x7fffffff` sans repetition ->
    la boucle native pioche jusqu'a EPUISEMENT du pool : c'est une **PERMUTATION ALEATOIRE COMPLETE**
    de `source`, pas un echantillon. Consommation PRNG = **`len(pool)` tirages**, bornes decroissantes
    `len(pool)`, `len(pool)-1`, ... 1 -- le dernier tirage (`range == 1`) consomme quand meme un
    `genrand_int32` (loi #130/#215). Court-circuiter desaligne tout le flux RNG en aval.

    A quoi il sert, chez son consommateur porte
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.EmpyricAmbushAbility$$ExecuteBehaviour`) : il est
    enveloppe par `SortTilesByUtility` puis `First`, et
    `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` finit par
    `Enumerable.OrderBy(tiles, utilite)` -- un tri **STABLE**. L'ordre aleatoire ne survit donc que
    sur les EX AEQUO d'utilite : c'est exactement ce qui rend le choix de tuile d'atterrissage
    non deterministe quand plusieurs tuiles adjacentes se valent."""
    def __init__(self, source: TargetsSelector):
        super().__init__(source, amount=0x7FFFFFFF, allow_duplicates=False,
                         max_duplicates=0x7FFFFFFF, ignore_forced_targets=False)


class Otherwise(TargetsSelector):
    """`IdunBattle.DSL.TargetsSelector$$Otherwise(primary, fallback)` : le natif alloue un selecteur a DEUX
    branches (ctor : `+0x18 = primary`, `+0x20 = fallback`) qui rend `primary` s'il produit quelque chose,
    `fallback` sinon -- le FALLBACK d'un selecteur potentiellement VIDE.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$PickTiles`
    (`TilesUnitCanAttackFrom(free, caster, unitId, 1).Otherwise(free)` = si aucune tuile libre ne permet au
    summon d'attaquer la cible, on retombe sur TOUTES les tuiles libres adjacentes)."""
    def __init__(self, primary: TargetsSelector, fallback: TargetsSelector):
        self.primary, self.fallback = primary, fallback

    def select(self, ctx):
        v = self.primary.evaluate(ctx)
        if v:
            return v
        return self.fallback.evaluate(ctx)


class TilesBehindInLine(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$TilesBehindInLine(from, to, settings)` -> `IdunBattle.Entities.Selectors.TilesBehindInLineSelector$$Select` : les tuiles ALIGNEES au-dela de `to`, en partant de `to`, dans la direction
    `from -> to`. Geometrie CUBE droite (parite-INDEPENDANTE) DEJA live-reconciliee par les deux autres
    consommateurs portes du meme noeud (`IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$GetAffectedTiles`
    `_line_tiles`, `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInLine`) :
    `tile_k = cube(to) + k*dir`, `dir = cube(to) - cube(from)`, `k = 0..` -- la 1re tuile rendue EST `to`.

    `max_count` = le `Direct(n)` natif quand il est fourni (Excruciating : `nrOfTiles` ; DeathOnTheWind :
    `Get(nrOfTiles-1)`) ; None = pas de borne -> on prolonge JUSQU'AU BORD du plateau. Retour list[int]
    (tile ids). `from`/`to` normalises par `_tile_positions` (unite/id/position). board None -> [].

    GATE PAR TUILE — `IdunBattle.Core.Services.TileUtil$$IsTileValidForList(tile, refTile, checkWalkable,
    checkElevation=1)` (MIRROR ; le 4e argument est le litteral `1` dans `GetTilesBehind`) :
        if tileComponent+0x41 != 0            -> false
        if !checkWalkable                     -> return tileComponent+0x40 == 0
        if !TileExtensions.IsWalkable(tile)   -> false
        if refTile != null                    -> return |elev(refTile) - elev(tile)| < 2
    La ligne S'ARRETE au 1er echec (`return list`) — c'est un PREFIXE, pas un filtre.

    `check_walkable` / `update_reference` = les DEUX bools de la struct `settings` que chaque call-site
    alloue et passe a `IdunBattleLogic.Entities.DSLFactory$$TilesBehindInLine` (champs `+0x10` / `+0x11`),
    relayes par `IdunBattle.Entities.Selectors.TilesBehindInLineSelector$$Select` a
    `IdunBattle.Core.Services.BattleQuery$$GetTilesBehind(from, to, bool1, bool2, maxCount)` :
      * `+0x10 = check_walkable` : gate `IsWalkable` **ET** — c'est la consequence NON EVIDENTE —
        l'activation du gate d'ELEVATION (qui vit DANS la branche walkable de `IsTileValidForList`).
      * `+0x11 = update_reference` : `GetTilesBehind` re-affecte la tuile de REFERENCE d'elevation a la
        DERNIERE tuile ajoutee (marche pas-a-pas) au lieu de garder la tuile d'origine.
    INVENTAIRE des call-sites (lu au decompile, PAS deduit) :
      | ability | +0x10 | +0x11 |
      | `DarkTalonStrikeAbility$$GetTilesInLine`            | 1 | 1 |
      | `ExcruciatingFrequenciesAbility$$GetAffectedTiles`  | 1 | 1 |
      | `DeathOnTheWindAbility$$GetTilesInLine`             | 0 | 1 |
      | `ThriceBlessedConflagrationAbility$$GetTilesInLine` | 0 | 0 |
    Defauts `False/False` = le comportement HISTORIQUE (ThriceBlessed, inchange).

    ⚠ **LE RESIDU DE LA BRANCHE `check_walkable == False` EST REPARE (#889-r6), et il n'etait PAS
    inerte.** Le natif teste `tileComponent+0x41` (le MUR) INCONDITIONNELLEMENT et met `IsWalkable`
    DANS la branche `checkWalkable` ; le port appliquait `board.walkable` (qui FOND les deux)
    inconditionnellement, donc il COUPAIT la ligne sur toute tuile `Block` ou `Unplayable`. Mesure
    directe sur `CE6_boss` : le natif MARQUE `(6,4)` et `(6,6)`, deux `Unplayable`
    (`walkable = false`, `isWall = false`). Ce selecteur cable donc desormais `is_wall_at` depuis le
    champ `isWall` du `boardGraph`, et `battle_query.is_tile_valid_for_list` applique l'ORDRE natif.
    La redaction precedente justifiait l'inertie par le `FilterContinuous(HasUnit & AreEnemies)` en
    aval de ses deux call-sites d'alors -- vrai pour eux, faux des qu'un consommateur COMPTE les
    tuiles : `...InstrumentsOfVengeanceAbility$$GetEffectBehavior` fait de cette longueur une CLE DE
    TRI, et la ligne choisie n'etait pas la meme.
    Ce qui reste NON PORTE, nomme : `+0x40` lui-meme -- aucun champ du `boardGraph` ne le publie
    (`walkable`, `isWall`, `isTemporary`, `isInFog`, `tileDefId` : aucun ne coincide avec la mesure
    ci-dessus). Le gate reste INERTE, borne SUPERIEURE.

    La MARCHE elle-meme (`GetTilesBehind` + `IsTileValidForList`) vit dans `engine.battle_query.
    get_tiles_behind` : mirror UNIQUE partage avec les deux feuilles de DECISION (#124), en domaine
    POSITION. Ce selecteur n'en est que l'adaptateur tile-id (`board.id_at` / `board.walkable` /
    `board.elevation`)."""
    def __init__(self, frm: TargetsSelector, to: TargetsSelector, max_count=None,
                 check_walkable: bool = False, update_reference: bool = False):
        self.frm, self.to, self.max_count = frm, to, max_count
        self.check_walkable = bool(check_walkable)
        self.update_reference = bool(update_reference)

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        src = _tile_positions(self.frm, ctx, board)
        dst = _tile_positions(self.to, ctx, board)
        if not src or not dst:
            return []
        n = self.max_count
        n = (n.evaluate(ctx) if hasattr(n, "evaluate") else n)
        n = int(n) if n is not None else None
        def _mur(p):
            """`tileComponent+0x41` -- le champ `isWall` du `boardGraph`, TRI-ETAT : absent (board
            monte a la main dans un test unitaire) -> `False`, gate INERTE, borne SUPERIEURE."""
            t = board.by_id.get(board.id_at(p[0], p[1]))
            return bool((t or {}).get("isWall", False))

        positions = battle_query.get_tiles_behind(
            src[0], dst[0], max_count=n,
            check_walkable=self.check_walkable, update_reference=self.update_reference,
            walkable_at=lambda p: board.walkable(board.id_at(p[0], p[1])),
            elevation_at=lambda p: board.elevation(board.id_at(p[0], p[1])),
            tile_exists=lambda p: board.id_at(p[0], p[1]) is not None,
            is_wall_at=_mur)
        return [board.id_at(p[0], p[1]) for p in positions]


class EdgeTilesByDirection(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$EdgeTilesByDirection(direction)` ->
    `IdunBattle.Entities.Selectors.EdgeTilesByDirectionSelector$$Select` : le BORD du plateau
    designe par une direction hex -- une ligne entiere de tuiles, pas un voisinage.

    MIRROR du decompile, lu branche par branche. Le champ `+0x18` est une formule VECTEUR
    (`IdunBattle.Entities.Selectors.EdgeTilesSelector$$.ctor(state, battleQuery, selector)`, meme
    corps deduplique pour les quatre fabriques `CenterTiles`/`CornerTiles`/`EdgeTiles`/
    `EdgeTilesByDirection`) ; `Select` en prend la valeur `Nullable<Vector>`, **ne lit que le champ
    `direction`** (les 4 premiers octets, compares a 0..5) et balaie une bordure :

        v = (<+0x18> as IVectorFormula).Calculate(entities);
        if (!v.HasValue)                              return <liste vide>;
        switch (v.Value.direction) {
          case 3:            for (c = 0; c < COLS; c++) add( GetTileAt(c, 0) );
          case 0:            for (c = 0; c < COLS; c++) add( GetTileAt(c, ROWS - 1) );
          case 1: case 2:    for (r = 0; r < ROWS; r++) add( GetTileAt(COLS - 1, r) );
          case 5: case 4:    for (r = 0; r < ROWS; r++) add( GetTileAt(0, r) );
          default:                                    return <liste vide>;
        }

    `GetTileAt(column, row)` est la surcharge a DEUX `int` d'`IdunBattle.Core.Services.BattleQuery`
    (l'autre prend une `AxialCoordinate`) ; une tuile absente rend `null` et n'est PAS ajoutee --
    c'est ce que reproduit le `board.id_at(...) is not None` ci-dessous, et c'est ce qui rend le
    noeud correct sur un plateau non rectangulaire.

    ⚠ **LES DEUX BORNES DE BOUCLE SONT NOMMEES PAR LEUR USAGE, PAS PAR UN NOM DE METHODE.** Les
    deux slots d'`IBattleQuery` (`<slot 0x6a>` et `<slot 0x6b>`) n'ont pas de symbole nomme dans
    ce build ; ce qui les identifie est la POSITION de leur valeur dans `GetTileAt(column, row)` :
    le slot `0x6b` borne l'argument COLONNE (branches `South` / `North`) et fournit `COLS - 1`
    comme colonne (branches `North_East`/`South_East`) ; le slot `0x6a` borne l'argument LIGNE et
    fournit `ROWS - 1` comme ligne. Le port les derive du plateau (`max(col) + 1`, `max(row) + 1`),
    seule lecture disponible offline -- c'est une EQUIVALENCE, pas une transcription de symbole.

    ⚠ **LE PORT MIRRORE L'ORDINAL, PAS LE LIBELLE D'ECRAN.** Le `switch` natif compare des
    `IdunBattle.Utils.Hex.Edge` bruts, et le natif ne passe JAMAIS par `AxialCoordinate$$NeighbourAt`
    ici : la table `_CUBE_DIRECTIONS` de ce module (dont l'index est un `Edge` et dont le rendu
    ECRAN est INVERSE, cf. son commentaire) n'entre pas dans ce noeud. Traduire `Edge.North` en
    « bas de la grille » avant de choisir la ligne serait une correction de repere que le natif ne
    fait pas -- elle echangerait les deux bordures opposees.

    ⚠ **`North_East` et `South_East` rendent LA MEME bordure**, et de meme `South_West`/`North_West`
    -- le natif fond deux aretes par cote sur l'axe des colonnes. Ce n'est pas une simplification du
    port : les deux `case` partagent litteralement le meme bloc dans le decompile. C'est ce qui fait
    que les deux branches de `...InstrumentsOfVengeanceAbility$$ExecuteBehaviour` (`{1, 5}` et
    `{2, 4}`) visent le MEME couple de bordures (droite puis gauche) et ne different que par la
    DIRECTION de la ligne tiree depuis chacune (`EdgeExtensions$$Rotate(direction, 3)`).

    `direction` = noeud VALEUR ou entier brut. `None` (le `Nullable` VIDE du natif) -> `[]`, jamais
    une bordure par defaut. Retour : list[int] (tile ids)."""
    def __init__(self, direction):
        self.direction = direction

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        d = self.direction.evaluate(ctx) if hasattr(self.direction, "evaluate") else self.direction
        if d is None:                                   # `!v.HasValue` -> liste VIDE
            return []
        d = int(d)
        coords = getattr(board, "by_coord", None)
        if not coords:
            return []
        cols = max(c for c, _ in coords) + 1            # borne du slot `0x6b` (argument COLONNE)
        rows = max(r for _, r in coords) + 1            # borne du slot `0x6a` (argument LIGNE)
        if d == int(Edge.South):
            cells = [(c, 0) for c in range(cols)]
        elif d == int(Edge.North):
            cells = [(c, rows - 1) for c in range(cols)]
        elif d in (int(Edge.North_East), int(Edge.South_East)):
            cells = [(cols - 1, r) for r in range(rows)]
        elif d in (int(Edge.South_West), int(Edge.North_West)):
            cells = [(0, r) for r in range(rows)]
        else:                                           # `default:` du switch natif
            return []
        out = []
        for c, r in cells:
            t = board.id_at(c, r)
            if t is not None:                           # `GetTileAt` -> null : non ajoutee
                out.append(t)
        return out


class NextTileInLine(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$NextTileInLine(origin: ITargetsSelector,
    direction: IVectorFormula)` -- MIRROR du decompile. Le noeud n'a PAS de selecteur a lui : il
    construit le MEME `IdunBattle.Entities.Selectors.TilesBehindInLineSelector` que
    `TilesBehindInLine` ci-dessus, dans sa variante **IVectorFormula**, avec :

        settings  = <TilesBehindInLineSettings NEUF>   -> `+0x10 = 0`, `+0x11 = 0`
        maxAmount = <DSLFormulas>+0x20 = `Direct(1)`   (champ partage, deja LU par #505)

    et `IdunBattle.Entities.Selectors.TilesBehindInLineSelector$$Select` traite cette variante en
    MATERIALISANT la tuile d'arrivee AVANT de marcher :

        to = query.<slot 95 = GetTileInDirection>(origin, direction.Calculate(entities))
        return query.<slot 84 = GetTilesBehind>(origin, to, settings+0x10, settings+0x11, maxAmount)

    et `IdunBattle.Core.Services.BattleQuery$$GetTileInDirection(startTile, vector)` boucle
    `vector.amount` fois sur `PositionComponent$$NeighbourAt(vector.direction)` -- or le SEUL
    producteur de vecteur porte (`DSLFormulas$$DirectionTo`) fige `amount = 1`. `to` est donc la
    VOISINE de `origin` dans la direction, ce que rend exactement `TileFromVector`.

    `maxAmount = 1` et « la 1re tuile rendue EST `to` » (cf. `TilesBehindInLine`) : le noeud rend
    donc AU PLUS UNE tuile -- la voisine -- et RIEN quand elle sort du plateau (`GetTileInDirection`
    rend null -> le natif rend une liste VIDE) ou quand elle echoue au gate `IsTileValidForList`.
    C'est une COMPOSITION de deux noeuds deja portes, exactement comme le natif compose deux appels
    de service : aucune geometrie n'est reecrite ici."""
    def __init__(self, origin: TargetsSelector, direction):
        self.origin, self.direction = origin, direction

    def select(self, ctx):
        return TilesBehindInLine(self.origin, TileFromVector(self.origin, self.direction),
                                 max_count=1).evaluate(ctx)


class NextTileClockwise(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$NextTileClockwise(fromTile, aroundTile)` ->
    `IdunBattle.Entities.Selectors.NextTileInCircleSelector$$Select` -- MIRROR du decompile :

        around = <aroundTile @+0x20>.<slot 12 = SelectSingle>(entities)
        result = new List()
        if (from != null && from.Any() && around != null)
            foreach (e in <fromTile @+0x18>.<slot 10>(entities))
                d = AxialCoordinate.DirectionTo(around.Position, e.Position).Value
                d = EdgeExtensions.Next(d, <+0x28 direction>)
                d = EdgeExtensions.Next(d, <+0x28 direction>)          # DEUX fois, meme argument
                t = query.<slot 95 = GetTileInDirection>(around, new Vector(d, 1))
                if (t != null) result.Add(t)
        return result

    et `IdunBattle.Utils.Hex.EdgeExtensions$$Next(edge, direction)` =
    `(edge + (direction != 0 ? -1 : +1)) mod 6` (le natif rattrape les deux debordements a la main).

    `<+0x28>` est le 5e argument du ctor `NextTileInCircleSelector..ctor(state, battleQuery,
    fromTile, aroundTile, direction: IdunBattle.Utils.Hex.RotationDirection)`, et
    `DSLSelectors$$NextTileClockwise` le passe a **0** -- LU AUX OCTETS (`xor eax, eax` puis
    `mov [rsp+0x28], eax` juste avant le `call`, ghidra ne resolvant pas cet immediat).
    `RotationDirection.Clockwise = 0` (`data/symbols/<build>/frida/enums.tsv`), d'ou le nom du
    noeud, et `Next` avance donc de **+1 par appel, soit +2 crans au total** (120 degres).

    Le noeud rend la voisine d'`aroundTile` dans la direction `(around -> e) + 2` : pour chaque
    element de `fromTile`, UNE tuile du ring 1 d'`aroundTile`. Domaine de sortie : ids de tuile.

    DEGRADATION NOMMEE : le natif appelle `Nullable.get_Value` sur la direction, donc il LEVERAIT
    si `DirectionTo` rendait vide (deux tuiles dont le vecteur cube ne normalise sur aucune arete,
    cf. `direction_to`). Le port SAUTE l'element au lieu de lever -- aucun call-site porte ne
    l'atteint (`NovaCharge` passe par le gate `IsValidLineStartTile`, qui ne laisse que des tuiles
    ALIGNEES sur un axe du centre)."""
    def __init__(self, from_tile: TargetsSelector, around_tile: TargetsSelector):
        self.from_tile, self.around_tile = from_tile, around_tile

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        around = _tile_positions(self.around_tile, ctx, board)      # `SelectSingle`
        if not around:
            return []
        origin = around[0]
        out = []
        for p in _tile_positions(self.from_tile, ctx, board):
            d = direction_to(origin, p)
            if d is None:                       # cf. DEGRADATION NOMMEE ci-dessus
                continue
            d = (int(d) + 1) % 6                # `EdgeExtensions.Next(d, Clockwise)`
            d = (d + 1) % 6                     # ... appele une SECONDE fois
            t = board.id_at(*neighbour_at(origin[0], origin[1], d))
            if t is not None:
                out.append(t)
        return out


class CenterTiles(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$CenterTiles(entities)` ->
    `IdunBattle.Entities.Selectors.CenterTilesSelector$$Select` -> `IBattleQuery` slot **93**
    `IdunBattle.Core.Services.BattleQuery$$GetCenterTiles(tiles)` -- MIRROR du decompile :

        best = new OrderedSet() ; y = Fix64.MaxValue          # `<Fix64 statics>+0x10`
        foreach (e in tiles)
            d = GetAverageDistance(<liste a un element : e>, tiles, defaultValue: 0)
            if (d < y)  { y = d ; best.Clear() }
            if (d <= y) best.Add(e)
        return best

    = les tuiles de la source dont la distance MOYENNE a TOUTE la source est minimale, c'est-a-dire
    son (ou ses) CENTRE(S) geometrique(s). `OrderedSet` -> dedupliquees, ordre d'insertion.

    ⚠ La moyenne est celle de `BattleQuery$$GetAverageDistance`, donc a DIVISION ENTIERE -- des
    tuiles differentes peuvent partager la meme moyenne tronquee et sortir ENSEMBLE. Le
    `defaultValue` vaut **0** ici (et non `10000` comme dans `AverageDistance`) : il n'est atteint
    que si la source est vide, auquel cas la boucle ne tourne pas de toute facon.

    Unique consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    NovaChargeAbility$$GetLineTiles` (`CenterTiles(CasterTile@DSLSelectors+0x58)` = la tuile
    CENTRALE d'un caster multi-hex -- `tauBossRiptide` en occupe sept). Domaine : ids de tuile."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        tiles = _tile_positions(self.source, ctx, board)
        best_avg = None
        out = []
        for p in tiles:
            if not tiles:
                continue
            total = sum(hexgeo.distance(q, p) for q in tiles)
            avg = total // len(tiles)           # `GetAverageDistance`, division ENTIERE
            if best_avg is None or avg < best_avg:
                best_avg = avg
                out = []
            if avg <= best_avg:
                out.append(p)
        seen, ids = set(), []                   # `OrderedSet` : dedup, ordre d'insertion
        for p in out:
            t = board.id_at(p[0], p[1])
            if t is not None and t not in seen:
                seen.add(t)
                ids.append(t)
        return ids


class EdgeTiles(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$EdgeTiles(entities)` ->
    `IdunBattle.Entities.Selectors.EdgeTilesSelector$$Select` -- MIRROR du decompile :

        foreach (t in <+0x18>.SelectTiles(entities))
            if (battleQuery@<+0x20>.<slot 0xa2 = IsEdgeTile>(t))  out.Add(t);

    `IdunBattle.Core.Services.BattleQuery$$IsEdgeTile(tile)` :

        return EntityExtensions.IsTile(tile)
            && GetSurroundingTilesCount(tile, distance: 1, onlyEmptyOrSteppable: false,
                                        onlyWalkable: false, onlyMovable: false,
                                        includeCenter: TRUE) <= 5;

    ⚠ **LES SIX LITTERAUX SONT LUS A L'ASSEMBLEUR, PAS DANS LE PSEUDO-C.** Ghidra laisse deux des
    arguments en registres non resolus (`in_stack_*`) et affiche le test comme `< 6`. Le decodage du
    prologue tranche : `r8d = 1` (distance), `r9d = 0` (onlyEmptyOrSteppable),
    `[rsp+0x20] = 0` (onlyWalkable), `[rsp+0x28] = 0` (onlyMovable), `[rsp+0x30] = 1`
    (includeCenter), puis `cmp eax, 5 ; setle`.

    ⚠ **`includeCenter = true` DECALE LE SEUIL D'UN CRAN, et c'est observable.** Le compte inclut la
    tuile elle-meme, donc `count <= 5` equivaut a **`voisins <= 4`** : une tuile a CINQ voisins
    n'est **PAS** une tuile de bord au sens du natif. Lire `< 6` comme « moins de 6 voisins » aurait
    elargi la selection de tout le liseré interne du plateau.

    ⚠ **Aucun filtre de marchabilite ni d'occupation** (`onlyWalkable`/`onlyMovable`/
    `onlyEmptyOrSteppable` valent tous `false`) : le comptage porte sur les tuiles qui EXISTENT.
    C'est ce qui rend le noeud composable avec le `CanAddUnit` que son call-site place EN AMONT
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.CallInReinforcementsAbility$$CreateBehaviour` =
    `EdgeTiles(CanAddUnit(AllTiles@<DSLSelectors+0x18>))`) -- et non l'inverse.

    Le voisinage compte est celui d'`IdunBattle.Core.Services.TileQuery$$IterateSurroundingTiles`
    (DISQUE cube de rayon 1, sans porte d'elevation), donc `battle_query.get_surrounding_tiles`, et
    non le ring-1 `IterateAdjacentTiles` du `ConnectivityComponent`.

    DOMAINE : ids de tuile en entree comme en sortie, ordre de `source` preserve. `board` -> `[]`."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        exists = (lambda p: board.id_at(p[0], p[1]) is not None)
        out = []
        for t in self.source.evaluate(ctx) or []:
            c = board.coord(t)
            if c is None:
                continue
            n = len(battle_query.get_surrounding_tiles(
                (c[0], c[1]), radius=1, include_center=True, check_walkable=False,
                tile_exists=exists, only_empty_or_steppable=False))
            if n <= 5:                                # `cmp eax, 5 ; setle` (cf. docstring)
                out.append(t)
        return out


class FilterContinuous(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$FilterContinuous(source, predicate)` = MEME construction que
    `IdunBattleLogic.Entities.DSLFactory$$Filter` (`FromTriggerSelector`) + le FLAG de court-circuit : on garde
    le PREFIXE CONTIGU d'elements satisfaisant le predicat et on S'ARRETE au premier echec (une « ligne »
    d'ennemis s'interrompt au premier trou), la ou `Filter` balaie tout.

    Meme binding sujet que `Filter` (l'element courant est lie au slot sujet du contexte avant evaluation).
    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInLine`."""
    def __init__(self, source: TargetsSelector, predicate: TargetsSelector):
        self.source, self.predicate = source, predicate

    def select(self, ctx):
        out = []
        for item in self.source.evaluate(ctx):
            if not self.predicate.evaluate(replace(ctx, subject=item)):
                break                          # court-circuit (flag `Continuous`)
            out.append(item)
        return out


class UnitsWithVisualId(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsWithVisualId(visualIdValue, mode)` = `UnitsWithIdSelector(ctx,
    factory+0x80, visualIdValue, mode)`. La source est le slot PARTAGE `factory+0x80` (pose par
    `IdunBattleLogic.Entities.DSLFactory$$InitializeShared`, == la source d'`AllUnits`/`Friends(caster, @0x80)` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour`) -> le selecteur est **BOARD-WIDE : AUCUN RAYON**, a ne pas
    confondre avec `UnitsWithIds(source, ids)` (qui FILTRE un sous-ensemble deja restreint, ex.
    `SurroundingFriends` de SupremeCommander IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour).

    Consommateurs lus : `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` (site IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour+0x2f6+) et son homologue
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetTriggerSummonsBehaviour`, tous deux
    `Friends(caster@0x160, UnitsWithVisualId(VisualUnitIdFromUnitId(Get(unitId)), 1), 3)`.

    `visual_id` = noeud VALEUR (`VisualUnitIdFromUnitId`, entities/formulas.py) ou str/iterable de str.
    Le filtre compare le champ `visualId` du dict d'unite (meme convention que `UnitsWithIds`)."""
    def __init__(self, visual_id, mode: int = 1):
        self.visual_id, self.mode = visual_id, int(mode)

    def _ids(self, ctx) -> list:
        v = self.visual_id
        v = v.evaluate(ctx) if hasattr(v, "evaluate") else v
        if v is None:
            return []
        return [v] if isinstance(v, str) else [s for s in v if s]

    def select(self, ctx):
        ids = self._ids(ctx)
        if not ids:
            return []
        return [u for u in ctx.units if u.get("visualId") in ids]


class UnitsWithId(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsWithId(source, idValue, mode)` = `UnitsWithIdSelector(ctx, source,
    TestUnitProvider(idValue), mode)` : le VOLET MONO-ID d'`UnitsWithIds` (qui, lui, UNIONNE les volets sur
    un tableau d'ids). Filtre `source` par `IdunBattle.Entities.UnitExtensions$$HasUnitId(unit, id)`.
    Consommateur lu : `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour`
    (`UnitsWithId(SurroundingEnemies(target@0x178, range, 1, 3), GetStringConstant(0|4), 3)`).

    ⚠ **LE FILTRE PASSE PAR LE FOYER `has_unit_id` (#1078-r1), PLUS PAR UNE EGALITE DE `visualId`.**
    Le natif compare l'id de **CONFIG** (`IdunBattle.Entities.UnitExtensions$$GetUnitId` lit le champ
    +0x10 du composant d'identite), et le port ne dispose que du `visualId` (+0x20) -- la comparaison
    directe SUR-COMPTE et SOUS-COMPTE selon le sens (mesure #1078 sur `HailOfLivingAmmunition`).
    Le volet MULTI-ID `selectors/units.py::UnitsWithIds` avait ete bascule ; ce volet-ci ne l'etait
    pas, alors que `IdunBattle.Entities.Selectors.UnitsWithIdSelector$$Select` est LE MEME
    selecteur pour les deux (le multi n'est que l'`op_Addition` des volets mono).

    RAYON DE SOUFFLE MESURE (`probe_1078r1_units_with_id_mono.py`, etape 2 : les 8 `unitId` LUS aux
    call-sites executables x les 268 `visualId` que le gameconfig peut presenter) : **2 verdicts
    changent**, tous deux `False -> True`, tous deux dans un `Children(Owner)` --
    `tyranNpc1Hormagaunt` vs `tyranSmnHormagaunt` (SynapticLinchpin) et `votanNpc1Ecog` vs
    `votanSmnEcog` (EcogSupport). **0 verdict passe de True a False** : pour les 8 `unitId`,
    `presenting(unitId)` contient `unitId` ou est VIDE (repli historique), donc une unite SPAWNEE
    par le port (dont le `visualId` porte l'id de CONFIG, cf. `_spawn_config_grot`) reste matchee.

    Ces 2 changements sont des CORRECTIONS, et le regime AMBIGU que redoutait la docstring
    d'`has_unit_id` ne mord pas ici : la source de ces deux call-sites est
    `IdunBattleLogic.Entities.DSLSelectors$$Children(owner)`, qui ne contient que des unites
    SPAWNEES par le porteur -- jamais le npc homonyme. Un enfant SEEDE DEPUIS LE LIVE
    (`snapshot._load_unit_parent` <- `combatSnapshot.units[].parentId`) porte, lui, son id VISUEL :
    l'ancienne comparaison ne le comptait PAS dans le cap de summons, donc le port spawnait AU-DELA
    du plafond que le natif applique.

    ⚠ **LE 3e ARGUMENT `mode` EST UN `UnitSelectionType`, ET IL EST DESORMAIS APPLIQUE.** Il etait
    STOCKE et jamais LU : le noeud ne filtrait que sur `visualId`. Tant que la SOURCE etait
    elle-meme un selecteur d'unites filtre (`Friends`, `SurroundingEnemies` -- les deux seuls
    call-sites executables anterieurs), l'omission etait INERTE, les morts etant deja ecartes en
    amont. Elle cesse de l'etre des que la source ne filtre RIEN : `ChildrenOf`
    (`IdunBattleLogic.Entities.DSLSelectors$$Children(parent)`) rend explicitement TOUTES les
    entites enfants, mortes comprises. Le call-site
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility$$CreateBehaviour`
    compte ainsi `UnitsWithId(Children(owner@+0x30), unitId, OnlyAliveAndTargetable)` pour son cap
    de summons : sans le filtre, un Hormagaunt MORT tenait un slot que le natif a libere -- le port
    refusait un spawn que le natif fait. Le filtre passe par le FOYER unique
    (`entities/unit_selection_type.py::selection_ok_from_ctx`, mirror de
    `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`), jamais par un `alive` a la
    main ; son tri-etat degrade en VRAI ce qui n'est pas mesure."""
    def __init__(self, source: TargetsSelector, unit_id, mode: int = int(UnitSelectionType.OnlyAliveAndTargetable)):
        self.source, self.unit_id, self.mode = source, unit_id, int(mode)

    def select(self, ctx):
        uid = self.unit_id.evaluate(ctx) if hasattr(self.unit_id, "evaluate") else self.unit_id
        if uid is None:
            return []
        return [u for u in self.source.evaluate(ctx)
                if has_unit_id(u, uid) and selection_ok_from_ctx(u, self.mode, ctx)]


#: Les champs du `DslContext` qui correspondent a un slot d'`IdunBattle.Entities.Abilities.
#: AbilityEntities` -- l'ORDRE est celui du `.ctor` natif, dont Ghidra rend les 33 parametres nommes
#: (`caster, actor, target, owner, casterTile, activePlayer, casterTiles, effect, targetTile,
#: targetTiles, activeTarget, previousActiveTarget, currentAbilityOrEffect, ...`).
#: Les offsets des trois premiers sont LUS, pas supposes : `ActorSelector$$Select` lit `entities+0x0`,
#: `IdunBattle.Entities.Selectors.CasterSelector$$Select` lit `+0x8`,
#: `IdunBattle.Entities.Selectors.TargetSelector$$Select` lit `+0x10`.
#: `subject` n'a pas de slot PROPRE : le port l'emploie comme l'element courant lie par un
#: `Filter`/`Foreach`, ce que le natif ecrit dans `activeTarget` (surcharge
#: `AbilityEntities$$.ctor(entities, activeTarget)`, une COPIE-avec-activeTarget). Il entre donc
#: dans la cle, au meme titre.
#: ⚠ CE QUI N'Y EST PAS, et c'est un RESULTAT : les 20+ champs de DEGAT de la structure
#: (`damageReason`, `hitIndex`, `usedDamageProfiles`, `wasCrit`, ...) dont le `DslContext` ne
#: modelise que `is_first_hit`. Un `Cache` reevalue sous deux `hitIndex` differents dans la MEME
#: serie de coups verrait donc un HIT la ou le natif re-calcule. Aucun call-site porte n'est dans
#: ce cas (les `Cache` portes vivent au-dessus de la boucle de coups) -- residu NOMME.
_ABILITY_ENTITIES_SLOTS = ("actor", "caster", "target", "owner", "caster_pos",
                           "effect", "active_target", "subject", "is_first_hit")


def _entity_key(x):
    """Reduit un slot de role a une CLE HACHABLE qui mirrore l'egalite native.

    `AbilityEntities` est un `struct` sans `Equals`/`GetHashCode` propres : le `Dictionary` compare
    donc champ a champ, et les champs ENTITE (`IEntity`) le sont par REFERENCE. Cote port,
    l'identite stable d'une entite est son `id` (le dict d'unite est reconstruit d'un canal a
    l'autre, l'`id` non) -- on preferera donc l'`id` quand il existe, et l'identite d'OBJET sinon,
    qui est la traduction litterale de la reference native."""
    if x is None:
        return None
    if isinstance(x, dict):
        v = x.get("id")
        return ("e", v) if v is not None else ("o", id(x))
    if isinstance(x, (bool, int, float, str, bytes)):
        return x
    if isinstance(x, (list, tuple, set, frozenset)):
        return tuple(_entity_key(y) for y in x)
    v = getattr(x, "id", None)                       # `LiveUnit` & co : meme identite que le dict
    return ("e", v) if v is not None else ("o", id(x))


def _ability_entities_key(ctx):
    """La CLE du `Dictionary<AbilityEntities, List<IEntity>>` de `CacheSelector+0x30` (#927-r3),
    construite sur les SEULS slots que le port modelise (cf. `_ABILITY_ENTITIES_SLOTS`)."""
    return tuple(_entity_key(getattr(ctx, nom, None)) for nom in _ABILITY_ENTITIES_SLOTS)


class Cache(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Cache(source)` → `IdunBattle.Entities.Selectors.CacheSelector$$Select` : **MÉMOÏSE** le résultat
    du sous-arbre. Décompilé : 1re éval calcule (`source.evaluate` + `ToList`) et STOCKE dans le slot
    `+0x28` (mode slot unique, flag `+0x20`==0) ou un dict keyé par le contexte (`+0x30`) ; évals suivantes
    renvoient le CACHE. **PAS un pass-through** : la mémoïsation est OBSERVABLE quand l'état mute entre deux
    consommateurs — GetEmRuntz partage `Cache(GetSpawnTileSelector)` entre `Spawn` (capture les tuiles
    LIBRES PRÉ-spawn) et `PerformAIAttackFromCurrentPosition` (relit ces MÊMES tuiles POST-spawn pour y
    trouver les grots) ; sans mémoïsation, `CanAddUnit` recalculé exclurait les tuiles désormais occupées
    → zéro grot trouvé. Portée = l'instance du nœud ; l'arbre étant rebâti par cast (`getemruntz_tree()`),
    le cache est **par-cast**.

    ⚠ **LES DEUX MODES SONT PORTES (#927-r3), ET LE PORT N'AVAIT QUE LE MINORITAIRE.** La factory est
    `IdunBattleLogic.Entities.DSLSelectors$$Cache(entities, matchAbilityEntities)` ; le ctor pose
    `+0x18 = source`, `+0x20 = matchAbilityEntities`, `+0x28 = 0` (le slot) et alloue TOUJOURS le
    `Dictionary` de `+0x30`. `IdunBattle.Entities.Selectors.CacheSelector$$Select`, terme a terme :

        result = 0
        if (this+0x20 == 0)  result = this+0x28                      // mode SLOT
        else                 this+0x30.TryGetValue(entities, out result)   // mode DICT
        if (result != 0) return result
        result   = <source>.Select(entities).ToList()
        this+0x28 = result                                           // TOUJOURS
        this+0x30.Add(entities, result)                              // TOUJOURS
        return result

    Seule la LECTURE branche sur le flag ; l'ECRITURE alimente les deux emplacements. Le mode SLOT
    rend donc la 1re valeur memoisee QUEL QUE SOIT le contexte suivant ; le mode DICT re-calcule
    des que l'`AbilityEntities` recu differe.

    CENSUS PE DE TOUS LES CALL-SITES (build `t6dpr4k06g`, 2026-08-15) : **119 call-sites**, dont
    **112 en mode DICT** et **7 en mode SLOT**. Les sept, nommes :
    `...ResurrectionOrbAbility$$GetResurrectBehaviour`, `...StormcallerAbility$$ExecuteBehaviour`,
    `...HeavyRailRifle_AttackAbility$$CreateBehaviour`, `...LightImUpAbility$$CreateBehaviour`
    (le 2e de ses deux appels), `...DakkaDakkaDakkaAbility$$ExecuteBehaviour`,
    `...DakkaDakkaDakkaAbility$$GetLeftoverHitsPerTargetFormula`,
    `...DarkTalonStrikeAbility$$ExecuteBehaviour`.
    D'ou le defaut `True` : ce n'est pas un litteral invente, c'est celui de 112 sites sur 119, et
    tout call-site de la minorite l'ECRIT (`match_ability_entities=False`).

    ⚠ CE QUE LA CLE COUVRE, ET CE QU'ELLE NE COUVRE PAS. Le natif keye sur la STRUCTURE
    `AbilityEntities` entiere (33 champs, egalite de `ValueType` : references pour les entites,
    valeurs pour les scalaires). Le `DslContext` du port n'en modelise qu'un SOUS-ENSEMBLE, et
    `_ability_entities_key` ci-dessous ne prend QUE ces champs-la -- surtout pas le contexte entier,
    qui porte aussi `units`, `board` et une trentaine d'accesseurs que la structure native ignore :
    les inclure ferait RATER le cache a chaque reconstruction de contexte, et c'est exactement la
    memoisation load-bearing de GetEmRuntz qu'on casserait."""
    def __init__(self, source, match_ability_entities: bool = True):
        self.source = source
        self.match_ability_entities = bool(match_ability_entities)   # `+0x20`
        self._cached = None                          # `+0x28`, initialise a 0 par le ctor natif
        self._by_entities: dict = {}                 # `+0x30`, alloue par le ctor natif

    def select(self, ctx):
        if not self.match_ability_entities:          # `if (this+0x20 == 0)`
            cached = self._cached
        else:                                        # `TryGetValue(entities, out result)`
            cached = self._by_entities.get(_ability_entities_key(ctx))
        # `if (result != 0) return result` -- une liste VIDE est un pointeur NON NUL cote natif,
        # donc un resultat vide EST memoise. `is not None`, jamais un test de verite Python.
        if cached is not None:
            return cached
        result = self.source.evaluate(ctx)           # `<source>.Select(entities).ToList()`
        self._cached = result                        # `this+0x28 = result` -- INCONDITIONNEL
        self._by_entities[_ability_entities_key(ctx)] = result   # `this+0x30.Add(...)` -- idem
        return result


class Entity(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$Entity(...)` : résout la RÉFÉRENCE passée en argument
    (rôle caster/target/subject) en ENTITÉ. Wrapper fin — l'opérande (souvent un nœud rôle, ex.
    `Subject`) évalue déjà l'entité.

    **DEUX surcharges natives, UNE SEULE classe de sélecteur** (`IdunBattle.Entities.Selectors.
    EntitySelector`, même pointeur de classe alloué par les deux) : `Entity(entity)` prend l'entité,
    `Entity(entityId)` prend une FORMULE d'id. Le port les collapse sur ce nœud — c'est légitime
    parce que le natif lui-même n'a qu'un `EntitySelector`, dont le `$$Select` rend une liste de
    **0 ou 1** élément (`GetEntity(entities)` -> null ⇒ liste vide).

    ⚠ **LA FORME `entityId` EST CELLE QUE CONSOMME `...InstrumentsOfVengeanceAbility$$
    GetEffectBehavior`** (#889-r6) : `Entity(GetPersistentData(<clé composite>))`, où la valeur
    stockée est l'id d'une TUILE. Le port représente une tuile par son id NU (`int`), donc `select`
    rend cet entier tel quel — `_tile_positions` et `Sub._key` le normalisent, comme partout ailleurs
    en domaine mixte. `None` (clé absente ⇒ `GetPersistentData` rend `0`, mais `EntityId` n'écrit
    jamais `0`) rend `[]`, pas une entité fantôme.

    ⚠ **CE QUI N'EST PAS PORTÉ, et c'est nommé** : le natif résout un `IEntity.Id` de l'ECS, le port
    un id de TUILE du `boardGraph` — deux numérotations distinctes. L'aller-retour
    `SetPersistentData(EntityId(sel))` -> `Entity(GetPersistentData(...))` est FIDÈLE (les deux bouts
    parlent la même représentation), mais un id venu d'AILLEURS que de cet aller-retour ne se
    résoudrait pas. Aucun call-site porté n'est dans ce cas."""
    def __init__(self, ref):
        self.ref = ref

    def select(self, ctx):
        v = self.ref.evaluate(ctx)
        return [] if v is None else v                  # `GetEntity` -> null ⇒ liste VIDE


class Nothing(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Nothing` : sélecteur VIDE (retourne `[]`). Classe DISTINCTE de `Null`."""
    def select(self, ctx):
        return []


class SelectIf(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$If(abilityTrigger, selectorTrue, selectorFalse)` --
    le `If` du domaine SELECTEUR, TROISIEME homonyme du DSL et classe NATIVE distincte des deux
    autres :
      * `DSLBehaviors$$If(cond, then, else)`  -> `entities/behaviours.py::If`   (kind E) ;
      * `DSLFormulas$$If(cond, a, b)`         -> `entities/formulas.py::If`     (kind V) ;
      * CELUI-CI                              -> un SELECTEUR (kind S).
    Les trois coexistent au meme call-site (`HaywireMineAbility$$CreateBehaviour` en utilise deux),
    d'ou le nom distinct cote port.

    ⚠ Le `.ctor` alloue par la factory porte dans Ghidra le nom
    `IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$.ctor` : c'est un corps DEDUPLIQUE
    (meme signature `(state, trigger, sel, sel)`), pas l'identite de la classe -- on cite donc la
    FACTORY, qui est nommee sans ambiguite.

    Semantique : evalue le predicat, puis DELEGUE a l'une des deux branches (l'autre n'est pas
    evaluee -- le `Select` natif n'appelle qu'un seul sous-selecteur). `selectorFalse` absent au
    call-site -> `[]` (branche vide), jamais la source.

    CONSOMMATEUR PORTE : le selecteur de tuiles de `HaywireMineAbility$$CreateBehaviour`
    (`If(<a une tuile precedente ET a bouge>, CanAddUnit(PreviousTile), <meilleure adjacente>)`)."""
    def __init__(self, cond, selector_true: TargetsSelector,
                 selector_false: TargetsSelector = None):
        self.cond = cond
        self.selector_true, self.selector_false = selector_true, selector_false

    def select(self, ctx):
        if self.cond.evaluate(ctx):
            return self.selector_true.evaluate(ctx)
        return [] if self.selector_false is None else self.selector_false.evaluate(ctx)


class ConditionalSelector(SelectIf):
    """`IdunBattleLogic.Entities.DSLSelectors$$ConditionalSelector(abilityTrigger, selectorTrue,
    selectorFalse)` -- QUATRIEME porte du `If` selecteur, et **la MEME classe native** que
    `DSLSelectors$$If` (cf. `SelectIf` ci-dessus) : les deux factories sont a des adresses
    DISTINCTES mais allouent le meme singleton (`DAT_18335bd70`), avec le meme
    `...UnobscuredEntitiesSelector$$.ctor(state, trigger, selTrue, selFalse)` et le meme ordre
    d'arguments -- LU aux deux decompiles. La semantique est donc celle de `SelectIf`, dont on
    herite : evalue le predicat puis DELEGUE a UNE seule branche (l'autre n'est jamais evaluee).

    Ce point compte pour le RNG : au seul call-site porte
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase$$GetMovementBehavior`),
    la branche FAUSSE contient un `Randomize(CanAddUnit(AllTiles))` -- une permutation aleatoire
    COMPLETE du plateau, donc `len(pool)` tirages. Elle n'est tiree QUE si la tuile d'atterrissage
    directe est occupee ; evaluer les deux branches desalignerait tout le flux RNG en aval.

    La classe existe pour que le port CITE la factory que son call-site ecrit -- meme raison que
    `AtIndex` vs `units.First`."""


class Null(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Null` : entité/valeur NULLE (retourne `None`). Même classe qu'`Entity` avec
    arg null ; distinct de `Nothing` (ensemble vide)."""
    def select(self, ctx):
        return None


class EffectSource(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EffectSource` : entité SOURCE de l'effet COURANT (`ctx.effect`). NON captable
    hors application d'effet → None si `ctx.effect` absent."""
    def select(self, ctx):
        return _effect_field(ctx.effect, "source", None)


class EffectFromOwner(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EffectFromOwner(effectType)` → `EffectWithTypeSelector IdunBattle.Entities.Selectors.EffectWithTypeSelector$$Select` : effets
    du type possédés par l'owner. NON captable offline (effets par unité absents du state) → `[]` défaut."""
    def __init__(self, effect_type):
        self.effect_type = effect_type

    def select(self, ctx):
        return []


class EffectsFromUnitSource(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EffectsFromUnitSource(source, effectType)` -> `EffectWithTypeSelector
    IdunBattle.Entities.Selectors.EffectWithTypeSelector$$Select` (frere d'`EffectFromOwner`, keye sur la SOURCE au lieu de l'owner) : les INSTANCES d'effet
    du type `effect_type` dont le `EffectComponent.SourceUnit @+0x10` est l'unite `source`. Domaine =
    ENTITES-EFFET (pas des unites) -> consomme par `OwnerOfEffect` qui remonte a leurs porteurs.

    Seul call-site porte : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour`
    (`RemoveEffect(OwnerOfEffect(EffectsFromUnitSource(Self@0x148, 0x4e1)), 0x4e1)` = le marqueur pose par
    CE caster, ou qu'il soit). Offline l'entite-effet est modelisee par un dict
    `{"effect_type", "source", "owner_id"}` (`ctx.effects_from_source`) ; sans accesseur -> [] (degradation
    fidele « present != applique »)."""
    def __init__(self, source: TargetsSelector, effect_type):
        self.source, self.effect_type = source, effect_type

    def select(self, ctx):
        fn = getattr(ctx, "effects_from_source", None)
        if fn is None:
            return []
        src = resolve_unit(self.source, ctx)
        if src is None:
            return []
        et = self.effect_type.evaluate(ctx) if hasattr(self.effect_type, "evaluate") else self.effect_type
        return list(fn(src, int(et)) or [])


class EffectsOfUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$EffectFromOwner(effectTarget, effectType)` --
    la surcharge a DEUX arguments (signature LUE au decompile :
    `EffectFromOwner(void *this, void *effectTarget, void *effectType)`), ou `effectTarget` est un
    SELECTEUR D'UNITES et non l'owner implicite du contexte. A NE PAS confondre avec
    `EffectFromOwner` ci-dessous, qui mirrore `DSLFactory$$EffectFromOwner(effectType)` (owner
    implicite, non captable offline -> `[]`).

    Domaine de sortie = ENTITES-EFFET, comme `EffectsFromUnitSource` : dicts
    `{"effect_type", "owner_id", "level"}`, une entree PAR INSTANCE portee. C'est ce domaine que
    consomme `EffectLevelOf` (`DSLFormulas$$EffectLevel(effects)`), qui SOMME les `level`.

    Seul call-site porte : `IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$
    ExecuteBehaviour` -- `EffectLevel(EffectFromOwner(<cache des allies mecaniques>, 0x555))`, le
    total de `MachineVengeance` transfere a Belisarius.

    Accesseur `ctx.effects_of_units` absent -> `[]` (degradation fidele « present != applique », la
    meme que ses deux freres de ce module)."""
    def __init__(self, targets: TargetsSelector, effect_type):
        self.targets, self.effect_type = targets, effect_type

    def select(self, ctx):
        fn = getattr(ctx, "effects_of_units", None)
        if fn is None:
            return []
        et = self.effect_type.evaluate(ctx) if hasattr(self.effect_type, "evaluate") else self.effect_type
        out = []
        for u in _units_of(self.targets, ctx):
            out.extend(fn(u, int(et)) or [])
        return out


class OwnerOfEffect(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$OwnerOfEffect(effects)` : remonte de chaque ENTITE-EFFET a l'UNITE qui la
    PORTE (`EffectComponent.Target @+0x14` / cle `EffectsState.by_unit`). Rend des dicts d'unite
    (domaine unit) dedupliques, dans l'ordre du selecteur source."""
    def __init__(self, effects: TargetsSelector):
        self.effects = effects

    def select(self, ctx):
        by_id = {u.get("id"): u for u in (ctx.units or []) if isinstance(u, dict)}
        out, seen = [], set()
        for e in (self.effects.evaluate(ctx) or []):
            oid = e.get("owner_id") if isinstance(e, dict) else None
            if oid is None or oid in seen:
                continue
            u = by_id.get(oid)
            if u is not None:
                seen.add(oid)
                out.append(u)
        return out
