"""La face STREAM d'`IdunBattle.Operations.EvaluateTriggerOperation` -- `Group=Ability_Power`.

C'est le SECOND artefact du bloc 1 de `System_StartMatch` (#477-r21) : les 29 / 30
`Group=Ability_Power` de profondeur 1 du flux temoin, qui enveloppent 35 / 37 des
`Group=Effect_Refresh` que #477-r20 avait chiffres non atteignables.

COMMENT ON Y ARRIVE DEPUIS `StartMatchOperation` -- la chaine, lue de bout en bout :

    IdunBattle.Operations.StartMatchOperation$$Execute
      processor.<slot 0x51>(GetMatchEntity(state), null, null,
                            EventTriggerType.MatchInit /*0x19*/, default)      <- puis MatchStart
    -> Core.Services.OperationProcessor$$EvaluateAbilities(actor, caster, target, trigger,
                                                           ability)           <- la surcharge a 5 args
         delegue a la surcharge a 10 args, qui construit un `AbilityEntities` et appelle
    -> IdunBattle.Operations.EvaluateTriggerOperation$$Execute(trigger, abilityEntities,
                                                               previousResult)
    -> IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal(...)
         foreach (item in AOperation.AbilityAndEffectCache.<slot 3>(trigger))
             EvaluateAbilityOrEffectTrigger(trigger, item, createAbilityEntities, onlyNonAtomic)
    -> IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger(...)   <- EMET ICI

⚠ LA SURCHARGE A CINQ ARGUMENTS EST ETABLIE, PAS DEVINEE. `Core.Services.OperationProcessor`
porte SIX `EvaluateAbilities` ; le call-site de `StartMatchOperation$$Execute` passe cinq
arguments plus le `MethodInfo*`, et une seule des six a cette arite :
`EvaluateAbilities(actor, caster, target, trigger, ability)`. Les cinq litteraux se lisent :
l'entite de match, `null`, `null`, l'ordinal du declencheur, et une struct d'ability
ENTIEREMENT NULLE (les quatre mots de `&local_128` sont mis a zero juste avant l'appel).

⚠ LES DEUX ORDINAUX SONT NOMMES PAR `engine/dsl/event_trigger_type.py` : `MatchInit = 25`
(`0x19`) et `MatchStart = 26` (`0x1a`). C'est le NOM qui identifie le bloc, pas sa forme dans le
flux -- et c'est la regle « un entier qui DESIGNE passe par un ENUM » appliquee au declencheur.

CE QUE `EvaluateAbilityTrigger` EMET, lu verbatim :

    var events = AOperation.get_Events(this);
    if (sortedTriggeredAbility.<+0x10> != null) {                 // l'unite porteuse
        Events.StartGroup(GroupType.Ability_Power /*0x15*/,
                          sortedTriggeredAbility.<+0x10>.<Id>,
                          ((TriggeredAbilityType)sortedTriggeredAbility.<Order>).ToString(),
                          initialTarget);
        ability.<slot 4>(...);                                    // l'EXECUTION -- le contenu
        if (ability.<slot 9>) component.MarkAsTriggered(order);   // pas d'emission
        Events.FinishGroup();
        DataReporter.<...>(TriggeredAbilityConfigId.GetStringValue(...));   // pas d'emission
    }

⚠ LES DEUX GARDES EN AMONT NE SONT PAS PORTEES, ET ELLES SONT LUES. Avant d'emettre quoi que ce
soit, `EvaluateAbilityTrigger` refuse deux fois : si
`TriggeredAbilityComponent$$GetTimesTriggeredThisPhase(order) >= 0x33` (51 -- la branche part
alors dans `AOperation.get_Logger`, pas dans le flux), et si le slot 2 de l'ability rend faux
(`CanTrigger`-like). Les deux dependent de l'ETAT ECS, que ce paquet ne simule pas : un appelant
qui n'a pas decide de declencher n'appelle simplement pas cette fonction. C'est la meme
frontiere que pour `RefreshEffectsOperation` -- porter la DECISION est `#477-r21-r2`.

⚠ `Source=` EST LE NOM D'UN `TriggeredAbilityType`, ET LE FLUX LE RECOUPE TOUT SEUL. Le groupe
ecrit `Source=OnOnMeltaDamageAbility` et l'effet qu'il enveloppe porte
`Tag=Effect_SourceTriggeredAbility:1211`, or le mirror
`engine/entities/triggered_ability_type.py` donne `OnOnMeltaDamageAbility = 1211`. Mesure sur
C1_02 : les 13 noms distincts qui apparaissent a la fois en `Source=` et en tag concordent 13 / 13
(`1115 InescapableAccuracy`, `98 TerrifyingAbility`, `1143 StructuralAnalyser`,
`1216 BlessingsOfKhorne`, `1037 TeleportStrike`, `1188 RapidAssault`, `1142 TerminatorArmour`,
`1285 PowerTrip`, `1030 BigTarget`, `1308 StandVigil`, `1092 MartialSuperiority`,
`1085 Parry`, `1186 CrushingStrike`). Le NOM et l'ORDINAL sont deux canaux natifs distincts --
leur accord confirme la lecture du decompile, il ne la remplace pas.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from ..entities.triggered_ability_type import TriggeredAbilityType
from .dispatcher import StreamDispatcher
from .entity_id import format_enum_value
from .group_type import GroupType


def evaluate_ability_trigger(events: StreamDispatcher, unit_entity_id: int,
                             triggered_ability_type: int,
                             initial_target: Optional[int] = None,
                             corps: Optional[Callable[[], None]] = None) -> None:
    """`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger`.

    `corps` est l'EXECUTION de l'ability declenchee -- le slot 4 de l'objet d'ability, entre le
    `StartGroup` et le `FinishGroup`. Le port ne la simule pas : un appelant qui sait ce que
    l'ability produit (typiquement un `Group=Effect_Refresh` de `refresh_effects`) le passe ici.
    `None` = le groupe est VIDE, ce que le flux temoin montre bel et bien
    (`Group=Ability_Power Entity=49 Source=OverwatchAutoAttack InitialTarget=` suivi
    immediatement de `Finish_Group`, idem `BigTarget` sur l'entite 57).

    ⚠ UN `Ability_Power` VIDE EXISTE, LA OU UN `Effect_Refresh` VIDE N'EXISTE PAS. Les deux
    groupes se ressemblent dans le flux et se comportent a l'INVERSE : `GenerateEventGroup`
    enveloppe son `StartGroup` dans `if (eventActions.Count > 0)`, alors qu'ici le `StartGroup`
    ne depend que de `sortedTriggeredAbility.<+0x10> != null`, jamais du contenu. Confondre les
    deux ferait disparaitre deux groupes sur C1_02.

    `initial_target` est le SEUL des quatre arguments de `StartGroup` a ne pas etre un litteral :
    le decompile le construit en `Nullable<BEntityId>` a partir de l'identifiant rendu par le
    slot 1 d'un objet obtenu au slot 0xc, et le laisse `null` quand cet objet est nul. Sur les
    59 `Ability_Power` des deux boards temoins il vaut `null` 59 / 59 -- ce que le port exprime
    par un defaut, pas par une constante."""
    events.start_group(GroupType.Ability_Power, unit_entity_id,
                       format_enum_value(TriggeredAbilityType, triggered_ability_type),
                       initial_target)
    if corps is not None:
        corps()
    events.finish_group()


def execute_internal(events: StreamDispatcher,
                     entrees: Sequence[Callable[[], None]]) -> None:
    """`IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal` -- sa seule face stream.

    L'operation n'emet RIEN elle-meme : tout son texte vient de ses enfants. Ce qu'elle apporte,
    et que le port preserve, c'est l'ORDRE -- elle parcourt la liste que le cache d'abilites et
    d'effets rend pour le declencheur (`AOperation.AbilityAndEffectCache.<slot 3>(trigger)`) et
    appelle `EvaluateAbilityOrEffectTrigger` sur chaque entree, dans cet ordre.

    ⚠ CE QUI FIXE L'ORDRE EST LE CACHE, ET IL N'EST PAS PORTE. La liste est triee cote natif
    (le parametre s'appelle `sortedTriggeredAbility` chez l'appelee) ; ni sa construction ni son
    critere de tri ne sont dans cette tranche. L'ordre est donc une ENTREE, et le probe le
    declare en borne (c) plutot que de laisser croire qu'il est mesure.

    ⚠ `EvaluateAbilityOrEffectTrigger` TRIE ENTRE DEUX FORMES, et le port ne materialise pas ce
    tri : le decompile teste deux `Il2CppClass*` distincts sur l'entree (un composant d'EFFET,
    puis un d'ABILITY DECLENCHEE) et part respectivement vers
    `EvaluateEffectTriggerEffectAbilities` + `EvaluateEffectTriggerTargets`, ou vers
    `CanGetAbilityTrigger` + `EvaluateAbilityTrigger`. Les deux branches ne sont PAS exclusives
    dans le natif (deux `if` successifs, pas un `if/else`). Cote flux, l'appelant du port dit
    directement ce que chaque entree emet."""
    for entree in entrees:
        entree()
