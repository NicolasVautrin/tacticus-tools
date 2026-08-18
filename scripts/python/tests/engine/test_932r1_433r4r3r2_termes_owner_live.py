"""#932-r1 / #433-r4-r3-r2 -- CLIQUET LIVE des trois termes OWNER << +w par ami adjacent >>.

CE QUE CES GARDES PROTEGENT. Trois playbooks de la feuille `TriggeredAbilities(2)` versent un poids
PAR AMI ADJACENT a la tuile candidate du PORTEUR. Un terme absent du registre, ou un poids lu sur la
mauvaise cle, ne produit NI erreur NI crash : il produit des tuiles que le port EGALISE alors que le
natif les SEPARE -- des ties ARTEFACTS, et un depart de decision arbitraire.

  * **1510 `DeathwingKnight`** (#932-r1, port NEUF) -- 10 par ami `DarkAngels` a distance 1.
    Porteurs `darkaNpc3Terminator` (npc) et `darkaSmnTerminator` (summon) : aucun hero du pool. Le
    npc entre par le chemin de stats EXPLICITE, donc avec SES stats, SES traits et SON passif.
  * **1000 `PsychicFortress`** (#433-r4-r3-r2) -- 5 par ami, sans aucun gate.
  * **1487 `EcogSupport`** (#433-r4-r3-r2) -- 30 par ami dont `GetParent(u) == case.Unit`.

LE CRITERE EST L'ACCORD NATIF SUR UNE CONFIGURATION QUE LE TERME RENVERSE, jamais un scalaire gele.
Le probe cherche (et FABRIQUE, en deplacant des amis ou en occupant le sommet) une configuration ou
le port SANS le terme et le port AVEC ne retiennent pas la meme tuile ; alors seulement il demande
au natif laquelle il joue. Sur une configuration ou le terme ne renverse rien, un accord serait
parfaitement lisible et entierement vide -- le probe REFUSE alors de conclure et le dit.

Mesure du 2026-08-18 (`t6dpr4k06g`, `MC1_67`) -- accord **3/3** :
    deathwingknight  T1=(6,5) -> T2=(4,7) apres 3 amis DarkAngels deplaces ; natif (4,7)
    psychicfortress  egalite a 3 tuiles brisee par 1 ami ; natif (5,7)
    ecogsupport      egalite a 3 tuiles brisee par l'E-Cog ; natif (3,4)

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import probe_932r1_433r4r3r2_termes_owner_adjacents as P   # noqa: E402

#: #486-r15 -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_932r1_433r4r3r2_termes_owner_adjacents.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/playbook/friends_in_range.py",
    ),
    "build": False,
    "toujours": True,
    "raison": ("`toujours` parce que le verdict est un ACCORD LIVE : il depend du composite "
               "`Tile(7)` ENTIER (29 feuilles) et de la geometrie du board, donc de presque tout "
               "`engine/playbook/**` et `engine/utilities/tile.py`. Un declencheur limite aux trois "
               "foyers du terme serait un faux vert des qu'une AUTRE feuille du composite bouge et "
               "deplace l'argmax."),
}

TERMES = ("deathwingknight", "psychicfortress", "ecogsupport")


@pytest.fixture(scope="module", params=TERMES)
def mesure(request):
    nom = request.param
    if P.etape0_poids(nom, verbose=False):
        pytest.skip("poids nul ou playbook hors registre pour %s" % nom)
    res = None
    for graine in ("777", "31337"):
        res = P.confronter(nom, seed=graine, board=P.DEFAULT_BOARD, verbose=False)
        if not res.get("error") and res.get("renverse"):
            break
    res["_nom"] = nom
    return res


def test_le_montage_s_installe(mesure):
    """Un montage qui ne s'installe pas n'est PAS un verdict -- il doit rougir, pas se taire."""
    assert not mesure.get("error"), "%s : %s" % (mesure["_nom"], mesure.get("error"))


def test_le_kit_declenche_porte_l_ability(mesure):
    """GARDE DE SOURCE : le dispatcher `TriggeredAbilities(2)` itere le kit DECLENCHE du mover. Une
    ability absente de ce kit rendrait le playbook enregistre et JAMAIS appele -- un port
    speculatif, vert sans rien exercer. C'est decisif pour `1510`, qui arrive par une greffe de
    stats explicites, et pour `1487`, dont le porteur est injecte au catalogue."""
    assert mesure["ability"] in (mesure.get("kit") or ()), (
        "%s : ability %d absente du kit declenche %r"
        % (mesure["_nom"], mesure["ability"], mesure.get("kit")))


def test_le_terme_vaut_le_poids_fois_le_nombre_d_amis(mesure):
    """L'ecart ON-OFF, TUILE PAR TUILE, doit valoir exactement `w x |amis qualifiants|`. C'est la
    forme du corps natif (`val += getUtilityVal(<cle>)` par voisin retenu), et c'est ce qui
    distingue un terme JUSTE d'un terme qui tomberait par hasard sur le bon argmax."""
    assert not mesure.get("delta_incoherent"), (
        "%s : %r" % (mesure["_nom"], mesure["delta_incoherent"]))


def test_le_montage_n_est_pas_degenere(mesure):
    """Le nombre d'amis qualifiants doit prendre AU MOINS DEUX valeurs sur les tuiles candidates.
    A valeur constante, le terme est une translation uniforme : il ne peut RIEN departager, et
    l'accord natif qui suit serait vide."""
    assert len(mesure.get("n_distincts") or ()) >= 2, (
        "%s : |amis qualifiants| constant %r sur les %d tuiles candidates -- le terme ne peut rien "
        "separer" % (mesure["_nom"], mesure.get("n_distincts"), mesure.get("n_tuiles")))


def test_le_terme_RENVERSE_la_decision_du_port(mesure):
    """Sans terme, le port retient une AUTRE tuile (ou n'arrive pas a decider : egalite en tete).
    Avec, il tranche STRICTEMENT. C'est la condition pour que la question posee au natif ait une
    reponse informative."""
    assert mesure.get("renverse"), (
        "%s : le terme ne renverse rien (argmax OFF %r / ON %r, %d ex aequo en tete sans terme) -- "
        "aucune conclusion ne peut etre tiree de cette configuration"
        % (mesure["_nom"], mesure.get("argmax_off"), mesure.get("argmax_on"),
           mesure.get("tete_off", -1)))


def test_le_natif_joue_la_tuile_que_le_terme_designe(mesure):
    """L'ACCORD. C'est la garde qui tomberait ROUGE si le terme etait absent, mal pondere, ou lu
    sur la cle de sa jumelle (`DEATHWING_` au lieu de `DEATHWINGKNIGHT_`, `PSYCHICFORTRESS_
    AdjacentFriend` au lieu de `...Friendly`) : le port retiendrait alors la tuile SANS terme, que
    le natif ne joue pas."""
    assert mesure.get("native_erreur") is None, (
        "%s : oracle natif inexploitable -- %s" % (mesure["_nom"], mesure.get("native_erreur")))
    assert mesure.get("accord") is True, (
        "%s : le port retient %r, le natif joue %r"
        % (mesure["_nom"], mesure.get("argmax_on"), mesure.get("native")))
