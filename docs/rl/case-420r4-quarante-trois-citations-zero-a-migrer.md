# #420-r4 — 43 citations « à lire », **0** à migrer : c'est le COMPTEUR qui les fabrique

**Mesuré le 2026-08-15, build `t6dpr4k06g`**, `probe_283_enum_ordinal_sweep.py --step prose -v`.

## 1. Le compte de la fiche était faux, et le verdict aussi

La fiche annonçait **15** citations d'origine inconnue (compte de `rnca9r7q6c`). La re-mesure en
donne **43**, dans **26 fichiers** (2 097 justes à côté). Les **43** ont été LUES une par une.
**Aucune n'est à corriger.**

Le critère de l'étape 4 est un **appariement de proximité** en prose : un nom de membre d'enum
suivi (ou précédé) d'un nombre à ≤ 4 séparateurs. Elle ne vérifie pas que le nombre *prétend*
être un ordinal — c'est un COMPTEUR, pas un gate, et l'étape 4bis (qui, elle, exige que le nombre
vaille l'ordinal ARCHIVÉ) rend **0**.

## 2. Ventilation des 43

| # | catégorie | ce que le nombre désigne | exemples |
|---|---|---|---|
| 12 | **estampille historique** délibérée | l'ordinal d'un build ANTÉRIEUR, cité pour montrer le décalage | `damage_utility.py:43,48` (8), `heal.py:19`, `probe_519:10`, `probe_431_build_literals.py:11`, `test_431_build_pin_offline.py:475` |
| 9 | **ordinal JUSTE d'un AUTRE enum** | homonymie de membre | `StatType.Attack=0` (×4), `UnitFlag.ArrivedAtFinalTile=1`, `PhaseType.AddUnit=4`, `ObscuringType.Elevation=2` (×2) |
| 7 | **appariement de voisinage** du regex | le nombre étiquette l'élément VOISIN | `damage_utility.py:49` (table du build COURANT, ordinaux tous justes), stat-blocks i2 « … Damage **N** Armour » (×2), un numéro de ligne |
| 6 | **slot d'interface** | `IOperationProcessor` | `127 ChangeUnitOwner` (×5), `68 TransferDamage` |
| 4 | **poids / magnitude d'utilité** | `Elevation 10/niveau` (×3), `AddedTileEffects = 0` | `tile.py:1317`, `strike.py:751`, `orks.py:244` |
| 2 | **offset de champ natif** | `<this+0x18 : Remaining>` | `probe_278`, `test_repair_prediction_values_live.py` |
| 2 | **compte d'events observés** | 6 `UnitDamaged` attendus | `probe_202b`, `probe_204` |
| 1 | **id de gameconfig** | `EffectType.Fire=5` / `FirstAidHeal=10` | `tile.py:26` |
| **0** | **citation d'ordinal FAUSSE** | — | — |

## 3. Deux sites méritent d'être signalés

- **`probe_431_build_literals.py:11` et `test_431_build_pin_offline.py:475`** sont
  **auto-référentiels** : ils citent le témoin que #420 a laissé EXPRÈS
  (« cette table portait `55: UnitDefeated`, juste sur `gqfc5mff6c` »), et le second est une
  **contre-mutation** qui vérifie que le cliquet NE rougit PAS dessus. Les « corriger »
  inverserait le test.
- **`tile.py:26`** était réellement ambigu (une table de synthèse collait `5,10` au nom
  `MoltenForm` sans dire de quel enum ils venaient). Corrigé dans cette tranche : c'est la seule
  édition qu'ait produite ce résidu.

## 4. Ce qui reste — `#420-r7`

**16 des 43** (catégories « voisinage » et « autre enum ») sont éliminables **mécaniquement** :

- sur une ligne de type table (`<n> <Nom>  <n> <Nom> …`), ne retenir l'appariement SUFFIXE que
  si aucun appariement PRÉFIXE n'existe pour le même couple (ligne, membre) — éteint
  `damage_utility.py:49` en entier (4 sites, ordinaux tous JUSTES) ;
- appliquer à l'étape 4 le discriminant que `probe_519_ordinaux_decales.py:13-26` énonce déjà
  (« LE NOM NE TRANCHE PAS L'ENUM ») — **2 des 9** faux positifs de cette catégorie sont
  précisément les lignes de `probe_519` qui décrivent ce faux positif.

⚠ Ne pas le faire à l'aveugle : ce compteur garde un gisement réel (13 citations vraies trouvées
par #420). Un raffinement qui éteindrait aussi des vraies serait pire que le bruit actuel.
