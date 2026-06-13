# Hooks — architecture & conventions (frida/hooks/)

Script Frida injecté dans Tacticus (Unity 6 IL2CPP), bundlé par `frida-compile`
(`npm run build:hooks` → `frida/dist/hooks.js`). Injecté via le host
(`POST /api/admin/inject`), pas en CLI. Le host (`frida/host/`) est documenté
ailleurs ; ici = le script injecté. Total ~26k LOC.

## Boot & câblage

`hooks/main.ts` est le point d'entrée :

```
main.ts
  ├─ import "./game/runner.js" / "./game/match-state.js" / "./game/ai-control.js"
  ├─ installMainPump / installMenuPump   (runtime/main-pump : pump Unity pour queueOnMainThread)
  ├─ installCrashLogger / installExceptionTracer  (runtime/)
  └─ wireRpc(ctx)                          (controller.ts)
```

`controller.ts` définit `Ctx = { rpc: Record<string, (...args)=>unknown> }` et
`wireRpc(ctx)` appelle le `register(ctx)` de **chaque feature module** (+ une
nuée de modules `scratch/*` d'introspection one-shot). Un module ajoute ses
handlers sur `ctx.rpc.<nom>` → exposés au host (voir [rpc-api.md](rpc-api.md)).

## Dossiers

- `hooks/game/` — modèle runtime du combat :
  - `runner.ts` — `buildRunner(config)` (sidecars NullLogger/TimeSource/…,
    Initialize), offsets runner, `IdunRunner.Apply`/`StartMatch`.
  - `match-state.ts` — **projecteur canonique** `projectMatchState(statePtr)` :
    `forEachEntity`/`forEachComponent` (réflexion par classe, **pas d'offsets
    devinés**), `EntityType` enum (Tile=0, Unit=1, Match=2, Effect=3, Player=4,
    UnitFoot=5, Machine=6, MachinePlatform=7, EnvironmentAbility=8), résout
    UnitFoot→Tile (position) et Player→TeamId. Produit `units[]` + `mows[]`.
  - `ai-control.ts` — `AiControl.ApplyAiMessage`/`ApplyHumanAiMessage`.
  - `recorder.ts`, `apply-stack.ts` — capture des `Apply` + StreamDispatcher
    events par fenêtre d'apply.
  - `state.ts` — état partagé agent (liveRunner, watchedRunners, applySeq…).
  - `runner-registry.ts` — registre des runners isolés (`getRunner(id)`).
- `hooks/features/` — un fichier par feature, chacun `export register(ctx)`.
  Familles : runner/launch (`launch.ts`, `cheat.ts`), sim/mirror
  (`sim-engine.ts`, `sim.ts`, `compare.ts`), normalisation
  (`normalize-bc.ts`), capture live (`campaign-builder.ts`, `battle-config.ts`,
  `mode-source-capture.ts`, `mow-builder.ts`, `dump-boards.ts`,
  `dump-pvp-boards.ts`), observation (`observe.ts`), AI trace (`ai-trace.ts`,
  `ai-utility-trace.ts`, `message-trace.ts`, `bucket-audit.ts`,
  `dispatch-observe.ts`, `move-options.ts`, `movement-trace.ts`,
  `board-trace.ts`, `winner-capture.ts`, `whatif-trigger.ts`), warmup/boot
  (`warmup-singletons.ts`, `auto-boot.ts`), résolution visuels
  (`unit-visual-resolve.ts`, `unit-asset-map.ts`), diag bas niveau
  (`crash-trap.ts`, `init-trace.ts`, `introspect.ts`, `status.ts`,
  `config-io.ts`).
- `hooks/scratch/` — modules d'introspection RE jetables (dump offsets/méthodes/
  enums/formules). Lecture humaine uniquement, jamais une dépendance de prod.
- `hooks/il2cpp/` — `helpers.ts` : `findClassAnywhere(ns,cls)`,
  `findMethod(klass,name)`, `getFieldOffset`, `class_get_name`,
  `readIl2cppString`, `invokeMethod`, … (API IL2CPP C wrappée).
- `hooks/runtime/` — pump main thread (`queueOnMainThread`), crash logger,
  exception tracer, diag log.

## Conventions (impératives)

- **Résolution runtime, AUCUNE RVA hardcodée** : `findClassAnywhere` →
  `findMethod` → `Interceptor.attach`. Une RVA copiée d'un dump devient
  invalide au prochain changement de hash de build (cf. CLAUDE.md).
- **Pas de heap scan auto** (`Process.enumerateRanges`/`Memory.scan`) : Frida
  suspend les threads pendant le scan IL2CPP → UnityFreezeDetector tue le
  process. Gated par `allowHeapScan` sur action user explicite uniquement.
- **Pas de broad-hook sur méthodes UI hot** ni sur property getters appelés par
  les sérialisations Newtonsoft (ex. `GameConfigData.get_gameConfigDto`,
  27k appels/s → frame >960 ms → crash).
- **Capture ctor en `onLeave`** (l'objet est construit), pas `onEnter`.
- **Tout accès MatchState/IL2CPP via `queueOnMainThread`** (jamais hors pump).
- **Features diagnostiques auto-armées au `register`** (pas d'étape « arm »
  manuelle avant le scénario).
- **`Interceptor.replace` actif** (sim-engine mirror) : cleanup gracieux
  obligatoire avant stop, sinon crash jeu. Ne pas restart le host en plein
  battle.
- Splitter un module > ~1000 lignes **seulement sur une couture nette**
  (sous-features indépendantes), pas sur la taille seule : `sim-engine.ts` est
  gros mais cohérent (état + lifecycle partagés) → reste monolithique.

## Build / cycle

```bash
cd frida && npm run build:hooks      # → dist/hooks.js
curl -X POST http://127.0.0.1:8765/api/admin/inject -d '{}'   # (ré)injecte
```

La (ré)injection **réinitialise l'état agent** (liveRunner=null, caches Frida
des MethodInfo* perdus) → re-`warmupGameSingletons` requis, et l'utilisateur
doit re-cliquer une battle de campagne pour ré-armer les captures live.
