"""`UnitExtensions` -- les tags d'ETAT COMPLET d'une unite, mirror 1:1 des TROIS surcharges.

`IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags` existe en trois surcharges, que la
table des methodes du build distingue par leur signature (`frida/methods.tsv`) :

    GetFullStateUpdateTags(unit : IdunBattle.Core.IEntity)                        -> 16 tags
    GetFullStateUpdateTags(activeAbility : ...Components.ActiveAbility)           ->  6 (+2)
    GetFullStateUpdateTags(passiveAbilityComponent : ...Components.TriggeredAbilityComponent,
                           triggeredAbility : ...Enum.TriggeredAbilityType)       ->  3 tags

⚠ CE NE SONT PAS DES `StreamHelper$$Get*Tags`. La fiche parente (`case-477r15` § 5) rangeait ces
tags dans les dix `IdunBattle.Core.Services.StreamHelper$$Get*Tags` ; c'est FAUX. Le producteur
est `UnitExtensions`, et il est PARTAGE par quatre operations -- ce qui rend le port utile bien
au-dela du deploiement :

    IdunBattle.Operations.AddUnitOperation$$Execute
    IdunBattle.Operations.AddMachineOperation$$Execute
    IdunBattle.Operations.ReAddMachineOperation$$Execute
    IdunBattle.Operations.ResurrectUnitOperation$$SendStreamEvents

LA SEQUENCE D'EMISSION, identique dans les quatre (lue verbatim dans `AddUnitOperation$$Execute`
et `AddMachineOperation$$Execute`) :

    Action(StepType.ChangeStats,   unitEntity, GetFullStateUpdateTags(unit))
    foreach (a in ActiveAbilityComponent.Abilities)       // @+0x20
        Action(StepType.ChangeAbility, unitEntity, GetFullStateUpdateTags(a))
    foreach (t in TriggeredAbilityComponent.Abilities)    // @+0x18
        Action(StepType.ChangeAbility, unitEntity, GetFullStateUpdateTags(component, t))

Les ACTIVES d'abord, les DECLENCHEES ensuite -- et l'entite de la ligne est TOUJOURS l'unite,
jamais l'ability.

⚠ `AddMachineOperation` remplace la premiere ligne par `GetFullMachineStateUpdateTags` (une
CINQUIEME fonction, non portee ici) ; ses deux boucles d'ability, elles, appellent bien les
surcharges portees ci-dessous.

CE QUE LE PORT RECOIT, ET POURQUOI. Le natif lit ses valeurs sur des composants ECS
(`unit.GetComponent<T>()`), que le port ne materialise pas -- meme choix que
`stream_helper.get_add_unit_tags`, qui recoit deja `owner_id` / `parent_id` resolus. Les
dataclasses ci-dessous sont donc le SUBSTRAT RESOLU, un champ par lecture native, et la
docstring de chaque champ nomme la lecture qu'il remplace.

⚠ LE NATIF LEVE SI UN COMPOSANT MANQUE. La cascade de `if (component != null)` de la premiere
surcharge se termine, en sortie de la derniere garde, sur le thunk de levee d'exception : un
composant absent ne produit PAS un tag manquant, il fait echouer l'appel. Le port exprime cette
exigence par des champs OBLIGATOIRES -- il n'y a donc rien a decider a l'execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from ..entities.entity_type import EntityType
from ..entities.traits.unit_trait import UnitTrait
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.unit_flag import UnitFlag
from .tag_key import TagKey

#: Les trois porteurs que teste le DERNIER tag de la premiere surcharge. Le natif ecrit
#: `IsPlayDeathAnimationOnHit = !(HasTrait(0x3f6) | TryGetAbility(0x400) | TryGetAbility(0x509))`.
#: Les trois litteraux sont qualifies par le TYPE DECLARE de leur parametre, lu dans
#: `frida/methods.tsv` -- `BaseUnitComponent$$HasTrait(trait : UnitTrait)` et
#: `TriggeredAbilityComponent$$TryGetAbility(abilityType : TriggeredAbilityType)`. Les deux
#: enums portent un membre `FinalJustice` a des ordinaux DIFFERENTS (1014 et 1024) : les
#: confondre etait a portee de main, et seul le type declare les separe.
DEATH_ANIMATION_TRAIT = UnitTrait.FinalJustice                       # 0x3f6
DEATH_ANIMATION_ABILITIES = (TriggeredAbilityType.FinalJustice,      # 0x400
                             TriggeredAbilityType.Bounce)            # 0x509


@dataclass(frozen=True)
class UnitFullState:
    """Le substrat de `GetFullStateUpdateTags(unit)` -- une lecture native par champ.

    L'appariement composant -> `StatType` n'est PAS devine : c'est le meme pointeur de classe
    que le `switch` de `IdunBattle.Entities.UnitExtensions$$GetStatComponent` associe a chaque
    valeur de `StatType` (`case 0` = Attack, `case 2` = Range, `case 1` = Movement, `case 7`
    = BlockChance, `case 8` = BlockDamage, `case 9` = CritChance, `case 10` = CritDamage,
    `case 0x10` = FixedArmor). Les trois composants « fill-up » (sante, armure, membres) n'y
    figurent pas -- ce sont des `FillUpStatComponent`, pas des `StatComponent`."""

    entity_type: int
    """`entity.Type`. La surcharge commence par `if (unit == null || unit.Type != EntityType.Unit)`
    et rend alors un dictionnaire VIDE -- c'est une GARDE, pas une levee."""

    max_health: int
    """`FillUpStatComponent$$get_CurrentMaximumValue()` du composant de SANTE.
    = `MaximumValue(+0x14) + clamp(Modification(+0x28), -Initial(+0x10), IntMax - Initial)`,
    ou l'override de `ValueOverride$$GetOverrideValueWithModification(+0x38)` s'il en porte un."""
    max_armor: int
    """Idem sur le composant d'ARMURE."""
    max_members: int
    """Idem sur le composant de MEMBRES."""
    fixed_armor: int
    """`StatComponent$$get_CurrentValue()` du composant `StatType.FixedArmor`
    = `GetClampedValue(override ?? Initial(+0x10) + Modification(+0x48))`."""

    init_remaining_health: int
    """Champ BRUT `RemainingValue(+0x18)` du composant de sante -- pas un accesseur."""
    init_remaining_armor: int
    """Champ brut `+0x18` du composant d'armure."""
    init_alive_members: int
    """Champ brut `+0x18` du composant de membres."""

    attack: int
    """`get_CurrentValue()` du composant `StatType.Attack`."""
    range: int
    """`get_CurrentValue()` du composant `StatType.Range`."""
    movement: int
    """`get_CurrentValue()` du composant `StatType.Movement`."""
    block_chance: int
    """`get_CurrentValue()` du composant `StatType.BlockChance`."""
    block_damage: int
    """`get_CurrentValue()` du composant `StatType.BlockDamage`."""
    crit_chance: int
    """`get_CurrentValue()` du composant `StatType.CritChance`."""
    crit_damage: int
    """`get_CurrentValue()` du composant `StatType.CritDamage`."""

    turn_finished: bool
    """`UnitFlagsComponent$$Has(UnitFlag.TurnFinished)` -- le litteral natif est `3`, et
    `UnitFlag` est le type declare du parametre `flag` d'`UnitExtensions$$HasFlag`."""

    has_death_animation_trait: bool
    """`BaseUnitComponent$$HasTrait(UnitTrait.FinalJustice)`."""
    has_death_animation_abilities: Sequence[bool] = (False, False)
    """`TriggeredAbilityComponent$$TryGetAbility(t)` pour chaque `t` de
    `DEATH_ANIMATION_ABILITIES`, DANS CET ORDRE. Une sequence plutot que deux booleens : le
    natif les combine par un OU, donc leur nombre est une propriete du decompile, pas du port."""


@dataclass(frozen=True)
class ActiveAbilityState:
    """Le substrat de `GetFullStateUpdateTags(activeAbility)` -- champs de
    `IdunBattle.Entities.Components.ActiveAbility`, offsets RELATIFS lus au decompile."""

    ability_name: int
    """`AbilityName(+0x44)` -- un `ActiveAbilityType`."""
    level: int
    """`get_AbilityState().Level(+0x0)`. L'accesseur rend `OverrideAbilityState` s'il a une
    valeur, sinon `_abilityState` (`ActiveAbility$$get_AbilityState`)."""
    variable_multiplier_percentage: int
    """`get_AbilityState().VariableMultiplierPercentage(+0x4)`."""
    can_still_be_used: bool
    """`CanStillBeUsed(+0x28) != 0`."""
    remaining_cooldown_turns: Optional[int] = None
    """`RemainingCooldownTurns(+0x2c)`, un `Nullable<int>` que le natif ecrit par
    `Nullable$$GetValueOrDefault` -- un Nullable VIDE s'ecrit donc `0`, pas rien."""
    is_disabled: bool = False
    """`IsDisabled(+0x35) != 0`."""
    ammo_cost: Optional[int] = None
    """`AmmoCost(+0x38)`, `Nullable<int>`. `None` = pas de cout en munitions => les DEUX tags
    conditionnels ne sont pas emis. Le natif teste `HasValue` puis lit `get_Value`."""
    has_enough_ammo: bool = True
    """`HasEnoughAmmo(+0x40) != 0` -- ecrit UNIQUEMENT quand `ammo_cost` a une valeur."""


@dataclass(frozen=True)
class TriggeredAbilityState:
    """Le substrat de `GetFullStateUpdateTags(component, triggeredAbility)` : ce que
    `TriggeredAbilityComponent$$GetAbilityState` rend pour l'ability demandee."""

    level: int
    """`AbilityState.Level` (1er champ de la struct rendue)."""
    variable_multiplier_percentage: int
    """`AbilityState.VariableMultiplierPercentage` (2e champ, `+4`)."""


def get_full_state_update_tags(unit: UnitFullState) -> Dict[int, int]:
    """`IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags(unit)` -- 16 tags.

    ⚠ LA GARDE D'ENTREE REND UN DICTIONNAIRE VIDE, ELLE NE LEVE PAS. Sur toute entite qui n'est
    pas une `EntityType.Unit` (une plateforme, un effet, une tuile...) le natif saute directement
    a la construction d'un `Dictionary` neuf et le rend tel quel. L'appelant emet alors une
    `Action=ChangeStats` SANS AUCUN TAG -- c'est-a-dire une ligne bien reelle dans le flux.

    L'ordre d'insertion ci-dessous est celui du DECOMPILE. Il n'a aucun effet observable :
    `StreamCache$$Action` re-trie par ORDINAL (`SortedDictionary<TagKey,int>`). Le conserver est
    ce qui rend le mirror relisible ligne a ligne contre le natif."""
    tags: Dict[int, int] = {}
    if int(unit.entity_type) != int(EntityType.Unit):
        return tags
    tags[TagKey.UnitStats_MaxHealth] = int(unit.max_health)
    tags[TagKey.UnitStats_MaxArmor] = int(unit.max_armor)
    tags[TagKey.UnitStats_MaxMembers] = int(unit.max_members)
    tags[TagKey.UnitStats_FixedArmor] = int(unit.fixed_armor)
    tags[TagKey.UnitStats_InitRemainingHealth] = int(unit.init_remaining_health)
    tags[TagKey.UnitStats_InitRemainingArmor] = int(unit.init_remaining_armor)
    tags[TagKey.UnitStats_InitAliveMembers] = int(unit.init_alive_members)
    tags[TagKey.UnitStats_Attack] = int(unit.attack)
    tags[TagKey.UnitStats_Range] = int(unit.range)
    tags[TagKey.UnitStats_Movement] = int(unit.movement)
    tags[TagKey.UnitStats_BlockChance] = int(unit.block_chance)
    tags[TagKey.UnitStats_BlockDamage] = int(unit.block_damage)
    tags[TagKey.UnitStats_CritChance] = int(unit.crit_chance)
    tags[TagKey.UnitStats_CritDamage] = int(unit.crit_damage)
    tags[TagKey.UnitStats_TurnFinished] = 1 if unit.turn_finished else 0
    # `(hasTrait | hasAbilityA | hasAbilityB) ^ 1` : un OU sur les trois porteurs, NIE.
    porte = bool(unit.has_death_animation_trait) or any(unit.has_death_animation_abilities)
    tags[TagKey.UnitStats_IsPlayDeathAnimationOnHit] = 0 if porte else 1
    return tags


def get_full_state_update_tags_for_active(active: ActiveAbilityState) -> Dict[int, int]:
    """`GetFullStateUpdateTags(activeAbility)` -- 6 tags, +2 si l'ability a un cout en munitions.

    ⚠ LES DEUX TAGS CONDITIONNELS PORTENT UN NOM TROMPEUR. Ce sont
    `UnitStats_TriggeredAbility_AmmoCost` (29) et `_EnoughAmmo` (30) -- des tags nommes
    « Triggered » ecrits par la surcharge ACTIVE. Le decompile est formel (`0x1d` puis `0x1e`
    dans le bloc garde par `Nullable$$get_HasValue` du champ `AmmoCost`), et un port qui
    corrigerait ce nom « evident » ecrirait des ordinaux faux.

    ⚠ `remaining_cooldown_turns` passe par `GetValueOrDefault` : le tag est TOUJOURS emis, a `0`
    quand le Nullable est vide. C'est l'inverse du couple munitions, ou c'est la PRESENCE du
    Nullable qui decide de l'emission."""
    tags: Dict[int, int] = {}
    tags[TagKey.UnitStats_ActiveAbility_Id] = int(active.ability_name)
    tags[TagKey.UnitStats_ActiveAbility_Level] = int(active.level)
    tags[TagKey.UnitStats_ActiveAbility_VariableMultiplierPercentage] = int(
        active.variable_multiplier_percentage)
    tags[TagKey.UnitStats_ActiveAbility_CanStillBeUsed] = 1 if active.can_still_be_used else 0
    tags[TagKey.UnitStats_ActiveAbility_RemainingCooldownTurns] = int(
        active.remaining_cooldown_turns or 0)
    tags[TagKey.UnitStats_ActiveAbility_IsDisabled] = 1 if active.is_disabled else 0
    if active.ammo_cost is not None:
        tags[TagKey.UnitStats_TriggeredAbility_AmmoCost] = int(active.ammo_cost)
        tags[TagKey.UnitStats_TriggeredAbility_EnoughAmmo] = 1 if active.has_enough_ammo else 0
    return tags


def get_full_state_update_tags_for_triggered(
        triggered_ability: int, state: TriggeredAbilityState) -> Dict[int, int]:
    """`GetFullStateUpdateTags(passiveAbilityComponent, triggeredAbility)` -- 3 tags.

    ⚠ L'ORDRE DES PARAMETRES EST INVERSE PAR RAPPORT AU NATIF, et c'est delibere : le natif prend
    le COMPOSANT puis le type, et lit l'etat par `TriggeredAbilityComponent$$GetAbilityState`. Le
    port ne materialise pas le composant -- il recoit l'etat DEJA resolu, donc le seul argument
    qui reste « natif » est le type. Le nommer en premier evite de laisser croire que le second
    est un composant."""
    return {
        TagKey.UnitStats_TriggeredAbility_Id: int(triggered_ability),
        TagKey.UnitStats_TriggeredAbility_Level: int(state.level),
        TagKey.UnitStats_TriggeredAbility_VariableMultiplierPercentage: int(
            state.variable_multiplier_percentage),
    }
