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
3. Cliquer **INJECT** dans l'UI (auto-discovery du PID via `_Data/` adjacent à l'exe).
4. **Warmup** = appeler le RPC `warmupGameSingletons({ force: true })`.
   **Autonome** : il pilote toute la nav UI lui-même (campagne → node → play →
   capture ctor → pause → retreat) et capture `lastSource` +
   `lastUnitProgression` + `IdunUniverse`, push `builder_ready` au front (refresh
   catalog). **Aucun clic humain ; Claude ne demande JAMAIS à l'utilisateur de
   cliquer une battle in-game.** (Détails : section « Workflow RL ».)
5. Builder front : tout est armé. On peut générer la `BattleConfiguration` de
   n'importe quelle node (events inactifs inclus) sans relancer une battle.

## Workflow RL — runner isolé avec config patchée

Pour entraîner un agent RL sans toucher au battle in-game, on utilise un
**runner isolé** construit depuis la `BattleConfiguration` capturée. Le runner
isole complètement le state — on peut le créer/détruire à volonté sans casser
le jeu actif.

**Procédure obligatoire dans cet ordre** :

1. **Warmup une fois** par session Frida (après chaque inject/reinject) :
   ```
   warmupGameSingletons({ force: true })
   ```
   **C'est AUTONOME — pas de clic humain.** Ce RPC pilote toute la nav UI
   lui-même : campagne (`IdunNavigation.ToCampaign`) → clic node → clic play →
   capture du ctor `CampaignGameModeSource` → attente déploiement stable →
   pause → retreat → confirm, et laisse le jeu revenu à l'écran campagne.
   **Claude doit l'appeler directement après chaque (re)inject et NE JAMAIS
   demander à l'utilisateur de cliquer une battle in-game.**

   > **RÈGLE INCONDITIONNELLE — warmup après CHAQUE (re)inject, AVANT tout
   > RPC/probe, SANS EXCEPTION.** Y compris les probes « self-contained » qui
   > montent un runner depuis une **seed BC sur disque** (ex.
   > `rl_probe_step.py --mode card|view|rank|predict`, `rl_collect_batch`) et
   > ne touchent pas `lastSource`. Raison : un (re)inject ne perd pas seulement
   > `lastSource._currentBattle` (→ `buildPatchedRunner`/`inspectBattleConfig`
   > échouent), il **repart aussi avec des caches `MethodInfo*` Frida-side vides
   > et la couche d'init IL2CPP non ré-amorcée** dont dépendent `initAndStart`/
   > `buildPatchedRunner`. Un probe qui « marche » sans warmup ne prouve rien :
   > c'est que le jeu était déjà warm d'une nav précédente (chance), pas de la
   > correction — au prochain build froid c'est le crash `0x2c` (metadata non
   > initialisée). **Ne jamais raisonner « ce mode-là n'a pas besoin de
   > warmup ».** Le warmup déclenche `CampaignGameModeSource.LoadBattle` (peuple
   > `_currentBattle`) ET force l'init des singletons/classes.

2. **Build runner isolé** (avec patch optionnel) :
   ```
   buildPatchedRunner({
     aiUnits: ["necroNpc1Warrior:6", ...], // 10 strings exactes
     randomizeAi: true,                     // optionnel
     templateOverrides: { ... },            // optionnel (HP/dmg sur player roster)
   })
   ```
   Retourne `{ runnerId, runner, seed, bcPtr, patch }`. Le patch s'applique
   in-place sur `lastSource._currentBattle`. **`Initialize()` du runner consume
   les `PredefinedUnits` patchées et auto-spawn les enemies** — pas besoin
   d'appeler `spawnPredefinedUnits` séparément.

3. **Observer l'état** :
   ```
   observeBattle({ runnerId })
   ```
   Renvoie `{ stage, byType, units: [{ entityId, visualId, hp, ... }] }`.
   À ce stade : `stage=Setup` (0), 10 units présentes côté AI.

4. **Itérer sans repasser par la game UI** : le `lastSource._currentBattle`
   reste valide tant que la session Frida n'est pas réinjectée. On peut
   re-patch + re-buildPatchedRunner autant qu'on veut. Chaque appel crée
   un nouveau `runnerId`.

**À NE PAS oublier** :
- Re-warmup après chaque `reinject` (la mémoire managée du wrapper survit
  mais les caches Frida-side perdent les MethodInfo*).
- `buildPatchedRunner` mute la BC source — clone si on veut comparer
  multiple variants.
- Les unit IDs AI sont au format `"unitId:level"` (ex. `"necroNpc1Warrior:6"`),
  pas juste `"necroNpc1Warrior"`.

## Build + Injection

```bash
cd frida && npm run build:hooks   # → frida/dist/hooks.js (~110 KB)
```

L'**injection se fait via l'UI** (`POST /api/admin/inject`) — pas en ligne de
commande. Le host gère device discovery, attach, load script, session lifecycle.

Pour info : (file:///C:/Users/nicolasv/tacticus-tools/frida/host/admin.ts) +
(file:///C:/Users/nicolasv/tacticus-tools/frida/public/src/admin.js).

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

<!-- TODO références à (ré)écrire contre le code actuel (les drafts d'avril
     dans .claude/worktrees/agent-a0e45617/ sont périmés) : frida-host.md,
     game-architecture.md, decompilation.md, ai-engine-audit.md, knowledge.md.
     Ne pas !include tant qu'ils n'existent pas dans ce tree (résolution à vide). -->

