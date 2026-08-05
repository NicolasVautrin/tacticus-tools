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

## 4. La garde étendue, et pourquoi chaque étape neuve

`probe_433r4r1r4r2_neigh_channel_wired.py` (dans la banque) porte **quatre étapes**. Les deux
premières cotent la **présence** du canal, les deux dernières sa **consommation** — parce qu'un
canal présent et non consommé a l'allure d'un mirror branché et le comportement d'avant.

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
La seule verte est artificielle — géométrie nue **avec la dérivation laissée morte** au-dessus.
C'est elle qu'ont fermée les deux étapes suivantes (**#433-r4-r1-r4-r2-r1-r1**).

**Étape 3 — la DÉRIVATION LAISSÉE MORTE.** Trois formes, toutes des no-op **démontrables**, aucune
allowlist : (a) un nom **teinté** par la valeur du canal — le teint se propage par point fixe —
assigné et jamais relu ; (b) un appel à une fonction **PURE** du foyer (les CIBLES + `neigh_map`)
dont la valeur est jetée — même **résolution d'import** qu'à l'étape 1, sans quoi un
`update_charging(...)` en statement nu, qui est un **mutateur ECS légitime**, y entrerait ;
(c) un **paramètre** du canal jamais lu. Le filtre d'entrée de cette étape est le seul à compter les
**paramètres** : un paramètre inerte n'apparaît comme `ast.Name` nulle part — c'est sa définition —
donc le filtre par usage des étapes 2 et 4 la rendrait structurellement inatteignable.

**Étape 4 — la GÉOMÉTRIE qui décide MALGRÉ le canal**, complément exact de l'étape 2 sur le même
gisement (mirror déclaré **avec** canal, là où l'étape 2 garde le mirror **sans**). Le critère est un
critère de **FLOT** : on propage « le canal est établi indisponible ici », un test qui parle du canal
le retourne selon sa polarité, et la sortie d'un `if` **fusionne en ET** les branches qui ne
terminent pas. Ces deux règles — fusion en ET, une branche qui **termine** ne participant pas —
sont exactement ce qui sépare les deux replis légitimes du vice : `is_adjacent` met sa géométrie sous
`if neigh is None` ; `services.battle_query.are_tiles_adjacent` la met **après** un bloc canal dont
toutes les feuilles retournent. Une garde inerte (`if neigh_by_pos is None: pass`) ou un canal
consulté puis ignoré, eux, laissent la géométrie décider sur un chemin où le canal répondait.

Le groupe de noms qui « parle du canal » se dérive aussi : valeurs du canal, **porteurs** (les
arguments d'une dérivation) et ce qui en dérive. Il est **volontairement large** — il ne sert qu'à
RECONNAÎTRE un test, donc l'élargir ne peut que retenir le cliquet. L'étape 3, elle, prend le groupe
**strict** : sinon le moindre code mort dérivé d'un `board` deviendrait un vice.

**Le gisement, mesuré le 2026-08-05** (`--inventaire`) : **99** fonctions d'`engine/` touchent le
canal, **0** dérivation morte ; **2** mirrors déclarés portent canal + géométrie
(`is_adjacent`, `services.battle_query.are_tiles_adjacent`), **0** géométrie non gardée. Ce zéro est
un **cliquet**, pas un acquis. **Contre-épreuve : 25 tests, 12 mutations** — 6 synthétiques isolant
chaque forme, 6 sur le **vrai** code (`battle_query.py`, `runner/components.py`,
`services/battle_query.py`), chacune vérifiée **mordante** — et **8 anti-faux-positifs**, qui sont
ici le vrai risque. Coût : **+2,5 s** (e3 1,7 + e4 0,8) sur ~8 s.

**Ce que la mesure NE couvre PAS**, nommé : un store d'**attribut** (`self._neigh = …`) n'est pas
coté (sa lecture peut vivre hors périmètre) ; le critère porte sur le **nom**, donc une réassignation
masque un store mort ; `elev_by_pos` n'est pas un canal de l'étape 3 (la porte d'élévation est
l'objet de l'étape 1) ; boucles et `try` ne propagent pas leur état de sortie ; un test de forme non
reconnue vaut **crédit** ; et l'étape 4 tient **toute** `distance ∼ 1` d'un mirror déclaré pour une
décision d'adjacence — vrai des deux fonctions du gisement, à re-questionner si une troisième y
entre pour un autre usage. Et surtout la liste `NATIFS_LISTE_STOCKEE` est **littérale** — §6.

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

* ~~**`#433-r4-r1-r4-r2-r1-r1`**~~ **FERMÉ** par les étapes 3 et 4 (§4). Le critère de flot redouté
  ne produit **pas** de faux positif sur les deux replis légitimes : ce n'était pas la garde par une
  condition sur le canal qui manquait, mais la **fusion en ET** à la sortie d'un `if` et l'exclusion
  des branches qui **terminent** — `are_tiles_adjacent` ne garde rien syntaxiquement, son bloc canal
  ne **tombe** simplement jamais dans la géométrie. Prouvé dans les deux sens par
  `test_e4_bloc_canal_qui_ne_termine_plus`, où le `return` retiré est la seule différence.

* **`#433-r4-r1-r4-r2-r1-r1-r1` — le critère « docstring » a un gisement qu'il ne voit pas, et il y
  a un VICE dedans.** Les étapes 2 et 4 n'entrent que sur `NATIFS_LISTE_STOCKEE`, une liste
  **littérale de 8 noms**. `AreEntitiesAdjacent` n'y est pas, alors que la chaîne est LUE
  (`BattleQuery$$AreEntitiesAdjacent` → `MovementUtil$$AreTilesAdjacent` →
  `ConnectivityComponent$$IsNeighbour` = `this[+0x10].Contains`, §1) — pas plus qu'`AreUnitsInMelee`,
  `GetFreeAdjacentTiles` ou les nœuds DSL `AdjacentTiles`/`AdjacentUnits`. `--inventaire` rend
  **3** fonctions hors verdict (mesure du 2026-08-05), dont **une tranchée à la RE** :

  * **VICE RÉEL** — `engine/runner/abilities/orks.py:509`, dans `get_dynamic_invalid_target_reason`
    (mirror de `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetDynamicInvalidTargetReason`).
    Le natif décide `isAdjacent` par le **slot 0x61** d'`IBattleQuery` (= `AreEntitiesAdjacent`,
    décompile relu le 2026-08-05 : `cVar6 = FUN_1800051d0(0x61, …, casterTiles, target)`) ; le port
    écrit `hexgeo.distance(cp, tp) == 1`. **Trois** écarts, tous permissifs : ni liste stockée, ni
    porte d'élévation, et le natif compare les **empreintes** (`casterTiles` est une `IList`) là où
    le port compare deux tuiles principales. Le canal est pourtant dans la **même fonction**
    (`board.neighbours_native(ttile)`, l. 519) et le foyer branché existe
    (`services.battle_query.are_entities_adjacent`, `runner.abilities.targeting`). NON CORRIGÉ ici,
    par mandat.
  * **NON TRANCHÉS** — `playbook/noncomparable/aberrant_hypermorph.py:50` et
    `master_of_the_tutelaries.py:73`, tous deux `hexgeo.distance(T, ST) != 1` pour « spawn adjacent à
    la position T », le canal branché deux lignes plus bas. `AberrantHypermorphPlaybook$$EvaluateNonComparable`
    (relu) ne filtre **pas** par distance : il énumère `GetEligibleTargetsSelectable`, donc la
    contrainte d'adjacence vient du **sélecteur DSL** de l'ability. Trancher demande de lire ce
    sélecteur — s'il passe par `AdjacentTiles`, c'est le même vice.

  Élargir `NATIFS_LISTE_STOCKEE` **armerait le cliquet sur ce rouge**, donc l'ordre est : corriger
  d'abord, élargir ensuite. C'est aussi le voisin de `#433-r4-r1-r4-r2-r2`, resté ouvert pour la même
  raison de fond — le gisement se définit par une **liste de noms natifs**, pas par une dérivation.
  Le constat est **figé par un test** (`test_le_critere_mord_sur_un_VICE_REEL_…`) : liste élargie en
  mémoire, l'étape 4 désigne `orks.py:509` **et elle seule** — c'est la preuve que le critère de flot
  mord sur un vice **du dépôt**, pas seulement sur des mutations fabriquées. Quand la tranche aura
  corrigé orks, ce test rougira : c'est alors qu'on élargit la liste pour de bon.
* **`#433-r4-r1-r4-r2-r2`** (ouvert ailleurs) reste ouvert : `playbook/noncomparable/
  heroic_fusillade.py` appelle `count_adjacent` **sans** élévation ni voisinage, donc hors gisement
  de l'étape 1 (qui garde le COUPLE) et de l'étape 2 (il ne cite pas de natif à liste stockée dans
  la fonction concernée). À trancher sur son propre décompilé.

## 7. Reproduction

    python -m pytest tests/engine/test_433r4r1r4r2r1_foyers_voisins_offline.py
    python -m pytest tests/engine/test_433r4r1r4r2r1r1_derivation_morte_offline.py
    python -m pytest tests/engine/runner/test_433r4r1r4r2r1_update_charging_bridge_live.py
    python probe_433r4r1r4r2r1_solde_par_foyer.py [--board C3_14]
    python probe_433r4r1r4r2_neigh_channel_wired.py [--inventaire]
