"""Extract `TIMEOUT/NULL` markers from decompiled_tacticus/*.c into a TSV suitable
for a second Ghidra pass (same format as all_battlelogic_targets.tsv):
  top_class_fs_path \t method_full_name \t rva_hex

ENTREE `data/decompiled_tacticus/` : artefact du pipeline Ghidra hors-ligne, ni
versionne ni produit ici -> resolu par `host_inputs` (tri-etat #273). Sans lui,
`os.walk` sur un chemin absent rend ZERO fichier SANS lever, et ce script
ecrivait un TSV VIDE qui se lit comme « plus aucune cible en echec » (#314).

SORTIE -> `logs/ghidra/failed_targets.tsv`, RELATIF au checkout : `data/` est le
repertoire des ENTREES versionnees, et un chemin absolu ferait ecrire ce script
dans l'arbre principal depuis n'importe quel worktree d'agent.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_inputs  # noqa: E402

ROOT = host_inputs.require('data/decompiled_tacticus').as_posix() + '/'
OUT = Path(__file__).resolve().parents[2] / 'logs' / 'ghidra' / 'failed_targets.tsv'

pairs = {}
pattern = re.compile(r'// === (.+?) \(RVA: (0x[0-9A-Fa-f]+)\) === TIMEOUT/NULL')

for root, dirs, files in os.walk(ROOT):
    for f in files:
        if not f.endswith('.c'):
            continue
        full = os.path.join(root, f).replace(os.sep, '/')
        with open(full, 'r', encoding='utf-8', errors='replace') as fp:
            text = fp.read()
        rel = full.replace(ROOT, '').removesuffix('.c')
        for m in pattern.finditer(text):
            rva = int(m.group(2), 16)
            pairs[rva] = (m.group(1), rel)

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    for rva, (name, path) in sorted(pairs.items()):
        f.write(f'{path}\t{name}\t{rva:x}\n')

print(f'Wrote {len(pairs)} failed targets to {OUT.as_posix()}')
for rva, (name, path) in list(sorted(pairs.items()))[:5]:
    print(f'  {path}  {name}  0x{rva:x}')
