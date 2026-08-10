# #585-r3 — l'étage amont : SEPT mirrors, pas quatre, et un piège qui ne s'écrit nulle part

La fiche annonçait **quatre** mirrors à plomber (`AdjacentUnits`, `AdjacentFriends`,
`SurroundingUnits`, `UnitsFromFaction`) et **un** piège (les deux surcharges d'arité 4). Le piège
est **réel et confirmé**. Le compte de quatre, lui, était le compte des mirrors **rencontrés aux
28 sites déjà relevés** — pas celui de l'étage.

## 1. Sept, parce que trois de plus bloquaient EXACTEMENT de la même façon

Compte AST des call-sites sous `engine/**`, avant la tranche :

| mirror | call-sites | dans les quatre de la fiche ? |
|---|---|---|
| `AdjacentEnemies` | **28** | non |
| `AdjacentUnits` | 26 | oui |
| `AdjacentFriends` | 15 | oui |
| `SurroundingEnemies` | **11** | non |
| `SurroundingUnits` | 9 | oui |
| `UnitsFromFaction` | 6 | oui |
| `SurroundingFriends` | **4** | non |

`AdjacentEnemies` est le **plus utilisé des sept** et n'était pas dans la liste. Poser l'étage à
quatre l'aurait re-bloqué au call-site suivant — et c'est arrivé pendant la tranche même : sur les
58 sites relevés ensuite, **20** passent par `AdjacentEnemies`/`SurroundingEnemies`/
`SurroundingFriends`.

## 2. Le piège, confirmé — et il ne concerne QUE deux des sept

`IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends` et `$$AdjacentEnemies` ont **deux
surcharges d'arité 4**, au même nom affiché, indiscernables dans le pseudo-C :

| variante | signature | `selectionType` |
|---|---|---|
| **A** | `(this, unit, unique, selectionType)` | **propagé** au `Units` interne ET au `Friends`/`Enemies` final |
| **B** | `(this, unit, unitTile, unique)` | **`3` EN DUR** aux deux étages ; le 3ᵉ argument est une **entité** (l'ancre géométrique) |

Lire le 4ᵉ argument de **B** comme un `selectionType` donne `1` = `OnlyAlive` — **le filtre qui
n'écarte PAS `Untargetable`**, soit l'inverse exact de ce que ce chantier répare.

Emprunteurs de la variante B, **re-dérivés par `list_xrefs`** (pas hérités) : **15** fonctions pour
`$$AdjacentFriends`, **11** pour `$$AdjacentEnemies`, dont **2 communes**
(`TalonOfHorusAbility$$GetAdditionalTargets`, `FealtyAbility$$GetAdditionalTargets`, qui empruntent
B des deux côtés).

⚠ **Les cinq autres mirrors n'ont PAS ce piège, et c'est un RÉSULTAT, pas une symétrie supposée.**
Les **deux** surcharges de `$$SurroundingUnits`, les **quatre** de `$$SurroundingEnemies`, les
**quatre** de `$$SurroundingFriends` et les **deux** de `$$UnitsFromFaction` portent toutes
`unitSelectionType` en **dernière** position et le propagent ; aucune n'en code un en dur. Elles ne
diffèrent que par la séparation `unit`/`unitTile` et par le typage du 3ᵉ argument (`$$UnitsFromFaction`
reçoit soit l'enum `UnitFaction` — qu'il convertit par `System.Enum.ToString` — soit le `factionId`
déjà en `string`). `$$AdjacentUnits` n'a **qu'une** surcharge.

## 3. Où le filtre tombe, lu et non déduit

* `$$AdjacentUnits` = `op_Subtraction(Units(AdjacentTiles(origin), unique, selectionType), origin)`.
  **Sans wrapper `Enemies`/`Friends`, ce filtre est le SEUL de l'ensemble rendu** — c'est le mirror
  où le paramètre pèse le plus.
* `Adjacent*`/`Surrounding*` avec camp : le prédicat est appliqué **deux fois** (au `Units` interne,
  puis au `Friends`/`Enemies`). Il est **pur** en `(unité, selectionType)`, donc idempotent → un
  seul passage au port.
* `$$UnitsFromFaction` → `UnitsFromFactionSelector$$.ctor(state, entities, factionId,
  shouldBelong = 1, unitSelectionType)` (champ `+0x2c`), `shouldBelong` **en dur** dans les deux
  surcharges. `$$Select` consomme le `selectionType` **d'abord** (dans le `SelectUniqueUnits` qui
  énumère `entities`), le test `IdunBattle.Entities.UnitExtensions$$HasFaction` **ensuite**.

## 4. Ce que la validation a mesuré, et qui change la lecture du témoin

`_within` — le foyer géométrique du port — **filtre déjà les vivants**, en amont du `selectionType`
(mirror de `IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`, qui résout l'occupant par
le `TileContentComponent` : un mort n'y est plus, cf. #57m).

⇒ Sur un sélecteur d'**occupation**, `Any` et `OnlyAlive` rendent le **même** ensemble. Le couple
qui discrimine est `OnlyAlive` / `OnlyAliveAndTargetable` — **exactement le couple que #585 avait
mesuré live** sur `spaceRockfist` en deep strike. Un témoin construit sur `Any` vs `OnlyAlive`
aurait rendu un accord **dégénéré**, et cet accord aurait pu se citer ensuite comme une preuve.

Corollaire de montage : il faut un `Untargetable` **dans chaque camp**. Avec un seul témoin côté
allié, `AdjacentEnemies` et `SurroundingEnemies` rendaient le même ensemble pour les quatre
littéraux — le premier jet du cliquet est passé par là.

## 5. Livré

* Les sept mirrors portent `selection_type`, **en dernière position**, défaut `None`. Neutralité
  vérifiée mécaniquement : **0** call-site du dépôt ne dépasse l'arité historique en positionnel.
* Effet mesuré sur le recenseur : `probe_585r1_selection_type_call_sites.py` passe de **122 à 195**
  call-sites. Ces **73** sites n'étaient pas « déjà renseignés », ils étaient **INVISIBLES** — le
  recenseur ne visite que les factories qui portent le paramètre.
* Cliquet : `tests/engine/runner/test_585r3_etage_amont_selection_type_offline.py` — présence et
  **position** du paramètre, neutralité du défaut (mesurée contre `Any`, pas affirmée), morsure sur
  les quatre littéraux pour les sept mirrors, non-dégénérescence assertionnée, exclusion du mort
  **nommée** (règle #57m), et cohabitation `reference` × `selection_type`.
* Contre-épreuve : `probe_585r3_mutants.py`, **4/4 mordent** — dont deux mutants « paramètre
  décoratif » (stocké, jamais lu), que l'introspection de signature ne peut pas voir.

## 6. Ce qui n'est PAS couvert

* **Aucune confrontation LIVE.** Le défaut `None` rend la pose observationnellement nulle par
  construction ; ce qui se confronte, c'est le **relevé** (les littéraux posés aux call-sites), et
  son régime discriminant exige une unité `Untargetable` dans le champ du sélecteur — le montage
  que #585 avait dû construire pour `WarHowl`.
* **Le flag `unique`** de `Units`/`AdjacentUnits`/`Surrounding*` reste hors paramètre : résidu
  `#433-r3-r1a-r1`, distinct et préalable.
* **La `reference` d'`AdjacentEnemies`** (le natif sépare `unit` de `unitTile` dans la variante B)
  n'est pas paramétrée côté port — aucun call-site relevé n'en a besoin, tous ayant `unit == caster`.
  `AdjacentFriends` et `SurroundingEnemies`, eux, la portent déjà.
