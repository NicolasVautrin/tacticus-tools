#!/usr/bin/env python
"""#448-r3-r1 -- un NOM utilise dans une fonction d'`engine/` doit etre RESOLVABLE.

POURQUOI CE PROBE EXISTE (mesure du 2026-08-05, pas une precaution). `630fb33e`
(#270-r1-r1-r3) a converti des litteraux en membres d'enum -- `return 16` -> `return
StatType.FIXED_ARMOR` -- dans HUIT `get_stat_modification_stat` de deux modules ou `StatType`
n'etait importe QUE dans le corps de quelques AUTRES methodes. Aucun de ces huit sites n'avait
l'import : ils levaient `NameError` a l'appel.

CE QUE CA COUTAIT, et pourquoi ca ne se voit pas a la lecture : le lecteur est
`entities/effects/__init__.py::effect_stat_modifications` <- `stat_modifications_by_source` <-
`UnitContext.from_snapshot` <- `snapshot.load_state`. Toute bataille dont une unite porte l'un de
ces effets faisait donc LEVER LE CHARGEMENT D'ETAT -- 4 erreurs sur
`test_448_r2_teleporting_in_live.py`, trouvees en re-jouant les tests APRES REBASE.

CE QUE LE PROBE MESURE. Pour chaque fonction d'`engine/**`, tout `Name` charge (`ast.Load`)
commencant par une MAJUSCULE (classes, enums, constantes de type) doit etre lie :
au niveau MODULE, dans une portee ENGLOBANTE (fonction imbriquee, classe), dans la fonction
elle-meme (import local, parametre, assignation), ou etre un builtin.

⚠ LE PIEGE DE METHODE, VECU ICI. Une premiere version resolvait les bindings de module par un
`ast.walk` sur chaque noeud de `tree.body` -- ce qui DESCEND dans les corps de methodes et compte
un `from ... import X` LOCAL a une methode comme un binding MODULE. Elle rendait « aucun site non
resolvable » sur le fichier qui LEVAIT. Les bindings de module se collectent donc SANS descendre
dans les corps de fonctions (le corps d'une CLASSE, lui, s'execute bien a l'import).

Le probe est OFFLINE et PUR (aucun runner, aucune session). Usage, depuis `scripts/python` :

    python probe_448_r3_r1_noms_non_resolvables.py
    python probe_448_r3_r1_noms_non_resolvables.py --mutate   # contre-epreuve
"""
from __future__ import annotations

import argparse
import ast
import builtins
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ENGINE = PYDIR / "engine"

#: Noms qu'un module d'`engine/` peut charger sans les lier lui-meme -- il n'y en a pas d'autre que
#: les builtins. La liste est VIDE et doit le rester : une entree ici serait une exemption, donc un
#: trou. Si un nom manque, c'est l'import qui manque.
ALLOWED: frozenset = frozenset()

BUILTINS = frozenset(dir(builtins))


def _names_bound(node) -> set:
    """Les noms que CE noeud (hors corps de fonction) lie dans sa portee."""
    out: set = set()
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.alias):
            out.add((n.asname or n.name).split(".")[0])
    return out


def module_bindings(node, out=None) -> set:
    """Bindings de la portee MODULE. ⚠ On NE DESCEND PAS dans les corps de fonctions (cf. le piege
    de methode en tete de fichier) ; le corps d'une CLASSE, lui, s'execute a l'import."""
    out = set() if out is None else out
    for n in getattr(node, "body", []) or []:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(n.name)                                   # le NOM seul, jamais le corps
        elif isinstance(n, ast.ClassDef):
            out.add(n.name)
            module_bindings(n, out)
        elif isinstance(n, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            module_bindings(n, out)                           # `if TYPE_CHECKING:`, `try: import`
            for br in (getattr(n, "orelse", None) or []):
                module_bindings(ast.Module(body=[br], type_ignores=[]), out)
            for br in (getattr(n, "finalbody", None) or []):
                module_bindings(ast.Module(body=[br], type_ignores=[]), out)
            for h in (getattr(n, "handlers", None) or []):
                module_bindings(h, out)
            for it in (getattr(n, "items", None) or []):
                if getattr(it, "optional_vars", None) is not None:
                    out |= _names_bound(it.optional_vars)
            if isinstance(n, (ast.For, ast.While)) and getattr(n, "target", None) is not None:
                out |= _names_bound(n.target)
        else:
            for x in ast.walk(n):
                if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
                    out.add(x.id)
                elif isinstance(x, ast.ExceptHandler) and x.name:
                    out.add(x.name)
    return out


def _annotation_nodes(fn) -> set:
    """Les `id()` des noeuds qui vivent dans une ANNOTATION.

    ⚠ Sous `from __future__ import annotations` (PEP 563), une annotation n'est JAMAIS evaluee :
    elle est rangee en chaine. Un `Optional` non importe y est donc inoffensif -- et c'etait
    **22 des 22** sites que le probe rapportait avant ce filtre, tous de cette forme. Un balayage
    qui les compte comme des levees fait corriger du bruit et cache le vrai gisement."""
    out: set = set()
    for n in ast.walk(fn):
        anns = []
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            anns.append(n.returns)
            for a in list(n.args.args) + list(n.args.kwonlyargs) + list(n.args.posonlyargs):
                anns.append(a.annotation)
            for a in (n.args.vararg, n.args.kwarg):
                if a is not None:
                    anns.append(a.annotation)
        elif isinstance(n, ast.AnnAssign):
            anns.append(n.annotation)
        for a in anns:
            if a is None:
                continue
            for sub in ast.walk(a):
                out.add(id(sub))
    return out


def scan_function(fn, enclosing: set, fails: list, rel: str, lazy_annotations: bool = True) -> None:
    """Balaye UNE fonction : ses propres bindings + ceux des portees englobantes."""
    local = _names_bound(fn.args) | set()
    for n in fn.body:
        local |= _names_bound(n)
    visible = enclosing | local
    skip = _annotation_nodes(fn) if lazy_annotations else set()
    for n in ast.walk(fn):
        if id(n) in skip:
            continue                                       # annotation PEP 563 : jamais evaluee
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn:
            scan_function(n, visible, fails, rel, lazy_annotations)   # closure : voit `visible`
            continue
        if not (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)):
            continue
        if not n.id[:1].isupper():
            continue                                           # on ne juge que les NOMS DE TYPE
        if n.id in visible or n.id in BUILTINS or n.id in ALLOWED:
            continue
        fails.append("%s:%d  %s()  ->  `%s` n'est lie NI au module NI dans la fonction"
                     % (rel, n.lineno, fn.name, n.id))


def _top_level_functions(node) -> list:
    """Les fonctions de PREMIER NIVEAU d'un module ou d'un corps de classe.

    ⚠ Surtout PAS `ast.walk` : il rend aussi les fonctions IMBRIQUEES, qu'on evaluerait alors avec
    la seule portee MODULE -- donc en ignorant les imports faits par leur fonction PARENTE. Mesure :
    ce raccourci produisait 85 sites dont l'ecrasante majorite etaient de faux positifs de ce type
    (`amulet_of_the_voidwyrm.py::_adjacent_friends`, dont le parent importe `AdjacentFriends`,
    `Owner` et `Const`). La recursion se fait dans `scan_function`, qui PROPAGE la portee."""
    out = []
    for n in getattr(node, "body", []) or []:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(n)
        elif isinstance(n, ast.ClassDef):
            out.extend(_top_level_functions(n))
        elif isinstance(n, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            out.extend(_top_level_functions(n))
            for br in (getattr(n, "orelse", None) or []):
                out.extend(_top_level_functions(ast.Module(body=[br], type_ignores=[])))
            for h in (getattr(n, "handlers", None) or []):
                out.extend(_top_level_functions(h))
    return out


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def star_bindings(tree, path: Path, root: Path, unresolved: list) -> set:
    """Ce qu'un `from X import *` apporte dans la portee MODULE.

    ⚠ SANS CE VOLET, LE BALAYAGE EST INUTILISABLE : `engine/playbook/prediction/abilities.py` fait
    `from ._shared import *` et lit `GC`, `AbilityConfiguration`, `ProbableDamageEvent`... -- mesure,
    le probe rendait **75 faux positifs**, tous de cette forme. On resout donc l'etoile en IMPORTANT
    reellement le module cible (le moteur s'importe proprement) et en lisant son `__all__`, ou a
    defaut ses noms publics. Un import qui ECHOUE n'est pas tu : le fichier est compte comme
    INDETERMINE et ses fonctions ne sont pas jugees -- un zero silencieux serait pire."""
    import importlib
    out: set = set()
    pkg = _module_name(path, root).rsplit(".", 1)[0]
    for n in getattr(tree, "body", []) or []:
        if not (isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)):
            continue
        target = ("." * (n.level or 0)) + (n.module or "")
        try:
            m = importlib.import_module(target, package=pkg if n.level else None)
        except Exception as exc:                       # noqa: BLE001 -- on RAPPORTE, on ne tait pas
            unresolved.append("%s : `from %s import *` non resolvable (%s: %s)"
                              % (path.name, target, type(exc).__name__, exc))
            return set()
        names = getattr(m, "__all__", None)
        out |= set(names) if names is not None else {k for k in dir(m) if not k.startswith("_")}
    return out


def scan_file(path: Path, root: Path, fails: list, indetermines: list) -> None:
    rel = str(path.relative_to(root)).replace("\\", "/")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    has_star = any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
                   for n in (tree.body or []))
    unresolved: list = []
    mod = module_bindings(tree) | star_bindings(tree, path, root, unresolved)
    if unresolved:
        indetermines.extend(unresolved)
        return                                          # portee INCONNUE -> on ne juge pas
    if has_star and not mod:
        indetermines.append("%s : `import *` sans binding resolu" % rel)
        return
    # PEP 563 : les annotations ne sont paresseuses QUE sous `from __future__ import annotations`.
    # Sans lui elles sont EVALUEES, donc un nom manquant y leve pour de bon -- on les juge alors.
    lazy = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
               and any(a.name == "annotations" for a in n.names)
               for n in (tree.body or []))
    for fn in _top_level_functions(tree):
        scan_function(fn, mod, fails, rel, lazy)


def run(mutate: bool = False) -> tuple:
    """Rend `(nombre de fichiers balayes, sites non resolvables, fichiers INDETERMINES)`."""
    fails: list = []
    indetermines: list = []
    files = sorted(ENGINE.rglob("*.py"))
    if str(PYDIR) not in sys.path:
        sys.path.insert(0, str(PYDIR))
    for p in files:
        scan_file(p, PYDIR, fails, indetermines)
    if mutate:
        # CONTRE-EPREUVE : on rejoue le site EXACT que `630fb33e` avait laisse cassable -- un
        # `return StatType.FIXED_ARMOR` dans une methode sans import -- sur un module SYNTHETIQUE.
        # On ne touche pas au depot : c'est la DETECTION qu'on eprouve, pas le code.
        src = ("class E:\n"
               "    def get_stat_modification_stat(self):\n"
               "        return StatType.FIXED_ARMOR\n"
               "    def autre(self):\n"
               "        from x import StatType\n"
               "        return StatType.CRIT_CHANCE\n")
        tree = ast.parse(src)
        mod = module_bindings(tree)
        m: list = []
        for fn in _top_level_functions(tree):
            scan_function(fn, mod, m, "<mutant>")
        fails.extend(m)
    return len(files), fails, indetermines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", action="store_true",
                    help="ajoute le site EXACT de `630fb33e` sur un module synthetique -- la "
                         "detection DOIT le voir")
    a = ap.parse_args()
    n, fails, indetermines = run(mutate=a.mutate)
    print("fichiers balayes sous engine/ : %d" % n)
    # TRI-ETAT : un fichier dont la portee n'a pas pu etre resolue n'est PAS un fichier vert.
    print("fichiers INDETERMINES (portee non resolue) : %d" % len(indetermines))
    for f in indetermines:
        print("  ? " + f)
    if a.mutate:
        seen = [f for f in fails if f.startswith("<mutant>")]
        print("sites du MUTANT detectes : %d" % len(seen))
        for f in seen:
            print("  - " + f)
        if not seen:
            print("[VERDICT] MUTATION NON DETECTEE -- le balayage ne garde RIEN. ROUGE.")
            return 1
        print("[VERDICT] mutation DETECTEE -- le balayage discrimine.")
        return 0
    if fails:
        print("%d SITE(S) NON RESOLVABLE(S) -- ils LEVENT a l'appel :" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("[VERDICT] VERT -- aucun nom de type non resolvable sous engine/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
