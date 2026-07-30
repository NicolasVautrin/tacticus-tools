#!/usr/bin/env python
"""Probe #217 -- validation live de BlackRage (active 1163, bloodDeathCompany "Lucien").

Face COMBAT portee (engine/runner/abilities/loki/strike.py:BlackRageAbility + black_rage_tree) :
    SetHealth(caster -> 30% MaxHealth) + AddEffect(1342 ExtraMove & 1343 ExtraDamage & 1344 AutomaticUnit)
    + MoveUnit(caster -> charge) + UseActiveAbility(caster, target, NormalAttack).

Protocole (pattern probe_202c + test_effect_stun_live) : build LIVE Lucien vs tyranTyrantGuard (tanky,
survit), drive Lucien a portee de charge, CAPTURE l'etat pre-cast (decisionView/observe/combatSnapshot/
dumpRng -> load_state + rng cale), CAST 1163 LIVE (parse cascade brute), APPLIQUE le MEME message OFFLINE
(Runner.apply) et CONFRONTE offline vs live :
  A. SetHealth : hp offline == hp live (30% MaxHealth, DETERMINISTE bit-exact).
  B. Effets 1342/1343/1344 poses (remaining=0 live -> None offline), delta vs pre-cast.
  C. stat MOVEMENT offline == pre + extraMovement(1) (statModSources live = source-de-l'effet).
  D. Charge : Lucien offline ADJACENT a l'ennemi (dist hex 1) apres le MoveUnit.
  E. Attaque normale : offline dispatchee (rng cale pre-cast) -> total == total Loki_NormalAttack live
     (bit-exact si palier no-crit/no-block ; SOFT = report, pas fail).

ASCII only (cp1252). Usage: python probe_217_blackrage.py [--seed 31337]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import stream_events as SE  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.runner import Runner  # noqa: E402
from engine.runner.messages import ActiveAbilityMessage  # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent, HealthComponent,  # noqa: E402
                                      StatsComponent, UnitComponent)
from engine.entities.stats import StatType, StatPart  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_a217_brage_state.json"
LUCIEN = "bloodDeathCompany"
ENEMY = "tyranTyrantGuard"           # tanky BigTarget -> survit + push no-op
ABILITY = 1163
EXTRA_MOVE, EXTRA_DAMAGE, AUTOMATIC_UNIT = 1342, 1343, 1344
W, H = 7, 9


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def build(seed):
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", LUCIEN, "--a-units", ENEMY, "--hp-target", "500000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[217] build KO: {(proc.stderr or proc.stdout or '')[-400:]}")
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _board(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _free(dec):
    occ = {_pos(u) for u in (dec.get("units") or []) if u.get("alive")}
    return {(c, r) for c in range(W) for r in range(H)} - occ


def _cascade(r):
    out = list(r.get("cascade") or [])
    for a in (r.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def _tags(ev):
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


def _off_stat(state, uid, stat):
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    return sc.ctx.stats.get_stat(int(stat), int(StatPart.CURRENT)) if sc is not None else None


def _off_hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _off_pos(state, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _parse_live(cascade, luc_id, enemy_id):
    """Extrait de la cascade : setHealth (RemainingHealth sous le group BlackRage), effets poses (1342/
    1343/1344), et RemainingHealth de l'ennemi APRES le DERNIER coup Loki_NormalAttack (= avant les
    passifs VisionsOfHeresy/RapidAssault) -> permet total normal-attack = enemy_precast - normal_after_hp.

    Pas resolus PAR NOM (#254b-b) : ecrits en dur avec les ordinaux de `gqfc5mff6c`, `13` et `16`
    designaient depuis la MAJ `rnca9r7q6c` `ChangeAbility` et `LoseEffect` -- `set_health` et
    `effects` restaient donc VIDES, silencieusement."""
    out = {"set_health": None, "effects": {}, "normal_after_hp": None}
    s_change_stats = SE.step_id("ChangeStats")
    s_receive_effect = SE.step_id("ReceiveEffect")
    s_unit_damaged = SE.step_id("UnitDamaged")
    stack = []            # pile des sources de groupes ouverts (finish n'a pas d'id -> pile, cf. probe_202c)
    for ev in cascade:
        k = ev.get("kind")
        t = _tags(ev)
        if k == "group":
            stack.append(ev.get("source"))
            continue
        if k == "finish":
            if stack:
                stack.pop()
            continue
        st = ev.get("step")
        # SetHealth : le groupe `Ability_Power` BlackRage porte UnitStats_RemainingHealth
        # (transform du HP) — 1er vu
        if st == s_change_stats and ev.get("entity") == luc_id \
                and "UnitStats_RemainingHealth" in t and out["set_health"] is None:
            out["set_health"] = int(t["UnitStats_RemainingHealth"])
        # effets poses (`ReceiveEffect` -> Effect_Id ; source = group BlackRage_*)
        if st == s_receive_effect and ev.get("entity") == luc_id \
                and "Effect_SourceActiveAbility" in t:
            out["effects"][t.get("Effect_Id")] = t
        # attaque normale : coups sur l'ennemi tant qu'un ancetre Loki_NormalAttack est ouvert (dernier vu)
        if st == s_unit_damaged and ev.get("entity") == enemy_id and "Loki_NormalAttack" in stack \
                and "UnitStats_RemainingHealth" in t:
            out["normal_after_hp"] = int(t["UnitStats_RemainingHealth"])
    return out


def _apply(rpc, rid, action, t=240):
    return rpc("applyAction", {"runnerId": rid, "action": action}, t)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)  # noqa: E731
    print(f"[217] seed={args.seed} runner={rid}")
    fails = []
    try:
        board = _board(rpc, rid)
        if board is None:
            print("[217] boardGraph KO"); return 2
        # --- drive Lucien a portee de charge (dist 2-4) de l'ennemi, sur son tour ---
        luc = enemy = None
        for _turn in range(20):
            dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 150)
            luc = next((u for u in (dec.get("units") or []) if u.get("visualId") == LUCIEN and u.get("alive")), None)
            enemy = next((u for u in (dec.get("units") or []) if u.get("visualId") == ENEMY and u.get("alive")), None)
            if luc is None or enemy is None:
                print("[217] unite manquante"); return 2
            if dec.get("currentPlayer") != luc.get("owner"):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                rpc("aiPlayTurn", {"runnerId": rid}, 240)
                continue
            d = hexgeo.distance(_pos(luc), _pos(enemy))
            if 2 <= d <= 4:
                break
            ft = _free(dec)
            cands = sorted([t for t in hexgeo.disk(_pos(luc)[0], _pos(luc)[1], 4) if t in ft],
                           key=lambda t: abs(hexgeo.distance(t, _pos(enemy)) - 3))
            moved = False
            for t in cands[:6]:
                r = _apply(rpc, rid, {"kind": "move", "unitId": luc["id"], "to": {"col": t[0], "row": t[1]}}, 120)
                if ((r or {}).get("actions") or [{}])[0].get("ok"):
                    moved = True
                    break
            if not moved:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                rpc("aiPlayTurn", {"runnerId": rid}, 240)
        # --- CAPTURE PRE-CAST ---
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 150)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        luc = next((u for u in dv["units"] if u.get("visualId") == LUCIEN and u.get("alive")), None)
        enemy = next((u for u in dv["units"] if u.get("visualId") == ENEMY and u.get("alive")), None)
        if luc is None or enemy is None:
            print("[217] pre-cast unite manquante"); return 2
        luc_id, enemy_id = luc["id"], enemy["id"]
        enemy_pos = _pos(enemy)
        enemy_precast_hp = enemy.get("hp")
        d0 = hexgeo.distance(_pos(luc), enemy_pos)
        print(f"[217] pre-cast: luc id={luc_id} pos={_pos(luc)} hp={luc.get('hp')} enemy id={enemy_id} "
              f"pos={enemy_pos} dist={d0}")
        state = load_state(dv, ob, snap)
        state.board = board
        if s0 and s0.get("mt"):
            state.rng = _seed_rng(s0)
        mov_before = _off_stat(state, luc_id, StatType.MOVEMENT)
        pre_types = {int(e.effect_type) for e in state.effects.active_effects(luc_id)} if state.effects else set()

        # --- CAST 1163 LIVE ---
        r = _apply(rpc, rid, {"kind": "ability", "casterId": luc_id, "targetId": enemy_id, "abilityType": ABILITY})
        a0 = ((r or {}).get("actions") or [{}])[0]
        if not a0.get("ok"):
            print(f"[217] cast KO: {a0.get('error')}"); return 2
        live = _parse_live(_cascade(r), luc_id, enemy_id)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 150)
        luc2 = next((u for u in dv2["units"] if u.get("id") == luc_id), None)
        live_hp = luc2.get("hp") if luc2 else None
        live_pos = _pos(luc2) if luc2 else None
        live_effs = {e.get("effectType"): e for e in (luc2.get("effects") or [])} if luc2 else {}
        live_total = ((enemy_precast_hp - live["normal_after_hp"])
                      if (enemy_precast_hp is not None and live["normal_after_hp"] is not None) else None)
        print(f"[217] LIVE post: hp={live_hp} pos={live_pos} setHealth(cascade)={live['set_health']} "
              f"effets 1342/1343/1344 rem={[live_effs.get(x, {}).get('remaining') for x in (EXTRA_MOVE, EXTRA_DAMAGE, AUTOMATIC_UNIT)]}")
        print(f"[217] LIVE normal-attack total(cascade)={live_total} (enemy {enemy_precast_hp}->{live['normal_after_hp']})")

        # --- APPLIQUE OFFLINE le MEME message ---
        runner = Runner(state).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=luc_id, target_id=enemy_id, ability_type=ABILITY))
        last = runner.ability_handler.last or {}
        if not last.get("ported"):
            print(f"[217] X ability 1163 NON portee (handler.last={last})")
            fails.append("ported")
        off_hp = _off_hp(state, luc_id)
        off_pos = _off_pos(state, luc_id)
        off_mov = _off_stat(state, luc_id, StatType.MOVEMENT)
        off_types = {int(e.effect_type) for e in state.effects.active_effects(luc_id)} if state.effects else set()
        off_new = off_types - pre_types
        off_rem = {int(e.effect_type): e.remaining_turns
                   for e in state.effects.active_effects(luc_id) if int(e.effect_type) in (EXTRA_MOVE, EXTRA_DAMAGE, AUTOMATIC_UNIT)}
        off_enemy_hp = _off_hp(state, enemy_id)
        off_attack = last.get("attack")
        off_total = ((off_attack.get("attack") or {}).get("total") if off_attack else None)
        print(f"[217] OFFLINE post: hp={off_hp} pos={off_pos} movement {mov_before}->{off_mov} "
              f"new_effects={sorted(off_new)} rem={off_rem}")
        print(f"[217] OFFLINE enemy hp={off_enemy_hp} attack_subject={off_attack.get('subject') if off_attack else None} "
              f"attack_target={off_attack.get('target') if off_attack else None} attack_total={off_total}")

        # --- CONFRONTATIONS ---
        # A. SetHealth (deterministe bit-exact)
        if off_hp is not None and live_hp is not None and off_hp == live_hp:
            print(f"[217] A SetHealth OK: offline {off_hp} == live {live_hp}")
        else:
            print(f"[217] A SetHealth X: offline {off_hp} != live {live_hp}")
            fails.append("A:setHealth")
        # B. effets poses
        want = {EXTRA_MOVE, EXTRA_DAMAGE, AUTOMATIC_UNIT}
        live_has = {x for x in want if x in live_effs}
        if want <= off_new and want <= live_has:
            print(f"[217] B effets 1342/1343/1344 OK (offline new={sorted(off_new & want)}, live={sorted(live_has)})")
        else:
            print(f"[217] B effets X: offline new={sorted(off_new)} live={sorted(live_has)}")
            fails.append("B:effects")
        # remaining : live 0 -> offline None (permanent)
        for et in want:
            lr = live_effs.get(et, {}).get("remaining")
            orr = off_rem.get(et, "absent")
            exp = None if lr in (0, None) else lr
            if orr != exp:
                print(f"[217] B remaining X effet {et}: offline={orr} live={lr} (map 0->None -> {exp})")
                fails.append(f"B:rem-{et}")
        # C. movement +extraMovement
        if mov_before is not None and off_mov is not None and off_mov == mov_before + 1:
            print(f"[217] C movement OK: {mov_before} -> {off_mov} (+1 ExtraMove)")
        else:
            print(f"[217] C movement X: {mov_before} -> {off_mov} (attendu +1)")
            fails.append("C:movement")
        # D. charge : Lucien offline adjacent a l'ennemi
        d_off = hexgeo.distance(off_pos, enemy_pos) if off_pos else None
        if d_off == 1:
            print(f"[217] D charge OK: Lucien offline {off_pos} adjacent ennemi {enemy_pos} (dist 1)")
        else:
            print(f"[217] D charge X: Lucien offline {off_pos} dist={d_off} de l'ennemi {enemy_pos} (attendu 1)")
            fails.append("D:charge")
        # E. attaque normale dispatchee + total (SOFT : bit-exact si palier no-crit/no-block)
        if off_attack is not None:
            match = (off_total is not None and live_total and int(off_total) == int(live_total))
            print(f"[217] E attaque normale dispatchee: offline total={off_total} vs live Loki_NormalAttack "
                  f"total={live_total} -> {'BIT-EXACT' if match else 'diff (palier/passifs, SOFT)'}")
            if off_enemy_hp is not None and enemy_precast_hp is not None and off_enemy_hp >= enemy_precast_hp:
                print(f"[217] E X: ennemi offline non touche (hp={off_enemy_hp} >= pre {enemy_precast_hp})")
                fails.append("E:no-damage")
        else:
            print(f"[217] E attaque non dispatchee (attack=None ; rng cale={state.rng is not None})")
            fails.append("E:no-attack")

        print(f"[217] VERDICT: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}")
        return 0 if not fails else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
