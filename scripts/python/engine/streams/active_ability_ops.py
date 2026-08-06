"""La face STREAM d'`IdunBattle.Operations.RemoveActiveAbilityOperation` et
`IdunBattle.Operations.AddActiveAbilityOperation` -- l'echange d'ability active.

C'est le second artefact de `#477-r21-r1`. Sur le flux temoin il apparait comme un
`Group=Ability_Power ... Source=TwistedScience` dont les DEUX enfants directs ne sont ni un
`Effect_Refresh` ni une action d'effet :

    Group=Ability_Power Entity=63 Source=TwistedScience InitialTarget=
        Action=ChangeStats Entity=63
            Tag=UnitStats_RemoveActiveAbility:18
        Action=ChangeAbility Entity=63
            Tag=UnitStats_ActiveAbility_Id:1167
            ...
    Finish_Group

LA CHAINE, lue de bout en bout et NOMMEE :

    IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger    <- ouvre le groupe
      ability.<slot 4>(...)                                                  <- l'execution
    -> IdunBattleLogic.Entities.Abilities.Triggered.Loki.TwistedScienceAbility$$CreateBehaviour
         DSLBehaviors$$RemoveActiveAbility(selectors.Caster, ActiveAbilityType 0x12)
           & DSLBehaviors$$AddActiveAbility(selectors.Caster, ActiveAbilityType 0x48f,
                                            abilityState)
    -> IdunBattle.Operations.RemoveActiveAbilityOperation$$Execute(target, activeAbilityType)
    -> IdunBattle.Operations.AddActiveAbilityOperation$$Execute(target, activeAbilityType,
                                                                abilityState)

⚠ LES DEUX LITTERAUX SONT DANS LE `CreateBehaviour`, PAS DANS LE FLUX. Le decompile de
`TwistedScienceAbility$$CreateBehaviour` passe `0x12` a `RemoveActiveAbility` et `0x48f` a
`AddActiveAbility` -- soit exactement les `18` et `1167` que le flux ecrit. C'est le meme
recoupement que `Source=` / `Effect_SourceTriggeredAbility` du cran precedent : deux canaux
natifs distincts qui concordent, ce qui CONFIRME la lecture sans la remplacer.

⚠ LES SIX TAGS DE `ChangeAbility` NE SONT PAS `GetFullStateUpdateTags(activeAbility)`, ET LES
CONFONDRE SERAIT FAUX. `AddActiveAbilityOperation$$Execute` INLINE son propre dictionnaire ; la
surcharge de `IdunBattle.Entities.UnitExtensions` portee par `unit_extensions.py` en ecrit les
memes six PLUS deux conditionnels (`UnitStats_TriggeredAbility_AmmoCost` et `_EnoughAmmo`, sous
`AmmoCost.HasValue`). Reutiliser l'autre fonction ajouterait donc deux lignes que le natif
n'ecrit pas des qu'une ability porte un cout en munitions -- une divergence qui ne se verrait
que sur une Machine of War. Les deux producteurs restent separes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .dispatcher import StreamDispatcher
from .step_type import StepType
from .tag_key import TagKey


@dataclass(frozen=True)
class AddedActiveAbility:
    """Ce que `AddActiveAbilityOperation$$Execute` LIT sur l'`ActiveAbility` fraichement ajoutee.

    Les offsets RELATIFS sont ceux du decompile, et ce sont les MEMES que ceux de
    `unit_extensions.ActiveAbilityState` -- c'est la meme classe native
    `IdunBattle.Entities.Components.ActiveAbility`. Ce qui differe est la LISTE des champs lus,
    pas leur emplacement."""

    ability_name: int
    """`AbilityName(+0x44)` -- un `ActiveAbilityType`. Note : le natif le relit sur l'instance
    RANGEE dans le composant (`Abilities[activeAbilityType]`), pas sur l'argument."""
    level: int
    """`get_AbilityState().Level(+0x00)`."""
    variable_multiplier_percentage: int
    """`get_AbilityState().VariableMultiplierPercentage(+0x04)`."""
    can_still_be_used: bool
    """`CanStillBeUsed(+0x28) != 0`."""
    remaining_cooldown_turns: Optional[int] = None
    """`RemainingCooldownTurns(+0x2c)`, `Nullable<int>` lu par `Nullable$$GetValueOrDefault` :
    le tag est TOUJOURS emis, a `0` quand le Nullable est vide."""
    is_disabled: bool = False
    """`IsDisabled(+0x35) != 0`."""


def remove_active_ability(events: StreamDispatcher, target_entity_id: int,
                          active_ability_type: int) -> None:
    """`IdunBattle.Operations.RemoveActiveAbilityOperation$$Execute(target, activeAbilityType)`.

        component = target.GetComponent<ActiveAbilityComponent>();
        if (!component.Abilities.Contains(activeAbilityType)) return;     <- SORTIE SILENCIEUSE
        component.Abilities.Remove(activeAbilityType);
        tags = new Dictionary<TagKey,int>();
        tags.Add(TagKey.UnitStats_RemoveActiveAbility /*0x74*/, activeAbilityType);
        Events.Action(StepType.ChangeStats /*0xc*/, target.<Id>, tags);

    ⚠ UN SEUL TAG, ET C'EST CE QUI LA DISTINGUE DES DEUX AUTRES `ChangeStats` DU FLUX : celle de
    `transform_unit` porte toujours `UnitStats_Transformed`, celle d'`AddUnitOperation` porte
    l'etat complet (16 tags). Un port qui rangerait les trois sous une seule fonction perdrait
    cette separation.

    ⚠ LA GARDE `Contains` N'EST PAS PORTEE, ET ELLE EST LUE. Elle depend de l'etat ECS : une
    ability absente fait sortir SANS emettre. L'appelant qui ne sait pas si l'unite la porte ne
    doit donc pas appeler cette fonction -- c'est la meme frontiere que pour les deux gardes
    d'`EvaluateAbilityTrigger` (`#477-r21-r2`)."""
    events.action(StepType.ChangeStats, target_entity_id,
                  {int(TagKey.UnitStats_RemoveActiveAbility): int(active_ability_type)})


def get_add_active_ability_tags(ability: AddedActiveAbility) -> Dict[int, int]:
    """Les SIX tags qu'`AddActiveAbilityOperation$$Execute` inline, dans l'ordre du decompile.

        tags.Add(0x12 /*UnitStats_ActiveAbility_Id*/,                    ability.AbilityName);
        tags.Add(0x18 /*..._Level*/,                     ability.AbilityState.Level);
        tags.Add(0x19 /*..._VariableMultiplierPercentage*/,
                                     ability.AbilityState.VariableMultiplierPercentage);
        tags.Add(0x13 /*..._CanStillBeUsed*/,            ability.CanStillBeUsed != 0);
        tags.Add(0x14 /*..._RemainingCooldownTurns*/,
                                     Nullable.GetValueOrDefault(ability.RemainingCooldownTurns));
        tags.Add(0x15 /*..._IsDisabled*/,                ability.IsDisabled != 0);

    L'ordre d'insertion n'est PAS observable (`StreamCache$$Action` recopie dans un
    `SortedDictionary<TagKey,int>`, donc le flux ecrit par ORDINAL) ; il est conserve pour que
    le mirror se relise ligne a ligne contre le natif."""
    return {
        int(TagKey.UnitStats_ActiveAbility_Id): int(ability.ability_name),
        int(TagKey.UnitStats_ActiveAbility_Level): int(ability.level),
        int(TagKey.UnitStats_ActiveAbility_VariableMultiplierPercentage): int(
            ability.variable_multiplier_percentage),
        int(TagKey.UnitStats_ActiveAbility_CanStillBeUsed): 1 if ability.can_still_be_used else 0,
        int(TagKey.UnitStats_ActiveAbility_RemainingCooldownTurns): int(
            ability.remaining_cooldown_turns or 0),
        int(TagKey.UnitStats_ActiveAbility_IsDisabled): 1 if ability.is_disabled else 0,
    }


def add_active_ability(events: StreamDispatcher, target_entity_id: int,
                       ability: AddedActiveAbility) -> None:
    """`IdunBattle.Operations.AddActiveAbilityOperation$$Execute(target, activeAbilityType,
    abilityState)` -- sa seule face stream.

        if (component.Abilities.Contains(activeAbilityType)) return;        <- GARDE
        if (StaticBattleRules.ActiveAbility.IsRegularAttack(activeAbilityType))
            processor.<slot 0x2a>(target, UnitExtensions$$GetNormalAttackType(target));
        component.Add(activeAbilityType, abilityState, null);
        Events.Action(StepType.ChangeAbility /*0xd*/, target.<Id>, tags);   <- LA LIGNE
        processor.<slot 0x51>(target, target, target, EventTriggerType.<0x31>,
                              (AbilityOrEffect)activeAbilityType);
        AddDerivedAbilities(target, activeAbilityType);

    ⚠ TROIS CHOSES SONT LUES ET NON PORTEES, ET CHACUNE PEUT AJOUTER DU FLUX. Le `<slot 0x2a>`
    (branche attaque normale), le `<slot 0x51>` -- c'est le MEME `EvaluateAbilities` qui ouvre
    tout le bloc 1 (`evaluate_trigger`), donc une re-entree possible -- et `AddDerivedAbilities`.
    Sur le seul cas confronte (`TwistedScience`), le groupe se ferme immediatement apres la
    ligne : les trois n'ecrivent rien. C'est une observation, pas une regle -- le port ne les
    materialise pas, l'appelant qui saurait qu'ils produisent quelque chose l'emettrait
    lui-meme, apres."""
    events.action(StepType.ChangeAbility, target_entity_id, get_add_active_ability_tags(ability))
