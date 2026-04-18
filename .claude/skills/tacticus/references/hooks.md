# Hooks Frida — structure & conventions

## Codebase active

`frida/src/hooks/` — bundlée par `frida-compile` vers `frida/dist/hooks.js`.

### Arborescence

```
src/hooks/
├── main.ts              # entrypoint : boot → install → wire controller
├── controller.ts        # dispatcher : features → rpc.exports
│
├── il2cpp/              # primitives IL2CPP (stateless, réutilisables)
│   ├── helpers.ts       # findClass, findMethod, findCtorByParamCount, getFieldOffset,
│   │                    # readIl2cppString, s, hook, readMsgClass, getStack
│   ├── invoke.ts        # invokeMethod (+ managed exception unwind), createObject
│   ├── serializer.ts    # wrapper Newtonsoft JsonConvert.SerializeObject
│   ├── gc-root.ts       # anti-GC via System.Collections.ArrayList
│   └── mt.ts            # MersenneTwister snapshot / restore
│
├── game/                # Tacticus-specific (IdunBattle)
│   ├── runner.ts        # IdunRunner class + offsets + buildStandaloneRunner
│   ├── match-state.ts   # entityCensus, readTurn, digestState, EntityType enum
│   ├── ai-control.ts    # AiControl + Apply*AiMessage + CheatRunAIMessage
│   ├── apply-stack.ts   # applyStack + StreamDispatcher hooks (events)
│   ├── recorder.ts      # install() + bootstrap preamble + log[] + ensureInstalled
│   └── state.ts         # shared mutable state (runnerInstance, log, simCache, pending)
│
├── features/            # chaque fichier = export register(ctx: Ctx): void
│   ├── status.ts        # info, summary, dump, clear, battleStatus, forceInstall
│   ├── sim.ts           # sim, commit, simAndCommit + simCache
│   ├── compare.ts       # compareStandalone (dumps + event traces via send())
│   └── cheat.ts         # cheatRunAi (CheatRunAI direct sur live)
│
└── runtime/
    ├── queue.ts         # queueOnMainThread + pending[]
    └── main-pump.ts     # Interceptor.replace sur IdunGameViews.Update
```

## Conventions

### Feature module

Chaque feature exporte `register(ctx: Ctx)` :
```ts
import { Ctx } from "../controller.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { state } from "../game/state.js";

export function register(ctx: Ctx): void {
    ctx.rpc.myFeature = (arg1: number) => queueOnMainThread(() => {
        // main-thread work here — IL2CPP calls safe
        return { ok: true };
    });
}
```

Puis dans `controller.ts` : importer et ajouter dans `wireRpc`.

### Shared state

`game/state.ts` exporte un objet `state` avec les refs runtime (runnerInstance,
log, simCache, etc.). Les modules le mutent directement — pas de setters.

### Main-thread discipline

TOUS les IL2CPP calls (`invokeMethod`, `il2cpp_object_new`) doivent tourner
sur le main thread Unity. Wrapper les RPCs dans `queueOnMainThread(() => ...)`.
Le `runtime/main-pump.ts` draine la queue dans `IdunGameViews.Update`.

### Hooks d'install

- `StreamDispatcher.Action` / `StartGroup` : attachés UNE FOIS au boot
  (via `installStreamHooks()` dans main.ts)
- `runner.Apply`, `AiControl.ApplyAiMessage`, `ApplyHumanAiMessage` :
  attachés dans `recorder.install()`, identity-filtered par runner +
  aiControl snapshot, ré-installés à chaque nouveau runner
- Le main-pump détecte le switch de runner et déclenche install() via
  `setTimeout(0)` (Interceptor.attach depuis callback Interceptor.replace
  échoue silencieusement)

## Règles (pièges résolus)

- **`findCtorByParamCount(klass, 2)`** au lieu de `findMethod(".ctor")` —
  les classes avec plusieurs ctors → crash access violation sinon
- **Dispatch standalone via `runner.Apply` uniquement** — `AiControl.ApplyAiMessage`
  hors contexte CheatRunAI → `abort was called`
- **Skip `CheatRunAIMessage`** dans le catch-up — ses sub-messages sont déjà
  dans le log, re-fire double-applique
- **`gcRoot.add(obj)`** obligatoire sur chaque IL2CPP object gardé entre
  apply et commit (sinon GC Unity le collecte en quelques secondes)
- **Exceptions managées** : `invokeMethod` les déballe avec Message + StackTrace

## Legacy (`hooks-legacy/`)

Ancien répertoire, toujours utilisé pour :
- One-shots autonomes (`_oneshot/dump-*`, probes) — producteurs des `data/*.json`
- `autoplay/pick-next-*.js` — à porter quand on fera le tree exploration

Voir `hooks-legacy/README.md` pour la classification complète
(encore-utilisé / à-porter / obsolete).