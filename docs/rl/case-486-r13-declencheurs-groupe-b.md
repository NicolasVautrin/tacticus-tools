# #486-r13 — Le DÉCLENCHEUR des cliquets, groupe B (11 entrées)

Mesuré le 2026-08-07. **Re-dériver ces chiffres, jamais les citer.**

Chaque cliquet du groupe déclare, dans son propre source, **ce qui doit changer pour qu'il
puisse changer d'avis** — lu dans son critère, jamais deviné :

```python
#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {"chemins": (...), "build": bool, "toujours": bool, "raison": "..."}
```

**Aucun critère n'est touché** : on ajoute une déclaration, pas un jugement. Le mécanisme qui
la consomme et le garde qui la tient vivent ailleurs (#486-r12).

## 1. Les onze, et leur portée

Coût **isolé**, séquentiel, cache chaud. Portées : *fichier* / *voisinage* / *dépôt entier* /
*son propre source*.

| cliquet | coût | portée | build | ce qui le déclenche |
|---|---:|---|---|---|
| `probe_366camo` | 0,9 s | voisinage | non | `engine/**` + racine `scripts/python` + `data/seed-bc.json` |
| `probe_366pos` | 1,5 s | voisinage | non | `engine/**` seul — il n'importe RIEN |
| `probe_421` | 1,8 s | voisinage | non | **union** avec `probe_229` |
| `probe_229` | 6,9 s | voisinage | non | `engine/**` + racine + `data/seed-bc.json` |
| `probe_443r2` | 13,5 s | voisinage | non | `engine/**` seul — il n'importe RIEN |
| `probe_443r2b1` | 16,1 s | voisinage | non | `engine/**` + racine + `data/seed-bc.json` |
| `probe_366bcp` | 17,8 s | voisinage | non | tout `scripts/python/**` |
| `probe_440` | 20,8 s | voisinage | non | `scripts/python/**` **+ `scripts/ratchets.ps1`** |
| `probe_443r1c` | 31,6 s | voisinage | **oui** | `scripts/python/**` + les **deux** builds |
| `probe_274` | 54,0 s | dépôt entier | **oui** | tous les `.py`, le JS du frontend, les deux builds |
| `probe_455` | 125,4 s | voisinage | non | le garde, son câblage, `pytest.ini`, `tests/**` versionné |

**Zéro en `toujours: True`** : les onze bornent leur périmètre, tous l'écrivent dans leur propre
source (`ENGINE.rglob`, `PY_ROOT.rglob`, `os.walk(REPO)`, `git ls-files <testpaths>`). Ce n'est
pas une facilité — c'est ce que la contre-épreuve du §2 a **vérifié**.

**Aucun des onze n'est une contre-épreuve pure** (portée « son propre source ») : chacun mesure
le dépôt, même quand il porte un auto-test de détecteur en étape 0 — cet auto-test tourne sur des
sources *synthétiques* écrites dans le probe, mais le verdict global lit le dépôt derrière.
Cette portée-là est celle de `probe_439`, hors groupe.

Deux déclencheurs incluent ce que le cliquet **GARDE**, pas seulement ce qu'il **LIT**, et
c'est le point non dérivable de la tranche :

- **`probe_421`** garde la couverture du RAIL de `probe_229` : un cliquet de couverture qui se
  rejouerait *moins* souvent que le cliquet couvert laisserait passer exactement son gisement.
- **`probe_440`** n'applique son étage R3 (« un cliquet qui écrit sous `scripts/python` ») qu'aux
  entrées de la **banque**, périmètre dérivé de `scripts/ratchets.ps1`. Un probe déjà présent et
  déjà fautif devient rouge le jour où on l'**inscrit** — sans qu'aucun `.py` ne bouge. Omettre le
  `.ps1` rendrait ce cliquet silencieux dans le seul régime où la course de #455 se produit.

## 2. LA PRISE : quatre déclencheurs étaient TROP ÉTROITS, et la lecture ne le montrait pas

Contre-épreuve : `sys.addaudithook` sur `open`, tout le run, confronté aux globs déclarés. Un
chemin **lu et non couvert** est le faux vert que la tranche vise.

`probe_229`, `probe_421`, `probe_366camo`, `probe_443r2b1` ouvraient tous les quatre
**`data/seed-bc.json`**, absent de leurs globs. Cause **unique** et invisible à toute lecture
des imports : `engine/services/damage_modifiers.py` lit le seed BC **au niveau module**
(`_DMG_CFG`), donc *toute* cascade traversant `engine.entities.effects` l'ouvre. Aucun des
quatre ne le nomme, aucun ne le sait.

⚠ **Et le premier tracer ne le voyait pas non plus** — il armait son hook **après**
`import_module(probe)`, donc restait aveugle à toute la cascade d'import : il rendait
« 0 non couvert » sur les quatre. Armé avant le premier import, **11/11** sont couverts. Un
instrument de contre-épreuve se vérifie comme le reste ; celui-ci a d'abord confirmé une
déclaration fausse.

## 3. Ce que la forme imposée ne sait PAS exprimer

- **Les entrées HORS DÉPÔT.** `gameconfig.py` lit le gameconfig **du jeu**
  (`AppData/LocalLow/…/gameconfig/<hash>.json`) et il bouge à chaque mise à jour. Il n'entre au
  verdict d'aucun des onze (il est `lru_cache`-lazy et jamais atteint — vérifié à la trace), mais
  aucun champ ne pourrait le dire s'il y entrait : `chemins` est un glob du dépôt, `build` désigne
  `data/symbols/<build>`.
- **L'OUTILLAGE.** `probe_455` lance `pytest` en sous-processus : une montée de version de pytest
  peut déplacer son verdict sans qu'un octet du dépôt change. Idem pour la version de Python de
  tous les autres. Ce n'est ni un chemin ni un build.
- **`data/seed-bc.json` est une troisième espèce** : entrée versionnée, donc exprimable en
  `chemins` — mais elle change à la **migration de build**, exactement comme `data/symbols/`.
  Un lecteur qui croit que « build » couvre toutes les dépendances au build se trompe.

## 4. Rouge PRÉEXISTANT rencontré, hors périmètre

`probe_471` rend `rc=1`, et il le rend **aussi sur `origin/master` pur** (arbre extrait par
`git archive`, mêmes trois rouges, même cause) : son faux dépôt jetable copie
`probe_457_offline_tests_green.py` et `pytest.ini`, mais **pas `repo_read.py`**, dont
`probe_457` a acquis la dépendance depuis sa lecture parallèle. Ses trois contre-épreuves
échouent donc toutes sur `ModuleNotFoundError: No module named 'repo_read'` — un échec de
**montage**, pas une mesure. C'est le faux rouge que `scripts/ratchets.ps1` cite déjà en tête.
Non corrigé ici : hors du groupe B.

## Re-dériver

Le coût : `python scripts/python/<probe>.py`, un par un (le parallélisme fausse l'isolé).

La contre-épreuve de couverture tient en dix lignes, et **son hook s'arme avant le premier
import du probe** — c'est tout ce qui la sépare d'un faux vert (§2) :

```python
import fnmatch, runpy, sys
from pathlib import Path
lus = set()
sys.addaudithook(lambda ev, a: lus.add(str(a[0])) if ev == "open" else None)
try:
    runpy.run_module(nom_du_probe, run_name="__main__")   # AVANT tout import du probe
except SystemExit:
    pass
import importlib
globs = importlib.import_module(nom_du_probe).DECLENCHEUR["chemins"]
# + tout `m.__file__` de sys.modules ; relatif au dépôt ; ignorer __pycache__ ;
# un chemin non couvert par `fnmatch` contre `globs` = déclencheur TROP ÉTROIT.
```

Le contrôle de forme, lui, se dérive des quatre clés : types exacts, `raison` ASCII pur
(cp1252), et **aucun glob mort** — un glob qui ne matche aucun fichier de `git ls-files` ne se
déclencherait jamais, donc c'est un faux vert déguisé en déclaration.
