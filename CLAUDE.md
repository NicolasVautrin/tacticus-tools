# tacticus-tools

Hooking Frida de **WH40K Tacticus** (Windows PC build, Unity 6 IL2CPP) — monorepo TypeScript.

## Structure

- Racine : `C:\Users\nicolasv\tacticus-tools`
- `frida/` — codebase active (hooks TS + host TS, bundlé par `frida-compile`)
  - `frida/hooks/` — script injecté dans Tacticus
  - `frida/host/` — serveur Node qui pilote les sessions Frida (Express + WS)
  - `frida/public/` — frontend browser (statique, servi sur `/view/`)
  - `frida/dist/` — outputs build (gitignored)
- `hooks-legacy/` — ancien répertoire de hooks, conservé pour one-shots (dumps,
  probes historiques). Voir `hooks-legacy/README.md` pour classification.
- `data/` — dumps IL2CPP (`symbols.json`, abilities, enums) — gitignored
- `sources_win/` — décompilation Ghidra de `GameAssembly.dll` — gitignored
- `STATUS.md` — état d'avancement vivant du projet

## Cible Windows

- **Exe** : `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\Tacticus.exe`
- **GameAssembly.dll** : ~60 MB, IL2CPP AOT (Unity 6000.3.8f1)
- **Pas d'`adb`, pas de device, pas de `frida-server`** : injection locale via `frida.getLocalDevice()`

### Hash du build = identité du dump

Tacticus stocke chaque build dans `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\`
où `<HASH>` (ex. `nb3o9lmt6c`, `uu2fr8mv6c`, …) **change à chaque mise à jour**
du jeu. Toutes les RVAs IL2CPP, dumps Il2CppDumper (`data/win_dump/`,
`data/dumps/<HASH>/`), décompilations Ghidra (`sources_win/`) et caches
analytiques (`data/all_game_targets_win.tsv`, `call_graph_win.json`, …) sont
**spécifiques à ce hash**. Une RVA résolue contre le mauvais dump donne un
nom de méthode incohérent — symptôme classique : la stack pointe vers une
méthode qui n'existe pas dans le binaire actif (typique : `findMethod` retourne
RVA différente de celle dumpée), et tous les hooks installés via RVA hardcodée
(ex. `RVA_BUCKET_ADD_ACTION = 0x1478820`) tombent sur du code aléatoire.

**Avant de consulter `sources_win/` ou `data/dumps/<HASH>/` ou de croiser
une stack frame contre `all_game_targets_win.tsv` :**

1. Lire le hash du build courant :
   ```bash
   ls -d /c/Users/nicolasv/AppData/Local/tacticus/games/*/
   ```
2. Lire le hash du dump :
   ```bash
   cat data/dumps/<HASH>/HASH    # ancien data/win_dump/HASH
   ```
3. **Si les deux ne matchent pas, refuser l'analyse offline** : signaler à
   l'utilisateur, demander un re-dump avant tout. Forcer la désynchronisation
   silencieuse a déjà coûté plusieurs heures de debug.

### Règle de code : résolution runtime, pas de RVA hardcodées

**Tout hook doit résoudre son entry point en runtime** via la table IL2CPP :

```ts
const klass = findClassAnywhere(ns, cls);              // helpers.ts
const mptr = findMethod(klass, methodName);            // helpers.ts
Interceptor.attach(mptr.ptr, { ... });
```

**Aucune RVA hardcodée**, ni en constante, ni en fallback `?? il2cppBase.add(0x...)`.
Une RVA copiée d'un dump devient invalide au prochain changement de hash, et
`Interceptor.attach` réussit silencieusement sur du code aléatoire — symptôme
que le hook ne fire jamais (ou fire et crashe). Si `findClassAnywhere` ou
`findMethod` ne trouve pas la méthode (rare — typiquement des gshared bodies
ou des classes non indexées par `image_get_class`), c'est une vraie limitation
à investiguer, **pas** un cas pour ressortir un RVA offline.

Cette règle s'applique aux dumps offline pareil : tout `data/dumps/<hash>/*.tsv`
ou `*.json` n'a de valeur que pour la **lecture humaine** (consulter du code
décompilé, comprendre l'archi). Aucun hook live ne doit en dépendre.

## Démarrage

```bash
cd frida && npm run dev
```

Host sur `http://127.0.0.1:8765`. Front sur `http://127.0.0.1:8765/view/`.

## Workflow utilisateur (validé)

1. Lancer Tacticus, attendre que le menu principal soit pleinement loaded.
2. Ouvrir le front (`/view/`).
3. **Injecter** via `POST /api/admin/inject` (body `{}`) — auto-discovery du PID
   du jeu via le dossier `<basename>_Data/` adjacent à l'exe. (Le bouton INJECT
   du front `/view/` fait le même appel mais **n'est plus utilisé** : l'injection
   passe par l'API / les scripts.)
4. **Warmup** = appeler le RPC `warmupGameSingletons({ force: true })`.
   **Autonome** : il pilote toute la nav UI lui-même (campagne → node → play →
   capture ctor → pause → retreat) et capture `lastSource` +
   `lastUnitProgression` + `IdunUniverse`, push `builder_ready` au front (refresh
   catalog). **Aucun clic humain ; Claude ne demande JAMAIS à l'utilisateur de
   cliquer une battle in-game.** (Détails : section « Workflow RL ».)
5. Builder front : tout est armé. On peut générer la `BattleConfiguration` de
   n'importe quelle node (events inactifs inclus) sans relancer une battle.

## Workflow RL — runner isolé

> **Le LANCEMENT DE RUNNER est centralisé dans `.claude/skills/tacticus/references/runner.md`**
> (inclus ci-dessus, pointé par les agents `validator`/`re-expert`) : warmup obligatoire, voie
> `rl_duel build`, choix de board (`--board`/`--board-pool` + `board.py`), discipline runner.
> C'est LA source unique — ne pas dupliquer ces règles ici.

Pour entraîner un agent RL / valider le moteur sans toucher au battle in-game, on monte un
**runner isolé** depuis une **seed BC sur disque** (`rl_duel build`), déployé et pilotable à
volonté sans casser le jeu actif. Rappel des deux points les plus violés (détail : `runner.md`) :

1. **Warmup une fois par session Frida** (après chaque inject/reinject), AVANT tout RPC/build :
   `warmupGameSingletons({ force: true })`. **Autonome — aucun clic humain** : pilote la nav
   (campagne → node → play → capture ctor → pause → retreat) et force l'init des singletons/classes.
   Claude l'appelle directement après chaque (re)inject et NE demande JAMAIS de cliquer une battle.

   > **RÈGLE INCONDITIONNELLE — warmup après CHAQUE (re)inject, AVANT tout RPC/probe, SANS EXCEPTION**,
   > y compris les probes « self-contained » montés depuis une seed BC sur disque (ex.
   > `rl_probe_step.py`, `rl_collect_batch`). Un (re)inject repart avec des caches `MethodInfo*`
   > Frida-side vides + la couche d'init IL2CPP non ré-amorcée dont dépend `initAndStart`. Un probe
   > qui « marche » sans warmup ne prouve rien (jeu déjà warm par chance) → au prochain build froid
   > c'est le crash `0x2c` (metadata non initialisée). Ne jamais raisonner « ce mode-là n'a pas
   > besoin de warmup ».

2. **Build + pilotage** : `rl_duel build --seed <s> --state-file <propre> [--p-units/--a-units,
   --board/--board-pool, ...]` puis `view/act/play/aiturn` ou `engine_validate.py --runner <id>`.
   Discipline runner (state-file propre, `--runner` explicite, coexistence/MAX_RUNNERS=10, dispose
   tes runners jamais ceux des autres) : `runner.md` §3.

## Build + Injection

```bash
cd frida && npm run build:hooks   # → frida/dist/hooks.js (~110 KB)
```

L'**injection se fait via `POST /api/admin/inject`** (body `{}`) — pas en ligne
de commande, et **plus via le bouton UI** (le front `/view/` n'est plus utilisé
depuis longtemps ; il appelle le même endpoint). Le host gère device discovery,
attach, load script, session lifecycle. Un inject frais crée une session neuve
qui charge le `dist/hooks.js` courant ET est trackée par `/api/admin/status`
(→ re-warmup ensuite, cf. Workflow RL).

Pour info : (file:///C:/Users/nicolasv/tacticus-tools/frida/host/admin.ts) +
(file:///C:/Users/nicolasv/tacticus-tools/frida/host/sessions.ts) (cycle de vie
des sessions, durci — cf. « Robustesse du harnais » ci-dessous).

## Arrêt

- Ctrl+C dans le terminal `npm run dev`, ou
- `curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown` (graceful).

## Restart du host (pour Claude)

Quand tu modifies du code dans `frida/host/` (router, config-store, sessions,
admin, …) le host doit être redémarré — `npm run dev` lance `tsx host/index.ts`
**sans watch**. Procédure :

1. Shutdown graceful : `curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown`
2. Relance en background : `cd frida && npm run dev > /tmp/host.log 2>&1 &`
3. Vérification : `curl -s http://127.0.0.1:8765/api/health` doit retourner
   `{"status":"ok"}` après ~3 s.

**Important** : le restart du host **réinjecte** l'agent Frida via auto-restore
(load fresh `dist/hooks.js` dans le PID Tacticus). L'état mémoire du précédent
agent est perdu — donc :
- `lastSource` (CampaignGameModeSource), `lastUnitProgression`, `lastUniverse`
  redeviennent `null`
- Les RPCs `buildCampaignConfig` / `dumpCampaignCatalog` / etc. répondent
  "no live CampaignGameModeSource captured" jusqu'à re-warmup
- **Ré-armer = appeler `warmupGameSingletons({ force: true })`** (RPC autonome,
  pilote la nav UI seul — aucun clic humain). **C'est la procédure par défaut
  pour Claude : ne jamais demander à l'utilisateur de cliquer une battle.**
  (Le hook `CampaignGameModeSource..ctor` recapture aussi si l'utilisateur
  navigue manuellement, mais ce n'est pas requis.)

Re-build de `dist/hooks.js` requis uniquement quand `frida/hooks/*` a changé
(`npm run build:hooks` avant le restart).

**Changement `frida/hooks/*` SEULEMENT (pas `frida/host/*`) → PAS besoin de
restart host.** Plus léger et propre : rebuild puis réinjecter via
`POST /api/admin/inject` (body `{}`), qui stoppe proprement la session courante
(protocole cleanup) et ré-attache en chargeant le `dist/hooks.js` frais (nouveau
`sessionId` en retour). Le restart complet du host n'est nécessaire que si du
code `frida/host/*` a changé. Dans les deux cas, **re-warmup ensuite via
`warmupGameSingletons({ force: true })`** (autonome — cf. Workflow RL) **AVANT
tout RPC/probe, sans exception** (même les probes seed-BC sur disque type
`rl_probe_step --mode card` : cf. la RÈGLE INCONDITIONNELLE du Workflow RL).

### Robustesse du harnais de session (`frida/host/sessions.ts`)

Le cycle de vie des sessions Frida est **durci** contre les zombies et les
injects wedgés. À connaître pour diagnostiquer un état de session incohérent :

- **Signal `fridaScript.destroyed` câblé** (en plus de `fridaSession.detached`) :
  un script qui meurt seul marque la session `stopped` via un `finalize()`
  idempotent — **plus de session fantôme « running » à script mort** qui faisait
  échouer tout RPC avec le brut `"Script is destroyed"`.
- **Porte de vivacité post-`load()`** dans `runScript` : si le script est
  `isDestroyed` juste après le load (typique d'un **PID wedgé** par un agent
  précédent), la session passe `error` (message actionnable) et `runScript`
  **throw** — au lieu de rendre une session fantôme « running ». La course
  `agent_ready` de 15 s reste un fallback by-design ; seul `isDestroyed` est un
  échec dur (pas de faux positif sur un simple boot lent).
- **`requireLiveSession(id)`** (utilisé par `rpcCall` / `postMessage`) : self-heal
  du zombie (marque `stopped` + prune runners) puis erreur **actionnable** au lieu
  du brut frida : « reinject (`POST /api/admin/inject`) ; si l'inject wedge sur le
  même PID, relance Tacticus d'abord ».
- **`pickLiveSessionId()`** (délégué par `pickRunningSession`, donc
  `/api/admin/status` et les autres call-sites) : filtre `running` **ET** script
  vivant → l'état admin ne publie plus un zombie.

**Conséquence pratique** : un reinject qui wedge le PID (cf. le cas connu où un
reinject après stop hang dans le même PID Tacticus) échoue désormais **franchement**
avec « relance Tacticus ». Récupération = **relancer le jeu** puis restart host
(l'auto-restore rediscover le nouveau PID par exePath) ou fresh inject.

## Serveur ghidra-mcp (analyse offline)

Le serveur MCP `ghidra` expose `GameAssembly.dll` analysé + symbolisé (decompile,
xrefs, callgraph, recherche sémantique) en **lecture seule** — aucun lien avec les
hooks Frida live. Il tourne en **headless via `pyghidra-mcp`** (serveur HTTP
persistant), et **ne démarre pas tout seul** : c'est un lancement **manuel**.
Le `.mcp.json` du projet ne fait que **se connecter** à l'URL
((file:///C:/Users/nicolasv/tacticus-tools/.mcp.json)) :

```json
{ "mcpServers": { "ghidra": { "type": "http", "url": "http://127.0.0.1:13337/mcp" } } }
```

### Démarrer le serveur

```bash
pwsh -File C:\Users\nicolasv\ghidra-mcp\start-ghidra-mcp.ps1   # build courant (gqfc5mff6c)
# autre build : ... start-ghidra-mcp.ps1 -Project <chemin\gameassembly.gpr>
```

- **Le tool Bash de Claude n'a pas `pwsh`** → lancer via le tool PowerShell (5.1).
  `Start-Process` en 5.1 n'a pas `-Environment` : poser `$env:JAVA_HOME` +
  `$env:GHIDRA_INSTALL_DIR` dans la session **puis** `Start-Process` (l'enfant hérite
  l'env). Le script `start-ghidra-mcp.ps1` fait déjà tout ça.
- **Boot ~2 min** (`--wait-for-analysis`). Tant que le port n'écoute pas, l'analyse
  tourne ; **quand le port 13337 écoute, l'analyse est terminée** (le serveur n'ouvre
  le port qu'à la fin). Sur projet déjà analysé, pas de ré-analyse (détecte « already
  complete »).

### Vérifier / connecter

```bash
# le port écoute ?
netstat -ano | grep "127.0.0.1:13337.*LISTENING"
```

`.mcp.json` se charge **au démarrage de session** : si le serveur a été lancé
après l'ouverture de Claude Code, faire `/mcp` (reconnect) ou recharger la session
pour exposer les outils `mcp__ghidra__*`. Si `/mcp` affiche `ghidra · failed`,
c'est quasi toujours que **le serveur n'est pas lancé** → le démarrer puis `/mcp`.

### Ne pas faire

- **Ne pas repasser `.mcp.json` en transport `stdio`** (`command`/`args` lançant
  `pyghidra-mcp.exe`). Avec `--wait-for-analysis`, l'exe bloque ~2 min sur le boot
  Ghidra **avant** de répondre au handshake MCP → Claude Code timeout → `failed`.
  Sans `--wait-for-analysis` c'est pire (analyse skippée, tools « Analysis
  incomplete »). Une 2ᵉ session entrerait aussi en collision sur le lock du `.gpr`.
- **Lock bloqué** : si un lancement précédent est mort, il peut rester un
  `gameassembly.lock` / `.lock~` dans `data/ghidra_<HASH>/`. Si **aucun** process
  java/pyghidra ne tourne, ces locks sont périmés → les supprimer avant de relancer.

### Au changement de build du jeu

Le `<HASH>` change → refaire le pipeline (dump Il2CppDumper v39 → import/analyse
Ghidra → apply IL2CPP names) puis pointer `-Project` sur le nouveau `.gpr`.

## Compréhension des mécanismes = RE ghidra fidèle, PAS d'expérience

Pour comprendre un mécanisme du jeu (formule de dégât, prédiction, scoring IA, etc.), la
méthode attendue est la **rétro-ingénierie fidèle via ghidra** (le décompilé = vérité), **pas**
l'expérimentation live (« je fais varier un input et j'observe la sortie pour deviner la formule »).

- **Le live sert UNIQUEMENT de confirmation** d'un mécanisme déjà compris depuis le code natif,
  jamais de source pour deviner/fitter une formule.
- **Chercher d'abord les fonctions NOMMÉES décomposées** (`mcp__ghidra__search_symbols_by_name`
  sur le namespace, ex. `DamageCalculations$$`, `DamagePrediction$$`) **avant** de grinder une
  fonction inline géante (`PredictAttackRaw` ≈ l'inline optimisé de ~80 méthodes propres). Porter
  depuis les feuilles propres (1:1 méthode→fonction), pas depuis l'inline.
- **Les traces/hooks live = un OUTIL DE CIBLAGE de la RE, JAMAIS un outil de découverte de formule.**
  Le SEUL usage légitime d'un hook live dans une enquête RE : poser **UN** hook + `Thread.backtrace`,
  lire la **chaîne d'appels** (frames `il2cpp+0xRVA` → soustraire `0x180000000` → adresses de
  fonctions), en déduire **quelle(s) fonction(s) NOMMÉE(S)** est en jeu, puis **aller LIRE ces
  fonctions dans ghidra** (`decompile_function`). Le backtrace répond à **« QUELLE fonction dois-je
  RE ? »**, jamais à « quelle est la formule / la valeur ? » — ça, c'est le décompilé qui le donne.
  - **Anti-pattern PROSCRIT** (déjà commis, ~10 reinjects gaspillés en une session) : empiler hook
    après hook (capturer la sortie de la feuille A, puis B, puis les 29 feuilles, puis le bonus…)
    pour **re-découvrir en tâtonnant** ce que la fonction nommée du décompilé donne en 30 s de
    lecture. Dès qu'un backtrace (ou un simple `search_symbols_by_name` sur la classe de service)
    pointe une fonction nommée pertinente (`CalculateElevationBonusModifier`, `CalculateDefenderModifiersForPrediction`,
    …), **STOP les hooks → lire le décompilé**. Réflexe de départ : `search_symbols_by_name` sur la
    classe de service (`DamageCalculations$$`, …) et LIRE, **avant** de poser le 1ᵉʳ hook.
  - Corollaire : ne pas confirmer live une valeur (« le +50 vient-il d'ici ? ») qu'on peut LIRE dans
    le code. Le live ne confirme QUE ce que le décompilé ne peut pas trancher statiquement (ex.
    valeur runtime d'un état, ordre d'énumération non-RE, generic-sharing ambigu).
- **Ne JAMAIS asserter un mécanisme sans l'avoir lu dans le décompilé** : un pattern qualitatif
  observé (« la largeur dépend de la cible ») ≠ formule vérifiée. Marquer toute déduction non
  encore lue dans le code comme **hypothèse**, et la confirmer dans ghidra avant de l'affirmer ou
  d'agir dessus.
- **Pourquoi** : les expériences live coûtent du temps, sont bruitées (positions/effets/RNG
  cachés), et mènent à des fits faux (cf. hypothèses crit puis perçage-seul réfutées). Le décompilé
  donne le mécanisme exact, déterministe et modifiable.

### Tester / confirmer live = ADAPTER LES TEAMS à l'objectif

Quand le live sert à **confirmer** un mécanisme (jamais à le deviner — cf. ci-dessus), **toujours
crafter les rosters + tailles + positions pour que la condition à observer SOIT remplie et STABLE
assez longtemps**. Ne pas lancer une bataille générique/aléatoire puis se battre contre ses
dynamiques émergentes.

- **Garder vivante l'unité observée** : team adverse faible/peu nombreuse, ou la driver en lieu sûr
  (une unité en sécurité survit indéfiniment — prendre autant de tours que nécessaire).
- **Éliminer le bruit** : 1 mécanisme à la fois (ex. si on étudie MES summons, pas de summoners
  ennemis qui polluent l'observation).
- **Garantir l'occasion d'agir** : un ennemi vivant à portée/atteignable pour voir l'attaque/le move.
- **Pourquoi** : faute déjà commise (combat où les scarabs se faisaient focus/tuer en 1 round avant
  d'avoir pu agir → impossible de valider « les summons agissent-ils par tour ? » ; la cause était le
  setup, pas le mécanisme). Prolonge la règle « driver les positions, ne pas blâmer la géométrie ».

### La structure du code Python doit refléter celle du jeu

Le port Python d'un mécanisme natif doit **coller le plus possible à la structure du code du jeu** :

- **1:1 classe native → module, méthode native → fonction homonyme**, avec la **VA citée** en
  commentaire (ex. `# DamagePrediction.GetBaseDamageFix64 @181030ba0`).
- **Validable méthode par méthode** contre le natif — pas de black-box ni de cache d'outputs (on
  RE-CALCULE le mécanisme depuis ses entrées, on ne stocke pas la sortie native).
- **Pourquoi** : c'est ce qui rend le moteur **fidèle ET modifiable** (le but du portage) — on peut
  changer un paramètre/une règle au bon endroit, comme dans le jeu. Une structure qui diverge du
  natif devient impossible à valider finement et à faire évoluer.

#### RÈGLE IMPÉRATIVE — PARTIR de la fonction native NOMMÉE, NE JAMAIS inventer

**Avant d'écrire UNE ligne de port, ouvrir le décompilé et partir de la fonction/classe NATIVE
NOMMÉE.** L'ordre est non négociable : (1) `search_symbols_by_name` sur le mécanisme →
(2) lire la fonction native → (3) nommer la fonction/classe Python **d'après son homonyme natif +
`# NomNatif @VA` en commentaire** → (4) mirroir de la **chaîne d'appels** native. **INTERDIT
d'inventer un nom ou une structure quand une contrepartie native existe.**

- Si un helper offline préexistant a un **nom inventé** (ex. `predict_normal`/`predict_special`),
  NE PAS prolonger ce pli : le réaligner sur son homonyme natif quand on le touche
  (`MakeDamagePredictions` → `GenerateMultiHitAttackPredictions` → `CalculateDamagePredictionScenario` ;
  utilité `CalculateUtilityFromPredictions` = `Σ CalculateUtilityFromDamageEvent`).
- **Ne pas découper une fonction native en plusieurs fonctions Python** au nommage arbitraire
  (ex. inventer `predict_special_aoe` alors que le natif est UN seul
  `<Ability>Playbook.MakeDamagePredictions` qui produit la liste main + AoE). Une fonction native =
  une fonction Python homonyme.
- **DSL du jeu = arbre d'expression LAZY** (`DSLFactory`/`TargetsSelector` : `Sum`/`Min`/`If`/
  `SurroundingUnits`/… sont des NŒUDS, car leurs opérandes sont des sous-formules runtime type
  `TotalTimesAttacked`). On le mirroir par un **moteur de nœuds** (`engine/dsl/nodes.py`,
  `Node.evaluate(ctx)`), chaque ability = l'arbre EXACT du décompilé, vérifiable nœud-par-nœud.
  Nuance port **eager** : on résout les feuilles puis on combine → l'arithmétique triviale
  (`Sum`=`+`) NE doit PAS être un wrapper inutile ; le socle générique ne garde que le NON-trivial
  (géométrie/ciblage/état runtime). ⚠ **Ghidra MISLABEL les ctors de nœuds gshared** (le ctor de
  `DSLFactory.Sum @180dfc200` s'affiche `HasUsedActiveAbilityThisTurnTrigger$$.ctor`) → sémantique
  lue via la STRUCTURE (pointeur de classe, args, arithmétique), JAMAIS via les noms.
- **Pourquoi (faute déjà commise, corrigée 3× en une session par l'utilisateur — « pourquoi tu
  invente alors que la doctrine est claire ? »)** : inventer des noms/structures rend le port
  invérifiable contre le décompilé, non-évolutif, et fait perdre du temps en corrections. Le nom
  natif + la VA sont la preuve de fidélité.

## Sorties console Python — ASCII only (Windows cp1252)

La console Windows (et les tools Bash/PowerShell) tourne en **cp1252**, pas UTF-8.
Tout caractère non-ASCII envoyé à `stdout` (un `print`, un message d'assertion pytest
affiché via `-s`, une f-string de diagnostic) lève **`UnicodeEncodeError`** et fait
**crasher le script / échouer le test** — un faux négatif qui masque le vrai résultat
(les assertions, elles, passaient).

- **Dans tout `print`/log/sortie de script ou de test Python : ASCII uniquement.**
  Remplacer les symboles courants : `->` (pas `→`), `OK`/`X` (pas `✓`/`✗`), `<=`/`>=`
  (pas `≤`/`≥`), `Delta`/`d=` (pas `Δ`), `x` (pas `×`), `v`/`down` (pas `↓`), `...`
  (pas `…`). Le français accentué (é, è, à) est **aussi** non-ASCII → l'éviter dans les
  chaînes *imprimées* (OK dans les commentaires/docstrings non imprimés).
- **Pytest** : ne pas compter sur `-s` pour voir des prints contenant du non-ASCII (ça
  crashe). Invoquer pytest **sans `-s`** (sortie capturée) ; si une diagnostic est
  vraiment nécessaire à l'écran, la garder ASCII ou poser `PYTHONIOENCODING=utf-8`.
- **Pourquoi** : faute déjà commise plusieurs fois (`→`/`✓`/`Δ`/`↓` dans des prints) ;
  le contenu *écrit dans un fichier* via `open(..., encoding="utf-8")` n'est PAS concerné,
  seulement ce qui part vers la console.

## Tests du moteur Python — NE PAS relancer la suite complète

Après une modif, **ne lancer QUE les tests CIBLÉS de la tranche touchée**, jamais toute la
suite `tests/engine/` — **beaucoup trop lourd**.

- **Pourquoi** : chaque test live monte une (ou plusieurs) bataille(s) isolée(s) via le runner
  (build + nav + RPC). Un seul fichier = quelques dizaines de secondes à plusieurs minutes ; la
  suite entière = ~10 min+ et sature la session Frida. C'est un coût disproportionné pour valider
  un changement localisé.
- **Comment** : invoquer pytest sur les **fichiers pertinents uniquement** (ex. slice DAMAGE →
  `test_damage_roll_live.py` + `test_runner_attack_live.py` + les tests crit/block ; slice EFFETS →
  `test_effect_*_live.py`). Inclure un test de garde par dépendance impactée (ex. une modif d'un
  composant partagé `effects`/`base` → relancer aussi un test damage qui consomme ce chemin), mais
  **pas plus**.
- **Suite complète** : seulement sur **demande explicite** de l'utilisateur, ou avant un jalon
  (commit d'une tranche), pas après chaque édition.

## Agents (subagents) — TOUJOURS en worktree isolé

**Tout agent (outil `Agent`, et `agent()` d'un `Workflow`) doit être lancé avec
`isolation: "worktree"`, sans exception.**

- **Pourquoi** : sans `isolation`, l'agent partage MON working directory et peut
  éditer les mêmes fichiers que moi. Un agent qui monkeypatche le code (même
  « temporairement » pour reproduire un cas) corrompt alors mon arbre — déjà subi :
  un validateur a laissé `return /float(...)` dans `engine/utilities/tile.py`
  → `SyntaxError` cassant tout l'import `engine`. Avec `isolation: "worktree"`,
  l'agent bosse dans SON checkout jetable (`.claude/worktrees/agent-<id>/`, branche
  `worktree-agent-<id>`, auto-nettoyé si inchangé) → ses edits/monkeypatches ne
  touchent JAMAIS mon arbre. L'isolation par défaut prime sur son coût (~200-500 ms
  + disque). (`isolation: "remote"` = variante cloud, toujours en background.)

- **CONSÉQUENCE — le worktree part du HEAD de `master` (la base), PAS de ma branche
  courante ni de mes changements NON COMMITÉS.** Un working tree sale / une
  side-branch est INVISIBLE au worktree → l'agent auditerait du code périmé (déjà
  arrivé : un validateur a audité `8f9c547` sans le code à valider). Donc si l'agent
  doit VOIR mon travail en cours :
  1. **commiter sur `master` d'abord** → le worktree (= master HEAD) a le code
     automatiquement, aucun hash à passer (chemin propre, à privilégier) ; OU
  2. **fallback** : passer le **hash du commit dans le `prompt`** + instruire l'agent
     de `git checkout <hash>` + vérifier (`git rev-parse HEAD` == hash + grep un
     marqueur) AVANT d'agir. Il n'existe PAS de champ structuré pour un ref/commit
     dans l'outil `Agent` — c'est une convention de prompt (fragile, filet de secours).

- **Pipeline (optimiste, ne bloque jamais)** : commiter le checkpoint sur `master`
  → lancer le(s) agent(s) worktree (async, chacun épinglé sur ce commit) → continuer
  à travailler sur `master` (les agents déjà lancés ne bougent pas) → **fix-forward**
  (nouveau commit) sur les findings. N agents = N worktrees isolés (git autorise
  plusieurs worktrees détachés au même commit) → **panel adversarial** possible sur
  un seul commit. Pour un agent d'audit (validator), je prends son **VERDICT**, jamais
  son code (son worktree est jetable).

- **Le warning du harnais « avoid working with the same files or topics it is using »
  (rendu par l'outil `Agent`) NE S'APPLIQUE PAS aux agents `isolation: "worktree"`.**
  Ce message générique vise les agents qui PARTAGENT mon working dir. Un agent worktree
  est **figé au commit de lancement** (checkout jetable, HEAD immuable) → mes edits sur
  `master` (même sur LES MÊMES fichiers que l'agent lit) ne peuvent PAS le perturber, et
  réciproquement. Donc **pendant qu'un agent worktree tourne, je CONTINUE d'éditer `master`
  librement** (implémenter, refactor, committer) — ne JAMAIS m'auto-bloquer « j'attends
  qu'il ait fini de lire ce fichier ». Le seul point de synchro est le **VERDICT** de l'agent
  (que je réconcilie avec mon travail en cours au retour), pas les fichiers.

## Ne jamais

- **Utiliser `--reload`/hot-reload côté host** : casse les sessions Frida
  actives, peut crash Tacticus si `Interceptor.replace` est en cours.
- **Stop manuel d'une session avec `Interceptor.replace` actif** sans le
  protocole cleanup graceful (crash le jeu).
- **Heap scans automatiques** (`Process.enumerateRanges`, `Memory.scan`) :
  Frida suspend les threads de la cible pendant le scan IL2CPP heap (~10 s sur
  Tacticus PC). UnityFreezeDetector (qui est lui-même hooké pour le pump)
  conclut que le main thread est figé → tue le process. Heap scans uniquement
  sur action utilisateur explicite, gated par `allowHeapScan: true`.
- **Broad-hooks sur méthodes UI hot** (`UnitProgression.Get*/Has*/...`) : la
  surcharge des trampolines × hot path = destabilisation IL2CPP cctor cascade.
- **Hook permanent sur des property getters** appelés par les sérialisations
  Newtonsoft du jeu (ex. `GameConfigData.get_gameConfigDto`) : 27 000 appels/s
  → frame >960 ms → crash.
- **Commit** : `data/`, `frida/dist/`, `hooks-legacy/`, `server/`, `logs/`,
  `frida/assets/raw/`, `sources_win/`.

## Documentation détaillée

!include .claude/skills/tacticus/references/hooks.md
!include .claude/skills/tacticus/references/rpc-api.md
!include .claude/skills/tacticus/references/runner.md

<!-- TODO références à (ré)écrire contre le code actuel (les drafts d'avril
     dans .claude/worktrees/agent-a0e45617/ sont périmés) : frida-host.md,
     game-architecture.md, decompilation.md, ai-engine-audit.md, knowledge.md.
     Ne pas !include tant qu'ils n'existent pas dans ce tree (résolution à vide). -->

