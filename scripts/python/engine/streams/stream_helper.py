"""`StreamHelper` -- les fabriques de TAGS du flux, mirror 1:1 par helper natif.

`IdunBattle.Core.Services.StreamHelper` porte DIX methodes `Get*Tags` (recensees par #477-r15) ;
elles construisent le dictionnaire `Dictionary<TagKey,int>` passe a
`IdunBattle.Streams.StreamDispatcher$$Action`. DEUX sont portees ici -- `GetAddUnitTags`, la
seule dont le flux de DEPLOIEMENT a besoin, et `GetDamageTags` (#477-r34), celle du
`Group=Damage`. Les huit autres (`GetRefreshEffectTags`, `GetResurrectUnitTags`,
`GetAddOrUpdateShieldTags`, `GetAddScoreTags`, `GetRemoveShieldTags`, `GetReviveUnitTags`,
`GetActiveAbilityStateUpdateTags`, `GetUpdateActiveAbilityModificationTags`) relevent du
DEROULE de bataille : elles sont la tranche D, et leur absence est PUBLIEE par le comparateur,
jamais silencieuse.

⚠ L'ORDRE D'INSERTION N'EST PAS L'ORDRE D'ECRITURE. Le natif insere dans un `Dictionary`
(non ordonne) et c'est `StreamCache$$Action` qui re-trie par ORDINAL. L'ordre ci-dessous est donc
celui du DECOMPILE -- il n'a aucun effet observable, et le conserver est ce qui rend le mirror
relisible ligne a ligne contre le natif.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from .damage_result import AbilityOrEffect, DamageAppliedResult
from .tag_key import TagKey

#: `TagKey.Unit_Foot_Tile_Id_1` .. `_7` -- le natif deroule SEPT tests `if (feet.Count > i)`,
#: chacun avec son ordinal en dur. La borne 7 est donc NATIVE, pas une convention du port.
FOOT_TILE_TAGS = (
    TagKey.Unit_Foot_Tile_Id_1,
    TagKey.Unit_Foot_Tile_Id_2,
    TagKey.Unit_Foot_Tile_Id_3,
    TagKey.Unit_Foot_Tile_Id_4,
    TagKey.Unit_Foot_Tile_Id_5,
    TagKey.Unit_Foot_Tile_Id_6,
    TagKey.Unit_Foot_Tile_Id_7,
)


def get_add_unit_tags(owner_id: int, parent_id: int, source: int, is_boss: bool,
                      foot_count: int,
                      unit_feet_tile_ids: Sequence[int]) -> Dict[int, int]:
    """`IdunBattle.Core.Services.StreamHelper$$GetAddUnitTags(unit, unitComponent, source, feet,
    unitFeetTileIds)`.

    Le natif lit ses valeurs sur des composants ECS ; le port les recoit deja resolues. Ce sont
    des donnees d'ETAT, pas des identifiants d'entite a allouer -- l'allocation, elle, est portee
    depuis `#477-r21-r3` (`engine/streams/entity_allocator.py`) :

      `owner_id`   -- `unit.GetComponent<...>()+0x10`, le champ recopie dans `Unit_Owner_Id` ;
                      c'est un id d'ENTITE de joueur, pas un `PlayerId` (piege #477-r11) ;
      `parent_id`  -- `unit.GetComponent<...>()+0x10` du composant de parente ; `0` = pas de
                      parent, et c'est CE test qui decide `Unit_IsSummoned` ;
      `source`     -- `SpawnSource` ;
      `is_boss`    -- `unitComponent+0x88` ;
      `foot_count` -- `feet.Count` : le natif teste la taille de `feet` mais LIT dans
                      `unitFeetTileIds`. Les deux collections sont distinctes dans la signature,
                      donc le port les garde distinctes plutot que de deduire l'une de l'autre.

    ⚠ `Unity.Collections.CollectionHelper$$AssumePositive`, applique a `parent_id` dans le
    decompile, est un corps TRIVIAL (donc potentiellement un mislabel de deduplication IL2CPP,
    cf. CLAUDE.md) : il est mirrore comme l'identite. Il n'a aucun effet observable sur un id
    d'entite, qui est positif par construction."""
    tags: Dict[int, int] = {}
    tags[TagKey.Unit_Owner_Id] = int(owner_id)
    tags[TagKey.Unit_IsSummoned] = 1 if int(parent_id) != 0 else 0
    tags[TagKey.Unit_SpawnSource] = int(source)
    tags[TagKey.UnitStats_IsBoss] = 1 if is_boss else 0
    # `int p = 0; if (parent.@0x10 != 0) p = parent.@0x10; tags.Add(Unit_Parent_Id, p);`
    parent = int(parent_id) if int(parent_id) != 0 else 0
    tags[TagKey.Unit_Parent_Id] = parent
    for index, tag in enumerate(FOOT_TILE_TAGS):
        if int(foot_count) > index:
            tags[tag] = int(unit_feet_tile_ids[index])
    return tags


#: LA CASCADE DE LA SOURCE DU COUP -- `(<champ d'AbilityOrEffect>, <TagKey>)`, dans l'ORDRE ou
#: `GetDamageTags` les teste. Le natif s'arrete au PREMIER champ qui a une valeur, et n'ecrit
#: alors qu'UN tag.
#:
#: ⚠ LE COUPLE `triggered_ability` -> `Passive_Ability_Type` EST LU, PAS DEDUIT DU NOM. Le champ
#: natif s'appelle `AbilityOrEffect.TriggeredAbility` (`set_TriggeredAbility`, type declare
#: `Nullable<TriggeredAbilityType>`) et le tag `TagKey.Passive_Ability_Type` : les deux noms ne
#: se ressemblent pas, et c'est exactement ce qui rend l'appariement non devinable.
SOURCE_TAGS: Tuple[Tuple[str, TagKey], ...] = (
    ("active_ability", TagKey.Active_Ability_Type),
    ("triggered_ability", TagKey.Passive_Ability_Type),
    ("effect", TagKey.Effect_Type),
)

#: LA MEME CASCADE POUR LE HIT ADDITIONNEL. Les trois clés sont DISTINCTES des trois
#: ci-dessus, et leur ordre est le meme (`active` puis `triggered` puis `effect`).
ADDITIONAL_HIT_SOURCE_TAGS: Tuple[Tuple[str, TagKey], ...] = (
    ("active_ability", TagKey.Additional_Hit_ActiveAbility_Source),
    ("triggered_ability", TagKey.Additional_Hit_TriggeredAbility_Source),
    ("effect", TagKey.Additional_Hit_Effect_Source),
)


def _ajouter_premier_present(tags: Dict[int, int], source: AbilityOrEffect,
                             cascade: Tuple[Tuple[str, TagKey], ...]) -> None:
    """La cascade `if (x.HasValue) { Add(cle, x.Value); } else if (y.HasValue) { ... }`.

    Le natif re-lit le `Nullable` englobant a CHAQUE etage (`get_Value(dr+0x40, ...)` apparait
    quatre fois dans le decompile) ; ce n'est qu'une consequence du passage par valeur d'un
    `ValueType`, sans effet observable. Ce qui compte, et qui est reproduit : UN SEUL tag est
    ecrit, et c'est celui du PREMIER champ non vide. Les trois vides -> AUCUN tag."""
    for champ, cle in cascade:
        valeur = getattr(source, champ)
        if valeur is not None:
            tags[int(cle)] = int(valeur)
            return


def get_damage_tags(target_entity_id: int, damage_result: DamageAppliedResult,
                    num_members_died: int, caster_entity_id: Optional[int], amount: int,
                    remaining_health: int, remaining_armor: int, total_shield: int,
                    number_of_members: int) -> Dict[int, int]:
    """`IdunBattle.Core.Services.StreamHelper$$GetDamageTags(target, damageResult,
    numMembersDied, caster, result)` -- la signature exacte est publiee par
    `data/symbols/<build>/frida/methods.tsv` :

        target        : IdunBattle.Core.IEntity
        damageResult  : IdunBattle.Core.Services.DamageAppliedResult
        numMembersDied: System.Int32
        caster        : IdunBattle.Core.IEntity
        result        : IdunBattle.Core.OperationResult
        -> System.Collections.Generic.Dictionary<IdunBattle.Streams.TagKey, System.Int32>

    LE DECOMPILE, dans son ordre d'insertion :

        tags.Add(UnitStats_RemainingHealth /*5*/,   <composant>.<+0x18>);
        tags.Add(UnitStats_RemainingArmor  /*6*/,   <composant>.<+0x18>);
        tags.Add(Shields_RemainingAmount /*0xeb*/,
                 IdunBattle.Entities.Components.ShieldComponent$$GetTotalShield(<composant>));
        tags.Add(UnitStats_NumberOfMembers /*100*/, <composant>.<+0x18>);
        tags.Add(Attack_DidCrit      /*0x8a*/, damageResult.<+0x0e>);   // didCrit
        tags.Add(Attack_DidBlock     /*0x8b*/, damageResult.<+0x0c>);   // didBlock
        tags.Add(Attack_DidEvade     /*0x8c*/, damageResult.<+0x0d>);   // didEvade
        tags.Add(Attack_WasOverkill  /*0x8e*/, damageResult.<+0x0f>);   // didOverkill
        tags.Add(Attack_Is_First_Hit /*0x83*/, damageResult.<+0x14> == 0);  // hitIndex == 0
        if (numMembersDied > 0)
            tags.Add(UnitStats_NumberOfMembers_Change /*0x65*/, numMembersDied);
        tags.Add(Attack_WasMemberKilled /*0x8f*/, numMembersDied > 0);
        if (caster != null) tags.Add(Attacker_Id /*0xb6*/, <IEntity slot 0>(caster));
        tags.Add(Target_Id /*0xb3*/, <IEntity slot 0>(target));
        tags.Add(Amount            /*0xe1*/, result.<+0x00>);
        tags.Add(DamageProfileType /*0xe2*/, damageResult.<+0x00>);
        if (!damageResult.<+0x40>.HasValue) return tags;               // <-- LE RETOUR ANTICIPE
        <cascade Active_Ability_Type / Passive_Ability_Type / Effect_Type sur +0x40>
        if (damageResult.<+0x78>.HasValue)
            <cascade Additional_Hit_*_Source sur +0x78>
        return tags;

    ⚠ QUATRE VALEURS SONT DES ENTREES D'ETAT ECS, comme dans `get_add_unit_tags`. Le natif les
    lit sur QUATRE composants du `target` (`GetComponent<T>` sur des `Il2CppClass*` que Ghidra
    ne resout pas -- seul `ShieldComponent$$GetTotalShield` est nomme) ; le port les recoit
    resolues, et c'est declare en borne (c) partout ou il est confronte. Elles sont donnees
    dans l'ORDRE des clés qu'elles alimentent : `remaining_health`, `remaining_armor`,
    `total_shield`, `number_of_members`.

    ⚠ `Attack_Is_First_Hit` SORT DE `hitIndex == 0`, PAS DU CHAMP `isFirstDamagingHit`. Le
    getter qui le calcule a un corps TRIVIAL (`return *(int*)(this + 0x14) == 0;`) qu'IL2CPP
    DEDUPLIQUE : Ghidra le nomme `IdunMetaLogic.UserProgress.ProductCost$$get_IsFree`. Prendre
    ce nom au serieux ferait lire « le produit est gratuit » la ou le jeu teste l'indice du
    coup. C'est l'avertissement du CLAUDE.md sur les tables (une PRESENCE trompeuse), et
    l'offset `+0x14` le tranche : le `.ctor` y ecrit `hitIndex`, et `isFirstDamagingHit` est a
    `+0x18`.

    ⚠ LE RETOUR EST ANTICIPE QUAND LA SOURCE DU COUP EST VIDE, ET C'EST ASYMETRIQUE. Si
    `damageResult.Source.<+0x18>` n'a pas de valeur, la fonction REND -- le bloc
    `Additional_Hit_*` n'est alors JAMAIS evalue, meme si `<+0x50>` en a une. En revanche, si le
    `Nullable` a une valeur mais que ses TROIS champs sont vides, le natif saute seulement
    l'`Add` (`goto`) et evalue quand meme le hit additionnel. Les deux chemins different, et
    les confondre serait invisible sur tout corpus ou la source est toujours presente -- ce
    qui est le cas du notre (72 / 72). Ils sont donc portes tels quels et DECLARES NON EXERCES.

    ⚠ `Attack_WasMemberKilled` EST INCONDITIONNEL, `UnitStats_NumberOfMembers_Change` NON. Le
    natif ecrit toujours le booleen `numMembersDied > 0`, et n'ecrit le compte que s'il est
    strictement positif. Un port qui garderait les deux, ou aucun, produirait un flux qui ne
    differe du bon que sur les coups sans mort -- c'est-a-dire la majorite."""
    tags: Dict[int, int] = {}
    tags[int(TagKey.UnitStats_RemainingHealth)] = int(remaining_health)
    tags[int(TagKey.UnitStats_RemainingArmor)] = int(remaining_armor)
    tags[int(TagKey.Shields_RemainingAmount)] = int(total_shield)
    tags[int(TagKey.UnitStats_NumberOfMembers)] = int(number_of_members)
    tags[int(TagKey.Attack_DidCrit)] = 1 if damage_result.did_crit else 0
    tags[int(TagKey.Attack_DidBlock)] = 1 if damage_result.did_block else 0
    tags[int(TagKey.Attack_DidEvade)] = 1 if damage_result.did_evade else 0
    tags[int(TagKey.Attack_WasOverkill)] = 1 if damage_result.did_overkill else 0
    tags[int(TagKey.Attack_Is_First_Hit)] = 1 if int(damage_result.hit_index) == 0 else 0
    if int(num_members_died) > 0:
        tags[int(TagKey.UnitStats_NumberOfMembers_Change)] = int(num_members_died)
    tags[int(TagKey.Attack_WasMemberKilled)] = 1 if int(num_members_died) > 0 else 0
    if caster_entity_id is not None:
        tags[int(TagKey.Attacker_Id)] = int(caster_entity_id)
    tags[int(TagKey.Target_Id)] = int(target_entity_id)
    tags[int(TagKey.Amount)] = int(amount)
    tags[int(TagKey.DamageProfileType)] = int(damage_result.damage_profile_type)
    source = damage_result.source.source
    if source is None:
        return tags
    _ajouter_premier_present(tags, source, SOURCE_TAGS)
    additionnel = damage_result.source.additional_hit_source
    if additionnel is not None:
        _ajouter_premier_present(tags, additionnel, ADDITIONAL_HIT_SOURCE_TAGS)
    return tags
