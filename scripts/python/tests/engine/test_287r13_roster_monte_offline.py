"""#287-r13 -- GARDE : le roster DEMANDE est confronte au roster MONTE, et le DEFICIT est NOMME.

CE QUE CE FICHIER GARDE, et pourquoi il existe. `rl_duel build` portait DEUX confrontations
(`_validate_placements` en amont, `_verify_placements` en aval) et l'une comme l'autre ne visite que
les unites CITEES par `--place`/`--a-place`. Une unite du roster confiee au placement NATIF
(`BC.PredefinedUnits` -> `IdunBattle.Operations.SetupGameOperation$$AddPredefinedUnits`) qui n'arrive
pas ne traverse AUCUNE de leurs lignes.

MESURE qui a ouvert la tranche (board `C1_02`, seed 4242) : `--a-units necroWarden x4` avec TROIS
`--a-place` monte **3 unites sur 4**, imprime `[build] placements verifies OK (4)` et rend **rc 0**,
en affichant un roster adverse a quatre entrees. La geometrie mesuree n'est alors pas celle demandee,
et un cote de bascule disparait sans trace.

⚠ L'ENONCE DU RESIDU ETAIT EN PARTIE FAUX, ET C'EST CE QUI REND CE FICHIER NECESSAIRE. Il disait
« un `--place` dont l'unite n'arrive pas est SILENCIEUX » : REFUTE par mesure -- `_verify_placements`
couvre deja ce cas (`[error] placement NON HONORE par le natif: necroWarden (team2) demande @(0,6)
mais present @[(2,3),(1,1),(4,6)]`, rc 3). Le silence etait ailleurs. Un test qui ne garderait que
`_verify_placements` graverait donc l'enonce faux.

CINQ ETAGES, tous OFFLINE (aucun runner, aucune session) -- `_verify_roster` est une fonction PURE
de `(decisionView, p_units, a_units)` :

  * ETAGE 1 -- LE DEFICIT MORD, et le message NOMME l'unite, la team et le compte. Assertionne son
    propre NON-VIDE : un etage qui rend une liste vide passerait pour vert.
  * ETAGE 2 -- LE ROSTER COMPLET NE MORD PAS. C'est le cran anti-faux-positif : sans lui, une garde
    qui rougirait TOUJOURS serait aussi verte a l'etage 1.
  * ETAGE 3 -- LE SURPLUS NE MORD PAS. Un summon pose au deploiement, une unite de boss : ils
    AJOUTENT des entites. Seul le DEFICIT est une faute.
  * ETAGE 4 -- LES `unitId` A PALIER sont normalises (`tauNpc5StealthSuit:5` demande,
    `tauNpc5StealthSuit` monte -> aucun ecart), et la troncature ne s'applique QUE si la partie
    droite est un entier (un `:` non numerique reste dans l'id).
  * ETAGE 5 -- LA TEAM DISCRIMINE. Le MEME `visualId` peut etre des DEUX cotes (rosters croises) :
    sans la team, un deficit du joueur se lirait comme comble par l'unite adverse homonyme. C'est
    exactement la faute que `_verify_placements` avait deja commise a son premier jet.

ASCII only. Aucun `print` non-ASCII.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import rl_duel as RD                                                     # noqa: E402

#: #486-r15 -- le declencheur de ce fichier.
DECLENCHEUR = {
    "chemins": (
        # LES MODULES RACINE de `scripts/python` -- 983 fichiers. C'est le glob que la MESURE
        # impose, pas une facilite : un premier jet nommait les quatre chemins que ce test
        # importe VRAIMENT (`rl_duel`, `rl_collect_batch`, `gameconfig`, `engine/**`) et le
        # cliquet a rendu **22 chemins hors perimetre**, TOUS a la racine -- `conftest.py`,
        # `board.py`, `catalog_inject.py`, `enum_maps.py`, `green_skip_guard.py`,
        # `declencheur_guard.py`, `engine_validate.py`, `engine_agreement_stages.py`, ... Ils
        # viennent du CONFTEST de la banque, que pytest charge pour tout fichier de `tests/`,
        # pas du test lui-meme. Les enumerer serait plus etroit ET plus fragile : une arete
        # ajoutee au conftest -- fichier partage -- casserait la declaration d'un test qui n'a
        # pas bouge, et un declencheur trop ETROIT fabrique un FAUX VERT.
        "scripts/python/*.py",
        # Le paquet moteur (456 fichiers) et la banque (782). `tools/` (1 fichier) reste HORS
        # perimetre : rien de la cascade ne l'importe.
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Garde PUREMENT OFFLINE de deux fonctions de `rl_duel` : `_verify_roster` et "
        "`_base_unit_id`. Elle construit ses `decisionView` A LA MAIN (des dicts de trois "
        "clefs), ne monte aucun runner, n'ouvre ni le gameconfig ni le seed BC ni un board, et "
        "ne confronte RIEN au jeu -- son verdict ne peut donc pas basculer sur un changement de "
        "build (`build: False`), et c'est ce qui BORNE reellement ce declencheur : ni `data/`, "
        "ni `frida/`, ni `docs/`, ni les boards ne peuvent le faire changer d'avis. Ce qui le "
        "fait basculer est le CODE de `rl_duel` et la cascade d'import que le conftest de la "
        "banque traine derriere lui -- mesuree a 22 modules RACINE de `scripts/python`, d'ou le "
        "glob racine plutot qu'une enumeration."),
}


def _dec(units):
    """Un `decisionView` MINIMAL -- seuls `visualId` et `team` sont lus par `_verify_roster`."""
    return {"units": [{"visualId": v, "team": t} for v, t in units]}


# ================================================================================================ #
# ETAGE 1 -- LE DEFICIT MORD, ET IL NOMME
# ================================================================================================ #

def test_etage1_le_deficit_mord_et_nomme_unite_team_et_compte():
    """Le cas MESURE : quatre `necroWarden` demandes au camp adverse, trois montes."""
    dec = _dec([("orksNob", 1), ("necroWarden", 2), ("necroWarden", 2), ("necroWarden", 2)])
    pb = RD._verify_roster(dec, ["orksNob"], ["necroWarden"] * 4)
    # NON-VIDE assertionne : un etage qui rend `[]` passerait pour vert sans rien mesurer.
    assert pb, "le deficit MESURE (4 demandes, 3 montes) doit produire au moins un ecart"
    assert len(pb) == 1, f"un seul ecart attendu, recu {pb}"
    msg = pb[0]
    for jeton in ("necroWarden", "team2", "x4", "x3"):
        assert jeton in msg, f"le message n'ecrit pas {jeton!r} : {msg!r}"


def test_etage1b_le_deficit_du_camp_joueur_mord_aussi():
    """Le camp du JOUEUR passe par `AddUnitMessage`, l'adverse par `PredefinedUnits` : deux
    chemins natifs distincts, une seule garde. Sans cette ligne, la moitie du perimetre serait
    non testee et la garde pourrait ne lire que `a_units` sans que rien ne rougisse."""
    dec = _dec([("ultraTitus", 1), ("necroWarden", 2)])
    pb = RD._verify_roster(dec, ["ultraTitus", "ultraTitus"], ["necroWarden"])
    assert len(pb) == 1 and "team1" in pb[0], f"deficit joueur non vu : {pb}"


# ================================================================================================ #
# ETAGE 2 -- LE ROSTER COMPLET NE MORD PAS (cran anti-faux-positif)
# ================================================================================================ #

def test_etage2_roster_complet_ne_mord_pas():
    dec = _dec([("orksNob", 1), ("ultraTitus", 1), ("ultraTitus", 1),
                ("necroWarden", 2), ("necroWarden", 2)])
    pb = RD._verify_roster(dec, ["orksNob", "ultraTitus", "ultraTitus"],
                           ["necroWarden", "necroWarden"])
    assert pb == [], f"aucun ecart attendu sur un roster integralement monte : {pb}"


# ================================================================================================ #
# ETAGE 3 -- LE SURPLUS NE MORD PAS
# ================================================================================================ #

def test_etage3_le_surplus_ne_mord_pas():
    """Un summon pose au deploiement AJOUTE une entite dans l'equipe de son summoner. Le rendre
    fautif ferait rougir tout montage a summon -- une garde qui refuse le normal est pire que
    l'absence de garde."""
    dec = _dec([("orksRukkatrukk", 1), ("orksSmnSquig", 1), ("orksSmnSquig", 1),
                ("necroWarden", 2)])
    pb = RD._verify_roster(dec, ["orksRukkatrukk"], ["necroWarden"])
    assert pb == [], f"un SURPLUS ne doit jamais faire faute : {pb}"


# ================================================================================================ #
# ETAGE 4 -- LES `unitId` A PALIER SONT NORMALISES
# ================================================================================================ #

def test_etage4_palier_numerique_normalise():
    """`--explicit-stats tauNpc5StealthSuit:5` exige la forme a palier dans `--p-units`, mais le
    `visualId` republie par `decisionView` ne la porte pas. Sans normalisation, TOUT montage npc a
    palier rougirait -- mesure : 0 faux positif sur ce montage apres normalisation."""
    dec = _dec([("tauNpc5StealthSuit", 1), ("tauNpc5StealthSuit", 1),
                ("orksWarboss", 2), ("thousTzaangor", 2)])
    pb = RD._verify_roster(dec, ["tauNpc5StealthSuit:5", "tauNpc5StealthSuit:5"],
                           ["orksWarboss", "thousTzaangor"])
    assert pb == [], f"un id a PALIER ne doit pas produire d'ecart : {pb}"


def test_etage4b_la_troncature_est_conditionnelle_a_un_entier():
    """La coupe ne s'applique QUE si la partie droite est un ENTIER. Un `:` non numerique reste
    dans l'id : c'est le sens PRUDENT (au pire on compare deux noms identiques), et l'inverse
    -- tronquer aveuglement au dernier `:` -- confondrait deux ids distincts."""
    assert RD._base_unit_id("tauNpc5StealthSuit:5") == "tauNpc5StealthSuit"
    assert RD._base_unit_id("thousNpc2Screamer:45") == "thousNpc2Screamer"
    assert RD._base_unit_id("necroWarden") == "necroWarden"
    assert RD._base_unit_id("necroWarden:pvp") == "necroWarden:pvp"
    assert RD._base_unit_id(":5") == ":5", "un id VIDE a gauche ne doit pas devenir la chaine vide"


# ================================================================================================ #
# ETAGE 5 -- LA TEAM DISCRIMINE
# ================================================================================================ #

def test_etage5_la_team_discrimine_les_homonymes():
    """Rosters CROISES : le meme `visualId` des deux cotes. Sans la clef `(visualId, team)`, le
    deficit du camp 1 se lirait comme comble par les exemplaires du camp 2 -- faute deja commise
    au premier jet de `_verify_placements`, et gardee ici pour qu'elle ne revienne pas."""
    dec = _dec([("necroWarden", 1), ("necroWarden", 2), ("necroWarden", 2), ("necroWarden", 2)])
    pb = RD._verify_roster(dec, ["necroWarden", "necroWarden"], ["necroWarden", "necroWarden"])
    assert len(pb) == 1, f"un seul ecart attendu (team1 : 2 demandes, 1 monte), recu {pb}"
    assert "team1" in pb[0] and "x2" in pb[0] and "x1" in pb[0], pb[0]


def test_etage5b_une_unite_absente_de_tout_deploiement_mord():
    """Le cas EXTREME : l'unite n'apparait NULLE PART. Le compte monte vaut 0, pas `None` -- un
    tri-etat serait ici une fausse prudence, `decisionView` publie TOUTES les unites deployees."""
    dec = _dec([("orksNob", 1)])
    pb = RD._verify_roster(dec, ["orksNob"], ["necroWarden"])
    assert len(pb) == 1 and "x0" in pb[0], f"une unite jamais deployee doit mordre : {pb}"
