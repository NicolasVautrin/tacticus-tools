# #459 — les accesseurs de tuile rendent l'EMPREINTE, et le voisinage n'a qu'UNE vue

Deux résidus du même foyer géométrique, tranchés séparément. **Verdict : QUIRK PORTÉ pour l'item 1
(et l'énoncé y est réfuté sur un point : `OwnerTile` n'est pas ce que le natif appelle `OwnerTile`) ;
CORRECTION STRUCTURELLE mais MESURÉE INERTE pour l'item 2** — 0 arête asymétrique sur **10 boards**.

## 1. ITEM 1 (`#433-r3-r1a-r2`) — ce que rendent RÉELLEMENT les trois accesseurs

Les deux mesures de #517 sont **confirmées**, et la RE en ajoute la moitié manquante : la cascade
complète et le contrat de CONSOMMATION.

| accesseur | artefact natif | rend |
|---|---|---|
| `CasterTile()` | `DSLSelectors+0x50` **et** `+0x58` → `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` | `CasterPosition.Tiles` (+0x48) `?? CasterTile.ToList()` (+0x40) `?? GetTiles(Caster)` (+0x08) — une **LISTE** |
| `TargetTile()` | `DSLSelectors+0x78` → `IdunBattle.Entities.Selectors.TargetTilesSelector$$Select` | `TargetPosition.Tiles` (+0x38) `?? TargetTile.ToList()` (+0x30) `?? GetTiles(Target)` (+0x10) |
| `OwnerTile()` | **pas un slot** — le natif passe `Owner@0x148` (l'ENTITÉ) | l'empreinte, dépliée par `SelectTiles` |

**Aucune branche `GetMainTile`** dans les deux premiers, et `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`
alloue bien `+0x50` et `+0x58` depuis le **même pointeur de classe** (`DAT_183342968`), même ctor —
les deux mesures de #517, re-vérifiées. Les slots sont identifiés **sans ambiguïté** par les triggers
qui les comparent : `IdunBattleLogic.Entities.DSLTriggers$$get_CasterIsCasterTile` = `AreEqual(+0x48, +0x50)`,
`$$get_OwnerIsCaster` = `AreEqual(+0x30, +0x48)`, `$$get_OwnerIsTargetTile` = `AreEqual(+0x78, +0x30)`.

### `OwnerTile` — l'énoncé est réfuté, dans les deux sens

Le natif **a** une notion de « tuile de l'owner », et ce n'est pas un slot : c'est
`IdunBattleLogic.Entities.DSLSelectors$$MainTileOfUnits(Owner@0x148)` →
`IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select` = `GetMainTile` par entité = **UNE**
tuile (`$$get_OwnerTileIsTarget` en est la preuve directe). Mais **aucun des trois call-sites portés
ne l'utilise** : `fighting_retreat_adjacent_enemies`/`_friends` et `martial_apotheosis_valid_targets`
mirrorent `AdjacentEnemies(Owner@0x148, …)` / `AdjacentUnits(casterTile@0x148, …)` — l'ENTITÉ, que
`SelectTiles` déplie. Le nœud `OwnerTile` du port est donc un véhicule de collapse mal nommé, et il
devait s'élargir comme les deux autres. Le prendre pour `MainTileOfUnits` aurait été l'erreur
symétrique.

### Le contrat de CONSOMMATION a deux faces, et le port n'en avait qu'une

C'est ce qui rend l'élargissement **sûr** au lieu d'être une régression en chaîne :

```
IdunBattle.DSL.TargetsSelector$$SelectTiles(entities)      // PLURIEL, vslot 0xa
    list = this.Select(entities);
    if (this.<IsTileSelector>) return list;                          // deja des tuiles
    foreach (e in list) foreach (t in IterateTiles(e, state)) result.Add(t);   // l'EMPREINTE

IdunBattle.DSL.TargetsSelector$$SelectTile(entities)       // SINGULIER, vslot 0xc
    foreach (e in this.Select(entities)) {
        if (IsTile(e)) return e;
        if (IsUnit(e) || IsUnitFoot(e)) { t = GetMainTile(e, state); if (t != null) return t; }
    }
    return null;                                                     // la PREMIERE tuile
```

Les consommateurs scalaires appellent tous `SelectTile`, **lu au décompilé un par un** :
`IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select` (son `unitTileSelector` @+0x28
remplace le `GetMainTile(unit)` par défaut), `IdunBattle.Entities.Selectors.TilesBehindInLineSelector$$Select`
(origin @+0x18 **et** direction @+0x20), et le référent de
`IdunBattle.Entities.Selectors.SortByDistanceSelector$$Select` (son comparateur ferme sur **un**
`PositionComponent`). `IdunBattleLogic.Entities.DSLSelectors$$TilesUnitCanMoveToChargeTarget` passe
son `casterTiles` à ce même `MovableTilesInRangeSelector` — donc scalaire lui aussi.

Le port pose donc le nœud `SelectTile` (mirror du singulier) et l'applique aux **8** sites scalaires.
Sur une unité mono-hex il rend exactement ce que rendait l'accesseur d'avant, et **même sur une unité
multi-hex** : `snapshot._load_feet` recale la `PositionComponent` sur `feet[0]`, donc
`SelectTile(TargetTile()) == _pos(target)` — attesté par un test live dédié.

### Le périmètre, RE-DÉRIVÉ par AST (jamais hérité)

Balayage AST de `engine/`, consommateur direct par site : **50 sites** — `CasterTile` **28**,
`TargetTile` **19**, `OwnerTile` **3**. Ventilation par contrat :

| contrat | sites | traitement |
|---|---|---|
| PLURIEL (`Adjacent*`, `Surrounding*`) | 39 | l'empreinte, sans changer le call-site |
| PLURIEL (`AdjacentTiles`) | 3 | idem — le nœud accepte déjà une liste |
| SCALAIRE (`TilesBehindInLine` ×2, `tiles_unit_can_move_to_charge_target` ×2, `SortByDistance`, `MovableTilesInRange`, `Cache` ×2) | 8 | enveloppés par `SelectTile` |

Le compte « 52 lecteurs à origine TUILE » de #517 (`--step occupancy`) est **re-mesuré identique**
(101 sites exécutables, 25 ENTITÉ / 52 TUILE) : il compte les *lecteurs d'occupation*, pas les
*instanciations d'accesseur* — les deux vues sont cohérentes.

## 2. ITEM 1bis — le second quirk : les DEUX exclusions ne sont pas la même

Rien ne l'annonçait, et c'est ce qui empêche de généraliser depuis `_origin_tiles`. **C'est le
SÉLECTEUR qui tranche, pas le rayon** :

```
IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select
    tiles = this.source.SelectTiles(entities);              // l'EMPREINTE
    foreach (t in tiles) foreach (a in GetAdjacentTiles(t, false, true, true))
        if (!tiles.Contains(a)) result.Add(a);              // TOUTE l'empreinte retranchee

IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles(origin, includeCenter: 0, ...)
    = SurroundingTiles(origin, includeCenter: 1, ...) op_Subtraction Tiles(origin)
      // Tiles = UnitsMainTilesSelector = GetMainTile PAR ENTITE -> UNE tuile
```

Conséquence, sur le **même** état et le **même** rayon : une origine multi-hex **ne peut pas**
ressortir de son propre `AdjacentUnits`, et **ressort** de son propre `SurroundingUnits`. Les deux
verdicts sont opposés ; c'est la contre-épreuve la plus forte du lot, et le brief avait raison de
prévenir que retrancher toute l'empreinte côté `Surrounding` serait « une seconde erreur ».

Le port porte les deux : `_within` choisit son exclusion sur `order`, et `AdjacentTiles` applique
son `Contains`. Sur mono-hex les deux formes coïncident terme à terme — c'est ce qui rendait
l'écart invisible.

## 3. ITEM 2 (`#457-r1`) — laquelle des deux vues est juste, et ce que ça change

**Les deux appels sont le MÊME appel, à l'octet près.** Décompilé :

```
MovementQuery$$IsAdjacent(a, b) :
    lVar1 = <IBattleQuery slot 0x4f>(this->battleQuery@+0x30, a, 0, 1, 1);   return lVar1.Contains(b);
MovementQuery$$GetPossibleTileListsFromMovableTiles, branche feetCount == 7 :
    uVar4 = <IBattleQuery slot 0x4f>(this->battleQuery@+0x30, t, 0, 1, 1);   ...
```

Même slot, même receveur, mêmes flags `(onlyEmptyOrSteppable: 0, onlyWalkableTiles: 1,
allowTemporary: 1)`. La vue est celle de
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, qui énumère la
liste d'adjacence **STOCKÉE** (`ConnectivityComponent`) avec une porte d'élévation `|Δ| < 2`
inconditionnelle : ⇒ **`Board.neighbours_native`**. `is_adjacent` lisait `board.neighbours()` (triée
**et** symétrisée) : c'était la lecture fausse. Foyer unique posé :
`movement_query.adjacent_tile_ids`.

### Le rayon de souffle, MESURÉ — et il est NUL en ensemble

L'asymétrie vit dans le `ConnectivityComponent`, **non dérivable** des dumps `data/boards/` (ils
portent la `BattleConfiguration`, pas la connectivité) : il faut capter le `boardGraph` d'un runner.
`probe_459_adjacency_view.py`, **10 boards** (`MC1_67`, `C1_74`, `C2_02`, `C4_09`, `C1_25`, `C1_02`,
`C3_01`, `SyncPvp_Arctic_06`, `C1_50`, `C2_26`) :

| mesure | résultat |
| --- | --- |
| arêtes dirigées ajoutées par la symétrisation | **0**, sur les 10 boards |
| verdicts d'`is_adjacent` qui changent | **0** |
| empreintes à 3 pieds (`IsValidUnitFeetList`, permutations comprises) qui changent de validité | **0** (sur 48 à 204 candidates par board) |
| anneaux à 7 pieds dont l'**ensemble** change | **0** |
| anneaux à 7 pieds dont l'**ORDRE** change | **33 à 63 par board** |

⇒ **La divergence est INERTE en ensemble** : le graphe stocké capté est déjà symétrique sur ce build.
Ce qui diffère réellement entre les deux vues, c'est le **tri** — inerte pour `is_adjacent` (un
`Contains`) et déjà correct pour la branche 7 (qui lisait `neighbours_native`). La correction est
donc **structurelle** : elle supprime la possibilité de divergence, elle n'en corrige aucune
observée. Le dire est le point — ne pas la maquiller en gain.

⚠ **Une affirmation du dépôt n'est PAS reproduite** : la docstring de `entities/pathfinding/board.py`
annonce « ~18 arêtes one-way observées ». Sur ces 10 boards et ce build, **0**. Soit la mesure
d'origine portait sur un autre build, soit sur des boards non couverts ici. Non tranché — la
docstring n'est pas modifiée, et le résidu est nommé (`#459-r3`).

⚠ **`#457-r2` reste OUVERT et n'est pas fermé ici** : `onlyWalkableTiles = 1` n'est réappliqué nulle
part (le `boardGraph` est capté avec `requireWalkable = 0`, murs inclus à dessein). Inerte sur les
deux consommateurs — leurs tuiles viennent toutes de `GetMovableTilesFor` (pathfinding) ou de
l'empreinte courante, donc marchables par construction — mais mordant dès qu'un appelant y ferait
entrer un mur. Le foyer `adjacent_tile_ids` est désormais l'endroit UNIQUE où le poser.

## 4. Ce qui a été MESURÉ

### LIVE — `test_459_tile_accessors_live.py`, 13/13

Porteur multi-hex : `ultraDreadnought` (MoW du pool) → `DutyEternal` (1158) → `ultraSmnDreadnought`
sur **3 tuiles**, board `MC1_67`. **Le montage n'est pas forké** : la fixture de
`test_433_r3_r1a_occupancy_live.py` est appelée par sa fonction sous-jacente (`__wrapped__`), donc
son critère de discriminance (`_pick_anchor`) est celui d'origine, pas une copie.

**Trois oracles natifs indépendants du port**, et aucun cast à mesurer :

| canal natif | ce qu'il ancre |
|---|---|
| `boardGraph.tiles[].occupantUnitId` (projection du `TileContentComponent`) | l'EMPREINTE (3 pieds) |
| `observeBattle.units[]`, une ligne par PIED, `entityId` croissant | la MAIN TILE = `_feet[0]` |
| `boardGraph.tiles[].neighbours` (le `ConnectivityComponent`) | l'ANNEAU natif |

⚠ **Un oracle a été essayé puis RÉFUTÉ par la mesure, en cours de route** :
`decisionView.units[].pos` n'est **pas** la main tile — `decisionView` déduplique la projection
par-pied et rend le **dernier** pied (mesuré ici : `(2,2)` contre `(1,2)`). C'est exactement le piège
que `snapshot._load_feet` documente depuis #R30, et il a fait rougir ce fichier avant d'être corrigé.
Un cran dédié (`test_decision_view_pos_is_not_the_main_tile`) le fige, pour qu'aucune tranche
ultérieure ne le reprenne comme oracle.

### OFFLINE — `test_459_tile_accessors_offline.py`, 20/20

Un axe par face, chacun avec sa réciproque : les trois accesseurs, la cascade `CasterPosition`, le
`SelectTile` singulier (et son identité sur mono-hex), les deux exclusions **et leur coïncidence sur
mono-hex**, l'exclusion d'`AdjacentTiles` (et son inertie sur mono-hex), la vue stockée sur un board
à **arête dirigée** construit exprès.

### Matrice de MUTATION — chaque mutant mord à SON cran

Cinq mutants, appliqués par patch textuel puis restaurés (revert vérifié vert dans les deux passes) :

| mutant | rouges OFFLINE | rouges LIVE |
|---|---|---|
| M1 — accesseurs collapsés en main tile | **6** | **7** |
| M2 — `adjacent` n'exclut que la main tile | **2** | **1** |
| M3 — `surrounding` exclut toute l'empreinte | **1** | **1** |
| M4 — `adjacent_tile_ids` sur la vue symétrisée | **3** | **0** |
| M5 — `AdjacentTiles` sans exclusion | **1** | **2** |

**M2 et M3 sont réciproques et disjoints** : chacun ne rougit que sur SON axe, sur le même montage et
le même rayon. **M4 rouge offline, inerte live** — c'est la même mesure que le §3 par une seconde
voie : le board réel n'a pas d'arête asymétrique, seul le board construit exprès en a.

### Non-régression — **31 fichiers, 194 tests LIVE** + **942 tests OFFLINE**

Offline : `probe_457` en 3 shards, **86 fichiers, 942 tests, 3 verdicts PASS** (le fichier neuf y
entre tout seul — son périmètre se dérive).

Live, face COMBAT : `test_multihex_dutyeternal_live` (20), `test_433_r3_r1a_occupancy_live` (10),
`test_433_r3_r1_dsl_footprint_live` (4), `test_targeting_adjacency_rules_live` (22),
`test_splash_targeting_live` (10), `test_splash_range_clamp_live` (18), `test_death_nova_live` (5),
`test_doom_siren_live` (4), `test_harvester_live` (3), `test_plasma_grenade_splash_live` (1),
`test_stikkbomb_migration_live` (1), `test_plasma_cannon_lateral_live` (1),
`test_scything_talons_migration_live` (1), `test_psyker_splash_live` (1),
`test_gauntlets_combat_live` (1), `test_jakhal_stimms_live` (3), `test_dark_talon_strike_live` (2),
`test_black_legion_1029_1020_live` (10).

Live, les abilities DIRECTEMENT éditées : `test_rad_bombardment_live` (4),
`test_thunderous_assault_push_live` (2), `test_thunderous_assault_targeting_live` (1),
`test_waaagh_cast_gate_live` (6), `test_waaagh_buff_contrib_live` (7),
`test_353_ramming_speed_prediction_live` (4), `test_383_ramming_speed_explosion_live` (4),
`test_381r1_movable_tiles_pool_live` (4), `test_charge_tile_utility_live` (6).

Live, face DÉCISION : `test_thrice_blessed_decision_live` (4), `test_plasma_grenade_decision_live` (8),
`test_mass_driver_splash_prediction_live` (5), `test_stikkbomb_decision_live` (9, **joué SEUL** —
il ne tient pas dans un lot de 4, contention mesurée par #517).

### La banque de cliquets — et ce qu'elle a exigé au passage

Relevé daté, joué depuis ce worktree : **33 cliquets, VERTE, mur 116,2 s**. La banque se *définit*
dans `scripts/ratchets.ps1` ; cette ligne l'*atteste*.

Son premier passage a rougi sur `pytest_attestations`, et c'était **un effet direct de cette
tranche** : citer `DSLTriggers$$get_CasterIsCasterTile` / `$$get_OwnerIsTargetTile` /
`$$get_OwnerTileIsTarget` dans `accessors.py` les inscrit au registre `#337`, qui refuse tout
`CITE_A_QUALIFIER` — l'aveu que l'outil ne sait pas attribuer. Les trois sont entrées dans
`docs/rl/dsl-port-attestations.tsv` en **`NON_PORTE` LU** (mention documentaire : elles ancrent la
carte des slots, aucun artefact du port ne construit ces triggers d'égalité), et l'inventaire figé
du test a suivi. C'est le geste que le cliquet exige ; ce qui aurait été interdit, c'est de retirer
les citations pour faire taire le rouge — elles sont précisément ce qui rend le mapping de slots
vérifiable au grep.

## 5. Résidus NOMMÉS

* **`#459-r1` — la position candidate n'est portée que par sa MAIN TILE.** `CasterTileSelector`
  rend `CasterPosition.Tiles`, c'est-à-dire la `UnitPosition` **entière** de la tuile d'attaque
  balayée ; le port ne stocke qu'un `(col,row)` dans `ctx.caster_pos`, donc cette branche rend une
  liste d'UN élément. Inerte côté runner (`caster_pos` None → `_feet`) et pour toute unité mono-hex ;
  mordrait sur la face DÉCISION d'un caster multi-hex. Fermer ce résidu exige de porter la
  `UnitPosition` candidate jusqu'au contexte DSL, pas seulement sa main tile — c'est aussi ce que
  demande `#433-r3-r1c` (« l'empreinte n'existe pas côté DÉCISION »).
* **`#459-r2` — `AdjacentTiles` ne DÉDOUBLONNE toujours pas.** Le natif accumule dans un
  `OrderedSet` ; le port rend l'union brute. Sans effet aux call-sites portés (ils font suivre d'un
  `Unique`/`TileUnique`), mais l'écart devient visible dès qu'une origine multi-hex alimente un
  consommateur qui compte, et l'élargissement de #459 rend justement ce régime atteignable.
* **`#459-r3` — les « ~18 arêtes one-way » de `board.py` ne sont pas reproduites.** 10 boards
  mesurés sur `rnca9r7q6c` : **0**. La docstring n'est pas corrigée (elle peut décrire un autre
  build ou d'autres boards) ; la trancher demande de balayer les 779 boards, donc 779 builds.
* **`#457-r2` — `onlyWalkableTiles = 1` n'est appliqué nulle part** (cf. §3). Le foyer où le poser
  existe maintenant.
* **`#459-r4` — les consommateurs scalaires ne sont enveloppés que là où le port les nomme.** Deux
  probes versionnés (`probe_353r1_ramming_speed_charge_tile.py`, `probe_381r1_movable_tiles_pool.py`)
  passent encore `CasterTile()` **nu** à `MovableTilesInRange`. C'est sans effet — le nœud prend déjà
  la première position de ce qu'il reçoit, ce qui est le `SelectTile` natif — mais le mirror n'y est
  pas explicite.

Résidus hérités toujours ouverts : `#433-r3-r1a-r1` (flag `unique` de `Units`),
`#433-r3-r1a-r3` (`MatchesUnitSelectionType`), `#433-r3-r1a-r4` (la chaîne end-to-end « une AoE
endommage par un pied secondaire »), `#433-r3-r1a-r5`, `#433-r3-r1b`, `#433-r3-r1c`, `#433-r3-r1d`,
`#457-r3`, `#457-r4`.
