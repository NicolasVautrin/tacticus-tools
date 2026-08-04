"""#433-r4-r1-r4-r2 -- `is_adjacent` enumere la liste STOCKEE, plus la couronne hex.

Ce que cette garde verrouille
-----------------------------
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` est une
ENUMERATION suivie d'une PORTE, dans cet ordre :

    elev0 = tile.TileComponent.Elevation;
    foreach (nid in tile.ConnectivityComponent.Neighbours) {      // <- la liste STOCKEE
        t = state.GetTileEntity(nid);  if (t == null) continue;
        <filtres terrain optionnels>
        if (Math.Abs(elev0 - t.Elevation) < 2) yield return t;    // <- la porte
    }

Le port portait le SECOND etage (#433-r4-r1-r4) mais recalculait le premier en couronne hex. La
liste stockee est PLUS PETITE que la couronne : `InitializeConnectivityOperation$$Execute` n'y met
une arete que si `TileComponent$$HasEdge` la porte des DEUX cotes (`e` chez l'une,
`(e + 3) % 6` chez l'autre -- le modulo 6 est fixe par
`IdunBattle.Operations.AddTileOperation$$RotateTileEdges`). Les tuiles `Bridge` sont exactement ce
que ce critere refuse et que la couronne inventait.

MESURE (`probe_433r4r1r4r2_is_adjacent_substrat_live.py`, 4 boards) : ecart **4** aretes dirigees
sur `C1_74`, **38** sur `C3_14`, **0** sur `MC1_67`/`C6_25`, et **0 arete restrictive** partout --
l'ecart etait donc strictement PERMISSIF. Le critere natif etant symetrique par construction, les
trois vues mesurees n'ont **aucune** arete one-way : le risque « exposer des aretes a sens unique »
est REFUTE, pas contourne.

Les crans couvrent : le canal et son TRI-ETAT, l'ordre des deux etages, le repli geometrique
NOMME, la derivation par `DslContext` / `Scene`, `neigh_map` sur les trois formes de contexte, et
la propagation aux trois derivees. 100 % OFFLINE.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine import battle_query as bq                                            # noqa: E402
from engine.dsl.base import DslContext                                           # noqa: E402
from engine.entities.pathfinding.board import (Board,                            # noqa: E402
                                               adjacent_neigh_by_pos)

COLS, ROWS = 5, 5


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board(elev=None, coupe=(), with_neighbours: bool = True) -> Board:
    """Board 5x5 plein. `coupe` = arêtes NON DIRIGEES a retirer du champ `neighbours` des DEUX
    cotes -- le patron `Bridge` mesure live (le `ConnectivityComponent` ne relie pas le pont a son
    voisin de niveau, alors que la couronne hex, elle, les voit adjacents).

    `with_neighbours=False` retire le CHAMP : c'est l'etat « canal absent » (board bati a la main,
    `boardGraph` anterieur au capteur), a ne PAS confondre avec une liste vide."""
    elev = elev or {}
    coupees = set()
    for (a, b) in coupe:
        coupees.add((a, b))
        coupees.add((b, a))
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            t = {"id": _tid(col, row), "col": col, "row": row, "walkable": True,
                 "isWall": False, "elevation": int(elev.get((col, row), 0))}
            if with_neighbours:
                t["neighbours"] = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                                   if 0 <= c < COLS and 0 <= r < ROWS
                                   and ((col, row), (c, r)) not in coupees]
            tiles.append(t)
    return Board(tiles)


# --- le patron mesure : une arete de la couronne que la liste stockee NE PORTE PAS -------------
A = (2, 2)
B = hexgeo.neighbors(2, 2)[0]          # un voisin geometrique de A, quelconque mais reel
AUTRE = hexgeo.neighbors(2, 2)[1]


def test_le_montage_est_bien_discriminant():
    """Sans ce cran, tous les autres pourraient etre verts pour la mauvaise raison : il faut que
    `B` soit VRAIMENT dans la couronne de `A` (sinon l'ecart mesure ne serait pas un ecart)."""
    assert hexgeo.distance(A, B) == 1
    assert B != AUTRE and hexgeo.distance(A, AUTRE) == 1


def test_arete_absente_de_la_liste_stockee_n_est_PAS_adjacente():
    """Le cran central : la couronne dit VRAI, la liste stockee dit FAUX -> le natif dit FAUX."""
    bd = _board(coupe=[(A, B)])
    neigh = adjacent_neigh_by_pos(bd)
    assert bq.is_adjacent(A, B, bd.elev_by_pos(), neigh) is False
    assert bq.is_adjacent(B, A, bd.elev_by_pos(), neigh) is False      # et dans les DEUX sens
    # temoin : une arete que la liste PORTE reste adjacente
    assert bq.is_adjacent(A, AUTRE, bd.elev_by_pos(), neigh) is True


def test_sans_le_canal_le_port_reste_GEOMETRIQUE_et_donc_permissif():
    """La CONTRE-EPREUVE, dans le test lui-meme : sans le canal, le verdict est l'ANCIEN. Sans ce
    cran, le precedent pourrait passer alors que la porte d'elevation ferait tout le travail."""
    bd = _board(coupe=[(A, B)])
    assert bq.is_adjacent(A, B, bd.elev_by_pos(), None) is True        # repli geometrique NOMME


def test_canal_absent_du_board_rend_None_jamais_un_dict_vide():
    """TRI-ETAT : `{}` se lirait comme « aucune tuile n'a de voisin » -> predicat FAUX partout,
    une degradation RESTRICTIVE massive (le vice de `#381-r3`)."""
    assert adjacent_neigh_by_pos(_board(with_neighbours=False)) is None
    assert adjacent_neigh_by_pos(None) is None


def test_tuile_hors_canal_retombe_sur_la_geometrie_pour_ELLE_SEULE():
    """Une carte fournie mais SANS la cle de la tuile source : le repli est LOCAL, il ne
    contamine pas les tuiles qui, elles, sont captees."""
    bd = _board(coupe=[(A, B)])
    partiel = dict(adjacent_neigh_by_pos(bd))
    del partiel[A]
    assert bq.is_adjacent(A, B, bd.elev_by_pos(), partiel) is True     # repli pour A
    assert bq.is_adjacent(B, A, bd.elev_by_pos(), partiel) is False    # B, lui, reste gate


def test_liste_stockee_VIDE_isole_la_tuile():
    """`foreach` sur une liste vide ne yield rien : une tuile dont le champ `neighbours` est
    present et VIDE n'a aucun voisin. C'est un etat REEL (mesure `C1_74` : deux `Water` dont tous
    les voisins sont a 2 crans), et il se distingue du champ ABSENT ci-dessus."""
    bd = _board()
    neigh = dict(adjacent_neigh_by_pos(bd))
    neigh[A] = []
    assert bq.is_adjacent(A, B, bd.elev_by_pos(), neigh) is False
    assert bq.is_adjacent(A, AUTRE, bd.elev_by_pos(), neigh) is False


def test_la_porte_d_elevation_SURVIT_a_la_bascule():
    """L'etage 2 ne doit pas disparaitre au profit de l'etage 1 : une arete PRESENTE dans la liste
    mais a `|dElev| >= 2` reste refusee."""
    bd = _board(elev={B: 2})
    neigh = adjacent_neigh_by_pos(bd)
    assert bq.is_adjacent(A, B, bd.elev_by_pos(), neigh) is False
    assert bq.is_adjacent(A, AUTRE, bd.elev_by_pos(), neigh) is True


def test_les_deux_etages_sont_INDEPENDANTS():
    """Chacun refuse pour SA raison : ni l'un ni l'autre ne subsume le second."""
    bd = _board(elev={AUTRE: 2}, coupe=[(A, B)])
    neigh = adjacent_neigh_by_pos(bd)
    assert bq.is_adjacent(A, B, bd.elev_by_pos(), neigh) is False       # etage 1 (liste)
    assert bq.is_adjacent(A, AUTRE, bd.elev_by_pos(), neigh) is False   # etage 2 (porte)
    assert bq.is_adjacent(A, B, bd.elev_by_pos(), None) is True         # ni l'un ni l'autre


# --- le CANAL : derivation et acces ------------------------------------------------------------

def test_dsl_context_derive_le_canal_de_son_board():
    """Meme parade que pour l'elevation (#433-r4-r1-r4) : brancher au `__post_init__` plutot qu'aux
    call-sites, sinon le prochain constructeur rouvre le trou en silence."""
    bd = _board(coupe=[(A, B)])
    ctx = DslContext(board=bd)
    assert ctx.neigh_by_pos is not None
    assert B not in ctx.neigh_by_pos[A]
    assert bq.is_adjacent(A, B, ctx.elev_by_pos, bq.neigh_map(ctx)) is False


def test_dsl_context_sans_board_ne_fabrique_pas_de_canal():
    ctx = DslContext()
    assert ctx.neigh_by_pos is None
    assert bq.neigh_map(ctx) is None


def test_dsl_context_ne_pietine_pas_un_canal_FOURNI():
    bd = _board()
    fourni = {A: []}
    ctx = DslContext(board=bd, neigh_by_pos=fourni)
    assert ctx.neigh_by_pos is fourni


def test_neigh_map_lit_les_TROIS_formes_de_contexte():
    """`AiDecisionContext`/`Scene` sont des objets, le `tile_leaf_ctx` est un dict : un acces ecrit
    a la main a chaque call-site retomberait sur `AttributeError` chez l'une ou l'autre."""
    class _Objet:
        neigh_by_pos = {A: [B]}

    assert bq.neigh_map(_Objet()) == {A: [B]}
    assert bq.neigh_map({"neigh_by_pos": {A: [B]}}) == {A: [B]}
    assert bq.neigh_map({}) is None
    assert bq.neigh_map(object()) is None          # porteur sans le champ -> tri-etat, pas d'erreur
    assert bq.neigh_map(None) is None


def test_scene_derive_le_canal_de_son_board():
    from engine.playbook.scene import Scene
    bd = _board(coupe=[(A, B)])
    sc = Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
               vis_by_id={}, units=[], hp_by_id={}, pos_by_id={}, team_by_id={}, eff_state=None,
               board=bd)
    assert sc.neigh_by_pos is not None and B not in sc.neigh_by_pos[A]
    assert bq.neigh_map(sc) is sc.neigh_by_pos          # meme objet -> memoise
    sc2 = Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                vis_by_id={}, units=[], hp_by_id={}, pos_by_id={}, team_by_id={}, eff_state=None)
    assert sc2.neigh_by_pos is None                    # sans board : tri-etat, pas de canal


# --- PROPAGATION aux trois derivees ------------------------------------------------------------

def test_count_adjacent_propage_le_canal():
    bd = _board(coupe=[(A, B)])
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    assert bq.count_adjacent(A, [B, AUTRE], elev, None) == 2       # avant : la couronne
    assert bq.count_adjacent(A, [B, AUTRE], elev, neigh) == 1      # apres : la liste stockee


def test_count_adjacent_matching_propage_le_canal():
    bd = _board(coupe=[(A, B)])
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    units = [{"pos": {"col": B[0], "row": B[1]}}, {"pos": {"col": AUTRE[0], "row": AUTRE[1]}}]
    assert bq.count_adjacent_matching(A, units, lambda u: True, elev, None) == 2
    assert bq.count_adjacent_matching(A, units, lambda u: True, elev, neigh) == 1


def test_are_entities_adjacent_propage_le_canal_ET_garde_son_court_circuit():
    """`MovementUtil$$AreTilesAdjacent` porte le court-circuit d'IDENTITE (#433-r1) : `t1 == t2`
    rend VRAI sans consulter la connectivite. Le canal ne doit pas le supprimer."""
    bd = _board(coupe=[(A, B)])
    neigh, elev = adjacent_neigh_by_pos(bd), bd.elev_by_pos()
    assert bq.are_entities_adjacent(A, B, elev, None) is True
    assert bq.are_entities_adjacent(A, B, elev, neigh) is False
    assert bq.are_entities_adjacent(A, A, elev, neigh) is True     # identite : VRAI malgre tout
