#!/usr/bin/env python3
"""Extracteur JETABLE : imprime les sous-arbres HORS PERIMETRE du bloc 1 deja captures.

    python probe_477r21r1_extraire_hors.py logs/477r21-C1_02-natif-bloc1.txt

Il ne mesure RIEN -- il relit un fichier ecrit par `probe_477r21_activation_tree.py` et
imprime, tel quel, ce que sa partition a mis de cote. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r21_activation_tree as R21  # noqa: E402


def main() -> int:
    chemin = Path(sys.argv[1])
    bloc1 = [l for l in chemin.read_text(encoding="utf-8").split("\n") if l != ""]
    par = R21.parser_bloc1(bloc1)
    print("PORTES=%d lignes  HORS=%d lignes" % (par["lignes_portees"], par["lignes_hors"]))
    for k, h in enumerate(par["hors"]):
        print("")
        print("--- HORS #%d (%d lignes) : %s" % (k, h["lignes"], h["raison"]))
        for l in h["texte"]:
            print(l)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
