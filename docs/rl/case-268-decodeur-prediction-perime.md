# case-268 — Le régime « létal sous le seuil » est atteignable ; c'est l'INSTRUMENT qui était mort

Question posée, binaire : **le régime « létal-sous-le-seuil » est-il atteignable avec un montage
correctement piloté ?** Réponse mesurée : **OUI** — PV 2256, dégât 2774, `2256 <= 2774 < 4512`,
crescendo `0 -> 1`, port et live d'accord. Le montage n'était pas en cause, le **roster non plus** :
le canal qui *mesurait* le dégât rendait `[1,100]` pour tout couple depuis la migration de build.

Quatrième cause de la famille `case-254` (« une donnée capturée sur l'ancien build confrontée à du
code neuf »), et la plus silencieuse des quatre : elle ne fait ni crasher ni rougir — elle fait
**skipper**.

## 1. Le symptôme, et pourquoi son message accusait le mauvais coupable

`pytest tests/engine/runner -k "overkill_gate or prevent_overkill_decision"` sur `dd129216` :
**4 failed, 8 skipped**. Les trois messages de skip nommaient tous le montage :

```
conftest.py:73  / :94   plage [1,100] trop large : dmax >= 2 x dmin, pas de PV rendant TOUTE la
                        plage letale-sous-le-seuil
conftest.py:189         regime letal-sous-le-seuil inatteignable : bornes [0,0]
```

Lus tels quels, ils envoient re-choisir un roster « au profil de dégât resserré ». Or `[1,100]`
n'est pas une plage large : **c'est du garbage**. Mesure sur le montage `control` (Shiron ->
genesPrimus, 400 PV, au contact) :

```
[178] control : PV=400 degat=[1,100]
[178]   REJEU port (flag reel) -> overkill=True (total=2375 ...)
[178]   LIVE crescendo 0 -> 1  -> overkill=True
```

Le coup vaut **2375**, le live le confirme, le port aussi — et la prédiction annonce `[1,100]`.
Les **quatre rouges et les huit skips ont donc UNE seule cause**, contrairement à l'hypothèse de
départ qui en supposait deux (« plage trop large » vs « plage vide »).

## 2. La cause : le décodeur du struct de prédiction lit des offsets périmés

`aiPredict` et `aiPlaybookPredict` ne calculent rien : ils **relisent en mémoire** le struct
`IdunBattle.Core.Services.DamagePredictionResult` rendu par le natif, à des offsets **figés dans le
code des hooks** (`// dump kqkbjqfb6c`). Dump live sur `rnca9r7q6c`, victime à 400 PV :

```
hpBefore      400            <- juste
armorBefore   0              <- plausible
shieldBefore  -842041904     <- garbage
healthDmgMin  0 / Max 0      <- garbage (le coup vaut 2375)
totalDmgMin   1 / Max 100    <- garbage
mightCrit     25             <- un bool qui vaut 25
probability   0 / probMult 0 <- un event natif n'a jamais une probabilité nulle
```

Seuls les deux premiers champs (offsets 0x00 et 0x04) survivent. Tout ce qui suit a bougé.

**Contre-épreuve** : le même dump sur un build **sans aucun patch de stats** (`--hp-target`,
`--crit` et `--block-target` retirés), unités amenées au contact, donne exactement les mêmes
`totalDmg [1,100]` et `mightCrit 25`. Ce n'est donc ni le patch de stats, ni le roster, ni la
géométrie.

### 2bis. Les offsets, re-dérivés au décompilé du build courant

`data/symbols/rnca9r7q6c/frida/classes.tsv` :
`IdunBattle.Core.Services.DamagePredictionResult` = **176 octets** (`0xB0`).

> ⚠ **Ces 176 octets sont la taille BOXÉE, pas celle des champs** (corrigé en #276). La colonne
> `size` de `classes.tsv` est `il2cpp_class_instance_size`, qui inclut le header IL2CPP de `0x10`
> pour un `System.ValueType`. Les champs occupent donc **`0xA0`**, ce que trois fonctions
> confirment indépendamment : `unit_HUD_test$$CreateDamagePrediction` et
> `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` font un `memset(dst, 0, 0xa0)`,
> et `…HarlequinsPanoplyAbility$$SurvivesByDiscardingHits` recopie `+0x00 .. +0x9f`.
> Même correction pour tous les autres types de la table : `MinMaxDamage` = 32 boxé donc **16**
> de champs, `DamagePredictionScenario` = 52 donc **36**, `ProbableDamageEvent` = 200 donc
> **`0xB8`** (et non `0xD8`, la valeur que les hooks utilisaient comme stride).

Trois fonctions **indépendantes** se recoupent sur le même layout — aucune déduction, que de la
lecture :

| Fonction lue | Ce qu'elle prouve |
|---|---|
| `IdunBattle.Core.Services.DamagePredictionResult$$get_MightBeKill` | `*(int*)this <= *(int*)(this+0x20)` ⇒ `CurrentHealth@0x00`, borne **haute** de dégât santé `@0x20` |
| `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` | même comparaison avec `*(int*)(this+0x1c)` ⇒ borne **basse** `@0x1c` ; sort avant si `*(char*)(this+0x89)` |
| `IdunBattle.Core.Services.DamagePredictionResult$$get_HealthDamageWithBlock` | copie les 16 octets `this+0x14 .. this+0x23` ⇒ `HealthDamage` est un `MinMaxDamage` **@0x14**, dont `Min` est à `+8` et `Max` à `+0xc` |
| `IdunBattle.Core.Services.DamagePredictionResult$$get_ShieldDamage` | copie `this+0x24 .. this+0x33` ⇒ `ShieldDamage` **@0x24** |
| `IdunBattle.Core.Services.DamagePredictionResult$$MightBeOverkill` | passe à `IsOverkill` : `this+0x00`, `this+0x20`, `this+0x8a`, `this+0x8b`, `this+0x8c` ⇒ `MightCrit@0x8a`, `ForceOverkill@0x8b`, **`PreventOverkill@0x8c`** |
| `IdunBattle.Core.Services.DamagePredictionResult$$Add` | `MinMaxDamage$$ApplyCap` appelé sur `this+0x14`, `+0x24`, `+0x40`, `+0x50`, `+0x60` (5 `MinMaxDamage` de 16 o) ; un seul `int` agrégé, `@0x98` ; deux `List` `@0x38` et `@0x80` |

Le motif `Min@+8 / Max@+0xc` **survit à la migration** : l'ancien `AccurateHealthDamage@0x58`
donnait bien `Min@0x60 / Max@0x64`. Ce n'est donc pas `MinMaxDamage` qui a changé, c'est
l'**emplacement des champs dans le struct englobant**.

| champ | hook aujourd'hui (`kqkbjqfb6c`) | `rnca9r7q6c` (re-dérivé) |
|---|---|---|
| `HealthDamage.Min` / `.Max` | `0x60` / `0x64` | **`0x1c` / `0x20`** |
| `MightCrit` | `0xB1` | **`0x8a`** |
| `ForceOverkill` | `0xB2` | **`0x8b`** |
| `PreventOverkill` | `0xB3` | **`0x8c`** |
| taille du struct | ≥ `0xC0` | **`0xB0`** |

`TotalDamage`, `Armor`, `Shield` et `AppliedHits` **ne sont PAS re-dérivés ici** : `Add` montre
trois `MinMaxDamage` restants (`0x40`, `0x50`, `0x60`) et un `int` agrégé (`0x98`), sans dire lequel
est lequel. Les nommer demande de lire les écrivains (`GetAllPredictions`,
`CalculateProbabilisticDamage*`) — c'est le travail du chantier ci-dessous, pas de ce cas.

### 2quater. Appariement des trois `MinMaxDamage` restants — fait en #276, par XREF

Aucun de ces champs n'a d'accesseur `get_*`. On les a donc nommés par leur **consommateur**, pas
par un ordre de déclaration supposé — chacun est une fonction NOMMÉE qui ne fait rien d'autre que
lire cet offset :

| off | champ | ce qui le nomme |
|---|---|---|
| `0x40` | `HealthDamage` → Min `0x48` / Max `0x4c` | `IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage` = `MinMaxDamage$$Avg(pred + 0x40)` |
| `0x50` | `ShieldDamage` → Min `0x58` / Max `0x5c` | `IdunBattle.AI.Utilities.DamageUtility$$GetShieldDamage` = `MinMaxDamage$$Avg(pred + 0x50)` |
| `0x60` | `TotalDamage` → Min `0x68` / Max `0x6c` | `unit_HUD_test$$CreateDamagePrediction` y écrit `minArmor + minHealth` / `maxArmor + maxHealth` ; `PredictAttackRaw` y pose le retour de `MinMaxDamage$$Add(a, b)` |
| `0x98` | `AppliedHits` (int) | `PredictAttackRaw` le pose à **1** à l'instant précis où UN `HitDamage` est ajouté à la liste `@0x80` ; `DamagePredictionResult$$Add` le somme (seul `int` agrégé) |

Deux autres champs tombent au passage, et ils **corrigent l'ancien décodeur** :

* **`0x04` = `CurrentShield`**, pas `CurrentArmor`. Deux sources : `CalculateProbabilisticDamagePart`
  fait `Math.Min(this[4], scenario.ShieldDamage)` (un dégât de bouclier plafonné par le bouclier
  courant) et `CalculateProbabilisticDamage` cape le total à `this[0] + this[4]` ;
  `unit_HUD_test$$CreateDamagePrediction` y écrit son argument `currentShield`.
* **`CurrentArmor` n'a AUCUN lecteur** dans ce build. Le décodeur rend donc `armorBefore = null` —
  une absence déclarée, pas un offset deviné. C'est exactement le défaut qu'on répare : `+0x04`
  rendait une valeur *plausible* sous le nom « armor », et personne ne pouvait le voir.

Deux champs restent **non identifiés** et ne sont pas exposés : `0x08` (8 o) et `0x9c` (4 o).

### 2quinquies. Ce que #276 a livré

Un décodeur UNIQUE — `frida/hooks/game/damage-prediction.ts` — qui porte la table ci-dessus avec
la fonction native qui prouve chaque ligne, et que les six fichiers de hooks appellent désormais.
Plus aucun offset de prédiction n'est écrit ailleurs.

Il porte **deux gardes**, parce que le défaut reviendra :

1. **taille de classe** — `il2cpp_class_instance_size` confronté aux tailles RE (`0xB0`, `0xC8`,
   `0x28`). C'est le signal le plus précoce d'un changement de build et il ne coûte ni bataille ni
   cible : `aiPredict` rend alors `layoutError` non nul au lieu d'une plage inventée ;
2. **sentinelles de forme** au décodage (`shapeErrors`) — un `bool` hors `{0,1}`, un `min > max`,
   des PV négatifs. Elles attrapent l'autre moitié du problème : la classe intacte mais une base
   fausse (mauvais boxing, mauvais stride, pointeur d'event mal calculé). `mightCrit = 25` était
   précisément ça.

Sonde de non-régression : `python scripts/python/probe_276_prediction_decoder.py` — elle confronte
la plage rendue au dégât **mesuré live** (`hp_avant − hp_après`, victime increvable) et nomme chaque
sentinelle en échec. Elle compare à une grandeur MESURÉE, jamais à une constante de référence qui
se périmerait au même rythme que les offsets.

### 2ter. Portée réelle du défaut — 6 fichiers, ~25 sites

Le même struct est relu à la main par `frida/hooks/features/ai-step/rpc-predict.ts`,
`playbook-predict.ts`, `rpc-snapshot.ts`, `state.ts`, `projection.ts` et
`features/scorer-damage-trace.ts`. **Tous portent les anciens offsets.** Corriger le décodeur est
donc un chantier à part entière, et il exige une **RÉINJECTION** pour être validé — geste interdit
à un solveur tant que d'autres agents tournent. D'où le partage retenu ici :

* ce qui est **réparable côté Python et validable sans reinject** l'a été (§3) ;
* ce qui **ne l'est pas** échoue désormais **bruyamment**, en accusant l'instrument (§4).

## 3. La réparation : le montage mesure le dégât LIVE, plus aucune prédiction

`probe_178_overkill_gate.py` avait **deux** passes 1, toutes deux disqualifiées :
`_tune_hp` lisait `aiPredict` (canal mort) et `_tune_hp_replay` **rejouait le vecteur offline** —
c'est-à-dire que le PORT calibrait le montage censé l'éprouver.

Les deux sont remplacées par **`_measure_live_damage`** : même seed, même composition, même
géométrie que le régime, mais **victime increvable** (`--hp-target 200000`) ; on caste le vecteur
**en live** et on lit `hp_avant - hp_après`. La victime survivant, la lecture donne le dégât
**calculé** du vecteur entier — exactement la grandeur que `IsOverkill` compare à
`targetInitialHealth`. Les deux bouts sont live ; il ne reste ni prédiction, ni port, dans
l'installation du régime.

**Ce qui rend la passe 1 exacte, et c'est le point mesuré :** le tirage est **reproductible** à
seed + séquence d'actions égales.

```
seed 17811, PV 200000, 3 runners successifs : D = 2375 / 2375 / 2375
seeds 17811 / 17812 / 17813                 : D = 2375 / 2575 / 3051
seed 17811, crit force 100,1                : D = 2774 / 2774
```

La passe 1 rend donc le tirage **exact** que la passe 2 produira. Les PV du régime valent
`0,95 x D` : 5 % de marge de **létalité**, 90 % de marge sous le **seuil** (il faudrait
`D >= 2 x PV`, soit 1,9 x la mesure, pour que l'overkill devienne naturel).

La mesure est **toujours prise à `--crit 0,0`**, y compris pour le régime `crit` : la paire
`crit`/`nocrit` partage ainsi ses PV et reste comparable. Le régime `crit` est ensuite mesuré une
seconde fois **avec son crit** — c'est ce dégât-là (2774) qui doit tomber dans `[PV, 2 x PV)`.

Deux régimes distincts, tranchés sur la même mesure :

* `lethal_below_threshold` = `PV <= D < 2 x PV` — le verdict dépend d'un **argument** (`isCritical`,
  `isForceOverkill`) : c'est la fenêtre où #R33 mesure ;
* `above_threshold` = `D >= 2 x PV` — l'overkill est **naturel**, le verdict est vrai sans argument :
  c'est la fenêtre où #178 mesure ses gates d'unité.

Les tests assertent l'un ou l'autre **explicitement**, au lieu de comparer des bornes de prédiction.

### Mesures, montage réparé (seed 17811 / 17833, board `MC1_67`)

| régime | PV | dégât LIVE | régime atteint | observable live | port |
|---|---|---|---|---|---|
| `control` (genesPrimus) | 400 | 2375 | overkill **naturel** | crescendo `0 -> 1` | overkill |
| `titus` (ultraTitus, flag 0x13) | 400 | 2375 | overkill **naturel** | crescendo `0 -> 0` | pas overkill |
| `crit` | 2256 | 2774 | létal **sous le seuil** | crescendo `0 -> 1` | overkill |
| `nocrit` | 2256 | 2375 | létal **sous le seuil** | crescendo `0 -> 0` | pas overkill |
| `revive-crit` | 8889 | 9334 | létal **sous le seuil** | victime **morte** | morte |
| `revive-nocrit` | 8889 | 9357 | létal **sous le seuil** | victime **revive** | revive |
| `revive-flail` | 19971 | 21023 | létal **sous le seuil** | victime **morte** | morte |

Les deux prédicats de régime sont **mutuellement exclusifs et tous deux observés** dans le même
fichier (`above_threshold` vrai sur `control`/`titus`, `lethal_below_threshold` vrai sur les cinq
autres) : un test qui assertirait le mauvais rougirait. La discriminance du montage n'est donc pas
une supposition.

`tests/engine/runner/test_overkill_gate_live.py` : **8 passed** (était 3 failed + 5 skipped).

### Généralisation : seed 20000, mêmes verdicts, montage auto-calibré

`probe_178_overkill_gate.py --case r33 --seed 20000` — les quatre régimes s'installent sur des
dégâts entièrement différents (2768 ; 2623 → 2639 avec crit ; 8312 ; 9119 → 9350), et les verdicts
live sont inchangés : crescendo `0 -> 0` sans crit / `0 -> 1` avec, victime revive sans crit /
morte avec. **BILAN OK.** Ce que ça prouve : les PV ne sont plus une constante héritée d'une
mesure d'un autre build, ils sont re-dérivés à chaque montage.

### Ce que la mesure live a RÉVÉLÉ au passage — un écart port/natif sur FlailSwing

Le montage publie désormais, côte à côte, le dégât **live** du vecteur et le **contrepoint** du
port sur le même état. Sur `revive-flail` :

```
degat LIVE 21023   |   contrepoint port 21680     (+657, soit +3,1 %)
```

L'écart était **invisible** tant que le montage se calibrait sur le port (`_tune_hp_replay`) : les
deux côtés bougeaient ensemble. Il ne fait tomber aucun test — les deux valeurs restent dans
`[PV, 2 x PV)` — mais c'est un vrai désaccord de dégât sur `FlailSwing` (1042), à instruire à part
(décomposition par étage, jamais un scalaire à ajuster).

## 4. Ce qui reste rouge, et pourquoi c'est le bon état

`tests/engine/runner/test_prevent_overkill_decision_live.py` (**4 failed**) mesure le champ
`PreventOverkill` **dans le résultat de prédiction** (`result@+0xb3` côté hook, `@0x8c` en réalité)
et les **bornes RAW natives**. Ces deux grandeurs n'existent nulle part ailleurs : les remplacer par
`combatSnapshot.unitFlags` reviendrait à supprimer la garde — ce test existe précisément pour
vérifier que le décodeur **lit** ce champ.

Les trois skips sont donc devenus des **échecs**, et le message accuse l'instrument, pas le
montage :

```
montage prevent-overkill NON INSTALLE (ultraTitus) : CANAL MORT (#268) -- le decodeur du struct
de prediction lit des offsets PERIMES sur le build courant. [...] -- sentinelles :
probability=0 (nulle) ; mightKillDmg=0 alors que la paire est au contact (bornes RAW lues [0,0])
```

La garde repose sur trois **sentinelles** que le natif ne peut pas produire — un `bool` hors
`{0,1}`, une probabilité nulle sur un event rendu, une borne haute de dégât nulle sur une paire au
contact. Elles sont posées **avant** le test de régime : sans ce tri, l'échec dirait « régime
inatteignable » et enverrait re-crafter un roster pour un problème qui n'est pas là.

**Aucun `pytest.skip` ne subsiste dans les fixtures de cette famille.** Un montage qui ne s'installe
pas échoue ; c'est la seule façon qu'il a de se faire voir.

## 4bis. Bilan chiffré

`pytest tests/engine/ -k "overkill_gate or prevent_overkill_decision"` (13 tests sélectionnés) :

| | avant (`dd129216`) | après |
|---|---|---|
| passed | 1 | **9** |
| failed | 4 | 4 (tous nommés « CANAL MORT », tous #195) |
| **skipped** | **8** | **0** |

Le nombre de rouges n'a pas bougé, et c'est voulu : trois d'entre eux **étaient** des skips. Ce qui
a changé, c'est qu'aucun test de cette famille ne peut plus passer sans avoir mesuré.

## 5. Ce qui n'est PAS couvert

* ~~**Le décodeur lui-même n'est pas corrigé.**~~ **FAIT en #276** (cf. §2quater / §2quinquies) :
  les six fichiers passent par un décodeur unique, les quatre champs manquants sont appariés par
  XREF, et deux gardes structurelles ont été posées. ⚠ **Le fix vit dans `frida/hooks/**` : il
  n'entre en vigueur qu'après un `build:hooks` + réinjection**, geste que l'auteur du fix ne fait
  pas. Tant que ça n'a pas eu lieu, `probe_276_prediction_decoder.py` mesure l'ANCIEN décodeur.
* **Les autres consommateurs du canal ne sont pas inventoriés fonctionnellement.** On sait *où* le
  struct est relu (§2ter) ; on ne sait pas lesquels de leurs tests sont déjà faux à cause de ça.
  `test_overkill_decision_live.py` (fixtures `overkill_decision_*` du même `conftest.py`) lit le
  même canal et garde ses `pytest.skip` — **hors périmètre de ce cas**, mais c'est le même piège.
* **La mesure live coûte un build de plus par régime** (passe 1 jetable). Le fichier complet tient
  en ~70 s grâce au cache de module ; un montage qui perdrait ce cache doublerait son coût.
* **La marge de 5 % (`_LETHAL_FRACTION`)** n'est pas dérivée d'une borne native : elle est calée sur
  la dispersion observée (ratio max/min = 1,28 sur trois seeds). Elle tient tant que le tirage reste
  reproductible ; si un jour il cesse de l'être, c'est la létalité qui lâchera la première — et le
  probe le dira (`la victime n'a pas ete tuee`, avec le dégât mesuré dans le message).
