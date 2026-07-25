#!/usr/bin/env python3
"""Garde-fou AVANT migration : une VA est-elle dans du CODE EXECUTABLE ou dans de la PROSE ?

Reecrire une citation dans un commentaire est inoffensif. Reecrire un LITTERAL utilise par
le code (une constante d'image base, une cle de dict `<adresse>: "Nom"`, un `if addr ==
<adresse>:`) le CASSE. Ce probe classe
chaque occurrence en tokenisant reellement le Python (module `tokenize`) :
  - COMMENT / STRING -> prose (migrable) ;
  - NUMBER           -> litteral EXECUTABLE (INTERDIT a la migration).

Pour les fichiers non-Python (.md, .ts) tout est traite comme prose, sauf signalement.
Sortie ASCII pure.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import token as T
import tokenize
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VA_RE = re.compile(r"(?<![0-9a-fA-Fx])(?:0x|@)(18[0-9a-fA-F]{7})(?![0-9a-fA-F])")


def classify_python(path: Path):
    """-> Counter par categorie + liste des occurrences EXECUTABLES (path, ligne, texte)."""
    cats = Counter()
    danger = []
    try:
        src = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return cats, danger
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        cats["ERREUR DE TOKENISATION"] += 1
        danger.append((path, 0, "tokenisation impossible : %s" % exc))
        return cats, danger

    lines = src.splitlines()
    for tk in toks:
        if not VA_RE.search(tk.string):
            continue
        n = len(VA_RE.findall(tk.string))
        if tk.type == T.COMMENT:
            cats["commentaire"] += n
        elif tk.type == T.STRING:
            cats["chaine / docstring"] += n
        elif tk.type == T.NUMBER:
            cats["LITTERAL EXECUTABLE"] += n
            row = tk.start[0]
            danger.append((path, row, lines[row - 1].strip() if row <= len(lines) else ""))
        else:
            cats["autre token (%s)" % tokenize.tok_name.get(tk.type, "?")] += n
            row = tk.start[0]
            danger.append((path, row, lines[row - 1].strip() if row <= len(lines) else ""))
    return cats, danger


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--exclude", default=".claude\\worktrees")
    args = ap.parse_args()

    files = []
    for root in args.roots:
        p = REPO / root
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += [f for f in p.rglob("*.py") if f.is_file()]
    files = [f for f in files if args.exclude not in str(f)]

    cats = Counter()
    danger = []
    for f in files:
        c, d = classify_python(f)
        cats.update(c)
        danger += d

    print("fichiers Python scannes : %d" % len(files))
    print("")
    for cat, n in sorted(cats.items(), key=lambda kv: -kv[1]):
        print("  %-28s %d" % (cat, n))
    print("")
    if danger:
        print("--- OCCURRENCES A NE PAS TOUCHER (%d) ---" % len(danger))
        for path, row, text in danger:
            print("  %s:%d" % (path.relative_to(REPO), row))
            print("      %s" % text[:130])
    else:
        print("AUCUNE occurrence dans du code executable : migration sans risque de casse.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
