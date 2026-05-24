"""
diag_normalize.py — Diagnostic standalone : verifie que les units du
runner apres init JSON-only ont bien les stats R17 Mythic normalisees,
et que le board injecte correspond bien a celui du JSON template.

Pipeline :
  1. Charge arena BC seed
  2. buildNormalizedBC (R17 Mythic) -> JSON normalise
  3. Lit Units[<5 sample>] cote JSON : HP, damage, armor, rank
  4. Patch PredefinedUnits avec un roster connu
  5. initRunner + startBattle
  6. observeBattle -> compare HP/damage/armor de chaque unit spawnee
     contre les valeurs attendues lues etape 3
  7. disposeRunner
"""

from __future__ import annotations

import copy
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[2]
ARENA_SEED_BC = ROOT / "data" / "arena-battle-config-newtonsoft.json"

SAMPLE_ROSTER = [
    "ultraTigurius", "necroPlasmancer", "adeptRetributor",
    "deathBlightlord", "necroDestroyer",
]
PLAYER_ID_HUMAN = 11
PLAYER_ID_AI = 12


def _http(path, method="GET", body=None, timeout=30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        HOST + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _rpc(sid, method, args=None, timeout=60):
    return _http(f"/api/scripts/{sid}/rpc", "POST",
                 {"method": method, "args": args or [],
                  "timeout": int(timeout * 1000)}, timeout=timeout + 5)


def main():
    sid = (_http("/api/admin/status").get("session") or {}).get("id")
    if not isinstance(sid, int):
        print("no session"); return 2
    print(f"[ok] sid={sid}")

    seed_bc = json.loads(ARENA_SEED_BC.read_text(encoding="utf-8"))
    print(f"[ok] seed BC loaded ({len(seed_bc.get('Units') or [])} unit templates)")

    # Step 2 : buildNormalizedBC offline
    norm = _rpc(sid, "buildNormalizedBC", [{
        "baseBcJson": json.dumps(seed_bc),
        "targetRank": 17, "targetProgressionIndex": 17,
        "targetRarity": 5, "targetLevel": 50,
        "targetStarLevel": 5, "targetAbilityLevel": 50,
    }], timeout=60).get("result") or {}
    if not norm.get("ok"):
        print(f"[fail] buildNormalizedBC: {norm.get('err')}"); return 1
    template = json.loads(norm["configJson"])
    print(f"[ok] normalized BC ({norm.get('normalized') and len(norm['normalized'])} units)")

    # Step 3 : capture les stats attendues pour le SAMPLE_ROSTER
    expected = {}
    for u in template.get("Units") or []:
        if u.get("Id") in SAMPLE_ROSTER:
            expected[u["Id"]] = {
                "Health": u.get("Health"),
                "Damage": u.get("Damage"),
                "Armor": u.get("Armor"),
                "Rank": u.get("Rank"),
                "Rarity": u.get("Rarity"),
                "Level": u.get("Level"),
            }
    print(f"[ok] expected stats (post-normalize) for sample roster :")
    for uid, st in expected.items():
        print(f"  {uid:<20} HP={st['Health']:>5} dmg={st['Damage']:>5} "
              f"arm={st['Armor']:>4} rank={st['Rank']} rarity={st['Rarity']} "
              f"lvl={st['Level']}")

    # Step 4 : patch PredefinedUnits = AI uniquement (pattern PvP)
    bc = copy.deepcopy(template)
    bc["PredefinedUnits"] = [
        {"Id": PLAYER_ID_AI, "Units":
            [{"UnitId": f"{u}:pvp", "RemainingHealth": None, "MaxHealth": None}
             for u in SAMPLE_ROSTER]},
    ]

    # Step 5 : init + AddUnit player + start
    init = _rpc(sid, "initRunner",
                [{"configJson": json.dumps(bc)}], timeout=30).get("result") or {}
    runner_id = init.get("runnerId")
    if runner_id is None:
        print(f"[fail] initRunner: {init.get('err')}"); return 1
    print(f"[ok] runnerId={runner_id} seed={init.get('seed')}")

    # Player units via AddUnit (cols 0..4, row 0 = TWPI=0 area)
    for i, u in enumerate(SAMPLE_ROSTER):
        au = _rpc(sid, "applyAddUnit",
                  [{"runnerId": runner_id, "unitId": f"{u}:pvp",
                    "playerId": PLAYER_ID_HUMAN, "col": i, "row": 0}],
                  timeout=10).get("result") or {}
        if not au.get("ok"):
            print(f"[warn] AddUnit {u}: {au.get('err')}")

    start = _rpc(sid, "startBattle",
                 [{"runnerId": runner_id}], timeout=10).get("result") or {}
    print(f"[ok] startBattle: {start}")

    # Step 6 : observeBattle
    obs = _rpc(sid, "observeBattle",
               [{"runnerId": runner_id}], timeout=10).get("result") or {}
    print(f"[ok] observeBattle stage={obs.get('stage')}({obs.get('stageName')}) "
          f"units={obs.get('counts', {}).get('units')} board info:")
    print(f"     matchState={obs.get('matchState')}")

    # Step 7 : compare each spawned unit's stats vs expected
    print()
    print("== compare units spawnees vs expected (R17 Mythic) ==")
    ok_total = 0
    fail_total = 0
    for u in obs.get("units") or []:
        vid = u.get("visualId")
        exp = expected.get(vid)
        if not exp:
            print(f"  [?] {vid:<20} entityId={u.get('entityId')} not in expected")
            continue
        hp_max = u.get("hpMax")
        dmg = u.get("damage")
        arm = u.get("armor")
        hp_ok = hp_max == exp["Health"]
        dmg_ok = dmg == exp["Damage"]
        arm_ok = arm == exp["Armor"]
        all_ok = hp_ok and dmg_ok and arm_ok
        flag = "✓" if all_ok else "✗"
        print(f"  [{flag}] {vid:<20} eid={u.get('entityId'):<3} "
              f"pid={u.get('playerId')} "
              f"HP={hp_max}/{exp['Health']} "
              f"dmg={dmg}/{exp['Damage']} "
              f"arm={arm}/{exp['Armor']} "
              f"pos=({u.get('col')},{u.get('row')})")
        if all_ok: ok_total += 1
        else: fail_total += 1
    print()
    print(f"== resume == ok={ok_total} fail={fail_total}")

    # Step 8 : board verification
    print()
    print("== board (cote JSON template) ==")
    board = template.get("Board") or {}
    print(f"  Id={board.get('Id')} Width={board.get('Width')} "
          f"Height={board.get('Height')}")
    sps_list = board.get("SpawnPointSets") or []
    print(f"  SpawnPointSets={len(sps_list)}")
    if sps_list:
        groups = sps_list[0].get("SpawnPointGroups") or []
        print(f"  group[0].TWPI count: {[(g.get('TeamWithPlayerIndex'), len(g.get('SpawnPoints') or [])) for g in groups]}")

    # Cleanup
    _rpc(sid, "disposeRunner", [{"runnerId": runner_id}], timeout=5)
    print()
    print("== done ==")
    return 0 if fail_total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
