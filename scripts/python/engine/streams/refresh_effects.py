"""La face STREAM de `IdunBattle.Operations.RefreshEffectsOperation` -- `Group=Effect_Refresh`
et ses quatre actions d'effet.

C'est le PLUS PETIT des deux artefacts du bloc 1 de `System_StartMatch` (#477-r21), et le seul
dont la totalite du texte se lit dans des fonctions NOMMEES. Il produit, sur le flux temoin,
les 42 / 44 `Group=Effect_Refresh` que #477-r20 a chiffres comme non atteignables.

CE QUE CE MODULE EST -- ET N'EST PAS. Comme `game_setup` et `input_messages`, seule la FACE
STREAM est portee. `RefreshEffectsOperation` decide AUSSI quels effets rafraichir, quelles
cibles ajouter ou retirer (`ShouldBeActive`, `GetTargetsToAdd`, `GetTargetsToRemove`,
`UpdateEffectTargets`) et alloue les entites ECS d'effet : RIEN de cela n'est ici. Le port
recoit ses donnees, comme `UnitSetup` les recoit pour le deploiement.

LA CHAINE NATIVE, lue verbatim :

    RefreshEffectsOperation$$GenerateEventGroup(eventActions, effectEntity, effectComponent)
        if (eventActions.Count > 0) {                 <- LE GROUPE EST CONDITIONNEL
            <StartEventGroup, inline>
            foreach (action in eventActions) action.Invoke();
            <FinishEventGroup, inline>
        }

    RefreshEffectsOperation$$StartEventGroup(effectEntity, effectComponent)
        if (state.<slot 0xb>()) return;              <- garde de simulation, cf. plus bas
        Events.StartGroup(GroupType.Effect_Refresh /*0x16*/, effectEntity.<Id>,
                          ((EffectType)effectComponent.<+0x58>).ToString(),
                          default(BEntityId?));

    RefreshEffectsOperation$$FinishEventGroup()
        if (state.<slot 0xb>()) return;
        Events.FinishGroup();

⚠ `GenerateEventGroup` NE PEUT PAS PRODUIRE UN GROUPE VIDE, ET C'EST LU. Le test
`eventActions.Count > 0` enveloppe l'ouverture ET la fermeture. C'est l'inverse exact du cran
`System_ProcessRemovals` (#477-r19), ou le groupe s'ouvrait pour un contenu qui restait vide.
Le flux temoin le confirme : sur 42 + 44 occurrences, zero `Effect_Refresh` sans action.

⚠ LA GARDE `state.<slot 0xb>()` EST UN SLOT D'INTERFACE, PAS UN NOM. Elle apparait
IDENTIQUEMENT en tete de `StartEventGroup`, `FinishEventGroup` et des quatre `Add*Action` : les
six sortent SANS RIEN EMETTRE quand elle est vraie. C'est le regime de SIMULATION (les
`OperationProcessor$$SimulateEffects<T>` du binaire), jamais atteint sur un deroule reel -- le
flux temoin porte 86 / 94 actions d'effet, donc la garde y est fausse partout. Le port ne la
materialise PAS : un emetteur de replay n'a pas de mode simulation, et un parametre toujours
faux serait une branche morte de plus. C'est une omission DECLAREE, pas un oubli.

LES QUATRE ACTIONS, lues verbatim -- noter QUELLE entite chacune porte :

    AddActivateEffectAction(owner, effectEntity, effectComponent)
        Events.Action(StepType.ActivateEffect /*0x11*/, owner.<Id>,
                      GetEffectTags(effectEntity, effectComponent, StepType.ActivateEffect));
    AddDeactivateEffectAction(owner, effectEntity, effectComponent)
        Events.Action(StepType.DeactivateEffect /*0x12*/, owner.<Id>,
                      GetEffectTags(effectEntity, effectComponent, StepType.DeactivateEffect));
    AddLoseEffectAction(target, effectEntity, effectComponent)
        Events.Action(StepType.LoseEffect /*0x10*/, target.<Id>,
                      GetEffectTags(effectEntity, effectComponent, StepType.LoseEffect));
    AddReceiveEffectAction(target, effectTags)
        Events.Action(StepType.ReceiveEffect /*0xf*/, target.<Id>, effectTags);

⚠ `AddReceiveEffectAction` NE CALCULE PAS SES TAGS -- SEULE DES QUATRE. Elle les recoit tout
faits de son appelant ; les trois autres appellent `RefreshEffectsOperation$$GetEffectTags`,
qui delegue au slot 3 du `StreamHelper`, c'est-a-dire
`IdunBattle.Core.Services.StreamHelper$$GetRefreshEffectTags`. La signature du port garde cette
asymetrie plutot que de l'uniformiser : c'est elle qui explique pourquoi un `ReceiveEffect`
porte cinq tags la ou un `ActivateEffect` du MEME effet n'en porte qu'un.

⚠ `ActivateEffect` ET `DeactivateEffect` PORTENT L'ENTITE `owner`, `ReceiveEffect` ET
`LoseEffect` L'ENTITE `target` -- et les deux DIVERGENT. Mesure sur le flux temoin (C1_02) :
`Group=Effect_Refresh Entity=82 Source=StructuralAnalyserDmgBoost` porte
`Action=ActivateEffect Entity=51` puis TROIS `Action=ReceiveEffect` sur 49, 55 et 53. Un port
qui confondrait les deux serait faux sur toutes les auras.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Sequence

from ..entities.effect_type import EffectType
from .dispatcher import StreamDispatcher
from .entity_id import format_enum_value
from .group_type import GroupType
from .step_type import StepType
from .tag_key import TagKey


@dataclass(frozen=True)
class EffectState:
    """`Nullable<...>` du composant d'effet, lu a `EffectComponent+0x2c`.

    ⚠ LU, JAMAIS CONFRONTE. Le decompile de `GetRefreshEffectTags` teste `HasValue` sur ce
    champ puis emet DEUX tags d'affilee (`Effect_State_Level`, puis
    `Effect_State_VariableMultiplierPercentage`), chacun par un `get_Value` sur la MEME
    `Nullable`. Aucune occurrence sur les flux temoins de #477-r20 / -r21 : les deux tags sont
    absents des 244 exerces. Le port les rend EXPRIMABLES (ce champ) plutot que de les taire,
    et le probe les compte en NON CONFRONTE."""

    level: int
    variable_multiplier_percentage: int


@dataclass(frozen=True)
class EffectSetup:
    """Ce que `StreamHelper$$GetRefreshEffectTags` LIT -- et rien de plus.

    Chaque champ cite l'expression native dont il provient. Les trois sources
    (`active_ability` / `triggered_ability` / `trait`) viennent du slot 6 puis du slot 7 de la
    CONFIGURATION d'effet, les autres du COMPOSANT : ce sont deux objets distincts dans le
    natif, et c'est pourquoi le port ne les fusionne pas en une seule notion de « source »."""

    entity_id: int
    """`effectEntity.<Id>` -- l'entite ECS de l'EFFET. C'est le `Entity=` du `Group=` et la
    valeur du tag `Effect_Id`.

    IL SE DERIVE : `engine/streams/entity_allocator.add_effect(match)` rend exactement cet
    identifiant, le compteur etant celui que `game_setup.assign_entity_ids` a laisse a la sortie
    du deploiement (`#477-r21-r3`, regle SUFFISANTE sur 63/63, 67/67 et 22/22 allocations de
    trois scenarios).

    ⚠ MAIS L'APPELANT DOIT LE DEMANDER DANS L'ORDRE DE CREATION, PAS DANS L'ORDRE D'APPARITION.
    Les deux DIFFERENT, et c'est mesure : 4 / 3 / 0 inversions selon le scenario, plus 2 / 4 / 5
    entites d'effet ALLOUEES dont le flux n'ecrit aucune ligne. Alimente par le seul ordre du
    flux, l'allocateur ne rend juste que 7 / 7 / 4 identifiants sur 61 / 63 / 17. Savoir quels
    `AddEffectOperation` sont appeles, et dans quel ordre, est la SELECTION -- `#477-r21-r2`."""

    effect_type: int
    """`effectComponent.<+0x58>` -- l'`EffectType`. Le `Source=` du groupe en est le NOM, rendu
    par `System.Enum$$ToString`."""

    current_level: int = 0
    """`effectComponent.<+0x68>` -> `TagKey.Effect_CurrentLevel`. Emis SANS CONDITION dans la
    branche `ReceiveEffect` -- c'est le seul tag de cette branche qui n'a aucune garde."""

    source_id: int = 0
    """`effectComponent.<+0x10>` -> `TagKey.Effect_SourceId`, emis SEULEMENT si non nul
    (`if (effectComponent.<+0x10> != 0)`). `0` = pas de source, donc pas de tag."""

    remaining_turns: Optional[int] = None
    """`effectComponent.<+0x64>` -> `TagKey.Effect_RemainingTurns`, garde par le drapeau
    `effectComponent.<+0x5d>`. `None` = drapeau faux. LE DRAPEAU EST UN CHAMP DISTINCT DE LA
    VALEUR dans le natif : un effet permanent porte `0` sous un drapeau faux, pas l'absence de
    champ -- d'ou l'`Optional` plutot qu'un test `> 0`."""

    source_active_ability: Optional[int] = None
    """slot 6 de la config, 1er champ -> `TagKey.Effect_SourceActiveAbility`. Deux `HasValue`
    imbriques dans le decompile (une `Nullable` dans une `Nullable`)."""

    source_triggered_ability: Optional[int] = None
    """slot 6 de la config, 2e champ -> `TagKey.Effect_SourceTriggeredAbility`."""

    source_trait: Optional[int] = None
    """slot 7 de la config -> `TagKey.Effect_SourceTrait`."""

    bonded_entity_id: Optional[int] = None
    """`TagKey.BondEffect_BondedId`, emis quand l'entite d'EFFET porte le composant de lien
    (`effectEntity.TryGetComponent<...>(out c)`) -- pas quand la CIBLE le porte. Aucune
    occurrence sur les flux temoins."""

    state: Optional[EffectState] = None
    """`effectComponent.<+0x2c>` -- cf. `EffectState`. Non confronte."""


def get_refresh_effect_tags(effect: EffectSetup, step_type: int) -> Dict[int, int]:
    """Mirror de `IdunBattle.Core.Services.StreamHelper$$GetRefreshEffectTags(effectEntity,
    effect, effectComponent, stepType)`.

    LA STRUCTURE EST UN `if (stepType == StepType.ReceiveEffect) ... else ...`, ET LES DEUX
    BRANCHES SE REJOIGNENT SUR LE MEME `Add` FINAL. Le decompile le montre litteralement : la
    branche `else` saute a `LAB_1811c9d28`, qui est aussi la sortie de la branche
    `ReceiveEffect`. C'est ce partage qui garantit que `Effect_Id` est present sur les QUATRE
    formes d'action, et c'est pourquoi le port n'a qu'un seul site pour ce tag.

    L'ORDRE DES `Add` CI-DESSOUS EST CELUI DU DECOMPILE, ET IL N'EST PAS OBSERVABLE :
    `StreamCache$$Action` recopie les tags dans un `SortedDictionary<TagKey,int>`, donc le flux
    les ecrit dans l'ordre des ORDINAUX. Il est conserve pour que le mirror se relise contre le
    natif, pas parce qu'il compterait.

    CONTROLE INDEPENDANT DE CE MAPPING. Les onze cles sont un intervalle contigu d'ordinaux
    (`0xa4`..`0xae`) que `TagKey` nomme `BondEffect_BondedId` .. `Effect_Id`. Le flux temoin le
    recoupe sur cinq d'entre elles a la fois par leur NOM et par leur ORDRE : un bloc
    `ReceiveEffect` y sort `Effect_RemainingTurns` (165), `Effect_CurrentLevel` (167),
    `Effect_SourceId` (168), `Effect_SourceTriggeredAbility` (170), `Effect_Id` (174) --
    strictement croissant, comme le tri l'impose."""
    tags: Dict[int, int] = {}
    if int(step_type) == int(StepType.ReceiveEffect):
        # `if (effectEntity.TryGetComponent<...>(out c) && c != null)`
        if effect.bonded_entity_id is not None:
            tags[int(TagKey.BondEffect_BondedId)] = int(effect.bonded_entity_id)
        # `if (effectComponent.<+0x10> != 0)`
        if int(effect.source_id) != 0:
            tags[int(TagKey.Effect_SourceId)] = int(effect.source_id)
        # tout ce qui suit est dans `if (effect != null)` -- la CONFIGURATION d'effet. Elle est
        # toujours resolue ici (`EffectsDatabase.Get(effectComponent.<+0x58>)`), et son absence
        # LEVE dans le natif (`FUN_1801f51f0`) : le port n'a donc pas de branche pour ce cas.
        if effect.source_active_ability is not None:
            tags[int(TagKey.Effect_SourceActiveAbility)] = int(effect.source_active_ability)
        if effect.source_triggered_ability is not None:
            tags[int(TagKey.Effect_SourceTriggeredAbility)] = \
                int(effect.source_triggered_ability)
        if effect.source_trait is not None:
            tags[int(TagKey.Effect_SourceTrait)] = int(effect.source_trait)
        # `if (effectComponent.<+0x5d> != 0) tags.Add(0xa5, effectComponent.<+0x64>)`
        if effect.remaining_turns is not None:
            tags[int(TagKey.Effect_RemainingTurns)] = int(effect.remaining_turns)
        # `if (effectComponent.<+0x2c>.HasValue) { Add(0xac, ...); Add(0xad, ...); }`
        if effect.state is not None:
            tags[int(TagKey.Effect_State_Level)] = int(effect.state.level)
            tags[int(TagKey.Effect_State_VariableMultiplierPercentage)] = \
                int(effect.state.variable_multiplier_percentage)
        # sans garde
        tags[int(TagKey.Effect_CurrentLevel)] = int(effect.current_level)
    # sortie COMMUNE aux deux branches (`LAB_1811c9d28`)
    tags[int(TagKey.Effect_Id)] = int(effect.entity_id)
    return tags


def add_activate_effect_action(events: StreamDispatcher, owner_id: int,
                               effect: EffectSetup) -> None:
    """`RefreshEffectsOperation$$AddActivateEffectAction(owner, effectEntity, effectComponent)`.

    L'entite est celle du PORTEUR de l'effet, pas de la cible."""
    events.action(StepType.ActivateEffect, owner_id,
                  get_refresh_effect_tags(effect, StepType.ActivateEffect))


def add_deactivate_effect_action(events: StreamDispatcher, owner_id: int,
                                 effect: EffectSetup) -> None:
    """`RefreshEffectsOperation$$AddDeactivateEffectAction(owner, effectEntity,
    effectComponent)`."""
    events.action(StepType.DeactivateEffect, owner_id,
                  get_refresh_effect_tags(effect, StepType.DeactivateEffect))


def add_lose_effect_action(events: StreamDispatcher, target_id: int,
                           effect: EffectSetup) -> None:
    """`RefreshEffectsOperation$$AddLoseEffectAction(target, effectEntity, effectComponent)`.

    L'entite est celle de la CIBLE qui perd l'effet."""
    events.action(StepType.LoseEffect, target_id,
                  get_refresh_effect_tags(effect, StepType.LoseEffect))


def add_receive_effect_action(events: StreamDispatcher, target_id: int,
                              effect_tags: Dict[int, int]) -> None:
    """`RefreshEffectsOperation$$AddReceiveEffectAction(target, effectTags)`.

    ⚠ LES TAGS SONT UN PARAMETRE, PAS UN CALCUL -- c'est la seule des quatre actions dans ce
    cas, et le port le preserve. L'appelant les obtient par `get_refresh_effect_tags(effect,
    StepType.ReceiveEffect)`."""
    events.action(StepType.ReceiveEffect, target_id, effect_tags)


def start_event_group(events: StreamDispatcher, effect: EffectSetup) -> None:
    """`RefreshEffectsOperation$$StartEventGroup(effectEntity, effectComponent)`.

    `sourceId` est le NOM de l'`EffectType`, rendu par `System.Enum$$ToString` sur le champ
    `effectComponent.<+0x58>` -- pas un slot de litteral, contrairement aux trois `Source=`
    VIDES des groupes racines de #477-r18 / -r19 / -r20. Le flux temoin le montre en clair
    (`Source=Melta_ExtraDmg`, `Source=BlockEnteringUnits`, ...).

    `initialTarget` est `default(BEntityId?)` -- LU comme litteral, jamais calcule ici."""
    events.start_group(GroupType.Effect_Refresh, effect.entity_id,
                       format_enum_value(EffectType, effect.effect_type), None)


def finish_event_group(events: StreamDispatcher) -> None:
    """`RefreshEffectsOperation$$FinishEventGroup()`."""
    events.finish_group()


def generate_event_group(events: StreamDispatcher,
                         event_actions: Sequence[Callable[[], None]],
                         effect: EffectSetup) -> None:
    """`RefreshEffectsOperation$$GenerateEventGroup(eventActions, effectEntity,
    effectComponent)`.

    ⚠ `event_actions` EST UNE SEQUENCE DE CALLABLES PARCE QUE LE NATIF EN EST UNE.
    `eventActions` y est une `List<Action>` construite par les appelants (`AddTargetsToEffect`,
    `RemoveTargetsFromEffect`, `ApplyEffectsForTargets`, `RevertEffectsForTargets`, `UpdateLevel`)
    et invoquee ici dans l'ORDRE. Le port ne re-decide donc pas l'ordre : il le recoit, exactement
    comme l'operation native. C'est ce qui permet a un appelant de glisser une action que ce
    module ne produit pas -- typiquement l'`Action=ChangeStats` d'une modification de stat, qui
    sort d'`Effect.ApplyModification` et reste hors de cette tranche (`#477-r21-r1`).

    ⚠ LE `if (eventActions.Count > 0)` ENVELOPPE L'OUVERTURE ET LA FERMETURE : zero action =>
    AUCUNE ligne, pas un groupe vide."""
    if len(event_actions) <= 0:
        return
    start_event_group(events, effect)
    for action in event_actions:
        action()
    finish_event_group(events)


def bind_refresh_actions(events: StreamDispatcher, actions, effect: EffectSetup
                         ) -> list:
    """Traduit le PLAN rendu par `engine/runner/operations/refresh_effects.update_effect_targets`
    en la `Sequence[Callable]` que `generate_event_group` consomme.

    C'EST LA FRONTIERE DECISION / EMISSION, ET ELLE EST LE `.Invoke()` NATIF. Cote natif, la
    `List<Action>` porte deja les closures : decider et emettre sont le meme objet. Le port les
    separe (l'un lit et ecrit l'ETAT ECS, l'autre n'ecrit que des lignes), donc il lui faut ce
    point de recollement -- et c'est ici qu'il vit, du cote EMISSION, pour que la couche qui
    decide n'importe rien de `streams`.

    ⚠ LES DESCRIPTEURS SONT LUS EN CANARD (`.action`, `.entity`), JAMAIS IMPORTES. Importer
    `RefreshAction` depuis `engine.runner` creerait une dependance `streams -> runner` a rebours
    de celle que le port vient d'etablir.

    ⚠ LES TAGS `ReceiveEffect` SONT CALCULES UNE SEULE FOIS, HORS BOUCLE -- mirror littéral d'
    `IdunBattle.Operations.RefreshEffectsOperation$$AddTargetsToEffect`, qui hisse
    `GetEffectTags(effectEntity, effectComponent, StepType.ReceiveEffect)` au-dessus de son
    `foreach` et le passe tel quel a chaque `AddReceiveEffectAction`. C'est aussi ce qui explique
    que `AddReceiveEffectAction` soit la seule des quatre a RECEVOIR ses tags.

    Les deux formes `RevertEffectsForTargets` / `ApplyEffectsForTargets` n'ecrivent AUCUNE ligne de
    ce module : elles produisent des `Action=ChangeStats` / `Action=ChangeAbility` qui sortent d'
    `Effect.ApplyModification`, hors perimetre (#477-r21-r1). Elles sont donc IGNOREES ici, et
    c'est declare plutot que silencieux."""
    receive_tags = get_refresh_effect_tags(effect, StepType.ReceiveEffect)
    out: list = []
    for a in actions:
        nom = getattr(a, "action", None)
        cible = getattr(a, "entity", None)
        if nom == "AddActivateEffectAction":
            out.append(lambda o=cible: add_activate_effect_action(events, o, effect))
        elif nom == "AddDeactivateEffectAction":
            out.append(lambda o=cible: add_deactivate_effect_action(events, o, effect))
        elif nom == "AddLoseEffectAction":
            out.append(lambda t=cible: add_lose_effect_action(events, t, effect))
        elif nom == "AddReceiveEffectAction":
            out.append(lambda t=cible, tg=receive_tags: add_receive_effect_action(events, t, tg))
    return out
