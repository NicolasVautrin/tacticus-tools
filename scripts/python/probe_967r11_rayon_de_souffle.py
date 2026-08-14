#!/usr/bin/env python3
"""#967-r11 -- RAYON DE SOUFFLE du noeud DSL `SurroundingTiles`, derive du CODE.

Un `git grep SurroundingTiles` rend 66 fichiers, dont l'ecrasante majorite ne fait que CITER le
symbole natif en docstring. Le rayon reel est l'ensemble des sites qui INSTANCIENT la classe
`engine.entities.selectors.accessors.SurroundingTiles` -- eux seuls voient l'ensemble change par
un gate pose dans `select`.

Le tri est fait par AST (jamais par regex) : on resout, fichier par fichier, quels noms locaux
designent cette classe (import direct, alias, acces attributaire sur le module importe -- la
troisieme voie est celle qu'un recensement d'`ImportFrom` rate, cf. #485-r1-r1), puis on compte
les `ast.Call` sur ces noms.

Sortie ASCII stricte. Offline pur, ne monte aucun runner.

Usage :
    python probe_967r11_rayon_de_souffle.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ENGINE = PYDIR / "engine"

CIBLE_MODULE = "engine.entities.selectors.accessors"
CIBLE_NOM = "SurroundingTiles"


def _module_of(path: Path) -> str:
    rel = path.relative_to(PYDIR).with_suffix("")
    return ".".join(rel.parts)


def _resoudre_relatif(module: str, niveau: int, cible: str | None) -> str:
    """`from ...entities.selectors.accessors import X` dans `engine.runner.abilities.loki.x`."""
    parts = module.split(".")
    base = parts[:len(parts) - niveau] if niveau else parts
    return ".".join([p for p in base + ([cible] if cible else []) if p])


def _noms_locaux(tree: ast.AST, module: str):
    """Rend (noms_directs, noms_de_module) : les identifiants qui designent la CLASSE, et ceux
    qui designent le MODULE `accessors` (pour l'acces attributaire `acc.SurroundingTiles`)."""
    directs, modules = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            src = _resoudre_relatif(module, n.level or 0, n.module) if n.level else (n.module or "")
            for a in n.names:
                if src == CIBLE_MODULE and a.name == CIBLE_NOM:
                    directs.add(a.asname or a.name)
                # `from engine.entities.selectors import accessors`
                elif src == CIBLE_MODULE.rsplit(".", 1)[0] and a.name == CIBLE_MODULE.rsplit(".", 1)[1]:
                    modules.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name == CIBLE_MODULE:
                    modules.add(a.asname or a.name.split(".")[0])
    return directs, modules


def _compter(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return 0
    directs, modules = _noms_locaux(tree, _module_of(path))
    if not directs and not modules:
        return 0
    n = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name) and f.id in directs:
            n += 1
        elif (isinstance(f, ast.Attribute) and f.attr == CIBLE_NOM
              and isinstance(f.value, ast.Name) and f.value.id in modules):
            n += 1
    return n


def main():
    fichiers = sorted(ENGINE.rglob("*.py"))
    print("PERIMETRE : %d fichiers sous engine/" % len(fichiers))
    print()
    total_sites, total_fichiers = 0, 0
    print("%-62s %s" % ("FICHIER (instancie le noeud)", "sites"))
    for p in fichiers:
        n = _compter(p)
        if n:
            total_sites += n
            total_fichiers += 1
            print("%-62s %5d" % (str(p.relative_to(PYDIR)).replace("\\", "/"), n))
    print()
    print("CONSOMMATEURS EXECUTABLES sous engine/ : %d fichiers, %d sites"
          % (total_fichiers, total_sites))

    # Hors engine/ : probes et tests qui montent le noeud a la main (ils voient le gate aussi).
    hors, hors_sites = [], 0
    for p in sorted(PYDIR.rglob("*.py")):
        try:
            p.relative_to(ENGINE)
            continue
        except ValueError:
            pass
        n = _compter(p)
        if n:
            hors.append((p, n))
            hors_sites += n
    print()
    print("HORS engine/ (probes + tests, ils exercent le meme gate) : %d fichiers, %d sites"
          % (len(hors), hors_sites))
    for p, n in hors:
        print("  %-60s %5d" % (str(p.relative_to(PYDIR)).replace("\\", "/"), n))
    if total_fichiers == 0:
        print()
        print("ATTENTION : ZERO consommateur -- soit le recenseur est aveugle a une voie, soit le "
              "noeud est mort. Ne pas lire ce zero comme 'rien a rejouer'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
