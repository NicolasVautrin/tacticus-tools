#!/usr/bin/env python
"""#418 / #411-r3 -- CONTRE-EPREUVES du port de `1511 PrimarchOfTheFirstLegion`.

Un test vert ne prouve rien tant qu'on n'a pas montre qu'il sait ROUGIR. Ce probe mute le PORT,
une propriete a la fois, rejoue les deux fichiers de garde, et exige un rouge a chaque fois.

Les six mutations visent chacune une lecture de la RE, et **M1 est celle qui compte** : c'est
exactement la faute que #411 avait refuse de commettre a l'aveugle (« le porter sans cette lecture
donnerait un port au flux RNG faux -- c'est-a-dire pire que pas de port »). Un court-circuit du
`Randomize` rend LA BONNE CIBLE et decale tout le flux aleatoire en aval : aucune valeur mesuree ne
le trahit, seul un ledger le voit.

⚠ Une ancre introuvable est traitee comme un ECHEC, pas comme un vert : une mutation qui ne
s'applique pas laisse l'arbre SAIN, et le vert qui suit ne prouve rien (piege deja paye ailleurs
dans le depot -- « verifier que la MUTATION a mordu »).

Usage :  python scripts/python/probe_418_mutants.py        (depuis n'importe ou)

RE : `docs/rl/case-411-r3-primarch-of-the-first-legion.md`.

ASCII only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
GEO = PYDIR / "engine" / "entities" / "selectors" / "geometry.py"
UNITS = PYDIR / "engine" / "entities" / "selectors" / "units.py"
PFL = PYDIR / "engine" / "runner" / "operations" / "triggers" / "loki" / "primarch_first_legion.py"

TESTS = ["tests/engine/test_418_primarch_transfer_offline.py",
         "tests/engine/test_411_transfer_hit_wiring_offline.py"]

MUTANTS = [
    ("M1 court-circuit du Randomize", GEO,
     "        return f(pool, n, self.allow_duplicates, self.max_duplicates)",
     "        return list(pool)[:n] if len(pool) <= n else "
     "f(pool, n, self.allow_duplicates, self.max_duplicates)"),
    ("M2 filtre de faction retire", UNITS,
     "        return [u for u in self.source.evaluate(ctx) if fo(u) == self.faction]",
     "        return list(self.source.evaluate(ctx))"),
    ("M3 gate de parite retire", PFL,
     "        if int(hit_index) % 2 == 0:                       # AmountIsOdd(CurrentHitIndex)\n"
     "            return False",
     "        if False:                                         # AmountIsOdd(CurrentHitIndex)\n"
     "            return False"),
    ("M4 anti-repetition retiree", PFL,
     "    rank = FIf(Contains(already, it), Const(0), Const(1))",
     "    rank = Const(1)"),
    ("M5 Cache retire", PFL,
     "    return Cache(First(SortByFormula(shuffled, rank, ascending=False)))",
     "    return First(SortByFormula(shuffled, rank, ascending=False))"),
    ("M6 tri ASCENDANT (polarite inversee)", PFL,
     "    return Cache(First(SortByFormula(shuffled, rank, ascending=False)))",
     "    return Cache(First(SortByFormula(shuffled, rank, ascending=True)))"),
]


def _run() -> tuple:
    p = subprocess.run([sys.executable, "-m", "pytest"] + TESTS + ["-q", "--no-header"],
                       cwd=str(PYDIR), capture_output=True, text=True)
    tail = [ln for ln in p.stdout.splitlines() if " passed" in ln or " failed" in ln]
    return p.returncode, (tail[-1] if tail else p.stdout[-200:].replace("\n", " "))


def main() -> int:
    rc, base = _run()
    print("[base] rc=%d  %s" % (rc, base))
    if rc != 0:
        print("ARBRE NON MUTE DEJA ROUGE -- ce probe ne peut RIEN conclure.")
        return 1
    survivants = []
    for name, path, old, new in MUTANTS:
        src = path.read_text(encoding="utf-8")
        if src.count(old) != 1:
            print("[%-38s] ANCRE INTROUVABLE (%d occurrences) -- mutation NON APPLIQUEE"
                  % (name, src.count(old)))
            survivants.append(name)
            continue
        path.write_text(src.replace(old, new), encoding="utf-8")
        try:
            rc2, line = _run()
        finally:
            path.write_text(src, encoding="utf-8")       # restauration INCONDITIONNELLE
        print("[%-38s] rc=%d  %s" % (name, rc2, line))
        if rc2 == 0:
            survivants.append(name)
    rc3, again = _run()
    print("[restaure] rc=%d  %s" % (rc3, again))
    if rc3 != 0:
        print("L'ARBRE N'EST PAS REVENU A SON ETAT SAIN -- verifier avant tout commit.")
        return 1
    if survivants:
        print("MUTANTS SURVIVANTS : %s" % survivants)
        return 1
    print("OK -- %d mutations, %d tuees." % (len(MUTANTS), len(MUTANTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
