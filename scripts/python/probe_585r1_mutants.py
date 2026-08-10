"""CONTRE-EPREUVE du cliquet #585-r1 : chaque mutant DOIT faire rougir le test.

Un cliquet vert ne prouve rien tant qu'on n'a pas montre qu'il rougit sur la faute qu'il pretend
interdire. Trois mutants, chacun vise un etage DIFFERENT :

  M1  un littéral RETIRE d'un call-site         -> etages 1 et 4 (degradation permissive)
  M2  le contre-exemple `Any` reecrit en `3`    -> etage 1 (la faute exacte que la fiche annoncait)
  M3  le contre-exemple RETIRE de la table      -> etage 1b (releve devenu degenere)

Sortie ASCII (cp1252). Le fichier mute est RESTAURE dans un `finally`.

Usage:
    python probe_585r1_mutants.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
CIBLE = os.path.join("tests", "engine", "runner", "test_585r1_selection_type_releve_offline.py")

MUTANTS = (
    ("M1 un littéral RETIRE (`plagueburst_adjacent_enemies`)",
     os.path.join("engine", "runner", "abilities", "deathguard.py"),
     "return Enemies(Units(AdjacentTiles(target_sel), selection_type=SELECTION),\n"
     "                   selection_type=SELECTION)",
     "return Enemies(Units(AdjacentTiles(target_sel)))"),
    ("M2 le contre-exemple `Any` reecrit en `3` (ResurrectionOrb)",
     os.path.join("engine", "runner", "abilities", "necrons.py"),
     "selection_type=int(UnitSelectionType.Any)),",
     "selection_type=SELECTION),"),
    ("M3 le contre-exemple RETIRE de la table du cliquet",
     CIBLE,
     '    ("ResurrectionOrbAbility$$GetPossibleResurrectTargets / Friends",\n'
     '     _resurrection_orb, ("source", "selection_type"), _ANY),',
     ""),
)


def _jouer():
    r = subprocess.run([sys.executable, "-m", "pytest", CIBLE, "-q"],
                       cwd=ICI, capture_output=True, text=True)
    return r.returncode


def main():
    base = _jouer()
    print("BASE (aucun mutant) : rc=%d  %s" % (base, "OK" if base == 0 else "KO -- ARRET"))
    if base != 0:
        return 1

    inertes = []
    for libelle, rel, avant, apres in MUTANTS:
        chemin = os.path.join(ICI, rel)
        with open(chemin, "r", encoding="utf-8") as fh:
            src = fh.read()
        if avant not in src:
            print("%-58s MUTATION NON APPLIQUEE (motif absent)" % libelle)
            inertes.append(libelle + " [motif absent -- le mutant ne teste RIEN]")
            continue
        try:
            with open(chemin, "w", encoding="utf-8") as fh:
                fh.write(src.replace(avant, apres, 1))
            rc = _jouer()
        finally:
            with open(chemin, "w", encoding="utf-8") as fh:
                fh.write(src)
        print("%-58s rc=%d  %s" % (libelle, rc, "MORD" if rc != 0 else "INERTE"))
        if rc == 0:
            inertes.append(libelle)

    apres_base = _jouer()
    print("RESTAURATION : rc=%d  %s" % (apres_base, "OK" if apres_base == 0 else "KO"))
    if inertes:
        print("\nMUTANTS INERTES (%d) -- le cliquet ne garde PAS ce qu'il pretend :" % len(inertes))
        for m in inertes:
            print("  " + m)
        return 1
    if apres_base != 0:
        return 1
    print("\nOK : %d/%d mutants mordent." % (len(MUTANTS), len(MUTANTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
