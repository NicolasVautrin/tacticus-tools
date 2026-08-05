"""`BEntityId` -- le type sous lequel le flux ECRIT un identifiant d'entite, et son formatage.

POURQUOI CE FICHIER EXISTE. Le flux porte `Entity=NO_ENTITY` sur certaines lignes
(`Group=User_PlaceUnit Entity=NO_ENTITY`) et `Entity=49` sur d'autres. Les deux sortent du MEME
`String.Format` : `IdunBattle.BattleStream.Loggers.StreamCache$$StartGroup` et `$$Action`
BOXENT l'identifiant avant de le formater, et le type boxe est un ENUM --
`IdunBattle.Core.BEntityId`, qui ne porte qu'un seul membre :

    IdunBattle.Core.BEntityId    0=NO_ENTITY

(lu dans `data/symbols/<CURRENT>/frida/enums.tsv`). Le meme boxage se relit dans
`IdunBattle.Core.Entity$$ToString`, qui boxe son champ `+0x10` avec le meme type.

⇒ `Enum.ToString()` de .NET rend le NOM quand la valeur est un membre, et la valeur DECIMALE
sinon. D'ou `0 -> "NO_ENTITY"` et `49 -> "49"`, sans aucun cas particulier dans le writer.

⚠ UN `IntEnum` PYTHON NE FAIT PAS CA. `BEntityId(49)` leve (`49 is not a valid BEntityId`), et
`str(BEntityId.NO_ENTITY)` rend `"BEntityId.NO_ENTITY"` selon la version de Python. Le formatage
passe donc par `format_enum_value`, qui mirror la regle .NET -- et qui sert AUSSI a `GroupType`
/ `StepType` / `TagKey`, pour lesquels un ordinal inconnu doit s'ecrire en clair plutot que
lever : le jeu ecrit un nombre, il ne plante pas.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Type


class BEntityId(IntEnum):
    """`IdunBattle.Core.BEntityId` -- VERBATIM du build (1 valeur).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, ligne `IdunBattle.Core.BEntityId`.
    """

    NO_ENTITY = 0


#: Sentinelle « pas d'entite », telle que le flux l'ECRIT.
NO_ENTITY = int(BEntityId.NO_ENTITY)


def format_enum_value(enum_cls: Type[IntEnum], value: int) -> str:
    """Mirror de `System.Enum$$ToString` : le NOM si la valeur est un membre, sinon le decimal.

    C'est la regle qui produit `Entity=NO_ENTITY` pour 0 et `Entity=49` pour 49 -- le writer
    natif n'a aucune branche pour ces deux cas, seulement ce formatage."""
    member = enum_cls._value2member_map_.get(int(value))
    if member is None:
        return str(int(value))
    # `None_` est l'echappement Python du membre natif `None` (meme convention que
    # `ActiveAbilityType.None_` ; `probe_313` denormalise a la comparaison). Le jeu, lui,
    # ecrit `None`.
    name = member.name
    return name[:-1] if name == "None_" else name
