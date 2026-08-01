"""GARDE #366-r1 tranche 3/3 (OFFLINE PURE) -- `1141 StormboyzStrike`, la triggered de
`orksNpc6Stormboy`.

CE QU'ELLE PROTEGE, et pourquoi chaque bloc peut regresser SILENCIEUSEMENT :

  1. **LE BEHAVIOUR**. `...StormboyzStrike_TeleportAbility$$CreateBehaviour` =
     `RemoveUnitFromItsTiles(Owner, true) & AddEffect(0x474, stateRef, Owner, turns:Nullable(2))`.
     La duree est DEJA EN TOURS (la surcharge `turns:Nullable<int>` en fait un `Direct(n)` que
     `AddEffectOperation` ne convertit pas) : un `duration_rounds=2` rendrait `2 * nbJoueurs`, soit
     4 tours sur un duel -- un ecart de facteur 2 qu'aucun crash ne signale. Mesure live :
     `remaining = 2`.
  2. **LES TROIS GATES** de `$$CreateTrigger` : `get_OwnerIsActor`,
     `AmountIsEqual(UnitTurnsStarted(Owner), Direct(0))` et `NOT HasFlag(Owner, Moved=0)`. Chacun
     est exerce dans les DEUX sens. Un gate perdu rendrait l'ability re-tirable a chaque
     `AbilityInit` -- degradation PERMISSIVE.
  3. **LE REGISTRE**. L'entree `ABILITY_TRIGGERS["StormboyzStrike"]` (voie `passiveAbilities`) et
     l'`event_id` = `On(AbilityInit = 0x21)`.
  4. **LA QUALIFICATION DES ENUMS**. `1141` est un `TriggeredAbilityType` ici, mais un
     `ActiveAbilityType` (`OverwhelmingWrath`) ailleurs ; `1140` est un `EffectType` ici, mais un
     `ActiveAbilityType` (`ExemplarOfHate`) et un `TriggeredAbilityType` (`PowerUp_Hits`) ailleurs.
     Le test verrouille les trois lectures pour qu'un futur port ne les confonde pas -- et verifie
     que 1141/1140 ne sont PAS entres dans le registre des ACTIVES par erreur.

Confrontation LIVE (4 montages, greffe du passif, pool de teleport) :
`python scripts/python/probe_366_r1_stormboyz_strike.py`.
RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` §7. ASCII only. Aucune VA en dur.
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
from engine.entities.active_ability_type import ActiveAbilityType        # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.entities.stats import StatType                               # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.components import (PositionComponent, StatsComponent,  # noqa: E402
                                      UnitComponent, get_unit_feet, set_moved_flag)
from engine.runner.operations.triggers.base import TriggerEvent          # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.loki.stormboyz_strike import (    # noqa: E402
    StormboyzStrikeTeleportAbility, stormboyz_strike_teleport_tree)
from engine.runner.snapshot import load_state                            # noqa: E402

TELEPORTING_IN = 0x474           # 1140 EffectType.StormboyzStrike_TeleportingIn
STORMBOYZ_STRIKE = 0x475         # 1141 TriggeredAbilityType.StormboyzStrike
COLS, ROWS = 7, 7
CARRIER, ALLY, FOE = 10, 40, 20


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
    """`State` runner minimal : le porteur, un allie, un ennemi. `EffectsState` materialise -- sans
    lui `AddEffectOperation` abandonne et la feuille emettrait quand meme sa trace."""
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CARRIER, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": ALLY, "visualId": "orksWarboss", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 3}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 6, "row": 6}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    # `combatSnapshot` MINIMAL : sans lui aucune unite n'a de `StatsComponent`, donc pas de
    # compteur `turnsStarted` a exercer -- et le gate #2 serait teste sur une valeur de repli.
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


def _ev(actor=CARRIER):
    return TriggerEvent(int(EventTriggerType.AbilityInit), actor, actor,
                        ranged=False, profile=None)


def _teleporting(st, uid) -> list:
    return [e for e in (st.effects.by_unit.get(int(uid)) or [])
            if int(getattr(e, "effect_type", -1)) == TELEPORTING_IN and not e.consumed]


def _set_turns_started(st, uid, value: int) -> None:
    sc = st.get_entity(int(uid)).get_component(StatsComponent)
    cur = int(sc.ctx.stat(StatType.TURNS_STARTED) or 0)
    sc.ctx.stats.increment_base(int(StatType.TURNS_STARTED), int(value) - cur)


# ------------------------------------------------------------------ 1. LE BEHAVIOUR

def test_behaviour_removes_the_carrier_from_the_board_and_marks_it(state):
    """LES DEUX ETAGES en un seul `execute_behaviour` : le porteur quitte le plateau (`pos`/`feet`
    vides, `alive = True` -- c'est un retrait de TUILES, pas une mort) ET porte 1140."""
    out = StormboyzStrikeTeleportAbility(CARRIER).execute_behaviour(state, _ev())
    assert get_unit_feet(state, CARRIER) == []
    assert state.get_entity(CARRIER).get_component(PositionComponent) is None
    assert state.get_entity(CARRIER).get_component(UnitComponent).alive is True
    got = _teleporting(state, CARRIER)
    assert len(got) == 1, "effet 1140 non pose sur le porteur : %r" % (out,)
    assert out["tilesFreed"] == [(0, 3)] and out["placed"] is True, out


def test_the_effect_duration_is_two_TURNS_not_two_ROUNDS(state):
    """LE DISCRIMINANT du `turns`. `Nullable<int>(2)` est deja en TOURS ; un `TurnsFromRounds(2)`
    vaudrait `2 * state.turn_order_player_count`. On force le compteur de joueurs a 3 : si le port
    convertissait, on lirait 6."""
    state.turn_order_player_count = 3
    StormboyzStrikeTeleportAbility(CARRIER).execute_behaviour(state, _ev())
    got = _teleporting(state, CARRIER)
    assert [e.remaining_turns for e in got] == [2], (
        "duree = %r (attendu 2 TOURS, non convertis)" % ([e.remaining_turns for e in got],))


def test_the_effect_source_is_the_carrier_itself(state):
    """La surcharge native passe litteralement `0` en selecteur SOURCE d'`AddEffectBehaviour$$.ctor`
    -> fallback « la source EST la cible ». Ici cible == owner, donc source == owner."""
    StormboyzStrikeTeleportAbility(CARRIER).execute_behaviour(state, _ev())
    assert [e.source for e in _teleporting(state, CARRIER)] == [CARRIER]


def test_the_effect_lands_on_the_carrier_and_NOBODY_else(state):
    """CONTRE-BRAS de ciblage : ni l'allie, ni l'ennemi, ni aucune TUILE ne recoit 1140 (c'est ce qui
    distingue ce kit de `1011 TunnelingHorror`, dont le marqueur va sur la tuile visee)."""
    StormboyzStrikeTeleportAbility(CARRIER).execute_behaviour(state, _ev())
    assert _teleporting(state, ALLY) == [] and _teleporting(state, FOE) == []
    others = [k for k in state.effects.by_unit if int(k) != CARRIER and _teleporting(state, k)]
    assert others == [], "1140 pose hors du porteur : %r" % (others,)


def test_the_tree_is_a_sequence_of_the_two_native_leaves():
    """STRUCTURE (#149) : l'`op_BitwiseAnd` natif est une SEQUENCE de deux feuilles, dans cet ordre.
    Le retrait de tuiles DOIT preceder la pose -- l'effet est pose sur une unite deja sans tuile."""
    from engine.entities.behaviours import Seq
    from engine.runner.abilities.behaviours import AddEffect, RemoveUnitFromItsTiles
    t = stormboyz_strike_teleport_tree()
    assert isinstance(t, Seq)
    assert isinstance(t.left, RemoveUnitFromItsTiles) and t.left.remove_tile_from_unit is True
    assert isinstance(t.right, AddEffect)
    assert t.right.effect_type == TELEPORTING_IN
    assert t.right.duration_turns == 2 and t.right.duration_rounds is None
    assert t.right.source_from_target is True


# ------------------------------------------------------------------ 2. LES TROIS GATES

def test_gate_owner_is_actor(state):
    """`get_OwnerIsActor` -- l'evenement doit etre porte par le PORTEUR."""
    ab = StormboyzStrikeTeleportAbility(CARRIER)
    assert ab.matches(state, _ev(CARRIER)) is True
    assert ab.matches(state, _ev(ALLY)) is False


def test_gate_first_turn_only(state):
    """`AmountIsEqual(UnitTurnsStarted(Owner), Direct(0))` -- c'est le PREMIER tour ou rien.
    Mesure live : sur le premier etat lisible d'un runner le porteur est deja a 1."""
    ab = StormboyzStrikeTeleportAbility(CARRIER)
    assert ab.matches(state, _ev()) is True
    _set_turns_started(state, CARRIER, 1)
    assert ab.matches(state, _ev()) is False
    _set_turns_started(state, CARRIER, 0)
    assert ab.matches(state, _ev()) is True


def test_gate_has_not_moved(state):
    """`op_LogicalNot(HasFlag(Owner, UnitFlag.Moved = 0))`."""
    ab = StormboyzStrikeTeleportAbility(CARRIER)
    assert ab.matches(state, _ev()) is True
    set_moved_flag(state, CARRIER)
    assert ab.matches(state, _ev()) is False


# ------------------------------------------------------------------ 3. LE REGISTRE

def test_the_registry_wires_the_passive_on_the_ability_init_vector():
    assert ABILITY_TRIGGERS.get("StormboyzStrike") == [StormboyzStrikeTeleportAbility]
    assert StormboyzStrikeTeleportAbility.event_id == int(EventTriggerType.AbilityInit) == 0x21
    assert StormboyzStrikeTeleportAbility.TRIGGERED_ABILITY_ID == STORMBOYZ_STRIKE


# ------------------------------------------------------------------ 4. LES ENUMS QUALIFIES

def test_the_three_ids_are_read_in_the_right_enum():
    """Le nid de collisions du kit. Se tromper de table donne un port faux SANS erreur."""
    assert int(TriggeredAbilityType.StormboyzStrike) == 1141
    assert int(ActiveAbilityType.OverwhelmingWrath) == 1141        # meme id, autre enum
    assert int(EffectType.StormboyzStrike_TeleportingIn) == 1140
    assert int(ActiveAbilityType.ExemplarOfHate) == 1140           # meme id, autre enum
    assert int(TriggeredAbilityType.PowerUp_Hits) == 1140          # meme id, autre enum
    assert int(EffectType.StormboyzStrike_AlreadyUsedTile) == 1179
    assert int(ActiveAbilityType.CultDemagogue) == 1179            # meme id, autre enum


def test_the_triggered_ability_did_not_leak_into_the_ACTIVE_registry():
    """`ABILITY_CLASSES` est indexe par `ActiveAbilityType`. Y inscrire 1141 (qui y designe
    `OverwhelmingWrath`) ecraserait une AUTRE ability -- et c'est precisement pour ca que cette
    tranche n'a ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` : une `BaseTriggeredAbility` ne
    traverse jamais `IdunBattle.Operations.ActiveAbilityOperation`."""
    assert ABILITY_CLASSES.get(1141) is not StormboyzStrikeTeleportAbility
    assert ABILITY_CLASSES.get(1140) is not StormboyzStrikeTeleportAbility
    assert not hasattr(StormboyzStrikeTeleportAbility, "TARGETING_OPTIONS")
    assert not hasattr(StormboyzStrikeTeleportAbility, "ABILITY_ATTACK_TYPE")
