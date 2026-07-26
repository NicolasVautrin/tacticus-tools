#!/usr/bin/env python
"""Probe #203 (swarm) -- LivingMetal sur un SWARM Necron (necroSmnSwarm). Le repair heal la HP
du swarm (entite unique) de round(10% du maxHP TOTAL du swarm) -> re-derive les membres vivants
(case-60). Face COMBAT offline-vs-live.

Setup (reprend probe_60) : P = necroSpyder (ScarabHive 1007 -> 2x necroSmnSwarm 5 membres) +
admecManipulus ; A = bloodSanguinary (3h Chain, --hp-target eleve pour survivre au chip). On
avance jusqu'a ce qu'un scarab existe ET soit endommage, puis :
  * capture S au TOUR ENNEMI (currentPlayer=A, scarab endommage) ;
  * LIVE : endturn (-> turn-start de P -> LivingMetal repair du swarm) -> live_regen = HP_apres-avant ;
  * OFFLINE : load_state(S) + turn_start_other_triggers(P_player) -> healed du scarab.
  * VERDICT : offline healed == live_regen EXACT (le repair porte par HealUnitOperation cape a maxHP
    ET re-derive les membres via on_group_unit_hp_changed). Skip propre si aucun scarab endommage.

ASCII only. Usage: python probe_203_swarm.py [--seed 60002] [--max-rounds 10]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                     # noqa: E402
from engine.runner.snapshot import load_state                          # noqa: E402
from engine.runner.operations.triggers import turn_start_other_triggers  # noqa: E402
from engine.runner.operations.triggers.loki.living_metal import (       # noqa: E402
    living_metal_pct, _round_half_even)

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_203_swarm_state.json"
# necroSpyder SEUL (PAS admecManipulus) : le Repair_GalvanicField 1119 du manipulus (ForRepair, WAKE)
# reviverait les membres du scarab -> re-heal a plein avant la capture -> confond le gate IsDamaged.
# Sans lui, le scarab reste a sa frontiere de membre endommagee (888/2218) = vrai discriminant du cap.
P_UNITS, A_UNITS = "necroSpyder", "bloodSanguinary"
SPY, SANG, SWARM = "necroSpyder", "bloodSanguinary", "necroSmnSwarm"
W, H = 7, 9
SCARAB_HIVE = 1007
SWARM_MV = 4


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(seed):
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", P_UNITS, "--a-units", A_UNITS, "--hp-target", "200000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[203sw] build KO:", (proc.stderr or proc.stdout or "")[-400:], file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def dv(sid, rid, full=False):
    b = {"runnerId": rid, "maxRank": 99, "allAbilities": True} if full else {"runnerId": rid, "maxRank": 1}
    return _r(sid, "decisionView", b, 120)


def alive_vis(d, vis):
    return [u for u in (d.get("units") or []) if u.get("alive") and u.get("visualId") == vis]


def pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def snap_hp(sid, rid):
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
    return {u.get("entityId"): (int((u.get("stats") or {}).get("health") or 0),
                                int(u.get("healthMax") or 0)) for u in (snap.get("units") or [])}


def endturn(sid, rid):
    _r(sid, "applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    return dv(sid, rid).get("currentPlayer")


def aiturn():
    subprocess.run([sys.executable, "rl_duel.py", "aiturn", "--state-file", str(STATE)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")


def move(sid, rid, uid, cur, goal, occupied, mv):
    cands = [t for t in hexgeo.disk(cur[0], cur[1], mv)
             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occupied and t != cur]
    cands.sort(key=lambda t: (hexgeo.distance(t, goal), hexgeo.distance(t, cur)))
    for t in cands[:12]:
        r = _r(sid, "applyAction", {"runnerId": rid, "actions": [
            {"kind": "move", "unitId": uid, "to": {"col": t[0], "row": t[1]}}]}, 60)
        if isinstance(r, dict) and not r.get("error"):
            return t
    return cur


def hive_target(sid, rid, spy_id):
    at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": spy_id}, 60)
    for u in (at.get("units") or []):
        for ab in (u.get("abilities") or []):
            if ab.get("abilityId") != SCARAB_HIVE:
                continue
            fh = [t.get("targetId") for t in (ab.get("fromHere") or []) if t.get("targetId") is not None]
            return fh[0] if fh else None
    return None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=60002)
    ap.add_argument("--max-rounds", type=int, default=12)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    pct = living_metal_pct()
    rid = build(args.seed)
    print(f"[203sw] seed={args.seed} runner={rid} pct={pct}")
    hive_cast = False
    try:
        d0 = dv(sid, rid, full=True)
        p_team = d0.get("currentPlayer")
        spy = (alive_vis(d0, SPY) or [{}])[0].get("id")
        print(f"[203sw] spyder=u{spy} P player={p_team}")
        for rnd in range(args.max_rounds):
            d = dv(sid, rid, full=True)
            if not alive_vis(d, SANG):
                print(f"[203sw] sang mort r{rnd} -> stop"); break
            spy_u = (alive_vis(d, SPY) or [None])[0]
            sang_u = alive_vis(d, SANG)[0]
            swarms = alive_vis(d, SWARM)
            sp = pos(sang_u)

            # CAST ScarabHive des qu'une cible legale existe.
            if not hive_cast and spy_u is not None:
                fh = hive_target(sid, rid, spy)
                if fh is not None:
                    r = _r(sid, "applyAction", {"runnerId": rid, "actions": [
                        {"kind": "ability", "casterId": spy, "targetId": fh,
                         "abilityType": SCARAB_HIVE}]}, 90)
                    hive_cast = isinstance(r, dict) and not r.get("error")
                    print(f"[203sw] r{rnd}: CAST ScarabHive ok={hive_cast}")
                    d = dv(sid, rid, full=True)
                    swarms = alive_vis(d, SWARM)

            # un scarab endommage (missing > 0) ET currentPlayer=A -> capture + comparaison.
            hp = snap_hp(sid, rid)
            dmg_scarab = None
            for sw in swarms:
                wh = hp.get(sw["id"])
                if wh and wh[0] < wh[1]:
                    dmg_scarab = sw["id"]; break
            cur = d.get("currentPlayer")
            print(f"[203sw] r{rnd}: cp={cur} scarabs={[ (s['id'], hp.get(s['id'])) for s in swarms]}")
            if dmg_scarab is not None:
                # scarab endommage -> amener currentPlayer=A (tour ENNEMI) sans faire agir A (pas d'aiturn :
                # sang ne tape pas, le scarab reste endommage) puis comparer offline-vs-live la regen.
                if cur == p_team:
                    cur = endturn(sid, rid)     # P -> A startturn (A=sang non-Necron, pas de regen)
                return _compare(sid, rid, dmg_scarab, p_team, cur, pct)

            # driver : scarab-0 colle a sang (pour se faire taper) ; spyder approche tant que pas caste.
            occupied = {pos(u) for u in (d.get("units") or []) if u.get("alive")}
            if swarms:
                sw0 = swarms[0]; c0 = pos(sw0)
                if hexgeo.distance(c0, sp) > 1:
                    move(sid, rid, sw0["id"], c0, sp, occupied, SWARM_MV)
            if spy_u is not None and not hive_cast:
                move(sid, rid, spy, pos(spy_u), sp, occupied, 3)
            endturn(sid, rid); aiturn()

        print("[203sw] aucun scarab endommage au tour ennemi -> non discriminant (skip)")
        return 4
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[203sw] runner {rid} dispose")
        except Exception as e:
            print(f"[203sw] dispose KO: {e}")


def _compare(sid, rid, scarab_id, p_team, cur, pct):
    hp_before = snap_hp(sid, rid).get(scarab_id)
    uncapped = _round_half_even(hp_before[1] * pct / 100)   # 10% du maxHP PLEIN (ce que ferait un non-group)
    print(f"[203sw] capture S cp={cur} scarab u{scarab_id} hp_before={hp_before} 10%(non-cape)={uncapped}")
    dec = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    # LIVE : endturn -> P turn-start -> LivingMetal repair (INERTE sur un swarm a une frontiere de membre).
    newcp = endturn(sid, rid)
    hp_after = snap_hp(sid, rid).get(scarab_id)
    live_regen = (hp_after[0] - hp_before[0]) if hp_after else None
    print(f"[203sw] LIVE endturn -> cp={newcp} scarab hp_after={hp_after} live_regen={live_regen}")
    # OFFLINE (port) : load_state(S) + regen du player du scarab. Le cap group-unit (get_group_unit_heal_limit)
    # doit rendre healed == live (0 a une frontiere ; le 10% non-cape ~222 serait la DIVERGENCE sans le cap).
    state = load_state(dec, ob, snap)
    if state.get_entity(scarab_id) is None:
        print("[203sw] scarab absent offline -> snapshot incomplet"); return 2
    res = turn_start_other_triggers(state, p_team)
    off = next((r for r in res if r.get("type") == "living_metal_repair" and r.get("unit") == scarab_id), None)
    off_healed = off.get("healed") if off else 0            # None (amount cape a 0) -> healed 0
    print(f"[203sw] OFFLINE regen scarab={off} (off_healed={off_healed})")
    # VERDICT : offline == live EXACT. Au boundary, les deux == 0 (LivingMetal inerte sur ce swarm) ;
    # le 10% non-cape (uncapped>0) prouve que le cap group-unit est LOAD-BEARING (sinon le port divergerait).
    ok = (off_healed == live_regen) and (uncapped > 0)
    print(f"[203sw] BILAN swarm: offline_healed={off_healed} live_regen={live_regen} "
          f"(10%-non-cape={uncapped} -> le cap group-unit evite cette divergence) "
          f"-> {'OK' if ok else '** FAIL **'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
