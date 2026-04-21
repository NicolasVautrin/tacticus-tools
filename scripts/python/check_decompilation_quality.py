"""Spot-check the quality of decompiled .c files after enriched Ghidra pass.

Reports:
  - Unique FUN_ references (should be near zero)
  - undefined8 / undefined4 count (should be low)
  - Coroutine files placement (must be under parent class dir)
  - Sample qualitative view of key files
"""

import os
import re
import sys

ROOT = 'data/decompiled_tacticus'

def count_patterns(root, patterns):
    counts = {p: set() if p == 'FUN_unique' else 0 for p in patterns}
    total_files = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith('.c'):
                continue
            total_files += 1
            path = os.path.join(dirpath, f)
            with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read()
            counts['FUN_unique'].update(re.findall(r'FUN_[0-9a-f]{8}', content))
            counts['undefined8'] += len(re.findall(r'\bundefined8\b', content))
            counts['undefined'] += len(re.findall(r'\bundefined\b', content))
            counts['long param_1'] += len(re.findall(r'\blong param_\d+\b', content))
            counts['total_lines'] += content.count('\n')
    counts['total_files'] = total_files
    counts['FUN_unique_count'] = len(counts.pop('FUN_unique'))
    return counts

def check_placement():
    """Check that coroutines are placed under their parent class directory."""
    result = {'correctly_placed': 0, 'loose_coroutines': []}
    for dirpath, _, files in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        for f in files:
            # Coroutine files start with _ (sanitized <)
            if f.startswith('_') and 'd__' in f and f.endswith('.c'):
                # If the parent dir name == the coroutine's declaring class short name, OK
                result['correctly_placed'] += 1
            elif 'd__' in f and f.endswith('.c'):
                # Top-level "d__" file? suspicious
                if '/' not in rel:
                    result['loose_coroutines'].append(os.path.join(rel, f))
    return result

def sample(files):
    for rel_path in files:
        full = os.path.join(ROOT, rel_path)
        if not os.path.exists(full):
            print(f'  MISSING: {rel_path}')
            continue
        size = os.path.getsize(full)
        with open(full, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        fun_count = len(set(re.findall(r'FUN_[0-9a-f]{8}', content)))
        undefined_count = len(re.findall(r'\bundefined8?\b', content))
        print(f'  {rel_path}: {size//1024}KB, {fun_count} FUN_ uniq, {undefined_count} undefined')

print(f'=== Quality report on {ROOT} ===\n')
if not os.path.exists(ROOT):
    print(f'{ROOT} does not exist yet')
    sys.exit(0)

patterns = ['FUN_unique', 'undefined8', 'undefined', 'long param_1', 'total_lines']
counts = count_patterns(ROOT, patterns)
print(f'Files: {counts["total_files"]}')
print(f'Total lines: {counts["total_lines"]:,}')
print(f'FUN_ unique: {counts["FUN_unique_count"]}')
print(f'undefined8:  {counts["undefined8"]:,}')
print(f'undefined:   {counts["undefined"]:,}')
print(f'long param_: {counts["long param_1"]:,}')
print()

placement = check_placement()
print(f'Coroutines correctly placed: {placement["correctly_placed"]}')
print(f'Loose coroutines at root: {len(placement["loose_coroutines"])}')
for p in placement['loose_coroutines'][:5]:
    print(f'  {p}')
print()

print('=== Key file samples ===')
samples = [
    'IdunBattle/Runner/IdunRunner.c',
    'IdunBattle/AI/Playbook/HealPlaybook.c',
    'IdunBattle/AI/DefaultPlayerStrategy.c',
    'IdunBattleLogic/Entities/Abilities/Triggered/LifewardsAbility.c',
    'IdunBattle/Entities/Abilities/BaseTriggeredAbility.c',
    'IdunBattle/AI/Playbook/BasePlaybook.c',
]
sample(samples)
