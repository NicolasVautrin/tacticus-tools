# case-448-r1-r1 — `FullThrottleAbility$$CreateTrigger` : le gate qui manquait, et le verrou `MovementSteps` levé OFFLINE

`#448-r1-r1`. Le **behaviour** de `1134 FullThrottle` était porté depuis #532 (face exercée par
`StormboyzStrike_MissAbility` via le nœud `TriggerAbility`, qui court-circuite `ShouldTrigger`).
Le **`CreateTrigger`** — le passif autonome « pousser les gaz peut faire lâcher le jetpack » — ne
l'était pas : `full_throttle.py` le documentait comme RÉSIDU NOMMÉ, avec pour cause un verrou de RE
réputé infranchissable offline.

**Ce verrou n'existait pas.** Il tombe par une lecture de table, sans runtime.

---

## 1. Le verrou annoncé, et pourquoi il était faux

L'état de l'art (`full_throttle.py`, en-tête, avant cette tranche) :

> la formule `IdunBattleLogic.Entities.DSLFormulas$$MovementSteps()` alloue une classe dont le
> `.ctor` ne prend QU'UN argument (un champ mis a `0`) et dont **aucun nom n'apparait dans les
> tables de symboles** [...] il faudrait lire son slot `Calculate` au RUNTIME.

Les deux premières affirmations sont exactes. La troisième est **fausse**, et la conclusion avec
elle. La classe s'appelle `IdunBattle.DSL.MovementStepFormula`, et elle est dans `classes.tsv` :

    IdunBattle.DSL.MovementStepFormula                        16   IdunBattle.DSL.ASimpleAmountFormula
    IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula     24   IdunBattle.DSL.ASimpleAmountFormula
    IdunBattle.Entities.Formulas.TilesMovedLastTurnFormula     24   IdunBattle.DSL.ASimpleAmountFormula

**La recherche avait porté sur le mauvais namespace** : les deux formules de comparaison vivent
sous `IdunBattle.Entities.Formulas.*`, celle-ci sous `IdunBattle.DSL.*`. Chercher
`Formulas.MovementSteps*` ne pouvait pas la rendre.

Deux corroborations indépendantes, toutes deux LUES :

* **La taille**. `MovementStepFormula` = **16** octets = l'en-tête d'objet seul, **aucun champ
  d'instance** ; les deux `TilesMoved*` = 24 = en-tête + un champ (le sélecteur d'unité). C'est
  exactement l'asymétrie de ctor qui servait de verrou —
  `IdunBattleLogic.Entities.DSLFormulas$$MovementSteps` appelle `ctor(obj, 0)` tandis que
  `$$TilesMovedThisTurn` / `$$TilesMovedLastTurn` appellent `ctor(obj, unit, 0)`. Le `0` de queue
  est le `MethodInfo*` implicite : **`MovementStepFormula..ctor()` ne prend aucun paramètre**.
  ⚠ Les deux ctors sont mislabelés par ghidra (`UnityThreadUtilsInternal___ctor`,
  `RequiredByNativeCodeAttribute___ctor`) — corps triviaux dédupliqués. Le nom ne dit rien ; la
  **structure** (arité) et le **pointeur de classe** disent tout.
* **`Calculate` est nommé dans les DEUX tables** — `frida/methods.tsv` et `ghidra/functions.tsv` :

      IdunBattle.DSL.MovementStepFormula$$Calculate
          (entities: AbilityEntities, result: OperationResult) -> System.Int32

## 2. Ce que la formule LIT

`IdunBattle.DSL.MovementStepFormula$$Calculate`, corps entier :

    Nullable<int>.GetValueOrDefault( entities + 0x11c )

Et `AbilityEntities+0x11c` se nomme **`movementSteps`** — verbatim dans la signature du ctor à 33
paramètres d'`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` :

    (this, caster, actor, target, owner, casterTile, activePlayer, casterTiles, effect, targetTile,
     targetTiles, activeTarget, previousActiveTarget, currentAbilityOrEffect, parentAbilityOrEffect,
     triggerAbilityOrEffect, damageReason, damageProfile, usedDamageProfiles, appliedDamageProfiles,
     healthDamage, initialDamage, totalDamage, wasCrit, wasBlock, blockedHits, wasOverkilled,
     hitIndex, hitGroupIndex, isFirstDamagingHit, **movementSteps**, individualHitDamage,
     hasUsedAttackDamage)

⇒ **`MovementSteps()` n'est PAS « les tuiles parcourues ce tour ».** C'est une donnée de
l'**ÉVÉNEMENT** : le nombre de pas du mouvement qui vient d'être joué, porté par l'`AbilityEntities`
de cet événement-là. La supposition que la doctrine interdisait aurait donc été **fausse** — et
c'est précisément pourquoi elle était interdite.

`GetValueOrDefault()` : un `Nullable` vide rend **0**. Tout émetteur de `On(0x24)` qui ne renseigne
pas `movementSteps` rend donc un gate FAUX (`0 >= 3` est faux), sans erreur.

## 3. L'émetteur

`IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers(this, unit, position,
previousPosition, movementSteps, isInterimStep, triggeringAbilityOrEffect)` :

    ns = new Nullable<int>(movementSteps)
    entities = new AbilityEntities(unit, unit, unit, ..., movementSteps: ns, ...)
    Evaluate(On(0x24 = UnitPositionChanged_1))
    if (isInterimStep) return                       # <- les DEUX suivants sont sautes
    Evaluate(On(4 = UnitAfterMove))
    Evaluate(On(0x1d = UnitPositionChanged_2))

C'est le SEUL des trois events after-move à être émis sur un pas intermédiaire, et c'est justement
celui que `FullThrottleAbility$$CreateTrigger` écoute.

## 4. L'arbre natif, relu en entier

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FullThrottleAbility$$CreateTrigger` :

    On(0x24 = UnitPositionChanged_1, true)
      & get_OwnerIsActor
      & AmountIsEqualOrGreater( MovementSteps(),
                                Direct(GetNumberConstant(0x51 = 'movement')) )

`FullThrottle.constants` (gameconfig) = `{movement: 3, chance: 30}`, sans ambiguïté de résolution.

`$$CreateBehaviour` (déjà porté, #532) :

    If( Maybe(GetNumberConstant(0x2a = 'chance')), Kill(Caster, Caster, ForDirectKill), null )

---

_(suite : cadence d'émission, port, mesures — en cours de rédaction)_
