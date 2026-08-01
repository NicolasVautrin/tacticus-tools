# #409 — Le mur des cliquets : où passaient les ~160 s de `probe_273 --only-scan`

**Verdict : REDUCTIBLE, et réduit ~4x — sans toucher au verdict.** Le coût ne venait
d'aucun calcul coûteux : il venait de la **répétition**. Sortie strictement identique
(diff vide, rc identique) face à la version `origin/master`.

## 1. La mesure

Profil `cProfile` + chronos par étape, sur l'arbre `ad763de4` (1422 fichiers
`scripts/python/**`, 23 Mo, 2,51 M nœuds AST, 160 765 nœuds `Call`).

| Étape | Avant (série) |
|---|---|
| `step0` | 48,1 s |
| `step0b` | 9,8 s |
| `step0c` | 40,3 s |
| **total** | **~100 s** |

Ventilation (micro-benchmark, hors profileur) :

| Poste | Coût unitaire | Répétitions | Total |
|---|---|---|---|
| `open()` + `read()` de l'arbre | ~12-18 s | **3** (étapes 0, 0b, 0c) | ~45-54 s |
| `ast.parse` | 8,2 s | **2** (le balayage AST est joué par 0 **puis** par 0c) | ~16 s |
| `ast.walk` + évaluation | ~3 s / passe | **22** par AST (11 par balayage x 2) | ~30 s |

**L'`open()` est le poste dominant, et il n'est pas de notre fait** : ~9 ms par fichier,
contre 1,7 s pour lire les 23 Mo une fois ouverts (`read()` seul). C'est un filtre au
niveau du système (antivirus sur `CreateFile`) — **mesuré identique dans l'arbre principal
et dans un worktree**, donc ni un artefact d'isolation ni quelque chose que le probe
puisse corriger. Ce qu'il peut corriger, c'est le **nombre** d'ouvertures.

## 2. Ce qui a été fait (`probe_273_gitignored_inputs.py`)

Cinq changements, tous de structure — les trois étapes posaient la même question à
l'arbre et la recalculaient chacune :

1. **`_sources()`** — une seule lecture, partagée par 0, 0b et 0c, **parallélisée**
   (l'`open()` bloque hors GIL : 16 threads, ~18 s -> ~7 s).
2. **`_file_infos()`** — un seul `ast.parse`, mémoïsé par `scan_root`.
3. **`_FileInfo`** — les 4 buckets (alias / assignations / `import … from` / candidats)
   remplis en **une** passe `ast.walk`, ordre de visite conservé (le point fixe en dépend).
   `_fragment_ids` part des **candidats** : `_base_of` rend `None` partout ailleurs, les
   autres nœuds ne coûtaient qu'une traversée.
4. **`_scan_repo_paths` mémoïsé** — les étapes 0 et 0c posaient la MÊME question.
5. **`_call_tail()`** remplace `ast.unparse(node.func).split(".")[-1]` sur le chemin chaud
   (160 765 nœuds `Call`, revisités à chaque `walk`).

Un point de sémantique à ne pas perdre : les deux lecteurs ne lisaient **pas pareil** —
0b en `errors="replace"` (tolérante), le balayage AST en strict (fatal, la
`UnicodeDecodeError` n'étant rattrapée par aucun des deux `except`). `_decode` conserve
l'erreur stricte pour que `_file_infos` la re-lève **au même moment qu'avant** : partager
la lecture ne doit pas transformer un plantage en silence.

## 3. Après

| | Avant | Après |
|---|---|---|
| Mesure isolée (machine peu chargée) | **112,7 s** | **24,1 s** |
| 3 mesures alternées (3 agents en vol) | 100,1 / 153,9 / 221,9 s | 33,2 / 49,0 / 49,5 s |
| Sortie | — | **strictement identique** (6 runs, diff vide, rc=0) |

Le mur des 9 cliquets en parallèle n'est donc plus `probe_273` : `pytest signatures`
(~59 s en série) reprend la tête.

Ventilation du coût **restant** (~24 s) : lecture ~1-15 s selon l'état du cache système,
`ast.parse` ~8 s, `ast.walk` + buckets ~4 s, tout le reste < 1,5 s.

## 4. Le plancher, et pourquoi l'incrémental ne tiendrait pas le verdict

`ast.parse` de 23 Mo (~8 s) est le plancher dur : on ne peut pas décider quels fichiers
sauter sans un critère textuel — donc une heuristique, donc un verdict affaibli.

**Un balayage borné aux fichiers touchés rendrait un verdict DIFFÉRENT**, pour deux
raisons indépendantes :

* le point fixe est **inter-fichiers** — une racine se propage de module à module
  (`from rl_gen_ref_tables import ROOT`, `import runner as R` puis `R.BOARDS_DIR`), donc
  éditer un fichier peut changer le chemin résolu dans un **autre** ;
* `_check_allowlist_live` (les deux sens du cliquet : entrer oblige à se justifier, ne
  plus s'appliquer oblige à sortir) exige la vue **globale** — une exception « morte » ne
  se voit qu'en balayant tout.

Non livré, donc, et à ne pas tenter sans lever ces deux points.

## 5. Trouvé en chemin : le self-test de `probe_273` était MORT

`probe_319_scan_fidelity.py` — dont tout l'objet est de prouver que le cliquet #273 mord
encore — **crashait à sa ligne 68** (`AttributeError: _root_vars`), avant le premier
contrôle. Il RÉIMPLÉMENTAIT l'ancien balayage contre deux helpers que `probe_273` n'a plus
depuis que son évaluateur résout les chemins au lieu de reconnaître des formes par le
texte. Ni fidélité, ni déterminisme, ni les six mutations ne tournaient.

Derrière, une **seconde** panne que la première masquait : le montage était périmé
vis-à-vis de #349. `_fresh_tree` montait un `git init` nu, sans `data/` versionné ;
l'étape 0c refuse (à raison) de conclure contre un référentiel vide et rendait `rc=1` sur
**tous** les cas. Vérifié en rejouant le même montage avec le `probe_273` de
`origin/master` : identique. Donc les quatre cas « attendu ROUGE » passaient **pour la
mauvaise raison**, et les deux « attendu VERT » étaient impossibles.

Réparé : le probe demande sa vue non filtrée à `probe_273` lui-même
(`_scan_paths(drop_fragments=False)`) — plus rien à réimplémenter, plus rien à périmer —
et `_fresh_tree` pose les quatre entrées `data/` versionnées (`git add` suffit :
`git ls-files` lit l'INDEX) plus les six consommateurs qui portent `_ALLOWED_DATA`.

Ajouté :

* **étape 2bis** — les trois raccourcis de #409 qui *calculent* autrement (les autres ne
  font que moins souvent) sont confrontés à leur forme d'origine, **exhaustivement** :
  `_call_tail` vs `ast.unparse` (160 811 nœuds, **0** divergence), `_fragment_ids` depuis
  les candidats vs depuis tous les nœuds (1422 fichiers, **0**), `_decode` vs
  `Path.read_text` (CRLF / CR seul / BOM / form feed / utf-8 invalide / vide, levée en
  strict comprise) ;
* **deux mutations pour l'étape 0c**, que `probe_319` ne couvrait pas du tout : une sortie
  de run dans `data/` doit rougir, une lecture d'entrée VERSIONNÉE doit rester verte.

`probe_319` : **rc=0, 8 cas de mutation sur 8**, et « arbre non muté » est VERT — c'est
précisément ce qui rend les cinq ROUGE interprétables.

## 6. Reproduire

```
python scripts/python/probe_273_gitignored_inputs.py --only-scan   # le cliquet
python scripts/python/probe_319_scan_fidelity.py                   # son self-test
```

Équivalence contre une révision antérieure (c'est ainsi que celle-ci a été prouvée) :

```
git show <ref>:scripts/python/probe_273_gitignored_inputs.py > <tmp>/probe_ref.py
git show <ref>:scripts/python/host_inputs.py                 > <tmp>/host_inputs.py
python <tmp>/probe_ref.py --only-scan --scan-root <racine>   # diff avec la version courante
```
