#!/usr/bin/env python3
"""#967-r10 -- le noeud DSL `SurroundingTiles` doit filtrer les MURS, pour TOUTE valeur
d'`includeNonWalkable`.

RE relue VERBATIM sur `rnca9r7q6c` (`mcp__ghidra__decompile_function`). La chaine complete,
maillon par maillon -- elle est ecrite ici parce que l'enonce du residu ne citait que le
DERNIER maillon, et qu'une citation qui saute un etage est exactement ce qui a fait porter
#948-r1 sur le mauvais symbole :

    `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select`
        -> slot **102** d'`IBattleQuery` (`IterateSurroundingTiles`, lu dans
           `data/symbols/<build>/metadata/interface_slots.tsv`), avec
           `checkWalkable = (this+0x29 == 0)` -- c'est le mapping d'`includeNonWalkable` de #967-r2
    `IdunBattle.Core.Services.BattleQuery.u003CIterateSurroundingTilesu003Ed__117$$MoveNext`
        -> `EntityExtensions.IterateTiles(center)` puis le slot d'`ITileQuery`
    `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`
        -> triple boucle cube ascendante, puis
           `TileUtil$$IsTileValidForList(tile, originTile, checkWalkability, checkElevation: 0)`

et le corps du maillon terminal, `IdunBattle.Core.Services.TileUtil$$IsTileValidForList` :

    if (tileComponent+0x41 != 0)   return false          # MUR -- AVANT tout test de walkability
    if (!checkWalkability)         return tileComponent+0x40 == 0
    ...                            IsWalkable(tile, checkFog: 1)

IDENTITE DES DEUX DRAPEAUX, etablie par LECTURE et non par voisinage de nom (les deux octets sont
adjacents, donc les confondre ne leve rien) :
  * `+0x41` = **IsWall** : `IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsAnyAdjacentTileWall`
    rend `true` sur `*(char*)(comp+0x41) != 0`, et rien d'autre ;
  * `+0x40` = **IsInFogOfWar** : `IdunBattle.Entities.TileExtensions$$IsInFogOfWar` rend
    EXACTEMENT `*(byte*)(comp+0x40)`.

=> le filtre MUR est INCONDITIONNEL : `includeNonWalkable = 1` desarme la marchabilite, jamais le
mur. Le port, lui, construisait un disque `hexgeo.disk` PUR.

SUBSTRAT : `boardGraph` publie `isWall` PAR TUILE (`frida/hooks/game/match-state.ts` le lit dans
`COMP_FIELD.tileIsWall`), DISTINCT de `walkable`. Le gate est donc reellement alimentable offline.
La cle ABSENTE laisse le gate INERTE -- meme doctrine que `_walkable` : on ne fabrique jamais un
`False` depuis une NON-MESURE. On ne passe volontairement PAS par `Board.is_wall()`, dont le repli
documente est `not walkable` : ce repli FOND les deux axes, et l'emprunter ferait retirer des
tuiles non-walkables aux 5 call-sites qui gardent `includeNonWalkable = True` -- une seconde
erreur, pas une correction.

Offline pur, aucun runner. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.pathfinding.board import Board            # noqa: E402
from engine.entities.selectors.accessors import (              # noqa: E402
    FixedTileIds, SurroundingTiles,
)
from engine.dsl.base import Const                              # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/entities/selectors/accessors.py",
                "scripts/python/engine/entities/pathfinding/board.py"),
    "build": False,
    "toujours": False,
    "raison": "Il garde le filtre MUR du noeud DSL `SurroundingTiles` (mirror de "
              "`TileUtil$$IsTileValidForList`) et le substrat `isWall` du board qui l'alimente : "
              "seuls ces deux fichiers peuvent le faire mentir.",
}


class _Ctx:
    """Contexte minimal : `SurroundingTiles.select` ne lit que `ctx.board`."""
    def __init__(self, board):
        self.board = board


def _board(walls=(), non_walkable=(), w=5, h=5, with_iswall_key=True):
    """Grille `w x h` en coordonnees (col,row), id = col * h + row.

    `walls` / `non_walkable` : ensembles de (col,row). Les deux axes sont INDEPENDANTS -- c'est
    precisement ce que le board natif publie (une tuile `Block`/`Water` est `walkable=False` et
    `isWall=False` ; cf. la docstring de `Board.is_wall`).
    `with_iswall_key=False` omet la cle `isWall` : c'est le board d'un test unitaire ancien, sur
    lequel le gate doit rester INERTE.
    """
    tiles = []
    for c in range(w):
        for r in range(h):
            t = {"id": c * h + r, "col": c, "row": r, "elevation": 0,
                 "walkable": (c, r) not in non_walkable, "neighbours": []}
            if with_iswall_key:
                t["isWall"] = (c, r) in walls
            tiles.append(t)
    return Board(tiles, adjacency="evenq")


def _ids(board, coords):
    return {board.id_at(c, r) for (c, r) in coords}


def _select(board, center_coord, radius, **kw):
    tid = board.id_at(*center_coord)
    node = SurroundingTiles(FixedTileIds([tid]), Const(radius), **kw)
    return list(node.select(_Ctx(board)))


# --------------------------------------------------------------------------------------------
# Le coeur du residu : le mur sort, pour les DEUX valeurs d'`includeNonWalkable`.
# --------------------------------------------------------------------------------------------

def test_mur_exclu_meme_avec_include_non_walkable_true():
    """`includeNonWalkable = 1` -> `checkWalkable = 0` -> la branche
    `if (tileComponent+0x41 != 0) return false` d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList`
    s'applique QUAND MEME : elle est en AMONT du test `checkWalkability`.

    C'est la valeur que portent 5 des 6 call-sites du noeud (le defaut) -- donc le regime ou le
    port ne filtrait ABSOLUMENT rien."""
    b = _board(walls={(2, 1)})
    got = _select(b, (2, 2), 1, include_center=False, include_non_walkable=True)
    mur = b.id_at(2, 1)
    assert mur not in got, (
        "un MUR est entre dans le disque SurroundingTiles alors que "
        "`TileUtil$$IsTileValidForList` le rejette AVANT le test `checkWalkability` : %r" % (got,))
    # temoin NON NUL : le disque n'est pas vide par accident de montage
    assert len(got) >= 4, "montage degenere : le disque ne porte que %d tuiles" % len(got)


def test_mur_exclu_avec_include_non_walkable_false():
    """L'autre valeur (`ThriceBlessedConflagrationAbility`, le seul call-site a la poser) : le mur
    sort AUSSI, et par la meme porte -- pas par la porte walkable."""
    b = _board(walls={(2, 1)})
    got = _select(b, (2, 2), 1, include_center=False, include_non_walkable=False)
    assert b.id_at(2, 1) not in got, "mur garde sous includeNonWalkable=False : %r" % (got,)


def test_les_deux_axes_sont_independants_non_walkable_reste():
    """LE discriminant du residu, et ce qui interdit d'emprunter `Board.is_wall()` : une tuile
    `walkable = False` / `isWall = False` (Block, Water) reste DANS le disque quand
    `includeNonWalkable = 1`. Fondre les deux axes la retirerait -- c'est le regime que le
    GROUND TRUTH d'`astramilitarum.py` mesure (board `C3_01` : 14 tuiles walkable=false /
    isWall=false, et le LIVE fait tomber un obus sur l'une d'elles)."""
    b = _board(walls={(2, 1)}, non_walkable={(3, 2)})
    got = _select(b, (2, 2), 1, include_center=False, include_non_walkable=True)
    assert b.id_at(3, 2) in got, (
        "une tuile non-walkable mais NON MUR a ete retiree : le filtre a fondu les deux axes, "
        "alors que le natif ne coupe que sur `+0x41`. Obtenu : %r" % (got,))
    assert b.id_at(2, 1) not in got, "mur garde : %r" % (got,)


def test_walkable_gate_mord_toujours_quand_arme():
    """Contre-epreuve du precedent : sous `includeNonWalkable = False`, la MEME tuile
    non-walkable, elle, sort. Sans ce test, le precedent passerait aussi si le gate walkable
    avait ete casse par le fix."""
    b = _board(walls={(2, 1)}, non_walkable={(3, 2)})
    got = _select(b, (2, 2), 1, include_center=False, include_non_walkable=False)
    assert b.id_at(3, 2) not in got, "le gate walkable ne mord plus : %r" % (got,)


def test_gate_inerte_si_le_board_ne_publie_pas_iswall():
    """Board sans la cle `isWall` (test unitaire ancien, board construit a la main) : le gate est
    INERTE, l'ensemble est celui d'AVANT. Un `False` fabrique depuis une NON-MESURE retirerait des
    tuiles que le natif garde."""
    b_sans = _board(walls={(2, 1)}, with_iswall_key=False)
    b_avec = _board(walls=set(), with_iswall_key=True)
    got_sans = _select(b_sans, (2, 2), 1, include_center=False, include_non_walkable=True)
    got_avec = _select(b_avec, (2, 2), 1, include_center=False, include_non_walkable=True)
    assert set(got_sans) == set(got_avec), (
        "l'absence de la cle `isWall` a fait couper des tuiles : %r vs %r" % (got_sans, got_avec))


def test_le_centre_mur_sort_aussi_sous_include_center():
    """`includeCenter = 1` ne contourne pas le filtre : le natif fait passer le centre par le MEME
    `IsTileValidForList` (la triple boucle cube emet le centre comme les autres, seul le gate
    `tile != origin` est conditionne par `includeSelf`)."""
    b = _board(walls={(2, 2)})
    got = _select(b, (2, 2), 1, include_center=True, include_non_walkable=True)
    assert b.id_at(2, 2) not in got, "le centre MUR est reste sous includeCenter=1 : %r" % (got,)
    assert got, "montage degenere : disque vide"


def test_disque_sans_mur_est_inchange():
    """Non-regression : sur un board SANS mur, le fix ne retire rien -- l'ensemble et l'ORDRE
    (cube-lexicographique, tie-break de `SortByFormula`) sont ceux d'avant."""
    b = _board(walls=set())
    got = _select(b, (2, 2), 1, include_center=False, include_non_walkable=True)
    # voisinage even-q d'une colonne PAIRE : (-1,0)(-1,1)(0,-1)(0,1)(1,0)(1,1) autour de (2,2)
    attendu = _ids(b, {(1, 2), (1, 3), (2, 1), (2, 3), (3, 2), (3, 3)})
    assert set(got) == attendu, "disque altere sur un board sans mur : %r vs %r" % (
        sorted(got), sorted(attendu))
