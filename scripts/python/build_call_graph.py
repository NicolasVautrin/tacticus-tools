"""
Build a call graph from the Ghidra-decompiled .c files.

Each .c has headers of the form:
    // === <FullName> (RVA: 0x...) ===
followed by the function body. We parse:
  - Header: caller_fqn + caller_rva
  - Body: every call expression `ident(` appearing up to the next header

Callees are identified as either:
  - `FUN_<hex>` or `thunk_FUN_<hex>` -> resolved via il2cpp_full.json methods map
  - Long underscore-separated C# identifiers like
    `IdunBattle_DSL_AbilityBehaviour_op_BitwiseAnd` -> translated back to dot form
  - Short/unknown ones are dropped.

Output: data/call_graph.json
    {
      "caller.Full.Name": ["callee1", "callee2", ...],
      ...
    }
Plus companion `data/call_graph_stats.json` with counts and unresolved.
"""
from __future__ import annotations
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path('C:/Users/nicolasv/tacticus-tools')
DECOMP = ROOT / 'data' / 'decompiled_tacticus'
DUMP = ROOT / 'data' / 'il2cpp_full.json'
OUT = ROOT / 'data' / 'call_graph.json'
OUT_STATS = ROOT / 'data' / 'call_graph_stats.json'

HEADER_RE = re.compile(r'^\s*//\s*===\s*(?P<name>[^=]+?)\s*\(RVA:\s*0x(?P<rva>[0-9a-fA-F]+)\)\s*===')
FUN_CALL_RE = re.compile(r'\b(?:thunk_FUN_|FUN_)([0-9a-f]{6,10})\b')
# Underscore-name callee heuristic: identifier with >= 2 underscores, at least one uppercase
# component, immediately followed by `(`. Excludes local vars and keywords.
IDENT_CALL_RE = re.compile(r'\b([A-Z][A-Za-z0-9_]*(?:_[A-Za-z0-9_]+){1,})\s*\(')
# These C identifiers appear as calls but aren't real callees:
FALSE_POSITIVES = {
    'WARNING',
}

# Tokens that are clearly local variable names declared in Ghidra output
LOCAL_DECL_TYPES = {'undefined8', 'undefined4', 'undefined2', 'undefined1',
                    'ulong', 'uint', 'int', 'long', 'short', 'byte', 'char',
                    'code'}


def translate_identifier(ident: str) -> str:
    """Convert `IdunBattle_AI_X_Method` back to `IdunBattle.AI.X.Method`.
    We collapse underscores into dots, but keep known operator suffixes like
    `_ctor`, `_op_BitwiseAnd`, `_get_Foo`, `_set_Foo` as the final segment.
    """
    if not ident or '_' not in ident:
        return ident
    # Known method prefix markers that should keep their underscore-prefixed form
    # as a single final segment.
    method_markers = ('ctor', 'cctor', 'op_', 'get_', 'set_', 'add_', 'remove_', 'Invoke')
    parts = ident.split('_')
    out_parts: list[str] = []
    i = 0
    while i < len(parts):
        p = parts[i]
        # Check if this part starts a method marker (consuming multiple underscore pieces)
        if any(p == m or p.startswith(m.rstrip('_')) for m in method_markers) and i > 0 and out_parts:
            # Absorb the rest as the method name
            method = '_'.join(parts[i:])
            out_parts.append(method)
            i = len(parts)
        else:
            out_parts.append(p)
            i += 1
    return '.'.join(out_parts)


def strip_body_comments(text: str) -> str:
    """Remove /* ... */ block comments and // line comments (except header ones)."""
    # Remove block comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    # Remove line comments that are not headers (we'll keep headers for the outer parser)
    lines = []
    for line in text.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('//') and '===' not in stripped:
            continue
        lines.append(line)
    return '\n'.join(lines)


def extract_methods_from_file(path: Path, methods_by_rva: dict) -> list[tuple[str, int, str]]:
    """Return list of (caller_fqn, caller_rva_int, body_text)."""
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.split('\n')
    # Find header positions
    headers = []  # (lineno, name, rva_int)
    for i, ln in enumerate(lines):
        m = HEADER_RE.match(ln)
        if m:
            name = m.group('name').strip()
            rva = int(m.group('rva'), 16)
            headers.append((i, name, rva))
    out = []
    for idx, (lineno, name, rva) in enumerate(headers):
        end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        body = '\n'.join(lines[lineno + 1:end])
        body = strip_body_comments(body)
        out.append((name, rva, body))
    return out


def extract_callees(body: str, methods_by_rva: dict,
                    unresolved_counter: dict) -> set[str]:
    """Extract callee identifiers from a function body."""
    callees: set[str] = set()
    # FUN_xxx calls -> try to resolve via RVA map
    for m in FUN_CALL_RE.finditer(body):
        rva = int(m.group(1), 16)
        entry = methods_by_rva.get(rva)
        if entry is not None:
            callees.add(entry['n'])
        else:
            tok = m.group(0)
            callees.add(tok)
            unresolved_counter[tok] = unresolved_counter.get(tok, 0) + 1
    # Named calls via underscore-form identifier
    for m in IDENT_CALL_RE.finditer(body):
        ident = m.group(1)
        if ident in FALSE_POSITIVES:
            continue
        if ident in LOCAL_DECL_TYPES:
            continue
        # Must look like a C# method: contain at least two namespace parts
        # (at least 2 underscores, first segment non-all-lowercase).
        if ident.count('_') < 2:
            continue
        callees.add(translate_identifier(ident))
    return callees


def main():
    print('Loading il2cpp dump...')
    with open(DUMP, 'r', encoding='utf-8') as f:
        dump = json.load(f)
    raw_methods = dump['methods']
    # keys are hex strings without 0x
    methods_by_rva: dict[int, dict] = {}
    for k, v in raw_methods.items():
        try:
            methods_by_rva[int(k, 16)] = v
        except ValueError:
            continue
    print(f'Indexed {len(methods_by_rva)} methods by RVA')

    graph: dict[str, set[str]] = defaultdict(set)
    unresolved_counter: dict[str, int] = {}
    stats = {
        'files': 0,
        'methods': 0,
        'edges': 0,
        'unresolved_unique': 0,
    }

    c_files = sorted(DECOMP.rglob('*.c'))
    print(f'Scanning {len(c_files)} .c files...')
    for idx, f in enumerate(c_files):
        if idx and idx % 500 == 0:
            print(f'  {idx}/{len(c_files)}')
        stats['files'] += 1
        for caller, rva, body in extract_methods_from_file(f, methods_by_rva):
            stats['methods'] += 1
            # Prefer canonical FQN from the dump if available (header can be slightly noisy)
            canonical = methods_by_rva.get(rva, {}).get('n') or caller
            callees = extract_callees(body, methods_by_rva, unresolved_counter)
            callees.discard(canonical)  # no self-loops
            if callees:
                graph[canonical] |= callees
                stats['edges'] += len(callees)
    stats['unresolved_unique'] = len(unresolved_counter)

    # Serialize
    print(f'Writing call graph ({len(graph)} nodes, {stats["edges"]} edges)...')
    with open(OUT, 'w', encoding='utf-8') as out:
        json.dump({k: sorted(v) for k, v in graph.items()}, out, indent=1)
    # Top unresolved
    top_unresolved = sorted(unresolved_counter.items(), key=lambda x: -x[1])[:50]
    with open(OUT_STATS, 'w', encoding='utf-8') as out:
        json.dump({
            'stats': stats,
            'top_unresolved_FUN_': top_unresolved,
        }, out, indent=2)
    print('Done.')
    print(f'  Files:      {stats["files"]}')
    print(f'  Methods:    {stats["methods"]}')
    print(f'  Edges:      {stats["edges"]}')
    print(f'  Unresolved FUN_ (unique): {stats["unresolved_unique"]}')


if __name__ == '__main__':
    main()
