# #433-r4-r2 — les deux consommateurs qui tranchaient l'adjacence HORS du foyer mirror

**Verdicts : FORK PORTÉ (`EarlyWarningOverridePlaybook`) et FORK DE FOYER PORTÉ, sans écart
observable (`BattleQuery$$GetNearestEnemy`).** Les deux appellent la **même** primitive native,
`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` — mais par deux chemins différents, et
l'énoncé hérité se trompait sur les deux.

La bascule du natif est **mesurée contre lui-même** : même caster, même tuile, même sweep, seule la
tuile de l'ennemi passe d'un voisin PLAT à un voisin à `|dElev| >= 2` — et le bonus natif à `d = 4`
passe de **50** à **0**. Aucun terme du port n'entre dans cette mesure.

## 1. Ce que l'inventaire annonçait, et ce qui est FAUX

| énoncé #433-r4 | verdict |
|---|---|
| #11 `EarlyWarningOverridePlaybook` « porté HORS FOYER, `hexgeo.distance == 1` » | **CONFIRMÉ** |
| #11 « le régime d'identité y est inatteignable » | **CONFIRMÉ** (caster vs ennemi vivant distinct) |
| #17 `GetNearestEnemy` « tranche par `bq.is_adjacent` » | **CONFIRMÉ** |
| #17 la primitive native y est `AreUnitsInMelee` | **FAUX** — le décompilé appelle `BattleQuery$$AreEntitiesAdjacent` **directement** ; `$$AreUnitsInMelee` existe, mais c'est un **passe-plat d'une ligne** vers cette même fonction, et il n'apparaît pas dans ce corps |
| les slots cités par les deux ports (`0x49`, `0x6b`, `0x72`, `0xb2`, `0xc4`) | **PÉRIMÉS d'un cran** depuis `gqfc5mff6c` — re-dérivés au runtime, cf. §5 |
| `slot0xb3` « NON identifié » (port) | **IDENTIFIÉ** : `BattleQuery$$FindRangedWeapon` |

## 2. La primitive, pour chacun — lue au décompilé

### 2.1 `IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable`

```
casterTile = EntityExtensions.GetMainTile(caster, state)      # la tuile REELLE, pas la position balayee
otherTiles = EntityExtensions.GetTiles(otherUnit, state)
adj        = TileExtensions.IsAdjacentTo(casterTile, otherTiles)
if (!adj)  { if (!IsTileInRangeOfAnyAbility(otherUnit, P))  util += 50 }   # branche A
else       { thr = FindRangedWeapon(otherUnit)?.[+0x24] ?? 1
             if (thr < d)                                    util += 50 }  # branche B
util -= d * 10
```

`IdunBattle.Entities.TileExtensions$$IsAdjacentTo`, surcharge **`(tile, otherTiles)`**, est un
`∃` sur la liste dont **chaque paire** passe par `MovementUtil$$AreTilesAdjacent` (surcharge
SCALAIRE) : `(|dElev| < 2) & (t1 == t2 || ConnectivityComponent.IsNeighbour(t1, t2))`.

Ce booléen ne produit pas une valeur : il **choisit une branche**. L'oublier ne casse donc rien —
ça fait évaluer l'autre branche, en silence. Le port tranchait par `hexgeo.distance(origin, ep) == 1`
(ni identité, ni porte d'élévation) : **FORK**.

`adj` est évalué sur `caster`, pas sur la position balayée ⇒ le partage A/B est **constant sur tout
le sweep**. C'est ce qui rend le fix mesurable position par position.

### 2.2 `IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy`

```
best = null ; bestD = int.MaxValue ; bestAdj = false
tiles = position.HasValue ? position.Value : GetUnitPosition(caster)
foreach (u in GetAllAliveUnits(null))
    if (!UnitExtensions.IsEnemy(caster, u, state))   continue
    if (UnitExtensions.IsIrrelevantObject(u))        continue
    d   = BattleQuery.GetDistance(tiles, u)
    adj = BattleQuery.AreEntitiesAdjacent(tiles, u)
    if (d < bestD || (adj && !bestAdj)) { best = u ; bestAdj = adj ; bestD = d }
return best
```

`AreEntitiesAdjacent` → `MovementUtil$$AreTilesAdjacent(IList, IList)` → la scalaire. Le foyer
mirror est donc `battle_query.are_entities_adjacent`, **et non** `battle_query.is_adjacent`, qui
mirrore `TileQuery$$IterateAdjacentTiles` — la primitive que **#433-r1 §4 désigne comme
contre-exemple** (elle ne rend jamais la tuile source ; l'aligner ferait compter chaque unité comme
sa propre voisine). Le brief demandait de vérifier ce point avant de toucher quoi que ce soit :
**`is_adjacent` reste inchangé**, seul le call-site est re-pointé.

**Écart observable : NUL, et par COMPOSITION.** Les deux foyers du port ne diffèrent que par le
court-circuit d'identité ; il exige que les deux opérandes désignent la même tuile, or
`engine.ai.context._enemies` filtre `alive` — un cadavre n'entre pas dans `ctx.epos`, et deux unités
vivantes distinctes ne partagent pas une tuile. La porte d'élévation, elle, était **déjà portée des
deux côtés** (`are_entities_adjacent` la délègue à `is_adjacent`). Le re-pointage est posé par
**fidélité**, pas parce qu'un régime l'exige — et le test l'atteste plutôt que de l'affirmer
(balayage exhaustif des paires distinctes d'un voisinage à relief : 0 divergence).

## 3. La MESURE qui isole la cause — le natif contre lui-même

`probe_433_r4_r2_adjacency_foyer.py --step partition`, board `MC1_67`, caster `tauCrisis` (HERO du
pool, seul porteur `lineup` de 1077), ennemi `tauMarksman` (arme à distance de portée **3**).
Le triplet (tuile d'origine, voisin haut, voisin plat) est **dérivé du `boardGraph`**.

`O = (1,2)` élévation 2 ; `Y_hi = (1,3)` élévation **4** ; `Y_lo = (0,1)` élévation 3.
Le voisin haut est **absent de la liste d'adjacence NATIVE** de `O` (le `boardGraph` publie
`GetAdjacentTiles` → `IterateAdjacentTiles`, qui a déjà traversé la porte) ; le voisin plat y est.

Gisement re-dérivé le 2026-08-03 (entrées versionnées) : **685 boards sur 779** portent au moins une
paire voisine à `|dElev| >= 2` ; sur `MC1_67`, **18 arêtes dirigées sur 316**. Un montage plat
rendrait vert pour la mauvaise raison — d'où le verrou de montage du test, qui exige à la fois
`|dElev| >= 2` **et** l'absence du voisin haut de la liste native. *(Chiffres à re-dériver.)*

| bonus natif (= `util + 10·d`) | d=1 | d=2 | d=3 | **d=4** |
|---|---|---|---|---|
| ennemi sur `Y_hi` (`\|dElev\| = 2`) | 0 | 0 | 0 | **0** |
| ennemi sur `Y_lo` (plat) | 0 | 0 | 0 | **50** |

Même caster, même tuile, même sweep de 33 positions, même unité ennemie : **seule l'élévation de la
tuile occupée change**, et le natif change de branche. `50` à `d = 4` = branche B (`d > 3`, la portée
de l'arme à distance) ; `0` = branche A (`IsTileInRangeOfAnyAbility` vrai jusque-là).

C'est la preuve que `AreTilesAdjacent` — porte d'élévation comprise — est bien ce qui tranche
« caster adjacent à E », **sans qu'aucun terme du port n'intervienne**.

## 4. Le couple divergence → convergence, sur le port

`--step couple`, même board, `--unit-stat tauCrisis:Movement=2` : le sweep est **confiné à
`d <= 3`** de l'ennemi. Pourquoi confiner — c'est le point qui rend l'oracle interprétable : les
deux approximations de branche du port (§5) sont exactes tant que `d <= portée`, et la mesure §3
montre que le natif ne verse rien avant `d > 3` non plus. Hors de ce domaine, un désaccord serait
imputable à ces approximations, pas au terme corrigé.

`O = (1,2)` élévation 2, ennemi sur `(1,3)` élévation 4, **15** positions balayées, `d_max = 3`.

| | `adj_origin` | positions où port ≠ natif | action émise |
|---|---|---|---|
| port **AVEC** le canal (livré) | `∅` | **0 / 15** | aucune |
| port **canal NEUTRALISÉ** (`elev_by_pos = None`) | `{(1,3)}` | **9 / 15** | cast 1077, `to=(0,1)`, util **30** |
| natif (`ncEvaluate`, sweep) | — | référence | max du sweep = **−10** |

La troisième lecture est ce qui empêche l'accord d'être tautologique : sans elle, un port
d'accord avec le natif ne prouverait pas que la porte mord. Et l'utilité **30** que le port émettait
sans le canal n'est atteinte **nulle part** par le natif sur ce sweep.

⚠ « le port n'émet plus » n'est **pas** « le natif n'émet pas » : le Bucket de ce playbook n'a pas
de `min` (résidu `#433-r4-r2-r3`). L'assertion porte sur l'utilité **émise**, qui se compare.

## 5. Les six slots, RE-DÉRIVÉS au runtime

`--step slots` délègue à `probe_27_4g_battlequery_slots.py` (balayage borné de la vtable propre de
`BattleQuery`, conversion `slot d'interface + 4 = index de vtable` vérifiée sur deux ancres
indépendantes). Les slots cités par les deux ports dataient de `gqfc5mff6c` et étaient **tous
décalés d'un cran** — recopier une fiche désigne donc la **méthode voisine**, sans aucune erreur.

| slot d'interface | méthode | ce que le port en disait |
|---|---|---|
| `0x4a` | `GetNearestEnemy` | `0x49` |
| `0x60` | `AreEntitiesAdjacent` | (confirme #433-r3) |
| `0x6c` | `GetDistance` | `0x6b` |
| `0x89` | `GetAllAliveUnits` | `0x88` |
| **`0xb3`** | **`FindRangedWeapon`** | **« NON identifié »** |
| `0xc5` | `IsTileInRangeOfAnyAbility` | `0xc4` |

`0xb3` est celui qui comptait : le `threshold` de la branche B n'est pas une constante, c'est le
champ `Nullable<int>` à `+0x24` de l'arme rendue par `FindRangedWeapon` — **la portée de l'arme à
distance** (`?? 1` = mêlée). Mesuré live : ennemi plat `tauMarksman`, le natif verse `+50` à partir
de `d = 4`, c'est-à-dire `d > 3` = sa portée, et non `d > 1`.

## 6. Ce qui est porté, et ce qui ne l'est pas

**Porté** : le *partage* A/B, c'est-à-dire la primitive d'adjacence, pour les deux consommateurs.
`EarlyWarningOverridePlaybook` expose désormais `enemies_of` / `adjacent_at_origin` / `utility_at`
— extraction sans changement de comportement, dont l'objet est de rendre l'utilité **confrontable
position par position** à `ncEvaluate` (comparer les seuls argmax laisserait passer un désaccord
compensé).

**Non porté** : le *contenu* des deux branches. Les deux approximations sont désormais **lues**, pas
seulement soupçonnées — cf. §7. Elles sont hors du périmètre de ce cas (deux autres fonctions
natives, chacune avec sa propre RE et son propre oracle), et les toucher ici aurait confondu la
validation.

## 7. Résidus NOMMÉS

* **`#433-r4-r2-r1` — branche A : `IsTileInRangeOfAnyAbility` (slot `0xc5`) n'est pas portée.**
  Le natif, lu :
  `if (GetFeetCount(unit) > 1) return true ; return slot0xe(<this+0x20>, unit, OrderedSet{GetMainTile(unit)}, true).Contains(tile)`
  — donc **mouvement et LoS compris**, plus un court-circuit **multi-tuiles → toujours en portée**.
  Le port approxime par `d <= portée d'arme max`. **Mesuré** (`tauMarksman`, portée 3, sweep de 33
  positions) : le natif rend « en portée » jusqu'à `d = 5` **inclus**, et exclut **une** tuile à
  `d = 5` que ses voisines de même distance incluent (LoS/élévation). L'approximation est donc
  fausse dès `d > portée`, **dans les deux sens**.
  *Canal pour la fermer* : RE du slot `0xe` du service à `BattleQuery+0x20`, puis oracle
  `ncEvaluate` sur un sweep dépassant la portée de l'ennemi (le montage de `--step partition` le
  produit déjà).
* **`#433-r4-r2-r2` — branche B : le `threshold` reste figé à `1`.** Il vaut
  `FindRangedWeapon(E)?.[+0x24] ?? 1`. Le port n'a pas de modèle « l'arme à distance » (il ne
  connaît qu'un max sur `weapons`), donc la fermeture demande de lire le corps de
  `FindRangedWeapon` (quelle arme, quel départage).
  ⚠ **À garder en tête** : une fois fermé, `threshold` vaudra la portée de l'arme à distance —
  la **même** valeur que `portée d'arme max` pour toute unité à une seule arme à distance. Les deux
  branches du **port** deviendront alors identiques, et le partage A/B cessera d'être observable
  *dans le port* tant que `#433-r4-r2-r1` n'est pas fermé lui aussi. C'est pourquoi l'oracle §3
  (le natif contre lui-même) est la mesure qui fait foi ici, et pas §4.
* **`#433-r4-r2-r3` — `MIN_UTILITY = 1` sur `EarlyWarningOverridePlaybook` est CONTESTÉ.** Son
  Bucket est construit par le ctor à **deux** arguments — donc sans `min` — là où
  `MasterOfTheTutelariesPlaybook` lit le statique `+0xb8` et le passe au ctor à quatre arguments.
  Les **deux** cctors écrivent pourtant `Fix64(1)` à `+0xb8`. Et `ncEvaluate` rend un `best` à
  utilité **négative** à chaque position (§4). Reste à établir qui lit ce statique ici (un
  `get_MinUtility` consommé par le générateur ?). Non tranché, non touché.
* **`#419-r1-tr10-r2` (recoupement)** — les deux natifs comparent des **empreintes**
  (`GetMainTile(caster) × GetTiles(E)` pour #2.1, `GetUnitPosition(caster) × GetTiles(u)` pour
  #2.2) là où le port compare deux tuiles principales. Écart sur les seules unités MULTI-TUILES.
* **`GetNearestEnemy` : le filtre `IsIrrelevantObject` n'est pas porté**, et l'ordre
  d'énumération natif (`GetAllAliveUnits`) reste approximé par l'ordre de `ctx.epos` (départage des
  ex æquo). Hors périmètre adjacence, signalé.

## 8. Validation

* **OFFLINE** — `tests/engine/test_433_r4_r2_adjacency_foyer_offline.py`, **15 passed**. Axes : la
  bascule dans les **deux sens** (voisin plat → branche B ; `|dElev| >= 2` → branche A), le
  court-circuit d'identité, la dégradation sans canal (borne SUPÉRIEURE, aucune adjacence retirée à
  l'aveugle), le seuil strict `|dElev| < 2` (`1` passe, `2` non), les deux prédicats de branche,
  l'action émise bout en bout, la garde de FOYER de `_nearest_enemy_tile` (compteur d'appels), la
  priorité mêlée gatée, l'**inertie prouvée** du re-pointage sur toutes les paires distinctes d'un
  voisinage à relief, et le maintien de `is_adjacent` comme contre-exemple.
* **CONTRE-ÉPREUVE par MUTATION** — les deux foyers remis à leur état d'avant
  (`hexgeo.distance == 1` / `bq.is_adjacent`) : **6 des 15 rougissent** ; arbre restauré, sha256
  re-vérifié. `test_tutelaries_melee_priority_respects_the_elevation_gate` reste vert sous la
  mutation #2 — c'est **correct** et c'est la preuve de l'inertie annoncée au §2.2.
* **LIVE** — `tests/engine/test_433_r4_r2_adjacency_foyer_live.py`, **7 passed / 134 s** : les six
  slots, l'absence du voisin haut de la liste d'adjacence native, la bascule A/B du natif (§3), le
  confinement du sweep, la mutation du canal qui mord, la convergence 0/15 contre 9/15, et l'utilité
  émise qui cesse de dépasser le maximum natif.
* **Non-régression** — 54 tests offline de la famille 433 + `test_nc_priority_tiers_offline.py` ;
  gardes LIVE des consommateurs voisins du foyer partagé : `test_356_noncomparable_oracle_live.py`,
  `test_433_r4_r3_non_owner_playbooks_live.py`, `test_433_r3_r1_dsl_footprint_live.py`.
  Banque de cliquets jouée.
* **NON CONFRONTÉ** — `MasterOfTheTutelariesPlaybook` n'a **aucune** confrontation live ici, et
  c'est assumé : le re-pointage y est inerte (§2.2), donc un test live serait une tautologie. Le
  canal qui le confronterait si le régime devenait observable : un ennemi **multi-tuiles**, qui fait
  mordre les empreintes (`#419-r1-tr10-r2`) — pas l'adjacence.
