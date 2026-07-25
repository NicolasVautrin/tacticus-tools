"""Tranche DAMAGE crit — REPLAY-DIFF BIT-EXACT d'une attaque CRIT (offline vs live).

Le crit du COMBAT (≠ prédiction) : par coup, RollCritical D'ABORD (NextBool, 1 genrand si
cc≥1) PUIS spread dans des bornes crit-inclusives — `eff_attack = attack + critDamage` ajouté
AVANT spread/perçage (`IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64 isCrit), PAS l'`ApplyCritDamage`
post-réduction de la PRÉDICTION. Modèle confirmé bit-exact contre le genrand brut live
(necroDestroyer CC=100/CD=500 : 12 tirages/6 coups, per-coup [675,1012]=[435,652]×1406/906).

On force le crit via un build 1v1 patché (`rl_duel --crit "100,<cd>"`) sur un attaquant
multi-coups mêlée vs une cible vanille, on positionne en MÊLÉE HEX (boardGraph = vérité hex ;
l'adjacence n'est PAS cheby), on rejoue l'attaque live+offline (même MT via dumpRng) et on
diffe les PV. Bit-exact => le crit (roll interleavé + bornes eff_attack) est fidèle.

Lit l'état LIVE (pas de tuile/RVA hardcodée). Pinne l'attaquant : aucune unité de lineup n'a
de crit de base — le crit n'existe que via le patch BC. Skip si session/positionnement KO.
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

ATTACKER = "necroDestroyer"      # 6 coups mêlée (Gauss p60) — crit fiable une fois patché
TARGET = "eldarFarseer"          # Psyker, défense vanille
CRIT = "100,500"                 # CritChance=100 (chaque coup crite) , CritDamage=500


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
def crit_attack(live_session, rpc, build_runner):
    """Build 1v1 crit, positionne l'attaquant au contact hex de la cible, rejoue l'attaque
    live+offline. Renvoie le cas {hp_before, live_after, off_after, live_ph, off_ph, crits}."""
    b = build_runner("777", extra=["--roster", "1", "--p-units", ATTACKER,
                                   "--a-units", TARGET, "--crit", CRIT])
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
        if ctile in board.neighbours(ttile):       # DÉJÀ au contact hex → attaque
            return _replay(rpc, rid, board, champ, tgt, None)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        adj = [(tid, cr) for tid, cr in reach.items() if tid in board.neighbours(ttile)]
        if adj:                                     # une tuile atteignable est voisine → s'y placer + attaque
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
    state = load_state(dv2, ob2, snap2, board=board)   # #64 : board a la source (feuilles positionnelles armees)
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
    import json
    live_ph = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)
    runner.apply(AttackUnitMessage(att, tid))
    rr = runner.damage_handler.last
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    return {"hp_before": hp_before, "live_after": live_after, "off_after": off_after,
            "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"),
            "crits": (rr or {}).get("crits"), "rr": rr,
            "blk": any((json.loads(e["tags"]) if isinstance(e.get("tags"), str) else (e.get("tags") or {}))
                       .get("Attack_DidBlock") or
                       (json.loads(e["tags"]) if isinstance(e.get("tags"), str) else (e.get("tags") or {}))
                       .get("Attack_DidEvade") for e in (a0.get("events") or []) if e.get("tags"))}


def test_crit_attack_reproduces_live_per_hit(crit_attack):
    """CŒUR : l'attaque CRIT offline reproduit le live AU COUP PRÈS (per-hit) et au total (PV)."""
    c = crit_attack
    assert c["rr"] is not None, "runner offline n'a rien calculé"
    if c["blk"]:
        pytest.skip("coup avec block/evade live (hors slice crit pur)")
    print(f"\n[CRIT replay] live per-hit={c['live_ph']} off per-hit={c['off_ph']} "
          f"crits={c['crits']} live_after={c['live_after']} off_after={c['off_after']}")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live : off={c['off_ph']} live={c['live_ph']}")
    assert c["off_after"] == c["live_after"], (
        f"PV cible offline {c['off_after']} != live {c['live_after']}")


def test_crit_actually_fired(crit_attack):
    """SANITY : le crit a bien été exercé (CC=100 → tous les coups critent côté offline)."""
    c = crit_attack
    assert c["crits"] and all(c["crits"]), \
        f"crit non déclenché offline (CC={CRIT}) → crits={c['crits']}"
