"""Famille `IdunBattle.Entities.Effects.CounterAttackEffect` — les RIPOSTES portees par un EFFET.

Distinction structurelle avec la riposte portee par une TRIGGERED-ABILITY (`MartialSuperiority`,
`runner/operations/triggers/loki/martial_superiority.py`) : ici le trigger de riposte vit sur
l'entite-EFFET, et sa fenetre d'armement est l'etat `EffectComponent.IsActive @+0x5c` pilote par les
`Triggered()` de `IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal`.
C'est ce qui porte le « the FIRST time ... during the enemy's turn » d'i2 : une seule riposte par
armement, re-armee a la fin du tour du porteur.

Chaine de classes, lue dans `data/symbols/<build>/frida/classes.tsv` (pas devinee) :

    WireweaveNet_CounterAttackEffect : CounterAttackEffect : PlayerTurnEffect : BaseEffect

Les cinq membres de la famille sur ce build : `GrimRetribution_CounterAttackEffect`,
`SmashaSquigJaws_CounterAttackEffect`, `UnwaveringSentinel_CounterAttackEffect`,
`WarConstruct_CounterAttackEffect`, `WireweaveNet_CounterAttackEffect`. SEUL le dernier est porte
(porteur `eldarRanger` HERO au pool) ; les quatre autres sont des residus NOMMES.
"""
from __future__ import annotations

from ..base import BaseEffect
from ....entities.triggered_ability_type import TriggeredAbilityType   # #270-r1-r1-r3


class WireweaveNetCounterAttackEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.WireweaveNet_CounterAttackEffect` (EffectType 0x457 = 1111,
    nom capte "WireweaveNet_CounterAttack") — l'effet-RIPOSTE pose sur elle-meme par le PASSIF
    `WireweaveNet` (`TriggeredAbilityType` 0x457 = 1111) de `eldarRanger` (Calandis).

    i2 : « The first time Calandis is targeted by a normal melee attack during the enemy's turn, the
    attacker immediately takes 2x 873-1310 Piercing Damage. If the attacker is eliminated, their melee
    attack is not executed. »

    CETTE CLASSE N'A AUCUN CANAL DE BONUS. Tout son comportement observable vit dans les TROIS
    `Triggered()` portes par `runner/operations/triggers/loki/wireweave_net.py` (registre
    `EFFECT_TRIGGERS[1111]`). Elle est inscrite a `EFFECT_CLASSES` pour deux raisons, aucune
    decorative : (a) nommer la classe NATIVE que l'instance materialisee mirrore, au lieu de la
    router sur `BaseEffect` ; (b) etre le foyer UNIQUE des trois litteraux de son `.ctor`, que le
    module de triggers relit.

    LES LITTERAUX DU `.ctor`, lus a l'ASSEMBLEUR (`WireweaveNet_CounterAttackEffect$$.ctor`) —
    le decompilateur masque l'immediat, d'ou la lecture par octets :

        mov edx, 0x457                      ; 1111
        call IdunBattle.Core.AbilityOrEffect$$op_Implicit    ; <- la surcharge @ +0x181669f80
        ...
        mov edx, 1        (turnsEnabled)
        mov r8d, 2        (activationFrequency)
        call IdunBattle.Entities.Effects.CounterAttackEffect$$.ctor

    * **La surcharge d'`op_Implicit` est tranchee par SON CORPS, jamais par son nom** : celle que le
      `call` designe appelle `IdunBattle.Core.AbilityOrEffect$$set_TriggeredAbility` (les trois autres
      homonymes ecrivent `set_ActiveAbility` / `set_Effect` / un 4e champ). Donc `0x457` est ici un
      **`TriggeredAbilityType`** (= le passif `WireweaveNet`), PAS un `ActiveAbilityType` ni un
      `EffectType` — meme si `WireweaveNetAbility$$GetEffectType` rend par ailleurs la MEME valeur
      numerique en `EffectType`. C'est l'exemple type de la qualification d'enum : deux enums,
      un seul nombre.
    * `CounterAttackEffect$$.ctor(turnsEnabled, activationFrequency, sourceAbility)` (signature LUE
      dans `frida/methods.tsv`, types `PlayerTurnEffect.TurnsEnabled` / `.ActivationFrequency`)
      delegue a `PlayerTurnEffect$$.ctor`, qui ecrit `this+0x484 = turnsEnabled`,
      `this+0x480 = activationFrequency` et passe `hasAutomaticActivation = (activationFrequency == 0)`
      a `BaseEffect$$.ctor` — donc **FALSE** ici.

    Ce que ces trois litteraux VALENT, lu chez leurs consommateurs :

    * `turnsEnabled = 1` -> `PlayerTurnEffect$$IsEnabledTurnType` prend la branche
      `op_LogicalNot(<DSLTriggers+0x28>)` = **`NOT IsTurnOf(Owner)`** (le slot `+0x28` est identifie
      `IsTurnOf(Owner)` par `docs/rl/case-366-r1-fire-and-reposition-reduce-dmg.md` §2). La valeur 0
      donnerait `IsTurnOf(Owner)`, la valeur 2 `<DSLTriggers+0x70>` (= un `YesTrigger`, cf. le `.ctor`
      de `DSLTriggers`). => la fenetre d'armement est le tour ENNEMI.
    * `activationFrequency = 2` -> la branche `(int)this+0x480 == 2` de
      `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal` : `On(TurnStart_EffectActivation) &
      IsTurnOf(Owner) -> DeactivateEffect` et `On(TurnEnd) & IsTurnOf(Owner) -> ActivateEffect`.
      (La branche `== 1` batit la paire SYMETRIQUE, avec `IsEnabledTurnType` au lieu d'`IsTurnOf`.)
    * `hasAutomaticActivation = False` -> l'instance ne s'arme pas d'elle-meme a la pose ; c'est le
      `If(NOT IsTurnOf(Owner)) -> ActivateEffect(Owner, 1111)` que `WireweaveNetAbility$$CreateBehaviour`
      ajoute a son `AddEffect` qui l'arme quand la pose tombe pendant un tour ennemi.
    """

    # Litteraux du `.ctor` (cf. docstring). Foyer UNIQUE : le module de triggers les relit, il ne
    # les re-code pas.
    TURNS_ENABLED = 1              # `PlayerTurnEffect.TurnsEnabled` -> `NOT IsTurnOf(Owner)`
    ACTIVATION_FREQUENCY = 2       # `PlayerTurnEffect.ActivationFrequency` -> Deactivate@TurnStart / Activate@TurnEnd
    HAS_AUTOMATIC_ACTIVATION = False   # `BaseEffect$$.ctor(hasAutomaticActivation = (freq == 0))`
    SOURCE_TRIGGERED_ABILITY = TriggeredAbilityType.WireweaveNet   # 1111 en `TriggeredAbilityType` (set_TriggeredAbility)
