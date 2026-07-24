"""#220 PsychicFortress_DmgReduction (AURA 1010) — REPLAY-DIFF quand un ami de Tigurius DEFEND en Psychic.

Tigurius (ultraTigurius) porte le passif PsychicFortress : `PsychicFortressAbility.CreateBehaviour
@181224070` pose l'effet aura `PsychicFortress_DmgReduction` (0x3f2=1010) sur LUI-MEME (capte live
source=Tigurius) qui PROJETTE une reduction PLATE -dmgReduction du degat PSYCHIQUE recu par ses AMIS
ring-1 (`CreateDamageModifier @180f66a30` = ForAddition(OwnerIsTarget & DamageProfileIs(0xd=Psychic),
Multiply(ConfigVar(0x12), Direct(-1))) ; selector `CreateTargetSelector @180f66c30` =
Friends(SurroundingUnits(range=1, includeCenter=false))). Jumeau structurel de DaughterOfTheAbyss_Owner
@180f3d070 / Nightshroud @180f5bff0 -> flat_reductions PRE-percage (canal aura defense).

On drive les positions (applyAction ignore la portee) : ami ADJACENT a Tigurius (ring-1, aura ACTIVE)
vs a distance 2 (ring-2, aura INACTIVE), attaque PSYCHIQUE de bloodMephiston (pierce 100 -> pas de
dilution armure), RNG seede via dumpRng, --crit force pour sortir du regime degenere (base >> reduction).
On exige off_ph == live_ph AU COUP PRES dans les DEUX cas, ET la reduction presente (flat_reductions) en
ring-1 / absente en ring-2. Lit l'etat LIVE (rien de hardcode). ASCII-only.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.runner.damage_model import defender_modifiers

ATTACKER = "bloodMephiston"          # arme Psychic (pierce 100, multi-coups) -> reduction visible
CARRIER = "ultraTigurius"            # passif PsychicFortress : aura -dmgReduction Psychic aux amis ring-1
ALLY = "ultraApothecary"             # ami simple (aucune reduction de degat propre)

# positions (col,row) : (Tigurius, ami F, Mephiston M) ; M lateral -> T PAS sur la ligne M->F (LoS libre)
POS_RING1 = ((3, 5), (3, 4), (5, 4))   # F a distance 1 de T -> aura ACTIVE
POS_RING2 = ((3, 5), (3, 3), (3, 1))   # F a distance 2 de T -> aura INACTIVE


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _unit(dv, vid):
    return next((x for x in (dv.get("units") or []) if x.get("visualId") == vid and x.get("alive")), None)


def _measure(rpc, rid, t_pos, f_pos, m_pos):
    """Place T/F/M, cale le tour de l'attaquant, rejoue l'attaque Psychique RNG-seedee -> dict resultat."""
    def move(uid, col, row):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "move", "unitId": uid,
                                                        "to": {"col": col, "row": row}}}, 40)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    uM, uT, uF = _unit(dv, ATTACKER), _unit(dv, CARRIER), _unit(dv, ALLY)
    if not (uM and uT and uF):
        pytest.skip("unite manquante (build/pool)")
    tid_M, tid_T, tid_F = uM["id"], uT["id"], uF["id"]
    m_owner = uM.get("owner")
    move(tid_M, 0, 1)
    move(tid_T, *t_pos)
    move(tid_F, *f_pos)
    move(tid_M, *m_pos)
    for _ in range(4):                       # caler le tour de l'attaquant
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if dv.get("currentPlayer") == m_owner:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    uT, uF, uM = _unit(dv, CARRIER), _unit(dv, ALLY), _unit(dv, ATTACKER)
    def _p(u): p = u.get("pos") or {}; return (p.get("col"), p.get("row"))
    d_TF = hexgeo.distance(_p(uT), _p(uF))
    if _p(uT) in hexgeo.line(_p(uM), _p(uF)):
        pytest.skip("Tigurius sur la ligne de tir (LoS bloque) -> geometrie a ajuster")

    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    # #63/#64 : board charge A LA SOURCE (load_state board=) -> les feuilles POSITIONNELLES du combat
    # (elevation/trench/terrain) ne sont plus des no-op. Positions de ce test PLATES (bit-exact deja),
    # mais sans board un futur ajustement vers des tuiles a relief masquerait la reduction PsychicFortress
    # sous un bonus d'elevation manque (faux mismatch). cf. docs/rl/case-63.
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym") if (isinstance(bg, dict) and bg.get("tiles")) else None
    state = load_state(dv, ob, snap, board=board)
    te = state.get_entity(tid_F)
    hc = te.get_component(HealthComponent) if te else None
    if hc is None or hc.hp is None:
        pytest.skip("ami introuvable offline")
    dmods, _ = defender_modifiers(state, tid_F, hc.hp, is_melee=False,
                                  damage_profile="Psychic", attacker_id=tid_M)
    a2 = next((u for u in (dv.get("units") or []) if u.get("id") == tid_M), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and "mt" in s0):
        pytest.skip("dumpRng indispo")
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {"kind": "ability", "casterId": tid_M,
                                                         "targetId": tid_F, "abilityType": norm["id"]}}, 40)
    a0 = (res.get("actions") or [{}])[0]
    if not a0.get("ok"):
        pytest.skip(f"attaque live KO: {str(res)[:160]}")
    live_ph, did_evade = [], False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid_F and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
            did_evade = did_evade or bool(td.get("Attack_DidEvade"))
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid_F), None)
    runner.apply(AttackUnitMessage(tid_M, tid_F))
    rr = runner.damage_handler.last
    off_after = state.get_entity(tid_F).get_component(HealthComponent).hp
    return {"d_TF": d_TF, "flat_reductions": list(dmods.flat_reductions),
            "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"),
            "live_after": live_after, "off_after": off_after, "did_evade": did_evade,
            "hit_count": len(live_ph)}


@pytest.fixture(scope="session")
def pf_ring1(rpc, build_runner):
    b = build_runner("777", extra=["--crit", "100,3000", "--roster", "1",
                                   "--p-units", ATTACKER, "--a-units", f"{CARRIER},{ALLY}"])
    return _measure(rpc, b["rid"], *POS_RING1)


@pytest.fixture(scope="session")
def pf_ring2(rpc, build_runner):
    b = build_runner("777", extra=["--crit", "100,3000", "--roster", "1",
                                   "--p-units", ATTACKER, "--a-units", f"{CARRIER},{ALLY}"])
    return _measure(rpc, b["rid"], *POS_RING2)


def test_aura_active_ring1_reduces_and_bitexact(pf_ring1):
    """Ami ADJACENT a Tigurius (ring-1) : l'aura Psychic est ACTIVE (flat_reductions non vide) ET le
    degat PSYCHIQUE recu est reproduit AU COUP PRES par le runner (meme reduction plate que le natif)."""
    c = pf_ring1
    if c["did_evade"] or not c["live_ph"]:
        pytest.skip("coup evade / aucun degat live capte")
    assert c["d_TF"] == 1, f"ami pas a ring-1 de Tigurius (dist={c['d_TF']})"
    assert c["flat_reductions"], (
        "ami ring-1 mais flat_reductions vide -> aura PsychicFortress non materialisee "
        f"(reductions={c['flat_reductions']})")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live : off={c['off_ph']} live={c['live_ph']} "
        "(reduction aura Psychic non appliquee identiquement ?)")
    assert c["off_after"] == c["live_after"], (
        f"PV ami offline {c['off_after']} != live {c['live_after']}")


def test_aura_inactive_ring2_bitexact(pf_ring2):
    """Ami a distance 2 de Tigurius (ring-2) : aura INACTIVE (flat_reductions vide) ET degat plein
    reproduit AU COUP PRES (contrefactuel : la reduction ne s'applique QUE au ring-1)."""
    c = pf_ring2
    if c["did_evade"] or not c["live_ph"]:
        pytest.skip("coup evade / aucun degat live capte")
    assert c["d_TF"] == 2, f"ami pas a ring-2 de Tigurius (dist={c['d_TF']})"
    assert not c["flat_reductions"], (
        f"ami ring-2 mais flat_reductions={c['flat_reductions']} -> aura ne devrait PAS s'appliquer hors ring-1")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live (sans aura) : off={c['off_ph']} live={c['live_ph']}")
    assert c["off_after"] == c["live_after"], (
        f"PV ami offline {c['off_after']} != live {c['live_after']}")
