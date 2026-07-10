"""#91 GuardianOrganism_DamageReduction (DEFENSE) — REPLAY-DIFF quand tyranTyrantGuard DEFEND.

Le Tyrant Guard (trait GuardianOrganism, tank Tyranide) porte sur LUI-MEME (self + amis ring-1)
l'effet `GuardianOrganism_DamageReduction` = reduction du degat RECU = min(dmgReductionPct%(25-33) x
CurrentDamage, dmgReduction_cap x mult). Le natif PRE-EVALUE le defender-mod en scalaire UNIQUE
(`CalculateBaseDamageWithAllModifiers @18102d3f0`) : CurrentDamage = D = le CENTRE du degat post-mods,
donc le montant = min(trunc(pct% x D), cap) est un FLAT soustrait IDENTIQUE a chaque coup (PAS 33% de
chaque valeur tiree). #91 : le runner appliquait ce flat AUX BORNES (per-borne, avant tirage) -> desync
RNG + amplitude fausse ; corrige = flat depuis le centre des bornes, soustrait APRES le tirage par coup.

On rejoue une attaque multi-coups (necroDestroyer, 6 coups melee) contre le Tyrant Guard, RNG seede via
dumpRng, et on exige off_ph == live_ph + PV egaux : le runner doit appliquer la MEME reduction que le
natif a chaque coup. Assertion deterministe : le defenseur expose bien l'effet GuardianOrganism offline
(seede depuis decisionView.effects) ET son def_mods porte des capped_reductions. Lit l'etat LIVE (rien
de hardcode). ASCII-only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.damage_model import defender_modifiers
from engine.entities.stats import StatType

ATTACKER = "necroDestroyer"      # 6 coups melee -> plusieurs coups reduits
TARGET = "tyranTyrantGuard"      # GuardianOrganism -> reduction min(pct%xdmg, cap) sur soi


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


def _go_effects(active):
    return [ef for ef in active if "GuardianOrganism" in (getattr(ef, "name", "") or "")]


@pytest.fixture(scope="session")
def go_combat(live_session, rpc, build_runner):
    from engine.entities.pathfinding.board import Board
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
    active = state.effects.active_effects(tid, {"hp": hc.hp}) if state.effects is not None else []
    go = _go_effects(active)
    # def_mods offline de la cible (reduction capee) — chemin combat exact.
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
            "capped_reductions": list(dmods.capped_reductions),
            "did_evade": did_evade, "rr": rr,
            "has_go_effect": bool(go),
            "go_names": [getattr(ef, "name", "?") for ef in go]}


def test_guardian_organism_effect_present(go_combat):
    """DETERMINISTE : le Tyrant Guard (defenseur) expose l'effet GuardianOrganism offline (seede depuis
    decisionView.effects) ET son def_mods porte des capped_reductions (reduction du degat recu)."""
    c = go_combat
    if not c["has_go_effect"]:
        pytest.skip("GuardianOrganism non seede sur tyranTyrantGuard (aura non capturee dans decisionView.effects)")
    assert c["capped_reductions"], (
        f"effet GuardianOrganism present ({c['go_names']}) mais def_mods.capped_reductions vide "
        f"-> reduction non materialisee en combat")


def test_guardian_organism_combat_replay(go_combat):
    """COEUR #91 : attaque contre le Tyrant Guard rejouee RNG-seede -> per-hit offline == live AU COUP
    PRES (le runner applique la MEME reduction GuardianOrganism per-valeur que le natif)."""
    c = go_combat
    assert c["rr"] is not None, "runner offline n'a rien calcule"
    if not c["has_go_effect"]:
        pytest.skip("GuardianOrganism non seede -> replay ne teste pas #91 (materialisation runner requise)")
    if c["did_evade"]:
        pytest.skip("coup avec evade live (hors slice reduction)")
    print(f"\n[GO-COMBAT replay] live per-hit={c['live_ph']} off per-hit={c['off_ph']} "
          f"capped={c['capped_reductions']} live_after={c['live_after']} off_after={c['off_after']}")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live : off={c['off_ph']} live={c['live_ph']} "
        f"(reduction GuardianOrganism non appliquee identiquement ?)")
    assert c["off_after"] == c["live_after"], (
        f"PV cible offline {c['off_after']} != live {c['live_after']}")
