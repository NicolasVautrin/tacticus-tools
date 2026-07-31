"""Selecteurs du domaine TUILE (ids de tuile) -- ils lisent `ctx.board`.

Pont unite -> tuile (`Tiles`, `AdjacentTiles`), dedup et intersection propres au domaine
(`TileUnique`, `TileIntersect`), occupation (`CanAddUnit`) et portee de deplacement
(`MovableTilesInRange`). Tranche 2 du decoupage de `selectors.py` -- cf. `__init__.py`."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ... import battle_query          # mirror UNIQUE de GetTilesBehind/IsTileValidForList (#117/#124)
from ...dsl.base import (TargetsSelector, Const, _pos, _within, _is_alive, _units_of, _effect_field,
                         resolve_unit)
from ._shared import _entity_pos, _tile_positions


# --- Selecteurs de TUILES (domaine TILE = ids de tuile ; lisent ctx.board). Pont unit->tile
#     (`AdjacentTiles`) et tile->tile (`CanAddUnit`/`TileUnique`/`TileIntersect`). board None -> []. ---

class Caster(TargetsSelector):
    """L'unite CASTER (`caster@+0x168`, ref passee aux selecteurs). Accesseur unit-domain =
    `ctx.caster` (dict|None)."""
    def select(self, ctx):
        return ctx.caster


class AllUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AllUnits` -> `AllAliveMachinesSelector IdunBattle.Entities.Selectors.AllAliveMachinesSelector$$Select` : toutes les unites
    VIVANTES de la bataille. Le primitif DSL `AllUnits` est **la variante ALIVE** (un `AllUnitsSelector`
    natif distinct existe pour l'ensemble brut, mais `DSLFactory.AllUnits` ne l'utilise PAS). Source des
    filtres `Enemies`/`Friends` du port (le natif `Enemies(caster, ...)` folde la source ; cote port on
    fournit `AllUnits` a l'inner). **Le filtre alive est ICI** (mirror de AllAliveMachines), PAS via un
    noeud `Damageable` en aval -> cf. confront LIVE #200 tracer-v2 + fix #202 (le natif GetSpawnTileSelector
    n'a AUCUN Damageable ; c'est `AllUnits`=alive qui exclut les morts)."""
    def select(self, ctx):
        return [u for u in ctx.units
                if bool(u.get("alive", True)) and (u.get("hp") or 0) > 0]


class AllTiles(TargetsSelector):
    """`IdunBattle.Entities.Selectors.AllTilesSelector` — le slot PARTAGE `factory+0x78` que
    `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` alloue (`AllTilesSelector..ctor(uVar2, ctx,
    0, 0)` -> `*(factory + 0x78) = uVar2`) : TOUTES les tuiles du plateau, en domaine ID.

    C'est la source des selecteurs board-wide de TUILES ; unique consommateur porte :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$NrOfHitsFormula`
    (`Count(EntitiesWithAnyEffect(AllTiles@0x78, Fire=5, sourceFlag=6))` = « +1 coup par hex EN FEU »).

    Ordre = celui de `board.by_id` (ordre d'insertion du dump) ; le seul consommateur en prend le
    CARDINAL, donc l'ordre n'est pas observable. board None -> []."""
    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        return list(board.by_id.keys())


class Children(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Children` = `Entities.Selectors.AllAliveMachinesSelector` (IdunBattle.Entities.Selectors.AllAliveMachinesSelector$$.ctor) SCOPÉ
    aux enfants (summons) produits par CE cast (natif `factory+0x148`). Port = l'accumulateur `ctx.children`
    (alimenté par la feuille `SpawnUnit`, `runner/abilities/behaviours.py`). ⚠ Le filtre `AllAlive` est un
    no-op offline pour l'on-appearance de CE cast (les summons survivent à leur apparition). cf.
    `getemruntz_taunt_tree` (loki.py)."""
    def select(self, ctx):
        return list(getattr(ctx, "children", None) or [])


class Parent(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Parent(source, mode)` -> `IdunBattle.Entities.Selectors.ParentSelector$$Select` :
    pour CHAQUE entite du selecteur source, `IdunBattle.Entities.UnitExtensions$$GetParent(u, ..., mode)` ;
    les parents non nuls sont accumules dans un `OrderedSet` (donc DEDUPLIQUES, ordre d'apparition).

    ⚠ La RECURSION vers la racine est conditionnee au 3e argument `root` de `GetParent` (le champ
    `+0x20` que `ParentSelector$$.ctor` recopie du `mode`) : sans lui le natif rend le parent
    DIRECT, ce que porte ce selecteur.

    Port : le lien enfant -> parent vit sur le dict d'unite (`parentId` = `ChildComponent.ParentId`,
    alimente par `UnitComponent.parent_id` que `SpawnUnitOperation` pose au spawn = le
    `Unit_Parent_Id` natif, ou que `snapshot._load_unit_parent` seede depuis
    `combatSnapshot.units[].parentId` sur un etat hydrate, #378). Le parent est
    RESOLU dans `ctx.units` (meme domaine que tous les selecteurs d'unite) ; un parent absent du
    contexte (ou `parentId` None) ne produit rien -> selecteur VIDE, mirror du `if (parent != null)`.

    Call-sites portes : `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$CreateTargetSelector`
    (`Parent(Self@0x148)` = le summoner que l'effet buffe) et
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtector_ProtectAbility$$CreateBehaviour`
    (`SwitchPosition(Self, Parent(Self))`)."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        out: list = []
        seen: set = set()
        for u in _units_of(self.source, ctx):
            pid = u.get("parentId") if isinstance(u, dict) else None
            if pid is None or pid in seen:
                continue
            for cand in ctx.units:
                if cand.get("id") == pid:
                    seen.add(pid)
                    out.append(cand)
                    break
        return out


class LastUnitAttackedBy(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$LastUnitAttackedBy` = `Entities.Selectors.LastUnitAttackedBySelector`
    (IdunBattle.Entities.Selectors.LastUnitAttackedBySelector$$Select) : dernière unité attaquée par `unit`. Port : le dict FRAIS (état POST-attaque, relu par la
    feuille `PerformAIAttack`) de la cible frappée → champ `_last_attacked` de l'unité (None si aucune). Ce
    dict porte `alive`/`hp` COURANTS → `IsAlive(LastUnitAttackedBy(child))` lit l'état vivant APRÈS l'attaque."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def select(self, ctx):
        u = resolve_unit(self.unit, ctx)
        return (u or {}).get("_last_attacked")


class AdjacentTiles(TargetsSelector):
    """`DSLFactory.AdjacentTiles(source)` : UNION (BRUTE, avec doublons possibles entre unites -> le
    natif fait suivre d'un `Unique`) des tuiles hex-adjacentes aux unites de `source`, via le
    voisinage NATIF `ctx.board.neighbours(tile_de_l_unite)`. `source` = TargetsSelector d'ENTITES : le
    natif prend la MainTile de chaque entite -- pour une entite-UNITE c'est sa tuile, pour une
    entite-TUILE c'est ELLE-MEME. Le port accepte donc les DEUX domaines (`_tile_positions`), ce
    qu'exige un cast TILE-TARGET (`PlagueburstMortarAbility$$ExecuteBehaviour` :
    `AdjacentTiles(target@0x178)` ou `target@0x178` EST la tuile ciblee ; les call-sites unit-domain
    historiques passent par le meme chemin, resultat inchange). Retour list[int]. board None -> [].

    ORDRE (R28-1) : `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` accumule dans un
    `OrderedSet` (ordre d'INSERTION) ce que rend `BattleQuery$$GetAdjacentTiles` = la liste
    d'adjacence STOCKEE sur la tuile -> `Board.neighbours_native` (champ brut `boardGraph.neighbours`),
    et **pas** `board.neighbours()` qui trie les ids et symetrise. Observable des qu'un
    `PickRandomly`/`First`/tri stable consomme le resultat (== `_free_tiles_adjacent(native_order=True)`,
    valide live par fc23f1e). 2e consommateur confronte live : le splash de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour`, itere par un
    `SortedAttackSeries` SANS `OrderBy` -> l'ordre fixe la sequence de tirages de degat."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        out: list = []
        for p in _tile_positions(self.source, ctx, board):
            tid = board.id_at(p[0], p[1])
            if tid is None:
                continue
            out.extend(board.neighbours_native(tid))
        return out


class TileUnique(TargetsSelector):
    """`DSLFactory.Unique(source)` sur le domaine TILE (LINQ Distinct sur ids de tuile, 1re
    apparition preservee). Homologue tile de `Unique` (qui dedup par id d'ENTITE, KO sur des ints)."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        seen, out = set(), []
        for t in self.source.evaluate(ctx):
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out


class CanAddUnit(TargetsSelector):
    """`DSLFactory.CanAddUnit(tiles)` : garde les tuiles ou une unite PEUT etre ajoutee = `walkable`
    ET LIBRE (aucun occupant VIVANT). Occupation = tuiles des `ctx.units` vivants (mirror du
    `_occupied_tiles(state)` imperatif). Ordre de `source` preserve. board None -> [].

    OCCUPATION PAR PIED (#91) : le natif `IdunBattle.Entities.TileExtensions$$CanAddUnit` lit le
    `TileContentComponent` de la tuile -- une tuile sous N'IMPORTE QUEL pied est occupee (#R30 §1).
    On lit donc l'EMPREINTE (`unit["feet"]`, mirror `EntityExtensions$$GetTiles`), pas la seule
    `PositionComponent`. Strictement equivalent pour une unite mono-tuile (`feet == [pos]`) ; sans
    ca, un Galatian pose au sol par `DutyEternal` ne bloquait que sa MAIN TILE et le port acceptait
    de spawner sur ses deux autres pieds."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        occ = set()
        for u in ctx.units:
            if not _is_alive(u):
                continue
            feet = (u or {}).get("feet")
            if not feet:                                  # unite hors plateau / dict sans empreinte
                p = _pos(u)
                feet = [] if p is None else [p]
            for f in feet:
                t = board.id_at(f[0], f[1])
                if t is not None:
                    occ.add(t)
        return [t for t in self.source.evaluate(ctx) if t not in occ and board.walkable(t)]


class TileIntersect(TargetsSelector):
    """Intersection de deux ensembles de TUILES (ids) — `op_BitwiseAnd` du domaine tile
    (`CombinedSelector`). Garde les tuiles de `left` presentes dans `right` (ordre de `left`,
    dedup). Homologue tile de `And` (intersection par id d'entite)."""
    def __init__(self, left: TargetsSelector, right: TargetsSelector):
        self.left, self.right = left, right

    def select(self, ctx):
        rs = set(self.right.evaluate(ctx))
        seen, out = set(), []
        for t in self.left.evaluate(ctx):
            if t in rs and t not in seen:
                seen.add(t)
                out.append(t)
        return out


class MovableTilesInRange(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$MovableTilesInRange(unit, fromTile, range, canReachOnly,
    …)` -> `IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select`, qui resout
    `unit` (@+0x20), `fromTile` (@+0x28, a defaut `GetMainTile(unit)`), `range` (formule @+0x30,
    `Nullable<int>`) puis delegue au slot 0xc de la `PathfindingQuery` avec `canReachOnly` (@+0x38).

    Le calcul est le PATHFINDER (impératif, `entities/pathfinding/walk_pathfinder.py` — mirror de
    `IdunBattle.Entities.Pathfinding.BasePathfinder$$GetMovablePositions`) : ce noeud est la FEUILLE
    DSL qui l'appelle, comme `CanAddUnit` est la feuille qui appelle les predicats de board.

    `can_reach_only` :
      * `False` (natif `0`) -> le `visited` du BFS = TOUTES les tuiles ATTEINTES en <= range pas
        (traversables, y compris occupees par un allie) ;
      * `True`  (natif `1`) -> le `stop_set` = celles ou l'unite peut S'ARRETER (libres, start exclu).
    Contraste mesure : `WaaaghAbility$$GetPossibleMovementTiles` passe `0`,
    `VigilanceEternal`/`HeroicFusillade` passent `1`.

    Occupation = les unites VIVANTES de `ctx.units` (meme modele que `CanAddUnit`) ; `moving_team` =
    l'equipe de `unit` (un ENNEMI sur la tuile bloque la traversee, un allie non). Ordre de sortie =
    id de tuile croissant (le natif rend un `List<Tile>` issu d'un BFS ; ce noeud n'est consomme
    qu'a travers une INTERSECTION `op_BitwiseAnd`, cf. `tiles_unit_can_move_to_charge_target`, ou
    seul l'ordre de l'operande GAUCHE est observable). `board` absent -> []."""
    def __init__(self, unit: TargetsSelector, from_tile: TargetsSelector,
                 range_amount, can_reach_only: bool = False):
        self.unit, self.from_tile = unit, from_tile
        self.range_amount, self.can_reach_only = range_amount, bool(can_reach_only)

    def select(self, ctx):
        from ..pathfinding.walk_pathfinder import get_movable_positions
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        u = resolve_unit(self.unit, ctx)
        if u is None:
            return []
        start_pos = None
        for p in _tile_positions(self.from_tile, ctx, board):
            start_pos = p
            break
        if start_pos is None:
            start_pos = _pos(u)
        start = board.id_at(start_pos[0], start_pos[1]) if start_pos is not None else None
        if start is None:
            return []
        occ: dict = {}
        for other in ctx.units:
            if not _is_alive(other):
                continue
            p = _pos(other)
            if p is None:
                continue
            t = board.id_at(p[0], p[1])
            if t is not None:
                occ[t] = other.get("team")
        visited, stop = get_movable_positions(board, start, int(self.range_amount.evaluate(ctx)),
                                              occ, u.get("team"))
        return sorted(stop if self.can_reach_only else visited)


def tiles_unit_can_move_to_charge_target(unit: TargetsSelector, from_tile: TargetsSelector,
                                         target: TargetsSelector, range_amount,
                                         can_reach_only: bool = False) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLFactory$$TilesUnitCanMoveToChargeTarget(unit, fromTile, target,
    range, canReachOnly)` — MIRROR du decompile, qui n'assemble QUE deux noeuds :

        CanAddUnit(AdjacentTiles(target))  op_BitwiseAnd  MovableTilesInRange(unit, fromTile,
                                                                             range, canReachOnly)

    = « tuiles LIBRES et marchables hex-adjacentes a la cible, que l'unite peut atteindre en <=
    `range` pas ». `op_BitwiseAnd` du domaine TILE = `TileIntersect` (ordre de l'operande GAUCHE
    preserve). Helper de FACTORY (comme `get_spawn_tile_selector`), pas une classe native."""
    return TileIntersect(CanAddUnit(AdjacentTiles(target)),
                         MovableTilesInRange(unit, from_tile, range_amount, can_reach_only))
