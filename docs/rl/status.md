# RL pipeline — status (session compact-pre 2026-05-25)

## ⏩ ÉTAT COURANT — reprise 2026-06-14 (arbre de groupes + attribution complète)

**Objectif (rappelé) :** **imitation learning d'abord** (imiter l'IA in-game depuis
les démonstrations collectées), **RL ensuite**. Dataset = démonstrations expertes.
Cf. mémoire `[[project_rl_objective_il_first]]`. Les besoins RL précis (state features,
action space, reward) restent **à re-clarifier** — c'est le prochain gros sujet.

**Infra live :** host `:8765` (background, session warm). Build **kqkbjqfb6c**.
Postgres **TACTICUS** `:5433` schema `tacticus` (creds `.env`). ghidra-mcp `:13337`.
⚠️ **`rl_collect_batch` se lance avec `python` (psycopg3), PAS `py`** (psycopg2 → ingest
silencieusement off). Requêtes/migrations manuelles : `py` (psycopg2). Cf. mémoire
`[[feedback_rl_batch_python_psycopg3]]`.

**Dataset courant :** re-collecte propre **48 battles** (50 lancées, ~2 perdues à
l'ingest) **avec l'arbre matérialisé**. `stream_event` ~61k, `stream_group` ~38k.

**Acquis majeur cette session — l'arbre de groupes :** le « trou » mêlée/distance
était une **capture incomplète** : on ne hookait pas `StreamDispatcher.FinishGroup`
(fermetures de groupe). Corrigé → arbre complet `stream_group` (parent_group_id,
`WITH RECURSIVE`). Du coup attribution **complète** :
- **mêlée/distance = 100% des vraies attaques d'arme** (colonne `weapon_is_melee`,
  remplie depuis le `Info`(arme) du scope + fallback positionnel borné pour les ~3%).
- **`damage_kind`** (015) : normal_melee / normal_ranged / effect / mow_artillery /
  ability / unknown. Le « 32% non-classé » = **70% ability + 24% artillerie MoW +
  ~6% (fixé)** — pas un trou. `caster_entity` (acteur via l'arbre).
- **overwatch** quantifiable (`effect_type=1009`=Overwatch_AutoAttack ; `5`=Fire/DoT).
- **soins** (`v_heal` : healer Caster_Id + amount + cleanse), **réparations**
  (`v_repair` : montant = delta `hp_remaining`, RepairInfo restaure les PV pas l'armure).
- enums dénormalisés (`*_name`) + FK vers ref tables (`enum_maps.py`, build-aware).

**Commits poussés (master) cette session :** `e55933c` (hook FinishGroup), `df04e4c`
(arbre + enum FK/names + attribution 012/013/014), `dac7aee` (doc schéma DB),
`3a8a6e6` (damage_kind + fallback mêlée + v_heal/v_repair 015), `1dae793` (doc
catégories/soins). Migrations `001`→`015`. Générateurs : `rl_gen_ref_tables.py`,
`rl_gen_enum_columns.py`. Doc schéma complète :
`.claude/skills/tacticus/references/rl-database.md`.

**Pièges/règles à NE PAS reperdre :** `effect_id` ≠ `effect_type` (instance vs enum,
pas de FK sur effect_id) ; `attacker_id`/`caster_id` ↔ `unit_state.squad_id` (PAS
`unit_id`), MoW ↔ `mow_state.machine_id` ; arbre = re-collecte obligatoire (battles
pré-FinishGroup n'ont pas le nesting).

**Exploré mais ABANDONNÉ (pas codé) — summons :** la donnée est là (`unit_is_summoned`,
`unit_spawn_source` [Ability/Deployment], `unit_parent_id`, `Unit_Foot_Tile_Id`=placement).
Constats : 409 summons/48 battles (~8,5/b), **9,7% des dégâts**, **87% meurent**
(consommables), Genestealers + Biovore (Spore Mines) en tête. Passe summon proposée
(vue `v_summon` + mapping summoner→spawn + stats) **non faite** — l'utilisateur a
laissé tomber.

**Prochain gros sujet :** re-clarifier l'IL — définir **features d'état** (unit_state/
mow_state/tree → tenseur) et **espace d'action** de l'expert (move / attack / ability /
summon) pour bâtir l'extracteur de paires (état, action).

---

## ⏩ reprise 2026-06-13 (dataset MoW + analytics)

**Où on en est :** MoW arena-PvP **résolu et exploité**. 85 battles MoW en
Postgres, attribution des dégâts par caster en colonnes, analyse en cours.

**Infra live :** host `npm run dev` sur `:8765` (background). Tacticus build
**kqkbjqfb6c**. ghidra-mcp `:13337`. Postgres : db **TACTICUS**, `:5433`, schema
`tacticus`, creds dans `.env`. Session Frida ~20 (a changé au fil des reinjects).

**Dataset DB (85 battles MoW, 0 token) :** `battle` 85 (44 joueur/41 IA, 100%
WonMatch, avg 10 tours), `mow_state` 13 678, `stream_event` 170 885, `unit_state`
106 218, `message` 6 839. **Toutes les battles non-MoW + 797 MB de traces JSONL
ont été supprimées** (DB + ai-traces ne contiennent plus que du MoW).

**Commits poussés (master) :** `0cf03d5` (arena MoW + projecteur `mows` +
`dumpEntityComponents`), `c00ba84` (skill refs rpc-api/hooks), `cae83b6` (filtre
board MoW-capable + denylist necroPlasmancer), `b2e35e3` (GC pin fix).

**NON COMMITÉ (à committer) — analytics :**
- `scripts/sql/012_stream_event_attribution.sql` (NOUVEAU, **déjà appliqué à la
  DB** : 21 colonnes attribution/combat-quality/lifecycle + backfill 170k +
  index + vue `v_damage_by_caster`).
- `scripts/python/rl_collect_batch.py` (wiring des 21 colonnes dans l'ingest —
  50/50 vérifié) + (déjà commité avant : filtre board + denylist).
- `scripts/python/rl_ingest_postgres.py` (ajout ingest `mow_state` — chemin post-hoc).
- Commit proposé : `feat(rl): promote attribution/combat-quality tags to
  stream_event columns + mow_state ingest`.

**Diagnostics clés (acquis cette session) :**
- Le « blocage MoW » était **necroPlasmancer** : seule unité inspawnable (97/98
  OK), throw exception managée au spawn. **PAS** le GC ni un static-gate (ces 2
  théories étaient fausses — vérifier le **déterminisme** avant toute théorie
  stochastique). Denylist : `_load_unspawnable()` + `data/unspawnable_rank17.json`
  (cache probe) + fallback `UNSPAWNABLE_FALLBACK={"necroPlasmancer"}`.
- **Freeze** : PAS inhérent aux batches (50 battles d'affilée 1 session = OK).
  Venait du benchmark non-pacé + du probe (storm d'exceptions). **amorce
  nécessaire seulement au reinject** (cold-start), PAS par chunk — le
  reinject-par-chunk re-entrait une battle campagne à chaque fois (= « déconne »).
  → batch normal : 1 reinject + 1 amorce, puis `rl_collect_batch -n N` d'affilée.
- Attribution : le caster est **dans les tags de l'event** (`Attacker_Id`,
  `Caster_Id`, `Effect_SourceId`), pas besoin de corréler par fenêtre. Promu en
  colonnes (012). `v_damage_by_caster` (source_id = coalesce attacker/effect/caster).
- MoW entity (type-6) : 15 composants, **ni HealthComponent ni PositionComponent
  ni UnitComponent** → `hp/pos` null by-design ; `visualId` lu via MachineComponent
  (BaseUnitComponent.VisualId@0x20). RPC diag `dumpEntityComponents`.
- `UnitStats_*_Override` : **gardés en JSONB** (0,05% des lignes, sentinelle INT_MIN).

**Analyse (dernier run, 85 battles) :**
- MoW ≈ **9,3% des dégâts, 9,4% des member-kills** (651 activations ability,
  85/85 battles, avg 7,7/battle). MoW = artillerie : que des `ActiveAbilityMessage`,
  zéro `MoveUnitMessage`.
- Top dealers : deathTyphus (unit, 263k), astraOrdnanceBattery (MoW 208k),
  adeptExorcist (MoW 184k)… crit **très rare (0,3% global)**, overkill 7,5%.
**🔑 `Effect_Type` = LE marqueur d'attribution des dégâts (acquis 2026-06-13, session Q&A) :**
Le « 2 trous d'attribution » noté précédemment était **FAUX**. Les dégâts
d'effet/ability/overwatch/DoT **SONT** dans `UnitDamaged` — ils portent un tag
`Effect_Type = <id effet>` (absent sur les attaques d'arme classiques). C'est CE
champ qui les distingue, pas les tags `*TriggeredAbility*` (j'avais vérifié les
mauvais). Dégâts effet-sourcés observés sur les 85 battles :

| `Effect_Type` | tirs | dégâts | battles | nature |
|---|---|---|---|---|
| **1009** | 304 | 289 704 | 43/85 | **overwatch** (`0x3f1`, confirmé binaire) |
| 5 | 199 | 77 329 | 53 | DoT (poison/bleed/burn — piste tyranBiovore) |
| 1077 | 18 | 18 180 | 3 | ability spécifique |
| 1476 | 15 | 11 406 | 10 | ability spécifique |

- **Overwatch mesurable** : 304 tirs / 289 704 dmg / 26 member-kills / 31 tireurs.
  Top : **tauCrisis** (110 tirs, 123k dmg, 14 kills, 8 battles), ultraSmnDreadnought,
  darkaCompanion, necroDestroyer, admecDestroyer, **eldarMauganRa** (18/3 battles).
  → le blind-spot « l'IA fonce dans l'overwatch » (cf. [[project_overwatch_blindspot]])
  est **quantifiable** dès maintenant, sans hook supplémentaire.
- **Gap biovore/DoT résolu** : ses dégâts ne sont PAS « seulement dans ReceiveEffect » ;
  ils sont dans `UnitDamaged` taggés `Effect_Type=5`.
- **Piège de join** : `Attacker_Id`/`attacker_id` ↔ `unit_state.squad_id` (PAS `unit_id`).
  Join sur `unit_id` renvoie tout en `None`. (cf. commentaire migration 012.)

**Turn-order = dynamique, pas figé (acquis 2026-06-13) :** l'ordre d'activation
est l'**Initiative recalculée à chaque round** (file unique 2 camps mélangés, pas
d'alternance d'équipe). Il change round-à-round (réordonnancement init + morts +
invocations) — démontré sur battle 239 (R1 `89 94 96 98…` vs R2 `98 90 92 94…`).
**Reproductible** pour un triplet (seed, rosters, board) identique, mais jamais
constant. `unit_state` **ne capture pas l'initiative** (colonnes : col,row,hp,
hp_max,owner_id,team_id,visual_id,rank,is_dead) → à ajouter si on veut feature-iser
l'ordre. Ordre reconstructible a posteriori via séquence `MoveUnit`/`ActiveAbility`
par `msg_idx` (le `unit_id_raw` du `CheatRunAIMessage` parent n'est PAS l'acteur :
= attacker seulement 12/9578 fois → inutile pour le contexte de tour).

**Playbooks = policy IA, lisible via ghidra-mcp (acquis 2026-06-13) :** toute l'IA
de combat est dans le namespace `IdunBattle.AI.Playbook` (~150-200 classes,
décompilables). Hiérarchie `BasePlaybook → Playbook<T> → Comparable/NonComparable`,
+ `TriggeredAbilityPlaybook<T>` / `TriggeredAbilityNonOwnerPlaybook<T>`. Méthodes
clés : `GenerateAction`, `GetUtilityValue`, `CalculateUtilityFromDamageEvent`,
`Generate{Attack,Heal,…}Predictions`, `ShouldExecute`/`ShouldEvaluate`. Ex lisible :
`BringerOfDespairPlaybook$$ShouldExecute = !WillNormalAttackKill(...)`. C'est la
couche par-ability au-dessus des poids `BattleConfiguration.Utilities`. (cf.
[[reference_playbook_ai_policy]])

**NB `effect_type` déjà colonne** : la colonne `stream_event.effect_type` existe
déjà (migration 007, bloc effects) et est peuplée (536/536), `rl_collect_batch`
l'insère déjà. Pas de migration à écrire pour ça — `Effect_Type` est déjà sorti
des tags.

**Prochaines étapes :** committer l'analytics ; **tables de référence des enums +
FK** (effect_type, active/passive_ability_type, damage_profile_type,
unit_spawn_source, step_code… → id↔nom depuis les enums IL2CPP ; cf.
`scripts/python/rl_gen_ref_tables.py` non tracké) ; stats overwatch par unité (taux
suicide IA) ; plus de stats (win-rate vs dmg MoW, dégâts par `active_ability_type`).
Le flag mêlée/distance (`Attack_Weapon_IsMelee` NULL sur UnitDamaged) reste le seul
vrai trou ouvert.

---

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
