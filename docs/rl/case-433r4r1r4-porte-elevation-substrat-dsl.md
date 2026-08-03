# #433-r4-r1-r4 — la porte d'élévation du substrat DSL, branchée sur le canal du board

**FERMÉ.** `DslContext.elev_by_pos` se **dérive** désormais du `board` quand il n'est pas fourni
(`DslContext.__post_init__`), via le foyer unique `entities/pathfinding/board.py::elevations_by_pos`.
**17 tests offline** dont le rejeu du montage sur un board RÉEL (`MC1_67`), **4 mutations → 4 rouges**,
arbre restauré bit-exact, et **CONFRONTÉ LIVE par deux oracles indépendants** (§6) — dont le couple
divergence → convergence sur une cascade de dégât.

## 1. Le décompilé, relu — la porte et sa source

Le gate est **inconditionnel** et **il n'a pas d'état « élévation inconnue »**.

`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, verbatim :
l'élévation de la tuile SOURCE est lue **une seule fois à l'init** (`d__8+0x48` ←
`source→[0x20]→[0x18]`), celle du voisin par itération (`tile→[0x20]→[0x18]`), puis — **après** les
filtres terrain `IsTemporary` (`d__8+0x40`), `IsWalkable` (`+0x42`), `IsEmptyOrSteppable` (`+0x44`) :

```
iVar10 = this[0x48] - elev(voisin);
iVar4  = -iVar10; if (iVar4 < 0) iVar4 = iVar10;     // abs
if (iVar4 < 2) { yield voisin; }
```

`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(tile1, tile2)` (surcharge SCALAIRE) :

```
e1 = GetComponent<Elevation>(tile1)+0x18 ; e2 = GetComponent<Elevation>(tile2)+0x18
d  = abs(e2 - e1)
b  = (tile1 == tile2) ? 1 : ConnectivityComponent.IsNeighbour(conn(tile1), tile2)
return (d < 2) & b
```

— le court-circuit d'identité pose `b = 1` mais **ne saute pas** le `&` ; il tient parce que
`d = 0 < 2` (#433-r1 confirmé, pas contredit).

`IdunBattle.Entities.TileExtensions$$GetElevationDifference(tile, otherTile)` = `abs(e(other) − e(tile))`
et **LÈVE** si le composant manque. `$$GetElevation`, lui, rend `-1` sur une entité sans composant —
mais aucun des deux foyers de la porte ne passe par lui : ils déréférencent `+0x20` directement.

⇒ **L'« élévation inconnue » est une notion strictement PORT** (board bâti à la main, `boardGraph`
antérieur au capteur). D'où le **tri-état** ci-dessous, et non un `0` par défaut.

Troisième lecteur du même entier : `IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select`
— `otherTile = <sel@+0x18>.SelectTile(entities)` (SINGULIER), source = `<sel@+0x20>.SelectTiles`, garde
si `GetElevationDifference(tile, otherTile) <= this+0x28` (**maxDiff = 1** au call-site
`UnitsDirectlyBehind`). `<= 1` et `< 2` sont le même prédicat sur des entiers.

## 2. Le périmètre, MESURÉ (`probe_433r4r1r4_elevation_gate_perimeter.py`)

« Fermable en un seul geste » était une hypothèse. Le balayage AST la **rectifie** : ce n'est pas
`entities_from_state` seul, c'est **4 constructeurs sur 11**.

| constructeurs de `DslContext` | compte | canal |
|---|---|---|
| avec `board` **et** `elev_by_pos` explicite | 5 | déjà branché |
| avec `board`, **sans** `elev_by_pos` | **4** | **INERTE** — `runner/abilities/behaviours/context.py` (`entities_from_state`), `runner/abilities/loki/mv71.py` (face prédiction), `playbook/prediction/abilities.py` ×2 |
| sans `board` | 2 | sans objet (arbre purement numérique) |

**Lecteurs du canal dans le substrat DSL : exactement DEUX** —
`entities/selectors/tiles.py::FilterTilesIfCanAttackTargetTileFrom` (les deux bras) et
`entities/selectors/units.py::UnitsDirectlyBehind` (`TilesOnSameElevationSelector`). Les autres nœuds
d'adjacence du DSL (`IsAdjacent`, `IsCharging` dans `entities/triggers.py`) passent par
`services/battle_query.py::are_entities_adjacent(feet, feet, board)` → `targeting.are_tiles_adjacent`,
qui lit l'élévation **du board** : ils étaient **déjà gatés**. L'énoncé hérité « pour TOUS les nœuds
d'adjacence du substrat DSL runner » est donc **trop large** — le gisement réel est de 2 nœuds.

**Où la porte peut mordre** (entrées versionnées, couronne even-q, tuiles jouables) :
**685 boards sur 779** portent au moins une paire voisine à `|dElev| >= 2`. Sur `MC1_67` :
**18 paires sur 316** changent de verdict pour les DEUX primitives (`--step flips`). Un test sur board
plat serait vert pour la mauvaise raison.

## 3. Le fix — un canal, deux règles

**`entities/pathfinding/board.py`**

* `Board.elev_by_pos()` — mémoïsé, **OMET** toute tuile dont l'élévation n'est pas captée.
  ⚠ Ce n'est **pas** le 3ᵉ élément de `walk_maps_by_pos()` et les deux ne peuvent pas fusionner :
  celui-là rend `int(elevation or 0)` parce que le pathfinder a besoin d'une fonction **totale**.
  Coter `0` une élévation non mesurée **fabrique une donnée** et rendrait la porte **RESTRICTIVE** —
  un faux NÉGATIF d'adjacence supprime des actions légales, strictement pire que la dégradation
  permissive qu'on ferme.
* `elevations_by_pos(board)` — **tri-état** : `None` = pas de canal, jamais `{}` (qui se lirait comme
  une mesure). Accepte les deux formes de board portées (`Board`, ou tout objet exposant `by_coord` —
  `ctx.board` est duck-typé dans tout le DSL).

**`dsl/base.py` — `DslContext.__post_init__`** : `elev_by_pos` absent **et** `board` présent ⇒ dérivé.
Le brancher là plutôt qu'aux 4 call-sites est ce qui empêche le prochain constructeur de rouvrir le
trou en silence — même forme de dette que `TARGETING_OPTIONS`. `dataclasses.replace` (le `Filter`/
`Foreach`) le préserve ; une carte fournie explicitement n'est jamais écrasée.

**`runner/operations/spawn.py`** rejoint le foyer (il dérivait la même carte en ligne, mêmes clés
omises — substitution bit-identique).

Reste hors foyer, **nommé** : `entities/selectors/units.py::Unobscured` dérive sa propre carte depuis
`board.by_coord` avec `elevation` **par défaut 0** (résidu `#433-r4-r1-r4-r1`).

## 4. Ce que le fix change, observable — et il bascule DANS LES DEUX SENS

C'est le point qui interdit de lire ce correctif comme « on restreint » :

| bras natif | sens de la bascule | effet |
|---|---|---|
| `GetAdjacentUnits(tile, null, enemyOf, false).Count == 0` | **PLUS PERMISSIF** | un ennemi 2+ crans plus haut n'est pas un voisin natif ⇒ la tuile reste attaquable et le 1ᵉʳ bras la **GARDE** |
| `\|\| TileExtensions.IsAdjacentTo(tile, targetTile)` | **PLUS RESTRICTIF** | une tuile cible 2+ crans plus haut n'est plus adjacente ⇒ **plus de rattrapage** |
| `TilesOnSameElevation(maxDiff 1)` de `UnitsDirectlyBehind` | **PLUS RESTRICTIF** | un ennemi derrière la cible hors tolérance sort du pool de splash de `PlasmaCannonAbility` / `SuperchargeAbility` |

Un fix qui n'aurait fait que restreindre serait **faux**.

## 5. Validation

**OFFLINE — `tests/engine/test_433r4r1r4_elevation_gate_dsl_offline.py`, 17 passed.** Axes : le canal
(carte, omission d'une tuile non captée, tri-état, board duck-typé, mémoïsation) ; la dérivation
(`__post_init__`, absence de board, carte fournie non écrasée, `replace`) ; les deux bras de
`FilterTilesIfCanAttackTargetTileFrom` dans les deux sens ; l'identité qui survit à la porte ;
`UnitsDirectlyBehind` aux trois régimes (plat / hors tolérance / tolérance ±1) ; le câblage runner
(`entities_from_state`, verdict de `MV71._filter_can_attack_target_tile_from` qui bascule) ; et la
non-régression sur un board sans canal.

**Le montage rejoué sur un board RÉEL** — `MC1_67`, entrée versionnée, coordonnées `caster (0,0)`,
`target (1,2)` élévation 2, `behindHIGH (1,3)` élévation **4**, `behindFLAT (2,2)` élévation 2 :
le pool `UnitsDirectlyBehind` passe de `{10, 11}` à `{11}`.

**Contre-épreuve par MUTATION** (patch vérifié mordant, arbre restauré, sha256 bit-exact) :

| mutation | résultat |
|---|---|
| dérivation `__post_init__` retirée | rc 1 — **6 failed** / 10 passed |
| élévation absente cotée `0` au lieu d'être omise | rc 1 — 3 failed |
| canal absent → carte vide au lieu de `None` | rc 1 — 2 failed |
| tolérance `TilesOnSameElevation` `<= 1` → `== 0` | rc 1 — 1 failed |

**Régression, 215 passed** sur 17 fichiers offline touchant le substrat DSL / le runner, plus les
81 tests de la famille 433 et `test_units_directly_behind_offline.py`. **Banque de cliquets VERTE**
(35 cliquets).

**Non-régression des tests LIVE consommateurs, établie par LECTURE de leur montage** — aucun n'a
été modifié (et la confrontation §6 B les corrobore : sur un montage à `|dElev| <= 1`, comme le
leur, le port rend le même ensemble avant et après) :

* `test_plasma_cannon_live.py` et `test_plasma_cannon_lateral_live.py` **contraignent déjà** leur
  géométrie à `|elev(behind) − elev(target)| <= 1` (et `|elev(target) − elev(caster)| <= 1`) au moment
  de driver les positions : le pool est identique avant et après.
* `test_darkangels_lot1_live.py` compare son oracle **géométrique** `_behind()` au résultat **LIVE**
  (`assert set(live) == set([tgt] + bh)`). Cet assert est déjà l'oracle du gate natif : partout où il
  passe, `géométrique == gaté`, donc le port d'après vaut le port d'avant. S'il venait à rougir, la
  cause serait le montage (oracle élévation-aveugle), pas le fix.

## 6. CONFRONTATION LIVE — deux oracles indépendants

`tests/engine/runner/test_433r4r1r4_elevation_gate_live.py`, **1 passed**, board `MC1_67`, runner
isolé disposé au `finally`. Le quadruplet est **dérivé du `boardGraph`**, pas hardcodé.

### (A) La porte elle-même, lue sur la liste d'adjacence NATIVE — le sens PERMISSIF

Le `boardGraph` est capté par `BattleQuery$$GetAdjacentTiles` → `TileQuery$$IterateAdjacentTiles` :
la liste rendue a **déjà traversé la porte**. Mesuré live sur `MC1_67` (63 tuiles) :

| arêtes de la couronne hex | compte |
|---|---|
| présentes dans la liste native | **298** |
| **absentes** de la liste native | **18** — dont `\|dElev\| >= 2` : **18**, autres : **0** |
| présentes dans la liste native hors couronne | **0** |

Le natif exclut donc **exactement** les arêtes que la porte prédit, et rien d'autre — le chiffre
`18 / 316` est identique à la mesure offline. C'est le **sens permissif** confronté : ces voisins-là
ne sont pas itérés, donc `GetAdjacentUnits(tile, null, enemyOf, false).Count` ne les compte pas, et
le PREMIER bras de `FilterTilesIfCanAttackTargetTileFrom` garde la tuile. (Le bras applicatif
lui-même reste hors d'atteinte — §7, `#433-r4-r1-r4-r4`.) Sur ce board, `0` arête stockée hors
couronne : le quirk de connectivité du résidu `-r2` n'y mord pas.

### (B) Le sens RESTRICTIF, sur une cascade de dégât — oracle à 1 bit

`darkaTerminator` (deep-strike, on le fait atterrir), `PlasmaCannon` 1150, splash
`PickRandomly(UnitsDirectlyBehind(caster, target), 2)`. Positions **drivées** :

| rôle | tuile | élévation | `\|dElev\|` vs cible |
|---|---|---|---|
| caster `u85` | `(1,0)` | 3 | — |
| cible `u77` | `(1,2)` | 2 | — |
| derrière HAUT `u79` | `(1,3)` | **4** | **2** ⇒ hors tolérance |
| derrière PLAT `u81` | `(2,2)` | 2 | 0 ⇒ dans la tolérance |

Trois lectures du **même** état :

| lecture | `UnitsDirectlyBehind` / cibles frappées | verdict |
|---|---|---|
| **LIVE (natif)** | frappe `{u77, u81}`, 3 coups chacun — `u79` **jamais touché** | référence |
| **port AVEC le canal** (livré) | `[u81]` | **ACCORD** |
| **port canal NEUTRALISÉ** (`elev_by_pos = {}`, l'état d'avant) | `[u79, u81]` | **DÉSACCORD** |

C'est le couple exigé : **divergent avant, convergent après**, sur le même montage. La troisième
lecture est dans le test — sans elle, l'accord live/port ne prouverait pas que la porte mord.

**684 boards versionnés sur 779** admettent ce quadruplet : ce n'est pas un cas de bord.

## 7. Résidus NOMMÉS

* **`#433-r4-r1-r4-r1` — `Unobscured` dérive sa propre carte avec `elevation` par défaut `0`**
  (`entities/selectors/units.py`), au lieu du foyer `elevations_by_pos`. Sans effet sur un board dont
  toutes les tuiles portent leur élévation ; sur un board partiellement capté, il **fabrique** un
  niveau `0` là où le foyer omettrait. Non convergé ici : `is_target_tile_obscured` a son propre
  contrat sur les clés absentes, à relire avant de toucher.
* **`#433-r4-r1-r4-r2` — `is_adjacent` reste géométrique + porte, là où le natif itère la liste
  STOCKÉE.** `TileQuery$$IterateAdjacentTiles` parcourt le `ConnectivityComponent`, pas la couronne
  hex : mesuré sur `C1_74` (case-433-r3), les deux vues divergent sur **74 arêtes dirigées**, dont
  **70** que la porte explique désormais — et **4** que non (les deux `Bridge` que le
  `ConnectivityComponent` ne relie pas à leur voisin de niveau). Ces 4 restent un écart PERMISSIF du
  port. Le fermer voudrait dire lire `board.neighbours_native` dans `is_adjacent`, ce qui expose les
  ~18 arêtes one-way de la capture : à instruire, pas à improviser.
* **`#433-r4-r1-r4-r3` — la face DÉCISION n'a pas été re-mesurée.** `AiDecisionContext.elev_by_pos`
  est peuplé depuis `tileMeta` et les playbooks passent déjà `ctx.elev_by_pos` ; le balayage n'a
  trouvé aucun lecteur DSL inerte de ce côté. Aucune anomalie constatée, aucun test décision rejoué.
* **`#433-r4-r1-r4-r4` — le BRAS APPLICATIF permissif reste NON CONFRONTÉ, pour raison
  STRUCTURELLE.** La porte, elle, l'est (§6 A). Ce qui ne l'est pas, c'est le premier bras de
  `FilterTilesIfCanAttackTargetTileFrom` **en tant que branche exécutée**, et ses deux seuls
  consommateurs l'interdisent : le repli de `MV71SniperDroneSquadAttackAbility$$PickTile` n'est
  atteint que si **aucune** des ~60 tuiles libres à distance 1..4 de la cible ne passe `IsFreeTile`
  (hors d'atteinte d'un roster), et `WallOfMirrorsAbility$$GetPossibleTiles` (1186) n'est pas portée
  — porteurs npc + summon sans summoner, donc greffe requise. L'oracle (A) couvre la **primitive**
  dont ce bras dépend, pas la branche.
