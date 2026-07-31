# #391 — un répertoire portait DEUX collecteurs `Directory`, et son conftest devenait invisible

**Défaut de HARNAIS** (pytest 9.1.1). Mesuré et fermé le 2026-08-01.

## Le symptôme

`pytest <S>/a.py <D>/b.py <S>/c.py`, avec `S` sous-répertoire de `D`, faisait échouer **le
troisième argument seulement** sur `ERROR ... fixture '<nom>' not found`, avec une liste
« available fixtures » amputée de tout `<S>/conftest.py`. Chaque **paire** passait, chaque
fichier **seul** passait.

Reproducteur d'origine — `18 passed, 4 errors` avant, `22 passed, 0 error` après :

```
cd scripts/python
python -m pytest -q \
  tests/engine/runner/test_fire_and_reposition_reduce_dmg_live.py \
  tests/engine/test_366r1_carrier_active_level_offline.py \
  tests/engine/runner/test_363_ability_states_default_live.py
```

Coût déjà payé : un lot de validation lu comme ROUGE alors que rien n'était cassé, et six
runs de bisection pour l'attribuer.

## La cause — trois étages, tous lus dans le pytest installé

1. `_pytest/main.py::Session.collect` — quand la dernière part à matcher est un **fichier**,
   pytest pose `handle_dupes = False` et **re-collecte le `Directory` PARENT**. Ce re-collect
   reconstruit ses enfants : les sous-`Directory` deviennent de **nouveaux objets**, et
   `Session._collection_cache` est écrasé avec eux. C'est l'argument `<D>/b.py` qui recrée
   `<D>/<S>`.
2. `_pytest/fixtures.py::FixtureManager.pytest_make_collect_report` — les fixtures d'un
   conftest sont attachées au `Directory` de son répertoire via
   `self._pending_conftests.pop(collector.path, None)`. Le `pop` est **destructif** : seul le
   PREMIER objet les reçoit.
3. `_pytest/fixtures.py::FixtureManager._matchfactories` — depuis pytest 9, la visibilité se
   décide par **identité d'objet** (`if fixturedef.node is not None: if fixturedef.node in
   parent_nodes`), plus par préfixe de nodeid.

Le `nodeid` des deux objets est **identique** (`tests/engine/runner`) : le défaut est
invisible à toute inspection par chaîne de caractères. Mesuré :
`Dir(tests/engine/runner)#…420448` puis `#…345904`, `fixturedef.node` sur le premier.

## Les deux candidats du diagnostic initial, ÉCARTÉS PAR MESURE

- **`--import-mode=importlib`** : déjà dans `pytest.ini` depuis son commit d'origine
  (`2920fa4d`), et le défaut se produit AVEC. Les trois conftest sont chargés sous des noms
  **distincts** (`tests.conftest`, `tests.engine.conftest`, `tests.engine.runner.conftest`) —
  il n'y a **aucune collision `sys.modules`**, contrairement à ce que l'hypothèse d'origine
  supposait.
- **Poser des `__init__.py`** : les `Dir` deviennent des `Package`, et le doublon persiste
  **à l'identique** (deux `Package(tests/engine/runner)` d'`id()` différents). `Package` dérive
  de `nodes.Directory` : les trois étages s'appliquent mot pour mot.

## Le correctif

`scripts/python/conftest.py` (nouveau, à la rootdir pytest) : le premier `Directory` vu pour
un chemin fait foi ; tout doublon ultérieur est remplacé par lui dans le rapport de collecte
de son parent. Le doublon n'étant jamais collecté, l'étage 2 n'a rien à ré-attacher et
l'étage 3 matche.

Ne touche **ni** à la déduplication des fichiers (les `Module` restent recréés), **ni** à
l'ordre d'exécution, **ni** aux scopes (aucune `FixtureDef` en double).

## Portée réelle — plus large que le cas rapporté

Le probe dérive du disque **3** couples `(D, S)` porteurs du motif : `tests ← tests/engine`,
`tests/engine ← tests/engine/runner`, `tests ← tests/engine/runner`. Les **trois** rougissent
sans le correctif — `tests/engine/conftest.py` était exposé autant que celui du runner.

## Gardes

- `scripts/python/probe_391_conftest_dir_identity.py` — MESURE. Dérive les couples du disque
  et joue une **collecte** (`--co`, aucun test exécuté, aucun runner, aucune session live) sur
  chaque triplet, en vérifiant **(a)** l'unicité des collecteurs `Directory` et **(b)** la
  résolution de chaque fixture demandée. Le troisième argument est choisi parmi les fichiers
  qui **consomment** réellement une fixture du conftest, sans quoi (b) resterait verte et vide.
- `scripts/python/tests/test_391_conftest_dir_identity_offline.py` — CLIQUET, rejoue le probe
  en sous-processus.

Preuve de rougeur sur l'état d'avant : probe `rc=1` / garde `1 failed` ; après, `rc=0` /
`1 passed`.

## Ce qui n'est PAS couvert

- La **borne de bruyance** reste conditionnelle : les trois conftest n'ont aucun nom de
  fixture en commun (10 / 6 / 20, intersections vides), donc l'échec était toujours bruyant.
  Le correctif rend la question sans objet, mais rien n'interdit deux conftest de partager un
  nom — aucune garde ne le surveille.
- Le correctif traite les collecteurs `Directory`. Un doublon d'une autre classe de collecteur
  (`Module`, `Class`) ne serait pas canonisé — non observé, non mesuré.
- Aucun correctif upstream n'est suivi : si pytest répare l'un des trois étages, la
  canonisation deviendra redondante (inoffensive) plutôt que nécessaire.
