"""`StreamHelper` -- les fabriques de TAGS du flux, mirror 1:1 par helper natif.

`IdunBattle.Core.Services.StreamHelper` porte DIX methodes `Get*Tags` (recensees par #477-r15) ;
elles construisent le dictionnaire `Dictionary<TagKey,int>` passe a
`IdunBattle.Streams.StreamDispatcher$$Action`. Une seule est portee ici -- `GetAddUnitTags`,
la seule dont le flux de DEPLOIEMENT a besoin. Les neuf autres (`GetDamageTags`,
`GetRefreshEffectTags`, `GetResurrectUnitTags`, `GetAddOrUpdateShieldTags`, `GetAddScoreTags`,
`GetRemoveShieldTags`, `GetReviveUnitTags`, `GetActiveAbilityStateUpdateTags`,
`GetUpdateActiveAbilityModificationTags`) relevent du DEROULE de bataille : elles sont la
tranche D, et leur absence est PUBLIEE par le comparateur, jamais silencieuse.

⚠ L'ORDRE D'INSERTION N'EST PAS L'ORDRE D'ECRITURE. Le natif insere dans un `Dictionary`
(non ordonne) et c'est `StreamCache$$Action` qui re-trie par ORDINAL. L'ordre ci-dessous est donc
celui du DECOMPILE -- il n'a aucun effet observable, et le conserver est ce qui rend le mirror
relisible ligne a ligne contre le natif.
"""
from __future__ import annotations

from typing import Dict, Sequence

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
