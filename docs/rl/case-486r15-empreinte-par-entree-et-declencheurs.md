# Case 486-r15 — L'empreinte offline prend la forme du ledger live, et chaque test DÉCLARE son déclencheur

## 1. Le fait

`scripts/ratchets-457-footprints.json` portait **UN SEUL `_commit`** pour tout le fichier, et
`impacted_files` s'en servait comme **critère** de fraîcheur (union du diff de la PR avec « tout ce
qui a changé depuis la mesure »).

Ce sha était écrit **dans le worktree d'un agent**, donc sur SA branche — que le squash-merge
remplace par un commit neuf avant de la supprimer. **Il naissait mort-né.** Mesuré le 2026-08-07 :
`57bb2a7c` inconnu de `git cat-file`, et `probe_457 --since` sélectionnait **220/220 fichiers sur
chacune des 8 dernières bases de PR** — la sélection ne sélectionnait plus rien depuis 3 jours et
~40 commits. Ce n'est pas un oubli : c'est **auto-destructeur à chaque livraison par PR**.

Le repli était correct (« tout doute rejoue TOUT, et le dit ») mais **muet** : la ligne était
imprimée à chaque run et personne ne la lisait.

## 2. Ce qui remplace le tampon global : RIEN — le `git diff` fait foi

La question à laquelle l'empreinte répond est « ce diff touche-t-il ce test ? ». Git rend déjà la
liste des chemins modifiés ; on l'apparie aux deps mesurées et aux globs déclarés. **Appariement de
chaînes, zéro lecture, zéro sha.**

Une clé de contenu par entrée a été **essayée puis écartée**, sur trois mesures :

| forme | coût | verdict |
| --- | --- | --- |
| clé de fermeture d'imports par entrée | graphe 29,5 s + 0,45 s | redondante avec le diff |
| deps au FICHIER, avec blob par dep | 1 227 → **59 592** deps (**×48,6**) | volume rédhibitoire |
| sha256 du contenu de `scripts/python` | **4 001 ms** | > le plus petit test (80 ms) |
| `stat()` seul de `scripts/python` | **2 643 ms** | pas un refuge (coût = nb d'appels système) |
| `git ls-files -s` (tout le dépôt, 3 985 fichiers) | **274 ms** | viable, mais inutile si le diff fait foi |

**Et la fraîcheur se répare toute seule dès que la mise à jour PARTIELLE existe** : le fichier de
test change → il est dans le diff → il est sélectionné → il tourne → **son entrée est réécrite**.
Un module de sa fermeture change → le graphe le retient → même chaîne. Le seul cas dangereux (un
module qui se met à lire une donnée que l'empreinte ignore) est donc couvert **au moment même où ce
module change**. C'est pourquoi la mise à jour partielle est le cœur de la tranche, et le `_commit`
global qui l'interdisait était le vrai défaut.

## 3. Le tri-état qui manquait : JAMAIS MESURÉ ≠ MESURÉ-ET-VIDE

`impacted_files` lisait « absent de `par_test` » comme « ce test n'ouvre aucun fichier du dépôt ».
C'est une **affirmation jamais gagnée** : elle ne vaut que si le test a tourné au moins une fois
sous le hook d'audit. Mesuré sur `master` : **88 entrées pour 220 fichiers offline** — 132 fichiers
passaient par cette affirmation.

Le format **2** écrit une entrée pour **chaque fichier joué**, `dirs` VIDE compris. Une absence se
lit donc « pas de mesure » → rejoue. Le mode de défaillance bascule du côté sûr : **une empreinte
vidée rejoue TOUT** au lieu de sauter des tests.

## 4. La moitié DÉCLARÉE : `DECLENCHEUR` par FICHIER

Chaque fichier de test déclare, au niveau module, ce qui doit changer pour qu'il puisse changer de
verdict — **mêmes quatre clés et même sémantique de glob que les cliquets** (`declencheur_cliquet.py`,
foyer partagé avec #486-r12).

**Coût d'évaluation, mesuré sur les 220 fichiers offline :**

| poste | coût |
| --- | --- |
| lecture des 220 fichiers + pré-filtre par sous-chaîne + AST des seuls déclarants | **227 ms** |
| appariement des globs au diff (15 chemins) | **1,0 ms** |
| *(pour comparaison)* graphe d'imports de la moitié MESURÉE | **29 508 ms** |

Soit **×130** moins cher que ce qu'il remplace, et 1,7 % des 13,1 s que pèsent à eux tous les 165
fichiers offline les plus légers. Le graphe est **paresseux** : il n'est calculé que s'il reste un
fichier non déclaré — c'est ce que la généralisation des déclarations fait disparaître.

**Le grain est le FICHIER, jamais le test**, et c'est mesuré : sur
`test_477r24r1_slots_interface_offline.py`, **1 test = 15,0 s** contre **49,7 s pour les 59** — le
coût FIXE des fixtures est ~15 s et ne se divise pas (le dépôt porte 485 fixtures `scope="module"`
et 58 `scope="session"`). Et surtout : une sélection **intra-fichier casserait `probe_455`** — un
fichier dont tous les tests sont désélectionnés n'émet **aucun report**, donc devient
structurellement invisible (volet #455-r3).

## 5. L'obligation : pas un héritage, un CLIQUET à la collecte

La forme spontanée — une classe `TestOffline` portant `should_trigger = False` que les dérivées
seraient « obligées » de surcharger — ne tient pas, pour deux raisons :

- corpus réel : **711 fichiers, 5 080 tests, 100 % en fonctions de module, 0 méthode de classe** ;
- **en Python, hériter ne force aucune surcharge** : une dérivée distraite hériterait
  silencieusement de `False` et cesserait d'être jouée. C'est exactement #455.

D'où : `declencheur_guard.py`, enregistré comme **plugin** par le conftest racine (et non importé
hook par hook — `tests/conftest.py` lie déjà `pytest_sessionfinish` et `pytest_terminal_summary`
depuis `green_skip_guard`, et un module ne peut lier qu'un objet par nom). Il lit la déclaration
par `getattr` sur le **module déjà importé** : ni lecture, ni AST.

- Critère = la **COLLECTE** (`pytest_collection_modifyitems`), pas la sélection : `-k`/`-m`/
  `--deselect` filtrent après elle (#455-r3).
- Périmètre **dérivé** de `git ls-files` — jamais une allowlist.
- **DETTE** versionnée (`scripts/ratchets-486r15-dette-declencheurs.txt`) : poser l'obligation sèche
  rendrait `master` rouge sur 711 fichiers le jour de sa livraison, donc la ferait désarmer dans
  l'heure. Un fichier **neuf** hors dette est rouge tout de suite ; la dette ne peut que rétrécir,
  et tout élargissement apparaît dans un diff. `--sans-dette` joue le critère sec.
- Les fichiers de test **synthétiques** que déposent certains cliquets (`probe_455`) sont écartés
  par un filtre `git ls-files` **paresseux** (appelé seulement si un candidat existe).

## 6. La confrontation — la déclaration n'est jamais crue sur parole

`probe_486r15_declencheurs_tests.py` confronte chaque déclaration à **deux mesures** :

1. la **fermeture d'imports** du fichier (tous imports, y compris différés — un `import` dans un
   corps de test s'exécute bel et bien) **plus ses `conftest.py`**, que l'AST ne voit pas ;
2. les **témoins** de l'empreinte `probe_457` — les fichiers réellement OUVERTS, seuls à révéler un
   `read_text("data/...")` qu'aucun import ne montre.

⚠ Cette fermeture n'est **pas** celle d'`import_closure.py` (#486-r11), qui répond à « que charge
`import M` ? » et **exclut** les différés, à raison pour son critère. L'employer ici
**sous-approximerait**, et une sous-approximation dans un garde de couverture est un faux vert.

Coût mesuré : **2,5 s** pour les 711 fichiers (l'obligation) plus la fermeture des seuls déclarants.

## 7. Le capteur de visibilité (#467)

`loop_status.py` (hook `Stop`) porte désormais un poste **EMPREINTE** : deux `git ls-files` et une
lecture JSON, **aucun graphe, aucun AST**. Il signale un format périmé (`--since` refuse alors de
s'en servir) ou une couverture incomplète, avec le geste à poser. Tri-état strict : git muet,
empreinte illisible ou dépôt sans test offline sortent en **PAS MESURÉ** (contexte), jamais en zéro
fabriqué — ni alarmant, ni rassurant. Un dépôt sans fichier de test ne produit **aucun** signal :
le périmètre effondré reste gardé là où il a un sens (`probe_457` rend `FAIL shard VIDE`).

## 8. Ce qui n'est PAS couvert

- **8 déclarations sur 711.** Le mécanisme, le cliquet d'obligation et la dette sont livrés ;
  la généralisation ne l'est pas.
- La **répétition du socle** (11 chemins communs à toute déclaration) est imposée par le contrat :
  `ast.literal_eval` ne résout aucun nom, donc aucune constante partagée n'est lisible. Un module
  ajouté à la cascade des `conftest.py` fait rougir **toutes** les déclarations — c'est le garde qui
  fonctionne, mais c'est un coût de maintenance réel.
- `declencheur_cliquet.py` est **vendoré à l'identique** (même blob) depuis la branche de #486-r12,
  non encore mergée. Si les deux PR atterrissent, le conflit est add/add à contenu identique.
- Le résidu du 486-r8 (`git ls-files -s`, hash par blob sans lecture) est **mesuré ici — 274 ms
  pour 3 985 fichiers** — mais **non employé** : le diff rend la question sans objet.
