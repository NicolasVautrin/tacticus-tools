"""Convert data/il2cpp_full.json to TSV files for fast consumption by the Ghidra Java script.

Outputs:
  data/il2cpp_methods.tsv  — one method per line:
    RVA_hex \t full_name \t declaring_class \t is_static(0|1) \t return_type \t params(name:type,name:type,...)

  data/il2cpp_classes.tsv  — one class per line:
    full_name \t size \t parent \t vtype \t fields(name:type:offset,name:type:offset,...)

  data/il2cpp_enums.tsv    — one enum per line:
    full_name \t values(value=name,value=name,...)
"""

import json

SRC = 'data/il2cpp_full.json'

with open(SRC) as f:
    d = json.load(f)

methods = d['methods']
classes = d['classes']
enums = d['enums']

# --- methods.tsv ---
with open('data/il2cpp_methods.tsv', 'w', encoding='utf-8') as f:
    for rva, m in methods.items():
        name = m['n'].replace('\t', ' ').replace('\n', ' ')
        decl = m.get('d', '').replace('\t', ' ')
        is_static = int(m.get('s', 0))
        ret = m.get('r', '').replace('\t', ' ')
        params = m.get('p', [])
        p_str = ','.join(
            f"{(p.get('n') or '').replace(',', '_').replace(':', '_').replace('\t', ' ')}:{(p.get('t') or '').replace(',', '_').replace(':', '_').replace('\t', ' ')}"
            for p in params
        )
        f.write(f'{rva}\t{name}\t{decl}\t{is_static}\t{ret}\t{p_str}\n')
print(f'Wrote {len(methods)} methods')

# --- classes.tsv ---
with open('data/il2cpp_classes.tsv', 'w', encoding='utf-8') as f:
    for name, c in classes.items():
        sz = c.get('size', 0)
        parent = (c.get('parent') or '').replace('\t', ' ')
        vtype = c.get('vtype', 0)
        fields = c.get('fields', [])
        f_str = ','.join(
            f"{(fd.get('n') or '').replace(',', '_').replace(':', '_').replace('\t', ' ')}:{(fd.get('t') or '').replace(',', '_').replace(':', '_').replace('\t', ' ')}:{fd.get('o', 0)}"
            for fd in fields
        )
        f.write(f'{name}\t{sz}\t{parent}\t{vtype}\t{f_str}\n')
print(f'Wrote {len(classes)} classes')

# --- enums.tsv ---
with open('data/il2cpp_enums.tsv', 'w', encoding='utf-8') as f:
    for name, values in enums.items():
        v_str = ','.join(f'{v}={n}' for v, n in values.items())
        f.write(f'{name}\t{v_str}\n')
print(f'Wrote {len(enums)} enums')
