"""La face STREAM du `Group=Damage` -- `IdunBattle.Operations.ApplyDamageOperation$$Execute`
(#477-r34).

C'est la SECONDE des deux familles que `#477-r22-r1` avait laissees hors perimetre dans les
couples `Action=PrepareTurn` + `Group=StartTurn` (l'autre, `Group=ResurrectUnit`, reste
ouverte). Elle ne sort PAS du pipeline de tour : elle sort du pipeline de DEGAT, et c'est
pourquoi elle apparait aussi -- et bien plus souvent -- sous `User_UseAbility` et
`System_ProcessDeaths`.

LES TROIS EMISSIONS, lues verbatim dans `ApplyDamageOperation$$Execute`
----------------------------------------------------------------------

    Events.StartGroup(GroupType.Damage /*0x1a*/, <IEntity slot 0>(target),
                      "" /*litteral d'index 0*/, default(BEntityId?));
    Events.Action(StepType.UnitDamaged /*4*/, <IEntity slot 0>(target),
                  StreamHelper.<slot 9>(target, damageResult, numMembersDied, caster, result));
    ...                                                        // -- `corps`
    Events.FinishGroup();

⚠ LES DEUX LIGNES PORTENT LA MEME ENTITE, LUE DEUX FOIS. Le decompile appelle deux fois
l'accesseur d'identifiant d'`IdunBattle.Core.IEntity` sur le MEME `target` -- une fois pour
l'entete du groupe, une fois pour l'action. Le port les fait suivre le meme parametre, et le
probe EXIGE que les deux coincident sur le flux : c'est un recoupement mesurable.
C'est aussi l'entite du `Tag=Target_Id` que `GetDamageTags` ecrit, ce qui donne un TROISIEME
canal pour la meme valeur -- et le probe confronte les trois.

⚠ LE `Source=` EST VIDE PAR UN SLOT DE LITTERAL, PAS PAR `String.Empty`. Le call-site passe
`DAT_183386748`, le MEME slot que le `Group=StartTurn` de `StartTurnOperation` -- resolu par
`data/symbols/<build>/metadata/string_literals.tsv` a l'index 0, valeur `""`. La distinction
avec le premier champ statique de `System.String` (la voie de `User_PlaceUnit`,
`System_ProcessRemovals`, `System_StartMatch`) n'est PAS observable apres `String.Format` :
elle est LUE, pas mesuree.

⚠ L'`InitialTarget=` EST VIDE PAR UN LITTERAL `0` -- le septieme argument du helper d'appel,
`default(BEntityId?)`. Le flux le confirme sur 72 / 72 occurrences.

⚠ LE GROUPE PEUT PORTER DAVANTAGE QUE SON ACTION, ET C'EST `corps`. Entre l'`Events.Action` et
l'`Events.FinishGroup`, `Execute` traverse ~550 lignes de decompile (statistiques de coup,
bouclier, membres, drapeaux, evenements post-degat) -- dont certaines emettent : le flux montre
des `Group=Effect_Refresh` DANS le `Group=Damage` (les effets qui expirent sur le coup). Le
port les recoit par `corps`, exactement comme `start_turn` recoit le sien, plutot que de
supposer un groupe toujours reduit a une ligne.

CE QUE CE MODULE NE PORTE PAS, ET QUI EST NOMME
-----------------------------------------------
  * LA DECISION qu'un coup produise un `Group=Damage`. `ApplyDamageOperation$$Execute` est
    appelee depuis le pipeline de degat (`ADamageOperation$$ExecuteHit` et ses derives
    `AttackDamageOperation` / `AbilityDamageOperation` / `MachineDamageOperation`) ; ni ce
    pipeline ni les gardes amont ne sont une face stream, et ce paquet n'en simule aucune.
    L'appelant appelle -- ou n'appelle pas ;
  * TOUT le calcul du degat : `DamageAppliedResult` est une ENTREE. Le port n'a ni
    `DamagePrediction`, ni PRNG, ni armure ; les quatre valeurs d'etat (`remaining_health`,
    `remaining_armor`, `total_shield`, `number_of_members`) sont fournies resolues, comme dans
    tout `engine/streams/` ;
  * les mutations ECS que `Execute` fait au passage (`ShieldComponent`, `HealthComponent`,
    `ActorStatisticsComponent`, `UnitFlagsComponent$$Add(0xd)`) : elles n'ecrivent rien dans le
    flux. L'axe ECS du degat vit dans `engine/runner/` ;
  * les AUTRES groupes du pipeline de degat -- `GroupType.MachineDamage` (28),
    `GroupType.DamageChain` (29), `GroupType.TileDamage` (27) -- qui sortent d'operations
    distinctes (`MachineDamageOperation$$ExecuteHit` a son propre helper de tags,
    `MachineDamageOperation$$GetMachineHitTags`). Ce module ne porte QUE `GroupType.Damage`.
"""
from __future__ import annotations

from typing import Callable, Mapping, Optional

from .dispatcher import StreamDispatcher
from .group_type import GroupType
from .step_type import StepType

#: `sourceId` du `Group=Damage`. Meme slot de litteral que `START_TURN_SOURCE_ID`
#: (`turn_phase.py`), resolu a l'index 0 -> `""`.
DAMAGE_SOURCE_ID = ""


def apply_damage(events: StreamDispatcher, target_entity_id: int, tags: Mapping[int, int],
                 corps: Optional[Callable[[], None]] = None) -> None:
    """`IdunBattle.Operations.ApplyDamageOperation$$Execute` -- sa face STREAM, et elle seule.

    `tags` est le dictionnaire rendu par `stream_helper.get_damage_tags` : le port le recoit
    construit plutot que de le reconstruire, parce que c'est exactement le decoupage natif --
    `Execute` appelle le slot 9 d'`IStreamHelper` et passe le resultat tel quel a
    `Events.Action`.

    ⚠ L'ACTION EST LA PREMIERE LIGNE DU GROUPE, AVANT `corps`. Le decompile place
    l'`Events.Action` immediatement apres le `StartGroup` ; tout ce qui emet ensuite le fait
    APRES elle et AVANT le `FinishGroup`. Le port place donc `corps` entre les deux, jamais
    avant l'action -- c'est la meme decision d'ordre que `start_turn`, et la contre-epreuve
    `damage_ordre_action` a de quoi mordre.

    `corps = None` signifie un groupe reduit a son action, ce qui est le cas le plus frequent
    (69 des 72 occurrences du corpus confronte)."""
    events.start_group(GroupType.Damage, int(target_entity_id), DAMAGE_SOURCE_ID, None)
    events.action(StepType.UnitDamaged, int(target_entity_id), tags)
    if corps is not None:
        corps()
    events.finish_group()
