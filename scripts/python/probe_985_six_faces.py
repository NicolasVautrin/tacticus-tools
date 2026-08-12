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


#: Les 8 Machines of War SPAWNABLES du pool au rank courant (`rl_duel build --list-pool`).
#: Elles servent de temoin NON VIDE au discriminant ci-dessous.
MOW_POOL = ("adeptExorcist", "astraOrdnanceBattery", "blackForgefiend", "deathCrawler",
            "orksRukkatrukk", "tauBroadside", "tyranBiovore", "ultraDreadnought")


def machines() -> int:
    """Le discriminant MACHINE du gameconfig, MESURE -- substrat de `_is_machine` (1160).

    `EntityExtensions$$IsMachine` = `GetEntityType(entity) == EntityType.Machine (6)`, et ce type
    n'a AUCUN canal cote DECISION. Le port derive donc le predicat du seul champ qui separe les
    deux populations dans le gameconfig : `mythicAbilities`. Ce n'est utilisable QUE si la mesure
    montre 0 faux negatif sur les MoW confrontables -- sinon le port prendrait la branche DEGAT
    sur une Machine.
    """
    import gameconfig as GC
    champ = "mythicAbilities"
    lineup = GC._index()["lineup"]
    porte = lambda uid: champ in ((GC.unit(uid) or {}))          # noqa: E731
    pos = sorted([u for u in lineup if porte(u)])
    manques = [u for u in MOW_POOL if not porte(u)]
    print("[985] discriminant MACHINE : le champ `%s` du gameconfig" % champ)
    print("   lineup portant le champ : %d -> %s" % (len(pos), ", ".join(pos)))
    print("   MoW du pool spawnable   : %d" % len(MOW_POOL))
    print("   FAUX NEGATIFS (MoW du pool sans le champ) : %s" % (manques or "aucun"))
    print("   au-dela du pool         : %s"
          % (", ".join(u for u in pos if u not in MOW_POOL) or "aucun"))
    if manques:
        print("   -> INUTILISABLE : le port prendrait la branche DEGAT sur une Machine.")
        return 1
    if not pos:
        print("   -> temoin VIDE : un discriminant qui ne designe personne ne prouve rien.")
        return 1
    print("   -> UTILISABLE : 0 faux negatif, temoin non vide (%d designees)." % len(pos))
    return 0


def main() -> int:
    if "--machines" in sys.argv:
        return machines()
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
