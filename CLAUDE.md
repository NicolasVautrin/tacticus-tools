# tacticus-tools

Hooking Frida de WH40K Tacticus — monorepo TypeScript.

## Structure

- Racine : `C:\Users\nicolasv\tacticus-tools`
- `frida/` — codebase active (hooks TS + host TS, bundlé par `frida-compile`)
  - `frida/hooks/` — script injecté
  - `frida/host/` — serveur Node qui pilote les sessions Frida
  - `frida/dist/` — outputs build (gitignored)
- `hooks-legacy/` — ancien répertoire de hooks, conservé pour one-shots (dumps,
  probes historiques). Voir `hooks-legacy/README.md` pour classification.
- `server/` — ancien serveur Node (obsolete, à renommer en `server-legacy/`
  quand le process node aura relâché les fichiers)
- `data/` — dumps IL2CPP (`symbols.json`, abilities, enums) — gitignored
- `sources/` — sources décompilées enrichies offsets — gitignored

## Démarrage

```bash
cd frida && npm run dev
```

Serveur sur `http://127.0.0.1:8765`.

## Device

- Xiaomi 2201117TY, serial `f32224e7`, rooté
- Package : `com.snowprintstudios.tacticus`

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

## Arrêt

```bash
curl -s -X POST http://127.0.0.1:8765/api/scripts/{id}/stop
```

Pour tuer le serveur : Ctrl+C dans le terminal `npm run dev`, ou
`curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown`.

## Ne jamais

- Utiliser `--reload`/hot-reload côté host (casse les sessions Frida actives)
- Appeler stop manuellement sur une session avec `Interceptor.replace` actif
  sans le protocole cleanup (crash le jeu)
- Commit `data/` (symbols.json 12M+, etc.) ou `frida/dist/`, `hooks-legacy/`,
  `server/`, `logs/`

## Documentation détaillée

!include .claude/skills/tacticus/references/frida-host.md
!include .claude/skills/tacticus/references/hooks.md
!include .claude/skills/tacticus/references/rpc-api.md
!include .claude/skills/tacticus/references/knowledge.md
!include .claude/skills/tacticus/references/game-architecture.md
!include .claude/skills/tacticus/references/decompilation.md
!include .claude/skills/tacticus/references/ai-engine-audit.md
