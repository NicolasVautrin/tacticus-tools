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


def test_les_deux_replis_legitimes_sont_dans_le_perimetre_de_letape4(arbres_reels):
    """Le vert de l'etape 4 porte bien sur les deux fonctions a risque, pas sur un ensemble vide.

    `is_adjacent` (repli sous `if neigh is None`) et `services.battle_query.are_tiles_adjacent`
    (geometrie APRES un bloc canal dont toutes les feuilles retournent) sont exactement les deux
    formes que le critere de flot doit accepter."""
    vus = {fn.name for _, fn in G._mirrors_avec_canal(arbres_reels)}
    assert vus == {"is_adjacent", "are_tiles_adjacent"}, vus


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
