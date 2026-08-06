"""#486-r11 -- GARDE de la cle par SOUS-GRAPHE. Offline pur, aucune session.

CE QUE CE FICHIER TIENT
-----------------------
Le cliquet `probe_270r4r2_import_en_premier` lance UN interpreteur par module d'`engine/`
(437, 0,54 s piece). #486-r5 les a memoises sous `empreinte_engine()` -- l'arbre ENTIER --
donc une seule ligne modifiee relancait les 437 : le regime NORMAL d'une PR moteur.

La cle est descendue a la FERMETURE transitive des imports du module. Ce fichier garde les
DEUX faces de ce changement, et la seconde est celle qui compte :

  * ce qui DOIT etre re-teste l'est (sinon : verdict PERIME, faux vert) ;
  * ce qui ne doit PAS l'etre ne l'est pas (sinon : le gain est imaginaire).

POURQUOI IL EST BON MARCHE, ET POURQUOI CA COMPTE
--------------------------------------------------
La premiere garde de #486-r5 coutait **+150 s** parce qu'elle re-balayait le corpus reel :
un cliquet qui rouvre le gisement qu'il ferme. Ici, tout ce qui est CRITERE se joue sur des
corpus SYNTHETIQUES, ou la reponse est connue d'avance et ou rien ne coute. L'arbre REEL n'est
touche que par deux etages qui ne peuvent pas se jouer ailleurs :

  * la COINCIDENCE de l'accelerateur groupe avec le calcul naif -- une derive entre les deux
    rendrait des cles fausses en silence, et elle ne se voit que sur un vrai graphe cyclique ;
  * le TEMOIN de granularite -- si la fermeture d'un module valait tout l'arbre, la descente
    de cle serait FICTIVE et tous les etages synthetiques resteraient verts.

Les deux sont bornes a une poignee de modules.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]              # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import import_closure as IC                              # noqa: E402
import probe_270r4r2_import_en_premier as IP             # noqa: E402
import verdict_cache                                     # noqa: E402


# ================================================================= corpus synthetique

def _ecrire(racine: Path, chemin: str, texte: str) -> Path:
    p = racine / chemin
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texte, encoding="utf-8")
    return p


@pytest.fixture
def arbre(tmp_path):
    """Un paquet `engine` jouet : un hub, deux branches disjointes, un differe, un TYPE_CHECKING.

    La forme est choisie pour que « DANS la fermeture » et « HORS de la fermeture » soient tous
    deux NON VIDES -- une contre-epreuve sur un arbre ou tout depend de tout serait vacueuse.
    """
    _ecrire(tmp_path, "engine/__init__.py", "")
    _ecrire(tmp_path, "engine/socle.py", "SOCLE = 1\n")
    _ecrire(tmp_path, "engine/gauche/__init__.py", "")
    _ecrire(tmp_path, "engine/gauche/feuille.py", "X = 1\n")
    _ecrire(tmp_path, "engine/gauche/a.py",
            "from typing import TYPE_CHECKING\n"
            "from engine.socle import SOCLE\n"
            "from .feuille import X\n"
            "if TYPE_CHECKING:\n"
            "    from engine.droite.b import Y\n"
            "\n\n"
            "def tard():\n"
            "    from engine.droite.differee import Z\n"
            "    return Z\n")
    _ecrire(tmp_path, "engine/droite/__init__.py", "")
    _ecrire(tmp_path, "engine/droite/b.py", "Y = 2\n")
    _ecrire(tmp_path, "engine/droite/differee.py", "Z = 3\n")
    _ecrire(tmp_path, "horsarbre.py", "H = 4\n")
    return tmp_path


@pytest.fixture
def cl(arbre):
    return IC.Cloture(arbre)


# ================================================================= 1. LA FERMETURE

def test_etage1_la_fermeture_prend_les_ancetres_et_le_module_level(cl):
    """Ce que `import engine.gauche.a` EXECUTE : les deux `__init__.py` ancetres compris."""
    f = cl.fermeture("engine.gauche.a")
    assert f == {"engine", "engine.gauche", "engine.gauche.a", "engine.gauche.feuille",
                 "engine.socle"}, sorted(f)


def test_etage1_la_fermeture_EXCLUT_le_differe_et_le_TYPE_CHECKING(cl):
    """Ni l'un ni l'autre ne s'execute au chargement : les inclure ferait de la fermeture de
    presque tout module presque tout l'arbre -- la cle grossiere sous un autre nom."""
    f = cl.fermeture("engine.gauche.a")
    assert "engine.droite.differee" not in f, "un import DIFFERE est entre dans la fermeture"
    assert "engine.droite.b" not in f, "un import TYPE_CHECKING est entre dans la fermeture"
    assert "engine.droite" not in f


def test_etage1_un_import_module_level_CONDITIONNEL_entre_quand_meme(arbre):
    """Sur-approximer est SAIN, sous-approximer est FAUX : un `if <cond>: import X` au niveau
    module peut s'executer, donc `X` est dans la fermeture, condition non evaluee."""
    _ecrire(arbre, "engine/gauche/a.py",
            "import sys\n"
            "if sys.platform == 'jamais':\n"
            "    from engine.droite.b import Y\n")
    f = IC.Cloture(arbre).fermeture("engine.gauche.a")
    assert "engine.droite.b" in f, sorted(f)


def test_etage1_un_module_INCONNU_rend_None_jamais_un_ensemble_vide(cl):
    """TRI-ETAT. Un ensemble vide se lirait comme « rien ne le gouverne », donc « toujours a
    jour » -- exactement le faux vert."""
    assert cl.fermeture("engine.nexistepas") is None
    assert cl.cle("engine.nexistepas") is None


def test_etage1_la_fermeture_IGNORE_ce_qui_n_est_pas_dans_cet_arbre(cl):
    """La stdlib n'a pas de fichier a hacher ici. `typing` ne doit pas entrer."""
    assert not [x for x in cl.fermeture("engine.gauche.a") if not x.startswith("engine")]


def test_etage1_un_frere_HORS_paquet_entre_dans_la_fermeture(arbre):
    """`engine.x` peut importer un module frere de `scripts/python/` -- mesure a la livraison :
    `gameconfig` et `hexgeo`, ce dernier gouvernant 351 modules sur 437. La cle grossiere de
    #486-r5 ne les regardait PAS : c'est un trou refere ici, pas une precaution."""
    _ecrire(arbre, "engine/gauche/a.py", "import horsarbre\n")
    f = IC.Cloture(arbre).fermeture("engine.gauche.a")
    assert "horsarbre" in f, sorted(f)


# ================================================================= 2. LA CLE

def test_etage2_la_cle_bouge_sur_le_CONTENU_d_un_fichier_de_la_fermeture(arbre):
    avant = IC.Cloture(arbre).cle("engine.gauche.a")
    _ecrire(arbre, "engine/socle.py", "SOCLE = 2\n")
    assert IC.Cloture(arbre).cle("engine.gauche.a") != avant


def test_etage2_la_cle_bouge_sur_la_COMPOSITION_meme_a_contenus_inchanges(arbre):
    """Ajouter une ARETE fait entrer un fichier NEUF dans la fermeture. Un hash qui ne porterait
    que les contenus des fichiers deja presents ne le verrait pas."""
    avant = IC.Cloture(arbre).cle("engine.gauche.a")
    a = arbre / "engine" / "gauche" / "a.py"
    a.write_text("from engine.droite.b import Y\n" + a.read_text(encoding="utf-8"),
                 encoding="utf-8")
    apres = IC.Cloture(arbre).cle("engine.gauche.a")
    assert apres != avant
    assert "engine.droite.b" in IC.Cloture(arbre).fermeture("engine.gauche.a")


def test_etage2_la_cle_NE_bouge_PAS_sur_un_fichier_HORS_fermeture(arbre):
    """C'EST LE POINT DE LA TRANCHE. Sans cet etage, une cle « fine » qui bougerait quand meme
    serait verte partout et ne gagnerait rien."""
    avant = IC.Cloture(arbre).cle("engine.gauche.a")
    _ecrire(arbre, "engine/droite/b.py", "Y = 999\n")
    _ecrire(arbre, "engine/droite/differee.py", "Z = 999\n")
    assert IC.Cloture(arbre).cle("engine.gauche.a") == avant


def test_etage2_un_INIT_invalide_TOUT_son_paquet(arbre):
    """`engine/entities/__init__.py` est dans la fermeture des 397 modules de son paquet. Le
    rendre vert serait rendre vert le fichier le plus structurant du depot."""
    cibles = ["engine.gauche.a", "engine.gauche.feuille", "engine.droite.b"]
    avant = {m: IC.Cloture(arbre).cle(m) for m in cibles}
    _ecrire(arbre, "engine/gauche/__init__.py", "# touche\n")
    apres = {m: IC.Cloture(arbre).cle(m) for m in cibles}
    assert apres["engine.gauche.a"] != avant["engine.gauche.a"]
    assert apres["engine.gauche.feuille"] != avant["engine.gauche.feuille"]
    assert apres["engine.droite.b"] == avant["engine.droite.b"], (
        "un `__init__.py` d'un AUTRE paquet a invalide : la cle n'est pas un sous-graphe")

    # ... et la racine `engine/__init__.py` invalide, elle, TOUT
    avant = {m: IC.Cloture(arbre).cle(m) for m in cibles}
    _ecrire(arbre, "engine/__init__.py", "# touche\n")
    apres = {m: IC.Cloture(arbre).cle(m) for m in cibles}
    assert all(apres[m] != avant[m] for m in cibles), (
        "la racine du paquet ne remonte pas dans toutes les fermetures")


def test_etage2_un_fichier_SUPPRIME_de_la_fermeture_fait_bouger_la_cle(arbre):
    """Une entree perimee doit MANQUER, jamais mentir : un fichier illisible entre dans la cle
    comme `ABSENT`, ce qui est une donnee, pas un silence."""
    avant = IC.Cloture(arbre).cle("engine.gauche.a")
    (arbre / "engine" / "socle.py").unlink()
    assert IC.Cloture(arbre).cle("engine.gauche.a") != avant


# ================================================================= 3. L'ACCELERATEUR

def test_etage3_le_calcul_GROUPE_coincide_avec_le_NAIF_sur_l_arbre_jouet(cl):
    """Le graphe porte des CYCLES (un `__init__` importe ses enfants, chaque enfant a ce paquet
    pour ancetre) : une memoisation par module serait FAUSSE. La memoisation se fait par
    composante fortement connexe, et cet etage garde qu'elle rend bien la meme chose."""
    _ecrire(cl.racine, "engine/gauche/__init__.py", "from .a import tard\n")   # cycle paquet<->enfant
    c = IC.Cloture(cl.racine)
    mods = ["engine", "engine.socle", "engine.gauche", "engine.gauche.a",
            "engine.gauche.feuille", "engine.droite.b"]
    groupe = c.fermetures(mods)
    for m in mods:
        assert groupe[m] == c.fermeture(m), (
            "groupe != naif sur %s : groupe-naif=%s naif-groupe=%s"
            % (m, sorted(groupe[m] - c.fermeture(m)), sorted(c.fermeture(m) - groupe[m])))
    assert "engine.gauche.a" in groupe["engine.gauche"], (
        "le cycle paquet<->enfant n'est pas monte : l'arbre jouet ne teste pas ce qu'il annonce")


@pytest.mark.parametrize("mod", ["engine.entities.stats", "engine.runner.snapshot",
                                 "engine.playbook.psyker"])
def test_etage3_le_calcul_GROUPE_coincide_avec_le_NAIF_sur_l_arbre_REEL(mod):
    """Meme propriete, sur le vrai graphe -- le seul qui porte les vraies composantes. Borne a
    trois modules : leurs fermetures partagent l'essentiel de l'arbre, donc la couverture est
    large pour un cout de parse paye une seule fois."""
    groupe = IC.CLOTURE.fermetures([mod])
    assert groupe[mod] == IC.CLOTURE.fermeture(mod)


# ================================================================= 4. LE TEMOIN DE GRANULARITE

def test_etage4_temoin_la_fermeture_reelle_est_NON_VIDE_et_PLUS_PETITE_que_l_arbre():
    """Sans lui, tous les etages ci-dessus resteraient verts alors que la descente de cle serait
    FICTIVE (une fermeture = tout l'arbre reproduit exactement la cle grossiere).

    Mesure a la livraison : 437 modules, fermeture mediane 191, et le rayon d'invalidation d'un
    fichier median est de 181 modules sur 437. Les bornes ci-dessous sont larges a dessein --
    ce qui est garde est la PROPRIETE, pas le chiffre du jour.
    """
    mods = IP._modules_sous(("engine",))
    assert len(mods) >= 300, "portee derisoire : %d module(s)" % len(mods)
    f = IC.CLOTURE.fermeture("engine.playbook.psyker")
    assert f is not None and len(f) >= 5, "fermeture derisoire : %r" % (f and len(f))
    assert len(f) < len(mods), (
        "la fermeture d'un module vaut TOUT l'arbre : la cle par sous-graphe est fictive")
    assert "engine" in f and "engine.playbook" in f, (
        "les `__init__.py` ancetres ne sont pas dans la fermeture : un `__init__` touche ne "
        "reinvaliderait pas son paquet")


# ================================================================= 5. LE CACHE, DANS LES DEUX SENS

@pytest.fixture
def bac(arbre, monkeypatch):
    """`essayer_tous` branche sur l'arbre jouet, avec `_essayer` SUBSTITUE.

    On mesure la MEMOISATION, jamais le corpus : substituer l'interpreteur est ce qui rend cette
    garde bon marche, et c'est aussi ce qui la rend probante (un chronometre ne distinguerait pas
    « le cache mord » de « la machine est chargee »).
    """
    lances: list[str] = []
    fermetures_rendues: dict = {}

    def _faux(mod):
        lances.append(mod)
        f = fermetures_rendues.get(mod, IC.CLOTURE.fermeture(mod) or frozenset())
        return mod, 0, "", f

    monkeypatch.setattr(IP, "RACINE", arbre)
    monkeypatch.setattr(IC, "CLOTURE", IC.Cloture(arbre))
    monkeypatch.setattr(IP, "_essayer", _faux)
    monkeypatch.setattr(IP, "_ESSAIS", {})
    monkeypatch.setattr(IP, "_OPAQUES", {})
    monkeypatch.setattr(IP, "_VUS", set())
    monkeypatch.setattr(IP, "_LANCES", [0])
    monkeypatch.setattr(IP, "_GEN_ENGINE", None)
    monkeypatch.setattr(IP, "_GEN_HORS", {})
    monkeypatch.setattr(IP, "_CACHE", verdict_cache.CacheCliquet(
        "jouet_486r11", "contexte-jouet", dossier=arbre / "cache"))
    return arbre, lances, fermetures_rendues


TOUS = ["engine.gauche.a", "engine.gauche.feuille", "engine.droite.b", "engine.socle"]


def test_etage5_toucher_un_fichier_DANS_la_fermeture_RELANCE_le_module(bac):
    """SENS 1 -- le seul dont l'echec serait un FAUX VERT : un verdict perime servi comme frais."""
    arbre, lances, _ = bac
    IP.essayer_tous(TOUS)
    assert sorted(lances) == sorted(TOUS), lances
    del lances[:]

    _ecrire(arbre, "engine/socle.py", "SOCLE = 42\n")           # DANS la fermeture de gauche.a
    IP.essayer_tous(TOUS)
    assert "engine.gauche.a" in lances, (
        "un fichier de la fermeture a change et le module n'a PAS ete re-teste : %s" % lances)
    assert "engine.socle" in lances, lances


def test_etage5_toucher_un_fichier_HORS_fermeture_NE_relance_PAS(bac):
    """SENS 2 -- l'echec ici n'est pas dangereux, il est seulement RUINEUX : c'est tout le gain.

    Et la mutation doit avoir MORDU : on verifie qu'elle relance bien SON propre module, sans
    quoi ce vert dirait seulement « rien n'a change », ce qui est le vert suspect.
    """
    arbre, lances, _ = bac
    IP.essayer_tous(TOUS)
    del lances[:]

    _ecrire(arbre, "engine/droite/b.py", "Y = 42\n")            # HORS fermeture de gauche.a
    IP.essayer_tous(TOUS)
    assert "engine.droite.b" in lances, (
        "LA MUTATION N'A PAS MORDU : le fichier touche n'a meme pas relance son propre module")
    assert "engine.gauche.a" not in lances, (
        "un fichier HORS fermeture a relance le module : la cle n'est pas un sous-graphe (%s)"
        % lances)
    assert "engine.socle" not in lances, lances


def test_etage5_le_verdict_traverse_un_process_par_le_cache_VERSIONNE(bac):
    """Le gain vise le regime « PR touchant 0 fichier » : un process FRAIS doit demarrer CHAUD.
    Un cache de process seul rendrait les trois regimes identiques."""
    arbre, lances, _ = bac
    IP.essayer_tous(TOUS)
    assert IP._enregistrer_si_complet(), "le cache versionne n'a pas ete ecrit"
    del lances[:]

    #: process « frais » : memoire videe, le fichier TSV est la seule survivance.
    IP._ESSAIS.clear()
    IP._CACHE = verdict_cache.CacheCliquet("jouet_486r11", "contexte-jouet",
                                           dossier=arbre / "cache")
    res = IP.essayer_tous(TOUS)
    assert lances == [], "le cache versionne n'a servi a rien : %s" % lances
    assert res == [(m, 0, "") for m in TOUS], res


def test_etage5_un_CONTEXTE_different_fait_tout_recalculer(bac):
    """Invalider trop est toujours sur ; invalider trop peu serait faux. Le contexte porte les
    sources qui PRODUISENT la cle -- si `import_closure` change, aucune entree ne vaut plus."""
    arbre, lances, _ = bac
    IP.essayer_tous(TOUS)
    IP._enregistrer_si_complet()
    del lances[:]
    IP._ESSAIS.clear()
    IP._CACHE = verdict_cache.CacheCliquet("jouet_486r11", "AUTRE-contexte",
                                           dossier=arbre / "cache")
    IP.essayer_tous(TOUS)
    assert sorted(lances) == sorted(TOUS), lances


# ================================================================= 6. LE REPLI, NOMME

def test_etage6_une_fermeture_MESUREE_qui_deborde_fait_RETOMBER_sur_la_cle_grossiere(bac):
    """LE PIEGE 1. Un `importlib.import_module`, un `__import__`, un differe execute au
    chargement : le calcul statique ne les voit pas, sa fermeture SOUS-APPROXIME, et un fichier
    hors fermeture pourrait changer le verdict -- faux vert.

    Le controle n'est pas une heuristique : l'interpreteur rend ce qu'il A CHARGE, et le
    debordement se lit. Le module concerne n'entre alors JAMAIS au cache versionne.
    """
    arbre, lances, rendues = bac
    rendues["engine.gauche.a"] = frozenset(
        {"engine", "engine.gauche", "engine.gauche.a", "engine.gauche.feuille", "engine.socle",
         "engine.droite.differee"})                     # <- charge en plus, invisible du calcul
    IP.essayer_tous(TOUS)
    assert "engine.gauche.a" in IP._OPAQUES, sorted(IP._OPAQUES)
    assert IP._OPAQUES["engine.gauche.a"] == frozenset({"engine.droite.differee"})

    IP._enregistrer_si_complet()
    IP._ESSAIS.clear()
    IP._CACHE = verdict_cache.CacheCliquet("jouet_486r11", "contexte-jouet",
                                           dossier=arbre / "cache")
    IP._OPAQUES.clear()
    del lances[:]
    IP.essayer_tous(TOUS)
    assert lances == ["engine.gauche.a"], (
        "un module OPAQUE a ete servi depuis le cache versionne : son verdict repose sur une "
        "fermeture qui ne le decrit pas (%s)" % lances)


def test_etage6_une_fermeture_NON_MESUREE_declenche_le_MEME_repli(bac):
    """TRI-ETAT : `None` = « pas mesure », jamais « rien de plus ». Les confondre attesterait un
    verdict sur une base inconnue."""
    arbre, lances, _ = bac
    monkey = {}

    def _muet(mod):
        lances.append(mod)
        return mod, 0, "", (None if mod == "engine.socle" else IC.CLOTURE.fermeture(mod))

    monkey["ancien"] = IP._essayer
    IP._essayer = _muet
    try:
        IP.essayer_tous(TOUS)
        IP._enregistrer_si_complet()
        IP._ESSAIS.clear()
        IP._CACHE = verdict_cache.CacheCliquet("jouet_486r11", "contexte-jouet",
                                               dossier=arbre / "cache")
        del lances[:]
        IP.essayer_tous(TOUS)
    finally:
        IP._essayer = monkey["ancien"]
    assert lances == ["engine.socle"], (
        "un module dont la fermeture n'a PAS ete mesuree a ete cache : %s" % lances)


def test_etage6_un_ECHEC_n_est_jamais_cache(bac):
    """Un import qui echoue laisse `sys.modules` a mi-chemin : sa fermeture n'est pas celle du
    verdict. Attester un ROUGE le rendrait peremptoire -- et un rouge doit se recalculer."""
    arbre, lances, _ = bac

    def _rouge(mod):
        lances.append(mod)
        f = IC.CLOTURE.fermeture(mod) or frozenset()
        return (mod, 1, "ImportError: boum", f) if mod == "engine.socle" else (mod, 0, "", f)

    ancien = IP._essayer
    IP._essayer = _rouge
    try:
        res = IP.essayer_tous(TOUS)
        assert ("engine.socle", 1, "ImportError: boum") in res, res
        IP._enregistrer_si_complet()
        IP._ESSAIS.clear()
        IP._CACHE = verdict_cache.CacheCliquet("jouet_486r11", "contexte-jouet",
                                               dossier=arbre / "cache")
        del lances[:]
        IP.essayer_tous(TOUS)
    finally:
        IP._essayer = ancien
    assert lances == ["engine.socle"], "un ECHEC a ete servi depuis le cache : %s" % lances


# ================================================================= 7. LE CACHE NE RETRECIT PAS

def test_etage7_un_run_PARTIEL_n_ecrase_pas_le_cache_complet(bac):
    """`CacheCliquet.enregistrer` reecrit avec EXACTEMENT les entrees vues. Un run sur un
    sous-ensemble (un seul des deux fichiers de test, `--modules a,b`) RETRECIRAIT donc le
    fichier versionne, et le run suivant repaierait plein tarif."""
    arbre, lances, _ = bac
    IP.essayer_tous(TOUS)
    assert IP._enregistrer_si_complet()
    complet = (arbre / "cache" / "jouet_486r11.tsv").read_text(encoding="utf-8")

    IP._ESSAIS.clear()
    IP._VUS.clear()
    IP._CACHE = verdict_cache.CacheCliquet("jouet_486r11", "contexte-jouet",
                                           dossier=arbre / "cache")
    IP.essayer_tous(["engine.socle"])                   # run PARTIEL
    assert not IP._enregistrer_si_complet(), "un run partiel a reecrit le cache versionne"
    assert (arbre / "cache" / "jouet_486r11.tsv").read_text(encoding="utf-8") == complet
