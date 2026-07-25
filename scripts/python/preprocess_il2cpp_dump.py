"""Convert data/il2cpp_full.json to TSV files for fast consumption by the Ghidra Java script.

Chaque TSV porte en 1re ligne une ESTAMPILLE DE PROVENANCE (`il2cpp_provenance.py`) : le
sha256 du `GameAssembly.dll` dont le dump est issu. `GhidraApplyIl2CppSymbols.java` la relit
et REFUSE d'appliquer les symboles si elle ne correspond pas au binaire charge.

Pourquoi : le 2026-07-25 on a constate que ces TSV dataient du build de mai alors que le
projet Ghidra portait celui de juin — rien ne le signalait, et le script d'application les lit
en dur. Un `run` aurait ecrase les bons noms par les mauvais, en silence.

Outputs (apres la ligne `#!il2cpp-provenance`) :
  data/symbols/<HASH>/frida/methods.tsv  — one method per line:
    RVA_hex \t full_name \t declaring_class \t is_static(0|1) \t return_type \t params(name:type,...)

  data/symbols/<HASH>/frida/classes.tsv  — one class per line:
    full_name \t size \t parent \t vtype \t fields(name:type:offset,...)

  data/symbols/<HASH>/frida/enums.tsv    — one enum per line:
    full_name \t values(value=name,...)

Usage :
    python scripts/python/preprocess_il2cpp_dump.py [--dll <GameAssembly.dll>]
Le dump `data/il2cpp_full.json` doit avoir ete produit depuis CE binaire
(`scripts/frida/dump-il2cpp-full.js` injecte dans le jeu en cours).
"""

import argparse
import json
from pathlib import Path

from il2cpp_provenance import ProvenanceError, installed_dll, stamp_for

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / 'data' / 'il2cpp_full.json'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dll', help='binaire de reference (defaut : le build installe)')
    args = ap.parse_args()

    # FAIL-CLOSED : sans binaire de reference identifiable, on n'ecrit RIEN. Un TSV sans
    # provenance est un piege (cf. l'incident du 2026-07-25) — mieux vaut pas de fichier.
    try:
        dll = Path(args.dll) if args.dll else installed_dll()
        if not dll.is_file():
            raise ProvenanceError('binaire introuvable : %s' % dll)
        stamp = stamp_for(dll, source='il2cpp_full.json')
    except ProvenanceError as exc:
        print('REFUS : %s' % exc)
        print('  Aucun TSV ecrit (un TSV sans provenance est inutilisable en aval).')
        return 2

    # Un repertoire PAR BUILD, et une famille PAR PRODUCTEUR — la structure dit d'ou vient
    # chaque table, ce qui evite la confusion « les TSV nourrissent Frida » (ils n'alimentent
    # que Ghidra ; Frida est la SOURCE, pas un consommateur) :
    #   data/symbols/<HASH>/frida/{methods,classes,enums}.tsv   <- ici
    #   data/symbols/<HASH>/ghidra/functions.tsv                <- ghidra_symbols.py dump
    build = dll.parent.name
    out_dir = REPO / 'data' / 'symbols' / build / 'frida'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / 'BUILD').write_text(build + '\n', encoding='utf-8')

    print('provenance : build=%s' % build)
    print('             sha256=%s' % stamp.split('sha256=')[1].split('\t')[0])
    print('sortie     : %s' % out_dir.relative_to(REPO))

    with SRC.open(encoding='utf-8') as f:
        d = json.load(f)

    methods = d['methods']
    classes = d['classes']
    enums = d['enums']

    # --- methods.tsv ---
    with (out_dir / 'methods.tsv').open('w', encoding='utf-8') as f:
        f.write(stamp + '\n')
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
    with (out_dir / 'classes.tsv').open('w', encoding='utf-8') as f:
        f.write(stamp + '\n')
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
    with (out_dir / 'enums.tsv').open('w', encoding='utf-8') as f:
        f.write(stamp + '\n')
        for name, values in enums.items():
            v_str = ','.join(f'{v}={n}' for v, n in values.items())
            f.write(f'{name}\t{v_str}\n')
    print(f'Wrote {len(enums)} enums')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
