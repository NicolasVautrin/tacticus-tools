"""#448-r1-r1-r1-r1-r2 OFFLINE -- le CONTRAT du canal brut `ConnectivityComponent`.

Le capteur qui alimente ce canal (`connectivity` / `teleportTwinTileId` du RPC `boardGraph`)
exige une fenetre de reinjection pour tirer. Ces crans-la, eux, ne l'exigent PAS : ils
verrouillent le contrat du LECTEUR (`Board.neighbours_connectivity` / `Board.teleport_twin`),
c'est-a-dire tout ce qui peut se casser sans qu'aucun capteur ne soit en cause.

Le cran central est le TRI-ETAT. `#381-r3` a deja paye, sur le champ `neighbours`, la confusion
« absent == vide » : le repli inventait six voisins la ou le natif n'en a aucun. Ici la meme
faute serait PIRE -- un repli silencieux sur `neighbours_native()` rendrait precisement le champ
AMPUTE que ce canal existe pour contourner, donc le bug se deguiserait en correctif.

ASCII only (cp1252).
"""
from __future__ import annotations

from engine.entities.pathfinding.board import Board

# Bande 4x1. `neighbours` (le champ AMPUTE, capte via `TileQuery$$IterateAdjacentTiles` et sa
# porte `|dElev| < 2`) omet l'arete 2<->3 ; `connectivity` (le canal BRUT, la liste stockee du
# `ConnectivityComponent`) la porte. C'est exactement la forme mesuree sur `MC1_67` : 18 aretes
# dirigees presentes cote natif et absentes du champ herite.
_ROW = [
    {"id": 1, "col": 0, "row": 0, "elevation": 0, "walkable": True, "isWall": False,
     "neighbours": [2], "connectivity": [2], "teleportTwinTileId": 0},
    {"id": 2, "col": 1, "row": 0, "elevation": 0, "walkable": True, "isWall": False,
     "neighbours": [1], "connectivity": [1, 3], "teleportTwinTileId": 0},
    {"id": 3, "col": 2, "row": 0, "elevation": 2, "walkable": True, "isWall": False,
     "neighbours": [4], "connectivity": [2, 4], "teleportTwinTileId": 0},
    {"id": 4, "col": 3, "row": 0, "elevation": 2, "walkable": True, "isWall": False,
     "neighbours": [3], "connectivity": [3], "teleportTwinTileId": 0},
]


def _rows():
    return [dict(t) for t in _ROW]


def test_le_canal_brut_porte_l_arete_que_le_champ_ampute_omet():
    """La raison d'etre du canal : la marche 2->3 (delta d'elevation 2) EXISTE cote natif."""
    b = Board(_rows(), adjacency="evenq")
    assert b.neighbours_native(2) == [1]              # champ herite, ampute par la porte
    assert b.neighbours_connectivity(2) == [1, 3]     # canal brut, la liste stockee


def test_canal_ABSENT_rend_None_et_NE_retombe_PAS_sur_le_champ_ampute():
    """Le point qui compte. Un repli sur `neighbours_native()` rendrait le graphe AMPUTE en se
    faisant passer pour le graphe natif -- un bug deguise en correctif, invisible."""
    tiles = [{k: v for k, v in t.items() if k != "connectivity"} for t in _ROW]
    b = Board(tiles, adjacency="evenq")
    assert b.neighbours_connectivity(2) is None
    assert b.neighbours_native(2) == [1]              # l'autre canal, lui, repond toujours


def test_canal_VIDE_rend_une_liste_vide_pas_None():
    """Legitime cote natif : une tuile dont le `ConnectivityComponent` ne relie rien. `[]` et
    `None` ne veulent pas dire la meme chose et ne doivent jamais se confondre."""
    tiles = _rows()
    tiles[1]["connectivity"] = []
    b = Board(tiles, adjacency="evenq")
    assert b.neighbours_connectivity(2) == []
    assert b.neighbours_connectivity(2) is not None


def test_le_canal_filtre_les_ids_hors_board():
    """Meme discipline que `neighbours_native` : un id absent du board est ecarte, pas propage."""
    tiles = _rows()
    tiles[0]["connectivity"] = [2, 999]
    b = Board(tiles, adjacency="evenq")
    assert b.neighbours_connectivity(1) == [2]


def test_teleport_twin_tri_etat():
    """`0` cote natif = « pas une tuile de teleport » (la valeur exacte que testent les quatre
    surcharges de `TileExtensions$$IsTeleportationTile`) -> `None`, jamais un id `0`."""
    b0 = Board(_rows(), adjacency="evenq")
    assert b0.teleport_twin(1) is None                # champ present, valeur 0

    tiles = _rows()
    tiles[0]["teleportTwinTileId"] = 4
    tiles[3]["teleportTwinTileId"] = 1
    b1 = Board(tiles, adjacency="evenq")
    assert b1.teleport_twin(1) == 4
    assert b1.teleport_twin(4) == 1                   # les deux se pointent mutuellement
    assert b1.teleport_twin(2) is None

    absent = Board([{k: v for k, v in t.items() if k != "teleportTwinTileId"} for t in _ROW],
                   adjacency="evenq")
    assert absent.teleport_twin(1) is None


# ---------------------------------------------------------------------------------------------
# #448-r1-r1-r1-r1-r2-r1 -- LE REBRANCHEMENT. Ces crans REMPLACENT la garde de perimetre
# (« aucun pathfinder n'est rebranche »), qui a fait son office : le rebranchement est fait,
# mesure live et confronte au natif (case-doc SS14). Elle ne pouvait de toute facon pas garder ce
# qu'elle croyait -- elle observait la MARCHE, sur qui le changement est un NO-OP prouve, donc
# elle serait restee VERTE apres le rebranchement. Ce qui la remplace garde les DEUX faces : le
# no-op la ou il est prouve, et le changement la ou il doit avoir lieu.
#
# Grille 3x3 even-q, ids 1..9 par (col,row) : (0,0)=1 (0,1)=2 (0,2)=3 / (1,0)=4 (1,1)=5 (1,2)=6 /
# (2,0)=7 (2,1)=8 (2,2)=9. La tuile 5 est un `Bridge` : `TileComponent$$HasEdge` ne lui laisse
# que l'axe de son pont (4 et 6), donc les 8 aretes dirigees qui la relient a 1,2,7,8 sont dans
# la GEOMETRIE et pas dans le canal -- la forme exacte mesuree sur `C1_74`. La tuile 9 est a
# elevation 2 : ses aretes sont dans le canal et PAS dans le champ herite, que la porte
# `|dElev| < 2` de `TileQuery$$IterateAdjacentTiles` ampute.
_GEO = {1: [2, 4, 5], 2: [1, 3, 5, 6], 3: [2, 6], 4: [1, 5, 7], 5: [1, 2, 4, 6, 7, 8],
        6: [2, 3, 5, 8, 9], 7: [4, 5, 8], 8: [5, 6, 7, 9], 9: [6, 8]}
_CONN = {1: [2, 4], 2: [1, 3, 6], 3: [2, 6], 4: [1, 5, 7], 5: [4, 6],
         6: [2, 3, 5, 8, 9], 7: [4, 8], 8: [6, 7, 9], 9: [6, 8]}
#: `neighbours` == `connectivity` INTERSECTE `{|dElev| < 2}` -- l'identite LUE au decompile, pas
#: recopiee : seules les aretes touchant la tuile 9 (elevation 2) disparaissent.
_NEIGH = {1: [2, 4], 2: [1, 3, 6], 3: [2, 6], 4: [1, 5, 7], 5: [4, 6],
          6: [2, 3, 5, 8], 7: [4, 8], 8: [6, 7], 9: []}
_ELEV = {i: (2 if i == 9 else 0) for i in range(1, 10)}
_POS = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 0), 5: (1, 1), 6: (1, 2),
        7: (2, 0), 8: (2, 1), 9: (2, 2)}


def _grid(canal: bool = True):
    out = []
    for i in range(1, 10):
        t = {"id": i, "col": _POS[i][0], "row": _POS[i][1], "elevation": _ELEV[i],
             "walkable": True, "isWall": False, "neighbours": list(_NEIGH[i]),
             "tileDefId": "Bridge" if i == 5 else "Grass"}
        if canal:
            t["connectivity"] = list(_CONN[i])
            t["teleportTwinTileId"] = 0
        out.append(t)
    return out


def test_la_grille_de_garde_reproduit_les_DEUX_ecarts_mesures():
    """Sans ce cran, les suivants pourraient etre verts sur un board DEGENERE -- le piege paye
    deux fois sur ce sujet (`C6_25` rend `316/316/316`). On verifie donc d'abord que la grille
    porte bien les deux ecarts, dans les deux sens, et l'identite qui les separe."""
    b = Board(_grid(), adjacency="evenq")
    g = {i: set(b.neighbours_geometric(i)) for i in range(1, 10)}
    c = {i: set(b.neighbours_connectivity(i)) for i in range(1, 10)}
    n = {i: set(b.neighbours_native(i)) for i in range(1, 10)}
    assert g == {i: set(v) for i, v in _GEO.items()}       # la couronne even-q, recalculee
    assert sum(len(n[i] - c[i]) for i in c) == 0           # N inclus dans C
    assert sum(len(c[i] - g[i]) for i in c) == 0           # C inclus dans G
    assert sum(len(c[i] - n[i]) for i in c) == 4           # la porte d'elevation (tuile 9)
    assert sum(len(g[i] - c[i]) for i in c) == 8           # le refus de `HasEdge` (le Bridge)
    # `G\\N == C\\N + G\\C` : l'identite qui SEPARE les deux causes. A deux vues elles sont
    # indiscernables -- c'est ce qui avait fait sous-compter le residu.
    assert sum(len(g[i] - n[i]) for i in g) == 4 + 8
    # Toute arete que le canal ajoute au champ herite a `|dElev| >= 2` : c'est ce fait, et lui
    # seul, qui rend le rebranchement INERTE sur les routes a porte d'elevation.
    assert all(abs(_ELEV[a] - _ELEV[x]) >= 2 for a in c for x in c[a] - n[a])


def test_la_MARCHE_est_INCHANGEE_par_le_rebranchement():
    """NO-OP, et il est PROUVE, pas constate : `WalkPathfinder$$IsValidPathNode` exige
    `|dElev| <= 1` (`$$IsReachableElevationDifference`) et refuse donc exactement les aretes que
    le canal ajoute. Mesure live confirmant : 0 couple (start,depth) sur 189 change, sur les
    TROIS boards."""
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions

    avec = Board(_grid(canal=True), adjacency="evenq")
    sans = Board(_grid(canal=False), adjacency="evenq")
    for start in range(1, 10):
        for depth in (1, 2, 5):
            a = get_movable_positions(avec, start, depth, {}, 1)[1]
            s = get_movable_positions(sans, start, depth, {}, 1)[1]
            assert a == s, (start, depth, a, s)
    # ... et la tuile 9 reste inatteignable des DEUX cotes : le canal la relie, la porte du
    # PREDICAT la refuse. C'est la difference entre « le port ne voit pas l'arete » et « le port
    # la voit et la refuse » -- indiscernable au resultat, decisive a la lecture.
    assert 9 not in get_movable_positions(avec, 1, 9, {}, 1)[1]


def test_IGNORE_TERRAIN_est_INCHANGE_par_le_rebranchement():
    """Meme argument, meme porte (`|dElev| <= 1`). Ce site alimente l'utilite IA
    `MinDistanceToClosestEnemyUtility` : un changement ici ferait basculer des decisions."""
    from engine.entities.pathfinding.ignore_terrain_pathfinder import get_path_node_counts

    avec = Board(_grid(canal=True), adjacency="evenq")
    sans = Board(_grid(canal=False), adjacency="evenq")
    for target in range(1, 10):
        assert get_path_node_counts(avec, target, {}) == get_path_node_counts(sans, target, {})


def test_la_BEELINE_suit_le_canal_et_CONTOURNE_le_pont():
    """LE site qui MORD, parce que `IgnoreEverythingPathfinder$$IsValidPathNode` est le corps
    trivial `return true` : il ne re-filtre RIEN, donc une arete de trop dans le voisinage EST un
    raccourci. `1 -> 8` traverse le pont en 2 aretes sur la geometrie, en fait le tour en 3 sur
    le canal. Le NATIF a departage (`tilesMovedThisTurn` d'un porteur `TeleportStrike` sur
    `C1_74`) : il suit le CANAL, 4/4 mesures discriminantes."""
    from engine.entities.pathfinding.beeline_pathfinder import find_path

    avec = Board(_grid(canal=True), adjacency="evenq")
    p = find_path(avec, 1, 8)
    assert p is not None and len(p) - 1 == 3, p
    assert 5 not in p, p                                   # le pont n'est PAS traverse
    assert find_path(avec, 2, 7) is not None and len(find_path(avec, 2, 7)) - 1 == 3


def test_le_repli_de_la_BEELINE_est_la_GEOMETRIE_jamais_le_champ_ampute():
    """Canal non capte (boardGraph d'un bundle anterieur). Retomber sur `neighbours_native`
    rejouerait le bug que la mesure de #448-r1-r1-r1-r1 SS9 avait ferme (le port rendait 3 la ou
    le natif enregistre 2) : le correctif deguiserait le bug. Le repli est donc la GEOMETRIE."""
    from engine.entities.pathfinding.beeline_pathfinder import find_path

    sans = Board(_grid(canal=False), adjacency="evenq")
    p = find_path(sans, 1, 8)
    assert p is not None and len(p) - 1 == 2, p            # la geometrie, pas le champ ampute
    assert 5 in p, p
    # Le champ herite aurait donne 3 ici AUSSI (il n'ampute que les aretes de la tuile 9), donc
    # ce cran ne suffirait pas seul. Le discriminant est la tuile 9 : depuis 6, le champ ampute
    # ne l'atteint pas du tout, la geometrie si.
    assert find_path(sans, 6, 9) is not None and len(find_path(sans, 6, 9)) - 1 == 1
    assert sans.neighbours_native(9) == []                 # le champ, lui, la laisse isolee


def test_le_JUMEAU_EN_DOMAINE_POSITION_reste_sur_le_champ_AMPUTE_et_c_est_LOAD_BEARING():
    """LE SITE QUI NE DOIT **PAS** ETRE REBRANCHE, et ce n'est pas un oubli.

    `ignore_terrain_pathfinder.get_path_node_counts_by_pos` (le jumeau en domaine POSITION, ne
    depuis `#175-r1`) recoit `neigh_by_pos` = `board.neighbours_native` -- le champ AMPUTE -- alors
    que son frere en domaine TILE-ID lit le canal. La docstring du jumeau appelle ca un << NO-OP
    prouve >> ; ce cran le MESURE, et mesure aussi le regime ou il CESSE d'en etre un.

      * `elev_by_pos` FOURNI (le cas nominal) : les deux canaux rendent le MEME resultat. Le
        rebranchement serait inerte -- exactement l'argument de `base_add_neighbours` (les aretes
        que le canal ajoute ont `|dElev| >= 2`, et `IgnoreTerrainPathfinder$$IsValidPathNode` exige
        `|dElev| <= 1`).
      * `elev_by_pos` ABSENT : ils DIVERGENT. Le port ne peut alors PAS rejouer la porte, et le
        canal le ferait SUR-ATTEINDRE -- il compterait joignable une tuile que le natif refuse.
        Le champ ampute, lui, porte deja la porte du CAPTEUR : c'est ce qui rend le port juste
        dans ce regime-la.

    ⇒ le choix est LOAD-BEARING dans un sens, inerte dans l'autre. Un futur rebranchement << par
    coherence >> casserait le second cas sans rien gagner au premier. Le second `assert` est ce
    qui l'interdit ; le premier est ce qui empeche ce test d'etre vert sur un montage degenere."""
    from engine.entities.pathfinding import ignore_terrain_pathfinder as ITP

    b = Board(_grid(), adjacency="evenq")
    ampute = {_POS[i]: [_POS[x] for x in b.neighbours_native(i)] for i in range(1, 10)}
    canal = {_POS[i]: [_POS[x] for x in b.base_add_neighbours(i)] for i in range(1, 10)}
    assert ampute != canal, "montage DEGENERE : les deux canaux coincident, rien ne peut diverger"
    walk = {_POS[i]: True for i in range(1, 10)}
    elev = {_POS[i]: _ELEV[i] for i in range(1, 10)}

    avec_a = ITP.get_path_node_counts_by_pos(_POS[1], neigh_by_pos=ampute,
                                             walkable_by_pos=walk, elev_by_pos=elev)
    avec_c = ITP.get_path_node_counts_by_pos(_POS[1], neigh_by_pos=canal,
                                             walkable_by_pos=walk, elev_by_pos=elev)
    assert avec_a == avec_c, (avec_a, avec_c)          # NO-OP, MESURE et pas seulement deduit

    sans_a = ITP.get_path_node_counts_by_pos(_POS[1], neigh_by_pos=ampute,
                                             walkable_by_pos=walk, elev_by_pos=None)
    sans_c = ITP.get_path_node_counts_by_pos(_POS[1], neigh_by_pos=canal,
                                             walkable_by_pos=walk, elev_by_pos=None)
    assert sans_a != sans_c, (
        "sans porte d'elevation les deux canaux devraient DIVERGER (la tuile 9, a elevation 2, "
        "n'est joignable que par le canal) -- si ce n'est plus le cas, l'argument qui justifie de "
        "laisser ce site sur le champ ampute a disparu : %r vs %r" % (sans_a, sans_c))
    assert _POS[9] in sans_c and _POS[9] not in sans_a, (sans_a, sans_c)


def test_base_add_neighbours_respecte_le_TRI_ETAT_du_canal():
    """Le foyer ne doit jamais confondre « canal absent » et « liste vide ». Une tuile dont le
    `ConnectivityComponent` ne relie rien rend `[]` -- et surtout PAS le repli, qui inventerait
    des voisins la ou le natif n'en a aucun (la faute exacte de `#381-r3`)."""
    tiles = _grid()
    tiles[0]["connectivity"] = []                          # tuile 1 : composant present, vide
    b = Board(tiles, adjacency="evenq")
    assert b.base_add_neighbours(1) == []
    assert b.base_add_neighbours(1, b.neighbours_geometric) == []
    assert b.has_connectivity_channel() is True

    sans = Board(_grid(canal=False), adjacency="evenq")
    assert sans.has_connectivity_channel() is False
    assert sans.base_add_neighbours(1) == sans.neighbours_native(1)
    assert sans.base_add_neighbours(1, sans.neighbours_geometric) == sans.neighbours_geometric(1)
