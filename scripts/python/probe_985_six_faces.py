"""#985 -- passe les SIX dernieres faces DECISION par le recenseur `decision_face_voies`.

Avant Ghidra : le recenseur PARTITIONNE (il ne liste plus), et il porte l'etat ternaire
PORTEE / CONSTANTE / NON PORTEE. Un item retire ici avec sa voie est un resultat complet.

Sortie ASCII. Usage : depuis `scripts/python/`  ->  python probe_985_six_faces.py
"""
from __future__ import annotations

import os
import sys

_PYROOT = os.path.dirname(os.path.abspath(__file__))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import decision_face_voies as DFV

#: Les six items du lot, `(ActiveAbilityType, nom, porteur)`.
SIX = [
    (1026, "BasiliskBarrage", "astraOrdnance"),
    (1068, "SilentDeath", "eldarJainZar"),
    (1159, "MacroPlasmaIncinerator", "ultraDreadnought"),
    (1200, "SquigLaunchas", "orksRukkatrukk"),
    (1211, "RitesOfMorkai", "spaceWolfPriest"),
    (1160, "HeavyRailRifle", "tauBroadside"),
]


def main() -> int:
    tables = DFV.voies_par_ability()
    att = DFV.attestations()
    print("[985] les SIX faces DECISION, passees au recenseur #979")
    for aid, nom, porteur in SIX:
        st, detail = DFV.etat(aid, nom, tables, att)
        print("   %-5d %-24s %-18s %-12s %s" % (aid, nom, porteur, st, detail))
    print("\n[985] rappel : NON PORTEE = a lire au decompile ; PORTEE/CONSTANTE = retire du lot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
