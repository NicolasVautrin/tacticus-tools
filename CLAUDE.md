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

## RECON D'ABORD : lire le KIT COMPLET de l'unité AVANT toute RE / probe / ghidra

**Le tout PREMIER geste face à un mécanisme lié à une unité (divergence de dégât, effet non porté,
formule d'ability, scoring d'une attaque…) = lire le KIT COMPLET de l'unité concernée** —
`gameconfig.py <unit>` (traits + actives + **passives** décodés, avec les nombres) **ET** le texte
de règles i2 — **AVANT** de poser un hook, lancer un probe live, décompiler dans ghidra, ou écrire
une ligne de port. La recon oriente TOUTE l'enquête : sans elle, on RE à l'aveugle le mauvais
mécanisme.

- **Comment** : `python gameconfig.py <unit>` (kit complet : traits + `[active]` + `[passive]`),
  puis `--ability <name>` / `--trait <name>` pour les tableaux par-niveau + flags
  (`variablesAffectedByRarityBonus`), et le **texte i2** (`--ability`/`--trait` le rend). Croiser
  avec `unit_map.py` si on cherche une unité qui porte un mécanisme donné. Ordre : **gameconfig →
  i2 → (seulement alors) ghidra/probe**.
- **Ce que SEUL le kit révèle** (invisible côté effets capturés / decisionView) :
  - **passif vs actif** : un **passif** est indexé par SON niveau/canal propre, PAS forcément
    l'`activeAbilityLevel` de l'ability active — et sa magnitude peut ne PAS être rarity-scalée.
    (Ex. **SmashaEad = PASSIF** « +437 Damage » ; le confondre avec l'active fausse level+multiplier.)
  - **conditionnels / triggers / snowball** : n'existent QUE dans le **texte i2**
    (« for every 2 hits… », « increased by 73 per hex traversed », « until start of next turn »).
  - **mécaniques de trait transitoires** (ex. GetStuckIn coups bonus, BeastSlayer) qui ne
    remontent JAMAIS comme un effet nommé (`decisionView.effects` est aveugle).
- **Pourquoi** : faute déjà commise (cette session #75 : sauté sur `statModSources` + décompilé
  combat de SmashaEad **avant** de lire que c'est un **passif** — la lecture du kit a montré que
  599/437/300 ne se réconcilient PAS par level/mult, ce que le décompilé seul ne disait pas ; #47
  GetStuckIn +2 coups manqué en ne lisant que les effets capturés). Un mécanisme PAR-UNITÉ ne peut
  pas être RE correctement sans savoir QUEL trait / active / passif le porte. La recon coûte ~1
  commande ; la sauter coûte des heures de RE mal ciblée. (Doctrine déjà en mémoire
  `feedback_recon_units_first` + `feedback_recon_full_kit_not_captured_effects` — ici rendue
  **inconditionnelle et projet-level**.)

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

#### RÈGLE — tout GATE par nom/id/effet doit être JUSTIFIÉ contre le natif (pas un raccourci qui cache un chemin générique)

**Tout branchement conditionné par un nom (ability/effet/playbook/unité) ou un id — `if ability_name == "X"`,
`if id == N`, `X in {_SET}`, `"X" in name` — doit correspondre à une DISTINCTION RÉELLE du natif (une
classe / un id / un enum bespoke côté jeu), commentée avec sa preuve (VA / classe / enum). JAMAIS un
raccourci qui court-circuite un mécanisme GÉNÉRIQUE natif qu'on aurait loupé.**

- **Miroir du dispatch natif** : per-ability → 1 classe native ⇒ registre par **id** ; per-effet → 1 classe
  native ⇒ **factory par nom** ; condition de trait/profil/faction ⇒ gate `HasTrait`/`DamageProfileIs`/
  `IsSameFaction` (par enum/trait, PAS par nom d'unité). Si le natif a UNE fonction générique (ex.
  `RepairPlaybook @181187c00`, `CalculateBaseDamageWithAllModifiers @18102d3f0`), le port passe par CE
  générique — il ne hardcode pas les cas un par un.
- **INTERDIT le substring de nom** (`"Repair" in name`, `"Heal" in name`) comme DISCRIMINANT : il
  false-matche (ex. `NanoscarabRepairProtocols` capté par `"Repair"`, mauvais routage) — utiliser l'**id /
  enum exact**. (Le substring reste OK pour une NORMALISATION de clé documentée, ex. `Heal_<Passive>` → clé
  config gameconfig, ce n'est PAS un gate.)
- **Gate hardcodé INÉVITABLE** (distinction native NON dérivable offline — ex. héritage de `PredictAttack`
  via la vtable +0x27, cf. `_PREDICT_VIA_NORMAL_ATTACK={SpiritLeech}` #90) : (a) commenter la **raison + le
  mécanisme natif + VA** ; (b) le marquer **possiblement INCOMPLET** ; (c) créer une **tâche** pour énumérer
  l'ensemble complet par RE (ex. #92). Ne jamais laisser un tel hardcode silencieux se faire passer pour
  générique/complet.
- **Pourquoi** : un gate par nom non justifié = l'anti-pattern « inventer au lieu de mirrorer » appliqué au
  CONTRÔLE DE FLUX — il fork le port loin de la structure native, casse la généralisation (un cas non listé
  est traité à tort), et devient invérifiable contre le décompilé. Chaque gate doit se lire comme « le natif
  distingue ce cas ICI (classe/id/enum @VA), donc moi aussi » — sinon c'est un chemin générique loupé.

## Divergence de dégât off↔live = DÉCOMPOSITION PAR ÉTAGE (outil), JAMAIS fit de scalaire

**PREMIER RÉFLEXE, INCONDITIONNEL : dès qu'une valeur de dégât diverge offline↔live** (replay-diff,
prédiction↔oracle, `off ≠ live`, un ratio/écart « bizarre »), **le geste n°1 est l'OUTIL DE DÉCOMPOSITION
`scripts/python/tools/damage_decomp.py` — lire la valeur PAR ÉTAGE du pipeline des DEUX côtés et localiser
l'étage divergent. NE JAMAIS fitter un scalaire (×0.9 ? /2 ? mult 90 ?) sur le dégât FINAL.**

- **Pourquoi** : un dégât final est **sous-déterminé** — `300 = 333×0.9 = 167×1.8 = 599/2` : impossible de
  distinguer multiplier / valeur / base / nb de coups depuis le seul endpoint. Le fit-de-scalaire mène à la
  mauvaise piste **de façon quasi garantie** (déjà : ~5 reinjects gaspillés sur #68 à « capter le mult 90 »
  alors que le mult=180 était confirmé live et que le vrai signal était l'additif RÉSOLU ; #49 élévation
  red-herring). **L'étage se LIT, il ne se devine pas.** Si tu es tenté d'écrire « le facteur est ~X donc le
  paramètre Y vaut Z » → **STOP, décompose d'abord.**
- **Pipeline natif (étages nommés)** : `base → GetBaseDamageWithFixedPiercedArmor (pierce/armure) →
  result_bout → CalculateBaseDamageWithAllModifiers (%-mult + ADDITIF via DamageModifiers.Add) → crit/block
  → Amount`. `modifier-observe` (DÉJÀ dans les hooks : RPC `modifierObserveInstall`/`modifierObserveStatus`/
  `modifierObserveReset`) capte la valeur LIVE par étage (base/pierceA/pierceB/penetration/result par bout +
  additif attaquant/défenseur + attribution par-source via `BaseEffect.DamageBonusForAttack`).
  `tools/damage_decomp` : `arm(rpc)` → rejouer l'attaque (seedée) → `read_live_decomp(rpc)` →
  `decomp_report(rr, live_ph, live_decomp)` imprime le tableau + l'ÉTAGE divergent. Démo/gabarit :
  `tests/engine/runner/test_damage_decomp_live.py`.
- **Le décompilé décide QUEL étage RE ; UNE lecture live confirme SA valeur runtime** (cf. « RE ghidra fidèle,
  PAS d'expérience » + « mirror named game functions »). Le live NE sert JAMAIS à deviner une formule.
- **Un « facteur qui colle » sur UN cas = HYPOTHÈSE, pas un fait** : trouver un 2ᵉ cas qui SÉPARE les
  candidats avant de committer (ex. u90 PowerTrip ×180 sans /2 réfute un /2 universel en une ligne). Si une
  mesure DIRECTE contredit l'hypothèse (Level.mult=180 ≠ 90) → **RE-DÉRIVER**, pas patcher l'hypothèse.
- **Côté PRÉDICTION (#96/#98) — deux pièges + la fenêtre de mesure fiable** :
  1. **`aiPredict` (= `DamagePredictionQuery.GetAllPredictions`) N'EST PAS l'oracle du dégât per-ability du
     playbook** : c'est le preview decisionView, Attack-based quel que soit l'abilityType (vérifié cache ET
     `fresh:true`). Une égalité `aiPredict(special)==aiPredict(normale)` ne prouve RIEN (faux verdict #96,
     PlasmaCannon routé Attack-based à tort). Tuile d'attaque invalide → fallback
     `GetPredictionForTargetsUnreachableFromSelectionTile` (valeur d'une AUTRE tuile).
  2. **La fenêtre fiable = le tour de décision IA OBSERVÉ** : `modifierObserveInstall` → `Reset` →
     `aiPlayByUnit` → `modifierObserveStatus`. Étages prédiction : `multDumps` (chaque multiplicateur
     composé ×1000 + topRva — LA décomposition du ×k), `predCalcDumps` (in→out per-bout,
     `DamagePrediction.CalculateBaseDamageWithAllModifiers`), `valueDumps` (bouts post-perçage, ring 200),
     `varLevelDumps` (variables d'ability niveau×mult). Tuiles candidates SÉPARATRICES (not-moved+élévation
     vs moved+plate) pour isoler les gates. Cas d'école complet : prediction.md « MAJ #96 REVERTÉ + #98 RÉSOLU ».
- Détail : `docs/rl/case-68-orksnob-attacker-effects.md` + memory `feedback_damage_decomposition_measure_stage`.

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

- **Corollaire — « avancer pendant qu'un agent tourne » = prendre la tâche la PLUS UTILE,
  pas la plus isolée.** Ne JAMAIS m'auto-restreindre à du « hors-sujet / offline / pas-ses-
  fichiers » : c'est une sur-prudence qui gâche la parallélisation (déjà subi : une session
  entière passée à me cantonner à des tâches « non-overlappantes » sans raison). Deux clarifs :
  - **Fichiers/sujet = AUCUNE contrainte** (cf. bullet ci-dessus : le worktree est figé au
    commit de lancement).
  - **Session Frida live = PAS un blocage non plus.** La game encaisse très bien plusieurs
    runners concurrents, et les traces sont **par-runner distinctes** (OriginBuffers, mig #43 :
    buffers séparés par origine, purgés au dispose). L'agent et moi pouvons faire des RPC /
    monter des runners EN MÊME TEMPS sans se marcher dessus (disciplines mineures : ne pas
    dépasser **MAX_RUNNERS=10**, **disposer MES runners** jamais ceux des autres).
  - **⛔ LA SEULE VRAIE INTERDICTION pendant qu'un agent tourne : ne PAS (ré)injecter Frida**
    (`POST /api/admin/inject`) — ni **restart host** (qui auto-réinjecte). L'inject STOPPE la
    session courante et en ré-attache une neuve → ça **CASSE la session / le harnais que l'agent
    utilise** (état warm + RPC en vol perdus). C'est le SEUL geste à proscrire ; tout le reste
    (fichiers, sujet, RPC concurrents, runners) est libre. Corollaire : si la game a crashé/
    redémarré et qu'un reinject est nécessaire, **attendre la fin de l'agent** (ou le stopper
    sciemment) avant de réinjecter.
  - **La SEULE attente légitime (hors reinject) = une dépendance de CONTENU** : si mon prochain
    pas (ex. un port) dépend du **VERDICT** de l'agent (une réponse RE encore inconnue), j'attends
    ce verdict — pas parce que « fichiers/session partagés » (faux), mais parce que coder à
    l'aveugle = deviner. Distinguer cette vraie dépendance de la fausse contrainte d'isolation.

- **Reprendre un agent background STOPPÉ / perdu = `SendMessage(to: <agentId>)`, PAS un nouvel appel
  `Agent` (qui repart de ZÉRO) ni un synthétiseur du transcript.** L'outil `Agent` n'a AUCUN `--resume` :
  un nouvel `Agent` démarre toujours frais. SEUL `SendMessage(to: <agentId>)` continue un agent déjà
  lancé — il recharge son **transcript** (= la conversation JSONL de l'agent sur disque,
  `…/tasks/<agentId>.output` : prompt + tours assistant + `tool_use`/`tool_result`) puis y ajoute mon
  message. C'est le VRAI équivalent de `--resume`.
  - Agent **terminé** ou stoppé **proprement** (`TaskStop`) → transcript flushé → resume **AVEC contexte
    intact**. Cas normal.
  - **Exit BRUTAL du process Claude Code parent** (crash / Ctrl-C sur la session / terminal fermé) pendant
    que l'agent tourne → buffer jamais flushé → transcript **0 octet**, contexte perdu → le `SendMessage`
    « reprend » mais **À VIDE** → je dois **RÉ-INJECTER tout le contexte de la tâche** dans le message de
    reprise. (Vécu : re-expert perdu à une interruption, `.output` 0 octet ; reprise `SendMessage` +
    ré-injection manuelle du contexte technique → OK, verdict rendu end-to-end.) NB : un `TaskStop` **propre**
    ≠ perte de transcript (il le préserve) ; seul l'exit brutal du parent le perd.
  - Ne JAMAIS lire le transcript moi-même (conversation entière de l'agent = déborde MON contexte) ; pour
    récupérer le partiel d'un agent mort, **déléguer la SYNTHÈSE** à un sous-agent qui le lit en chunks
    (offset/limit) et me rend ~15-30 lignes.

## Manques de portage = tâches (automatique)

**Tout manque de portage constaté ⇒ une tâche créée IMMÉDIATEMENT (`TaskCreate`), sans attendre.**
Dès que je constate qu'un mécanisme natif n'est pas reproduit par le moteur offline — effet/trait/
formule non porté, divergence runner↔live ou prédiction↔oracle, `off ≠ live` dans un replay-diff,
un `# TODO`/no-op documenté rencontré — je crée automatiquement une tâche qui le capture : **unité/
effet concerné + symptôme CHIFFRÉ (off vs live) + VA/fonction native si connue + pointeur doc
case-study** si pertinent.

- **Pourquoi** : un gap laissé en remarque de conversation est perdu au `/compact` ; laissé dans
  un seul doc, il n'est pas suivi. Le système de tâches est LE registre des gaps de fidélité — je
  dois pouvoir lister « ce que le moteur ne reproduit pas encore » à tout moment.
- **S'applique aux découvertes FORTUITES autant qu'aux gaps ciblés**, et sans me laisser détourner
  de la tâche courante (créer la tâche ≠ la traiter tout de suite). Ex. la sonde RNG de #62c a
  révélé au passage que le runner omet des effets de dégât d'orksNob (SmashaEad self-buff,
  BeastSlayer) → tâche créée sur-le-champ.
- Complète « persist findings durably » : la tâche = le tracker actionnable ; le doc case-study =
  le détail RE. Les deux, pas l'un OU l'autre.

## DÉCIDER ≠ EXÉCUTER — deux chemins/registres SÉPARÉS, le no-op combat est SILENCIEUX

**Porter/valider le côté DÉCISION d'un mécanisme (prédiction, scoring, playbook — « faut-il caster X ?
quel dégât PRÉDIT ? quelle cible ? ») ne garantit EN RIEN qu'il est reproduit côté EXÉCUTION (le runner
qui APPLIQUE l'action choisie et mute l'état).** Ce sont **deux chemins distincts, à registres distincts** :
`engine/playbook` + `engine/services` (prédiction/décision) vs `engine/runner` + `AbilityHandler.
ABILITY_CLASSES` + `operations/*` (exécution combat). Confirmer l'un NE couvre PAS l'autre.

- **Le runner combat NO-OP SILENCIEUSEMENT toute ability non enregistrée** : `AbilityHandler.
  visit_ActiveAbilityMessage` fait `ported:False ; return` (0 dégât, 0 effet, AUCUNE erreur) pour tout
  `ActiveAbilityType` absent de `ABILITY_CLASSES` (~11 abilities enregistrées). La divergence d'état qui
  s'ensuit est INVISIBLE → attribuée à tort au bruit RNG ou à un autre mécanisme. **Faute déjà commise** :
  SpiritLeech (1104) lourdement travaillé côté DÉCISION (#84/#86/#90 : lifesteal-util, snowball, prédiction
  Attack-based) mais JAMAIS exécuté en combat — no-op muet non détecté jusqu'à #93.
- **Doctrine** :
  1. **Jamais conclure « X est porté/géré » sans préciser QUEL côté** (décision vs exécution) est couvert.
     Si un seul côté est fait, **TÂCHER l'autre** (port-gap → `TaskCreate`).
  2. **Rendre le no-op combat VISIBLE** (flag `AbilityHandler.unported` qui accumule les casts tombés sur
     no-op) et l'**ASSERTER** dans tout test d'exécution d'ability (`assert last["ported"] is True`) — un
     cast qui tombe sur no-op doit **ÉCHOUER LOUD**, pas passer en silence.
  3. Un replay-diff / self-play qui « colle » **sans forcer l'exécution** du mécanisme ne prouve RIEN sur
     l'exécution : la décision peut choisir X pendant que le runner l'ignore.
- **Pourquoi** : la fidélité « le moteur reproduit le jeu » a DEUX faces — **décider** comme l'IA native +
  **exécuter** comme le moteur natif. Valider une seule face en croyant couvrir les deux = un angle mort
  SILENCIEUX qui corrompt le dataset RL / le replay sans le moindre signal (pas d'erreur, pas de test rouge).

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

