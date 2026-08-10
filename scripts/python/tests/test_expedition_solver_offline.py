"""Garde du solveur d'Operations (Expeditions) -- 100 % OFFLINE, aucun runner.

Ce que ce fichier protege, et pourquoi ces cas-la :

1. La MINIMALITE de la couverture. C'est tout l'interet du solveur : une unite
   pivot qui coche deux objectifs libere une place. Un solveur qui rendrait
   << un personnage par objectif >> serait valide-mais-inutile, et ca ne se voit
   PAS sur un resultat isole -- il faut un cas ou la reponse naive et la reponse
   optimale different.
2. Le ZERO NOMME. Un objectif sans aucun porteur doit sortir en `ok=False` AVEC
   son libelle. Rendre une liste vide sans dire lequel est introuvable, c'est le
   defaut classique << 0 se lit comme rien a signaler >>.
3. Le PLAFOND `participants`. Une couverture qui existe mais depasse le nombre de
   places n'est PAS une solution.
4. Le REFUS d'un identifiant ambigu ou inconnu. Forcer un id au hasard rendrait un
   plan faux d'apparence juste -- pire qu'une erreur.
5. La DISJONCTION du plateau. Une unite envoyee est immobilisee ; deux operations
   ne peuvent pas se partager le meme pivot.

Les kits sont SYNTHETIQUES : le solveur est teste sur sa logique, pas sur le
gameconfig du jour, donc ce garde ne rougit pas au prochain changement de build.
"""

DECLENCHEUR = {
    "chemins": (
        "scripts/python/expedition_solver.py",
        # Importe AU CHARGEMENT du solveur : un changement de son API casse l'import
        # de ce fichier avant meme le premier assert. Declare bien qu'aucun test
        # ci-dessous ne LISE le gameconfig -- les kits sont synthetiques.
        "scripts/python/unit_map.py",
        # Tire par `unit_map` au chargement, meme chaine de raisonnement.
        "scripts/python/gameconfig.py",
        "scripts/python/tests/test_expedition_solver_offline.py",
    ),
    # Aucun test ici ne lit le dump ni le gameconfig : les kits sont fabriques a la
    # main, precisement pour que ce garde ne rougisse PAS au changement de build.
    "build": False,
    "toujours": False,
    "raison": "Le solveur lui-meme, les deux modules qu'il importe au chargement "
              "(une rupture d'API y casse l'import avant tout assert), et ce fichier. "
              "Volontairement LARGE sur `unit_map`/`gameconfig` : ce garde n'exerce "
              "que la logique de couverture sur des kits SYNTHETIQUES, mais une "
              "signature changee cote import le ferait tomber, et un declencheur qui "
              "ne le prevoit pas serait un faux vert.",
}

import os                                                               # noqa: E402
import sys                                                              # noqa: E402

import pytest                                                           # noqa: E402

_ICI = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(_ICI)
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import expedition_solver as ES  # noqa: E402


def _kit(uid, faction="Custodes", alliance="Imperial", traits=(), ranged_hits=0):
    return {"id": uid, "name": uid, "kind": "lineup", "faction": faction,
            "alliance": alliance, "traits": list(traits), "ranged_hits": ranged_hits}


VOCAB = ({"Custodes", "Ultramarines", "AdeptusAstartes"},
         {"Healer", "MkXGravis", "Parry"},
         {"Imperial", "Chaos"})


def _obj(txt):
    return ES.resoudre_objectif(txt, *VOCAB)


# --- 1. minimalite -----------------------------------------------------------

def test_pivot_reduit_la_taille_sous_la_reponse_naive():
    """Trois objectifs, mais une unite en couvre deux -> 2 unites, pas 3."""
    objs = [_obj("melee"), _obj("faction:Custodes"), _obj("trait:Healer")]
    cands = [
        _kit("pivot", faction="Custodes", ranged_hits=0),          # melee + Custodes
        _kit("soigneur", faction="Ultramarines", traits=["Healer"], ranged_hits=3),
    ]
    # Contre-epreuve : la reponse naive (un par objectif) vaudrait 3.
    assert len(objs) == 3
    r = ES.resoudre_operation(cands, objs, participants=5)
    assert r["ok"] is True
    assert r["taille"] == 2, "le pivot n'a pas ete exploite : %r" % (r["taille"],)


def test_une_seule_unite_peut_couvrir_tout():
    objs = [_obj("melee"), _obj("faction:Custodes"), _obj("trait:Parry")]
    cands = [_kit("solo", faction="Custodes", traits=["Parry"], ranged_hits=0)]
    r = ES.resoudre_operation(cands, objs, participants=3)
    assert r["ok"] is True and r["taille"] == 1


# --- 2. le zero est NOMME ----------------------------------------------------

def test_objectif_sans_porteur_sort_nomme_et_non_vide():
    objs = [_obj("melee"), _obj("trait:MkXGravis")]
    cands = [_kit("a", ranged_hits=0)]           # personne n'a MkXGravis
    r = ES.resoudre_operation(cands, objs, participants=5)
    assert r["ok"] is False
    # le garde-fou du garde-fou : la liste ne doit pas etre vide, sinon ce test
    # passerait sur un solveur qui ne dit rien.
    assert r["impossibles"], "aucun objectif nomme alors que la couverture echoue"
    assert any("MkXGravis" in o for o in r["impossibles"])
    assert any(c["candidats"] == 0 for c in r["couverture"])


# --- 3. plafond de participants ----------------------------------------------

def test_participants_insuffisants_refuse_meme_si_la_couverture_existe():
    objs = [_obj("faction:Custodes"), _obj("trait:Healer"), _obj("trait:MkXGravis")]
    cands = [
        _kit("c", faction="Custodes", ranged_hits=1),
        _kit("h", faction="Ultramarines", traits=["Healer"], ranged_hits=1),
        _kit("g", faction="Ultramarines", traits=["MkXGravis"], ranged_hits=1),
    ]
    # Avec 3 places : possible.
    assert ES.resoudre_operation(cands, objs, participants=3)["ok"] is True
    # Avec 2 : impossible, et la raison doit le dire.
    r = ES.resoudre_operation(cands, objs, participants=2)
    assert r["ok"] is False
    assert r["taille"] is None
    assert "IMPOSSIBLE" in r["raison"]


# --- 4. refus d'un identifiant douteux ---------------------------------------

def test_identifiant_inconnu_leve():
    with pytest.raises(ES.ObjectifIrresoluble) as e:
        _obj("trait:Nexiste Pas")
    assert "INCONNU" in str(e.value)


def test_un_identifiant_EXACT_prime_sur_l_approximatif():
    """Ce test existe parce que le premier jet du garde accusait le code A TORT.

    On avait construit l'<< ambiguite >> avec {"AdeptusAstartes", "Astartes"} et
    l'entree "Astartes" -- or celle-ci correspond EXACTEMENT a l'un des deux, et
    l'exact DOIT primer. Le code avait raison, le test avait tort. On garde donc
    la regle explicitement, pour qu'un futur durcissement de `_apparier` ne la
    casse pas en croyant bien faire."""
    factions = {"AdeptusAstartes", "Astartes"}
    o = ES.resoudre_objectif("faction:Astartes", factions, VOCAB[1], VOCAB[2])
    assert o.valeur == "Astartes"


def test_identifiant_ambigu_leve_et_liste_les_candidats():
    # Vraie ambiguite : "Astartes" ne matche EXACTEMENT aucun des deux, mais est
    # suffixe des deux -- aucune raison de trancher, donc on refuse.
    factions = {"AdeptusAstartes", "GreyAstartes"}
    with pytest.raises(ES.ObjectifIrresoluble) as e:
        ES.resoudre_objectif("faction:Astartes", factions, VOCAB[1], VOCAB[2])
    msg = str(e.value)
    assert "AMBIGU" in msg
    assert "AdeptusAstartes" in msg and "GreyAstartes" in msg, (
        "le refus doit LISTER les candidats, sinon l'utilisateur ne peut pas trancher")


def test_forme_non_reconnue_leve():
    with pytest.raises(ES.ObjectifIrresoluble):
        _obj("nimportequoi")


# --- 5. melee mirroir de "without a normal ranged attack" --------------------

def test_melee_est_bien_absence_d_attaque_a_distance():
    m = _obj("melee")
    assert ES.satisfait(_kit("x", ranged_hits=0), m) is True
    assert ES.satisfait(_kit("y", ranged_hits=2), m) is False
    r = _obj("ranged")
    assert ES.satisfait(_kit("y", ranged_hits=2), r) is True


# --- 6. plateau : unites disjointes ------------------------------------------

def test_plateau_ne_reutilise_pas_la_meme_unite_sur_deux_operations():
    pivot = _kit("pivot", faction="Custodes", traits=["Healer"], ranged_hits=0)
    kits = {"pivot": pivot}
    ops = []
    for i in (1, 2):
        ops.append({"id": "op%d" % i, "expeditionId": "op%d" % i,
                    "participants": 1, "grandAlliance": "Imperial",
                    "_objs": [_obj("faction:Custodes")]})
    r = ES.resoudre_plateau(ops, kits, ["pivot"])
    # Une seule unite existe : une seule operation peut obtenir son bonus.
    assert r["couvertes"] == 1, "la meme unite a ete affectee deux fois"
    affectees = [p["ensemble"] for p in r["plan"] if p["ensemble"] is not None]
    assert affectees == [["pivot"]]


def test_plateau_couvre_les_deux_operations_quand_le_roster_suffit():
    kits = {
        "a": _kit("a", faction="Custodes", ranged_hits=0),
        "b": _kit("b", faction="Custodes", ranged_hits=0),
    }
    ops = [{"id": "op%d" % i, "expeditionId": "op%d" % i, "participants": 1,
            "grandAlliance": "Imperial", "_objs": [_obj("faction:Custodes")]}
           for i in (1, 2)]
    r = ES.resoudre_plateau(ops, kits, ["a", "b"])
    assert r["couvertes"] == 2
    assert r["unites_mobilisees"] == 2
