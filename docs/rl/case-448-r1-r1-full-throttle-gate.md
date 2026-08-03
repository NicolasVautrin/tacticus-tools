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

## 5. La cadence, et le `+1` qui déplace le seuil

`list_xrefs` sur `EvaluateAfterMoveTriggers` : **exactement deux `CALL`**, tous deux dans
`IdunBattle.Operations.MoveUnitOperation$$Execute`, **aucun dans une boucle** (la boucle par tuile
d'`IdunBattle.Operations.MoveUnitOperation$$AddMoveEvent` n'en contient pas). Un mouvement n'émet
donc **pas** un `On(0x24)` par pas.

| site | garde | `movementSteps` |
|---|---|---|
| A | branche dégénérée (`position.Count == 0`) | `0` littéral |
| B | fin du mouvement normal | `IsLikeFlying ? distance(path.First(), path.Last()) : **path.Count**` |

**`path.Count`, pas le nombre de pas.** `path[0]` est la tuile de DÉPART (la boucle `AddMoveEvent`
démarre à `i = 1`), et le helper que le jeu utilise ailleurs pour compter les tuiles PARCOURUES,
`IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(path)`, rend `path.Count - 1`.

⇒ deux lectures possibles, et elles ne diffèrent **que** sur un mouvement de 2 pas :

* **H_COUNT** — `movementSteps = pas + 1` : le gate `>= 3` mord dès **2 pas**.
* **H_STEPS** — lecture naïve « movementSteps = nombre de pas » : il mord à **3 pas**.

`IdunBattle.Operations.MoveUnitOperation$$IsLikeFlying(unit, options)` =
`IdunBattle.Entities.UnitExtensions$$IsLikeFlying(unit) || options.<+0x8> == 3`. Les deux branches
sont **asymétriques** côté natif — la branche volante rend une DISTANCE, sans le `+1`. Le port les
mirrore telles quelles ; le second bras d'`IsLikeFlying` (override porté par la struct `options`)
n'est posé par aucun call-site du port. RÉSIDU NOMMÉ.

## 6. La mesure — H_STEPS RÉFUTÉE

Montage : greffe (`catalog_inject.graft_passive_ability`) sur **5 unités du pool**
(`orksNob` Movement 4, `orksWarboss`, `orksRuntherd`, `orksBigMek`, `orksKillaKan`) —
`orksNpc6Stormboy` est le seul porteur et il est npc. Board `MC1_67`, seed 777, `--no-ai`.
La mort est relue **immédiatement après le move**, avant toute action adverse.

| pas | `path.Count` | H_COUNT prédit | H_STEPS prédit | **NATIF mesuré** | PORT | PORT sans le `+1` |
|---|---|---|---|---|---|---|
| 1 | 2 | faux → 0 | faux → 0 | **0 / 15** | 0,0 % | 0,0 % |
| 2 | 3 | vrai → ~30 % | **faux → 0** | **3 / 10 (30 %)** | 33,5 % | **0,0 %** |
| 3 | 4 | vrai → ~30 % | vrai → ~30 % | **4 / 10 (40 %)** | 26,0 % | 26,0 % |

Les deux bords sont tranchés, et chacun exclut une hypothèse :

* `P(0 mort sur 15 | gate vrai) = 0,7^15 = 0,47 %` → le gate est bien **faux à 1 pas** ;
* `P(3 morts sur 10 | gate faux) = 0` → le gate est bien **vrai à 2 pas**.

⇒ **H_COUNT confirmée.** La lecture naïve — celle qu'un port « raisonnable » aurait écrite — est
réfutée par la mesure. Le seuil affiché par le kit (`movement: 3`) n'est **pas** le seuil en pas.

**CONTRE-ÉPREUVES, toutes deux mordantes et à cause établie :**

* `--mutate` (gate neutralisé, `matches -> True`) : l'étape 0 rougit sur les **4** valeurs sous le
  seuil + le test d'acteur (5 anomalies, rc 1). C'est le port qu'on obtiendrait en inscrivant
  l'ability sans lire son `CreateTrigger`.
* `--mutate-steps` (le `+1` retiré = H_STEPS) : le bras **L=2 s'effondre à 0 %**, et **uniquement
  lui** (L=1 et L=3 inchangés à 0,0 % et 26,0 %). La mutation mord exactement là où la mesure
  discrimine — c'est ce qui garde l'off-by-one.

## 7. Le port

* `TriggerEvent.movement_steps` — mirror du `Nullable<int>` `AbilityEntities+0x11c`. `None` = le
  Nullable VIDE : les lecteurs rendent **0** (ce que fait `GetValueOrDefault()`), ils ne « se
  taisent » pas. C'est fidèle, et les trois émetteurs qui laissent le champ nul en dépendent.
* `runner/operations/movement.py::_movement_steps` — les deux branches natives.
* `MoveUnitOperation.last_movement_steps` — publié par l'opération (son entrée, la position de
  départ, n'existe plus après), consommé par `MovementHandler` qui le threade aux **trois** events
  after-move (le natif construit un seul `AbilityEntities` pour les trois).
* `FullThrottlePassiveAbility` + `ABILITY_TRIGGERS["FullThrottle"]`.

**Le tirage PRNG ne se fait que si le gate passe** : inscrire ce trigger change le nombre de
`NextBool` consommés — même nature que le gate manquant de #448-r1, qui DÉCALAIT la séquence.

## 8. Ce que la tranche ne mirror PAS, nommément

* **La branche VOLANTE elle-même** (`IsLikeFlying` → distance) est portée mais **NON CONFRONTÉE** :
  les trois bras du §6 sont tous des MARCHEURS. Elle n'a pas le `+1`, donc à gate égal un volant
  doit franchir **3** hexes là où un marcheur en franchit **2** — l'écart d'un pas que la mesure
  actuelle ne discrimine pas. Canal qui l'établirait : greffe sur un porteur `Flying`/`Burrow` du
  pool, mêmes trois bras (`#448-r1-r1-r1`).
* **Le second bras d'`IsLikeFlying`** (`options.<+0x8> == 3`) : la struct `options` d'`Execute`
  n'est pas modélisée et aucun call-site du port ne la pose.
* **`path` vs `connectedPath`** : le natif tire `movementSteps` de `path` (8e out-param de
  `CalculatePaths`) et `RecordTilesMoved` compte `connectedPath` (le 9e) — deux listes. Le port
  n'en matérialise qu'une ; elles ont la même longueur sur un chemin de marche ordinaire et
  divergent là où `MovementQuery$$GetConnectedPathTo` DENSIFIE (téléporteurs/sauts).
* **Le mouvement NUL** (`from == to`) : le natif aurait `path.Count == 1`, le port rend `0`.
  Inobservable — le seul lecteur exige `>= 3`.
* **Le site A** (branche dégénérée `position.Count == 0`, `movementSteps = 0` littéral) : le port
  n'a pas cette branche ; sa valeur y serait `0` de toute façon.

## 9. Un faux coupable, et pourquoi il ne l'est pas

Le volet PORT a d'abord rendu **0 mort sur 200 essais** là où le natif en tue 30 %. Diagnostic par
étage : le gate était bon, `_movement_steps` rendait bien `3` pour 2 pas — mais
`collect_triggered_abilities` instanciait **0** `FullThrottlePassiveAbility`, parce que
`UnitContext.passive_abilities` valait `None`, donc la dérivation retombait sur le gameconfig par
`visualId` (où `orksNob` porte `SmashaEad`).

**Ce n'est pas un trou du moteur.** La suite live lie le transport comme AMBIANT
(`snapshot.bind_live_rpc`, fixture `rpc` du conftest, #363) et `load_state` va alors chercher
`unitAbilityStates` d'elle-même. Le trou est propre aux **appelants sans ce binding** — un probe
autonome. Il est réparé par un `ability_states=` explicite, et le test live le garde à l'étage 3.

## 10. Reproduction

    python scripts/python/probe_448_r1_r1_full_throttle.py --offline       # etape 0 (0 runner)
    python scripts/python/probe_448_r1_r1_full_throttle.py --mutate        # contre-epreuve GATE
    python scripts/python/probe_448_r1_r1_full_throttle.py --lens 1,2,3    # les 3 bras NATIFS
    python scripts/python/probe_448_r1_r1_full_throttle.py --port          # chaine PORT
    python scripts/python/probe_448_r1_r1_full_throttle.py --port --mutate-steps   # contre-epreuve SEUIL
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_full_throttle_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_full_throttle_live.py
