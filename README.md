---
title: "tacticus-tools"
subtitle: "Serveur Frida minimal pour WH40K Tacticus"
date: "2026-04-14"
---

# tacticus-tools

Serveur Node.js minimal pour le hooking Frida de **WH40K Tacticus** sur Android.

Remplace le backend Python de frida-ide avec ~500 lignes de TypeScript :
injection de scripts, RPC, logs JSONL, enrichissement des symboles IL2CPP
et descriptions I2.

## Fonctionnalites

- **Injection Frida** : attach/spawn sur device USB via frida-node
- **RPC synchrone** : appels get_state, move, attack, end_turn avec timeout
- **Enrichissement automatique** : stacks IL2CPP, enums, descriptions I2
  (abilities, triggered, effets — 100% resolus)
- **JSONL logging** : un fichier par session, append-only
- **WebSocket streaming** : messages enrichis en temps reel avec reconnection
- **Shutdown propre** : cleanup des hooks Frida avant decharge

## Prerequis

- Node.js >= 18
- frida-server 17.9.1 sur le device Android (root requis)
- adb dans le PATH

## Installation

```bash
cd server
npm install
```

## Demarrage

```bash
cd server
npx tsx src/index.ts
```

Le serveur ecoute sur `http://127.0.0.1:8765`.

## Utilisation rapide

### Lister les devices

```bash
curl -s http://127.0.0.1:8765/api/devices
```

### Injecter l'autoplay

```bash
PID=$(adb -s f32224e7 shell "ps -A | grep -i tacticus" | awk '{print $2}')

cat hooks/_utils/il2cpp-helpers.js \
    hooks/_utils/il2cpp-invoke.js \
    hooks/_utils/il2cpp-serializer.js \
    hooks/_utils/matchstate-reader.js \
    hooks/autoplay/message-factory.js \
    hooks/autoplay/action-queue.js \
    hooks/autoplay/turn-observer.js \
    hooks/autoplay/input-capture.js \
    hooks/autoplay/recv-handler.js \
    > scripts/autoplay-composed.js

node -e "
const fs = require('fs');
const source = fs.readFileSync('scripts/autoplay-composed.js', 'utf-8');
const payload = JSON.stringify({
  serial: 'f32224e7', mode: 'attach', pid: $PID,
  source, log_dir: 'logs'
});
fs.writeFileSync('scripts/inject-payload.json', payload);
"

curl -s -X POST http://127.0.0.1:8765/api/scripts/run \
  -H "Content-Type: application/json" \
  -d @scripts/inject-payload.json
```

### Recuperer l'etat de jeu

```bash
curl -s -X POST http://127.0.0.1:8765/api/scripts/1/rpc \
  -H "Content-Type: application/json" \
  -d '{"method":"get_state","args":{"depth":6}}'
```

### Arreter

```bash
curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown
```

## API

| Methode | Route | Description |
|:--------|:------|:------------|
| GET | `/api/health` | Health check + stats symboles |
| GET | `/api/devices` | Devices Frida (USB, local) |
| GET | `/api/devices/:serial/processes` | Processus du device |
| POST | `/api/scripts/run` | Injection de script |
| POST | `/api/scripts/:id/stop` | Stop session |
| POST | `/api/scripts/:id/rpc` | Appel RPC synchrone |
| POST | `/api/scripts/:id/message` | Message async au script |
| GET | `/api/scripts/:id` | Status session |
| POST | `/api/_dev/shutdown` | Arret du serveur |

WebSocket : `ws://127.0.0.1:8765/ws/run/:id` (reconnection via `?last_event_id=N`)

## Structure

```
server/src/
  index.ts              # Routes Express + startup
  frida-manager.ts      # Sessions Frida (attach, RPC, cleanup)
  symbol-resolver.ts    # Enrichissement (enums, stacks, I2, effets)
  jsonl-logger.ts       # Logging JSONL
  ws-stream.ts          # WebSocket + ring buffer

hooks/                  # Modules Frida (composition par concat)
  _utils/               # il2cpp-helpers, invoke, serializer, matchstate-reader
  autoplay/             # Boucle autoplay complete
  _oneshot/             # Dumps one-shot (symbols, abilities, gameconfig)
  ai/                   # Observers IA du jeu
  battle/               # Hooks de combat

data/                   # Donnees de reference (gitignore)
lib/                    # Helpers Python (state, hex, rpc)
logs/                   # Sessions JSONL (gitignore)
scripts/                # Scripts composes et outils
```

## Donnees

Les fichiers `data/` sont generes par les hooks oneshot et ne sont pas
versionnes. Pour les regenerer :

- **symbols.json** : `_oneshot/dump-symbols.js` (hors combat)
- **gameconfig-abilities.json** : `_oneshot/dump-gameconfig.js` +
  `scripts/dump-all-configs.js` (en combat)
- **i2_en.json** : extraction depuis le bundle UnityFS de l'APK
