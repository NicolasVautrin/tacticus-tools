---
title: "tacticus-tools"
subtitle: "Frida hooking + browser builder pour WH40K Tacticus (Windows PC)"
date: "2026-05-03"
---

# tacticus-tools

Outils Frida + serveur Node.js pour **WH40K Tacticus** (build Windows PC,
Unity 6 IL2CPP). Capture passive de `BattleConfiguration` via les hooks
GameModeSource, génération à la demande de configs de campagne (events
inactifs inclus) via une mute-and-swap path sur la `CampaignProgression`
live, et frontend browser pour piloter le tout.

## Fonctionnalités

- **Injection Frida** locale (frida.getLocalDevice, pas de device distant)
  via auto-discovery du PID Tacticus
- **Capture passive** : chaque battle lancée naturellement par l'utilisateur
  est capturée et persistée comme `BattleConfiguration` JSON
- **Campaign builder** : génère la config de n'importe quelle node de
  campagne (Standard / Mirror / Elite / Event actif ou inactif) sans avoir
  à lancer la battle en jeu, via le pattern progression-swap
- **Frontend browser** : board interactif, gestion des captures (suppression,
  filtrage), builder hiérarchique CampaignType → Campaign → Node
- **WebSocket push** : notifications en temps réel (`builder_ready`,
  `captured_config`, `battle_event`) — pas de polling

## Prérequis

- **Tacticus PC installé** (`C:\Users\nicolasv\AppData\Local\tacticus\games\nb3o9lmt6c\`)
- **Node.js >= 18**, npm
- **Windows** (host Frida-node natif)

Pas d'`adb`, pas de device, pas de `frida-server` — `frida-node` parle
directement à `frida-core` embarqué dans le process Node.

## Installation

```bash
cd frida
npm install
```

## Workflow utilisateur

### 1. Lancer Tacticus

Lance Tacticus normalement (launcher → PLAY, ou directement
`Tacticus.exe`). **Attendre que le menu principal soit pleinement loaded**
(animations en boucle visibles).

### 2. Démarrer le host Node

```bash
cd frida
npm run dev
```

Host sur `http://127.0.0.1:8765`. Le front est exposé à `/view/`.

> ⚠️ Ne **jamais** activer hot-reload sur le host : casse les sessions Frida
> actives, peut crash Tacticus.

### 3. INJECT depuis le front

Ouvrir `http://127.0.0.1:8765/view/`. Le bandeau status en haut affiche
l'état de Tacticus :
- **Vert** : Tacticus tourne, hooks actifs
- **Orange** : Tacticus tourne mais pas de session — clic INJECT
- **Rouge** : Tacticus pas lancé

Cliquer INJECT → l'agent (~110 KB) est injecté, les hooks essentiels sont
posés. **Aucun heap scan, aucun freeze**.

### 4. Amorce

Ouvrir une campagne quelconque + cliquer un battle (n'importe lequel). Ce
clic naturel déclenche :
- `CampaignGameModeSource..ctor` (onLeave) → capture `lastSource`
- Push `{ t: "builder_ready" }` → le front auto-rafraîchit le catalog
- `UnitProgression.GetUnit` → capture `lastUnitProgression`
- `IdunUniverse.*` → capture l'univers (portraits, boards)

### 5. Builder

Le panel **Campaign Builder** (front) liste toutes les campagnes /
events disponibles. Cliquer une node :
- L'agent fait un **progression-swap** (mute mode) sur la live
  `CampaignProgression` — swap temporaire de `_campaignType`,
  `_campaignId`, `_battlesConfigCampaigns`
- Prechargement par faction (`UnitProgression.GetUnit` sur les enemy units du
  match) pour pré-résoudre les classes IL2CPP non-touchées
- Appel `LoadBattle(true)` → BattleConfiguration générée
- Restore tout dans le `finally`
- Round-trip ~60 ms pour un build typique

La config est persistée sur disque sous `frida/assets/public/configs/...`,
mirrorable côté browser pour rendu board + placements.

## Stop / cleanup

Front : bouton STOP de la session, ou côté host :

```bash
curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown
```

(ou Ctrl+C dans le terminal `npm run dev`)

## API HTTP

| Methode | Route | Description |
|:--------|:------|:------------|
| GET | `/api/admin/status` | Tacticus running? launcher? game PID + path? session info |
| POST | `/api/admin/inject` | Injection (body vide = auto-discovery du PID) |
| GET | `/api/sessions` | Sessions Frida actives |
| POST | `/api/scripts/:id/stop` | Stop session (cleanup graceful) |
| POST | `/api/scripts/:id/rpc` | RPC synchrone — body: `{method, args, timeout?}` |
| GET | `/api/configs` | Liste des `BattleConfiguration` capturées |
| GET | `/api/configs/:id` | JSON d'une capture |
| DELETE | `/api/configs/:id` | Supprimer une capture |
| GET | `/api/campaigns/builder-status` | État du builder (lastSource captured?) |
| POST | `/api/campaigns/catalog/refresh` | Force re-dump du catalog (heap scan autorisé) |
| POST | `/api/campaigns/build` | `{campaignType, campaignId, locationIndex}` → JSON BattleConfiguration |
| POST | `/api/_dev/shutdown` | Arrêt graceful du host |

WebSocket : `ws://127.0.0.1:8765/ws/run/:id` (reconnect via `?last_event_id=N`).
Messages push : `captured_config`, `battle_event`, `builder_ready`, `diag`, `trace`.

## Structure

```
frida/                    # Monorepo TypeScript actif
  hooks/                  # Script injecté (bundlé par frida-compile)
    il2cpp/               # Primitives IL2CPP (helpers, invoke, serializer, gc-root, mt)
    game/                 # Tacticus-specific (runner, match-state, ai-control, recorder, apply-stack)
    features/             # RPCs par feature
      campaign-builder.ts # Build à la demande via progression-swap
      mode-source-capture.ts  # Capture passive des battles naturelles
      launch.ts           # Standalone runner (sim-and-commit)
      sim/compare/cheat/  # Phase 2 — simulation
      configIo/status/...
    runtime/              # queue, main-pump, menu-pump, diag (log + traceEnter)
    controller.ts         # Aggregate features → rpc.exports
    main.ts               # Entrypoint
  host/                   # Serveur Node (Express + WS + Frida bridge)
    index.ts router.ts sessions.ts admin.ts ws.ts
    config-store.ts battle-store.ts meta-sync.ts
  public/                 # Front browser — servi sur /view/
    index.html app.js style.css
    src/                  # Modules JS (api, ws, board, configs, campaign-builder, ...)
  assets/
    raw/                  # AssetBundles extraits (gitignored)
    public/               # PNG + manifest.json — servi sur /assets/
      configs/            # BattleConfiguration captures + générées
  data/                   # Symbols.json, gameconfig dumps (gitignored)
  dist/                   # Bundles build (gitignored)

scripts/
  python/build_asset_manifest.py  # UnityPy → assets/public + manifest
  ghidra/GhidraDecompileGameAssembly.java  # Décompilation headless

hooks-legacy/             # One-shots historiques (cf. README local)
sources_win/              # Décompilation Ghidra (gitignored, lourd)
STATUS.md                 # État vivant du projet
```

## Caveats / pièges connus

- **Heap scans automatiques** : Frida suspend les threads cible pendant
  `Process.enumerateRanges` / `Memory.scan` (~10 s sur Tacticus PC). Au-delà
  de 5–10 s de freeze, **Tacticus's UnityFreezeDetector tue le process**.
  Heap scans gated par `allowHeapScan: true` (= bouton ↻ du front uniquement).
- **Broad-hooks sur méthodes UI hot** (`Get*`, `Has*`, `Is*`...) : la
  surcharge cumulée des trampolines déstabilise les cctor cascades IL2CPP
  pendant les transitions de scène. **Ne pas hooker des méthodes appelées
  par les rendus UI**.
- **Hook permanent sur property getters** appelés par les sérialisations
  Newtonsoft internes du jeu (ex. `GameConfigData.get_gameConfigDto` →
  ~27 000 appels/s) : amplifie une cctor cascade naturelle en hard crash.
  Préférer un appel à la demande (`unwrapGameConfig`).
- **Re-injection après stop** : peut wedge dans le même PID Tacticus.
  Relancer Tacticus avant de réinjecter.

Voir (file:///C:/Users/nicolasv/tacticus-tools/STATUS.md) pour l'état
courant + validations passées.
