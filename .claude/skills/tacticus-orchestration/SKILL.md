---
name: tacticus-orchestration
description: "Conduite de campagne tacticus-tools par l'ORCHESTRATEUR : exploitation de la plateforme live (demarrage, inject, restart du host, boot ghidra-mcp), pipeline de dispatch des solveurs et workflow de livraison par PR, et procedure complete de migration au changement de build du jeu. Charge a la demande — le CLAUDE.md ne garde que ce dont un AGENT a besoin pour porter."
---

# Orchestration tacticus-tools

Ce skill porte ce que **seul l'orchestrateur** deroule. Il a ete sorti du `CLAUDE.md` le
2026-07-25 : ce dernier est charge par CHAQUE sous-agent, et 65 % de son volume ne servait
qu'a la conduite de campagne — un cout paye a chaque lancement d'agent, pour rien.

Ce qui reste dans le `CLAUDE.md` (donc vu par tous les agents) : protocole RE + portage,
gate de confrontabilite, DSL-vs-imperatif, regle de citation par symbole, discipline runner,
tests cibles, ASCII, `Ne jamais`, et les invariants d'agents (worktree, reinject).
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
4. **Warmup — RIEN À FAIRE : l'inject de l'étape 3 l'enchaîne tout seul** (depuis le
   2026-07-31). Session déjà vivante mais froide → `POST /api/admin/warmup`.
   Le RPC sous-jacent reste `warmupGameSingletons({ force: true })`, mais ne l'appelle
   pas à la main après un inject : tu le jouerais deux fois.
   **Autonome** : pilote toute la nav UI lui-même (campagne → node → play → capture
   ctor), capture `lastSource` + `lastUnitProgression` + `IdunUniverse`, push
   `builder_ready` au front, **puis REVIENT SUR LA CAMPAGNE**. **Aucun clic humain :
   ne JAMAIS demander à l'utilisateur de cliquer une battle ni de ramener la campagne**
   — le cycle sait aussi sortir seul d'un écran de bataille hérité (`recover-from-battle`).
   Mesuré le 2026-07-31 : inject + warmup = **14,1 s**, warmup seul = **11,9 s**.
   `{ warmup: false }` sur l'inject, ou `stopAfterCapture: true` sur le RPC, sont des
   échappatoires explicites — pas des défauts.

   > **Pourquoi ce n'est plus « le jeu reste en bataille ».** Le 2026-07-25 la sortie
   > anticipée était devenue le défaut sur `cycle complet 61,2 s / ok:false` contre
   > `sortie 3,9 s / ok:true`, d'où la conclusion « la transition bataille → campagne
   > wedge ». **Réfutée** le 2026-07-30 (`97ebf7ac`) : les mêmes clics rejoués à la main,
   > espacés de ~2 s, ramènent la campagne en moins de 5 s. La cause était un clic
   > **AVALÉ** — `interactable == true` précède la fin de l'animation du popup, et le clic
   > émis dans cette fenêtre est perdu **en rapportant `ok:true`**. Parade généralisée aux
   > deux bras le 2026-07-31 (#332) : chaque clic est validé par son EFFET et rejoué s'il
   > manque. **Règle générale : ne jamais conclure du retour d'un clic qu'il a porté.**
5. Builder front : tout est armé. On peut générer la `BattleConfiguration` de
   n'importe quelle node (events inactifs inclus) sans relancer une battle.

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

## Fenêtre de harnais par le mode DRAIN — la voie SÛRE pour (ré)injecter

**Un reinject / restart de host n'est plus un geste proscrit : il est CONDITIONNÉ.** Le
`CLAUDE.md` continue de l'interdire *aux agents* — c'est l'orchestrateur qui conduit la
fenêtre, et lui seul. Procédure **exécutée et validée le 2026-07-31**, 4 agents en vol :

1. **Armer** : `POST /api/admin/drain` `{enabled: true, retryAfterSec: 120, message: "…"}`.
   Refuse les **CRÉATIONS** de runner (503 + `Retry-After`) sur les 5 points d'entrée
   (`initAndStart`, `buildPatchedRunner`, `initRunner`, `loadFromSavedBundle`,
   `simBuildPreview`) — **sans toucher aux runners en place**, qui vivent leur vie.
2. **Prévenir les agents en validation live** par `SendMessage`. Sans ce message ils bouclent
   sur des retries et retardent la fenêtre. Leur dire, dans cet ordre : **commiter d'abord**
   (un worktree PROPRE est auto-supprimé à la pause, et la reprise repart dans l'arbre
   principal), **disposer leurs runners**, puis **ATTENDRE la réouverture** — pas s'arrêter.
   ⚠ **Dire « attends », jamais « arrête-toi »** : un agent qui rend la main coûte une reprise
   et risque la perte de worktree, pour une fenêtre qui dure des minutes. Ne demander un
   rapport d'état que si la fenêtre s'annonce longue. Et toujours : **ne RIEN conclure d'un
   refus** — un 503 n'est ni un « porteur non confrontable » ni un « régime inatteignable ».
   ⚠ **Une fenêtre longue coûte donc plus qu'elle n'en a l'air** : tout agent en vol y est
   suspendu. Regrouper les besoins de reinject plutôt que d'ouvrir une fenêtre par correctif.
3. **Attendre `liveRunners == 0`** sur `GET /api/admin/drain`, en boucle de veille.
   ⚠ Cette jauge interroge le **registre des HOOKS**, pas le cache du host — lequel dérive :
   **mesuré 786 côté host contre 1 côté hooks**. Une veille bâtie sur `/api/runners` ne
   tomberait jamais à zéro. Tri-état : `null` = **PAS mesuré** (session morte, RPC en échec),
   jamais à lire comme un zéro.
4. **Débusquer l'orphelin** s'il ne converge pas. `listRunners` donne un `owner` (souvent un
   state-file `logs/_pytest_duel_state-<PID>-N.json`) : le PID est-il **mort** ? Purger par ce
   recoupement propriétaire ↔ processus, **jamais par l'âge** — l'âge condamnerait aussi un
   runner légitimement long. Mesuré : un orphelin d'une passe de validation *de
   l'orchestrateur* a bloqué une fenêtre à lui seul.
5. **Agir** : `npm run build:hooks` si `frida/hooks/*` a changé → restart host → inject
   (le warmup est enchaîné par l'inject — vérifier `warmupError: null` dans sa réponse).

   ⚠ **`npm run build:hooks` HANGE sur cette machine** (même cause que `npm run dev` : `frida-compile`
   n'est pas dans le PATH que npm expose ici). Passer par node :
   `node node_modules\frida-compile\dist\cli.js hooks/main.ts -o dist/hooks.js` depuis `frida/`
   (~10 s, rc 0). Vérifier le `LastWriteTime` de `dist/hooks.js` — c'est le seul témoin que le
   bundle est neuf.

   ⚠ **Si l'inject dépasse la minute, N'EN RELANCE PAS UN À L'IDENTIQUE — ISOLE L'ÉTAGE.**
   Mesuré le 2026-07-31 : le premier inject après une session vieille de 2 h a dépassé **300 s** et
   laissé `.session == null` ; un second, immédiat, avec `{"warmup": false}`, a rendu la main en
   **5,1 s** — puis `POST /api/admin/warmup` seul en **15,1 s**, 8 étapes vertes. Le harnais n'avait
   rien de cassé. `{"warmup": false}` sert exactement à ça : il sépare l'ATTACH du WARMUP, donc il
   dit LEQUEL a consommé le temps. Sans cette séparation on lit « le reinject wedge » et on va
   demander une relance du jeu (geste UTILISATEUR, coûteux) pour un incident qui se résout tout seul.
   ⚠ **Ne PAS conclure de ce timeout que le warmup est en cause** : rien ne l'établit — un attach qui
   hange bloque avant lui. Écrire « étage non isolé » plutôt que désigner un coupable.
6. **Lever le drain**, puis **reprendre les agents par `SendMessage`** (contexte intact),
   en leur donnant l'état du harnais (session, warmup, drain levé, hash de build).

⚠ Le drain vit **en mémoire du host** : un restart le remet à `false` de lui-même.
⚠ **Vérifier le hash de build après toute relance du jeu** : installé ==
`data/symbols/CURRENT` == `python scripts/python/ghidra_symbols.py build`. Une relance peut
être une mise à jour déguisée, et l'analyse offline deviendrait fausse en silence.

## Restart du host (pour Claude)

Quand tu modifies du code dans `frida/host/` (router, config-store, sessions,
admin, …) le host doit être redémarré — `npm run dev` lance `tsx host/index.ts`
**sans watch**. Procédure :

1. Shutdown graceful : `curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown`
2. Relance en background : `cd frida && npm run dev > /tmp/host.log 2>&1 &`
   ⚠ **Sur cette machine les deux voies évidentes échouent** : le tool Bash rend
   `exp: command not found`, et `npm run dev` rend `'tsx' n'est pas reconnu` (npm n'ajoute pas
   `node_modules/.bin` au PATH ici). La commande qui marche, via le tool **PowerShell** :
   `Set-Location C:\Users\nicolasv\tacticus-tools\frida; node node_modules\tsx\dist\cli.mjs host/index.ts`
   ⚠ L'auto-restore ne réinjecte pas toujours : si `/api/admin/status` rend `.session == null`
   après le restart, injecter explicitement par `POST /api/admin/inject` body `{}`.
3. Vérification : `curl -s http://127.0.0.1:8765/api/health` doit retourner
   `{"status":"ok"}` après ~3 s.

**Important** : le restart du host **réinjecte** l'agent Frida via auto-restore
(load fresh `dist/hooks.js` dans le PID Tacticus). L'état mémoire du précédent
agent est perdu — donc :
- `lastSource` (CampaignGameModeSource), `lastUnitProgression`, `lastUniverse`
  redeviennent `null`
- Les RPCs `buildCampaignConfig` / `dumpCampaignCatalog` / etc. répondent
  "no live CampaignGameModeSource captured" jusqu'à re-warmup
- **Ré-armer = `POST /api/admin/warmup`** (l'auto-restore du restart host réinjecte
  mais NE warme PAS — seul `POST /api/admin/inject` enchaîne le warmup). Autonome :
  pilote la nav UI seul et rend la main sur la campagne. **Ne jamais demander à
  l'utilisateur de cliquer une battle ni de ramener la campagne.**
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
pwsh -File C:\Users\nicolasv\ghidra-mcp\start-ghidra-mcp.ps1   # build courant = cat data/symbols/CURRENT
# autre build : ... start-ghidra-mcp.ps1 -Project <chemin\gameassembly.gpr>
```

> **Les projets Ghidra vivent HORS du dépôt** depuis le 2026-07-26 :
> `C:\Users\nicolasv\ghidra-projects\ghidra_<HASH>\gameassembly.gpr`. Ils pesaient
> 14,1 Go dans `data/` (96 % du répertoire) alors qu'ils sont entièrement
> régénérables — les garder dedans rendait `data/` inmanipulable.

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
  `gameassembly.lock` / `.lock~` dans `C:\Users\nicolasv\ghidra-projects\ghidra_<HASH>\`.
  Si **aucun** process
  java/pyghidra ne tourne, ces locks sont périmés → les supprimer avant de relancer.

## Au changement de build du jeu — PROCÉDURE

Le `<HASH>` du dossier change à chaque mise à jour. **Tant que cette procédure n'est pas
passée, toute analyse offline est fausse** (adresses 100 % périmées) et les artefacts
estampillés refusent de servir — c'est voulu, ils échouent FORT plutôt que de mentir.

**Un répertoire par build, une famille par producteur** — l'arborescence dit d'où vient
chaque table (le mot « dump » est surchargé, la structure lève l'ambiguïté) :

```
data/symbols/<HASH>/
  BUILD                          le hash, en clair
  frida/{methods,classes,enums}.tsv    produit par preprocess_il2cpp_dump.py
  ghidra/functions.tsv                 EXTRAIT de Ghidra par ghidra_symbols.py dump
```

| famille | produit par | consommé par | son diff dit |
|---|---|---|---|
| `frida/methods.tsv` | `preprocess` (depuis le dump Frida) | **Ghidra** (nommage) | signatures — mais la RVA est en colonne 1, donc **toutes** les lignes changent : diff bruité |
| `frida/classes.tsv` | idem | **Ghidra** (structs) | **taille, parent, offsets de champs** — aucune adresse, **diff propre** |
| `frida/enums.tsv` | idem | lecture humaine | **valeurs d'enum** — aucune adresse, **diff propre** |
| `ghidra/functions.tsv` | `ghidra_symbols.py dump` | **nos outils offline** (`whereis`, migrateur, probes) | apparitions / disparitions / renommages |

**Les deux tables qui comptent pour détecter une casse silencieuse sont `classes` et `enums`** :
la doctrine conserve les offsets RELATIFS (`+0xa8`, slots de vtable) et les identifiants
d'effet en dur — si une MAJ redispose une struct ou renumérote un enum, **seul leur diff le
montre**. La table plate `functions.tsv`, elle, ne voit qu'un nom qui bouge.

**Aucune ne nourrit Frida.** Frida est la SOURCE de la chaîne (le one-shot lit les métadonnées
du runtime IL2CPP), et les hooks live, eux, résolvent leurs cibles au runtime via `findMethod`
— jamais depuis un fichier. `ghidra/functions.tsv` n'est pas une redite de `frida/methods.tsv` :
**Ghidra apporte les frontières de fonctions**, que Frida n'a pas (il ne connaît que les points
d'entrée). C'est ce qui permet de situer une adresse À L'INTÉRIEUR d'une fonction et donc
d'écrire `<symbole>+0x<offset>`.

`GhidraApplyIl2CppSymbols.java` **sélectionne lui-même** son build : il parcourt
`data/symbols/*/frida/` et retient celui dont l'estampille porte le sha256 du binaire chargé.
Il ne peut donc plus appliquer les symboles d'un autre build — soit il trouve, soit il refuse.

### Partage de vérité Frida / Ghidra — aucun ne remplace l'autre

**Frida fait autorité sur les MÉTADONNÉES** : dispositions de classes, offsets de champs,
valeurs d'enum, signatures. Il lit la table de métadonnées du runtime IL2CPP.

**Ghidra fait autorité sur le CODE** : frontières de fonctions, instructions, références
croisées, graphe d'appels. Frida ne les voit pas — il ne désassemble rien.

Le sens de la dépendance va peut-être à l'inverse de l'intuition :

> **Ghidra ne connaît les structures que parce qu'on les lui injecte.** Le binaire IL2CPP est
> strippé — l'analyse automatique de Ghidra ne peut pas retrouver la disposition d'un type C#.
> C'est `GhidraApplyIl2CppSymbols` qui lit `frida/classes.tsv` et **fabrique** les structs dans
> la base. Une structure fausse dans le TSV devient une structure fausse dans tout le décompilé.

C'est pourquoi une MAJ oblige à refaire **toute** la chaîne, pas un maillon : regénérer le
dump Frida sans réappliquer dans Ghidra laisse un décompilé qui ment sur les types ; et
l'inverse (rejouer Ghidra sur de vieux TSV) est exactement l'incident du 2026-07-25.

**Ordre de lecture après une mise à jour**, du moins cher au plus cher :

1. diff `frida/classes.tsv` + `frida/enums.tsv` → **CE QUI** a changé dans le contrat de données ;
2. diff `ghidra/functions.tsv` → **QUELLES FONCTIONS** ont disparu, apparu, été renommées ;
3. décompilé via `mcp__ghidra__*` → **COMMENT**.

Seule la 3ᵉ étape coûte ; les deux premières servent à la cibler. Attaquer directement par le
décompilé, c'est relire un binaire de 60 Mo sans savoir quoi y chercher.

### Le projet Ghidra a DEUX consommateurs, pas un

Les frontières de fonctions ne servent pas qu'à produire `ghidra/functions.tsv` : c'est **le
même modèle** que les agents interrogent en direct via `mcp__ghidra__*` (`decompile_function`,
`list_xrefs`, `gen_callgraph`, `search_symbols_by_name`). Le `.gpr` n'est pas un détail
d'outillage, **c'est la surface de RE entière**.

**Conséquence à ne pas rater après une MAJ** : si le serveur `ghidra-mcp` sert encore l'ANCIEN
projet pendant que la table versionnée est celle du NOUVEAU build, un agent **décompile un
binaire et cite les symboles d'un autre** — et rien ne proteste. Les deux réponses sont
plausibles séparément, incohérentes ensemble. C'est la version silencieuse de l'incident du
2026-07-25, transposée aux agents.

**Le contrôle**, à passer après tout redémarrage du serveur ou changement de build :

```bash
python scripts/python/ghidra_symbols.py build   # hash RÉELLEMENT chargé par ghidra-mcp
cat data/symbols/CURRENT                        # hash des tables versionnées
```

Les deux doivent coïncider. Sinon : relancer `start-ghidra-mcp.ps1 -Project <nouveau.gpr>`
**avant** de lancer le moindre agent RE — un agent lancé sur un serveur périmé produit du
travail à jeter, sans le savoir.

**Étape 0 — constater.** Comparer le hash installé au hash des artefacts :

```bash
ls -d /c/Users/nicolasv/AppData/Local/tacticus/games/*/   # hash installé
cat data/symbols/CURRENT                                  # hash des symboles
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
l'analyse finir, puis appliquer les noms via `scripts/ghidra/GhidraApplyIl2CppSymbols.java`.
Ce script **vérifie l'estampille avant toute écriture** et s'arrête si elle ne correspond pas
au binaire chargé. Les trois se font en **un seul appel headless** :

```powershell
$env:JAVA_HOME='C:\Program Files\Eclipse Adoptium\jdk-21.0.9.10-hotspot'
$env:GHIDRA_INSTALL_DIR='C:\Users\nicolasv\ghidra_12.0.4_PUBLIC'
& 'C:\Users\nicolasv\ghidra_12.0.4_PUBLIC\support\analyzeHeadless.bat' `
  'C:\Users\nicolasv\ghidra-projects\ghidra_<HASH>' gameassembly `
  -import 'C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\GameAssembly.dll' `
  -postScript GhidraApplyIl2CppSymbols.java `
  -scriptPath 'C:\Users\nicolasv\tacticus-tools\scripts\ghidra' -max-cpu <N>
```

> **⏱ Compter ~1 heure, PAS « quelques minutes ».** Mesuré le 2026-07-29 sur
> `rnca9r7q6c` (57 Mo, 124 719 méthodes), 19 cœurs : **54 min 52 s** de bout en bout,
> dont seulement **452 s d'auto-analyse** et **18 s de symbolisation** — c'est
> l'**import** qui domine. Le lancer en tâche de fond et faire autre chose.
> Pic mémoire **11,9 Go** contre `MAXMEM=16G` dans `analyzeHeadless.bat` : la marge
> n'est pas énorme, vérifier ce réglage si un build plus gros OOM.
> Ne pas confondre avec le « ~2 min » cité plus haut : celui-là est le **boot de
> pyghidra-mcp sur un projet DÉJÀ analysé**, pas l'analyse (mesuré 2 min 11 s le 2026-07-29).

**RE-SYMBOLISER SANS RÉIMPORTER — la branche à 2 minutes.** Si seul le *nommage* change
(correctif de l'applier, convention revue) et que le projet est déjà analysé, il ne faut
**surtout pas** rejouer l'import : `-process` + `-noanalysis` réapplique les noms sur place.

```powershell
& 'C:\Users\nicolasv\ghidra_12.0.4_PUBLIC\support\analyzeHeadless.bat' `
  'C:\Users\nicolasv\ghidra-projects\ghidra_<HASH>' gameassembly `
  -process 'GameAssembly.dll' -noanalysis `
  -postScript GhidraApplyIl2CppSymbols.java `
  -scriptPath 'C:\Users\nicolasv\tacticus-tools\scripts\ghidra' -max-cpu <N>
```

Mesuré le 2026-07-29 : **1 min 52 s** (dont 45 s de symbolisation), `named=124719`, `skipped=0`,
`created=0` — les fonctions existent déjà, seuls leurs noms bougent. À comparer aux 54 min 52 s
d'un projet neuf. **Arrêter ghidra-mcp d'abord** (il tient le verrou du `.gpr`) et supprimer les
`gameassembly.lock*` périmés, sinon l'appel échoue. Le re-dump de l'étape 3, lui, reste à payer
en entier.

Puis démarrer le serveur sur le nouveau projet :

```bash
pwsh -File C:\Users\nicolasv\ghidra-mcp\start-ghidra-mcp.ps1 -Project <chemin\nouveau.gpr>
```

⚠ **Le lanceur Tacticus SUPPRIME le dossier de l'ancien build** dès la mise à jour : son
`GameAssembly.dll` n'est plus re-dumpable, et son projet Ghidra devient la **seule** trace
de son code. Ne jamais nettoyer un projet dont le DLL a disparu — cf.
`C:\Users\nicolasv\ghidra-projects\NE-PAS-SUPPRIMER.md`.

**Étape 3 — EXTRAIRE la table DE Ghidra, et la COMMITER.** Rien n'est relu du jeu ici : on
sort de Ghidra ce qu'on vient d'y faire entrer, enrichi des frontières de fonctions.

```bash
python scripts/python/ghidra_symbols.py dump   # -> data/symbols/<NOUVEAU_HASH>/functions.tsv
git add data/symbols/<NOUVEAU_HASH>
```

**Compter ~1 h 15** — deux mesures du 2026-07-29 sur le même build (154 176 symboles) :
**1 h 10 min 26 s** et **1 h 18 min 14 s**, soit ~34 symboles/s. C'est **plus long que l'analyse
Ghidra elle-même** (54 min 52 s à l'étape 2), ce qui est contre-intuitif et faisait sous-estimer
la migration entière. Le coût est dans les **allers-retours HTTP paginés** vers ghidra-mcp, pas
dans un calcul.

> **Deux pièges de mesure, vécus le même jour.**
> 1. La progression avance **par paliers avec des pauses** : une fenêtre de 5-6 s à delta nul ne
>    prouve RIEN (conclu « terminé » à tort **deux fois**). Attendre la **sortie du process
>    client**, jamais un `mtime` stable.
> 2. **Ne pas jauger l'avancement sur la taille du dump PRÉCÉDENT** — la cible n'est pas la même
>    (ici 10,09 Mo contre 9,80, le format `$$` étant plus verbeux). Même erreur commise deux fois
>    dans la journée, dans les deux sens.
>
> Pendant le dump, ghidra-mcp est **saturé** : `symbols_sync.py` le rapporte « ÉTEINT » alors que
> le port écoute — c'est de la contention, pas une mort. Les appels `mcp__ghidra__*` tombent aussi
> (`transport dropped mid-call`) : ne pas lancer d'agent RE pendant un dump.
>
> **Le serveur doit être lancé DÉTACHÉ** (`Start-Process`). Lancé comme enfant d'une tâche de
> fond, un `TaskStop` sur cette tâche **tue le serveur avec l'arbre de processus** — et le dump
> qui suit échoue en 3 s sur `WinError 10061`.

**Son diff EST le rapport de changement du jeu** : ce qui apparaît, disparaît ou se
renomme entre deux builds est exactement ce que la mise à jour a touché. Ne pas le
commiter, c'est perdre le seul moyen de savoir ce qui a bougé.

> **⚠ LE DIFF BRUT EST ININTERPRÉTABLE SI LA FORME DES SYMBOLES A CHANGÉ.** Toujours **vérifier
> la forme avant de lire un diff** — `grep -c '\$\$'` sur les deux tables — et normaliser si elle
> diffère. **La forme canonique est `Namespace.Classe$$Membre`**, chevrons échappés en
> `u003C`/`u003E` ; `GhidraApplyIl2CppSymbols.canonicalName` la produit et c'est ce que citent
> les 4 230 références du dépôt.
>
> **L'incident qui a établi cette règle (2026-07-29).** Le premier dump du nouveau build est sorti
> en `Classe.Methode` avec `<` littéral — **0 ligne en `$$` sur 154 176**. Comparés tels quels,
> les deux builds n'avaient que **485 symboles en commun (0,43 %)** : la signature d'un jeu
> entièrement réécrit. En réalité un simple séparateur — après correction, **81,9 %** des
> citations résolvent et le changement réel se réduit à **229 symboles**.
>
> **La cause n'était pas la MAJ du jeu, mais un CHANGEMENT D'OUTILLAGE.** Le `$$` est la
> convention d'**Il2CppDumper v39**, portée par `GhidraApplyIl2CppNamesWin.java` (lisait
> `data/win_dump/script.json`, recopiait `Name` verbatim). Ce script a été supprimé le 2026-07-25
> (`8e591496`, « suppression du legacy ») au profit de la chaîne Frida — mais le projet Ghidra
> alors en place était **déjà symbolisé** par le legacy, et sa table a été versionnée telle quelle
> le même jour (`4c82b367`). Il a fallu une **re-symbolisation complète** pour révéler l'écart.
>
> **La leçon générale** : remplacer un maillon de la chaîne sans re-jouer tout l'aval laisse
> l'ancienne sortie faire foi jusqu'à la prochaine régénération — qui peut arriver des mois plus
> tard. Aucune garde ne l'attrape : les trois axes de `symbols_sync.py` vérifient la PROVENANCE,
> jamais la FORME (tâche #255).

> **UN RÉPERTOIRE PAR BUILD, ET ON LES GARDE TOUS.** `data/symbols/CURRENT` (une ligne, un
> hash) désigne celui qui **fait foi** ; les autres sont des **archives**, conservées exprès —
> leur diff doit rester consultable bien après la fenêtre de migration.
>
> Jusqu'au 2026-07-29 la garde `symbols_sync.py` **échouait** dès qu'il y avait deux
> répertoires (« lequel fait foi ? ») et ne proposait que d'**effacer** l'ancien — on jetait
> donc la référence pour satisfaire un outil. La multiplicité n'était qu'un **proxy**
> d'ambiguïté : le vrai contrôle, « la table correspond-elle au sha256 du binaire installé ? »,
> la garde le faisait déjà. Le pointeur le rend **exact**, et la multiplicité cesse de gêner.
>
> Résolution centralisée dans `scripts/python/symbols_layout.py` (`current_build()`,
> `build_dir()`, `archived_builds()`). Un `CURRENT` qui désigne un répertoire absent est une
> **erreur dure** — jamais de repli silencieux sur « le seul autre ».
>
> `GhidraApplyIl2CppSymbols.java` n'utilise **pas** ce pointeur, et c'est voulu : il
> discrimine par le **sha256 du binaire qu'il a chargé**, ce qui est strictement plus sûr que
> de suivre un pointeur.

**Étape 4 — reprendre les citations.** Le code cite des **symboles**, pas des adresses :
~97,5 % traversent la mise à jour sans rien faire. Les survivantes ne sont pas le sujet —
**les disparues le sont**, et ce sont précisément les fonctions que la MAJ a changées :

```bash
python scripts/python/probe_va_citation_shapes.py scripts/python/engine   # taux de résolution
```

Une citation qui ne résout plus = une mécanique à re-RE, pas un simple renommage.

**Étape 5 — ARCHIVER le gameconfig, PUIS comparer.** Les symboles disent ce que le CODE a
changé, pas ce que les DONNÉES ont changé. Le gameconfig est téléchargé au runtime dans
`AppData/LocalLow/Snowprint/<produit>/gameconfig/<hash>.json`.

> **⛔ Le premier geste est de le COPIER dans le dépôt, AVANT toute autre chose :**
>
> ```powershell
> Copy-Item '<AppData>\...\gameconfig\<hash>.json' 'data\symbols\<BUILD>\gameconfig.json'
> git add data/symbols/<BUILD>/gameconfig.json
> ```
>
> Il va dans le **répertoire du build**, à côté de `BUILD`, `frida/` et `ghidra/` : un build =
> un répertoire, tout ce qui le décrit au même endroit.
>
> **Une croyance fausse a coûté la ligne de base du 2026-07-29** : cette procédure affirmait
> qu'il y avait « une copie par version, qui s'accumulent », et que cette accumulation servait
> d'historique. **Faux, mesuré** — le lanceur ÉCRASE. Il n'existe qu'**UN SEUL** gameconfig
> complet sur disque à un instant donné (les dizaines d'autres `.json` du dossier font 0 Mo :
> des configs partielles, écartées par `_is_full_config`). Résultat : le gameconfig de
> `gqfc5mff6c` a disparu sans jamais avoir été versionné, et on ne saura **jamais** ce que
> cette mise à jour a changé dans les données — alors qu'on sait précisément ce qu'elle a
> changé dans le code.
>
> ⚠ `scripts/python/gameconfig.py` lit le fichier **VIVANT**, pas la copie versionnée : dès
> que le jeu se met à jour, le port consomme les nouvelles données **silencieusement**. La
> copie dans `data/gameconfig/` est l'**archive** qui rend le diff possible, pas le chemin de
> lecture.

Celui qui fait foi pour le build courant est **le plus récemment écrit**.

```bash
python scripts/python/gameconfig.py --which              # quel instantané est lu (+ hash)
python scripts/python/gameconfig_diff.py --list          # instantanés disponibles
python scripts/python/gameconfig_diff.py <A.json> <B.json> [--section units]
```

`gameconfig_diff.py` aplatit chaque config en `chemin -> valeur feuille` et range les écarts
selon le critère de #105 : **chemin ajouté/retiré ou valeur non numérique = mécanique**,
**valeur numérique changée = rééquilibrage**.

**Pas encore outillé, à faire à la main** : la garde automatique qui refuse les artefacts
désynchronisés en amont de chaque probe.

**Étape 6 — REPOSER les prefs d'écran (la MAJ les écrase).** Mesuré le 2026-07-29 : la mise à
jour a remis `Screenmanager Resolution Width/Height` à **2560×1920** (4,9 Mpx). Symptôme :
`dwm` à **51 %** de GPU pour afficher un écran de bataille statique — le compositeur travaille
à la fréquence de l'ÉCRAN, pas aux 30 Hz du jeu, donc **le bridage de cadence ne corrige
rien** ; seule la surface compte. Retomber à 1280×960 a ramené le GPU à **6,8 %**.

```powershell
# jeu FERMÉ (le script refuse sinon : Unity réécrit les prefs en quittant)
powershell -File scripts\tacticus-screen-prefs.ps1
```

Le levier à chaud, pour une session déjà lancée, est le RPC `renderBudget` — **enveloppe
`args` (un TABLEAU), pas `params`** : un `params` est ignoré en silence et l'appel se comporte
en lecture seule (`applied: []`).

```powershell
$b = '{"method":"renderBudget","args":[{"width":1280,"height":960,"fullScreenMode":3}]}'
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/scripts/<SID>/rpc" -Method Post -Body $b -ContentType 'application/json'
```

⚠ `fullScreenMode` est un **ENUM**, pas un booléen (`0` = `ExclusiveFullScreen`, `3` =
`Windowed`) — la confusion a déjà coûté le process. Passer **3** quand le jeu est déjà en
fenêtre : aucun changement de mode, donc aucun `SetFullscreenState`, donc aucun contact avec
le swapchain. Et le retour ne dit RIEN d'un échec (`applied:["resolution"]` même quand rien
n'a pris) : **vérifier en RELISANT** `renderBudget` sans argument une frame plus tard —
`SetResolution` est asynchrone, `after` est encore l'ancienne valeur dans l'appel qui l'écrit.

La cadence, elle, n'a rien à faire ici : `render-budget.ts` l'**auto-arme** à 30 Hz /
`vSync = 0` à chaque inject (vérifiable par `autoArm.done`).

## Suivre un agent — LIRE À FROID, ne JAMAIS le réveiller pour un état

**Un `SendMessage` REJOUE tout le contexte de l'agent** — pour un solveur mature, **300 à 600 K
tokens**. Ne jamais payer ça pour une information d'avancement : elle se lit à froid, pour zéro.

**Signaux gratuits, dans cet ordre :**

| ce qu'on veut savoir | comment, sans toucher l'agent |
|---|---|
| dernière activité | `LastWriteTime` de `~/.claude/projects/<projet>/<session>/subagents/agent-<agentId>.jsonl` — LE transcript, appendu à chaque tour d'outil. ⚠ `Get-Item` **seulement** : ne JAMAIS lire ce fichier (700 Ko à 1,4 Mo), il ferait déborder le contexte. |
| ce qu'il a écrit | `git -C <worktree> status --porcelain` et `git -C <worktree> log --oneline origin/master..HEAD` |
| empreinte live | `listRunners` côté host — montre ses runners sans l'éveiller |
| en cours vs arrêté | `LastWriteTime` du même `.jsonl` comparé à maintenant. **PAS** l'absence de notification — un agent vivant n'en émet aucune. |

> ⛔ **`<session>/tasks/<agentId>.output` — celui que l'outil `Agent` rapporte comme `output_file` —
> fait `0 octet` pour TOUS les agents, vivants comme morts, et son `LastWriteTime` vaut l'heure de
> LANCEMENT.** Il ne mesure ni l'activité, ni la survie du contexte. **Mesuré le 2026-07-31 sur
> 9 agents : 0 Ko × 9**, pendant que les `subagents/*.jsonl` faisaient 92 Ko à 1,4 Mo.
>
> Cette ligne du skill disait le contraire, et l'avoir crue a coûté : quatre agents tombés sur
> erreur API ont été relancés **à neuf** alors que leur transcript était intact (`SendMessage` les
> aurait repris) ; un cinquième, **qui travaillait**, a été déclaré mort — d'où un doublon lancé sur
> sa tâche et un `git commit` intrusif dans son worktree. Un agent qui tombe sur erreur API
> **garde son transcript** : la reprise à vide décrite plus bas ne vaut que pour un exit brutal du
> parent, et se vérifie sur la TAILLE du `.jsonl`, jamais sur ce fichier-ci.

- **Un `SendMessage` ne se justifie que pour CHANGER ce que l'agent fait** : demande de rebase,
  correction de cap, consigne neuve, préavis de reinject. **Jamais** pour un rapport d'état.
- **« Silencieux » ≠ « n'a pas reçu ».** Un message est mis en file et délivré **au prochain tour
  d'outil**. Un agent dans une longue opération (suite de tests live, décompilation) ne le voit pas
  avant d'en sortir — **ne pas ré-envoyer**, ça n'accélère rien et double le coût.
- **Un agent en veille ne bloque pas une fenêtre de reinject** : il ne tient aucune mesure live, et
  le reinject tue les runners de toute façon. Ne pas attendre sa réponse — et ne pas l'arrêter non
  plus, son travail serait irrécupérable. Il découvrira au réveil qu'il doit reconstruire.

*(Faute commise le 2026-07-30 : agent réveillé après 62 min de silence pour savoir s'il était
bloqué — alors que sa réponse ne changeait rien à la décision.)*

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

- **Worktree RUNNABLE par son SEUL checkout — plus aucune étape 0 (2026-07-26).** `data/`
  est VERSIONNÉ et ne porte que des ENTRÉES : `symbols/`, `boards/`, `seed-bc.json`,
  `i2_en.json` (~47 Mo bruts, ~1,1 Mo compressés). Un agent les tient donc de SON commit,
  et **travaille DANS son worktree** (éditer + exécuter). Ne PLUS instruire « travaille dans
  l'arbre principal » : cette vieille béquille faisait partager le working copy →
  l'orchestrateur devait GELER ses éditions `engine/**` pendant les runs.

  La **junction `data/` (tâche #63) est SUPPRIMÉE**, et avec elle trois défauts qu'elle
  portait : la table de symboles d'un agent n'était pas celle de SON commit (le script
  effaçait le `data/symbols` que git venait de matérialiser) ; les N agents écrivaient dans
  le MÊME répertoire, d'où la discipline « nom unique par agent » — et 355 state-files
  retrouvés le 2026-07-26 qui avaient **survécu** aux worktrees les ayant produits ; et un
  `worktree remove --force` sur la junction pouvait détruire le `data/` partagé (vécu le
  2026-07-22).

  **Les sorties vont dans `logs/`** (gitignoré), à la racine du worktree qui les produit :
  elles **meurent avec lui**. Rien de produit par un run ne doit atterrir dans `data/` —
  s'il y atterrit, il apparaît dans `git status`, et c'est ce qui rend la règle
  auto-vérifiable. Disciplines runner encore valables : disposer SES runners, MAX_RUNNERS,
  session Frida globale via RPC. Le script `setup-agent-worktree.ps1` ne crée plus rien :
  il VÉRIFIE qu'un checkout est runnable et signale une junction héritée.

- **⚠ LA LEÇON DE LA JUNCTION N'AVAIT PAS ÉTÉ GÉNÉRALISÉE — elle a resservi le 2026-07-31.**
  Supprimer la junction `data/` a fermé UN chemin, pas la CLASSE. Les agents en ont recréé
  ailleurs, pour la même raison de fond : un worktree frais ne pouvait pas **compiler le
  bundle**. Résultat mesuré — `frida/hooks/scratch` (67 modules gitignorés, jamais versionnés,
  aucune copie nulle part) **détruit dans l'arbre principal**, `frida/node_modules` amputé, le
  bundle devenu inconstructible. Sous Windows, `git worktree remove --force` **suit le point de
  reparse et vide la cible** ; un agent qui « nettoie sa junction avant de rendre la main » n'y
  change rien, la destruction a lieu APRÈS son départ.

  **La cause n'est jamais la junction, c'est ce qui la rend nécessaire** : une entrée de build
  gitignorée. `frida/hooks/scratch/` est donc VERSIONNÉ depuis le 2026-07-31, et le cliquet
  `probe_365_versioned_imports_gitignored.py` rougit si un fichier versionné importe
  statiquement une cible gitignorée ou absente — c'est lui qui empêche la classe de revenir.
  L'interdiction de junction est posée dans les invariants agents du `CLAUDE.md`.

  **Suppression d'un worktree — ne jamais laisser `--force` traverser un lien.** Énumérer les
  points de reparse et supprimer les LIENS d'abord, puis retirer le worktree :

  ```powershell
  $wt = ".claude/worktrees/agent-<id>"
  Get-ChildItem $wt -Recurse -Force -Attributes ReparsePoint -ErrorAction SilentlyContinue |
      ForEach-Object { cmd /c rmdir "`"$($_.FullName)`"" }   # supprime le LIEN, pas la cible
  git worktree remove $wt --force
  ```

  Un `worktree remove` qui échoue en **`Invalid argument`** est la signature d'un point de
  reparse : ne pas réessayer en boucle — enlever le lien d'abord.

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
    dépasser **MAX_RUNNERS**, **disposer MES runners** jamais ceux des autres).
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
  `~/.claude/projects/<projet>/<session>/subagents/agent-<agentId>.jsonl` : prompt + tours assistant
  + `tool_use`/`tool_result`) puis y ajoute mon message. C'est le VRAI équivalent de `--resume`.
  ⚠ **Pas** `tasks/<agentId>.output`, qui est vide pour tout le monde (encadré plus haut).
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

## Scinder un module — le seuil porte sur le CODE, docstrings EXCLUES

**C'est MA décision, pas celle d'un agent** : un solveur travaille sur sa tranche et n'a aucune vue
d'ensemble pour arbitrer une scission. Si une scission est nécessaire, elle part comme **tâche
dédiée**, jamais en effet de bord d'un port.

**Seuil : ~1000 lignes de CODE NET** — hors docstrings, commentaires, lignes vides. Ne jamais
annoncer une dette de taille sur un `wc -l`. Ne pas pré-scinder : un module de 350 lignes va bien.

- **Pourquoi le net et pas le brut** : ce code est issu de RE, et la docstring porte le lien vers le
  natif — symbole, mesure, hypothèse réfutée — sans lequel le mirror n'est plus vérifiable sur place.
  Mesuré le 2026-08-01 : `engine/**` = 348 modules, **37,5 % de code / 50,0 % de prose**. Un seuil en
  lignes brutes y désigne **21** modules, celui sur le code **0**. Le plus gros,
  `engine/runner/components.py`, fait 1939 lignes pour **704 de code** ;
  `engine/entities/effects/base.py` en fait 1013 pour **154** — le scinder donnerait deux fichiers de
  ~77 lignes de code, tous deux encore majoritairement de la prose. Sur tout le Python versionné :
  30 fichiers au seuil brut contre **4** au seuil net.
  ⚠ Le piège est SYMÉTRIQUE : `engine/entities/effect_type.py`, quasi sans prose, était invisible au
  seuil brut alors qu'il portait le plus de code net du moteur.
- **Comment mesurer** : classer les lignes en code / docstring / commentaire / vide — `ast` pour les
  docstrings, `tokenize` pour les commentaires (un `#` dans une chaîne n'est PAS un commentaire).
- **NE PAS faire déporter ces docstrings vers `docs/rl`** pour raccourcir : le récit d'enquête y est
  déjà (**214 des 348** modules d'`engine/` pointent dehors, **325** citent un symbole natif, **191**
  portent une mesure). Ce qui reste est l'irréductible, et la règle « on cite un SYMBOLE » existe
  précisément pour que le grep code ↔ `data/symbols/<build>/functions.tsv` soit immédiat.
- **Convention** : `feature.py` → `feature/__init__.py` + sous-modules ; l'entrée reste au chemin
  d'origine pour ne pas casser les importeurs. Les coutures suivent les **namespaces natifs** — le
  nombre de symboles `X$$Y` distincts par module (médiane 11, max 187) les révèle.
  ⚠ Piste ÉCARTÉE : faire du compte de symboles un second seuil. Il corrèle à **r = 0,76** avec les
  lignes de code, donc il duplique le signal ; ses désaccords s'expliquent (un mirror fidèle d'une
  grosse classe native est court et riche en symboles — `active_ability.py`, 153 symboles pour 351
  lignes de code — et le scinder casserait le 1:1).
- **Chiffres à re-dériver, pas à citer.** Seul candidat réel au 2026-08-01 :
  `scripts/python/rl_duel.py`, **1679 lignes de code**. Les 3 autres au-dessus de 1000 sont une table
  (`enum_maps.py`, 2 % de prose), un générateur et un pilote de batch — monolithiques par nature.
- **Non mesuré** : le même ratio côté TypeScript (`frida/**`) — 10 fichiers > 1000 lignes brutes, part
  de prose inconnue. `router.ts` (1833) et `sim-engine.ts` (1594) sont PLAUSIBLES, pas établis, et ils
  sont sous fenêtre (hooks = rebuild+reinject, host = restart).

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
  L'ordre exact du merge et la place de la banque : « La boucle de MERGE » ci-dessous.
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


## La boucle de MERGE — la banque tourne HORS du chemin critique

**Ordre, et il ne se réorganise pas :** rapport → `gh pr view --json headRefName` → fraîcheur
(`merge-base --is-ancestor`) → `git merge --no-ff --no-commit` → **lire le diff des tests EXISTANTS
modifiés** + **classer le diff `engine/`** → 3 à 5 groupes ciblés joués **par moi** → régénérer les
docs générés **et l'attestation `probe_462`** → **commit LOCAL** → `ratchets-bg` en arrière-plan →
lire la PR suivante → **push seulement sur VERT** → `git worktree remove` (après scan des points de
reparse).

```
merge --no-ff LOCAL  ->  pwsh -File scripts/ratchets-bg.ps1 -Since <base>   (arriere-plan)
                                          |
                      vert  -> push -> merge suivant       rouge -> fix-forward, PUIS push
```

- **Ne pousser que du VERT.** Les worktrees d'agents partent d'`origin/master` : un rouge poussé
  démarre cassé tout agent dispatché ensuite. Les merges s'empilent **localement** dans l'ordre ;
  on pousse dans l'ordre des VERDICTS, pas des merges.
- **Le verdict se lit avant le prochain dispatch**, jamais après.
- `ratchets-bg.ps1` épingle un COMMIT dans un **worktree persistant** (`%TEMP%`, verrou exclusif,
  repli jetable si pris). Il juge donc un commit, **jamais le working tree** — un correctif non
  commité lui est invisible, et il le DIT.
- **Trois issues, à ne pas confondre** : `0` vert · `n` = n cliquets rouges · `64` (usage) et `99`
  (montage) = **aucun verdict sur le dépôt**, jamais à lire comme un rouge (#457-r7).

### Ne pas PAYER DEUX FOIS — reproche « t'es trop lent à merger » (2026-08-03)

La lenteur ne venait pas du nombre de gardes : je **rejouais à la main** le jeu de non-régression que
l'agent avait déjà joué et rapporté, en dormant par tranches de 2 min.

- ⛔ **Ne pas rejouer les tests live que la PR touche.** Régénérer l'attestation
  (`probe_462_live_tests_status.py --run --since origin/master`) les **REJOUE** — c'est ça, la mesure
  indépendante, pas un enregistrement de la parole de l'agent. Les 3 à 5 groupes ciblés de l'ordre
  ci-dessus portent sur le **diff `engine/` classé**, pas sur le jeu déjà rendu par l'auteur.
- **Régénérer le ledger AVANT de lancer la banque**, jamais après — une passe a rougi pour cette
  seule raison de séquence. Puis `git add scripts/ratchets-462-live-attestations.json`.
- ⚠ **Grouper plusieurs PR sur une seule tête est un REPLI, pas la règle** — ça fait perdre
  l'ATTRIBUTION, et `ratchets-bg` existe précisément pour ne pas avoir à choisir entre vitesse et
  attribution (il épingle le commit, l'arbre principal passe à la PR suivante). Ne grouper que si le
  fond est indisponible.
- **Lancer, passer à la suite, lire le verdict quand il tombe.** Pas de veille en boucle serrée : le
  fichier `logs/ratchets-bg/<court>-<horodatage>.txt` attend, lui.
- ⛔ **`probe_457 --measure` n'a RIEN à faire dans la boucle de merge** — c'est de la maintenance
  (« à rejouer quand le mur dérive », dit sa propre aide). Mesuré le 2026-08-04 : **12 min bloquantes**
  (719,7 s / 1462 tests), payées **deux fois** dans la même boucle. Les DEUX artefacts se dégradent
  **du côté sûr**, et le code le dit (`probe_457_offline_tests_green.py`, commentaires de
  `_footprints_path` et `_weights_path`) : une **empreinte** périmée « sélectionne TROP — et retombe
  continûment sur le rejeu total » ; des **poids** périmés « coûtent du MUR, jamais un faux vert,
  jamais un trou ». Aucun des deux ne peut produire un faux vert, et ce coût tombe **dans la banque,
  qui tourne en fond** — donc zéro sur le chemin critique. Le lancer, c'est convertir un coût
  invisible en blocage.
  Seule chose qui force la main aujourd'hui : la **garde d'ÉQUILIBRAGE**, qui rougit dès qu'un
  fichier de test offline neuf n'a pas de poids — une garde d'OPTIMISATION calibrée comme un
  invariant de correction, et qui ne peut PAS rougir chez un agent (worktree frais → repli md5).
  C'est la tâche **#463** ; tant qu'elle n'est pas corrigée, la sortie est de pousser en connaissant
  ce rouge-là, pas de payer 12 min.
- **Ce qui reste manuel et non négociable** : la relecture du **diff d'un test EXISTANT que la PR
  MODIFIE**. Aucune garde ne voit un test adapté pour passer.

**Coût mesuré le 2026-08-03** (à re-dériver, jamais à citer) : complet ~240 s ; avec `-Since` sur
une PR de documentation **141 s** ; worktree neuf +34 s contre persistant. La sélection dérive d'une
**empreinte MESURÉE** (`scripts/ratchets-457-footprints.json`, versionnée, auto-invalidée par son
`_commit`) + du graphe d'imports ; tout doute rejoue TOUT et l'écrit.

⚠ **`-Since` ne remplace pas un run complet** : un complet **une fois par session**, et après tout
`--measure`. Si tu veux t'en passer, le geste juste n'est pas la confiance mais **régénérer
l'empreinte** — c'est elle qui porte la vérité.

⚠ **La banque n'est PAS le filet principal, et le croire fait relâcher la relecture.** Mesuré sur
nos merges depuis le 2026-07-25 : 21 « banque VERTE » contre 6 rouges, dont **3 contre-épreuves
délibérées**, **2 rouges réels mais PRÉ-EXISTANTS** (trouvés en AJOUTANT un cliquet, pas en
rejouant les existants) et **UN SEUL** causé par le changement en validation. Ce qui attrape, c'est
la relecture du diff et les groupes ciblés ; la banque couvre le tail risk — d'où sa place en fond.

## Gabarit de BRIEF — les clauses non négociables

Ce gabarit n'existait qu'implicitement (dans la tête de l'orchestrateur), et il dérivait d'un lot
à l'autre. Il est posé ici, versionné. Chaque clause vient d'un défaut **mesuré**, pas d'une
préférence de style.

1. **Le CRITÈRE de décision d'abord** — une question BINAIRE, avant toute méthode. L'agent doit
   pouvoir dire « oui » ou « non », et savoir ce qui tranche (décompilé, pas expérience live).
2. **Séparer VÉRIFIÉ et HÉRITÉ, dans la phrase.** Ce que l'orchestrateur a constaté lui-même dans
   la session (avec `fichier:ligne`) vs ce qu'il recopie d'un autre agent ou d'une fiche. Le second
   se marque **« hérité, à re-confronter »**.
   *Pourquoi* : mesuré le 2026-07-27 — **10 briefs sur 11 portaient une prémisse matériellement
   fausse**, presque toutes recopiées d'un inventaire écrit à un instant donné. L'orchestrateur est
   le vecteur de transmission ; c'est sur lui que la clause pèse, pas sur l'agent.
3. **Démentir explicitement une fiche fausse** quand on l'a constaté (« ne cherche pas ce bug, il
   n'existe pas », avec la ligne réelle en regard). Vécu sur N1 : la fiche allègue une tautologie
   `own_fac == own_fac` qui n'est pas dans le code.
4. **Déclarer le TERRITOIRE des agents en vol**, fichier par fichier, et ce qui est LIBRE.
   *Pourquoi* : c'est la sérialisation en amont qui tient — 13 PR mergées pour **un seul** conflit
   (une ligne de doc).
5. **Le montage livré en FIXTURE NOMMÉE ET RÉUTILISABLE**, jamais inline. Le montage (roster,
   positions drivées, board, seed) est l'unité de valeur réelle, pas le test ; re-crafté à chaque
   fois, il se perd. Coût marginal nul au moment où l'agent l'écrit, zéro rétro-travail.
6. **Une garde vue ROUGE avant le fix, par MUTATION adversariale** — casser son propre mécanisme et
   vérifier que la garde tombe. Message rouge rapporté **verbatim**. Une garde qu'on n'a jamais vue
   rougir ne prouve rien.
7. **Mesure, pas argument** : avant/après chiffrés. Et un lot où les deux hypothèses donnent le même
   résultat ne conclut RIEN — le dire et refaire le montage.
8. **La PR qui ferme un résidu MET À JOUR SA LIGNE D'INVENTAIRE** (`docs/rl/port-residuals-inventory.md`),
   dans le même commit.
   *Pourquoi* : mesuré le 2026-07-28 — les PR #151 et #152 ont chacune fermé une entrée **nominative**
   de l'inventaire sans y toucher. Un document corrigé uniquement par ses passes de re-confrontation
   **ment structurellement entre deux passes**, et c'est précisément ce mensonge qui alimente la
   clause 2. Trente secondes contre une prémisse fausse dans le brief suivant.
9. **Rebase sur `origin/master` AVANT d'ouvrir la PR, puis RE-JEU des tests** par l'auteur. La
   divergence, c'est la durée de vie de l'agent (2-3 h), pas la latence de merge.
10. **Discipline de fin** : écrire tôt (un worktree propre est auto-supprimé à la pause et l'agent
    repart dans l'arbre principal sans le savoir) ; ne jamais injecter ni redémarrer le host ; ASCII
    strict en sortie console ; citer les symboles Ghidra, jamais une VA absolue.

**Côté orchestrateur, après un merge** : la tranche à rejouer est celle qui **OBSERVE** le
comportement changé, pas celle que l'auteur cite. (Vécu : #138 mergée sur un rouge — le test qui
encodait l'ancien comportement était dans une autre tranche.)

## Références chargées avec ce skill

<!-- Conventions des hooks : ne sert QUE si on edite frida/hooks/* — pas au portage Python. -->
!include .claude/skills/tacticus/references/hooks.md

<!-- Techniques de resolution de cas durs, ecrites EXCLUSIVEMENT par fable-solver.
     Leur raison d'etre est que l'ORCHESTRATEUR tente de resoudre seul avant de deleguer :
     c'est donc ici qu'elles vivent, pas dans le contexte de chaque agent. -->
!include docs/rl/solving-playbook.md