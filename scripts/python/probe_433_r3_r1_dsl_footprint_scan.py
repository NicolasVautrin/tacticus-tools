"""#433-r3-r1 etape 1 -- PERIMETRE MESURE des noeuds DSL qui collapsent une entite sur sa MAIN TILE.

Le residu `#433-r3-r1` annonce quatre noeuds « freres » (`IsAdjacent`, `IsInRange`, `IsSurrounding`,
`IsCharging`) qui passeraient tous par `engine/dsl/base.py::_pos`. Cette liste est une PISTE : elle
n'a jamais ete derivee du code. Ce probe la derive, par AST et non par grep.

POURQUOI L'AST. Un `grep _pos` rend 978 occurrences sur 117 fichiers -- et il MENT DANS LES DEUX
SENS : il compte des `_pos` qui sont des VARIABLES LOCALES (`a_pos`, `t_pos`, `pos = ...`) ou des
fonctions HOMONYMES definies ailleurs (il en existe), et il rate ce qui atteint la main tile SANS
nommer `_pos` (un `u["pos"]` lu a la main, un `_within(...)` qui collapse en interne). Le scan ci-
dessous resout les IMPORTS (`from ...dsl.base import _pos`, y compris relatifs et alias), attribue
chaque appel a sa CLASSE englobante, et ne retient que les classes qui sont des NOEUDS DSL (bases
`AbilityTrigger` / `TargetsSelector` / `AAmountFormula`, fermeture transitive intra-fichier).

Il rapporte TROIS gisements distincts :
  A. noeuds DSL appelant `dsl.base._pos` directement ;
  B. noeuds DSL appelant `dsl.base._within` (qui collapse `_pos` en interne, sur le CENTRE) ;
  C. noeuds DSL lisant `["pos"]` / `.get("pos")` a la main (le trou que le grep `_pos` rate).

⚠ Et un AST NAIF ment lui aussi : la premiere version de ce probe ne regardait que le corps des
CLASSES, et ratait `entities/triggers.py::_units_on` -- un helper MODULE-LEVEL qui collapse `_pos`
pour le compte de DEUX noeuds (`HasUnit`, `AreEnemies`). D'ou la FERMETURE TRANSITIVE intra-fichier
sur les fonctions module-level (gisement `D_via`, avec le chemin d'appel).

Il ne CLASSE PAS (empreinte vs main tile natif) : ca se lit au decompile, noeud par noeud. Il
etablit seulement QUI est candidat, et confronte le compte a la liste de la fiche.

Sortie ASCII (cp1252). rc = 0 (inventaire).
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

# Bases de noeud DSL (mirror des 3 bases lazy natives + la famille EFFET du runner).
DSL_BASES = {"AbilityTrigger", "TargetsSelector", "AAmountFormula"}

# La liste ANNONCEE par docs/rl/case-433-r3-isadjacent-noeud-dsl.md Sec.7 (residu #433-r3-r1).
FICHE_CLAIM = {"IsAdjacent", "IsInRange", "IsSurrounding", "IsCharging"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _engine_root() -> Path:
    return Path(__file__).resolve().parent / "engine"


def _imported_from_dsl_base(tree: ast.Module) -> dict:
    """{nom local -> nom d'origine} pour tout symbole importe de `engine.dsl.base` (relatif ou non)."""
    out: dict = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        mod = node.module or ""
        # relatif (`from ..dsl.base import ...`) ou absolu (`from engine.dsl.base import ...`)
        if not (mod == "dsl.base" or mod.endswith(".dsl.base") or mod == "base" and node.level >= 1
                and False):
            continue
        for a in node.names:
            out[a.asname or a.name] = a.name
    return out


class _ClassStack(ast.NodeVisitor):
    """Attribue a chaque noeud AST la pile de classes/fonctions englobantes."""

    def __init__(self):
        self.cls_of: dict = {}      # id(node) -> (class_name | None, func_name | None)
        self._cls: list = []
        self._fn: list = []

    def visit_ClassDef(self, node):
        self._cls.append(node.name)
        self.generic_visit(node)
        self._cls.pop()

    def visit_FunctionDef(self, node):
        self._fn.append(node.name)
        self.generic_visit(node)
        self._fn.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def generic_visit(self, node):
        self.cls_of[id(node)] = (self._cls[-1] if self._cls else None,
                                 self._fn[-1] if self._fn else None)
        super().generic_visit(node)


def _base_names(cd: ast.ClassDef) -> set:
    out = set()
    for b in cd.bases:
        if isinstance(b, ast.Name):
            out.add(b.id)
        elif isinstance(b, ast.Attribute):
            out.add(b.attr)
    return out


def _dsl_classes(tree: ast.Module) -> dict:
    """{nom de classe -> base DSL racine} pour les classes de NOEUD DSL du module (transitif intra-fichier)."""
    defs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    root: dict = {}
    changed = True
    while changed:
        changed = False
        for name, cd in defs.items():
            if name in root:
                continue
            bases = _base_names(cd)
            hit = bases & DSL_BASES
            if hit:
                root[name] = sorted(hit)[0]
                changed = True
                continue
            inherited = [root[b] for b in bases if b in root]
            if inherited:
                root[name] = inherited[0]
                changed = True
    return root


def _collapse_kind(node, imports) -> tuple:
    """(gisement, detail) si ce noeud AST collapse une entite sur UNE position ; (None, '') sinon."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        origin = imports.get(node.func.id)
        if origin == "_pos":
            return "A_pos", node.func.id
        if origin == "_within":
            return "B_within", node.func.id
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
            and node.slice.value == "pos":
        return "C_raw", '["pos"]'
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "get" and node.args \
            and isinstance(node.args[0], ast.Constant) and node.args[0].value == "pos":
        return "C_raw", '.get("pos")'
    return None, ""


def scan_file(path: Path) -> list:
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    imports = _imported_from_dsl_base(tree)
    dslc = _dsl_classes(tree)
    if not dslc:
        return []
    stack = _ClassStack()
    stack.visit(tree)

    # --- passe 1 : sites DIRECTS, dans le corps d'une classe de noeud DSL
    hits: list = []
    for node in ast.walk(tree):
        cls, fn = stack.cls_of.get(id(node), (None, None))
        kind, detail = _collapse_kind(node, imports)
        if kind is None or cls is None or cls not in dslc:
            continue
        hits.append({"file": str(path).replace("\\", "/"), "line": node.lineno,
                     "cls": cls, "base": dslc[cls], "func": fn, "kind": kind, "detail": detail,
                     "via": ""})

    # --- passe 2 : helpers MODULE-LEVEL qui collapsent, remontes a leurs noeuds appelants
    #     (fermeture transitive intra-fichier : helper -> helper -> classe).
    top_fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    collapsing: dict = {}          # nom de helper -> (gisement, ligne)
    for name, fnode in top_fns.items():
        for sub in ast.walk(fnode):
            kind, _d = _collapse_kind(sub, imports)
            if kind is not None:
                collapsing.setdefault(name, (kind, sub.lineno))
                break
    changed = True
    while changed:                  # helper appelant un helper collapsant
        changed = False
        for name, fnode in top_fns.items():
            if name in collapsing:
                continue
            for sub in ast.walk(fnode):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                        and sub.func.id in collapsing:
                    collapsing[name] = (collapsing[sub.func.id][0], sub.lineno)
                    changed = True
                    break
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        helper = node.func.id
        if helper not in collapsing:
            continue
        cls, fn = stack.cls_of.get(id(node), (None, None))
        if cls is None or cls not in dslc:
            continue
        hits.append({"file": str(path).replace("\\", "/"), "line": node.lineno,
                     "cls": cls, "base": dslc[cls], "func": fn, "kind": "D_via",
                     "detail": helper, "via": helper})
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = _engine_root()
    files = sorted(root.rglob("*.py"))
    hits: list = []
    for f in files:
        hits.extend(scan_file(f))

    by_cls: dict = {}
    for h in hits:
        key = (h["cls"], h["file"])
        e = by_cls.setdefault(key, {"cls": h["cls"], "base": h["base"], "file": h["file"],
                                    "kinds": set(), "lines": [], "via": set()})
        e["kinds"].add(h["kind"])
        e["lines"].append(h["line"])
        if h.get("via"):
            e["via"].add(h["via"])

    rows = sorted(by_cls.values(), key=lambda e: (e["file"], min(e["lines"])))
    print("=== #433-r3-r1 -- noeuds DSL qui collapsent une entite sur une position ===")
    print("fichiers balayes : %d ; classes de noeud touchees : %d ; sites : %d"
          % (len(files), len(rows), len(hits)))
    print("")
    print("%-34s %-16s %-10s %s" % ("CLASSE", "BASE", "GISEMENT", "FICHIER:LIGNES"))
    for e in rows:
        short = e["file"].split("/engine/", 1)[-1]
        suffix = (" via " + ",".join(sorted(e["via"]))) if e["via"] else ""
        print("%-34s %-16s %-10s %s:%s%s"
              % (e["cls"], e["base"], ",".join(sorted(e["kinds"])), short,
                 ",".join(str(x) for x in sorted(set(e["lines"]))[:6]), suffix))

    found = {e["cls"] for e in rows}
    print("")
    print("--- confrontation a la liste de la fiche (residu #433-r3-r1) ---")
    print("annonces par la fiche : %s" % ", ".join(sorted(FICHE_CLAIM)))
    print("trouves par AST       : %d classes" % len(found))
    print("annonces NON trouves  : %s" % (", ".join(sorted(FICHE_CLAIM - found)) or "(aucun)"))
    extra = sorted(found - FICHE_CLAIM)
    print("trouves HORS liste    : %d -> %s" % (len(extra), ", ".join(extra) or "(aucun)"))

    if args.json:
        print(json.dumps([{**e, "kinds": sorted(e["kinds"])} for e in rows], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
