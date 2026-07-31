# case-350-r3 (a) — l'oracle de la face NonComparable

Résidu `#350-r3` **mur (a)** : « les playbooks **NonComparable** rendent 0 event à `aiPlaybookPredict`
(mesuré sur `1132 KillMaimBurn` ; concerne aussi 1111, 1173, 1202) — il manque un oracle pour la face
NonComparable. »

Question binaire posée : **existe-t-il un point d'observation natif qui rende la prédiction de dégât
d'un playbook NonComparable ?** Réponse : **OUI** — mais pas au même endroit, et il faut un capteur.
Le détail ci-dessous sépare ce qui est *structurellement impossible* de ce qui est *observable*.

## 1. Pourquoi `aiPlaybookPredict` ne peut RIEN rendre — et pourquoi c'est la réponse JUSTE

La hiérarchie est lue dans la table VERSIONNÉE `data/symbols/rnca9r7q6c/frida/classes.tsv`
(colonne « parent »), pas déduite :

```
BasePlaybook              (System.Object)
  └── Playbook`1
        ├── ComparablePlaybook`1        <- MakeDamage/Heal/Effect/RepairPredictions y sont DÉCLARÉES
        └── NonComparablePlaybook`1     <- EvaluateInternal
```

`ComparablePlaybook`1` et `NonComparablePlaybook`1` sont **frères**. Les quatre `Make*Predictions`
n'existent que sur la branche Comparable :
`ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions` (corps de base :
enumerable vide), `$$MakeHealPredictions`, `$$MakeEffectPredictions`, `$$MakeRepairPredictions`.
`NonComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E` n'en déclare **aucune** — ses seuls
membres propres sont `$$EvaluateInternal` (un dispatch nu vers le slot de vtable `+0x318`, c.-à-d.
`EvaluateNonComparable`), `$$GenerateBucketWithActionForEveryEligibleTarget` et
`$$GenerateBucketWithMultipleStrategies`.

⇒ Sur un playbook NonComparable, le `findMethodByParamCount(pbCls, "MakeDamagePredictions", 4|3)` de
`playbook-predict.ts::makeDamagePredictions` **ne résout rien** : le RPC rend `makeArity: 0`,
`listNull: true`, `count: -1`. Ce n'est pas un silence à interpréter — c'est la **valeur de retour**
qui dit « ce chemin n'existe pas ici ». **Le « 0 event » de #350 est exact et le restera.**

Portée : `classes.tsv` compte **134** classes de parent direct `NonComparablePlaybook`1` contre **96**
de parent `ComparablePlaybook`1`. Le mur ne concernait donc pas 4 abilities mais la moitié du
catalogue de playbooks.

## 2. Ce que le natif fait à la place — et où la prédiction de dégât EXISTE

`<X>Playbook$$EvaluateNonComparable(this, caster, casterPosition, abilityState)` boucle sur
`BasePlaybook$$GetEligibleTargetsSelectable` (une `List<AbilityEntities>`, une entrée par cible
éligible) et, par cible :

1. évalue le nœud de dégât de l'ability (`this+0x68`) — corps et **slot d'`IAmountFormula`** relus
   site par site (le slot n'est PAS constant, cf. §3) ;
2. lit `AActiveAbility$$GetDamageProfile` et `AActiveAbility$$GetHits` ;
3. appelle `Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent` avec
   le triplet `(damage, profile, hits)` ;
4. `BasePlaybook$$GenerateAction(position, target, utility)` puis `Bucket$$AddAction`.

**Le point clé est l'étape 3.** Les deux surcharges « triplet » de
`Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent` — celle à
`(entities, damage, profile, hits)` et celle à `(caster, target, position, damage, profile, hits)` —
font TOUTES DEUX, avant de scorer :

* `IBattleQuery` slot `0x28` (`GetAttackPrediction`) avec `(caster, target, casterPosition,
  AbilityOrEffect, damage, Nullable(profile), hits)` → un `DamagePredictionResult` **complet** ;
* `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor(target, damagePrediction, probability, weight)` ;
* puis délèguent à la surcharge finale `(ProbableDamageEvent, caster, casterPosition, …)`, qui
  construit l'`UtilityAttackCase$$ForDamagePrediction`.

⇒ **Un playbook NonComparable CONSTRUIT le même `ProbableDamageEvent` qu'un Comparable.** Il ne le
met simplement dans aucune liste : il le consomme sur place. La différence entre les deux faces n'est
pas « prédiction vs heuristique », c'est **« prédiction RENDUE vs prédiction CONSOMMÉE »**.

C'est ce qui rend un oracle possible, et avec le décodeur DÉJÀ écrit : la struct est celle que
`playbook-predict.ts::readDamageEvent` lit (stride et offsets résolus dans `game/damage-prediction.ts`,
#276), puisque c'est littéralement le même ctor.

## 3. Le slot d'évaluation n'est pas constant — relu sur les quatre abilities du résidu

`FUN_180025fb0(slot, IAmountFormula, node, entities, out)` est l'invocation d'interface par slot.
Lu VERBATIM au call-site de chaque `EvaluateNonComparable` :

| id | corps de la formule | slot |
|---|---|---|
| 1132 KillMaimBurn | `StaffOfStarsAbility$$GetDamage(state, isPrediction = 1)` | **4** (`CalculateAverage`) |
| 1111 LivingBatteringRam | `StaffOfStarsAbility$$GetDamage(state, isPrediction = 1)` | **1** (`Calculate`) |
| 1173 ArcScourge | `StranglethornCannonAbility$$GetDamageAmountMain(state)` | **1** (`Calculate`) |
| 1202 VigilanceEternal | `VigilanceEternalAbility$$GetDamage(state)` (pas d'`isPrediction`) | **4** (`CalculateAverage`) |

`IdunBattle.DSL.AAmountFormula$$CalculateAverage` n'est PAS inconditionnellement `(min + max) / 2` :
il teste d'abord le prédicat de vtable `+0x1c8` et, s'il est vrai, retombe sur `Calculate` (`+0x1d8`) ;
sinon seulement il fait `(vtable+0x1f8 + vtable+0x1e8) / 2` en division entière C (troncature).
Slot 1 et slot 4 coïncident donc pour un nœud déterministe et divergent pour un `RandomAmount` —
ce qui est cohérent avec les inscriptions de #350 (1132/1111 en (a2), 1202 en (b)), **mais la
coïncidence est une propriété du nœud, pas une identité des slots**. Un port qui recalculerait la
moyenne sans lire le slot du call-site serait juste par accident.

1173 ajoute au triplet un terme propre : pour chaque unité poussée, `Playbook<T>$$GetUtilityValue`
d'une constante différente selon `UnitExtensions$$IsEnemy`. Il n'affecte pas la prédiction de dégât.

## 4. Ce qui existe DÉJÀ, et ce qui manque

| oracle | rend | état |
|---|---|---|
| `aiPlaybookPredict` | `ProbableDamageEvent[]` d'un playbook **Comparable** | livré ; **inapplicable** à la face NC (§1) |
| `ncEvaluate` (#46) | l'**utilité** `best` du Bucket d'un playbook NC, par position | **livré et applicable** — jamais branché au rail #344 |
| `ncPlaybookPredict` | les `ProbableDamageEvent` **construits** pendant l'évaluation NC | **capteur neuf** (§5) |

`ncEvaluate` répond déjà à « la face NC vit-elle, et que vaut-elle ? ». Il ne répond pas à « quelle
prédiction de dégât l'a produite » : entre les deux il y a `UtilityAttackCase$$ForDamagePrediction` et
tout le composite d'utilité, qu'il faudrait porter pour inverser. Pour l'objet de #350 — la FORME de la
moyenne, un écart d'une unité — c'est le mauvais étage : on mesurerait un scalaire agrégé au lieu de
l'entrée (doctrine « décomposer par étage, jamais fitter un scalaire »).

## 5. Le capteur livré — `ncPlaybookPredict`

Ancrage : **`IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor`**, corps UNIQUE, présent dans
`data/symbols/rnca9r7q6c/frida/methods.tsv` avec sa signature
`(target: IEntity, damagePrediction: DamagePredictionResult, probability: Nullable<Fix64>,
weight: Nullable<Fix64>)` — donc résoluble par `findClassAnywhere` + `findMethod`, **sans aucune RVA**.

Le ctor écrit dans `this` (= `args[0]`) : `Target` à `+0x00`, les **0xa0** octets du
`DamagePredictionResult` de `+0x08` à `+0xa4`, `Probability` à `+0xa8`, `Weight` à `+0xb0` — donc
exactement ce que `readDamageEvent` lit, et la capture se fait en `onLeave` (la struct vit sur la pile
de l'appelant et n'est remplie qu'au retour). Les deux `Nullable<Fix64>` sont **résolues par le ctor
lui-même** (`Fix64(1)` quand `hasValue` est faux), donc le champ capturé est la valeur effective.

Le RPC est **fenêtré**, pas armé en permanence : il attache le trampoline, invoque le wrapper
`Evaluate` du playbook (même résolution que `ncEvaluate` — appeler la leaf nue crashe, l'`AbilityState`
manque), détache immédiatement, puis décode le buffer avec `readDamageEvent`. Il n'existe donc à aucun
moment de hook permanent sur ce ctor, qui est chaud (tout `MakeDamagePredictions` comparable le traverse).

La réponse mirror celle d'`aiPlaybookPredict` (`events[]` avec `healthDmgMin/Max`, `appliedHits`, …),
de sorte que le gabarit `probe_344_ability_damage_average.py` puisse commuter d'oracle sans changer sa
logique de verdict.

## 6. Le montage doit atteindre le RÉGIME, et le PROUVER (#356)

`1202 VigilanceEternal` porte une **précondition géométrique**, lue dans
`IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetDynamicInvalidTargetReason` :

```
si  <ITileService> slot 0x62 (casterTiles, targetTiles)      -> return 0            (déjà adjacent)
sinon  DSLSelectors$$TilesUnitCanMoveToChargeTarget(caster, casterTiles, target,
                                    movementRange = GetNumberConstant(0x16))
       .Count >= 1                                            -> return 0
       sinon                                                  -> return 0x8000000   (TargetIsInRange)
```

Aux tuiles de **spawn** de `MC1_67`, le caster est à **10-11 hex** des cibles : aucune n'est
éligible, `GetEligibleTargetsSelectable` rend une liste vide, et le bucket vide est la **réponse
juste** du natif. Le `capture=0` hérité mesurait donc le **montage**, pas le port.

**Ce qui n'est PAS une preuve** : `ncEvaluate.hvt` (`IBattleQuery.HasValidTargets`, slot `0x3f`)
valait **`true` aux 13/13 positions** de ce montage à éligibilité vide — ce gate ne traverse pas
`GetDynamicInvalidTargetReason`. La preuve retenue est `abilityTargets` (`fromHere`/`targets` non
vides) confirmée par `abilityReason`, dont le `targetReason.hex` **EST** le flag du décompilé
(`0x8000000` = refus, `0x0` = éligible).

Le probe **pilote donc les positions** (`_approach` : les deux camps avancent l'un vers l'autre sur
un runner `--no-ai`, donc chaque déplacement est le nôtre) jusqu'à ce que la précondition soit vraie
**au début de mon tour**, caster non encore déplacé. Effet de bord voulu : au round *N* le caster a
`turnsStarted = N`, donc le gate natif `VigilanceEternalPlaybook$$ShouldEvaluate`
(`GetStat(unit, 0xc) > 1`) est franchi lui aussi — le montage est dans le régime où le générateur
natif évaluerait **réellement** ce playbook.

⚠ `BasePlaybook$$Evaluate` **n'appelle PAS** `ShouldEvaluate` : il pose l'`AbilityState`, coupe le
random et saute au slot `+0x238` (`EvaluateInternal`). Les deux oracles NC contournent donc ce gate,
et c'est correct — ils mesurent la face « évaluer », pas la face « décider d'évaluer ».

**Trois issues, jamais deux.** Le probe distingue désormais : régime non atteint → `NON CONFRONTÉ`
(rc **2**) ; régime atteint + events → OK ; régime atteint + capture nulle → ÉCHEC, et c'est
seulement là que le port/harnais est en cause. `--max-rounds 1` exerce délibérément la première
branche.

## 7. État de la mesure — CONFRONTÉ le 2026-07-31 (session Frida 2)

`probe_350r3_noncomparable_oracle.py`, joué en entier :

| étape | ce qu'elle tranche | état |
|---|---|---|
| 0 structure | frères, exclusivité des `Make*Predictions`, les 4 playbooks sont NC | **VERTE** (134 NC / 96 Comparable) |
| 1 valeur de retour | `aiPlaybookPredict` rend `makeArity 0` / `listNull` **et** la bonne `playbookClass` | **VERTE** sur les 4 (1132, 1111, 1173, 1202) |
| 3a verrou capteur | `deathBlightlord`/`1042` : capture == liste rendue | **VERTE** (`capture=1 rendue=1 identiques=True`) |
| 2 `ncEvaluate` | non-vacuité de la face NC, régime atteint | **VERTE** : 17 positions, **16 scorées** |
| 3b oracle NC | `ncPlaybookPredict` sur le montage piloté | **VERTE** : `capture=1` |

Régime atteint en **3 rounds** (caster `(1,0) -> (2,2)`, cibles `(6,8)/(6,7) -> (4,3)/(3,3)`),
`fromHere=1 targets=2`, `abilityReason` = `0x0`. Event capturé :
`tgt=79 (ultraTitus) healthDmg=[1938, 2904] appliedHits=3 probability=1`, `bucketUtil = 25.3800189`.

**L'oracle NonComparable est OUVERT.** Les **134** classes de playbook NC redeviennent observables —
sous réserve, pour chacune, d'atteindre son propre régime d'éligibilité.

### 7.1 Ce que le port en dit — `probe_344` branché sur cet oracle

`probe_344 --oracle auto` commute sur `ncPlaybookPredict` dès que l'ability a un playbook NC porté,
et compare à `engine.playbook.prediction.generate_multi_hit_attack_prediction` (le chemin exact du
playbook NC porté). Le point de branchement patché reste `AActiveAbility.get_damage`, donc le verdict
d'arrondi se lit à l'identique sur les deux faces. L'anneau de `_place_ring` satisfait la précondition
**par construction** (toutes les cibles à distance 1) et le probe le **vérifie** (`_nc_regime`).

`custoKyrus` / `1202`, anneau centré en `(3,4)`, `--armor-target 0` :

| bras | niveau | minDmg+maxDmg | natif | `to_even` | `trunc` | `half_up` | `ceil` |
|---|---|---|---|---|---|---|---|
| A | 4 | 35+48 = 83 (**3 mod 4**) | **(99, 147, 3)** | (102,150,3) | **=** | (102,150,3) | (102,150,3) |
| B | 3 | 31+42 = 73 (**1 mod 4**) | **(87, 129, 3)** | **=** | **=** | (90,132,3) | (90,132,3) |

Intersection sur les deux bras = **`trunc`**, exactement ce que le registre
`_PREDICTION_MINMAX_RANDOM_READ` prévoit pour `1202` (famille (b) : `RandomAmount` lu au slot **4**
`CalculateAverage`, division entière). Le code **LIVRÉ** égale le natif sur les deux bras. Une forme
d'arrondi de plus passe donc de « lue au décompilé » à « confrontée live ».

Sur le montage piloté (rank 17, niveau 50, mult 140), la comparaison per-position tient aussi :
port et natif rendent `(1938, 2904, 3)` sur 14 positions et `(2904, 4356, 3)` sur `(0,3)`/`(1,3)`,
et l'argmax du port (`target=77`, `to=(1,3)`, `u=42.5158`) égale le `bucketUtil` natif de cette
position (`42.5158117`). **Écart relevé, non tranché** : par position, le natif ne score qu'**une**
cible là où le port en score deux (gate `P in ranked(tgt)` du plan vs `GetValidTargets` par
position) — sans effet sur l'argmax de ce montage, donc hors périmètre de #356.

### 7.2 Une capture nulle a une TROISIÈME lecture

`ncPlaybookPredict` capture ce que le natif **construit**. Un playbook NC dont l'utilité n'est pas
un dégât n'en construit aucun, et le zéro est alors juste. Mesuré :
`IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$EvaluateNonComparable` score
`Fix64(DarkTalonStrikeAbility$$GetAttackTargets(GetTilesInBestLine()).Count)` — un **compte de
cibles**, aucun `ProbableDamageEvent`.

Ce trou n'était pas atteignable tant que `probe_344` ne parlait qu'aux Comparables ; `--oracle auto`
l'ouvre. `probe_344` **refuse donc désormais (rc 2)** toute ability absente des **deux** registres
d'arrondi : sur celles-là son `expected` (`to_even` si dans `_PREDICTION_MINMAX_AVERAGE`, `trunc`
sinon) serait une **fabrication**. Des 13 abilities à `minDmg`/`maxDmg` dont le playbook NC est porté,
**seule `1202`** est dans un registre.

**Le capteur est DÉPLOYÉ** (session Frida 2) et **inchangé par ce travail** — aucune réinjection
n'est requise pour rejouer ce qui précède.
