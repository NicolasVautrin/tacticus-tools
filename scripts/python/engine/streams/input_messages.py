"""L'ANCRAGE du deroule : les groupes RACINE ouverts par `InputMessageProcessor`.

`IdunBattle.Messages.InputMessageProcessor` est la seule couche du chemin de replay qui
n'existait nulle part dans `engine/` (#477-r18). Elle est pourtant l'origine des **15** groupes
racines `System_*` / `User_*` du flux. Tout le reste du flux (`StartTurn`, `Damage`,
`Effect_Refresh`, ...) est ouvert par des Operations, deja portees.

⚠ « OUVERT PAR `InputMessageProcessor` » NE VEUT PAS DIRE « OUVERT PAR `Visit` », et le
distinguer est ce qui donne son ancrage au cran 2. Mesure du 2026-08-05 (#477-r19) :
`System_ProcessDeaths` et `System_ProcessRemovals` ne sont ouverts par AUCUNE surcharge de
`Visit`. Ils le sont par `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`, donc APRES
le message, dans la retombee de son traitement -- c'est exactement ce qui fonde
`PHASE_BARRIER_GROUPS` plus bas.

CE QUE CE MODULE EST -- ET N'EST PAS. Comme `game_setup.py`, seule la FACE STREAM est portee :
l'enveloppe, et l'ordre dans lequel elle appelle ce qui est deja emis. Rien de ce qui construit
l'etat (creation d'entites, composants, phases) n'est ici.

⚠ LES 37 SURCHARGES DE `Visit` NE SE LISENT PAS PAR NOM. `decompile_function` par nom rend un
corps VIDE, sans erreur, et la sortie se lit « non decompilable » (piege 1 de #477-r18). Chaque
mirror ci-dessous cite donc la surcharge par le TYPE de son parametre, lu dans
`data/symbols/<build>/frida/methods.tsv` -- c'est ce qui rend l'appariement verifiable.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from .dispatcher import StreamDispatcher
from .entity_id import NO_ENTITY
from .game_setup import UnitSetup, add_unit
from .group_type import GroupType
from .step_type import StepType

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


#: `sourceId` du groupe racine `System_ProcessRemovals`. MEME LECTURE que
#: `PLACE_UNIT_SOURCE_ID`, et meme expression dans le decompile : l'argument passe a `StartGroup`
#: est le PREMIER champ statique de `System.String`, c'est-a-dire `String.Empty` -- pas un slot
#: de litteral. La lambda `<VerifyDeaths>b__0` passe le MEME argument pour `System_ProcessDeaths`.
PROCESS_REMOVALS_SOURCE_ID = ""

#: LES GROUPES RACINES QUI NE PEUVENT PAS S'INTERCALER entre le `System_ProcessDeaths` et le
#: `System_ProcessRemovals` D'UN MEME `VerifyDeaths`. C'est la regle d'ANCRAGE de cette tranche,
#: et chaque membre y est pour une raison LUE, pas pour son nom :
#:
#:   * `StartTurn` / `EndTurn` -- ils sont produits par le bloc `if (isInternalPhase == 0)` de
#:     `IdunBattle.Messages.InputMessageProcessor$$RunPhase` (celui qui appelle `VerifyTurnEnd`
#:     et `VerifyDrafting`). Les DEUX `RunPhase` de `VerifyDeaths` passent `isInternalPhase:
#:     true` -- lu verbatim sur les deux call-sites -- donc ce bloc est court-circuite ;
#:   * les `System_*` / `User_*` restants -- ils sont ouverts par une surcharge de
#:     `IdunBattle.Messages.InputMessageProcessor$$Visit`, c'est-a-dire par un AUTRE MESSAGE
#:     D'ENTREE. `VerifyDeaths` s'execute DANS le traitement du message courant (la pile
#:     `InputMessageProcessor$$Apply` -> `Visit` -> ... -> `VerifyDeaths`), qui n'a pas rendu la
#:     main : aucun autre message ne peut commencer. Le producteur de `User_PlaceUnit` est LU
#:     (#477-r18-r5) ; les autres sont HERITES du recensement de #477-r18 (« les 15 `System_*` /
#:     `User_*` ont leur producteur lu »), pas relus ici -- d'ou le controle ci-dessous.
#:
#: ⚠ CE N'EST PAS UNE LISTE BLANCHE DE CE QUI PEUT S'INTERCALER, et c'est voulu : une telle
#: liste ne pourrait pas montrer le groupe qu'elle a oublie. Le probe #477-r19 IMPRIME donc
#: chaque groupe qu'il traverse entre le `System_ProcessDeaths` et le `System_ProcessRemovals`
#: predit : un intrus s'y verrait, et une barriere de trop ferait rougir la prediction.
#:
#: ⚠ `System_ProcessDeaths` et `System_ProcessRemovals` N'EN SONT PAS : ils sont ouverts par
#: `VerifyDeaths` elle-meme, qui est RE-ENTRANTE (`RunPhase` la rappelle apres l'action). Une
#: rafale de morts imbriquees s'intercale donc legitimement.
#: LES DEUX ANCRES DE `VerifyDeaths` -- le groupe racine apres lequel elle est rappelee, donc
#: apres lequel un `System_ProcessRemovals` PEUT apparaitre. `VerifyDeaths` a TROIS call-sites
#: (`RunPhase` x2, `VerifyTurnEnd` x1), qui se ramenent a deux formes VISIBLES dans le flux :
#:
#:   (A) `IdunBattle.Messages.InputMessageProcessor$$RunPhase`, juste apres `action.Invoke()` --
#:       donc apres la CLOTURE du groupe que la phase ouvre. La phase qui en ouvre un et qui
#:       precede structurellement les retraits est celle des morts : `System_ProcessDeaths` ;
#:   (B) `IdunBattle.Messages.InputMessageProcessor$$VerifyTurnEnd` -- lue verbatim :
#:       `processor.<0x21>() ; processor.<0x20>(0, isManualTurnEnd) ;
#:        ProcessPendingTriggeredAbilities() ; VerifyDeaths() ; ProcessDamageEvents() ; ...`.
#:       Le `<0x20>` est le flux de tour, qui ecrit `EndTurn` PUIS `StartTurn` : l'ancre tombe
#:       donc apres `StartTurn`. Le bloc `if (isInternalPhase == 0)` de `RunPhase` est ce MEME
#:       corps, inline -- meme suite de slots, meme ordre.
#:
#: ⚠ CE N'EST PAS « APRES CHAQUE MORT », ET C'EST MESURE. Le decompile de `VerifyDeaths` ne
#: garde par `deaths.Count > 0` que le `RunPhase` des MORTS : le bloc des retraits, lui, suit
#: dans TOUS les cas. Un `System_ProcessRemovals` sans aucun `System_ProcessDeaths` en amont
#: existe donc -- et il a ete observe des le second board (MC1_67, 3e occurrence, apres un
#: `StartTurn`). Une regle calee sur le seul premier board l'aurait rate.
#:
#: ⚠ UNE TROISIEME FORME EST POSSIBLE ET N'EST PAS RETENUE : la branche `RunPhase` ci-dessus
#: vaut pour N'IMPORTE QUELLE phase, pas seulement celle des morts -- donc apres tout groupe
#: racine ouvert par un `RunPhase`. La retenir rendrait l'ensemble des positions admissibles
#: presque total, donc le controle vide. Le probe #477-r19 IMPRIME toute occurrence tombant
#: hors des ancres (A)/(B) : c'est la condition de retournement, et elle est armee.
VERIFY_DEATHS_ANCHOR_GROUPS = frozenset((
    GroupType.System_ProcessDeaths,
    GroupType.StartTurn,
))

PHASE_BARRIER_GROUPS = frozenset((
    GroupType.System_GameSetup,
    GroupType.System_StartMatch,
    GroupType.System_UnitDrafting,
    GroupType.System_RerollDraftOption,
    GroupType.System_StartTurn,
    GroupType.System_PickUnit,
    GroupType.User_MoveUnit,
    GroupType.User_UseAbility,
    GroupType.User_PlaceUnit,
    GroupType.User_RemoveUnit,
    GroupType.User_EndTurn,
    GroupType.User_Surrender,
    GroupType.User_CheatAmmo,
    GroupType.User_Effect_Manipulation,
    GroupType.StartTurn,
    GroupType.EndTurn,
))


def verify_removed_units(events: StreamDispatcher, match_entity_id: int,
                         removed_unit_ids: Sequence[int]) -> None:
    """Face stream d'`IdunBattle.Messages.InputMessageProcessor$$VerifyRemovedUnits`.

    ⚠ CETTE FONCTION N'A AUCUN APPELANT DANS LE BINAIRE -- son corps est INLINE dans
    `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`, et c'est ce qui donne son
    ANCRAGE a la tranche. Mesure : le `Il2CppClass*` du `<>c__DisplayClass50_0` et le pointeur
    de sa lambda sont references par EXACTEMENT DEUX fonctions -- `VerifyDeaths` (l'inline) et
    `VerifyRemovedUnits` (l'original, que personne n'appelle : ses deux seules xrefs sont des
    entrees DATA de table de methodes). Il n'existe donc AUCUN autre site d'emission de
    `GroupType.System_ProcessRemovals`.

    LA STRUCTURE DE `VerifyDeaths`, lue verbatim -- c'est elle qui place le groupe :

        var phases = state.<GetCurrentRunningPhaseCount>();
        var deaths = state.<les morts>;
        if (state.<HasRunningPhase-like>() && phases > 1) return;
        if (deaths != null) {
            if (deaths.Count > 0) {
                RunPhase(PhaseType.<0xc>, <VerifyDeaths>b__0, isInternalPhase: true, false);
                processor.<slot 0x8e>();
            }
            if (phases > 1) return;
            // ---------- INLINE DE VerifyRemovedUnits ----------
            var queue = state.<les acteurs retires>;             // `MatchState$$AddRemovedActor`
            if (queue != null) {
                if (queue.Count < 1) return;
                RunPhase(PhaseType.<0xd>, <VerifyRemovedUnits>b__0, isInternalPhase: true, false);
            }
        }

    ⚠ LE `0xd` EST UN `IdunBattle.Core.PhaseType`, PAS UN `GroupType` -- meme piege qu'au cran 1
    (`case-477r18r5` § 1). Le `GroupType` est le `6` que la LAMBDA passe a `StartGroup`.

    LA LAMBDA, lue verbatim (`InputMessageProcessor.u003Cu003Ec__DisplayClass50_0$$u003CVerifyRemovedUnitsu003Eb__0`) :

        var list = new List<int>(queue);
        queue.Clear();
        Events.StartGroup(GroupType.System_ProcessRemovals /*6*/, ((IEntity)state).Id,
                          String.Empty, default(BEntityId?));
        foreach (var id in list) {
            var entity = state.<Get(id)>;
            if (entity != null) processor.RemoveUnit(entity, removeEffects: true, keepActive);
        }
        Events.FinishGroup();

    ⚠ `entityId` N'EST PAS UN LITTERAL, ET C'EST CE QUI LE REND VERIFIABLE. Le decompile caste
    le state en `IEntity` et appelle son accesseur d'identifiant -- l'expression est
    CARACTERE POUR CARACTERE la meme que celle de la lambda `<VerifyDeaths>b__0` qui ouvre
    `System_ProcessDeaths`. Les deux groupes portent donc TOUJOURS la meme entite sur un meme
    flux : c'est un recoupement mesurable, que le probe exige. Sur nos runners elle vaut `1`,
    l'entite MATCH que `IdunBattle.Operations.SetupGameOperation$$Execute` passe en dur
    (`game_setup.MATCH_ENTITY_ID`) -- d'ou le parametre plutot qu'une constante recopiee.

    LE GROUPE EST VIDE, ET LE PORT N'INVENTE PAS SON CONTENU. Ce que la boucle PEUT emettre est
    lu dans `IdunBattle.Operations.RemoveUnitOperation$$Execute` : une `Action=RemoveUnit`
    (`StepType.RemoveUnit`) portant `TagKey.Unit_IsDying` et `TagKey.Unit_WasOverkilled`. Elle
    ne l'emet QUE si l'unite franchit trois gardes, toutes en tete de l'operation :
    `unit != null`, `IdunBattle.Entities.EntityExtensions$$IsUnit(unit)`, et
    `!IdunBattle.Entities.UnitExtensions$$HasFlag(unit, 0x1a)` -- ce dernier flag etant pose par
    l'operation ELLE-MEME, plus bas, sur toute unite qu'elle retire. S'y ajoute le
    `if (entity != null)` de la lambda. Dans TOUT le regime mesure le groupe ressort vide ;
    le port emet donc l'enveloppe seule, et le contenu reste un RESIDU (#477-r19-r1) plutot
    qu'un port speculatif qu'aucun montage ne saurait exercer.

    `removed_unit_ids` gouverne l'OUVERTURE (`queue.Count < 1` => rien du tout), pas le
    contenu : les deux grandeurs sont DISTINCTES dans le natif, et c'est precisement leur
    ecart qui produit un groupe vide."""
    if len(removed_unit_ids) < 1:
        return
    events.start_group(GroupType.System_ProcessRemovals, match_entity_id,
                       PROCESS_REMOVALS_SOURCE_ID, None)
    # `foreach (id in list) { if (state.Get(id) != null) processor.RemoveUnit(...); }` -- le
    # contenu n'est PAS porte (cf. docstring, residu #477-r19-r1). Le groupe reste VIDE, ce qui
    # est ce que le natif produit dans tout le regime confronte.
    events.finish_group()


#: `sourceId` du groupe racine `System_StartMatch`. TROISIEME occurrence de la MEME lecture que
#: `PLACE_UNIT_SOURCE_ID` et `PROCESS_REMOVALS_SOURCE_ID` : l'argument passe a `StartGroup` est le
#: PREMIER champ statique de `System.String`, c'est-a-dire `String.Empty` -- pas un slot de
#: litteral, et pas `null`. `""` et `null` rendent le meme `Source=` vide apres `String.Format` :
#: la distinction n'est pas observable dans le flux, elle est LUE.
START_MATCH_SOURCE_ID = ""


def start_match(events: StreamDispatcher, match_entity_id: int) -> None:
    """Face stream d'`IdunBattle.Operations.StartMatchOperation$$Execute` -- SA PREMIERE
    EMISSION SEULEMENT.

    ⚠ CETTE FONCTION NE PORTE PAS L'OPERATION, ET C'EST MESURE. `StartMatchOperation$$Execute`
    produit 477 lignes sur le flux temoin ; ce qui est porte ici en fait DEUX (l'`Action=` et sa
    place). Ce qui reste dehors est ENUMERE dans la docstring de `visit_start_battle_message` et
    chiffre par `probe_477r20_start_match.py` -- pas sous-entendu.

    L'EMISSION PORTEE, lue verbatim dans le decompile :

        processor.<slot 0xd>();                       // pas d'emission de flux
        var tags = new Dictionary<TagKey,int>();      // AUCUN `Add` -- le dictionnaire est VIDE
        Events.Action(StepType.StartMatch /*1*/, 1, tags);

    ⚠ LE DICTIONNAIRE EST VIDE, ET C'EST LU, PAS DEDUIT DU FLUX : le ctor du dictionnaire est
    suivi directement de l'appel d'action, sans aucun `Dictionary$$Add` entre les deux. Le flux
    le confirme (`Action=StartMatch Entity=1` sans aucun `Tag=`), mais la lecture tranche.

    ⚠ L'ENTITE EST UN LITTERAL DANS LE DECOMPILE (`1`), la ou l'OUVERTURE du groupe la lit par
    `IdunBattle.Entities.StateExtensions$$GetMatchEntity(state)` puis l'accesseur d'identifiant
    d'`IdunBattle.Core.IEntity`. Les deux voies sont DISTINCTES dans le natif et valent 1 sur nos
    runners (meme entite MATCH que `game_setup.MATCH_ENTITY_ID`, que
    `IdunBattle.Operations.SetupGameOperation$$Execute` passe elle aussi en dur). Le port prend
    donc un PARAMETRE plutot que de recopier la constante, et le probe EXIGE que les deux voies
    coincident sur le flux -- c'est un recoupement mesurable, pas une supposition."""
    events.action(StepType.StartMatch, match_entity_id, {})


def visit_start_battle_message(events: StreamDispatcher, match_entity_id: int,
                               corps: Optional[Callable[[], None]] = None) -> None:
    """Face stream d'`IdunBattle.Messages.InputMessageProcessor$$Visit(message:
    IdunBattle.Messages.StartBattleMessage)`.

    ⚠ « OUVERT PAR `InputMessageProcessor` » NE DIT PAS PAR QUOI. Au cran precedent les deux
    groupes etaient ouverts par `VerifyDeaths`, pas par `Visit` : la question se re-pose a chaque
    tranche. Ici la surcharge de `Visit` EST la porte, mais elle n'ouvre RIEN elle-meme --

        this.<+0x28> = <le composant de match>;      // memorise pour la garde de `RunPhase`
        var action = new Action(this, <Visit>b__18_0);
        RunPhase(PhaseType.StartBattle /*0*/, action, isInternalPhase: true,
                 isManualTurnEnd: false);

    -- et c'est la LAMBDA D'INSTANCE `InputMessageProcessor$$u003CVisitu003Eb__18_0` qui emet, en
    exactement trois choses :

        Events.StartGroup(GroupType.System_StartMatch /*4*/,
                          StateExtensions.GetMatchEntity(state).<Id>,
                          String.Empty, default(BEntityId?));
        processor.<slot 0x12>();                     // -> `Core.Services.OperationProcessor$$StartMatch`
        Events.FinishGroup();

    ⚠ LA LAMBDA N'EST PAS UN `<>c__DisplayClass`, ET C'EST CE QUI PERMET DE L'APPARIER. Elle ne
    capture rien : son `this` est l'`InputMessageProcessor` lui-meme (`+0x10` = l'etat, `+0x18` =
    le processeur d'operations, `+0x20` = le dispatcher -- les champs poses par
    `InputMessageProcessor$$Initialize`). Le binaire n'en porte que TROIS de cette forme
    (`<Visit>b__18_0`, `<Visit>b__20_0`, `<Visit>b__42_0`) ; la seconde ouvre
    `GroupType.System_StartTurn` et est referencee par la seule `Visit(StartTurnMessage)`, la
    troisieme n'ouvre aucun groupe. Le pointeur de methode que `Visit(StartBattleMessage)` passe
    au ctor de delegue n'est lu par AUCUNE autre fonction du binaire.

    ⚠ LE `0` DE `RunPhase` EST UN `IdunBattle.Core.PhaseType`, PAS UN `GroupType` -- meme piege
    qu'aux crans 1 et 2 (`case-477r18r5` § 1, `case-477r19` § 1), ou c'etaient un `4` puis un
    `0xd`. Le `GroupType` est le `4` que la LAMBDA passe a `StartGroup`. Le NOM tranche, et il
    est lisible : `data/symbols/<build>/frida/enums.tsv` donne `IdunBattle.Core.PhaseType` =
    `0=StartBattle, ..., 4=AddUnit, ..., 12=ProcessDeaths, 13=ProcessRemovals`. Les trois crans
    concordent donc, et cette lecture CONFIRME au passage `case-477r19` § 6 : la phase `0xd` est
    bien celle des RETRAITS, pas celle du revive.

    ⚠ `isInternalPhase: true` EST LU, et il a une consequence VISIBLE : le bloc
    `if (isInternalPhase == 0)` d'`InputMessageProcessor$$RunPhase` -- celui qui appelle
    `VerifyAutomaticTurnEnd` puis `VerifyDrafting` -- est court-circuite. Ce qui suit malgre tout
    l'invocation (`VerifyDeaths`, `ProcessDamageEvents`,
    `ProcessPendingTriggeredAbilities`) s'execute APRES le `FinishGroup`, donc HORS de ce groupe.
    Le `Action=PrepareTurn` et le `Group=StartTurn` que le flux montre DEDANS ne viennent donc pas
    de la, mais du dernier appel de `StartMatchOperation$$Execute` lui-meme.

    LE SLOT `0x12`, ET COMMENT IL EST ETABLI. Les methodes d'une INTERFACE n'ont aucun corps, donc
    aucune ligne dans `data/symbols/<build>/frida/methods.tsv` (indexee par adresse) : l'ordre des
    slots de `Core.Services.IOperationProcessor` ne se LIT nulle part hors du metadata. L'ordre du
    dump de la CLASSE ne le donne pas non plus -- verifie, il n'existe aucun decalage constant
    (`ContinueTurnPhase` est au slot `0x16` pour la position 26, `VerifyAutomaticTurnEnd` au slot
    `0x20` pour la position 134). L'attribution est donc etablie par RECOUPEMENT, et il est
    ferme : la lambda appelle UN slot SANS ARGUMENT ; `Core.Services.OperationProcessor$$StartMatch`
    est sans argument et delegue a `IdunBattle.Operations.StartMatchOperation$$Execute` ; cette
    operation est le seul producteur de `StepType.StartMatch` du binaire ; et le flux montre
    `Action=StartMatch` comme PREMIERE ligne du groupe. Aucun autre call-site du binaire n'appelle
    ce slot sur ce `Il2CppClass*`.

    CE QUE LE PORT N'EMET PAS -- ENUMERE, PAS SOUS-ENTENDU. `StartMatchOperation$$Execute` est,
    apres `User_UseAbility`, le plus gros groupe du deroule : 477 lignes sur le flux temoin, dont
    475 que ce module ne produit pas. Elles se ventilent en TROIS blocs, tous mesures par
    `probe_477r20_start_match.py` et aucun porte cote flux aujourd'hui :

      1. l'ARBRE D'ACTIVATION des effets permanents -- `Group=Ability_Power` et
         `Group=Effect_Refresh` imbriques, avec leurs `Action=ActivateEffect` / `ReceiveEffect` /
         `ChangeStats` / `LoseEffect`. Il sort de DEUX appels au meme slot `0x51` de
         `IOperationProcessor`, a cinq arguments, dont le decompile donne les litteraux :
         `EvaluateAbilities(GetMatchEntity(state), null, null, EventTriggerType.MatchInit /*0x19*/,
         null)` puis le meme avec `EventTriggerType.MatchStart /*0x1a*/`. Les deux ordinaux sont
         NOMMES par `engine/dsl/event_trigger_type.py` (`MatchInit = 25`, `MatchStart = 26`) --
         c'est ce qui identifie le bloc, pas sa forme dans le flux ;
      2. `Action=PrepareTurn` et le `Group=StartTurn` COMPLET, qui sortent du dernier appel de
         l'operation -- `processor.<slot 0x16>(TurnStage.Start /*3*/, false, true)`, c'est-a-dire
         `ContinueTurnPhase` (meme slot, memes trois arguments, que la lambda `<Visit>b__20_0` de
         `Visit(StartTurnMessage)`) ;
      3. le groupe `RarityCapTransform` (`StepType.PlayerInitialRarity`), emis seulement quand le
         joueur humain porte une rarete initiale (`Nullable.HasValue && Value > 0`) -- ABSENT du
         flux temoin. Son unique tag est la cle `0xd4`, que `TagKey` NOMME `Rarity` : le nom
         recoupe la lecture du fragment.

    `corps` rend ce trou EXPRIMABLE plutot que silencieux : un appelant qui saurait produire l'un
    de ces blocs le passe ici, et l'enveloppe reste inchangee. `None` = le port n'emet que ce
    qu'il a lu."""
    events.start_group(GroupType.System_StartMatch, match_entity_id,
                       START_MATCH_SOURCE_ID, None)
    start_match(events, match_entity_id)
    if corps is not None:
        corps()
    events.finish_group()
