# #462-r4e-o — le tag `Amount` per-coup est BORNÉ aux PV restants

Trouvé en généralisant #462-r4e (3 boards × 3 seeds) : `astraBullgryn` vs `eldarFarseer`, le port
rendait le dégât **brut** là où le natif écrit le retrait **effectif**. `hp_after` identique des deux
côtés — écart de **RAPPORT**, pas de calcul.

## 1. L'étage qui borne, et sa valeur exacte

Trois maillons, tous lus au décompilé (`rnca9r7q6c`) :

1. `IdunBattle.Core.Services.StreamHelper$$GetDamageTags` écrit le tag `Amount` (`TagKey` **225**)
   depuis le champ **@+0** de la valeur de retour d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`
   — pas depuis le `DamageAppliedResult`.
2. Ce champ est un **accumulateur** (memset à 0 en tête d'`Execute`) alimenté par **exactement deux**
   termes, tous deux des retraits **réellement appliqués** :

   ```
   amount  = FillUpStatComponent.Reduce(healthComponent, dar.healthDamage, ignoreMinimum: false)
   amount += ApplyDamageOperation.ReduceShield(unit, dar.shieldDamage)
   ```

3. `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` **est la borne** :

   ```
   applied = Math.Min(Math.Max(0, damage), Current)                 # Current @+0x18
   if (!ignoreMinimum && Minimum.HasValue)                          # Minimum @+0x1c, Nullable<int>
       applied = Math.Min(Current - Math.Min(Current, Minimum.Value), applied)
   Current -= applied ; <compteur @+0x24> += Math.Max(0, damage - applied) ; return applied
   ```

   Le **surplus** part dans le compteur @+0x24, jamais dans le retour.

**L'armure-pool n'entre pas dans `Amount`** : `IdunBattle.Core.Services.DamageAppliedResult$$.ctor`
reçoit un `armorDamage` et **ne le stocke dans aucun champ** ; `…$$get_Damage` rend `@+0x8 + @+0x4`
= bouclier + santé. Sans effet mesurable ici : aucun call-site de `_run_hits` ne passe `armor_pool`.

**L'application est PAR COUP**, et c'est structurel, pas déduit d'un chiffre : le `DamageAppliedResult`
que reçoit `Execute` porte un `hitIndex` **@+0x14**.

Recoupement indépendant : le **même** accumulateur est gravé dans `ActorStatisticsComponent+0x68`/`+0x6c`
(`last_hit_damage_taken`), ce que `components.py` documentait déjà.

## 2. Port

`damage_amount_applied` (`engine/runner/operations/damage_hits.py`), fonction de **module** — donc
point de mutation des contre-épreuves, comme `crit_gate_open`. `_run_hits` prend `hp_current` /
`hp_floor` (4 call-sites : normal, normal_like, ability, additional_hits) et compose `per_hit` avec
des PV restants **décroissants coup par coup**.

`total`, `per_hit_health` et `rolls` restent le **demandé** — `record_left_over_damages` et le
`didOverkill` per-coup en dépendent, et le natif y met bien le demandé (`dar.healthDamage`).
L'état final était déjà correct (`thc.reduce(total)` bornait) : **rien ne change côté PV**.

## 3. Rayon de souffle de `per_hit`

| lecteur | effet |
|---|---|
| `last_hit = per_hit[-1]` → `_record_last_hit_damage_taken` | **corrigé** — le natif y grave le même accumulateur (TimeFlux de `thousTerminator`) |
| dicts de diagnostic d'abilities (`blacklegion`, `spacewolves`, `behaviours/combat`) | comparés au live par leurs tests — alignés |
| `additional_hits.out["per_hit"]` | concaténation, même sémantique |
| `tools/damage_decomp.py` | outil de mesure, lit les deux côtés |

**Traces RL déjà ingérées : non contaminées.** La colonne `stream_events.amount` est peuplée depuis
`tags->>'Amount'` (`scripts/sql/012_stream_event_attribution.sql`), donc depuis le **live natif** —
déjà borné. Aucune trace ingérée ne porte la valeur brute du port.

## 4. Confrontation live

Probe `probe_462_r4e_o_overkill_amount.py` (4 régimes) + `test_overkill_amount_live.py` (3 tests) :

| régime | `live` | `off` avant | `off` après |
|---|---|---|---|
| `letal` MC1_67/31337 | `[1975, 1573, 2339, 1643]` | `[…, 2404]` (Σ 8291) | **identique** (Σ 7530) |
| `cadavre` C3_01/777 | `[2764, 3787, 979, 0]` | `[…, 2289, 2203]` (Σ 11043) | **identique** (Σ 7530) |
| `survivant` (`--hp-target 999999`) | `[3583, 3181, 3947, 4012]` | identique | identique |

`cadavre` est le régime **discriminant** : le coup 3 est écrêté *partiellement* (979) et le coup 4
tombe sur un cadavre (0) — « borner le coup létal » aurait rendu `2289` / `2203`.
Généralisation : `tauAunShi` (5 coups) bit-exact sur les trois régimes.

**Contre-épreuve** (`--mutate brut`) : `letal` et `cadavre` divergent et **retrouvent exactement**
les valeurs d'avant ; `survivant` reste identique — pas de sur-ajustement.

## 5. `#462-r4e-o-r1` — CARDINALITÉ des events (**PORTÉ**, 2026-08-05)

Quand **au moins deux** coups tombent après la mort (régime `multi_cadavre` : `--hp-target 2000`), le
natif émet le coup létal **puis un seul** event à `Amount` 0, et **rien** ensuite ; le port en émettait
un par coup restant :

```
live=[2000, 0]     off=[2000, 0, 0, 0]        # meme etat, meme somme -> aucun test d'ETAT ne le voyait
```

### 5.1 Le SITE (A) est per-COUP, et le flag est posé UN COUP TROP TÔT pour couper le coup courant

`IdunBattle.Operations.ApplyDamageOperation$$Execute` est appelé **une fois par coup**. Sa tête est le
SITE (A), qui **précède** toute émission (`On(0x39)`, `Reduce`, `On(0xf)`, `lastHitDamageTaken`,
`On(0x10)`, et le `UnitDamaged` porteur du tag `Amount`) :

```
cVar15 = UnitExtensions__HasFlag(target, 8);          // UnitFlag.Overkilled
if (cVar15 != '\0') { RecordHitStatistics ; AddLeftoverHit(.., 1, 0) ; return; }
```

Le flag est posé par **le même** `Execute` (`UnitFlagsComponent$$Add(flags, 8)` sous
`dar.didOverkill && UnitExtensions.CanBeOverkilled(target)`), **après** le calcul et **avant**
l'émission — donc le coup qui pose le flag **émet encore**. D'où `[2000, 0]` et jamais `[2000]`.

### 5.2 La question ouverte : TRANCHÉE, et la piste héritée est RÉFUTÉE

> *« pourquoi le flag n'est posé qu'au coup suivant le létal ? `Execute` efface `dar[+0xf]` sous une
> condition dérivée du compte de membres tués »*

**Il n'y a aucune règle « au coup suivant » : c'est une conséquence ARITHMÉTIQUE.** `didOverkill` est
le retour de la surcharge d'**instance** d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`,
relue verbatim :

```
if (!CanBeOverkilled(target)) return false;
accum = hitDamage + deniedDamage;
currentHealth = UnitExtensions.GetStat(target, Health = 5);
if (targetHealthBeforeAttack.HasValue) {
    accum        += (targetHealthBeforeAttack.Value - currentHealth) + healthComponent@+0x24;
    currentHealth = targetHealthBeforeAttack.Value;
}
return IsOverkill(currentHealth, accum, isCritical, isForceOverkill, HasFlag(target, 0x13), …);
```

Un coup létal qui ne **double** pas les PV rend faux (`accum` = son seul dégât) ; le coup **suivant**
ajoute les PV entiers déjà retirés et franchit le seuil. Le décalage d'un coup **tombe tout seul**.

**La piste `dar[+0xf] = 0` est réfutée** : la variable `local_768` que la fiche précédente lisait
comme « compte de membres tués » est **réutilisée par Ghidra pour deux valeurs sans rapport** dans la
même fonction. L'effacement réel est
`if (local_758._4_4_ == 0) uVar28 = local_7d0 & 0xff; if (uVar28 != 0) dar[+0xf] = 0;` — c.-à-d.
« le dégât santé FINAL est nul **et** un consommateur d'`On(0x39 = PreDamageTaken)` l'a **réduit** »
(`local_7d0` est posé par la comparaison du `PendingDamage` @`HealthComponent+0x64` **avant/après** le
dispatch d'`On(0x39)`). C'est une garde d'**interception de dégât**, pas un compteur de membres, et
elle est inerte dans tous les régimes mesurés.

### 5.3 Le terme qui manquait : `healthComponent@+0x24`

Le premier port du prédicat ne sommait que `hitDamage + (hp_départ − hp_courant)`. **Une mesure l'a
réfuté** — MC1_67/31337 `--hp-target 4000`, rolls `[3583, 3181, 3947, 4012]` :

| | coup 3 | verdict | events |
|---|---|---|---|
| sans `+0x24` | `3947 + 4000 = 7947 < 8000` | flag au coup **4** | `[3583, 417, 0, 0]` |
| natif | — | flag au coup **3** | `[3583, 417, 0]` |
| avec `+0x24` | `3947 + 4000 + (3181−417) = 10711` | flag au coup **3** | `[3583, 417, 0]` |

Le composant que `IsOverkill` va chercher est **le même** que le `HealthComponent` d'`ApplyDamageOperation`
(identique `GetComponent(target, …)`), et `+0x24` est l'accumulateur de **sur-réduction** que
`IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` alimente en queue
(`this[0x24] += Math.Max(0, damage − applied)`), **sauté** quand le plancher `Minimum` est posé et `> 0`.
Le nom vient du natif : `…$$ResetOverReduce` (`this+0x24 = 0`) — qui **n'a aucun xref de code**.

⚠ **En conclure « le compteur n'est jamais remis à zéro » était FAUX** — corrigé en §7 (`#462-r4e-o-r2`).

⚠ **Cela réfute le « RÉSIDU NOMMÉ » d'`unit_is_overkill`** (« hypothèse, non mesurée : accumulateur du
dégât refusé par le plancher de PV ; nul tant qu'aucun plancher n'est actif »). Il est non nul **dès
qu'un coup est écrêté**, et il est load-bearing.

**Identité remarquable** : `(hp_départ − hp_courant)` = dégât **appliqué** des coups précédents,
`+0x24` = dégât **gaspillé** ⇒ leur somme est le dégât **DEMANDÉ cumulé**. C'est exactement ce que
re-joue `AttackDamageOperation._did_overkill` : le port n'a jamais eu deux modèles concurrents. Les
deux formes ne se séparent que sur un `+0x24` **hérité** (revive) et sur un **soin** intercalé.

### 5.4 Port

* `overkill_hit_emits(overkilled)` — le SITE (A), **fonction de module** = point de mutation ;
* `overkill_flag_posted_by_hit(...)` — le prédicat de pose, forme native (les trois termes) ;
* `_run_hits` tient `_overkilled` / `_over_reduce` **par coup** ; `overkilled0` / `can_be_overkilled` /
  `over_reduce0` sont threadés aux **4** call-sites (mêmes patrons que `crit_allowed0`/`failed_block0`) ;
* `per_hit` devient la liste des events **émis** ⇒ **`len(per_hit)` n'est plus le compte de coups** :
  c'est `hits_executed` (seul lecteur corrigé : `additional_hits.py`). `per_hit_health`, `rolls`,
  `crits`, `denied_before`, `total` restent **full-length** et le **demandé** ;
* `HealthComponent.over_reduce` (mirror `+0x24`), alimenté par `HealthComponent.reduce` et **reposé
  exactement** par `_apply_damage_pipeline` quand la décomposition existe ;
* `_did_overkill` consomme le verdict de `_run_hits` quand il existe (**foyer unique**), et garde son
  re-jeu comme repli (DoT, knockback, groupes additionnels).

### 5.5 Mesures

`live == off` **bit-exact sur 5 régimes × 2 attaquants** (`astraBullgryn` 4 coups, `tauAunShi` 5), et
la **position de la coupure varie** (aucun régime ne la fixe) :

| régime | `astraBullgryn` | coupure | `tauAunShi` | coupure |
|---|---|---|---|---|
| `letal` MC1_67/31337 | `[1975, 1573, 2339, 1643]` | — | `[978, 743, 980, 685, 779]` | — |
| `cadavre` C3_01/777 | `[2764, 3787, 979, 0]` | — | `[1411, 1338, 1124, 1468, 1166]` | — |
| `survivant` | `[3583, 3181, 3947, 4012]` | — | `[2436, 1773, 1905, 1984, 2036]` | — |
| `multi_cadavre` (hp 2000) | `[2000, 0]` | après coup **2** | `[2000, 0]` | après coup **2** |
| `cadavre_sans_flag` (hp 4000) | `[3583, 417, 0]` | après coup **3** | `[2436, 1564, 0, 0]` | après coup **4** |

`cadavre` est le **contre-modèle** : la cible meurt au coup 3 et un 4ᵉ tombe sur le cadavre, mais le
cumul n'atteint jamais `2 × PV` ⇒ **aucune** suppression. Un modèle « on coupe dès que la cible est
morte » y rendrait 3 entrées : il est réfuté par la mesure.

**Contre-épreuve** : `probe_462_r4e_o_overkill_amount.py --mutate cardinalite --only multi_cadavre`
(le SITE (A) ouvert) redonne **exactement** `off=[2000, 0, 0, 0]` — le verdict du probe s'inverse et
exige alors la divergence. Le même foyer est muté dans le test **offline**.

## 5bis. `#462-r4e-o-r1-r1` — le coup **DISCARDÉ** (**PORTÉ**, 2026-08-05)

Même vice que §5, **autre porte, autre étage** : un coup jeté par `HarlequinsPanoply` appendait
encore une entrée `per_hit` à 0. Le natif n'en émet **aucune**.

### 5bis.1 La chaîne, lue de bout en bout (`rnca9r7q6c`)

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, après `On(6)`/`On(7)`, relit le
`Nullable<AttackHit>` de `OngoingAttack+0x98` :

```
pcVar18 = <Nullable.HasValue>(attack + 0x98);
if (*pcVar18 != '\0') {                       // HasValue
    Nullable.get_Value(attack + 0x98, &hit);
    if (hit.discard != 0) { return this; }    // `this` = OperationResult MEMSET A 0
    ...
}
```

Ce `return` **précède la sub-op 0x42**, et c'est ce qui tranche :

```
0x42 = IdunBattle.Operations.DealDamageOperation$$Execute
     -> slot 0x43 = IdunBattle.Core.Services.OperationProcessor$$ApplyDamage
     -> IdunBattle.Operations.ApplyDamageOperation$$Execute   (unique appelant de CODE)
     -> event UnitDamaged + tag `Amount` (StreamHelper$$GetDamageTags, TagKey 225)
```

⇒ **pas de 0x42, pas de 0x43, pas d'event.** Le SITE (A) de §5 gate à l'entrée d'`ApplyDamage`
(donc **en aval** de la résolution) ; celui-ci sort **en amont** — le coup ne se résout même pas.

**La face ABILITY a le MÊME gate** (`IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` :
`if (local_448[8] != '\0') { memset(this, 0, 0x30); goto <sortie>; }`, qui saute lui aussi le
dispatch `0x42` **et** `EvaluateAfterHitTriggers`). Le port ne distingue pas les deux familles sur
cette branche : c'est fidèle.

⚠ **Le TRANSFERT (#411) est le contre-modèle** — il relit le MÊME champ au MÊME instant, mais sur
`!HasValue` : le natif **ne sort pas**, pose `damage = 0` et poursuit jusqu'à la 0x42 ⇒ l'event
**existe**, à `Amount` 0. « Supprimer les entrées à 0 » serait donc une règle FAUSSE. La docstring
de `test_411r1_transfer_port_offline.py::test_le_transfert_est_teste_AVANT_le_discard` énonçait
déjà cette distinction (« aucune entrée dans `per_hit` » contre « y laisse un 0 ») sans que le port
l'applique.

### 5bis.2 Port

`discarded_hit_emits()` — fonction de **module** (donc point de mutation, comme `overkill_hit_emits`
et `damage_amount_applied`), lue par `_discarded` dans `_run_hits`. `crits` / `rolls` /
`per_hit_health` restent **full-length** : ils comptent les coups EXÉCUTÉS, et
`hits_executed = len(per_hit_health)` en dépend. Aucune troncature après coup — le refus de §5 tient.

### 5bis.3 Mesures

Montage : **greffe** de `HarlequinsPanoply` (`catalog_inject.write_grafted_seed_bc`) — ses deux
porteurs sont `eldarSmnHarlequin` (summon) et `eldarNpc3Harlequin` (npc), et le seul artefact qui
summone le premier est `EnvFactionSummons:Aeldari`, une ability d'**environnement** : aucun summoner.
`--block-target 100,300` rend le block déterministe au coup 0. **Deux bras** identiques au bit près.

| régime | témoin (sans greffe) | greffé |
|---|---|---|
| `necroDestroyer` 6 coups, MC1_67/31337 | `[212, 146, 325, 291, 201, 320]` | **`[212]`** |
| `tauAunShi` 5 coups, C3_01/777 | `[1111, 824, 866, 1127, 865]` | **`[1111]`** |

`live == off` bit-exact sur les quatre cellules, PV finaux identiques.

**Contre-épreuve** (`--mutate cardinalite-discard`, le foyer ouvert) : `off` redevient
`[212, 0, 0, 0, 0, 0]` / `[1111, 0, 0, 0, 0]` contre `live=[212]` / `[1111]` — **même somme, même
`hp_after`**. C'est exactement pourquoi aucun test d'état ne le voyait.

**Le probe a trouvé un faux négatif de HARNAIS avant de mesurer quoi que ce soit** : sans
`snapshot.bind_live_rpc`, `load_state` n'a aucun transport pour tirer `unitAbilityStates`,
`UnitContext.passive_abilities` reste `None`, la détection retombe sur le kit gameconfig et **la
greffe est invisible au port** (`off` rendait ses 6 coups). Le probe porte désormais une garde de
montage qui vérifie, par le canal MESURÉ, que le bras greffé publie `1187` et que le témoin ne le
publie pas.

### 5bis.4 Gardes

* `tests/engine/test_462_r4e_o_r1_r1_discard_cardinality_offline.py` (8 tests) — cardinalité,
  séparation events/coups, position non-suffixe, contre-modèle transfert, régime mixte,
  non-régression, consommation RNG, et la contre-épreuve du foyer muté. Sous mutation globale :
  **3 rouges** (les 4 verts sont les contrôles, qui n'assertionnent pas la cardinalité de `per_hit`).
* `probe_462_r4e_o_r1_r1_discard_amount.py` — confrontation live, `--mutate cardinalite-discard`.
* ⚠ `test_harlequins_panoply_live.py` assertionnait `all(h == 0 for h in per_hit[1:])`, devenu
  **vacueusement vrai** sur une liste d'une entrée : les cinq assertions concernées sont passées en
  **cardinalité** (`len(per_hit) == 1`, `len(per_hit) == hits`).

## 6. Non couvert, nommé

* le terme `+ ReduceShield` de la formule n'a **pas** été exercé sur une cible à **bouclier non nul**
  (tous les régimes ont `shield = 0`) — la borne santé, elle, l'est ;
* le plancher `Minimum` (HP-floor Hypersensory) n'est **pas** confronté live (aucun régime ne le pose) ;
  il est porté à l'identique du natif et couvert par `HealthComponent.reduce`, déjà en place. Il gate
  **aussi** l'accumulation de `+0x24` (branche `if (0 < minimum) goto …`), porté, non confronté ;
* la borne et la cardinalité sur le chemin **ABILITY** et **coups additionnels** sont câblées (mêmes
  call-sites) mais confrontées seulement en **non-régression**, pas dans un régime overkill dédié ;
* **`targetHealthBeforeAttack` d'un groupe de coups ADDITIONNELS** : le port passe les PV au début du
  **GROUPE**, le natif ceux du début de l'**ATTAQUE** (même approximation que `limits_hp`, pré-existante
  #67/#178). Elle rend le port **moins** enclin à poser le flag sur un groupe additionnel ;
* `total` inclut encore le demandé des coups **supprimés** (le natif n'appelle pas `Reduce` pour eux).
  Inerte sur l'état — la cible est morte, `thc.reduce` borne — et `over_reduce` est reposé exactement ;
* **le `AddLeftoverHit` d'un coup DISCARDÉ sur un cadavre** (`#462-r4e-o-r1-r1-r1`) : `per_hit_health`
  reste full-length et y porte `0`, donc `record_left_over_damages` pousse la **base nominale** pour ce
  coup dès que la cible est déjà morte à l'entrée du groupe — le natif, lui, sort d'`ExecuteHit` avant
  d'atteindre `ApplyDamageOperation`, donc ne pousse **rien**. Inerte tant que la cible est vivante
  (`applied == 0`, aucune branche). Régime **structurellement inatteignable aujourd'hui** : le marqueur
  1227 exige que le porteur BLOQUE (donc vive) et meurt à la clôture de l'attaque qui l'a posé. Nommé,
  **non porté** — un correctif qu'aucune mesure ne peut invalider serait du code mort armé ;
* **la face ABILITY du discard** est lue au décompilé (même gate, même saut de la 0x42) et couverte
  offline, mais **non confrontée live** : aucun montage n'amène une ability multi-coups sur un porteur
  `HarlequinsPanoply` ;
* **`#462-r4e-o-r2` est TRAITÉ en §7** — et il a réfuté sa propre prémisse.

## 7. `#462-r4e-o-r2` — l'accumulateur EST purgé, par une voie que `ResetOverReduce` ne trahit pas

**La prémisse de `-r1` (« `+0x24` n'est JAMAIS remis à zéro ») est FAUSSE.** Elle reposait sur
« `…$$ResetOverReduce` n'a aucun xref de code » — vrai, ce symbole n'est jamais appelé — pour conclure
que rien n'écrit le zéro. **Deux autres méthodes de la même classe l'écrivent EN LIGNE** :

| écrivain de `this[0x24] = 0` | position | appelants (xrefs **exhaustifs**) |
|---|---|---|
| `…FillUpStatComponent$$FillUp` | **queue, inconditionnelle** (même `filled == 0`) | `HealUnitOperation$$Execute`, `RepairUnitOperation$$Execute`, `ResurrectUnitOperation$$SetHealth` |
| `…FillUpStatComponent$$Initialize` | corps | `AddUnitOperation$$Execute`, `UnitFactory$$Build`, `UnitFactory$$InitHealth` |
| `…FillUpStatComponent$$ResetOverReduce` | corps | **aucun** (table de méthodes seule) |

⇒ **SOIN, RÉPARATION et RÉSURRECTION purgent l'accumulateur. Le REVIVE, non.**
`IdunBattle.Operations.ReviveUnitOperation$$SetHealth` n'appelle ni `FillUp` ni `Initialize` : il pose
les PV via un slot de l'`OperationProcessor` qui applique des **modificateurs de stat** (les deux
autres call-sites de ce même slot sont `SetupGameOperation$$ApplyModifiers` et
`TransformActorToConfigIdOperation$$UpdateStats`).

### 7.1 Réponse à la question binaire

* **REVIVE → OUI, quirk natif** : l'unité revient avec l'accumulateur de sa vie précédente et peut poser
  `UnitFlag.Overkilled` **dès son premier coup reçu, à pleine vie**. Le port le reproduisait déjà **par
  omission** ; il est désormais **documenté** dans `revive.py` pour qu'il ne soit pas « corrigé », et
  **gardé** par un test.
* **RESURRECT → NON** : `FillUp` purge. Le port, lui, écrivait `hc.hp = int(hp)` — **divergence**, corrigée.
* **SOIN / RÉPARATION → NON** : `FillUp` purge. Le port sortait avant. **Deux divergences de plus.**

### 7.2 Le régime est structurellement étroit — et c'est ce qui le rend invisible

`Reduce` n'accumule que ce qu'il n'a **pas pu** retirer ⇒ **`over_reduce > 0` implique `hp == 0`**, donc
une unité **morte**. Le seul état où un porteur **vivant** a un accumulateur non nul est
« mort en sur-réduction **puis** retour à la vie ». Corollaire : le correctif sur `HealUnitOperation` /
`RepairUnitOperation` est **inerte sauf après un revive** ; celui sur `ResurrectUnitOperation`, lui, mord
à chaque résurrection (elle opère **toujours** sur un mort).

### 7.3 Port

Foyer unique **`HealthComponent.fill_up`** (mirror 1:1, pendant de `reduce`) — point de mutation des
contre-épreuves. Appelé par `heal.py`, `repair.py`, `resurrect.py` ; **jamais** par `revive.py`.
Deux conséquences du mirror, lues au décompilé :

* le `FillUp` natif précède les early-returns des deux opérations (`heal` : `if (!wasWounded &&
  healed < 1 && …) return;` ; `repair` : `if (filled < 1 && …) return;`) ⇒ le port appelle `fill_up`
  **avant** de décider de sortir ;
* `EffectType.Cursed` n'est **pas** une sortie anticipée native : `healAmount = cursed ? 0 : predicted`,
  puis `FillUp(0)` **quand même** ⇒ un soin annulé par Cursed **purge**. Le port sortait avant.

`resurrect.py` passe d'une écriture **absolue** (`hc.hp = hp`) au `FillUp` **relatif** du natif ; les deux
coïncident puisque l'unité est morte (`Current == 0`).

### 7.4 Mesures

`test_462r4eor2_over_reduce_purge_offline.py` — **16 tests**. Conséquence observable, 4 coups de 200 sur
1000 PV : sans accumulateur `per_hit = [200, 200, 200, 200]` et aucun flag ; avec `over_reduce = 8000`
hérité, **flag au coup 0** et `per_hit = [200]` (le SITE (A) supprime les trois suivants).

**Contre-épreuve DOUBLE** : monkeypatch du foyer (assertions inversées, verte) **et mutation réelle du
code produit** (`self.over_reduce = 0` retiré de `fill_up`) → **6 tests tombent**. La garde mord.

**Non-régression live rejouée : 73 tests verts** — `test_heal_operation_live`, `test_firstaid_heal_live`,
`test_repair_execution_live`, `test_target_is_healable_live`, `test_living_metal_repair_live`,
`test_repair_decision_rail_live`, `test_overkill_amount_live`, `test_overkill_gate_live`,
`test_ambush_migration_live` (le chemin **resurrect**, qui asserte « PV pleins » — c'est lui qui
attraperait le passage absolu → relatif), `test_narthecium_revive_live`,
`test_tainted_narthecium_revive_live`, `test_revive_cancels_death_events_live`.

### 7.5 Non couvert, nommé

* **NON CONFRONTÉ LIVE** — le régime demande un **retour à la vie NATIF suivi d'une attaque NATIVE**, et
  aucun harnais ne le monte : `replay_normal_attack` ne compose qu'**une** attaque, et les trois tests de
  revive/resurrect capturent l'état live puis **simulent** la mort offline. Les deux montages possibles
  sont identifiés : (a) `TaintedNarthecium` (`deathRotbone` + allié Chaos adjacent, revive **75 %**,
  « even if Overkilled ») pour le **quirk** ; (b) le trait **Ambush** (`genesPrimus`/`genesKelermorph`,
  `EnvAmbushResurrectAbility` sur `On(TurnStart)` au tour **suivant**) pour le **resurrect**. Résidu
  **`#462-r4e-o-r2-r1`**.
  ⚠ `ResurrectionOrb` n'est **pas** une voie : son unique nœud natif est un `Spawn` de `necroSmnWarrior`.
* `fill_up` mirrore le `Math.Min` **nu** du natif (pas de `max(0, …)`) : un `hp > hp_max` ferait donc
  **descendre** les PV. Inatteignable à notre connaissance, non mesuré.
* le gate `amount <= 0 -> return 0` de `heal.py` est **conservé** faute d'équivalent natif lisible — le
  natif n'a pas de paramètre scalaire à ce rang, sa gate amont est `AttackQuery$$EntityCanBeHealed`
  (non portée). Il masque la purge d'un soin **de zéro** sur une unité revivée (marginal).
* le port du revive écrit les PV en **absolu** là où le natif passe par des modificateurs de stat
  (slot non identifié nominativement — 3 call-sites, tous poseurs de modificateurs). Approximation
  **pré-existante**, inchangée ici.
