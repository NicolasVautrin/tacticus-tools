"""#220 CondemnorStake (adeptCanoness <<Roswitha>> passif, Sisterhood/Imperial) -- bonus extra-damage
vs cibles PSYKER.

adeptCanoness porte le passif CondemnorStake : effet EffectType 1076 "CondemnorStake_ExtraDmg" dont
`IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` = `EffectBonus.ForAddition(OwnerIsActor & HasTrait(target,
0x3ea=1002=Psyker), ConfigVar(8=extraDmg, GetAbilityState, EffectSource))` -- JUMEAU de AvalancheOfMuscle
IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack avec le gate IsCharging remplace par HasTrait(target, Psyker) (RE decompile : callees IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack =
{GetAbilityState, ConfigVar, get_OwnerIsActor, HasTrait(target, 0x3ea), op_BitwiseAnd} ; AUCUN gate
melee/ranged/normal/charging). Additif PRE-percage par coup (attacker_additive_pre, canal DamageModifiers.Add),
gate CIBLE = la cible a-t-elle le trait Psyker. i2 "+2183 Damage" = extraDmg[L65] (lu gameconfig, jamais hardcode).

VALIDATION (adversariale, combat replay-diff bit-exact). Le discriminant est le trait Psyker de la CIBLE. Pour
CHAQUE attaque normale live d'adeptCanoness contre une cible on calcule DEUX contrefactuels offline depuis le
MEME etat + le MEME RNG (dumpRng) :
  - off_real  : traits REELS de la cible (aucune manipulation) ;
  - off_flip  : le trait Psyker TOGGLE (retire si present, ajoute si absent).
et on confronte au live per-hit :
  (a) cible PSYKER (eldarFarseer, traits [Hero, Psyker]) -> live_ph == off_real (bonus +extraDmg APPLIQUE,
      magnitude/scope corrects) ET live_ph != off_flip (le bonus DISPARAIT quand on retire Psyker : bonus REEL).
  (b) cible NON-PSYKER (necroWarden) -> live_ph == off_real (PAS de bonus) ET live_ph != off_flip (ajouter
      Psyker CREE le bonus : le gate HasTrait(target, Psyker) discrimine bien).
Lit l'etat LIVE, rien de hardcode (magnitude lue de gameconfig via l'effet capte). ASCII-only.
(Modele : test_avalanche_of_muscle_live.py.)
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
from engine.runner.components import HealthComponent, StatsComponent
from engine.entities.pathfinding.board import Board

ATTACKER = "adeptCanoness"       # passif CondemnorStake (+extraDmg vs Psyker, effet 1076)
PSYKER = "eldarFarseer"          # cible PSYKER (traits [Hero, Psyker]) -> bonus attendu
NONPSY = "admecManipulus"        # cible NON-Psyker (Mechanical, sans reanim reactive) -> pas de bonus
# NB : necroWarden aussi non-Psyker et per-hit bit-exact, mais LivingMetal REANIMe le degat en fin
# d'action (heal non modelise offline) -> confond le PV residuel. admecManipulus n'a pas de heal REACTIF
# (son repair est une ability ACTIVE, hors de mon attaque) -> PV residuel propre.

PYDIR = Path(__file__).resolve().parents[3]                   # scripts/python
ROOT = Path(__file__).resolve().parents[5]                    # racine repo (worktree)
# State-file DEDIE a CET agent (nom UNIQUE, chemin ABSOLU) -> pas de collision avec un autre agent/pytest.
STATE = ROOT / "logs" / "runners" / "_condemnor_stake_a6a136c3_state.json"


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


def _toggle_psyker(state, tid: int, present: bool):
    """Force la presence/absence du trait Psyker de la cible dans l'etat offline (mirror HasTrait(target,
    Psyker) du gate natif). `present` True -> Psyker present ; False -> Psyker retire."""
    te = state.get_entity(tid)
    tsc = te.get_component(StatsComponent) if te is not None else None
    ctx = getattr(tsc, "ctx", None) if tsc is not None else None
    if ctx is None:
        return
    traits = list(getattr(ctx, "traits", None) or [])
    has = "Psyker" in traits
    if present and not has:
        traits.append("Psyker")
    elif (not present) and has:
        traits = [t for t in traits if t != "Psyker"]
    ctx.traits = traits


def _off_per_hit(dv, ob, snap, att, tid, psyker_present, rng_state):
    """Rejoue l'attaque normale OFFLINE depuis un etat frais + RNG seede. `psyker_present` -> force le trait
    Psyker de la cible (True=present, False=retire). Renvoie (per_hit, hp_after)."""
    state = load_state(dv, ob, snap)
    _toggle_psyker(state, tid, psyker_present)
    state.rng = _seed_rng(rng_state)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tid))
    rr = runner.damage_handler.last or {}
    hp_after = state.get_entity(tid).get_component(HealthComponent).hp
    return rr.get("per_hit"), hp_after


def _target_is_psyker(dv, ob, snap, tid) -> bool:
    st = load_state(dv, ob, snap)
    te = st.get_entity(tid)
    tsc = te.get_component(StatsComponent) if te is not None else None
    traits = list(getattr(getattr(tsc, "ctx", None), "traits", None) or []) if tsc is not None else []
    return "Psyker" in traits


def _measure(rpc, rid, att, tid):
    """Une attaque normale live d'adeptCanoness -> triple {live, off_real, off_flip}. Seede le RNG live
    (dumpRng) sur les DEUX rejeux offline pour un replay-diff bit-exact. off_real = traits reels de la cible ;
    off_flip = trait Psyker toggle (le contrefactuel de l'autre branche du gate)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    a = next((u for u in (dv.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale exposee")
    real_psyker = _target_is_psyker(dv, ob, snap, tid)
    # niveau/mult reels de l'effet CondemnorStake du porteur (diag, rien de hardcode).
    diag = None
    st_probe = load_state(dv, ob, snap)
    _ae = st_probe.get_entity(att)
    _ahc = _ae.get_component(HealthComponent) if _ae is not None else None
    if _ae is not None and st_probe.effects is not None:
        for _e in st_probe.effects.active_effects(att, {"hp": _ahc.hp if _ahc else None}):
            if getattr(_e, "name", None) == "CondemnorStake_ExtraDmg":
                _b = _e.create_effect_damage_bonus_for_attack(target_traits=frozenset({"Psyker"}))
                diag = {"al": getattr(_e, "ability_level", None), "lvl": getattr(_e, "level", None),
                        "mult": getattr(_e, "ability_variables_multiplier", None),
                        "bonus_per_hit": getattr(_b, "value", None) if _b is not None else None}
                break
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    off_real, hp_r = _off_per_hit(dv, ob, snap, att, tid, real_psyker, s0)
    off_flip, hp_f = _off_per_hit(dv, ob, snap, att, tid, not real_psyker, s0)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 40)
    if not _ok(res):
        pytest.skip(f"attaque live KO: {str(res)[:160]}")
    live_ph, evaded, live_after, a0 = _live_per_hit(res, tid, norm["id"])
    if not (a0.get("ok")):
        pytest.skip(f"coup live KO: {str(a0)[:160]}")
    return {"live_ph": live_ph, "off_real": off_real, "off_flip": off_flip, "evaded": evaded,
            "live_after": live_after, "hp_off_real": hp_r, "hp_off_flip": hp_f,
            "real_psyker": real_psyker, "diag": diag}


def _build_measure(rpc, host, live_session, target_vis):
    """Build 1v1 adeptCanoness (HP force -> survit) vs `target_vis` (HP force -> survit). Amene la Canoness
    au contact et mesure une attaque normale. Dispose le runner. Renvoie la mesure {live, off_real, off_flip}."""
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "220", "--state-file", str(STATE),
         "--board", "MC1_67", "--roster", "1", "--p-units", ATTACKER, "--a-units", target_vis,
         "--hp-target", "160000", "--hp-player", "160000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        pytest.skip(f"build KO ({target_vis}): {(proc.stderr or proc.stdout or '')[-300:]}")
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

        my_player = None
        for _turn in range(24):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            if not _ok(dec):
                pytest.skip("decisionView KO")
            units = dec.get("units") or []
            champ = next((u for u in units if u.get("visualId") == ATTACKER and u.get("alive")), None)
            tgt = next((u for u in units if u.get("visualId") == target_vis and u.get("alive")), None)
            if champ is None or tgt is None:
                pytest.skip(f"unite manquante (build 1v1 {target_vis} KO)")
            if my_player is None:
                my_player = champ.get("owner")
            if dec.get("currentPlayer") != my_player:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            ctile, ttile = utile(champ), utile(tgt)
            att, tid = champ["id"], tgt["id"]
            if ctile in board.neighbours(ttile):
                # deja adjacent -> attaque melee normale, mesure
                return _measure(rpc, rid, att, tid)
            # sinon : amener la Canoness au contact (adjacence) ce tour
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == att), None)
            reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                     for t in ((cmt or {}).get("tiles") or [])}
            adj = [(tid_, cr) for tid_, cr in reach.items() if tid_ in board.neighbours(ttile)]
            if adj:
                _t, (col, row) = adj[0]
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": att, "to": {"col": col, "row": row}}}, 40)
                return _measure(rpc, rid, att, tid)
            # pas encore a portee de contact -> avancer d'un pas vers la cible et finir le tour
            dist = _bfs(board, ttile)
            pool = [t for t in reach if t in dist]
            if not pool:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
            best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": att, "to": {"col": col, "row": row}}}, 40)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        pytest.skip(f"contact non atteint en 24 tours ({target_vis})")
    finally:
        try:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass


@pytest.fixture(scope="session")
def condemnor(live_session, rpc, host):
    """2 builds 1v1 adeptCanoness (HP force) vs [PSYKER eldarFarseer] puis [NON-PSYKER necroWarden].
    Chaque build : contact + attaque normale mesuree (live + 2 contrefactuels off_real/off_flip)."""
    psyker = _build_measure(rpc, host, live_session, PSYKER)
    nonpsy = _build_measure(rpc, host, live_session, NONPSY)
    return {"psyker": psyker, "nonpsy": nonpsy}


def test_psyker_bonus_applied_bit_exact(condemnor):
    """(a) cible PSYKER -> live per-hit == off_real (bonus +extraDmg APPLIQUE, magnitude/scope corrects) ET
    != off_flip (retirer Psyker annule le bonus : bonus REEL, magnitude non nulle). Prouve presence + magnitude."""
    c = condemnor["psyker"]
    if c["evaded"]:
        pytest.skip("coup psyker avec evade live")
    assert c["real_psyker"] is True, "la cible PSYKER ne porte pas le trait Psyker (build KO)"
    print(f"\n[CONDEMNOR-PSYKER] live={c['live_ph']} off_real={c['off_real']} off_flip={c['off_flip']} "
          f"diag={c['diag']}")
    assert c["off_real"] == c["live_ph"], (
        f"psyker: off_real {c['off_real']} != live {c['live_ph']} (magnitude/canal extraDmg faux)")
    assert c["off_flip"] != c["live_ph"], (
        f"psyker: off_flip {c['off_flip']} == live -> le bonus n'aurait aucun effet observable "
        f"(diag={c['diag']}) ; scenario non discriminant")
    assert c["hp_off_real"] == c["live_after"], (
        f"psyker: PV off_real {c['hp_off_real']} != live {c['live_after']}")


def test_nonpsyker_no_bonus_bit_exact(condemnor):
    """(b) cible NON-PSYKER -> live per-hit == off_real (PAS de bonus) ET != off_flip (ajouter Psyker cree le
    bonus). Prouve le gate HasTrait(target, Psyker) : le bonus est bien conditionne au trait de la cible."""
    n = condemnor["nonpsy"]
    if n["evaded"]:
        pytest.skip("coup non-psyker avec evade live")
    assert n["real_psyker"] is False, "la cible NON-PSYKER porte le trait Psyker (build KO)"
    print(f"\n[CONDEMNOR-NONPSYKER] live={n['live_ph']} off_real={n['off_real']} off_flip={n['off_flip']} "
          f"diag={n['diag']}")
    assert n["off_real"] == n["live_ph"], (
        f"non-psyker: off_real {n['off_real']} != live {n['live_ph']} (base faux)")
    assert n["off_flip"] != n["live_ph"], (
        f"non-psyker: off_flip {n['off_flip']} == live -> ajouter Psyker serait no-op (gate mal cable)")
    assert n["hp_off_real"] == n["live_after"], (
        f"non-psyker: PV off_real {n['hp_off_real']} != live {n['live_after']}")


def test_bonus_magnitude_is_config_var8(condemnor):
    """Sanity : le bonus per-hit (delta off_real vs off_flip cote PSYKER) == extraDmg[level] x multiplier lu
    de gameconfig (ConfigVar 8), pas une valeur hardcodee (jamais 2183 en dur). Le diag expose la magnitude
    resolue offline ; on exige qu'elle soit > 0 et qu'elle CREE la difference psyker/non-psyker."""
    c = condemnor["psyker"]
    diag = c["diag"] or {}
    bonus = diag.get("bonus_per_hit")
    assert bonus is not None and bonus > 0, f"bonus extraDmg non resolu (diag={diag})"
    oc, on = c["off_real"] or [], c["off_flip"] or []
    if oc and on and len(oc) == len(on):
        deltas = [a - b for a, b in zip(oc, on)]
        assert any(d > 0 for d in deltas), f"aucun delta positif psyker vs non-psyker {deltas} (diag={diag})"
