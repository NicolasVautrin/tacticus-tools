"""CONTRE-EPREUVE du cliquet `#552-r4` (volet livre) : chaque mutant DOIT faire rougir le test.

Le gate slot-4 de `1192 NovaBoost` / `1194 NovaShield` est un gate AMONT dont l'absence est
PERMISSIVE : elle ne leve rien, elle fait seulement caster une fois de trop. Un cliquet qui
garderait cela doit donc etre montre MORDANT, sinon il n'est qu'un inventaire.

  M1  le gate de `NovaShield` est retire                       -> etages 1 et 2
      (c'est LITTERALEMENT l'etat d'avant cette tranche)
  M2  le gate de `NovaBoost` est retire                        -> etages 1 et 2
  M3  le litteral `2` de `NovaBoost` devient `1`               -> etages 2 et 4
      (l'<< arrondi >> d'un litteral lu au decompile)
  M4  le gate de `NovaShield` REFUSE quand le canal est muet   -> etage 3
      (la faute de tri-etat la plus courante : un defaut qui PRONONCE un refus)
  M5  `NovaBoost` surcharge `use_probability` au lieu du slot 4 -> etage 1
      (la faute que le foyer `NonComparablePlaybook.should_evaluate` invite a commettre : sa
       prescription vise les PROBABILITES, pas les surcharges de vtable)

Sortie ASCII (cp1252). Chaque fichier mute est RESTAURE dans un `finally`.

Usage:
    python probe_552r4_mutants.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
CIBLE = os.path.join("tests", "engine", "playbook",
                     "test_552r4_gate_nova_remaining_turns_offline.py")

NB = os.path.join("engine", "playbook", "noncomparable", "nova_boost.py")
NS = os.path.join("engine", "playbook", "noncomparable", "nova_shield.py")

_GATE = ("        if not has_minimum_remaining_turns(ctx, _MIN_REMAINING_TURNS):\n"
         "            return False\n")

MUTANTS = (
    ("M1 le gate de NovaShield est retire", NS, _GATE, ""),
    ("M2 le gate de NovaBoost est retire", NB, _GATE, ""),
    ("M3 le litteral 2 de NovaBoost devient 1", NB,
     "_MIN_REMAINING_TURNS = 2", "_MIN_REMAINING_TURNS = 1"),
    ("M4 le gate de NovaShield refuse quand le canal est muet", NS,
     "        if not has_minimum_remaining_turns(ctx, _MIN_REMAINING_TURNS):",
     "        if getattr(ctx, 'victory_conditions', None) is None or "
     "not has_minimum_remaining_turns(ctx, _MIN_REMAINING_TURNS):"),
    ("M5 NovaBoost surcharge use_probability au lieu du slot 4", NB,
     "    def should_evaluate(self, ctx: NCContext) -> bool:",
     "    def use_probability(self, ctx: NCContext):\n"
     "        return 1.0 if has_minimum_remaining_turns(ctx, _MIN_REMAINING_TURNS) else 0.0\n\n"
     "    def _should_evaluate_MUTANT(self, ctx: NCContext) -> bool:"),
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
