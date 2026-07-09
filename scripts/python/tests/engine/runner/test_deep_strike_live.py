"""Agrement DEEP-STRIKE (TeleportStrike) runner-engine CONFRONTE au natif LIVE.

Modele (ground truth live) : une unite deep-strike est posee on-board avec
`TeleportStrike_TeleportingIn` (1035 : non-ciblable, passives NON initialisees) ; a la FIN de
son 1er tour d'equipe elle ATTERRIT -> effet retire + passives init (aura PathOfCommand) ->
ciblable + auras projettent.

On confronte la transition OFFLINE (`load_state` + `EndTurnOperation`) au LIVE (`endturn`) :
  (1) etat pre-landing : non-ciblable, aura off ;
  (2) etat post-landing : ciblable, PathOfCommand pose, aura projette ;
  (3) FIDELITE numerique : la magnitude d'aura OFFLINE == le delta d'Attack LIVE across l'endturn.
Version/seed-independant (lit l'etat live, aucune valeur hardcodee). Skip si le build echoue ou
si la config ne produit pas d'Autarch deep-strike + allie adjacent.
"""
from __future__ import annotations

import pytest

import gameconfig as GC
from engine.runner.snapshot import load_state
from engine.runner.operations.turnflow import EndTurnOperation
from engine.runner.components import OwnerComponent, UnitComponent
from engine.ai.state_bridge import _is_untargetable, TELEPORT_STRIKE_TELEPORTING_IN
from engine.playbook.scene import Scene
from engine.entities.effects import aura_attack_bonus_from_allies

DS_UNITS = "eldarAutarch,eldarRanger"    # Autarch = deep-strike + PathOfCommand ; Ranger = allie Aeldari adjacent


def _find(state, vsub):
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc and vsub in str(uc.visual_id).lower():
            return uid
    return None


def _ranger_attack(rpc, rid, vis_by_id, ranger_id):
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    for u in (snap.get("units") or []):
        if u.get("entityId") == ranger_id:
            st = u.get("stats") or {}
            return st.get("attack") or st.get("damage")
    return None


def _aura_bonus(state, att_id):
    scene = Scene.from_state(state)
    _agu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    aura_ctx = {"att_id": att_id, "att_pos": scene.pos(att_id), "att_team": scene.team(att_id),
                "att_grand_alliance": _agu.get("GrandAllianceId"), "att_faction": _agu.get("FactionId"),
                "board": scene.board}
    carriers = [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("GrandAllianceId"),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("FactionId"), scene.effects(uid))
                for uid in scene.pos_by_id if uid != att_id and (scene.hp(uid) or 0) > 0]
    return aura_attack_bonus_from_allies(carriers, aura_ctx)


def test_deep_strike_landing_matches_native(rpc, build_runner):
    rid = build_runner(seed="777", extra=["--p-units", DS_UNITS])["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    obs = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (isinstance(dv, dict) and dv.get("units")):
        pytest.skip("decisionView vide")
    vis_by_id = {u["id"]: u.get("visualId") for u in dv.get("units")}

    state = load_state(dv, obs, snap)
    autarch = _find(state, "utarch")
    ranger = _find(state, "anger")
    if autarch is None or ranger is None:
        pytest.skip("Autarch/Ranger non deployes (pool/spawn)")
    # pre-condition : l'Autarch DOIT etre en teleport-in (sinon la config n'exerce pas le deep-strike)
    if not state.effects.has_effect(autarch, effect_type=TELEPORT_STRIKE_TELEPORTING_IN):
        pytest.skip("Autarch pas en teleport-in (deja pose ?)")

    # (1) PRE-LANDING : non-ciblable + aura off
    assert _is_untargetable(state, autarch) is True
    assert _aura_bonus(state, ranger) == 0, "aura PathOfCommand projette AVANT l'atterrissage"

    # delta d'Attack LIVE across un endturn (le natif atterrit a la fin du 1er tour de l'Autarch)
    att_before = _ranger_attack(rpc, rid, vis_by_id, ranger)
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30)
    att_after = _ranger_attack(rpc, rid, vis_by_id, ranger)
    live_delta = (att_after - att_before) if (att_before is not None and att_after is not None) else None

    # (2)/(3) POST-LANDING OFFLINE : EndTurnOperation (joueur finissant = proprietaire de l'Autarch)
    state.current_player_id = state.get_entity(autarch).get_component(OwnerComponent).player
    EndTurnOperation.execute(state, advance=False)

    assert _is_untargetable(state, autarch) is False, "toujours non-ciblable apres l'atterrissage"
    assert state.effects.has_effect(autarch, name="PathOfCommand_ExtraDmg"), \
        "PathOfCommand non initialise a l'atterrissage"
    off_bonus = _aura_bonus(state, ranger)
    assert off_bonus > 0, "aura PathOfCommand ne projette pas apres l'atterrissage"
    # (3) fidelite numerique : magnitude offline == delta live (si l'Attack live a ete lu)
    if live_delta is not None and live_delta > 0:
        assert off_bonus == live_delta, \
            f"aura offline {off_bonus} != delta Attack live {live_delta}"
