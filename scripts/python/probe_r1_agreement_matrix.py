#!/usr/bin/env python
"""Probe R1 (compagnon) -- MATRICE d'agreement sur N couples (board, seed).

Sert de MESURE AVANT/APRES du fix R1 : build un runner dedie par couple, marche la trajectoire
native (`engine_validate.run_agreement`) et imprime pos / ability / stay. Chaque runner est dispose
juste apres son couple (discipline runner : jamais plus d'un runner vivant a la fois ici).

`stay` = le compteur ajoute par R1 (natif agit SANS bouger -> le port bouge-t-il quand meme ?).
C'est l'angle mort que `pos` ne voit pas.

ASCII only. Usage :
  python probe_r1_agreement_matrix.py --couples MC1_67:777:24 C3_01:31337:26 C4_09:999:26
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import engine_validate as EV  # noqa: E402
from engine import weights as W  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(seed, board, extra=None):
    state = ROOT / "logs" / "runners" / f"probeR1m-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--board", board, "--state-file", str(state)] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("  BUILD KO:", (p.stderr or p.stdout or "")[-300:])
        return None, None
    return json.loads(state.read_text())["runnerId"], state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--couples", nargs="+", default=["MC1_67:777:24"],
                    help="board:seed:steps")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[],
                    help="args `rl_duel build` supplementaires (rosters crafts, --hp-target, ...)")
    args = ap.parse_args()
    sid = _resolve_session()
    wt = W.load()
    out = []
    for c in args.couples:
        board, seed, steps = c.split(":")
        rid, state = _build(seed, board, args.extra)
        if rid is None:
            continue
        print(f"\n===== {board} / seed {seed} / runner {rid} =====")
        try:
            res = EV.run_agreement(sid, rid, int(steps), wt, log=lambda *_a, **_k: None)
        finally:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            try:
                state.unlink()
            except Exception:
                pass
        p, a, st = res["pos"], res["ability"], res["stay"]
        miss = [r for r in res["records"] if r["kind"] == "stay" and not r["match"]]
        out.append((board, seed, p, a, st))
        print(f"  pos     : exact {p['exact']}/{p['n']} | <=1hex {p['near']}/{p['n']}")
        print(f"  ability : {a['match']}/{a['n']}")
        print(f"  stay    : {st['match']}/{st['n']}")
        for m in miss:
            print(f"    STAY MISS step {m['step']} u{m['uid']} origin={m['native']} "
                  f"engine={m['engine']}")
    print("\n===== RESUME =====")
    for board, seed, p, a, st in out:
        print(f"  {board:10s} seed {seed:6s} | pos {p['exact']}/{p['n']} "
              f"(<=1hex {p['near']}/{p['n']}) | ability {a['match']}/{a['n']} | "
              f"stay {st['match']}/{st['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
