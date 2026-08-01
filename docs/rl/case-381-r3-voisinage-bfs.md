# case-381-r3 — le voisinage du BFS est un slot VIRTUEL, pas un mode de `Board`

Ferme le résidu `#381-r3` (ouvert par `case-381-r1` §5, affiné par `case-403`). **La lecture
fondatrice était fausse sur son axe** : le champ `neighbours` du `boardGraph` n'est pas incomplet,
et il n'y avait rien à corriger au CAPTEUR.

## 1. Ce que le décompilé dit — deux corps, deux sources

`IdunBattle.Entities.Pathfinding.BasePathfinder$$GetValidNeighbours`
(`u003CGetValidNeighboursu003Ed__18$$MoveNext`) concatène **trois** énumérateurs, et le premier est
un appel de VTABLE (`vslot 0x238`). Les seules XREFS de `BasePathfinder$$AddNeighbours` et de
`FlyPathfinder$$AddNeighbours` sont des entrées de vtable : c'est un **override réel**.

| corps | ce qu'il énumère | consommateur |
|---|---|---|
| `BasePathfinder$$AddNeighbours` (`d__19`) | la `List` du `ConnectivityComponent` de la tuile (`connectivity+0x10`), chaque id résolu sur l'état | **MARCHE** (et tout ce qui dérive de `BasePathfinder` sans override) |
| `FlyPathfinder$$AddNeighbours` (`d__7`) | la requête de tuiles au **rayon 1**, centre écarté | **VOL** |

Le port n'avait qu'une source, `board.neighbours()`, choisie par le `adjacency=` de l'appelant :
`evenq` dans tous les probes, `native_sym` dans `playbook/scene.py` (la PRODUCTION). Un mode global
se trompait donc **forcément d'un côté**.

## 2. La mesure qui tranche — `C1_74`/3811, `overrideRange` 5, oracle `aiMovableTiles`

| vue du graphe | `tauAunShi` (walk) | `bloodIntercessor` (fly) |
|---|---|---|
| natif | **34** | **46** |
| `evenq` (l'état d'avant, côté probes) | 36 — en trop (4,2) et (5,3) | 46 |
| `native_sym` (l'état d'avant, côté production) | 34 | 45 — manque (3,1) |
| **livré** (marche = stockée, vol = géométrie) | **34** | **46** |

Les deux vues divergent sur **74 arêtes dirigées**, toutes dans le sens géométrie \ stockée
(`stockée \ géométrie = 0`, aucune arête one-way). Ventilées : **70** à `|Δelev| >= 2` — sans effet,
`WalkPathfinder$$IsValidPathNode` les refuse de toute façon — et **4** à `|Δelev| = 1`, qui sont les
seules à séparer la marche : le `ConnectivityComponent` ne relie pas les deux `Bridge` à leur voisin
de même niveau, `(1,5)`↔`(2,4)` et `(4,4)`↔`(5,5)`.

**Scénario crafté** (`probe_381r3_bridge_edge.py`) : une unité DRIVÉE sur la charnière `(1,5)`,
mesurée à `overrideRange` **1** — l'écart se réduit à cette unique arête. Port **1** == natif **1** ;
la vue géométrie rend **2**, la tuile en trop étant exactement `(2,4)`.

## 3. Pourquoi « le champ capté est incomplet » était faux

`case-381-r1` §5 concluait que remplacer une vue par l'autre donnait 32 tuiles pour 34 au natif,
donc que le capteur amputait le graphe. Re-mesuré sur `78e92ff7` : le pool devient **34/34**. Le
déficit venait d'avoir basculé le `Board` GLOBALEMENT, ce qui casse le VOL (46 → 45) — pas d'une
perte du capteur.

Le capteur passe bien par une porte `|Δelev| < 2` **INCONDITIONNELLE**
(`IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`, déjà documentée dans `rpc-board.ts`),
là où `IsValidPathNode` la saute quand les DEUX tuiles sont des téléporteurs. Ce n'est pas une perte
observable ici : la paire de téléporteurs n'est de toute façon pas dans le
`ConnectivityComponent` — elle est ajoutée à part, par `BasePathfinder$$AddTeleportationTiles`.

## 4. Ce que le port fait maintenant

`walk_pathfinder.get_reachable_levels` prend un paramètre `neighbours`, second slot virtuel à côté
de l'arête `edge` ; défaut = `Board.neighbours_native`. `fly_pathfinder.get_movable_positions` passe
`Board.neighbours_geometric` (nouveau — la couronne even-q recalculée, indépendante du mode).
`ignore_terrain_pathfinder` lit `neighbours_native` : `IgnoreTerrainPathfinder` dérive de
`BasePathfinder` (`classes.tsv`) et n'override pas `AddNeighbours`. Le `adjacency=` du `Board` ne
gouverne plus aucun pathfinder.

Corollaire trouvé en mesurant : `Board.neighbours_native` confondait champ **ABSENT** (board
fabriqué à la main → repli légitime sur `neighbours()`) et champ **VIDE**, et inventait six voisins
sur les tuiles en creux — sur `C1_74`, les deux `Water` d'élévation 1 entourées de 3 et 4, que la
porte du capteur vide entièrement. Le test est désormais `raw is None`.

`IgnoreTerrainPathfinder` portait le même défaut, **mesuré** contre `pathDistToEnemies` (qui appelle
`IPathfinders.GetPath(1, …)`) sur `C1_74` : 180 distances confrontées, **11** écarts sur la
géométrie (4 unités sur 10), **0** sur la liste stockée.

## 5. Confrontation

`probe_381r1_movable_tiles_pool.py` (pool nu contre `aiMovableTiles`, égalité EXACTE attendue) :

| board | WALK avant | WALK après | VOL |
|---|---|---|---|
| `C1_74` | 8/9 | **9/9** | 1/1 |
| `MC1_67` | 9/9 | **9/9** | 1/1 |
| `C2_26` | 9/9 | **9/9** | 1/1 |
| `PVP_desert_04` | 9/9 | **9/9** | 1/1 |

Gardes adversariales, chacune ne frappant QUE sa branche — la preuve croisée que les deux sources
sont distinctes et chacune juste pour la sienne :

| mutation | ce qu'elle défait | résultat sur `C1_74` |
|---|---|---|
| `geo-walk` | la marche relit la géométrie | WALK **8/9** (`tauAunShi` 36 pour 34), VOL 1/1 intact |
| `stored-fly` | le vol relit la liste stockée | WALK 9/9 intact, VOL **0/1** (`bloodIntercessor` 45 pour 46) |

Gardes committées : `tests/engine/entities/pathfinding/test_381r3_neighbour_source_{live,offline}.py`
(3 live auto-discriminants + 7 offline). `test_381r5_special_movement_live` perd son exemption
`walk_strict=False` sur `C1_74` — c'est un CLIQUET : il rougit si la marche repasse à la géométrie.

## 6. Ce qui reste

* **`BasePathfinder$$AddTeleportationTiles`** — non porté. Si la tuile courante est une tuile de
  téléportation (`ConnectivityComponent+0x18 != 0`, cf.
  `IdunBattle.Entities.TileExtensions$$IsTeleportationTile`), sa jumelle devient voisine, sauf si un
  ENNEMI l'occupe. Le `boardGraph` ne publie pas ce champ → ni dans `neighbours_native`, ni
  dérivable. Dégradation RESTRICTIVE, **bornée** : `stockée \ géométrie = 0` sur `C1_74`, `MC1_67`,
  `C2_26` et `PVP_desert_04`, donc aucun de ces boards ne porte de téléporteur. Le capteur devrait
  publier `teleportTileId` par tuile (reinject requis).
* **`BasePathfinder$$AddShadewalkerTiles`** — non porté. Sous trait `0x23` ET effet `0x3a` sur la
  tuile de départ, TOUTE tuile du board portant ce même effet devient voisine (`GetAllTiles`).
* **L'exemption d'élévation du couple téléporteur** (`IsValidPathNode` saute `|Δelev| <= 1` quand les
  deux tuiles sont des téléporteurs) : sans objet tant que le champ ci-dessus n'est pas publié.
* **L'ORDRE** de `neighbours_geometric` est trié par id, là où le natif suit l'ordre de la requête
  de tuiles. Non observable ici (le BFS accumule un `set`) ; le deviendrait pour un consommateur qui
  lirait le PREMIER voisin.
