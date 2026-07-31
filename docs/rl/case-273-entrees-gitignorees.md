# case-273 — Huit lecteurs rendaient « aucune trace » sans jamais regarder au bon endroit

> **Verdict** : `frida/data/ai-traces` et ses voisins gitignorés sont écrits par le HOST dans
> **son** arbre ; un worktree y résolvait dans le vide, et `Path.glob()` sur un chemin
> inexistant **rend `[]` sans lever**. La résolution passe désormais par
> `scripts/python/host_inputs.py` : arbre local, puis **arbre principal** du dépôt
> (`git rev-parse --git-common-dir`), avec convention **tri-état** — une levée pour
> « pas mesuré », `[]` pour « mesuré et vide ».

## 1. Le mécanisme, et pourquoi il est pire qu'un fichier absent

`frida/host/ai-trace-store.ts` écrit sous `path.resolve(process.cwd(), "data", "ai-traces")`,
avec `process.cwd()` = `frida/` de l'arbre d'où le host a été lancé — l'arbre **principal**.
Les lecteurs, eux, construisaient `ROOT / "frida" / "data" / "ai-traces"` où `ROOT` est la
racine de **leur** checkout.

Le mode de panne n'est pas une exception, et c'est tout le problème :

```
>>> Path("C:/.../worktree/frida/data/ai-traces").exists()
False
>>> list(Path("C:/.../worktree/frida/data/ai-traces").glob("*.jsonl"))
[]                       # AUCUNE levee
```

Pas de `KeyError`, pas de `FileNotFoundError`, rien. Le script conclut « aucune trace » et rend
un résultat d'apparence normale. C'est un **capteur mort qui se présente comme une mesure** —
et l'inverse exact de #254b-a, où la panne, elle, était au moins bruyante (`KeyError`).

## 2. Le relevé, RE-DÉRIVÉ (pas repris)

`probe_273_gitignored_inputs.py` étape 0 balaie par AST tous les chemins construits depuis une
racine dérivée de `__file__` dans `scripts/python/**`, puis les confronte à
`git check-ignore -z --stdin`. Mesure sur `origin/master` @ `a860047e`, dans un worktree créé à
l'instant :

| | compte |
|---|---|
| occurrences | 1 203 |
| chemins distincts | 189 |
| dont **gitignorés** | 117 |
| — **SORTIES** sous `logs/` (conformes, non touchées) | **110** |
| — **ENTRÉES** | **7** |

Les 7 entrées, et leurs lecteurs :

| entrée | lecteurs |
|---|---|
| `frida/data/ai-traces` | `engine_agreement_stages`, `inspect_ai_trace`, `probe_32_casttile`, `probe_49g_l3tiles`, `probe_57k_l3`, `rl_collect_batch`, `rl_ingest_postgres` (+ `diag_summoner_crash`, **variable morte**) |
| `frida/data/rl-batches` | `rl_collect_batch`, `rl_ingest_postgres` |
| `frida/data/meta` | `probe_269_stream_events_source` |
| `.env` | `rl_collect_batch`, `rl_gen_enum_columns`, `rl_gen_ref_tables`, `rl_ingest_postgres` |
| `frida/assets/raw`, `frida/assets/raw/Bundles`, `frida/assets/public` | `build_asset_manifest` |

Deux écarts avec le relevé hérité de #254b-a, qui valent d'être dits : le balayage y voyait
**4** lecteurs d'`ai-traces` là où il y en a **8** (`inspect_ai_trace` construit sa racine
**en ligne**, sans passer par une variable ; `probe_57k_l3` et `rl_collect_batch` n'étaient
pas listés), et `.env` a **4** lecteurs et non 3 (`rl_gen_enum_columns` **importe** `ROOT`
d'un autre module). Un balayage par nom de variable rate ces deux formes **en silence** —
c'est le même défaut que celui qu'on corrige, un cran plus haut.

## 3. L'arbitrage — le coût accepté, dit

Deux voies étaient ouvertes.

**(b) lever en NOMMANT le répertoire attendu.** Zéro hypothèse de déploiement, message
pédagogique. **Insuffisante seule** : elle laisserait `probe_32`, `probe_49g`, `probe_57k`,
le LEVER 3 d'`engine_agreement_stages` et `rl_ingest_postgres --all` **inutilisables depuis
un worktree** — c'est-à-dire pour toute la population qui les fait tourner. On échangerait un
faux négatif silencieux contre un blocage franc : mieux, mais pas assez.

**(a) pointer explicitement l'arbre principal.** **Retenue**, et elle ne demande **aucun
chemin en dur** : `git rev-parse --path-format=absolute --git-common-dir` rend `<main>/.git`
depuis n'importe quel worktree lié. C'est la voie git native, elle survit au déplacement du
dépôt, et elle est **vraie par construction du déploiement** — un seul host tourne, lancé
depuis `frida/` de l'arbre principal, et un worktree n'en lance jamais (réinjection et restart
du host sont proscrits aux agents).

**Le coût accepté** : on inscrit dans le code l'hypothèse « le host écrit dans l'arbre principal
de CE dépôt ». Trois contreparties la rendent tenable :

* elle est **RENDUE, pas tacite** — `Resolved.origin` vaut `local` ou `main-worktree`, et les
  appelants l'impriment (`ai-traces dir : …/frida/data/ai-traces [main-worktree]`). L'hypothèse
  se lit à chaque run ;
* elle est **débrayable** — `TACTICUS_HOST_DATA_ROOT` pointe un arbre tiers. **Exclusif** :
  posé, il est le seul candidat. Retomber en silence sur un autre arbre quand il n'y est pas
  reviendrait à re-fabriquer la panne ;
* **quand elle échoue, (b) s'applique** — plus aucun candidat n'existe ⇒ `HostInputUnavailable`,
  qui nomme les chemins essayés, **qui** remplit le répertoire, **comment** (`aiTraceEnable`,
  `rl_collect_batch`, …) et l'échappatoire.

Ce qui reste **hors d'atteinte, et c'est nommé** : aucun consommateur ne *demande* au host où
il écrit. `aiTraceStoreStatus()` porte pourtant le `dir` absolu — il n'est exposé par aucune
route HTTP. L'exposer donnerait une résolution **mesurée** plutôt qu'inférée, au prix d'un
rebuild + restart du host, proscrit ici (backlog `#273-r`).

## 4. La convention tri-état

```
levée  = PAS MESURE   -- aucun candidat n'existe, on regarde dans le vide
[]     = MESURE, VIDE -- le repertoire est la, aucun fichier ne matche
[...]  = MESURE, PLEIN
```

`host_inputs.find()` ne rend **jamais** `[]` pour cause de répertoire absent. `resolve()`, elle,
ne lève jamais et rend `path=None` — pour les appelants qui doivent dégrader plutôt qu'échouer.

Les appelants ont été câblés **selon ce qu'ils peuvent offrir**, pas uniformément :

| consommateur | PAS MESURE | MESURE et VIDE |
|---|---|---|
| `probe_32`, `probe_49g` | message + **rc 5** | message + rc 4 (inchangé) |
| `probe_57k_l3` | **propage** la levée (pas de résultat dégradé à offrir) | `None` + message |
| `inspect_ai_trace` | **rc 2** | **rc 1** (« Demarre le host ») |
| `engine_agreement_stages` (LEVER 3) | `None` + **message une fois** — lever tuerait tout le run d'agreement, or LEVER 3 est auxiliaire | `None`, silencieux |
| `rl_collect_batch` | **rc 2 avant le premier build** — un batch qui collecte sans savoir où sont les traces est une collecte perdue | n/a |
| `rl_ingest_postgres` | **rc 2** | rc 1 (« lance rl_collect_batch ») |
| `probe_269` étape 1 | `NON VERIFIEE` (déjà conforme avant) | idem |

`.env` reçoit le même traitement : `rl_ingest_postgres` distinguait déjà l'échec, mais son
message — « PG_PASSWORD vide dans .env » — accusait le **contenu** d'un fichier qui, en
worktree, n'existait pas. `rl_collect_batch`, lui, se contentait d'un `[ingest] PG_PASSWORD
vide — ingestion desactivee` sur stderr : le batch tournait, collectait tout, et **n'ingérait
rien**.

## 5. Validation

**La preuve demandée — worktrees créés à l'instant, hors de l'arbre principal (`%TEMP%`),
même host (session 27), même instant.**

| mesure | AVANT (`origin/master`) | APRÈS |
|---|---|---|
| `inspect_ai_trace._list_sources(None)` | **0 fichier** annoncé comme mesure, + « Demarre le host » alors que le host TOURNE | **25 fichiers [MESURE]** |
| `inspect_ai_trace(main, chemin bidon)` | rc **1** (confondu avec « rien à inspecter ») | rc **2** (PAS MESURE, distinct) |
| `probe_57k_l3._trace_file(27)` | `None` → « AUCUN fichier trace » | `…/ai-traces/27-2026-07-30T04-49-43-047Z.jsonl` — la trace de la session **courante** |
| `rl-batches` `batch-*.json` | `[]` → `rl_ingest --all` ingérait **zéro** batch | **38 summaries** |

**Le cliquet** — `probe_273` étape 0 fait échouer toute entrée gitignorée lue depuis la racine
sans passer par `host_inputs` :

| arbre | rc | entrées non résolues |
|---|---|---|
| `origin/master` @ `a860047e` | **1** | `.env`, `frida/data/ai-traces`, `frida/data/meta`, `frida/data/rl-batches` |
| cette branche | **0** | aucune (3 restantes, toutes qualifiées dans `_ALLOWED`) |

**Gardes et mesures**

| mesure | résultat |
|---|---|
| `pytest tests/test_host_inputs_offline.py` (garde neuve, offline) | **14 passed** |
| `pytest tests/test_stream_events_offline.py` (garde #254b-a, dépendance) | **16 passed** |
| `probe_273` étapes 0-3 | rc **0** |
| `probe_269 --state-file <abs>` (offline + live) | étape 0 OK ; **étape 1 VÉRIFIÉE** — `StepType` 62/62, `GroupType` 104/104, **0 divergence** ; étape 2 live 389 events, `UnitDamaged` 20/20, `RemoveUnit` 1/1, `ReceiveEffect` 29/29 → **CONFORME** |
| `rl_duel build --seed 777 --board MC1_67` + `act move` + `aiturn` | rc **0** / **0** / **0**, cascade décodée |
| `engine_agreement_stages --build --seeds 777 --steps 4` | **4/4 EXACT**, prédiction 1/1, utilité 1/1, ability 100 %, move 100 % |

L'étape 1 de `probe_269` est **discriminante et neuve** : elle était perpétuellement
« NON VERIFIEE » depuis un worktree — l'artefact host n'y étant jamais visible, la comparaison
qui justifie d'avoir choisi la table versionnée ne pouvait **jamais** être rejouée par un agent.
Elle l'est maintenant, et elle dit 0 divergence.

## 6. Ce qui n'est PAS couvert

* **Le chemin LEVER 3 n'a pas été exercé LIVE.** `_l3_native_terms` n'appelle `_trace_file` que
  sous `--l3`, qui est **session-globale** et proscrite tant qu'un autre agent walke l'IA. Les
  quatre branches (introuvable / présent-vide / présent-avec-la-trace / trace d'une AUTRE
  session) sont couvertes **offline** par `test_lever3_degrade_sans_lever_mais_le_DIT`.
* **Deux entrées restent des chemins locaux**, toutes deux dans `build_asset_manifest.py` et
  qualifiées dans `probe_273._ALLOWED` : `frida/assets/public` est une **SORTIE** (`mkdir` +
  écriture) ; `frida/assets/raw/Bundles` est le **repli** d'une entrée dont la source primaire
  est l'installation du jeu (`TACTICUS_INSTALL`, hors dépôt) — `_bundle_dir` la résout par
  `host_inputs`, mais la constante subsiste et les appelants se contentent d'un
  `[warn] missing`. Outillage one-shot, aucun consommateur de mesure ⇒ admis, pas oublié.
  (Une troisième, `frida/assets/raw`, a longtemps figuré ici : c'était un **fragment**
  fabriqué par le balayage, pas un chemin du script — cf. §7.)
* **`scripts/node/verify_portraits.mjs`** lit `frida/assets/public/*.json` en chemin **relatif
  au cwd** : hors du périmètre balayé (`scripts/python/**`), non traité.
* **Le balayage ne voit que les chemins STATIQUES.** Un segment dynamique (`ROOT / "logs" /
  f"{tag}.json"`) est tronqué à son préfixe littéral, et un chemin entièrement calculé lui
  échappe. Le cliquet est donc une garde, pas une preuve d'exhaustivité.
* **La péremption d'une trace n'est pas détectée.** Les globs sont indexés par `sid`, et les
  `sid` repartent à 1 au redémarrage du host : un `27-*.jsonl` d'un déploiement antérieur
  matcherait. Le risque est **inchangé** par ce cas (il existait déjà dans l'arbre principal),
  et les appelants prennent le plus récent par `mtime` dans une fenêtre de `seq` — mais il n'est
  pas fermé.

## 7. #319 — le cliquet mesurait mal, des deux côtés

Le garde-fou de ce cas s'est fait prendre à son propre motif : il **rendait un verdict qui ne
décrivait pas le dépôt**. Deux défauts indépendants, tous deux corrigés dans
`probe_273_gitignored_inputs.py`, tous deux gardés par `probe_319_scan_fidelity.py`.

**(a) Il comptait des chemins que personne ne construit.** `ast.walk` visite les
sous-expressions : sur `ROOT / "frida" / "assets" / "raw" / "Bundles"`, il rendait aussi
`frida/assets/raw`, `frida/assets` et `frida`. Le balayage signalait donc `frida/assets` comme
une **ENTRÉE lue par `build_asset_manifest.py`** — qui ne la nomme nulle part (il n'a que `RAW`
et `PUBLIC`). Le scan ne retient plus que les expressions **maximales** (`_fragment_ids`).
Mesure : 228 → 202 chemins distincts, **26 fragments** éliminés, **0 orphelin** (tout fragment
reste couvert par un chemin maximal qui le préfixe). L'entrée `_ALLOWED` `frida/assets/raw`, dont
la justification disait littéralement « préfixe de RAW », était l'aveu du défaut : elle est
**retirée** — une exception se supprime quand sa cause est corrigée.

**(b) Son verdict dépendait de l'état du DISQUE — donc il était vert là où l'on travaille.**
Une règle `.gitignore` à slash final (`frida/assets/`, ligne 41) est **directory-only** : git ne
l'applique que s'il voit un répertoire, ce qu'il déduit du disque. `frida/assets/` existe dans
l'arbre principal et **pas** dans un worktree frais, d'où :

| arbre | `git check-ignore frida/assets` | verdict du cliquet |
|---|---|---|
| arbre principal (répertoire présent) | ignoré | **rc 1**, `[FAIL] frida/assets` |
| worktree frais (répertoire absent) | non ignoré | **rc 0**, chemin invisible |

C'est le motif de ce cas retourné contre son propre garde-fou : *un verdict qui dépend d'un
répertoire absent se lit « rien à signaler »*. Conséquence directe et observée — un agent a
rapporté « probe_273 : OK » de **bonne foi** depuis son worktree, en contradiction avec le rouge
de l'arbre principal. `_check_ignored` interroge désormais git **deux fois**, chemin nu et chemin
suffixé `/`, et retient l'**union** : un chemin statique ne dit pas s'il désigne un fichier ou un
répertoire, l'union est la seule réponse indépendante du checkout, et elle penche du côté
fail-loud.

**Le cliquet mord dans les deux sens.** `_check_allowlist_live` fait maintenant échouer toute
entrée d'`_ALLOWED` / `_ALLOWED_ABS` qui ne correspond plus à aucun chemin balayé. Sans lui, une
allowlist ne fait que croître : la ligne survit à la correction qui l'a rendue inutile, et plus
personne ne sait laquelle couvre encore un cas réel. Entrer oblige à se justifier ; ne plus
s'appliquer oblige à sortir. Ce contrôle n'est exploitable que **parce que** (b) est corrigé —
tant que le verdict dépendait du disque, une entrée pouvait paraître morte en worktree et vivante
dans l'arbre principal.

**Ce que #319 ne corrige pas** : le balayage reste statique (un chemin entièrement calculé lui
échappe, cf. §6) et son périmètre reste `scripts/python/**`. Il garantit désormais que ce qu'il
signale existe vraiment, et qu'il le signale partout de la même façon — pas qu'il voit tout.

## 8. L'invariant 3 du `CLAUDE.md`

Il dit aujourd'hui : « un worktree frais est RUNNABLE par son seul checkout ». C'est vrai des
**entrées versionnées** (`data/symbols`, `data/boards`, `data/seed-bc.json`, `data/i2_en.json`)
et des **sorties** (`logs/`, qui meurt avec le worktree). Ce cas ne le rend pas faux : il en
nomme la **troisième** catégorie, que l'invariant passait sous silence — les artefacts écrits
par un **processus hors du checkout** (le host Node) ou par l'utilisateur (`.env`). Ceux-là ne
seront jamais dans un checkout, et c'est correct. Ce qui doit être vrai, c'est qu'un lecteur
sache **dire** qu'il ne les voit pas plutôt que rendre un zéro. La reformulation est du ressort
de l'auteur du `CLAUDE.md` ; ce fichier n'en propose que la matière.

## 9. #349 — le troisième angle : la SORTIE écrite dans `data/`

Même invariant, angle distinct des deux premiers : le chemin est **relatif** (donc invisible à
l'étape 0b, qui ne voit que les absolus vers l'arbre principal) et `data/` **n'est pas
gitignoré** (donc hors du verdict de l'étape 0). Une sortie qui y atterrit salit `git status`
sans qu'aucun fichier n'ait été édité — c'est-à-dire qu'elle brouille le **signal même** dont
l'isolation par worktree se sert comme garde-fou.

**Mesure** (balayage `scripts/python/**` sur `origin/master` @ `ac88bc47`) : **25 sites sur 19
fichiers** — 15 probes et 4 tests live, soit des state-files de runner, des seed BC augmentés et
trois dumps de probe. Résidu de la migration `f467e64`, qui n'avait déplacé que les sous-répertoires
`data/rl-state[s]` et `data/selfplay-logs`, pas les fichiers posés à la racine de `data/`. Tous
déplacés sous `logs/runners/` (ou `logs/` pour les dumps). Hors Python, un appelant faisait la
même chose : `.claude/workflows/tacticus-selfplay.js` construisait `data/_sp_<seed>_{A,B}.json`
à chaque match.

**Cliquet — étape 0c de `probe_273 --only-scan`.** Verdict : le premier segment sous `data/`
doit être une entrée que **git suit**, dérivé de `git ls-files data` et jamais d'une liste en
dur. `data/symbols`, `data/boards`, `data/seed-bc.json` et `data/i2_en.json` sont donc verts
d'office — y compris quand la chaîne de symboles y **écrit** (`preprocess_il2cpp_dump`,
`ghidra_symbols`, `symbols_sync`, `symbols_layout` : 82 chemins balayés, 0 faux positif). Les
**7** chemins `data/` non versionnés qui restent sont des **lectures** d'entrées locales (dump
IL2CPP, instantané gameconfig, spawn-probe), justifiées dans `_ALLOWED_DATA`.

**Refus au choke point, en plus du cliquet statique** — celui-ci ne balaye que
`scripts/python/**`, et le vecteur JS le prouvait : `rl_duel --state-file`,
`catalog_inject --out` et `write_augmented_seed_bc()` **refusent** désormais un chemin sous
`data/` (`host_inputs.reject_data_output`, rc 2, message actionnable).

**Le balayage a été réécrit en évaluation concrète** (`_Eval` : `__file__` vaut le fichier
balayé, donc `.parent`, `.parents[N]`, `os.path.dirname/join`, `Path()`, `str()`, les variables
module **et** locales, et `import x as R` puis `R.VAR` se résolvent). L'ancien reconnaissait des
**formes par le texte** et ratait `DATA = PYDIR.parent.parent / "data"` — le motif même de #349 —
ainsi que `PYDIR / ".." / ".." / "logs"` (segment `..` non normalisé, deux sorties conformes
classées « autre »).
