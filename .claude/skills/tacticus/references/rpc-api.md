# RPC API — agent Frida ↔ host

RPC exposés par l'agent injecté (`frida/hooks/`), appelés par le host Node et
les scripts `scripts/python/`.

**Synchronisé avec le code le 2026-07-02.** Surface réelle = 257 handlers
(`grep -rhoE "ctx\.rpc\.[A-Za-z0-9_]+" frida/hooks`). Ce fichier documente
individuellement les RPC du **workflow actif** (consommés par `rl_duel.py`,
`predict_validate.py`, `pathfind_validate.py`, `rl_probe_step.py`,
`rl_collect_batch.py`, `engine_validate.py`, tests) et regroupe le reste par
**famille de diagnostic**. La source fait foi.

## Mécanisme

Chaque feature fait `register(ctx)` et attache ses handlers sur `ctx.rpc.<nom>`
(voir [hooks.md](hooks.md)). Appel host :

```
POST /api/scripts/<sessionId>/rpc   { "method","args":[...],"timeout":<ms> }
```

Réponse `{ "result" }` (ou `{ "error" }`, HTTP 500 si throw). `args` positionnel ;
la plupart des RPC = **un seul objet d'options** → `args: [{ ... }]`. Session :
`GET /api/admin/status` → `.session.id`, **change à chaque (ré)inject**. Tout RPC
touchant l'état passe par `queueOnMainThread` (pump Unity). **Ordre = dernier
`register` gagne** : `battleStatus`/`dumpEntityComponents` d'`ai-step` écrasent
les homonymes de `status.ts`/`observe.ts`.

## Cycle de vie du runner isolé (RL / sim 0-token)

Ordre obligatoire (détails CLAUDE.md « Workflow RL ») :

- **`warmupGameSingletons({ force? })`** (`warmup-singletons.ts`) — nav UI
  AUTONOME (capture `lastSource` + init classes battle IL2CPP, sinon crash 0x2c).
  1× par session après chaque (ré)inject, avant tout autre RPC. Aucun clic humain.
- **`buildNormalizedBC({ baseBcJson, target{Rank,ProgressionIndex,Rarity,Level,StarLevel,AbilityLevel}, boardJson?, spawnPointSetIndex? })`**
  (`normalize-bc.ts`) → `{ ok, configJson, normalized:[unitId], mow:[unitId] }`.
  Résout une BC seed au rank cible ; passage obligé (les UnitId `:pvp` bruts
  échouent la désérialisation).
- **`initAndStart({ configJson, seed?, playerUnits:[{unitId,playerId,col,row}], keepExisting? })`**
  (`launch.ts`) → `{ runnerId, seed, addUnits, startEventCount }`. Atomique :
  deserialize → buildRunner (Initialize auto-spawn PredefinedUnits/Machines) →
  AddUnit joueur → StartMatch. Variante 3-temps : `initRunner` + `applyAddUnit`×N
  (+ `applyAddMachine`/`applyAddUnitSrc`) + `startBattle({ runnerId })`.
- **`buildPatchedRunner(patch?)`** (`battle-config.ts`) → `{ ok, runnerId, runner,
  seed, bcPtr, patch }`. Runner depuis la BC live capturée avec patch in-place
  (aiUnits/randomizeAi/templateOverrides). Warmup préalable requis.
  `spawnPredefinedUnits({ runnerId })` / `addPredefinedMachine({ playerId, unitId,… })`
  = leviers manuels sur cette BC live.
- **`observeBattle({ runnerId })`** (`observe.ts`) → état projeté (shape ci-dessous).
- **`autoPlayRunner({ runnerId, maxTurns? })`** (`cheat.ts`) → joue toute la
  battle (boucle `CheatRunAIMessage`, 1/tour) → `{ ok, turns, reachedFinished,
  finalStage, hitMaxTurns, history }`. Tour par tour : `playTurn({ runnerId })`.
  Sur le runner LIVE : `cheatRunAi()`.
- **`battleStatus({ runnerId })`** (ai-step) — poll LÉGER (stage + currentPlayer +
  winner + unitsAlive, sans projection) ; base du long-poll `/api/selfplay/:id/await`.
- **`dumpRng({ runnerId })`** → `{ mt:[624], mti, callCount }` — MT19937 de combat
  pour synchroniser `engine/runner/prng.py`.
- **`disposeRunner({ runnerId })`** / **`listRunners()`** (`launch.ts`).

Single-build (défaut) : `initRunner`/`initAndStart` disposent **TOUT** runner
précédent **silencieusement**. Multi-runner / self-play : `keepExisting:true`
(`rl_duel build --keep`). FOOTGUN : un build sans `--keep` dans une fenêtre
concurrente **nuke les frères en vol** (signature : `listRunners`=[] +
`await` → 502 instantané) ; parade = gate d'adressabilité au SETUP. cf.
docs/rl/design.md §Multi-runner.

### Shape `observeBattle`

`{ ok, stage, stageName, currentPlayer, counts, byType, units[], mows[] }`.
`units` = `{ entityId, squadId, visualId, teamId, playerId, col, row, hp, hpMax,
rank, isDead }` ; `mows` = `{ id, machineId, entityType:6, pos, hp, maxHp,
ownerId, teamId, visualId, rank, isDead, initialSlot }`. `byType` = `EntityType`
(Tile=0, Unit=1, Match=2, Effect=3, Player=4, UnitFoot=5, Machine=6,
MachinePlatform=7, EnvironmentAbility=8). MoW : `hp`/`pos` = `null` by design
(entité Machine sans Health/Position) ; visualId/teamId/ownerId/initialSlot fiables.

## Décision & action (oracle live — `ai-step/rpc-view.ts`)

Read-only sauf `applyAction` (`mutated=false` attendu). Cœur oracle + harnais moteur.

- **`decisionView({ runnerId, maxRank?=6, allAbilities?=false })`** — vue
  décision-ready : méta + units (pos/HP/team/alive/hasAction/ranged/abilities) +
  `toActivate` + `attackPlans` rankés + `dangerZone` + `roundCap` + `effects` live.
- **`combatSnapshot({ runnerId })`** — stats de combat RÉSOLUES par unité
  (`GetStat`) ; seed one-shot du prédicteur offline.
- **`tileMeta({ runnerId })`** — élévation + terrain + effets par tuile.
- **`boardGraph({ runnerId })`** — adjacence hex native (`GetAdjacentTiles`) +
  `walkable` + élévation ; graphe STATIQUE, capter 1×/battle.
- **`pathDistToEnemies({ runnerId, unitId })`** — par tuile atteignable,
  distance-CHEMIN (`Pathfinders.GetPath`) à l'ennemi le plus proche (≠ dist hex).
- **`aiMovableTiles({ runnerId, side?, dangerZone?, threat?, extraRange?, overrideRange? })`**
  — tuiles légales par unité contrôlée (`GetMovableTilesFor`).
- **`aiAttackRank({ runnerId, unitId?, targetId?, abilityType?, allAbilities?, maxRank?=8, overrideRange? })`**
  — positions d'attaque RANKÉES par (unit,target,ability) via `GetBestTileToAttackFrom`.
- **`abilityTargets({ runnerId, unitId?, abilityType?, allAbilities?=true })`** —
  cibles légales par (unit,ability) incl. non-attaque. `targets` = move inclus ;
  `fromHere` = sans bouger. Absent des deux ⇒ no-op certain.
- **`abilityReason({ runnerId, casterId, abilityType, targetId? })`** — raison
  structurée d'un cast invalide (flags `TargetingRule` en noms).
- **`aiPredict({ runnerId, unitId, targetId, abilityType?, col?, row? })`** —
  prédiction de dégât (`GetAllPredictions`) pour un (unit,target) depuis une tuile.
- **`exposureView({ runnerId, unitId?, allAbilities?=true })`** — move-guard
  (inverse d'attackPlans) : dégât ennemi entrant au prochain tour + flag `exposed`.
- **`applyAction({ runnerId, action | actions[] })`** — applique mon coup
  (`ApplyAiMessage`), snapshot avant/après. `action` = `{kind:"move",unitId,to|feet}`
  | `{kind:"ability",casterId,targetId,abilityType}` | `{kind:"finish",unitId}`.
  Fidèle (SkipFlags=false). Décomposable 1 action/appel.
- **`dumpEntityComponents({ runnerId, target?, withFields? })`** — introspection
  read-only des composants d'une entité.

## Pilotage de l'IA native (`ai-step/rpc-drive.ts`)

- **`aiStepDryRun({ runnerId, maxPump? })`** — pompe 1 `MoveNext` de
  `CalculateNextActionForPlayer`, décode l'action suivante SANS commit.
- **`aiDryRunAllUnits({ runnerId, maxPump? })`** — par unité, action proposée
  par l'IA (`CalculateNextActionForUnit`) contre le même état, sans appliquer.
- **`aiPlayByUnit({ runnerId, maxTurns?, maxActivations?, maxPump?, captureEvents?, captureOverwatch? })`**
  — driver per-unité COMPLET (sans `CheatRunAIMessage`) : l'IA choisit unité +
  position, applique + capture 1 démo/activation.
- **`aiPlayOrdered({ runnerId, order?="desc", maxTurns?,… })`** — force l'ordre
  d'activation (l'IA décide seulement quoi fait chaque unité).

## Capture live (depuis le jeu)

- **Campaign** (`campaign-builder.ts`, `auto-boot.ts`) : `buildCampaignConfig`,
  `dumpCampaignCatalog`, `diagnoseCampaign`, `campaignBuilderStatus`,
  `triggerAutoBoot`, `getAutoBootStatus`.
- **BattleConfiguration** (`battle-config.ts`) : `inspectBattleConfig`,
  `dumpBattleConfig`, `inspectSpawnPoints`, `discoverSources`, patch
  (`setBattleConfigPatch`/`…GameMode`/`…RuleSet`/`applyBattleConfigPatchNow`/
  `clearBattleConfigPatch`/`getBattleConfigPatchStatus`).
- **Boards** : `dumpAllBoards`, `dumpPvpAndSyncBoards` (`dump-boards.ts`,
  `dump-pvp-boards.ts`).
- **MachinesOfWar** (`mow-builder.ts`) : `buildMachinesOfWarConfig`,
  `dumpMachinesOfWarCatalog`, `machinesOfWarBuilderStatus`, `dumpLiveEvent*`,
  `dumpMoWProgressionState` (hors-sujet MoW arena PvP : cf. `project_mow_deploy_gate`).
- **UI nav** (`ui-nav.ts`) : `uiList`, `uiListAll`, `uiClick(path)`.
- **Config / visuels** : `getGameConfig`/`getMatchState` (`config-io.ts`) ;
  `getGameVersion`/`dumpEnum(s)`/`resolveVtableSlot` (`introspect.ts`) ;
  `resolveUnitVisual`/`dumpAllUnitVisuals`/`getUnitAssetMap` (`unit-visual-resolve.ts`,
  `unit-asset-map.ts`).

## Sim / mirror (`sim-engine.ts`, `sim.ts`)

`sim`, `commit`, `simAndCommit`, `simRunAiTurn`, `simEndTurn`, `simMirror`,
`simBuildPreview`, `simGetState`, `simRebuildAndCatchUpTo`, `simStatus`, `simReset`,
… Mirror = runner persistant suivant le live. ⚠️ `Interceptor.replace` actif → ne
pas restart le host en plein battle.

## Familles de diagnostic (rôle + source ; auto-armées au `register`)

Outils de RE / observabilité — jamais une dépendance d'un hook live.

- **`dump*`/`check*`/`find*`/`search*`/`test*`/`inspect*`/`map*`** (~90,
  `controller.ts` → `hooks/scratch/*`) : introspection IL2CPP one-shot (offsets,
  méthodes, enums, stats, weapons, progression).
- **`aiTrace*`** (`ai-trace.ts` + `ai-trace/`) : capture playbook/prédictions/
  utilités → JSONL (`data/ai-traces/`). `aiTraceEnable(level)`/`aiTraceStatus()`
  pilotés par les scripts RL.
- **`aiUtilityTrace*`** (`ai-utility-trace.ts`) : clés `UtilityConfig` lues par l'IA.
- **`scorer*`** (`scorer-damage-trace.ts`) : scoring de dégât par tuile.
- **`bucketAudit*`** (`bucket-audit.ts`) : actions ajoutées/choisies par bucket.
- **`overwatch*`/`overwatchFix*`** (`overwatch-fix/`) : anti-suicide overwatch.
- **`whatifTrigger*`** (`whatif-trigger.ts`) : simulation « et si » de triggers.
- **`dispatchObserve*`** (`dispatch-observe.ts`), **`modifierObserve*`**
  (`modifier-observe.ts`) : observation StreamDispatcher / modificateurs de dégât.
- **`movementTrace*`** (`movement-trace.ts`, DÉSACTIVÉ par défaut : hooks laggy),
  **`boardTrace*`** (`board-trace.ts`), **`moveOptionsTrace*`** (`move-options.ts`).
- **Statuts / dumps ponctuels** : `dumpComposedUtility*` (`dump-composed.ts`),
  `messageTraceStatus` (`message-trace.ts`), `winnerCaptureStatus`
  (`winner-capture.ts`), `abilityPreferences` (`ability-prefs.ts`),
  `rlGetObservation` (`rl/bridge.ts`).
- **Divers debug** : `probe*`/`installStatsFormulaTrap`/`dumpItemsCatalog`/`previewBis`
  (`normalize-bc/debug-rpcs.ts`, `items-catalog.ts`) ; `findClassesNamed`/`dumpModeSources`
  (`mode-source-capture.ts`) ; `armExceptionCtorHook` (`init-trace.ts`) ;
  `ping`/`info`/`summary`/`dump`/`clear`/`forceInstall` (`status.ts`).

## Conventions

- **Aucune RVA hardcodée** : résolution runtime (`findClassAnywhere` →
  `findMethod` → `Interceptor.attach`). Cf. CLAUDE.md.
- **Pas de heap scan auto** (`Memory.scan`/`enumerateRanges`) : gèle le main
  thread → UnityFreezeDetector tue le process. Gated `allowHeapScan` only.
- **Pas de broad-hook** sur méthodes UI hot / property getters sérialisés.
- Features diagnostiques : **auto-arm au register**, pas d'étape « arm » manuelle.
