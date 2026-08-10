"""Selecteurs COMPOSITES : ceux qui assemblent des noeuds de plusieurs tranches.

Isoles ici parce qu'ils sont les SEULS a dependre de `units`, `tiles` ET `accessors` :
les laisser dans une tranche y aurait cree un cycle d'import. Ce module est une
FEUILLE du graphe -- personne n'importe depuis lui a l'interieur du package."""
from __future__ import annotations

from ...dsl.base import TargetsSelector
from .units import Enemies, Sub, Units, UnitsWithoutTrait
from .tiles import AdjacentTiles, AllAliveUnits, CanAddUnit, Caster, TileIntersect, TileUnique
from ..traits.unit_trait import UnitTrait


def adjacent_units(source: TargetsSelector, selection_type=None) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits(source, mode, mask)` — MIRROR TEXTUEL du
    decompile (la factory native n'alloue AUCUN selecteur dedie, elle COMPOSE) :

        AdjacentTiles(source) -> Units(<ces tuiles>, mode, mask) -> op_Subtraction(<ces unites>, source)

    donc : les occupants (VIVANTS, cf. `Units`) des tuiles hex-adjacentes a CHAQUE entite de `source`,
    MOINS les entites de `source` elles-memes.

    Pourquoi ce helper A COTE de la classe `AdjacentUnits` (units.py) : cette derniere passe par
    `_within(units, center, radius)`, qui n'accepte qu'UN centre (dict ou position) -- suffisant pour
    tous ses call-sites historiques (`AdjacentUnits(TargetTile())`), mais IMPOSSIBLE des que la source
    est un ENSEMBLE. Le natif, lui, itere le selecteur de tuiles : la bande TERTIAIRE de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$ExecuteBehaviour` passe
    justement l'ENSEMBLE des cibles secondaires (`AdjacentUnits(Cache(<secondaires>), 1, 3)`).
    On mirror donc la COMPOSITION native, qui est exacte pour un centre comme pour N :
    l'exclusion finale est `- source` (appartenance a l'ensemble), PAS « distance > 0 » -- une unite
    de `source` adjacente a une AUTRE unite de `source` est bien retiree ici, alors qu'un `d > 0`
    par-centre l'aurait gardee.

    board absent -> `AdjacentTiles` rend [] -> ensemble vide (degradation deja documentee du domaine
    tuile).

    `selection_type` = le 3e argument NATIF (`mask` ci-dessus), que la factory passe a son `Units`
    interne -- relu sur `rnca9r7q6c` : `AdjacentUnits(this, origin, unique, selectionType)` =
    `op_Subtraction(Units(this, AdjacentTiles(this, origin), unique, selectionType), origin)`. Le
    port l'AVALAIT (#585-r1), alors que le call-site cite ci-dessus passe justement `3`. `None` =
    comportement HISTORIQUE. Le flag `unique`, lui, reste hors parametre : residu `#433-r3-r1a-r1`."""
    return Sub(Units(AdjacentTiles(source), selection_type), source)


def get_spawn_tile_selector() -> TargetsSelector:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector` (mirror 1:1, confirme LIVE #200 tracer-v2) =
        op_BitwiseAnd( CanAddUnit(AdjacentTiles(caster)),
                       Unique(AdjacentTiles( UnitsWithoutTrait(
                           Enemies(<dsl>+0x48 = Caster, <dsl>+0x20, 3), 0x1b) )) )
    = ids de tuiles LIBRES (walkable + inoccupees) adjacentes au CASTER **ET** adjacentes a un
    ENNEMI vivant non-`Steppable` (0x1b=27, cf. `UnitTrait.Steppable` #146/#158 ; `UnitsWithoutTrait`
    = filtre TRAIT). **AUCUN noeud `Damageable`** : le natif n'en a pas (decompile + capture live
    tracer-v2 concordent) — l'exclusion des morts est portee par la SOURCE, le champ partage
    `<dsl>+0x20` = `IdunBattle.Entities.Selectors.AllAliveUnitsSelector` (pool
    `EntityPool.AliveUnits`), porte `AllAliveUnits()` (#202, ré-attribué par #514 : ce n'est ni
    `DSLSelectors$$AllUnits` ni `AllAliveMachinesSelector`). Enemies/UnitsWithoutTrait = meme module."""
    caster_free = CanAddUnit(AdjacentTiles(Caster()))
    enemies = UnitsWithoutTrait(Enemies(AllAliveUnits()), int(UnitTrait.Steppable))
    enemy_adj = TileUnique(AdjacentTiles(enemies))
    return TileIntersect(caster_free, enemy_adj)
