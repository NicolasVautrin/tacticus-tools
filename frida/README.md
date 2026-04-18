# frida/ — Tacticus hooking (TypeScript monorepo)

Script Frida injecté + serveur Node qui pilote les sessions. Unifié, typé,
bundlé par `frida-compile`.

## Layout

```
frida/
├── package.json              # scripts + deps
├── tsconfig.base.json        # options communs
├── tsconfig.hooks.json       # noEmit, types frida-gum (pour lint)
├── tsconfig.host.json        # output dist/host/
├── dist/                     # outputs (gitignored)
│   ├── hooks.js              # bundle injectable
│   └── host/                 # compiled node server
└── src/
    ├── hooks/                # script injecté
    │   ├── main.ts           # entry — boot, install, wire controller
    │   ├── controller.ts     # aggregate features → rpc.exports
    │   ├── il2cpp/           # primitives IL2CPP (stateless)
    │   │   ├── helpers.ts    # findClass, findMethod, getFieldOffset, …
    │   │   ├── invoke.ts     # invokeMethod (+ managed exception)
    │   │   ├── serializer.ts # Newtonsoft JsonConvert wrapper
    │   │   ├── gc-root.ts    # anti-GC via System.Collections.ArrayList
    │   │   └── mt.ts         # MersenneTwister snapshot/restore
    │   ├── game/             # Tacticus-specific
    │   │   ├── runner.ts     # IdunRunner + buildStandaloneRunner
    │   │   ├── match-state.ts# entityCensus, readTurn, digestState
    │   │   ├── ai-control.ts # AiControl + apply methods + CheatRunAI
    │   │   ├── apply-stack.ts# applyStack + StreamDispatcher hooks
    │   │   ├── recorder.ts   # install() + bootstrap preamble + log
    │   │   └── state.ts      # shared mutable state
    │   ├── features/         # RPCs par feature
    │   │   ├── status.ts     # info, summary, dump, clear, battleStatus, forceInstall
    │   │   ├── sim.ts        # sim, commit, simAndCommit
    │   │   ├── compare.ts    # compareStandalone (dumps + event traces)
    │   │   └── cheat.ts      # cheatRunAi
    │   └── runtime/
    │       ├── queue.ts      # queueOnMainThread
    │       └── main-pump.ts  # Interceptor.replace sur IdunGameViews.Update
    └── host/                 # serveur Node (Frida bridge)
        ├── index.ts          # entry — Express + WebSocket
        ├── router.ts         # routes /api/*
        ├── sessions.ts       # attach, load, rpc, cleanup
        ├── logger.ts         # jsonl writer per session
        └── ws.ts             # WebSocket streaming
```

## Build & run

```bash
cd frida
npm install
npm run build:hooks    # → dist/hooks.js (bundle injectable)
npm run dev            # host sur :8765 (tsx, hot-reload)
# ou :
npm run build          # hooks + host
```

## Injection

```bash
PID=$(adb -s f32224e7 shell "ps -A | grep -i tacticus" | awk '{print $2}')
node -e "
const fs = require('fs');
const source = fs.readFileSync('frida/dist/hooks.js', 'utf-8');
fs.writeFileSync('/tmp/inject.json', JSON.stringify({
    serial: 'f32224e7', mode: 'attach', pid: $PID, source,
    log_dir: 'logs',
}));
"
curl -s -X POST http://127.0.0.1:8765/api/scripts/run \
    -H "Content-Type: application/json" -d @/tmp/inject.json
```

## Ajouter une feature

1. Créer `src/hooks/features/foo.ts` :
```ts
import { Ctx } from "../controller.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { state } from "../game/state.js";

export function register(ctx: Ctx): void {
    ctx.rpc.myRpc = () => queueOnMainThread(() => {
        // ...
        return { ok: true };
    });
}
```

2. Ajouter dans `controller.ts` :
```ts
import * as foo from "./features/foo.js";
// puis dans wireRpc :
[status, sim, compare, cheat, foo].forEach((f) => f.register(ctx));
```

3. `npm run build:hooks` → réinjecter.

## RPCs disponibles

| RPC | Rôle |
|---|---|
| `ping` | health |
| `info` | runner / listeners / gcRoot state |
| `battleStatus` | stage + currentTurnPlayer + unitsAlive |
| `summary` | log counts + head/tail |
| `dump` | full log |
| `clear` | reset log |
| `forceInstall` | re-attacher les hooks live |
| `sim` | standalone + catch-up + CheatRunAI(standalone) → simId |
| `commit(simId)` | apply decisions sur live AiControl |
| `simAndCommit` | wrapper sim + commit |
| `compareStandalone` | state digests + dumps + event traces via `send()` |
| `cheatRunAi` | CheatRunAIMessage direct sur live |

## Règles clés (gotchas)

- **`findCtorByParamCount(runnerClass, 2)`** — PAS `findMethod(".ctor")` qui
  retourne un overload arbitraire → crash access violation
- **Dispatch sur standalone** : TOUT via `runner.Apply`, jamais
  `AiControl.ApplyAiMessage` hors contexte CheatRunAI (abort)
- **Skip `CheatRunAIMessage`** dans le catch-up — ses sub-messages sont
  déjà dans le log, re-fire double-appliquerait
- **GC rooting** (`gcRoot.add`) obligatoire sur chaque IL2CPP object
  qu'on garde entre apply et commit
- **Install deferred via `setTimeout(0)`** — `Interceptor.attach` depuis
  callback `Interceptor.replace` échoue silencieusement
