# case-344 — la prédiction d'ability moyenne par DEUX chaînes natives, pas une

Résidus `#339-r1/r2/r3` : cinq sites moyennent `min`/`max` à la main. La tâche demandait de mettre
chacun sur la bonne des deux primitives déjà portées. La validation adversariale a montré que la
question était mal posée pour le premier : **son artefact dépend du playbook appelant**.

---

## 1. Le fait

`<X>Playbook$$MakeDamagePredictions` passe en 6ᵉ argument de
`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` **l'une de deux formes**, portées chacune
par **un corps dédupliqué** (donc un seul nom ghidra pour tous ses propriétaires) :

| forme | corps (nom ghidra du corps partagé) | chaîne | arrondi |
|---|---|---|---|
| (a) `<X>Ability$$GetDamageAmountMain` | `StranglethornCannonAbility$$GetDamageAmountMain` | → `AActiveAbility$$MinMaxDamageAverage` = `Half(Sum(Direct(minDmg), Direct(maxDmg)), 0)` → `DivideAmount$$Calculate` → `AAmountFormula$$RoundFix64Result(., 0)` | demi-vers-le-**PAIR** |
| (b) `<X>Ability$$GetDamage` | `VigilanceEternalAbility$$GetDamage` | → `AActiveAbility$$MinMaxDamage(state, isPrediction: **FALSE**)` = `RandomAmount(min, max)`, pris au slot 4 = `AAmountFormula$$CalculateAverage` | **TRONCATURE** |

`AActiveAbility$$MinMaxDamage` porte les deux : `isPrediction != 0` construit le `Half(Sum(...))`,
`== 0` construit le `RandomAmount`. Le nom « isPrediction » est trompeur — la face PRÉDICTION
emprunte les DEUX, selon le playbook.

**Xrefs des deux corps : 18 abilities de chaque côté** (build `rnca9r7q6c`). Elles divergent
exactement quand `minDmg + maxDmg` vaut **3 mod 4**, d'exactement 1.

## 2. La mesure LIVE — deux familles, deux réponses OPPOSÉES

`probe_344_ability_damage_average.py`. Deux leviers de pilotage : `--unit-stat
'<vis>:ActiveAbilityLevel=<L>'` choisit `(minDmg, maxDmg)` donc la classe mod 4 ;
`--armor-target 0` empêche la réduction d'armure d'ABSORBER l'écart d'une unité.

Oracle `aiPlaybookPredict`, event de la cible principale, bornes `(healthDmgMin, healthDmgMax, hits)` :

| montage | famille | bras A (`3 mod 4`) natif | `to_even` | `trunc` | bras B (`1 mod 4`) natif | `half_up`/`ceil` |
|---|---|---|---|---|---|---|
| `deathBlightlord` FlailSwing 1042, lvl 2/5, MC1_67 | (a) | `(54, 84, 3)` | **=** | `(54, 81, 3)` ✗ | `(84, 123, 3)` | `(84, 126, 3)` ✗ |
| `darkaTerminator` PlasmaCannon 1150, lvl 3/2, C1_03 | (b) | `(36, 57, 3)` | `(39, 57, 3)` ✗ | **=** | `(33, 45, 3)` | `(33, 48, 3)` ✗ |
| `blackTerminator` BringerOfDespair 1022, lvl 3/2, MC1_67, armure 0 | (a) | `(108, 164, 4)` | **=** | `(104, 160, 4)` ✗ | `(88, 136, 4)` | `(92, 140, 4)` ✗ |
| `emperKakophonist` DoomSiren 1199, lvl 2/3, C1_03, armure 0 | (b) | `(45, 69, 3)` | `(48, 72, 3)` ✗ | **=** | `(54, 78, 3)` | `(54, 84, 3)` ✗ |

⇒ **la variante nulle sur les DEUX bras est `to_even` pour (a) et `trunc` pour (b)**. Un port à
moyenne unique est faux dans l'une des deux moitiés. Le code LIVRÉ (sans patch) égale le natif sur
les 8 bras.

> **Piège de bras muet**, ré-observé : `BringerOfDespair` niveau 2 sur cible blindée rend `(36,56)`
> pour les QUATRE variantes — la réduction d'armure absorbe l'unité. Le probe déclare ce bras NON
> DISCRIMINANT et **échoue** au lieu de verdir. C'est le même piège que le `Ceiling` de #339 §4.

## 3. Verdict des cinq sites

| site | artefact lu | verdict |
|---|---|---|
| `entities/abilities/active_ability.py::get_damage` | (a) OU (b), selon le playbook | **BUG, corrigé** : registre `_PREDICTION_MINMAX_AVERAGE` (18 ids) ; défaut = (b) = troncature = statu quo |
| `runner/abilities/votann.py::_ancestral_fortune_attack_target` | `AncestralFortuneAbility$$GetAttackTarget` passe `MinMaxDamage(isPrediction: **true**)` = `Half(Sum(...), 0)` ; `SortUnitsByDamageUtilitySelector$$Select` l'évalue au **slot 1** (`Calculate`) → `DivideAmount$$Calculate` | **BUG, corrigé** → `_round_fix64(Fraction(mn+mx, 2), 0)` |
| `runner/abilities/darkangels.py::_exemplar_of_hate_attackers` | `SortAttackersByDamagePredictionSelector.<Select>b__0` finit par `MinMaxDamage$$Avg` | **BUG, corrigé** → `min_max_avg` |
| `runner/operations/damage_hits.py::HitDamage.get_damage` | `IdunBattle.Core.HitDamage$$GetDamage` : `(iVar1 + *(int*)this) / 2`, division entière C, **aucun Fix64** | **la troncature est JUSTE** — rien à changer |
| `entities/unit_context.py::normal_base` | aucun symbole cité, **zéro consommateur** (grep exhaustif, accès dynamiques inclus) | **DEAD CODE** — retirée |

Le piège annoncé a tenu : `playbook/fury_of_the_ancients.py:103` **n'a pas été touché** (son `// 2`
passe par `AAmountFormula$$CalculateAverage`, cf. `case-339` §2) — une garde le verrouille.

## 4. L'écart RENVERSE un argmax — démontré, pas supposé

`_exemplar_of_hate_attackers` trie par `OrderByDescending(MinMaxDamage$$Avg(bornes))`, tie-break sur
l'id croissant. Deux attaquants, l'un dans le régime `3 mod 4` (bornes `29/38`, floor 33) et l'autre
à clé 34 : la troncature ordonne `[9, 1]`, le demi-vers-le-pair égalise les clés à 34 et le
tie-break rend `[1, 9]`. **L'ordre des attaquants change.** (Garde offline, sans état à monter.)

Sur la face PRÉDICTION, l'écart se propage au dégât prédit — mesuré 3 points de borne haute sur
FlailSwing niveau 2 (84 vs 81), donc à l'utilité. Aucun renversement d'argmax n'y a été **construit**.

## 5. Ce qui n'est PAS couvert

- ~~**~60 abilities de la face prédiction ne sont dans AUCUN des deux registres**~~ → **FERMÉ par
  #350** (`case-350`) : inventaire clos, **+18** en forme (a), **+1** en (b), **7** abilities dont la
  base n'est pas une moyenne, nommées. Résidus ouverts `#350-r1/r2/r3`.
- **`SortAttackersByDamagePredictionSelector` bâtit TROIS prédictions** (slots 2/4/3 =
  `CalculateMin`/`CalculateAverage`/`CalculateMax`), teste `WillBeKill` sur celle du MAX,
  `MightBeKill` sur celle du MIN, et moyenne le champ `+0x60` de celle de l'AVERAGE ; le port n'en
  bâtit qu'une et moyenne `raw_health_damage`. Axe CHAMP/COMPTE, distinct de l'arrondi. Backlog `#344-r2`.
- **Le volet AoE** : plusieurs playbooks émettent 2 events là où le port en émet 1 (mesuré sur
  BringerOfDespair). Le probe isole la cible principale et **affiche** l'écart de compte.
- **votann et darkangels ne sont pas confrontés live dans le régime `3 mod 4`** : leurs deux sites
  sont des clés de tri internes sans oracle direct. Le verdict repose sur le décompilé (chaîne lue
  de bout en bout) ; les gardes vérifient le câblage sur l'objet importé, et les tests lot1 des deux
  factions passent.

## 6. Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `tests/engine/test_344_ability_damage_average_offline.py` (8) | la divergence par famille sur `3 mod 4` **et** leur coïncidence ailleurs ; le défaut NON LU ; la disjonction des deux registres + résolution de chaque id ; le câblage des 4 sites voisins sur la primitive de LEUR artefact (objet importé, pas texte) ; `HitDamage$$GetDamage` tronque ; `normal_base` retirée ; le renversement d'argmax |
| `tests/engine/test_344_ability_damage_average_live.py` (7) | les deux parités PILOTÉES et le niveau effectif relu ; chaque bras DISCRIMINE ; le code LIVRÉ == natif sur les 4 bras ; la variante nulle diffère entre les deux familles ; les deux mutations symétriques (troncature pour (a), demi-vers-le-pair pour (b)) |

**Mutations jouées, toutes rouges** : troncature partout (1 rouge) ; demi-vers-le-pair partout
(2 rouges) ; `HitDamage` aligné sur `MinMaxDamage$$Avg` (1) ; darkangels dé-câblé (1) ; votann
re-câblé sur `CalculateAverage` (1) ; `normal_base` remise (1).
