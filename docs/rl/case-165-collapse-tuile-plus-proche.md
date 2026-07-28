# case-165 — `SortTilesByUtility` : le collapse « tuile la plus PROCHE » de-forke sur les 3 ports freres

`SkyStrike` (1025), `HeroicFusillade` (1180) et `ForwardSpotter` (1143) choisissaient leur tuile
(atterrissage de charge / tuile de spawn) par un collapse imperatif, la ou le natif applique
`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select`. Les trois sont corriges et
**valides LIVE sur une geometrie ou l'ancienne et la nouvelle regle DIVERGENT**.

## 1. Le natif — un seul artefact, quatre call-sites

`IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtility` a **deux surcharges** : celle qui prend un
`int` construit `IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor(utilityType)` et delegue a celle
qui prend l'objet ; `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtilityForSummon` fait pareil en
fixant le selecteur d'unites a `IdunBattle.Entities.Selectors.AllAliveMachinesSelector`. Les deux
finissent sur le MEME `SortTilesByUtilitySelector`, dont le `Select` remis en C# donne :

```
dc.tiles = this.tiles.Select(entities) ; dc.units = this.units.Select(entities)
dc.owner = this.owner.Select(entities) ; dc.dict  = new Dictionary<Tile, Fix64>()
foreach (tile in dc.tiles)
    dc.dict[tile] = UtilityDecider.CalculateUtility(tile, this.definition.Buckets[0], cache)
return dc.tiles.OrderBy(dc.<Select>b__0).ToList()      // b__0 = Fix64.op_UnaryNegation(dict[tile])
```

`<Select>b__0` rend l'OPPOSE de l'utilite -> **tri DECROISSANT**, et `OrderBy` LINQ est **STABLE** :
l'ordre du SELECTEUR SOURCE tranche les egalites. **ZERO tirage** (le tri ne touche pas le PRNG).
`<Select>b__1` construit `UtilityMovementCase(dc.units, tile, null, null, dc.owner)`.

Litteral d'utilite LU call-site par call-site :

| ability (symbole) | selecteur source | `UtilityDefinition` |
|---|---|---|
| `HammerOfWrathAbility$$ExecuteBehaviour` | `Filter(CanAddUnit(AdjacentTiles(target)), MinDistance <= range)` | **7 = Tile** (objet) |
| `SkyStrikeAbility$$ExecuteBehaviour` | `CanAddUnit(AdjacentTiles(target))` | **7 = Tile** (objet) |
| `HeroicFusilladeAbility$$ExecuteBehaviour` | `CanAddUnit(SurroundingTiles(target, radius)) & MovableTilesInRange(caster, range, reachOnly)` | **7 = Tile** (litteral int) |
| `ForwardSpotterAbility$$PickTiles` | `CanAddUnit(AdjacentTiles(target)).Otherwise-filtre` | **7 = Tile** (`ForSummon`) |
| `VigilanceEternalAbility$$ExecuteBehaviour` | `GetPossibleMovementTiles` (= le pool HeroicFusillade, radius 1) | **0x20 = 32 = MovementSuggestion** |

## 2. Verdict par item

| item | verdict | ce qui a change |
|---|---|---|
| **HeroicFusillade (1180)** | **quirk porte** | `_hf_move_dest_tile` appelle le foyer `first_tile_by_utility` ; le pool est extrait dans `_charge_candidate_tiles` (partage avec VigilanceEternal) et l'ORDRE du selecteur y est desormais PRESERVE (il passait par un `set()`, qui le detruisait) |
| **SkyStrike (1025)** | **quirk porte** | `_sky_strike_dest_tile` : tri `Tile(7)` + ordre source `board.neighbours_native` (mirror d'`AdjacentTilesSelector`) au lieu de `hexgeo.disk` |
| **ForwardSpotter (1143)** | **quirk porte** | `forward_spotter_pick_tiles` : `sort_tiles_by_utility(...)[:n]` + `neighbours_native` au lieu de `board.neighbours` (ids TRIES) sans tri |
| VigilanceEternal (1202) | **residu nomme** (hors perimetre du cas, mais SEPARE du fork) | son utilite est `MovementSuggestion(32)` = `[Tile(7), TileDistance(33)]` (carte de composition de l'`UtilitiesDatabase`, case-128 §2). `TileDistanceUtility` n'est PAS portee -> le collapse « plus proche » est CONSERVE (il approxime le terme de distance manquant, et il est live-valide #220). `_vigilance_move_dest_tile` le porte explicitement, avec le residu documente |
| HammerOfWrath (1153) | **de-forke** (etait deja correct sur le tri) | branche sur le foyer ; son ordre source passe de `board.neighbours` a `board.neighbours_native` (mirror d'`AdjacentTilesSelector`, etabli case-130 SS5 / #117 / FragBomb) |

Le natif n'a **qu'un** `SortTilesByUtilitySelector$$Select` : le port n'en a donc **qu'un**, le foyer
`engine/utilities/tile.py::sort_tiles_by_utility` (+ le raccourci `first_tile_by_utility` = `First(sel, 1)`).
`runner/operations/spawn.py::_sort_tiles_by_utility_for_summon` (le port live-valide de case-130 SS5)
y delegue au lieu de porter son propre corps.

Le selecteur d'unites (`caster` ici, `AllAliveMachinesSelector` cote summon) n'alimente que des feuilles
gatees sur l'unite, non plombees offline -> la distinction est **INERTE** cote port ; c'est la
degradation deja documentee de `utilities/tile.py`.

## 3. Validation LIVE — 3 geometries ou collapse et tri DIVERGENT

Harnais : `scripts/python/probe_165_charge_tile_utility.py` (`--plan` offline, `--live-scan` /
`--live-scan-spawn` / `--live-scan-sky` pour CONSTRUIRE la divergence, `--strict` pour ne garder que
les cas ou l'UTILITE departage — les egalites, elles, ne testent que l'ordre source).

| ability | board | geometrie (drivee par `act move`) | collapse (AVANT) | port (APRES) | **natif LIVE** |
|---|---|---|---|---|---|
| HeroicFusillade 1180 | MC1_67 | Judh @(3,4), necroWarden @(5,5) ; pool = (4,4)e2 / (4,5)e1 / (5,4)e3 | (4,4) e2 | (5,4) e3 | **(5,4)** (`Unit_Foot_Tile_Id_1 = 61`) |
| ForwardSpotter 1143 | C3_01 | MoW `astraOrdnanceBattery`, cible u80 @(2,2) ; ring-1 libre = (1,2)e1 / (1,3)e1 / (2,1)e0 / (2,3)e2 / (3,3)e1 | (1,2) e1 | (2,3) e2 | **(2,3)** (`Unit_Foot_Tile_Id_1 = 33` au spawn) |
| SkyStrike 1025 | MC1_67 | Celestine @(2,7), necroWarden @(4,6) ; ring-1 libre = (3,7)e1 / (3,6)e2 DryBush / (4,7)e1 / (4,5)e1 / (5,6)e1 / (5,7)e1 | (3,7) e1 | (3,6) e2 | **(3,6)** (`Unit_Foot_Tile_Id_1 = 45`) |

Les trois cas sont **discriminants par construction** : l'ancien port aurait donne une AUTRE tuile.
Deux boards distincts (MC1_67, C3_01), trois porteurs de familles differentes (hero / MoW / hero
injecte). Le cas SkyStrike exerce en prime la feuille `TileEffectsUtility` (la tuile gagnante est une
DryBush, +9 LightCover en plus de l'elevation).

**Porteur SkyStrike** : `adeptCelestine` est HORS du seed BC ; injecte par
`python catalog_inject.py --units adeptCelestine --out <abs>.json` puis `rl_duel build --seed-bc`.
Le « `system error` au cast de 1025 » que la docstring du port signalait comme residu **ne se produit
plus** : `catalog_inject` pose AUSSI `BC.Abilities` (cf. `runner.md` §1bis), le cast passe et fait ses
3 coups. Residu leve.

## 4. Ce qui n'est PAS couvert

* **L'ordre source de `SurroundingTiles`** (HeroicFusillade) : le port garde `hexgeo.disk`
  (`_surrounding_free_tiles`). `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select` remplit
  un `OrderedSet` depuis un slot d'iface `battleQuery+0x65`, PAS depuis la liste d'adjacence stockee
  d'`AdjacentTilesSelector` -> l'ordre n'est pas prouve identique. Il n'est observable qu'a **utilite
  EGALE** (carte plate) ; le scenario valide, lui, est departage par l'utilite.
* **`TileDistanceUtility` (33)** et donc le composite `MovementSuggestion(32)` de VigilanceEternal :
  non portes (residu nomme ci-dessus).
* Les feuilles de `Tile(7)` **gatees sur l'unite** : elles rendent 0 (aucun `ctx` n'est passe), comme
  partout ailleurs dans `utilities/tile.py`.
* Le tri ne consomme **aucun** tirage : verifie au decompile (`OrderBy` LINQ), non re-mesure ici.
