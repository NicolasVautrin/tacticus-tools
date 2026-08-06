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


def empreinte_engine() -> tuple:
    """Etat de l'arbre `engine/` : `(chemin, mtime_ns, taille)` pour chaque `.py`, trie.

    C'est la CLE du cache de `essayer_tous`. Un cache indexe seulement par nom de module
    mentirait des qu'un test aurait modifie une source entre deux mesures -- et le mensonge
    serait dans le sens VERT, le seul qui ne se voit pas. Cout mesure : ~437 `stat`, sous 0,2 s,
    contre 0,54 s pour UN SEUL essai.
    """
    out = []
    for f in sorted((RACINE / "engine").rglob("*.py")):
        try:
            st = f.stat()
        except OSError:                                # pragma: no cover - course disque
            out.append((f.as_posix(), None, None))
            continue
        out.append((f.as_posix(), st.st_mtime_ns, st.st_size))
    return tuple(out)


#: `{(empreinte de l'arbre, module): (module, rc, message)}` -- memoise pour la duree du process.
#:
#: POURQUOI (#486-r5). `_essayer` lance UN interpreteur par module : 0,54 s piece, 131,6 s pour
#: les 437 modules a 8 workers. DEUX fichiers de test appellent ce balayage dans la MEME passe,
#: et leurs perimetres se recouvrent a **201 modules sur 437** -- soit 44,1 s payes deux fois.
#:
#: SUR A PARTAGER : la valeur est un `tuple` de scalaires, IMMUABLE. Et la cle porte l'EMPREINTE
#: de l'arbre `engine/`, donc une source modifiee entre deux mesures invalide le cache d'elle-meme
#: au lieu de rendre un verdict perime.
_ESSAIS: dict = {}


def essayer_tous(mods, jobs: int = 8) -> list:
    """`[(module, rc, message)]` pour `mods`, en parallele, SANS re-essayer ce qui l'a deja ete
    sur le MEME etat de l'arbre. L'ordre du retour suit `mods`."""
    mods = list(mods)
    emp = empreinte_engine()
    manquants = [m for m in mods if (emp, m) not in _ESSAIS]
    if manquants:
        with ThreadPoolExecutor(max_workers=max(1, min(jobs, len(manquants)))) as ex:
            for res in ex.map(_essayer, manquants):
                _ESSAIS[(emp, res[0])] = res
    return [_ESSAIS[(emp, m)] for m in mods]


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

    echecs = [(mod, err) for mod, rc, err in essayer_tous(mods, args.jobs) if rc != 0]

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
