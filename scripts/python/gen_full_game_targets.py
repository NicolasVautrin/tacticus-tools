"""Full decompilation targets: every game-specific method in `libil2cpp.so`.

Same logic as `gen_battlelogic_targets.py`, but accepts ALL game namespaces
(Assembly-CSharp.dll + MetaLogicAssembly.dll + IdunSharedAssembly.dll +
BattleLogicAssembly.dll + thor + idun + ...). Excludes only pure framework
noise (Unity / mscorlib / Newtonsoft / Snowprint / Microsoft / Loki).

Output: `data/all_game_targets.tsv`. Consumed by
`GhidraDecompileGameAll.java` (a sibling of GhidraDecompileBattleLogicParallel
with a different TARGETS_FILE).

Estimated method count: ~80-100k (vs. ~30k for battlelogic-only).
Decompile time at 16 threads / 120s timeout: ~6-10 hours.
"""

import json

SRC = 'data/il2cpp_full.json'
OUT_TSV = 'data/all_game_targets.tsv'

# Match if the method's full name STARTS WITH any of these prefixes.
ACCEPT_PREFIXES = (
    'Idun.', 'idun.',
    'IdunBattle.', 'IdunBattleLogic.',
    'IdunMetaLogic.',
    'thor.', 'Thor.',
    'tactic.', 'Tactic.',
)

# Hard-exclude framework / 3rd-party — these blow up Ghidra time without
# adding value to game-logic understanding.
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


def compute_top(class_name, classes, cache):
    if class_name in cache:
        return cache[class_name]
    cls = classes.get(class_name)
    if not cls:
        cache[class_name] = None
        return None
    decl = cls.get('decl')
    if decl:
        top = compute_top(decl, classes, cache) or decl
    else:
        top = class_name
    cache[class_name] = top
    return top


def main():
    with open(SRC) as f:
        data = json.load(f)
    methods = data['methods']
    classes = data['classes']
    cache = {}
    rows = []
    skipped_noise = 0
    skipped_no_top = 0
    skipped_namespace = 0
    for rva_hex, m in methods.items():
        name = m['n']
        if any(name.startswith(p) for p in REJECT_PREFIXES):
            skipped_namespace += 1
            continue
        # Accept if matches game-prefix OR has no namespace prefix at all
        # (some code lives in the global / anonymous namespace).
        accepted = any(name.startswith(p) for p in ACCEPT_PREFIXES)
        if not accepted and '.' in name and not name[0].islower():
            # Capitalized non-game namespace (e.g. some 3rd party).
            skipped_namespace += 1
            continue
        if '<>c__' in name or 'DisplayClass' in name:
            skipped_noise += 1
            continue
        decl = m.get('d')
        if not decl:
            skipped_no_top += 1
            continue
        top = compute_top(decl, classes, cache)
        if not top:
            skipped_no_top += 1
            continue
        top_path = '/'.join(sanitize(p) for p in top.split('.'))
        rows.append((int(rva_hex, 16), top_path, name))
    rows.sort()
    with open(OUT_TSV, 'w', encoding='utf-8') as f:
        for rva, top_path, name in rows:
            safe = name.replace('\t', ' ').replace('\n', ' ')
            f.write(f'{top_path}\t{safe}\t{rva:x}\n')
    print(f'Total methods: {len(rows)}')
    print(f'  Skipped noise (<>c__, DisplayClass): {skipped_noise}')
    print(f'  Skipped missing declaring: {skipped_no_top}')
    print(f'  Skipped framework namespace: {skipped_namespace}')
    print(f'Wrote to {OUT_TSV}')


if __name__ == '__main__':
    main()
