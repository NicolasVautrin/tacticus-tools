
---
name: tacticus
description: WH40K Tacticus hooking, MatchState serialization, and auto-play. Use when working on Tacticus hooks, battle analysis, or game AI.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Edit, Write, Agent
---

# Tacticus — WH40K Hooking & Auto-play

## Device

- Xiaomi 2201117TY, serial `f32224e7`
- Android 12 (API 31), ARM64, Magisk root, frida-server 17.9.1
- Target: `com.snowprintstudios.tacticus`

## Repo

`C:/Users/nicolasv/tacticus-tools/`

```
tacticus-tools/
  frida/              # Monorepo TypeScript actif (hooks + host)
    src/hooks/        # Script injecté (bundlé par frida-compile)
      il2cpp/         # Primitives IL2CPP (helpers, invoke, serializer, gc-root, mt)
      game/           # Tacticus-specific (runner, match-state, ai-control, recorder, state)
      features/       # RPCs par feature (status, sim, compare, cheat)
      runtime/        # queue, main-pump
      controller.ts   # Aggregate features → rpc.exports
      main.ts         # Entrypoint
    src/host/         # Serveur Node (Express + WS + Frida bridge)
      index.ts, router.ts, sessions.ts, logger.ts, ws.ts
    dist/             # Outputs build (gitignored)
  hooks-legacy/       # Anciens hooks — one-shots (dumps, probes) + obsolete. README classifie.
  server/             # Ancien serveur Node (à renommer server-legacy/)
  data/               # Dumps IL2CPP (symbols.json, abilities, enums) — gitignored
  sources/            # Stubs C# enrichis offsets — gitignored
  logs/               # JSONL des sessions — gitignored
```

## Démarrage du serveur

```bash
cd frida && npm run dev
# Écoute sur http://127.0.0.1:8765
```

Arrêt : `curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown`

Ne JAMAIS utiliser de hot-reload (casse les sessions Frida).

## References detaillees

- [hooks.md](references/hooks.md) — modules Frida, composition, Interceptor.replace, conventions
- [rpc-api.md](references/rpc-api.md) — RPCs, format state, events, Python helpers
- [knowledge.md](references/knowledge.md) — pieges resolus (unboxed, same-thread, findMethod, etc.)
- [game-architecture.md](references/game-architecture.md) — ECS, entites, composants, grille hex, combats headless
- [decompilation.md](references/decompilation.md) — Ghidra headless, scripts, methode, adresses
- [ai-engine-audit.md](references/ai-engine-audit.md) — Audit du moteur IA depuis decompilation

## API du serveur

### Endpoints HTTP

| Methode | Route | Description |
|---------|-------|-------------|
| GET | `/api/health` | Health check + stats symboles |
| GET | `/api/devices` | Liste des devices Frida + USB |
| GET | `/api/devices/:serial/processes` | Liste des process |
| POST | `/api/scripts/run` | Injection — body: `{serial, mode, pid?, target?, source, log_dir?}` |
| POST | `/api/scripts/:id/stop` | Stop session (cleanup graceful) |
| POST | `/api/scripts/:id/rpc` | RPC synchrone — body: `{method, args, timeout?}` |
| POST | `/api/scripts/:id/message` | Envoyer un message au script |
| GET | `/api/scripts/:id` | Status session |
| POST | `/api/_dev/shutdown` | Arret du serveur |

### WebSocket

`ws://127.0.0.1:8765/ws/run/:id` — stream des messages Frida enrichis (reconnection via `?last_event_id=N`)

### Enrichissement automatique

Le serveur enrichit tous les messages et reponses RPC :
- **Stacks** : offsets IL2CPP → noms de methodes
- **Enums** : `{_enum, _value}` → ajout `_name`
- **Descriptions I2** : abilities et effets → substitution templates + variables/constants gameconfig
- **Effets** : cross-pass avec les params de l'unite source (100% resolus, 0 placeholders)

## Boucle de jeu (workflow)

```
1. Injecter le script compose (hooks autoplay)
2. get_state(depth=6) -> GameState enrichi
3. Analyser : positions, HP, distances, tiles atteignables
4. Decider la meilleure action (move, ability, end_turn)
5. play(action, ...) -> nouveau GameState + events
6. Repeter 3-5 jusqu'a fin de tour
7. end_turn() -> attend fin du tour IA -> nouveau GameState
8. Retour a 2
```

## Build + Injection

```bash
cd frida && npm run build:hooks        # → frida/dist/hooks.js

PID=$(adb -s f32224e7 shell "ps -A | grep -i tacticus" | awk '{print $2}')
node -e "
const fs = require('fs');
const source = fs.readFileSync('C:/Users/nicolasv/tacticus-tools/frida/dist/hooks.js', 'utf-8');
const payload = JSON.stringify({serial: 'f32224e7', mode: 'attach', pid: $PID, source, log_dir: 'logs'});
fs.writeFileSync('C:/Users/nicolasv/AppData/Local/Temp/inject.json', payload);
"

curl -s -X POST http://127.0.0.1:8765/api/scripts/run \
  -H "Content-Type: application/json" \
  -d @C:/Users/nicolasv/AppData/Local/Temp/inject.json
```

Le payload est trop gros pour curl inline, passer par un fichier temp. `log_dir: 'logs'` sinon les messages vont dans le cwd du host.

## Ajouter une feature

Créer `frida/src/hooks/features/foo.ts` :
```ts
import { Ctx } from "../controller.js";
import { queueOnMainThread } from "../runtime/queue.js";

export function register(ctx: Ctx): void {
    ctx.rpc.myRpc = () => queueOnMainThread(() => ({ ok: true }));
}
```
Puis dans `controller.ts` : ajouter `import * as foo from "./features/foo.js";`
et l'inclure dans le tableau de `wireRpc`. Rebuild.

## Messages injectables (testes)

| Message | Champs | Statut |
|---------|--------|--------|
| `EndTurnMessage` | aucun | OK |
| `MoveUnitMessage` | `unitId`, `positions: [{col, row}]` | OK (fix unboxed) |
| `ActiveAbilityMessage` | `casterId`, `targetId`, `abilityType` | OK — `abilityType` = `NormalAttackType` de l'unite (ex: 69, 1123). Type 0 est ignore. |

## AI Services Observer

`hooks/ai/ai-services.js` — hooks minimaux sur les services utilises par l'IA :
- `AttackQuery.GetValidTargets` — 106 appels/tour IA
- `AttackQuery.HasValidTargets` — 53 appels/tour IA
- `DamagePredictionQuery.GetAllPredictions` — pas appele dans le combat observe
- `TargetingQuery.GetRangeValue` — pas appele dans le combat observe

Composable avec l'autoplay (ajouter avant `recv-handler.js` dans la concatenation).

## Simulation — standalone IdunRunner (état 2026-04-18 soir)

**Script unique** : `hooks/autoplay/full-recorder.js`. Il hooke live, construit un standalone isolé, rejoue l'historique dessus, laisse l'IA décider le tour courant, commit sur live. Tout est validé et robuste.

### Workflow

```
inject full-recorder → hooks armés (runner.Apply, AiControl.Apply*AiMessage, StreamDispatcher)
                     → bootstrap preamble depuis ReplayRecorder natif (top-level)
                     → log = [top_boot + live captures over time]

sim()   → buildStandaloneRunner() + catch-up via log + CheatRunAI(standalone)
        → capture sub-messages via Interceptor.attach filtered sur innerAiControl
        → stash sous simId

commit(simId) → rejoue les captured sur realAiControl → live bouge

simAndCommit = sim() then commit()
```

### Règles clés

- **Ctor standalone** : `findCtorByParamCount(runnerClass, 2)` (PAS `findMethod(".ctor")` — retourne pas forcément le bon overload, crash `access violation` sur adresse data).
- **Dispatch sur standalone** : TOUT via `runner.Apply(msg)`, pour top, ai ET humanAi. `AiControl.ApplyAiMessage` hors contexte CheatRunAI → `abort was called`.
- **Skip `CheatRunAIMessage`** dans le catch-up — ses sub-messages sont déjà dans notre log, re-fire double-appliquerait.
- **Vol des sidecars** : logger @80, timeSource @88, config @176, opProc @192 → startMatchOp @+528 → reporter @+48 (`NullBattleDataReporter`).
- **Seed depuis `ReplayRecorder._replay.RngSeed`** → Initialize(seed overload) → standalone PRNG aligné sur live (même `mt[]`).
- **GC rooting** : `gcRoot.add(x)` sur chaque IL2CPP object qu'on garde entre apply et commit. ArrayList-based avec retry sur `ArrayTypeMismatchException`.

### Ce qu'on peut faire maintenant

- **Clone isolé** de l'état via standalone (aligné à 1.4KB près, census entités identique 195/195).
- **AI fresh sur standalone** sans toucher le live (`sim` RPC).
- **Commit différé** (`commit(simId)`) ou combiné (`simAndCommit`).
- **Comparaison** standalone vs live (`compareStandalone`) : state digest + PRNG + census + dumps complets via `send({t:"state_dump"})`.
- **Event traces** correlés par trigger : `StreamDispatcher.Action/StartGroup` routés via `applyStack` → events attachés à `log[i].events` sur live, `standaloneTrace[i].events` pour les dispatches standalone.

### Delta résiduel standalone vs live

~1.4KB, sur des champs transitoires post-kill que live nettoie via un tick end-of-turn (`LeftOverDamage`, `PendingHit`, `DeathReason`, `KilledThisTurn`, `DefeatedByMeleeAttack`). La logique de gameplay est alignée : mêmes kills, mêmes summons, mêmes effets, même ordre d'actions.

### Anti-pattern à ne plus reprendre

- `ReplayRunner` : crash `access violation 0x4` sur 2ème build dans la même session. Abandonné au profit de standalone `IdunRunner`.
- Swap `runner._state` : 67 services gardent leur propre ref → swap ignoré.
- `InitializeBattle()` sur ReplayRunner : NPE systématique.

### RPCs principaux

| RPC | Rôle |
|---|---|
| `battleStatus` | stage, currentTurnPlayer, unitsAlive |
| `summary` / `dump` | aperçu / dump complet du log capturé |
| `sim` | build standalone + catch-up + CheatRunAI → `{simId, captured}` |
| `commit(simId)` | rejoue les messages du sim sur live |
| `simAndCommit` | wrapper `sim + commit` |
| `compareStandalone` | state digest + census + dumps state JSON + event traces via send() |
| `cheatRunAi` | fallback direct : CheatRunAI sur live (pour finir une battle, debug) |
| `compareNative` | sanity-check : nos `top` = ReplayRecorder natif |

Détails complets : memory `project_matchstate_copy.md`, `project_replay_sim.md`, `project_ai_plays_player.md`, `project_sim_and_commit_turn1.md`. Plan d'arbre de décision : `~/.claude/plans/twinkling-floating-pond.md`.

## TODO autres

### Court terme
- Enrichir les hooks AI observer : entity IDs + stacks
- Reproduire les appels AttackQuery/TargetingQuery en RPC
- Construction de `UnitPosition` (necessaire pour appeler GetValidTargets)

### Moyen terme
- Damage prediction via `DamagePredictionQuery`
- Detection overwatch (TriggeredAbilityComponent)