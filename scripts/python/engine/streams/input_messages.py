"""L'ANCRAGE du deroule : les groupes RACINE ouverts par `InputMessageProcessor`.

`IdunBattle.Messages.InputMessageProcessor` est la seule couche du chemin de replay qui
n'existait nulle part dans `engine/` (#477-r18). Elle est pourtant l'origine des **15** groupes
racines `System_*` / `User_*` du flux : chacun est ouvert par une surcharge de
`IdunBattle.Messages.InputMessageProcessor$$Visit`, une par type de message d'entree. Tout le
reste du flux (`StartTurn`, `Damage`, `Effect_Refresh`, ...) est ouvert par des Operations, deja
portees.

CE QUE CE MODULE EST -- ET N'EST PAS. Comme `game_setup.py`, seule la FACE STREAM est portee :
l'enveloppe, et l'ordre dans lequel elle appelle ce qui est deja emis. Rien de ce qui construit
l'etat (creation d'entites, composants, phases) n'est ici.

⚠ LES 37 SURCHARGES DE `Visit` NE SE LISENT PAS PAR NOM. `decompile_function` par nom rend un
corps VIDE, sans erreur, et la sortie se lit « non decompilable » (piege 1 de #477-r18). Chaque
mirror ci-dessous cite donc la surcharge par le TYPE de son parametre, lu dans
`data/symbols/<build>/frida/methods.tsv` -- c'est ce qui rend l'appariement verifiable.
"""
from __future__ import annotations

from .dispatcher import StreamDispatcher
from .entity_id import NO_ENTITY
from .game_setup import UnitSetup, add_unit
from .group_type import GroupType

#: `sourceId` du groupe racine `User_PlaceUnit`. Ce n'est PAS un slot de litteral (contrairement
#: a celui d'`AddUnitOperation$$Execute`, resolu par #477-r15-r1) : le decompile lit le PREMIER
#: champ statique de `System.String`, c'est-a-dire `String.Empty`. Le meme motif se relit dans
#: `System.Security.NamedPermissionSet$$set_Name`, qui compare a `String.Empty` par
#: `System.String$$op_Equality`. `""` et `null` rendent le meme `Source=` vide apres
#: `String.Format` -- la distinction n'est pas observable dans le flux, elle est LUE.
PLACE_UNIT_SOURCE_ID = ""


def visit_add_unit_message(events: StreamDispatcher, unit: UnitSetup,
                           use_group_for_add_unit: bool = True) -> None:
    """Face stream d'`IdunBattle.Messages.InputMessageProcessor$$Visit(message:
    IdunBattle.Messages.AddUnitMessage)`.

    Cette surcharge ne fait qu'assembler un `<>c__DisplayClass9_0` (l'etat capture : le
    processeur, le message, le joueur resolu par
    `IdunBattle.Entities.StateExtensions$$GetPlayer`, son id d'entite, et la liste des tuiles
    lues dans la table de la grille) puis appeler la fonction locale
    `IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass9_0$$u003CVisitu003Eg__AddUnit|0`
    -- soit directement, soit a travers `InputMessageProcessor$$RunPhase` selon un drapeau du
    message. LES DEUX BRANCHES APPELLENT LA MEME FONCTION LOCALE : l'enveloppe emise est
    identique, `RunPhase` n'ajoutant que des etapes APRES (`VerifyDeaths`, `ProcessDamageEvents`,
    `ProcessPendingTriggeredAbilities`), qui produisent leurs PROPRES groupes racines.

    LA FONCTION LOCALE, lue verbatim (elle n'emet QUE ces trois choses) :

        Events.StartGroup(GroupType.User_PlaceUnit /*0xd*/, 0 /*NO_ENTITY*/,
                          String.Empty, default(BEntityId?));
        processor.AddUnit(unitId, unitFeetTileIds, playerId, spawnSource, options);
        Events.FinishGroup();

    L'appel du milieu est le slot 5 de `Core.Services.IOperationProcessor`, dont
    l'implementation `Core.Services.OperationProcessor$$AddUnit(unitId, unitFeetTileIds,
    playerId, spawnSource, options)` delegue a `IdunBattle.Operations.AddUnitOperation$$Execute`
    -- exactement le `Group=AddUnit` que `game_setup.add_unit` emet deja pour le deploiement.
    Le contenu de la tranche est donc DEJA PORTE ; ce module n'apporte que l'enveloppe.

    ⚠ `spawnSource` EST UN CHAMP DU MESSAGE, PAS UNE CONSTANTE. Le decompile le lit a
    `AddUnitMessage+0x28` et le passe tel quel ; `SpawnSource.Deployment` (5) est ce que NOTRE
    montage envoie, pas ce que le natif impose. Le port le recoit donc par `UnitSetup.source`,
    comme pour le deploiement (`SpawnSource.InitialOperations`).

    ⚠ `entityId` VAUT `NO_ENTITY` ET C'EST STRUCTUREL : le groupe est ouvert AVANT que l'unite
    existe -- son entite est allouee par l'operation qu'il enveloppe. Un port qui y mettrait
    l'entite de l'unite serait faux sur toutes les lignes d'ouverture."""
    events.start_group(GroupType.User_PlaceUnit, NO_ENTITY, PLACE_UNIT_SOURCE_ID, None)
    add_unit(events, unit, use_group=use_group_for_add_unit)
    events.finish_group()
