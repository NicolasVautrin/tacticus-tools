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

### 7.3 Second garde-fou : un oracle ouvert ne remplace pas un port

`1132 KillMaimBurn` (`worldKharn`, **dans le pool**) est dans `_PREDICTION_MINMAX_AVERAGE` et son
playbook natif est NonComparable : l'oracle répond pour elle. Tant qu'**aucun playbook NC n'était
porté**, le côté offline ne pouvait proposer que le chemin GÉNÉRIQUE
(`generate_multi_hit_attack_prediction`). `probe_344` refuse donc (rc 2) une ability NC **sans
playbook porté** : sinon il rougirait comme un écart d'**arrondi** ce qui est un **port manquant**.

L'écart alors inscrit — natif `(8536, 8536, 4)` contre `(86, 129, 1)` — a été tranché par #362, et
**ce n'était pas une divergence de formule** : voir §8. Le garde-fou, lui, reste ; son sujet est
désormais dérivé (registres × table de symboles × registre porté), pas épinglé sur un id.

**Le capteur est DÉPLOYÉ** (session Frida 2) et **inchangé par ce travail** — aucune réinjection
n'est requise pour rejouer ce qui précède.

## 8. `1132 KillMaimBurn` — ce que l'oracle capture n'est pas ce qu'on croyait (#362)

`ncPlaybookPredict` est ancré sur `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor`. Il capture
donc **tout ce que l'évaluation construit**, y compris ce qu'un GATE construit sans jamais le
scorer. Lu VERBATIM dans `IdunBattle.AI.Playbook.Loki.KillMaimBurnPlaybook$$EvaluateNonComparable` :

```
bucket = new Bucket(0, Nullable(MIN_UTILITY))                      # .cctor = Fix64(1)
profile = ability.GetDamageProfile()                               # = damageProfile (NON suffixe)
foreach entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPos.MainTile):
    if BasePlaybook$$WillNormalAttackKill(entities): continue      # <-- construit un ProbableDamageEvent
    damage = slot 4 CalculateAverage( ability.GetDamage(state, isPrediction: TRUE), entities )
    hits   = slot 4 CalculateAverage( ability.GetHitsFormula(), entities )
    util   = Playbook<T>$$CalculateUtilityFromDamageEvent(caster, target, casterPos,
                                                          damage, profile, hits)
    bucket.AddAction(BasePlaybook$$GenerateAction(casterPos, target, util))
```

`BasePlaybook$$WillNormalAttackKill(entities)` relaie vers la surcharge
`(caster = entities+0x08, target = entities+0x10, casterTile = entities+0x40)` — offsets lus dans
`GetEligibleTargetsSelectable` — qui invoque `IBattleQuery` slot `0x21` (`PredictAttack`, attaque
**NORMALE**), **construit un `ProbableDamageEvent`** et n'en retient que
`DamagePredictionResult$$get_WillBeKill`.

**D'où la relecture de l'écart de `#356-r1`.** `(8536, 8536, 4)` n'était pas « la prédiction de 1132
bornée aux PV MAX » : c'était l'attaque NORMALE de `worldKharn`, avec le MÊME `targetId` que
l'event d'ability. Deux discriminants observables le disent : `4` = `worldKharn.weapons[0].hits`
(l'ability a `nrOfHits = 1`), et les bornes sont ÉGALES parce que la normale sur-tue — le cap
per-coup à la santé restante (`DamagePrediction$$PredictAttackRaw` : `health = min(health, rem_HP)`,
publié en `AccurateHealthDamage@0x40`) écrase min et max sur les PV. La « borne aux PV MAX » était
donc **déjà portée**, et sur le mauvais objet.

MESURE (`probe_362_kill_maim_burn_nc.py`, `worldKharn` rank 17, anneau `(3,4)` de `MC1_67`,
`--armor-target 0`, niveau 3 ; le SEUL curseur entre les deux régimes est les PV de la cible) :

| régime | capture BRUTE (tous les events) | bucket | port normale (`willBeKill`) | port ability |
|---|---|---|---|---|
| PV du seed (8536) | `[tgt79 (9537,9537,4), tgt77 (8536,8536,4)]` | **vide** | `(8536,8536,4)` (**True**) | `(86,129,1)` |
| PV forcés (400000) | `[tgt79 (9537,9537,4), tgt77 (10052,15072,4), tgt77 (86,129,1)]` | vide | `(10052,15072,4)` (False) | `(86,129,1)` |

Aux PV du seed le gate mord sur **toutes** les cibles ⇒ `continue` ⇒ **aucune** prédiction d'ability
n'est construite, bucket vide. Le port rend, dans les deux régimes, **exactement** la même séquence.

### 8.1 Le kit a trois profils, le playbook n'en lit qu'un

`GetDamageProfile` = `AbilityConfiguration$$GetDamageProfile` (clé `damageProfile`), `GetHitsFormula`
= `DSLFormulas$$ConfigConst(0x2f)` (la clé de `AActiveAbility$$GetHits`, `nrOfHits`), et
`AActiveAbility$$MinMaxDamage` les variables `0xc`/`0xd` (`minDmg`/`maxDmg`). Les suffixes `_2`/`_3`
(`nrOfHits_2:6 Eviscerate`, `nrOfHits_3:1 Plasma`) appartiennent à la face COMBAT
(`KillMaimBurnAbility$$ExecuteBehaviour`), pas à la face DÉCISION. **Le chemin générique est donc
EXACTEMENT le sien** — ce qui manquait n'était pas une formule, mais le gate.

`isPrediction = TRUE` fait rendre à `MinMaxDamage` un `Half(Sum(Direct(minDmg), Direct(maxDmg)))`
(la branche `FALSE` rendrait un `RandomAmount`). Ce nœud est DÉTERMINISTE, donc le slot 4
`CalculateAverage` retombe sur `Calculate` (prédicat de vtable `+0x1c8`) →
`DivideAmount$$Calculate` → `RoundFix64Result(., 0)` = **demi-vers-le-pair** : c'est la famille (a),
et `1132` figure bien dans `_PREDICTION_MINMAX_AVERAGE`.

### 8.2 Ce que `probe_344` compare désormais sur la face NC

Deux durcissements, tous deux imposés par le fait ci-dessus :

* la comparaison porte sur la **SÉQUENCE construite** — côté port,
  `playbook.damage_predictions(position, cible, ctx)` rend `[(tag, DamagePredictionResult)]` dans
  l'ordre natif, avec les tags `WillNormalAttackKill` / `ability` ; côté natif, tous les events
  captés de la cible principale. Comparer la seule prédiction d'ability à une capture qui commence
  par l'event du gate était la fausse divergence ;
* **trois issues, jamais deux** : si le playbook n'a construit **aucune** prédiction d'ability (son
  gate a mordu), le probe rend `NON CONFRONTÉ` (rc **2**) et nomme le levier —
  `--victim-hp <n>` force `Health`/`RemainingHealth` de la cible, ce qui déplace le seul verdict
  `get_WillBeKill` sans toucher ni la formule de dégât, ni l'armure, ni le crit.

`probe_344 --oracle auto --caster worldKharn --ability 1132 --lvl-a 3 --lvl-b 12 --armor-target 0
--victim-hp 400000` :

| bras | niveau | minDmg+maxDmg | natif | `to_even` | `trunc` | `half_up` | `ceil` |
|---|---|---|---|---|---|---|---|
| A | 3 | 70+101 = 171 (**3 mod 4**) | **(86, 129, 1)** | **=** | (85,128,1) | **=** | **=** |
| B | 12 | 171+246 = 417 (**1 mod 4**) | **(208, 313, 1)** | **=** | **=** | (209,314,1) | (209,314,1) |

(l'event du gate `(10052, 15072, 4)` précède les deux, identique des deux côtés). Intersection sur
les deux bras = **`to_even`**, exactement ce que le registre prévoit ; le code **LIVRÉ** égale le
natif sur les deux bras. Sans `--victim-hp`, le même montage rend `rc 2` avec le motif « le gate
prédictif du playbook a sauté la cible ».

### 8.3 Le gate change le RÉSULTAT OBSERVABLE, pas un scalaire

Généralisation craftée : deux ennemis sur l'anneau, un seul curseur (les PV) — `necroWarden` à
30 000 PV **survit** à la normale de Kharn, `ultraTitus` (9 537) non ; ability au niveau 50.

| | `necroWarden` (survivant) | `ultraTitus` (mourant) | argmax |
|---|---|---|---|
| natif (`bucketUtil`) | **14.07906140666455** | — (sauté) | survivant |
| port AVEC gate | 14.079061395906939 | `None` | survivant |
| port SANS gate (contrefactuel) | 14.079061395906939 | 44.2813712129154 | **mourant** |

Le natif met au bucket l'utilité du **survivant** ; sans le gate, le port aurait émis le **mourant**
(le composite prime le kill sûr). Le port du gate est donc confronté par un changement de **cible
émise**, pas par un ajustement de valeur.

### 8.4 A/B d'agreement sur une marche d'IA native — le port ferme un MISS

`engine_validate.py --steps 14`, seed 777 / `MC1_67`, équipes
`worldKharn,astraBullgryn,ultraTitus` contre `necroWarden,orksNob,tauCrisis`. Le SEUL curseur entre
les deux colonnes est la présence de `1132` dans `engine.playbook.noncomparable.PLAYBOOKS` (le même
état, deux runners bâtis sur la même seed) :

| pas 7 (`u83` = Kharn) | avec le port | sans le port (fallback Comparable) |
|---|---|---|
| natif | `ability(ab=1132, tgt=79)` en `(3,3)` | idem |
| moteur | `ability(ab=1132, **tgt=79**)` en `(3,3)` — **MATCH**, position EXACTE | `ability(ab=1132, **tgt=122**)` en `(2,3)` — **MISS**, position à 1 hex |
| agreement de la marche | pos exact **11/13**, ability **9/10** | pos exact 10/13, ability 8/10 |

Le fallback Comparable trouvait bien l'ability mais **pas la cible** : c'est ce que la face NC — son
sélecteur par position, son gate `WillNormalAttackKill` et son utilité de dégât — corrige. Le seul
MISS restant (pas 6, `u87` / `ab=1154`) est étranger à ce cas et inchangé entre les deux colonnes.

### 8.5 Constantes et gates du playbook, mesurés

* `MIN_UTILITY` = `KillMaimBurnPlaybook$$.cctor` = `Fix64.op_Implicit(1)` → **1**.
* `PRIORITY` = **0** : `1132` est hors `NATIVE_PRIORITY` (sweep exhaustif #170, re-joué : 36
  playbooks portés, accord exact).
* `ShouldEvaluate` (slot 4 d'`IPlaybook`) = l'implémentation de BASE. **Mesuré**, pas supposé : RPC
  `pbGate` slot 4 sur `worldKharn` au **premier** tour rend `1`, quand `1202 VigilanceEternal` — qui
  porte le corps foldé `AlphaWarriorPlaybook$$ShouldEvaluate` (`GetStat(unit, 0xc) > 1`) — rend `0`
  au même instant. `1132` n'a donc aucun gate de tour.
* ⚠ `bucketAction.targetLow` de `ncPlaybookPredict` est le dword BAS d'un **pointeur** d'entité, pas
  un `unitId` (mesuré : `705051616`, `1008571280` d'un run à l'autre) — il n'identifie rien
  d'exploitable offline. C'est `bucketUtil` qui sert de cadran.

**Aucune réinjection n'a été requise** : le capteur `ncPlaybookPredict` est celui de #356, inchangé.

## 9. `#350-r3a-r3` — le gate per-position : l'écart n'était pas le prédicat, c'était la TRONCATURE

**Énoncé hérité, RÉFUTÉ** : « le port gate sur une UNION de positions (`P in ranked(tgt)` du plan)
là où le natif interroge `GetValidTargets(caster, position, ability)` par position ». Les DEUX côtés
sont per-position, et ils portent le MÊME prédicat :
`BasePlaybook$$GetEligibleTargetsSelectable` appelle `AttackQuery$$GetValidTargets` une fois par
position ; `computeAttackPlans` (`frida/hooks/features/ai-step/projection.ts`) fait un
shrink-and-recall sur `AttackQuery$$GetBestTileToAttackFrom`, dont le corps garde une tuile ssi
`AttackQuery$$GetInvalidTargetReason` n'est pas invalide. **Écart de prédicat mesuré : 0 position sur
33, à tous les rangs** (`castFromTiles` == éligibilité native, y compris le flag `0x8000000`
`TargetIsInRange` de `VigilanceEternalAbility$$GetDynamicInvalidTargetReason`).

**Le vrai écart** : `computeAttackPlans` PLAFONNE le résultat — `for (let r = 0; r < maxRank; r++)`.
Ce plafond n'existe nulle part côté natif. Mesure sur **un seul état** (`probe_350r3a_r3_position_gate.py`,
fixture `carte` : `custoKyrus` en `(3,4)`, `necroWarden` à 1 hex, `ultraTitus` à 3 hex, board `MC1_67`) :

| `maxRank` | positions perdues par le port | argmax |
|---|---|---|
| 32 | 0 / 33 | natif `(1,3)` = port `(1,3)` |
| **8** (défaut `rl_duel._decision`) | **19 / 33** | identique — **par coïncidence de géométrie** |
| **6** (défaut du RPC `decisionView`) | **21 / 33** | **natif `(1,3)` vs port `(0,3)`** |

Le régime fautif est donc celui de **production**, et l'écart est à sens unique (le port est plus
PAUVRE, jamais plus permissif : `diff_port_only` = `[]` partout).

**Pourquoi il avait résisté deux fois** : le relevé de #356 et le `0/33` du WIP mesuraient un écart de
COMPTE d'éligibilité à une position, jamais un écart de DÉCISION. Un montage où les deux modèles
rendent le même argmax ne conclut rien — la position gagnante y voyait les deux cibles.

**Fix** : `_PlanTargetPlaybook.eligible_positions` (foyer neuf, `engine/playbook/noncomparable/_base.py`,
7 sous-classes) lit `castFromTiles` — même prédicat, SANS troncature — au lieu de `ranked(tgt)`.
Repli NOMMÉ sur `ranked` si la seam est absente, en erreur, ou rend un ensemble vide malgré
`rankCount >= 1`. L'énumération des CIBLES reste celle du plan : aucune n'est perdue par la
troncature (`rankCount >= 1` dès qu'une position est valide, le harnais bornant `maxRank >= 1`).

**Ce que le fix ne fait PAS** : il ne détronque pas `attackPlans`. Tout autre consommateur de
`ranked` reste exposé au plafond — c'est un défaut du **harnais**, et le corriger demanderait une
réinjection.

Garde : `tests/engine/test_350r3a_r3_position_gate_live.py` — **9 passed** (était 2 failed / 4 passed
avant le fix ; 4 failed sous mutation adversariale du gate). Elle exige l'égalité des ENSEMBLES
d'éligibilité aux 33 positions et des ARGMAX, aux trois rangs `32 / 8 / 6`.

### 9.1 Généralisation — et la limite de la méthode de mesure

* **Autre géométrie, même ability** (`--rings 2,4`) : le plan perd jusqu'à **18 positions sur 33**
  (`E2plan` = 0 → 11 → 14 → 16 → 18 quand `maxRank` descend de 32 à 2), et pourtant la carte du gate
  reste **identique à 0 position près** aux cinq rangs, argmax inclus. Le gate est devenu insensible
  au plafond — ce qui était le but.
* **Autre sous-classe** (`1153 HammerOfWrath`, `bloodIntercessor`, fixture `hammer`) : argmax
  identique aux cinq rangs, aucune régression. Le régime de troncature n'y est PAS atteint
  (`ranked = 1` tuile) — c'est donc une non-régression, pas une seconde démonstration.
* **Les quatre autres `_PlanTargetPlaybook`** (`BloodyFury`, `Stormcaller`, `VexillaMagnifica`,
  `BlackRage`) ont une utilité position-INDÉPENDANTE : leur argmax est l'ORIGINE par keep-first, que
  le gate soit tronqué ou non. Le fix ne peut pas les changer. **NON CONFRONTÉ**, et c'est un
  raisonnement structurel, pas une mesure.

⚠ **La CAPTURE n'est pas l'ensemble des cibles ÉLIGIBLES** — même leçon que #362. L'oracle est ancré
sur `ProbableDamageEvent$$.ctor` : il voit tout ce que l'évaluation construit. Sur `1153`, qui score
`Σ CalculateUtilityFromDamageEvent` sur la cible ET ses adjacents, il capture les éclaboussures :
mesuré, `e1_nat_only = 1` à l'origine (`abilityReason(77)` = `TargetIsNotAdjacent`, et 77 est
pourtant capturé). Ce n'est **pas** un écart de gate. Le probe sépare donc les deux sens —
`e1_cft_only` (le port serait PERMISSIF : le seul qui accuse le gate) et `e1_nat_only` (splash) — et
l'égalité ensembliste n'est concluante que sur une ability **MONO-CIBLE**. `1202` l'est
(`e1_cft_only = e1_nat_only = 0` aux 33 positions), d'où la validité de la mesure ci-dessus.
