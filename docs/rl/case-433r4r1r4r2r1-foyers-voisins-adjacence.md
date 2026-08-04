# #433-r4-r1-r4-r2-r1 — quatre foyers voisins, **trois** natifs, **deux** sens

**FERMÉ.** Les quatre foyers que #433-r4-r1-r4-r2 avait laissés en géométrie ne partagent pas le
vice : ils ne mirrorent pas le même natif. Deux sont **branchés** sur la liste stockée, deux sont
**géométriques par lecture** — et y portaient une porte d'élévation **en trop**. Chaque foyer
bascule dans le sens que sa lecture prescrit, et **seulement** dans ce sens (§3).

| foyer | natif | verdict | rayon |
|---|---|---|---|
| `battle_query.is_charging` | `BattleQuery$$IsCharging` → `MovementUtil$$AreTilesAdjacent` → `ConnectivityComponent$$IsNeighbour` | **BRANCHÉ** | 2 ponts → 9 consommateurs |
| `battle_query.newly_adjacent_ids` + son jumeau ECS `runner.components.update_charging` | `MoveUnitOperation$$UpdateCharging` → `BattleQuery$$GetAdjacentUnits` → `IterateAdjacentTiles` | **BRANCHÉ** (2 étages manquants) | 1 + 1 |
| `battle_query.in_arc` | `BasePlaybook$$GetEligibleTargetsSelectable` → … → `BattleQuery$$GetTilesAtDistance` | **GÉOMÉTRIQUE PUR** — rien à brancher, porte retirée | 2 (dont 1 mort) |
| `battle_query.count_enemies_in_arc` | idem | idem | **0 appelant** |

## 1. Les trois lectures

**`ConnectivityComponent$$IsNeighbour`** vaut `this[+0x10].Contains(<entity id de tile2>)` — la
**même** `List<int>` qu'énumère `IterateAdjacentTiles`. `MovementUtil$$AreTilesAdjacent` la joint à
la porte par un ET (`iVar7 < 2 & bVar3`), le court-circuit d'identité restant devant. Donc
`IsCharging` lit bien la liste stockée : le canal s'y propage, et rejouer la porte dessus est
idempotent (le canal la porte déjà).

**`GetAdjacentUnits(from, …)`** est `IterateAdjacentTiles(from, …)` puis `GetUnitsOnTiles(…)`. Le
port de `UpdateCharging` faisait `hexgeo.distance == 1` **nu** : ni l'énumération, ni la porte.
**Deux** étages manquants, tous deux permissifs, sur les **deux** faces (prédiction + ECS).

**`GetTilesAtDistance(centerTile, distance, …)`** filtre le disque de `GetSurroundingTiles` par
`PositionComponent$$Distance(t, centre) == distance` — une distance hexagonale sur un disque cube.
**Aucun `ConnectivityComponent`, aucun `|dElev| < 2`** sur la chaîne d'éligibilité. Y brancher le
canal FABRIQUERAIT une divergence ; et la porte d'élévation qu'`in_arc` portait au ring-1 était un
**fork de port** contre `eligible_targets_count`, qui ne l'a jamais eue et le disait avec son
datapoint live (case-49x, `C1_25` : ennemi adjacent à `|dElev| = 2`, le natif génère quand même une
action). Porte retirée, **avec son paramètre** — un paramètre accepté mais non lu se refait passer
un jour pour un canal actif.

⚠ `dist 0` : hors régime, et le natif n'y répond **pas** par la distance —
`TargetingQuery$$GetUnitsInRange` traite `range == 0` à part (`{caster}` ou vide selon le bit 15 des
options), jamais le disque.

## 2. Le rayon, foyer par foyer (balayage AST de `git ls-files *.py`, 2026-08-04)

`is_charging` : **2** call-sites — `damage_model.battle_query_is_charging` (COMBAT, qui ne passait
**ni** élévation **ni** voisinage) et `_shared._prediction_is_charging` (PRÉDICTION). En aval :
3 + 6 consommateurs. `newly_adjacent_ids` : **1**. `update_charging` : **1**. `in_arc` : **2**
(`count_enemies_in_arc`, `enemies_in_arc`). `count_enemies_in_arc` : **0**. `enemies_in_arc` : **1**
(le fallback offline de `gauntlets_target`, dont la branche native lit déjà le canal).

**Le canal se DÉRIVE**, jamais ne se pose au call-site : `Scene.neigh_by_pos` côté prédiction,
`state.board` côté combat. `adjacent_neigh_by_pos` est désormais **mémoïsé** sur l'instance (le
graphe est statique — lu) : les deux appelants combat sont sur des chemins chauds (un appel par pas,
un par coup).

**Trois demi-branchements PRÉEXISTANTS** trouvés au passage, invisibles à l'ancienne garde parce
qu'ils appellent en **nom nu** ou sous **alias** : `playbook/noncomparable/_base.py`,
`utilities/ramming_speed.py`, `runner/operations/spawn.py`. Plus `adjacent_addable_count`, branché
en **NO-OP démontrable** (branche native : `p` sort déjà du canal ; branche fallback : `neigh` est
la couronne).

## 3. Le solde, ventilé PAR SENS et PAR FOYER

`probe_433r4r1r4r2r1_solde_par_foyer.py`, les 4 boards de #433-r4-r1-r4-r2 (comparabilité).
FERMÉ = permissif fermé (avant VRAI / après FAUX) · OUVERT = restrictif ouvert.

| foyer | `C1_74` | `C3_14` | `MC1_67` | `C6_25` | total |
|---|---|---|---|---|---|
| `is_charging` | 4 / 0 | 38 / 0 | 0 / 0 | 0 / 0 | **42 / 0** |
| `newly_adjacent_ids` | 74 / 0 | 116 / 0 | 18 / 0 | 0 / 0 | **208 / 0** |
| ├ étage énumération | 4 / 0 | 38 / 0 | 0 / 0 | 0 / 0 | 42 / 0 |
| └ étage élévation | 70 / 0 | 78 / 0 | 18 / 0 | 0 / 0 | 166 / 0 |
| `in_arc` | 0 / 70 | 0 / 78 | 0 / 18 | 0 / 0 | **0 / 166** |

Trois faits que la ventilation seule rend lisibles : le solde d'`is_charging` **reproduit** celui
d'`is_adjacent` (4 et 38, #433-r4-r1-r4-r2) — même substrat ; la décomposition de
`newly_adjacent_ids` est **additive exacte** (42 + 166 = 208), donc chaque étage est mesuré
séparément ; et les **166** d'`in_arc` sont **exactement** l'étage élévation de
`newly_adjacent_ids`, dans l'autre sens — la même porte, comptée une fois là où elle manquait et
une fois là où elle était en trop.

**Aucun solde négatif nulle part.** ⚠ Le gisement reste chiffré sur 4 boards (résidu
#433-r4-r1-r4-r2-r3, toujours ouvert) : le format `data/boards/` ne porte **pas** la connectivité,
qui vient du `boardGraph` capté live — un balayage offline des 779 exigerait de porter
`InitializeConnectivityOperation$$Execute` depuis `TileId`/`Rotation`.

## 4. La garde étendue, et pourquoi une seconde étape

`probe_433r4r1r4r2_neigh_channel_wired.py` (dans la banque) passe à **deux étapes**.

**Étape 1** — l'invariant de couple, mais la détection **RÉSOUT l'import** au lieu de comparer des
noms. Un `bq.is_adjacent(...)` était vu ; ni le nom nu, ni l'alias — or la face prédiction n'importe
**que** sous alias, et les foyers de `battle_query.py` s'appellent entre eux en nom nu. Comparer les
seuls noms produit l'erreur **symétrique** : `services/movement_query.py` définit son propre
`is_adjacent(board, a, b)` et `services/battle_query.py` son propre `are_entities_adjacent(a, b,
board)` — homonymes dont le 3ᵉ paramètre n'est pas `elev_by_pos`. Mesuré : **12** rouges avec la
détection naïve, dont **9 faux positifs** ; **3** vrais après résolution.

**Étape 2** — pas de **géométrie nue** dans un mirror **déclaré** du substrat stocké. L'étape 1 est
structurellement aveugle au vice qui a rouvert ce résidu : `newly_adjacent_ids` et `update_charging`
ne passaient **ni** l'un **ni** l'autre canal, donc étaient **hors gisement**. Le critère est dérivé
du contenu (#440) et conjoint : la fonction **cite** un natif à liste stockée, son corps **compare**
une distance hex à 1, et il **n'utilise** aucun canal. Les trois ensemble sont exactement le vice ;
`is_adjacent` porte les deux premiers et c'est son repli documenté, le troisième l'en sort.

⚠ **Le critère porte sur l'USAGE, pas sur la disponibilité** — et c'est la contre-épreuve qui l'a
imposé : coter la **signature** laissait passer la mutation qui remettait `newly_adjacent_ids` en
géométrie nue (ses paramètres restaient déclarés). Un paramètre non lu ne branche rien.

**Contre-épreuve (9 mutations, patch vérifié mordant, arbre restauré bit-exact) : 8 rougissent.**
La seule verte est artificielle — géométrie nue **avec la dérivation laissée morte** au-dessus ;
la mutation complète, elle, rougit. Résidu **#433-r4-r1-r4-r2-r1-r1** ci-dessous.

## 5. Validation

**OFFLINE — `test_433r4r1r4r2r1_foyers_voisins_offline.py`, 23 passed.** Axes : montage
discriminant, les deux étages séparément, le delta d'`UpdateCharging`, l'accord des DEUX faces, le
tri-état **par clé** (dict vide ≠ isolement), la dérivation depuis `Scene`/`state.board`, la
géométrie pure d'`in_arc` et son accord **total** avec `eligible_targets_count`, la mémoïsation et
sa tolérance à un board figé. **Contre-épreuve : 10 mutations, 10 rouges**, arbre restauré
bit-exact.

**LIVE — l'oracle est INDÉPENDANT du canal** :
`tests/engine/runner/test_433r4r1r4r2r1_update_charging_bridge_live.py`, **6 passed** (`C3_14`,
arête dérivée du board). L'oracle est `combatSnapshot.units[].chargedUnitIds`
(= `UnitComponent+0x190`), un **état ECS** écrit par `UpdateCharging` : il ne lit aucun champ de
`boardGraph`. C'est aussi le **seul** point d'observation direct de ce natif — son unique lecteur
(`BattleQuery$$IsCharging`) re-teste l'adjacence sur le même substrat, donc rendrait FAUX par son
**premier** terme quel que soit le contenu de la liste : le contenu est inobservable par le dégât.

| lecture | verdict |
|---|---|
| **NATIF** | charge le TÉMOIN (voisin réel), **jamais** le FANTÔME (voisin géométrique hors liste) |
| **port AVEC canal** | `{témoin}` — **ACCORD** |
| **port SANS canal** | `{témoin, fantôme}` — **DÉSACCORD** |

Un cran vérifie que la liste était **vide avant le pas** (sinon le contenu final ne serait pas
imputable au pas mesuré) et un autre que la porte d'élévation n'explique **pas** l'écart.

**Non-régression** : 54 offline (substrat #606, identité #433-r1, empreinte DSL, tiles-moved) et
**29 live** sur 4 fichiers (`ischarging_extra_damage` 7, `ischarging_saga_crit` 8,
`ischarging_unstoppable_ferocity` 10, `adjacent_tiles_bridge` 4).

**NON couvert, nommé** : (a) le comportement d'`in_arc` sur `dist 0` — hors régime, le natif y
répond par un flag et non par la distance ; (b) `count_enemies_in_arc` n'a **aucun** appelant, donc
son changement n'est gardé que par le test offline ; (c) l'aval — de combien une utilité de playbook
bouge (résidu #433-r4-r1-r4-r2-r4, mesuré en parallèle) ; (d) les 775 boards non mesurés (§3).

## 6. Résidus NOMMÉS

* **`#433-r4-r1-r4-r2-r1-r1` — la garde ne voit pas la « dérivation laissée morte ».** Une fonction
  qui dérive le canal puis ne s'en sert pas (variable calculée, jamais lue) passe l'étape 2 : le
  critère lit les noms **utilisés** dans le corps, pas le lien syntaxique entre le canal et la
  décision d'adjacence. La forme complète du vice, elle, rougit. Fermer ce trou demande un critère
  de flot (la comparaison de distance doit être **gardée** par une condition sur le canal), qui
  produirait des faux positifs sur les deux replis légitimes (`is_adjacent`,
  `services.battle_query.are_tiles_adjacent`) — arbitrage non tranché.
* **`#433-r4-r1-r4-r2-r2`** (ouvert ailleurs) reste ouvert : `playbook/noncomparable/
  heroic_fusillade.py` appelle `count_adjacent` **sans** élévation ni voisinage, donc hors gisement
  de l'étape 1 (qui garde le COUPLE) et de l'étape 2 (il ne cite pas de natif à liste stockée dans
  la fonction concernée). À trancher sur son propre décompilé.

## 7. Reproduction

    python -m pytest tests/engine/test_433r4r1r4r2r1_foyers_voisins_offline.py
    python -m pytest tests/engine/runner/test_433r4r1r4r2r1_update_charging_bridge_live.py
    python probe_433r4r1r4r2r1_solde_par_foyer.py [--board C3_14]
    python probe_433r4r1r4r2_neigh_channel_wired.py
