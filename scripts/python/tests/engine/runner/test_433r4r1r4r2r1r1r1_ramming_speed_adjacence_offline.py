"""#433-r4-r1-r4-r2-r1-r1-r1 -- `RammingSpeed` decide-t-elle l'adjacence par le SUBSTRAT NATIF ?

LE VICE. `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetDynamicInvalidTargetReason`
decide `isAdjacent` par le slot 0x61 d'`IBattleQuery` = `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`
-> `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(IList, IList)` -> la primitive scalaire
`(|dElev| < 2) & (t1 == t2 || IdunBattle.Entities.Components.ConnectivityComponent$$IsNeighbour(t1, t2))`.
Le port ecrivait `hexgeo.distance(cp, tp) == 1` : TROIS ecarts, tous PERMISSIFS, et ce fichier les
isole UN PAR UN.

  A. LISTE STOCKEE  -- deux tuiles hex-voisines dont l'arete est ABSENTE du `ConnectivityComponent`.
  B. ELEVATION      -- deux tuiles hex-voisines separees de `|dElev| >= 2`.
  C. EMPREINTES     -- cible MULTI-HEX, adjacente par un pied qui n'est PAS sa main tile.

L'OBSERVABLE, et pourquoi il faut faire BOUGER le caster. La valeur rendue par le mirror ne
distingue pas les deux modeles quand le caster n'a pas bouge : `isAdjacent = faux` mene alors a la
branche de charge, qui rend `0` des qu'une tuile de charge existe -- soit la MEME valeur que
`isAdjacent = vrai`. Un caster qui a DEJA bouge separe les deux modeles a coup sur :

    isAdjacent = vrai  -> 0                          (deja au contact, aucun gate)
    isAdjacent = faux  -> 0x10 `CasterHasNotMoved`   (`movedOrOffTile && !isAdjacent`)

Les axes A et B rendent donc `0` APRES le correctif la ou le port d'AVANT rendait... l'inverse :
c'est le port d'AVANT qui croyait les entites adjacentes (couronne hex permissive) et rendait `0`,
tandis que le natif -- et le port corrige -- rendent `0x10`. L'axe C est dans l'autre SENS (le port
d'avant ratait une adjacence par pied secondaire). Les deux sens sont exerces, ce qui interdit
qu'un correctif « toujours vrai » ou « toujours faux » passe.

CONTRE-EPREUVE. Chaque axe rejoue le bras d'AVANT en substituant le foyer d'adjacence par le
predicat main-tile-hex EXACT qui etait ecrit dans `orks.py` -- et exige que le verdict BASCULE.
Sur une contre-epreuve, le VERT est le resultat suspect : un test qui passerait dans les deux bras
ne mesurerait rien.

100 % OFFLINE, board synthetique, aucun runner. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                        # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities import orks as ORKS                     # noqa: E402
from engine.runner.abilities.orks import RammingSpeedAbility         # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.components import set_moved_flag, set_unit_feet   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

COLS, ROWS = 9, 9
CASTER_ID, TARGET_ID, ALLY_ID = 10, 20, 40
CASTER_VIS, TARGET_VIS, ALLY_VIS = "orksKillaKan", "necroWarden", "astraBullgryn"
NO_RULE = 0


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles(elev=None, coupe=()) -> list:
    """Board 9x9. `elev` = {(col,row): elevation} ; `coupe` = paires de positions dont l'arete est
    RETIREE du champ `neighbours` (= le `ConnectivityComponent` que lit `IsNeighbour`).

    Le champ `neighbours` est la SOURCE du mode `native_sym`, celui de la PRODUCTION : couper une
    arete ici, c'est exactement ce que fait un board reel ou `TileComponent$$HasEdge` refuse d'un
    cote (mesure #433-r4-r1-r4-r2 : 4 aretes sur `C1_74`, 38 sur `C3_14`)."""
    elev = elev or {}
    coupees = set()
    for (a, b) in coupe:
        coupees.add((_tid(*a), _tid(*b)))
        coupees.add((_tid(*b), _tid(*a)))
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            me = _tid(col, row)
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS and (me, _tid(c, r)) not in coupees]
            out.append({"id": me, "col": col, "row": row,
                        "elevation": int(elev.get((col, row), 0)),
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _state(board, caster_pos, target_pos, target_feet=None, ally_pos=(8, 8)):
    decision = {
        "currentPlayer": 1,
        "units": [
            {"id": CASTER_ID, "visualId": CASTER_VIS, "alive": True, "team": 1, "owner": 1,
             "pos": {"col": caster_pos[0], "row": caster_pos[1]}, "effects": []},
            {"id": ALLY_ID, "visualId": ALLY_VIS, "alive": True, "team": 1, "owner": 1,
             "pos": {"col": ally_pos[0], "row": ally_pos[1]}, "effects": []},
            {"id": TARGET_ID, "visualId": TARGET_VIS, "alive": True, "team": 2, "owner": 2,
             "pos": {"col": target_pos[0], "row": target_pos[1]}, "effects": []},
        ],
    }
    observe = {"units": [{"squadId": u["id"], "hp": 100000, "hpMax": 100000}
                         for u in decision["units"]]}
    st = load_state(decision, observe, board=board)
    if target_feet:
        set_unit_feet(st, TARGET_ID, [tuple(f) for f in target_feet])
    return st


def _reason(state, *, moved: bool) -> int:
    """Le verdict du mirror, caster ayant bouge ou non."""
    if moved:
        set_moved_flag(state, CASTER_ID)
    return int(RammingSpeedAbility().get_dynamic_invalid_target_reason(state, CASTER_ID, TARGET_ID))


def _bras_avant(monkeypatch):
    """Rejoue EXACTEMENT le predicat d'avant le correctif : `hexgeo.distance(cp, tp) == 1` sur les
    deux MAIN TILES, sans liste stockee ni porte d'elevation.

    On substitue le foyer tel qu'`orks.py` le voit (`ORKS.are_entities_adjacent`), et le nouveau
    corps ignore le `board` : c'est la definition litterale du bras d'avant."""
    def _main_tile_hex(feet_a, feet_b, board=None):
        if not feet_a or not feet_b:
            return False
        return hexgeo.distance(tuple(feet_a[0]), tuple(feet_b[0])) == 1
    monkeypatch.setattr(ORKS, "are_entities_adjacent", _main_tile_hex)


# ------------------------------------------------------------------ montages, un par axe

@pytest.fixture
def axe_liste_stockee():
    """(4,4) et (4,5) sont hex-voisines, mais l'arete est RETIREE de la liste stockee."""
    caster, target = (4, 4), (4, 5)
    board = Board(_tiles(coupe=[(caster, target)]), adjacency="native_sym")
    assert hexgeo.distance(caster, target) == 1, "montage DEGENERE : pas hex-voisines"
    assert _tid(*target) not in board.neighbours(_tid(*caster)), "l'arete n'a pas ete coupee"
    return board, caster, target


@pytest.fixture
def axe_elevation():
    """(4,4) et (4,5) sont hex-voisines ET dans la liste stockee, mais a 2 crans d'elevation."""
    caster, target = (4, 4), (4, 5)
    board = Board(_tiles(elev={target: 2}), adjacency="native_sym")
    assert _tid(*target) in board.neighbours(_tid(*caster)), "montage DEGENERE : arete absente"
    assert abs(board.elevation(_tid(*caster)) - board.elevation(_tid(*target))) >= 2
    return board, caster, target


@pytest.fixture
def axe_empreintes():
    """Cible a TROIS pieds ; le caster touche `feet[1]` et est a distance >= 2 de `feet[0]`.

    Quel que soit le pied qu'un port mono-tuile retienne, il conclut « pas adjacent » la ou le natif
    conclut « adjacent » -- c'est le critere de discriminance de #433-r3-r1."""
    board = Board(_tiles(), adjacency="native_sym")
    feet = [(1, 4), (4, 4), (7, 4)]     # le pied qui touche est celui du MILIEU
    caster = (4, 5)
    return board, caster, feet


# ------------------------------------------------------------------ A -- la liste stockee

def test_axeA_liste_stockee_le_port_suit_le_natif(axe_liste_stockee):
    """Arete absente de la liste stockee -> `IsNeighbour` faux -> `isAdjacent` faux -> `0x10`."""
    board, caster, target = axe_liste_stockee
    st = _state(board, caster, target)
    assert _reason(st, moved=True) == int(TR.CasterHasNotMoved)


def test_axeA_le_bras_SANS_correctif_diverge(axe_liste_stockee, monkeypatch):
    """CONTRE-EPREUVE : la couronne hex croit les entites adjacentes et rend `0`."""
    board, caster, target = axe_liste_stockee
    _bras_avant(monkeypatch)
    st = _state(board, caster, target)
    assert _reason(st, moved=True) == NO_RULE


# ------------------------------------------------------------------ B -- la porte d'elevation

def test_axeB_elevation_le_port_suit_le_natif(axe_elevation):
    """`|dElev| = 2` -> `AreTilesAdjacent` faux MALGRE l'arete stockee -> `0x10`."""
    board, caster, target = axe_elevation
    st = _state(board, caster, target)
    assert _reason(st, moved=True) == int(TR.CasterHasNotMoved)


def test_axeB_le_bras_SANS_correctif_diverge(axe_elevation, monkeypatch):
    board, caster, target = axe_elevation
    _bras_avant(monkeypatch)
    st = _state(board, caster, target)
    assert _reason(st, moved=True) == NO_RULE


def test_axeB_un_seul_cran_ne_coupe_PAS(axe_elevation):
    """La porte est `< 2`, pas `!= 0` : un cran d'ecart laisse les tuiles adjacentes.

    Sans ce cran, un correctif qui refuserait TOUTE difference d'elevation passerait les deux
    tests precedents en etant faux."""
    board, caster, target = axe_elevation
    board1 = Board(_tiles(elev={target: 1}), adjacency="native_sym")
    st = _state(board1, caster, target)
    assert _reason(st, moved=True) == NO_RULE


# ------------------------------------------------------------------ C -- les empreintes

def test_axeC_montage_strictement_discriminant(axe_empreintes):
    """Le montage SEPARE les deux modeles -- sinon toute la suite ne prouve rien."""
    board, caster, feet = axe_empreintes
    st = _state(board, caster, feet[0], target_feet=feet)
    from engine.runner.abilities.targeting import entity_tiles
    vus = entity_tiles(st, TARGET_ID)
    assert len(vus) == 3, "cible non multi-hex : %r" % (vus,)
    d = [hexgeo.distance(f, caster) for f in vus]
    assert min(d) == 1, "caster non adjacent a un pied : %r" % (d,)
    assert d[0] >= 2, "caster adjacent a la MAIN TILE -- montage DEGENERE"
    assert d[-1] >= 2, "caster adjacent au DERNIER pied -- un collapse `pos` passerait aussi"


def test_axeC_empreintes_le_port_suit_le_natif(axe_empreintes):
    """Adjacent par `feet[1]` -> `AreTilesAdjacent(IList, IList)` vrai -> `0`, meme apres un move."""
    board, caster, feet = axe_empreintes
    st = _state(board, caster, feet[0], target_feet=feet)
    assert _reason(st, moved=True) == NO_RULE


def test_axeC_le_bras_SANS_correctif_diverge(axe_empreintes, monkeypatch):
    """CONTRE-EPREUVE, dans le SENS INVERSE des axes A et B : le collapse main tile rate
    l'adjacence et invente un refus `CasterHasNotMoved`."""
    board, caster, feet = axe_empreintes
    _bras_avant(monkeypatch)
    st = _state(board, caster, feet[0], target_feet=feet)
    assert _reason(st, moved=True) == int(TR.CasterHasNotMoved)


# ------------------------------------------------------------------ non-regression du regime nominal

def test_le_regime_NOMINAL_est_inchange(axe_empreintes):
    """Deux unites mono-tuiles, board plat, aretes completes : le correctif est INERTE.

    C'est le cran qui interdit de faire passer les axes A/B/C en cassant le cas courant."""
    board, _caster, _feet = axe_empreintes
    st = _state(board, (4, 4), (4, 5))
    assert _reason(st, moved=True) == NO_RULE, "adjacent au sens des DEUX modeles -> 0"
    st2 = _state(board, (0, 0), (4, 5))
    assert _reason(st2, moved=True) == int(TR.CasterHasNotMoved), "loin + a bouge -> 0x10"


def test_le_court_circuit_d_IDENTITE_est_porte(axe_empreintes):
    """`AreTilesAdjacent(t, t)` rend VRAI (`t1 == t2`, et `|dElev| = 0 < 2`) -- quirk #433-r1.

    Il vient du foyer partage, pas d'une reecriture locale : le verifier ici, c'est verifier que le
    mirror passe bien PAR ce foyer."""
    board, _caster, feet = axe_empreintes
    st = _state(board, (4, 4), feet[0], target_feet=[(4, 4), (7, 7)])
    assert _reason(st, moved=True) == NO_RULE
