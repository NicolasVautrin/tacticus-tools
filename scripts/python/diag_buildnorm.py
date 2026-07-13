"""diag_buildnorm.py — quick probe of buildNormalizedBC over arena seed."""
import json, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
base = (ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8")

body = {
    "method": "buildNormalizedBC",
    "args": [{
        "baseBcJson": base,
        "targetRank": 17, "targetProgressionIndex": 17,
        "targetRarity": 5, "targetLevel": 50,
        "targetStarLevel": 5, "targetAbilityLevel": 50,
    }],
    "timeout": 50000,
}
req = urllib.request.Request(
    "http://127.0.0.1:8765/api/scripts/6/rpc",
    data=json.dumps(body).encode("utf-8"), method="POST",
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=70) as resp:
    raw = resp.read().decode("utf-8")
data = json.loads(raw)
r = data.get("result") or data
print("KEYS:", list(r.keys()))
print("ok:", r.get("ok"))
print("err:", r.get("err"))
norm = r.get("normalized") or []
sk = r.get("skipped") or []
print(f"normalized: {len(norm)}")
print(f"skipped: {len(sk)}")
for s in sk[:8]:
    print(f"  {s}")
cj = r.get("configJson") or ""
print(f"configJson length: {len(cj)}")
if cj:
    parsed = json.loads(cj)
    sample = (parsed.get("Units") or [])[:3]
    for u in sample:
        print(f"  {u.get('Id'):<20} HP={u.get('Health')} dmg={u.get('Damage')} rank={u.get('Rank')} rarity={u.get('Rarity')}")
