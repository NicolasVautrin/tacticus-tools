"""Rebuild the `sources/` directory from Il2CppDumper's `dump.cs` (Windows).

The previous `sources/` content was generated from the Android build
(libil2cpp.so) with Android RVAs. After switching to GameAssembly.dll,
those RVAs are obsolete. This script regenerates the per-class .cs
skeleton files with Windows RVAs (already baked into dump.cs).

Layout:
    sources/<Namespace>/<Sub>/.../<ClassName>.cs

(No per-assembly grouping like before — Il2CppDumper's dump.cs doesn't
mark which image each class came from. Namespaces are unique enough.)

Each output file looks like:

    // Source: Il2CppDumper dump.cs (GameAssembly.dll, build vXXX)
    namespace Idun.Source.IdunBattle.View
    {
        // TypeDefIndex: 12345
        public class BattleConfigBuilder
        {
            // ... fields with // 0xOFFSET
            // ... methods with // RVA: 0xRVA
        }
    }
"""

import os
import re
import sys
from pathlib import Path

DUMP_CS = Path('data/win_dump/dump.cs')
OUT_DIR = Path('sources_win')

NS_RE = re.compile(r'^// Namespace:\s*(.*)$')
TYPE_DECL_RE = re.compile(
    r'^\s*(?:\[[^\]]+\]\s*)*'                           # any number of [Attr]
    r'(?:public|internal|private|protected)?\s*'         # access
    r'(?:static\s+|abstract\s+|sealed\s+|partial\s+|readonly\s+)*'
    r'(?:struct|class|interface|enum)\s+'
    r'([A-Za-z_][\w<>`,\s.]*?)'
    r'(?:\s*:\s*[^{]+)?'                                # base/interface
    r'\s*(?://.*)?$')


def sanitize_path(s: str) -> str:
    """Make a string safe for filesystem use."""
    return (s.replace('<', '_')
             .replace('>', '_')
             .replace('`', '_T')
             .replace(',', '_')
             .replace(' ', '')
             .replace('?', '_q'))


def class_name_from_decl(line: str) -> str | None:
    m = TYPE_DECL_RE.match(line)
    if not m:
        return None
    raw = m.group(1).strip()
    # Strip generic params and base list
    raw = re.split(r'[<:]', raw, maxsplit=1)[0].strip()
    return raw


def is_type_decl_line(line: str) -> bool:
    """A line that opens a top-level type (class/struct/etc.). Excludes
    nested type declarations inside another class. We rely on indentation:
    top-level decls are flush-left."""
    if line.startswith('\t') or line.startswith(' '):
        return False
    return bool(TYPE_DECL_RE.match(line))


def find_block_end(lines: list[str], start: int) -> int:
    """Given the index of a line opening `{`, return the index of the
    matching closing `}`. Counts braces while ignoring strings/comments
    on a single-line basis."""
    depth = 0
    in_block_comment = False
    in_string = False
    string_char = ''
    for i in range(start, len(lines)):
        line = lines[i]
        j = 0
        while j < len(line):
            c = line[j]
            if in_block_comment:
                if c == '*' and j + 1 < len(line) and line[j + 1] == '/':
                    in_block_comment = False
                    j += 2
                    continue
            elif in_string:
                if c == '\\':
                    j += 2
                    continue
                if c == string_char:
                    in_string = False
            else:
                if c == '/' and j + 1 < len(line):
                    nxt = line[j + 1]
                    if nxt == '/':
                        break  # rest of line is a line comment
                    if nxt == '*':
                        in_block_comment = True
                        j += 2
                        continue
                if c == '"' or c == "'":
                    in_string = True
                    string_char = c
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        return i
            j += 1
    return -1


def main():
    if not DUMP_CS.exists():
        print(f'ERROR: {DUMP_CS} missing', file=sys.stderr)
        sys.exit(1)

    print(f'Reading {DUMP_CS} ...')
    text = DUMP_CS.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines(keepends=True)
    print(f'  {len(lines):,} lines')

    if OUT_DIR.exists():
        # Don't blindly nuke; require explicit removal by user.
        print(f'NOTE: {OUT_DIR} exists. Files will be overwritten in place.')
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    current_ns = ''
    pending_attrs: list[str] = []           # accumulated [Attr] / // comment lines before a class
    written = 0
    skipped_no_name = 0
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.rstrip('\n').rstrip('\r')

        # Track namespace (Il2CppDumper marks each class with `// Namespace: ...`).
        m = NS_RE.match(stripped)
        if m:
            current_ns = m.group(1).strip()
            pending_attrs = []
            i += 1
            continue

        # Accumulate attribute and comment lines preceding a top-level decl.
        if stripped.startswith('[') or stripped.startswith('//'):
            # Reset accumulation if blank line preceded
            pending_attrs.append(line)
            i += 1
            continue

        if stripped == '':
            pending_attrs = []
            i += 1
            continue

        if is_type_decl_line(stripped):
            cls_name = class_name_from_decl(stripped)
            if not cls_name:
                pending_attrs = []
                i += 1
                continue
            # Find the opening brace for this type
            brace_idx = i
            while brace_idx < n and '{' not in lines[brace_idx]:
                brace_idx += 1
            if brace_idx >= n:
                # No body — single-line forward decl, just write the line.
                end = i
            else:
                end = find_block_end(lines, brace_idx)
                if end < 0:
                    end = i
            # Emit the file
            block_lines = pending_attrs + lines[i:end + 1]
            pending_attrs = []
            ns_path = sanitize_path(current_ns).replace('.', os.sep) if current_ns else '_NoNamespace'
            out_dir = OUT_DIR / ns_path
            out_dir.mkdir(parents=True, exist_ok=True)
            file_name = sanitize_path(cls_name) + '.cs'
            out_path = out_dir / file_name
            # Build content with namespace wrapper
            buf = ['// Source: Il2CppDumper dump.cs (GameAssembly.dll)\n']
            if current_ns:
                buf.append(f'namespace {current_ns}\n')
                buf.append('{\n')
            buf.extend(block_lines)
            if not block_lines or not block_lines[-1].endswith('\n'):
                buf.append('\n')
            if current_ns:
                buf.append('}\n')
            # Append for partial classes / multiple classes per namespace+name —
            # Il2CppDumper sometimes emits the same class twice (one per image).
            mode = 'a' if out_path.exists() else 'w'
            with out_path.open(mode, encoding='utf-8') as f:
                f.writelines(buf)
            written += 1
            i = end + 1
            continue

        # Non-type, non-namespace line at column 0 — skip.
        pending_attrs = []
        i += 1

    print(f'Wrote {written} class blocks to {OUT_DIR}/')


if __name__ == '__main__':
    main()
