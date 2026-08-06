# #486-r12 -- LE DECLENCHEUR D'UN CLIQUET, ET LE GARDE QUI LE CONFRONTE A LA MESURE

**Groupe A (11 cliquets) + le MECANISME que les groupes B et C appliqueront.**
`scripts/ratchets.ps1` porte 48 entrees pour 36 scripts, toutes rejouees sans aucune selection.
Les tests ont `probe_457 --since` depuis #457 ; les cliquets n'avaient rien.

## 1. La forme, et les trois choses que le foyer ajoute

Chaque cliquet declare chez lui, au niveau module, sous une forme executable :

```python
#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/python/**/*.py",),   # globs, style git pathspec
    "build": False,       # son verdict depend-il d'un artefact du JEU installe ?
    "toujours": False,    # True = rien ne permet de le borner
    "raison": "<ce que le cliquet LIT, et pourquoi ces chemins suffisent>",
}
```

Contrat, matcher et validation : `scripts/python/declencheur_cliquet.py`. **Trois ajouts sont
faits par le foyer, jamais par le declarant** : le **source du cliquet lui-meme** (l'ecrire 46
fois serait 46 occasions de l'oublier), **`data/symbols/**` quand `build: True`**, et rien
d'autre -- la banque ne change aucun verdict, elle choisit qui court.

**`**/` vaut ZERO segment ou plus** (semantique git pathspec), donc `scripts/python/**/*.py`
couvre `scripts/python/probe_x.py`. C'est deliberement l'inverse de `pathlib` : ce depot a paye
la confusion deux fois -- #458 (967 fichiers versionnes dans aucun seau de `probe_431`) et
#457-r5 (les 24 fichiers poses directement sous `tests/`, les plus lourds du perimetre).

**Le defaut est `toujours: True`.** Un declencheur trop LARGE coute du temps ; trop ETROIT
fabrique un faux vert -- le cliquet n'est pas joue quand son gisement vient de se rouvrir.
L'asymetrie est totale, donc le doute se resout du cote large.

## 2. Le garde : `probe_486r12_declencheurs.py`

Perimetre **DERIVE** de `scripts/ratchets.ps1` (via `probe_439.banque_par_texte`, foyer unique) :
une entree neuve y entre d'elle-meme. Deux etages :

| | |
|---|---|
| **[1] DECLARATION** | le script porte-t-il un `DECLENCHEUR` bien forme ? Sinon **ROUGE**, nomme. |
| **[2] MESURE** | ce qu'il **OUVRE reellement** est-il couvert par ce qu'il **DECLARE** ? |

L'etage 2 est le point : croire le source du declarant reviendrait a lui demander de
s'auto-attester. `declencheur_trace` pose un audit hook sur `open` -- meme idee que
`probe_457._FilesPerTest` -- et se **propage aux sous-process python** par un `sitecustomize`
jetable (dont le chemin est retire de `sys.path` sitot charge : le laisser ferait importer les
helpers de `scripts/python` a la place de ceux d'un arbre JETABLE, ce que `probe_319` monte).

**L'empreinte est VERSIONNEE** (`scripts/declencheurs-empreinte.tsv`, 338 lignes pour 11
cliquets, ~30 par cliquet) et porte le **sha du source** de chaque cliquet : si le source a
bouge, l'entree n'est pas SERVIE, elle est **PERIMEE donc NON MESUREE**. Regle de
`verdict_cache` (#486-r1) : une attestation qui ne peut que manquer ne peut pas mentir.
Les lectures sont agregees par **(dossier, extension)** avec **deux temoins** (min et max) --
c'est ce qui borne la taille, et c'est une **approximation assumee** : un glob discriminant sur
le NOM de base pourrait couvrir les deux temoins sans couvrir un troisieme fichier du groupe.

**Tri-etat** (#471) : `0` vert, `1` rouge, `99` **INDISPONIBLE** -- banque illisible, entree
absente de l'empreinte, entree perimee, ou **mesure a zero process trace** (un run tue avant
d'avoir rien trace laisserait un perimetre vide, donc trivialement couvert : un vert fabrique
par une panne est pire qu'un rouge).

**Ce que la mesure NE VOIT PAS, et qui est DIT** : un sous-process non-python (`git`, `pwsh`)
lit hors du hook -- le cliquet est marque `MESURE INCOMPLETE`, sa confrontation ne vaut que dans
un sens (ce qui est VU doit etre couvert). Idem pour un fichier dont seule l'EXISTENCE decide.
La mesure borne par le BAS ; elle ne dit jamais qu'un declencheur est suffisant.

## 3. Ce que la MESURE a trouve, et qu'aucune relecture n'aurait donne

1. **`probe_313` lit `lib/*.py` A LA RACINE du depot** (son etape 3 derive son perimetre de
   `git ls-files *.py`). Un declencheur ecrit a l'oeil aurait porte `scripts/python/**/*.py` --
   **trop ETROIT**, et le faux vert aurait ete invisible.
2. **CINQ des onze lisent `data/seed-bc.json` sans le nommer nulle part** (`probe_181` fait
   76 lignes et un seul `import`) : il arrive par la cascade d'import.
3. `probe_391` lit `scripts/python/pytest.ini` ; `probe_437r1r1r1` lit `data/seed-bc.json` en
   plus de ses deux tables de symboles.
4. **Un bug du traceur, trouve parce que la mesure a rendu ZERO sous-process opaque** alors que
   quatre des onze lancent `git ls-files`. Sous Windows,
   `sys.audit("subprocess.Popen", exe, args, ...)` passe `exe = None` et `args` = une **ligne de
   commande**, pas une liste : `subprocess.run(["git", "--version"])` emet
   `(None, 'git --version', None, None)`. Ne lire que `exe` laissait `MESURE INCOMPLETE`
   silencieux -- le faux vert que le tri-etat existe pour interdire.
5. **Une forme A dans le garde lui-meme**, attrapee par sa propre contre-epreuve :
   `def charger(cls, chemin=EMPREINTE)` fige le chemin A L'IMPORT, donc `EMPREINTE` etait
   insubstituable et le test ne pouvait pas monter de depot jetable (cf. CLAUDE.md, formes
   A/B/C).

## 3bis. Contre-epreuves livrees

- **Sur l'arbre REEL, pas en synthetique.** Retirer `data/seed-bc.json` du declencheur de
  `probe_181`, re-mesurer, et le garde le **NOMME** : `LU hors perimetre : data/seed-bc.json`,
  `1 de fidelite`, `rc=1`. Restauration -> `0 de fidelite`, et `probe_181` revient **bit-a-bit**
  (`git diff` vide).
- **Le rouge du normalisateur est venu de la mesure elle-meme** (cf. SS3.5), pas d'un test :
  la premiere confrontation des onze a accuse `probe_319` de lire `.gitignore` alors qu'il le
  DECLARAIT.
- **56 tests offline** (`scripts/python/tests/test_486r12_declencheurs_offline.py`), montage
  100 % jetable : semantique du glob dans les deux sens, 9 fautes de forme chacune NOMMEE,
  lecture par AST d'un module qui `raise` en tete, et les cinq verdicts du garde -- VERT,
  ROUGE de fidelite, ROUGE de declaration, `toujours: True` non confronte, et les trois
  chemins de `99` (banque illisible, empreinte absente, empreinte perimee, zero process trace).

⚠ **Toucher un cliquet PERIME son empreinte**, par construction (la cle est le sha de son
source). Le garde rend alors `99 NON MESUREE` -- pas un vert, pas un rouge -- et dit quoi
rejouer : `--mesurer --only <id>`. C'est le comportement voulu : un declencheur qu'on vient de
modifier n'a pas encore ete confronte.

## 4. Les onze du groupe A

Cout **ISOLE**, mesure en serie le 2026-08-07 sur machine partagee (8 process python d'autres
agents) -- somme **394,9 s**.

| cliquet | isole | portee | `chemins` declares | `build` |
|---|---|---|---|---|
| `probe_437r1r1r1` | 4,0 s | voisinage + build | `scripts/python/**/*.py`, `data/seed-bc.json` | oui |
| `probe_120` | 6,9 s | voisinage + jeu | `scripts/python/**/*.py`, `data/boards/**`, `data/seed-bc.json` | oui |
| `probe_181` | 8,8 s | voisinage | `scripts/python/**/*.py`, `data/seed-bc.json` | non |
| `probe_313` | 15,1 s | voisinage (tout le Python du depot) | `**/*.py`, `data/seed-bc.json`, son cache | oui |
| `probe_449r2` | 15,2 s | voisinage | `scripts/python/engine/**/*.py` | non |
| `probe_365` | 17,3 s | voisinage | `frida/**`, `.gitignore`, `**/.gitignore` | non |
| `probe_433r4r1r4r2` | 19,6 s | voisinage | `scripts/python/engine/**/*.py` | non |
| `probe_464` | 37,1 s | **un fichier** | `scripts/python/**/*.py` | non |
| `probe_391` | 65,6 s | **`toujours: True`** | (declares, non confrontes) | non |
| `probe_273` | 69,8 s | voisinage | `scripts/python/**/*.py`, `.gitignore`, `**/.gitignore`, `data/**` | non |
| `probe_319` | 135,5 s | voisinage **+ contre-epreuve** | idem `probe_273` | non |

**`probe_464` est le seul a portee UN FICHIER** : `sites(rel, src)` parse et decide seul, sans
resolution d'import ni croisement. **`probe_319` est mixte** : ses etapes 3 et 4 sont des
contre-epreuves (portee la plus etroite du depot : {son source, celui de `probe_273`}), mais ses
etapes 1/2/2bis confrontent l'ancien balayage au nouveau **sur l'arbre reel**, ou un fichier neuf
peut creer un orphelin de couverture -- donc aucune reduction possible.
**Aucun des onze n'est a portee << depot entier irreductiblement >>** (celle de `probe_468`, ou
l'unicite n'a pas de voisinage).

Deux entrees `.gitignore` / `data/**` sont declarees **sans etre mesurables** : elles sont lues
par `git check-ignore` et `git ls-files data`, hors de portee du hook. Elles viennent de la
lecture du CRITERE, et c'est le sens de << un declencheur se prend large >>.

**Etat a la livraison** : `11 declares / 0 mal formes / 10 bornes`, **0 faute de fidelite**, et
**6 des onze marques MESURE INCOMPLETE** (ils lancent `git`). Les **25 scripts restants** de la
banque sont la dette des groupes B et C, et le garde les NOMME un par un.

⚠ **Le cout de la MESURE n'est pas le cout du cliquet** : sous audit hook et machine chargee,
`probe_273` passe de 69,8 a 122,4 s et `probe_313` de 15,1 a 76,4 s -- ce dernier surtout parce
que poser sa declaration a invalide son cache (SS7). La mesure se paie une fois par cliquet et
par modification de son source, jamais a chaque run.

## 5. Le seul `toujours: True` : `probe_391`, et ce n'est pas un renoncement

Son perimetre de FICHIERS est parfaitement borne (1 071 fichiers mesures). Ce n'est pas lui qui
impose le defaut : **son SUJET n'est pas dans l'arbre.** Il mesure l'identite des collecteurs
`_pytest.nodes.Directory` et la resolution des `FixtureDef` -- c'est la **version de pytest
installee** qui decide, et le depot ne porte **aucun manifeste de dependances**. Une mise a jour
de pytest renverse son verdict sans qu'une ligne du depot bouge.

C'est exactement la forme de `build: True`, **moins le `data/symbols/CURRENT` versionne** qui
rend celui-la bornable : un changement de build SE VOIT dans un diff, un upgrade de pytest NON.

## 6. Non couvert

- **La selection n'est PAS cablee** dans `ratchets.ps1`, et le garde n'entre PAS dans la banque :
  les deux gestes attendent les groupes B et C (25 scripts restants). Le garde est donc **ROUGE
  par construction** jusque-la, et il **NOMME** les scripts qui ne declarent pas -- c'est sa
  mesure de la dette, pas une panne.
- **L'agregation (dossier, extension)** : cf. SS2, un glob discriminant sur le nom de base n'est
  garde que par ses deux temoins.
- **`.git/info/exclude` et le gitignore global** de la machine : dans aucun arbre, donc dans
  aucun declencheur (`probe_365`, `probe_273`).
- **Une empreinte peut vieillir sans que le cliquet change** : elle se perime au sha du SOURCE
  DU CLIQUET, pas a celui de ses helpers. Un helper qui se met a lire ailleurs n'invalide rien
  -- `--mesurer` reste la voie.

## 7. Effet de bord a connaitre : poser un `DECLENCHEUR` dans un cliquet CACHE

`probe_313` est l'un des trois cliquets a cache versionne (#486-r1), et son **contexte** porte le
sha de son propre source : y ecrire une declaration **invalide le cache entier** et le fichier
est reecrit. **Churn mesure : 4 insertions / 4 suppressions sur 1 447 entrees** -- le contenu se
re-remplit a l'identique, seule la ligne de contexte et les entrees des fichiers reellement
touches bougent. Le fichier regenere est commite avec la tranche, jamais fusionne a la main.
Les groupes B et C toucheront `probe_477r24r1` et `probe_477r25` de la meme facon (4 965 et
6 682 entrees) -- **s'attendre au meme geste, pas s'en alarmer**.
