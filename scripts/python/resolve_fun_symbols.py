"""Resolve FUN_xxxxxxxx references in decompiled .c files using symbols.json.

Converts Ghidra addresses to RVAs (- 0x100000) and looks them up in symbols.json.
Replaces FUN_xxxxxxxx with the real method name in-place.
"""

import json
import os
import re
import sys

DECOMPILED_DIR = 'data/decompiled_tacticus'
SYMBOLS_FILE = 'data/symbols.json'
IMAGE_BASE = 0x100000

# Load symbols
print(f'Loading {SYMBOLS_FILE}...')
with open(SYMBOLS_FILE) as f:
    data = json.load(f)

methods = data.get('methods', {})

# Build reverse lookup: RVA (int) -> name
rva_to_name = {}
for rva_hex, name in methods.items():
    rva_to_name[int(rva_hex, 16)] = name
print(f'Loaded {len(rva_to_name)} method symbols')

# Also load existing resolved_symbols.json for IL2CPP runtime functions
resolved_file = 'data/resolved_symbols.json'
manual_mappings = {}
if os.path.exists(resolved_file):
    with open(resolved_file) as f:
        manual_mappings = json.load(f)
    print(f'Loaded {len(manual_mappings)} manual mappings from resolved_symbols.json')

# FUN_ pattern
FUN_PATTERN = re.compile(r'\bFUN_([0-9a-f]{8})\b')
THUNK_PATTERN = re.compile(r'\bthunk_FUN_([0-9a-f]{8})\b')

# Stats
total_files = 0
modified_files = 0
total_replacements = 0
unresolved = {}  # addr -> count

# Walk all .c files
for root, dirs, files in os.walk(DECOMPILED_DIR):
    for filename in files:
        if not filename.endswith('.c'):
            continue
        filepath = os.path.join(root, filename)
        total_files += 1

        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        original = content
        file_replacements = 0

            # Replace all FUN_ and thunk_FUN_ in one pass
        def replace_match(match):
            full = match.group(0)
            addr_hex = match.group(1)
            ghidra_addr = int(addr_hex, 16)
            rva = ghidra_addr - IMAGE_BASE
            is_thunk = full.startswith('thunk_')

            # Check manual mappings first (try both full and base FUN_ key)
            base_key = f'FUN_{addr_hex}'
            if full in manual_mappings:
                return manual_mappings[full]
            if base_key in manual_mappings:
                resolved_name = manual_mappings[base_key]
                return f'thunk_{resolved_name}' if is_thunk else resolved_name

            # Check symbols
            if rva in rva_to_name:
                name = rva_to_name[rva]
                safe = name.replace('<', '_').replace('>', '_').replace('`', '_T')
                return f'thunk_{safe}' if is_thunk else safe

            # Track unresolved
            unresolved[addr_hex] = unresolved.get(addr_hex, 0) + 1
            return full

        combined = re.compile(r'\b(?:thunk_)?FUN_([0-9a-f]{8})\b')
        content = combined.sub(replace_match, content)

        # Count replacements by diffing
        file_replacements = sum(1 for a, b in zip(original.split(), content.split()) if a != b)
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            modified_files += 1
            total_replacements += file_replacements

        if total_files % 500 == 0:
            print(f'  Progress: {total_files} files scanned, {modified_files} modified, {total_replacements} replacements')

print(f'\nDone:')
print(f'  Files scanned: {total_files}')
print(f'  Files modified: {modified_files}')
print(f'  Total replacements: {total_replacements}')
print(f'  Unique unresolved FUN_: {len(unresolved)}')

# Show top unresolved
if unresolved:
    print(f'\nTop 20 most referenced unresolved FUN_:')
    for addr, count in sorted(unresolved.items(), key=lambda x: -x[1])[:20]:
        rva = int(addr, 16) - IMAGE_BASE
        print(f'  FUN_{addr} (RVA 0x{rva:x}) — {count} references')