# case-589-r2 — l'aval de `tilesMovedThisTurn` RECONFRONTÉ pour `MastersOfManoeuvre`

`#589-r2`. Deux crans de `master` étaient **ROUGES**, même cause : `#589-r1` avait classé
`MastersOfManoeuvre` « saturé » en s'appuyant sur le fait que **son trigger n'était pas porté**.
Il l'est depuis `#999-r1` (`MastersOfManoeuvrePlaceOnMove`), donc son seuil est **exercé**, et les
deux crans réclamaient la reconfrontation. Elle est faite — et **mesurée, pas déduite**.

| cran | avant | après |
|---|---|---|
| `test_589r1_tiles_moved_consumers_offline.py` | 1 failed / 8 passed | **10 passed** |
| `probe_589r1_tiles_moved_consumers_live.py --only INV` | FAIL (2 écarts) | **PASS** |

Le second portait **deux** accusations : `MastersOfManoeuvre` (réelle) et `EmpyricAmbush`
(**périmée** — fermée par `#589-r1-r1`, le probe était en retard sur sa propre fermeture).

## 1. Le natif, relu VERBATIM sur `t6dpr4k06g`

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MastersOfManoeuvreAbility$$CreateTrigger`,
branche `<A>` — la seule qui lit le compteur :

    AmountIsEqualOrGreater( TilesMovedThisTurn( Actor@<DSLSelectors+0x40> ),
                            Get( GetNumberConstant( config@<this+0x20>,
                                 AbilityConstantType.tilesTraversed = 0x88 ) ) )

`IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` rend
`<ActorStatisticsComponent>+0xf0`, et **0** quand l'entité n'a pas le composant.
`tilesTraversed` **relu du gameconfig courant = 2**.

Le port est un mirror 1:1 (`triggers/loki/masters_of_manoeuvre.py`), et sa chaîne d'alimentation
est bien celle que `#589` a rebranchée — vérifiée bout à bout :
`operations/movement.py::_num_tiles_moved` (`get_num_tiles_moved(get_connected_path_to(...))`)
→ `components.record_tiles_moved` → `uc.tiles_moved_this_turn`
→ `behaviours/context.py::_unit_dict["tilesMovedThisTurn"]` → `formulas.TilesMovedThisTurn`.

## 2. Le verdict : **SATURÉ** — 5253 couples divergents, 0 bascule, témoin non-nul

`probe_589r2_masters_of_manoeuvre_aval.py --only GATE` évalue **le gate porté lui-même** (pas un
scalaire intermédiaire) sur les deux substrats, tous couples × 4 régimes :

| board | couples divergents (`n_G != n_C`) | bascules `MastersOfManoeuvre` (K=2) | bascules **témoin** `EmpyricAmbush` (K=4) |
|---|---|---|---|
| `C1_74` (2 `Bridge`) | 326 | **0** | 70 |
| `C3_14` (15 `Bridge`) | 4927 | **0** | 1258 |

Ventilation `C3_14` : `Walk` 0 divergent · `Fly` 943 · `TeleportStrike(Walk)` 1992 ·
`TeleportStrike(+Fly)` 1992.

⚠ **Le témoin est ce qui empêche ce zéro d'être vide.** « aucune bascule » et « la mesure ne sait
pas voir de bascule » sont indistinguables sans lui : un seuil placé **au-dessus de la borne**
bascule 1328 fois sur les **mêmes** couples. Le zéro est donc un résultat, pas un silence.

## 3. La borne avait une HYPOTHÈSE CACHÉE — et le cran qui la gardait l'écartait en silence

La saturation vient de : la beeline n'est recousue que `if (GetDistance(last, next) > 1)`, donc le
sous-chemin compte `>= 2` arêtes **dans les deux substrats** (`C ⊆ G` ne peut qu'allonger) ⇒ tout
seuil `K <= 2` est franchi avant comme après.

**Cette dérivation suppose que la beeline TROUVE un chemin.** Or elle peut échouer :
`IdunBattle.Entities.Pathfinding.BasePathfinder$$FindPath` rend `null` quand la destination est
inatteignable dans le voisinage (échec du `TryGetValue` de la remontée d'arbre BFS). Et là, les
deux côtés **divergent** :

* le **natif** ne dégrade pas, il LÈVE — `MovementQuery$$GetConnectedPathTo` fait
  `if (<beeline> == 0) goto <raise>`, qui tombe sur `FUN_1801f5460` (= `FUN_180201bc0(); swi(3)`) ;
* le **port** écrit `for mid in (sub or [])[1:-1]` — il avale l'absence et compte le saut pour
  **1** arête.

C'est le **seul** régime où `n_C < n_G`, donc le seul où `K = 2` pourrait basculer
(`n_C = 1 < 2 <= n_G`), dans le sens permissif→restrictif.

Le cran `S1` de `probe_589r1 --only SCAN` ne pouvait pas le voir : `if lg is None or lc is None:
continue` — un compte filtré qui ne dit pas ce qu'il filtre, **exactement sur le régime qui
casserait la borne**. Le cran `BORNE` de `#589-r2` les **compte** :

| board | couples à `d_hex > 1` | beeline sans chemin (canal seul / géom. seule / les deux) | sauts réellement recousus | dont sans chemin canal |
|---|---|---|---|---|
| `C1_74` | 3590 | **0 / 0 / 0** | 3590 | **0** |
| `C3_14` | 3590 | **0 / 0 / 0** | 3590 | **0** |

⇒ le régime est **VIDE sur les deux boards mesurés**, `min(beeline) = 2` en `G` comme en `C`. La
borne tient, et elle tient désormais **par mesure de son hypothèse**, plus seulement par
dérivation. L'écart de fidélité, lui, reste ouvert : `#589-r2-r1`.

## 4. Ce que la sortie du registre a coûté en garde — le remplaçant

`MastersOfManoeuvre` sort de la liste accusée exactement comme `EmpyricAmbush` en `#589-r1-r1` :
non par assouplissement, mais contre un garde **discriminant**,
`test_le_seuil_porte_de_MastersOfManoeuvre_ne_BASCULE_pas`, qui exerce le **gate porté** sur ses
deux faces (bascule à `K` exactement ; même verdict sur les deux substrats), avec son témoin.

**Contre-épreuve jouée** (3 mutants, hors dépôt) — le cran n'est pas vide :

| mutant | effet attendu | mesuré |
|---|---|---|
| M1 — le gate lit un seuil au-dessus de la borne (3) | face 2 rougit | **8 bascules sur 8 divergents** |
| M2 — le gate bascule à `>` au lieu de `>=` | face 1 rougit | `n = K` n'ouvre plus |
| M3 — témoin placé **sous** la borne (2) | non-vacuité rougit | témoin **0** |

Deux gardes de **non-vacuité** sont posés en plus, parce que la sortie du registre repose sur un
fait qui peut disparaître : le test asserte que `MastersOfManoeuvre` **est** encore dans les tokens
exécutables de `triggers/`, et le probe qu'`EmpyricAmbush` et lui ont encore un trigger porté. Sans
eux, perdre le trigger rendrait les remplaçants silencieusement vides.

## 5. Le probe lisait la PROSE — corrigé, et ça changeait un verdict

`_port_consumers` détectait par `re.search` sur le texte brut. Passé à l'**AST** (même traitement
que le test) : `ModifiedExoarmour` bascule `True → False`, et **`False` est le verdict juste** —
ses 3 occurrences sous `triggers/` sont **toutes** de la prose (`maugetar.py:48`,
`prophetic_sentinel.py:72`, `wireweave_net.py:36`), la première étant la ligne qui avait déjà fait
rougir `master`. Son ability est portée côté **effet**, pas par un trigger.

## 6. Reproduction

    python probe_589r2_masters_of_manoeuvre_aval.py --only INV
    python probe_589r2_masters_of_manoeuvre_aval.py --only BORNE --board C1_74
    python probe_589r2_masters_of_manoeuvre_aval.py --only GATE  --board C3_14
    python probe_589r1_tiles_moved_consumers_live.py --only INV
    python -m pytest tests/engine/entities/pathfinding/test_589r1_tiles_moved_consumers_offline.py

## 7. Ce qui n'est PAS couvert

* **L'écart de fidélité du §3 n'est pas corrigé**, seulement mesuré non-atteint sur 2 boards.
  Résidu `#589-r2-r1` — il touche `services/movement_query.py`, foyer partagé de `#589`.
* **285 des 287 boards à `Bridge` restent non mesurés** sur ce régime : le `0 / 0 / 0` vaut pour
  `C1_74` et `C3_14`. Un board dont le `ConnectivityComponent` aurait une composante isolée le
  rouvrirait — non cherché.
* **La pose n'est pas confrontée live dans un régime où la beeline mord.**
  `test_1038_masters_of_manoeuvre_live.py` confronte bien le seuil au natif (bras 2 tuiles +
  contre-bras 1 tuile), mais sur `MC1_67` avec un **marcheur** (`worldKharn`) — soit le régime où
  `#589` est inerte (`Walk` : 0 couple divergent, mesuré ici sur les deux boards). C'est un
  régime **structurellement dégénéré** pour l'axe `G → C`, puisque la borne interdit toute bascule
  à `K = 2` : il n'existe aucun montage live discriminant. Le verdict repose donc sur les 5253
  couples du §2, pas sur un bras de bataille.
* **La branche `<B>`** (`On(0x28 = UnitFinishedTurn)`, gate d'adjacence) ne lit pas le compteur :
  hors périmètre de `#589`, non touchée.
* **`SmashaEad`** reste non exercé (aucun trigger porté) — il reste, seul, dans la liste accusée.
