#!/usr/bin/env python3
"""Garde-fou AVANT migration : une VA est-elle dans du CODE EXECUTABLE ou dans de la PROSE ?

Reecrire une citation dans un commentaire est inoffensif. Reecrire un LITTERAL utilise par
le code (une constante d'image base, une cle de dict `<adresse>: "Nom"`, un `if addr ==
<adresse>:`) le CASSE. Ce probe classe
chaque occurrence en tokenisant reellement le Python (module `tokenize`) :
  - COMMENT / STRING -> prose (migrable) ;
  - NUMBER           -> litteral EXECUTABLE (INTERDIT a la migration).

PERIMETRE -- a lire avant de se fier a un verdict de ce probe : il ne collecte QUE des
`*.py`. Les `.md` / `.ts` ne sont PAS scannes, et une racine qui n'en contient aucun (ex.
`docs`) le faisait autrefois imprimer "fichiers Python scannes : 0" puis "AUCUNE occurrence
dans du code executable : migration sans risque de casse" -- un VERT sur un repertoire
jamais regarde. Mesure #330 : ce faux vert a laisse `docs/` accumuler 4600 VA absolues,
dont 4278 PERIMEES, invisibles de la migration de build #251.
Il DIT desormais ce qu'il n'a pas regarde, et REFUSE de conclure sur une racine muette
(sortie 2). Pour la PROSE (`.md`, `.txt`, `.tsv`), l'outil est
`probe_330_prose_va_and_build_stamps.py`.

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

    # L'exclusion se teste sur le chemin RELATIF au depot, jamais sur l'absolu. Sinon, lance
    # depuis un worktree d'agent (`<repo>/.claude/worktrees/agent-xxx/`), le motif par defaut
    # `.claude/worktrees` matche la racine elle-meme et le probe s'exclut INTEGRALEMENT --
    # zero fichier scanne, verdict vert, sur tout le code. Mesure #330 : c'est ce qui arrivait
    # a tout agent qui le lancait, c.-a-d. au cas nominal.
    excl = args.exclude.replace("\\", "/")

    def is_excluded(f: Path) -> bool:
        try:
            rel = f.relative_to(REPO).as_posix()
        except ValueError:
            rel = f.as_posix()
        return excl in rel

    files = []
    ignored = Counter()          # extension -> nb de fichiers NON scannes (angle mort)
    mutes = []                   # racines qui n'ont rendu aucun .py
    for root in args.roots:
        p = REPO / root
        before = len(files)
        if p.is_file():
            if p.suffix == ".py":
                files.append(p)
            else:
                ignored[p.suffix or "<sans extension>"] += 1
        elif p.is_dir():
            for f in p.rglob("*"):
                if not f.is_file() or is_excluded(f):
                    continue
                if f.suffix == ".py":
                    files.append(f)
                else:
                    ignored[f.suffix or "<sans extension>"] += 1
        if len(files) == before:
            mutes.append(root)

    cats = Counter()
    danger = []
    for f in files:
        c, d = classify_python(f)
        cats.update(c)
        danger += d

    print("fichiers Python scannes : %d" % len(files))
    if ignored:
        # DIRE l'angle mort. Un probe qui tait ce qu'il n'a pas regarde se lit comme
        # "rien a signaler" -- c'est exactement ainsi que le gisement `docs/` est passe.
        print("fichiers NON scannes (ce probe ne classe que du Python) : %d"
              % sum(ignored.values()))
        for ext, n in ignored.most_common(8):
            print("    %-16s %d" % (ext, n))
        print("    -> pour la PROSE : probe_330_prose_va_and_build_stamps.py")
    print("")
    if mutes:
        print("REFUS DE CONCLURE : aucune racine Python dans %s." % ", ".join(mutes))
        print("Ce probe ne sait rien dire de ces racines -- ne pas lire son silence comme un vert.")
        print("Pour la prose : python scripts/python/probe_330_prose_va_and_build_stamps.py %s"
              % " ".join(mutes))
        return 2
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
