# #447 — la voie du BIT 51 de `TargetIsNotSteppable`, CONFRONTÉE AU NATIF

**Livré le 2026-08-01.** Build de référence : `rnca9r7q6c`. Ferme le premier résidu de
`docs/rl/case-442-target-is-not-steppable.md` §6.

## 1. Ce qui restait ouvert

`TargetIsNotSteppable` a **deux armements**. #442 a confronté le premier — l'armement IMPLICITE
(`get_IsUnitTargeting` sans `AllowSteppableUnit`, l'attaque normale incluse), 18/18 en live. Le
second — le **BIT 51 posé au masque** — n'y était confronté qu'**offline** (étage D), faute de
porteur joignable.

## 2. Les deux montages de #442, instruits — et ce qu'ils rendent

**Montage 1 — `write_augmented_seed_bc` sur `necroSmnDestroyer` : MESURÉ, et il échoue, mais pas
là où #442 le supposait.** Le catalogue n'a rien à compléter : l'entrée `necroSmnDestroyer` est
**déjà** dans le seed BC (`Health`/`Damage`/`Armor` à 0, comme toute entrée de summon) et sa config
`TunnelingHorror` est **déjà** dans `BC.Abilities.ActiveAbilities`. `augment` rend
`added=[] abilities=[]`. Le refus vient de l'**étage 2**, celui qu'aucun enrichissement du catalogue
ne lève (`case-92` §5bis) : `buildNormalizedBC` →
`IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor` ne couvre pas les summons,
l'unité reste hors `normalized`, et le build sort en
`--a-units: hors pool / non spawnables au rank 17: ['necroSmnDestroyer']` (pool = 97).

**Montage 2 — un board qui pose ses `EnvFactionSummons` : NON TENTÉ**, et devenu sans objet (§6).

**Montage 3 — la GREFFE DE L'ACTIVE sur une unité du pool**, recours 3 de `case-92` §5bis. C'est
celui qui est joué.

* **Elle est NÉCESSAIRE, et le natif le dit** :
  `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` commence par
  `ActiveAbilityComponent$$GetOrNull(unit, abilityType)` et rend `broken(ValidRequest)` quand
  l'unité ne possède pas l'ability — on ne peut pas interroger le natif sur une ability non montée.
* **Elle est EXACTE pour cette mesure** : les `TargetingOptions` sont un champ de l'objet
  `AActiveAbility` résolu **par TYPE** (le natif les lit sur l'instance rendue par le service
  d'abilities, jamais sur l'unité) — le masque exercé est celui du ctor de
  `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$.ctor`. La limite
  habituelle de la greffe (« ni stats ni traits ni armes du vrai porteur ») ne mord sur **aucune**
  des quatre règles armées par 1011 (bits 1, 6, 12, 51), et la portée ne mord pas non plus : son
  `TargetingRange` est `useWholeBoard`. **Mesuré** : le verdict est identique avec un greffon
  Necron (`necroWarden`) et avec un greffon Adepta Sororitas (`adeptRetributor`) — §5.
* **Elle n'était pas OUTILLÉE.** `case-92` §5bis la DÉCRIT, mais seul le volet passif avait sa
  fonction. Cette tranche ajoute le pendant exact : `catalog_inject.graft_active_ability` +
  `write_grafted_seed_bc(..., kind="active")` (défaut `"passive"` — signature non cassante).

## 3. Ce que la voie du bit exhibe, et que la voie unit-targeting ne peut pas montrer

`1011 TunnelingHorror` est **TILE-targeting** (bit 6), donc son `get_IsUnitTargeting` est **FAUX** :
la voie implicite de #442 ne l'arme pas. Chez lui la règle n'est armée **que** par le bit 51 —
c'est la branche `else` du natif, celle qui saute directement au prédicat.

Et 1011 porte **aussi** le bit 12 `TargetTileIsFree`, dont l'appel natif est
`IdunBattle.Entities.TileExtensions$$IsFreeTile(tile, state, allowSteppable: 1, allowTemporaryTile: 0,
allowAnyUnit: 0)`. Relu verbatim, sa branche `allowSteppable != 0` rend **libre** une tuile portée
par une unité `Steppable` (`IsEmpty()` faux → `GetUnit` → `GetBaseUnitComponent` → `HasTrait(0x1b)`
→ `return true`). Le partage des deux règles est donc **mesurable**, et c'est le cœur de la tranche.

Les deux masques ne diffèrent, sur ce point, **que par le bit 51** :

```
1011 TunnelingHorror     0x8000000001042 = bits 1 (dynamique) | 6 (tuile) | 12 | 51
1166 AberrantHypermorph          0x1040  = bits                 6 (tuile) | 12
```

## 4. La confrontation — `probe_447_bit51_native.py`, quatre étages

Montage : greffe de l'active 1011 sur les 4 unités adverses, puis `genesPrimus` amené au contact de
l'une d'elles et `CultDemagogue` (1179) cast sur elle → 4 `genesSmnDecoy`. Le greffon est ensuite
l'interrogé du gate natif, tuile par tuile.

**Étage B — la voie du BIT 51 (natif)**, `abilityReason(caster, 1011, targetId = id de TUILE)`
(`boardGraph` et `abilityReason` peuplent tous deux leur table par `forEachEntity` : même espace
d'ids) :

| cible | natif | règle natif | port |
|---|---|---|---|
| 4 tuiles de DECOY | `0x8000000000000` | `TargetIsNotSteppable` | `0x8000000000000` |
| 9 tuiles d'unité non-`Steppable` | `0x1000` | `TargetTileIsFree` | `0x1000` |
| 3 tuiles LIBRES | `0x0` | — | `0x0` |

Accord natif/port **16/16**, et les trois régimes sont présents — la mesure ne dégénère ni en
« refuse tout » ni en « accepte tout ».

**Étage C — LE PARTAGE 51 / 12 (natif)**. `1166 AberrantHypermorph` (`RANGE_ADJACENT`) est amenée au
contact de **chaque** decoy tour à tour, et interrogée sur **la même tuile** que 1011 :

| tuile | natif 1166 (bit 12 seul) | natif 1011 (bit 12 + 51) |
|---|---|---|
| DECOY (×4) | **`0x0` — ACCEPTÉE** | **`0x8000000000000`** |
| unité non-`Steppable` (×3) | `0x1000` | `0x1000` |
| tuile libre (×4) | `0x0` | `0x0` |

**11/11** lignes en accord natif/port **sur les deux abilities**, **4 lignes discriminantes**. C'est
la ligne que le brief exigeait : *une tuile qu'un decoy occupe, refusée par 51 et NON par 12*. Sans
elle, les deux règles pourraient rendre le même code sur la même entrée et l'accord ne prouverait
rien.

⚠ **Ne pas attendre `0x0` sur toute tuile à d=1.** L'adjacence native
(`IdunBattle.Core.Utils.MovementUtil$$AreTilesAdjacent`) est gatée en élévation (`|dElev| < 2`) :
au premier jet, la tuile libre `t24` (seed 777 / `MC1_67`) a rendu `TargetIsInRange` — natif **et**
port d'accord. C'était un attendu faux du probe, pas une divergence ; le critère accepte désormais
`TargetIsInRange` là où la portée peut mordre, et la non-dégénérescence est portée par des
compteurs explicites.

**Étage D — l'armement, offline sur les VRAIES classes du registre** (contrefactuel du CHAMP) :

* **D1** — `1011.is_unit_targeting = False` et `has(bit 51) = True` : la voie implicite est FERMÉE
  chez lui, donc le refus de l'étage B ne peut venir que du bit.
* **D2** — 1011 **privée** du bit 51 rend `0x0` sur les 4 decoys : le bit est **nécessaire**.
* **D3** — 1011 **avec** `AllowSteppableUnit` (bit 20) refuse **quand même** (4/4). **NON CONFRONTÉ
  au natif** : **0** des **102** masques du registre pose le bit 20 (compte re-dérivé), et un masque
  est un littéral de ctor — aucun cast live ne peut l'exercer.

### Généralisation

Même verdict sur un montage entièrement différent — autre board (`C4_09`), autre seed (`31337`), et
surtout **un greffon d'une autre faction** (`adeptRetributor` au lieu de `necroWarden`), ce qui est
le discriminant du point §2 : le masque est une propriété de l'**ability**, pas du porteur.

```
python scripts/python/probe_447_bit51_native.py --seed 31337 --board C4_09 --graft adeptRetributor
```

Étage B **16/16**, étage C **7/7** avec **3** lignes discriminantes (un decoy avait disparu entre
deux déplacements — compté « NON MESURÉ », jamais supposé).

### Trois contre-épreuves, chacune vérifiée mordante

| # | mutation | mesuré |
|---|---|---|
| CE1 | la règle 51 neutralisée (`if False and …`) | **3 rouges** : B (4 MISMATCH sur les decoys), C (4), D3. A reste VERT — il mesure le substrat, pas la règle |
| CE2 | `has_steppable_unit` → `return False` | **A rouge**, sortie immédiate |
| CE3 | le bit 12 neutralisé | **2 rouges** : B (9 MISMATCH), C (3) — le bit 12 est bien MESURÉ, son acceptation de la tuile du decoy n'est pas un angle mort |

⚠ **D2 ne peut pas rougir sous CE1** (privée du bit ou règle morte, le port rend `0x0` dans les deux
cas) : c'est un test de **nécessité** du bit, gardé pour la suffisance par B et D3.

Garde : `scripts/python/tests/engine/runner/test_bit51_native_live.py` (11 tests, ~18 s).

## 5. Ce que la tranche change

**Rien au moteur.** Le port était déjà conforme sur les deux armements : l'accord est de **27/27**
lignes natif/port sur les deux étages live, sans aucune modification d'`engine/`. La tranche
**convertit un mirror-offline en mesure**, et outille la greffe ACTIVE pour la suite.

## 6. Résidus

* **`AllowSteppableUnit` (bit 20) reste NON CONFRONTÉ** — 0 porteur sur 102 masques, et le masque
  est un littéral de ctor : il n'y a pas de montage live, seulement un patch mémoire. Le port en
  porte le contrefactuel (étage D3).
* **Le montage `EnvFactionSummons` n'a pas été tenté** et n'est plus nécessaire : la voie du bit est
  confrontée. Il resterait la seule façon d'observer `necroSmnDestroyer` **lui-même** (ses stats,
  son arme, sa passive `WhipcoilBody`) — hors périmètre de la règle de ciblage.
* **Citation de symbole PÉRIMÉE dans le port** (nommé, non corrigé — hors périmètre) :
  `engine/runner/abilities/targeting.py` cite `IdunBattle.Entities.TileExtensions$$CanAddUnit` pour
  le bit 12 (`tile_can_add_unit`, et le pendant DÉCISION `engine/battle_query.can_add_unit`). Ce
  symbole **n'existe pas** dans `data/symbols/rnca9r7q6c/ghidra/functions.tsv` : le corps s'y appelle
  `IdunBattle.Entities.TileExtensions$$IsFreeTile` (deux adresses), aux côtés de
  `TileExtensions$$CanAddUnitFromAbility`. La sémantique décrite par la docstring est **exacte** —
  c'est bien ce que fait `IsFreeTile` — seul le nom a bougé. À renommer lors d'une passe qui touche
  déjà ce module.
* Les résidus **`astarSmnHaywireMine`** et **les 25 npc `Steppable`** de #442 §6 sont inchangés.

## 7. Ce qui a été joué (relevé daté)

**AVANT rebase.** `probe_447_bit51_native` PASS (seed 777 / `MC1_67`) · PASS en généralisation
(31337 / `C4_09` / `adeptRetributor`) · `test_bit51_native_live` 11 ✅ ·
`test_steppable_targeting_live` 8 ✅ · `test_targeting_masks_live` 13 ✅ ·
`test_ability_target_gate_live` 13 ✅ · `test_echoes_from_the_warp_revive_live` 6 ✅ ·
`test_harlequins_panoply_live` 10 ✅ · `test_411_transfer_hit_wiring_offline` +
`test_380_seed_bc_patch_survival_offline` + `test_237_relic_equip_offline` +
`test_366_r1_bcpatch_port_blindspot_offline` **51 ✅** — ces quatre derniers gardent
`catalog_inject`, le seul module existant que la tranche modifie.

**APRÈS rebase sur `origin/master`** (5 commits entre-temps — #443 `SaviorProtocols`, #419-r1
tranche 3 ; `engine/runner/abilities/targeting.py` est dans le diff, donc le re-jeu n'est pas
formel) : `test_bit51_native_live` 11 ✅ · `test_steppable_targeting_live` 8 ✅ ·
`test_targeting_masks_live` 13 ✅ · `test_ability_target_gate_live` 13 ✅ — et la **banque de
cliquets VERTE, 24 cliquets, mur 92,3 s**.

Le probe n'entre PAS à la banque : il monte un runner, et la banque est offline (le critère est le
coût marginal en parallèle).

## 8. Re-dériver

```
python scripts/python/probe_447_bit51_native.py
python -m pytest tests/engine/runner/test_bit51_native_live.py -q
```
