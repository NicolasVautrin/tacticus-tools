"""Probe #341 -- traque la signature « deux rebases ont chacun ajoute leur ligne sans retirer
l'autre » dans un document markdown : une CLE de tableau (1re cellule) qui apparait DEUX fois
dans le meme tableau.

C'est la faute qui a produit les deux comptes divergents de `port-residuals-inventory.md` §4.g
(la ligne §4.b figurait deux fois, a 11 puis a 15 -- corrige par `5176603d`). Le probe verifie
qu'elle n'a pas frappe ailleurs, et il additionne au passage les colonnes numeriques d'un tableau
qui porte une ligne « Total » pour dire si le total tombe juste.

Usage : depuis `scripts/python/`
  python probe_341_dup_table_rows.py [chemin.md ...]      (defaut : port-residuals-inventory.md)
"""
from __future__ import annotations

import os
import re
import sys

_PYROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PYROOT))

DEFAULT = [os.path.join(_REPO, "docs", "rl", "port-residuals-inventory.md")]

_SEP = re.compile(r"^\|[\s:\-|]+\|$")
_BOLD = re.compile(r"[*`~]")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _key(cell: str) -> str:
    """Cle normalisee : on retire le gras/code/barre et on coupe au tiret cadratin ou au ' -- '."""
    s = _BOLD.sub("", cell).strip()
    for sep in ("\u2014", " - ", " -- "):
        if sep in s:
            s = s.split(sep)[0]
    return s.strip().lower()


def _num(cell: str):
    m = re.search(r"\d+", _BOLD.sub("", cell))
    return int(m.group()) if m else None


def scan(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    problems = 0
    i = 0
    while i < len(lines):
        if not lines[i].startswith("|") or i + 1 >= len(lines) or not _SEP.match(lines[i + 1]):
            i += 1
            continue
        start = i
        i += 2
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            rows.append((i + 1, _cells(lines[i])))
            i += 1
        if len(rows) < 2:
            continue

        seen: dict[str, int] = {}
        total_row = None
        parts = []
        for lineno, cs in rows:
            k = _key(cs[0])
            if k.startswith("total"):
                total_row = (lineno, cs)
                # Une ligne posterieure au Total est HORS compte par construction (c'est ainsi que
                # §4.g range `§4.d — veille` et `§4.f — NON CONFRONTABLES`) : on arrete de sommer.
                continue
            # Cle vide ou purement typographique : c'est un PLACEHOLDER de numerotation, pas une
            # cle (§2.1 numerote `—` ses deux entrees NON PERTINENTES). Deux `—` ne sont pas un
            # doublon.
            if not k or not re.search(r"[0-9a-z]", k):
                continue
            if k in seen:
                print("  DUP    l.%-5d cle '%s' deja vue l.%d (tableau l.%d)"
                      % (lineno, cs[0][:60], seen[k], start + 1))
                problems += 1
            else:
                seen[k] = lineno
            n = _num(cs[1]) if len(cs) > 1 else None
            if n is not None and total_row is None:
                parts.append((k, n))

        if total_row is not None and parts:
            lineno, cs = total_row
            declared = _num(cs[1]) if len(cs) > 1 else None
            somme = sum(n for _, n in parts)
            ok = declared == somme
            print("  TOTAL  l.%-5d declare=%s  somme des lignes=%d  -> %s"
                  % (lineno, declared, somme, "OK" if ok else "INCOHERENT"))
            if not ok:
                print("         detail : %s" % ", ".join("%s=%d" % p for p in parts))
                problems += 1
    return problems


def main():
    paths = sys.argv[1:] or DEFAULT
    total = 0
    for p in paths:
        print("== %s" % os.path.relpath(p, _REPO).replace("\\", "/"))
        total += scan(p)
    print()
    print("problemes: %d" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
