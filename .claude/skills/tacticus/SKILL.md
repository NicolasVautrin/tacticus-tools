---
name: tacticus
description: WH40K Tacticus PC hooking — injection Frida locale, campaign builder via progression-swap, capture passive de BattleConfiguration, simulation standalone. Use when working on Tacticus hooks, battle analysis, or game AI.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Edit, Write, Agent
---

# Tacticus — WH40K Hooking & Builder (Windows PC)

## Cible

- **Tacticus PC** : `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\Tacticus.exe` —
  `<HASH>` change à chaque mise à jour du jeu ; le lire, jamais le recopier
  (`ls -d /c/Users/nicolasv/AppData/Local/tacticus/games/*/`, et
  `data/symbols/CURRENT` pour le build contre lequel les symboles sont dumpés)
- Unity **6000.3.13f1** au 2026-08-04, IL2CPP AOT, GameAssembly.dll ~60 MB
  (comme le `<HASH>` : le lire dans `meta.unityVersion` à l'inject, jamais le recopier)
- Frida injection **locale** via `frida.getLocalDevice()` — pas d'`adb`,
  pas de `frida-server`, pas de device

## Repo

`C:/Users/nicolasv/tacticus-tools/`

```
tacticus-tools/
  frida/                   # Monorepo TypeScript actif (hooks + host + front)
    hooks/                 # Script injecté
      il2cpp/              # Primitives IL2CPP
      game/                # Tacticus-specific (runner, match-state, ...)
      features/            # RPCs par feature
        campaign-builder.ts    # path 2 progression-swap (events inactifs)
        mode-source-capture.ts # capture passive battles naturelles
        launch.ts              # standalone runner
        sim/compare/cheat/...
      runtime/             # queue, pumps, diag (log + traceEnter)
      controller.ts main.ts
    host/                  # Express + WebSocket + Frida bridge
    public/                # Front browser (HTML statique servi /view/)
    assets/public/configs/ # BattleConfiguration capturées + générées
    data/                  # symbols.json, gameconfig dumps (gitignored)
    dist/                  # bundles build (gitignored)
  scripts/
    python/build_asset_manifest.py
    ghidra/GhidraDecompileGameAssembly.java
  hooks-legacy/            # one-shots historiques
  sources_win/             # décompilation Ghidra (gitignored)
  STATUS.md                # état d'avancement vivant
```

## Setup / bring-up

1. **Tacticus** : lance via launcher ou directement `Tacticus.exe`. Attends
   le menu principal **pleinement loaded** (animations en boucle).
2. **Host** :
   ```bash
   cd frida && npm run dev   # http://127.0.0.1:8765, front /view/
   ```
   Pas de hot-reload. `npm run build:hooks` à chaque modif TS sous `frida/hooks/`.
3. **INJECT** : ouvre `http://127.0.0.1:8765/view/`, clique INJECT. Le host
   auto-discovery le PID Tacticus (heuristique : `Tacticus_Data/` adjacent
   à l'exe écarte le launcher), attache, charge `dist/hooks.js`.
4. **Amorce** : ouvre une campagne in-game + clique un battle → l'agent
   capture `lastSource` + push `builder_ready` au front → catalog
   auto-rafraîchi.
5. **Build node** : clique une node dans le panel Campaign Builder du front.
   Path 2 progression-swap → BattleConfiguration générée + persistée.

Arrêt host : `curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown` (ou
Ctrl+C). Stop session : front bouton STOP, ou
`curl -s -X POST http://127.0.0.1:8765/api/scripts/{id}/stop`.

## References détaillées

- [hooks.md](references/hooks.md) — modules Frida, composition, conventions
- [rpc-api.md](references/rpc-api.md) — RPCs, format state, events
- [rl-database.md](references/rl-database.md) — schéma Postgres `TACTICUS` (dataset RL : tables, enums, ref tables, espaces d'ids, vues, recettes SQL)

<!-- À (ré)écrire contre le code actuel (drafts d'avril périmés dans
     .claude/worktrees/agent-a0e45617/) : knowledge.md, game-architecture.md,
     decompilation.md, ai-engine-audit.md, frida-host.md. -->


## API HTTP du host

| Methode | Route | Description |
|---------|-------|-------------|
| GET | `/api/admin/status` | Tacticus running? launcher? game PID + path? session info |
| POST | `/api/admin/inject` | Injection (body vide = auto-discovery) |
| GET | `/api/sessions` | Sessions Frida actives |
| POST | `/api/scripts/:id/stop` | Stop session (cleanup graceful) |
| POST | `/api/scripts/:id/rpc` | RPC synchrone — `{method, args, timeout?}` |
| GET | `/api/configs` | Liste captures |
| GET | `/api/configs/:id` | JSON capture |
| DELETE | `/api/configs/:id` | Supprimer capture |
| GET | `/api/campaigns/builder-status` | État builder |
| POST | `/api/campaigns/catalog/refresh` | Force re-dump catalog (heap scan autorisé) |
| POST | `/api/campaigns/build` | `{campaignType, campaignId, locationIndex}` → BattleConfiguration JSON |
| GET | `/view/` | Frontend |
| GET | `/assets/*` | PNG, manifest, configs statiques |
| POST | `/api/_dev/shutdown` | Arrêt graceful |

WebSocket `ws://127.0.0.1:8765/ws/run/:id` (reconnect via `?last_event_id=N`).
Messages push : `captured_config`, `battle_event`, `builder_ready`, `diag`, `trace`.

## Architecture campaign builder (path 2)

Le path 2 mute progression-swap est l'unique path validé sur Tacticus PC :

1. Ctor `CampaignGameModeSource..ctor` (onLeave) → capture `lastSource`
2. `lastSource._gameConfig` (offset 0x90) = `GameConfigData` wrapper.
   Unwrap via `GameConfigData.get_gameConfigDto()` à la demande →
   vraie `GameConfigDto`
3. `GameConfigDto.battles.campaigns` → catalog complet (Standard, Mirror,
   Elite, Event types)
4. Pour build : sur `lastSource._campaignProgression` (offset +0x20) :
   - save+swap `_campaignType` (+0x18, S32), `_campaignId` (+0x28, string),
     `_battlesConfigCampaigns` (+0x88, List)
   - swap `_currentMatch` etc. sur source
   - per-faction amorce via `UnitProgression.GetUnit` sur enemy units
   - `LoadBattle(true)` → BattleConfiguration
   - Restore dans `finally`

Layouts validés sur Tacticus 1.38.94 :
```
CampaignGameModeSource :
  +0x20 _campaignProgression
  +0x68 _currentCampaignId
  +0x70 _currentLocationIndex
  +0x78 _currentMatch
  +0x80 _currentBattle
  +0x90 _gameConfig (= GameConfigData wrapper)

CampaignProgression :
  +0x18 _campaignType  (CampaignType enum, 4 bytes)
  +0x28 _campaignId    (string)
  +0x88 _battlesConfigCampaigns (List<CampaignConfigDto>)
```

## Push-based UI sync

L'agent émit `send({ t: "builder_ready", via: "ctor" | "LoadBattle" })`
quand `lastSource` passe de null à assigné. Le front (`ws.js` →
`registerWsHandler`) écoute et déclenche un `refresh(true)` (idempotent
via `builderReadyConsumed`). Plus de polling de `builderStatus` pour le
amorce — le polling défensif reste pour le cas où l'utilisateur HR le
front après amorce déjà fait (rejoue depuis le ring buffer WS).

## Capture passive

`mode-source-capture.ts` hook 19 `*GameModeSource.LoadBattle` (Campaign,
PvpStarterSeason, MachinesOfWarEvent, Friendly, Sandbox, Endless, etc.).
Sur chaque battle naturelle :
1. Lecture des identity fields (campaignId, locationIndex) en synchrone
2. **Defer** la sérialisation Newtonsoft (heavy : 540 KB sur 200–500 ms)
   via `gcRoot.add(retval)` + `queueOnMainThread(...)` → exécute la
   sérialisation au prochain tick du main pump
3. Émet `send({ t: "captured_config", ... })` async — le host route et
   persiste sur disque

## Pièges majeurs (NE PAS RÉINTRODUIRE)

- **Heap scans automatiques** (`Process.enumerateRanges`, `Memory.scan`) :
  Frida suspend les threads cible ~10 s. UnityFreezeDetector kill. Heap
  scans gated par `allowHeapScan: true` (=  bouton ↻ explicite uniquement).
- **Broad-hooks sur méthodes UI hot** (UnitProgression.Get*/Has*/Is*/
  Compute*/Try/Find/Update, BattleConfigBuilder broad, RandomGenerator
  broad) : trampoline overhead × hot path = destabilisation cctor cascade.
- **Hook permanent sur property getters** appelés par sérialisations
  Newtonsoft (`GameConfigData.get_gameConfigDto`) : ~27 000 appels/s →
  frame >960 ms → crash. Préférer un appel à la demande.
- **Hooks metadata diag** sur `FUN_180002560` (RVA 0x2560) ou hot path
  IL2CPP class init : trampoline sur des fonctions appelées des milliers
  de fois.
- **ctor capture en `onEnter`** : les fields Zenject ne sont pas encore
  injectés. Capturer en `onLeave`.
- **`findMethod(".ctor")` quand plusieurs overloads** : retourne un
  overload arbitraire → crash. Utiliser `findCtorByParamCount(klass, n)`.

## Ajouter une feature

```ts
// frida/hooks/features/foo.ts
import { Ctx } from "../controller.js";
import { queueOnMainThread } from "../runtime/queue.js";

export function register(ctx: Ctx): void {
    ctx.rpc.myRpc = () => queueOnMainThread(() => ({ ok: true }));
}
```

Puis dans `controller.ts` : ajouter `import * as foo from "./features/foo.js";`
et l'inclure dans le tableau de `wireRpc`. Rebuild.

## Standalone runner (phase 2 — simulation)

`launch.ts` + `runner.ts` exposent :
- `initRunner(configJson)` → construit un `IdunRunner` isolé via
  `JsonConvert.DeserializeObject` + 2-arg ctor + Initialize(seed)
- `applyAddUnit(runnerId, unitId, playerId, col, row)` → `runner.Apply`
- `startBattle(runnerId)` → `runner.StartMatch`
- `sim`, `commit`, `simAndCommit`, `compareStandalone` (cf. memory
  `project_sim_and_commit_turn1.md`, `project_replay_sim.md`)

Le standalone runner partage le PRNG seed avec live (depuis
`ReplayRecorder._replay.RngSeed`) → même `mt[]` → décisions IA
déterministes.

## Workflow RL — runner isolé

Pour entraîner un agent RL / valider le moteur **sans toucher au battle in-game**, on monte un
runner isolé depuis une **seed BC sur disque** via `rl_duel build`, déployé et pilotable.

> **Le lancement de runner est centralisé dans `references/runner.md`**
> (`rl_duel build` + options, choix de board `--board`/`--board-pool` + `board.py`, discipline
> runner) — s'y référer, ne pas dupliquer ici.

Rappel minimal :
- `python rl_duel.py build --seed <s> --board <id> --state-file <propre> [--p-units/--a-units, ...]`
  puis `view/act/play` ou `engine_validate.py --runner <id>`. **`--board` OBLIGATOIRE** (ex. MC1_67 ;
  cf. runner.md). Si `data/boards/` ou `data/seed-bc.json` manquent (purge de `data/`) → `python
  dump_boards.py` régénère. Discipline : state-file propre, `--runner` explicite, dispose tes runners
  (coexistence, cap MAX_RUNNERS).

**Offsets validés (Tacticus 1.39.40)** :
```
BattleConfiguration :
  +0x10 Id (string)
  +0x28 SpawnPointSetIndex (int)
  +0x40 PredefinedUnits (List<PredefinedUnits>)
  +0x68 Board (BattleConfigBoardConfiguration)
  +0x80 Units (List<UnitConfiguration> — PLAYER roster, pas AI enemies)
  +0x88 Tiles (List<BattleConfigTileConfiguration> — palette filtrée par node)
  +0xC0 StartingActions (List<IInputMessage>, JsonIgnore — built at Initialize)
  # neuf booléens CONSÉCUTIFS depuis +0xE0 — cette ligne a porté « +0xE7 RandomizeAiInput »,
  # faux d'un octet (#10022-r1). Table complète + ancres nommées : frida/hooks/features/battle-config.ts
  +0xE0 UseGroupForAddUnit  … +0xE6 DisableActiveAbilitiesOnAI
  +0xE7 DisableRandomness (bool)
  +0xE8 RandomizeAiInput (bool)

PredefinedUnits (per-player squad) :
  +0x10 Id (PlayerId enum int — 12 = AI standard)
  +0x18 Units (List<PredefinedUnit>)

PredefinedUnit :
  +0x10 UnitId (string, "id:level" format)
  +0x18 RemainingHealth (Nullable<int>)
  +0x20 MaxHealth (Nullable<int>)

SpawnPointGroupConfiguration :
  +0x10 TeamWithPlayerIndex (int)
  +0x18 SpawnPoints (List<SpawnPointConfiguration>)

SpawnPointConfiguration : BattleConfigPosition
  +0x10 Column (int)
  +0x14 Row (int)
```

**Modules concernés** :
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/battle-config.ts)
  inspect / patch / normalisation BC (lancement de runner : cf. `references/runner.md`)
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/observe.ts)
  observeBattle (live runner ou registry par runnerId)
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/auto-boot.ts)
  autoBootExtraire (avec retreat optionnel)

## Pipeline d'assets

`scripts/python/build_asset_manifest.py` (UnityPy 1.25, Unity 6000.3.8f1) :
- Extrait portraits `ui_avatar_<assetNaming>` (heroes 256×256) +
  atlas-packed `ui_image_RoundPortrait_<assetNaming>` (NPCs 128×128)
- Extrait backgrounds `<BoardId>_Visual` + MonoBehaviour Config_Visual
  (`PlayableMinCol/MaxCol/MinRow/MaxRow`)
- Produit `frida/assets/public/manifest.json` : `{ units, boards, boardVisuals }`

Volumétrie : 331 portraits (13 MB), 756 backgrounds 1024×1024 (930 MB).

## Frontend

`frida/public/` (statique, pas de build) :
- 3 colonnes : configs/captures | board | roster+placements
- Builder hiérarchique CampaignType → Campaign → Node
- Hex pointy-top odd-r offset overlay sur board PNG
- Push handlers via `registerWsHandler(t, fn)` (`builder_ready`, etc.)

Ouverture : `http://127.0.0.1:8765/view/`.

## Mémoire (memory/)

- `project_tacticus_pc_workflow.md` — workflow stable + pièges
- `project_campaign_builder_resolution.md` — pattern progression-swap
- `project_matchstate_copy.md` — Copy() vs services holding their own ref
- `project_replay_sim.md` — ReplayRunner abandon, IdunRunner standalone
- `project_sim_and_commit_turn1.md` — sim+commit validé bout-en-bout
- `project_ai_plays_player.md` — CheatRunAIMessage
- `feedback_frida_wedge_after_stop.md` — relaunch Tacticus après stop
