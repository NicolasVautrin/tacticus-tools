"""L'ALLOCATION des identifiants d'entite ECS -- mirror de `MatchComponent$$NextId` et des NEUF
sites qui le consomment, y compris le versant EFFET (`#477-r21-r3`).

POURQUOI CE MODULE EXISTE. Tout le paquet `engine.streams` RECEVAIT ses identifiants d'entite :
`PlayerSetup.entity_id`, `TileSetup.entity_id`, `UnitSetup.entity_id`, `EffectSetup.entity_id`
etaient des ENTREES, et c'est ce qui rendait un `Group=Effect_Refresh` REPRODUCTIBLE mais jamais
AUTONOME (#477-r21 § 5 : 34/40, 36/42, 12/12 reproduits ; 0 autonome). #477-r16 avait etabli et
mesure la regle d'allocation (12 criteres, 3 tailles de board, 8 BC) mais n'avait RIEN porte --
« Aucun emetteur ecrit ». Ce module est ce port.

L'ALLOCATEUR EST UNIQUE, ET C'EST UN COMPTEUR MONOTONE.
`IdunBattle.Entities.Components.MatchComponent$$NextId` est le SEUL producteur d'identifiant du
binaire (xrefs Ghidra : neuf sites d'appel, aucun autre) :

    NextId()        this.<+0x10> += 1 ; return this.<+0x10>       -- PRE-incrementation
    ReturnLastId()  this.<+0x10> -= 1
    .ctor()         this.<+0x10> = 1

⚠ `ReturnLastId` N'A QUE DEUX SITES, ET LES DEUX SONT DES TUILES
(`AddTileOperation$$Execute` et `$$CreateTile`). Il n'existe donc AUCUN recyclage d'identifiant
pendant le deroule : un effet retire, une unite morte, un summon disparu ne rendent jamais leur
id. Le compteur ne redescend jamais entre la fin du deploiement et la fin de la bataille --
c'est ce qui rend la suite des ids d'effet PREVISIBLE des lors qu'on connait l'ORDRE des
creations.

LA SEQUENCE D'AMORCAGE, lue dans `IdunBattle.Operations.SetupGameOperation$$Execute` puis
`IdunBattle.Operations.InitializeMatchOperation$$Execute` :

    Blueprints$$Match(matchEntityId = 1)      l'entite MATCH prend le LITTERAL 1 ; son
                                              `MatchComponent$$.ctor` pose `+0x10 = 1`
    InitializeMatchOperation$$Execute         `matchComponent.<+0x10> += 1`   -> compteur = 2
    AddPlayers / AddEnvironmentAbilities / AddTiles / AddMachinePlatform / AddPredefinedUnits...

⇒ le premier `NextId` rend **3**, et l'id **2 n'est jamais attribue**. Mesure #477-r16 : les
trois joueurs recoivent 3, 4, 5 sur les trois boards.

CE QUE CE MODULE NE FAIT PAS. Il ne DECIDE rien : ni quelles unites se deploient, ni quels
effets se creent, ni dans quel ordre. Il mirror le COMPTEUR et l'ORDRE DES SITES ; le nombre
d'appels lui est donne, exactement comme `GameSetup` recoit son roster. Pour l'effet, ce qui
reste hors de portee est nomme : la SELECTION (`#477-r21-r2`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


class MatchComponent:
    """`IdunBattle.Entities.Components.MatchComponent` -- son champ `+0x10` et ses deux
    accesseurs, mirror 1:1.

    Le champ porte le DERNIER id attribue, pas le prochain : `NextId` PRE-incremente."""

    __slots__ = ("last_id",)

    def __init__(self) -> None:
        # `MatchComponent$$.ctor` : `*(undefined4 *)(this + 0x10) = 1;`
        self.last_id = 1

    def next_id(self) -> int:
        """`MatchComponent$$NextId` : `this.<+0x10> += 1 ; return this.<+0x10>`."""
        self.last_id += 1
        return self.last_id

    def return_last_id(self) -> None:
        """`MatchComponent$$ReturnLastId` : `this.<+0x10> -= 1`.

        ⚠ DEUX SITES D'APPEL DANS TOUT LE BINAIRE, tous deux sur le chemin TUILE. Aucune autre
        operation ne rend son id -- un echec de creation d'unite ou de machine le BRULE."""
        self.last_id -= 1


def initialize_match(match: MatchComponent) -> None:
    """`IdunBattle.Operations.InitializeMatchOperation$$Execute` -- son dernier geste.

    Le decompile n'y appelle PAS `NextId` : il incremente le champ DIRECTEMENT
    (`*(int *)(matchComponent + 0x10) = *(int *)(matchComponent + 0x10) + 1;`). Le port garde
    cette distinction plutot que d'appeler `next_id()` et de jeter le resultat : la valeur
    rendue par `NextId` n'est utilisee par personne ici, et ce n'est pas une allocation."""
    match.last_id += 1


# --------------------------------------------------------------------------------------------
# Les NEUF sites d'appel de `NextId`, un par fonction native. Chacun est un mirror 1:1 : ils ne
# font rien d'autre que consommer le compteur au bon nombre de reprises.
# --------------------------------------------------------------------------------------------

def add_player(match: MatchComponent) -> int:
    """`IdunBattle.Operations.AddPlayerOperation$$Execute` -- un id par joueur."""
    return match.next_id()


def add_environment_ability(match: MatchComponent) -> int:
    """`IdunBattle.Operations.AddEnvironmentAbilityOperation$$Execute`.

    ⚠ DEUX sites `NextId` dans cette fonction, mais dans des branches EXCLUSIVES : elle teste le
    TYPE de la configuration (`EnhancementsEnvironmentAbilityConfiguration` =>
    `Blueprints$$EnhancementEnvironmentAbility`, sinon `Blueprints$$EnvironmentAbility`), et
    chaque branche alloue UNE fois. Le compte est donc `1` par configuration.
    `$$CreateEntity` porte la meme paire, et n'est pas appelee par `Execute`."""
    return match.next_id()


def add_tile(match: MatchComponent, *, factory_returned_entity: bool = True) -> Optional[int]:
    """`IdunBattle.Operations.AddTileOperation$$Execute` (et `$$CreateTile`, meme forme).

    ⚠ LE SEUL CHEMIN QUI ROLLBACK. L'id est alloue AVANT l'appel a la factory ; si celle-ci rend
    `null`, `ReturnLastId` le rend au compteur. `factory_returned_entity=False` mirror ce cas --
    il rend `None`, et le compteur est REVENU a sa valeur d'avant. Aucun autre `Add*Operation`
    ne fait cela."""
    entity_id = match.next_id()
    if not factory_returned_entity:
        match.return_last_id()
        return None
    return entity_id


def add_machine_of_war_platform(match: MatchComponent) -> int:
    """`IdunBattle.Operations.AddMachineOfWarPlatformOperation$$Execute` -- un id par plateforme.

    Le nombre de plateformes est EN DUR chez l'appelant, pas ici : le helper inline de
    `SetupGameOperation$$Execute` appelle `AddMachineOfWarPlatform` deux fois. Le foyer de ce
    litteral est `engine.streams.game_setup.PLATFORM_POSITIONS`."""
    return match.next_id()


@dataclass(frozen=True)
class UnitAllocation:
    """Ce qu'un seul `AddUnitOperation$$Execute` consomme : l'unite PUIS ses pieds."""

    entity_id: int
    foot_entity_ids: Tuple[int, ...]


def add_unit(match: MatchComponent, foot_count: int) -> UnitAllocation:
    """`IdunBattle.Operations.AddUnitOperation$$Execute` -- DEUX sites `NextId`, et le second est
    DANS UNE BOUCLE.

    Ce n'est PAS « deux entites par unite » : la fonction alloue l'unite, puis entre dans une
    boucle sur les tuiles occupees et alloue une `FootEntity` par tuile (`Blueprints$$UnitFoot`
    -> `UnitComponent$$AddFoot`). `IdunBattle.Entities.Enum.EntityType` porte d'ailleurs
    `UnitFoot` a cote d'`Unit`. Le pas vaut donc `1 + foot_count`, et il tombe a 2 seulement
    parce que les unites predefinies sont mono-tuile (`AddPredefinedUnits` passe une liste a UN
    element). La boucle multi-pieds est LUE, non confrontee -- residu `#477-r16-r2`.

    ⚠ AUCUN ROLLBACK ICI : si la factory rend `null`, `AddUnitOperation` sort sans appeler
    `ReturnLastId`, et les ids sont BRULES. Un emetteur qui supposerait « pas d'entite => pas
    d'id consomme » divergerait sur toute la suite du flux."""
    entity_id = match.next_id()
    feet = tuple(match.next_id() for _ in range(int(foot_count)))
    return UnitAllocation(entity_id=entity_id, foot_entity_ids=feet)


def add_machine(match: MatchComponent) -> int:
    """`IdunBattle.Operations.AddMachineOperation$$Execute` -- un id, AUCUN pied.

    `Blueprints$$Machine` ne cree pas de `UnitFoot` : c'est ce qui distingue une machine d'une
    unite dans le compteur."""
    return match.next_id()


def add_effect(match: MatchComponent) -> int:
    """`IdunBattle.Operations.AddEffectOperation$$Execute` -- l'UNIQUE site `NextId` du chemin
    EFFET, et le coeur de `#477-r21-r3`.

    UN EFFET COUTE EXACTEMENT UN ID. `Blueprints$$Effect(id)` construit une `Core.EffectEntity`
    et lui attache un seul `EffectComponent` : aucune sous-entite, donc aucun pas variable comme
    pour l'unite.

    ⚠ L'ALLOCATION EST CONDITIONNELLE, ET LA CONDITION N'EST PAS ICI. `Execute` sort AVANT toute
    allocation sur quatre chemins, tous LUS :

        owner == null                                       -> log, retour `null`
        <config d'effet>.<slot 0x28>(owner)                  -> retour `null`
        owner.IsUnit() && UnitExtensions$$HasFlag(owner, 6)  -> log, retour ; 6 = `UnitFlag.Dead`
        UpdateExistingEffect(...) == true                    -> l'effet EXISTANT est mis a jour

    et le quatrieme est le plus consequent : `AddEffectOperation$$UpdateExistingEffect` commence
    par `StaticBattleRules.Effect$$IsUpdatable(effectType)` puis balaie les effets DEJA PORTES
    par la cible en cherchant le meme `EffectType` (`effectComponent.<+0x58>`), la meme
    parente (`effectComponent.<+0x70>`) et une configuration dont le slot 5 est faux. Trouve =>
    aucune entite creee. Ces conditions dependent de l'ETAT, pas du flux : elles relevent de la
    SELECTION (`#477-r21-r2`). Ce module ne les evalue donc pas -- il est appele quand le natif
    appelle `NextId`, exactement comme les huit autres sites."""
    return match.next_id()


# --------------------------------------------------------------------------------------------
# La SEQUENCE de `SetupGameOperation$$Execute` -- ce qui fixe l'ANCRE des ids du deroule.
# --------------------------------------------------------------------------------------------

#: L'entite du MATCH : argument LITTERAL de `Blueprints$$Match` dans `SetupGameOperation$$Execute`.
#: Elle n'est PAS allouee par `NextId` -- c'est pourquoi le compteur peut valoir 1 a sa naissance
#: sans que le match ait « pris » un id au sens de l'allocateur.
MATCH_ENTITY_ID = 1


@dataclass(frozen=True)
class SetupAllocation:
    """Tous les identifiants que `SetupGameOperation$$Execute` consomme, dans son ordre."""

    players: Tuple[int, ...]
    environment_abilities: Tuple[int, ...]
    tiles: Tuple[int, ...]
    machine_of_war_platforms: Tuple[int, ...]
    units: Tuple[UnitAllocation, ...]
    machines: Tuple[int, ...]

    @property
    def first_tile_entity_id(self) -> Optional[int]:
        """`3 + P + E` de `#477-r16` -- rendu ici comme MESURE du port, pas comme formule."""
        return self.tiles[0] if self.tiles else None

    @property
    def first_unit_entity_id(self) -> Optional[int]:
        return self.units[0].entity_id if self.units else None


def allocate_setup_game(match: MatchComponent, *, player_count: int,
                        environment_ability_count: int, tile_count: int,
                        machine_of_war_platform_count: int,
                        unit_foot_counts: Sequence[int],
                        machine_count: int = 0) -> SetupAllocation:
    """Face ALLOCATION d'`IdunBattle.Operations.SetupGameOperation$$Execute`.

    L'ORDRE est celui du decompile, et c'est lui seul qui produit l'offset :

        InitializeMatch(matchEntityId = 1, ...)   -> compteur = 2 (cf. `initialize_match`)
        AddPlayers()                 SortedDictionary : ordre par CLE, derivable du BC
        AddEnvironmentAbilities()    List de `GetEnvironmentAbilities` (`#477-r16` § 3bis)
        AddTiles()                   for row in 0..Width-1 { for col in 0..Height-1 }
        SetupRoom()                  n'alloue RIEN (il itere un HashSet, sans effet sur les ids)
        AddMachinePlatform()         DEUX appels, positions 2 puis 1
        RevealHumanPlayerRoom()      n'alloue RIEN
        AddPredefinedUnits() / AddPredefinedMachines() / AddBossUnit()

    ⚠ `initialize_match` N'EST PAS APPELE ICI. La sequence commence apres lui : c'est
    `SetupGameOperation$$Execute` qui appelle `InitializeMatch` en premier, et le port garde les
    deux separes pour que l'amorcage soit visible au site d'appel plutot qu'enfoui.

    ⚠ `environment_ability_count` N'EST PAS ENTIEREMENT DANS LA BC. Deux tables STATIQUES du
    binaire y entrent (`StaticBattleRules.TriggeredAbility` `+0x38` pour les derivees,
    `StaticBattleRules.DamageTrait$$.cctor` pour les traits de degat), et trois des cinq termes
    passent par `SetupGameOperation$$IncludeEnvironmentAbility`, qui DEDUPLIQUE. La regle
    complete est etablie et confrontee par `#477-r16` (`probe_477r16_allocation_entites_ecs.py`,
    fonction `deriver_regle`) : ce module en recoit le RESULTAT, il ne le recalcule pas."""
    players = tuple(add_player(match) for _ in range(int(player_count)))
    environment = tuple(add_environment_ability(match)
                        for _ in range(int(environment_ability_count)))
    tiles = tuple(int(t) for t in (add_tile(match) for _ in range(int(tile_count)))
                  if t is not None)
    platforms = tuple(add_machine_of_war_platform(match)
                      for _ in range(int(machine_of_war_platform_count)))
    units = tuple(add_unit(match, foot_count) for foot_count in unit_foot_counts)
    machines = tuple(add_machine(match) for _ in range(int(machine_count)))
    return SetupAllocation(players=players, environment_abilities=environment, tiles=tiles,
                           machine_of_war_platforms=platforms, units=units, machines=machines)


def new_match_after_setup(*, player_count: int, environment_ability_count: int, tile_count: int,
                          machine_of_war_platform_count: int,
                          unit_foot_counts: Sequence[int],
                          machine_count: int = 0) -> Tuple[MatchComponent, SetupAllocation]:
    """Le montage complet : `MatchComponent` neuf, `InitializeMatch`, puis le deploiement.

    Rend le compteur DANS L'ETAT OU LE DEROULE LE PREND -- c'est-a-dire pret a servir l'ANCRE
    des identifiants d'effet : le premier `add_effect` rendra `match.last_id + 1`."""
    match = MatchComponent()
    initialize_match(match)
    return match, allocate_setup_game(
        match, player_count=player_count,
        environment_ability_count=environment_ability_count, tile_count=tile_count,
        machine_of_war_platform_count=machine_of_war_platform_count,
        unit_foot_counts=unit_foot_counts, machine_count=machine_count)
