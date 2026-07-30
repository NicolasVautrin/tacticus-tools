"""
diag_summoner_crash.py — Repro deterministe du 'Apply failed: system error'

Hypothese : le crash IL2CPP arrive quand un summoner du roster utilise sa
summon ability mid-battle. Le summon est instancie avec un template
bc.Units[*Smn*] a stats=0 (cas du seed BC), et le moteur AI plante en
faisant un damage_prediction sur ce summon mal initialise.

Strategie de repro : on force un roster compose UNIQUEMENT de summoners
sur les deux equipes. Probabilite que >=1 summoner trigger sa summon
ability dans les premiers turns ≈ 1.

Liste des 7 summoners identifies via cross-ref bc.Units.ActiveAbilities
× ACTIVE_ABILITY_NAMES (ids 1003,1009,1031..,1040,1047,1058,1084,1096,
1145,1172,1200,1201) :
    - ultraInceptorSgt       (DeathFromAbove)
    - orksWarboss            (Waaagh)
    - necroOverlord          (ResurrectionOrb)
    - deathBlightbringer     (Poxwalkers)
    - thousInfernalMaster    (MasterOfTheTutelaries)
    - tyranBiovore           (SporeMineLauncher)
    - orksRukkatrukk         (SquigLaunchas, SquigMine)

Usage:
    python scripts/python/diag_summoner_crash.py             # n=5
    python scripts/python/diag_summoner_crash.py -n 20
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[2]
# #273 : `TRACES_DIR = ROOT / "frida" / "data" / "ai-traces"` vivait ici sans
# AUCUN lecteur -- une entree gitignoree citee mais jamais lue. Retiree : elle
# gonflait l'inventaire des consommateurs sans en etre un. Les vrais lecteurs
# passent par `host_inputs.find("frida/data/ai-traces", ...)`.
ARENA_SEED_BC = ROOT / "data" / "seed-bc.json"

PLAYER_ID_HUMAN = 11
PLAYER_ID_AI = 12

# Active-summoner unitIds (vu plus haut). Les 7 sont des picks safe :
# normalises par buildNormalizedBC + presents dans bc.Units du seed.
SUMMONERS = [
    "ultraInceptorSgt",
    "orksWarboss",
    "necroOverlord",
    "deathBlightbringer",
    "thousInfernalMaster",
    "tyranBiovore",
    "orksRukkatrukk",
]


def _http(path: str, method: str = "GET",
          body: dict | None = None, timeout: float = 10.0) -> dict:
    url = HOST + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"_httpError": e.code, "_body": str(e)}
    except urllib.error.URLError as e:
        return {"_urlError": str(e)}


def _rpc(sid: int, method: str, args: list | None = None,
         timeout: float = 60.0) -> dict:
    body = {"method": method, "args": args or [], "timeout": int(timeout * 1000)}
    return _http(f"/api/scripts/{sid}/rpc", "POST", body, timeout=timeout + 5)


def _resolve_session() -> int:
    st = _http("/api/admin/status")
    sess = st.get("session") or {}
    sid = sess.get("id")
    if not sid or sess.get("status") != "running":
        raise RuntimeError(f"no active session (got {sess})")
    return sid


def _enable_ai_trace(sid: int) -> None:
    for lvl in ["L1", "L2"]:
        _rpc(sid, "aiTraceEnable", [lvl], timeout=5)


def _normalize(sid: int, base_bc: dict, rank: int = 17
               ) -> tuple[dict, list[str]]:
    args = {
        "baseBcJson": json.dumps(base_bc),
        "targetRank": rank, "targetProgressionIndex": rank,
        "targetRarity": 5, "targetLevel": 50,
        "targetStarLevel": 5, "targetAbilityLevel": 50,
    }
    out = _rpc(sid, "buildNormalizedBC", [args], timeout=60).get("result") or {}
    if not out.get("ok"):
        raise RuntimeError(f"normalize failed: {out.get('err')}")
    return json.loads(out["configJson"]), sorted(set(out.get("normalized") or []))


def _spawn_points_by_twpi(bc: dict) -> dict[int, list[tuple[int, int]]]:
    board = bc.get("Board") or {}
    sets = board.get("SpawnPointSets") or []
    if not sets:
        return {}
    idx = bc.get("SpawnPointSetIndex") or 0
    groups = (sets[idx] or {}).get("SpawnPointGroups") or []
    out: dict[int, list[tuple[int, int]]] = {}
    for g in groups:
        twpi = g.get("TeamWithPlayerIndex")
        pts = [(int(p["Column"]), int(p["Row"]))
               for p in (g.get("SpawnPoints") or [])
               if p.get("Column") is not None and p.get("Row") is not None]
        if twpi is not None:
            out[twpi] = pts
    return out


def _patch_predefined(bc: dict, ai_roster: list[str]) -> None:
    bc["PredefinedUnits"] = [{
        "Id": PLAYER_ID_AI,
        "Units": [{"Id": uid, "BattleId": None} for uid in ai_roster],
    }]


def _one_battle(sid: int, idx: int, template_bc: dict, summoner_pool: list[str],
                player_pts: list[tuple[int, int]], max_turns: int,
                rng: random.Random, roster_size: int) -> dict:
    t0 = time.monotonic()
    if len(player_pts) < roster_size:
        return {"i": idx, "ok": False, "phase": "spawn-pts",
                "err": f"only {len(player_pts)} pp", "elapsed": time.monotonic() - t0}

    bc = copy.deepcopy(template_bc)
    # Engine semble silencieusement rejeter PredefinedUnits dupliquees
    # (stage=Finished immediate, units AI invisibles). On contraint a
    # un set unique. Si pool < roster_size, complete avec non-summoners
    # du pool global (= argument summoner_pool injecte plus haut).
    k = min(roster_size, len(summoner_pool))
    roster_p = rng.sample(summoner_pool, k=k)
    roster_a = rng.sample(summoner_pool, k=k)
    _patch_predefined(bc, roster_a)

    # 1. initRunner
    init_resp = _rpc(sid, "initRunner", [{"configJson": json.dumps(bc)}],
                     timeout=30)
    init = init_resp.get("result") or {}
    runner_id = init.get("runnerId")
    if runner_id is None:
        return {"i": idx, "ok": False, "phase": "init",
                "rosterP": roster_p, "rosterA": roster_a,
                "err": init.get("err") or init_resp.get("error")
                       or f"HTTP {init_resp.get('_httpError')}"
                       or "no runnerId",
                "elapsed": time.monotonic() - t0}

    # 2. AddUnit player
    spawn_ok = 0
    for i, u in enumerate(roster_p):
        col, row = player_pts[i]
        au = _rpc(sid, "applyAddUnit",
                  [{"runnerId": runner_id, "unitId": u,
                    "playerId": PLAYER_ID_HUMAN, "col": col, "row": row}],
                  timeout=5).get("result") or {}
        if au.get("ok"):
            spawn_ok += 1

    # 3. startBattle
    sb = _rpc(sid, "startBattle", [{"runnerId": runner_id}],
              timeout=10).get("result") or {}
    if not sb.get("ok"):
        _rpc(sid, "disposeRunner", [{"runnerId": runner_id}], timeout=5)
        return {"i": idx, "ok": False, "phase": "start",
                "rosterP": roster_p, "rosterA": roster_a,
                "spawnP": spawn_ok, "err": sb.get("err"),
                "elapsed": time.monotonic() - t0}

    # 3b. Observe state right after startBattle (diag)
    obs = _rpc(sid, "observeBattle", [{"runnerId": runner_id}],
               timeout=5).get("result") or {}

    # 4. autoPlay
    play = _rpc(sid, "autoPlayRunner",
                [{"runnerId": runner_id, "maxTurns": max_turns}],
                timeout=180).get("result") or {}

    _rpc(sid, "disposeRunner", [{"runnerId": runner_id}], timeout=5)

    return {
        "i": idx, "ok": bool(play.get("ok")),
        "runnerId": runner_id, "rosterP": roster_p, "rosterA": roster_a,
        "spawnP": spawn_ok, "turns": play.get("turns"),
        "reachedFinished": play.get("reachedFinished"),
        "finalStage": play.get("finalStage"),
        "elapsed": time.monotonic() - t0,
        "phase": "play" if not play.get("ok") else None,
        "err": play.get("reason") if not play.get("ok") else None,
        "obsAfterStart": {
            "stage": obs.get("stage"),
            "stageName": obs.get("stageName"),
            "unitCount": len(obs.get("units") or []),
            "byType": obs.get("byType"),
            "teams": sorted({u.get("teamId") for u in (obs.get("units") or [])
                             if u.get("teamId") is not None}),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--max-turns", type=int, default=100)
    ap.add_argument("--roster-size", type=int, default=5)
    args_ns = ap.parse_args()

    sid = _resolve_session()
    print(f"[ok] session id = {sid}")
    _enable_ai_trace(sid)

    base_bc = json.loads(ARENA_SEED_BC.read_text(encoding="utf-8"))
    template, pool = _normalize(sid, base_bc, 17)
    summoners_in_pool = [s for s in SUMMONERS if s in pool]
    print(f"[ok] normalized pool {len(pool)}, summoners present: {summoners_in_pool}")
    if len(summoners_in_pool) < 2:
        print("[error] not enough summoners in pool", file=sys.stderr)
        return 2

    pts = _spawn_points_by_twpi(template)
    player_pts = pts.get(0) or []
    print(f"[ok] player spawn points: {len(player_pts)}")

    seed = args_ns.seed if args_ns.seed is not None else int(time.time())
    rng = random.Random(seed)
    print(f"[ok] seed = {seed}")
    print(f"[ok] launching {args_ns.n} max-summoner battles "
          f"(maxTurns={args_ns.max_turns}, roster={args_ns.roster_size})")
    print("-" * 70)

    results = []
    t0 = time.monotonic()
    for i in range(args_ns.n):
        r = _one_battle(sid, i + 1, template, summoners_in_pool, player_pts,
                        args_ns.max_turns, rng, args_ns.roster_size)
        results.append(r)
        if r["ok"]:
            print(f"  [{i+1:3d}/{args_ns.n}] ok turns={r['turns']:3d} "
                  f"fin={r['reachedFinished']} ({r['elapsed']:.1f}s)")
        else:
            print(f"  [{i+1:3d}/{args_ns.n}] FAIL phase={r['phase']} "
                  f"err={r['err']!r} ({r['elapsed']:.1f}s)")
            print(f"           rosterP={r.get('rosterP')} spawnP={r.get('spawnP')}")
            print(f"           rosterA={r.get('rosterA')}")
            oas = r.get("obsAfterStart") or {}
            print(f"           obsAfterStart: stage={oas.get('stageName')}"
                  f"({oas.get('stage')}) units={oas.get('unitCount')} "
                  f"teams={oas.get('teams')} byType={oas.get('byType')}")

    print("-" * 70)
    n_ok = sum(1 for r in results if r["ok"])
    n_fail_play = sum(1 for r in results if r.get("phase") == "play")
    n_fail_init = sum(1 for r in results if r.get("phase") == "init")
    print(f"= summary =")
    print(f"  ok                  : {n_ok}/{args_ns.n}")
    print(f"  fail in play        : {n_fail_play}")
    print(f"  fail in init        : {n_fail_init}")
    print(f"  elapsed             : {time.monotonic()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
