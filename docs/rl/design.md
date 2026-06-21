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
existants avant d'en bâtir un). Corrigé par **`keepExisting` opt-in** (défaut inchangé = mono-runner
sûr) + flag **`autoDispose`** sur l'Entry du registre (durcissement recorder). Validé : 2 runners
(seeds 11111/22222) coexistent, `decisionView` OK sur les deux, rosters distincts, **zéro cross-talk**,
via `rl_duel build --keep` + `--state-file` isolés. **Enablers du parallèle** : (1) isolation runner ✓,
(2) state-file par agent ✓, (3) coexistence ✓.

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
  `frida/host/sessions.ts` (rpcCall + pending map), + endpoint host. Rebuild + reinject + warmup + test.

## Questions ouvertes (à trancher avant lancement)
- **Budget/stop** : combien de matchs par session avant un /compact ? un cap de coût (nb matchs) par run ?
- **Observabilité** : se contenter des fichiers, ou la mini-dashboard `/view` vaut le coup plus tard ?
- **Profondeur du sous-agent** : `maxTurns`/garde-fou pour qu'un match ne parte pas en boucle ?
