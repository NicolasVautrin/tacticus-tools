#!/usr/bin/env python
"""#10031 -- LA MORSURE D'UNE SUBSTITUTION, MESUREE AU LIEU D'ETRE SUPPOSEE.

LE GISEMENT
-----------
Un probe ou un test qui pose `X.foo = stub` sur le module SOURCE ne mord que si le CONSOMMATEUR
resout `foo` A L'APPEL. CLAUDE.md le dit deja, mesure a l'appui : la forme **A**
(`from X import foo` au niveau module) **NE MORD PAS** ; **B** (`import X` puis `X.foo()`) mord ;
**C** (`from X import foo` dans la fonction) mord par accident. Ce qui manquait, c'est un moyen de
le CONSTATER depuis le site de mesure -- et l'histoire de `#381-r4` montre pourquoi :

  * `492c722f` (2026-08-05, « hisser 624 imports differes d'engine/ au niveau module ») a passe
    `make_can_continue` et `is_like_flying` de la forme C a la forme A dans
    `engine/services/movement_query.py` ;
  * TROIS instruments visaient ces deux noms. Le seul joue par un cliquet
    (`test_381r4_imperative_collapses_offline.py`) a rougi et a ete repare AU SITE DE MESURE
    (en patchant aussi le consommateur) ; les deux autres -- le pendant LIVE et
    `probe_381r4_imperative_collapses.py` -- sont restes MUETS 13 jours, en rendant des messages qui
    accusaient la GEOMETRIE (« aucune geometrie ou le gate #131 change l'atterrissage », « le bras
    NE DISCRIMINE PAS ») la ou la cause etait la LIAISON.

`migrate_485r1_barils_reexport.py morsure` voit ce gisement -- mais il le voit AVANT le hissage
(son perimetre est l'ensemble des imports DIFFERES) ; une fois le hissage consomme, le couple sort
de son ecran, et sa categorie `DEJA_INERTE` est un INVENTAIRE non bloquant de plusieurs dizaines de
lignes. Ce module-ci repond a l'autre question, celle du site de mesure : « MON patch mord-il ? ».

DEUX LECTURES, ET ELLES NE VOIENT PAS LA MEME CHOSE
---------------------------------------------------
`liaisons_figees`           -- RUNTIME. Ne voit que les modules CHARGES, donc exactement ceux que le
                               chemin exerce a tires. C'est la bonne lecture pour une garde locale
                               posee dans un `_no_gate()` : elle ne peut pas rougir sur un module
                               que le test ne traverse pas.
`liaisons_figees_statiques` -- AST. Voit TOUT l'arbre, y compris ce qu'aucune passe ne charge. C'est
                               la bonne lecture pour un cliquet, et la seule qui montre une liaison
                               figee dans un module qui dort.

Aucune des deux ne remonte un simple RE-EXPORT : un module qui lie le nom sans jamais l'APPELER ne
change la morsure de personne. Le critere « appelle » est DERIVE de l'AST du module, jamais liste.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable, Optional

#: racine du paquet balaye par la lecture statique (le seul arbre ou vivent nos foyers).
RACINE_DEFAUT = Path(__file__).resolve().parent / "engine"


def _appelle(arbre: ast.AST, nom: str) -> bool:
    """VRAI si `nom` est appele quelque part dans le module (`nom(...)` ou `nom(...)` decore).

    C'est ce qui separe un CONSOMMATEUR d'un simple re-export : seule une position d'appel peut
    voir -- ou ne pas voir -- une substitution."""
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == nom:
            return True
    return False


def _lie_en_forme_a(arbre: ast.AST, module_source: str, nom: str) -> bool:
    """VRAI si le module porte `from <module_source> import <nom>` AU NIVEAU MODULE (forme A).

    Les `ImportFrom` imbriques dans une fonction/classe (forme C) sont EXCLUS : ils sont re-executes
    a chaque appel, donc ils mordent. L'import RELATIF est resolu par le suffixe : `from ..x import
    foo` dans `engine.services` designe `engine.entities...x` -- on n'a pas besoin du paquet exact,
    il suffit que le dernier segment concorde, car un homonyme de module qui exporterait le meme nom
    serait de toute facon un consommateur a verifier."""
    queue = module_source.rsplit(".", 1)[-1]
    for n in getattr(arbre, "body", []):
        if not isinstance(n, ast.ImportFrom):
            continue
        mod = n.module or ""
        if mod != module_source and mod.rsplit(".", 1)[-1] != queue:
            continue
        if any(a.name == nom for a in n.names):
            return True
    return False


def liaisons_figees(module_source: str, nom: str, objet, *,
                    consommateurs_seuls: bool = True,
                    prefixe: str = "engine.") -> "set[str]":
    """RUNTIME : les modules CHARGES qui ont fige `nom` (forme A) et l'APPELLENT.

    `objet` = la valeur ORIGINALE (celle sauvegardee avant la substitution). L'identite est le seul
    critere sur lequel on puisse conclure : un module qui porte encore l'objet d'origine apres que
    la source a ete substituee n'a pas vu la substitution.

    ⚠ Cette lecture ne peut RIEN dire d'un module non charge -- c'est voulu (une garde locale ne
    doit pas rougir sur un chemin que le test ne traverse pas), et c'est exactement ce que
    `liaisons_figees_statiques` complete."""
    out = set()
    for nom_mod, mod in list(sys.modules.items()):
        if mod is None or nom_mod == module_source or not nom_mod.startswith(prefixe):
            continue
        if getattr(mod, nom, None) is not objet:
            continue
        if consommateurs_seuls:
            src = getattr(mod, "__file__", None)
            if not src or not Path(src).exists():
                continue
            try:
                arbre = ast.parse(Path(src).read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            if not _appelle(arbre, nom):
                continue
        out.add(nom_mod)
    return out


def liaisons_figees_statiques(module_source: str, nom: str, *,
                              racine: Optional[Path] = None,
                              consommateurs_seuls: bool = True) -> "set[str]":
    """AST : les modules de `racine` qui lient `nom` en forme A ET l'appellent. Voit tout l'arbre,
    charge ou non. Rend des chemins RELATIFS a la racine (lisibles dans un message d'echec)."""
    racine = Path(racine or RACINE_DEFAUT)
    out = set()
    for p in sorted(racine.rglob("*.py")):
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        if not _lie_en_forme_a(arbre, module_source, nom):
            continue
        if consommateurs_seuls and not _appelle(arbre, nom):
            continue
        out.add(p.relative_to(racine).as_posix())
    return out


def cibles_substituees(fichiers: Iterable[Path]) -> "set[tuple[str, str]]":
    """DERIVE des instruments eux-memes les couples (alias de module, attribut) qu'ils substituent.

    On cherche les affectations `ALIAS.attr = <...>` dont `ALIAS` est lie par un
    `import <module> as ALIAS` / `from <paquet> import <module> as ALIAS` dans le meme fichier --
    la seule forme par laquelle on substitue un symbole d'un module tiers. Rend
    `(module_pleinement_qualifie_ou_suffixe, attribut)`.

    C'est ce qui remplace une LISTE ECRITE A LA MAIN : le jour ou un instrument change de cible, le
    cliquet suit sans qu'on ait a l'editer."""
    out = set()
    for f in fichiers:
        f = Path(f)
        try:
            arbre = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        alias = {}
        for n in ast.walk(arbre):
            if isinstance(n, ast.Import):
                for a in n.names:
                    alias[a.asname or a.name.split(".")[0]] = a.name
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    if a.asname:
                        alias[a.asname] = "%s.%s" % (n.module or "", a.name)
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Assign):
                continue
            for cible in n.targets:
                if (isinstance(cible, ast.Attribute) and isinstance(cible.value, ast.Name)
                        and cible.value.id in alias):
                    out.add((alias[cible.value.id].lstrip("."), cible.attr))
    return out


def main() -> int:                                       # pragma: no cover - outil de lecture
    import argparse
    ap = argparse.ArgumentParser(description="morsure d'une substitution (#10031)")
    ap.add_argument("module_source")
    ap.add_argument("nom")
    a = ap.parse_args()
    figees = liaisons_figees_statiques(a.module_source, a.nom)
    print("[10031] %s . %s -- liaisons FIGEES (forme A) qui appellent le nom : %d"
          % (a.module_source, a.nom, len(figees)))
    for m in sorted(figees):
        print("    %s" % m)
    return 0 if not figees else 1


if __name__ == "__main__":                               # pragma: no cover
    raise SystemExit(main())
