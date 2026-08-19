# RPC API

## Endpoint

`POST /api/scripts/{run_session_id}/rpc`

```json
{"method": "string", "args": [...], "timeout": 10000}
```

`args` est un tableau positionnel passé tel quel à la fonction RPC côté
agent. `timeout` en millisecondes.

Récupérer le `run_session_id` via `GET /api/sessions`.

## Routes RESTful (préférées au RPC raw)

Le host expose des routes typées qui wrap les RPC + persistance.

### Campaign builder

- `GET /api/campaigns/builder-status` — état des captures (cheap, polled
  toutes les 5 s par le front)
- `POST /api/campaigns/catalog/refresh` — force un dump du catalog
  (autorise le heap scan fallback côté agent)
- `POST /api/campaigns/build` — body `{ campaignType, campaignId, locationIndex }`
  → BattleConfiguration JSON, persisté sous
  `frida/assets/public/configs/Campaign<N>/<id>_<idx>.json`

### Configs (captures passives)

- `GET /api/configs` — liste metadata
- `GET /api/configs/:id` — JSON complet d'une capture
- `DELETE /api/configs/:id` — supprimer

### Admin

- `GET /api/admin/status` — `{ tacticus: { running, gamePid, gamePath, … }, session, version }`
- `POST /api/admin/inject` — body `{}` (auto-discovery PID) ou `{ pid: N }`
- `GET /api/admin/candidates` — debug, tous les processes Tacticus détectés

### Sessions

- `GET /api/sessions`
- `POST /api/scripts/:id/stop` — cleanup graceful (handshake `cleanup` avec l'agent)
- `POST /api/scripts/:id/rpc` — RPC raw

### Métadonnées

- `POST /api/meta/sync` — sync enums + catalog (mode "full", autorise heap scan)

## RPC côté agent

### Campaign builder

| RPC | Args | Rôle |
|-----|------|------|
| `dumpCampaignCatalog` | `{ allowHeapScan?: boolean }` | Dump catalog complet (Standard/Mirror/Elite/Event types). Sans `allowHeapScan`, throw si pas de capture. Avec `allowHeapScan: true`, fallback heap scan GameConfigDto (~10 s freeze). |
| `buildCampaignConfig` | `{ campaignType: number, campaignId: string, locationIndex: number }` | BattleConfiguration JSON via path 2 progression-swap + per-faction amorce. ~60 ms round-trip. |
| `campaignBuilderStatus` | — | Cheap, jamais de scan. Retourne `{ hasGameConfig, hasUnitProgression, hasInstance, instance, gameConfig }`. |

### Standalone runner (simulation)

| RPC | Args | Rôle |
|-----|------|------|
| `initRunner` | `{ configJson: string }` | Désérialise une `BattleConfiguration` JSON, construit IdunRunner isolé via 2-arg ctor + Initialize(seed). Retourne `{ runnerId, seed }`. |
| `applyAddUnit` | `{ runnerId, unitId, playerId, col, row }` | Place une unit. |
| `startBattle` | `{ runnerId }` | `runner.StartMatch`. |
| `listRunners` | — | Liste runners actifs. |
| `disposeRunner` | `{ runnerId }` | Drop. |
| `cheatRunAiOnRunner` | `{ runnerId }` | CheatRunAIMessage sur un runner standalone. |

### Phase 2 — sim sur le live runner

| RPC | Args | Rôle |
|-----|------|------|
| `sim` | — | `buildStandaloneRunner` + catch-up via `state.log` + `CheatRunAI(standalone)` + capture. Retourne `{ simId, captured }`. |
| `commit` | `{ simId }` | Rejoue les messages capturés sur live. |
| `simAndCommit` | — | Wrapper. |
| `compareStandalone` | — | State digest + census + dumps state JSON + event traces via `send()`. |
| `compareNative` | — | Sanity-check : nos `top` = ReplayRecorder natif. |

### Cheat / debug

| RPC | Args | Rôle |
|-----|------|------|
| `cheatRunAi` | — | `CheatRunAIMessage` direct sur live (joue un tour). |
| `forceInstall` | — | Re-attache les hooks live (recorder). |
| `info` | — | Runner / listeners / gcRoot state. |
| `summary` | — | Counts + head/tail du log. |
| `dump` | — | Full log capturé. |
| `clear` | — | Reset log. |
| `battleStatus` | — | `{ stage, currentTurnPlayer, unitsAlive }`. |

### Métadonnées / introspection

| RPC | Args | Rôle |
|-----|------|------|
| `getGameVersion` | — | `{ version, identifier, productName, unityVersion }`. |
| `dumpEnums` | — | `{ "Namespace.EnumName": { "Value0": "0", ... } }` pour la liste curated. Keye par NOM, valeur en decimal exact (chaine) : un enum de flags 64 bits depasse `2^53`, et deux membres peuvent partager une valeur (alias, composite). |
| `dumpEnum` | `{ asm, ns, cls }` | Un seul enum. |
| `getUnitAssetMap` | — | `{ count, map }` — unitId → assetNaming. |
| `dumpAllUnitVisuals` | — | Depuis IdunUniverse capturé. |
| `resolveUnitVisual` | `unitId` | Un seul visual. |
| `unitVisualResolveStatus` | — | État captures IdunUniverse. |

## Format des messages push (WebSocket)

Le host re-broadcast tous les `send()` de l'agent via WS. Format :
```json
{
  "id": <ring buffer id>,
  "ts": "ISO date",
  "payload": {
    "type": "send",
    "payload": {
      "t": "<event type>",
      ...
    }
  }
}
```

Types observés :
- `diag` — `log()` du script, `{ msg }`
- `trace` — `traceEnter()`, `{ n, name }` (throttled per hook)
- `captured_config` — capture passive d'une battle :
  `{ id, mode, ts, bytes, campaignId, locationIndex, json }`
- `battle_event` — pendant simulation : `{ runnerId, msg, events, matchState }`
- `builder_ready` — push amorce signal : `{ via: "ctor" | "LoadBattle" }`
- `hook_ready` — boot agent (`{ name, version }`)
- `cleanup_done` — handshake stop

Le front filtre via `registerWsHandler(t, fn)` (pluggable, `frida/public/src/ws.js`).

## Exemples

### Build d'une node event tyranid

```bash
curl -s -X POST http://127.0.0.1:8765/api/campaigns/build \
  -H "Content-Type: application/json" \
  -d '{"campaignType": 4, "campaignId": "eventStandard5", "locationIndex": 0}'
# → { id, campaignType, campaignId, locationIndex, bytes, path, source, generatedAt }
```

### Force le dump du catalog

```bash
curl -s -X POST http://127.0.0.1:8765/api/campaigns/catalog/refresh
# → { version, bytes, path }   (version = Tacticus app version, ex "1.38.94")
```

### Status général

```bash
curl -s http://127.0.0.1:8765/api/admin/status
# → { tacticus: { running, gamePid, gamePath, … }, session, version }
```

### RPC raw

```bash
SID=$(curl -s http://127.0.0.1:8765/api/sessions | npx -y node-jq '.[0].id')

curl -s -X POST "http://127.0.0.1:8765/api/scripts/$SID/rpc" \
  -H "Content-Type: application/json" \
  -d '{"method":"campaignBuilderStatus","args":[]}'
```
