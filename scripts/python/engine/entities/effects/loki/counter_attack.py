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
`WarConstruct_CounterAttackEffect`, `WireweaveNet_CounterAttackEffect`. TROIS sont portes
(`WireweaveNet` #366-r1b, puis `GrimRetribution` + `UnwaveringSentinel` #946) ; restent
`SmashaSquigJaws_CounterAttackEffect` (1104) et `WarConstruct_CounterAttackEffect` (1286).

================================================================================================
CE QUE LE PATRON NE DIT PAS -- les ecarts MESURES entre les trois membres portes (#946)
================================================================================================
Le bloc `methodPointers` de chaque classe fait SIX slots, dans le MEME ordre pour les trois
(`.ctor · GetCounterAttackTargets · GetCounterAttackTrigger · GetCounterAttackCondition ·
GetCounterAttackBehaviour · GetDamage`) -- l'ordre est ETABLI, pas suppose : les corps PARTAGES par
ICF tombent a la position HOMOLOGUE de leur jumeau dans les trois blocs. Nombre de corps PROPRES :
2/6 pour `GrimRetribution`, 5/6 pour `UnwaveringSentinel`, 6/6 pour `WireweaveNet`.

| | WireweaveNet (1111) | GrimRetribution (1213) | UnwaveringSentinel (1439) |
|---|---|---|---|
| `activationFrequency` | **2** | **1** | **1** |
| fenetre d'armement | Deactivate@TurnStart(Owner) / Activate@TurnEnd(Owner) | Activate@TurnStart(ennemi) / Deactivate@TurnEnd(ennemi) | idem GR |
| cadence effective | **1 riposte par CYCLE** | **1 riposte par TOUR ENNEMI** | **1 riposte par TOUR ENNEMI** |
| `GetCounterAttackTrigger` | `On(PreUnitAbility)` -- riposte AVANT le coup | `On(Attack)` -- riposte APRES | `On(Attack)` (corps que GR PARTAGE) |
| `GetCounterAttackBehaviour` | `AttackDamage(...)` direct | `AttackDamage(...)` (corps de WW, PARTAGE) | `TriggerAbilityDelayed(Owner, 1449, OnlyAliveAndTargetable)` |
| `GetDamage` | `GetMinMaxDamage(0)` | idem (corps de WW, PARTAGE) | `<DSLFormulas+0x18>` -- **override MORT**, cf. plus bas |
| classe de l'ability source | `AOwnerEffectTriggeredAbility` | `AOwnerEffectTriggeredAbility` | **`BaseTriggeredAbility`** |
| l'ability override `CreateBehaviour` ? | OUI (ajoute `If(NOT IsTurnOf(Owner)) -> ActivateEffect`) | **NON** (2 slots : `.ctor` + `GetEffectType`) | OUI, et il BIFURQUE sur `triggerType` |

Une recopie du jumeau de forme aurait donc ete fausse sur SEPT axes.

`activationFrequency = 1` -> la branche `(int)this+0x480 == 1` de
`PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal`, qui est l'INVERSE de la branche `== 2` :

    On(TurnStart_EffectActivation) & IsEnabledTurnType()  ->  ActivateEffect(<Sel+0x38>)
    On(TurnEnd)                    & IsEnabledTurnType()  ->  DeactivateEffect(<Sel+0x38>)

et `PlayerTurnEffect$$IsEnabledTurnType` pour `turnsEnabled == 1` (`this+0x484`) rend
`op_LogicalNot(<DSLTriggers+0x28>)` = `NOT IsTurnOf(Owner)`. C'est litteralement le « During each
enemy turn » que l'i2 des DEUX passifs ecrit, la ou `WireweaveNet` dit « The first time ... during
the enemy's turn ».
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


class GrimRetributionCounterAttackEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.GrimRetribution_CounterAttackEffect`
    (`EffectType.GrimRetribution_CounterAttack` = 0x4bd = 1213) -- l'effet-RIPOSTE que le PASSIF
    `GrimRetribution` (`TriggeredAbilityType.GrimRetribution` = 0x499 = 1177) de `darkaHellblaster`
    (Sarquael) pose sur lui-meme.

    i2 : « During each enemy turn, if there is no enemy adjacent to Sarquael, he shoots back at the
    first enemy within range that attacked him or a friendly adjacent Dark Angel. This shot counts as
    Overwatch and deals 1x 2183-2619 Plasma Damage. »

    COMME sa soeur `WireweaveNetCounterAttackEffect`, cette classe N'A AUCUN CANAL DE BONUS : tout le
    comportement observable vit dans les `Triggered()` de
    `runner/operations/triggers/loki/grim_retribution.py` (registre `EFFECT_TRIGGERS[1213]`). Elle
    existe pour NOMMER la classe native mirroree et pour etre le foyer UNIQUE des trois litteraux de
    son `.ctor`.

    LES LITTERAUX DU `.ctor`, lus a l'ASSEMBLEUR (`GrimRetribution_CounterAttackEffect$$.ctor`) --
    le decompilateur masque l'immediat :

        xor  r8d, r8d
        lea  rcx, [rsp+0x30]                ; buffer de retour de la struct
        mov  edx, 0x499                     ; 1177
        call IdunBattle.Core.AbilityOrEffect$$op_Implicit    ; <- la MEME surcharge que WireweaveNet
        ...
        mov  edx, 1        (turnsEnabled)
        mov  r8d, edx      (activationFrequency = 1)         ; <- ECART : WireweaveNet a 2
        call IdunBattle.Entities.Effects.CounterAttackEffect$$.ctor

    * La surcharge d'`op_Implicit` est tranchee par l'ADRESSE REELLE de la cible du `call`
      (`E8 rel32` decode) : c'est le MEME corps que celui du `.ctor` de `WireweaveNet`, celui dont la
      docstring ci-dessus etablit qu'il ecrit `set_TriggeredAbility`. Donc `0x499` est un
      **`TriggeredAbilityType`** -- et la qualification MORD ici : `EffectType 1177` nomme
      `SereneUnifierZephyrsGrace_Visual`, rien a voir.
    * `activationFrequency = 1` : cf. le tableau d'ecarts en tete de module. C'est le SEUL litteral
      qui differe de `WireweaveNet`, et il change la CADENCE de la riposte.
    """

    TURNS_ENABLED = 1              # `PlayerTurnEffect.TurnsEnabled` -> `NOT IsTurnOf(Owner)`
    ACTIVATION_FREQUENCY = 1       # -> Activate@TurnStart(ennemi) / Deactivate@TurnEnd(ennemi)
    HAS_AUTOMATIC_ACTIVATION = False   # `BaseEffect$$.ctor(hasAutomaticActivation = (freq == 0))`
    SOURCE_TRIGGERED_ABILITY = TriggeredAbilityType.GrimRetribution   # 1177 (set_TriggeredAbility)


class UnwaveringSentinelCounterAttackEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.UnwaveringSentinel_CounterAttackEffect`
    (`EffectType.UnwaveringSentinel_CounterAttack` = 0x59f = 1439) -- l'effet-RIPOSTE que le PASSIF
    `UnwaveringSentinel` (`TriggeredAbilityType.UnwaveringSentinel` = 0x5a9 = 1449) de `custoKyrus`
    (Tyrith) pose sur elle-meme.

    i2 : « During each enemy turn, after Tyrith is attacked and the attacker is within range 2, she
    deals 2x 1601-2183 Bolter Damage to the attacker. If there is an enemy adjacent to Tyrith, the
    range of this ability is reduced to 1. »

    ⚠ **1439 != 1449** : contrairement a `WireweaveNet` (ou `0x457` vaut des DEUX cotes), l'effet et
    l'ability portent ici des ordinaux DIFFERENTS, et chacun ment dans l'autre enum --
    `TriggeredAbilityType 1439` = `NovaShield_BlockVisual`, `EffectType 1449` =
    `MoreGitzOverEre_ExtraDamagePct`. C'est exactement le regime ou une confusion d'enum serait
    SILENCIEUSE en ordinal.

    LES LITTERAUX DU `.ctor`, lus a l'ASSEMBLEUR -- le corps est byte-pour-byte celui de
    `GrimRetribution` a l'immediat pres :

        mov  edx, 0x5a9                     ; 1449 en TriggeredAbilityType
        call IdunBattle.Core.AbilityOrEffect$$op_Implicit    ; MEME surcharge (set_TriggeredAbility)
        mov  edx, 1 ; mov r8d, edx          ; turnsEnabled = 1, activationFrequency = 1
        call IdunBattle.Entities.Effects.CounterAttackEffect$$.ctor

    ⚠ **`GetDamage` est un OVERRIDE MORT, et c'est un RESULTAT, pas un oubli.**
    `UnwaveringSentinel_CounterAttackEffect$$GetDamage` rend `<DSLFormulas+0x18>` (un noeud-formule
    singleton du service), et le slot de vtable `+0x758` qu'il occupe n'a QU'UN consommateur :
    `CounterAttackEffect$$AttackDamage`. Or cette classe n'emprunte JAMAIS ce chemin -- son
    `GetCounterAttackBehaviour` fait un `TriggerAbilityDelayed`, pas un `AttackDamage`. Le dégât
    vient donc de l'ABILITY (`BaseTriggeredAbility$$MinMaxDamage/GetHits/GetDamageProfile`), pas de
    l'effet. Meme remarque pour `GetCounterAttackTargets` (slot `+0x768`), lu par la seule
    `AttackDamage` : le corps existe (partage avec `WireweaveNet`) et n'est pas consomme.
    """

    TURNS_ENABLED = 1              # `PlayerTurnEffect.TurnsEnabled` -> `NOT IsTurnOf(Owner)`
    ACTIVATION_FREQUENCY = 1       # -> Activate@TurnStart(ennemi) / Deactivate@TurnEnd(ennemi)
    HAS_AUTOMATIC_ACTIVATION = False   # `BaseEffect$$.ctor(hasAutomaticActivation = (freq == 0))`
    SOURCE_TRIGGERED_ABILITY = TriggeredAbilityType.UnwaveringSentinel   # 1449 (set_TriggeredAbility)
