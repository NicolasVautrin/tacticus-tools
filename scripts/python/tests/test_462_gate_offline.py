"""#462 -- ce que la gate `probe_462 --gate` promet, prouve OFFLINE.

Ce fichier n'entre dans aucune allowlist : il est `test_*.py` et n'est pas `_live.py`, donc le
perimetre DERIVE de `probe_457` le joue tout seul.

Il prouve les DEUX directions a chaque fois. Une gate qui ne sait que dire PASS est un cliquet
creux (#430/#439) ; une gate qui ne sait que dire FAIL est desarmee le lendemain.

ASCII only (cp1252).
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import probe_462_live_tests_status as P


# --------------------------------------------------------------------------- verdicts

def test_un_fichier_qui_passe_est_VERT():
    assert P._verdict({"passed": 3, "skipped": 0, "failed": 0, "error": 0, "xfailed": 0}) == "VERT"


def test_un_echec_est_ROUGE():
    assert P._verdict({"passed": 3, "failed": 1, "error": 0, "skipped": 0, "xfailed": 0}) == "ROUGE"
    assert P._verdict({"passed": 3, "failed": 0, "error": 1, "skipped": 0, "xfailed": 0}) == "ROUGE"


def test_un_fichier_INTEGRALEMENT_SKIPPE_est_ROUGE():
    """#455 : `passed == 0 and skipped > 0` = zero assertion evaluee. Le compter vert est
    exactement le faux negatif que ce depot a paye deux fois."""
    assert P._verdict({"passed": 0, "skipped": 8, "failed": 0, "error": 0, "xfailed": 0}) == "ROUGE"


def test_un_fichier_ENTIEREMENT_XFAIL_n_est_PAS_ROUGE():
    """Alignement sur `green_skip_guard` : xfail/xpass comptent comme JOUES -- l'assertion a bien
    ete evaluee, son echec etait attendu. Sans cette regle, tout fichier a xfail rougirait a tort,
    et un cliquet qui rougit a tort finit desarme."""
    assert P._verdict({"passed": 0, "skipped": 0, "failed": 0, "error": 0, "xfailed": 2}) == "VERT"
    assert P._verdict({"passed": 0, "skipped": 0, "failed": 0, "error": 0, "xpassed": 1,
                       "xfailed": 0}) == "VERT"


def test_un_fichier_SANS_AUCUN_TEST_est_VIDE_pas_VERT():
    """Un perimetre qui s'effondre ne doit pas se lire comme un succes (#455-r3)."""
    assert P._verdict({"passed": 0, "skipped": 0, "failed": 0, "error": 0, "xfailed": 0}) == "VIDE"


# --------------------------------------------------------------------------- JUnit

_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest">
 <testcase classname="tests.engine.runner.test_a_live" name="t_ok" time="1.5"/>
 <testcase classname="tests.engine.runner.test_a_live" name="t_xf" time="0.5">
   <skipped type="pytest.xfail" message="attendu"/></testcase>
 <testcase classname="tests.engine.runner.test_b_live" name="t_ko" time="2.0">
   <failure message="AssertionError: off != live"/></testcase>
 <testcase classname="tests.engine.runner.test_c_live" name="t_sk" time="0.1">
   <skipped type="pytest.skip" message="montage KO"/></testcase>
</testsuite></testsuites>"""


@pytest.fixture()
def junit(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(_XML, encoding="utf-8")
    return p


def test_le_XML_est_rattache_par_CLASSNAME_car_pytest_n_emet_PAS_d_attribut_file(junit):
    """Mesure du 2026-08-03 sur `junit_family=xunit2` (le defaut) : un `testcase` ne porte que
    `classname` et `name`. Une lecture par `file` rendrait ZERO report -- donc tous les fichiers
    en << NON JOUE >>, ce qui est precisement ce qu'un premier jet a produit."""
    assert all(c.get("file") is None for c in ET.fromstring(_XML).iter("testcase"))
    rels = ["tests/engine/runner/test_a_live.py", "tests/engine/runner/test_b_live.py",
            "tests/engine/runner/test_c_live.py"]
    vu = P._parse_junit(junit, P._classname_index(rels))
    assert set(vu) == set(rels)


def test_le_xfail_du_XML_n_est_PAS_compte_comme_un_skip(junit):
    rels = ["tests/engine/runner/test_a_live.py", "tests/engine/runner/test_b_live.py",
            "tests/engine/runner/test_c_live.py"]
    vu = P._parse_junit(junit, P._classname_index(rels))
    a = vu["tests/engine/runner/test_a_live.py"]
    assert (a["passed"], a["xfailed"], a["skipped"]) == (1, 1, 0)
    assert P._verdict(a) == "VERT"
    assert P._verdict(vu["tests/engine/runner/test_b_live.py"]) == "ROUGE"
    assert P._verdict(vu["tests/engine/runner/test_c_live.py"]) == "ROUGE"


def test_le_message_d_echec_est_RAPPORTE_VERBATIM(junit):
    """Le probe ne CLASSE pas PORT/MONTAGE/HARNAIS -- il ne peut pas (#533 : le message disait vrai
    sur le fait et faux sur la cause). Il doit donc rendre le symptome tel quel."""
    vu = P._parse_junit(junit, P._classname_index(["tests/engine/runner/test_b_live.py"]))
    assert "off != live" in " ".join(vu["tests/engine/runner/test_b_live.py"]["messages"])


def test_un_XML_absent_ne_rend_pas_un_vert(tmp_path):
    assert P._parse_junit(tmp_path / "rien.xml", {}) == {}


# --------------------------------------------------------------------------- la gate

_CIBLE = "tests/engine/runner/test_x_live.py"


@pytest.fixture()
def gate(tmp_path, monkeypatch):
    """Cable la gate sur un ledger jetable et un diff simule. tmpdir SYSTEME (#455) : jamais une
    ecriture sous `scripts/python/`, que la banque enumere en parallele."""
    ledger = tmp_path / "attestations.json"
    monkeypatch.setattr(P, "ledger_path", lambda: ledger)
    monkeypatch.setattr(P, "_live_in_diff", lambda ref: ([_CIBLE], "1 fichier (simule)"))
    monkeypatch.setattr(P, "_blobs", lambda rels: {r: "blobCOURANT" for r in rels})

    def ecrire(entree):
        ledger.write_text(json.dumps({"fichiers": {_CIBLE: entree}}), encoding="utf-8")
    return ecrire


def test_SANS_attestation_la_gate_ROUGIT(gate):
    assert P._do_gate("origin/master") == 1


def test_avec_attestation_VERTE_au_BON_blob_la_gate_PASSE(gate):
    gate({"verdict": "VERT", "_blob": "blobCOURANT"})
    assert P._do_gate("origin/master") == 0


def test_une_attestation_VERTE_a_un_AUTRE_blob_ne_vaut_RIEN(gate):
    """Le coeur du dispositif. #533 : le fichier a ete MODIFIE (398 lignes) puis livre rouge. Si
    l'attestation survivait au changement du fichier, la gate serait verte sur exactement le cas
    qu'elle existe pour voir."""
    gate({"verdict": "VERT", "_blob": "blobDAVANT"})
    assert P._do_gate("origin/master") == 1


def test_une_attestation_ROUGE_ne_passe_pas(gate):
    gate({"verdict": "ROUGE", "_blob": "blobCOURANT"})
    assert P._do_gate("origin/master") == 1


def test_un_diff_SANS_fichier_live_ne_demande_RIEN(tmp_path, monkeypatch):
    """68 % des commits mesures sont dans ce cas -- c'est ce qui rend la gate gratuite."""
    monkeypatch.setattr(P, "ledger_path", lambda: tmp_path / "vide.json")
    monkeypatch.setattr(P, "_live_in_diff", lambda ref: ([], "0 fichier"))
    assert P._do_gate("origin/master") == 0


def test_une_ref_INCONNUE_est_un_REFUS_pas_un_vert(monkeypatch):
    """<< Un echec RENDU se lit comme une mesure >> : rendre 0 ici ferait passer une gate qui n'a
    RIEN verifie pour une gate verte."""
    monkeypatch.setattr(P, "_live_in_diff", lambda ref: (None, "ref inconnue"))
    assert P._do_gate("pasunref") == 2


# --------------------------------------------------------------------------- perimetre

def test_le_perimetre_est_DERIVE_et_disjoint_de_celui_de_probe_457():
    """Les deux cliquets partitionnent les fichiers de test collectes : aucun fichier n'est joue
    deux fois, et aucun n'echappe aux deux. C'est ce que #457-r6 a du prouver a la main pour les
    trois entrees `pytest_*` retirees."""
    import probe_457_offline_tests_green as P457
    live = set(P.live_files())
    offline = set(P457.candidate_files())
    assert live and offline
    assert not (live & offline), "un fichier ne peut pas etre dans les deux perimetres"
    assert all(r.endswith("_live.py") for r in live)


def test_le_ledger_n_est_PAS_sous_scripts_python(tmp_path):
    """#455 : la banque enumere `scripts/python/**` en parallele ; y deposer un fichier le fait
    apparaitre puis disparaitre sous les pieds d'un voisin (`probe_440` R3)."""
    p = P.ledger_path()
    assert p.name.endswith(".json")
    assert "python" not in p.parent.name, p
    assert p.parent == P.repo_root() / "scripts", p


def test_le_ledger_est_VERSIONNE_sinon_l_anciennete_redevient_invisible():
    """Sous `logs/` (gitignore) il mourrait avec le worktree : chaque agent repartirait de
    << aucune mesure >>, ce qui est exactement le vice repare."""
    import subprocess
    p = P.ledger_path()
    r = subprocess.run(["git", "-C", str(P.repo_root()), "check-ignore", "-q", str(p)],
                       capture_output=True)
    assert r.returncode != 0, "%s est gitignore -- le ledger ne survivrait pas au worktree" % p
