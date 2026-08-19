# Boucle d'auto-progression — DESIGN (à VALIDER avant lancement)

Doc de **décisions + invariants**. Dashboard live = `loop.md` ; procédure exécutable = skill
`tacticus-loop` ; données = `journal.md` / `hypotheses.md` / `toolfeedback.md`.

## Objectif
Progresser au jeu Tacticus en **conservant l'expérience dans des FICHIERS**, via le cycle
`explorer → hypothèse → valider → promouvoir`.

## 2 contraintes dures (elles pilotent TOUTE l'archi)
- **COÛT** : pas de Claude **headless** (`claude -p` / Agent SDK) — facturation séparée, trop cher.
  La cognition doit rester **dans la session interactive déjà payée**.
- **CONTEXTE** : rien de persistant ne doit accumuler en contexte → **tout le durable en fichiers**.

## Modèle de cognition (DÉCIDÉ)
- **Cerveau = MOI** (session interactive) **+ sous-agents `Agent` éphémères** (1/match) → même
  session/abonnement, **aucun coût headless additionnel**.
- **Sous-agent** : contexte isolé ; lit doctrine + fichiers, joue 1 match, écrit son entrée
  `journal.md`, renvoie **~10 lignes** (issue, tags, deltas H, promotions, tool-feedback), puis **MEURT**.
- **Orchestrateur = MOI via `/loop`**, **near-stateless par tick** : lire fichiers → choisir mode →
  spawn sous-agent → appliquer son retour aux fichiers → tick suivant. Je ne tiens **RIEN** entre les
  ticks (fichiers = vérité).
- **Résumabilité = la clé anti-contexte** : quand mon contexte se remplit (/compact ou fin de session),
  l'état est en fichiers → la boucle **REPREND de là**. Donc « **autonome dans une session, résumable
  entre sessions** », PAS 24/7. Compromis imposé par le coût, assumé.

## Pas de serveur Node-driver (conséquence du coût)
Le serveur Node ne peut pas appeler l'outil `Agent` (session-only) → il faudrait du headless → **exclu**.
Le Node est **DIFFÉRÉ** à une couche d'**observabilité read-only optionnelle** (rendre les fichiers sur
`/view`), **jamais** un driver de cognition. Observabilité v1 = **lire les fichiers** (`journal.md`,
`loop.md` lisibles à la main).

## Modes de match
- **EXPLORE** (seed aléatoire) → découvrir des failure modes → nouvelles H.
- **VALIDATE** (rejouer un seed précis) → test **causal** d'une H (même matchup, ne change que le comportement visé).
- **BENCHMARK** (seeds held-out, joués jusqu'au **terminal vrai**, **pas d'abandon-won**) → mesure de progrès.

## Abandon (coût + contexte) — via verdict scorer, ASYMÉTRIQUE
- `lost` **libéral** ; `won` **quasi-mathématique** (j'ai sur-estimé « je gagne » 2× → barre haute).
- Jamais de kill mid-battle : le match en vol finit/abandonne proprement + écrit son entrée + dispose le runner.

## Scorer de position (`verdict`) — outil TF02
Composantes calculables : **(A)** matériel **pondéré par rôle** (pas HP brut), **(B)** **atteignabilité
de la win-condition adverse** (le facteur raté en G02/G03), **(C)** course aux dégâts / **TTK** (qui tombe
à 0 unité en 1er sous focus), **(D)** **tendance/escalade** (Neuroparasite, ramp Khorne, sustain>dmg).
`decided` = **règles interprétables**, pas un seuil magique.
**GOUVERNANCE (critique)** : le scorer change **GATÉ** (≥N preuves de miscalibration via `calibration-log`)
+ **VERSIONNÉ** + la **métrique de progrès est DÉCOUPLÉE du scorer** (issues réelles sur benchmark).
**Jamais de tweak par tour** (sinon règle mobile + metric-gaming).

## Concurrence
Session Frida = **ressource unique** → **SÉQUENTIEL par défaut** (sémaphore taille 1). Parallèle (plusieurs
sous-agents) seulement **si l'isolation 2-runners est prouvée** (expérience en attente) — et ça sérialise
de toute façon sur la session. Vrai parallélisme = plusieurs instances de jeu (lourd, hors scope).

## Garde anti-overfit
Filtre d'inscription **(général + vérifié + non-dérivable)** ; promotion en doctrine = **≥2 parties OU
seed-replay contrôlé**. Méta-travail (calibration/promotion gatées) **délégué à un `maintenance-agent`
éphémère** (lit le fichier-log, rend 1 ligne) — pas tenu en contexte.

## Canal outillage
`toolfeedback.md` : tout agent signale un outil **manquant/améliorable** (jamais de contournement silencieux) ;
friction `recurrence ≥2` = **tâche d'outil prioritaire** (corriger avant de jouer cassé).

## Mesure de progrès
**Win-rate sur la suite BENCHMARK held-out** (sol ferme, contrôle la chance de matchup) **+ baisse de
fréquence des tags d'échec**. PAS le win-rate aléatoire brut. Ne jamais entraîner la doctrine sur les seeds benchmark.

## Reste à faire AVANT lancement
1. **TF01** — étendre `rl_duel.py play --spec` : abilities sur hex (`--to`), self-buff, actif MoW → 1 appel/round hétérogène.
2. **TF02** — `rl_duel.py verdict` (scorer A-D + flag `decided`) + un `calibration-log` (verdict@tour vs issue réelle).
3. **Fixer la suite benchmark** : 4-5 seeds de difficultés variées (départ : 88888 équilibré-gagné, 73348 équilibré, 33182/31337/777 hard-counters).
4. *(option)* tester l'isolation 2-runners.
5. **Dry-run 1 itération** (un vrai sous-agent) → valider le pipeline (contexte isolé, écriture fichier, format du retour) → puis lancer `/loop`.

## Multi-runner & concurrence RPC (RÉSOLU — coexistence prouvée)
**✅ RÉSOLU (2026-06-16)** : la coexistence multi-runner MARCHE. Le vrai blocker n'était ni host ni
une race recorder (2 hypothèses fausses héritées d'un framing d'avant-compact) — c'était la
**single-build policy d'`initAndStart`** (`launch.ts`:490, déterministe : dispose tous les runners
existants avant d'en bâtir un). Corrigé d'abord par **`keepExisting` opt-in** + flag **`autoDispose`**
sur l'Entry du registre (durcissement recorder) — puis (2026-07-03) la coexistence est devenue le
**DÉFAUT** et `keepExisting`/`--keep` ont été supprimés (cf. ¶ suivant). Validé : 2 runners
(seeds 11111/22222) coexistent, `decisionView` OK sur les deux, rosters distincts, **zéro cross-talk**,
via `--state-file` isolés. **Enablers du parallèle** : (1) isolation runner ✓,
(2) state-file par agent ✓, (3) coexistence ✓.

**⚠ FOOTGUN concurrent (self-play, diagnostiqué 2026-06-23 — ÉLIMINÉ 2026-07-03)** : la single-build
policy était une disposition **SILENCIEUSE** (zéro event `runner_disposed`). En self-play
`matchesInFlight ≥ 2`, un seul `rl_duel build` SANS `--keep` entrant dans la fenêtre concurrente
**disposait tous les runners frères en vol** → matchs en "runner not found"/no-result **sans trace**
(signature : `listRunners`=[] + `battleStatus ok:false` + `/api/selfplay/:id/await` → 502 instantané ;
host-tracker stale). **Résolution structurelle (2026-07-03)** : la coexistence est devenue le DÉFAUT
d'`initAndStart` (`--keep`/`keepExisting` supprimés — le footgun ne peut plus être commis) ; la
garde-ressource gcRoot est reprise par le cap dur **`MAX_RUNNERS`** (`runner-registry.ts`) : au cap,
le build REFUSE explicitement (liste des runnerIds) au lieu de nuker. Discipline compensatoire : chaque
acteur **dispose ses runners en fin de passe** ; `rl_duel build` remplace le runner de SON
`--state-file` (replace scopé par acteur). La **GATE d'adressabilité** du SETUP self-play (confirmer le
runner joignable via `await` avant `ok`) reste en place comme défense en profondeur. `initRunner` +
`loadFromSavedBundle` (chemins UI BUILD/LOAD) gardent la sémantique replace = ops de session exclusives.

**Pourquoi rien d'autre n'est nécessaire à petite échelle (analysé 2026-06-16)** : avec `await` par
appelant (le `_rpc` python est bloquant), le pipeline est en **boucle fermée** — chaque sous-agent a
**≤1 RPC en vol** → total en vol **borné par N** (nb de sous-agents) PARTOUT : `state.pending` Frida ≈1
(drain whole-queue à chaque frame, résidence ≤1 frame), file host ≤ N. **Rien ne diverge.** Donc :
- **`getQueueStats` Frida = DROPPÉ** (reverté) — il ne mesurait qu'un canari de freeze (`depth` ≈1 hors
  stall ; il ne grossit que si la pump s'arrête → mais alors `frameNo` figé suffit comme signal).
- **IDs de corrélation** = utiles uniquement pour logger/annuler un **reply zombie de timeout** (bénin en
  read ; à surveiller sur un RPC **mutant** type `applyAction` qui muterait après l'abandon du host).
- **Cap host (semaphore K)** = PAS contre l'accumulation (inexistante à petit N) ; son vrai rôle =
  **découpler N (agents qui raisonnent = levier de throughput) de K (RPC simultanées frame-safe)**.
  **YAGNI tant que N ≤ K_frame-safe.** Note : une `decisionView` overrun **déjà** une frame seule → le
  risque frame = le **poids PAR-RPC**, pas leur nombre ; K restera petit (1–2) le jour où on l'ajoutera.

**Instrument de capacité host (construit 2026-06-16 — `host/rpc-queue.ts`)** : un gate par session sur
`rpcCall`, **non** comme protection (le `await` suffit à petit N) mais comme **instrument** pour répondre
empiriquement à « combien d'agents Frida encaisse ». `GET /api/rpc-queue` = télémétrie (`avgInFlight`,
`busyFraction`, `avgRpcMs`, `maxInFlight`, `waiting`, `totalTimeouts`…) ; `POST {cap}` = throttle (∞ défaut
= pass-through, comportement inchangé) ; `POST {timeoutScale}` = **plancher de timeout configurable par
l'orchestrateur** (seul Claude connaît le nb d'agents prévu → il le POSTe avant de lancer un batch).
Timeout effectif = `base × max(timeoutScale, inFlight+waiting)` (mon plancher + taille de queue vive ;
le pump Frida est sériel → latence ∝ ça ; généreux par design car un faux timeout sur RPC **mutante** =
corruption zombie). Lecture saturation : `avgInFlight`→N persistant ou `avgRpcMs` qui décolle = « ça
respire pas ». Le `cap` reste séparé du `timeoutScale` (throttle ≠ durée d'attente).

cf. TF06/TF07. Investigation détaillée (toujours valide) ci-dessous.

**CADRAGE (clé)** : le bottleneck = le **temps de RAISONNEMENT** des agents, PAS le jeu (RPC
sub-seconde). Levier de throughput = **paralléliser le raisonnement** (N match-agents). Une seule
session jeu sert très bien N agents reasoning-bound : elle est **idle la plupart du temps** (RPC rares
+ courtes → les sérialiser ne coûte ~rien). Donc les inquiétudes concurrence-jeu ci-dessous
(sérialisation, freeze, depth) sont **mineures** pour ce profil — le seul vrai risque par-frame = une
**RPC lourde isolée** (`decisionView`), indépendant du parallélisme. **Enablers RÉELS du parallèle (3)** :
(1) isolation runner ✓, (2) **IDs de corrélation**, (3) **state-file par agent** (`rl_duel --state-file`).
Le reste = sûreté secondaire. Coût : le parallèle achète du **temps, pas de l'argent** (N× tokens).

**Bonne nouvelle (Explore)** : runners déjà **isolés** — MatchState par-runner, **EntityServices
fraîche par runner** (le « 67 services » est **par-runner**, pas global), RPC **paramétrées par
`runnerId`**, registre en Map (`runner-registry.ts`), et **`state.pending` + main-pump sérialisent**
toutes les RPC sur le main thread. Donc **PAS de refonte Zenject** — juste **durcir la plomberie RPC
concurrente** :
- **IDs de corrélation explicites** : corrélation résultat→appelant déjà OK (closures de promesse +
  `rpc.exports` natif), MAIS pas d'ID traçable → sous concurrence on ne peut pas logger/détecter les
  drops, et un **timeout host laisse une tâche « zombie »** (`queue.ts` la draine plus tard, resolve
  dans le vide). → host génère `reqId` + map `pending(reqId→{resolve,reject,method,t0})` ; agent
  **echo `reqId`** dans l'enveloppe + tag l'item de queue.
- **Profondeur de queue exposée** : `state.pending.length` via un export **LÉGER non-queued**
  `getQueueStats()` → `{depth, oldestAgeMs, inFlight, lastDrainMs, itemsLastTick, maxItemMs}` (sinon il
  attend dans la queue qu'il mesure) ; + `enqueuedAt` par item.
- **Garde anti-`UnityFreezeDetector` = le TEMPS DE DRAIN PAR FRAME, pas la depth.** Le détecteur ne catch
  qu'**une frame trop longue** (pas un backlog cumulé) → une queue profonde est OK si **étalée sur
  plusieurs frames**. Donc le **main-pump** (`runtime/main-pump.ts`, draine synchrone dans `Update`) doit
  avoir un **budget par tick** (temps ou N items max) et reporter le reste. Risque résiduel : **une RPC
  lourde isolée** (ex. `decisionView` = plans + danger zone) peut overrun une frame **seule** → mesurer
  `maxItemMs` et chunker les lourdes si besoin. `depth/oldestAge` = signal de **backpressure** (enqueue vs drain), pas le garde freeze.
- **À confirmer empiriquement** : test 2-runners avancés en interleave → zéro cross-talk via
  d'éventuels singletons **JEU** (progression/loot) non runner-scopés (mitigé par unit IDs distincts par config).
- **Concurrence v1** : la sérialisation main-thread fait que 2 battles ne tournent pas en *vrai*
  parallèle (RPC sérialisés) → le parallèle ne gagne que le **raisonnement** des agents. Acté.
- Fichiers touchés : `frida/hooks/runtime/queue.ts`, un export léger (`main.ts`/controller),
  `frida/host/sessions.ts` (rpcCall + pending map), + endpoint host. Rebuild + reinject + amorce + test.

## Questions ouvertes (à trancher avant lancement)
- **Budget/stop** : combien de matchs par session avant un /compact ? un cap de coût (nb matchs) par run ?
- **Observabilité** : se contenter des fichiers, ou la mini-dashboard `/view` vaut le coup plus tard ?
- **Profondeur du sous-agent** : `maxTurns`/garde-fou pour qu'un match ne parte pas en boucle ?

## Self-play oracle-vs-oracle — SPEC (verrouillée 2026-06-22)

**But** : élever le plafond des démos d'IL. Au lieu d'oracle-vs-IA-native, jouer **les deux
camps par des agents oracle** → dataset où les deux côtés sont experts. (L'oracle battant l'IA
native sur les matchups jouables, l'IA native n'est plus l'expert à imiter.)

### Découpage des rôles (clé — chacun fait UNE chose)
| Rôle | Qui | Responsabilité |
|---|---|---|
| **Hand-off de tour + exclusion** | **Host** (`/api/selfplay/:id/await`) | long-poll sur `currentPlayer` du runner ; rend la main quand c'est le tour du joueur, ou `gameOver`. PAS de cognition (cohérent avec « Node = plomberie, jamais driver de cognition »). |
| **Lifecycle du match** | **Arbitre** (≈ script workflow + agents setup/teardown) | build le runner partagé, adjuge W/L/**no-winner** (round-cap `EnvEndBombardment`), timeouts/deadlock, dispose, enregistre la démo. **Ne relaie PAS les tours.** |
| **Jouer un camp** | **Player agent CHAUD** | 1 seul `agent()` long = recon 1× puis boucle tous ses tours ; joue via `decisionView` + `play --no-ai`. |
| **Plafond de scale** | **le pump Frida** (mesuré par `rpc-queue`) | borne le fan-out de matchs. |

### Pourquoi « warm » sans SendMessage
Chaque player est **un `agent()` long** qui joue TOUS ses tours dans un seul contexte → recon +
doctrine lus **1×**, contexte persistant (cache input). Pas de spawn-par-tour → pas de cold-start
répété. N'utilise QUE des primitives **sûres** (`agent`/`parallel` + host long-poll), PAS
l'inférence non vérifiée « SendMessage depuis un sous-agent ».

### Boucle d'un player agent
```
recon UNE FOIS (sa team, gameconfig→wiki)
boucle:
   GET /api/selfplay/:id/await?runnerId=R&player=P   ← bloque CÔTÉ HOST jusqu'à mon tour / gameOver
   si gameOver -> sortir (rapporter l'issue)
   decisionView (état courant) -> planifier -> rl_duel play --no-ai --state-file sf
       play --no-ai = mes actions + endturn-retry jusqu'au flip adverse, PUIS STOP
       (pas de tour IA natif : c'est à l'autre agent de jouer)
```
L'agent émet **UN seul** GET await par tour (pas de boucle `sleep` côté client — le foreground
sleep est bloqué par le harness ; c'est le host qui bloque).

### Règle de fidélité (NON négociable)
A et B = **contextes séparés**. L'arbitre voit leurs résumés retournés mais ne **passe JAMAIS**
d'info privée d'un camp à l'autre. Chaque player tire son état du **host** (`decisionView`
perspective-scoped), pas de l'arbitre. → self-play fidèle (≠ le piège « un agent joue les deux »
= collusion, pire pour l'IL).

### Caveats actés
- **`rpc-queue` ≠ mutex de tour** : le pump mono-thread garantit l'atomicité **RPC**, PAS celle du
  **TOUR** (un tour = plusieurs RPC). L'exclusion au niveau tour vient du turnstile (host await +
  `currentPlayer` : un seul camp est « courant » à la fois).
- **Le pump EST le plafond de débit** : tous les runners partagent une session Frida → les RPC
  runner sérialisent → plus de matchs // ≠ plus de débit (mesurer `avgInFlight`/`busyFraction`).
  Self-play LLM = **quelques** matchs ; le mass = la politique réseau (étape 2, hors Frida).
- **Move-guard mal-spécifié en self-play** (son « tour ennemi » = IA native, pas l'oracle adverse)
  → **coupé en v1** ; chaque player raisonne seul.

### Tranches
1. **(CETTE tranche — FAITE)** `rl_duel play --no-ai` (Python) + RPC hook légère `battleStatus`
   (stage+currentPlayer seuls, ≠ decisionView lourde) + endpoint host `/api/selfplay/:id/await`
   (long-poll). = les primitives de hand-off.
2. Prompts des 2 player agents (perspective, recon-once, boucle await→play) + agent **setup**
   (build le runner partagé, renvoie runnerId) + agent **teardown** (adjuge + dispose + démo).
3. Workflow **arbitre** : `parallel([playerA, playerB])` par match + fan-out sur N matchs ;
   mesure pump via `rpc-queue` (combien de matchs concurrents avant que « ça respire pas »).

### Validation tranche 2 (2026-06-22 — 1 match end-to-end, sonnet)
**✅ La boucle self-play CONVERGE.** Setup (`build` runner 2) → `attach` player B → 2 player agents
CHAUDS (équipe 1 / équipe 2) lancés **en parallèle**, coordonnés **uniquement par le host**
(`/api/selfplay/:id/await`) → match joué jusqu'à `stage=Finished` (team 1 vainqueur, ~6-8 tours
par camp, ~115 k tokens/agent). **Aucun deadlock**, hand-off A↔B propre, fidélité OK (contextes
séparés, perspectives séparées), démos + décisions clés remontées par chaque player. Les **3
chemins de l'endpoint** validés live : `yourTurn` / `timedOut` / `gameOver` (stage=2 Finished).
- **Friction #1 (PROMPT, pas code) à corriger en tranche 3** : `play --no-ai` **termine le tour
  après le spec** (applique toutes les actions du spec PUIS endturn-flip). Les players ont
  **sous-batché** (peu d'actions/spec) → tour terminé avant que toutes leurs units jouent =
  activations gâchées. **FIX** : le `playerPrompt` doit imposer « un seul `play --no-ai --spec
  [TOUTES tes units + finishs]` par tour ; pas de within-turn feedback en v1 — on planifie le tour
  complet depuis la carte (comme les combat-agents) ».
- **Friction #2 (recon/usage, pas plumbing)** : `LightOfSanguinius` (ability 1177, Dante) renvoie
  `ok=True mutated=False` (0 effet) sur ~6 tentatives chez les deux players → condition non
  satisfaite (free-hex adjacent ? « has not moved » ?) mal lue. À recon (`gameconfig.py --ability
  LightOfSanguinius`) et noter dans toolfeedback/wiki — n'affecte PAS le hand-off.

### Confrontation des 2 retours = vérif indépendante GRATUITE (tranche 3 — teardown)
Le retrait de l'étage verif (wave) a coûté l'indépendance du verdict (un agent s'auto-juge →
biais de confirmation). **La self-play la récupère pour rien** : A et B analysent le MÊME match
depuis des côtés OPPOSÉS, en contextes SÉPARÉS → pour tout ce qui est **cross-observable**, on a
**2 témoins indépendants**. Le **teardown** (barrière après `parallel([A,B])` qui reçoit les 2
retours) devient un agent **CONFRONTATION + adjudication** AVANT l'écriture :
- **win-condition** : `A.win_condition.theirs` (lecture de B par A) vs `B.win_condition.mine`
  (auto-lecture de B) → accord = confiance, divergence = un des deux a mal lu.
- **mechanics** : surtout les abilities de l'ADVERSAIRE (cross-observables — A voit les abilities
  de B frapper contre lui) = 2 observations indépendantes de la même mécanique.
- **threat/role** + **outcome** (divergence d'issue → fallback sur le **vainqueur autoritatif**
  FinishMatch/`Match_Winner`, pas la perception — cf. A « team2 wipe » vs B « Njal survit » = timing).
- **Mapping consensus → confiance** : les 2 d'accord → **high-confidence (wiki)** ; un seul → candidat
  (hypotheses) ; contradiction → flag. **`gameconfig`/i2 reste l'arbitre** des règles DISCRÈTES —
  le consensus est un PRIOR fort, PAS la vérité (les 2 peuvent se tromper pareil).
- **Caveats** : ne couvre que le **cross-observable** (mécanique déclenchée par mes SEULES units →
  1 seul témoin → retombe sur l'auto-vérif) ; **asymétrie de perspective** (A *infère* B vs B
  *connaît* B → une divergence peut être complémentaire, pas une erreur).
→ 2ᵉ raison d'être de la self-play au-delà des démos : un **moteur de vérif par consensus à 2
observateurs**, qui répond pile à la perte d'indépendance du verif.
