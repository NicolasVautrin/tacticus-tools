"""
diag_state_degradation.py — Mesure ce qui se degrade entre 2 battles.

Hypothese : disposeRunner mute le singleton (`_currentBattle.Units`),
provoquant des failures intermittentes a partir de la N-eme battle.

Methodo :
  1. Amorce une fois (-> pool=106)
  2. Loop N fois :
       a) buildNormalizedBC -> pool_size
       b) initRunner(safe roster) -> rid
       c) (optionnel) applyAddUnit+startBattle+autoPlay  (--play)
       d) disposeRunner(rid)
       e) re-buildNormalizedBC -> pool_size
       f) log (iter, pool_before, pool_after)
  3. Identifier l'iter ou pool decroit.

Usage :
    python scripts/python/diag_state_degradation.py -n 30
    python scripts/python/diag_state_degradation.py -n 30 --play
"""

from __future__ import annotations
import argparse, json, urllib.request, copy, time, sys
from pathlib import Path

HOST = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[2]
ARENA = ROOT / "data" / "seed-bc.json"
PLAYER_ID_HUMAN, PLAYER_ID_AI = 11, 12
SAFE_AI = ["ultraTigurius", "bloodDante", "eldarFarseer", "custoTrajann", "thousAhriman"]
SAFE_P  = ["orksWarboss", "templHelbrecht", "tauShadowsun", "necroOverlord", "adeptCanoness"]


def _rpc(sid: int, method: str, args=None, timeout: float = 30):
    body = json.dumps({"method": method, "args": args or [],
                       "timeout": int(timeout*1000)}).encode()
    req = urllib.request.Request(
        f"{HOST}/api/scripts/{sid}/rpc", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=timeout+5).read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=30)
    ap.add_argument("--play", action="store_true",
                    help="aussi addUnit+startBattle+autoPlay (sinon init+dispose seuls)")
    ap.add_argument("--max-turns", type=int, default=20)
    args = ap.parse_args()

    st = json.loads(urllib.request.urlopen(f"{HOST}/api/admin/status",
                                           timeout=5).read())
    sid = (st.get("session") or {}).get("id")
    print(f"[ok] session id={sid}")

    bc = json.loads(ARENA.read_text(encoding="utf-8"))
    norm_args = [{"baseBcJson": json.dumps(bc), "targetRank": 17,
                  "targetProgressionIndex": 17, "targetRarity": 5,
                  "targetLevel": 50, "targetStarLevel": 5,
                  "targetAbilityLevel": 50}]

    # baseline
    out = _rpc(sid, "buildNormalizedBC", norm_args, 60).get("result") or {}
    pool0 = len(out.get("normalized") or [])
    template = json.loads(out["configJson"])
    sets = template["Board"]["SpawnPointSets"]
    idx  = template.get("SpawnPointSetIndex", 0)
    twpi0 = [(p["Column"], p["Row"]) for g in sets[idx]["SpawnPointGroups"]
             if g["TeamWithPlayerIndex"] == 0 for p in g["SpawnPoints"]]
    print(f"[ok] baseline pool={pool0}, player_pts={len(twpi0)}, play={args.play}")
    print(f"     SAFE_AI={SAFE_AI}")
    print("-" * 70)

    first_drop_iter = None
    for i in range(1, args.n + 1):
        t0 = time.monotonic()
        # before
        b_out = (_rpc(sid, "buildNormalizedBC", norm_args, 60).get("result") or {})
        pool_b = len(b_out.get("normalized") or [])

        # init runner with safe roster
        tpl = copy.deepcopy(template)
        tpl["PredefinedUnits"] = [{"Id": PLAYER_ID_AI,
                                   "Units": [{"Id": u, "BattleId": None}
                                             for u in SAFE_AI]}]
        init_rsp = _rpc(sid, "initRunner",
                        [{"configJson": json.dumps(tpl)}], 15)
        init_r = init_rsp.get("result") or {}
        rid = init_r.get("runnerId")
        init_err = init_rsp.get("error") or init_r.get("err")
        if rid is None:
            print(f"[{i:3d}] init FAILED err={init_err!r} pool_before={pool_b}")
            if first_drop_iter is None and pool_b < pool0:
                first_drop_iter = i
            continue

        play_summary = ""
        if args.play:
            for u, (c, r) in zip(SAFE_P, twpi0):
                _rpc(sid, "applyAddUnit",
                     [{"runnerId": rid, "unitId": u,
                       "playerId": PLAYER_ID_HUMAN, "col": c, "row": r}], 5)
            _rpc(sid, "startBattle", [{"runnerId": rid}], 10)
            play = (_rpc(sid, "autoPlayRunner",
                         [{"runnerId": rid, "maxTurns": args.max_turns}],
                         120).get("result") or {})
            play_summary = (f" play ok={play.get('ok')} "
                            f"turns={play.get('turns')}")

        _rpc(sid, "disposeRunner", [{"runnerId": rid}], 5)

        # after
        a_out = (_rpc(sid, "buildNormalizedBC", norm_args, 60).get("result") or {})
        pool_a = len(a_out.get("normalized") or [])

        if pool_a < pool0 and first_drop_iter is None:
            first_drop_iter = i

        marker = ""
        if pool_a < pool_b:  marker = " <DROP>"
        elif pool_a > pool_b: marker = " <UP>"
        print(f"[{i:3d}] pool {pool_b:3d} -> {pool_a:3d}{marker}{play_summary}"
              f" ({(time.monotonic()-t0)*1000:.0f}ms)")

    print("-" * 70)
    print(f"first iter where pool < {pool0}: {first_drop_iter}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
