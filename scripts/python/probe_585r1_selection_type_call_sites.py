"""Inventaire AST des call-sites de factory a `selectionType` -- #585-r1.

Ne devine RIEN : il liste, il ne conclut pas. Sortie ASCII (console cp1252).

Les factories retenues sont celles dont le MIRROR porte aujourd'hui un parametre
`selection_type` (lu dans le source, pas ecrit ici a la main).

Usage:
    python probe_585r1_selection_type_call_sites.py [--racine engine/runner/abilities]
                                                    [--csv <chemin>]
"""
from __future__ import annotations

import argparse
import ast
import re
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(ICI, "engine")


def _factories_avec_parametre():
    """DERIVE du source : toute classe/fonction de `entities/selectors/**` dont la signature
    porte `selection_type`. Jamais une liste ecrite a la main."""
    noms = {}
    base = os.path.join(ENGINE, "entities", "selectors")
    for f in sorted(os.listdir(base)):
        if not f.endswith(".py"):
            continue
        chemin = os.path.join(base, f)
        with open(chemin, "r", encoding="utf-8") as fh:
            arbre = ast.parse(fh.read(), filename=chemin)
        for n in ast.walk(arbre):
            if isinstance(n, ast.FunctionDef):
                args = [a.arg for a in n.args.args] + [a.arg for a in n.args.kwonlyargs]
                if "selection_type" in args:
                    if n.name == "__init__":
                        continue
                    noms[n.name] = (f, args.index("selection_type"))
            elif isinstance(n, ast.ClassDef):
                for m in n.body:
                    if isinstance(m, ast.FunctionDef) and m.name == "__init__":
                        args = [a.arg for a in m.args.args]
                        if "selection_type" in args:
                            # position hors `self`
                            noms[n.name] = (f, args.index("selection_type") - 1)
    return noms


def _fichiers(racine):
    for d, _sd, fs in os.walk(racine):
        for f in sorted(fs):
            if f.endswith(".py"):
                yield os.path.join(d, f)


def _nom_appele(node):
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


_SYMBOLE = re.compile(r"(IdunBattle[\w.]*\$\$\w+)")


def _symboles_par_ligne(src, arbre):
    """`ligne -> symbole natif cite dans la docstring du def/class ENGLOBANT le plus proche`.

    L'appariement port <-> natif n'est PAS devine : le port cite deja son artefact natif dans la
    docstring de la classe/fonction qui le porte. On remonte la chaine des noeuds englobants et on
    prend le PREMIER symbole cite. Un site sans symbole englobant sort a `?` -- c'est un resultat,
    pas un defaut : il faudra l'identifier a la main."""
    portee = {}                                   # (debut, fin) -> [symboles]
    for n in ast.walk(arbre):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        doc = ast.get_docstring(n) or ""
        syms = _SYMBOLE.findall(doc)
        fin = getattr(n, "end_lineno", None) or n.lineno
        portee[(n.lineno, fin)] = syms
    def pour(ligne):
        candidats = [(deb, fin, s) for (deb, fin), s in portee.items()
                     if deb <= ligne <= fin and s]
        if not candidats:
            return "?"
        # le plus INTERIEUR (portee la plus etroite)
        deb, fin, s = min(candidats, key=lambda c: c[1] - c[0])
        return s[0]
    return pour


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", default=os.path.join(ENGINE, "runner", "abilities"))
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    fac = _factories_avec_parametre()
    print("FACTORIES A PARAMETRE (derivees du source de entities/selectors) : %d" % len(fac))
    for k in sorted(fac):
        print("  %-32s %s (position %d)" % (k, fac[k][0], fac[k][1]))
    print("")

    racine = os.path.abspath(args.racine)
    lignes = []
    for chemin in _fichiers(racine):
        with open(chemin, "r", encoding="utf-8") as fh:
            src = fh.read()
        try:
            arbre = ast.parse(src, filename=chemin)
        except SyntaxError as exc:
            print("SYNTAXE KO %s : %s" % (chemin, exc))
            continue
        sym = _symboles_par_ligne(src, arbre)
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            nom = _nom_appele(n)
            if nom not in fac:
                continue
            pos = fac[nom][1]
            renseigne = any(k.arg == "selection_type" for k in n.keywords)
            if not renseigne and len(n.args) > pos:
                renseigne = True
            rel = os.path.relpath(chemin, ENGINE).replace("\\", "/")
            lignes.append((rel, n.lineno, nom, "RENSEIGNE" if renseigne else "MUET",
                           sym(n.lineno)))

    lignes.sort()
    muets = [l for l in lignes if l[3] == "MUET"]
    print("CALL-SITES sous %s : %d (dont MUETS : %d)"
          % (os.path.relpath(racine, ENGINE).replace("\\", "/"), len(lignes), len(muets)))
    print("")
    par_fac = {}
    for l in lignes:
        par_fac.setdefault(l[2], [0, 0])
        par_fac[l[2]][0] += 1
        if l[3] == "MUET":
            par_fac[l[2]][1] += 1
    print("%-32s %8s %8s" % ("factory", "total", "muets"))
    for k in sorted(par_fac, key=lambda x: -par_fac[x][0]):
        print("%-32s %8d %8d" % (k, par_fac[k][0], par_fac[k][1]))
    print("")
    # Regroupement PAR SYMBOLE NATIF : c'est l'unite de travail du releve (un decompile = tous les
    # call-sites du port qui le mirrorent).
    par_sym = {}
    for l in lignes:
        if l[3] != "MUET":
            continue
        par_sym.setdefault(l[4], []).append("%s:%d %s" % (l[0], l[1], l[2]))
    print("SYMBOLES NATIFS A DECOMPILER : %d (dont `?` = non cite en docstring englobante)"
          % len(par_sym))
    for s in sorted(par_sym, key=lambda x: (-len(par_sym[x]), x)):
        print("  %-3d  %s" % (len(par_sym[s]), s))
        for e in par_sym[s]:
            print("        %s" % e)

    if args.csv:
        with open(args.csv, "w", encoding="utf-8") as fh:
            fh.write("fichier;ligne;factory;etat;symbole\n")
            for l in lignes:
                fh.write("%s;%d;%s;%s;%s\n" % l)
        print("\nCSV -> %s" % args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
