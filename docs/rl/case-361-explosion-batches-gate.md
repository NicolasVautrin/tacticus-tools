# case-361 — `RammingSpeed` batchs 3/4 : le natif les émet, JUSTES. La cause était le MONTAGE

Clôt `#353-r1` volet (b), `#361-r2`, `#361-r3`. Suites : `#372`, `#365`, `#386`, `#370`, `#374`, `#381`.

## 1. Le verdict

`IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` émet ses quatre batchs et
les émet **exacts**. Mesuré le 2026-07-31 sur le montage même qui portait le verrou
(`probe_361_ramming_speed_explosion_batches.py`, board `MC1_67`, greffe `orksKillaKan ← 1059`) :
**5 events == 5 attendus**, cibles et dégâts exacts, cast réel MATCH sur `(5,7)`.

```
list = <batch 1 : la CIBLE>            // 1 event
self = <batch 2 : le CASTER (recul)>   // 1 event
list.AddRange(self)
if (!self.Any(p => p.Prediction.WillBeKill)) return list;   // <>c$$<MakeDamagePredictions>b__2_0
tile = RammingSpeedAbility$$GetTileToMoveTo(ability)
list.AddRange(GenerateAttackPredictions(..., Friends(<Caster>, AdjacentUnits(tile, 1, 3), 3), ...))
list.AddRange(GenerateAttackPredictions(..., Enemies(<Caster>, AdjacentUnits(tile, 1, 3), 3), ...))
```

Les « 2 events pour 5 attendus » observés pendant toute l'enquête venaient du **montage**, sous
**deux formes distinctes**, chacune mesurée (§4). Aucune n'est une propriété de l'arbre.

⇒ **Le refus de porter les batchs 3/4 de `1059` n'a plus aucun fondement.** `1059` reste hors
`ABILITY_CLASSES` (seule `GetTileToMoveTo` est portée, `#353-r1` volet a) : c'est une tâche ouverte.

## 2. Le maillon, tranché — et il est en AMONT des trois qu'on cherchait

Le pool de `GetTileToMoveTo` est
`MovableTilesInRange(Caster@0x48, CasterTile@0x50, Direct(range), 0, 0)
 op_BitwiseAnd CanAddUnit(AdjacentTiles(Target@0x60))`, trié puis `First(…, 1)`.

Le capteur (§5) lit le pool **avant** ces trois maillons. Dans le régime déficitaire il rend `0`,
et sa **classe de retour** (`OrderedSet`1`, pas `List`1`) écarte les deux early-returns du
sélecteur : la requête a répondu, et elle a répondu vide. La chaîne, lue au décompilé :

`MovableTilesInRangeSelector$$Select` → `BattleQuery$$GetMovableTilesFor` →
`MovementQuery$$GetMovableTilesFor` (qui **alloue** l'`OrderedSet`) →
`MovementQuery$$FindAnyOrAllMoveableTiles`, dont la première instruction utile est une garde qui
rend **sans rien remplir**, sans erreur ni exception :

```
if ( (UnitFlagsComponent$$Has(unitFlags, 1) && ignoreUnitFlags == 0)
   || !UnitExtensions$$CanMove(unit) )   return;      // l'OrderedSet repart VIDE
```

`MovableTilesInRangeSelector` passe `_ignoreFlags = 0` — champ **mesuré** par le capteur, pas
supposé — donc la première branche est armée. Les deux branches se séparent par leur durée de vie :
le flag dépend du **tour** ; `UnitExtensions$$CanMove` teste `BaseUnitComponent$$HasTrait(0x418)` et
`MovementComponent$$IsAllowedToMove` (= le dictionnaire de blocages `+0x50` a `Count == 0`), deux
états **persistants**.

## 3. Comment on l'a séparé sans aucun nouveau hook

Le RPC `aiMovableTiles` appelle la **même** `MovementQuery$$GetMovableTilesFor(unit,
ignoreUnitFlags: false, options)` ; avec `side="all"` il couvre les unités que le joueur courant ne
contrôle pas, et avec `overrideRange` il pose le range du sélecteur. C'est le capteur, déjà chargé.

`probe_381_movable_tiles_query_gate.py` balaie donc les tours sur une géométrie **figée** (aucune
unité déplacée entre les étapes, tuile d'arrivée et attendu constants, gate ouverte partout) :

| géométrie | tuile | attendu | avec la main | sans la main | events |
|---|---|---|---|---|---|
| `#386` §1 — caster (1,4) | (5,7), d=5 | 5 | **51** tuiles | **0** | 5 / 2 |
| montage — caster (6,7) | (3,5), d=4 | 4 | **28** tuiles | **0** | 4 / 2 |

Oscillation **4/4** puis **6/6**, et la requête nue s'accorde au pool DSL sur **toutes** les étapes
(51/0/51/0 et 28/0/28/0/28/0) — donc le vide est bien celui de `GetMovableTilesFor`, pas un effet du
contexte DSL. ⇒ **branche FLAG**.

## 4. Les deux artefacts de montage, nommés

**(a) Le caster n'a pas la main.** `drive_to` termine sur un `endturn` : c'est la **parité** des
tours consommés qui décide du camp qui joue. Deux montages posant la MÊME géométrie par des chemins
de drive différents ne la laissent pas au même camp — c'était toute la différence entre
`probe_361` (2 events) et `montage_361` (5 events) sur la géométrie de `#386` §1. Parade :
`probe_353r1…$$ensure_turn`, appelée après le drive ; les probes **refusent** de conclure sans elle.

Garde adversariale jouée — `probe_361_ramming_speed_explosion_batches.py --no-ensure-turn`, même
build, même seed, même géométrie : `caster_has_turn=False`, **2 events pour 5**, `BRAS NON
DISCRIMINANT`. Avec : **5 == 5**. La seule variable est le tour.

**(b) Aucune tuile de charge n'est ATTEIGNABLE.** `MovableTilesInRange` est un **pathfinding**
(`MovementQuery$$AnyOrFillMoveableTiles`), pas un disque hexagonal : sur un ring saturé, les tuiles
candidates sont à portée hexagonale mais aucun chemin n'y mène. `op_BitwiseAnd
CanAddUnit(AdjacentTiles(Target))` rend alors vide, `First` ne désigne rien, et les batchs manquent
**légitimement**. Mesuré (`probe_361_ramming_speed_forced_tile.py`, caster (1,0), cible (3,4)) :
pool de mouvement **23** tuiles, candidates `(2,3) (2,4) (4,3) (4,4)` à distance 4–6,
**intersection VIDE**. C'est le seul régime où l'un des trois maillons aval a été mesuré vidant —
et il le fait à juste titre.

⚠ Ce bras avait conclu « l'arbre rend VIDE » d'un compte d'events, sans jamais lire le pool, et sa
garde de portée lisait la portée **naturelle** de l'unité (13 tuiles) au lieu de celle du sélecteur
(23). Les deux défauts sont corrigés ; le bras rend désormais `BRAS NON DISCRIMINANT`.

## 5. Le capteur

`frida/hooks/features/ai-step/movable-tiles-probe.ts` + flag `tileProbe` d'`aiPlaybookPredict`
(composable avec `gateProbe`). Ancrage `MovableTilesInRangeSelector$$Select` — seul retour vide
silencieux de la chaîne haute — **plus** les deux sous-sélecteurs qui produisent ses locales,
invisibles d'un attach sur `Select` seul : `CasterSelector$$Select` (corps entier : `ctx+0x08`) et
`CasterTileSelector$$Select` (`ctx+0x48 ?? ToList(ctx+0x40) ?? GetTiles(ctx+0x08)`, le seul nœud qui
change de branche entre les deux contextes). Champs lus par leur **nom runtime**, aucun offset en
dur ; hooks éphémères, filtrés thread, détachés en `finally`, bornés ; `findClassAnywhere` +
`findMethod`.

Le retour se lit en **deux formes**, et la classe est elle-même discriminante : `List`1` vide =
early-return silencieux ; `OrderedSet`1` = la requête a répondu. `OrderedSet<T>` **dérive** de
`List<T>` (`.ctor` sur le même `this`, `get_Item` délégué), reconnu par la **chaîne d'héritage
IL2CPP** — jamais par des noms en dur — et le stride n'est pas supposé (`class_get_element_class` +
`class_is_valuetype` : un élément VALEUR fait répondre `-1`).

Décodeur `probe_361_movable_tiles_selector._tile_verdict` : **11 états deux à deux distincts**,
garde `tests/engine/test_370_tile_probe_tristate_offline.py`. Le piège verrouillé : `nodes == []`
(arbre PAS évalué, cause en amont) et `returnedCount == 0` (pool vide) portent des verdicts
**opposés** ; `[retour-illisible]` reste strictement distinct de `[vide]`.

## 6. Ce que la gate `WillBeKill` fait, et ce qu'elle ne fait pas

Elle **gouverne** (capteur `playbook-gate-probe.ts` : `get_WillBeKill → TRUE`, 1 appel), et elle
n'est pas la cause. Le test pur reste `StormOfFlensingBladesPlaybook$$MakeDamagePredictions`, dont
le compte d'events ne dépend d'aucun sélecteur : 2 events quand le flag est faux, 0 quand il est
vrai (`probe_361_will_be_kill_gate_direct.py` volet A).

⚠ Le 1ᵉʳ jet de ce bras ne prouvait rien : sans drive, la cible est hors portée, le dégât est nul, et
on lisait 2 events des deux côtés. Le probe porte la garde qui refuse ce montage.

## 7. Ce qui reste VRAI de la RE des sélecteurs (#365)

* `DSLSelectors$$Friends`/`$$Enemies` allouent le **même** `UnitsFromFactionSelector` à un bit près
  et **partitionnent** leur entrée par `UnitExtensions$$HasFaction` ⇒ les deux batchs vides
  équivaut à `AdjacentUnits(GetTileToMoveTo(), 1, 3)` vide.
* `DSLSelectors$$AdjacentUnits(origin, unique, sel)` = `Units(AdjacentTiles(origin), unique, sel)
  op_Subtraction origin` — aucun sélecteur dédié. `AdjacentTilesSelector$$Select` exclut déjà les
  tuiles d'origine. `GenerateAttackPredictions` appelle l'index **4**
  (`TargetsSelector$$SelectUniqueUnits`) avec `(ctx, 3)` ; `UnitExtensions$$MatchesUnitSelectionType`
  à `3` = « vivante ET sans le flag `0x11` ».
* La composition est **VIVANTE** dans le contexte du playbook — `probe_361_adjacent_units_selector.py`,
  **3/3 bras exacts** sur les deux seuls autres appelants de `GenerateAttackPredictions` (xrefs) :
  `1004 MortisRound` (`Entity(target)`) rend 1 event ; `1170 ExplosivePresents` rend 3 events, cibles
  exactes, caster loin puis posé adjacent (retiré par la soustraction). Garde adversariale
  `--mutate no-subtraction` : ROUGE, `3 events pour 4 attendus`.
* Contexte construit par `GenerateAttackPredictions` : `+0x08` caster, `+0x10` target, `+0x18` owner,
  `+0x38` `GetTiles(target)`, `+0x40` `get_MainTile(casterPosition)`, `+0x48` casterPosition.
* `ExplodesAbility$$GetDamage` n'est **pas** une porte : elle rend un **arbre DSL** (elle lève au
  lieu de rendre 0), et le chemin `== 0` tombe dans le thrower, jamais dans un `return list`.

## 8. Ce qui n'est PAS couvert

* **`1059` n'entre toujours pas dans `ABILITY_CLASSES`** — port des batchs 3/4 à faire, avec
  `TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE` dans le même commit.
* **Écart PORT/NATIF sur un ring saturé** : `ramming_speed_tile_to_move_to` désigne `(2,3)` alors que
  le natif ne peut **pas** l'atteindre (intersection vide, §4b). Le port de `MovableTilesInRange` ne
  modélise donc pas le blocage par les unités que `MovementQuery$$AnyOrFillMoveableTiles` applique.
  Non confronté hors de cette géométrie ; le MATCH 2/2 de `#353-r1` portait sur des régimes non
  bloqués. **Résidu nommé, non traité.**
* **La branche `UnitExtensions$$CanMove`** n'a jamais été observée fermée : aucun montage n'a porté
  le trait `0x418` ni un blocage de mouvement. Elle est lue, pas mesurée.
* **La gate de Fragstorm** (`1048`) : son ouverture reste indéterminée, son batch étant mort en aval
  (`case-352` §3 — `memset(0)` complet ; ne pas le réparer).
* **Le régime fully-shared generic** : l'hypothèse « le lambda reçoit un pointeur décalé » est
  écartée par le capteur (`get_WillBeKill` rend TRUE sur l'objet décodé), pas démontrée impossible.
* **Six géométries** jouées côté `RammingSpeed` (deux dans `#386`/§4a, deux balayées par `probe_381`,
  une à ring saturé, une par `montage_361`) ; côté `ExplosivePresents`, trois bras sur une seule
  géométrie de board `MC1_67`. Un seul board (`MC1_67`) dans tous les cas.
