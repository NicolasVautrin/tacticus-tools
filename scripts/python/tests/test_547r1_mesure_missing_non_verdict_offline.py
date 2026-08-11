"""#547-r1 -- la GARDE du cliquet `probe_547r1_mesure_missing_non_verdict.py`.

Ce que ce fichier tient, et pourquoi il faut les DEUX :

  * une passe PARTIELLE de `probe_457` ne rend jamais `0` -- ni par le chemin
    << rien a mesurer >>, ni apres avoir joue des fichiers tous verts ;
  * une passe COMPLETE (`--measure`) garde son `0`, parce qu'elle joue TOUT le perimetre et que
    son `rc` est alors un vrai verdict. Sans ce second bras, << ne jamais rendre 0 >> se serait
    etendu a un mode qui a le droit de le faire.

Le cliquet lui-meme porte sa contre-epreuve (etage 4 : on remet `return 0` dans un arbre temoin
ROUGE et le `0` revient). Ce fichier-ci la REJOUE, pour qu'elle entre dans le perimetre offline
que `probe_457` balaie -- un cliquet qu'aucune passe ne joue est exactement ce que #547 a trouve.

100 % OFFLINE. ASCII only.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_457_offline_tests_green as P         # noqa: E402
import probe_547r1_mesure_missing_non_verdict as G  # noqa: E402

#: DECLENCHEUR -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_547r1_mesure_missing_non_verdict.py",
        "scripts/python/probe_457_offline_tests_green.py",
        # ⚠ NI DERIVE NI DERIVABLE PAR IMPORT : le cliquet CHOISIT sa cible dans ce fichier de
        # durees VERSIONNE (`_fichier_le_moins_cher`). Il est ouvert par chemin, jamais importe.
        "scripts/ratchets-457-durations.json",
        # ⚠ LES TROIS SUIVANTS SONT DES TEMOINS, apportes par l'EMPREINTE et non par la fermeture.
        # Ce fichier LANCE `probe_457` en sous-process (etages 2-4) : les modules que CELUI-CI
        # importe sont OUVERTS pendant le test, donc mesures. Aucune analyse d'imports de CE
        # fichier ne peut les voir -- c'est exactement l'ecart a DEUX SOURCES que #486-r29 decrit,
        # et il n'apparait qu'APRES `--measure-missing`.
        "scripts/python/ledger_vert_offline.py",
        "scripts/python/probe_463r1_ecart_empreinte_offline.py",
        "scripts/python/repo_read.py",
    ),
    "build": False,          # ne lit ni le binaire ni `data/symbols/**`
    "toujours": False,
    "raison": (
        "CES chemins et pas d'autres, en DEUX groupes de nature differente. (1) La FERMETURE : ce "
        "test n'importe que le cliquet et le probe qu'il juge, et aucun des deux ne tire "
        "`engine.*`. (2) Ce qu'aucun import ne revele : la CIBLE du contrefactuel, choisie "
        "mecaniquement dans les durees versionnees ; et les TROIS modules que `probe_457` importe "
        "quand ce test le LANCE EN SOUS-PROCESS -- ils arrivent par les temoins de l'empreinte, "
        "donc seulement APRES `--measure-missing` (#486-r29). Les omettre serait le faux vert que "
        "#486-r15 combat, vu depuis l'autre bout."
    ),
}


@pytest.fixture(scope="module", autouse=True)
def _temoin_partage():
    """LE WORKTREE TEMOIN MEURT AVEC LE MODULE (#941).

    Les etages 3 et 4 le PARTAGENT desormais (ils jugeaient le meme arbre `HEAD` depuis deux
    montages independants, a 53 s piece -- `worktree add` 35,0 s + `remove --force` 18,4 s,
    mesure du 2026-08-11). Ici, `main()` n'est pas dans la boucle : c'est pytest qui appelle
    `etape3`/`etape4`, donc c'est a ce finalizer de liberer -- sans lui, un worktree survivrait
    a la passe et apparaitrait dans `git worktree list` de tout le depot."""
    yield
    G._liberer_temoin()


# --------------------------------------------------------- le DISCRIMINANT : `complete`

def _rc_du_foyer(complete: bool) -> int:
    """Exerce `_ecrire_mesure` sans ecrire une ligne dans le depot (poids rediriges, empreinte
    `None`) -- meme montage que l'etage 1 du cliquet."""
    tmp = Path(tempfile.mkdtemp(prefix="t547r1_"))
    ancien = P._weights_path
    try:
        P._weights_path = lambda: tmp / "poids.json"
        rels = ["tests/a.py", "tests/b.py"]
        h = G._Horloge(rels)
        joues = rels if complete else rels[:1]
        return P._ecrire_mesure(rels, joues, h, None, 0, 1.0, {}, complete=complete)
    finally:
        P._weights_path = ancien
        shutil.rmtree(tmp, ignore_errors=True)


def test_une_passe_PARTIELLE_ne_rend_jamais_zero():
    """LE LIVRABLE. `0` se lit << l'arbre offline est vert >> ; une passe partielle ne l'a pas
    regarde."""
    assert _rc_du_foyer(complete=False) == P.EX_NON_MESURE


def test_une_passe_COMPLETE_garde_son_verdict():
    """ANTI-SUR-CORRECTION, et c'est le bras qui compte : `--measure` joue TOUT le perimetre,
    donc son `rc` EST un verdict de verdeur. L'etendre au mode complet aurait rendu ce probe
    incapable de dire vert, jamais."""
    assert _rc_du_foyer(complete=True) == 0


def test_le_foyer_du_non_verdict_rend_EX_NON_MESURE_et_le_DIT(capsys):
    """Un `rc` ne nomme rien tout seul (#467-r6) : le foyer doit ECRIRE ce qu'il ne mesure pas,
    et vers quoi se tourner."""
    assert G.P._non_verdict_de_verdeur("controle") == P.EX_NON_MESURE
    out = capsys.readouterr().out
    assert "NE JUGE PAS LA VERDEUR" in out
    assert "--since" in out and "probe_547_ledger_sans_verdict_non_vert" in out


def test_EX_NON_MESURE_nest_ni_zero_ni_un():
    """La convention de ce depot : `0` = vert, `1` = rouge de gisement, `99` = AUCUN verdict.
    Rabattre le troisieme sur l'un des deux premiers est precisement le vice repare ici."""
    assert P.EX_NON_MESURE not in (0, 1)


# --------------------------------------------------------- la CONTRE-EPREUVE, rejouee

def _sauter_si_dans_un_temoin():
    """⚠ TOUT test qui lance `probe_457` en SOUS-PROCESS doit passer par ici.

    Ce fichier est joue PAR `probe_457` (il est dans son perimetre offline). Les etages 2, 3 et 4
    du cliquet relancent `probe_457` : sans garde, chaque niveau rejoue ce fichier, qui relance un
    niveau de plus. Mesure du 2026-08-08 : **~150 processus chaines**, un toutes les 12 s, 35
    minutes durant, avant un `taskkill /T`. Le sous-process porte `TEMOIN_ENV` ; on saute ici, et
    les etages restent exerces au niveau du dessus."""
    import os
    if os.environ.get(G.TEMOIN_ENV):
        pytest.skip("joue DANS un sous-process de ce cliquet (%s=1) : relancer `probe_457` ici "
                    "serait une recursion infinie -- exerce au niveau du dessus" % G.TEMOIN_ENV)


def test_le_chemin_rien_a_mesurer_ne_rend_pas_zero():
    """Etage 2 du cliquet -- le chemin EXACT du `rc = 0` historique."""
    _sauter_si_dans_un_temoin()
    assert G.etape2() == []


@pytest.mark.parametrize("etage", [3, 4], ids=["temoin_rouge", "mutant_du_correctif"])
def test_le_temoin_reel_et_son_mutant(etage):
    """Etages 3 et 4 : un `assert False` injecte dans un fichier de test offline EXISTANT ne fait
    plus rendre `0` ; et le `0` REVIENT quand on retire le correctif -- c'est ce second bras qui
    etablit que c'est le correctif qui agit, et non le hasard du montage.

    ⚠ Ils jugent l'arbre COMMITE (worktree temoin depuis `HEAD`), comme `probe_547` juge le
    ledger versionne.

    ⚠ ET ILS SAUTENT QUAND CE FICHIER EST DEJA JOUE **DANS** UN TEMOIN -- sinon la recursion est
    infinie, et elle l'a ETE : ce test appelle un cliquet qui lance `probe_457`, lequel joue les
    fichiers sans entree d'empreinte, dont CE fichier. Mesure du 2026-08-08 : ~150 processus
    chaines, un toutes les 12 s, 35 minutes durant. Le skip est NOMME et ne masque rien -- les
    autres tests du fichier restent joues (donc `passed > 0`, cf. le garde #455), et les deux
    etages sont exerces des que le cliquet est joue normalement."""
    _sauter_si_dans_un_temoin()
    assert (G.etape3() if etage == 3 else G.etape4()) == []


def test_le_cliquet_est_CABLE_a_son_verdict(monkeypatch):
    """Un cliquet qui MESURE sans RENDRE son verdict est un inventaire deguise (#430)."""
    monkeypatch.setattr(G, "ETAGES", [("X -- faux", lambda: ["une faute"])])
    assert G.main([]) == 1
    monkeypatch.setattr(G, "ETAGES", [("X -- vrai", lambda: [])])
    assert G.main([]) == 0


def test_les_deux_etages_a_temoin_ne_montent_QU_UN_SEUL_worktree(monkeypatch, tmp_path):
    """#941 -- LE GAIN, VERROUILLE. Les etages 3 et 4 jugent le MEME arbre `HEAD` ; ils en
    montaient DEUX.

    Mesure du 2026-08-11 sur ce depot : `git worktree add --detach` = **35,0 s**,
    `worktree remove --force` = **18,4 s** (l'essentiel vient de `data/`, 170 Mo pour 807
    fichiers). Le second montage etait ~53 s de pur gaspillage, sur le fichier de test le plus
    lourd du parc -- et il FUYAIT : un `wt547r1_*` du 2026-08-08 (4699 fichiers) etait encore
    enregistre dans `git worktree list` trois jours plus tard.

    Verifie par SUBSTITUTION : aucun worktree REEL n'est monte ici. Un cliquet qui, pour garder un
    gain de 53 s, en couterait 53 rouvrirait le gisement qu'il ferme (lecon de #486-r5)."""
    journal = []
    racine = tmp_path / "temoin"
    racine.mkdir(parents=True, exist_ok=True)
    probe_dans_le_temoin = racine / "t" / "scripts" / "python" / "probe_457_offline_tests_green.py"

    def _faux_git(args, cwd=None, tolere=False):
        journal.append(" ".join(args[:2]))
        if args[:2] == ["worktree", "add"]:
            cible = Path(args[3])
            (cible / "scripts" / "python" / "tests").mkdir(parents=True, exist_ok=True)
            (cible / "scripts" / "python" / "probe_457_offline_tests_green.py").write_text(
                G.ANCRAGE_CORRECTIF + "    return 99\n", encoding="utf-8")
            (cible / "scripts" / "python" / "tests" / "t_jouet.py").write_text(
                "def test_ok():\n    assert True\n", encoding="utf-8")
        return ""

    class _RcPytest:
        returncode = 1                       # le fichier temoin EST rouge

    def _faux_joue_457(cwd, args):
        """Le geste rend `0` si et seulement si le MUTANT est pose -- c'est le DISCRIMINANT que
        les etages 3 et 4 mesurent, reproduit ici sans lancer `probe_457`."""
        mute = G.MUTANT_CORRECTIF in (Path(cwd) / "scripts" / "python"
                                      / "probe_457_offline_tests_green.py").read_text(
                                          encoding="utf-8")
        return (0 if mute else 99), ""

    monkeypatch.setattr(G, "_git", _faux_git)
    monkeypatch.setattr(G, "_fichier_le_moins_cher", lambda: "tests/t_jouet.py")
    monkeypatch.setattr(G, "_joue_457", _faux_joue_457)
    monkeypatch.setattr(G.subprocess, "run", lambda *a, **k: _RcPytest())
    monkeypatch.setattr(G.tempfile, "mkdtemp", lambda prefix="": str(racine))
    monkeypatch.setattr(G, "_TEMOIN", None)

    assert G.etape3() == [], "l'etage 3 doit passer sur ce montage jouet"
    assert G.MUTANT_CORRECTIF not in probe_dans_le_temoin.read_text(encoding="utf-8")
    assert G.etape4() == [], "l'etage 4 doit passer sur ce montage jouet"

    assert journal.count("worktree add") == 1, (
        "les deux etages montent %d worktree(s) alors qu'ils jugent le MEME arbre `HEAD` : un "
        "seul suffit, et le second coute 53 s" % journal.count("worktree add"))
    assert journal.count("worktree remove") == 0, (
        "le temoin est demonte AVANT le dernier etage -- l'etage suivant le remonterait")


def test_le_temoin_partage_REFUSE_de_deriver_entre_deux_etages(monkeypatch, tmp_path):
    """LE CRAN QUI REND LE PARTAGE SUR, et il n'existait pas avant #941 parce que le partage non
    plus.

    `--measure-missing` ECRIT dans l'arbre qu'il juge (poids, empreinte, ledger). Sans
    restauration entre les etages, le second trouverait << rien a mesurer >> et rendrait son `rc`
    pour une raison ETRANGERE au critere -- exactement la lecture rassurante que ce cliquet
    existe pour interdire. `_restaurer` REFUSE plutot que de laisser deriver."""
    vus = []

    def _git_qui_ne_nettoie_RIEN(args, cwd=None, tolere=False):
        vus.append(args[0])
        return " M scripts/ratchets-457-durations.json\n" if args[0] == "status" else ""

    monkeypatch.setattr(G, "_git", _git_qui_ne_nettoie_RIEN)
    with pytest.raises(SystemExit) as exc:
        G._restaurer(tmp_path)
    assert "restaure" in str(exc.value), str(exc.value)
    assert "checkout" in vus, "la restauration n'a meme pas essaye : %r" % (vus,)


def test_l_ancrage_du_mutant_existe_dans_le_probe_juge():
    """Sans lui, l'etage 4 LEVE au lieu de mesurer -- et un etage qui ne s'exerce pas ne prouve
    rien. On le verifie ICI aussi, pour que la peremption se voie dans une passe de tests."""
    src = (PYDIR / "probe_457_offline_tests_green.py").read_text(encoding="utf-8")
    assert src.count(G.ANCRAGE_CORRECTIF) == 1
    assert G.MUTANT_CORRECTIF != G.ANCRAGE_CORRECTIF
    assert "return 0" in G.MUTANT_CORRECTIF
