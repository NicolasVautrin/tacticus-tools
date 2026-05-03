# Tacticus Builder — Status (2026-05-03)

## TL;DR

**Campaign Builder** end-to-end fonctionnel sur Tacticus PC (Windows IL2CPP). Pipeline stable :
**INJECT → warmup (clic battle in-game) → push `builder_ready` → catalog auto-refresh → build node (events inactifs inclus)**.

Plus aucun crash IL2CPP cctor cascade, plus aucun freeze UnityFreezeDetector. Path 2 progression-swap + per-faction warmup couvre tous les campaign types testés.

## Architecture

### Capture pipeline

| Capture | Hook | Timing | Notes |
|---------|------|--------|-------|
| `lastSource` (CampaignGameModeSource) | `..ctor` | **onLeave** | onEnter = fields uninit ; onLeave = post Zenject injection |
| `lastSource` (alt) | `.LoadBattle` | onEnter | post-construction, OK direct |
| `lastConfigBuilder` + `lastUnitDelegate` | `BattleConfigBuilder.GetCampaignLevelConfig` | onEnter | capture builder + Func<string,IUnitModel> en même temps |
| `lastUnitProgression` | `UnitProgression.GetUnit` | onEnter | hook spécifique 1-arg, PAS broad-hook |
| `lastGameConfig` | dérivé de `lastSource._gameConfig` à la demande | via `unwrapGameConfig` | offset 0x90 = `GameConfigData` wrapper ; on extrait via `.gameConfigDto` getter |

### Push-based UI sync

- Agent émit `send({ t: "builder_ready", via: "ctor" | "LoadBattle" })` quand `lastSource === null` → assigné
- Front `ws.js` : `registerWsHandler(t, fn)` pluggable handlers
- Front `campaign-builder.js` : handler idempotent `builder_ready` → `refresh(true)` (force agent dump)
- Plus de polling `builderStatus` toutes les 5 s pour le warmup (le `setInterval` reste défensif, ne déclenche que `refresh(false)` cache disque uniquement)

### Build path

Path 2 progression-swap reste primaire :
1. Resolve `targetMatch` via `gameConfig.battles.campaigns[type][id].battles[locIdx]`
2. **Per-faction warmup** : `UnitProgression.GetUnit(unitId)` pour chaque enemy unit unique du match
3. Sur `source._campaignProgression` (offset +0x20), save+swap `_campaignType` (+0x18), `_campaignId` (+0x28), `_battlesConfigCampaigns` (+0x88)
4. Sur `source`, save+swap state (campaignId/locIdx/match/battle)
5. `LoadBattle(true)` → BattleConfiguration
6. Restore tout dans `finally`

## Heap scans = explicit-only

Frida `Process.enumerateRanges` / `Memory.scan` suspendent les threads cibles → 10–11 s de freeze game thread → **Tacticus's UnityFreezeDetector kill le process**.

| Scan | Auto trigger | Manual trigger |
|------|--------------|----------------|
| `findGameConfigDtoViaHeap` | ❌ supprimé partout | ✓ via `dumpCampaignCatalog({ allowHeapScan: true })` (bouton ↻) |
| `findAutoTestFactoryViaHeap` | ❌ supprimé de `campaignBuilderStatus` | (path 0 dead, jamais utile) |
| `findCampaignGameModeSourceViaHeap` | ❌ jamais auto | fallback dans buildCampaignConfig si lastSource manquant |

## Hooks au boot

5 `Interceptor.attach` spécifiques + 2 `Interceptor.replace` pumps :
- `CampaignGameModeSource..ctor` (onLeave)
- `CampaignGameModeSource.LoadBattle` (onEnter)
- `BattleConfigBuilder.GetCampaignLevelConfig`
- `UnitProgression.GetUnit` (1-arg)
- 19 × `*GameModeSource.LoadBattle` via `mode-source-capture` (capture passive de battles naturels, serialize déféré via `queueOnMainThread` + `gcRoot.add`)
- 8 × `IdunUniverse.*` via `unit-visual-resolve`
- `IdunGameViews.Update` + `UnityFreezeDetector.Update` (pumps via replace)

Module désactivés (désormais opt-in si besoin AI debug) :
- `movement-trace` — 39 hooks `EvaluateMovementInSteps` × 3 `class_get_name` par appel = lag visible
- `ad-bypass` — Tacticus PC n'a pas d'ads (module supprimé)

## Validations

| Test | Path | Status |
|------|------|--------|
| Inject + warmup + auto catalog refresh | push `builder_ready` | ✅ |
| Catalog dump | `unwrapGameConfig` (no heap scan) | ✅ 1.17 MB |
| Standard campaign build | path 2 mute | ✅ |
| Event campaign INACTIVE build | path 2 + progression-swap + per-faction warmup | ✅ |

## Tasks restantes

- #25 MachinesOfWar Event support (code path séparé `MachinesOfWarEventGameModeSource` avec son DTO)
- #23 UI banner "warm-up needed" — moins urgent depuis le push `builder_ready`

## Pièges majeurs documentés (memory)

- (file:///C:/Users/nicolasv/.claude/projects/C--Users-nicolasv-tacticus-tools/memory/project_tacticus_pc_workflow.md) — workflow stable + pièges à ne pas réintroduire (broad-hooks UI, get_gameConfigDto hook, heap scans auto)
- (file:///C:/Users/nicolasv/.claude/projects/C--Users-nicolasv-tacticus-tools/memory/project_campaign_builder_resolution.md) — pattern progression-swap, layouts CGMS+CampaignProgression
