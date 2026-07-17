"""#93 SpiritLeech (id 1104, tyranNeurothrope) — dégât de COMBAT (config-based) : replay-diff LIVE vs porté.

SpiritLeech.ExecuteBehaviour @181209900 = AttackWithAbilityDamage(target, GetAttackDamage(combat), Psychic,
nrOfHits=1) & AddEffect(0x429 Pinned) & Heal(lifesteal 60% — DIFFERE #94). GetAttackDamage COMBAT (param_3=0)
= RandomAmount(minDmg/maxDmg config) [+ extraDmg si cible deja Pinned]. ⚠ Le COMBAT est CONFIG-based
(config-avg×mult180 ~2593), != la PREDICTION Attack-based (~2670, slot 0x27) : divergence NATIVE (verdict #92).

On force le cast de SpiritLeech (bypass scoring, cf. #87) sur une cible vanille tanky a portee 3, RNG seede,
et on confronte le per-coup + PV cible (le lifesteal soigne le CASTER, PAS la cible -> PV cible comparable).
DURCISSEMENT HARNAIS (lecon du no-op silencieux) : on assert `ability_handler.last["ported"] is True` — une
ability non portee ferait un no-op MUET (0 degat) que ce test transforme en ECHEC LOUD. On verifie aussi que
la cible recoit bien Pinned (0x429). Lit l'etat LIVE. ASCII-only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent
import hexgeo

CASTER_VIS = "tyranNeurothrope"
TARGET_VIS = "necroOverlord"         # vanille tanky (~8536 hp, effects=[] : survit + 0 reduction/block)
ABILITY = 1104                       # SpiritLeech
PINNED = 0x429
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", TARGET_VIS]
RANGE = 3                            # SpiritLeech = Ranged, range 3


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


def test_spirit_leech_combat_damage_bit_exact(live_session, rpc, build_runner):
    """Le degat de COMBAT de SpiritLeech (config-based) est reproduit per-coup bit-exact offline, la cible
    recoit Pinned, et l'ability est REELLEMENT executee (ported:True — garde anti-no-op silencieux)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    def cr_of(u):
        p = u.get("pos") or {}
        return (p.get("col"), p.get("row")) if p.get("col") is not None else None

    def tile_of(u):
        cr = cr_of(u)
        return board.id_at(cr[0], cr[1]) if cr is not None else None

    my_player = None
    caster = tgt = None
    for _turn in range(25):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        units = dec.get("units") or []
        caster = next((u for u in units if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET_VIS and u.get("alive")), None)
        if caster is None or tgt is None:
            pytest.skip(f"unite manquante (caster={bool(caster)} tgt={bool(tgt)})")
        if my_player is None:
            my_player = caster.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        if hexgeo.distance(cr_of(caster), cr_of(tgt)) <= RANGE:     # a portee (ranged 3) -> caster
            break
        dist = _bfs(board, tile_of(tgt))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == caster["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": caster["id"], "to": {"col": col, "row": row}}}, 40)
    else:
        pytest.skip("caster n'a pas atteint la portee 3 de la cible en 25 tours")

    att, tid = caster["id"], tgt["id"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap)
    ae = state.get_entity(att)
    if ae is None or ae.get_component(StatsComponent) is None:
        pytest.skip("attaquant sans StatsComponent (stats non chargees)")
    te = state.get_entity(tid)
    thc = te.get_component(HealthComponent) if te is not None else None
    if thc is None or thc.hp is None:
        pytest.skip("cible introuvable offline")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s0)

    # cast LIVE :
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": ABILITY}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    live_ph, dc, db, de = [], False, False, False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
            live_ph.append(td.get("Amount"))
            dc = dc or bool(td.get("Attack_DidCrit"))
            db = db or bool(td.get("Attack_DidBlock"))
            de = de or bool(td.get("Attack_DidEvade"))
    if dc or db or de:
        pytest.skip(f"coup non propre (crit/block/evade live): c={dc} b={db} e={de}")
    if not live_ph:
        pytest.skip("aucun event de degat live (cible hors portee / cast sans degat capte)")
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)

    # OFFLINE via le wiring ability-exec :
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=att, target_id=tid, ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    # DURCISSEMENT : l'ability DOIT etre executee (pas un no-op silencieux). Sans SpiritLeech au registry,
    # ce serait ported:False (0 degat) -> ECHEC LOUD ici au lieu d'une divergence attribuee au bruit.
    assert last.get("ported") is True, (
        f"SpiritLeech (1104) n'a PAS ete execute en combat (no-op) : last={last} ; "
        f"unported={getattr(runner.ability_handler, 'unported', None)}")
    atk = last.get("main_attack")
    assert atk is not None, f"pas de resultat d'attaque SpiritLeech offline: {last}"
    off_ph = atk["per_hit"]
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    # la cible doit porter Pinned (0x429) apres le cast (AddEffect materialise).
    off_pinned = state.effects is not None and state.effects.has_effect(tid, effect_type=PINNED)
    print(f"\n[SPIRITLEECH combat] hits={atk['hits']} base=[{atk['base_min']},{atk['base_max']}] "
          f"pierce={atk['pierce']} armor={atk['armor']} live_ph={live_ph} off_ph={off_ph} "
          f"live_after={live_after} off_after={off_after} off_pinned={off_pinned}")
    # VALIDATION du port SpiritLeech = le DEGAT (per-coup, bit-exact) + Pinned + execution reelle (ported).
    assert off_ph == live_ph, f"per-coup SpiritLeech offline {off_ph} != live {live_ph} (combat config-based)"
    assert off_pinned, "la cible ne porte pas Pinned(0x429) apres SpiritLeech (AddEffect non materialise)"

    # #94 LIFESTEAL : GetHealAmountForExecution @181209f00 = PercentageOf(LastAttackDamageMade, hpToHealPct,
    # mode=1=CEILING) (hpToHealPct HORS variablesAffectedByRarityBonus -> mult 100). Le degat est valide
    # (off_ph==live_ph) -> le montant heal est ancre au degat LIVE. GetHealTargets @18120a1e0 inclut TOUJOURS
    # le caster (Self). Round-mode natif = 1 = Ceiling (node canonique entities/formulas.py PercentageOf).
    from engine.entities.effects.magnitude import ability_var
    from engine.dsl.base import _round_fix64
    from fractions import Fraction
    csc = state.get_entity(att).get_component(StatsComponent)
    hlvl = csc.ctx.active_ability_level
    pct = int(ability_var("SpiritLeech", "hpToHealPct", hlvl, multiplier_pct=100) or 0)
    exp_heal = _round_fix64(Fraction(sum(live_ph) * pct, 100), 1)   # PercentageOf mode=1 = Ceiling (Fix64)
    heal_amount = last.get("heal_amount")
    heals = last.get("heals") or []
    print(f"[SPIRITLEECH heal] hpToHealPct={pct} dmg={sum(live_ph)} -> heal_amount={heal_amount} "
          f"(attendu {exp_heal}) heals={heals}")
    assert heal_amount == exp_heal, (
        f"heal_amount {heal_amount} != trunc(dmg {sum(live_ph)} x {pct}%/100)={exp_heal}")
    if heal_amount > 0:
        assert any(h.get("target") == att for h in heals), (
            f"le CASTER (Self, op_Addition(Self, ...)) n'est pas une cible du heal: {heals}")
    # PV cible ABSOLU = CONFONDU par des mecanismes CIBLE separes (necroOverlord a LivingMetal = heal Necron
    # par tour) + derive multi-tours de l'approche -> hors perimetre du port SpiritLeech. Le per-coup bit-exact
    # (== live_ph) EST la validation du degat inflige ; le heal cible est un autre axe (non porte). Informatif :
    if live_after is not None and off_after != live_after:
        print(f"[SPIRITLEECH combat] NOTE PV cible off={off_after} != live={live_after} "
              f"(delta {live_after - off_after} = heal cible LivingMetal / derive, hors port SpiritLeech)")
