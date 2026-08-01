# case-403 — le `FlyPathfinder` n'est pas un `WalkPathfinder` qui ignore l'élévation

Ferme `#381-r2`, dernier écart du pool de tuiles mobiles. **DEUX maillons**, tous deux dans
`fly_pathfinder`, tous deux trouvés au décompilé puis confrontés live.

## 1. Le gate d'expansion #131 ne vaut PAS pour le vol

`IdunBattle.Entities.Pathfinding.BasePathfinder$$NodesInNextLevel` interroge un slot virtuel avant
d'étendre la fill (`vslot 10`, `(**(code **)(*(longlong *)this + 0x1d8))`), et le port lui passait
le prédicat de la MARCHE pour tous les pathfinders. Il n'y a pas droit :

* `IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons` est le **seul**
  producteur du bit `BlockEnteringUnits`, et ses XREFS sont EXHAUSTIVES — cinq appelants, tous
  dans la branche marche : `WalkPathfinder$$IsValidContinuePathTile`, `$$GetEffectiveDepth`,
  `$$WeightCost`, `IgnoreDoorPathfinder$$IsValidContinuePathTile`,
  `WaveValidatorPathfinder$$IsValidContinuePathTile` ;
* `FlyPathfinder` dérive de `BasePathfinder`, **pas** de `WalkPathfinder`
  (`data/symbols/<build>/frida/classes.tsv`), et `IgnoreDoor`/`WaveValidator` sont les deux seules
  sous-classes de `WalkPathfinder`.

Le corps du `vslot 10` du `FlyPathfinder` reste non nommable (dédup IL2CPP), mais les deux seules
formes compatibles sont **indiscernables ici** : `true`, ou le corps
d'`IgnoreTerrainPathfinder$$IsValidContinuePathTile` = `TileExtensions$$IsWalkable(tile,
checkFog: true)` — que l'arête a déjà exigé de toute tuile atteinte.

MESURE — `C2_26`/38104, `overrideRange` 2, T+6 `endturn` : `bloodIntercessor` natif **13** /
port **12**. La tuile manquante est `(0,2)`, qui ne pend que du Swamp `(1,2)`. Après : **13/13**.

## 2. L'arête FLY n'est pas `IsWalkable` — `#403-r1`

`FlyPathfinder$$IsValidPathNode` = `TileComponent[+0x40] == 0 && [+0x41] == 0` =
`!IsInFogOfWar && !IsWall` (offsets recoupés : `FlyPathfinder$$IsAnyAdjacentTileWall` teste
`+0x41` ; `TileExtensions$$IsWalkable(tile, checkFog)` teste `+0x40` sous le nom `checkFog` ;
`frida/hooks/game/match-state.ts` nomme les deux). `IsWalkable`, lui, teste
`MovementComponent[+0x10] == 0 && TileComponent[+0x40] == 0` — un **troisième** champ, celui des
obstacles de décor. Une tuile `Block`/`Water` porte `walkable=False, isWall=False` : **le vol la
survole** sans pouvoir s'y poser.

L'exclusion de l'ARRIVÉE est faite ailleurs, et le port ne l'avait pas non plus :
`MovementQuery$$AnyOrFillMoveableTiles` fait `RemoveAll(t => !IsMovableTile(...))`, et
`MovementQuery$$IsMovableTile` délègue à `TileExtensions$$IsFreeTile(tile, state,
allowSteppable: true, null, ignoreUnitsOnTiles)` dont les deux premiers tests sont, verbatim,
`MovementComponent[+0x10] == 0` puis `TileComponent[+0x40] == 0` — c'est-à-dire exactement
`IsWalkable`. Ils sont testés **avant** le `if (!allowAnyUnit)` : même sous `ignoreUnitsOnTiles`
une tuile non walkable sort du pool.

MESURE — `C2_26`/38104, `overrideRange` 4, T+6 : `tyranNeurothrope` natif **22** / port **21**.
La tuile manquante est `(6,6)`, qui ne pend que du `Block` `(6,5)`. Après : **22/22**.

## 3. Le port

* `fly_pathfinder.is_valid_path_node` = `not board.is_wall(to)` (nouveau, `boardGraph.isWall`) ;
* `walk_pathfinder.get_movable_positions` filtre `visited` **et** `stop` par `board.walkable` —
  mirror explicite du `RemoveAll(!IsMovableTile)`, **no-op pour la marche** (son arête l'exige
  déjà) ;
* `pathfinders.continue_gate_for(type, walk_gate)` : le gate #131 n'est passé qu'à la base MARCHE.
  Les huit décorateurs suivent leur base (`ATeleportPathfinder$$IsValidContinuePathTile` délègue),
  donc 7/9/11/13 n'en ont pas non plus.

## 4. Confrontation

`probe_403_c2_26_fly_gap.py` (localisation + contre-épreuve), `probe_403r1_fly_edge_predicate.py`
(recensement du terrain + arête). Quatre boards, `overrideRange` 2, T+6, roster complet du seed
38104 : **0 écart** sur toute unité que le natif juge mobile — `C2_26`, `MC1_67`, `C1_74`,
`PVP_desert_04`.

Garde : `tests/engine/entities/pathfinding/test_403_fly_no_expansion_gate_live.py` (3 tests,
portées 2..5). AUTO-DISCRIMINANTE par **deux** contre-épreuves — le gate marche remis sur le vol,
et l'arête remise sur `board.walkable` : chaque test exige qu'au moins une mesure CHANGE.
`C2_26` discrimine les deux (6 Swamp, 12 obstacles non-mur) ; `MC1_67` le gate seul (1 obstacle) ;
`PVP_desert_04` est le contrôle négatif (aucun des deux ne doit bouger).

## 5. Ce qui reste

* ~~**`IsInFogOfWar` n'est pas publié** par le `boardGraph`~~ — **PUBLIÉ ET VÉRIFIÉ LIVE le
  2026-08-01** (fenêtre jouée, commit `ec2f944c`). Le capteur le LISAIT depuis toujours
  (`match-state.ts` `tileIsInFog: 0x40`, rendu par `projectTile`) ; seul le retour de
  `ctx.rpc.boardGraph` ne l'exposait pas — une ligne. Mesure sur runner frais : **63 tuiles,
  63 portent `isInFog`**. L'arête de vol du port peut désormais porter `!IsInFogOfWar &&
  !IsWall` comme `FlyPathfinder$$IsValidPathNode` ; **tant qu'elle ne le fait pas, la
  dégradation PERMISSIVE sur la TRAVERSÉE demeure** (l'ARRIVÉE reste gardée par
  `board.walkable`, qui inclut le volet fog). Le verrou de harnais est levé, le port reste
  à faire.
* ~~**`#381-r3` s'affine**~~ — **FERMÉ (2026-08-01)**, `case-381-r3-voisinage-bfs.md`. L'affinement
  écrit ici était juste et il a suffi : la vue dépend du PATHFINDER, `BasePathfinder$$AddNeighbours`
  (d__19) itère le `ConnectivityComponent` et `FlyPathfinder$$AddNeighbours` (d__7) interroge le
  rayon 1. Chaque pathfinder passe désormais SA source ; le `adjacency=` du `Board` ne gouverne plus
  rien. Le vol restait juste sous `evenq` (les probes) mais était FAUX sous `native_sym`
  (`playbook/scene.py`, la PRODUCTION) : `bloodIntercessor`/`C1_74` 45 pour 46 au natif.
* `IsTileReserved` / `IsTilePendingDrafting` / `IsTemporary` d'`IsMovableTile`, et le trait
  `Steppable` d'`IsFreeTile` : non portés (résidus déjà nommés par `case-381-r4`).
