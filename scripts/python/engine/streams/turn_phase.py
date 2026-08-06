"""La face STREAM du TOUR -- `Action=PrepareTurn` et `Group=StartTurn`.

C'est le BLOC 2 du contenu de `System_StartMatch` (#477-r22), le dernier des trois que
`case-477r20` § 1 avait nommes. Il sort du DERNIER appel de
`IdunBattle.Operations.StartMatchOperation$$Execute` :

    processor.<slot 0x16>(TurnStage.Start /*3*/, forceEndTurn: false, isManual: true);
                                     -> `Core.Services.OperationProcessor$$ContinueTurnPhase`
                                     -> `IdunBattle.Operations.ContinueTurnPhaseOperation$$Execute`

⚠ CE MODULE SE REUTILISE HORS DE `System_StartMatch`, ET C'EST TOUT SON INTERET. Le
`Group=StartTurn` n'a qu'UN SEUL producteur dans le binaire --
`IdunBattle.Operations.StartTurnOperation$$Execute` -- et `ContinueTurnPhase` est atteint par le
MEME slot avec les MEMES trois arguments depuis la lambda
`IdunBattle.Messages.InputMessageProcessor$$u003CVisitu003Eb__20_0` de `Visit(StartTurnMessage)`.
Ce qui est porte ici vaut donc pour TOUTES les occurrences du flux, pas seulement celle qui est
imbriquee dans `System_StartMatch`.

LA CHAINE, lue de bout en bout
------------------------------

    ContinueTurnPhaseOperation$$Execute(requestedTurnStage, forceEndTurn, isManual)
        turn = StateExtensions.GetMatchTurn(state);
        if (requestedTurnStage.HasValue) turn.<+0x14> = requestedTurnStage.Value;
        while (true) {
            var next = TurnComponent.GetNextTurnStage(turn);      // Nullable<TurnStage>
            if (!next.HasValue) return;
            if (StateExtensions.GetMatch(state).<+0x24> == 2) return;      // match TERMINE
            if (!HandleNextTurn(next.Value, forceEndTurn, ref isManual)) return;
        }

    TurnComponent$$GetNextTurnStage(turn)
        if (turn.<+0x14> != turn.<+0x10>)
            return new Nullable<TurnStage>(EnumExt.NextValueOrFirst(turn.<+0x10>));
        return default(Nullable<TurnStage>);

    ContinueTurnPhaseOperation$$ExecuteStage(nextTurnStage, forceEndTurn)
        turn.<+0x10> = nextTurnStage;                     // le stage COURANT avance ICI
        switch (nextTurnStage) {
          case 0: processor.<slot 0x17>();                // -> ChangeTurnOperation$$Execute
          case 1: processor.<slot 0x18>();                // -> PrepareTurnOperation$$Execute
          case 2: processor.<slot 0x19>();                // -> non identifie (drafting)
          case 3: processor.<slot 0x1c>();                // -> StartTurnOperation$$Execute
          case 4: processor.<slot 0x1d>(!forceEndTurn);   // -> EndTurnOperation$$Execute
          default: return;                                // rien
        }

⚠ L'ATTRIBUTION SLOT -> METHODE CI-DESSUS EST CONTESTEE, ET CE PORT N'EN DEPEND PAS.
`#477-r24-r1` a mesure sur `Core.Services.IOperationProcessor` un decalage slot->classe **local**
de 12 (trois ancrages concordants dans la zone 96-99), **incompatible** avec la lecture de
`case-477r20` que ce module reprend (`ContinueTurnPhase` au slot `0x16` pour la position 26). Une
des deux lectures est fausse et rien ne dit laquelle : les methodes d'une INTERFACE n'ont aucun
corps, donc aucune ligne dans `frida/methods.tsv`, et l'ordre des slots ne se lit nulle part hors
du metadata. Les numeros de slot ci-dessous sont donc cites comme REPERES DE CALL-SITE, jamais
comme une attribution etablie.
CE QUI, LUI, EST ETABLI, ET QUI SUFFIT A CE PORT : les DEUX operations sont identifiees par leur
EMISSION, pas par un mapping de slot -- `PrepareTurnOperation$$Execute` est le seul producteur de
`StepType.PrepareTurn` du binaire, `StartTurnOperation$$Execute` le seul de `GroupType.StartTurn`,
et le flux les montre exactement la ou le `switch` les predit (29 / 29 couples a l'egalite brute,
#477-r22). Si `#477-r24-r1` tranche un jour contre `case-477r20`, ce sont les COMMENTAIRES de slot
qu'il faudra corriger, pas le code.

⚠ LES DEUX CHAMPS `+0x10` / `+0x14` SONT LUS PAR LEUR OFFSET, PAS PAR LEUR NOM -- et c'est
obligatoire. Leurs deux setters sont des corps TRIVIAUX (`mov [rcx+off], edx ; ret`) qu'IL2CPP
DEDUPLIQUE : Ghidra les nomme `VoxelBusters.CoreLibrary.NativePlugins.DateComponents$$set_Year`
(ecrit `+0x14`) et `CenterSpace.Free.MersenneTwister$$set_Count` (ecrit `+0x10`). Prendre ces
noms pour argent comptant ferait lire « l'annee » et « un compteur de Mersenne » la ou le jeu
ecrit le stage DEMANDE et le stage COURANT. C'est le pendant exact de l'avertissement du
CLAUDE.md sur l'ABSENCE dans les tables : ici c'est une PRESENCE trompeuse.

⚠ `SetCurrentPlayer` DONNE LE SENS DE `TurnComponent+0x18`, ET C'EST CE QUI ATTRIBUE LE TAG.
`IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer` ecrit, dans cet ordre :
`this.<+0x24> = nextPlayerId` puis `this.<+0x18> = <l'ancien CurrentPlayerId>`. Le champ `+0x18`
que `PrepareTurnOperation` et `StartTurnOperation` lisent est donc le joueur PRECEDENT -- ce que
`TagKey.Match_PreviousPlayerId` nomme. Le nom du tag et la lecture du setter concordent : deux
canaux natifs distincts.

CE QUE CE MODULE EST -- ET N'EST PAS
------------------------------------
Comme `game_setup`, `input_messages` et `refresh_effects`, seule la FACE STREAM est portee.
`StartTurnOperation$$Execute` fait BEAUCOUP plus que ses trois emissions : elle remet a zero les
statistiques de tour de chaque unite (`ActorStatisticsComponent$$Reset*`), leurs drapeaux
(`UnitFlagsComponent$$RemoveTurnFlags`), les machines (`$$ResetMachine`), incremente les
compteurs de tour et debloque le drafting. RIEN de cela n'est ici : ce sont des mutations d'etat
ECS, aucune n'ecrit dans le flux (aucun appel a `IdunBattle.Streams.StreamDispatcher` entre
elles -- verifie sur le decompile entier).

Ne sont PAS portees non plus, et elles sont NOMMEES :

  * les gardes d'`IdunBattle.Operations.ContinueTurnPhaseOperation$$HandleNextTurn`, qui peuvent
    ARRETER la boucle avant `Start` : le match deja termine (`match.<+0x24> == 2`), et surtout
    `if (turn.<+0x10> == TurnStage.Draft && DraftingComponent.get_IsPendingDraftingDecision(...))`
    -- qui rend `false` sans rien emettre quand `forceEndTurn` est faux. Un montage avec drafting
    en attente n'aurait donc PAS de `Group=StartTurn` ; le port ne le simule pas, il l'ecrit ;
  * la branche `nextTurnStage == TurnStage.Prepare` de la meme fonction, qui n'appelle
    `ExecuteStage` que si l'une des quatre conditions LUES est vraie (joueur precedent dans un
    etat autre que 3/0, un drapeau statique, `isManual`, ou `forceEndTurn`) -- sinon elle poste un
    message et rend `false`. `StartMatchOperation` passe `isManual: true` EN DUR, ce qui la rend
    vraie : c'est ce littéral qui garantit que `Action=PrepareTurn` est emise ;
  * le CONTENU du `Group=StartTurn` : le `RefreshEffects` du slot `0x2f` et les CINQ
    `EvaluateAbilities(TurnStart_*)` du slot `0x4d`. Ils passent par `corps`.

LE SLOT `0x21`, LUI, N'EST PLUS DANS CETTE LISTE (#477-r22-r1). Il est RESOLU --
`Core.Services.IOperationProcessor` slot 33, `VerifyUnitsTurnFinished`, ARITE 0, lu dans
`data/symbols/<build>/metadata/interface_slots.tsv` -- et sa face stream est portee par
`engine/streams/verify_turn_finished.py`. `start_turn` le recoit par le parametre `verifier`,
SEPARE de `corps` pour que l'ordre « corps puis verification » reste une decision du PORT.
"""
from __future__ import annotations

from typing import Callable, Dict, Mapping, Optional

from ..entities.turn_stage import TurnStage, next_value_or_first
from .dispatcher import StreamDispatcher
from .group_type import GroupType
from .step_type import StepType
from .tag_key import TagKey


def prepare_turn(events: StreamDispatcher, match_entity_id: int, current_player_id: int,
                 previous_player_id: int, turns_started_by_current_player: int) -> None:
    """`IdunBattle.Operations.PrepareTurnOperation$$Execute` -- sa SEULE emission.

    LE DECOMPILE, litteral pour litteral :

        var turn = <le TurnComponent de l'entite de match>;
        if (turn != null) {
            var tags = new Dictionary<TagKey,int>();
            tags.Add(TagKey.Match_CurrentPlayerId /*0x9d*/,
                     TurnComponent.get_CurrentPlayerId(turn));
            tags.Add(TagKey.Match_PreviousPlayerId /*0x9e*/, turn.<+0x18>);
            tags.Add(TagKey.Match_AmountOfTurnsStartedByCurrentPlayer /*0x9f*/,
                     TurnComponent.GetAmountOfTurnsStartedByCurrentPlayer(turn));
            Events.Action(StepType.PrepareTurn /*0x26*/,
                          StateExtensions.GetMatchEntity(state).<Id>, tags);
        }

    ⚠ L'ACTION EST A PROFONDEUR 0 QUAND AUCUN GROUPE N'EST OUVERT, et c'est le cas de la MAJORITE
    de ses occurrences : `StreamCache$$Action` n'exige aucun groupe ouvert. Seule celle du
    `System_StartMatch` est imbriquee -- parce que la lambda `<Visit>b__18_0` a ouvert le groupe
    autour de toute l'operation. Le port n'a donc rien de special a faire : la profondeur vient du
    `StreamCache`, pas d'un parametre.

    ⚠ LES TROIS TAGS SONT INCONDITIONNELS -- aucun `if` entre le ctor du dictionnaire et l'appel
    d'action. C'est l'inverse de `StreamHelper$$GetRefreshEffectTags`, dont six tags sur onze sont
    gardes (#477-r21). Le port n'a donc aucune branche ici, et le probe le confronte : 3 tags sur
    3, sur toutes les occurrences.

    ⚠ `current_player_id` ET `previous_player_id` VIENNENT DE DEUX CANAUX NATIFS DISTINCTS -- un
    ACCESSEUR (`get_CurrentPlayerId`, qui deroute vers le joueur temporaire quand
    `TurnComponent+0x28` a une valeur) et un CHAMP BRUT (`+0x18`). Les fusionner en une seule
    notion de « joueur » serait faux des qu'un tour temporaire est en cours."""
    tags: Dict[int, int] = {}
    tags[int(TagKey.Match_CurrentPlayerId)] = int(current_player_id)
    tags[int(TagKey.Match_PreviousPlayerId)] = int(previous_player_id)
    tags[int(TagKey.Match_AmountOfTurnsStartedByCurrentPlayer)] = \
        int(turns_started_by_current_player)
    events.action(StepType.PrepareTurn, match_entity_id, tags)


#: `sourceId` du `Group=StartTurn`. QUATRIEME occurrence d'un `Source=` vide sur ce dossier, mais
#: la PREMIERE dont la lecture differe : les trois precedents (`User_PlaceUnit`,
#: `System_ProcessRemovals`, `System_StartMatch`) passaient le PREMIER CHAMP STATIQUE de
#: `System.String`, c'est-a-dire `String.Empty` ; ici le decompile passe un SLOT DE LITTERAL
#: (`DAT_183386748`, initialise par le prologue de litteraux de la fonction), et
#: `data/symbols/<build>/metadata/string_literals.tsv` le resout : index 0, valeur `""`. Le meme
#: slot sert au `Group=RarityCapTransform` de `StartMatchOperation`. Les deux voies rendent le
#: meme `Source=` vide apres `String.Format` -- la distinction n'est pas observable, elle est LUE.
START_TURN_SOURCE_ID = ""


def start_turn(events: StreamDispatcher, match_entity_id: int, previous_player_id: int,
               corps: Optional[Callable[[], None]] = None,
               verifier: Optional[Callable[[], None]] = None) -> None:
    """`IdunBattle.Operations.StartTurnOperation$$Execute` -- sa face STREAM.

    LES TROIS EMISSIONS, lues verbatim, dans l'ordre du decompile :

        Events.StartGroup(GroupType.StartTurn /*0x2f*/,
                          StateExtensions.GetMatchEntity(state).<Id>,
                          "" /*litteral d'index 0*/, default(BEntityId?));
        var tags = new Dictionary<TagKey,int>();
        tags.Add(TagKey.Match_PreviousPlayerId /*0x9e*/, turn.<+0x18>);
        Events.Action(StepType.StartTurn /*2*/,
                      StateExtensions.GetMatchEntity(state).<Id>, tags);
        processor.<slot 0x2f>(refreshOptions);                        // -- `corps`
        processor.<slot 0x4d>(EventTriggerType.TurnStart_EffectActivation /*0x12*/, entities);
        processor.<slot 0x4d>(EventTriggerType.TurnStart_Other          /*0x13*/, entities);
        processor.<slot 0x4d>(EventTriggerType.TurnStart_EnvironmentEffects /*0x14*/, entities);
        processor.<slot 0x4d>(EventTriggerType.TurnStart_DelayedAttacks /*0x15*/, entities);
        processor.<slot 0x4d>(EventTriggerType.TurnStart_Actions        /*0x16*/, entities);
        processor.<slot 0x21>();                                       // -- `verifier`
                                  // = `Core.Services.OperationProcessor$$VerifyUnitsTurnFinished`
        Events.FinishGroup();

    ⚠ L'OUVERTURE EST INCONDITIONNELLE, ET C'EST L'INVERSE D'`Effect_Refresh`.
    `RefreshEffectsOperation$$GenerateEventGroup` enveloppe son `StartGroup` dans
    `if (eventActions.Count > 0)` (#477-r21) ; ici le `StartGroup` ne depend de RIEN d'autre que
    d'avoir une entite de match et un dispatcher non nuls. Un `Group=StartTurn` sans aucun enfant
    autre que son `Action=StartTurn` est donc possible, et le port ne doit pas l'empecher.

    ⚠ `Action=StartTurn` EST LA PREMIERE LIGNE DU GROUPE, AVANT TOUT LE CONTENU. Les trois appels
    delegues (`0x2f`, `0x4d`, `0x21`) viennent APRES elle et AVANT le `FinishGroup` -- c'est ce
    qui met leurs emissions DANS le groupe. Le port place donc `corps` entre l'action et la
    fermeture, jamais avant l'action.

    ⚠ `corps` ET `verifier` SONT DEUX PARAMETRES, PAS UN SEUL, ET L'ORDRE EST DERIVE ICI (#477-r22-r1).
    `corps` porte le `RefreshEffects` du slot `0x2f` et les CINQ `EvaluateAbilities(TurnStart_*)`
    du slot `0x4d` ; `verifier` porte le slot `0x21` = `VerifyUnitsTurnFinished`, que le
    decompile appelle APRES les six autres et AVANT `Events.FinishGroup()`. Les fusionner en un
    seul callable rendrait cet ordre a l'APPELANT ; les separer le rend au PORT, ou le decompile
    l'a lu. C'est ce qui fait que la contre-epreuve `verif_avant_corps` a quelque chose a mordre.

    ⚠ L'ENTITE EST LUE DEUX FOIS, PAR DEUX APPELS DISTINCTS a
    `IdunBattle.Entities.StateExtensions$$GetMatchEntity(state)` suivis chacun de l'accesseur
    d'identifiant d'`IdunBattle.Core.IEntity` -- une fois pour le groupe, une fois pour l'action.
    Le port les fait suivre le MEME parametre, et le probe EXIGE que les deux coincident sur le
    flux : c'est un recoupement mesurable, pas une supposition.

    ⚠ LE TAG EST UNIQUE, ET IL EST LE MEME QUE L'UN DES TROIS DE `prepare_turn`. Un seul `Add`
    entre le ctor du dictionnaire et l'appel d'action -- `Match_CurrentPlayerId` et
    `Match_AmountOfTurnsStartedByCurrentPlayer` sont bien LUS par la fonction (dans `uVar7` et
    `uVar8`), mais servent ailleurs : le premier a resoudre l'entite du joueur courant, le second
    a la garde `if (turnsStarted == 1 && ...)` de fin. Les recopier dans les tags serait la faute
    naturelle -- c'est la contre-epreuve `tag_startturn`.

    `corps` = `None` signifie un groupe sans contenu, ce que le port doit savoir emettre."""
    events.start_group(GroupType.StartTurn, match_entity_id, START_TURN_SOURCE_ID, None)
    events.action(StepType.StartTurn, match_entity_id,
                  {int(TagKey.Match_PreviousPlayerId): int(previous_player_id)})
    if corps is not None:
        corps()
    if verifier is not None:
        verifier()
    events.finish_group()


#: LA CORRESPONDANCE STAGE -> OPERATION, LUE dans le `switch` d'`ExecuteStage`, avec le slot de
#: `Core.Services.IOperationProcessor` que chaque branche appelle. Elle vit DANS le port parce
#: qu'elle EST une decision native : un appelant qui la fournirait ferait du port un simple
#: repartiteur, et l'ordre `Prepare` avant `Start` cesserait d'etre derive.
#:
#: ⚠ L'ORDRE DES SLOTS D'UNE INTERFACE NE SE LIT NULLE PART HORS DU METADATA -- une interface
#: IL2CPP n'a aucun corps, donc AUCUNE ligne dans `data/symbols/<build>/frida/methods.tsv`
#: (indexee par adresse) ; mesure de controle : 0 methode declaree par
#: `Core.Services.IOperationProcessor` dans les 121 502 lignes de la table. L'attribution des
#: quatre premieres est donc etablie par RECOUPEMENT (arite + nom de l'implementation +
#: emission observee), et la cinquieme (`0x19`) est laissee NON IDENTIFIEE plutot que devinee.
#: ⚠ ET LE MAPPING GLOBAL EST OUVERTEMENT CONTESTE (`#477-r24-r1`, cf. docstring du module) : les
#: numeros en commentaire de fin de ligne sont des REPERES DE CALL-SITE. Ce qui identifie chaque
#: operation ici est son EMISSION -- seul producteur de `StepType.PrepareTurn` d'un cote, seul
#: producteur de `GroupType.StartTurn` de l'autre -- et cette identification-la, le flux la
#: confirme.
OPERATION_PAR_STAGE: Dict[TurnStage, str] = {
    TurnStage.Change: "IdunBattle.Operations.ChangeTurnOperation$$Execute",       # slot 0x17
    TurnStage.Prepare: "IdunBattle.Operations.PrepareTurnOperation$$Execute",     # slot 0x18
    TurnStage.Draft: "<slot 0x19 -- non identifie>",
    TurnStage.Start: "IdunBattle.Operations.StartTurnOperation$$Execute",         # slot 0x1c
    TurnStage.End: "IdunBattle.Operations.EndTurnOperation$$Execute",             # slot 0x1d
}

#: LES DEUX STAGES DONT CE MODULE PORTE L'OPERATION. Les trois autres restent a la charge de
#: l'appelant -- et `execute_stage` REFUSE de continuer s'il ne les fournit pas, plutot que
#: d'emettre un flux ampute en silence.
#:
#: ⚠ `TurnStage.Change` EST SUR pour un emetteur de replay, et c'est LU :
#: `IdunBattle.Operations.ChangeTurnOperation$$Execute` ne touche jamais
#: `IdunBattle.Streams.StreamDispatcher` -- elle resout le joueur suivant
#: (`$$FindNextPlayer`), appelle `TurnComponent$$SetCurrentPlayer`, et peut se rappeler elle-meme.
#: Aucune de ces branches n'ecrit. Un `lambda: None` y est donc FIDELE, pas une approximation.
STAGES_PORTES = (TurnStage.Prepare, TurnStage.Start)


def execute_stage(events: StreamDispatcher, next_turn_stage: int,
                  operations: Mapping[TurnStage, Callable[[], None]]) -> TurnStage:
    """`IdunBattle.Operations.ContinueTurnPhaseOperation$$ExecuteStage(nextTurnStage,
    forceEndTurn)` -- le SWITCH, et lui seul.

    Rend le stage execute, qui devient le stage COURANT : le natif ecrit `turn.<+0x10> =
    nextTurnStage` EN TETE de la fonction, avant le switch. Cet ordre compte -- c'est lui qui fait
    que la garde `turn.<+0x10> == TurnStage.Draft` de `HandleNextTurn` voit le stage PRECEDEMMENT
    execute, pas celui qu'on s'apprete a executer.

    ⚠ `forceEndTurn` N'EST LU QUE PAR LA BRANCHE `End` (`processor.<slot 0x1d>(!forceEndTurn)`),
    et cette branche n'est pas portee : le parametre n'apparait donc pas dans la signature. C'est
    une omission DECLAREE.

    ⚠ LE `default:` NATIF NE FAIT RIEN ; LE PORT LEVE. `TurnStage(int(...))` rejette tout entier
    hors des cinq membres. Le natif retourne simplement -- mais aucun appelant legitime ne peut
    fabriquer un stage hors domaine (`GetNextTurnStage` ne rend qu'un membre), et un flux ampute
    en silence est exactement ce que `engine/streams/conformance.py` existe pour interdire."""
    stage = TurnStage(int(next_turn_stage))
    if stage not in operations:
        raise ValueError(
            "execute_stage : aucune operation fournie pour TurnStage.%s (le natif y appelle %s). "
            "Ce paquet porte %s ; les autres stages doivent etre passes explicitement, meme "
            "vides -- une entree muette produirait un flux ampute sans erreur"
            % (stage.name, OPERATION_PAR_STAGE[stage],
               "/".join("TurnStage.%s" % s.name for s in STAGES_PORTES)))
    operations[stage]()
    return stage


def get_next_turn_stage(current_turn_stage: int,
                        requested_turn_stage: int) -> Optional[TurnStage]:
    """`IdunBattle.Entities.Components.TurnComponent$$GetNextTurnStage`, lu verbatim :

        if (this.<+0x14> != this.<+0x10>)
            return new Nullable<TurnStage>(EnumExt.NextValueOrFirst(this.<+0x10>));
        return default(Nullable<TurnStage>);

    `current_turn_stage` est `+0x10`, `requested_turn_stage` est `+0x14` -- l'attribution vient
    des OFFSETS de leurs setters, pas de leurs noms Ghidra (cf. docstring du module).

    ⚠ LA COMPARAISON PORTE SUR L'EGALITE, PAS SUR UN ORDRE. Le stage courant avance donc en
    CYCLE (`NextValueOrFirst`) jusqu'a retomber sur le demande -- c'est ce qui fait qu'un
    `ContinueTurnPhase(Start)` demande depuis `End` traverse `Change`, `Prepare` et `Draft` avant
    d'atteindre `Start`, alors que le meme appel depuis `Change` ne traverse que `Prepare` et
    `Draft`."""
    if int(requested_turn_stage) == int(current_turn_stage):
        return None
    return next_value_or_first(current_turn_stage)


def continue_turn_phase(events: StreamDispatcher, current_turn_stage: int,
                        requested_turn_stage: int,
                        operations: Mapping[TurnStage, Callable[[], None]]) -> TurnStage:
    """`IdunBattle.Operations.ContinueTurnPhaseOperation$$Execute` -- sa BOUCLE.

    Rend le stage courant final. Le natif rend `void` ; le port rend la valeur pour qu'un
    appelant enchaine deux phases sans re-deviner ou il en est.

    ⚠ LA SURCHARGE `requestedTurnStage == null` N'EST PAS PORTEE. Le natif la traite (`if
    (requestedTurnStage.HasValue) turn.<+0x14> = ...`), c'est-a-dire « garder le stage demande
    courant ». Les deux call-sites confrontes passent tous deux une valeur : `TurnStage.Start` en
    dur depuis `StartMatchOperation$$Execute`, et les MEMES trois arguments depuis la lambda
    `InputMessageProcessor$$u003CVisitu003Eb__20_0`. Le port exige donc un stage demande ; c'est
    une omission DECLAREE, pas un oubli.

    ⚠ LES GARDES DE `HandleNextTurn` NE SONT PAS PORTEES (cf. docstring du module) : le port
    execute CHAQUE stage traverse. Sur un montage avec drafting en attente le natif s'arreterait
    avant `Start` et le port emettrait un `Group=StartTurn` de trop -- c'est la meme frontiere que
    pour `evaluate_ability_trigger` (#477-r21), dont les deux gardes dependent aussi de l'etat
    ECS que ce paquet ne simule pas.

    ⚠ LA TERMINAISON EST GARANTIE PAR LE CYCLE, PAS PAR UN COMPTEUR. `next_value_or_first` parcourt
    les cinq membres en boucle, donc le stage courant atteint le demande en au plus `len(TurnStage)
    - 1` pas ; le natif n'a pas davantage de garde-fou, et le port n'en ajoute pas."""
    courant = TurnStage(int(current_turn_stage))
    demande = TurnStage(int(requested_turn_stage))
    while True:
        suivant = get_next_turn_stage(courant, demande)
        if suivant is None:
            return courant
        courant = execute_stage(events, suivant, operations)
