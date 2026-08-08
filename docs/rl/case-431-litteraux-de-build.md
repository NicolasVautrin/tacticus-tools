# #431 — les hashes de build ecrits en dur : ce qui echoue FORT, ce qui ment EN SILENCE

> Build courant `rnca9r7q6c`. Etat FINAL au 2026-08-01. Cliquet : `probe_431_build_literals.py --cliquet`.

> ⚠ **Le PERIMETRE de ce cliquet a ete refait le 2026-08-02 (#458)** : ses globs passaient par
> `Path.match`, qui ne developpe pas `**`, et **967 fichiers versionnes tombaient dans AUCUN seau**
> — tout `scripts/python/engine/**`, tout `tests/**`, et par le HAUT `frida/host/router.ts`,
> `frida/hooks/main.ts`. Le perimetre se derive desormais de l'**extension**, et une etape 0
> **prouve la couverture**. Les comptes de la §1 ci-dessous sont ceux de l'ancien perimetre.
> Detail et re-mesures : **`docs/rl/case-458-perimetre-derive-du-cliquet-431.md`**.

## 1. Le recensement, re-derive

**Les 5 probes** qui construisaient le chemin du `GameAssembly.dll` de `gqfc5mff6c` :

| fichier | ce qui etait epingle |
|---|---|
| `scripts/python/probe_8889_methodptr_vtable.py:33` | `DEFAULT_DLL` |
| `scripts/python/probe_88_dispatch_scan.py:21,23` | DLL + `functions.tsv` + **2 VA de thunk** |
| `scripts/python/probe_88_event_emitters.py:19` | DLL + **55 call-sites transcrits** |
| `scripts/python/probe_88_on3_emitter.py:21,23` | DLL + `functions.tsv` |
| `scripts/python/probe_88_on3_publishers.py:29,31` | DLL + `functions.tsv` + **3 ordinaux d'enum** |

**Citations de l'ancien hash** : `git grep -l gqfc5mff6c` rend **461 fichiers suivis**
(253 `scripts/python`, 182 `docs/rl`, 15 `frida/hooks`, 5 `data/symbols` — l'archive
elle-meme —, 2 `.claude/skills`, `CLAUDE.md`, 3 divers). **Le « 91 » du brief n'est
reproductible sous aucune definition essayee** (total, hors-docs, executables seuls,
case-docs seuls) ; les chiffres ci-dessous sont re-derives et portent leur definition.

## 2. Le regime : lequel des deux s'applique

`gqfc5mff6c` **n'est plus installe** (le launcher purge : seul `rnca9r7q6c` est sur disque).
Les 5 echouaient donc FORT — 2 proprement (`ABSENT: ...`, rc 2), 3 par `FileNotFoundError`
nu (rc 1). **Aucun n'etait dans le regime silencieux.**

**Mais le regime silencieux etait a UNE CORRECTION de distance**, et c'est le point du cas :
faire resoudre la DLL par le build COURANT *sans toucher au reste* transforme l'echec franc
en mesure fausse. Mesure :

* les **55** call-sites de `probe_88_event_emitters` resolvent **55/55** contre la table
  `gqfc5mff6c` et **0/55** contre `rnca9r7q6c` — chacun tombe dans du code d'UI
  (`idun.ui.UnitDeploymentHud$$GetSameUnitWithDifferentBorrowedState+0x147`,
  `idun.Idun.Source.UI.ToggleSlider...`). Le decodage d'immediat aurait continue de rendre
  des nombres, l'en-tete d'afficher les BONS noms d'operations ;
* le thunk `0x180026490` est un **debut de fonction** sur `gqfc5mff6c` et tombe a
  `FUN_180026460+0x30` sur `rnca9r7q6c` — le balayage rendrait **zero call-site**, qui se lit
  « aucun evenement publie » ;
* les temoins de `probe_88_on3_publishers` etaient **deja faux** : `0x2f` et `0x2c` y sont
  annonces `UnitResurrected` / `UnitHealed`, mais valent `UnitMemberDeath` /
  `UnitHealedWithRemoveEffects` sur le build courant (4 enums renumerotes, #283). Le probe
  aurait cherche deux autres evenements, et l'absence de ses propres temoins — sa seule
  auto-validation — se serait lue comme un faux negatif du balayage.

**TROISIEME regime, non prevu et rencontre** : le **refus FAUX**. `probe_193c` et
`probe_r1b` exigeaient `gqfc5mff6c` pour les RVA en dur de `scorer-damage-trace.ts` alors
que **#257 les avait deja migrees vers `rnca9r7q6c`** : ils refusaient de tourner sur un
build ou tout etait bon. Un refus faux se lit exactement comme un refus legitime.

## 3. Le point de raccord : `scripts/python/build_pin.py`

Un seul foyer, fail-closed (`BuildPinRefused`, jamais un chemin) :

* `game_dll()` — la DLL du build INSTALLE, **et seulement** s'il est celui de
  `data/symbols/CURRENT`. C'est la regle du `CLAUDE.md` tenue **au point d'usage** : elle
  l'etait deja sur les artefacts centraux (`symbols_sync.py` axe 1), et sur rien la ou un
  littéral court-circuitait tout ;
* `functions_tsv()`, `load_dll()` — les trois artefacts (octets, sections, table) sortent
  **ensemble** du meme build ou aucun ne sort ;
* `require_pinned(build, quoi, comment)` — pour les valeurs TRANSCRITES A LA MAIN (VA de
  thunk, ordinaux, RVA d'un hook). **Seul axe qu'aucun balayage du depot ne peut deriver** :
  sa source est hors depot. Il est donc DECLARE et confronte ;
* `archived_build(nom, quoi)` — pour une reference DELIBEREMENT anterieure (diff de
  migration). On n'exige pas qu'elle corresponde a l'installe, on exige que son **archive**
  soit encore versionnee ;
* `install_dir(strict=)`, `pe_sections()`, `SymbolIndex` — mutualises (quatre des cinq
  probes portaient leur propre copie du parse PE).

### Ce que sont devenus les 5

| probe | verdict |
|---|---|
| `probe_8889_methodptr_vtable` | **tourne** — seul le chemin etait perime |
| `probe_88_on3_emitter` | **tourne** — aucun epinglage, DLL+table par le foyer |
| `probe_88_on3_publishers` | **tourne** — temoins **nommes**, ordinal lu dans `EventTriggerType`. Les 3 ressortent sur leur operation native (`MoveUnitOperation$$EvaluateArrivedAtFinalTileTrigger`, `ResurrectUnitOperation$$Execute`, `HealUnitOperation$$Execute`) |
| `probe_88_dispatch_scan` | **tourne** — thunks **RE-DERIVES** a chaque run depuis un symbole NOMME + une valeur d'enum NOMMEE (`MoveUnitOperation$$EvaluatePreMoveTriggers` publiant `PreUnitMove` en r9d ; `DisplaceUnitOperation$$EventAndAbilitiesAndEffects` publiant `UnitDisplaced` en pile). 58 call-sites, 49 evenements |
| `probe_88_event_emitters` | **tourne** — la transcription des 55 call-sites est **SUPPRIMEE**, pas mise a jour : une liste ecrite a la main se re-perime au build suivant et rien dans le depot ne peut le voir |

Les deux thunks sont des `FUN_<addr>` — la doctrine autorise la VA quand le symbole n'est
que l'adresse deguisee, **elle n'exempte pas de la peremption**. D'ou l'ancrage, qui ne
coute rien : `MoveUnitOperation$$EvaluatePreMoveTriggers` -> `FUN_1800280e0`,
`DisplaceUnitOperation$$EventAndAbilitiesAndEffects` -> `FUN_18002a780`, verifies au
decompile.

## 4. La garde : `probe_431_build_literals.py`

Ce que les gardes existantes ne peuvent pas voir : `symbols_sync` verifie les artefacts
CENTRAUX (un littéral ne les consulte pas) ; `probe_330` ne balaye que la **prose**
(`.md/.txt/.tsv` sous `docs/` et `.claude/`), aucun `.py` ni `.ts`.

**Tri EXECUTABLE vs PROSE — decidable.** Pour un `.py`, l'AST tranche exactement : un
commentaire n'y est pas, un docstring s'y identifie a sa position. Pour un `.ts/.js`,
heuristique de ligne **annoncee** (+ retrait du commentaire de queue, sans lequel
`battle-log.js:242` passait pour du code).

**Tri RESOLUTION vs MESSAGE — local et exact** : la chaine EST un hash, ou le hash y est un
segment de chemin. Deux criteres plus larges ont ete essayes et **rejetes, tous deux vers le
vert faux** : « le contexte contient games/symbols/... » classait RESOLUTION 4 lignes de
markdown GENERE ; « segment de chemin seulement » laissait passer **9** `--build
default="<hash>"` / `table_owners("<hash>")`, qui selectionnent bel et bien une table.

**Le littéral n'est pas interdit — il est interdit HORS du foyer.** Passe en argument direct
de `archived_build` / `require_pinned`, il est CONTROLE ; l'exemption se **derive de l'AST**,
pas d'une liste d'exceptions (une liste, il faudrait la maintenir, et elle survivrait a son
motif).

**Chiffres** (meme classifieur des deux cotes, `git ls-tree` du commit de depart) :
**23 resolutions dans 19 fichiers -> 0**, sur 845/847 fichiers executables versionnes.
Au-dela des 5 probes : 3 racines d'installation sur `nb3o9lmt6c` (`probe_languages` tourne
pour la premiere fois depuis ; `build_asset_manifest` retombait TOUJOURS sur le pull RAW sans
le dire), 6 selecteurs de table -> `CURRENT`, 3 references -> `archived_build`, 2 pins de RVA
corriges.

### Vu rougir

`tests/test_431_build_pin_offline.py` — **17 tests**. Les deux mutations sur fichier
REELLEMENT SUIVI (le perimetre vient de `git ls-files` : un mutant non suivi ne serait jamais
balaye, et le test passerait au vert sans rien eprouver) verifient la morsure en deux temps —
relecture disque + sha256 — puis restaurent. La **contre**-mutation (une estampille en prose
ajoutee) doit rester VERTE : un cliquet qui rougit sur les rappels historiques serait desarme
dans la semaine.

Meta-contre-epreuve, **5 mutants / 5 tues** : classement (chaine-qui-EST-un-hash ; segment de
chemin), balayage (plus aucune constante examinee), foyer (double controle desarme ;
`require_pinned` qui accepte tout). Temoin intact vert avant et apres, arbre restaure.

## 5. La face PROSE — recensee, pas jugee

596 occurrences dans 260 fichiers de prose versionnes (334 `gqfc5mff6c`, 241 `rnca9r7q6c`,
15 `kqkbjqfb6c`, 4 `nb3o9lmt6c`, 1 `uu2fr8mv6c`, 1 `rmvdp0v56c`). `probe_330` en ventile la
part `docs/`+`.claude/` : **210 estampilles d'en-tete/declaratives perimees dans 156
fichiers** (56 REFERENCE, 154 CASE-DOC) et 139 mentions en corps dans 70 fichiers.

**Le tri fin n'est pas automatisable, et on ne le simule pas.** Le test de lecture :
*remplacer mentalement le hash par « le build courant »*. Si la phrase reste vraie, c'est une
reference vivante — perimee. Si elle devient fausse, c'est un rappel date, et le corriger
DETRUIT le fait (#420 en a laisse un expres : `probe_hazeord_blast_radius.py:34`).
Trois signaux le rendent tranchable en pratique : la citation porte-t-elle une date ou un
marqueur d'anteriorite ; le hash est-il le SUJET de la phrase ou son DECOR ; le document
est-il un compte rendu ou une reference.

**Audit a la main, borne aux documents lus comme etat COURANT par tout agent**
(`CLAUDE.md`, `.claude/skills`, `.claude/agents`) — **5 citations, 4 rappels deliberes,
1 reference vivante perimee** :

| citation | verdict |
|---|---|
| `.claude/skills/tacticus-orchestration/SKILL.md:568` | rappel — recit d'un incident (« a disparu sans jamais avoir ete versionne ») |
| `.claude/skills/tacticus/references/runner.md:140` | rappel — la mesure DIT sur quel build elle a ete faite ; c'est la bonne pratique |
| `CLAUDE.md:44` | rappel — exemples illustratifs ; leur peremption RENFORCE le propos |
| `CLAUDE.md:106` | rappel date d'une mesure de churn |
| `.claude/skills/tacticus/references/rl-database.md:244` | **vivante, perimee — CORRIGEE** : « (actuellement **kqkbjqfb6c**) », deux builds en arriere. Le mot « actuellement » EST le discriminant |

## 6. Residus

* **Les 210 estampilles d'en-tete de la prose** restent : `probe_330 --fail-on-header-stamp`
  est ROUGE et n'est pas dans les 9 cliquets. C'est le gisement de `probe_330`, pas de #431 ;
  il demande un tri de lecture document par document.
* **`probe_193c` / `probe_r1b`** portent encore un hash transcrit (`rnca9r7q6c`), et c'est
  irreductible : il vient de `frida/hooks/features/scorer-damage-trace.ts`, un fichier `.ts`
  dont on ne derive pas la validite des RVA depuis Python. Il est desormais DECLARE et
  confronte par `require_pinned`, avec la procedure de re-derivation dans le message.
* **`frida/hooks/**` n'est couvert que par l'heuristique de ligne** — pas d'AST TypeScript
  ici. Les 4 occurrences trouvees sont des messages de log ; une resolution d'artefact cote
  hook passerait, elle, par `Process.findModuleByName`, jamais par un chemin.

## 10. `#431-r1` : le perimetre etait deja repare -- ce qui manquait, c'etait le CLIQUET

**Ferme le 2026-08-08, sur `b3e80f94`.** La fiche de residu decrivait `is_exec` comme testant
`Path(rel).match("scripts/**/*.py")` et chiffrait **904 fichiers balayes sur 1 814**. Les deux
etaient **perimes de six jours** : #458 avait deja remplace la liste de globs par un seau derive
de l'EXTENSION. Re-derive :

| mesure | fiche (2026-08-02) | re-derive (2026-08-08) |
|---|---|---|
| fichiers suivis | 1 814 `.py` sous `scripts/` | **4 255** (tout l'arbre) |
| seau EXECUTABLE | 904 | **2 629** |
| hors de tout seau | 910 (muets) | **0** (l'etape 0 rougit dessus) |
| RESOLUTIONs | 17 annoncees apres correction | **0** (36 occurrences, toutes MESSAGE) |

Les « 17 RESOLUTIONs synthetiques » que la fiche donnait comme prix de la correction n'existent
pas : elles ont ete traitees dans #458 meme.

### Le balayage transverse a rendu ZERO -- et c'est le resultat, pas un non-lieu

La fiche demandait de chercher la meme faute ailleurs, `PurePath.match` avec `**` etant un piege
de LANGAGE et non une etourderie locale. Balayage AST sur les **2 287** `.py` versionnes :

* **1** seul `PurePath.match` avec un glob de chemin -- `test_431_build_pin_offline.py:532`,
  et c'est la **contre-epreuve** delibiree qui isole la cause de #458 (`assert not ...`) ;
* `glob.glob` : tous les appels a `**` portent `recursive=True` ; `fnmatch` : **0** motif `**` ;
* **1** seul convertisseur glob -> regex maison, `declencheur_cliquet._regex`, et il est
  **correct** (`**/` y vaut ZERO segment ou plus, semantique git pathspec).

### Ce qui est livre, et pourquoi ce n'est pas une reparation

`probe_431r1_globs_non_recursifs.py` + `tests/test_431r1_globs_non_recursifs_offline.py`.
Rien n'etait casse ; un balayage ponctuel, lui, ne peut pas empecher le retour -- et ce vice
est **muet par construction** : aucun des trois matchers ne leve, tous acceptent le motif.

Le cliquet couvre les **trois** matchers qui ne developpent pas `**`, et **aucun** de ceux qui
le developpent (`Path.glob`/`rglob`, `full_match` 3.13) -- les compter serait du bruit :

| matcher | ce que `**` y devient | leve ? |
|---|---|---|
| `PurePath.match` | UN segment, et le match part de la DROITE | non |
| `glob.glob` sans `recursive=True` | degrade en `*` | non |
| `fnmatch` | `*` traverse les `/`, donc `**/` exige quand meme un `/` | non |

Deux choix de conception, tous deux **derives** et non saisis :

* le litteral doit etre un **glob de chemin** (`**` + `/` ou `*.`) -- sans ce discriminant, les
  **495** litteraux de markdown gras (`**PORTE**`) des generateurs d'audit entreraient tous ;
* l'exemption de **contre-epreuve** porte sur la FORME `assert not <appel>`, jamais sur un
  chemin : une allowlist se perime et devient l'echappatoire. La garde tient les deux cotes --
  un appel NON nie rougit dans le meme fichier qu'un `assert not`.

Enfin le probe **prouve qu'il mord dans le meme processus que la conformite** (idiome #421) :
10 mutants, dont **7 sains**, joues a chaque run. Un jeu tout-positif prouverait la morsure et
jamais l'absence de bruit -- le test assertionne les deux polarites.

## 11. Le vice s'est REJOUE D'UN CRAN PLUS HAUT -- sur le DECLENCHEUR du cliquet

**Trouve en relecture de #845, corrige dans la foulee.** Les trois cliquets livres par cette
tranche declaraient leur perimetre ainsi :

```python
"chemins": ("scripts/python/probe_431r1_globs_non_recursifs.py",),
"toujours": False,
```

Lu litteralement : **ce cliquet ne se rejoue que si sa propre sonde change**. Or il balaie les
2 287 `.py` versionnes. Un fichier NEUF portant un `PurePath.match("**/…")` fautif ne l'aurait
donc **pas reveille** -- exactement le mode de panne qu'il existe pour empecher.

C'est la lecon de #458 (une liste de racines laissait **967** fichiers dans un trou MUET),
transposee d'un etage : cette fois c'est le **DECLENCHEUR** qui etait la liste trop courte. Le
motif ecrit pour justifier le bypass etait juste sur le fond -- << une fermeture d'imports ne
peut pas borner un cliquet dont le perimetre est l'ARBRE >> -- mais la conclusion ne suivait
pas : ce n'est pas un bypass qu'il fallait, c'est `toujours: True`.

**Le precedent etait dans la meme famille** : `tests/test_431_build_pin_offline.py` declare
`("*", "**")` + `toujours: True`, et pour la raison exacte -- son verdict depend du CONTENU de
l'arbre, pas de ses imports.

| | avant | apres |
|---|--:|--:|
| entrees de `ratchets-486r24-bypass-confrontation.txt` | **6** | **3** |

Les trois ajoutees par #845 en sont sorties, sans aucun rouge : `toujours: True` + un glob qui
dit la verite (`("*", "**")`) rendent le bypass **inutile**. `probe_486r15` l'a confirme tout
seul -- il porte deja le cran << declare `hors_confrontation` mais NE MASQUE RIEN : declaration
MORTE, la retirer >>, et il a signale les trois attestations comme **PERIMEES** avant de les
retirer.

⚠ **Le glob large ne MENT au selecteur que si `toujours` est `False`.** Le critere de
`probe_486r15` est << ce joker couvre-t-il un test ou un probe TIERS ? >> -- et ici la reponse
est oui **parce que c'est vrai** : ces cliquets OUVRENT les tests et les probes tiers pour les
parser. Avec `toujours: True`, la question de la selection ne se pose plus : le fichier se
rejoue de toute facon.

⚠ **Une echappatoire qui n'a plus de raison d'etre est PIRE qu'inutile** : elle documente une
derobade qui n'existe plus, et le fichier d'attestation dit lui-meme que ce qui est garde n'est
pas le zero mais qu'on sache **QUI se derobe et sur quel motif**. Un motif qui s'evapore doit
faire sortir de la liste.
