"""L'emission du DEPLOIEMENT -- mirror de la face STREAM de `SetupGameOperation`.

C'est la premiere chose que le jeu ecrit dans le flux de replay, et c'est le seul morceau
entierement atteignable aujourd'hui : il ne depend d'AUCUNE mecanique de combat, donc d'aucune
ability portee. `case-477r15` § 5 : « A, B, E [...] suffisent a produire un flux comparable sur
le seul deploiement (`System_GameSetup` : `AddPlayer`, `AddTile`, `AddUnit`) ».

LA SEQUENCE NATIVE, lue dans `IdunBattle.Operations.SetupGameOperation$$Execute` :

    Events.StartGroup(GroupType.System_GameSetup, 1, null, null)
      AddPlayers(...)                  -> un `AddPlayerOperation` par joueur
      AddEnvironmentAbilities(...)
      AddTiles(...)                    -> un `AddTileOperation` par tuile
      SetupRoom(...)
      RevealHumanPlayerRoom(...)
      AddPredefinedUnits(...)          -> un `AddUnitOperation` par unite predefinie
      AddPredefinedMachines(...)
      AddBossUnit(...)
      ExecuteStartingMessages(...)
    Events.FinishGroup()

L'entite `1` du groupe racine est en dur dans le decompile (c'est l'entite MATCH) ; le flux reel
le confirme : `Group=System_GameSetup Entity=1 Source= InitialTarget=`.

CE QUE CE MODULE N'EST PAS. Ce n'est PAS un mirror de `SetupGameOperation` : tout ce qui
construit reellement l'etat (creation d'entites, composants, pathfinding, salles, vagues) est
hors sujet ici. Seule la FACE STREAM est portee -- l'ordre et le contenu de ce qui s'ecrit.

L'HYPOTHESE QU'IL PREND, ET CE QU'ELLE LUI INTERDIT. Les identifiants d'entite ECS sont des
ENTREES : ce module ne les calcule pas. L'ordre d'allocation natif (un compteur GLOBAL : 35
tuiles => unites a 49/51/53..., 63 tuiles => 77/79/81...) n'est pas retro-ingenierie, c'est
`#477-r16`. Consequence directe : un emetteur alimente par un etat OBSERVE reproduit les ids,
un emetteur alimente par une simulation PURE ne le peut pas -- et dans ce second cas la
comparaison doit se faire par POSITION, jamais par id.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from ..entities.spawn_source import SpawnSource
from ..services.machine_of_war_position import MachineOfWarPosition
from .dispatcher import StreamDispatcher
from .group_type import GroupType
from .step_type import StepType
from .stream_helper import get_add_unit_tags
from .tag_key import TagKey

#: L'entite du MATCH, argument en dur de `StartGroup` dans `SetupGameOperation$$Execute`.
MATCH_ENTITY_ID = 1


@dataclass(frozen=True)
class PlayerSetup:
    """Une entree d'`AddPlayers`. `entity_id` est l'entite ECS du joueur, `player_id` son
    `PlayerId` de configuration (11/12/13 sur notre seed BC) -- les confondre est le premier
    des trois pieges de lecture de #477-r11."""

    entity_id: int
    player_id: int


@dataclass(frozen=True)
class TileSetup:
    """Une entree d'`AddTiles`, telle que `AddTileOperation$$DispatchTileAddedEvent` la lit :
    `config+0x10` (colonne), `config+0x14` (ligne), `config+0x22` (drapeau territoire)."""

    entity_id: int
    column: int
    row: int
    is_territory: bool = False


@dataclass(frozen=True)
class UnitSetup:
    """Une entree d'`AddPredefinedUnits`, reduite a ce que la face STREAM consomme."""

    entity_id: int
    owner_id: int
    foot_tile_ids: Sequence[int]
    parent_id: int = 0
    source: int = int(SpawnSource.InitialOperations)
    is_boss: bool = False
    foot_count: Optional[int] = None
    """`feet.Count` du natif. `None` => `len(foot_tile_ids)`. Les deux collections sont
    DISTINCTES dans la signature native (`feet` et `unitFeetTileIds`) : le port ne deduit pas
    l'une de l'autre par defaut, il rend la distinction exprimable."""


def add_player(events: StreamDispatcher, player: PlayerSetup) -> None:
    """Face stream d'`IdunBattle.Operations.AddPlayerOperation$$Execute`.

    Le decompile s'y termine par un dictionnaire a UNE entree, puis l'appel d'action :

        tags = new Dictionary<TagKey,int>();
        tags.Add(0x99 /*Player_Id*/, CollectionHelper.AssumePositive(playerId));
        Events.Action(7 /*AddPlayer*/, playerEntity+0x10, tags);
    """
    events.action(StepType.AddPlayer, player.entity_id,
                  {TagKey.Player_Id: int(player.player_id)})


def add_tile(events: StreamDispatcher, tile: TileSetup) -> None:
    """Face stream d'`IdunBattle.Operations.AddTileOperation$$DispatchTileAddedEvent`.

        tags.Add(0x96 /*Tile_Column*/,      config+0x10);
        tags.Add(0x97 /*Tile_Row*/,         config+0x14);
        tags.Add(0x98 /*Tile_IsTerritory*/, config+0x22 != 0);
        Events.Action(8 /*AddTile*/, tile+0x10, tags);
    """
    events.action(StepType.AddTile, tile.entity_id, {
        TagKey.Tile_Column: int(tile.column),
        TagKey.Tile_Row: int(tile.row),
        TagKey.Tile_IsTerritory: 1 if tile.is_territory else 0,
    })


#: Les DEUX plateformes de Machine of War que `SetupGameOperation$$AddMachinePlatform` pose,
#: dans CET ordre : le helper (inline dans `SetupGameOperation$$Execute`) appelle deux fois
#: `AddMachineOfWarPlatform` avec `position = 2` PUIS `position = 1`. Les deux valeurs sont EN
#: DUR dans le decompile -- elles ne dependent ni du board ni du roster.
PLATFORM_POSITIONS = (MachineOfWarPosition.Bottom, MachineOfWarPosition.Top)


def add_machine_platform(events: StreamDispatcher, entity_id: int, position: int) -> None:
    """Face stream d'`IdunBattle.Operations.AddMachineOfWarPlatformOperation$$Execute`.

        tags.Add(0xd1 /*MachinePosition*/, position);
        Events.Action(0x2b /*AddMachinePlatform*/, platform+0x10, tags);

    Aucun `StartGroup` / `FinishGroup` : l'operation emet une `Action` NUE, dans le groupe
    ouvert par son appelant -- ici `System_GameSetup`."""
    events.action(StepType.AddMachinePlatform, entity_id,
                  {TagKey.MachinePosition: int(position)})


def add_unit(events: StreamDispatcher, unit: UnitSetup,
             use_group: bool = True) -> None:
    """Face stream d'`IdunBattle.Operations.AddUnitOperation$$Execute` : un GROUPE `AddUnit`
    dont la premiere action est `Action=AddUnit`, tags fabriques par
    `IdunBattle.Core.Services.StreamHelper$$GetAddUnitTags`.

    ⚠ LE GROUPE EST CONDITIONNEL, ET CE N'EST PAS UN DETAIL. `StartGroup` ET `FinishGroup` sont
    tous deux enveloppes dans le meme test `IdunBattle.Core.Services.BattleQuery$$get_UseGroupForAddUnit`
    (un drapeau de la configuration de bataille). Si le drapeau est faux, les trois `Action` sont
    emis SANS groupe englobant. Un port qui ouvrirait toujours le groupe divergerait des que la
    config le desarme -- d'ou ce parametre, plutot qu'une structure en dur. La valeur `True` par
    defaut est celle OBSERVEE sur nos runners, pas une lecture du decompile.

    ⚠ COUVERTURE PARTIELLE, ET C'EST PUBLIE. Le groupe natif contient AUSSI un
    `Action=ChangeStats` (16 tags) puis un `Action=ChangeAbility` par ability -- actives d'abord,
    declenchees ensuite. Leurs tags viennent des trois surcharges de
    `IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags`, qui n'est PAS un
    `StreamHelper$$Get*Tags` : c'est la tranche D, et le comparateur classe ces lignes en
    divergence CONNUE, jamais en « egal »."""
    if use_group:
        # `sourceId` : le decompile passe ici un handle de litteral de chaine, NON RESOLUBLE
        # statiquement (les chaines .NET vivent dans `global-metadata.dat`). Ce n'est PAS le
        # litteral 0 de `SetupGameOperation$$Execute`. Le flux reel tranche : `Source=` est VIDE
        # -- donc chaine vide ou null, indiscernables apres `String.Format`.
        events.start_group(GroupType.AddUnit, unit.entity_id, None, None)
    foot_count = (len(unit.foot_tile_ids) if unit.foot_count is None
                  else int(unit.foot_count))
    events.action(StepType.AddUnit, unit.entity_id,
                  get_add_unit_tags(owner_id=unit.owner_id,
                                    parent_id=unit.parent_id,
                                    source=unit.source,
                                    is_boss=unit.is_boss,
                                    foot_count=foot_count,
                                    unit_feet_tile_ids=unit.foot_tile_ids))
    if use_group:
        events.finish_group()


@dataclass
class GameSetup:
    """Les entrees du deploiement, dans l'ordre ou `SetupGameOperation$$Execute` les consomme."""

    players: Sequence[PlayerSetup] = field(default_factory=tuple)
    tiles: Sequence[TileSetup] = field(default_factory=tuple)
    units: Sequence[UnitSetup] = field(default_factory=tuple)
    platform_entity_ids: Sequence[int] = field(default_factory=tuple)
    """Ids d'entite des DEUX plateformes de MoW, dans l'ordre de `PLATFORM_POSITIONS`. Vide =
    ne pas emettre (le port ne SAIT pas encore predire ces ids -- `#477-r16`)."""
    use_group_for_add_unit: bool = True
    """`IdunBattle.Core.Services.BattleQuery$$get_UseGroupForAddUnit` -- cf. `add_unit`."""


def emit_game_setup(events: StreamDispatcher, setup: GameSetup) -> None:
    """Face stream d'`IdunBattle.Operations.SetupGameOperation$$Execute`.

    L'ORDRE est celui du decompile : `AddPlayers`, puis `AddTiles`, puis (via `AddMachinePlatform`
    inline) les deux plateformes, puis `AddPredefinedUnits`. La POSITION des plateformes entre
    `AddTiles` et `AddPredefinedUnits` est en revanche MESUREE sur le flux reel : le decompile
    montre plusieurs helpers entre les deux (`SetupRoom`, `RevealHumanPlayerRoom`) et n'ordonne
    pas l'inline de facon lisible.

    Le `FinishGroup` final ramene la pile a zero, donc `StreamCache$$SendRootGroupIfFinished`
    flushe le groupe racine a ses listeners : c'est la que le texte devient comparable."""
    events.start_group(GroupType.System_GameSetup, MATCH_ENTITY_ID, None, None)
    for player in setup.players:
        add_player(events, player)
    for tile in setup.tiles:
        add_tile(events, tile)
    for entity_id, position in zip(setup.platform_entity_ids, PLATFORM_POSITIONS):
        add_machine_platform(events, entity_id, position)
    for unit in setup.units:
        add_unit(events, unit, use_group=setup.use_group_for_add_unit)
    events.finish_group()
