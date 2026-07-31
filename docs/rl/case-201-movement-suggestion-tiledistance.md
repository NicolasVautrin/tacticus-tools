# case-201 — `MovementSuggestion(32)` = `[Tile(7), TileDistance(33)]` : le composite que `VigilanceEternal` consommait a moitie

Residu nomme de `case-165-collapse-tuile-plus-proche.md` §« ce qui n'est PAS couvert ». Le foyer
`engine/utilities/tile.py::sort_tiles_by_utility` portait, dans sa docstring, une EXCEPTION :

> le call-site `VigilanceEternalAbility$$ExecuteBehaviour` passe `UtilityDefinition(0x20 =
> MovementSuggestion)` [...] `TileDistance` n'etant PAS porte, ce call-site NE PASSE PAS par ici.

`_vigilance_move_dest_tile` gardait donc un collapse local — « la tuile la plus PROCHE du caster,
tie-break par id de tuile ». Ce cas leve l'exception : les deux moities du composite sont portees, le
call-site rejoint le foyer, le collapse disparait.

## 1. Le critere, tranche au decompile

**Q1 — le litteral est-il bien `MovementSuggestion(32)` ?** OUI.
`IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$ExecuteBehaviour` :

```c
uVar9 = VigilanceEternalAbility$$GetPossibleMovementTiles(this, 0);
lVar15 = this->dsl;                                    // this+0x30
uVar9 = DSLFactory$$SortTilesByUtility(lVar15, uVar9, lVar15->caster /*+0x160*/, 0x20, 0, 0);
uVar9 = DSLFactory$$First(lVar15, uVar9, 1, 0, 0);
```

L'octet est lisible aussi a l'encodage : le call-site est precede de `41 b9 20 00 00 00`
(`mov r9d, 0x20`). **Le 4e argument de la surcharge `int` est le littéral d'utilite** — c'est ce
qu'on lit pour classer un call-site, et c'est reproductible sur les 13 call-sites (§5).

**Q2 — la carte de composition donne-t-elle `[Tile(7), TileDistance(33)]` ?** OUI.
`IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities` construit
`UtilitiesDatabase+0x58` = `Dictionary<UtilityType, UtilityType[]>` et y ecrit, entree par entree :

| cle | tableau | lecture |
|---|---|---|
| `7` | 29 elements (`InitializeArray`) | `Tile` = les 29 feuilles deja portees |
| `0x22` = 34 | 13 elements | `Damage` |
| `0x2e` = 46 | 3 elements | `Repair` |
| `0` | `[7, 1]` | `Spawn` |
| **`0x20` = 32** | **`[7, 0x21]`** | **`MovementSuggestion` = `[Tile, TileDistance]`** |
| `6` | `[7, 0x10]` | `UnitMovement` = `[Tile, MinDistanceToClosestEnemy]` |
| `5` | `[6, 0x11]` | `UnitMovementFromTemporary` |

Le tableau de `0x20` est ecrit litteralement `array[0] = 7` puis `array[1] = 0x21`.
`IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` mappe ensuite chaque sous-type via
`IdunBattle.Core.Services.UtilitiesDatabase.u003Cu003Ec__DisplayClass16_0$$u003CGetUtilityu003Eb__0`
(= `GetUtility(sousType, MEME collection)`) et, `Count > 1`, construit un `ComposedUtility`.

**Q3 — existe-t-il une geometrie ou le terme manquant DEPARTAGE ?** OUI, et largement : §3.

## 2. `TileDistanceUtility` au decompile

`IdunBattle.AI.Utilities.TileDistanceUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` +
`IdunBattle.AI.Utilities.TileDistanceUtility$$DistanceTo`, remis en C# :

```csharp
IEnumerator<Fix64> EvaluateMovementInSteps(UtilityMovementCase c) {
    if (c.units != null)      yield return DistanceTo(c, c.units);   // case+0x10
    else if (c.owner != null) yield return DistanceTo(c, c.owner);   // case+0x30
    else                      yield return Fix64.FromInt(0);
}
Fix64 DistanceTo(UtilityMovementCase c, IEntity caseUnit) {
    ITile from = caseUnit.GetMainTile(this.entities);   // this+0x10
    ITile to   = c.position.MainTile;                   // case+0x18 = UnitPosition(tuile candidate)
    int d = this.battleQuery.<slot 0x6b = GetDistance>(from, to);    // this+0x20
    return Fix64.FromInt(-d) / Fix64.FromInt(10);
}
```

Trois faits que le decompile TRANCHE, et qu'il aurait ete faux de deviner :

* **AUCUN poids BC.** Le corps ne touche ni `BaseUtility$$HasUtilityValue` ni
  `BaseUtility$$GetUtilityValue` : le facteur `-1/10` est une constante de code. Contraste avec
  `ElevationUtility`, dont le `10` vient de `Utilities.Default.Elevation.Multiplier`. Rien a cabler
  dans `engine/weights.py`.
* **Signe NEGATIF** — plus loin = pire.
* **Distance HEX, pas cout de chemin.** Le slot `0x6b` du `battleQuery` retombe sur
  `IdunBattle.Core.Services.MovementQuery$$GetDistance`, qui prend le MIN sur les paires de
  `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` des tuiles des deux entites. Les deux arguments
  passent par `GetMainTile` -> mono-tuile -> `hexgeo.distance` exactement.

Le `case.units` du call-site est le sélecteur d'unites que le selecteur resout
(`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` -> `dc.units`), et
`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector.u003Cu003Ec__DisplayClass8_0$$u003CSelectu003Eb__1`
le passe au `UtilityMovementCase(dc.units, tile, null, null, dc.owner)`. Pour `VigilanceEternal`
c'est `caster@0x160` : **`d = hexdist(tuile du caster PRE-move, tuile candidate)`.**

`IdunBattle.AI.Utilities.ComposedUtility.u003CEvaluateMovementInStepsu003Ed__8$$MoveNext` somme les
enfants **sans ponderation** (`Fix64.op_Addition` nu). Le seul poids de la chaine est le
`WeightedUtility.Weight` du bucket, et
`IdunBattleLogic.AI.Utilities.WeightedUtility$$.ctor` le met a `Fix64.FromInt(1)` quand il est null —
ce qui est le cas de la surcharge `int` de `SortTilesByUtility` (`UtilityDefinition..ctor(utilityType)`
-> `UtilityBucket(utilityType, null)` -> `WeightedUtility(utilityType, null)`).

## 3. Le regime ou le terme mord — decomposition PAR TERME

L'ordre de grandeur decide de TOUT. Sur un pool de charge (`move_range` = 2), `d ∈ {1, 2}` donc
`TileDistance ∈ {-0.1, -0.2}`, tandis que les feuilles de `Tile(7)` sont a valeurs entieres
(`Elevation` 10/niveau, `TileEffects` +9 DryBush / −25 Swamp, playbooks 10/30/…). D'ou :

* **`Tile(7)` departage → il DOMINE toujours.** `TileDistance` ne peut pas renverser un ecart >= 1.
* **`Tile(7)` est plat → `TileDistance` departage TOUT** : le classement devient « la plus proche
  d'abord ». C'est exactement ce que le collapse historique reproduisait — et pourquoi il paraissait
  juste (#220 : la geometrie de reference tombait dans ce regime).

Le collapse etait donc faux **des que `Tile(7)` departage**, c'est-a-dire des que les candidates
different d'elevation ou de terrain. Mesure du gisement (`probe_201_vigilance_movement_suggestion.py
--scan-only`) : sur `MC1_67`, **344 couples (caster, cible) divergents sur 847 testes** ; sur
`C4_09`, **236 sur 568**. Ce n'est pas un cas de coin.

Il portait en prime un **tie-break invente** (`, t` = id de tuile) la ou le natif laisse le
`OrderBy` LINQ stable rendre l'ordre du selecteur source.

### 3.1 — Les cinq geometries jouees LIVE

`custoKyrus` (Tyrith, HERO, present dans `rl_duel.py build --list-pool`) vs `necroWarden`,
`--no-ai`, positions DRIVEES par `applyAction move` puis cast reel de 1202. « ANCIEN » = le collapse
supprime ; « Tile(7) seul » = l'autre moitie du composite, isolee ; « 32 » = le port livre.

| # | board / seed | caster | cible | pool `(coord, Tile(7), TileDistance)` | ANCIEN | Tile(7) seul | **32** | **NATIF** |
|---|---|---|---|---|---|---|---|---|
| 1 | MC1_67 / 201201 | (1,4) | (2,6) | (1,6) Swamp `-5 / -0.2` · (2,5) `+20 / -0.2` | (1,6) | (2,5) | (2,5) | **(2,5)** |
| 2 | MC1_67 / 201202 | (1,0) | (1,2) | (0,1) `30 / -0.2` · (1,1) `30 / -0.1` · (2,1) `20 / -0.2` | (1,1) | (0,1) | (1,1) | **(1,1)** |
| 3 | C4_09 / 999 | (3,2) | (5,4) | (4,3) Swamp `-5 / -0.2` · (5,3) `+20 / -0.2` | (4,3) | (5,3) | (5,3) | **(5,3)** |
| 4 | C4_09 / 999 | (3,3) | (2,5) | (2,4) `30 / -0.2` · (3,5) DryBush `39 / -0.2` | (2,4) | (3,5) | (3,5) | **(3,5)** |
| 5 | C4_09 / 998 | (3,3) | (3,5) | (2,4) `30 / -0.2` · (3,4) `30 / -0.1` · (4,4) `30 / -0.2` | (3,4) | (2,4) | (3,4) | **(3,4)** |

Deux regimes SEPARES, chacun sur deux boards :

* **#1, #3, #4 refutent le collapse** — `Tile(7)` tranche et le natif le suit. Le terme est nomme a
  chaque fois : `TileEffects` −25 (`Thorns_DefenseReduction` de la `Swamp`, canal Loop1 — confirme
  par `tileMeta`, qui remonte bien `BlockEnteringUnits` + `Thorns_DefenseReduction` sur (1,6) et
  (4,3)) ; `TileEffects` +9 (`LightCover` heberge par la `DryBush`, canal Loop2) ; `Elevation`
  20 vs 30.
* **#2 et #5 refutent `Tile(7)` seul** — `Tile(7)` est ex aequo et c'est `TileDistance` SEUL, a
  `0.1` d'ecart, qui designe la bonne tuile. **C'est la contre-epreuve de la feuille portee** :
  sans elle, le tri stable rendrait la premiere tuile de l'ordre source ((0,1) et (2,4)), et le
  natif ne la rend PAS.

Aucune geometrie ou le natif suit l'ANCIEN collapse contre le composite. 5/5 pour `MovementSuggestion(32)`.

## 4. Le port

* `engine/utilities/tile.py` :
  * **`TileDistanceUtility`** — mirror 1:1 du corps §2 ; lit `ctx["self_pos"]` (= la position de
    `case.units`, deja posee par `runner_tile_leaf_ctx`/`tile_leaf_ctx` depuis #196) et la position
    candidate (1er argument, deja `(col,row)` depuis #196). `self_pos` absent -> `0.0`.
  * **`MOVEMENT_SUGGESTION_UTILITY`** = `ComposedUtility([TILE_UTILITY, TileDistanceUtility()],
    utility_type=MovementSuggestion)`.
  * **`UTILITY_BY_TYPE`** = mirror reduit de `UtilitiesDatabase$$GetUtility` (`{7: Tile,
    MovementSuggestion, ...}`). `sort_tiles_by_utility` / `first_tile_by_utility` prennent un
    `utility_type` (defaut `Tile(7)` — tous les appelants existants sont inchanges) et **levent**
    sur un type absent de la table plutot que de degrader silencieusement.
    MAJ **#353-r1** : la table s'interroge desormais par `utilities_database(<type>)`, et les deux
    fonctions acceptent AUSSI un `utility_definition` — un call-site peut batir son
    `UtilityDefinition` A LA MAIN avec PLUSIEURS `WeightedUtility` dans le meme bucket
    (`RammingSpeedAbility$$GetTileToMoveTo` : `[Tile(7), RammingSpeed_MostAdjacentEnemies(54)]`),
    ce que le scalaire `utility_type` ne peut pas exprimer. La composition (somme PONDEREE, poids
    par defaut 1) vit dans `engine/utilities/decider.py`.
* `engine/runner/abilities/genestealer.py::_vigilance_move_dest_tile` — le collapse et son
  tie-break par id sont SUPPRIMES ; l'appel devient
  `first_tile_by_utility(state, cands, unit_id=caster_id, utility_type=MovementSuggestion)`.
  Le pool (`_charge_candidate_tiles`) est inchange.

## 5. Residus NOMMES (non traites ici — chacun a son porteur et sa validation)

**Cinq autres call-sites passent `0x20`** et gardent un collapse. Litteraux relus un par un a
l'encodage (`mov r9d, imm32` devant le `call` de la surcharge `int`
`IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtility`) — a ne PAS deduire du nom de l'ability :

| call-site natif | litteral | port |
|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour` | **0x20** | `operations/triggers/loki/betrayer.py::_betrayer_stop_tile` — collapse (et le natif enveloppe d'un `SortByFormula(..., MinPathLength)`, donc le cas n'est PAS le meme que 1202) |
| `...TheBetrayer_TakeTurnAbility$$GetMovementTile` | **0x20** | idem |
| ~~`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour`~~ | **0x20** | **TRAITE (case-206)** — `abilities/loki/strike.py` (et non `bloodangels.py`) : pool ET tri etaient collapses |
| ~~`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour`~~ (== `$$GetMoveBehaviour`, corps INLINE) | **0x20** | **TRAITE (case-206)** — `abilities/orks.py::waaagh_charge_tile` |
| `EnvAngelsOfDeath` · `LightOfSanguinius` · `BurrowersAbility_Appear` (×2) · `HeroicFusillade` · `KissOfDeath` · `WallOfMirrors` | `7` | rien a changer |

Le fix y est desormais un changement d'argument (`utility_type=MovementSuggestion`), mais **chacun
demande sa propre geometrie discriminante live** — les livrer sans confronter serait du port
speculatif. `BlackRage` et `Waaagh` sont fermes par
`case-206-black-rage-waaagh-movement-suggestion.md` (19 poses live, 0 contre-exemple) ; les deux
`TheBetrayer` restent ouverts.

**Autres non-couverts :**

* **La `UtilityConfigCollectionType` que le selecteur passe a `GetUtility` n'est pas lue.** Le cache
  `Func<UtilityType, IUtility>` du selecteur est construit dans `Select` sur une methode
  `<Select>b__…` du `<>c__DisplayClass8_0` qui **n'est pas dans la table de symboles** (corps
  deduplique ; l'appel a la db passe par le slot d'interface `IUtilitiesDatabase`, donc invisible en
  xref). Sans effet mesurable ici : `TileDistance` n'a AUCUNE config, et `GetUtilityConfig` fait
  **fallback sur `Default(0)`** pour toute cle absente de la collection demandee. Le seul ecart
  possible serait `RangedAdjacentEnemy(15)`, la seule cle que `Utilities.MovementSuggestion` porte
  (−50) — feuille non portee (=0 chez nous), gatee sur « le caster a une arme ranged » (Tyrith est
  melee) et, sur ce pool, **constante** (toutes les candidates sont adjacentes a la cible, donc
  toutes auraient le −50) : elle ne peut pas deplacer l'argmax de ce call-site.
* ~~**Le call-site SUMMON** (`SortTilesByUtilityForSummon`) reste sans `unit_id` : son `dc.units` est
  `AllAliveMachinesSelector`, un ENSEMBLE~~ — **CORRIGE par `case-205-summon-sort-tiles-unit-null.md`** :
  `dc.unit` y vaut **`null`** (selecteur construit avec un provider NUL), pas « un ensemble ». Le foyer
  prend un `parent_id` et le ctx porte `is_spawning`. La branche `c.owner` de `TileDistance` reste
  non modelisee, mais elle est INATTEIGNABLE : les six call-sites `ForSummon` passent tous
  `UtilityDefinition(7 = Tile)`, jamais `0x20`. Residu nomme, cf. case-205 §5.
* Les feuilles de `Tile(7)` dormantes faute de metadata par-tuile (case-165b §4) le restent.

## 6. Cliquet

`tests/engine/runner/test_vigilance_eternal_live.py` :

* `test_vig_landing_tile_refutes_closest_tile_collapse` — moitie `Tile(7)` ;
* `test_vig_landing_tile_needs_tiledistance_leaf` — moitie `TileDistance(33)`.

Les deux **cherchent eux-memes** leur geometrie discriminante sur l'etat live, **echouent** (pas
`skip`) s'il n'en existe aucune, drivent les positions, castent 1202 et confrontent la tuile ou le
natif POSE Tyrith. Aucune valeur gelee : les deux tris de reference sont recalcules sur l'etat live
apres le drive. Les 4 tests #220 du meme fichier restent verts.

Harnais de mesure : `scripts/python/probe_201_vigilance_movement_suggestion.py`
(`--scan-only` inventaire, `--scan --against legacy|tile7` scan + cast, geometrie explicite par
`--caster-pos/--target-pos`, decomposition par terme + `tileMeta` live).
