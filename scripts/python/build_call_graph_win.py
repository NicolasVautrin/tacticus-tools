"""Post-process the Ghidra-decompiled .c files to build a call graph.

Input:  data/decompiled_gameassembly/**/*.c (output of GhidraDecompileGameAssembly)
        data/win_dump/script.json           (Il2CppDumper RVA -> name mapping)

Output: data/call_graph_win.json — adjacency list keyed by caller RVA:
    {
      "<caller_rva_hex>": {
        "name": "FUN_180XXXXXXX",            # Ghidra name (raw FUN_ form)
        "il2cpp_name": "Class$$Method"|null, # mapped from script.json
        "file": "Idun/Source/.../File.c",    # decomp file relative path
        "callees": [
            { "rva": "<rva_hex>", "il2cpp_name": "..."|null }, ...
        ]
      },
      ...
    }

A reverse index (callee_rva -> [caller_rva]) is also written to
`data/call_graph_win.reverse.json` for "who calls X" queries.

The call graph stays platform-stable across rebuilds because it's keyed
by RVA — not by IL2CPP names, which can move when the metadata regenerates.
"""

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from _dump_path import current_dump_dir

ROOT = Path('.')
DUMP = current_dump_dir()
DECOMP_DIR = ROOT / 'data' / 'decompiled_gameassembly'
SCRIPT_JSON = DUMP / 'script.json'
OUT_GRAPH = DUMP / 'call_graph_win.json'
OUT_REVERSE = DUMP / 'call_graph_win.reverse.json'

# Each .c file has blocks separated by:
#   // === <method-name> (RVA: 0xXXXX) ===
#   <decompiled C body>
#   // === <next> (RVA: 0xXXXX) ===
#   ...
HEADER_RE = re.compile(
    r'^// === (.*?) \(RVA: 0x([0-9A-Fa-f]+)\) ==='
    r'(.*)?$', re.MULTILINE)

# Match calls like FUN_180012345 or thunk_FUN_180012345 — captures the VA.
# Ghidra uses VA = ImageBase + RVA. PE x64 default ImageBase is 0x180000000
# for GameAssembly.dll; subtract to recover RVA-space (consistent with
# the RVA headers in our decomp blocks).
CALL_RE = re.compile(r'\b(?:thunk_)?FUN_([0-9A-Fa-f]{8,12})\b')
IMAGE_BASE = 0x180000000


def load_il2cpp_names(path: Path) -> dict[int, str]:
    """Build {RVA -> il2cpp_name} from script.json. RVAs are stored as
    decimal ints in script.json's ScriptMethod entries."""
    if not path.exists():
        print(f'note: {path} not found, no il2cpp names will be attached', file=sys.stderr)
        return {}
    print(f'Loading {path} ...', file=sys.stderr)
    data = json.load(path.open(encoding='utf-8'))
    methods = data.get('ScriptMethod', [])
    out: dict[int, str] = {}
    for m in methods:
        addr = m.get('Address')
        name = m.get('Name')
        if isinstance(addr, int) and name:
            out[addr] = name
    print(f'  {len(out):,} IL2CPP names', file=sys.stderr)
    return out


def parse_decomp_file(path: Path) -> list[tuple[int, str, list[int]]]:
    """Return list of (caller_rva, caller_name, [callee_rvas])."""
    text = path.read_text(encoding='utf-8', errors='replace')
    # Find every method header in this file with its body.
    headers = list(HEADER_RE.finditer(text))
    if not headers:
        return []
    out = []
    for i, m in enumerate(headers):
        name = m.group(1).strip()
        rva = int(m.group(2), 16)
        body_start = m.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[body_start:body_end]
        # Extract callee RVAs (deduplicated, stable order via dict).
        # CALL_RE captures the VA; subtract IMAGE_BASE to get the RVA.
        callees: dict[int, None] = {}
        for c in CALL_RE.finditer(body):
            va = int(c.group(1), 16)
            cr = va - IMAGE_BASE if va >= IMAGE_BASE else va
            if cr != rva:           # don't count self-recursion as edge
                callees[cr] = None
        out.append((rva, name, list(callees.keys())))
    return out


def main():
    if not DECOMP_DIR.exists():
        print(f'ERROR: {DECOMP_DIR} not found', file=sys.stderr)
        sys.exit(1)

    il2cpp_names = load_il2cpp_names(SCRIPT_JSON)

    # Walk all .c files
    cs = sorted(DECOMP_DIR.rglob('*.c'))
    print(f'Found {len(cs):,} .c files', file=sys.stderr)

    graph: dict[str, dict] = {}
    reverse: dict[str, list[str]] = defaultdict(list)
    total_methods = 0
    total_edges = 0

    for path in cs:
        try:
            methods = parse_decomp_file(path)
        except Exception as e:
            print(f'  WARN {path}: {e}', file=sys.stderr)
            continue
        rel = path.relative_to(DECOMP_DIR).as_posix()
        for rva, name, callees in methods:
            total_methods += 1
            rva_hex = f'0x{rva:x}'
            entry = {
                'name': f'FUN_{rva:08x}',
                'il2cpp_name': il2cpp_names.get(rva),
                'decomp_name': name,        # what the decomp header had
                'file': rel,
                'callees': [
                    {
                        'rva': f'0x{c:x}',
                        'il2cpp_name': il2cpp_names.get(c),
                    }
                    for c in callees
                ],
            }
            if rva_hex in graph:
                # Same RVA dumped in multiple files (rare but possible).
                # Merge callees, keep first file as primary.
                existing = graph[rva_hex]
                merged_callees = {c['rva']: c for c in existing['callees']}
                for c in entry['callees']:
                    merged_callees.setdefault(c['rva'], c)
                existing['callees'] = list(merged_callees.values())
            else:
                graph[rva_hex] = entry
            for c in callees:
                total_edges += 1
                reverse[f'0x{c:x}'].append(rva_hex)

    print(f'Methods indexed: {total_methods:,}', file=sys.stderr)
    print(f'Total edges:     {total_edges:,}', file=sys.stderr)
    print(f'Unique callees:  {len(reverse):,}', file=sys.stderr)

    # Reverse: dedup + sort the caller lists
    for k in list(reverse.keys()):
        reverse[k] = sorted(set(reverse[k]))
    # Convert defaultdict for json.dump
    reverse_dict = dict(reverse)

    print(f'Writing {OUT_GRAPH} ...', file=sys.stderr)
    with OUT_GRAPH.open('w', encoding='utf-8') as f:
        json.dump(graph, f)
    print(f'Writing {OUT_REVERSE} ...', file=sys.stderr)
    with OUT_REVERSE.open('w', encoding='utf-8') as f:
        json.dump(reverse_dict, f)
    print('Done.', file=sys.stderr)


if __name__ == '__main__':
    main()
