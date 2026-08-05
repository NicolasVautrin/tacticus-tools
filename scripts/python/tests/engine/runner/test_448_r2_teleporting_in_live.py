"""GARDE LIVE #448-r2 tranche 1/4 -- `IdunBattle.Entities.Effects.Loki.ATeleportingEffect` sur
`1035 TeleportStrike_TeleportingIn` : le port et le NATIF, sur le MEME etat de depart.

DEUX gestes, UN SEUL runner (deux unites deep-strike du pool : `eldarAutarch` et `spaceRockfist`) :

  T1 + T4  le MOUVEMENT -- `On(0x1f PreUnitMove)` pose `1036 TeleportStrike_Moving`,
           `On(0x04 UnitAfterMove)` retire 1035 (et 1036). L'atterrissage est mesure NUMERIQUEMENT :
           l'aura `PathOfCommand_ExtraDmg` de l'autarch, DEFEREE tant qu'il descend, devient un
           `+Attack` chez son allie DES le pas -- pas a la fin du tour.
  T3       la FIN D'ACTIVATION -- `On(0x28 UnitFinishedTurn) & HasTile(Owner)` sur une unite qui n'a
           ni bouge ni caste.

T2 (`On(0x2a PreUnitAbility)`) est confronte par le probe, qui doit amener un ennemi au contact :
`python scripts/python/probe_448_r2_teleporting_in.py` (2 couples board/seed, + contre-epreuve
`--mutate`).

CE QUI REGRESSERAIT SANS CETTE GARDE : le port d'avant #448-r2 faisait atterrir les unites
deep-strike dans `EndTurnOperation`. Le porteur restait donc NON-CIBLABLE, sur le pathfinder de
teleport et SANS ses passives deferrees pendant tout le reste de son activation -- aucune erreur,
aucun crash, juste un ecart d'Attack de 400 (rank 17) chez l'allie. ASCII only.
"""
from __future__ import annotations

import pytest

import gameconfig as GC
import probe_448_r3_move_step_atomicity as R3
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.effects import aura_attack_bonus_from_allies
from engine.entities.stats import StatType
from engine.playbook.scene import Scene
from engine.runner.components import StatsComponent, UnitComponent, get_unit_feet
from engine.runner.messages import MoveUnitMessage
from engine.runner.operations.turnflow import FinishUnitTurnOperation
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

DS_UNITS = "eldarAutarch,adeptCanoness,spaceRockfist"
TELEPORTING_IN = int(EffectType.TeleportStrike_TeleportingIn)   # 1035
MOVING = int(EffectType.TeleportStrike_Moving)                  # 1036


def _capture(rpc, rid) -> dict:
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 90),
            "ob": rpc("observeBattle", {"runnerId": rid}, 40),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
            "tm": rpc("tileMeta", {"runnerId": rid}, 60),
            "bg": rpc("boardGraph", {"runnerId": rid}, 60)}


def _state(cap):
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def _find(st, sub):
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and sub.lower() in str(uc.visual_id).lower():
            return int(uid)
    return None


def _effects(st, uid) -> list:
    return sorted((getattr(x, "name", None) or str(getattr(x, "effect_type", "?")))
                  for x in (st.effects.by_unit.get(int(uid)) or []) if not x.consumed)


def _attack(st, uid):
    sc = st.get_entity(int(uid)).get_component(StatsComponent)
    return sc.ctx.stat(StatType.ATTACK) if sc is not None else None


def _aura_bonus(st, att_id) -> int:
    """MEME canal que `test_deep_strike_live.py` : `aura_attack_bonus_from_allies`. Le port lit
    l'aura a la QUERY (elle n'est pas materialisee dans le `UnitStats`), alors qu'un etat RECHARGE
    du natif la porte deja dans `Attack` -- d'ou la comparaison bonus/DELTA."""
    scene = Scene.from_state(st)
    agu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    ctx = {"att_id": att_id, "att_pos": scene.pos(att_id), "att_team": scene.team(att_id),
           "att_grand_alliance": agu.get("GrandAllianceId"), "att_faction": agu.get("FactionId"),
           "board": scene.board}
    carriers = [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("GrandAllianceId"),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("FactionId"), scene.effects(uid))
                for uid in scene.pos_by_id if uid != att_id and (scene.hp(uid) or 0) > 0]
    return aura_attack_bonus_from_allies(carriers, ctx)


@pytest.fixture(scope="module")
def stage(rpc, build_runner):
    rid = build_runner(seed="777", extra=["--p-units", DS_UNITS, "--no-ai"])["rid"]
    cap = _capture(rpc, rid)
    st, board = _state(cap)
    autarch, ally, rockfist = _find(st, "eldarAutarch"), _find(st, "adeptCanoness"), \
        _find(st, "spaceRockfist")
    if autarch is None or ally is None or rockfist is None:
        pytest.skip("roster non deploye (pool/spawn)")
    if not st.effects.has_effect(autarch, effect_type=TELEPORTING_IN):
        pytest.skip("l'autarch n'arrive pas en teleport-in")
    return {"rid": rid, "autarch": autarch, "ally": ally, "rockfist": rockfist, "board": board}


def test_the_carrier_starts_in_teleport_in_without_its_deferred_passives(rpc, stage):
    """PRE-CONDITION, et c'est une MESURE : sans elle les deux tests suivants ne discrimineraient
    rien. `remaining = 2` = `TurnsFromRounds(1)` a deux joueurs."""
    st, _b = _state(_capture(rpc, stage["rid"]))
    got = [e for e in st.effects.by_unit.get(stage["autarch"], []) if not e.consumed]
    assert [e.effect_type for e in got] == [TELEPORTING_IN], _effects(st, stage["autarch"])
    assert [e.remaining_turns for e in got] == [2]
    assert _aura_bonus(st, stage["ally"]) == 0, "l'aura projette AVANT l'atterrissage"


def test_a_full_replay_of_the_move_through_the_runner_agrees_too(rpc, stage):
    """Meme geste, mais par la voie COMPLETE (`Runner.apply(MoveUnitMessage)`) plutot que par
    l'Operation decoupee : c'est le chemin de production, et il doit rendre le MEME etat. Ce test
    ne mute QUE l'etat offline -- il precede donc celui qui joue le pas LIVE."""
    rid, autarch = stage["rid"], stage["autarch"]
    st, _b = _state(_capture(rpc, rid))
    assert st.effects.has_effect(autarch, effect_type=TELEPORTING_IN)
    mv = (rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}).get("units") or []
    legal = sorted({(t.get("col"), t.get("row")) for u in mv if u.get("unitId") == autarch
                    for t in (u.get("tiles") or [])})
    if not legal:
        pytest.skip("aucune tuile legale (montage)")
    Runner(st).install_default_handlers(20).apply(MoveUnitMessage(autarch, tuple(legal[0])))
    alive = [int(e.effect_type) for e in st.effects.by_unit.get(autarch, []) if not e.consumed]
    assert TELEPORTING_IN not in alive, alive
    assert MOVING not in alive, alive
    assert get_unit_feet(st, autarch) == [tuple(legal[0])]


def test_the_move_poses_the_moving_marker_then_lands_the_carrier(rpc, stage):
    """T4 puis T1, DANS LE MEME PAS, observe DE L'INTERIEUR (#448-r3).

    ⚠ CE TEST NE DECOUPE PLUS LE PAS, et c'est une correction de MONTAGE, pas d'intention. Il
    appelait `MoveUnitOperation.execute()` puis `after_move_triggers()`, en supposant que le premier
    s'arretait avant le vecteur. `9767a8e4` (#448-r1-r1-r2-r1) a REPLIE le vecteur DANS l'Operation
    -- le premier appel joue desormais le pas ENTIER, donc 1036 etait pose PUIS retire avant qu'on
    regarde, et le second appel REJOUAIT un vecteur deja joue. Le test rougissait en accusant le
    port d'avoir perdu T4, qui fire normalement.

    LE REPLI EST LE MIRROR : `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` a
    DEUX call-sites dans tout le binaire, les DEUX dans
    `IdunBattle.Operations.MoveUnitOperation$$Execute`, et
    `IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers` en a ZERO (corps INLINE dans
    le meme `Execute`). Le pas natif est donc ATOMIQUE : aucun etat natif RECHARGE ne peut porter
    1036. C'est pourquoi l'etat intermediaire se capte par INSTRUMENTATION du vecteur
    (`probe_448_r3_move_step_atomicity.play_step_instrumented`) et non en coupant le pas.

    TEMOIN NATIF NON-NUL, mesure (`probe_448_r3_move_step_atomicity.py`, 2 couples board/seed) : la
    cascade d'events du `applyAction` publie `Effect_Refresh <<TeleportStrike_Moving>>` avec
    `ActivateEffect`/`ReceiveEffect` aux events 2-3, `ChangePosition` a l'event 5, puis
    `LoseEffect`/`DeactivateEffect` aux events 16-17 -- 1036 ENCADRE le deplacement."""
    rid, autarch, ally, board = stage["rid"], stage["autarch"], stage["ally"], stage["board"]
    st, _b = _state(_capture(rpc, rid))
    apos = next(iter(get_unit_feet(st, ally)), None)
    mv = (rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}).get("units") or []
    legal = {(t.get("col"), t.get("row")) for u in mv if u.get("unitId") == autarch
             for t in (u.get("tiles") or [])}
    dest = next((board.coord(t) for t in board.neighbours(board.id_at(apos[0], apos[1]))
                 if board.coord(t) in legal), None)
    if dest is None:
        pytest.skip("aucune tuile LEGALE adjacente a l'allie (montage)")

    before_ally_attack = _attack(st, ally)
    # --- PORT : le pas joue UNE SEULE FOIS, l'etat intermediaire capte de l'interieur.
    step = R3.play_step_instrumented(st, autarch, dest)
    assert len(step["calls"]) == 1, (
        "le vecteur after-move a ete joue %d fois pour UN pas (attendu 1, par "
        "MoveUnitOperation.execute)" % len(step["calls"]))
    mid = step["calls"][0]["effects"]
    assert MOVING in mid, "T4 n'a pas pose 1036 pendant le pas : %r" % (mid,)
    assert TELEPORTING_IN in mid, "1035 deja retire pendant le pas : T1 fire trop tot"
    port_eff = _effects(st, autarch)
    port_aura = _aura_bonus(st, ally)
    assert MOVING not in [int(e.effect_type) for e in st.effects.by_unit.get(autarch, [])
                          if not e.consumed], "1036 survit au pas"

    # --- NATIF : le MEME pas, puis rechargement.
    r = rpc("applyAction", {"runnerId": rid,
                            "action": {"kind": "move", "unitId": autarch,
                                       "to": {"col": int(dest[0]), "row": int(dest[1])}}}, 60) or {}
    # `mutated` vit dans `actions[0]`, pas au niveau racine -- et un move HORS POOL est un NO-OP
    # SILENCIEUX (`ok=true, mutated=false`, H55) : sans ce controle, un montage rate se lirait
    # comme un desaccord de PORT.
    assert (r.get("actions") or [{}])[0].get("mutated") is True, \
        "le move live n'a RIEN mute (montage) : %r" % (r,)
    st2, _b2 = _state(_capture(rpc, rid))
    native_eff = _effects(st2, autarch)
    live_delta = (_attack(st2, ally) or 0) - (before_ally_attack or 0)

    assert "TeleportStrike_TeleportingIn" not in native_eff, \
        "le natif GARDE 1035 apres le pas -- la mesure ne discrimine rien"
    assert port_eff == native_eff, "port=%r != natif=%r" % (port_eff, native_eff)
    assert live_delta > 0, "l'aura n'a pas mordu LIVE (delta=%r) -- mesure vide" % live_delta
    assert port_aura == live_delta, "aura port %r != delta Attack natif %r" % (port_aura, live_delta)


def test_finishing_the_turn_lands_a_carrier_that_did_nothing(rpc, stage):
    """T3 -- `On(0x28 UnitFinishedTurn) & OwnerIsActor & HasTile(Owner)`. Le vecteur `On(0x28 = UnitFinishedTurn)`
    lui-meme etait un RESIDU NOMME cote port jusqu'a #448-r2 (aucun consommateur) ; c'est ce
    trigger-ci qui l'ouvre."""
    rid, rockfist = stage["rid"], stage["rockfist"]
    st, _b = _state(_capture(rpc, rid))
    if not st.effects.has_effect(rockfist, effect_type=TELEPORTING_IN):
        pytest.skip("le second deep-strike a deja atterri (ordre des tests)")
    FinishUnitTurnOperation.execute(st, rockfist)
    port_eff = _effects(st, rockfist)
    assert "TeleportStrike_TeleportingIn" not in port_eff, port_eff

    r = rpc("applyAction", {"runnerId": rid,
                            "action": {"kind": "finish", "unitId": rockfist}}, 60) or {}
    assert (r.get("actions") or [{}])[0].get("ok") is True, r
    st2, _b2 = _state(_capture(rpc, rid))
    native_eff = _effects(st2, rockfist)
    assert "TeleportStrike_TeleportingIn" not in native_eff, \
        "le natif GARDE 1035 apres FinishUnitTurn -- la mesure ne discrimine rien"
    assert port_eff == native_eff, "port=%r != natif=%r" % (port_eff, native_eff)
