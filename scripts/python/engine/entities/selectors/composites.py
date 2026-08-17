"""Selecteurs COMPOSITES : ceux qui assemblent des noeuds de plusieurs tranches.

Isoles ici parce qu'ils sont les SEULS a dependre de `units`, `tiles` ET `accessors` :
les laisser dans une tranche y aurait cree un cycle d'import. Ce module est une
FEUILLE du graphe -- personne n'importe depuis lui a l'interieur du package."""
from __future__ import annotations

from ...dsl.base import AAmountFormula, TargetsSelector
from .units import Enemies, Sub, Units, UnitsWithoutTrait
from .tiles import AdjacentTiles, AllAliveUnits, CanAddUnit, Caster, TileIntersect, TileUnique
from .geometry import PickRandomly
from ..traits.unit_trait import UnitTrait
from ..unit_selection_type import UnitSelectionType


def attackable_enemies(unit: TargetsSelector = None,
                       source: TargetsSelector = None) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLSelectors$$AttackableEnemies(unit)` -- le corps natif ENTIER,
    transcrit :

        entities = DSLSelectors$$Enemies(unit, this.<+0x20 = AllAliveUnits>,
                                         UnitSelectionType.OnlyAliveAndTargetable);
        return     DSLSelectors$$UnitsWithoutTrait(entities, UnitTrait.Steppable,
                                                   UnitSelectionType.OnlyAliveAndTargetable);

    Ce n'est donc PAS une classe : c'est un COMPOSITE de deux noeuds deja portes, et l'ecrire comme
    tel est ce qui garantit qu'il n'existe pas une TROISIEME implementation de << ennemi >> ni de
    << non Steppable >> dans le depot -- c'est aussi, litteralement, le meme couple que
    `get_spawn_tile_selector` ci-dessous compose deja. Les DEUX `selectionType` valent `3` au
    decompile et doivent etre poses : sans eux, les deux etages ne filtreraient RIEN (defaut
    historique `None`, #585-r1).

    `unit` = le referent d'alliance (`Owner@DSLSelectors+0x30` chez `MartialExemplarAbility$$
    ExecuteBehaviour` et `TheBetrayer_TakeTurnAbility$$GetAttackTarget`, les DEUX seuls appelants du
    build). ⚠ Le noeud `Enemies` du port lit ce referent dans `ctx.caster`, PAS dans un argument :
    le parametre est conserve pour le mirror structurel de la signature native et pour rendre le
    site grepable, mais l'alliance reste evaluee au contexte -- exact tant que `Owner == Caster`,
    ce qui est le cas des deux appelants (une active castee par son porteur).

    `source` = le champ partage `<DSLSelectors>+0x20` ; defaut `AllAliveUnits()`, qui EST ce champ
    (cf. la docstring de `tiles.AllAliveUnits`). #889-r5."""
    _ = unit                                     # cf. docstring : l'alliance vient de `ctx.caster`
    st = int(UnitSelectionType.OnlyAliveAndTargetable)
    return UnitsWithoutTrait(
        Enemies(source if source is not None else AllAliveUnits(), selection_type=st),
        int(UnitTrait.Steppable), selection_type=st)


def adjacent_units(source: TargetsSelector, selection_type=None) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(source, mode, mask)` — MIRROR TEXTUEL du
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


def random_adjacent_free_tile(origin: TargetsSelector, amount: AAmountFormula) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLSelectors$$RandomAdjacentFreeTile(origin, amount)` -- le corps
    natif ENTIER, transcrit (la factory n'alloue AUCUN selecteur dedie, elle COMPOSE) :

        var tiles = DSLSelectors$$AdjacentTiles(origin);
        tiles     = DSLSelectors$$CanAddUnit(tiles);                 // surcharge a UN argument
        return new Entities.Selectors.PickRandomAmountSelector(state, tiles, amount, random,
                                                               false, 0x7fffffff, false);

    soit : tirage aleatoire de `amount` tuiles parmi les tuiles hex-adjacentes a `origin` ou une
    unite PEUT etre posee. Les trois derniers arguments du `PickRandomAmountSelector` sont des
    CONSTANTES du site (`allowDuplicates = false`, `maxDuplicates = 0x7fffffff`,
    `ignoreForcedTargets = false`) : ce sont exactement les defauts de `geometry.PickRandomly`, donc
    le composite ne les repose pas -- les ecrire serait dupliquer une valeur au lieu de la lire.

    ⚠ `CanAddUnit` est appele ici par sa surcharge a **UN** argument (`tiles`), pas par celle a deux
    (`tiles, isSteppable`) ni celle a trois (`tiles, parent, isSteppable`) -- LU au call-site
    (`DSLSelectors$$RandomAdjacentFreeTile` appelle `CanAddUnit(this, pvVar1)`). Le port laisse donc
    `allow_steppable` a son defaut.

    ⚠ **ET CE DEFAUT EST `True` DEPUIS #462-...-r5-r3 -- la phrase qui vivait ici (<< passer `True`
    autoriserait la pose sur un `Steppable` occupe >>) etait une DEDUCTION, et elle etait FAUSSE.**
    La surcharge a UN argument code son trigger EN DUR a `<DSLTriggers+0x48>` (relu :
    `mov rbx,[rax+0x88]` puis `mov rbx,[rbx+0x48]` dans `DSLSelectors$$CanAddUnit` @ la surcharge a
    123 xrefs), et `+0x48` est `op_LogicalNot(<trigger nu>)` -> `ShouldTrigger` FAUX ->
    `allowSteppable` **VRAI**. C'est le MEME appariement slot/valeur que
    `tests/engine/runner/test_955r2_free_tiles_steppable_offline.py` grave deja pour
    `FreeTilesOrAdjacentFreeTiles` ; ce site-ci en heritait la conclusion INVERSE parce que personne
    n'avait relu le corps de la surcharge a un argument.

    Unique appelant PORTE : `IdunBattleLogic.Entities.Abilities.Active.Loki.BioMinefieldAbility$$
    ExecuteBehaviour` (branche `else` du `If` : `RandomAdjacentFreeTile(Target@+0x60,
    Direct(GetNumberConstant(nrOfSummons_2)))`). L'autre appelant du build est
    `AutoSummonOnDamageAbility`, non porte. (#939)"""
    return PickRandomly(CanAddUnit(AdjacentTiles(origin)), amount)


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
