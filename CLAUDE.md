# tacticus-tools

Hooking Frida de **WH40K Tacticus** (Windows PC build, Unity 6 IL2CPP) — monorepo TypeScript.

## Structure

- Racine : `C:\Users\nicolasv\tacticus-tools`
- `frida/` — codebase active (hooks TS + host TS, bundlé par `frida-compile`)
  - `frida/hooks/` — script injecté dans Tacticus
  - `frida/host/` — serveur Node qui pilote les sessions Frida (Express + WS)
  - `frida/public/` — frontend browser (statique, servi sur `/view/`)
  - `frida/dist/` — outputs build (gitignored)
- `scripts/frida/` — scripts Frida one-shot **vivants**, hors bundle (notamment
  `dump-il2cpp-full.js`, qui produit toute la chaîne de symboles).
- `hooks-legacy/` — hooks et probes **historiques** (versionnés, consultables). Rien
  de vivant ne doit en dépendre. Voir `hooks-legacy/README.md`.
- `data/` — dumps IL2CPP, gameconfig, boards — gitignored, **à une exception près** :
  `data/symbols/<HASH>/` (la table de symboles) est VERSIONNÉE.
- `sources_win/` — décompilation Ghidra de `GameAssembly.dll` — gitignored
- `STATUS.md` — état d'avancement vivant du projet

## Cible Windows

- **Exe** : `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\Tacticus.exe`
- **GameAssembly.dll** : ~60 MB, IL2CPP AOT (Unity 6000.3.8f1)
- **Pas d'`adb`, pas de device, pas de `frida-server`** : injection locale via `frida.getLocalDevice()`

### Hash du build = identité du dump

Tacticus stocke chaque build dans `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\`
où `<HASH>` (ex. `nb3o9lmt6c`, `uu2fr8mv6c`, …) **change à chaque mise à jour**
du jeu. Toutes les RVAs IL2CPP, le dump `data/il2cpp_full.json` et ses TSV,
la table `data/symbols/<HASH>/` et les décompilations Ghidra (`sources_win/`) sont
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

### Règle d'écriture : on cite un SYMBOLE, jamais une adresse

**Toute référence à du code natif — commentaire, docstring, message de test, doc —
s'écrit avec le symbole Ghidra VERBATIM, jamais avec une VA.**

```
IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage      ✅
`CalculateDirectDamage @18102f130`                                    ❌
```

- **Point interne** à une fonction : `<symbole>+0x<offset>`.
- **Échappement conservé tel quel** (`u003C` = `<`, `u003E` = `>`) : c'est ce qui rend le
  grep code ↔ table immédiat.
- **Les offsets RELATIFS restent** : champs de struct (`+0xa8`), slots de vtable, RVA
  calculées en code depuis l'image base. Seules les **VA absolues** sont proscrites.

**Pourquoi** : churn inter-build **mesuré** (build de mai → `gqfc5mff6c`) — les noms sont
stables à **97,5 %**, les adresses changent à **100 %**. Une citation par adresse est donc
fausse dès la mise à jour suivante, **silencieusement** : on ne l'apprend qu'en lisant du
décompilé qui ne correspond à rien. Le symbole, lui, survit et se re-résout d'un grep.

**Comment résoudre** une adresse trouvée dans Ghidra :

```bash
python scripts/python/ghidra_symbols.py whereis <VA>     # -> <symbole>+0x<offset>
```

ou, 100 % offline (ghidra-mcp éteint), un grep dans `data/symbols/<build>/functions.tsv`
(format `<adresse>\t<symbole>`). Migration d'un lot existant :
`scripts/python/migrate_va_to_symbol.py` (token-aware — il ne réécrit QUE dans les
commentaires et chaînes, jamais un littéral exécutable) ; `probe_va_in_code_vs_prose.py`
est le garde-fou à passer avant.

**Reste en VA, et c'est voulu** : les adresses qui ne résolvent que sur un placeholder
`FUN_<addr>` (le « symbole » n'y est que l'adresse déguisée) et les thunks de la table
d'imports. Les lister plutôt que les maquiller.

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
   capture ctor) et capture `lastSource` + `lastUnitProgression` + `IdunUniverse`,
   push `builder_ready` au front (refresh catalog). **Aucun clic humain ; Claude ne
   demande JAMAIS à l'utilisateur de cliquer une battle in-game.**
   **Le cycle s'ARRÊTE à la capture** (`stopAfterCapture`, défaut depuis le
   2026-07-25) : le jeu reste sur l'écran de bataille, et c'est normal. Le ménage
   d'écran qui suivait (pause → retreat → retour campagne) était du confort pur et
   **la seule source de wedge** — 61,2 s / `ok:false` contre 3,9 s / `ok:true`.
   (Détails : section « Workflow RL ».)
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
   (campagne → node → play → capture ctor) et force l'init des singletons/classes.
   Claude l'appelle directement après chaque (re)inject et NE demande JAMAIS de cliquer une battle.
   Le cycle **s'arrête à la capture** et laisse le jeu sur l'écran de bataille (`stopAfterCapture`,
   défaut) : c'est l'état ATTENDU, pas un warmup incomplet. Les runners isolés ne consomment
   pas l'écran campagne. Pour l'écran rendu propre malgré le risque de wedge :
   `warmupGameSingletons({ force: true, stopAfterCapture: false })`.

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

### QUAND (ne pas) ré-injecter — RÈGLE STRICTE

**Un changement Python `scripts/python/engine/**` (la réimplémentation OFFLINE : runner,
oracle, prédiction, playbook, tests moteur) N'EXIGE JAMAIS de reinject ni de rebuild `hooks.js`.**

- **Pourquoi** : ce code tourne dans le process **pytest / probe** et parle au runner live
  **par RPC** ; il **ne s'exécute PAS dans Frida**. Seul le script injecté `frida/hooks/*`
  (bundlé en `dist/hooks.js`) tourne dans le jeu. Donc :
  - modif `frida/hooks/*` → `npm run build:hooks` **puis** reinject (`POST /api/admin/inject`) ;
  - modif `frida/host/*` → restart host (qui auto-réinjecte) ;
  - modif Python `engine/**` (ou n'importe quoi hors `frida/`) → **RIEN** : on réutilise la
    session Frida existante telle quelle, on relance juste les tests/probes.
- **Un reinject est DESTRUCTEUR** : il stoppe la session courante et perd son état warm
  (singletons init, `lastSource`, runners en vol). Ne jamais le déclencher « par réflexe ».

**AVANT tout `POST /api/admin/inject` : vérifier qu'aucune session vivante n'existe DÉJÀ, en
lisant le BON champ du status.** `/api/admin/status` renvoie **`.session` (SINGULIER)**, pas
`.sessions` (pluriel — n'existe pas) :

```bash
curl -s http://127.0.0.1:8765/api/admin/status | npx -y node-jq -c '.session'
# -> {"id":N,"pid":...,"status":"running",...}  => session VIVANTE : la RÉUTILISER, NE PAS injecter
# -> null                                         => pas de session : injecter puis warmup
```

- **Piège vécu (2026-07-18)** : un filtre jq erroné sur `.sessions` (pluriel) a renvoyé `[]`
  → conclusion « aucune session » → reinject inutile qui a tué une session warm vivante. **Ne
  JAMAIS déduire « pas de session » d'un champ absent/mal nommé** : lire `.session` (singulier)
  et tester `.session.status == "running"`. Si `running`, il n'y a **rien à injecter** (sauf
  changement `frida/hooks/*` explicite).
- Rappel warmup : après un inject RÉELLEMENT nécessaire (hooks changés / aucune session), warmup
  obligatoire. En pytest, le fixture `live_session` s'en charge (warmup-if-needed au 1er test) —
  pas besoin d'un warmup manuel.

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

## Au changement de build du jeu — PROCÉDURE

Le `<HASH>` du dossier change à chaque mise à jour. **Tant que cette procédure n'est pas
passée, toute analyse offline est fausse** (adresses 100 % périmées) et les artefacts
estampillés refusent de servir — c'est voulu, ils échouent FORT plutôt que de mentir.

**Étape 0 — constater.** Comparer le hash installé au hash des artefacts :

```bash
ls -d /c/Users/nicolasv/AppData/Local/tacticus/games/*/   # hash installé
cat data/symbols/*/BUILD                                  # hash des symboles
```

**Étape 1 — re-dumper depuis le jeu qui tourne** (jeu lancé, menu principal ; le
lancement du jeu est un geste UTILISATEUR) :

```bash
python scripts/python/dump_il2cpp.py --pid <pid>   # -> data/il2cpp_full.json
python scripts/python/preprocess_il2cpp_dump.py    # -> data/il2cpp_{methods,classes,enums}.tsv
```

**PAS de warmup** pour cette étape : le one-shot lit les métadonnées IL2CPP, pas les
singletons de jeu. Le dump (~40 Mo en un `send`) fait tomber la session Frida — c'est
normal et sans danger depuis la neutralisation du détecteur de gel.
`preprocess` estampille chaque TSV (`#!il2cpp-provenance`, pivot = **sha256 du
GameAssembly.dll installé**) et **refuse d'écrire** s'il ne peut pas l'établir.

**Étape 2 — Ghidra** : importer le nouveau `GameAssembly.dll` dans un projet neuf, laisser
l'analyse finir (~2 min), puis appliquer les noms via `scripts/ghidra/GhidraApplyIl2CppSymbols.java`.
Ce script **vérifie l'estampille avant toute écriture** et s'arrête si elle ne correspond pas
au binaire chargé. Démarrer le serveur sur le nouveau projet :

```bash
pwsh -File C:\Users\nicolasv\ghidra-mcp\start-ghidra-mcp.ps1 -Project <chemin\nouveau.gpr>
```

**Étape 3 — extraire la table, et la COMMITER** :

```bash
python scripts/python/ghidra_symbols.py dump   # -> data/symbols/<NOUVEAU_HASH>/functions.tsv
git add data/symbols/<NOUVEAU_HASH>
```

`data/symbols/` est la **seule** exception versionnée de `data/` (cf. `.gitignore`).
**Son diff EST le rapport de changement du jeu** : ce qui apparaît, disparaît ou se
renomme entre deux builds est exactement ce que la mise à jour a touché. Ne pas le
commiter, c'est perdre le seul moyen de savoir ce qui a bougé.

**Étape 4 — reprendre les citations.** Le code cite des **symboles**, pas des adresses :
~97,5 % traversent la mise à jour sans rien faire. Les survivantes ne sont pas le sujet —
**les disparues le sont**, et ce sont précisément les fonctions que la MAJ a changées :

```bash
python scripts/python/probe_va_citation_shapes.py scripts/python/engine   # taux de résolution
```

Une citation qui ne résout plus = une mécanique à re-RE, pas un simple renommage.

**Pas encore outillé, à faire à la main** : le diff `gameconfig` inter-build (séparer un
rééquilibrage de valeurs d'un changement de mécanique) et la garde automatique qui refuse
les artefacts désynchronisés en amont de chaque probe.

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

- **NE JAMAIS passer `model:` à l'invocation de l'outil `Agent`.** Les agents du projet
  (`opus-solver`, `re-expert`, `validator`, `standby-executor`) sont épinglés sur **`opus[1m]`**
  dans leur frontmatter — Opus 5 **avec fenêtre 1M**. Or l'ordre de résolution du modèle est
  *env `CLAUDE_CODE_SUBAGENT_MODEL` > paramètre d'invocation > frontmatter > modèle de session* :
  passer `model: "opus"` à l'appel **écrase** le frontmatter et **retombe sur la fenêtre 200 K**
  (l'enum du paramètre d'invocation ne connaît que les alias nus `sonnet|opus|haiku|fable` — il
  **ne sait pas exprimer** le suffixe `[1m]`). Omettre le champ = les agents gardent leur 1M.
  `fable-solver` reste sur **`fable`** (levier de diversité de modèle pour les cas durs) et
  `live-ops` sur **`haiku`** (procédures mécaniques).

- **Pourquoi** : sans `isolation`, l'agent partage MON working directory et peut
  éditer les mêmes fichiers que moi. Un agent qui monkeypatche le code (même
  « temporairement » pour reproduire un cas) corrompt alors mon arbre — déjà subi :
  un validateur a laissé `return /float(...)` dans `engine/utilities/tile.py`
  → `SyntaxError` cassant tout l'import `engine`. Avec `isolation: "worktree"`,
  l'agent bosse dans SON checkout jetable (`.claude/worktrees/agent-<id>/`, branche
  `worktree-agent-<id>`, auto-nettoyé si inchangé) → ses edits/monkeypatches ne
  touchent JAMAIS mon arbre. L'isolation par défaut prime sur son coût (~200-500 ms
  + disque). (`isolation: "remote"` = variante cloud, toujours en background.)

- **Worktree RUNNABLE : junction `data/` OBLIGATOIRE (tâche #63, 2026-07-22).** Un worktree
  frais n'a PAS les `data/` gitignorés (dumps gameconfig/i2, seeds BC, boards, state-files,
  ai-traces) dont dépendent `gameconfig.py`, `rl_duel.py`, le harness stages et les probes.
  **Étape 1 de TOUT agent tacticus : créer la junction** —
  `powershell -File C:\Users\nicolasv\tacticus-tools\scripts\setup-agent-worktree.ps1`
  (depuis son worktree ; équivalent Git Bash :
  `cmd //c "mklink /J data C:\Users\nicolasv\tacticus-tools\data"`) — **puis travailler DANS
  son worktree** (éditer + exécuter). Ne PLUS instruire « travaille dans l'arbre principal » :
  cette ancienne béquille faisait partager le working copy → l'orchestrateur devait GELER ses
  éditions `engine/**` pendant les runs des agents, et leurs validations zéro-régression
  devenaient polluables. Avec la junction, l'isolation redevient réelle : l'orchestrateur édite
  `master` librement pendant que les agents tournent (leurs imports viennent de LEUR checkout
  figé). `data/` reste PHYSIQUEMENT PARTAGÉ → disciplines runner inchangées (state-file à NOM
  UNIQUE par agent en chemin absolu, disposer SES runners, MAX_RUNNERS=10, session Frida
  globale via RPC). Vérifié : junction sans droits admin, `git status` du worktree ignore
  `data` (gitignore), suppression du worktree n'affecte pas la cible (rmdir = lien seul).

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

## Solveurs autonomes : `opus-solver` par DÉFAUT, `fable-solver` en dernier recours

**RÈGLE : on dispatche EXCLUSIVEMENT sur `opus-solver`.** `fable-solver` n'est **jamais** un premier
choix — il est réservé aux cas qu'**opus a réellement tenté et n'a pas résolus**. Un tag `[fable]`
posé au moment de proposer une tâche est une *estimation de difficulté*, **pas** une affectation :
même `[fable]`, la tâche part d'abord en `opus-solver`, avec l'échappatoire explicite dans son prompt
(« si ça résiste — divergence non localisée, verdicts contradictoires, aller-retours — ne t'acharne
pas, signale-le comme candidat à délégation »).

- **Pourquoi** : sur les vagues récentes, l'écrasante majorité des cas tagués `[fable]` ont été
  résolus par opus — plusieurs en retournant carrément leur prémisse (le débloqueur REVIVE #66,
  résolu opus-first sans fable, en est l'exemple). Réserver fable à ce qui a *effectivement* résisté
  évite de payer le modèle le plus lourd pour du travail qu'opus fait, et garde le
  `solving-playbook` centré sur les vrais cas durs.
- **Escalade** : un cas ne devient `fable` que sur un **rapport d'échec d'opus** (le solveur dit
  lui-même qu'il bloque), jamais sur une intuition a priori de difficulté.

Le workflow de livraison est **identique pour les deux** (worktree isolé, édition libre, validation
adversariale de son PROPRE fix, livraison **PAR PULL REQUEST**) :

- Il commit son fix + son entrée `docs/rl/solving-playbook.md` sur sa branche worktree, `git push
  origin HEAD` + `gh pr create`, et reporte l'URL. **Filet** : si le push/gh échoue (creds/env), il
  laisse tout committé sur sa branche → **je pousse + ouvre la PR à sa place**.
- **Moi** : je RELIS la PR + RE-VALIDE (checkout branche, tests CIBLÉS de la tranche) + **merge**.
  Le merge sur `master` reste MON geste, **sur ton accord** — jamais l'agent. Après merge :
  je supprime la branche (`git push origin --delete <branche>` + `git worktree prune`).
- **`docs/rl/solving-playbook.md` = base des techniques de résolution de cas durs, écrite
  EXCLUSIVEMENT par `fable-solver`** (une entrée par cas). Je ne l'édite JAMAIS. Son contenu est
  **`!include` dans ce CLAUDE.md** (section « Documentation détaillée ») → chargé en contexte chaque
  session : je tente de résoudre un cas dur SEUL avec ces techniques AVANT de déléguer. But : à terme,
  de moins en moins besoin de l'agent.
- **`opus-solver`** (`.claude/agents/opus-solver.md`, modèle `opus[1m]`) — **le dispatch par défaut,
  quel que soit le tag** : artefact identifié, volume mécanique, port 1:1, câblage… et aussi les cas
  `[fable]` en PREMIÈRE tentative. Il n'écrit **jamais** `solving-playbook.md` (fable-solver only) ;
  un item qui se révèle DUR est reporté comme **candidat fable-solver**, pas résolu à l'usure.
- **`fable-solver`** (`.claude/agents/fable-solver.md`, modèle `fable`) — **uniquement après un échec
  opus RAPPORTÉ**. Son modèle distinct est aussi un levier de *diversité* : sur un cas où opus a
  tourné en rond, changer de famille de modèle vaut mieux que relancer le même.

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
- **Commit** : `data/` (SAUF `data/symbols/`, qui est versionnée EXPRÈS),
  `frida/dist/`, `server/`, `logs/`, `frida/assets/raw/`, `sources_win/`.
  (`hooks-legacy/` EST versionné — l'ancienne mention ici était fausse.)

## Protocole RE + portage (DÉCISION + COMBAT)

Le protocole complet — recon du kit, RE fidèle (décompilé = vérité, jamais l'expérience live),
mirror 1:1 des fonctions natives nommées, décomposition par étage (jamais fitter un scalaire),
validation des DEUX faces (décider ≠ exécuter) — vit dans le skill `tacticus-re-port`
(invocable via `/tacticus-re-port`), inclus ci-dessous. C'est LA source unique de cette doctrine.

### Gate de confrontabilité : HERO / MoW / SUMMON — jamais NPC

Avant de porter une mécanique (ou d'exiger un datapoint live), établir **qui la porte** et si ce
porteur est atteignable en bataille. Trois catégories seulement comptent, et les chemins de
vérification sont **distincts** :

- **HERO / MACHINE OF WAR** → présence **directe** dans `python scripts/python/rl_duel.py --list-pool`
  (rank courant). C'est **la seule porte valable** — surtout pas `kind == lineup` de gameconfig,
  qui ment.
- **SUMMON** → compte **aussi**, **même absent de `--list-pool`**. On l'amène en bataille en spawnant
  son **summoner** (qui, lui, doit être dans le pool) : le summon apparaît dans l'équipe du summoner
  et agit dès son apparition. **Ne jamais conclure « non confrontable » d'un carrier summon.**
- **NPC** → hors-jeu, jamais confrontable. Un item dont **tous** les porteurs sont npc n'est pas
  « bloqué », il est **NON PERTINENT** : ne pas y brûler d'agent (sauf demande explicite de mirror +
  toggle offline).

**Pourquoi** : les deux erreurs symétriques ont déjà coûté. Compter les npc comme spawnables envoie un
solver valider une branche impossible ; inversement, ranger un carrier **summon** en « non confrontable »
rabat à tort un port validable-live sur du mirror-offline (vécu le 2026-07-25 sur TwoManTeam/Diminutive,
corrigé en cours de route). Toujours **ventiler les porteurs hero / mow / summon / npc** et dire par
quel chemin chacun arrive en bataille.

### DSL-effet vs impératif : c'est l'ARTEFACT NATIF qui tranche (#149)

Avant de porter/migrer un behaviour, demander **« quel est l'artefact natif ? »** :

- Natif = `CreateBehaviour`/`ExecuteBehaviour`/`CreateTrigger`, sélecteur ou formule (un **arbre de nœuds
  `DSLFactory`**, kinds E/T/S/V) → **DOIT être un arbre DSL** ; jamais de logique (ciblage, re-trigger,
  exclusion de trait) recâblée à la main dans un `execute_*` — elle doit **émerger** des nœuds.
- Natif = `Operation.Execute` (mutateur ECS), `Effect.ApplyModification`/`ReverseModification`, pathfinding,
  scheduler, PRNG, pipeline Apply → **RESTE impératif** (mirror fidèle). Une **feuille DSL l'APPELLE**.

**La frontière = le `.Execute` d'une feuille DSL** : au-dessus (structure de l'arbre + sélecteurs/formules) =
déclaratif → DSL ; en-dessous (l'Operation) = impératif → Operation. **Piège** : un helper qui FUSIONNE le
behaviour (`AddEffect`) et le `ApplyModification` de l'effet (ex. `_apply_act_of_faith_stack`) — les SÉPARER
(feuille DSL au-dessus, Operation/effet impératif en-dessous), ne pas wrapper le mélange. Classification par
ability + roadmap des tranches restantes : **`docs/rl/dsl-effect-nodes.md`** (section « Classification »).

!include .claude/skills/tacticus-re-port/SKILL.md

## Documentation détaillée

!include .claude/skills/tacticus/references/hooks.md
!include .claude/skills/tacticus/references/rpc-api.md
!include .claude/skills/tacticus/references/runner.md

<!-- Techniques de résolution de cas durs, écrites EXCLUSIVEMENT par fable-solver (cf. section
     « Solveurs autonomes ») — incluses pour tenter de résoudre SEUL avant de déléguer. -->
!include docs/rl/solving-playbook.md

<!-- TODO références à (ré)écrire contre le code actuel (les drafts d'avril
     dans .claude/worktrees/agent-a0e45617/ sont périmés) : frida-host.md,
     game-architecture.md, decompilation.md, ai-engine-audit.md, knowledge.md.
     Ne pas !include tant qu'ils n'existent pas dans ce tree (résolution à vide). -->

