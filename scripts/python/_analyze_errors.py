"""Categorise gradle build errors.

Chemin RELATIF au checkout (#314) : en absolu, ce script lisait le
`build-errors.log` de l'ARBRE PRINCIPAL depuis un worktree d'agent -- donc le
build de QUELQU'UN D'AUTRE, sans que rien ne le signale. Le log est ecrit par
`_capture_build.py`, qui le pose desormais sous `logs/`.
"""
import sys
from collections import Counter
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "logs" / "build-errors.log"
if not LOG.exists():
    raise SystemExit("[analyze] introuvable : %s\n"
                     "  produire le log d'abord : python _capture_build.py"
                     % LOG.as_posix())
txt = LOG.read_text()
errs = []
lines = txt.splitlines()
i = 0
while i < len(lines):
    l = lines[i]
    if ": error:" in l:
        msg_parts = [l.split(": error:")[1].strip()]
        j = i + 1
        while j < len(lines) and (lines[j].startswith("  ") or lines[j].startswith("\t")) and ": error:" not in lines[j]:
            msg_parts.append(lines[j].strip())
            j += 1
        errs.append(" | ".join(msg_parts[:3]))
        i = j
    else:
        i += 1
c = Counter(errs)
for msg, n in c.most_common(50):
    print(f"{n:4d}  {msg[:180]}")
