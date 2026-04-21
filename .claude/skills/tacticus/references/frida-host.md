# Frida host — Node qui pilote Frida

Host HTTP Node.js local (Express + WebSocket) qui pilote Frida : injection
scripts, RPC sur les sessions, persistance des messages `send()` en jsonl.
Code source : (file:///C:/Users/nicolasv/tacticus-tools/frida/host/)

**Ne pas confondre avec** :
- **`frida-server`** : daemon Frida qui tourne *sur le device Android*
  (installé via `adb push` + `chmod +x`). C'est l'autre bout du lien —
  notre host Node **parle** à ce daemon via le binding `frida` npm.

Architecture :
```
Claude / scripts locaux
     |
     | HTTP :8765
     v
Frida host Node (frida/host/index.ts)   <- ce document
     |
     | npm 'frida' binding (USB)
     v
frida-server (daemon sur device)
     |
     | ptrace + injection
     v
com.snowprintstudios.tacticus
```

## Démarrage

```bash
cd frida && npm run dev   # écoute 127.0.0.1:8765
```

Le module `frida` npm est dans `frida/node_modules` — tout script Node
qui `require('frida')` doit être exécuté depuis `frida/`.

## Modules

- `host/index.ts` — Express + WS, entrypoint
- `host/router.ts` — routes HTTP `/api/*` (factorisées)
- `host/sessions.ts` — attach / load / rpc / graceful cleanup
- `host/logger.ts` — jsonl writer per session (`logs/run-N_HHMMSS_target.jsonl`)
- `host/ws.ts` — WebSocket streaming avec ring buffer + reconnect `?last_event_id=N`

## Endpoints exposes

| Method | Route | Role |
|--------|-------|------|
| GET    | `/api/health`                      | ping |
| GET    | `/api/devices`                     | liste des devices adb/USB (vu par Frida) |
| GET    | `/api/devices/:serial/processes`   | liste des process sur le device |
| POST   | `/api/scripts/run`                 | injecte un script Frida dans un process |
| POST   | `/api/scripts/:id/stop`            | stoppe une session (cleanup + unload) |
| POST   | `/api/scripts/:id/rpc`             | appelle une methode RPC exposee par le script |
| POST   | `/api/scripts/:id/message`         | envoie un `recv()` au script |
| GET    | `/api/scripts/:id`                 | etat d'une session (id, pid, status) |
| GET    | `/api/sessions`                    | **liste** de toutes les sessions |

Pas d'endpoint pour recuperer les `send()` emis par un script — il faut lire le fichier JSONL (voir plus bas).

## Injection one-shot

Pattern type : ecrire le payload dans un fichier (curl -d inline explose sur des payloads > quelques KB), puis POST :

```bash
# 1. Trouver le PID du jeu
PID=$(adb -s f32224e7 shell "ps -A | grep tacticus" | awk '{print $2}')

# 2. Construire le payload via node (source = contenu du script bundlé)
node -e "
const fs=require('fs');
const source=fs.readFileSync('C:/Users/nicolasv/tacticus-tools/frida/dist/hooks.js','utf-8');
fs.writeFileSync('C:/Users/nicolasv/AppData/Local/Temp/inject.json', JSON.stringify({
  serial: 'f32224e7',
  mode:   'attach',
  pid:    $PID,
  source,
  log_dir: 'logs',
}));
"

# 3. Injecter
curl -s -X POST http://127.0.0.1:8765/api/scripts/run \
  -H "Content-Type: application/json" \
  -d @C:/tmp/inject.json
# -> {"run_session_id": 25, "pid": 9985, "mode": "attach", "status": "running"}
```

## Logs — piege principal du serveur Node

`POST /api/scripts/run` accepte un champ `log_dir` qui determine ou atterrissent les `send()` du script :

- **Si absent** → defaut `path.resolve(__dirname, "../../logs")` = chemin **absolu** vers (file:///C:/Users/nicolasv/tacticus-tools/logs/).
- **Si present** → interprete tel quel. Une valeur relative comme `"logs"` est resolue par rapport au **cwd du process serveur Node** (donc `server/logs/` si le serveur tourne depuis `server/`) — pas la racine du projet.

Pour un one-shot, **omettre `log_dir`** pour que les outputs arrivent dans (file:///C:/Users/nicolasv/tacticus-tools/logs/).

Nom du fichier : `run-{id}_{HHMMSS}_{target}.jsonl` ou `target` = valeur du param `target` du POST, sinon `"unknown"`.

Les `send({...})` du script IL2CPP apparaissent dans ce JSONL sous cette forme :
```json
{"type":"send","ts":"...","payload":{"type":"send","payload":{"t":"...",...}}}
```

Double `payload` = enveloppe Frida (interne) + enveloppe server. Le vrai contenu utile est dans `ev.payload.payload`.

## Recuperer les messages d'un script one-shot

Aucune API n'expose les `send()` du script cote serveur Node. Il faut lire le JSONL :

```bash
# Trouver le log le plus recent de la session N
ls -t C:/Users/nicolasv/tacticus-tools/logs/run-{N}_* | head -1

# Extraire un type d'event precis
python -c "
import json
with open('logs/run-25_232822_unknown.jsonl', encoding='utf-8') as f:
    for line in f:
        ev = json.loads(line)
        p = ev.get('payload', {}).get('payload', {})
        if p.get('t') == 'il2cpp_full':
            # traiter p['classes'], p['methods'], p['enums']
            break
"
```

## Probe des exports Frida disponibles

Avant d'utiliser un `il2cpp_*` helper dans un script, vérifier qu'il existe sur ce binaire via
(file:///C:/Users/nicolasv/tacticus-tools/hooks-legacy/_oneshot/probe-class-flags.js).

Resultats observes sur `libil2cpp.so` de Tacticus :

| Export | Disponible |
|--------|------------|
| `il2cpp_class_get_flags` | oui |
| `il2cpp_class_is_interface` | oui |
| `il2cpp_class_is_abstract` | oui |
| `il2cpp_class_is_generic` | oui |
| `il2cpp_class_is_inflated` | oui |
| `il2cpp_class_is_sealed` | non (deduire via `flags & 0x100`) |
| `il2cpp_class_get_interfaces` | oui |
| `il2cpp_class_get_properties` | oui |
| `il2cpp_type_is_reference` | non |

## Cleanup / re-injection

`POST /api/scripts/:id/stop` envoie `{type:"cleanup"}` au script, attend `{t:"cleanup_done"}` + sleep 50ms, puis unload. Obligatoire si le script utilise `Interceptor.replace` — detacher pendant un frame Update crashe le jeu.

`recv-handler.js` (dans autoplay) contient le handler cleanup cote script.

## Ameliorations serveur Node identifiees

Pour eviter de re-tomber dans les memes pieges :

- `GET /api/scripts/:id/events?since=N` manquant → on est oblige de lire le JSONL a la main.
- `POST /api/scripts/run?wait_for={"t":"probe_done"}` manquant → pas de moyen synchrone d'attendre un event pour un one-shot.
- `log_dir` relatif est trompeur → forcer absolu ou afficher warning.
- Pas de `GET /api/scripts` (sans id) → utiliser `GET /api/sessions` a la place.

## Exemple complet : probe + lecture

```bash
# Probe pour savoir quels exports sont dispos
node -e "
const fs=require('fs');
const source=fs.readFileSync('hooks/_oneshot/probe-class-flags.js','utf-8');
fs.writeFileSync('C:/tmp/probe.json', JSON.stringify({
  serial:'f32224e7', mode:'attach', pid:9985, source
}));
"
curl -s -X POST http://127.0.0.1:8765/api/scripts/run \
  -H "Content-Type: application/json" -d @C:/tmp/probe.json
# -> {"run_session_id": 23, ...}

# Attendre que le script ait emis puis lire
cat C:/Users/nicolasv/tacticus-tools/logs/run-23_*.jsonl | python -c "
import json, sys
for line in sys.stdin:
    ev = json.loads(line)
    p = ev['payload']['payload']
    if p.get('t') == 'probe_samples':
        print(p['samples'])
"
```