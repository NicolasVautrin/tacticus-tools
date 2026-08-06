"""#270-r4-r2-r2-r2 et -r3 -- CLIQUET : les gardes du hissage d'imports ECHOUENT, elles ne se
contentent plus de RAPPORTER.

DEUX TROUS DE LA MEME FAMILLE, fermes ici. Ils ne se voyaient PAS l'un l'autre, et c'est le
point du fichier :

  * TROU A (#270-r4-r2-r2-r2) -- `probe_270r4r2_empreinte_valeurs` VOYAIT la disparition d'un
    nom (197 116 -> 197 115) et l'IMPRIMAIT, mais son `rc` ne dependait QUE des divergences de
    VALEUR. Un hissage CASSE (import SUPPRIME au lieu d'etre DEPLACE) passait donc VERT.
    Ferme par `comparer()` : DISPARU non declare, IMPORT casse et declaration PERIMEE echouent.
  * TROU B (#270-r4-r2-r2-r3) -- un hissage qui AJOUTE l'import module-level sans RETIRER le
    differe rend le nom LOCAL A TOUTE LA FONCTION ; l'autre chemin lit une locale non liee.
    `UnboundLocalError` MESURE sur `master` (15 failed / 7 passed de
    `test_death_queue_ordering_live.py`). AUCUN cliquet ne le voyait : le tri des differes compte
    des INSTRUCTIONS, il ne regarde jamais si le nom est DEJA LIE AU MODULE.
    Ferme par `probe_270r4r2r2r3_import_ombre`.

CE QUI FAIT QUE CE FICHIER N'EST PAS VERT A VIDE
  * chaque detecteur est confronte a des MUTANTS (il doit MORDRE) **et** a des TEMOINS NEGATIFS
    (il ne doit pas rougir) -- un detecteur qui rend TOUT serait vert sur les seuls mutants ;
  * la severite ATTENDUE est assertionnee, pas seulement le fait de mordre ;
  * le balayage assertionne SON PROPRE NON-VIDE (fichiers, fonctions, imports differes vus).

100 % OFFLINE : aucun runner, aucune session Frida. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_270r4r2_empreinte_valeurs as EMP      # noqa: E402
import probe_270r4r2r2r3_import_ombre as OM        # noqa: E402

#: SEUIL, et il est nomme comme tel. Les ombrages HORS `engine/` vivent dans des fichiers que
#: d'autres tranches editent ; l'invariant ne les couvre pas (residu #270-r4-r2-r2-r3-r1). Ce
#: plafond n'existe que pour empecher le gisement de GROSSIR. Le BAISSER quand il descend.
PLAFOND_HORS_ENGINE = 15


# ======================================================================= TROU B -- l'ombrage

@pytest.fixture(scope="module")
def balayage():
    ombres, stats, _ = OM.balayer(PYDIR / OM.PAQUET, PYDIR)
    return ombres, stats


def test_etage0_temoin_le_balayage_voit_quelque_chose(balayage):
    """TEMOIN d'abord : sans lui, l'invariant serait vert SUR RIEN."""
    _, stats = balayage
    assert stats["fichiers"] >= 300, "portee derisoire : %d fichier(s)" % stats["fichiers"]
    assert stats["fonctions"] >= 1000, "portee derisoire : %d fonction(s)" % stats["fonctions"]
    assert stats["imports_differes"] >= 100, (
        "le detecteur ne voit plus d'import differe (%d) : il serait vert a vide"
        % stats["imports_differes"])
    assert stats["illisibles"] == 0, "%d fichier(s) illisible(s)" % stats["illisibles"]


def test_etage1_invariant_aucun_import_differe_n_ombrage_un_import_module_level(balayage):
    """INVARIANT A ZERO. Le critere est la REDONDANCE, pas l'armement (cf. la docstring du probe).

    Un site inoffensif est a UNE edition d'etre arme, et c'est precisement l'etage qui manquait."""
    ombres, _ = balayage
    ecarts = [o for o in ombres if o.exemption is None]
    assert ecarts == [], "\n".join(
        ["%d import(s) differe(s) OMBRAGENT un import module-level du meme nom." % len(ecarts),
         "En Python un `import` dans un corps de fonction rend le nom LOCAL A TOUTE LA FONCTION :",
         "tout chemin qui n'execute pas la ligne leve `UnboundLocalError`.",
         "RETIRER le differe (l'import module-level suffit), ou declarer au site "
         "`# %s <raison>`." % OM.MARQUEUR_VOULU,
         ""]
        + ["  " + o.texte() for o in ecarts[:40]])


def test_etage2_l_echappatoire_reste_visible_bornee_et_MOTIVEE(balayage):
    """Une echappatoire non comptee est une porte ouverte ; sans motif, c'en est une aussi."""
    ombres, _ = balayage
    exemptees = [o for o in ombres if o.exemption is not None]
    sans_motif = [o for o in exemptees if not o.exemption]
    assert sans_motif == [], "exemption(s) SANS MOTIF :\n  " + "\n  ".join(
        o.texte() for o in sans_motif)
    assert len(exemptees) <= 3, (
        "trop d'exemptions declarees (%d) : l'echappatoire devient la norme" % len(exemptees))


def test_etage3_contre_epreuve_chaque_mutant_MORD_et_est_BIEN_CLASSE():
    """`a_mordu` par mutant, et la SEVERITE assertionnee -- une contre-epreuve inerte passe pour
    mordante, et ce depot s'est fait avoir plusieurs fois de suite."""
    assert OM.MUTANTS, "aucun mutant : contre-epreuve vide"
    inertes, mal_classes = [], []
    for nom, src, attendu, sev in OM.MUTANTS:
        lot, _ = OM.analyser("mutant", src)
        if len(lot) < attendu:
            inertes.append("%s (%d ombrage(s) vu(s), %d attendu(s))" % (nom, len(lot), attendu))
        elif not all(o.severite == sev for o in lot):
            mal_classes.append("%s : attendu %s, mesure %s" % (nom, sev, OM.severites(lot)))
    assert inertes == [], "mutant(s) INERTE(s) :\n  " + "\n  ".join(inertes)
    assert mal_classes == [], "mutant(s) MAL CLASSE(s) :\n  " + "\n  ".join(mal_classes)


def test_etage4_temoins_negatifs_le_detecteur_DISCRIMINE():
    """Un detecteur qui rendrait TOUT serait vert sur les seuls mutants. Ces sept sources-la
    couvrent chacune une raison DISTINCTE de ne PAS rougir (module-level sous `TYPE_CHECKING`,
    corps de classe, noms differents, alias distinct, portee imbriquee, `global`)."""
    assert len(OM.TEMOINS_NEGATIFS) >= 5, "trop peu de temoins negatifs"
    faux = []
    for nom, src in OM.TEMOINS_NEGATIFS:
        lot, _ = OM.analyser("temoin", src)
        if lot:
            faux.append("%s -> %s" % (nom, [o.cle() for o in lot]))
    assert faux == [], "FAUX POSITIF(S) :\n  " + "\n  ".join(faux)


def test_etage5_la_faute_HISTORIQUE_reproduite_a_l_identique():
    """LE CRAN QUI COMPTE : la garde doit rougir sur la faute REELLE, pas sur un mutant de
    laboratoire. C'est la structure EXACTE d'`applied_stat_mods` au commit `492c722f` --
    import module-level PRESENT, differe conserve sous `if self.value is not None:`, lecture du
    nom dans l'autre chemin.

    Mesure de reference, reproductible :
        python probe_270r4r2r2r3_import_ombre.py --historique 492c722f   -> 14 sites, 1 ARME
        python probe_270r4r2r2r3_import_ombre.py --historique d450c362   -> 0"""
    src = ("from engine.entities.stats import StatType\n"
           "\n"
           "\n"
           "class ContagionsOfNurgleArmorReductionEffect:\n"
           "    def applied_stat_mods(self, stats_ctx):\n"
           "        if not self.active:\n"
           "            return []\n"
           "        if self.value is not None:\n"
           "            from engine.entities.stats import StatType\n"
           "            return [(int(StatType.FIXED_ARMOR), int(self.value))]\n"
           "        return [(int(StatType.FIXED_ARMOR), 0)]\n")
    lot, _ = OM.analyser("engine.entities.effects.loki.status", src)
    assert len(lot) == 1, "la faute historique n'est plus vue : %r" % lot
    assert lot[0].nom == "StatType"
    assert lot[0].severite == "ARME", (
        "la faute historique est classee %s alors qu'elle LEVE `UnboundLocalError` au runtime"
        % lot[0].severite)
    # et le CORRECTIF (le differe retire) doit redevenir VERT -- sinon la garde serait
    # ininstallable : elle rougirait sur l'arbre repare.
    lot2, _ = OM.analyser("engine.entities.effects.loki.status",
                          src.replace("            from engine.entities.stats import StatType\n", ""))
    assert lot2 == [], "la garde rougit sur l'arbre CORRIGE : %r" % lot2


def test_etage6_le_hors_perimetre_est_MESURE_pas_tu():
    """SEUIL. L'invariant porte sur `engine/` ; le reste de `scripts/python` n'est pas garde
    (residu #270-r4-r2-r2-r3-r1). Un compte filtre DIT ce qu'il filtre -- et ce plafond empeche
    le gisement non garde de GROSSIR pendant qu'on ne le regarde pas."""
    res = OM.mesurer_hors_perimetre(PYDIR)
    assert res is not None, "mesure du hors-perimetre IMPOSSIBLE : ce n'est PAS un zero"
    n, lot = res
    assert n <= PLAFOND_HORS_ENGINE, "\n".join(
        ["ombrages HORS `engine/` : %d pour un plafond de %d." % (n, PLAFOND_HORS_ENGINE),
         "Ce gisement n'est pas garde (residu #270-r4-r2-r2-r3-r1) mais il ne doit pas croitre.",
         ""] + ["  " + o.texte() for o in lot[:20]])
    assert n > 0, ("le hors-perimetre rend 0 : soit il a ete resorbe (BAISSER le plafond et "
                   "fermer le residu), soit le balayage est casse")


# ======================================================================= TROU A -- l'empreinte

def test_etage7_l_empreinte_ECHOUE_sur_un_nom_disparu():
    """La faute HISTORIQUE du TROU A : un hissage casse SUPPRIME l'import au lieu de le deplacer.

    Mesure de reference sur l'arbre reel (`engine/services/movement_query.py`, retrait de
    `from ..entities.pathfinding.fly_pathfinder import is_like_flying`) : la garde offline
    `probe_270r4r2_import_en_premier --tous` reste VERTE (412/412) -- le module s'IMPORTE, le nom
    ne manque qu'a l'APPEL -- et l'empreinte rend desormais rc 1."""
    ref = {"engine.m.A": 1, "engine.m.B": 2, "!TEMOIN!attributs": 2}
    mesure = {"engine.m.A": 1, "!TEMOIN!attributs": 1}
    d = EMP.comparer(ref, mesure)
    assert d["rc"] == 1, "un NOM DISPARU ne fait plus echouer l'empreinte : %r" % d
    assert [k for k, _ in d["disparus_non_declares"]] == ["engine.m.B"]


def test_etage8_contre_epreuve_du_TRI_de_l_empreinte():
    """Chaque mutant du tri doit rendre le `rc` attendu -- et les DEUX sens comptent : un mutant
    qui doit PASSER (nom APPARU, disparition DECLAREE) verifie qu'on n'a pas ferme trop large."""
    assert EMP.MUTANTS, "aucun mutant : contre-epreuve vide"
    ecarts = []
    for nom, mesure, voulues, rc_attendu in EMP.MUTANTS:
        d = EMP.comparer(EMP._REF_SYNTH, mesure, voulues)
        if d["rc"] != rc_attendu:
            ecarts.append("%s : rc=%d, attendu %d" % (nom, d["rc"], rc_attendu))
    assert ecarts == [], "mutant(s) du tri en ECART :\n  " + "\n  ".join(ecarts)
    # les deux sens sont bien representes : sans ca, "tout rougit" passerait.
    assert {rc for _, _, _, rc in EMP.MUTANTS} == {0, 1}, (
        "les mutants du tri ne couvrent qu'un seul sens : la contre-epreuve ne discrimine pas")


def test_etage9_un_NOM_APPARU_n_est_JAMAIS_un_echec():
    """C'est ce que PRODUIT un hissage reussi (le nom importe devient attribut du module) : le
    fermer ferait rougir toute la tranche qui a hisse 625 imports."""
    ref = {"engine.m.A": 1, "!TEMOIN!attributs": 1}
    mesure = {"engine.m.A": 1, "engine.m.NOUVEAU": 2, "!TEMOIN!attributs": 2}
    d = EMP.comparer(ref, mesure)
    assert d["rc"] == 0, "un NOM APPARU fait echouer l'empreinte : %r" % d
    assert len(d["apparus"]) == 1


def test_etage10_une_declaration_PERIMEE_echoue_aussi():
    """Une porte laissee ouverte apres usage est le mode de defaillance SUIVANT."""
    ref = {"engine.m.A": 1, "!TEMOIN!attributs": 1}
    d = EMP.comparer(ref, dict(ref), ("engine.m.A",))
    assert d["rc"] == 1, "une declaration PERIMEE passe : la porte reste ouverte"
    assert d["declarations_perimees"] == ["engine.m.A"]


def test_etage11_un_module_qui_ne_s_importe_PLUS_echoue():
    """La cle `!IMPORT!<mod>` APPARAISSAIT, et un APPARU ne comptait pas : une regression
    d'import etait donc structurellement invisible de cette sonde."""
    ref = {"engine.m.A": 1, "!TEMOIN!attributs": 1}
    mesure = {"engine.m.A": 1, "!IMPORT!engine.m": "ImportError: cannot import name 'X'",
              "!TEMOIN!attributs": 2}
    d = EMP.comparer(ref, mesure)
    assert d["rc"] == 1, "un module qui ne s'importe plus passe VERT : %r" % d
    assert [m for m, _ in d["imports_casses"]] == ["engine.m"]
    # sens inverse : un module REPARE est une amelioration, jamais un echec.
    d2 = EMP.comparer(mesure, ref)
    assert d2["rc"] == 0 and len(d2["imports_repares"]) == 1
