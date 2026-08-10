"""CONTRE-EPREUVE du cliquet #585-r1 : chaque mutant DOIT faire rougir le test.

Un cliquet vert ne prouve rien tant qu'on n'a pas montre qu'il rougit sur la faute qu'il pretend
interdire. Trois mutants, chacun vise un etage DIFFERENT :

  M1  un littéral RETIRE d'un call-site         -> etages 1 et 4 (degradation permissive)
  M2  un contre-exemple `Any` reecrit en `3`    -> etage 1 (la faute exacte que la fiche annoncait)
  M3  TOUS les contre-exemples hors de la table -> etage 1b (releve devenu degenere)
  M4  le second contre-exemple reecrit en `3`   -> etage 1 (`Foehammer`, seconde passe)

⚠ M3 A DU ETRE ELARGI, et c'est une mesure, pas un ajustement de confort. Tant que la table ne
portait QU'UN contre-exemple, en retirer un suffisait a la rendre degeneree. La seconde passe du
releve en a ajoute DEUX autres (`UnbreakableDuty`, `Foehammer` -- meme cause : la source est un
ensemble de MORTS), donc retirer le seul `ResurrectionOrb` laissait `test_etage1b` VERT : le
mutant etait devenu INERTE en silence. Un probe de contre-epreuve se perime avec le corpus qu'il
garde -- c'est ce qui rend son re-jeu obligatoire apres toute extension.

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

#: chaque mutant = (libelle, fichier, [(avant, apres), ...]) -- une LISTE de substitutions, parce
#: qu'un corpus a plusieurs contre-exemples ne se degenere qu'en les retirant TOUS.
MUTANTS = (
    ("M1 un littéral RETIRE (`plagueburst_adjacent_enemies`)",
     os.path.join("engine", "runner", "abilities", "deathguard.py"),
     [("return Enemies(Units(AdjacentTiles(target_sel), selection_type=SELECTION),\n"
       "                   selection_type=SELECTION)",
       "return Enemies(Units(AdjacentTiles(target_sel)))")]),
    ("M2 le contre-exemple `Any` reecrit en `3` (ResurrectionOrb)",
     os.path.join("engine", "runner", "abilities", "necrons.py"),
     [("selection_type=int(UnitSelectionType.Any)),", "selection_type=SELECTION),")]),
    ("M3 les TROIS contre-exemples hors de la table du cliquet",
     CIBLE,
     [('    ("ResurrectionOrbAbility$$GetPossibleResurrectTargets / Friends",\n'
       '     _resurrection_orb, ("source", "selection_type"), _ANY),', ""),
      ('    ("UnbreakableDutyAbility$$GetAmountOfDeadImperialUnits / Friends",\n'
       '     _unbreakable_dead, ("a", "a", "selection_type"), _ANY),', ""),
      ('    ("UnbreakableDutyAbility$$GetAmountOfDeadImperialUnits / UnitsWithTraits",\n'
       '     _unbreakable_dead, ("b", "selection_type"), _ANY),', ""),
      ('    ("FoehammerAbility$$GetDeadHeroes / UnitsWithTrait",\n'
       '     _foehammer_dead, ("selection_type",), _ANY),', "")]),
    ("M4 le contre-exemple `Any` reecrit en `3` (Foehammer)",
     os.path.join("engine", "runner", "abilities", "spacewolves.py"),
     [("return UnitsWithTrait(AllDeadOrResurrectedUnits(), HERO_TRAIT,\n"
       "                          selection_type=int(UnitSelectionType.Any))",
       "return UnitsWithTrait(AllDeadOrResurrectedUnits(), HERO_TRAIT,\n"
       "                          selection_type=SELECTION)")]),
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
    for libelle, rel, substitutions in MUTANTS:
        chemin = os.path.join(ICI, rel)
        with open(chemin, "r", encoding="utf-8") as fh:
            src = fh.read()
        absents = [a for a, _b in substitutions if a not in src]
        if absents:
            print("%-58s MUTATION NON APPLIQUEE (%d motif(s) absent(s))" % (libelle, len(absents)))
            inertes.append(libelle + " [motif absent -- le mutant ne teste RIEN]")
            continue
        mute = src
        for avant, apres in substitutions:
            mute = mute.replace(avant, apres, 1)
        try:
            with open(chemin, "w", encoding="utf-8") as fh:
                fh.write(mute)
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
