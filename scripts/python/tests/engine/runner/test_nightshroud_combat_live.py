"""#120 Nightshroud_DmgReduction (DEFENSE) — REPLAY-DIFF quand un allie de Sibyll DEFEND.

Sibyll Devine (astraPrimarisPsy) porte l'ability Nightshroud : tout allie qui COMMENCE son tour
adjacent a elle prend -{dmgReduction} Damage from EACH hit (leur tour + le prochain tour ennemi).
C'est un additif DEFENSEUR plat @+0x10, soustrait de la BASE PRE-percage (comme l'additif attaquant
#75 ; `CalculateBaseDamageWithAllModifiers @18102d3f0` ne re-consomme pas @+0x10) -> DILUE par
percage/armure PUIS scale x%-list. #120 : le runner COMBAT ne le fusionnait pas dans l'additif
pre-percage (seule la PREDICTION le faisait, #111) -> combat SUR-comptait le degat contre les allies
proteges. Fix = `_apply_defender_flat_reductions` (mirror du merge prediction) dans les 3 vecteurs.

On rejoue une attaque multi-coups (necroDestroyer, melee) contre custoTrajann PROTEGE par Sibyll, RNG
seede via dumpRng, et on exige off_ph == live_ph + PV egaux : le runner doit appliquer la MEME reduction
plate que le natif a chaque coup. Assertion deterministe : le defenseur expose l'effet Nightshroud offline
(seede depuis decisionView.effects) ET son def_mods porte des flat_reductions. Lit l'etat LIVE (rien de
hardcode). SKIP si l'aura ne se materialise pas (custoTrajann pas adjacent a Sibyll au bon tour). ASCII-only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.runner.damage_model import defender_modifiers

ATTACKER = "necroDestroyer"          # multi-coups melee -> plusieurs coups reduits
CARRIER = "astraPrimarisPsy"         # Sibyll Devine : aura Nightshroud sur allies ring-1
TARGET = "custoTrajann"              # allie protege (adjacent a Sibyll)


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


def _ns_effects(active):
    return [ef for ef in active if "Nightshroud" in (getattr(ef, "name", "") or "")]


@pytest.fixture(scope="session")
def ns_combat(live_session, rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    b = build_runner("777", extra=["--roster", "1", "--p-units", ATTACKER,
                                    "--a-units", f"{CARRIER},{TARGET}"])
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

    for _turn in range(24):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        units = dec.get("units") or []
        champ = next((u for u in units if u.get("visualId") == ATTACKER and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET and u.get("alive")), None)
        if champ is None or tgt is None:
            pytest.skip("unite manquante (build KO)")
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
    pytest.skip(f"{ATTACKER} n'a pas atteint {TARGET} protege en melee en 24 tours")


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
    active = state.effects.active_effects(tid, {"hp": hc.hp}) if state.effects is not None else []
    ns = _ns_effects(active)
    dmods, _ = defender_modifiers(state, tid, hc.hp, is_melee=True, damage_profile=None, attacker_id=att)
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
            "flat_reductions": list(dmods.flat_reductions),
            "did_evade": did_evade, "rr": rr,
            "has_ns_effect": bool(ns),
            "ns_names": [getattr(ef, "name", "?") for ef in ns]}


def test_nightshroud_effect_present(ns_combat):
    """DETERMINISTE : le defenseur protege expose l'effet Nightshroud offline (seede depuis
    decisionView.effects) ET son def_mods porte des flat_reductions (additif defenseur pre-percage)."""
    c = ns_combat
    if not c["has_ns_effect"]:
        pytest.skip("Nightshroud non seede sur custoTrajann (aura non capturee / pas adjacent a Sibyll)")
    assert c["flat_reductions"], (
        f"effet Nightshroud present ({c['ns_names']}) mais def_mods.flat_reductions vide "
        f"-> reduction non materialisee en combat")


def test_nightshroud_combat_replay(ns_combat):
    """COEUR #120 : attaque contre l'allie protege rejouee RNG-seede -> per-hit offline == live AU COUP
    PRES (le runner applique la MEME reduction plate Nightshroud pre-percage que le natif)."""
    c = ns_combat
    assert c["rr"] is not None, "runner offline n'a rien calcule"
    if not c["has_ns_effect"]:
        pytest.skip("Nightshroud non seede -> replay ne teste pas #120 (materialisation runner requise)")
    if c["did_evade"]:
        pytest.skip("coup avec evade live (hors slice reduction)")
    print(f"\n[NS-COMBAT replay] live per-hit={c['live_ph']} off per-hit={c['off_ph']} "
          f"flat={c['flat_reductions']} live_after={c['live_after']} off_after={c['off_after']}")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live : off={c['off_ph']} live={c['live_ph']} "
        f"(reduction Nightshroud non appliquee identiquement ?)")
    assert c["off_after"] == c["live_after"], (
        f"PV cible offline {c['off_after']} != live {c['live_after']}")
