"""#515 (residu `#497-r1`) -- GARDE de l'ADJACENCE du RUNNER : une ENUMERATION, pas un disque.

CE QUE CE FICHIER FIGE, et pourquoi la divergence n'etait gardee par RIEN avant lui : `#497` a
MESURE l'ecart (18 aretes dirigees sur 316 sur `MC1_67`, chaine de 4 la ou le natif s'arrete a 1)
mais n'a rien asserte -- un test ecrit a ce moment-la aurait FIGE LE BUG. Il ne pouvait donc
exister qu'APRES la reparation, et c'est ce fichier.

LES DEUX `order` ONT DES ITERATEURS NATIFS DISTINCTS, et c'est le coeur de la garde :

  * `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` (rayon 1)
        elev0 = tile[+0x20][+0x18];                                  // lu UNE fois, d__8+0x48
        foreach (nid in tile[+0x30][+0x10])                           // ConnectivityComponent
            t = state.GetTileEntity(nid); if (t == null) continue;
            <filtres terrain optionnels>
            if (Math.Abs(elev0 - t[+0x20][+0x18]) < 2) yield return t;   // porte INCONDITIONNELLE
    Une ENUMERATION de liste STOCKEE, puis une PORTE. La valeur ABSOLUE rend la porte SYMETRIQUE :
    elle est portee par la PAIRE, jamais par l'arete.

  * `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` (rayon
    quelconque) est une TRIPLE BOUCLE en coordonnees CUBE (`x`,`y`,`z` avec `x+y+z == 0`) resolue
    par `StateExtensions$$GetTileAt` : **aucune liste stockee, AUCUNE porte d'elevation**.

=> Brancher les deux `order` sur la meme primitive serait un BUG, pas une unification. Le test
`test_515_surrounding_traverse_la_marche` est la POUR CA : il rougirait sur une reparation trop
large, la ou tous les autres resteraient verts.

Chaque axe porte sa CONTRE-EPREUVE (l'ancienne primitive, rejouee par monkeypatch, doit INVERSER
le verdict) et le test VERIFIE que la mutation a mordu : un test qui ne peut pas rougir ne garde
rien, et un patch qui ne matche pas rend un VERT qui ment.

ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.dsl import nodes as dsl
from engine.dsl.base import Const, DslContext, _adjacent_tiles_native, _within
from engine.entities.pathfinding.board import EVENQ_EVEN, EVENQ_ODD, Board
from engine.entities.selectors.units import AdjacentUnits, SurroundingUnits

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        # PROPRE A CE FICHIER. Foyers load-bearing, pour la relecture : `engine/dsl/base.py`
        # (`_within` / `_adjacent_tiles_native` / `_tile_enum_rank`),
        # `engine/entities/selectors/units.py` (les six selecteurs et l'`order` qu'ils passent),
        # `engine/entities/pathfinding/board.py` (`neighbours_native` et son tri-etat), et
        # `probe_515_adjacence_rayon_de_souffle.py` (deux tests LISENT sa mesure).
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
        # Deux tests balaient les 675 boards VERSIONNES : leur verdict en depend directement.
        "data/boards/**",
    ),
    # Aucun oracle natif ici (pas de session, pas de runner) : ce fichier confronte le port a
    # des boards versionnes et a lui-meme. Le BUILD ne peut pas le faire changer d'avis.
    "build": False,
    "toujours": False,
    "raison": "Verdicts figes : l'etage `order='adjacent'` (rayon 1) enumere la liste STOCKEE "
              "(`TileQuery$$IterateAdjacentTiles`) au lieu de tester `hexgeo.distance <= r` ; "
              "l'etage `order='surrounding'` reste GEOMETRIQUE (`IterateSurroundingTiles` est un "
              "balayage cube sans porte d'elevation) ; le TRI-ETAT de `_adjacent_tiles_native` ; "
              "et la MONOTONIE de la reparation sur les 675 boards versionnes. Aucun runner, "
              "aucune session Frida : le seul acces disque est le depot.",
}

COLS, ROWS = 5, 5

CENTRE = (2, 2)
#: Voisin de PLAIN-PIED : la porte l'accorde des deux cotes.
PLAIN = (2, 1)
#: Voisin DERRIERE LA MARCHE : `|dElev| = 3 >= 2`, le natif ne le voit pas. C'est le temoin.
MARCHE = (2, 3)


def _board(marche_elev: int = 3, avec_neighbours: bool = True) -> Board:
    """Plateau 5x5 plat a elevation 0, sauf `MARCHE`. Le champ `neighbours` est construit comme le
    CAPTEUR le produit -- `BattleQuery$$GetAdjacentTiles(t, false, false, true)`, donc filtres de
    terrain OFF et porte `|dElev| < 2` ON. Identite LUE (cf. `Board.base_add_neighbours`) :
    `neighbours == connectivity INTERSECTE {aretes de |dElev| < 2}`.

    `avec_neighbours=False` retire le CHAMP (pas la liste : le champ) -> le tri-etat doit replier
    sur la geometrie, jamais rendre un voisinage vide."""
    idof = {(c, r): 1 + c * ROWS + r for c in range(COLS) for r in range(ROWS)}
    elev = {p: (marche_elev if p == MARCHE else 0) for p in idof}
    tiles = []
    for (c, r), i in idof.items():
        ds = EVENQ_EVEN if c % 2 == 0 else EVENQ_ODD
        voisins = [idof[(c + dc, r + dr)] for dc, dr in ds
                   if (c + dc, r + dr) in idof and abs(elev[(c, r)] - elev[(c + dc, r + dr)]) < 2]
        t = {"id": i, "col": c, "row": r, "elevation": elev[(c, r)], "tileDefId": "Grass",
             "isTemporary": False, "isWall": False, "walkable": True, "occupantUnitId": None}
        if avec_neighbours:
            t["neighbours"] = voisins
        tiles.append(t)
    return Board(tiles, adjacency="evenq")


def _u(uid, pos, team=2):
    return {"id": uid, "team": team, "hp": 100, "alive": True,
            "pos": {"col": pos[0], "row": pos[1]}}


def _ctx(board, unites, caster):
    return DslContext(units=list(unites) + [caster], caster=caster, target=caster, board=board)


# ------------------------------------------------------------------ le montage lui-meme
def test_515_le_montage_est_discriminant():
    """SANS ce cran, tous les autres tests pourraient etre verts pour la mauvaise raison : il faut
    que les deux temoins soient a distance hex 1 (donc pris par l'ANCIENNE primitive) et que la
    porte n'en refuse qu'UN SEUL."""
    assert hexgeo.distance(CENTRE, PLAIN) == 1
    assert hexgeo.distance(CENTRE, MARCHE) == 1
    b = _board()
    voisins = _adjacent_tiles_native(b, [CENTRE])
    assert voisins is not None, "centre non resolvable : le montage ne mesure rien"
    assert PLAIN in voisins, "le montage a perdu son temoin de plain-pied"
    assert MARCHE not in voisins, "la marche n'est pas assez haute : |dElev| < 2"


# ------------------------------------------------------------------ l'axe repare
def test_515_adjacent_units_s_arrete_a_la_marche():
    """`AdjacentUnits` = `Units(AdjacentTiles(target))` -> `TileQuery$$IterateAdjacentTiles`.
    L'unite derriere la marche N'EST PAS voisine, meme a distance hex 1."""
    b = _board()
    caster = _u(1, CENTRE, team=1)
    got = AdjacentUnits(dsl.Caster(), Const(1)).select(_ctx(b, [_u(2, PLAIN), _u(3, MARCHE)],
                                                            caster))
    assert [u["id"] for u in got] == [2], "ids retenus : %s" % [u["id"] for u in got]


def test_515_contre_epreuve_ancienne_primitive(monkeypatch):
    """L'ANCIENNE primitive (`hexgeo.distance <= r`) rejouee : le verdict doit S'INVERSER.

    Le repli geometrique est exactement ce que `_adjacent_tiles_native` rend quand aucun centre
    n'est resolvable -- on le force en rendant `None`, ce qui EST le chemin de degradation reel du
    port, pas un stub invente. Et on VERIFIE que la mutation a mordu (l'unite derriere la marche
    revient), sans quoi ce test serait un vert qui ment."""
    b = _board()
    caster = _u(1, CENTRE, team=1)
    ctx = _ctx(b, [_u(2, PLAIN), _u(3, MARCHE)], caster)
    monkeypatch.setattr("engine.dsl.base._adjacent_tiles_native", lambda board, centers: None)
    got = [u["id"] for u in AdjacentUnits(dsl.Caster(), Const(1)).select(ctx)]
    assert got == [2, 3], ("la contre-epreuve N'A PAS MORDU : %s (attendu [2, 3], la couronne hex "
                           "entiere)" % got)


# ------------------------------------------------------------------ la BORNE de la reparation
def test_515_surrounding_traverse_la_marche():
    """`SurroundingUnits` passe par `IterateSurroundingTiles`, une TRIPLE BOUCLE CUBE resolue par
    `GetTileAt` : **aucune liste stockee, aucune porte d'elevation**. La distance hex y est le
    mirror EXACT.

    Ce test est la GARDE DE NON-UNIFICATION : il est le seul du fichier qui rougirait si on
    branchait `order='surrounding'` sur la meme primitive que `order='adjacent'`."""
    b = _board()
    caster = _u(1, CENTRE, team=1)
    got = SurroundingUnits(dsl.Caster(), Const(1)).select(_ctx(b, [_u(2, PLAIN), _u(3, MARCHE)],
                                                               caster))
    assert sorted(u["id"] for u in got) == [2, 3], \
        "la porte d'elevation a fuite sur `surrounding` : %s" % sorted(u["id"] for u in got)


def test_515_adjacent_a_rayon_deux_reste_geometrique():
    """`order='adjacent'` avec un rayon != 1 n'a PAS d'homologue natif (`AdjacentTiles` est ring-1
    par construction) : le port y retombe sur le disque, et la reparation ne doit pas s'y etendre.
    Le dire par un test evite qu'un lecteur l'etende « par coherence »."""
    b = _board()
    caster = _u(1, CENTRE, team=1)
    got = _within([_u(3, MARCHE)], CENTRE, 2, board=b, order="adjacent")
    assert [u["id"] for u in got] == [3]


# ------------------------------------------------------------------ le TRI-ETAT
def test_515_tri_etat_champ_absent_replie_sur_la_geometrie():
    """Champ `neighbours` ABSENT = board d'un test unitaire ou capture anterieure -> degradation
    PERMISSIVE et nommee. Jamais un voisinage vide."""
    b = _board(avec_neighbours=False)
    caster = _u(1, CENTRE, team=1)
    got = AdjacentUnits(dsl.Caster(), Const(1)).select(_ctx(b, [_u(2, PLAIN), _u(3, MARCHE)],
                                                            caster))
    assert sorted(u["id"] for u in got) == [2, 3]


def test_515_tri_etat_sans_board_replie_sur_la_geometrie():
    caster = _u(1, CENTRE, team=1)
    got = _within([_u(2, PLAIN), _u(3, MARCHE)], CENTRE, 1, order="adjacent")
    assert sorted(u["id"] for u in got) == [2, 3]


def test_515_tri_etat_zero_voisin_est_un_resultat_exact():
    """`[]` != `None`. Une tuile dont TOUS les voisins stockes sont a 2 niveaux ou plus ressort a
    ZERO voisin, et c'est EXACT -- mesure `C1_74` : les deux `Water` `(2,5)`/`(4,5)`, elevation 1,
    entourees de 3 et 4. Replier la dessus rejouerait le vice de `#381-r3` (il INVENTAIT six
    voisins la ou le natif n'en a aucun) et rendrait la reparation inerte precisement sur les
    tuiles qu'elle vise."""
    b = _board()
    for t in b.by_id.values():                       # tuile isolee : champ PRESENT, liste VIDE
        if (t["col"], t["row"]) == CENTRE:
            t["neighbours"] = []
    assert _adjacent_tiles_native(b, [CENTRE]) == []
    caster = _u(1, CENTRE, team=1)
    got = AdjacentUnits(dsl.Caster(), Const(1)).select(_ctx(b, [_u(2, PLAIN), _u(3, MARCHE)],
                                                            caster))
    assert got == [], "un voisinage stocke VIDE doit rendre l'ensemble VIDE, pas la couronne hex"


def test_515_tri_etat_centre_hors_board_replie():
    """Centre resolvable sur AUCUNE tuile du board -> `None` -> repli geometrique. C'est le cas
    d'un montage dont le board ne couvre pas la position (capture partielle)."""
    b = _board()
    assert _adjacent_tiles_native(b, [(99, 99)]) is None


# ------------------------------------------------------------------ MONOTONIE
def test_515_la_reparation_est_monotone_sur_tous_les_boards():
    """La porte ne peut que RETIRER des aretes -- c'est ce qui BORNE le rayon de souffle : tout
    site dont le resultat change voit son ensemble RETRECIR, jamais grandir. Mesure sur les 675
    boards versionnes, pas sur un temoin choisi.

    Le test exige AUSSI que la porte MORDE quelque part : un `0 violation` sur un corpus ou elle
    ne mord jamais serait un accord en regime DEGENERE."""
    import probe_515_adjacence_rayon_de_souffle as P
    m = P.etage234()
    assert m["boards"] > 100, "corpus de boards trop maigre (%d) -- mesure sans portee" % m["boards"]
    assert m["refusees"] > 0 and m["boards_sensibles"] > 0, \
        "la porte ne mord sur AUCUN board : regime degenere, le 0 ci-dessous ne prouve rien"
    assert m["violations_monotonie"] == 0, \
        "%d violation(s) d'inclusion : la reparation AJOUTE des aretes" % m["violations_monotonie"]


@pytest.mark.parametrize("board_id,aretes,tuiles", [("MC1_67", 18, 11)])
def test_515_accord_avec_la_mesure_live_de_497(board_id, aretes, tuiles):
    """CONTROLE CROISE : la mesure OFFLINE (elevations du BC) retrouve-t-elle ce que #497 a mesure
    LIVE sur le `boardGraph` ? Sur `MC1_67`, #497 a compte 18 aretes dirigees sur-atteintes et 11
    tuiles touchees. Les deux voies sont INDEPENDANTES (champ capte vs champ BC + porte rejouee).

    Un ecart ne serait pas forcement une faute -- l'offline ne voit pas le refus `HasEdge` du
    substrat, donc il MINORE. Mais l'egalite, elle, etablit que sur ce board la porte explique la
    TOTALITE de l'ecart."""
    import probe_515_adjacence_rayon_de_souffle as P
    m = P.etage234()
    r = m["par_board"].get(board_id)
    assert r is not None, "board %s absent de data/boards/global" % board_id
    assert (r[2], r[3]) == (aretes, tuiles), \
        "%s : offline %d aretes / %d tuiles, #497 live %d / %d" % (board_id, r[2], r[3],
                                                                   aretes, tuiles)
