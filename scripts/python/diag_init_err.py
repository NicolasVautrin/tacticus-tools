"""diag_init_err.py — capture le body de l'erreur HTTP 500 sur initRunner."""
import json, copy, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
base = json.loads((ROOT / "data" / "arena-battle-config-newtonsoft.json").read_text(encoding="utf-8"))

# Step 1: normalize via RPC
body_norm = {"method": "buildNormalizedBC", "args": [{
    "baseBcJson": json.dumps(base),
    "targetRank": 17, "targetProgressionIndex": 17,
    "targetRarity": 5, "targetLevel": 50,
    "targetStarLevel": 5, "targetAbilityLevel": 50,
}], "timeout": 50000}
req = urllib.request.Request(
    "http://127.0.0.1:8765/api/scripts/6/rpc",
    data=json.dumps(body_norm).encode("utf-8"), method="POST",
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=70) as resp:
    r = json.loads(resp.read().decode("utf-8")).get("result") or {}
norm_json = r.get("configJson") or ""
print(f"[ok] normalized configJson length: {len(norm_json)}")

# Step 2: patch PredefinedUnits = AI seul, then initRunner
bc = json.loads(norm_json)
bc["PredefinedUnits"] = [{
    "Id": 12, "Units": [
        {"UnitId": "ultraTigurius:pvp", "RemainingHealth": None, "MaxHealth": None},
        {"UnitId": "necroPlasmancer:pvp", "RemainingHealth": None, "MaxHealth": None},
    ],
}]
body_init = {"method": "initRunner",
             "args": [{"configJson": json.dumps(bc)}], "timeout": 30000}
req2 = urllib.request.Request(
    "http://127.0.0.1:8765/api/scripts/6/rpc",
    data=json.dumps(body_init).encode("utf-8"), method="POST",
    headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req2, timeout=35) as resp:
        print("OK:", resp.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    print(f"HTTP {e.code} body:\n{body[:2000]}")
