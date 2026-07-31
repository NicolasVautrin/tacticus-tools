# #350-r3b — la couche TRIGGERED et ses DEUX formes de moyenne

Symétrique de #350 (couche ACTIVE, `docs/rl/case-350-formes-de-moyenne-lues.md`) et de #344.
Build lu : `rnca9r7q6c`. Tout ce qui suit est **dérivé des xrefs entrantes**, pas hérité.

## 1. Les deux constructeurs natifs — ils rendent un NŒUD, pas un scalaire

`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage(this, abilityState)`
lit les variables `0xc` (`minDmg`) et `0xd` (`maxDmg`) de `this@+0x20` par
`IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel`, puis rend

    IdunBattleLogic.Entities.DSLFormulas$$RandomAmount(Get(minDmg), Get(maxDmg))     # nœud à PLAGE

`BaseTriggeredAbility$$MinMaxDamageAverage(this, abilityState)` lit **les mêmes** `0xc`/`0xd`
et rend

    Half( Sum( Direct(minDmg), Direct(maxDmg) ), roundingRule = 0 )                  # nœud SIMPLE

(`BaseTriggeredAbility$$MinMaxDamage2` est la même chose sur `0x36`/`0x37` = le second couple de
variables ; 5 appelants, tous des `CreateBehaviour` — aucun playbook, hors périmètre.)

⚠ **La forme d'arrondi ne sort donc PAS d'un helper choisi à la main : elle sort de la STRUCTURE du
nœud croisée avec le SLOT d'`IAmountFormula` que le playbook invoque.**

## 2. Le slot décide — mesuré call-site par call-site

Les playbooks invoquent l'interface par `FUN_180025fb0(<slot>, <IAmountFormula>, <nœud>, …)`.

| Playbook (call-site) | getter appelé | nœud | slot | arrondi |
|---|---|---|---|---|
| `IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction` | `…$$GetDamage` | `RandomAmount` | **4** | **TRONCATURE** |
| `IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$EvaluateNonComparable` | `…$$GetDamage` | `RandomAmount` | **4** | **TRONCATURE** |
| `IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityForMainTarget` | `…$$GetAverageDamage` | `Half(Sum(…))` | **1** | **HALF-TO-EVEN** |
| `IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityForSecondaryTarget` | `…$$GetAverageDamage` | `Half(Sum(…))` | 1 | HALF-TO-EVEN |
| `IdunBattle.AI.Playbook.Loki.LightImUpPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` | `…$$GetAverageDamage` | `Half(Sum(…))` | 1 | HALF-TO-EVEN |
| `IdunBattle.AI.Playbook.Loki.MassiveScythingTalonsPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` | `…$$GetAverageDamage` | `Half(Sum(…))` | 1 | HALF-TO-EVEN |

- slot **1** = `Calculate`. Sur `Half` c'est `IdunBattle.Entities.Formulas.DivideAmount$$Calculate` :
  `Fix64(a) / Fix64(b)` puis `IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., this@+0x20)`, et
  `this@+0x20` vaut `0` (3ᵉ argument du `Half` construit) = `Fix64.Round` **demi-vers-le-PAIR**.
- slot **4** = `IdunBattle.DSL.AAmountFormula$$CalculateAverage`. Sur `RandomAmount` (qui porte ses
  propres `IdunBattle.Entities.Formulas.RandomAmount$$CalculateMin`/`$$CalculateMax` = ses deux
  enfants) c'est `(max + min) / 2` en division **ENTIÈRE C** — aucun Fix64 sur cette branche.

Les deux formes ne divergent QUE lorsque `minDmg + maxDmg` vaut **3 mod 4**, d'exactement `1`.
Ex. `2761 + 2762` : slot 4 rend `2761`, slot 1 rend `2762`.

⚠ Les corps `MassiveScythingTalonsAbility$$GetDamage` / `$$GetAverageDamage` sont **DÉDUPLIQUÉS**
(un `{ return base.MinMaxDamage{,Average}(this, state); }` partagé). Leur NOM ne dit rien de
l'ability réellement évaluée : `HeavyRailRiflePlaybook` va chercher `1260 HeavyRailRifle_Attack`
par `Playbook<T>$$GetAbility<T>(this, 0x4ec, …)`, pas MassiveScythingTalons.

### Le prédicat `<vtable+0x1c8>` n'est PAS modélisé — et c'est sans effet

`AAmountFormula$$CalculateAverage` court-circuite : `if (<vtable+0x1c8>(this) != 0) return Calculate()`.
Le corps de ce prédicat est trivial et dédupliqué (aucun symbole propre). On ne le porte pas, parce
qu'il est **inobservable ici** : `IdunBattle.DSL.ASimpleAmountFormula$$CalculateMin`/`$$CalculateMax`
retombent tous DEUX sur `<vtable+0x1d8>` = `Calculate`, donc pour tout nœud SIMPLE la branche
« plage » rend `(v + v) / 2 = v` — **identique** à la branche court-circuit, quelle que soit la
polarité. Et pour `RandomAmount` la branche « plage » est établie LIVE par #339
(`probe_32d_fury.py` : la feuille Fury tombe sur la moyenne EXACTE des deux cibles ; un
`Calculate()` de `RandomAmount` est un TIRAGE et ne le pourrait pas).

**RÉSIDU** : les 8 autres nœuds à plage (`SumAmount`, `MultiplyAmount`, `IfAmount`, `PercentageOf`,
`CacheAmount`, `ConditionalAmount`, `MultiplyPercentageRecursively`,
`FirstHitInCurrentAttackDamageRange`) ne sont pas couverts par ce raisonnement — aucun n'apparaît
dans les deux chaînes ci-dessus, ils sont hors périmètre.

## 2bis. Ce que le brief héritait, et qui est FAUX

- « 2 playbooks appellent `MinMaxDamage`, 4 appellent `MinMaxDamageAverage` » : les **chiffres** sont
  bons mais l'**attribution** ne l'est pas — 4 SITES pour la voie Average, soit **2 playbooks**
  (`LightImUp` ×3, `MassiveScythingTalons` ×1) ; et `LightImUp` n'est PAS un appelant de
  `MinMaxDamage` côté playbook.
- `BaseTriggeredAbility$$MinMaxDamage` a **63 appelants nommés** au total, `$$MinMaxDamageAverage`
  **1 seul** (`MassiveScythingTalonsAbility$$GetAverageDamage`). L'écrasante majorité des 63 sont des
  `<X>Ability$$CreateBehaviour` — c'est l'EXÉCUTION (un vrai tirage `RandomAmount`), pas la décision.
- « `MinMaxDamage` = TRONCATURE » n'est vrai qu'**au slot 4** ; le même nœud au slot 1 est un tirage.

## 3. Verdict par playbook — la forme du port

| Playbook | forme native | état du port |
|---|---|---|
| `FuryOfTheAncientsPlaybook` (1247) | TRONCATURE | **PORTÉ, CORRECT** — `engine/playbook/fury_of_the_ancients.py` |
| `HeavyRailRiflePlaybook` (1160 → ability 1260) | TRONCATURE | **NON PORTÉ** (playbook absent ; documenté `_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY`) |
| `LightImUpPlaybook` (1103) | HALF-TO-EVEN | **NON PORTÉ** |
| `MassiveScythingTalonsPlaybook` (1054) | HALF-TO-EVEN | **NON PORTÉ** |

⇒ La forme HALF-TO-EVEN de la couche TRIGGERED n'existait **nulle part** dans le moteur : le seul
consommateur triggered porté (Fury) est du côté troncature. C'est le trou que #350-r3b ferme.

## 4. Ce qui est livré

- `engine/dsl/base.py` — les slots manquants d'`IAmountFormula` sur `AAmountFormula` :
  `calculate_min`/`calculate_max` (mirror `ASimpleAmountFormula$$…` = `Calculate`) et la MÉTHODE
  `calculate_average(ctx)` (slot 4, mirror `AAmountFormula$$CalculateAverage`), qui délègue à la
  fonction libre `calculate_average(min, max)` déjà présente (#339).
- `engine/entities/formulas.py` — `RandomAmount.calculate_min`/`calculate_max` (ses deux enfants),
  mirror `RandomAmount$$CalculateMin`/`$$CalculateMax`.
- `engine/entities/abilities/triggered_ability.py` (NEUF) — `BaseTriggeredAbility` :
  `min_max_damage()` / `min_max_damage_average()` rendent les DEUX NŒUDS ; le registre
  `TRIGGERED_PREDICTION_AVERAGE_FORM` (playbook → slot) est LU par
  `triggered_prediction_damage(ability_name, level, mult, playbook)`, foyer unique des deux formes.
- `engine/playbook/fury_of_the_ancients.py` recâblé sur ce foyer (plus d'appel direct à la
  primitive) — la couche est donc EXERCÉE, pas spéculative.

## 5. Confrontation — quel oracle répond

Les six call-sites sont des `CalculateAttackUtility*` / `EvaluateNonComparable` : leur sortie est une
**UTILITÉ**, pas une prédiction. `aiPlaybookPredict` ne répond donc pas.

- **RÉPOND** : `FuryOfTheAncientsPlaybook` — déjà réconcilié EXACT contre la feuille L3 native
  (`probe_32d_fury.py`, #32/#339, delta ~1e-8). C'est la face TRONCATURE.
- **NE RÉPOND PAS** : la face HALF-TO-EVEN. `LightImUp` (1103) et `MassiveScythingTalons` (1054) sont
  des triggered de BOSS ; leur utilité ne sort ni de `aiPlaybookPredict` ni de `decisionView`. Le
  point d'ancrage natif à hooker serait
  `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent`
  (retour Fix64 par event) — capteur ABSENT, et un agent ne réinjecte pas.
  ⇒ **CONFRONTATION MANQUANTE, NOMMÉE.** La face half-to-even est validée OFFLINE sur le régime
  discriminant (`minDmg + maxDmg ≡ 3 mod 4`), pas live.
