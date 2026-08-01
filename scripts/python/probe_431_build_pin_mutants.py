#!/usr/bin/env python3
"""#431 -- META-contre-epreuve : `test_431_build_pin_offline.py` sait-il ROUGIR ?

POURQUOI CE PROBE EXISTE
------------------------
`test_431_build_pin_offline.py` est deja une contre-epreuve (il mute un fichier suivi et
exige que le cliquet rougisse). Mais un test de garde qui passe ne prouve pas qu'il MORD :
il pourrait passer parce qu'il n'eprouve rien. On casse donc les GARDES eux-memes, maillon
par maillon, et on exige que le fichier de test tombe a chaque fois.

    python probe_431_build_pin_mutants.py

rc 0 = tous les mutants TUES. rc 1 = au moins un GARDE-MUET (ou une mutation non appliquee).

⚠ VERT EST LE RESULTAT SUSPECT SUR UNE CONTRE-EPREUVE. Chaque mutation est donc verifiee en
deux temps -- compte d'occurrences EXACT avant ecriture, relecture disque + sha256 apres --
et un mutant qui n'a pas mordu sort en `MUTATION-NON-APPLIQUEE`, jamais confondu avec
`GARDE-MUET`. Restauration en `finally` + assertion d'empreinte : `git status` doit etre
inchange en sortie.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
CIBLE_TESTS = "tests/test_431_build_pin_offline.py"

# (fichier, motif EXACT attendu une seule fois, remplacement, ce qu'on casse)
MUTANTS = [
    ("probe_431_build_literals.py",
     '    if text.strip() == text[start:end]:\n        return "RESOLUTION"',
     '    if False:\n        return "RESOLUTION"',
     "M1 classement : une chaine qui EST un hash n'est plus une resolution"),
    ("probe_431_build_literals.py",
     '    if avant in SEPARATORS or apres in SEPARATORS:\n        return "RESOLUTION"',
     '    if False:\n        return "RESOLUTION"',
     "M2 classement : un segment de chemin n'est plus une resolution"),
    ("probe_431_build_literals.py",
     "        if id(node) in docs or id(node) in foyer:",
     "        if True:",
     "M3 balayage : plus aucune constante n'est examinee"),
    ("build_pin.py",
     "    if installed == versioned:\n        return",
     "    if True:\n        return",
     "M4 foyer : le double controle installe / data-symbols-CURRENT ne mord plus"),
    ("build_pin.py",
     "    if inst == pinned_build:\n        return inst",
     "    if True:\n        return inst",
     "M5 foyer : require_pinned accepte n'importe quel build"),
]


def _tests() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", CIBLE_TESTS, "-q", "--no-header", "-x"],
                       cwd=str(PYDIR), capture_output=True, text=True, timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, (out.strip().splitlines() or [""])[-1]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    print("=== temoin : arbre INTACT ===")
    rc, ligne = _tests()
    print("  rc=%d  %s" % (rc, ligne))
    if rc != 0:
        print("  l'arbre intact est DEJA rouge -- aucun mutant n'est interpretable")
        return 1

    verdicts = []
    for nom, motif, repl, label in MUTANTS:
        p = PYDIR / nom
        avant = p.read_text(encoding="utf-8")
        sha0 = _sha(p)
        n = avant.count(motif)
        if n != 1:
            print("  %-72s MUTATION-NON-APPLIQUEE (motif vu %d fois)" % (label[:72], n))
            verdicts.append((label, "MUTATION-NON-APPLIQUEE"))
            continue
        try:
            p.write_text(avant.replace(motif, repl), encoding="utf-8")
            relu = p.read_text(encoding="utf-8")
            if repl not in relu or _sha(p) == sha0:
                print("  %-72s MUTATION-NON-APPLIQUEE (disque inchange)" % label[:72])
                verdicts.append((label, "MUTATION-NON-APPLIQUEE"))
                continue
            rc, ligne = _tests()
            verdicts.append((label, "GARDE-MORD" if rc != 0 else "GARDE-MUET"))
            print("  %-72s rc=%d  %s" % (label[:72], rc, ligne[:50]))
        finally:
            p.write_text(avant, encoding="utf-8")
            if _sha(p) != sha0:
                print("  RESTAURATION RATEE sur %s -- verifier `git status`" % nom)
                return 1

    print("")
    print("=== verdicts ===")
    for label, v in verdicts:
        print("  %-22s %s" % (v, label))
    muets = [l for l, v in verdicts if v != "GARDE-MORD"]
    print("")
    print("tues : %d / %d" % (len(verdicts) - len(muets), len(verdicts)))
    return 0 if not muets else 1


if __name__ == "__main__":
    raise SystemExit(main())
