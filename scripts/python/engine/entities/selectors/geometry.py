"""Geometrie hex par DIRECTION + selecteurs tardifs (effets, memoisation, ids visuels).

`IdunBattle.Utils.Hex` : voisin par direction, triangle, vecteur, meme elevation, ligne derriere.
Plus les noeuds construits au-dessus (`TilesBehindInLine`, `FilterContinuous`, `Cache`,
`EffectSource`...). Tranche 4 du decoupage de `selectors.py` -- cf. `__init__.py`."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ... import battle_query          # mirror UNIQUE de GetTilesBehind/IsTileValidForList (#117/#124)
from ...dsl.base import (TargetsSelector, Const, _pos, _feet, _within, _is_alive, _units_of,
                         _effect_field, resolve_unit)
from ._shared import _entity_pos, _tile_positions


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
_CUBE_DIRECTIONS = ((0, 1), (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1))


def neighbour_at(col: int, row: int, direction: int) -> tuple:
    """`IdunBattle.Utils.Hex.AxialCoordinate$$NeighbourAt` : position de la tuile voisine dans la DIRECTION HEX
    `direction` (0..5, table `_CUBE_DIRECTIONS`). Le natif passe en cube (x=col, z=row-(col+(col&1))/2),
    ajoute (dx,dz) puis reconvertit — soit exactement `hexgeo.to_cube`/`from_cube` (meme parite
    odd-q-UP : le natif calcule `col + (col & 1)` quand le flag de parite @+0x18 vaut 0)."""
    dx, dz = _CUBE_DIRECTIONS[int(direction) % 6]
    x, _y, z = hexgeo.to_cube(int(col), int(row))
    return hexgeo.from_cube(x + dx, z + dz)


# `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape` : par index de COIN (0..5), le COUPLE de directions
# hex des deux voisines ajoutees a la tuile-centre, dans l'ordre d'insertion du natif (lVar5 puis lVar6).
# Lu case par case sur les DEUX branches de parite du decompile (colonne paire / impaire), qui donnent
# le MEME couple de directions — la parite ne change que l'ecriture en offset.
_TRIANGLE_SHAPE_DIRECTIONS = {0: (5, 0), 1: (0, 1), 2: (5, 4), 3: (1, 2), 4: (4, 3), 5: (3, 2)}


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
        from ...services.spawn_tile_shape import get_area
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


class PickFirstN(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$First(source, amountNode)` -> `IdunBattle.Entities.Selectors.PickFirstNSelector` (`IdunBattle.DSL.APickSelector`, taille 0x30 =
    ctx/source/amount-node/flag) : les `amount` PREMIERS elements de la source, ordre PRESERVE.

    ⚠ A NE PAS CONFONDRE avec `IdunBattle.Entities.Selectors.PickAtIndexSelector$$Select` (taille 0x28, champ
    +0x20 = un INT d'index) qui rend `[source[index]]` : c'est une classe DISTINCTE, construite par une
    AUTRE factory. `DSLFactory.First` construit bien `PickFirstN`. Le noeud `First` de ce module (index 0
    par defaut) coincide avec `PickFirstN(1)` pour tous ses call-sites historiques (index non passe).

    `amount` = noeud VALEUR (`Direct(nrOfSummons)`) ou int. <=0 -> liste vide."""
    def __init__(self, source: TargetsSelector, amount):
        self.source, self.amount = source, amount

    def select(self, ctx):
        n = self.amount.evaluate(ctx) if hasattr(self.amount, "evaluate") else self.amount
        n = int(n or 0)
        if n <= 0:
            return []
        return list(self.source.evaluate(ctx))[:n]


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

    RESIDU documente : la branche `check_walkable == False` du natif teste `tileComponent+0x40 == 0`
    (drapeau de tuile SEUL, sans le composant MUR) ; le port utilise `board.walkable` (capture live de
    `TileExtensions.IsWalkable`, qui FOND le drapeau de tuile ET le mur). Inerte pour ses deux call-sites
    (`FilterContinuous(HasUnit & AreEnemies)` en aval : une tuile non-walkable ne porte pas d'unite).

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
        positions = battle_query.get_tiles_behind(
            src[0], dst[0], max_count=n,
            check_walkable=self.check_walkable, update_reference=self.update_reference,
            walkable_at=lambda p: board.walkable(board.id_at(p[0], p[1])),
            elevation_at=lambda p: board.elevation(board.id_at(p[0], p[1])),
            tile_exists=lambda p: board.id_at(p[0], p[1]) is not None)
        return [board.id_at(p[0], p[1]) for p in positions]


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
    Meme reduction offline que `UnitsWithIds` : comparaison sur le champ `visualId` du dict d'unite
    (qui porte l'id de CONFIG pour les unites SPAWNEES, cf. `_spawn_config_grot`)."""
    def __init__(self, source: TargetsSelector, unit_id, mode: int = 3):
        self.source, self.unit_id, self.mode = source, unit_id, int(mode)

    def select(self, ctx):
        uid = self.unit_id.evaluate(ctx) if hasattr(self.unit_id, "evaluate") else self.unit_id
        if uid is None:
            return []
        return [u for u in self.source.evaluate(ctx) if u.get("visualId") == uid]


class Cache(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Cache(source)` → `IdunBattle.Entities.Selectors.CacheSelector$$Select` : **MÉMOÏSE** le résultat
    du sous-arbre. Décompilé : 1re éval calcule (`source.evaluate` + `ToList`) et STOCKE dans le slot
    `+0x28` (mode slot unique, flag `+0x20`==0) ou un dict keyé par le contexte (`+0x30`) ; évals suivantes
    renvoient le CACHE. **PAS un pass-through** : la mémoïsation est OBSERVABLE quand l'état mute entre deux
    consommateurs — GetEmRuntz partage `Cache(GetSpawnTileSelector)` entre `Spawn` (capture les tuiles
    LIBRES PRÉ-spawn) et `PerformAIAttackFromCurrentPosition` (relit ces MÊMES tuiles POST-spawn pour y
    trouver les grots) ; sans mémoïsation, `CanAddUnit` recalculé exclurait les tuiles désormais occupées
    → zéro grot trouvé. Portée = l'instance du nœud ; l'arbre étant rebâti par cast (`getemruntz_tree()`),
    le cache est **par-cast**. Slot unique (suffisant pour GetEmRuntz : même contexte top-level aux deux
    évals ; la variante dict-keyée par contexte reste à porter si un `Cache` est éval sous un `Foreach`)."""
    def __init__(self, source):
        self.source = source
        self._has = False
        self._cached = None

    def select(self, ctx):
        if not self._has:                            # slot +0x28 : miss -> calcule + stocke
            self._cached = self.source.evaluate(ctx)
            self._has = True
        return self._cached                          # hit -> renvoie le cache (mémoïsation observable)


class Entity(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Entity(ref)` : résout la RÉFÉRENCE passée en argument (rôle
    caster/target/subject) en ENTITÉ. Wrapper fin — l'opérande (souvent un nœud rôle, ex. `Subject`)
    évalue déjà l'entité."""
    def __init__(self, ref):
        self.ref = ref

    def select(self, ctx):
        return self.ref.evaluate(ctx)


class Nothing(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Nothing` : sélecteur VIDE (retourne `[]`). Classe DISTINCTE de `Null`."""
    def select(self, ctx):
        return []


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
