# case-205 — le call-site SUMMON de `SortTilesByUtility` : `case.unit` est **NULL**, pas un ensemble

Résidu #165b §4 : `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtilityForSummon` fixe le sélecteur
d'unités à `IdunBattle.Entities.Selectors.AllAliveMachinesSelector`. La fiche #165b en déduisait « un
ENSEMBLE d'unités, pas l'unité qui bouge » et laissait les feuilles gatées sur l'unité muettes, en
nommant le résidu « porter la résolution de ce sélecteur (le `case.unit` natif y est une collection) ».

**Ce n'était pas une collection.** Le décompilé tranche : `case.unit` vaut **`null`**, et le natif
MODÉLISE ce cas explicitement.

## 1. Le critère, tranché au décompilé

### 1.1 `dc.unit` est un IEntity SINGULIER, pas une liste

`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select`, remis en C# :

```csharp
dc.tiles  = this.tiles.<itf ITargetsSelector slot 10>(entities);        // IList<IEntity>
dc.unit   = this.unit .<itf ITargetsSelector slot  7>(entities, 0);     // IEntity   <- SINGULIER
dc.parent = this.parent.<itf ITargetsSelector slot 8>(entities, 0);     // IEntity   (0 si sélecteur nul)
dc.dict   = new Dictionary<IEntity, Fix64>();
foreach (tile in dc.tiles) dc.dict[tile] = UtilityDecider.CalculateUtility(tile, definition.Buckets[0], cache);
return dc.tiles.OrderBy(dc.<Select>b__0).ToList();
```

Trois lectures indépendantes le confirment :

* le ctor est `SortTilesByUtilitySelector..ctor(tiles: ITargetsSelector, **unit**: ITargetsSelector,
  utilityDefinition, parent: ITargetsSelector, state, utilitiesDatabase, aiLogger)` — le paramètre
  s'appelle `unit`, au SINGULIER ;
* les deux slots 7/8 prennent un argument supplémentaire (`UnitSelectionType`, littéral `0`) et
  rendent un `IEntity` — c'est la famille `IdunBattle.DSL.TargetsSelector$$SelectUnit` /
  `$$SelectMachine` / `$$SelectActor`, toutes bâties sur « le PREMIER élément de `Select(entities)`
  qui passe le filtre, sinon **null** » ;
* `IdunBattle.AI.Utilities.UtilityMovementCase$$.ctor` a pour signature
  `(unit: IEntity, movementPosition: UnitPosition, closestEnemy: IEntity,
  abilityType: Nullable<ActiveAbilityType>, parent: IEntity)` et
  `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector.u003Cu003Ec__DisplayClass8_0$$u003CSelectu003Eb__1`
  l'appelle en `(dc.unit, tile, null, null, dc.parent)`. Champs : `+0x10 = unit`, `+0x18 = position`,
  `+0x30 = parent`.

### 1.2 Le natif a DEUX accesseurs dédiés au sujet ABSENT

```csharp
// IdunBattle.AI.Utilities.UtilityMovementCase$$get_UnitOrParent
IEntity UnitOrParent => this.unit /*+0x10*/ ?? this.parent /*+0x30*/;

// IdunBattle.AI.Utilities.UtilityMovementCase$$get_IsSpawning   (corps lu en octets)
bool IsSpawning => this.unit == null && this.parent != null;
```

`IsSpawning` n'a de sens QUE pour un `UtilityMovementCase` dont `unit` est nul et `parent` ne l'est
pas — c'est-à-dire exactement la forme que `SortTilesByUtilityForSummon` produit : sélecteur d'unités
« vide », sélecteur `parent` = celui du call-site.

### 1.3 Le sélecteur d'unités de `ForSummon` est un `AllAliveMachinesSelector` SANS provider

Les DEUX surcharges de `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtilityForSummon` construisent
`AllAliveMachinesSelector(state = DSLFactory+0x10, provider = **0**)` — vérifié en octets
(`xor r8d,r8d` juste avant l'appel au ctor, contre `DSLFactory+0x28` pour
`IdunBattleLogic.Entities.DSLFactory$$AllUnits` et l'argument de scope pour
`IdunBattleLogic.Entities.DSLFactory$$Children`).

`IdunBattle.Entities.Selectors.AllAliveMachinesSelector$$Select` est
`return this.<champ +0x18>.<itf slot 0x95>(null);` gardé par un `test/je` vers un `call` noreturn :
avec un provider nul, l'évaluer lèverait une NullReference. **Le sélecteur n'est donc jamais évalué**,
et `dc.unit` reste `null` — la seule lecture compatible à la fois avec `IsSpawning`/`UnitOrParent`,
avec le corps des feuilles (§2) et avec le fait mesuré que les summons se placent sans crash depuis
case-130. Le mécanisme EXACT par lequel le slot 7 rend `null` sans évaluer `Select` n'est pas
départageable au décompilé (corps de `Select*` possiblement surchargé et dédupliqué chez un autre
propriétaire, cf. `CLAUDE.md` « l'absence dans les tables ne prouve rien ») ; le RÉSULTAT, lui, l'est.

## 2. Chaque feuille a sa dégradation NOMMÉE — trois comportements DIFFÉRENTS

C'est le point que le résidu #165b présumait uniforme (« les feuilles gatées par unité restent
muettes »). Le décompilé montre trois régimes distincts.

| feuille | corps natif face `unit == null` | valeur en SPAWN |
|---|---|---|
| `TriggeredAbilities(2)` | `if (case.unit != null) { AbilitiesComponent … LoadPlaybook … }` — sinon on tombe sur `Current = u` avec `u = Fix64.FromInt(0)` | **0** |
| `CapturePoint(24)` | `flag = (unit == null ? parent != null : HasTrait(unit,2)) \|\| HasTrait(unit,13)` — `IsSpawning` INLINÉ | **flag = TRUE** -> `summons_dislike_capture_points` (−300) sur tuile territoire, PAS 0 |
| `PowerUp(26)` | même motif exact, puis `& IsPowerUp(occupant)` | **flag = TRUE** -> `summons_dislike_tiles_with_powerups` (−300), PAS 0 |
| `UnitEffectsAdjacent/Surrounding/Ranged(10/11/12)` | `case.unit` est posé dans le slot SUJET des `AbilityEntities` passées au sélecteur `AdjacentFriends`/`SurroundingFriends` | sélecteur vide -> **0** |
| `SteppableUnit(19)` | `IsEnemy(steppable, case.unit, state)` — `case.unit` passé SANS garde de nullité | dépend de `IsEnemy(x, null, state)` ; gate amont = présence d'une unité steppable sur la candidate |
| `SwornProtector_AvoidAdjacentEnemies` (hors `Tile(7)`) | `UtilityMovementCase$$get_UnitOrParent` | **le PARENT** |

Deux autres feuilles complètent le tableau, avec ENCORE deux formes différentes :

| feuille | corps natif face `unit == null` | valeur en SPAWN |
|---|---|---|
| `DespoiledGround(28)` | `if (case.unit == null) yield break;` en PREMIÈRE instruction — l'itérateur n'émet AUCUN step | **0** (par yield-break, pas par `yield return 0`) |
| `HeroLikeDoorOpening(30)` | `if (case.unit == null \|\| !HasTrait(case.unit, 0x10)) yield return 0;` | **0** |
| `SummonDislikeDoorOpening(29)` | `if (case.parent == null) { if (IsControlledByHumanPlayer(case.unit) && (case.unit == null \|\| !HasTrait(case.unit,2))) -> 0 }` — le test de PARENT vient EN PREMIER et court-circuite | **gate BYPASSÉ** (l'unité est « affected ») |

Lecture de synthèse : le natif **ne prend ni l'ensemble ni un représentant**. Il pose `unit = null`,
garde le `parent`, et laisse CHAQUE feuille décider — 0 pour le dispatcher de playbooks (et pour les
deux feuilles de porte à gate de trait Hero), `IsSpawning` (donc « traite le sujet comme un summon »)
pour les feuilles à gate de trait 2/13, le parent pour celles qui appellent `UnitOrParent`.

## 3. Ce que la mesure ÉTABLIT — et ce qu'elle RÉFUTE

Harnais : `scripts/python/probe_205_summon_tile_subject.py` (`--boards a,b`, `--strict`, `--geom N`,
`--scan-only`). Il cherche OFFLINE une géométrie où deux lectures du sujet DIVERGENT, la DRIVE live,
déclenche le spawn et confronte.

* **summoner** = `admecMarshall` (Tan Gi'da) — HERO présent dans `rl_duel.py build --list-pool`. Son
  passif (1200) n'est dans AUCUN playbook de mouvement porté ⇒ sous `H_PARENT` la feuille 2 rendrait
  aussi 0 : **`H_PARENT` et `H_NULL` coïncident live**, `H_PARENT` est réfuté au décompilé (§2), pas
  ici. Le placement mesuré est celui de `ControlEdictAbility$$SummonMinion` =
  `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(caster)), 7, caster), 1)`.
* **témoin** = `templAncient` (HERO, pool), porteur d'`AstartesBanner` (1106) =
  `5 × |amis à r ≤ 2 de la tuile candidate, self inclus|`. C'est lui qui rend `H_FIRST` (« le sujet est
  la tête de l'ensemble `AllAliveMachines` ») OBSERVABLE — et c'était l'hypothèse la plus plausible a
  priori, puisque la famille `IdunBattle.DSL.TargetsSelector$$SelectMachine`/`$$SelectUnit`/
  `$$SelectActor` rend précisément « le PREMIER élément qui passe le filtre ».
* Le scan exige que le **terme de tuile VARIE** (élévations et/ou terrains distincts) **et** que la
  tête `H_NULL` soit **STRICTEMENT** meilleure : sinon c'est l'ordre du sélecteur source (tri stable)
  qui tranche et le montage ne teste plus le composite.
* **Piège de mesure corrigé en cours de route** : la cible doit être ADJACENTE au caster pour que
  l'attaque normale porte — elle OCCUPE donc une tuile du pool `CanAddUnit(AdjacentTiles(caster))` et
  l'AMPUTE. Une première passe scannait sans elle : les deux montages sont devenus tautologiques
  au drive (`H_NULL == H_FIRST` sur le pool résiduel). Le scan place désormais les TROIS unités.

| # | board | Tan | témoin | cible | pool résiduel `(coord, elev, terrain, u_NULL, u_FIRST)` | `H_NULL` | `H_FIRST` | **NATIF** |
|---|---|---|---|---|---|---|---|---|
| 1 | `MC1_67` | (0,2) | (0,4) | (0,3) | (1,3) e4 **Swamp** `25 / 40` · (1,2) e2 Grass `20 / 30` · (0,1) e3 Grass `30 / 40` | **(0,1)** | (1,3) | **(0,1)** |
| 2 | `C4_09` | (0,7) | (0,4) | (1,8) | (0,8) e2 Grass `20 / 25` · (1,7) e1 **DryBush** `19 / 24` · (0,6) e1 **DryBush** `19 / 29` | **(0,8)** | (0,6) | **(0,8)** |

Les termes qui tranchent sont NOMMÉS : `ElevationUtility` (10/niveau) dans les deux ; `TileEffects`
**−25** (`Thorns_DefenseReduction` de la `Swamp`, canal Loop1) au montage 1 — sans lui le marécage à
élévation 4 gagnerait ; `TileEffects` **+9** (`LightCover` hébergé par la `DryBush`, canal Loop2) au
montage 2. Dans les deux cas la tête `H_NULL` est STRICTE.

**Bilan : 2 montages, 2 boards, 2 fois la tuile prédite avec `case.unit == null`, et 2 fois
`H_FIRST` désigne une AUTRE tuile que le natif.** L'hypothèse « le sujet est un représentant de
l'ensemble » est RÉFUTÉE ; celle du résidu #165b (« `case.unit` est une collection ») n'a jamais été
la bonne question.

## 4. Le port

`engine/utilities/tile.py` :

* **`sort_tiles_by_utility(state, tiles, wt, unit_id, utility_type, parent_id=None)`** et
  **`first_tile_by_utility(..., parent_id=None)`** — `parent_id` EST le `parent` natif, 3ᵉ argument de
  `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtilityForSummon`.
* **`runner_tile_leaf_ctx(state, unit_id, parent_id=None)`** — `unit_id is None` produit désormais
  `{"is_spawning": True}` quand `parent_id` est renseigné (le call-site SUMMON), `{}` sinon. Le régime
  `unit_id` renseigné gagne `is_spawning: False` ; `tile_leaf_ctx` (face DÉCISION) aussi — le sweep de
  mouvement part TOUJOURS d'une unité existante.
* Six feuilles portent maintenant leur dégradation NOMMÉE au lieu de dépendre d'un `ctx` vide :
  `CapturePoint(24)` et `PowerUp(26)` (flag `IsSpawning` INLINÉ), `SummonDislikeDoorOpening(29)`
  (`case.parent != null` en tête de gate), `DespoiledGround(28)` et `HeroLikeDoorOpening(30)` (0),
  `TriggeredAbilities(2)` (0). **La différence n'est pas cosmétique** : sur une tuile territoire, le
  ctx vide rendait `heroes_on_capture_points` = **+300** là où le natif rend
  `summons_dislike_capture_points` = **−300** — 600 points d'écart, dans le mauvais sens.

`engine/runner/operations/spawn.py::_sort_tiles_by_utility_for_summon` passe `parent_id=caster_id`
(son 3ᵉ argument, jusqu'ici documenté « n'est PAS lu »). Tous ses appelants en héritent :
`execute_squighound_summon`, `execute_control_edict_summon`,
`operations/triggers/loki/spiritual_leader.py`.

`engine/runner/abilities/astramilitarum.py::forward_spotter_pick_tiles` gagne `owner_id` (le
`owner@0x148` natif), passé par `ForwardSpotterAbility.execute_behaviour`.

## 5. Ce qui n'est PAS couvert

* **Les trois feuilles à `IsSpawning` restent DORMANTES dans ce foyer** : `sort_tiles_by_utility`
  construit un `meta` réduit (`elevation`, `elevation_max/min`, `effects`) et ne pose ni
  `is_territory`, ni `occupant_is_powerup`, ni `door`. Le comportement est désormais JUSTE dès que la
  metadata arrivera, mais il n'est pas confronté live ici — et il ne peut pas l'être : les seeds arène
  n'ont **aucune** tuile territoire (mesuré #175), et aucun RPC ne remonte power-up ni porte.
* **`H_PARENT` n'est réfuté qu'au décompilé.** Aucun summoner du pool ne porte un passif enregistré
  dans `TRIGGERED_MOVE_PLAYBOOKS` (balayage des 669 kits : `adeptCelestine` 1048, `bloodMephiston`
  1247, `necroOverlord` 1045, `necroSpyder` 1006, `templAncient` 1106, `tyranTyrantGuard` 1181,
  `ultraCalgar` 1014 — et aucun de ces sept n'a d'ability passant par
  `SortTilesByUtilityForSummon` ; `necroSpyder`/ScarabHive passe par `SortByDistance`). Le montage
  live ne peut donc pas séparer `H_PARENT` de `H_NULL` ; c'est le test `case.unit == null` PUIS
  `case.parent != null` de `CapturePointTileUtility`/`PowerUpTileUtility` qui le fait — il serait
  mort si `unit` valait déjà le parent.
* **Le mécanisme exact par lequel le slot rend `null`** n'est pas départageable au décompilé :
  `AllAliveMachinesSelector$$Select` est `this.<+0x18>.<itf slot 0x95>(null)` gardé par un `test/je`
  vers un `call` noreturn, et `SortTilesByUtilityForSummon` construit ce sélecteur avec `+0x18 = 0`
  (lu en octets) — l'évaluer lèverait donc une NullReference. Le corps réellement invoqué par le slot
  7 est probablement un override dédupliqué chez un autre propriétaire (`CLAUDE.md`, « l'absence dans
  les tables ne prouve rien »). Le RÉSULTAT (`unit == null`) est établi par trois faits indépendants ;
  le CHEMIN reste un résidu de RE, sans conséquence sur le port.
* **`TileDistance(33)` avec `dc.parent`** : la branche `else if (c.owner != null) DistanceTo(c,
  c.owner)` n'est pas portée. Elle n'est atteignable que sur le call-site SUMMON, or ses occurrences
  passent toutes `UtilityDefinition(7 = Tile)`, jamais `0x20 = MovementSuggestion` — porter la
  position du parent serait spéculatif. Résidu NOMMÉ.
* **`SteppableUnit(19)` en spawn** : le natif passe `case.unit` (donc `null`) à
  `IdunBattle.Entities.UnitExtensions$$IsEnemy(steppable, null, state)` SANS garde de nullité. La
  valeur de retour de cet appel n'est pas tranchée, et le foyer ne pose pas `meta.steppable` — la
  feuille rend 0 des deux côtés. Résidu NOMMÉ, à rouvrir le jour où `CanAddUnit` laissera une tuile
  occupée par un steppable entrer dans le pool.

## 6. Cliquet

`tests/engine/runner/test_placement_sort_rng_live.py` — deux tests ajoutés au fichier qui garde déjà
les quatre sites de placement :

* `test_summon_case_unit_is_null_not_a_stand_in` — la tuile où le natif POSE le summon est celle du
  composite évalué avec `case.unit == null` ;
* `test_summon_subject_scenario_refutes_a_stand_in` — ANTI-TAUTOLOGIE : sur CHAQUE montage,
  l'hypothèse « sujet tiré de l'ensemble » désigne une AUTRE tuile.

Les deux **cherchent eux-mêmes** leur géométrie sur l'état live (terme de tuile qui varie + tête
STRICTE) et **échouent** — pas `skip` — si moins de deux montages discriminants sortent. Aucune valeur
gelée : les classements sont recalculés sur l'état live après le drive.
