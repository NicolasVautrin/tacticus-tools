#!/usr/bin/env python
"""#228 -- ventilation des PORTEURS d'`EchoesFromTheWarp` (effet 1284 = `EchoesFromTheWarp_Revive`).

PREALABLE BLOQUANT du cas : etablir QUI porte le passif, et par quel chemin ce porteur arrive en
bataille. La colonne `kind` du gameconfig MENT sur la spawnabilite -> la seule porte valable est le
pool natif (`rl_duel.py --list-pool`, rank courant) pour hero/MoW, plus la fermeture transitive des
summons (un summon compte s'il est amenable via un summoner du pool).

Sortie ASCII pure (console cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import gameconfig as GC

ABILITY = "EchoesFromTheWarp"


def _units_with(passive: str):
    """Toutes les unites du gameconfig (lineup + npc + summons) dont le kit cite `passive`.
    Les trois buckets sont des DICTS keyes par unitId (cf. `gameconfig._index`)."""
    idx = GC._index()
    out = []
    for bucket in ("lineup", "npc", "summons"):
        for uid, u in (idx.get(bucket) or {}).items():
            names = []
            for key in ("passiveAbilities", "activeAbilities", "abilities"):
                v = u.get(key)
                if isinstance(v, list):
                    names += [x for x in v if isinstance(x, str)]
                elif isinstance(v, dict):
                    names += [x for x in v.keys() if isinstance(x, str)]
            hit = [n for n in names if passive in n]
            if hit:
                out.append({"id": uid, "bucket": bucket, "hits": hit,
                            "faction": u.get("faction") or ""})
    return out


def _pool():
    """Pool natif spawnable (`rl_duel.py --list-pool`) -- ids en minuscules pour comparaison."""
    here = Path(__file__).resolve().parent
    p = subprocess.run([sys.executable, str(here / "rl_duel.py"), "--list-pool"],
                       capture_output=True, text=True, cwd=str(here))
    return p.stdout, p.returncode


def main():
    carriers = _units_with(ABILITY)
    print("== porteurs gameconfig de %s ==" % ABILITY)
    for c in carriers:
        print("  %-22s bucket=%-8s faction=%-18s hits=%s" % (c["id"], c["bucket"], c["faction"],
                                                             ",".join(c["hits"])))
    if not carriers:
        print("  (aucun)")
    print()
    out, rc = _pool()
    print("== --list-pool (rc=%d) ==" % rc)
    ids = [c["id"] for c in carriers]
    for line in out.splitlines():
        if any(i and i.lower() in line.lower() for i in ids):
            print("  POOL HIT: %s" % line.strip())
    print("  (pool size lines: %d)" % len(out.splitlines()))


if __name__ == "__main__":
    main()
