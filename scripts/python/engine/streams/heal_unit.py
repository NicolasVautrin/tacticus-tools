"""La face STREAM du pas `Action=HealInfo` -- `IdunBattle.Operations.HealUnitOperation$$Execute`
(#477-r39).

C'est la troisieme des familles que `#477-r22-r1` avait laissees hors perimetre dans les couples
`Action=PrepareTurn` + `Group=StartTurn` (`Group=Damage` est entree avec `#477-r34`,
`Group=ResurrectUnit` reste ouverte). Elle ne sort ni du pipeline de tour ni de celui du degat :
elle sort du pipeline de SOIN, appele depuis le behaviour DSL d'une ability (le flux la montre
sous `Group=Ability_Power Source=MedicusMinistorum`).

LA SIGNATURE, publiee par `data/symbols/<build>/frida/methods.tsv`
------------------------------------------------------------------

    IdunBattle.Operations.HealUnitOperation.Execute(
        caster        : IdunBattle.Core.IEntity,
        target        : IdunBattle.Core.IEntity,
        amount        : System.Int32,
        scope         : IdunBattle.Entities.Enum.HealScope,
        removeEffects : System.Boolean,
        abilityOrEffect: System.Nullable<IdunBattle.Core.AbilityOrEffect>)
      -> IdunBattle.Core.OperationResult

⚠ LES NOMS GHIDRA DES PARAMETRES SONT DECALES D'UN CRAN, ET LES PRENDRE AU SERIEUX INVERSE LE
SOIN. Le retour est un `ValueType` de 0x40 octets, donc `rcx` porte le pointeur de retour (sret),
`rdx` le vrai `this`, et tout glisse : ce que Ghidra nomme `target` est le **caster**, ce qu'il
nomme `amount` est la **cible**, ce qu'il nomme `abilityOrEffect` est le booleen `removeEffects`.
Le recoupement est interne et tient en trois points : (a) `if (<ghidra:abilityOrEffect>)` garde
l'appel qui produit `UnitStats_RemovedNegativeUnitEffects` -- c'est donc bien `removeEffects` ;
(b) `Tag=Caster_Id` recoit l'identifiant de `<ghidra:target>` ; (c) les 0x1c octets de
`<ghidra:in_stack_00000040>` sont recopies tels quels dans les deux declencheurs post-soin, ce
qui est la taille d'un `Nullable<AbilityOrEffect>`.

LA FACE STREAM, lue verbatim dans `HealUnitOperation$$Execute`
--------------------------------------------------------------

    var tags = new Dictionary<TagKey, int>();
    tags.Add(UnitStats_RemainingHealth /*5*/,                 <composant>.<+0x18>);
    tags.Add(UnitStats_RemovedNegativeUnitEffects /*7*/,      removedNegativeUnitEffects);
    tags.Add(UnitStats_WasWoundedBeforeHeal /*8*/,            wasWoundedBeforeHeal);
    tags.Add(Amount /*0xe1*/,                                 result.<+0x04>);
    tags.Add(Caster_Id /*0xb4*/,   <IEntity slot 0>(caster));
    tags.Add(UnitStats_NumberOfMembers /*100*/,
             IdunBattle.Entities.UnitExtensions$$GetNumberOfMembers(target));
    Events.Action(StepType.HealInfo /*5*/, <IEntity slot 0>(target), tags);

⚠ IL N'Y A PAS DE `StreamHelper$$GetHealTags`, ET C'EST MESURE. Le build porte DIX
`IdunBattle.Core.Services.StreamHelper$$Get*Tags` (`AddUnit`, `ActiveAbilityStateUpdate`,
`Damage`, `RefreshEffect`, `ResurrectUnit`, `AddOrUpdateShield`, `AddScore`, `RemoveShield`,
`ReviveUnit`, `UpdateActiveAbilityModification`) -- aucune de soin. Le dictionnaire est construit
INLINE dans l'operation. La separation `get_heal_tags` / `heal_unit` ci-dessous est donc une
DECOUPE DU PORT, pas une frontiere native : elle existe pour que le dictionnaire soit mutable a
part dans les contre-epreuves. C'est l'inverse d'`apply_damage`, ou la frontiere EST native
(`ApplyDamageOperation$$Execute` appelle le slot 9 d'`IStreamHelper` et passe le resultat tel
quel).

⚠ LES SIX `Add` SONT INCONDITIONNELS, ET C'EST UNE LECTURE DE STRUCTURE, PAS UNE HYPOTHESE. Le
decompile enveloppe les deux derniers et l'emission dans un `if (<caster> != null)` -- exactement
la forme du `if (caster != null)` de `GetDamageTags` autour d'`Attacker_Id`. Les deux ne sont
PAS la meme chose, et le discriminant est le CHEMIN DE SORTIE :

  * dans `GetDamageTags`, le `if` est suivi de code qui s'execute dans les DEUX cas
    (`Add(Target_Id)`, `Add(Amount)`, ... puis `return tags`) -> c'est un `if` du source C#,
    et le port de `#477-r34` a raison de le porter ;
  * ici, aucune branche ne rejoint un `return` normal : l'echec de chacun de ces tests tombe sur
    le helper de levee d'IL2CPP (`FUN_1801f51f0`, marque « does not return »). Ce sont donc les
    NULL-CHECKS generes par le codegen autour de `caster.Id`, pas un `if` du source.

Ecrire ici la conditionnalite de `GetDamageTags` produirait, sur un caster nul, une
`Action=HealInfo` a quatre tags que le natif n'emet JAMAIS -- il leve.

CE QUE CE MODULE NE PORTE PAS, ET QUI EST NOMME
-----------------------------------------------
  * LES DEUX GARDES qui suppriment l'emission, toutes deux LUES et toutes deux de vrais `if`
    (elles rendent le `OperationResult` par un `return` normal) :

        if (!AttackQuery.<slot 0x11>(caster, target, scope, removeEffects)) return result;
        ...
        if (!wasWounded && healedAmount < 1 && removedNegativeUnitEffects < 1
            && !UnitExtensions.HasFlag(caster, 0x17))                        return result;

    La seconde est le seul endroit ou les trois grandeurs du dictionnaire se relisent ensemble :
    un soin qui ne soigne rien, sur une cible intacte, sans effet retire, n'ecrit rien. Le port
    ne les simule pas -- il n'a ni `AttackQuery` ni etat ECS -- et l'appelant appelle, ou pas ;
  * TOUT le calcul du soin : `DamagePredictionQuery.<slot 1>(caster, casterMainTile, target,
    amount, scope)` puis `FillUpStatComponent$$FillUp`, avec la remise a zero quand
    `EntityExtensions$$HasEffect(target, state, 0x4f, null)` -- `healedAmount`,
    `wasWoundedBeforeHeal` et `remainingHealth` sont des ENTREES, comme dans tout
    `engine/streams/` ;
  * les mutations ECS que l'operation fait au passage (`ActorStatisticsComponent$$
    AddRestoreHealthAction`, les compteurs `+0xc8` / `+0xd4` / `+0xe4`) : elles n'ecrivent rien
    dans le flux ;
  * les QUATRE appels POST-EMISSION -- trois declencheurs d'`EventTriggerType` (`0x1e` sur la
    cible, `0x2b` puis, si `removeEffects`, `0x2c` sur le caster) et un
    `RefreshEffects(RefreshEffectOptions{3, null})`. Ils PEUVENT emettre, et ce qu'ils emettent
    apparait APRES l'`Action=HealInfo` a la MEME profondeur -- `HealUnitOperation` n'ouvre aucun
    groupe. Le port les recoit donc comme des sous-arbres frères, jamais comme un corps.
"""
from __future__ import annotations

from typing import Dict, Mapping

from .dispatcher import StreamDispatcher
from .step_type import StepType
from .tag_key import TagKey


def get_heal_tags(caster_entity_id: int, target_entity_id: int, remaining_health: int,
                  removed_negative_unit_effects: int, was_wounded_before_heal: bool,
                  amount: int, number_of_members: int) -> Dict[int, int]:
    """LES SIX `Dictionary$$Add` d'`IdunBattle.Operations.HealUnitOperation$$Execute`, dans leur
    ORDRE D'INSERTION.

    ⚠ L'ORDRE D'INSERTION N'EST PAS L'ORDRE D'ECRITURE, comme partout dans ce paquet :
    `IdunBattle.BattleStream.Loggers.StreamCache$$Action` recopie dans un
    `SortedDictionary<TagKey,int>` et re-trie par ORDINAL. Le flux ecrit donc
    `5, 7, 8, 100, 180, 225` la ou le natif insere `5, 7, 8, 225, 180, 100`. L'ordre ci-dessous
    est celui du DECOMPILE -- il n'a aucun effet observable, et le conserver est ce qui rend le
    mirror relisible ligne a ligne.

    ⚠ `target_entity_id` N'ALIMENTE AUCUN TAG, et c'est voulu : le pendant de `Tag=Target_Id` du
    `Group=Damage` N'EXISTE PAS ici. L'identifiant de la cible n'est ecrit qu'a UN seul endroit,
    l'entite de l'`Events.Action` -- c'est pourquoi il est parametre de `heal_unit` et pas de
    cette fonction. Un port qui ajouterait un `Tag=Target_Id` ecrirait une ligne de plus.

    ⚠ `number_of_members` VIENT D'UN HELPER NOMME, pas d'un offset. Le natif appelle
    `IdunBattle.Entities.UnitExtensions$$GetNumberOfMembers(target)`, la ou
    `StreamHelper$$GetDamageTags` lit `<composant>.<+0x18>` pour la MEME cle. Deux canaux, une
    grandeur : le port les recoit tous deux resolus (borne (c)).

    ⚠ `amount` EST `result.<+0x04>`, PAS `result.<+0x00>`. `GetDamageTags` ecrit son `Amount`
    depuis `result.<+0x00>` ; ici le decompile lit les 32 bits HAUTS du premier qword du
    `OperationResult`, c'est-a-dire le champ que l'operation vient d'incrementer
    (`result.<+0x04> += healedAmount`). Les deux cles portent le meme nom et NE lisent pas le
    meme champ."""
    tags: Dict[int, int] = {}
    tags[int(TagKey.UnitStats_RemainingHealth)] = int(remaining_health)
    tags[int(TagKey.UnitStats_RemovedNegativeUnitEffects)] = int(removed_negative_unit_effects)
    tags[int(TagKey.UnitStats_WasWoundedBeforeHeal)] = 1 if was_wounded_before_heal else 0
    tags[int(TagKey.Amount)] = int(amount)
    tags[int(TagKey.Caster_Id)] = int(caster_entity_id)
    tags[int(TagKey.UnitStats_NumberOfMembers)] = int(number_of_members)
    return tags


def heal_unit(events: StreamDispatcher, target_entity_id: int,
              tags: Mapping[int, int]) -> None:
    """L'EMISSION d'`IdunBattle.Operations.HealUnitOperation$$Execute` -- une `Action=` NUE :

        Events.Action(StepType.HealInfo /*5*/, <IEntity slot 0>(target), tags);

    ⚠ AUCUN GROUPE N'EST OUVERT, et c'est ce qui distingue cette famille des deux precedentes.
    `ApplyDamageOperation` encadre son action d'un `StartGroup`/`FinishGroup` ; le decompile de
    `HealUnitOperation` ne contient aucun appel d'ouverture de groupe. Le `Group=Ability_Power`
    que le flux montre autour vient de l'ETAGE DU DESSUS
    (`EvaluateTriggerOperation$$EvaluateAbilityTrigger`, `engine/streams/evaluate_trigger.py`),
    qui enveloppe tout le behaviour de l'ability.

    ⚠ L'ENTITE EST CELLE DE LA CIBLE, PAS CELLE DU CASTER. Les deux sont dans la meme fonction et
    a un argument d'ecart ; le flux les montre DIFFERENTES (`Action=HealInfo Entity=83` avec
    `Tag=Caster_Id:81`). Les intervertir laisserait un flux de meme forme, de meme longueur, et
    faux."""
    events.action(int(StepType.HealInfo), int(target_entity_id), tags)
