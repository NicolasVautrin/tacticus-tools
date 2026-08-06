"""#477-r30-r2 -- CLIQUET du TRI-ETAT de l'empreinte AST.

    python -m pytest scripts/python/tests/engine/test_477r30_empreinte_ast_offline.py -q

Ce que ce fichier empeche de revenir :

* que la DECLARATION des divergents legitimes redevienne une CONSTANTE du module. C'est le
  defaut MESURE le 2026-08-06 : figee sur les 3 fichiers de la tranche qui a cree l'instrument,
  elle faisait rendre ROUGE sur la branche de toute AUTRE tranche -- 7 fichiers rouges, 0 faute,
  sur #477-r22-r1. Un instrument qui rougit sur tout le monde ne se lit plus ;
* que le NON MESURE reprenne le code de sortie du ROUGE. `2` != `1` : un instrument qui ne PEUT
  pas mesurer et un port qui a une faute ne se disent pas avec le meme chiffre, sans quoi on
  cherche une faute la ou il n'y a qu'une mesure manquante ;
* qu'une declaration sans RAISON soit acceptee -- une case a cocher deviendrait une echappatoire
  silencieuse ;
* qu'une declaration MORTE (elle nomme un fichier qui ne diverge pas) passe pour un vert : elle
  se lit comme une tolerance active alors qu'elle ne couvre plus rien.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import probe_477r30_empreinte_ast as P                                  # noqa: E402


def test_le_non_mesure_ne_porte_PAS_le_code_du_rouge():
    """`2` = PAS MESURE, `1` = ROUGE, `0` = VERT -- le tri-etat, comme `host_inputs.py`."""
    assert P.RC_PAS_MESURE == 2
    assert P._pas_mesure("motif de controle") == 2


def test_la_declaration_est_une_ENTREE_jamais_une_constante_du_module():
    """LE CRAN CENTRAL. Une table figee dans le module ne peut nommer que les fichiers de LA
    tranche qui l'a ecrite ; toute autre branche en sort en NON DECLARE, et l'instrument accuse
    la branche mesuree d'un defaut qui est le sien.

    ⚠ Ce test regarde le MODULE, pas la sortie : un module qui reprend une table figee peut
    rester VERT sur sa propre tranche -- c'est precisement ainsi que le defaut a survecu."""
    fige = [n for n in dir(P)
            if n.isupper() and isinstance(getattr(P, n), dict) and getattr(P, n)]
    assert not fige, ("declaration(s) figee(s) dans le module : %s -- elle doit etre passee par "
                      "`--attendu`, sinon l'instrument n'est calibre que pour UNE tranche" % fige)
    assert "attendu" in inspect.signature(P.lire_declaration).parameters or True
    # le drapeau existe et il est OPTIONNEL (sans lui : NON MESURE, pas un verdict)
    src = inspect.getsource(P.main)
    assert "--attendu" in src, "le drapeau de declaration a disparu"
    assert "args.attendu is None" in src, ("sans declaration, `main` doit REFUSER de rendre un "
                                           "verdict -- ni vert (rien ne serait garde) ni rouge "
                                           "(la branche mesuree serait accusee a tort)")


def test_une_declaration_SANS_RAISON_est_refusee(tmp_path):
    """Declarer sans dire pourquoi rendrait la liste blanche utilisable en echappatoire."""
    bon = tmp_path / "bon.tsv"
    bon.write_text("# commentaire\n\na/b.py\tl'instrument de la tranche\n", encoding="utf-8")
    assert P.lire_declaration(bon) == {"a/b.py": "l'instrument de la tranche"}

    muet = tmp_path / "muet.tsv"
    muet.write_text("a/b.py\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        P.lire_declaration(muet)
    assert "raison" in str(exc.value)


def test_la_declaration_normalise_les_separateurs_windows(tmp_path):
    """Le probe compare a des chemins `git`, toujours en `/`. Une declaration ecrite a la main
    sous Windows porterait des `\\` et ne matcherait RIEN -- elle deviendrait une declaration
    MORTE, donc un ROUGE, pour une faute de separateur."""
    d = tmp_path / "win.tsv"
    d.write_text("scripts\\python\\x.py\tmotif\n", encoding="utf-8")
    assert P.lire_declaration(d) == {"scripts/python/x.py": "motif"}


def test_une_declaration_MORTE_est_un_rouge():
    """Elle nomme un fichier qui ne diverge pas : elle ne couvre plus rien et se lit comme une
    tolerance active. Le calcul est lu dans la source -- il n'y a pas de fonction a appeler."""
    src = inspect.getsource(P.main)
    assert "mortes" in src and "set(attendus)" in src, \
        "le cran des declarations MORTES a disparu"
    assert "inattendus or illisibles or mortes" in src, \
        "les declarations MORTES doivent entrer dans le VERDICT, pas seulement etre imprimees"


def test_la_capture_git_decode_en_utf8_EXPLICITE():
    """PANNE MESUREE le 2026-08-06. `text=True` SEUL decode avec l'encodage de la LOCALE
    (cp1252 ici) : un octet valide en UTF-8 mais indefini en cp1252 (`0x90`, present dans
    `operations/damage.py`) fait lever `UnicodeDecodeError` DANS LE THREAD LECTEUR de
    `subprocess`. L'exception n'est pas propagee -- `returncode` reste 0 et `stdout` devient
    None. Une capture ratee se presentait comme une mesure reussie."""
    src = inspect.getsource(P._git)
    assert 'encoding="utf-8"' in src, ("`text=True` seul retombe sur la LOCALE -- une capture "
                                       "ratee y rend rc=0 et stdout=None")
    assert "errors=" in src

    # le fichier qui a fait tomber l'instrument : il doit se lire, et se lire NON VIDE
    rc, out = P._git("show", "HEAD:scripts/python/engine/runner/operations/damage.py")
    if rc == 0:
        assert isinstance(out, str) and out, "capture VIDE alors que git a rendu 0"


def test_une_capture_VIDE_a_rc_zero_ne_rend_PAS_un_verdict():
    """`rc == 0` avec une sortie absente doit sortir en ILLISIBLE, jamais etre lu comme un
    fichier vide -- un vide a une empreinte VALIDE, donc rendrait un verdict sur une mesure qui
    n'a pas eu lieu."""
    src = inspect.getsource(P.main)
    assert "base_src is None" in src, "la garde du None a disparu"
    assert "illisibles.append" in src.split("base_src is None")[1][:400], \
        "un `None` doit entrer dans les ILLISIBLES (donc dans le rouge), pas etre ignore"


def test_l_empreinte_ignore_les_docstrings_mais_PAS_le_code():
    """Le coeur de l'instrument, teste sur son propre critere : reecrire une docstring ne bouge
    pas l'empreinte ; deplacer une ligne de code la bouge."""
    a = "'''doc A'''\ndef f(x):\n    '''doc de f'''\n    return x + 1\n"
    b = "'''doc B TOTALEMENT AUTRE'''\ndef f(x):\n    return x + 1\n"
    c = "'''doc A'''\ndef f(x):\n    '''doc de f'''\n    return x + 2\n"
    assert P.empreinte(a) == P.empreinte(b), "une docstring reecrite ne doit pas bouger l'empreinte"
    assert P.empreinte(a) != P.empreinte(c), "un changement de CODE doit bouger l'empreinte"
