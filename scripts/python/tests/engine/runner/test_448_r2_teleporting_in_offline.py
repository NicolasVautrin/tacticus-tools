"""GARDE #448-r2 tranche 1/4 (OFFLINE PURE) -- `IdunBattle.Entities.Effects.Loki.ATeleportingEffect`
et son effet compagnon `IdunBattleLogic.Effects.TeleportMovingEffect`, specialises pour
`1035 TeleportStrike_TeleportingIn`.

CE QU'ELLE PROTEGE, et pourquoi chaque bloc peut regresser SILENCIEUSEMENT :

  1. **LES QUATRE `Triggered()`** de `$$CreateHandleTriggerAbilitiesInternal`, leur `event_id` et
     leur cardinalite. En perdre un ne casse RIEN : ca REPOUSSE seulement l'atterrissage a la fin du
     tour (le comportement d'avant #448-r2), donc aucune erreur, aucun crash -- juste une unite
     laissee non-ciblable, sur un pathfinder de teleport, et privee de ses passives deferrees
     pendant tout le reste de son activation.
  2. **`OwnerIsActor`**, exerce dans les DEUX sens sur les quatre : sans lui, l'atterrissage de
     N'IMPORTE QUELLE unite ferait atterrir toutes les autres.
  3. **`HasTile(Owner)`** sur T3 SEUL. Il est toujours vrai pour 1035 (le deep-strike reste SUR le
     plateau) mais c'est LUI qui, pour les trois soeurs, laisse une unite HORS PLATEAU garder son
     effet a travers la fin de son tour. Le poser sur T1/T2, ou l'oublier sur T3, se verrait
     seulement sur une tranche fille.
  4. **`turns: Nullable<int>(1)`** de T4 : deja en TOURS. Un `duration_rounds=1` rendrait
     `1 * nbJoueurs` -- facteur 2 sur un duel, qu'aucun crash ne signale.
  5. **La branche `Nothing()`** de T4 quand `GetMovingEffectType()` rend un `Nullable` VIDE : c'est
     le cas de `StormboyzStrike_TeleportingInEffect`, et la classe de base doit le porter AVANT
     qu'une tranche fille l'inscrive.
  6. **Le retrait de l'effet compagnon** `1036` par `TeleportMovingEffect`. Sans lui le marqueur
     survivrait au pas et `set_moved_flag` poserait `UnitFlag.Teleported` sur des deplacements
     ordinaires -- degradation PERMISSIVE.
  7. **L'INVENTAIRE de la famille** (cliquet) : les QUATRE derivees, leur `EffectType`, leur ability
     SOURCE avec son enum QUALIFIE et leur `*_Moving`. Trois d'entre elles ne sont PAS portees --
     le test le FIGE pour qu'une inscription ne se fasse pas en douce, sans confrontation.

Confrontation LIVE : `python scripts/python/probe_448_r2_teleporting_in.py`.
RE : `docs/rl/case-448-r2-ateleporting-effect-family.md`. ASCII only. Aucune VA en dur.
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
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.runner.components import (PositionComponent, UnitComponent,   # noqa: E402
                                      get_unit_feet, set_unit_feet)
from engine.runner.operations.triggers.base import TriggerEvent          # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.loki.teleporting_in import (      # noqa: E402
    ATeleportingAddMovingOnPreMove, ATeleportingRemoveOnAfterMove,
    ATeleportingRemoveOnPreUnitAbility, ATeleportingRemoveOnUnitFinishedTurn,
    TeleportMovingRemoveOnAfterMove,
    TeleportStrikeMovingRemoveOnAfterMove,
    TeleportStrikeTeleportingInAddMovingOnPreMove,
    TeleportStrikeTeleportingInRemoveOnAfterMove,
    TeleportStrikeTeleportingInRemoveOnPreUnitAbility,
    TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn,
    TELEPORT_STRIKE_MOVING, TELEPORT_STRIKE_TELEPORTING_IN)
from engine.runner.operations.effects import AddEffectOperation          # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

COLS, ROWS = 7, 7
CARRIER, ALLY, FOE = 10, 40, 20

#: La famille, telle que `data/symbols/<build>/frida/classes.tsv` la donne (parent
#: `ATeleportingEffect`) : (EffectType, ability SOURCE, enum QUALIFIE de cette source, `*_Moving`).
#: Les DEUX surcharges d'`IdunBattle.Core.AbilityOrEffect$$op_Implicit` sont ce qui distingue les
#: deux enums -- `$$set_TriggeredAbility` pour les deux premieres, `$$set_ActiveAbility` pour les
#: deux dernieres (lu a l'octet sur les quatre `$$.ctor`, qui partagent un corps DEDUPLIQUE).
FAMILY = [
    (EffectType.TeleportStrike_TeleportingIn, TriggeredAbilityType.TeleportStrike,
     "TriggeredAbilityType", EffectType.TeleportStrike_Moving),
    (EffectType.StormboyzStrike_TeleportingIn, TriggeredAbilityType.StormboyzStrike,
     "TriggeredAbilityType", None),
    (EffectType.FearOfTheUnseen_TeleportingIn, ActiveAbilityType.FearOfTheUnseen,
     "ActiveAbilityType", EffectType.FearOfTheUnseen_Moving),
    (EffectType.TitanhammerSquad_TeleportingIn, ActiveAbilityType.TitanhammerSquad,
     "ActiveAbilityType", EffectType.TitanhammerSquad_Moving),
]


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
        {"id": CARRIER, "visualId": "eldarAutarch", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": ALLY, "visualId": "eldarRanger", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 3}, "effects": []},
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


# ------------------------------------------------------------------ 1. LES QUATRE Triggered()

def test_the_registry_holds_exactly_the_four_triggers_of_the_native_ArraySet():
    """`ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` rend un `ArraySet` de QUATRE
    entrees ; le port en fait quatre classes (une par `event_id`, puisque le registre du port est
    indexe par event). Cardinalite ET evenements verrouilles."""
    got = EFFECT_TRIGGERS.get(TELEPORT_STRIKE_TELEPORTING_IN) or []
    assert [c.__name__ for c in got] == [
        "TeleportStrikeTeleportingInRemoveOnAfterMove",
        "TeleportStrikeTeleportingInRemoveOnPreUnitAbility",
        "TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn",
        "TeleportStrikeTeleportingInAddMovingOnPreMove"], [c.__name__ for c in got]
    assert [c.event_id for c in got] == [int(EventTriggerType.UnitAfterMove),        # On(0x04)
                                         int(EventTriggerType.PreUnitAbility),       # On(0x2a = PreUnitAbility)
                                         int(EventTriggerType.UnitFinishedTurn),     # On(0x28 = UnitFinishedTurn)
                                         int(EventTriggerType.PreUnitMove)]          # On(0x1f)
    assert all(c.effect_type == TELEPORT_STRIKE_TELEPORTING_IN for c in got)


def test_TeleportMovingEffect_registers_exactly_one_trigger():
    """`TeleportMovingEffect$$CreateHandleTriggerAbilitiesInternal` = UN SEUL `Triggered(On(4) &
    OwnerIsActor, RemoveEffect(EffectSelf))`."""
    got = EFFECT_TRIGGERS.get(TELEPORT_STRIKE_MOVING) or []
    assert [c.__name__ for c in got] == ["TeleportStrikeMovingRemoveOnAfterMove"]
    assert got[0].event_id == int(EventTriggerType.UnitAfterMove)
    assert issubclass(got[0], TeleportMovingRemoveOnAfterMove)


@pytest.mark.parametrize("cls", [TeleportStrikeTeleportingInRemoveOnAfterMove,
                                 TeleportStrikeTeleportingInRemoveOnPreUnitAbility,
                                 TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn])
def test_each_removal_trigger_drops_the_effect(state, cls):
    """Les TROIS retraits font la MEME chose (`BaseEffect$$GetRemoveEffectBehaviour` =
    `RemoveEffect(EffectSelf)`) -- seule leur condition differe."""
    _put(state, CARRIER, TELEPORT_STRIKE_TELEPORTING_IN, "TeleportStrike_TeleportingIn")
    assert len(_live(state, CARRIER, TELEPORT_STRIKE_TELEPORTING_IN)) == 1
    out = cls(CARRIER).execute_behaviour(state, _ev(cls.event_id))
    assert _live(state, CARRIER, TELEPORT_STRIKE_TELEPORTING_IN) == []
    assert out is not None and out["removed"] == 1, out


def test_the_moving_marker_is_dropped_by_its_own_trigger(state):
    _put(state, CARRIER, TELEPORT_STRIKE_MOVING, "TeleportStrike_Moving")
    assert len(_live(state, CARRIER, TELEPORT_STRIKE_MOVING)) == 1
    TeleportStrikeMovingRemoveOnAfterMove(CARRIER).execute_behaviour(
        state, _ev(EventTriggerType.UnitAfterMove))
    assert _live(state, CARRIER, TELEPORT_STRIKE_MOVING) == []


# ------------------------------------------------------------------ 2. OwnerIsActor

@pytest.mark.parametrize("cls", [TeleportStrikeTeleportingInRemoveOnAfterMove,
                                 TeleportStrikeTeleportingInRemoveOnPreUnitAbility,
                                 TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn,
                                 TeleportStrikeTeleportingInAddMovingOnPreMove,
                                 TeleportStrikeMovingRemoveOnAfterMove])
def test_owner_is_actor_is_exercised_both_ways(state, cls):
    """`get_OwnerIsActor` sur les CINQ classes. Sans lui, le pas d'une unite quelconque ferait
    atterrir toutes les autres."""
    _put(state, CARRIER, TELEPORT_STRIKE_TELEPORTING_IN, "TeleportStrike_TeleportingIn")
    _put(state, CARRIER, TELEPORT_STRIKE_MOVING, "TeleportStrike_Moving")
    trig = cls(CARRIER)
    assert trig.matches(state, _ev(cls.event_id, actor=CARRIER)) is True
    assert trig.matches(state, _ev(cls.event_id, actor=ALLY)) is False


# ------------------------------------------------------------------ 3. HasTile(Owner) sur T3 SEUL

def test_only_the_finished_turn_trigger_gates_on_HasTile(state):
    """T3 porte `HasTile(Owner)` ; T1, T2 et T4 ne le portent PAS. Le distinguo est INERTE pour 1035
    (le deep-strike ne quitte jamais le plateau) mais c'est ce gate qui, pour les trois soeurs,
    laisse une unite HORS PLATEAU garder son effet a travers la fin de son tour."""
    _put(state, CARRIER, TELEPORT_STRIKE_TELEPORTING_IN, "TeleportStrike_TeleportingIn")
    assert get_unit_feet(state, CARRIER) == [(0, 3)]
    assert TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn(CARRIER).matches(
        state, _ev(EventTriggerType.UnitFinishedTurn)) is True
    # HORS PLATEAU (`RemoveUnitFromTilesOperation` : empreinte VIDE + `PositionComponent` retiree)
    set_unit_feet(state, CARRIER, [])
    assert get_unit_feet(state, CARRIER) == []
    assert state.get_entity(CARRIER).get_component(PositionComponent) is None
    assert state.get_entity(CARRIER).get_component(UnitComponent).alive is True
    assert TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn(CARRIER).matches(
        state, _ev(EventTriggerType.UnitFinishedTurn)) is False, "T3 ignore HasTile(Owner)"
    for cls in (TeleportStrikeTeleportingInRemoveOnAfterMove,
                TeleportStrikeTeleportingInRemoveOnPreUnitAbility,
                TeleportStrikeTeleportingInAddMovingOnPreMove):
        assert cls(CARRIER).matches(state, _ev(cls.event_id)) is True, \
            "%s ne doit PAS porter le gate HasTile" % cls.__name__


# ------------------------------------------------------------------ 4./5. T4 : pose et Nothing()

def test_the_moving_effect_is_posed_for_one_TURN_not_one_ROUND(state):
    """`AddEffect(<type>, ..., Owner, turns: Nullable<int>(1))` -- deja en TOURS. On force le compteur
    de joueurs a 3 : si le port convertissait (`TurnsFromRounds`), on lirait 3."""
    state.turn_order_player_count = 3
    _put(state, CARRIER, TELEPORT_STRIKE_TELEPORTING_IN, "TeleportStrike_TeleportingIn")
    out = TeleportStrikeTeleportingInAddMovingOnPreMove(CARRIER).execute_behaviour(
        state, _ev(EventTriggerType.PreUnitMove))
    got = _live(state, CARRIER, TELEPORT_STRIKE_MOVING)
    assert out is not None and out["placed"] is True, out
    assert [e.remaining_turns for e in got] == [1], (
        "duree = %r (attendu 1 TOUR, non converti)" % ([e.remaining_turns for e in got],))
    assert [e.source for e in got] == [CARRIER], "source != cible (fallback natif source=cible)"


def test_an_empty_GetMovingEffectType_takes_the_Nothing_branch(state):
    """La classe de BASE rend `MOVING_EFFECT_TYPE = None` = `Nullable` VIDE -> branche `Nothing()`.
    C'est le cas de `StormboyzStrike_TeleportingInEffect` (son `GetMovingEffectType` a un corps
    TRIVIAL `return 0`), et ce comportement doit exister AVANT qu'une tranche fille l'inscrive."""
    class _Silent(ATeleportingAddMovingOnPreMove):
        effect_type = TELEPORT_STRIKE_TELEPORTING_IN
    _put(state, CARRIER, TELEPORT_STRIKE_TELEPORTING_IN, "TeleportStrike_TeleportingIn")
    trig = _Silent(CARRIER)
    assert trig.MOVING_EFFECT_TYPE is None
    assert trig.matches(state, _ev(EventTriggerType.PreUnitMove)) is True   # la CONDITION passe
    assert trig.execute_behaviour(state, _ev(EventTriggerType.PreUnitMove)) is None
    assert _live(state, CARRIER, TELEPORT_STRIKE_MOVING) == []


def test_the_two_neutral_vslots_collapse_to_true(state):
    """`GetAdditionalRemoveTriggers` (vslot 0x738) et `GetCustomMovingEffectCondition` (0x748) ont un
    corps de BASE qui rend `<DSLTriggers+0x40>` -- le conjonct NEUTRE (la MEME classe que
    `<+0x70>`, dont `BaseEffect$$NeedsRefreshing` traite la presence comme « pas de condition »).
    Le port les COLLAPSE a `True` ; une tranche fille les SURCHARGE."""
    _put(state, CARRIER, TELEPORT_STRIKE_TELEPORTING_IN, "TeleportStrike_TeleportingIn")
    ev_move = _ev(EventTriggerType.UnitAfterMove)
    ev_pre = _ev(EventTriggerType.PreUnitMove)
    assert ATeleportingRemoveOnAfterMove(CARRIER)._additional_remove_triggers(state, ev_move) is True
    assert ATeleportingRemoveOnPreUnitAbility(CARRIER)._additional_remove_triggers(
        state, ev_move) is True
    assert ATeleportingRemoveOnUnitFinishedTurn(CARRIER)._additional_remove_triggers(
        state, ev_move) is True
    t4 = ATeleportingAddMovingOnPreMove(CARRIER)
    assert t4._additional_remove_triggers(state, ev_pre) is True
    assert t4._custom_moving_condition(state, ev_pre) is True


# ------------------------------------------------------------------ 7. INVENTAIRE de la famille

def test_the_family_inventory_is_frozen():
    """CLIQUET. Les QUATRE derivees d'`ATeleportingEffect`, leur `EffectType`, leur ability SOURCE
    (enum QUALIFIE) et leur `*_Moving`. Le test verrouille aussi les ids : 1035/1140/1238/1573."""
    assert [int(e) for e, _s, _q, _m in FAMILY] == [1035, 1140, 1238, 1573]
    assert [int(s) for _e, s, _q, _m in FAMILY] == [1037, 1141, 1115, 1231]
    assert [(int(m) if m is not None else None) for _e, _s, _q, m in FAMILY] == \
        [1036, None, 1241, 1574]
    assert [q for _e, _s, q, _m in FAMILY] == ["TriggeredAbilityType", "TriggeredAbilityType",
                                               "ActiveAbilityType", "ActiveAbilityType"]


def test_the_unconfronted_sisters_are_still_out_of_the_registry():
    """Les soeurs NON CONFRONTEES (1140 -> #448-r2b, 1573 -> #448-r2d) et le `*_Moving` de la
    seconde (1574) ne sont PAS au registre : chacune est une TRANCHE FILLE, a confronter sur SON
    porteur. Ce test tombe des qu'une inscription se fait -- ce qui est l'intention : elle doit
    s'accompagner de sa confrontation, pas se glisser en douce.

    1238 / 1241 sont SORTIES de cette liste par #448-r2c, qui les a confrontees
    (`probe_448_r2c_fear_of_the_unseen.py`, `test_448_r2c_*_live.py`)."""
    for eff in (EffectType.StormboyzStrike_TeleportingIn,
                EffectType.TitanhammerSquad_TeleportingIn,
                EffectType.TitanhammerSquad_Moving):
        assert EFFECT_TRIGGERS.get(int(eff)) is None, (
            "%s est entree au registre sans sa tranche : elle doit etre CONFRONTEE "
            "(porteur, chemin, gardes) avant, cf. docs/rl/case-448-r2-ateleporting-effect-family.md"
            % eff.name)
