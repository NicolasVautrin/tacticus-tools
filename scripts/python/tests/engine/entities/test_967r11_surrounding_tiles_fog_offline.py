#!/usr/bin/env python3
"""#967-r11 -- le noeud DSL `SurroundingTiles` doit filtrer le FOG, pour TOUTE valeur
d'`includeNonWalkable`, et par un axe DISTINCT de la marchabilite.

RE relue VERBATIM sur `rnca9r7q6c` (`mcp__ghidra__decompile_function`). Meme maillon terminal que
#967-r10, TROISIEME axe :

    `IdunBattle.Core.Services.TileUtil$$IsTileValidForList` :

        if (tileComponent+0x41 != 0)   return false                     # MUR   (#967-r10)
        if (checkWalkability == 0)     return tileComponent+0x40 == 0   # FOG, branche 1
        else                           IsWalkable(tile, tileComponent, tile+0x40,
                                                  checkFog: CONCAT71(checkElevation>>8, 1))

    `IdunBattle.Entities.TileExtensions$$IsWalkable` -- la surcharge a 4 ARGUMENTS (il en existe
    trois, desambiguisees par l'ARITE ; les deux autres prennent `(tile, checkFog)`) :

        if (movement+0x10 != 0)   return false           # MARCHABILITE (`MovementComponent`)
        if (checkFog == 0)        return true
        return tileComponent+0x40 == 0                   # FOG, branche 2 -- MEME octet

=> le FOG coupe dans les DEUX branches, donc INCONDITIONNELLEMENT, exactement comme le mur.
Le litteral `1` du 4e argument est ecrit EN DUR par `IsTileValidForList` (octet bas de
`CONCAT71(checkElevation >> 8, 1)`) : ce n'est PAS `checkElevation` qui pilote `checkFog`.

IDENTITE DE L'OCTET, etablie par LECTURE et non par voisinage de nom (`+0x40` et `+0x41` sont
adjacents, donc les confondre ne leve rien -- le depot les avait justement INVERSES avant
#967-r10) : `IdunBattle.Entities.TileExtensions$$IsInFogOfWar` rend EXACTEMENT
`*(byte*)(comp+0x40)`.

LES TROIS AXES SONT INDEPENDANTS, et c'est le coeur du test :
  * MUR      = `TileComponent+0x40+1`  -> `_is_wall`      -- inconditionnel
  * FOG      = `TileComponent+0x40`    -> `_is_in_fog`    -- inconditionnel
  * MARCHE   = `MovementComponent+0x10`-> `_walkable`     -- arme par `includeNonWalkable == 0`
Fondre FOG et MARCHE laisserait passer 31 tuiles sur 63 du board `C6_02` (mesure #433-r4 :
`walkable == True` ET `isInFog == True`), que le natif COUPE.

SUBSTRAT : `boardGraph` publie `isInFog` PAR TUILE, au meme rang qu'`isWall`
(`frida/hooks/features/ai-step/rpc-board.ts` : `isWall: t.isWall, isInFog: t.isInFog ?? false`),
alimente par `match-state.ts` `COMP_FIELD.tileIsInFog` et deja VERIFIE LIVE par #403 (`C6_02` :
31 tuiles sur 63). Le gate est donc reellement alimentable, sans aucun capteur a poser --
c'est ce qui perime le `BLOCAGE: seeding` de la ligne de backlog.
Cle ABSENTE -> gate INERTE : on ne fabrique jamais un `True` depuis une NON-MESURE.

Offline pur, aucun runner. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

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
    "raison": "Il garde le filtre FOG du noeud DSL `SurroundingTiles` (mirror de "
              "`TileUtil$$IsTileValidForList`) et son independance vis-a-vis des deux autres "
              "axes (mur, marchabilite) : seuls ces deux fichiers peuvent le faire mentir.",
}

# Coordonnees du montage, nommees une fois -- elles sont citees par plusieurs tests.
CENTRE = (2, 2)
MUR = (2, 1)
FOG_ET_MARCHABLE = (1, 2)      # le regime DISCRIMINANT : 31/63 tuiles de `C6_02`
NON_MARCHABLE_SANS_FOG = (3, 2)  # Block/Water : `walkable=False, isWall=False, isInFog=False`


class _Ctx:
    """Contexte minimal : `SurroundingTiles.select` ne lit que `ctx.board`."""
    def __init__(self, board):
        self.board = board


def board_trois_axes(walls=(), fog=(), non_walkable=(), w=5, h=5,
                     avec_cle_isinfog=True, avec_cle_iswall=True):
    """FIXTURE REUTILISABLE -- grille `w x h` en (col,row), id = col * h + row.

    Les trois axes sont poses INDEPENDAMMENT, exactement comme le board natif les publie :
    une tuile peut etre `isInFog` ET `walkable`, ou `walkable=False` sans etre ni mur ni fog
    (Block/Water). `avec_cle_*=False` omet la cle : c'est le board d'un test ancien construit a
    la main, sur lequel le gate correspondant doit rester INERTE.
    """
    tiles = []
    for c in range(w):
        for r in range(h):
            t = {"id": c * h + r, "col": c, "row": r, "elevation": 0,
                 "walkable": (c, r) not in non_walkable, "neighbours": []}
            if avec_cle_iswall:
                t["isWall"] = (c, r) in walls
            if avec_cle_isinfog:
                t["isInFog"] = (c, r) in fog
            tiles.append(t)
    return Board(tiles, adjacency="evenq")


@pytest.fixture(name="board_fog")
def _fixture_board_fog():
    """Le montage NON DEGENERE de reference : les trois axes armes sur trois tuiles distinctes de
    l'anneau-1 du centre, plus trois tuiles ordinaires -- donc un disque qui reste NON VIDE apres
    tous les filtres, et qui DISCRIMINE (retirer un axe change l'ensemble)."""
    return board_trois_axes(walls={MUR}, fog={FOG_ET_MARCHABLE},
                            non_walkable={NON_MARCHABLE_SANS_FOG})


def selectionner(board, centre, radius, **kw):
    """Monte le noeud sur un centre donne et rend la liste de tile ids qu'il selectionne."""
    tid = board.id_at(*centre)
    node = SurroundingTiles(FixedTileIds([tid]), Const(radius), **kw)
    return list(node.select(_Ctx(board)))


def _ids(board, coords):
    return {board.id_at(c, r) for (c, r) in coords}


# --------------------------------------------------------------------------------------------
# Le coeur du residu : le fog sort, pour les DEUX valeurs d'`includeNonWalkable`.
# --------------------------------------------------------------------------------------------

def test_fog_exclu_avec_include_non_walkable_true(board_fog):
    """`includeNonWalkable = 1` -> `checkWalkable = 0` -> la branche
    `if (checkWalkability == 0) return tileComponent+0x40 == 0` s'applique : le fog coupe SEUL,
    sans meme passer par `IsWalkable`.

    C'est la valeur que portent 5 des 6 call-sites du noeud (le defaut) -- donc le regime ou le
    port ne filtrait le fog NULLE PART."""
    got = selectionner(board_fog, CENTRE, 1, include_center=False, include_non_walkable=True)
    tuile_fog = board_fog.id_at(*FOG_ET_MARCHABLE)
    assert tuile_fog not in got, (
        "une tuile EN BROUILLARD est entree dans le disque SurroundingTiles alors que "
        "`TileUtil$$IsTileValidForList` rend `tileComponent+0x40 == 0` dans cette branche : %r"
        % (got,))
    # temoin NON NUL : le disque n'est pas vide par accident de montage
    assert len(got) >= 3, "montage degenere : le disque ne porte que %d tuiles" % len(got)


def test_fog_exclu_avec_include_non_walkable_false(board_fog):
    """L'autre valeur (`ThriceBlessedConflagrationAbility`, le seul call-site a la poser) : le fog
    sort AUSSI, et par l'autre branche -- `IsWalkable(..., checkFog: 1)`, dont le litteral `1` est
    ecrit en dur par l'appelant."""
    got = selectionner(board_fog, CENTRE, 1, include_center=False, include_non_walkable=False)
    assert board_fog.id_at(*FOG_ET_MARCHABLE) not in got, (
        "fog garde sous includeNonWalkable=False : %r" % (got,))
    assert got, "montage degenere : disque vide"


def test_fog_et_marchabilite_sont_deux_axes_distincts(board_fog):
    """LE discriminant du residu. La tuile en fog du montage est `walkable = True` : le gate
    walkable est DESARME (`includeNonWalkable = True`) et ne peut donc pas l'avoir retiree.
    Seul un gate FOG propre l'explique.

    Regime mesure sur un board reel : `C6_02` porte **31 tuiles sur 63** qui sont `walkable` ET
    `isInFog` (#433-r4). Sans axe fog separe, ces 31 tuiles entrent dans tous les disques."""
    tuile = board_fog.id_at(*FOG_ET_MARCHABLE)
    assert board_fog.walkable(tuile) is True, (
        "montage invalide : la tuile de fog doit etre MARCHABLE pour que le test discrimine")
    got = selectionner(board_fog, CENTRE, 1, include_center=False, include_non_walkable=True)
    assert tuile not in got, (
        "la tuile `walkable=True, isInFog=True` est restee : le gate fog n'existe pas, ou il a "
        "ete rabattu sur la marchabilite. Obtenu : %r" % (got,))


def test_non_marchable_sans_fog_reste_quand_le_gate_walkable_est_desarme(board_fog):
    """Contre-epreuve symetrique, et ce qui interdit de rabattre le fog sur `not walkable` : une
    tuile `walkable=False, isWall=False, isInFog=False` (Block, Water) RESTE dans le disque quand
    `includeNonWalkable = 1`. Le natif ne coupe alors ni sur `+0x41` ni sur `+0x40`, et
    `IsWalkable` n'est meme pas appele.

    C'est le regime que le GROUND TRUTH d'`astramilitarum.py` mesure (board `C3_01` : 14 tuiles
    dans ce cas, dont une recoit un obus en live)."""
    got = selectionner(board_fog, CENTRE, 1, include_center=False, include_non_walkable=True)
    assert board_fog.id_at(*NON_MARCHABLE_SANS_FOG) in got, (
        "une tuile non-walkable, NI mur NI fog, a ete retiree : un des trois filtres a fondu "
        "deux axes. Obtenu : %r" % (got,))


def test_les_trois_axes_coupent_chacun_leur_tuile(board_fog):
    """Les trois axes ensemble, sur le MEME disque : sous `includeNonWalkable = False` les trois
    gates sont armes, et chacun retire SA tuile. Sans ce test, un fix qui aurait casse le gate
    mur ou le gate walkable passerait les tests fog."""
    got = set(selectionner(board_fog, CENTRE, 1, include_center=False,
                           include_non_walkable=False))
    for nom, coord in (("MUR", MUR), ("FOG", FOG_ET_MARCHABLE),
                       ("NON MARCHABLE", NON_MARCHABLE_SANS_FOG)):
        assert board_fog.id_at(*coord) not in got, (
            "l'axe %s ne coupe plus : %r" % (nom, sorted(got)))
    # temoin NON NUL : il reste des tuiles -- un ensemble vide validerait tout
    assert got, "montage degenere : les trois filtres ont tout retire, aucun temoin"


def test_gate_inerte_si_le_board_ne_publie_pas_isinfog():
    """Board sans la cle `isInFog` (test unitaire ancien, board construit a la main) : le gate est
    INERTE, l'ensemble est celui d'AVANT. Un `True` fabrique depuis une NON-MESURE retirerait des
    tuiles que le natif garde -- meme doctrine que `_is_wall` et `_walkable`."""
    b_sans = board_trois_axes(fog={FOG_ET_MARCHABLE}, avec_cle_isinfog=False)
    b_avec = board_trois_axes(fog=set(), avec_cle_isinfog=True)
    got_sans = selectionner(b_sans, CENTRE, 1, include_center=False, include_non_walkable=True)
    got_avec = selectionner(b_avec, CENTRE, 1, include_center=False, include_non_walkable=True)
    assert set(got_sans) == set(got_avec), (
        "l'absence de la cle `isInFog` a fait couper des tuiles : %r vs %r"
        % (sorted(got_sans), sorted(got_avec)))
    assert got_sans, "montage degenere : disque vide des deux cotes"


def test_le_centre_en_fog_sort_aussi_sous_include_center():
    """`includeCenter = 1` ne contourne pas le filtre : la triple boucle cube de
    `TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` emet le centre comme les autres et
    le fait passer par le MEME `IsTileValidForList` -- seul le gate `tile != origin` est
    conditionne par `includeSelf`."""
    b = board_trois_axes(fog={CENTRE})
    got = selectionner(b, CENTRE, 1, include_center=True, include_non_walkable=True)
    assert b.id_at(*CENTRE) not in got, (
        "le centre EN BROUILLARD est reste sous includeCenter=1 : %r" % (got,))
    assert got, "montage degenere : disque vide"


def test_disque_sans_fog_est_inchange():
    """Non-regression du rayon de souffle : sur un board SANS fog, le fix ne retire rien --
    l'ensemble ET l'ORDRE (cube-lexicographique, tie-break de `SortByFormula`) sont ceux d'avant.
    C'est ce qui rend le correctif value-preserving pour les 6 call-sites tant qu'aucune tuile
    n'est en brouillard."""
    b = board_trois_axes(fog=set())
    got = selectionner(b, CENTRE, 1, include_center=False, include_non_walkable=True)
    # voisinage even-q d'une colonne PAIRE : (-1,0)(-1,1)(0,-1)(0,1)(1,0)(1,1) autour de (2,2)
    attendu = _ids(b, {(1, 2), (1, 3), (2, 1), (2, 3), (3, 2), (3, 3)})
    assert set(got) == attendu, "disque altere sur un board sans fog : %r vs %r" % (
        sorted(got), sorted(attendu))


def test_fog_coupe_au_rayon_2_aussi():
    """Le gate vit dans la boucle du disque, pas dans un cas particulier du rayon 1 : au rayon 2
    (le rayon que portent `SurroundingUnits(..., 2, ...)` et `bespoke`), la tuile en fog de
    l'anneau-2 sort elle aussi."""
    loin = (0, 2)     # a distance hex 2 de (2,2) en even-q
    b = board_trois_axes(fog={loin})
    got = selectionner(b, CENTRE, 2, include_center=False, include_non_walkable=True)
    assert b.id_at(*loin) not in got, "fog de l'anneau-2 garde : %r" % (sorted(got),)
    assert len(got) > 6, "montage degenere : le disque r=2 ne depasse pas l'anneau-1 (%d)" % len(got)
