"""`IdunBattle.Entities.Effects.Loki.BattleFocusEffect` (`EffectType.BattleFocus` = 0x4af = **1199**)
-- l'effet que le passif `BattleFocus` (`TriggeredAbilityType.BattleFocus` = 0x494 = **1172**) pose
sur SON PROPRE porteur a l'init. #1080.

i2 : « After attacking or being attacked, moves 1 hex in a direction as far away from enemies as
possible. »

⚠ **1199 != 1172, ET CHACUN MENT DANS L'AUTRE ENUM** -- meme piege que `UnwaveringSentinel` :
`TriggeredAbilityType 1199` = `GalvanicField` (sans aucun rapport), `EffectType 1172` =
`HuntersBeyondDeath_ExtraDamage`. La confusion serait SILENCIEUSE en ordinal ; les deux constantes
sont donc ecrites par leur MEMBRE.

LES LITTERAUX DU `.ctor`, LUS A L'ASSEMBLEUR (le pseudo-C n'en montre aucun) :

    mov  edx, 0x494                     ; 1172 en TriggeredAbilityType
    call IdunBattle.Core.AbilityOrEffect$$op_Implicit    ; surcharge set_TriggeredAbility
    mov  r8b, 1                         ; hasAutomaticActivation = 1
    call IdunBattle.Entities.Effects.BaseEffect$$.ctor

`hasAutomaticActivation = 1` = `activationFrequency == 0` : ce n'est PAS un `PlayerTurnEffect`, il
n'y a donc AUCUNE paire `Activate/Deactivate` sur les bornes de tour (contraste avec les trois
effets-riposte de `counter_attack.py`). L'effet est actif en permanence tant qu'il est pose.

L'effet ne porte NI modification de stat, NI bonus/malus de degat : sa seule substance est le couple
`CreateTargetTrigger` / `CreateTargetTriggerBehaviour`, porte par
`engine/runner/operations/triggers/loki/battle_focus.py` (canal `EFFECT_TRIGGERS`). Cette classe
existe pour que `EffectFactory.create` le materialise depuis `decisionView.effects` -- ce qui EST le
canal reel : mesure live du 2026-08-14, `decisionView` rend `u81 [eldarNpc1Guardian] : BattleFocus`
des le deploiement, sans qu'aucun cast ait eu lieu.
"""
from __future__ import annotations

from ..base import BaseEffect
from ....entities.triggered_ability_type import TriggeredAbilityType   # #270-r1-r1-r3


class BattleFocusEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.BattleFocusEffect` -- cf. l'en-tete du module."""

    HAS_AUTOMATIC_ACTIVATION = True    # `BaseEffect$$.ctor(hasAutomaticActivation = 1)`, LU
    #: `AbilityOrEffect.op_Implicit(0x494)` du `.ctor` : la SOURCE de l'effet est l'ability
    #: DECLENCHEE 1172, pas un `EffectType` ni une active.
    SOURCE_TRIGGERED_ABILITY = TriggeredAbilityType.BattleFocus         # 0x494 = 1172
