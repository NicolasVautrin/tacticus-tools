"""Liste detaillee de TOUTES les manquantes TARGETING_OPTIONS, par module. ASCII only."""

from __future__ import annotations

import sys

from engine.runner.abilities.handler import ABILITY_CLASSES


def main() -> int:
    by_mod = {}
    for ability_type, cls in sorted(ABILITY_CLASSES.items()):
        if getattr(cls, "TARGETING_OPTIONS", None) is not None:
            continue
        mod = cls.__module__.rsplit(".", 1)[-1]
        by_mod.setdefault(mod, []).append((ability_type, cls.__name__))
    for mod in sorted(by_mod):
        print("[%s]" % mod)
        for ability_type, name in by_mod[mod]:
            print("   %-6d %s" % (ability_type, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
