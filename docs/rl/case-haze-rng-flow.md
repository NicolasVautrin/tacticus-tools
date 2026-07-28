# case-#221 — le FLUX RNG du report `HazeOfCorruption` (natif 8 tirages, port 6)

> Fiche nommée par le SUJET et non par le numéro : `case-221-daemon-extrablock-rng.md` occupe déjà
> le préfixe `case-221-`.

**Critère (binaire)** : le port consomme-t-il le même NOMBRE de `genrand_int32` que le natif, aux
MÊMES points de la cascade ? Sinon, quelle opération native émet les tirages manquants ?

**Réponse** : non — l'écart mesuré (natif 8 / port 6 au régime PV 6000) recouvrait **quatre**
défauts indépendants, dont deux se compensaient en nombre mais pas en position. Après correctif :
**natif == port sur 5 régimes × 2 seeds**, avec un témoin observable indépendant du compte.

| régime (k = 1 relais sauf mention) | natif | port AVANT | port APRÈS |
|---|---|---|---|
| PV 8000 — la cible survit | 4 | 4 | **4** |
| PV 7354 — le coup fatal tombe PILE (leftover d'arme = 0) | 8 | 6 | **8** |
| PV 6000 — mort au 3e coup, 2 transferts | 8 | 6 | **8** |
| PV 5000 — mort au 2e coup, 3 transferts | 9 | 6 | **9** |
| PV 6000, **k = 0** (aucun relais, aucun bond) | 5 | 4 | **5** |

---

## 1. Le flux natif, rang par rang (k = 1, PV 6000)

| rang | émetteur natif | port AVANT |
|---|---|---|
| 0 | `HazeOfCorruption_TargetFinderAbility` → `PickRandomAmountSelector` (pool = {relais}) | ✅ |
| 1‑3 | les 3 coups d'arme | ✅ |
| 4 | `HazeCorruption_BonusHitAbility` — jet du montant du coup Toxic | ✅ |
| 5 | `OnToxicDamageAbility$$CreateBehaviour` → `Maybe(25)`, déclenché par le `On(0x10)` **du coup bonus** | ❌ **absent** |
| 6 | transfert #1 (effet 1077) — résolution du montant | ❌ **absent** |
| 7 | transfert #2 (effet 1077) — résolution du montant | ❌ **absent** |
| — | *aucun* `Maybe` sur les transferts (une seule série ⇒ `IsFirstHitInSeries` faux au‑delà du 1er) | ❌ **1 en TROP** |

L'attribution n'est pas arithmétique : chaque étage a été isolé par un régime qui le fait varier
seul (`k = 0` retire le finder ET les transferts ⇒ isole le coup bonus à **2** tirages ; PV 5000
ajoute un transfert et un seul ⇒ **1** tirage par transfert).

## 2. Les quatre défauts

### 2.1 `On(DamageDealt = 0x10)` n'a AUCUN gate « dégât appliqué > 0 »

`IdunBattle.Operations.ApplyDamageOperation$$Execute` — relecture : les deux émissions vivent dans
des blocs **distincts**, ce que le port avait fusionné (« émis DANS LE MÊME BLOC que `On(0xf)` »).

```
On(0x3a)  : aucun gate propre
On(0xf)   : (0 < local_7dc) || !HealthComponent.IsUnitWithHealthStat(cible)
            local_7dc = valeur de retour de FillUpStatComponent.Reduce  -> l'APPLIQUÉ
On(0x10)  : local_7e8 == 0                       <-- SEUL gate propre, aucun terme sur local_7dc
            local_7e8 <- 1 si (degat_sante_DEMANDE < 1) ; sinon <- octet hitInfo+0x94
```

⇒ le gate porté est le dégât **SANTÉ DEMANDÉ ≥ 1**. La différence n'existe que pour un coup qui
tombe sur une cible **déjà à 0 PV** — exactement le coup Toxic bonus (`Amount 0` en live).

**Témoin observable, indépendant du compte** : `OnToxicDamageAbility` pose `Contaminated` (1244) sur
la tuile de la cible quand son `Maybe(25)` passe. En résolvant le rang candidat du flux en
`NextBool[1,99]`, on PRÉDIT la pose — puis on la lit dans `tileMeta`. **19 confrontations, 19/19**,
et les deux bornes sont exercées : seed 55 → valeur **25** → pose ; seeds 123 et 64 → valeur **26**
→ rien. C'est ce qui établit que le natif émet bien `On(0x10)` sur le cadavre.

### 2.2 Le résolveur de montant de la branche reduce‑then‑roll était le mauvais

Deux fonctions natives distinctes, et une seule porte un gate largeur‑1 :

```
IdunBattle.Core.HitDamage$$GetDamage(hit, rng, useAverage)
    if (min == max) return min;                    <-- GATE largeur-1
    if (useAverage)  return (min + max) / 2;
    return rng.NextInternal(min, max + 1);

IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage(this, minmax)
    return rng.NextInternal(minmax.min, minmax.max + 1);   <-- AUCUN gate
```

Le port appelait `HitDamage$$GetDamage` là où le natif appelle le **slot 8**. Le correctif est gaté
par la **FAMILLE de factory** (`is_attack_damage_op`), pas par la largeur des bornes — la famille
ABILITY (`AbilityDamageOperation$$ExecuteHits`, qui appelle `HitDamage$$GetDamage` **directement**,
xref confirmé) garde donc son gate, et Stormcaller reste bit‑exact. Le changement est **strictement
no‑op dès que la cellule est large** (même appel, même valeur) ; il ne mord que sur une cellule
dégénérée — le cas des transferts (montant reporté) et du splash Psyker.

> **Ce correctif FERME le résidu backlog « Resolve slot‑8 non matérialisé dans
> `execute_normal_like` »**, mesuré sur son propre montage (`probe_130_pick_randomly_one_rng.py`,
> splash Psyker). Contre‑épreuve jouée dans les deux sens : avec l'ancien `damage_hits.py`,
> `k=1 → live 3 / port 2 (delta 1)` et `k=2 → live 3 / port 2 (delta 1)` ; avec le correctif,
> **delta 0** aux trois régimes — c'est-à-dire l'« attendu » que le probe imprimait sans l'atteindre.

### 2.3 Les N feuilles du transfert forment UNE série, pas N

`$$CreateTargetTriggerBehaviour` empile les `AttackDamage` sous **un seul**
`IdunBattle.Entities.Behaviours.AttackBehaviour` (`Attack(bonded, Owner@0x148, beh)`), donc le
`hitIndex` court d'une feuille à l'autre et `IsFirstHitInSeries()` n'est vrai qu'à la première.

Le port instanciait une feuille par transfert avec `is_first_hit=True` à chaque fois : un `Maybe`
en trop dès qu'un transfert portait le profil Toxic, **et la pose de `Contaminated` sur la tuile du
RELAIS au lieu de celle de la CIBLE**. Le modèle concurrent (« le natif n'émet pas `On(0x10)` pour
les transferts ») est **RÉFUTÉ** par les seeds 13 et 314, dont le rang qui suit les transferts passe
sous 25 sans qu'aucune tuile ne soit contaminée en live.

### 2.4 `AddLeftoverHit` ne filtre pas les montants nuls

`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` relu en entier : son **seul** gate
d'entrée est l'octet `hitInfo+0x15` (`if ((char)(param_4[2] >> 0x28) != 0) return;`) ; il construit
ensuite la `LeftOverDamage` et fait `List.Add` **inconditionnellement**.

Une entrée de montant **0** est donc poussée — le cas du coup fatal qui tombe pile sur les PV
restants. Régime construit exprès (`--hp 7354` = la somme exacte des trois jets de la seed 777) : le
relais reçoit bien **deux** événements, `[relais, 0, 1077]` puis `[relais, 1397, 1077]`. Filtrer le
0 côté port coûtait un `AttackDamage` (donc un résolve) **et** décalait le rang de tous les
transferts suivants dans la série — les défauts 2.3 et 2.4 sont couplés.

## 3. Le correctif

* `engine/runner/operations/damage.py` — `On(0xf)` et `On(0x10)` sortent de leur bloc commun ; le
  second est gaté par le dégât DEMANDÉ. L'octet `hitInfo+0x94` reste non modélisé (**résidu nommé** :
  il ne peut que RESTREINDRE l'émission).
* `engine/runner/operations/damage_hits.py` — branche `post_roll is None` : `next_internal(min,
  max+1)` sans gate quand `is_attack_damage_op` (mirror du slot 8), sinon `HitDamage$$GetDamage`.
* `engine/runner/operations/damage_ops/normal_like.py` + `abilities/behaviours/combat.py` —
  `is_first_hit` devient un paramètre (défaut `True` = inchangé pour tout appelant dont l'appel EST
  la série entière).
* `engine/runner/operations/left_over_damage.py` — le gate porte désormais sur `< 0` ; `None`
  (base nominale inconnue) reste la dégradation conservatrice, distincte d'une base valant 0.
* `engine/runner/operations/triggers/loki/haze_of_corruption.py` — émet une feuille par entrée,
  montant 0 compris, avec `is_first_hit=(i == 0)`.

## 4. La mesure

```
python probe_221_haze_rng_flow.py --seeds 777,88 --hp 8000,6000,5000,7354 --k 1
python probe_221_haze_rng_flow.py --seeds 88,17,55,512,13,314,123,64 --hp 6000 --k 0
python probe_209_haze_damage_transfer.py --seeds 777,88 --hp 8000,6000,5000     # garde du DÉGÂT
python probe_130_pick_randomly_one_rng.py --seed 777                            # résidu splash fermé
```

`probe_221_haze_rng_flow.py` réutilise la géométrie de `probe_207_haze_pool_ladder.py` et trace, pour
chaque tirage du replay offline, sa PILE d'appel `engine/` — c'est ce qui a nommé les deux volets
manquants au lieu de les deviner. Il imprime aussi la résolution `NextBool[1,99]` de chaque valeur
brute et l'empreinte `Contaminated` des deux côtés.

**Non‑régression rejouée APRÈS rebase** : `test_haze_of_corruption_transfer_live.py` +
`test_haze_of_corruption_rng_live.py` + `test_on_toxic_damage_live.py` → **24 passed** ;
`test_damage_roll_live.py` + `test_psyker_splash_live.py` → **3 passed** ;
`test_on_fire_damage_migration_live.py` + `test_plasma_grenade_splash_live.py` +
`test_runner_attack_live.py` → **5 passed**. Le dégât du report reste **bit‑exact 6/6**.

## 5. Ce qui n'est PAS couvert

* **L'octet `hitInfo+0x94`** (2e conjoint du gate de `On(0x10)`) : non modélisé, faute de vecteur
  connu qui le pose. Il ne peut que RESTREINDRE l'émission — donc un `Maybe` de trop dans un régime
  non identifié reste possible.
* **Le premier transfert de profil Toxic** : aucun montage de ce kit ne le produit (la position 0
  est toujours occupée par le leftover du coup d'arme, fût‑il nul). La branche « le natif tire un
  `Maybe` sur le transfert #0 » est donc portée mais **non confrontée**.
* **La chaîne à 2 relais** (`k = 2`) : le flux RNG n'y a pas été mesuré (il faut que le premier
  relais meure du report).
* **Le résolve sur les autres appelants d'`execute_normal_like`** : le correctif 2.2 est gaté par la
  famille et no‑op sur cellule large, donc l'attaque normale d'arme et l'attaque de summon
  (`spread_pct=20`) ne sont pas touchées — mais aucun montage ne les a exercées en cellule dégénérée.
* **Le régime armure non nulle** : `--hp-target` force l'armure à 0 (hérité de case‑209).
