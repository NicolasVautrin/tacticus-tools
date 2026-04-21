"""Generate Ghidra decompilation targets for BattleLogicAssembly methods.

Reads data/il2cpp_full.json, filters IdunBattle.* / IdunBattleLogic.* namespaces,
computes the TOP-LEVEL declaring class for each method (so nested classes /
coroutines / interface implementations go into their outer class's .c file),
and emits data/all_battlelogic_targets.tsv with one line per method:

    top_class_fs_path \t method_full_name \t rva_hex

where top_class_fs_path is the filesystem-safe path that Ghidra will use to
name the output .c file (e.g. "IdunBattle/AI/DefaultPlayerStrategy").
"""

import json

SRC = 'data/il2cpp_full.json'
OUT_TSV = 'data/all_battlelogic_targets.tsv'


def sanitize_fs_part(s: str) -> str:
    """Replace chars that are illegal/messy in filesystem paths."""
    return (
        s.replace('<', '_')
         .replace('>', '_')
         .replace('`', '_T')
         .replace(',', '_')
         .replace(' ', '')
    )


def compute_top_class(class_name: str, classes: dict, cache: dict) -> str | None:
    """Walk the declaring_type chain up to the top-level class.

    Returns the fully-qualified name of the outermost declaring class,
    or None if the class isn't in the dump.
    """
    if class_name in cache:
        return cache[class_name]
    cls = classes.get(class_name)
    if not cls:
        cache[class_name] = None
        return None
    decl = cls.get('decl')
    if decl:
        top = compute_top_class(decl, classes, cache) or decl
    else:
        top = class_name
    cache[class_name] = top
    return top


def main():
    with open(SRC) as f:
        data = json.load(f)

    methods = data['methods']
    classes = data['classes']
    top_cache: dict[str, str | None] = {}

    rows = []
    skipped_noise = 0
    skipped_no_top = 0

    for rva_hex, m in methods.items():
        name = m['n']
        if not (name.startswith('IdunBattle.') or name.startswith('IdunBattleLogic.')):
            continue
        if '<>c__' in name or 'DisplayClass' in name:
            skipped_noise += 1
            continue

        decl = m.get('d')  # direct declaring class
        if not decl:
            skipped_no_top += 1
            continue
        top = compute_top_class(decl, classes, top_cache)
        if not top:
            skipped_no_top += 1
            continue

        # Build filesystem path for the top class: replace '.' with '/', sanitize
        top_path = '/'.join(sanitize_fs_part(p) for p in top.split('.'))

        rows.append((int(rva_hex, 16), top_path, name))

    rows.sort()  # by RVA

    with open(OUT_TSV, 'w', encoding='utf-8') as f:
        for rva, top_path, name in rows:
            safe_name = name.replace('\t', ' ').replace('\n', ' ')
            f.write(f'{top_path}\t{safe_name}\t{rva:x}\n')

    total = len(rows)
    coros = sum(1 for _, _, n in rows if '>d__' in n or '_d__' in n)
    nested = sum(1 for _, tp, n in rows if f'{tp.replace("/", ".")}.' != n.rsplit('.', 1)[0] + '.')
    print(f'Total methods: {total}')
    print(f'  Coroutines (d__): {coros}')
    print(f'  Nested (under non-top declaring class): {nested}')
    print(f'  Skipped noise (<>c__, DisplayClass): {skipped_noise}')
    print(f'  Skipped missing declaring: {skipped_no_top}')
    print(f'Written to {OUT_TSV}')


if __name__ == '__main__':
    main()