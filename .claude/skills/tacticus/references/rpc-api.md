# RPC API — agent Frida ↔ host

Référence des RPC exposés par l'agent injecté (`frida/hooks/`) et appelés par
le host Node (`frida/host/`). Tenu à jour avec le code ; en cas de doute, la
source fait foi (`grep -rhoE "ctx\.rpc\.[A-Za-z0-9_]+" frida/hooks`).

## Mécanisme

Chaque feature module fait `register(ctx)` et attache ses handlers sur
`ctx.rpc.<nom>` (`Ctx = { rpc: Record<string, (...args) => unknown> }`, voir
[hooks.md](hooks.md)). Le host appelle un RPC via :

```
POST /api/scripts/<sessionId>/rpc
Content-Type: application/json
{ "method": "<nom>", "args": [ ... ], "timeout": <ms> }
```

Réponse : `{ "result": <payload> }` (ou `{ "error": ... }`, HTTP 500 si le
handler throw). `args` est un **tableau positionnel** : la plupart des RPC
prennent un **seul objet d'options** → `args: [{ ... }]`.

Récupérer la session active : `GET /api/admin/status` → `.session.id`. Le
`sessionId` **change à chaque (ré)injection** (`POST /api/admin/inject`).

**Thread** : tout RPC qui touche l'état IL2CPP/MatchState s'exécute via
`queueOnMainThread(...)` (pump Unity) — jamais d'accès heap hors main thread.

## Workflow runner isolé (RL / sim 0-token)

Le cœur : construire un `IdunRunner` isolé depuis une `BattleConfiguration`
JSON, le jouer sans toucher au battle in-game. Ordre obligatoire :

1. **`warmupGameSingletons({ force })`** — initialise les classes battle
   IL2CPP (sinon metadata non init → crash 0x2c). 1× par session après inject.
2. **`buildNormalizedBC({ baseBcJson, targetRank, targetProgressionIndex, targetRarity, targetLevel, targetStarLevel, targetAbilityLevel, boardJson?, spawnPointSetIndex? })`**
   → `{ ok, configJson, normalized:[unitId], mow:[unitId] }`. Normalise une BC
   seed (résout les stats au rank cible) ; `mow` = unités flaggées MoW
   (= `PredefinedMachines`). **Toujours** passer par là : les UnitId `:pvp`
   bruts échouent la désérialisation directe.
3. **`initAndStart({ configJson, seed?, playerUnits:[{unitId, playerId, col, row}] })`**
   → `{ runnerId, seed, addUnits, startEventCount }`. Atomique : deserialize BC
   → `buildRunner` (Initialize consomme `PredefinedUnits`/`PredefinedMachines`
   et auto-spawn) → AddUnit joueur aux spawn points → StartMatch.
   Variante en 3 temps : `initRunner` + `applyAddUnit`×N + `startBattle`.
4. **`observeBattle({ runnerId })`** → état projeté (voir shape ci-dessous).
5. **`autoPlayRunner({ runnerId, maxTurns })`** → joue la battle entière en
   bouclant `CheatRunAIMessage` (1 par tour, 1 `queueOnMainThread`/tour).
   Retour `{ ok, turns, reachedFinished, finalStage, hitMaxTurns, history }`.
   Tour par tour : **`playTurn({ runnerId })`**.
6. **`disposeRunner({ runnerId })`** — libère le runner + unpin la BC (gcRoot).

Single-build : `initRunner`/`initAndStart` disposent tout runner précédent.

### Shape `observeBattle`

```jsonc
{
  "ok": true, "runner": "0x..", "matchState": "0x..",
  "stage": 1, "stageName": "Running", "currentPlayer": <id>,
  "counts": { "total", "tiles", "units", "match", "effects", "player", "other" },
  "byType": { "0":tiles, "1":units, "5":unitFeet, "6":machines, "7":platforms, ... },
  "units": [ { entityId, squadId, visualId, teamId, playerId, col, row,
               hp, hpMax, rank, isDead } ],   // 1 ligne par UnitFoot visible
  "mows":  [ { id, machineId, entityType:6, pos, hp, maxHp, ownerId, teamId,
               visualId, rank, isDead, initialSlot } ]  // 1 ligne par Machine type-6
}
```

`byType` = `EntityType` enum (voir [hooks.md](hooks.md) : Tile=0, Unit=1,
Match=2, Effect=3, Player=4, UnitFoot=5, Machine=6, MachinePlatform=7,
EnvironmentAbility=8). MoW : `hp`/`pos` sont `null` **by design** (l'entité
Machine ne porte ni HealthComponent ni PositionComponent) ; `visualId`,
`teamId`, `ownerId`, `initialSlot` (slot Top/Bottom) sont fiables.

`dumpEntityComponents({ runnerId, types?:[int], perType? })` — introspection
read-only : liste les classes de composants par EntityType (sert à trouver où
vivent HP/position/etc.).

## Capture live (depuis le jeu)

- **Campaign** : `buildCampaignConfig`, `dumpCampaignCatalog`,
  `diagnoseCampaign`, `campaignBuilderStatus` (`campaign-builder.ts`). Nécessite
  d'avoir cliqué une battle de campagne in-game une fois (capture
  `CampaignGameModeSource`).
- **BattleConfiguration live** : `inspectBattleConfig`, `dumpBattleConfig`,
  patch (`setBattleConfigPatch`, `setBattleConfigGameMode`,
  `setBattleConfigRuleSet`, `applyBattleConfigPatchNow`,
  `clearBattleConfigPatch`, `getBattleConfigPatchStatus`) (`battle-config.ts`).
- **Boards** : `dumpAllBoards`, `dumpPvpAndSyncBoards`, `inspectSpawnPoints`.
- **MachinesOfWar events** : `buildMachinesOfWarConfig`,
  `dumpMachinesOfWarCatalog`, `machinesOfWarBuilderStatus` (`mow-builder.ts`).
  NB : hors-sujet pour le MoW **arena PvP** (qui passe par la BC arena +
  `PredefinedMachines`, cf. mémoire `project_mow_deploy_gate`).
- **UI nav** : `uiList`, `uiListAll`, `uiClick(path)` — pilote
  `Button.onClick` (`ui-nav.ts`).

## Sim / mirror

`sim`, `simAndCommit`, `simRunAiTurn`, `simEndTurn`, `simBuildPreview`,
`simGetState`, `simMirror`, `simRebuildAndCatchUpTo`, … (`sim-engine.ts`,
`sim.ts`). Mirror = runner persistant qui suit le runner live (⚠️ ne pas
restart le host en plein battle — bootstrap Replay.Messages top-level only).

## AI trace / observabilité

- `ai-trace.ts` : `aiTraceEnable/Disable/Status/GetProjections/SetProjection`.
- `ai-utility-trace.ts` : `aiUtilityTraceEnable/Disable/Dump/Counters/Patch/Clear`,
  `…DiagSampler…`, `…Callstacks…` — quelles clés `UtilityConfig` l'IA lit.
- `message-trace.ts` (auto-install) : `messageTraceStatus` ; capture les
  messages `runner.Apply` + sous-messages IA (`MoveUnitMessage`,
  `ActiveAbilityMessage`, …) avec `unitId@0x10` + snapshot MatchState, flush
  JSONL dans `data/ai-traces/<sessionId>-*.jsonl`.
- Autres traces : `bucket-audit.ts`, `dispatch-observe.ts`, `move-options.ts`
  (`armMoveOptionsTrace`), `movement-trace.ts`, `board-trace.ts`,
  `winner-capture.ts` (`winnerCaptureStatus`), `whatif-trigger.ts`.

## Introspection / dump (scratch)

`introspect.ts` + la nuée de modules `hooks/scratch/*` exposent ~120 RPC
`dump*` / `check*` / `search*` / `find*` (offsets de composants, méthodes,
enums, formules de stats, weapons, progression…). **Outils de RE one-shot**,
pas du chemin de prod — utiliser pour lire des layouts IL2CPP, jamais comme
dépendance d'un hook live.

## Conventions

- **Aucune RVA hardcodée** : résolution runtime (`findClassAnywhere` →
  `findMethod` → `Interceptor.attach`). Cf. CLAUDE.md.
- **Pas de heap scan auto** (`Memory.scan`/`enumerateRanges`) : gèle le main
  thread → UnityFreezeDetector tue le process. Gated `allowHeapScan` only.
- **Pas de broad-hook** sur méthodes UI hot / property getters sérialisés.
- Features diagnostiques : **auto-arm au register**, pas d'étape « arm » manuelle.
