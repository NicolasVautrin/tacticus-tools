# tacticus-tools

Serveur Node.js minimal pour le hooking Frida de WH40K Tacticus.

## Demarrage

```bash
cd server && npm run dev
```

Le serveur ecoute sur `http://127.0.0.1:8765`.

## Device

- Xiaomi 2201117TY, serial `f32224e7`
- Package : `com.snowprintstudios.tacticus`

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
    > /tmp/composed.js

# Payload trop gros pour curl inline
node -e "
const fs = require('fs');
const source = fs.readFileSync('/tmp/composed.js', 'utf-8');
const payload = JSON.stringify({serial: 'f32224e7', mode: 'attach', pid: $PID, source, log_dir: 'logs'});
fs.writeFileSync('/tmp/inject.json', payload);
"
curl -s -X POST http://127.0.0.1:8765/api/scripts/run \
  -H "Content-Type: application/json" -d @/tmp/inject.json
```

## Arret

```bash
curl -s -X POST http://127.0.0.1:8765/api/scripts/{id}/stop
```

Pour tuer le serveur : Ctrl+C ou `kill $(lsof -ti:8765)`.

## Ne jamais

- Utiliser `--reload` ou equivalent hot-reload (casse les sessions Frida)
- Appeler stop manuellement sur une session avec Interceptor.replace actif (crash le jeu)
- Commit les fichiers data/ (12M+ symbols.json, etc.)
