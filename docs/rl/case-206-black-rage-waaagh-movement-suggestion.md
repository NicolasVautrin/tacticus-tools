# case-206 — `BlackRage` (1163) et `Waaagh` (1058) : les deux derniers call-sites `0x20` qui gardaient leur collapse

Résidu nommé de `case-201-movement-suggestion-tiledistance.md` §5. #201 a porté le composite
`MovementSuggestion(32) = [Tile(7), TileDistance(33)]` et branché **un seul** de ses six call-sites
(`VigilanceEternal` 1202) sur le foyer `engine/utilities/tile.py::sort_tiles_by_utility`. Cinq
call-sites gardaient leur collapse ; ce cas en ferme **deux**.

Hors périmètre, et pour cause : les deux `TheBetrayer_TakeTurn` enveloppent l'appel d'un
`SortByFormula(…, MinPathLength)` — cas structurellement différent, à traiter à part.

## 1. Le critère, tranché au décompilé

Les deux call-sites ont **exactement** la forme de 1202.

`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` (phase C) :

```c
uVar12 = BlackRageAbility$$GetPossibleMovementTiles(this, 0);
lVar19 = this->dsl;                                          // this+0x30
uVar12 = DSLFactory$$SortTilesByUtility(lVar19, uVar12, lVar19->caster /*+0x160*/, 0x20, 0, 0);
uVar12 = DSLFactory$$First(lVar19, uVar12, 1, 0, 0);
local_268 = DSLFactory$$MoveUnit(lVar19, lVar19->caster, uVar12, &opts /* 5 sélecteurs NULS */, 0);
```

`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` (étage MOVE) :

```c
uVar16 = WaaaghAbility$$GetPossibleMovementTiles(this, this->dsl->target /*+0x178*/, 0);
uVar16 = DSLFactory$$SortTilesByUtility(lVar20, uVar16, lVar20->caster /*+0x160*/, 0x20, 0, 0);
uVar16 = DSLFactory$$First(lVar20, uVar16, 1, 0, 0);
uVar16 = DSLFactory$$MoveUnit(..., lVar20->caster, uVar16, &opts, 0);
```

Le 4ᵉ argument est le littéral d'utilité (**`0x20` = 32 = `MovementSuggestion`**) : c'est la
surcharge `int` de `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtility`, qui construit
`IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor(0x20)` et délègue à la surcharge objet —
**avec un `ownerSel` NUL** (le wrapper ne passe que 4 arguments, la surcharge objet en attend 5) :
`dc.units = caster@0x160`, `dc.owner = null`.

**Le pool.** Les deux `GetPossibleMovementTiles` sont le MÊME nœud, au bonus d'effet près :

| ability | nœud natif |
|---|---|
| BlackRage | `TilesUnitCanMoveToChargeTarget(caster@0x160, casterTile@0x168, target@0x178, UnitMovementRangeWithBonus(caster, **0x53e**=1342, ConfigConst(0xe)), canReachOnly=**0**)` |
| Waaagh | `TilesUnitCanMoveToChargeTarget(caster@0x160, casterTile@0x168, target, UnitMovementRangeWithBonus(caster, **1099**, Direct(GetNumberConstant(0xe))), canReachOnly=**0**)` |

`IdunBattleLogic.Entities.DSLFactory$$TilesUnitCanMoveToChargeTarget` n'assemble que deux nœuds :
`CanAddUnit(AdjacentTiles(target)) op_BitwiseAnd MovableTilesInRange(unit, fromTile, range,
canReachOnly)`. **L'ordre de sortie est celui de l'opérande GAUCHE** : relu à
`IdunBattle.DSL.CombinedSelector$$SelectIntersection`, qui itère l'énumérable gauche et ne garde que
ce que `right.Contains(item)` valide. C'est ce qui fixe le départage des ex æquo, `OrderBy` LINQ
étant stable.

## 2. Ce que les deux ports faisaient — deux collapses DIFFÉRENTS

**Waaagh** (`abilities/orks.py::waaagh_charge_tile`) : le pool était le vrai nœud DSL, seul le TRI
était collapsé en `sorted(pool, key=(hexdist(caster, tuile), tileId))[0]`.

**BlackRage** (`abilities/loki/strike.py::_black_rage_charge_positions`) : **pool ET tri** collapsés.
Le pool était `board.neighbours(tuile de la cible)` — un ring-1 NU, sans `MovableTilesInRange` et
sans `CanAddUnit` —, trié par `hexdist(caster, tuile)`, la liste ENTIÈRE partant dans un
`FixedTiles` dont la feuille `MoveUnit` retenait la 1ʳᵉ tuile libre+walkable. La docstring justifiait
l'absence de reachability par « déjà garantie par la DÉCISION au moment du cast » : c'est faux — le
gate `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetDynamicInvalidTargetReason`
garantit `Count(pool) > 0`, c'est-à-dire l'EXISTENCE d'une tuile atteignable, jamais que TOUTES les
voisines de la cible le soient.

Les deux collapses ne sont justes que dans le régime `Tile(7)` **PLAT** — où `TileDistance = −d/10`
est le seul terme non nul et ordonne effectivement par distance croissante. Dès que `Tile(7)`
départage, il DOMINE : ses feuilles sont à valeurs entières (`Elevation` 10/niveau, `TileEffects`
+9 DryBush / −25 Swamp) contre `|TileDistance| <= 0.5` sur un pool de charge. Les deux portaient en
prime un tie-break **inventé** (`, t` = id de tuile pour Waaagh ; l'ordre de `board.neighbours`,
trié et symétrisé, pour BlackRage) là où le natif laisse le tri stable rendre l'ordre du sélecteur
source.

**Mesure du gisement** (`probe_206_charge_tile_movement_suggestion.py --scan-only`, board `MC1_67`,
couples (caster, cible) jouables, ancien collapse ≠ nouveau tri) :

| ability | couples testés | divergents | dont `Tile(7)` tranche | dont tie-break | dont hors-pool |
|---|---|---|---|---|---|
| Waaagh | 712 | 400 (plafond de collecte) | 314 | 86 | — |
| BlackRage | 702 | 400 (plafond de collecte) | 290 | 78 | **32** |

La colonne **hors-pool** est propre à BlackRage : l'ancien code désignait une tuile qui n'est même
pas dans le pool natif.

## 3. Les 19 géométries jouées LIVE

`bloodDeathCompany` (Lucien) et `orksWarboss` (Snotflogga) sont tous deux **HERO présents dans
`rl_duel.py build --list-pool`** (rank 17). Board `MC1_67`, `--no-ai`, positions DRIVÉES par
`applyAction move`, puis cast réel de 1163 / 1058. Un runner par cas, disposé après.

« ANCIEN » = le collapse supprimé ; « Tile(7) seul » = l'autre moitié du composite, isolée ;
« 32 » = le port livré.

### 3.1 Régime `Tile(7)` tranche — le régime qui réfute le collapse

| # | ability | caster | cible | pool `(coord, Tile(7), TileDistance)` | ANCIEN | Tile(7) seul | **32** | **NATIF** |
|---|---|---|---|---|---|---|---|---|
| 1 | Waaagh | (3,0) | (1,0) | (1,1) `30/−0.2` · (2,0) `20/−0.1` · (0,0) `30/−0.3` | (2,0) | (1,1) | (1,1) | **(1,1)** |
| 2 | Waaagh | (3,0) | (1,1) | (1,2) `20/−0.3` · (2,1) `20/−0.2` · (2,0) `20/−0.1` · (1,0) `30/−0.2` · (0,0) `30/−0.3` · (0,1) `30/−0.3` | (2,0) | (1,0) | (1,0) | **(1,0)** |
| 3 | Waaagh | (1,0) | (1,3) | (0,2) `30/−0.3` · (0,3) `50/−0.4` | (0,2) | (0,3) | (0,3) | **(0,3)** |
| 4 | Waaagh | (1,0) | (2,2) | (3,3) `30/−0.4` · (3,2) DryBush `29/−0.3` · (2,1) `20/−0.2` · (1,2) `20/−0.2` | (1,2) | (3,3) | (3,3) | **(3,3)** |
| 5 | Waaagh | (3,1) | (1,2) | (2,2) `20/−0.2` · (2,1) `20/−0.1` · (1,1) `30/−0.2` · (0,1) `30/−0.3` · (0,2) `30/−0.3` | (2,1) | (1,1) | (1,1) | **(1,1)** |
| 6 | BlackRage | (3,0) | (1,0) | (1,1) `30/−0.2` · (2,0) `20/−0.1` · (0,0) `30/−0.3` | (2,0) | (1,1) | (1,1) | **(1,1)** |
| 7 | BlackRage | (3,0) | (1,1) | idem #2 | (2,0) | (1,0) | (1,0) | **(1,0)** |
| 8 | BlackRage | (3,1) | (1,2) | idem #5 | (2,1) | (1,1) | (1,1) | **(1,1)** |
| 9 | BlackRage | (0,0) | (1,3) | (1,4) `30/−0.4` · (2,3) `50/−0.4` · (0,2) `30/−0.2` · (0,3) `50/−0.3` | (0,2) | (2,3) | **(0,3)** | **(0,3)** |
| 10 | BlackRage | (1,0) | (1,4) | (2,3) `50/−0.4` · (1,3) Swamp `25/−0.3` · (0,3) `50/−0.4` · (0,4) `30/−0.5` | (1,3) | (2,3) | (2,3) | **(2,3)** |

Les termes qui tranchent sont NOMMÉS à chaque fois : `Elevation` 20 vs 30 vs 50 ; `TileEffects` +9
(`LightCover` hébergé par la `DryBush`, canal Loop2) en #4 ; `TileEffects` −25
(`Thorns_DefenseReduction` de la `Swamp`) en #10 — l'ancien collapse envoyait Lucien charger DANS le
marécage.

**#9 est la contre-épreuve de `TileDistance`** : `Tile(7)` seul rendrait (2,3), les deux tuiles à
`Tile(7) = 50` étant ex æquo ; c'est `TileDistance` SEUL, à `0.1` d'écart, qui désigne (0,3) — et le
natif y va.

### 3.2 Régime ex æquo — le tie-break, seconde moitié du fix

Ici `total32` est ÉGAL entre l'ancien choix et le nouveau : seul l'ordre du sélecteur source (tri
stable) départage, contre le tie-break inventé.

| # | ability | caster | cible | ANCIEN | **32** | **NATIF** | note |
|---|---|---|---|---|---|---|---|
| 11 | BlackRage | (2,0) | (0,0) | (1,0) | (1,1) | **(1,1)** | (1,1)/(1,0) ex æquo à `29.9` |
| 12 | BlackRage | (1,0) | (0,1) | (0,0) | (1,1) | **(1,1)** | (1,1)/(0,0) ex æquo |
| 13 | BlackRage | (0,1) | (1,0) | (0,0) | (1,1) | **(1,1)** | (1,1)/(0,0) ex æquo |
| 14 | Waaagh | (2,0) | (0,0) | (1,0) | (1,1) | **(1,1)** | — |
| 15-17 | Waaagh | — | — | — | — | **=32** | pool amputé par les spawns (§3.3) |

### 3.3 Le piège de mesure : Waaagh SPAWNE avant de bouger

`WaaaghAbility$$ExecuteBehaviour` exécute `Group(spawnB, 0x22)` **avant** `Group(moveB, 0x23)`, et
les 2 Ork Boyz atterrissent sur `PickRandomly(CanAddUnit(AdjacentTiles(casterTile)), 2)` — des tuiles
adjacentes au CASTER, qui **recouvrent souvent le pool de charge**. Le pool que le natif TRIE est donc
le pool POST-SPAWN.

Une première passe du probe prédisait depuis l'état PRE-cast et a produit **un faux contre-exemple**
(caster@(0,1), cible@(1,0) : natif (0,0), port (1,1)). Diagnostic : un Ork Boy avait spawné sur la
tuile 22 = (1,1), qui sort donc du pool ; sur le pool restant, le port désigne (0,0) — le natif était
d'accord depuis le début. Le probe et le test lisent maintenant les tuiles de spawn dans les events
(`Unit_IsSummoned` + `Unit_Foot_Tile_Id_*`) et re-trient le pool amputé : c'est ce qui isole l'étage
TRI, seul objet de ce port, au lieu de mesurer le TIRAGE.

**Bilan : 19 poses live, 19 fois la tuile du composite `MovementSuggestion(32)`, 0 contre-exemple.**

## 4. Le port

`engine/runner/abilities/orks.py` :

* **`waaagh_charge_tile`** — le collapse `sorted(…, key=(hexdist, tileId))` est SUPPRIMÉ ; l'appel
  devient `first_tile_by_utility(state, cands, unit_id=caster_id,
  utility_type=MovementSuggestion)`. Le pool (`waaagh_possible_movement_tiles_selector`) était déjà
  le mirror 1:1 — inchangé. `import hexgeo` devenu mort, retiré.

`engine/runner/abilities/loki/strike.py` :

* **`black_rage_possible_movement_tiles_selector(move_range)`** (NOUVEAU) — mirror 1:1 de
  `BlackRageAbility$$GetPossibleMovementTiles` : `tiles_unit_can_move_to_charge_target(Caster(),
  CasterTile(), Target(), Const(move_range), can_reach_only=False)`. Remplace le ring-1 nu.
* **`_black_rage_move_range(state, caster)`** (NOUVEAU) — mirror de
  `UnitMovementRangeWithBonus(caster, 0x53e=1342, ConfigConst(0xe = extraMovement))` :
  `If(HasEffect(caster,1342), StatAmount(MOVEMENT), Sum(<idem>, bonus))`. Jumeau de
  `orks.py::waaagh_move_range`, à l'`EffectType` près.
* **`_black_rage_charge_tile`** (NOUVEAU, remplace `_black_rage_charge_positions`) —
  `First(SortTilesByUtility(pool, caster, 0x20), 1)` via le foyer. Rend UNE tuile (comme le natif),
  au lieu d'une liste que `MoveUnit` filtrait.
* **`black_rage_tree` éclatée en trois** — `black_rage_set_health_tree()`,
  `black_rage_buffs_tree()`, `black_rage_charge_tree(dest)` — et `BlackRageAbility.execute_behaviour`
  les exécute SUCCESSIVEMENT, mirror des trois `AActiveAbility.Execute`/`ExecuteAtomic` natifs (même
  découpage que `WaaaghAbility`). **Ce n'est pas cosmétique** : les sélecteurs natifs sont PARESSEUX,
  donc `UnitMovementRangeWithBonus` voit l'effet 1342 DÉJÀ posé par la phase B. Le pool doit donc être
  calculé ENTRE la pose des buffs et le move — impossible avec l'arbre monolithique, qui figeait la
  destination avant toute exécution.
* `loki/__init__.py` : exports mis à jour (`black_rage_tree` / `_black_rage_charge_positions`
  disparaissent au profit des cinq nouveaux symboles).

## 5. Cliquet

`tests/engine/runner/test_charge_tile_utility_live.py` — deux tests ajoutés au fichier qui garde déjà
les trois call-sites `Tile(7)` :

* `test_black_rage_charge_tile_follows_movement_suggestion`
* `test_waaagh_charge_tile_follows_movement_suggestion` (SPAWN-AWARE, cf. §3.3)

Les deux **cherchent eux-mêmes** leur géométrie discriminante sur l'état live et **exigent que
`Tile(7)` DIFFÈRE** entre le choix du collapse et celui du port (un cas à `Tile(7)` égal ne testerait
que l'ordre du sélecteur source et laisserait passer le collapse sur toute carte plate) ; ils
**échouent** — pas `skip` — s'il n'en existe aucune, drivent les positions, castent, et confrontent
la tuile où le natif POSE le caster. Aucune valeur gelée : les deux tris de référence sont recalculés
sur l'état live après le drive.

Harnais de mesure : `scripts/python/probe_206_charge_tile_movement_suggestion.py`
(`--ability blackrage|waaagh|both`, `--scan-only` inventaire avec ventilation par étage de
divergence, `--cat TILE7|TILEDIST|TIEBREAK|HORS-POOL` pour ne jouer qu'un régime, `--cases N`
géométries jouées live, décomposition par terme).

## 6. Résidus NOMMÉS

* **Les deux call-sites `TheBetrayer_TakeTurn`** (`$$CreateBehaviour` et `$$GetMovementTile`) gardent
  leur collapse : le natif y enveloppe l'appel d'un `SortByFormula(…, MinPathLength)`, cas
  structurellement différent. Hors périmètre de ce cas, à traiter à part.
* ~~**Le call-site SUMMON** (`SortTilesByUtilityForSummon`) reste sans `unit_id`~~ — **FERMÉ par
  `case-205-summon-sort-tiles-unit-null.md`** : son `dc.unit` vaut **`null`** (ce n'était pas « un
  ensemble »), le foyer prend un `parent_id` et chaque feuille porte sa dégradation nommée.
* **`BlackRage` n'a toujours pas de `TARGETING_OPTIONS`** (une des entrées manquantes du registre) et
  ne porte pas `get_dynamic_invalid_target_reason`. Le gate natif est pourtant désormais trivial à
  poser : `BlackRageAbility$$GetDynamicInvalidTargetReason` est le JUMEAU EXACT de celui de Waaagh —
  `Count(GetPossibleMovementTiles.Evaluate(ents)) > 0 ? 0 : 0x8000000` (`TargetIsInRange`) — et
  `black_rage_possible_movement_tiles_selector` le rend disponible. Non fait ici parce que le masque
  manque : sans `TargetMatchesDynamicRule` dans `TARGETING_OPTIONS`, la règle dynamique n'est jamais
  consultée, donc la poser seule serait inerte. **À livrer ensemble**, hors périmètre de ce cas.
* **`UseActiveAbility` de BlackRage** : le sujet natif est `Alive(caster@0x160)`, le port passe
  `Caster()` nu. Sans effet sur ce chemin (le move ne déclenche aucun after-move — les 5 sélecteurs
  d'options de `MoveUnit` sont NULS —, donc le caster ne peut pas mourir entre la charge et
  l'attaque), mais l'écart structurel est noté.
* Les feuilles de `Tile(7)` dormantes faute de metadata par-tuile (case-165b §4) le restent.
