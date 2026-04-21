"""Extract `TIMEOUT/NULL` markers from decompiled_tacticus/*.c into a TSV suitable
for a second Ghidra pass (same format as all_battlelogic_targets.tsv):
  top_class_fs_path \t method_full_name \t rva_hex
"""
import os, re, sys

ROOT = 'C:/Users/nicolasv/tacticus-tools/data/decompiled_tacticus/'
OUT  = 'C:/Users/nicolasv/tacticus-tools/data/failed_targets.tsv'

pairs = {}
pattern = re.compile(r'// === (.+?) \(RVA: (0x[0-9A-Fa-f]+)\) === TIMEOUT/NULL')

for root, dirs, files in os.walk(ROOT):
    for f in files:
        if not f.endswith('.c'):
            continue
        full = os.path.join(root, f).replace(os.sep, '/')
        with open(full, 'r', encoding='utf-8', errors='replace') as fp:
            text = fp.read()
        rel = full.replace(ROOT, '').removesuffix('.c')
        for m in pattern.finditer(text):
            rva = int(m.group(2), 16)
            pairs[rva] = (m.group(1), rel)

with open(OUT, 'w', encoding='utf-8') as f:
    for rva, (name, path) in sorted(pairs.items()):
        f.write(f'{path}\t{name}\t{rva:x}\n')

print(f'Wrote {len(pairs)} failed targets to {OUT}')
for rva, (name, path) in list(sorted(pairs.items()))[:5]:
    print(f'  {path}  {name}  0x{rva:x}')
