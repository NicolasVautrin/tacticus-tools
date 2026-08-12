"""#967 -- recensement AU BLOC D'ADRESSES des classes playbook de la tranche.

Le grep par NOM rate ce que l'ICF fond : un corps trivial partage par N classes n'a qu'UN
proprietaire dans `ghidra/functions.tsv` (indexe par adresse, sans doublon). Le seul recensement
qui montre la frontiere reelle est celui du BLOC CONTIGU : on trie par adresse et on imprime tout
ce qui siege entre la 1re et la derniere methode nommee de la classe, voisins compris.

Usage :
    python probe_967_playbook_blocks.py <MotifClasse> [<MotifClasse> ...]
    python probe_967_playbook_blocks.py --plage <va_lo> <va_hi>
"""
from __future__ import annotations

import sys
from pathlib import Path

BUILD = "rnca9r7q6c"


def _tsv() -> Path:
    here = Path(__file__).resolve()
    root = here.parents[2]
    return root / "data" / "symbols" / BUILD / "ghidra" / "functions.tsv"


def charger() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    with open(_tsv(), "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                rows.append((int(parts[0], 16), parts[1]))
            except ValueError:
                continue
    rows.sort(key=lambda r: r[0])
    return rows


def bloc(rows, lo: int, hi: int, marge: int = 0):
    for va, sym in rows:
        if lo - marge <= va <= hi + marge:
            yield va, sym


def main(argv: list[str]) -> int:
    rows = charger()
    print("total fonctions = %d" % len(rows))
    if argv and argv[0] == "--plage":
        lo, hi = int(argv[1], 16), int(argv[2], 16)
        for va, sym in bloc(rows, lo, hi):
            print("  %012x  %s" % (va, sym))
        return 0
    for motif in argv:
        hits = [(va, sym) for va, sym in rows if motif in sym]
        if not hits:
            print("\n=== %s : AUCUN symbole nomme ===" % motif)
            continue
        lo, hi = hits[0][0], hits[-1][0]
        print("\n=== %s : %d symboles nommes, bloc %012x..%012x ==="
              % (motif, len(hits), lo, hi))
        propres = {va for va, _ in hits}
        for va, sym in bloc(rows, lo, hi):
            marque = "   " if va in propres else ">>>"
            print("  %s %012x  %s" % (marque, va, sym))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
