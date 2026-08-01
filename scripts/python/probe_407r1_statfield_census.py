#!/usr/bin/env python
"""probe #407-r1 (voie 2) -- recensement NUMERIQUE des champs `StatType` du gameconfig.

Pourquoi ce second balayage : le premier (`probe_407r1_evasion_carriers.py`) cherche le
VOCABULAIRE ("evasion"/"evade"/...). Or un effet qui modifie une stat ne la nomme pas : il
porte l'INDEX de l'enum `StatType` (`EVASION_CHANCE = 15`). Un balayage textuel est donc
structurellement aveugle a la seule voie qui pourrait allumer le composant
`IdunBattle.Entities.Components.EvasionChanceComponent` -- exactement le faux negatif de
#323. Ici on recense les champs qui PORTENT un StatType, on liste les valeurs vues, et on
dit si 15 y figure.

Aucun runner, aucun RPC. Sortie ASCII.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import gameconfig as gc  # noqa: E402

sys.path.insert(0, str(_HERE))
from engine.entities.stats import StatType  # noqa: E402

EVASION_STAT = int(StatType.EVASION_CHANCE)

# Un champ « porte un StatType » si son NOM contient stat/attribute et sa valeur est un int
# ou le NOM d'un membre de l'enum.
_RX_STATFIELD = re.compile(r"stat(type)?$|^stat|statto|targetstat|affectedstat", re.I)
_NAMES = {m.name.replace("_", "").lower(): int(m) for m in StatType}
_NAMES_PASCAL = {m.name: int(m) for m in StatType}


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            if isinstance(v, (dict, list)):
                yield from _walk(v, p)
            else:
                yield p, str(k), v
    elif isinstance(node, list):
        for i, v in enumerate(node):
            p = f"{path}[{i}]"
            if isinstance(v, (dict, list)):
                yield from _walk(v, p)
            else:
                yield p, "", v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    idx = gc._index()
    # 1) champs dont le NOM ressemble a un porteur de StatType
    by_field = defaultdict(Counter)
    evasion_sites = []
    # 2) toute valeur STRING egale a un nom de membre de l'enum (forme PascalCase du jeu)
    name_hits = Counter()
    name_evasion_sites = []

    scopes = {"abilities": idx["abilities"], "lineup": idx["lineup"],
              "npc": idx["npc"], "summons": idx["summons"]}
    for scope, blob in scopes.items():
        for oid, obj in (blob or {}).items():
            for path, key, val in _walk(obj):
                kl = key.lower()
                if _RX_STATFIELD.search(kl):
                    by_field[key][repr(val)] += 1
                    if val == EVASION_STAT or (isinstance(val, str)
                                               and val.lower().replace("_", "")
                                               in ("evasionchance",)):
                        evasion_sites.append((scope, oid, path, val))
                if isinstance(val, str) and val in _NAMES_PASCAL:
                    name_hits[val] += 1
                    if _NAMES_PASCAL[val] == EVASION_STAT:
                        name_evasion_sites.append((scope, oid, path, val))

    if args.json:
        print(json.dumps({"evasion_sites": evasion_sites,
                          "name_evasion_sites": name_evasion_sites,
                          "fields": {k: dict(v) for k, v in by_field.items()},
                          "enum_name_values": dict(name_hits)}, default=str)[:20000])
        return 0

    print("=== #407-r1 : champs StatType du gameconfig (cible : %d = EVASION_CHANCE) ==="
          % EVASION_STAT)
    print()
    print("-- champs dont le NOM porte un StatType --")
    if not by_field:
        print("   AUCUN champ de ce nom dans abilities/lineup/npc/summons")
    for field, vals in sorted(by_field.items()):
        tot = sum(vals.values())
        top = ", ".join("%s x%d" % (v, n) for v, n in vals.most_common(30))
        print("   %-28s (%d occurrences) : %s" % (field, tot, top))
    print()
    print("-- valeurs STRING egales a un membre de l'enum StatType --")
    if not name_hits:
        print("   aucune")
    for v, n in name_hits.most_common(40):
        print("   %-46s x%d  (=%d)" % (v, n, _NAMES_PASCAL[v]))
    print()
    print("-- sites EVASION (index 15 ou nom EvasionChance) --")
    for s in evasion_sites + name_evasion_sites:
        print("   %s" % (s,))
    if not (evasion_sites or name_evasion_sites):
        print("   AUCUN")
    print()
    print("VERDICT : StatType 15 %s parmi les StatTypes references par le gameconfig"
          % ("PRESENT" if (evasion_sites or name_evasion_sites) else "ABSENT"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
