"""#464-r1 -- le chemin d'un script FRERE ne doit pas dependre du repertoire de lancement.

Deux objets sous garde :
  * `sibling_script.sibling_script()` -- l'ANCRAGE (rend un absolu, leve si le frere manque,
    et rend LE MEME chemin quel que soit le CWD) ;
  * `probe_464_sibling_script_cwd.sites()` -- le CRITERE du cliquet, eprouve sur des cas
    FABRIQUES plutot qu'en rejouant le probe entier (le rejeu coute un `git ls-files` et
    1682 lectures, et ne prouve rien de plus sur le critere).

Tout se joue en memoire ou dans un tmpdir SYSTEME (`mkdtemp()` sans `dir=`) : un test de la
banque n'ecrit JAMAIS sous `scripts/python` (#455 -- la banque tourne en parallele, un
repertoire qui apparait puis disparait fait rougir le voisin qui enumere le meme arbre).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict
#: (#486-r15). Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des deux `conftest.py` et sa
        # fermeture. Aucun test ne les IMPORTE -- c'est de la semantique pytest -- et ils
        # portent le `green_skip_guard` de #455 plus trois fixtures `autouse`, dont le
        # verdict de CHAQUE test depend. Liste EXPLICITE et non `scripts/python/*.py` : le
        # glob large retiendrait ce test a chaque modification d'un probe quelconque.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER :
        "scripts/python/probe_464_sibling_script_cwd.py",
        "scripts/python/sibling_script.py", "scripts/python/repo_read.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le probe sous test, le foyer `sibling_script` dont il verifie l'emploi, et "
              "`repo_read` qui porte la lecture parallele du balayage. Le perimetre BALAYE, lui, "
              "est `scripts/python/**` -- deja couvert par les entrees ci-dessus au titre du "
              "socle et du probe.",
}

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import probe_464_sibling_script_cwd as P            # noqa: E402
from sibling_script import sibling_script           # noqa: E402


# --------------------------------------------------------------------------- #
# 1. L'ancrage
# --------------------------------------------------------------------------- #

def test_rend_un_absolu_existant():
    p = sibling_script("rl_duel.py")
    assert Path(p).is_absolute()
    assert Path(p).is_file()
    assert Path(p).name == "rl_duel.py"


def test_leve_si_le_frere_est_absent():
    """Le rc que 8 des 15 appelants ignoraient devient un echec qui NOMME le frere."""
    with pytest.raises(FileNotFoundError) as exc:
        sibling_script("ce_script_n_existe_pas_464.py")
    assert "ce_script_n_existe_pas_464.py" in str(exc.value)


def test_identique_depuis_n_importe_quel_cwd():
    """LE point du cas : c'est ce qui etait faux avant #464-r1.

    On mesure depuis un tmpdir SYSTEME -- un repertoire qui n'a aucun rapport avec le
    depot, donc ou un nom nu ne resoudrait vers rien.
    """
    depuis_ici = sibling_script("rl_duel.py")
    ailleurs = tempfile.mkdtemp(prefix="t464-")
    avant = os.getcwd()
    try:
        os.chdir(ailleurs)
        assert sibling_script("rl_duel.py") == depuis_ici
        # et le nom NU, lui, ne designe rien ici : c'est le defaut d'origine.
        assert not (Path(ailleurs) / "rl_duel.py").exists()
    finally:
        os.chdir(avant)
        shutil.rmtree(ailleurs, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 2. Le critere du cliquet
# --------------------------------------------------------------------------- #

def _sites(src: str):
    return P.sites("fabrique.py", src)


def test_critere_voit_le_litteral_en_place():
    src = ('import subprocess, sys\n'
           'subprocess.run([sys.executable, "rl_duel.py", "build"])\n')
    assert [s[1] for s in _sites(src)] == [["rl_duel.py"]]


def test_critere_voit_l_argv_passe_par_une_VARIABLE():
    """La forme que le recensement de #561 ne voyait pas -- d'ou son compte de 13/15."""
    src = ('import subprocess, sys\n'
           'cmd = [sys.executable, "rl_duel.py", "build"]\n'
           'out = subprocess.run(cmd, capture_output=True)\n')
    assert [s[1] for s in _sites(src)] == [["rl_duel.py"]]


def test_cwd_explicite_neutralise():
    src = ('import subprocess, sys\n'
           'subprocess.run([sys.executable, "rl_duel.py"], cwd="/x")\n')
    assert _sites(src) == []


def test_kwargs_indecidable_n_accuse_pas():
    """`**kw` peut porter un `cwd=`. On ne condamne pas ce qu'on ne peut pas lire."""
    src = ('import subprocess, sys\n'
           'kw = {}\n'
           'subprocess.run([sys.executable, "rl_duel.py"], **kw)\n')
    assert _sites(src) == []


def test_chemin_absolu_neutralise():
    src = ('import subprocess, sys\n'
           'subprocess.run([sys.executable, "C:/x/rl_duel.py"])\n')
    assert _sites(src) == []


def test_forme_sure_non_accusee():
    """`sibling_script("rl_duel.py")` est un APPEL, pas une constante -- donc invisible au
    critere. C'est ce qui rend la correction stable sous le cliquet."""
    src = ('import subprocess, sys\n'
           'from sibling_script import sibling_script\n'
           'subprocess.run([sys.executable, sibling_script("rl_duel.py")])\n')
    assert _sites(src) == []


def test_git_hors_sujet():
    """`git show <rev>:<chemin>.py` n'invoque pas un script -- son axe est `-C`."""
    src = ('import subprocess\n'
           'subprocess.run(["git", "show", "origin/master:scripts/python/x.py"])\n')
    assert _sites(src) == []


# --------------------------------------------------------------------------- #
# 3. Le gisement est a zero, et le cliquet est lui-meme insensible au CWD
# --------------------------------------------------------------------------- #

def test_gisement_a_zero_sur_ce_checkout():
    racine = P.repo_root()
    mauvais = []
    for rel in P.fichiers():
        try:
            src = (racine / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            for ligne, scripts in P.sites(rel, src):
                mauvais.append("%s:%d %s" % (rel, ligne, scripts))
        except SyntaxError:
            continue
    assert mauvais == [], "invocation(s) resolue(s) depuis le CWD : %s" % mauvais


def test_le_cliquet_ne_porte_pas_le_vice_qu_il_garde():
    """Son perimetre doit etre le MEME depuis n'importe quel repertoire.

    Un cliquet ancre sur le CWD rendrait ici un perimetre vide -- et `main()` le traite
    comme un echec, pas comme un PASS, mais le test le prend en amont.
    """
    attendu = P.fichiers()
    ailleurs = tempfile.mkdtemp(prefix="t464b-")
    avant = os.getcwd()
    try:
        os.chdir(ailleurs)
        assert P.fichiers() == attendu
        assert P.repo_root().is_dir()
    finally:
        os.chdir(avant)
        shutil.rmtree(ailleurs, ignore_errors=True)
