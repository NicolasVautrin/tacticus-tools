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

## 3. Validation LIVE — 4 geometries ou collapse et tri DIVERGENT

Harnais : `scripts/python/probe_165_charge_tile_utility.py` (`--plan` offline, `--live-scan` /
`--live-scan-spawn` / `--live-scan-sky` pour CONSTRUIRE la divergence, `--strict` pour ne garder que
les cas ou l'UTILITE departage — les egalites, elles, ne testent que l'ordre source).
Cliquet : `tests/engine/runner/test_charge_tile_utility_live.py` (3 tests, geometrie discriminante
RE-CHERCHEE a chaque run puis drivee par `applyAction`, confront a la tuile natif).

| ability | board | geometrie (drivee par `act move`) | collapse (AVANT) | port (APRES) | **natif LIVE** |
|---|---|---|---|---|---|
| HeroicFusillade 1180 | MC1_67 | Judh @(3,4), necroWarden @(5,5) ; pool = (4,4)e2 / (4,5)e1 / (5,4)e3 | (4,4) e2 | (5,4) e3 | **(5,4)** (`Unit_Foot_Tile_Id_1 = 61`) |
| ForwardSpotter 1143 | C3_01 | MoW `astraOrdnanceBattery`, cible u80 @(2,2) ; ring-1 libre = (1,2)e1 / (1,3)e1 / (2,1)e0 / (2,3)e2 / (3,3)e1 | (1,2) e1 | (2,3) e2 | **(2,3)** (`Unit_Foot_Tile_Id_1 = 33` au spawn) |
| SkyStrike 1025 (COVER tranche) | MC1_67 | Celestine @(2,7), necroWarden @(4,6) ; ring-1 = (3,7)e1 / **(3,6)e2 DryBush** / (4,7)e1 / (4,5)e1 / (5,6)e1 / (5,7)e1 | (3,7) e1 | (3,6) e2 | **(3,6)** (tuile 45) |
| SkyStrike 1025 (ELEVATION seule) | MC1_67 | Celestine @(2,2), necroWarden @(0,1) ; ring-1 TOUT Grass = (0,0)e3 / (0,2)e3 / (1,1)e3 / **(1,2)e2** (la plus PROCHE) | (1,2) e2 | (1,1) e3 | **(1,1)** e3 |

Les quatre cas sont **discriminants par construction** : l'ancien port aurait donne une AUTRE tuile.
Deux boards distincts (MC1_67, C3_01), trois porteurs de familles differentes (hero / MoW / hero
injecte). Le 3e cas exerce la feuille `TileEffectsUtility` (cover DryBush +9) ; le 4e isole
`ElevationUtility` (terrain uniforme, seule l'elevation departage) et refute le collapse SANS
l'aide du cover.

**Porteur SkyStrike** : `adeptCelestine` est HORS du seed BC ; injecte par
`python catalog_inject.py --units adeptCelestine --out <abs>.json` puis `rl_duel build --seed-bc`.
Le « `system error` au cast de 1025 » que la docstring du port signalait comme residu **ne se produit
plus** : `catalog_inject` pose AUSSI `BC.Abilities` (cf. `runner.md` §1bis), le cast passe et fait ses
3 coups. Residu leve.

## 4. RESIDU MESURE — SkyStrike sur une cible au BORD, caster tres eloigne

Une 5e geometrie CONTREDIT le composite porte, et elle est documentee telle quelle (mesuree, pas
supposee) :

| geometrie | ring-1 libre (tout Grass) | port `Tile(7)` | **natif LIVE** |
|---|---|---|---|
| Celestine @(1,0) (dist **11**), necroWarden @**(6,7)** — cible au BORD, 4 voisins seulement | (5,7)e1 / **(6,6)e2** / (5,8)e1 / (6,8)e1 | (6,6) e2 | **(5,7) e1** (= la plus PROCHE) |

Le chemin natif est UNE seule etape (`Unit_Foot_Tile_Id_1 = (5,7)`, `Is_Last_Tile=1`) : ce n'est donc
PAS un arret en cours de route vers (6,6), c'est bien la destination CHOISIE. Ce que ce cas exclut :
ce n'est pas « SkyStrike ignore l'elevation » (le 4e cas du §3, cover-neutre et caster PROCHE, la
suit), ni « le collapse etait juste » (les cas 3 et 4 le refutent).

Ce qui reste ouvert — deux pistes, aucune tranchee :
* une feuille de `Tile(7)` **gatee sur l'unite** (`dc.units` = le caster est passe au
  `UtilityMovementCase`), muette offline faute de `ctx` ;
* le **Loop1 de `TileEffectsUtility`** (effets DYNAMIQUES de l'entite-tuile) : le necroWarden porte
  `RelentlessMarch_DangerZone` ; si cet effet marque des tuiles et que `state.effects.by_unit[tileId]`
  n'est pas hydrate pour elles, le port est aveugle a une penalite que le natif applique.

**Candidat fable-solver** (mesure reproductible ci-dessus + les deux pistes). Ce n'est PAS une raison
de revenir au collapse : celui-ci est refute par les cas 3 et 4, et le mirror structurel reste la
bonne base. Le cliquet `test_sky_strike_landing_tile_follows_tile_utility` EXIGE explicitement une
cible a 6 voisins et un caster a distance <= 3 — il garde le patron etabli, il n'arbitre pas ce residu.

## 5. Ce qui n'est PAS couvert

* **L'ordre source de `SurroundingTiles`** (HeroicFusillade) : le port garde `hexgeo.disk`
  (`_surrounding_free_tiles`). `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select` remplit
  un `OrderedSet` depuis un slot d'iface `battleQuery+0x65`, PAS depuis la liste d'adjacence stockee
  d'`AdjacentTilesSelector` -> l'ordre n'est pas prouve identique. Il n'est observable qu'a **utilite
  EGALE** (carte plate) ; le scenario valide, lui, est departage par l'utilite.
* **`TileDistanceUtility` (33)** et donc le composite `MovementSuggestion(32)` de VigilanceEternal :
  non portes (residu nomme au §2).
* Le cas SkyStrike « cible au BORD / caster lointain » du §4 : le port y rend une AUTRE tuile que le
  natif. Aucun autre call-site n'a ete confronte dans cette configuration.
* Les feuilles de `Tile(7)` **gatees sur l'unite** : elles rendent 0 (aucun `ctx` n'est passe), comme
  partout ailleurs dans `utilities/tile.py`.
* Le tri ne consomme **aucun** tirage : verifie au decompile (`OrderBy` LINQ), non re-mesure ici.
