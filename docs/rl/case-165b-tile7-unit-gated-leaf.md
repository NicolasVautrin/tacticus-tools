# case-165b — le terme manquant du composite `Tile(7)` : la feuille GATEE SUR L'UNITE

Residu #4 de `case-165-collapse-tuile-plus-proche.md` : sur `MC1_67`, cible `necroWarden` au BORD
en (6,7), `SkyStrikeAbility$$ExecuteBehaviour` faisait atterrir Celestine en **(5,7) e1** la ou le
port rendait **(6,6) e2**. Le terme manquant est **`GEMINAESUPERIA_FreeAdjacentHex`**, emis par la
feuille `TriggeredAbilities(2)` du composite via le playbook du passif de Celestine.

## 1. Le terme, et pourquoi il etait invisible

`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` construit, PAR TUILE candidate :

```
UtilityMovementCase(dc.units, tile, null, null, dc.owner)
```

(`<Select>b__1` -> `IdunBattle.AI.Utilities.UtilityMovementCase$$.ctor` surcharge « tile », qui pose
`+0x10 = units`, `+0x18 = UnitPosition(tile)`, `+0x30 = owner`).

`dc.units` = le selecteur d'unites du call-site (`caster@0x160` pour les charges). Il est donc
DISPONIBLE pour toutes les feuilles gatees sur l'unite — le port, lui, passait un `ctx` VIDE, si
bien que les 20+ feuilles gatees rendaient 0. C'etait le « non couvert » de case-165.

Pour `adeptCelestine` (traits `Hero`/`ActOfFaith`/`Flying`, passif **`GeminaeSuperia`**), la feuille
`TriggeredAbilities(2)` dispatche (`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook`) vers
`IdunBattle.AI.Playbook.Loki.GeminaeSuperiaPlaybook` (`..$$.ctor` passe le litteral `0x418` = 1048),
dont `..u003CCalculateMovementUtilityInStepsInternalu003Ed__3$$MoveNext` remis en C# donne :

```csharp
tile = UtilityAttackCase.get_CasterTile(case);                     // la TUILE CANDIDATE
free = CanAddUnit(AdjacentTiles(Get(tile)));
val  = config["GEMINAESUPERIA_FreeAdjacentHex"] * free.Count(entities);          // 10 x N
if (Count(AdjacentUnits(Get(tile), 1, 3) & Get(case.unit)) == 1)                 // OwnerInAdjacentTile
    val += config["GEMINAESUPERIA_FreeAdjacentHex"];                             // +10
gem  = UnitsWithId(Friends(Get(case.unit), AdjacentUnits(Get(tile), 1, 3), 3),
                   AbilityConfiguration.GetStringConstant(config, 0), 3);
val += config["GEMINAESUPERIA_AdjacentAliveSummon"] * gem.Count(entities);       // 30 par Geminae
yield Fix64.FromInt(val);
```

Le 2e terme a sa methode NOMMEE, `IdunBattle.AI.Playbook.Loki.GeminaeSuperiaPlaybook$$OwnerInAdjacentTile`
(meme corps, inline dans l'iterateur) : « l'unite qui evalue est-elle DEBOUT sur une tuile ring-1 de
la candidate ». C'est la **compensation** du 1er : la tuile d'origine est comptee OCCUPEE par
`CanAddUnit` (l'unite y est encore pendant le sweep) alors qu'elle sera libre une fois partie.

Poids BC (`Utilities.Default.TriggeredAbilities`) : `GEMINAESUPERIA_FreeAdjacentHex` = **10**,
`GEMINAESUPERIA_AdjacentAliveSummon` = **30**. `GetStringConstant(config, 0)` =
`gameconfig.abilities.GeminaeSuperia.constants.unitId` = `adeptSmnGeminaeSuperia`.

**Pourquoi le residu ne se voyait qu'au BORD** : en plein plateau toute tuile a 6 voisins libres, le
terme vaut 60 PARTOUT et ne departage rien — c'est exactement pourquoi les 4 geometries de case-165
etaient justes SANS lui. Il ne mord que la ou le voisinage est TRONQUE : bord de plateau, coin, ou
voisins occupes. Il y vaut jusqu'a 50 points d'ecart, largement de quoi renverser `ElevationUtility`
(10/elevation, +10 au max du board, -5 au min).

## 2. Ce que la mesure ETABLIT (et ce qu'elle ECARTE)

Harnais : `scripts/python/probe_165b_sky_strike_border.py` (build + drive + decomposition PAR TERME
+ cast live ; `--block <vis>:<col>,<row>` gare une unite sur une tuile du pool ; `--scan-owner`
cherche une geometrie ou le terme `OwnerInAdjacentTile` renverse l'argmax).

| # | geometrie (MC1_67) | pool (ordre selecteur) et score PORT apres fix | natif LIVE |
|---|---|---|---|
| 1 | Celestine @(1,0) (d=11), Warden @**(6,7)** | (6,8) 5+10=**15** / (6,6) 20+30=**50** / (5,7) 5+50=**55** / (5,8) 5+40=**45** | **(5,7)** |
| 2 | Celestine @(4,5) (d=2), Warden @(6,7) | idem (le caster n'est ring-1 d'aucune candidate) | **(5,7)** |
| 3 | idem + `astraBullgryn` gare sur **(5,7)** | (6,8) **15** / (6,6) 20+20=**40** / (5,8) 5+30=**35** | **(6,6)** |
| 4 | Celestine @(1,8), Warden @(0,6) | (0,7) 5+20=**25** / (1,7) 5+50=**55** / (1,6) 20-25+50=**45** (Swamp) / (0,5) 20+30=**50** | **(1,7)** |
| 5 | Celestine @(1,6), Warden @(0,4) | (0,5) **50** / (1,5) **80** / (1,4) **80** / (0,3) **80** | **(1,5)** |

* **La distance du caster n'est PAS la variable** (#2 : caster a d=2, meme resultat qu'a d=11).
* **Le BORD n'est pas la variable non plus** : la 4e geometrie de case-165 §3 a une cible au bord
  (`(0,1)`, 4 voisins) et le natif y suit l'elevation. Ce qui compte est le COMPTE de voisins
  LIBRES, pas le fait d'etre au bord.
* **Le Loop1 de `TileEffectsUtility` est ECARTE** : `tileMeta` rend `effects: []` sur les 4
  candidates de la geometrie #1 — le `RelentlessMarch_DangerZone` du Warden ne marque aucune tuile.
* **Le terme suit le KIT DU CASTER, pas la tuile** : sur le MEME board, la MEME cible (6,7) et le
  MEME couple de candidates {(5,7) e1, (6,6) e2}, `HammerOfWrathAbility$$ExecuteBehaviour` joue par
  `bloodIntercessor` (qui n'a PAS `GeminaeSuperia`) fait charger le natif sur **(6,6)** — mesure
  #226 deja consignee dans `_how_move_dest_tile`. C'est le TEMOIN qui attribue l'ecart au caster.
* Les geometries #4 et #5 sont les seules qui exercent `OwnerInAdjacentTile` : sans son +10, le port
  rendrait (0,5) (#4, marge STRICTE 55 vs 50) et (1,4) (#5) ; le natif rend (1,7) et (1,5).
* La 4e geometrie exerce en prime le `Thorns_DefenseReduction` -25 de la `Swamp` (canal Loop1) —
  `tileMeta` confirme que l'entite-tuile porte bien `BlockEnteringUnits` + `Thorns_DefenseReduction`.

## 3. Le port

* `engine/playbook/geminae_superia.py` — `GeminaeSuperiaPlaybook`, mirror 1:1 du corps ci-dessus.
  Il reutilise `battle_query.adjacent_addable_count` (= `|{n in GetAdjacentTiles : CanAddUnit(n)}|`,
  deja live-valide pour `HammerOfWrathPlaybook` #116) et `battle_query.is_adjacent` pour
  `AdjacentUnits(..., 1, 3)`. Enregistre dans `TRIGGERED_MOVE_PLAYBOOKS` sous
  `TriggeredAbilityType.GeminaeSuperia` (1048).
* `engine/utilities/tile.py` :
  * `sort_tiles_by_utility(state, tiles, wt=None, **unit_id=None**)` et
    `first_tile_by_utility(..., unit_id=None)` — `unit_id` EST `dc.units` ;
  * **`runner_tile_leaf_ctx(state, unit_id)`** — jumeau RUNNER de `tile_leaf_ctx` (qui, lui, part
    d'un `AiDecisionContext`). Memes cles, memes formes ;
  * le 1er argument passe a `tile_composite` devient la POSITION `(col,row)` et non l'id de tuile —
    c'est le contrat des deux autres constructeurs de composite et celui qu'attendent les playbooks
    (inerte tant que le `ctx` etait vide, decisif des qu'il ne l'est plus) ;
  * `tile_leaf_ctx` gagne `walkable_by_pos` (carte du gate `CanAddUnit`) et `vis` sur les records
    d'unites voisines (argument du noeud `UnitsWithId`).
* Call-sites ou `dc.units` EST le caster -> `unit_id=caster_id` :
  `sisterhood._sky_strike_dest_tile` (1025), `bloodangels._how_move_dest_tile` (1153),
  `genestealer._hf_move_dest_tile` (1180).

## 4. Ce qui n'est PAS couvert

* ~~**Le call-site SUMMON** (`SortTilesByUtilityForSummon`) reste sans `unit_id` : son `dc.units` est
  `AllAliveMachinesSelector`, un ENSEMBLE d'unites~~ — **REPRIS ET CORRIGE par
  `case-205-summon-sort-tiles-unit-null.md`.** Ce constat etait FAUX : `dc.unit` est un `IEntity`
  SINGULIER (ctor `SortTilesByUtilitySelector..ctor(tiles, **unit**, utilityDefinition, parent, …)`)
  et il vaut **`null`** sur ce call-site — le `AllAliveMachinesSelector` y est construit avec son
  provider (`+0x18`) NUL. Le natif modelise ce cas avec `UtilityMovementCase$$get_IsSpawning`
  (= `unit == null && parent != null`) et `$$get_UnitOrParent` (= `unit ?? parent`), et chaque
  feuille applique SA propre degradation. Le foyer prend desormais un `parent_id`.
* **Le 3e terme (`GEMINAESUPERIA_AdjacentAliveSummon`, +30 par Geminae adjacente) n'est pas
  confronte live** : aucune des 5 geometries n'avait de Geminae invoquee sur le plateau. Le corps
  est porte (mirror du decompile), la valeur ne l'est pas.
* **Les autres feuilles gatees sur l'unite** que le `ctx` reveille desormais cote runner
  (`CapturePoint(24)`, `PowerUp(26)`, `DespoiledGround(28)`, `HeroLikeDoorOpening(30)`, …) ne sont
  pas confrontees ici : leur metadata PAR TUILE (`occupant_is_powerup`, `door`, …) n'est toujours
  remontee par aucun RPC, elles rendent donc 0 — meme degradation qu'avant.
* `scene` / `hpmax_by_id` / `enemies` ne sont PAS produits par `runner_tile_leaf_ctx` ->
  `FuryOfTheAncientsPlaybook` (1247) rend 0 sur le chemin du tri. Residu nomme.
* `is_territory_by_pos` / `tile_effect_type_ids_by_pos` : le `meta` de ce foyer ne les porte pas
  (inchange par ce cas).

## 5. Cliquet

`tests/engine/runner/test_charge_tile_utility_live.py::test_sky_strike_landing_tile_follows_unit_gated_leaf`
— cherche LIVE une geometrie ou `first_tile_by_utility(..., unit_id=None)` (le port d'AVANT) et
`_sky_strike_dest_tile` (le port d'APRES) divergent, echoue si elle n'existe pas, puis confronte au
natif. Les 3 tests de case-165 restent dans le meme fichier et restent VERTS.
