"""Selecteurs COMPOSITES : ceux qui assemblent des noeuds de plusieurs tranches.

Isoles ici parce qu'ils sont les SEULS a dependre de `units`, `tiles` ET `accessors` :
les laisser dans une tranche y aurait cree un cycle d'import. Ce module est une
FEUILLE du graphe -- personne n'importe depuis lui a l'interieur du package."""
from __future__ import annotations

from ...dsl.base import TargetsSelector
from .units import Enemies, UnitsWithoutTrait
from .tiles import AdjacentTiles, AllUnits, CanAddUnit, Caster, TileIntersect, TileUnique


def get_spawn_tile_selector() -> TargetsSelector:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector` (mirror 1:1, confirme LIVE #200 tracer-v2) =
        op_BitwiseAnd( CanAddUnit(AdjacentTiles(caster)),
                       Unique(AdjacentTiles( UnitsWithoutTrait(Enemies(AllUnits), 0x1b) )) )
    = ids de tuiles LIBRES (walkable + inoccupees) adjacentes au CASTER **ET** adjacentes a un
    ENNEMI vivant non-`Steppable` (0x1b=27, cf. `UnitTrait.Steppable` #146/#158 ; `UnitsWithoutTrait`
    = filtre TRAIT). **AUCUN noeud `Damageable`** : le natif n'en a pas (decompile + capture live
    tracer-v2 concordent) — l'exclusion des morts est portee par `AllUnits`=`AllAliveMachinesSelector`
    (#202). Enemies/UnitsWithoutTrait = meme module."""
    from ..traits.unit_trait import UnitTrait
    caster_free = CanAddUnit(AdjacentTiles(Caster()))
    enemies = UnitsWithoutTrait(Enemies(AllUnits()), int(UnitTrait.Steppable))
    enemy_adj = TileUnique(AdjacentTiles(enemies))
    return TileIntersect(caster_free, enemy_adj)
