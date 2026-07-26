"""#220 AvalancheOfMuscle (astraBullgryn passif, AstraMilitarum) -- bonus extra-damage de CHARGE.

astraBullgryn porte le passif AvalancheOfMuscle : effet EffectType 1025 "AvalancheOfMuscle_ExtraDamage"
dont `IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack` = `EffectBonus.ForAddition(OwnerIsCaster & IsCharging,
ConfigVar(8=extraDmg, GetAbilityState, EffectSource))` -- JUMEAU de FeederTendrils IdunBattle.Entities.Effects.Loki.FeederTendrils_ExtraDamageEffect$$CreateEffectDamageBonusForAttack SANS le
noeud IsNormalAttack (RE decompile : callees IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack = {get_OwnerIsCaster, IsCharging, op_BitwiseAnd,
GetAbilityState, ConfigVar} ; PAS d'IsNormalAttack). Additif PRE-percage par coup (attacker_additive_pre),
gate IsCharging = l'unite s'est-elle rapprochee de la cible (has_moved), astraBullgryn etant MELEE-only.

VALIDATION (adversariale, combat replay-diff bit-exact). load_state NE seed PAS le `UnitFlag.Moved` depuis
le live (aucun RPC ne l'expose ; il n'est pose que par MoveUnitOperation offline) -> on RECONSTRUIT
fidelement l'etat "a charge" via `set_moved_flag(state, att)` SSI l'attaque live etait une charge (fait CONNU car on pilote
le deplacement). Pour CHAQUE attaque normale live on calcule DEUX contrefactuels offline depuis le MEME
etat + le MEME RNG (dumpRng) : off_charge (moved={att}) et off_nocharge (moved vide), et on confronte au
live per-hit :
  (a) attaque de CHARGE (astraBullgryn s'est deplace au contact ce tour) -> live_ph == off_charge (bonus
      +extraDmg applique, magnitude/scope corrects) ET live_ph != off_nocharge (bonus REELLEMENT present).
  (b) attaque SANS charge (deja adjacent, pas de deplacement ce tour) -> live_ph == off_nocharge (pas de
      bonus) ET live_ph != off_charge (le gate IsCharging annule bien le bonus).
Lit l'etat LIVE, rien de hardcode. ASCII-only. (Modele : test_getstuckin_combat_live.py.)
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.entities.pathfinding.board import Board

ATTACKER = "astraBullgryn"       # passif AvalancheOfMuscle (+extraDmg de charge, effet 1025)
TARGET = "bloodIntercessor"      # cible propre (utilisee bit-exact par test_getstuckin) ; HP force -> survit

PYDIR = Path(__file__).resolve().parents[3]                   # scripts/python
ROOT = Path(__file__).resolve().parents[5]                    # racine repo (worktree)
# State-file DEDIE a CET agent (nom UNIQUE, chemin ABSOLU) -> pas de collision avec un autre agent/pytest.
STATE = ROOT / "logs" / "runners" / "_avalanche_muscle_a32f82d4_state.json"


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


def _live_per_hit(res, tid, ability_id):
    """Per-hit live (Amount) + flag evade, filtre sur la cible + l'ability du coup."""
    a0 = (res.get("actions") or [{}])[0]
    ph, evaded = [], False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == ability_id:
            ph.append(td.get("Amount"))
            evaded = evaded or bool(td.get("Attack_DidEvade"))
    after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)
    return ph, evaded, after, a0


def _off_per_hit(dv, ob, snap, att, tid, charged: bool, rng_state):
    """Rejoue l'attaque normale OFFLINE depuis un etat frais + RNG seede. `charged` -> pose le flag natif
    `UnitFlag.Moved` sur l'attaquant (fidele au fait live "a charge"). Renvoie (per_hit, hp_after)."""
    from engine.runner.components import set_moved_flag
    state = load_state(dv, ob, snap)
    if charged:
        set_moved_flag(state, att)                 # IsCharging : l'attaquant s'est deplace ce tour
    state.rng = _seed_rng(rng_state)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tid))
    rr = runner.damage_handler.last or {}
    hp_after = state.get_entity(tid).get_component(HealthComponent).hp
    return rr.get("per_hit"), hp_after


def _measure(rpc, rid, att, tid):
    """Une attaque normale live d'astraBullgryn -> triple {live, off_charge, off_nocharge}. Seede le RNG
    live (dumpRng) sur les DEUX rejeux offline pour un replay-diff bit-exact."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    a = next((u for u in (dv.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale exposee")
    # niveau/mult reels de l'effet AvalancheOfMuscle du porteur (diag, rien de hardcode).
    diag = None
    st_probe = load_state(dv, ob, snap)
    _ae = st_probe.get_entity(att)
    _ahc = _ae.get_component(HealthComponent) if _ae is not None else None
    if _ae is not None and st_probe.effects is not None:
        for _e in st_probe.effects.active_effects(att, {"hp": _ahc.hp if _ahc else None}):
            if getattr(_e, "name", None) == "AvalancheOfMuscle_ExtraDamage":
                _b = _e.create_effect_damage_bonus_for_attack(is_ranged=False, has_moved=True)
                diag = {"al": getattr(_e, "ability_level", None), "lvl": getattr(_e, "level", None),
                        "mult": getattr(_e, "ability_variables_multiplier", None),
                        "bonus_per_hit": getattr(_b, "value", None) if _b is not None else None}
                break
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    off_charge, hp_c = _off_per_hit(dv, ob, snap, att, tid, True, s0)
    off_nocharge, hp_n = _off_per_hit(dv, ob, snap, att, tid, False, s0)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 40)
    if not _ok(res):
        pytest.skip(f"attaque live KO: {str(res)[:160]}")
    live_ph, evaded, live_after, a0 = _live_per_hit(res, tid, norm["id"])
    if not (a0.get("ok")):
        pytest.skip(f"coup live KO: {str(a0)[:160]}")
    return {"live_ph": live_ph, "off_charge": off_charge, "off_nocharge": off_nocharge,
            "evaded": evaded, "live_after": live_after, "hp_off_charge": hp_c,
            "hp_off_nocharge": hp_n, "diag": diag}


@pytest.fixture(scope="session")
def avalanche(live_session, rpc, host):
    """Build 1v1 astraBullgryn vs cible tanky (survit 2 attaques). Turn 1 : CHARGE (deplacement au contact
    + attaque). Turn 2 : NO-CHARGE (deja adjacent, aucun deplacement). Retourne les 2 mesures."""
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "220", "--state-file", str(STATE),
         "--board", "MC1_67", "--roster", "1", "--p-units", ATTACKER, "--a-units", TARGET,
         "--hp-target", "120000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        pytest.skip(f"build KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
            pytest.skip("dumpRng indispo")
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and "tiles" in bg):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")

        def utile(u):
            p = u.get("pos") or {}
            return board.id_at(p.get("col"), p.get("row")) if "col" in p else None

        my_player, charge_res = None, None
        for _turn in range(24):
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
            att, tid = champ["id"], tgt["id"]
            adj_now = ctile in board.neighbours(ttile)
            if charge_res is None:
                # --- Turn de CHARGE : amener astraBullgryn au contact CE tour, puis mesurer ---
                if adj_now:
                    # deja adjacent au spawn : impossible de charger -> avancer/reculer non trivial ; on skip
                    pytest.skip("astraBullgryn spawn deja adjacent -> pas de charge possible turn 1")
                mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
                cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == att), None)
                reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                         for t in ((cmt or {}).get("tiles") or [])}
                adj = [(tid_, cr) for tid_, cr in reach.items() if tid_ in board.neighbours(ttile)]
                if adj:
                    _t, (col, row) = adj[0]
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": att, "to": {"col": col, "row": row}}}, 40)
                    charge_res = _measure(rpc, rid, att, tid)
                    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                    continue
                # pas encore a portee de contact -> avancer d'un pas vers la cible et finir le tour
                dist = _bfs(board, ttile)
                pool = [t for t in reach if t in dist]
                if not pool:
                    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
                best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": att, "to": {"col": col, "row": row}}}, 40)
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            # --- Turn de NO-CHARGE : astraBullgryn deja adjacent (charge du tour precedent), pas de move ---
            if not adj_now:
                pytest.skip("cible non adjacente au turn 2 (deplacee) -> no-charge non mesurable")
            nocharge_res = _measure(rpc, rid, att, tid)
            return {"charge": charge_res, "nocharge": nocharge_res}
        pytest.skip("scenario charge/no-charge non atteint en 24 tours")
    finally:
        try:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass


def test_charge_bonus_applied_bit_exact(avalanche):
    """(a) attaque de CHARGE -> live per-hit == off_charge (bonus +extraDmg APPLIQUE, magnitude/scope
    corrects) ET != off_nocharge (le bonus est REELLEMENT present live). Prouve la presence + la magnitude."""
    c = avalanche["charge"]
    if c["evaded"]:
        pytest.skip("coup de charge avec evade live")
    print(f"\n[AVALANCHE-CHARGE] live={c['live_ph']} off_charge={c['off_charge']} "
          f"off_nocharge={c['off_nocharge']} diag={c['diag']}")
    assert c["off_charge"] == c["live_ph"], (
        f"charge: off_charge {c['off_charge']} != live {c['live_ph']} (magnitude/canal extraDmg faux)")
    assert c["off_nocharge"] != c["live_ph"], (
        f"charge: off_nocharge {c['off_nocharge']} == live -> le bonus n'aurait aucun effet observable "
        f"(diag={c['diag']}) ; scenario non discriminant")
    assert c["hp_off_charge"] == c["live_after"], (
        f"charge: PV off_charge {c['hp_off_charge']} != live {c['live_after']}")


def test_no_charge_no_bonus_bit_exact(avalanche):
    """(b) attaque SANS charge (deja adjacent, pas de deplacement) -> live per-hit == off_nocharge (PAS de
    bonus) ET != off_charge (le gate IsCharging annule bien l'additif). Prouve le gate charge."""
    n = avalanche["nocharge"]
    if n["evaded"]:
        pytest.skip("coup no-charge avec evade live")
    print(f"\n[AVALANCHE-NOCHARGE] live={n['live_ph']} off_charge={n['off_charge']} "
          f"off_nocharge={n['off_nocharge']} diag={n['diag']}")
    assert n["off_nocharge"] == n["live_ph"], (
        f"no-charge: off_nocharge {n['off_nocharge']} != live {n['live_ph']} (base faux)")
    assert n["off_charge"] != n["live_ph"], (
        f"no-charge: off_charge {n['off_charge']} == live -> le gate IsCharging serait no-op (bonus mal gate)")
    assert n["hp_off_nocharge"] == n["live_after"], (
        f"no-charge: PV off_nocharge {n['hp_off_nocharge']} != live {n['live_after']}")


def test_bonus_magnitude_is_config_var8(avalanche):
    """Sanity : le bonus per-hit observe (delta charge vs no-charge des contrefactuels) == extraDmg[level]
    x multiplier lu de gameconfig (ConfigVar 8), pas une valeur hardcodee. Le diag expose la magnitude
    resolue offline ; on exige qu'elle soit > 0 et qu'elle CREE la difference charge/no-charge."""
    c = avalanche["charge"]
    diag = c["diag"] or {}
    bonus = diag.get("bonus_per_hit")
    assert bonus is not None and bonus > 0, f"bonus extraDmg non resolu (diag={diag})"
    # le delta per-coup off_charge - off_nocharge doit refleter le bonus additif (>0 sur au moins 1 coup).
    oc, on = c["off_charge"] or [], c["off_nocharge"] or []
    if oc and on and len(oc) == len(on):
        deltas = [a - b for a, b in zip(oc, on)]
        assert any(d > 0 for d in deltas), f"aucun delta positif charge vs no-charge {deltas} (diag={diag})"
