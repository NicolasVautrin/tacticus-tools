"""La face STREAM d'`IdunBattle.Operations.TransformUnitOperation` -- l'`Action=ChangeStats`
d'une MODIFICATION DE STAT.

C'est le premier des deux artefacts de `#477-r21-r1`, et il n'a AUCUN rapport avec
`RefreshEffectsOperation` : il vit dans une operation distincte, atteinte par une feuille DSL.
La chaine, lue de bout en bout :

    IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets
      -> la DERNIERE closure de la `List<Action> eventActions` (cf. plus bas)
    -> IdunBattle.Operations.RefreshEffectsOperation$$ApplyEffectsForTargets
         foreach (target in targetsToAdd) { effect.<slot 0xe>(owner, target, effectEntity); ... }
    -> IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification(owner, target, effect)
         construit un arbre DSL et l'execute :
           IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat(
               targets   = DSLSelectors$$Entity(config.<+0x90>, target),
               stat      = new Stat(<statType>, StatPart.Modification /*5*/),
               amount    = DSLFormulas$$Direct(config.<+0x80>, <statPart>),
               modifier  = DSLSelectors$$Entity(config.<+0x90>, effect))
    -> IdunBattle.Operations.TransformUnitOperation$$Execute(unit, statModifiers, isHidden)
    -> Events.Action(StepType.ChangeStats /*0xc*/, unit.<Id>, tags)          <- LA LIGNE

⚠ POURQUOI LA LIGNE TOMBE *DANS* LE `Group=Effect_Refresh`, ET C'EST LU, PAS OBSERVE.
`ApplyEffectsForTargets` emet IMMEDIATEMENT ; ce qui la place dans le groupe, c'est que
`UpdateEffectTargets` ne l'appelle pas directement -- elle en fait la DERNIERE entree d'une
`List<Action>` DIFFEREE, invoquee par `GenerateEventGroup` entre le `StartGroup` et le
`FinishGroup`. Les six entrees de cette liste, dans l'ordre du decompile :

    (1) ActivateEffect       si `currentTargets.Count == 0 && desiredTargets.Count > 0`
    (2) RemoveTargetsFromEffect  -> les `LoseEffect`
    (3) AddTargetsToEffect       -> les `ReceiveEffect`
    (4) DeactivateEffect     si `currentTargets.Count > 0 && desiredTargets.Count == 0`
    (5) RevertEffectsForTargets  si `targetsToRemove.Count > 0`   -> `ReverseModification`
    (6) ApplyEffectsForTargets   si `targetsToAdd.Count > 0`      -> CE MODULE

C'est ce qui explique, sans rien deviner, que le flux temoin ecrive TOUJOURS le `ChangeStats`
APRES les `ReceiveEffect` du meme groupe. `UpdateEffectTargets` elle-meme n'est PAS portee ici :
elle est nommement dans le perimetre de `#477-r21-r2`.

⚠ LE RACCORD AVEC LE VOLET A DE `#477-r21-r2` EST OUVERT, ET LES DEUX COTES LE NOMMENT.
`engine/runner/operations/refresh_effects.update_effect_targets` (volet A, livre) rend deja le
PLAN complet dans l'ordre natif, `RefreshAction(ACTION_REVERT, ...)` et
`RefreshAction(ACTION_APPLY, ...)` compris ; `engine/streams/refresh_effects.bind_refresh_actions`
les IGNORE explicitement et renvoie ici. Il manque donc UNE seule chose : que `bind_refresh_actions`
traduise `ACTION_APPLY` en un `transform_unit(events, <cible>, <modificateurs>)` de ce module. Ce
qui bloque n'est pas la forme -- c'est la DONNEE : les `StatModifierSetup` demandent des lectures
`UnitExtensions$$GetStat` que la couche decision ne produit pas encore (meme manque que
`#477-r26`). `ACTION_REVERT`, lui, sort d'un artefact que cette tranche n'a PAS lu
(`RevertEffectsForTargets` -> le slot d'interface `IEffect+0xf`, `ReverseModification`), et il
n'a aucune occurrence sur les quatre flux temoins.

CE QUE CE MODULE EST -- ET N'EST PAS. Seule la FACE STREAM. `TransformUnitOperation$$Execute`
fait AUSSI trois choses qui ne sont pas ici : elle clampe les modifications
(`ClampModifiers` -> `StatComponent$$ModificationThatCanBeAdded` sur `StatPart.Modification`),
elle les APPLIQUE (`UnitExtensions$$ApplyStatModifiers`), et elle re-declenche des abilities
(`OrderedSet<EventTriggerType>` accumule par les `Add*Tags`, puis un `<slot 0x51>` par
declencheur, puis `<slot 0x2f>`, puis `<slot 0x62>` si l'unite vient de mourir). Le port recoit
donc les VALEURS deja resolues, exactement comme `EffectSetup` recoit les siennes.

LES DEUX TABLES SONT LUES VERBATIM, ET ELLES SE RECOUPENT TOUTES SEULES. Les 15 entrees de
`MOD_STAT_TRANSFORM_CONFIG` viennent de `IdunBattle.Operations.TransformUnitOperation$$.cctor`,
l'unique entree de `FILL_STAT_TRANSFORM_CONFIG` de
`IdunBattle.Operations.TransformUnitOperation$$.ctor`. L'ORDRE des champs de chaque struct est
donne par la signature de son ctor dans `frida/methods.tsv` --
`ModStatTransformConfig..ctor(currentKey, modificationKey, modificationChangeKey,
modificationEntityKey, overrideKey, overrideEntityKey, overrideIsModifiableKey,
eventTriggerType)` -- et il est CONFIRME par deux canaux independants :

  * le NOM des `TagKey` obtenus : `StatType.Attack` rend `UnitStats_Attack`,
    `UnitStats_Attack_Modification`, `..._Modification_Change`, `..._Modification_Entity`,
    `..._Override`, `..._Override_Entity`, `..._Override_IsModifiable` -- dans cet ordre ;
  * le NOM de l'`EventTriggerType` : `StatType.Attack` porte `AttackChanged` (55),
    `StatType.BlockDamage` porte `BlockDamageChanged` (56), et l'entree fill-up
    `StatType.Health` porte `HealthChanged` (30). Trois concordances semantiques qu'aucune
    erreur de lecture d'offset ne produirait.

⚠ L'ORDRE DES ORDINAUX N'EST PAS L'ORDRE DES CHAMPS -- et c'est ce qui rend la table
NECESSAIRE. `UnitStats_Movement_*` numerote `Modification`(48), `_Entity`(49), `_Change`(50),
mais `UnitStats_MaxHealth_*` numerote `Modification`(10), `_Change`(11), `_Entity`(12) : les
deux familles inversent les deux derniers. Deduire les cles d'un `StatType` par arithmetique
sur les ordinaux ecrirait donc des tags faux sur la moitie des stats.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from ..dsl.event_trigger_type import EventTriggerType
from ..entities.stats import StatPart, StatType
from .dispatcher import StreamDispatcher
from .step_type import StepType
from .tag_key import TagKey

#: `int.MinValue`, ecrit tel quel par les branches `ResetModification` / `RemoveOverride` comme
#: valeur SENTINELLE d'un retrait. Le decompile porte le litteral `0x80000000`.
INT_MIN = -2147483648


@dataclass(frozen=True)
class ModStatTransformConfig:
    """`IdunBattle.Operations.TransformUnitOperation.ModStatTransformConfig`.

    Ordre des champs = ordre des parametres du ctor, lu dans `frida/methods.tsv` ; offsets
    RELATIFS `+0x00` .. `+0x18` puis le `Nullable<EventTriggerType>` a `+0x1c`."""

    current_key: int
    modification_key: int
    modification_change_key: int
    modification_entity_key: int
    override_key: int = TagKey.UnitStats_Unimplemented
    override_entity_key: int = TagKey.UnitStats_Unimplemented
    override_is_modifiable_key: int = TagKey.UnitStats_Unimplemented
    event_trigger_type: Optional[int] = None
    """N'INTERVIENT PAS DANS L'EMISSION. Le natif l'accumule dans un `OrderedSet` pour
    re-declencher des abilities APRES la ligne. Conserve parce que le `.cctor` l'ecrit, et
    parce que son nom recoupe la lecture des offsets."""


@dataclass(frozen=True)
class FillStatTransformConfig:
    """`IdunBattle.Operations.TransformUnitOperation.FillStatTransformConfig`.

    Deux champs de plus que la precedente (`remainingKey` en tete, et un second
    `Nullable<EventTriggerType>` en queue), donc TOUS les offsets suivants sont decales de 4.
    C'est pourquoi `AddModificationTags` existe en DEUX surcharges qui ne different que par
    cela."""

    remaining_key: int
    max_key: int
    modification_key: int
    modification_change_key: int
    modification_entity_key: int
    override_key: int = TagKey.UnitStats_Unimplemented
    override_entity_key: int = TagKey.UnitStats_Unimplemented
    override_is_modifiable_key: int = TagKey.UnitStats_Unimplemented
    event_trigger_type: Optional[int] = None
    modification_event_trigger_type: Optional[int] = None


#: `IdunBattle.Operations.TransformUnitOperation$$.cctor` -- 15 entrees, dans l'ordre du
#: decompile. Les cles absentes (`UnitStats_Unimplemented`, ordinal 0) sont ECRITES `0` par le
#: natif et filtrees par `add_tag_if_implemented` : c'est le mecanisme « non implemente », pas
#: un trou du port.
MOD_STAT_TRANSFORM_CONFIG: Dict[int, ModStatTransformConfig] = {
    StatType.ATTACK: ModStatTransformConfig(
        TagKey.UnitStats_Attack, TagKey.UnitStats_Attack_Modification,
        TagKey.UnitStats_Attack_Modification_Change,
        TagKey.UnitStats_Attack_Modification_Entity,
        TagKey.UnitStats_Attack_Override, TagKey.UnitStats_Attack_Override_Entity,
        TagKey.UnitStats_Attack_Override_IsModifiable, EventTriggerType.AttackChanged),
    StatType.MOVEMENT: ModStatTransformConfig(
        TagKey.UnitStats_Movement, TagKey.UnitStats_Movement_Modification,
        TagKey.UnitStats_Movement_Modification_Change,
        TagKey.UnitStats_Movement_Modification_Entity,
        TagKey.UnitStats_Movement_Override, TagKey.UnitStats_Movement_Override_Entity,
        TagKey.UnitStats_Movement_Override_IsModifiable, None),
    StatType.RANGE: ModStatTransformConfig(
        TagKey.UnitStats_Range, TagKey.UnitStats_Range_Modification,
        TagKey.UnitStats_Range_Modification_Change,
        TagKey.UnitStats_Range_Modification_Entity),
    StatType.BLOCK_CHANCE: ModStatTransformConfig(
        TagKey.UnitStats_BlockChance, TagKey.UnitStats_BlockChance_Modification,
        TagKey.UnitStats_BlockChance_Modification_Change,
        TagKey.UnitStats_BlockChance_Modification_Entity,
        TagKey.UnitStats_BlockChance_Override, TagKey.UnitStats_BlockChance_Override_Entity,
        TagKey.UnitStats_BlockChance_Override_IsModifiable, None),
    StatType.BLOCK_DAMAGE: ModStatTransformConfig(
        TagKey.UnitStats_BlockDamage, TagKey.UnitStats_BlockDamage_Modification,
        TagKey.UnitStats_BlockDamage_Modification_Change,
        TagKey.UnitStats_BlockDamage_Modification_Entity,
        TagKey.UnitStats_Unimplemented, TagKey.UnitStats_Unimplemented,
        TagKey.UnitStats_Unimplemented, EventTriggerType.BlockDamageChanged),
    StatType.CRIT_CHANCE: ModStatTransformConfig(
        TagKey.UnitStats_CritChance, TagKey.UnitStats_CritChance_Modification,
        TagKey.UnitStats_CritChance_Modification_Change,
        TagKey.UnitStats_CritChance_Modification_Entity),
    StatType.CRIT_DAMAGE: ModStatTransformConfig(
        TagKey.UnitStats_CritDamage, TagKey.UnitStats_CritDamage_Modification,
        TagKey.UnitStats_CritDamage_Modification_Change,
        TagKey.UnitStats_CritDamage_Modification_Entity),
    StatType.FIXED_ARMOR: ModStatTransformConfig(
        TagKey.UnitStats_FixedArmor, TagKey.UnitStats_FixedArmor_Modification,
        TagKey.UnitStats_FixedArmor_Modification_Change,
        TagKey.UnitStats_FixedArmor_Modification_Entity),
    # ⚠ LES SEPT SUIVANTES ONT `currentKey == modificationKey`, ET CE N'EST PAS UNE FAUTE DE
    # RECOPIE : le `.cctor` ecrit litteralement `0x4f0000004f`, `0x5200000052`, ... Ce sont les
    # stats « MODIFICATION SEULE » -- le flux n'en rapporte jamais la valeur courante, seulement
    # le delta (meme constat que le registre de `engine/streams/conformance.py`).
    StatType.EXTRA_HITS: ModStatTransformConfig(
        TagKey.UnitStats_ExtraHits_Modification, TagKey.UnitStats_ExtraHits_Modification,
        TagKey.UnitStats_ExtraHits_Modification_Change,
        TagKey.UnitStats_ExtraHits_Modification_Entity),
    StatType.EXTRA_HITS_MELEE: ModStatTransformConfig(
        TagKey.UnitStats_ExtraHitsMelee_Modification,
        TagKey.UnitStats_ExtraHitsMelee_Modification,
        TagKey.UnitStats_ExtraHitsMelee_Modification_Change,
        TagKey.UnitStats_ExtraHitsMelee_Modification_Entity),
    StatType.EXTRA_PIERCE_MELEE: ModStatTransformConfig(
        TagKey.UnitStats_ExtraPierceMelee_Modification,
        TagKey.UnitStats_ExtraPierceMelee_Modification,
        TagKey.UnitStats_ExtraPierceMelee_Modification_Change,
        TagKey.UnitStats_ExtraPierceMelee_Modification_Entity),
    StatType.EXTRA_PIERCE_RANGED: ModStatTransformConfig(
        TagKey.UnitStats_ExtraPierceRanged_Modification,
        TagKey.UnitStats_ExtraPierceRanged_Modification,
        TagKey.UnitStats_ExtraPierceRanged_Modification_Change,
        TagKey.UnitStats_ExtraPierceRanged_Modification_Entity),
    StatType.EXTRA_PIERCE: ModStatTransformConfig(
        TagKey.UnitStats_ExtraPierce_Modification, TagKey.UnitStats_ExtraPierce_Modification,
        TagKey.UnitStats_ExtraPierce_Modification_Change,
        TagKey.UnitStats_ExtraPierce_Modification_Entity),
    StatType.EXTRA_RANGE: ModStatTransformConfig(
        TagKey.UnitStats_ExtraRange_Modification, TagKey.UnitStats_ExtraRange_Modification,
        TagKey.UnitStats_ExtraRange_Modification_Change,
        TagKey.UnitStats_ExtraRange_Modification_Entity),
    StatType.EXTRA_MAX_DAMAGE: ModStatTransformConfig(
        TagKey.UnitStats_ExtraMaxDamage_Modification,
        TagKey.UnitStats_ExtraMaxDamage_Modification,
        TagKey.UnitStats_ExtraMaxDamage_Modification_Change,
        TagKey.UnitStats_ExtraMaxDamage_Modification_Entity),
}

#: `IdunBattle.Operations.TransformUnitOperation$$.ctor` -- UNE seule entree. Ce n'est PAS une
#: table statique : le `.ctor` la reconstruit a chaque instance, la ou la table modifiable est
#: un champ STATIQUE ecrit par le `.cctor`. L'asymetrie est native.
#: ⚠ `StatType.ARMOR` et `StatType.NUMBER_OF_MEMBERS` sont eux aussi des `FillUpStatComponent`
#: mais N'ONT PAS d'entree ici : sur eux, `Execute` tombe dans le troisieme cas (le fallback
#: `ACTIVE_ABILITY_LEVEL`, qui ne les reconnait pas non plus) et n'ecrit AUCUN tag.
FILL_STAT_TRANSFORM_CONFIG: Dict[int, FillStatTransformConfig] = {
    StatType.HEALTH: FillStatTransformConfig(
        TagKey.UnitStats_RemainingHealth, TagKey.UnitStats_MaxHealth,
        TagKey.UnitStats_MaxHealth_Modification, TagKey.UnitStats_MaxHealth_Modification_Change,
        TagKey.UnitStats_MaxHealth_Modification_Entity,
        TagKey.UnitStats_Unimplemented, TagKey.UnitStats_Unimplemented,
        TagKey.UnitStats_Unimplemented, EventTriggerType.HealthChanged, None),
}


@dataclass(frozen=True)
class StatOverrideReading:
    """Ce que `IdunBattle.Entities.UnitExtensions$$GetStatOverride(unit, statType)` rend --
    un `Nullable<...>` dont le port materialise seulement le contenu.

    Offsets RELATIFS lus dans les branches `StatPart.Override` / `RemoveOverride` :
    `+0x00` la valeur, `+0x04` le drapeau, `+0x08` un `Nullable<BEntityId>`.

    ⚠ NON CONFRONTE : aucune occurrence sur les trois flux temoins de `#477-r21`."""

    value: int
    is_modifiable: bool
    entity_id: Optional[int] = None


@dataclass(frozen=True)
class ModifierReading:
    """Une entree du `Modifications` d'un composant de stat, pour la SECONDE boucle d'`Execute`.

    ⚠ NON CONFRONTEE : elle n'est parcourue que pour `StatPart.Initial`, absent des trois flux
    temoins. Le port l'exprime plutot que de la taire, et REFUSE quand elle manque."""

    entity_id: int
    """La CLE du dictionnaire `Modifications` -- l'entite qui porte la modification."""
    stat_modification_total: int
    """`GetStat(unit, new Stat(statType, StatPart.Modification), null)`."""
    stat_modification_from_entity: int
    """`GetStat(unit, new Stat(statType, StatPart.Modification), entityId)`."""


@dataclass(frozen=True)
class StatModifierSetup:
    """`IdunBattleLogic.Battle.StatModifier` + les lectures ECS que les `Add*Tags` en tirent.

    Le natif porte `(Stat stat, int value, bool isModifiable, Nullable<BEntityId> entityId)`
    -- layout `+0x00` statType, `+0x04` statPart, `+0x08` value, `+0x0c` isModifiable,
    `+0x10` Nullable<BEntityId>. Les champs `stat_*` ci-dessous ne sont PAS dans la struct : ce
    sont les retours d'`IdunBattle.Entities.UnitExtensions$$GetStat`, que ce paquet recoit
    resolus (meme frontiere que `unit_extensions.UnitFullState`)."""

    stat_type: int
    stat_part: int
    value: int = 0
    is_modifiable: bool = False
    entity_id: Optional[int] = None
    """`Nullable<BEntityId>` -- l'entite du MODIFICATEUR (une entite d'EFFET dans le bloc 1).
    `None` fait sauter les deux tags `_Change` / `_Entity` : c'est une garde native."""

    stat_current: Optional[int] = None
    """`GetStat(unit, stat, null)` -- le `stat` COMPLET, donc la grandeur demandee par le
    `StatPart` du modificateur. Sur `StatPart.Modification`, c'est la modification TOTALE."""
    stat_from_modifier: Optional[int] = None
    """`GetStat(unit, stat, entityId)` -- la part apportee par CE modificateur."""
    stat_modification_total: Optional[int] = None
    """`GetStat(unit, new Stat(statType, StatPart.Modification), null)` -- lu par la SEULE
    branche `StatPart.ResetModification`, qui force le `StatPart` a `Modification`."""
    override: Optional[StatOverrideReading] = None
    """`GetStatOverride(unit, statType)`, lu par les branches `Override` / `RemoveOverride`.
    `None` = le `Nullable` natif est VIDE (branche « pas d'override »), ce qui est un cas
    NORMAL, pas une donnee manquante."""
    number_of_members: Optional[int] = None
    """`UnitExtensions$$GetNumberOfMembers(unit)`, lu par la queue d'`AddTagsForFillUp` quand
    `stat_type == StatType.HEALTH`."""
    existing_modifications: Optional[Sequence[ModifierReading]] = None
    """Le `Modifications` du composant, pour la SECONDE boucle d'`Execute` (`StatPart.Initial`)."""


def add_tag_if_implemented(tags: Dict[int, int], key: int, value: int) -> None:
    """`IdunBattle.Operations.TransformUnitOperation$$AddTagIfImplemented(eventTags, key,
    value)`.

    ⚠ `key == 0` NE POSE AUCUN TAG, et c'est LE mecanisme « non implemente » du natif : les
    configs ecrivent `TagKey.UnitStats_Unimplemented` (ordinal 0) partout ou la stat n'expose
    pas la grandeur. Le premier test du decompile est `if (key != 0)`.

    ⚠ UN DOUBLON NE REECRIT PAS. Le natif teste `ContainsKey` : absent, il `Add` ; present avec
    une valeur DIFFERENTE, il part dans `AOperation$$get_Logger` et laisse le dictionnaire
    INTACT. Le port ne materialise pas le logger, mais il preserve le point qui compte -- la
    PREMIERE valeur gagne. Ecraser produirait un flux faux des qu'une unite porte deux
    modificateurs de la meme stat dans la meme transformation."""
    if int(key) == int(TagKey.UnitStats_Unimplemented):
        return
    if int(key) in tags:
        return
    tags[int(key)] = int(value)


def _exiger(valeur: Optional[int], quoi: str, setup: "StatModifierSetup") -> int:
    """REFUSE plutot que d'ecrire un zero silencieux.

    Le port ne lit aucun composant ECS : quand une branche native appelle `GetStat` et que
    l'appelant n'a pas fourni la lecture correspondante, il n'y a AUCUNE valeur juste a ecrire.
    Emettre `0` produirait une ligne bien formee et FAUSSE -- exactement la degradation
    silencieuse que `#477-r22` a bannie en faisant lever `execute_stage`."""
    if valeur is None:
        raise ValueError(
            "transform_unit: la lecture `%s` manque pour StatType=%s StatPart=%s -- le port ne "
            "peut pas l'inventer (elle vient de `UnitExtensions$$GetStat`)"
            % (quoi, _nom(StatType, setup.stat_type), _nom(StatPart, setup.stat_part)))
    return int(valeur)


def _nom(enum_cls, valeur: int) -> str:
    try:
        return enum_cls(int(valeur)).name
    except ValueError:
        return str(int(valeur))


def add_modification_tags(tags: Dict[int, int], config: ModStatTransformConfig,
                          setup: StatModifierSetup) -> None:
    """`TransformUnitOperation$$AddModificationTags(eventTags, stat, config : ModStatTransform
    Config, unit, modifierId)` -- la surcharge « modifiable ».

        AddTagIfImplemented(config.modificationKey,       GetStat(unit, stat, null));
        if (modifierId.HasValue) {
            AddTagIfImplemented(config.modificationChangeKey, GetStat(unit, stat, modifierId));
            AddTagIfImplemented(config.modificationEntityKey, modifierId.Value);
        }

    ⚠ TROIS TAGS, PAS UN DE PLUS, ET LES DEUX DERNIERS SONT SOUS LA MEME GARDE. Un modificateur
    sans entite (il en existe : le natif construit des `StatModifier` par le ctor a trois
    arguments, qui laisse le `Nullable` vide) ne produit donc QUE `modificationKey`."""
    add_tag_if_implemented(tags, config.modification_key,
                           _exiger(setup.stat_current, "GetStat(unit, stat, null)", setup))
    if setup.entity_id is None:
        return
    add_tag_if_implemented(
        tags, config.modification_change_key,
        _exiger(setup.stat_from_modifier, "GetStat(unit, stat, entityId)", setup))
    add_tag_if_implemented(tags, config.modification_entity_key, int(setup.entity_id))


def add_modification_tags_fill(tags: Dict[int, int], config: FillStatTransformConfig,
                               setup: StatModifierSetup) -> None:
    """`TransformUnitOperation$$AddModificationTags(..., config : FillStatTransformConfig, ...)`
    -- la surcharge « fill-up ».

    Corps STRICTEMENT identique au precedent : seuls les offsets de `config` different (`+0x08`,
    `+0x0c`, `+0x10` au lieu de `+0x04`, `+0x08`, `+0x0c`), parce que `FillStatTransformConfig`
    porte un champ de plus en tete. Les deux fonctions existent separement dans le binaire ;
    les fusionner ferait perdre la trace de cette raison."""
    add_tag_if_implemented(tags, config.modification_key,
                           _exiger(setup.stat_current, "GetStat(unit, stat, null)", setup))
    if setup.entity_id is None:
        return
    add_tag_if_implemented(
        tags, config.modification_change_key,
        _exiger(setup.stat_from_modifier, "GetStat(unit, stat, entityId)", setup))
    add_tag_if_implemented(tags, config.modification_entity_key, int(setup.entity_id))


def add_tags_for_modifiable(tags: Dict[int, int], setup: StatModifierSetup,
                            config: ModStatTransformConfig) -> None:
    """`TransformUnitOperation$$AddTagsForModifiable(eventTags, statModifier, config, unit)`.

    C'est un `switch (statModifier.stat.statPart)` -- PAS sur le `StatType`. Les cinq cas et le
    `default` sont lus verbatim ; `default` construit un `System.NotImplementedException` et le
    LEVE, ce que le port reproduit.

    ⚠ `StatPart.Modification` (5) ET `MultiplierModification` (9) PARTAGENT LE MEME CORPS. Le
    flux ne peut donc pas les separer : sur les trois scenarios temoins, choisir l'un ou l'autre
    donne le MEME texte."""
    part = int(setup.stat_part)
    if part in (int(StatPart.CURRENT), int(StatPart.INITIAL)):
        add_tag_if_implemented(tags, config.current_key, int(setup.value))
        return
    if part in (int(StatPart.MODIFICATION), int(StatPart.MULTIPLIER_MODIFICATION)):
        add_modification_tags(tags, config, setup)
        return
    if part == int(StatPart.RESET_MODIFICATION):
        # `GetStat(unit, statModifier.stat.statType, StatPart.Modification /*5*/, null)` -- le
        # `StatPart` du modificateur est IGNORE, la lecture est forcee sur `Modification`.
        add_tag_if_implemented(
            tags, config.modification_key,
            _exiger(setup.stat_modification_total,
                    "GetStat(unit, statType, StatPart.Modification, null)", setup))
        if setup.entity_id is None:
            return
        add_tag_if_implemented(tags, config.modification_change_key, INT_MIN)
        add_tag_if_implemented(tags, config.modification_entity_key, int(setup.entity_id))
        return
    if part in (int(StatPart.OVERRIDE), int(StatPart.REMOVE_OVERRIDE)):
        # `GetStatOverride(unit, statType)` rend un `Nullable` : VIDE => une seule sentinelle.
        if setup.override is None:
            add_tag_if_implemented(tags, config.override_key, INT_MIN)
            return
        add_tag_if_implemented(tags, config.override_key, int(setup.override.value))
        # ⚠ `!= 0` ICI, `== 0` DANS LA VERSION FILL-UP. L'asymetrie est dans le binaire, pas
        # dans le port : les deux fonctions sont a quelques centaines d'octets l'une de
        # l'autre et testent le MEME champ dans les DEUX sens. Uniformiser serait un choix,
        # donc une invention.
        add_tag_if_implemented(tags, config.override_is_modifiable_key,
                               1 if setup.override.is_modifiable else 0)
        if setup.override.entity_id is None:
            return
        add_tag_if_implemented(tags, config.override_entity_key, int(setup.override.entity_id))
        return
    raise NotImplementedError(
        "AddTagsForModifiable: StatPart=%s n'a pas de branche -- le natif y construit un "
        "`System.NotImplementedException` et le LEVE" % _nom(StatPart, part))


def add_tags_for_fill_up(tags: Dict[int, int], setup: StatModifierSetup,
                         config: FillStatTransformConfig) -> None:
    """`TransformUnitOperation$$AddTagsForFillUp(eventTags, statModifier, config, unit)`.

    Meme forme que la precedente, avec DEUX differences lues :

      * un cas de plus -- `StatPart.Maximum` (2), qui ecrit `maxKey` et SORT SANS passer par le
        `AddTagIfImplemented` final (le decompile y saute directement a la queue) ;
      * une QUEUE commune a tous les chemins : si la stat est `StatType.Health`, un
        `UnitStats_NumberOfMembers` de plus, valeur `UnitExtensions$$GetNumberOfMembers(unit)`.
        Le test porte sur `statModifier.stat.statType`, pas sur la config."""
    part = int(setup.stat_part)
    if part == int(StatPart.CURRENT):
        add_tag_if_implemented(tags, config.remaining_key, int(setup.value))
    elif part == int(StatPart.MAXIMUM):
        add_tag_if_implemented(tags, config.max_key, int(setup.value))
    elif part == int(StatPart.INITIAL):
        add_tag_if_implemented(tags, config.max_key, int(setup.value))
        add_tag_if_implemented(tags, config.remaining_key, int(setup.value))
    elif part in (int(StatPart.MODIFICATION), int(StatPart.MULTIPLIER_MODIFICATION)):
        add_modification_tags_fill(tags, config, setup)
    elif part == int(StatPart.RESET_MODIFICATION):
        add_tag_if_implemented(
            tags, config.modification_key,
            _exiger(setup.stat_modification_total,
                    "GetStat(unit, statType, StatPart.Modification, null)", setup))
        if setup.entity_id is not None:
            add_tag_if_implemented(tags, config.modification_change_key, INT_MIN)
            add_tag_if_implemented(tags, config.modification_entity_key, int(setup.entity_id))
    elif part in (int(StatPart.OVERRIDE), int(StatPart.REMOVE_OVERRIDE)):
        if setup.override is None:
            add_tag_if_implemented(tags, config.override_key, INT_MIN)
        else:
            add_tag_if_implemented(tags, config.override_key, int(setup.override.value))
            # ⚠ `== 0` -- l'inverse exact d'`AddTagsForModifiable`. Verbatim, cf. plus haut.
            add_tag_if_implemented(tags, config.override_is_modifiable_key,
                                   0 if setup.override.is_modifiable else 1)
            if setup.override.entity_id is not None:
                add_tag_if_implemented(tags, config.override_entity_key,
                                       int(setup.override.entity_id))
    else:
        raise NotImplementedError(
            "AddTagsForFillUp: StatPart=%s n'a pas de branche -- le natif y construit un "
            "`System.NotImplementedException` et le LEVE" % _nom(StatPart, part))
    if int(setup.stat_type) == int(StatType.HEALTH):
        add_tag_if_implemented(
            tags, TagKey.UnitStats_NumberOfMembers,
            _exiger(setup.number_of_members, "GetNumberOfMembers(unit)", setup))


def build_transform_tags(modifiers: Sequence[StatModifierSetup],
                         is_hidden: bool = False) -> Dict[int, int]:
    """Le dictionnaire de la PREMIERE `Action=ChangeStats` d'`Execute`, sans l'emettre.

        tags = new Dictionary<TagKey,int>();
        tags.Add(TagKey.UnitStats_Transformed /*0x69*/, 1);          <- INCONDITIONNEL
        if (isHidden) tags.Add(TagKey.UnitStats_Modification_Hidden /*0x6b*/, 1);
        foreach (sm in statModifiers) { ... }

    ⚠ `UnitStats_Transformed` EST L'INVARIANT DE LA LIGNE. Il est ecrit AVANT la boucle, sans
    aucune garde : une `Action=ChangeStats` issue de cette operation le porte TOUJOURS -- ce que
    les trois motifs ecartes de `#477-r21` confirment (2 + 1 occurrences sur chaque board).
    C'est aussi ce qui la distingue, dans le flux, des `ChangeStats` de `AddUnitOperation`
    (etat complet, cf. `unit_extensions`) et de `RemoveActiveAbilityOperation` (un seul tag).

    ⚠ L'AIGUILLAGE EST UNE CASCADE A TROIS ETAGES, DANS CET ORDRE : table modifiable (statique),
    puis table fill-up (d'instance), puis un cas special en dur pour
    `StatType.ActiveAbilityLevel`. Une stat qu'aucun des trois ne reconnait ne produit AUCUN
    tag et n'est pas une erreur -- c'est un `continue` du decompile."""
    tags: Dict[int, int] = {}
    tags[int(TagKey.UnitStats_Transformed)] = 1
    if is_hidden:
        tags[int(TagKey.UnitStats_Modification_Hidden)] = 1
    for setup in modifiers:
        config = MOD_STAT_TRANSFORM_CONFIG.get(int(setup.stat_type))
        if config is not None:
            add_tags_for_modifiable(tags, setup, config)
            continue
        fill = FILL_STAT_TRANSFORM_CONFIG.get(int(setup.stat_type))
        if fill is not None:
            add_tags_for_fill_up(tags, setup, fill)
            continue
        if int(setup.stat_type) != int(StatType.ACTIVE_ABILITY_LEVEL):
            continue
        # ⚠ CE TROISIEME ETAGE N'UTILISE PAS `AddTagIfImplemented` : le decompile appelle
        # `Dictionary$$Add` DIRECTEMENT, qui LEVE sur une cle deja presente. Le port refuse
        # donc au lieu d'ecraser -- deux modificateurs `ActiveAbilityLevel` dans la meme
        # transformation font echouer l'operation NATIVE, pas produire une ligne silencieuse.
        part = int(setup.stat_part)
        if part == int(StatPart.OVERRIDE):
            valeur = int(setup.value)
        elif part == int(StatPart.REMOVE_OVERRIDE):
            valeur = INT_MIN
        else:
            continue
        if int(TagKey.UnitStats_ActiveAbility_Level) in tags:
            raise ValueError(
                "transform_unit: `Tag=%s` deja pose -- le natif appelle `Dictionary$$Add`, qui "
                "leve sur doublon" % TagKey.UnitStats_ActiveAbility_Level.name)
        tags[int(TagKey.UnitStats_ActiveAbility_Level)] = valeur
    return tags


def transform_unit(events: StreamDispatcher, unit_entity_id: int,
                   modifiers: Sequence[StatModifierSetup], is_hidden: bool = False) -> None:
    """La FACE STREAM de `IdunBattle.Operations.TransformUnitOperation$$Execute(unit,
    statModifiers, isHidden)`.

    UNE `Action=ChangeStats` pour tout le lot de modificateurs -- puis, pour chaque modificateur
    en `StatPart.Initial`, UNE LIGNE DE PLUS PAR MODIFICATION EXISTANTE du composant (seconde
    boucle du decompile). L'entite est TOUJOURS celle de l'unite, jamais celle du modificateur.

    ⚠ LA SECONDE BOUCLE EST PORTEE MAIS NON CONFRONTEE : `StatPart.Initial` n'apparait sur aucun
    des trois flux temoins de `#477-r21`. Elle REFUSE si `existing_modifications` manque, au
    lieu d'emettre une ligne de moins sans le dire."""
    events.action(StepType.ChangeStats, unit_entity_id,
                  build_transform_tags(modifiers, is_hidden))
    for setup in modifiers:
        if int(setup.stat_part) != int(StatPart.INITIAL):
            continue
        config = MOD_STAT_TRANSFORM_CONFIG.get(int(setup.stat_type))
        fill = FILL_STAT_TRANSFORM_CONFIG.get(int(setup.stat_type))
        if config is None and fill is None:
            continue
        if setup.existing_modifications is None:
            raise ValueError(
                "transform_unit: StatPart.Initial sur StatType=%s sans `existing_modifications` "
                "-- la seconde boucle d'`Execute` parcourt `StatComponent$$get_Modifications`, "
                "que le port ne peut pas inventer" % _nom(StatType, setup.stat_type))
        for lecture in setup.existing_modifications:
            # Le natif reconstruit un `Stat(statType, StatPart.Modification)` -- le `StatPart`
            # du modificateur d'origine (`Initial`) n'est PAS celui de la lecture.
            relu = StatModifierSetup(
                stat_type=setup.stat_type, stat_part=StatPart.MODIFICATION,
                entity_id=lecture.entity_id,
                stat_current=lecture.stat_modification_total,
                stat_from_modifier=lecture.stat_modification_from_entity)
            tags: Dict[int, int] = {}
            if config is not None:
                add_modification_tags(tags, config, relu)
            else:
                add_modification_tags_fill(tags, fill, relu)
            events.action(StepType.ChangeStats, unit_entity_id, tags)
