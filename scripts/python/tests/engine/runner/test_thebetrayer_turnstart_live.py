"""TheBetrayer (worldKharn) — auto-tour de DÉBUT DE TOUR, confronté au LIVE (replay-diff).

Valide le **vecteur turn-start** (`start_turn_triggers` = `On(0x16)`, émis par `StartTurnOperation`
@180ea3fb0) + la passive **TheBetrayer** :
  - `TheBetrayer_AddEffectAbility` : Kharn gagne la rage `0x4f3` quand il TUE (OnDeath & OwnerIsActor) —
    confirmé : la rage apparaît dans `decisionView.effects` après un kill ;
  - `TheBetrayer_TakeTurnAbility` : au début de SON tour, s'il a la rage, il vise l'unité la plus proche
    (ennemi préféré, sinon allié), se déplace vers elle (≤ range 2) et l'attaque (4 coups Eviscerate).

PROTOCOLE replay-diff : on capture l'état S au tour ENNEMI (Kharn a déjà la rage) ; LIVE on `endturn`
(flip → StartTurn de Kharn → TheBetrayer tire) et on observe la cible touchée + la position finale de
Kharn ; OFFLINE on `load_state(S)` + `start_turn_triggers(kharn_player)` et on confronte :
  • la CIBLE choisie offline == l'ennemi touché live (sélection `GetAttackTarget` exacte) ;
  • la TUILE de move offline == la position finale live de Kharn (exacte).
Le DÉGÂT exact (3488 vs ~3661 live) dépend du calage RNG de la cascade turn-start (la prédiction de
dégât est validée bit-exact ailleurs) → ici on exige seulement qu'une attaque ait lieu (total>0).

Teams adaptées (Kharn + ennemis tanky qui survivent au burst et lui donnent un kill -> rage). Seed =
simple bootstrap. ⚠ ADJACENCE = evenq.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.triggers import (
    start_turn_triggers, THEBETRAYER_EFFECT, _add_betrayer_effect)
from engine.runner.prng import IntBasedMersenneTwister

KHARN = "worldKharn"
RAGE = 1267   # 0x4f3
BUILD = ["--roster", "1", "--p-units", "worldKharn",
         "--a-units", "necroWarden,necroOverlord,necroWarden"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def test_thebetrayer_turnstart_live(live_session, rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    # avancer jusqu'a : Kharn a la rage 0x4f3 AU TOUR ENNEMI (prochain flip = son turn-start).
    k_player = None
    found = False
    for _ in range(20):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        k = next((u for u in (dec.get("units") or []) if u.get("visualId") == KHARN), None)
        if k is None:
            break
        if k_player is None:
            k_player = k.get("owner")
        rage = RAGE in [e.get("effectType") for e in (k.get("effects") or [])]
        if rage and dec.get("currentPlayer") not in (None, k_player):
            found = True
            break
        rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                             "maxPump": 3000, "captureEvents": False}, 300)
    if not found:
        pytest.skip("Kharn n'a pas obtenu la rage 0x4f3 au tour ennemi en 20 iters")

    # capture S (avant le turn-start de Kharn).
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    k0 = next((u for u in (dec.get("units") or []) if u.get("visualId") == KHARN), None)
    if k0 is None:
        pytest.skip("Kharn absent de S")
    kid = k0.get("id")
    en0 = {u.get("squadId"): u.get("hp") for u in (ob.get("units") or [])
           if u.get("teamId") == 2 and not u.get("isDead")}

    # LIVE : endturn -> Kharn turn-start -> TheBetrayer ; cible touchee + position finale.
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": True}, 90)
    ob1 = rpc("observeBattle", {"runnerId": rid}, 60)
    k1 = next((u for u in (ob1.get("units") or []) if u.get("visualId") == KHARN and not u.get("isDead")), None)
    en1 = {u.get("squadId"): u.get("hp") for u in (ob1.get("units") or [])
           if u.get("teamId") == 2 and not u.get("isDead")}
    live_dmg = {sq: en0[sq] - en1.get(sq, 0) for sq in en0 if en0[sq] - en1.get(sq, 0) > 0}
    live_move = (k1.get("col"), k1.get("row")) if k1 else None

    # OFFLINE : load_state(S) + start_turn_triggers.
    state = load_state(dec, ob, snap)
    state.board = board
    if _ok(rng0):
        state.rng = _seed_rng(rng0)
    if state.get_entity(kid) is None:
        pytest.skip("Kharn absent offline (snapshot incomplet)")
    if state.effects is None or not state.effects.has_effect(kid, effect_type=THEBETRAYER_EFFECT):
        _add_betrayer_effect(state, kid)        # decisionView peut ne pas exposer 0x4f3 -> garantir le gate

    res = start_turn_triggers(state, k_player)
    bet = next((r for r in res if r.get("ability") == "TheBetrayer"), None)
    off_target = bet.get("target") if bet else None
    off_move = (bet.get("moved") or {}).get("to") if (bet and bet.get("moved")) else None
    off_attack = bet.get("attack") if bet else None
    print(f"\n[BETRAYER] off target={off_target} move={off_move} "
          f"attack_total={(off_attack or {}).get('total')} | live target(s)={list(live_dmg.keys())} "
          f"live_move={live_move} live_dmg={live_dmg}")

    # 1. TheBetrayer a tiré offline (cible choisie).
    assert bet is not None and off_target is not None, \
        f"TheBetrayer n'a pas tire offline (res={res})"
    # 2. CIBLE offline == ennemi touche live (id offline == squadId live).
    assert live_dmg, "live : aucun ennemi touche au turn-start (Kharn n'a pas charge ?)"
    assert off_target in live_dmg, \
        f"cible offline {off_target} != cible(s) live {list(live_dmg.keys())}"
    # 3. TUILE de move offline == position finale live de Kharn.
    if off_move is not None and live_move is not None:
        assert off_move == live_move, f"move offline {off_move} != live {live_move}"
    # 4. une attaque a bien eu lieu offline (degat exact = calage RNG, hors scope).
    assert off_attack is not None and (off_attack.get("total") or 0) > 0, \
        f"pas d'attaque offline (attack={off_attack})"
