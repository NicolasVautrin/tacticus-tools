#!/usr/bin/env python
"""#254 -- POURQUOI un runner FAUTE (`initAndStart: system error`) apres la migration de build.

Hypothese a verifier ou refuter : le seed BC VERSIONNE (`data/seed-bc.json`, capture sur le build
gqfc5mff6c) porte, dans chaque entree `Units[]`, des IDS NUMERIQUES d'enum
(`ActiveAbilities` = `IdunBattle.Entities.Enum.ActiveAbilityType`,
 `PassiveAbilities` = `IdunBattle.Entities.Enum.TriggeredAbilityType`)
tandis que le second catalogue `BC.Abilities` est keye par NOM. Si l'enum a ete RENUMEROTE par la
mise a jour du jeu, un id du seed BC ne designe plus la meme ability : le moteur le resout en un
NOM different, ce nom est absent de `BC.Abilities`, et
`IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` leve -> « system error ».

Ce probe est PUREMENT OFFLINE : il diffe les deux tables d'enums versionnees et croise le resultat
avec le catalogue capture. ASCII only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYMBOLS = ROOT / "data" / "symbols"
SEED_BC = ROOT / "data" / "seed-bc.json"

OLD = "gqfc5mff6c"
NEW = "rnca9r7q6c"

ENUMS = ("IdunBattle.Entities.Enum.ActiveAbilityType",
         "IdunBattle.Entities.Enum.TriggeredAbilityType")


def enum_map(build: str, enum_name: str) -> dict:
    """{id: nom} d'un enum, lu dans data/symbols/<build>/frida/enums.tsv."""
    p = SYMBOLS / build / "frida" / "enums.tsv"
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.startswith(enum_name + "\t"):
                continue
            out = {}
            for kv in line.rstrip("\n").split("\t", 1)[1].split(","):
                k, v = kv.split("=", 1)
                out[int(k)] = v
            return out
    raise RuntimeError(f"enum {enum_name!r} absent de {p}")


def main(argv) -> int:
    seed = json.loads(SEED_BC.read_text(encoding="utf-8"))
    units = seed.get("Units") or []
    abil = seed.get("Abilities") or {}
    act_names = set(abil.get("ActiveAbilities") or {})
    pas_names = set(abil.get("PassiveAbilities") or {})

    print(f"[seed-bc] {len(units)} entrees Units, "
          f"{len(act_names)} configs actives, {len(pas_names)} configs passives")

    rc = 0
    for enum_name, key, cfg_names in (
            (ENUMS[0], "ActiveAbilities", act_names),
            (ENUMS[1], "PassiveAbilities", pas_names)):
        old = enum_map(OLD, enum_name)
        new = enum_map(NEW, enum_name)
        moved = {i: (old[i], new[i]) for i in sorted(set(old) & set(new))
                 if old[i] != new[i]}
        gone = sorted(set(old) - set(new))
        print(f"\n=== {enum_name}")
        print(f"  {OLD}: {len(old)} membres   {NEW}: {len(new)} membres")
        print(f"  ids RENUMEROTES (meme id, nom different) : {len(moved)}")
        print(f"  ids DISPARUS du nouveau build            : {len(gone)}")
        for i in sorted(moved)[:12]:
            print(f"    {i}: {moved[i][0]} -> {moved[i][1]}")

        # Croisement avec le catalogue : quelle unite du seed BC porte un id dont
        # le NOM a change (donc dont la config sera introuvable dans BC.Abilities) ?
        broken = {}
        for u in units:
            bad = []
            for i in (u.get(key) or []):
                nm_new = new.get(i)
                if nm_new is None:
                    bad.append((i, old.get(i), None))
                elif nm_new not in cfg_names:
                    bad.append((i, old.get(i), nm_new))
            if bad:
                broken[u["Id"]] = bad
        print(f"  unites du catalogue dont un id {key} ne resout plus vers une config "
              f"presente : {len(broken)}")
        for uid in sorted(broken)[:20]:
            print(f"    {uid}: {broken[uid]}")
        if broken:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
