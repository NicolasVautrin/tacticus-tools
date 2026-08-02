# `#449-r2-r5` — audit « périmètre DÉRIVÉ vs SAISI » des 30 entrées de la banque

Le motif : **le critère ou le périmètre d'un cliquet est SAISI (un littéral recopié dans le probe)
au lieu d'être DÉRIVÉ (lu d'une source qui bouge avec le code)**. Un garde saisi devient
silencieux au moment précis où le code évolue — c'est-à-dire au moment où il sert.

Déjà trouvé **trois** fois (#421 liste manuelle citant un nom mort ; #426 périmètre du garde saisi ;
#440 tuple d'exclusion qui n'excluait rien), une quatrième avec `#449-r2-r5` (le défaut de
signature codé en dur). Cet audit balaie les **30** entrées de `scripts/ratchets.ps1`.

## Le critère, énoncé avant la méthode

> **Si je rouvre dans le code le trou que ce cliquet garde, sans toucher au probe, rougit-il ?**

* **DÉRIVÉ** — la référence est lue d'une source qui évolue avec le code : AST des sources,
  `data/symbols/<build>/**`, `git ls-files` / `git check-ignore`, `ratchets.ps1` lui-même,
  introspection d'un registre Python.
* **SAISI** — la référence est un littéral (liste de noms, valeur attendue, chemin, ordinal, défaut,
  tuple d'exclusion) que rien ne re-dérive.
* **ATTESTATION ≠ SAISI fautif.** Un fait **lu au décompilé natif**, inscrit avec sa raison, est
  légitimement saisi : le décompilé n'est pas dans le dépôt. Est fautif de saisir un fait
  **dérivable mécaniquement du dépôt**. Une allowlist courte **gardée dans les deux sens** (le probe
  rougit si une entrée ne désigne plus rien) est également légitime.

## Inventaire

| entrée | verdict | ce qui est saisi, et ce que ça laisse passer |
|---|---|---|
| `probe_181` | **DÉRIVÉ** | itère `ABILITY_CLASSES` importé du moteur, `getattr(cls, "TARGETING_OPTIONS")` — l'accès exact de la production |
| `probe_120` | MIXTE | `NORMAL_ATTACK_KIND = 0x3f5` **réinjecté par le probe** au lieu de passer par l'appelant de production |
| `probe_273` | MIXTE (dominante dérivé) | référence = `git check-ignore` + `git ls-files data` ; 3 allowlists **gardées**. Saisis : `_OUTPUT_ROOTS = {"logs","app"}` **non gardée**, le périmètre `scripts/python/**`, le nom du dépôt dans `_ABS_REPO` |
| `probe_319` | MIXTE | dérive l'« avant » en appelant `probe_273` lui-même. Saisi : `_CASES`, liste manuelle de 8 mutations qui **ne se dérive pas** des étapes de 273 |
| `probe_365` | MIXTE | critère dérivé (`git ls-files` + `git check-ignore`) ; **corpus** saisi : `frida/**/*.ts` uniquement |
| `probe_391` | **DÉRIVÉ** | dérive du disque tous les couples porteurs du motif ; identité mesurée sur l'**objet** `Directory` ; 0 couple ⇒ `return 1` |
| `probe_313` | MIXTE (dominante dérivé) | référence = `enums.tsv` du build courant ; registre **gardé dans les deux sens**. Saisis : `PAR_CLS` indexé par **nom court** de classe, `HORS_MIRROR` non gardée, `BASES_ENUM` |
| `probe_449r2` | **DÉRIVÉ** (corrigé ici) | était SAISI : défauts codés en dur. Désormais périmètre + défaut + position + gate dérivés ; ne restent que les **attestations** natives |
| `probe_229` | MIXTE | `RAIL` est une attestation légitime ; `ARRAYSET_READS_BY_TREE` exempte 3 classes — l'existence de la classe est gardée (par 421), **la motivation ne l'est pas** |
| `probe_421` | **DÉRIVÉ** | compare les clés de `probe_229` au registre `EFFECT_TRIGGERS` sur 4 axes dérivés |
| `probe_366camo` | MIXTE | périmètre dérivé (surcharges de `is_active`) ; `POSE_VECTOR` est une attestation, mais **sans garde de fraîcheur** (pas d'`orphan` façon 421) |
| `probe_366pos` | MIXTE, **critère saisi** | 5 regex `PORTS` + un jeu de marqueurs `GATES` |
| `probe_366bcp` | MIXTE (dominante dérivé) | deux recensements AST avec point fixe, `check_reader` garde le foyer. Saisis : `PATCH_CALLS` **non gardée**, `_COVERAGE_HOLES`/`_UNRESOLVED_PATCHES` non gardées contre l'orphelinat |
| `probe_440` | MIXTE (R1/R2 dérivés) | tout se dérive du chemin canonique et de `ratchets.ps1` ; saisie : `_ECRITURES`, table d'API stdlib **incomplète** |
| `probe_274` | MIXTE (dominante dérivé) | ordinaux lus d'`enums.tsv`, exclusion worktrees **relative**, table JS gardée. Saisis : `_KEYS`, `ALLOWLIST`, périmètre `.py` + **un seul** fichier JS |
| `probe_443r1c` | **DÉRIVÉ** | indices confrontés aux ordinaux d'`enums.tsv` (build courant **et** archivé), périmètre dérivé de `probe_283` |
| `probe_443r2` | MIXTE, **critère saisi** | inventaire dérivé, mais le **régime de chaque substrat** est la table littérale `SUBSTRATS` — rien ne lit le corps des fonctions |
| `probe_443r2b1` | MIXTE | [A]–[E] appellent le vrai code = dérivés ; [F] balaie un `glob("*.py")` **non récursif** + exclusion par préfixe de nom |
| `probe_455` | **DÉRIVÉ** | n'compare à aucun littéral : il **exerce** le vrai garde, le rejoue en sous-processus, et prouve le câblage en copiant le `conftest.py` de production ; hooks dérivés par `dir(G)` |
| `probe_431` | **SAISI** | `EXEC_GLOBS` appliqué par `Path.match`, **qui n'étend pas `**` récursivement** |
| `pytest_signatures` | MIXTE | garde 1 dérivée (`inspect.signature`) et auto-gardée ; garde 2 **saisie** : 2 factories et 2 paramètres sur les 20 du port |
| `pytest_attestations` | MIXTE | vérifie la **ligne morte** (symbole présent dans les symboles re-dérivés, fichier, ancre, citation) ; croit sur parole la **substance** (cliquet = `nom in src`, un substring à l'échelle du fichier) |
| `pytest_adjacency` | MIXTE | les littéraux natifs sont des attestations et chaque assertion porte sa contre-épreuve par monkeypatch ; la **liste des foyers gardés** est manuelle (5 formes, 5 nœuds importés nommément) |
| `probe_283:diff` | compteur, **déclaration juste** | `step_diff` sans `ko +=` |
| `probe_283:mirror` | MIXTE | référence dérivée d'`enums.tsv` ; **périmètre `ENUMS` saisi** |
| `probe_283:exec` | MIXTE | référence dérivée ; **critère de détection saisi** (`_ROOTS`, 14 sous-chaînes de noms de variables) |
| `probe_283:tables` | MIXTE | référence dérivée ; **sélection saisie** (`_TAB_SEQ_NOM`, `_SUFFIXES`) |
| `probe_283:prose` | MIXTE | critère **entièrement dérivé** ; **périmètre saisi** (`--racine` par défaut `scripts/python`) |
| `probe_283:on` | compteur, **déclaration juste** | le slot `0x4d|0x50` est une attestation native |
| `probe_439` | MIXTE (liste dérivée, 1 saisi réel) | liste dérivée **deux fois** de `ratchets.ps1` avec accord bidirectionnel (30 == 30) ; défauts d'argparse lus de l'AST. Saisi : `cibles[0]` |

**Bilan : 6 DÉRIVÉ net, 1 SAISI, 21 MIXTE, 2 compteurs justes.**

## Les cinq risques HAUTS, par ordre de traitement

Aucun n'est corrigé ici (hors périmètre du cas) ; chacun porte sa mutation reproductible.

### 1. `probe_431` — périmètre littéral **et** sémantiquement cassé (mesuré)

`EXEC_GLOBS` est appliqué par `Path(rel).match(g)`, et **`PurePath.match` n'étend pas `**`
récursivement** (il se comporte comme `*`). Mesure : **1577** `.py` suivis sous `scripts/`, dont
**677** atteints par le glob ⇒ **900 fichiers hors périmètre effectif**, dont l'intégralité de
`scripts/python/engine/**` et `scripts/python/tests/**`. Ils ne tombent pas non plus dans la face
PROSE (`.py` absent de `PROSE_EXT`) : ils ne sont **dans aucun seau**. Même trou pour
`frida/hooks/index.ts` (racine du glob) et toute profondeur ≥ 3 sous `frida/host/`.

> **Mutation** : écrire `data/symbols/gqfc5mff6c/frida/functions.tsv` dans n'importe quel fichier
> sous `scripts/python/engine/` → résolution d'artefact par un hash périmé, `symbols_sync`
> aveugle, `probe_431 --cliquet` **VERT**. **316** de ces 900 fichiers citent déjà un hash.
> Correctif : `full_match` (3.13+) ou `fnmatch` sur le chemin POSIX.

### 2. `probe_283:*` — `ENUMS` est mécaniquement dérivable, et se périme quand il sert

`ENUMS` (les 4 enums renumérotés) est **le résultat exact d'un calcul que le fichier sait déjà
faire** : mesuré sur les deux tables versionnées, 2194 enums communs, 39 dont la table change,
**exactement 4** avec un membre renuméroté — `UtilityType` (73), `EventTriggerType` (36),
`StepType` (55), `DisplaceDirection` (7).

> **Mutation** : la prochaine MAJ renumérote un 5<sup>e</sup> enum (`EffectType`,
> `TriggeredAbilityType`, `ActiveAbilityType` sont les candidats mesurés). Les quatre étapes
> gardées ne le voient pas et rendent `PASS`. Le probe existe *parce que* les MAJ renumérotent :
> son périmètre se périme exactement au moment où il sert.

### 3. `probe_283:prose` — le périmètre exclut là où vivent les citations

L'entrée de banque ne passe pas `--racine`, donc balaie `scripts/python`. Mesuré :
`--racine docs` rend **447 citations dérivées, 369 à l'ancien ordinal, et 77 FAIL du gate 4bis**
(`case-100-anvil-shield-residus.md:40`, `backlog.md:166`, `case-220/votann.md:112`…). Aucun autre
cliquet ne couvre `docs/**`.

### 4. `probe_443r2` — le régime des substrats est recopié, pas lu

> **Mutation** : ajouter `and e.active` à `EffectsState.has_effect`. Le substrat bascule en régime
> ACTIVITÉ, tous les mirrors déclarés `onlyActive: 0/false/null` lisent désormais l'activité —
> exactement la divergence gardée — et le probe reste **VERT** parce que sa table dit toujours
> `"has_effect": "PRESENCE"`. Une ligne, motivation plausible, seul garde de cet axe.

### 5. `probe_366pos` — un marqueur d'exemption qui ne prouve aucune garde

`GATES` contient `return`. Mesuré : **133** sites ont leur déréférencement neutralisé par un
marqueur, dont **17** par un marqueur qui ne prouve rien (`" and "` 7, `" or "` 4, `" else "` 3,
`"return"` 2, `"if not "` 1).

> **Mutation** : écrire `return e.get_component(PositionComponent).col` — la forme la plus banale
> d'un accesseur. Site jamais signalé, crash offline garanti, **VERT**.

## Risques MOYENS retenus

* **`probe_439` — `cibles[0]`** : une entrée pytest multi-fichiers n'est jugée que sur son
  **premier** fichier. `pytest_adjacency` en porte 3 ; les deux autres (11 et 18 tests) ne sont
  **jamais** jugés. Vider l'un d'eux de ses `assert` laisse 439 vert.
* **`probe_120`** : `NORMAL_ATTACK_KIND = 0x3f5` est réinjecté par le probe, donc mettre
  `ability_type=None` dans `damage_ops/normal.py` ne rougit pas (les étapes 1/2/5 restent, elles,
  gardées).
* **`probe_313`** : `PAR_CLS` indexé par **nom court** — une seconde `IntEnum` homonyme dans un
  autre fichier écrase l'entrée sans être ni orpheline ni absente.
* **`probe_274`** : la table JS positionnelle est gardée pour `battle-log.js` uniquement ; et
  l'étape 1 ne retient que `.py`, donc `if (step === 13)` dans `frida/hooks/*.ts` est invisible.
* **`pytest_signatures`** : la garde de **transmission** ne teste que 2 des 20 paramètres — un
  21<sup>e</sup> paramètre accepté-et-avalé par les substitutions passe.
* **`pytest_adjacency`** / **`probe_366bcp`** / **`probe_319`** : motif #421 — la **couverture** est
  une liste manuelle, donc un 6<sup>e</sup> foyer / une 3<sup>e</sup> voie de patch / une étape
  neuve de `probe_273` n'est enrôlé par personne. Constat qui l'étaye : une sixième fonction
  d'adjacence existe **déjà** (`engine/services/movement_query.py::is_adjacent`) et n'apparaît dans
  aucun des trois fichiers de `pytest_adjacency`.

## La leçon, sous forme de règle

Un cliquet a **deux** faces, et prouver la première ne dit rien de la seconde :

1. **le critère** — ce qu'il compare. C'est là que vit l'attestation native, légitimement saisie ;
2. **le périmètre** — *sur quoi* il le compare. C'est là que le saisi tue en silence, parce qu'un
   périmètre trop étroit ne rend pas d'erreur : il rend **zéro**, et un zéro se lit « rien à
   signaler ».

Sur les 5 risques hauts, **4 sont des périmètres**, pas des critères.
