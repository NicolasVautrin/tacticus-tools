# #433-r4-r1-r4-r2-r1-r1-r1 — `RammingSpeed` décidait l'adjacence par une couronne hexagonale

Le mirror de `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetDynamicInvalidTargetReason`
écrivait `hexgeo.distance(cp, tp) == 1`. Le natif, lui, appelle un **service**, et ce service porte
**trois** étages qu'une distance hexagonale ne voit pas. Les trois sont désormais confrontés live.

## 1. Ce que fait le natif (relu le 2026-08-05 sur `rnca9r7q6c`)

```c
casterTile     = casterTiles[0]
movedOrOffTile = UnitExtensions.DidMove(caster) || EntityExtensions.GetMainTile(caster) != casterTile
isAdjacent     = battleQuery.<slot 0x61>(casterTiles, target)
if (movedOrOffTile && !isAdjacent) return 0x10;          // CasterHasNotMoved
if (isAdjacent)                    return 0;
if (battleQuery.<slot 0x4f>(target,1,1,1).Count < 1) return 0x20;
tile = GetTileToMoveTo().SelectTile(...);
if (tile != null && battleQuery.<slot 0x14>(caster, tile, 0).Count != 0) return 0;
return 0x8000000;
```

Le slot `0x61` est `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`, surcharge
**`(IList tiles, IEntity unit)`** — et cette identification ne repose **pas** sur l'index seul :

* les lambdas du décorateur `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery`
  (`DisplayClass117_0/118_0/119_0`) ré-appellent l'inner par `0x60`/`0x61`/`0x62` ;
* `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, branche `OnlyAdjacent`, passe
  `(casterTiles, target)` au slot `0x61` ;
* `RammingSpeedAbility$$GetDynamicInvalidTargetReason` passe **les mêmes types** au même `0x61`.

Deux call-sites indépendants mélangent donc une LISTE et une ENTITÉ : c'est le **type des
arguments** qui désigne la surcharge, pas le rang.

En dessous :

```
AreEntitiesAdjacent(tiles, unit) = MovementUtil.AreTilesAdjacent(tiles, EntityExtensions.GetTiles(unit))

MovementUtil.AreTilesAdjacent(IList a, IList b)          // OU sur les paires
    foreach t1 in a: foreach t2 in b: if (AreTilesAdjacent(t1,t2)) return true;
    return false;                                        // enumeration epuisee -> FAUX

MovementUtil.AreTilesAdjacent(t1, t2)                    // la primitive SCALAIRE
    return (|dElev| < 2) & (t1 == t2 || ConnectivityComponent(t1).IsNeighbour(t2));
```

**Trois écarts, et ils ne vont pas tous dans le même sens** :

| axe | ce que le natif porte | sens de l'erreur du port d'avant |
|---|---|---|
| **A — liste STOCKÉE** | `IsNeighbour` lit `ConnectivityComponent+0x10`, pas la couronne hex | PERMISSIF |
| **B — ÉLÉVATION** | `\|dElev\| < 2`, terme **séparé** de la primitive | PERMISSIF |
| **C — EMPREINTES** | deux `IList` : adjacent par **n'importe lequel** des pieds | **RESTRICTIF** |

C'est ce troisième sens qui interdit qu'un correctif « toujours vrai » ou « toujours faux » passe.

## 2. Le correctif

`get_dynamic_invalid_target_reason` appelle désormais le foyer partagé
`engine.services.battle_query.are_entities_adjacent(entity_tiles(caster), entity_tiles(target), board)`,
qui délègue à `engine.runner.abilities.targeting.are_entities_adjacent` dès qu'un board est là : le
verdict de ciblage de `RammingSpeed` et celui de la cascade générique sortent **littéralement de la
même fonction**. `board` absent (scène de test) → dégradation NOMMÉE (adjacence hex + court-circuit
d'identité, sans porte d'élévation), jamais une géométrie nue de plus.

## 3. Le levier de confrontation — lire le prédicat natif SANS déplacer une unité

`castFromTiles` interroge `GetInvalidTargetReason(caster, <tuile>, target, ability)` depuis une
tuile **explicite**. Or depuis une tuile hypothétique `T != mainTile`, `movedOrOffTile` est VRAI
**par construction** (`GetMainTile(caster) != casterTiles[0]`), donc la fonction se réduit à

```
valide depuis T  <=>  AreEntitiesAdjacent([T], GetTiles(target))
```

`castFromTiles(...).moveTiles` est donc, à lui seul, la **liste des tuiles du set de move que le
natif tient pour adjacentes à la cible**. Côté port, on met le moteur dans le même régime : position
réécrite à `T` + flag « a bougé » posé — cette seconde écriture n'est pas un artifice, c'est la
2ᵉ clause de `movedOrOffTile`, que le port ne modélise nulle part (résidu assumé, docstring
d'`orks.py`). Sans elle on comparerait la branche de CHARGE du port à la branche d'ADJACENCE du
natif.

Le montage est **dérivé du board** (`choisir_poste`) : on poste la cible sur la tuile dont les
voisins hex tombant dans le set de move se ventilent en deux groupes **non vides**, tenus / refusés
par la liste stockée ; chaque refus est ventilé en `arete` (absent du `ConnectivityComponent`) ou
`elevation`. L'axe `arete` passe en premier — c'est le seul où l'élévation n'explique rien.

## 4. Mesures

### 4.1 Contre-épreuve OFFLINE (`test_433r4r1r4r2r1r1r1_ramming_speed_adjacence_offline.py`)

10 tests, board synthétique, aucun runner. Fix retiré (retour à `hexgeo.distance(cp, tp) == 1`) :
**4 rouges** — `axeA`, `axeB`, `axeC`, et le court-circuit d'identité `#433-r1`. Le cran
`test_axeB_un_seul_cran_ne_coupe_PAS` interdit qu'un correctif refusant *toute* différence
d'élévation passe, et `test_le_regime_NOMINAL_est_inchange` interdit de faire passer les trois axes
en cassant le cas courant.

### 4.2 Confrontation LIVE (`probe_433r4r1r4r2r1r1r1_ramming_speed_adjacence_live.py`)

Porteur GREFFÉ (`RammingSpeed` a zéro porteur au gameconfig, #353) sur `orksKillaKan`.

| axe | board | montage | natif | port APRÈS | port AVANT | désaccord APRÈS |
|---|---|---|---|---|---|---|
| **B** élévation | `C1_74` | cible postée en `(0,1)`, elev 4 | 2 tuiles | **2** | 4 | **0** |
| **A** arête | `C3_14` | cible postée en `(1,2)` | 1 tuile | **1** | 3 | **0** |
| **C** empreintes | `MC1_67` | Galatian 3 pieds `[(2,0),(2,1),(3,1)]` | 3 tuiles | **3** | 1 | **0** |

Les deux tuiles que l'axe C récupère sont `(1,2)` et `(2,2)`, toutes deux à `d(pied0) = 2` et
`d(empreinte) = 1` : le bras d'avant y **inventait** un refus. Le probe **sort en écart (rc 2) si le
bras d'avant ne diverge sur aucune tuile** — un accord sur un montage dégénéré ne prouve rien.

Le porteur de l'axe C est le **summon**, jamais la MoW : une MoW a un `MachineComponent`, pas de
pieds. `DutyEternal` (1158) fait naître `ultraSmnDreadnought` (Galatian), **seule** unité à 3 pieds
confrontable de ce build — l'autre producteur de `IdunBattleLogic.Entities.DSLFactory$$ThreeTileUnitSpawnShape`,
`AetherStride` (1208, `thousDaemonPrince`), est hors seed BC **et** non porté.

## 5. La liste LUE, élargie — et une suspension qui se re-mesure

`probe_433r4r1r4r2_neigh_channel_wired.py` n'entrait, aux étapes 2 et 4, que sur `NATIFS_LISTE_STOCKEE`,
une liste **littérale**. Trois natifs LUS y entrent : `AreEntitiesAdjacent` (les 3 surcharges),
`AreUnitsInMelee` (corps entier = `return AreEntitiesAdjacent(...)`), `GetFreeAdjacentTiles`
(`GetAdjacentTiles(from,1,1)` + `FilterInPlace`). **0 rouge** après élargissement.

**La DÉRIVATION de cette liste est RÉFUTÉE par la mesure**, pas abandonnée : ni le binaire (aucun
call-graph versionné), ni le NOM, ni la fermeture sur les docstrings ne séparent une méthode de
requête d'adjacence d'un enum / d'un `UtilityType` / d'une variable locale du décompilé —
**28 tokens rendus, 3 vrais, 25 faux**. Un cliquet à 89 % de bruit se fait désactiver, et
l'allowlist qui le sauverait *serait cette liste-ci*.

Ce qui **est** dérivé, c'est l'**étape 5**, à critère INVERSE : un natif LU mais dont l'armement
rougirait sur un vice ouvert hors périmètre entre au registre **SUSPENDU** avec son numéro de
résidu ; l'étape l'arme *pour de faux* à chaque passe et **rougit si plus personne n'en souffre** —
la suspension est alors PÉRIMÉE, et c'est elle le vice.

## 6. Résidus NOMMÉS

* **`#433-r4-r1-r4-r2-r1-r1-r1-r1`** — `AdjacentTiles` / `AdjacentUnits` sont au registre
  **SUSPENDU**. Les armer ferait rougir `playbook/noncomparable/aberrant_hypermorph.py` et
  `master_of_the_tutelaries.py`, qui reconstruisent « spawn adjacent à la position T » par
  `hexgeo.distance(T, ST) != 1` alors que le canal est deux lignes plus bas. Trancher demande de
  lire le sélecteur DSL de chaque ability : `AberrantHypermorphPlaybook$$EvaluateNonComparable` ne
  filtre pas par distance, la contrainte vient du sélecteur. L'étape 5 re-mesure à chaque passe que
  cette suspension est encore justifiée.
* **`#381-r1`** (déjà ouvert) — le test de CHEMIN (slot `0x14`) reste SUBSUMÉ côté port :
  `ramming_speed_tile_to_move_to` n'émet que des tuiles de `MovableTilesInRange`, qui est le
  `visited` d'un BFS **qui traverse**, là où le natif fait un pathfinding. Écart d'ACCEPTATION sur
  un ring saturé, jamais de refus inventé.
* **`#433-r3-r3`** (déjà ouvert) — soldé **pour deux groupes seulement** : les slots
  `AreEntitiesAdjacent` et `GetAdjacentEnemies` de `targeting.py` étaient tous deux décalés d'un
  cran ; `docs/rl/case-243-targeting-adjacency.md` porte encore la table datée
  (`DisplayClass116_0`, qui n'existe pas sur `rnca9r7q6c`). Le balayage général des slots cités en
  commentaire reste à faire.

## 7. Ce qui n'est PAS couvert

* La 2ᵉ clause de `movedOrOffTile` (`GetMainTile(caster) != casterTiles[0]`) n'est modélisée nulle
  part côté port : `get_dynamic_invalid_target_reason` ne prend pas de tuile hypothétique en
  paramètre et lit toujours la position réelle. C'est sans effet sur le chemin `ExecuteInternal`
  (qui passe les tuiles réelles), et c'est le probe live qui pose le flag pour aligner les régimes.
* `AetherStride` (1208) / `thousSmnDaemonPrince` : 2ᵉ empreinte 3-pieds du jeu, **jamais confrontée**
  (ability non portée, MoW hors seed BC).
* Les tailles d'empreinte **3** et **7** existent dans l'enum `TargetingRule` ; seul le **3** a un
  producteur dans ce build.

## 8. Reproduction

    python -m pytest tests/engine/runner/test_433r4r1r4r2r1r1r1_ramming_speed_adjacence_offline.py
    python -m pytest tests/engine/test_433r4r1r4r2r1r1_derivation_morte_offline.py
    python probe_433r4r1r4r2_neigh_channel_wired.py
    python probe_433r4r1r4r2r1r1r1_ramming_speed_adjacence_live.py --build --board C1_74 --no-mow
    python probe_433r4r1r4r2r1r1r1_ramming_speed_adjacence_live.py --build --board C3_14 --no-mow
    python probe_433r4r1r4r2r1r1r1_ramming_speed_adjacence_live.py --build --axe-c --board MC1_67
    python probe_433r4r1r4r2r1r1r1_ramming_speed_adjacence_live.py --dispose
