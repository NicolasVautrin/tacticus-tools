"""CONTRE-EPREUVE du cliquet #10037 : chaque mutant DOIT faire rougir le test.

Un cliquet vert ne prouve rien tant qu'on n'a pas montre qu'il rougit sur la faute qu'il pretend
interdire. HUIT mutants, un par lecture gardee -- et chacun est la faute PLAUSIBLE, pas une
absurdite (un mutant qu'on n'aurait jamais ecrit ne mesure rien) :

  M1  `EarlyWarningOverride.MIN_UTILITY` revient a `1.0`            -> etages 1 et 1b
      (c'est LITTERALEMENT l'etat d'avant cette tranche)
  M2  le gate2 d'`HeroicFusillade` repasse par `count_adjacent`      -> etage 2
      (c'est la << reparation >> que le residu demandait, et elle est FAUSSE)
  M3  `tiles_in_native_order` degenere en l'ordre de l'UNION         -> etages 3d et 3f
      (l'etat d'avant #971, celui qui avait rendu 11 classes natives contre 10 portees)
  M4  `MasterOfTheTutelaries` cesse d'emprunter le foyer d'ordre     -> etage 3
  M5  `CallRipperSwarms.use_probability` rabat le non-mesure sur 0   -> etage 5c
      (la faute de tri-etat la plus courante : un defaut qui PRONONCE un refus)
  M6  `filter_movement_tiles` perd son ANTI-VIDAGE                   -> etage 6e
  M7  le rayon du filtre passe de 2 a 3                              -> etage 6c
  M8  le palier de `WarHowl` est INTERPOLE (`n == 2 -> 62`)          -> etage 7
      (la << correction >> tentante d'un palier non monotone)

Sortie ASCII (cp1252). Chaque fichier mute est RESTAURE dans un `finally`.

Usage:
    python probe_10037_mutants.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
CIBLE = os.path.join("tests", "engine", "playbook",
                     "test_10037_playbooks_noncomparable_offline.py")

EWO = os.path.join("engine", "playbook", "noncomparable", "early_warning_override.py")
HF = os.path.join("engine", "playbook", "noncomparable", "heroic_fusillade.py")
BASE = os.path.join("engine", "playbook", "noncomparable", "_base.py")
MOT = os.path.join("engine", "playbook", "noncomparable", "master_of_the_tutelaries.py")
CRS = os.path.join("engine", "playbook", "noncomparable", "call_ripper_swarms.py")
SP = os.path.join("engine", "playbook", "savior_protocols.py")
WH = os.path.join("engine", "playbook", "noncomparable", "war_howl.py")

MUTANTS = (
    ("M1 EarlyWarningOverride.MIN_UTILITY revient a 1.0", EWO,
     '    MIN_UTILITY = float("-inf")\n    PRIORITY = 0',
     '    MIN_UTILITY = 1.0\n    PRIORITY = 0'),

    ("M2 HeroicFusillade repasse par count_adjacent", HF,
     "            if not any(hexgeo.distance(tpos, e) <= self._SPLASH_RADIUS for e in others):",
     "            from engine import battle_query as bq\n"
     "            if bq.count_adjacent(tpos, others) < 1:"),

    ("M3 tiles_in_native_order degenere en l'ordre de l'UNION", BASE,
     "    ordered = [p for p in ((q[0], q[1]) for q in ring) if p in eligibles]\n"
     "    reste = [p for p in union if p in eligibles and p not in ordered]\n"
     "    return ordered + reste",
     "    return list(union)"),

    ("M4 MasterOfTheTutelaries n'emprunte plus le foyer d'ordre", MOT,
     "            for ST in tiles_in_native_order(ctx, T, from_here, union, eligibles):",
     "            for ST in spawn_tiles:"),

    ("M5 CallRipperSwarms rabat le non-mesure sur 0.0", CRS,
     "        if n is None or mx is None:\n            return None",
     "        if n is None or mx is None:\n            return 0.0"),

    ("M6 filter_movement_tiles perd son ANTI-VIDAGE", SP,
     "        return garde if garde else tiles",
     "        return garde"),

    ("M7 le rayon du filtre passe de 2 a 3", SP,
     "_FILTER_RADIUS = 2",
     "_FILTER_RADIUS = 3"),

    ("M8 le palier de WarHowl est INTERPOLE (n == 2 -> 62)", WH,
     "_PCT_AUTRE = 50",
     "_PCT_AUTRE = 62"),
)


def _jouer():
    r = subprocess.run([sys.executable, "-m", "pytest", CIBLE, "-q", "-p", "no:randomly"],
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
