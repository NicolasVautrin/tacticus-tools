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
6. L'ELIGIBILITE, mirror de `ExpeditionUnitEligibility$$IsEligibleFor`. POSSEDER
   N'EST PAS POUVOIR PARTIR, et le confondre a produit un faux resultat MESURE :
   sur la possession seule le plateau du 2026-08-10 rendait 7 bonus sur 7, alors
   que l'operation Mythic est INFAISABLE -- ses 10 unites eligibles couvrent ZERO
   de ses 6 objectifs. Le plan avait l'air juste et aurait ete refuse a l'envoi.
   Le cas est fige ici, avec le tri-etat qui l'entoure : une donnee non mesuree
   (seuil, rang) doit sortir en refus NOMME, jamais en `eligible` par defaut.

Les kits sont SYNTHETIQUES : le solveur est teste sur sa logique, pas sur le
gameconfig du jour, donc ce garde ne rougit pas au prochain changement de build.
"""

DECLENCHEUR = {
    "chemins": (
        "scripts/python/expedition_solver.py",
        # ⚠ `expedition_roster.py` et `gamenav/transport.py` ont ETE RETIRES du
        # declencheur EN MEME TEMPS que les modules eux-memes : ils lisaient le pool
        # par l'ecran (`uiList`/`uiClick`), et les neuf endpoints d'interface sont
        # supprimes. Un declencheur qui cite un chemin DISPARU ne protege rien -- il
        # se contente de ne jamais se declencher, ce qui se lit comme un vert.
        # Importe AU CHARGEMENT du solveur : un changement de son API casse l'import
        # de ce fichier avant meme le premier assert. Declare bien qu'aucun test
        # ci-dessous ne LISE le gameconfig -- les kits sont synthetiques.
        "scripts/python/unit_map.py",
        # Tire par `unit_map` au chargement, meme chaine de raisonnement.
        "scripts/python/gameconfig.py",
        # Le pilote : sa decision PURE `motif_non_partante` est gardee ici (le reste
        # exige une session vivante). Un motif faux ne casse RIEN -- il fait juste
        # conclure a l'envers, ce qui est deja arrive.
        "scripts/python/expedition_run.py",
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
# Le pilote n'ouvre AUCUNE connexion a l'import (tout l'I/O est dans des fonctions) :
# seule sa decision PURE `motif_non_partante` est exercee ici.
import expedition_run as ER  # noqa: E402


def _kit(uid, faction="Custodes", alliance="Imperial", traits=(), ranged_hits=0,
         profils=()):
    return {"id": uid, "name": uid, "kind": "lineup", "faction": faction,
            "alliance": alliance, "traits": list(traits), "ranged_hits": ranged_hits,
            "weapons": [{"profile": p} for p in profils]}


VOCAB = ({"Custodes", "Ultramarines", "AdeptusAstartes"},
         {"Healer", "MkXGravis", "Parry", "Mechanical"},
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


def test_les_commentaires_du_roster_se_coupent_PAR_LIGNE(tmp_path):
    """Regression : le filtre etait par JETON, donc `# Pool ELIGIBLE ...` faisait
    entrer `Pool`, `ELIGIBLE`, ... dans le roster (18 faux ids mesures sur un
    en-tete de deux lignes). Benin tant qu'ils sont inconnus -- mais un commentaire
    qui NOMME une unite l'ajouterait au roster sans que rien ne le dise. C'est ce
    cas-la que le test fabrique, pas le cas benin."""
    kits = {"custoTrajann": _kit("custoTrajann"), "ultraCalgar": _kit("ultraCalgar")}
    f = tmp_path / "roster.txt"
    # Le commentaire NOMME une unite reelle : si la coupe est par jeton, elle entre.
    f.write_text("# roster de secours, sans ultraCalgar pour l'instant\n"
                 "custoTrajann\n", encoding="utf-8")
    ids, suppose = ES._roster(str(f), kits)
    assert suppose is False
    assert ids == ["custoTrajann"], (
        "un identifiant cite dans un COMMENTAIRE est entre dans le roster : %r" % (ids,))


# --- 6bis. DamageType, multiplicites, formes natives -------------------------

DEGATS = {"Power", "Physical", "Psychic", "Piercing"}


def _objd(txt):
    return ES.resoudre_objectif(txt, VOCAB[0], VOCAB[1], VOCAB[2], DEGATS)


def test_damagetype_lit_le_profil_des_armes():
    o = _objd("DamageType:Psychic")
    assert ES.satisfait(_kit("psy", profils=["Flame", "Psychic"]), o) is True
    assert ES.satisfait(_kit("nope", profils=["Power"]), o) is False
    assert ES.satisfait(_kit("sansarme"), o) is False


def test_hasnorangedattack_est_accepte_avec_sa_cible_bidon():
    """Le plateau ecrit `HasNoRangedAttack:None`. Resoudre << None >> comme une faction
    donnerait un refus absurde ; la cible doit etre jetee AVANT l'appariement."""
    o = _objd("HasNoRangedAttack:None")
    assert o.kind == "melee"
    assert ES.satisfait(_kit("m", ranged_hits=0), o) is True


def test_forme_native_objet_est_normalisee():
    assert ES.normaliser_objectif_brut(
        {"objectiveType": "Trait", "objectiveTarget": "Healer"}) == "Trait:Healer"
    # Le serialiseur emet AUSSI la variante PascalCase : les deux doivent passer.
    assert ES.normaliser_objectif_brut(
        {"ObjectiveType": "Faction", "ObjectiveTarget": "Custodes"}) == "Faction:Custodes"
    assert ES.normaliser_objectif_brut("trait:Healer") == "trait:Healer"
    with pytest.raises(ES.ObjectifIrresoluble):
        ES.normaliser_objectif_brut(42)


def test_extraire_board_deroule_l_enveloppe_du_capteur():
    b = [{"id": "x"}]
    assert ES._extraire_board({"expeditionState": {"board": b}}) == b
    assert ES._extraire_board({"board": b}) == b
    assert ES._extraire_board(b) == b
    with pytest.raises(ValueError):
        ES._extraire_board({"rien": 1})


def test_un_objectif_REPETE_exige_DEUX_porteurs_distincts():
    """`Trait:Healer` deux fois sur le plateau reel. Avec UN seul soigneur, c'est
    infaisable ; avec deux, il faut les DEUX -- pas un seul compte double."""
    objs = [_objd("trait:Healer"), _objd("trait:Healer")]
    un = [_kit("h1", traits=["Healer"])]
    r = ES.resoudre_operation(un, objs, participants=5)
    assert r["ok"] is False
    assert any("requis 2" in o and "disponibles 1" in o for o in r["impossibles"]), (
        "le refus doit dire la MULTIPLICITE et le vivier : %r" % (r["impossibles"],))

    deux = un + [_kit("h2", traits=["Healer"])]
    r2 = ES.resoudre_operation(deux, objs, participants=5)
    assert r2["ok"] is True and r2["taille"] == 2


def test_plus_d_objectifs_que_de_places_reste_soluble():
    """C'EST LA MESURE QUI A REFUTE LA LECTURE STRICTE. Sur le plateau reel, 6 operations
    sur 7 ont PLUS d'objectifs que de places (op 3 : 6 objectifs, 4 places). Si chaque
    objectif exigeait un porteur qui lui soit propre, ces bonus seraient inatteignables.
    Un personnage DOIT donc compter pour plusieurs objectifs DIFFERENTS."""
    objs = [_objd("faction:Custodes"), _objd("trait:Parry"),
            _objd("DamageType:Power"), _objd("melee")]
    assert len(objs) == 4
    cands = [_kit("polyvalent", faction="Custodes", traits=["Parry"],
                  ranged_hits=0, profils=["Power"])]
    r = ES.resoudre_operation(cands, objs, participants=1)
    assert r["ok"] is True, "4 objectifs pour 1 place doivent tenir : %r" % (r["raison"],)
    assert r["taille"] == 1


def test_multiplicite_et_recouvrement_se_combinent():
    """Deux `Physical` + un `Mechanical` en 2 places : il faut deux porteurs Physical,
    dont au moins un Mechanical."""
    objs = [_objd("DamageType:Physical"), _objd("DamageType:Physical"),
            _objd("trait:Mechanical")]
    cands = [
        _kit("a", traits=["Mechanical"], profils=["Physical"]),
        _kit("b", profils=["Physical"]),
        _kit("c", traits=["Mechanical"]),          # pas de Physical
    ]
    r = ES.resoudre_operation(cands, objs, participants=2)
    assert r["ok"] is True and r["taille"] == 2
    # `c` ne peut pas figurer : il ne porte pas Physical, et les deux places sont prises
    # par les porteurs Physical.
    ids = {u["id"] for combo in r["solutions"] for grp in combo for u in grp["unites"]}
    assert "c" not in ids


# --- 7. capteur de pool : RETIRE avec la voie UI -----------------------------
#
# `expedition_roster.py` capturait le pool en lisant les boutons de l'ecran
# (`uiList`/`uiClick`). Les neuf endpoints d'interface ont ete SUPPRIMES : piloter
# l'ecran pour lire ou ecrire sur le compte est proscrit -- `expedition_run.py` avait
# deja retire son etape UI pour la meme raison (elle FAISAIT DISPARAITRE l'ecran du
# joueur). Le pipeline lit desormais le roster par le RPC natif `rosterOwned`, qui
# DEMANDE la possession au jeu au lieu de la deduire d'un ecran.
#
# Les quatre tests qui vivaient ici gardaient les fonctions PURES de ce capteur
# (`extraire`, `qualifier`). Ils partent avec lui : garder un test sur du code
# supprime le rendrait vert sans rien garder.

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


def test_une_operation_SANS_bonus_atteignable_part_quand_meme():
    """MESURE du 2026-08-11 : 6 operations parties la ou 7 pouvaient l'etre.

    Une operation dont aucun ensemble ne couvre les objectifs rapporte quand meme sa
    recompense de BASE. La renoncer laisse un slot vide -- ce n'est pas une optimisation,
    c'est une perte seche. Le bonus reste PRIORITAIRE : la base ne se sert qu'apres.
    """
    kits = {
        "cible": _kit("cible", faction="Custodes", ranged_hits=0),
        "quelconque": _kit("quelconque", faction="Ultramarines", ranged_hits=0),
    }
    ops = [
        # couvrable : `cible` porte la faction demandee
        {"id": "avec", "expeditionId": "avec", "participants": 1,
         "grandAlliance": "Imperial", "_objs": [_obj("faction:Custodes")]},
        # INCOUVRABLE : aucun kit ne porte ce trait -- mais l'operation peut PARTIR
        {"id": "sans", "expeditionId": "sans", "participants": 1,
         "grandAlliance": "Imperial", "_objs": [_obj("trait:MkXGravis")]},
    ]
    r = ES.resoudre_plateau(ops, kits, ["cible", "quelconque"])
    assert r["couvertes"] == 1, "le bonus reste prioritaire"
    assert r["partantes"] == 2, "l'operation sans bonus doit PARTIR pour sa base"
    assert r["base_seule"] == ["sans"]
    sans = next(p for p in r["plan"] if p["op"]["id"] == "sans")
    assert sans["equipe"] == ["quelconque"], (
        "la base seule ne doit pas voler l'unite qui debloque un bonus")


def test_le_remplissage_epargne_l_unite_RARE_pour_l_operation_servie_en_DERNIER():
    """MESURE du 2026-08-11 : deux des CINQ unites rang 17 du roster brulees en bourrage
    sur une operation a 32 eligibles, ce qui a verrouille la Mythic (5 candidats, 4 places).

    ⚠ CE CAS EST CALIBRE, et la premiere version ne discriminait PAS. Si l'unite rare
    appartient a un ensemble COUVRANT, la disjonction la reserve deja -- le test passait
    avec ou sans la presse. La presse ne compte que pour ce qui est servi EN DERNIER : les
    operations sans bonus, remplies apres toutes les autres. C'est exactement le cas reel.

    Montage : `etroite` n'a aucun bonus atteignable (personne ne porte le trait), donc elle
    passe en dernier, et son alliance Chaos ne laisse passer que `rare`. `large` a une place
    de remplissage et accepte les deux alliances. Sans presse, elle prend `rare` -- l'ordre
    du pool suit celui du roster -- et `etroite` ne part jamais.
    """
    kits = {
        "pivot": _kit("pivot", faction="Custodes", ranged_hits=0),
        "rare": _kit("rare", faction="AdeptusAstartes", alliance="Chaos", ranged_hits=0),
        "commune": _kit("commune", faction="Ultramarines", ranged_hits=0),
    }
    ops = [
        {"id": "large", "expeditionId": "large", "participants": 2,
         "grandAlliance": None, "_objs": [_obj("faction:Custodes")]},
        {"id": "etroite", "expeditionId": "etroite", "participants": 1,
         "grandAlliance": "Chaos", "_objs": [_obj("trait:MkXGravis")]},
    ]
    # `rare` AVANT `commune` dans le roster : sans presse, c'est elle que le pool sert.
    r = ES.resoudre_plateau(ops, kits, ["pivot", "rare", "commune"])
    large = next(p for p in r["plan"] if p["op"]["id"] == "large")
    assert "rare" not in (large["equipe"] or []), (
        "le remplissage a brule l'unite qui etait le SEUL recours de `etroite`")
    assert r["partantes"] == 2, "`etroite` doit partir pour sa base"
    assert r["base_seule"] == ["etroite"]


# ---------------------------------------------------------------------------
# ELIGIBILITE -- mirror de `ExpeditionUnitEligibility$$IsEligibleFor`
# ---------------------------------------------------------------------------

#: Mesures du 2026-08-10, niveau d'expedition 16/20, RPC `expeditionRankRequirements`.
SEUILS = {"Common": 0, "Uncommon": 3, "Rare": 6, "Epic": 9, "Legendary": 12, "Mythic": 17}


def _prog(**unites):
    """{id: (rang, rarete_ordinale)} -> la forme rendue par `rosterOwned {details:true}`."""
    return {u: {"rank": r, "rarity": q,
                "rarete": None if q is None else ES.RARETES[q]}
            for u, (r, q) in unites.items()}


def test_rarete_accepte_le_nom_et_l_ordinal():
    # Le serialiseur emet l'un ou l'autre selon qu'un StringEnumConverter est pose :
    # le plateau REEL du 2026-08-10 portait la chaine ("Legendary").
    assert ES.rarete_en_ordinal("Legendary") == 4
    assert ES.rarete_en_ordinal("legendary") == 4
    assert ES.rarete_en_ordinal(4) == 4
    assert ES.rarete_en_ordinal("4") == 4


def test_rarete_inconnue_rend_None_et_pas_zero():
    # Zero est `Common`, donc << aucune exigence >>. Le confondre avec << non lu >>
    # rendrait TOUT le roster eligible sur une operation qu'on n'a pas su lire.
    for v in ("Mythique", "", None, 99, -1, True, {}):
        assert ES.rarete_en_ordinal(v) is None, v


def test_refus_nomme_par_rarete_puis_par_rang():
    kits = {"u": _kit("u", alliance="Imperial")}
    entry = {"rarity": "Legendary", "grandAlliance": "Imperial"}
    # Rarete trop basse : refuse AVANT meme de regarder le rang.
    ok, motif = ES.est_eligible("u", kits, _prog(u=(50, 3)), entry, SEUILS)
    assert ok is False and "rarete insuffisante" in motif
    # Rarete suffisante mais rang sous le seuil de l'operation.
    ok, motif = ES.est_eligible("u", kits, _prog(u=(11, 4)), entry, SEUILS)
    assert ok is False and "rang insuffisant (11 < 12)" in motif
    ok, motif = ES.est_eligible("u", kits, _prog(u=(12, 4)), entry, SEUILS)
    assert (ok, motif) == (True, None)


def test_le_seuil_de_rang_vient_de_la_rarete_de_L_OPERATION():
    """Le piege central du decompile : `GetRequiredRankFor(entry.rarity)`, pas
    `GetRequiredRankFor(unit.rarity)`. Une Mythic rang 12 passe sur une operation
    Legendary (seuil 12) et ECHOUE sur une Mythic (seuil 17) -- meme unite, meme rang."""
    kits = {"u": _kit("u", alliance="Imperial")}
    prog = _prog(u=(12, 5))  # Mythic, rang 12
    ok, _ = ES.est_eligible("u", kits, prog, {"rarity": "Legendary"}, SEUILS)
    assert ok is True
    ok, motif = ES.est_eligible("u", kits, prog, {"rarity": "Mythic"}, SEUILS)
    assert ok is False and "rang insuffisant (12 < 17)" in motif


def test_alliance_ne_contraint_que_si_l_operation_en_impose_une():
    kits = {"x": _kit("x", alliance="Chaos")}
    prog = _prog(x=(20, 5))
    assert ES.est_eligible("x", kits, prog, {"rarity": "Common"}, SEUILS)[0] is True
    assert ES.est_eligible("x", kits, prog,
                           {"rarity": "Common", "grandAlliance": None}, SEUILS)[0] is True
    ok, motif = ES.est_eligible("x", kits, prog,
                                {"rarity": "Common", "grandAlliance": "Imperial"}, SEUILS)
    assert ok is False and "alliance" in motif


def test_une_donnee_NON_MESUREE_refuse_en_le_disant():
    """Le sens du refus compte : on ne veut ni un `True` par defaut (plan faux), ni un
    `False` muet (trou invisible). Le motif doit NOMMER ce qui manque."""
    kits = {"u": _kit("u", alliance="Imperial")}
    entry = {"rarity": "Rare"}
    ok, motif = ES.est_eligible("u", kits, _prog(u=(None, 3)), entry, SEUILS)
    assert ok is False and "rang NON MESURE" in motif
    ok, motif = ES.est_eligible("u", kits, _prog(u=(10, None)), entry, SEUILS)
    assert ok is False and "rarete NON MESUREE" in motif
    ok, motif = ES.est_eligible("u", kits, _prog(u=(10, 3)), entry, dict(SEUILS, Rare=None))
    assert ok is False and "seuil de rang NON MESURE" in motif
    ok, motif = ES.est_eligible("absente", kits, _prog(u=(10, 3)), entry, SEUILS)
    assert ok is False and "non possedee" in motif


def test_sans_progression_le_pool_retombe_sur_l_alliance_SEULE():
    """Repli assume, mais il doit rester DISCERNABLE : `resoudre_plateau` publie
    `eligibilite`, et un plan bati dessus peut proposer une unite refusee."""
    kits = {"a": _kit("a", alliance="Imperial"), "b": _kit("b", alliance="Chaos")}
    pool, refus = ES.pool_eligible({"grandAlliance": "Imperial"}, kits, ["a", "b"],
                                   None, None)
    assert pool == ["a"] and refus == {"b": "alliance"}
    ops = [{"id": "op", "expeditionId": "op", "participants": 1,
            "grandAlliance": "Imperial", "_objs": []}]
    assert ES.resoudre_plateau(ops, kits, ["a"])["eligibilite"] == "alliance seule"
    r = ES.resoudre_plateau(ops, kits, ["a"], progression=_prog(a=(20, 5)), seuils=SEUILS)
    assert r["eligibilite"] == "complete"


def test_pool_eligible_NON_VIDE_mais_couvrant_ZERO_objectif():
    """LE CAS MESURE, celui qui a produit le faux 7/7.

    `all_knowledge_m_04_10` (Mythic, 4 places) a 10 unites eligibles et SIX objectifs,
    dont AUCUN n'est porte par ces 10. Sur la possession seule, les porteurs existent
    (5 Healer, 12 Psychic, ...) et le solveur couvrait l'operation -- un plan que le
    jeu aurait refuse. Un pool non vide ne vaut donc pas couverture : il faut que le
    filtre s'applique AVANT l'enumeration des ensembles."""
    kits = {
        # Eligibles (Mythic, rang eleve) mais sans le trait demande.
        "gros1": _kit("gros1", alliance="Imperial", traits=["Parry"]),
        "gros2": _kit("gros2", alliance="Imperial", traits=["Parry"]),
        # Porteur du trait, mais rang trop bas pour une operation Mythic.
        "soigneur": _kit("soigneur", alliance="Imperial", traits=["Healer"]),
    }
    prog = _prog(gros1=(17, 5), gros2=(17, 5), soigneur=(12, 5))
    # 2 places, pas 4 : la contre-epreuve doit isoler l'effet de l'ELIGIBILITE. Avec 4
    # places et 3 unites au roster, c'est le REMPLISSAGE qui echouerait (cf.
    # `test_remplissage_obligatoire_*`), et le test passerait pour la mauvaise raison.
    op = {"id": "myth", "expeditionId": "myth", "participants": 2, "rarity": "Mythic",
          "grandAlliance": "Imperial", "_objs": [_obj("trait:Healer")]}
    pool, refus = ES.pool_eligible(op, kits, list(prog), prog, SEUILS)
    assert sorted(pool) == ["gros1", "gros2"]
    assert "rang insuffisant (12 < 17)" in refus["soigneur"]

    r = ES.resoudre_plateau([op], kits, list(prog), progression=prog, seuils=SEUILS)
    assert r["couvertes"] == 0, "le bonus est HORS D'ATTEINTE : aucun eligible ne soigne"
    assert r["pool_par_op"] == [2]
    # Contre-epreuve : sans le filtre, le meme plateau se croit couvert. C'est
    # exactement le faux positif qu'on fige ici.
    naif = ES.resoudre_plateau([op], kits, list(prog))
    assert naif["couvertes"] == 1


# ---------------------------------------------------------------------------
# REMPLISSAGE OBLIGATOIRE -- mesure au decompile de
#   ExpeditionDispatchScreen$$HandleOnDispatchTapped :
#       si SelectedCount() < ParticipantsRequired -> flyout, et RETOUR SANS ENVOI.
#   ExpeditionDispatchScreen$$UpdateDispatchButton garde le bouton grise dans le
#   meme cas.
#
# Le solveur minimisait les unites mobilisees, ce qui n'a de sens que si une place
# vide reste vide. Elle ne reste pas vide : elle EMPECHE le depart. Une operation
# consomme donc `participants` unites, et la disjonction se calcule la-dessus.
# ---------------------------------------------------------------------------

def test_remplissage_obligatoire_complete_jusqu_aux_places():
    kits = {u: _kit(u, faction="Custodes") for u in ("a", "b", "c", "d")}
    prog = _prog(a=(20, 5), b=(20, 5), c=(20, 5), d=(20, 5))
    op = {"id": "op", "expeditionId": "op", "participants": 3, "rarity": "Common",
          "grandAlliance": "Imperial", "_objs": [_obj("faction:Custodes")]}
    r = ES.resoudre_plateau([op], kits, list(prog), progression=prog, seuils=SEUILS)
    assert r["couvertes"] == 1
    p = r["plan"][0]
    # UN seul Custodes suffit au bonus, mais l'equipe DOIT compter 3 unites.
    assert len(p["ensemble"]) == 1
    assert len(p["equipe"]) == 3
    assert p["remplissage"] == 2
    assert r["unites_utiles"] == 1 and r["unites_mobilisees"] == 3


def test_operation_ECARTEE_si_le_pool_ne_remplit_pas():
    """Un pool trop etroit ne rend pas une equipe incomplete : il retire l'operation
    du plan, en la NOMMANT. Une equipe incomplete paraitrait partante et ne partirait
    pas -- exactement le silence qu'on refuse."""
    kits = {u: _kit(u, faction="Custodes") for u in ("a", "b")}
    prog = _prog(a=(20, 5), b=(20, 5))
    op = {"id": "trop-grande", "expeditionId": "trop-grande", "participants": 5,
          "rarity": "Common", "grandAlliance": "Imperial",
          "_objs": [_obj("faction:Custodes")]}
    r = ES.resoudre_plateau([op], kits, list(prog), progression=prog, seuils=SEUILS)
    assert r["couvertes"] == 0
    assert len(r["incompletes"]) == 1
    i = r["incompletes"][0]
    assert i["op"] == "trop-grande" and i["besoin"] == 5 and i["pool_libre"] == 2
    assert r["plan"][0]["ensemble"] is None


def test_le_remplissage_sert_les_pools_ETROITS_en_premier():
    """Deux operations, un pool commun etroit. Si la large sert d'abord, elle rafle
    les candidats et l'etroite tombe. L'ordre par taille de pool l'evite."""
    kits = {}
    kits.update({u: _kit(u, faction="Custodes", alliance="Chaos") for u in ("x", "y")})
    kits.update({u: _kit(u, faction="Custodes", alliance="Imperial")
                 for u in ("i1", "i2", "i3", "i4")})
    prog = _prog(**{u: (20, 5) for u in list(kits)})
    etroite = {"id": "etroite", "expeditionId": "etroite", "participants": 2,
               "rarity": "Common", "grandAlliance": "Chaos",
               "_objs": [_obj("faction:Custodes")]}
    large = {"id": "large", "expeditionId": "large", "participants": 3,
             "rarity": "Common", "grandAlliance": "Imperial",
             "_objs": [_obj("faction:Custodes")]}
    r = ES.resoudre_plateau([large, etroite], kits, list(prog),
                            progression=prog, seuils=SEUILS)
    assert r["couvertes"] == 2, r.get("incompletes")
    assert r["unites_mobilisees"] == 5


def test_deja_parties_retire_operations_et_unites():
    ops = [
        {"id": "partie", "expeditionId": "p", "status": 1,
         "units": ["custoTrajann", "ultraCalgar"]},
        {"id": "libre", "expeditionId": "l", "status": 0, "units": None},
    ]
    libres, prises = ES.deja_parties(ops)
    assert [o["id"] for o in libres] == ["libre"]
    assert prises == ["custoTrajann", "ultraCalgar"]
    # `status` absent se lit comme DISPONIBLE (un plateau ecrit a la main n'en porte pas).
    libres, prises = ES.deja_parties([{"id": "sans-status", "expeditionId": "s"}])
    assert len(libres) == 1 and prises == []


# ---------------------------------------------------------------------------
# LE MOTIF D'UNE OPERATION QUI NE PART PAS (`expedition_run.motif_non_partante`)
# ---------------------------------------------------------------------------
# Le 2026-08-12 le pilote affichait << 106 unites libres au roster >> pour une Mythic
# dont le pool eligible TOTAL valait 3 pour 5 places. Le compte etait JUSTE et la
# lecture FAUSSE : il portait sur le roster, pas sur le pool de l'operation, et se
# lisait << il y a du monde, c'est le bonus qui coince >> -- d'ou la conclusion
# << attendre le retour des parties >>. Attendre n'y changeait rien.
#
# Les trois causes appellent des gestes OPPOSES (monter des raretes / attendre /
# revoir le plan), donc chacune a son test, et chacun est monte pour ne tomber que
# sur SA branche : c'est ce qui distingue un garde d'un test decoratif.

def _op_mythic(participants):
    return {"id": "myth", "expeditionId": "myth", "participants": participants,
            "rarity": "Mythic", "grandAlliance": "Xenos", "_objs": []}


def _roster_mythic(n):
    """n unites Xenos, rarete Mythic, rang au-dessus du seuil -> toutes eligibles."""
    kits = {"x%d" % i: _kit("x%d" % i, faction="Necrons", alliance="Xenos")
            for i in range(n)}
    return kits, _prog(**{u: (20, 5) for u in kits})


def test_motif_pool_INSUFFISANT_EN_SOI_ne_renvoie_pas_a_l_attente():
    """3 eligibles pour 5 places, AUCUNE partie : attendre ne peut rien changer.

    C'est le cas reel du 2026-08-12 (`xenos_raid_m_03_10`)."""
    kits, prog = _roster_mythic(3)
    roster = list(prog)
    m = ER.motif_non_partante(_op_mythic(5), kits, roster, roster, prog, SEUILS)
    assert "INSUFFISANT en soi" in m, m
    assert "3 eligibles au total pour 5 places" in m, m
    # Et surtout : il ne doit PAS envoyer attendre.
    assert "attendre leur retour" not in m, m


def test_motif_unites_PARTIES_renvoie_a_l_attente():
    """5 eligibles au total mais 2 libres : la meme operation redeviendra faisable."""
    kits, prog = _roster_mythic(5)
    roster = list(prog)
    libres = roster[:2]
    m = ER.motif_non_partante(_op_mythic(5), kits, roster, libres, prog, SEUILS)
    assert "PARTIES" in m and "attendre leur retour" in m, m
    assert "5 eligibles dont 2 libres" in m, m
    assert "INSUFFISANT" not in m, m


def test_motif_pool_SUFFISANT_n_accuse_ni_la_rarete_ni_l_attente():
    """Assez d'unites libres eligibles : la cause est ailleurs (bonus / remplissage).

    Sans ce cas, une implementation qui accuserait TOUJOURS le pool passerait les
    deux tests precedents."""
    kits, prog = _roster_mythic(6)
    roster = list(prog)
    m = ER.motif_non_partante(_op_mythic(5), kits, roster, roster, prog, SEUILS)
    assert "bonus hors d'atteinte" in m, m
    assert "INSUFFISANT" not in m and "attendre" not in m, m


def test_motif_compte_le_pool_DE_L_OPERATION_et_jamais_le_roster():
    """Le defaut d'origine, fige : un roster PLETHORIQUE dont presque rien n'est
    eligible doit rendre << insuffisant >>, pas un grand nombre rassurant."""
    kits, prog = _roster_mythic(2)                       # 2 Xenos Mythic eligibles
    for i in range(100):                                 # + 100 Imperiaux inaptes
        u = "imp%d" % i
        kits[u] = _kit(u, faction="Ultramarines", alliance="Imperial")
        prog[u] = {"rank": 20, "rarity": 5, "rarete": ES.RARETES[5]}
    roster = list(prog)
    assert len(roster) == 102
    m = ER.motif_non_partante(_op_mythic(5), kits, roster, roster, prog, SEUILS)
    assert "2 eligibles au total pour 5 places" in m, m
    assert "102" not in m, m
