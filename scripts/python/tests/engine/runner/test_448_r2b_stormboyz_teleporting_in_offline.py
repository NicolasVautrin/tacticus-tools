"""GARDE #448-r2b tranche 2/4 (OFFLINE PURE) -- `1140 StormboyzStrike_TeleportingIn`, la seule
derivee d'`IdunBattle.Entities.Effects.Loki.ATeleportingEffect` SANS `*_Moving`.

CE QU'ELLE PROTEGE, et pourquoi chaque bloc peut regresser SILENCIEUSEMENT :

  1. **L'INSCRIPTION des quatre `Triggered()`** de la base, avec leurs `event_id`. En perdre un ne
     casse rien : l'unite reste seulement non-ciblable et sur son pathfinder de teleport plus
     longtemps que le natif -- degradation PERMISSIVE, sans erreur ni crash.
  2. **La branche `Nothing()` de T4** : `MOVING_EFFECT_TYPE is None`. C'est le point PROPRE de
     cette tranche, et il ne se deduit PAS d'une absence de symbole -- la surcharge
     `StormboyzStrike_TeleportingInEffect$$GetMovingEffectType` EXISTE (vslot 0x758, trouvee a la
     profondeur 0 par le RPC `resolveMethodPtr`), son corps est DEDUPLIQUE avec
     `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId` et vaut `xor eax, eax ; ret` :
     `Nullable<EffectType>` (int32 + bool, 8 octets) revient dans RAX, donc `hasValue = 0`.
     Un port qui lui donnerait un `*_Moving` par SYMETRIE avec ses trois soeurs poserait un
     marqueur qui n'existe pas -- et le test verifie AUSSI qu'aucun `StormboyzStrike_Moving`
     n'existe dans l'`EffectType` du build.
  3. **Le gate `HasTile(Owner)` de T3**, exerce sur ses DEUX bras. 1140 est la SEULE des quatre
     dont le poseur (`...StormboyzStrike_TeleportAbility$$CreateBehaviour`) appelle
     `RemoveUnitFromItsTiles` : sous 1140 l'unite est HORS PLATEAU, `HasTile` est FAUX, T3 ne fire
     pas et l'effet SURVIT a la fin de son tour. Un port qui perdrait le gate le retirerait --
     l'unite redeviendrait ciblable et sortirait du pathfinder de teleport en pleine descente.
  4. **L'ABSENCE de couche imperative derriere le retrait** : contrairement a 1035, la
     specialisation de 1140 ne porte PAS `_TeleportStrikeLandingMixin`. Le regime est l'inverse :
     c'est `On(0x21 = AbilityInit)` qui POSE 1140, donc les owner-effects du porteur sont deja
     initialises quand l'effet arrive (mesure live : volet E1b du probe, le porteur greffe arrive
     sous 1140 avec ses `BeastSlayer_*`). Ajouter le mixin ici serait une couche SPECULATIVE.
  5. **Le DOMAINE de non-ciblabilite** : le flag `UnitFlag 0x11` vient de
     `IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal`, donc de la BASE et non
     de l'effet feuille. Le port en fait un domaine (`UNTARGETABLE_EFFECT_TYPES`) et non une
     constante. 1238 / 1573 / `JustSummonedEffect` en restent DEHORS tant que leur tranche n'est
     pas confrontee -- un ajout speculatif retirerait des cibles a l'IA sans mesure.

Confrontation LIVE : `python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py`.
RE : `docs/rl/case-448-r2b-stormboyz-teleporting-in.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402
from engine.ai.state_bridge import _is_untargetable                      # noqa: E402
from engine.entities.effects_state import EffectsState  # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects.aura_selectors import (                     # noqa: E402
    UNTARGETABLE_EFFECT_TYPES, is_targetable)
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.components import (PositionComponent, UnitComponent,   # noqa: E402
                                      get_unit_feet, set_unit_feet)
from engine.runner.operations.triggers.base import TriggerEvent          # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.dispatch.turn import (            # noqa: E402
    unit_finished_turn_triggers)
from engine.runner.operations.triggers.loki.teleporting_in import (      # noqa: E402
    ATeleportingRemoveTrigger,
    STORMBOYZ_STRIKE_TELEPORTING_IN, TELEPORT_STRIKE_TELEPORTING_IN,
    StormboyzStrikeTeleportingInAddMovingOnPreMove,
    StormboyzStrikeTeleportingInRemoveOnAfterMove,
    StormboyzStrikeTeleportingInRemoveOnPreUnitAbility,
    StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn)
from engine.runner.operations.effects import AddEffectOperation          # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

COLS, ROWS = 7, 7
CARRIER, ALLY, FOE = 10, 40, 20

REMOVE_CLASSES = [StormboyzStrikeTeleportingInRemoveOnAfterMove,
                  StormboyzStrikeTeleportingInRemoveOnPreUnitAbility,
                  StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn]


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
        {"id": CARRIER, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": ALLY, "visualId": "orksWarboss", "alive": True, "team": 1, "owner": 1,
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


def _off_board(st, uid):
    """`...StormboyzStrike_TeleportAbility$$CreateBehaviour` -> `RemoveUnitFromItsTiles(Owner,
    removeTileFromUnit: true)`, dont le port mirror le collapse par `set_unit_feet(..., [])` :
    empreinte VIDE **et** `PositionComponent` retiree (#366-r1/#438)."""
    set_unit_feet(st, int(uid), [])


# --------------------------------------------------------- 1. l'inscription au registre

def test_the_registry_holds_the_four_triggers_for_1140():
    got = EFFECT_TRIGGERS.get(STORMBOYZ_STRIKE_TELEPORTING_IN) or []
    assert [c.__name__ for c in got] == [
        "StormboyzStrikeTeleportingInRemoveOnAfterMove",
        "StormboyzStrikeTeleportingInRemoveOnPreUnitAbility",
        "StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn",
        "StormboyzStrikeTeleportingInAddMovingOnPreMove"], [c.__name__ for c in got]
    assert [c.event_id for c in got] == [int(EventTriggerType.UnitAfterMove),      # On(0x04)
                                         int(EventTriggerType.PreUnitAbility),     # On(0x2a)
                                         int(EventTriggerType.UnitFinishedTurn),   # On(0x28)
                                         int(EventTriggerType.PreUnitMove)]        # On(0x1f)
    assert all(c.effect_type == STORMBOYZ_STRIKE_TELEPORTING_IN for c in got)
    assert int(EffectType.StormboyzStrike_TeleportingIn) == 1140


# --------------------------------------------------------- 2. la branche Nothing() de T4

def test_T4_declares_no_moving_effect_and_poses_nothing(state):
    """`GetMovingEffectType()` rend un `Nullable` VIDE -> `Nothing()`. T4 doit MATCHER (sa
    condition est vraie) et ne RIEN poser : c'est la difference entre << la condition est fausse >>
    et << la condition est vraie mais le behaviour est `Nothing()` >>, et seule la seconde est le
    natif."""
    assert StormboyzStrikeTeleportingInAddMovingOnPreMove.MOVING_EFFECT_TYPE is None
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    before = sorted(int(e.effect_type)
                    for e in (state.effects.by_unit.get(CARRIER) or []) if not e.consumed)
    trig = StormboyzStrikeTeleportingInAddMovingOnPreMove(CARRIER)
    assert trig.matches(state, _ev(EventTriggerType.PreUnitMove)) is True
    assert trig.execute_behaviour(state, _ev(EventTriggerType.PreUnitMove)) is None
    after = sorted(int(e.effect_type)
                   for e in (state.effects.by_unit.get(CARRIER) or []) if not e.consumed)
    assert after == before, "T4 a POSE quelque chose alors que le Nullable natif est VIDE"


def test_no_StormboyzStrike_Moving_exists_in_the_build_enum():
    """CLIQUET sur la SOURCE. Les `*_Moving` du build sont EXACTEMENT trois -- ceux des trois
    soeurs -- et `TeleportMovingEffect$$.ctor` n'a que trois appelants. Si un
    `StormboyzStrike_Moving` apparaissait, le corps `xor eax,eax ; ret` de
    `StormboyzStrike_TeleportingInEffect$$GetMovingEffectType` serait a relire."""
    moving = sorted(m.name for m in EffectType if m.name.endswith("_Moving"))
    assert moving == ["FearOfTheUnseen_Moving", "TeleportStrike_Moving",
                      "TitanhammerSquad_Moving"], moving


# --------------------------------------------------------- 3. le gate HasTile de T3

def test_T3_keeps_the_effect_while_the_carrier_is_off_board(state):
    """LE point de la tranche. Hors plateau -> `HasTile(Owner)` FAUX -> T3 ne matche PAS et
    l'effet SURVIT ; une fois repose (ce que fait `...StormboyzStrike_FallbackAbility`, NON
    PORTEE), le MEME trigger retire."""
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    _off_board(state, CARRIER)
    assert get_unit_feet(state, CARRIER) == []
    assert state.get_entity(CARRIER).get_component(PositionComponent) is None
    assert state.get_entity(CARRIER).get_component(UnitComponent).alive is True

    # On passe par le VECTEUR de production (`On(0x28)`), pas par `execute_behaviour` : c'est
    # `evaluate_trigger_operation` qui evalue `matches` avant le behaviour -- exactement comme le
    # `Triggered(cond, behaviour)` natif. Appeler le behaviour en direct court-circuiterait le gate
    # qu'on veut precisement mesurer.
    t3 = StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn(CARRIER)
    assert t3.matches(state, _ev(EventTriggerType.UnitFinishedTurn)) is False
    unit_finished_turn_triggers(state, CARRIER)
    assert len(_live(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN)) == 1, \
        "T3 a retire l'effet d'une unite HORS PLATEAU -- le gate `HasTile(Owner)` est perdu"

    set_unit_feet(state, CARRIER, [(2, 2)])                 # sortie observee du Fallback
    assert t3.matches(state, _ev(EventTriggerType.UnitFinishedTurn)) is True
    unit_finished_turn_triggers(state, CARRIER)
    assert _live(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN) == []


def test_only_T3_carries_the_HasTile_gate(state):
    """T1, T2 et T4 ne portent PAS `HasTile` : hors plateau ils matchent quand meme. C'est ce qui
    permet a T1 de retirer l'effet a l'arrivee du pas de teleport (l'unite part de nulle part)."""
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    _off_board(state, CARRIER)
    for cls in (StormboyzStrikeTeleportingInRemoveOnAfterMove,
                StormboyzStrikeTeleportingInRemoveOnPreUnitAbility,
                StormboyzStrikeTeleportingInAddMovingOnPreMove):
        assert cls(CARRIER).matches(state, _ev(cls.event_id)) is True, \
            "%s ne doit PAS porter le gate HasTile" % cls.__name__


@pytest.mark.parametrize("cls", REMOVE_CLASSES)
def test_each_removal_trigger_drops_1140_when_its_condition_holds(state, cls):
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    assert len(_live(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN)) == 1
    out = cls(CARRIER).execute_behaviour(state, _ev(cls.event_id))
    assert _live(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN) == []
    assert out is not None and out["removed"] == 1, out


@pytest.mark.parametrize("cls", REMOVE_CLASSES + [
    StormboyzStrikeTeleportingInAddMovingOnPreMove])
def test_owner_is_actor_is_exercised_both_ways(state, cls):
    """`get_OwnerIsActor` sur les QUATRE. Sans lui, le pas d'une unite quelconque ferait atterrir
    tous les Stormboyz du plateau."""
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    trig = cls(CARRIER)
    assert trig.matches(state, _ev(cls.event_id, actor=CARRIER)) is True
    assert trig.matches(state, _ev(cls.event_id, actor=ALLY)) is False


# --------------------------------------------------------- 4. AUCUNE couche imperative

@pytest.mark.parametrize("cls", REMOVE_CLASSES)
def test_no_deferred_passive_layer_is_attached_to_1140(state, cls):
    """1140 ne porte PAS `_TeleportStrikeLandingMixin` : `_after_remove` doit etre celui de la
    BASE (liste vide). Le regime << passives DEFERREES >> est propre a 1035 -- pour 1140 c'est
    `On(0x21 = AbilityInit)` lui-meme qui pose l'effet, donc les owner-effects du porteur sont
    deja la (mesure live E1b). L'`_after_remove` remonte aussi dans le retour du trigger, ce que
    le test verifie plutot que d'inspecter la MRO."""
    assert cls._after_remove is ATeleportingRemoveTrigger._after_remove, (
        "%s a acquis une couche imperative d'atterrissage -- le natif ne fait que "
        "`RemoveEffect(EffectSelf)`" % cls.__name__)
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    out = cls(CARRIER).execute_behaviour(state, _ev(cls.event_id))
    assert out is not None and out["after"] == [], out


# --------------------------------------------------------- 5. le domaine UntargetableEffect

def test_1140_makes_its_carrier_untargetable(state):
    """`UntargetableEffect$$ApplyInternal` -> `UnitFlagsComponent$$Add(0x11)` : le flag vient de la
    BASE, donc de TOUTE derivee. Les deux lecteurs du port (`_is_untargetable` cote decision,
    `is_targetable` cote selecteur d'aura) partagent le MEME domaine."""
    assert _is_untargetable(state, CARRIER) is False
    assert is_targetable(state, CARRIER) is True
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    assert _is_untargetable(state, CARRIER) is True
    assert is_targetable(state, CARRIER) is False
    assert _is_untargetable(state, ALLY) is False          # exerce dans les deux sens


def test_the_untargetable_domain_holds_only_the_confronted_slices():
    """CLIQUET. Fermeture NATIVE de `UntargetableEffect` = les 4 `ATeleportingEffect` +
    `JustSummonedEffect`. Le port n'inscrit que ce qu'il a CONFRONTE SUR CE CANAL : 1035 (#448-r2)
    et 1140 (#448-r2b).

    ⚠ `1238` est DEHORS bien que ses TRIGGERS soient portes (#448-r2c) : cette tranche-la a
    explicitement laisse la face DECISION en RESIDU NOMME, hors de son perimetre. Le test dit donc
    << non confronte SUR CE CANAL >>, pas << non porte >> -- les deux ne coincident plus.
    `1573` arrive avec #448-r2d ; `JustSummonedEffect` n'a aucune tranche ouverte (#448-r2b-r1).
    Ce test tombe des qu'une inscription se fait sans sa confrontation."""
    assert sorted(UNTARGETABLE_EFFECT_TYPES) == [TELEPORT_STRIKE_TELEPORTING_IN,
                                                 STORMBOYZ_STRIKE_TELEPORTING_IN]
    for eff in (EffectType.FearOfTheUnseen_TeleportingIn,
                EffectType.TitanhammerSquad_TeleportingIn):
        assert int(eff) not in UNTARGETABLE_EFFECT_TYPES, (
            "%s inscrite au domaine sans que la face DECISION soit CONFRONTEE (le port de ses "
            "triggers ne suffit pas -- cf. #448-r2b-r1)" % eff.name)
