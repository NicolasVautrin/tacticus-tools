#!/usr/bin/env python
"""Probe #274 (`#254b-b`) -- balayage OFFLINE des ordinaux `StepType` / `GroupType` en dur.

POURQUOI CE PROBE EXISTE
------------------------
`step` et `group` sont les 1er arguments de `IdunBattle.Streams.StreamDispatcher$$Action(StepType,
BEntityId, Dictionary<TagKey,int>)` et `IdunBattle.Streams.StreamDispatcher$$StartGroup(GroupType,
BEntityId, string, Nullable<BEntityId>)`. Ces enums sont IMPLICITEMENT numerotees : le retrait d'un
membre au milieu decale tout ce qui suit de -1.

C'est ARRIVE : la MAJ `gqfc5mff6c` -> `rnca9r7q6c` a retire `StepType.RestoreArmorInfo` (7). Un
filtre `step == 10` qui visait `AddUnit` designe desormais `AddMachine`. La panne est MUETTE : le
filtre ne rend pas « rien », il rend UN AUTRE PAS, souvent en quantite. Mesure de `case-254b-a` sur
une cascade reelle : les pas voisins des anciens litteraux valaient 28 `ChangeStats` et 31
`LoseEffect` la ou l'on croyait lire des morts et des effets.

`stream_events.step_id("<Nom>")` / `group_id("<Nom>")` resolvent le nom contre
`data/symbols/<CURRENT>/frida/enums.tsv` (VERSIONNEE, donc presente dans tout worktree) et LEVENT si
le membre a disparu. Ce probe est le cliquet qui empeche un ordinal en dur de revenir.

UN ORDINAL JUSTE AUJOURD'HUI RESTE UN DEFAUT : `GroupType` n'a PAS bouge entre les deux builds
(104/104, 0 divergent -- verifie par l'etape 0), et `step == 4` (`UnitDamaged`) precede le membre
retire. Ces litteraux-la sont neanmoins signales : ils sont faux au prochain build, en silence.

CE QUE LE PROBE FAIT
--------------------
0. Rend les deux tables du build courant, et le DIFF avec le build precedent s'il est present sous
   `data/symbols/` -- c'est ce qui donne, pour chaque litteral trouve, « ce qu'il designait AVANT »
   et « ce qu'il designe MAINTENANT ».
1. Balaye en AST les `.py` de SON PROPRE checkout -- `.claude/worktrees/` est exclu, cf. le
   commentaire de `_SKIP_RELS` : toute comparaison `<expr step/group> <op> <litteral int>`
   (ou `in (…)` d'un tuple/liste/set d'entiers). L'expression est reconnue soit directement
   (`x.get("step")`, `x["group"]`), soit par ALIAS (une variable affectee depuis un tel acces dans
   le meme fichier -- le motif `step = ev.get("step")` puis `if step == 13`).
2. Verifie la table de LABELS positionnelle du frontend (`frida/public/src/battle-log.js`) contre
   `enums.tsv` : elle est indexee par ordinal, donc exposee au meme decalage.

Verdict FAIL si un ordinal en dur subsiste hors allowlist, ou si une table de labels diverge.

ASCII only (cp1252). Usage: python probe_274_step_ordinals_sweep.py [-v]
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import stream_events as SE  # noqa: E402
from symbols_layout import current_build  # noqa: E402

STEP_ENUM = SE.STEP_ENUM
GROUP_ENUM = SE.GROUP_ENUM

# Fichiers exemptes du cliquet, avec la RAISON. Un fichier n'entre ici que s'il ne peut PAS
# resoudre par nom -- jamais « parce que c'est vieux ».
ALLOWLIST = {
    # Le module qui DEFINIT la resolution par nom : ses seuls entiers sont des Effect_Type
    # (`Effect_Type` n'est ni StepType ni GroupType), pas des ordinaux de pas.
    "scripts/python/stream_events.py": "definit step_id/group_id",
    "scripts/python/probe_274_step_ordinals_sweep.py": "ce probe (les litteraux y sont des donnees)",
}

# `hooks-legacy/` est VERSIONNE mais rien de vivant n'en depend (cf. `hooks-legacy/README.md`) :
# on l'inventorie a part, il ne fait pas echouer le cliquet.
INFO_PREFIXES = ("hooks-legacy/",)

# ⚠ Ces segments se testent sur le chemin RELATIF au depot, JAMAIS sur `p.parts` (absolu). Ce
# probe filtrait sur l'absolu : le trou n'etait pas theorique, il etait des DEUX cotes.
_SKIP_PARTS = (".git", "node_modules", "logs", "sources_win", "dist", ".venv")

# `.claude/worktrees/agent-<id>/` est un AUTRE checkout du depot (#434). Depuis l'arbre principal
# il est HORS PERIMETRE -- sans cette ligne, ce probe lisait et RAPPORTAIT le code en cours des
# autres agents. Mesure du 2026-08-01, 8 worktrees vivants : 13 267 `.py` retenus dont 11 746
# (88,5 %) chez eux ; perimetre propre 1 521. Le probe mettait 366,6 s depuis l'arbre principal
# contre 33,7 s depuis un worktree.
#
# ⚠ L'exclusion porte sur le chemin RELATIF, et c'est ce qui la rend correcte DANS LES DEUX SENS.
# Ajouter `worktrees` au filtre par SEGMENT (`p.parts`) parait equivalent et ne l'est pas : un
# agent tourne DANS `.claude/worktrees/agent-<id>/`, donc tout chemin absolu chez lui porte ce
# segment. Mesure directe de cette variante : 1 521 fichiers depuis l'arbre principal -- et
# **0 fichier** depuis un worktree, avec `VERDICT: PASS`. Le cliquet `probe_440` garde cette
# distinction pour tout le depot.
_SKIP_RELS = (".claude/worktrees",)


def _rel_ou_none(p: Path) -> "str | None":
    """Chemin relatif POSIX du fichier, ou None s'il est hors perimetre."""
    try:
        rel = p.relative_to(REPO).as_posix()
    except ValueError:
        return None
    if any(seg in _SKIP_PARTS for seg in rel.split("/")):
        return None
    return None if any(rel == r or rel.startswith(r + "/") for r in _SKIP_RELS) else rel


def _py_du_depot() -> list:
    """Les `*.py` du depot -- MEME liste que `sorted(REPO.rglob("*.py"))`, mais elaguee A LA
    SOURCE : `rglob` descend PARTOUT puis on filtre, donc la traversee de `.git`, de
    `node_modules` et des worktrees imbriques etait payee integralement. `os.walk` laisse elaguer
    `dirnames` EN PLACE. Il ne suit pas non plus les points de reparse (junction), la ou `rglob`
    y descend. La comparaison de suffixe est INSENSIBLE A LA CASSE, comme `Path.glob` sous
    Windows (`rglob("*.py")` y ramene aussi `Foo.PY`)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(REPO):
        d = Path(dirpath)
        dirnames[:] = [n for n in dirnames if _rel_ou_none(d / n) is not None]
        out += [d / n for n in filenames if n.lower().endswith(".py")]
    return sorted(out)


def _enum_map(build: str, cle: str) -> dict:
    """{ordinal: NOM} d'un enum, lu dans `data/symbols/<build>/frida/enums.tsv`."""
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith(cle + "\t"):
                out = {}
                for kv in line.rstrip("\n").split("\t", 1)[1].split(","):
                    o, _, n = kv.partition("=")
                    if n:
                        try:
                            out[int(o)] = n
                        except ValueError:
                            pass
                return out
    return {}


def _builds() -> list:
    d = REPO / "data" / "symbols"
    return sorted(x.name for x in d.iterdir() if (x / "frida" / "enums.tsv").is_file()) \
        if d.is_dir() else []


# --------------------------------------------------------------------------------------------
# Etape 1 -- balayage AST
# --------------------------------------------------------------------------------------------

_KEYS = ("step", "group")


def _direct_key(node) -> "str | None":
    """`x.get("step")` / `x["group"]` -> "step"/"group", sinon None."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "get" and node.args:
        a = node.args[0]
        if isinstance(a, ast.Constant) and a.value in _KEYS:
            return a.value
    if isinstance(node, ast.Subscript):
        s = node.slice
        if isinstance(s, ast.Constant) and s.value in _KEYS:
            return s.value
    # `int(ev.get("step") or -1)`, `_safe_int(ev.get("group"))` : un seul niveau d'emballage
    if isinstance(node, ast.Call) and node.args:
        inner = _direct_key(node.args[0])
        if inner:
            return inner
    if isinstance(node, ast.BoolOp) and node.values:
        return _direct_key(node.values[0])
    return None


class _Aliases(ast.NodeVisitor):
    """Trois liaisons, collectees sur TOUT le fichier :

    * `alias`   : variable affectee depuis un acces step/group (`step = ev.get("step")`) ;
    * `champ`   : CLE de dict litteral dont la valeur est un acces step/group
      (`gstack.append({"code": gcode, ...})` -> `frame["code"]` est un groupe). Ce motif-la n'est
      pas theorique : c'est exactement par lui que `rl_collect_batch.py` comparait `fr["code"]`
      a des ordinaux de `GroupType` ;
    * `const`   : constante MODULE affectee a un tuple/liste/set d'entiers (`_USER = (11, 12, 13)`)
      -- sans quoi `gcode in _USER` passe sous le radar, le litteral etant derriere un nom."""

    def __init__(self):
        self.alias: dict = {}
        self.champ: dict = {}
        self.const: dict = {}

    def _bind(self, targets, value):
        k = _direct_key(value)
        if k:
            for t in targets:
                if isinstance(t, ast.Name):
                    self.alias[t.id] = k
            return
        vals = _literals(value)
        if vals is not None and len(vals) > 1:
            for t in targets:
                if isinstance(t, ast.Name):
                    self.const[t.id] = vals

    def visit_Dict(self, node):
        for cle, val in zip(node.keys, node.values):
            if isinstance(cle, ast.Constant) and isinstance(cle.value, str):
                k = _direct_key(val) or (self.alias.get(val.id)
                                         if isinstance(val, ast.Name) else None)
                if k:
                    self.champ[cle.value] = k
        self.generic_visit(node)

    def visit_Assign(self, node):
        self._bind(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self._bind([node.target], node.value)
        self.generic_visit(node)

    def visit_NamedExpr(self, node):
        self._bind([node.target], node.value)
        self.generic_visit(node)


def _literals(node) -> "list | None":
    """Litteral entier, ou tuple/liste/set d'entiers -> liste d'ordinaux ; sinon None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        out = []
        for e in node.elts:
            if isinstance(e, ast.Constant) and isinstance(e.value, int) \
                    and not isinstance(e.value, bool):
                out.append(e.value)
            else:
                return None
        return out or None
    return None


class _Sweep(ast.NodeVisitor):
    def __init__(self, al: _Aliases):
        self.al = al
        self.hits: list = []

    def _key(self, node) -> "str | None":
        k = _direct_key(node)
        if k:
            return k
        if isinstance(node, ast.Name):
            return self.al.alias.get(node.id)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            return self.al.champ.get(node.slice.value)
        # `stack[0][0]` etc. : on ne devine pas -- hors perimetre assume.
        return None

    def _vals(self, node) -> "list | None":
        v = _literals(node)
        if v is not None:
            return v
        if isinstance(node, ast.Name):
            return self.al.const.get(node.id)
        return None

    def visit_Compare(self, node):
        sides = [node.left] + list(node.comparators)
        for i, op in enumerate(node.ops):
            lhs, rhs = sides[i], sides[i + 1]
            for a, b in ((lhs, rhs), (rhs, lhs)):
                k = self._key(a)
                if not k:
                    continue
                vals = self._vals(b)
                if vals is None:
                    continue
                self.hits.append((node.lineno, k, vals, type(op).__name__))
                break
        self.generic_visit(node)


def sweep_py(verbose: bool) -> tuple:
    step_now = _enum_map(current_build(), STEP_ENUM)
    group_now = _enum_map(current_build(), GROUP_ENUM)
    prev = [b for b in _builds() if b != current_build()]
    step_prev = _enum_map(prev[-1], STEP_ENUM) if prev else {}
    group_prev = _enum_map(prev[-1], GROUP_ENUM) if prev else {}

    fails, infos = [], []
    for p in _py_du_depot():
        rel = _rel_ou_none(p)
        if rel is None or rel in ALLOWLIST:
            continue
        try:
            src = io.open(p, encoding="utf-8").read()
            tree = ast.parse(src, filename=rel)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        al = _Aliases()
        al.visit(tree)
        al.visit(tree)      # 2e passe : les cles de dict dependent des alias deja liees
        sw = _Sweep(al)
        sw.visit(tree)
        for line, kind, vals, op in sw.hits:
            now = step_now if kind == "step" else group_now
            old = step_prev if kind == "step" else group_prev
            det = []
            for v in vals:
                n_now, n_old = now.get(v, "?"), old.get(v, "?")
                det.append("%d=%s%s" % (v, n_now, "" if n_old == n_now else " (avant: %s)" % n_old))
            row = (rel, line, kind, op, ", ".join(det))
            (infos if rel.startswith(INFO_PREFIXES) else fails).append(row)
    return fails, infos, (prev[-1] if prev else None)


# --------------------------------------------------------------------------------------------
# Etape 2 -- table de labels POSITIONNELLE du frontend
# --------------------------------------------------------------------------------------------

JS = REPO / "frida" / "public" / "src" / "battle-log.js"
JS_TABLES = (("STEP_LABEL", STEP_ENUM), ("GROUP_LABEL", GROUP_ENUM))


def _js_array(src: str, const: str) -> "list | None":
    i = src.find("const %s = [" % const)
    if i < 0:
        return None
    j = src.find("];", i)
    if j < 0:
        return None
    body = src[src.find("[", i) + 1:j]
    out = []
    for chunk in body.split(","):
        c = chunk.strip()
        if not c or c.startswith("//"):
            continue
        c = c.split("//")[0].strip()
        if len(c) >= 2 and c[0] == '"' and c[-1] == '"':
            out.append(c[1:-1])
    return out


def sweep_js() -> list:
    """La table JS est indexee PAR ORDINAL -- un membre retire la decale entierement.
    Le nom du jeu porte `_` la ou le frontend affiche `.` (System_StartTurn / System.StartTurn) :
    on compare sur une forme normalisee."""
    if not JS.is_file():
        return [("%s : ABSENT" % JS.relative_to(REPO).as_posix(),)]
    src = io.open(JS, encoding="utf-8").read()
    bad = []
    for const, cle in JS_TABLES:
        arr = _js_array(src, const)
        ref = _enum_map(current_build(), cle)
        if arr is None:
            bad.append(("%s : bloc `const %s = [` introuvable" % (JS.name, const),))
            continue
        for i, nom in enumerate(arr):
            attendu = ref.get(i)
            if attendu is None:
                bad.append(("%s[%d] = %r ; le build courant n'a pas cet ordinal"
                            % (const, i, nom),))
            elif nom.replace(".", "_") != attendu.replace(".", "_"):
                bad.append(("%s[%d] = %r ; attendu %r" % (const, i, nom, attendu),))
    return bad


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    build = current_build()
    step_now = _enum_map(build, STEP_ENUM)
    group_now = _enum_map(build, GROUP_ENUM)
    print("[274] build courant : %s" % build)
    print("[274] etape 0 : StepType(%d) GroupType(%d) -- source %s"
          % (len(step_now), len(group_now), SE.source_path().relative_to(REPO).as_posix()))
    prev = [b for b in _builds() if b != build]
    if prev:
        b0 = prev[-1]
        for cle, lbl in ((STEP_ENUM, "StepType"), (GROUP_ENUM, "GroupType")):
            o, n = _enum_map(b0, cle), _enum_map(build, cle)
            d = [i for i in sorted(set(o) | set(n)) if o.get(i) != n.get(i)]
            print("[274] etape 0 : %s %s(%d) -> %s(%d) ; %d ordinaux divergents"
                  % (lbl, b0, len(o), build, len(n), len(d)))
            if args.verbose:
                for i in d:
                    print("         %3d %s -> %s" % (i, o.get(i), n.get(i)))
    else:
        print("[274] etape 0 : un seul build sous data/symbols -- pas de diff possible")

    fails, infos, b_prev = sweep_py(args.verbose)
    print("[274] etape 1 : %d ordinal(aux) step/group en dur dans le code VIVANT, %d en legacy"
          % (len(fails), len(infos)))
    for rel, line, kind, op, det in fails:
        print("   FAIL %s:%d  %s %s  -> %s" % (rel, line, kind, op, det))
    for rel, line, kind, op, det in infos:
        print("   info %s:%d  %s %s  -> %s" % (rel, line, kind, op, det))

    js = sweep_js()
    print("[274] etape 2 : table de labels frontend -- %d divergence(s)" % len(js))
    for (m,) in js:
        print("   FAIL %s" % m)

    ko = len(fails) + len(js)
    print("[274] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
