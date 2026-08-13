"""Recon des abilities MYTHIQUES : porteurs, ids, configs de seed.

Sortie ASCII only. Lecture seule.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gameconfig  # noqa: E402

PORTEURS = [
    "necroReanimator",
    "thousDaemonPrince",
    "tyranBiovore",
    "deathCrawler",
    "blackForgefiend",
    "darkaStormSpeeder",
]


def main() -> int:
    gc = gameconfig._cfg()
    units = gc.get("units", {})
    print("=== ETAGE 1 : mythicAbilities par porteur (toutes les voies units.<kind>) ===")
    trouve = {}
    for kind, entries in units.items():
        if not isinstance(entries, dict):
            continue
        for uid, u in entries.items():
            if not isinstance(u, dict):
                continue
            ma = u.get("mythicAbilities")
            if ma:
                trouve[uid] = (kind, ma, u.get("tertiaryAbilities"), u.get("relicAbilities"))
    print("unites AVEC mythicAbilities : %d" % len(trouve))
    for uid, (kind, ma, ta, ra) in sorted(trouve.items()):
        mark = " <== CIBLE" if uid in PORTEURS else ""
        print("  %-22s kind=%-10s mythic=%s tertiary=%s relic=%s%s"
              % (uid, kind, ma, ta, ra, mark))

    print()
    print("=== ETAGE 2 : les 6 porteurs -- champs bruts pertinents ===")
    for uid in PORTEURS:
        found = None
        for kind, entries in units.items():
            if isinstance(entries, dict) and uid in entries:
                found = (kind, entries[uid])
                break
        if not found:
            print("  %-22s ABSENT du gameconfig" % uid)
            continue
        kind, u = found
        keys = sorted(k for k in u.keys() if "abilit" in k.lower() or "mythic" in k.lower()
                      or k in ("unitType", "alliance", "grandAlliance", "faction"))
        print("  %-22s kind=%s" % (uid, kind))
        for k in keys:
            print("      %-26s = %s" % (k, json.dumps(u[k])[:200]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
