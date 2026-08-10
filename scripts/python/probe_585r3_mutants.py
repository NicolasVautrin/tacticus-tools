"""CONTRE-EPREUVE du cliquet #585-r3 : chaque mutant DOIT faire rougir le test.

Un cliquet vert ne prouve rien tant qu'on n'a pas montre qu'il rougit sur la faute qu'il pretend
interdire. Quatre mutants, chacun vise un etage DIFFERENT de
`tests/engine/runner/test_585r3_etage_amont_selection_type_offline.py` :

  M1  le parametre est STOCKE mais plus LU (`AdjacentUnits.select`)   -> etage 3 (le << mord >>)
  M2  le defaut passe de `None` a `3` (`SurroundingUnits`)            -> etages 1b et 2
  M3  `selection_type` insere AVANT `reference` (`AdjacentFriends`)   -> etage 1 (la POSITION)
  M4  le filtre retire du corps d'`UnitsFromFaction`                  -> etage 3

M1 et M4 sont les deux formes du meme vice -- un parametre decoratif -- et c'est justement celui
qu'une introspection de signature ne peut PAS voir. M3 est la regression d'ORDRE : elle laisse tous
les call-sites en mot-cle intacts, donc elle ne se voit qu'en lisant la signature.

Sortie ASCII (cp1252). Le fichier mute est RESTAURE dans un `finally`.

Usage:
    python probe_585r3_mutants.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
CIBLE = os.path.join("tests", "engine", "runner",
                     "test_585r3_etage_amont_selection_type_offline.py")
UNITS = os.path.join("engine", "entities", "selectors", "units.py")

MUTANTS = (
    ("M1 parametre STOCKE mais plus LU (AdjacentUnits)", UNITS,
     "        st = self.selection_type\n"
     "        return out if st is None else [u for u in out if _selection_ok(u, st, ctx)]\n"
     "\n"
     "\nclass Enemies(TargetsSelector):",
     "        return out\n"
     "\n"
     "\nclass Enemies(TargetsSelector):"),
    ("M2 defaut `None` -> `3` (SurroundingUnits)", UNITS,
     "    def __init__(self, center: TargetsSelector, radius: TargetsSelector, include_center: bool = False,\n"
     "                 selection_type=None):",
     "    def __init__(self, center: TargetsSelector, radius: TargetsSelector, include_center: bool = False,\n"
     "                 selection_type=3):"),
    ("M3 `selection_type` insere AVANT `reference` (AdjacentFriends)", UNITS,
     "    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None,\n"
     "                 reference: TargetsSelector | None = None, selection_type=None):\n"
     "        self.center, self.radius = center, radius or Const(1)\n"
     "        self.reference = reference",
     "    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None,\n"
     "                 selection_type=None, reference: TargetsSelector | None = None):\n"
     "        self.center, self.radius = center, radius or Const(1)\n"
     "        self.reference = reference"),
    ("M4 filtre retire du corps (UnitsFromFaction)", UNITS,
     "        st = self.selection_type\n"
     "        return [u for u in self.source.evaluate(ctx)\n"
     "                if (st is None or _selection_ok(u, st, ctx)) and fo(u) == self.faction]",
     "        return [u for u in self.source.evaluate(ctx) if fo(u) == self.faction]"),
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
            with open(chemin, "w", encoding="utf-8", newline="") as fh:
                fh.write(src.replace(avant, apres, 1))
            rc = _jouer()
        finally:
            with open(chemin, "w", encoding="utf-8", newline="") as fh:
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
