"""probe_181 -- inventaire RE-DERIVE des TARGETING_OPTIONS manquantes.

Croise ABILITY_CLASSES (engine/runner/abilities/handler.py) avec
getattr(cls, "TARGETING_OPTIONS", None) et ventile par module d'origine.
Sortie ASCII stricte (console cp1252).

Usage:
    python probe_181_targeting_gaps.py [--module necrons,orks,votann,genestealer]
"""

from __future__ import annotations

import argparse
import sys

from engine.runner.abilities.handler import ABILITY_CLASSES


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--module",
        default="",
        help="filtre CSV sur le nom court du module (ex. necrons,orks,votann,genestealer)",
    )
    args = ap.parse_args()
    wanted = {m.strip() for m in args.module.split(",") if m.strip()}

    rows = []
    for ability_type, cls in sorted(ABILITY_CLASSES.items()):
        mod = cls.__module__.rsplit(".", 1)[-1]
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        rows.append((ability_type, cls.__name__, mod, opts))

    total = len(rows)
    with_mask = [r for r in rows if r[3] is not None]
    without = [r for r in rows if r[3] is None]

    print("ABILITY_CLASSES        : %d" % total)
    print("avec TARGETING_OPTIONS : %d" % len(with_mask))
    print("MANQUANTES (global)    : %d" % len(without))
    print("")

    by_mod = {}
    for ability_type, name, mod, opts in without:
        by_mod.setdefault(mod, []).append((ability_type, name))
    print("-- manquantes ventilees par module --")
    for mod in sorted(by_mod):
        print("  %-16s %d" % (mod, len(by_mod[mod])))
    print("")

    if wanted:
        print("-- detail perimetre %s --" % ",".join(sorted(wanted)))
        n = 0
        for ability_type, name, mod, opts in without:
            if mod in wanted:
                n += 1
                print("  %-6d %-40s %s" % (ability_type, name, mod))
        print("  total perimetre manquant: %d" % n)
        print("")
        print("-- deja poses dans le perimetre --")
        for ability_type, name, mod, opts in with_mask:
            if mod in wanted:
                print("  %-6d %-40s %s  rules=0x%x" % (ability_type, name, mod, opts.rules))
    return 0


if __name__ == "__main__":
    sys.exit(main())
