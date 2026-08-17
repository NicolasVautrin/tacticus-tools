"""#433-r4-r1-r4-r1 -- `Unobscured` lit le CANAL du contexte, il ne re-derive plus sa carte.

Ce que cette garde verrouille
-----------------------------
`IdunBattleLogic.Entities.DSLSelectors$$Unobscured` ->
`IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$Select` ->
`IdunBattle.Core.Services.TargetingQuery$$IsTargetUnitObscured` ->
`IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain` : cote natif l'elevation est un
composant de TUILE (`tile->[0x20]->[0x18]`), deref directement, et
`IdunBattle.Entities.TileExtensions$$GetElevationDifference` LEVE quand il manque -- il n'existe
AUCUN etat natif << elevation inconnue >>. L'inconnu est donc une notion strictement PORT, et le
port a UN seul contrat pour elle : le tri-etat d'`entities/pathfinding/board.elevations_by_pos`,
que `DslContext.__post_init__` pose dans `ctx.elev_by_pos` -- `None` = pas de canal, et une tuile
non captee est OMISE, jamais cotee `0`.

`Unobscured` ne lisait pas ce canal : il re-derivait
`{k: t.get("elevation", 0) for k, t in ctx.board.by_coord.items()}`. Les trois etages ci-dessous
mesurent que cet ecart MORD, et dans les DEUX SENS -- une correction seulement restrictive (ou
seulement permissive) serait FAUSSE.

Chaque etage porte sa CONTRE-EPREUVE : la carte d'AVANT est reconstruite ici meme
(`_carte_d_avant`) et le test assertionne que les deux cartes NE DONNENT PAS le meme ensemble. Une
garde qui ne verrait pas son propre bras d'avant diverger ne prouverait rien : elle serait verte
sur le code d'avant comme sur celui d'apres.

100 % OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Le noeud sous garde, et le seul dont le comportement est mesure ici.
        "scripts/python/engine/entities/selectors/units.py",
        # Le CANAL : le foyer tri-etat, et le constructeur de contexte qui le pose.
        "scripts/python/engine/entities/pathfinding/board.py",
        "scripts/python/engine/dsl/base.py",
        # Le PREDICAT dont les etages exercent le contrat sur les cles absentes.
        "scripts/python/engine/battle_query.py",
        # La geometrie hex dont le plateau DERIVE ses deux formes de ligne (droite / fat-line) :
        # un changement de voisinage change QUELLES paires sont mesurees.
        "scripts/python/hexgeo.py",
        # La source du selecteur employe par les etages 3 et 4.
        "scripts/python/engine/entities/selectors/tiles.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline et sans lecture de `data/` : les seules entrees sont le noeud, le "
              "canal d'elevation (foyer + pose dans le contexte), le predicat "
              "`is_target_tile_obscured` dont le contrat sur les cles absentes EST l'objet de la "
              "garde, la geometrie hex qui derive le plateau, et le selecteur source. Le build du "
              "jeu n'entre pas : aucun symbole n'est resolu ici, ils ne sont que CITES.",
}

import sys                                                                       # noqa: E402
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine import battle_query as bq                                            # noqa: E402
from engine.dsl.base import DslContext                                           # noqa: E402
from engine.entities.pathfinding.board import Board, elevations_by_pos           # noqa: E402
from engine.entities.selectors.tiles import AllAliveUnits                         # noqa: E402
from engine.entities.selectors.units import Enemies, Unobscured                           # noqa: E402

COLS, ROWS = 7, 7


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board(elev=None, sans_elevation=()) -> Board:
    """Board 7x7 plein, voisinage even-q. `elev` = surcharges `{(col,row): elevation}`, le reste
    a 0 ; `sans_elevation` = positions dont le CHAMP est retire (tuile non captee)."""
    elev = elev or {}
    sans = set(sans_elevation)
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            t = {"id": _tid(col, row), "col": col, "row": row,
                 "walkable": True, "isWall": False, "neighbours": nb}
            if (col, row) not in sans:
                t["elevation"] = int(elev.get((col, row), 0))
            tiles.append(t)
    return Board(tiles, adjacency="evenq")


def _unit(uid, team, pos):
    return {"id": uid, "team": team, "alive": True, "hp": 100,
            "pos": {"col": pos[0], "row": pos[1]}}


def _carte_d_avant(board):
    """Le BRAS D'AVANT, verbatim : `Unobscured` re-derivait sa carte depuis `board.by_coord` avec
    un defaut `0`. Reconstruit ici pour que chaque etage puisse mesurer que le fix MORD."""
    bc = getattr(board, "by_coord", None) if board is not None else None
    return ({k: t.get("elevation", 0) for k, t in bc.items()} if bc else None)


def _obscurcies(frm, cibles, elev):
    """Ce que `Unobscured` retient, exprime au niveau du seul predicat qui differe entre les deux
    bras -- `bq.is_target_tile_obscured`. Rend l'ensemble des cibles GARDEES."""
    return {p for p in cibles
            if not (hexgeo.distance(frm, p) == 2 and elev is not None
                    and bq.is_target_tile_obscured(frm, p, elev))}


def _mids(frm, to):
    """Les tuiles intermediaires que teste `is_target_tile_obscured` : les voisins communs."""
    return [p for p in hexgeo.neighbors(*frm) if hexgeo.distance((p[0], p[1]), to) == 1]


def _paire_diagonale():
    """Un couple (frm, to) a distance 2 avec DEUX voisins communs (cas << fat-line >>), et un
    couple a UN seul voisin commun (ligne droite). Derives de la geometrie, jamais ecrits."""
    diag = droite = None
    for col in range(1, COLS - 1):
        for row in range(1, ROWS - 1):
            frm = (col, row)
            for to in [(c, r) for c in range(COLS) for r in range(ROWS)
                       if hexgeo.distance(frm, (c, r)) == 2]:
                n = len(_mids(frm, to))
                if n == 2 and diag is None:
                    diag = (frm, to)
                if n == 1 and droite is None:
                    droite = (frm, to)
    assert diag is not None, "aucun couple diagonal (2 voisins communs) sur ce plateau"
    assert droite is not None, "aucun couple droit (1 voisin commun) sur ce plateau"
    return diag, droite


# ===================================================== 0. LE PLATEAU EST BIEN DANS LES DEUX REGIMES

def test_le_plateau_offre_les_deux_geometries():
    """Un etage qui ne mesurerait qu'une des deux formes de ligne ne verrait pas la moitie du
    gisement. On assertionne le NON-VIDE des deux avant de s'en servir."""
    diag, droite = _paire_diagonale()
    assert len(_mids(*diag)) == 2
    assert len(_mids(*droite)) == 1


# ============================================ 1. INCONNUE EN MID -- le `0` invente ETEINT le blocage

def test_mid_non_capte_le_zero_invente_eteignait_le_blocage():
    """Cas DIAGONAL (2 candidates). Une crete a 4 sur l'une, l'autre non captee.

    * canal (fix)   : la candidate inconnue est RETIREE -> `len(mids) == 1` -> `4 - 0 >= 2` -> BLOQUE.
    * bras d'avant  : elle vaut `0` -> fat-line -> `all(4>=2, 0>=2)` FAUX -> ne bloque pas.
    """
    (frm, to), _ = _paire_diagonale()
    m0, m1 = _mids(frm, to)
    board = _board(elev={m0: 4}, sans_elevation=[m1])

    canal = elevations_by_pos(board)
    avant = _carte_d_avant(board)
    assert m1 not in canal, "le foyer doit OMETTRE la tuile non captee"
    assert avant[m1] == 0, "le bras d'avant doit bien FABRIQUER un 0 (sinon la mesure est vide)"

    gardees_canal = _obscurcies(frm, [to], canal)
    gardees_avant = _obscurcies(frm, [to], avant)
    assert gardees_canal == set(), "canal : la cible doit etre OBSCURCIE (crete a 4, un seul mid)"
    assert gardees_avant == {to}, "bras d'avant : le 0 invente eteignait le blocage"
    assert gardees_canal != gardees_avant                       # le fix MORD, sens RESTRICTIF


# ================================== 2. INCONNUE EN `from` -- le `0` invente FABRIQUE l'obscurcissement

def test_origine_non_captee_le_zero_invente_fabriquait_un_obscurcissement():
    """Cas DROIT (1 candidate). La crete est a 4, la cible a 0, et l'ORIGINE n'est pas captee.

    * canal (fix)   : `ef is None` -> `is_target_tile_obscured` rend `False` -> cible GARDEE.
    * bras d'avant  : `ef = 0` invente -> `4 - 0 >= 2` -> cible EXCLUE, sur une elevation qu'aucun
      capteur n'a mesuree.
    """
    _, (frm, to) = _paire_diagonale()
    (mid,) = _mids(frm, to)
    board = _board(elev={mid: 4}, sans_elevation=[frm])

    canal = elevations_by_pos(board)
    avant = _carte_d_avant(board)
    assert frm not in canal
    assert avant[frm] == 0

    gardees_canal = _obscurcies(frm, [to], canal)
    gardees_avant = _obscurcies(frm, [to], avant)
    assert gardees_canal == {to}, "canal : origine inconnue -> jamais obscurci (borne SUPERIEURE)"
    assert gardees_avant == set(), "bras d'avant : obscurcissement FABRIQUE"
    assert gardees_canal != gardees_avant                       # le fix MORD, sens PERMISSIF


# ================================================ 3. LE NOEUD LUI-MEME, sur un contexte de bout en bout

def test_le_noeud_Unobscured_consomme_le_canal_du_contexte():
    """Meme regime que l'etage 1, mais joue par le NOEUD -- c'est lui le livrable, pas le predicat.

    Le contexte porte le canal (`DslContext.__post_init__` -> `elevations_by_pos(board)`), et la
    cible doit disparaitre de la sortie. Sur le bras d'avant elle y restait.
    """
    (frm, to), _ = _paire_diagonale()
    m0, m1 = _mids(frm, to)
    board = _board(elev={m0: 4}, sans_elevation=[m1])

    caster = _unit(1, 0, frm)
    cible = _unit(2, 1, to)
    ctx = DslContext(units=[caster, cible], caster=caster, board=board)

    assert ctx.elev_by_pos is not None and m1 not in ctx.elev_by_pos

    sortie = Unobscured(Enemies(AllAliveUnits())).select(ctx)
    assert [u["id"] for u in sortie] == [], "le noeud doit EXCLURE la cible obscurcie"

    # contre-epreuve : avec la carte d'AVANT injectee dans le contexte, la cible revient.
    ctx_avant = DslContext(units=[caster, cible], caster=caster, board=board,
                           elev_by_pos=_carte_d_avant(board))
    sortie_avant = Unobscured(Enemies(AllAliveUnits())).select(ctx_avant)
    assert [u["id"] for u in sortie_avant] == [2], "bras d'avant : la cible restait"


# ============================================ 4. LA FORME DU BOARD -- `by_coord` n'etait pas le canal

def test_une_injection_explicite_du_canal_est_desormais_HONOREE():
    """Le bras d'avant re-derivait TOUJOURS depuis `board.by_coord` : un `elev_by_pos` pose
    explicitement dans le contexte etait purement IGNORE. C'est le meme vice, vu par l'autre bout --
    et c'est ce qui rend l'etage 3 possible."""
    # Paire DROITE (un seul mid) : une crete unique y suffit a bloquer. Sur la paire diagonale il
    # en faudrait DEUX (fat-line, `blk = all(...)`) -- piege trouve en jouant ce test.
    _, (frm, to) = _paire_diagonale()
    (mid,) = _mids(frm, to)
    board = _board()                                       # plateau PLAT, aucune crete

    caster = _unit(1, 0, frm)
    cible = _unit(2, 1, to)
    # canal injecte : une crete a 4 que le BOARD ne porte pas.
    ctx = DslContext(units=[caster, cible], caster=caster, board=board,
                     elev_by_pos={**elevations_by_pos(board), mid: 4})

    sortie = Unobscured(Enemies(AllAliveUnits())).select(ctx)
    assert [u["id"] for u in sortie] == [], "l'injection explicite doit gouverner"

    # temoin : sans injection, le plateau est plat -> la cible est gardee. Sans ce temoin, un noeud
    # qui rendrait TOUJOURS vide passerait l'assertion ci-dessus.
    ctx_plat = DslContext(units=[caster, cible], caster=caster, board=board)
    assert [u["id"] for u in Unobscured(Enemies(AllAliveUnits())).select(ctx_plat)] == [2]
