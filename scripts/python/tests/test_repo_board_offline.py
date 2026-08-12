"""Garde du board de depot -- 100 % OFFLINE, aucun appel reseau.

Ce fichier protege la seule chose du board qui decide QUOI FAIRE d'une panne. Le reste
(agregation, rendu HTML) se relit au resultat ; la classification, non : elle se manifeste
par une attente de trois minutes, ou par un run perdu.

CE QUI L'A FAIT NAITRE. Le 2026-08-12, deux runs consecutifs sont morts sur
`HTTP 502: Bad Gateway` de l'API GitHub. Mesure : la MEME commande rend rc=1 puis rc=0 en
68 s sans qu'on ait touche a rien, et `--limit 1000` echoue la ou `--limit 3000` passe --
donc PAS de seuil de taille, c'est la PAGINATION qui expose (`gh pr list` decoupe en pages
de 100 ; a 982 PR, ~10 appels GraphQL, et un seul 502 perd tout). Le risque CROIT avec le
depot : ne pas re-tenter condamne l'outil a mesure qu'il grossit.

LES TROIS CLASSES, ET POURQUOI TROIS. Re-tenter une panne DEFINITIVE (auth, 404, mauvais
drapeau) fait perdre trois minutes et masque le diagnostic -- c'est deja arrive en sens
inverse, un 502 nu ayant fait accuser l'auth. Et rabattre l'INCONNU sur << transitoire >>
recree ce defaut pour toute panne future qu'on n'a pas prevue : l'inconnu insiste UNE fois,
puis remonte son texte.
"""

DECLENCHEUR = {
    "chemins": (
        "scripts/python/repo_board.py",
        # `repo_board.py` importe `repo_board_render.page` (import DIFFERE, ligne ~906) :
        # la fermeture le tire, donc il entre au perimetre. L'omettre rendait
        # `probe_486r15` ROUGE des l'arrivee de ce fichier sur `master`.
        "scripts/python/repo_board_render.py",
        "scripts/python/tests/test_repo_board_offline.py",
    ),
    # Aucun test ici ne lit le dump, le gameconfig ni un transcript : les stderr sont
    # des chaines litterales, mesurees sur `gh 2.88.1`.
    "build": False,
    "toujours": False,
    "raison": "La classification des pannes du board et sa boucle de re-essai. Un mauvais "
              "classement ne casse RIEN de visible -- il fait soit perdre un run entier "
              "sur un hoquet amont, soit boucler sur une erreur d'usage.",
}

import os                                                               # noqa: E402
import sys                                                              # noqa: E402

import pytest                                                           # noqa: E402

_ICI = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(_ICI)
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import repo_board as RB  # noqa: E402


# --- classification ----------------------------------------------------------

#: Textes REELS rendus par `gh` (stderr verbatim). Le 502 est celui du 2026-08-12.
TRANSITOIRES_REELS = [
    "HTTP 502: 502 Bad Gateway (https://api.github.com/graphql)",
    "HTTP 503: Service Unavailable (https://api.github.com/graphql)",
    "HTTP 504: Gateway Time-out (https://api.github.com/graphql)",
    "Post \"https://api.github.com/graphql\": read tcp: connection reset by peer",
    "unexpected EOF",
]

DEFINITIVES_REELLES = [
    "error: not logged into any GitHub hosts. Run gh auth login",
    "HTTP 401: Bad credentials (https://api.github.com/graphql)",
    "HTTP 404: Could not resolve to a Repository with the name 'x/y'.",
    "unknown flag: --limite",
    "You have exceeded a secondary rate limit",
]


@pytest.mark.parametrize("txt", TRANSITOIRES_REELS)
def test_les_pannes_AMONT_sont_transitoires(txt):
    assert RB._classe_panne(txt) == "transitoire", txt


@pytest.mark.parametrize("txt", DEFINITIVES_REELLES)
def test_les_pannes_DE_NOTRE_COTE_sont_definitives(txt):
    assert RB._classe_panne(txt) == "definitive", txt


def test_une_panne_INCONNUE_n_est_ni_l_une_ni_l_autre():
    """Le tri-etat est le point du dispositif. Rabattre l'inconnu sur << transitoire >>
    ferait boucler sur toute panne future non prevue ; sur << definitive >>, ca ferait
    renoncer a un hoquet reel. On veut voir le trou."""
    for txt in ("", "quelque chose que personne n'a prevu", "boom"):
        assert RB._classe_panne(txt) == "inconnue", txt


def test_le_401_l_emporte_meme_s_il_cotoie_un_mot_transitoire():
    """L'ordre de test EST le comportement : `definitive` est examinee EN PREMIER. Un
    stderr qui melange les deux (un 401 rendu par un proxy qui parle de gateway) ne doit
    pas partir en boucle de re-essai."""
    assert RB._classe_panne(
        "HTTP 401: Bad credentials (bad gateway upstream)") == "definitive"


# --- la boucle ---------------------------------------------------------------

class _FauxRun:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _sequence(monkeypatch, resultats):
    """Substitue `subprocess.run` par une sequence FIGEE, et compte les appels."""
    etat = {"n": 0}

    def faux(*a, **k):
        r = resultats[min(etat["n"], len(resultats) - 1)]
        etat["n"] += 1
        return r

    monkeypatch.setattr(RB.subprocess, "run", faux)
    monkeypatch.setattr(RB.time, "sleep", lambda _s: None)   # pas d'attente reelle
    return etat


def test_un_502_puis_un_succes_rend_le_succes(monkeypatch):
    """Le cas MESURE : la meme commande echoue puis passe. C'est tout l'objet du correctif."""
    etat = _sequence(monkeypatch, [
        _FauxRun(1, "", "HTTP 502: 502 Bad Gateway"),
        _FauxRun(0, '[{"number": 1}]', ""),
    ])
    assert RB.sh_retry(["gh", "pr", "list"]) == '[{"number": 1}]'
    assert etat["n"] == 2, "doit avoir insiste exactement une fois"


def test_une_panne_DEFINITIVE_ne_re_tente_PAS(monkeypatch):
    """Boucler sur une erreur d'auth coute trois minutes et masque le diagnostic."""
    etat = _sequence(monkeypatch, [_FauxRun(1, "", "HTTP 401: Bad credentials")])
    with pytest.raises(SystemExit) as e:
        RB.sh_retry(["gh", "pr", "list"])
    assert etat["n"] == 1, "un seul appel, aucune insistance"
    assert "DEFINITIVE" in str(e.value)


def test_une_panne_INCONNUE_insiste_UNE_fois_puis_remonte(monkeypatch):
    etat = _sequence(monkeypatch, [_FauxRun(1, "", "boom")])
    with pytest.raises(SystemExit) as e:
        RB.sh_retry(["gh", "pr", "list"], essais=4)
    assert etat["n"] == 2, "une insistance, pas quatre"
    assert "inconnue" in str(e.value)


def test_un_transitoire_PERSISTANT_finit_par_remonter_et_dit_qu_on_a_insiste(monkeypatch):
    """Insister n'est pas insister indefiniment : l'echec final doit ARRIVER, et nommer
    sa classe -- sinon on relit << gh a echoue >> et on accuse l'auth, comme en juillet."""
    etat = _sequence(monkeypatch, [_FauxRun(1, "", "HTTP 502: 502 Bad Gateway")])
    with pytest.raises(SystemExit) as e:
        RB.sh_retry(["gh", "pr", "list"], essais=3)
    assert etat["n"] == 3
    msg = str(e.value)
    assert "insistance" in msg and "transitoire" in msg and "502" in msg


def test_un_rc_non_nul_AVEC_sortie_est_un_succes(monkeypatch):
    """Mirror de `sh` : `gh` rend parfois rc!=0 en ayant tout de meme produit le JSON.
    Le re-tenter perdrait un resultat valide."""
    etat = _sequence(monkeypatch, [_FauxRun(1, '[{"number": 7}]', "warning")])
    assert RB.sh_retry(["gh", "pr", "list"]) == '[{"number": 7}]'
    assert etat["n"] == 1
