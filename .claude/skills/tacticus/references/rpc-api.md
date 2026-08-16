# RPC API — agent Frida ↔ host

RPC exposés par l'agent injecté (`frida/hooks/`), appelés par le host Node et
les scripts `scripts/python/`.

**Surface re-dérivée le 2026-08-05 : 320 handlers** — le chiffre ne se cite pas, il se
re-dérive (`python scripts/python/probe_480r8_rpc_ventilation.py`, étape 1). Cette ligne a
annoncé **257** pendant un mois pour une surface qui en portait **321** : un catalogue périmé
fait conclure « ce RPC n'existe pas » sur un RPC vivant.

Ce fichier documente individuellement les RPC du **workflow actif** (consommés par `rl_duel.py`,
`predict_validate.py`, `pathfind_validate.py`, `rl_probe_step.py`, `rl_collect_batch.py`,
`engine_validate.py`, tests) et **nomme** le reste par famille de diagnostic (§ Familles).
La source fait foi.

⚠ **Un RPC qui n'est écrit NULLE PART est inutilisable, pas « disponible »** : pour invoquer
`{"method": "<nom>"}` il faut connaître le nom. #480-r8 a mesuré que **154 des 320** n'ont aucun
appelant statique, dont **83** qu'aucun code, aucune doc et aucun message de commit ne
mentionnait — ils étaient hors d'atteinte de fait. C'est pourquoi les familles ci-dessous sont
NOMMÉES et non plus résumées par un patron (`dump*`) : un patron ne rend aucun nom découvrable.

## Mécanisme

Chaque feature fait `register(ctx)` et attache ses handlers sur `ctx.rpc.<nom>`
(voir [hooks.md](hooks.md)). Appel host :

```
POST /api/scripts/<sessionId>/rpc   { "method","args":[...],"timeout":<ms> }
```

Réponse `{ "result" }` (ou `{ "error" }`, HTTP 500 si throw). `args` positionnel ;
la plupart des RPC = **un seul objet d'options** → `args: [{ ... }]`. Session :
`GET /api/admin/status` → `.session.id`, **change à chaque (ré)inject**. Tout RPC
touchant l'état passe par `queueOnMainThread` (pump Unity). **Ordre = dernier
`register` gagne** : `battleStatus`/`dumpEntityComponents` d'`ai-step` écrasent
les homonymes de `status.ts`/`observe.ts`.

## Cycle de vie du runner isolé (RL / sim 0-token)

Ordre obligatoire (détails CLAUDE.md « Workflow RL ») :

- **`warmupGameSingletons({ force?, stopAfterCapture? })`** (`warmup-singletons.ts`) — nav UI
  AUTONOME (capture `lastSource` + init classes battle IL2CPP, sinon crash 0x2c).
  1× par session après chaque (ré)inject, avant tout autre RPC. Aucun clic humain.
  **Rend la main sur l'ÉCRAN CAMPAGNE** (`retreat-to-campaign` + `wait-back-to-campaign`), et
  sait aussi SORTIR SEUL d'un écran de bataille hérité (étape `recover-from-battle`). ~12 s.
  `stopAfterCapture: true` (explicite) coupe après la capture et laisse le jeu en bataille.
  ⚠ Ne PAS l'appeler à la main après un `POST /api/admin/inject` : celui-ci l'enchaîne déjà.
  Session vivante mais froide → `POST /api/admin/warmup`.
  **Se rattrape SEUL d'un wedge post-retraite (#390)** : si le nœud de campagne ne revient
  pas, le cycle ferme les popups modaux puis invoque `IdunNavigation.ToCampaign` — 2 tentatives,
  +40 s au pire, **0 s sur le chemin nominal**. Le rattrapage ne rend pas le wedge muet :
  `steps` garde `wait-back-to-campaign` à `ok:false`, ajoute les `wedge-remedy-*`, et le
  résultat porte **`recovered`** = le motif qui a porté. Un `ok:false` dit désormais lequel des
  cinq motifs a échoué — dont `scene-meta-absente`, le seul qui exige encore de relancer le jeu.
- **`buildNormalizedBC({ baseBcJson, target{Rank,ProgressionIndex,Rarity,Level,StarLevel,AbilityLevel}, boardJson?, spawnPointSetIndex? })`**
  (`normalize-bc.ts`) → `{ ok, configJson, normalized:[unitId], mow:[unitId] }`.
  Résout une BC seed au rank cible ; passage obligé (les UnitId `:pvp` bruts
  échouent la désérialisation).
- **`initAndStart({ configJson, seed?, playerUnits:[{unitId,playerId,col,row}], recordReplay? })`**
  (`launch.ts`) → `{ runnerId, seed, addUnits, startEventCount }`. Atomique :
  deserialize → buildRunner (Initialize auto-spawn PredefinedUnits/Machines) →
  AddUnit joueur → StartMatch. Variante 3-temps : `initRunner` + `applyAddUnit`×N
  (+ `applyAddMachine`/`applyAddUnitSrc`) + `startBattle({ runnerId })`.
  `recordReplay` (défaut **false**, #477-r1) ARME l'enregistreur natif :
  `IdunBattle.Runner.IdunRunner$$Initialize` ne fait `SetupReplayRecorder` que si
  `IdunRunnerOptions.RecordReplay` est vrai — **sans lui, `replayOutputStream` rend un
  flux VIDE sans erreur**. Côté CLI : `rl_duel build --record-replay`.
- **`replayOutputStream({ runnerId, maxChars? })`** (`replay-output-stream.ts`) →
  `{ ok, outputStream, outputStreamLength, truncated, rngEventCount, stepCount,
  recorderArmed, err }`. Trace textuelle canonique de la bataille
  (`IdunBattleLogic.Replay.Replay$$GetWholeBattleOutputStream`), celle que
  `Runner.ReplayValidator$$CompareOutputStream` compare caractère par caractère.
  `recorderArmed:false` ⇒ le runner a été construit sans `recordReplay` : le flux est
  vide PAR CONSTRUCTION, `ok` est `false` et `err` le dit.
  **`replayOutputStreamStatus()`** rend la résolution des symboles **et** `runners[]`
  avec leur armement — les quatre booléens de résolution ne disent rien du contenu.
- **`buildPatchedRunner(patch?)`** (`battle-config.ts`) → `{ ok, runnerId, runner,
  seed, bcPtr, patch }`. Runner depuis la BC live capturée avec patch in-place
  (aiUnits/randomizeAi/templateOverrides). Warmup préalable requis.
  `spawnPredefinedUnits({ runnerId })` / `addPredefinedMachine({ playerId, unitId,… })`
  = leviers manuels sur cette BC live.
- **`observeBattle({ runnerId })`** (`observe.ts`) → état projeté (shape ci-dessous).
- **`autoPlayRunner({ runnerId, maxTurns? })`** (`cheat.ts`) → joue toute la
  battle (boucle `CheatRunAIMessage`, 1/tour) → `{ ok, turns, reachedFinished,
  finalStage, hitMaxTurns, history }`. Tour par tour : `playTurn({ runnerId })`.
  Sur le runner LIVE : `cheatRunAi()`.
- **`battleStatus({ runnerId })`** (ai-step) — poll LÉGER (stage + currentPlayer +
  winner + unitsAlive, sans projection) ; base du long-poll `/api/selfplay/:id/await`.
- **`dumpRng({ runnerId })`** → `{ mt:[624], mti, callCount }` — MT19937 de combat
  pour synchroniser `engine/runner/prng.py`.
- **`disposeRunner({ runnerId })`** / **`listRunners()`** (`launch.ts`).

Coexistence (défaut) : `initAndStart`/`buildPatchedRunner` ne disposent
**JAMAIS** les runners frères. Garde-ressource = cap dur **`MAX_RUNNERS`**
(`runner-registry.ts`, budget gcRoot ~900 handles) : au cap le build **REFUSE**
avec la liste des runnerIds actifs. Discipline : chaque acteur DISPOSE ses
runners en fin de passe ; `rl_duel build` remplace le runner de SON
`--state-file` (replace scopé, jamais les frères). Exceptions à sémantique
**replace** conservée : `initRunner` + `loadFromSavedBundle` (chemins UI
BUILD/LOAD du front = ops de session, exclusives). cf. docs/rl/design.md
§Multi-runner.

### Shape `observeBattle`

`{ ok, stage, stageName, currentPlayer, counts, byType, units[], mows[] }`.
`units` = `{ entityId, squadId, visualId, teamId, playerId, col, row, hp, hpMax,
rank, isDead }` ; `mows` = `{ id, machineId, entityType:6, pos, hp, maxHp,
ownerId, teamId, visualId, rank, isDead, initialSlot }`. `byType` = `EntityType`
(Tile=0, Unit=1, Match=2, Effect=3, Player=4, UnitFoot=5, Machine=6,
MachinePlatform=7, EnvironmentAbility=8). MoW : `hp`/`pos` = `null` by design
(entité Machine sans Health/Position) ; visualId/teamId/ownerId/initialSlot fiables.

## Décision & action (oracle live — `ai-step/rpc-view.ts`)

Read-only sauf `applyAction` (`mutated=false` attendu). Cœur oracle + harnais moteur.

- **`decisionView({ runnerId, maxRank?=6, allAbilities?=false })`** — vue
  décision-ready : méta + units (pos/HP/team/alive/hasAction/ranged/abilities) +
  `toActivate` + `attackPlans` rankés + `dangerZone` + `roundCap` + `effects` live.
  Dégât `attackPlans` (#103) : les ACTIVES/granted passent par l'ORACLE PLAYBOOK
  per-ability (`MakeDamagePredictions`, cf. `playbook-predict.ts`) → correct pour les
  spéciales CONFIG-based (PlasmaCannon/SpiritLeech…) que `GetAllPredictions` sous-/
  zéro-value ; l'attaque NORMALE reste sur `GetAllPredictions` (son preview natif
  authoritatif, ~4× moins cher). K!/K? via seuils willKill/mightKill (post floor-Resilient).
- **`combatSnapshot({ runnerId })`** — stats de combat RÉSOLUES par unité
  (`GetStat`) ; seed one-shot du prédicteur offline.
- **`tileMeta({ runnerId })`** — élévation + terrain + effets par tuile.
- **`boardGraph({ runnerId })`** — adjacence hex native (`GetAdjacentTiles`) +
  `walkable` + élévation ; graphe STATIQUE, capter 1×/battle.
- **`pathDistToEnemies({ runnerId, unitId })`** — par tuile atteignable,
  distance-CHEMIN (`Pathfinders.GetPath`) à l'ennemi le plus proche (≠ dist hex).
  Miroir COMPLET des filtres `FindClosestEnemy IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext` (#26, prédicats NATIFS
  invoqués) : `!CurrentOwnerIsEnvironment` / `IsTargetable` / `!IsIrrelevantObject`
  / vivant, puis restriction `GetOnlyTargets` (taunt — validé live CrushingClaws).
  Renvoie aussi `enemies:[{id,col,row}]` (cibles retenues → `ctx.tgt_epos`, seed du
  fallback hex MinDist) + `onlyTargetsCount`/`onlyTargetsUnmatched` (set vidé par la
  restriction = dégradation sûre non restreinte, flaggée).
- **`aiMovableTiles({ runnerId, side?, dangerZone?, threat?, extraRange?, overrideRange? })`**
  — tuiles légales par unité contrôlée (`GetMovableTilesFor`).
- **`aiAttackRank({ runnerId, unitId?, targetId?, abilityType?, allAbilities?, maxRank?=8, overrideRange? })`**
  — positions d'attaque RANKÉES par (unit,target,ability) via `GetBestTileToAttackFrom`.
- **`abilityTargets({ runnerId, unitId?, abilityType?, allAbilities?=true })`** —
  cibles légales par (unit,ability) incl. non-attaque. `targets` = move inclus ;
  `fromHere` = sans bouger. Absent des deux ⇒ no-op certain.
- **`abilityReason({ runnerId, casterId, abilityType, targetId? })`** — raison
  structurée d'un cast invalide (flags `TargetingRule` en noms).
- **`aiPredict({ runnerId, unitId, targetId, abilityType?, col?, row?, fresh? })`** —
  PREVIEW de dégât decisionView (`GetAllPredictions`). ⚠ Attack-based quel que soit
  l'abilityType — PAS l'oracle du dégât per-ability du playbook (utiliser aiPlaybookPredict).
- **`aiPlaybookPredict({ runnerId, unitId, targetId, abilityType, level?, multiplier? })`** —
  ORACLE DIRECT du playbook per-ability : invoque `<Ability>Playbook.MakeDamagePredictions`
  natif → liste `ProbableDamageEvent` (target, healthDmg min/max, appliedHits, probability).
  `level`/`multiplier` overrident le capteur AbilityState (test d'hypothèse de niveau).
  Depuis la tuile COURANTE (bouger l'unité pour une autre position). Read-only.
- **`pairUtility({ runnerId, unitId, targetId, abilityType, level?, multiplier?, col?, row? })`**
  (#45) — UTILITÉ DE PAIRE au scoreur NATIF : invoque `ComparablePlaybook.
  IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions` → Fix64 (Σ familles damage/heal/effect/repair,
  prob + modifs inclus) pour (ability, cible) depuis une position. ⚠ `ncEvaluate` AV @0x46
  sur les playbooks COMPARABLES hors tour natif — utiliser CE RPC pour l'utilité comparable.
- ~~**`navToCampaign()`**~~ — **RETIRÉ le 2026-08-07. Ne pas le rétablir.** Le cycle de warmup
  applique déjà ce remède lui-même sur wedge détecté (cran 8, même foyer). L'exposer en plus
  comme levier manuel faisait croire qu'un warmup rouge se rattrape à la main : **il ne se
  rattrape pas.** Mesuré — joué quatre fois de suite, il a ramené la campagne à chaque coup
  pendant que `warm-gate` refusait toujours la création de runner, le RPC de warmup rendant
  `ok:false`. Il répare l'**écran**, jamais le **verdict**. Un warmup rouge se diagnostique par
  `POST /api/admin/warmup`, qui rend le détail étape par étape.
  Cran exécutable qui garde son absence : `frida/tools/probe-390-wedge-remedy.ts` §6.
- **`exposureView({ runnerId, unitId?, allAbilities?=true })`** — move-guard
  (inverse d'attackPlans) : dégât ennemi entrant au prochain tour + flag `exposed`.
  Même routing dégât que attackPlans (#103 : actives→playbook, normale→preview).
- **`applyAction({ runnerId, action | actions[] })`** — applique mon coup
  (`ApplyAiMessage`), snapshot avant/après. `action` = `{kind:"move",unitId,to|feet}`
  | `{kind:"ability",casterId,targetId,abilityType}` | `{kind:"finish",unitId}`.
  Fidèle (SkipFlags=false). Décomposable 1 action/appel.
- **`dumpEntityComponents({ runnerId, target?, withFields? })`** — introspection
  read-only des composants d'une entité.

## Pilotage de l'IA native (`ai-step/rpc-drive.ts`)

- **`aiStepDryRun({ runnerId, maxPump? })`** — pompe 1 `MoveNext` de
  `CalculateNextActionForPlayer`, décode l'action suivante SANS commit.
- **`aiDryRunAllUnits({ runnerId, maxPump? })`** — par unité, action proposée
  par l'IA (`CalculateNextActionForUnit`) contre le même état, sans appliquer.
- **`aiPlayByUnit({ runnerId, maxTurns?, maxActivations?, maxPump?, captureEvents?, captureOverwatch? })`**
  — driver per-unité COMPLET (sans `CheatRunAIMessage`) : l'IA choisit unité +
  position, applique + capture 1 démo/activation.
- **`aiPlayOrdered({ runnerId, order?="desc", maxTurns?,… })`** — force l'ordre
  d'activation (l'IA décide seulement quoi fait chaque unité).

## Capture live (depuis le jeu)

- **Campaign** (`campaign-builder.ts`, `auto-boot.ts`) : `buildCampaignConfig`,
  `dumpCampaignCatalog`, `diagnoseCampaign`, `campaignBuilderStatus`,
  `triggerAutoBoot`, `getAutoBootStatus`.
- **BattleConfiguration** (`battle-config.ts`) : `inspectBattleConfig`,
  `dumpBattleConfig`, `inspectSpawnPoints`, `discoverSources`, patch
  (`setBattleConfigPatch`/`…GameMode`/`…RuleSet`/`applyBattleConfigPatchNow`/
  `clearBattleConfigPatch`/`getBattleConfigPatchStatus`).
- **Boards** : `dumpAllBoards`, `dumpPvpAndSyncBoards` (`dump-boards.ts`,
  `dump-pvp-boards.ts`). **Persistés sur disque** (`data/boards/{kind}/<id>.json`) par
  `scripts/python/dump_boards.py` — qui capture AUSSI le seed BC (`dumpBattleConfig` →
  `data/seed-bc.json`). Artefacts per-hash, purgeables ; régénère via `python dump_boards.py`
  (cf. runner.md §1, #159).
- **MachinesOfWar** (`mow-builder.ts`) : `buildMachinesOfWarConfig`,
  `dumpMachinesOfWarCatalog`, `machinesOfWarBuilderStatus`, `dumpLiveEvent*`,
  `dumpMoWProgressionState` (hors-sujet MoW arena PvP : cf. `project_mow_deploy_gate`).
- **UI nav — SUPPRIMÉ.** Les neuf endpoints d'interface (`uiList`, `uiListAll`, `uiClick`,
  `uiTexts`, `uiWindows`, `uiWindowEvents`, `uiScrollList`, `uiScrollSet`, `uiMutations`) et
  leurs modules (`ui-nav.ts`, `ui-scroll.ts`, `ui-mutations.ts`, le paquet
  `scripts/python/gamenav/`) ont été retirés. **Piloter l'écran pour lire ou écrire sur le
  compte est proscrit** : `expedition_run.py` avait déjà supprimé son étape UI, et sa raison
  vaut pour tout le reste — elle FAISAIT DISPARAÎTRE l'écran du joueur, exigeait un écran de
  départ précis, et chaque clic devait être validé par son EFFET (`interactable` précède la
  fin de l'animation, donc le retour d'un clic ne prouve rien).
  Ce qu'on lisait par l'écran se demande au jeu : `rosterOwned` pour la possession,
  `expeditionBoard` pour le plateau, les porteurs de `ViewCommandExecutor` pour le reste.
  ⚠ `ui-windows.ts` SURVIT, sans `register` : le warmup importe `ecouterTransitions`, qui
  OBSERVE les transitions de fenêtre et ne clique rien.
- **Config / visuels** : `getGameConfig`/`getMatchState` (`config-io.ts`) ;
  `getGameVersion`/`dumpEnum(s)`/`resolveVtableSlot` (`introspect.ts`) ;
  `resolveUnitVisual`/`dumpAllUnitVisuals`/`getUnitAssetMap` (`unit-visual-resolve.ts`,
  `unit-asset-map.ts`).

## Sim / mirror (`sim-engine.ts`, `sim.ts`)

`sim`, `commit`, `simAndCommit`, `simRunAiTurn`, `simEndTurn`, `simMirror`,
`simBuildPreview`, `simGetState`, `simRebuildAndCatchUpTo`, `simStatus`, `simReset`,
… Mirror = runner persistant suivant le live. ⚠️ `Interceptor.replace` actif → ne
pas restart le host en plein battle.

## Familles de diagnostic (rôle + source ; auto-armées au `register`)

Outils de RE / observabilité — aucun hook live ne les APPELLE, mais leur code est
**dans le bundle injecté**, pas à côté.

- **Introspection IL2CPP one-shot** (offsets, méthodes, enums, stats, weapons, progression).
  `hooks/probes/` est VERSIONNÉ et **66 de ses modules sortent dans `dist/hooks.js`** : ce sont
  des entrées de build, pas des brouillons à côté du build. (Il s'appelait `hooks/scratch/`
  jusqu'à #480-r6.)
  ⚠ **Leur sortie ne revient PAS dans la réponse RPC** : ces handlers rendent `{ ok: true }` et
  écrivent par `console.log`. Frida en fait un message que `sessions.ts` publie et journalise
  (`onMessage` → `publish` + `appendLog`) — on lit donc le résultat dans le **log de session**,
  pas dans le retour de l'appel.

  Liste NOMMÉE, re-dérivable (`probe_480r8_rpc_ventilation.py --catalogue`) :

  - **`controller.ts`** (57) : `checkInvoker`, `checkKlass`, `checkMethod`, `checkMethodParams`,
    `checkParent`, `checkStatsFields`, `debugFlagsType`, `dumpAbility`, `dumpAbilityProperly`,
    `dumpAbilityState`, `dumpAttackDefense`, `dumpComps`, `dumpCritBlock`, `dumpDamageProfile`,
    `dumpDpProperly`, `dumpExtraDmg`, `dumpFlags`, `dumpMethod`, `dumpMethods`, `dumpParams`,
    `dumpPathfinder`, `dumpProgAnywhere`, `dumpProgExt`, `dumpReturn`, `dumpRunnerFields`,
    `dumpStatComp`, `dumpStatTypes`, `dumpStats`, `dumpStatsFormula`, `dumpStatsFormulaFields`,
    `dumpUnitEntity`, `dumpUnitEntityCore`, `dumpUnitProgData`, `dumpUnitProgDataNested`,
    `dumpUnitProgFields`, `dumpUnitProgMethods`, `dumpUnitProgression`, `dumpUniverse`,
    `dumpValueOverride`, `dumpWeaponClass`, `dumpWeaponProfile`, `dumpWeapons`,
    `dumpWeaponsTypes`, `dumpWpTypes`, `findAction`, `findGlobals`, `findPathfinderOff`,
    `findProgInstances`, `inspectInstance`, `inspectPtr`, `introspectFlags`, `listComps`,
    `mapRanks`, `searchClass`, `searchClasses`, `testSafeInvoke`, `testStatic`
  - **`features/unit-visual-resolve.ts`** (5) : `fullAssemblyScan`,
    `listUniverseInstanceFields`, `listUniverseRefs`, `tryGlobalsCapture`, `tryStaticCapture`
  - **`probes/*`** (6) : `dumpIdunNavInfo`, `dumpNavMethods`, `inspectCgms`, `testScene`,
    `testUnityFind`, `tryToCampaign`
  - **`features/compare.ts`** : `compareBuilt` — **`features/dump-composed.ts`** :
    `dumpComposedUtilityStatus`

- **Traces on-demand, armées à la main** — le `register` n'arme RIEN (cf. `controller.ts`) ;
  ces RPC sont les commandes d'armement/lecture, sans appelant statique par construction :
  - **`features/effect-immunity-observe.ts`** (4) : `effectImmunityObserveEnable`,
    `effectImmunityObserveDisable`, `effectImmunityObserveReset`, `effectImmunityObserveStatus`
  - **`features/move-options.ts`** (4) : `armMoveOptionsTrace`, `disarmMoveOptionsTrace`,
    `moveOptionsTraceReset`, `moveOptionsTraceStatus`
  - **`features/board-trace.ts`** (3) : `boardTraceStart`, `boardTraceStatus`, `boardTraceStop`
  - **`features/trigger-trace.ts`** (2) : `triggerTraceInstall`, `triggerTraceSetEnabled`

- **Lecteurs de trace — moitiés de paire** : leur jumeau d'armement est câblé, eux se lisent à
  la main après coup. Sans appelant statique **par construction**, donc nommés ici :
  - **`features/scorer-damage-trace.ts`** (6) : `scorerAttModDump`, `scorerBaseOverrideDump`,
    `scorerModifyDump`, `scorerPredBaseDump`, `scorerScenarioTraceDump`, `scorerStatModsDump`
  - **`features/movement-trace.ts`** (2) : `dumpMovementTrace`, `movementTraceInstallStatus`
    — ⚠ le module est **désactivé** dans `controller.ts` (`void movementTrace`, hors de la liste
    des `register`) : ces deux RPC ne sont **pas exposés** par la session tant qu'il est commenté.
  - **`features/hit-trace.ts`** (2) : `hitTraceDisarm`, `hitTraceSetEnabled`
  - **`features/ai-trace.ts`** : `aiTraceGetProjections`

- **Capteurs META — hors bataille (#599 / #600, 2026-08-10)** : ils observent le client de
  méta-jeu (réseau, roster, Expeditions), pas le combat. Armement/désarmement/lecture à la main,
  donc **sans appelant statique par construction** — d'où leur nom ici. Modules entiers nommés,
  pas seulement les orphelins : un patron `*Status` ne rend aucun nom découvrable.
  - **`features/net-capture.ts`** (4) : `netCaptureArm`, `netCaptureDisarm`, `netCaptureDump`,
    `netCaptureStatus` — tout ce que le client POSTe, capté au point de fil
    (`Snowprint.ClientSdk.Web.WwwWebHelper$$PostString/PostBytes/PostData`, les trois portes
    ancrées, `via` publié). **HTTP seulement.**
  - **`features/ws-capture.ts`** (4) : `wsCaptureArm`, `wsCaptureDisarm`, `wsCaptureDump`,
    `wsCaptureStatus` — le PvP **synchrone** parle WebSocket
    (`thor.Logic.Client.Web.WebsocketController$$Send/OnMessage`), que `net-capture` ne voit pas :
    l'armer sur une partie SyncPvp rendrait un journal VIDE. Capté **aux deux sens**.
  - **`features/roster-owned.ts`** (4) : `rosterOwned`, `rosterOwnedArm`, `rosterOwnedDisarm`,
    `rosterOwnedStatus` — possession réelle demandée au jeu
    (`IdunMetaLogic.UserProgress.UnitProgression$$HasUnitUnlocked`), recoupée par
    `$$AmountOfUnlockedUnits`. Remplace le grattage de l'écran de dispatch, qui mesurait
    l'ÉLIGIBILITÉ (possession × alliance × rareté × niveau), pas le roster.
  - **`features/expedition-board.ts`** (8) : `expeditionBoardArm`, `expeditionBoardDisarm`,
    `expeditionBoardDump`, `expeditionBoardRead`, `expeditionBoardStatus`,
    `expeditionEligibility`, `expeditionEligibilityFor`, `expeditionRankRequirements` — le
    plateau d'Operations complet, capté là où la réponse est APPLIQUÉE
    (`thor.Client.ResponseProcessing.GameStateSynchronizerLogic$$ApplyExpeditionProgress` et
    deux autres portes, `via` publié). L'UI est virtualisée (4 lignes visibles sur 7) et
    `net-capture` ne voit que le sortant : les deux voies naïves mentent.
  - **`features/expedition-dispatch.ts`** (7) : `expeditionCallbackForge`, `expeditionClaim`,
    `expeditionDispatch`, `expeditionDispatchArm`, `expeditionDispatchDisarm`,
    `expeditionDispatchJournal`, `expeditionRefresh` —
    ⚠ **seul module de la famille qui ÉCRIT**, par TROIS portes, toutes sur
    `ExpeditionGameEvents` (dont les quatre champs sont des commandes — l'UI est au-dessus,
    et c'est elle qu'on contourne) : `expeditionDispatch` engage le compte (unités
    immobilisées pour la durée), `expeditionClaim` encaisse, `expeditionRefresh` repeuple le
    plateau. Les `*Arm`/`*Journal` observent la chaîne réelle sans rien envoyer.
    ⚠ **`expeditionRefresh` est le SEUL RPC du dépôt qui puisse coûter des GEMMES** : son
    paramètre `index` est le palier facturé, fourni par l'appelant, et la table
    `clientGameConfig.expeditions.refresh` va de 0 (1er du jour) à 1000 gemmes (21ᵉ). Le
    contournement de l'UI supprime la popup qui annonce le prix, d'où un **refus exécutable** :
    le palier est lu au natif (`ExpeditionRefreshProgression$$GetCurrentTierIndex`) et tout
    palier ≠ 0 est REFUSÉ sauf `autoriserPalier` explicitement égal. Un palier NON MESURÉ fait
    refuser, jamais supposer le gratuit.
    ⚠ Les trois portes **partent même si le jeu gèle ensuite** (#600) : ne jamais rejouer à
    l'aveugle, relire le plateau et n'inclure que ce qui reste à faire.
  - **`probes/gc-rendezvous.ts`** : `gcRendezvous` — sonde de MESURE, pas d'outil : elle
    établit qu'un GC forcé sous Frida FIGE le jeu (145 threads dans `ntdll`, `.Responding` à
    `False`). C'est pourquoi `gcRoot.collect()` refuse par défaut. **Ne la lancer que pour
    remesurer au changement de build** — elle gèle le process.

- **`aiTrace*`** (`ai-trace.ts` + `ai-trace/`) : capture playbook/prédictions/
  utilités → JSONL (`data/ai-traces/`). `aiTraceEnable(level)`/`aiTraceStatus()`
  pilotés par les scripts RL.
- **`aiUtilityTrace*`** (`ai-utility-trace.ts`) : clés `UtilityConfig` lues par l'IA.
- **`scorer*`** (`scorer-damage-trace.ts`) : scoring de dégât par tuile.
- **`bucketAudit*`** (`bucket-audit.ts`) : actions ajoutées/choisies par bucket.
  ⚠ hooks constatés MORTS 2026-07-03 (0 fire sur tours IA) — re-diagnostiquer
  avant usage (cf. docs/rl/validation.md §5).
- **Traces séparées par runner** : les 3 familles ci-dessus stockent leurs
  events dans des buffers PAR ORIGINE (`OriginBuffers`,
  `game/trace-origin.ts` ; origine = runner du RPC déclencheur, `null` = IA
  live) — CAP par bucket, events tagués `originRunnerId`. Dumps avec
  `{ runnerId }` → bucket direct ; clears scopables
  (`scorerDamageTraceClear`/`aiUtilityTraceClear`/`bucketAuditReset`
  `{ runnerId }`) ; `disposeRunner` PURGE automatiquement les buckets du
  runner.
- **L'ARMEMENT aussi est par runner (#483) — passe TON `runnerId`.** Les seaux
  étaient par runner mais la PORTE ne l'était pas : un booléen de module,
  session-global. Comme les probes appellent leur `*Off` dans un `finally`, le
  premier des 4-en-parallèle qui finissait **désarmait la capture des autres**,
  qui dumpaient un seau **TRONQUÉ sans aucune erreur**. Foyer :
  `game/armed-runners.ts`, six familles (`scorerDamageTrace*`,
  `triggeredMoveTrace*`, `effectBonusTrace*`, `hitTrace*`, `aiUtilityTrace*`,
  `bucketAudit*`).
  - `On/Arm/Enable {runnerId}` → armement **NOMINATIF** ; sans `runnerId` →
    armement **GLOBAL** (comportement historique, préservé).
  - `Off/Disarm/Disable {runnerId}` → désarme CE runner ; **sans `runnerId`,
    seul le GLOBAL est désarmé — les armements nominatifs des autres acteurs
    SURVIVENT.** C'est l'asymétrie : un `On` de trop ne coûte que de la perf,
    un `Off` de trop détruisait une mesure en silence.
  - **Un désarmement doit porter le MÊME scope que son armement** : un
    `Off {runnerId}` sur un armement global ne désarme rien et laisse le global
    ouvert pour la session.
  - Les `*Dump` publient `armedGlobal` + `armedRunners` (état réel) et un `on`
    qui répond « la capture était-elle ouverte **pour l'origine interrogée** ».
    `traceArmedStatus` (`status.ts`) donne l'état des six familles d'un coup.
  - Cliquet offline : `probe_483_armement_par_runner.py` (périmètre **dérivé**
    de `new OriginBuffers<`). Isolation live :
    `probe_483_isolation_armement_live.py`.
  Capture/lecture concurrente OK ; le clear global (sans `runnerId`) reste
  exclusif (cf. validation.md §0).
- **`overwatch*`/`overwatchFix*`** (`overwatch-fix/`) : anti-suicide overwatch.
- **`whatifTrigger*`** (`whatif-trigger.ts`) : simulation « et si » de triggers.
- **`dispatchObserve*`** (`dispatch-observe.ts`), **`modifierObserve*`**
  (`modifier-observe.ts`) : observation StreamDispatcher / modificateurs de dégât.
- **`movementTrace*`** (`movement-trace.ts`, DÉSACTIVÉ par défaut : hooks laggy),
  **`boardTrace*`** (`board-trace.ts`), **`moveOptionsTrace*`** (`move-options.ts`).
- **Statuts / dumps ponctuels** : `dumpComposedUtility*` (`dump-composed.ts`),
  `messageTraceStatus` (`message-trace.ts`), `winnerCaptureStatus`
  (`winner-capture.ts`), `abilityPreferences` (`ability-prefs.ts`),
  `rlGetObservation` (`rl/bridge.ts`).
- **Divers debug** : `probe*`/`installStatsFormulaTrap`/`dumpItemsCatalog`/`previewBis`
  (`normalize-bc/debug-rpcs.ts`, `items-catalog.ts`) ; `findClassesNamed`/`dumpModeSources`
  (`mode-source-capture.ts`) ; `armExceptionCtorHook` (`init-trace.ts`) ;
  `ping`/`info`/`summary`/`dump`/`clear`/`forceInstall` (`status.ts`).

## Conventions

- **Aucune RVA hardcodée** : résolution runtime (`findClassAnywhere` →
  `findMethod` → `Interceptor.attach`). Cf. CLAUDE.md.
- **Pas de heap scan auto** (`Memory.scan`/`enumerateRanges`) : gèle le main
  thread → UnityFreezeDetector tue le process. Gated `allowHeapScan` only.
- **Pas de broad-hook** sur méthodes UI hot / property getters sérialisés.
- Features diagnostiques : **auto-arm au register**, pas d'étape « arm » manuelle.
