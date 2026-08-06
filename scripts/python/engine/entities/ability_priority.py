"""Mirror de `IdunBattle.Entities.Abilities.AbilityPriority`.

C'est le type de retour LU (`frida/methods.tsv`) des trois `get_Priority` que le dump nomme :

    IdunBattle.AI.Playbook.Loki.TzeentchsFirestormPlaybook.get_Priority   -> AbilityPriority
    IdunBattle.AI.Playbook.Loki.SquigMinePlaybook.get_Priority            -> AbilityPriority
    IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect.get_Priority
                                                                          -> AbilityPriority

Le MEME enum sert donc aux DEUX axes, et c'est le point a ne pas confondre :

  * axe PLAYBOOK (`IPlaybook` slot 0) -- le tier qui range les `ActiveAbilityType` NonComparable
    dans `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists`. Table portee :
    `engine/playbook/noncomparable/_base.py::NATIVE_PRIORITY` (22 valeurs, case-170) ;
  * axe CACHE D'ACTIVATION -- `IdunBattleLogic.Core.Services.Caches.SortedTriggeredAbility$$get_Priority`
    (slot 7 de l'ability) et `...SortedEffect$$get_Priority` (slot 9 de l'effet), qui ORDONNENT
    la liste que `EvaluateTriggerOperation$$ExecuteInternal` parcourt (#477-r21-r2 volet B).

Les deux axes lisent des slots DIFFERENTS sur des objets DIFFERENTS : un playbook de tier 1000
ne dit RIEN de la priorite de cache de l'ability homonyme. Les confondre ordonnerait le cache
par le tier de decision de l'IA.

⚠ LES VALEURS PAR PORTEUR NE SONT PAS LISIBLES AU DECOMPILE, et c'est la meme cause que #170 :
ces getters ont pour corps `mov eax,<imm32> ; ret`, qu'IL2CPP DEDUPLIQUE entre tous les porteurs
de meme tier -- un seul proprietaire arbitraire par corps dans `frida/methods.tsv`. L'ENUM, lui,
se lit : `data/symbols/<build>/frida/enums.tsv` porte
`IdunBattle.Entities.Abilities.AbilityPriority  1000=First,100=Early,0=Normal,-100=Late,-1000=Last`.
"""
from __future__ import annotations

from enum import IntEnum


class AbilityPriority(IntEnum):
    """`IdunBattle.Entities.Abilities.AbilityPriority` -- verbatim `enums.tsv`."""

    First = 1000
    Early = 100
    Normal = 0
    Late = -100
    Last = -1000
