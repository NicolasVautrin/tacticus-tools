"""Noeuds SELECTEURS de TUILES du DSL lazy (domaine TILE = ids de tuile), a cote des selecteurs
UNIT-domain (selectors.py). Lisent `ctx.board` (`Board`, entities/pathfinding : `neighbours`/`id_at`/
`walkable`). Utilises par les behaviours de PLACEMENT/spawn (`GetSpawnTileSelector` de GetEmRuntz,
#149 slice-2b). Retour = list[int] (ids de tuile). `ctx.board` None -> domaine tile degrade -> [].

Le DSL lazy existant est UNIT-domain (`ctx.units`, dicts) ; ces noeuds font le pont unit -> tile
(`AdjacentTiles` : unites -> leurs tuiles voisines) et tile -> tile (`CanAddUnit`/`TileUnique`/
`TileIntersect`). cf. docs/rl/dsl-effect-nodes.md.
"""
from __future__ import annotations

from .base import Node, _pos, _units_of, _is_alive


class Caster(Node):
    """L'unite CASTER (`caster@+0x168`, ref passee aux selecteurs). Accesseur unit-domain =
    `ctx.caster` (dict|None)."""
    def evaluate(self, ctx):
        return ctx.caster


class AllUnits(Node):
    """Ensemble des unites de bataille (`ctx.units`) — source des filtres `Enemies`/`Friends`/
    `Damageable` du port (le natif `Enemies(caster, ...)` @180... folde la source implicitement ;
    cote port `Enemies(inner)` prend un inner -> on lui fournit `AllUnits`). Adaptateur port, pas
    une classe native distincte."""
    def evaluate(self, ctx):
        return list(ctx.units)


class AdjacentTiles(Node):
    """`DSLFactory.AdjacentTiles(source)` : UNION (BRUTE, avec doublons possibles entre unites -> le
    natif fait suivre d'un `Unique`) des tuiles hex-adjacentes aux unites de `source`, via le
    voisinage NATIF `ctx.board.neighbours(tile_de_l_unite)`. `source` = Node unit-domain (unite
    seule ou liste, normalise par `_units_of`). Retour list[int] (tile ids). board None -> []."""
    def __init__(self, source: Node):
        self.source = source

    def evaluate(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        out: list = []
        for u in _units_of(self.source, ctx):
            p = _pos(u)
            if p is None:
                continue
            tid = board.id_at(p[0], p[1])
            if tid is None:
                continue
            out.extend(board.neighbours(tid))
        return out


class TileUnique(Node):
    """`DSLFactory.Unique(source)` sur le domaine TILE (LINQ Distinct sur ids de tuile, 1re
    apparition preservee). Homologue tile de `selectors.Unique` (qui dedup par id d'ENTITE, KO sur
    des ints)."""
    def __init__(self, source: Node):
        self.source = source

    def evaluate(self, ctx):
        seen, out = set(), []
        for t in self.source.evaluate(ctx):
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out


class CanAddUnit(Node):
    """`DSLFactory.CanAddUnit(tiles)` : garde les tuiles ou une unite PEUT etre ajoutee = `walkable`
    ET LIBRE (aucun occupant VIVANT). Occupation = tuiles des `ctx.units` vivants (mirror du
    `_occupied_tiles(state)` imperatif). Ordre de `source` preserve. board None -> []."""
    def __init__(self, source: Node):
        self.source = source

    def evaluate(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        occ = set()
        for u in ctx.units:
            if not _is_alive(u):
                continue
            p = _pos(u)
            if p is None:
                continue
            t = board.id_at(p[0], p[1])
            if t is not None:
                occ.add(t)
        return [t for t in self.source.evaluate(ctx) if t not in occ and board.walkable(t)]


class TileIntersect(Node):
    """Intersection de deux ensembles de TUILES (ids) — `op_BitwiseAnd` du domaine tile
    (`CombinedSelector`). Garde les tuiles de `left` presentes dans `right` (ordre de `left`,
    dedup). Homologue tile de `selectors.And` (intersection par id d'entite)."""
    def __init__(self, left: Node, right: Node):
        self.left, self.right = left, right

    def evaluate(self, ctx):
        rs = set(self.right.evaluate(ctx))
        seen, out = set(), []
        for t in self.left.evaluate(ctx):
            if t in rs and t not in seen:
                seen.add(t)
                out.append(t)
        return out


def get_spawn_tile_selector() -> Node:
    """`GetEmRuntzAbility.GetSpawnTileSelector @1811e26b0` (mirror 1:1) =
        op_BitwiseAnd( CanAddUnit(AdjacentTiles(caster)),
                       Unique(AdjacentTiles( UnitsWithoutTrait(Enemies(caster,0x80,3), 0x1b) )) )
    = ids de tuiles LIBRES (walkable + inoccupees) adjacentes au CASTER **ET** adjacentes a un
    ENNEMI vivant non-`Steppable` (0x1b=27, cf. `UnitTrait.Steppable` #146/#158 ; `UnitsWithoutTrait`
    = filtre TRAIT). Alive filtre via `Damageable` (mirror de la garde `uc.alive` de l'imperatif
    `SpawnUnitOperation.execute_getemruntz`)."""
    from .selectors import Enemies, UnitsWithoutTrait, Damageable
    from ..entities.traits.unit_trait import UnitTrait
    caster_free = CanAddUnit(AdjacentTiles(Caster()))
    enemies = UnitsWithoutTrait(Damageable(Enemies(AllUnits())), int(UnitTrait.Steppable))
    enemy_adj = TileUnique(AdjacentTiles(enemies))
    return TileIntersect(caster_free, enemy_adj)
