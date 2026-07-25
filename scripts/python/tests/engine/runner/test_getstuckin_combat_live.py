"""#62c GetStuckIn (coups bonus COMBAT) — REPLAY-DIFF BIT-EXACT quand orksNob ATTAQUE.

orksNob (Tanksmasha) porte le trait GetStuckIn -> en COMBAT, sur chaque coup d'INDEX IMPAIR (0-based) le
natif tire `Maybe(GetBonusHitChance)` (behaviour `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateBehaviour`, roll dans `EvaluateAfterHitTriggers`) ;
succes => +1 coup bonus DEFERE (FIFO) apres la boucle de base. En 1v1 la chance = 30 (branche 100 =
orks_adj>=2 / amis_adj>=4 non atteinte). AVANT le port (#62c), le runner OMETTAIT ce roll -> desync RNG
des le 1er coup impair. APRES (roll `next_bool(30)` a l'index impair + coups bonus deferes), le runner
consomme le MEME tirage -> replay-diff bit-exact.

Ce test valide EN MEME TEMPS la magnitude COMBAT de SmashaEad (#68) : orksNob attaquant applique son additif
SmashaEad (is_prediction=False) ; si off_ph == live_ph AU COUP PRES, la magnitude combat est fidele.

On rejoue une attaque normale d'orksNob (RNG seede via dumpRng) contre une cible NON-Big/NON-Vehicle
(bloodIntercessor -> BeastSlayer_ExtraDmg=0, isole GetStuckIn+SmashaEad) et on exige off_ph == live_ph +
PV egaux. Assertion deterministe supplementaire : `getstuckin_combat_chance` d'orksNob adjacent = 30. Lit
l'etat LIVE (rien de hardcode). ASCII-only. (Modele : test_beast_slayer_block_live.py.)
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
from engine.runner.damage_model import getstuckin_combat_chance
from engine.entities.pathfinding.board import Board

ATTACKER = "orksNob"             # GetStuckIn (coups bonus) + SmashaEad (additif combat)
TARGET = "bloodIntercessor"      # NON-Big/NON-Vehicle -> BeastSlayer_ExtraDmg=0 (isole GetStuckIn+SmashaEad)


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
def gsi_combat(live_session, rpc, build_runner):
    b = build_runner("4242", extra=["--roster", "1", "--p-units", ATTACKER, "--a-units", TARGET])
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
    # DIAG #68 : parametres de l'effet SmashaEad de l'ATTAQUANT (lvl/mult/valeur additif) pour la magnitude.
    sm_diag = None
    _ae = state.get_entity(att)
    if _ae is not None and state.effects is not None:
        _ahc = _ae.get_component(HealthComponent)
        for _e in state.effects.active_effects(att, {"hp": _ahc.hp if _ahc else None}):
            if getattr(_e, "name", None) == "SmashaEad":
                _bonus = _e.create_effect_damage_bonus_for_attack()
                sm_diag = {"aal": getattr(_e, "active_ability_level", None),
                           "al": getattr(_e, "ability_level", None), "lvl": getattr(_e, "level", None),
                           "mult": getattr(_e, "ability_variables_multiplier", None),
                           "bonus": getattr(_bonus, "value", None) if _bonus is not None else None}
                break
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        pytest.skip("cible introuvable offline")
    # DETERMINISTE : orksNob adjacent a la cible -> chance GetStuckIn calculee = 30 (1v1, pas d'adjacence 100).
    ap = next((u for u in (dv2.get("units") or []) if u.get("id") == att), None)
    apos = (ap.get("pos") or {}) if ap else {}
    tpos = (tgt.get("pos") or {})
    gsi_chance = getstuckin_combat_chance(
        state, att, tid,
        (apos.get("col"), apos.get("row")) if "col" in apos else None,
        (tpos.get("col"), tpos.get("row")) if "col" in tpos else None, state.board)
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
            "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"), "gsi_chance": gsi_chance,
            "bonus_hits": (rr or {}).get("bonus_hits"), "did_evade": did_evade,
            "effects": (rr or {}).get("effects"), "base": (rr or {}).get("base"), "sm": sm_diag, "rr": rr}


def test_getstuckin_chance_present(gsi_combat):
    """DETERMINISTE : orksNob adjacent a la cible expose une chance GetStuckIn combat = 30 (1v1)."""
    c = gsi_combat
    assert c["gsi_chance"] == 30, (
        f"chance GetStuckIn attendue 30 (1v1 adjacent), obtenu {c['gsi_chance']}")


def test_getstuckin_hitcount_and_rng_aligned(gsi_combat):
    """COEUR #62c : valide la CONTRIBUTION de GetStuckIn (indep. de l'offset SmashaEad #68) :
    (1) meme NOMBRE de coups off/live (compte des coups bonus correct) ; (2) l'ecart off-live est CONSTANT
    sur tous les coups => le tirage Maybe (index impair) est consomme a la BONNE POSITION (un desync RNG
    donnerait un ecart CHAOTIQUE apres le 1er coup impair, pas constant). L'offset constant lui-meme = un
    additif deterministe (SmashaEad, cf. test xfail #68), SANS rapport avec le RNG de GetStuckIn."""
    c = gsi_combat
    assert c["rr"] is not None, "runner offline n'a rien calcule"
    if c["did_evade"]:
        pytest.skip("coup avec evade live (hors slice GetStuckIn)")
    off_ph, live_ph = c["off_ph"] or [], c["live_ph"] or []
    print(f"\n[GSI-COMBAT] live per-hit={live_ph} off per-hit={off_ph} bonus_hits={c['bonus_hits']} "
          f"chance={c['gsi_chance']} effects={c['effects']} base={c['base']} "
          f"deltas={[o - l for o, l in zip(off_ph, live_ph)]} smashaEad={c['sm']}")
    assert len(off_ph) == len(live_ph), (
        f"nombre de coups off {len(off_ph)} != live {len(live_ph)} (compte coups bonus GetStuckIn faux)")
    deltas = {o - l for o, l in zip(off_ph, live_ph)}
    assert len(deltas) == 1, (
        f"ecart off-live NON constant {sorted(deltas)} -> DESYNC RNG (tirage Maybe GetStuckIn mal positionne)")


def test_getstuckin_combat_absolute_bit_exact(gsi_combat):
    """Bit-exact ABSOLU (off_ph == live_ph + PV egaux). VERT depuis #75/#68 (case-68 MAJ 13) : l'additif
    ForAddition ATTAQUANT s'applique au degat AVANT percage/armure en COMBAT (attacker_additive_pre=True :
    bornes (base+-spread)+additif -> GetDamageWithPiercing -> %-list), PAS en +flat post-percage. La
    magnitude 599 (extraDmg[49]=333 x mult 180) etait CORRECTE ; c'etait le PLACEMENT qui sur-comptait
    la fraction non-percante (offset constant +299 avec pierce 50 vs armure 2208)."""
    c = gsi_combat
    if c["did_evade"]:
        pytest.skip("coup avec evade live")
    assert c["off_ph"] == c["live_ph"], f"off={c['off_ph']} live={c['live_ph']}"
    assert c["off_after"] == c["live_after"], f"PV off {c['off_after']} != live {c['live_after']}"
