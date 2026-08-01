# case-430 — la banque de cliquets devient un artefact exécutable

**L'artefact** : `scripts/ratchets.ps1`. **19 cliquets**, source UNIQUE, parallèle,
`rc = nombre de rouges`. `-List` imprime la banque en TSV.

```powershell
pwsh -File scripts/ratchets.ps1                      # tout, parallélisme auto
pwsh -File scripts/ratchets.ps1 -Only probe_283      # un cliquet (ou son préfixe)
pwsh -File scripts/ratchets.ps1 -List                # id / commande / seul-a-voir / doc
```

## 1. Le fait

La liste des cliquets n'existait **nulle part comme objet**. `git ls-files` ne rend aucun
`.github/`, aucun Makefile, aucun runner. Elle vivait en trois exemplaires **incompatibles** :
la prose du `CLAUDE.md`, un `runpar.ps1` **non versionné** du scratchpad de l'orchestrateur, et
des case-docs qui en citaient des compositions divergentes (`case-366-r1-martial-superiority`
en citait 5 ; `case-415-suppressive-fire` en citait 8, dont **4 hors des 9**).

C'est la cause d'**exécution** derrière trois dérives mesurées le 2026-08-01 (#420 `probe_283`,
#421 `probe_229`, #427 `probe_313`).

## 2. Ce que #427 avait établi, et que cette tranche opérationnalise

Prouver sa couverture est **nécessaire et non suffisant**. `probe_313` avait DÉJÀ cette forme —
sa preuve de couverture EST un test offline de la suite — et a laissé passer deux dérives : la
suite complète n'est **jamais** jouée (le `CLAUDE.md` la proscrit, à raison), et un agent ne
cible que les tests de SA tranche.

> Dans ce dépôt, **« être un test » et « être joué » sont INDÉPENDANTS**.

D'où l'artefact : une liste **qu'on lance**.

## 3. Ce que le premier passage a trouvé — deux dérives, immédiatement

La banque a payé son écriture avant d'être finie.

| # | Trouvaille | Preuve | Sort |
|---|---|---|---|
| 1 | **`probe_313` était ROUGE sur `origin/master`** au commit de lancement (`11864f04`). `PathfinderType` (`engine/entities/pathfinding/pathfinders.py`) et `KillUnitStep` (`engine/runner/operations/remove_effects.py`) — deux mirrors natifs écrits VERBATIM du dump — étaient entrés dans `engine/` **sans entrer à son registre**. Le cliquet existait, il n'était pas joué. | Inscrits ; **12** mirrors SOUS GARDE, bijection 0/0/0, `total=1854` références qualifiées, rc 0. | **Fermé en parallèle par #427**, arrivé dans `master` pendant cette tranche — conflit de rebase sur le registre, tranché **en faveur de #427**. Mon correctif prenait `KillUnitStep` en `strict=False` ; le sien renomme les membres du **port** en verbatim du jeu et garde `strict=True`, ce qui est meilleur : `strict=False` relâche les NOMS pour **tout** le mirror et rend muet le sens RENUMEROTE. La valeur qui reste : **confirmation indépendante** que le trou n'était pas dans la détection mais dans le **lancement**. |
| 2 | **`probe_181` ne pouvait PAS rougir.** Il rendait `return 0` **inconditionnellement** — un inventaire déguisé en garde-fou. Or le `CLAUDE.md` prescrivait « faire passer `probe_181` avant d'ouvrir une PR », et une quinzaine de case-docs l'attestaient comme cliquet. | Mesure : renommer le `TARGETING_OPTIONS` de `HarbingerOfDestructionAbility` (1008) le laissait **VERT**. Gate posé sur le compte GLOBAL ; le mutant le fait désormais rougir en nommant l'ability. | **Corrigé ici, et exclusif** : `origin/master` porte toujours le `return 0` inconditionnel au moment du rebase. |

La seconde est la plus instructive : **un cliquet cité par le `CLAUDE.md` n'atteste rien tant
que personne n'a vérifié qu'il RENDAIT un code non nul.** L'audit du critère sur les 13 scripts
de la banque n'a trouvé que celui-là — les 12 autres ont un chemin de sortie non nul réel
(attention au faux négatif : `probe_365` porte le sien en `rc = 1`, pas en `return 1`).

## 4. Les entrants — verdict, et pourquoi

Critère énoncé : **le coût marginal en parallèle** (jamais le coût absolu) et **ce que le cliquet
est seul à voir**.

| Candidat | Verdict | Motif |
|---|---|---|
| `probe_313` | **DEDANS** | Seul à voir un mirror `IntEnum` qui n'est plus en bijection avec `enums.tsv` (manquant / mort / **renuméroté**) et toute `IntEnum` entrée sous `engine/` sans appariement ni justification. A trouvé deux dérives réelles à son premier passage. |
| `probe_319` | **DEDANS** | Seul à voir la **dégradation d'un autre cliquet de la banque** : fidélité du balayage de `probe_273` (un fragment de chemin pris pour une lecture) et reproductibilité worktree vs arbre principal — les deux propriétés étaient FAUSSES. Un garde-fou dont le verdict dérive ne vaut rien. Proposé par #409-r1. |
| `probe_229` + `probe_421` | **DEDANS, les deux** | Inséparables : `probe_229` vérifie la conformité des classes **qu'il connaît** ; `probe_421` vérifie qu'il les connaît **toutes** (19 classes étaient entrées au registre sans entrer au rail). L'un sans l'autre est un demi-cliquet. Coût marginal quasi nul. |
| `probe_283` | **DEDANS, éclaté en ses 6 étapes** | Seul à voir la casse par **migration de build** — 220 citations invalidées **sans qu'une seule ligne change**, donc structurellement invisible à tout déclencheur sur diff ; et l'étape `exec` couvre le gisement de #272, qui a produit du code exécutable faux en silence (`CAPTURE_POINT = 24` devenu `MoltenForm`, feuille rendant `0.0`). |

### Le découpage de `probe_283` — ce qui rend son admission soutenable

`--step all` est l'**union stricte** des six étapes (lire `main` : six `ko +=` indépendants), et
sans `--fix` le probe est en **lecture seule** — six processus concurrents ne peuvent pas se
marcher dessus. Le découpage ne change donc **rien** à la couverture, et tout au coût :

| Composition | Mur (parallèle) |
|---|---|
| les 9 d'avant | **112,8 s** |
| 9 + 313 + 319 + 229 + 421 | **145,0 s** |
| + `probe_283` **d'un bloc** (14 entrées) | **299,4 s** — il double le mur à lui seul |
| + `probe_283` **éclaté** (19 entrées) | **172,0 s** |

Éclaté, sa plus longue étape (`prose`, ~47 s isolée) passe très en dessous du mur, qui reste tenu
par `pytest_signatures` et `probe_313`. Coût marginal des **10 entrées neuves : +59 s de mur**.

`diff` et `on` sont des **compteurs** (aucun `ko +=` : structurellement incapables de rougir).
Ils restent dans la banque — 9 s de CPU pour qu'elle soit l'équivalent **exact** de `--step all`,
et pour qu'un futur `ko +=` posé sur eux soit vu. Les exclure aurait recréé le défaut corrigé
ici : un cliquet listé mais jamais joué.

⚠ Ces chiffres se re-dérivent (`pwsh -File scripts/ratchets.ps1`), ils ne se citent pas : la
machine était partagée avec d'autres agents, et le mur bouge **beaucoup** avec la charge. Les
quatre compositions ci-dessus ont été mesurées en runs consécutifs, donc comparables entre elles ;
la même banque de 19, re-jouée **après rebase** sur une machine plus calme, rend **108,8 s**. Ce
qui est stable, c'est le **rapport** entre compositions, jamais la seconde absolue.

## 5. La contre-épreuve — la banque rougit, et nomme

Trois mutations **simultanées**, sur un run **complet** (pas un `-Only` : il fallait prouver que
le rouge n'est pas avalé au milieu de 19) :

| Mutant | Cliquet visé | Résultat |
|---|---|---|
| `TARGETING_OPTIONS` de `HarbingerOfDestructionAbility` renommé | `probe_181` | ROUGE, `MANQUANT 1008 HarbingerOfDestructionAbility necrons` |
| entrée `PathfinderType` retirée du registre de `probe_313` | `probe_313` | ROUGE, `ORPHELINE PathfinderType ...` + `1 ecart(s) BLOQUANT(s)` |
| fichier jetable portant la signature structurelle d'une substitution | `pytest_signatures` | ROUGE, `AssertionError: substitution(s) ... desynchronisees du port` |

**`rc = 3`**, les trois nommés en tête de rapport **et** dans la ligne de synthèse, extraits de 2
à 5 lignes portant la cause. Arbre restauré (`necrons.py` revenu **bit-exact**, aucune trace au
`git status`), banque re-jouée **verte, 19/19**.

Un défaut du rapport a été trouvé par cette contre-épreuve et corrigé : le motif d'extraction
`MANQUANT` **non ancré** matchait les `MANQUANTS=0` des lignes VERTES de `probe_313` et
repoussait hors cadre la seule ligne utile. Toute alternative du motif est désormais ancrée en
début de ligne ou porte un séparateur.

## 6. La règle qui remplace la duplication

**`scripts/ratchets.ps1` est la source unique.** Un cliquet neuf s'ajoute **dans le fichier**,
avec sa ligne « ce qu'il est SEUL à voir » — le champ n'est pas décoratif, c'est le critère
d'admission écrit à côté de l'entrée.

Distinction qui évite de rouvrir le défaut : une case-doc **atteste** ce qu'elle a joué (un
relevé daté, ex. « `probe_181` 98/98 ») ; elle ne **définit** pas la banque. Seules les
énumérations qui se présentaient comme LA composition ont été remplacées par le pointeur.

## 7. Ce qui n'est PAS couvert

* **Rien ne force à lancer la banque.** Pas de CI (il n'y en a pas), pas de hook git auto-installé
  — les deux étaient explicitement hors périmètre. La banque déplace le problème de « quelle est
  la liste ? » (résolu) vers « l'agent la lance-t-il ? » (discipline, comme avant). Le levier
  restant serait un hook `pre-push` **proposé** et non installé, ou une étape du workflow de PR.
* **Les ~15 case-docs qui attestent un sous-ensemble daté** (« Cliquets : `probe_181` (98/98),
  `probe_120 --step 0` ») n'ont pas été réécrites : ce sont des relevés, pas des définitions. Le
  risque résiduel est qu'un lecteur les prenne pour la composition — c'est ce que la règle du §6
  et le pointeur du `CLAUDE.md` doivent empêcher.
* **Le chemin de repli du rapport** (aucun motif de cause reconnu → queue du log) n'est pas
  éprouvé par mutant : les trois mutations sont toutes tombées sur le chemin nominal.
* **`probe_283 --step live`** est hors `all`, donc hors banque : il exige une session vivante et
  warmée, ce qu'un cliquet offline ne doit pas supposer.
* **Le critère « peut-il rougir ? » n'est pas gardé automatiquement.** Il a été vérifié à la main
  sur les 13 scripts (un seul défaillant, `probe_181`). Un cliquet neuf qui rendrait `0`
  inconditionnellement entrerait sans être vu — c'est le résidu le plus proche d'un vrai trou.

## 8. Fichiers

| quoi | où |
|---|---|
| la banque | `scripts/ratchets.ps1` |
| gate posé sur l'inventaire | `scripts/python/probe_181_targeting_gaps.py` |
| deux mirrors inscrits au registre | `scripts/python/probe_313_enum_mirror_bijection.py` |
| pointeurs (plus d'énumération) | `CLAUDE.md`, `docs/rl/case-415-suppressive-fire-pair-term.md`, `docs/rl/case-366-r1-martial-superiority-visual.md` |
