# case-320 — l'étage `scoring` du mouvement : la TUILE COURANTE manquait au candidate-set

`case-309` a établi que « le natif finit le tour » recouvre **trois** étages et n'en a porté qu'un
(`mirror`). Cette fiche porte le deuxième : **`scoring`** — le port choisissait une **autre tuile**
là où le natif reste sur place. Le troisième (`ability`) reste ouvert.

**État : LIVRÉ.** Le foyer est `engine.ai.action_generators.movement_candidate_positions`.

---

## 1. Ce que le natif fait — chaîne complète, lue de première main (`rnca9r7q6c`)

### 1.1 `positions` est un ARGUMENT du générateur, et il contient la tuile courante

`IdunBattle.AI.ActionGenerators.MovementActionGenerator$$GenerateActions(unit, startPosition,
positions, overrideUtility)` ne fait que ranger ses arguments dans l'itérateur :

```
d__6+0x38 = unit ; +0x20 = startPosition ; +0x40 = positions ; +0x28 = overrideUtility ; +0x30 = this
```

`IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext`
(état 0), en clair :

```
if (UnitPosition.op_Equality(startPosition, null))  yield break;
if (UnitPosition.IsEmpty(startPosition))            yield break;
mainTile = startPosition.MainTile
utility  = overrideUtility ?? new UtilityDefinition(TileExtensions.IsTemporary(mainTile) ? 5 : 6)
closest  = FindClosestEnemy(unit, new UnitPosition(mainTile))          // itérateur, pompé
cases    = new UtilityMovementCase[positions.Count]
foreach (pos in positions)
    cases[i++] = new UtilityMovementCase(unit, pos, closest, null, null, null)
best     = <generator+0x28>.Decide(cases, utility)                     // itérateur, pompé
if (best == null) yield break;
yield return <action de mouvement vers best.MovementTile>
```

Le générateur n'a donc **aucun** candidate-set propre : il évalue exactement ce qu'on lui passe.

`positions` vient de `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles`, qui appelle le
slot `+0xe` de l'`IBattleQuery` = `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` :

```
var pos = EntityExtensions.GetUnitPosition(unit, this._state);
var set = new OrderedSet<UnitPosition>(pos);                                   // la COURANTE, GRAINE
set.UnionWith(this._movementQuery.GetMovablePositionsFor(unit, ignoreUnitFlags, options));
return set;
```

⇒ la position **COURANTE est dans l'ensemble**, et elle en est **le PREMIER élément** ; les tuiles de
`GetMovableTilesFor` (qui, elles, l'excluent — d'où l'union) suivent. `GenerateActionTiles` laisse
ensuite chaque playbook d'ability appliquer son `FilterMovementTiles`, qui ne peut que RESTREINDRE.

### 1.2 Le chooser est `UtilityDecider`, et son argmax est KEEP-FIRST

`<generator+0x28>` est construit par `IdunBattle.AI.ActionGenerators.MovementActionGenerator$$.ctor`
à partir de `(utilitiesDatabase, aiLogger)` : c'est un
`IdunBattleLogic.AI.Utilities.UtilityDecider`. `UtilityDecider$$Decide(cases, definition)` délègue à
`UtilityDecider$$DecideEnumeratoru003Cobjectu003E`, qui boucle sur les `WeightedUtility` de
`definition.Buckets[0]` et, pour chacune, appelle
`UtilityDecider$$CalculateUtilitiesForCasesEnumeratedu003Cobjectu003E`.

**Ici, la définition n'a qu'UNE tranche** : `IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor(int
utilityType)` alloue `new UtilityBucket[1] { new UtilityBucket(utilityType, null) }`, et
`UtilityBucket..ctor` un seul `WeightedUtility(utilityType, weight ?? 1)`. Le mécanisme
d'élimination multi-tranches du `UtilityDecider` (seuil `weighted+0x20`, disqualification
`weighted+0x18`) **n'a donc rien à départager sur ce chemin** — il n'y a pas de second tour.

L'argmax vit dans
`IdunBattleLogic.AI.Utilities.UtilityDecider.u003CCalculateUtilitiesForCasesEnumeratedu003Ed__7u003Cobjectu003E$$MoveNext` :

```
v = utilities[i] + leafResult;   utilities[i] = v;
if (Fix64.op_GreaterThan(v, bestUtility)) { second = best; secondUtility = bestUtility;
                                            best   = case; bestUtility   = v; }
else if (Fix64.op_GreaterThan(v, secondUtility)) { second = case; secondUtility = v; }
```

`op_GreaterThan` est **STRICT** ⇒ **keep-first à égalité**. Combiné au §1.1 :
**à utilité ÉGALE le natif RESTE SUR PLACE**, et il ne bouge que sur un gain STRICT.

### 1.3 …et la conséquence observable

Quand `best` est la tuile courante, l'action porte `Position == currentPosition` :
`IdunBattle.AI.ActionGenerators.InputBuilder$$GenerateInputMessagesFromUnitAction` n'émet alors
**aucun** `MoveUnitMessage` (cf. `case-309` §1.3), et — s'il n'y a pas non plus de cible — la liste
vide devient un `FinishUnitTurnMessage`. C'est exactement la trace qu'on observe : `natif=finish`.

---

## 2. Ce que le port faisait

`engine.ai.action_generators.MovementActionGenerator.generate` passait `ctx.move_tiles` à
`engine.move.best_move_faithful`. `ctx.move_tiles` = RPC `aiMovableTiles` = `GetMovableTilesFor`,
**qui exclut la tuile courante**. Le candidate-set du port était donc amputé de la seule tuile que
le natif évalue en PREMIER : **« rester sur place » n'était pas représentable**, et le générateur
proposait toujours un déplacement réel.

Trois faits rendent le défaut particulièrement peu visible :

* la dégradation est **permissive** — ni erreur ni crash, et `case-309` a montré que
  `engine_validate.run_agreement` n'entre dans sa comparaison que sous
  `if (nat["move"] or nat["ability"])` : un pas `finish` seul y est invisible ;
* **toutes les données étaient déjà là.** Le RPC `pathDistToEnemies` renvoie explicitement la tuile
  courante (« Tuiles atteignables (`GetMovableTilesFor`) + tuile COURANTE ») et `tileMeta` couvre le
  board entier — rien ne manquait, seul l'ensemble candidat était faux ;
* `engine.ai.context.action_tiles_for` **construisait déjà** le bon ensemble (origine en tête) et
  `ctx.action_tiles` le portait : il était consommé par les sweeps de position d'ability, pas par le
  générateur de mouvement.

---

## 3. Ce qui change côté port

| fichier | changement |
|---|---|
| `engine/ai/action_generators.py` | **nouveau** `movement_candidate_positions(ctx)` — mirror de `GenerateActionTiles` / `GetCurrentAndMovablePositionsFor` : `ctx.action_tiles` (origine EN TÊTE), au format `{"col","row"}` |
| `engine/ai/action_generators.py` | `MovementActionGenerator.generate` consomme ce candidate-set au lieu de `ctx.move_tiles` ; le gate devient `not positions` |
| `engine/move.py` | docstring de `best_move_faithful` : `tiles` **EST** le `positions` natif, ORDRE COMPRIS, et l'argmax `u > bu` est le mirror du `op_GreaterThan` strict |

C'est une fonction de MODULE (et non une méthode) pour la même raison que le mirror de `case-309` :
c'est ce qui la rend **neutralisable** depuis un probe, donc la garde falsifiable.

---

## 4. Ce qui est mesuré

`scripts/python/probe_320_movement_scoring_origin.py`. Le montage nommé est le couple *(board,
seed)* ; **les deux bras sont joués sur le MÊME état, au même pas** (`engine_decide` est pur : ses
RPC sont read-only), pas sur « deux runners identiques ».

### 4.1 Les deux montages — et surtout, DEUX RÉGIMES DE DÉPARTAGE OPPOSÉS

C'est ce qui interdit de fitter un scalaire : **la même feuille y prend des valeurs de signe
opposé**, et les deux tombent ensemble avec le seul correctif.

| montage | pas | ORIGINE (natif) | tuile du port NEUTRE | feuille qui DÉPARTAGE |
|---|---|---|---|---|
| `C1_12`/12100 | step 8, `u79` | **(3,6)** `tile=+4` `mindist=-300` → **-296** | (4,5) `tile=-30` `mindist=-300` → -330 | **`TileEffectsUtility`** : `+9` (cover hébergé) contre `-25` (`Thorns_DefenseReduction`) — **MinDist ÉGAL** (pathdist 3 des deux côtés) |
| `C1_12`/909 | step 3, `u93` | **(4,5)** `tile=-30` `mindist=**-200**` → **-230** | (5,5) `tile=+10` `mindist=-300` → -290 | **`MinDistanceToClosestEnemy`** : pathdist **2** contre 3 — ici le terme de TUILE **défavorise** l'origine (`-30` contre `+10`) |

Sur le premier montage, l'origine gagne **par la tuile** ; sur le second, elle gagne **malgré la
tuile**, par la distance. Aucune constante, aucun biais uniforme ne produit les deux.

Le second montage n'est pas choisi à l'intuition : `probe_320 --scan 777,909,4242,31337` sur `C1_12`
l'a désigné — **c'est le seul des quatre à porter un pas discriminant** (777, 4242 et 31337 rendent
le même résultat dans les deux bras, donc ne concluent rien, et sont écartés SUR MESURE).

### 4.2 Chiffres

| montage | pas décidés | natif SUR PLACE (même tuile CÂBLÉ / NEUTRE) | natif BOUGE (CÂBLÉ / NEUTRE) | corrigés | cassés |
|---|---|---|---|---|---|
| `C1_12`/12100 (12 pas) | 12 | 3 → **3 / 2** | 9 → **8 / 8** | 1 (step 8 `u79`) | **0** |
| `C1_12`/909 (14 pas) | 14 | 8 → **7 / 6** | 6 → **6 / 6** | 1 (step 3 `u93`) | **0** |
| `C1_12`/777 (14 pas) | 14 | 2 → 2 / 2 | 12 → 10 / 10 | 0 | 0 |
| `C1_12`/4242 (14 pas) | 14 | 3 → 3 / 3 | 11 → 9 / 9 | 0 | 0 |
| `C1_12`/31337 (14 pas) | 14 | 2 → 0 / 0 | 12 → 11 / 11 | 0 | 0 |

**Aucun pas cassé sur les 5 montages** : le correctif n'échange pas un accord contre un autre.

Les désaccords **résiduels** de la colonne « natif SUR PLACE » sont IDENTIQUES dans les deux bras —
ils relèvent d'un autre étage (le port caste, ou vise une autre tuile d'attaque). Exemple mesuré :
`C1_12`/909 step 6 `u77`, natif `ability` depuis (0,6), port `ability` depuis (0,7) — c'est le sweep
de position d'une ability, pas le générateur de mouvement. `C1_12`/31337 en porte deux.

### 4.3 Non-régression par MUTATION

`probe_320 --noreg --board MC1_67 --seed 12100 --steps 40` rejoue le walk d'agreement de référence
(`engine_validate.run_agreement`) avec le candidate-set CÂBLÉ puis NEUTRALISÉ. **Chiffres
strictement identiques**, et identiques à ceux consignés par `case-309` §4 :

```
pos      AVEC fix={'n': 25, 'exact': 21, 'near': 22} | SANS={'n': 25, 'exact': 21, 'near': 22}
ability  AVEC fix={'n': 22, 'match': 16}             | SANS={'n': 22, 'match': 16}
stay     AVEC fix={'n': 6,  'match': 5}              | SANS={'n': 6,  'match': 5}
```

Ce n'était **pas** l'attendu a priori — contrairement au mirror de `case-309`, ce correctif PEUT
mordre sur le périmètre comparé : il suffirait que le port se mette à préférer la tuile courante sur
un pas où le natif BOUGE pour dégrader `pos`. Le résultat dit qu'il ne le fait sur aucun des 25
déplacements natifs de ce montage — et le probe le re-mesure, il ne le suppose pas.

### 4.4 La garde ROUGIT sous mutation

`tests/engine/test_movement_scoring_origin_live.py` — **7 passed** au code livré ; sous mutation
adversariale (candidate-set ramené à `ctx.move_tiles`), **3 failed / 4 passed**, message VERBATIM :

```
E  AssertionError: montage C1_12/12100 : 1 pas ou le natif ne bouge pas et ou le port propose un
   deplacement REEL -- [{'step': 8, 'uid': 79, 'origin': (3, 6), 'nat_to': (3, 6),
                         'cable_to': (4, 5), 'neutre_to': (4, 5)}]
```

⚠ **Une première version de la garde était VACUOUS sous cette mutation**, et la mutation seule l'a
révélé : le test A y était restreint aux pas `discriminant` (câblé ≠ neutre). Or quand on remet le
candidate-set d'avant, les deux bras redeviennent identiques, `discriminant` est VIDE, et le test
passait au VERT sur un port faux. Il est désormais formulé sur le DÉFAUT lui-même (« le natif ne
bouge pas ET le port propose un déplacement réel »), qui ne dépend pas de la contre-épreuve.

---

## 5. Résidus nommés

- **Étage `ability` — le port caste là où le natif finit le tour.** Inchangé par cette tranche
  (`case-309` §5 : `C1_03`/4242 pas 13, plus deux occurrences sur `MC1_67`/909). Cause en amont de
  la traduction en messages. La garde `test_movement_null_action_live.py` continue de le tenir
  visible.
- **Aucun ennemi ciblable ⇒ le port ne bouge plus du tout.** `MovementActionGenerator.generate`
  garde son court-circuit `not ctx.enemies` → `{"to": None}`, et `best_move_faithful` rend
  `(None, None)` sur `enemy_positions` vide. Le natif, lui, **évalue quand même** : `FindClosestEnemy`
  rend `null`, la feuille `MinDistanceToClosestEnemy` tombe sur son gate 3 (`case.ClosestEnemy ==
  null` → `0`, cf. `#236`) et le composite se réduit à `Tile(7)` — le natif peut donc **se déplacer**
  vers la meilleure tuile. Le port rend `finish`. Écart d'un AUTRE étage (non exercé sur ces
  montages : tous portent des ennemis ciblables), laissé ouvert.
- **`FilterMovementTiles` des playbooks n'est pas porté.** `GenerateActionTiles` laisse chaque
  playbook d'ability restreindre l'ensemble — le seul corps existant,
  `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$FilterMovementTilesForMaxMovement`
  (RunsAround / RunsAway / SaviorProtocols), re-remplit un `OrderedSet` par argmax de longueur de
  chemin, et **peut donc retirer la tuile courante**. Résidu antérieur (déjà nommé par
  `action_tiles_for`), inchangé ici.
- **Le mécanisme multi-tranches du `UtilityDecider` n'est pas porté**, et c'est délibéré : sur ce
  chemin `UtilityDefinition..ctor(int)` ne produit qu'UN `WeightedUtility`, donc ni le seuil
  `weighted+0x20` ni la disqualification `weighted+0x18` n'ont de second tour où mordre. Un
  appelant qui construirait une définition à PLUSIEURS tranches sortirait de ce mirror.
- **`UtilityDefinition(5)` — `UnitMovementFromTemporary`** — n'est pas porté : le générateur natif
  choisit `5` au lieu de `6` quand `TileExtensions.IsTemporary(mainTile)`, c'est-à-dire quand
  l'unité est **déjà** sur une tuile temporaire. Le composite `5` inclut `MaxDistanceToUnitTile(18)`
  (cf. `engine/utilities/move.py`, doc §13.3). Non exercé sur ces montages.
