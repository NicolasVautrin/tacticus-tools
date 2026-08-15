# #433-r4-r2-r1-r2-r2-r1-r1-r1 — la tuile SOURCE dans la zone, et les 8 masques hors pool

**Critère binaire** : la zone d'une ability contient-elle la tuile du CASTER, et sous quelle
condition ? Et les abilities actives HORS POOL portent-elles leur masque ?

**Verdict** : la prémisse héritée — « la règle n'est pas uniforme, un correctif naïf casserait
l'autre branche » — est **RE-CADRÉE par la lecture** : elle l'est, mais la règle ne vit pas
entièrement dans `GetTilesInRange`. Fix porté, mesuré live (**FP 1 → 0** en régime singleton).
Item 2 : **8** masques posés, pas 10 — un est NON LU, un autre était déjà au registre.

---

## 1. La cascade, relue en entier

`IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`, avec le slot `IBattleQuery` de chaque
branche génératrice et sa signature :

| branche (ordre natif) | slot | zone | tuile source |
|---|---|---|---|
| `(int)range < 0` | — | `OrderedSet` VIDE | — |
| `range.UseWholeBoard` | `0x69` `GetAllTiles()` | tout | **INCLUT** |
| `(int)range == 0` | — | `rules >> 0xf & 1` ? `casterTiles` : VIDE | ssi bit 15 |
| `range.OnlyAdjacent` | `0x51` `GetAdjacentTiles(casterTiles, false, !bit43, true)` | couronne | **EXCLUT** |
| `rules & TargetIsAtRange` | `0x64` `GetTilesAtDistance(casterTiles, (int)range, false)` | anneau `d == v` | EXCLUT |
| sinon | `0x67` `GetSurroundingTiles(casterTiles, (int)range, false, !bit43, false, includeCenter)` | disque | ssi bit 15 |

Les slots sont attribués par la **signature** de leur surcharge (6 paramètres nommés
`center/distance/onlyEmptyOrSteppable/onlyWalkable/onlyMovable/includeCenter` pour `0x67`, 3 pour
`0x64`, 4 pour `0x51`), jamais par un comptage à l'œil. `includeCenter` est le seul paramètre qui
rende la source : `TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` balaie le disque en
coordonnées CUBE et ne garde une tuile que si `includeCenter || tile != center` ; la surcharge
LISTE re-filtre en plus par `ListExtensions$$FilterInPlace` sur les centres.

⚠ **La fiche `#…-r1-r1` §7 citait `GetTilesInRadius`** — ce nom n'existe pas dans le binaire, et
c'est ce qui a masqué le paramètre `includeCenter`.

## 2. Ce que la cascade ne dit pas — l'appelant RE-AJOUTE

`TargetingQuery$$GetPossibleTargetsForOptions`, juste après et **avant** les trois `RemoveAll` :

```
if (rules >> 0xf & 1)          tiles.<IOrderedSet slot 0>(casterTiles)   // CasterIsPossibleTarget
if (rules & 0x200000000000000) tiles.<IOrderedSet slot 0>(casterTiles)   // TargetIsCasterOrEnemy
```

Le slot 0 est un **AJOUT**, et c'est une lecture : `MovementQuery$$GetMovablePositionsFor`
l'invoque sur le même couple (interface, receveur) avec `EntityExtensions$$IterateTiles(unit)` —
le movable set d'une unité contient sa tuile courante. Le slot 1 de la même interface est
`RemoveAll(Predicate)`, celui du filtre de walkability. Confirmation **croisée** : le port
`services.movement_query.get_movable_positions_for`, écrit par une tranche antérieure, documente
déjà `movable.AddRange(EntityExtensions.IterateTiles(unit, state))`.

⇒ **la source est dans la zone ssi `UseWholeBoard | CasterIsPossibleTarget | TargetIsCasterOrEnemy`**.
Les branches `range == 0` et `GetSurroundingTiles` lisent le MÊME bit 15 que le premier ajout :
elles n'en sont pas des exceptions. La règle est donc uniforme — au niveau du CONSOMMATEUR.

## 3. Ce que le port faisait, et le gisement

`_ability_covers_tile` testait `d <= tiles_in_range_reach` : `d = 0` passait **toujours**.
Mesuré (`probe_…_source_tile_zone --step inventaire`) : **148** abilities, **683** unités,
**97 947** couples résolus, dont **61 748** changent de réponse à `d = 0`. Ventilation des
branches : `only_adjacent` 49, `radius` 47, `whole_board` 35, `range_zero` 13, `non_lu` 4,
`at_range` **0**. **20** abilities re-ajoutent la source ; **aucun** des 18 profils d'attaque
normale — donc son terme était faux pour toute unité.

Foyer unique `_range_terms` : `tiles_in_range_reach` (le rayon) et `tiles_in_range_zone_contains`
(l'ensemble) le partagent, sinon ce serait le fork que `#…-r1-r1` venait de supprimer. Le rayon
reste la **borne supérieure** exacte de la zone — gardé, 103 900 points, 0 hors borne.

## 4. La mesure LIVE — ce que l'oracle peut, et ce qu'il ne peut pas

L'oracle `aiMovableTiles {threat: true}` enchaîne `GetMovableTilesFor` puis
`GetAllTilesInAbilityRange(unit, <ce set>, includeNormalAttack: 1)`. Deux faits mesurés :

* le `possiblePositions` **ne contient pas la tuile courante** (c'est `GetMovablePositionsFor`,
  l'autre surcharge, qui l'y ajoute) ; `overrideRange: 0` rend `tiles: []` **et** `threatTiles: []`
  pour toutes les unités — un verdict lu là-dessus serait un artefact, pas une réponse ;
* l'écart ne s'observe qu'en **movable set SINGLETON** : sinon chaque position est couverte depuis
  une autre. On l'obtient par des fillers qui OCCUPENT les tuiles de spawn voisines.

| montage | board | n_move | natif | port AVANT | port APRÈS |
|---|---|---|---|---|---|
| `astraBullgryn` / `1017` (aucun bit) | `MC1_67`, 3 fillers | **1** | 5 | 6 (**1 FP**) | **5 — 0 FP, 0 FN** |

Le FP unique est exactement la tuile du movable set. Gates CASTER alimentés (`decisionView`
`allAbilities: true`) dans les deux colonnes.

## 5. Ce qui n'est PAS couvert

* **`#433-r4-r2-r1-r2-r2-r1-r1-r1-r1` — la branche INCLUSION n'est pas confrontée live.** Le seul
  porteur testable du pool (`orksRuntherd` / `1045`, `CasterIsPossibleTarget` + `RANGE_SELF`) est
  annulé par un étage AMONT : mesuré en singleton, `natif = 5 = port(attaque normale SEULE)`, donc
  son ability ne verse RIEN côté natif et la mesure n'atteint jamais la zone. Trois lectures
  concordantes la soutiennent (branche `range == 0`, `includeCenter`, l'ajout aval) — c'est une
  lecture, pas une mesure.
* **`#433-r4-r2-r1-r2-r2-r1-r1-r1-r2` — `1091 SlashingDive` n'a pas de masque.** Aucune classe
  `SlashingDiveAbility` dans les tables (seuls son Playbook et ses Visuals portent ce nom), donc
  aucun ctor à lire. L'absence ne prouve rien : un ctor trivial `return <Base>$$.ctor(this);` est
  dédupliqué par IL2CPP. Trancher exige le slot de vtable de l'INSTANCE, au runtime.
* ~~**`#433-r4-r2-r1-r2-r2-r1-r1-r1-r3`**~~ — **le zéro porte désormais sur le BINAIRE (2026-08-15).**
  « 0 porteur sur les 148 masques lus » ne visitait que le registre du port : un ctor non lu aurait
  pu porter le bit sans que rien ne le montre. Le compte a d'ailleurs bougé depuis (**182** masques
  lus, `TARGETING_OPTIONS_UNPORTED` désormais VIDE) sans que le zéro change — ce qui ne le fondait
  pas davantage.
  `probe_433r4r2r1r2r2r1r1r1r3_anneau_at_range.py` visite la population ENTIÈRE : les **261**
  `IdunBattleLogic.Entities.Abilities.Active.*$$.ctor` de
  `data/symbols/<build>/ghidra/functions.tsv`, chacun devant tomber dans l'un des trois ensembles
  dont le masque est lu — registre + attaque normale, `CTORS_RELUS` (les 74 relus un par un pour
  cette tranche), presets du `cctor`. **0 DÉCOUVERT**, et un ctor hors des trois fait ROUGIR : c'est
  ce qui rend le zéro durable au prochain build.
  Les quatre sources, mesurées : 182 masques de registre, 18 profils d'attaque normale, **16**
  presets (`rules` ∈ {`0x4002`, `0x4000`, `0x80040`, `0x8500`, `0x6000040`, `0x42`, `0x102004032`,
  `0x8004`, `0x400`, `0x200000000000004`}), 61 ctors relus — **0 porteur du bit 9**. Les trois
  fabriques sont incluses (`CustomIdunNormalAttackOptions` `+0x80 | extraRules`,
  `CustomLokiNormalAttackOptions` `+0x00 | extraRules`, `SelfCastIfEnemyInCustomRangeOptions`
  `0x4000`), leurs `extraRules` lus à l'octet au call-site (`0x10000000`, `0x2`, aucun).
  **Aucune liste blanche** : les 16 ctors `Test*` sont RELUS, pas exclus par préfixe — les exclure
  aurait ré-introduit le vice même que la tranche corrige.
  ⇒ La branche ANNEAU est **structurellement inatteignable** dans ce build, et NON CONFRONTABLE :
  le masque est câblé dans le ctor natif, donc ni la greffe (`catalog_inject`) ni l'injection de
  catalogue ne peuvent armer le bit. Cran synthétique + cran de couverture, cf.
  `tests/engine/test_433r4r2r1r2r2r1r1r1r3_anneau_offline.py`.
* **`#433-r4-r2-r1-r2-r2-r1-r1-r1-r4` — `AttackQuery$$GetInvalidCasterReason` n'est pas porté.**
  C'est un QUATRIÈME gate de la surcharge 4 arguments, distinct des trois de `#…-r1-r1-c` (que le
  port lit déjà) : alimenter `ability_state` ne l'a PAS fermé. Il inclut le gate dynamique CASTER
  (`CasterMatchesDynamicRule`). Écart mesuré : 1 tuile sur `orksRuntherd`, sens PERMISSIF.
* Le régime MULTI-TUILES : `casterTiles` est le singleton `{GetMainTile(unit)}` ici, et
  `feet_count > 1` rend `True` inconditionnellement en amont.

## 6. Item 2 — les masques du lot HORS POOL

⚠ **« hors pool » n'est pas « npc-only »** : la ventilation des porteurs, re-dérivée du gameconfig,
donne **huit** abilities à porteur SUMMON (confrontables via leur summoner), **une** MoW du pool
(`1144 BioMinefield` / `tyranBiovore`), et **une seule** réellement npc-only (`1010`).

| id | forme du ctor | `rules` | portée |
|---|---|---|---|
| 1010 StormOfFlensingBlades | flags directs | `0x4010` CasterHasNotMoved \| TargetIsEnemy | RANGE_ADJACENT |
| 1015 PrecisionShot | preset `+0x280` \| `0x10` | `0x8014` | RANGE_SELF, self-cast |
| 1044 / 1080 | static-copy `+0x140` | `0x4002` | FROM_CONFIG, `forceMeleeTarget = True` |
| 1053 / 1108 | static-copy `+0x40` | `0x4000` TargetIsEnemy seul | RANGE_ADJACENT |
| 1144 BioMinefield | flags directs | `0x40004020` (dont **AllowNullCasterTile**) | WHOLE_BOARD |
| 1185 ForwardObservers | flags directs | `0x200004002` | FROM_CONFIG, `forceMeleeTarget = True` |

La surcharge est tranchée par les **XREFS ENTRANTES** : `PrecisionShotAbility$$.ctor` figure dans
les appelants de `.ctor(this, template, additionalRules)` et d'aucune autre ; les quatre ctors à
flags directs n'apparaissent ni là ni chez `.ctor(this, template)`. `AllowNullCasterTile` sur 1144
est la signature MoW (une machine n'a aucune tuile), et son porteur EST une MoW du pool.

**`1186 WallOfMirrors` n'est pas dans la table** : sa face COMBAT est portée depuis, donc son
masque vit dans `ABILITY_CLASSES` (contrat de disjonction). Son ctor a tout de même été relu —
`0x6004012` sur `RANGE_WHOLE_BOARD` — et il **concorde champ pour champ** avec ce que le registre
porte : deux lectures indépendantes, même résultat.

## 7. Validation

* **OFFLINE** — `test_…_r1_source_tile_zone_offline.py` : **14 passed**, dont la paire
  discriminante `28` / `1053` (même `TargetingRange`, seul le bit 15 les sépare). Voisins :
  `ability_range_offline`, `whole_board_gates_offline`, `tiles_in_range_order`,
  `line_of_sight_offline`, `friend_gates_offline`, `walkability_offline`,
  `dynamic_target_gate_offline`, `caster_gates_offline`, `adjacency_foyer_offline`,
  `targeting_options_sources`, `ability_registry_ratchet` — **tous verts**.
* **CONTRE-ÉPREUVE** — **9 mutations ciblées, 9 rouges**, chacune vérifiée comme APPLIQUÉE
  (comptage de l'ancre avant substitution ; une ancre absente est rapportée, pas passée sous
  silence) : branche `only_adjacent` → disque, suppression des deux `AddRange`, `range == 0` sans
  le bit, `includeCenter` toujours vrai, anneau → disque, `whole_board` → partiel, masque du
  caster ajouté à l'attaque normale, retrait du masque de `1144`, ré-introduction du doublon `1186`.
* **LIVE** — **75 passed** : `pool_masks_live` 6, `ability_range_live` 6, `only_adjacent_live` 12,
  `caster_gates_live` 13, `walkability_live` 8, `line_of_sight_live` 7, `friend_gates_live` +
  `walkability_offline` 23.
