# case-302 — route de decision a cibles TUILE

Chantier ouvert par la tranche 4g de `case-27` (PR #313), qui a re-qualifie le verrou de
`1169 PlagueburstMortar` : ce n'est pas « les MoW ne sont pas modelisees », c'est le **domaine de
cible**. Cette fiche etablit l'INVENTAIRE (RE au decompile `rnca9r7q6c`), pose la premiere tranche
et decoupe explicitement les suivantes.

**Etat : tranches 1 (§6), 2, 3 (§8), 4 et 5 LIVREES.** Le chantier est CLOS cote decision (§7).
La tranche 2 a sa fiche propre : **`case-302-2-prediction-tile-target.md`** — elle porte le terme de
PREDICTION de 1169 et degage le **patron valable pour tout tile-target a degat**.

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

> ### ⚠ Ce que le bit `TargetIsTile` dit, et ce qu'il NE dit PAS
>
> Le bit repond a **« le DOMAINE de `GetValidTargets` est-il fait de tuiles ? »**, PAS a
> **« la cible de l'action est-elle une tuile ? »**. Les deux questions ne coincident pas, et les
> confondre fait rater des abilities dans les deux sens :
>
> - **`1197 ExcruciatingFrequencies` cible une TUILE par un chemin qui n'est PAS le domaine.** Son
>   aim passe par `TargetTiles@0x190` (la ligne de tir) — d'ou sa route BESPOKE
>   (`engine/playbook/excruciating_frequencies.py`, qui balaie positions x aims) plutot que la route
>   generique de cette fiche.
>   ⚠ **RECTIFICATIF (tranche 4)** : cette ligne affirmait aussi « sans porter le bit », et c'est
>   FAUX — `...Loki.ExcruciatingFrequenciesAbility$$.ctor` passe `rules = 0x20000000042`, bit 6
>   POSE. Elle etait absente du balayage du §4 parce que ce balayage ne lisait que `ABILITY_CLASSES`,
>   ou 1197 ne figure pas. Voir `case-302-4-population-cible-tuile.md` §6.
> - Reciproquement, une ability qui porte le bit voit son ensemble eligible bascule ENTIEREMENT en
>   domaine tuile — c'est ce qui rendait `eligible_targets` VIDE (et la route inerte) tant que le
>   port filtrait `kind == "unit"`.
>
> Le balayage du §4 repond a la premiere question. La seconde n'a pas d'inventaire, et n'est pas
> derivable d'un masque.

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

**Ce que ce balayage NE couvrait PAS** : `ABILITY_CLASSES` compte 97 entrees sur les **257** du
registre natif. Le bit n'y etait lu que sur les abilities **deja portees**. La population complete
est desormais MESUREE — **41 abilities, dont 22 hors `ABILITY_CLASSES`** — par la tranche 4 :
**`case-302-4-population-cible-tuile.md`**. Les 19 ci-dessus s'y retrouvent **a l'identique**, ce qui
valide croisement l'inventaire manuel et le balayage automatique.

> ⚠ **`1197 ExcruciatingFrequencies` n'etait pas dans cette liste, et la raison ecrite ici etait
> FAUSSE.** Ce n'est pas qu'elle « ne porte pas le bit » — elle le porte
> (`...Loki.ExcruciatingFrequenciesAbility$$.ctor` passe `rules = 0x20000000042`, bit 6 pose). Elle
> etait absente parce qu'elle n'est pas dans `ABILITY_CLASSES`, le seul ensemble que ce balayage
> lisait. Reste vrai : son ciblage EFFECTIF passe par `TargetTiles@0x190` (l'aim d'une ligne), d'ou
> sa route BESPOKE (`excruciating_frequencies.py`) plutot que cette route generique. Detail :
> `case-302-4-population-cible-tuile.md` §6.

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

### Ce que la tranche 1 NE portait PAS — RESORBE par la tranche 2

> Section conservee telle qu'elle etait ecrite : le terme de PREDICTION est desormais PORTE
> (`case-302-2-prediction-tile-target.md`). Le diagnostic ci-dessous reste juste sur le REGIME
> (`0` exact sur un board frais), et c'est exactement ce que garde le bras TEMOIN de la tranche 2.

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

### Tranche 2 — LIVREE : le terme de PREDICTION de 1169 + le patron tile-target a degat

Fiche propre : **`case-302-2-prediction-tile-target.md`**. Trois corrections a ce que cette section
annoncait, toutes MESUREES :

- le batch de prediction ne couvre **que l'occupant de la tuile VISEE** (`GetMainDamageTarget`), pas
  les ennemis ADJACENTS — ceux-la ne comptent QUE par le terme custom ;
- ce qui manquait n'etait pas seulement « l'evaluation du predicat » : `dsl_context_for_tile_target`
  ne fournissait **ni `has_negative_modifier` ni `is_in_team_aura`**, donc les deux branches du
  predicat rendaient `False` d'office ;
- le montage discriminant retenu passe par la branche **AURA** (`ContagionsOfNurgle`), pas par la
  branche armure : `--hp-target` met `Armor`/`FixedArmor` a **0**, ce qui rend la branche armure
  inatteignable dans ce regime.

### Tranche 3 — LIVREE : `1148 DaemonicOrdnance` (2e membre, meme route)

Voir **§8** — le port, et surtout l'etage que la tranche a fait apparaitre
(`IsPositionMachineForCurrentPlayer` lisait la mauvaise chose).

### Tranche 4 — LIVREE : balayage EXHAUSTIF du bit `TargetIsTile`

Fiche propre : **`case-302-4-population-cible-tuile.md`** ; probe
`scripts/python/probe_302_4_tile_target_population.py` ; tables `docs/rl/case-302-4/`.

`probe_302 --inventory` ne lisait le bit que sur `ABILITY_CLASSES` — un sous-ensemble. La tranche 4
le lit sur **toute** la population enregistree par le jeu, `.ctor` par `.ctor`, avec les quatre
formes de `TargetingOptions..ctor` (litteral / preset+flags / preset seul / copie d'un statique) et
un tri-etat explicite pour ce qui n'est pas lisible. Deux corrections a ce que cette section
annoncait :

- le denominateur n'est PAS « les membres d'`ActiveAbilityType` » mais **les entrees du registre**
  `IdunBattle.Core.Services.AbilitiesDatabase$$InitializeActiveAbilities` — `...$$GetActive` rend
  `new NoneAbility()` pour toute valeur absente de ce dictionnaire ;
- les pieges sont **quatre**, pas deux : s'ajoutent l'overload PRESET SEUL, et surtout le fait que
  le champ lu par `GetValidTargets` est `AActiveAbility+0x70`, PAS le second jeu d'options
  `+0xb0` (`TargetingOptionsForContinue`), qu'un slot virtuel peut surcharger.

### Tranche 5 — LIVREE : le canal etait DEJA publie, il manquait le FIL

> ⚠ **Le verrou annonce par cette section etait FAUX** (mesure du 2026-08-06), sur le meme patron
> que `#27-r8`. Elle affirmait « exige un reinject » en nommant un champ **a ajouter**
> (`boardGraph.spawnGroups`) — alors qu'un **autre champ du MEME RPC**, livre par `#311` dans le
> **meme commit hooks** (`de7879b2`) et deploye par le **meme reinject**, publiait deja la reponse,
> et **mieux**. Le port, lui, appelait deja `boardGraph` et jetait tout sauf `tiles`. Zero reinject,
> zero RPC supplementaire. **Un verrou doit nommer le canal que le CONSOMMATEUR lit, et se verifier
> dans le bundle INJECTE avant d'etre ecrit.**

Trois points, dont un seul demande encore une fenetre :

1. **`rpc-targeting.ts::mapTargets` n'emet pas d'`id` sur `kind == "tile"`** alors que
   `forEachEntity` l'indexe (`EntityType.Tile`). Le port s'en passe par `boardGraph`, donc c'est
   **confort**, pas blocage. **Code ECRIT et COMPILE** (bundle `rc 0` ; `tsc -p tsconfig.hooks.json`
   : 0 erreur sur ce fichier), en attente de la prochaine fenetre de reinject. L'id est emis
   **accompagne de `targetEntityType`** : publier l'id nu ferait passer pour une tuile toute entite
   tombee dans la branche par defaut — le canal se decrit lui-meme, comme `pairUtility` (#302-t5).
2. ~~`rpc-predict.ts::pairUtility` ne resout `targetId` que sur `EntityType.Unit`~~ — **CLOS, et
   cette ligne etait PERIMEE des la tranche 2.** Le commit hooks `#302-t5` resout la cible sur TOUS
   les `EntityType` et publie `targetEntityType` : `pairUtility(caster, <tileEntityId>, ability)`
   EST l'oracle PAR ETAGE de `ComparablePlaybook$$CalculateUtilityFromPredictions` sur une cible
   tuile. MESURE (`probe_302_2 --stage`) : `ok: true, targetEntityType: 0`, et la valeur rendue est
   identique a 1e-12 selon qu'on passe la TUILE ou l'UNITE qui l'occupe. La tranche 2 valide donc
   par etage ET par la decision complete. ⚠ La ligne restait ecrite ici alors que le correctif
   etait deja au depot : **verifier le hook AVANT de conclure « pas d'oracle »**.
3. ~~**AUCUN RPC n'expose la config de spawn D'UN RUNNER**~~ — **CLOS, et l'enonce visait le
   MAUVAIS CHAMP.** `boardGraph` publie `mowPositions: [{playerId, teamId, machineOfWarPosition}]`
   depuis `#311`. Ce champ est **strictement meilleur** que le `spawnGroups` reclame ici : au lieu
   des groupes BRUTS — que le port devrait re-traverser par un mirror de `GroupForPlayer` — il porte
   le retour de `IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer(player)`
   **INVOQUE**, donc la valeur EFFECTIVE, repli natif compris. Et il est **plus fidele que notre
   mirror** : le natif lit `playerNr` de `IdunBattle.Entities.StateExtensions$$GetTeam(state)`
   (`local_res10 >> 0x20` au decompile) la ou `machine_of_war_position_for_player` le **devine a 0**.

   **Ce que la tranche a livre** (Python pur, `engine/ai/context.py`) :
   - `_board_graph` cache la **REPONSE** de `boardGraph` et non ses seules `tiles` — le champ
     voyageait deja dans cet objet et etait jete a la ligne suivante, d'ou **0 RPC** de plus ;
   - `_board_mow_positions` -> `{playerId: MachineOfWarPosition}`, **tri-etat preserve** du hook
     (`None` = pas mesure, `{}` = mesure et vide). Une entree en ERREUR est **ECARTEE**, jamais
     rabattue sur `0` — `0` est une valeur **LEGITIME** (`MachineOfWarPosition.None_`), portee par
     la majorite des plateaux ;
   - `_machine_of_war_position` gagne un **cran 0** : le natif invoque passe devant le mirror de la
     BC, qui reste le seul canal du chemin **OFFLINE** (`build_from_state`, sans RPC).

   **Le gain, chiffre sur le consommateur final** (`probe_302_3 --decision`, board `MC1_67`) : le
   bras `nogroups` (canal BC coupe, c.-a-d. le regime de **tout** appelant qui ne connait pas la BC
   — `engine_validate`, la collecte RL, le self-play) visait la tuile **53** quand le natif vise
   **52**. Apres la tranche : **52**. C'est exactement l'erreur que §8.2 avait diagnostiquee, et
   elle survivait pour tous les appelants qui ne passaient pas `spawn_groups` a la main.

   **Le cran de repli `decisionView.mows` est structurellement MUET la ou le natif diverge** :
   un groupe qui declare `MachineOfWarPosition.None_` ne deploie **aucune** MoW, donc `mows` y est
   **vide** (mesure sur `C1_01`). Il ne pouvait donc jamais couvrir les plateaux discriminants.

   **Le denominateur, et pourquoi « 502 » et « 552 » ne se contredisent PAS.** `data/boards` porte
   **779 fichiers** pour **675 ids** distincts. Signature `(mow_team1, mow_team2)` du set ACTIF :
   **552 ids** portent `(0, 0)` (DISCRIMINANTE) et **173** portent `(2, 1)` (== repli) — mais
   `552 + 173 = 725 > 675`, parce que **50 ids portent une declaration DIFFERENTE selon le pool ou
   ils sont dumpes**. `552 - 50 = 502` = les ids qui portent `(0, 0)` **exclusivement**, le chiffre
   ecrit dans `engine/services/machine_of_war_position.py`. Les deux comptes sont justes ; ils ne
   repondent pas a la meme question, et `probe_302_5 --boards` imprime desormais les trois.
   ⚠ Consequence pratique : pour ces 50 ids, **`--board <id>` ne suffit pas** a fixer la
   `MachineOfWarPosition` — le `--board-pool` la change (ex. `C1_02`, `C1_21`, `C1_25`).

   Probe : `probe_302_5_mow_position_channel.py` (`--canal/--cascade/--d311/--boards`, `rc 0`) ;
   garde : `tests/engine/test_302_5_mow_position_offline.py` (18 tests, etage **MUTANTS** — 5/5 des
   mutations du vrai code la font rougir, `a_mordu` mesure et non suppose).

---

## 8. Tranche 3 — LIVREE : `1148 DaemonicOrdnance`

### 8.1 Le custom, mirror 1:1

`IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$CalculateCustomUtility` :

```
sel = DaemonicOrdnanceAbility.GetTargetAreaTiles();            // arbre DSL
ent = AbilityEntities(owner: caster, caster: null, target: target);
x   = Fix64(0);
foreach (tileEntity in TargetsSelector.<slot 10>(sel, ent))    // Select, PAS Count
    if (UnitExtensions.GetUnit(tileEntity, state) is u && UnitExtensions.IsEnemy(u, caster, state))
        x += Fix64(0xa);
return x;
```

Trois contrastes avec 1169, tous lus au decompile :

| | 1169 PlagueburstMortar | 1148 DaemonicOrdnance |
|---|---|---|
| poids | `GetUtilityValue("PlagueburstMortar_AdjacentEnemy")` | **`Fix64(0xa)` EN DUR** — aucun `GetUtilityValue`, aucune cle `BC.Utilities` |
| agregation | `TargetsSelector.Count` (slot 2) | boucle IMPERATIVE sur `Select` (slot 10) — pas de dedoublonnage par unite |
| slot `caster` de l'`AbilityEntities` | `caster` | **null** (sans effet : l'arbre ne lit que `target@0x178`) |

Port : `scripts/python/engine/playbook/daemonic_ordnance.py` (+ `tile_targets.unit_on_tile`, mirror
de `UnitExtensions$$GetUnit` restreint au domaine tuile).

### 8.2 L'etage que la tranche a fait apparaitre — et qui etait FAUX au depot

`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetTargetAreaTiles` =
`TilesOnSameElevation(target, TilesInTriangleShape(target, If(IsPositionMachineForCurrentPlayer(2),
1, 4)), 1)`. La **direction du triangle** decide de la zone, donc du comptage, donc de la cible.

`IdunBattle.Entities.Triggers.IsPositionMachineForPlayerTrigger$$ShouldTrigger` compare
`IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer(<joueur COURANT>)` a son
litteral. Et cette fonction **n'interroge AUCUNE machine deployee** :

```
teamIndex = player.GetComponent<TeamComponent>().<+0x24>
grp = spawnPointSet@+0x78.GroupForPlayer(teamIndex, playerNr)      // TWPI : team1/p0 -> 0, team2/p0 -> 1
if (grp != null) return grp.MachineOfWarPosition@+0x14             // propriete du PLATEAU
return teamIndex == 1 ? 2 : (teamIndex == 2 ? 1 : 0)               // fallback SANS groupe
```

Le port lisait `MachineComponent.Position` de la MoW deployee (`entities_from_state`, et la
docstring de `entities/triggers.py` l'affirmait) : un **proxy** exact quand la machine existe, et
« inconnu » sinon — alors que le natif repond toujours. Consequence mesuree : sur `MC1_67`
(`SpawnPointSetIndex 1`, groupes `[(0 -> 2), (1 -> 1)]`) et **sans aucune MoW**, le natif prend
`dir = 1` la ou le port prenait `dir = 4`, et visait **une autre tuile** (53 au lieu de 52).

Le fallback natif n'est pas un defaut acceptable : balayage des **675 boards** du depot (sur le
`spawnPointsSet` paire de chaque dump) — **502 declarent `(0, 0)`**, **173 declarent `(2, 1)`**.
L'appliquer sans avoir lu le groupe serait faux sur ~74 % des plateaux. Le port ne devine donc pas :
`AiDecisionContext.machine_of_war_position` cascade **groupes lus** -> **slot d'une MoW deployee**
(proxy exact quand il repond, et c'est le regime REEL de 1148 : son porteur EST une MoW) ->
**`None` = non mesure**.

Mirror de la cascade : `scripts/python/engine/services/machine_of_war_position.py`
(`GroupForPlayer` + `GetPositionMachineForPlayer`, fallback natif inclus).

### 8.3 Ce qui est mesure (`probe_302_3_daemonic_ordnance.py`)

Montage : greffe de 1148 sur `deathTyphus`, cluster TRIANGLE `(A, A+S, A+SE)` = `(4,4) (4,5) (5,5)`,
caster en `(2,4)`, cooldown initial purge.

| bras | plateau | `MachineOfWarPosition` | natif | moteur | custom max |
|---|---|---|---|---|---|
| favorable (`--hp-target 400000`) | `MC1_67` | **2** (groupe) | `(1148, 52)` | `(1148, 52)` | **30** (triangle `{S,SE}` : les 3 ennemis) |
| TEMOIN (`--hp-target 1`) | `MC1_67` | 2 | `(69, 77)` | `(69, 77)` | 30 |
| FLIP (`--flip`) | `C1_03` (groupes `(0,0)`) | **0** | `(1148, 53)` | `(1148, 53)` | **20** (triangle `{NW,N}`) |

Bras de necessite, tous mesures sur le bras favorable :

| bras | resultat | ce qu'il exclut |
|---|---|---|
| `nogroups` (canal `SpawnPointGroups` coupe) | `(1148, **53**)` | l'accord ne vient pas d'un « VRAI par hasard » : sans la lecture du groupe le moteur vise une AUTRE tuile |
| `zero` (custom force a 0) | `(69, 77)` | le terme custom est NECESSAIRE |
| `noroute` (registre non-attaque vide) | `(69, 77)` | la route est NECESSAIRE |
| domaine UNITE force | `[]` | l'enumeration tuile est NECESSAIRE |
| `_best_attack` | rend `69` | la porte plan-driven ne peut pas produire 1148 |

Garde : `scripts/python/tests/engine/test_daemonic_ordnance_decision_live.py` (**13 tests**), dont
le bras TEMOIN, le bras FLIP et le bras `nogroups` (le ROUGE conserve).

### 8.4 Ce que la tranche 3 NE porte PAS (residus nommes)

- **Le terme de PREDICTION de 1148 reste a `0`**, et ici c'est STRUCTUREL, pas un regime :
  `...DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle `GenerateMultiHitAttackPredictions`
  sur `DaemonicOrdnanceAbility$$GetAllDamageableTargets` = `Enemies(caster, Units(Filter(
  GetTargetAreaTiles(), HasEffect(Tiles(Subject@0x180), 5 = Fire)), 1), 3)` — **les ennemis sur une
  tuile DEJA EN FEU**, or c'est ce meme cast qui pose le feu, en DERNIER etage de son
  `ExecuteBehaviour`. Sur une zone qui ne brule pas, l'ensemble est VIDE et la somme vaut REELLEMENT
  0 : le port est exact partout ou la zone visee ne porte pas `Fire`. Des qu'elle le porte, il
  SOUS-ESTIME. Montage discriminant (protocole `case-172`) : caster une premiere fois pour allumer,
  puis re-scorer un tir sur la meme zone avec un ennemi encore dessus. Garde de non-regression
  silencieuse : `test_prediction_term_is_zero_because_the_area_is_not_burning`.
- **La face COMBAT garde le proxy** (`entities_from_state` lit `MachineComponent.Position`). La
  corriger demande de porter les `SpawnPointGroups` jusqu'au `State` — non fait, non valide ici. Les
  consommateurs concernes sont `1142 MacroPlasmaIncinerator` et `DevastatingRefrain`.
- **`unit_on_tile` resout l'occupant par la MAIN tile.** Le natif passe par `TileContentComponent`,
  rempli pour CHAQUE pied d'une unite multi-tuiles ; une unite dont seul un pied SECONDAIRE tombe
  dans la zone serait comptee par le natif et pas par le port. Les heros du pool sont mono-tuile et
  les MoW n'ont pas de ligne dans `dv.units` — non exerce, donc non mesure.
- **La branche `playerNr != 0` de `GroupForPlayer`** (TWPI 2/3/5) n'est pas exercee : tous nos
  runners declarent un seul joueur par equipe. Le port la transcrit, elle n'est pas confrontee.
