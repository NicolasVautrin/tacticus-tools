"""Categorise gradle build errors."""
from collections import Counter
from pathlib import Path

txt = Path(r"C:\Users\nicolasv\tacticus-tools\build-errors.log").read_text()
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
