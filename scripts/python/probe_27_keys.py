"""probe #27 -- liste les cles de poids `Utilities.*.ActiveAbilities` de la seed BC
qui matchent un motif (recherche de la cle exacte d'un terme custom)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    pat = sys.argv[1] if len(sys.argv) > 1 else ""
    raw = (REPO / "data" / "seed-bc.json").read_text(encoding="utf-8")
    keys = sorted(set(re.findall(r'"([A-Za-z0-9_]+)"\s*:', raw)))
    rx = re.compile(pat, re.I)
    for k in keys:
        if rx.search(k):
            print(k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
