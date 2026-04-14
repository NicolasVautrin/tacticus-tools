
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
  server/src/         # Serveur Node.js (Express + frida-node + ws)
  hooks/              # Bibliotheque de hooks Frida (composition par concat)
  data/               # Fichiers de donnees (gitignore)
    symbols.json      # 168k methodes + 2015 enums
    i2_en.json        # 17810 termes I2
    gameconfig-abilities.json  # 599 configs (active + triggered + traits)
    gameconfig-units.json      # 117 unites
    gameconfig-summons.json    # 55 summons
  lib/                # Helpers Python (state.py, hex.py, rpc.py)
  sources/            # Stubs C# depuis IL2CPP runtime dump (gitignore)
  logs/               # JSONL des sessions (gitignore)
  scripts/            # Scripts standalone et outils de dump
```

## Demarrage du serveur

```bash
cd server && npx tsx src/index.ts
# Ecoute sur http://127.0.0.1:8765
```

Arret : `curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown`

Ne JAMAIS utiliser de hot-reload (casse les sessions Frida).

## References detaillees

- [hooks.md](references/hooks.md) — modules Frida, composition, Interceptor.replace, conventions
- [rpc-api.md](references/rpc-api.md) — RPCs, format state, events, Python helpers
- [knowledge.md](references/knowledge.md) — pieges resolus (unboxed, same-thread, findMethod, etc.)
- [game-architecture.md](references/game-architecture.md) — ECS, entites, composants, grille hex

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

## Injection rapide

```bash
PID=$(adb -s f32224e7 shell "ps -A | grep -i tacticus" | awk '{print $2}')
HOOKS="hooks"
cat "$HOOKS/_utils/il2cpp-helpers.js" \
    "$HOOKS/_utils/il2cpp-invoke.js" \
    "$HOOKS/_utils/il2cpp-serializer.js" \
    "$HOOKS/_utils/matchstate-reader.js" \
    "$HOOKS/autoplay/message-factory.js" \
    "$HOOKS/autoplay/action-queue.js" \
    "$HOOKS/autoplay/turn-observer.js" \
    "$HOOKS/autoplay/input-capture.js" \
    "$HOOKS/autoplay/recv-handler.js" \
    > scripts/autoplay-composed.js

# Construire le payload (trop gros pour curl inline)
node -e "
const fs = require('fs');
const source = fs.readFileSync('scripts/autoplay-composed.js', 'utf-8');
const payload = JSON.stringify({serial: 'f32224e7', mode: 'attach', pid: $PID, source,
  log_dir: 'logs'});
fs.writeFileSync('scripts/inject-payload.json', payload);
"

curl -s -X POST http://127.0.0.1:8765/api/scripts/run \
  -H "Content-Type: application/json" \
  -d @scripts/inject-payload.json
```

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

## TODO

### Court terme
- Enrichir les hooks AI observer : entity IDs + stacks
- Reproduire les appels AttackQuery/TargetingQuery en RPC
- Construction de `UnitPosition` (necessaire pour appeler GetValidTargets)

### Moyen terme
- Damage prediction via `DamagePredictionQuery`
- Detection overwatch (TriggeredAbilityComponent)