# R30 — substrat MULTI-HEX : une unité qui occupe N tuiles

**Question** : une unité occupant N tuiles est-elle représentée, positionnée, déplacée et ciblée
par le port comme par le natif ? **Réponse : oui pour N = 1 et N = 3, confronté live.** N = 7 est
porté mais **inexerçable** (aucun producteur dans `gqfc5mff6c`).

## 1. Le modèle natif

Une unité a **N pieds**. Chaque pied est une **entité** à part entière :

```
UnitComponent._feet  @+0x78   OrderedSet<int>            ids des entités-PIEDS
  UnitFoot (entité)           UnitFootComponent          UnitId @+0x10, TileId @+0x14
    Tile (entité)             PositionComponent          col, row
```

| natif | rôle |
|---|---|
| `IdunBattle.Operations.AddUnitOperation$$Execute` | `UnitComponent$$ClearFeet`, puis **un `UnitComponent$$AddFoot` par tuile reçue**, chaque pied créé dans la même boucle avec un id monotone (`PlayerIdGenerator.Next`) |
| `IdunBattle.Entities.UnitExtensions$$GetUnitFeet` / `$$GetUnitFeetIds` | itère `_feet` |
| `IdunBattle.Entities.UnitExtensions$$GetFeetCount` | `GetUnitFeetIds(...).Count` — **compte COURANT**, aucun champ gameconfig ne porte la taille d'une unité |
| `IdunBattle.Entities.EntityExtensions$$GetTiles` / `$$IterateTiles` | les tuiles des pieds, dans l'ordre des pieds |
| `IdunBattle.Entities.EntityExtensions$$GetMainTileId` | pied `_feet[0]` → son `TileId`. **La main tile est la tuile du PREMIER pied** |
| `IdunBattle.Core.Services.MovementQuery$$GetDistance(IList, IList)` | **MIN** de `CubeCoordinate.Distance` sur toutes les paires de pieds ; seed `int.MaxValue`, rendu tel quel sur liste vide |
| `IdunBattle.Core.Services.MovementQuery$$IsValidUnitFeetList` | même élévation partout ; **1** = toujours ; **3** = triangle (3 distances 1 + 3 `IsAdjacent`) ; **7** = centre + anneau ; sinon log « Unsupported feet count » |
| `IdunBattle.Core.Services.MovementQuery$$GetPossibleTileListsFromMovableTiles` | `GetKCombs(tiles, 1|3)` ; pour 7, `{t} + voisins(t)` quand `tiles ⊇ voisins(t)` |
| `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles` | **1 pied = chemin à part** (`ToUnitPositionList`, aucun filtre) ; au-delà, filtre `IsValidUnitFeetList` |
| `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor` | gate `HasTrait(0x418)` (immobile) → vide ; sinon `GetMovableTilesFor` **+ les tuiles courantes** → regroupement |
| `IdunBattle.Entities.TileExtensions$$CanAddUnit` | lit `TileContentComponent` → **une tuile sous un pied est occupée** |

Les tailles 1 / 3 / 7 ne sont pas une hypothèse : l'enum `IdunBattle.Core.Services.TargetingRule`
les **déclare** (`CasterHas1/3/7Tiles` bits 35/36/37, `TargetHas1/3/7Tiles` bits 47/48/49) et
`IsValidUnitFeetList` les impose.

### La forme à 3 pieds

`IdunBattleLogic.Entities.DSLFactory$$ThreeTileUnitSpawnShape` →
`IdunBattle.Entities.Selectors.ThreeUnitSpawnTileShapeSelector`. **XREFS EXHAUSTIVES** :
`DutyEternalAbility` et `AetherStrideAbility`, rien d'autre. **Aucun producteur d'empreinte à 7
pieds n'existe dans ce build** — les branches `7` de `MovementQuery` et de
`DislikeStartingTilesUtility` sont du code mort ici.

* `$$GetArea(ancre)` essaie les directions dans l'ordre **`[1, 0, 5, 4, 3, 2]`** et retient la
  première dont l'aire passe `$$CorrectArea` ; aucune → liste vide (et
  `GetDynamicInvalidTargetReason` refuse la cible).
* `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape(tile, d)` rend
  `new List<>(new HashSet{tile, t1, t2})` → **ordre `[ancre, t1, t2]`**. Le switch branche sur la
  **parité de la colonne** ; les deux tables de deltas sont transcrites dans
  `engine/battle_query.py`.
* `$$CorrectArea` : `Count == 3`, pas de power-up, `CanAddUnit(tile, state, 1, 0, 0)`,
  et `$$CorrectRelationshipInArea` (toutes voisines deux à deux **et même élévation**).

## 2. Le porteur confrontable

`ultraDreadnought` (Galatian) est une **MoW du pool** (`rl_duel build --list-pool`). Son ability
`DutyEternal` (1158) = `RemoveMachine + Spawn(ThreeTileUnitSpawnShape)` → `ultraSmnDreadnought`
apparaît sur **3 tuiles**. Deux leviers : `munitionsCost = 3` (patch
`BC.Player.Players[*].MachineOfWarAmmo`) et `initialCooldownTurns = 2` (tours à faire tourner).

`AetherStride` (1208, `thousDaemonPrince`) est l'autre producteur du même
`ThreeTileUnitSpawnShape` ; son porteur est hors seed BC (`catalog_inject`) — **non exercé**.

`BigTarget` **n'est pas** le marqueur multi-hex : 60 unités le portent (Morvenn Vahl, Farsight,
Gulgortz…), toutes mono-tuile. Le seul marqueur est le spawn shape.

## 3. Les canaux de mesure (aucun nouveau hook)

* **`observeBattle.units[]` émet UNE LIGNE PAR PIED** — `entityId` du pied, `squadId` de l'unité,
  col/row. C'est le canal complet ET ordonné : `entityId` croissant == ordre d'`AddFoot` ==
  ordre de `_feet` (les pieds sont créés dans la boucle d'ajout, id monotone). Mesure Galatian :
  `108 → (2,1)`, `109 → (2,2)`, `110 → (3,2)`.
* ⚠ **`decisionView.units[].pos` n'est PAS la main tile.** Le projecteur émet une ligne par pied
  (`projectMatchState` : *« one entry per visible piece, walking UnitFoot → Tile »*) et
  `decisionView` **déduplique** : pour un Galatian ancré en `(2,1)` il rend `(3,2)`, c'est-à-dire
  le **dernier** pied. Un port qui prendrait `pos` pour l'ancre se tromperait d'un à deux hexes
  sur toute unité multi-hex.
* `applyAction.changes[]` (une entrée `appeared` par pied), tags `Unit_Foot_Tile_Id_1..3` de
  l'event de spawn, `boardGraph.tiles[].occupantUnitId`, `abilityReason`.

## 4. Ce qui est porté

| fichier | contenu |
|---|---|
| `engine/runner/components.py` | `UnitComponent.feet` (mirror `_feet`, **`None` = 1 pied** → cas nominal intact), `add_foot` / `clear_feet`, `get_unit_feet` / `get_feet_count` / `get_main_tile`, `set_unit_feet` (écrivain UNIQUE, maintient `feet[0] == PositionComponent`) |
| `engine/runner/state.py` | `State.unit_at(pos)` / `State.occupied_positions()` — occupance **par pied** |
| `engine/services/movement_query.py` | `get_distance`, `get_entity_distance`, `is_adjacent`, `is_valid_unit_feet_list`, `get_possible_tile_lists_from_movable_tiles`, `get_movable_positions_from_tiles`, `get_movable_positions_for` |
| `engine/services/spawn_tile_shape.py` | `ThreeUnitSpawnTileShapeSelector` : `get_area`, `correct_area`, `correct_relationship_in_area`, `DIRECTION_ORDER` |
| `engine/battle_query.py` | `get_tiles_in_triangle_shape` (tables de forme par parité de colonne) |
| `engine/runner/abilities/targeting.py` | `get_range_broken_rule` raisonne sur les **empreintes** ; `are_entities_adjacent` (surcharge LISTE de `MovementUtil$$AreTilesAdjacent`) |
| `engine/runner/snapshot.py` | `_load_feet` — seed depuis `observeBattle`, trié par `entityId` de pied |
| `engine/ai/utilities.py` | `DislikeStartingTilesUtility` : empreinte candidate = `[MainTile]`, étendue de l'anneau **si et seulement si `feetCount == 7`** ; test final = chevauchement d'ensembles |

**Non-régression du cas nominal** : une unité à 1 pied garde `feet = None`, son empreinte est
`[PositionComponent]`, et les deux chemins natifs à part (`GetMovablePositionsFromTiles` cas 1,
`IsValidUnitFeetList` cas 1) rendent le comportement bit-à-bit identique.

## 5. Validation

* `tests/engine/runner/test_multihex_substrate.py` — 18 assertions offline (formes, accesseurs,
  occupance, géométrie, feuille 27), dont la garde explicite de non-régression mono-tuile.
* `tests/engine/runner/test_multihex_dutyeternal_live.py` — 7 tests, confrontation live :
  empreinte native == prédiction du port (**ordre compris**), `decisionView.pos` == dernier pied,
  occupance native des 3 tuiles, état du port rechargé, exclusion des pieds de `aiMovableTiles`,
  portée mesurée sur l'empreinte entière.
* **Chiffre discriminant** (garde vue rouge en désarmant `_load_feet`) : attaquant en `(2,0)`,
  Galatian ancré en `(2,1)`, pieds `(2,1)/(2,2)/(3,2)`. Natif : **en portée** de mêlée.
  Port sans substrat : distance **2** (il ne voit que `(2,2)`, le pied que `decisionView` rend)
  → refus. Port avec substrat : distance **1** → accord.
* `probe_r30_multihex.py` — le probe de mesure autonome.

## 6. Résidus (nommés, non couverts)

1. **`HasPowerup` dans `CorrectArea`** : le port ne modélise pas les power-ups de tuile → il est
   plus permissif qu'un natif sur un plateau qui en porte. `IdunBattle.Entities.TileExtensions$$HasPowerup`.
2. **Le centre d'une empreinte à 7** vient d'un slot d'interface non nommé
   (`<IBattleQuery slot 0x5d>(tiles)`). Le port applique la définition géométrique que la branche
   impose juste après (unique tuile adjacente aux 6 autres) — cohérente avec le producteur, mais
   **inexerçable** : aucun contenu ne produit 7 pieds dans ce build.
3. **Le gate `HasTrait(0x418)`** (immobile) de `GetMovablePositionsFor` n'est pas reproduit dans
   `movement_query.get_movable_positions_for` (il appartient à l'appelant qui connaît les traits).
   Sans conséquence tant que le seul multi-hex du build a `Movement = 0`.
4. **`MoveUnitOperation` ne déplace toujours qu'une tuile.** Le canal `MoveUnitMessage.
   UnitFeetPositions` accepte déjà un footprint côté hooks (`buildMoveMsg`), mais aucune unité
   multi-hex de ce build ne bouge (`ultraSmnDreadnought` : `Movement = 0`, décrit « stationary »).
   Le déplacement multi-hex est donc **porté au niveau des positions légales**
   (`get_movable_positions_from_tiles`) et **non confrontable live** — à rouvrir dès qu'un
   porteur mobile existe.
5. **Le poids BC `DislikeStartingTiles`** reste non identifié (`_WEIGHT = 0.0`) — data-gap
   antérieur, hors périmètre ; seul le trou `GetFeetCount` est comblé.
