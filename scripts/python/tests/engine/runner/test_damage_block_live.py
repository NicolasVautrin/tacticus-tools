"""Tranche DAMAGE block — REPLAY-DIFF BIT-EXACT d'une attaque BLOQUÉE (offline vs live).

Le **block** est une mécanique DÉFENSEUR. Comme le crit, **aucune unité n'a de block de base** :
il vient UNIQUEMENT des items équipés (I_Block_* → BlockChance/BlockDamage résolus, exposés en
`MultiValueStat(7)`). On le force donc via le levier BC `rl_duel --block-target "chance,amount"`
(= restaure le stat résolu, équivalent à un item I_Block équipé — même analogue que `--crit`).

Par coup, APRÈS le spread : `ApplyRandomBlockDamage`@181000390 = chaîne `NextBool(chance)` par
source de block triée jusqu'à la 1ʳᵉ réussite → `ApplyBlockDamage`=`max(0, dmg − BlockDamage)`,
DidBlock=1 (échecs = +1 tirage + failed-id). Ordre RNG/coup confirmé live : [crit-roll] → spread →
block-roll. Modèle validé bit-exact (necroDestroyer 6h → eldarFarseer block 100/300 : 12 tirages
/6 coups, per-hit = roll − 300 à l'unité).

Lit l'état LIVE (pas de tuile/RVA hardcodée). Pinne l'attaquant (multi-coups mêlée). Skip si
session/positionnement KO.
"""
from __future__ import annotations

from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.entities.pathfinding.board import Board

ATTACKER = "necroDestroyer"      # 6 coups mêlée (Gauss p60), sans crit → isole le block
TARGET = "eldarFarseer"          # cible vanille ; block forcé via item-équivalent (--block-target)
BLOCK = "100,300"                # BlockChance=100 (chaque coup bloque), BlockDamage=300


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


@pytest.fixture(scope="session")
def block_attack(live_session, rpc, build_runner):
    """Build 1v1 block, positionne l'attaquant au contact hex de la cible, rejoue l'attaque
    live+offline. Renvoie {hp_before, live_after, off_after, live_ph, off_ph, blocks, rr}."""
    b = build_runner("777", extra=["--roster", "1", "--p-units", ATTACKER,
                                   "--a-units", TARGET, "--block-target", BLOCK])
    rid, my_player = b["rid"], None
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        pytest.skip("dumpRng indispo (rebuild+reinject hooks ?)")
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    def utile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if "col" in p else None

    for _turn in range(20):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        units = dec.get("units") or []
        champ = next((u for u in units if u.get("visualId") == ATTACKER and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET and u.get("alive")), None)
        if champ is None or tgt is None:
            pytest.skip("unité manquante (build 1v1 KO)")
        if my_player is None:
            my_player = champ.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ctile, ttile = utile(champ), utile(tgt)
        dist = _bfs(board, ttile)
        if ctile in board.neighbours(ttile):
            return _replay(rpc, rid, board, champ, tgt, None)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        adj = [(tid, cr) for tid, cr in reach.items() if tid in board.neighbours(ttile)]
        if adj:
            tid, (col, row) = adj[0]
            return _replay(rpc, rid, board, champ, tgt, (col, row))
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    pytest.skip(f"{ATTACKER} n'a pas atteint {TARGET} en mêlée en 20 tours")


def _replay(rpc, rid, board, champ, tgt, move_to):
    import json
    att, tid = champ["id"], tgt["id"]
    if move_to is not None:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": att, "to": {"col": move_to[0], "row": move_to[1]}}}, 40)
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
    a2 = next((u for u in (dv2.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale")
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv2, ob2, snap2)
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        pytest.skip("cible introuvable offline")
    hp_before = hc.hp
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 40)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"attaque live KO: {str(res)[:160]}")
    live_ph, did_evade = [], False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
            did_evade = did_evade or bool(td.get("Attack_DidEvade"))
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)
    runner.apply(AttackUnitMessage(att, tid))
    rr = runner.damage_handler.last
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    return {"hp_before": hp_before, "live_after": live_after, "off_after": off_after,
            "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"),
            "blocks": (rr or {}).get("did_block"), "did_evade": did_evade, "rr": rr}


def test_block_attack_reproduces_live_per_hit(block_attack):
    """CŒUR : l'attaque BLOQUÉE offline reproduit le live AU COUP PRÈS (per-hit) et au total (PV)."""
    c = block_attack
    assert c["rr"] is not None, "runner offline n'a rien calculé"
    if c["did_evade"]:
        pytest.skip("coup avec evade live (hors slice block pur)")
    print(f"\n[BLOCK replay] live per-hit={c['live_ph']} off per-hit={c['off_ph']} "
          f"off_block={c['blocks']} live_after={c['live_after']} off_after={c['off_after']}")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live : off={c['off_ph']} live={c['live_ph']}")
    assert c["off_after"] == c["live_after"], (
        f"PV cible offline {c['off_after']} != live {c['live_after']}")


def test_block_actually_fired(block_attack):
    """SANITY : le block a bien été exercé (BlockChance=100 → block côté offline)."""
    assert block_attack["blocks"], f"block non déclenché offline (BLOCK={BLOCK})"
