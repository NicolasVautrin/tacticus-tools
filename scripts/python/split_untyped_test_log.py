"""Parse the GhidraTestUntypedDecompile.java stdout log and write each recovered
method's C into data/decompiled_tacticus_untyped_test/<top_class_fs_path>.c,
mirroring the arborescence of data/decompiled_tacticus/.
"""
import re, os, sys
from pathlib import Path

LOG = Path('C:/Users/nicolasv/tacticus-tools/data/untyped-test.log')
TSV = Path('C:/Users/nicolasv/tacticus-tools/data/failed_targets.tsv')
OUT = Path('C:/Users/nicolasv/tacticus-tools/data/decompiled_tacticus_untyped_test')

# rva_int -> top_class_fs_path
rva_to_path = {}
for line in TSV.read_text(encoding='utf-8').splitlines():
    parts = line.split('\t')
    if len(parts) >= 3:
        try:
            rva_to_path[int(parts[2], 16)] = parts[0]
        except ValueError:
            pass

text = LOG.read_text(encoding='utf-8', errors='replace')

# Sections look like:
#   ---- 0x2B4EC7C: IdunBattle.DSL.AbilityBehaviour.op_BitwiseAnd (39389ms, 5011 lines) ----
#   <C body>
#   ---- 0x...: ... ----
# Strip Ghidra wrapper prefixes like "INFO  ... (GhidraScript)" that appear on every line.
sections = re.split(r'\n(?=---- 0x[0-9A-Fa-f]+: )', text)

count = 0
for section in sections:
    m = re.match(r'---- (0x[0-9A-Fa-f]+): (.+?) \((\d+)ms(?:, (\d+) lines)?\) (?:----|FAIL: ?(.*?) ----)', section)
    if not m:
        continue
    rva_hex, name, ms, lines_n, fail_reason = m.groups()
    rva = int(rva_hex, 16)
    if fail_reason is not None:
        continue  # skip failed ones
    path = rva_to_path.get(rva)
    if not path:
        print(f'  no path for {rva_hex}', file=sys.stderr)
        continue
    # Extract the C body (lines after the header, until end of section)
    # Remove the Ghidra log wrapper "INFO  GhidraScript> ... (GhidraScript)" from each line if present.
    body_lines = section.split('\n')[1:]
    clean = []
    wrapper = re.compile(r'^INFO\s+[^>]+>\s?(.*?)(?:\s+\(GhidraScript\))?$')
    for ln in body_lines:
        wm = wrapper.match(ln)
        clean.append(wm.group(1) if wm else ln)
    body = '\n'.join(clean).rstrip() + '\n'

    out_path = OUT / f'{path}.c'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Append if already exists (multiple methods per class), otherwise write header
    if not out_path.exists():
        out_path.write_text(f'// Untyped-recovery test for top-level class: {path.replace("/", ".")}\n\n', encoding='utf-8')
    with open(out_path, 'a', encoding='utf-8') as f:
        f.write(f'// === {name} (RVA: {rva_hex}) === [UNTYPED RECOVERY, {ms}ms, {lines_n} lines]\n')
        f.write(body)
        f.write('\n')
    print(f'  wrote {name} -> {out_path}')
    count += 1

print(f'\n{count} methods split into {OUT}')