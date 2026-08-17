# case-512r4/489r2 — la CARDINALITE d'`On(Attack = 9)`, et la loi de `GetLeftOverHits` : une premisse tombee, une loi qui resiste

Tranche du 2026-08-18, build `t6dpr4k06g`. Items : `#512-r4`, `#489-r2`.
Foyers edites : `runner/operations/triggers/dispatch/attack.py`,
`runner/abilities/behaviours/combat.py`, `runner/operations/damage_ops/ability.py`,
`runner/operations/damage_ops/normal_like.py`,
`runner/operations/triggers/loki/haze_of_corruption.py`, plus un cliquet neuf
(`tests/engine/runner/test_512r4_on9_cardinalite_offline.py`) et une fixture neuve
(`scripts/python/probe_489r2_leftover_law.py`).

**Verdicts** : `#512-r4` **PORTE ET CONFRONTE** ; `#489-r2` **PREMISSE REFUTEE, LOI NON CLOSE**.

---

## 1. `#512-r4` — RESOLU. `On(9)` sort d'un NOEUD, jamais d'une operation de degat

### 1.1 Ce que le decompile dit

`On(Attack = 9)` est la 1re publication d'`IdunBattle.Operations.FinishAttackOperation$$Execute`
(`FUN_1800280e0(0x50, .., 9, entities)`), la 2e etant `On(10)` sous `if (currentAttack@+0x2c != 0)`.
Cette operation n'est atteinte que par le **slot 59** (`FinishAttack`) du processeur, et ce slot est
pousse par des **NOEUDS de l'arbre DSL** — cinq emetteurs, relus au build courant :

| emetteur natif | granularite |
|---|---|
| `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` | `if (next == null || next != cur)` — une fois par cible **distincte** (la liste est `OrderBy`-ee des que `Count > 1`, donc les repetitions sont groupees), symetrique du `StartAttack` sous `if (prev == null || prev != cur)` |
| `IdunBattle.Entities.Behaviours.SortedAttackSeriesBehaviour$$Execute` | a chaque changement de cle du `Dictionary<UnitEntity, List<behaviour>>`, plus une fois a la sortie — donc une par cible distincte **meme si cette cible porte DEUX behaviours** |
| `IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute` | autour de **chaque maillon** |
| `IdunBattle.Entities.Behaviours.FinishAttackBehaviour$$Execute` | une fois |
| la voie MESSAGE | une fois |

**Aucune operation de degat ne pousse ce slot.** Le port, lui, emettait `On(9)` depuis
`after_hit_ability_attack`, appelee par `execute_ability_attack` / `execute_normal_like` — donc
**par FEUILLE**.

### 1.2 Les trois porteurs de l'ecart, tous reels

* **`1088 HellfyreMissileRack`** — `HellfyreMissileRackAbility$$ExecuteBehaviour` monte DEUX
  `AbilityDamage` sur `ActiveTarget()` dans un `SortedAttackSeries`. Des que la cible du message a
  deja pris du Psychic ce tour (le « which can include the initial target again » de l'i2), elle
  est dans les DEUX selecteurs : le port emettait **deux** `On(9)`, le natif **un**.
* **le FOLD de l'attaque normale** (`abilities/loki/additional_targets.py::primary_fold_tree`) —
  feuille NUE composee dans le `Attack(...)` de la primaire. Le port emettait un `On(9)` **en plus**
  de celui que `damage_ops/normal.py` emet deja a la sortie de l'operation. Contraste avec le
  CLEAVE, qui enveloppe SA feuille dans son propre `Attack(...)` et doit donc emettre.
* **`HazeOfCorruption`** — `$$CreateTargetTriggerBehaviour` accumule N feuilles `AttackDamage` par
  `op_Addition` dans **UN SEUL** `Attack(bonded, Owner@0x148, beh)`. Le port emettait **N** `On(9)`.

### 1.3 Le correctif — SEPARER, pas gater en bloc

`after_hit_ability_attack` emet **trois** evenements qui n'ont pas la meme granularite native :

* `On(0x3c = UnitBlocked)` et `On(8 = AttackHit)` viennent d'`IdunBattle.Operations.
  ADamageOperation$$EvaluateAfterHitTriggers`, appelee **par COUP** par les deux `ExecuteHit` — ils
  suivent l'OPERATION ;
* `On(9)`, non.

D'ou le parametre `emit_finish_attack`, threade depuis `is_outside_attack` par les deux facades.
C'est **exactement le gate que `#512-r2` avait pose pour `On(PreAttack = 5)`** et qui manquait a la
cloture ; gater la fonction entiere aurait eteint le cluster on-block avec elle.

Foyer de NOEUD : `combat.py::_emettre_finish_attack_de_noeud`, appele par `SortedAttackSeries` (par
cible distincte, a la fin des behaviours de cette cible — donc dans l'ordre natif `Finish(T)` puis
`Start(T+1)`) et par `HazeOfCorruption` (une fois, pendant exact de son `On(5)` unique). Le payload
est **agrege sur les feuilles de la cible**, parce que `FinishAttackOperation$$Execute` commence par
`GetCurrentAttack()` et lit l'etat ACCUMULE de l'attaque (`+0x20`, `+0x24`, `+0x2c`, `+0x38`,
`+0x3c`, `+0x50`, `+0x58`, `+0x60`), pas celui d'une feuille.

`ChainLeftOverHitsAttackDamage` garde le defaut `is_outside_attack = True` : son homologue natif
pousse bien 0x3a/0x3b autour de **chaque** maillon, donc un `On(9)` par maillon — le port etait deja
juste la.

### 1.4 Ce qui l'etablit

* **Cliquet NEUF, vu ROUGE par MUTATION avant le fix** —
  `tests/engine/runner/test_512r4_on9_cardinalite_offline.py`. En neutralisant l'emission de noeud :
  `AssertionError: [5, 5] / assert 0 == 2`, **3 failed / 1 passed**. Source restauree : 4 passed.
  Le fichier porte son **CONTRE-CAS integre** (des feuilles qui cloturent elles-memes, c'est-a-dire
  le port d'avant, rendent un compte DIFFERENT) — sans quoi la mesure ne serait pas discriminante.
* **Confrontation LIVE du porteur nomme** — `probe_487_hellfyre_missile_rack.py`, **RC = 0**, dans
  le regime meme du residu : « etage 3ter (doublement conditionnel) : cible u81 EST armee -> 2 coups
  attendus, LIVE 2 », per-coup **bit-exact** offline/live
  (`[(81, 2792), (81, 2792), (83, 3989), (85, 2792)]`).
* **Rayon de souffle rejoue** (voir §4).

### 1.5 Ce qui reste — `#512-r6`

`On(AttackDamageAttack = 10)` sort du **MEME** `FinishAttackOperation$$Execute`, et il n'a PAS suivi.
Deux consequences, mesurees et laissees en l'etat :

* **cardinalite** : sur un noeud a deux feuilles sur la meme cible, `On(10)` part encore deux fois ;
* **ordre** : sur la voie NOEUD, `On(9)` est desormais emis **apres** `On(10)` (le noeud clot apres
  que ses feuilles ont rendu la main) alors que le natif emet 9 puis 10. Avant cette tranche il
  etait emis **avant** `On(0x42 = FinalDamage)`, donc trop tot ; il est maintenant trop tard.

Pourquoi pas maintenant : deplacer `On(10)` au noeud **n'est pas symetrique**. La voie
`execute_normal_like` (les N transferts d'`HazeOfCorruption`) n'emet AUCUN `On(10)` aujourd'hui alors
que ses feuilles sont de la famille ATTACK — l'y ajouter serait un **port NEUF**, avec un
consommateur non idempotent (`LegendaryCommander_ExtraHits`, dont le gate `IsValidAttack` lit
`!IsNormalAttack`), pas une correction de granularite.

---

## 2. `#489-r2` — PREMISSE REFUTEE. La loi ne se lit pas sur l'index d'OVERKILL

### 2.1 La refutation

La fiche posait : « le gate du call-site (a) d'`AddLeftoverHit` — le SEUL des trois a pousser un flag
LITTERAL `1` — est `HasFlag(target, UnitFlag.Overkilled)`, donc le compte se lit sur l'index
d'OVERKILL `o`, et il manque UN point pour separer `H - o` de `H - o + 1` ».

Le premier membre est vrai, le second ne s'en deduit pas. Relus au build courant, les **trois**
call-sites d'`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` :

| site | gate | flag pousse |
|---|---|---|
| (a) | `UnitExtensions.HasFlag(target, UnitFlag.Overkilled = 8)`, en TETE — puis `return` (aucun event, aucune mutation) | litteral **1** |
| (b) | `0 < DamageAppliedResult.get_Damage(result)` **et** `HealthComponent$$IsDead` AVANT la mutation | l'`IsDead` d'avant — donc **VRAI** |
| (c) | `0 < <reduction REELLEMENT appliquee>` (retour de `FillUpStatComponent$$Reduce`) **et** `IsDead` APRES la mutation | l'`IsDead` d'avant — donc **FAUX** sur le coup qui tue |

Tout coup posterieur au coup fatal produit donc **une** entree flag-vraie : par (a) si le flag
`Overkilled` est deja pose, par (b) sinon. **Les deux voies sont interchangeables pour le compte**, et
`o` ne decide que de LAQUELLE.

**Mesure qui le montre sans detour** : sur `1129 BloodyFury` a PV 9000 et 12000, `o == H` — donc
**zero** coup gate par le site (a) — et le report ne vaut pas 0 pour autant. `H - o` et `H - o + 1`
meurent ensemble : il n'y avait pas un point de mesure a ajouter, il y avait un etage a relire.

### 2.2 Et le montage prescrit etait une TAUTOLOGIE

La fiche proposait « ajouter la lecture de `overkill_at_hit` du 1er maillon » — une valeur que le
**PORT** calcule (`damage_hits.overkill_flag_posted_by_hit`). Confronter la loi du port a l'index du
port est la meme tautologie que le VERDICT-4 de `probe_489_fragstorm_grenade_launcher.py`, que
`#489-r1` reprochait deja.

**Le canal NATIF existe et ne demande aucun capteur neuf** :

* `o` = le **nombre d'events de degat** d'un maillon MOURANT (le site (a) sort avant toute emission,
  donc les coups `o+1..H` n'emettent rien) ;
* `k` = l'index du **dernier event a `Amount != 0`** (au-dela, `Reduce` ne retire plus rien) ;
* `H` = le nombre d'events d'un maillon dont la cible **SURVIT** (bras TEMOIN) ;
* `report` = le nombre d'events du maillon **suivant** quand il survit et n'a aucun malus de coups.

`k` et `o` sortent du **MEME bras et du MEME tick** — deux comptages pris a deux instants fabriquent
un ecart qui n'existe pas.

Fixture : `probe_489r2_leftover_law.py`, trois regimes — `bf` (1129), `mte` (1006) et `chain3` (le
montage de `test_chain_leftover_hits_live.py` **avec le bras TEMOIN qu'il n'a pas**).

### 2.3 Ce qui est mesure, et pourquoi ca ne se referme pas

**Dix points natifs, deux porteurs.** `1129` passe `extraHitsAfterTargetKilled` = **null** — LU
VERBATIM : le 9e argument de `DSLBehaviors$$ChainLeftOverHitsAttackDamage` dans
`BloodyFuryAbility$$ExecuteBehaviour` est `(void *)0x0` — donc son report EST le compte d'entrees.
`1006` passe `DSLFormulas$$Get(GetNumberConstant(0x2b) = extraHit = 1)`, non nul.

| porteur | extra | H demande | H applique | k | o | report LIVE | ce port rend |
|---|---|---|---|---|---|---|---|
| 1129 (PV 1800) | 0 | 4 | 4 | 1 | 1 | **3** | 2 |
| 1129 (PV 5200) | 0 | 4 | 4 | 1 | 1 | **3** | 2 |
| 1129 (PV 9000) | 0 | 4 | 4 | 2 | 4 | **2** | 1 |
| 1129 (PV 12000) | 0 | 4 | 4 | 2 | 4 | **2** | 1 |
| 1006 (PV 1500, `H_app` 5) | 1 | 6 | 5 | 1 | 2 | **5** | 4 |
| 1006 (PV 3000, `H_app` 5) | 1 | 6 | 5 | 2 | 4 | **4** | 3 |
| 1006 (PV 5000, `H_app` 5) | 1 | 6 | 5 | 3 | 5 | **3** | 2 |
| 1006 (PV 1500, `H_app` 6) | 1 | 6 | 6 | 1 | 2 | **5** | 5 |
| 1006 (PV 3000, `H_app` 6) | 1 | 6 | 6 | 2 | 4 | **4** | 4 |
| 1006 (PV 5000, `H_app` 6) | 1 | 6 | 6 | 3 | 5 | **3** | 3 |

**Le port rend un coup de trop peu des que `extraHits = 0` ou qu'un malus de coups s'applique.** La
forme portee `max(0, H_applique - k - 1) + extraHits` coincide avec `max(0, H_demande - k)`
exactement quand `extraHits == 1` ET qu'aucun malus n'intervient — c'est-a-dire dans **tout** le
regime que `test_chain_leftover_hits_live.py` et `test_523_heavy_warp_flamer_live.py` exercent. Elle
etait donc verte pour une raison qui ne se generalise pas.

**LE VERROU.** Aucune forme unique ne passe les trois porteurs :

* `max(0, H_demande - k)` explique les dix points ci-dessus… et **casse `1227 HeavyWarpFlamer`**
  (`test_523_heavy_warp_flamer_live.py`, dont le relais SURVIT donc son compte d'events EST le
  report) : rejoue, 3 rouges sur 11 ;
* `max(0, H_applique - k) + extra` explique `1129` et le regime `H_app = 5` de `1006`, et casse les
  deux autres ;
* la forme portee explique `1227`, `1006` sans malus et `chain3`, et casse `1129`.

**La grandeur qui separe toutes les paires est la meme** : le rapport entre coups **DEMANDES** et
coups **APPLIQUES**, c'est-a-dire le modele de malus de coups. Il a ete confronte au natif **6 fois**
(cible immortelle, 6 coups demandes, on compte les events) et il est juste **6/6** :

| unite | tuile cible | tuile caster | demande | events natifs | port `applied_hits` |
|---|---|---|---|---|---|
| astraBullgryn | (3,3) | (3,4) | 6 | 6 | 6 |
| astraBullgryn | (3,2) | (3,4) | 6 | 6 | 6 |
| astraBullgryn | (3,2) | (3,3) | 6 | 6 | 6 |
| eldarRanger | (3,3) | (3,4) | 6 | 6 | 6 |
| eldarRanger | (3,2) | (3,4) | 6 | **4** | 4 |
| necroWarden | (3,3) | (3,4) | 6 | **5** | 5 |
| necroWarden | (3,2) | (3,4) | 6 | **4** | 4 |

Ce qui n'a **pas** ete confronte, c'est le malus **avec une unite INTERPOSEE** entre le caster et la
cible — la configuration de tout maillon `>= 2`. Elle n'est pas atteignable par tir direct :
`abilityTargets.fromHere` refuse la tuile lointaine des qu'une unite s'interpose (mesure :
`legal=[81]` avec u79 en (3,2) et u81 en (3,3), le caster en (3,4)). **C'est le prochain montage a
inventer** — une interposition NON COLINEAIRE, ou une lecture native des entrees
d'`AttackHitsWithModifiersFormula`.

**Decision** : la loi **n'est pas remplacee**. Quatre points natifs la contredisent sur un porteur,
mais aucune forme ne passe les trois, et livrer celle qui passe `1129` rendrait `master` rouge sur
`1227`. Le residu `#489-r2` est **re-enonce**, pas ferme.

### 2.4 Sous-residu `#512-r5` — `DSLFormulas$$Get` n'est pas `$$Direct`

Le port lit le 9e argument de `1006` comme `extra = 1` (la valeur de `GetNumberConstant(0x2b)`).
Or `IdunBattleLogic.Entities.DSLFormulas$$Get(int)` et `$$Direct(int)` **allouent deux CLASSES de
formule differentes** (`thunk_FUN_180222ae0(DAT_183396708)` contre celle de `$$Direct`), et la
distinction n'a jamais ete lue. Si `Get(1)` ne rend pas `1`, une partie de la table ci-dessus se
reinterprete. Foyer : `engine/runner/abilities/necrons.py`, `.../worldeaters.py`.

---

## 3. Ce que la validation a coute, et ce qu'elle a sauve

La loi `max(0, H - k)` **a ete ecrite, commitee, puis retiree** — la meme sequence que #489-r1 avait
deja vecue, mais pour une raison differente : cette fois elle etait soutenue par **sept** points
natifs et non par une lecture. Ce sont les deux fichiers live qui l'ont tuee, et il a fallu, pour
savoir lequel accusait quoi, mesurer `H` **maillon par maillon** dans le montage du test — ce que le
test lui-meme ne fait pas.

Corollaire, et c'est le vrai enseignement de la tranche : **un bilan vert sur une chaine ne dit rien
de chaque maillon.** `test_chain_leftover_hits_live.py` ne confronte que le per-coup du maillon
SURVIVANT ; les deux premiers maillons sont tronques par le site (A), donc leur `H` n'est jamais
observe. Un tel montage est vert sous une loi fausse des qu'une seconde erreur la compense. Le bras
TEMOIN (`--regime chain3`) est ce qui retire la compensation du modele.

---

## 4. Rayon de souffle rejoue (`#512-r4`)

| fichiers | verdict |
|---|---|
| `test_512r4_on9_cardinalite_offline.py` (neuf) | 4 passed ; **3 failed** sous mutation |
| `test_489r1_foyer_combat_offline.py` | 21 passed (etage 5 change d'invariant, cf. §1.3) |
| `test_487_hellfyre_missile_rack_live.py` | 4 passed |
| `probe_487_hellfyre_missile_rack.py` | **RC = 0**, regime « cible dans les DEUX volets » |
| `test_haze_of_corruption_transfer_live.py` + `test_haze_bonded_chain_live.py` | 27 passed |
| `test_925_fold_pre_attack_live.py` + `test_925r1_ltgb_attribution_live.py` | 27 passed |
| `test_437_overwatch_consumes_armour_live.py` + `test_432_terminator_armour_cycle_live.py` | 8 passed |
| `test_441_neuroparasite_pair_term_live.py` + `test_overwatch_single_shot_per_activation.py` | 15 passed |
| `test_523r1_heavy_warp_flamer_tracking_live.py` + `test_shock_assault_buff_live.py` | 15 passed |
| `test_925_boltstorm_faces_offline.py` + `test_944_combat_behaviours_offline.py` + `test_1001_votann_relics_offline.py` + `test_523r1_..._offline.py` | 55 passed |
| `test_chain_leftover_hits_live.py` + `test_523_heavy_warp_flamer_live.py` | 13 passed |
| `test_1077_firing_position_mischief_makers_offline.py` | passed |

**ROUGES PRE-EXISTANTS, verifies sur l'arbre d'AVANT le fix (`git checkout <sha> -- scripts/python/engine`)** —
ils ne sont **pas** imputables a cette tranche et ne sont **pas** repares ici :

* `test_frag_bomb_live.py::test_frag_bomb_crowded_live` et `::test_frag_bomb_alone_live`
  (`At index 0 diff: (44, 1432) != (77, 1432)`) ;
* `test_act_of_faith_crit_resets_both_paths_live.py::test_normal_and_ability_crit_both_reset`
  (`aof_reset=False` sur la branche NORMALE).

## 5. Ce qui n'est PAS couvert

* Aucun scenario live n'a ete craft ou un **consommateur** d'`On(9)` rende la cardinalite
  OBSERVABLE (armure Terminator consommee une fois au lieu de deux, decoy spawne une fois au lieu de
  deux). Sur tous les montages joues, soit les feuilles portent sur des cibles distinctes, soit
  aucun consommateur d'`On(9)` n'est present — le port et le natif s'accordent donc trivialement.
  La confrontation de `#512-r4` est **structurelle** (decompile) + **offline sous mutation**, plus
  la non-regression live du porteur nomme.
* `On(10)` : cardinalite et ordre, cf. `#512-r6`.
* La branche « cible DEJA morte a l'entree » de `_left_over_hits` reste **modelisee, non
  confrontee**.
