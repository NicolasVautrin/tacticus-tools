"""#433-r4-r1-r4-r2-r1-r1 -- la garde du canal de voisinage cote-t-elle la CONSOMMATION, et pas
seulement la PRESENCE ?

Le vice : le canal est passe, l'appel est branche, mais sa valeur n'est jamais consommee -- ou elle
est recalculee en geometrie juste apres. Le call-site a l'allure d'un mirror branche et le
comportement d'avant le branchement. C'est la seule mutation restee VERTE a la contre-epreuve de
#611 (case-433r4r1r4r2r1 §4).

CE QUE CE FICHIER PROUVE, et dans les deux sens :

* les etapes 3 et 4 de `probe_433r4r1r4r2_neigh_channel_wired.py` ROUGISSENT sur chaque forme du
  vice -- sur des sources SYNTHETIQUES (une forme isolee par test) ET sur des MUTATIONS du vrai
  code (`engine/battle_query.py`, `engine/runner/components.py`, `engine/services/battle_query.py`),
  chacune verifiee MORDANTE avant d'etre cotee : sur une contre-epreuve, le VERT est le resultat
  suspect ;
* elles restent VERTES sur les replis LEGITIMES, qui sont le vrai risque ici -- une geometrie sous
  `if neigh is None`, une geometrie APRES un bloc canal dont toutes les feuilles retournent, une
  derivation consommee dans une closure, un homonyme de `services/` dont la valeur est jetee.

Aucun fichier n'est ECRIT : les mutations vivent en memoire (un cliquet n'ecrit jamais dans
`scripts/python/`, #455). 100 % OFFLINE.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import pytest

import probe_433r4r1r4r2_neigh_channel_wired as G

ROOT = G.ROOT
BQ = "scripts/python/engine/battle_query.py"
COMPOSANTS = "scripts/python/engine/runner/components.py"
SERVICES_BQ = "scripts/python/engine/services/battle_query.py"
DEGATS = "scripts/python/engine/runner/damage_model.py"
BASE_ABILITES = "scripts/python/engine/runner/abilities/base.py"
VOTANN = "scripts/python/engine/runner/abilities/votann.py"


# ------------------------------------------------------------------ montage

def _synthetique(**modules) -> dict:
    """{chemin FICTIF sous `engine/`: arbre} -- rien n'est ecrit sur disque.

    Le chemin doit vivre sous `scripts/python/engine` : c'est de la que `_paquet` derive le nom de
    paquet, donc la resolution d'import. Nommer un module `battle_query` le fait DEVENIR le foyer,
    ce qui permet d'exercer la resolution des noms nus."""
    return {ROOT / "scripts" / "python" / "engine" / (nom + ".py"): ast.parse(src)
            for nom, src in modules.items()}


def _mute(chemin_rel: str, *paires) -> dict:
    """Un arbre a UN fichier, mutation(s) appliquee(s) EN MEMOIRE.

    Chaque ancrage est verifie present et chaque substitution verifiee MORDANTE : un patch qui ne
    matche pas rendrait la contre-epreuve verte pour une raison qui n'a rien a voir avec le
    critere."""
    p = ROOT / chemin_rel
    src = p.read_text(encoding="utf-8")
    mute = src
    for (avant, apres) in paires:
        assert avant in mute, "ancrage introuvable dans %s (le code a bouge ?)" % chemin_rel
        avant_patch = mute
        mute = mute.replace(avant, apres, 1)
        assert mute != avant_patch, "la mutation n'a pas MORDU"
    return {p: ast.parse(mute)}


@pytest.fixture(scope="module")
def arbres_reels():
    """Le VRAI arbre du checkout courant, parse une seule fois."""
    fichiers = G._fichiers("scripts/python/engine")
    if fichiers is None:
        pytest.fail("INDISPONIBLE (montage, pas gisement) : git ls-files injouable")
    out = {}
    for p in fichiers:
        with open(p, encoding="utf-8", newline="") as fh:
            out[p] = ast.parse(fh.read())
    return out


def _noms(manquants) -> set:
    return {m[2] for m in manquants}


# ------------------------------------------------------------------ l'etat courant

def test_arbre_courant_vert_et_perimetres_non_vides(arbres_reels):
    """Les deux etapes neuves sont VERTES sur `origin/master`, sur un perimetre NON VIDE.

    Un zero de manquants ne vaut que si le balayage a vu quelque chose : c'est la meme regle que le
    garde-perimetre de l'etape 1."""
    m3, t3 = G.etape3(arbres_reels)
    m4, t4 = G.etape4(arbres_reels)
    assert t3 > 0, "etape 3 : aucune fonction ne touche le canal -- perimetre casse"
    assert t4 > 0, "etape 4 : aucun mirror declare avec canal -- perimetre casse"
    assert m3 == [], "derivations mortes : %r" % (m3,)
    assert m4 == [], "geometries non gardees : %r" % (m4,)


# --------------------------------------- #943-r6-r1 : l'etape 1 n'etait JOUEE PAR PERSONNE
# --------------------------------------- (un garde que rien ne convoque n'existe pas)

def test_etape1_arbre_courant_vert_et_perimetre_non_vide(arbres_reels):
    """L'INVARIANT DE COUPLE, sur l'arbre courant -- et c'est la premiere fois qu'un test le joue.

    ⚠ POURQUOI CE TEST EXISTE (#943-r6-r1). Les quatre etapes NEUVES (2/3/4/5) avaient chacune leur
    test de cablage ; l'ANCIENNE, non. Mesure du 2026-08-12 : ce fichier est le SEUL de la banque a
    importer le probe, et il appelait `etape2/3/4/5`, jamais `etape1` -- qui etait ROUGE sur
    `engine/runner/abilities/admec.py` (`are_entities_adjacent` : elevation fournie, voisinage
    omis), sans que rien de la banque ne le voie. Un garde que rien ne convoque est un garde qui
    n'existe pas.

    Le zero ne vaut que sur un perimetre NON VIDE : c'est la meme regle que pour les etapes 3 et 4,
    et `main()` la porte deja pour l'etape 1 (`t1 == 0` -> `ECART`)."""
    m1, t1 = G.etape1(arbres_reels)
    assert t1 > 0, "etape 1 : aucun call-site gate par l'elevation -- perimetre casse"
    assert m1 == [], (
        "call-site(s) a moitie branches (elevation fournie, voisinage MANQUANT) : %r" % (m1,))


def test_etape1_est_CABLEE_au_verdict(monkeypatch):
    """Le critere le plus juste ne vaut rien s'il n'est pas COMPTE (#430).

    `main()` comptait deja `etape1`, mais AUCUN test ne le prouvait -- et c'est bien la partie
    << personne ne le joue >> qui a laisse le rouge vivre, pas la partie << ce n'est pas compte >>."""
    monkeypatch.setattr(G, "etape1", lambda arbres: ([("f.py", 1, "is_adjacent")], 1))
    assert G.main() == 1


def test_les_replis_legitimes_sont_dans_le_perimetre_de_letape4(arbres_reels):
    """Le vert de l'etape 4 porte bien sur les fonctions a risque, pas sur un ensemble vide.

    `is_adjacent` (repli sous `if neigh is None`) et `services.battle_query.are_tiles_adjacent`
    (geometrie APRES un bloc canal dont toutes les feuilles retournent) sont exactement les deux
    formes que le critere de flot doit accepter.

    ⚠ LA TROISIEME EST ARRIVEE PAR L'ELARGISSEMENT DU CRITERE (#433-r4-r1-r4-r2-r1-r1-r1-r1,
    2026-08-15), PAS PAR UN CODE NEUF. `utilities/tile.py::apply_tile_attributes` ecrit
    `d <= 1` -- une forme que `_est_compare_geo` ne reconnaissait pas, l'appel de distance n'y
    etant pas l'operande gauche. Elle est LEGITIME et c'est precisement le patron que l'etape 4
    doit valider : elle SEPARE deja les deux substrats de la famille `AUnitEffectsUtility` --
    `adjacent` par `battle_query.is_adjacent` (`IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends` -> liste stockee +
    porte d'elevation), `surrounding1`/`ranged2` par la distance nue
    (`IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(1|2)` -> disque CUBE, sans liste ni porte).

    Ce test assertionne l'ensemble EXACT, et c'est voulu : le relacher en inclusion ferait taire
    l'arrivee d'un site a risque. Le prix est qu'il rougit quand le PERIMETRE bouge -- et c'est
    alors une invitation a LIRE le nouveau venu, pas a elargir la liste sans regarder."""
    vus = {fn.name for _, fn in G._mirrors_avec_canal(arbres_reels)}
    assert vus == {"is_adjacent", "are_tiles_adjacent", "apply_tile_attributes"}, vus


def test_le_VICE_REEL_de_orks_est_CORRIGE_et_la_liste_ELARGIE(arbres_reels):
    """SUITE du constat fige par #614, dans l'ordre qu'il prescrivait : corriger, PUIS elargir.

    Le vice etait `engine/runner/abilities/orks.py`, mirror de
    `RammingSpeedAbility$$GetDynamicInvalidTargetReason`, qui decidait `isAdjacent` par
    `hexgeo.distance == 1` la ou le natif appelle le slot 0x61 (`BattleQuery$$AreEntitiesAdjacent`
    -> `MovementUtil$$AreTilesAdjacent` -> `ConnectivityComponent$$IsNeighbour`).

    Ce que ce test verifie, et c'est plus fort que l'ancien : la fonction ne compare PLUS aucune
    distance a 1 -- elle sort donc du gisement des etapes 2 et 4 par la porte du haut (plus de
    geometrie du tout), pas parce qu'une garde l'excuse. Et l'elargissement de la liste aux trois
    natifs LUS ne rouvre rien."""
    for nat in ("AreEntitiesAdjacent", "AreUnitsInMelee", "GetFreeAdjacentTiles"):
        assert nat in G.NATIFS_LISTE_STOCKEE, "%s doit etre entre a la liste ARMEE" % nat
    orks = next(p for p in arbres_reels
                if p.as_posix().endswith("engine/runner/abilities/orks.py"))
    # `orks.py` porte DEUX `get_dynamic_invalid_target_reason` (Waaagh 1058 et RammingSpeed 1059) :
    # on designe par le NATIF cite, pas par le nom de methode.
    fns = [f for f in G._fonctions_racine(arbres_reels[orks])
           if f.name == "get_dynamic_invalid_target_reason"
           and "RammingSpeedAbility" in (ast.get_docstring(f) or "")]
    assert len(fns) == 1, "mirror de RammingSpeed introuvable ou duplique : %d" % len(fns)
    fn = fns[0]
    assert not G._compare_distance_a_un(fn), (
        "orks.get_dynamic_invalid_target_reason compare encore une distance a 1")
    assert "AreEntitiesAdjacent" in (ast.get_docstring(fn) or ""), (
        "le mirror doit CITER le natif qu'il porte -- sans quoi il sort du gisement pour la "
        "mauvaise raison")
    # HORS TOLERANCE : les deux selecteurs d'aura de #943-r4 sont un ecart ASSUME et NOMME
    # (cf. `GEOMETRIE_NUE_TOLEREE` et les quatre tests ci-dessous, qui re-mesurent sa
    # justification). Tout AUTRE mirror declare a geometrie nue rougit ici.
    assert G.etape2_hors_tolerance(arbres_reels)[0] == [], (
        "l'etape 2 rougit sur la liste elargie, HORS les sites nommement toleres")
    assert G.etape4(arbres_reels)[0] == [], "l'etape 4 rougit sur la liste elargie"


# ------------------------------------------------- #943-r4 : la TOLERANCE se MESURE, elle ne se
# ------------------------------------------------- declare pas (meme regle que l'etape 5)

def test_la_tolerance_ne_contient_aucune_entree_PERIMEE(arbres_reels):
    """Une entree qui ne designe plus rien est le vice que la liste pourrait cacher.

    Meme mode de defaillance que la SUSPENSION de l'etape 5 : une liste d'exceptions qui se
    perpetue apres la disparition de son objet dispense un site que plus personne n'a lu. On exige
    donc que CHAQUE cle corresponde a un site REELLEMENT vu par la mesure brute."""
    vus = {(rel, nom) for (rel, _ln, nom) in G.etape2(arbres_reels)[0]}
    perimees = sorted(k for k in G.GEOMETRIE_NUE_TOLEREE if k not in vus)
    assert not perimees, (
        "%d entree(s) de GEOMETRIE_NUE_TOLEREE ne designent plus aucun site du gisement : "
        "%r -- la tolerance est PERIMEE, retire-la" % (len(perimees), perimees))


def test_la_JUSTIFICATION_de_la_tolerance_se_re_mesure(arbres_reels):
    """LE FAIT QUI FONDE LA TOLERANCE, re-derive a chaque passe -- jamais cite de memoire.

    La tolerance ne dit pas << cette geometrie est correcte >> : elle dit << la reparer ICI SEULEMENT
    serait un fork >>, ce qui n'est vrai que TANT QUE d'autres sites portent la meme geometrie sans
    etre vus. C'est un fait du depot, et il peut cesser d'etre vrai -- le jour ou la famille est
    reparee au foyer, la tolerance n'a plus d'objet et doit tomber.

    ⚠ CE JOUR EST ARRIVE (#943-r7, 2026-08-15), ET CE TEST L'AVAIT PRESCRIT. Il a d'abord rougi
    pour la BONNE raison (ses trois temoins nommes -- `imperative.py`, `BigTargetAdjacent`,
    `GetStuckIn` -- venaient d'etre CABLES), et sa consigne (<< Si la famille a ete reparee, la
    tolerance n'a plus d'objet -- retire-la >>) a ete SUIVIE : `GEOMETRIE_NUE_TOLEREE` est VIDE, et
    l'`etape6` ne rend plus AUCUN site `LISTE_STOCKEE`.

    IL RESTE DONC UNE CONDITIONNELLE, PAS UN COMPTE : tant que la tolerance est vide il n'y a rien a
    justifier ; des qu'un site y entre, la FAMILLE doit etre demontrable a nouveau (au moins un
    autre site a geometrie nue MUET dont le natif enumere la liste stockee). Ecrire l'implication
    plutot qu'un seuil est ce qui empeche ce test de rougir chez l'auteur suivant pour un site qu'il
    n'a pas creuse -- la faute que `test_270r4r2r2_differes_offline` a payee trois fois."""
    muets, total = G.etape6(arbres_reels)
    assert total > 0, "perimetre casse : aucune geometrie nue vue par l'etape 6"
    # LE FAIT MESURE : plus aucune geometrie nue MUETTE ne mirrore un natif a liste stockee. Les 5
    # qui restent sont `GEOMETRIQUE` -- les cabler serait une REGRESSION, pas une reparation.
    classes = {G.GEOMETRIE_NUE_CLASSEE.get((rel, nom), (None,))[0]
               for (rel, _ln, nom) in muets}
    if not G.GEOMETRIE_NUE_TOLEREE:
        assert G.LISTE_STOCKEE not in classes, (
            "la tolerance est VIDE mais l'etape 6 voit encore une geometrie nue a substrat STOCKE : "
            "soit elle est cablable (fais-le), soit elle a besoin d'une tolerance NOMMEE -- %r"
            % sorted(rel_nom for rel_nom in ((r, n) for (r, _l, n) in muets)
                     if G.GEOMETRIE_NUE_CLASSEE.get(rel_nom, (None,))[0] == G.LISTE_STOCKEE))
        return
    # Tolerance NON vide -> la FAMILLE doit etre demontrable : au moins un AUTRE site porte la meme
    # geometrie sans etre vu par le critere `docstring`, sinon << reparer ici serait un fork >> est
    # faux et la tolerance n'est plus qu'une dispense.
    assert G.LISTE_STOCKEE in classes, (
        "%d entree(s) de tolerance, mais AUCUN site MUET a substrat stocke ne les accompagne : la "
        "famille qui fondait le << fork >> a disparu -- retire la tolerance et arme l'etape 2"
        % len(G.GEOMETRIE_NUE_TOLEREE))


def test_la_tolerance_ne_dispense_QUE_les_sites_quelle_NOMME():
    """CONTRE-EPREUVE 1 -- un mirror declare NEUF a geometrie nue rougit malgre la tolerance.

    Sans elle, `GEOMETRIE_NUE_TOLEREE` serait une porte ouverte : on verifierait que le cliquet est
    vert sans verifier qu'il peut encore rougir."""
    arbres = _synthetique(faux="""
import hexgeo


def adjacents(a, b):
    %s
    return hexgeo.distance(a, b) == 1
""" % _DOC)
    assert _noms(G.etape2_hors_tolerance(arbres)[0]) == {"adjacents"}, (
        "un mirror declare NEUF a geometrie nue ne rougit plus : la tolerance dispense plus que "
        "les deux sites qu'elle nomme")


def test_la_tolerance_MORD_quand_on_la_vide(monkeypatch):
    """CONTRE-EPREUVE 2 -- le filtre SOUSTRAIT vraiment, il ne recopie pas `etape2`.

    Si `etape2_hors_tolerance` se contentait de recopier `etape2`, le test principal serait vert
    par accident (il l'etait sur `master`... et rouge). Un site NOMME doit donc etre dispense, et
    reapparaitre des qu'on vide la liste.

    ⚠ LE MONTAGE EST DEVENU SYNTHETIQUE (#943-r7, 2026-08-15), ET C'EST LE MEME VICE CORRIGE UN CRAN
    PLUS HAUT. Ce test lisait le registre REEL : il figeait d'abord l'ensemble EXACT des deux sites
    (perime au premier rebase, #950), puis son cardinal (`>= 2`) -- et ce cardinal est tombe a ZERO
    le jour ou la famille a ete cablee, faisant rougir le test pour la DISPARITION de son gisement,
    pas pour une faute. Or ce qu'il garde n'est pas l'occupation du registre : c'est le MECANISME de
    soustraction. Un arbre synthetique le rend independant de l'etat du depot -- il mordra a
    l'identique que la tolerance reelle soit vide ou pleine."""
    arbres = _synthetique(faux="""
import hexgeo


def tolere_moi(a, b):
    %s
    return hexgeo.distance(a, b) == 1
""" % _DOC)
    chemin = "scripts/python/engine/faux.py"
    # (1) NOMME -> dispense. La cle est bien celle du site, sinon la soustraction ne porterait sur
    # rien et l'etape (2) serait verte par vacuite.
    monkeypatch.setattr(G, "GEOMETRIE_NUE_TOLEREE", {(chemin, "tolere_moi"): "#000"})
    assert G.etape2_hors_tolerance(arbres)[0] == [], (
        "un site NOMME par la tolerance n'est PAS dispense : la soustraction ne porte sur rien")
    # (2) VIDE -> il reapparait, EXACTEMENT lui.
    monkeypatch.setattr(G, "GEOMETRIE_NUE_TOLEREE", {})
    assert _noms(G.etape2_hors_tolerance(arbres)[0]) == {"tolere_moi"}, (
        "vider la tolerance ne fait pas reapparaitre le site qu'elle nommait")


# ------------------------------------- #943-r4 : le critere d'entree n'est plus un token de PROSE
# ------------------------------------- (etape 6 ARMEE : toute geometrie nue doit avoir ete LUE)

def test_etape6_toute_geometrie_nue_est_CLASSEE(arbres_reels):
    """LE FOND DE #943-r4 : plus aucun site n'est invisible parce qu'il ne NOMME pas son natif.

    Les etapes 2 et 4 n'entrent au gisement que si la docstring cite un `NATIFS_LISTE_STOCKEE` --
    une propriete de la PROSE. Mesure de la tranche precedente : 30 fonctions comparent une distance
    hex a 1, 2 vues, 2 avec canal, 26 MUETTES. L'etape 6 balaie par le CONTENU et EXIGE desormais
    une classification, donc une LECTURE du natif.

    Le zero ne vaut que sur un perimetre NON VIDE (meme regle que les etapes 1/3/4)."""
    m6nc, t6nc = G.etape6_non_classee(arbres_reels)
    assert t6nc > 0, "etape 6 : aucune geometrie nue muette vue -- perimetre casse"
    assert m6nc == [], (
        "%d site(s) a geometrie nue NON CLASSE(S) : %r -- lis le natif qu'il mirrore, puis "
        "classe-le (`GEOMETRIQUE` = le natif est lui-meme geometrique, `LISTE_STOCKEE` = le canal "
        "manque) ou cable le canal" % (len(m6nc), m6nc))


def test_etape6_est_CABLEE_au_verdict(monkeypatch):
    """Un rouge de l'etape 6 doit sortir par `main()` -- sinon la classification est decorative."""
    monkeypatch.setattr(G, "etape6_non_classee", lambda arbres, **kw: ([("f.py", 1, "f")], 1))
    assert G.main() == 1


def test_etape6_perimetre_VIDE_nest_pas_un_vert(monkeypatch):
    """CONTRE-EPREUVE du garde-perimetre : un balayage qui ne voit RIEN ne garde rien.

    Sans ce cran, casser le critere d'entree (une `_compare_distance_a_un` qui ne matche plus)
    rendrait l'etape 6 verte en ne visitant aucun site -- le mode de defaillance exact que
    `main()` previent deja pour les etapes 1 et 3."""
    monkeypatch.setattr(G, "etape6_non_classee", lambda arbres, **kw: ([], 0))
    assert G.main() == 1


def test_le_registre_de_classification_ne_contient_aucune_entree_PERIMEE(arbres_reels):
    """Meme mode de defaillance que la tolerance et que la suspension de l'etape 5.

    Une entree qui ne designe plus aucun site du gisement dispense un site que plus personne n'a lu.
    ⚠ La cle `(chemin, nom)` ne separe PAS les homonymes -- `hits.py` porte DEUX
    `create_aura_additional_hits_for_ally` -- donc une entree survit tant que l'UNE des deux vit.
    C'est nomme dans le registre plutot que corrige : une cle par LIGNE perimerait a chaque
    edition, le vice que la tolerance evite deja."""
    vus = {(rel, nom) for (rel, _ln, nom) in G.etape6(arbres_reels)[0]}
    perimees = sorted(k for k in G.GEOMETRIE_NUE_CLASSEE if k not in vus)
    assert not perimees, (
        "%d entree(s) de GEOMETRIE_NUE_CLASSEE ne designent plus aucun site a geometrie nue : "
        "%r -- retire-les" % (len(perimees), perimees))


def test_chaque_classification_CITE_un_substrat_LU_de_sa_classe(arbres_reels):
    """CE QUI REND LA CLASSIFICATION VERIFIABLE au lieu de declarative.

    Sans ce cran, ranger un site en `GEOMETRIQUE` couterait un trait de plume, et le registre
    serait la dispense qu'il existe pour interdire. On exige donc que le natif cite contienne un
    substrat LU de SA classe, et AUCUN de l'autre.

    Les deux jeux de substrats sont les corps effectivement decompiles (#943-r4) :
    `IterateSurroundingTiles` balaie le cube et n'a pas de porte d'elevation ; `AdjacentTiles` /
    `GetAdjacentUnits` / `GetAdjacentEnemies` / `IsNeighbourOf` / `AreEntitiesAdjacent` descendent
    tous sur `ConnectivityComponent+0x10`."""
    assert G.GEOMETRIE_NUE_CLASSEE, "registre vide : ce test ne garde plus rien"
    assert set(G.SUBSTRATS_LUS) == {G.GEOMETRIQUE, G.LISTE_STOCKEE}
    for (cle, valeur) in sorted(G.GEOMETRIE_NUE_CLASSEE.items()):
        assert isinstance(valeur, tuple) and len(valeur) == 2, (cle, valeur)
        classe, natif = valeur
        assert classe in G.SUBSTRATS_LUS, "classe inconnue pour %r : %r" % (cle, classe)
        autre = G.LISTE_STOCKEE if classe == G.GEOMETRIQUE else G.GEOMETRIQUE
        assert any(s in natif for s in G.SUBSTRATS_LUS[classe]), (
            "%r est classe %s mais ne cite AUCUN substrat lu de cette classe : %r"
            % (cle, classe, natif))
        assert not any(s in natif for s in G.SUBSTRATS_LUS[autre]), (
            "%r est classe %s mais cite un substrat de l'autre classe : %r" % (cle, classe, natif))


@pytest.mark.parametrize("classe,natif", [
    (G.GEOMETRIQUE, "DSLSelectors$$AdjacentFriends"),      # substrat de l'AUTRE classe
    (G.LISTE_STOCKEE, "DSLSelectors$$SurroundingTiles"),   # idem, en miroir
    (G.GEOMETRIQUE, "UnNatifQueNulNaLu$$Machin"),          # aucun substrat lu du tout
])
def test_une_classification_NON_ETAYEE_est_REFUSEE(monkeypatch, arbres_reels, classe, natif):
    """CONTRE-EPREUVE du test ci-dessus, DANS LES DEUX SENS.

    Un test qui verifie seulement que le registre courant passe ne prouve pas qu'il pourrait
    echouer -- c'est le faux vert que l'etape 5 a paye (#943)."""
    faux = dict(G.GEOMETRIE_NUE_CLASSEE)
    faux[("scripts/python/engine/battle_query.py", "is_target_tile_obscured")] = (classe, natif)
    monkeypatch.setattr(G, "GEOMETRIE_NUE_CLASSEE", faux)
    with pytest.raises(AssertionError):
        test_chaque_classification_CITE_un_substrat_LU_de_sa_classe(arbres_reels)


def test_le_registre_ne_dispense_QUE_les_sites_quil_NOMME():
    """CONTRE-EPREUVE 1 de l'etape 6 -- une geometrie nue NEUVE rougit, docstring ou pas.

    C'est exactement ce que le critere de PROSE ne savait pas faire : cette fonction-ci ne cite
    AUCUN natif, donc les etapes 2 et 4 ne la voient pas -- et pourtant elle decide une adjacence
    a la couronne hex."""
    arbres = _synthetique(faux="""
import hexgeo


def adjacents_muet(a, b):
    \"\"\"Aucun natif declare -- invisible aux etapes 2 et 4, par construction.\"\"\"
    return hexgeo.distance(a, b) == 1
""")
    assert G.etape2(arbres) == ([], 0), "l'etape 2 ne doit PAS voir un site muet"
    assert _noms(G.etape6_non_classee(arbres)[0]) == {"adjacents_muet"}, (
        "une geometrie nue NEUVE et muette ne rougit plus : le critere est redevenu de la PROSE")


def test_le_registre_MORD_quand_on_le_vide(arbres_reels, monkeypatch):
    """CONTRE-EPREUVE 2 -- le vert d'aujourd'hui vient du REGISTRE, pas d'un gisement disparu.

    Si `etape6_non_classee` se contentait de recopier `etape6`, le test principal serait vert par
    accident. En vidant le registre, TOUS les muets doivent reapparaitre."""
    muets = {(rel, nom) for (rel, _ln, nom) in G.etape6(arbres_reels)[0]}
    monkeypatch.setattr(G, "GEOMETRIE_NUE_CLASSEE", {})
    reapparus = {(rel, nom) for (rel, _ln, nom) in G.etape6_non_classee(arbres_reels)[0]}
    assert reapparus == muets and len(muets) >= 3, (len(muets), sorted(muets)[:5])


def test_les_deux_sites_REPARES_ont_quitte_le_gisement_par_le_HAUT(arbres_reels):
    """Les deux reparations de #943-r4 sortent du gisement parce qu'elles CONSOMMENT le canal.

    `base.py::_fighting_retreat_sets_flags` (`GetAdjacentEnemies` slot 125 ->
    `GetUnitsOnTiles(IterateAdjacentTiles(...))`) et
    `votann.py::_ancestral_fortune_attack_target` (`DSLSelectors$$AdjacentEnemies` ->
    `AdjacentTiles`) etaient MUETS et a geometrie nue. Ce test verifie qu'ils n'y sont plus par la
    porte du HAUT -- plus aucune comparaison de distance a 1 -- et non parce qu'une entree de
    registre les excuse : ils ne sont volontairement PAS au registre.

    L'etape 3 les voit desormais (elles touchent le canal), donc leur derivation est gardee
    CONSOMMEE par `test_arbre_courant_vert_et_perimetres_non_vides`."""
    for (chemin, nom) in ((BASE_ABILITES, "_fighting_retreat_sets_flags"),
                          (VOTANN, "_ancestral_fortune_attack_target")):
        p = next(x for x in arbres_reels if x.as_posix().endswith(chemin.split("engine/", 1)[1]))
        fns = [f for f in G._fonctions_racine(arbres_reels[p]) if f.name == nom]
        assert len(fns) == 1, "%s introuvable ou duplique : %d" % (nom, len(fns))
        assert not G._compare_distance_a_un(fns[0]), (
            "%s compare encore une distance a 1" % nom)
        assert G._noms_du_corps(fns[0]) & set(G.ACCES_CANAL), (
            "%s ne touche pas le canal de voisinage" % nom)
        assert (chemin, nom) not in G.GEOMETRIE_NUE_CLASSEE, (
            "%s est REPARE : il n'a rien a faire au registre de classification" % nom)


def test_les_natifs_SUSPENDUS_le_sont_pour_une_raison_qui_se_MESURE(arbres_reels):
    """Le registre suspendu n'est pas une echappatoire : sa justification se re-mesure.

    Un natif LU comme substrat stocke peut y vivre TANT QUE l'armer ferait rougir un vice ENCORE
    OUVERT ; des que ce n'est plus vrai, la suspension EST le vice, et l'etape 5 le dit.

    ⚠ LE REGISTRE EST VIDE DEPUIS #943-r7 (2026-08-15), ET << VIDE >> N'EST PAS << VACANT >>. Le
    `assert NATIFS_LISTE_STOCKEE_SUSPENDUS` qui vivait ici exigeait qu'il reste au moins une
    suspension -- c'est-a-dire qu'il exigeait un VICE, exactement l'inverse de ce que l'etape 5
    prescrit. Les quatre natifs qui y ont vecu en sont sortis PAR LE HAUT, chacun a la demande de
    l'etape 5 une fois son dernier foyer cable. Ce que ce test garde desormais :
      * la boucle de justification, INCHANGEE, pour tout natif qui y entrerait a nouveau ;
      * et, a sa place, le cran qui empeche << vide >> de vouloir dire << oublie >> : les quatre
        natifs sortis doivent etre ARMES. Un natif LU qui ne serait NI arme NI suspendu serait en
        SILENCE TOTAL -- le mode de defaillance que #983 a paye sur `AdjacentEnemies`.
    La capacite du mecanisme a MORDRE reste gardee par
    `test_etape5_ROUGIT_sur_une_suspension_perimee`, qui suspend un nom synthetique."""
    for nat in ("AdjacentTiles", "AdjacentUnits", "AdjacentFriends", "AdjacentEnemies"):
        assert nat in G.NATIFS_LISTE_STOCKEE, (
            "%s a quitte le registre SUSPENDU sans entrer a la liste ARMEE : il serait en SILENCE "
            "TOTAL, ni vu de l'etape 2/4 ni re-mesure par l'etape 5" % nat)
        assert nat not in G.NATIFS_LISTE_STOCKEE_SUSPENDUS, (
            "%s est a la fois ARME et SUSPENDU : l'etape 5 mesurerait un delta toujours vide" % nat)
    base = G.NATIFS_LISTE_STOCKEE
    for nat in sorted(G.NATIFS_LISTE_STOCKEE_SUSPENDUS):
        try:
            G.NATIFS_LISTE_STOCKEE = base + (nat,)
            rouges = G.etape2(arbres_reels)[0] + G.etape4(arbres_reels)[0]
        finally:
            G.NATIFS_LISTE_STOCKEE = base
        assert rouges, ("%s ne fait plus rougir personne : sa suspension est PERIMEE, l'etape 5 "
                        "doit le dire" % nat)
    assert G.etape5(arbres_reels)[0] == [], "etape 5 rouge sur l'arbre courant"


def test_etape5_ROUGIT_sur_une_suspension_perimee(arbres_reels, monkeypatch):
    """CONTRE-EPREUVE de l'etape 5 : un natif suspendu qui ne fait rougir personne EST le vice.

    On suspend un nom qui n'apparait dans aucune docstring -- l'armer ne peut rien faire rougir,
    donc la suspension est sans objet, donc PERIMEE."""
    monkeypatch.setattr(G, "NATIFS_LISTE_STOCKEE_SUSPENDUS",
                        {"NatifQuiNexistePas": "#000"})
    m5, t5 = G.etape5(arbres_reels)
    assert t5 == 1
    assert [x[0] for x in m5] == ["NatifQuiNexistePas"]


def test_etape5_est_CABLEE_au_verdict(monkeypatch):
    """Le critere le plus juste ne vaut rien s'il n'est pas COMPTE (#430).

    `**kw` : `main()` passe a l'etape 5 la reference deja calculee (parametre de COUT)."""
    monkeypatch.setattr(G, "etape5", lambda arbres, **kw: ([("X", "#000")], 1))
    assert G.main() == 1


def test_indisponible_porte_son_nom(monkeypatch):
    """Une panne de `git` n'est pas un rouge de gisement : rc 99, distinct (#471)."""
    def _explose(*a, **k):
        raise OSError("git absent")
    monkeypatch.setattr(subprocess, "run", _explose)
    assert G.main() == 99


@pytest.mark.parametrize("etape", ["etape3", "etape4"])
def test_chaque_etape_neuve_est_CABLEE_au_verdict(monkeypatch, etape):
    """Un rouge d'etape doit sortir par `main()`.

    Le critere le plus juste ne vaut rien s'il n'est pas COMPTE : `probe_181` a rendu `0`
    inconditionnellement pendant que le `CLAUDE.md` prescrivait de « le faire passer » (#430)."""
    monkeypatch.setattr(G, etape, lambda arbres: ([("f.py", 1, "f", "x")], 1)
                        if etape == "etape3" else ([("f.py", 1, "f")], 1))
    assert G.main() == 1


# ------------------------------------------------------------------ etape 3, formes isolees

_DOC = '"""`IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` -- mirror."""'


def test_e3_forme_a_store_teinte_jamais_relu():
    """(a) `neigh = neigh_map(ctx)` puis plus rien : la valeur du canal est calculee et jetee."""
    arbres = _synthetique(faux="""
import hexgeo
from .battle_query import neigh_map


def adjacents(ctx, a, b):
    %s
    neigh = neigh_map(ctx)
    return hexgeo.distance(a, b) == 1
""" % _DOC)
    m3, t3 = G.etape3(arbres)
    assert t3 == 1
    assert _noms(m3) == {"adjacents"}
    assert "jamais relue" in m3[0][3]


def test_e3_forme_a_derivation_en_chaine():
    """Le teint se propage : `x = neigh_map(ctx)` puis `y = x.get(t)` -- si `y` meurt, c'est mort."""
    arbres = _synthetique(faux="""
from .battle_query import neigh_map


def adjacents(ctx, t):
    %s
    x = neigh_map(ctx)
    y = x.get(t)
    return len(x)
""" % _DOC)
    m3, _ = G.etape3(arbres)
    assert [m[3] for m in m3] == ["derivation `y` jamais relue"]


def test_e3_forme_b_appel_pur_du_foyer_dont_la_valeur_est_jetee():
    """(b) un predicat PUR du foyer appele en statement nu ne branche rien -- resolution comprise.

    Le module s'appelle `battle_query`, donc il EST le foyer : le nom NU y resout."""
    arbres = _synthetique(battle_query="""
import hexgeo


def is_adjacent(tile, pos, elev_by_pos=None, neigh_by_pos=None):
    return neigh_by_pos is None or (elev_by_pos, pos, tile) is None


def compte(tile, positions, elev_by_pos=None, neigh_by_pos=None):
    %s
    is_adjacent(tile, positions, elev_by_pos, neigh_by_pos)
    return sum(1 for p in positions if hexgeo.distance(tile, p) == 1)
""" % _DOC)
    m3, _ = G.etape3(arbres)
    assert _noms(m3) == {"compte"}
    assert "valeur est jetee" in m3[0][3]


def test_e3_forme_c_parametre_du_canal_jamais_lu():
    """(c) un parametre accepte mais non lu se refait passer un jour pour un canal actif."""
    arbres = _synthetique(faux="""
import hexgeo


def adjacents(a, b, elev_by_pos=None, neigh_by_pos=None):
    %s
    return hexgeo.distance(a, b) == 1
""" % _DOC)
    m3, _ = G.etape3(arbres)
    assert [m[3] for m in m3] == ["parametre `neigh_by_pos` jamais lu"]


# ------------------------------------------------------------------ etape 3, anti-faux-positifs

def test_e3_derivation_consommee_dans_une_closure_reste_verte():
    """`update_charging` derive le canal PUIS le lit dans `_adjacent_ids` : la portee est la
    fonction RACINE, closures comprises."""
    arbres = _synthetique(faux="""
from .battle_query import is_adjacent
from .entities.pathfinding.board import adjacent_neigh_by_pos


def maj(state, board, pos):
    %s
    neigh_by_pos = adjacent_neigh_by_pos(board)

    def _adj(p):
        return is_adjacent(p, pos, None, neigh_by_pos)
    return _adj(pos)
""" % _DOC)
    m3, t3 = G.etape3(arbres)
    assert t3 == 1 and m3 == []


def test_e3_valeur_jetee_explicitement_par_underscore_reste_verte():
    """`_ = ...` DIT qu'on jette : c'est la seule cible exclue, et elle se lit."""
    arbres = _synthetique(faux="""
from .battle_query import neigh_map


def sonde(ctx):
    %s
    _ = neigh_map(ctx)
    return 0
""" % _DOC)
    m3, _ = G.etape3(arbres)
    assert m3 == []


def test_e3_mutateur_homonyme_jete_en_statement_nu_reste_vert():
    """Un `update_charging(...)` en statement nu est LEGITIME : c'est un mutateur ECS, pas un
    predicat du foyer. Seules les fonctions PURES de `engine.battle_query` sont cotees."""
    arbres = _synthetique(faux="""
from .runner.components import update_charging
from .battle_query import neigh_map


def joue(state, ctx, uid, a, b):
    %s
    neigh_by_pos = neigh_map(ctx)
    update_charging(state, uid, a, b)
    return neigh_by_pos
""" % _DOC)
    m3, _ = G.etape3(arbres)
    assert m3 == []


def test_e3_deballage_dont_UNE_cible_est_relue_reste_vert():
    """LE FAUX POSITIF MESURE (#824, `walk_pathfinder.get_path_node_counts_by_pos`) : `best, _came
    = _dijkstra_by_pos(origin, neigh_by_pos, ...)` consomme `best`, donc le canal a MORDU -- coter
    `_came` seul faisait ROUGIR `master` sur `test_arbre_courant_vert_et_perimetres_non_vides`
    pour une derivation qui n'a rien de morte.

    Le critere se lit au niveau du STATEMENT : la valeur d'une affectation est consommee des
    qu'UNE de ses cibles teintees est relue."""
    arbres = _synthetique(faux="""
from .battle_query import neigh_map


def compte(ctx, origin):
    %s
    neigh_by_pos = neigh_map(ctx)
    best, _came = _dijkstra(origin, neigh_by_pos)
    return best
""" % _DOC)
    m3, t3 = G.etape3(arbres)
    assert t3 == 1 and m3 == [], m3


def test_e3_deballage_INTEGRALEMENT_jete_reste_ROUGE():
    """LA CONTRE-EPREUVE du test ci-dessus, et elle est indispensable : relacher le deballage ne
    doit PAS ouvrir une porte. Quand AUCUNE cible teintee n'est relue, la valeur est bien perdue --
    les DEUX cibles sont cotees."""
    arbres = _synthetique(faux="""
from .battle_query import neigh_map


def compte(ctx, origin):
    %s
    neigh_by_pos = neigh_map(ctx)
    best, came = _dijkstra(origin, neigh_by_pos)
    return 0
""" % _DOC)
    m3, _ = G.etape3(arbres)
    assert _noms(m3) == {"compte"}, m3
    assert sorted(m[3] for m in m3) == ["derivation `best` jamais relue",
                                        "derivation `came` jamais relue"], m3


def test_e3_homonyme_de_services_jete_reste_vert():
    """`services.movement_query.is_adjacent(board, a, b)` est un HOMONYME : son 3e parametre n'est
    pas le canal, et la detection RESOUT l'import (#433-r4-r1-r4-r2-r1)."""
    arbres = _synthetique(faux="""
from .services.movement_query import is_adjacent
from .battle_query import neigh_map


def joue(board, ctx, a, b):
    %s
    neigh_by_pos = neigh_map(ctx)
    is_adjacent(board, a, b)
    return neigh_by_pos
""" % _DOC)
    m3, _ = G.etape3(arbres)
    assert m3 == []


# ------------------------------------------------------------------ etape 4, formes isolees

def test_e4_garde_inerte_puis_geometrie():
    """`if neigh_by_pos is None: pass` teste le canal sans rien en faire : la geometrie decide sur
    les DEUX chemins, dont celui ou le canal repondait. C'est la fusion en ET qui le voit."""
    arbres = _synthetique(faux="""
import hexgeo


def adjacents(a, b, neigh_by_pos=None):
    %s
    if neigh_by_pos is None:
        pass
    return hexgeo.distance(a, b) == 1
""" % _DOC)
    m4, t4 = G.etape4(arbres)
    assert t4 == 1
    assert _noms(m4) == {"adjacents"}


def test_e4_canal_consulte_puis_ignore():
    """Le canal est lu, sa reponse est calculee -- et la geometrie tranche quand meme."""
    arbres = _synthetique(faux="""
import hexgeo


def adjacents(a, b, neigh_by_pos=None):
    %s
    neigh = None if neigh_by_pos is None else neigh_by_pos.get(a)
    if neigh is not None and b in neigh:
        pass
    return hexgeo.distance(a, b) == 1
""" % _DOC)
    m4, _ = G.etape4(arbres)
    assert _noms(m4) == {"adjacents"}


def test_e4_geometrie_avant_la_consultation_du_canal():
    """Tester le canal APRES coup ne rattrape rien : la geometrie a deja tranche."""
    arbres = _synthetique(faux="""
import hexgeo


def adjacents(a, b, neigh_by_pos=None):
    %s
    if hexgeo.distance(a, b) != 1:
        return False
    neigh = None if neigh_by_pos is None else neigh_by_pos.get(a)
    return neigh is None or b in neigh
""" % _DOC)
    m4, _ = G.etape4(arbres)
    assert _noms(m4) == {"adjacents"}


def test_e4_geometrie_dans_une_closure_definie_hors_garde():
    """La forme de #611 : la geometrie est enfouie dans une closure, la derivation reste au-dessus.
    Le flot de la closure est celui de son point de DEFINITION."""
    arbres = _synthetique(faux="""
import hexgeo


def nouveaux(a, b, positions, neigh_by_pos=None):
    %s
    neigh = neigh_by_pos

    def _adj(p):
        return {i for i, q in positions.items() if hexgeo.distance(p, q) == 1}
    return _adj(a) - _adj(b)
""" % _DOC)
    m4, _ = G.etape4(arbres)
    m3, _ = G.etape3(arbres)
    assert _noms(m4) == {"nouveaux"}, "etape 4 aveugle a la geometrie de la closure"
    assert _noms(m3) == {"nouveaux"}, "etape 3 aveugle a la derivation morte"


def test_e4_bloc_canal_qui_ne_termine_plus():
    """La MEME fonction, au `return` pres : quand le bloc canal laisse TOMBER dans la geometrie,
    celle-ci n'est plus un repli. C'est la contre-epreuve de la regle de terminaison."""
    gabarit = """
import hexgeo
from .entities.pathfinding.board import connectivity_neighbours


def adjacents(a_pos, t_pos, board=None):
    %s
    if board is not None:
        a_tile = board.id_at(a_pos)
        t_tile = board.id_at(t_pos)
        if a_tile is not None and t_tile is not None:
            conn = connectivity_neighbours(board, a_tile)
            %s
    return hexgeo.distance(a_pos, t_pos) == 1
"""
    vert = _synthetique(faux=gabarit % (_DOC, "return t_tile in conn"))
    rouge = _synthetique(faux=gabarit % (_DOC, "ok = t_tile in conn"))
    assert G.etape4(vert)[0] == [], "faux positif sur le bloc a echappement complet"
    assert _noms(G.etape4(rouge)[0]) == {"adjacents"}


def test_e4_repli_garde_reste_vert():
    """La forme d'`is_adjacent` : la geometrie sous `if neigh is None`, donc sur le seul chemin ou
    le canal n'a pas repondu."""
    arbres = _synthetique(faux="""
import hexgeo


def adjacents(a, b, neigh_by_pos=None):
    %s
    neigh = None if neigh_by_pos is None else neigh_by_pos.get(a)
    if neigh is None:
        if hexgeo.distance(a, b) != 1:
            return False
    elif b not in neigh:
        return False
    return True
""" % _DOC)
    assert G.etape4(arbres)[0] == []


def test_e4_early_return_du_chemin_canal_reste_vert():
    """`if <canal>: return <canal>` puis geometrie : la geometrie n'est atteinte que sans canal."""
    arbres = _synthetique(faux="""
import hexgeo


def adjacents(a, b, neigh_by_pos=None):
    %s
    if neigh_by_pos is not None:
        return b in neigh_by_pos.get(a, ())
    return hexgeo.distance(a, b) == 1
""" % _DOC)
    assert G.etape4(arbres)[0] == []


def test_e4_sans_natif_declare_reste_hors_gisement():
    """Le critere n'est pas « toute geometrie » : il faut avoir DECLARE mirrorer le substrat
    stocke. Sans citation, la fonction sort du verdict et entre a l'INVENTAIRE."""
    src = """
import hexgeo
from .battle_query import neigh_map


def candidats(ctx, a, b):
    \"\"\"Sans natif a liste stockee dans la docstring.\"\"\"
    neigh = neigh_map(ctx)
    return hexgeo.distance(a, b) == 1 and neigh is not None
"""
    arbres = _synthetique(faux=src)
    assert G.etape4(arbres) == ([], 0)
    assert _noms(G.inventaire(arbres)) == {"candidats"}


# ------------------------------------------------------------------ mutations du VRAI code

def test_mutation_newly_adjacent_ids_geometrie_et_derivation_morte():
    """La mutation restee VERTE a la contre-epreuve de #611, sur le vrai `battle_query.py`."""
    arbres = _mute(
        BQ,
        ("                if q is not None and is_adjacent(tuple(p), tuple(q), elev_by_pos,"
         " neigh_by_pos)}",
         "                if q is not None and hexgeo.distance(tuple(p), tuple(q)) == 1}"),
        ("    def _adj(p):", "    neigh = neigh_by_pos\n\n    def _adj(p):"))
    assert "newly_adjacent_ids" in _noms(G.etape3(arbres)[0])
    assert "newly_adjacent_ids" in _noms(G.etape4(arbres)[0])


def test_mutation_update_charging_geometrie_nue_canaux_derives():
    """Le jumeau ECS : les derivations restent en tete, la decision repasse en geometrie.

    Seule la derivation de VOISINAGE est cotee -- `elev_by_pos = elevations_by_pos(board)` n'est pas
    teinte, parce que le canal garde ici est l'ENUMERATION, pas la porte d'elevation (celle-la est
    l'objet de l'etape 1)."""
    arbres = _mute(
        COMPOSANTS,
        ("            if is_adjacent(tuple(pos), (opc.col, opc.row), elev_by_pos, neigh_by_pos):",
         "            if hexgeo.distance(tuple(pos), (opc.col, opc.row)) == 1:"))
    m3 = G.etape3(arbres)[0]
    assert {(m[2], m[3]) for m in m3} == {("update_charging",
                                           "derivation `neigh_by_pos` jamais relue")}
    assert "update_charging" in _noms(G.etape4(arbres)[0])


def test_mutation_is_adjacent_garde_inerte():
    """Le repli d'`is_adjacent` reduit a une garde qui ne garde rien."""
    arbres = _mute(
        BQ,
        ("    neigh = None if neigh_by_pos is None else neigh_by_pos.get(t)",
         "    if neigh_by_pos is None:\n        pass\n    neigh = None"))
    assert "is_adjacent" in _noms(G.etape4(arbres)[0])


def test_mutation_are_tiles_adjacent_court_circuit_geometrique():
    """Une geometrie glissee DANS le bloc ou le canal est disponible (`services/battle_query.py`)."""
    arbres = _mute(
        SERVICES_BQ,
        ("            conn = connectivity_neighbours(board, a_tile)",
         "            if hexgeo.distance(a_pos, t_pos) == 1:\n                return True\n"
         "            conn = connectivity_neighbours(board, a_tile)"))
    assert "are_tiles_adjacent" in _noms(G.etape4(arbres)[0])


def test_mutation_is_charging_parametre_inerte():
    """Couper la propagation rend le parametre `neigh_by_pos` d'`is_charging` INERTE."""
    arbres = _mute(
        BQ,
        ("    if not are_entities_adjacent(caster_pos, target_pos, elev_by_pos,\n"
         "                                 neigh_by_pos):",
         "    if not are_entities_adjacent(caster_pos, target_pos, elev_by_pos):"))
    m3 = G.etape3(arbres)[0]
    assert ("is_charging", "parametre `neigh_by_pos` jamais lu") in {(m[2], m[3]) for m in m3}


def test_mutation_pont_ecs_derivation_sortie_puis_oubliee():
    """Un QUATRIEME fichier, hors `battle_query.py` : le pont COMBAT d'`IsCharging`.

    La derivation est extraite dans une variable -- et l'appel ne la prend plus. C'est la forme la
    plus discrete du vice : le `adjacent_neigh_by_pos(board)` est toujours la, bien visible."""
    arbres = _mute(
        DEGATS,
        ("    return _bq_is_charging(_pos(caster_id), _pos(target_id), target_id,\n"
         "                           charged_unit_ids(state, int(caster_id)),\n"
         "                           elevations_by_pos(board), adjacent_neigh_by_pos(board))",
         "    neigh_by_pos = adjacent_neigh_by_pos(board)\n"
         "    return _bq_is_charging(_pos(caster_id), _pos(target_id), target_id,\n"
         "                           charged_unit_ids(state, int(caster_id)),\n"
         "                           elevations_by_pos(board))"))
    m3 = G.etape3(arbres)[0]
    assert ("battle_query_is_charging", "derivation `neigh_by_pos` jamais relue") in \
        {(m[2], m[3]) for m in m3}


def test_mutation_count_adjacent_appel_jete():
    """Le predicat du foyer appele pour rien, la geometrie decidant a cote."""
    arbres = _mute(
        BQ,
        ("    return sum(1 for p in (positions or [])\n"
         "               if is_adjacent(tile, p, elev_by_pos, neigh_by_pos))",
         "    is_adjacent(tile, positions, elev_by_pos, neigh_by_pos)\n"
         "    return sum(1 for p in (positions or [])\n"
         "               if hexgeo.distance(tile, p) == 1)"))
    m3 = G.etape3(arbres)[0]
    assert ("count_adjacent", "appel `is_adjacent` dont la valeur est jetee") in \
        {(m[2], m[3]) for m in m3}
