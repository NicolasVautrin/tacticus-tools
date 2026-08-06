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

LES IDENTIFIANTS D'ENTITE ECS SE DERIVENT DESORMAIS -- `assign_entity_ids` ci-dessous.
Ce module les acceptait comme de pures ENTREES tant que l'allocateur n'etait pas porte ; il
l'est (`engine/streams/entity_allocator.py`, `#477-r21-r3`), et la mesure est exacte sur trois
scenarios : 50 / 78 / 72 identifiants de deploiement produits sans en lire aucun. Les champs
`entity_id` restent des entrees ACCEPTEES -- un appelant qui possede l'etat observe continue de
les fournir -- mais un emetteur alimente par une simulation pure passe par `assign_entity_ids`
et n'a plus a comparer par POSITION.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional, Sequence, Tuple

from ..entities.spawn_source import SpawnSource
from ..services.machine_of_war_position import MachineOfWarPosition
from .dispatcher import StreamDispatcher
from .entity_allocator import MATCH_ENTITY_ID as ALLOCATOR_MATCH_ENTITY_ID
from .entity_allocator import MatchComponent, new_match_after_setup
from .group_type import GroupType
from .step_type import StepType
from .stream_helper import get_add_unit_tags
from .tag_key import TagKey
from .unit_extensions import (ActiveAbilityState, TriggeredAbilityState, UnitFullState,
                              get_full_state_update_tags,
                              get_full_state_update_tags_for_active,
                              get_full_state_update_tags_for_triggered)

#: L'entite du MATCH, argument en dur de `StartGroup` dans `SetupGameOperation$$Execute`. Meme
#: litteral que celui passe a `Blueprints$$Match` : le foyer est `entity_allocator`, qui porte
#: la raison pour laquelle cette entite N'EST PAS allouee par `NextId`. Re-exporte ici parce que
#: le nom fait partie de l'API de ce module depuis #477-r15.
MATCH_ENTITY_ID = ALLOCATOR_MATCH_ENTITY_ID


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
    full_state: Optional[UnitFullState] = None
    """Le substrat d'`Action=ChangeStats`. `None` = L'APPELANT NE FOURNIT PAS L'ETAT, donc rien
    n'est emis -- le port n'invente aucune stat. Ce n'est PAS le natif, qui emet toujours la
    ligne : c'est le seul degre de liberte du mirror, et il est visible ici plutot que dilue
    dans seize valeurs par defaut. Le comparateur classe alors la ligne absente en divergence,
    jamais en « egal »."""
    active_abilities: Sequence[ActiveAbilityState] = ()
    """`ActiveAbilityComponent.Abilities(+0x20)`, DANS SON ORDRE -- une `Action=ChangeAbility`
    chacune. L'ordre est celui de la collection native, pas un tri du port."""
    triggered_abilities: Sequence[Tuple[int, TriggeredAbilityState]] = ()
    """`TriggeredAbilityComponent.Abilities(+0x18)`, DANS SON ORDRE : `(TriggeredAbilityType,
    etat)`. Emises APRES toutes les actives."""


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

    LE GROUPE PORTE TROIS FORMES D'ACTION, dans cet ordre (lu verbatim dans le decompile,
    et identique dans `AddMachineOperation$$Execute` / `ResurrectUnitOperation$$SendStreamEvents`) :

        Action=AddUnit        tags de `StreamHelper$$GetAddUnitTags`
        Action=ChangeStats    tags de `UnitExtensions$$GetFullStateUpdateTags(unit)`
        Action=ChangeAbility  une par ACTIVE, puis une par DECLENCHEE

    L'entite de toutes ces lignes est l'UNITE, jamais l'ability."""
    if use_group:
        # `sourceId` : le handle de chaine que `AddUnitOperation$$Execute` passe ici est LU
        # depuis `#477-r15-r1` (`data/symbols/<build>/metadata/string_literals.tsv`), et il vaut
        # la chaine VIDE -- pas `null`. Les deux rendent le meme texte apres `String.Format` ;
        # c'est la lecture qui tranche, plus le flux. Le port passe `None`, ce qui produit le
        # meme `Source=` vide : la distinction n'est pas observable dans le flux.
        # ⚠ Et `Source=` NON VIDE n'est PAS un litteral : `#477-r15-r1` mesure 8 sources non
        # vides sur un deroule reel, 8/8 des membres d'enum rendus par `Enum.ToString()`
        # (1/8 seulement est aussi un litteral). Ce qui manque pour les emettre n'est donc pas
        # une table de chaines -- c'est de savoir QUEL enum et QUEL ordinal chaque producteur
        # passe a `StartGroup`, `BigTarget` ayant a lui seul deux porteurs.
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
    if unit.full_state is not None:
        events.action(StepType.ChangeStats, unit.entity_id,
                      get_full_state_update_tags(unit.full_state))
    for active in unit.active_abilities:
        events.action(StepType.ChangeAbility, unit.entity_id,
                      get_full_state_update_tags_for_active(active))
    for triggered_ability, state in unit.triggered_abilities:
        events.action(StepType.ChangeAbility, unit.entity_id,
                      get_full_state_update_tags_for_triggered(triggered_ability, state))
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
    ne pas emettre. `assign_entity_ids` les REMPLIT toujours : les deux plateformes sont posees
    inconditionnellement par `SetupGameOperation$$AddMachinePlatform`, donc un setup derive n'a
    aucune raison de les taire."""
    use_group_for_add_unit: bool = True
    """`IdunBattle.Core.Services.BattleQuery$$get_UseGroupForAddUnit` -- cf. `add_unit`."""


def assign_entity_ids(setup: GameSetup, *, environment_ability_count: int
                      ) -> Tuple[GameSetup, MatchComponent]:
    """DERIVE tous les identifiants d'entite du deploiement, et rend le compteur POUR LA SUITE.

    C'est le raccord de `#477-r21-r3` : `entity_allocator` porte la regle, ce helper la branche
    sur la structure que `emit_game_setup` consomme. Les `entity_id` du `setup` recu sont
    IGNORES -- seule sa STRUCTURE compte (nombre de joueurs, de tuiles, d'unites, et le nombre
    de pieds de chacune).

    `environment_ability_count` est le SEUL terme qui ne se lit pas dans le `setup` : les
    abilities d'environnement sont allouees entre les joueurs et les tuiles SANS emettre la
    moindre ligne. Sa regle -- deux tables statiques du binaire et trois termes dedupliques --
    est etablie et confrontee par `#477-r16` (`probe_477r16_allocation_entites_ecs.deriver_regle`).
    Le passer FAUX decale tout ce qui suit ; c'est pourquoi il est explicite et sans defaut.

    ⚠ LE COMPTEUR RENDU N'EST PAS UN DETAIL : c'est lui qui porte l'ANCRE du deroule. Le premier
    `entity_allocator.add_effect(match)` d'apres rend exactement l'identifiant que le natif
    donne au premier effet cree (mesure #477-r21-r3 : 59 / 87 / 81 sur trois scenarios)."""
    match, alloc = new_match_after_setup(
        player_count=len(setup.players),
        environment_ability_count=int(environment_ability_count),
        tile_count=len(setup.tiles),
        machine_of_war_platform_count=len(PLATFORM_POSITIONS),
        unit_foot_counts=[(len(u.foot_tile_ids) if u.foot_count is None else int(u.foot_count))
                          for u in setup.units])
    players = tuple(replace(p, entity_id=eid) for p, eid in zip(setup.players, alloc.players))
    tiles = tuple(replace(t, entity_id=eid) for t, eid in zip(setup.tiles, alloc.tiles))
    units = tuple(replace(u, entity_id=a.entity_id)
                  for u, a in zip(setup.units, alloc.units))
    return (replace(setup, players=players, tiles=tiles, units=units,
                    platform_entity_ids=tuple(alloc.machine_of_war_platforms)),
            match)


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
