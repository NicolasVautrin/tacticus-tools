# case-448-r1-r1-r1 — la branche VOLANTE de `_movement_steps`, confrontée

`#448-r1-r1-r1`. #448-r1-r1 avait tranché le seuil de `1134 FullThrottle` en mesurant trois bras
— **tous des marcheurs**. La branche volante du ternaire d'`Execute` était portée d'après le
décompilé et **jamais exercée**. Elle l'est désormais, et elle est **juste**.

---

## 1. Le natif, relu

`IdunBattle.Operations.MoveUnitOperation$$Execute`, au site de fin de mouvement :

    movementSteps = IsLikeFlying(unit, options)
                      ? battleQuery.<slot itf 0x6c>(path.First(), path.Last())
                      : path.Count

`path` est le **8ᵉ out-param** de `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths`
(`connectedPath`, le 9ᵉ, est ce que compte `RecordTilesMoved` — deux listes distinctes).
`path[0]` est la tuile de DÉPART, `path.Last()` la destination :
`IdunBattle.Entities.Pathfinding.BasePathfinder$$FindPath` construit la liste de `to` en
remontant puis la **renverse**, et la boucle d'`AddMoveEvent` démarre à `i = 1`.

`IdunBattle.Operations.MoveUnitOperation$$IsLikeFlying(unit, options)` =
`IdunBattle.Entities.UnitExtensions$$IsLikeFlying(unit) || options.<+0x8> == 3`, avec
`UnitExtensions$$IsLikeFlying(unit)` = `HasTrait(0x4 = Flying) || HasTrait(0x13 = Burrow)` — les
deux bras lus, `Burrow` compris.

## 2. Le slot `0x6c`, RE-DÉRIVÉ AU RUNTIME

La fiche ne suffit pas : #433-r4-r2 a mesuré que **tous** les slots `IBattleQuery` de deux ports
voisins étaient décalés d'un cran, et un cran plus bas (`0x6b`) vaut aujourd'hui
`GetBoardWidth`. Re-dérivation par `probe_27_4g_battlequery_slots.py` sur `rnca9r7q6c` (ancres
`+4` confirmées sur deux points indépendants) :

| slot d'interface | index de vtable | méthode | RVA |
|---|---|---|---|
| `0x15` | `0x19` | `GetConnectedPathTo` | `0x115fa20` |
| `0x17` | `0x1b` | `GetNumTilesMoved` | `0x1165cf0` |
| **`0x6c`** | **`0x70`** | **`GetDistance`** | **`0x11608f0`** |
| `0x6d` | `0x71` | `GetDistance` (autre surcharge) | `0x11607a0` |

Les deux premières lignes **recoupent** : ce sont exactement les slots que le décompilé
d'`Execute` utilise par ailleurs (`GetNumTilesMoved(connectedPath)` pour `RecordTilesMoved`,
`GetConnectedPathTo` dans `CalculatePaths`). La RVA `0x11608f0` est celle de la surcharge
**`(tileA, tileB)`** — pas une des trois autres.

Ce que cette surcharge fait, lu :

    BattleQuery$$GetDistance(tileA, tileB)
      -> MovementQuery$$GetDistance(origin: IEntity, destination: IEntity)
           originTiles = GetTiles(origin) ; destinationTiles = GetTiles(destination)
      -> MovementQuery$$GetDistance(originTiles, destinationTiles)
           min sur (a, b) de CubeCoordinate$$Distance(a.GetCubeCoordinate(), b.GetCubeCoordinate())
           (0x7fffffff si une liste est vide)

et `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` = `Max(Max(|dx|, |dy|), |dz|)`, soit
exactement `hexgeo.distance` (`(|dx|+|dy|+|dz|)/2` — même valeur quand `dx+dy+dz = 0`).

**Corroboration structurelle, indépendante du runtime** : `CalculatePaths` appelle **le même slot
`0x6c`** avec `(startTile, endTile)` et compare son retour au stat `Movement`
(`GetStat(unit, 1)`) pour décider s'il doit borner le `maxRange` du pathfinder. Comparer à un
`Movement` n'a de sens que pour une distance en hexes.

## 3. Le porteur — gate de confrontabilité passée au premier étage

`rl_duel build --list-pool` (rank 17) : **15 des 105 unités spawnables** portent `Flying`
(`admecManipulus`, `blackHaarken`, `bloodDante`, `bloodIntercessor`, `eldarAutarch`,
`necroSpyder`, `tauCrisis`, `tauShadowsun`, `thousAhriman`, `thousSorcerer`, `thousTzaangor`,
`tyranNeurothrope`, `tyranParasite`, `tyranWingedPrime`, `ultraInceptorSgt`). Aucune injection
catalogue nécessaire. Greffons retenus : les cinq de `Movement >= 4`, pour pouvoir viser `d = 2`
**et** `d = 3`.

Canal d'observation : la greffe de `1134 FullThrottle`
(`catalog_inject.graft_passive_ability`) — son `CreateTrigger` est
`On(0x24) & OwnerIsActor & AmountIsEqualOrGreater(MovementSteps(), 'movement' = 3)` et son
`CreateBehaviour` `If(Maybe('chance' = 30), Kill(Caster))`. Ni l'un ni l'autre ne lit stat, trait
ou arme du caster : la condition de greffe est vérifiée.

## 4. La mesure — quatre bras, dont un COUPLE

`probe_448_r1_r1_r1_flying_movement_steps.py`. Mort relue **immédiatement après le move**, avant
toute action adverse (`--no-ai`).

| bras | trajet | `movementSteps` attendu | gate `>= 3` | **NATIF mesuré** |
|---|---|---|---|---|
| **M2** | MARCHEUR, `d = 2`, 2 pas (MC1_67) | `path.Count` = 3 | VRAI | **3 / 8 = 37,5 %** |
| **V2** | VOLANT, `d = 2`, vol direct (MC1_67) | `distance` = 2 | FAUX | **0 / 20 = 0,0 %** |
| **V3** | VOLANT, `d = 3`, vol direct (MC1_67) | `distance` = 3 | VRAI | **4 / 13 = 30,8 %** |
| **VD** | VOLANT, `d = 2`, vol DÉTOURNÉ (C6_25) | `distance` = 2 | FAUX | **0 / 14 = 0,0 %** |

**M2 + V2 = le couple.** Même distance parcourue, `movementSteps` différent selon le régime :
le marcheur meurt à 37,5 %, le volant **jamais**. `P(0 mort sur 20 | gate vrai) = 0,7^20 =
0,08 %` — le gate est bien FAUX à `d = 2` pour un volant. C'est ce couple, et lui seul, qui
prouve l'asymétrie ; une mesure sur le seul volant ne distinguerait rien.

**V3 est le contrôle POSITIF**, sans lequel « 0 mort chez le volant » serait indistinguable
d'une greffe inerte : 30,8 %, soit `chance` exactement.

**VD est le discriminant FIN.** Sur un vol direct, `GetDistance` et `path.Count - 1` **coïncident**
— un accord obtenu là ne confirmerait rien. Le bras VD choisit des trajets où un mur force le vol
à contourner : `d = 2` mais chemin de vol de **3 ou 4** pas. Les trois lectures y divergent
(2 / 3 / 4) et une seule n'arme pas le gate. `P(0 sur 14 | gate vrai) = 0,7^14 = 0,68 %`.

### Comment le bras VD a été monté

`FlyPathfinder$$IsValidPathNode` ne teste que `TileComponent+0x40` (fog) et `+0x41` (`IsWall`) :
**seul un mur détourne un vol** — `Block` / `Water` sont survolés. Les murs vivent dans les
tuiles `HulkWall` / `HulkDoor`, présentes sur **17 boards**, tous `C6_*`.

Le `boardGraph` (live) est la seule source de `isWall` ; le JSON de `data/boards/` porte un
`TileId`. Le mapping a été établi sur un board (`Tiles[col].Tile[row]`, 63/63 élévations
concordantes ; `HulkWall`/`HulkDoor` → `isWall = True, walkable = False`), puis les 17 boards
balayés **offline** — un seul build au lieu de dix-sept.

Résultat : **C6_25** (7 départs, 14 couples détournés) est le seul board utilisable ; C6_09, avec
pourtant 16 murs, en offre **zéro** — sa barrière coupe le plateau en deux zones que le vol ne
relie plus du tout, donc les paires « à travers » sont déconnectées et les autres directes.

Les porteurs ne partent pas là où la configuration existe : le probe joue des **pas d'approche
d'un hexe** (`movementSteps` y vaut 1 ou 2, `< 3` sous les deux régimes — ils ne peuvent ni tuer
ni polluer la mesure) pour les y amener. C'est le « déplacer les unités » de la doctrine, pas un
« bloqué par la géométrie de spawn ».

## 5. Contre-épreuve — la mutation qui NIE l'asymétrie

`--mutate-fly` fait passer les volants par la branche marcheuse (`path.Count` pour tout le
monde) : c'est exactement le port qu'on obtiendrait en ne lisant pas le ternaire.

| | étape 0 | volet PORT `fly d=2` | volet PORT `fly d=3` |
|---|---|---|---|
| livré | 0 anomalie | **0,0 %** (200 essais) | 26,0 % (200 essais) |
| `--mutate-fly` | **9 anomalies** | **33,5 %** | 26,0 % **inchangé** |
| NATIF | — | **0 / 20** | 4 / 13 |

La mutation mord **exactement** sur le bras discriminant et **nulle part ailleurs** : `fly d=3`
ne bouge pas d'un point. Et le port muté diverge du natif là où le port livré l'accorde.

⚠ La contre-épreuve porte sur le **volet PORT**, pas sur les bras natifs : ceux-ci ne dépendent
pas du code Python, donc un mutant qui ne s'appliquerait qu'à eux ne prouverait rien.

## 6. Ce que la RE a rendu visible en chemin — RÉSIDU `#448-r1-r1-r1-r1`, ~~OUVERT~~ **FERMÉ**

> **FERMÉ le 2026-08-04** — `docs/rl/case-448-r1-r1-r1-r1-flying-tiles-moved.md`. Le constat
> ci-dessous était juste ; **le chemin de fermeture qu'il proposait ne l'était pas**, sur ses
> deux points (a) et (b) :
>
> * **(b) est RÉFUTÉ** : le 5ᵉ paramètre de `FindPath` n'est pas un `maxRange`. Sa signature est
>   `useTeleporter: System.Nullable<IdunBattle.Entities.Pathfinding.UseTeleporter>`, et **ni
>   `BasePathfinder$$FindPath` ni `FlyPathfinder$$FindPath` ne le LISENT** — argument mort.
> * **(a) était incomplet** : il ne suffit pas d'un « compteur de nœuds FLY ».
>   `IdunBattle.Entities.Pathfinding.FlyPathfinder$$FindPath` **OVERRIDE** et ne rend PAS le
>   chemin — il le réduit à ses WAYPOINTS —, puis `GetConnectedPathTo` le RE-DENSIFIE par un
>   `PathfinderType.Beeline` qui traverse tout, murs compris.
>
> Et deux étages que ce paragraphe ne soupçonnait pas : `GetPathfinderTypeForUnit` teste QUATRE
> effets **avant** `IsLikeFlying` (3 des 5 volants du pool sortent en type DÉCORÉ, dont
> `ATeleportPathfinder$$FindPath` rend `[from, to]`), et le champ `neighbours` du `boardGraph`
> est amputé de 18 arêtes par la porte d'élévation du capteur.

`_num_tiles_moved` (le mirror de `GetNumTilesMoved(connectedPath)`, consommé par
`record_tiles_moved`) prend le **WalkPathfinder inconditionnellement**. Or
`MovementQuery$$GetConnectedPathTo` résout
`MovementQuery$$GetPathfinderTypeForUnit(unit)` = `IsLikeFlying(unit) ? 3 : 0` — c'est-à-dire
le **FlyPathfinder** pour un volant (le `3` est aussi, littéralement, la valeur que le second bras
d'`IsLikeFlying` compare).

⇒ **pour une unité volante, le port enregistre des pas de MARCHE dans `TilesMovedThisTurn`.**
Mesuré sur MC1_67 : `(1,1) -> (1,3)` vaut **3** pas de marche et **2** de vol — le port
compterait 3.

**Ce n'est pas dans le périmètre de cette tranche** : `_movement_steps` n'appelle pas
`_num_tiles_moved` sur la branche volante, donc rien de ce qui est mesuré ici n'en dépend. Le
fermer demande (a) un compteur de nœuds FLY (le port n'a qu'un `get_movable_positions` fly, pas
de `get_path_node_counts_by_pos`), (b) le `maxRange = GetStat(unit, Movement)` que
`GetConnectedPathTo` passe et que la marche ne passe pas, et (c) sa propre validation — il
déplace `TilesMovedThisTurn`, donc tous ses lecteurs.

## 7. Ce que la tranche ne mirror PAS, nommément

* **Le second bras d'`IsLikeFlying`** (`options.<+0x8> == 3`). La RE est désormais complète —
  c'est le `Nullable<PathfinderType>` d'override que `CalculatePaths` relit pour choisir son
  pathfinder, et `3` en est la valeur « volante ». Mais le port n'a pas de struct `options` et
  aucun de ses call-sites ne la pose. RÉSIDU NOMMÉ, inchangé.
* **`GetDistance` sur argument NUL** rend `0x7fffffff` (= gate VRAI) là où le port rend `0`.
  Inatteignable : `path.First()`/`path.Last()` d'un mouvement joué ne sont jamais nuls.
* **Le mouvement NUL** (`from == to`) : le natif aurait `GetDistance = 0` côté volant et
  `path.Count == 1` côté marcheur ; le port rend `0` dans les deux cas. Inobservable — le seul
  lecteur exige `>= 3`.
* **Le multi-pieds.** `MovementQuery$$GetDistance` prend le **min** sur toutes les paires
  `GetTiles(a) x GetTiles(b)`. Ses arguments ici sont des TUILES (pas des unités), donc des
  singletons, et le min est la distance directe. Le port collapse de toute façon l'empreinte
  (`UnitComponent.feet`).
* **La branche dégénérée** (`movementStartPosition.Count == 0`) : le natif y pose
  `path = connectedPath = [endTile, endTile]`, donc `path.Count = 2` côté marcheur et
  `GetDistance(endTile, endTile) = 0` côté volant. Aucune de ces valeurs n'arme le gate ; le port
  n'a pas cette branche.
* **Le fog (`TileComponent+0x40`) dans l'arête de vol** — résidu préexistant de
  `fly_pathfinder` : le `boardGraph` ne le publie pas. Il ne biaise pas cette mesure, et dans le
  bon sens : le port **sous-estime** les détours, donc tout trajet qu'il qualifie « détourné »
  l'est *a fortiori* côté natif.

## 8. Reproduction

    python scripts/python/probe_448_r1_r1_r1_flying_movement_steps.py --offline
    python scripts/python/probe_448_r1_r1_r1_flying_movement_steps.py --only M2 --turns 4
    python scripts/python/probe_448_r1_r1_r1_flying_movement_steps.py --only V2 --turns 4
    python scripts/python/probe_448_r1_r1_r1_flying_movement_steps.py --only V3 --turns 4
    python scripts/python/probe_448_r1_r1_r1_flying_movement_steps.py --only VD \
        --detour-board C6_25 --turns 16
    python scripts/python/probe_448_r1_r1_r1_flying_movement_steps.py --port
    python scripts/python/probe_448_r1_r1_r1_flying_movement_steps.py --port --mutate-fly
    python scripts/python/probe_27_4g_battlequery_slots.py --slots 0x6c,0x15,0x17
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r1_flying_movement_steps_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r1_flying_movement_steps_live.py
