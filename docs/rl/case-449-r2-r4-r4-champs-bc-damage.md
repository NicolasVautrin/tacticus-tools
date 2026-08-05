# `#449-r2-r4-r4` — les autres champs de `BattleConfiguration.Damage`

Build de référence : `rnca9r7q6c`.

La tranche parente `#449-r2-r4` a montré que `DamageSpreadPercentage` était codé en dur à 20 en
13 endroits. **Le vice n'était pas isolé** : la même section porte huit autres champs, et le port
en figeait quatre de plus. C'est mesuré, pas déduit — sur le bras où la BC ne porte **pas**
`ElevationBonus`, le natif inflige **5160** là où le port calculait **8797** (**+70,5 %**).

## 1. La classe native, et son ctor

`IdunBattle.Configuration.DamageConfiguration` — taille **72 = 0x48**
(`data/symbols/rnca9r7q6c/frida/classes.tsv`).

`IdunBattle.Configuration.DamageConfiguration$$.ctor` n'écrit **qu'un** champ :

    *(this + 0x40) = new Dictionary<DamageProfileType, DamageProfile>()

**Aucun autre champ n'a d'initialiseur.** Un champ absent du JSON vaut donc **0** (ou `false`),
jamais le littéral que le port écrivait en repli. La mesure que la tranche parente avait faite sur
un champ vaut pour **toute la section**.

Et le zéro n'est pas un accident : `IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromConfigValue`
rend un `Nullable` **vide** à `configValue == 0` (même forme inline dans `$$CalculateTrenchReduction`).
Le natif **modélise** explicitement ce régime — un repli non nul est donc doublement faux : ni lu,
ni même dans le régime prévu.

## 2. Inventaire des champs — dérivé du natif

Chaque offset est **lu dans le corps de son consommateur**, jamais déduit de l'ordre de
sérialisation. Le layout ferme exactement la taille annoncée (`0x40 + 8 = 0x48 = 72`).

| offset | champ | consommateur natif où l'offset est LU |
|---|---|---|
| `+0x10` | `ElevationBonus` | `IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier` (inliné dans `$$CalculateAttackerModifiersForPrediction`) |
| `+0x14` | `ClassBonus` | **aucun lecteur** — cf. §3 |
| `+0x18` | `AffinityBonus` | **aucun lecteur** — cf. §3 |
| `+0x1c` | `ArmorPercentage` | `IdunBattle.Core.Services.DamageCalculations$$get_ArmorPercentageFix64` (inliné dans `$$CalculateDamageBlockedByArmor`) |
| `+0x20` | `DamageSpreadPercentage` | `IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64` (#449-r2-r4) |
| `+0x24` | `KnockbackPercentage` | `IdunBattle.Core.Services.DamageCalculations$$get_KnockbackPercentageFix64` (inliné dans `$$CalculateKnockbackDamage`) |
| `+0x28` | `RangedInMeleeReductionPercentage` | `IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction` |
| `+0x2c` | `TrenchReductionPercentage` | `IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction` |
| `+0x30` | `AllowOverkill` (bool) | `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` — paramètre **nommé** `allowOverkill` |
| `+0x31` | `IgnoreDamageSpread` (bool) | `IdunBattle.Core.Services.DamagePrediction$$get_IgnoreDamageSpread` (#449-r2-r4) |
| `+0x34` | `OverkillDmgPctOfHealth` | `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` — paramètre **nommé** `overkillDmgPctOfHealth` |
| `+0x38` | `DamagedMachineDestroyChanceIncrease` | `IdunBattle.Core.Services.DamagePrediction$$GetMachineDestroyChance` |
| `+0x40` | `DamageProfiles` | `IdunBattle.Configuration.DamageConfiguration$$GetDamageProfile` |

**Trois confirmations indépendantes du layout**, au-delà des getters :

* `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` existe en trois surcharges. La
  **statique** porte des paramètres nommés — `(targetInitialHealth, healthDamage, isCritical,
  isForceOverkill, isPreventOverkill, allowOverkill, overkillDmgPctOfHealth, targetMinimumHealth)`
  — et les deux surcharges d'instance lui passent `*(byte*)(configuration + 0x30)` et
  `*(uint*)(configuration + 0x34)`. Le **nom** de ces deux champs est donc lu, pas inféré.
* `idun.tests.AbilityAnimationTest$$SetupBattleConfig` **écrit** dans `BattleConfiguration+0xa8`
  (= la section `Damage`) : `+0x10 = 50`, `+0x1c = 50`, `+0x24 = 10`, `+0x28 = -50`, et surtout
  `+0x30` en **un octet** contre `+0x34` en **dword** — la largeur des deux champs d'overkill est
  confirmée par un écrivain, pas seulement par un lecteur.
  ⚠ Ne pas confondre avec le bloc voisin `BattleConfiguration+0xb0`, une autre section que le même
  test remplit ; ses offsets ne sont **pas** ceux de `Damage`.
* `Idun.Source.IdunBattle.View.BattleConfigBuilder$$CreateBattleConfig` alimente les 12 champs
  depuis le DTO gameconfig, ce qui donne la correspondance complète offset ↔ source.

## 3. `ClassBonus` et `AffinityBonus` sont de la CONFIG MORTE (verdict natif)

Balayage exhaustif (les 38 méthodes de `DamageCalculations`, les 47 de `DamagePrediction` — `.ctor`
compris —, les trois sites UI, plus la voie `BattleConfiguration+0xa8`) : **aucune fonction native
ne lit `+0x14` ni `+0x18`**.

Ils sont pourtant **écrits** : `Idun.Source.IdunBattle.View.BattleConfigBuilder$$CreateBattleConfig`
les alimente depuis le DTO (`+0x14 <- DTO+0x15c`, `+0x18 <- DTO+0x160`). Ce sont donc des champs
**alimentés mais jamais consommés** par le moteur.

Faisceau corroborant (pas une preuve) : il existe
`idun.shared.utils.IdunLocalization.Ui$$DamageInfoHud_Detailed_ElevationBonus_Tooltip_Title` mais
**aucun symbole équivalent** pour ClassBonus/AffinityBonus ; et
`idun.ui.tooltips.BattlePreviewUnitInfoTooltip` porte bien des champs `ClassBonusAmount` /
`AffinityBonusAmount`, mais aucune de ses méthodes lues ne les écrit, et la classe ne reçoit jamais
de `DamageConfiguration`.

**⇒ Ne pas porter.** Un port serait du code que rien n'exerce.

*Limite honnête* : la clôture repose sur les quatre porteurs dérivés de `methods.tsv`, élargis à
`BC+0xa8`. Un cinquième détenteur de référence non déclaré resterait hors de portée.

## 4. Inventaire côté PORT — et re-cadrage d'une prémisse

La tâche annonçait « **8 champs non lus du tout** » par le port. **Faux** : le compte re-dérivé est
**3**. Les autres étaient lus, mais **mal** — un vice plus discret que l'absence.

| champ | AVANT | APRÈS |
|---|---|---|
| `ElevationBonus` | seed **figée à l'import**, repli littéral `50` | **BC de la bataille** (foyer) |
| `ClassBonus` | pas lu | pas lu — **dead-config natif**, §3 |
| `AffinityBonus` | pas lu | pas lu — **dead-config natif**, §3 |
| `ArmorPercentage` | `50` en dur dans `predict.py` (**code mort**) | défaut retiré, paramètre obligatoire |
| `DamageSpreadPercentage` | foyer OK, **+ 2 littéraux résiduels** dans `predict.py` | littéraux retirés |
| `KnockbackPercentage` | **`_KNOCKBACK_PCT = 20`** | **BC de la bataille** (constante supprimée) |
| `RangedInMeleeReductionPercentage` | seed figée, repli `-50` | inchangé — **prédiction-only**, §6 |
| `TrenchReductionPercentage` | seed figée, repli `-50` | **BC de la bataille** (foyer) |
| `AllowOverkill` | **`1` en dur**, 4 sites | `_allow_overkill()` → foyer |
| `IgnoreDamageSpread` | foyer (#449-r2-r4) | inchangé |
| `OverkillDmgPctOfHealth` | **`gameconfig.globalValues`** — une autre table | `BC.Damage` (foyer) |
| `DamagedMachineDestroyChanceIncrease` | pas lu | pas lu — **mécanisme entier non porté**, §6 |

Les deux porteurs nommés par la tâche sont **confirmés** : `_KNOCKBACK_PCT = 20` et
`armor_percentage = 50` étaient bien des littéraux.

### 4.1 `predict.py::CombatConstants` est du CODE MORT (`#449-r2-r4-r5`)

`git grep CombatConstants` sur tout le dépôt : la classe n'apparaît que dans sa propre définition.
**`from_bc` n'a aucun appelant.** Un défaut que rien n'exerce est un littéral que **rien ne peut
invalider** — le brancher sur le foyer reviendrait à câbler un canal que personne n'emprunte.

Traitement retenu, identique à celui de `HitDamage.from_base` dans la tranche parente : **défauts
retirés, paramètres rendus obligatoires**, et `from_bc` rend `0` sur champ absent (comme le natif).
Cela ferme le résidu `#449-r2-r4-r5`.

## 5. Le correctif — un seul foyer, pas un second

`engine/services/damage_config.py` devient le foyer de **toute** la section :

* **`DAMAGE_FIELDS`** — table `nom_port -> (clé BC, offset natif, symbole du consommateur)`. C'est
  elle qui porte la RE, et elle est **dérivée** : `snapshot.load_state` boucle dessus, donc un champ
  qui entre dans la table est transporté sans qu'on ait à y penser.
* **`default_damage_field(name)`** — défaut **dérivé** de `data/seed-bc.json`, jamais écrit ; **lève**
  si la seed est illisible ou si la clé manque (même discipline que la tranche parente).
* **`resolve_damage_field(name, value=None, state=None)`** — généralisation exacte de
  `resolve_spread_pct` : explicite > BC de cette bataille (`State`) > défaut dérivé.

Consommateurs câblés : `apply_elevation_bonus`, `apply_trench_reduction`
(`engine/runner/damage_model.py`), `_apply_knockback_to` (`engine/runner/operations/displace.py`,
constante `_KNOCKBACK_PCT` **supprimée**), `_allow_overkill` / `_overkill_threshold_pct`
(`engine/services/trait_damage_limits.py`, 4 sites).

## 6. Ce qui n'est PAS porté, et pourquoi

* **`RangedInMeleeReductionPercentage`** — **prédiction-only** (le trait `0xb` n'est jamais assigné,
  #161). Le consommateur porté est `engine/playbook/prediction/_shared.py`, qui n'a pas de `State` :
  le câbler demanderait de faire descendre la BC dans la couche prédiction. **Non fait**, résidu.
* **`ArmorPercentage`** — la branche consommatrice (`calculate_damage_blocked_by_armor`, pool
  d'armure déplétable) **n'est pas exercée** : toutes les cibles live ont `RemainingArmor == 0`. Son
  défaut `0` coïncide d'ailleurs avec le natif à champ absent. Non confrontable, résidu.
* **`DamagedMachineDestroyChanceIncrease`** — le mécanisme entier est **absent du port**. Le natif
  le lit sur un vrai chemin d'exécution (`IdunBattle.Entities.Behaviours.MachineDamageBehaviour$$Execute`
  → `IdunBattle.Operations.MachineDamageOperation$$ExecuteHit` → slot 0x13
  `$$GetMachineDestroyChance`, puis slot 9 `$$ResolveMachineHit` qui tire au PRNG si
  `destroyChance < 100`). Porter le champ seul, sans son consommateur, serait spéculatif.
* **`OverkillDmgPctOfHealth`** — la correction de source (`gameconfig` → `BC.Damage`) **n'est pas
  mesurable** : les deux tables valent 100. C'est un **accord en régime dégénéré**, justifié par le
  décompilé, pas par un écart observé.

## 7. La mesure

`probe_449r2r4r4_bc_damage_fields.py` — trois bras qui ne diffèrent **que** par la section
`BC.Damage` d'une copie de `data/seed-bc.json`, passée au runner par `--seed-bc`. Attaquant RANGED
`necroDestroyer` piloté en **surplomb** (MC1_67, `(0,3)` élévation 4 → `(0,5)` élévation 2, distance
hex 2, tuiles choisies en LISANT le board — pas subies). Face COMBAT par replay-diff, PRNG calé sur
le MT live (`dumpRng`).

| bras | `BC.ElevationBonus` | natif | port AVANT | écart | port APRÈS |
|---|---|---|---|---|---|
| `seed` | 50 | 8797 | 8797 | 0 | **8797** |
| `v100` | 100 | 10520 | 8797 | **−1723 (−16,4 %)** | **10520** |
| `absent` | *(retiré)* | 5160 | 8797 | **+3637 (+70,5 %)** | **5160** |

Le natif suit exactement le champ — centres de `aiPredict` : 5436 → ×1,5 → ×2,0. Après correctif :
**bit-exact sur les trois bras**.

⚠ **Le premier run de ce probe a accusé le bon coupable pour la mauvaise raison.** Sans
`load_state(board=...)`, les feuilles positionnelles du port sont des **no-op silencieux** : le port
rendait 5160 sur les trois bras, ce qui se lisait « le port ignore le champ » alors que le probe
mesurait son propre montage. Même correctif que #63 dans `_combat_replay.py`. Le probe **refuse**
désormais de mesurer si `boardGraph` est indisponible.

## 8. Résidus

* **`#449-r2-r4-r4-r1`** — la garde `probe_449r2_spread_inventory.py` couvre désormais
  `elevation_pct` et `trench_reduction_pct` (attestés `REQUIS`), mais **pas** `allow_overkill`,
  `overkill_dmg_pct_of_health`, `armor_pct` ni `ranged_in_melee_reduction_pct`. Ce n'est pas un
  oubli : la sémantique du probe est celle de la *variance*, et ne leur transpose pas — un gate
  booléen **inversé** (`if not allow_overkill`) est déclaré « paramètre MORT » alors qu'il est bien
  lu, et aucun des trois régimes (`0` / `LU_BC` / `REQUIS`) ne décrit un *seuil de comparaison*. Les
  y faire entrer demande d'élargir les **régimes** du détecteur, pas seulement sa liste de noms.
  Mesuré : les inscrire tels quels rend **15 désaccords**, dont plusieurs sont des artefacts.
  ⚠ L'extension a aussi révélé un gisement **hors périmètre de cette tranche** : `armor_pct=0` est
  passé sans attestation par 5 call-sites.
* **`RangedInMeleeReductionPercentage`** dans la couche prédiction (§6) — la BC n'y descend pas.
* **`DamagedMachineDestroyChanceIncrease`** (§6) — porter d'abord `MachineDamageOperation`.
* L'auto-test du probe tourne désormais sur un périmètre restreint (`_SELF_TEST_PARAMS`) : ses
  arbres synthétiques ne portent qu'un rail, et le garde « périmètre AVEUGLE » les rendait rouges
  alors qu'ils sont conformes. Le verdict sur l'arbre **réel** garde tous les rails.
