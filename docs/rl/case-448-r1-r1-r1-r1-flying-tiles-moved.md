# case-448-r1-r1-r1-r1 — `GetNumTilesMoved` pour un VOLANT, fermé

`#448-r1-r1-r1-r1`. Le résidu était écrit ainsi : « `_num_tiles_moved` prend le WalkPathfinder
inconditionnellement, donc un volant enregistre des pas de MARCHE ». Il est **fermé, et la RE a
trouvé deux étages de plus que ce que le résidu annonçait** — un que la fiche parente demandait
de porter et qui n'existe pas (`maxRange`), un qu'elle ne soupçonnait pas (le décorateur
TÉLÉPORT).

---

## 1. La chaîne native, établie de bout en bout

`IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, n, state)` reçoit

    n = IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(connectedPath)
      = IsNullOrEmpty(path) ? 0 : path.Count - 1

et `connectedPath = IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo(unit, from, to)`,
dont le décompilé remis en C# est :

    maxRange = new Nullable<UseTeleporter>(UnitExtensions.GetStat(unit, 1));
    path = pathfinders.GetPath(unit, from, to, maxRange);          // slot itf 3
    if (path == null) return new List { from, to };                // branche DEGENEREE
    q = new Queue(path); res = new List(); cur = q.Dequeue();
    while (true) {
        res.Add(cur);
        if (q.Count < 1) return res;
        last = res.Last(); next = q.Dequeue();
        if (last != null && next != null
            && GetDistance(GetTiles(last), GetTiles(next)) > 1) {
            sub = pathfinders.GetPath(PathfinderType.Beeline, unit, last, next, null);
            for (i = 1; i < sub.Count - 1; i++) res.Add(sub[i]);   // extremites EXCLUES
        }
        cur = next;
    }

Le `PathfinderType` que reçoit ce slot 3 d'`IPathfinders` (`GetPath`, 4 arguments) est résolu par
`IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit)` — slot `0xe`
d'`IMovementQuery` :

    if (HasEffect(0x40b)) return IsLikeFlying ? 7  : 6;
    if (HasEffect(0x474)) return IsLikeFlying ? 9  : 8;
    if (HasEffect(0x4d6)) return IsLikeFlying ? 11 : 10;
    if (HasEffect(0x625)) return IsLikeFlying ? 13 : 12;
    return IsLikeFlying ? 3 : 0;

**Pour un MARCHEUR, la densification est un no-op** (deux nœuds consécutifs d'un chemin de
`BasePathfinder$$FindPath` sont adjacents). Pour tout le reste, elle ne l'est pas.

## 2. Ce que les tables de symboles ne pouvaient pas dire — RE-DÉRIVÉ AU RUNTIME

Six slots décidaient du résultat et **aucun n'était nommable offline** : IL2CPP déduplique les
corps triviaux, donc ni Ghidra ni `frida/methods.tsv` n'en portent le nom. Résolus par
`resolveVtableSlot` (vtable propre depuis `+0x138`, pas de `0x10`), build `rnca9r7q6c` :

| classe | idx | slot | corps résolu |
|---|---|---|---|
| `FlyPathfinder` | `0x0c` | `WeightCost` | **trivial `return 10`** |
| `FlyPathfinder` | `0x09` | `IsValidFinalTile` | `WalkPathfinder$$IsValidFinalTile` (partagé) |
| `FlyPathfinder` | `0x0a` | `IsValidContinuePathTile` | **trivial `return true`** |
| `IgnoreEverythingPathfinder` | `0x0b` | `IsValidPathNode` | **trivial `return true`** |
| `IgnoreEverythingPathfinder` | `0x09` | `IsValidFinalTile` | **trivial `return true`** |
| `TeleportStrikePathfinder` | `0x07` | `FindPath` | `ATeleportPathfinder$$FindPath` |

Trois conséquences directes :

* le `WeightCost` du vol est **uniforme** ⇒ le chemin de coût minimal EST le chemin de longueur
  minimale, donc le résidu de départage de `base_pathfinder` **ne mord pas** sur cette branche ;
* les trois prédicats du `Beeline` sont `true` ⇒ **il traverse tout, murs compris** ;
* `FlyPathfinder$$IsValidContinuePathTile = true` **confirme au runtime** ce que `#381-r2` avait
  conclu par exhaustion des XREFS (aucun gate d'expansion pour le vol).

## 3. `FlyPathfinder$$FindPath` ne rend PAS le chemin

C'est l'override central, et il était invisible du résidu :

    path = base.FindPath(...);  if (path == null || path.Count <= 1) return path;
    dir = path[0].GetPosition().DirectionTo(path[1].GetPosition());
    for (i = 0; i < path.Count; i++) {
        if (i < path.Count - 1 && i != 0) {
            isTele = IsTeleportationTile(tile);  turn = false;
            if (IsAnyAdjacentTileWall(this, tile)) {
                nd = tile.GetPosition().DirectionTo(path[i + 1].GetPosition());
                turn = (dir != nd);  if (turn) dir = nd;
            }
            if (isTele || turn) out.Add(tile);
        } else out.Add(tile);                       // extremites TOUJOURS
    }

⇒ un vol DIRECT se réduit à `[from, to]`, et `GetConnectedPathTo` recoud le saut par une beeline
qui **coupe à travers les murs**. Un vol détourné garde ses points de virage — mais seulement
ceux qui ont un mur dans leur couronne.

**`AxialCoordinate$$DirectionTo`** normalise le delta cube en Fix64 (sqrt, tie-break
`x *= K + 0.01` quand `|x| == |y|` ou `|x| == |z|`, arrondi vers l'extérieur) puis passe à
`CubeDirections$$EdgeToNeighbor`. Sur un **pas unitaire** — le seul régime où `FindPath`
l'appelle — les trois branches du tri redonnent exactement le delta cube ; c'est ce qui est porté,
le reste est un résidu nommé.

## 4. RÉFUTÉ : le « `maxRange` » du résidu n'existe pas

La fiche parente demandait de porter « le `maxRange = GetStat(unit, Movement)` que
`GetConnectedPathTo` passe ». **Ce n'est pas un maxRange.** Sa signature, lue dans
`data/symbols/<build>/frida/methods.tsv`, est

    FlyPathfinder.FindPath(unit, fromTile, toTile,
                           useTeleporter: System.Nullable<IdunBattle.Entities.Pathfinding.UseTeleporter>)

et **ni `BasePathfinder$$FindPath` ni `FlyPathfinder$$FindPath` ne le LISENT** — il traverse leur
corps sans être déréférencé. C'est un argument mort sur les deux routes. Rien à porter.

## 5. Le porteur, et la gate de confrontabilité

**15 des 105 unités du pool portent `Flying`** — premier étage franchi, aucune injection
catalogue. Cinq retenues (`Movement >= 4`) : `blackHaarken`, `bloodDante`, `bloodIntercessor`,
`eldarAutarch`, `tyranWingedPrime`.

⚠ **Et 3 des 5 ne sont PAS en `PathfinderType.Fly`** : `bloodDante`, `bloodIntercessor` et
`eldarAutarch` portent `TeleportStrike` et sortent en type **7**. C'est la mesure qui l'a révélé,
pas le trait : `GetPathfinderTypeForUnit` teste un **effet**, pas un trait.

## 6. Le canal d'observation — un SCALAIRE, pas un gate

`actorStats.tilesMovedThisTurn` = `ActorStatisticsComponent+0xf0`, lu AVANT et APRÈS un
`applyAction move`. C'est exactement ce qu'écrit `RecordTilesMoved`. Aucun tirage aléatoire, donc
aucune statistique à accumuler — contrairement au gate `FullThrottle` de la tranche parente.

**GARDE DE MONTAGE, trouvée par la mesure.** Le move de la **dernière unité activable** fait
basculer le tour, donc `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn`
(`if (wasOwnTurn) comp[0xf4] = comp[0xf0]; comp[0xf0] = 0;`) remet `+0xf0` à **zéro pour toutes
les unités** — y compris celle qu'on vient de bouger. La lecture rend alors `0`, qui se lit comme
« le natif n'a rien enregistré » : **faux**. Ce faux désaccord s'est présenté 4 fois sur 15 au
premier jet, toujours sur `tyranWingedPrime`, et aurait pu se lire comme un bug de port propre à
cette unité.

Discriminant : une **autre** unité a vu son compteur DIMINUER — aucune écriture native ne le peut
(`RecordTilesMoved` ne fait que `+=` et sort sur `if (tiles < 1) return`). Le report `+0xf4`
n'est pas une échappatoire : ce champ est illisible sur le bundle courant.

## 7. La mesure — quatre bras, dont un qui rend TROIS valeurs

`probe_448_r1_r1_r1_r1_flying_tiles_moved.py`, seed 777.

| bras | montage | mesures | désaccords |
|---|---|---|---|
| **FD** | VOLANT, `d = 2`, vol direct (MC1_67) | 12 | **0** |
| **FD3** | VOLANT, `d = 3`, vol direct (MC1_67) | 12 | **0** |
| **W** | MARCHEUR, `d = 2` (MC1_67) — non-régression | 10 | **0** |
| **FX** | VOLANT, `d = 2`, vol **DÉTOURNÉ** (C6_25) | 10 | **0** |

**FX est le discriminant, et il n'est pas dégénéré** : sur des couples **tous à `d = 2`**, le
natif rend **2, 3 OU 4** —

* `bloodIntercessor` `(2,2) -> (4,3)`, chemin de vol 3 pas → **2** (il est en `TeleportStrike`,
  donc `[from, to]` puis beeline) ;
* `blackHaarken` `(4,2) -> (2,3)`, chemin de vol 3 pas → **3** ;
* `blackHaarken` `(2,3) -> (4,3)`, chemin de vol 4 pas → **4**.

Aucune lecture constante ne produit ces trois valeurs. Le port suit les trois.

Le montage `C6_25` est repris de `#448-r1-r1-r1` (17 boards à murs balayés ; `C6_09` en a 16 et
n'offre **aucun** trajet détourné — sa barrière déconnecte le plateau).

## 8. Les contre-épreuves — chacune isole SON étage

| mutant | ce qu'il nie | bras | effet |
|---|---|---|---|
| `--mutate-walk` | le dispatch entier (WalkPathfinder inconditionnel = le port d'AVANT) | FD3 / FX | **2** / **1** désaccord |
| `--mutate-teleport` | le seul décorateur `ATeleportPathfinder$$FindPath` | FX | **1** désaccord |
| `--mutate-beeline-native` | le substrat de la beeline (champ capté au lieu de la géométrie) | FD | **1** désaccord |

Le port livré rend **0** désaccord sur les quatre bras. Chaque mutant mord sur son gisement et
**pas ailleurs** : `--mutate-teleport` ne touche que le cas `bloodIntercessor` de FX,
`--mutate-beeline-native` que le cas `(1,1)->(1,3)` de FD.

## 9. Le substrat de la beeline — un arbitrage MESURÉ, pas une commodité

Le natif lit le `ConnectivityComponent` (`BasePathfinder$$AddNeighbours`). Le port lit la
**géométrie**, et c'est la mesure qui l'impose : le champ `neighbours` du `boardGraph` n'est pas
le `ConnectivityComponent`. Le capteur passe par
`IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`, dont la porte `|Δelev| < 2` est
**inconditionnelle** — sur `MC1_67` il ampute **18 arêtes dirigées**, toutes des marches `2 ↔ 4`.

Le natif prouve que ces arêtes existent chez lui : sur `(1,1) -> (1,3)` d'un volant (`d = 2`) il
enregistre **2**, ce qui exige un chemin de deux arêtes, donc l'arête `(1,2)-(1,3)` que le champ
ne porte pas. Avec le champ, le port rendait **3**.

⚠ **Résidu dans l'autre sens** : le `ConnectivityComponent` peut légitimement ne PAS relier deux
tuiles géométriquement voisines (`#381-r3` : les deux `Bridge` de `C1_74`, 4 arêtes sur 74) — la
beeline du port y couperait où le natif ferait le tour. Aucun board mesuré ici n'est dans ce cas.
Le test live garde les deux faces (que le trou existe encore, et qu'il change un compte).

### 9 bis. Interaction avec `#433-r4-r2-r1-r1` (PR #558) — vérifiée, CONVERGENTE

`#558` a livré `engine/services/ability_range.py` et attribué ses derniers faux positifs à **la
même porte d'élévation**, `|srcElev - Elevation| < 2` de
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`. Deux tranches
touchant au même étage géométrique par deux chemins : vérifié après rebase sur `e814745d`.

**Les deux ports lisent la même géométrie de base et divergent sur la porte — chacun là où SON
natif la porte.** Ce n'est pas un accroc, c'est la fidélité :

| | natif mirroré | géométrie lue | porte `|Δelev| < 2` |
|---|---|---|---|
| `ability_range` (#558) | `TileQuery$$IterateAdjacentTiles` | `hexgeo.distance == 1`, **recalculée** | **appliquée** (`battle_query.is_adjacent`, depuis `elev_by_pos`) |
| beeline (cette tranche) | `BasePathfinder$$AddNeighbours` / `ConnectivityComponent` | `board.neighbours_geometric` | **non appliquée** |

`ability_range` ne touche **jamais** `board.neighbours_*` : il passe par
`bq.is_adjacent(t, n, elev_by_pos)` et applique la porte lui-même. Il est donc **structurellement
insensible** à l'amputation du champ `neighbours` qui, elle, m'a mordu.

**Et la mesure de cette tranche CORROBORE l'attribution de #558, par un chemin indépendant.** Le
natif enregistre **2** sur `(1,1) -> (1,3)` d'un volant, ce qui exige l'arête `(1,2)-(1,3)` dont
le Δélévation vaut **2** — donc le `ConnectivityComponent` **contient** cette arête. ⇒ la porte
`|Δelev| < 2` appartient bien à `IterateAdjacentTiles` et **pas** au graphe de connectivité. Le
capteur du `boardGraph`, qui passe par `IterateAdjacentTiles` pour produire le champ `neighbours`,
l'applique donc à un champ qui, côté natif, ne l'a pas — c'est exactement le mécanisme du résidu
`-r2` ci-dessous.

Contrôle joué après rebase : `test_433_r4_r2_r1_ability_range_live.py` **6 passed**,
`test_433_r4_r2_r1_r2_ability_range_offline.py` + `test_433_r4_r2_r1_r1_dynamic_target_gate_offline.py`
verts dans la passe de 101.

## 10. Ce que la tranche ne porte PAS, nommément

* **`IsTeleportationTile`** (`ConnectivityComponent+0x18`), le second critère de rétention d'un
  waypoint dans `FlyPathfinder$$FindPath`. Le `boardGraph` ne publie pas ce champ — même absence
  de source que le `AddTeleportationTiles` déjà nommé dans `walk_pathfinder`. Le port ne garde
  donc pas un waypoint que le natif garderait, sur un board à téléporteur.
* **La branche MARCHE reste sur son moteur en domaine POSITION**
  (`get_path_node_counts_by_pos`), FOYER PARTAGÉ avec la face DÉCISION (`#304`). La rebrancher
  créerait deux implémentations du même natif ; la densification y est de toute façon un no-op.
  Résidu marche **préexistant et inchangé** : sur une destination injoignable le port rend `0` là
  où le natif prend sa branche dégénérée (`[from, to]` → `1`).
* **`AxialCoordinate$$DirectionTo` hors pas unitaire** — aucun call-site porté ne le sollicite.
* **`IsAnyAdjacentTileWall`** interroge le slot 2 de la requête de tuiles (args `(tile, 0, 0, 1)`)
  et n'écarte pas le centre, là où `AddNeighbours` interroge le slot 1 (args `(tile, 1, ...)`) et
  l'écarte. Inobservable : `FindPath` n'appelle ce prédicat que sur des tuiles déjà traversées, et
  l'arête interdit d'entrer sur un mur.
* **Le fog (`TileComponent+0x40`) dans l'arête de vol** — résidu préexistant de `fly_pathfinder`.

## 11. Reproduction

    python scripts/python/probe_448_r1_r1_r1_r1_flying_tiles_moved.py --offline
    python scripts/python/probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FD  --turns 4
    python scripts/python/probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FD3 --turns 3
    python scripts/python/probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only W   --turns 3
    python scripts/python/probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FX  --turns 12
    python scripts/python/probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FX  --turns 12 --mutate-walk
    python scripts/python/probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FX  --turns 12 --mutate-teleport
    python scripts/python/probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FD  --turns 3  --mutate-beeline-native
    python scripts/python/probe_448_r1_r1_r1_r1_flying_tiles_moved.py --diag "1,1>1,3;1,2>1,3"
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r1_r1_flying_tiles_moved_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r1_r1_flying_tiles_moved_live.py

## 12. Résidus OUVERTS nés de cette tranche

* **`#448-r1-r1-r1-r1-r1`** — le **départage à coût égal** de `BasePathfinder$$GenerateBreadthFirstTree`
  n'est pas lu au décompilé (ordre interne de la `PriorityQueue` native, mise à jour sur `<`
  STRICT). Inerte sur la branche VOL (coût uniforme ⇒ tous les chemins minimaux ont la même
  longueur), il redevient actif dès qu'un pathfinder à coût non uniforme passe par
  `base_pathfinder` — c'est-à-dire si la branche MARCHE y était un jour rebranchée.
* **`#448-r1-r1-r1-r1-r2`** — le **substrat de la beeline** (§9). **FERMÉ le 2026-08-04 par la
  mesure (§13.5)** : la géométrie est bien un sur-ensemble strict du `ConnectivityComponent`, et
  les deux divergent sur les `Bridge` — **16** arêtes dirigées sur `C1_74`, pas 4. Deux résidus
  NAISSENT de là :
  * **`#448-r1-r1-r1-r1-r2-r1`** — le **rebranchement** des pathfinders sur
    `neighbours_connectivity`. **FAIT et CONFRONTÉ le 2026-08-04 : cf. §14.** Le natif tranche
    pour le canal (5 mesures discriminantes / 5), et l'ancien substrat était un **bug de port
    réel** — 4 tuiles parcourues au lieu de 6.
  * **`#448-r1-r1-r1-r1-r2-r2`** — `ConnectivityComponent+0x18` (la jumelle de téléport) reste
    **NON CONFRONTÉ EN VALEUR** : le champ est localisé par deux sources indépendantes, mais
    **aucun des 779 boards du pool** ne porte de tuile de téléport (critère natif : l'ability
    déclenchée `0x3c`, pas un `TileId`). Cf. §13.5.

## 13. Le capteur du canal BRUT — écrit (#466), **CONFRONTÉ le 2026-08-04** (§13.5)

Le résidu `-r2` était bloqué sur un capteur, pas sur une question ouverte. Il est écrit, déployé,
et **mesuré** : la mesure et ses verdicts sont en **§13.5**. Les §13.1-13.4 sont la RE et le plan
d'avant-fenêtre, conservés tels quels — c'est ce qui rend l'écart du cran 6 lisible.

### 13.1 Ce que le décompilé ajoute à §9 — la preuve par la CONSTRUCTION

§9 établissait l'absence de porte par la CONSÉQUENCE (2 tuiles parcourues sur un vol qui exige
une arête de Δélévation 2). `IdunBattle.Operations.InitializeConnectivityOperation$$Execute`,
relu le 2026-08-04, l'établit par la construction — la liste se bâtit ainsi, une tuile à la fois :

```csharp
foreach (edge in Enum.GetValues(typeof(TileEdge))) {
    if (!TileComponent.HasEdge(srcComp, edge))                        continue;
    (r, c) = (PositionComponent.RowAt(pos, edge), ColumnAt(pos, edge));
    if (!BoardComponent.IsPositionInside(board, c, r))                continue;
    nid = board.Grid[c, r];   if (nid == 0)                           continue;
    if (!TileComponent.HasEdge(tileCompOf(nid), (n/2 + i) % n))       continue;   // arête OPPOSÉE
    list.Add(nid);
}
GetComponent<ConnectivityComponent>(tile).<liste> = list;
```

Critère purement **topologique** : arête des deux côtés, voisin sur le plateau. **Aucune
élévation n'y entre.** Les deux chemins concordent, et c'est la première fois que le point est
lu à sa source plutôt que déduit.

`ConnectivityComponent` (0x20 boxé) porte **deux** champs, confirmés par trois lectures
indépendantes — `BasePathfinder.u003CAddNeighboursu003Ed__19$$MoveNext` (itère),
`ConnectivityComponent$$IsNeighbour` (`List.Contains`), `ConnectivityComponent$$Copy`
(reconstruit) :

| offset | contenu | qui le lit |
|---|---|---|
| `+0x10` | `List<int>` d'entity ids de tuiles | `AddNeighbours`, `IsNeighbour` |
| `+0x18` | `int` — entity id de la tuile de TÉLÉPORT jumelle, `0` = aucune | les **quatre** surcharges de `IdunBattle.Entities.TileExtensions$$IsTeleportationTile` ; écrit par `InitializeConnectivityOperation$$ConnectTeleportTiles` |

Publier `+0x18` **ferme la source manquante de deux résidus** qui citaient la même absence :
`AddTeleportationTiles` (`base_pathfinder.py`) et `IsTeleportationTile` (§10, le second critère
de rétention d'un waypoint de `FlyPathfinder$$FindPath`).

### 13.2 Rayon de souffle — pourquoi un canal EN PLUS, jamais une correction

L'avertissement du mandat (« ne supprime pas la porte du champ existant sans mesurer qui le
consomme ») a été instruit. Le champ `neighbours` a **deux familles** de lecteurs, et la porte
est **juste pour l'une** :

| famille | natif mirroré | porte `|Δelev| < 2` | verdict |
|---|---|---|---|
| sélecteurs `AdjacentTiles` du DSL (`neighbours_native`) — `dsl/base.py`, `selectors/tiles.py`, `abilities/{bloodangels,sisterhood,astramilitarum,orks}`, `movement_query.adjacent_tile_ids` | `TileQuery$$IterateAdjacentTiles` | **la porte** | champ INCHANGÉ |
| pathfinding — `walk_maps_by_pos`, `ignore_terrain_pathfinder`, `beeline` | `BasePathfinder$$AddNeighbours` | ne la porte pas | lit un graphe amputé |
| `engine/services/ability_range.py` (#558) | `TileQuery$$IterateAdjacentTiles` | l'applique **lui-même** | **ne lit jamais** `board.neighbours_*` — structurellement insensible |

⇒ corriger le champ existant **casserait la première famille pour réparer la seconde**. Le
capteur AJOUTE `connectivity` (+ `teleportTwinTileId`) ; `neighbours` reste bit-pour-bit ce
qu'il était. Les deux coexistent **par fidélité**, chacun mirroir du natif de SON consommateur.

### 13.3 Ce qui est livré

* `frida/hooks/features/ai-step/rpc-board.ts` — `boardGraph` publie par tuile `connectivity`
  (tri-état) et `teleportTwinTileId`, plus, au niveau réponse, `connectivityClassResolved`,
  `connectivityLayout`, `connectivityTiles`, `connectivityMissing`, `connectivityEdges`,
  `connectivityTeleportTiles`, `neighbourEdges`. Offsets **résolus par nom de champ au runtime**
  (`class_get_fields`, choix par TYPE : l'unique `List`, l'unique `Int32`), repli sur les
  littéraux du décompilé, **et le layout observé est publié** — un capteur ne fait pas passer une
  lecture d'offset supposé pour une mesure.
* `engine/entities/pathfinding/board.py` — `neighbours_connectivity()` et `teleport_twin()`, en
  **tri-état** (`None` = canal absent, `[]` = liste vide). **Aucun pathfinder n'est rebranché** :
  changer le substrat change des résultats observables, donc c'est un port spéculatif tant que
  la mesure n'a pas eu lieu.
* `tests/engine/entities/pathfinding/test_448r1r1r1r1r2_connectivity_channel_offline.py` —
  6 crans, **13 passed** avec `test_381r3_neighbour_source_offline.py` (non-régression). Ils
  verrouillent ce qui peut casser SANS capteur : le tri-état, le filtrage hors-board, et une
  **garde de périmètre** qui rougit si un pathfinder est rebranché sans passer par la mesure.

### 13.4 PLAN DE MESURE — ce que la fenêtre doit jouer, et ce que chaque résultat tranche

Prérequis : reinject + `autoBootExtraire({force:true})`. Puis, depuis `scripts/python` :

```
python rl_duel.py build --seed 777 --board MC1_67 --state-file <ABSOLU unique>
# puis RPC boardGraph { runnerId } ; idem sur C1_74 (les deux `Bridge`) et C6_25 (murs).
```

| # | mesure | résultat attendu | ce qu'un ÉCART trancherait |
|---|---|---|---|
| 1 | `connectivityClassResolved` | `true` | `false` ⇒ la classe n'est pas indexée par `image_get_class` — capteur inopérant, **rien d'autre n'est interprétable** ; c'est le premier à lire |
| 2 | `connectivityLayout.resolved` + `.fields` | `true`, un `List` @`0x10` et un `Int32` @`0x18` | `false`, ou des offsets autres ⇒ le repli littéral a servi : **confronter `fields`** et corriger les constantes. Un layout divergent invalide les mesures 3-6 |
| 3 | `connectivityMissing` | `0` | `> 0` ⇒ des entités `Tile` sans `ConnectivityComponent` : à nommer, pas à moyenner |
| 4 | **`connectivityEdges - neighbourEdges` sur `MC1_67`** | **`+18`** | c'est LE cran. `+18` reproduit, par un troisième chemin indépendant, l'amputation mesurée en §9. `0` ⇒ le canal capte la même chose que le champ hérité, donc le capteur ne mord pas (ancrage à revoir). Un écart ≠ 18 ⇒ la porte n'est pas la seule différence : **ventiler arête par arête avant toute conclusion** |
| 5 | les 18 arêtes en écart | **toutes** des marches `2 ↔ 4` | une arête en écart dont le Δélévation vaut `< 2` ⇒ une SECONDE cause coexiste avec la porte, et §9 est incomplet |
| 6 | `C1_74` : arêtes du canal brut absentes de `neighbours_geometric` | les **4** arêtes `Bridge` (`(1,5)-(2,4)`, `(4,4)-(5,5)`) sont dans la géométrie et **PAS** dans le canal brut | c'est le résidu « dans l'autre sens » de §9, jamais mesuré directement. S'il est confirmé, la beeline sur géométrie coupe où le natif fait le tour ⇒ le rebranchement de `beeline_pathfinder` devient **nécessaire**, et pas seulement propre |
| 7 | `connectivityTeleportTiles` sur un board à téléporteur | `2` (les deux tuiles se pointent mutuellement, `teleport_twin(a) == b` et `teleport_twin(b) == a`) | `0` partout ⇒ soit aucun board du pool n'en porte (le dire, ne pas conclure), soit `+0x18` n'est pas le champ. `1` ⇒ asymétrie : `ConnectTeleportTiles` n'a écrit qu'un côté, contredit son décompilé |

**Après la fenêtre, et seulement après** : rejouer
`probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FD --turns 3` avec la beeline rebranchée sur
`neighbours_connectivity`. Le port doit rendre **0 désaccord** comme aujourd'hui — la beeline
géométrique et le canal brut ne divergent sur AUCUN board mesuré ici, donc **le rebranchement
doit être un no-op sur ce corpus**. S'il déplace un compte, c'est le canal qui est mal lu, pas le
pathfinder : ne pas « corriger » le pathfinder pour rattraper.

⚠ **Ce qui reste NON COUVERT même après la fenêtre** : `AddShadewalkerTiles` (effet `0x3a`, aucune
source publiée), le fog dans l'arête de vol, et le départage à coût égal de
`GenerateBreadthFirstTree` (`#448-r1-r1-r1-r1-r1`, inerte sur la branche vol).

### 13.5 LA MESURE — jouée le 2026-08-04, session 3, build `rnca9r7q6c`

`probe_448r1r1r1r1r2_connectivity_channel_live.py`, trois boards. **Le canal TRANSPORTE.**

| # | attendu | obtenu | verdict |
|---|---|---|---|
| 1 | `connectivityClassResolved: true` | `true` (3/3 boards) | **OK** |
| 2 | `layout.resolved: true`, `List`@`0x10` + `Int32`@`0x18` | `resolved: **false**` — repli littéral, mais champs **déclarés** `NeighbourIds@0x10` (`List\`1`) et `TeleportTileId@0x18` (**`BEntityId`**) | **ÉCART — défaut du capteur**, cf. ci-dessous |
| 3 | `connectivityMissing: 0` | `0`, `connectivityTiles = 63/63`, `oversize = 0` (3/3) | **OK** |
| 4 | `connectivityEdges - neighbourEdges == +18` sur `MC1_67` | **`+18`** (316 vs 298), ventilé `C\N = 18`, `N\C = 0` | **OK, exact** |
| 5 | les 18 en écart = des marches `2 ↔ 4` | **0** arête avec `|Δelev| < 2` | **OK** |
| 6 | `C1_74` : **4** arêtes `Bridge` dans la géométrie et pas dans le canal | **16** arêtes dirigées, **toutes** incidentes aux deux `Bridge` | **CONFIRMÉ, et le compte de §9 était sous-estimé** |
| 7 | `connectivityTeleportTiles == 2` sur un board à téléporteur | `0` sur les 3 — **aucun board du pool n'en porte** | **NON CONFRONTÉ, cause nommée** |

**Le cran 2 est un vrai défaut, et il n'est PAS celui qu'on croit.** Les offsets employés sont
**justes** — les noms déclarés par le runtime les confirment, et le décompilé aussi
(`InitializeConnectivityOperation$$Execute` écrit la liste à `+0x10`, `ConnectTeleportTiles`
écrit `*(comp + 0x18) = <entity id>` sur les **deux** tuiles). Ce qui était cassé, c'est la
**résolution runtime** : le filtre par type cherchait un `Int32`, le champ est un `BEntityId`,
donc `resolved` était **toujours** faux et le repli littéral **toujours** emprunté. La seule
protection contre un changement de layout au prochain build était donc inerte — précisément ce
que le capteur existait pour éviter. Corrigé (résolution par **nom déclaré** d'abord, type en
second, littéral en dernier, `source` publié) ; **non déployé**, ne prend effet qu'à la prochaine
fenêtre. Que les mesures 3-7 restent valides tient à un fait, pas à une chance : le capteur
**publiait le layout observé**, ce qui a permis de le confronter.

**Le cran 6 REDRESSE §9, et c'est le résultat le plus utile de la fenêtre.** §9 comptait « 4
arêtes sur 74 » ; la mesure en trouve **16**. L'écart n'est pas une erreur de §9 : c'est ce que
la troisième vue rend visible. Avec deux vues seulement (`G` et `N`), les 12 arêtes de
`|Δelev| >= 2` incidentes à un `Bridge` sont **indiscernables** de celles qu'ampute la porte
d'élévation ; seules restaient visibles les 4 de `|Δelev| < 2`, inexplicables autrement. Le canal
brut sépare les deux causes :

```
G \ N = 74   (la géométrie hex contre GetAdjacentTiles)
      = C \ N (58, la porte |delev| < 2)  +  G \ C (16, le refus de TileComponent$$HasEdge)
```

L'identité `G\N == C\N + G\C` est **vérifiée sur les trois boards** (18 = 18+0 ; 74 = 58+16 ;
0 = 0+0) — elle rougirait si une troisième cause s'était glissée dans une des vues.

Et la mesure dit *pourquoi* : chaque `Bridge` a **6 voisins géométriques et 2 arêtes de
connectivité**, ses deux voisins dans l'axe du pont (`(1,5) -> (1,4),(1,6)` ; `(5,5) ->
(5,4),(5,6)`). C'est `TileComponent$$HasEdge`, pur et sans élévation — confirmé *a contrario*
par les deux sens : des arêtes de `Δélévation 1` **absentes** du canal (donc pas la porte), et
des arêtes de `Δélévation 2` **présentes** ailleurs (`MC1_67`). ⇒ le résidu « dans l'autre
sens » est **confirmé**, et le rebranchement de `beeline_pathfinder` sur `neighbours_connectivity`
devient **nécessaire**, pas seulement propre : sur `C1_74`, la beeline géométrique coupe par un
`Bridge` là où le natif fait le tour. **Rebranchement NON FAIT ici** — c'est un changement de
substrat, il exige son propre re-jeu de `probe_448_r1_r1_r1_r1 --only FD`.

**`C6_25` est un TÉMOIN DÉGÉNÉRÉ, et il vaut d'être gardé** : les trois vues y coïncident
(316/316/316, tous écarts nuls). Un capteur mesuré sur ce seul board aurait rendu un accord
parfait **sans rien prouver**. C'est la raison d'être du cran « au moins un board rend un écart
non nul » dans le probe.

**Cran 7 — pourquoi il ne pouvait pas être joué (suite en §14 pour le rebranchement).** `InitializeConnectivityOperation$$Execute`
n'ajoute une tuile à sa liste de téléport que si
`TriggeredAbilityComponent$$TryGetAbility(tileComp, 0x3c)` répond vrai — critère confirmé par
`idun.Game.Board.TileView$$IsTeleportTile`, qui teste `Contains(0x3c)` sur la même liste. Une
tuile de téléport n'est donc **pas** un `TileId` de terrain : le balayage des **779** dumps rend
**11** `TileId` distincts (`Grass`, `Block`, `Swamp`, `DryBush`, `Water`, `Bridge`, `Trench`,
`BrokenIce`, `FirstAid`, `HulkWall`, `HulkDoor`) et **aucun** téléporteur ; les 15 boards à
`Doors` portent des `HulkDoor`, ce qui est autre chose. Le champ, lui, est **localisé par deux
sources indépendantes** (nom déclaré au runtime, écriture directe au décompilé) ; ce qui reste
non mesuré est une **valeur non nulle**, faute de porteur dans le pool. À rouvrir si un board à
téléporteur entre au pool.

## 14. `#448-r1-r1-r1-r1-r2-r1` — LE REBRANCHEMENT, fait et confronté (2026-08-04, session 4)

Le canal transportait (§13.5). Ça ne disait **rien** de ce qu'un rebranchement change : un
substrat plus juste est INERTE si le prédicat d'arête re-filtre déjà ce qui diffère. La question
est donc **par route**, jamais globale.

### 14.1 L'identité qui décide de tout, LUE et non supposée

`TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` itère la **même liste stockée** que
`BasePathfinder.u003CAddNeighboursu003Ed__19$$MoveNext`, puis applique `IsTemporary` /
`IsWalkable` / `IsEmptyOrSteppable` — les trois OFF pour le capteur, qui appelle
`GetAdjacentTiles(tile, false, false, true)` — et **une porte `|Δelev| < 2` inconditionnelle**.
D'où, au décompilé et pas par régression :

    neighbours == connectivity INTERSECTE {arêtes de |Δelev| < 2}          ⇒  N ⊆ C ⊆ G

`BasePathfinder$$AddNeighbours`, lui, ne filtre **rien** : ses seuls tests sont `CheckNeighbour`
(`voisin != tile`, `excluded`, vslot `IsValidPathNode`). Tout gate appartient au PRÉDICAT.

### 14.2 La ventilation — 3 routes rebranchées, 3 non concernées, 1 site hors pathfinding

| site | natif mirroré | substrat AVANT | APRÈS | ce que ça déplace |
|---|---|---|---|---|
| `walk_pathfinder.get_reachable_levels` | `BasePathfinder$$AddNeighbours` | `neighbours` (N) | **canal (C)** | **0** — no-op PROUVÉ |
| `board.walk_maps_by_pos` (face DÉCISION + `_num_tiles_moved`) | idem | N | **C** | **0** — même preuve |
| `ignore_terrain_pathfinder.get_path_node_counts` | idem | N | **C** | **0** — même preuve |
| **`beeline_pathfinder.find_path`** | idem | **géométrie (G)** | **C** | **126 couples / 3906 sur `C1_74`** |
| `fly_pathfinder` | `FlyPathfinder$$AddNeighbours` (OVERRIDE → `GetSurroundingTiles` r=1) | G | G | non concerné |
| `teleport_pathfinder` (`_has_adjacent_enemy`, `_titanhammer`) | `GetAdjacentEnemies`/`GetAdjacentTiles` → `IterateAdjacentTiles` | N | N | non concerné — leur natif PORTE la porte |
| `battle_query.are_tiles_adjacent` | `MovementUtil$$AreTilesAdjacent` → `ConnectivityComponent$$IsNeighbour` | `board.neighbours()` **(mode-dépendant)** | **C** | **0** en `native_sym`, **4** en `evenq` |

**Le no-op des trois premières est PROUVÉ, pas constaté** : le canal n'y ajoute que des arêtes de
`|Δelev| >= 2` (14.1), et leur `IsValidPathNode` exige `|Δelev| <= 1` — il les refuse toutes.
Mesuré quand même, sur les trois boards : `0/189` couples (start, depth) pour la marche,
`0/3663..3907` distances pour `IgnoreTerrain`.

**Le 7e site n'est pas un pathfinder**, et c'est pour ça qu'il avait été manqué :
`AreTilesAdjacent` vaut `(|Δelev| < 2) & (a == b || IsNeighbour(a, b))`, où la porte est un terme
**séparé** (`iVar7 < 2 & bVar3`) et `IsNeighbour` = `this[+0x10].Contains(id)` = le canal brut.
Le port lisait `board.neighbours()` — donc le `adjacency=` du MONTAGE de l'appelant, le vice exact
que `#381-r3` avait fermé pour les pathfinders.

### 14.3 Ce que ça déplace, par board

| board | `C \ N` | `G \ C` | marche | `IgnoreTerrain` | **beeline** |
|---|---|---|---|---|---|
| `C1_74` (2 `Bridge`) | 58 | **16** | 0 / 189 | 0 / 3663 | **126 / 3906** (+1 sur 124, +2 sur 2) |
| `MC1_67` | 18 | 0 | 0 / 189 | 0 / 3907 | 0 / 3906 |
| `C6_25` (témoin dégénéré) | 0 | 0 | 0 / 189 | 0 / 2445 | 0 / 3906 |

**Les boards ne sont pas interchangeables, et le probe le fait rougir** : joué sans `C1_74`, il
rend `run DEGENERE : aucun board joué n'a G \ C != 0 — rien ne POUVAIT bouger`. C'est une cause
différente de « ça ne bouge pas alors que ça devrait », et les confondre est le piège de ce sujet.

**Combien de décisions d'IA basculent : ZÉRO**, et pour une raison structurelle nommée. Les deux
seules routes que la face DÉCISION emprunte sont `ignore_terrain` (l'utilité
`MinDistanceToClosestEnemyUtility`) et `walk_maps_by_pos` (`prediction/_shared`,
`modified_exoarmour`) — toutes deux no-op. Le changement est **confiné à la face COMBAT**, où il
atteint `tiles_moved_this_turn`, donc les quatre consommateurs natifs de
`DSLFormulas$$TilesMovedThisTurn` (`ModifiedExoarmour_ExtraDmg`, `EmpyricAmbushEffect`,
`MastersOfManoeuvre`, `SmashaEad`).

### 14.4 LE NATIF TRANCHE — et l'ancien substrat était un BUG, pas une approximation

`ATeleportPathfinder$$FindPath` rend `[from, to]`, donc pour un porteur `TeleportStrike`
`GetConnectedPathTo` recoud **tout** le trajet par une beeline et `tilesMovedThisTurn` **EST** sa
longueur en arêtes. Oracle direct du substrat. `bloodIntercessor` sur `C1_74`, seed 777 :

| couple | NATIF | beeline(G) | beeline(C) | verdict |
|---|---|---|---|---|
| `(1,5) -> (5,5)` | **6** | 4 | 6 | CANAL |
| `(5,5) -> (1,5)` | **6** | 4 | 6 | CANAL |
| `(1,5) -> (6,7)` | **6** | 5 | 6 | CANAL |
| `(6,5) -> (4,4)` | **3** | 2 | 3 | CANAL |
| `(1,6) -> (5,5)` | **5** | 4 | 5 | CANAL |

**5 discriminantes / 5 CANAL, 0 GEOMETRIE**, plus **3 témoins** (`G == C`) tous justes. Le port
d'avant rendait donc **4 là où le natif enregistre 6** : une erreur de 50 % sur un compteur qui
alimente du dégât, sur un board du pool.

**Le pool concerné n'est pas anecdotique** : le refus de `HasEdge` est porté par le terrain
`Bridge` (dérivé des 3 boardGraph — les 16 arêtes de `C1_74` se ventilent en 8 sortantes des deux
`Bridge` + 8 entrantes chez leurs voisins, et aucun autre `tileDefId` n'a de masque partiel).
**287 des 779 boards dumpés en portent au moins un** (795 `Bridge` au total ; 241 `global`,
32 `pvp`, 14 `syncPvp`). ⚠ C'est un ESTIMATEUR : le porteur est dérivé de trois boards mesurés, et
un `Bridge` isolé peut ne raccourcir aucun trajet utile.

### 14.5 Les contre-épreuves — chacune mord sur SON gisement, et PAS ailleurs

| mutant | board | mesures discriminantes | désaccords |
|---|---|---|---|
| `--mutate-geometric` (le port d'AVANT) | `C1_74` (`G \ C` = 16) | 3 | **3** |
| `--mutate-geometric` | `MC1_67` (`G \ C` = 0) | 3 | **0** — hors gisement |
| `--mutate-native` (le champ amputé) | `MC1_67` (`C \ N` = 18) | 3 | **3** |
| `--mutate-native` | `C1_74` | 2 | **0** — hors gisement |

⚠ **Le premier `--mutate-native` a été joué sur `C1_74` et est revenu VERT.** Sur une
contre-épreuve, vert est le résultat SUSPECT — ici il ne l'était pas : sur ces couples `N` et `C`
donnent la même longueur. La leçon est que le critère de discrimination doit se dériver du
MUTANT : le probe le calcule désormais sur les **trois** vues (`len({lg, lc, ln}) > 1`), sans quoi
le bras `native` était structurellement incapable de mordre sur son propre gisement.

Côté OFFLINE, les trois gardes mordent aussi : la beeline sous « géométrie partout », la marche et
`IgnoreTerrain` sous « porte d'élévation retirée » — c'est-à-dire dans le monde où le no-op serait
faux. ⚠ La mutation « géométrie partout » laisse la marche VERTE : le test compare deux BOARDS
(avec/sans canal), donc une mutation qui frappe les deux côtés lui est structurellement invisible.

### 14.6 Deux gardes de montage payées à la mesure

* **`ResetThisTurn` avec le porteur SEUL côté joueur** : son move est celui de la dernière unité
  activable, donc le tour bascule et `+0xf0` retombe à zéro — **7 pseudo-désaccords d'affilée**,
  tous lus `NATIF=0`. §6 le documentait déjà, mais son discriminant (« une AUTRE unité a vu son
  compteur diminuer ») est aveugle quand personne d'autre n'a bougé. Deux figurants le ferment, et
  un delta NUL sur un move réel est désormais rendu **NON MESURÉ**.
* **`GetConnectedPathTo` ne recoud QUE `if (GetDistance(last, next) > 1)`.** À distance 1 la
  beeline n'est jamais appelée : le couple ne discrimine RIEN. Sans ce filtre, `(6,5) -> (5,5)`
  s'étiquetait « GEOMETRIE » et accusait à tort le canal — alors que le port y était juste.

### 14.7 Reproduction

    python probe_448r1r1r1r1r2r1_pathfinder_rebranch_live.py                      # STRUCT, 3 boards
    python probe_448r1r1r1r1r2r1_pathfinder_rebranch_live.py --only NATIVE --turns 22
    python probe_448r1r1r1r1r2r1_pathfinder_rebranch_live.py --only NATIVE --turns 8 --mutate-geometric
    python probe_448r1r1r1r1r2r1_pathfinder_rebranch_live.py --only NATIVE --board MC1_67 --turns 10 --mutate-native
    python -m pytest tests/engine/entities/pathfinding/test_448r1r1r1r1r2_connectivity_channel_offline.py

### 14.8 Ce qui reste OUVERT

* **`#448-r1-r1-r1-r1-r2-r2`** (téléport) — INCHANGÉ : `connectivityTeleportTiles = 0` sur les
  trois boards, aucun des 779 dumps ne porte de tuile de téléport. Le champ est localisé, sa
  VALEUR non nulle reste non confrontée.
* **`#448-r1-r1-r1-r1-r1`** (départage à coût égal de `GenerateBreadthFirstTree`) — INCHANGÉ, et
  toujours inerte : la beeline a un coût quasi uniforme (`10 + IsFilled`).
* ~~**NON CONFRONTÉ** : la route `Fly` pure sur un board à `Bridge`.~~ **FERMÉ le 2026-08-04
  (`#589-r1`, `docs/rl/case-589-r1-aval-tiles-moved.md` §5), et la réponse n'est PAS l'inertie** :
  `blackHaarken` (`ptype = 3`) sur `C1_74` rend **accord CANAL 9/9, accord GÉOMÉTRIE 4/9** — sur
  `(1,5) -> (5,5)` le natif enregistre **6** là où la géométrie donne **4**. La route `Fly` portait
  le même écart de 50 % que `TeleportStrike` ; le rebranchement la corrige aussi.
* ~~**NON MESURÉ** : l'effet aval sur le DÉGÂT des quatre consommateurs.~~ **FERMÉ le 2026-08-04
  (`#589-r1` §4)** : les six call-sites sont ventilés, et le régime décide avant le consommateur.
  Le seul LINÉAIRE (`ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus`) a pour sujet le
  porteur, et `votanChampion` est un MARCHEUR (`ptype = 0`, **0 couple sur 3906**) : l'aval y est
  inerte **par le régime**. Les trois consommateurs à SEUIL (`<= 2`) sont saturés par la borne
  « `n >= 2` dès que la beeline mord », mesurée. Seul `EmpyricAmbush` (`K = movement = 4`) peut
  basculer — 22 à 24 couples sur `C1_74` — et il n'est pas porté. La chaîne, elle, EST sensible :
  greffé sur un volant, le dégât suit `n` à **+1596 / +1600 par tuile** (contre-bras sans greffe :
  pente **0.0**).
* Les **287 boards à `Bridge`** sont un estimateur du gisement, pas une mesure : seul `C1_74` a
  été confronté au natif.

### 14.9 Ce qui resservira — changer un SUBSTRAT partagé

Quatre points de méthode, tous payés par une mesure de cette tranche :

1. **Le no-op se DÉDUIT du prédicat, il ne se constate pas.** Chaque consommateur d'un substrat
   applique son propre filtre APRÈS lui. Si ce filtre refuse exactement ce que le nouveau substrat
   ajoute, le rebranchement est inerte *sur tout board* — pas seulement sur ceux qu'on mesure.
   Classer les consommateurs par la FORCE de leur prédicat avant de mesurer quoi que ce soit :
   ici, celui qui MORD est le seul dont le prédicat est le corps trivial `return true`.
2. **Chercher les consommateurs par le NOM NATIF, jamais par le nom du module.** Le 7e site
   (`are_tiles_adjacent`) n'est pas un pathfinder ; il lit le même substrat par
   `ConnectivityComponent$$IsNeighbour`. Un grep sur `neighbours` l'aurait manqué — il appelait
   `board.neighbours()`, l'accesseur mode-dépendant.
3. **Le critère de discrimination se dérive du MUTANT, et son ORDRE compte.** Deux mutants d'un
   substrat à N vues ont des gisements DISJOINTS (`G \ C` vit sur `C1_74`, `C \ N` sur `MC1_67`) :
   discriminer sur `len({v1..vN}) > 1`, pas sur le couple qui intéresse la thèse. Et trier les
   candidats par le seul écart maximal noie le cas utile dès qu'un autre écart est plus gros —
   mesuré, 22 tours sur `C1_74` sans un seul verdict tranchant.
4. **Chercher le porteur dont la chaîne native DÉGÉNÈRE.** `ATeleportPathfinder$$FindPath` rend
   `[from, to]`, donc pour lui `tilesMovedThisTurn` **EST** la longueur beeline : le substrat
   devient lisible tel quel, sans étage intermédiaire. C'est ce porteur-là le cas discriminant,
   pas le porteur « normal ».

Et une garde : **une garde de PÉRIMÈTRE (« X n'est pas encore fait ») meurt avec la tâche, et
souvent elle ne gardait déjà rien** — celle de `-r2` observait la MARCHE, sur qui le rebranchement
est un no-op, donc elle serait restée verte après. La remplacer par une garde des DEUX faces, et
vérifier que chaque cran mord sous SON mutant. ⚠ Un test qui compare deux MONTAGES est
structurellement aveugle à une mutation qui frappe les deux côtés.
