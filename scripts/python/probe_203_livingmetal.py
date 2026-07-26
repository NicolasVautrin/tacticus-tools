#!/usr/bin/env python
"""Probe #203 -- trait LivingMetal (regen % PV debut de tour, roster Necron). Face COMBAT
offline-vs-live (replay-diff) + ground truth du montant/scoping/cap/gate IsDamaged.

Setup (pool rank 17) : P = necroWarden (mesure, --hp-player pour un maxHP connu), A = necroDestroyer
(--crit-target -> gros coups qui endommagent le warden > regen). endturn(P)+aiturn(A) jusqu'a ce que
le warden manque > 2*regen ; puis :
  * GROUND TRUTH LIVE : capture S au TOUR ENNEMI (currentPlayer=A, warden deja endommage) ->
    `endturn` (flip -> turn-start de P -> LivingMetal regen) -> live_regen = HP_apres - HP_avant.
  * OFFLINE (port) : `load_state(S)` + `turn_start_other_triggers(P_player)` -> le montant `healed`
    de LivingMetalRepairAbility. Doit == live_regen EXACT (zero tolerance) ET == round_half_even(10%
    maxHP) (non cape).
  * SCOPING : offline `turn_start_other_triggers(A_player)` a S ne regen PAS le warden (P) ; et le
    necroDestroyer (A, plein) n'apparait dans aucun resultat de regen.

Ground truth du mecanisme (mesure directe, imprimee) : au bracket d'endturns purs, le warden regen
round(10% maxHP) UNIQUEMENT au tour du proprietaire (0 au tour adverse), cape a maxHP, stop a PV pleins.

ASCII only (cp1252). Usage: python probe_203_livingmetal.py [--seed 20304] [--hp 30000]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402
from engine.runner.operations.triggers import turn_start_other_triggers  # noqa: E402
from engine.runner.operations.triggers.loki.living_metal import (        # noqa: E402
    living_metal_pct, _round_half_even)

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_203_livingmetal_state.json"
WARDEN, DESTROYER = "necroWarden", "necroDestroyer"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(seed, hp):
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", WARDEN, "--a-units", DESTROYER,
         "--hp-player", str(hp), "--crit-target", "100,700"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[203] build KO:", (proc.stderr or proc.stdout or "")[-400:], file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def snap_hp(sid, rid):
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
    return {u.get("entityId"): (int((u.get("stats") or {}).get("health") or 0),
                                int(u.get("healthMax") or 0)) for u in (snap.get("units") or [])}


def cp(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer")


def units(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def endturn(sid, rid):
    _r(sid, "applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    return cp(sid, rid)


def aiturn():
    subprocess.run([sys.executable, "rl_duel.py", "aiturn", "--state-file", str(STATE)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20304)
    ap.add_argument("--hp", type=int, default=30000)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    pct = living_metal_pct()
    expect = _round_half_even(args.hp * pct / 100)
    rid = build(args.seed, args.hp)
    print(f"[203] seed={args.seed} runner={rid} hp={args.hp} pct={pct} expect_regen={expect}")
    ok = True
    try:
        al = units(sid, rid)
        war = next((u for u in al if u.get("visualId") == WARDEN), None)
        des = next((u for u in al if u.get("visualId") == DESTROYER), None)
        if not war or not des:
            print(f"[203] roster KO war={war is not None} des={des is not None}"); return 2
        wid, did = war["id"], des["id"]
        p_team = cp(sid, rid)
        print(f"[203] warden=u{wid} (P player {p_team}) destroyer=u{did}")

        # Phase 1 : endturn(P)+aiturn(A) jusqu'a warden manquant > 2*regen.
        damaged = False
        for rnd in range(16):
            hp = snap_hp(sid, rid)
            wh = hp.get(wid)
            if wh is None:
                print(f"[203] r{rnd}: warden mort -> stop"); break
            miss = wh[1] - wh[0]
            print(f"[203] r{rnd}: cp={cp(sid,rid)} warden={wh} missing={miss}")
            if miss > 2 * expect:
                damaged = True
                break
            endturn(sid, rid); aiturn()
        if not damaged:
            print("[203] warden pas assez endommage -> scenario non discriminant"); return 4

        # amener currentPlayer=A (tour ENNEMI) : la phase 1 finit sur un P-startturn (aiturn) -> endturn -> A.
        cur = cp(sid, rid)
        if cur == p_team:
            cur = endturn(sid, rid)     # P -> A
        print(f"[203] capture S au tour ENNEMI cp={cur}")

        # capture S (avant le turn-start de P).
        dec = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
        hp_before = snap_hp(sid, rid).get(wid)
        print(f"[203] S: warden hp_before={hp_before}")

        # LIVE : endturn (A -> P turn-start -> LivingMetal regen).
        newcp = endturn(sid, rid)
        hp_after = snap_hp(sid, rid).get(wid)
        live_regen = hp_after[0] - hp_before[0]
        print(f"[203] LIVE endturn -> cp={newcp} warden hp_after={hp_after} live_regen={live_regen}")

        # OFFLINE (port) : load_state(S) + scoping + regen.
        state = load_state(dec, ob, snap)
        if state.get_entity(wid) is None:
            print("[203] warden absent offline -> snapshot incomplet"); return 2
        # SCOPING offline : turn-start du player ADVERSE (A) ne regen PAS le warden (P).
        res_a = turn_start_other_triggers(state, cur)
        lm_a = [r for r in res_a if r.get("type") == "living_metal_repair"]
        # REGEN offline : turn-start du player du warden (P).
        res_p = turn_start_other_triggers(state, p_team)
        lm_p = [r for r in res_p if r.get("type") == "living_metal_repair"]
        off = next((r for r in lm_p if r.get("unit") == wid), None)
        off_healed = off.get("healed") if off else None
        off_amount = off.get("amount") if off else None
        print(f"[203] OFFLINE scoping(A-turn) lm={lm_a} | regen(P-turn) warden={off}")

        # === verdicts ===
        # 1. scoping offline : aucune regen du warden au tour adverse.
        if any(r.get("unit") == wid for r in lm_a):
            print("[203] ** FAIL scoping ** : warden regen offline au tour ADVERSE"); ok = False
        # 2. le necroDestroyer (A, plein) ne regen dans aucun resultat.
        if any(r.get("unit") == did for r in (lm_a + lm_p)):
            print("[203] ** FAIL ** : necroDestroyer regen (plein / mauvaise team)"); ok = False
        # 3. montant offline == live EXACT.
        if off_healed != live_regen:
            print(f"[203] ** FAIL montant ** offline healed={off_healed} != live {live_regen}"); ok = False
        # 4. montant == round(10% maxHP) NON cape (missing > regen a S).
        if off_amount != expect:
            print(f"[203] ** FAIL formule ** offline amount={off_amount} != round(10%)={expect}"); ok = False
        if off_healed != expect:
            print(f"[203] ** NOTE ** healed={off_healed} != expect={expect} (cape ? missing<regen)")

        print(f"[203] BILAN: offline_healed={off_healed} live_regen={live_regen} "
              f"expect(10%)={expect} scoping_ok={not any(r.get('unit')==wid for r in lm_a)} "
              f"-> {'OK' if ok else '** FAIL **'}")
        return 0 if ok else 1
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[203] runner {rid} dispose")
        except Exception as e:
            print(f"[203] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
