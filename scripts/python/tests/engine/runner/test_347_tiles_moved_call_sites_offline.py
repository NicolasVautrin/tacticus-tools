"""#347 -- les call-sites de `RecordTilesMoved` que #335/#340 n'avaient pas portes.

Pourquoi une garde OFFLINE plutot que live : le compteur `ActorStatisticsComponent+0xf0` n'a
AUCUN lecteur atteignable sur ces trois mecanismes (detail et alternatives essayees :
`docs/rl/case-347-tiles-moved-call-sites.md` SS5). Le capteur direct
`actorStats.tilesMovedThisTurn`, livre par #340, n'est pas deploye. Le montage live est ecrit
(`scripts/python/probe_347_tiles_moved_call_sites.py`) et RELEVE que le capteur manque au lieu de
rendre un zero ; ce fichier-ci garde ce que le port DOIT faire, mecanisme par mecanisme, et surtout
les DEUX gates -- c'est-a-dire les deux facons de sur-compter.

CE QUE LE DECOMPILE DIT (relu sur `rnca9r7q6c`) :

    IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved(caster, target, prev, dest, options):
        if (options.<+0x10>)                            // = DisplaceUnitBehaviourOptions+0x1c
            if (!IdunBattle.Entities.UnitExtensions$$IsEnemy(caster, target, state))
                RecordTilesMoved(target, GetDistance(prev, [dest]), state);

    IdunBattle.Operations.DisplaceUnitOperation$$SwitchPosition(caster, target, options):
        if (!deadTarget) { MoveUnit(target -> tileCaster); AddTilesMoved(caster, target,  ...); }
        if (!deadCaster) { MoveUnit(caster -> tileTarget); AddTilesMoved(caster, CASTER, ...); }

Le second appel passe `target = caster` : son gate `!IsEnemy` est TOUJOURS passant. C'est le fait
que le nom « echange » ne laisse pas deviner, et le seul que ce fichier peut verrouiller sans
capteur.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from engine.battle_query import DISTANCE_UNREACHABLE, get_distance          # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent,    # noqa: E402
                                      UnitComponent, unit_tiles_moved_this_turn)
from engine.runner.events import EventBus                                   # noqa: E402
from engine.runner.operations.displace import (DisplaceUnitOperation,       # noqa: E402
                                               SwitchPositionOperation, _add_tiles_moved)
from engine.runner.operations.revive import _set_revive_position            # noqa: E402
from engine.runner.state import State                                       # noqa: E402


def _state(units):
    """`units` = [(id, (col,row), team)] -> un `State` nu (sans board : aucun des chemins testes
    n'a besoin de pathfinding, `AddTilesMoved` comptant en distance HEX)."""
    st = State()
    for uid, pos, team in units:
        e = st.add_entity(uid)
        e.add_component(PositionComponent(pos[0], pos[1]))
        e.add_component(UnitComponent("u%d" % uid, True))
        e.add_component(OwnerComponent(team))
    return st


# --------------------------------------------------------------------- `MovementQuery$$GetDistance`
def test_get_distance_is_hex_not_path():
    """Le corps de `IdunBattle.Core.Services.MovementQuery$$GetDistance` est un minimum de
    `CubeCoordinate.Distance` -- pas un pathfinding. Un obstacle ne le change donc PAS, la ou
    `GetNumTilesMoved(connectedPath)` (l'autre quantite, celle de `MoveUnitOperation$$Execute`)
    facturerait le detour."""
    assert get_distance([(0, 0)], [(0, 3)]) == 3
    assert get_distance([(0, 0)], [(0, 0)]) == 0
    # minimum sur les DEUX ensembles (unites multi-tuiles cote natif)
    assert get_distance([(0, 0), (0, 5)], [(0, 4)]) == 1
    # ensemble vide -> `int.MaxValue`, exactement comme le natif
    assert get_distance([], [(1, 1)]) == DISTANCE_UNREACHABLE
    assert get_distance([(1, 1)], []) == DISTANCE_UNREACHABLE


# ------------------------------------------------------------------------------- `AddTilesMoved`
def test_add_tiles_moved_records_hex_distance_on_the_target():
    st = _state([(1, (0, 0), 10), (2, (0, 3), 10)])
    n = _add_tiles_moved(st, 1, 2, [(0, 3)], (0, 0), record_tiles=True)
    assert n == 3
    assert unit_tiles_moved_this_turn(st, 2) == 3
    assert unit_tiles_moved_this_turn(st, 1) == 0          # c'est la CIBLE qui est creditee


def test_add_tiles_moved_is_off_without_the_options_gate():
    """`record_tiles` = `DisplaceUnitBehaviourOptions+0x1c`. Les SIX feuilles de push/pull/displace
    le laissent a 0 ; seules `DSLBehaviors$$SwitchPosition` et `$$Teleport` le posent."""
    st = _state([(1, (0, 0), 10), (2, (0, 3), 10)])
    assert _add_tiles_moved(st, 1, 2, [(0, 3)], (0, 0), record_tiles=False) == 0
    assert unit_tiles_moved_this_turn(st, 2) == 0


def test_add_tiles_moved_refuses_an_enemy_target():
    """`!IsEnemy(caster, target)` : seul un deplacement AMICAL compte."""
    st = _state([(1, (0, 0), 10), (2, (0, 3), 20)])
    assert _add_tiles_moved(st, 1, 2, [(0, 3)], (0, 0), record_tiles=True) == 0
    assert unit_tiles_moved_this_turn(st, 2) == 0


def test_add_tiles_moved_always_passes_when_target_is_the_caster():
    """`IsEnemy(x, x)` est faux : c'est ce qui rend la moitie « caster » de `SwitchPosition`
    inconditionnelle, meme face a une cible ENNEMIE."""
    st = _state([(1, (0, 0), 10)])
    assert _add_tiles_moved(st, 1, 1, [(0, 0)], (0, 2), record_tiles=True) == 2


# ------------------------------------------------------------------------------ `SwitchPosition`
def test_switch_credits_both_units_between_allies():
    st = _state([(1, (0, 0), 10), (2, (0, 3), 10)])
    res = SwitchPositionOperation(1, 2).execute(st, EventBus())
    assert res["switched"] is True
    assert unit_tiles_moved_this_turn(st, 1) == 3
    assert unit_tiles_moved_this_turn(st, 2) == 3
    assert res["tiles_moved"] == {1: 3, 2: 3}


def test_switch_credits_only_the_caster_against_an_enemy():
    """La moitie « cible » a le gate `!IsEnemy(caster, target)` ; la moitie « caster » ne l'a pas."""
    st = _state([(1, (0, 0), 10), (2, (0, 3), 20)])
    SwitchPositionOperation(1, 2).execute(st, EventBus())
    assert unit_tiles_moved_this_turn(st, 1) == 3
    assert unit_tiles_moved_this_turn(st, 2) == 0


def test_switch_records_nothing_without_the_options_gate():
    st = _state([(1, (0, 0), 10), (2, (0, 3), 10)])
    SwitchPositionOperation(1, 2, record_tiles=False).execute(st, EventBus())
    assert unit_tiles_moved_this_turn(st, 1) == 0
    assert unit_tiles_moved_this_turn(st, 2) == 0


# ------------------------------------------------------------------------------- push (le NON-cas)
def test_push_records_nothing():
    """Le bras qui garde contre le SUR-comptage : aucune feuille DSL de push ne pose `+0x1c`, donc
    un push n'enregistre RIEN -- ni sur le pousseur, ni sur la poussee. Un port qui aurait cable
    `AddTilesMoved` sans son gate rendrait 1 ici."""
    st = _state([(1, (0, 0), 10), (2, (0, 1), 20)])
    op = DisplaceUnitOperation(1, 2)
    assert op.record_tiles is False                        # le DEFAUT, pas une option du montage
    st.board = None                                        # le push sort avant tout pathfinding
    res = op.execute(st, EventBus())
    assert res.get("tiles_moved") is None
    assert unit_tiles_moved_this_turn(st, 2) == 0


# ---------------------------------------------------------------------------- `SetRevivePosition`
def test_revive_at_position_records_the_hex_distance():
    st = _state([(1, (0, 0), 10)])
    assert _set_revive_position(st, 1, (0, 3)) == (0, 3)
    assert unit_tiles_moved_this_turn(st, 1) == 3


def test_revive_in_place_records_nothing():
    """`if (!revivePosition.HasValue) return;` -- la premiere instruction de la fonction native.
    C'est le cas de TOUS les consommateurs sauf le `GhostEffect` de `thousTerminator`."""
    st = _state([(1, (0, 0), 10)])
    assert _set_revive_position(st, 1, None) is None
    assert unit_tiles_moved_this_turn(st, 1) == 0


def test_revive_on_the_same_tile_records_nothing():
    """Distance 0 -> `RecordTilesMoved` no-ope (`if (tiles < 1) return`)."""
    st = _state([(1, (0, 0), 10)])
    assert _set_revive_position(st, 1, (0, 0)) == (0, 0)
    assert unit_tiles_moved_this_turn(st, 1) == 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
