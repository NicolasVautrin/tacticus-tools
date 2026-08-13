"""#1021 -- cliquet : une active de `ABILITY_CLASSES` porte son VERDICT de face DECISION.

100 % OFFLINE (aucun runner).

CE QUE CE FICHIER GARDE, ET POURQUOI IL EXISTE
------------------------------------------------
`probe_1021_face_decision_au_registre.py` MESURE et rend un `rc` ; ce fichier REFUSE que le cran
se degrade en silence. La distinction n'est pas cosmetique : un cliquet qu'AUCUNE passe de test ne
joue n'est pas un cliquet -- c'est le vice que `probe_486r15` documente (un garde que personne
n'interroge ne garde rien).

Les etages 1 a 3 sont les TROIS CRANS eux-memes. Les etages 4 a 7 sont les CONTRE-EPREUVES : un
cran jamais vu rougir ne prouve rien, et c'est exactement le defaut repare ici (`probe_909`
comptait et rendait `rc=0`). L'etage 8 garde la propriete la plus fragile du lot -- que le PROGRES
ne rougisse JAMAIS.

⚠ POURQUOI AUCUN ETAGE NE COMPARE UN COMPTE A UN NOMBRE. Le 2026-08-13, CINQ cliquets ont rougi
parce qu'une ability avait ete PORTEE : leurs planchers de population (`>= 20`, `>= 1`,
`any(canal peuple)`) lisaient le progres comme une panne. Un `assert len(DETTE) == 16` aurait
exactement ce defaut : il rendrait ROUGE le commit qui tranche un item. La dette se garde par sa
FORME (le CRAN A la rend obligatoire pour toute entree neuve) et par le CRAN B (un item solde ne
peut pas retomber), jamais par son cardinal.

⚠ CE QUE CES CONTRE-EPREUVES MORDENT VRAIMENT. `probe_1021` lie `ABILITY_CLASSES` par
`from ... import` (forme A du CLAUDE.md) : un `monkeypatch.setattr` sur le module d'origine NE
MORDRAIT PAS. Les etages qui manipulent la population passent donc par `setitem` sur l'OBJET dict
lui-meme -- le meme que celui du module d'origine --, ce qui mord des deux cotes. Poser un patch
qui ne mord pas serait un vert qui ne mesure rien.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le cran sous test, et le probe dont il propage le verdict.
        "scripts/python/probe_1021_face_decision_au_registre.py",
        "scripts/python/probe_909_decision_actives_kit.py",
        # Le foyer UNIQUE du predicat de face DECISION, et le ledger du troisieme etat. Changer
        # l'un des deux change directement quels ids sont << sans verdict >>.
        "scripts/python/decision_face_voies.py",
        "scripts/python/coverage_attestations.py",
        "scripts/ratchets-951r2-couverture-attestee.json",
        # La population : le registre de la face COMBAT, et tout ce que sa cascade d'import tire.
        "scripts/python/engine/runner/abilities/**/*.py",
        "scripts/python/engine/playbook/**/*.py",
        "scripts/python/engine/entities/abilities/active_ability.py",
        # Le mirror d'enum : un renumerotage deplace les ids de la dette sous les pieds du cran.
        "scripts/python/enum_maps.py",
        "scripts/python/engine/entities/active_ability_type.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Il croise `ABILITY_CLASSES` (face COMBAT) avec les voies de `decision_face_voies` "
              "et le ledger d'attestations. Il change de verdict quand une ability entre au "
              "registre COMBAT, quand une voie de decision bouge (port livre ou retire), quand le "
              "ledger bouge, quand le mirror d'enum est renumerote -- et au CHANGEMENT DE BUILD "
              "(`build: True`), parce que `coverage_attestations.validite` PERIME toute "
              "attestation dont le `build` n'est plus celui de `data/symbols/CURRENT` : un "
              "nouveau build peut a lui seul remettre un item au compte des sans-verdict.",
}

import os                                                                # noqa: E402
import sys                                                               # noqa: E402

import pytest                                                            # noqa: E402

_ICI = os.path.dirname(os.path.abspath(__file__))
_PYROOT = os.path.dirname(os.path.dirname(_ICI))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import decision_face_voies as DFV                                        # noqa: E402
import enum_maps as EM                                                   # noqa: E402
import probe_1021_face_decision_au_registre as P                         # noqa: E402


@pytest.fixture(scope="module")
def mesure():
    return P.mesurer()


# ============================================================================================
#  Etage 0 -- la mesure MESURE (sinon tout le reste est un vert qui ne dit rien)
# ============================================================================================

def test_etage0_la_mesure_est_non_vide(mesure):
    """Un cliquet qui ne visite rien rend vert pour rien. On assertionne le non-vide D'ABORD.

    Le controle porte sur CHAQUE entree du predicat, pas seulement sur la population : un mirror
    vide ou une liste de voies vide rendrait << tout est sans verdict >>, et un ledger illisible
    rendrait << aucune constante >>. Chacun se lit ici separement pour que la panne se NOMME.
    """
    assert mesure, "`ABILITY_CLASSES` est vide -- la population n'a pas ete chargee"
    assert EM.ACTIVE_ABILITY_TYPE, "le mirror `ACTIVE_ABILITY_TYPE` est vide"
    assert DFV.VOIES, "`decision_face_voies.VOIES` est vide -- tout serait rendu NON PORTEE"
    portes = [a for a, v in mesure.items() if v["etat"] in ("PORTEE", "CONSTANTE")]
    assert portes, (
        "aucun id du registre ne porte de verdict : le predicat est casse, pas la dette")


def test_etage0b_la_population_est_bien_le_registre_de_combat(mesure):
    """La population VISITEE est exactement `ABILITY_CLASSES` -- ni un sous-ensemble, ni autre chose.

    Sans ce controle, une mesure qui filtrerait silencieusement (un `continue` de trop) rendrait un
    CRAN A vert sur une population amputee.
    """
    from engine.runner.abilities.handler import ABILITY_CLASSES
    assert set(mesure) == {int(a) for a in ABILITY_CLASSES}, (
        "la mesure ne visite pas exactement `ABILITY_CLASSES` (%d visites pour %d entrees)"
        % (len(mesure), len(ABILITY_CLASSES)))


def test_etage0c_le_predicat_est_celui_du_foyer_partage(mesure):
    """Le verdict vient de `decision_face_voies.etat`, pas d'une re-derivation locale.

    #979 a ferme exactement cette faille : `probe_909` et `audit_kit_coverage` testaient DEUX
    listes blanches divergentes pour la meme question (3 registres contre 4), et le compte annonce
    sur-comptait de 22 %. Un cran dont le predicat differe de celui de l'audit ne garde rien.
    """
    tables, att = DFV.voies_par_ability(), DFV.attestations()
    for aid, v in mesure.items():
        if v["nom"] is None:
            continue
        attendu, _d = DFV.etat(aid, v["nom"], tables, att)
        assert v["etat"] == attendu, (
            "id %d (%s) : la mesure rend %r, le foyer `decision_face_voies.etat` rend %r"
            % (aid, v["nom"], v["etat"], attendu))


# ============================================================================================
#  Etages 1 a 3 -- LES TROIS CRANS, sur l'arbre reel
# ============================================================================================

def test_etage1_cranA_aucun_sans_verdict_hors_dette(mesure):
    """CRAN A -- la question binaire de #1021.

    Une active entree dans `ABILITY_CLASSES` (donc dont la face COMBAT est portee) sans qu'aucun
    verdict ne dise ce qu'il en est de sa face DECISION est une regression SILENCIEUSE : l'unite
    s'execute fidelement mais est CHOISIE par le chemin generique -- invisible en replay.
    """
    k = P.crans(mesure)
    assert not k["A"], (
        "%d active(s) au registre COMBAT sans verdict de face DECISION et hors dette : %s. "
        "Trois issues : porter l'utilite (une voie de `decision_face_voies.VOIES`), attester "
        "`RIEN_A_PORTER`, ou attester `PORTE_HORS_REGISTRE` au ledger `coverage_attestations`. "
        "Detail : `python scripts/python/probe_1021_face_decision_au_registre.py`."
        % (len(k["A"]), [(a, mesure[a]["nom"]) for a in k["A"]]))


def test_etage2_cranB_les_tranches_le_restent(mesure):
    """CRAN B -- un item solde ne retombe pas sous couvert de sa vieille ligne de dette.

    Sans ce cran, la dette serait une amnistie permanente : un id tranche puis re-casse resterait
    tolere par le CRAN A, qui ne regarde que l'APPARTENANCE a `DETTE`.
    """
    k = P.crans(mesure)
    assert not k["B"], (
        "%d id(s) declare(s) TRANCHE ont PERDU leur verdict de face DECISION : %s -- c'est une "
        "regression, pas une dette" % (len(k["B"]), k["B"]))


def test_etage3_cranC_la_mesure_mesure(mesure):
    """CRAN C -- aucune des entrees du predicat n'est vide, et rien n'est visite << hors mirror >>."""
    k = P.crans(mesure)
    assert not k["C"], "la mesure est creuse : %s" % (k["C"],)


# ============================================================================================
#  Etages 4 a 7 -- LES CONTRE-EPREUVES (un cran jamais vu rougir ne prouve rien)
# ============================================================================================

def test_etage4_cranA_mord_sur_une_entree_neuve(mesure, monkeypatch):
    """CONTRE-EPREUVE du CRAN A, sur la VRAIE population.

    On ajoute au registre COMBAT un id d'`ActiveAbilityType` valide, sans verdict et hors dette --
    exactement le geste que le cran doit refuser -- et on re-MESURE. `setitem` sur l'objet dict est
    ce qui mord ici : `probe_1021` a lie `ABILITY_CLASSES` par `from ... import` (forme A), donc un
    `setattr` sur le module d'origine laisserait le cran aveugle et rendrait ce test faussement
    vert.
    """
    from engine.runner.abilities.handler import ABILITY_CLASSES
    cible = next((a for a, n in P.hors_registre_sans_verdict()
                  if a not in ABILITY_CLASSES and a not in P.DETTE), None)
    assert cible is not None, (
        "aucun id d'`ActiveAbilityType` sans verdict et hors registre : impossible de fabriquer "
        "le reactif. Si toutes les actives portent desormais un verdict, le DIRE et adapter cette "
        "contre-epreuve -- ne pas la retirer")
    victime = next(iter(ABILITY_CLASSES.values()))
    monkeypatch.setitem(ABILITY_CLASSES, cible, victime)

    k = P.crans(P.mesurer())
    assert cible in k["A"], (
        "id %d ajoute a `ABILITY_CLASSES` sans verdict et hors dette : le CRAN A ne l'a PAS vu "
        "(A=%s). Le cran est inerte." % (cible, k["A"]))


def test_etage5_cranB_mord_sur_une_regression(mesure, monkeypatch):
    """CONTRE-EPREUVE du CRAN B : un id declare TRANCHE mais dont l'etat mesure est NON PORTEE.

    On prend un id REELLEMENT sans verdict (donc de la dette) et on le declare TRANCHE : c'est la
    forme exacte d'une regression -- quelqu'un a promu la ligne sans que le verdict existe, ou le
    verdict a disparu depuis.
    """
    assert P.DETTE, "la dette est vide : plus rien a promouvoir, adapter cette contre-epreuve"
    cible = P.sans_verdict(mesure)[0]
    monkeypatch.setitem(P.DETTE, cible, ("TRANCHE", "TEMP -- contre-epreuve #1021"))

    k = P.crans(mesure)
    assert cible in k["B"], (
        "id %d declare TRANCHE sans porter de verdict : le CRAN B ne l'a PAS vu (B=%s)"
        % (cible, k["B"]))


def test_etage6_cranC_mord_sur_une_mesure_creuse():
    """CONTRE-EPREUVE du CRAN C : une population vide ne doit JAMAIS sortir verte.

    C'est le mode de defaillance le plus insidieux -- un import casse, un registre non charge, et
    tous les autres crans deviennent trivialement verts parce qu'ils n'ont rien a juger.
    """
    k = P.crans({})
    assert k["C"], "une population VIDE passe le CRAN C : le cran ne mesure pas sa propre mesure"
    assert not k["A"] and not k["B"], (
        "sur population vide, A et B sont trivialement verts -- c'est precisement pourquoi C doit "
        "rougir, et ce test le grave")


def test_etage7_cranC_mord_sur_un_id_hors_mirror(mesure, monkeypatch):
    """CONTRE-EPREUVE du CRAN C : un id du registre absent du mirror `ACTIVE_ABILITY_TYPE`.

    Le cas n'est pas theorique : un renumerotage d'enum entre deux builds deplace les ordinaux, et
    un id orphelin signifie qu'on ne visite pas ce qu'on croit visiter. Le rabattre sur << pas de
    verdict >> ecrirait un nom FAUX ; le rabattre sur << rien a signaler >> serait pire.
    """
    from engine.runner.abilities.handler import ABILITY_CLASSES
    orphelin = max(EM.ACTIVE_ABILITY_TYPE) + 1000
    assert orphelin not in EM.ACTIVE_ABILITY_TYPE
    monkeypatch.setitem(ABILITY_CLASSES, orphelin, next(iter(ABILITY_CLASSES.values())))

    k = P.crans(P.mesurer())
    assert any("hors du mirror" in m for m in k["C"]), (
        "id %d hors du mirror `ACTIVE_ABILITY_TYPE` : le CRAN C ne l'a PAS vu (C=%s)"
        % (orphelin, k["C"]))


# ============================================================================================
#  Etage 8 -- LE PROGRES NE ROUGIT JAMAIS (la propriete la plus fragile du lot)
# ============================================================================================

def test_etage8_un_item_tranche_ne_rougit_pas(mesure, monkeypatch):
    """INVARIANT -- un id de la dette qui ACQUIERT son verdict est un SUCCES, jamais un rouge.

    C'est le defaut du 2026-08-13, transpose : cinq cliquets ont rougi parce qu'une ability avait
    ete PORTEE. On simule le progres a la source -- une attestation `RIEN_A_PORTER` VALIDE de plus
    au ledger, donc l'etat passe a `CONSTANTE` -- et on exige que les trois crans restent verts et
    que l'item sorte par le canal `progres`.
    """
    cible = P.sans_verdict(mesure)[0]
    nom = mesure[cible]["nom"]
    vrai = DFV.attestations()
    monkeypatch.setattr(
        DFV, "attestations",
        lambda: dict(vrai, **{nom: {"verdict": "RIEN_A_PORTER", "categorie": "active-decision",
                                    "nom": nom, "source": "TEMP#1021"}}))

    mes2 = P.mesurer()
    assert mes2[cible]["etat"] == "CONSTANTE", (
        "le progres simule n'a pas mordu (etat %r) : la contre-epreuve ne prouverait rien"
        % mes2[cible]["etat"])
    k = P.crans(mes2)
    assert not k["A"] and not k["B"] and not k["C"], (
        "un item de la dette qui acquiert son verdict fait ROUGIR le cran (A=%s B=%s C=%s). Une "
        "dette qui descend est un succes -- c'est exactement le defaut des cinq cliquets a "
        "plancher de population du 2026-08-13." % (k["A"], k["B"], k["C"]))
    assert cible in k["progres"], (
        "id %d a acquis son verdict et ne sort PAS par le canal `progres` : le retrait de sa ligne "
        "de dette resterait invisible" % cible)


def test_etage9_le_compte_de_la_dette_n_est_compare_a_aucun_nombre():
    """INVARIANT DE FORME -- aucun cran ne doit tenir a un cardinal.

    Le controle est structurel, pas textuel : on RETIRE toute la dette et on verifie que le seul
    effet est de faire rougir le CRAN A sur les ids reellement sans verdict -- jamais un rouge qui
    dirait << la dette n'a pas la bonne taille >>. Un cliquet qui exigerait `len(DETTE) == N`
    rendrait ROUGE le commit qui tranche un item, et se ferait desarmer.
    """
    import unittest.mock as M
    mes = P.mesurer()
    manque = P.sans_verdict(mes)
    with M.patch.dict(P.DETTE, {}, clear=True):
        k = P.crans(mes)
    assert sorted(k["A"]) == sorted(manque), (
        "dette videe : le CRAN A devrait rendre EXACTEMENT les sans-verdict (%s), il rend %s"
        % (manque, k["A"]))
    assert not k["B"] and not k["C"], (
        "vider la dette a fait rougir B ou C : un cran tient a un cardinal (B=%s C=%s)"
        % (k["B"], k["C"]))


def test_etage10_toute_ligne_de_dette_porte_un_etat_admis_et_une_raison():
    """INVARIANT -- la dette n'est pas une liste blanche : chaque ligne DIT quoi, et pourquoi.

    Sans raison ecrite, un lecteur ne peut pas distinguer << lu, il n'y a rien a porter >> de
    << personne n'a regarde >>, donc il recopie la ligne. C'est le mecanisme d'IMITATION que le
    CLAUDE.md chiffre sur les imports differes (32 des 52 gratuits vivaient dans un module portant
    deja un differe legitime).
    """
    assert P.DETTE, "la dette est vide -- si elle est soldee, le dire et retirer ce garde"
    for aid, entree in sorted(P.DETTE.items()):
        assert isinstance(entree, tuple) and len(entree) == 2, (
            "ligne de dette %d malformee : %r" % (aid, entree))
        etat, raison = entree
        assert etat in P.ETATS, (
            "id %d : etat de dette %r inconnu -- admis : %s" % (aid, etat, ", ".join(P.ETATS)))
        assert len(raison.strip()) >= 60, (
            "id %d : raison de %d caractere(s). Une ligne de dette sans substance est une liste "
            "blanche deguisee -- citer le playbook natif et ce qui a ete LU."
            % (aid, len(raison.strip())))
        assert aid in EM.ACTIVE_ABILITY_TYPE, (
            "id %d de la dette n'est pas un membre du mirror `ACTIVE_ABILITY_TYPE`" % aid)


def test_etage11_probe_909_propage_le_verdict_du_cran():
    """INVARIANT -- le robinet nomme reste ferme.

    `probe_909_decision_actives_kit.py` comptait les actives sans face DECISION et rendait `rc=0`.
    Son etape 7 appelle desormais ce cran et AJOUTE ses fautes a son `rouge`. Si quelqu'un retire
    cet appel, le probe redevient un inventaire deguise en garde-fou -- et personne ne le verrait,
    puisque son `rc` resterait 0 tant que la dette couvre.
    """
    import probe_909_decision_actives_kit as P909
    src = open(P909.__file__, encoding="utf-8").read()
    assert "probe_1021_face_decision_au_registre" in src, (
        "`probe_909` n'appelle plus le cran #1021 : il est redevenu un inventaire qui compte sans "
        "mordre")
    assert 'rouge += len(k["A"]) + len(k["B"]) + len(k["C"])' in src, (
        "`probe_909` appelle le cran #1021 mais ne PROPAGE plus son verdict a son `rc` -- un "
        "appel qui n'influence pas le code de retour ne garde rien")
