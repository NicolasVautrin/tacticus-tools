"""GARDE #433-r1 (OFFLINE PURE) -- le COURT-CIRCUIT D'IDENTITE d'
`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`, et la porte d'ELEVATION qui l'accompagne.

La surcharge SCALAIRE, lue au decompile :

    dElev = |elev(tile2) - elev(tile1)|                      # les DEUX lues AVANT tout branchement
    b     = (tile1 == tile2) ? 1                             # COURT-CIRCUIT sur l'IDENTITE
                             : ConnectivityComponent$$IsNeighbour(tile1.Connectivity, tile2)
    return (dElev < 2) & b

Le test d'identite porte sur l'IDENTITE DE REFERENCE des deux entites-tuile (comparaison de
pointeurs), il court-circuite le calcul de voisinage, et le gate d'elevation ne peut pas le
contredire : sur une meme entite `dElev = 0 < 2`. **Une tuile est adjacente a elle-meme,
inconditionnellement.**

CE QUE CE FICHIER PROTEGE, et pourquoi chaque point regresse EN SILENCE :

  1. **Les foyers du port** qui pretendent mirrorer cette primitive doivent tous rendre VRAI sur une
     paire identique -- y compris la branche DEGRADEE sans board, ou `hexgeo.distance(p, p)` vaut
     `0` et rendait donc FAUX. Un foyer qui rate le court-circuit ne leve pas : il REFUSE une
     adjacence que le natif accorde, et tout consommateur (portee `OnlyAdjacent`, gate melee,
     comptage de voisins) herite du refus.
  2. **Le vslot 0x748** (`TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition`),
     dont le bras `IsAdjacentTiles` passait par `board.neighbours` NU : ni identite, ni elevation.
     Les deux termes sont exerces separement.
  3. **L'INDEPENDANCE A L'ORDRE** des tuiles marquees. C'est une CONSEQUENCE du court-circuit :
     `AreTilesAdjacent(t, t)` etant vrai, `Contains(X, marked[0])` implique
     `IsAdjacentTiles(X, marked)` -- le premier bras est SUBSUME par le second, cote natif comme
     cote port. Le verdict ne peut donc plus dependre de l'ordre d'enumeration de
     `EffectsState.by_unit`, qui n'est PAS celui du natif. Avant #433-r1 il en dependait.

Confrontation LIVE (mesuree, MC1_67/777) : `python scripts/python/probe_433_r1_identity_shortcircuit.py`
-- marque en (4,2) a l'elevation 4, destination (3,2) a l'elevation 2 : le natif ne pose AUCUN
`1574`, le port est en accord ; sous `--mutate` (retour a `board.neighbours` nu) le port en pose un
-> `DESACCORD sur 1574 -- port=True natif=False`.
RE : `docs/rl/case-433-r1-identite-adjacence.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.battle_query import (                                        # noqa: E402
    are_entities_adjacent as pb_entities_adjacent, is_adjacent as pb_is_adjacent)
from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402
from engine.entities.effects_state import EffectsState  # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects.factory import EffectFactory  # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities.targeting import (                          # noqa: E402
    are_entities_adjacent, are_tiles_adjacent)
from engine.runner.operations.effects import AddEffectOperation          # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent          # noqa: E402
from engine.runner.operations.triggers.loki.teleporting_in import (      # noqa: E402
    TitanhammerSquadTeleportingInAddMovingOnPreMove,
    TITANHAMMER_SQUAD_TARGET_TILE, TITANHAMMER_SQUAD_TELEPORTING_IN)
from engine.runner.snapshot import load_state                            # noqa: E402
from engine.services.battle_query import are_tiles_adjacent as bq_adj    # noqa: E402

COLS, ROWS = 7, 7
CARRIER, CASTER = 10, 40
MARK = (3, 3)
#: la marque, une voisine SURELEVEE de 2 crans, et une seconde marque DISJOINTE (voisine d'aucune
#: autre) -- c'est elle qui rend le bras `Contains` insuffisant.
HIGH = (3, 4)
FAR_MARK = (0, 6)


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board(elev_by_pos=None) -> Board:
    elev_by_pos = elev_by_pos or {}
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row,
                          "elevation": int(elev_by_pos.get((col, row), 0)),
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


@pytest.fixture
def flat():
    return _board()


def _stage(board):
    decision = {"currentPlayer": 1, "units": [
        {"id": CARRIER, "visualId": "deathBlightlord", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 1}, "effects": []},
        {"id": CASTER, "visualId": "astarLysander", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 2}, "effects": []}]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 0},
                           "healthMax": 1000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in decision["units"]]}
    st = load_state(decision, observe, snapshot, board=board, ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    AddEffectOperation.execute(st, source=CASTER, target=CARRIER,
                               effect_type=TITANHAMMER_SQUAD_TELEPORTING_IN,
                               name=EffectType.TitanhammerSquad_TeleportingIn.name)
    return st


def _mark(st, board, coord):
    st.effects.add_effect(int(board.id_at(coord[0], coord[1])), EffectFactory.create(
        {"name": EffectType.TitanhammerSquad_TargetTile.name,
         "effectType": TITANHAMMER_SQUAD_TARGET_TILE, "source": CASTER, "remaining": 0}))


def _cond(st, dest) -> bool:
    ev = TriggerEvent(int(EventTriggerType.PreUnitMove), CARRIER, CARRIER, ranged=False,
                      profile=None, dest_tile=(None if dest is None else tuple(dest)))
    return TitanhammerSquadTeleportingInAddMovingOnPreMove(CARRIER)._custom_moving_condition(st, ev)


# ------------------------------------------------------- 1. la propriete, foyer par foyer

def test_every_declared_mirror_calls_a_tile_adjacent_to_itself(flat):
    """`(tile1 == tile2) -> b = 1`, et `dElev = 0 < 2` : VRAI dans TOUS les foyers.

    La 4e ligne est celle qui manquait : sans board le port degradait en `hexgeo.distance == 1`,
    qui vaut `0` sur une paire identique -- un FAUX REFUS silencieux."""
    tid = flat.id_at(MARK[0], MARK[1])
    assert are_tiles_adjacent(flat, tid, tid) is True
    assert are_entities_adjacent(flat, [MARK], [MARK]) is True
    assert bq_adj(MARK, MARK, flat) is True
    assert bq_adj(MARK, MARK, None) is True
    assert pb_entities_adjacent(MARK, MARK, {MARK: 0}) is True


def test_the_IterateAdjacentTiles_mirror_must_NOT_gain_the_shortcircuit():
    """LE CONTRE-EXEMPLE, et il est aussi important que la propriete elle-meme.

    `battle_query.is_adjacent` mirrore `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`
    (les comptages `GetAdjacent*`, `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits`), dont le `MoveNext` parcourt la liste
    d'adjacence STOCKEE sur la tuile : la source ne s'y trouve jamais. L'aligner sur la primitive de
    PORTEE << par coherence >> ferait compter chaque unite comme sa propre voisine -- une inflation
    silencieuse de toutes les utilites de voisinage. Les deux natifs sont distincts, le port aussi."""
    assert pb_is_adjacent(MARK, MARK, None) is False
    assert pb_is_adjacent(MARK, MARK, {MARK: 0}) is False


def test_the_elevation_gate_is_not_weakened_by_the_shortcircuit(flat):
    """La primitive rend `(dElev < 2) & b` : le court-circuit ne pose que `b`, il n'ouvre PAS la
    porte d'elevation pour les paires DISTINCTES."""
    b = _board({MARK: 0, HIGH: 2})
    lo, hi = b.id_at(MARK[0], MARK[1]), b.id_at(HIGH[0], HIGH[1])
    assert hi in set(b.neighbours(lo)), "MONTAGE : (3,4) doit etre voisine de (3,3)"
    assert are_tiles_adjacent(b, lo, hi) is False
    assert are_tiles_adjacent(b, lo, lo) is True and are_tiles_adjacent(b, hi, hi) is True


# ------------------------------------------------------- 2. le vslot 0x748, ses DEUX termes

def test_a_destination_that_IS_a_mark_passes_even_when_it_is_not_the_first(flat):
    """Bras `IsAdjacentTiles` sous COURT-CIRCUIT. `XContainsYTrigger` reduit son 2e operande a UNE
    entite (slot 1) et ne voit donc que la PREMIERE marque ; c'est le court-circuit d'identite du
    slot 0x60 qui rattrape les autres. Sans lui, une destination posee SUR la 2e marque ne poserait
    aucun `1574` -- alors que le natif en pose un."""
    st = _stage(flat)
    _mark(st, flat, MARK)
    _mark(st, flat, FAR_MARK)
    assert flat.id_at(FAR_MARK[0], FAR_MARK[1]) not in set(
        flat.neighbours(flat.id_at(MARK[0], MARK[1]))), \
        "MONTAGE : les deux marques doivent etre DISJOINTES"
    assert _cond(st, FAR_MARK) is True


def test_the_verdict_no_longer_depends_on_the_enumeration_order(flat):
    """L'INDEPENDANCE A L'ORDRE, consequence directe du court-circuit : `Contains` etant subsume par
    `IsAdjacentTiles`, poser les deux marques dans un ordre ou dans l'autre donne le MEME verdict
    pour chacune des deux destinations. L'ordre de `EffectsState.by_unit` n'est PAS celui du natif
    (ordre de creation des entites-effet) : c'est ce test qui rend cette difference inoffensive."""
    for order in ((MARK, FAR_MARK), (FAR_MARK, MARK)):
        st = _stage(flat)
        for m in order:
            _mark(st, flat, m)
        assert _cond(st, MARK) is True, order
        assert _cond(st, FAR_MARK) is True, order


def test_a_neighbour_two_elevation_steps_away_does_not_arm_the_marker():
    """Bras `IsAdjacentTiles` sous la porte d'ELEVATION. `board.neighbours` nu la rate : le port
    posait `1574` la ou le natif n'en pose aucun (mesure LIVE MC1_67/777, cf. l'en-tete)."""
    b = _board({MARK: 0, HIGH: 2})
    st = _stage(b)
    _mark(st, b, MARK)
    assert _cond(st, HIGH) is False
    flat_neighbour = next(b.coord(n) for n in b.neighbours(b.id_at(MARK[0], MARK[1]))
                          if b.coord(n) != HIGH)
    assert _cond(st, flat_neighbour) is True, "temoin : une voisine PLATE doit armer le marqueur"


def test_the_marked_tile_itself_still_arms_it(flat):
    """NON-REGRESSION du bras `Contains` : la tuile marquee elle-meme reste couverte. Elle l'est
    desormais DEUX fois (le court-circuit la couvre aussi), et c'est exactement la subsomption."""
    st = _stage(flat)
    _mark(st, flat, MARK)
    assert _cond(st, MARK) is True
    assert _cond(st, (0, 0)) is False
