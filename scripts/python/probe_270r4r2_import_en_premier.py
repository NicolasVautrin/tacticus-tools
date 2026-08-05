"""#270-r4-r2 -- Un cycle ne se voit QUE dans UN SENS : ce probe importe chaque module
d'`engine/` EN PREMIER, dans un interpreteur FRAIS, et rapporte les `ImportError`.

C'est la mesure MATERIELLE que le calcul de SCC (`probe_270r4r2_cycles_imports.py`) ne
donne pas : un graphe acyclique dans le modele « source declaree » n'exclut pas qu'un
import reel echoue (les paquets ANCETRES sont traverses, eux, quoi qu'on ecrive).

Par defaut, il balaye les modules des PAQUETS touches par la coupe. `--tous` balaye les
408 (lent : un interpreteur par module). `--modules a,b` cible une liste.

Usage :
    python probe_270r4r2_import_en_premier.py
    python probe_270r4r2_import_en_premier.py --tous
    python probe_270r4r2_import_en_premier.py --modules engine.services.static_battle_rules
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RACINE = Path(__file__).resolve().parent
# Paquets dont la coupe #270-r4-r2 a change les imports, PLUS ceux qui les consomment
# de pres (le sens d'entree compte : un cycle ne se voit que d'un cote).
PAQUETS_DEFAUT = ("engine.services", "engine.playbook", "engine.entities", "engine.dsl")


def _modules_sous(prefixes: tuple[str, ...]) -> list[str]:
    out = []
    for f in sorted((RACINE / "engine").rglob("*.py")):
        parts = list(f.relative_to(RACINE).parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]
        nom = ".".join(parts)
        if any(nom == p or nom.startswith(p + ".") for p in prefixes):
            out.append(nom)
    return out


def _essayer(mod: str) -> tuple[str, int, str]:
    r = subprocess.run([sys.executable, "-c", "import %s" % mod],
                       cwd=str(RACINE), capture_output=True, text=True, timeout=180)
    err = ""
    if r.returncode != 0:
        lignes = [l for l in (r.stderr or "").strip().splitlines() if l.strip()]
        err = lignes[-1] if lignes else "(stderr vide)"
    return mod, r.returncode, err


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tous", action="store_true", help="les 408 modules d'engine/")
    ap.add_argument("--modules", default="", help="liste separee par des virgules")
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    if args.modules:
        mods = [m.strip() for m in args.modules.split(",") if m.strip()]
        portee = "liste explicite"
    elif args.tous:
        mods = _modules_sous(("engine",))
        portee = "TOUT engine/"
    else:
        mods = _modules_sous(PAQUETS_DEFAUT)
        portee = "paquets " + ", ".join(PAQUETS_DEFAUT)

    print("[270-r4-r2/import] TEMOIN : %d module(s) a importer EN PREMIER (%s)" % (len(mods), portee))
    if not mods:
        print("[270-r4-r2/import] ECHEC : 0 module a essayer -- un zero de balayage ne prouve RIEN")
        return 2

    echecs = []
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for mod, rc, err in ex.map(_essayer, mods):
            if rc != 0:
                echecs.append((mod, err))

    if echecs:
        print("[270-r4-r2/import] ECHEC : %d module(s) sur %d ne s'importent pas EN PREMIER"
              % (len(echecs), len(mods)))
        for mod, err in echecs:
            print("   %s\n      %s" % (mod, err))
        return 1
    print("[270-r4-r2/import] OK : %d/%d modules s'importent EN PREMIER" % (len(mods), len(mods)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
