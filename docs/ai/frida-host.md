# Frida host — Node qui pilote Frida (Tacticus PC)

Host HTTP Node.js local (Express + WebSocket) qui pilote Frida : injection
de scripts, RPC sur les sessions, persistance des messages `send()` en
JSONL, broadcast WebSocket vers le frontend.

Code source : (file:///C:/Users/nicolasv/tacticus-tools/frida/host/)

## Architecture

```
Frontend browser  (frida/public/)
     |
     | HTTP /api/* + WebSocket /ws/run/:id
     v
Frida host Node (frida/host/index.ts)   <- ce document
     |
     | npm 'frida' binding via frida.getLocalDevice()
     | (pas d'adb, pas de frida-server)
     v
Tacticus.exe (Windows, Unity 6 IL2CPP)
     |
     | injection en mémoire — frida-agent.dll
     v
GameAssembly.dll  (~60 MB, AOT)
```

## Démarrage

```bash
cd frida && npm run dev   # écoute 127.0.0.1:8765
```

Le module `frida` npm est dans `frida/node_modules` — le serveur s'exécute
depuis `frida/`. Pas de hot-reload (casserait les sessions Frida actives).

## Modules

- `host/index.ts` — Express + WS, entrypoint, listen :8765
- `host/router.ts` — routes HTTP `/api/*` (factorisées)
- `host/sessions.ts` — attach (local device), load script, RPC, lifecycle
- `host/admin.ts` — auto-discovery PID Tacticus + injectBundle
- `host/ws.ts` — WebSocket streaming + ring buffer + reconnect
  `?last_event_id=N`
- `host/config-store.ts` — file-backed BattleConfiguration captures
- `host/battle-store.ts` — battle_event store (sim, simAndCommit, …)
- `host/meta-sync.ts` — `syncEnums`, `syncCampaignCatalog` (allowHeapScan)

Logs JSONL écrits sous (file:///C:/Users/nicolasv/tacticus-tools/frida/logs/)
(default), nommés `run-{id}_HHMMSS_target.jsonl`.

## Auto-discovery du PID Tacticus

`admin.ts` énumère `frida.getLocalDevice().enumerateProcesses({ scope: "metadata" })`
puis filtre :
- nom matchant `/tacticus/i`
- exe accompagné d'un dossier `Tacticus_Data/` adjacent (heuristique Unity
  standard qui distingue le **jeu** du **launcher**)

Si plusieurs candidats game → 409 + liste pour disambiguation côté UI.
Si zéro → 404 explicite.

## Endpoints exposés

| Méthode | Route | Rôle |
|---------|-------|------|
| GET | `/api/admin/status` | Tacticus running + game/launcher PIDs + session info |
| POST | `/api/admin/inject` | Injection (body `{}` = auto-discovery, `{pid:N}` = forçage) |
| GET | `/api/admin/candidates` | Liste tous les processes Tacticus détectés (debug) |
| GET | `/api/sessions` | Sessions Frida actives |
| POST | `/api/scripts/:id/stop` | Stop session (cleanup graceful) |
| POST | `/api/scripts/:id/rpc` | RPC synchrone — `{method, args, timeout?}` |
| GET | `/api/scripts/:id` | État session |
| GET | `/api/configs` | Liste BattleConfiguration captures |
| GET | `/api/configs/:id` | JSON capture |
| DELETE | `/api/configs/:id` | Supprimer capture |
| GET | `/api/campaigns/builder-status` | RPC `campaignBuilderStatus` (cheap, 5s polled) |
| POST | `/api/campaigns/catalog/refresh` | Force re-dump catalog (passe `allowHeapScan: true` à l'agent) |
| POST | `/api/campaigns/build` | `{campaignType, campaignId, locationIndex}` → BattleConfiguration |
| GET | `/view/` | Frontend statique |
| GET | `/assets/*` | PNGs, manifest, configs persistés |
| POST | `/api/_dev/shutdown` | Arrêt graceful |

WebSocket : `ws://127.0.0.1:8765/ws/run/:id` — reconnect via
`?last_event_id=N`.

## Front-end

| Route | Sert | Source disque |
|-------|------|---------------|
| `/view/` | UI principale | (file:///C:/Users/nicolasv/tacticus-tools/frida/public/) |
| `/assets/*` | PNG, manifest, configs persistés | (file:///C:/Users/nicolasv/tacticus-tools/frida/assets/public/) |

URL à ouvrir : **http://127.0.0.1:8765/view/** (la racine `/` n'est pas
servie → 404).

## Logs JSONL — format

Chaque message `send({...})` du script + chaque échange RPC + chaque event
ws.publish() sont append-écrits :

```json
{"type":"send","ts":"...","payload":{"type":"send","payload":{"t":"...",...}}}
```

Double `payload` = enveloppe Frida + enveloppe host. Le contenu utile est
dans `ev.payload.payload`. Champ `.t` = type d'event :
- `diag` — `log()` du script (`{ msg }`)
- `trace` — `traceEnter()` du script (`{ n, name }`)
- `captured_config` — capture passive d'une battle (`{ id, mode, ts, bytes, json }`)
- `battle_event` — pendant simulation (sim, simAndCommit)
- `builder_ready` — push amorce signal (`{ via: "ctor" | "LoadBattle" }`)
- `hook_ready`, `cleanup_done`, …

Lecture rapide :
```bash
LOG=$(ls -t C:/Users/nicolasv/tacticus-tools/frida/logs/run-*.jsonl | head -1)
grep '"t":"diag"' "$LOG" | tail -10
```

## Cleanup / re-injection

`POST /api/scripts/:id/stop` envoie `{type:"cleanup"}` au script, attend
`{t:"cleanup_done"}` (handshake court), puis unload. Obligatoire si le
script utilise `Interceptor.replace` — détacher pendant un frame Update
crashe le jeu.

Le handler côté script est dans `frida/hooks/main.ts`.

**Caveat** : la re-injection sur le même PID Tacticus après un stop peut
wedge (cf. memory `feedback_frida_wedge_after_stop.md`). Procédure sûre :
relancer Tacticus avant de réinjecter.

## Heap scans = explicit-only

L'agent expose des fallback heap scans (`findGameConfigDtoViaHeap`,
`findCampaignGameModeSourceViaHeap`, …) gated par
`allowHeapScan: true` dans les opts. Frida `Process.enumerateRanges` /
`Memory.scan` suspendent les threads cible pendant le scan IL2CPP heap
(~10 s). Tacticus's UnityFreezeDetector tue le process si freeze > seuil.

Côté host :
- `syncCampaignCatalog(sid, allowHeapScan=true)` pour
  `POST /api/campaigns/catalog/refresh` (= bouton ↻ utilisateur)
- `syncCampaignCatalog(sid, allowHeapScan=false)` partout ailleurs
- `syncMetadata("fast")` ne sync **pas** le catalog (catalog uniquement en
  mode "full" = `/api/meta/sync` explicite)

Workflow utilisateur normal : amorce en jeu → push `builder_ready` →
catalog auto-rafraîchi via natural capture, **aucun heap scan déclenché**.

## Exemple : récupérer le state d'une session

```bash
# Lister les sessions actives
curl -s http://127.0.0.1:8765/api/sessions

# RPC sur la session N
curl -s -X POST http://127.0.0.1:8765/api/scripts/N/rpc \
  -H "Content-Type: application/json" \
  -d '{"method":"info","args":[]}'
```

Pour un dump raw des messages d'un script, lire le JSONL.
