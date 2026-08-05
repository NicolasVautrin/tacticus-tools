# #270-r1-r1 + #270-r3 — le recenseur ne peut pas rendre zéro sur ce qu'il ne visite pas

**Livré le 2026-08-05.** Tranche **offline pure** — aucun runner, aucune session Frida (les
contrôles live joués le sont en non-régression, pas en confrontation).
Build `rnca9r7q6c` (`data/symbols/CURRENT`). Base : `d6ca045d` (= `origin/master` au lancement).

## 1. Le vrai défaut n'était pas « un rôle manquant » — c'était la LISTE BLANCHE

`probe_270r1_enum_candidates.py` a rendu un zéro rassurant **deux fois**, et la tâche l'attribuait
à deux causes distinctes (un rôle absent, un seuil de cardinalité). Les deux sont réelles. Mais
ajouter `visit_Tuple/List/Set` aurait reconduit le vice : **une liste blanche de rôles ne peut pas
montrer le rôle qu'elle a oublié**. Mesuré en l'ajoutant — deux autres positions manquaient :

```
return 7          # StatType.BLOCK_CHANCE      -> role « valeur de retour », 18 occurrences
_GALVANIC_REPAIR_ID = 1119   # Repair_GalvanicField  -> role « affectation », 165 occurrences
```

Le critère est donc **inversé** : on visite **tous** les `ast.Constant` entiers et le rôle se
**dérive du nœud PARENT**. Une position inconnue n'est plus invisible, elle sort en
`autre (<NoeudParent>)`. La somme des rôles est, par construction, le nombre total de littéraux
entiers du module — le probe l'imprime et l'assertionne à chaque passage.

| | rôles | candidats retenus (`\|n\| > 3`, hors corps d'enum) |
|---|---|---|
| avant | 5 déclarés | **285** |
| après | 15 **dérivés** + fourre-tout nommé | **912** |

Le gisement réel était **3,2×** ce qu'on en voyait. Les rôles neufs, mesurés :
`affectation` 165, `expression` 102, `opérande arithmétique` 37, `branche de conditionnelle` 31,
`valeur de dict` 22, `valeur par défaut` 20, `valeur de retour` 18, `opérande unaire` 16,
`indice` 8.

**Le seuil, lui, est resté réglable — mais il DIT ce qu'il filtre.** `--seuil-dict` vaut désormais
`1` (il ne filtre rien) et, quel que soit son réglage, la sortie imprime `ECARTES PAR CE SEUIL :
N groupe(s), M clé(s) -- NON examines`. Un compte filtré qui ne dit pas ce qu'il filtre est
indistinguable d'une absence de gisement.

## 2. Les deux chiffres annoncés, re-dérivés

* **#270-r3 — CONFIRMÉ à l'unité** : **8 clés / 5 dicts** sous le seuil `>= 3`.
* **#270-r1-r1 — RÉFUTÉ, et par le haut** : la tâche annonçait « 161 littéraux, 31 conteneurs,
  16 fichiers ». Mesure : **201 littéraux non structurels, 71 conteneurs, 32 fichiers**.
  L'écart n'est **pas** dû à l'arbre — re-mesuré sur le commit d'avant #652, c'est **201 / 69 / 32**.
  **Douze variantes de critère** ont été essayées (conteneur homogène ou non × tous éléments non
  structurels ou non × cardinal ≥ 1/2/3) : **aucune ne rend 161 / 31 / 16** ; la plus proche est
  152 / 29 / 15. Le chiffre du backlog n'est donc pas re-dérivable, et c'est le mien qui est écrit
  avec son critère : *tout littéral entier `|n| > 3` placé directement dans un `ast.Tuple`/`List`/
  `Set`, hors corps d'enum*.

## 3. Ce qui a été converti — 160 littéraux, 23 conteneurs + 5 dicts

`element de conteneur` : **201 → 41**. `cle de dict` : **8 → 0**.

Le discriminant est, site par site, le **NOM déjà écrit au site** ou le **TYPE DÉCLARÉ** lu dans
`data/symbols/<build>/frida/methods.tsv`. Jamais la voie, jamais l'ordinal.

| enum | sites | ce qui tranche |
|---|---|---|
| `ActiveAbilityType` | 9 conteneurs (110 ids) + 2 dicts | le nom en commentaire de fin de ligne / dans la prose du site — **110/110** concordants ; `TriggeredAbilityType` et `EffectType` nomment systématiquement autre chose au même ordinal |
| `EffectType` | 5 conteneurs + 2 dicts | le nom du ctor natif cité ligne à ligne (`FireEffect$$.ctor`…) |
| `PathfinderType` | valeurs de `SPECIAL_MOVEMENT_PATHFINDER_TYPES` | le commentaire les nommait déjà (`-> TeleportStrikeWalk / Fly`) |
| `TriggeredAbilityType` | 3 sites | **1482** et **1260** : le nom discrimine, l'ordinal non (1482 est `PrioritisedEfficiency_ExtraMovement` en `EffectType`) |
| `UnitTrait` | `_TRAIT_GATE` | le champ s'appelle `_TRAIT_GATE`, sa docstring dit « Gate trait » |
| `StatType` / `StatPart` | 4 sites | le nom en commentaire ; `StatPart` est un mirror STRICT |
| **`Corner`** | `spawn_tile_shape.DIRECTION_ORDER` | type **DECLARÉ** de `BattleQuery$$GetTilesInTriangleShape` |
| **`Edge`** | valeurs de `_TRIANGLE_SHAPE_DIRECTIONS`, les 2 listes de `DevastatingRefrainAbility$$GetShape` | type **DECLARÉ** du paramètre `direction` d'`AxialCoordinate$$NeighbourAt` |

### `Edge` — LU, pas déduit, et le nom court aurait apparié faux

```
IdunBattle.Utils.Hex.AxialCoordinate.NeighbourAt   direction:IdunBattle.Utils.Hex.Edge
IdunBattle.Utils.Hex.CubeCoordinate.NeighbourAt    edge:IdunBattle.Utils.Hex.Edge
IdunBattle.Utils.Hex.Edge   0=North,1=North_East,2=South_East,3=South,4=South_West,5=North_West
```

Mirror neuf : `scripts/python/engine/hex_edge.py` (6 membres, bijection parfaite), **inscrit au
registre de `probe_313` DANS LE MÊME COMMIT** — registre **14 → 15 mirrors sous garde, 0 dette**.
La clé est le nom **PLEIN** : le build porte un second `Edge` (`UnityEngine.RectTransform.Edge`,
4 valeurs). Même piège que `Corner` (cinq homonymes Unity/SimpleUI).

Troisième source, indépendante et **géométrique** : chaque coin est encadré par ses deux arêtes, et
les six couples du switch natif sont exactement ceux-là — chaque arête apparaît alors **exactement
deux fois**, ce que la garde assertionne (`Counter` == {2}).

⚠ **Le nom DÉSIGNE, il ne décrit pas l'écran.** Dans le repère odd-q de `hexgeo`, `Edge.North`
pointe vers le BAS de la grille (mesure live #90). Les commentaires `-> {N, SE, SW}` de
`sisterhood.py` décrivent l'ÉCRAN, le membre décrit l'ordinal du build : les deux coexistent, et
c'est écrit au site plutôt que laissé se découvrir.

## 4. `StatType` — la décision, NOMMÉE

Son mirror est inscrit `strict=False` au registre de `probe_313` : le port reconventionne les noms
(`CRIT_CHANCE` pour `CriticalChance`). **On convertit quand même**, et ce n'est pas un
contournement :

1. ce que la règle vise est la **péremption silencieuse d'un ordinal**. `strict=False` relâche les
   **NOMS**, jamais les **VALEURS** : `probe_313` confronte les 27 valeurs de `StatType` au build à
   chaque passe. Écrire le membre fait re-dériver l'ordinal d'une table **sous cliquet** ; laisser
   `7` ne protège de rien ;
2. l'écart de nom est **DÉCLARÉ** (docstring du mirror + `raison=` du registre), pas silencieux.

L'alternative — renommer les membres du port en verbatim, la voie retenue pour `KillUnitStep`
(#427) — a un rayon de souffle **mesuré** : **553** références `StatType.<MEMBRE>` dans **169**
fichiers Python suivis. Hors périmètre → résidu **#270-r1-r1-r2**.

## 5. `static_battle_rules.py` — NON CONVERTI, et la garde est DÉPORTÉE

La conversion a été **tentée puis annulée** : `engine/services/` est la couche que `entities/` et
`runner/` importent tous deux. Un `from ..entities.effect_type import EffectType` au niveau module
initialise le paquet `engine.entities`, qui tire `effects/loki/hits.py`, qui ré-importe
`services.static_battle_rules` → `ImportError` sur `TILE_STATUS_EFFECT_NAMES`. **Cycle mesuré**,
pas redouté.

Ce que la règle vise est obtenu autrement, au même cran : le test confronte les **11** valeurs aux
membres d'enum (lui, il peut importer les deux couches). Un renumérotage du build fait rougir
exactement comme si le membre était écrit au site — vérifié par mutation (`0x4dc` → `0x4dd` : ROUGE).

⚠ **La condition de retournement est EXÉCUTABLE, et sa première version était VERTE À TORT.** Elle
importait les deux modules dans un interpréteur neuf en exigeant un échec — mais l'import interdit
n'est pas écrit dans le fichier, donc il n'y avait rien à faire échouer : le test passait déjà sur
`master`. Le critère retenu est la **CAUSE** : `engine.entities` importe-t-il transitivement
`engine.services.static_battle_rules` ? Tant que oui, le compromis tient ; le jour où non, le test
**rougit** et demande la conversion. Résidu **#270-r1-r1-r1**.

## 6. Value-preserving — VÉRIFIÉ, et la méthode a failli mentir

Empreinte `sha256` de chaque structure, prise sur l'arbre de base extrait par `git archive
d6ca045d` puis sur l'arbre converti : **41/41 identiques**.

⚠ **La première passe a rendu 3 divergences, toutes FAUSSES.** L'empreinte hachait `repr(valeur)`,
et `repr(6)` ≠ `repr(<PathfinderType.TeleportStrikeWalk: 6>)` : elle mesurait la REPRÉSENTATION là
où la propriété à tenir est la **VALEUR**. Un `IntEnum` **est** un `int` ; la canonicalisation
correcte est `int(x)`, appliquée **récursivement** dans les conteneurs pour que la discrimination
reste totale. C'est exactement le mode de panne « le contrôle rougit sur son propre artefact » —
et il aurait fait renoncer à trois conversions justes.

## 7. La garde — six étages

`scripts/python/tests/engine/test_270r1r1_container_enum_offline.py` (8 tests, 100 % offline).

| étage | ce qu'il tient |
|---|---|
| 1 CLIQUET | chaque élément / clé est une instance de l'enum LU — rougit si un ordinal nu revient |
| 1b VALEURS | les trois sites où la **valeur** porte un enum, dont deux où il DIFFÈRE de celui de la clé |
| 2 ANTI-DÉPLACEMENT | sur-ensemble pour les sets ; **égalité stricte** pour les tuples (leur ordre EST la donnée) |
| 3 ACCESSEURS PUBLICS | traversée par le chemin réel des appelants, ordinal **et** membre, avec anti-dégénérescence |
| 4 GARDE DÉPORTÉE | `static_battle_rules` + sa condition de retournement exécutable |
| 5 BALAYAGE STATIQUE | tout Python **suivi** : aucun site n'écrit/mute/redéfinit ces structures en ordinaux nus |
| 6 REGISTRE | `Edge` et `Corner` sont au registre de `probe_313`, appariés par leur nom **PLEIN** |

**Un trou trouvé en écrivant l'étage 3, et il est instructif** : l'assertion sur
`get_pathfinder_type_for_unit` comparait le résultat à la valeur **lue dans la table testée**. Un
échange walk/fly serait passé VERT. Un attendu qui se lit dans l'objet testé ne teste rien — les
paires sont désormais figées en ordinaux dans le snapshot.

**18 mutations essayées, 18 détectées** (chacune posée dans le fichier réel, restauration vérifiée
par `git diff --stat`) :

| mutation | verdict |
|---|---|
| **enum FAUX à ordinal JUSTE** — `ActiveAbilityType.ArcScourge` (1173) → `TriggeredAbilityType.MasterOfTheTutelaries_Summon` (1173) | ROUGE (étage 1) |
| **enum FAUX à ordinal JUSTE, axe hexagonal** — `Edge.North_West` (5) → `Corner.SouthEast` (5) | ROUGE (étage 1) |
| **enum FAUX à ordinal JUSTE, clé composite** — `TriggeredAbilityType.LetTheGalaxyBurn` (1482) → `EffectType.PrioritisedEfficiency_ExtraMovement` (1482) | ROUGE (étage 1b) |
| **enum FAUX à ordinal JUSTE, trait** — `UnitTrait.Daemon` (1019) → `TriggeredAbilityType.AutoRevive` (1019) | ROUGE (étage 1) |
| retour à l'ordinal nu (`1173,`) | ROUGE (étage 1) |
| voisin **plausible** — `ArcScourge` → `ArmoriumCherub` (doublon ⇒ entrée perdue) | ROUGE (3 tests) |
| **ORDRE** d'un tuple — les deux premiers effets de mouvement spécial échangés | ROUGE (étage 2) |
| **VALEUR déplacée** — walk/fly échangés pour TeleportStrike | ROUGE (étages 2 et 3) |
| permutation d'arêtes dans `_TRIANGLE_SHAPE_DIRECTIONS` | ROUGE (étage 2) |
| élément retiré (`NOT_ACTIVE_ABILITY_TYPES` perd `Repair_GalvanicField`) | ROUGE (3 tests) |
| clé #270-r3 en ordinal nu (`STAT_CLAMP_MIN`, `CTOR_ARGS`) | ROUGE (étage 1) ×2 |
| clé #270-r3 égarée (`DaemonicOrdnance` → `HadesAutocannons`, doublon) | ROUGE (étage 2) |
| **redéfinition en ordinaux nus dans un fichier TIERS** | ROUGE (étage 5) |
| `Edge` retiré du registre de `probe_313` | ROUGE (étage 6) |
| `TILE_STATUS_EFFECT_TYPES` perd `Contaminated` (`0x4dc` → `0x4dd`) | ROUGE (étage 4) |

## 8. Ce qui RESTE en littéral, et c'est un RÉSULTAT

Les **41** éléments de conteneur non convertis, ventilés — l'étage 1 ne porte volontairement pas
dessus :

* **10** — `static_battle_rules` (§5, garde déportée) ;
* **10** — `damage_config.DAMAGE_FIELDS` : des **offsets de struct** (`0x10`, `0x1c`, …) ;
* **17** — des **pourcentages** `100` (multiplicateur de variables d'ability) et les cinq tiers de
  `NC_PRIORITY_TIERS` ;
* **2** — les **slots d'`IAmountFormula`** de `TRIGGERED_PREDICTION_AVERAGE_FORM` ;
* **1** — `SUPPORTED_FEET_COUNTS` (1/3/7 = un **compte** de tuiles) ;
* **1** — `0x7FFFFFFF` (sentinelle « pas de maximum »).

S'y ajoute `_CUBE_DIRECTIONS` (`geometry.py`), dont les éléments sont des **deltas cubiques** :
c'est son **INDEX** qui est un `Edge`. Écrire `Edge` sur les deltas serait faux — plus faux que
l'ordinal, qui lui ne ment pas.

## 9. Validation

**Offline, 231 tests verts** : la garde neuve (8), les deux volets de #270-r1 (15 au total avec
elle), les trois cliquets d'enum (`mirror`/`ordinal`/`maps`), `333_minmax_avg_rounding`,
`350_prediction_average_forms`, `433_r4_r2_adjacency_foyer`, `433r4r1r4r2_is_adjacent_substrat`,
`448_r1_r1_r1_flying_movement_steps`, `448_r2_teleporting_in`, `448_r2b_stormboyz_teleporting_in`,
`stat_override_refresh`, `statmod_captured_channel`, `433_r3_isadjacent_node`,
`433r4r1r4r2r1r1r1_ramming_speed_adjacence`. Aucun fichier à `0 passed / N skipped`.

**Live, 28 tests verts** en non-régression sur les sites convertis côté runner :
`mow_effect_posers` (8, `SHAPE_DIRECTIONS_*`), `fuelled_by_fury` (5,
`ABILITY_COUNTED_ONCE_PER_BATTLE`), `active_ability_used_gate` (3, `NO_*_ABILITY_TYPES`),
`mv71_sniper_drone` (5), `contagions_lifecycle` (7, `CTOR_ARGS`).

⚠ **Aucune confrontation live, et c'est motivé** : la conversion est value-preserving *par
construction* (§6), donc aucun scénario ne peut faire diverger le comportement avant/après — il n'y
a pas de « scénario où le port change le résultat » à crafter. Ce qui est couvert à la place est
l'**atteignabilité** des sites convertis, offline par l'étage 3 et live par les 28 ci-dessus.

**Cliquets rejoués, tous verts** : `probe_313` (15 mirrors, 0 dette), `probe_181` (104 abilities,
0 masque manquant), `probe_120`, `probe_443r1c` (5 350 indices, 0 périmé), `probe_283`,
`probe_274`, `probe_365`, `probe_468`.

### Un rouge trouvé, et il n'est PAS de cette tranche

`tests/engine/runner/test_448_r2_teleporting_in_live.py::test_the_move_poses_the_moving_marker_then_lands_the_carrier`
échoue (`T4 n'a pas pose 1036 pendant le pas : [1107, 1112]`). **Il préexiste sur `d6ca045d`,
c'est-à-dire sur `origin/master`** : mesuré en re-basculant `scripts/python/engine` sur la version
de base (`git checkout d6ca045d -- scripts/python/engine`) et en re-jouant le même test — **échec
identique, même message**. Les 3 autres tests du fichier passent dans les deux mondes. Ce n'est
donc ni une régression de cette tranche ni un faux positif de harnais : c'est un rouge de `master`,
signalé et non traité ici (hors périmètre).

## 10. Ce qui reste

* **#270-r1-r1-r1** — `static_battle_rules` garde ses ordinaux tant que `engine.entities` importe
  transitivement `services.static_battle_rules`. **Condition de retournement exécutable** : l'étage
  4 rougit le jour où ce n'est plus vrai.
* **#270-r1-r1-r2** — `StatType` sous `strict=False` : renommer ses membres en verbatim du build
  (voie #427) demanderait de toucher **553** références dans **169** fichiers. À peser, pas à faire
  au fil de l'eau.
* **#270-r1-r1-r3** — **les rôles que le recenseur exhaustif vient de faire apparaître**, et que
  personne n'avait comptés : `affectation` **165**, `valeur de retour` **18**, `valeur de dict`
  **22**, `indice` **8**, plus les **189** `argument d'appel` et **49** `comparaison` que les cinq
  rôles d'origine voyaient déjà sans qu'aucun volet ne les convertisse. Deux familles sautent aux
  yeux et sont homogènes : les `_STAT = 8  # StatType.BlockDamage` / `return 7  # StatType
  .BLOCK_CHANCE` (une quinzaine, même décision que §4), et les `EFFECT_<X> = 1193  # 0x4a9`
  (dizaines, `EffectType`). Le chiffre se re-dérive :
  `python scripts/python/probe_270r1_enum_candidates.py --croiser`.
