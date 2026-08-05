"""`EffectTargetType` -- le ROLE cherche quand on interroge la presence d'un effet.

Mirror 1:1 de l'enum natif, re-derivable de `data/symbols/<build>/frida/enums.tsv`.

CE QU'IL DESIGNE, ET COMMENT ON LE SAIT. C'est le type DECLARE du dernier parametre des cinq
foyers natifs qui interrogent un effet, LU dans `frida/methods.tsv` (jamais deduit d'un nom
court ni d'un ordinal) :

    IdunBattleLogic.Entities.DSLTriggers.HasEffect            (targetType : ...EffectTargetType)
    IdunBattleLogic.Entities.DSLSelectors.EntitiesWithAnyEffect        (effectTarget : ...)
    IdunBattle.Entities.EntityExtensions.HasOneOfEffects               (targetType : ...)
    IdunBattle.Entities.Selectors.EntitiesWithAnyEffectSelector..ctor  (targetType : ...)
    IdunBattle.Entities.Triggers.HasEffectTrigger..ctor           (effectTargetType : ...)

C'est le seul canal qui tranche : l'ordinal `6` est aussi un membre valide de dizaines d'autres
enums du build (dont `EffectType.PoisonGrenade`), et rien dans la VALEUR ne dit lequel --
exactement le regime ou un ordinal juste ne prouve rien.

`0` et `1` n'existent PAS dans le build : le natif ne publie aucun membre neutre, et les trois
membres ci-dessous sont l'INTEGRALITE de l'enum. Les valeurs SUGGERENT des bits (`6 == 2|4`),
mais l'attribut `[Flags]` n'a pas ete lu -- d'ou `IntEnum`, qui n'affirme que ce qui est lu.
Ecrire `Owner | Target` reste possible (un `IntEnum` EST un `int`) et rend bien `6`.
"""
from __future__ import annotations

from enum import IntEnum


class EffectTargetType(IntEnum):
    """`IdunBattle.Entities.Enum.EffectTargetType` -- VERBATIM du build (3 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, cle
    `IdunBattle.Entities.Enum.EffectTargetType`. Sous garde de
    `probe_313_enum_mirror_bijection.py` (bijection exigee, appariement par NOM PLEIN --
    le build ne porte AUCUN homonyme de ce nom, mesure #270-r4 ; c'est l'exception, pas la
    regle : `Corner` en a cinq, `Edge` un)."""

    Owner = 2
    Target = 4
    Both = 6
