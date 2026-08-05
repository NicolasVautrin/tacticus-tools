"""`IdunBattle.Core.Services.TargetingQuery` -- l'etage qui DECIDE si la ligne de vue est
interrogee, et avec quel masque d'obscurcissement.

CE QUE CE MODULE FERME (#433-r4-r2-r1-r2). `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions`
retire des candidats par TROIS predicats successifs, et seul le troisieme etait porte (#558) :

    zone = GetTilesInRange(...)           # <-- CE MODULE AUSSI : le retrait des NON MARCHABLES
    RemoveAll(b__0)                       # ami/ennemi, portee, regles statiques
    RemoveAll(b__1)                       # <-- CE MODULE : la LIGNE DE VUE
    if (rules & TargetMatchesDynamicRule) RemoveAll(b__2)   # GetDynamicInvalidTargetReason (#558)

⚠ La premiere ligne n'est PAS un quatrieme predicat : le retrait des tuiles non marchables vit
DANS la fonction qui CONSTRUIT la zone, donc en AMONT des trois `RemoveAll` -- c'est la reponse a
`#433-r4-r2-r1-r2-r2-r1`, portee par `tile_removed_by_walkability`.

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
from ..entities.traits.unit_trait import UnitTrait   # #270-r1-r1-r3

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

#: `IdunBattle.Core.Services.TargetingRule.AllowUnwalkableTargetTile` (bit 43) -- le SEUL bit que
#: lit l'etage AMONT `GetTilesInRange` (cf. `tile_removed_by_walkability`). Nomme ici plutot
#: qu'importe de `engine.runner.abilities.targeting_rule` : ce module ne depend pas du registre
#: COMBAT, et le litteral est celui du decompile.
ALLOW_UNWALKABLE_TARGET_TILE = 1 << 43

#: `IdunBattle.Entities.Enum.UnitTrait.IndirectFire` = 1005 = `0x3ed`, le litteral passe a
#: `IdunBattle.Entities.UnitExtensions$$HasTrait` par `TargetingQuery$$GetTilesObscuringTerrain`.
#: Un caster qui le porte est EXEMPTE du volet ELEVATION -- exactement comme le bit 25 du masque.
INDIRECT_FIRE_TRAIT = UnitTrait.IndirectFire

#: `IdunBattle.Core.TeamId` -- `0=Environment, 1=Team1_Default, 2=Team2_DefaultEnemy, 3=Team3`
#: (enum LU dans `data/symbols/<build>/frida/enums.tsv`). Le `0` n'est PAS « pas d'equipe » : c'est
#: l'equipe ENVIRONNEMENT, et c'est aussi la valeur que rendent les deux gardes ci-dessous quand
#: `EntityExtensions$$GetCurrentPlayer` ne resout AUCUN joueur -- d'ou leur asymetrie.
TEAM_ENVIRONMENT = 0


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


def tile_removed_by_walkability(rules: Optional[int], walkable: Optional[bool],
                                is_in_fog: Optional[bool] = None) -> bool:
    """L'etage AMONT : `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` retire de la zone
    toute tuile NON MARCHABLE. `True` = la tuile est RETIREE.

    C'EST UN ETAGE DISTINCT, ET IL EST EN AMONT DE LA LIGNE DE VUE (#433-r4-r2-r1-r2-r2-r1). Le
    retrait n'est PAS l'un des trois predicats de `GetPossibleTargetsForOptions` (`b__0` ami/portee,
    `b__1` ligne de vue, `b__2` gate dynamique) : il vit DANS la fonction qui CONSTRUIT la zone,
    donc avant que ces predicats ne la voient. Fin de `GetTilesInRange`, VERBATIM :

        if ((options.Rules & AllowUnwalkableTargetTile) == 0)      // bit 43
            <cache statique>.RemoveAll(zone, TargetingQuery.<>c.<GetTilesInRange>b__36_0);

    et la lambda, `IdunBattle.Core.Services.TargetingQuery.u003Cu003Ec$$u003CGetTilesInRangeu003Eb__36_0` :

        b__36_0(t) = !IdunBattle.Entities.TileExtensions$$IsWalkable(t, checkFog: true)

    Le MEME bit 43 est en outre passe en `onlyWalkableTiles` aux deux slots `IBattleQuery` qui
    construisent la zone (`0x67` GetTilesInRadius, `0x51` GetAdjacentTiles) : le `RemoveAll` final
    est donc IDEMPOTENT pour ces branches, et n'est indispensable que pour celles qui ne filtrent
    pas (`UseWholeBoard` -> slot `0x69` GetAllTiles, et la branche `casterTiles` de portee nulle).

    LES DEUX VOLETS DE `IsWalkable`, et pourquoi il en faut DEUX canaux :

        IsWalkable(tile, checkFog) :
            if (tile == null)                            return false;
            m = tile.<MovementComponent @+0x40>;
            if (m.<+0x10> != 0)                          return false;   # terrain infranchissable
            if (!checkFog)                               return true;
            return tile.<TileComponent @+0x20>.<IsInFogOfWar @+0x40> == 0;

    * le PREMIER volet est EXACTEMENT ce que rend `IdunBattle.Core.Services.BattleQuery$$IsWalkableTile`
      (`IsTile(tile) && comp.<+0x10> == 0`), donc le champ `walkable` du `boardGraph` ;
    * le SECOND volet n'y est PAS -- `IsWalkableTile` n'a pas de parametre `checkFog`. Il se lit sur
      le champ `isInFog` du meme `boardGraph` (`TileComponent+0x40`, publie depuis #403).
      MESURE (2026-08-04, board `C6_02`) : **31 tuiles sur 63** sont `walkable == True` ET
      `isInFog == True`. Rabattre l'un sur l'autre laisserait donc 31 tuiles attribuees a tort.

    `rules is None` (masque non RE-lu) -> `False` : meme convention permissive que le reste de la
    cascade. C'est un ECART NOMME -- le natif, lui, RETIRE par defaut (sur les 106 masques lus du
    port, un SEUL porte le bit 43 : `1116 RadBombardment`).
    `walkable is None` / `is_in_fog is None` -> le volet correspondant ne retire rien : canal muet
    n'est pas canal a `False`."""
    if rules is None or (int(rules) & ALLOW_UNWALKABLE_TARGET_TILE):
        return False
    if walkable is not None and not bool(walkable):
        return True                       # `m.<+0x10> != 0` -- terrain infranchissable
    return bool(is_in_fog) if is_in_fog is not None else False


def friend_gates_for_tile_target(caster_team: Optional[int],
                                 occupant_team: Optional[int]) -> Tuple[bool, bool]:
    """Les DEUX gardes « ami » du predicat, evaluees pour une cible qui est une **TUILE** --
    le regime que `TargetingQuery$$GetPossibleTargetTiles` impose (`onlyTiles: 1`).

    Rend `(target_is_friend, target_is_friend_or_has_friendly_unit)`, les deux parametres du
    mirror ci-dessous. `caster_team` / `occupant_team` sont des `IdunBattle.Core.TeamId`
    (`observeBattle.units[].teamId` = `PlayerComponent+0x24`) ; `occupant_team is None` = tuile
    SANS unite. Un `caster_team is None` (canal muet) rend `(False, False)` -- le statu quo, qui
    ne peut que RETIRER davantage, et c'est la degradation NOMMEE.

    LES DEUX GARDES NE LISENT PAS LA MEME CHOSE, et c'est le coeur de `#433-r4-r2-r1-r2-r2` :

    * **`IdunBattle.Entities.UnitExtensions$$IsFriend(target, caster, state)`** (la garde de la
      lambda `TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__1`)
      compare `GetCurrentPlayer(target)` a `GetCurrentPlayer(caster)`, chacun rabattu sur `0`
      quand il ne resout rien. Or `IdunBattle.Entities.EntityExtensions$$GetCurrentPlayer` ne
      teste que TROIS classes -- `PlayerEntity` (rend `this`), `FootEntity` (`GetUnit` puis
      recursion) et `UnitEntity` (`OwnerComponent+0x20`) -- et retombe sinon sur un
      `TryGetComponent<OwnerComponent>` que la **`TileEntity` NE PORTE PAS**.
      => sur une TUILE, `GetCurrentPlayer` rend `null`, donc `0`, et **l'occupant n'est jamais
      resolu**. La garde se reduit alors a `TeamId(caster) == Environment(0)` : une CONSTANTE du
      caster, pas une propriete de la tuile.
      ⚠ La fiche precedente lisait « `GetCurrentPlayer` sur une tuile resout l'unite qui
      l'OCCUPE (branche `UnitExtensions$$GetUnit` du decompile) ». C'est REFUTE : cette branche
      est celle de `FootEntity` (identifiee par ses xrefs `Blueprints$$UnitFoot` /
      `FootEntity$$Copy`), pas celle de la tuile (`Blueprints$$Tile` / `TileEntity$$Copy`).
      Le port passait `False`, ce qui reste JUSTE dans nos runners -- mais par accident.

    * **`IdunBattle.Entities.UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt(target, caster,
      state)`** (la garde de `TargetingQuery$$GetTilesObscuringTerrain`), elle, passe par
      `IdunBattle.Entities.UnitExtensions$$GetUnit(target, state)`, qui TESTE bien `TileEntity`
      (`TileContentComponent+0x38`, `IsFilled` -> resolution de l'occupant). Elle vaut donc
      « la tuile porte une unite de la MEME equipe que le caster », et c'est elle qui mord.
      Son premier gate est `EntityExtensions$$IsUnit(caster)`, inline dans le decompile
      (`FUN_180002590(1, <Entity>, caster) == 1`, meme corps que `EntityExtensions$$IsUnit`) :
      un caster qui n'est pas une unite rend `false`. Le port n'appelle ce foyer que pour des
      unites, donc ce terme est constant a `True` ici."""
    if caster_team is None:
        return False, False
    ct = int(caster_team)
    is_friend = (ct == TEAM_ENVIRONMENT)
    has_friendly = (occupant_team is not None and int(occupant_team) == ct)
    return is_friend, has_friendly


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
    `IdunBattle.Entities.UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt(target, caster, state)` :
    « la cible EST une unite amie, OU porte une unite amie ». Sur une tuile VIDE le natif rend
    `false` (`GetUnit(tile) == null`) -- d'ou le defaut. L'appelant qui connait l'occupation le
    calcule par `friend_gates_for_tile_target` (#433-r4-r2-r1-r2-r2) : le canal existe
    (`observeBattle.units[].teamId` + `col`/`row`), il n'etait pas LU."""
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
    force `onlyTiles: 1`, ce sont des TUILES -- et `IdunBattle.Entities.EntityExtensions$$GetCurrentPlayer`
    **ne resout PAS** l'occupant d'une tuile (elle ne branche que sur `PlayerEntity`, `FootEntity`
    et `UnitEntity`, puis retombe sur un `TryGetComponent<OwnerComponent>` absent de la
    `TileEntity`). La garde vaut donc `TeamId(caster) == Environment(0)` : voir
    `friend_gates_for_tile_target`, qui la calcule pour l'appelant. Le defaut `False` reste le
    statu quo quand le canal d'equipe est muet.

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
