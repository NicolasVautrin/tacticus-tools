"""TURN FLOW (TF-A) — EndTurn -> ChangeTurn -> StartTurn, confronte au LIVE (replay-diff).

Valide le vecteur turn flow porte (`engine.runner.operations.turnflow`) :
  - `ChangeTurnOperation`/`find_next_player` @180e62570 : le `current_player` passe au joueur suivant ;
  - `EndTurnOperation.RefreshEffects` @180e6bf70 : les effets a duree de TOUTES les unites perdent 1 tour ;
  - `StartTurnOperation` @180ea3fb0 : compteur de tours du nouveau joueur incremente.

PROTOCOLE : build d'une bataille 2 equipes (necron vs necron, AUCUN trigger turn-start type TheBetrayer).
On capture S, on lit le joueur courant + les effets a duree. LIVE on `applyAction endturn` (fin du tour
courant -> flip + debut de tour suivant). OFFLINE on `load_state(S)` + applique `EndTurnMessage` via le
runner, et on confronte :
  • le `current_player` OFFLINE == le joueur courant LIVE apres endturn (FLIP exact) ;
  • pour chaque effet a duree qui SURVIT (remaining live > 0 apres), le remaining OFFLINE == remaining LIVE
    (tick d'1 tour) ; conditionnel (skip si aucun effet a duree).

DEFERE (non suivi offline, cf. turnflow.py) : cooldowns d'ability, boucliers, ActorStatistics, PickNextUnit.
ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import EndTurnMessage

# 2 equipes necron (pas de passive turn-start type TheBetrayer) -> flip propre, pas d'auto-action.
BUILD = ["--roster", "1", "--p-units", "necroWarden,necroOverlord",
         "--a-units", "necroWarden,necroOverlord"]


def _timed_effects(decision: dict) -> dict:
    """{(unit_id, effectType): remaining} pour les effets a duree (remaining>0) de decisionView."""
    out: dict[tuple, int] = {}
    for u in (decision.get("units") or []):
        uid = u.get("id")
        for e in (u.get("effects") or []):
            rem = e.get("remaining")
            et = e.get("effectType")
            if rem is not None and isinstance(rem, int) and rem > 0 and et is not None:
                out[(uid, et)] = rem
    return out


def test_turnflow_endturn_live(live_session, rpc, build_runner):
    rid = build_runner("777", extra=BUILD)["rid"]

    # capture S (avant endturn).
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    cur0 = dec.get("currentPlayer")
    if cur0 is None:
        pytest.skip("currentPlayer absent de S")
    eff0 = _timed_effects(dec)

    # LIVE : fin du tour courant -> flip + debut de tour suivant.
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": True}, 90)
    dec1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    cur_live = dec1.get("currentPlayer")
    eff_live = _timed_effects(dec1)

    # OFFLINE : load S + EndTurnMessage via le runner.
    state = load_state(dec, ob, snap)
    runner = Runner(state).install_default_handlers()
    runner.apply(EndTurnMessage(advance=True))
    cur_off = state.current_player_id

    print(f"\n[TURNFLOW] cur0={cur0} | live_next={cur_live} off_next={cur_off}")

    # 1. le LIVE a bien change de joueur (sinon le scenario n'exerce pas le flip).
    assert cur_live is not None and cur_live != cur0, \
        f"live n'a pas flip le joueur (cur0={cur0}, live={cur_live})"
    # 2. FLIP exact : offline == live.
    assert cur_off == cur_live, f"flip offline {cur_off} != live {cur_live}"
    # 3. compteur de tours du nouveau joueur incremente.
    assert state.turn_counts.get(cur_off, 0) >= 1, \
        f"turn_counts[{cur_off}] non incremente ({state.turn_counts})"

    # 4. tick d'effets a duree : pour chaque effet present dans S ET survivant live (remaining>0 apres),
    #    le remaining offline == remaining live (decrement d'1). Conditionnel (skip si aucun).
    checked = 0
    if state.effects is not None:
        for (uid, et), _r0 in eff0.items():
            live_rem = eff_live.get((uid, et))
            if live_rem is None or live_rem <= 0:
                continue  # effet expire/retire live -> hors scope du check de survie
            offs = [e for e in state.effects.by_unit.get(int(uid), [])
                    if e.effect_type == et and not e.consumed and not e.expired]
            if not offs:
                continue
            off_rem = offs[0].remaining_turns
            if off_rem is None:
                continue
            assert off_rem == live_rem, \
                f"tick effet u{uid}/{et}: offline remaining {off_rem} != live {live_rem}"
            checked += 1
    print(f"[TURNFLOW] effets a duree confrontes (survivants) = {checked} (sur {len(eff0)} en S)")
