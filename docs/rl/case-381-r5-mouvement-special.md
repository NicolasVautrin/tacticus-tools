# case-381-r5 — le pathfinder ne dépend PAS que d'`IsLikeFlying`

Ferme le résidu `#381-r5` (ouvert par `case-381-r4` §4). Rend aussi un **verdict chiffré** sur la
prémisse de `#381-r2`.

## 1. Le dispatch, lu verbatim

`IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit, ignoreSpecialMovement)` —
la surcharge à deux arguments n'est qu'un `(…, false)` :

```
if (!ignoreSpecialMovement) {
    if (HasEffect(unit, 0x40b)) return IsLikeFlying(unit) ? 7  : 6;   // 1035 TeleportStrike_TeleportingIn
    if (HasEffect(unit, 0x474)) return IsLikeFlying(unit) ? 9  : 8;   // 1140 StormboyzStrike_TeleportingIn
    if (HasEffect(unit, 0x4d6)) return IsLikeFlying(unit) ? 11 : 10;  // 1238 FearOfTheUnseen_TeleportingIn
    if (HasEffect(unit, 0x625)) return IsLikeFlying(unit) ? 13 : 12;  // 1573 TitanhammerSquad_TeleportingIn
}
return IsLikeFlying(unit) ? 3 : 0;
```

`PathfinderType` a **quatorze** valeurs (`data/symbols/<build>/frida/enums.tsv`) et
`Pathfinders$$.ctor` remplit les quatorze entrées de son `Dictionary`. Les huit dernières sont des
**DÉCORATEURS** : le ctor passe la MÊME instance `walk` (ou `fly`) aux quatre sous-classes de
`ATeleportPathfinder` — `<X>Pathfinder..ctor(basePathfinder:IPathfinder)`.

## 2. Ce que le décorateur ajoute — et ce n'est pas quatre fois la même chose

`ATeleportPathfinder$$IterateReachableTiles` (`<IterateReachableTiles>d__11$$MoveNext`) :

```
foreach (t in _base.IterateReachableTiles(startTile, depth, unit)) yield return t;
if (unit != null) foreach (t in FindTilesReachableByTeleport(unit)) yield return t;
```

Le second pool ne lit **ni le start ni la portée** : il est BOARD-WIDE. `FindTilesReachableByTeleport`
enchaîne six `RemoveAll` — `!IsEmptyOrSteppable`, `!IsWalkable(checkFog:true)`, `IsTemporary`, un
filtre power-up et un booléen `+0x2e` d'un composant de tuile (tous deux gardés par une propriété
virtuelle **triviale donc dédupliquée**, non nommable), et `!IsValidTeleportTile` (vslot 11).

**Le vslot 11 est ce qui sépare les quatre.** Lu au décompilé :

| famille | `IsValidTeleportTile(unit, tile)` |
|---|---|
| `TeleportStrike` | `GetAdjacentEnemies(tile, unit, false).Count(e => !IsSteppable(e)) == 0` — **on ne se pose pas à côté d'un ennemi** |
| `FearOfTheUnseen` | le même, **plus** `IsTallGrass(tile)` et la bulle `Synapse_Effect` (0x41c) d'un allié (`GetSurroundingTiles(allié, 2, …, includeCenter:true)`) |
| `StormboyzStrike` | aucune méthode nommée → corps trivial. **`true` — CONFRONTÉ live le 2026-08-01** (#366-r1 3/3, greffe du passif : natif == port sur 3 montages ; le prédicat de `TeleportStrike` y rend 59/28/55 contre 61/31/59) |
| `TitanhammerSquad` | le seul RESTRICTIF : la tuile, ou une voisine, porte `TitanhammerSquad_TargetTile` (1571) posé par un allié |

Les deux autres slots : `IsValidContinuePathTile` **délègue** à la base (le gate #131 reste celui de
la base) ; `FindPath` rend `[fromTile, toTile]` (pas de chemin — non porté, aucun consommateur).

## 3. `GetAdjacentEnemies` lit l'adjacence **STOCKÉE**, pas la géométrie — mesuré

`GetAdjacentEnemies` → `IterateAdjacentTiles(from, false, true, true)` = la liste d'adjacence
portée par la tuile. Le `Board` du port est monté en `adjacency="evenq"` (voisinage recalculé et
symétrisé). Sur `C1_74`, où les deux vues divergent sur 32 tuiles (`#381-r3`), le prédicat monté sur
`board.neighbours` rendait **34** tuiles contre **37** au natif ; sur `board.neighbours_native`,
**37/37**. Sur `C2_26`, `MC1_67` et `PVP_desert_04` les deux vues coïncident.

## 4. La confrontation — `aiMovableTiles`, `overrideRange` 2, tout début de bataille

`aiMovableTiles` appelle littéralement `MovementQuery$$GetMovableTilesFor` : égalité EXACTE, unité
par unité. Seed 38104, roster complet, porteurs `tyranDeathleaper` (walk) et `bloodIntercessor`
(fly), tous deux sous `TeleportStrike_TeleportingIn`.

| board | natif | port | port SANS le dispatch |
|---|---|---|---|
| `C2_26` | 35 / 35 | **35 / 35** | 9 · 12 |
| `MC1_67` | 47 / 47 | **47 / 47** | 5 · 6 |
| `C1_74` | 37 / 37 | **37 / 37** | 8 · 6 |

Les unités WALK restent exactes (`C2_26` 5/5, `MC1_67` 5/5 ; `C1_74` 3/5 — les deux écarts sont
`#381-r3`, préexistants et hors périmètre). `test_381r4_imperative_collapses_live` n'écarte plus le
mouvement spécial : **7/7** au lieu de 5/5.

Garde : `tests/engine/entities/pathfinding/test_381r5_special_movement_live.py` (3 tests,
auto-discriminants — ils exigent qu'au moins une unité soit en mouvement spécial ET que le port
muté `_no_special` diverge, donc ils rougissent si le dispatch retombe sur `IsLikeFlying ? Fly :
Walk`). Le test `C1_74` est la garde de la lecture d'adjacence NATIVE.

## 5. Verdict chiffré sur `#381-r2`

`probe_381r5_verdict_r2.py` mesure en deux temps (T0, puis T+6 `endturn` — l'effet expire) :

* le datapoint fondateur de `#381-r2` (`bloodIntercessor`, `MC1_67`, natif 47 / port 27) est un
  artefact de `#381-r5` : le **47 EST** le pool de téléport, désormais reproduit exactement, et
  l'unité redevient FLY après expiration — **natif 6 / port 6**. Idem `C1_74` (37→**6/6**) et
  `PVP_desert_04` (10→**8/8**). Les trois chiffres cités par `#381-r2` (47/27, 46/44, 32/28) sont
  donc tous pris sous l'effet.
* **la prémisse n'est pas morte pour autant** : sur `C2_26` à T+6, `bloodIntercessor` FLY sans
  effet rend natif **13** / port **12** (une tuile MANQUANTE). `#381-r2` reste ouvert, mais son
  ordre de grandeur passe de « 20 tuiles » à **1**.
  **FERMÉ depuis (`case-403-fly-pathfinder.md`)** : la tuile est `(0,2)`, et la cause est le gate
  d'expansion #131 que le port appliquait au vol. Un SECOND maillon a suivi (`#403-r1`, l'arête
  `IsWalkable` au lieu de `!IsWall`). Les deux boards + `C1_74` + `PVP_desert_04` sont désormais
  à **0 écart** sur toute unité mobile.
* les trois autres volantes du roster (`admecManipulus`, `thousSorcerer`, `tyranNeurothrope`) sont
  EXACTES à T0 sur les quatre boards.

## 6. Ce qui reste

* **`IsTemporary`**, le filtre **power-up** et le booléen `+0x2e` (deux gardes virtuelles triviales,
  donc non nommables) : non portés. MESURE — une fois les trois filtres portés appliqués, le pool
  du port est EXACT sur les quatre boards : ces trois-là n'ont retiré aucune tuile sur les
  configurations confrontées.
* ~~`StormboyzStrike` NON CONFRONTÉ~~ → **CONFRONTÉ le 2026-08-01** par #366-r1 3/3 : le passif se
  GREFFE sur une unité du pool (`catalog_inject.graft_passive_ability`), ce qui la met hors plateau
  sous 1140 dès l'init. `probe_366_r1_stormboyz_strike.py`, §6 de
  `case-366-r1-tunneling-horror-pending-summon.md`.
  **`TitanhammerSquad` NON CONFRONTÉ** (seul porteur `astarLysander`, lineup hors pool du seed —
  injectable, `case-92` §6) ; la 3ᵉ branche de `FearOfTheUnseen` (bulle Synapse) est portée mais
  non confrontée (il faut caster l'ability pour entrer dans ce régime).
* **`AnyOrFillMoveableTiles`, branche `tiles.Count == 0` : NON PORTÉE.** Le décompilé appelle
  `GetReachableTiles(start = NULL, type, range, unit)` quand l'unité n'a **aucune tuile** — c'est
  exactement l'état que produisent `RemoveUnitFromItsTiles` (1011/1023/1090/1141). Le port exige un
  `from_tile` (`services/movement_query.get_movable_tiles_for`) et ses appelants sautent l'unité.
  MESURÉ le 2026-08-01 : le natif rend **61** tuiles pour l'unité hors plateau (`MC1_67`), le port
  n'en rendrait aucune par cette porte. Dégradation RESTRICTIVE, sans consommateur aujourd'hui (seul
  un porteur de `StormboyzStrike` bouge depuis cet état). RÉSIDU NOMMÉ.
* **Le nœud DSL** `MovableTilesInRange` passe `teleport_target_tiles=None` : `ctx.tile_has_effect`
  n'expose pas la SOURCE de l'effet, donc « posé par un allié » n'y est pas décidable → pool de
  téléport Titanhammer vide (dégradation RESTRICTIVE, nommée).
* `ATeleportPathfinder$$FindPath` (téléport sans chemin) : non porté, aucun consommateur.
