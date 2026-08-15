"""#593 -- la SURFACE de `rl_duel.py` : masse, commandes, et surtout ce que ses IMPORTEURS lient.

POURQUOI CE PROBE. La fiche #593 chiffre la MASSE (lignes, fonctions, `cmd_build`) et le RAYON
(fichiers qui citent / qui importent), puis propose « extraire `cmd_build` dans un module dedie en
gardant `rl_duel.py` comme FACADE ». Mais elle ne mesure PAS ce qui DECIDE de la faisabilite :
**quels SYMBOLES les importeurs lient reellement**. Une facade est triviale si l'on ne lie que
`main` et deux helpers ; elle est un chantier si trente noms prives circulent.

CE QUE LE PROBE REND, tout DERIVE de l'arbre courant (aucun chiffre recopie) :
  1. masse : lignes totales / de code / de docstring, fonctions, classes, commandes ;
  2. la plus grosse fonction, et sa part du fichier ;
  3. le RAYON : fichiers qui CITENT, fichiers qui IMPORTENT comme module ;
  4. l'INVENTAIRE DES SYMBOLES lies par ces importeurs -- la contrainte de facade, et la seule
     chose qu'un decoupage puisse casser EN SILENCE ;
  5. la ventilation PRIVE / PUBLIC de ces symboles : un nom prive lie depuis l'exterieur est un
     couplage que la facade devra assumer explicitement.

⚠ Les acces ATTRIBUTAIRES comptent. `import rl_duel as R` puis `R._rpc(...)` ne laisse AUCUNE
trace dans un recensement d'`ImportFrom` -- c'est exactement le gisement que #485-r1-r1 a mesure
sur un autre foyer, et c'est la forme MAJORITAIRE ici.

Usage (depuis `scripts/python`, 100 % offline) :

    python probe_593_rl_duel_surface.py
"""
from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parent
CIBLE = RACINE / "rl_duel.py"


def _masse(src: str) -> dict:
    arbre = ast.parse(src)
    lignes = src.splitlines()
    doc = set()
    for n in ast.walk(arbre):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(n, clean=False)
            if d is not None and n.body and isinstance(n.body[0], ast.Expr):
                e = n.body[0]
                doc.update(range(e.lineno, (e.end_lineno or e.lineno) + 1))
    vides = sum(1 for ln in lignes if not ln.strip())
    fns = [n for n in arbre.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    plus_grosse = max(fns, key=lambda f: (f.end_lineno or f.lineno) - f.lineno, default=None)
    return {
        "lignes": len(lignes),
        "docstring": len(doc),
        "vides": vides,
        "code": len(lignes) - len(doc) - vides,
        "fonctions": len(fns),
        "classes": sum(1 for n in arbre.body if isinstance(n, ast.ClassDef)),
        "commandes": sum(1 for f in fns if f.name.startswith("cmd_")),
        "plus_grosse": (plus_grosse.name,
                        (plus_grosse.end_lineno or 0) - plus_grosse.lineno + 1) if plus_grosse
                       else (None, 0),
        "exportes": sorted(f.name for f in fns),
    }


def _rayon(racine: Path) -> dict:
    """Qui cite, qui importe, et QUELS symboles chaque importeur lie."""
    cite, importeurs = set(), {}
    for p in racine.rglob("*.py"):
        if p == CIBLE:
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "rl_duel" not in src:
            continue
        cite.add(p)
        try:
            arbre = ast.parse(src)
        except SyntaxError:
            continue
        alias, symboles = None, set()
        for n in ast.walk(arbre):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name == "rl_duel":
                        alias = a.asname or "rl_duel"
            elif isinstance(n, ast.ImportFrom) and n.module == "rl_duel":
                symboles.update(a.name for a in n.names)          # liaison directe (forme A)
        if alias is not None:
            for n in ast.walk(arbre):
                if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                        and n.value.id == alias):
                    symboles.add(n.attr)                          # acces ATTRIBUTAIRE (forme B)
        if alias is not None or symboles:
            importeurs[p] = symboles
    return {"cite": cite, "importeurs": importeurs}


def main(argv=None) -> int:
    src = CIBLE.read_text(encoding="utf-8")
    m = _masse(src)
    print("[593] MASSE de rl_duel.py")
    print("    lignes=%d  (code=%d  docstring=%d  vides=%d)"
          % (m["lignes"], m["code"], m["docstring"], m["vides"]))
    print("    fonctions=%d  classes=%d  commandes=%d"
          % (m["fonctions"], m["classes"], m["commandes"]))
    print("    plus grosse fonction : %s = %d lignes (%.0f %% du fichier)"
          % (m["plus_grosse"][0], m["plus_grosse"][1],
             100.0 * m["plus_grosse"][1] / max(1, m["lignes"])))

    r = _rayon(RACINE)
    print("[593] RAYON DE SOUFFLE")
    print("    fichiers qui CITENT rl_duel     : %d" % len(r["cite"]))
    print("    fichiers qui l'IMPORTENT        : %d" % len(r["importeurs"]))

    lies = Counter()
    for symboles in r["importeurs"].values():
        lies.update(symboles)
    connus = set(m["exportes"])
    prives = sorted(s for s in lies if s.startswith("_"))
    publics = sorted(s for s in lies if not s.startswith("_"))
    print("[593] SYMBOLES LIES PAR LES IMPORTEURS -- la CONTRAINTE de facade")
    print("    distincts=%d  (publics=%d  prives=%d)" % (len(lies), len(publics), len(prives)))
    print("    publics : %s" % (publics,))
    print("    prives  : %s" % (prives,))
    hors = sorted(s for s in lies if s not in connus)
    print("    lies mais NON definis comme fonction top-level (constantes, modules re-exportes,")
    print("    attributs dynamiques) : %s" % (hors,))
    print("[593] LES 12 PLUS LIES : %s" % (lies.most_common(12),))
    print("[593] LECTURE : une facade doit re-exporter EXACTEMENT les symboles ci-dessus, en")
    print("    FORME B (`import X` puis `X.foo()`) -- la forme A desarmerait les patchs deja")
    print("    poses (#485-r1-r1). Les symboles PRIVES sont ceux qu'un decoupage casserait en")
    print("    silence : ils ne sont dans aucun contrat, et rien d'autre que ce probe ne les voit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
