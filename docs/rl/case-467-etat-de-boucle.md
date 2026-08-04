# #467 — L'état de la BOUCLE, dérivé et déclenché tout seul

**Critère binaire.** À la fin de chaque tour, l'orchestrateur voit-il, **sans avoir à y penser**,
qu'il lui reste des slots d'agent vides, des commits non poussés, des worktrees à nettoyer ou un
verdict de banque en attente ?

Avant ce cas : **non**. Mesuré le 2026-08-04 — un tour terminé à **1 agent sur un plafond de 5**
après que quatre solveurs avaient rendu, avec **30 commits d'avance non poussés** et **4 worktrees
livrés non nettoyés**. Rien ne l'a signalé ; l'utilisateur a dû demander « t'oublies rien ? ».

## 1. Pourquoi c'était structurel

Le dépôt portait **37 cliquets qui gardent le CODE, et zéro qui garde la BOUCLE**. La raison de
l'angle mort : **une erreur de code produit un ROUGE, une erreur de boucle ne produit RIEN**. Un
slot vide n'échoue pas — il coûte. C'est exactement la dégradation invisible contre laquelle les
cliquets existent, appliquée à l'étage au-dessus.

## 2. Ce qui est livré

| Fichier | Rôle |
|---|---|
| `scripts/python/loop_status.py` | l'état, **dérivé** : flotte / livraison / harnais / banque |
| `scripts/hooks/loop-status.ps1` | le déclencheur (wrapper du hook `Stop`) |
| `.claude/settings.json` | le câblage — hook **du projet**, donc versionné |
| `scripts/python/probe_467_loop_status_fidelity.py` | le cliquet de fidélité (banque) |
| `scripts/python/fleet_board.py` | `collect(only_alive=True)` + `transcripts()` |

**Rien n'est saisi.** Chaque chiffre vient d'une source nommée, et la source est imprimée à côté
en `--json`. La **seule** valeur assumée est `PLAFOND_DISPATCH = 5` : c'est un **paramètre**
d'orchestration, pas une mesure — surchargeable par `--max-agents` / `TACTICUS_DISPATCH_CAP`.

## 3. Les décisions, et la mesure qui les tranche

### 3.1 Le tri-état, repris de `host_inputs` (#273)

`None` = **pas mesuré**, jamais rendu comme un zéro. Le cas qui l'impose est `liveRunners` : c'est
le budget partagé des 4-en-parallèle, l'orchestrateur ne peut pas le deviner et l'a déjà calculé
de tête (2 fichiers rendus en `timed out`). Le host l'expose **déjà** en tri-état
(`GET /api/admin/drain`, `liveRunners: null` + `liveRunnersError`) — on le **propage** au lieu de
l'aplatir. Même règle pour `gh` : « 0 PR ouverte » et « je n'ai pas pu demander » sont deux états.

### 3.2 Le raccourci de flotte est une PREUVE, pas une heuristique

`fleet_board.collect()` relisait **870 transcripts, 1,23 Go — 54,8 s**. Inutilisable dans un hook.

`only_alive` pré-filtre par `mtime`, et c'est **exact** : le dernier horodatage *interne* d'un
transcript est écrit au moment où la ligne part sur disque, donc `last_ts <= mtime`. Si
`now - mtime >= SILENCE_MORT_MIN`, alors `silence >= SILENCE_MORT_MIN` : `est_vif` rendrait `False`
de toute façon. Écarter le fichier **ne peut pas** changer l'état « vif » d'un seul agent.

Mesure : **54,8 s → 0,17 s**. `os.scandir` plutôt que `glob` + `stat()` : sous Windows le mtime
vient de l'énumération du répertoire, le pré-filtre est donc quasi gratuit.

Le mode complet reste le défaut — lui seul voit l'état **`attente`** (agent en pause, worktree
conservé), qu'aucun mtime ne peut distinguer d'un agent fini.

### 3.3 Il se TAIT — et le critère de silence est dérivé

Un rappel qui parle à chaque tour d'un dépôt au repos se fait désarmer en une journée. Les slots
libres ne sont donc signalés que si **la campagne est en cours**, ce qui se dérive :
au moins un agent en vol, **ou** un worktree d'agent, **ou** une PR ouverte, **ou** un commit
d'avance. Zéro partout = dépôt au repos = silence total.

Signaux (tous **actionnables**) : slots libres, commits non poussés, fichiers suivis modifiés,
worktrees nettoyables, verdict de banque, drain armé, aucune session Frida, runners orphelins.
Le contexte (PR, session, `liveRunners`) accompagne les signaux et **ne parle jamais seul**.

### 3.4 Le verdict de banque se ventile en TROIS régimes

`rc != 0` → signalé **à chaque tour** (un rouge ne s'acquitte pas, il se corrige).
`rc is None` → le fichier existe mais son `rc` est **illisible** : capteur muet, jamais « rien à
signaler ». `rc == 0` → signalé **une fois**, et seulement si son commit n'est **pas encore** dans
`origin/master` (c'est la lecture exacte de « plus récent que le dernier push »).

### 3.5 Le hook ne doit jamais immobiliser un tour

`gh` est le seul poste réseau. Son timeout portait `max(self.timeout, 12.0)`, ce qui **annulait**
tout réglage à la baisse. Sous `--hook` : timeout **3 s**, cache **300 s**, et un dépassement rend
l'état *pas mesuré* — ce qui se lit, au contraire d'un tour figé. Le cache est **horodaté et son
âge est imprimé** à côté des chiffres qui en dérivent (`PR ouvertes : 2 [cache 135 s]`) : un cache
muet serait une valeur inventée.

## 4. Deux bugs trouvés en chemin, tous deux silencieux

**`ratchets-bg.ps1` — la ligne `rc` du verdict n'existait pas.** En PowerShell la virgule lie plus
fort que `-f` : `@("a","b","mur {0:N1} s" -f $mur, "rc : $rc", '')` se parse comme
`@(...) -f ($mur, "rc…", '')`. Le tableau de gauche est joint par des espaces et appliqué comme un
format unique — l'en-tête tenait sur **une seule ligne** et la ligne `rc` **disparaissait**. Les
**3** verdicts présents sur disque n'en portaient aucune ; tout lecteur automatique rendait donc
« rc inconnu » sur un fichier d'apparence normale. Les parenthèses sont désormais load-bearing et
commentées ; `_lire_verdict` sait lire **les deux formes** (en-tête, puis repli sur la ligne de
bilan du corps) — sinon le cliquet neuf serait muet sur son unique gisement historique.

**Le BOM de PowerShell 5.1.** Il préfixe d'un `﻿` tout ce qu'il pipe vers un exécutable natif.
`json.loads` levait, la charge du hook retombait à `{}`, et le rappel se déclenchait **malgré
`stop_hook_active`** — c'est-à-dire la boucle qu'il est censé éviter. Deux gardes : le wrapper
n'émet plus de BOM (`$OutputEncoding`), et `loop_status` sait l'avaler. Une charge **illisible**
se rabat désormais sur le **silence** (défaut sûr), plus sur « pas de garde ».

**`dossier_verdicts()` lisait les verdicts d'un AUTRE arbre.** Il passait par
`host_inputs.resolve`, qui part de **sa** racine (`parents[2]` de son propre fichier) et non de
l'arbre qu'on demande de juger. Un `--repo` explicite lisait donc ailleurs. Trouvé par
`probe_467r4` (§5) dès sa première exécution : le dépôt jetable portait un verdict **ROUGE**,
l'outil rapportait le **VERT** du worktree de l'agent. **Aucune substitution de sources n'aurait
pu le montrer** — le bug est dans la résolution d'un chemin réel. Ordre corrigé : l'arbre jugé
d'abord, `host_inputs` en repli (qui garde son sens : depuis un worktree, `logs/` est vide par
construction et il faut remonter à l'arbre principal).

## 5. Les deux cliquets

### `probe_467` — dans la banque

100 % **offline** : la façade `Sources` est **substituée**. Sans cette couture, garder le tri-état
exigerait d'éteindre le host — et un cliquet qui dépend de l'état de la machine n'est pas un
cliquet. **37 épreuves, 0,9 s**, aucun appel à git / `gh` / host, tmpdir **système** (#455).

**Contre-épreuve (il doit pouvoir ROUGIR, #439)** : 6 mutations injectées **en mémoire**, 6 rouges.

| Mutation | rc |
|---|---|
| `liveRunners` non mesuré rendu comme `0` | 3 |
| `gh` en échec rendu comme « 0 PR ouverte » | 2 |
| `only_alive` laisse passer les agents silencieux | 1 |
| le hook parle hors du dépôt / dans une chaîne relancée | 1 |
| verdict illisible rabattu sur `rc=0` | 3 |
| un worktree d'agent **en vol** proposé au nettoyage | 4 |

Sans mutation : `rc=0`.

### `probe_467r4` — HORS banque, et c'est ce qui le rend utile

Il monte un **vrai dépôt git** (clone, branches, worktrees, merges) et y rejoue la scène du
2026-08-04 : 3 commits non poussés, 1 fichier suivi modifié, 2 non suivis dont un inconnu,
2 worktrees d'agents livrés, un verdict rouge non livré, host coupé. **14 épreuves + une
contre-épreuve** (« tout réglé → silence total », sans laquelle un outil qui signalerait *tout,
toujours* passerait les 13 autres). **40 s.**

Il couvre exactement ce que `probe_467` ne peut pas : le **contrat** des commandes
(`--porcelain=v2`, `worktree list --porcelain`, `for-each-ref --merged`) et la résolution de
chemins **réels** — c'est lui qui a trouvé le bug de `dossier_verdicts`. Il n'entre pas dans la
banque parce qu'il construit un dépôt : coût dépendant de la machine, là où la banque exige du
déterministe et du bon marché. **La seule chose qu'il substitue est la flotte** (elle se lit dans
`~/.claude/projects` — propriété de la machine, pas du dépôt).

## 6. Coût mesuré

| | médiane | min |
|---|---|---|
| `python -c pass` (référence) | 0,52 s | 0,24 s |
| hook, **autre projet** | — | — (hook **du projet** : ne se déclenche pas) |
| hook, **ce dépôt**, cache chaud | 2,61 s | 1,36 s |

Mesures prises **sous 5 agents en vol** — la contention domine (`git status` isolé passe de 0,25 s
à 4,29 s sous charge). Le mur est celui de `git status --porcelain=v2` et du démarrage de Python.

Trois réductions faites : `--porcelain=v2 --branch` fond **trois** appels git en un (branche +
avance + arbre) ; `for-each-ref --merged` limité aux **refs des worktrees montés** au lieu de
`branch --merged` sur les **169** branches locales, et **entièrement sauté** quand il n'y a aucun
worktree d'agent ; `urllib.request` / `concurrent.futures` / `shutil` importés paresseusement.

**Le hook est posé dans `<repo>/.claude/settings.json`, pas dans le settings global.** Trois
raisons, toutes structurelles : il est **versionné** (donc livré par la PR, et il survit à un
changement de machine — le global ne serait dans aucune PR) ; il ne se déclenche **que** pour ce
dépôt (coût nul pour les autres projets, alors que le global ferait démarrer Python à chaque fin de
tour de chaque projet) ; et le dépôt a **déjà** ce précédent (`SessionStart` → `scripts/hooks/`).
Le hook global qui joue un son n'est **pas touché** : les deux fusionnent.

## 7. Résidus

- **`#467-r1` — le plafond de 5 est ASSUMÉ.** Rien dans le dépôt ne le dérive : c'est une décision
  d'orchestration. S'il change, la valeur se périme en silence. Elle porte sa source en commentaire
  et deux surcharges, mais ce n'est pas une mesure.
- **`#467-r2` — les squash-merges anciens.** `git for-each-ref --merged` ne voit qu'un tip
  **ancêtre** ; un squash est rattrapé par `gh pr list --state merged --limit 120`. Au-delà de 120
  PR, un worktree squash-mergé ne sera **pas** proposé au nettoyage. C'est le côté sûr (on ne
  propose jamais de supprimer une branche non livrée), mais c'est un trou.
- **`#467-r3` — un seul rappel par chaîne.** `stop_hook_active` interdit de re-bloquer, sinon le
  hook boucle. Si l'orchestrateur ne traite pas tout au premier tour, le rappel ne revient qu'au
  tour utilisateur suivant.
- **`#467-r5` — le journal d'acquittement est un ÉTAT.** `logs/ratchets-bg/../loop-status-seen.json`
  est local et gitignoré ; le supprimer re-signale une fois le dernier verdict vert. Bénin, mais
  c'est le seul endroit où l'outil se souvient de quelque chose.
- **`#467-r6-a` — la borne de 30 min du repli est ASSUMÉE**, comme le plafond de `r1`. Rien ne la
  dérive : c'est un arbitrage entre « servir une PR déjà relue » et « ne rien dire ». Elle est
  gardée par `probe_467` (un cache plus vieux retombe en PAS MESURE), donc elle ne peut pas
  disparaître en silence — mais sa *valeur* reste un choix.
- **`#467-r4-a` — le volet LIVE ne juge que ce que le host EXPOSE.** `probe_467r4_contrat_host`
  confronte la forme réelle quand le host répond, mais un champ présent et **faux** (un
  `liveRunners` qui compterait le registre host au lieu du registre hooks) passerait : le cliquet
  garde la FORME, pas la justesse de la valeur. Cette justesse-là n'a pas de second témoin.

## 8. `#467-r6` — la ligne PR aveugle : le diagnostic annoncé était FAUX

**Ce qui était supposé** : « `gh` n'est pas sur le PATH que voit le processus du hook ».
**Ce que la mesure dit** (2026-08-04, poste de l'utilisateur) :

| mesure | résultat |
|---|---|
| `gh` sur le PATH sous `pwsh` **et** sous le `powershell.exe -NoProfile` qui exécute le hook | **oui, identique** — 39 entrées, `GitHub CLI` présent des deux côtés |
| `gh pr list`, 20 tirages au repos | médiane **1,60 s**, max **1,99 s**, **0** au-dessus de 3 s |
| `gh pr list` seul, sous l'hôte du hook | **2,90 s** pour un budget de **3,00 s** |
| tour **complet** en mode hook (gh concurrent de `git status`, flotte, banque) | **5 tours sur 8** en `rc=127` |

La cause est donc le **BUDGET**, pas le PATH — et elle est **intermittente hors hook aussi**, ce
qu'une observation indépendante a confirmé le même jour (deux invocations directes à une heure
d'écart, une réussie, une en `rc=127`). Un correctif « chemin absolu » aurait donné l'illusion
d'avoir réparé.

**Pourquoi le diagnostic était impossible à faire** : les trois pannes de `gh` — binaire absent,
délai dépassé, `OSError` — rendaient **toutes** le même `rc=127`, la sentinelle `RC_MUET`. Le
message ne portait aucune information. C'est ce qui a fait lire « absent du PATH » un dépassement
de délai, et c'est le vrai défaut de fidélité : *un capteur qui ne sait pas nommer sa panne fait
diagnostiquer la mauvaise cause*.

**Ce qui a été fait**, du plus à la cause au plus périphérique :

1. **`timeout_gh`, budget propre de `gh`** (10 s sous `--hook`, 12 s sinon). Ce n'est **pas** le
   plancher `max(self.timeout, 12.0)` retiré auparavant : un paramètre distinct se règle dans les
   deux sens. Le mur reste tenu par les **20 s** du hook côté Claude Code et par le cache de 300 s.
   Mesuré après : **0/8** tours aveugles, même gisement, même hôte.
2. **Chaque panne porte son nom** (`gh: delai depasse (10 s)`, `gh introuvable`, `gh: rc=4`).
3. **Repli sur le cache périmé**, borné à 30 min et **ASYMÉTRIQUE** : retenu *seulement* s'il porte
   une PR ouverte. Un cache disant « 0 PR » ne prouve rien quand `gh` est muet — une PR ouverte
   depuis y serait absente, et l'outil se tairait en ayant l'air d'avoir mesuré. **Le repli peut
   SIGNALER, jamais RASSURER** ; aucun chemin ne fabrique un zéro. Les PR *mergées* sont écartées
   sous repli : proposer un nettoyage de worktree sur un instantané périmé, c'est proposer de
   supprimer le travail d'un agent.
4. **Résolution de `gh` par chemin absolu** (`TACTICUS_GH_EXE`, PATH, emplacements connus). Cause
   **éliminable à coût nul**, mais ce n'était pas la cause constatée — et c'est dit.

### La piste « git pur » est RÉFUTÉE par la mesure

L'idée proposée — « les branches `worktree-agent-*` présentes sur `origin` et non fusionnées dans
`master` donnent la même information en git pur » — ne tient pas :

    for-each-ref --no-merged origin/master refs/remotes/origin/   ->  79 branches
    gh pr list --state open                                       ->   1 PR

Les branches d'agents **survivent sur `origin` après leur merge**, et un squash-merge ne les rend
jamais ancêtres de `master` : `--no-merged` les compte donc toutes, indéfiniment. Un filtre de
fraîcheur *semble* sauver la piste (moins de 48 h → exactement la bonne, 1 pour 1), mais il produit
des faux **négatifs** sur les PR **anciennes** — précisément les plus oubliables, c'est-à-dire le
mauvais sens d'erreur pour un rappel. La voie git pure est donc écartée comme substitut de `gh`.

## 9. `#467-r4` — le contrat host n'était vérifié par rien

`probe_467_loop_status_fidelity` **et** `probe_467r4_scene_git_reelle` substituent tous deux la
façade `Sources`, donc tous deux remplacent `http_json`. Un champ disparu côté host les laissait
**verts tous les deux** : deux lecteurs qui partagent la même entrée morte s'accordent parfaitement
et ont tort ensemble. La dégradation serait du pire genre — `dr.get("liveRunners")` sur une réponse
qui ne porte plus la clé rend `None`, donc `live_runners` bascule en PAS MESURE **à vie**, sur le
seul chiffre que personne ne peut deviner.

`probe_467r4_contrat_host.py` (dans la banque) le ferme en **deux volets** :

- **A — le contrat contre le CODE SOURCE du host** (`frida/host/*.ts`), 100 % offline. La liste des
  champs exigés est **dérivée de `loop_status.mesurer_harnais`** par lecture de son propre source :
  un champ ajouté au lecteur devient automatiquement exigé du producteur. *Un cliquet dont la liste
  se recopie dérive* — c'est le vice qu'on corrige, on ne le réintroduit pas. La recherche porte sur
  l'argument de `res.json(...)` et suit les spreads (`...getDrainState()` → types de `drain.ts`).
- **B — la FORME réelle**, quand le host répond. Il ne conditionne pas le vert (le host est éteint
  la moitié du temps) et ne dépend pas d'une session **vivante** : il juge la forme, pas la valeur
  — `liveRunners: null` accompagné de `liveRunnersError` est une réponse conforme. Injoignable →
  **`NON MESURE`** dit franchement, verdict `PASS PARTIEL`, jamais un vert muet.

**L'auto-épreuve intégrée (#439) a payé au premier passage.** Le volet A validait `liveRunners` sur
la **déclaration locale** `let liveRunners: number | null = null` du handler, et restait donc vert
alors que le champ avait été retiré de `res.json`. Resserré sur le littéral réellement rendu.
Même leçon un cran plus bas : l'épreuve « la cause de `gh` est nommée » passait par une
substitution de `gh()` — donc n'exerçait **jamais** le code qu'elle prétendait juger, et restait
verte sous mutation. Les causes sont désormais exercées en substituant `subprocess.run`, **un cran
en dessous**. Sans la contre-épreuve par mutation, ces deux gardes seraient entrés aveugles.
