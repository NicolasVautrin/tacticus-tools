"""#133 -- `MartialSuperiority` (passif `templChampion` << Brother Jaeger >>, TriggeredAbilityType
0x444 = 1092) : RIPOSTE `On(PreUnitAbility)` AVANT que l'attaque entrante ne s'execute.

RE + residus : `engine/runner/operations/triggers/loki/martial_superiority.py`.

TROIS scenarios CRAFTES (positions et tour PILOTES -- le runner est un bac a sable), chacun
confronte au LIVE par REPLAY-DIFF RNG-seede :

 1. POSITIF          -- un ennemi MELEE adjacent frappe Jaeger pendant le tour ADVERSE ->
                        la riposte part (2 coups Power sur l'attaquant) PUIS l'attaque entrante ;
                        PV offline == PV live des DEUX cotes (le stream RNG reste aligne, donc la
                        riposte est jouee au MEME rang que le natif).
 2. NEGATIF `IsMeleeAttack` -- MEME cible, attaquant RANGED a 2 hexes -> AUCUNE riposte.
                        Sans le gate, le port infligerait ~2 coups de riposte fantomes.
 3. LETHAL           -- l'attaquant a peu de PV : la riposte le TUE -> l'attaque entrante est
                        ANNULEE (gate ACTEUR-MORT **POST-`On(0x2a = PreUnitAbility)`** de
                        `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`). C'est
                        l'observable qui prouve le « before the enemy attack executes » d'i2.

+ un volet OFFLINE PUR sur le gate `NOT IsTurnOf(Owner@0x148)` : le LIVE REFUSE l'action d'une
unite hors-tour (mesure : `applyAction` rend 0 evenement), donc ce conjoint ne peut pas etre
confronte live -- on l'isole en basculant `state.current_player_id` sur l'etat DEJA charge.

Lit l'etat LIVE (rien de hardcode). ASCII only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, OwnerComponent
from engine.entities.pathfinding.board import Board
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.loki.martial_superiority import (
    MartialSuperiorityRiposteAbility)
from engine.dsl.event_trigger_type import EventTriggerType

JAEGER = "templChampion"
MELEE_ATTACKER = "orksNob"        # melee pur -> cas POSITIF et LETHAL
RANGED_ATTACKER = "necroWarden"   # arme Range 3 (Gauss) -> cas NEGATIF IsMeleeAttack


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _scenario(rpc, build_runner, attacker, want_dist, hp_target="999999"):
    """Monte le duel Jaeger vs `attacker`, amene JAEGER a `want_dist` hexes de l'attaquant, passe
    au tour ADVERSE, puis rejoue l'attaque de l'ennemi live ET offline. Renvoie la classification
    ou `{ok: False, reason}` (le test appelant decide skip/fail)."""
    b = build_runner("777", extra=["--roster", "1", "--p-units", JAEGER,
                                   "--a-units", attacker,
                                   "--hp-player", "999999", "--hp-target", hp_target])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return {"ok": False, "reason": "boardGraph indispo"}
    board = Board(bg["tiles"], adjacency="native_sym")

    def tile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row"))

    for _turn in range(30):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dv):
            return {"ok": False, "reason": "decisionView KO"}
        jae, att = _alive(dv, JAEGER), _alive(dv, attacker)
        if jae is None or att is None:
            return {"ok": False, "reason": "unite manquante"}
        dist = _bfs(board, tile(att))
        if dist.get(tile(jae)) == want_dist:
            break
        if dv.get("currentPlayer") != jae.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == jae["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((row or {}).get("tiles") or [])}
        exact = [t for t in reach if dist.get(t) == want_dist]
        pool = exact or [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = exact[0] if exact else min(pool, key=lambda t: dist[t])
        col, r = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": jae["id"], "to": {"col": col, "row": r}}}, 40)
        if not exact:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    # tour ADVERSE (conjoint `NOT IsTurnOf(Owner)`)
    for _ in range(4):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        jae = _alive(dv, JAEGER)
        if jae is not None and dv.get("currentPlayer") != jae.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    jae, att = _alive(dv, JAEGER), _alive(dv, attacker)
    if jae is None or att is None:
        return {"ok": False, "reason": "unite manquante post-setup"}
    got = _bfs(board, tile(att)).get(tile(jae))
    if got != want_dist:
        return {"ok": False, "reason": f"distance {got} != {want_dist} apres pilotage"}
    norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        return {"ok": False, "reason": "pas d'attaque normale sur l'attaquant"}
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)      # board OBLIGATOIRE : le gate est POSITIONNEL
    hp_before = {}
    for u in (jae, att):
        e = state.get_entity(u["id"])
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is None or hc.hp is None:
            return {"ok": False, "reason": "unite sans PV offline"}
        hp_before[u["id"]] = hc.hp
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return {"ok": False, "reason": "dumpRng KO"}
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att["id"], "targetId": jae["id"],
        "abilityType": norm["id"]}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        return {"ok": False, "reason": f"attaque live KO: {str(res)[:150]}"}
    live_hp = {u.get("squadId"): u.get("hp") for u in (res.get("units") or [])}
    riposte_amounts = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == att["id"] and "Amount" in td:
            riposte_amounts.append(td.get("Amount"))
    runner.apply(AttackUnitMessage(att["id"], jae["id"]))
    off_hp = {}
    for u in (jae, att):
        e = state.get_entity(u["id"])
        hc = e.get_component(HealthComponent) if e is not None else None
        off_hp[u["id"]] = hc.hp if hc is not None else None
    return {"ok": True, "reason": None, "state": state, "board": board,
            "jaeger": jae["id"], "attacker": att["id"], "dist": got,
            "hp_before": hp_before, "live_hp": live_hp, "off_hp": off_hp,
            "riposte_amounts": riposte_amounts}


# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="function")
def ms_positive(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, MELEE_ATTACKER, want_dist=1)


@pytest.fixture(scope="function")
def ms_ranged(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, RANGED_ATTACKER, want_dist=2)


@pytest.fixture(scope="function")
def ms_lethal(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, MELEE_ATTACKER, want_dist=1, hp_target="2500")


def test_martial_superiority_riposte_positive(ms_positive):
    """POSITIF : attaque MELEE adjacente pendant le tour adverse -> la riposte part LIVE (l'attaquant
    perd des PV avant d'avoir frappe) et le REPLAY offline reproduit les PV des DEUX unites AU PV
    PRES. L'egalite sur la CIBLE (Jaeger) prouve en outre que la riposte est jouee au MEME RANG dans
    le flux RNG que le natif : un decalage l'aurait desynchronise."""
    c = ms_positive
    if not c["ok"]:
        pytest.skip(c["reason"])
    jid, aid = c["jaeger"], c["attacker"]
    assert c["live_hp"][aid] < c["hp_before"][aid], (
        "AUCUNE riposte live : l'attaquant garde ses PV "
        f"({c['live_hp'][aid]} == {c['hp_before'][aid]}) -- le scenario n'exerce rien")
    assert len(c["riposte_amounts"]) == 2, (
        f"riposte live attendue en 2 coups (nrOfHits=2), obtenu {c['riposte_amounts']}")
    assert c["off_hp"][aid] == c["live_hp"][aid], (
        f"PV ATTAQUANT offline {c['off_hp'][aid]} != live {c['live_hp'][aid]} "
        f"(riposte non reproduite : amounts live={c['riposte_amounts']})")
    assert c["off_hp"][jid] == c["live_hp"][jid], (
        f"PV JAEGER offline {c['off_hp'][jid]} != live {c['live_hp'][jid]} "
        "(flux RNG desynchronise -> la riposte n'est pas jouee au bon rang)")


def test_martial_superiority_no_riposte_on_ranged(ms_ranged):
    """NEGATIF `IsMeleeAttack` (predicat POSITIONNEL natif) : MEME porteur, MEME evenement
    `On(PreUnitAbility)`, mais l'attaquant tire a 2 hexes -> le natif ne riposte PAS. Sans le gate,
    le port infligerait 2 coups Power fantomes a l'attaquant."""
    c = ms_ranged
    if not c["ok"]:
        pytest.skip(c["reason"])
    aid = c["attacker"]
    assert c["dist"] >= 2, f"scenario non discriminant : distance {c['dist']}"
    assert c["live_hp"][aid] == c["hp_before"][aid], (
        f"le natif a riposte a distance ({c['live_hp'][aid]} < {c['hp_before'][aid]}) -- "
        "le gate IsMeleeAttack ne serait pas ce que dit le decompile")
    assert c["off_hp"][aid] == c["live_hp"][aid], (
        f"RIPOSTE FANTOME offline : PV attaquant {c['off_hp'][aid]} != live {c['live_hp'][aid]}")
    assert c["off_hp"][c["jaeger"]] == c["live_hp"][c["jaeger"]], (
        f"PV Jaeger offline {c['off_hp'][c['jaeger']]} != live {c['live_hp'][c['jaeger']]}")


def test_martial_superiority_lethal_riposte_cancels_incoming_attack(ms_lethal):
    """LETHAL : la riposte TUE l'attaquant -> `ActiveAbilityOperation$$ExecuteInternal` re-teste la
    mort du caster JUSTE APRES `On(0x2a = PreUnitAbility)` et `return 0` : l'attaque entrante n'a JAMAIS lieu.
    Observable : Jaeger ne perd AUCUN PV. C'est le gate POST-`On(0x2a = PreUnitAbility)` porte par ce lot."""
    c = ms_lethal
    if not c["ok"]:
        pytest.skip(c["reason"])
    jid, aid = c["jaeger"], c["attacker"]
    if c["live_hp"][aid] != 0:
        pytest.skip(f"la riposte n'a pas tue l'attaquant (PV live {c['live_hp'][aid]})")
    assert c["live_hp"][jid] == c["hp_before"][jid], (
        f"le natif a quand meme execute l'attaque entrante (Jaeger {c['hp_before'][jid]} -> "
        f"{c['live_hp'][jid]}) -- l'hypothese du gate POST-On(0x2b) serait fausse")
    assert c["off_hp"][jid] == c["live_hp"][jid], (
        f"ATTAQUE FANTOME offline : Jaeger {c['off_hp'][jid]} != live {c['live_hp'][jid]} "
        "(gate acteur-mort POST-On(0x2a = PreUnitAbility) absent)")
    assert c["off_hp"][aid] == c["live_hp"][aid], (
        f"PV attaquant offline {c['off_hp'][aid]} != live {c['live_hp'][aid]}")


def test_martial_superiority_turn_gate_offline(ms_positive):
    """Conjoint `NOT ctx@0xa0` = `NOT IsTurnOf(Owner@0x148)`, ISOLE OFFLINE.

    Il ne peut pas etre confronte live : le moteur natif REFUSE l'action d'une unite dont ce n'est
    pas le tour (mesure : `applyAction` rend 0 evenement et 0 delta de PV), donc aucun scenario live
    ne distingue « le gate a bloque la riposte » de « l'action n'a pas eu lieu ». On l'isole donc sur
    l'etat DEJA charge : MEME evenement, MEME geometrie, on bascule seulement le joueur courant."""
    c = ms_positive
    if not c["ok"]:
        pytest.skip(c["reason"])
    state, jid, aid = c["state"], c["jaeger"], c["attacker"]
    trig = MartialSuperiorityRiposteAbility(jid)
    ev = TriggerEvent(int(EventTriggerType.PreUnitAbility), aid, jid,
                      ranged=False, profile=None, ability_type=1013)   # kind attaque-normale
    owner = state.get_entity(jid).get_component(OwnerComponent)
    saved = state.current_player_id
    try:
        state.current_player_id = int(owner.player) + 1        # tour ADVERSE
        assert trig.matches(state, ev) is True, (
            "la riposte ne part pas pendant le tour adverse alors que la geometrie est celle du "
            "cas positif -- un autre conjoint bloque")
        state.current_player_id = int(owner.player)            # tour DU PORTEUR
        assert trig.matches(state, ev) is False, (
            "la riposte part pendant le tour de Jaeger : le conjoint NOT IsTurnOf(Owner) manque")
    finally:
        state.current_player_id = saved
