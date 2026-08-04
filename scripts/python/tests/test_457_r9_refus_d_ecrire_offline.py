"""#464 -- GARDE : `probe_457` REFUSE de mesurer hors de son CWD, et n'ecrit JAMAIS une mesure vide.

CE QUE CETTE GARDE EST SEULE A VOIR
-----------------------------------
Un echec de MONTAGE qui se PERSISTE en se faisant passer pour une mesure.

Mesure du 2026-08-04, en montage reel : lance depuis la RACINE du depot au lieu de
`scripts/python/`, `probe_457 --measure` rend `pytest rc=4` (usage error, << no tests ran in
0.00s >>) -- et ECRIT quand meme. 129 fichiers chronometres a **0,0 s**, une empreinte a
<< 0 fichier(s) de test >>, soit **632 lignes supprimees** du fichier VERSIONNE
`scripts/ratchets-457-footprints.json`, et un `rc=1` annonce << poids ecrits, mais l'arbre est
ROUGE >> -- un verdict de gisement pour un echec de montage.

C'est le patron << un echec RENDU se lit comme une MESURE >>, en pire : il PERSISTE.

ET LE DEGAT N'EST PAS CELUI QU'ON CROIT. Le fichier dit lui-meme qu'une empreinte perimee
<< selectionne TROP et retombe continument sur le rejeu total >>. Une empreinte VIDEE fait
l'INVERSE : `impacted_files` interprete << absent de `par_test` >> comme << ce test n'ouvre aucun
fichier du depot, ses dependances sont d'import pur >>, donc il le SAUTE. Un `par_test` vide fait
donc sauter tout test dont la seule dependance est une donnee (`data/symbols/...`, `docs/...`,
`frida/hooks/*.ts`) -- un FAUX VERT partage, versionne.

CE QUE CETTE GARDE NE DIT PAS
-----------------------------
Elle ne garde pas que la mesure est JUSTE, seulement qu'une mesure VIDE n'est jamais ecrite et
qu'un rc d'usage n'est jamais rendu comme un verdict. Elle ne s'appuie sur aucun etat de `logs/`
ni sur le CWD reel de la passe : tous les cas sont montes sur des stubs et un tmpdir.

ASCII only (cp1252).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_457_offline_tests_green as P                                # noqa: E402


class _Horloge:
    """Stub de `_TimePerFile` : `sec` (secondes cumulees) et `n` (nombre de reports) par fichier."""

    def __init__(self, sec=None, n=None) -> None:
        self.sec = dict(sec or {})
        self.n = dict(n or {})


class _Empreinte:
    """Stub de `_FilesPerTest`. Pas d'audit hook -- on ne veut pas en poser un dans la session."""

    def __init__(self, globales=(), par_test=None) -> None:
        self.globales = set(globales)
        self.par_test = dict(par_test or {})


@pytest.fixture
def sorties(monkeypatch, tmp_path):
    """Detourne les DEUX sorties du probe vers un tmpdir SYSTEME (#455 : jamais sous
    `scripts/python/`, que la banque enumere en parallele)."""
    poids = tmp_path / "457-durations.json"
    emp = tmp_path / "ratchets-457-footprints.json"
    monkeypatch.setattr(P, "_weights_path", lambda: poids)
    monkeypatch.setattr(P, "_footprints_path", lambda: emp)
    return poids, emp


# --------------------------------------------------------------------------- LE GARDE DE CWD

def test_le_garde_de_cwd_ACCEPTE_scripts_python(monkeypatch):
    monkeypatch.chdir(PYDIR)
    assert P._exiger_cwd() == "", "le probe doit accepter son propre repertoire"


@pytest.mark.parametrize("forme", ["minuscules", "separateurs"])
def test_le_garde_de_cwd_ACCEPTE_les_ECRITURES_EQUIVALENTES(monkeypatch, forme):
    """Le mode de defaillance le plus couteux : un garde trop STRICT.

    S'il comparait des CHAINES au lieu de chemins resolus, la banque entiere (8 shards) rendrait 99
    des que l'appelant ecrit le chemin autrement -- et un `Set-Location` PowerShell, un `cd` shell
    ou un chemin herite d'une variable ne garantissent ni la casse ni le separateur sous Windows.
    Le refus doit porter sur le REPERTOIRE, pas sur son orthographe."""
    chemin = str(PYDIR).lower() if forme == "minuscules" else str(PYDIR).replace("\\", "/")
    monkeypatch.chdir(chemin)
    assert P._exiger_cwd() == "", "garde trop strict : %r rejete" % chemin


def test_le_garde_de_cwd_REFUSE_ailleurs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    refus = P._exiger_cwd()
    assert refus, "le probe DOIT refuser un CWD qui n'est pas `scripts/python`"
    assert "REFUS" in refus and str(P.EX_NON_MESURE) in refus
    assert refus.isascii(), "sortie console cp1252 -- ASCII only"


@pytest.mark.parametrize("argv", [["--measure"], ["--measure-missing"], ["--shard", "0/8"],
                                  ["--shard", "3/8", "--since", "origin/master"]])
def test_main_hors_cwd_rend_99_SANS_RIEN_JOUER(monkeypatch, tmp_path, argv):
    """Le coeur de #464 : le refus doit tomber AVANT tout travail et avant toute ecriture.

    Les deux portes de sortie sont piegees -- si le garde manquait, l'une d'elles leverait, et le
    test rougirait SANS avoir rien ecrit ni rien joue."""
    def _boom(*a, **k):
        raise AssertionError("le probe a joue/ecrit alors que le CWD est FAUX")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(P, "_measure", _boom)
    monkeypatch.setattr(P, "pytest", type("_P", (), {"main": staticmethod(_boom)}))
    assert P.main(argv) == P.EX_NON_MESURE


def test_list_reste_jouable_hors_cwd(monkeypatch, tmp_path):
    """`--list` n'invoque pas pytest (l'enumeration passe par `git -C <racine>`), donc le garde ne
    doit PAS le bloquer -- sinon il deviendrait un obstacle sans gisement."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(P, "pytest",
                        type("_P", (), {"main": staticmethod(
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("joue")))}))
    assert P.main(["--shard", "0/8", "--list"]) == 0


# ------------------------------------------------------------------- LE REFUS D'ECRIRE UNE MESURE

PERIMETRE = ["tests/a_offline.py", "tests/b_offline.py"]


@pytest.mark.parametrize("rc", sorted(P.RC_PYTEST_SANS_MESURE))
def test_un_rc_pytest_NON_EXPLOITABLE_n_ecrit_RIEN(sorties, rc):
    poids, emp = sorties
    horloge = _Horloge(sec={"tests/a_offline.py": 1.5}, n={"tests/a_offline.py": 4})
    got = P._ecrire_mesure(PERIMETRE, PERIMETRE, horloge, _Empreinte(), rc, 2.0, {})
    assert got == P.EX_NON_MESURE, "rc=%d doit rendre << non mesure >>, jamais un verdict" % rc
    assert not poids.exists(), "les poids ont ete ecrits sur un rc non exploitable"
    assert not emp.exists(), "l'empreinte VERSIONNEE a ete ecrite sur un rc non exploitable"


def test_aucun_report_du_tout_n_ecrit_RIEN(sorties):
    """Le montage EXACT du 2026-08-04 : pytest a rendu 4 et pas un fichier n'a produit de report.

    Garde separee du critere sur `rc` : un `rc=0` sur une collecte integralement vide reste une
    mesure vide, et c'est elle qui vide le fichier versionne."""
    poids, emp = sorties
    got = P._ecrire_mesure(PERIMETRE, PERIMETRE, _Horloge(), _Empreinte(), 0, 2.0, {})
    assert got == P.EX_NON_MESURE
    assert not poids.exists() and not emp.exists()


def test_une_mesure_REELLE_est_bien_ecrite(sorties):
    """CONTRE-EPREUVE indispensable : sans elle, un refus SYSTEMATIQUE passerait les tests
    ci-dessus -- le probe ne mesurerait plus jamais rien, sous un vert."""
    poids, emp = sorties
    horloge = _Horloge(sec={"tests/a_offline.py": 1.25, "tests/b_offline.py": 0.5},
                       n={"tests/a_offline.py": 3, "tests/b_offline.py": 2})
    empreinte = _Empreinte(globales=["data/seed-bc.json"],
                           par_test={"tests/a_offline.py": {"data/symbols/x.tsv"}})
    assert P._ecrire_mesure(PERIMETRE, PERIMETRE, horloge, empreinte, 0, 3.0, {}) == 0

    import json
    ecrits = json.loads(poids.read_text(encoding="utf-8"))
    assert ecrits == {"tests/a_offline.py": 1.25, "tests/b_offline.py": 0.5}
    lu = json.loads(emp.read_text(encoding="utf-8"))
    assert lu["_globales"] == ["data/seed-bc.json"]
    assert lu["par_test"] == {"tests/a_offline.py": ["data/symbols"]}, "granularite REPERTOIRE"
    assert lu["_commit"], "sans `_commit`, `impacted_files` refuse de s'appliquer"


def test_des_tests_ROUGES_n_empechent_PAS_la_mesure(sorties):
    """`rc=1` = des tests ont echoue, mais les fichiers ONT ete joues : durees et empreinte sont
    valides. Confondre ce cas avec un echec de montage retirerait toute mesure a un arbre rouge."""
    poids, _ = sorties
    horloge = _Horloge(sec={"tests/a_offline.py": 2.0}, n={"tests/a_offline.py": 1})
    assert P._ecrire_mesure(PERIMETRE, PERIMETRE, horloge, _Empreinte(), 1, 3.0, {}) == 1
    assert poids.exists(), "un arbre ROUGE reste une mesure valide des durees"


# ------------------------------------------------------------------------ LA MESURE INCREMENTALE

def test_la_mesure_incrementale_FUSIONNE_et_ne_touche_PAS_l_empreinte(sorties):
    """#463 -- le mode nominal. Les poids des fichiers non rejoues survivent ; l'empreinte, dont le
    `_commit` horodate l'ENSEMBLE, n'est pas rafraichie sur une mesure partielle."""
    poids, emp = sorties
    connus = {"tests/a_offline.py": 9.0, "tests/supprime_offline.py": 42.0}
    horloge = _Horloge(sec={"tests/b_offline.py": 0.75}, n={"tests/b_offline.py": 2})

    got = P._ecrire_mesure(PERIMETRE, ["tests/b_offline.py"], horloge, None, 0, 1.0, connus)
    assert got == 0

    import json
    ecrits = json.loads(poids.read_text(encoding="utf-8"))
    assert ecrits["tests/a_offline.py"] == 9.0, "un poids CONNU et non rejoue doit survivre"
    assert ecrits["tests/b_offline.py"] == 0.75, "le fichier neuf doit prendre sa mesure"
    assert "tests/supprime_offline.py" not in ecrits, (
        "un poids HORS PERIMETRE doit etre purge -- sinon il gonfle le `defaut` de `bins_of`")
    assert not emp.exists(), (
        "la mesure incrementale a REECRIT l'empreinte : son `_commit` pretendrait une fraicheur "
        "qu'elle n'a pas, et `impacted_files` sauterait des tests")


def test_les_deux_modes_de_mesure_s_EXCLUENT():
    assert P.main(["--measure", "--measure-missing"]) == 2


# --------------------------------------------------------------- LE FOYER UNIQUE D'ECRITURE

def _fonctions_qui_ecrivent(source: str) -> set:
    """Les fonctions de niveau module qui contiennent, DIRECTEMENT ou dans une fonction imbriquee,
    un appel d'ecriture de fichier."""
    ecritures = {"write_text", "write_bytes", "writelines", "mkdir"}
    arbre = ast.parse(source)
    trouvees = set()
    for noeud in arbre.body:
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for interne in ast.walk(noeud):
            if not isinstance(interne, ast.Call):
                continue
            f = interne.func
            nom = getattr(f, "attr", None) or getattr(f, "id", None)
            if nom in ecritures or (nom == "open" and any(
                    isinstance(a, ast.Constant) and isinstance(a.value, str)
                    and a.value[:1] in ("w", "a", "x") for a in interne.args)):
                trouvees.add(noeud.name)
                break
    return trouvees


def test_TOUTES_les_ecritures_du_probe_passent_par_le_foyer_unique():
    """La propriete STRUCTURELLE qui rend le refus ci-dessus non contournable.

    Sans elle, une ecriture ajoutee demain ailleurs dans le fichier echapperait a la decision --
    exactement ce qui s'etait passe : la decision (<< l'arbre est ROUGE >>) etait imprimee APRES
    les deux `write_text`."""
    source = Path(P.__file__).read_text(encoding="utf-8")
    trouvees = _fonctions_qui_ecrivent(source)
    assert trouvees, "aucune ecriture detectee -- le detecteur est casse, ce test ne prouve rien"
    assert trouvees == {"_ecrire_mesure"}, (
        "ecriture(s) de fichier HORS du foyer unique `_ecrire_mesure` : %s. Toute sortie du probe "
        "doit passer par lui, sinon une mesure vide peut encore etre persistee." % sorted(trouvees))
