# #10023-r2 — L'ordre des builds archivés était le tri du NOM, et les deux ordres divergeaient déjà

**Critère binaire.** `archived_builds()` rend-il les builds dans un ordre **mesuré**, ou dans un
ordre qui *ressemble* à une chronologie ?

Avant ce cas : `sorted(SYMBOLS.iterdir())` — l'ordre du **NOM**. Or un hash de build est
**aléatoire**.

## 1. La prémisse du résidu était fausse, et dans le sens rassurant

Le backlog affirmait : « les quatre hashs versionnés (`gqfc5mff6c` < `kqkbjqfb6c` < `rnca9r7q6c`
< `t6dpr4k06g`) **se trouvent être dans l'ordre de sortie du jeu**, mais rien ne le garantit ».

Mesuré le 2026-08-18 — **c'est déjà faux** :

| build | entrée dans l'arbre (`git log --diff-filter=A`) | estampille `generated=` des tables `frida/` |
|---|---|---|
| `gqfc5mff6c` | 2026-07-25 (`8e591496`) | 2026-07-27T16:19:50 |
| `rnca9r7q6c` | 2026-07-29 (`b8dba3c0`) | 2026-07-29T13:08:41 |
| `kqkbjqfb6c` | **2026-08-06** (`630a9c59`) | **aucune table estampillée** |
| `t6dpr4k06g` | 2026-08-15 (`e1683b2e`) | 2026-08-15T00:15:00 |

`kqkbjqfb6c` entre **après** `rnca9r7q6c` et le tri par nom le place **avant**. La coïncidence sur
laquelle tout reposait avait cessé d'exister au moment où on l'écrivait — elle a été rompue par
`630a9c59` (#482-r3), qui archive ce build pour un usage tout autre : conserver l'empreinte
STRUCTURELLE d'un binaire avant sa disparition.

**Ce qui a sauvé le résultat, c'est un DEUXIÈME hasard**, indépendant du premier :
`probe_283.previous_build()` filtre sur la présence de `frida/enums.tsv`, et `kqkbjqfb6c` n'en a
pas — le binaire n'était plus là pour la produire. Le seul build mal classé était donc aussi le
seul écarté. Deux coïncidences empilées, aucune garantie.

## 2. La portée avait déjà fondu — mais pas disparu

La PR #1162 (#10023) a fait lire aux étapes 1-5 la **mémoire archivée** (`memoire_archivee`,
l'UNION de toutes les archives), insensible à l'ordre par construction. Restaient
ordre-dépendants :

- `previous_build()`, dont l'unique consommateur est `step_diff` (étape 0) ;
- le libellé `[283] build courant : X ; archives : A, B, C`.

Et `step_diff` **ne contribue pas au verdict** (`ko` ne reçoit pas son retour). Un couple inversé
n'aurait donc rien fait basculer — il aurait affiché un diff dans le mauvais sens, en le
présentant comme mesuré. C'est un défaut de **rapport**, pas de gate. Ce qui ne le rend pas
inoffensif : c'est exactement par un diff lu à l'envers qu'on conclut « 0 ordinal divergent »
alors qu'on compare le mauvais couple.

## 3. La réparation n'a demandé AUCUN fichier neuf

La date était déjà dans le dépôt. Chaque table `frida/*.tsv` porte en 1re ligne l'estampille de
provenance `#!il2cpp-provenance\tsha256=…\tbuild=…\tgenerated=<iso8601>\tsource=…`, et
`symbols_sync._reference_la_plus_recente` ordonnait **déjà** par là.

**La piste que le résidu proposait — « un champ explicite dans `BUILD` » — est REFUSÉE, et c'est
mesuré** : trois lecteurs font `(<rep>/"BUILD").read_text().strip()` et comparent au nom du
répertoire (`probe_916r1_effect_slots.py:111`, `test_963r4_areenemies_null_operand_offline.py:149`,
`symbols_sync.py:111`). Une deuxième ligne les aurait cassés. Le rayon de souffle d'un format
partagé se mesure avant de l'étendre.

Livré dans `symbols_layout` :

- `build_generated(build) -> str | None` — **tri-état**. `None` = pas mesurable, jamais une chaîne
  vide ni une date inventée. Les trois tables sont interrogées dans l'ordre, la première lisible
  fait foi (elles sortent de la même passe : horodatages identiques vérifiés sur les 3 builds).
- `builds_sans_date() -> list[str]` — **énumérable**, même patron que `builds_sans_table_enums` :
  un filtre muet redevient un faux vert.
- `archived_builds()` — clé de tri **totale et déterministe** `(pas de date ?, date, nom)`. Les
  non-datables finissent la liste **par convention de tri**, jamais présentée comme une mesure.

Dans `probe_283` :

- `previous_build()` **saute** les non-datables. Le piège est créé par la convention elle-même :
  les non-datés étant en fin, `reversed(...)` les visite **en premier**. Sans ce cran, le build le
  **moins** ordonnable serait élu « le plus récent ».
- Le libellé imprime l'horodatage de chaque archive, et `? NON DATE` là où il n'y en a pas.
- Le `DECLENCHEUR` de l'entrée `probe_283:diff` gagne `il2cpp_provenance.py` : le parseur
  d'estampille gouverne désormais l'ordre, donc le modifier peut changer `previous_build`.

**Le résultat ne change pas** — `previous_build()` rend `rnca9r7q6c` avant comme après. Il est
**fondé** au lieu d'être chanceux, et le test `etage3_..._reste_le_meme_qu_avant_la_reparation` le
fige pour qu'on ne puisse pas déplacer la référence du diff en silence.

## 4. Validation

`tests/test_10023r2_ordre_des_archives_offline.py`, **5 tests, 5 verts**. Deux étages construisent
leur propre arbre témoin (`aaa` le plus récent, `zzz` le plus ancien : le tri par nom rendrait
exactement l'inverse), et l'étage 1 **assertionne sa propre non-vacance** (`vu != sorted(vu)`) —
sans quoi un témoin où les deux ordres coïncident passerait pour vert.

**Contre-épreuve par mutation**, les deux rougissent :

| mutation | effet |
|---|---|
| tri par NOM restauré | **3 failed**, 2 passed |
| `previous_build` sans le filtre de date | **1 failed**, 4 passed |

Rejoués sans régression : `test_symbols_coverage_guard_offline.py` (18 passed), `probe_251`,
`probe_916r1`, `probe_283 --step diff` (PASS).

## 5. Ce que la tranche NE couvre PAS

- **`kqkbjqfb6c` reste non datable.** Sa position dans la succession des builds du JEU n'est pas
  dérivable du dépôt : il n'a jamais été écrit dans `CURRENT` (dont l'histoire versionnée ne porte
  que `rnca9r7q6c` → `t6dpr4k06g`), et ses deux tables (`ghidra/`, `fingerprints/`) ont une 1re
  ligne `# build=…` qui n'est pas le format de provenance. On le **nomme** au lieu de le classer.
- **Date d'ARCHIVAGE ≠ date de SORTIE du build.** L'estampille dit quand la table a été *produite*,
  pas quand le jeu a livré le binaire. Les deux coïncident tant qu'on dumpe à la migration ;
  `kqkbjqfb6c` est précisément le contre-exemple (build ancien, archivé tardivement).
- L'écrivain (`ghidra_symbols.py`) n'a pas été modifié : un futur build archivé **sans** table
  `frida/` rouvrira le même trou. Il sera alors **nommé** par `builds_sans_date()` au lieu d'être
  mal classé en silence — ce qui est le comportement voulu, pas une réparation complète.
