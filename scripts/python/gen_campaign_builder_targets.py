"""Focused targets for decompiling BattleConfigBuilder + nearby helpers.

We need bodies for `Idun.Source.IdunBattle.View.*` (Assembly-CSharp.dll
namespace not covered by `gen_battlelogic_targets.py`). Output goes to
`data/campaign_builder_targets.tsv` consumed by GhidraDecompileTargeted.java.
"""

import json

SRC = 'data/il2cpp_full.json'
OUT_TSV = 'data/campaign_builder_targets.tsv'

NAMESPACE_PREFIXES = (
    'Idun.Source.IdunBattle.View.',  # BattleConfigBuilder + helpers
)


def sanitize(s: str) -> str:
    return (
        s.replace('<', '_')
         .replace('>', '_')
         .replace('`', '_T')
         .replace(',', '_')
         .replace(' ', '')
    )


def compute_top(class_name: str, classes: dict, cache: dict):
    if class_name in cache:
        return cache[class_name]
    cls = classes.get(class_name)
    if not cls:
        cache[class_name] = None
        return None
    decl = cls.get('decl')
    top = compute_top(decl, classes, cache) or decl if decl else class_name
    cache[class_name] = top
    return top


def main():
    with open(SRC) as f:
        data = json.load(f)
    methods = data['methods']
    classes = data['classes']
    cache: dict = {}
    rows = []
    for rva_hex, m in methods.items():
        name = m['n']
        if not any(name.startswith(p) for p in NAMESPACE_PREFIXES):
            continue
        if '<>c__' in name or 'DisplayClass' in name:
            # keep nested helpers — they may be the lambdas used by the
            # delegate target. Write them under their outer class file.
            pass
        decl = m.get('d')
        if not decl:
            continue
        top = compute_top(decl, classes, cache)
        if not top:
            continue
        top_path = '/'.join(sanitize(p) for p in top.split('.'))
        rows.append((int(rva_hex, 16), top_path, name))
    rows.sort()
    with open(OUT_TSV, 'w', encoding='utf-8') as f:
        for rva, top_path, name in rows:
            f.write(f'{top_path}\t{name}\t{rva:x}\n')
    print(f'Wrote {len(rows)} methods to {OUT_TSV}')


if __name__ == '__main__':
    main()
