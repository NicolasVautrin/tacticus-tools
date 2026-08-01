# case-434 — le périmètre des cliquets : la banque lisait le code des autres agents

**Verdict : PÉRIMÈTRE FAUX, corrigé.** Deux étapes de `probe_283` (`mirror`, `tables`)
énuméraient depuis la **racine du dépôt** sans exclure `.claude/worktrees/`. Lancées depuis
l'arbre principal, elles parsaient donc les **checkouts entiers des autres agents en vol**.
C'est d'abord un problème de **justesse** — un rouge appartenant à la branche d'un agent
serait attribué à l'arbre principal — et accessoirement le mur de la banque.

## 1. Le périmètre réel

Mesuré le 2026-08-01 depuis `C:\Users\nicolasv\tacticus-tools`, **8 worktrees vivants** :

| | total sous la racine | `.claude/worktrees/` | `node_modules/` | **vrai périmètre** |
|---|---|---|---|---|
| `*.py` | 13 501 | **11 702 (87 %)** | 279 | **1 514** |
| `*.ts` | 2 168 | 1 640 | 321 | 207 |
| `*.js` | 1 184 | 656 | 420 | 93 |

`node_modules` était déjà filtré — mais **après** la traversée, donc payé. Les worktrees, eux,
n'étaient ni filtrés ni élagués : lus, parsés, **et rapportés**.

## 2. Ce n'est pas un coût, c'est un rapport faux — la preuve

Les logs du passage de la banque du 2026-08-01 depuis l'arbre principal :

| log | lignes de rapport | dont sous `.claude/worktrees/` |
|---|---|---|
| `probe_283_mirror.log` | 29 | **16** — soit 8 worktrees x 2 mirrors |
| `probe_283_tables.log` | 30 | **24** — soit 8 worktrees x 3 tables |

`etape 1` annonçait **18 classes** de mirror : **2** appartiennent à l'arbre principal, 16 sont
les copies des agents. `etape 3` annonçait **27 tables** : **3** sont à l'arbre principal.
**89 % du rapport, dans les deux cas, décrivait le code en cours d'autres agents.**

Elles étaient vertes ce jour-là — le faux positif ne s'est donc pas encore matérialisé en
rouge. Mais la mécanique est là et elle est immédiate : un agent qui touche SON
`engine/dsl/event_trigger_type.py` (c'est exactement le fichier qu'un port d'enum édite) fait
rougir la banque lancée depuis l'arbre principal, sur une mutation **absente** de l'arbre
principal. Le rapport nomme bien le chemin, mais la ligne de synthèse, elle, dit
`BANQUE ROUGE`, et c'est elle qui décide d'ouvrir ou non une PR.

## 3. Le correctif, et le piège qu'il ne rouvre pas

Le commentaire au-dessus de `_SKIP_PARTS` documentait déjà le mot « worktrees », **pour une
autre raison** : filtrer sur le chemin **relatif au dépôt**, jamais sur `p.parts` absolu —
un agent tourne dans `.claude/worktrees/agent-<id>/`, donc tout chemin absolu chez lui contient
`worktrees`, et un filtre naïf le faisait **s'auto-exclure** (la 1re version du probe rendait
« 0 classe trouvée — aucun mirror Python » avec `VERDICT: PASS`).

C'est **ce même relatif** qui rend l'exclusion correcte dans les deux sens :

* depuis l'arbre principal, `rel` vaut `.claude/worktrees/agent-<id>/...` → hors périmètre ;
* depuis un worktree, `REPO` **est** ce checkout, `rel` ne porte pas ce préfixe → aucun
  auto-exclusion.

D'où `_SKIP_RELS = (".claude/worktrees",)`, comparé par **chemin complet** (`rel == r` ou
`rel.startswith(r + "/")`), jamais par le segment `worktrees` seul.

Second changement, indissociable : `sorted(REPO.rglob(pat))` → `_fichiers_du_depot(suffixe)`,
qui **élague à la source** (`os.walk` + `dirnames[:] = ...`). `rglob` descend partout **puis**
on filtre : la traversée de `.git`, `node_modules`, `sources_win`, `dist` était payée
intégralement. Trois points de fidélité :

* les listes sont **triées** en fin de collecte → même ordre que `sorted(rglob(...))` ;
* la comparaison de suffixe est **insensible à la casse**, comme `Path.glob` sous Windows
  (`rglob("*.py")` y ramène aussi `Foo.PY`) ;
* le cache est **keyé sur `REPO`**, pas global — un appelant qui repointe la racine (bench,
  contre-épreuve) ne relit pas le cache de l'autre arbre.

Bonus non recherché : `os.walk` ne suit pas les points de reparse, là où `rglob` y descend.

## 4. Non-régression : la sortie, pas le chrono

Montage : les **deux** versions du probe chargées avec `REPO` **forcé sur l'arbre principal**,
deux processus en parallèle, `stdout` capturé. Rien n'est écrit dans l'arbre principal.

Critère (#409) : la sortie APRÈS doit être identique à la sortie AVANT **après retrait des
seules lignes sous `.claude/worktrees/` ou `node_modules/`**.

| | lignes AVANT | dont hors périmètre | DÉTAIL (lignes portant un chemin) |
|---|---|---|---|
| `etape 1` (mirror) | 18 | 13 | **IDENTIQUE** — 2 lignes, même ordre |
| `etape 3` (tables) | 22 | 18 | **IDENTIQUE** — 3 lignes, même ordre |

Les seules lignes qui changent sont les **agrégats**, et leur arithmétique se vérifie :
`15 classes -> 2` (delta 13 = lignes retirées), `21 tables -> 3` (delta 18 = lignes retirées).

Preuve plus forte que le rapport — les **listes de fichiers énumérées**, comparées élément par
élément :

| | fichiers |
|---|---|
| `rglob` brut (ancien) | **13 319** — dont 10 460 sous `.claude/worktrees/`, 1 041 sous les autres `_SKIP_PARTS` |
| ancien, après son `_ignore` | **1 818** |
| `os.walk` élagué (nouveau) | **1 818** |
| **listes identiques, ordre compris** | **oui** — 0 en plus, 0 en moins |

Et les 6 `SyntaxWarning` de `tools/**` (gitignoré, présent seulement dans l'arbre principal)
sont émis **avant comme après** : le périmètre hors-git de l'arbre principal est conservé.

⚠ Le log de banque annonçait 18 mirrors / 27 tables ; le bench, 15 / 21. Ce n'est pas une
incohérence — c'est **le symptôme** : la population de worktrees a changé entre les deux
mesures (des agents ont fini). Le verdict d'un cliquet dépendait du nombre d'agents en vol.

### 4bis. La contre-épreuve — il exclut, et il mord encore

Une exclusion qui rend le balayage muet serait pire que le trou. Trois mutations, **depuis mon
worktree** (donc depuis un chemin absolu qui contient `worktrees` — c'est le cas piégeux) :

| mutation | version | attendu | obtenu |
|---|---|---|---|
| worktree **imbriqué** factice `.claude/worktrees/faux-agent-434/…/event_trigger_type.py` portant `UnitHealed = 999` | **corrigée** | **VERT** (hors périmètre) | `2 classe(s) trouvee(s)`, `VERDICT: PASS`, rc 0 |
| la **même**, arbre identique | **ancienne** | ROUGE (c'est le trou) | `3 classe(s)`, **2 `FAIL`** sur le chemin du faux agent |
| `EventTriggerType.UnitDeath = 0 -> 700` dans le **vrai** `scripts/python/engine/dsl/` | **corrigée** | **ROUGE** | rc **1**, `FAIL … UnitDeath = 700 ; le build rnca9r7q6c dit 0` |

La 1re et la 3e ensemble sont le contrat complet : le probe **ignore** l'autre checkout et
**voit** le sien. La 2e démontre que le faux positif n'était pas théorique — mêmes octets sur
disque, verdict opposé selon la version.

Mutation vérifiée avant chaque run (`sha256` changé) et arbre restauré **bit-exact** (`sha256`
identique, `git status` inchangé) : sur une contre-épreuve, VERT est le résultat suspect.

## 5. Le mur

Conditions — **elles font partie du chiffre** : arbre principal
`C:\Users\nicolasv\tacticus-tools`, **8 worktrees vivants**, machine partagée (7 à 14
processus `python` d'autres agents pendant les mesures).

**AVANT, banque complète depuis l'arbre principal** (19 cliquets, parallélisme 19) : mur
**428,5 s**, tenu par `probe_283:tables` **427,2 s** et `probe_283:mirror` **410,1 s**. Le
suivant est `pytest_signatures` à **156,8 s** — donc les deux étapes trouées valaient à elles
seules **2,7x** le reste de la banque.

**Les deux étapes, même arbre, 2 processus** :

| | avant | après | rapport |
|---|---|---|---|
| `etape 1` (mirror) | 226,2 s | **22,4 s** | x10,1 |
| `etape 3` (tables) | 236,9 s | **22,9 s** | x10,3 |
| énumération seule (sans parse) | 13,0 s | **1,4 s** | x9,3 |

**APRÈS, mur de la banque depuis l'arbre principal** : les 17 autres cliquets sont bornés à
`scripts/python/**` (§6), donc leur coût **ne dépend pas** de la racine ni du nombre de
worktrees. Le mur du même run privé de ses deux premières lignes vaut donc **156,8 s** —
`pytest_signatures`. C'est une **recomposition**, pas une mesure directe : mesurer
directement aurait exigé d'écrire le correctif dans l'arbre principal.

### Où part le temps restant (mesure, pas estimation)

Le mur reste au-dessus de la minute, et il n'est plus dans `probe_283`. Profil du run AVANT,
hors les deux étapes corrigées : `pytest_signatures` 156,8 / `probe_319` 135,3 /
`probe_283:exec` 121,7 / `probe_366bcp` 100,2 / `probe_283:prose` 96,5 / `probe_313` 84,2 /
`probe_283:on` 82,8 / `probe_273` 68,6 / `probe_391` 53,3 / puis 6 cliquets sous 25 s.

Ce profil a une cause unique et **structurelle** : **7 cliquets relisent intégralement le même
`scripts/python/**`** (`probe_273`, `probe_319`, `probe_283:exec`, `:prose`, `:on`,
`probe_366bcp`, `pytest_signatures`), et 3 de plus en relisent un sous-arbre (`probe_313`,
`probe_391`, `probe_366pos`). #409 a mesuré le poste dominant de cette lecture : l'`open()`
lui-même, ~9 ms/fichier (filtre système sur `CreateFile`), **et non** le `read()` ni le parse.
Soit ~13 s de pur `open()` par cliquet, ~90 s à l'échelle de la banque — payés **N fois**
parce que chaque cliquet est un **processus séparé**. Le cache mémoïsé de #409 s'arrête à la
frontière du processus.

Le gisement suivant est donc là, et il n'est **pas** dans un cliquet : il est dans le modèle
d'exécution de la banque (un cache de sources/AST partagé, ou un lanceur unique in-process).
Non traité ici — c'est un changement de forme de `scripts/ratchets.ps1`, pas une correction de
périmètre.

## 6. Le balayage des autres cliquets — pas de foyer commun, et c'est un résultat

Critère : *ce cliquet énumère-t-il des fichiers par `rglob`/`walk` depuis la racine du dépôt
sans exclure `.claude/worktrees` ?* Les 19 entrées de `scripts/ratchets.ps1` :

| cliquet | racine énumérée | verdict |
|---|---|---|
| `probe_283:mirror`, `probe_283:tables` | **`REPO`** | **TROUÉS — corrigés ici** |
| `probe_283:exec`, `:prose`, `:on` | `REPO/scripts/python` | sains |
| `probe_283:diff` | n'énumère rien (lit `enums.tsv`) | sain |
| `probe_273`, `probe_319` | `<scan_root>/scripts/python` | sains |
| `probe_313` | `scripts/python/engine` | sain |
| `probe_366bcp` | `scripts/python` / `scripts/python/engine` | sain |
| `probe_366pos` | `scripts/python/engine` | sain |
| `probe_391` | `scripts/python/tests` | sain |
| `pytest_signatures` | `scripts/python` | sain |
| `probe_365` | **`git ls-files`** — n'énumère pas le disque | sain par construction |
| `probe_181`, `probe_120`, `probe_229`, `probe_421`, `probe_366camo` | n'énumèrent aucun fichier (registres importés) | sains |

**Il n'existe donc pas de foyer commun de balayage** : `_SKIP_PARTS` n'est défini que dans
`probe_283`, et aucun autre cliquet ne remonte à la racine. En inventer un pour deux appels
dans un seul fichier aurait ajouté un module partagé sans lecteur — le correctif reste local,
et cette ligne est là pour que le prochain ne le cherche pas.

**Résidu, fermé par #440** (§10) : `probe_274_step_ordinals_sweep.py:245` portait le **même**
trou, et filtrait en plus sur `p.parts` **absolu**.

## 7. Ce qui n'est PAS couvert

* **`tools/`** (gitignoré, présent seulement dans l'arbre principal) reste dans le périmètre et
  y produit 6 `SyntaxWarning` sur `stderr` : c'est un écart arbre-principal/worktree
  **indépendant** de cette tranche, laissé tel quel.
* **Le mur mesuré est celui d'une machine partagée** (7 à 14 processus python d'autres agents
  pendant les mesures). Les rapports entre compositions sont exploitables ; les secondes
  absolues sont à re-dériver.

## 8. Reproduire

```powershell
pwsh -File scripts/ratchets.ps1 -Only probe_283      # la banque, les 6 étapes
python scripts/python/probe_283_enum_ordinal_sweep.py --step mirror
```

Banque entière re-jouée après le correctif, depuis le worktree : **VERTE 19/19, mur 91,3 s**,
`probe_283:mirror` **51,8 s** et `:tables` **52,9 s** — ils ne tiennent plus le mur nulle part.

## 9. Re-joué après rebase sur `origin/master`

Rebase **sans conflit** (3 PR intégrées entre-temps : #472, #473, #474). Re-jeu complet :

* banque entière **VERTE 20/20**, mur **91,1 s** (`origin/master` a ajouté `probe_431`) ;
  `probe_283:mirror` **54,1 s**, `:tables` **54,6 s** ;
* ancienne vs nouvelle version sur l'arbre rebasé, `REPO` = le worktree : sortie
  **strictement identique octet à octet** pour `mirror` et pour `tables`, listes énumérées
  **1 778 = 1 778, ordre compris**. Depuis un worktree le correctif ne change donc **rien** au
  verdict — seulement le coût (`mirror` 84,3 → 34,3 s, l'élagage de `.git`/`dist`/`logs`).

Équivalence contre la révision antérieure — c'est ainsi que celle-ci a été prouvée : charger
les deux versions du probe avec `REPO` **forcé sur l'arbre principal**, comparer les sorties
après retrait des seules lignes sous `.claude/worktrees/` et `node_modules/`.

## 10. #440 — les deux résidus, fermés ensemble

Le second **est** le garde du premier : corriger `probe_274` sans cliquet aurait reproduit la
situation de §7 (un fait, pas un cliquet).

### 10.1 `probe_274` — mesuré d'abord, corrigé ensuite

Il n'était dans aucune banque, donc son état n'avait **jamais** été mesuré. Même commit, même
fichier (`sha256` identique dans les deux arbres), 8 worktrees vivants :

| lancé depuis | `*.py` retenus | dont `.claude/worktrees/` | durée | verdict |
|---|---|---|---|---|
| arbre principal | 13 267 | **11 746 (88,5 %)** | **366,6 s** | PASS |
| un worktree | 1 494 | 0 | **33,7 s** | PASS |

`PASS` des deux côtés : le trou était **latent en rapport** (aucun ordinal en dur ne subsiste
aujourd'hui) et **réel en périmètre** — le probe lisait les checkouts des autres agents.

⚠ **Un point de l'énoncé de #434 était inexact, et la mesure le corrige** : `probe_274` ne
s'auto-excluait *pas*. Son tuple `p.parts` ne contenait pas `worktrees` — il n'excluait donc
**rien**. Le filtre absolu n'était pas la faute active : c'était le **piège armé**, celui qui
transforme la correction évidente en faux vert. Mesuré directement, en ajoutant `worktrees` à
ce tuple :

| variante « filtre absolu + `worktrees` » | arbre principal | un worktree |
|---|---|---|
| fichiers retenus | 1 521 (a l'air juste) | **0** — auto-exclusion totale, `VERDICT: PASS` |

Après correction (filtre sur le **relatif** + `os.walk` élagué à la source) :

| | fichiers retenus | dont worktrees | marche |
|---|---|---|---|
| arbre principal | **1 527** | **0** | 0,6 s |
| un worktree | **1 495** | 0 | 0,1 s |

Les deux sens tiennent : il ignore les autres checkouts **et** ne s'ampute pas du sien.

### 10.2 `probe_440` — le cliquet, dérivé et non saisi

`scripts/python/probe_440_repo_root_scan_guard.py` balaie **tout `scripts/python/**`**, pas les
seules entrées de la banque. Deux détecteurs, tous deux dérivés du seul chemin canonique
`.claude/worktrees` — **aucune allowlist** (règle #421) :

* **R1** — énumération récursive (`rglob`, `glob("**/…")`, `os.walk`, `glob.glob`) partant de la
  racine, dans un fichier qui ne porte nulle part, **dans son code**, un préfixe de chemin de
  `.claude/worktrees`. La racine est résolue symboliquement (`Path(__file__).resolve()`,
  `.parent`, `.parents[k]`, `os.path.dirname`) et comparée à la profondeur du fichier ; les
  paramètres sont liés par **point fixe intra-fichier** (`def f(root): root.rglob(…)` n'est
  fautif que si un appelant lui passe la racine).
* **R2** — le piège armé : un **segment** de ce même chemin (`.claude`, `worktrees`) testé
  contre `.parts`.

**Être ancré à la racine ne suffit pas** : c'est le premier segment qui tranche. Le détecteur
naïf a produit un faux positif mesuré —
`glob.glob(str(PYDIR.parents[1] / "data" / "symbols" / "*" / "frida" / "classes.tsv"))`
(`test_356_noncomparable_oracle_live.py:112`) part bien de la racine mais `data` le **confine**.
Une descente explicitement dirigée vers `.claude` (lire les transcripts d'agents) est
intentionnelle, donc hors gisement.

**Son étape 0 est un auto-test de ses propres détecteurs** sur 15 sources synthétiques, joué à
**chaque** run et compté dans le verdict — un cliquet dont le détecteur a cessé de mordre verdit
sur un dépôt fautif (c'est `probe_181` avant #430). Il a payé tout de suite : il a trouvé **deux
bugs de mon détecteur** (`os.walk` capté par la branche `Path.walk`, donc jamais testé sur son
argument ; et le cas `.claude` exempté par sa propre conformité) que la relecture n'avait pas vus.

### 10.3 Le garde MORD — mutation vérifiée avant lecture du verdict

Témoin jetable portant les deux motifs, joué **par la banque** (run complet), mutation vérifiée
présente avant lecture :

| étape | résultat |
|---|---|
| témoin R1+R2 en place | **ROUGE nommé** — `probe_440_temoin_mutation.py:16` sur R1 *et* sur R2, `VERDICT: FAIL (2)` |
| témoin retiré | **VERT**, rc 0 |

Même protocole pour l'admission de `probe_274` (un cliquet qui ne peut rougir de rien n'a rien à
faire dans la banque — #430-r2) : témoin portant les deux formes qu'il est seul à voir, l'**alias**
(`step = ev.get("step")` puis `step == 10`) et la **clé de dict** (`frame["code"] == 13`) →
**ROUGE nommé**, `10=AddMachine (avant: AddUnit)` — le décalage exact de la MAJ. Retiré → vert.

### 10.4 Admission dans la banque

Les deux entrent. Le critère n'est pas le coût absolu mais le **coût marginal en parallèle** et
**ce que le cliquet est seul à voir** :

* `probe_274` est seul à voir **`GroupType`** (104 membres) — aucune étape de `probe_283` ne le
  couvre — et les ordinaux `StepType` derrière un **alias** ou une **clé de dict**, motifs que
  l'étape `exec` de `probe_283` ne reconnaît pas ;
* `probe_440` est seul à voir le périmètre lui-même.

Banque complète re-jouée depuis le worktree : **VERTE 23/23, mur 178,8 s**, tenu par
`pytest_signatures` (176,9 s). `probe_274` **95,1 s** et `probe_440` **95,0 s** — tous deux très
en dessous du mur, donc **coût marginal nul**. Seuls : 42,0 s et 43,6 s hors charge.

### 10.5 Ce que #440 ne couvre PAS

* **Le balayage porte sur `scripts/python/**`**, comme demandé. Un `REPO.rglob` dans
  `frida/host/*.ts` ou dans un `.ps1` n'est pas vu — autre langage, autre analyseur.
* **Chaîne construite dynamiquement** : `glob.glob(str(REPO) + "/**/*.py")` (concaténation,
  f-string) n'est pas résolu — R1 ne rougit que sur les formes `Path` / `os.path.join`. Aucun
  site du dépôt n'est dans ce cas au 2026-08-01.
* **R1 vérifie que le fichier CONNAÎT le chemin d'exclusion, pas que le filtre est bien câblé.**
  Vérifier le câblage serait ré-implémenter le filtre. R2 couvre l'autre moitié — que ce littéral
  ne soit pas appliqué à des segments.
* **`probe_274` reste `PASS` sur le fond** : sa correction est un périmètre, pas un ordinal. Le
  gisement d'ordinaux en dur est à 0 depuis #279, et c'est maintenant un cliquet qui le tient.
