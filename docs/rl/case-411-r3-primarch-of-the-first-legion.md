# case-411-r3 — `1511 PrimarchOfTheFirstLegion` : le RNG du transfert, lu et porté

> Tâche **#418 (#411-r3)**. La fiche porte le nom `case-411-r3-*` et non `case-418-*` :
> `docs/rl/case-418-r1-is-effect-target.md` existe déjà et désigne une tâche SANS RAPPORT
> (`IsEffectTarget`). La filiation `#411-r3` est celle du brief, et elle est sans ambiguïté.

> Résidu nommé en §7 de `case-411` : « **NON PORTÉ, délibérément.** Son `transferTarget` sort d'un
> `AdjacentFriends → UnitsFromFaction(0xa) → Randomize → SortByFormula → First` : le `Randomize`
> **consomme du RNG** et l'ordre du pool source n'est pas lu. Le porter sans cette lecture donnerait
> un port au flux RNG faux — c'est-à-dire pire que pas de port. »
>
> **Les deux lectures manquantes sont faites** (§2, §3), **une affirmation de `case-411` est
> RÉFUTÉE** (§1.1), et le port est **LIVRÉ et CONFRONTÉ** (§5, §6).

## 1. L'arbre natif, de bout en bout

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PrimarchOfTheFirstLegionAbility$$CreateTrigger` :

```
On(EventTriggerType.PreAttackDamageHit = 7, ownerNeedsToBeAlive: <littéral 1>)
  & AreEqual(Owner@DSLSelectors+0x30, Target@DSLSelectors+0x60)
  & AmountIsOdd(CurrentHitIndex)
```

`...PrimarchOfTheFirstLegionAbility$$CreateBehaviour` :

```
target = Cache(
           First(
             SortByFormula(
               Randomize(UnitsFromFaction(AdjacentFriends(Owner@+0x30, unique:1, selType:3),
                                          faction: 0xa = DarkAngels, selType:3)),
               If(Contains(GetPersistentDataListAsEntities(<this>, Owner@+0x30, <key>),
                           It@DSLSelectors+0x68),
                  <DSLFormulas+0x18 = 0>, <DSLFormulas+0x20 = 1>),
               ascending: 0  → DESCENDANT),
             amount: 1, ignoreForcedTargets: 0),
           matchAbilityEntities: 1)

return If(AmountIsGreaterThanZero(target),
            Inform({0x83: TriggerBoolNumber(AmountIsEqual(CurrentHitIndex, <+0x20 = 1>))})
          & TransferHit(Caster@+0x48, Target@+0x60, target, <this>)
          & IfAlive(target,
                      AddEffect(0x5f3 = 1523, <abilityStateRef>, target,
                                TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)))
                    + AddToPersistentDataList(<this>, Owner@+0x30, Get(<key>), EntityId(target))),
          null)
```

Recoupé, arête par arête, par une seconde source indépendante : `docs/rl/dsl-usage/dsl-usage-edges.tsv`
donne **33 arêtes** pour les trois artefacts `PrimarchOfTheFirstLegion*` — toutes retrouvées, aucune
en trop.

`...PrimarchOfTheFirstLegion_EndTurnAbility$$CreateBehaviour` = `ClearAllPersistentData(<this>,
Owner@+0x30)` (la purge de la mémoire anti-répétition). Son **trigger n'est pas lisible** — §7.

`IdunBattle.Entities.Effects.Loki.PrimarchOfTheFirstLegion_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
= `EffectBonus.ForAddition(get_OwnerIsCaster, ConfigVar(8 = extraDmg, <abilityState>))`.

### 1.1 Deux écarts avec `1109 DrawFire`, et une RÉFUTATION

| | `1109 DrawFire` | `1511 PrimarchOfTheFirstLegion` |
|---|---|---|
| position du porteur | `!AreEqual(Owner, Target)` — un **ALLIÉ ADJACENT** du défenseur | `AreEqual(Owner, Target)` — le porteur **EST** le défenseur |
| `ownerNeedsToBeAlive` | retour d'un **virtuel** (slot `+0x298`), non résolu | **littéral `1`** — lu, pas supposé |
| gates de camp | `AreFriends` + `IsAdjacent` + `AreEnemies` | **aucun** — un allié qui frappe le porteur déclenche aussi |
| `transferTarget` | `Owner` (le porteur lui-même), **0 tirage** | un tirage dans le voisinage Dark Angels |

⚠ **RÉFUTATION de `case-411` §6.2**, qui écrivait : « `PrimarchOfTheFirstLegion` n'a pas d'`AmountIsOdd`
— sa garde reste **NON LUE** ». C'est **faux**. `CreateTrigger` porte bien `AmountIsOdd(CurrentHitIndex)`
en troisième conjoint (`DSLTriggers$$AmountIsOdd`, confirmé aussi par `dsl-usage-edges.tsv`).
L'anti-récursion est donc **exactement celle de DrawFire** : `TransferHitOperation$$Execute` pose
`opts[+0x2E] = 1` (`isOutsideAttack`), l'attaque de transfert est SÉPARÉE et son compteur de coups
repart à `0`, or `AmountIsOdd(0)` est faux. Rien à inventer.

## 2. Le `Randomize` — la première lecture manquante

`IdunBattleLogic.Entities.DSLSelectors$$Randomize(x)` construit un
`IdunBattle.Entities.Selectors.PickRandomAmountSelector` avec **cinq littéraux qu'il écrit lui-même** :

```
PickRandomAmountSelector(state, x, requestedAmount: 0x7fffffff, random,
                         allowDuplicates: false, maxDuplicatesAllowed: 0x7fffffff,
                         ignoreForcedTargets: false)
```

et `...PickRandomAmountSelector$$Select` :

```
candidates = source.Select(ctx).ToList()
picked = new List<T>()
if (!ignoreForcedTargets) AddForcedTargetsAndUpdateCandidates(...)   # no-op sans forced target
for (i = picked.Count ; i < requestedAmount ; i++) {
    if (candidates.Count < 1) return picked                          # LA sortie effective
    idx = random.Next(0, candidates.Count)                           # <-- LE TIRAGE
    picked.Add(candidates[idx])
    if (!allowDuplicates) candidates.RemoveAt(idx)
}
```

`requestedAmount` valant `int.MaxValue`, la boucle ne s'arrête que par épuisement :

> **pool de N ⇒ N tirages**, de bornes DÉCROISSANTES `N, N-1, …, 1`. **Pool vide ⇒ 0 tirage.**

⚠ **Le dernier tirage n'est pas court-circuité.**
`IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$IdunBattle.Utils.PRNG.IPseudoRNG.Next(min, max)` est
**`[min, max)` exclusif** et attaque directement `genrand_int32()` : à `range == 1` il prend la branche
puissance-de-2, consomme un `genrand_int32` et rend toujours `0`. **Un pool d'UNE unité coûte donc UN
tirage** — celui qui ne discrimine aucune valeur, et que seul un ledger attrape.

⚠ Ne pas confondre avec `IdunBattle.Utils.PRNG.MersenneTwister$$Next(minValue, maxValue)`, qui est
**INCLUSIF** (`hi - lo + 1`) et passe par `genrand_real2()`/Fix64. Ce n'est pas la surcharge appelée
ici : le sélecteur passe par l'**interface** `IPseudoRNG`, dont l'implémentation `IntBasedMersenneTwister`
est celle que le port mirrore (`engine/runner/prng.py::next_internal`).

### 2.1 Le `Cache` ne fait PAS économiser de tirages entre deux coups

`Cache(x, matchAbilityEntities: 1)` → `IdunBattle.Entities.Selectors.CacheSelector$$Select` mémoïse
dans un `Dictionary<AbilityEntities, List<T>>` **keyé par le contexte**. Or
`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` — dont les **33 paramètres sont nommés dans la
métadonnée** — place `hitIndex` à **`+0x108`**. La clé change donc à chaque coup.

⇒ le cache mord **à l'intérieur d'un déclenchement** (`target` est lu **six** fois dans l'arbre : la
condition du `If`, `TransferHit`, `AddEffect`, `IfAlive`, `EntityId`, et la cible de
`AddToPersistentDataList`), **jamais entre deux coups**. Une évaluation, donc **N tirages, par
déclenchement**.

Disposition complète de la struct, lue du ctor (utile bien au-delà de ce cas) :
`+0x08 caster · +0x10 target · +0x18 owner · +0x20 activeTarget · +0x28 previousActiveTarget ·
+0x30 targetTile · +0x38 targetTiles · +0x40 casterTile · +0x48 casterTiles · +0x50 activePlayer ·
+0x58 effect · +0x60 currentAbilityOrEffect · +0x7c parentAbilityOrEffect · +0x98 triggerAbilityOrEffect ·
+0xb4 damageReason · +0xbc damageProfile · +0xc8 usedDamageProfiles · +0xd0 appliedDamageProfiles ·
+0xd8 initialDamage · +0xe0 healthDamage · +0xe8 totalDamage · +0xf0 individualHitDamage ·
+0xf8 wasCrit · +0xf9 hasUsedAttackDamage · +0xfa wasBlock · +0xfc blockedHits · +0x104 wasOverkilled ·
+0x108 hitIndex · +0x110 hitGroupIndex · +0x118 isFirstDamagingHit · +0x11c movementSteps`.

La seconde surcharge, `AbilityEntities$$.ctor(entities, activeTarget)`, **recopie tout et remplace le
seul `activeTarget@+0x20`** : c'est ce que fait `SortByFormulaSelector` pour lier l'élément courant —
ce qui **confirme** que `DSLSelectors+0x68` (`It`) lit bien ce slot.

## 3. L'ORDRE du pool — la seconde lecture manquante

C'est lui qui décide **qui** est pioché, le `Randomize` ne tirant qu'un **index** dans la liste
source. La chaîne, lue de bout en bout :

```
AdjacentFriends(X, unique, selType)
  = Friends(reference: X, Units(AdjacentTiles(X), unique, selType) - X, selType)     # surcharge 4-args

AdjacentTilesSelector$$Select :
    result = new OrderedSet<Tile>()                 # ORDRE D'INSERTION préservé
    origins = <selecteur d'origine>.Select(ctx).ToList()
    foreach (o in origins)
        foreach (n in battleQuery.<slot 0x50>(o, 0, 1, 1))     # voisins à rayon 1
            if (!origins.Contains(n)) result.Add(n)
    return result
```

`Units`/`Friends`/`UnitsFromFaction` sont des **filtres** (`UnitsOnTilesSelector` résout l'occupant
tuile par tuile, puis des `Where`) : **aucun ne retrie**. L'ordre du pool est donc celui de
l'énumération de voisinage du `BattleQuery`.

⇒ **c'est exactement l'ordre déjà porté** : `_within(..., order="adjacent")` de `engine/dsl/base.py`
(« liste d'adjacence STOCKÉE, `boardGraph.neighbours` brut » — R28-1). Le verrou nommé par `case-411`
était donc **déjà levé dans le dépôt** ; il fallait le constater, pas le construire.

### 3.1 Le tri, et ses deux constantes

`SortByFormulaSelector$$Select` : `ascending == 0` → **`OrderByDescending`** ; `!= 0` → `OrderBy`.
Les deux sont des tris LINQ, donc **STABLES** — l'ordre du mélange survit à l'intérieur d'une clé.

Les deux constantes de la formule viennent de `IdunBattleLogic.Entities.DSLFormulas$$.ctor`, qui
construit cinq formules-constantes : **`+0x18 = 0`**, **`+0x20 = 1`**, `+0x28 = 2`, `+0x30 = 100`,
`+0x38 = -1`.

⇒ `If(Contains(déjàServis, It), 0, 1)` + tri **descendant** = **les alliés PAS ENCORE SERVIS
passent devant**, à ordre de mélange préservé. C'est une mémoire anti-répétition, pas une préférence
de stat.

### 3.2 Les deux primitives que cela a fallu porter

* `IdunBattleLogic.Entities.DSLTriggers$$Contains(list, elements)` →
  `IdunBattle.Entities.Triggers.XContainsYTrigger$$ShouldTrigger` :
  `elements` passe par **`SelectSingle`** (0 ou >1 ⇒ **FALSE**), la comparaison est sur **`get_Id`**,
  et l'ordre des arguments est `Contains(CONTENANT, CONTENU)` (`+0x10` = la liste). **11 propriétaires
  natifs** (`dsl-usage-primitives.tsv`).
* `IdunBattleLogic.Entities.DSLSelectors$$GetPersistentDataListAsEntities(abilityOrEffect, unit, key)`
  → `IdunBattle.Entities.Selectors.EntitiesFromPersistentDataListSelector$$Select` : résout chaque id
  en entité (`GetEntity`, **null ⇒ silencieusement jeté**), filtre `MatchesUnitSelectionType(3)` sur
  les seules entités-UNITÉ, **sans aucun tri** — l'ordre est celui d'insertion.
  C'était le **résidu nommé de #354** (`runner/abilities/behaviours/persistent_data.py` : « le jour où
  un consommateur a besoin des ENTITÉS, le sélecteur entre ici »).

## 4. La face effet — `1523`, et la source qui n'est pas celle qu'on croit

`AddEffect` est appelé par la surcharge **4-args**
`DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns)`, qui passe **littéralement `0`**
en paramètre `source` du `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor` (la surcharge
5-args, elle, en pose un explicite). Or `AddEffectBehaviour$$Execute` fait, par cible,
`src = <cible> ; if (<sélecteur source> != null) src = <son résultat>` :

⇒ **sélecteur source nul ⇒ la source EST la cible** (`source_from_target` du port, déjà lu pour
`BrazierOfHolyFire` et `RadBombardment`). L'`abilityState`, lui, reste celui du **porteur de 1511**,
et c'est lui qui résout le `ConfigVar`.

L'effet : `ForAddition(get_OwnerIsCaster, ConfigVar(8 = extraDmg))` — **gate SEUL**. C'est l'écart
avec ses jumeaux `SmashaEad` / `FeederTendrils`, qui portent en plus `IsNormalAttack` et rendent donc
`None` en prédiction. Recopier leur `if is_prediction: return None` ici aurait été la faute inverse.
Durée : `TurnsFromRounds(GetNumberConstant(0x45))` = `nrOfRounds`, que le gameconfig donne à **1**.

## 5. Le PORT — LIVRÉ

| pièce | fichier | ce qu'elle mirrore |
|---|---|---|
| `Contains` | `engine/entities/triggers.py` | `XContainsYTrigger$$ShouldTrigger` |
| `EntitiesFromPersistentDataList` | `engine/entities/selectors/units.py` | `EntitiesFromPersistentDataListSelector$$Select` (+ accesseur `ctx.entity_by_id`) |
| `primarch_transfer_target_selector` | `engine/runner/operations/triggers/loki/primarch_first_legion.py` | l'arbre de ciblage 1:1 (§1) |
| `primarch_reward_tree` | idem | la branche `IfAlive(target, AddEffect + AddToPersistentDataList)` |
| `PrimarchTransfer` | idem | l'accroche per-coup, jumelle de `DrawFireTransfer` |
| `PrimarchOfTheFirstLegionExtraDamageEffect` | `engine/entities/effects/loki/extra_damage.py` | l'effet `1523` (§4) |

**La frontière DSL/impératif est celle de #149** : la STRUCTURE du ciblage (Randomize, tri, cache,
persistent-data) est un **arbre DSL** ; `TransferHit` reste **impératif** (ré-entrée dans
`AttackDamageOperation.execute`), exactement comme pour `1109` — parce que le bus du port émet
`On(6)`/`On(7)` une fois par **ATTAQUE** alors que le transfert se décide par **COUP**. Les deux
déclencheurs sont branchés dans le même intercepteur (`harlequins_panoply.py::should_transfer`).

## 6. Ce que la confrontation a mesuré

`probe_418_primarch_transfer.py` — greffe `darkaCompanion:PrimarchOfTheFirstLegion` (la VICTIME est
le porteur), `necroDestroyer` attaquant, board `MC1_67`, `--crit 0,0 --crit-target 0,0
--block-target 0,0`. Deux gardes de montage sont posées **avant** toute mesure : la configuration
d'adjacence est **vérifiée** après assemblage, et la bataille doit être **en cours** (`stageName !=
Finished`) avec toutes les unités vivantes.

```
TEMOIN (sans greffe)   NATIF victim=4061  alliés 0/0   PORT per_hit=[171, 928, 658, 797, 870]
GREFFE seed=31337      NATIF victim=2361  alliés 815/815
                       PORT per_hit=[171, 0, 48, 0, 724]  2 transferts, select_cost=4 (pool de 2)
GREFFE seed=777        NATIF victim=2473  alliés 815/815
GREFFE seed=4242       NATIF victim=1782  alliés 815/815
GREFFE seed=90210      NATIF victim=2520  alliés 815/815
GREFFE + hors faction  NATIF astraCreed=0 (jamais servi), alliés 815/815
```

Six propriétés, chacune **falsifiable**, toutes vertes :

1. **le natif transfère** — les alliés perdent des PV, la victime en perd **41 % de moins** qu'au
   témoin, et le bras TÉMOIN (identique à un bit près) est inerte ;
2. **le natif répartit sur les DEUX alliés** — signature observable de tout l'étage
   `SortByFormula(If(Contains(…), 0, 1), descendant)` + `AddToPersistentDataList`. Un port qui
   n'aurait porté que le `Randomize` servirait parfois deux fois le même ;
3. **le natif filtre sur la FACTION** — l'`astraCreed` adjacent ne perd **rien** ;
4. **l'effet `1523` est posé** sur l'allié servi ;
5. **le port a la même structure per-coup** — dégât nul aux indices IMPAIRS, non nul aux pairs ;
6. **le LEDGER** — `select_cost / 2` vaut **exactement la taille du pool** à chaque transfert : pas
   `1` (un `First` paresseux), pas `0` (un court-circuit « le pool tient déjà dans `amount` »), pas
   `2 × N` (un `Cache` qui ne mordrait pas).

Le compte de coups est **dérivé de la série mesurée**, pas supposé : `necroDestroyer` rend **5** coups
sur ce montage (donc 2 indices impairs, donc 2 transferts), pas 6.

### 6.1 Le bras qui falsifie l'ALÉA lui-même — MESURÉ

Avec **2 candidats et 2 transferts**, les deux sont servis à tous les coups : la mesure reste
compatible avec « le natif prend toujours le même ordre ». **Ce bras-là ne falsifie donc PAS
l'aléa**, et le dire est le point. Le probe ajoute un bras **`pool = 3`** (`darkaTerminator` en
troisième candidat) : 2 transferts pour 3 candidats, donc la **paire servie doit VARIER** d'un seed
à l'autre. Mesure, 4 seeds :

```
[pool3 natif] 31337 -> [darkaHellblaster, darkaTerminator]     [pool3 port] 31337 -> [79, 83]
              777   -> [darkaHellblaster, darkaTerminator]                   777   -> [79, 83]
              4242  -> [darkaAzrael,      darkaHellblaster]                  4242  -> [79, 83]
              90210 -> [darkaAzrael,      darkaHellblaster]                  90210 -> [79, 81]
```

**Deux paires distinctes de chaque côté** ⇒ le natif TIRE réellement (`Randomize` n'est pas un
no-op, les N tirages que le port consomme ne sont pas « de trop »), **et le port tire aussi**.
Sur ce bras, `select_cost = 6` ⇒ **pool de 3** ⇒ le ledger **suit la taille du pool**, ce n'est pas
une constante. Et sur les 4 seeds × 2 côtés, **aucun allié n'est servi deux fois** alors qu'un
candidat neuf restait disponible — c'est l'anti-répétition qui le garantit, pas le hasard
(`(2/3)^8 ≈ 4 %` sans elle).

⚠ Un premier jet re-seedait le MT du port à `777` **en dur** : sa VARIATION était alors
**inobservable**, et seule celle du natif était confrontée. Le probe seede désormais le port avec
le même entier que le build ; le check `port_TIRE_vraiment` existe pour ça, et il est le seul à
avoir manqué au premier passage.

**Verdict : 20 checks, `PORT CONFORME`.**

## 7. Ce qui n'est PAS couvert (résidus NOMMÉS)

* **`PrimarchOfTheFirstLegion_EndTurnAbility` — la purge, NON PORTÉE.** Son `CreateBehaviour` est lu
  (`ClearAllPersistentData(<this>, Owner)`), mais son **`CreateTrigger` est ABSENT des DEUX tables de
  symboles** (`data/symbols/rnca9r7q6c/frida/methods.tsv` **et** `ghidra/functions.tsv`) — corps
  dédupliqué, la classe héritant **directement** de `IdunBattle.Entities.Abilities.BaseTriggeredAbility`
  (lu dans `frida/classes.tsv`). Les deux autres `*_EndTurnAbility` du binaire
  (`PriorityReclamation`, `RadZoneCorps`) sont dans le même cas. **L'EVENT n'est pas lu** ; le poser
  serait une invention.
  **Conséquence, bornée et unilatérale** : la liste persistante ne se vide jamais. Une fois tous les
  candidats servis, `If(Contains, 0, 1)` rend `0` pour tous et le tri **redevient neutre** (stable) —
  le choix repasse au premier du mélange. **Le ledger RNG est INCHANGÉ** (même pool, même compte de
  tirages) ; seul le CHOIX peut diverger après saturation. Gardé par un test offline dédié.
* **`Inform({0x83: …})`** : écriture de contexte DSL sans consommateur identifié — même verdict que
  pour `1109`. Non porté (le bus n'est pas modélisé côté port).
* **`AddForcedTargetsAndUpdateCandidates`** : `ignoreForcedTargets = false` fait entrer la branche,
  mais elle est un no-op sans `GetOnlyTargets` sur le caster — verdict déjà rendu par le foyer
  `_pick_randomly_n` (#130/#215).
* **La collision `1109` × `1511` sur un MÊME coup** : les deux s'abonnent à `On(7)`, le natif évalue
  chaque abonné, et le premier qui s'exécute EFFACE le `Nullable<AttackHit>` (les suivants sortent sur
  `!HasValue`). Le port s'arrête de même au premier qui rend `True`, mais **l'ORDRE d'abonnement natif
  n'est pas lu**. Régime jamais atteint (il exigerait un porteur `DrawFire` adjacent à un porteur
  `1511` en train d'être frappé).
* **La face ABILITY** (`AbilityDamageOperation$$ExecuteHit`) : le câblage la couvre (même
  intercepteur), elle n'est pas confrontée — même état que `1109`.
* **Le niveau d'ability de l'effet `1523`** : le natif résout son `ConfigVar` contre l'`abilityState`
  du **porteur de 1511** ; le `BaseEffect` du port ne porte que celui de l'unité qui PORTE l'effet
  (l'allié). Sur le régime confronté (rangs normalisés identiques) les deux coïncident ; ils
  divergeraient à niveaux distincts. C'est le résidu **#68**, hérité, pas propre à ce port.
* **La `dataKey` littérale** du sac persistant : le natif la lit d'une globale initialisée au runtime
  (`DSLFormulas$$Get(<DAT>)`), que le dump statique ne résout pas. Elle est **inobservable** — la clé
  du port est composite `(abilityOrEffect, dataKey)`, `1511` n'en a qu'une, et les trois consommateurs
  portent la même.
