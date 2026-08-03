"""#457-r8 -- garde de la SELECTION PAR DIFF de `probe_457` (`--since`).

Une selection par diff est le SEUL endroit de ce depot ou l'on peut fabriquer un FAUX VERT : elle
retire des tests du perimetre. Ce fichier garde la propriete qui la rend acceptable --
**tout ce qui n'est pas PROUVE independant est rejoue**, et un doute rejoue TOUT en le DISANT.

Aucune dependance a `logs/` : l'empreinte y vit (gitignore, #455), donc chaque test injecte la
sienne. Un checkout frais joue donc ces gardes a l'identique.

ASCII only (console cp1252).
"""
import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import probe_457_offline_tests_green as P  # noqa: E402


PERIMETRE = ["tests/a_offline.py", "tests/b_offline.py", "tests/c_offline.py"]


@pytest.fixture
def empreinte(monkeypatch):
    """Injecte une empreinte SYNTHETIQUE et un diff controle."""
    def poser(globales, par_test, changes, mods=None, inverse=None, incertains=None):
        monkeypatch.setattr(P, "_footprints",
                            lambda: {"_globales": globales, "par_test": par_test})
        monkeypatch.setattr(P, "_changed", lambda ref: changes)
        monkeypatch.setattr(P, "_import_graph",
                            lambda m: (inverse or {}, incertains or set()))
        if mods is not None:
            import subprocess

            class _R:
                returncode = 0
                stdout = "\n".join(mods)

            monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    return poser


def test_une_ref_inconnue_rejoue_TOUT_et_le_dit(monkeypatch):
    monkeypatch.setattr(P, "_changed", lambda ref: None)
    retenus, raison = P.impacted_files(PERIMETRE, "pas_une_ref")
    assert retenus == PERIMETRE, "une ref inconnue DOIT rejouer tout le perimetre"
    assert "TOUT rejoue" in raison, "le rejeu total doit etre DIT, pas silencieux"


def test_sans_empreinte_mesuree_on_rejoue_TOUT(monkeypatch):
    monkeypatch.setattr(P, "_changed", lambda ref: ["scripts/python/engine/x.py"])
    monkeypatch.setattr(P, "_footprints", dict)
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE, "sans empreinte, aucune independance n'est PROUVEE"
    assert "AUCUNE empreinte" in raison


def test_un_changement_dans_une_lecture_GLOBALE_rejoue_TOUT(empreinte):
    empreinte(globales=["data/seed-bc.json"], par_test={}, changes=["data/seed-bc.json"], mods=[])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE, "une lecture globale n'est attribuable a personne -> impacte tout"
    assert "GLOBALE" in raison


def test_les_pyc_ne_declenchent_PAS_un_rejeu_total(empreinte):
    # 521 des 527 lectures globales mesurees sont des `.pyc` : les compter rendrait la selection
    # inutile, et ils ne peuvent PAS apparaitre dans un diff (bytecode non versionne).
    empreinte(globales=["scripts/python/__pycache__/x.cpython-313.pyc"],
              par_test={}, changes=["docs/rl/note.md"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == [], "un .pyc en globale ne doit pas forcer le rejeu total"


def test_un_fichier_de_test_MODIFIE_est_toujours_retenu(empreinte):
    empreinte(globales=[], par_test={}, changes=["scripts/python/tests/b_offline.py"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert "tests/b_offline.py" in retenus, "un test modifie DOIT etre rejoue"


def test_un_module_INCERTAIN_est_toujours_retenu(empreinte):
    # import dynamique / fichier illisible : on ne PRETEND pas savoir de quoi il depend.
    empreinte(globales=[], par_test={}, changes=["scripts/python/engine/x.py"], mods=[],
              incertains={"scripts/python/tests/c_offline.py"})
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert "tests/c_offline.py" in retenus, "un module a resolution incertaine impacte par defaut"


def test_la_cloture_ARRIERE_des_imports_est_suivie(empreinte):
    # a_offline importe m2, qui importe m1. Changer m1 doit retenir a_offline.
    empreinte(globales=[], par_test={},
              changes=["scripts/python/engine/m1.py"],
              mods=["scripts/python/engine/m1.py"],
              inverse={"scripts/python/engine/m1.py": {"scripts/python/engine/m2.py"},
                       "scripts/python/engine/m2.py": {"scripts/python/tests/a_offline.py"}})
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert "tests/a_offline.py" in retenus, "la dependance TRANSITIVE doit etre suivie"


def test_un_non_py_retient_les_tests_qui_lisent_son_REPERTOIRE(empreinte):
    # Granularite REPERTOIRE : un test qui lit docs/rl/x.md doit rejouer si docs/rl/y.md change --
    # sinon un fichier NEUF, absent de toute empreinte, passerait entre les mailles.
    empreinte(globales=[], par_test={"tests/c_offline.py": ["docs/rl/x.md"]},
              changes=["docs/rl/y.md"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == ["tests/c_offline.py"], "granularite repertoire attendue, ni plus ni moins"


def test_la_selection_est_INCLUSE_dans_le_perimetre(empreinte):
    empreinte(globales=[], par_test={"tests/a_offline.py": ["data/symbols/z.tsv"]},
              changes=["data/symbols/z.tsv"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert set(retenus) <= set(PERIMETRE), "la selection ne peut pas INVENTER un fichier"
    assert len(retenus) == len(set(retenus)), "aucun doublon"


def test_un_diff_VIDE_ne_joue_rien(empreinte):
    empreinte(globales=[], par_test={}, changes=[], mods=[])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD")
    assert retenus == [], "aucun changement -> aucun test a rejouer"
    assert "aucun fichier change" in raison


def test_le_perimetre_reel_est_NON_VIDE(monkeypatch):
    # Anti-vacuite : sans cela, tous les tests ci-dessus passeraient sur un perimetre effondre.
    reel = P.candidate_files()
    assert len(reel) > 50, "perimetre reel effondre (%d) -- les gardes ne prouveraient rien" % len(reel)
