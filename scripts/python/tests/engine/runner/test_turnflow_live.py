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
from engine.runner.components import StatsComponent
from engine.entities.stats import StatType

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


def _turns_started(snap: dict) -> dict:
    """{entityId (== id d'unite): turnsStarted} depuis combatSnapshot (stat 12, capteur #122)."""
    out: dict[int, int] = {}
    for u in (snap.get("units") or []):
        eid = u.get("entityId")
        ts = (u.get("stats") or {}).get("turnsStarted")
        if eid is not None and ts is not None:
            out[int(eid)] = int(ts)
    return out


def _offline_turns_started(state) -> dict:
    """{id d'unite: stat 12 offline} lu depuis `StatsComponent.ctx` de chaque entite du runner Python."""
    out: dict[int, int] = {}
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and sc.ctx is not None:
            out[int(eid)] = int(sc.ctx.stat(StatType.TURNS_STARTED))
    return out


def test_turnflow_turnsstarted_live(live_session, rpc, build_runner):
    """#123 : `StartTurnOperation` bumpe le compteur PER-UNITE `turnsStarted` (stat 12,
    UnitComponent+0x58) de chaque unite du joueur qui commence son tour. Confronte le stat 12
    OFFLINE (runner Python apres EndTurnMessage) a un combatSnapshot LIVE FRAIS pris apres le MEME
    endturn (agreement NON-circulaire : le natif est la verite du compteur). ASCII only."""
    rid = build_runner("777", extra=BUILD)["rid"]

    # capture S (avant endturn) : decisionView + observeBattle + combatSnapshot (turnsStarted).
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    cur0 = dec.get("currentPlayer")
    ts0 = _turns_started(snap0)
    if cur0 is None or not ts0:
        pytest.skip("currentPlayer/turnsStarted absent de S (capteur stat 12 non present ?)")

    # LIVE : fin du tour courant -> flip + StartTurn du joueur suivant, puis combatSnapshot FRAIS.
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": True}, 90)
    dec1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    snap1 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    cur_live = dec1.get("currentPlayer")
    ts1 = _turns_started(snap1)

    # OFFLINE : load S + EndTurnMessage via le runner Python (=> StartTurnOperation._bump_turns_started).
    state = load_state(dec, ob, snap0)
    runner = Runner(state).install_default_handlers()
    runner.apply(EndTurnMessage(advance=True))
    ts_off = _offline_turns_started(state)

    # 1. le scenario a bien exerce le flip (sinon StartTurn du joueur suivant ne tourne pas).
    assert cur_live is not None and cur_live != cur0, \
        f"live n'a pas flip le joueur (cur0={cur0}, live={cur_live})"

    # 2. le bump s'est produit LIVE sur >=1 unite (garantit que le test exerce l'increment).
    bumped_live = [uid for uid, v in ts1.items() if v != ts0.get(uid)]
    assert bumped_live, f"aucune unite n'a incremente turnsStarted live (ts0={ts0} ts1={ts1})"
    for uid in bumped_live:
        assert ts1[uid] == ts0.get(uid, 0) + 1, \
            f"u{uid} turnsStarted live {ts0.get(uid)}->{ts1[uid]} (attendu +1)"

    # 3. AGREEMENT : pour chaque unite commune, stat 12 OFFLINE == stat 12 LIVE FRAIS apres endturn.
    common = sorted(set(ts_off) & set(ts1))
    assert common, "aucune unite commune offline/live pour confronter turnsStarted"
    diffs = [f"u{uid}: offline {ts_off[uid]} != live {ts1[uid]}"
             for uid in common if ts_off[uid] != ts1[uid]]
    print(f"\n[TURNSTARTED] cur0={cur0} live_next={cur_live} | bumped_live={bumped_live} | "
          f"confrontes={len(common)}")
    assert not diffs, "stat 12 offline != live apres StartTurn:\n  " + "\n  ".join(diffs)
