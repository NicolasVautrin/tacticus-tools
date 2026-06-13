# RL pipeline — status (session compact-pre 2026-05-25)

## ✅ MoW arena-PvP dans le runner isolé — RÉSOLU (2026-06-13)

**Objectif atteint :** une battle **arena PvP avec MoW** tourne start-to-end dans
le runner isolé, **0 token**, et **l'IA joue les MoW**. Repro :
`scripts/python/_mow_arena_test.py` (scratch). Détail mémoire : [[project_mow_deploy_gate]].

**Preuve (build kqkbjqfb6c, session 3) :**
- `buildNormalizedBC(arena seed)` → patch `PredefinedMachines` = MoW pour Id 11 ET
  12 → `initAndStart` + 5 units joueur @TWPI0 → `observeBattle` :
  `byType '6':2` (= **2 Machine type-6, une par équipe**), `mows=2`
  (M96→team1/joueur, M95→team2/IA).
- Trace messages IA (`data/ai-traces/3-*.jsonl`) : `src=ai ActiveAbilityMessage
  unitId=95` ET `unitId=96` (×2 chacun) → **l'IA active les capacités des 2 MoW**.
  Une MoW d'artillerie (adeptExorcist) ne bouge pas (pas de MoveUnitMessage) — elle
  tire. Battle Finished en ~6 tours.

**Le « blocage MoW » précédent = triple faux diagnostic (corrigé) :**
1. Pas de static anonyme `DAT_1832d50b0` : c'est le MethodInfo de
   `Nullable<(TeamId,TeamPlayerIndex)>.get_HasValue` ; le deref pris pour un dict
   = generic-sharing IL2CPP. Vrai gate = `SpawnPointSetConfiguration.GroupForPlayer
   (BC.spawnConfig, teamId, tpi)` ≠ 0 — **dans la BC**. La BC arena a déjà
   `SpawnPointSet[0]` {TWPI:0,MoWPos:2}+{TWPI:1,MoWPos:1} → 11→TWPI0, 12→TWPI1 OK.
2. Machines orphelines = path `applyAddMachine` (runtime), PAS le path propre
   `PredefinedMachines → AddMachineOperation.Execute` (crée la machine seulement si
   `GetPlatform` OK, puis lie `MachinePlatformComponent.MachineId @+0x14`).
3. `observeBattle.mows=0` = bug projecteur (jetait la ligne si position plateforme
   illisible). **Corrigé** dans `match-state.ts` : itère sur Machine type-6 (source
   de vérité), position via plateforme liée si dispo → `mows.length == #machines`.

**Pièges pratiques :**
- BC brute (`:pvp` UnitId) → `initRunner` 500 (échec normalisation). **Toujours**
  passer par `buildNormalizedBC` ; MoW valides = `result.mow` (pool_mow).

**observeBattle.mows — composants MoW (type-6, vérifiés via RPC `dumpEntityComponents`) :**
15 comps, **ni HealthComponent, ni PositionComponent, ni UnitComponent** (= Parent,
EffectsOwned, TriggeredAbility, Owner, Attack, Crit*, ActiveAbility, UnitFlags,
Extra*, MachineComponent, ActorStatistics).
- `visualId` : **corrigé** — lu depuis `MachineComponent` (`: BaseUnitComponent`,
  VisualId@0x20). Vérifié M96→adeptExorcist(t1), M95→astraOrdnanceBattery(t2).
- `hp` = **null by design** (pas de HealthComponent — MoW non « tuable »).
- `pos` (col/row) = **null by design** (pas de PositionComponent ; position grille
  dérivée config : `MachineComponent.Position` slot 1/2 → board `MachineOfWarPosition`).
  `initialSlot` expose le slot.
- Lus OK : `ownerId`, `teamId`, `machineId`, `initialSlot`, `visualId`.
- RPC `dumpEntityComponents({runnerId, types, perType})` ajouté (introspection
  composants read-only, gardé comme outil de debug).

**Comment lancer :** `rl_collect_batch.py` (défaut = MoW aléatoire des 2 côtés via
BC normalisée) ou `--mow-player <unitId> --mow-ai <unitId>`. Le subsystem
`/api/mow/*` (events Machines of War) est **hors-sujet** pour ça.

---


## TL;DR

Pipeline RL complet **opérationnel** sur Campaign (sans MoW). Cette session
a ajouté **5 nouvelles tables/features** + **smooth heap scan** + **path
PvP/MoW investigué** :
- `tile_ref` (snapshot grille statique)
- `target_kind` (unit/tile/machine) sur stream_event
- `ability_state_change` (cooldown/state actives + triggered)
- `mow_state` (schema prêt, vide en Campaign)
- BC PvP **live captured** validé en condition réelle (Machine entity=6 spawne)
- Heap scans **tous chunked async** → reinject safe sans crash Tacticus

## Capture Frida (auto au boot)

- `move-options.ts` armed via RPC → action mask
- `winner-capture.ts` auto-armed → outcome (WonMatch×N validé)
- `message-trace.ts` auto-installed → messages + matchState snapshot + sub-events
- `mow_state` schema + `target_kind='machine'` prêts
- **Hooks GameModeSource** :
  - `CampaignGameModeSource..ctor` + `LoadBattle`
  - `MachinesOfWarEventGameModeSource..ctor` + `LoadBattleInternal`
  - **`PvpGameModeSource..ctor`** + hooks passifs sur 7 méthodes
    (`get_BattleGameMode`, `get_Name`, `HandleTurnStarted`,
    `PreventAIControl`, `PreventHumanControl`, `StartBattle`,
    `get_ControlsRunner`)

## Heap scan smooth (NOUVEAU)

**Tous** les heap scans convertis en `findInstanceByHeapScanChunked` :
- Chunks 4MB (configurable via `chunkMb`)
- `Memory.scan` ASYNC (callbacks vs `scanSync` bloquant)
- `await sleep(30ms)` entre chunks → main thread Tacticus respire
- UnityFreezeDetector ne kick pas, GPU TDR évité, socket PvP préservée

Fonctions converties :
- `findGameConfigDtoViaHeap` (était 18s sync ⚠️ → async chunked)
- `findCampaignGameModeSourceViaHeap` (était 17s sync ⚠️ → async chunked)
- `findUnitProgressionViaHeap` (était 300ms sync → async chunked)
- `findPvpGameModeSourceViaHeap` (NOUVEAU async chunked)
- `tryActiveDiscoveryOfSources` (sync → async, await tous les scans)
- `extractDependenciesAndNavigate` (auto-boot, sync → async)

Trade-off : scan total ~60-90s (vs 35s sync) mais zéro crash Tacticus.

## Postgres TACTICUS schema tacticus

Tables existantes :
- `batch` / `battle` (winner_*, outcome, reason_*)
- `message` + `unit_state` (1 row/UnitFoot, squad_id parent)
- `mow_state` (1 row/MachinePlatform, machine_id parent) — VIDE en Campaign
- `stream_event` (20 hot cols + JSONB tags + `target_kind`)
- `move_options_event`, `tile_ref`, `ability_state_change`
- Ref : `ref_active_ability` (323), `ref_triggered_ability` (557),
  `ref_effect` (682), `ref_unit` (103)
- Vues : `v_damage`, `v_effect_received_unit/tile`, `v_effect_tile_resolved`,
  `v_ability_state_latest`, `v_overwatch_ready`, `v_mows_per_battle`

Données accumulées sur Campaign :
- Batch 7 : 100 battles (92 OK), 962 turns, 7848 msgs, 124k unit_states,
  192k stream_events, 4245 move_options. 0 MoW (Campaign = pas de MoW spawn).

## MoW — diagnostic corrigé via Ghidra (2026-06-13)

**La section "MoW investigation" plus bas (2026-05) est en partie obsolète.**
Pipeline RL complet **re-validé end-to-end cette session** (build→start→playTurn→
Finished, ingest PG, 0 token — sims in-memory isolées). Le collecteur a déjà
les flags `--mow-player/--mow-ai/--list-mow` (catalogue 8 MoW dispo sans nav).

**Faits établis (Ghidra + DB) :**
- `RuleSet` = **fausse piste** : `diagPredefMachinesFires` monte à chaque setup →
  `SetupGameOperation$$Execute` (@180ef74b0) appelle `AddPredefinedMachines`
  **inconditionnellement**, pas de gate RuleSet à l'entrée.
- Le no-op est **dans** `AddPredefinedMachines` (@180ef4c00) : gates internes =
  (1) `GetPlayer` ok, (2) **check team/config** `thunk_FUN_1801f50e0(&team, DAT_1832d50b0)`
  (singleton moteur, *pas* la vue), (3) unitId non vide, (4) **`GroupForPlayer`**
  (@181147290) ≠ null → sinon machine skippée silencieusement.
- **`applyAddMachine` (AddMachineMessage runtime) ne suffit PAS** : crée l'entité
  Machine (byType type-6) mais **AUCUNE MachinePlatform (type-7)** → MoW non
  déployée sur le board → **l'IA ne la joue pas** (DB : 0 `MachineHit`, 0
  mouvement machine, events 100% units ; `mow_state`=0 → d'où `mo=0`).
- Le board arena (`data/arena-battle-config-newtonsoft.json`) n'a **que TWPI 0/1**
  (3 SpawnPointSets, tous units) → **pas de spawn-set MoW**. Sur 782 board dumps :
  TWPI 2=85, 3=18 boards, mais **0 board avec TWPI 2 ET 3 dans le même sps** +
  units. `SupportsMachinesOfWar` (vue, @181628930) = switch sur GameMode (faux pour
  modes {3,5,10,11,12,13}) — mais c'est **côté vue**, pas le gate moteur.

**Gate moteur identifié (RE approfondie 2026-06-13) :**
- Plateformes (type-7) créées **inconditionnellement** au setup
  (`SetupGameOperation$$Execute` → `FUN_180003b40(0x8c,...,2)` & `(...,1)` =
  `AddMachineOfWarPlatformOperation` slots 2/1). Donc type-7=2 toujours présent.
- `AddMachineOperation$$Execute` → `GetPlatform(slot)` cherche une plateforme au
  slot du machine ; **échoue (log err niv.4) si absente** → d'où l'orphelin du
  bypass runtime `applyAddMachine` (appelé après StartMatch).
- **LE GATE** dans `AddPredefinedMachines` ET `BattleQuery$$GetPositionMachineForPlayer`
  (même pattern) : `pcVar = TryGetValue(team, DAT_1832d50b0_config->+0xc0->+8->+0x80)`
  ; `if (*pcVar==0) return/skip`. C'est une **éligibilité MoW par team** lue dans
  un **singleton statique** (`DAT_1832d50b0`, lazy-init `FUN_1801e6880`, lu aussi
  par `GetSpawnPointsForPlayer`/`GetMachineOfWarPositionForPlayer`). Le spawn group
  (`GroupForPlayer`) est **en aval** du gate → testé empiriquement : ajouter un
  SpawnPointGroup TWPI=2 ne change rien (battle 237 : 0 event machine).
- Comme le config est **statique** (pas per-BC), patcher la BC JSON
  (RuleSet/GameMode/Board) ne le peuple pas → explique l'inefficacité du
  `RuleSet=0` JSON. La team de nos joueurs (11→team1, 12→team2) n'est pas
  reconnue MoW-éligible dans ce config.

**Reste à identifier** : la classe de `DAT_1832d50b0` + ce qui peuple son dict
team→éligibilité MoW (probablement le setup de mode/RuleSet côté GameModeSource,
absent du runner isolé). Si confirmé : déploiement MoW offline = nécessite de
peupler ce static (ou capture live). **Décision produit en attente.**
(cf. `scripts/python/_mow_probe.py` scratch, bypass retiré du collecteur.)

## MoW investigation (cette session)

### Constats
- Campaign mode = **AUCUNE MoW spawned** (par design)
- `BC.PredefinedMachines` vide en Campaign
- Le gate dans `SetupGameOperation.Execute()` :
  - **`BC.RuleSet`** doit être set (Nullable<SyncPvpRuleSet> non-null)
  - Patch validé : avec `setBattleConfigRuleSet(0)` → fires=2 (`AddPredefinedMachines` appelée)
- Mais en Campaign avec MoW UnitId injecté → **AddPredefinedMachines no-op** :
  templates pas reconnus comme MoW valides hors contexte PvP
- En PvP live → **Machine entity spawned correctement** (validated byType['6']=1)

### Format unitId
- Campaign : `unitId` plain (ex. `astraOrdnance`, `tauBroadside`)
- PvP : suffix `:pvp` requis (ex. `astraOrdnanceBattery:pvp`, `tauBroadside:pvp`)
- Templates `:pvp` chargés UNIQUEMENT si types Mono PvP init (= user a navigué vers PvP)

### RPCs MoW codés (battle-config.ts + launch.ts)
- `addPredefinedMachine({playerId, unitId})` — patch BC.PredefinedMachines
- `applyAddMachine({runnerId, playerId, unitId})` — runtime AddMachineMessage
- `setBattleConfigRuleSet({rule})` — set BC.RuleSet
- `setBattleConfigGameMode({mode})` — set BC.GameMode
- `discoverSources({chunkMb, pauseMs})` — manual heap scan trigger (smooth)
- `dumpBattleConfig` — serialize live BC en JSON via Newtonsoft
- `diagPredefMachinesFires` — diag hook AddPredefinedMachines counter

### Path PvP live validé
Avec une battle PvP loaded in-game :
- `PvpGameModeSource._currentBattle @+0xD8` lu
- BC `Id=PvpBattle`, `gameMode=1`, `predefMachines=[{playerId:12, unitId:'tyranBiovore:pvp'}]`
- 5 AI units `:pvp` dans PredefinedUnits
- `buildPatchedRunner` sur cette BC → byType `'6': 1` (Machine spawned !)
- `applyAddMachine` player → byType `'6': 2`

### initRunner(arenaJsonDump) crash
- Le dump JSON `data/arena-battle-config-newtonsoft.json` ne contient PAS
  `RuleSet` (NullValueHandling.Ignore Newtonsoft)
- `initRunner` sur ce JSON → 20+ `native_crash mono_type_size` (types Mono
  PvP pas init dans session Campaign-only) — **CRASH**
- Conséquence : dump JSON statique pas suffisant pour reproduire BC PvP
  hors session live

## Tasks state (post-compact)

- ✓ #18 mow_state (capture + DB + ingest)
- ✓ #19 addPredefinedMachine + applyAddMachine
- ✓ #21 Capturer BC PvP/MoW live
- ✓ #23 Heap scans chunked async
- ⏳ #22 Refactor RL pipeline pour BC PvP (= ce qu'il reste à faire)
- ⏳ #24 dumpBattleConfig + roundtrip JSON → initRunner (path testable)
- ⏸️ #13 Persister singleton ptrs côté host (post-reinject)

## Files clés

- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/battle-config.ts) — patch BC, RPCs PvP/MoW, dumpBattleConfig
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/campaign-builder.ts) — heap scans chunked + ctor hooks + Pvp passive
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/launch.ts) — applyAddMachine, applyAddUnit
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/auto-boot.ts) — async migration
- (file:///C:/Users/nicolasv/tacticus-tools/scripts/sql/) — migrations 001-011
- (file:///C:/Users/nicolasv/tacticus-tools/data/arena-battle-config-newtonsoft.json) — dump partiel (RuleSet manquant)

## Reprise pratique post-compact

```bash
# 1. Si Tacticus relancé (souvent vu le nombre de crashes session précédente)
curl -s http://127.0.0.1:8765/api/admin/status
curl -s -X POST http://127.0.0.1:8765/api/admin/inject -d '{}'

# 2. Au boot, auto-boot launchera tryActiveDiscoveryOfSources async
#    (chunks 4MB + yield 30ms). Plus de crash UnityFreezeDetector.
#    Total ~60-90s pour les 3 scans (GameConfigDto + UnitProgression + Campaign).

# 3. Pour battle PvP live :
#    a) User navigue in-game vers PvP/Arena, charge battle, deployment screen
#    b) Ctor hook fire (instance fresh) OU discoverSources si reinject
curl -s -X POST .../rpc -d '{"method":"discoverSources","args":[{"chunkMb":4,"pauseMs":30}],"timeout":120000}'
#    c) inspect → vérifier Id=PvpBattle, gameMode=1, predefMachines
curl -s -X POST .../rpc -d '{"method":"inspectBattleConfig","args":[],"timeout":15000}'
#    d) buildPatchedRunner → byType doit avoir '6': 1+ (Machine)

# 4. Pour test JSON snapshot (task #24) :
#    a) dumpBattleConfig sur BC PvP live → JSON
#    b) save JSON
#    c) initRunner({configJson, seed}) → check Machine spawn

# 5. Task #22 :
#    Refactor rl_collect_batch.py pour partir d'une BC PvP capturée
#    au lieu de Campaign. Inclura les MoW dans le dataset RL.
```

## Points à creuser

1. **Dans buildCampaignConfig** : fallback heap scan inline retiré
   (queueOnMainThread bloquait). User doit `discoverSources` AVANT si BC absent.
2. **task #22** : refactor rl_collect_batch pour BC PvP → MoW dans data RL
3. **task #24** : dumpBattleConfig + initRunner(JSON) roundtrip pour battles
   reproductibles sans dépendre du live state
