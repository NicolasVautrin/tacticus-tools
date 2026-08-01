"""GARDE #448-r2c tranche 2/4 (OFFLINE PURE) -- `1238 FearOfTheUnseen_TeleportingIn`, la SEULE
derivee d'`IdunBattle.Entities.Effects.Loki.ATeleportingEffect` qui surcharge le vslot 0x738.

CE QU'ELLE PROTEGE, et pourquoi chaque bloc peut regresser SILENCIEUSEMENT :

  1. **La surcharge N'EST PAS le conjonct neutre.**
     `IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_TeleportingInEffect$$
     GetAdditionalRemoveTriggers` = `AmountIsEqual(EffectRemainingTurns(EffectSelf), Direct(1))`.
     La ramener a `True` (le corps de BASE, herite des trois soeurs) ne casse RIEN : elle fait
     seulement partir 1238 des le `FinishUnitTurn` qui SUIT SON PROPRE CAST -- le Deathleaper ne
     disparait alors JAMAIS. Degradation PERMISSIVE, muette, et invisible de tout test qui ne
     regarderait qu'un seul tour.
  2. **Le vslot gouverne les QUATRE `Triggered()`, T4 COMPRIS.** `$$CreateHandleTriggerAbilitiesInternal`
     appelle `(**(code **)(*in_RDX + 0x738))()` une fois par trigger. Oublier T4 poserait le marqueur
     `1241 FearOfTheUnseen_Moving` sur un pas fait avec `remaining = 3`, alors que le natif n'y pose
     rien.
  3. **L'EGALITE est STRICTE**, pas un `<=` ni un `>=` : le tail-call vise la surcharge d'
     `IdunBattleLogic.Entities.DSLTriggers$$AmountIsEqual` qui instancie
     `IdunBattle.Entities.Conditions.AmountIsEqualAbilityTrigger` -- sa VOISINE IMMEDIATE porte le
     MEME nom et la MEME signature, et instancie `AmountIsGreaterAbilityTrigger`. Un `>=` ferait
     partir l'effet des le tour du cast (remaining 3 >= 1) : exactement la regression du point 1.
  4. **`GetMovingEffectType` = 1241**, et non 1036 : deux marqueurs distincts, deux entrees de
     registre distinctes. Se tromper de constante laisserait 1241 non retire (le port n'a pas de
     trigger pour 1036 sur ce porteur) et `set_moved_flag` poserait `UnitFlag.Teleported` sur les
     deplacements ordinaires suivants.
  5. **La chronologie de bout en bout** (3 -> 2 -> 1 -> retrait), jouee par le VRAI decrement
     (`EffectsState.on_turn_end` = `EffectComponent$$RemoveOneTurn`), pas par une valeur posee a la
     main.

RE : `docs/rl/case-448-r2c-fear-of-the-unseen-teleporting-in.md`.
Confrontation LIVE : `python scripts/python/probe_448_r2c_fear_of_the_unseen.py`.
ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402
from engine.entities import EffectsState                                 # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.components import set_unit_feet                       # noqa: E402
from engine.runner.operations.effects import AddEffectOperation          # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent          # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.loki.teleporting_in import (      # noqa: E402
    FEAR_OF_THE_UNSEEN_MOVING, FEAR_OF_THE_UNSEEN_TELEPORTING_IN,
    FearOfTheUnseenMovingRemoveOnAfterMove,
    FearOfTheUnseenTeleportingInAddMovingOnPreMove,
    FearOfTheUnseenTeleportingInRemoveOnAfterMove,
    FearOfTheUnseenTeleportingInRemoveOnPreUnitAbility,
    FearOfTheUnseenTeleportingInRemoveOnUnitFinishedTurn,
    TeleportMovingRemoveOnAfterMove, effect_remaining_turns)
from engine.runner.snapshot import load_state                            # noqa: E402

COLS, ROWS = 7, 7
CARRIER, FOE = 10, 20

#: Les QUATRE classes de 1238, dans l'ordre de l'`ArraySet` natif.
THE_FOUR = [FearOfTheUnseenTeleportingInRemoveOnAfterMove,          # T1 On(0x04)
            FearOfTheUnseenTeleportingInRemoveOnPreUnitAbility,     # T2 On(0x2a = PreUnitAbility)
            FearOfTheUnseenTeleportingInRemoveOnUnitFinishedTurn,   # T3 On(0x28 = UnitFinishedTurn)
            FearOfTheUnseenTeleportingInAddMovingOnPreMove]         # T4 On(0x1f)


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


@pytest.fixture
def state():
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CARRIER, "visualId": "tyranDeathleaper", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 6, "row": 6}, "effects": []},
    ]}
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
    return st


def _put(st, uid, effect_type, name, duration=None):
    AddEffectOperation.execute(st, source=uid, target=uid, effect_type=int(effect_type),
                               name=name, duration_override=duration)


def _live(st, uid, effect_type) -> list:
    return [e for e in (st.effects.by_unit.get(int(uid)) or [])
            if int(getattr(e, "effect_type", -1)) == int(effect_type) and not e.consumed]


def _ev(event_id, actor=CARRIER):
    return TriggerEvent(int(event_id), actor, actor, ranged=False, profile=None)


def _pose(st, remaining: int):
    """Pose 1238 avec la duree voulue, en TOURS (le poseur natif passe `Sum(TurnsFromRounds(1),
    Direct(1))`, deja folde en tours par `FearOfTheUnseenAbility.execute_behaviour`).

    ⚠ `remaining = 0` ne se monte PAS par `duration_override` : la fabrique normalise toute duree
    `<= 0` en `None` (= PERMANENT, `EffectComponent.HasTurns` faux) -- cf.
    `entities/effects/factory.py`. C'est fidele au natif, qui ne LAISSE JAMAIS vivre un effet a 0
    (`$$ShouldBeRemoved` = `HasTurns && Duration == 0` -> retrait immediat). On force donc le champ
    pour ce seul cas : c'est une garde de FORME sur la condition (fermer la porte a un `<=`), pas un
    regime que le natif traverse."""
    _put(st, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN, "FearOfTheUnseen_TeleportingIn",
         duration=int(remaining) if remaining > 0 else 1)
    got = _live(st, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN)
    if remaining <= 0:
        for e in got:
            e.remaining_turns = int(remaining)
    assert [e.remaining_turns for e in got] == [remaining], [e.remaining_turns for e in got]


# ------------------------------------------------------------------ 1./3. le vslot 0x738

@pytest.mark.parametrize("cls", THE_FOUR)
@pytest.mark.parametrize("remaining,expected", [(3, False), (2, False), (1, True), (0, False)])
def test_the_vslot_gates_all_four_triggers_on_remaining_equals_one(state, cls, remaining, expected):
    """LE COEUR DE LA TRANCHE. `AmountIsEqual(EffectRemainingTurns(EffectSelf), Direct(1))` sur les
    QUATRE `Triggered()` -- le vslot 0x738 est lu une fois par trigger dans le decompile, T4 inclus.

    Les quatre valeurs balayees exercent l'egalite STRICTE dans les deux sens : `3`/`2` sont les
    valeurs REELLES que 1238 traverse (pose a 3 a deux joueurs), `0` ferme la porte a un `<=`."""
    _pose(state, remaining)
    assert cls(CARRIER).matches(state, _ev(cls.event_id)) is expected, (
        "%s : remaining=%d -> %r (attendu %r)"
        % (cls.__name__, remaining, cls(CARRIER).matches(state, _ev(cls.event_id)), expected))


def test_the_removal_is_a_no_op_while_more_than_one_turn_remains(state):
    """Contre-epreuve d'EXECUTION, pas seulement de condition : le dispatcher n'appelle
    `execute_behaviour` que si `matches`, mais un port qui aurait cable la condition au mauvais
    endroit retirerait quand meme. On verifie que l'effet SURVIT."""
    _pose(state, 3)
    for cls in THE_FOUR[:3]:
        trig = cls(CARRIER)
        assert trig.matches(state, _ev(cls.event_id)) is False
        assert len(_live(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN)) == 1


@pytest.mark.parametrize("cls", THE_FOUR[:3])
def test_each_removal_trigger_drops_the_effect_at_remaining_one(state, cls):
    """A `remaining == 1`, les TROIS retraits font la MEME chose
    (`BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(EffectSelf)`)."""
    _pose(state, 1)
    assert cls(CARRIER).matches(state, _ev(cls.event_id)) is True
    out = cls(CARRIER).execute_behaviour(state, _ev(cls.event_id))
    assert _live(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN) == []
    assert out is not None and out["removed"] == 1, out


# ------------------------------------------------------------------ 2./4. T4 et le marqueur 1241

def test_T4_poses_1241_and_only_at_remaining_one(state):
    """`GetMovingEffectType` = `Nullable<EffectType>(0x4d9)` = **1241**, pas 1036. Et la pose est
    gouvernee par le MEME vslot 0x738 que les retraits."""
    trig = FearOfTheUnseenTeleportingInAddMovingOnPreMove(CARRIER)
    assert trig.MOVING_EFFECT_TYPE == int(EffectType.FearOfTheUnseen_Moving) == 1241
    _pose(state, 3)
    assert trig.matches(state, _ev(EventTriggerType.PreUnitMove)) is False
    assert _live(state, CARRIER, FEAR_OF_THE_UNSEEN_MOVING) == []
    # meme etat, mais a 1 tour restant
    for e in _live(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN):
        e.remaining_turns = 1
    assert trig.matches(state, _ev(EventTriggerType.PreUnitMove)) is True
    out = trig.execute_behaviour(state, _ev(EventTriggerType.PreUnitMove))
    got = _live(state, CARRIER, FEAR_OF_THE_UNSEEN_MOVING)
    assert out is not None and out["placed"] is True, out
    assert [e.effect_type for e in got] == [1241]


def test_the_moving_marker_lives_exactly_one_step(state):
    """`IdunBattleLogic.Effects.TeleportMovingEffect$$CreateHandleTriggerAbilitiesInternal` = UN SEUL
    `Triggered(On(4) & OwnerIsActor, RemoveEffect(EffectSelf))`, et le RETRAIT du marqueur ne porte
    AUCUNE condition de tours (le vslot 0x738 est celui de `ATeleportingEffect`, pas du compagnon)."""
    got = EFFECT_TRIGGERS.get(FEAR_OF_THE_UNSEEN_MOVING) or []
    assert [c.__name__ for c in got] == ["FearOfTheUnseenMovingRemoveOnAfterMove"]
    assert issubclass(got[0], TeleportMovingRemoveOnAfterMove)
    _put(state, CARRIER, FEAR_OF_THE_UNSEEN_MOVING, "FearOfTheUnseen_Moving", duration=1)
    FearOfTheUnseenMovingRemoveOnAfterMove(CARRIER).execute_behaviour(
        state, _ev(EventTriggerType.UnitAfterMove))
    assert _live(state, CARRIER, FEAR_OF_THE_UNSEEN_MOVING) == []


def test_the_moving_marker_of_1238_is_not_the_one_of_1035(state):
    """Cliquet de constante : 1241 != 1036. Les deux marqueurs sont des `EffectType` distincts avec
    leur PROPRE entree de registre."""
    assert FEAR_OF_THE_UNSEEN_MOVING == 1241
    assert int(EffectType.TeleportStrike_Moving) == 1036
    assert EFFECT_TRIGGERS.get(1036) is not EFFECT_TRIGGERS.get(1241)


# ------------------------------------------------------------------ HasTile / OwnerIsActor

def test_T3_still_gates_on_HasTile_and_the_others_do_not(state):
    """Le gate propre a T3 est HERITE tel quel : la surcharge du vslot s'AJOUTE, elle ne remplace
    rien (`op_BitwiseAnd` en chaine dans le decompile)."""
    _pose(state, 1)
    t3 = FearOfTheUnseenTeleportingInRemoveOnUnitFinishedTurn(CARRIER)
    assert t3.matches(state, _ev(EventTriggerType.UnitFinishedTurn)) is True
    set_unit_feet(state, CARRIER, [])                    # HORS PLATEAU
    assert t3.matches(state, _ev(EventTriggerType.UnitFinishedTurn)) is False
    for cls in (THE_FOUR[0], THE_FOUR[1], THE_FOUR[3]):
        assert cls(CARRIER).matches(state, _ev(cls.event_id)) is True, cls.__name__


@pytest.mark.parametrize("cls", THE_FOUR + [FearOfTheUnseenMovingRemoveOnAfterMove])
def test_owner_is_actor_is_exercised_both_ways(state, cls):
    _pose(state, 1)
    _put(state, CARRIER, FEAR_OF_THE_UNSEEN_MOVING, "FearOfTheUnseen_Moving", duration=1)
    trig = cls(CARRIER)
    assert trig.matches(state, _ev(cls.event_id, actor=CARRIER)) is True
    assert trig.matches(state, _ev(cls.event_id, actor=FOE)) is False


# ------------------------------------------------------------------ 5. la chronologie complete

def test_the_effect_survives_its_own_cast_turn_and_the_enemy_turn(state):
    """SCENARIO DE BOUT EN BOUT, avec le VRAI decrement (`EffectsState.on_turn_end` =
    `EffectComponent$$RemoveOneTurn` + `$$ShouldBeRemoved`) -- aucune valeur posee a la main.

        cast          remaining 3 -> le FinishUnitTurn qui SUIT le cast ne retire RIEN
        fin tour 1    remaining 2 -> le tour adverse ne retire rien non plus
        fin tour 2    remaining 1 -> le tour SUIVANT du porteur retire

    Un port qui collapserait le vslot a `True` echouerait des la premiere assertion."""
    _pose(state, 3)                                       # `Sum(TurnsFromRounds(1), Direct(1))`
    t3 = FearOfTheUnseenTeleportingInRemoveOnUnitFinishedTurn(CARRIER)
    # --- tour du cast : le FinishUnitTurn immediatement consecutif
    assert t3.matches(state, _ev(EventTriggerType.UnitFinishedTurn)) is False
    assert len(_live(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN)) == 1
    state.effects.on_turn_end(CARRIER, attacked=False)     # fin du tour du porteur
    assert effect_remaining_turns(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN) == 2
    assert t3.matches(state, _ev(EventTriggerType.UnitFinishedTurn)) is False
    state.effects.on_turn_end(CARRIER, attacked=False)     # fin du tour adverse
    assert effect_remaining_turns(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN) == 1
    # --- tour SUIVANT du porteur : le regime s'ouvre
    assert t3.matches(state, _ev(EventTriggerType.UnitFinishedTurn)) is True
    assert FearOfTheUnseenTeleportingInRemoveOnAfterMove(CARRIER).matches(
        state, _ev(EventTriggerType.UnitAfterMove)) is True
    assert FearOfTheUnseenTeleportingInAddMovingOnPreMove(CARRIER).matches(
        state, _ev(EventTriggerType.PreUnitMove)) is True


def test_effect_remaining_turns_mirrors_the_native_formula(state):
    """`EffectRemainingTurnsFormula$$Calculate` SOMME `EffectComponent.Duration @+0x64` sur les
    entites-effet resolues. Un effet PERMANENT (`HasTurns` faux, `remaining_turns is None`)
    contribue 0, pas None -- et un effet CONSOMME ne contribue plus (gate `!Removed`)."""
    assert effect_remaining_turns(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN) == 0
    _pose(state, 3)
    assert effect_remaining_turns(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN) == 3
    for e in _live(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN):
        e.remaining_turns = None
    assert effect_remaining_turns(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN) == 0
    for e in _live(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN):
        e.remaining_turns, e.consumed = 1, True
    assert effect_remaining_turns(state, CARRIER, FEAR_OF_THE_UNSEEN_TELEPORTING_IN) == 0


def test_the_four_are_registered_in_the_native_ArraySet_order():
    got = EFFECT_TRIGGERS.get(FEAR_OF_THE_UNSEEN_TELEPORTING_IN) or []
    assert [c.__name__ for c in got] == [c.__name__ for c in THE_FOUR]
    assert [c.event_id for c in got] == [int(EventTriggerType.UnitAfterMove),        # On(0x04)
                                         int(EventTriggerType.PreUnitAbility),       # On(0x2a = PreUnitAbility)
                                         int(EventTriggerType.UnitFinishedTurn),     # On(0x28 = UnitFinishedTurn)
                                         int(EventTriggerType.PreUnitMove)]          # On(0x1f)
    assert all(c.effect_type == FEAR_OF_THE_UNSEEN_TELEPORTING_IN for c in got)
