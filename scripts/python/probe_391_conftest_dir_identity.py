"""#391 -- MESURE : un repertoire n'a-t-il qu'UN SEUL collecteur `Directory` par session,
et toutes les fixtures de conftest restent-elles visibles ?

CE QUE CE PROBE ATTRAPE
-----------------------
Passer des fichiers en arguments dans l'ordre `<D>/<S>/a.py`, `<D>/b.py`, `<D>/<S>/c.py`
faisait perdre au TROISIEME argument toutes les fixtures du `conftest.py` de `<S>`
(`ERROR ... fixture '<nom>' not found`). Le nodeid des deux collecteurs `<S>` est pourtant
IDENTIQUE : le defaut est invisible a toute inspection par chaine de caracteres, seule
l'identite d'objet le revele. Mecanisme complet et candidats ecartes : `conftest.py` a la
rootdir pytest (`scripts/python/conftest.py`).

CE QU'IL FAIT
-------------
Il DERIVE du disque tous les couples `(D, S)` capables de porter le motif -- `S` strictement
sous `D`, `S` portant un `conftest.py` et au moins DEUX fichiers de test, `D` portant au
moins UN fichier de test direct -- puis, pour chacun, joue une COLLECTE (`--co`, aucun test
execute, aucun runner monte, aucune session live touchee) sur le triplet et verifie DEUX
proprietes :

  (a) IDENTITE   -- chaque repertoire apparait sous un seul et meme objet `Directory` dans
                    les chaines de collecte de tous les items ;
  (b) VISIBILITE -- pour chaque item, chaque argument de sa signature qui n'est pas un
                    parametre de `parametrize` se resout en au moins une `FixtureDef`.

(b) est le symptome utilisateur, (a) sa cause. On mesure les deux : (a) seul pourrait rester
vert si pytest changeait de strategie de matching, (b) seul ne dirait pas ou regarder.

Usage :
    python probe_391_conftest_dir_identity.py [--verbose]

rc = 0 si toutes les proprietes tiennent, 1 sinon. ASCII only (cp1252).
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
from pathlib import Path

import pytest
from _pytest import nodes

HERE = Path(__file__).resolve().parent
TESTS_ROOT = HERE / "tests"

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#: MESURE : 1 071 fichiers -- `scripts/python/tests/**`, `pytest.ini`, la cascade d'import des
#: conftest (`data/seed-bc.json` compris). Le perimetre de FICHIERS est donc parfaitement
#: borne ; ce n'est pas lui qui impose `toujours`.
DECLENCHEUR = {
    "chemins": ("scripts/python/**/*.py", "scripts/python/pytest.ini", "data/seed-bc.json"),
    "build": False,
    "toujours": True,
    "raison": "SON SUJET N'EST PAS DANS L'ARBRE. Il mesure l'identite des collecteurs "
              "`_pytest.nodes.Directory` et la resolution des `FixtureDef` : c'est la VERSION "
              "DE PYTEST INSTALLEE qui decide, et elle ne se lit dans aucun fichier versionne "
              "-- le depot ne porte aucun manifeste de dependances. Une mise a jour de pytest "
              "peut donc renverser ce verdict sans qu'une seule ligne du depot bouge, "
              "exactement comme un changement de build pour `data/symbols`, mais SANS le "
              "`data/symbols/CURRENT` versionne qui rend celui-la bornable. Les `chemins` "
              "restent ecrits parce qu'ils sont VRAIS et qu'ils disent ce qu'il lit -- mais "
              "sous `toujours: True` le garde ne les CONFRONTE pas (accuser un declarant qui "
              "se rejoue de toute facon dissuaderait d'ecrire le defaut prudent).",
}

_DIRECTORY = getattr(nodes, "Directory", None)


def _fixturedefs(fixturemanager, argname, item):
    """`getfixturedefs` prend un NODE depuis pytest 9, un nodeid avant. On tente les deux
    plutot que de rendre un faux rouge sur une version differente."""
    try:
        return fixturemanager.getfixturedefs(argname, item)
    except (TypeError, AttributeError):
        return fixturemanager.getfixturedefs(argname, item.nodeid)


class _CollectionChecker:
    """Plugin de verification -- n'execute aucun test, lit l'arbre de collecte."""

    def __init__(self):
        self.violations: list[str] = []

    def pytest_collection_modifyitems(self, session, config, items):
        fixturemanager = session._fixturemanager
        canonical: dict[Path, object] = {}
        duplicated: set[Path] = set()

        for item in items:
            for node in item.listchain():
                if _DIRECTORY is None or not isinstance(node, _DIRECTORY):
                    continue
                seen = canonical.setdefault(node.path, node)
                if seen is not node and node.path not in duplicated:
                    duplicated.add(node.path)
                    self.violations.append(
                        "IDENTITE : le repertoire %s porte DEUX collecteurs %s distincts "
                        "(nodeid identique %r) -- les fixtures de son conftest ne sont "
                        "visibles que sous le premier"
                        % (
                            node.path.relative_to(HERE),
                            type(node).__name__,
                            node.nodeid,
                        )
                    )

            info = getattr(item, "_fixtureinfo", None)
            if info is None:
                continue
            callspec = getattr(item, "callspec", None)
            params = set(callspec.params) if callspec is not None else set()
            for argname in info.argnames:
                if argname in params:
                    continue
                if not _fixturedefs(fixturemanager, argname, item):
                    self.violations.append(
                        "VISIBILITE : %s demande la fixture %r, introuvable depuis son "
                        "noeud" % (item.nodeid, argname)
                    )


def _test_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("test_*.py") if p.is_file())


def _fixture_names(conftest_path: Path) -> set[str]:
    """Noms des fixtures declarees par un conftest, lus TEXTUELLEMENT (le probe ne doit pas
    importer le conftest : c'est justement son import qui est en cause)."""
    names: set[str] = set()
    pending = False
    for line in conftest_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("@pytest.fixture") or stripped.startswith("@fixture"):
            pending = True
            continue
        if pending:
            match = re.match(r"(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", stripped)
            if match:
                names.add(match.group(1))
                pending = False
            elif stripped.startswith("@"):
                continue
            else:
                pending = False
    return names


def _consumers(files: list[Path], names: set[str]) -> list[Path]:
    """Fichiers de test qui NOMMENT au moins une de ces fixtures -- ce sont les seuls sur
    lesquels la propriete VISIBILITE est discriminante."""
    if not names:
        return []
    pattern = re.compile(r"\b(%s)\b" % "|".join(sorted(re.escape(n) for n in names)))
    return [
        path
        for path in files
        if pattern.search(path.read_text(encoding="utf-8", errors="replace"))
    ]


def _motif_couples() -> list[tuple[Path, Path]]:
    """Tous les couples (D, S) du disque capables de porter le motif de #391."""
    couples: list[tuple[Path, Path]] = []
    if not TESTS_ROOT.is_dir():
        return couples
    for sub in sorted(TESTS_ROOT.rglob("conftest.py")):
        carrier = sub.parent
        if len(_test_files(carrier)) < 2:
            continue
        for ancestor in carrier.parents:
            if ancestor == HERE:
                break
            if _test_files(ancestor):
                couples.append((ancestor, carrier))
    return couples


def _collect(args: list[str]) -> tuple[int, list[str], str]:
    """La collecte imbriquee ecrit sa propre liste de tests : on la CAPTURE pour que le
    rapport du probe reste lisible, et on ne la ressort qu'en cas d'echec."""
    checker = _CollectionChecker()
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = pytest.main(
            ["-q", "--co", "-p", "no:cacheprovider", *args], plugins=[checker]
        )
    return int(code), checker.violations, buffer.getvalue()


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    os.chdir(HERE)

    if _DIRECTORY is None:
        print("ECHEC : ce pytest n'expose pas `_pytest.nodes.Directory` -- la propriete")
        print("        d'identite n'est pas mesurable, le probe ne peut PAS conclure.")
        return 1

    couples = _motif_couples()
    if not couples:
        print("ECHEC : aucun couple (D, S) porteur du motif trouve sous tests/ -- le probe")
        print("        ne mesure alors RIEN, ce qui n'est pas un vert.")
        return 1

    failures = 0
    for parent, carrier in couples:
        carrier_files = _test_files(carrier)
        parent_files = _test_files(parent)

        # Le TROISIEME argument est celui qui perd ses fixtures : on y met de preference un
        # fichier qui en CONSOMME, sinon la propriete VISIBILITE reste verte et vide et seule
        # la cause (IDENTITE) rougirait.
        consumers = _consumers(carrier_files, _fixture_names(carrier / "conftest.py"))
        third = consumers[0] if consumers else carrier_files[1]
        first = next(path for path in carrier_files if path != third)
        triplet = [
            str(first.relative_to(HERE)).replace(os.sep, "/"),
            str(parent_files[0].relative_to(HERE)).replace(os.sep, "/"),
            str(third.relative_to(HERE)).replace(os.sep, "/"),
        ]
        label = "%s <- %s" % (
            str(parent.relative_to(HERE)).replace(os.sep, "/"),
            str(carrier.relative_to(HERE)).replace(os.sep, "/"),
        )
        if verbose:
            print("[motif] %s" % label)
            for arg in triplet:
                print("        %s" % arg)

        code, violations, output = _collect(triplet)
        if code != 0:
            failures += 1
            print("ECHEC [%s] : la collecte a rendu rc=%d" % (label, code))
            for line in output.splitlines()[-15:]:
                print("  | %s" % line)
        if violations:
            failures += 1
            print("ECHEC [%s] : %d violation(s)" % (label, len(violations)))
            for violation in violations:
                print("  - %s" % violation)
        if code == 0 and not violations:
            print("OK [%s] : collecteurs uniques, fixtures toutes visibles" % label)

    if failures:
        print("")
        print("=> #391 REOUVERT : voir scripts/python/conftest.py (canonisation des")
        print("   collecteurs Directory) -- le correctif est absent ou inoperant.")
        return 1

    print("")
    print("=> OK : %d motif(s) verifie(s), aucune violation." % len(couples))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
