# case-333 — `MinMaxDamage$$Avg` ARRONDIT, et il arrondit DEMI-VERS-LE-PAIR

Question posée, binaire : **quel mode d'arrondi `IdunBattle.Core.Services.MinMaxDamage$$Avg`
applique-t-il, et le port le fait-il ?**

Réponse mesurée : **`MidpointRounding.ToEven` (demi-vers-le-pair)** ; le port, lui, rendait
`(min + max) / 2.0` et **gardait le `.5`**. Écart sur toute somme IMPAIRE, dans le composite
`Damage(34)` **partagé** — donc sur tout le rail de dégât, jusqu'à l'attaque normale `69`.

Résidu nommé par #329 (`case-302-2` §5), laissé hors de son périmètre parce que son rayon est
global. C'était le bon appel : la correction touche deux méthodes et déplace toute utilité de
dégât du moteur.

---

## 1. Ce que le natif fait — lu au décompilé (`rnca9r7q6c`), rien de déduit

```
IdunBattle.Core.Services.MinMaxDamage$$Avg(this) =
    Fix64.op_Explicit( Fix64.Round(
        Fix64.op_Division( Fix64.op_Implicit(this.Min@+0x8) + Fix64.op_Implicit(this.Max@+0xc),
                           Fix64.op_Implicit(2) ),
        midpointRounding = 0 ) )
```

Les quatre étages, chacun relu :

| étage natif | corps | conséquence |
|---|---|---|
| `FixMath.NET.Fix64$$op_Implicit` (int → Fix64) | `(long)(int)v << 32` | exact, **sign-extend** (négatifs corrects) |
| `FixMath.NET.Fix64$$op_Division` | quotient accumulé à `2^-33` puis `(q+1)>>1` | pour `/2` : rend `(Min+Max) << 31` — fraction `0` (somme paire) **ou** exactement `0x80000000` (somme impaire), jamais autre chose |
| `FixMath.NET.Fix64$$Round(value, 0)` | voir ci-dessous | **le seul étage qui décide** |
| `FixMath.NET.Fix64$$op_Explicit` (Fix64 → long) | `raw >> 32` (floor) | exact après `Round`, qui rend déjà un raw intégral |

```
FixMath.NET.Fix64$$Round(value, midpointRounding) :
    integral = value & 0xffffffff00000000        # floor vers -inf
    frac     = value & 0xffffffff
    frac <  0x80000000                            -> integral
    frac == 0x80000000 && midpointRounding == 0   -> ((value >> 0x20) & 1) == 0 ? integral
                                                                                : integral + One
    frac == 0x80000000 && midpointRounding != 0   -> integral < Zero ? integral : integral + One
    sinon                                         -> integral + One
```

`One` = `Fix64` statics`+0x20` = `0x100000000` et `Zero` = statics`+0x28` = `0`, tous deux écrits
par `FixMath.NET.Fix64$$.cctor` (littéraux lus, pas supposés). `midpointRounding = 0` prend donc la
branche **de PARITÉ de la partie entière** = `MidpointRounding.ToEven` ; l'autre branche
(`AwayFromZero`) est celle qui compare à `Zero`, et elle n'est PAS empruntée ici.

⚠ Le cast `(int)` est **APRÈS** `Round`, pas avant : `Avg` n'est pas « une division entière ».

### Les deux consommateurs du rail de dégât

```
IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage(prediction) :
    r = Fix64( MinMaxDamage$$Avg(prediction + 0x40) )        # AccurateHealthDamage
    if (prediction.LimitedByMinHp@+0x88) r = Fix64(prediction.CurrentHealth@+0x00)
    return r

IdunBattle.AI.Utilities.DamageUtility$$GetShieldDamage(prediction) :
    return MinMaxDamage$$Avg(prediction + 0x50)              # AccurateShieldDamage
```

et `IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` les
**SOMME après coup** (`op_Addition(hAvg, sAvg)`) : **deux arrondis, pas un**. Arrondir la somme
des deux demis donnerait `1` là où le natif donne `0` (bornes `[0,1]` des deux côtés).

> Offsets `rnca9r7q6c`. L'en-tête de `engine/utilities/damage.py` cite ceux de `gqfc5mff6c`
> (`0x58` / `0x78` / `0xB0`) — la STRUCTURE est identique, seuls les offsets ont bougé.

---

## 2. Pourquoi #329 ne pouvait PAS conclure sur le mode

Un `.5` EXACT n'existe que si `Min + Max` est **IMPAIR**, et sur un `.5` dont la partie entière est
**IMPAIRE**, demi-vers-le-pair et demi-vers-le-haut rendent la **même** valeur. La mesure de #329
(`3771 + 5652` = `9423`, floor `4711`, IMPAIR) ne voyait donc que le côté où les deux modes
coïncident. Sa garde asserte d'ailleurs `nat - port > 0` sur les sommes impaires — vrai pour ce
côté-là seulement ; sur un floor PAIR le natif DESCEND et l'écart est NÉGATIF.

C'est la forme générale du piège : **un montage qui n'exerce qu'une parité rend un vert qui ne dit
rien du mode.**

---

## 3. Le correctif — au FOYER, une seule fois

| fichier | changement |
|---|---|
| `engine/services/min_max_damage.py` | **`min_max_avg(min, max)`** — mirror 1:1, composé des primitives DÉJÀ portées de `engine.services.fix64` (`from_int` / `div` / `round_raw(mode=0)` / `to_int`). `MinMaxDamage.avg()` (qui faisait `// 2`) le délègue. |
| `engine/utilities/damage.py` | `DamageUtility.get_health_damage` et `get_shield_damage` appellent `min_max_avg` au lieu de `(a+b)/2.0`. |

`fix64.round_raw(raw, mode=0)` portait **déjà** la branche `ToEven` — elle n'avait simplement
aucun appelant à `mode=0` sur ce chemin. Rien de neuf n'a été inventé : le correctif est un
**câblage**.

`MinMaxDamage.avg()` n'avait **aucun appelant** dans le dépôt (mesuré : `git grep "\.avg()"` = 0) ;
sa correction est donc sans effet direct, mais c'est l'homonyme de la fonction native et c'est là
que la lecture du décompilé doit vivre.

---

## 4. La mesure LIVE — la parité est PILOTÉE, pas subie

`AccurateHealthDamage` est **capée aux PV de la cible**, et `rl_duel build --hp-target H` pose
`Health = RemainingHealth = H`. Avec `rawMin < H < rawMax`, les bornes valent exactement
`[rawMin, H]` : **`H` choisit la parité de la somme ET celle de la partie entière**. Deux bras à
`H` distants de 2, tout le reste identique.

Sur chaque bras : `pairUtility` NATIF
(`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`)
contre le terme dégât du PORT **nourri des mêmes prédictions natives** (`aiPlaybookPredict`) —
formule ISOLÉE, donc tout écart est un gap de LOGIQUE. Quatre variantes d'arrondi tournent sur ce
même feed, en remplaçant le seul `engine.utilities.damage.min_max_avg`.

`probe_333_minmax_avg_rounding.py`, `ultraInceptorSgt -> genesPrimus`, board `MC1_67`,
bornes non capées `[4812, 7224]` :

| bras | PV | bornes | somme | floor | natif | `to_even` | `half_up` | `kept_half` | `trunc` |
|---|---|---|---|---|---|---|---|---|---|
| UP | 6019 | `[4812, 6019]` | 10831 impaire | 5415 **impair** | 139.9518 | **0** | 0 | **+0.5 pas** | **+1 pas** |
| DOWN | 6017 | `[4812, 6017]` | 10829 impaire | 5414 **pair** | 139.9485 | **0** | **−1 pas** | **−0.5 pas** | 0 |

`pas` = `100 / combinedMax` = la dérivée de l'utilité par unité de dégât (`DamageDealt` 80 +
`remaining` 20, `IdunBattle.AI.Utilities.DamageUtility$$.cctor`) ≈ `1.66e-2` ici. Écarts mesurés
conformes à `±0.02 pas` près.

⇒ **`to_even` est la SEULE variante nulle sur les DEUX bras.** Le mode est discriminé, pas supposé.

### Généralisation (le même protocole, ailleurs)

| montage | bornes non capées | verdict |
|---|---|---|
| `ultraInceptorSgt -> genesPrimus`, `MC1_67`, anneau (3,4) | `[4812, 7224]` | OK |
| `emperNoiseMarine -> necroWarden`, `MC1_67`, anneau (3,4) | `[1452, 2178]` | OK |
| `ultraInceptorSgt -> genesPrimus`, **`C1_03`**, anneau (3,6) | `[4812, 7224]` | OK |

> Sur `C1_03`, l'anneau centré en `(3,4)` rend des bornes `[0,0]` : l'élévation y empêche le
> contact. Ce n'est **pas** « couple non mesurable », c'est un centre mal choisi — le probe le dit
> désormais explicitement et l'anneau a été DÉPLACÉ en `(3,6)`.

### Le résidu de #329, re-mesuré sur SON montage

`probe_302_2_plagueburst_prediction.py --stage`, mêmes tuiles :

| tuile | bornes | somme | écart nat − port AVANT | APRÈS |
|---|---|---|---|---|
| `(4,4)` orksWarboss | `[3771, 5652]` | IMPAIRE | `+2.500e-03` | `+7.4e-09` |
| `(3,5)` necroWarden | `[3771, 5652]` | IMPAIRE | `+2.500e-03` | `+8.7e-09` |
| `(4,3)` astraCreed | `[2514, 3768]` | PAIRE | `−2.8e-09` | `−2.8e-09` |

---

## 5. Ce que le changement DÉPLACE

Consommateurs du composite `Damage(34)`, tous re-joués :

| garde | rôle | résultat |
|---|---|---|
| `test_plagueburst_mortar_prediction_live.py` | l'attribution du résidu par #329 | **RÉÉCRITE** — voir ci-dessous |
| `test_overkill_decision_live.py`, `test_prevent_overkill_decision_live.py` | confrontation par paire natif/port | 10 passed |
| `test_normal_attack_bonus_decision_live.py` | décision, attaque normale | 8 passed |
| `test_finaljustice_live.py` | `first_by_damage_utility` (face COMBAT) | 1 passed |
| `test_damage_roll_live.py`, `test_runner_attack_live.py`, `test_normal_attack_bounds_rounding_live.py` | rail de dégât COMBAT | 5 passed |

**La seule garde qui bouge est celle de #329**, et sa nouvelle valeur attendue est justifiée par le
natif : elle assertait `nat − port > 0` sur les sommes impaires (« le port SOUS-ESTIME »), ce qui
est faux dès que le port applique l'arrondi. Après le correctif elle ne passait plus que par
**bruit flottant** (`+7.4e-09 > 0`) — un vert qui ne dit plus ce qu'il prétend. Elle est réécrite
en : *l'écart est NUL sur les deux parités*, avec le pouvoir discriminant reporté sur une
**MUTATION** (rejouer le `.5` conservé et exiger que l'écart RÉAPPARAISSE sur les sommes impaires,
et seulement sur elles).

Deux call-sites COMBAT ne peuvent PAS bouger, et c'est lisible dans leur appel :
`engine/runner/abilities/thousandsons.py:171` (`sort_units_by_damage_utility(..., dmg_min, dmg_min)`)
et `engine/runner/abilities/votann.py:388` (`first_by_damage_utility(..., avg, avg)`) passent
`min == max` ⇒ somme PAIRE ⇒ aucun `.5`. Seul `final_justice.py:85` passe une vraie plage.

---

## 6. Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `tests/engine/test_333_minmax_avg_rounding_offline.py` (22 tests) | le MODE, sur une table de bornes choisies couvrant les deux parités ; que `trunc` / `half_up` / `.5 conservé` sont chacun **contredits** par au moins une ligne ; le floor vers −inf sur les négatifs ; le câblage des deux méthodes de `DamageUtility` ; le fait que les deux termes sont arrondis SÉPARÉMENT |
| `tests/engine/test_333_minmax_avg_rounding_live.py` (6 tests) | le même mode CONFRONTÉ au natif, sur les deux parités pilotées ; la non-dégénérescence du régime (`LimitedByMinHp` faux, pas de clamp — le pas mesuré vaut bien `100/combinedMax`) ; la MUTATION (`.5` conservé) rouge dans les DEUX directions |

**Mutation jouée** (arrondi du port remis dans `min_max_avg`) : **16 rouges** — 13 offline, 3 live.

---

## 7. Ce qui n'est PAS couvert

- **Le terme BOUCLIER n'est pas exercé LIVE.** `AccurateShieldDamage` vaut `[0,0]` sur tous les
  montages : `BC.Units[].Shield` existe mais **n'est pas honoré au déploiement** (mesuré —
  `--unit-stat "genesPrimus:Shield=6000"` rend `shieldBefore = 0`). La route pour l'exercer est de
  POSER un bouclier en bataille (vecteur `ArcaneShield`, cf. `case-n1-arcane-shield-vector.md`)
  avant de prédire. C'est le MÊME appel `min_max_avg`, couvert offline.
- **La branche `LimitedByMinHp`** court-circuite `Avg` : elle est gardée offline, jamais atteinte
  live sur ces montages.
- **Les bornes NÉGATIVES** (`floor` vers −inf) sont transcrites et gardées offline ; le rail de
  dégât ne les produit pas, elles ne sont donc pas confrontées.
- **Aucun renversement de DÉCISION n'a été construit.** L'écart vaut un demi-pas d'utilité
  (`50 / combinedMax`) ; le renverser demanderait deux candidats à égalité à moins que ça. Ce qui
  est mesuré est l'utilité PAR PAIRE, bit-exacte contre l'oracle natif — pas un changement d'argmax.
- **`IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamageAverage` est un AUTRE artefact** :
  `Half(Sum(Direct(minDmg), Direct(maxDmg)))`, un arbre `DSLFormulas`, dont l'arrondi est celui de
  `IdunBattle.DSL.AAmountFormula$$RoundFix64Result`. Il n'est PAS touché ici, et
  `engine/playbook/fury_of_the_ancients.py:103` en garde une transcription `// 2` — à confronter
  séparément.
  > **#339 — cette attribution est FAUSSE, et son verdict aussi.** Le site Fury ne passe pas par
  > `MinMaxDamageAverage` mais par `IdunBattle.DSL.AAmountFormula$$CalculateAverage`, qui **tronque**
  > (aucun Fix64 sur cette branche) : son `// 2` était JUSTE. Et `RoundFix64Result` en mode 0 est
  > bien `Fix64.Round(., ToEven)`, donc `MinMaxDamageAverage` arrondit COMME `Avg`. Détail et
  > chaîne de symboles : `case-339-arrondi-moyennes-residuelles.md` §1/§2.
- **`engine/ai/action_generators.py:417-418`** (`_spiritleech_lifesteal_util`) moyenne les bornes
  BRUTES à la main (`/ 2.0`). Son artefact natif est
  `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealAmountForPrediction`,
  **pas** `MinMaxDamage$$Avg` — non relu, laissé tel quel, nommé ici comme résidu.
  > **#339 — relu : il l'est, en fin de chaîne.** `GetHealAmountForPrediction` =
  > `PercentageOf(DamagePredictionFormula(…), hpToHealPct, Ceiling)`, et
  > `DamagePredictionFormula$$Calculate` finit par `MinMaxDamage$$Avg(prediction + 0x40)` =
  > `AccurateHealthDamage`. Le port lisait les bornes BRUTES **et** ajoutait un terme de bouclier
  > inexistant : **4.83 points d'utilité** d'écart mesurés, corrigé par `case-339` §3/§4.

---

## 8. Observation hors périmètre — la ligne `#268-a` du backlog est PÉRIMÉE

Le backlog dit que `aiPredict` / `aiPlaybookPredict` rendent du garbage sur `rnca9r7q6c`
(`totalDmg [1,100]`, `mightCrit = 25`, bornes RAW `[0,0]`) et pose comme critère d'acceptation
`test_prevent_overkill_decision_live.py` vert. **Mesuré le 2026-07-31** sur la session injectée :
l'event natif rend `healthDmg [4812, 7224]`, `mightCrit 0`, `probability 1`, `appliedHits 6`, et
`test_overkill_decision_live.py` + `test_prevent_overkill_decision_live.py` = **10 passed**. Le
correctif de décodeur (#276/#279) est donc EN VIGUEUR dans le bundle injecté. Ligne à fermer — pas
fait ici, hors périmètre.
