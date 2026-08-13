"""#967-r2 -- le 5e argument de `DSLSelectors$$SurroundingTiles` (`includeNonWalkable`) MORD.

CE QUE LA GARDE TIENT, ET POURQUOI CHAQUE ETAGE EXISTE
------------------------------------------------------
Le residu disait : << le 5e argument est LU et NON MAPPE, et il DIFFERE entre 1213 et 1187 ; l'ecart
est soit inerte sur les regimes joues, soit masque -- non tranche >>. La lecture VERBATIM sur
`rnca9r7q6c` le tranche :

    `IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles(this, origin, includeCenter, range,
                                                            onlyMovable, includeNonWalkable)`
    -> `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$.ctor` : `this+0x29 = includeNonWalkable`
    -> `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select` : appelle le slot
       d'`IBattleQuery` avec `checkWalkable = (this+0x29 == 0)`

Donc `includeNonWalkable == 0` ARME le filtre de marchabilite. `ThriceBlessedConflagrationAbility$$
GetTilesInBestLine` (1187) passe `0` ; `DeathOnTheWindAbility$$GetMachineAttackTiles` (1213) passe
`1`. Les quatre etages ci-dessous gardent, dans l'ordre : que le parametre MORD, que son DEFAUT ne
change rien, que le call-site 1187 le POSE, et que les DEUX FACES de 1187 s'accordent.

⚠ L'etage 4 est le seul qui aurait vu le bug : les etages 1-3 restent verts si l'on cable le
parametre sans le poser au call-site COMBAT. C'est un ecart de FACE, invisible d'un test qui
n'interroge qu'un cote.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.dsl.base import Const                              # noqa: E402
from engine.entities.selectors.accessors import SurroundingTiles   # noqa: E402


# --- FIXTURE NOMMEE : un board minimal ou la marchabilite DISCRIMINE ----------------------------
#
# Damier 5x5 hex plat. La couronne r=1 du centre (2,2) porte SIX voisins ; on en rend DEUX non
# marchables. Sans le filtre le ring en compte 6, avec le filtre 4 -- un temoin NON NUL des deux
# cotes (un ring vide, ou un ring inchange, ne departagerait rien).

class _Board:
    """Duck-type du board du DSL : `id_at(col,row)`, `walkable(tid)`, `tile_at`. MEME surface que
    `engine.entities.pathfinding.board.Board`, reduite a ce que le noeud consomme."""

    def __init__(self, non_walkable: "set|None" = None):
        self.by_pos = {}
        self.pos_by_id = {}
        tid = 1
        for col in range(5):
            for row in range(5):
                self.by_pos[(col, row)] = tid
                self.pos_by_id[tid] = (col, row)
                tid += 1
        self.non_walkable = set(non_walkable or ())

    def id_at(self, col, row):
        return self.by_pos.get((col, row))

    def tile_at(self, col, row):
        t = self.id_at(col, row)
        return None if t is None else {"id": t, "col": col, "row": row}

    def walkable(self, tid) -> bool:
        return self.pos_by_id.get(tid) not in self.non_walkable


class _Ctx:
    def __init__(self, board, center):
        self.board = board
        self._center = center

    # Le noeud evalue `self.center` ; un selecteur constant suffit ici.
    @property
    def center(self):
        return self._center


class _Pos:
    """Selecteur de centre : rend un couple (col,row), la forme que `SurroundingTiles` accepte."""

    def __init__(self, pos):
        self.pos = pos

    def evaluate(self, ctx):
        return self.pos


CENTRE = (2, 2)


def _ring(board, include_non_walkable):
    node = SurroundingTiles(_Pos(CENTRE), Const(1), include_center=False,
                            include_non_walkable=include_non_walkable)
    return list(node.select(_Ctx(board, CENTRE)))


def _voisins_du_centre():
    """Les positions du disque r=1 autour du centre, centre EXCLU -- derivees du noeud lui-meme sur
    un board SANS obstacle, jamais recopiees a la main (une liste figee se perimerait avec
    `hexgeo.disk`)."""
    plein = _Board()
    ids = _ring(plein, include_non_walkable=True)
    return [plein.pos_by_id[t] for t in ids]


def test_etage1_le_parametre_mord():
    """Poser `include_non_walkable=False` RETIRE les tuiles non marchables -- et le temoin est NON
    NUL des deux cotes (sinon la comparaison ne prouverait rien)."""
    voisins = _voisins_du_centre()
    assert len(voisins) >= 3, "board temoin degenere : %d voisins" % len(voisins)
    bloquees = set(voisins[:2])
    board = _Board(non_walkable=bloquees)

    sans = _ring(board, include_non_walkable=True)     # `includeNonWalkable = 1` -> aucun filtre
    avec = _ring(board, include_non_walkable=False)    # `includeNonWalkable = 0` -> filtre ARME

    assert len(sans) == len(voisins), "le defaut ne doit RIEN filtrer : %d != %d" % (
        len(sans), len(voisins))
    assert len(avec) == len(voisins) - len(bloquees), (
        "filtre arme : attendu %d tuiles, obtenu %d" % (len(voisins) - len(bloquees), len(avec)))
    assert avec, "temoin DEGENERE : le ring filtre est VIDE, il ne discrimine rien"
    retirees = {board.pos_by_id[t] for t in sans} - {board.pos_by_id[t] for t in avec}
    assert retirees == bloquees, "retirees=%s attendu=%s" % (sorted(retirees), sorted(bloquees))


def test_etage2_le_defaut_est_non_regressif():
    """Le defaut vaut `includeNonWalkable = 1` : sur un board PORTANT des tuiles non marchables, le
    ring par defaut est IDENTIQUE a celui d'un board sans obstacle. C'est ce qui garantit que les
    call-sites qui ne nomment pas le parametre n'ont pas bouge."""
    voisins = _voisins_du_centre()
    board = _Board(non_walkable=set(voisins[:2]))
    assert _ring(board, include_non_walkable=True) == _ring(_Board(), include_non_walkable=True)


def test_etage3_le_call_site_1187_pose_le_litteral_zero():
    """La face COMBAT de 1187 (`ThriceBlessedConflagrationAbility$$GetTilesInBestLine`) doit POSER
    `include_non_walkable=False` -- le litteral `0` LU au decompile. Un cablage sans pose laisserait
    les etages 1-2 verts et le bug entier."""
    from engine.runner.abilities import sisterhood
    ring = sisterhood.thrice_blessed_get_tiles_in_best_line()
    trouve = _chercher_surrounding(ring)
    assert trouve is not None, "aucun noeud SurroundingTiles dans l'arbre de 1187"
    assert trouve.include_non_walkable is False, (
        "1187 doit ARMER le filtre (`includeNonWalkable: 0` au decompile), or il vaut %r"
        % trouve.include_non_walkable)


def _chercher_surrounding(node, vus=None):
    """Parcours de l'arbre DSL a la recherche du premier `SurroundingTiles`. Generique (attributs)
    plutot qu'une liste de champs : la forme de l'arbre de 1187 peut bouger sans que ce test doive
    la connaitre."""
    vus = vus if vus is not None else set()
    if id(node) in vus:
        return None
    vus.add(id(node))
    if isinstance(node, SurroundingTiles):
        return node
    for nom in dir(node):
        if nom.startswith("__"):
            continue
        try:
            v = getattr(node, nom)
        except Exception:
            continue
        if callable(v):
            continue
        cands = v if isinstance(v, (list, tuple)) else [v]
        for c in cands:
            if hasattr(c, "__dict__"):
                r = _chercher_surrounding(c, vus)
                if r is not None:
                    return r
    return None


def test_etage4_les_deux_faces_de_1187_s_accordent():
    """LE seul etage qui voit le bug DE BOUT EN BOUT : la face DECISION de 1187 posait DEJA
    `check_walkable=True` (`playbook/noncomparable/thrice_blessed_conflagration.py::
    _best_line_direction` -> `bq.get_surrounding_tiles(..., check_walkable=True, ...)`), la face
    COMBAT ne filtrait rien. Sur un MEME board porteur de tuiles non marchables, les deux rings
    doivent coincider.

    ⚠ Le ring COMBAT est EXTRAIT DE L'ARBRE REEL de 1187, jamais reconstruit : une premiere version
    de cet etage fabriquait son propre noeud `SurroundingTiles(..., include_non_walkable=False)` et
    restait donc VERTE quand on retirait le litteral du call-site -- un declencheur trop etroit,
    vert sur le bug meme qu'il pretend garder. Mesure de la mutation adversariale : etage 3 ROUGE,
    etage 4 VERT. Il est desormais ROUGE lui aussi."""
    from engine import battle_query as bq
    from engine.runner.abilities import sisterhood
    voisins = _voisins_du_centre()
    bloquees = set(voisins[:2])
    board = _Board(non_walkable=bloquees)

    # face DECISION : le foyer que le playbook appelle, avec SES accesseurs.
    walkable_by_pos = {p: (p not in bloquees) for p in board.by_pos}
    decision = set(bq.get_surrounding_tiles(
        CENTRE, radius=1, include_center=False, check_walkable=True,
        walkable_at=lambda p: walkable_by_pos.get((p[0], p[1]), True),
        elevation_at=None, tile_exists=lambda p: (p[0], p[1]) in board.by_pos))

    # face COMBAT : LE noeud de l'arbre de 1187, evalue sur le MEME board.
    noeud = _chercher_surrounding(sisterhood.thrice_blessed_get_tiles_in_best_line())
    assert noeud is not None, "aucun noeud SurroundingTiles dans l'arbre de 1187"
    reel = SurroundingTiles(_Pos(CENTRE), Const(1), include_center=noeud.include_center,
                            include_non_walkable=noeud.include_non_walkable)
    combat = {board.pos_by_id[t] for t in reel.select(_Ctx(board, CENTRE))}

    assert decision, "temoin DEGENERE cote DECISION : ring vide"
    non_filtre = {board.pos_by_id[t] for t in _ring(_Board(), include_non_walkable=True)}
    assert combat != non_filtre, (
        "la face COMBAT de 1187 n'a RIEN filtre : son ring (%s) est celui d'un board SANS obstacle,"
        " alors que %s sont non marchables" % (sorted(combat), sorted(bloquees)))
    assert combat == decision, (
        "FORK prediction/combat sur le ring de 1187 : combat=%s decision=%s"
        % (sorted(combat), sorted(decision)))
