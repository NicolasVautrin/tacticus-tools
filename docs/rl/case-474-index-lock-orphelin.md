# Case 474 — `.git/index.lock` orphelin dans l'arbre partagé (+ résidu #471-r2)

**Cause ÉTABLIE et reproduite** : un process `git` **terminé de force** pendant qu'il tient
`.git/index.lock` laisse ce lock derrière lui. Fermé à la source par `--no-optional-locks`.
Cliquet : `probe_474`. Instrument : `probe_474_git_lock_forensics.py`.

**Lien avec #471-r2 : RÉFUTÉ** — les deux symptômes n'ont pas la même cause (§5).

## 1. Le fait, mesuré

`git status` **prend** `.git/index.lock` et l'y laisse **à 0 octet pendant ~toute sa durée**.
Mesures sur dépôt jetable (6 000 fichiers, index 482 Ko ; l'arbre réel : 1,2 s d'après
`loop_status.mesurer_livraison`) :

| mesure | résultat |
| --- | --- |
| `git status` : lock pris | **5/5**, taille observée **0** sur tout l'échantillonnage (2 ms) |
| `git add -A` : tailles vues | 0 → 131072 → 262144 → 393216 → 481886 (blocs de 128 Ko, en fin de course) |
| kill (`TerminateProcess`) pendant la fenêtre, binaire réel `mingw64/bin/git.exe` | **20/20 résidus**, tous **0 octet**, tous **libres** |
| idem via le shim `cmd/git.exe` (ce que résout le PATH) | **1/60 (1,7 %)** — il ne relaie pas le signal |
| témoin sans kill | **0/10** |

La signature « 0 octet » n'est donc **pas** un indice : c'est l'état **normal** d'un lock
vivant. Seule l'**ouverture exclusive** distingue un résidu d'une commande en cours.

Les trois occurrences de #474 sont des **victimes**, pas des créatrices : `fatal: Unable to
write index.` est le littéral de `builtin/merge.c`, atteint quand `repo_refresh_and_write_index`
échoue à **prendre** le lock (`repo_hold_locked_index(..., 0)` → `-1`). Même sémantique que
`Unable to create index.lock: File exists`.

**Le taux est fonction de (largeur de fenêtre × latence du tueur), jamais nul** : un kill
instantané dans la fenêtre = 100 %, un `taskkill /T` (~300 ms de démarrage) rate une fenêtre de
240 ms mais mord une fenêtre de 1,2 s. C'est pourquoi la parade supprime la **fenêtre**, et non
le résidu.

## 2. Les deux porteurs, dans notre code

| site | contexte tuable |
| --- | --- |
| `scripts/ratchets-bg.ps1:147` | `git -C $repo status` sur l'**arbre principal**, script fait pour tourner en arrière-plan |
| `scripts/python/loop_status.py`, `Sources.git` | hook `Stop`, `--repo` = arbre principal, `subprocess.run(timeout=3.0)` qui **tue** au dépassement |

Les deux passent à `--no-optional-locks` : lock pris **0/5** au lieu de 5/5, kill dans la
fenêtre **0/15** au lieu de 15/15, **sortie strictement identique**.

Sur `loop_status`, l'option est posée **au foyer** (`Sources.git`), pas au site : un
`src.git("status", …)` ajouté demain est couvert d'office.

## 3. Le corrélat worktree : RÉFUTÉ, structurellement

Le corrélat rapporté (« la 3ᵉ occurrence est simultanée d'un `git worktree add` ») ne tient pas.

| bras | mesure |
| --- | --- |
| A — `worktree add`/`remove` **seuls**, 6 cycles, 20,6 s | `.git/index.lock` de l'arbre principal aperçu **0 fois sur 6 788 échantillons** (pas de 2 ms) |
| B — contention pure 3 écrivains + 3 lecteurs, 30 s, **sans kill** | 103 `status` + 154 `ls-files`, **0 erreur, 0 résidu** |
| A′ — même charge **+** worktree add/remove | 124 + 186, **0 erreur, 0 résidu** — aucun écart avec B |

C'est structurel, pas statistique : `git worktree add` écrit `.git/worktrees/<n>/index`, jamais
`.git/index`. La co-occurrence s'explique par le **hook `Stop`** — il se déclenche en fin de
tour, exactement quand l'orchestrateur dispatche un agent et merge une PR.

Autres pistes **éliminées** : `git gc --auto` / `git maintenance` ne touchent pas l'index ;
un handle tiers (antivirus) donnerait un lock **tenu**, pas libre ; la contention seule ne
produit rien (bras B).

## 4. La parade, et ce qu'elle n'est pas

`--no-optional-locks` supprime la prise du lock pour les commandes de **lecture**. Périmètre
**mesuré**, aucune extrapolation :

| commande | lock pris |
| --- | --- |
| `status` | **3/3** |
| `describe --dirty` | **1/3** |
| `diff`, `diff --quiet`, `diff --stat`, `ls-files`, `stash list`, `rev-parse`, `worktree list`, `for-each-ref`, `rev-list` | **0/3** |

⚠ **La parade n'est PAS « supprimer `index.lock` quand une commande échoue »** — ce serait
corrompre le dépôt le jour où un git tourne vraiment. `git add`/`commit` ne sont pas visés :
leur lock est une écriture voulue.

**Le discriminant, inchangé : libre ⇒ périmé, tenu ⇒ attendre — par ouverture EXCLUSIVE, jamais
par l'âge.** `os.open()`/`open()` de Python ne répondent pas à la question (ils réussissent sur
un fichier tenu) : il faut `CreateFileW` avec `dwShareMode = 0`.

## 5. #471-r2 — lien RÉFUTÉ

`git ls-files` **ne prend pas** `.git/index.lock`, et un lock résiduel ne le gêne pas.
Matrice mesurée de `git ls-files scripts/python/tests` :

| état | rc | message |
| --- | --- | --- |
| `index.lock` résiduel présent | **0** | (300 lignes rendues) |
| index absent | 0 | 0 ligne — le « rc=0 + liste vide » que le `CLAUDE.md` classe ROUGE |
| index verrouillé par un tiers | 0 | (lu quand même) |
| index tronqué | **0xC0000005** | crash (access violation) |
| index poubelle | **128** | `error: bad signature 0x42554f50` |
| worktree, gitdir disparu | **128** | `fatal: not a git repository: …/.git/worktrees` |

Éliminé aussi : contention lecteur/écrivain (**0 rc≠0 sur 340 invocations**, bras A+B) et
`git worktree add` tué (**0/8** — `git ls-files` y rend rc=0).

**Les deux symptômes ne partagent pas leur cause immédiate.** Le 128 de `probe_457:s3` a deux
chemins possibles restants — **gitdir disparu** ou **index corrompu** — et le message de
l'occurrence n'a pas été conservé (`check=True` d'origine). Depuis #471, `_git` **rapporte
stderr** : la prochaine occurrence portera son diagnostic. **Cause du 128 : toujours OUVERTE**
(résidu `#474-r1`).

## 6. Ce qui est livré

* `scripts/ratchets-bg.ps1`, `scripts/python/loop_status.py` — la fenêtre, fermée.
* `scripts/python/probe_474_optional_locks.py` — cliquet, 2 étages (AST + comportement du
  foyer), périmètre dérivé de `git ls-files scripts`, dans la banque.
* `scripts/python/probe_474_git_lock_forensics.py` — l'instrument : `--rapport`,
  `--veille` (capture l'occurrence suivante dans `logs/474-git-lock/`), `--purger` **explicite**,
  chaque suppression re-testée par ouverture exclusive juste avant.
* `tests/test_474_optional_locks_offline.py` (29) et `tests/test_474_forensics_offline.py` (4).

Le cliquet a **rougi sur son propre test** au re-jeu d'après rebase : la contre-épreuve
« un lock tenu est vu tenu » lançait un vrai `git status`. Corrigé en `git add -A` — qui prend
`index.lock` tout aussi réellement (8/8) et qui est **hors gisement par construction** (écriture
voulue). Aucune allowlist : exempter un fichier ruinerait un périmètre dérivé.

**L'instrument n'est branché nulle part** — c'est délibéré : le câbler dans un chemin critique
(hook, wrapper git) sans mesure préalable rejouerait le vice. Le point de branchement naturel
est le hook `Stop` / `loop_status`, qui lit déjà l'état du dépôt à chaque fin de tour et ne lève
jamais ; à décider séparément.

## 7. Résidus

* **`#474-r1`** — la cause du `128` de `probe_457:s3` reste **non tranchée** ; deux chemins
  mesurés y mènent, l'instrumentation pour la prochaine occurrence est en place.
* **`#474-r2`** — le taux réel de production du résidu dans la boucle n'est pas mesuré : il
  dépend de la fenêtre de l'arbre réel (1,2 s) et de la latence du tueur du harnais. La parade
  ne dépend pas de ce chiffre (elle supprime la fenêtre), mais il resterait à établir pour
  savoir si d'autres porteurs, hors dépôt, subsistent.
* Deux locks orphelins de **16 h** étaient encore présents à l'instruction
  (`objects/maintenance.lock`, `refs/heads/worktree-agent-ad12299b0b1be9235.lock`, 0 octet,
  libres) avec `gc.pid` pointant un **PID mort** — même signature, familles différentes :
  le kill n'épargne aucun lockfile.
