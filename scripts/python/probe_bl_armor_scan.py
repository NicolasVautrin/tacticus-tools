#!/usr/bin/env python
"""Probe utilitaire (case-bl-1029-1020) : ARMURE des a-units d'un build SANS `--hp-target`.

Le profil de degat des deux abilities portees est `Piercing` -> un montage discriminant EXIGE une cible
a armure NON NULLE (sinon le percage n'a rien a mordre). `--hp-target` met `Armor`/`FixedArmor` a 0 :
ce probe verifie quelles unites du roster adverse gardent une armure exploitable sans ce flag.

ASCII only. Usage: python probe_bl_armor_scan.py [--seed 777] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.components import StatsComponent, UnitComponent, HealthComponent  # noqa: E402
from engine.entities.stats import StatType, StatPart  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_bl_armor_scan.json"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--p-units", default="blackAbaddon,blackHaarken")
    ap.add_argument("--a-units", default="necroWarden,necroDestroyer,necroOverlord")
    args = ap.parse_args(argv)
    sid = _resolve_session()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed), "--state-file", str(STATE),
         "--board", args.board, "--p-units", args.p_units, "--a-units", args.a_units],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[armor] build KO: {(proc.stderr or proc.stdout or '')[-400:]}")
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    rpc = lambda m, b, t=90: _r(sid, m, b, t)  # noqa: E731
    try:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 150)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        st = load_state(dv, ob, snap)
        for uid, e in sorted(st.entities.items()):
            uc = e.get_component(UnitComponent)
            sc = e.get_component(StatsComponent)
            hc = e.get_component(HealthComponent)
            if uc is None or sc is None:
                continue
            g = sc.ctx.stats.get_stat
            print("uid=%-4s vis=%-22s hp=%-7s armor=%-6s fixedArmor=%-6s attack=%s"
                  % (uid, uc.visual_id, (hc.hp if hc else None),
                     g(int(StatType.ARMOR), int(StatPart.CURRENT)),
                     g(int(StatType.FIXED_ARMOR), int(StatPart.CURRENT)),
                     g(int(StatType.ATTACK), int(StatPart.CURRENT))))
        return 0
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
