"""#935-r1 -- GARDE de l'axe `.py` de l'empreinte : le troisieme mecanisme de `--since`.

CE QUE CE FICHIER PROTEGE. `impacted_files` traitait les `.py` par le SEUL graphe d'imports, et
l'empreinte (`dirs`) ne servait que pour les changements HORS-`.py`. Un cliquet qui BALAIE des
`.py` sans les importer n'avait donc AUCUNE arete vers le fichier qu'il accuse -- mesure de #935 :
`--since <merge>~1` manquait **6 des 13** cas rouges connus, dont un a **90 %** de perimetre
retenu. Ce n'etait pas une question d'etroitesse, c'etait un AXE ABSENT.

TROIS PROPRIETES, ET IL FAUT LES TROIS :

 1. **la lecture APPLICATIVE d'un `.py` est mesuree, la lecture d'IMPORT ne l'est pas** -- le
    discriminant est pris a l'ECRITURE, sur la frame appelante. Sans lui, `py` vaudrait `dirs` et
    tout test qui importe `engine/` serait retenu par n'importe quel changement de `engine/` ;
 2. **la SOUS-TRAITANCE est un tri-etat, pas un zero** -- un test qui lance un processus fils
    n'ouvre rien lui-meme ; son axe n'est pas VIDE, il est NON MESURABLE, et il rejoue ;
 3. **une entree ANCIENNE ne se lit pas << ne balaie rien >>** -- elle retombe sur les `.py` de ses
    temoins, ce qui SUR-selectionne et le DIT.

S'y ajoute la CONTRE-EPREUVE de `probe_935` : sa classe AST confrontee a l'empreinte mesuree. Le
sens dangereux (AST dit selectionnable / la mesure voit un balayage) doit valoir ZERO ; il valait
**19** au premier passage, ce qui est la raison d'etre du probe.

Aucune dependance a une session live : 100 % offline. ASCII only (console cp1252).
"""


#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_457_offline_tests_green.py",
        "scripts/python/probe_935_cliquets_insellectionnables.py",
        "scripts/python/probe_935r1_contre_epreuve_classes.py",
        "scripts/ratchets-457-footprints.json",
        # Les POIDS : `candidate_files` / `bins_of` les ouvrent quand la confrontation monte le
        # perimetre REEL. Chemin EXACT plutot qu'un `hors_confrontation` -- un bypass se justifie
        # quand la fermeture ne PEUT pas borner le fichier ; ici elle le peut, a un chemin pres.
        "scripts/ratchets-457-durations.json",
        "scripts/python/tests/**", "scripts/python/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Les trois foyers sous test, l'EMPREINTE versionnee qu'ils confrontent, et l'arbre "
              "`scripts/python/**` dont la classe AST de `probe_935` est une FONCTION.",
}

import subprocess
import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import probe_457_offline_tests_green as P            # noqa: E402
import probe_935_cliquets_insellectionnables as P935  # noqa: E402
import probe_935r1_contre_epreuve_classes as CE       # noqa: E402


PERIMETRE = ["tests/a_offline.py", "tests/b_offline.py", "tests/c_offline.py"]


def _e(dirs=(), py=None, temoins=(), fils=False):
    """Une entree d'empreinte. `py=None` = axe NON MESURE (entree ecrite avant #935-r1)."""
    e = {"_at": 1, "_commit": "contexte", "dirs": list(dirs), "temoins": list(temoins)}
    if py is not None:
        e["py"] = list(py)
    if fils:
        e["fils"] = True
    return e


@pytest.fixture
def empreinte(monkeypatch):
    """Empreinte SYNTHETIQUE + diff controle + AUCUNE declaration -- meme montage que #457-r8."""
    def poser(globales, par_test, changes, mods=None, inverse=None, incertains=None):
        monkeypatch.setattr(P, "_footprints",
                            lambda: {"_format": P.FORMAT_EMPREINTE, "_globales": globales,
                                     "par_test": par_test})
        monkeypatch.setattr(P, "_changed", lambda ref: changes)
        monkeypatch.setattr(P, "_import_graph", lambda m: (inverse or {}, incertains or set()))
        monkeypatch.setattr(P, "declencheurs_du_perimetre", lambda perim, racine=None: ({}, {}))
        monkeypatch.setattr(P, "_modules_du_graphe",
                            lambda racine=None: {m2: m2 for m2 in (mods or [])})
    return poser


# ================================================================================ 1. LA SELECTION

def test_un_py_BALAYE_retient_le_test_qui_le_lit(empreinte):
    """LE CAS DE #935 : le `.py` change n'est importe PAR PERSONNE, il est LU."""
    par_test = {rel: _e(py=[]) for rel in PERIMETRE}
    par_test["tests/c_offline.py"] = _e(py=["scripts/python/engine"])
    empreinte(globales=[], par_test=par_test, changes=["scripts/python/engine/predict.py"],
              mods=["scripts/python/engine/predict.py"])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == ["tests/c_offline.py"], (
        "le balayeur DOIT etre retenu, et lui seul -- sinon l'axe selectionne tout le monde")
    assert "balayage .py" in raison, "la cause doit etre NOMMEE, pas fondue dans `hors .py`"


def test_un_py_IMPORTE_ne_retient_PAS_un_axe_MESURE_ET_VIDE(empreinte):
    """LA NON-REGRESSION QUI FAIT LE PRIX DU DISCRIMINANT.

    Si l'axe `py` recopiait `dirs`, tout test qui IMPORTE `engine/` serait retenu par n'importe
    quel changement de `engine/` -- la selection ne selectionnerait plus rien (mesure de #935 :
    la mediane de retention est deja de 90 %, le graphe d'imports y suffit)."""
    par_test = {rel: _e(dirs=["scripts/python/engine"], py=[]) for rel in PERIMETRE}
    empreinte(globales=[], par_test=par_test, changes=["scripts/python/engine/predict.py"],
              mods=["scripts/python/engine/predict.py"])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == [], (
        "`dirs` porte le repertoire par une lecture HORS-.py ; un axe `py` MESURE ET VIDE dit "
        "<< je n'ai lu aucun `.py` applicatif >>, et cela ne doit rien retenir")


def test_une_entree_SANS_axe_py_retombe_sur_ses_TEMOINS_et_le_DIT(empreinte):
    """TRI-ETAT : la cle ABSENTE n'est PAS << ne balaie rien >>."""
    par_test = {rel: _e(py=[]) for rel in PERIMETRE}
    par_test["tests/a_offline.py"] = _e(temoins=["scripts/python/engine/predict.py"])
    empreinte(globales=[], par_test=par_test, changes=["scripts/python/engine/damage.py"],
              mods=["scripts/python/engine/damage.py"])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == ["tests/a_offline.py"], "l'entree ancienne doit rester couverte"
    assert "repli temoins" in raison, "le REPLI doit etre dit -- il sur-selectionne"


def test_le_repli_IGNORE_la_propre_source_du_test(empreinte):
    """Un test qui TOMBE fait lire sa source par la traceback de pytest. Ce n'est pas une
    dependance : sans ce retrait, tout fichier ROUGE se declare balayeur de son propre
    repertoire -- donc retenu par tout changement d'un test VOISIN."""
    par_test = {rel: _e(py=[]) for rel in PERIMETRE}
    par_test["tests/b_offline.py"] = _e(temoins=["scripts/python/tests/b_offline.py"])
    empreinte(globales=[], par_test=par_test, changes=["scripts/python/tests/a_offline.py"],
              mods=["scripts/python/tests/a_offline.py"])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert "tests/b_offline.py" not in retenus, (
        "la lecture de SA PROPRE source ne doit pas faire de `b` un balayeur de `tests/`")
    assert retenus == ["tests/a_offline.py"], "seul le fichier du diff est retenu"


def test_la_SOUS_TRAITANCE_rejoue_sur_un_py_et_se_TAIT_sur_un_md(empreinte):
    """Ce que le hook d'audit ne franchit pas : la frontiere de PROCESS."""
    par_test = {rel: _e(py=[]) for rel in PERIMETRE}
    par_test["tests/c_offline.py"] = _e(py=[], fils=True)

    empreinte(globales=[], par_test=par_test, changes=["scripts/python/engine/predict.py"],
              mods=["scripts/python/engine/predict.py"])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == ["tests/c_offline.py"], "un axe NON MESURABLE rejoue sur tout `.py`"
    assert "sous-traite" in raison

    empreinte(globales=[], par_test=par_test, changes=["docs/rl/note.md"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == [], (
        "la sous-traitance ne doit pas degenerer en `toujours` : un diff sans `.py` ne la "
        "declenche pas")


def test_l_axe_py_n_OTE_jamais_un_fichier_de_la_selection(empreinte):
    """PROPRIETE DE SURETE : ce mecanisme est purement ADDITIF. Il ne peut pas fabriquer de faux
    vert -- au pire il fait payer du temps de test."""
    par_test = {rel: _e(py=["scripts/python/engine"]) for rel in PERIMETRE}
    changes = ["scripts/python/engine/predict.py", "docs/rl/x.md"]
    empreinte(globales=[], par_test=par_test, changes=changes,
              mods=["scripts/python/engine/predict.py"])
    avec, _ = P.impacted_files(PERIMETRE, "HEAD~1")

    par_test_sans = {rel: _e(py=[]) for rel in PERIMETRE}
    empreinte(globales=[], par_test=par_test_sans, changes=changes,
              mods=["scripts/python/engine/predict.py"])
    sans, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert set(sans) <= set(avec), "l'axe ne peut qu'AJOUTER des fichiers a la selection"


# ================================================================== 2. LA MESURE (face ECRITURE)

@pytest.fixture
def sonde():
    """FABRIQUE de `_FilesPerTest`, enracinee ou l'appelant veut -- jamais sur le depot.

    ⚠ C'est une FABRIQUE, et non une sonde deja posee, pour une raison MESUREE : l'evenement
    d'audit `open` couvre AUSSI les ECRITURES. Une sonde posee par la fixture enregistrait le
    `write_text` qui FABRIQUE le module du cas -- et cette ecriture-la, faite par `pathlib`, est
    APPLICATIVE. Le cas << l'import n'entre pas dans l'axe >> passait alors au vert pour la
    mauvaise raison, ou au rouge pour une raison qui n'etait pas la sienne. Les fichiers se creent
    AVANT la sonde.

    ⚠ `sys.addaudithook` est GLOBAL et IRREVERSIBLE : la sonde survit au test. Sans effet ici --
    son prefixe ne matche qu'un `tmp_path`."""
    def poser(racine, courant="tests/x_offline.py"):
        s = P._FilesPerTest(racine)
        s.courant = courant
        return s
    return poser


def test_une_lecture_APPLICATIVE_de_py_entre_dans_l_axe(sonde, tmp_path):
    cible = tmp_path / "paquet" / "mod_applicatif.py"
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text("VAL = 1\n", encoding="utf-8")
    s = sonde(tmp_path)
    cible.read_text(encoding="utf-8")
    lus = s.py_par_test.get("tests/x_offline.py", set())
    assert "paquet/mod_applicatif.py" in lus, (
        "une lecture de source faite par le code du test EST une dependance")


def test_une_lecture_d_IMPORT_n_entre_PAS_dans_l_axe(sonde, tmp_path, monkeypatch):
    """LE DISCRIMINANT, ET LA PREUVE QU'IL MORD.

    On force l'import a lire la SOURCE (bytecode desactive) : sans le filtre, ce `.py` entrerait
    dans l'axe et le repertoire de tout module importe deviendrait une dependance de balayage."""
    paquet = tmp_path / "paquet_import"
    paquet.mkdir()
    (paquet / "mod_importe_935r1.py").write_text("VAL = 2\n", encoding="utf-8")
    s = sonde(tmp_path)
    monkeypatch.syspath_prepend(str(paquet))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    sys.modules.pop("mod_importe_935r1", None)

    import importlib

    assert importlib.import_module("mod_importe_935r1").VAL == 2
    sys.modules.pop("mod_importe_935r1", None)

    tous = s.par_test.get("tests/x_offline.py", set())
    appli = s.py_par_test.get("tests/x_offline.py", set())
    assert "paquet_import/mod_importe_935r1.py" in tous, (
        "ANTI-VACUITE : si l'import n'a pas ouvert la source, ce cas ne prouve RIEN -- le filtre "
        "n'aurait rien eu a filtrer")
    assert "paquet_import/mod_importe_935r1.py" not in appli, (
        "une source ouverte PAR LE CHARGEUR est deja couverte par le graphe d'imports")


def test_un_PROCESSUS_FILS_marque_l_entree(sonde, tmp_path):
    s = sonde(tmp_path)
    subprocess.run([sys.executable, "-c", "pass"], capture_output=True, check=False)
    assert "tests/x_offline.py" in s.fils, (
        "l'audit hook ne voit pas ce que le fils ouvre -- l'entree doit le DIRE")


def test_l_empreinte_ecrit_l_axe_pour_CHAQUE_entree_mesuree(monkeypatch):
    """`py: []` doit etre ECRIT : c'est ce qui rend l'absence lisible comme << pas mesure >>."""
    monkeypatch.setattr(P, "_footprints", dict)
    emp = P._empreinte_fusionnee(
        mesures=["tests/a_offline.py", "tests/b_offline.py"],
        lus_par_test={"tests/a_offline.py": {"docs/rl/x.md"}},
        dossiers=lambda c: sorted({x.rsplit("/", 1)[0] for x in c if "/" in x}),
        temoins=lambda c: sorted(c),
        globales=[], commit=None, complete=True, mods={},
        py_par_test={"tests/a_offline.py": {"scripts/python/engine/predict.py"}},
        fils={"tests/b_offline.py"})
    a = emp["par_test"]["tests/a_offline.py"]
    b = emp["par_test"]["tests/b_offline.py"]
    assert a["py"] == ["scripts/python/engine"], "l'axe est stocke a la granularite REPERTOIRE"
    assert b["py"] == [], "une entree mesuree SANS lecture `.py` porte quand meme la cle"
    assert "fils" not in a and b["fils"] is True, (
        "`fils` n'est ecrit que s'il est VRAI -- sinon `py` seul atteste les deux faits")


def test_l_empreinte_RETIRE_la_propre_source_du_test(monkeypatch):
    monkeypatch.setattr(P, "_footprints", dict)
    emp = P._empreinte_fusionnee(
        mesures=["tests/a_offline.py"], lus_par_test={},
        dossiers=lambda c: sorted({x.rsplit("/", 1)[0] for x in c if "/" in x}),
        temoins=lambda c: sorted(c), globales=[], commit=None, complete=True, mods={},
        py_par_test={"tests/a_offline.py": {"scripts/python/tests/a_offline.py",
                                            "scripts/python/engine/predict.py"}})
    assert emp["par_test"]["tests/a_offline.py"]["py"] == ["scripts/python/engine"], (
        "la source du test LUI-MEME est un artefact de traceback, pas une dependance")


# =========================================================== 3. LE MODE `--measure-only`

def test_measure_only_REFUSE_un_chemin_hors_perimetre(capsys):
    rc = P._measure(["tests/a_offline.py"], seulement=["tests/pas_du_perimetre.py"])
    assert rc == 2, "un chemin hors perimetre est une erreur d'USAGE, pas un verdict"
    assert "HORS du perimetre" in capsys.readouterr().out


def test_les_TROIS_modes_de_mesure_s_excluent(capsys):
    rc = P._run(["--measure", "--measure-only", "tests/a_offline.py"])
    assert rc == 2
    assert "s'excluent" in capsys.readouterr().out


# ================================================ 4. LA CONTRE-EPREUVE DE LA CLASSE AST (volet a)

@pytest.fixture(scope="module")
def confrontation():
    """La confrontation REELLE, calculee UNE FOIS (24,7 s : cloture d'imports du perimetre)."""
    return CE.confronter()


def test_aucun_FAUX_NEGATIF_sur_ce_checkout(confrontation):
    """L'INVARIANT, et le seul sens dangereux.

    Un fichier que l'AST dit SELECTIONNABLE alors que la mesure voit un balayage est exactement
    ce qu'une composition `{insellectionnables} UNION {selection}` laisserait tomber. Il en
    existait **19** avant #935-r1 : dix-sept `inspect.getsource(...)`, un import DYNAMIQUE qui
    cassait la cloture, et un `Path(MODULE.__file__).read_text()`."""
    _accords, _sur, faux, _hors, _sources, _ins, _sel = confrontation
    assert not faux, ("faux negatif(s) : %s -- etendre le critere de `probe_935`"
                      % [r for r, _s, _d in faux])


def test_la_confrontation_est_NON_VACUE(confrontation):
    """Un accord fabrique sur un ensemble vide serait un vert qui ne mesure rien."""
    accords, sur, _faux, _hors, sources, ins, sel = confrontation
    assert ins and sel, "les deux classes AST doivent etre NON VIDES"
    assert len(accords) > 100, "trop peu de confrontables : l'empreinte ne couvre pas le perimetre"
    assert sur, ("AUCUNE sur-approximation : ce serait une exactitude parfaite, que le critere AST "
                 "ne peut PAS atteindre -- suspecter un montage degenere")
    assert sources.get("axe mesure", 0) + sources.get("repli temoins", 0) == \
        len(accords) + len(sur) + len(_faux), "toute confrontation porte une SOURCE"


def test_le_regime_de_SUR_APPROXIMATION_est_nominal(confrontation):
    accords, sur, faux, _hors, _sources, _ins, _sel = confrontation
    total = len(accords) + len(sur) + len(faux)
    pct = 100.0 * len(sur) / total
    assert pct <= CE.SUR_APPROXIMATION_MAX_PCT, (
        "regime degenere : %.1f %% > %.1f %%" % (pct, CE.SUR_APPROXIMATION_MAX_PCT))


def test_la_contre_epreuve_VOIT_un_faux_negatif_injecte(monkeypatch):
    """CONTRE-EPREUVE DE LA CONTRE-EPREUVE : un cliquet qui ne peut pas rougir est un inventaire.

    On declare un fichier SELECTIONNABLE cote AST tout en lui donnant un axe `py` non vide cote
    mesure -- exactement la configuration que le probe doit refuser."""
    monkeypatch.setattr(P935, "classer", lambda perimetre=None: ({}, list(perimetre or ())))
    monkeypatch.setattr(CE, "_empreinte",
                        lambda: {"_format": P.FORMAT_EMPREINTE,
                                 "par_test": {"tests/z_offline.py":
                                              {"py": ["scripts/python/engine"], "temoins": []}}})
    _accords, _sur, faux, _hors, _sources, _ins, _sel = CE.confronter(["tests/z_offline.py"])
    assert [r for r, _s, _d in faux] == ["tests/z_offline.py"]


def test_une_entree_ABSENTE_sort_en_NON_CONFRONTABLE_jamais_en_accord(monkeypatch):
    """Un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas."""
    monkeypatch.setattr(P935, "classer", lambda perimetre=None: ({}, list(perimetre or ())))
    monkeypatch.setattr(CE, "_empreinte",
                        lambda: {"_format": P.FORMAT_EMPREINTE, "par_test": {}})
    accords, sur, faux, hors, _sources, _ins, _sel = CE.confronter(["tests/z_offline.py"])
    assert not accords and not sur and not faux
    assert [r for r, _d in hors] == ["tests/z_offline.py"]


# ============================================== 5. LE CRITERE AST, ET SA MEMOISATION (`probe_935`)

@pytest.mark.parametrize("source,attendu", [
    ("import inspect\ndef f(x):\n    return inspect.getsource(x)\n", "LECTURE DE SOURCE"),
    ("from pathlib import Path\ndef f(m):\n    return Path(m.__file__).read_text()\n",
     "LECTURE D'UN `.py` NOMME"),
    ("from pathlib import Path\nP = Path('a') / 'engine' / 'predict.py'\n"
     "def f():\n    return P.read_text()\n", "LECTURE D'UN `.py` NOMME"),
    ("from pathlib import Path\ndef f(d):\n    return list(Path(d).rglob('*.py'))\n", "BALAYAGE"),
    ("import subprocess\ndef f():\n    return subprocess.run(['x'])\n", "SOUS-PROCESSUS"),
    # Le NEGATIF : une lecture de DONNEES n'est pas un balayage de sources.
    ("from pathlib import Path\ndef f(d):\n    return list(Path(d).glob('*.json'))\n", None),
])
def test_le_critere_AST_reconnait_chaque_forme(tmp_path, source, attendu):
    f = tmp_path / "m.py"
    f.write_text(source, encoding="utf-8")
    cause = P935._cause_du_fichier(f)
    if attendu is None:
        assert cause is None, "une lecture de DONNEES ne doit pas contaminer la classe"
    else:
        assert cause is not None and cause.startswith(attendu), cause


def test_l_import_DYNAMIQUE_entre_dans_la_cloture(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("import importlib\nM = importlib.import_module('probe_935_cliquets')\n",
                 encoding="utf-8")
    import ast as _ast

    noms = P935._imports_locaux(_ast.parse(f.read_text(encoding="utf-8")))
    assert "probe_935_cliquets" in noms, (
        "un import dynamique cassait la cloture EN SILENCE -- c'est un faux negatif mesure")


def test_le_cache_des_imports_EVITE_le_second_parse(monkeypatch, tmp_path):
    """#941-r2 : le discriminant n'est pas << combien de VERDICTS >> mais << combien d'APPELS >>.
    Mesure : 79,0 s -> 16,1 s sur le perimetre entier."""
    f = tmp_path / "m.py"
    f.write_text("import os\n", encoding="utf-8")
    monkeypatch.setitem(P935._IMPORTS_CACHE, str(f), {"os"})
    lectures = []
    vraie = Path.read_text
    monkeypatch.setattr(Path, "read_text",
                        lambda self, *a, **k: (lectures.append(self), vraie(self, *a, **k))[1])
    assert P935._imports_du_fichier(f) == {"os"}
    assert not lectures, "un fichier deja parse ne doit pas etre relu"


def test_la_classification_est_DETERMINISTE(tmp_path):
    """`_imports_locaux` rend un SET : sans tri, le module ACCUSE changeait d'un run a l'autre
    (mesure du 2026-08-12 : 20 lignes sur 160)."""
    perimetre = P.candidate_files()[:40]
    a_ins, a_sel = P935.classer(perimetre)
    b_ins, b_sel = P935.classer(perimetre)
    assert a_sel == b_sel and a_ins == b_ins, "deux appels doivent rendre exactement la meme chose"
    assert a_ins or a_sel, "ANTI-VACUITE : un perimetre vide rendrait ce cas creux"
