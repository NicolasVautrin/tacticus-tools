# case-381-r1 — `MovableTilesInRange` rendait un DISQUE ; le natif rend un pathfinding filtré

Ferme le résidu `#381-r1` (nommé par `case-361` §8, re-mesuré par `case-383` §5). Suites ouvertes,
toutes DISTINCTES et toutes préexistantes : `#381-r2` (§5), `#381-r3` (§5), `#381-r4` (§5).

## 1. La lecture qui était fausse — le 4ᵉ argument n'est pas un `canReachOnly`

Le nœud prend **CINQ** arguments, et le port en lisait quatre :

```
IdunBattleLogic.Entities.DSLSelectors$$MovableTilesInRange(unitSelector, unitTileSelector,
                                                           overrideRange, ignoreFlags,
                                                           ignoreUnitsOnTiles)
    -> MovableTilesInRangeSelector$$.ctor : +0x20 unitSelector · +0x28 unitTileSelector
                                            +0x30 overrideRange · +0x38 ignoreFlags
                                            +0x39 ignoreUnitsOnTiles
```

Le port lisait `+0x38` comme un `canReachOnly` qui aurait choisi entre le `visited` et le `stop_set`
du BFS. **Cet axe n'existe pas.** `+0x38` est `ignoreFlags` : il ne fait que désarmer la garde
d'entrée de `MovementQuery$$FindAnyOrAllMoveableTiles` (laquelle rend un set **VIDE**, jamais un set
plus large). Le seul booléen qui élargisse l'ensemble est `+0x39`, et il vaut **`0` sur les cinq
call-sites lus** — `RammingSpeedAbility$$GetTileToMoveTo`,
`VigilanceEternalAbility$$GetPossibleMovementTiles`, `HeroicFusilladeAbility$$ExecuteBehaviour`,
`VigilanceEternalAbility$$GetPossibleAdditionalTargetTilesForDangerZone`, et
`DSLSelectors$$TilesUnitCanMoveToChargeTarget` (qui l'écrit **en dur à 0**, seul `ignoreFlags`
remontant à l'appelant).

La chaîne, lue de bout en bout :

```
MovableTilesInRangeSelector$$Select
  -> BattleQuery$$GetMovableTilesFor(entity, fromTile, ignoreFlags, options)   // ToList(fromTile)
  -> MovementQuery$$GetMovableTilesFor(unit, unitTiles, ignoreFlags, options)
  -> MovementQuery$$FindAnyOrAllMoveableTiles :
        if ((UnitFlagsComponent$$Has(unitFlags, 1) && ignoreFlags == 0)
            || !UnitExtensions$$CanMove(unit))                 return;        // set VIDE  (#381)
        type  = GetPathfinderTypeForUnit(unit, options.pathfinderTypeOverride)
        range = options.overrideRange ?? StatComponent(Movement).CurrentValue
        bonus = options.rangeBonusesOverride ?? GetRangeBonusForUnit(unit, …)
  -> MovementQuery$$AnyOrFillMoveableTiles(tiles, type, unit, range, bonus, ignoreUnitsOnTiles, out):
        range = MovementRangeWithAppliedBonus(unit, range, bonus)
        foreach (start in tiles) {
            r = GetReachableTiles(start, type, range, unit)                    // le PATHFINDING
            r.RemoveAll(t => !IsMovableTile(this, unit, t, ignoreUnitsOnTiles))
            result.AddRange(r) }
```

Les **trois** `RemoveAll` d'`AnyOrFillMoveableTiles` partagent un seul corps
(`MovementQuery.<>c__DisplayClass11_0$$<AnyOrFillMoveableTiles>b__2`, dédupliqué) :

```
IsMovableTile(unit, tile, ignoreUnitsOnTiles) =
      (!IsTileReserved(tile) || IsTileReservedForUnit(tile, unit))
   && !IsTilePendingDrafting(tile, state, null)
   && IsFreeTile(tile, state, allowSteppable: 1, allowTemporaryTile: 0,
                 allowAnyUnit: ignoreUnitsOnTiles)
   && !IsTemporary(tile)
```

⇒ **le pool est TOUJOURS filtré par l'occupation**, tuile de départ comprise (elle porte l'unité).
C'est le `stop_set`, pas le `visited`.

Et le pathfinding est le même foyer que partout : `GetReachableTiles` →
`Pathfinders$$FindReachableTiles` → `BasePathfinder$$FindReachableTiles` =
`ListPool(IterateReachableTiles(start, depth, unit))`, qui délègue à
`BasePathfinder$$GetMovablePositions` — donc **gate d'expansion `NodesInNextLevel` compris**.

## 2. Ce que le port faisait, et pourquoi ça se voyait sur `RammingSpeed`

Aucun call-site du port ne passait `can_reach_only=True` : le nœud rendait **toujours** le
`visited`, et il appelait le pathfinder **sans aucun** des trois étages que
`ai/state_bridge._move_tiles` (le mirror déjà confronté du même RPC) porte :

| étage natif | `_move_tiles` | nœud DSL (avant) |
|---|---|---|
| `RemoveAll(!IsMovableTile)` → stop-set | oui | **non** (`visited`) |
| `NodesInNextLevel` → `IsValidContinuePathTile` (#131) | oui | **non** |
| `GetPathfinderTypeForUnit` → `IsLikeFlying` | oui | **non** |
| occupation par EMPREINTE (`GetTileContent`) | oui | **non** (main tile) |

Derrière l'intersection `op_BitwiseAnd CanAddUnit(...)`, le premier étage est **inobservable** (les
tuiles occupées y étaient déjà retirées). **C'est le deuxième qui mordait** — et c'est la mesure
`case-383` §5 : sur `C1_74`, caster (2,0), cible (3,4), le port désignait (2,4) quand le natif pose
le caster en (4,3).

MESURE OFFLINE, board `C1_74` réel, départ (2,0), portée 5, aucune unité :

| gate #131 | tuiles atteintes | (2,3) | (2,4) | (4,3) | (4,4) |
|---|---|---|---|---|---|
| désarmé (le port d'avant) | 35 | oui | **oui** | oui | **oui** |
| armé (le natif) | 29 | oui | **non** | oui | **non** |

(2,4) et (4,4) ne pendent que d'un **Swamp**. C'est exactement le couple que `case-383` §5 relevait
comme « dans le pool du port, hors des 27 tuiles d'`aiMovableTiles` ».

## 3. Le correctif

`engine/entities/selectors/tiles.py` : `MovableTilesInRange(unit, from_tile, range_amount,
ignore_flags=False, ignore_units_on_tiles=False)` — le nœud rend `stop` (le `visited` seulement
sous `ignore_units_on_tiles`), pose le gate d'expansion (`_movement_can_continue`, nouveau helper),
dispatche le pathfinder par `IsLikeFlying` et lit l'occupation par **empreinte**.
`tiles_unit_can_move_to_charge_target` propage `ignore_flags` et force `ignore_units_on_tiles=0`,
comme le helper natif.

`_movement_can_continue` monte le gate sur le substrat DSL : canal dynamique
`ctx.tile_has_effect(tileId, effectType)` **en union** avec le repli TERRAIN
(`tile_blocking.terrain_blocks_entering`), évalué PAR TUILE et mémoïsé (le BFS n'interroge que ce
qu'il atteint). Le repli est indispensable : la plupart des contextes DSL sont montés sans le canal
opt-in des effets de tuile, et le gate serait INERTE en silence — le résidu fermé par `case-224` §4.

**L'ORDRE n'a pas bougé** : le nœud rend toujours `sorted(...)`, et retirer des éléments d'un
opérande ne réordonne pas les restants. Vérifié par un test dédié
(`test_l_intersection_de_charge_est_inchangee_sur_un_board_sans_blocage`) : le datapoint d'ordre de
`case-353` §5bis est intact.

## 4. La confrontation

`probe_381r1_movable_tiles_pool.py` — le pool du nœud contre `aiMovableTiles`, **nu** (le RPC
appelle littéralement `MovementQuery$$GetMovableTilesFor`, donc l'égalité attendue est EXACTE). Le
probe ventile WALK / VOLANT et écarte les unités dont le pool natif est vide (garde FLAG, non
portée), plutôt que de les compter comme des désaccords.

| board | tuiles block-entering | WALK confrontées | égalité exacte |
|---|---|---|---|
| `MC1_67` | 4 | 9 | **9/9** |
| `C2_26` | 6 | 9 | **9/9** |
| `PVP_desert_04` | 0 | 9 | **9/9** |
| `C1_74` | 2 | 9 | 8/9 → §5 (`#381-r3`) |

Gardes adversariales (le port muté DOIT diverger), sur `MC1_67` :

| mutation | ce qu'elle défait | résultat |
|---|---|---|
| `visited` | l'état d'AVANT ce correctif | **0/9** s'accordent (5 tuiles en trop par unité) |
| `no-gate` | le gate d'expansion #131 | **6/9** s'accordent (3 unités sur-atteignent) |

Gardes committées : `tests/engine/runner/test_381r1_movable_tiles_pool_live.py` (3 boards,
auto-discriminant) et `..._offline.py` (6 tests, board synthétique, sans runner).

## 5. Ce qui reste — quatre résidus, tous DISTINCTS et tous PRÉEXISTANTS

* **`#381` (la garde d'entrée)** — `UnitFlagsComponent$$Has(unitFlags, 1) && ignoreFlags == 0` et
  `UnitExtensions$$CanMove` : `unitFlags` n'a aucun substrat côté port, donc le nœud ne rend jamais
  vide par cette voie. `ignore_flags` est STOCKÉ et ne change rien. Dégradation PERMISSIVE.
* **`#381-r2` — le FlyPathfinder n'itère pas le même voisinage.**
  `FlyPathfinder$$AddNeighbours` (d__7) itère `GetSurroundingTiles(tile, 1)` — le voisinage
  **GÉOMÉTRIQUE** (triple boucle cube de `TileQuery$$IterateSurroundingTiles`) — là où
  `BasePathfinder$$AddNeighbours` (d__19) itère la **liste d'adjacence stockée sur la tuile**. Le
  port de `fly_pathfinder` réutilise le BFS commun, donc le second. Mesuré : `bloodIntercessor`,
  natif 47 tuiles, port 27 (`MC1_67`) ; 46/44 (`C1_74`) ; 32/28 (`C2_26`) ; **égal** sur
  `PVP_desert_04`, où les deux vues du graphe coïncident. Frappe AUSSI `_move_tiles`, jamais
  confronté sur une unité volante.
* **`#381-r3` — le substrat de voisinage du BFS.** Sur `C1_74`, `tauAunShi` sur-atteint de deux
  tuiles ((4,2) Swamp et (5,3)). Ce n'est **pas** le nœud : `_move_tiles` rend exactement le même
  écart, bit à bit. Le `Board` est construit `adjacency="evenq"` (voisinage hexgeo recalculé) alors
  que le natif itère le champ `neighbours` du `boardGraph` ; sur `C1_74` les deux diffèrent sur
  **32 tuiles**, et remplacer l'un par l'autre donne 32 tuiles au lieu de 34 (le natif) — donc le
  champ capté est lui-même incomplet. À trancher sur le CAPTEUR, pas sur le pathfinder.
* **`#381-r4` — les collapses impératifs du même nœud** ne portent ni le gate #131 ni le dispatch
  fly : `abilities/genestealer._charge_candidate_tiles` (HeroicFusillade / VigilanceEternal),
  `triggers/loki/betrayer._betrayer_stop_tile`, `triggers/genestealer._hypersensory_move_dest`
  (portée 1 ⇒ gate structurellement inerte). Le correctif est le même à recopier, avec le re-jeu
  des tests live de chaque ability. Docstrings mises à jour, comportement INCHANGÉ ici.
* **Non portés dans `IsMovableTile`** : `IsTileReserved` / `IsTileReservedForUnit` /
  `IsTilePendingDrafting` / `IsTemporary` (aucun canal offline) et le trait `Steppable` (0x1b) de
  `IsFreeTile(allowSteppable: 1)` — ce dernier volontairement, par SYMÉTRIE avec `CanAddUnit` : les
  deux nœuds s'intersectent, un écart ENTRE EUX serait pire que l'écart commun au natif.
* **`MovementQuery$$GetRangeBonusForUnit` / `MovementRangeWithAppliedBonus`** : tous les call-sites
  portés passent un `overrideRange` explicite et la boucle de bonus est un no-op sur liste vide. Le
  volet `HasTriggeredAbility(0x4b8) || HasTrait(0x418) -> range 0` n'est pas porté ici
  (`services/movement_query.get_movable_positions_for` le porte déjà pour la face empreinte).
* **`WalkPathfinder$$GetEffectiveDepth`** (`Min(1, depth)` sous le bit 0x2 de
  `GetTileBlockingReasons`), appelé au début d'`IterateReachableTiles` : toujours sans datapoint
  (résidu #131 d'origine).
