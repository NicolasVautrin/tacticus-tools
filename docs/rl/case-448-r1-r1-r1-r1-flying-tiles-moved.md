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

Le slot 3 résout `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit)` :

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
* **`#448-r1-r1-r1-r1-r2`** — le **substrat de la beeline** (§9) : la géométrie est un
  sur-ensemble du `ConnectivityComponent`, et les deux divergent sur les `Bridge`. Fermer
  demande que le capteur publie le `ConnectivityComponent` BRUT, sans la porte d'élévation —
  c'est-à-dire une modification de `frida/hooks/*`, donc une fenêtre de réinjection.
