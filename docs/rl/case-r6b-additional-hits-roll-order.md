# R6-b — ORDRE tirage/réduction du canal `additional_hits` (groupes `predefined`)

**Question (binaire)** : dans le canal de coups additionnels à groupe `predefined`, le natif
tire-t-il **AVANT** de réduire (roll-then-reduce, 2 tirages par coup) ou **APRÈS**
(reduce-then-roll, 1 tirage par coup) ?

**Réponse : roll-then-reduce, 2 tirages par coup.** Le port faisait reduce-then-roll ; il
manquait donc *à la fois* la bonne valeur (le modulo portait sur la mauvaise largeur) et un
tirage par coup (le resolve slot-8, que le natif consomme **sans condition**).

C'est l'étage **AMONT** de R6 : R6 décidait *comment* un tirage se matérialise, R6-b décide
*quel* tirage sort. Les deux se mesurent séparément — les mélanger revient à fitter deux étages
avec un scalaire.

---

## 1. RE — le décompilé, d'abord (gqfc5mff6c)

Les deux voies natives de coups additionnels retombent sur le per-coup
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (établi par R6 :
`…AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` → `ExecuteHits`, et
`IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` → slot 0x3c
`Core.Services.OperationProcessor$$AttackDamage` → `…AttackDamageOperation$$Execute` →
`ExecuteHits`). Le corps d'`ExecuteHit`, **lu dans son ordre** :

| # | appel natif | consommation RNG |
|---|---|---|
| 1 | `IdunBattle.Core.HitDamage$$GetDamage(attackData.HitDamage, rng, useAverage)` | **1 tirage SSI `min != max`** |
| 2 | slot 0xb → `IdunBattle.Core.Services.CritDamageInfo`, dont le champ 0 **est** ce dégât | — |
| 3 | slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack` (le `Nullable<int>` damage de sa struct d'entrée = `CritDamageInfo.Damage`) | 0 |
| 4 | slot 8 `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` | **1 tirage, TOUJOURS** |

Les deux fonctions de tirage sont lues verbatim, et leur **asymétrie est le cœur du cas** :

```
HitDamage$$GetDamage(this, rng, useAverage)          RandomlyResolveMinMaxDamage(this, pred)
    if (min == max)  return min;      <-- GATE           rng.Range(pred.min, pred.max + 1);
    if (useAverage)  return (min+max)/2;                 // AUCUN gate min == max
    return rng.Range(min, max + 1);
```

Reste à établir la forme du `HitDamage` d'un coup additionnel.
`IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData` bâtit l'`AttackData` de
chaque groupe et son instruction utile est
`IdunBattle.Core.HitDamage$$.ctor(min = descripteur.minDmg, max = Nullable(descripteur.maxDmg))` —
un groupe `predefined` (`RandomAmount(ConfigVar(0xc), ConfigVar(0xd))`) y arrive donc **NON
dégénéré**.

⇒ étape 1 **tire** (c'est LA valeur brute du coup), étape 3 la réduit, étape 4 tire **encore**,
sur une cellule dégénérée : le tirage est **gaspillé** mais bien consommé.
⇒ **ROLL-THEN-REDUCE, 2 tirages par coup.**

Ce n'est pas un patron neuf : c'est **exactement** la branche `post_roll` de
`damage_hits.py::_one_hit` (`is_attack_damage_op=True`), déjà mirrorée et validée bit-exact pour
le vecteur ability bounds-mode de la **même famille ATTACK**. Un coup additionnel `predefined` est
structurellement le même objet — un `HitDamage` non dégénéré posé dans l'`AttackData`. Le port
avait *deux façades offline pour une seule opération native* : un fork de port.

---

## 2. Deux cas discriminants, sur deux AXES différents

Un seul montage ne suffit pas : les deux composantes du fix (l'**ordre** et la **consommation**)
ne se voient pas dans le même régime.

### 2.a — Axe LARGEUR DU MODULO : `orksRuntherd` / `SquigHound`

2 coups `predefined` `[2660, 3988]`, profil `Physical` **PiercingRatio 1**, cible
`ultraApothecary` forcée à `--armor-target 6000` (fixture `_pierce_floor_regime`). La branche
perçage l'emporte, donc la réduction est une **multiplication** : largeur BRUTE 1329 vs largeur
RÉDUITE 14 (cellules `[27, 40]`). Le modulo n'est pas le même ⇒ **le PREMIER coup déjà**
discrimine. `--crit 0,0 --block-target 0,0` ; cible sans `BigTarget`/`Vehicle` (`BeastSlayer`
inerte, %-listes vides) ni `SwornProtector`.

| seed | live (groupe) | reduce-then-roll | **roll-then-reduce** | roll-then-reduce SANS resolve |
|---|---|---|---|---|
| 777 | `[32, 37]` | `[34, 35]` | `[32, 39]` | `[32, 34]` |
| 31337 | `[30, 34]` | `[37, 28]` | **`[30, 34]`** | `[30, 37]` |
| 12345 | `[38, 35]` | `[31, 31]` | **`[38, 35]`** | `[38, 39]` |
| 314159 | `[27, 33]` | `[31, 32]` | `[27, 35]` | `[27, 36]` |
| 88 | `[30, 37]` | `[37, 30]` | **`[30, 37]`** | `[30, 32]` |

⇒ **1ᵉʳ coup : roll-then-reduce 5/5, reduce-then-roll 0/5**, les 5 montages étant discriminants.
Sur les **3** seeds où le 2ᵉ coup est lui aussi reproduit, la variante **sans** resolve échoue à
chaque fois (**3/3**) : le tirage gaspillé n'est pas optionnel. Les 2 seeds restantes relèvent du
résidu R6-b' (§4).

### 2.b — Axe CONSOMMATION : `admecRuststalker` / `CordClaw`

`CordClaw` (1122) pose sur **lui-même** l'effet 1250 ; les attaques suivantes du porteur portent
2 coups `predefined` profil `DirectDamage` **PiercingRatio 100**. À p100,
`idun.…StaticBattleRules.Damage$$GetDamageWithPiercing` rend `max(0, d − armure, d × 1.0) = d` :
la réduction est **l'identité**, donc les deux ordres donnent le **même 1ᵉʳ coup** — ce montage
est **aveugle** à l'axe précédent. Ce qui discrimine ici est le **seul resolve gaspillé**, qui
décale le flux RNG d'un tirage : c'est le **2ᵉ** coup qui tranche.

| seed | live (groupe) | reduce-then-roll | **roll-then-reduce** | roll-then-reduce SANS resolve |
|---|---|---|---|---|
| 777 | `[1266, 1222]` | `[1266, 1189]` | **=live** | `[1266, 1189]` |
| 31337 | `[1058, 1172]` | `[1058, 1114]` | **=live** | `[1058, 1114]` |
| 12345 | `[961, 1294]` | `[961, 1048]` | **=live** | `[961, 1048]` |
| 314159 | `[1007, 1092]` | `[1007, 1320]` | **=live** | `[1007, 1320]` |
| 88 | `[977, 1256]` | `[977, 1275]` | **=live** | `[977, 1275]` |
| 4242 | `[1312, 890]` | `[1312, 1291]` | **=live** | `[1312, 1291]` |
| 2024 | `[1264, 1236]` | `[1264, 963]` | **=live** | `[1264, 963]` |

⇒ **2ᵉ coup : roll-then-reduce AVEC resolve 7/7 ; reduce-then-roll 0/7 ; sans resolve 0/7.**
Le 1ᵉʳ coup est reproduit 7/7 par tous les modèles — non discriminant **par construction**, et
c'est ce qui fait de ce cas un cas *indépendant* du premier.

Ce porteur n'a **ni** `GetStuckIn` **ni** extra-dégât conditionnel : les deux coups du groupe y
sont bit-exacts, ce qui **attribue** le résidu §4 à `orksRuntherd`, pas au canal.

---

## 3. Le port

`engine/runner/operations/additional_hits.py::execute_additional_hits` passe désormais à
`_run_hits` les **bornes BRUTES** du descripteur et sa réduction en `post_roll`, avec
`is_attack_damage_op=True` (famille ATTACK ⇒ resolve slot-8 consommé) :

```
hd = HitDamage(g_min, g_max)                 # au lieu de HitDamage(reduce(g_min), reduce(g_max))
_run_hits(..., post_roll=_reduce, is_attack_damage_op=True, ...)
```

`reduce_group_damage` — le foyer unique de l'étage matérialisation posé par R6 — est **inchangé**
dans sa formule ; seul son call-site change (il reçoit la valeur tirée, plus les bornes). Les deux
étages restent donc séparés, et la garde R6 continue de verrouiller l'aval.

**Max-out `WeaverOfFate` (#202-A)** : `_apply_max_out` reste appliqué, désormais aux bornes
BRUTES — la **valeur** produite est la même (`post_roll(max)`), mais le port court-circuite le
tirage brut (`get_damage` gate `min == max`) là où le natif l'a déjà consommé avant d'évaluer
`IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage`. Écart de **consommation** strictement
identique à celui du vecteur ability bounds-mode (`damage_ops/ability.py`, même appel) : no-op
tant que l'attaquant ne porte pas l'effet 1185.

**Groupes `amount`** (CyclicIonBlaster, FoulInfusion, ExplosiveMaladies, FleshmetalGuns) : ils
passent par la **même** `ExecuteHit`, donc le même ordre — le fix s'y applique aussi. Leurs
**bornes**, elles, restent fausses : c'est le résidu **R6-c**, distinct et non traité ici.

---

## 4. R6-b' — le `Maybe` de `GetStuckIn` sur les coups d'un groupe — **FERMÉ 2026-07-28**

> **PORTÉ ET VALIDÉ LIVE** — fiche complète : **`case-r6bp-after-hit-maybe-on-groups.md`**
> (port 8/8 + 6/6 sur deux montages à **parité inversée**, témoin sans trigger 4/4 bit-exact,
> gardes `test_additional_hits_after_hit_maybe_live.py`). Ce qui suit est la RE telle qu'elle avait
> été établie ici ; elle est exacte, mais le modèle chiffré du bas (« k = 1 si le nombre de coups
> d'arme est impair ») s'est révélé **sous-déterminé** — cf. §4.b.

Sur `orksRuntherd`, le 2ᵉ coup du groupe n'était reproduit que **3/5**. La cause est **résolue au
décompilé** ci-dessous.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger`, lu verbatim :

```
On(8 /*AfterHit*/, 1)
  & AmountIsOdd(CurrentHitIndex())
  & OwnerIsCaster
  & !AmountIsGreater(MinDistance(caster, target), Direct(2))
```

avec le behaviour `Maybe(AddBonusHitsToCurrentHitGroup(…), GetBonusHitChance())`. La chaîne du
compteur :

* `IdunBattle.Entities.Formulas.CurrentHitIndexFormula$$Calculate` lit `AbilityEntities+0x110` ;
* ce champ est alimenté par `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`
  (qui émet le trigger `On(8)` à la fin de **chaque** `ExecuteHit`, y compris ceux d'un groupe)
  depuis son `param_5` = le `param_3` d'`ExecuteHit` ;
* `ExecuteHits` le remplit avec `*(currentAttack + 0x30)` ;
* `IdunBattle.Operations.ADamageOperation$$UpdateCurrentAttackAfterHit` fait
  `*(currentAttack + 0x30) += 1` **après chaque coup** ;
* et `…AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` passe **le même**
  `currentAttack` à `ExecuteHits`.

⇒ **`CurrentHitIndex` est le compteur de coups de l'ATTAQUE, continu à travers les
sous-opérations** — il ne repart pas à 0 pour un groupe additionnel.

**MESURE** (`probe_r6b_additional_hits_order.py --case squig --extra-rolls 4`, qui consomme *k*
tirages entre deux coups du groupe) : le modèle « **k = 1 si le nombre de coups d'arme ÉMIS est
IMPAIR, sinon 0** » reproduit le live **5/5** —

| seed | coups d'arme émis | k requis | live 2ᵉ coup | k=0 | k=1 |
|---|---|---|---|---|---|
| 777 | 3 (impair) | **1** | 37 | 39 | **37** |
| 314159 | 3 (impair) | **1** | 33 | 35 | **33** |
| 12345 | 3 (impair) | 0 ou 1 (indistinguable) | 35 | 35 | 35 |
| 31337 | 4 (pair) | **0** | 34 | **34** | 29 |
| 88 | 4 (pair) | **0** | 37 | **37** | — |

soit **3 seeds strictement discriminantes** (777 et 314159 imposent k=1, 31337 impose k=0), et la
parité du nombre de coups d'arme sépare exactement ces cas — ce qui est la signature du compteur
CONTINU ci-dessus (3 coups d'arme ⇒ le 1ᵉʳ coup du groupe est d'index 3, **impair** ⇒ un `Maybe`
est roulé juste après lui).

### 4.b — Ce qui a été porté, et pourquoi le modèle ci-dessus ne suffisait pas

Le port (`case-r6bp-after-hit-maybe-on-groups.md`) threade `hit_index0` dans `_run_hits` et
`bonus_hit_chance` dans `execute_additional_hits` — **un seul site d'évaluation**, pas un second.
La question laissée ouverte ici est tranchée : `AddBonusHitsToCurrentHitGroupBehaviour$$Execute`
écrit dans la liste `+0xf0` du CASTER, que `ADamageOperation$$UpdateHitGroupAfterHit` déverse dans
le `hitGroup+0x58` **de la sous-opération courante** ⇒ un succès pendant un groupe défère un coup
bonus **dans ce groupe**.

Le modèle « k = 1 si le nombre de coups d'arme émis est IMPAIR » est **numériquement correct sur le
préfixe à 2 coups**, mais **sous-déterminé** : il ne dit rien du **3ᵉ** coup que le natif émet quand
le `Maybe` du groupe RÉUSSIT. La ligne « 12345 : indistinguable » ci-dessus en est la trace — le
live y a en fait **trois** coups de groupe, `[38, 35, 36]`, dont le troisième est marqué
`Additional_Hit_TriggeredAbility_Source: 1234` (= `AbilityOrEffect(0x4d2)` de `CreateBehaviour`).

---

## 5. Ce qui n'est PAS couvert

* **R6-c** — bornes COMBAT des groupes `amount` (la face native tire dans
  `RandomAmount(minDmg, maxDmg)`, le port applique `amount ± 20 %`). Inchangé par ce cas.
* **#202-A max-out** — 1 tirage brut non consommé en régime `WeaverOfFate` (cf. §3) ; la valeur
  reste juste. Non exercé (aucun montage ne combine 1185 et un porteur de groupe).
* **crit sur les coups d'un groupe** — le port passe `crit_chance=0, crit_enabled=False` ; aucun
  montage n'a exercé un descripteur portant une plage crit.
* **`Maybe` after-hit sur le vecteur ABILITY** — porté sur la seule voie NORMALE (cf. §4.b) ;
  `damage_ops/ability.py` reste muet sur les DEUX faces (arme et groupes). Résidu nommé dans
  `case-r6bp-after-hit-maybe-on-groups.md` §5.
* Les deux points « à confirmer live » de `case-202` §7 (gate `hp > 0`, `failed_block` remis à
  zéro entre la phase d'arme et les groupes) restent ouverts.

---

## 6. Reproduire

```
# cas 1 -- axe LARGEUR (orksRuntherd / SquigHound, regime percage-dominant)
python probe_r6b_additional_hits_order.py --case squig --seeds 777,31337,12345,314159,88

# cas 2 -- axe CONSOMMATION (admecRuststalker / CordClaw, DirectDamage p100)
python probe_r6b_additional_hits_order.py --case cordclaw --target necroWarden \
    --a-units "necroWarden,necroWarden" --seeds 777,31337,12345,314159,88,4242,2024

# residu R6-b' (FERME) : combien de tirages manquent entre deux coups du groupe ?
python probe_r6b_additional_hits_order.py --case squig --seeds 777,314159,12345,31337 \
    --extra-rolls 4
# ... et sa mesure de FERMETURE (port livre vs contrefactuel, deux parites) :
python probe_r6bp_after_hit_maybe_groups.py --case squig --seeds 777,314159,12345,88,31337,2468,20202,4242
python probe_r6bp_after_hit_maybe_groups.py --case parry --seeds 777,314159,12345,88,31337,2468
```

Gardes live : `tests/engine/runner/test_additional_hits_roll_order_live.py` (les deux axes)
et `tests/engine/runner/test_additional_hits_after_hit_maybe_live.py` (R6-b').
Fixture partagée du montage : `tests/engine/runner/_pierce_floor_regime.py`
(`pierce_dominant_regime`, `drive`, `live_amounts`, `replay_orders`).
