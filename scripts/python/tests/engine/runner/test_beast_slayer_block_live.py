"""#72 BeastSlayer_ExtraBlock (DEFENSE) — REPLAY-DIFF BIT-EXACT quand orksNob DEFEND.

orksNob (Tanksmasha) porte le trait BeastSlayer -> effet capte `BeastSlayer_ExtraBlock` = source de
BLOCK SUPPLEMENTAIRE (`AddExtraBlockEffectToOwner IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour` : chance beastSlayerBlockChance=10% /
amount = 100% du FixedArmor courant), ABSENTE du scalaire GetStat(7/8) (live orksNob blockChance=0).

Validation DETERMINISTE de la consommation RNG : par coup, l'ordre est [crit] -> spread -> block-roll.
AVANT le port, orksNob (defenseur) n'avait AUCUNE source de block -> le runner NE tirait PAS le
block-roll que le natif tire -> desync RNG des le 2e coup -> off_ph != live_ph. APRES (source BeastSlayer
ajoutee via `_block_sources`), le runner consomme le MEME tirage -> replay-diff bit-exact. On rejoue donc
une attaque multi-coups contre orksNob (RNG seede via dumpRng) et on exige off_ph == live_ph + PV egaux.
Assertion deterministe supplementaire : le block_sources offline d'orksNob CONTIENT bien la source
BeastSlayer (chance 10 / amount = FixedArmor). Lit l'etat LIVE (rien de hardcode). ASCII-only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent, UnitComponent
from engine.runner.operations.damage import AttackDamageOperation
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatType

ATTACKER = "necroDestroyer"      # 6 coups melee (Gauss p60) -> plusieurs block-rolls
TARGET = "orksNob"               # BeastSlayer -> block +10% / 100% FixedArmor (source native, PAS --block-target)


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
def bs_block(live_session, rpc, build_runner):
    b = build_runner("777", extra=["--roster", "1", "--p-units", ATTACKER, "--a-units", TARGET])
    rid, my_player = b["rid"], None
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        pytest.skip("dumpRng indispo")
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
            pytest.skip("unite manquante (build 1v1 KO)")
        if my_player is None:
            my_player = champ.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ctile, ttile = utile(champ), utile(tgt)
        dist = _bfs(board, ttile)
        if ctile in board.neighbours(ttile):
            return _replay(rpc, rid, tgt, champ, None)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        adj = [(tid, cr) for tid, cr in reach.items() if tid in board.neighbours(ttile)]
        if adj:
            _tid, (col, row) = adj[0]
            return _replay(rpc, rid, tgt, champ, (col, row))
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    pytest.skip(f"{ATTACKER} n'a pas atteint {TARGET} en melee en 20 tours")


def _replay(rpc, rid, tgt, champ, move_to):
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
    # DETERMINISTE : la source de block BeastSlayer d'orksNob DOIT etre presente offline (sinon effet
    # non seede -> le replay ne teste pas #72). block_sources = base (scalaire) + effets.
    tsc = te.get_component(StatsComponent)
    active = state.effects.active_effects(tid, {"hp": hc.hp}) if state.effects is not None else []
    armor = tsc.ctx.stat(StatType.FIXED_ARMOR) if tsc is not None else 0
    bsrc = AttackDamageOperation._block_sources(tsc, active, armor)
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
            "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"), "armor": armor,
            "block_sources": bsrc, "blocks": (rr or {}).get("did_block"),
            "did_evade": did_evade, "rr": rr, "has_bs_effect": any(
                getattr(ef, "name", None) == "BeastSlayer_ExtraBlock" for ef in active)}


def test_beast_slayer_block_source_present(bs_block):
    """DETERMINISTE : orksNob (defenseur) expose bien la source de block BeastSlayer offline
    (chance 10 / amount = FixedArmor), issue de l'effet capte `BeastSlayer_ExtraBlock`."""
    c = bs_block
    if not c["has_bs_effect"]:
        pytest.skip("BeastSlayer_ExtraBlock non seede sur orksNob (capture effets)")
    srcs = c["block_sources"] or []
    bs = [s for s in srcs if s.chance == 10 and s.amount == c["armor"]]
    assert bs, (f"source BeastSlayer absente de block_sources={srcs} "
                f"(attendu chance=10, amount=FixedArmor={c['armor']})")


def test_beast_slayer_block_replay_bit_exact(bs_block):
    """COEUR #72 : attaque contre orksNob rejouee RNG-seede -> per-hit offline == live AU COUP PRES
    (le block-roll BeastSlayer consomme le MEME tirage que le natif ; sans le port, desync des le 2e coup)."""
    c = bs_block
    assert c["rr"] is not None, "runner offline n'a rien calcule"
    if c["did_evade"]:
        pytest.skip("coup avec evade live (hors slice block)")
    print(f"\n[BS-BLOCK replay] live per-hit={c['live_ph']} off per-hit={c['off_ph']} "
          f"off_block={c['blocks']} armor={c['armor']} live_after={c['live_after']} off_after={c['off_after']}")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live : off={c['off_ph']} live={c['live_ph']} "
        f"(source block BeastSlayer non consommee identiquement ?)")
    assert c["off_after"] == c["live_after"], (
        f"PV cible offline {c['off_after']} != live {c['live_after']}")
