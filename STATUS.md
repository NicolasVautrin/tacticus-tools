# Tacticus Builder — Status (2026-05-03 fin de session)

## TL;DR

**Projet stable end-to-end sur Tacticus Windows PC** (Unity 6 IL2CPP).
Pipeline validée : `INJECT (UI) → amorce (clic battle in-game) →
push builder_ready → catalog auto-refresh → build node`. Aucun crash,
aucun freeze. Code mort path 0/1 supprimé. Docs à jour. **Commit
`e25aefc` poussé sur origin/master.**

## Pipeline validée (1 build event tyranid réel)

```
13:13:00  ✓ UnitProgression captured (via GetUnit hook)
13:13:02  ✓ CampaignGameModeSource ctor onLeave → lastSource captured
13:13:02  ✓ send({ t: "builder_ready", via: "ctor" })
13:13:02  ✓ IdunUniverse + BattleConfigBuilder + delegate captured
13:13:03  ✓ gcRoot ArrayList created (defer serialize ready)
14:01:57  ✓ captured_config eventStandard2 loc=24 (540 KB) — battle naturel
14:02:00  ✓ build event lancé via front
          → entering mute path
          → precharge 3 unit classes (prechargement par faction)
          → progression swap: type 0→4, id → "eventStandard2", battlesList swapped
          → LoadBattle returned in 59 ms
          → serialized 548 KB
          → progression restored
          ✓ captured_config eventStandard2 loc=30 (548 KB) — battle généré
```

## Architecture définitive

### Hooks essentiels (au boot, light)

| Hook | Type | Rôle |
|------|------|------|
| `IdunGameViews.Update` | replace | main pump (drain queueOnMainThread) |
| `UnityFreezeDetector.Update` | replace | menu pump (idem hors battle) |
| `CampaignGameModeSource..ctor` | attach onLeave | capture lastSource + push builder_ready |
| `CampaignGameModeSource.LoadBattle` | attach onEnter | capture lastSource (alternatif) |
| `UnitProgression.GetUnit` (1-arg) | attach | capture lastUnitProgression |
| `IdunUniverse.*` × 8 | attach | capture lastUniverse + dump unit visuals |
| `*GameModeSource.LoadBattle` × 19 | attach onLeave | capture passive battles → defer serialize |

Pas de broad-hook UI hot. Pas de hook permanent sur getter. Pas de heap
scan auto.

### Build path (path 2 mute progression-swap)

1. Resolve `targetMatch` via `gameConfig.battles.campaigns[type][id].battles[locIdx]`
2. **Prechargement par faction** : `UnitProgression.GetUnit(unitId)` pour chaque
   enemy unit unique du match (pré-résout les classes IL2CPP cold)
3. Sur `source._campaignProgression` (offset +0x20), save+swap :
   - `+0x18` `_campaignType` (S32) → request type
   - `+0x28` `_campaignId` (string ptr) → managed string
   - `+0x88` `_battlesConfigCampaigns` (List ptr) → eventBattlesList
4. Sur `source`, save+swap state (campaignId/locIdx/match/battle)
5. `LoadBattle(true)` → BattleConfiguration
6. Restore tout dans `finally`
7. Round-trip ~60 ms

### Push-based UI sync

- Agent émet `send({ t: "builder_ready", via: "ctor" | "LoadBattle" })`
  quand `lastSource` passe de null → assigné
- Front `ws.js` : `registerWsHandler(t, fn)` pluggable handlers
- Front `campaign-builder.js` : handler idempotent `builder_ready` →
  `refresh(true)` une seule fois
- Plus de polling de `builderStatus` pour le amorce (le `setInterval`
  défensif persiste mais ne déclenche que `refresh(false)` cache disque)

### Heap scans = explicit-only

| Scan | Auto trigger | Manual trigger |
|------|--------------|----------------|
| `findGameConfigDtoViaHeap` | ❌ | via `dumpCampaignCatalog({ allowHeapScan: true })` (bouton ↻) |
| `findCampaignGameModeSourceViaHeap` | ❌ | fallback `buildCampaignConfig` si lastSource manquant |
| `findUnitProgressionViaHeap` | ❌ | fallback synth (mort, mais code conservé) |
| `findAutoTestFactoryViaHeap` | — | **supprimé** (mort code) |
| `findBattleConfigBuilderViaHeap` | — | **supprimé** (path 1 mort) |

## Cleanup commit `e25aefc`

**campaign-builder.ts** : 2047 → **881 lignes (-57%)**
**dist/hooks.js** : 145 → **110 KB (-23%)**

**Supprimé** :
- Path 0 : `findAutoTestFactoryViaHeap`, `tryBuildViaAutoTestFactory`,
  `lastAutoTestFactory`, `autoTestFactoryScanDone`
- Path 1 : `tryConstructConfigBuilder`, `trySynthesizeDelegate`,
  `findBattleConfigBuilderViaHeap`, `getCampaignLevelConfigMi`,
  `lastConfigBuilder`, `lastUnitDelegate`, `lastRandom`, `synthDelegate`,
  BattleConfigBuilder hook
- Crash diag : `_runtimeInvokePropagate`, `armCrashDiag`/`disarmCrashDiag`/
  `ensureCrashDiagInstalled`, crash globals
- IL2CPP helpers inutilisés : `_methodGetParam`, `_methodGetObject`,
  `_typeGetObject`, `_classGetFieldFromName`, `_fieldGetType`,
  `_classFromType`, `_methodGetPointer`
- Module `ad-bypass.ts` (Tacticus PC n'a pas d'ads)
- Imports nettoyés : `class_get_namespace`, `getSystemType`, `gcRoot`,
  `il2cpp_object_new`, `findCtorByParamCount`

**Re-activé** : `mode-source-capture` (avait été désactivé pour bisecter,
n'était pas le coupable). Defer serialize via `gcRoot.add` +
`queueOnMainThread` → onLeave revient instantané.

**Désactivé en place** :
- `movement-trace` — diagnostic AI, opt-in si besoin debug

## Validations

| Test | Path | Status |
|------|------|--------|
| INJECT light (sans freeze) | — | ✅ |
| Capture passive `captured_config` | mode-source-capture defer | ✅ 540+ KB |
| Push `builder_ready` → auto refresh | WebSocket pluggable handler | ✅ |
| Catalog dump | `unwrapGameConfig` (no heap scan) | ✅ 1.17 MB |
| Build event INACTIVE (eventStandard2) | path 2 progression-swap + prechargement par faction | ✅ 59 ms |
| Cleanup (path 0/1/diag/ad-bypass) | suppression + rebuild | ✅ |

## Docs réécrits (commit `e25aefc`)

- `CLAUDE.md` — Tacticus PC, workflow INJECT via UI, gotchas
- `README.md` (root) — public-facing, pipeline complète
- `frida/README.md` — layout actuel, RPCs, gotchas
- `.claude/skills/tacticus/SKILL.md` — bring-up, layouts validés
- `.claude/skills/tacticus/references/`
  - `frida-host.md` — host PC + endpoints
  - `hooks.md` — features mis à jour, règles enrichies
  - `rpc-api.md` — RPCs actuels
  - `knowledge.md` — préfixe "Pièges Tacticus PC"
  - `decompilation.md` — préfixe pipeline PC `GameAssembly.dll` / `sources_win/`
  - `ai-engine-audit.md` — header note PC vs Android
  - `game-architecture.md` — inchangé (zéro ref plateforme)
- `STATUS.md` — ce fichier (vivant)

## Layouts validés (Tacticus 1.38.94 PC)

```
CampaignGameModeSource :
  +0x20 _campaignProgression (ICampaignProgression)
  +0x68 _currentCampaignId (string)
  +0x70 _currentLocationIndex (int)
  +0x78 _currentMatch (CampaignConfigDto)
  +0x80 _currentBattle (BattleConfiguration)
  +0x90 _gameConfig (= GameConfigData wrapper, NON GameConfigDto direct)

GameConfigData (wrapper) :
  expose le DTO via .gameConfigDto property → GameConfigData.get_gameConfigDto()
  cf. unwrapGameConfig()

CampaignProgression (path 2 swap) :
  +0x18 _campaignType (CampaignType enum, 4 bytes)
  +0x28 _campaignId (string)
  +0x88 _battlesConfigCampaigns (List<CampaignConfigDto>)
```

## Tasks

| # | Status | Description |
|---|--------|-------------|
| 13–22 | ✅ | (cleanup historique) |
| 23 | ⏳ | UI banner "warm-up needed" — moins urgent depuis push `builder_ready` |
| 24 | ✅ | Test progression-swap path for inactive event configs |
| 25 | ⏳ | Add MachinesOfWar Event support to builder (code path séparé `MachinesOfWarEventGameModeSource` avec son DTO) |
| 26–28 | ✅ | (front polish, archive captures, prechargement par faction) |

## Memory entries (CLAUDE)

- `project_tacticus_pc_workflow.md` — workflow stable + pièges PC à ne pas réintroduire
- `project_campaign_builder_resolution.md` — pattern progression-swap, layouts CGMS+CampaignProgression
- `project_matchstate_copy.md`, `project_replay_sim.md`, `project_sim_and_commit_turn1.md`
- `project_ai_plays_player.md`
- `feedback_frida_wedge_after_stop.md` — relaunch needed après stop+reinject

## Pieges majeurs documentés (NE PAS RÉINTRODUIRE)

1. **Heap scans automatiques** → UnityFreezeDetector kill
2. **Broad-hooks sur méthodes UI hot** (Get*/Has*/Is*/Compute*/Try/Find/Update) → cctor cascade crash
3. **Hook permanent sur property getters** appelés par Newtonsoft (`get_gameConfigDto`) → 27k appels/s → frame >960 ms → kill
4. **ctor.onEnter** au lieu de `onLeave` → fields Zenject pas encore injectés
5. **Confondre `_gameConfig`** (GameConfigData wrapper) avec GameConfigDto direct
6. **Sérialisations Newtonsoft synchrones dans onLeave** → bloque le retour de la méthode hookée → freeze visible

## Repo state

```
Branch:  master
HEAD:    e25aefc Tacticus PC port + Campaign Builder (path 2 progression-swap)
Origin:  up to date
Working tree:  clean (probe-* + sources_win/ + dist/ ignored)
```

Build : ✅ `dist/hooks.js` à 110 KB. Host tourne sur :8765.
