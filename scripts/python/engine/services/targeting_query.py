"""`IdunBattle.Core.Services.TargetingQuery` -- l'etage qui DECIDE si la ligne de vue est
interrogee, et avec quel masque d'obscurcissement.

CE QUE CE MODULE FERME (#433-r4-r2-r1-r2). `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions`
retire des candidats par TROIS predicats successifs, et seul le troisieme etait porte (#558) :

    RemoveAll(b__0)                       # ami/ennemi, portee, regles statiques
    RemoveAll(b__1)                       # <-- CE MODULE : la LIGNE DE VUE
    if (rules & TargetMatchesDynamicRule) RemoveAll(b__2)   # GetDynamicInvalidTargetReason (#558)

⚠ **`b__1` n'est gate par AUCUN bit** : il tourne TOUJOURS. Les deux bits `AllowObscuredTargetBy*`
ne decident pas SI le predicat tourne, mais ce qu'il REGARDE -- ils sont consommes a l'interieur
de `TargetingQuery$$GetTilesObscuringTerrain`. C'est pour cela que le troisieme predicat pouvait
etre absent (`rules & 2 == 0`) et l'obscurcissement mordre quand meme, ce que les deux temoins de
#568 montraient sans pouvoir l'expliquer.

LA LAMBDA, VERBATIM (`TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__1`) :

    if (UnitExtensions.IsFriend(target, ctx.caster, ctx.query.state)) return false;   // GARDE
    tiles = ctx.query.GetTilesObscuringTerrain(ctx.caster, ctx.casterTiles, target, ctx.options);
    return tiles.Count > 0;                                                          // RETIRE

ET SON APPELE (`IdunBattle.Core.Services.TargetingQuery$$GetTilesObscuringTerrain`) :

    if (!this.<config @+0x30>.<EnableObscuringTerrain @+0x10>)                    return empty;
    if (UnitExtensions.IsFriendOrHasFriendlyUnitOnIt(target, caster, this.state))  return empty;
    flags = 0;
    if (!UnitExtensions.HasTrait(caster, 0x3ed)                                   // IndirectFire
        && (options.Rules & 0x2000000) == 0)      flags = 2;                      // AllowObscured...Elevation
    r = flags | 4;                                                                // ...ByWalls
    if ((options.Rules & 0x4000000) != 0)         r = flags;
    if (r == 0)                                                                   return empty;
    return this.<movement @+0x20>.<slot 0xf>(casterTiles, target, r, 2);

Les champs de `TargetingQuery` sont ceux de `IdunBattle.Core.Services.TargetingQuery$$Init(this,
attackQuery, battleQuery, movementQuery, state, config)` : `+0x10 attack`, `+0x18 battle`,
`+0x20 movement`, `+0x28 state`, `+0x30 config`. Le drapeau `+0x10` de ce dernier est
**`BC.Targeting.EnableObscuringTerrain`**, present dans la BC (`data/seed-bc.json`) et a `True`
sur le seed courant.

Le `2` litteral du call-site est le `blockingElevationDifference` ; le `r` est un
`idun.meta.ObscuringType` (`None=0, Elevation=2, Wall=4, All=6`). La GEOMETRIE, elle, vit dans
`engine.services.movement_query` (#444) et n'est pas redite ici -- un second corps serait une
seconde verite.

⚠ **QUELLE GEOMETRIE** -- la question est piegee, et la reponse est : NI L'UNE NI L'AUTRE des deux
deja cartographiees. `MovementQuery$$GetTilesObscuringTerrain` n'interroge ni le
`ConnectivityComponent`, ni le champ `neighbours` du `boardGraph` (celui que la porte
`|srcElev - Elevation| < 2` de `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` ampute de
18 aretes sur `MC1_67`) : il TRACE deux lignes de coordonnees
(`IdunBattle.Core.Services.MovementUtil$$DrawLineBetweenCoordinates`, lerp cube + nudge +/-eps +
`RoundFloatCubeCoordinates`), puis interroge chaque coordonnee par
`IdunBattle.Entities.StateExtensions$$GetTileAt`. Aucune ARETE n'est lue -- seulement des
COORDONNEES, l'elevation de la tuile qui s'y trouve, et son drapeau `IsWall`. Le graphe d'adjacence
est donc hors sujet pour ce predicat, dans les deux versions.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from . import movement_query as MQ

Pos = Tuple[int, int]

#: `idun.meta.ObscuringType` -- le 3e argument de `MovementQuery$$GetTilesObscuringTerrain`.
OBSCURING_TYPE_NONE = 0
OBSCURING_TYPE_ELEVATION = 2
OBSCURING_TYPE_WALL = 4
OBSCURING_TYPE_ALL = OBSCURING_TYPE_ELEVATION | OBSCURING_TYPE_WALL

#: Le 4e argument, LITTERAL au call-site de `TargetingQuery$$GetTilesObscuringTerrain`.
BLOCKING_ELEVATION_DIFFERENCE = 2

#: `IdunBattle.Core.Services.TargetingRule` -- les DEUX seuls bits que lit cet etage.
#: (bit 25 / bit 26 ; leur composite `AllowObscuredTarget` vaut 0x6000000.)
ALLOW_OBSCURED_TARGET_BY_ELEVATION = 1 << 25
ALLOW_OBSCURED_TARGET_BY_WALLS = 1 << 26

#: `IdunBattle.Entities.Enum.UnitTrait.IndirectFire` = 1005 = `0x3ed`, le litteral passe a
#: `IdunBattle.Entities.UnitExtensions$$HasTrait` par `TargetingQuery$$GetTilesObscuringTerrain`.
#: Un caster qui le porte est EXEMPTE du volet ELEVATION -- exactement comme le bit 25 du masque.
INDIRECT_FIRE_TRAIT = 1005


def obscuring_type_for(rules: Optional[int], caster_has_indirect_fire: bool = False) -> int:
    """Le `ObscuringType` que `TargetingQuery$$GetTilesObscuringTerrain` compose, VERBATIM :

        flags = 0;
        if (!HasTrait(caster, IndirectFire) && !(rules & AllowObscuredTargetByElevation)) flags = 2;
        r = flags | Wall(4);
        if (rules & AllowObscuredTargetByWalls) r = flags;
        return r;

    Les deux volets sont donc INDEPENDANTS, et `IndirectFire` n'agit QUE sur le volet elevation --
    un caster a tir indirect reste bloque par un MUR.

    `rules is None` (masque non RE-lu) -> `OBSCURING_TYPE_NONE` : le port ne retire alors rien.
    C'est la meme convention permissive que partout dans la cascade de ciblage -- inventer un
    obscurcissement sur un masque qu'on n'a pas lu retirerait des tuiles que le natif garde,
    et un faux NEGATIF est plus couteux qu'un faux positif pour le consommateur (il declarerait
    une unite inoffensive)."""
    if rules is None:
        return OBSCURING_TYPE_NONE
    r = int(rules)
    flags = 0
    if not caster_has_indirect_fire and not (r & ALLOW_OBSCURED_TARGET_BY_ELEVATION):
        flags = OBSCURING_TYPE_ELEVATION
    if r & ALLOW_OBSCURED_TARGET_BY_WALLS:
        return flags
    return flags | OBSCURING_TYPE_WALL


def get_tiles_obscuring_terrain(board, caster_tiles: Optional[Sequence[Pos]],
                                target_tile: Optional[Pos], rules: Optional[int],
                                caster_has_indirect_fire: bool = False,
                                target_is_friend_or_has_friendly_unit: bool = False,
                                enable_obscuring_terrain: bool = True) -> set:
    """`IdunBattle.Core.Services.TargetingQuery$$GetTilesObscuringTerrain(caster, casterTiles,
    target, options)` -- les TROIS gardes, puis la delegation a `MovementQuery`.

    `enable_obscuring_terrain` mirrore `BC.Targeting.EnableObscuringTerrain` (le champ `+0x10` du
    service `config` de `TargetingQuery$$Init`). Il est PARAMETRE et non code en dur : le port ne
    doit pas presumer d'une BC. Le defaut `True` est celui du seed courant.

    `target_is_friend_or_has_friendly_unit` mirrore
    `IdunBattle.Entities.UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt(target, caster, state)` --
    l'OCCUPATION n'etant pas publiee cote DECISION, l'appelant le passe explicitement plutot que
    le port ne le devine. Sur une tuile VIDE le natif rend `false` (`GetUnit(tile) == null`), ce
    qui est le regime du consommateur `IsTileInRangeOfAnyAbility` -- d'ou le defaut."""
    if not enable_obscuring_terrain or target_is_friend_or_has_friendly_unit:
        return set()
    ot = obscuring_type_for(rules, caster_has_indirect_fire)
    if ot == OBSCURING_TYPE_NONE:
        return set()
    return MQ.get_tiles_obscuring_terrain_from_tiles(board, caster_tiles, target_tile, ot,
                                                     BLOCKING_ELEVATION_DIFFERENCE)


def target_is_obscured(board, caster_tiles: Optional[Sequence[Pos]],
                       target_tile: Optional[Pos], rules: Optional[int],
                       caster_has_indirect_fire: bool = False,
                       target_is_friend: bool = False,
                       target_is_friend_or_has_friendly_unit: bool = False,
                       enable_obscuring_terrain: bool = True) -> bool:
    """Le SECOND predicat de `GetPossibleTargetsForOptions` -- `True` = la cible est RETIREE.

        b__1(target) = !IsFriend(target, caster, state)
                       && GetTilesObscuringTerrain(caster, casterTiles, target, options).Count > 0

    La GARDE `IsFriend` porte sur l'entite que `RemoveAll` itere. Quand `GetPossibleTargetTiles`
    force `onlyTiles: 1`, ce sont des TUILES, et `IdunBattle.Entities.EntityExtensions$$GetCurrentPlayer`
    sur une tuile resout l'unite qui l'OCCUPE (branche `UnitExtensions$$GetUnit` du decompile) :
    une tuile VIDE n'a donc pas de joueur, et la garde ne mord pas. L'appelant qui connait
    l'occupation le dit ; le defaut `False` est le regime de la tuile libre.

    `board is None` (aucun canal d'elevation) -> `False` : le port ne retire rien, degradation
    NOMMEE et permissive."""
    if board is None or target_tile is None or target_is_friend:
        return False
    tiles = get_tiles_obscuring_terrain(
        board, caster_tiles, target_tile, rules,
        caster_has_indirect_fire=caster_has_indirect_fire,
        target_is_friend_or_has_friendly_unit=target_is_friend_or_has_friendly_unit,
        enable_obscuring_terrain=enable_obscuring_terrain)
    return len(tiles) > 0
