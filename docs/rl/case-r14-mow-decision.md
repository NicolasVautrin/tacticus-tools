# Case R14 — face DÉCISION des MACHINES OF WAR (`DefaultMachineTactic`)

**Statut** : LIVRÉ. Confronté live `gqfc5mff6c`, session Frida 4, boards `C1_02` / `C1_25` / `C1_38`.
Correctif **100 % Python** (`scripts/python/**`) — aucun changement `frida/hooks`, aucun rebuild,
aucun reinject.

---

## 1. Le critère, et la réponse

> **Une ability de MoW est-elle PROPOSABLE par le port, et la proposition coïncide-t-elle avec ce
> que le natif décide pour ce même caster Machine ?**

- **PROPOSABLE : OUI.** `engine_decide` route désormais un caster `EntityType.Machine` vers le
  chemin natif dédié. Sweep des **8 MoW du pool** (`probe_r14_mow_decision.py --sweep`) : 8/8
  routées, **0 violation** des invariants du chemin (aucune proposition de mouvement, aucune ability
  refusée par `CanCurrentlyBeUsed` proposée, caster natif == la Machine).
- **COÏNCIDENCE : OUI, mesurée** sur `ThriceBlessedConflagration` (1187, `adeptExorcist`) — la
  **seule** des 16 abilities MoW dont la face DÉCISION est portée : le moteur complet rend la MÊME
  ability sur la MÊME cible que `aiStepDryRun`, sur 3 boards
  (`test_thrice_blessed_decision_live.py`, 4 tests verts).

Avant ce correctif, `engine_decide` n'avait **aucune entrée** pour un `casterId` de Machine : la
feuille NonComparable de 1187 était du code juste, atteint par personne.

---

## 2. RE — le chemin natif, de bout en bout

### 2.1 Reachability : l'IA native JOUE la MoW

`IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$CalculateNextActionForPlayer` :

```
playerComponent = player.GetComponent<PlayerComponent>()
entities        = GetEntitiesFromIds(playerComponent.CurrentlyOwnedUnitIds)
if (playerComponent+0x78 != 0)                       # id de la MACHINE du joueur
    entities.Add(state.GetEntity(playerComponent+0x78))
-> vtable+0x1a8 (CalculateNextActionForUnitGroup)
```

`PlayerComponent+0x78` est écrit par `IdunBattle.Operations.AddMachineOperation$$Execute`
(`*(playerComp + 0x74) = machine.Id ; *(playerComp + 0x78) = machine.Id`). La MoW entre donc dans
le groupe d'entités jouables du joueur, au même titre qu'une unité.

`DefaultGroupOperator.<CalculateNextActionForUnitGroup>d__6$$MoveNext` :
`PickNextUnit` → gate `!IsDead` → `baseUnitComponent+0x60 += 1` → `aiQuery.GetUnitTacticForUnit(u)`
→ `tactic.CalculateNextActionForUnit(u)`.

`IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit` — **l'ordre des branches est le routage** :

| test | tactic (slot d'`AiQuery`) |
|---|---|
| `UnitExtensions$$IsSteppable` | `SkipTurnAiUnitTactic` (+0x28) |
| `UnitExtensions$$IsUseless` | `SkipTurnAiUnitTactic` (+0x28) |
| **`EntityExtensions$$IsMachine`** | **`DefaultMachineTactic` (+0x30)** |
| `UnitExtensions$$IsBoss` | `LokiBossAiUnitTactic` (+0x18) |
| `UnitExtensions$$IsNonAttacking` | `OnlyMoveAiUnitTactic` (+0x20) |
| sinon | `DefaultAiUnitTactic` (+0x10) |

Le gate d'entrée dans le groupe est `AnAiGroupOperator$$GetValidUnits` :
`HasActionLeft(u) && !IsDead(u) && baseUnitComponent+0x60 < 0x3e9`.
`UnitExtensions$$HasActionLeft` accepte **`EntityType.Unit` (1) ET `EntityType.Machine` (6)** et vaut
`!UnitFlagsComponent.Has(4)`.

**Mesure live** (runner MoW `adeptExorcist`, board `C1_02`) : après `finish` des deux alliés
réguliers, `decisionView` affiche « units à activer : `[53]` » (la MoW seule, le tour ne bascule pas)
et `aiStepDryRun` rend `ActiveAbilityMessage{casterId: 53, targetId: 14, abilityType: 1188}`,
`mutated: false`.

### 2.2 `DefaultMachineTactic` — trois différences STRUCTURELLES avec le tactic unité

`IdunBattle.AI.Tactics.DefaultMachineTactic$$.ctor` :

```
ABaseAiActorTactic..ctor(...)
this+0x48 = <query> ; this+0x50 = <...>
InitAbilityTypeLists(this, 0)
this+0x60 = GetDefaultActiveAbilityActionGenerators(this, 0)      # <- DIRECTEMENT
```

à comparer à `DefaultAiUnitTactic$$.ctor`, qui construit en plus un `MovementActionGenerator`
(`this+0x58`), crée une `List`, y `AddRange` les générateurs d'ability **puis `Add`** le
générateur de mouvement.

`ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators` rend exactement **6**
`ActiveAbilityActionGenerator` : les tiers NonComparable `dict[1000]`, `dict[100]`, `dict[0]`,
`dict[-100]` (`0xffffff9c`), `dict[-1000]` (`0xfffffc18`), puis l'OrderedSet `special` (Comparable,
`this+0x38`).

1. **Pas de générateur de mouvement.** Corollaire lu :
   `DefaultMachineTactic.<CalculateMovementForUnit>d__8$$MoveNext` renvoie une `List` VIDE, toujours
   — **une MoW ne bouge jamais**.
2. **Position nulle + tuiles vides.**
   `DefaultMachineTactic.<CalculateNextActionForUnit>d__5$$MoveNext` appelle, par générateur :
   `gen.GenerateActions(machine, IdunBattle.Core.UnitPosition$$NullPosition(), new OrderedSet())`.
   Le tactic unité, lui, passe `EntityExtensions$$GetUnitPosition(unit)` et
   `ABaseAiUnitTactic$$GenerateActionTiles(unit)` — et gate d'abord sur `UnitExtensions$$IsAlive`,
   ce que le tactic Machine ne fait pas. (`UnitPosition$$NullPosition` construit une `List` vide :
   un `UnitPosition` EST une liste de tuiles — c'est le substrat multi-hex.)
3. **Émission dédiée.** `DefaultMachineTactic$$GenerateInputMessagesFromUnitAction` (et non
   `InputBuilder$$GenerateInputMessagesFromUnitAction`) : `ActiveAbilityMessage` si
   `action.Ability != null` (`+0x10` = id du caster, `+0x18` = `action.AbilityType`), sinon — et si
   le flag `param_4` est faux — le message de FIN d'activation. **Jamais de `MoveUnitMessage`.**

### 2.3 Côté générateur : la branche `positions.Count == 0`

`IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.<GenerateActions>d__7$$MoveNext` énumère
la collection de positions candidates (`+0x30`). Quand elle est VIDE — exactement le cas MoW — il
tombe dans la branche de repli :

```
if (positions.Count == 0 && playbook.<slot 2>())
    bucket.Merge( playbook.GenerateActions(unit, UnitPosition.NullPosition(), <unitPosition>) )
```

UNE seule évaluation, depuis la position nulle, **sans** le gate `HasValidTargets` (slot `0x3f`) que
la branche par-tuile applique. Le même motif existe dans
`RandomAbilityActionGenerator.<GenerateActions>d__5$$MoveNext`.

Filtres par ability, en amont (identiques au chemin unité) : `UnitExtensions$$HasFlag(unit, 2)` →
abandon ; `GetUnitAbilitiesInOrder(this, activeAbilityComponent)` ;
`UnitExtensions$$IsAbilityBlocked` ; **`ActiveAbility$$get_CanCurrentlyBeUsed`** ;
`this.abilityTypes.Contains(...)` ; `PlaybookDatabase$$LoadPlaybook` ; `ShouldEvaluate` slots 4 et 5.

### 2.4 Le gate `CanCurrentlyBeUsed` — le terme MUNITIONS

`IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed` :

```
CanStillBeUsed(@0x28) && !IsDisabled(@0x35)
  && (!RemainingCooldownTurns(@0x2c).HasValue || Value < 1)
  && (!AmmoCost(@0x38).HasValue           || HasEnoughAmmo(@0x40))
```

Le port ne lisait que le **premier** terme (le canal live le nomme `usable`) : il était strictement
plus permissif que le natif sur le cooldown **et** les munitions.

**Mesure live — les 8 MoW du pool, seed BC par défaut (`MachineOfWarAmmo = 0`)** : chacune a
exactement UNE ability « primaire » à `munitionsCost = 1`, et toutes les 8 sont
`hasAmmo = False` **alors que `usable = True`** :

| MoW | ability à munitions | l'autre |
|---|---|---|
| adeptExorcist | 1187 ThriceBlessedConflagration | 1188 DevastatingRefrain |
| astraOrdnanceBattery | 1142 MalleusRocketLauncher | 1143 ForwardSpotter (`cd=1`) |
| blackForgefiend | 1147 HadesAutocannons | 1148 DaemonicOrdnance |
| deathCrawler | 1168 EntropyCannons | 1169 PlagueburstMortar |
| orksRukkatrukk | 1200 SquigLaunchas | 1201 SquigMine |
| tauBroadside | 1160 HeavyRailRifle | 1161 TwinSmartMissileSystem |
| tyranBiovore | 1144 BioMinefield (`cd=1`) | 1145 SporeMineLauncher |
| ultraDreadnought | 1158 DutyEternal (`cd=1`) | 1159 MacroPlasmaIncinerator |

Sans ce terme, le port proposerait 1187 là où le natif caste 1188 (mesuré : `probe_r14_mow_decision`
sur un runner sans munitions → natif `1188`, port silencieux sur 1187).

**Impact sur les unités RÉGULIÈRES, mesuré** (10 tours, runner seed 777 / `MC1_67`) : sur **120**
entrées d'ability actives, **1** est refusée par le gate — `darkaTerminator PlasmaCannon (1150)`,
`usable=True, cooldown=1`. Le terme munitions ne mord jamais sur une unité (`ammoCost` y est `null`).

---

## 3. Le port

| Fichier | Ce qui change |
|---|---|
| `engine/ai/tactic.py` | **`DefaultMachineTactic`** — 5 tiers NonComparable + fallback Comparable, **sans** `MovementActionGenerator` ; aucune action ⇒ `{"kind": "finish"}` (mirror de `GenerateInputMessagesFromUnitAction(action=null)`). |
| `engine/ai/context.py` | **`machine_row(dv, uid)`** (discriminant `IsMachine` : présence dans `decisionView.mows`) et **`build_machine(...)`** — `origin=None`, `move_tiles=[]`, `reach_nc=[]`, `plans={}`, `normal_ids=set()`, **aucun appel `pathDistToEnemies`** (champ propre au générateur de mouvement). `ctrl` recalculé par rapport au camp de la MACHINE. |
| `engine/battle_query.py` | **`can_currently_be_used(ability)`** — mirror de `ActiveAbility$$get_CanCurrentlyBeUsed` sur le canal `decisionView`. Appliqué dans `build` (unités) ET `build_machine`. |
| `engine/runner/components.py` | `ActiveAbility` porte `ammo_cost` (`AmmoCost`@0x38) et `has_ammo` (`HasEnoughAmmo`@0x40) + la méthode `can_currently_be_used()`. |
| `engine/runner/snapshot.py` | `_active_abilities` lit `ammoCost`/`hasAmmo` ; **`_load_machines` pose l'`ActiveAbilitiesComponent`** de la MoW (composant MESURÉ présent sur l'entité Machine, peuplé par `AddMachineOperation$$InitializeAbilitiesStatus`). |
| `engine_validate.py` | `engine_decide` **route par type d'acteur** (mirror `AiQuery$$GetUnitTacticForUnit`) : Machine → `build_machine` + `DefaultMachineTactic`. |
| `engine/ai/state_bridge.py` | Documentation : l'exclusion des MoW de `_dv_units`/`_obs_units` est **fidèle** (canal `.mows` séparé + chemin de décision dédié), pas le résidu — et le résidu OFFLINE restant y est nommé (§5). |

**Ce qui n'a PAS été fait, délibérément** : aucune origine inventée pour la MoW, aucune ligne
Machine glissée dans `dv.units` — c'est le piège qui aurait produit des propositions plausibles et
fausses tout en contaminant le raisonnement positionnel des vraies unités.

---

## 4. Validation

### 4.1 Coïncidence par-ability — `test_thrice_blessed_decision_live.py` (4 tests, verts)

Le test confronte désormais le **moteur complet** (`engine_decide`), plus la feuille isolée :

- **[A]** sur un état où le natif CASTE 1187 : `kind == "ability"`, même ability, **même cible**
  (celle de l'argmax, en queue de `fromHere` — un port keep-first échouerait), `to is None`
  (absence de générateur de mouvement), `util == beam_count`, et `nat["caster"] == machineId`.
- **[B]** × 2 boards (`C1_38`/4242, `C1_25`/777) : les quirks de géométrie restent gardés — la même
  feuille remise à la géométrie de `DarkTalonStrike` rend une décision DIFFÉRENTE du natif.
- **[C]** (nouveau) **gate munitions** : même montage à `MachineOfWarAmmo = 0` ; l'état est vérifié
  discriminant (`ammoCost>0, hasAmmo=False, usable=True`), le natif ne caste pas 1187 et le moteur
  ne le propose pas.

### 4.2 Généralisation — sweep des 8 MoW (`probe_r14_mow_decision.py --sweep --ammo 5`)

```
adeptExorcist          OK caster=53 legales=[1187,1188] natif=1188 port=finish to=None
astraOrdnanceBattery   OK caster=53 legales=[1142]      natif=1142 port=finish to=None
blackForgefiend        OK caster=53 legales=[1147,1148] natif=1148 port=finish to=None
deathCrawler           OK caster=53 legales=[1168,1169] natif=1169 port=finish to=None
orksRukkatrukk         OK caster=53 legales=[1200,1201] natif=1201 port=finish to=None
tauBroadside           OK caster=53 legales=[1160,1161] natif=1160 port=finish to=None
tyranBiovore           OK caster=53 legales=[1145]      natif=1145 port=finish to=None
ultraDreadnought       OK caster=53 legales=[1159]      natif=1159 port=finish to=None
invariants du chemin VIOLES sur 0/8 MoW
```

`port=finish` sur ces 7 lignes n'est **pas** un défaut du chemin : **1187 est la SEULE des 16
abilities MoW à avoir une face DÉCISION portée** (`is_noncomp` = True pour 1187 seul ; aucune n'est
dans `playbook.REGISTRY`). Le chemin est ouvert ; ce qui manque est le gisement suivant (une feuille
par ability), désormais **déblocable** — c'est précisément ce que R15 attendait.

### 4.3 Non-régression (tests CIBLÉS rejoués, tous verts)

| suite | résultat |
|---|---|
| `test_playbook_live.py` (agreement, seed 777) | 3 passed |
| `test_playbook_live.py` (agreement, seed 31337) | 3 passed |
| `test_runner_state_live.py` + `test_spore_mine_launcher_live.py` + `test_turnflow_live.py` | 8 passed |
| `test_predict_live.py` + `test_runner_attack_live.py` | 4 passed |
| `test_thrice_blessed_decision_live.py` | 4 passed |

### 4.4 Ce qui n'est PAS couvert

- **La coïncidence des 15 autres abilities MoW** : aucune feuille de décision n'est portée pour
  elles, donc le port rend `finish`. Mesurable dès qu'une feuille est portée (le sweep donne, par
  MoW, l'ability que le natif choisit — c'est l'ordre de priorité de portage).
- **Le tie-break inter-abilities d'une même MoW** : jamais exercé, aucune MoW n'ayant deux feuilles
  portées.
- **La voie 100 % OFFLINE** (`state_bridge.build_from_state`) n'a pas de jumeau Machine — cf. §5.
- **`ShouldRandomizeOrder`** (`ActiveAbilityActionGenerator$$ShouldRandomizeOrder` → `Shuffle` des
  abilities quand deux entrées partagent le même type) n'est porté sur aucun des deux chemins.

---

## 5. Résidus laissés OUVERTS (nommés, pas contournés)

1. **Voie 100 % offline pour un caster Machine.** `ability_targets_offline` mirrore
   `BasePlaybook$$GetAllValidTargetsFromAllPossibleMovementTiles` : il ancre les cibles aux
   tuiles-caster (origine + move) et rend donc VIDE pour une entité sans position. L'éligibilité
   d'une ability de MoW vient de ses `TargetingOptions` + `GetAllTargets` (filtre STATIQUE non porté,
   tâche #115). Tant qu'il manque, la face DÉCISION MoW se confronte par la voie LIVE (RPC
   `abilityTargets`), exactement comme `context.build` le fait pour les unités. Un
   `build_machine_from_state` aujourd'hui serait du code sans consommateur (une MoW n'est pas
   `ai_controlled`) et sans cibles.
2. ~~**`get_Priority` EST surchargé sur au moins 3 playbooks**~~ → **FERMÉ par #170**, et le constat
   était **doublement sous-estimé** :
   - ce ne sont pas 3 playbooks mais **22** (les 3 vus dans `methods.tsv` n'étaient que les
     représentants de RVA de corps dédupliqués — la table est indexée par RVA, sans doublon, donc
     8 autres playbooks de tier 1000 partagent la ligne de `TzeentchsFirestormPlaybook`) ;
   - l'incidence n'était **pas** nulle : **trois playbooks DÉJÀ PORTÉS** avaient un tier faux —
     NovaBoost 1192 (0 → **1000**), ThriceBlessedConflagration 1187 (0 → **100**), NovaShield 1194
     (0 → **-1000**). #115 avait explicitement *supprimé* les valeurs 1000/-1000 de NovaBoost et
     NovaShield en les croyant issues d'un symbole stale : elles étaient justes.
   - l'affirmation n'était **pas** dans `CLAUDE.md` (`git log -S "get_Priority" -- CLAUDE.md` = vide)
     mais dans le code : `engine/ai/tactic.py`, `engine/ai/action_generators.py`,
     `engine/playbook/noncomparable/__init__.py` + ~22 docstrings de feuilles.

   Table de référence : `engine.playbook.noncomparable.NATIVE_PRIORITY` ;
   garde live `scripts/python/probe_170_playbook_priority.py` ; garde offline du câblage
   `tests/engine/test_nc_priority_tiers_offline.py`. Cf. [`case-170-get-priority.md`](case-170-get-priority.md).
3. **Le gate `can_currently_be_used` n'est appliqué que sur la voie LIVE.**
   `state_bridge.build_from_state` fabrique ses abilities depuis gameconfig avec `usable: True` en
   dur et ne consomme pas l'`ActiveAbilitiesComponent` (désormais chargé pour les unités ET les
   MoW) : le chemin summon offline reste plus permissif que le natif. Non touché ici (hors
   périmètre, et `test_skitarii_turn_live` — R5 — est déjà rouge sur ce chemin).
4. **`test_mow_caster_load_live.py` écrit ses state-files dans `data/`**
   (`data/_pytest_mow{gen,load,none}_<hash>.json`, non ignorés) — même famille que R24, sur un autre
   fichier que `conftest.py`.

---

## 6. Ce que ce case NE prouve PAS (hypothèse testée et RÉFUTÉE)

Les 3 suites MoW rouges pré-existantes ne s'expliquent **pas** par le gate munitions. Hypothèse
testée : « au seed BC par défaut, les abilities MoW à `munitionsCost` sont des no-op silencieux, d'où
les `live=[]` ». **Réfutée par mesure** : `test_mow_targeting_predicate_live::test_entropy_cannons…`
échoue sur `off_delta=20` vs **`live_delta=1631`** — le cast LIVE d'`EntropyCannons` (1168,
`hasAmmo=False`) produit bien 1631 de dégât. `applyAction` exécute la cascade native **sans** passer
par `CanCurrentlyBeUsed`, qui est un gate de DÉCISION/UI, pas d'exécution. Ces échecs sont des
divergences de MAGNITUDE côté port, étrangères à R14.

Baseline vérifiée par `git stash` : `test_mow_caster_load_live.py` rend **3 failed / 3 passed** à
l'identique AVANT et APRÈS ce correctif.
