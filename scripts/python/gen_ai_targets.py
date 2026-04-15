import json

with open('data/symbols.json') as f:
    data = json.load(f)

methods = data.get('methods', {})

ai_rvas = {}
for rva, name in methods.items():
    nl = name.lower()
    if any(x in nl for x in ['.ai.', 'aicontrol', 'playbook', 'aiplayer']):
        # Skip compiler-generated stuff
        if '<>' in name or 'DisplayClass' in name or 'd__' in name:
            continue
        ai_rvas[int(rva, 16)] = name

# Build targets dict for Ghidra
targets = {}
for rva, name in sorted(ai_rvas.items()):
    safe_name = name.replace('<', '_').replace('>', '_').replace('`', '_T')
    targets[safe_name] = rva

print(f'Total decompilable AI methods: {len(targets)}')
with open('data/ai_targets.json', 'w') as f:
    json.dump(targets, f)
print('Written to data/ai_targets.json')
