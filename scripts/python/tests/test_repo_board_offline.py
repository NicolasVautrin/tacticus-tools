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
    # RENDU PAR LE TRI-ETAT lui-meme le 2026-08-12 : la 3e tentative d'un run a echoue
    # sur ce texte, classe `inconnue`, remonte tel quel -- et c'est ainsi qu'on a su
    # qu'il fallait le classer. Une liste << transitoire par defaut >> l'aurait avale
    # sans jamais le montrer, une liste << definitive par defaut >> aurait fait renoncer.
    "stream error: stream ID 1; CANCEL; received from peer",
    "http2: server sent GOAWAY and closed the connection",
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


# ---------------------------------------------------------------------------
# LE CACHE DE COMMITS (`load_git` incremental)
# ---------------------------------------------------------------------------
# Mesure du 2026-08-12 : `load_git` pesait 67 % du run (120 s sur 178). Le `git log
# --numstat` integral calcule le diff des 3 672 commits de la fenetre a CHAQUE fois ;
# l'enumeration seule (`rev-list`, sans pathspec) coute 1,3 s. D'ou le decoupage.
#
# CE QUI EST CACHABLE ET CE QUI NE L'EST PAS -- tout le sujet, et la raison pour laquelle
# cette memoisation avait ete tenue en RESERVE : le numstat d'un commit est IMMUABLE, sa
# CLASSIFICATION ne l'est pas. Un commit pousse direct devient un commit de PR le jour ou
# une PR merge une branche qui le contient. Cacher les deux ensemble figerait un `direct`
# qui a cesse d'etre vrai -- regression SILENCIEUSE, le board restant vert.
#
# L'equivalence des deux voies est confrontee sur le VRAI depot (168 cellules, temoin de
# 2 227 shas, aucune divergence, x5,2) ; ici on garde les invariants qui la rendent possible.

def _table(**shas):
    """{sha: (jour, merge, +, -)} -> la forme cachee. `None` = HORS PERIMETRE."""
    return {s: (None if v is None else dict(j=v[0], m=v[1], a=v[2], d=v[3]))
            for s, v in shas.items()}


def test_un_MERGE_ne_tombe_dans_aucun_seau():
    """PR + direct + merges = tous les commits. Compter les merges gonflait le perimetre PR
    de 174 sur 993 pour ZERO ligne (--numstat ignore leur diff)."""
    t = _table(a=("2026-08-12", True, 0, 0), b=("2026-08-12", False, 10, 2))
    r = RB._agreger_commits(["a", "b"], t, keep={"a", "b"})
    assert r["2026-08-12"]["commits"] == 1, "le merge ne doit pas etre compte"
    assert r["2026-08-12"]["add"] == 10


def test_un_sha_HORS_PERIMETRE_est_ignore_sans_erreur():
    """`None` = ecarte par le pathspec (ne touche que `data/symbols`). C'est une valeur
    CACHEE, pas un trou : sans elle le sha serait reinterroge a chaque run."""
    t = _table(a=None, b=("2026-08-12", False, 5, 1))
    r = RB._agreger_commits(["a", "b"], t, keep=set())
    assert r["2026-08-12"]["direct_commits"] == 1
    assert "commits" not in r["2026-08-12"]


def test_la_CLASSIFICATION_n_est_PAS_figee_par_le_cache():
    """L'INVARIANT QUI JUSTIFIE LE DECOUPAGE. La MEME table mesuree, deux `keep` differents
    -> deux repartitions differentes. Si ce test tombe, c'est que la classification a ete
    cachee avec la mesure, et le board affichera un `direct` perime sans rien rougir."""
    t = _table(x=("2026-08-12", False, 7, 3))
    avant = RB._agreger_commits(["x"], t, keep=set())
    apres = RB._agreger_commits(["x"], t, keep={"x"})
    assert avant["2026-08-12"]["direct_commits"] == 1
    assert avant["2026-08-12"]["direct_add"] == 7
    assert apres["2026-08-12"]["commits"] == 1, "le meme sha doit basculer en PR"
    assert apres["2026-08-12"]["add"] == 7
    assert "direct_commits" not in apres["2026-08-12"]


# --- la boucle incrementale ---------------------------------------------------

#: `b` est HORS PERIMETRE : aucun enregistrement rendu par `git log`, comme le vrai git.
_LOG = {
    "a": "C|a|2026-08-12T10:00:00+00:00|p1\n5\t1\tf.py",
    "c": "C|c|2026-08-12T11:00:00+00:00|p1 p2",      # merge (deux parents)
}


def _faux_git(monkeypatch, shas, appels):
    """Substitue `RB.sh` : rend rev-list / log / shortstat depuis des donnees figees, et
    ENREGISTRE chaque `git log --no-walk` pour qu'on puisse compter les mesures reelles."""
    def faux(args, **k):
        if args[1] == "rev-list":
            return "base0000" if "--before" in args else "\n".join(shas)
        if args[1] == "log":
            demandes = [a for a in args if a in shas]
            appels.append(list(demandes))
            return "\n".join(_LOG[s] for s in demandes if s in _LOG)
        if args[1] == "diff":
            return "1 file changed, 1 insertion(+)"
        return ""

    monkeypatch.setattr(RB, "sh", faux)


def test_les_VIDES_sont_RETENUS_donc_le_cache_CONVERGE(monkeypatch):
    """Un sha ecarte par le pathspec n'a PAS d'enregistrement. Sans marque explicite il
    repasserait par `git log` a chaque run, indefiniment -- le cache ne convergerait jamais
    et le gain serait nul sur le depot qui en accumule le plus."""
    appels = []
    _faux_git(monkeypatch, ["a", "b", "c"], appels)
    cache = RB.empty_cache()
    RB.load_git("2026-07-10", set(), cache)
    assert cache["stat_commits"] == dict(mesures=3, reutilises=0)
    assert cache["commits"]["b"] is None, "le vide doit etre RETENU, pas oublie"

    appels.clear()
    RB.load_git("2026-07-10", set(), cache)
    assert cache["stat_commits"] == dict(mesures=0, reutilises=3)
    assert appels == [], "aucun `git log` ne doit repartir a chaud"


def test_la_voie_INTEGRALE_et_la_voie_CACHE_concordent(monkeypatch):
    """Mirror offline de la confrontation menee sur le vrai depot. `cache=None` est
    l'ORACLE : les deux voies doivent rendre le meme `by_day`."""
    _faux_git(monkeypatch, ["a", "b", "c"], [])
    integral, _ = RB.load_git("2026-07-10", {"a"}, None)
    par_cache, _ = RB.load_git("2026-07-10", {"a"}, RB.empty_cache())
    assert {j: dict(d) for j, d in integral.items()} == \
           {j: dict(d) for j, d in par_cache.items()}
    # ... et le temoin n'est PAS vide : il y a bien quelque chose a comparer.
    assert integral["2026-08-12"]["commits"] == 1
    assert integral["2026-08-12"]["add"] == 5


def test_la_mesure_est_REUTILISEE_quand_keep_change(monkeypatch):
    """Bout en bout : deux runs, meme cache, `keep` different. La mesure est reutilisee ET
    la repartition change -- le scenario reel d'une PR qui merge apres coup."""
    appels = []
    _faux_git(monkeypatch, ["a", "b", "c"], appels)
    cache = RB.empty_cache()
    r1, _ = RB.load_git("2026-07-10", set(), cache)
    appels.clear()
    r2, _ = RB.load_git("2026-07-10", {"a"}, cache)
    assert appels == [], "la mesure doit etre reutilisee"
    assert r1["2026-08-12"]["direct_add"] == 5
    assert r2["2026-08-12"]["add"] == 5 and "direct_add" not in r2["2026-08-12"]
