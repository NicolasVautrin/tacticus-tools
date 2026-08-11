"""Mirror de l'enum natif `IdunBattle.Operations.ActiveAbilityOperation.InvalidTargetPolicy`
(build `rnca9r7q6c`, `data/symbols/<build>/frida/enums.tsv` : `1=Allow,2=Skip,3=Error`).

C'est le champ `+0x00` des `UseActiveAbilityBehaviourOptions` -- un `System.Nullable<enum 4 octets>`
que `IdunBattleLogic.Entities.DSLBehaviors$$UseNormalAttackIfAble` et
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AutoCounterAttackAbility$$CreateBehaviour`
posent tous deux a `Skip`, et que `$$UseNormalAttack` laisse a `null`. #889-r5-r2.

CHAINE LUE DE BOUT EN BOUT (c'est ce qui leve le residu ; le nom << IfAble >> ne suffisait pas) :

  * `UseActiveAbilityBehaviour$$.ctor` range `options` en `this+0xa0..0xb3` (le ctor est NOMME :
    `(this, caster, target, activeAbilityType, parentAbility, triggerAbilityOrEffect, options)`) ;
  * `UseActiveAbilityBehaviour$$Execute` recopie `this+0xa0` en TETE de la struct passee au slot 2
    `IOperationProcessor.ActiveAbility(caster, target, abilityType, options)` ;
  * `ActiveAbilityOperation$$Execute` recopie les 0x58 octets et delegue a `$$ExecuteInternal` ;
  * `$$ExecuteInternal` lit `options+0x00`, prend `GetValueOrDefault` -- **le defaut est `Error`** --
    et le passe en 6e argument d'`ActiveAbilityOperation$$IsInvalidTarget`, dont la signature NOMME
    le parametre `invalidTargetPolicy` (le 7e, `options+0x08`, est un `ExecutionType` de defaut
    `StartAbility` ; aucun call-site porte ne l'ecrit, il n'a donc pas de mirror ici).

CORPS d'`$$IsInvalidTarget`, verbatim -- et c'est LUI qui donne la semantique :

    if (invalidTargetPolicy == Allow) return false;          # gate COURT-CIRCUITE
    ...
    if (!IBrokenTargetingRuleExtensions.IsInvalid(rule)) return false;
    if (invalidTargetPolicy != Error) return true;           # invalide, SANS log
    <LogError(...)>;                                         # invalide, AVEC log
    return true;

⇒ **`Skip` et `Error` rendent le MEME verdict** : seul le `LogError` les separe. Sur l'axe ETAT DE
BATAILLE, ecrire `Skip` ne change donc RIEN -- ce qui justifie a posteriori que le port n'ait
jamais invente de gate << seulement si l'unite PEUT attaquer >> : il n'y en a pas. La seule valeur
qui aurait un effet est `Allow`, et **aucun** call-site lu ne la pose.
"""
from enum import IntEnum


class InvalidTargetPolicy(IntEnum):
    #: La cible n'est JAMAIS declaree invalide (retour immediat `false`, avant meme de resoudre
    #: la regle de ciblage). Aucun call-site lu ne pose cette valeur.
    Allow = 1
    #: La regle de ciblage est evaluee ; si elle casse, la cible est invalide -- SANS log.
    #: C'est ce que posent `$$UseNormalAttackIfAble` et `AutoCounterAttackAbility$$CreateBehaviour`.
    Skip = 2
    #: Idem `Skip`, PLUS un `LogError`. C'est le DEFAUT du `Nullable` vide (`GetValueOrDefault`),
    #: donc le regime de `$$UseNormalAttack` et de la voie JOUEUR quand le message ne dit rien.
    Error = 3
