# #270-r1 volet 2 — les 128 clés que le build n'attribue PAS à un enum unique

**Livré le 2026-08-05.** Les **dix** dicts d'`engine/` dont les clés entières résolvent dans
plusieurs enums du build voient ces clés remplacées par le membre nommé. Le lot est **fermé** :
`probe_270r1_enum_candidates.py --croiser` rend désormais `dicts a >= 3 cles entieres : 0`.

Tranche **offline pure** — aucun runner, aucune session Frida.
Build `rnca9r7q6c` (`data/symbols/CURRENT`).

## 1. Le gisement, re-dérivé

| clés | table | enum LU |
|---|---|---|
| 44 | `runner/abilities/targeting.TARGETING_OPTIONS_UNPORTED` | `ActiveAbilityType` |
| 22 | `playbook/noncomparable/_base.NATIVE_PRIORITY` | `ActiveAbilityType` |
| 13 | `playbook/prediction/abilities._MAKE_DMG_INPUT_OVERRIDES` | `ActiveAbilityType` |
| 12 | `services/ability_caster_gates.DYNAMIC_CASTER_GATE_BY_ABILITY` | `ActiveAbilityType` |
| 9 | `playbook/prediction/abilities._PLAYBOOK_PROFILE_OVERRIDE` | `ActiveAbilityType` |
| 7 | `entities/abilities/active_ability._PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` | `ActiveAbilityType` |
| 3 | `playbook/prediction/abilities._MAKE_DMG_EXTRA_EVENTS` | `ActiveAbilityType` |
| 6 | `battle_query._TRIANGLE_EVEN_COL` | **`Corner`** |
| 6 | `battle_query._TRIANGLE_ODD_COL` | **`Corner`** |
| 6 | `entities/selectors/geometry._TRIANGLE_SHAPE_DIRECTIONS` | **`Corner`** |

La ventilation annoncée par la tâche était juste à deux détails près, tous deux re-mesurés :
`ability_caster_gates` est en `:411` (pas `:400`), et `active_ability.py:170` (7 clés) n'y était
pas listé.

## 2. Les 110 ids d'ability — le **NOM** tranche, l'ordinal ne tranche rien

Chaque entrée de ces sept tables porte déjà, en commentaire, le **symbole natif** dont elle est
transcrite (`GetEmRuntzAbility`, `BreathOfSilencePlaybook`, `HellfireShellsPlaybook$$MakeDamagePredictions`…).
Confronté à `data/symbols/rnca9r7q6c/frida/enums.tsv`, ce nom **matche 110/110** le membre
d'`ActiveAbilityType` à cet ordinal, tandis que `TriggeredAbilityType` et `EffectType` y nomment
systématiquement autre chose :

| ordinal | `ActiveAbilityType` | `TriggeredAbilityType` | `EffectType` |
|---|---|---|---|
| 1216 | `MartialExemplar` | `BlessingsOfKhorne` | `PsychicStalk_VisualEffect` |
| 1045 | `GetEmRuntz` | `MartialApotheosis` | — |
| 1070 | `BreathOfSilence` | `CondemnorStake` | `ExplosiveMaladies_ExtraRangedAttack` |

C'est la mesure de #270-c transposée : `TriggeredAbilityType` partage **458** ordinaux avec
`EffectType` (dont **454** nomment autre chose) et **233** avec `ActiveAbilityType` (dont **231**).
Un ordinal qui « résout » ne prouve donc à peu près rien ; le nom, lui, discrimine.

## 3. Les 18 clés de TRIANGLE — la tâche annonçait des scalaires, la mesure dit l'inverse

L'hypothèse de travail était « un rang, une distance, un compte — hors règle ». **Elle est
réfutée**, par une lecture et non par un raisonnement :

```
IdunBattle.Core.Services.BattleQuery.GetTilesInTriangleShape
    startTile:IdunBattle.Core.IEntity, direction:IdunBattleLogic.Utils.Hex.Corner
IdunBattle.Utils.Hex.AxialCoordinate.NeighbourAt
    direction:IdunBattle.Utils.Hex.Edge
```

`IdunBattleLogic.Utils.Hex.Corner` = `0=NorthWest,1=NorthEast,2=West,3=East,4=SouthWest,5=SouthEast`.

**Trois sources concordantes et indépendantes** :

1. le **type déclaré** du paramètre, lu dans `frida/methods.tsv` ;
2. le **nom de l'argument** du nœud DSL amont —
   `IdunBattleLogic.Entities.DSLSelectors$$TilesInTriangleShape(start, cornerDirection)` ;
3. la **géométrie** : chaque coin est encadré par deux arêtes, et le couple d'`Edge` que le port
   lit dans le switch natif est exactement celui-là, coin par coin —
   `NorthWest → (North_West, North)`, `NorthEast → (North, North_East)`,
   `West → (North_West, South_West)`, `East → (North_East, South_East)`,
   `SouthWest → (South_West, South)`, `SouthEast → (South_East, South)`.
   Aucun autre appariement des six valeurs ne produirait ces couples.

Le **décompilé** confirme la forme de `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape` :
garde `if (5 < direction) goto <retour du centre seul>`, **six** `case`, deux branches sur la parité
de la colonne (`col & 0x80000001`), et les six couples de deltas de la branche PAIRE sont
**identiques** à `_TRIANGLE_EVEN_COL`, dans l'ordre du switch.

⚠ **Le nom DÉSIGNE, il ne décrit pas l'écran.** Les tables de deltas du port travaillent dans le
repère offset odd-q de `hexgeo`, dont l'axe des lignes est inversé par rapport au libellé natif
(`Edge` 0 s'y lit `S`, mesure live #90). `Corner.NorthWest` porte donc des deltas qui pointent vers
le bas de la grille du port. C'est écrit dans la docstring du mirror plutôt que laissé se découvrir.

## 4. Le mirror `Corner` est NEUF, et il devait entrer au registre

`scripts/python/engine/hex_corner.py` — 6 membres, bijection parfaite.
Sans inscription au registre de `probe_313`, il en sort **ORPHELIN** (constaté : le probe a rougi
avant l'inscription, `APPARIEES=12 HORS-MIRROR=2 ORPHELINES=1`). La clé d'appariement est le **nom
plein** : cinq autres enums du build s'appellent `Corner` (`UnityEngine.U2D`, `UnityEngine.UI`, les
trois `SimpleUI.Layouts`), tous à 3 ou 4 valeurs — le nom court aurait apparié faux.

Registre : **12 → 13 mirrors sous garde**, 0 dette.

## 5. Value-preserving — vérifié, pas déclaré

Empreinte `sha256` de la relation `int(clé) -> repr(valeur)` de chaque dict (adresses hexa des
`repr` instables gommées), prise **avant** puis **après** la conversion, et re-prise après les
remaniements de style :

```
targeting.TARGETING_OPTIONS_UNPORTED                      44 cles  47d1aae2a713de29
ability_caster_gates.DYNAMIC_CASTER_GATE_BY_ABILITY       12 cles  517b73473af7cffb
noncomparable._base.NATIVE_PRIORITY                       22 cles  fa1f2985d44d3d4f
prediction.abilities._MAKE_DMG_INPUT_OVERRIDES            13 cles  79cb2af4311af4e2
prediction.abilities._PLAYBOOK_PROFILE_OVERRIDE            9 cles  e43f6550436cdb17
prediction.abilities._MAKE_DMG_EXTRA_EVENTS                3 cles  2f9dd250d9ac28eb
active_ability._PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE       7 cles  e43173cf23acac73
battle_query._TRIANGLE_EVEN_COL                            6 cles  1d18482f7075c045
battle_query._TRIANGLE_ODD_COL                             6 cles  d37e2e9fcdb879aa
selectors.geometry._TRIANGLE_SHAPE_DIRECTIONS              6 cles  4940d90cf52e9073
```

**10/10 identiques, 128/128 clés.** C'est le contrôle qui attrape le mode de panne propre à une
conversion de masse : le bon nom en face de la mauvaise valeur.

## 6. Les sites de MUTATION — hors de portée de l'empreinte, et deux d'entre eux hors de portée du grep

L'empreinte hache le dict, pas ses lecteurs. Un site qui **écrit** dans ces tables est donc invisible
d'elle. Or la distinction suivante est load-bearing, et elle est attestée par la garde :

* affectation sur une clé **déjà présente** → CPython **CONSERVE** la clé d'origine ;
* `pop` puis réinsertion → la clé est **REMPLACÉE** par ce qu'on passe.

Un ordinal nu dans la seconde forme laisse la table avec une clé non typée après restauration —
et le cliquet rougirait alors **selon l'ordre des tests**, l'échec intermittent qu'on ne diagnostique
jamais. Six sites passent au membre :
`tests/engine/test_savage_echoes_prediction_live`, `tests/engine/test_433_r4_r2_r1_r2_ability_range_offline`,
`probe_216_savage_prediction`, `probe_305_massdriver_splash`, `probe_351_facade_event_count`,
`probe_352_grenade_prediction_base` (+ `probe_27_r5_r1_plague_wind_prediction`, dont les deux
constantes perdent leur `int(...)`).

**Deux de ces sites — `probe_305` et `test_433` — n'ont PAS été trouvés par grep** (qui cherchait
`.pop`/`.update`/`.setdefault`) mais par le **balayage statique** de l'étage 5, sur la forme
`TABLE[X] = ...`. C'est la justification de cet étage, mesurée.

## 7. La garde — cinq étages, et le cinquième existe parce que les quatre premiers ne suffisaient pas

`scripts/python/tests/engine/test_270r1_volet2_dict_keys_enum_offline.py` (7 tests, 100 % offline).

| étage | ce qu'il tient |
|---|---|
| 1 CLIQUET | chaque clé est une instance de l'enum LU — rougit si un ordinal nu revient |
| 2 ANTI-DÉPLACEMENT | les 128 couples (ordinal, valeur), même valeur, même ordre relatif. Sur-ensemble **ordonné**, pas égalité : une entrée ajoutée passe sans re-figer 128 couples |
| 3 ACCESSEURS PUBLICS | les tables traversées par le chemin réel des appelants, ordinal **et** membre, avec anti-dégénérescence |
| 4 RÉINSERTION | la propriété CPython du §6, figée plutôt que supposée |
| 5 BALAYAGE STATIQUE | tout Python **suivi** : aucun site n'écrit/`pop` une clé de ces tables par un ordinal nu |

**L'étage 5 a été écrit APRÈS une mutation restée verte.** Rendre à `probe_216` sa constante
`ABILITY = 1230` laissait les quatre premiers étages verts : ils lisent les dicts après import, et un
probe que la passe ne joue pas ne les touche jamais. C'est mot pour mot le mode de défaillance de
#455-r3 — *le runtime ne voit que ce qu'une passe JOUE*.

**Sept mutations essayées, sept détectées** (chacune posée dans le fichier réel, restauration
vérifiée par `git status`) :

| mutation | verdict |
|---|---|
| déplacement — 1216 reçoit le membre de 1217 (doublon, entrée perdue) | ROUGE (4 tests) |
| voisin **plausible** — `NovaBoost` 1192 → `NovaShield` 1194 | ROUGE (4) |
| permutation de coins — `NorthWest` → `West` dans `_TRIANGLE_EVEN_COL` | ROUGE (4) |
| coin fantôme — `East` reçoit le couple de `West` dans `_TRIANGLE_SHAPE_DIRECTIONS` | ROUGE (3) |
| retour à l'ordinal nu — `1045:` | ROUGE (étage 1) |
| **enum FAUX à ordinal JUSTE** — `TriggeredAbilityType.ItsGonnaBlow` (1080) | ROUGE (étage 1) |
| réinsertion en ordinal nu dans un probe | ROUGE (étage 5) — **verte** avant l'étage 5 |

## 8. Validation

**Offline, 247 tests verts, 0 échec**, aucun fichier à `0 passed / N skipped` :
`270r1` (volet 1 **et** volet 2), `nc_priority_tiers`, `350_prediction_average_forms`,
`353_ramming_speed_prediction`, `433_r4_r2_r1_r2_ability_range`, `433_r4_r2_r1_r1_c_caster_gates`,
`433_r4_r2_r1_r1_dynamic_target_gate`, `365_selector_montage`, `383_ramming_speed_explosion`,
`344_ability_damage_average`, `333_minmax_avg_rounding`, `339_moyennes_residuelles`,
`350r3b_triggered_average_forms`, `433_r4_r2_adjacency_foyer`, `433r4r1r4r2_is_adjacent_substrat`,
`runner/targeting_options_sources`, `runner/targeting_rule_inventory`, `270d_catalog_traits_enum`,
`366_effects_registry_partition`.

**Le rebase a rapporté une prise, et elle n'est pas de cette tranche.** Rebasée sur `origin/master`
(20 commits d'écart, 0 conflit), la batterie a été **entièrement re-jouée** — 247 tests, les 7
mutations, l'empreinte. Un seul rouge, et il **préexistait sur `origin/master`** :
`engine/entities/damage_reason.py` (mirror natif d'`IdunBattle.Operations.DamageReason`, livré par
`c06a112f`, PR #651) était entré sous `engine/` **sans passer au registre de `probe_313`**, qui
rougissait donc sur `master`. C'est le gisement même que son étape 1 existe pour fermer, et sa
**troisième** réouverture par notre propre cadence après `PathfinderType` (#381-r5) et
`KillUnitStep` (#389-r2). Inscrit ici — 2 lignes, clé LUE dans `enums.tsv` (`IdunBattle.Operations`,
pas `IdunBattle.Entities.Enum`) — parce que cette tranche modifie ce cliquet et ne peut pas le
livrer rouge. Registre : **14** mirrors sous garde, 0 dette.

**Cliquets rejoués, tous verts** : `probe_313` (14 mirrors, 0 dette), `probe_181` (104 abilities,
0 masque manquant), `probe_120` (étape 0 : littéral de ctor manquant — aucun), `probe_443r1c`
(5 267 indices littéraux, 0 périmé), `probe_274`, `probe_283` (`exec` / `prose` / `tables`),
`probe_365`, `probe_462r5`.

⚠ **Aucun contrôle live, et c'est un choix motivé** : la conversion est value-preserving *par
construction*, donc aucun scénario ne peut faire diverger le comportement avant/après — il n'y a pas
de « scénario où le port change le résultat » à crafter. Ce qui est couvert à la place est
l'**atteignabilité** des 128 clés par le chemin des appelants (étage 3). Budget live saturé
(`liveRunners` ~5 pour un plafond de 4) : aucune nécessité démontrée n'aurait justifié d'y toucher.

## 9. Ce qui reste

* **`#270-r3` — le SEUIL du probe cache un gisement.** `probe_270r1_enum_candidates.py` ne rapporte
  que les dicts à **≥ 3 clés entières**. Sous ce seuil, **8 clés / 5 dicts** restent en ordinaux nus,
  et le rôle « clé de dict » du probe les montre pourtant (c'est ainsi qu'ils ont été trouvés) :

  | clés | dict | enum probable, à LIRE |
  |---|---|---|
  | 2 | `playbook/prediction/abilities._MAKE_DMG_TARGET_GATE` (1148, 1147) | `ActiveAbilityType` |
  | 2 | `entities/effects/loki/status.py:154-155` (`0x42F`, `0x430`) | à lire |
  | 1 | `entities/abilities/active_ability._PREDICTION_FORMULA_ON_TRIGGERED_ABILITY` (1160) | `ActiveAbilityType` — sa **valeur** porte un `TriggeredAbilityType` (1260) |
  | 2 | `entities/stats.STAT_CLAMP_MAX` (7, 9) | `StatType` — ⚠ mirror `strict=False`, noms reconventionnés (`CRIT_CHANCE`) |
  | 1 | `entities/stats.STAT_CLAMP_MIN` (17) | `StatType`, idem |

  `_MAKE_DMG_TARGET_GATE` est **adjacent** à `_MAKE_DMG_INPUT_OVERRIDES`, converti par ce volet :
  le diff est visiblement hétérogène, et c'est assumé — le lot livré est celui qui a été **recensé**.
  Le volet à faire a deux parties : abaisser le seuil du probe (le recensement doit être complet par
  construction), puis lire les 5 sites. Le cas `StatType` demande une décision à part : son mirror
  est sous garde `strict=False`, donc écrire `StatType.CRIT_CHANCE` nomme *le port*, pas le build.

* **`#270-r1-r1`** — les littéraux en position **élément de conteneur**, inchangé. Il touche
  directement ce volet : les **valeurs** de `_TRIANGLE_SHAPE_DIRECTIONS` sont des ordinaux
  d'`IdunBattle.Utils.Hex.Edge`, et le tuple `_CUBE_DIRECTIONS` en est indexé. `Edge` n'a
  volontairement **pas** de mirror ici : aucun de ses porteurs n'est une CLÉ.

* **Non re-mesurés** : `scripts/sql/006` et `013` (résidu #270-b), les audits générés
  (`kit-coverage.md`, `combat-ability-coverage.md`) — cette tranche ne porte aucune ability, elle ne
  peut pas les faire bouger.
