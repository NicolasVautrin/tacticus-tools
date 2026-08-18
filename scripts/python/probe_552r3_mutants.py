"""CONTRE-EPREUVE de `probe_552r3_slot4_declare` : le critere METADATA doit rougir quand il ment.

Le verdict de `#552-r3` (<< `MindControlPlaybook` ne surcharge PAS le slot 4 >>) repose entierement
sur une VOIE NEUVE : lire les methodes DECLAREES dans `global-metadata.dat` plutot que les tables
de symboles indexees par ADRESSE. Une voie neuve dont on n'a pas montre qu'elle peut RENDRE FAUX
n'est pas une mesure -- c'est une affirmation. Trois mutants, et le troisieme est le plus
important :

  MA  `noms_declares` rend toujours un ensemble SANS `ShouldEvaluate`   -> etage 1
      (le critere aveugle qui donnerait la MEME reponse pour MindControl, et serait faux)
  MB  `noms_declares` rend toujours un ensemble AVEC `ShouldEvaluate`   -> etages 1 et 2
      (l'aveuglement symetrique)
  MC  le temoin devient UNILATERAL (les 4 non-surchargeants retires)    -> etage 1
      (le regime DEGENERE : quatre accords tous du meme cote ne discriminent RIEN, et c'est
       exactement le controle qu'un relecteur presse supprimerait pour << alleger >>)

Sortie ASCII (cp1252). Le fichier mute est RESTAURE dans un `finally`.

Usage:
    python probe_552r3_mutants.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
CIBLE = "probe_552r3_slot4_declare.py"

MUTANTS = (
    ("MA le critere rend toujours SANS ShouldEvaluate", CIBLE,
     "    return {m.name for m in tbl} or None",
     "    return ({m.name for m in tbl} - {\"ShouldEvaluate\"}) or None  # MUTANT"),

    ("MB le critere rend toujours AVEC ShouldEvaluate", CIBLE,
     "    return {m.name for m in tbl} or None",
     "    return ({m.name for m in tbl} | {\"ShouldEvaluate\"}) or None  # MUTANT"),

    # ⚠ Le mutant COUPE la liste apres les quatre surchargeants (les quatre autres passent dans un
    #   tuple mort). Il ne RENOMME rien : une classe inconnue ferait rendre `PAS MESURE` (rc 2) au
    #   probe -- un capteur casse, pas une morsure, et le mutant ne testerait plus le controle vise.
    ("MC le temoin devient UNILATERAL (4 surchargeants, 0 non)", CIBLE,
     "    (\"EuphoricStrikesPlaybook\", False, False,",
     ")\n_TEMOINS_MORTS = (\n    (\"EuphoricStrikesPlaybook\", False, False,"),
)


def _jouer():
    r = subprocess.run([sys.executable, CIBLE], cwd=ICI, capture_output=True, text=True)
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
        # rc 2 = PAS MESURE : ce n'est PAS une morsure, c'est un capteur casse. On le DIT.
        etat = "MORD" if rc == 1 else ("INERTE" if rc == 0 else "PAS MESURE (rc=%d)" % rc)
        print("%-58s rc=%d  %s" % (libelle, rc, etat))
        if rc != 1:
            inertes.append("%s [%s]" % (libelle, etat))

    apres_base = _jouer()
    print("RESTAURATION : rc=%d  %s" % (apres_base, "OK" if apres_base == 0 else "KO"))
    if inertes:
        print("\nMUTANTS QUI NE MORDENT PAS (%d) :" % len(inertes))
        for m in inertes:
            print("  " + m)
        return 1
    if apres_base != 0:
        return 1
    print("\nOK : %d/%d mutants mordent." % (len(MUTANTS), len(MUTANTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
