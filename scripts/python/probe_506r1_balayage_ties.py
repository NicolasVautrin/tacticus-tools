#!/usr/bin/env python
"""#506-r1 -- BALAYAGE : ou reste-t-il un TIE de sweep sous le regime EQUIPE (#419-r6) ?

    python probe_506r1_balayage_ties.py --board C4_09 --seeds 999,4242,777,31337 --steps 8,32

Le montage `tests/engine/_move_tile_sweep_order.py` n'observe l'ordre de sweep que sur un pas ou
DEUX positions candidates atteignent la MEME utilite d'action -- toute autre situation est tranchee
par l'utilite et ne dit RIEN de l'ordre. L'en-tete de `test_move_tile_sweep_order_live.py` dit que
`C4_09`/999 pas 14 etait « le seul couple discriminant trouve sur 10 couples balayes ».

Depuis la bascule « equiper » de #419-r6, les stats ont change : les utilites se SEPARENT la ou
elles s'egalisaient. Ce probe RE-BALAIE pour dire ou le regime existe encore, au lieu de le
supposer -- et il imprime le detail par pas, y compris les ZEROS (un balayage qui ne rendrait que
ses trouvailles ne dirait pas ce qu'il a visite).

Sortie, par (seed, pas) : l'unite activee, le nombre de tuiles a l'utilite MAX, et si les deux
ordres (`action_tiles` vs `ranked`) DIVERGENT sur ces tuiles -- le critere qui rend un couple
DISCRIMINANT.

Discipline runner : UN runner par seed, DISPOSE des que le seed est epuise.
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine"))

import probe_112_darkangels as PR                                            # noqa: E402
import rl_collect_batch as R                                                 # noqa: E402


def _rpc(sid):
    def call(method, body, timeout=60):
        return PR.rpc(sid, method, body, timeout)
    return call


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C4_09")
    ap.add_argument("--seeds", default="999,4242,777,31337")
    ap.add_argument("--steps", default="8,32", help="pas MIN,MAX (inclus)")
    ap.add_argument("--extra", default="")
    ap.add_argument("--carrier", default="",
                    help="ne rapporter que ce visualId, et imprimer son kit declenche + `best`")
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.steps.split(","))

    sid = R._resolve_session()                                               # noqa: SLF001
    rpc = _rpc(sid)
    from _move_tile_sweep_order import _apply_native, _case_at               # noqa: E402
    import subprocess
    import json
    import tempfile

    trouves = []
    for seed in a.seeds.split(","):
        seed = seed.strip()
        if not seed:
            continue
        state = Path(tempfile.gettempdir()) / ("p506r1_%s_%s.json" % (a.board, seed))
        argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
                "--state-file", str(state), "--board", a.board]
        if a.extra:
            argv += a.extra.split()
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if p.returncode != 0:
            print("[%s] BUILD KO rc=%d : %s" % (seed, p.returncode, (p.stderr or "")[-300:]))
            continue
        rid = json.loads(state.read_text(encoding="utf-8"))["runnerId"]
        print("[%s] runner %d" % (seed, rid))
        try:
            for i in range(lo):
                dry = rpc("aiStepDryRun", {"runnerId": rid}, 60)
                if not dry.get("ok") or not dry.get("hasNext"):
                    print("[%s] trajectoire finie AVANT le pas %d" % (seed, lo))
                    break
                _apply_native(rpc, rid, dry)
            for step in range(lo, hi + 1):
                dry = rpc("aiStepDryRun", {"runnerId": rid}, 60)
                if not dry.get("ok") or not dry.get("hasNext"):
                    print("[%s] pas %d : trajectoire FINIE (%s)" % (seed, step, dry.get("error")))
                    break
                uid = dry.get("activatedUnitId")
                c = _case_at(rpc, rid, step, dry, uid, strict=False)
                if c is None:
                    print("[%s] pas %2d : (aucune unite activee lisible)" % (seed, step))
                elif a.carrier:
                    if c.visual_id == a.carrier:
                        from engine.utilities.tile import tile_leaf_ctx
                        kit = tile_leaf_ctx(c.ctx).get("unit_triggered_abilities") or []
                        print("[%s] pas %2d : %-22s best=%-5s kit=%r"
                              % (seed, step, c.visual_id, c.best is not None, list(kit)))
                        if c.best is not None:
                            trouves.append((seed, step, c.visual_id, len(c.tie_tiles), True))
                else:
                    tied = set(c.tie_tiles)
                    by_a = [t for t in c.action_tiles if t in tied]
                    by_r = [t for t in c.ranked_union if t in tied]
                    div = (by_a != by_r)
                    print("[%s] pas %2d : %-22s tie=%d divergent=%s %r"
                          % (seed, step, c.visual_id, len(c.tie_tiles), div, c.tie_tiles))
                    if len(c.tie_tiles) >= 2:
                        trouves.append((seed, step, c.visual_id, len(c.tie_tiles), div))
                _apply_native(rpc, rid, dry)
        finally:
            rpc("disposeRunner", {"runnerId": rid}, 20)
            state.unlink(missing_ok=True)

    print("\n== TIES (>= 2 tuiles a l'utilite max) : %d ==" % len(trouves))
    for t in trouves:
        print("   seed=%s pas=%d %s tie=%d divergent=%s" % t)
    if not trouves:
        print("   AUCUN sur le perimetre balaye -- le regime de tie a disparu de ces couples, il "
              "n'est PAS 'introuvable' en general (le balayage ne visite que ce qu'on lui donne).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
