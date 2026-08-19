# frida/ — Tacticus PC hooking (TypeScript monorepo)

Script Frida injecté + serveur Node qui pilote les sessions + frontend
browser. Cible : **Tacticus Windows PC** (Unity 6 IL2CPP, GameAssembly.dll).

## Layout

```
frida/
├── package.json                  # scripts + deps
├── tsconfig.{base,hooks,host}.json
├── dist/                         # outputs (gitignored)
│   └── hooks.js                  # bundle injectable
├── hooks/                        # script injecté (frida-compile bundle)
│   ├── main.ts                   # entry — il2cpp base, pumps, wireRpc
│   ├── controller.ts             # aggregate features → rpc.exports
│   ├── il2cpp/                   # primitives IL2CPP (stateless)
│   │   ├── helpers.ts            # findClass, findMethod, hook(), getFieldOffset
│   │   ├── invoke.ts             # invokeMethod, createManagedString
│   │   ├── serializer.ts         # JsonConvert wrapper
│   │   ├── gc-root.ts            # ArrayList-based pin
│   │   ├── mt.ts                 # MersenneTwister snapshot
│   │   └── enum-dump.ts
│   ├── game/                     # Tacticus-specific
│   │   ├── runner.ts             # IdunRunner ctor + offsets
│   │   ├── match-state.ts        # entityCensus, digestState
│   │   ├── ai-control.ts         # AiControl Apply* hooks
│   │   ├── apply-stack.ts        # StreamDispatcher event correlation
│   │   ├── recorder.ts           # install() + bootstrap preamble
│   │   └── state.ts              # shared mutable state
│   ├── features/
│   │   ├── campaign-builder.ts   # progression-swap path 2 (events inactifs)
│   │   ├── mode-source-capture.ts# capture passive des LoadBattle naturels
│   │   ├── launch.ts             # standalone runner (initRunner, applyAddUnit, startBattle)
│   │   ├── sim.ts compare.ts cheat.ts  # phase 2 — simulation
│   │   ├── status.ts config-io.ts unit-asset-map.ts
│   │   ├── unit-visual-resolve.ts# IdunUniverse capture + dump unit visuals
│   │   ├── movement-trace.ts     # AI debugging (désactivé par défaut)
│   │   └── introspect.ts
│   └── runtime/
│       ├── queue.ts              # queueOnMainThread (drained par les pumps)
│       ├── main-pump.ts          # Interceptor.replace IdunGameViews.Update + UnityFreezeDetector.Update
│       ├── crash-logger.ts       # VEH (désactivé par défaut)
│       └── diag.ts               # log() + traceEnter() (push via send())
├── host/                         # Node Express + WebSocket + Frida bridge
│   ├── index.ts                  # entry, listen :8765
│   ├── router.ts                 # routes /api/*
│   ├── sessions.ts               # attach, load, rpc, lifecycle
│   ├── admin.ts                  # auto-discovery PID Tacticus + injectBundle
│   ├── ws.ts                     # /ws/run/:id stream + ring buffer
│   ├── config-store.ts           # persist captured BattleConfiguration
│   ├── battle-store.ts           # battle_event store
│   └── meta-sync.ts              # syncEnums, syncCampaignCatalog
└── public/                       # Frontend browser (statique, servi /view/)
    ├── index.html style.css app.js
    └── src/
        ├── api.js ws.js          # HTTP + WebSocket client
        ├── board.js placements.js roster.js
        ├── configs.js            # archive captures
        ├── campaign-builder.js   # builder hiérarchique + push handler
        ├── runners.js launchers.js
        └── admin.js status.js collapsible.js
```

## Build & run

```bash
npm install
npm run build:hooks    # → dist/hooks.js (~110 KB bundle injectable)
npm run dev            # host sur :8765 (tsx, sans hot-reload)
```

Hot-reload côté host **interdit** : casserait les sessions Frida actives
(cf. CLAUDE.md).

## Injection

L'injection se fait via le **frontend** (bouton INJECT). Le host gère
l'auto-discovery du PID Tacticus (heuristique : exe accompagné d'un dossier
`Tacticus_Data/` adjacent), attache via `frida.getLocalDevice()`, charge le
bundle `dist/hooks.js`. Pas de ligne de commande.

API direct (hors UI) :
```bash
curl -s -X POST http://127.0.0.1:8765/api/admin/inject -H "Content-Type: application/json" -d '{}'
```

Body `{}` = auto-discovery. Body `{ "pid": 12345 }` = forçage explicite.

## Workflow campaign builder

1. Tacticus lancé, menu loaded
2. INJECT depuis le front
3. **Cliquer un battle in-game** (amorce) → l'agent capture `lastSource` +
   `lastUnitProgression`, push `builder_ready` au front
4. Le front auto-rafraîchit le catalog (POST `/api/campaigns/catalog/refresh`)
   → côté agent, le `_gameConfig` du source est unwrappé via
   `GameConfigData.get_gameConfigDto()` (le field est typé IGameConfigData,
   le runtime concrete est un wrapper `GameConfigData`)
5. L'utilisateur clique une node de build → progression-swap (mute path 2) :
   - Save+swap `_campaignType` (+0x18), `_campaignId` (+0x28),
     `_battlesConfigCampaigns` (+0x88) sur la live `CampaignProgression`
   - Per-faction amorce via `UnitProgression.GetUnit` sur enemy units
   - `LoadBattle(true)` → BattleConfiguration générée
   - Restore tout dans `finally`

## Ajouter une feature

1. Créer `hooks/features/foo.ts` :
```ts
import { Ctx } from "../controller.js";
import { queueOnMainThread } from "../runtime/queue.js";

export function register(ctx: Ctx): void {
    ctx.rpc.myRpc = () => queueOnMainThread(() => ({ ok: true }));
}
```

2. Ajouter dans `controller.ts` :
```ts
import * as foo from "./features/foo.js";
// puis dans wireRpc :
[..., foo].forEach((f) => f.register(ctx));
```

3. `npm run build:hooks` → réinjecter (front).

## RPCs principaux

| RPC | Rôle |
|---|---|
| `dumpCampaignCatalog({ allowHeapScan? })` | Catalog des campagnes (utilise `lastSource` ou heap scan si opt-in) |
| `buildCampaignConfig({ campaignType, campaignId, locationIndex })` | Génère BattleConfiguration via path 2 mute progression-swap |
| `campaignBuilderStatus` | Cheap, polled — `hasGameConfig`, `hasInstance`, `hasUnitProgression` |
| `initRunner(configJson)` | Construit standalone runner depuis JSON désérialisé |
| `applyAddUnit({ runnerId, unitId, playerId, col, row })` | Place unit sur standalone |
| `startBattle({ runnerId })` | StartMatch sur standalone |
| `cheatRunAi` | CheatRunAIMessage direct sur live |
| `sim`, `commit`, `simAndCommit`, `compareStandalone` | Simulation phase 2 |
| `getGameVersion`, `getUnitAssetMap`, `dumpEnums` | Métadonnées |

## Règles clés (gotchas)

- **`Interceptor.replace` sur les pumps Update** (et pas `attach`) : `attach`
  ajoute un recursion guard qui supprime les hooks fired pendant le drain.
  Tous les RPC IL2CPP doivent fire correctement même en cours de drain.
- **`findCtorByParamCount(klass, n)`** plutôt que `findMethod(".ctor")` quand
  plusieurs overloads coexistent (sinon access violation).
- **`gcRoot.add(x)`** sur tout objet IL2CPP qu'on garde entre RPC apply et
  commit (ArrayList-based, retry sur ArrayTypeMismatchException).
- **Pas de heap scan automatique** : Frida suspend les threads cible
  (~10 s sur GameAssembly.dll). UnityFreezeDetector tue le process. Heap
  scans uniquement sur opt-in explicite (`allowHeapScan: true`).
- **Pas de broad-hooks sur méthodes UI hot** (`Get*/Has*/Is*` etc.) : crash
  cctor cascade pendant les transitions de scène (live event popup, etc.).
- **Pas de hook permanent sur les property getters** appelés par les
  sérialisations Newtonsoft du jeu (ex. `get_gameConfigDto`) : 27 000 appels/s
  → frame >960 ms → kill.
- **ctor capture en `onLeave`** (pas `onEnter`) : à `onEnter` les fields
  Zenject ne sont pas encore injectés.
- **Push WebSocket** plutôt que polling : l'agent émit des messages typés
  (`builder_ready`, `captured_config`, ...) que le host re-broadcast aux
  subscribers.
