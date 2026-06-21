#!/usr/bin/env python
"""Ephemeral wave-build helper: same as `rl_duel.py build` but bakes
RandomizeAiInput=True into the BC (the build subcommand has no flag for it).
Not a shared-doctrine file; throwaway driver for the exploration wave.
"""
from __future__ import annotations
import argparse, copy, json, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rl_duel as RD
from rl_collect_batch import (
    _load_seed_bc, _load_unspawnable, _normalize_and_extract_pool,
    _spawn_points_by_twpi, _patch_predefined_units, _patch_predefined_machines,
    _rpc, PLAYER_ID_HUMAN,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--roster", type=int, default=5)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--mow", action="store_true")
    a = ap.parse_args()

    sid = RD._resolve_session()
    RD.STATE = Path(a.state_file)

    seed_bc = _load_seed_bc()
    template_bc, pool, pool_mow = _normalize_and_extract_pool(sid, seed_bc, a.rank)
    bad_u, bad_mow = _load_unspawnable(a.rank)
    pool = [u for u in pool if u not in bad_u]
    pool_mow = [u for u in pool_mow if u not in bad_mow]

    rng = random.Random(a.seed)
    p_units = rng.sample(pool, a.roster)
    a_units = rng.sample(pool, a.roster)

    p_mow = a_mow = None
    if a.mow and pool_mow:
        p_mow, a_mow = rng.choice(pool_mow), rng.choice(pool_mow)

    bc = copy.deepcopy(template_bc)
    _patch_predefined_units(bc, a_units)
    _patch_predefined_machines(bc, p_mow, a_mow)
    bc["RandomizeAiInput"] = True  # <-- the whole point of this wrapper

    spawns = _spawn_points_by_twpi(bc)
    player_pts = spawns.get(0) or []
    if len(player_pts) < len(p_units):
        print(f"[error] {len(player_pts)} spawns joueur < {len(p_units)} units", file=sys.stderr)
        return 2
    player_units = [
        {"unitId": p_units[i], "playerId": PLAYER_ID_HUMAN,
         "col": int(player_pts[i][0]), "row": int(player_pts[i][1])}
        for i in range(len(p_units))
    ]
    init = (_rpc(sid, "initAndStart",
                 [{"configJson": json.dumps(bc), "seed": a.seed,
                   "playerUnits": player_units,
                   "keepExisting": a.keep}], timeout=40).get("result") or {})
    rid = init.get("runnerId")
    if rid is None:
        print(f"[error] initAndStart: {init}", file=sys.stderr)
        return 2
    print(f"[build] runnerId={rid} RandomizeAiInput=True")
    print(f"[build] MON roster (team 1)={p_units}")
    print(f"[build] roster ADVERSE (team 2)={a_units}  MoW: moi={p_mow or '-'} IA={a_mow or '-'}")
    res = RD._show_card(sid, rid, bc)
    my_team = next((u.get("team") for u in (res.get("units") or [])
                    if u.get("ctrl")), None)
    RD._save_state({"runnerId": rid, "bc": bc, "seed": a.seed, "myTeam": my_team,
                    "playerUnits": player_units})  # requis par `guard` (clone T1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
