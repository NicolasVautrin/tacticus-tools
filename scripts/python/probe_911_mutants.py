#!/usr/bin/env python
"""probe #911 (matrice de MUTANTS) -- chaque cran du port de `1203 DaemonicPatrons` MORD-il ?

Un probe VERT ne prouve rien tant qu'on n'a pas montre qu'il ROUGIT quand on casse ce qu'il est
cense garder. Ce fichier applique, UN PAR UN, un mutant textuel au code PORTE, rejoue
`probe_911_daemonic_patrons.py`, et exige un **FAIL**. Le fichier est TOUJOURS restaure (`finally`).

MUTANTS
-------
  M1  le `Filter(..., HasEffect(It, 27))` du selecteur est COLLAPSE -> `n` compte TOUS les ennemis
      adjacents. Doit faire rougir E2 (1 vs 2) ET les deux canaux de degat.
  M2  le signe de la reduction est INVERSE (`+reduction` au lieu de `-reduction`) -- c'est la
      lecture du slot `+0x08` a montant NEGATIF. Doit faire rougir E2b et E4.
  M3  le `Min(Const(100), .)` est RETIRE. Doit faire rougir E2b (n = 4 -> -120 au lieu de -100).
  M4  la duree passe par `duration_rounds` au lieu de `duration_turns` -> le `Const(1)` de
      `Sum(TurnsFromRounds(n), Const(1))` est perdu ET la valeur est re-convertie. Doit faire
      rougir E1.
  M5  le facteur `x n` de l'extra-damage est retire (`v` seul). AVEUGLE en live (`n = 1` y rend le
      MEME nombre) -- c'est exactement pour lui que l'etage E2b existe, et c'est E2b qui le tue.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_911_mutants.py
    python probe_911_mutants.py --seul M3
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

PYDIR = os.path.dirname(os.path.abspath(__file__))
EFFETS = os.path.join(PYDIR, "engine", "entities", "effects", "loki", "daemonic_patrons.py")
ABILITY = os.path.join(PYDIR, "engine", "runner", "abilities", "emperorschildren.py")

MUTANTS = {
    "M1": (EFFETS,
           "    return Count(Filter(AdjacentEnemies(Owner(), Const(1)),\n"
           "                        HasEffect(Subject(), DP_TAUNTED, active_only=False)))",
           "    return Count(AdjacentEnemies(Owner(), Const(1)))"),
    "M2": (EFFETS,
           "        return for_percent_increase(False, -reduction)",
           "        return for_percent_increase(False, reduction)"),
    "M3": (EFFETS,
           "        reduction = min(DP_REDUCTION_CAP, int(pct) * int(n))",
           "        reduction = int(pct) * int(n)"),
    "M4": (ABILITY,
           "    extra = AddEffect(DP_EXTRA_DAMAGE, EffectType.DaemonicPatrons_ExtraDamage.name, Owner(),\n"
           "                      duration_rounds=None, duration_turns=duration_turns,",
           "    extra = AddEffect(DP_EXTRA_DAMAGE, EffectType.DaemonicPatrons_ExtraDamage.name, Owner(),\n"
           "                      duration_rounds=duration_turns, duration_turns=None,"),
    "M5": (EFFETS,
           "        return for_addition(True, int(v) * int(n))",
           "        return for_addition(True, int(v))"),
}


def joue() -> int:
    p = subprocess.run([sys.executable, "probe_911_daemonic_patrons.py"], cwd=PYDIR,
                       capture_output=True, text=True, timeout=900)
    for l in (p.stdout or "").splitlines():
        if l.startswith("[E") or l.startswith("[temoin") or l.startswith("[911]"):
            print("     " + l)
    return p.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seul", default=None)
    a = ap.parse_args()
    noms = [a.seul] if a.seul else sorted(MUTANTS)
    bilan = {}
    for nom in noms:
        chemin, avant, apres = MUTANTS[nom]
        with open(chemin, "r", encoding="utf-8") as f:
            src = f.read()
        if src.count(avant) != 1:
            print("[%s] ANCRE INTROUVABLE (%d occurrences) -- mutant NON JOUE" % (nom, src.count(avant)))
            bilan[nom] = "ANCRE"
            continue
        print("[%s] applique" % nom)
        try:
            with open(chemin, "w", encoding="utf-8", newline="") as f:
                f.write(src.replace(avant, apres))
            rc = joue()
            bilan[nom] = "MORD" if rc != 0 else "AVEUGLE"
            print("[%s] rc=%s -> %s" % (nom, rc, bilan[nom]))
        finally:
            with open(chemin, "w", encoding="utf-8", newline="") as f:
                f.write(src)
    print("\n[mutants] %s" % bilan)
    aveugles = [k for k, v in bilan.items() if v != "MORD"]
    print("[mutants] %s" % ("TOUS MORDENT" if not aveugles else "AVEUGLES : %s" % aveugles))
    return 0 if not aveugles else 1


if __name__ == "__main__":
    raise SystemExit(main())
