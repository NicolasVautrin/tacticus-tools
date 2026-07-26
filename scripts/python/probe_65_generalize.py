#!/usr/bin/env python
"""Probe #65 GENERALISATION adversariale — MEME attaquant/cible, block gate PUREMENT par le profil.

eldarFarseer : arme MELEE Piercing (blockable) + arme RANGED Psychic (NoBlocking).
Cible orksNob : trait BeastSlayer -> source de block (chance 10 / 100% FixedArmor).

  - MELEE (Piercing)  : block DOIT etre roule (offline block_sources non vide, tirage block consomme,
                        offline draws == live draws).
  - RANGED (Psychic)  : block BYPASSE (offline block_sources None, 0 tirage block, offline draws == live).

Discriminant = draw count offline (execute) vs live (dumpRng avant/apres), PLUS l'egalite des PV cible.
On DEPLACE eldarFarseer (drive-positions) pour forcer chaque configuration. ASCII only.
Usage: python probe_65_generalize.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
ATK = "eldarFarseer"
TGT = "orksNob"


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def build(tag, seed=777):
    state = ROOT / "logs" / "runners" / f"p65gen-{tag}.json"
    state.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state), "--board", "MC1_67",
         "--roster", "1", "--p-units", ATK, "--a-units", TGT],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return -1, None
    d = json.loads(state.read_text())
    return d["runnerId"], d.get("myTeam", 1)


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _find(dec, vis):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")), None)


def _hp_ob(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _live_ph(res, tid, norm_id):
    ph = []
    a0 = (res.get("actions") or [{}])[0]
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm_id:
            ph.append(td.get("Amount"))
    return ph


def _advance(rpc, rid, owner, max_iter=16):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        if not _ok(dec):
            return None
        if dec.get("currentPlayer") == owner:
            return dec
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None


def _drive(rpc, rid, board, want_dist, owner):
    """want_dist=1 -> melee ; want_dist=2 -> ranged (a portee mais non adjacent)."""
    from engine.entities.pathfinding.board import Board
    for _turn in range(16):
        dec = _advance(rpc, rid, owner)
        if dec is None:
            return None, None, None
        me = _find(dec, ATK); tgt = _find(dec, TGT)
        if me is None or tgt is None:
            return dec, me, tgt
        d = hexgeo.distance(_pos(me), _pos(tgt))
        if (want_dist == 1 and d == 1) or (want_dist == 2 and d == 2):
            return dec, me, tgt
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or []) if t.get("col") is not None]
        tp = _pos(tgt)
        cand = [p for p in tiles if hexgeo.distance(p, tp) == want_dist]
        if cand:
            best = min(cand, key=lambda p: hexgeo.distance(p, _pos(me)))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 40)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            me2 = _find(dec2, ATK); tgt2 = _find(dec2, TGT)
            if me2 and tgt2 and hexgeo.distance(_pos(me2), _pos(tgt2)) == want_dist:
                return dec2, me2, tgt2
        # rapprocher
        if tiles:
            best = min(tiles, key=lambda p: hexgeo.distance(p, tp))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None, None, None


def run_case(rpc, want_dist, label):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation

    rid, my_team = build(label)
    if rid < 0:
        return f"{label}: build KO"
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq") if bg.get("tiles") else None
        dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        me0 = _find(dec0, ATK)
        owner = me0.get("owner") if me0 else None
        dec, me, tgt = _drive(rpc, rid, board, want_dist, owner)
        if me is None or tgt is None:
            return f"{label}: drive KO"
        d = hexgeo.distance(_pos(me), _pos(tgt))
        dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        norm = next((ab for ab in (me.get("abilities") or []) if ab.get("kind") == "normal"), None)
        if norm is None:
            return f"{label}: pas d'attaque normale"
        hp0 = _hp_ob(ob2, tgt["id"])
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        # OFFLINE
        state = load_state(dv2, ob2, snap); state.board = board
        rng = IntBasedMersenneTwister(); rng.mt = list(s0["mt"]); rng.mti = s0["mti"]; state.rng = rng
        r_off = AttackDamageOperation.execute(state, me["id"], tgt["id"])
        off_draw = state.rng.mti - s0["mti"] + (624 if state.rng.mti < s0["mti"] else 0)
        # LIVE
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": me["id"], "targetId": tgt["id"], "abilityType": norm["id"]}}, 60)
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        live_draw = s1["mti"] - s0["mti"] + (624 if s1["mti"] < s0["mti"] else 0) if (_ok(s0) and _ok(s1)) else None
        live_ph = _live_ph(res, tgt["id"], norm["id"])
        live_after = _hp_ob(rpc("observeBattle", {"runnerId": rid}, 40), tgt["id"])
        off_after = hp0 - r_off["total"] if hp0 is not None else None
        match = "OK" if (live_after is not None and off_after == live_after) else "MISMATCH"
        draw_match = "OK" if off_draw == live_draw else "DIFF"
        print(f"[{label}] dist={d} profile={r_off.get('profile')} ranged={r_off.get('ranged')} "
              f"hits={r_off.get('hits')}")
        print(f"    OFFLINE per_hit={r_off['per_hit']} total={r_off['total']} did_block={r_off['did_block']} "
              f"draws={off_draw} after={off_after}")
        print(f"    LIVE    per_hit={live_ph} live_after={live_after} draws={live_draw}")
        print(f"    -> PV {match} ; draw-count {draw_match} (off {off_draw} vs live {live_draw})")
        return f"{label}: PV={match} draws={draw_match}"
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def main():
    sid = _resolve_session()

    def rpc(method, body, t=90):
        return _r(sid, method, body, t)

    results = []
    results.append(run_case(rpc, 1, "MELEE-Piercing"))     # blockable
    results.append(run_case(rpc, 2, "RANGED-Psychic"))     # NoBlocking
    print("\n=== BILAN ===")
    for r in results:
        print("  " + r)


if __name__ == "__main__":
    main()
