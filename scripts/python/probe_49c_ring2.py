#!/usr/bin/env python
"""Probe #49c : DISCRIMINATEUR ring-2 « occupancy-BFS » vs « ring-2 MORT » (Gauntlets 1000).

49b a refute l'occupancy simple : u79 deplace hors (4,4) -> (4,4) libre -> u81 devrait etre
ring-2-joignable -> bucket TOUJOURS vide. Nouvelle hypothese : le selecteur ring-2
(SurroundingTiles r=2, slot 0x65) ne rend JAMAIS d'ennemi (tuiles occupees exclues aussi en
TERMINAL) -> utilite Gauntlets = ring-1 count SEUL. Grille : #117 castait avec >=4 ennemis
ring-1 ; s14 ring-1 max 1-2 < seed 3 -> vide partout.

Deux configs sur le meme runner s14 (u87 Calgar, seed 3 = Min(3, 3 ennemis vivants)) :
  B) u79->(5,5) ADJ, u77->(6,4) ADJ, u81 reste (3,5) ring-2 chemin libre via (4,4) :
     occupancy-BFS => arc(5,4)=3 -> NON-VIDE ; ring-2-mort => arc=2 -> VIDE.
  A) + u81->(4,4) ADJ (les 3 adjacents de (5,4)) :
     les DEUX hypotheses => arc=3 -> NON-VIDE (sanity : admission >= et util=count).
Si A reste vide -> modele seed/util faux a un niveau plus profond (retour decompile).

Usage: python probe_49c_ring2.py [--seed 31337] [--stop-step 14]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_49gnt_state.json"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[49c] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def nc_nonempty(res: dict) -> list:
    out = []
    for p in (res.get("positions") or []):
        if isinstance(p, dict) and p.get("bucket") != "empty":
            out.append(p)
    return out


def move_unit(sid, rid, uid, dest):
    mv = _r(sid, "applyAction", {"runnerId": rid, "actions": [
        {"kind": "move", "unitId": uid, "to": {"col": dest[0], "row": dest[1]}}]}, 60)
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
           for u in (dv.get("units") or []) if u.get("pos")}
    ok = pos.get(uid) == tuple(dest)
    print(f"[49c] move u{uid} -> {dest}: applied={mv.get('ok')} verif={'OK' if ok else 'ECHEC'}")
    return ok


def nc_eval(sid, rid, tag):
    res = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": 87, "abilityType": 1000,
                                 "sweep": True}, 90)
    hits = nc_nonempty(res)
    n = len(res.get("positions") or [])
    if hits:
        det = "; ".join(json.dumps(h, default=str)[:160] for h in hits[:4])
        print(f"[49c] {tag}: NON-VIDE ({len(hits)}/{n} positions) -> {det}")
    else:
        print(f"[49c] {tag}: VIDE partout ({n} positions)")
    return hits


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--stop-step", type=int, default=14)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    print(f"[49c] seed={args.seed} runner={rid} -> walk jusqu'au pas {args.stop_step}")

    try:
        for step in range(args.stop_step):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[49c] natif epuise au pas {step}")
                return 3
            acts = []
            for m in (dry["action"]["messages"] or []):
                if m.get("cls") == "MoveUnitMessage":
                    acts.append({"kind": "move", "unitId": m["unitId"],
                                 "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
                elif m.get("cls") == "ActiveAbilityMessage":
                    acts.append({"kind": "ability", "casterId": m["casterId"],
                                 "targetId": m.get("targetId"),
                                 "abilityType": m["abilityType"]})
                elif m.get("cls") == "FinishUnitTurnMessage":
                    acts.append({"kind": "finish", "unitId": m["unitId"]})
            if acts:
                _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)

        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
               for u in (dv.get("units") or []) if u.get("pos")}
        print(f"[49c] s14: u87={pos.get(87)} u77={pos.get(77)} u79={pos.get(79)} u81={pos.get(81)}")

        nc_eval(sid, rid, "BASELINE (u79@(4,4))")

        # ---- config B : 2 adjacents + 1 ring-2 chemin libre ----
        if not move_unit(sid, rid, 79, (5, 5)):
            return 5
        if not move_unit(sid, rid, 77, (6, 4)):
            return 5
        hits_b = nc_eval(sid, rid, "CONFIG B (79@(5,5) 77@(6,4) 81@(3,5), (4,4) libre)")

        # ---- config A : les 3 adjacents ----
        if not move_unit(sid, rid, 81, (4, 4)):
            return 5
        hits_a = nc_eval(sid, rid, "CONFIG A (les 3 adjacents de (5,4))")

        print("[49c] === VERDICT ===")
        if hits_a and not hits_b:
            print("[49c] ring-2 MORT confirme (A non-vide, B vide) : util = ring-1 count seul")
        elif hits_a and hits_b:
            print("[49c] occupancy-BFS confirme (B ET A non-vides) : ring-2 compte si chemin libre")
        elif not hits_a:
            print("[49c] A VIDE : modele seed/util FAUX plus profond -> retour decompile")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[49c] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
