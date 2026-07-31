"""Conftest RACINE (rootdir pytest = `scripts/python`) -- un seul role : garantir qu'un
repertoire n'a JAMAIS deux collecteurs `Directory` dans une meme session (#391).

LE DEFAUT (pytest 9.x, mesure le 2026-08-01)
--------------------------------------------
Passer plusieurs fichiers en arguments dans l'ordre `<dir>/<sous-dir>/a.py`,
`<dir>/b.py`, `<dir>/<sous-dir>/c.py` faisait DISPARAITRE toutes les fixtures du
`conftest.py` de `<sous-dir>` pour le TROISIEME fichier -- `ERROR ... fixture '<nom>'
not found`, avec une liste « available fixtures » amputee de ce conftest. Chaque PAIRE
d'arguments passait, chaque fichier SEUL passait : seule la sequence declenchait.

Les trois etages du mecanisme, tous LUS dans le pytest installe :

1. `_pytest/main.py::Session.collect` -- quand la derniere part a matcher est un FICHIER,
   pytest pose `handle_dupes = False` (« files given directly multiple times on the command
   line should not be deduplicated ») et RE-COLLECTE le `Directory` PARENT. Ce re-collect
   reconstruit les enfants : les sous-`Directory` deviennent de NOUVEAUX objets, et
   `Session._collection_cache` est ecrase avec eux. C'est l'argument `<dir>/b.py` qui
   declenche le re-collect de `<dir>`, donc la recreation de `<dir>/<sous-dir>`.

2. `_pytest/fixtures.py::FixtureManager.pytest_make_collect_report` -- les fixtures d'un
   conftest sont attachees au `Directory` de son repertoire via
   `self._pending_conftests.pop(collector.path, None)`. Le `pop` est DESTRUCTIF : le
   conftest n'est parse qu'au PREMIER `Directory` de ce chemin. Le second objet, cree en 1,
   ne recoit donc JAMAIS les fixtures.

3. `_pytest/fixtures.py::FixtureManager._matchfactories` -- depuis pytest 9 la visibilite se
   decide par IDENTITE D'OBJET (`if fixturedef.node is not None: if fixturedef.node in
   parent_nodes`), plus par prefixe de nodeid. Le `nodeid` des deux objets est pourtant
   identique (`tests/engine/runner`) : c'est ce qui rend le defaut INVISIBLE a toute
   inspection par chaine de caracteres.

=> La fixture reste enregistree, avec le bon `baseid`, attachee au PREMIER objet ; l'item du
troisieme argument pend sous le SECOND ; l'identite ne matche pas ; la fixture est introuvable.

CE QUI A ETE ECARTE, PAR MESURE
-------------------------------
- `--import-mode=importlib` : deja actif dans `pytest.ini` depuis l'origine, et le defaut se
  produit AVEC. Mesure : les trois conftest sont bien charges sous des noms DISTINCTS
  (`tests.conftest`, `tests.engine.conftest`, `tests.engine.runner.conftest`) -- il n'y a
  aucune collision `sys.modules`.
- Poser des `__init__.py` : mesure, les `Dir` deviennent des `Package` et le doublon persiste
  A L'IDENTIQUE (deux `Package(tests/engine/runner)` d'`id()` differents, `fixturedef.node`
  pointant sur le premier). `Package` derive de `nodes.Directory` : les trois etages
  ci-dessus s'appliquent mot pour mot.

LE CORRECTIF
------------
On canonise les collecteurs : le premier `Directory` vu pour un chemin donne fait foi, et
tout doublon ulterieur est REMPLACE par lui dans le rapport de collecte de son parent. Le
doublon n'etant jamais collecte, l'etage 2 n'a rien a re-attacher et l'etage 3 matche.

On ne touche NI a la deduplication des fichiers (les `Module` restent recrees, donc passer
deux fois le meme fichier en argument collecte toujours deux fois), NI a l'ordre d'execution
des tests, NI aux scopes (aucune `FixtureDef` en double n'est creee).

Garde : `probe_391_conftest_dir_identity.py` (mesure) et
`tests/engine/test_391_conftest_dir_identity_offline.py` (cliquet).

ASCII only (cp1252).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _pytest import nodes

# `nodes.Directory` existe depuis pytest 8. En son absence le hook devient inerte : c'est le
# probe/test de garde qui le signale, pas un no-op silencieux.
_DIRECTORY = getattr(nodes, "Directory", None)

#: Attribut pose sur la `Session` -- le registre vit le temps d'UNE session, jamais au niveau
#: module (un `pytest.main()` appele deux fois dans le meme process repartirait sinon avec
#: des collecteurs de la session precedente).
_REGISTRY_ATTR = "_tacticus_canonical_directories"


def _registry(session) -> dict[Path, object]:
    registry = getattr(session, _REGISTRY_ATTR, None)
    if registry is None:
        registry = {}
        setattr(session, _REGISTRY_ATTR, registry)
    return registry


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    report = yield
    if _DIRECTORY is None or not isinstance(collector, _DIRECTORY):
        return report

    registry = _registry(collector.session)
    # Le collecteur courant fait foi pour son propre chemin s'il est le premier vu.
    registry.setdefault(collector.path, collector)

    children = list(report.result)
    replaced = False
    for index, child in enumerate(children):
        if not isinstance(child, _DIRECTORY):
            continue
        canonical = registry.setdefault(child.path, child)
        if canonical is not child:
            children[index] = canonical
            replaced = True
    if replaced:
        report.result = children
    return report
