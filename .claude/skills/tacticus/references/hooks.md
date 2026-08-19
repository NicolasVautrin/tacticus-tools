# Hooks — architecture & conventions (frida/hooks/)

Script Frida injecté dans Tacticus (Unity 6 IL2CPP), bundlé par `frida-compile`
(`npm run build:hooks` → `frida/dist/hooks.js`). Injecté via le host
(`POST /api/admin/inject`), pas en CLI. Le host (`frida/host/`) est documenté
ailleurs ; ici = le script injecté.

**Synchronisé avec le code le 2026-07-02** (carte des dossiers/modules vérifiée
contre `frida/hooks/`). La liste exhaustive des RPC exposés vit dans
[rpc-api.md](rpc-api.md).

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
handlers sur `ctx.rpc.<nom>` → exposés au host. **Ordre = dernier gagne** : un
nom réenregistré par un module câblé plus tard écrase (ex. `battleStatus` et
`dumpEntityComponents` d'`ai-step` écrasent les homonymes de `status.ts`/
`observe.ts`).

## Dossiers

- `hooks/game/` — modèle runtime du combat :
  - `runner.ts` — `buildRunner(config)` (sidecars NullLogger/TimeSource/…,
    Initialize), offsets runner, `IdunRunner.Apply`/`StartMatch`.
  - `match-state.ts` — **projecteur canonique** `projectMatchState(statePtr)` :
    `forEachEntity`/`forEachComponent` (réflexion par classe, **pas d'offsets
    devinés**), `EntityType` enum (Tile=0…EnvironmentAbility=8), résout
    UnitFoot→Tile (position) et Player→TeamId ; `readBattleStatus`. Produit
    `units[]` + `mows[]`.
  - `effects.ts` — `readEffectsByUnit`/`readEffectsByTile`/`readRoundCapClock`
    (EffectsOwnedComponent → EffectComponent, filtré IsActive).
  - `ai-control.ts` — `ApplyAiMessage`/`ApplyHumanAiMessage`, `CheatRunAIMessage`.
  - `recorder.ts`, `apply-stack.ts` — capture des `Apply` + StreamDispatcher
    events par fenêtre d'apply.
  - `state.ts` — état partagé agent (liveRunner, watchedRunners, applySeq…).
  - `runner-registry.ts` — registre des runners isolés (`getRunner(id)`).
- `hooks/features/` — un fichier (ou sous-dossier) par feature, chacun
  `export register(ctx)`. Familles :
  - **runner / launch** : `launch.ts` (initRunner/initAndStart/dispose),
    `cheat.ts` (cheatRunAi/autoPlayRunner), `auto-boot.ts`, `auto-boot.ts`.
  - **décision & action (oracle live)** : `ai-step/` — `rpc-view.ts`
    (decisionView, combatSnapshot, tileMeta, boardGraph, pathDistToEnemies,
    aiMovableTiles, aiAttackRank, abilityTargets, abilityReason, aiPredict,
    exposureView, applyAction, battleStatus, dumpRng), `rpc-drive.ts`
    (aiStepDryRun/aiDryRunAllUnits/aiPlayByUnit/aiPlayOrdered), `projection.ts`
    (computeAttackPlans/DangerZone/Exposure, projectUnitsFull/MowsFull),
    `internals.ts` (résolution de méthodes/offsets partagée).
  - **capture live** : `campaign-builder.ts`, `battle-config.ts`
    (buildPatchedRunner/patch BC), `mode-source-capture.ts`, `mow-builder.ts`,
    `dump-boards.ts`, `dump-pvp-boards.ts`, `normalize-bc.ts` (+ sous-dossier
    `normalize-bc/` : live-bc, formula, items-catalog, json-build, debug-rpcs),
    `observe.ts`, `config-io.ts`, `ui-nav.ts`, `unit-visual-resolve.ts`,
    `unit-asset-map.ts`.
  - **sim / mirror** : `sim-engine.ts`, `sim.ts`, `compare.ts`.
  - **AI trace / observabilité** : `ai-trace.ts` (+ sous-dossier `ai-trace/` :
    playbooks, generators, predictions, utilities, ai-control, state),
    `ai-utility-trace.ts`, `scorer-damage-trace.ts`, `message-trace.ts`,
    `bucket-audit.ts`, `dispatch-observe.ts`, `modifier-observe.ts`,
    `move-options.ts`, `movement-trace.ts` (désactivé par défaut : `void
    movementTrace` dans controller — hooks laggy), `board-trace.ts`,
    `winner-capture.ts`, `whatif-trigger.ts`, `dump-composed.ts`,
    `overwatch-fix/` (anti-suicide overwatch), `ability-prefs.ts`.
  - **RL** : `rl/` (bridge, tensorizer — observation tensorisée).
  - **diag bas niveau** : `crash-trap.ts`, `init-trace.ts`, `introspect.ts`,
    `status.ts`.
- `hooks/probes/` — sondes d'introspection RE (dump offsets/méthodes/enums/formules).
  Le répertoire est VERSIONNÉ (67 fichiers) et `controller.ts` en importe statiquement 67,
  donc **66 sortent dans `dist/hooks.js`** — l'écart d'un module est un import mort, éliminé
  par le tree-shaking d'esbuild. Leur SORTIE ne sert qu'à la lecture humaine ; leur CODE, lui,
  est livré dans le script injecté et engage donc la stabilité de la session. Il s'appelait
  `hooks/scratch/` jusqu'à #480-r6 : **un nom qui déclare un répertoire jetable le fait écarter
  des périmètres d'audit**, et celui-ci l'a été pendant quatre jours (142 erreurs `tsc`
  classées hors sujet). `hooks/probes/README.md` dit ce qu'est une sonde.
- `hooks/ai-toolkit/` — helpers partagés du toolkit décision : `hex.ts`
  (géométrie hex), `coroutine.ts` (pump MoveNext), `unit-action.ts`,
  `stack-capture.ts` (backtrace ciblé), `fix64.ts` (arithmétique Fix64).
- `hooks/data/` — tables de noms figées : `ability-names.ts`,
  `triggered-ability-names.ts`, `effect-type-names.ts`, `targeting-rule-names.ts`.
- `hooks/il2cpp/` — `helpers.ts` (`findClassAnywhere`/`findMethod`/
  `getFieldOffset`/`readIl2cppString`…), `invoke.ts`, `gc-root.ts` (pin/unpin),
  `serializer.ts`, `mt.ts` (Mersenne Twister), `enum-dump.ts`, `project.ts`.
- `hooks/runtime/` — pump main thread (`queue.ts`/`main-pump.ts`), crash logger,
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
des MethodInfo* perdus, `lastSource` à `null`). Ces caches se remplissent seuls
au premier `findClassAnywhere` ; `lastSource` se recapture quand le jeu construit
un `CampaignGameModeSource` (donc à la première nav de campagne).
