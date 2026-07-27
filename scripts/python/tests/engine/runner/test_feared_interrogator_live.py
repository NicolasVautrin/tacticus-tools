"""FearedInterrogator (1235, darkaAsmodai) — +extraDmg / +extraHits : replay-diff live, 3 discriminants.

`FearedInterrogatorAbility$$CreateBehaviour` pose DEUX effets sur ASMODAI :
  * `FearedInterrogator_Target` (1295) = MARQUEUR — son `CreateTargetSelector` designe les ennemis
    `Stunned`/`Pinned` OU adjacents a un AUTRE Dark Angel ami, parmi `ValidNormalAttackTargets(Asmodai)`.
    Il n'est JAMAIS materialise sur la cible (verifie live) -> le port RE-EVALUE le selecteur.
  * `FearedInterrogator_Owner` (1294) = `+extraDmg` si `HasEffect(Target, 1295, Both)`, `+extraHits`
    en plus si `HasTrait(Target, 0x7ea = grande-alliance Chaos)`.

Les 3 cas (dont un NEGATIF) sont joues sur LE MEME runner, positions DRIVEES (`applyAction move`
ignore la portee) :
  NEG      cible ni Pinned/Stunned ni adjacente a un ami Dark Angel -> AUCUN bonus
  POS_DMG  cible NON Chaos collee a `darkaCompanion`                -> +extraDmg, coups INCHANGES
  POS_HITS cible CHAOS collee au meme ami                            -> +extraDmg ET +extraHits
"""
from __future__ import annotations

import json

import pytest

ASMODAI = "darkaAsmodai"
DA_ALLY = "darkaCompanion"
FOE_XENOS = "necroOverlord"
FOE_CHAOS = "thousTzaangor"
FI_TARGET_EFFECT = 1295
BUILD = ["--roster", "1", "--p-units", f"{ASMODAI},{DA_ALLY}",
         "--a-units", f"{FOE_XENOS},{FOE_CHAOS}", "--hp-target", "90000", "--no-ai"]


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _unit(dv, vid):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vid and u.get("alive")), None)


def _measure(rpc, rid, label, tgt_vis, a_pos, ally_pos, tgt_pos, other_pos):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import HealthComponent
    from engine.runner.damage_model import marked_effect_types_for_target

    def move(uid, col, row):
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 40)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    uA = _unit(dv, ASMODAI)
    if uA is None:
        pytest.skip("Asmodai absent du build")
    my_player = uA.get("owner")
    for _ in range(8):                      # rendre son activation a Asmodai (les cas s'enchainent)
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        uA = _unit(dv, ASMODAI)
        if uA is not None and dv.get("currentPlayer") == my_player and uA.get("hasAction"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    uF, uT = _unit(dv, DA_ALLY), _unit(dv, tgt_vis)
    uO = _unit(dv, FOE_CHAOS if tgt_vis == FOE_XENOS else FOE_XENOS)
    if not (uA and uF and uT and uO):
        pytest.skip("unite manquante")
    aid, fid, tid, oid = uA["id"], uF["id"], uT["id"], uO["id"]
    # parking d'abord (un move vers une tuile OCCUPEE echoue silencieusement), geometrie ensuite
    move(oid, *other_pos)
    move(fid, 0, 8)
    move(aid, 1, 8)
    move(tid, *tgt_pos)
    move(fid, *ally_pos)
    move(aid, *a_pos)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    marked = marked_effect_types_for_target(state, aid, tid)

    a2 = next((u for u in (dv.get("units") or []) if u.get("id") == aid), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and "mt" in s0):
        pytest.skip("dumpRng indispo")
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": aid, "targetId": tid, "abilityType": norm["id"]}}, 40)
    a0 = (res.get("actions") or [{}])[0]
    if not a0.get("ok"):
        pytest.skip(f"attaque live KO: {str(res)[:160]}")
    live_ph = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)
    runner.apply(AttackUnitMessage(aid, tid))
    rr = runner.damage_handler.last or {}
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    return {"label": label, "marked": set(marked), "live_ph": live_ph,
            "off_ph": rr.get("per_hit"), "live_after": live_after, "off_after": off_after}


@pytest.fixture(scope="module")
def fi_cases(rpc, build_runner):
    rid = build_runner("31337", extra=BUILD)["rid"]
    return {
        "NEG": _measure(rpc, rid, "NEG", FOE_XENOS, (3, 3), (0, 0), (3, 4), (6, 0)),
        "POS_DMG": _measure(rpc, rid, "POS_DMG", FOE_XENOS, (3, 3), (3, 5), (3, 4), (6, 0)),
        "POS_HITS": _measure(rpc, rid, "POS_HITS", FOE_CHAOS, (3, 3), (3, 5), (3, 4), (6, 8)),
    }


@pytest.mark.parametrize("case", ["NEG", "POS_DMG", "POS_HITS"])
def test_replay_diff_bit_exact(fi_cases, case):
    """Le degat par coup ET les PV finaux offline reproduisent le live AU COUP PRES dans les 3 cas."""
    c = fi_cases[case]
    assert c["live_ph"], f"[{case}] aucun degat live capte"
    assert c["off_ph"] == c["live_ph"], (
        f"[{case}] per-hit offline {c['off_ph']} != live {c['live_ph']}")
    assert c["off_after"] == c["live_after"], (
        f"[{case}] PV cible offline {c['off_after']} != live {c['live_after']}")


def test_marker_gates_are_discriminant(fi_cases):
    """Le MARQUEUR 1295 est absent sans condition remplie (cas NEGATIF) et present sinon."""
    assert FI_TARGET_EFFECT not in fi_cases["NEG"]["marked"], (
        "cible ni Pinned/Stunned ni adjacente a un ami Dark Angel : le marqueur ne devrait PAS etre pose")
    assert FI_TARGET_EFFECT in fi_cases["POS_DMG"]["marked"], (
        "cible adjacente a un autre Dark Angel ami : le marqueur devrait etre pose")
    assert FI_TARGET_EFFECT in fi_cases["POS_HITS"]["marked"]


def test_extra_hits_only_against_chaos(fi_cases):
    """`HasTrait(Target, 0x7ea = Chaos)` MORD : +extraHits seulement contre une cible Chaos."""
    n_neg = len(fi_cases["NEG"]["live_ph"])
    n_dmg = len(fi_cases["POS_DMG"]["live_ph"])
    n_hits = len(fi_cases["POS_HITS"]["live_ph"])
    assert n_dmg == n_neg, (
        f"cible marquee NON Chaos : {n_dmg} coups vs {n_neg} sans marqueur -> extraHits applique a tort")
    assert n_hits > n_neg, (
        f"cible marquee ET Chaos : {n_hits} coups vs {n_neg} -> le +extraHits ne mord pas")


def test_extra_damage_only_when_marked(fi_cases):
    """Le +extraDmg n'entre QUE quand le marqueur est pose (comparaison des degats par coup)."""
    neg, pos = fi_cases["NEG"]["live_ph"], fi_cases["POS_DMG"]["live_ph"]
    assert min(pos) > max(neg), (
        f"cible marquee {pos} pas strictement au-dessus de la non marquee {neg} "
        "(le +extraDmg de FearedInterrogator ne se voit pas)")
