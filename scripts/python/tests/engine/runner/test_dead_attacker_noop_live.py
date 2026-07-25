"""#70 GATE ACTEUR-MORT — une attaque/ability d'un attaquant MORT est un NO-OP (0 tirage RNG, 0 degat).

Racine (RE gqfc5mff6c) : `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` gate le CASTER en amont de
toute execution -> `if (EntityExtensions.IsUnit(caster) && UnitExtensions.IsDead(caster)) return 0;`. Le
predicat `IdunBattle.Entities.UnitExtensions$$IsDead` = `!IsAlive(caster) && !HasFlag(caster, Fled=9)`, ou
`IdunBattle.Entities.Components.HealthComponent$$IsAlive` = hp>=1. L'attaque normale native EST une ActiveAbility per-unite
(#139) -> passe par le MEME gate. Un attaquant a hp=0 encore sur le board (IsAlive=false, non-Fled) rend
l'attaque un no-op AVANT tout roll. L'offline (`AttackDamageOperation.execute`, qui mirror le natif
`IdunBattle.Operations.AttackDamageOperation$$Execute` — SANS gate liveness) sur-executait une attaque complete depuis
un attaquant mort. Fix : gate ACTEUR-MORT au niveau DISPATCH (`DamageHandler.visit_AttackUnitMessage` +
`AbilityHandler.visit_ActiveAbilityMessage`, mirror d'ExecuteInternal), inerte sur tout attaquant vivant.

Repro DETERMINISTE (seed 123, board MC1_67) : astraPrimarisPsy (u95) attaque normale Psychic (id 69).
1. CONTREFACTUEL : u95 VIVANT -> genesKelermorph (u79) inflige un degat normal (gate inerte, offline==live).
   Cette attaque TUE u95 (overwatch au deplacement + retaliation, deterministe seed 123).
2. REPRO : u95 MORT -> tauDarkstrider (u81, Infiltrate) et templAggressor (u83) : le live NO-OP (0 tirage,
   0 degat), l'offline sur-executait 2924 pre-fix. Post-fix : offline no-op == live. (Les cibles portant ou
   non Infiltrate prennent le MEME no-op -> ce n'est PAS une eligibilite de cible mais l'acteur mort.)

LIVE-agreement, ASCII-only. Cf. docs/rl/case-70-dead-attacker-noop.md."""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, unit_is_dead
from engine.entities.pathfinding.board import Board

ATTACKER_VIS = "astraPrimarisPsy"   # attaque normale Psychic (id 69)
ALIVE_TGT_VIS = "genesKelermorph"   # u79 : cible du contrefactuel (l'attaque tue u95)
DEAD_TGTS_VIS = ["tauDarkstrider", "templAggressor"]  # u81 (Infiltrate) / u83 : cibles du no-op post-mortem


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _draws(a, b):
    return b - a + (624 if b < a else 0)


def _plan_tile(dec, att, tgt):
    for ap in (dec.get("attackPlans") or []):
        if ap.get("unitId") != att:
            continue
        for ev in (ap.get("evals") or []):
            if ev.get("targetId") == tgt:
                rk = (ev.get("ranked") or [{}])[0]
                return (rk.get("col"), rk.get("row"))
    return (None, None)


def _run_attack(rpc, rid, board, att, tgt, norm_id):
    """Deplace l'attaquant au tuile-plan (si un existe), capture l'etat PRE-attaque, joue l'attaque LIVE
    et rejoue OFFLINE (AttackUnitMessage). Renvoie les mesures des deux cotes + le statut mort offline."""
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 3, "allAbilities": True}, 90)
    col, row = _plan_tile(dec, att, tgt)
    if col is not None:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": att, "to": {"col": col, "row": row}}}, 40)
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    st = load_state(dv2, ob2, snap); st.board = board
    ae = st.get_entity(att)
    off_dead = unit_is_dead(ae)
    te = st.get_entity(tgt)
    hc = te.get_component(HealthComponent) if te is not None else None
    hp_before = hc.hp if hc is not None else None
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    st.rng = _rng(s0); mti0 = st.rng.mti
    runner = Runner(st).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tgt, "abilityType": norm_id}}, 40)
    s1 = rpc("dumpRng", {"runnerId": rid}, 30)
    live_nd = _draws(s0["mti"], s1["mti"]) if (_ok(s0) and _ok(s1)) else None
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tgt), None)
    live_dmg = (hp_before - live_after) if (hp_before is not None and live_after is not None) else None
    runner.apply(AttackUnitMessage(att, tgt))
    off_nd = _draws(mti0, st.rng.mti)
    off_after = st.get_entity(tgt).get_component(HealthComponent).hp
    off_dmg = (hp_before - off_after) if hp_before is not None else None
    return {"off_dead": off_dead, "live_dmg": live_dmg, "live_nd": live_nd,
            "off_dmg": off_dmg, "off_nd": off_nd, "last_none": runner.damage_handler.last is None,
            "hp_before": hp_before}


@pytest.fixture(scope="module")
def seq(live_session, rpc, build_runner):
    """Sequence deterministe seed 123/MC1_67 : drive u95 au contact, puis attaque u79 (contrefactuel, tue
    u95), puis u95-mort attaque u81 et u83 (repro). Renvoie {alive, dead: {u81, u83}}."""
    import predict_samples as PV
    sid = live_session
    b = build_runner("123")
    rid, my_team = b["rid"], b["my_team"]
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        pytest.skip("dumpRng indispo")
    PV._drive_into_range(sid, rid, my_team, 6)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ids = {u.get("visualId"): u.get("id") for u in (dec.get("units") or [])}
    a = ids.get(ATTACKER_VIS)
    if a is None:
        pytest.skip(f"{ATTACKER_VIS} absent (build seed 123 change ?)")
    au = next((u for u in (dec.get("units") or []) if u.get("id") == a), {})
    norm = next((ab for ab in (au.get("abilities") or []) if ab.get("kind") == "normal"), {})
    nid = norm.get("id")
    u79 = ids.get(ALIVE_TGT_VIS)
    dead_ids = [ids.get(v) for v in DEAD_TGTS_VIS]
    if nid is None or u79 is None or any(x is None for x in dead_ids):
        pytest.skip("roster seed 123 incomplet (u79/u81/u83)")
    alive = _run_attack(rpc, rid, board, a, u79, nid)       # contrefactuel : tue u95
    dead = {}
    for vis, tid in zip(DEAD_TGTS_VIS, dead_ids):
        dead[vis] = _run_attack(rpc, rid, board, a, tid, nid)   # repro : u95 mort
    return {"alive": alive, "dead": dead}


def test_alive_attacker_deals_normal_damage(seq):
    """CONTREFACTUEL : le gate ne sur-immunise PAS un attaquant VIVANT. u95 vivant -> u79 inflige un degat
    normal (l'operation s'execute, last non-None) et l'offline == live (chemin #65 validate)."""
    c = seq["alive"]
    assert c["off_dead"] is False, "u95 doit etre VIVANT pour le contrefactuel"
    assert c["last_none"] is False, "gate INERTE attendu (attaquant vivant) : l'attaque doit s'executer"
    assert c["off_dmg"] and c["off_dmg"] > 0, f"attaquant vivant : degat > 0 attendu, off={c['off_dmg']}"
    assert c["off_dmg"] == c["live_dmg"], (
        f"attaquant vivant : offline {c['off_dmg']} != live {c['live_dmg']} (le gate a-t-il sur-fire ?)")


@pytest.mark.parametrize("vis", DEAD_TGTS_VIS)
def test_dead_attacker_is_noop(seq, vis):
    """REPRO : un attaquant MORT (u95, tue par son attaque sur u79) -> attaque sur u81/u83 = NO-OP des DEUX
    cotes (0 tirage RNG, 0 degat). Pre-fix l'offline sur-executait 2924 ; post-fix il no-op == live."""
    c = seq["dead"][vis]
    assert c["off_dead"] is True, f"u95 doit etre MORT pour le repro ({vis})"
    # LIVE : no-op (le natif gate le caster mort dans ExecuteInternal)
    assert c["live_dmg"] == 0, f"live : attaquant mort -> 0 degat attendu, obtenu {c['live_dmg']} ({vis})"
    assert c["live_nd"] == 0, f"live : attaquant mort -> 0 tirage RNG attendu, obtenu {c['live_nd']} ({vis})"
    # OFFLINE (post-fix) : no-op identique
    assert c["last_none"] is True, f"offline : attaquant mort -> aucune operation (last None), ({vis})"
    assert c["off_dmg"] == 0, f"offline : attaquant mort -> 0 degat attendu, obtenu {c['off_dmg']} ({vis})"
    assert c["off_nd"] == 0, f"offline : attaquant mort -> 0 tirage RNG, obtenu {c['off_nd']} ({vis})"
    assert c["off_dmg"] == c["live_dmg"], f"offline {c['off_dmg']} != live {c['live_dmg']} ({vis})"
