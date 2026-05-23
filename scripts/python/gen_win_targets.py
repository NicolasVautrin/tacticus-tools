"""Generate Ghidra decompilation targets for the Windows GameAssembly.dll
build, using Il2CppDumper script.json directly (bypassing il2cpp_full.json).

Filters game-prefix namespaces (Idun.*, IdunBattle.*, IdunMetaLogic.*, ...),
excludes framework/vendor (UnityEngine, System, Newtonsoft, ...), strips
fully-shared generic stubs (`__Il2CppFullySharedGenericType`), and produces:

    data/dumps/<hash>/all_game_targets_win.tsv

with one line per method: `top_path \t method_full_name \t rva_hex`,
suitable for GhidraDecompileBattleLogicParallel.java. Output lives inside
the per-hash dump dir so it stays paired with the script.json it was
derived from.
"""

import json
import os
import sys

from _dump_path import current_dump_dir

DUMP = current_dump_dir()
SRC = str(DUMP / 'script.json')
OUT_TSV = str(DUMP / 'all_game_targets_win.tsv')

# Match if the method's full name STARTS WITH any of these prefixes.
ACCEPT_PREFIXES = (
    'Idun.', 'idun.',
    'IdunBattle.', 'IdunBattleLogic.',
    'IdunMetaLogic.',
    'IdunShared.',
    'thor.', 'Thor.',
    'tactic.', 'Tactic.',
)

REJECT_PREFIXES = (
    'UnityEngine.', 'Unity.',
    'System.', 'Microsoft.',
    'Newtonsoft.',
    'Loki.', 'loki.',
    'Snowprint.', 'snowprint.',
    'Mono.',
    'TMPro.', 'DG.', 'I2.',
    'JetBrains.',
)


def sanitize(s: str) -> str:
    return (
        s.replace('<', '_')
         .replace('>', '_')
         .replace('`', '_T')
         .replace(',', '_')
         .replace(' ', '')
    )


def split_class_method(name: str) -> tuple[str, str] | None:
    """Il2CppDumper formats names as 'Some.Class$$method'. Some entries may
    have nested classes / generics with embedded `$`. We split on the LAST
    '$$' that's not inside a generic parameter list."""
    idx = name.rfind('$$')
    if idx < 0:
        return None
    cls = name[:idx]
    method = name[idx + 2:]
    return cls, method


def main():
    if not os.path.exists(SRC):
        print(f'error: {SRC} missing — run Il2CppDumper first', file=sys.stderr)
        sys.exit(1)
    with open(SRC) as f:
        data = json.load(f)
    methods_in = data.get('ScriptMethod', [])

    rows = []
    skipped_noise = 0
    skipped_namespace = 0
    skipped_no_class = 0
    skipped_shared = 0

    for entry in methods_in:
        name = entry.get('Name') or ''
        addr = entry.get('Address')
        if not name or addr is None:
            continue
        # Skip fully-shared generic stubs (compiler-generated wrappers
        # that delegate to type-specific bodies — pointless to decompile).
        if '__Il2CppFullySharedGenericType' in name:
            skipped_shared += 1
            continue
        split = split_class_method(name)
        if split is None:
            skipped_no_class += 1
            continue
        cls, method = split
        # Reject framework noise.
        if any(cls.startswith(p) for p in REJECT_PREFIXES):
            skipped_namespace += 1
            continue
        # Accept game prefixes OR un-namespaced (no dot) class names.
        if not any(cls.startswith(p) for p in ACCEPT_PREFIXES):
            if '.' in cls and cls[0].isupper():
                skipped_namespace += 1
                continue
        # Skip compiler-generated noise classes.
        if '<>c__' in name or 'DisplayClass' in name:
            skipped_noise += 1
            continue
        # Build top-level class path (strip nested class suffixes).
        # Il2CppDumper uses '/' for nested? Actually it uses '.', and
        # generics are inline. Take the class name as-is and split on '.'.
        top_class = cls.split('/')[0]  # strip any nested separator
        top_path = '/'.join(sanitize(p) for p in top_class.split('.'))
        # Build the canonical method full name (Class.method).
        full_name = f'{cls}.{method}'.replace('/', '.')
        rows.append((addr, top_path, full_name))

    rows.sort()
    with open(OUT_TSV, 'w', encoding='utf-8') as f:
        for rva, top_path, name in rows:
            safe = name.replace('\t', ' ').replace('\n', ' ')
            f.write(f'{top_path}\t{safe}\t{rva:x}\n')
    print(f'Total methods: {len(rows)}')
    print(f'  Skipped fully-shared generics: {skipped_shared}')
    print(f'  Skipped noise (<>c__, DisplayClass): {skipped_noise}')
    print(f'  Skipped framework namespace: {skipped_namespace}')
    print(f'  Skipped no class delimiter: {skipped_no_class}')
    print(f'Wrote to {OUT_TSV}')


if __name__ == '__main__':
    main()
