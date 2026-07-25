#!/usr/bin/env python3
"""Reconnaissance AVANT migration VA -> symbole : forme des citations + taux de resolution.

Ne REECRIT RIEN. Mesure, sur un perimetre donne :
  - la forme syntaxique reelle des citations (`@180...`, `0x180...`, `(0x180...)`, ...) ;
  - si la VA tombe sur un DEBUT de fonction ou a l'INTERIEUR (offset) ;
  - si le symbole resolu est un VRAI nom ou un placeholder Ghidra `FUN_<addr>`
    (auquel cas migrer n'apporte RIEN : le "symbole" n'est que l'adresse deguisee) ;
  - si le nom du symbole est DEJA present dans la ligne (citation `Nom @VA` -> la
    reecriture naive produirait `Nom Namespace.Type$$Nom`, une redondance).

Sortie ASCII pure (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import bisect
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SYMBOLS_DIR = REPO / "data" / "symbols"

# 9 chiffres hex = plage VA du binaire (0x180000000 .. 0x18fffffff).
VA_RE = re.compile(r"(?<![0-9a-fA-Fx])(?:0x|@)(18[0-9a-fA-F]{7})(?![0-9a-fA-F])")


def load_table(build: str):
    """-> (addrs triees, noms alignes). Table = data/symbols/<build>/functions.tsv."""
    path = SYMBOLS_DIR / build / "functions.tsv"
    if not path.exists():
        raise SystemExit("table absente : %s (lancer ghidra_symbols.py dump)" % path)
    pairs = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            addr, _, name = line.rstrip("\n").partition("\t")
            if name:
                pairs.append((int(addr, 16), name))
    pairs.sort()
    return [a for a, _ in pairs], [n for _, n in pairs]


def resolve(addrs, names, va: int):
    """-> (nom, offset) du symbole englobant, ou (None, None) si avant le 1er symbole."""
    i = bisect.bisect_right(addrs, va) - 1
    if i < 0:
        return None, None
    return names[i], va - addrs[i]


def base_name(sym: str) -> str:
    """`Namespace.Type$$Methode` -> `Methode` (dernier segment apres $$ puis apres .)."""
    tail = sym.split("$$")[-1] if "$$" in sym else sym.split(".")[-1]
    return tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="gqfc5mff6c")
    ap.add_argument("roots", nargs="+", help="fichiers/dossiers a scanner")
    ap.add_argument("--ext", default=".py,.md,.ts")
    args = ap.parse_args()

    addrs, names = load_table(args.build)
    print("table %s : %d symboles" % (args.build, len(addrs)))

    exts = tuple(args.ext.split(","))
    files = []
    for root in args.roots:
        p = REPO / root
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += [f for f in p.rglob("*") if f.is_file() and f.suffix in exts]

    shapes = Counter()
    total = 0
    distinct = set()
    unresolved = set()
    fun_placeholder = set()
    at_start = set()
    interior = set()
    name_already_there = 0
    interior_offsets = Counter()

    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line in text.splitlines():
            for m in VA_RE.finditer(line):
                total += 1
                va = int(m.group(1), 16)
                distinct.add(va)
                shapes[m.group(0)[: -len(m.group(1))]] += 1
                sym, off = resolve(addrs, names, va)
                if sym is None:
                    unresolved.add(va)
                    continue
                if sym.startswith("FUN_"):
                    fun_placeholder.add(va)
                    continue
                if off == 0:
                    at_start.add(va)
                else:
                    interior.add(va)
                    interior_offsets[off if off < 0x1000 else "  >=0x1000"] += 1
                if base_name(sym).lower() in line.lower():
                    name_already_there += 1

    print("")
    print("fichiers scannes      : %d" % len(files))
    print("occurrences totales   : %d" % total)
    print("VA distinctes         : %d" % len(distinct))
    print("")
    print("--- forme syntaxique du prefixe ---")
    for shape, n in shapes.most_common():
        print("  %-4r %d" % (shape, n))
    print("")
    print("--- resolution (sur VA distinctes) ---")
    print("  debut de fonction, nom REEL : %d" % len(at_start))
    print("  interieur, nom REEL         : %d" % len(interior))
    print("  placeholder FUN_<addr>      : %d   <- migrer n'apporte RIEN" % len(fun_placeholder))
    print("  avant le 1er symbole        : %d" % len(unresolved))
    print("")
    print("--- occurrences dont la ligne CONTIENT DEJA le nom de la methode ---")
    print("  %d / %d  (%.0f%%) -> reecriture naive = redondance" % (
        name_already_there, total, 100.0 * name_already_there / max(total, 1)))
    print("")
    print("--- offsets internes (top 12) ---")
    for off, n in interior_offsets.most_common(12):
        label = off if isinstance(off, str) else "  +0x%x" % off
        print("  %-10s %d" % (label, n))

    if fun_placeholder:
        print("")
        print("--- echantillon FUN_ (10) ---")
        for va in sorted(fun_placeholder)[:10]:
            print("  @%x" % va)
    return 0


if __name__ == "__main__":
    sys.exit(main())
