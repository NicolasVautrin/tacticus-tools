# case-302 — route de decision a cibles TUILE

Chantier ouvert par la tranche 4g de `case-27` (PR #313), qui a re-qualifie le verrou de
`1169 PlagueburstMortar` : ce n'est pas « les MoW ne sont pas modelisees », c'est le **domaine de
cible**. Cette fiche etablit l'INVENTAIRE (RE au decompile `rnca9r7q6c`), pose la premiere tranche
et decoupe explicitement les suivantes.

---

## 1. Ce que le natif fait — la chaine complete, lue au decompile

### 1.1 L'aiguillage TUILE est UN SEUL bit, teste a UN SEUL endroit

`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions(this, caster, casterTiles,
options, range, onlyTiles)` :

```
isTile = onlyTiles ? true : ((options.rules >> 6) & 1)      // bit 6 = TargetingRule.TargetIsTile
...
if (rules & TargetIsCaster)          -> set = { isTile ? casterTiles : caster }
else if (rules & TargetIsMachine)    -> isTile ? OrderedSet VIDE : <toutes les machines>
else if (rules & TargetIsActor)      -> isTile ? GetTilesInRange : GetUnitsInRange U <machines>
else                                 -> isTile ? GetTilesInRange : GetUnitsInRange
...
if (rules & CasterIsPossibleTarget)  -> Add( isTile ? casterTiles : caster )
if (rules & TargetIsCasterOrEnemy)   -> Add( isTile ? casterTiles : caster )
<3 RemoveAll(predicate) : filtres de domaine>
if (rules & TargetIsEnemy || rules & TargetIsCasterOrEnemy)
    -> IntersectWith( GetOnlyTargets(caster) mappe par GetMainTile SI isTile )
```

`isTile` est exactement `IdunBattle.Core.Services.TargetingOptions$$get_IsTileTargeting`
(`rules >> 6 & 1`), deja mirrore cote port par
`engine.runner.abilities.targeting.TargetingOptions.is_tile_targeting`.

⇒ **`IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` est le SEUL enumerateur de cibles
TUILE du jeu.** Il n'y a pas de « chemin tuile » parallele : c'est la MEME fonction
`GetPossibleTargetsForOptions`, la MEME suite de filtres, le MEME conteneur de sortie.

### 1.2 Par quel chemin les tuiles entrent dans la comparaison de decision

```
IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext
  foreach ability, foreach position:  playbook.Evaluate(unit, position, ...)
    -> IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal
       -> IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities(caster, possibleCasterPosition)
          = <ITargetingQuery @this+0x28>.slot 0x42
              = IdunBattle.Core.Services.TargetingQuery$$GetValidTargets(caster, casterTiles,
                                                                         options, ...)
                -> GetInvalidCasterReason  (non-null -> ValidTargets.Empty)
                -> range = GetRange(...)
                -> GetPossibleTargetsForOptions(..., onlyTiles: false)     <-- 1.1
                -> foreach t: GetInvalidTargetReason(t) == null -> targets.Add(t)
                -> ValidTargets(mainTile, targets)
            .AllTargets                                            // ValidTargets +0x10
          -> idun.shared.extensions.ListExtensions$$Remove(
                 list, pred = IdunBattle.AI.Playbook.BasePlaybook$$u003CGetEligibleTargetsEntitiesu003Eb__58_0 )
       -> foreach target in <cette liste> : CalculateActionUtility(caster, position, target, ability)
       -> IdunBattle.AI.Playbook.BasePlaybook$$GenerateAction(position, target, utility)
          -> IdunBattle.AI.ActionGenerators.UnitAction$$.ctor(position, target, abilityType@this+0x10)
```

Deux lectures **decisives** :

- `...BasePlaybook$$u003CGetEligibleTargetsEntitiesu003Eb__58_0` = `!ShouldEvaluateTarget(t)`, et
  `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluateTarget` ne retire que
  `IsUnit(t) && CurrentOwnerIsEnvironment(t)` ou `UnitExtensions.IsIrrelevantObject(t)`.
  **Une entite-TUILE n'est jamais retiree** — le natif la score comme n'importe quelle cible.
- `UnitAction..ctor(position, target, abilityType)` prend `target` en **`IEntity` NON TYPEE**.
  Le format d'action natif ne distingue pas tuile et unite.

⇒ **Cote natif, il n'existe ni enumeration separee, ni format d'action separe.** Ce qui manquait au
port n'est donc PAS « un format d'action a etendre » (il porte deja un entity-id generique), mais
**un enumerateur qui ne jette pas les cibles `kind == "tile"`**.

---

## 2. Le contrat de `abilityTargets` pour `kind = "tile"`

`frida/hooks/features/ai-step/rpc-targeting.ts::mapTargets` lit **exactement** `ValidTargets +0x10`
(= `AllTargets`, le meme ensemble que `GetEligibleTargetsEntities`) et, par element :

```ts
const info = entById.get(p.ptr.toString());
if (info && (info.ty === EntityType.Unit || info.ty === EntityType.Machine))
    out.push({ kind: "unit", targetId: info.id, visualId, pos });
else
    out.push({ kind: "tile", tile: { col: p.col, row: p.row } });     // <-- PAS de targetId
```

| question | reponse MESUREE (lecture du hook + du natif) |
|---|---|
| que vaut l'`id` rendu ? | **il n'y en a pas** — la branche tuile n'emet que `tile:{col,row}` |
| est-ce une entite-tuile reelle ? | **OUI** — c'est un pointeur d'entite de `AllTargets` ; `forEachEntity` l'indexe bien (`EntityType.Tile` existe et est utilise par `readEffectsByTile`), le hook choisit de ne pas remonter son id |
| porte-t-elle une position ? | **OUI**, `{col,row}` via `extractTilePtrs` |

**La correspondance `id d'entite-tuile <-> (col,row)` n'a donc PAS a etre construite : elle existe
deja** — `engine.ai.context._board_tile_ids` (RPC `boardGraph`) expose `ctx.tile_id_by_pos`, et
c'est **le meme id qu'`applyOneAction` attend comme cible** (`findTileEntityId`). Il est deja
exerce en production par quatre routes tuile :
`engine/playbook/noncomparable/dark_talon_strike.py` (1092),
`.../master_of_the_tutelaries.py` (1096), `.../the_quickening.py` (1151),
`engine/playbook/excruciating_frequencies.py` (1197).

> **Consequence de perimetre** : aucune modification de `frida/hooks/**` n'est necessaire, donc
> aucun rebuild ni reinject. Faire emettre `targetId` sur `kind:"tile"` serait cosmetique.

---

## 3. Ou le format d'action doit changer : NULLE PART

Le format porte par le port est `{"kind": "ability", "target": <entityId>, "ability": <id>,
"to": (col,row)|None, "util": <float>}`. `target` y est deja un **entity-id generique**.

Call-sites qui construisent ce dict (compte re-derive, pas estime) :

| fichier | ligne | producteur |
|---|---|---|
| `engine/ai/action_generators.py` | 169 | `NonComparableGenerator.generate` |
| `engine/ai/action_generators.py` | 733 | `ComparableAbilityGenerator.generate` (bucket) |

Producteurs de CANDIDATS `{target, ability, to, pred, full}` consommes par le bucket : `_best_attack`,
`_heal_candidates`, `_repair_candidates`, `_repair_galvanic_candidates`, `_bespoke_candidates`,
`nonattack_candidates`, `excruciating_frequencies_candidates` — **7 routes, dont 1 deja tuile**.

⇒ La piece (2) annoncee par `case-27` (« etendre le format d'action pour porter une tuile ») est
**deja acquise**. Ce qui reste est la piece (1) : l'ENUMERATION.

---

## 4. Les abilities concernees — balayage du bit `TargetIsTile`

Re-derive du registre par `python scripts/python/probe_302_tile_target_route.py --inventory` :
**19 abilities sur les 97 de `ABILITY_CLASSES` portent le bit** `TargetIsTile` dans leur
`TARGETING_OPTIONS.rules`, et **3 seulement** avaient une route de decision avant cette fiche
(1092 DarkTalonStrike, 1096 MasterOfTheTutelaries, 1151 TheQuickening — toutes NonComparable
bespoke). Les 16 autres : 1017, 1018, 1026, 1112, 1116, 1142, 1145, **1148**, 1158, 1159, 1166,
**1169**, 1188, 1201, 1213, 1219.

Le detail (id, masque, route existante) est produit par le probe, qui est la source a citer — ces
chiffres se periment des qu'une ability entre au registre (95 -> 97 pendant la redaction).

**Ce que ce balayage NE couvre PAS, et il faut le dire** : `ABILITY_CLASSES` compte 97 entrees sur
les 257 valeurs d'`ActiveAbilityType`. Le bit n'a donc ete lu que sur les abilities **deja portees**
(chacune au decompile de son `.ctor`, par les tranches qui les ont fait entrer). La population
complete demanderait de lire les 160 `.ctor` restants — hors perimetre de ce chantier, et pose en
tranche 4 (§7).

> ⚠ **`1197 ExcruciatingFrequencies` n'est PAS dans cette liste** alors que sa cible de decision EST
> une tuile : son ciblage passe par `TargetTiles@0x190` (l'aim d'une ligne), pas par le bit
> `TargetIsTile`. Le bit repond a « le domaine de `GetValidTargets` est-il fait de tuiles ? », pas a
> « la cible de l'action est-elle une tuile ? ». D'ou sa route BESPOKE
> (`excruciating_frequencies.py`, qui balaie positions x aims) plutot que cette route generique.

---

## 5. Le verrou « le natif ne genere pas l'action » est REFUTE — c'etait un COOLDOWN

`probe_27_4g_plagueburst_route.py` concluait : `aiDryRunAllUnits` propose 69 sur 8/8 tirages et
**jamais** 1169, en regime pourtant maximalement favorable — donc « le natif ne genere pas
d'action pour 1169 depuis une unite de decision normale ».

**Cette conclusion etait un artefact du montage**, et l'etage qui la defait n'avait pas ete mesure :

| etage | mesure (`probe_302_tile_target_route.py --stage`, runner 468) |
|---|---|
| 1169 dans le kit vu par `unitAbilityTypes` | **OUI** (`kind = active`) |
| `usable` (`ActiveAbility.CanStillBeUsed`) | **True** |
| **`cooldown` (`RemainingCooldownTurns`)** | **1 — l'ability est INDISPONIBLE ce tour-la** |
| `abilityTargets` SANS `abilityType` (kit reel) | 1169 enumeree, 58 cibles, 100 % `tile` |
| `(col,row) -> tileEntityId` via `boardGraph` | **58 / 58 resolues** |

Le probe 4g lisait son etage 1 via `abilityTargets` **avec** `abilityType` explicite, ce qui passe
par la branche `manualAbility` de `rpc-targeting.ts` et court-circuite `unitAbilityTypes` : les 58
tuiles prouvaient que `GetValidTargets` produit un domaine, pas que l'ability fut castable.

**Une fois le cooldown purge (deux fins de tour, positions inchangees), le natif propose :**

```
MoveUnitMessage      to = (2,3)
ActiveAbilityMessage abilityType = 1169, targetId = 43        # 43 = tuile (3,4), PAS une unite
```

**6/6 tirages.** Le natif genere donc parfaitement l'action a cible TUILE — et `43` est bien un
`tileEntityId` du `boardGraph` (les unites du montage sont 77/79/81/83/85). Il y a un ORACLE.

> Lecon generalisable : **un `cooldown` initial non purge se lit exactement comme un refus de
> decision.** Toute mesure « le natif ne propose jamais X » doit d'abord asserter
> `RemainingCooldownTurns in (None, 0)` — c'est ce que fait desormais
> `test_plagueburst_mortar_decision_live.py::test_cooldown_is_purged_before_measuring`.

---

## 6. Tranche 1 — LIVREE : la route + `1169 PlagueburstMortar`

### Ce qui a change

| fichier | changement |
|---|---|
| `engine/playbook/nonattack.py` | `NonAttackComparablePlaybook.targets_tiles` (mirror de `get_IsTileTargeting`) + `eligible_targets` choisit le domaine TUILE ou UNITE au lieu de filtrer `kind == "unit"` |
| `engine/playbook/tile_targets.py` | **nouveau** — `dsl_context_for_tile_target(ctx)` : le `SelectorContext` de la face DECISION pour un playbook tile-target |
| `engine/playbook/plagueburst_mortar.py` | **nouveau** — `PlagueburstMortarPlaybook`, custom mirror 1:1 |
| `engine/runner/abilities/deathguard.py` | `plagueburst_adjacent_enemies(target_sel)` — `GetAdjacentEnemies`, a cote de son jumeau COMBAT |
| `engine/playbook/__init__.py` | enregistrement |

**Le domaine est EXCLUSIF, pas cumulatif** : `GetPossibleTargetsForOptions` appelle `GetTilesInRange`
**ou** `GetUnitsInRange`, jamais les deux — un ensemble de cibles natif est homogene. Concatener les
deux domaines aurait ete une permissivite inventee.

### Ce qui est mesure (`probe_302_tile_target_route.py --decision`, runner 523)

| | valeur |
|---|---|
| natif | `(1169, 43)` |
| moteur | `(1169, 43)`, `to = (2,3)` — **meme tuile de tir que le `MoveUnitMessage` natif** |
| bras `zero` (custom force a 0) | `(69, 77)` — le terme est **necessaire** |
| bras `noroute` (registre non-attaque vide) | `(69, 77)` — la route est **necessaire** |
| `_best_attack` | rend `69` — la porte plan-driven ne peut pas produire 1169 |
| domaine eligible | 60 tuiles ; **domaine UNITE force (= code d'avant) : `[]`** |
| custom par cible | valeurs distinctes `{0.0, 10.0, 20.0}` — lineaire en `n`, ni booleen ni constant |

Garde : `scripts/python/tests/engine/test_plagueburst_mortar_decision_live.py` (**10 tests**), avec
un bras TEMOIN (sans `--hp-target` gonfle) ou le natif NE caste PAS 1169 — sans lui, un port qui
casterait 1169 systematiquement passerait quand meme.

### Ce que la tranche 1 NE porte PAS (residu nomme)

Le terme de PREDICTION de 1169 reste a `0`.
`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$MakeDamagePredictions` =
`GenerateMultiHitAttackPredictions(..., mainTarget = PlagueburstMortarAbility$$GetMainDamageTarget,
GetDamage(abilityState), GetHits(), Nullable(GetDamageProfile()))`, et `GetMainDamageTarget` =
`Filter(Enemies(caster, target@0x178, 3), GetIsValidAdjacentEnemyTrigger)`. Ce predicat est FAUX
partout sur un board frais (ni aura `ContagionsOfNurgle_ArmorReduction1`, ni modificateur d'armure
negatif), donc la somme des predictions vaut **reellement** 0 et le port est **exact dans le regime
de l'oracle**. Hors de ce regime il SOUS-ESTIME — voir tranche 2.

---

## 7. Tranches suivantes (dispatchables telles quelles)

### Tranche 2 — le terme de PREDICTION de 1169 (et le patron pour tous les tile-target a degat)

Porter `PlagueburstMortarPlaybook$$MakeDamagePredictions`. Tout est deja au depot :
`deathguard.plagueburst_is_valid_adjacent_enemy_trigger` (les DEUX branches, depuis case-224) et
`engine.playbook.prediction.make_damage_predictions`. Ce qui manque est l'evaluation du predicat
dans le contexte de DECISION (`ctx.scene` au lieu d'un `State`) et le branchement per-cible.
**Montage discriminant** : un ennemi porteur d'un modificateur d'armure negatif adjacent a la tuile
visee — le natif ajoute alors un terme que le port actuel ignore.

### Tranche 3 — `1148 DaemonicOrdnance` (2e membre, meme route)

Masque `0x46000040` (bit 6 pose). Le custom est deja RE (`case-27` §4g) : `10 x |ennemis sur
GetTargetAreaTiles|`, ou `10` est une CONSTANTE `Fix64(0xa)` EN DUR (aucun `GetUtilityValue`).
Reste a porter l'evaluateur DSL `TilesOnSameElevation(TilesInTriangleShape(...))`. Porteur
`blackForgefiend` = MoW -> **greffer l'ability** sur une unite du pool (le playbook se charge par
ABILITY), exactement comme la tranche 1 l'a fait pour 1169. **Purger le cooldown avant de mesurer.**

### Tranche 4 — balayage EXHAUSTIF du bit `TargetIsTile`

`probe_302 --inventory` ne lit le bit que sur les **95** abilities de `ABILITY_CLASSES`, sur **257**
`ActiveAbilityType`. Lire les `.ctor` restants au decompile (attention aux deux pieges mesures :
overload PRESET+flags, et copie d'un champ statique de `TargetingOptions` ecrit par son `.cctor`).
Livrable : la liste complete, et pour chacune si sa face DECISION a une route.

### Tranche 5 (outillage, exige un reinject — a grouper avec un autre besoin de reinject)

Deux angles morts du harnais, tous deux dans `frida/hooks/features/ai-step/` :

1. `rpc-targeting.ts::mapTargets` n'emet pas d'`id` sur `kind == "tile"` alors que `forEachEntity`
   l'indexe (`EntityType.Tile`). Le port s'en passe par `boardGraph`, donc c'est **confort**, pas
   blocage.
2. `rpc-predict.ts::pairUtility` ne resout `targetId` que sur `EntityType.Unit` — **il n'existe donc
   aucun oracle PAR ETAGE pour une cible tuile**. C'est ce qui a oblige la tranche 1 a valider par
   la decision COMPLETE (`aiDryRunAllUnits`) plutot que paire par paire. C'est le point d'ancrage a
   ouvrir en priorite pour les tranches 2 et 3.
